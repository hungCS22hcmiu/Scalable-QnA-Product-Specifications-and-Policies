# Interface & Data Contracts

**Status:** Draft v0.5 · **Owner:** thesis author · **Created:** 2026-07-23 · **Revised:** 2026-09-02 (ADR-027, ADR-028, ADR-029)
**Companion to:** `Final_Proposal.md` (§6 architecture, §7 stack), `defense_demo.md` (§2 `/ask` contract), `decisions.md` (frozen choices).

**Purpose.** Pin the *seams* the pillars share — the HTTP API, the Go↔Python gRPC boundary, the chunk-ID scheme, the Redis cache/dependency schemas, and the invalidation event — **before** build work starts (timeline W5–W7 wires the gateway↔RAG seam; W9–W11 the invalidation map). These contracts are the single reuse-critical decision set: get the chunk-ID and provenance shape right once, or re-plumb them twice. Contracts here are **frozen**; any change requires a new entry in `decisions.md`.

> **v0.2 changes (ADR-016).** `reuse_confidence` → **`source_overlap`** (the deterministic rule's overlap score, not a predictor output); SSE demoted to optional/future; `question_type` / `answer_type` dropped from the Tier-2 schema; purge policy is **blind only**. The `Retrieve` RPC and the whole cascade are **unchanged** — the rule needs retrieval exactly as the predictor would have.
>
> **v0.3 changes — three correctness fixes found in advisor review.** Each closes a path by which C2's completeness guarantee would fail *silently*:
> 1. **Eviction policy (§D).** `allkeys-lru` can evict `dep:{chunk_id}` sets, orphaning the entries they point to. Dependency state now lives under **`noeviction`**, separate from the LRU-managed cache.
> 2. **`t1_key` (§D).** The dependency map stored only `entry_id`, from which the Tier-1 hash key is *not computable* — so Tier-1 entries survived purges. The Tier-2 record now carries `t1_key`.
> 3. **`dataset_epoch` (§B, §E).** A generation in flight during an edit wrote back *after* the purge, resurrecting stale data. Retrieval now stamps an epoch; write-back discards if it has advanced.

> Conventions: `snake_case` field names on the wire; timestamps are RFC 3339 UTC; vectors are `float32`. "Entry" = a cached Q&A record; "chunk" = a retrieved source fragment.

---

## Request-flow map

Keyed to proposal §6 (architecture diagram). Each numbered contract is specified below.

```
Client ──(A) HTTP POST /ask──▶ Go Gateway
                                  │
                                  ├─ (G) classify: cacheable? ──▶ (bypass) live source
                                  ├─ Tier-1 exact lookup ─────────▶ (D) Redis
                                  ├─ (F) embed query ─────────────▶ Embedding service
                                  ├─ Tier-2 vector search ────────▶ (D) Redis
                                  ├─ C1 cascade: (B) Retrieve ─────▶ Python RAG   (overlap only, no generation)
                                  └─ MISS: (B) Answer (stream) ────▶ Python RAG ──▶ Local LLM
                                                                     │
Corpus edit ──(E) invalidation event──▶ Invalidator ──▶ (D/E) Redis purge

Every request also appends one (H) evaluation-log record to results/{run_id}/raw/
```

---

## A. Client ↔ Gateway — HTTP API

### `POST /ask`

Request:

```json
{ "question": "Can I return this laptop after 30 days?" }
```

Success response (`200 application/json`) — **superset of `defense_demo.md` §2**; the six fields there are required, the rest optional:

```json
{
  "answer": "Returns are accepted within 30 days of delivery...",
  "cache": "TIER2_HIT",                    // TIER1_HIT | TIER2_HIT | MISS | BYPASS
  "latency_ms": 48,
  "similarity": 0.93,                       // Tier-2 embedding similarity; null on TIER1/BYPASS
  "source_overlap": 0.80,                   // overlap rule score (Contribution 1); null unless the cascade ran
  "sources": ["policy-returns#chunk-2"],    // provenance tags (Contribution 2); [] on BYPASS
  "model_used": "qwen3.5-2b",                // constant for now (routing rejected — ADR-011)
  "request_id": "01J..."                    // extension: correlation id for tracing/eval
}
```

| Field | Type | Notes |
| :--- | :--- | :--- |
| `answer` | string | Final answer text. |
| `cache` | enum | `TIER1_HIT` \| `TIER2_HIT` \| `MISS` \| `BYPASS`. Drives the debug-UI badge colors (`defense_demo.md` §3). |
| `latency_ms` | int | Gateway-internal wall time; the eval also records off-box end-to-end separately (`experiment-protocol.md`). |
| `similarity` | float\|null | Cosine similarity of the matched Tier-2 entry. |
| `source_overlap` | float\|null | Fraction of the candidate entry's `source_chunk_ids` also returned by retrieval on the incoming query — the rule's score, compared against θ. `null` when the cascade short-circuited on similarity alone. |
| `sources` | string[] | Chunk IDs (§C) that grounded the answer. |
| `model_used` | string\|null | Constant (`qwen3.5-2b`, ADR-021) — retained for forward compatibility with routing (future work). |
| `request_id` | string | Optional; ULID for joining logs to eval records. |

Showing `similarity` and `source_overlap` **side by side** is what makes the contribution observable: a high-similarity, low-overlap miss is the lookalike trap the rule exists to catch (`defense_demo.md` §4 step 4).

### Streaming variant (MISS path — SSE) — *optional, not in scope*

**Dropped from the thesis scope by ADR-016** (miss responses return complete). The shape is retained here so that adding it later is a pure extension, not a contract change. If implemented, a client sending `Accept: text/event-stream` receives a token stream whose terminal `done` event carries the metadata block:

```
event: token
data: {"text": "Returns are "}

event: token
data: {"text": "accepted within 30 days..."}

event: done
data: {"answer": "...", "cache": "MISS", "latency_ms": 4120, "sources": ["policy-returns#chunk-2"], "model_used": "qwen3.5-2b", "request_id": "01J..."}
```

### Backpressure / admission-control response

When the bounded generation-concurrency pool is exhausted and the queue budget is spent (proposal §6.1/§6.2 admission control), the gateway **sheds** rather than admitting a generation the memory envelope cannot hold:

```
HTTP/1.1 503 Service Unavailable
Retry-After: 2
{ "error": "busy", "reason": "generation_pool_saturated", "request_id": "01J..." }
```

Shed responses are counted by the scalability eval as graceful-degradation events, not errors (`experiment-protocol.md`).

---

## B. Gateway ↔ RAG Service — gRPC

Two RPCs. The separation is deliberate: the **C1 cascade** must run retrieval on the incoming query to compute source overlap **without** paying for generation (proposal §5 C1 — "the retriever doubles as a reuse-safety oracle").

```proto
syntax = "proto3";
package rag.v1;

service RagService {
  // Full miss path: retrieve + generate. Streaming is optional (see §A).
  rpc Answer(AnswerRequest) returns (stream AnswerChunk);
  // Retrieval only — supplies the chunk IDs the source-overlap rule compares against.
  rpc Retrieve(RetrieveRequest) returns (RetrieveResponse);
}

message RetrieveRequest {
  string query = 1;
  uint32 top_k = 2;          // default 5; pinned per run and reported
}

message RetrieveResponse {
  repeated string chunk_ids     = 1;   // stable chunk IDs, ranked (see §C)
  repeated float  scores        = 2;   // aligned with chunk_ids; retriever similarity
  uint64          dataset_epoch = 3;   // corpus version these chunks came from (§E)
}

message AnswerRequest {
  string query = 1;
  uint32 top_k = 2;
  bool   stream = 3;         // defaults FALSE in scope (SSE dropped — ADR-016):
                             // a single terminal AnswerChunk is returned
}

message AnswerChunk {
  string text = 1;                 // token / span for streaming
  bool   done = 2;                 // true on the terminal chunk
  repeated string source_chunk_ids = 3;  // populated on the terminal chunk
  string model_used    = 4;              // populated on the terminal chunk
  uint64 dataset_epoch = 5;              // epoch at retrieval time; gates write-back (§E)
}
```

Transport: gRPC over a pooled channel (proposal §6.1). Proto lives at `contracts/rag/v1/rag.proto` once code is scaffolded (**W6**); this sketch is the frozen shape.

---

## C. Stable chunk-ID scheme  ⚠️ reuse-critical

Both provenance (C1) and source-aware invalidation (C2) key on chunk IDs, so the scheme must be **stable across re-chunking** (timeline **W5** implements it, W9–W11 depend on it). It must survive the `dev-v0` → `v1` corpus change (ADR-020): the chunking config is frozen in W5, so `v1` is a content expansion under a new `dataset_version`, not a re-chunk.

- **Format:** `{doc_id}#chunk-{ordinal}` — e.g. `policy-returns#chunk-2` (this exact example is the one in `defense_demo.md` §2).
- **`doc_id`:** stable slug of the source document (`policy-returns`, `product-B08XYZ`), assigned at ingestion and never reused for a different document.
- **`ordinal`:** 0-based position of the chunk within the document under the **frozen chunking config** (size/overlap recorded in `decisions.md`).
- **Re-chunking rule:** if the chunking config changes, IDs are *not* silently reassigned — a re-chunk is a new dataset version (`data-card.md`) and forces a full cache rebuild, so a given `{doc_id}#chunk-{ordinal}` always denotes the same span within one dataset version. This keeps completeness/precision measurable (proposal §5 C2).
- **Uniqueness:** `(dataset_version, chunk_id)` is unique; `chunk_id` is unique within a dataset version.

---

## D. Cache-entry schema (Redis)

Bounded, LRU (proposal §6.3). **Capacity is `round(0.25 × K)`**, where `K` is the frozen workload's distinct-query count (ADR-027) — the ratio is frozen study-wide, the absolute is derived at corpus freeze and recorded per run. An absolute capacity was rejected because at `C ≥ K` nothing is ever evicted and the redundancy sweep collapses to a constant.

> ⚠️ **Eviction policy is a correctness constraint, not a tuning knob.** `allkeys-lru` evicts *any* key under pressure — **including the `dep:{chunk_id}` sets of §E**. An evicted dependency record makes its entries permanently unpurgeable, so invalidation completeness fails silently and non-reproducibly. Therefore:
>
> - Cache entries (`t1:*`, `t2:*`) live in a **logical DB / instance with `allkeys-lru`** at the stated capacity.
> - Dependency state (`dep:*`, `entry:*`) lives in a **separate logical DB / instance with `noeviction`**.
>
> At this corpus size the dependency map is a few megabytes, so the no-eviction region costs nothing. Equivalent alternative: one instance under `volatile-lru` with TTLs set **only** on cache entries. Whichever is chosen is recorded per run — a run whose dependency region evicted anything is **invalid** and repeated.

**Tier 1 — exact match.** O(1) hash lookup, no vector:

```
KEY   t1:{sha256(normalized_query)}      # HASH
      answer            <string>
      source_chunk_ids  <json array>
      model_used        <string>
      created_at        <rfc3339>
      entry_id          <ulid>            # links to the Tier-2 record / dependency map
```

Normalization (lowercase, collapse whitespace, strip punctuation) is specified in `decisions.md` (ADR-015) and must match the Tier-1 write path exactly.

> ⚠️ **Tier 1 runs no reuse rule, so its safety is a corpus invariant (ADR-028).** This lookup is a bare hash equality test — no similarity check, no containment check. Two workload queries with different correct answers that normalise to the same string would be served wrongly from first write, permanently, with nothing to detect it. Worse, the resulting false hit has **no bucket** in `experiment-protocol.md` §4's two-cause split and would be charged to the reuse rule, which never ran. The corpus therefore carries the invariant *"no two queries with different `reference_answer` or `doc_ids` share a `normalize(q)`"*, checked before the snapshot is hashed (`data-card.md` §7). Note that stripping punctuation collapses `Model A-1` and `Model A1` — harmless within one product, not harmless across two.

**Tier 2 — semantic.** RediSearch vector index (RedisVL) — **`FLAT` (exact), frozen study-wide**. HNSW is a scaling path for a production deployment but is **never enabled mid-study**: approximate retrieval would make `retrieve(q)` nondeterministic and inject overlap noise indistinguishable from C1's signal (proposal §5 C1, §7).

```
INDEX  idx:cache   ON HASH PREFIX t2:
KEY    t2:{entry_id}                      # HASH
       embedding         <float32[DIM]>   # VECTOR field; DIM = embedding model dim (§F)
       query_text        <string>
       answer            <string>
       source_chunk_ids  <json array>     # provenance (§C) — the set the overlap rule tests against
       t1_key            <string>         # ⚠️ the Tier-1 key this entry was co-written with
       dataset_epoch     <int>            # corpus version at generation time (§E)
       source_overlap    <float>          # last overlap score computed for this entry
       hit_count         <int>            # reuse-value signal (future admission-control idea)
       created_at        <rfc3339>
```

`source_chunk_ids` is the load-bearing field for **both** contributions: C1 intersects it with the incoming query's retrieval, C2 indexes it in reverse to build the dependency map (§E). (`question_type` / `answer_type`, auxiliary features for the learned predictor, were removed in v0.2 — ADR-016.)

> ⚠️ **`t1_key` exists so that Tier-1 is purgeable.** Tier 1 is keyed by `sha256(normalized_query)`; the dependency map stores only `entry_id`. Without a stored back-pointer the invalidator **cannot compute the Tier-1 key** from a dependency record, so Tier-1 copies of an invalidated answer would survive the purge and continue serving stale content — a completeness hole that no test of the Tier-2 path would reveal. Both tiers are written together on a miss, so `t1_key` is written at the same moment and never diverges.

Vector field: distance metric **COSINE**, `DIM` equals the embedding dimension in §F (they must not drift — see cross-consistency in `experiment-protocol.md`). Write-back on a full miss populates **both** tiers, tagged with `source_chunk_ids` (proposal §6.3).

---

## E. Dependency map + invalidation event

**Authoritative map (Redis):** reverse index from source chunk to dependent entries.

```
KEY   dep:{chunk_id}   # SET of entry_id
```

**Fast-path index (in-process, Go):** a read-mostly copy consulted without touching Redis on the hot path, guarded per proposal §5 C2 — `sync.RWMutex` baseline, or `atomic.Pointer` copy-on-write for a wait-free read path. Mutations are **serialized through a single writer goroutine** fed by a buffered channel; the writer updates the in-process index and fans the purge out to Redis (both tiers) off the critical path.

**Invalidation event (channel payload):**

```json
{
  "chunk_id": "policy-returns#chunk-2",
  "doc_id": "policy-returns",
  "change_type": "substantive",          // substantive (answer-changing) | cosmetic (answer-preserving)
  "new_text": "Returns are accepted within 14 days...",
  "dataset_version": "v3",
  "ts": "2026-07-23T10:00:00Z"
}
```

**Dataset epoch (⚠️ concurrency-critical).** A monotonic counter incremented by the invalidator on every applied edit, held in Redis under the no-eviction region and cached in-process.

```
KEY   dataset:epoch    # INT, monotonically increasing
```

- `Retrieve` and `Answer` return the epoch **observed at retrieval time** (§B).
- **Write-back compares that epoch against the current one and discards the result if it has advanced.** Without this, a generation already in flight when its source chunk is edited writes back *after* the purge has run — resurrecting an answer derived from superseded text, with no trace. Completeness is therefore a property of the purge **and** the write path together, not of the purge alone.
- Discarded write-backs are counted and reported; a nonzero count under load is expected and is evidence the guard is doing work, not evidence of a bug.

**Purge decision:** **`blind` only** — purge every `entry_id` in `dep:{chunk_id}`, dropping both the `t2:` record and its `t1_key` (§D). Guaranteed-complete: no answer over a changed source survives. Predictor-gated purging was removed by ADR-016 (it depended on the dropped learned predictor) and is future work (proposal §14).

- `change_type` is recorded **for evaluation only** — it measures how often blind purge over-invalidates on answer-preserving edits (`experiment-protocol.md` §4). It is never used as a gate: trusting an edit's self-declared type would make completeness depend on the corpus author's labelling.
- `new_text` is carried on the event so a future gated variant needs no corpus round-trip, and so the writer can log what changed.

---

## F. Embedding service

```
POST /embed   { "text": "..." }
200           { "vector": [float32...], "dims": 768, "model": "<frozen-model-id>" }
```

- The embedding model is **frozen** early (proposal §12) — see `decisions.md` ADR-003 (**Decided and frozen 2026-08-15**: `nomic-embed-text`, `dims = 768`). It is **served by Ollama**, not by an in-process `sentence-transformers`/PyTorch stack, which would cost ~2 GB resident for a ~400 MB model (ADR-017).
- ⚠️ **This call sits on the hit path.** Every Tier-2 lookup pays an embedding round-trip, so this endpoint's latency directly bounds **μ_hit** — the load-conversion ceiling of proposal §3. Hit-path latency is reported **decomposed** into {Tier-1 lookup, embed, vector search, overlap check} rather than as a single total, so the share attributable to this call is visible.
- `dims` **must equal** the Tier-2 index `DIM` (§D) and be identical across all **five** cache configurations (proposal §9.2 pins one embedding model so comparisons isolate the reuse policy).

---

## G. Bypass classifier

**Demo stub only — not an evaluated component (ADR-018).** The corpus contains no dynamic content and there is no live inventory source, so a learned or evaluated classifier would be scored against a stub while adding a false-hit cause that contaminates the headline. It is therefore a **hardcoded keyword rule** that exists so the demo can show the routing decision (`defense_demo.md` §1).

```
classify(query) -> { "route": "cacheable" | "bypass", "reason": "<label>" }
```

- `cacheable` → continues into Tier-1/Tier-2. This is the path all evaluation traffic takes.
- `bypass` → returns the stub response, sets `"cache": "BYPASS"`, `sources: []`.
- **Bypass accuracy is not a reported metric**, and `BYPASS` does not appear in the evaluation workload.

---

## H. Per-request evaluation log  ⚠️ measurement-critical

**ADR-029.** One **JSONL record per request**, appended by the gateway to `results/{run_id}/raw/requests.jsonl`. Written off the critical path. `request_id` (§A) is the join key to the `/ask` response and to judge verdicts.

Four metrics in `experiment-protocol.md` §4 are **not computable without this record**: *decisions changed by provenance*, *% entering the cascade band*, *false hits by cause*, and the hit-path latency decomposition.

```json
{
  "request_id": "01J...",              // ULID, joins to /ask (§A)
  "run_id": "2026-11-18T14-03-02_cfg4_zipf1.1",
  "config_id": 4,                       // 1..5 (proposal §9.2)
  "mutation": "off",                    // off|on (ADR-023)
  "ts": "2026-11-18T14:03:02.481Z",

  "query_raw": "How long is the warranty period on the XPS 13?",
  "query_normalized": "how long is the warranty period on the xps 13",
  "t1_key": "t1:9f2c...",               // §D; lets a collision be detected post hoc
  "stratum": "B-within",                // A | B-within | B-cross | C | D (ADR-028)

  "cache": "TIER2_HIT",                 // TIER1_HIT | TIER2_HIT | MISS
  "similarity": 0.91,
  "source_overlap": 0.80,               // null when the cascade short-circuited
  "entered_band": true,                 // paid for retrieval — the rule's cost driver
  "similarity_only_decision": "HIT",    // ⚠️ counterfactual, see below

  "retrieved_chunk_ids": ["policy-warranty-electronics#chunk-1"],
  "entry_sources": ["policy-warranty-electronics#chunk-1"],
  "entry_id": "01J...",

  "t_total_ms": 48.2,
  "t_tier1_ms": 0.3,
  "t_embed_ms": 11.4,
  "t_search_ms": 4.1,
  "t_overlap_ms": 0.1,
  "t_permit_wait_ms": null,             // null unless a permit was requested
  "t_generate_ms": null,                // null unless generation ran

  "shed": false,
  "permit_queue_depth": 0,

  "dataset_epoch_at_retrieval": 7,
  "writeback_discarded": false,         // epoch guard fired (§E)

  "answer_sha256": "3a71..."            // ⚠️ judge dedupe key, see below
}
```

> ⚠️ **Two fields cannot be reconstructed after the fact, and both carry a metric on their own.**
>
> - **`similarity_only_decision`** — what the fixed-threshold baseline *would* have decided for this request, recorded at the moment the rule ran. *Decisions changed by provenance* is the share of Tier-2 candidates where this disagrees with the served outcome. Re-deriving it later would require replaying against cache state that no longer exists. It is the metric that makes the **pre-registered null interpretable** (`experiment-protocol.md` §6) — without it, a null result cannot be distinguished from a thin corpus.
> - **`answer_sha256`** — `sha256` of the served answer text. `experiment-protocol.md` §4 keys judge verdicts by `sha256(query ‖ candidate_answer)` to keep judging affordable, and the hash must be taken when the answer is served rather than recomputed from a possibly re-generated answer.

Field notes:

| Field | Notes |
| :--- | :--- |
| `stratum` | Carried from the workload record (`data-card.md` §2). Enables the frontier to be reported per sub-stratum, which is what answers the product-ID objection (ADR-028) |
| `t1_key` | Recording it lets the Tier-1 collision invariant (ADR-028) be re-verified from run output, not only at corpus-freeze time |
| `entered_band` | Distinguishes short-circuit hits from cascade-band hits. `experiment-protocol.md` §4 requires their latencies reported separately |
| `t_*_ms` | Null where the stage did not run. Sum need not equal `t_total_ms` — the difference is gateway overhead and is reported as such |
| `writeback_discarded` | A nonzero count under load is evidence the epoch guard is working, not a bug (§E) |

`raw/` is write-once (`experiment-protocol.md` §3), so this file is immutable once a run completes.

---

## Versioning

These contracts are frozen for the study. A change to any wire shape, the chunk-ID format, or the Redis schema is a design decision: add a dated entry to `decisions.md` and bump this file's version. Silent drift here invalidates cross-configuration comparisons (proposal §12). Current version: **v0.5** (2026-09-02, ADR-029 adds §H; ADR-027 makes cache capacity a ratio of workload size).

**Frozen study-wide, from measurement or by policy — changing any of these mid-study invalidates every comparison:** the generation LLM, Qwen 3.5 2B `q4_K_M` with `think: false` (ADR-021) · the embedding model and `DIM` (ADR-003) · `top_k` · the **FLAT (exact) vector index** — no mid-study HNSW upgrade, since approximate retrieval would inject overlap noise indistinguishable from C1's signal · `num_ctx = 8192` and `OLLAMA_NUM_PARALLEL = 4` (ADR-017, from the feasibility spike) · the **cache-capacity ratio `C/K = 0.25`** and the two-region eviction policy (§D, ADR-027).
