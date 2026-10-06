package httpapi

// Tests for the outcome label of a client that leaves while its request is being served (finding
// F-A; super-plan.md item 1.2's follow-up; docs/work/2026-10-05-fa-abandonment-classification/,
// design.md §5 T1-T7). The rule they pin is D1's precedence: a shed first, then "this request's own
// client has gone" is ABANDONED, then GENERATION_FAILED; a generation that completed is a MISS
// whether or not the client has since left.
//
// ⚠️ Under a load generator an ABANDONED record is not client behaviour to exclude: a k6 client
// leaves only on its own timeout, so it is a request that went unanswered for that long, a censored
// latency observation counted against S2 (spec.md).
//
// ask_test.go:369-370 predates this fix and now reads as stale ("a cancellation that reaches a gRPC
// call is logged GENERATION_FAILED today"). It is left as it was, as 1.3 left its own stale
// comments, so that `git diff` on ask_test.go stays an audit.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/hung/thesis/gateway/internal/cache"
)

// leavingStore makes one request's client leave at a chosen point, which the harness cannot do by
// injecting a cancelled context: fakeStore ignores contexts, so a context that is dead from the
// start would test a path production does not have (real Redis rejects a dead context at Tier 1,
// and that request ends as F-B). It keys on the question text, so no other request is touched, and
// it is assigned to hs.h.Cache before any request starts.
type leavingStore struct {
	*fakeStore
	afterGet string             // the question whose client leaves right after its Tier-1 miss
	afterPut string             // the question whose client leaves as its write-back begins
	leave    context.CancelFunc // cancels that request's context
}

var _ cacheStore = (*leavingStore)(nil)

func (s *leavingStore) Get(ctx context.Context, query, productID string) (*cache.Entry, bool, error) {
	e, hit, err := s.fakeStore.Get(ctx, query, productID)
	if query == s.afterGet {
		s.leave()
	}
	return e, hit, err
}

// Put is the first write-back, inside the generation closure and after Answer has succeeded, so a
// cancel here leaves err == nil and ctx.Err() != nil together at the outcome switch.
func (s *leavingStore) Put(ctx context.Context, query, productID string, e cache.Entry) error {
	if query == s.afterPut {
		s.leave()
	}
	return s.fakeStore.Put(ctx, query, productID, e)
}

// T1. The client leaves while Answer is in flight. grpc-go reports the cancelled call as a
// *status.Error (code Canceled), which errors.Is(err, context.Canceled) does not match, so this was
// GENERATION_FAILED and a 502 written to a dead connection. t_generate_ms is not asserted: it is
// dropped on this path today (F-H).
func TestClientLeavingDuringAnswerIsAbandoned(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	hs.embedFresh(q)
	g := hs.holdAnswers()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	c := hs.start(askReq{question: q, productID: kettle.id, ctx: ctx})
	waitFor(t, "Answer to start", func() bool { return len(hs.rag.answerCalls()) == 1 })
	cancel()
	c.wait(t)
	g.open()
	hs.records(t)

	if !c.w.wroteNothing() {
		t.Errorf("a client that left was written to: status %d, header %v, body %q",
			c.w.Code, c.w.Header(), c.w.Body)
	}
	rec := c.record(t)
	rec.str("cache", "ABANDONED") // an extension to §H's cache enum (types.go)
	rec.boolean("shed", false)
	waitFor(t, "the permit to be released", func() bool { return hs.h.Admission.InFlight() == 0 })
}

