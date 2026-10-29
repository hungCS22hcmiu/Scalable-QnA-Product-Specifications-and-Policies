package httpapi

import (
	"context"
	"fmt"
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

// tier2Outcome is returned even when the candidate is REFUSED. A candidate below tau carries its
// similarity and no overlap: the containment counterfactual is computed only for a candidate that
// cleared tau. A candidate that cleared tau and was then refused by the support gate carries both,
// so a SUPPORT refusal is a MISS with an overlap (interfaces.md §A v0.13). A lookalike from another
// namespace is a plain MISS with no candidate at all -- the scoped search never returns it.
type tier2Outcome struct {
	Found bool
	// EnteredBand: a candidate cleared tau. It no longer equals TIER2_HIT: the support gate can refuse
	// a candidate that is in the band (cause SUPPORT or NOT_SCORED). A candidate in the band that the
	// lane rule refused is the alarm: the Redis TAG filter and Go's MatchNamespace disagree (cause
	// NAMESPACE).
	EnteredBand bool
	Candidate   cache.Candidate
	Decision    reuse.Decision

	// SearchFailed is set when the namespace-scoped Tier-2 search returned an error. The request still
	// degrades to a MISS with no cause, exactly like a cold-cache miss, so this flag is the only trace:
	// handler.go copies it into the record's tier2_search_failed (interfaces.md §H rule 12), and a run
	// with any such record is not admissible.
	SearchFailed bool

	// InvalidatedEntryID is set, with Found false, when the nearest candidate's entry had been
	// invalidated by the dependency map (C2). The candidate is dropped BEFORE it is judged, so no
	// cause is set and the request is a plain MISS (interfaces.md §H v0.17).
	InvalidatedEntryID string

	// --- two-lane experiment ---
	// NSDecision is the lane rule's verdict on the candidate. It is NOT the serve decision any more:
	// the support gate can still refuse a candidate it reused. Serve on Served. Decision above is
	// the containment COUNTERFACTUAL, computed on every banded request, so one run yields both
	// verdicts.
	NSDecision reuse.NamespaceDecision
	QueryLane  reuse.Lane
	QueryNS    string

	// --- the support gate and the refusal cause (item 2.3) ---
	// Cause is interfaces.md §H's refusal_cause for a JUDGED candidate, and "" (rendered null) when no
	// candidate was judged: no embedding or retrieval, no chunks, an empty namespace, a search error,
	// or nothing in the query's namespace. A cold cache is therefore null, never NAMESPACE.
	Cause string
	// Support holds both arms' verdicts when the gate is on and the candidate cleared the lane rule and
	// tau; it is nil with the gate off (item 2.4), whatever the candidate. Non-nil with Scored() false
	// means a stale server: the caller logs null for the values and the cause says why.
	Support *reuse.SupportResult
	// Served is the ONLY serve decision: Cause == NONE. It is never "no arm refused", because an
	// unscored result does not refuse (reuse.Judgement.Served).
	Served bool
}

// tryTier2 runs: lane + namespace -> one namespace-scoped search -> the two-lane rule, computing
// the containment rule alongside it as the counterfactual when the candidate cleared tau, then
// reuse.Thresholds.Judge, which adds the support gate and returns the ONE refusal cause. The served
// rule is therefore similarity AND namespace AND support with the gate on, and similarity AND namespace
// with it off (h.SupportGate; interfaces.md §H v0.14, ADR-009, ADR-010). The query text is not a
// parameter, so the gate cannot read it.
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

	// A retrieval with NO chunks has no evidence, so it cannot ground a hit. Stopped here, before any
	// namespace is derived: the SPEC lane's namespace falls back to the request's product ID when
	// there is no chunk (reuse.Namespace), so without this guard a zero-chunk retrieval searched,
	// matched an entry in that namespace, and was served with nothing behind the decision. It is the
	// zero-chunk hole items 2.1 and 2.2 left to this item. It holds for BOTH arms of configuration 4:
	// it sits before the gate, not inside it, and it is not in reuse.Namespace, which the write path
	// also calls (handler.go) and which would change an entry's partition. No candidate is judged, so
	// the cause is null; offline this reads as retrieved_chunk_ids null with a non-null dataset epoch.
	if len(retrieved.ChunkIDs) == 0 {
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
		out.SearchFailed = true
		return out
	}
	if len(scoped) == 0 {
		return out
	}

	// The rule still runs in reuse/ over whatever came back. The filter above is an optimisation
	// and this is the enforcement: if the two ever disagree, the Go check refuses.
	c := scoped[0]

	// C2's hit-path check, after the Redis read (see Ask's Tier-1 check). An invalidated candidate is
	// dropped here, before DecideLane: it is not judged, so it earns no refusal cause and the request is
	// a MISS with refusal_cause null. A promoted Tier-1 key shares this entry_id, so it is refused too.
	if h.Deps != nil && h.Deps.Invalidated(c.Entry.EntryID) {
		out.InvalidatedEntryID = c.Entry.EntryID
		return out
	}

	out.Found, out.Candidate = true, c
	out.NSDecision = h.Thresholds.DecideLane(reuse.LaneInput{
		Similarity: c.Similarity,
		QueryLane:  out.QueryLane,
		QueryNS:    out.QueryNS,
		EntryLane:  reuse.Lane(c.Entry.Lane),
		EntryNS:    c.Entry.Namespace,
	})

	// The band, written in the positive form so that a NaN similarity stays out of it, agreeing
	// with DecideLane's >=. The containment counterfactual is computed on the candidate the lane rule
	// judged, once. It is the rule configuration 4 would apply with the support gate off AND theta
	// served, which it does not (F-K): it is a logged counterfactual, never a serve decision.
	if c.Similarity >= h.Thresholds.Tau {
		out.EnteredBand = true
		out.Decision = h.Thresholds.Decide(c.Similarity, retrieved.ChunkIDs, c.Entry.SourceChunkIDs)
		out.NSDecision.Overlap = out.Decision.Overlap
	}

	// The cause, and the support gate behind it. THIS request's evidence goes in -- retrieved.Texts
	// and retrieved.ChunkIDs -- and never c.Entry.SourceChunkIDs: with the entry's IDs a stale server
	// (chunk IDs, no text) would read as "scored 0" instead of "not scored". The cached answer is
	// c.Entry.Answer; the query text is nowhere in this call. The first argument is the gate's arm
	// (item 2.4): h.SupportGate is the same field that labels the record, so what ran and what the log
	// says it ran cannot differ. With GateOff the gate does not run and retrieved.Texts is not read.
	j := h.Thresholds.Judge(h.SupportGate, out.NSDecision, c.Similarity, c.Entry.Answer, retrieved.Texts, retrieved.ChunkIDs)
	out.Cause, out.Support, out.Served = j.Cause, j.Support, j.Served()

	// The two verdicts side by side ARE the experiment. rule= names which TERM judged the lane
	// verdict, so a MIXED composite hit is never confused with a pure-lane namespace hit when the
	// false-hit rate is attributed per lane. cause= is the one value that reaches the log.
	log.Printf("gateway: cascade lane=%s ns=%s entry_lane=%s entry_ns=%s sim=%.4f\n"+
		"          ns_decision=%v (rule=%s lane_match=%v)  band=%v overlap_decision=%v (overlap=%.2f)\n"+
		"          cause=%s gate=%s support=%s\n"+
		"          retrieved=%v\n          entry_sources=%v",
		out.QueryLane, out.QueryNS, c.Entry.Lane, c.Entry.Namespace, c.Similarity,
		out.NSDecision.Reuse, out.NSDecision.Rule, out.NSDecision.LaneMatch,
		out.EnteredBand, out.Decision.Reuse, out.Decision.Overlap,
		out.Cause, h.SupportGate, supportSummary(out.Support),
		retrieved.ChunkIDs, c.Entry.SourceChunkIDs)

	return out
}

// supportSummary renders the gate's verdicts for the cascade's log line. It is a log line only; the
// evaluation log's fields are filled from the Support pointer in handler.go.
func supportSummary(s *reuse.SupportResult) string {
	switch {
	case s == nil:
		return "not run"
	case !s.Scored():
		return "NOT SCORED (chunk IDs without evidence text)"
	}
	return fmt.Sprintf("lex=%.4f (of %d) numeric_ok=%v (unsupported=%d unreadable=%d unitless=%d)",
		s.Lex.Score, s.Lex.ContentTokenCount, s.Numeric.Admits(),
		s.Numeric.Unsupported, s.Numeric.Unreadable, s.Numeric.Unitless)
}
