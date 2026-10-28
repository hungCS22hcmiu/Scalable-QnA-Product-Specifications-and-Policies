package cache

import (
	"context"
	"fmt"
)

// PurgeEntry deletes entry_id's Tier-2 record, every Tier-1 record that still names it, its
// lru:t1keys:{entry_id} set and its lru:entries member, in one atomic step. It deletes nothing of the
// dependency region: dep:* and entry:* belong to deps/, which calls this method (interfaces.md §E).
//
// The work is dropEntryScript's (capacity.go), the same script the trim runs, so a purge and an eviction
// can never disagree about what an entry owns. The Tier-1 keys come from the set, from the Tier-2
// record's `t1_key`, and from t1Key. Each is deleted only if its `entry_id` still names this entry:
// Tier 1 is keyed by the normalised query, so a newer entry for the same query reuses the key, and a
// blind DEL would remove that newer entry too -- over-invalidation the precision metric would charge to
// the purge.
//
// t1Key may be empty. An entry written with no Tier-2 record has no `t1_key` field to read, so the
// caller (deps/) passes the key it recorded at registration.
func (s *Store) PurgeEntry(ctx context.Context, entryID, t1Key string) error {
	if entryID == "" {
		return nil
	}
	if _, _, err := s.dropEntry(ctx, entryID, t1Key); err != nil {
		return fmt.Errorf("cache: purging %s: %w", entryID, err)
	}
	return nil
}
