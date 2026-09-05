package httpapi

import (
	"context"
	"log"
	"time"

	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/reuse"
)

// The Tier-2 cascade lives here, not in cache/ or reuse/, and that placement is load-bearing.
// httpapi is the leftmost package and may import rightward; reuse/ may not touch Redis or gRPC,
// because keeping it infrastructure-free is what lets C1 be falsified in isolation
// (docs/design/architecture.md 2). So: reuse/ owns the DECISION, this file owns the PLUMBING.

// stageTimings is interfaces.md F's required decomposition. Four numbers rather than one total,
// because the embedding round-trip sits on the hit path and bounds mu_hit -- a single figure
// would hide exactly the quantity the load-conversion ceiling depends on.
//
// Each span is measured independently. Do NOT derive one by subtracting from another: H notes
// the stage sums need not equal the total, and a derived number would silently absorb whatever
// it was subtracted from.
type stageTimings struct {
	Tier1   time.Duration
	Embed   time.Duration
	Search  time.Duration
	Overlap time.Duration // includes the Retrieve RPC, which is the bulk of it
}

// tier2Outcome is returned even when the rule REFUSES. That is deliberate and is the demo's
// whole point: a refusal must still carry its similarity and overlap to the response, so the
// audience sees a high similarity sitting next to a low overlap and watches the refusal happen.
// A refusal that renders both as null shows nothing.
type tier2Outcome struct {
	Found       bool
	EnteredBand bool // similarity cleared tau, so the cascade paid for retrieval
	Candidate   cache.Candidate
	Decision    reuse.Decision
}

// tryTier2 runs: vector search -> tau gate -> Retrieve -> containment rule.
//
// Every failure degrades to a miss rather than an error. A Tier-2 outage should cost hit rate,
// not availability, and a 500 here would be a served-request outcome fitting none of
// experiment-protocol.md 4's categories -- it would leak out of both the goodput numerator and
// the shed denominator.
func (h *Handler) tryTier2(ctx context.Context, question string, vec []float32, t *stageTimings) tier2Outcome {
	if vec == nil {
		return tier2Outcome{}
	}

	searchStart := time.Now()
	// k=3: decide on the nearest only, but log the runner-up so "what if the nearest neighbour
	// was the wrong entry?" is answerable without a rerun. Deliberately NOT falling through to
	// candidate 2 on a refusal -- that is a different rule with different false-hit behaviour
	// and would need its own pre-registration.
	candidates, err := h.Cache.NearestTier2(ctx, vec, 3)
	t.Search = time.Since(searchStart)
	if err != nil {
		log.Printf("gateway: tier-2 search failed, degrading to MISS: %v", err)
		return tier2Outcome{}
	}
	if len(candidates) == 0 {
		return tier2Outcome{}
	}

	best := candidates[0]
	out := tier2Outcome{Found: true, Candidate: best}

	// Below tau the cascade short-circuits WITHOUT retrieval -- there is no point paying a gRPC
	// round-trip to score a candidate that similarity has already excluded.
	if best.Similarity < h.Thresholds.Tau {
		return out
	}
	out.EnteredBand = true

	overlapStart := time.Now()
	retrieved, err := h.RAG.Retrieve(ctx, question, topKServerDefault)
	if err != nil {
		t.Overlap = time.Since(overlapStart)
		log.Printf("gateway: retrieve for overlap failed, degrading to MISS: %v", err)
		return out
	}
	out.Decision = h.Thresholds.Decide(best.Similarity, retrieved.ChunkIDs, best.Entry.SourceChunkIDs)
	t.Overlap = time.Since(overlapStart)

	log.Printf("gateway: cascade similarity=%.4f overlap=%.2f reuse=%v similarity_only=%v entered_band=true\n"+
		"          retrieved=%v\n          entry_sources=%v",
		best.Similarity, out.Decision.Overlap, out.Decision.Reuse, out.Decision.SimilarityOnly,
		retrieved.ChunkIDs, best.Entry.SourceChunkIDs)

	return out
}
