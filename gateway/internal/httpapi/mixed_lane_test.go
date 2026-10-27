package httpapi

import (
	"context"
	"errors"
	"net"
	"reflect"
	"testing"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/ragclient"
	"github.com/hung/thesis/gateway/internal/ragpb"
	"github.com/hung/thesis/gateway/internal/reuse"
)

// Item 4.5 (docs/work/2026-10-27-mixed-arm-field/): mixed_lane joins interfaces.md H at v0.16, a required
// key on EVERY record, "on" or "off" (ADR-016). The handler writes reuse.LaneBand.Arm() into it, from the
// same h.LaneBand that Classify reads. Two things must hold, and each has a test here:
//
//   - every exit of Ask that writes a record carries the key (TestMixedLaneKeyOnEveryExit), so a Tier-1 or
//     SHED record cannot read as an unknown arm;
//   - the label and the behaviour agree (TestMixedLaneLabelMatchesRule), so a record cannot say off while the
//     MIXED lane ran.
//
// This file is new on purpose: the existing httpapi tests are not edited. The harness is harness_test.go's.

// The two pinned bands of ADR-016, by the arm each one is.
var mixedLaneArms = []struct {
	arm  string
	band reuse.LaneBand
}{
	{"off", reuse.LaneBand{Lo: reuse.PinnedLo, Hi: reuse.PinnedLo}},
	{"on", reuse.LaneBand{Lo: reuse.PinnedLo, Hi: reuse.PinnedHiOn}},
}

// Every exit of Ask that writes a record, once per band. The table is a copy of
// TestSupportGateKeyOnEveryExit's (support_gate_test.go), with the loop over the band instead of the gate.
// The 405 and 400 exits write no record at all (they return before the deferred emit is registered).
func TestMixedLaneKeyOnEveryExit(t *testing.T) {
	const qa, qb = "Is the Aurora kettle cordless?", "Does the Aurora kettle whistle?"
	for _, c := range []struct {
		name           string
		permits, queue int
		wantCache      string
		run            func(t *testing.T, hs *harness) *call
	}{
		{"Tier-1 lookup error", 1, 0, "", func(t *testing.T, hs *harness) *call {
			hs.embedFresh(qa)
			hs.store.fail("Get", errors.New("redis: connection refused"))
			return hs.ask(t, askReq{question: qa, productID: kettle.id})
		}},
		{"TIER1_HIT", 1, 0, "TIER1_HIT", func(t *testing.T, hs *harness) *call {
			hs.store.seedTier1(qa, kettle.id, cache.Entry{
				Answer: kettle.answer, SourceChunkIDs: kettle.answerSources(), ModelUsed: testModel, EntryID: cache.NewEntryID(),
			})
			return hs.ask(t, askReq{question: qa, productID: kettle.id})
		}},
		{"TIER2_HIT", 1, 0, "TIER2_HIT", func(t *testing.T, hs *harness) *call {
			hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
			c := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
			waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
			waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 1 })
			return c
		}},
		{"MISS", 1, 0, "MISS", func(t *testing.T, hs *harness) *call {
			hs.embedFresh(qa)
			return hs.ask(t, askReq{question: qa, productID: kettle.id})
		}},
		{"SHED", 1, 0, "SHED", func(t *testing.T, hs *harness) *call {
			hs.embedFresh(qa, qb)
			g := hs.holdAnswers()
			a := hs.start(askReq{question: qa, productID: kettle.id})
			waitFor(t, "A to hold the permit", func() bool { return hs.h.Admission.InFlight() == 1 })
			b := hs.ask(t, askReq{question: qb, productID: kettle.id})
			g.open()
			a.wait(t)
			return b
		}},
		{"ABANDONED", 1, 1, "ABANDONED", func(t *testing.T, hs *harness) *call {
			hs.embedFresh(qa, qb)
			g := hs.holdAnswers()
			a := hs.start(askReq{question: qa, productID: kettle.id})
			waitFor(t, "A to hold the permit", func() bool { return hs.h.Admission.InFlight() == 1 })
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			b := hs.start(askReq{question: qb, productID: kettle.id, ctx: ctx})
			waitFor(t, "B to queue", func() bool { return hs.h.Admission.Queued() == 1 })
			cancel()
			b.wait(t)
			g.open()
			a.wait(t)
			return b
		}},
		{"GENERATION_FAILED", 1, 0, "GENERATION_FAILED", func(t *testing.T, hs *harness) *call {
			hs.embedFresh(qa)
			hs.rag.onAnswer(func(context.Context) error { return status.Error(codes.Internal, "the model runner crashed") })
			return hs.ask(t, askReq{question: qa, productID: kettle.id})
		}},
	} {
		for _, a := range mixedLaneArms {
			t.Run(c.name+"/"+a.arm, func(t *testing.T) {
				hs := newHarness(t, c.permits, c.queue)
				hs.h.LaneBand = a.band // before the first Ask, so no request sees the default band
				call := c.run(t, hs)
				hs.records(t)

				rec := call.record(t)
				rec.str("cache", c.wantCache) // the exit this case is meant to reach
				rec.str("mixed_lane", a.arm)
			})
		}
	}
}

// --- label and behaviour agree -----------------------------------------------------------------

// mixedRAG is a RAG service whose grounding is MIXED: one policy chunk in three. harness_test.go's fakeRAG
// returns product chunks only, and it is not edited, so this file brings its own. It is served behind the
// real ragclient, as fakeRAG is.
type mixedRAG struct {
	ragpb.UnimplementedRagServiceServer
}

