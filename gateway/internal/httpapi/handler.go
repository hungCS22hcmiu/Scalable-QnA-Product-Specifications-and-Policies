package httpapi

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"strconv"
	"sync"
	"time"

	"github.com/hung/thesis/gateway/internal/admission"
	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/catalog"
	"github.com/hung/thesis/gateway/internal/coalesce"
	"github.com/hung/thesis/gateway/internal/embed"
	"github.com/hung/thesis/gateway/internal/ragclient"
	"github.com/hung/thesis/gateway/internal/reuse"
	"github.com/hung/thesis/gateway/internal/telemetry"
)

// topKServerDefault is deliberately 0, not 5. The proto makes Go the sender of top_k, but Go
// has no config pinned to the frozen chunking, so a literal here would keep sending the old value the day
// the frozen chunking changes -- silently, since both sides would still work. Sending 0 makes the RAG
// service resolve it from rag/src/rag/config.py's TOP_K, leaving exactly one source of truth
// for the frozen value (impact.md lead risk; interfaces.md B: "default 5; pinned per run").
const topKServerDefault = 0

// modelUsedConstant mirrors rag/src/rag/config.py's LLM_MODEL_ID.
//
// It is a Go-side literal rather than a stored field because interfaces.md A defines model_used
// as "Constant (qwen3.5-2b) — retained for forward compatibility with routing (future
// work)", and the D Tier-2 schema has no model_used field to read it from. The alternatives were
// both worse: adding a field to a frozen schema needs an ADR, and fetching the co-written Tier-1
// record on every Tier-2 hit puts an extra Redis round-trip on the path that bounds mu_hit.
//
// The drift risk is real but bounded: routing was rejected, so this changes only if the
// generation model itself changes -- which already requires an ADR that would touch both sides.
const modelUsedConstant = "qwen3.5-2b"

// bumpTimeout bounds the detached hit_count write. Without it a stalled Redis would accumulate
// one goroutine per hit for as long as the stall lasts, which under load is precisely when the
// gateway has the least memory to spare.
const bumpTimeout = 2 * time.Second

// cacheStore is the part of *cache.Store that the request path uses. It exists so the tests can
// drive every exit path of Ask without Redis: RediSearch indexes only DB 0, which the dev cache
// occupies. *cache.Store is the only production implementation.
type cacheStore interface {
	Get(ctx context.Context, query, productID string) (*cache.Entry, bool, error)
	Put(ctx context.Context, query, productID string, e cache.Entry) error
	PutTier2(ctx context.Context, e cache.Tier2Entry, vec []float32) error
	NearestTier2InNamespace(ctx context.Context, vec []float32, namespace string, k int) ([]cache.Candidate, error)
	BumpHitCount(ctx context.Context, entryID string) error
	Touch(ctx context.Context, entryID string, nowUnixNano int64) error
	TrimToCapacity(ctx context.Context, capacity int) ([]cache.EvictedEntry, error)
}

var _ cacheStore = (*cache.Store)(nil) // the real store must keep satisfying it

// Handler serves POST /ask: cache.Get -> miss -> ragclient.Answer -> cache.Put. Single call
// site, so W16's admission control has exactly one place to insert later
// (architecture-guardrails.md: admission/ must be the sole place a permit is acquired --
// no miss path may bypass it).
//
// The cascade is orchestrated HERE rather than inside cache/ or reuse/. httpapi is the leftmost
// package and may import rightward; putting it here is what keeps reuse/ free of Redis, gRPC and
// HTTP so C1 stays falsifiable in isolation (docs/architecture.md 2).
type Handler struct {
	Cache      cacheStore
	RAG        *ragclient.Client
	Embed      *embed.Client
	Thresholds reuse.Thresholds

	// Admission bounds in-flight generations to the slots the model server serves (one, ADR-003),
	// queues a bounded number behind them, and sheds the rest. It must
	// be the SOLE place a permit is acquired (architecture-guardrails.md), which is why the miss
	// path has exactly one call site.
	Admission *admission.Pool

	// Generations collapses concurrent duplicate misses onto one execution. Keyed per handler,
	// not global, so a test can observe one handler's coalescing in isolation.
	Generations coalesce.Group[*generation]

	// Eval is the per-request evaluation log (interfaces.md H). A nil Logger is valid and does
	// nothing, which is what `make dev` runs with -- a functional run writes no measurement.
	Eval     *telemetry.Logger
	RunID    string
	ConfigID int
	Mutation string

	// Capacity is the bounded cache's size in ENTRIES, round(0.25 * K) per the capacity ratio. Zero means
	// unbounded, which is a valid thing to measure but never a thing to measure by accident --
	// main.go logs which one is in force at startup.
	Capacity int

	// LaneBand is the two-lane experiment's lane selector, widened
	// from one sigma to two bounds so stratum D has a lane. DEMO values like Tau and Theta:
	// swept, never hand-set for anything reported. A collapsed band (Lo == Hi) is the
	// pre-registered baseline and reproduces the original two-lane rule exactly.
	LaneBand reuse.LaneBand

	// Catalog backs GET /products for the demo UI. Nil is valid and yields an empty list --
	// the gateway must start and serve /ask whether or not a corpus index exists.
	Catalog *catalog.Catalog

	// Counters back GET /stats for the demo's required counters sidebar. In-memory and
	// process-local; the measurement channel is the evaluation log, never this.
	Counters Counters
}

