package cache

import (
	"context"
	"fmt"

	"github.com/redis/go-redis/v9"
)

// Bounded cache with LRU eviction, enforced HERE rather than by Redis.
//
// This is what interfaces.md D prescribes as of v0.6. It replaced the v0.3 two-region
// split, which could not express what the capacity ratio requires:
//
// fixes capacity at `round(0.25 * K)` **entries** -- a COUNT.
//   - §D prescribes a "logical DB with allkeys-lru", which evicts by **bytes**, and cannot be
//     told to hold N entries.
//   - `maxmemory-policy` is **server-global**, not per logical DB, so the two-region split §D
//     describes is not actually achievable on one redis-stack-server. Any allkeys-* setting can
//     evict the `dep:*` records of §E, which makes their entries permanently unpurgeable and
//     breaks C2's completeness with no error at all.
//
// `make redis-check` already refused a byte budget for exactly the first reason. Enforcing the
// count here satisfies the capacity ratio exactly and leaves Redis evicting nothing at all -- so the
// dependency region is safe BY CONSTRUCTION rather than by a configuration a later CONFIG SET
// could silently undo, which is stronger than the v0.3 split asked for.

// lruKey is the eviction index: a ZSET of entry_id scored by last access.
//
// It is NOT prefixed t1:/t2:, and must never be: those prefixes are what the invalidator and the
// index scan for. It is also not itself evictable, which is correct -- losing the index would
// strand every entry it tracked, uncounted and unevictable.
const lruKey = "lru:entries"

// t1KeysPrefix names the per-entry set of every Tier-1 key written for an entry:
// lru:t1keys:{entry_id} (interfaces.md §D, v0.19).
//
// The set is in the `lru:` region on purpose, not in deps/'s entry:{entry_id}. Eviction lives in this
// package and this package never reads the dependency records (item 4.1). `make demo-reset` and
// `make footprint` delete `lru:` together with t1: and t2:, and nothing reads the set but this package.
// It is not a dependency record, so invariant 1 (dependency records are never evicted) is untouched.
const t1KeysPrefix = "lru:t1keys:"

// t1KeysKey is the set's key for entryID.
func t1KeysKey(entryID string) string {
	return t1KeysPrefix + entryID
}

// Touch records an access to entry_id. Called on every hit, in either tier, and on write-back.
//
// Fire-and-forget at the call site: an access this misses only makes the entry look staler than
// it is, which costs a little hit rate. Failing a served request over it would cost availability
// to protect a heuristic.
func (s *Store) Touch(ctx context.Context, entryID string, nowUnixNano int64) error {
	if entryID == "" {
		return nil
	}
	return s.rdb.ZAdd(ctx, lruKey, redis.Z{Score: float64(nowUnixNano), Member: entryID}).Err()
}

// EvictedEntry is one victim, reported so the caller can log what capacity actually cost.
//
// T1Key is the Tier-2 record's `t1_key` field, as read when the victim went. T1Keys is every Tier-1
// key that was actually deleted for it: the set's members and that field, minus any key a newer entry
// had taken over.
type EvictedEntry struct {
	EntryID string
	T1Key   string
	T1Keys  []string
}

// dropEntryScript is what "this entry is gone" means. Both the trim and the purge run it, so the two
// can never disagree about what an entry owns.
//
// KEYS[1] = t2:{entry_id}, KEYS[2] = lru:entries, KEYS[3] = lru:t1keys:{entry_id}.
// ARGV[1] = entry_id, ARGV[2] = an extra Tier-1 key the caller knows of ("" when none).
//
// It gathers the candidate Tier-1 keys from three places: the set, the Tier-2 record's `t1_key`, and the
// key the caller passes. Each is deleted ONLY IF its `entry_id` field still names this entry. Tier 1 is
// keyed by the normalised query, so a newer entry for the same query reuses the key, and a blind DEL
// would remove that newer entry's Tier-1 copy. The compare and the delete run in one script, so nothing
// can overwrite a key between them. A key listed twice is harmless: the second HGET finds nothing.
// Then it deletes t2:, the set and the lru:entries member. It never touches dep:* or entry:*.
//
// It returns {t2's t1_key or "", {the Tier-1 keys it deleted}}.
//
// The Tier-1 key names come from the set at run time, so they are not in KEYS. Redis Cluster would
// refuse that; this is fine on the single standalone server the hardware envelope fixes.
var dropEntryScript = redis.NewScript(`
local cands = redis.call('SMEMBERS', KEYS[3])
local own = redis.call('HGET', KEYS[1], 't1_key')
if own then table.insert(cands, own) end
if ARGV[2] ~= '' then table.insert(cands, ARGV[2]) end
local deleted = {}
for _, k in ipairs(cands) do
  if redis.call('HGET', k, 'entry_id') == ARGV[1] then
    redis.call('DEL', k); table.insert(deleted, k)
  end
end
redis.call('DEL', KEYS[1], KEYS[3])
redis.call('ZREM', KEYS[2], ARGV[1])
return {own or '', deleted}
`)

