package httpapi

import (
	"context"
	"testing"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/hung/thesis/gateway/internal/ragpb"
	"github.com/hung/thesis/gateway/internal/reuse"
)

// ADR-024, item 5.6 (docs/work/2026-11-10-policy-namespace-product/): a POLICY answer is reused only for the
// product it was written for. This test goes through Ask, with fakes (no Redis, no Ollama), so it shows what
// reuse/'s own test cannot: that the write-back and the search build the SAME POLICY namespace. If they
// built different ones, no POLICY entry would ever be found again, and the hit rate would fall to zero with
// no error -- which reads like the expected cost of the change.
//
// This file is new on purpose: the existing httpapi tests are not edited. The harness is harness_test.go's.

// policyRAG is a RAG service whose grounding is POLICY only, for both products of the fake corpus: the same
// two policy chunks. harness_test.go's fakeRAG returns product chunks only, and it is not edited, so this
// file brings its own, as mixed_lane_test.go does. The chunk texts hold every word of the answer, so the
// support gate passes on a reused entry.
type policyRAG struct {
	ragpb.UnimplementedRagServiceServer
}

func policyGrounding() []string {
	return []string{"policy-returns-01#chunk-0", "policy-returns-01#chunk-1"}
}

const policyAnswerText = "unopened items may be returned within 30 days of delivery"

func policyKnows(productID string) bool {
	return productID == kettle.id || productID == headphones.id
}

func (policyRAG) Retrieve(_ context.Context, req *ragpb.RetrieveRequest) (*ragpb.RetrieveResponse, error) {
	if req.GetTopK() != 0 {
		return nil, status.Errorf(codes.InvalidArgument, "Retrieve sent top_k=%d; the gateway must send 0", req.GetTopK())
	}
	if !policyKnows(req.GetProductId()) {
		return nil, status.Errorf(codes.InvalidArgument, "Retrieve for unknown product_id %q", req.GetProductId())
	}
	return &ragpb.RetrieveResponse{
		ChunkIds:     policyGrounding(),
		Scores:       []float32{0.9, 0.8},
		DatasetEpoch: testEpoch,
		Texts: []string{
			"Unopened items may be returned within 30 days of delivery.",
			"Returns are free for unopened items.",
		},
	}, nil
}

func (policyRAG) Answer(req *ragpb.AnswerRequest, stream grpc.ServerStreamingServer[ragpb.AnswerChunk]) error {
	if req.GetTopK() != 0 {
		return status.Errorf(codes.InvalidArgument, "Answer sent top_k=%d; the gateway must send 0", req.GetTopK())
	}
	if !policyKnows(req.GetProductId()) {
		return status.Errorf(codes.InvalidArgument, "Answer for unknown product_id %q", req.GetProductId())
	}
	return stream.Send(&ragpb.AnswerChunk{
		Text:           policyAnswerText,
		Done:           true,
		SourceChunkIds: policyGrounding(),
		ModelUsed:      testModel,
		DatasetEpoch:   testEpoch,
	})
}

// The same policy question from two products, then a paraphrase from the first. The default band (off) is
// the harness's own. Three requests, one search each, so namespacesSearched() reads [A, B, A] and the two
// entries written (by A's and B's misses) are in the namespaces searched for A and for B.
func TestPolicyAnswerIsNotReusedForAnotherProduct(t *testing.T) {
	const (
		question   = "Can I return an unopened item?"
		paraphrase = "May I send back an item I never opened?"
	)
	hs := newHarness(t, 1, 0)
	hs.useRAG(t, policyRAG{})

	// 1. Product A (the kettle) asks. Nothing is cached, so it is a MISS and it writes a POLICY entry.
	c1 := hs.askNear(t, question, 1, 1.0, kettle)
	if got := c1.response(t).text("cache"); got != "MISS" {
		t.Fatalf("request 1: cache = %q, want MISS", got)
	}
	waitFor(t, "the first Tier-2 write-back", func() bool { return len(hs.store.tier2Written()) == 1 })
	entryA := hs.store.tier2Written()[0]
	if entryA.Lane != string(reuse.LanePolicy) {
		t.Fatalf("request 1 wrote lane %q, want POLICY: the fixture does not reach the POLICY lane", entryA.Lane)
	}

	// 2. Product B (the headphones) asks the same words, at the same vector: similarity 1.0 to A's entry.
	// A's entry is in the POLICY lane. Before ADR-024 its namespace was the policy document alone, B's
	// request searched it, found A's entry and reused it: the answer written for A went to B.
	c2 := hs.askNear(t, question, 1, 1.0, headphones)
	if got := c2.response(t).text("cache"); got != "MISS" {
		t.Fatalf("request 2: cache = %q, want MISS: product B's request reached the entry written for product A (namespace %q)",
			got, entryA.Namespace)
	}
	c2.response(t).null("similarity") // nothing was judged: A's entry was never a candidate
	waitFor(t, "the second Tier-2 write-back", func() bool { return len(hs.store.tier2Written()) == 2 })
	entryB := hs.store.tier2Written()[1]

	// 3. Product A asks a paraphrase, at a similarity above tau. It is still reused: the change must not
	// cost same-product reuse. This is also what shows the write path and the search path agree.
	c3 := hs.askNear(t, paraphrase, 1, hitCos, kettle)
	if got := c3.response(t).text("cache"); got != "TIER2_HIT" {
		t.Fatalf("request 3: cache = %q, want TIER2_HIT: product A's own paraphrase did not reach A's entry in %q",
			got, entryA.Namespace)
	}
	waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
	waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 3 })
	hs.records(t)

	// What the store was asked, and what it was holding.
	got := hs.store.namespacesSearched()
	if len(got) != 3 {
		t.Fatalf("namespaces searched = %q, want one search per request (3)", got)
	}
	if got[0] != entryA.Namespace || got[2] != entryA.Namespace {
		t.Errorf("A's requests searched %q and %q, but A's entry was written in %q: the write path and the search path disagree",
			got[0], got[2], entryA.Namespace)
	}
	if got[1] != entryB.Namespace {
		t.Errorf("B's request searched %q, but B's entry was written in %q: the write path and the search path disagree",
			got[1], entryB.Namespace)
	}
	if entryA.Namespace == entryB.Namespace {
		t.Errorf("A's and B's POLICY entries share the namespace %q", entryA.Namespace)
	}
	if want := reuse.Namespace(reuse.LanePolicy, policyGrounding(), headphones.id); got[1] != want {
		t.Errorf("B's request searched %q, want %q", got[1], want)
	}

	// The records: B's was a MISS with no candidate (nothing judged), A's paraphrase served A's entry.
	rec2 := c2.record(t)
	rec2.str("cache", "MISS")
	rec2.null("similarity")
	rec2.absent("candidate_entry_id")
	rec3 := c3.record(t)
	rec3.str("cache", "TIER2_HIT")
	rec3.str("entry_id", entryA.EntryID)
}