func NewHandler(c cacheStore, r *ragclient.Client, e *embed.Client, t reuse.Thresholds, band reuse.LaneBand, pool *admission.Pool) *Handler {
	return &Handler{Cache: c, RAG: r, Embed: e, Thresholds: t, LaneBand: band, Admission: pool}
}

// generation is the shared result of one miss: everything a coalesced follower needs to answer
// without generating. It carries the entry identity too, so every request that shared a
// generation reports the same entry_id in the evaluation log -- which is what lets "generations
// avoided by coalescing" be counted separately from cache hits.
type generation struct {
	Text           string
	SourceChunkIDs []string
	ModelUsed      string
	EntryID        string
	Lane           reuse.Lane
	Namespace      string
}

// retryAfterSeconds is the frozen Retry-After of interfaces.md A's shed response.
const retryAfterSeconds = 2

// shedResponse is interfaces.md A's 503 body, verbatim. The field names are the contract; a
// load generator counts graceful degradation by matching on them.
type shedResponse struct {
	Error     string `json:"error"`
	Reason    string `json:"reason"`
	RequestID string `json:"request_id"`
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
	var timings stageTimings

	// interfaces.md H: exactly one record per request, on EVERY exit path -- hit, miss, shed and
	// abandonment alike. A deferred emit is what guarantees "every", because a return added later
	// cannot forget it.
	normalized := cache.Normalize(req.Question)
	// ⚠️ BYPASS 2026-09-09 (reverses the "product_id in Tier-1 key -- Rejected"; see
	// cache.Key). Computed ONCE and reused everywhere below, so the formula cannot drift between
	// the eval-log record, the Tier-1 lookup, the coalescing key and Tier-2's t1_key -- a
	// four-way duplication this replaces (approvals.md).
	t1Key := cache.Key(normalized, req.ProductID)
	rec := telemetry.Record{
		RequestID: requestID, RunID: h.RunID, ConfigID: h.ConfigID, Mutation: h.Mutation,
		TS:              start.UTC().Format(time.RFC3339Nano),
		QueryRaw:        req.Question,
		QueryNormalized: normalized,
		T1Key:           t1Key,
		ProductID:       req.ProductID,
		Stratum:         stratumHeader(r),
	}
	var pastTier1 bool
	defer func() {
		rec.TotalMS = durMS(time.Since(start))
		rec.Tier1MS = durMS(timings.Tier1)
		if pastTier1 {
			// Null where the stage did not run (interfaces.md H). A stage that ran cannot take
			// exactly zero, so zero is an unambiguous "absent" here.
			rec.EmbedMS, rec.SearchMS, rec.OverlapMS =
				msPtr(timings.Embed), msPtr(timings.Search), msPtr(timings.Overlap)
		}
		h.Eval.Log(rec)
		// One bump per request, at the one point every path reaches. Driven off rec so the
		// counters and the evaluation log can never disagree about what happened.
		h.Counters.record(rec.Cache, rec.Coalesced)
	}()

	// --- Tier 1: exact match. No vectors, no judgement, just sha256 equality. ---
	t1Start := time.Now()
	entry, hit, err := h.Cache.Get(ctx, req.Question, req.ProductID)
	timings.Tier1 = time.Since(t1Start)
	if err != nil {
		http.Error(w, "cache lookup failed: "+err.Error(), http.StatusInternalServerError)
		return
	}
	if hit {
		modelUsed := entry.ModelUsed
		rec.Cache, rec.EntryID = cacheTier1Hit, entry.EntryID
		rec.EntrySources = entry.SourceChunkIDs
		rec.AnswerSHA256 = sha256Hex(entry.Answer)
		h.touch(ctx, entry.EntryID)
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

	pastTier1 = true

	// --- Embed and retrieve CONCURRENTLY. Both are needed before the rule can decide, and
	// serialising them made the hit path their sum (~15 ms + ~18 ms) when it need only be their
	// maximum. They are independent: the embedding is of the query text, the retrieval is over
	// the corpus, and neither reads the other's output.
	//
	// Retrieval is speculative -- it now runs even for a request that will find no candidate above
	// tau. That is cheap but NOT free until the miss path stops retrieving a
	// second time inside Answer (rag/src/rag/server.py Answer -> retrieve.retrieve). Until that
	// lands, a below-tau miss performs two retrievals where it previously performed one. The
	// trade is deliberate: ~18 ms of retrieval against a multi-second generation.
	//
	// Both spans are measured INDEPENDENTLY and now overlap in wall-clock, so they no longer sum
	// to the total. interfaces.md F already allows that -- "the stage sums need not equal the
	// total" -- and deriving either by subtraction would be wrong here in a way it was not before.
	var (
		vec       []float32
		retrieved *ragclient.RetrieveResult
		wg        sync.WaitGroup
	)
	wg.Add(2)
	go func() {
		defer wg.Done()
		embedStart := time.Now()
		v, err := h.Embed.Query(ctx, req.Question)
		timings.Embed = time.Since(embedStart)
		if err != nil {
			// Degrade to MISS rather than fail. A Tier-2 outage should cost hit rate, not
			// availability, and a 500 here is an outcome that fits none of the categories
			// the evaluation counts.
			log.Printf("gateway: request_id=%s embed failed, degrading to MISS: %v", requestID, err)
			return
		}
		vec = v
	}()
	go func() {
		defer wg.Done()
		retrieveStart := time.Now()
		r, err := h.RAG.Retrieve(ctx, req.Question, topKServerDefault, req.ProductID)
		timings.Overlap = time.Since(retrieveStart)
		if err != nil {
			log.Printf("gateway: request_id=%s retrieve failed, degrading to MISS: %v", requestID, err)
			return
		}
		retrieved = r
	}()
	wg.Wait()

	// --- Tier 2: nearest neighbour, then the lane rule. ---
	t2 := h.tryTier2(ctx, req.ProductID, vec, retrieved, &timings)

	// The similarity travels on any judged candidate, served or refused. The overlap travels only
	// on a banded one, which while the served rule is similarity AND namespace is always a hit.
	var similarity, sourceOverlap *float64
	var overlapDecision *bool
	if t2.Found {
		s := t2.Candidate.Similarity
		similarity = &s
	}
	if t2.EnteredBand {
		o := t2.Decision.Overlap
		sourceOverlap = &o
		// The counterfactual travels on every banded response. While F-K stands -- theta is not
		// in the served decision -- that is every TIER2_HIT, and overlap_decision: false marks a
		// reuse the containment conjunct would have refused.
		d := t2.Decision.Reuse
		overlapDecision = &d
	}

	rec.Similarity, rec.SourceOverlap = similarity, sourceOverlap
	rec.EnteredBand = t2.EnteredBand
	rec.ReuseRule = t2.NSDecision.Rule
	if retrieved != nil {
		rec.RetrievedChunkIDs = retrieved.ChunkIDs
		epoch := retrieved.DatasetEpoch
		rec.DatasetEpoch = &epoch
	}

	// The two-lane rule decides. Containment is computed but not consulted -- it is the
	// baseline being measured against.
	if t2.NSDecision.Reuse {
		modelUsed := modelUsedConstant
		rec.Cache, rec.EntryID = cacheTier2Hit, t2.Candidate.Entry.EntryID
		rec.EntrySources = t2.Candidate.Entry.SourceChunkIDs
		rec.AnswerSHA256 = sha256Hex(t2.Candidate.Entry.Answer)
		// Fire-and-forget, and it must actually BE that. Awaiting it put a Redis round-trip on
		// the hit path -- inside mu_hit, the quantity the S1 turns on -- to update a
		// counter no caller reads. Detached from the request context so the write is not
		// cancelled the moment the response is flushed.
		go func(entryID string) {
			bumpCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), bumpTimeout)
			defer cancel()
			if err := h.Cache.BumpHitCount(bumpCtx, entryID); err != nil {
				log.Printf("gateway: hit_count bump failed for %s: %v", entryID, err)
			}
		}(t2.Candidate.Entry.EntryID)
		h.touch(ctx, t2.Candidate.Entry.EntryID)

		// Promote into Tier 1: a repeat of THIS query (byte-identical, same product) previously
		// paid Tier-2's cost (embed + search) every single time, because only the MISS path
		// wrote Tier 1 -- a Tier-2 hit never did. Fire-and-forget for the same reason as the
		// hit_count bump above: this must never add a Redis round-trip to the hit path.
		//
		// ⚠️ Known limitation, not fixed here: the Tier-2 record's t1_key field is singular
		// (interfaces.md §D, capacity.go's eviction reads exactly one), and was written for the
		// entry's ORIGINAL Tier-1 key at MISS time. This promoted key is a second, untracked
		// Tier-1 pointer at the same entry_id -- harmless today (cache_capacity defaults
		// UNBOUNDED, so TrimToCapacity never evicts anything, and C2/invalidation is 0% built,
		// the approvals.md), but once either lands, this key will not be found and
		// cleaned up alongside its entry, and could go stale/orphaned. Revisit before capacity
		// is bounded or C2 ships: either track multiple t1_keys per entry, or decide
		// promotion should not persist across an eviction/purge cycle.
		go func(entryID, question, productID, answer, modelUsed string, sources []string) {
			putCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), bumpTimeout)
			defer cancel()
			if err := h.Cache.Put(putCtx, question, productID, cache.Entry{
				Answer:         answer,
				SourceChunkIDs: sources,
				ModelUsed:      modelUsed,
				EntryID:        entryID,
			}); err != nil {
				log.Printf("gateway: tier-1 promotion failed for %s: %v", entryID, err)
			}
		}(t2.Candidate.Entry.EntryID, req.Question, req.ProductID, t2.Candidate.Entry.Answer, modelUsed, t2.Candidate.Entry.SourceChunkIDs)
		log.Printf("gateway: request_id=%s cache=TIER2_HIT t_tier1=%s t_embed=%s t_search=%s t_overlap=%s",
			requestID, timings.Tier1, timings.Embed, timings.Search, timings.Overlap)
		writeJSON(w, askResponse{
			Answer:          t2.Candidate.Entry.Answer,
			Cache:           cacheTier2Hit,
			LatencyMs:       time.Since(start).Milliseconds(),
			Similarity:      similarity,
			SourceOverlap:   sourceOverlap,
			Sources:         t2.Candidate.Entry.SourceChunkIDs,
			ModelUsed:       &modelUsed,
			RequestID:       requestID,
			Lane:            string(t2.QueryLane),
			Namespace:       t2.QueryNS,
			ReuseRule:       t2.NSDecision.Rule,
			OverlapDecision: overlapDecision,
		})
		return
	}

	// --- Miss: generate under a permit, coalesced, then write BOTH tiers from one identity. ---
	//
	// The nesting is load-bearing: COALESCING WRAPS THE PERMIT, never the other way round. N
	// identical questions arriving together must consume ONE permit and cause ONE generation. If
	// admission sat outside, N permits would be spent to produce one answer -- the opposite of
	// governing the envelope, and it would also make the no-cache baseline's generation count a
	// function of the load generator's concurrency instead of the workload's redundancy.
	//
	// product_id is now INSIDE t1Key itself (⚠️ BYPASS 2026-09-09, cache.Key), so reusing it here
	// needs no separate suffix: two requests with the same question text but different
	// product_id already hash to different keys, and collapsing them would partition one
	// caller's answer under the other's product.
	coalesceKey := t1Key

	var retrievedIDs []string
	if retrieved != nil {
		retrievedIDs = retrieved.ChunkIDs
	}

	var permitWait *time.Duration
	var queueDepth *int
	var generateMS *float64
	gen, err, shared := h.Generations.Do(coalesceKey, func() (*generation, error) {
		permit, err := h.Admission.Acquire(ctx)
		if err != nil {
			return nil, err
		}
		defer permit.Release()
		permitWait, queueDepth = &permit.Waited, &permit.QueueDepth
		rec.PermitWaitMS, rec.PermitQueue = msPtr(permit.Waited), permit.QueueDepth

		genStart := time.Now()
		// Hand the service the chunks already retrieved above, so it does not retrieve a second
		// time. retrievedIDs is nil when retrieval failed, in which case the service
		// falls back to retrieving for itself rather than generating over nothing.
		result, err := h.RAG.Answer(ctx, req.Question, topKServerDefault, retrievedIDs, req.ProductID)
		generateMS = msPtr(time.Since(genStart))
		if err != nil {
			return nil, err
		}

		// entry_id is minted here, not inside Put, so both tiers carry the SAME id. Divergence
		// would break the Phase-2 purge, which finds t2 by entry_id and t1 through its t1_key.
		// t1Key is the OUTER, hoisted key (closure capture) -- the same one used for the Tier-1
		// lookup above, so Tier-2's t1_key can never drift from what Tier-1 actually wrote under.
		entryID := cache.NewEntryID()

		// The entry is partitioned by ITS OWN grounding, not by the incoming query's. Those
		// differ: the query's lane came from retrieve(q) in the cascade, this one comes from the
		// chunks the answer was actually generated over. Using the query's would let a request
		// that never entered the band write an entry with no partition at all.
		writeLane := reuse.Classify(result.SourceChunkIDs, h.LaneBand)
		writeNS := reuse.Namespace(writeLane, result.SourceChunkIDs, req.ProductID)

		// A failed write-back must NOT fail the request. The generation already succeeded, and it
		// is the most expensive resource in the system -- discarding it because a cache write
		// failed spends it for nothing, which is backwards on this thesis's own premise. It also
		// produces a served-request outcome that is none of TIER1_HIT | TIER2_HIT | MISS | BYPASS
		// | 503-shed, the only categories the evaluation's goodput/shed split accounts
		// for, so a nonzero rate of it would leak out of both the goodput numerator and the shed
		// denominator. Serve the answer, count it as the MISS it was, and surface the failure on
		// its own channel.
		if err := h.Cache.Put(ctx, req.Question, req.ProductID, cache.Entry{
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
				Namespace:      writeNS,
				Lane:           string(writeLane),
				// Stored, not acted on. The epoch GUARD (discard write-back if the epoch
				// advanced) is Phase 2 -- but the field must be captured now, because it cannot
				// be reconstructed after the fact (interfaces.md E).
				DatasetEpoch: result.DatasetEpoch,
			}, vec); err != nil {
				log.Printf("gateway: tier-2 write-back failed for request_id=%s: %v", requestID, err)
			}
		}

		// Record the access and enforce capacity. Both are off the answer's critical path in the
		// sense that matters -- a failure costs hit rate or a slightly oversized cache, never a
		// served request, for the same reason the write-back itself does not fail one.
		h.touch(ctx, entryID)
		if evicted, err := h.Cache.TrimToCapacity(ctx, h.Capacity); err != nil {
			log.Printf("gateway: eviction failed for request_id=%s: %v", requestID, err)
		} else if len(evicted) > 0 {
			log.Printf("gateway: request_id=%s evicted %d entr(y|ies) to hold capacity=%d",
				requestID, len(evicted), h.Capacity)
		}

		return &generation{
			Text:           result.Text,
			SourceChunkIDs: result.SourceChunkIDs,
			ModelUsed:      result.ModelUsed,
			EntryID:        entryID,
			Lane:           writeLane,
			Namespace:      writeNS,
		}, nil
	})

	switch {
	case errors.Is(err, admission.ErrShed):
		// The frozen shed contract (interfaces.md A). Counted by the scalability eval as a
		// graceful-degradation event, NEVER as an error.
		w.Header().Set("Retry-After", strconv.Itoa(retryAfterSeconds))
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusServiceUnavailable)
		_ = json.NewEncoder(w).Encode(shedResponse{
			Error:     "busy",
			Reason:    "generation_pool_saturated",
			RequestID: requestID,
		})
		rec.Shed, rec.Cache = true, cacheShed
		rec.PermitQueue = h.Admission.Queued()
		log.Printf("gateway: request_id=%s cache=SHED in_flight=%d queued=%d",
			requestID, h.Admission.InFlight(), h.Admission.Queued())
		return
	case errors.Is(err, context.Canceled), errors.Is(err, context.DeadlineExceeded):
		// The client left. Not a shed, not an error the gateway caused -- writing a body to a
		// dead connection would only muddy the counts.
		rec.Cache = cacheAbandoned
		log.Printf("gateway: request_id=%s abandoned while generating: %v", requestID, err)
		return
	case err != nil:
		rec.Cache = cacheGenFailed
		http.Error(w, "generation failed: "+err.Error(), http.StatusBadGateway)
		return
	}

	result := gen
	rec.Cache, rec.EntryID = cacheMiss, gen.EntryID
	rec.EntrySources = gen.SourceChunkIDs
	rec.AnswerSHA256 = sha256Hex(gen.Text)
	rec.GenerateMS = generateMS
	rec.Coalesced = shared
	_, _ = permitWait, queueDepth

	modelUsed := result.ModelUsed
	writeLane, writeNS := result.Lane, result.Namespace
	log.Printf("gateway: request_id=%s cache=MISS t_tier1=%s t_embed=%s t_search=%s t_overlap=%s",
		requestID, timings.Tier1, timings.Embed, timings.Search, timings.Overlap)
	writeJSON(w, askResponse{
		Answer:          result.Text,
		Cache:           cacheMiss,
		LatencyMs:       time.Since(start).Milliseconds(),
		Similarity:      similarity,
		SourceOverlap:   sourceOverlap,
		Sources:         result.SourceChunkIDs,
		ModelUsed:       &modelUsed,
		RequestID:       requestID,
		Lane:            string(writeLane),
		Namespace:       writeNS,
		OverlapDecision: overlapDecision,
	})
}

