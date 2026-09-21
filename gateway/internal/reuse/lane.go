package reuse

import "strings"

// Two-lane cache namespacing -- EXPERIMENT, see .docs/work/two-lane-cache/approvals.md.
//
// The idea this file tests: a RAG answer's own grounding says what cache namespace it belongs
// in, and the right namespace is NOT the same for every question.
//
//   - A question grounded in PRODUCT chunks ("what is the battery life of X") is answerable only
//     for X. Its namespace is the product. This is the namespace scoping production semantic
//     caches already do per tenant.
//   - A question grounded in POLICY chunks ("how long do I have to return X") has the same
//     answer for every product the policy governs. Its namespace is the policy. Scoping it by
//     product would store one entry per product for one answer, which is where a product_id
//     cache key spends capacity it did not need to.
//
//   - A question grounded in BOTH ("how long is the warranty on the EarBuds Pop 3, and what is
//     its battery life") belongs to neither namespace. data-card.md 2 pre-registers it as
//     stratum D and calls it impossible in dev-v0, because it needs the product<->policy join
//     key of ADR-024 requirement 1. It is LaneMixed here, and its namespace is the PAIR of both
//     documents -- neither alone is sufficient, as a measured false hit showed. See Namespace.
//
// Which lane a question is in is READ FROM THE GROUNDING, never predicted from the query text.
// That distinction is the point: a classifier's error would become a false-hit cause with no
// bucket in experiment-protocol.md 4's two-cause split, charged to the reuse rule -- the exact
// reason ADR-018 dropped the bypass classifier. A prefix count cannot be wrong about what
// retrieval returned.
//
// Measured on dev-v0 2026-09-06, 10 spec + 10 policy questions: PolicyFraction was 0.00 for
// every spec question and 0.40-0.80 for every policy question. Separation was total. Small
// sample, one corpus, not citable.
//
// This package stays free of Redis, gRPC and HTTP (architecture.md 2), so everything here is a
// pure function over chunk IDs.

// Lane is which regime a question falls in, decided by its grounding.
type Lane string

const (
	LaneSpec   Lane = "SPEC"
	LanePolicy Lane = "POLICY"

	// LaneMixed is stratum D of data-card.md 2: a question whose grounding SPANS product and
	// policy ("how long is the warranty on the EarBuds Pop 3 and what is its battery life").
	//
	// It exists because a single-key namespace is unsound for such a question, not merely
	// imprecise. Forced into LanePolicy it takes the rank-1 policy doc as its namespace and
	// DROPS the product entirely -- so the same mixed question about a different product shares
	// a namespace and is served the wrong spec half. That is a false hit the two-lane rule
	// CREATES and the containment rule does not have, because containment scores the whole
	// grounding set and so covers both document kinds without any lane at all.
	//
	// Its namespace is therefore the PAIR (product, policy) rather than either alone. See
	// Namespace and DecideLane.
	LaneMixed Lane = "MIXED"
)

// Chunk IDs are `{doc_id}#chunk-{ordinal}` (interfaces.md C) and doc_id carries the kind as a
// prefix.
//
// The prefix is REQUIRED by interfaces.md C as of v0.6 (ADR-032), checked at corpus-freeze time
// by data-card.md 7's gate G4, and enforced at ingestion by rag/src/rag/ingest.py:record_kind().
// It was an unstated convention until then, which mattered: a corpus without it classifies every
// question into the spec lane SILENTLY, with the lane machinery reporting plausible values.
const (
	policyPrefix  = "policy-"
	productPrefix = "product-"
)

// PolicyFraction is the share of a grounding set that is policy-grounded. It is the lane
// selector and nothing else: it is a property of ONE answer's provenance, never a comparison
// between two.
//
// That is why it survives a condition which defeats comparing two groundings: when the corpus
// holds fewer policy chunks than top_k, every policy question retrieves nearly the whole policy
// set, so containment between two policy questions saturates at ~1 and carries no information
// (measured on dev-v0: 4 policy chunks, top_k=5). A single set's COMPOSITION is unaffected by
// that -- spec questions still retrieve zero policy chunks.
func PolicyFraction(chunkIDs []string) float64 {
	if len(chunkIDs) == 0 {
		return 0
	}
	n := 0
	for _, id := range chunkIDs {
		if strings.HasPrefix(id, policyPrefix) {
			n++
		}
	}
	return float64(n) / float64(len(chunkIDs))
}