// T2. The client leaves after Tier 1, during embed or retrieve. Both fail on the dead context and
// degrade, the miss path takes the free permit on Acquire's fast path, and Answer fails on the
// client side.
//
// The server never sees that call, which is what keeps this case free of an orphaned generation
// (F-L). It holds because grpc-go checks the stream's context before picking a transport
// (v1.83.0, stream.go newAttemptLocked), so an Answer on a dead context never sends its headers.
// If a grpc upgrade breaks this assertion, abandonment before Answer now creates orphans: re-scope
// F-L. Do not weaken the assertion.
func TestClientLeavingAfterTier1IsAbandoned(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	hs.embedFresh(q)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	hs.h.Cache = &leavingStore{fakeStore: hs.store, afterGet: q, leave: cancel}

	c := hs.ask(t, askReq{question: q, productID: kettle.id, ctx: ctx})
	hs.records(t)

	if !c.w.wroteNothing() {
		t.Errorf("a client that left was written to: status %d, body %q", c.w.Code, c.w.Body)
	}
	rec := c.record(t)
	rec.str("cache", "ABANDONED")
	rec.boolean("shed", false)
	if n := len(hs.rag.answerCalls()); n != 0 {
		t.Errorf("the server saw %d Answer call(s), want 0: a dead context never leaves the client", n)
	}
	if n := hs.h.Admission.InFlight(); n != 0 {
		t.Errorf("%d permit(s) still held", n)
	}
}

// T3. rag.server can raise CANCELED and DEADLINE_EXCEEDED itself with the client still connected: a
// restart, or its own timeout. Neither is the client leaving. The label comes from this request's
// own context, never from the status code, so these stay GENERATION_FAILED. A pin: it passes
// before the fix, and it is what stops the fix from being keyed on the code.
func TestUpstreamCancelOrDeadlineWithALiveClientIsGenerationFailed(t *testing.T) {
	for _, tc := range []struct {
		name string
		code codes.Code
	}{
		{"CANCELED", codes.Canceled},
		{"DEADLINE_EXCEEDED", codes.DeadlineExceeded},
	} {
		t.Run(tc.name, func(t *testing.T) {
			hs := newHarness(t, 1, 0)
			const q = "Is the Aurora kettle cordless?"
			hs.embedFresh(q)
			hs.rag.onAnswer(func(context.Context) error {
				return status.Error(tc.code, "raised by rag.server itself")
			})

			c := hs.ask(t, askReq{question: q, productID: kettle.id})
			hs.records(t)

			if c.w.Code != http.StatusBadGateway {
				t.Fatalf("status %d, want 502: %s", c.w.Code, c.w.Body)
			}
			c.record(t).str("cache", "GENERATION_FAILED")
		})
	}
}

// T4. A client that is gone and meets a full pool and queue is still SHED: a shed is decided
// before the context is read, and counted as graceful degradation. A pin, against placing the new
// case above ErrShed, which would move such requests out of S2's shed rate. B's client leaves after
// its Tier-1 miss, and B cannot coalesce onto A because the questions differ.
func TestClientLeavingAgainstAFullPoolIsStillShed(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const qa, qb = "Is the Aurora kettle cordless?", "Is the Aurora kettle dishwasher safe?"
	hs.embedFresh(qa, qb)
	g := hs.holdAnswers()
	ctxB, cancelB := context.WithCancel(context.Background())
	defer cancelB()
	hs.h.Cache = &leavingStore{fakeStore: hs.store, afterGet: qb, leave: cancelB}

	a := hs.start(askReq{question: qa, productID: kettle.id})
	waitFor(t, "A to hold the permit", func() bool { return hs.h.Admission.InFlight() == 1 })
	b := hs.start(askReq{question: qb, productID: kettle.id, ctx: ctxB})
	b.wait(t)
	g.open()
	a.wait(t)
	hs.records(t)

	if b.w.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d, want 503: %s", b.w.Code, b.w.Body)
	}
	rec := b.record(t)
	rec.str("cache", "SHED")
	rec.boolean("shed", true)
	a.record(t).str("cache", "MISS")
	if n := hs.h.Counters.Shed.Load(); n != 1 {
		t.Errorf("Counters.Shed = %d, want 1", n)
	}
}

// T5. D1's rule 4: a generation that completed is a MISS whether or not the client has since left.
// The generation happened and wrote back, so the cache's truth is the entry. The client leaves as
// its write-back begins, after Answer has succeeded. A pin, against dropping the err != nil guard.
func TestACompletedGenerationIsStillAMissWhenTheClientHasLeft(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	hs.embedFresh(q)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	hs.h.Cache = &leavingStore{fakeStore: hs.store, afterPut: q, leave: cancel}

	c := hs.ask(t, askReq{question: q, productID: kettle.id, ctx: ctx})
	hs.records(t)

	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
	}
	c.record(t).str("cache", "MISS")
}

