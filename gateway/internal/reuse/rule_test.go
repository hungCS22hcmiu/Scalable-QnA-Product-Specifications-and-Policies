package reuse

import "testing"

// These tests are a thesis artifact, not coverage. Each one pins a property that, if it drifted,
// would change what the rule measures while leaving it looking like it still worked.

func TestOverlapIsAsymmetricContainment(t *testing.T) {
	// The single most important test here: it stops anyone "simplifying" Overlap into Jaccard.
	// Jaccard would give 2/5 = 0.4 in BOTH directions; containment does not.
	retrieved := []string{"a", "b", "c"}
	sources := []string{"a", "b"}

	if got := Overlap(retrieved, sources); got != 1.0 {
		t.Errorf("Overlap(retrieved, sources) = %v, want 1.0 — both of the entry's sources were re-retrieved", got)
	}
	if got := Overlap(sources, retrieved); got != 2.0/3.0 {
		t.Errorf("Overlap(sources, retrieved) = %v, want 2/3 — denominator is the SECOND argument", got)
	}
}

func TestOverlapMeasuredDemoPairs(t *testing.T) {
	// Regression pins for the two pairs measured 2026-09-05 on dev-v0 (worklog W08). If either
	// moves, the demo script is stale.
	laptop := []string{
		"policy-returns-electronics#chunk-0", "policy-returns-furniture#chunk-0",
		"policy-warranty#chunk-0", "product-laptops-06#chunk-0", "product-laptops-08#chunk-0",
	}
	paraphrase := laptop // a true paraphrase re-retrieves the same evidence
	sofa := []string{
		"policy-returns-furniture#chunk-0", "policy-returns-electronics#chunk-0",
		"policy-shipping#chunk-0", "product-furniture-04#chunk-0", "product-furniture-08#chunk-0",
	}

	if got := Overlap(paraphrase, laptop); got != 1.0 {
		t.Errorf("paraphrase overlap = %v, want 1.0", got)
	}
	if got := Overlap(sofa, laptop); got != 0.4 {
		t.Errorf("cross-category trap overlap = %v, want 0.4 (only the two return policies are shared)", got)
	}
}

func TestOverlapGranularityAtTopK5(t *testing.T) {
	// With |entrySources| = 5 the score can only take six values, so theta has no resolution
	// finer than 0.2. This is the executable form of that finding; it bounds the theta sweep.
	sources := []string{"a", "b", "c", "d", "e"}
	want := []float64{0, 0.2, 0.4, 0.6, 0.8, 1.0}
	for n, expect := range want {
		if got := Overlap(sources[:n], sources); got != expect {
			t.Errorf("%d of 5 shared: got %v, want %v", n, got, expect)
		}
	}
}

func TestOverlapEdgeCases(t *testing.T) {
	cases := []struct {
		name               string
		retrieved, sources []string
		want               float64
	}{
		{"no provenance can never be shown grounded", []string{"a"}, nil, 0},
		{"empty retrieval shares nothing", nil, []string{"a", "b"}, 0},
		{"disjoint sets", []string{"x", "y"}, []string{"a", "b"}, 0},
		{"duplicates must not push overlap above 1", []string{"a", "a", "a"}, []string{"a", "b"}, 0.5},
		{"order does not matter", []string{"b", "a"}, []string{"a", "b"}, 1.0},
	}
	for _, c := range cases {
		if got := Overlap(c.retrieved, c.sources); got != c.want {
			t.Errorf("%s: got %v, want %v", c.name, got, c.want)
		}
	}
}

func TestDecideRequiresBothConditions(t *testing.T) {
	r := Thresholds{Tau: 0.85, Theta: 0.6}
	full := []string{"a", "b", "c", "d", "e"}
	quarter := []string{"a", "b"} // 2/5 = 0.4, below theta

	cases := []struct {
		name        string
		sim         float64
		retrieved   []string
		wantReuse   bool
		wantSimOnly bool
	}{
		{"both pass", 0.965, full, true, true},
		{"the trap: similarity passes, overlap does not", 0.851, quarter, false, true},
		{"unrelated: neither passes", 0.532, quarter, false, false},
		{"high overlap cannot rescue low similarity", 0.400, full, false, false},
	}
	for _, c := range cases {
		got := r.Decide(c.sim, c.retrieved, full)
		if got.Reuse != c.wantReuse {
			t.Errorf("%s: Reuse = %v, want %v", c.name, got.Reuse, c.wantReuse)
		}
		if got.SimilarityOnly != c.wantSimOnly {
			t.Errorf("%s: SimilarityOnly = %v, want %v", c.name, got.SimilarityOnly, c.wantSimOnly)
		}
	}
}

func TestDecideBoundariesAreInclusive(t *testing.T) {
	// A pair landing EXACTLY on theta reuses. That is a measured case on this corpus and a false
	// hit inside the delta budget -- a documented limitation. Flipping >= to > would erase it
	// from the reported numbers without an ADR.
	r := Thresholds{Tau: 0.85, Theta: 0.6}
	sources := []string{"a", "b", "c", "d", "e"}
	exactlyTheta := []string{"a", "b", "c"} // 3/5 = 0.6

	if d := r.Decide(0.85, exactlyTheta, sources); !d.Reuse {
		t.Error("similarity == tau and overlap == theta must reuse; both bounds are inclusive")
	}
	if d := r.Decide(0.8499, exactlyTheta, sources); d.Reuse {
		t.Error("similarity just below tau must refuse")
	}
}

func TestSimilarityOnlyIsTheBaselineCounterfactual(t *testing.T) {
	// This field is what makes the pre-registered null interpretable: it records what a fixed
	// threshold WOULD have done, at the moment the rule ran. It must not depend on overlap.
	r := Thresholds{Tau: 0.85, Theta: 0.6}
	sources := []string{"a", "b", "c", "d", "e"}

	d := r.Decide(0.90, nil, sources) // overlap 0 -> rule refuses
	if d.Reuse {
		t.Error("rule should refuse at zero overlap")
	}
	if !d.SimilarityOnly {
		t.Error("similarity-only baseline should have reused — this disagreement is the signal C1 measures")
	}
}
