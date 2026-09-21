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

// Jaccard is the SYMMETRIC overlap of two chunk sets: |A n B| / |A u B|.
//
// It is never the reuse rule -- Overlap is (see above for why the denominator must be the entry's
// own provenance). It exists because Pre-Thesis 3.2.2/3.2.3 require it reported alongside
// containment as a robustness check, with no conclusion allowed to depend on which formulation is
// used, and because GroundedCache gates on symmetric Jaccard over chunk hashes, so this is the
// direct comparison against published practice.
//
// It costs NOTHING on the hit path and must stay that way: interfaces.md H already logs both
// retrieved_chunk_ids and entry_sources, so the run-level figure is derived exactly, offline, from
// the evaluation log. Nothing calls this per request.
//
// Two empty sets score 0, not 1. A vacuous "perfect agreement" between two answers with no
// recorded provenance would be indistinguishable in the numbers from genuine agreement, and
// Overlap already scores an entry with no provenance 0 for the same reason.
func Jaccard(a, b []string) float64 {
	setA := make(map[string]struct{}, len(a))
	for _, id := range a {
		setA[id] = struct{}{}
	}
	setB := make(map[string]struct{}, len(b))
	for _, id := range b {
		setB[id] = struct{}{}
	}
	if len(setA) == 0 && len(setB) == 0 {
		return 0
	}
	inter := 0
	for id := range setA {
		if _, ok := setB[id]; ok {
			inter++
		}
	}
	return float64(inter) / float64(len(setA)+len(setB)-inter)
}

// Thresholds are the rule's two knobs. Both are DEMO VALUES here and are swept, never hand-set,
// for anything reported (proposal 9.4, rules.md #10).
type Thresholds struct {
	Tau   float64 // similarity floor
	Theta float64 // overlap floor

	// TauHigh is the short-circuit ceiling of Pre-Thesis 3.2.3 Figure 3.2: at or above it the
	// cascade serves on similarity ALONE, consulting no provenance -- it runs in cascade.go
	// BEFORE Classify/Namespace, so a fired short-circuit bypasses the lane rule entirely, not
	// just the containment counterfactual.
	//
	// It ships DISABLED (+Inf, cascade.go's default) and the default is pinned by a test, for
	// three measured reasons:
	//
	//  1. There is no safe window on dev-v0. Across 17 labelled probes the traps and the
	//     legitimate hits INTERLEAVE: the worst trap scored 0.9685 while only one of seven
	//     correct reuses (0.9899) sat above it. Any TauHigh low enough to short-circuit an
	//     appreciable share of hits also serves lookalikes, on similarity alone, with the
	//     provenance rule never running.
	//  2. Since the gateway began retrieving concurrently with embedding, a short-circuit saves
	//     no latency anyway -- retrieval has already completed by the time this gate is reached.
	//     What was an optimisation is now purely a rule variant, and it is kept only so the
	//     frontier has the point.
	//  3. The default used to be 1.0 on the theory that cosine similarity "reaches it only on an
	//     identical vector" and that was an unreachable edge case. Discovered live 2026-09-09:
	//     it is not unreachable -- asking the byte-identical question about two different
	//     products embeds to the same vector both times, similarity is exactly 1.0, and the old
	//     default fired, serving one product's cached answer for a different product's question
	//     with no namespace check. +Inf is unreachable by construction (cosine is capped at 1.0);
	//     1.0 was only unreachable by assumption.
	TauHigh float64
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