// LaneBand is the lane selector, widened from one sigma to two so LaneMixed has somewhere to
// live. Both bounds are swept, never hand-set, exactly as Tau and Theta are (rules.md #10).
//
//	policy_frac >= Hi           -> POLICY
//	Lo <= policy_frac < Hi      -> MIXED
//	policy_frac <  Lo           -> SPEC
//
// ⚠️ Lo == Hi COLLAPSES the band and reproduces the old single-sigma rule exactly: the MIXED
// interval is empty and every question lands in one of the two original lanes. That degenerate
// setting is the pre-registered baseline, and it is the default -- see cmd/gateway/main.go. The
// mixed lane is a rule change and must not switch itself on.
type LaneBand struct {
	Lo float64
	Hi float64
}

// Classify picks the lane. Inclusive at both bounds, matching Decide's inclusive theta -- a
// boundary case must behave the same way in every rule or a comparison between them measures the
// boundary convention instead of the rules.
//
// The band is consulted ONLY when the grounding actually holds both kinds of document. A
// grounding with no policy chunk cannot be mixed however Lo is set, and one with no product
// chunk likewise; deciding those structurally rather than numerically means a badly chosen Lo
// can never invent a mixed question out of a single-kind grounding.
func Classify(chunkIDs []string, band LaneBand) Lane {
	if len(chunkIDs) == 0 {
		return LaneSpec
	}
	frac := PolicyFraction(chunkIDs)
	switch {
	case frac == 0:
		return LaneSpec
	case frac == 1:
		return LanePolicy
	case frac >= band.Hi:
		return LanePolicy
	case frac >= band.Lo:
		return LaneMixed
	default:
		return LaneSpec
	}
}

// docID drops the `#chunk-{ordinal}` suffix. The namespace is the DOCUMENT, not the chunk:
// re-chunking a policy must not silently repartition the cache (interfaces.md C's re-chunking
// rule already makes that a new dataset version, but the namespace should not depend on ordinal
// even within one version).
func docID(chunkID string) string {
	if i := strings.IndexByte(chunkID, '#'); i >= 0 {
		return chunkID[:i]
	}
	return chunkID
}

// Namespace derives the cache partition from the grounding, plus request metadata in the spec
// lane only.
//
//	POLICY -> doc_id of the HIGHEST-RANKED policy chunk.
//	SPEC   -> productID from the request; falls back to the highest-ranked product chunk.
//	MIXED  -> "{product}|{policy}", both components required.
//
// ⚠️ MIXED returned "" and deferred to containment until 2026-09-06. That was WRONG and the run
// that showed it is recorded in .docs/work/two-lane-cache/approvals.md. Containment cannot decide
// this lane, for a structural reason no threshold reaches: a mixed grounding is roughly four
// product chunks to one policy chunk, so the single chunk carrying the entire difference between
// "how long do I have to return it" and "how long is the warranty" is 1/5 of the denominator.
// Measured, same product, same cached entry:
//
//	paraphrase of the return question   -> overlap 0.80   reuse is CORRECT
//	the warranty question               -> overlap 0.80   reuse is a FALSE HIT
//
// Identical scores, opposite correct answers, and at top-5 the overlap granularity is 0.2 -- so
// no theta separates them. The composite key does: the two differ precisely in their rank-1
// policy doc.
//
// The objection this reverses is real but is the lesser harm. A composite key over-specifies: a
// stray policy chunk moves an entry to a namespace no paraphrase reaches, and rank-1 policy
// drifts across paraphrases the way rank-1 product does, with no request-metadata equivalent to
// pin it. Both cost false MISSES. Containment in this lane cost false HITS, which is the side
// the delta budget is spent on (proposal 10).
//
// Rank matters, and set membership does not. On dev-v0 both "return my headphones" and "return
// my sofa" retrieve BOTH category return policies, so the sets are indistinguishable -- but the
// retriever ranks the right one first in each case, so rank-1 separates them. Using the set here
// would inherit exactly the saturation PolicyFraction avoids.
//
// productID wins over rank-1 in the spec lane because rank-1 is unstable across paraphrases when
// a catalog holds near-duplicate variants: measured on dev-v0, "specifications of the EarBuds
// Pop 3" ranked product-headphones-04 (the *Pro* variant) first while "key features of the
// EarBuds Pop 3" ranked product-headphones-03. Two paraphrases of one question, two namespaces,
// and one of them the wrong product. Request metadata does not drift like that -- which is the
// honest half of the product_id objection ADR-028 rejected wholesale.
//
// Returns "" when the grounding offers no chunk of the needed kind -- and in MIXED, when EITHER
// component is missing, because half a composite key would silently widen to "any policy" or "any
// product". Callers must treat an empty namespace as UNMATCHABLE rather than as a wildcard; see
// MatchNamespace.
func Namespace(lane Lane, chunkIDs []string, productID string) string {
	switch lane {
	case LaneSpec:
		return specComponent(chunkIDs, productID)
	case LanePolicy:
		return firstDocIDWithPrefix(chunkIDs, policyPrefix)
	case LaneMixed:
		product := specComponent(chunkIDs, productID)
		policy := firstDocIDWithPrefix(chunkIDs, policyPrefix)
		if product == "" || policy == "" {
			return ""
		}
		return product + mixedSeparator + policy
	default:
		return ""
	}
}

