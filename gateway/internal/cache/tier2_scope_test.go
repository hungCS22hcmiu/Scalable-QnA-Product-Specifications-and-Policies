package cache

import (
	"context"
	"testing"

	"github.com/hung/thesis/gateway/internal/testredis"
)

// Item 6.0a (ADR-030): `scope` is a plain stored field. A shared entry lives in the policy document's own
// namespace, a product one in "{policy_doc}@{product_id}"; the index is unchanged because `namespace` is
// already a TAG. This is cache/'s half: the field and the namespace survive a round trip through Redis,
// and an entry written before the arm (no `scope`) reads as "product". Runs on DB 0, where the search
// module's index lives (the throwaway server of `make test-go`).
func TestTier2ScopeRoundTripsAndAnOldEntryReadsAsProduct(t *testing.T) {
	rdb := testredis.Client(t, 0)
	s := NewStore(rdb, 768)
	ctx := context.Background()
	dropCacheIndexAtEnd(t, rdb)

	vec := make([]float32, s.dim)
	vec[0] = 1
	write := func(id, ns, scope string) {
		t.Helper()
		if err := s.PutTier2(ctx, Tier2Entry{
			EntryID: id, QueryText: "q", Answer: "a", SourceChunkIDs: []string{"policy-return-electronics#chunk-0"},
			T1Key: "t1:" + id, DatasetEpoch: 1, Namespace: ns, Lane: "POLICY", Scope: scope,
		}, vec); err != nil {
			t.Fatalf("PutTier2 %s: %v", id, err)
		}
	}
	write("shared1", "policy-return-electronics", "shared")
	write("product1", "policy-return-electronics@product-electronics-a", "product")
	write("empty1", "policy-return-electronics@product-electronics-b", "") // a caller that sets no scope
	write("weird1", "policy-return-electronics@product-electronics-c", "global")
	// An entry from before the arm: the hash has no `scope` field at all.
	if err := rdb.HSet(ctx, "t2:legacy1", map[string]any{
		"embedding": encodeVector(vec), "query_text": "q", "answer": "a", "source_chunk_ids": `["policy-return-electronics#chunk-0"]`,
		"t1_key": "t1:legacy1", "dataset_epoch": 1, "source_overlap": 0, "hit_count": 0, "created_at": "2026-11-13T00:00:00Z",
		"namespace": "policy-return-electronics@product-electronics-d", "lane": "POLICY",
	}).Err(); err != nil {
		t.Fatal(err)
	}
	if err := s.EnsureCacheIndex(ctx); err != nil {
		t.Fatalf("EnsureCacheIndex: %v", err)
	}

	for _, tc := range []struct{ ns, wantID, wantScope string }{
		{"policy-return-electronics", "shared1", "shared"},
		{"policy-return-electronics@product-electronics-a", "product1", "product"},
		{"policy-return-electronics@product-electronics-b", "empty1", "product"},
		{"policy-return-electronics@product-electronics-c", "weird1", "product"}, // never an unplanned value
		{"policy-return-electronics@product-electronics-d", "legacy1", "product"},
	} {
		got, err := s.NearestTier2InNamespace(ctx, vec, tc.ns, 1)
		if err != nil || len(got) != 1 {
			t.Fatalf("search in %q: %v, %v", tc.ns, got, err)
		}
		if got[0].Entry.EntryID != tc.wantID || got[0].Entry.Scope != tc.wantScope {
			t.Errorf("%q: entry %s scope %q, want %s %q", tc.ns, got[0].Entry.EntryID, got[0].Entry.Scope, tc.wantID, tc.wantScope)
		}
	}
	// The shared namespace holds only the shared entry: a product namespace never leaks into it.
	got, _ := s.NearestTier2InNamespace(ctx, vec, "policy-return-electronics", 5)
	if len(got) != 1 || got[0].Entry.EntryID != "shared1" {
		t.Errorf("the shared namespace holds %d entries, want only shared1", len(got))
	}
}
