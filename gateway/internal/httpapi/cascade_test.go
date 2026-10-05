package httpapi

// Tests for configuration 4's Tier-2 cascade after the unfiltered phase was retired (super-plan.md
// item 1.3; docs/work/2026-10-05-retire-unfiltered-phase/, design.md §4 T1-T7). They pin THIS
// cascade, not every configuration: configuration 3 searches globally by design, and when it is
// built it gets its own path rather than a weaker version of these tests.
//
// Every TIER2_HIT test waits for the detached hit_count bump and Tier-1 promotion before records(),
// so neither lands after the test has finished.

import (
	"context"
	"net/http"
	"reflect"
	"testing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/hung/thesis/gateway/internal/ragclient"
)

// waitForHitWrites waits for the two detached writes a TIER2_HIT makes when nothing else has
// written Tier 1.
func waitForHitWrites(t *testing.T, hs *harness) {
	t.Helper()
	waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
	waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 1 })
}

// T1. One search, scoped to the query's namespace, on a hit and on a refusal below tau alike. A
// global search cannot come back through cacheStore without failing to compile
// (harness_test.go's interface check), so what is left to pin is the count and the argument.
func TestCascadeSearchesOnceInTheQuerysNamespace(t *testing.T) {
	for _, tc := range []struct {
		name  string
		cos   float64
		cache string
	}{
		{"hit", hitCos, "TIER2_HIT"},
		{"below tau", belowTauCos, "MISS"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			hs := newHarness(t, 1, 0)
			hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
			const q = "Which material is the Aurora kettle body?"
			hs.embedder.learn(q, toward(1, 2, tc.cos))

			c := hs.ask(t, askReq{question: q, productID: kettle.id})
			if tc.cache == "TIER2_HIT" {
				waitForHitWrites(t, hs)
			}
			hs.records(t)

			if c.w.Code != http.StatusOK {
				t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
			}
			c.record(t).str("cache", tc.cache)
			if n := hs.store.callCount("NearestTier2InNamespace"); n != 1 {
				t.Errorf("NearestTier2InNamespace called %d times, want 1", n)
			}
			if got, want := hs.store.namespacesSearched(), []string{kettle.id}; !reflect.DeepEqual(got, want) {
				t.Errorf("searched namespaces %q, want %q", got, want)
			}
		})
	}
}

// T2, F-E. Retrieval failed, so the request has no namespace and no evidence to judge with. It must
// not search, and must not report a similarity, a band entry or an overlap: a zero overlap here
// would read as a refusal on evidence that was never gathered. A same-namespace entry at hitCos
// is seeded so that any search left on this path would find it.
func TestRetrieveFailureReportsNoTier2Evidence(t *testing.T) {
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
	resp := c.response(t)
	resp.str("cache", "MISS")
	resp.null("similarity")
	resp.null("source_overlap")
	resp.null("overlap_decision")

	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.boolean("entered_band", false)
	rec.null("similarity")
	rec.null("source_overlap")
	rec.null("t_search_ms")
	if n := hs.store.callCount("NearestTier2InNamespace"); n != 0 {
		t.Errorf("NearestTier2InNamespace called %d times after retrieval failed, want 0", n)
	}
}

// T3. A candidate at exactly tau is served AND enters the band: the band and the served rule must
// agree on the boundary, or a hit could be logged as never having entered it. N2 keeps every other
// fixture 0.05 from tau, because float32 narrowing moves a cosine near it. One-hot vectors survive
// narrowing exactly and their cosine is exactly 1, so tau is moved to the vector instead. It is set
// before the only request, as TestBoundedCacheTouchesTheServedEntryAndTrimsToCapacity sets Capacity.
func TestCandidateExactlyAtTauIsServedAndEntersTheBand(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.h.Thresholds.Tau = 1.0
	hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	const q = "Which material is the Aurora kettle body?"
	hs.embedder.learn(q, basis(1))

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	waitForHitWrites(t, hs)
	hs.records(t)

	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
	}
	resp := c.response(t)
	resp.str("cache", "TIER2_HIT")
	resp.number("similarity", 1)
	resp.boolean("overlap_decision", true)

	rec := c.record(t)
	rec.str("cache", "TIER2_HIT")
	rec.number("similarity", 1)
	rec.boolean("entered_band", true)
}