// touch records an LRU access. Deliberately swallows its error: an access this drops only makes
// an entry look staler than it is, costing a little hit rate, whereas failing a request that was
// already answered correctly would cost availability to protect a heuristic.
func (h *Handler) touch(ctx context.Context, entryID string) {
	if h.Capacity <= 0 {
		return
	}
	if err := h.Cache.Touch(ctx, entryID, time.Now().UnixNano()); err != nil {
		log.Printf("gateway: lru touch failed for %s: %v", entryID, err)
	}
}

// durMS and msPtr keep interfaces.md H's millisecond fields in one place. msPtr returns nil for a
// zero duration: the schema says "null where the stage did not run", and a stage that ran cannot
// take exactly zero, so zero is an unambiguous "absent".
func durMS(d time.Duration) float64 { return float64(d.Microseconds()) / 1000 }

func msPtr(d time.Duration) *float64 {
	if d == 0 {
		return nil
	}
	v := durMS(d)
	return &v
}

// sha256Hex hashes the answer AS SERVED. interfaces.md H is explicit that it must be taken at
// serve time and never recomputed from a possibly re-generated answer, because experiment-
// protocol.md 4 keys judge verdicts on it.
func sha256Hex(answer string) string {
	sum := sha256.Sum256([]byte(answer))
	return hex.EncodeToString(sum[:])
}

// stratumHeader reads the workload's stratum label if the harness sent one.
//
// ⚠️ A HEADER, not a body field: interfaces.md A is frozen at v0.5 and does not carry a stratum,
// and this is a measurement-harness affordance rather than part of the client contract. If it is
// absent the field is null and the analysis joins the label offline on query_normalized, which is
// exact -- the Tier-1 collision invariant guarantees one stratum per normalised form.
func stratumHeader(r *http.Request) *string {
	if v := r.Header.Get("X-Thesis-Stratum"); v != "" {
		return &v
	}
	return nil
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}
