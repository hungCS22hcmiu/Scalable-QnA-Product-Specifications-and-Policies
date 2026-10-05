package httpapi

// Tests for every exit path of Ask (super-plan.md item 1.2; docs/work/2026-10-04-httpapi-tests/).
// Each asserts the HTTP response (interfaces.md §A) AND the evaluation record (§H). The harness is
// in harness_test.go, and every request also gets its checks: one record per Ask call, the run's
// identity, the stratum, and on a 200 the join and dedupe keys.
//
// The assertions here are IMMUTABLE (approvals.md, item 4): changed only after an RCA, with the
// author's confirmation. Two tests are declared 1.3-sensitive and may change under 1.3's own
// recorded decision; they say so.
//
// No test pins a known defect (spec.md, F-A to F-K). Where a finding makes a value wrong today,
// the value is left unasserted, and the comment names the finding.

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/hung/thesis/gateway/internal/cache"
)

// Path 4. A Tier-1 hit is a bare hash lookup: no embedding, no retrieval, no generation.
func TestTier1HitServesTheStoredAnswer(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "What is the Aurora kettle made of?"
	stored := cache.Entry{
		Answer:         kettle.answer,
		SourceChunkIDs: kettle.answerSources(),
		ModelUsed:      testModel,
		EntryID:        cache.NewEntryID(),
	}
	hs.store.seedTier1(q, kettle.id, stored)

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
	}
	resp := c.response(t)
	resp.str("cache", "TIER1_HIT")
	resp.str("answer", stored.Answer)
	resp.strs("sources", stored.SourceChunkIDs)
	resp.str("model_used", testModel)
	// §A: both render null on a Tier-1 hit, not omitted.
	resp.null("similarity")
	resp.null("source_overlap")

	rec := c.record(t)
	rec.str("cache", "TIER1_HIT")
	rec.str("entry_id", stored.EntryID)
	rec.strs("entry_sources", stored.SourceChunkIDs)
	// §H: null where the stage did not run.
	for _, k := range []string{"t_embed_ms", "t_search_ms", "t_overlap_ms", "t_permit_wait_ms", "t_generate_ms"} {
		rec.null(k)
	}

	if calls, _ := hs.embedder.counts(); calls != 0 {
		t.Errorf("the embedder was called %d time(s) on a Tier-1 hit", calls)
	}
	if n := len(hs.rag.retrieveCalls()) + len(hs.rag.answerCalls()); n != 0 {
		t.Errorf("the RAG service was called %d time(s) on a Tier-1 hit", n)
	}
}