// T4, F-G. The containment counterfactual describes the entry the rule SERVED, not the nearest entry
// overall. The headphones entry is closer to the query (0.99) but in another namespace, and shares
// no source with the kettle's retrieval. The kettle entry is at hitCos, with sources [#0, #1]
// inside the retrieved [#0, #1, #2], so its containment is exactly 1. An overlap of 0 here would
// be the headphones entry's.
func TestCounterfactualIsComputedOnTheServedEntry(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "What is the Aurora kettle body made of?"
	query := toward(1, 2, 0.99)
	hs.embedder.learn(q, query)
	hs.seedHit(headphones, "What do the EarBuds Pop come with?", 1)
	served := hitFixture(kettle, "Which material is the Aurora kettle body?")
	hs.store.seedTier2(served, float32s(around(query, 3, hitCos)))

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	waitForHitWrites(t, hs)
	hs.records(t)

	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
	}
	resp := c.response(t)
	resp.str("cache", "TIER2_HIT")
	resp.str("answer", kettle.answer)
	resp.number("source_overlap", 1)
	resp.boolean("overlap_decision", true)

	rec := c.record(t)
	rec.str("cache", "TIER2_HIT")
	rec.str("entry_id", served.EntryID)
	rec.number("source_overlap", 1)
}

// T5. similarity_only_decision was retired with the phase that produced it (interfaces.md §H, v0.9).
// A banded request is where it used to appear, so that is where its absence is checked.
func TestRecordCarriesNoSimilarityOnlyDecision(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	const q = "Which material is the Aurora kettle body?"
	hs.embedder.learn(q, toward(1, 2, hitCos))

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	waitForHitWrites(t, hs)
	hs.records(t)

	rec := c.record(t)
	rec.str("cache", "TIER2_HIT")
	rec.boolean("entered_band", true)
	rec.absent("similarity_only_decision")
}

// T6, the 2026-09-09 regression class. The byte-identical question about another product embeds to
// the same vector, so its similarity is exactly 1 -- the case that served one product's cached
// answer for another's while a similarity-only short-circuit existed. Moved here from reuse's
// TauHigh tests when the knob was retired: the property is now held by the namespace-scoped search,
// so it is tested where that search runs.
func TestIdenticalQuestionAboutAnotherProductIsNotServed(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "What comes in the box?"
	hs.store.seedTier2(hitFixture(headphones, q), float32s(basis(1)))
	hs.embedder.learn(q, basis(1))

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
		t.Errorf("Answer called %d times, want 1: the question must be generated for its own product", n)
	}
}

// T7. An empty namespace runs no search and times none. Timing a no-op call would leave a span of a
// few microseconds, which msPtr renders as a measurement rather than null. No request through the
// harness can reach this path, because checkEveryRecord requires a product_id and the spec lane
// then always names it, so tryTier2 is called directly with no product and an empty retrieval. In
// production the demo sends no product_id, and an empty retrieval reaches it.
func TestEmptyNamespaceRunsNoSearch(t *testing.T) {
	hs := newHarness(t, 1, 0)
	hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)

	var tm stageTimings
	out := hs.h.tryTier2(context.Background(), "", float32s(basis(1)),
		&ragclient.RetrieveResult{DatasetEpoch: testEpoch}, &tm)

	if out.Found || out.EnteredBand {
		t.Errorf("Found = %v, EnteredBand = %v on an empty namespace, want both false", out.Found, out.EnteredBand)
	}
	if tm.Search != 0 {
		t.Errorf("Search = %v on an empty namespace, want 0 (rendered null)", tm.Search)
	}
	if n := hs.store.callCount("NearestTier2InNamespace"); n != 0 {
		t.Errorf("NearestTier2InNamespace called %d times on an empty namespace, want 0", n)
	}
}
