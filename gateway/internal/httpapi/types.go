package httpapi

// askRequest is POST /ask's request body (interfaces.md §A).
type askRequest struct {
	Question string `json:"question"`

	// ProductID is the two-lane experiment's only request-side addition
	//. Optional, and only the SPEC lane reads it: a question
	// grounded in product chunks is answerable for one product, and the page the question was
	// asked on already knows which -- that is how production assistants are actually invoked.
	// The POLICY lane deliberately ignores it, because scoping a policy answer by product is
	// what spends capacity on one answer per product.
	//
	// Contract: interfaces.md §A v0.6, added by the doc-id kind prefix. In the SPEC lane it is a stabiliser: a
	// namespace derived from the rank-1 product document drifts across paraphrases, which cost
	// one false hit and one false miss in a single measured run.
	//
	// ⚠️ BYPASS 2026-09-09: it is ALSO now part of the Tier-1 key (cache.Key), which reverses
	// the explicit "product_id as a key -- Rejected". That decision recorded a real cost --
	// it moves work into the key and restates C1's claim as "provenance beats similarity given
	// product scoping" -- and was reversed here without the owed superseding ADR, for an urgent
	// MVP demo.
	ProductID string `json:"product_id,omitempty"`
}

// askResponse is POST /ask's success response (interfaces.md §A). similarity and
// source_overlap are pointers, not `omitempty`, so the JSON literally renders `null` on
// TIER1_HIT/MISS -- the contract calls out showing them side by side as the whole
// observability point of the pair (a high-similarity, low-overlap miss is the lookalike trap
// C1 exists to catch), so `null` must render, not be silently dropped.
type askResponse struct {
	Answer        string   `json:"answer"`
	Cache         string   `json:"cache"` // TIER1_HIT | TIER2_HIT | MISS | BYPASS
	LatencyMs     int64    `json:"latency_ms"`
	Similarity    *float64 `json:"similarity"`
	SourceOverlap *float64 `json:"source_overlap"`
	Sources       []string `json:"sources"`
	ModelUsed     *string  `json:"model_used"`
	RequestID     string   `json:"request_id"`

	// --- two-lane experiment ---

	// Lane and Namespace are what the rule actually decided on. Rendered so the decision is
	// inspectable from the response alone, the same reason similarity and source_overlap are.
	Lane      string `json:"lane,omitempty"`
	Namespace string `json:"namespace,omitempty"`

	// ReuseRule names which TERM of the lane rule decided: "namespace" in the SPEC and POLICY
	// lanes, "composite" in MIXED, where the key is the PAIR (product, policy) because a question
	// grounded in both has no single namespace (reuse.DecideLane). Recorded because otherwise a
	// MIXED hit and a pure-lane hit are indistinguishable in the numbers, and the mixed lane's
	// share of the false-hit rate could not be attributed to it.
	ReuseRule string `json:"reuse_rule,omitempty"`

	// OverlapDecision is the COUNTERFACTUAL: what the containment rule (Thresholds.Decide,
	// the pre-existing C1 rule) would have decided on the same request. It must be captured at
	// decision time -- it cannot be reconstructed later against cache state that no longer
	// exists, which is the same argument interfaces.md §H makes for similarity_only_decision.
	// Carrying both is what makes the two rules comparable without a second run.
	OverlapDecision *bool `json:"overlap_decision"`
}

const (
	cacheTier1Hit = "TIER1_HIT"
	cacheTier2Hit = "TIER2_HIT"
	cacheMiss     = "MISS"

	// Outcomes that are NOT in interfaces.md A's cache field, used only in the evaluation log so
	// that every request lands in exactly one bucket. the evaluation counts a shed as
	// graceful degradation rather than an error; the other two are neither served nor shed, and
	// leaving them blank would make them indistinguishable from a lost record.
	cacheShed      = "SHED"
	cacheAbandoned = "ABANDONED"
	cacheGenFailed = "GENERATION_FAILED"
)