// Path 6. A miss generates once, and writes BOTH tiers under one entry identity.
func TestMissGeneratesOnceAndWritesBothTiersUnderOneIdentity(t *testing.T) {
	hs := newHarness(t, 1, 0)
	// Mixed case and punctuation: Tier 2's t1_key must come from the NORMALIZED question.
	const q = "Does the Aurora Kettle switch itself OFF?"
	hs.embedFresh(q)

	miss := hs.ask(t, askReq{question: q, productID: kettle.id})
	again := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	if miss.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", miss.w.Code, miss.w.Body)
	}
	resp := miss.response(t)
	resp.str("cache", "MISS")
	resp.str("answer", kettle.answer)
	resp.strs("sources", kettle.answerSources())

	rec := miss.record(t)
	rec.str("cache", "MISS")
	rec.notNull("t_generate_ms")
	rec.strs("retrieved_chunk_ids", kettle.chunkIDs())
	rec.number("dataset_epoch_at_retrieval", float64(testEpoch))
	wantT1Key := cache.Key(cache.Normalize(q), kettle.id)
	rec.str("t1_key", wantT1Key)
	rec.strs("entry_sources", kettle.answerSources())
	entryID := rec.text("entry_id")

	// One retrieval: Answer was handed exactly what Retrieve returned.
	if n := len(hs.rag.retrieveCalls()); n != 1 {
		t.Errorf("Retrieve called %d times, want 1", n)
	}
	answers := hs.rag.answerCalls()
	if len(answers) != 1 {
		t.Fatalf("Answer called %d times, want 1", len(answers))
	}
	if !reflect.DeepEqual(answers[0].retrievedIDs, kettle.chunkIDs()) {
		t.Errorf("Answer received chunk IDs %q, want Retrieve's %q", answers[0].retrievedIDs, kettle.chunkIDs())
	}

	// Both tiers hold ANSWER's provenance, not Retrieve's (S7), under the record's entry_id.
	t1 := hs.store.tier1Written()
	if len(t1) != 1 {
		t.Fatalf("%d Tier-1 writes, want 1", len(t1))
	}
	if t1[0].key != wantT1Key {
		t.Errorf("Tier-1 written under %s, want %s", t1[0].key, wantT1Key)
	}
	if t1[0].entry.EntryID != entryID {
		t.Errorf("Tier-1 entry_id %s, want the record's %s", t1[0].entry.EntryID, entryID)
	}
	if !reflect.DeepEqual(t1[0].entry.SourceChunkIDs, kettle.answerSources()) {
		t.Errorf("Tier-1 sources %q, want Answer's %q", t1[0].entry.SourceChunkIDs, kettle.answerSources())
	}

	t2 := hs.store.tier2Written()
	if len(t2) != 1 {
		t.Fatalf("%d Tier-2 writes, want 1", len(t2))
	}
	e := t2[0]
	if e.EntryID != entryID {
		t.Errorf("Tier-2 entry_id %s, want the record's %s", e.EntryID, entryID)
	}
	// Invariant 2: without the right t1_key, a purge silently misses Tier 1.
	if e.T1Key != wantT1Key {
		t.Errorf("Tier-2 t1_key %s, want %s", e.T1Key, wantT1Key)
	}
	if !reflect.DeepEqual(e.SourceChunkIDs, kettle.answerSources()) {
		t.Errorf("Tier-2 sources %q, want Answer's %q", e.SourceChunkIDs, kettle.answerSources())
	}
	if e.DatasetEpoch != testEpoch {
		t.Errorf("Tier-2 dataset_epoch %d, want %d", e.DatasetEpoch, testEpoch)
	}
	if e.Namespace != kettle.id {
		t.Errorf("Tier-2 namespace %q, want %q", e.Namespace, kettle.id)
	}

	// The repeat is served from what the miss wrote, provenance included.
	againResp := again.response(t)
	againResp.str("cache", "TIER1_HIT")
	againResp.str("answer", kettle.answer)
	againResp.strs("sources", kettle.answerSources())
	againRec := again.record(t)
	againRec.str("entry_id", entryID)
	againRec.strs("entry_sources", kettle.answerSources())
}

// Paths 6 then 5. The partition a miss WRITES is the one a paraphrase is served from (S7).
func TestMissThenParaphraseIsATier2Hit(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle body made of steel?"
	const paraphrase = "Is the body of the Aurora kettle steel?"
	hs.embedder.learn(q, basis(1))
	hs.embedder.learn(paraphrase, toward(1, 2, hitCos))

	miss := hs.ask(t, askReq{question: q, productID: kettle.id})
	hit := hs.ask(t, askReq{question: paraphrase, productID: kettle.id})
	// The hit's detached writes must land before the test ends (U3).
	waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
	waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 2 })
	hs.records(t)

	miss.record(t).str("cache", "MISS")
	if hit.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", hit.w.Code, hit.w.Body)
	}
	resp := hit.response(t)
	resp.str("cache", "TIER2_HIT")
	resp.str("answer", kettle.answer)
	rec := hit.record(t)
	rec.str("cache", "TIER2_HIT")
	rec.str("entry_id", miss.record(t).text("entry_id"))
	rec.strs("entry_sources", kettle.answerSources())
	if n := len(hs.rag.answerCalls()); n != 1 {
		t.Errorf("Answer called %d times, want 1 (the miss only)", n)
	}
}

