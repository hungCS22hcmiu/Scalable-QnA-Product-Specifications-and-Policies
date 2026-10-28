package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"github.com/hung/thesis/gateway/internal/admission"
	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/catalog"
	"github.com/hung/thesis/gateway/internal/coalesce"
	"github.com/hung/thesis/gateway/internal/deps"
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

// dependencyMap is the part of *deps.Map that the request path uses (C2, interfaces.md §E): Register
// after a write-back, Invalidated on a hit. An interface so the tests can drive the hit path with a
// fake map and no Redis.
type dependencyMap interface {
	Register(deps.Registration)
	Invalidated(entryID string) bool
}

var _ dependencyMap = (*deps.Map)(nil) // the real map must keep satisfying it

// epochSource is the dataset epoch as the write-back guard reads it (interfaces.md §E, ADR-008).
// *deps.EpochFile is the production implementation; it re-reads its file on every call.
type epochSource interface {
	Current() (uint64, error)
}

var _ epochSource = (*deps.EpochFile)(nil) // the real source must keep satisfying it

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

	// SupportGate is the support gate's arm (item 2.4, interfaces.md H v0.14): GateOn runs the gate,
	// GateOff is the ablation arm. The ZERO VALUE IS GateOn, on purpose: this struct is built as a
	// literal by the test harness and the field is never set there, so a zero value that meant "off"
	// would ablate the gate in all of it. ONE field feeds both the Judge call (cascade.go) and the
	// record's support_gate key (Ask), so the behaviour and its label cannot come from two places
	// (design.md F2). It is set once, in main, before the server listens, and never changed.
	SupportGate reuse.Gate

	// Capacity is the bounded cache's size in ENTRIES, round(0.25 * K) per the capacity ratio. Zero means
	// unbounded, which is a valid thing to measure but never a thing to measure by accident --
	// main.go logs which one is in force at startup.
	Capacity int

	// LaneBand is the lane selector, widened from one sigma to two bounds so stratum D has a lane.
	// It is one of ADR-016's two pinned bands, checked at start by main's bandFromEnv: the closed band
	// (Lo == Hi, the default) is the MIXED-off arm and reproduces the original two-lane rule exactly,
	// and [0.20, 0.60) is the MIXED-on arm. It is the single source for both lane decisions (Classify,
	// for the query and for the write-back) and the record's mixed_lane label (LaneBand.Arm()).
	LaneBand reuse.LaneBand

	// Deps is the dependency map (C2). A nil Deps disables both the registration and the hit-path check,
	// so a Handler built as a struct literal (every test that predates item 4.1) behaves as it did.
	// cmd/gateway always sets it: a gateway without a map registers nothing, silently, and no purge can
	// then reach its entries (done condition 12 reads main.go for it).
	Deps dependencyMap

	// Epoch is the dataset epoch the write-back guard reads (item 4.2, interfaces.md §E). Nil turns the
	// guard off, so a Handler built as a struct literal (every test that predates item 4.2) writes back
	// as before. cmd/gateway always sets it: a gateway without a source never discards, and
	// writeback_discarded then stays false, which reads as "no race happened" (done condition 9 reads
	// main.go for it).
	Epoch epochSource

	// Catalog backs GET /products for the demo UI. Nil is valid and yields an empty list --
	// the gateway must start and serve /ask whether or not a corpus index exists.
	Catalog *catalog.Catalog

	// Counters back GET /stats for the demo's required counters sidebar. In-memory and
	// process-local; the measurement channel is the evaluation log, never this.
	Counters Counters

	// notScoredLogged keeps the NOT_SCORED alarm to one line per process. A stale RAG server answers
	// every request the same way, and a line per request would bury the one that matters. Its zero
	// value is ready to use, so a Handler built as a struct literal still works.
	notScoredLogged atomic.Bool
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

	// Discarded marks a generation whose write-back the epoch guard refused: nothing was written to
	// either tier or the dependency map, so there is no entry. Every request that shared the
	// generation then reports entry_id "" (interfaces.md §H).
	Discarded bool
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
		// Both arms are set HERE, in the literal, with config_id and mutation: every exit below emits this
		// record, so the Tier-1 lookup error, TIER1_HIT, SHED, ABANDONED and GENERATION_FAILED all carry
		// them. Set later, a Tier-1 record would carry "" and read as a different era of log (H, v0.14,
		// v0.16). mixed_lane comes from h.LaneBand, the same field Classify reads, so label and behaviour
		// cannot come from two places (ADR-016, item 4.5).
		SupportGate:     h.SupportGate.String(),
		MixedLane:       h.LaneBand.Arm(),
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
	// C2's hit-path check, AFTER the Redis read: the dependency map swaps its tombstones in before it
	// deletes anything, so a read that could still see a purged entry also sees its tombstone here.
	// The request then goes on as a Tier-1 miss, and the record names the entry it refused.
	if hit && h.Deps != nil && h.Deps.Invalidated(entry.EntryID) {
		rec.InvalidatedEntryID = entry.EntryID
		hit = false
	}
	if hit {
		modelUsed := entry.ModelUsed
		rec.Cache, rec.EntryID = cacheTier1Hit, entry.EntryID
		rec.EntrySources = entry.SourceChunkIDs
		rec.SetAnswer(entry.Answer)
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
	// The field names the FIRST invalidated entry this request met: Tier 1's wins if it set one.
	if rec.InvalidatedEntryID == "" {
		rec.InvalidatedEntryID = t2.InvalidatedEntryID
	}

	// The similarity travels on any judged candidate, served or refused. The overlap travels on a
	// banded one (sim >= tau), which is a hit unless the support gate then refused it: a SUPPORT or
	// NOT_SCORED request is a MISS that carries an overlap (interfaces.md §A v0.13).
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
		// in the served decision -- that is every TIER2_HIT and every support refusal, and
		// overlap_decision: false marks a reuse the containment conjunct would have refused.
		d := t2.Decision.Reuse
		overlapDecision = &d
	}

	rec.Similarity, rec.SourceOverlap = similarity, sourceOverlap
	rec.EnteredBand = t2.EnteredBand
	rec.ReuseRule = t2.NSDecision.Rule
	h.recordCause(&rec, t2, requestID)
	if retrieved != nil {
		rec.RetrievedChunkIDs = retrieved.ChunkIDs
		epoch := retrieved.DatasetEpoch
		rec.DatasetEpoch = &epoch
	}

	// The lane rule AND the support gate decide (the gate only while h.SupportGate is GateOn), through
	// the one cause: serve only on NONE (reuse.Judgement.Served), never on "no arm refused", which would
	// serve a stale server.
	// Containment is computed but not consulted -- it is the baseline being measured against.
	if t2.Served {
		modelUsed := modelUsedConstant
		rec.Cache, rec.EntryID = cacheTier2Hit, t2.Candidate.Entry.EntryID
		rec.EntrySources = t2.Candidate.Entry.SourceChunkIDs
		rec.SetAnswer(t2.Candidate.Entry.Answer)
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

		// The epoch guard (item 4.2, interfaces.md §E): any difference between the epoch Answer read
		// the chunk texts under and the epoch now discards the write-back, and so does a failed read.
		// A generation that started before an edit and finished after its purge would otherwise write
		// the old answer back with no trace. The compare is against ANSWER's epoch, because Answer
		// read the texts the answer was made from. Nothing below runs on this path: no Put, PutTier2,
		// Register, touch or TrimToCapacity. The client still gets the answer.
		if h.Epoch != nil {
			now, eerr := h.Epoch.Current()
			if eerr != nil || now != result.DatasetEpoch {
				// The leader's own record: this closure never runs for a coalesced follower, so only
				// the leader carries the flag and a discard is counted once.
				rec.WritebackDisc = true
				if eerr != nil {
					log.Printf("gateway: request_id=%s write-back discarded: epoch read failed: %v", requestID, eerr)
				} else {
					log.Printf("gateway: request_id=%s write-back discarded: answer epoch %d, current epoch %d",
						requestID, result.DatasetEpoch, now)
				}
				return &generation{
					Text:           result.Text,
					SourceChunkIDs: result.SourceChunkIDs,
					ModelUsed:      result.ModelUsed,
					Lane:           writeLane,
					Namespace:      writeNS,
					Discarded:      true,
				}, nil
			}
		}

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
				// Stored with the entry. The guard above compares it at write-back; the field cannot
				// be reconstructed after the fact (interfaces.md E).
				DatasetEpoch: result.DatasetEpoch,
			}, vec); err != nil {
				log.Printf("gateway: tier-2 write-back failed for request_id=%s: %v", requestID, err)
			}
		}

		// Register the entry's dependencies, WHATEVER the two writes above returned: a failed Tier-2 write
		// can leave the Tier-1 copy in Redis, and an entry with no dependency record survives every purge
		// (interfaces.md §E). Register takes no context, on purpose: this closure runs in the coalesced
		// generation, and a client that left cancels ctx. A registration that gave up on a cancelled
		// context would leave the entry unpurgeable, with no error (design.md §3, failure mode 1).
		if h.Deps != nil {
			h.Deps.Register(deps.Registration{
				EntryID:      entryID,
				Sources:      result.SourceChunkIDs,
				T1Key:        t1Key,
				DatasetEpoch: result.DatasetEpoch,
			})
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

	// t_generate_ms (interfaces.md §H v0.12, ADR-006): non-null iff THIS request's own Answer call was
	// attempted, successful or not. It is copied here, BEFORE the outcome switch, so that every outcome
	// inherits it and a case added later cannot forget it. generateMS is set only by this request's own
	// closure after Answer returns, so it stays nil, with no special case, for a SHED, for a client that
	// left while queued (both return from Acquire before genStart), and for every coalesced follower
	// (its closure never runs). It is deliberately NOT written inside the closure: that would change what
	// a leader that panics is logged with.
	rec.GenerateMS = generateMS

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
	case errors.Is(err, context.Canceled), errors.Is(err, context.DeadlineExceeded),
		err != nil && ctx.Err() != nil:
		// The client left. Under a load generator that is a timeout, and it counts against S2: it
		// is not client behaviour to exclude. Nothing is written, because a body to a dead
		// connection would only muddy the counts. A shed is above this case and an upstream error
		// with a live client is below it.
		//
		// The last condition is why a client that left while Answer was in flight lands here:
		// grpc-go reports a cancelled call as a *status.Error, which errors.Is does not match.
		// ctx is THIS request's own context (r.Context(), set at the top of Ask). It is read here,
		// after Do returns, and never inside the Do closure: the closure runs under the leader's
		// context, and reading that would hand a coalesced follower the leader's cancellation
		// (F-D). It is also never replaced by the status code, because rag.server can raise
		// CANCELED and DEADLINE_EXCEEDED itself with the client still connected.
		//
		// This relies on the request context being cancelled only by the client. main.go sets no
		// server timeout and no BaseContext. A future server-side deadline would be filed here as a
		// client leaving; context.Cause is the tool if that ever stops holding.
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
	if gen.Discarded {
		// interfaces.md H: no entry was written, so the record names none -- for the leader and for
		// every follower that shared the discarded generation. The response below still lists the
		// answer's sources; only the record changes.
		rec.EntryID, rec.EntrySources = "", nil
	}
	rec.SetAnswer(gen.Text)
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

// recordCause copies item 2.3's fields into the evaluation record. It runs BEFORE the miss path, so a
// request that is then shed, abandoned or fails to generate keeps the Tier-2 cause it earned: those
// records would otherwise read as "no candidate was judged".
//
//   - refusal_cause: set whenever a candidate was judged, null otherwise (Cause == "").
//   - support_lex and support_numeric_ok: set only when the gate SCORED. A stale server leaves them
//     null and the cause (NOT_SCORED) says why, so it is never mistaken for the gate-off arm. That arm
//     is named by the record's support_gate key (item 2.4), and its support fields are null by
//     construction: the gate did not run.
//   - candidate_entry_id and candidate_sources: the entry that was judged. On a refusal the record's
//     entry_id and entry_sources are the entry the miss then wrote, not this one (interfaces.md §H).
//
// Every value is copied into its own variable, so no pointer in the record aliases a reused one.
func (h *Handler) recordCause(rec *telemetry.Record, t2 tier2Outcome, requestID string) {
	if t2.Found {
		rec.CandidateEntryID = t2.Candidate.Entry.EntryID
		rec.CandidateSources = t2.Candidate.Entry.SourceChunkIDs
	}
	if t2.Cause == "" {
		return
	}
	cause := t2.Cause
	rec.RefusalCause = &cause
	if s := t2.Support; s != nil && s.Scored() {
		lex, numericOK := s.Lex.Score, s.Numeric.Admits()
		rec.SupportLex, rec.SupportNumericOK = &lex, &numericOK
	}
	if cause == reuse.CauseNotScored && h.notScoredLogged.CompareAndSwap(false, true) {
		log.Printf("gateway: ERROR request_id=%s refusal_cause=NOT_SCORED: the RAG service sent chunk IDs with no "+
			"evidence text (a pre-1.4 server?). Every Tier-2 candidate that clears tau will be refused and a run "+
			"taken now is NOT admissible (interfaces.md §H rule 10). Logged once per process.", requestID)
	}
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
