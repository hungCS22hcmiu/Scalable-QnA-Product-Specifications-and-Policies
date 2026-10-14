package httpapi

// Item 2.3 (docs/work/2026-10-14-refusal-cause-code/): the support gate is called from the cascade
// and every judged Tier-2 candidate carries ONE refusal cause. One test per line of spec.md's
// acceptance. Nothing here edits harness_test.go or an existing test; the wrappers are in
// cause_seams_test.go.
//
// Cases the harness fixtures allow (design.md 5):
//
//   - the paraphrase: a seeded kettle entry, a paraphrase at hitCos          -> TIER2_HIT, NONE
//   - the warranty case: the query's namespace holds no entry                 -> MISS, cause null
//   - a synthetic SUPPORT per arm: an entry in the query's OWN namespace whose answer the evidence
//     (the kettle's three chunks) does not support
//
// The measured warranty pair itself cannot go through Ask: its texts and cached answer carry
// numerals, which the corpus fixture rule forbids (impact.md 3.4).

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"testing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/ragclient"
)

const (
	// lexRefusedAnswer: headphones' answer in the kettle namespace. No numerals, and none of its
	// words is in the kettle's three chunks, so S_lex is 0 and the numeric arm has nothing to refuse.
	lexRefusedAnswer = "silicone ear tips and a compact charging case"
	// numericRefusedAnswer: kettle.answer plus a rating the evidence does not carry. Six of its eight
	// content tokens are in the kettle's chunk 0, so S_lex is 0.75 and the lexical arm admits; "1500 W"
	// is not in any chunk, so the numeric arm refuses.
	numericRefusedAnswer = "a brushed steel body and an automatic shutoff switch rated 1500 W"
)

// seedKettle stores a Tier-2 entry in the kettle namespace on basis(dir) with the given answer.
func (hs *harness) seedKettle(answer string, dir int) cache.Tier2Entry {
	e := hitFixture(kettle, fmt.Sprintf("seeded kettle question %d", dir))
	e.Answer = answer
	hs.store.seedTier2(e, float32s(basis(dir)))
	return e
}

// askNear asks a question embedded at cosine cos from basis(dir), about product p.
func (hs *harness) askNear(t *testing.T, q string, dir int, cos float64, p product) *call {
	t.Helper()
	hs.embedder.learn(q, toward(dir, dir+1, cos))
	return hs.ask(t, askReq{question: q, productID: p.id})
}

// --- acceptance 1: the paraphrase and the warranty case ---------------------------------------

func TestCauseServedHitIsNoneWithBothArms(t *testing.T) {
	hs := newHarness(t, 1, 0)
	seeded := hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	c := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
	waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
	waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 1 })
	hs.records(t)

	rec := c.record(t)
	rec.str("cache", "TIER2_HIT")
	rec.str("refusal_cause", "NONE")
	rec.number("support_lex", 1) // kettle.answer is a verbatim part of chunk 0
	rec.boolean("support_numeric_ok", true)
	rec.boolean("entered_band", true)
	rec.str("reuse_rule", "namespace")
	rec.str("candidate_entry_id", seeded.EntryID)
	rec.strs("candidate_sources", seeded.SourceChunkIDs)
	rec.str("entry_id", seeded.EntryID) // served: entry_* IS the candidate
	if n := len(hs.rag.answerCalls()); n != 0 {
		t.Errorf("Answer called %d times on a served hit", n)
	}
}

// The warranty case under configuration 4. The query's namespace holds no entry, so the scoped
// search returns nothing: no candidate is judged, the gate never runs, and the cause is NULL. It is
// not NAMESPACE and not SUPPORT (spec.md, acceptance 1, restated after impact.md 3.4).
func TestCauseWarrantyCaseIsNullBecauseTheNamespaceHoldsNothing(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.seedHit(headphones, "What do the EarBuds Pop ship with?", 1) // a lookalike in ANOTHER namespace
	c := hs.askNear(t, "What is included with the Aurora kettle?", 1, hitCos, kettle)
	hs.records(t)

	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.null("refusal_cause")
	rec.null("support_lex")
	rec.null("support_numeric_ok")
	rec.null("similarity")
	rec.boolean("entered_band", false)
	rec.absent("reuse_rule")
	rec.absent("candidate_entry_id")
	rec.absent("candidate_sources")
	if n := len(hs.rag.answerCalls()); n != 1 {
		t.Errorf("Answer called %d times, want 1: no candidate means generate", n)
	}
}

