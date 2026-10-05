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
// (docs/architecture.md 2). So: reuse/ owns the DECISION, this file owns the PLUMBING.

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

	// Search is the one namespace-scoped vector search. It stays zero -- rendered null -- when no
	// search ran: an embedding or a retrieval failed, or the query's namespace came out empty.
	Search time.Duration
	// Overlap is the Retrieve RPC span. Retrieval runs concurrently with the embedding for every
	// Tier-1 miss, so this is non-zero whether or not a candidate cleared tau. Read EnteredBand --
	// not this -- to tell a banded request from one that was not.
	Overlap time.Duration
}

// tier2Outcome is returned even when the rule REFUSES. A refusal carries its similarity, never an
// overlap: the containment counterfactual is computed only for a candidate that cleared tau, and
// while the served rule is similarity AND namespace that candidate is always served. A lookalike
// from another namespace is a plain MISS -- the scoped search never returns it (interfaces.md §A).
type tier2Outcome struct {
	Found bool
	// EnteredBand: a same-namespace candidate cleared tau. While the served rule is similarity AND
	// namespace this equals TIER2_HIT; the two disagreeing means the Redis TAG filter and Go's
	// MatchNamespace disagree.
	EnteredBand bool
	Candidate   cache.Candidate
	Decision    reuse.Decision

	// --- two-lane experiment ---
	// The rule under test decides with NSDecision. Decision above is the containment
	// COUNTERFACTUAL, computed on every banded request, so one run yields both verdicts.
	NSDecision reuse.NamespaceDecision
	QueryLane  reuse.Lane
	QueryNS    string
}

// tryTier2 runs: lane + namespace -> one namespace-scoped search -> the two-lane rule, computing
// the containment rule alongside it as the counterfactual when the candidate cleared tau.
//
// It does not call Retrieve: the caller runs that concurrently with the embedding and passes the
// result in, which is what turns the hit path from the SUM of those two round-trips into their
// maximum.
//
// ONE search, and only after retrieval, because the namespace that scopes it is derived from
// retrieval. The unfiltered search that used to run first was retired (interfaces.md v0.9,
// ADR-004): it searched outside the namespace the rule enforces, so it could only report an entry
// the rule would refuse. The alternative to a scoped search -- one over-fetch filtered in Go --
// needs an arbitrary fan-out constant whose horizon silently drops reusable entries as the cache
// fills (cache.NearestTier2InNamespace).
//
// Every failure degrades to a miss rather than an error. A Tier-2 outage should cost hit rate,
// not availability, and a 500 here would be a served-request outcome fitting none of
// the evaluation's categories -- it would leak out of both the goodput numerator and
// the shed denominator.
func (h *Handler) tryTier2(ctx context.Context, productID string, vec []float32, retrieved *ragclient.RetrieveResult, t *stageTimings) tier2Outcome {
	// Retrieval is checked FIRST, before anything derives a namespace. Deriving one without it
	// would let the spec lane fall back to productID alone and serve an entry with no evidence
	// behind the decision.
	if vec == nil || retrieved == nil {
		return tier2Outcome{}
	}

	// The lane is read from what retrieval returned for THIS query. Never predicted from the
	// query text: a classifier error would land in the false-hit metric with no bucket to hold
	// it (the reason for dropping the bypass classifier).
	out := tier2Outcome{QueryLane: reuse.Classify(retrieved.ChunkIDs, h.LaneBand)}
	out.QueryNS = reuse.Namespace(out.QueryLane, retrieved.ChunkIDs, productID)

	// An empty namespace matches nothing, so there is nothing to search. Return before the call
	// rather than let the store answer it: a timed no-op would leave a span of a few microseconds
	// that msPtr renders as a measurement instead of null.
	if out.QueryNS == "" {
		return out
	}

	// Ask Redis for the nearest entry INSIDE the namespace rather than over-fetching and filtering
	// in Go. k=1 suffices: the rule accepts or refuses on namespace equality, which every
	// candidate in this result satisfies, so the most similar one is the best one and the rest
	// could only lose on tau.
	searchStart := time.Now()
	scoped, err := h.Cache.NearestTier2InNamespace(ctx, vec, out.QueryNS, 1)
	t.Search = time.Since(searchStart)
	if err != nil {
		log.Printf("gateway: tier-2 namespace search failed, degrading to MISS: %v", err)
		return out
	}
	if len(scoped) == 0 {
		return out
	}

	// The rule still runs in reuse/ over whatever came back. The filter above is an optimisation
	// and this is the enforcement: if the two ever disagree, the Go check refuses.
	c := scoped[0]
	out.Found, out.Candidate = true, c
	out.NSDecision = h.Thresholds.DecideLane(reuse.LaneInput{
		Similarity: c.Similarity,
		QueryLane:  out.QueryLane,
		QueryNS:    out.QueryNS,
		EntryLane:  reuse.Lane(c.Entry.Lane),
		EntryNS:    c.Entry.Namespace,
	})

	// The band, written in the positive form so that a NaN similarity stays out of it, agreeing
	// with DecideLane's >=. The counterfactual is configuration 4's support-off rule, computed on
	// the candidate the served rule judged, once.
	if c.Similarity >= h.Thresholds.Tau {
		out.EnteredBand = true
		out.Decision = h.Thresholds.Decide(c.Similarity, retrieved.ChunkIDs, c.Entry.SourceChunkIDs)
		out.NSDecision.Overlap = out.Decision.Overlap
	}

	// The two verdicts side by side ARE the experiment. rule= names which TERM judged the lane
	// verdict, so a MIXED composite hit is never confused with a pure-lane namespace hit when the
	// false-hit rate is attributed per lane.
	log.Printf("gateway: cascade lane=%s ns=%s entry_lane=%s entry_ns=%s sim=%.4f\n"+
		"          ns_decision=%v (rule=%s lane_match=%v)  band=%v overlap_decision=%v (overlap=%.2f)\n"+
		"          retrieved=%v\n          entry_sources=%v",
		out.QueryLane, out.QueryNS, c.Entry.Lane, c.Entry.Namespace, c.Similarity,
		out.NSDecision.Reuse, out.NSDecision.Rule, out.NSDecision.LaneMatch,
		out.EnteredBand, out.Decision.Reuse, out.Decision.Overlap,
		retrieved.ChunkIDs, c.Entry.SourceChunkIDs)

	return out
}