// dropEntry runs dropEntryScript for entryID. It returns the Tier-2 record's `t1_key` (empty when the
// entry had no Tier-2 record) and the Tier-1 keys that were deleted.
func (s *Store) dropEntry(ctx context.Context, entryID, extraT1Key string) (string, []string, error) {
	res, err := dropEntryScript.Run(ctx, s.rdb,
		[]string{tier2KeyPrefix + entryID, lruKey, t1KeysKey(entryID)}, entryID, extraT1Key).Result()
	if err != nil {
		return "", nil, err
	}
	parts, ok := res.([]any)
	if !ok || len(parts) != 2 {
		return "", nil, fmt.Errorf("cache: dropEntry script returned %T %v, want a pair", res, res)
	}
	t2T1Key, _ := parts[0].(string)
	list, _ := parts[1].([]any)
	deleted := make([]string, 0, len(list))
	for _, v := range list {
		if k, ok := v.(string); ok {
			deleted = append(deleted, k)
		}
	}
	return t2T1Key, deleted, nil
}

// TrimToCapacity evicts least-recently-used entries until at most capacity remain. A capacity of
// zero or less means unbounded and does nothing.
//
// ⚠️ Both tiers of a victim die TOGETHER. Deleting t2 alone would leave the Tier-1 copy serving
// the same answer from a bare hash lookup that runs no reuse rule and no similarity check -- so
// the entry would still be served while being absent from the cache the experiment believes it is
// measuring, and the capacity sweep would measure nothing. `t1_key` is stored on the Tier-2 record
// precisely so this is possible (interfaces.md D). "Both tiers" now means EVERY Tier-1 key of the
// victim: the ones in its lru:t1keys:{entry_id} set (the miss key, promoted keys, a Tier-1-only
// entry's key) and the t2 record's `t1_key`, each deleted only if it still names the victim
// (dropEntryScript). Entries written before the set existed still go through `t1_key`.
func (s *Store) TrimToCapacity(ctx context.Context, capacity int) ([]EvictedEntry, error) {
	if capacity <= 0 {
		return nil, nil
	}
	n, err := s.rdb.ZCard(ctx, lruKey).Result()
	if err != nil {
		return nil, err
	}
	excess := n - int64(capacity)
	if excess <= 0 {
		return nil, nil
	}

	// Oldest first: index 0 is the lowest score, i.e. the least recently accessed.
	victims, err := s.rdb.ZRange(ctx, lruKey, 0, excess-1).Result()
	if err != nil {
		return nil, err
	}

	evicted := make([]EvictedEntry, 0, len(victims))
	for _, entryID := range victims {
		t2T1Key, deleted, err := s.dropEntry(ctx, entryID, "")
		if err != nil {
			return evicted, fmt.Errorf("cache: evicting %s: %w", entryID, err)
		}
		evicted = append(evicted, EvictedEntry{EntryID: entryID, T1Key: t2T1Key, T1Keys: deleted})
	}
	return evicted, nil
}

// CachedEntries is the current entry count. Only the tests call it today; it is meant for the run
// manifest, which item 5.1 defines.
func (s *Store) CachedEntries(ctx context.Context) (int64, error) {
	return s.rdb.ZCard(ctx, lruKey).Result()
}
