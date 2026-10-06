package httpapi

// Tests for F-H (task 2026-10-06-fh-generate-ms-on-abandoned): t_generate_ms is non-null if and only
// if THIS request's own Answer call was attempted, whether or not it succeeded. Until the fix the
// closure computed it and Ask dropped it on every outcome but a served MISS.
//
// STALE COMMENTS this file supersedes, left in place because their tests are immutable (F-A's
// precedent, abandon_test.go:13-15): ask_test.go:404 and abandon_test.go:64-65 say the field "is not
// asserted: it is dropped although the generation ran (F-H)". It is asserted here.
//
// Two sensitivities, declared so that a later change that flips one is read as a decision and not a
// regression:
//   - T3 is ADMISSION-SENSITIVE. It pins that Acquire's fast path ignores the context
//     (admission/pool.go), so a client that already left still reaches Answer. An Acquire that checked
//     the context would make that request null.
//   - T5 is F-D-SENSITIVE. It asserts a follower of an upstream-failed leader is null. An F-D fix that
//     re-elects followers on an upstream failure would legitimately make it non-null.
//
// No test here PINS a null t_permit_wait_ms. It is null on every fast-path request and after a queued-
// then-left request, both wrong under §H and both recorded findings; pinning either would turn the
// later fix into an edit of an immutable test. T6 reads it only as a precondition (a queued request
// that is SERVED carries a value of at least `held`), which survives that fix. Every assertion on the value is a LOWER bound: an upper
// bound would make a test timing-flaky.

import (
	"context"
	"math"
	"testing"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/hung/thesis/gateway/internal/cache"
)

// held is how long a test makes Answer take before it fails or is cancelled. It is a floor that makes
// the lower bound mean something, not a measurement.
const held = 25 * time.Millisecond

// genMS reads t_generate_ms from a call's record and fails if it is null.
func genMS(t *testing.T, c *call) float64 {
	t.Helper()
	v, ok := c.rec["t_generate_ms"].(float64)
	if !ok {
		t.Fatalf("t_generate_ms = %v, want a number: this request's own Answer was attempted", c.rec["t_generate_ms"])
	}
	return v
}

// failAfter makes every later Answer call wait for the given channel or its own context, then fail
// the way an upstream does.
func failAfter(hs *harness, release <-chan struct{}) {
	hs.rag.onAnswer(func(ctx context.Context) error {
		select {
		case <-release:
			return status.Error(codes.Internal, "the model runner crashed")
		case <-ctx.Done():
			return ctx.Err()
		}
	})
}

// T1. A generation that failed took time, and the record says how long.
func TestAFailedGenerationRecordsHowLongItTook(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	hs.embedFresh(q)
	hs.rag.onAnswer(func(ctx context.Context) error {
		select {
		case <-time.After(held):
			return status.Error(codes.Internal, "the model runner crashed")
		case <-ctx.Done():
			return ctx.Err()
		}
	})

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	c.record(t).str("cache", "GENERATION_FAILED")
	if got, floor := genMS(t, c), float64(held.Milliseconds()); got < floor {
		t.Errorf("t_generate_ms = %v, want at least the %v the failing Answer was held", got, floor)
	}
}

// T2. The client leaves while Answer is in flight. The value is censored (rag.server keeps generating,
// F-L), but it is at least how long this request's own Answer ran before the cancel reached it.
func TestClientLeavingDuringAnswerRecordsHowLongItWasHeld(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	hs.embedFresh(q)
	g := hs.holdAnswers()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	c := hs.start(askReq{question: q, productID: kettle.id, ctx: ctx})
	// The fake server appends the call at the top of its handler, which cannot run before the
	// gateway's genStart, so the time from here is a true lower bound on the span.
	waitFor(t, "Answer to start", func() bool { return len(hs.rag.answerCalls()) == 1 })
	time.Sleep(held)
	cancel()
	c.wait(t)
	g.open()
	hs.records(t)

	c.record(t).str("cache", "ABANDONED")
	if got, floor := genMS(t, c), float64(held.Milliseconds()); got < floor {
		t.Errorf("t_generate_ms = %v, want at least the %v Answer was held before the client left", got, floor)
	}
}