// --- acceptance 2 and 3: every exit, and a cold cache is never NAMESPACE ----------------------

func TestCauseColdCacheIsNullAndASearchRan(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.embedFresh("Is the Aurora kettle cordless?")
	c := hs.ask(t, askReq{question: "Is the Aurora kettle cordless?", productID: kettle.id})
	hs.records(t)

	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.null("refusal_cause")
	rec.null("similarity")
	rec.notNull("t_search_ms") // a search ran and found nothing: that is a cold cache
	if got := hs.store.namespacesSearched(); len(got) != 1 || got[0] != kettle.id {
		t.Errorf("namespaces searched = %q, want just %q", got, kettle.id)
	}
}

func TestCauseBelowTauIsSimilarity(t *testing.T) {
	hs := newHarness(t, 1, 0)
	seeded := hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	c := hs.askNear(t, "Does the Aurora kettle have a lid?", 1, belowTauCos, kettle)
	hs.records(t)

	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.str("refusal_cause", "SIMILARITY")
	rec.null("support_lex") // the gate does not run below tau
	rec.null("support_numeric_ok")
	rec.notNull("similarity")
	rec.boolean("entered_band", false)
	rec.null("source_overlap")
	rec.str("candidate_entry_id", seeded.EntryID)
}

// --- acceptance 7 and 1b: each arm alone refuses, and both values are logged ------------------

// The refused record pairs the CANDIDATE's overlap with the NEW entry's sources unless the candidate
// is named: this is design-review F1. The seeded entry's sources are chosen to differ from what the
// miss writes, so the two cannot be confused.
func TestCauseLexicalArmRefusesAlone(t *testing.T) {
	hs := newHarness(t, 1, 0)
	e := hitFixture(kettle, "seeded kettle question")
	e.Answer = lexRefusedAnswer
	e.SourceChunkIDs = []string{kettle.id + "#chunk-0", kettle.id + "#chunk-9"} // overlap 1/2 with {0,1,2}
	hs.store.seedTier2(e, float32s(basis(1)))
	c := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
	hs.records(t)

	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", c.w.Code, c.w.Body)
	}
	resp := c.response(t)
	resp.str("cache", "MISS")
	resp.str("answer", kettle.answer) // a fresh generation, not the refused entry's answer
	resp.number("source_overlap", 0.5)
	resp.notNull("similarity")

	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.str("refusal_cause", "SUPPORT")
	rec.number("support_lex", 0)
	rec.boolean("support_numeric_ok", true) // the numeric arm admits: the answer has no numbers
	rec.boolean("entered_band", true)
	rec.number("source_overlap", 0.5)
	rec.str("reuse_rule", "namespace")
	// F1: the candidate and the entry the miss wrote are different entries with different sources.
	rec.str("candidate_entry_id", e.EntryID)
	rec.strs("candidate_sources", e.SourceChunkIDs)
	if got := rec.text("entry_id"); got == e.EntryID {
		t.Errorf("entry_id = the refused candidate %s; on a refusal it must name the entry the miss wrote", got)
	}
	rec.strs("entry_sources", kettle.answerSources())
	if n := len(hs.rag.answerCalls()); n != 1 {
		t.Errorf("Answer called %d times, want 1: a support refusal generates", n)
	}
}

func TestCauseNumericArmRefusesAlone(t *testing.T) {
	hs := newHarness(t, 1, 0)
	seeded := hs.seedKettle(numericRefusedAnswer, 1)
	c := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
	hs.records(t)

	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.str("refusal_cause", "SUPPORT")
	rec.number("support_lex", 0.75) // the lexical arm admits (>= 0.6)
	rec.boolean("support_numeric_ok", false)
	rec.str("candidate_entry_id", seeded.EntryID)
}

// --- acceptance 3: NAMESPACE only through a disagreeing store ---------------------------------

