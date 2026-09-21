package httpapi

import (
	"context"
	"log"
	"time"

	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/ragclient"
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
	Tier1 time.Duration
	Embed time.Duration

	// Search is the SUM of two independently measured vector searches: the unfiltered k=1 that
	// works the tau gate, and the namespace-scoped k=1 that follows retrieval. Summing two
	// measured spans is not the same thing as deriving one by subtraction, which the note above
	// forbids -- both addends are timed directly and neither absorbs another stage.
	Search time.Duration
	// Overlap is the Retrieve RPC span. It used to be measured inside the cascade and so was
	// zero whenever the request short-circuited below tau; retrieval now runs concurrently with
	// the embedding for every Tier-1 miss, so this is non-zero even on a short-circuit. Read
	// EnteredBand -- not this -- to tell a banded request from a short-circuited one.
	Overlap time.Duration
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

	// --- two-lane experiment (.docs/work/two-lane-cache) ---
	// The rule under test decides with NSDecision. Decision above is kept and still computed on
	// every banded request as the containment COUNTERFACTUAL, so one run yields both verdicts.
	NSDecision reuse.NamespaceDecision
	QueryLane  reuse.Lane
	QueryNS    string
}

// tryTier2 runs: unfiltered search -> tau gate -> lane + namespace -> namespace-scoped search ->
// the two-lane rule, computing the containment rule alongside it as the counterfactual.
//
// It no longer calls Retrieve: the caller runs that concurrently with the embedding and passes the
// result in, which is what turns the hit path from the SUM of those two round-trips into their
// maximum.
//
// Two searches, not one, because the namespace that scopes the second is derived from retrieval.
// The alternative -- one over-fetch filtered in Go -- needs an arbitrary fan-out constant whose
// horizon silently drops reusable entries as the cache fills (cache.NearestTier2InNamespace).
//
// Every failure degrades to a miss rather than an error. A Tier-2 outage should cost hit rate,
// not availability, and a 500 here would be a served-request outcome fitting none of
// experiment-protocol.md 4's categories -- it would leak out of both the goodput numerator and
// the shed denominator.
func (h *Handler) tryTier2(ctx context.Context, productID string, vec []float32, retrieved *ragclient.RetrieveResult, t *stageTimings) tier2Outcome {
	if vec == nil {
		return tier2Outcome{}
	}

	// PHASE 1 -- unfiltered, k=1, purely to work the tau gate. The namespace is not known yet
	// (it comes from retrieval, which happens below), so this search cannot be filtered.
	searchStart := time.Now()
	candidates, err := h.Cache.NearestTier2(ctx, vec, 1)
	t.Search = time.Since(searchStart)
	if err != nil {
		log.Printf("gateway: tier-2 search failed, degrading to MISS: %v", err)
		return tier2Outcome{}
	}
	if len(candidates) == 0 {
		return tier2Outcome{}
	}

	// The nearest entry overall. It is what the tau gate judges, and it stays the entry reported
	// on a refusal so the response can show a high similarity next to the reason it was refused.
	nearest := candidates[0]
	out := tier2Outcome{Found: true, Candidate: nearest}
	if nearest.Similarity < h.Thresholds.Tau {
		return out
	}
	// TauHigh: serve on similarity ALONE, consulting no provenance (Pre-Thesis 3.2.3 Fig 3.2).
	// Disabled by default -- see reuse.Thresholds.TauHigh for the measured reason. EnteredBand
	// stays false so experiment-protocol.md 4 can report short-circuit and band hits separately.
	if h.Thresholds.TauHigh > 0 && nearest.Similarity >= h.Thresholds.TauHigh {
		out.NSDecision = reuse.NamespaceDecision{Reuse: true, Rule: reuse.RuleSimilarityOnly}
		return out
	}
	out.EnteredBand = true

	// Retrieval already ran, concurrently with the embedding (see Ask). A nil result means it
	// failed and was logged there; degrade to MISS rather than decide on half the evidence.
	if retrieved == nil {
		return out
	}

	// The counterfactual, on the NEAREST candidate -- that is the entry the containment rule
	// would have judged, so the comparison stays apples-to-apples with the pre-existing rule.
	out.Decision = h.Thresholds.Decide(nearest.Similarity, retrieved.ChunkIDs, nearest.Entry.SourceChunkIDs)

	// The lane is read from what retrieval returned for THIS query. Never predicted from the
	// query text: a classifier error would land in the false-hit metric with no bucket to hold
	// it (ADR-018's reason for dropping the bypass classifier).
	out.QueryLane = reuse.Classify(retrieved.ChunkIDs, h.LaneBand)
	out.QueryNS = reuse.Namespace(out.QueryLane, retrieved.ChunkIDs, productID)

	// PHASE 2 -- now the namespace IS known, so ask Redis for the nearest entry INSIDE it rather
	// than over-fetching and filtering in Go. k=1 suffices: the rule accepts or refuses on
	// namespace equality, which every candidate in this result satisfies, so the most similar one
	// is the best one and the rest could only lose on tau.
	//
	// This replaces a fan-out of 10 whose horizon was a silent false-miss source -- see
	// cache.NearestTier2InNamespace. An empty namespace returns nothing, never everything.
	search2Start := time.Now()
	scoped, err := h.Cache.NearestTier2InNamespace(ctx, vec, out.QueryNS, 1)
	t.Search += time.Since(search2Start)
	if err != nil {
		log.Printf("gateway: tier-2 namespace search failed, degrading to MISS: %v", err)
		return out
	}

	// The rule still runs in reuse/ over whatever came back. The filter above is an optimisation
	// and this is the enforcement: if the two ever disagree, the Go check refuses.
	served, nsDecision := nearest, reuse.NamespaceDecision{Lane: out.QueryLane, QueryNS: out.QueryNS}
	if len(scoped) > 0 {
		c := scoped[0]
		d := h.Thresholds.DecideLane(reuse.LaneInput{
			Similarity: c.Similarity,
			QueryLane:  out.QueryLane,
			QueryNS:    out.QueryNS,
			EntryLane:  reuse.Lane(c.Entry.Lane),
			EntryNS:    c.Entry.Namespace,
		})
		if d.Reuse {
			served, nsDecision = c, d
		} else {
			nsDecision = d
		}
	}

	// The containment counterfactual for the entry actually SERVED, computed once here rather
	// than inside the decision, which would run it per candidate and discard all but this one.
	nsDecision.Overlap = reuse.Overlap(retrieved.ChunkIDs, served.Entry.SourceChunkIDs)
	out.Candidate, out.NSDecision = served, nsDecision

	// The two verdicts side by side ARE the experiment. similarity_only is the third rule
	// (config 3, GPTCache's), kept so all three are readable from one line. rule= names which
	// TERM produced the lane verdict, so a MIXED composite hit is never confused with a pure-lane
	// namespace hit when the false-hit rate is attributed per lane.
	log.Printf("gateway: cascade lane=%s ns=%s entry_lane=%s entry_ns=%s sim=%.4f\n"+
		"          ns_decision=%v (rule=%s lane_match=%v)  overlap_decision=%v (overlap=%.2f)  similarity_only=%v\n"+
		"          retrieved=%v\n          entry_sources=%v",
		out.QueryLane, out.QueryNS, served.Entry.Lane, served.Entry.Namespace, served.Similarity,
		nsDecision.Reuse, nsDecision.Rule, nsDecision.LaneMatch,
		out.Decision.Reuse, out.Decision.Overlap, out.Decision.SimilarityOnly,
		retrieved.ChunkIDs, served.Entry.SourceChunkIDs)

	return out
}