// T3. ADMISSION-SENSITIVE. The client left after Tier 1 and a permit was free, so Acquire's fast path
// (which ignores the context) admitted it and Answer was called with a dead context: the server saw
// nothing, and the field is non-null all the same. It asserts nothing about the value's size, and it
// logs it so `go test -race -count=N -v` shows how long the never-sent tail really is, which a
// threshold for "the RPC never left" must be checked against before anyone uses one.
func TestClientLeftBeforeTheRPCStillRecordsAnAttempt(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	hs.embedFresh(q)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	hs.h.Cache = &leavingStore{fakeStore: hs.store, afterGet: q, leave: cancel}

	c := hs.ask(t, askReq{question: q, productID: kettle.id, ctx: ctx})
	hs.records(t)

	c.record(t).str("cache", "ABANDONED")
	if n := len(hs.rag.answerCalls()); n != 0 {
		t.Fatalf("the server saw %d Answer call(s), want 0: this test is about an RPC that never left", n)
	}
	t.Logf("never-sent t_generate_ms = %.3f ms", genMS(t, c))
}

// T4. A request that left while queued never got a permit, so its own Answer was never attempted. A
// pin, against copying a stale value into the case. It asserts only t_generate_ms.
func TestClientLeavingWhileQueuedRecordsNoAttempt(t *testing.T) {
	hs := newHarness(t, 1, 1)
	const qa, qb = "Is the Aurora kettle cordless?", "Is the Aurora kettle dishwasher safe?"
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
	hs.records(t)

	rec := b.record(t)
	rec.str("cache", "ABANDONED")
	rec.null("t_generate_ms")
}

// T5. F-D-SENSITIVE. A coalesced follower never runs the closure, so its own Answer was never
// attempted and its value is null, while the leader that did attempt it carries one. The follower is
// told apart by distinct raw text that normalises to the same key (a failure record carries no
// `coalesced`). It must NOT assert the follower's cache, status, body or the absence of `coalesced`:
// that is F-D's and the other findings' territory, and pinning it would pin a defect.
//
// The leader fails with an upstream status and a live client. A cancellation would be F-D's case, and
// an F-D fix that re-elects the follower would legitimately make the follower's value non-null. The
// follower is waited for before the leader fails, so that a follower that failed to coalesce (which
// would be SHED, also null) cannot make this pass for the wrong reason.
func TestAFailedLeaderRecordsAnAttemptButItsFollowerDoesNot(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const qLeader, qFollower = "Is the Aurora kettle cordless?", "is the aurora kettle cordless"
	key := cache.Key(cache.Normalize(qLeader), kettle.id)
	if other := cache.Key(cache.Normalize(qFollower), kettle.id); other != key {
		t.Fatalf("fixture: %q and %q must share a Tier-1 key", qLeader, qFollower)
	}
	hs.embedFresh(qLeader, qFollower)
	g := hs.holdAnswers() // registers the gate with the harness, so cleanup always releases it
	failAfter(hs, g.ch)

	leader := hs.start(askReq{question: qLeader, productID: kettle.id})
	waitFor(t, "the leader's Answer to start", func() bool { return len(hs.rag.answerCalls()) == 1 })
	follower := hs.start(askReq{question: qFollower, productID: kettle.id})
	waitFor(t, "the follower to wait on the leader", func() bool { return hs.h.Generations.Waiters(key) == 1 })
	time.Sleep(held)
	g.open()
	leader.wait(t)
	follower.wait(t)
	hs.records(t)

	if n := len(hs.rag.answerCalls()); n != 1 {
		t.Fatalf("Answer was called %d times, want 1: the follower did not coalesce", n)
	}
	leader.record(t).str("cache", "GENERATION_FAILED")
	if got, floor := genMS(t, leader), float64(held.Milliseconds()); got < floor {
		t.Errorf("the leader's t_generate_ms = %v, want at least the %v its Answer was held", got, floor)
	}
	follower.record(t).null("t_generate_ms")
}

