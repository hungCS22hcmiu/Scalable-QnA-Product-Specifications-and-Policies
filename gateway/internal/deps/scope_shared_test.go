package deps

import (
	"context"
	"testing"

	"github.com/hung/thesis/gateway/internal/cache"
)

// Item 6.0a, done condition 8 (ADR-030). A SHARED entry is written once, for every product of a
// category, and is then served to other products: each such hit promotes a copy into Tier 1 under that
// product's own key. All of those keys are in lru:t1keys:{entry_id}, and an invalidation must take all of
// them with the Tier-2 record. If one survived, another product would be served a stale answer from
// Tier 1 with no error, which no Tier-2 test would show.
//
// The entry depends on every chunk it was generated over, so an edit to the WRITER product's own chunk
// purges it too: that over-invalidation is deliberate (it is counted by item 6.5), and so is tested here.
func TestInvalidateDropsASharedEntryAndItsTier1CopiesUnderTwoProducts(t *testing.T) {
	for _, edited := range []string{
		"policy-return-electronics#chunk-0", // a chunk of the shared policy document
		"product-electronics-a#chunk-0",     // a chunk of the product that happened to write it
	} {
		t.Run(edited, func(t *testing.T) {
			rdb := testRedis(t)
			ctx := context.Background()
			store := cache.NewStore(rdb, 768)
			m := newMap(t, rdb, store, 16)

			const (
				qA, qB, qC = "can i return an unopened item", "may i send back something i never opened", "is a sealed item returnable"
				pA, pB, pC = "product-electronics-a", "product-electronics-b", "product-electronics-c"
			)
			kA := cache.Key(cache.Normalize(qA), pA)
			kB := cache.Key(cache.Normalize(qB), pB)
			kC := cache.Key(cache.Normalize(qC), pC)
			sources := []string{"policy-return-electronics#chunk-0", "product-electronics-a#chunk-0"}

			// The miss of product A writes the entry in both tiers, in the shared namespace.
			if err := store.Put(ctx, qA, pA, cache.Entry{Answer: "a", SourceChunkIDs: sources, EntryID: "S"}); err != nil {
				t.Fatal(err)
			}
			vec := make([]float32, 768)
			vec[0] = 1
			if err := store.PutTier2(ctx, cache.Tier2Entry{
				EntryID: "S", QueryText: qA, Answer: "a", SourceChunkIDs: sources, T1Key: kA,
				DatasetEpoch: 1, Namespace: "policy-return-electronics", Lane: "POLICY", Scope: "shared",
			}, vec); err != nil {
				t.Fatal(err)
			}
			if err := store.Touch(ctx, "S", 1); err != nil {
				t.Fatal(err)
			}
			// Products B and C are served the entry, and each hit is promoted into Tier 1 under its own key.
			for _, p := range []struct{ q, pid string }{{qB, pB}, {qC, pC}} {
				if err := store.Put(ctx, p.q, p.pid, cache.Entry{Answer: "a", SourceChunkIDs: sources, EntryID: "S", Promotion: true}); err != nil {
					t.Fatal(err)
				}
			}
			for _, k := range []string{kA, kB, kC} {
				if !isMember(t, rdb, "lru:t1keys:S", k) {
					t.Fatalf("setup: lru:t1keys:S does not list %s", k)
				}
			}
			if got, _ := rdb.HGet(ctx, "t2:S", "scope").Result(); got != "shared" {
				t.Fatalf("setup: t2:S has scope %q, want shared", got)
			}

			// An unrelated entry, to show the purge is exact.
			seedEntry(t, rdb, "OTHER", "t1:other", true)
			m.Register(Registration{EntryID: "S", Sources: sources, T1Key: kA, DatasetEpoch: 1})
			m.Register(Registration{EntryID: "OTHER", Sources: []string{"product-furniture-z#chunk-0"}, T1Key: "t1:other"})
			barrier(t, m)

			ids, err := m.Invalidate(Event{ChunkID: edited})
			if err != nil {
				t.Fatal(err)
			}
			barrier(t, m)
			if len(ids) != 1 || ids[0] != "S" {
				t.Fatalf("Invalidate(%s) purged %v, want [S]", edited, ids)
			}

			for _, k := range []string{kA, kB, kC, "t2:S", "lru:t1keys:S", "entry:S"} {
				if exists(t, rdb, k) {
					t.Errorf("%s survived the purge of the shared entry", k)
				}
			}
			if inLRU(t, rdb, "S") {
				t.Error("S is still in lru:entries")
			}
			// No Tier-1 key of any product may still name S.
			iter := rdb.Scan(ctx, 0, "t1:*", 100).Iterator()
			for iter.Next(ctx) {
				if id, err := rdb.HGet(ctx, iter.Val(), "entry_id").Result(); err == nil && id == "S" {
					t.Errorf("%s still names the shared entry after the purge", iter.Val())
				}
			}
			if err := iter.Err(); err != nil {
				t.Fatal(err)
			}
			if !exists(t, rdb, "t2:OTHER") {
				t.Error("the purge took an unrelated entry")
			}
		})
	}
}