// Path 5. One seeded entry, so the global and in-namespace nearest are the same entry and F-G
// cannot arise (design.md §5).
func TestTier2HitInsideTheNamespaceAndPromotesToTier1(t *testing.T) {
	hs := newHarness(t, 1, 0)
	seeded := hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	const q = "Which material is the Aurora kettle body?"
	hs.embedder.learn(q, toward(1, 2, hitCos))

	hit := hs.ask(t, askReq{question: q, productID: kettle.id})
	waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
	waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 1 })
	again := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	if hit.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", hit.w.Code, hit.w.Body)
	}
	resp := hit.response(t)
	resp.str("cache", "TIER2_HIT")
	resp.str("answer", seeded.Answer)
	resp.strs("sources", seeded.SourceChunkIDs)
	// The measured values, not only their presence: these feed the tau/theta frontier and the
	// false hits by cause. §A: source_overlap is null only when the cascade did not run (N4). One
	// seeded entry, so it is the served entry's overlap and F-G cannot arise. The fixture puts the
	// entry's sources inside what retrieval returns, so containment is exactly 1.
	resp.near("similarity", hitCos, 1e-3)
	resp.number("source_overlap", 1)
	resp.str("lane", "SPEC")
	resp.str("namespace", kettle.id)

	rec := hit.record(t)
	rec.str("cache", "TIER2_HIT")
	rec.str("entry_id", seeded.EntryID)
	rec.boolean("entered_band", true)
	rec.near("similarity", hitCos, 1e-3)
	rec.number("source_overlap", 1)
	rec.strs("entry_sources", seeded.SourceChunkIDs)
	rec.strs("retrieved_chunk_ids", kettle.chunkIDs())
	rec.number("dataset_epoch_at_retrieval", float64(testEpoch))
	if n := len(hs.rag.answerCalls()); n != 0 {
		t.Errorf("Answer called %d times on a Tier-2 hit", n)
	}

	if b := hs.store.bumped(); b[0] != seeded.EntryID {
		t.Errorf("hit_count bumped for %s, want %s", b[0], seeded.EntryID)
	}
	p := hs.store.tier1Written()[0]
	if p.entry.EntryID != seeded.EntryID {
		t.Errorf("promoted under entry_id %s, want %s", p.entry.EntryID, seeded.EntryID)
	}
	if want := cache.Key(cache.Normalize(q), kettle.id); p.key != want {
		t.Errorf("promoted under %s, want %s", p.key, want)
	}
	if p.entry.Answer != seeded.Answer || !reflect.DeepEqual(p.entry.SourceChunkIDs, seeded.SourceChunkIDs) {
		t.Errorf("promoted %q with sources %q, want the entry's %q and %q",
			p.entry.Answer, p.entry.SourceChunkIDs, seeded.Answer, seeded.SourceChunkIDs)
	}
	againResp := again.response(t)
	againResp.str("cache", "TIER1_HIT")
	againResp.str("answer", seeded.Answer)
	againResp.strs("sources", seeded.SourceChunkIDs)
	againRec := again.record(t)
	againRec.str("entry_id", seeded.EntryID)
	againRec.strs("entry_sources", seeded.SourceChunkIDs)
}

// Path 6, refused on the namespace conjunct ALONE (S1). The entry is the fixture for a kettle
// question in every respect -- kettle's chunks, an answer taken from kettle's chunk 0 -- except
// that it was written under the headphones namespace. So once theta or the support gate joins the
// served decision, dropping the namespace term still fails this test. The entry carries
// kettle.otherAnswer, so serving it would show in the response.
//
// DECLARED 1.3-SENSITIVE (approvals.md, item 2). Today the refusal's similarity comes from the
// GLOBAL nearest. After 1.3 the scoped search finds nothing, so it may become null, which changes
// what §A's lookalike-trap demonstration shows. 1.3 may change this test only under its own
// recorded decision, and may not change its cache outcome or its status.
func TestTier2RefusesAnEntryFromAnotherNamespace(t *testing.T) {
	hs := newHarness(t, 1, 0)
	e := hitFixture(kettle, "What comes in the box with the Aurora kettle?")
	e.Namespace = headphones.id
	e.Answer = kettle.otherAnswer
	hs.store.seedTier2(e, float32s(basis(1)))
	const q = "What is included with the Aurora kettle?"
	hs.embedder.learn(q, toward(1, 2, hitCos))

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
	}
	resp := c.response(t)
	resp.str("cache", "MISS")
	resp.str("answer", kettle.answer)
	resp.null("similarity")

	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.boolean("entered_band", false)
	if n := len(hs.rag.answerCalls()); n != 1 {
		t.Errorf("Answer called %d times, want 1: a refusal must generate", n)
	}
}

