package reuse

// C1's decision, computed in Go as a set intersection over chunk IDs. There is deliberately no
// import beyond the standard library and no I/O: this package must stay infrastructure-free so
// C1 can be falsified in isolation (docs/design/architecture.md 2).

// Overlap is the reuse score: ASYMMETRIC CONTAINMENT, not Jaccard.
//
//	overlap(retrieved, entrySources) = |retrieved ∩ entrySources| / |entrySources|
//
// It reads as a question about evidence: *is what grounded the cached answer still what grounds
// this new question?* The denominator is therefore the ENTRY's source set, not the incoming
// query's retrieval. Swapping the denominator, or "simplifying" this to Jaccard, changes the
// score on the trap pair and makes the rule stop distinguishing the case it exists for --
// silently, since both variants return a plausible number in [0,1].
//
// An entry with no recorded provenance scores 0: it can never be shown to still be grounded.
//
// Granularity note: with top_k = 5 on both sides the result takes only six values
// (0, 0.2, 0.4, 0.6, 0.8, 1.0), so theta has no resolution finer than 0.2. That bounds the
// theta sweep and is asserted in the tests.
func Overlap(retrieved, entrySources []string) float64 {
	if len(entrySources) == 0 {
		return 0
	}
	// Dedupe both sides. Duplicate chunk IDs would inflate the numerator past the denominator
	// and produce an overlap above 1.0.
	sources := make(map[string]struct{}, len(entrySources))
	for _, id := range entrySources {
		sources[id] = struct{}{}
	}
	seen := make(map[string]struct{}, len(retrieved))
	hits := 0
	for _, id := range retrieved {
		if _, dup := seen[id]; dup {
			continue
		}
		seen[id] = struct{}{}
		if _, ok := sources[id]; ok {
			hits++
		}
	}
	return float64(hits) / float64(len(sources))
}

// Thresholds are the rule's two knobs. Both are DEMO VALUES here and are swept, never hand-set,
// for anything reported (proposal 9.4, rules.md #10).
type Thresholds struct {
	Tau   float64 // similarity floor
	Theta float64 // overlap floor
}

// Decision records what the rule concluded and enough to reconstruct why.
type Decision struct {
	Reuse   bool
	Overlap float64

	// SimilarityOnly is the counterfactual: what a fixed-threshold baseline (config 3, which is
	// also GPTCache's rule) would have decided on similarity alone. interfaces.md H requires it
	// recorded AT DECISION TIME because it cannot be reconstructed afterwards against cache
	// state that no longer exists -- and without it the pre-registered null of
	// experiment-protocol.md 6 is uninterpretable.
	SimilarityOnly bool
}

// Decide applies overlap ≥ theta ∧ similarity ≥ tau.
func (t Thresholds) Decide(similarity float64, retrieved, entrySources []string) Decision {
	o := Overlap(retrieved, entrySources)
	simOK := similarity >= t.Tau
	return Decision{
		// Inclusive on both bounds. A pair landing exactly on theta reuses -- a real, measured
		// case on this corpus, and a false hit inside the delta budget. Flipping to > would make
		// that limitation vanish from the numbers without an ADR.
		Reuse:          simOK && o >= t.Theta,
		Overlap:        o,
		SimilarityOnly: simOK,
	}
}
