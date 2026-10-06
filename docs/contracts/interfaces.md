# Interface & Data Contracts

**Status:** Draft v0.11 · **Owner:** thesis author · **Created:** 2026-07-23 · **Revised:** 2026-10-06
**Companion to:** `Final_Proposal.md` (§6 architecture, §7 stack), `decisions.md` (frozen choices).

**Purpose.** Pin the *seams* the pillars share — the HTTP API, the Go↔Python gRPC boundary, the chunk-ID scheme, the Redis cache/dependency schemas, and the invalidation event — **before** build work starts (timeline W5–W7 wires the gateway↔RAG seam; W9–W11 the invalidation map). These contracts are the single reuse-critical decision set: get the chunk-ID and provenance shape right once, or re-plumb them twice. Contracts here are **frozen**; any change requires a new entry in `decisions.md`.

> **v0.2 changes.** `reuse_confidence` → **`source_overlap`** (the deterministic rule's overlap score, not a predictor output); SSE demoted to optional/future; `question_type` / `answer_type` dropped from the Tier-2 schema; purge policy is **blind only**. The `Retrieve` RPC and the whole cascade are **unchanged** — the rule needs retrieval exactly as the predictor would have.
>
> **v0.3 changes — three correctness fixes found in advisor review.** Each closes a path by which C2's completeness guarantee would fail *silently*:
> 1. **Eviction policy (§D).** `allkeys-lru` can evict `dep:{chunk_id}` sets, orphaning the entries they point to. Dependency state now lives under **`noeviction`**, separate from the LRU-managed cache.
> 2. **`t1_key` (§D).** The dependency map stored only `entry_id`, from which the Tier-1 hash key is *not computable* — so Tier-1 entries survived purges. The Tier-2 record now carries `t1_key`.
> 3. **`dataset_epoch` (§B, §E).** A generation in flight during an edit wrote back *after* the purge, resurrecting stale data. Retrieval now stamps an epoch; write-back discards if it has advanced.

> **v0.6 changes.** Three seam changes the two-lane reuse rule forced,
> each with a measured failure behind it rather than a preference:
> 1. **`product_id` on `/ask` (§A).** Optional. A spec-lane namespace derived from the *rank-1 product
>    document* is unstable: measured 2026-09-06, one run produced **one false hit and one false miss**
>    from that instability alone, both corrected by sending `product_id`. It is a **stabiliser, not a
>    cache key** — the rejection of `product_id` as a cache key stands untouched.
> 2. **Doc-id kind prefix is now required (§C).** `reuse.Classify` reads the document kind from the
>    `policy-` / `product-` prefix. It was enforced only in the ingester, so a corpus built without it
>    would classify every question `SPEC` **silently**, with the lane machinery reporting plausible
>    values throughout.
> 3. **Eviction moves into the gateway (§D).** `maxmemory-policy` is server-global rather than
>    per-logical-DB, so v0.3's two-region split was not achievable on one server; and the capacity ratio
>    capacity is a **count** of entries, which a byte budget cannot express.

> **v0.7 changes.** `AnswerRequest` gains `retrieved_chunk_ids` (§B). Every Tier-1 miss
> already retrieved once before reaching `Answer`, which then retrieved again; the duplicated work
> is the **query embedding**, not the vector search. Additive — an empty field preserves the old
> behaviour exactly.

> **v0.9 changes.** The reuse rule gains a fourth and final test — an
> **answer–evidence support gate** adopted from GroundedCache at its published threshold, in a
> lexical arm and a numeric arm — and two things follow at this seam. **§B `RetrieveResponse` gains
> `texts`**, positionally aligned with `chunk_ids`: the gateway has only ever held chunk
> *identifiers*, and the gate compares a cached answer against chunk *text*, so it cannot run at all
> without this field. **§H gains `refusal_cause`, `support_lex` and `support_numeric_ok`**, without
> which a support refusal is indistinguishable from a namespace refusal and the adopted gate's
> contribution cannot be attributed. In the same revision **§H's `similarity_only_decision` is
> retired** together with the unfiltered similarity-only cascade phase and the `tau_high`
> short-circuit that produced it; the counterfactual becomes a cross-configuration join
> on the static-cache arm. Additive at §B — an absent `texts` is today's behaviour exactly — but
> **removing** at §H, which is why retiring the unfiltered phase carries the reasoning rather than this note.

> **v0.10 changes.** The retirement v0.9 described is now **executed in code** and ratified
> (**ADR-004**, `super-plan.md` item 1.3). Configuration 4's cascade issues **at most one
> namespace-scoped search**; there is no global search and no `τ_high`. No field is added or removed
> here — `similarity_only_decision` left the schema at v0.9 and leaves the code now — but four keep
> their names and **change meaning**: `similarity` (§A, §H) is the nearest entry *within the query's
> namespace*, `source_overlap` is null unless that entry cleared τ, `entered_band` equals the
> TIER2_HIT indicator while θ is outside the served decision, and `t_search_ms` is one span. The
> extension field `reuse_rule` is now named in §H, because *% reaching the provenance check* is
> computed from it. **Never mix logs from either side of the 1.3 commit in one figure.**

> **v0.11 changes.** §H gains the **answer store**: the text behind every non-empty `answer_sha256`
> is written to `raw/answers/{answer_sha256}.txt` (**ADR-005**, `super-plan.md` item 1.5). Before this
> the log held a hash and the text lived only in the bounded LRU cache, so by the time the judge ran
> offline most `answer_sha256` values named nothing. **No JSON field is added, removed or renamed, and
> no wire shape changes**: §A–§G and the `.proto` are untouched. Two things change meaning without
> changing shape. **(1) A run can now be INCOMPLETE for a new reason** (a hash a record names has no
> file, a line failed to encode or write, the log failed to close, or an answer and its hash disagreed), on top
> of dropped records. **(2) `answer_sha256` is no longer described as "the judge dedupe key"**: a
> Tier-2 hit serves another query's answer byte for byte, so a bare answer hash would merge a true hit
> and a false hit on the same answer into one verdict (see the §H warning). **A log written before the
> 1.5 commit has no answer store and cannot be judged.**

> **v0.8 changes.** `RetrieveRequest` and `AnswerRequest` gain `product_id` (§B). When
> set, retrieval runs its normal unscoped search first, then drops any chunk belonging to a
> *different* product and, if `product_id`'s own chunk did not naturally rank, splices in exactly
> that one chunk — a post-filter on real ranking, never a pre-filter that forces content in.
> Unscoped retrieval over a flat, one-chunk-per-document corpus returns whichever chunk contains
> the query's literal words, regardless of product; reproduced 2026-09-10 by asking a generic
> "power rating" question against three different products and retrieving the same five
> kitchen-appliance chunks for all three. A first implementation pre-filtered candidates to
> `doc_id == product_id OR kind == "policy"` before ranking, which regressed measurably on this
> corpus (only four policy docs, one chunk per product): the eligible pool shrank to near `top_k`,
> so `PolicyFraction` (§B's own reuse machinery, `reuse/lane.go`) saturated toward ~0.8 for almost
> any product-scoped question, collapsing unrelated products into the same policy-dominated
> namespace — confirmed live serving one product's cached answer to a different, unrelated
> product's question. The post-filter design closes that: policy content only ever reaches the
> result when it genuinely ranks, never by construction of a too-small eligible pool. Additive — an
> empty `product_id` preserves the old, unscoped behaviour exactly, and the reuse-decision
> machinery is untouched: this only narrows what retrieval may consider, never
> how a retrieved candidate is judged for reuse.

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

Every request also appends one (H) evaluation-log record to results/{run_id}/raw/, and every answer it serves is stored under results/{run_id}/raw/answers/
```

---

## A. Client ↔ Gateway — HTTP API

### `POST /ask`

Request:

```json
{ "question": "Can I return this laptop after 30 days?",
  "product_id": "product-laptops-01" }
```

| Field | Type | Notes |
| :--- | :--- | :--- |
| `question` | string | Required. |
| `product_id` | string\|null | **Optional (v0.6).** The product the question was asked about — the page a production assistant is embedded in already knows it. Read **only** by the spec lane, to pin which product that lane's namespace names; the policy lane ignores it, because scoping a policy answer by product spends capacity on one answer per product. Absent, the namespace falls back to the rank-1 product document, which is correct but less stable. It is **not** part of the reuse decision and **not** a cache key. |

> ⚠️ **`stratum` is deliberately not a request field.** The evaluation log (§H) carries it, but it is a
> property of the *workload*, not of a client request. The measurement harness may send it as an
> optional `X-Thesis-Stratum` header; absent that, the label joins offline on `query_normalized`,
> which the Tier-1 collision invariant makes exact.

Success response (`200 application/json`) — the six fields the debug UI needs are required, the rest optional:

```json
{
  "answer": "Returns are accepted within 30 days of delivery...",
  "cache": "TIER2_HIT",                    // TIER1_HIT | TIER2_HIT | MISS | BYPASS
  "latency_ms": 48,
  "similarity": 0.93,                       // nearest Tier-2 entry in the query's namespace; null when none was judged (v0.10)
  "source_overlap": 0.80,                   // containment of that entry (Contribution 1); null unless it cleared τ (v0.10)
  "sources": ["policy-returns#chunk-2"],    // provenance tags (Contribution 2); [] on BYPASS
  "model_used": "qwen3.5-2b",                // constant for now (routing rejected)
  "request_id": "01J..."                    // extension: correlation id for tracing/eval
}
```

| Field | Type | Notes |
| :--- | :--- | :--- |
| `answer` | string | Final answer text. |
| `cache` | enum | `TIER1_HIT` \| `TIER2_HIT` \| `MISS` \| `BYPASS`. Drives the debug-UI badge colors (debug UI §3). |
| `latency_ms` | int | Gateway-internal wall time; the eval also records off-box end-to-end separately (an evaluation rule, not an error path). |
| `similarity` | float\|null | Cosine similarity of the nearest Tier-2 entry **within the query's namespace** (v0.10, ADR-004). `null` on TIER1_HIT and BYPASS, when the embedding or retrieval failed, and on a MISS whose namespace holds no entry — a lookalike in another namespace is never searched, so it reports no similarity. |
| `source_overlap` | float\|null | Fraction of the candidate entry's `source_chunk_ids` also returned by retrieval on the incoming query — the rule's score, compared against θ. `null` unless retrieval succeeded and a same-namespace candidate cleared τ (v0.10). While θ is outside the served decision (the served rule is similarity ∧ namespace), such a candidate is always served, so a refusal never carries an overlap. |
| `sources` | string[] | Chunk IDs (§C) that grounded the answer. |
| `model_used` | string\|null | Constant (`qwen3.5-2b`) — retained for forward compatibility with routing (future work). |
| `request_id` | string | Optional; ULID for joining logs to eval records. |

Showing `similarity` and `source_overlap` **side by side** is what makes the contribution observable: a high-similarity, low-overlap miss is the lookalike trap the rule exists to catch (debug UI §4 step 4).

> ⚠️ **v0.10.** With the unfiltered phase retired (ADR-004), a lookalike from **another namespace** is a MISS with `similarity: null`: the scoped search never returns it, so no high similarity appears beside the refusal. Inside a namespace, while θ is outside the served decision, the pairing that remains is a **TIER2_HIT whose `source_overlap` is below θ** — a reuse the containment conjunct would have refused.

### Streaming variant (MISS path — SSE) — *optional, not in scope*

**Dropped from the thesis scope** (miss responses return complete). The shape is retained here so that adding it later is a pure extension, not a contract change. If implemented, a client sending `Accept: text/event-stream` receives a token stream whose terminal `done` event carries the metadata block:

```
event: token
data: {"text": "Returns are "}

event: token
data: {"text": "accepted within 30 days..."}

event: done
data: {"answer": "...", "cache": "MISS", "latency_ms": 4120, "sources": ["policy-returns#chunk-2"], "model_used": "qwen3.5-2b", "request_id": "01J..."}
```

### Backpressure / admission-control response

When the bounded generation-concurrency pool is exhausted and the queue budget is spent (proposal §6.1/§6.2 admission control), the gateway **sheds** rather than admitting a generation that would only queue invisibly inside the model server, which serves one slot (ADR-003):

```
HTTP/1.1 503 Service Unavailable
Retry-After: 2
{ "error": "busy", "reason": "generation_pool_saturated", "request_id": "01J..." }
```

Shed responses are counted by the scalability eval as graceful-degradation events, not errors (an evaluation rule, not an error path).

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
  string product_id = 3;     // optional; scopes the search (v0.8) — see below
}

message RetrieveResponse {
  repeated string chunk_ids     = 1;   // stable chunk IDs, ranked (see §C)
  repeated float  scores        = 2;   // aligned with chunk_ids; retriever similarity
  uint64          dataset_epoch = 3;   // corpus version these chunks came from (§E)
  repeated string texts         = 4;   // v0.9 — chunk text, POSITIONALLY
                                       // ALIGNED with chunk_ids; see below
}

message AnswerRequest {
  string query = 1;
  uint32 top_k = 2;
  bool   stream = 3;         // defaults FALSE in scope (SSE dropped):
                             // a single terminal AnswerChunk is returned
  repeated string retrieved_chunk_ids = 4;  // v0.7 — see below
  string product_id = 5;                    // optional; scopes Answer's OWN fallback
                                             // retrieval when retrieved_chunk_ids is
                                             // empty (v0.8) — see below
}

// **`texts` (v0.9).** `texts[i]` is the text of `chunk_ids[i]`, or the field is absent
// entirely -- there is no partial population. The support gate compares a cached
// answer against this text; the gateway has never held chunk text and the gate cannot run at
// all without it. `text` is a field `store.build_schema()` declares, so this reads a schema
// field, not a storage-layout detail (the distinction single-retrieval settled).
//
// ⚠️ **Alignment is an invariant, not a convention.** A `texts` array shifted by one scores a
// cached answer against the WRONG chunk's text and returns a support verdict that is wrong with
// no error raised anywhere -- the same silent-failure class as the three invariants of v0.3.
// It joins the single-retrieval three obligations on this RPC: return the ids you were given, preserve
// rank order, drop a missing id rather than substitute one, and keep `texts` aligned.
//
// **`product_id` (v0.8).** Optional, on both `RetrieveRequest` and `AnswerRequest`. When
// non-empty, the service runs its normal unscoped top_k search FIRST -- ranking is untouched --
// then POST-filters: drops any chunk belonging to a different product, and if product_id's own
// chunk did not naturally rank, fetches it with one small product-scoped search and splices it
// in (dropping the lowest-ranked survivor to stay within top_k). Empty/absent is bit-for-bit
// today's unscoped search.
//
// Why it exists: unscoped retrieval over a flat, one-chunk-per-document corpus has almost no
// signal to prefer the asked-about product for a generic question — a literal word shared with an
// unrelated product's chunk can win outright. Reproduced 2026-09-10: the same generic "power
// rating" question retrieved identical unrelated chunks across three different products.
//
// ⚠️ Post-filter, not pre-filter -- the first implementation regressed. Pre-filtering candidates
// to `doc_id == product_id OR kind == "policy"` before ranking shrank the eligible pool to near
// top_k on this corpus (four policy docs, one chunk per product), so nearly every candidate
// came back regardless of relevance: PolicyFraction (reuse/lane.go) saturated toward ~0.8 for
// almost any product-scoped question, collapsing unrelated products into the same
// policy-dominated namespace. Confirmed live: product-kitchen-05 (a genuine 1800W power spec)
// was served product-laptops-02's cached "no power info" answer this way. Filtering AFTER
// ranking means policy content only ever appears because it genuinely ranked -- the MIXED lane's
// reason to exist is unaffected, but it can no longer be forced in by construction of
// a too-small eligible pool.
//
// This does not touch the reuse decision. `product_id` here decides what a single retrieval call
// may search over, never whether a retrieved candidate should be reused — `reuse/lane.go`,
// `reuse/rule.go`, and the cache-key functions are unaffected and still derive their partition
// from post-retrieval evidence (that boundary, unchanged).

// **`retrieved_chunk_ids` (v0.7).** Chunk IDs the caller already retrieved for this
// query. When non-empty the service **skips its own retrieval** and grounds generation on exactly
// these chunks; when empty it retrieves as before, so the field is additive.
//
// Why it exists: every Tier-1 miss retrieves at least once — above τ in the cascade, below it
// inside `Answer` — and since the gateway issues its retrieval concurrently with the embedding,
// every miss reached `Answer` having already retrieved, whereupon `Answer` retrieved again. The
// duplicated work is the **query embedding**, not the vector search.
//
// Three obligations on the service, each closing a silent failure:
//
// 1. **Return the ids it was given** in `source_chunk_ids`. Provenance is C1's input and C2's
//    dependency key, so an entry written under a set that differs from the one its answer was
//    generated over corrupts both contributions with no error (rules.md #6).
// 2. **Preserve rank order.** Generation is order-sensitive, and the reuse rule's namespace comes
//    from the rank-1 document *of each kind* — reordering would repartition the cache.
// 3. **Drop a missing id, never substitute.** A fabricated chunk puts text into an answer that no
//    provenance record accounts for; a short context is visible in the answer, an invented one is
//    not.

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

Both provenance (C1) and source-aware invalidation (C2) key on chunk IDs, so the scheme must be **stable across re-chunking** (timeline **W5** implements it, W9–W11 depend on it). It must survive the `dev-v0` → `v1` corpus change: the chunking config is frozen in W5, so `v1` is a content expansion under a new `dataset_version`, not a re-chunk.

- **Format:** `{doc_id}#chunk-{ordinal}` — e.g. `policy-returns#chunk-2` (this exact example is the one in the demo scripd` §2).
- **`doc_id`:** stable slug of the source document, assigned at ingestion and never reused for a different document. ⚠️ **It MUST begin with `policy-` or `product-` (v0.6)** — e.g. `policy-returns-electronics`, `product-laptops-01`. The prefix is the only place the document *kind* is recorded, and the reuse rule reads the lane from it. A corpus built without it classifies every question into the spec lane **silently**, with the lane machinery reporting plausible values throughout, so `data-card.md` §7 checks the prefix at corpus-freeze time alongside G1–G3. Enforced at ingestion in `rag/src/rag/ingest.py:record_kind()`, which raises on any other prefix.
- **`ordinal`:** 0-based position of the chunk within the document under the **frozen chunking config** (size/overlap recorded in `decisions.md`).
- **Re-chunking rule:** if the chunking config changes, IDs are *not* silently reassigned — a re-chunk is a new dataset version (`data-card.md`) and forces a full cache rebuild, so a given `{doc_id}#chunk-{ordinal}` always denotes the same span within one dataset version. This keeps completeness/precision measurable (proposal §5 C2).
- **Uniqueness:** `(dataset_version, chunk_id)` is unique; `chunk_id` is unique within a dataset version.

---

## D. Cache-entry schema (Redis)

Bounded, LRU (proposal §6.3). **Capacity is `round(0.25 × K)`**, where `K` is the frozen workload's distinct-query count — the ratio is frozen study-wide, the absolute is derived at corpus freeze and recorded per run. An absolute capacity was rejected because at `C ≥ K` nothing is ever evicted and the redundancy sweep collapses to a constant.

> ⚠️ **Eviction policy is a correctness constraint, not a tuning knob.** `allkeys-lru` evicts *any* key under pressure — **including the `dep:{chunk_id}` sets of §E**. An evicted dependency record makes its entries permanently unpurgeable, so invalidation completeness fails silently and non-reproducibly. Therefore:
>
> **v0.6 — the gateway evicts; Redis evicts nothing.** The v0.3 split above prescribed two
> regions with different eviction settings. That is **not achievable on one server**: the eviction
> setting is server-global rather than per logical DB, so any `allkeys-*` value can reach `dep:*`. It
> also cannot express the capacity ratio, which is a **count** of entries while `allkeys-lru` evicts by
> **bytes**. Therefore:
>
> - **Redis is configured to evict nothing at all**, and no byte budget is set. `make redis-check`
>   verifies this and fails the run otherwise.
> - **The gateway enforces the count.** A sorted set `lru:entries` holds `entry_id` scored by last
>   access; after each write-back the gateway trims to `round(0.25 × K)` entries.
> - **Both tiers of a victim are deleted together**, the Tier-1 record found through the `t1_key`
>   stored on the Tier-2 record. Dropping only `t2:` would leave Tier 1 serving the same answer from a
>   bare hash lookup that runs no reuse rule — so the entry would still be served while absent from the
>   cache the experiment believes it is bounding, and the capacity sweep would measure nothing.
>
> This is **stronger** than the v0.3 split, not a relaxation: the dependency region is now safe by
> construction rather than by a configuration a later `CONFIG SET` could silently undo. The capacity
> in force is recorded per run; a run whose dependency region lost anything remains **invalid** and is
> repeated.

**Tier 1 — exact match.** O(1) hash lookup, no vector:

```
KEY   t1:{sha256(normalized_query)}      # HASH
      answer            <string>
      source_chunk_ids  <json array>
      model_used        <string>
      created_at        <rfc3339>
      entry_id          <ulid>            # links to the Tier-2 record / dependency map
```

Normalization (lowercase, collapse whitespace, strip punctuation) is specified in `decisions.md` and must match the Tier-1 write path exactly.

> ⚠️ **Tier 1 runs no reuse rule, so its safety is a corpus invariant.** This lookup is a bare hash equality test — no similarity check, no containment check. Two workload queries with different correct answers that normalise to the same string would be served wrongly from first write, permanently, with nothing to detect it. Worse, the resulting false hit has **no bucket** in the evaluation §4's two-cause split and would be charged to the reuse rule, which never ran. The corpus therefore carries the invariant *"no two queries with different `reference_answer` or `doc_ids` share a `normalize(q)`"*, checked before the snapshot is hashed (`data-card.md` §7). Note that stripping punctuation collapses `Model A-1` and `Model A1` — harmless within one product, not harmless across two.

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

`source_chunk_ids` is the load-bearing field for **both** contributions: C1 intersects it with the incoming query's retrieval, C2 indexes it in reverse to build the dependency map (§E). (`question_type` / `answer_type`, auxiliary features for the learned predictor, were removed in v0.2.)

> ⚠️ **`t1_key` exists so that Tier-1 is purgeable.** Tier 1 is keyed by `sha256(normalized_query)`; the dependency map stores only `entry_id`. Without a stored back-pointer the invalidator **cannot compute the Tier-1 key** from a dependency record, so Tier-1 copies of an invalidated answer would survive the purge and continue serving stale content — a completeness hole that no test of the Tier-2 path would reveal. Both tiers are written together on a miss, so `t1_key` is written at the same moment and never diverges.

Vector field: distance metric **COSINE**, `DIM` equals the embedding dimension in §F (they must not drift). Write-back on a full miss populates **both** tiers, tagged with `source_chunk_ids` (proposal §6.3).

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

**Purge decision:** **`blind` only** — purge every `entry_id` in `dep:{chunk_id}`, dropping both the `t2:` record and its `t1_key` (§D). Guaranteed-complete: no answer over a changed source survives. Predictor-gated purging was removed by the scope reduction (it depended on the dropped learned predictor) and is future work (proposal §14).

- `change_type` is recorded **for evaluation only** — it measures how often blind purge over-invalidates on answer-preserving edits (defined with the evaluation metrics). It is never used as a gate: trusting an edit's self-declared type would make completeness depend on the corpus author's labelling.
- `new_text` is carried on the event so a future gated variant needs no corpus round-trip, and so the writer can log what changed.

---

## F. Embedding service

```
POST /embed   { "text": "..." }
200           { "vector": [float32...], "dims": 768, "model": "<frozen-model-id>" }
```

- The embedding model is **frozen** early (proposal §12) — see `decisions.md` the frozen embedding model (**Decided and frozen 2026-08-15**: `nomic-embed-text`, `dims = 768`). It is **served by Ollama**, not by an in-process `sentence-transformers`/PyTorch stack, which would cost ~2 GB resident for a ~400 MB model.
- ⚠️ **This call sits on the hit path.** Every Tier-2 lookup pays an embedding round-trip, so this endpoint's latency directly bounds **μ_hit** — the load-conversion ceiling of proposal §3. Hit-path latency is reported **decomposed** into {Tier-1 lookup, embed, vector search, overlap check} rather than as a single total, so the share attributable to this call is visible.
- `dims` **must equal** the Tier-2 index `DIM` (§D) and be identical across all **five** cache configurations (proposal §9.2 pins one embedding model so comparisons isolate the reuse policy).

---

## G. Bypass classifier

**Demo stub only — not an evaluated component.** The corpus contains no dynamic content and there is no live inventory source, so a learned or evaluated classifier would be scored against a stub while adding a false-hit cause that contaminates the headline. It is therefore a **hardcoded keyword rule** that exists so the demo can show the routing decision (debug UI §1).

```
classify(query) -> { "route": "cacheable" | "bypass", "reason": "<label>" }
```

- `cacheable` → continues into Tier-1/Tier-2. This is the path all evaluation traffic takes.
- `bypass` → returns the stub response, sets `"cache": "BYPASS"`, `sources: []`.
- **Bypass accuracy is not a reported metric**, and `BYPASS` does not appear in the evaluation workload.

---

## H. Per-request evaluation log  ⚠️ measurement-critical

**The evaluation log.** One **JSONL record per request**, appended by the gateway to `results/{run_id}/raw/requests.jsonl`. Written off the critical path. `request_id` (§A) is the join key to the `/ask` response and to judge verdicts.

Four evaluation metrics are **not computable without this record**: *decisions changed by provenance*, *% entering the cascade band*, *false hits by cause*, and the hit-path latency decomposition.

> **The answer store (v0.11, ADR-005).** The gateway keeps the **text** of every answer it serves,
> content-addressed, beside the log:
>
> ```
> results/{run_id}/raw/
> ├── requests.jsonl                 one JSONL record per request
> └── answers/
>     └── {answer_sha256}.txt        the answer exactly as served
> ```
>
> 1. **Name and bytes.** `{answer_sha256}` is the record's field, lowercase hex, 64 characters, plus
>    `.txt`. The file holds the **UTF-8 bytes of the served answer exactly**: no newline added, no
>    normalisation. The file's SHA-256 is its name. Readers match `^[0-9a-f]{64}\.txt$`, **verify the
>    hash when they read**, and ignore anything else. A `.answer-*.tmp` file is residue of a crash or of
>    a failed temp-file removal; readers ignore it.
> 2. **One file per distinct hash,** created once and never rewritten.
> 3. **Every path that serves text writes it:** TIER1_HIT, TIER2_HIT, and MISS, including a MISS whose
>    generation completed though the client left, and a coalesced follower. (An ABANDONED request,
>    rule 4, is one whose generation did not complete.) **A hit writes too**: the entry may predate the run, so
>    a hit can be the first time this run sees its text.
> 4. **No text, no file.** A record that served no answer (the log-only `cache` values SHED,
>    ABANDONED and GENERATION_FAILED, which §A's enum does not carry; or a Tier-1 lookup error) has `answer_sha256` equal to `""` and creates no file. `""` is **not** null.
>    An **empty answer is a real answer**: it hashes to
>    `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` and is stored as an empty file.
>    "Has an answer" means `answer_sha256 != ""`.
> 5. **The invariant. In a run that is not INCOMPLETE,** every record whose `answer_sha256` is non-empty
>    names a file in `answers/` whose bytes hash to that name, and **`answers/` holds no
>    `{answer_sha256}.txt` that no record names**. **Order:** the writer publishes the file before it
>    writes the line that names it (one writer, the file and then the line; nothing is fsynced, and on
>    macOS an `fsync` is not durable without `F_FULLFSYNC`). That is a property of the writer, **not
>    something a reader can check from `raw/`**, and it holds for a hash's first successful write: if
>    the first write failed and a later record with the same hash retried successfully, the first
>    record's line precedes its file. Admissibility turns only on the file existing at the end.
> 6. **INCOMPLETE.** A run is INCOMPLETE, and **not admissible**, if any of these holds when it ends:
>    records were dropped by a full buffer; a record's line failed to encode or write; a hash a record names has
>    **no file** at that moment (a write that failed and was not retried successfully); a record's
>    answer text did **not** hash to its `answer_sha256` (a call site set one without the other: a
>    defect, checked at a hash's first sighting and never cleared by a later retry); or the log failed to close cleanly. The gateway reports
>    this by **exit status and log at shutdown**. **Until the run manifest exists (`decisions.md`
>    P1) the verdict is not recorded in `raw/`**, so *the answers are recoverable from `raw/` alone*
>    holds, and *the run's admissibility is decidable from `raw/` alone* does not.
> 7. **What it proves.** That a file with the right hash exists for each named answer. For valid
>    UTF-8 the bytes also equal what the client decoded from the JSON response; invalid UTF-8 cannot
>    occur in a generated answer, because `AnswerChunk.text` is a proto3 `string` and protobuf-go
>    validates it on unmarshal, and a cached answer is a previously generated one.
>    It does **not** prove that the serving path sent the client the bytes it logged beyond the paths
>    the tests drive.
> 8. **Not covered.** The **retrieved chunk text** (the judge's SOURCE input) is not stored: the log
>    carries `retrieved_chunk_ids`, and the text is recoverable from the frozen corpus **only when
>    `mutation: off`**. Under `mutation: on` the text at serve time depends on
>    the ordered update set and the epoch it had reached: `dataset_epoch_at_retrieval` is logged, but
>    nothing in `raw/` yet records the update set with its epochs.
> 9. **Not published.** `experiments/results/*/raw/` is gitignored: it holds Amazon-PQA question text
>    (`query_raw`) and LLM answers grounded on PQA chunks, redistribution is not granted, and the
>    remote is public. `manifest.yaml` stays trackable.
>
> **What cannot be recovered even so:** a record skipped because it was logged after `Close` (F-F) or
> lost to a `Log`/`Close` race leaves neither a line nor a file, and is not counted. F-F is a
> `super-plan.md` finding with its own fix, the race is part of it per that finding's trail
> (`docs/work/2026-10-04-httpapi-tests/review.md`), and neither is widened by this change.

**v0.10 — the two band-shaped metrics, each with the expression that computes it (ADR-004):**
- ***% reaching the provenance check*** (`Final_Proposal.md` §9): among records with `similarity != null`, the share with `reuse_rule` ∈ {`namespace`, `composite`}. It is **1.0 by construction** once the unfiltered phase is retired, and it is kept as an **invariant check**: a gate re-added before the lane rule leaves `reuse_rule` empty on the requests it settles, and drops the share below 1.0. It is *not* `retrieved_chunk_ids != null`, which reads the same before and after the retirement and measures only retrieval availability.
- ***% entering the cascade band***: among records past Tier 1, the share with `entered_band: true`. While θ and the support gate are outside the served decision it **equals the TIER2_HIT share** (see the `entered_band` note).

```json
{
  "request_id": "01J...",              // ULID, joins to /ask (§A)
  "run_id": "2026-11-18T14-03-02_cfg4_zipf1.1",
  "config_id": 4,                       // 1..5 (proposal §9.2)
  "mutation": "off",                    // off|on
  "ts": "2026-11-18T14:03:02.481Z",

  "query_raw": "How long is the warranty period on the XPS 13?",
  "query_normalized": "how long is the warranty period on the xps 13",
  "t1_key": "t1:9f2c...",               // §D; lets a collision be detected post hoc
  "stratum": "B-within",                // A | B-within | B-cross | C | D

  "cache": "TIER2_HIT",                 // TIER1_HIT | TIER2_HIT | MISS
  "similarity": 0.91,
  "source_overlap": 0.80,               // null unless a same-namespace candidate cleared τ (v0.10)
  "entered_band": true,                 // a same-namespace candidate cleared τ — see the field note, v0.10
  "refusal_cause": "SUPPORT",           // v0.9 — null when reuse was served; see below
  "support_lex": 0.21,                  // v0.9 — null when the gate arm is off
  "support_numeric_ok": false,          // v0.9 — null when the gate arm is off

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

  "answer_sha256": "3a71..."            // the answer's address in raw/answers/ (v0.11); "" when no answer was served
}
```

> ⚠️ **`answer_sha256` is taken when the answer is served and cannot be reconstructed after the fact.**
> It is the `sha256` of the served answer text, and since v0.11 the text itself is kept at
> `raw/answers/{answer_sha256}.txt`, so it can be read back without the cache. The hash must still be
> taken at serve time rather than recomputed from a possibly re-generated answer: the Modelfile sets
> `temperature 1` (U8), so a second generation can be a different answer.
>
> ⚠️ **It is not, by itself, a judge verdict key.** The evaluation keys verdicts by
> `sha256(query ‖ candidate_answer)`. A Tier-2 hit serves a cached answer to a *different* query
> byte for byte, so a true hit `(q1, A)` and a false hit `(q2, A)` share one `answer_sha256`; keyed on
> the answer alone they would collapse into one verdict and the false-hit rate would be biased toward
> whichever came first. The bare `‖` is ambiguous without a delimiter; **item 5.1 fixes it.** The
> layout serves either key, since both are computable from `query_raw` and `raw/answers/`.
>
> ⚠️ **`similarity_only_decision` is RETIRED at v0.9.** It recorded what a fixed-threshold baseline *would* have decided, inline, because re-deriving it would have required replaying against cache state that no longer exists. It was produced by the unfiltered similarity-only cascade phase, and it is retired **with** that phase. *Decisions changed by provenance* is now a **cross-configuration join** of configurations 3 and 4 on `request_id`'s query identity — valid only on the **static-cache** arm, where both runs are guaranteed identical cache state, which is why retiring the unfiltered phase moves that arm into the non-negotiable list. A log written before the **1.3 commit** carries the old field — the code emitted it until then (ADR-004), so a log dated after v0.9 can still carry it; do not mix the two derivations in one figure.

Field notes:

| Field | Notes |
| :--- | :--- |
| `stratum` | Carried from the workload record (`data-card.md` §2). Enables the frontier to be reported per sub-stratum, which is what answers the product-ID objection |
| `t1_key` | Recording it lets the Tier-1 collision invariant be re-verified from run output, not only at corpus-freeze time |
| `answer_sha256` | **v0.11.** The SHA-256 of the answer text as served, lowercase hex, and the name of the file that holds that text in `raw/answers/`. `""` (not null) means no answer was served. See "The answer store" for the invariant and for what makes a run INCOMPLETE |
| `entered_band` | ⚠️ **v0.10 (ADR-004) restates it again: a same-namespace candidate cleared τ.** The band is [τ, 1], because `τ_high` is retired, so it no longer separates short-circuit hits from band hits — there is no short-circuit. While the served rule is similarity ∧ namespace (θ and the support gate outside it), it **equals the TIER2_HIT indicator**, so *% entering the cascade band* is the Tier-2 hit share until either joins. That gives an invariant: `entered_band ∧ cache ≠ TIER2_HIT` never occurs, and one would mean the Redis TAG filter and Go's `MatchNamespace` disagree. *History:* it first distinguished short-circuit hits from cascade-band hits. ⚠️ **v0.6 restates what this measures.** It was *"paid for retrieval — the rule's cost driver"*. Since the gateway issues retrieval **concurrently with the embedding**, every Tier-1 miss pays for retrieval whether or not it enters the band, so this now records **how often the rule consulted provenance** and no longer bounds what the rule costs. Read `t_overlap_ms` for the cost, and note it is wall-clock-concurrent with `t_embed_ms` |
| `refusal_cause` | **v0.9.** Why a Tier-2 candidate was refused: `SIMILARITY` \| `NAMESPACE` \| `CONTAINMENT` \| `SUPPORT` \| `NONE` (reuse served). Without it a support refusal is indistinguishable from a namespace refusal and the adopted gate's contribution cannot be attributed — which is the exact methodological gap this study records against the source paper's conjunctive reporting. ⚠️ **v0.10:** in configuration 4 the namespace is enforced **by the search, not by a refusal** (ADR-004). A request whose namespace holds no candidate is a MISS with no candidate, and **is not a `NAMESPACE` refusal** — coding it as one would turn a cold cache or an empty namespace into namespace refusals in *false hits by cause*. `NAMESPACE` is reachable only if the Redis filter and Go's check disagree. The namespace conjunct's effect is counted by the configurations 3 ⋈ 4 join, not by this field |
| `reuse_rule` | **Extension field, named here at v0.10** (not in the example above). The rule variant that judged the Tier-2 candidate: `namespace` (SPEC, POLICY) or `composite` (MIXED). **Present iff a candidate was judged, refusals below τ included, so its presence is not a hit.** *% reaching the provenance check* is computed from it (ADR-004), so it must not be dropped as an optional extension |
| `support_lex` / `support_numeric_ok` | **v0.9.** The two gate arms, **reported separately and never summed**. `support_lex` is the fraction of the cached answer's content tokens present in the fresh evidence; `support_numeric_ok` is the fail-closed numeric check. Both null on the gate-off arm of configuration 4, which is how the two arms are told apart in the log itself |
| `t_*_ms` | Null where the stage did not run. Sum need not equal `t_total_ms` — the difference is gateway overhead and is reported as such. ⚠️ **v0.10:** `t_search_ms` is **one** namespace-scoped search, no longer the sum of a global and a scoped one. It is null **exactly when no search ran**: the embedding or retrieval failed, or the query's namespace resolved to the empty string. A search that ran and found nothing (a cold cache) or errored still carries its span, so a MISS can show `similarity: null` beside a non-null `t_search_ms`. It is not comparable across the 1.3 commit |
| `writeback_discarded` | A nonzero count under load is evidence the epoch guard is working, not a bug (§E) |

> `raw/` is write-once, so `requests.jsonl` **and every file under `answers/`** are immutable once a
> run completes. A run id is never reused: the gateway creates `requests.jsonl` exclusively and then
> `answers/` (non-recursively) and **refuses to start** if either already exists.

---

## Versioning

These contracts are frozen for the study. A change to any wire shape, the chunk-ID format, the Redis schema, or the §H run layout under `raw/` is a design decision: add a dated entry to `decisions.md` and bump this file's version. Silent drift here invalidates cross-configuration comparisons (proposal §12).

**Current version: v0.11** (2026-10-06).

| Version | Date | Change |
| :--- | :--- | :--- |
| **v0.11** | 2026-10-06 | §H gains the **answer store**: the text behind every non-empty `answer_sha256` is written to `raw/answers/{answer_sha256}.txt`, so a run's answers are recoverable from `raw/` alone with the cache flushed (**ADR-005**, item 1.5). No JSON field changes and no wire shape changes: §A–§G and the `.proto` are unchanged. A run is now also INCOMPLETE when a named hash has no file, a line failed to encode or write, the log failed to close, or an answer and its hash disagreed. `answer_sha256` is no longer called the judge dedupe key (a bare answer hash cannot key Tier-2 verdicts). `raw/` is gitignored. A log written before the 1.5 commit has no store and cannot be judged |
| **v0.10** | 2026-10-05 | The v0.9 retirement is **executed in code** and ratified by **ADR-004**: configuration 4's cascade issues at most one namespace-scoped search, with no global search and no `τ_high`. No wire field is added or removed. `similarity`, `source_overlap`, `entered_band` and `t_search_ms` keep their names and **change meaning** (§A, §H); `refusal_cause`'s `NAMESPACE` is restated; the extension `reuse_rule` is named in §H. §B, §C, §D, §E and the `.proto` are unchanged. Logs from either side of the 1.3 commit must not be mixed |
| **v0.9** | 2026-09-21 | §B `RetrieveResponse` gains **`texts`**, positionally aligned with `chunk_ids` — the support gate compares a cached answer against chunk text the gateway had never held, so without this it cannot run at all. §H gains **`refusal_cause`** and the two support-arm fields, making the gate's contribution attributable rather than inferred from a conjunction. §H's `similarity_only_decision` is **retired** together with the unfiltered cascade phase and the `tau_high` knob that produced it, which moves *decisions changed by provenance* to a cross-configuration join valid only on the static-cache arm |
| v0.8 | 2026-09-10 | §B gains an optional `product_id`, scoping `Retrieve`/`Answer`'s own corpus search to the asked-about product plus all policy content. It closes a cross-product grounding failure that unscoped search could not avoid on a flat corpus, and it is **never a reuse-decision signal**. `Answer` may accept pre-retrieved chunks, so a request retrieves once rather than twice |
| v0.6 | 2026-08-2× | §A gains an optional `product_id`; §C fixes the `policy-` / `product-` doc-id kind prefix; §D moves eviction into the gateway; §H restates what `entered_band` measures |

**Frozen study-wide, from measurement or by policy — changing any of these mid-study invalidates every comparison:** the generation LLM, Qwen 3.5 2B `q4_K_M` with `think: false` · the embedding model and `DIM` · `top_k` · the **FLAT (exact) vector index** — no mid-study HNSW upgrade, since approximate retrieval would inject overlap noise indistinguishable from C1's signal · `num_ctx = 8192` and **one served generation slot**, with the Ollama server version (0.33.2) and the LLM weights blob pinned beside them (the envelope, **ADR-003**: Ollama serves the `qwen35` architecture at one slot whatever `OLLAMA_NUM_PARALLEL` requests, so the earlier `= 4` was never in effect; `make env-check` verifies all of it against the live runner) · the **cache-capacity ratio `C/K = 0.25`** and the rule that **Redis evicts nothing while the gateway enforces the entry count** (§D — this supersedes the two-region split frozen at v0.3) · the **`policy-` / `product-` doc-id kind prefix** (§C), on which the reuse rule's lane selection depends.