// Path 6, refused on tau alone: the same namespace, at cosine tau - 0.10 (S1).
//
// DECLARED 1.3-SENSITIVE (approvals.md, item 2): it assumes the tau gate runs before the namespace
// decides, which is the unfiltered phase 1.3 removes. 1.3 may change this test only under its own
// recorded decision, and may not change its cache outcome or its status.
func TestBelowTauDoesNotEnterTheBand(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	const q = "Can the Aurora kettle boil milk?"
	hs.embedder.learn(q, toward(1, 2, belowTauCos))

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
	}
	resp := c.response(t)
	resp.str("cache", "MISS")
	resp.null("source_overlap")

	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.boolean("entered_band", false)
}

// Path 8. At pool(1,1), A holds the permit and C holds the one queue slot, so B is shed. B's
// permit_queue_depth is 1, which tells "set from Queued()" apart from "never set" (N3).
func TestShedWhenPermitAndQueueAreBothFull(t *testing.T) {
	hs := newHarness(t, 1, 1)
	const qa, qb, qc = "Is the Aurora kettle cordless?", "Is the Aurora kettle dishwasher safe?", "Does the Aurora kettle whistle?"
	hs.embedFresh(qa, qb, qc)
	g := hs.holdAnswers()

	a := hs.start(askReq{question: qa, productID: kettle.id})
	waitFor(t, "A to hold the permit", func() bool { return hs.h.Admission.InFlight() == 1 })
	c := hs.start(askReq{question: qc, productID: kettle.id})
	waitFor(t, "C to queue", func() bool { return hs.h.Admission.Queued() == 1 })
	b := hs.ask(t, askReq{question: qb, productID: kettle.id})
	g.open()
	a.wait(t)
	c.wait(t)
	hs.records(t)

	if b.w.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d, want 503: %s", b.w.Code, b.w.Body)
	}
	if got := b.w.Header().Get("Retry-After"); got != "2" {
		t.Errorf("Retry-After = %q, want \"2\"", got)
	}
	resp := b.response(t)
	resp.str("error", "busy")
	resp.str("reason", "generation_pool_saturated")
	resp.str("request_id", b.record(t).text("request_id"))

	rec := b.record(t)
	rec.str("cache", "SHED") // an extension to §H's cache enum (types.go)
	rec.boolean("shed", true)
	rec.number("permit_queue_depth", 1)
	rec.null("t_generate_ms")

	a.record(t).str("cache", "MISS")
	c.record(t).str("cache", "MISS")
	if n := hs.h.Counters.Shed.Load(); n != 1 {
		t.Errorf("Counters.Shed = %d, want 1", n)
	}
}

// Path 9. A client that leaves while QUEUED for the permit is ABANDONED, not shed. B asks a
// different question from A, so it cannot coalesce onto A (S3). B is joined before A is released,
// so the permit can never reach it.
//
// Only this case is tested. A cancellation that reaches a gRPC call is logged GENERATION_FAILED
// today (F-A), and a test of it would pin that defect.
func TestAbandonedWhileQueuedIsNotAShed(t *testing.T) {
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

	if !b.w.wroteNothing() {
		t.Errorf("an abandoned request wrote a response: status %d, header %v, body %q",
			b.w.Code, b.w.Header(), b.w.Body)
	}
	rec := b.record(t)
	rec.str("cache", "ABANDONED") // an extension to §H's cache enum (types.go)
	rec.boolean("shed", false)

	a.record(t).str("cache", "MISS")
	if n := hs.h.Counters.Shed.Load(); n != 0 {
		t.Errorf("Counters.Shed = %d, want 0: leaving is not being shed", n)
	}
}

// Path 10. A failed generation is answered 502, and is neither served nor cached.
// t_generate_ms is not asserted: today it is dropped although the generation ran (F-H).
func TestGenerationFailureIsNotServedOrCached(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	hs.embedFresh(q)
	hs.rag.onAnswer(func(context.Context) error {
		return status.Error(codes.Internal, "the model runner crashed")
	})

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	if c.w.Code != http.StatusBadGateway {
		t.Fatalf("status %d, want 502: %s", c.w.Code, c.w.Body)
	}
	rec := c.record(t)
	rec.str("cache", "GENERATION_FAILED") // an extension to §H's cache enum (types.go)
	rec.boolean("shed", false)
	if n := hs.store.callCount("Put") + hs.store.callCount("PutTier2"); n != 0 {
		t.Errorf("%d cache write(s) after a failed generation, want 0", n)
	}
}

