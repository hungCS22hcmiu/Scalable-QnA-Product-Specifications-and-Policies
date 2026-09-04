package httpapi

import (
	"encoding/json"
	"log"
	"net/http"
	"time"

	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/ragclient"
)

// topKServerDefault is deliberately 0, not 5. The proto makes Go the sender of top_k, but Go
// has no config pinned to ADR-014, so a literal here would keep sending the old value the day
// ADR-014 changes -- silently, since both sides would still work. Sending 0 makes the RAG
// service resolve it from rag/src/rag/config.py's TOP_K, leaving exactly one source of truth
// for the frozen value (impact.md lead risk; interfaces.md B: "default 5; pinned per run").
const topKServerDefault = 0

// Handler serves POST /ask: cache.Get -> miss -> ragclient.Answer -> cache.Put. Single call
// site, so W16's admission control has exactly one place to insert later
// (architecture-guardrails.md: admission/ must be the sole place a permit is acquired --
// no miss path may bypass it).
type Handler struct {
	Cache *cache.Store
	RAG   *ragclient.Client
}

func NewHandler(c *cache.Store, r *ragclient.Client) *Handler {
	return &Handler{Cache: c, RAG: r}
}

func (h *Handler) Ask(w http.ResponseWriter, r *http.Request) {
	start := time.Now()

	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req askRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.Question == "" {
		http.Error(w, "invalid request: expected {\"question\": \"...\"}", http.StatusBadRequest)
		return
	}

	requestID := cache.NewEntryID()
	ctx := r.Context()

	if entry, hit, err := h.Cache.Get(ctx, req.Question); err != nil {
		http.Error(w, "cache lookup failed: "+err.Error(), http.StatusInternalServerError)
		return
	} else if hit {
		modelUsed := entry.ModelUsed
		writeJSON(w, askResponse{
			Answer:        entry.Answer,
			Cache:         cacheTier1Hit,
			LatencyMs:     time.Since(start).Milliseconds(),
			Similarity:    nil,
			SourceOverlap: nil,
			Sources:       entry.SourceChunkIDs,
			ModelUsed:     &modelUsed,
			RequestID:     requestID,
		})
		return
	}

	result, err := h.RAG.Answer(ctx, req.Question, topKServerDefault)
	if err != nil {
		http.Error(w, "generation failed: "+err.Error(), http.StatusBadGateway)
		return
	}

	// A failed write-back must NOT fail the request. The generation already succeeded, and it is
	// the most expensive resource in the system -- discarding it because a cache write failed
	// spends it for nothing, which is backwards on this thesis's own premise. It also produces a
	// served-request outcome that is none of TIER1_HIT | TIER2_HIT | MISS | BYPASS | 503-shed,
	// the only categories experiment-protocol.md 4's goodput/shed split accounts for, so a
	// nonzero rate of it would leak out of both the goodput numerator and the shed denominator.
	// Serve the answer, count it as the MISS it was, and surface the failure on its own channel.
	// W9's per-request evaluation log (interfaces.md H) gives this a durable bucket; until then
	// stderr is the honest place for it.
	if err := h.Cache.Put(ctx, req.Question, cache.Entry{
		Answer:         result.Text,
		SourceChunkIDs: result.SourceChunkIDs,
		ModelUsed:      result.ModelUsed,
	}); err != nil {
		log.Printf("gateway: write-back failed for request_id=%s: %v", requestID, err)
	}

	modelUsed := result.ModelUsed
	writeJSON(w, askResponse{
		Answer:        result.Text,
		Cache:         cacheMiss,
		LatencyMs:     time.Since(start).Milliseconds(),
		Similarity:    nil,
		SourceOverlap: nil,
		Sources:       result.SourceChunkIDs,
		ModelUsed:     &modelUsed,
		RequestID:     requestID,
	})
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}
