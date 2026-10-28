package cache

import (
	"context"
	"testing"
	"time"
)

// requireExists fails the test unless every key has the wanted existence (1 = present, 0 = absent).
func requireExists(t *testing.T, s *Store, want int64, keys ...string) {
	t.Helper()
	ctx := context.Background()
	for _, k := range keys {
		n, err := s.rdb.Exists(ctx, k).Result()
		if err != nil {
			t.Fatal(err)
		}
		if n != want {
			t.Fatalf("%s: exists=%d, want %d", k, n, want)
		}
	}
}

func lruHas(t *testing.T, s *Store, entryID string) bool {
	t.Helper()
	_, err := s.rdb.ZScore(context.Background(), lruKey, entryID).Result()
	return err == nil
}

// The purge takes an entry out of BOTH tiers and out of the eviction index, and nothing else.
// Deleting t2 alone would leave Tier 1 serving the old answer from a bare hash lookup.
func TestPurgeEntryDeletesBothTiers(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	seed(t, s, "victim", "t1:victimkey", time.Now())
	seed(t, s, "keeper", "t1:keeperkey", time.Now())

	if err := s.PurgeEntry(ctx, "victim", "t1:victimkey"); err != nil {
		t.Fatal(err)
	}
	requireExists(t, s, 0, tier2KeyPrefix+"victim", "t1:victimkey")
	if lruHas(t, s, "victim") {
		t.Fatal("victim is still in lru:entries")
	}
	requireExists(t, s, 1, tier2KeyPrefix+"keeper", "t1:keeperkey")
	if !lruHas(t, s, "keeper") {
		t.Fatal("keeper left lru:entries -- the purge touched an entry it was not asked about")
	}
}

// ⚠️ DC 4. Tier 1 is keyed by the normalised query, so a newer entry for the same query reuses the
// key. A blind DEL from the older entry's purge would delete the newer entry's record too:
// over-invalidation that the precision metric would charge to blind purge.
func TestPurgeEntryLeavesReusedTier1Key(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	seed(t, s, "older", "t1:k", time.Now())
	// A newer entry now owns t1:k.
	if err := s.rdb.HSet(ctx, "t1:k", "entry_id", "newer").Err(); err != nil {
		t.Fatal(err)
	}

	if err := s.PurgeEntry(ctx, "older", "t1:k"); err != nil {
		t.Fatal(err)
	}
	requireExists(t, s, 0, tier2KeyPrefix+"older")
	if lruHas(t, s, "older") {
		t.Fatal("older is still in lru:entries")
	}
	requireExists(t, s, 1, "t1:k")
	got, err := s.rdb.HGet(ctx, "t1:k", "entry_id").Result()
	if err != nil || got != "newer" {
		t.Fatalf("t1:k entry_id = %q (err %v), want it left naming newer", got, err)
	}
}

// With no t1Key given, the key comes from the t2 record's t1_key field.
func TestPurgeEntryReadsT1KeyFromTier2(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	seed(t, s, "victim", "t1:fromtier2", time.Now())

	if err := s.PurgeEntry(ctx, "victim", ""); err != nil {
		t.Fatal(err)
	}
	requireExists(t, s, 0, tier2KeyPrefix+"victim", "t1:fromtier2")
	if lruHas(t, s, "victim") {
		t.Fatal("victim is still in lru:entries")
	}
}
