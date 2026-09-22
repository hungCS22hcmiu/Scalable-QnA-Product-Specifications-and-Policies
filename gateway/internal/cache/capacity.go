package cache

import (
	"context"
	"fmt"

	"github.com/redis/go-redis/v9"
)

// Bounded cache with LRU eviction, enforced HERE rather than by Redis.
//
// This is what interfaces.md D prescribes as of v0.6 (ADR-031). It replaced the v0.3 two-region
// split, which could not express what ADR-027 requires:
//
//   - ADR-027 fixes capacity at `round(0.25 * K)` **entries** -- a COUNT.
//   - §D prescribes a "logical DB with allkeys-lru", which evicts by **bytes**, and cannot be
//     told to hold N entries.
//   - `maxmemory-policy` is **server-global**, not per logical DB, so the two-region split §D
//     describes is not actually achievable on one redis-stack-server. Any allkeys-* setting can
//     evict the `dep:*` records of §E, which makes their entries permanently unpurgeable and
//     breaks C2's completeness with no error at all (rules.md #5).
//
// `make redis-check` already refused a byte budget for exactly the first reason. Enforcing the
// count here satisfies ADR-027 exactly and leaves Redis evicting nothing at all -- so the
// dependency region is safe BY CONSTRUCTION rather than by a configuration a later CONFIG SET
// could silently undo, which is stronger than the v0.3 split asked for.

// lruKey is the eviction index: a ZSET of entry_id scored by last access.
//
// It is NOT prefixed t1:/t2:, and must never be: those prefixes are what the invalidator and the
// index scan for. It is also not itself evictable, which is correct -- losing the index would
// strand every entry it tracked, uncounted and unevictable.
const lruKey = "lru:entries"

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
type EvictedEntry struct {
	EntryID string
	T1Key   string
}

// TrimToCapacity evicts least-recently-used entries until at most capacity remain. A capacity of
// zero or less means unbounded and does nothing.
//
// ⚠️ Both tiers of a victim die TOGETHER. Deleting t2 alone would leave the Tier-1 copy serving
// the same answer from a bare hash lookup that runs no reuse rule and no similarity check -- so
// the entry would still be served while being absent from the cache the experiment believes it is
// measuring, and the capacity sweep would measure nothing. `t1_key` is stored on the Tier-2 record
// precisely so this is possible (interfaces.md D).
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
		t1Key, err := s.rdb.HGet(ctx, tier2KeyPrefix+entryID, "t1_key").Result()
		if err != nil && err != redis.Nil {
			return evicted, fmt.Errorf("cache: reading t1_key for eviction of %s: %w", entryID, err)
		}

		pipe := s.rdb.TxPipeline()
		pipe.Del(ctx, tier2KeyPrefix+entryID)
		if t1Key != "" {
			pipe.Del(ctx, t1Key)
		}
		pipe.ZRem(ctx, lruKey, entryID)
		if _, err := pipe.Exec(ctx); err != nil {
			return evicted, fmt.Errorf("cache: evicting %s: %w", entryID, err)
		}
		evicted = append(evicted, EvictedEntry{EntryID: entryID, T1Key: t1Key})
	}
	return evicted, nil
}

// CachedEntries is the current entry count, for the startup banner and the run manifest.
func (s *Store) CachedEntries(ctx context.Context) (int64, error) {
	return s.rdb.ZCard(ctx, lruKey).Result()
}