// mixedSeparator cannot appear in a doc_id (interfaces.md C's slug alphabet), so the composite is
// unambiguous and, incidentally, can never equal a SPEC or POLICY namespace -- the lanes cannot
// collide through the namespace even before DecideLane's explicit lane check.
const mixedSeparator = "|"

func specComponent(chunkIDs []string, productID string) string {
	if productID != "" {
		return productID
	}
	return firstDocIDWithPrefix(chunkIDs, productPrefix)
}

func firstDocIDWithPrefix(chunkIDs []string, prefix string) string {
	for _, id := range chunkIDs {
		if strings.HasPrefix(id, prefix) {
			return docID(id)
		}
	}
	return ""
}

// MatchNamespace is the lane rule's gate. An empty namespace on EITHER side never matches: an
// answer whose grounding could not be partitioned must not become reusable by everything, which
// is what treating "" as a wildcard would do.
func MatchNamespace(queryNS, entryNS string) bool {
	return queryNS != "" && queryNS == entryNS
}

// NamespaceDecision is the two-lane rule's verdict. It is a separate type from Decision, not a
// field added to it, so that a run can carry BOTH verdicts for the same request and neither can
// be mistaken for the other in the log.
type NamespaceDecision struct {
	Reuse   bool
	Lane    Lane
	QueryNS string
	EntryNS string
	Match   bool

	// Rule names which TERM produced Reuse, so a run can tell a namespace hit from a
	// containment hit without re-deriving it from Lane. Without this the mixed lane's hits and
	// the pure lanes' hits are indistinguishable in the log, and the fallback's contribution to
	// the false-hit rate cannot be attributed -- which would put it outside
	// experiment-protocol.md 4's two-cause split, the same defect ADR-018 rejected a classifier
	// for.
	Rule string

	// EntryLane and LaneMatch are read only on the MIXED path. On the pure lanes they stay zero,
	// because the namespace term never computes them.
	EntryLane Lane
	LaneMatch bool

	// Overlap is the containment COUNTERFACTUAL for the candidate actually served: what the rule
	// this one replaced would have scored. DecideLane does not compute it -- the cascade fills it
	// in once, for the served candidate only. Computing it inside the decision would run it for
	// every candidate in the fan-out and discard all but one, and containment over two chunk sets
	// allocates.
	//
	// It must still be captured at DECISION time, because it cannot be reconstructed later against
	// cache state that no longer exists -- the same argument interfaces.md H makes for
	// similarity_only_decision, and what lets a run re-derive the 2026-09-06 finding rather than
	// cite a session log.
	Overlap float64
}