func TestCauseNamespaceIsTheAlarmAndComesFirst(t *testing.T) {
	for _, c := range []struct {
		name     string
		cos      float64
		wantBand bool
	}{
		{"above tau", hitCos, true},
		// A2: NAMESPACE before SIMILARITY, so a low similarity does not hide the alarm.
		{"below tau", belowTauCos, false},
	} {
		t.Run(c.name, func(t *testing.T) {
			hs := newHarness(t, 1, 0)
			hs.h.Cache = anyNamespaceStore{hs.store}
			wrong := hs.seedHit(headphones, "What do the EarBuds Pop ship with?", 1) // the wrong namespace
			call := hs.askNear(t, "What is included with the Aurora kettle?", 1, c.cos, kettle)
			hs.records(t)

			rec := call.record(t)
			rec.str("cache", "MISS")
			rec.str("refusal_cause", "NAMESPACE")
			rec.null("support_lex")
			rec.null("support_numeric_ok")
			rec.notNull("similarity")
			rec.boolean("entered_band", c.wantBand)
			rec.str("candidate_entry_id", wrong.EntryID)
		})
	}
}

// --- acceptance 4: a server that sends no evidence text ---------------------------------------

func TestCauseStaleServerIsNotScoredAndNotServed(t *testing.T) {
	var logged bytes.Buffer
	log.SetOutput(&logged)
	t.Cleanup(func() { log.SetOutput(os.Stderr) })

	hs := newHarness(t, 1, 0)
	hs.useRAG(t, textlessRAG{hs.rag})
	seeded1 := hs.seedKettle(kettle.answer, 1)
	hs.seedKettle(kettle.answer, 4)
	c1 := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
	c2 := hs.askNear(t, "Does the Aurora kettle shut itself off?", 4, hitCos, kettle)
	hs.records(t)

	for _, c := range []*call{c1, c2} {
		resp := c.response(t)
		resp.str("cache", "MISS") // the cached answer is perfectly supportable, and still not served
		rec := c.record(t)
		rec.str("cache", "MISS")
		rec.str("refusal_cause", "NOT_SCORED") // never SUPPORT, never null
		rec.null("support_lex")
		rec.null("support_numeric_ok")
		rec.boolean("entered_band", true)
		rec.notNull("source_overlap")
	}
	c1.record(t).str("candidate_entry_id", seeded1.EntryID)
	if n := len(hs.store.bumped()); n != 0 {
		t.Errorf("hit_count bumped %d times: a stale server was served", n)
	}
	// One ERROR line per process, however many requests: a stale server fails every request alike.
	if n := strings.Count(logged.String(), "refusal_cause=NOT_SCORED"); n != 1 {
		t.Errorf("%d NOT_SCORED alarm lines, want exactly 1\n%s", n, logged.String())
	}
}

// --- acceptance 5: zero chunks ----------------------------------------------------------------

func TestCauseZeroChunksMakeNoTier2Attempt(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.useRAG(t, zeroChunkRAG{hs.rag})
	// A kettle entry that WOULD be a hit: same namespace, cosine hitCos. Before the guard, the SPEC
	// lane's namespace fell back to the product ID, the search ran, and this was served with no
	// evidence behind it.
	hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	c := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
	hs.records(t)

	if n := hs.store.callCount("NearestTier2InNamespace"); n != 0 {
		t.Errorf("%d Tier-2 searches after a zero-chunk retrieval, want 0", n)
	}
	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.null("refusal_cause")
	rec.null("similarity")
	rec.null("t_search_ms")
	rec.null("retrieved_chunk_ids")
	rec.number("dataset_epoch_at_retrieval", float64(testEpoch)) // retrieval worked; it found nothing
	rec.boolean("entered_band", false)
	rec.absent("reuse_rule")
	rec.absent("candidate_entry_id")
}

// --- the cause survives the miss path (design.md F3) ------------------------------------------

func TestCauseSurvivesAShedRequest(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.embedFresh("Is the Aurora kettle cordless?")
	g := hs.holdAnswers()
	hs.seedKettle(lexRefusedAnswer, 1)

	a := hs.start(askReq{question: "Is the Aurora kettle cordless?", productID: kettle.id})
	waitFor(t, "A to hold the permit", func() bool { return hs.h.Admission.InFlight() == 1 })
	b := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
	g.open()
	a.wait(t)
	hs.records(t)

	if b.w.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d, want 503", b.w.Code)
	}
	rec := b.record(t)
	rec.str("cache", "SHED")
	rec.str("refusal_cause", "SUPPORT")
	rec.number("support_lex", 0)
	rec.boolean("support_numeric_ok", true)
}

