package cache

import (
	"context"
	"fmt"

	"github.com/redis/go-redis/v9"
)

// purgeScript removes one entry from both tiers and from the eviction index, in one atomic step.
//
// KEYS[1] = t2:{entry_id}, KEYS[2] = lru:entries. ARGV[1] = entry_id, ARGV[2] = the Tier-1 key
// ("" when unknown).
//
// ⚠️ The Tier-1 key is deleted ONLY IF its `entry_id` field still names this entry. Tier 1 is keyed
// by the normalised query, so a newer entry for the same query reuses the key. A blind DEL would
// remove that newer entry too -- over-invalidation the precision metric would charge to the purge.
// The compare and the delete run in one script so nothing can overwrite the key between them.
//
// The Tier-1 key is passed in ARGV because its name is only known at run time. Redis Cluster would
// refuse that; this is fine on the single standalone server the hardware envelope fixes.
var purgeScript = redis.NewScript(`
redis.call('DEL', KEYS[1])
if ARGV[2] ~= '' then
  if redis.call('HGET', ARGV[2], 'entry_id') == ARGV[1] then
    redis.call('DEL', ARGV[2])
  end
end
redis.call('ZREM', KEYS[2], ARGV[1])
return 1
`)

// PurgeEntry deletes entry_id's Tier-2 record, its Tier-1 record (if that record still names it) and
// its lru:entries member. It deletes nothing of the dependency region: dep:* and entry:* belong to
// deps/, which calls this method (interfaces.md §E).
//
// t1Key may be empty, in which case it is read from the Tier-2 record. An entry written with no
// Tier-2 record has no such field, so the caller (deps/) passes the key it recorded at registration.
func (s *Store) PurgeEntry(ctx context.Context, entryID, t1Key string) error {
	if entryID == "" {
		return nil
	}
	if t1Key == "" {
		k, err := s.rdb.HGet(ctx, tier2KeyPrefix+entryID, "t1_key").Result()
		if err != nil && err != redis.Nil {
			return fmt.Errorf("cache: reading t1_key for purge of %s: %w", entryID, err)
		}
		t1Key = k
	}
	if err := purgeScript.Run(ctx, s.rdb, []string{tier2KeyPrefix + entryID, lruKey}, entryID, t1Key).Err(); err != nil {
		return fmt.Errorf("cache: purging %s: %w", entryID, err)
	}
	return nil
}
