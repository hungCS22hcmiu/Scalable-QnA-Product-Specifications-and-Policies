package httpapi

import (
	"encoding/json"
	"log"
	"net/http"
	"time"

	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/embed"
	"github.com/hung/thesis/gateway/internal/ragclient"
	"github.com/hung/thesis/gateway/internal/reuse"
)

// topKServerDefault is deliberately 0, not 5. The proto makes Go the sender of top_k, but Go
// has no config pinned to ADR-014, so a literal here would keep sending the old value the day
// ADR-014 changes -- silently, since both sides would still work. Sending 0 makes the RAG
// service resolve it from rag/src/rag/config.py's TOP_K, leaving exactly one source of truth
// for the frozen value (impact.md lead risk; interfaces.md B: "default 5; pinned per run").
const topKServerDefault = 0

// modelUsedConstant mirrors rag/src/rag/config.py's LLM_MODEL_ID.
//
// It is a Go-side literal rather than a stored field because interfaces.md A defines model_used
// as "Constant (qwen3.5-2b, ADR-021) — retained for forward compatibility with routing (future
// work)", and the D Tier-2 schema has no model_used field to read it from. The alternatives were
// both worse: adding a field to a frozen schema needs an ADR, and fetching the co-written Tier-1
// record on every Tier-2 hit puts an extra Redis round-trip on the path that bounds mu_hit.
//
// The drift risk is real but bounded: routing was rejected (ADR-011), so this changes only if the
// generation model itself changes -- which already requires an ADR that would touch both sides.
const modelUsedConstant = "qwen3.5-2b"

// Handler serves POST /ask: cache.Get -> miss -> ragclient.Answer -> cache.Put. Single call
// site, so W16's admission control has exactly one place to insert later
// (architecture-guardrails.md: admission/ must be the sole place a permit is acquired --
// no miss path may bypass it).
//
// The cascade is orchestrated HERE rather than inside cache/ or reuse/. httpapi is the leftmost
// package and may import rightward; putting it here is what keeps reuse/ free of Redis, gRPC and
// HTTP so C1 stays falsifiable in isolation (docs/design/architecture.md 2).
type Handler struct {
	Cache      *cache.Store
	RAG        *ragclient.Client
	Embed      *embed.Client
	Thresholds reuse.Thresholds
}

func NewHandler(c *cache.Store, r *ragclient.Client, e *embed.Client, t reuse.Thresholds) *Handler {
	return &Handler{Cache: c, RAG: r, Embed: e, Thresholds: t}
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

	// --- Tier 1: exact match. No vectors, no judgement, just sha256 equality. ---
	var timings stageTimings
	t1Start := time.Now()
	entry, hit, err := h.Cache.Get(ctx, req.Question)
	timings.Tier1 = time.Since(t1Start)
	if err != nil {
		http.Error(w, "cache lookup failed: "+err.Error(), http.StatusInternalServerError)
		return
	}
	if hit {
		modelUsed := entry.ModelUsed
		log.Printf("gateway: request_id=%s cache=TIER1_HIT t_tier1=%s", requestID, timings.Tier1)
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

	// --- Embed once. Used for the Tier-2 lookup and, on a miss, for write-back. ---
	// This round-trip sits on the hit path and bounds mu_hit (interfaces.md F), which is why
	// its span is timed separately rather than folded into a single total.
	embedStart := time.Now()
	vec, err := h.Embed.Query(ctx, req.Question)
	timings.Embed = time.Since(embedStart)
	if err != nil {
		// Degrade to MISS rather than fail. A Tier-2 outage should cost hit rate, not
		// availability, and a 500 here is an outcome that fits none of the categories
		// experiment-protocol.md 4 counts.
		log.Printf("gateway: request_id=%s embed failed, degrading to MISS: %v", requestID, err)
		vec = nil
	}

	// --- Tier 2: nearest neighbour, then the containment rule. ---
	t2 := h.tryTier2(ctx, req.Question, vec, &timings)

	// Both numbers travel to the response whether the rule accepted or refused. On a refusal
	// they are the evidence FOR the refusal, which is the one thing the demo must show.
	var similarity, sourceOverlap *float64
	if t2.Found {
		s := t2.Candidate.Similarity
		similarity = &s
	}
	if t2.EnteredBand {
		o := t2.Decision.Overlap
		sourceOverlap = &o
	}

	if t2.Decision.Reuse {
		modelUsed := modelUsedConstant
		if err := h.Cache.BumpHitCount(ctx, t2.Candidate.Entry.EntryID); err != nil {
			log.Printf("gateway: hit_count bump failed for %s: %v", t2.Candidate.Entry.EntryID, err)
		}
		log.Printf("gateway: request_id=%s cache=TIER2_HIT t_tier1=%s t_embed=%s t_search=%s t_overlap=%s",
			requestID, timings.Tier1, timings.Embed, timings.Search, timings.Overlap)
		writeJSON(w, askResponse{
			Answer:        t2.Candidate.Entry.Answer,
			Cache:         cacheTier2Hit,
			LatencyMs:     time.Since(start).Milliseconds(),
			Similarity:    similarity,
			SourceOverlap: sourceOverlap,
			Sources:       t2.Candidate.Entry.SourceChunkIDs,
			ModelUsed:     &modelUsed,
			RequestID:     requestID,
		})
		return
	}

	// --- Miss: generate, then write BOTH tiers from one identity. ---
	result, err := h.RAG.Answer(ctx, req.Question, topKServerDefault)
	if err != nil {
		http.Error(w, "generation failed: "+err.Error(), http.StatusBadGateway)
		return
	}

	// entry_id is minted here, not inside Put, so both tiers carry the SAME id. Divergence
	// would break the Phase-2 purge, which finds t2 by entry_id and t1 through its t1_key.
	entryID := cache.NewEntryID()
	t1Key := cache.Key(cache.Normalize(req.Question))

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
		EntryID:        entryID,
	}); err != nil {
		log.Printf("gateway: tier-1 write-back failed for request_id=%s: %v", requestID, err)
	}

	if vec != nil {
		if err := h.Cache.PutTier2(ctx, cache.Tier2Entry{
			EntryID:        entryID,
			QueryText:      req.Question,
			Answer:         result.Text,
			SourceChunkIDs: result.SourceChunkIDs,
			T1Key:          t1Key,
			// Stored, not acted on. The epoch GUARD (discard write-back if the epoch advanced)
			// is Phase 2 -- but the field must be captured now, because it cannot be
			// reconstructed after the fact (interfaces.md E).
			DatasetEpoch: result.DatasetEpoch,
		}, vec); err != nil {
			log.Printf("gateway: tier-2 write-back failed for request_id=%s: %v", requestID, err)
		}
	}

	modelUsed := result.ModelUsed
	log.Printf("gateway: request_id=%s cache=MISS t_tier1=%s t_embed=%s t_search=%s t_overlap=%s",
		requestID, timings.Tier1, timings.Embed, timings.Search, timings.Overlap)
	writeJSON(w, askResponse{
		Answer:        result.Text,
		Cache:         cacheMiss,
		LatencyMs:     time.Since(start).Milliseconds(),
		Similarity:    similarity,
		SourceOverlap: sourceOverlap,
		Sources:       result.SourceChunkIDs,
		ModelUsed:     &modelUsed,
		RequestID:     requestID,
	})
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}