func TestCauseSurvivesAFailedGeneration(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.rag.onAnswer(func(context.Context) error { return status.Error(codes.Internal, "the model runner crashed") })
	hs.seedKettle(numericRefusedAnswer, 1)
	b := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
	hs.records(t)

	if b.w.Code != http.StatusBadGateway {
		t.Fatalf("status %d, want 502", b.w.Code)
	}
	rec := b.record(t)
	rec.str("cache", "GENERATION_FAILED")
	rec.str("refusal_cause", "SUPPORT")
	rec.number("support_lex", 0.75)
	rec.boolean("support_numeric_ok", false)
	rec.str("answer_sha256", "") // not served: no text, so no hash (interfaces.md H rule 4)
}

func TestCauseSurvivesAnAbandonedRequest(t *testing.T) {
	hs := newHarness(t, 1, 1)
	hs.embedFresh("Is the Aurora kettle cordless?")
	g := hs.holdAnswers()
	hs.seedKettle(lexRefusedAnswer, 1)

	a := hs.start(askReq{question: "Is the Aurora kettle cordless?", productID: kettle.id})
	waitFor(t, "A to hold the permit", func() bool { return hs.h.Admission.InFlight() == 1 })
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	hs.embedder.learn("Which material is the Aurora kettle body?", toward(1, 2, hitCos))
	b := hs.start(askReq{question: "Which material is the Aurora kettle body?", productID: kettle.id, ctx: ctx})
	waitFor(t, "B to queue", func() bool { return hs.h.Admission.Queued() == 1 })
	cancel()
	b.wait(t)
	g.open()
	a.wait(t)
	hs.records(t)

	rec := b.record(t)
	rec.str("cache", "ABANDONED")
	rec.str("refusal_cause", "SUPPORT")
	rec.number("support_lex", 0)
}

// --- acceptance 6: reading the log offline ----------------------------------------------------

// checkCauseInvariants is design.md 6's I2' to I6, as a check on one finished record.
func checkCauseInvariants(t *testing.T, rec fields) {
	t.Helper()
	// The three required keys are PRESENT on every record, null or not (F8): a pre-2.3 log lacks them.
	cause, lex, num := rec.get("refusal_cause"), rec.get("support_lex"), rec.get("support_numeric_ok")
	cache, _ := rec.get("cache").(string)
	_, hasRule := rec.m["reuse_rule"]
	_, hasCand := rec.m["candidate_entry_id"]
	judged := cause != nil

	// I3: refusal_cause, similarity, reuse_rule and candidate_entry_id appear together.
	if judged != (rec.get("similarity") != nil) || judged != hasRule || judged != hasCand {
		t.Errorf("%s: I3 broken: cause=%v similarity=%v reuse_rule=%v candidate=%v",
			rec.what, cause, rec.m["similarity"], hasRule, hasCand)
	}
	// I4: NONE is exactly a served Tier-2 hit.
	if (cause == "NONE") != (cache == "TIER2_HIT") {
		t.Errorf("%s: I4 broken: cause=%v cache=%s", rec.what, cause, cache)
	}
	// I5: the two arms are both null or both set, set only where the gate scored, and a SUPPORT
	// refusal always has them (the gate-off arm of item 2.4 will relax the last).
	if (lex == nil) != (num == nil) {
		t.Errorf("%s: I5 broken: support_lex=%v support_numeric_ok=%v", rec.what, lex, num)
	}
	if lex != nil && cause != "NONE" && cause != "SUPPORT" {
		t.Errorf("%s: I5 broken: support values on cause %v", rec.what, cause)
	}
	if cause == "SUPPORT" && lex == nil {
		t.Errorf("%s: I5 broken: SUPPORT without support values", rec.what)
	}
	// I6: CONTAINMENT is absent, not zero.
	if cause == "CONTAINMENT" {
		t.Errorf("%s: I6 broken: CONTAINMENT was written", rec.what)
	}
	// I2': a banded request that was not served has a reason from the gate or the alarm.
	if rec.get("entered_band") == true && cache != "TIER2_HIT" &&
		cause != "SUPPORT" && cause != "NOT_SCORED" && cause != "NAMESPACE" {
		t.Errorf("%s: I2' broken: banded, not a hit, cause=%v", rec.what, cause)
	}
}