// T6. DECLARED F-D-SENSITIVE. A follower with a live client, coalesced onto a leader whose client
// leaves during Answer, must not be made worse by the fix: it is not ABANDONED and something is
// written to it. It does NOT assert a 502 or GENERATION_FAILED, which would pin F-D's defect, and it
// holds for an F-D fix that answers the follower or retries it as the new leader. It asserts
// nothing about the leader (T1 owns that).
//
// The follower asks the same question in other raw text that normalises to the same key, so the two
// records can be told apart. The gate is opened after the leader returns, so a follower that is
// retried can finish. A pin, against classifying in the generation closure or in ragclient from the
// leader's context, which hands every follower the leader's cancellation.
func TestALiveFollowerIsNotAbandonedByItsLeadersDeparture(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const qLeader, qFollower = "Is the Aurora kettle cordless?", "is the aurora kettle cordless"
	key := cache.Key(cache.Normalize(qLeader), kettle.id)
	if other := cache.Key(cache.Normalize(qFollower), kettle.id); other != key {
		t.Fatalf("fixture: %q and %q must share a Tier-1 key", qLeader, qFollower)
	}
	hs.embedFresh(qLeader, qFollower)
	g := hs.holdAnswers()
	leaderCtx, leave := context.WithCancel(context.Background())
	defer leave()

	leader := hs.start(askReq{question: qLeader, productID: kettle.id, ctx: leaderCtx})
	waitFor(t, "Answer to start", func() bool { return len(hs.rag.answerCalls()) == 1 })
	follower := hs.start(askReq{question: qFollower, productID: kettle.id})
	waitFor(t, "the follower to wait on the leader", func() bool { return hs.h.Generations.Waiters(key) == 1 })
	leave()
	leader.wait(t)
	g.open()
	follower.wait(t)
	hs.records(t)

	if follower.w.wroteNothing() {
		t.Errorf("a follower with a live client was written nothing: that is an empty 200 on the wire")
	}
	if got := follower.record(t).get("cache"); got == "ABANDONED" {
		t.Errorf("a follower with a live client was recorded ABANDONED")
	}
}

// T7. A real disconnect. The harness injects a context through httptest, so it cannot show that
// closing a connection cancels r.Context() in this handler. This goes through a real server and a
// real client.
//
// Detection rests on the body reaching EOF, because net/http starts watching the connection only
// then. The body here is exactly as long as its Content-Length, which is the shape k6, curl,
// urllib and the UI send. A body with trailing bytes, or a chunked body whose end has not arrived,
// is not detected and runs to completion: a recorded limitation, not behaviour this test protects.
//
// The call does not go through hs.start, so hs.records cannot read it. The server is closed first,
// which drains the handler before the harness's cleanup closes the log.
func TestARealDisconnectIsRecordedAbandoned(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	hs.embedFresh(q)
	hs.holdAnswers()
	srv := httptest.NewServer(http.HandlerFunc(hs.h.Ask))
	defer srv.Close()

	body, err := json.Marshal(map[string]string{"question": q, "product_id": kettle.id})
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, srv.URL+"/ask", bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Thesis-Stratum", testStratum)

	done := make(chan struct{})
	go func() {
		defer close(done)
		if resp, err := http.DefaultClient.Do(req); err == nil {
			_ = resp.Body.Close()
		}
	}()
	waitFor(t, "Answer to start", func() bool { return len(hs.rag.answerCalls()) == 1 })
	cancel()
	<-done
	waitFor(t, "the handler to finish", func() bool { return hs.h.Counters.Requests.Load() == 1 })
	srv.Close()
	if err := hs.h.Eval.Close(); err != nil {
		t.Fatalf("closing the eval log: %v", err)
	}

	recs := readJSONL(t, hs.logPath)
	if len(recs) != 1 {
		t.Fatalf("%d eval records, want 1", len(recs))
	}
	if got := recs[0]["cache"]; got != "ABANDONED" {
		t.Errorf("cache = %v, want ABANDONED: a client that disconnected mid-request", got)
	}
}