// Paths 6 and 7. COALESCING WRAPS ADMISSION: four identical concurrent misses, at one permit and no
// queue, cost one permit and one generation, and none is shed. The leader's Answer is held until
// three followers are waiting on it (U5), so no timing decides the outcome.
func TestCoalescingWrapsAdmission(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	hs.embedFresh(q)
	g := hs.holdAnswers()
	key := cache.Key(cache.Normalize(q), kettle.id)

	calls := make([]*call, 4)
	for i := range calls {
		calls[i] = hs.start(askReq{question: q, productID: kettle.id})
	}
	waitFor(t, "three followers to wait on the leader", func() bool { return hs.h.Generations.Waiters(key) == 3 })
	g.open()
	hs.records(t)

	leaders, entryID := 0, ""
	for _, c := range calls {
		if c.w.Code != http.StatusOK {
			t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
		}
		resp := c.response(t)
		resp.str("cache", "MISS")
		resp.str("answer", kettle.answer)

		rec := c.record(t)
		rec.str("cache", "MISS")
		if id := rec.text("entry_id"); entryID == "" {
			entryID = id
		} else if id != entryID {
			t.Errorf("entry_ids %s and %s: requests that shared one generation must share its entry", entryID, id)
		}
		// `coalesced` is an extension to §H (telemetry.Record). The leader's is absent or false:
		// omitempty is a serialisation detail, not what is under test.
		if follower, _ := c.rec["coalesced"].(bool); !follower {
			leaders++
			rec.notNull("t_generate_ms") // a follower's is not asserted (N5)
		}
	}
	if leaders != 1 {
		t.Errorf("%d records without coalesced, want exactly 1 leader", leaders)
	}
	if n := len(hs.rag.answerCalls()); n != 1 {
		t.Errorf("Answer called %d times, want 1", n)
	}
	if n := hs.h.Counters.Shed.Load(); n != 0 {
		t.Errorf("Counters.Shed = %d, want 0: a follower must never take a permit", n)
	}
	if gen, co := hs.h.Counters.Generated.Load(), hs.h.Counters.Coalesced.Load(); gen != 1 || co != 3 {
		t.Errorf("Counters Generated=%d Coalesced=%d, want 1 and 3", gen, co)
	}
}

// Path 6. The same question about two products is two questions. At two permits, both Answers are
// held until both generations hold a permit (S8), so collapsing them onto one would fail by
// deadline rather than pass by luck.
func TestCoalescingNeverCrossesProducts(t *testing.T) {
	hs := newHarness(t, 2, 0)
	const q = "What comes in the box?"
	hs.embedFresh(q)
	g := hs.holdAnswers()

	k := hs.start(askReq{question: q, productID: kettle.id})
	e := hs.start(askReq{question: q, productID: headphones.id})
	waitFor(t, "two generations to hold a permit each", func() bool {
		return hs.h.Admission.InFlight() == 2 && len(hs.rag.answerCalls()) == 2
	})
	g.open()
	hs.records(t)

	for _, tc := range []struct {
		c *call
		p product
	}{{k, kettle}, {e, headphones}} {
		if tc.c.w.Code != http.StatusOK {
			t.Fatalf("%s: status %d, want 200: %s", tc.p.id, tc.c.w.Code, tc.c.w.Body)
		}
		resp := tc.c.response(t)
		resp.str("cache", "MISS")
		resp.str("answer", tc.p.answer)
		tc.c.record(t).notTrue("coalesced")
	}
	if a, b := k.record(t).text("entry_id"), e.record(t).text("entry_id"); a == b {
		t.Errorf("both products got entry_id %s", a)
	}
}

// The four degradations end in MISS, never in an error. Each seeds what would otherwise be a
// TIER2_HIT and proves its failure actually fired (S2), so none can pass vacuously.

func TestEmbedFailureDegradesToMiss(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	const q = "Which material is the Aurora kettle body?"
	hs.embedder.learn(q, toward(1, 2, hitCos))
	hs.embedder.failEverything()

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	if _, failures := hs.embedder.counts(); failures == 0 {
		t.Fatalf("the embedder never failed, so nothing degraded")
	}
	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
	}
	c.response(t).str("cache", "MISS")
	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.null("similarity")
	rec.boolean("entered_band", false)
	// No vector, so nothing for Tier 2. Tier 1 is still written.
	if n := len(hs.store.tier1Written()); n != 1 {
		t.Errorf("%d Tier-1 writes, want 1", n)
	}
	if n := hs.store.callCount("PutTier2"); n != 0 {
		t.Errorf("%d Tier-2 writes without a vector, want 0", n)
	}
}