// mixedGrounding is product, policy, product: a policy fraction of 1/3, which is inside [0.20, 0.60).
func mixedGrounding() []string {
	return []string{"product-kettle-01#chunk-0", "policy-returns-01#chunk-0", "product-kettle-01#chunk-1"}
}

func (mixedRAG) Retrieve(_ context.Context, req *ragpb.RetrieveRequest) (*ragpb.RetrieveResponse, error) {
	if req.GetTopK() != 0 {
		return nil, status.Errorf(codes.InvalidArgument, "Retrieve sent top_k=%d; the gateway must send 0", req.GetTopK())
	}
	return &ragpb.RetrieveResponse{
		ChunkIds:     mixedGrounding(),
		Scores:       []float32{0.9, 0.8, 0.7},
		DatasetEpoch: testEpoch,
		Texts: []string{
			kettle.texts[0],
			"Unopened items may be returned within the return window.",
			kettle.texts[1],
		},
	}, nil
}

func (mixedRAG) Answer(req *ragpb.AnswerRequest, stream grpc.ServerStreamingServer[ragpb.AnswerChunk]) error {
	if req.GetTopK() != 0 {
		return status.Errorf(codes.InvalidArgument, "Answer sent top_k=%d; the gateway must send 0", req.GetTopK())
	}
	return stream.Send(&ragpb.AnswerChunk{
		Text:           kettle.answer,
		Done:           true,
		SourceChunkIds: mixedGrounding(),
		ModelUsed:      testModel,
		DatasetEpoch:   testEpoch,
	})
}

// useMixedRAG points the harness's handler at a mixedRAG server and cleans it up. The harness's own
// fakeRAG stays in place and unused. Cleanups run last in, first out, so this one runs before the
// harness's, when every Ask has already returned.
func (hs *harness) useMixedRAG(t *testing.T) {
	t.Helper()
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	srv := grpc.NewServer()
	ragpb.RegisterRagServiceServer(srv, mixedRAG{})
	go func() { _ = srv.Serve(lis) }()

	client, err := ragclient.New(lis.Addr().String())
	if err != nil {
		srv.Stop()
		t.Fatalf("ragclient: %v", err)
	}
	hs.h.RAG = client
	t.Cleanup(func() {
		_ = client.Close()
		srv.Stop()
	})
}

// One request whose grounding is mixed, asked under each band. Two Tier-2 entries are seeded, both at the
// query's vector and both clearing tau: a MIXED entry in the pair namespace and a POLICY entry in the policy
// namespace. Which one the request can reach is the lane rule, and which one it reached is read from two
// places that do not share a source with the label: the namespace the search was given (the fake store's
// own log) and reuse_rule (the record). The label, mixed_lane, must then name the same arm.
func TestMixedLaneLabelMatchesRule(t *testing.T) {
	const (
		mixedNS  = "product-kettle-01|policy-returns-01"
		policyNS = "policy-returns-01"
		question = "Can I return the Aurora kettle, and what is its body made of?"
	)
	for _, c := range []struct {
		arm       string
		band      reuse.LaneBand
		wantRule  string
		wantNS    string
		wantEntry func(mixed, policy cache.Tier2Entry) cache.Tier2Entry
	}{
		{"on", reuse.LaneBand{Lo: reuse.PinnedLo, Hi: reuse.PinnedHiOn}, "composite", mixedNS,
			func(mixed, _ cache.Tier2Entry) cache.Tier2Entry { return mixed }},
		{"off", reuse.LaneBand{Lo: reuse.PinnedLo, Hi: reuse.PinnedLo}, "namespace", policyNS,
			func(_, policy cache.Tier2Entry) cache.Tier2Entry { return policy }},
	} {
		t.Run(c.arm, func(t *testing.T) {
			hs := newHarness(t, 1, 0)
			hs.useMixedRAG(t)

			seed := func(lane reuse.Lane, ns, seedQuestion string) cache.Tier2Entry {
				e := cache.Tier2Entry{
					EntryID:        cache.NewEntryID(),
					QueryText:      seedQuestion,
					Answer:         kettle.answer,
					SourceChunkIDs: mixedGrounding(),
					T1Key:          cache.Key(cache.Normalize(seedQuestion), kettle.id),
					DatasetEpoch:   testEpoch,
					Namespace:      ns,
					Lane:           string(lane),
				}
				hs.store.seedTier2(e, float32s(basis(1)))
				return e
			}
			mixed := seed(reuse.LaneMixed, mixedNS, "May I return the Aurora kettle, and what is its body made of?")
			policy := seed(reuse.LanePolicy, policyNS, "How do I return an Aurora kettle, and what is it made of?")

			hs.h.LaneBand = c.band
			call := hs.askNear(t, question, 1, hitCos, kettle)
			if got := call.response(t).text("cache"); got != "TIER2_HIT" {
				t.Fatalf("cache = %q, want TIER2_HIT: the request did not reach the entry in %q", got, c.wantNS)
			}
			waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
			waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 1 })
			hs.records(t)

			rec := call.record(t)
			rec.str("cache", "TIER2_HIT")
			rec.str("mixed_lane", c.arm)
			rec.str("reuse_rule", c.wantRule)
			rec.str("entry_id", c.wantEntry(mixed, policy).EntryID) // the entry in the namespace the band reaches
			if got := hs.store.namespacesSearched(); !reflect.DeepEqual(got, []string{c.wantNS}) {
				t.Errorf("namespaces searched = %q, want %q", got, []string{c.wantNS})
			}
		})
	}
}