const (
	RuleNamespace = "namespace"
	RuleComposite = "composite"

	// RuleSimilarityOnly marks a TauHigh short-circuit: served WITHOUT consulting provenance.
	// It must be distinguishable in the log from the other two, because a false hit produced this
	// way was not the provenance rule's fault -- the provenance rule never ran -- and charging it
	// to that rule is exactly the mis-attribution experiment-protocol.md 4's two-cause split
	// exists to prevent.
	RuleSimilarityOnly = "similarity_only"
)

// DecideNamespace applies similarity >= tau AND namespace equality.
//
// There is deliberately no containment term. On the cases measured 2026-09-06 namespace equality
// and containment disagreed four times and namespace equality was right every time -- notably on
// two cases containment cannot get right at all: same-policy-different-product (containment
// refuses a safe reuse, costing capacity) and same-product-different-policy (containment reuses
// and is wrong). Containment is still computed on every request as the counterfactual baseline;
// see Thresholds.Decide and the cascade's log line.
func (t Thresholds) DecideNamespace(similarity float64, lane Lane, queryNS, entryNS string) NamespaceDecision {
	match := MatchNamespace(queryNS, entryNS)
	return NamespaceDecision{
		Reuse:   similarity >= t.Tau && match,
		Lane:    lane,
		QueryNS: queryNS,
		EntryNS: entryNS,
		Match:   match,
		Rule:    RuleNamespace,
	}
}

// LaneInput is everything the two-lane rule reads about one (query, candidate) pair. A struct
// rather than five positional arguments because two of them are Lane and two are string --
// adjacent same-typed parameters a caller can silently transpose, which here would mean comparing
// a namespace against itself and reporting a plausible verdict.
//
// It carries no chunk lists. The rule reads only the DERIVED namespace and lane, never the
// grounding they came from: the derivation happens once per request in Classify and Namespace,
// and re-deriving it per candidate would be the same work repeated across the fan-out.
type LaneInput struct {
	Similarity float64

	QueryLane Lane
	QueryNS   string

	EntryLane Lane
	EntryNS   string
}

// DecideLane is the two-lane rule including its stratum-D fallback. It is the entry point the
// cascade calls; DecideNamespace remains the pure-lane term it delegates to.
//
//	SPEC | POLICY -> similarity >= tau AND namespace equality                  (unchanged)
//	MIXED         -> similarity >= tau AND entry is ALSO mixed AND COMPOSITE namespace equality
//
// The MIXED arm is the same shape as the pure lanes; only the key is a pair. Containment was
// tried here first and measurably failed -- see Namespace's comment for the two requests that
// scored an identical 0.80 and needed opposite verdicts.
//
// The lane-equality term is kept even though a composite namespace can never equal a SPEC or
// POLICY one by construction. It costs one comparison and it makes the disjointness an ENFORCED
// invariant rather than an emergent property of a string format: a later change to mixedSeparator
// or to how a component is derived would otherwise silently reopen cross-lane reuse, and nothing
// would fail. It also earns its keep directly -- in the 2026-09-06 run it was what refused a
// spec-only entry at similarity 0.9244 that the containment rule accepted.
//
// The three lanes therefore partition the cache into three non-interacting regions, which is what
// makes their false-hit rates separately attributable to experiment-protocol.md 4's two causes.
func (t Thresholds) DecideLane(in LaneInput) NamespaceDecision {
	if in.QueryLane != LaneMixed {
		d := t.DecideNamespace(in.Similarity, in.QueryLane, in.QueryNS, in.EntryNS)
		d.EntryLane = in.EntryLane
		return d
	}

	laneMatch := in.EntryLane == LaneMixed
	match := MatchNamespace(in.QueryNS, in.EntryNS)
	return NamespaceDecision{
		Reuse:     in.Similarity >= t.Tau && laneMatch && match,
		Lane:      in.QueryLane,
		QueryNS:   in.QueryNS,
		EntryNS:   in.EntryNS,
		Match:     match,
		Rule:      RuleComposite,
		EntryLane: in.EntryLane,
		LaneMatch: laneMatch,
	}
}