// entered_band, source_overlap and similarity are not asserted: a Retrieve error makes them
// describe a refusal that never happened (F-E).
func TestRetrieveFailureDegradesToMiss(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	const q = "Which material is the Aurora kettle body?"
	hs.embedder.learn(q, toward(1, 2, hitCos))
	hs.rag.failRetrieve(status.Error(codes.Unavailable, "the corpus index is offline"))

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	if hs.rag.retrieveFailures() == 0 {
		t.Fatalf("Retrieve never failed, so nothing degraded")
	}
	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
	}
	c.response(t).str("cache", "MISS")
	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.null("retrieved_chunk_ids")
	rec.null("dataset_epoch_at_retrieval")
	answers := hs.rag.answerCalls()
	if len(answers) != 1 {
		t.Fatalf("Answer called %d times, want 1", len(answers))
	}
	if len(answers[0].retrievedIDs) != 0 {
		t.Errorf("Answer received chunk IDs %q after retrieval failed, want none", answers[0].retrievedIDs)
	}
}

// "both searches" fails every search method. "namespace-scoped search only" fails just the scoped
// search: it is the one search left after 1.3, and today it is the only way to reach the cascade's
// second error branch (S2), where serving the global nearest instead would be a false hit.
func TestTier2SearchFailureDegradesToMiss(t *testing.T) {
	for _, tc := range []struct {
		name    string
		failing []string
	}{
		{"both searches", []string{"NearestTier2", "NearestTier2InNamespace"}},
		{"namespace-scoped search only", []string{"NearestTier2InNamespace"}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			hs := newHarness(t, 1, 0)
			hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
			const q = "Which material is the Aurora kettle body?"
			hs.embedder.learn(q, toward(1, 2, hitCos))
			for _, m := range tc.failing {
				hs.store.fail(m, errors.New("redis: idx:cache unavailable"))
			}

			c := hs.ask(t, askReq{question: q, productID: kettle.id})
			hs.records(t)

			if hs.store.injectedCount() == 0 {
				t.Fatalf("no Tier-2 search failed, so nothing degraded")
			}
			if c.w.Code != http.StatusOK {
				t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
			}
			c.response(t).str("cache", "MISS")
			c.record(t).str("cache", "MISS")
		})
	}
}

// The generation succeeded, so a failed write-back must not cost the answer. Neither
// writeback_discarded nor entry_id is asserted: today a failed write-back leaves no trace in §H,
// and the record names an entry that was never stored (F-J). Its fix decides both.
func TestWritebackFailureStillServesTheAnswer(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	hs.embedFresh(q)
	writeDown := errors.New("redis: OOM command not allowed")
	hs.store.fail("Put", writeDown)
	hs.store.fail("PutTier2", writeDown)

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	if hs.store.injectedCount() == 0 {
		t.Fatalf("no write-back failed")
	}
	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
	}
	resp := c.response(t)
	resp.str("cache", "MISS")
	resp.str("answer", kettle.answer)
	c.record(t).str("cache", "MISS")
}

// Path 3. A failed Tier-1 lookup still emits exactly ONE record, which records() checks along
// with Counters.Requests. Neither the status nor the record's cache value is asserted: today the
// cache is "" (F-B), and both belong to that finding's fix.
func TestTier1LookupErrorStillEmitsOneRecord(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	hs.embedFresh(q) // in case a fix degrades to the cascade instead of failing
	hs.store.fail("Get", errors.New("redis: connection refused"))

	hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	if hs.store.injectedCount() == 0 {
		t.Fatalf("the Tier-1 lookup never failed")
	}
	if n := hs.h.Counters.Requests.Load(); n != 1 {
		t.Errorf("Counters.Requests = %d, want 1", n)
	}
}

