package cache

import "testing"

// A TAG value goes into a RediSearch query string, where the characters a doc_id is built from
// are syntax. This is the single most silent failure in the namespace-scoped lookup: an
// unescaped value does not error, it parses as a different query and matches nothing, so every
// scoped lookup becomes a miss and the cache appears to work while never hitting.
func TestEscapeTagEscapesEveryCharacterThatIsQuerySyntax(t *testing.T) {
	cases := map[string]string{
		// "-" leads a negation in RediSearch. Unescaped, `product-headphones-03` is read as
		// "product NOT headphones NOT 03".
		"product-headphones-03": `product\-headphones\-03`,
		// "|" is union, and it is the mixed lane's own separator -- so the composite key is the
		// value most in need of escaping and the one a naive implementation is likeliest to miss.
		"product-headphones-03|policy-warranty": `product\-headphones\-03\|policy\-warranty`,
		"policy-returns-electronics":            `policy\-returns\-electronics`,
		// Underscores and alphanumerics are not syntax and must pass through, or the escaped form
		// stops matching what was actually written to the hash.
		"plain_id42": "plain_id42",
	}
	for in, want := range cases {
		if got := escapeTag(in); got != want {
			t.Errorf("escapeTag(%q) = %q, want %q", in, got, want)
		}
	}
}

// The empty namespace is UNMATCHABLE, never a wildcard (reuse.MatchNamespace). If the scoped
// lookup ever built a query from it, the filter would drop away and the KNN would run over the
// whole cache -- turning "this entry could not be partitioned" into "this entry matches
// everything", which is a false hit on every lookup.
func TestNearestInNamespaceRefusesTheEmptyNamespaceWithoutTouchingRedis(t *testing.T) {
	var s *Store // nil on purpose: reaching Redis at all would panic and fail the test
	got, err := s.NearestTier2InNamespace(nil, nil, "", 1)
	if err != nil || got != nil {
		t.Fatalf("empty namespace: got %v, %v; want nil, nil with no Redis call", got, err)
	}
}
