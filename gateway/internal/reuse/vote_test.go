package reuse

import "testing"

// Item 6.0a, ADR-028: the POLICY namespace is the policy document with the MOST retrieved chunks, and
// on a tie the one whose first chunk ranks higher. The old rule took the first policy chunk's document.
// TestNamespaceUsesRankNotSetMembership (lane_test.go) still holds, because each list there has one
// chunk per document and the tie rule then picks rank 1.

func TestVoteTwoToOneBeatsRankOne(t *testing.T) {
	// The rank-1 policy chunk is in the return document, but two of the three policy chunks are in the
	// warranty document. The vote follows the majority; the old rule followed rank 1.
	ids := []string{
		"policy-return-laptops-new#chunk-0",
		"policy-warranty-laptops#chunk-1",
		"product-laptops-b07qvm5x8w#chunk-0",
		"policy-warranty-laptops#chunk-0",
	}
	if got, want := Namespace(LanePolicy, ids, ""), "policy-warranty-laptops"; got != want {
		t.Errorf("the vote = %q, want %q (2 chunks against 1)", got, want)
	}
	if got, want := Namespace(LanePolicy, ids, "product-laptops-b07qvm5x8w"), "policy-warranty-laptops@product-laptops-b07qvm5x8w"; got != want {
		t.Errorf("with a product the namespace = %q, want %q", got, want)
	}
	if got := firstDocIDWithPrefix(ids, policyPrefix); got != "policy-return-laptops-new" {
		t.Errorf("the old rule gave %q: the test no longer separates the two rules", got)
	}
}

func TestVoteTieGoesToTheBetterRank(t *testing.T) {
	// One chunk each: a tie, and the document whose first chunk comes first wins, in either order.
	a := []string{"policy-a#chunk-0", "policy-b#chunk-0"}
	b := []string{"policy-b#chunk-0", "policy-a#chunk-0"}
	if got := policyDocByVote(a); got != "policy-a" {
		t.Errorf("tie, a first: %q, want policy-a", got)
	}
	if got := policyDocByVote(b); got != "policy-b" {
		t.Errorf("tie, b first: %q, want policy-b", got)
	}
	// Two chunks each, interleaved: still a tie, and the first chunk decides.
	c := []string{"policy-b#chunk-0", "policy-a#chunk-0", "policy-a#chunk-1", "policy-b#chunk-1"}
	if got := policyDocByVote(c); got != "policy-b" {
		t.Errorf("2-2 tie, b ranks first: %q, want policy-b", got)
	}
	// A tie for the lead, with a third document behind both.
	d := []string{"policy-c#chunk-0", "policy-b#chunk-0", "policy-a#chunk-0", "policy-a#chunk-1", "policy-b#chunk-1"}
	if got := policyDocByVote(d); got != "policy-b" {
		t.Errorf("a-b tie at 2, b first: %q, want policy-b", got)
	}
}

func TestVoteIsStableAcrossManyCalls(t *testing.T) {
	// The tally is a map. The answer must not depend on its iteration order.
	ids := []string{"policy-x#chunk-0", "policy-y#chunk-0", "policy-z#chunk-0", "policy-y#chunk-1", "policy-x#chunk-1"}
	for i := 0; i < 200; i++ {
		if got := policyDocByVote(ids); got != "policy-x" {
			t.Fatalf("call %d: %q, want policy-x (2-2 tie, x ranks first)", i, got)
		}
	}
}

func TestVoteIgnoresProductChunksAndSurvivesNone(t *testing.T) {
	if got := policyDocByVote([]string{"product-a#chunk-0", "product-a#chunk-1"}); got != "" {
		t.Errorf("no policy chunk: %q, want empty", got)
	}
	if got := policyDocByVote(nil); got != "" {
		t.Errorf("nil: %q, want empty", got)
	}
	// Product chunks never vote, however many there are.
	ids := []string{"product-a#chunk-0", "product-a#chunk-1", "product-a#chunk-2", "policy-p#chunk-0"}
	if got := policyDocByVote(ids); got != "policy-p" {
		t.Errorf("= %q, want policy-p", got)
	}
}

func TestVoteGivesMixedItsPolicyPart(t *testing.T) {
	// MIXED: "{product}|{policy}". The policy part is the vote too, on the read and the write path alike.
	ids := []string{
		"policy-return-laptops-new#chunk-0",
		"product-laptops-b07qvm5x8w#chunk-0",
		"policy-warranty-laptops#chunk-0",
		"policy-warranty-laptops#chunk-1",
	}
	got := Namespace(LaneMixed, ids, "product-laptops-b07qvm5x8w")
	if want := "product-laptops-b07qvm5x8w|policy-warranty-laptops"; got != want {
		t.Errorf("MIXED namespace = %q, want %q", got, want)
	}
	// With no policy chunk, MIXED has no namespace: half a composite key must never be a wildcard.
	if got := Namespace(LaneMixed, []string{"product-a#chunk-0"}, "product-a"); got != "" {
		t.Errorf("MIXED with no policy chunk: %q, want empty", got)
	}
}

func TestVoteDoesNotChangeTheSpecLane(t *testing.T) {
	ids := []string{"policy-x#chunk-0", "product-first#chunk-0", "product-second#chunk-0", "product-second#chunk-1"}
	// SPEC with no product still takes the highest-ranked product chunk, not a vote.
	if got := Namespace(LaneSpec, ids, ""); got != "product-first" {
		t.Errorf("SPEC fallback = %q, want product-first", got)
	}
	if got := Namespace(LaneSpec, ids, "product-given"); got != "product-given" {
		t.Errorf("SPEC with a product = %q, want product-given", got)
	}
}