// T6. The spans nest: waiting for a permit, generating, and the whole request are disjoint and
// contained in one another, so permit wait + generate can never exceed the total. It is an inequality
// on integer microseconds, so it cannot flake high. It fails if the generation span starts at the
// beginning of Ask (so a request that waited is charged for the wait twice) or above Acquire (so the
// wait is charged to generation, which would also inflate every MISS and bias mu_gen).
//
// B queues behind a gated A for at least `held`, then its Answer fails. The hook is switched after A's
// call has captured its own, so A stays a MISS and B ends GENERATION_FAILED.
//
// B's t_permit_wait_ms is read only as a fixture precondition: a queued request that is SERVED carries
// it, so a null here means B did not queue. (A request that queued and then LEFT carries null: a
// recorded finding that no test here pins.)
func TestTheSpansNest(t *testing.T) {
	hs := newHarness(t, 1, 1)
	const qa, qb = "Is the Aurora kettle cordless?", "Is the Aurora kettle dishwasher safe?"
	hs.embedFresh(qa, qb)
	g := hs.holdAnswers()

	a := hs.start(askReq{question: qa, productID: kettle.id})
	waitFor(t, "A's Answer to start (and capture its hook)", func() bool { return len(hs.rag.answerCalls()) == 1 })
	b := hs.start(askReq{question: qb, productID: kettle.id})
	waitFor(t, "B to queue", func() bool { return hs.h.Admission.Queued() == 1 })
	time.Sleep(held)
	release := make(chan struct{})
	close(release)
	failAfter(hs, release) // B's Answer reads this hook; A's call already holds the old one
	g.open()
	a.wait(t)
	b.wait(t)
	hs.records(t)

	a.record(t).str("cache", "MISS")
	b.record(t).str("cache", "GENERATION_FAILED")

	us := func(key string) int64 {
		v, ok := b.rec[key].(float64)
		if !ok {
			t.Fatalf("B's %s = %v, want a number", key, b.rec[key])
		}
		return int64(math.Round(v * 1000))
	}
	wait, gen, total := us("t_permit_wait_ms"), us("t_generate_ms"), us("t_total_ms")
	if wait < held.Microseconds() {
		t.Fatalf("B waited %d µs for its permit, want at least %d: B did not queue behind A", wait, held.Microseconds())
	}
	if wait+gen > total {
		t.Errorf("permit wait (%d µs) + generate (%d µs) = %d µs exceeds the request's total (%d µs): the spans do not nest",
			wait, gen, wait+gen, total)
	}
}

// slowPutStore holds the Tier-1 write-back for a fixed time, so the write-back is a known slice of a
// MISS's total that the generation span must NOT include.
type slowPutStore struct {
	*fakeStore
	hold time.Duration
}

var _ cacheStore = (*slowPutStore)(nil)

func (s *slowPutStore) Put(ctx context.Context, query, productID string, e cache.Entry) error {
	time.Sleep(s.hold)
	return s.fakeStore.Put(ctx, query, productID, e)
}

// T7. A MISS's t_generate_ms is the time Answer took, BEFORE write-back (interfaces.md §H v0.12). The
// permit is held through write-back, so a span that ran to the end of the closure would inflate every
// MISS by the cache's round trips and silently inflate mu_gen. Write-back is held 100 ms; the request's
// total exceeds the generation's span by at least that. A lower bound on the difference, so it cannot
// flake on correct code.
func TestAMissGenerationTimeExcludesItsWriteBack(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	hs.embedFresh(q)
	const writeBack = 100 * time.Millisecond
	hs.h.Cache = &slowPutStore{fakeStore: hs.store, hold: writeBack}

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	c.record(t).str("cache", "MISS")
	total, ok := c.rec["t_total_ms"].(float64)
	if !ok {
		t.Fatalf("t_total_ms = %v, want a number", c.rec["t_total_ms"])
	}
	// 1 ms of slack for the µs truncation of two floats; the real gap is the write-back's 100 ms.
	if diff, floor := total-genMS(t, c), float64(writeBack.Milliseconds())-1; diff < floor {
		t.Errorf("t_total_ms - t_generate_ms = %v, want at least %v: the generation span includes write-back", diff, floor)
	}
}

// T8. A coalesced MISS follower never ran the closure, so its own Answer was never attempted and its
// t_generate_ms is null, while the leader's is not. The v0.12 selection rule
// (`cache == "MISS" ∧ t_generate_ms != null`) selects exactly the leaders only because of this. Without
// a test, a later change that copies the leader's span to followers on the success path would pass
// everything and silently double-count mu_gen and permit occupancy.
func TestACoalescedMissFollowerCarriesNoGenerationTime(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	key := cache.Key(cache.Normalize(q), kettle.id)
	hs.embedFresh(q)
	g := hs.holdAnswers()

	first := hs.start(askReq{question: q, productID: kettle.id})
	waitFor(t, "the leader's Answer to start", func() bool { return len(hs.rag.answerCalls()) == 1 })
	second := hs.start(askReq{question: q, productID: kettle.id})
	waitFor(t, "the follower to wait on the leader", func() bool { return hs.h.Generations.Waiters(key) == 1 })
	g.open()
	first.wait(t)
	second.wait(t)
	hs.records(t)

	// On a served MISS the extension field `coalesced` is present on a follower and absent on a leader.
	var leader, follower *call
	for _, c := range []*call{first, second} {
		c.record(t).str("cache", "MISS")
		if co, _ := c.rec["coalesced"].(bool); co {
			follower = c
		} else {
			leader = c
		}
	}
	if leader == nil || follower == nil || leader == follower {
		t.Fatalf("expected one leader and one coalesced follower, got leader=%v follower=%v", leader != nil, follower != nil)
	}
	genMS(t, leader) // non-null
	follower.record(t).null("t_generate_ms")
}