// One run that reaches every cause, read back from requests.jsonl alone. A SUPPORT refusal and a
// NAMESPACE refusal must be told apart by the field, and the causes must add up to the judged
// candidates: the Done-when of item 2.3.
func TestCauseOfflineReading(t *testing.T) {
	hs := newHarness(t, 1, 0)
	var calls []*call

	hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	hs.seedKettle(lexRefusedAnswer, 4)
	hs.seedKettle(numericRefusedAnswer, 7)
	hs.seedHit(kettle, "Does the Aurora kettle have a lid?", 10)
	hs.seedKettle(kettle.answer, 16)
	// The entry the disagreeing store will hand back for the NAMESPACE case. Its namespace is one no
	// request uses, so the headphones namespace stays EMPTY for the "no candidate" case below.
	stray := hitFixture(kettle, "What is the toaster slot width?")
	stray.Namespace = "product-toaster-99"
	hs.store.seedTier2(stray, float32s(basis(19)))

	calls = append(calls, hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)) // NONE
	waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 1 })
	calls = append(calls, hs.askNear(t, "What is the kettle made from?", 4, hitCos, kettle))      // SUPPORT (lexical)
	calls = append(calls, hs.askNear(t, "How strong is the kettle?", 7, hitCos, kettle))          // SUPPORT (numeric)
	calls = append(calls, hs.askNear(t, "Is the kettle lid removable?", 10, belowTauCos, kettle)) // SIMILARITY
	// No headphones entry exists, so this request finds an empty namespace.
	hs.embedder.learn("What do the EarBuds Pop ship with in the box?", basis(130))
	calls = append(calls, hs.ask(t, askReq{question: "What do the EarBuds Pop ship with in the box?", productID: headphones.id})) // null: empty namespace

	hs.h.Cache = anyNamespaceStore{hs.store}
	calls = append(calls, hs.askNear(t, "Does the kettle ship with ear tips?", 19, hitCos, kettle)) // NAMESPACE
	hs.h.Cache = hs.store

	hs.useRAG(t, textlessRAG{hs.rag})
	calls = append(calls, hs.askNear(t, "Which part of the kettle is steel?", 16, hitCos, kettle)) // NOT_SCORED
	hs.useRAG(t, zeroChunkRAG{hs.rag})
	calls = append(calls, hs.askNear(t, "Where is the kettle switch?", 16, hitCos, kettle)) // null: zero chunks
	hs.records(t)

	count := map[string]int{}
	judged := 0
	for _, c := range calls {
		rec := c.record(t)
		checkCauseInvariants(t, rec)
		if cause, ok := rec.get("refusal_cause").(string); ok {
			count[cause]++
			judged++
		} else {
			count["null"]++
		}
	}
	want := map[string]int{"NONE": 1, "SUPPORT": 2, "SIMILARITY": 1, "NAMESPACE": 1, "NOT_SCORED": 1, "null": 2}
	for cause, n := range want {
		if count[cause] != n {
			t.Errorf("cause %s: %d records, want %d (all: %v)", cause, count[cause], n, count)
		}
	}
	if judged != len(calls)-count["null"] {
		t.Errorf("%d judged records, want every record that has a cause (%d of %d)", judged, len(calls)-count["null"], len(calls))
	}
	if count["CONTAINMENT"] != 0 {
		t.Errorf("CONTAINMENT appears %d times; it is absent, not zero", count["CONTAINMENT"])
	}
}

// --- /ai-review F1: every exit that has NO candidate has a null cause ---------------------------

