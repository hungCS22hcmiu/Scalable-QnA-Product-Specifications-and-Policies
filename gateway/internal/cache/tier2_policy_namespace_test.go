package cache

import (
	"context"
	"math"
	"testing"

	"github.com/hung/thesis/gateway/internal/testredis"
)

// ADR-024, item 5.6 (docs/work/2026-11-10-policy-namespace-product/): a POLICY namespace is now
// `{policy_doc}@{product_id}`, for example `policy-returns-01@product-kettle-01`. The reuse rule is in
// reuse/ and is tested there. This test is cache/'s half: that the TAG field and escapeTag carry the new
// value through Redis unchanged, so a search in one namespace returns that namespace's entry and no other.
//
// If Redis did not match the value (an unescaped `@`, or the TAG field splitting it), every POLICY lookup
// would be a miss with no error, and the hit rate would fall to zero in a way that reads like the expected
// cost of the change. It uses literal values, so it does not depend on reuse/.
//
// It needs DB 0 (the search module creates indexes only there), so it runs on testredis.Client(t, 0): the
// throwaway server of `make test-go`, never :6379.
func TestTier2SearchKeepsPolicyNamespacesApart(t *testing.T) {
	rdb := testredis.Client(t, 0)
	s := NewStore(rdb, 768)
	ctx := context.Background()
	dropCacheIndexAtEnd(t, rdb)

	// One vector for all three entries, so only the namespace can tell them apart: each is the nearest
	// entry to the query, at cosine 1.
	vec := make([]float32, s.dim)
	vec[0] = 1

	entries := []struct{ id, ns string }{
		{"policykettle", "policy-returns-01@product-kettle-01"},
		{"policyheadphones", "policy-returns-01@product-headphones-03"},
		{"policybare", "policy-returns-01"}, // the form with no product_id
	}
	entryOf := map[string]string{}
	for _, e := range entries {
		id, ns := e.id, e.ns
		entryOf[ns] = id
		err := s.PutTier2(ctx, Tier2Entry{
			EntryID:        id,
			QueryText:      "Can I return an unopened item?",
			Answer:         "a",
			SourceChunkIDs: []string{"policy-returns-01#chunk-0"},
			T1Key:          "t1:" + id,
			DatasetEpoch:   1,
			Namespace:      ns,
			Lane:           "POLICY",
		}, vec)
		if err != nil {
			t.Fatalf("seeding %q: %v", ns, err)
		}
	}
	// EnsureCacheIndex returns only when the index has scanned the three entries above.
	if err := s.EnsureCacheIndex(ctx); err != nil {
		t.Fatalf("EnsureCacheIndex: %v", err)
	}

	for _, e := range entries {
		ns := e.ns
		got, err := s.NearestTier2InNamespace(ctx, vec, ns, 3)
		if err != nil {
			t.Fatalf("search in %q: %v", ns, err)
		}
		if len(got) != 1 {
			ids := make([]string, len(got))
			for i, c := range got {
				ids[i] = c.Entry.EntryID + " in " + c.Entry.Namespace
			}
			t.Fatalf("search in %q returned %d entries %q, want exactly 1 (its own)", ns, len(got), ids)
		}
		c := got[0]
		if c.Entry.EntryID != entryOf[ns] {
			t.Errorf("search in %q returned entry %q, want %q", ns, c.Entry.EntryID, entryOf[ns])
		}
		if c.Entry.Namespace != ns {
			t.Errorf("search in %q returned an entry in namespace %q", ns, c.Entry.Namespace)
		}
		if math.Abs(c.Similarity-1) > 1e-6 {
			t.Errorf("search in %q: similarity = %v, want 1", ns, c.Similarity)
		}
	}
}
