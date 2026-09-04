package httpapi

// askRequest is POST /ask's request body (interfaces.md §A).
type askRequest struct {
	Question string `json:"question"`
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
}

const (
	cacheTier1Hit = "TIER1_HIT"
	cacheMiss     = "MISS"
)