// Each of these exits seeds what would otherwise be a TIER2_HIT and proves its failure fired, so the
// test cannot pass by never reaching the exit. The cause must be null on all of them: a cause here
// would put a number in "false hits by cause" for a request that judged nothing (I3).
func TestCauseIsNullOnEveryExitWithNoCandidate(t *testing.T) {
	for _, c := range []struct {
		name    string
		arrange func(hs *harness)
		fired   func(hs *harness) bool
	}{
		{"embed failure", func(hs *harness) { hs.embedder.failEverything() },
			func(hs *harness) bool { _, f := hs.embedder.counts(); return f > 0 }},
		{"retrieve failure", func(hs *harness) { hs.rag.failRetrieve(status.Error(codes.Unavailable, "the corpus index is offline")) },
			func(hs *harness) bool { return hs.rag.retrieveFailures() > 0 }},
		{"search error", func(hs *harness) {
			hs.store.fail("NearestTier2InNamespace", errors.New("redis: idx:cache unavailable"))
		},
			func(hs *harness) bool { return hs.store.injectedCount() > 0 }},
	} {
		t.Run(c.name, func(t *testing.T) {
			hs := newHarness(t, 1, 0)
			hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
			c.arrange(hs)
			call := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
			hs.records(t)

			if !c.fired(hs) {
				t.Fatal("the failure never fired, so nothing degraded")
			}
			rec := call.record(t)
			rec.str("cache", "MISS")
			rec.null("refusal_cause")
			rec.null("support_lex")
			rec.null("support_numeric_ok")
			rec.null("similarity")
			rec.absent("reuse_rule")
			rec.absent("candidate_entry_id")
			rec.boolean("entered_band", false)
			checkCauseInvariants(t, rec)
		})
	}
}

// The real empty-namespace exit: a retrieval WITH chunks whose IDs carry neither doc-id kind prefix
// (interfaces.md C), so no namespace can be derived. TestEmptyNamespaceRunsNoSearch, an existing test,
// calls tryTier2 with ZERO chunks and now passes through the zero-chunk guard instead of this branch
// (finding found while resolving /ai-review F1), so this test is the one that reaches it. Called
// directly, as that test does, because no request through the harness can reach it.
func TestCauseEmptyNamespaceExitHasNoCauseAndRunsNoSearch(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)

	var tm stageTimings
	out := hs.h.tryTier2(context.Background(), "", float32s(basis(1)), &ragclient.RetrieveResult{
		ChunkIDs: []string{"orphan-doc#chunk-0"}, Texts: []string{"text of a document with no kind prefix"},
		DatasetEpoch: testEpoch,
	}, &tm)

	if out.Found || out.EnteredBand || out.Served || out.Cause != "" || out.Support != nil {
		t.Errorf("empty namespace: Found=%v EnteredBand=%v Served=%v Cause=%q Support=%v, want a bare outcome",
			out.Found, out.EnteredBand, out.Served, out.Cause, out.Support)
	}
	if out.QueryNS != "" {
		t.Fatalf("setup: QueryNS = %q, want empty (the chunk ID has no kind prefix)", out.QueryNS)
	}
	if tm.Search != 0 || hs.store.callCount("NearestTier2InNamespace") != 0 {
		t.Errorf("a search ran on an empty namespace (span %v, calls %d)", tm.Search, hs.store.callCount("NearestTier2InNamespace"))
	}
}

// --- /ai-review F3 and F4: a candidate with no provenance --------------------------------------

// A candidate with empty source_chunk_ids exists: a zero-chunk miss still writes one under the
// product-ID namespace (design.md 9). With a stale server it must still be NOT_SCORED. If the gate were
// handed the ENTRY's source IDs instead of this request's, "texts empty, IDs empty" would read as a
// legitimate empty retrieval, be scored 0, and be logged SUPPORT: a broken instrument blamed on the
// gate, and rule 10 would not fire (design.md F9). Every other test passes either way.
//
// It also pins what the contract says about such a record: candidate_entry_id is the presence marker
// and candidate_sources is omitted when empty (interfaces.md H v0.13).
func TestCauseStaleServerWithAnUnprovenancedCandidateIsStillNotScored(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.useRAG(t, textlessRAG{hs.rag})
	e := hitFixture(kettle, "seeded kettle question")
	e.SourceChunkIDs = nil
	hs.store.seedTier2(e, float32s(basis(1)))
	c := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
	hs.records(t)

	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.str("refusal_cause", "NOT_SCORED")
	rec.null("support_lex")
	rec.null("support_numeric_ok")
	rec.str("candidate_entry_id", e.EntryID)
	rec.absent("candidate_sources")
	checkCauseInvariants(t, rec)
}
