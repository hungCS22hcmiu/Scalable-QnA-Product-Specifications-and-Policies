package httpapi

import (
	"errors"
	"testing"
)

// interfaces.md §H rule 12 (v0.20): a request whose Tier-2 search returned an error still degrades to
// a MISS, and the existing record looks exactly like a cold-cache miss (cache MISS, null cause,
// entered_band false: see TestCauseIsNullOnEveryExitWithNoCandidate). So tier2_search_failed is the
// only trace that the search broke, and the Logger's counter is what makes the run inadmissible.
// Without the key, an idx:cache lost during a run reads as a colder cache and a lower h.
func TestTier2SearchErrorMarksTheRecord(t *testing.T) {
	// A failed search: the entry that would have been a TIER2_HIT exists, the search errors.
	hs := newHarness(t, 1, 0)
	hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	hs.store.fail("NearestTier2InNamespace", errors.New("redis: No such index"))
	failed := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
	hs.records(t)

	if hs.store.injectedCount() == 0 {
		t.Fatal("the injected search error never fired, so nothing degraded")
	}
	rec := failed.record(t)
	rec.str("cache", "MISS")
	rec.boolean("tier2_search_failed", true)
	if got := hs.h.Eval.Tier2SearchFailures(); got != 1 {
		t.Errorf("Eval.Tier2SearchFailures() = %d, want 1", got)
	}

	// An ordinary cold-cache miss on another question: the search ran and found nothing. The key is
	// absent, so only a real search error is marked.
	cold := newHarness(t, 1, 0)
	cold.embedFresh("Is the Aurora kettle cordless?")
	miss := cold.ask(t, askReq{question: "Is the Aurora kettle cordless?", productID: kettle.id})
	cold.records(t)

	rec = miss.record(t)
	rec.str("cache", "MISS")
	rec.absent("tier2_search_failed")
	if got := cold.h.Eval.Tier2SearchFailures(); got != 0 {
		t.Errorf("a normal MISS counted %d Tier-2 search failure(s), want 0", got)
	}
}