// Paths 1 and 2. Malformed requests are refused before anything runs. Only the response is
// asserted: whether a malformed request counts as a request in §H is not this task's decision.
func TestRejectsBadMethodAndBody(t *testing.T) {
	hs := newHarness(t, 1, 0)
	for _, tc := range []struct {
		name, method, body string
		want               int
	}{
		{"GET", http.MethodGet, "", http.StatusMethodNotAllowed},
		{"empty question", http.MethodPost, `{"question": ""}`, http.StatusBadRequest},
		{"invalid JSON", http.MethodPost, `{"question": `, http.StatusBadRequest},
	} {
		t.Run(tc.name, func(t *testing.T) {
			w := httptest.NewRecorder()
			hs.h.Ask(w, httptest.NewRequest(tc.method, "/ask", strings.NewReader(tc.body)))
			if w.Code != tc.want {
				t.Errorf("status %d, want %d", w.Code, tc.want)
			}
		})
	}
}

// Path 6. An entry in ANOTHER namespace above tau must not lift an entry in THIS namespace that is
// below tau: tau judges the candidate actually served, not the global nearest (B-cross). The
// in-namespace entry satisfies every conjunct but tau and carries kettle.otherAnswer, so serving it
// would show. Only the outcome is asserted: similarity and entered_band describe the global nearest
// today, which 1.3 removes.
func TestAnotherNamespaceAboveTauDoesNotLiftAnEntryBelowTau(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "What is included with the Aurora kettle?"
	query := toward(1, 2, hitCos)
	hs.embedder.learn(q, query)
	hs.seedHit(headphones, "What comes in the box with the EarBuds Pop?", 1) // at hitCos to q
	below := hitFixture(kettle, "What does the Aurora kettle come with?")
	below.Answer = kettle.otherAnswer
	hs.store.seedTier2(below, float32s(around(query, 3, belowTauCos)))

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
	}
	resp := c.response(t)
	resp.str("cache", "MISS")
	resp.str("answer", kettle.answer)
	c.record(t).str("cache", "MISS")
	if n := len(hs.rag.answerCalls()); n != 1 {
		t.Errorf("Answer called %d times, want 1", n)
	}
}

// §H's dataset_epoch_at_retrieval is RETRIEVE's epoch, not Answer's. Everywhere else the two are
// equal (S6). Here Answer reports a later epoch, as it would if the corpus advanced during
// generation. Which epoch the Tier-2 record stores, and whether the write-back survives, is the
// Phase 4 epoch guard's to decide, so neither is asserted.
func TestRecordCarriesTheRetrievalEpoch(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "Is the Aurora kettle cordless?"
	hs.embedFresh(q)
	hs.rag.answerAtEpoch(testEpoch + 1)

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
	}
	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.number("dataset_epoch_at_retrieval", float64(testEpoch))
}

// The bounded cache (CLAUDE.md: capacity round(0.25 x K), enforced by the gateway alone). Every
// path that serves an entry touches THAT entry for LRU, and every miss trims to the configured
// capacity -- never to 0, which the store reads as unbounded and which would make a bounded run
// silently unbounded.
func TestBoundedCacheTouchesTheServedEntryAndTrimsToCapacity(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.h.Capacity = 2

	const q1 = "What is the Aurora kettle made of?"
	stored := cache.Entry{
		Answer:         kettle.answer,
		SourceChunkIDs: kettle.answerSources(),
		ModelUsed:      testModel,
		EntryID:        cache.NewEntryID(),
	}
	hs.store.seedTier1(q1, kettle.id, stored)
	seeded := hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	const q2 = "Which material is the Aurora kettle body?"
	hs.embedder.learn(q2, toward(1, 2, hitCos))
	const q3 = "Is the Aurora kettle cordless?"
	hs.embedFresh(q3)

	t1 := hs.ask(t, askReq{question: q1, productID: kettle.id})
	t2 := hs.ask(t, askReq{question: q2, productID: kettle.id})
	waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
	waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 1 })
	miss := hs.ask(t, askReq{question: q3, productID: kettle.id})
	hs.records(t)

	t1.record(t).str("cache", "TIER1_HIT")
	t2.record(t).str("cache", "TIER2_HIT")
	missRec := miss.record(t)
	missRec.str("cache", "MISS")

	want := []string{stored.EntryID, seeded.EntryID, missRec.text("entry_id")}
	if got := hs.store.touched(); !reflect.DeepEqual(got, want) {
		t.Errorf("touched %q, want the served entries %q in order", got, want)
	}
	if got := hs.store.trimmedTo(); !reflect.DeepEqual(got, []int{2}) {
		t.Errorf("TrimToCapacity called with %v, want [2]: once, at the configured capacity", got)
	}
}
