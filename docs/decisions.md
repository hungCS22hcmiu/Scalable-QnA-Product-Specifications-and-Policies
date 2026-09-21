# Decision Log (ADRs)

**Status:** living document · **Created:** 2026-07-23 · **Last revised:** 2026-09-21 (ADR-035…040)
**Companion to:** `Final_Proposal.md` (rationale source), `interfaces.md` (schemas these decisions pin), `time_line.md` (decide-by weeks).

> **Read ADR-016 first.** It records the 2026-08-09 scope reduction and supersedes or closes several entries below. Section references in older entries point at the archived proposal; the mapping to current sections is in ADR-016.

**How to use.** One entry per architecturally significant choice. `Decided` choices are **frozen** for the study (swapping a frozen model/threshold mid-study invalidates cross-configuration comparisons — proposal §10). `Open` choices carry a **decide-by week** from `time_line.md`; when resolved, flip the status, add the date, and keep the entry (do not delete — the write-up's design chapter and the defense Q&A draw from this history). Entries seeded from the proposal are dated 2026-07-23 and marked *ratified in proposal*.

| ID | Decision | Status | Decide-by |
| :--- | :--- | :--- | :--- |
| ADR-001 | Go for the gateway | Decided | — |
| ADR-002 | Gemma 4 E4B / Ollama / 4-bit | **Superseded by ADR-021** | — |
| ADR-003 | Embedding model: `nomic-embed-text`, 768-dim | **Decided (frozen)** | — |
| ADR-004 | Redis + RedisVL for cache & corpus vectors; no Elasticsearch | Decided | — |
| ADR-005 | Bounded cache, fixed capacity + LRU | **Decided** (capacity ADR-027; mechanism ADR-031) | — |
| ADR-006 | False-hit budget δ ≤ 5% | Decided (provisional) | finalize W14 |
| ADR-007 | gRPC, with a retrieval-only RPC for the C1 cascade | Decided | — |
| ADR-008 | Stable chunk-ID scheme `{doc_id}#chunk-{ordinal}` | Decided | — |
| ADR-009 | Single-node envelope; scale-out = future work | Decided (scope) | — |
| ADR-010 | Predictor-gated invalidation w/ blind-purge fallback | **Superseded by ADR-016** | — |
| ADR-011 | Small routing model (RQ4) | **Rejected by ADR-016** | — |
| ADR-012 | Load generation off-box | Decided · **amended by ADR-040** | — |
| ADR-013 | Project LICENSE | **Open** | **W7** (before submission) |
| ADR-014 | Chunking: size=256, overlap=40, top_k=5 | **Decided (frozen)** | — |
| ADR-015 | Tier-1 query normalization | Decided | — |
| **ADR-016** | **Bachelor-scope reduction (60/25/15)** | **Decided (scope)** | — |
| **ADR-017** | **Envelope frozen from measurement; embeddings via Ollama** | **Decided (frozen)** | — |
| **ADR-018** | **Bypass classifier dropped (demo stub only)** | **Decided (scope)** | — |
| **ADR-019** | **C1 validity: labelling ablation + split discipline** | **Decided (method)** | — |
| **ADR-020** | **Schedule compression; two-corpus split (`dev-v0` / `v1`)** | **Decided (scope)** | — |
| **ADR-021** | **Generation LLM: Qwen 3.5 2B replaces Gemma 4 E4B** | **Decided (frozen)** | — |
| **ADR-022** | **Admission control: permit pool, bounded queue, explicit shed** | **Decided** | — |
| **ADR-023** | **Five configurations × source-mutation axis** | **Decided (experiment design)** | — |
| **ADR-024** | **`v1` corpus data model + sensitivity-gate overlap formula** | **Decided (data)** | — |
| **ADR-025** | **No message broker; invalidation events stay in-process** | **Decided (scope/arch)** | — |
| **ADR-026** | **C1 narrowed: provenance-gated reuse is concurrent work** | **Decided (research positioning)** | — |
| **ADR-027** | **Cache capacity = 0.25·K, and S1 restated** | **Decided (experiment design)** | — |
| **ADR-028** | **`v1`: within-product stratum B + Tier-1 collision invariant** | **Decided (data)** | — |
| **ADR-029** | **Per-request evaluation log** | **Decided (method)** | — |
| **ADR-030** | **Reuse rule v2: third lane for multi-source questions** | **Decided (method)** | — |
| **ADR-031** | **Cache capacity is an entry count enforced by the gateway** | **Decided (frozen)** | — |
| **ADR-032** | **`interfaces.md` v0.6: `product_id` on `/ask`; doc-id kind prefix** | **Decided (frozen)** | — |
| **ADR-033** | **`Answer` accepts pre-retrieved chunks; one retrieval per request** | **Decided (frozen)** | — |
| **ADR-034** | **`Retrieve`/`Answer` gain `product_id`: scope the search, not the reuse decision** | **Decided (frozen)** | — |
| **ADR-035** | **Adopt the answer–evidence support gate (lexical at the published τ_s, plus a numeric arm)** | **Decided (method)** | — |
| **ADR-036** | **Retire the unfiltered similarity-only phase, `tau_high`, and the inline counterfactual** | **Decided (method)** | — |
| **ADR-037** | **`Retrieve` returns chunk text — `interfaces.md` v0.9** | **Decided (frozen)** | — |
| **ADR-038** | **Condition-splitting is a `v1` corpus requirement** | **Decided (data)** | — |
| **ADR-039** | **`v1` corpus source: Amazon-PQA; redistribution stays closed** | **Decided (data)** | — |
| **ADR-040** | **Co-hosted load generation, bounded: amends ADR-012** | **Decided (method)** | — |

---

### ADR-001 — Go for the gateway
**Decided** · 2026-07-23 · *ratified in proposal §6.1, §5.*
Implement the caching/concurrency/governance gateway in Go.
- **Tier: architectural, not research (proposal §7.0).** This is an implementation choice. If Go were replaced by Java or Rust, **every hypothesis in this thesis would be tested identically** — no claim of Go's superiority is made, and no cross-language comparison is run or needed.
- **Rationale:** the governance mechanisms under study — a permit semaphore, a channel-serialized writer, a copy-on-write pointer swap — are expressed directly in Go's standard primitives (`sync.RWMutex`, `atomic.Pointer`, channels, `singleflight`, `x/sync/semaphore`) rather than through a framework; and the runtime's ~20 MB idle footprint is negligible against an envelope where an ML-runtime alternative costs ~2 GB — roughly one concurrent generation slot (ADR-017).
- **Alternatives:** Python — rejected on the envelope: the GIL blocks the concurrency model, and the footprint competes with KV cache. **Rust — not rejected on merit**; it would satisfy the same requirements. Go was selected over it for delivery speed within a ~250 h part-time budget, which is a **project-management** reason and is recorded as such. *It is deliberately excluded from the scientific justification in proposal §7.0* — "the author is faster in Go" is not evidence, and a reviewer asking "would Java invalidate the research?" must get the answer *no*.
- **Experimental control:** the same runtime and gateway build are held constant across **all** experimental configurations, so no measured difference between configurations can originate in the language choice.
- **Consequences:** Go↔Python boundary needs a defined RPC (ADR-007).
- **Revised 2026-08-18** (advisor review): rationale reframed to separate scientific justification from project-management rationale. The decision itself is unchanged; nothing is invalidated.

### ADR-002 — Local LLM: Gemma 4 E4B via Ollama
**Superseded by ADR-021** · decided 2026-07-23 · rev. 2026-08-09 (ADR-017) · superseded 2026-08-15 · *ratified in proposal §5, §7.*
~~Gemma 4 E4B, 4-bit quantized, served by Ollama, with `num_ctx`/`OLLAMA_NUM_PARALLEL` set from the W5 feasibility spike (ADR-017).~~
- **Now in force:** **ADR-021** — generation moves to Qwen 3.5 2B. The W5 spike measured Gemma 4 E2B (the smallest Gemma 4 variant, smallest available quant) against the machine's real available memory and found it enters **yellow** pressure even at the lightest config (`num_ctx=4096`, `NUM_PARALLEL=1`) — exactly the condition ADR-017 named as its own escalation trigger.
- **Rationale (historical):** edge-optimized, small footprint; local hosting removes API cost and keeps latency reproducible; consumed as a black box (not a contribution).
- **Consequences (historical):** freezing is mandatory — a mid-study swap invalidates every cross-config and cross-load comparison. No runs executed under this choice, so superseding it invalidates nothing.

### ADR-003 — Embedding model
**Decided (frozen)** · 2026-08-15 · *proposal §7, §9.2.*
**`nomic-embed-text` via Ollama, DIM = 768** (empirically confirmed via a live `/api/embed` call
before freezing — not assumed).
- **Rationale:** Ollama-servable (no in-process PyTorch/`sentence-transformers`, respecting
  ADR-017/`.docs/ai/rules.md` #7, #9); 274 MB on disk — small next to the 1.7 GB generation LLM
  (ADR-021) already resident within the ~5-6 GB operating ceiling; the most widely-used Ollama
  embedding model, marketed specifically for retrieval/RAG; beats `text-embedding-ada-002` on
  short/long-context retrieval per its model card.
- **Alternatives:** `all-minilm` (384-dim, ~46 MB — smaller/weaker, kept as a reserve option if
  RAM ever tightens further, same role Gemma 3 1B plays for ADR-021); `mxbai-embed-large` /
  `bge-m3` (1024-dim, 670 MB–1.2 GB — better MTEB scores but 2-4x the footprint, unjustified for a
  44-document `dev-v0` corpus).
- **Implementation note:** Nomic's models use task-prefix conventions
  (`"search_document: "` for indexed text, `"search_query: "` for queries) — omitting this
  degrades retrieval silently rather than erroring, so it is handled once in
  `rag/src/rag/embedding.py`, not duplicated at each call site.
- **Constraint:** its output dimension fixes the Tier-2 index `DIM` (`interfaces.md` §D) and is pinned identically across all **five** cache configs so comparisons isolate the reuse policy, not embedding quality (proposal §9.2).
- **Consequences:** `rag/src/rag/config.py` pins `EMBEDDING_MODEL`/`EMBEDDING_DIM`; changing either mid-study invalidates every cross-configuration comparison.

### ADR-004 — Redis + RedisVL; no Elasticsearch
**Decided** · 2026-07-23 · *proposal §5; reaffirmed after an Elasticsearch scoping review.*
Redis (Redis Stack / RedisVL) is the cache store, the Tier-2 vector index, and the corpus vector store. No dedicated heavyweight vector DB. **The index is `FLAT` (exact) and frozen study-wide** — ~~FLAT → HNSW~~ was revised 2026-08-09: an approximate index makes `retrieve(q)` nondeterministic and would inject overlap noise indistinguishable from C1's signal.
- **Rationale:** in-memory sub-ms lookups on the latency-critical hit path; TTL + LRU + native vector search in one store; the cache is small (compact footprint). A JVM service (Elasticsearch/OpenSearch) would antagonize the memory-pressure discipline (§7) it is the thesis's job to protect.
- **Alternatives:** Elasticsearch/OpenSearch hybrid retrieval — deferred to future work (ADR-009); the "hybrid retrieval sharpens the provenance signal" angle is a §12 experiment, not core.

### ADR-005 — Bounded cache with LRU, in two eviction regions
**Decided (capacity value Open, set-by W8)** · 2026-07-23 · rev. 2026-08-09 · *proposal §6.3; `interfaces.md` §D.*
Fixed capacity with LRU eviction for **cache entries**, in all experiments — and **`noeviction` for dependency state**.
- **Rationale:** reproducible, honest results; a bounded cache is a well-behaved memory citizen on the envelope.
- **⚠️ Revised 2026-08-09 (advisor review):** a single `allkeys-lru` policy evicts *any* key, **including `dep:{chunk_id}` sets**. An evicted dependency record makes its entries permanently unpurgeable, so C2's completeness would fail **silently and non-reproducibly**. Cache entries and dependency state therefore live in separate logical DBs/instances with different policies (equivalently: one instance under `volatile-lru` with TTLs only on cache entries). A run whose dependency region evicted anything is invalid and repeated.
- **Capacity — resolved by ADR-027 (2026-09-02):** capacity is `round(0.25 × K)` where `K` is the frozen workload's distinct-query count. The **ratio** is frozen study-wide, the absolute is derived at corpus freeze and recorded per run. An absolute capacity was rejected because at `C ≥ K` nothing is ever evicted and the redundancy sweep collapses to a constant. The dependency region is a few MB and needs no capacity planning.

### ADR-006 — False-hit budget δ ≤ 5%
**Decided (provisional; finalize when judge error is measured, ~W14)** · 2026-07-23 · rev. 2026-08-09 · *proposal §10.*
Compare frontiers at δ ≤ 5%, chosen for measurability.
- **Rationale:** δ must clearly exceed the LLM judge's measured error (the metric noise floor); the human-verified sample pins judge accuracy only coarsely.
- **Revised by ADR-016:** the human-verified sample is **~100 pairs** (was ~200), and frontier points are reported with **Wilson score intervals** rather than sized by a binomial power analysis — the power calculation implied a judging volume (~10k judged hits/point) the budget cannot fund.

### ADR-007 — gRPC with a retrieval-only RPC
**Decided** · 2026-07-23 · *proposal §5 C1, §7; `interfaces.md` §B.*
Go↔Python over gRPC, exposing **both** `Answer` (retrieve+generate) and `Retrieve` (retrieval only).
- **Rationale:** the C1 cascade needs source-overlap from retrieval **without** generation — "the retriever doubles as a reuse-safety oracle." A single answer RPC would force generation to get the overlap, destroying the cascade's latency-preservation purpose.
- **Unaffected by ADR-016:** the overlap *rule* needs retrieval on the incoming query exactly as the learned predictor would have, so this RPC and the cascade survive the scope reduction intact.
- **Why an RPC and not a message broker (added 2026-08-18).** The gateway cannot answer until RAG does, and the cascade needs retrieval results *before* deciding reuse — both interactions are synchronous and request-scoped. Putting a broker between them would rebuild request/response on top of messaging (correlation IDs, response topics, timeout handling, duplicate suppression) while inserting producer, broker, and consumer scheduling into **the exact critical path whose latency is the measurement**, and would consume memory inside an envelope ADR-017 measured at ~5–6 GB free. Event delivery does suit the **source-mutation** path, where nothing blocks on a client; that stays an open architectural question, and the shipped design is an in-process channel to a single writer goroutine (`interfaces.md` §E), which is sufficient at single-node scope (ADR-009).
- **Tier: architectural, not research (proposal §7.0).** **No claim is made that gRPC outperforms REST** — at generation costs measured in seconds, serialization overhead is not the interesting variable. REST/JSON is retained on the client→gateway edge (`interfaces.md` §A), where interoperability matters more than framing cost.
- **Experimental control:** the transport stack is **held constant across every configuration**, and gateway↔RAG overhead is measured separately as its own latency component. Without this, a frontier difference between configurations 3 and 4 could originate in the transport rather than in the reuse rule. ⚠️ **Channel concurrency is configured and recorded per run, never left at defaults:** HTTP/2 caps concurrent streams per connection, and an exhausted channel queues *client-side*, which would be indistinguishable from gateway saturation in the admission-control results (§9.4).

### ADR-008 — Stable chunk-ID scheme
**Decided** · 2026-07-23 · *`interfaces.md` §C.*
`{doc_id}#chunk-{ordinal}` (e.g. `policy-returns#chunk-2`), unique within a dataset version; re-chunking creates a new dataset version and a full cache rebuild rather than reassigning IDs.
- **Rationale:** provenance (C1) and invalidation (C2) both key on chunk IDs; stability is what makes completeness/precision measurable. Depends on the frozen chunking config (ADR-014).

### ADR-009 — Single-node envelope; scale-out = future work
**Decided (scope)** · 2026-07-23 · *proposal §7, §12.*
All experiments on one MacBook M1 (16 GB). Horizontal scaling / multi-pod, database sharding/partitioning, and a fronting load balancer (NGINX) are **out of scope**.
- **Rationale:** the contribution is single-envelope *load conversion*; the LLM (not the gateway) is the bottleneck, so replicating the gateway buys nothing and replicating the LLM exceeds the hardware budget. The interesting distributed problem — distributed cache-coherence for the invalidation map — is deferred to §12.
- **Consequence:** load generation still runs on a second machine (ADR-012), but the system-under-test is single-node.

### ADR-010 — Predictor-gated invalidation with blind-purge fallback
**Superseded by ADR-016** · decided 2026-07-23 · superseded 2026-08-09 · *proposal §5 C2, RQ3.*
~~On a source edit, re-score the reuse-safety predictor (new chunk vs. old answer) and purge only if no longer reuse-safe.~~
- **Now in force:** **blind dependency-purge only** — the guaranteed-complete option this ADR always named as the fallback. It becomes the sole mechanism because ADR-016 drops the learned predictor the gate depended on.
- **Preserved:** the update set keeps its `substantive` / `cosmetic` split, so blind purge's **over-invalidation is measured and reported** rather than assumed away. Predictor-gating moves to future work (proposal §14).

### ADR-011 — Small routing model (semantic routing, RQ4)
**Rejected by ADR-016** · opened 2026-07-23 · closed 2026-08-09.
~~Whether to add a small open-weights model for easy/hard routing.~~
- **Outcome:** not shipped. Semantic routing needed a second model resident in the same 16 GB envelope, a classifier, and its own correctness evaluation (RQ4) — cost the reduced budget cannot carry. **RQ4 is deleted**; routing moves to future work (proposal §14).

### ADR-012 — Load generation off-box
**Decided** · 2026-07-23 · *proposal §7.*
k6/Locust runs on a separate machine on the LAN, never co-hosted with the system-under-test.
- **Rationale:** a co-hosted generator steals CPU from the gateway/LLM in the exact high-load region being measured. If no second machine is available for a run, generator interference is measured and reported.

### ADR-013 — Project LICENSE
**Open** · decide-by **W7 — before the pre-thesis submission** · *proposal §11, §13 (open-source deliverable).*
Pick an OSI license before the first public push.
- **Consideration:** interacts with dataset redistribution terms (`data-card.md`); the self-authored policy corpus is author-owned and freely releasable, but Amazon-derived data may not be redistributable — the license and the data-release policy must be consistent.

### ADR-014 — Chunking config (size / overlap / top_k)
**Decided (frozen)** · 2026-08-15 · *proposal §6; `interfaces.md` §C.*
**`chunk_size = 256` tokens, `chunk_overlap = 40` tokens (~16%), `top_k = 5`.**
- **Rationale — `top_k=5`:** already the default written into `interfaces.md` §B's `RetrieveRequest` proto comment; this formalizes rather than invents it.
- **Rationale — `chunk_size=256`:** the corpus is short structured text (product specs, policy paragraphs), not long-form prose. A coarser size (e.g. 512+) risks collapsing a policy document into 1-2 chunks, making source-overlap near-binary and undermining the exact phenomenon the corpus sensitivity gate (`data-card.md` §7) exists to protect — the provenance signal needs queries that are similar but ground in genuinely different chunks, which requires policy documents to actually split into several chunks.
- **Rationale — `chunk_overlap=40`:** standard 10-20%-of-`chunk_size` heuristic; preserves context across a chunk boundary without materially inflating index size or creating near-duplicate chunks.
- **Consequence:** defines chunk ordinals (ADR-008); changing any of the three later forces a new dataset version and cache rebuild (`interfaces.md` §C's re-chunking rule). `rag/src/rag/config.py` pins these values.

### ADR-015 — Tier-1 query normalization
**Decided** · 2026-07-23 · *`interfaces.md` §D.*
Normalize queries for the Tier-1 hash key by: lowercase → collapse internal whitespace → strip surrounding/most punctuation.
- **Rationale:** catches trivial exact-repeat variants at O(1) before spending an embedding call. The identical function must be used on read and write paths, or Tier-1 hit rate is understated.

### ADR-016 — Bachelor-scope reduction (60 / 25 / 15)
**Decided (scope)** · 2026-08-09 · *supersedes the Contribution Profile of the archived proposal; ratified in `Final_Proposal.md` §2.*

Rebalance the thesis from **40 % systems / 40 % AI research / 20 % cache** to **60 % System Design / 25 % Applied-LLM / 15 % semantic cache**, cutting scope along the ML axis while preserving the research claim.

**Rationale.** Two facts invalidated the original plan. (i) **Budget:** the author works full-time and has 2–3 days/week (~15 h) for ~18 remaining weeks — roughly **250 effective hours**, against the ~360 the old plan assumed remained. (ii) **Skill profile:** the 40 % research pillar rested on a *learned* reuse-safety predictor (feature engineering, gradient-boosted trees, train/val/test discipline, AUC/calibration) — entirely in the author's weakest area, against a backend-engineering strength in Go, Redis, gRPC, and load testing. A third fact made action urgent: at the time of this decision, four of twenty-two weeks had elapsed with **zero lines of code** and the pre-thesis defense five weeks away.

**Dropped → future work (`Final_Proposal.md` §14).**

| Dropped | Why | Consequence |
| :--- | :--- | :--- |
| Learned reuse-safety predictor | ~3 weeks + an ML learning sprint, in the weakest area | C1 is now the **deterministic source-overlap rule**; the research claim is unchanged |
| Predictor-gated invalidation | Depended on the predictor | ADR-010 superseded → **blind purge only** |
| GPTCache / vCache **integration** | 2-week timebox on unmaintained external code, immediately before the evaluation weeks (was the top High/High risk) | GPTCache's rule **is** config 3, reimplemented in-harness; vCache compared on design, not measured |
| Semantic routing (RQ4) | Second model in the same envelope + classifier + its own eval | ADR-011 rejected; **RQ4 deleted** |
| SSE streaming | Complicates latency measurement for cosmetic gain | Miss path returns a complete answer |

**Shrunk.** Eight cache configs → **five**; corpus 500–2,000 products → **~150** plus 8 policy documents; human-verified judge sample 200 → **~100**; binomial power analysis → **Wilson score intervals** (ADR-006); Zipf sweep → **three** skew levels; repetitions ≥5 → **≥3** (5 where time permits); "containerized" deliverable → **Ollama native on the host** + compose for gateway/Redis/RAG, since Docker on macOS has no Metal GPU passthrough and containerizing the LLM would invalidate every latency measurement.

**Why the research claim survives.** The claim is *retrieval provenance is a better reuse-safety signal than embedding similarity alone*. It is tested by **config 3 vs config 4** — fixed cosine threshold vs. the source-overlap rule — with no model training involved. The archived proposal already argued the point: *"the signal is the contribution; the model is the combiner."* A learned combiner is calibration on top, and the rule is the experiment that says whether it is worth building.

**Consequences.**
- Every remaining deliverable is Go, Redis, gRPC, or experiment-running. **No ML expertise is on the critical path.**
- `pre_thesis-Proposal.md` moves to `archive/` with a superseded banner; `Final_Proposal.md` is the source of truth.
- Section-reference mapping for older entries in this log: old §2→**§4**, §3→**§5**, §4→**§6**, §5→**§7**, §6→**§8**, §7→**§9**, §8→**§10**, §10→**§12**, §11→**§13**, §12→**§14**.
- **To confirm with the advisor:** that dropping the learned model while keeping the provenance claim is acceptable. This is the one element of the reduction that changes the thesis's character.

### ADR-017 — Envelope frozen from measurement; embeddings served by Ollama
**Decided (frozen)** · opened 2026-08-09 · decided 2026-08-15 · *proposal §7; `experiment-protocol.md` §1.1.*

`num_ctx` and `OLLAMA_NUM_PARALLEL` are set from the feasibility spike, not assumed, and frozen study-wide at **`num_ctx = 8192`, `OLLAMA_NUM_PARALLEL = 4`**.

- **Why this was not a detail.** The previous value (`num_ctx = 8192`, ADR-002) was never checked against a memory budget, and the check mattered more than expected: the author's machine runs other projects continuously and is disciplined to ~9–10 GB used / ~5–6 GB free before testing, not a dedicated 16 GB envelope. Against that real constraint, the originally frozen model (Gemma 4 E2B — the smallest Gemma 4 variant, smallest available quant) entered **yellow** memory pressure (`kern.memorystatus_vm_pressure_level=2`) at the lightest possible config: 7.7 GB resident at `num_ctx=4096`, `NUM_PARALLEL=1`, a single request.
- **Escalation executed.** Per this ADR's own clause ("if even `NUM_PARALLEL=1` cannot hold green at `num_ctx=4096`, escalate to a smaller quantization or model"): no smaller official quant exists for Gemma 4 E2B, so five alternative models were measured empirically for memory footprint and RAG-QA reasoning quality. **See ADR-021** for the full comparison and the chosen replacement, Qwen 3.5 2B.
- **Frozen pair, measured.** At `num_ctx=8192`, `NUM_PARALLEL=4` (the largest cell tested — the earlier go/no-go's "`NUM_PARALLEL ≥ 2`" bar is cleared with margin), Qwen 3.5 2B holds **1.7 GB resident, green pressure**, under sustained concurrent load with realistic short structured prompts (4 concurrent requests, 8.9 s wall time).
- **μ_gen = 28.2 tokens/sec aggregate** at the frozen pair — the denominator of every load-conversion claim (proposal §3). This is a spike-level measurement (one batch of concurrent requests to completion); the fuller sustained-load characterization is the W7 in-process probe and the W18–19 campaigns (`time_line.md`).
- **Embeddings are served by Ollama**, not by an in-process `sentence-transformers`/PyTorch stack: torch costs ~2 GB resident for a ~400 MB model, which the envelope cannot spare. This also removes torch from the RAG service's dependency surface. Unaffected by ADR-021 — the embedding model itself is still open (ADR-003).
- **Redis is not a memory concern.** At this corpus size the cache, corpus vectors, and dependency map together are tens of megabytes. Do not spend time tuning cache capacity for memory reasons.
- **Headroom.** With the generation model resident (1.7 GB) against the ~5–6 GB operating ceiling the author maintains before testing, comfortable margin remains for the embedding model, Redis, the Go gateway, and the Python RAG service — none of which exist yet as of this freeze (`gateway/`, `rag/src/rag/` are still scaffolds). **Re-verify the combined footprint once they do**, before relying on this margin for concurrency headroom.
- **Output:** the memory-budget table in `experiment-protocol.md` §1.1 is filled from this spike.

### ADR-018 — Bypass classifier dropped; demo stub only
**Decided (scope)** · 2026-08-09 · *proposal §6.3; `interfaces.md` §G.*

No learned or evaluated cacheable-vs-dynamic classifier. A hardcoded keyword rule serves the demo.

- **Rationale:** the corpus contains **no dynamic content** and there is no live inventory source — the classifier would be evaluated against a stub. Worse, it injected a false-hit *cause* (bypass misroute) into the headline metric, so a classifier error would have been charged against the reuse rule.
- **Consequences:** "bypass-classifier accuracy" is removed as a metric; `BYPASS` does not appear in the evaluation workload; hit ratio is now hits ÷ total rather than hits ÷ (total − BYPASS); false-hits-by-cause splits into reuse-decision error vs. staleness only.

### ADR-019 — C1 validity: reference-free labelling ablation and split discipline
**Decided (method)** · 2026-08-09 · *proposal §5 C1, §9.2; `experiment-protocol.md` §4–§5.*

Three method constraints, all adopted because an advisor review found the C1 comparison was not cleanly isolated.

1. **Reference-free labelling ablation (not droppable).** A false hit is scored against `reference(q) = LLM(retrieve(q), q)`. When overlap is low the reference is built from *different context*, so it diverges — **low overlap partially predicts its own label**. Judge–human agreement does not detect this: it validates the judge, not the label-generating procedure. The ~100 human-verified pairs are therefore labelled **twice** (reference-anchored and reference-free), with agreement reported **by overlap bucket**, bounding the circularity empirically.
2. **Split discipline.** The rule exposes three free parameters (τ, θ, cascade band) against the baseline's one, so a frontier gap could come from selection alone. Tune on a **validation split partitioned by seed-question cluster**; report on **held-out test**.
3. **Isolation controls.** A **static-cache ablation** (pre-populated, frozen, write-disabled, identical across configs) isolates the decision rule from cache-population divergence under LRU; **stratified reporting** (natural clusters / generated paraphrases / constructed traps, trap fraction stated) prevents a frontier dominated by hand-built traps.

- **Consequence:** items 1 and 2 sit **above** the judged-evaluation sample size in the drop order (proposal §12) — a smaller judged set with honest intervals is worth more than a larger one whose labels are circular.

### ADR-020 — Schedule compression; two-corpus split
**Decided (scope)** · 2026-08-09 · *proposal §11; `time_line.md`; `data-card.md` §1–§2, §7.*

Pre-thesis submission moves to **Mon Aug 31, 2026**; the thesis completes **Sun Dec 13, 2026**. The runway becomes **W5–W7 (45 h)** and the thesis phase **W8–W22 (225 h)**.

**Consequence — the runway cannot also build the experimental apparatus.** 45 hours from zero code is enough for a working pipeline, not for a frozen corpus plus a load-testing harness. The corpus is therefore split in two:

| Corpus | Built | Size | Purpose |
| :--- | :--- | :--- | :--- |
| **`dev-v0`** | W5 | ~40 products, 4 policy docs, no category balance | **Throwaway.** Makes the pipeline run. **No measurement may cite it.** |
| **`v1`** | W8 | ~150 products, **≥3 categories**, per-category policies | The **frozen experimental corpus**. Hashed, versioned, gated. |

- **Rationale:** building a corpus that makes retrieval work is a different job from building one whose overlap structure can support C1. Conflating them was what made the old 5-week runway impossible in 3.
- **Both corpora use the same frozen embedding model and chunking config** (ADR-003, ADR-014, frozen W5), so `v1` is a content expansion, not a re-chunk — it is a new `dataset_version` under the existing ID scheme (ADR-008), and `dev-v0` is discarded rather than migrated.
- **Also moved to W8:** the corpus sensitivity gate (`data-card.md` §7) and the off-box k6 harness. **Moved to W10:** the literature-verification block, outstanding since W2.
- **The runway's fallback:** if W6 slips, submit with Tier-1 only and present Tier-2 as a design slide. A working exact cache over a real RAG pipeline is still a defensible prototype; a half-finished Tier-2 is not.
- **The two weeks the thesis phase gains are slack**, reserved for overrun. They are not an invitation to reinstate anything from §14.

### ADR-021 — Generation LLM: Qwen 3.5 2B replaces Gemma 4 E4B
**Decided (frozen)** · 2026-08-15 · *supersedes ADR-002; informs ADR-017; proposal §5, §7.*

Generation moves from Gemma 4 E4B (Ollama, 4-bit) to **Qwen 3.5 2B** (`qwen3.5:2b-q4_K_M`, Alibaba,
released 2026-03-02), called with the request parameter **`think: false`** on every call (see
Consequences). The embedding model is unaffected and remains a separate open decision (ADR-003).

- **Rationale:** the author's development machine runs other projects continuously and is
  disciplined to ~9–10 GB used / ~5–6 GB free before testing — not the ~16 GB the original envelope
  design implicitly assumed. Measured against this real constraint, Gemma 4 E2B (the smallest
  Gemma 4 variant, smallest available quant) entered **yellow** memory pressure at the lightest
  possible config (7.7 GB resident, `num_ctx=4096`, `NUM_PARALLEL=1`, single request) — precisely
  the condition ADR-017 named as its own escalation trigger. Five candidates were then measured
  empirically: memory footprint (`num_ctx∈{4096,8192} × NUM_PARALLEL∈{1,4}`, via `ollama ps` +
  `kern.memorystatus_vm_pressure_level`) and RAG-QA reasoning quality (5 structured
  domain-specific test questions — spec extraction, policy-window arithmetic, a lookalike-trap
  discrimination test, a grounding/refusal test with no answer in context, and a multi-attribute
  comparison requiring arithmetic). Qwen 3.5 2B won on both axes: the smallest footprint of any
  candidate that also scored 5/5 on the QA set (1.6–1.7 GB across the full tested grid, versus
  4.3–5.3 GB for the two 4B-class candidates — too much for the ~5–6 GB operating ceiling once
  Redis/gateway/Python/embedding are also resident), and its footprint is nearly flat across both
  `num_ctx` and `NUM_PARALLEL`, unlike the larger candidates.
- **Alternatives:**
  - **Gemma 4 E2B** (smallest Gemma 4 variant, `q4_K_M` — smallest official quant) — rejected:
    7.7 GB resident, yellow pressure at the lightest config. No smaller official quant exists.
  - **Gemma 3 1B** — rejected as primary: fits with the most margin of any candidate (1.2–1.3 GB)
    but scored 4/5 on the QA set — it listed the raw figures for the arithmetic-comparison question
    without performing the subtraction the question asked for. Kept in reserve as the safest
    fallback if the operating RAM ceiling ever tightens further.
  - **Gemma 3 4B** and **Qwen3 4B** — both scored 5/5 on the QA set, but resident footprint
    (4.3–5.3 GB across the tested grid) leaves too little of the ~5–6 GB operating ceiling for the
    rest of the stack (embedding model + Redis + gateway + Python service) once those exist.
  - **Qwen2.5 3B** — scored 5/5, fits (2.4–3.1 GB); was the leading candidate before Qwen 3.5 2B
    was tested. Kept in reserve as the second choice.
- **Consequences:**
  - **`think: false` must be passed on every generation call.** Qwen 3.5 2B defaults to a hidden
    chain-of-thought mode that inflates a typical response from ~300–400 tokens to ~1,700 tokens
    and total latency from ~12 s to ~59 s, with no observed quality benefit on this task. This is
    hardcoded in `rag/src/rag/generate.py` (W6) and added to `.docs/ai/frozen-values.txt`.
  - **Ollama upgraded 0.22.1 → 0.32.13.** Qwen 3.5 2B returned HTTP 500 on every request under
    0.22.1 (the `qwen35` architecture was not yet supported); the upgrade resolved it. Done before
    any measurement was frozen — see Invalidates. Ollama version is now part of the environment
    card (`experiment-protocol.md` §1) and should be pinned/reported per run going forward.
  - μ_gen (proposal §3) is measured at 28.2 tokens/sec aggregate at the frozen pair
    (`num_ctx=8192`, `NUM_PARALLEL=4`) — see ADR-017.
  - `interfaces.md`'s `model_used` example and the "Frozen study-wide" line are updated to the new
    model id.
- **Invalidates:** none — no experiment runs exist yet (`experiments/results/` has no run
  directories; `docs/worklog/W05.md`'s log was empty before this session). This decision lands
  before any measurement that would need to be discarded.

### ADR-022 — Admission control: bounded permit pool, bounded queue, explicit shed
**Decided** · 2026-08-18 · *proposal §5, §6.1, §6.2, §3 S2; `interfaces.md` §A.*

Miss-path generations are admitted through a **counting semaphore** whose permit count is sized from ADR-017's measured ceiling (`OLLAMA_NUM_PARALLEL = 4`, plus headroom). Requests that cannot take a permit wait in a **bounded queue with a time budget**; when the queue or the budget is exhausted the gateway returns **`503 busy, retry`** with `Retry-After`. **Cache hits never acquire a permit** — that asymmetry is what lets hit throughput exceed the generation ceiling (proposal §3).

- **Why this was not previously recorded.** This mechanism carries the **60 % systems weight** (ADR-016) and had **no ADR at all** until now; it existed only as prose in proposal §6.1/§6.2. A decision of this weight with no recorded alternatives is exactly the "chosen because the author prefers it" failure an examiner probes.
- **Requirement it satisfies.** The binding constraint is **resident memory**, and its failure mode is not slowness but swap → OOM (proposal §4). Governance must therefore bound *concurrent residency*, and must **shed rather than admit** work the envelope cannot hold. `503` responses are counted as graceful-degradation events, never as served load (proposal §3, "throughput means goodput").
- **Alternatives, and why not:**
  - **Fixed-rate limiting (requests/sec).** Rejected — **wrong control variable.** The envelope binds on concurrently resident KV cache, not arrival rate. A burst of long-context requests at a legal RPS still exhausts memory, while a stream of short ones is shed needlessly. Rate is a proxy for the thing that matters; permits are the thing itself.
  - **Token bucket.** Rejected for the same category error, and more sharply: a bucket exists precisely to *permit bursts*, and a burst is exactly what a fixed memory envelope cannot absorb.
  - **Unbounded queue, no shedding.** Rejected — converts an OOM into unbounded latency. p99 diverges, clients time out anyway, and the failure becomes invisible to the server. Proposal §3's S2 requires excess be shed **explicitly** so degradation is observable and counted.
  - **`429 Too Many Requests` instead of `503`.** Rejected — `429` asserts a per-client quota violation; the condition here is **server-side capacity**, client-agnostic. `503` + `Retry-After` is the semantically correct signal and is already what `interfaces.md` §A specifies.
  - **Per-request memory accounting instead of a permit count.** Rejected as **out of scope, with the limitation recorded**: Ollama exposes no per-sequence KV accounting. ADR-017 measured Qwen 3.5 2B's resident footprint as *nearly flat* across the whole `num_ctx × OLLAMA_NUM_PARALLEL` grid, so a permit **count** is an adequate proxy at this envelope. It would not be at an envelope where footprint scaled steeply with context length — stated as a generalizability threat (proposal §9.4), not hidden.
- **Evidence.** Pool sizing is derived from ADR-017's measurement (`NUM_PARALLEL = 4` holds green at 1.7 GB resident, the largest cell tested). The **queue depth and time budget are not yet measured** — they are swept in W16 (`time_line.md`). Reasoned from a measurement, not itself swept; stated as such.
- **Falsification.** If the governed system enters yellow/red pressure at full admission, or if goodput at saturation falls more than 10 % below peak (proposal §3 S2), the pool is mis-sized and the sizing rule — not the measurement — is wrong.
- **Invalidates:** none — no experiment runs exist (`experiments/results/` has no run directories, confirmed 2026-08-18).

### ADR-023 — Five configurations × source-mutation axis
**Decided (experiment design)** · 2026-08-18 · *revises proposal §9.2; changes `experiment-protocol.md` §2 `config_id`; refines ADR-016's "eight → five".*

The five-configuration ablation ladder is **kept**, and **source mutation is promoted to an explicit orthogonal binary factor** (`mutation: off | on`). Runs are identified by the **pair** `(config_id, mutation)`, not by `config_id` alone. Only meaningful cells are run.

| # | Configuration | mutation `off` | mutation `on` |
| :---: | :--- | :---: | :---: |
| 1 | No cache | ✅ baseline — generation cost/throughput ceiling | — nothing cached can go stale |
| 2 | Exact-match only (Tier 1) | ✅ cheap tier in isolation; the only cell that isolates *embedding calls saved* | — |
| 3 | Fixed-threshold semantic (best τ) — GPTCache's rule | ✅ Headline B baseline | ✅ **conventional cache under source change, no dependency-aware invalidation** |
| 4 | Source-overlap rule (overlap ≥ θ ∧ sim ≥ τ) | ✅ Headline B — the research contribution | ⚪ optional control, see below |
| 5 | Tiered full system (exact + rule + source-aware invalidation) | ✅ | ✅ **the invalidation result** |

- **Case 4 and Case 5 are not separate cache architectures.** They are controlled source-mutation extensions of Case 2 and Case 3 respectively — i.e. cells `(3, on)` and `(5, on)` of the grid above. Their purpose is to evaluate how cache correctness behaves under evolving source data, and whether explicit source-dependency information enables more reliable cache maintenance.
- **The optional cell `(4, on)` is a confound control.** Cell `(5, on)` differs from `(3, on)` by **two** changes: the reuse rule *and* dependency-aware invalidation. Without `(4, on)` — provenance rule under mutation, invalidation disabled — an improvement at `(5, on)` cannot be attributed to invalidation alone. Run it if budget permits; **if it is not run, the confound is reported as a limitation rather than argued away.**
- **Alternatives, and why not:**
  - **Adopt the 2×2 restructure verbatim** (Case1=no cache, Case2/3 = conventional/provenance static, Case4/5 = those + mutation). Rejected as specified because it **deletes configuration 2** — the exact-match-only tier, the only configuration that isolates the Tier-1 embedding-call saving that proposal §3's μ_hit argument rests on — and because it **collapses the static-cache ablation** from a *reported pair* into a configuration property. ADR-019 lists that ablation as an isolation control that is **not droppable**: cache-population divergence under LRU means configs 3 and 4 hold different entries by mid-run and are no longer compared on identical state. The grid above keeps both.
  - **Keep the pure static ladder** (status quo). Rejected — it hid that the mutation cells differ from their static counterparts by *two* variables, and it left mutation metrics (staleness rate, invalidation completeness/precision) sitting inside the Headline-B five-config table where **only configuration 5 can produce them**. That is the seam the advisor review identified.
- **Consequences.** `experiment-protocol.md` §2's run manifest gains a **`mutation: off|on`** field; `config_id` alone no longer identifies a run. Existing text reading "all five configs" now means "all five configurations at `mutation: off`". The swept-TTL baseline of RQ3 is the invalidation policy in force at cell `(3, on)`; TTL = ∞ is one point on that sweep.
- **Invalidates:** none — no runs exist. This is the last moment the ladder can be restructured for free; after W8's first campaigns it would void data.

### ADR-024 — `v1` corpus data model, and the sensitivity gate's overlap formula
**Decided (data)** · 2026-08-18 · *amends `data-card.md` §2, §7; depends on ADR-020, ADR-014, ADR-008.*

The `v1` corpus specification gains four structural requirements, and the corpus sensitivity gate's overlap formula is pinned. **`dev-v0` is not retrofitted** — it is throwaway and non-citable (ADR-020), so fixing it would leave no durable value.

1. **A product↔policy join key.** Policy records gain a `category` field; product records already carry one. Today `rag/src/rag/ingest.py` writes `category: ""` for **every** policy record, so the Redis `category` tag is empty on all four policy documents and there is **no join in either direction**.
   - *Why:* without it a **mixed specification + policy query** ("does the 30-day return cover this 4 kg monitor?") is **structurally impossible** to ground correctly — the retriever must infer product→policy purely lexically. The `kind ∈ {product, policy}` tag already exists in `store.py`, so "does this answer's provenance span both kinds?" becomes computable at essentially zero cost.
2. **Per-category *warranty* windows, not only return windows.** `data-card.md` §7 already requires warranty windows to differ per category; `dev-v0` shipped a single global `policy-warranty` and a single global `policy-shipping`, leaving **exactly one differentiated axis (returns) covering two of four categories** — `kitchen` has no return policy at all.
3. **Policy documents long enough to chunk into ≥ 3 chunks. ⚠️ This is the load-bearing one.** `dev-v0` ingested 44 documents into **44 chunks — one chunk per document** (`worklog/W05.md`, 2026-08-15), because the authored text falls under `chunk_size = 256`. A singleton `sources(e)` makes `overlap(A,B) = |A ∩ B| / |B|` take only the values **0 or 1**: θ has nothing to sweep and the C1 frontier degenerates to a step function. ADR-014 anticipated this hazard from the `chunk_size` direction ("collapsing a policy document into 1–2 chunks … undermining the exact phenomenon the corpus sensitivity gate exists to protect"); `dev-v0` reached it from the *document-length* direction instead.
4. **A stratum taxonomy that separates same-provenance from different-provenance, and paraphrase from lookalike.** The current three strata (natural cluster / generated paraphrase / constructed trap) cannot distinguish *similar query, same provenance* from *differently worded, same provenance* — both fall in the first two. `v1` tags each query with one of:

| Stratum | Query similarity | Provenance | What it tests |
| :--- | :--- | :--- | :--- |
| **A** | high | **same** | Safe reuse — the case a semantic cache should serve |
| **B** | high | **different** | The lookalike trap. **The phenomenon C1 exists to catch** |
| **C** | low (different wording) | same | Why exact-match alone is insufficient |
| **D** | any | spans product **and** policy | Multi-source-type grounding (needs requirement 1) |

5. **The gate's overlap formula is pinned to symmetric Jaccard.** The gate counts query **pairs** satisfying `sim ≥ 0.85 ∧ overlap ≤ 0.2`, but its overlap is between two *queries'* retrieval sets while the rule's is between a query's retrieval and a *cached entry's* provenance — and the rule's form `|A ∩ B| / |B|` is **asymmetric, hence not well-defined for a query–query pair**. The gate therefore uses `J(A,B) = |A ∩ B| / |A ∪ B|` over the two top-k retrieval sets. At equal `top_k` this is monotone in `|A ∩ B|` and so orders pairs identically to `|A ∩ B| / k`; with `top_k = 5`, `J ≤ 0.2` admits at most one shared chunk.
   - The gate statistic is a **corpus property**, not the rule's operating metric, and is reported as such so the two are never conflated.

- **Evidence:** measured against `dev-v0` as built — 44 documents, 44 chunks, 4 categories, 4 policy documents of which 2 are global; `top_k = 5` over a 44-chunk index containing only 4 policy chunks, which makes both return-policy chunks likely to appear in *both* queries' top-5 and drives overlap toward 1 for the very pair that is supposed to be a trap. The W5 exit test verified **ranking** ("ranked the furniture policy above the electronics one"); `overlap` is rank-insensitive, so that result does not rebut this.
- **Alternatives, and why not:**
  - **Retrofit `dev-v0`.** Rejected — ADR-020 makes it non-citable and discards it after W8; the effort would leave nothing durable and would consume W6 build hours.
  - **Leave the corpus and weaken the rule** (e.g. accept binary overlap). Rejected — `data-card.md` §7's standing instruction is **"fix the corpus, not the rule."** A binary overlap signal cannot produce the frontier the thesis reports.
  - **Global policies with per-product overrides.** Rejected — reintroduces the overlap ≈ 1 failure for every question that does not hit an override, and makes the trap fraction depend on override density rather than on category structure.
- **Falsification / gate:** if `v1` cannot reach ≥ ~50 pairs at `sim ≥ 0.85 ∧ J ≤ 0.2` after these requirements are met, the phenomenon is genuinely thin in this domain — reported as the pre-registered null (proposal §5 C1), not engineered around further.
- **Invalidates:** none — `v1` does not yet exist and `dev-v0` is not gated (ADR-020).

### ADR-025 — No message broker; invalidation events stay in-process
**Decided (scope/architecture)** · 2026-08-18 · *proposal §6, §7.0, §14; `interfaces.md` §E; depends on ADR-009, ADR-017.*

Source-mutation events are delivered by an **in-process buffered channel to a single writer goroutine**. No message broker (Kafka, RabbitMQ, NATS, Redis Streams) is introduced — not on the query path, and not on the mutation path.

- **Why record a decision about something not being built.** "Why not Kafka?" is a predictable examiner and reviewer question for any system with a read path and a write path, and the honest answer is architectural, not dismissive. Without this entry the absence of a broker reads as an oversight rather than a choice.
- **Query path — rejected on semantics *and* on measurement.** The gateway cannot answer until the RAG service does, and the C1 cascade needs retrieval results *before* deciding reuse; both are synchronous and request-scoped. A broker between them would rebuild request/response on top of messaging — correlation IDs, response topics, timeout handling, duplicate suppression — while inserting producer, broker, and consumer scheduling into **the exact critical path whose latency is the measurement**. See ADR-007.
- **Mutation path — the one place a broker genuinely fits, still rejected here.** A source edit is fire-and-forget and blocks no client, so event delivery suits it. But a broker's value is decoupling, fan-out, replay, and independently scaled consumers — and **at the single-node scope ADR-009 fixes, there is exactly one producer and one consumer.** There is nothing to decouple from anything.
- **Envelope.** ADR-017 measured ~5–6 GB free on the operating ceiling. A resident broker competes with KV cache inside the very envelope the thesis exists to govern — the same argument that rejected a JVM search service in ADR-004. Worse, it would land *inside* the RQ3 invalidation-under-load measurement: "did invalidation stall the read fast path?" would become entangled with broker scheduling, and the C2 result would no longer isolate the mechanism under study.
- **Alternatives, and why not:**
  - **Kafka on the query path** — rejected above; semantics and measurement both argue against it.
  - **Kafka on the mutation path only** — rejected on envelope and on the absence of any consumer to decouple. **This is the natural design once the system scales out**, and is recorded as such in proposal §14 rather than dismissed.
  - **Redis Streams / Pub-Sub as a lighter broker.** Redis is already resident, so the memory objection weakens — but **Redis Pub/Sub is fire-and-forget with no delivery guarantee**. A dropped invalidation event silently leaves stale entries unpurged, breaking C2's completeness guarantee with **no error** — precisely the silent-failure class ADR-005 exists to close. Redis Streams would avoid that but still adds a hop with no decoupling benefit at single-node.
  - **In-process buffered channel to one writer goroutine** — chosen. Writer-writer races are eliminated by construction rather than by locking discipline, and the purge fan-out stays off the critical path (proposal §5 C2).
- **Research relevance: none.** This is a tier-A architectural decision (§7.0). No claim is made that channels outperform brokers; the claim under test is about *how provenance information maintains cache correctness under source change*, which is unaffected by the delivery mechanism.
- **Falsification / revisit trigger:** if the invalidation writer becomes a measured bottleneck — writer-queue depth growing without bound under the W19 invalidation-under-load run — the single-goroutine design is wrong and the decision is revisited. That is a measurement, not a preference.
- **Invalidates:** none — no runs exist.

### ADR-026 — C1 narrowed: provenance-gated reuse is concurrent work, not an unoccupied gap
**Decided (research positioning)** · 2026-09-02 · *proposal §5 C1, §10, §10.1, §14; supersedes the gap statement in proposal §10 "Differentiation, bounded honestly"; depends on ADR-016, ADR-019, ADR-024.*

The literature-verification block that proposal §10 scheduled for the research core was **pulled forward to W8** and run against primary sources. Two systems were found occupying the cell C1 claimed. The gap statement is **rewritten, not defended**, as proposal §10.1 pre-committed.

**What was found.**

- **GroundedCache** — Shah, *"Grounded Cache Routing for Retrieval-Augmented Generation: When Is It Safe to Reuse an Answer?"*, arXiv:2605.27494, May 2026. Admits a cached answer only when four gates hold together: query similarity, **retrieved-evidence overlap**, source-version validity, and lexical or judge-based support of the cached answer by freshly retrieved evidence. Gates 1 and 2 are this thesis's rule. Gate 3 is the dataset-epoch guard of C2. Not a position paper — 12,000 real generations, Qwen2.5-7B on vLLM, HotpotQA and mtRAG, FAISS with `all-MiniLM-L6-v2`, against a GPTCache-style baseline.
- **FinCacheServe** — Zeng and Jin, *"Dependency-Consistent Answer Reuse for Cost-Efficient RAG Serving over Mutable Enterprise Documents"*, arXiv:2607.26076, July 2026. Maintains a **document→answer reverse index** and purges dependent entries on source-version change. Reports **zero dependency-stale serves** across 90 runs of an interleaved 4,096-query / 512-update stress, at 100k entries with 64 query workers. Its reuse gate uses evidence fingerprints over cited chunk identifiers, chunk hashes, and document versions. Its **baseline set already includes "grounded-style reuse"**, so the field now treats provenance-gated reuse as a baseline rather than a contribution.

**Decision.** C1 is narrowed from a claim about an **unused signal** to a claim about **form, measurement, and setting**. Provenance-gated reuse is **no longer claimed as novel**, and neither is dependency-keyed invalidation, which ADR-016 and proposal §5 C2 already declined to claim.

**What is still claimed — the five surviving differentiators.**

1. **Asymmetric containment, not symmetric Jaccard.** The rule is `overlap(A,B) = |A ∩ B| / |B|` with `A = retrieve(q)` and `B = sources(e)` — the fraction of the *cached entry's* sources that the incoming query re-retrieves. GroundedCache gates on symmetric Jaccard over chunk hashes. The asymmetric direction is the one that matches the reuse question, because reuse safety depends on whether the entry's grounding is re-covered, not on set agreement. Jaccard remains the robustness check (ADR-024), which now doubles as a direct comparison against published practice.
2. **A swept frontier at a stated error budget, not an operating point.** θ and τ are swept and reported as a hit-rate / false-hit-rate frontier with Wilson intervals at δ, on a split partitioned by seed-question cluster (ADR-019). Neither system reports a frontier. GroundedCache reports unsafe-served rate, FinCacheServe reports skip rate.
3. **Coupling to generation-admission control under a fixed unified-memory envelope.** Neither system bounds concurrent residency, sheds, or operates under memory-pressure discipline. Both run on datacenter GPU. FinCacheServe's "admission" is cache admission and eviction, which is a different mechanism from ADR-022's permit pool.
4. **Invalidation precision measured, not only completeness.** The `substantive` / `cosmetic` split (ADR-024, `data-card.md` §5) quantifies over-invalidation. FinCacheServe demonstrates completeness and does not report the precision cost.
5. **Lock-free copy-on-write dependency map.** FinCacheServe uses a **service-level metadata lock** around version-store updates and entry mutation. That is precisely the design proposal §5 C2 argues against, because it serialises the read fast path. C2's `atomic.Pointer` snapshot with a channel-serialised writer, and its reader-stall measurement, now answer a published alternative rather than a hypothetical one.

**What is explicitly no longer claimed.**

- That provenance is an unused signal in semantic caching.
- That no system decides reuse from retrieval context. Proposal §10's "to our knowledge, none uses retrieval provenance as the serving-time reuse decision" is **withdrawn**.
- Any priority claim. Both systems predate this report.

**Consequences.**

- Report Chapter 2 is restructured around concurrent work, with a dedicated section for both systems and a comparison table carrying explicit verification status.
- Proposal §5 C1, §10, §10.1, §2b row 5, and §14 are updated to match.
- The **pre-registered null** of proposal §5 C1 is unchanged and is now more likely to be the reported outcome. That was always an acceptable result and is stated as such.
- The 60 % systems pillar is untouched by either system. ADR-016's weighting stands.

**Falsification / revisit trigger.** If reading either paper in full contradicts the characterisations above — in particular if GroundedCache's overlap gate turns out to be asymmetric, or if FinCacheServe measures invalidation precision — the corresponding differentiator is **struck, not softened**, and the remaining differentiators carry C1 alone. If fewer than two survive, C1 is reported as a replication in a new setting rather than as a contribution.

**Invalidates:** no runs. `v1` is not yet frozen and no measurement exists. This is a positioning change, not a configuration change.

### ADR-027 — Cache capacity as a ratio of workload size, and S1 restated
**Decided (experiment design)** · 2026-09-02 · *resolves ADR-005's open capacity item (set-by W8); proposal §3 S1, §9.1, §9.5; `experiment-protocol.md` §1, §2, §6.*

Cache capacity is set as **`cache_capacity = round(0.25 × K)`**, where `K` is the count of distinct queries in the frozen workload. The **ratio** is frozen study-wide. The absolute value is derived once `K` is known and recorded per run.

**Why a ratio and not a number.** An absolute capacity silently becomes a different experiment when the corpus changes size. The quantity that governs cache behaviour is the ratio of capacity to working set, not the capacity itself.

**Evidence — the redundancy sweep collapses at `C/K ≥ 1`.** LRU simulated under Zipf, 400k requests, hit rate measured after 50 % warm-up, at the three skew levels the protocol sweeps:

| `K` | `C` | `C/K` | s=0.8 | s=1.1 | s=1.4 | sweep spread |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2,000 | 5,000 | 2.50 | 1.0000 | 1.0000 | 0.9995 | **0.000** |
| 5,000 | 5,000 | 1.00 | 1.0000 | 0.9996 | 0.9961 | 0.004 |
| 10,000 | 5,000 | 0.50 | 0.7919 | 0.9369 | 0.9899 | 0.198 |
| 20,000 | 5,000 | 0.25 | 0.6253 | 0.8834 | 0.9832 | **0.359** |
| 50,000 | 5,000 | 0.10 | 0.4603 | 0.8290 | 0.9758 | 0.515 |

At `C ≥ K` nothing is ever evicted, so hit rate is ≈ 1.000 at **every** skew level and the sweep produces a constant. Proposal §9.1 declares redundancy an **independent variable**, and RQ1 asks how the benefit varies with it. With ~150 products and a workload of order 1,000–3,000 distinct queries against the previous placeholder of 5,000, the study sat in the degenerate row. `C/K = 0.25` gives a spread of 0.359, which is dynamic range enough for the sweep to mean something.

**Consequence — S1 is restated, because the crossover is not reachable.** The load-conversion crossover sits at `h* = μ_hit / (μ_gen + μ_hit)`. With **μ_gen ≈ 0.19 req/s** (28.2 tok/s ÷ ~150 output tokens, ADR-017), `h*` is extreme for any plausible `μ_hit`:

| | μ_hit=20 | 50 | 100 | 200 | 400 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| **h\*** | 0.9907 | 0.9963 | 0.9981 | 0.9991 | 0.9995 |

The best hit rate obtainable in a **non-degenerate** sweep is ≈ 0.988 (`C/K = 0.5`, s=1.4). The crossover is therefore observable only if `μ_hit ≤ ~16 req/s`, which would mean ~63 ms per hit at full concurrency for a path that is a Redis lookup, one embedding call, and a FLAT vector search. **A meaningful redundancy sweep and an observable crossover are mutually exclusive under the frozen parameters.**

Proposal §3's S1 currently promises that "the crossover — the load-conversion ceiling — is located empirically". That is replaced by:

> **S1 — Capacity.** Measured sustainable load tracks the **binding term** of the `λ_max` model across the redundancy sweep. Both service rates are measured directly: μ_gen under sustained load, μ_hit by the 100 %-hit run. The crossover `h*` is **computed from those two measured rates** and reported alongside the range of `h` the workload actually reaches. If `h*` lies outside that range — which the model predicts whenever μ_gen ≪ μ_hit — the finding is that the system is **generation-bound throughout its operating range**, reported as a quantitative result rather than as a failed measurement.

This keeps S1 a falsifiable model-fit claim. It still requires both service rates to be measured, and the 100 %-hit run still earns its place — it now supplies `h*` rather than being expected to reach it.

- **Alternatives, and why not:**
  - **Keep the absolute 5,000.** Rejected — it is the value that produces the degenerate sweep, and it drifts in meaning as the corpus grows.
  - **Sweep capacity as an additional factor** (`C/K ∈ {0.1, 0.5}`). Rejected on budget — it doubles the Headline A matrix on top of the existing 5×2 grid (ADR-023). Recorded as a gap: the response of hit rate to cache pressure is not characterised, only its response to skew.
  - **Engineer the workload to reach `h*`.** Rejected — it would require `h > 99 %`, which is only obtainable by making the cache hold the entire query population, i.e. by returning to the degenerate regime.
- **Falsification / revisit trigger:** if the Phase 1 μ_hit probe returns **≤ ~16 req/s**, the crossover *is* reachable in a non-degenerate sweep and S1's original empirical wording should be restored. That is a measurement, and it is why the probe is a Phase 1 exit criterion.
- **Invalidates:** no runs. None exist.

### ADR-028 — `v1` corpus: within-product stratum B, and the Tier-1 collision invariant
**Decided (data)** · 2026-09-02 · *tightens ADR-024; `data-card.md` §2, §7; `interfaces.md` §D (Tier-1 key), ADR-015.*

Two additions to the pre-freeze corpus gate. Both close a path by which the corpus itself would defeat a contribution.

**1. Stratum B is split into `B-within` and `B-cross`, and `B-within = 0` fails the gate.**

| Sub-stratum | Query similarity | Product | Provenance | What it tests |
| :--- | :--- | :--- | :--- | :--- |
| **B-cross** | high | **different** | different | The case a `product_id` cache key also solves |
| **B-within** | high | **same** | different | The case **only** provenance solves |

- **The objection this exists to answer.** If every B pair is cross-product, then adding `product_id` to the Tier-1 and Tier-2 keys reproduces the rule's entire benefit at zero cost, with no retrieval round-trip on the hit path. C1 would be redundant *by construction of the corpus*, and the reported frontier would prove nothing about provenance.
- **The principle.** `product_id` is **metadata known before retrieval**. Provenance is **the grounding, known only after retrieval**. A key built from pre-retrieval metadata separates queries only along dimensions that metadata encodes. B-within pairs are the empirical demonstration that the two are not the same dimension.
- **Example pairs to build:** *"how long is the **warranty** period"* against *"how long is the **return** period"* · *"can I return this if it's **opened**"* against *"…**unopened**"* · *"return window for a **defective** item"* against *"…for a **change of mind**"*. Same product, same category, same metadata, different policy chunks.
- **This is a second justification for ADR-024's ≥3-chunks-per-policy-document requirement.** That constraint was recorded so θ would have range to sweep. B-within pairs *also* require it: distinct conditions must land in distinct chunks or there is nothing for containment to separate. One constraint, two independent reasons.
- **No numeric floor above zero is set.** There is no evidence yet from which to derive one, and an invented threshold is harder to defend than a stated gap. The first gate run on `v1` supplies the number. Recorded here as a known gap.
- **Reporting consequence.** The C1 frontier is reported **broken out by sub-stratum**. If the advantage rests entirely on B-cross, the product-ID objection lands, and that is what gets written.

**2. Tier-1 collision invariant.**

> No two workload queries with different `reference_answer` or different `doc_ids` may share the same `normalize(q)`.

- **Why it is a correctness invariant and not a nicety.** Tier 1 is `sha256(normalized_query) → answer` (`interfaces.md` §D, ADR-015). It runs **no similarity test and no reuse rule**. Two differently-answered questions that normalise identically are served wrongly from first write, permanently, with nothing to detect it.
- **The measurement damage is worse than the serving damage.** Such a hit is recorded as a false hit. `experiment-protocol.md` §4 splits false hits into exactly two causes, *reuse-decision error* and *staleness*. A Tier-1 collision is a **third cause with no bucket**, so it is charged to the reuse rule — attributing to C1 a defect C1 cannot cause, because the rule never ran.
- **A specific risk in the normalisation.** ADR-015 strips punctuation. `"Model A-1"` and `"Model A1"` collapse to the same key. Harmless within one product, not harmless across two.
- **Check:** group the workload by `normalize(q)`, and fail on any group whose members disagree on `doc_ids` or `reference_answer`. Runs before the snapshot is hashed, alongside the sensitivity gate.
- **On failure: fix the corpus, not the rule** — disambiguate the query text. Same standing instruction as the sensitivity gate (`data-card.md` §7).

- **Alternatives, and why not:**
  - **Add `product_id` to the request and the Tier-1 key.** Rejected. It is more faithful to production traffic, where questions are asked on a product page and are elliptical, but it moves the work C1 does into the cache key and forces C1's claim to be restated as *"provenance beats similarity **given** product scoping"* — materially weaker. Workload queries are instead required to be **self-contained**, naming their product or category in the query text, which is what the `/ask` contract already assumes (`interfaces.md` §A) and what `defense_demo.md` step 3 already demonstrates.
  - **Drop Tier 1 entirely**, which would make this invariant moot. Rejected — it deletes configuration 2, the only cell that isolates the literal-repeat share of the workload (ADR-023, proposal §9.2), and Tier 1 is already built.
  - **Numeric floor on B-within.** Rejected as unevidenced, above.
- **Falsification / revisit trigger:** if `v1` cannot produce B-within pairs at `sim ≥ 0.85 ∧ J ≤ 0.2` after the ADR-024 structural requirements are met, then within-product provenance divergence is genuinely thin in this domain. That is reported as a **corpus finding bounding C1's applicability**, and it strengthens rather than excuses the pre-registered null (proposal §5 C1).
- **Invalidates:** no runs. `v1` does not yet exist.

### ADR-029 — Per-request evaluation log
**Decided (method)** · 2026-09-02 · *`interfaces.md` §H (new); `experiment-protocol.md` §3, §4.*

The gateway emits **one JSONL record per request** into `results/{run_id}/raw/`. The schema is pinned in `interfaces.md` §H and joined to the `/ask` response by `request_id`.

**Why this is a decision and not an implementation detail.** `experiment-protocol.md` §3 already promises that `raw/` holds "per-request logs", but no schema was ever specified. Four metrics the protocol defines in §4 are **not computable** without one:

| Metric | Field it needs |
| :--- | :--- |
| Decisions changed by provenance | `similarity_only_decision` |
| % entering the cascade band | `entered_band` |
| False hits by cause | `cache`, `dataset_epoch_at_retrieval`, `entry_sources` |
| Hit-path latency decomposition | `t_tier1_ms`, `t_embed_ms`, `t_search_ms`, `t_overlap_ms` |

**Two fields must be captured at serve time and cannot be reconstructed afterwards.**

- **`similarity_only_decision`** — the counterfactual outcome the fixed-threshold baseline would have produced for this request, recorded at the moment the rule ran. Without it, *decisions changed by provenance* has to be inferred by re-running a baseline over a log that no longer holds the candidate entry's state. That metric is what makes the **pre-registered null interpretable** (proposal §5 C1, `experiment-protocol.md` §6). Losing it loses C1's fallback.
- **`answer_sha256`** — the judge dedupe key. `experiment-protocol.md` §4 already requires verdicts keyed by `sha256(query ‖ candidate_answer)` to keep the judging bill affordable. The hash must be written when the answer is served, not recomputed at judging time from a possibly re-generated answer.

- **Alternatives, and why not:**
  - **Derive everything from the `/ask` responses captured by k6.** Rejected — the response carries the six defence-demo fields plus extensions (`interfaces.md` §A), not the counterfactual, not the latency decomposition, and not admission state. Widening the client-facing response to carry evaluation internals would put measurement scaffolding on the wire.
  - **Structured application logs without a pinned schema.** Rejected — the protocol's reproducibility rule is that every figure regenerates from `raw/` by script. A script cannot depend on an unpinned shape.
- **Cost.** One append per request, off the critical path, written to `raw/` which is already write-once. The record is small and the volume is bounded by the run's request count.
- **Falsification / revisit trigger:** if any metric in `experiment-protocol.md` §4 turns out not to be computable from §H at analysis time, the schema is incomplete and the gap is recorded rather than back-filled by re-deriving numbers from a different source.
- **Invalidates:** no runs.

---

### ADR-030 — Reuse rule v2: a third lane for multi-source questions
**Decided (method)** · 2026-09-06 · *proposal §5 C1, §9.2; `interfaces.md` §D, §H; `data-card.md` §2 stratum D; supersedes nothing, extends ADR-026's narrowed C1.*

The reuse rule gains a **third lane**. A question whose retrieval spans product *and* policy documents — stratum D of `data-card.md` §2 — is classified `MIXED` by a two-sided band on `policy_fraction`, and its cache namespace is the **pair** `{product}|{policy}` rather than either document alone. The lane selector's single `sigma` becomes a band `(sigma_lo, sigma_hi)`; a collapsed band (`sigma_lo == sigma_hi`) reproduces the two-lane rule exactly and is the shipped default. A `tau_high` short-circuit knob is added to the cascade, shipped disabled. ~~`tau_high`~~ — **the knob is retired by ADR-036**, together with the unfiltered cascade phase that produced the candidate it gated; the lane rule, the band and the composite namespace are unaffected and remain in force.

- **Rationale — a single-key namespace is *unsound* for stratum D, not merely imprecise.** With two lanes, a mixed question falls into `POLICY`, takes the rank-1 policy document as its namespace, and **drops the product entirely**; the same mixed question about a different product then shares a namespace and is served the wrong specification half. Measured on `dev-v0` 2026-09-06: `policy_fraction` was 0.00 for all 10 spec questions, 0.20–0.40 for 5 of 6 mixed ones, and 0.60–0.80 for all 10 policy ones — so the band separates the three cleanly on this corpus.
- **Why the namespace is a pair and not containment.** The first implementation used containment (`Thresholds.Decide`) as the mixed lane's second term. It **failed measurably**. One cached entry, two follow-ups, both scoring an identical containment of **0.80** and needing opposite verdicts: a paraphrase of the same return question (reuse correct) and the *warranty* question about the same product (reuse a false hit — it was served the 30-day return answer). Retrieval was not at fault; it returned `policy-warranty` correctly. A mixed grounding is roughly four product chunks to one policy chunk, so the single chunk carrying the entire semantic difference is 1/5 of the denominator, and at `top_k = 5` the overlap granularity is 0.2. **No theta separates them.** The composite key does, because the two differ precisely in their rank-1 policy document.
- **Why lane equality is kept on top of the composite key.** A composite namespace can never equal a pure-lane one by construction, so the term is redundant — but it costs one comparison and makes lane disjointness an *enforced invariant* rather than an emergent property of a string format. It also earned its place directly: it refused a spec-only entry at similarity 0.9244 where containment accepted.
- **Why `tau_high` ships disabled (`1.0`).** A short-circuit serves on similarity **alone**, with the provenance rule never running. Across 17 labelled probes the traps and the legitimate reuses **interleave**: the worst trap scored 0.9685 while only one of seven correct reuses (0.9899) sat above it. Any `tau_high` low enough to short-circuit an appreciable share of hits also serves lookalikes. It is retained solely so the frontier has the point, and a short-circuit is logged as `reuse_rule=similarity_only` so a false hit made that way is never charged to a rule that did not run.
- **Alternatives, and why not:**
  - **Leave stratum D to the two-lane rule.** Rejected — that is the unsound case above, and it is a false hit the two-lane rule *creates* which plain containment does not have.
  - **Containment as the mixed lane's second term.** Rejected on measurement, above. Recorded because it was the first implementation and the reasoning that produced it was wrong in an instructive way.
  - **Classify the lane from the query text.** Rejected for ADR-018's reason: a classifier's error becomes a false-hit cause with no bucket in `experiment-protocol.md` §4's two-cause split, and would be charged to the reuse rule. The lane is read from the grounding, which cannot be wrong about what retrieval returned.
  - **Bypass generation for mixed questions.** Rejected — they are cacheable, just at a narrower key. Refusing them would be a capacity decision dressed as a correctness one.
- **Consequences:**
  - **`entered_band` stops being a cost driver.** `interfaces.md` §H calls it *"paid for retrieval — the rule's cost driver"*. Since the gateway began issuing the retrieval concurrently with the embedding (same date), **every** Tier-1 miss pays for retrieval, so band share now measures how often the rule consults provenance and **not** what the rule costs. Any reading of `experiment-protocol.md` §4's *"% entering the cascade band"* must be restated accordingly, and `tau_high` no longer saves latency even when enabled.
  - `sigma_lo` and `sigma_hi` join `tau` and `theta` as swept parameters (rules.md #10) — four now, against the baseline's one, which raises rather than lowers the importance of ADR-019's validation/test split by seed cluster.
  - Changing the band **invalidates a warm cache**: entries carry the lane and namespace they were partitioned with at write time, so a band change over a warm cache mixes two rules and contains no `MIXED` entries at all. Flush both tiers on any band change, exactly as for a `tau`/`theta` change.
  - Positioning: this is **not** a fourth contribution. It is a refinement of C1's rule for one stratum, arising from a measured failure, and belongs in the proposal's §3.2.3-equivalent discussion — never in a novelty claim, which ADR-026 has already narrowed.
- **Falsification / revisit trigger:** if on `v1` the mixed and policy `policy_fraction` distributions overlap, the band cannot separate the lanes on that corpus and the mixed lane must be reconsidered rather than tuned into place. Equally, if a swept `theta` on `v1` *does* separate the measured pair above, containment is sufficient after all and the composite key should be dropped.
- **Invalidates:** none — no runs exist. The shipped defaults (collapsed band, `tau_high = 1.0`) reproduce the previous rule bit-for-bit, and a regression on the four decisive queries reproduces the pre-change similarities exactly (0.4237 / 0.9244 / 0.9382 / 0.9578).

---

### ADR-031 — Cache capacity is an entry count enforced by the gateway
**Decided (frozen — amends the eviction mechanism of ADR-005 / ADR-027)** · 2026-09-06 · *`interfaces.md` §D; ADR-005, ADR-027; rules.md #5.*

Cache capacity is enforced **by the gateway** as a count of entries, using a Redis sorted set of `entry_id` scored by last access; after each write-back the gateway trims to capacity, deleting the Tier-1 and Tier-2 records of each victim together. Redis keeps `noeviction` globally and no byte budget is set. This replaces §D's prescription that cache entries live in "a logical DB with `allkeys-lru`".

- **Rationale — §D's mechanism cannot express what ADR-027 requires.** ADR-027 fixes capacity at `round(0.25 × K)` **entries**, a count. `allkeys-lru` evicts by **bytes** and cannot be told to hold N entries. Worse, `maxmemory-policy` is **server-global rather than per logical DB**, so §D's two-region split is not achievable on one `redis-stack-server` at all: any `allkeys-*` setting can evict the `dep:*` records of §E, which makes their entries permanently unpurgeable and breaks C2's completeness with no error (rules.md #5). `make redis-check` had already reached this conclusion independently and refuses any byte budget for exactly the first reason.
- **Why this is stronger than what §D asked for.** Under gateway-enforced eviction the dependency region is safe **by construction** — nothing in Redis is evictable at all — rather than safe by a configuration that a later `CONFIG SET` could silently undo. The invariant no longer depends on an operator remembering it.
- **Alternatives, and why not:**
  - **Two Redis instances**, one `allkeys-lru` with a byte budget, one `noeviction`. Rejected: it matches §D's letter but still evicts by size rather than by entry count, contradicting ADR-027, and it adds a second server and LaunchAgent to the envelope for no gain.
  - **One instance under `volatile-lru` with TTLs on cache entries only** — §D's own stated equivalent. Rejected: TTL eviction is time-based and still needs a byte budget to fire, so it delivers neither a count nor determinism.
  - **Leave the cache unbounded until `K` is frozen.** Rejected as a permanent answer, though it is the shipped default (`0`): every hit rate measured against an unbounded cache is an upper bound no deployment reaches, and ADR-027's whole argument is that the capacity-to-working-set ratio is what governs cache behaviour.
- **Consequences:**
  - `interfaces.md` §D's eviction paragraph and the "Frozen study-wide" line (which names *the two-region eviction policy*) are amended by this entry. The **ratio** `C/K = 0.25` is untouched and remains frozen.
  - Both tiers of an evicted entry are removed together. Deleting only the Tier-2 record would leave Tier 1 serving the same answer from a bare hash lookup that runs no reuse rule, so the entry would still be served while absent from the cache the experiment believes it is bounding — and the capacity sweep would measure nothing. The `t1_key` field of §D is what makes this possible.
  - A new Redis key prefix, `lru:`, joins `corpus:`, `t1:`, `t2:`, `dep:` and `entry:`. `make demo-reset`'s foreign-key guard was updated; it had begun refusing every reset, which is the guard working correctly.
  - Capacity is recorded per run in the manifest, as ADR-027 requires. The default of `0` is logged at startup as **unbounded**, so an unbounded run is never taken by accident.
- **Falsification / revisit trigger:** if trimming on the write-back path shows up in `mu_hit` or in miss-path latency under load, move the trim to a background sweeper. It is one `ZCARD` plus, only when over capacity, one `ZRANGE` and a small transaction per victim.
- **Invalidates:** **none — no runs exist.** `experiments/results/` contains no run directories, and no measurement has been taken under either eviction mechanism. Had any existed, all of them would be void: capacity governs hit rate directly, and a byte-budgeted cache and a count-bounded cache are not the same experiment.

---

### ADR-032 — `interfaces.md` v0.6: `product_id` on `/ask`, and the doc-id kind prefix
**Decided (frozen — contract change)** · 2026-09-06 · *`interfaces.md` §A, §C; ADR-028; ADR-030.*

`interfaces.md` moves to **v0.6** with two seam changes the two-lane rule depends on. §A's `POST /ask` request gains an **optional `product_id`**. §C promotes the `policy-` / `product-` **doc-id kind prefix** from an unstated convention to a required invariant.

- **Rationale for `product_id` — it is a *stabiliser*, which is not the role ADR-028 rejected it in.** ADR-028 rejected `product_id` as a *cache key*, correctly: it separates B-cross pairs but not B-within ones, so a corpus of only cross-product traps would make C1 redundant by construction. That argument stands and is untouched. What was missed is that a namespace derived from *rank-1 product document* is **unstable**. Measured 2026-09-06: the seed for "the EarBuds Pop 3" took `product-headphones-04` — the *Pro* variant — as rank 1, so a question about the Pro shared its namespace and was served the non-Pro answer (a false hit at similarity 0.9685), while a paraphrase of the original ranked `-03` first and was refused a reuse it deserved (a false miss). **One false hit and one false miss from the same instability, in one run.** Re-seeded with `product_id` on the request, both flipped to correct. Request metadata is known *before* retrieval and does not drift; provenance is known only after it. The rule still decides on provenance — `product_id` only pins which product the spec-lane namespace names.
- **Rationale for the prefix invariant.** `reuse.Classify` and `reuse.Namespace` read the document kind from the doc-id prefix. That prefix is enforced today only in `rag/src/rag/ingest.py:record_kind()`, while §C calls `doc_id` merely "a stable slug". The lane rule therefore depends on an unfrozen convention: a corpus built without it would classify every question `SPEC`, silently, with the lane machinery reporting plausible values throughout.
- **Alternatives, and why not:**
  - **Infer the product from retrieval only.** Rejected on the measurement above — that is the unstable path, and it produces errors in both directions.
  - **Make `product_id` required.** Rejected: it would break any caller that does not know one, and the fallback to rank-1 is correct behaviour, merely less stable. Optional keeps the contract backward-compatible.
  - **Derive the kind from a separate metadata field rather than the id prefix.** Rejected — it adds a field to every chunk record to encode what the id already carries, and the prefix is checkable by reading an id, which is what makes the invariant cheap to enforce at corpus-freeze time.
  - **Leave §C as convention and rely on `record_kind()`.** Rejected: the failure is silent, and the Go side cannot see the Python guard.
- **Consequences:**
  - Callers that send no `product_id` behave exactly as before, so the change is additive. The `/ask` response is unchanged.
  - `data-card.md` §7's corpus gate gains a fourth check: every `doc_id` starts with `policy-` or `product-`. This is cheap and belongs with G1–G3.
  - The **`stratum` label** used by the evaluation log (ADR-029) is deliberately **not** added to §A. It arrives as an optional `X-Thesis-Stratum` header, a measurement-harness affordance rather than part of the client contract; absent it, the label joins offline on `query_normalized`, which ADR-028's Tier-1 collision invariant makes exact.
  - §B is **not** part of this version. Letting `Answer` accept pre-retrieved chunks would remove the second retrieval on the miss path, but the mechanism is unresolved — the RAG service needs chunk *text*, not ids — and that decision gets its own ADR when it is designed.
- **Invalidates:** none — no runs exist. The change is additive at both seams and no measurement has been taken.

---

### ADR-033 — `Answer` accepts pre-retrieved chunks: one retrieval per request
**Decided (frozen — contract change)** · 2026-09-06 · *`interfaces.md` §B; ADR-007, ADR-030, ADR-032; rules.md #4, #6.*

`AnswerRequest` gains `repeated string retrieved_chunk_ids`. When non-empty the RAG service **skips its own retrieval** and grounds generation on exactly those chunks, loading their text from the `text` field declared in `store.build_schema()`. `interfaces.md` moves to **v0.7**.

- **Rationale — a banded miss retrieved twice, and the duplicate was the expensive half.** Every Tier-1 miss retrieves at least once: above `tau` in the cascade, below it inside `Answer`. Since the gateway began issuing its retrieval concurrently with the embedding (ADR-030's consequences), *every* miss reached `Answer` having already retrieved — and `Answer` then retrieved again. The wasted work is not the vector search but the **query embedding** the second retrieval redoes, measured at ~15 ms and the same call the gateway had just made.
- **Why this does not weaken ADR-007.** The two RPCs exist so the cascade can obtain overlap without paying for generation. That is untouched: `Retrieve` is unchanged and still the cascade's oracle. This only stops the *generation* path from repeating work the caller already did.
- **Consequences:**
  - **The service must return the ids it was given** in `source_chunk_ids`. Provenance is C1's input and C2's dependency key, so an entry written under a set that differs from the one its answer was generated over corrupts both contributions with no error (rules.md #6).
  - **Rank order is the caller's and is preserved.** Generation is order-sensitive, and ADR-030's namespace is derived from the rank-1 document *of each kind* — sorting or de-duplicating server-side would silently repartition the cache.
  - **A missing chunk id is dropped, never substituted.** Fabricating a chunk would put text into an answer that no provenance record accounts for; a short context is visible in the answer, an invented one is not.
  - Passing no ids preserves the old behaviour exactly, so the change is additive and any caller that does not retrieve first still works.
  - The service reads `text`, a field `store.build_schema()` declares — **not** a LlamaIndex-internal field. Generation is therefore not coupled to the library's storage layout.
- **Alternatives, and why not:**
  - **Send the chunk *text* rather than ids.** Rejected — it puts the whole context on the wire on every miss to avoid a Redis read of the same bytes, and it would let the gateway silently alter what the model sees.
  - **Cache the last retrieval per query inside the service.** Rejected — it makes a stateless RPC stateful and introduces a coherence problem across concurrent callers for no gain.
  - **Have the cascade skip retrieval below `tau` instead.** Rejected — that reverts the concurrency that took the hit path from ~35 ms to ~27 ms, to save a retrieval on the path where a multi-second generation dominates anyway.
- **Invalidates:** none — no runs exist. The regression on the four decisive queries reproduces the pre-change similarities exactly (0.4237 / 0.9244 / 0.9382 / 0.9578), with `sources` matching the ids the gateway retrieved.

---

### ADR-034 — `Retrieve`/`Answer` gain `product_id`: scope the search, not the reuse decision
**Decided (frozen — contract change)** · 2026-09-10 · *`interfaces.md` §B; ADR-014, ADR-028, ADR-030, ADR-032, ADR-033; rules.md #1, #4, #6.*

`RetrieveRequest` and `AnswerRequest` each gain an optional `string product_id`. When non-empty, `rag/src/rag/retrieve.py:retrieve()` runs the normal, unscoped, unchanged `top_k` search first, then **post-filters** the ranked result: drop any chunk belonging to a *different* product, and if `product_id`'s own chunk did not naturally rank, fetch it with one small product-scoped search and splice it in. Empty or absent `product_id` performs exactly today's unscoped search, byte for byte. `interfaces.md` moves to **v0.8**.

- **Rationale — the measured failure.** Found live 2026-09-09/10: a fresh, product-agnostic question ("what is the power rating of this item exactly right now") asked against three different products — a laptop, headphones, a furniture item — retrieved the identical five chunks from unrelated `product-kitchen-*` documents for all three, because those chunks contain the literal word "power" and `dev-v0` is one chunk per document across 44 docs, so a generic query has almost no signal to prefer the right product. This is the same corpus flatness `corpus_gate.py`'s G1/G2 shakedown already measured on `dev-v0` (0 pairs cleared `sim ≥ 0.85 ∧ J ≤ 0.2`), surfacing here as a single-query grounding failure rather than a cache false-hit. The LLM then generated an answer describing kitchen appliances instead of the asked product. Naming the product in the query text ("the Budget Note 15 laptop") correctly retrieves that product's own chunk, confirming the defect is retrieval's candidate set, not generation. The gateway already knows `product_id` before the question is asked — it is a first-class field on the product page (ADR-032) — and never passed it to retrieval.
- **Why this does not reopen ADR-028.** ADR-028 rejected `product_id` as a *cache-key* — a pre-retrieval signal substituting for the post-retrieval provenance signal C1 measures — because it would let a corpus of only cross-product traps make that substitution look free by construction. This change makes no cross-query comparison and touches no reuse decision at all: `reuse/lane.go`, `reuse/rule.go`, the Tier-1/Tier-2 key functions, and namespace/lane classification are all untouched and continue to derive their partition from post-retrieval `source_chunk_ids`, exactly as ADR-028 requires. `product_id` here answers "what material may this one retrieval draw from," never "should this candidate be reused." B-within/B-cross structure — the axis ADR-028's objection turns on — is irrelevant to a single-query candidate-set filter, so the objection does not transfer. (Same move ADR-032 already made for the namespace stabiliser, for a different mechanism: "it is a *stabiliser*, which is not the role ADR-028 rejected it in.")
- **Why this does not reopen ADR-032's "§B is not part of this version."** That line deferred a *different*, since-resolved feature (`Answer` accepting pre-retrieved chunk ids, resolved by ADR-033) — not a blanket freeze on §B. ADR-032's own justification for `product_id` — "known before retrieval, does not drift" — applies with equal force at this seam; this ADR exercises that same accepted premise where ADR-032 had not yet reached.
- **Why a post-filter, not a pre-filter — the first implementation regressed measurably.** The first version pre-filtered candidates to `doc_id == product_id OR kind == "policy"` before ranking. On `dev-v0` (four policy docs, one chunk per product) that eligibility pool has only five members at `top_k = 5`, so nearly every candidate came back **regardless of relevance** — `PolicyFraction` (`reuse/lane.go`) saturated toward ~0.8 for almost any product-scoped question, misclassifying plain `SPEC` questions as `POLICY` and collapsing their namespace to whichever policy document happened to rank first, a namespace shared by every *other* product asked a similarly generic question. Confirmed live 2026-09-10: `product-kitchen-05` (Air Fryer XL, a genuine `"power": "1800W"` spec) was served `product-laptops-02`'s cached "no power information" answer this way — a real cross-product false hit, and a worse failure than the one this ADR set out to close, because it needs no wording repeat, only two similarly-generic questions on different products. **Fix:** filter *after* ranking, not before it — drop a different product's chunk from the natural top-`k`, and only ever splice in the ONE chunk `product_id` itself owns (never blanket policy content) when it is otherwise absent. Policy content still reaches the result whenever it genuinely ranks — the `MIXED` lane's reason to exist (ADR-030) is unaffected — but it can no longer be forced in by construction of a too-small eligible pool. Regression test: `rag/tests/test_retrieve_scoping.py::test_scoping_does_not_flood_policy_chunks_for_a_plain_spec_question`.
- **Alternatives, and why not:**
  - **Enrich the query text via the `catalog` package** (splice the product's title into the text before embedding). Rejected — `catalog/`'s own header and `docs/design/architecture.md` §2 state it must never be reached from `/ask` or make any decision ("nothing here is on a measured path"); this would also silently change the reported query text on the measured path.
  - **Over-fetch `top_k` client-side and re-rank/filter in Go.** Rejected — `top_k` is frozen and reported per run (ADR-014, rules.md #1); a wider client-side fetch either changes what `top_k` means on the wire or adds a second, undeclared fetch-width concept, and still risks fewer than `top_k` correct candidates if the wider fetch also misses the right product.
  - **Enrich the query with the raw `product_id` slug, no title lookup.** Rejected — an embedding model has no principled reason to treat an id slug as semantically close to a natural-language question; unlike naming the product in prose (confirmed working), this is a probabilistic mitigation, not a deterministic one.
- **Consequences:**
  - `retrieve()` gains an optional `product_id` parameter; omitted or empty is bit-for-bit identical to today's behaviour (same nodes, same scores, same `top_k`), pinned by a regression test.
  - `Answer`'s own internal fallback retrieval (used when `retrieved_chunk_ids` is empty, ADR-033) is scoped identically, so a caller that never calls `Retrieve` first still gets scoped grounding.
  - `rag/src/rag/retrieve.py:make_retriever()` (the `corpus_gate.py` sweep) is explicitly **untouched** — it must keep measuring *unscoped* corpus ambiguity; the filter lives only in the single-query `retrieve()` path.
  - The gateway's two call sites (`Handler.tryTier2`'s concurrent-retrieve goroutine, and the coalesced-generation closure in `handler.go`) already had `req.ProductID` in scope; this is purely additive parameter threading, no restructuring.
- **Falsification / revisit trigger:** if a future corpus (`v1`) makes a product's own chunk *and* a same-category sibling both routinely relevant to one question (multi-chunk products), an equality filter on `doc_id` is too narrow and needs revisiting as a boost/re-rank rather than a hard filter.
- **Invalidates:** none — no runs exist that this affects. `make_retriever()`'s corpus-gate sweep path is untouched, so G1/G2's already-recorded `dev-v0` shakedown numbers (0 pairs, 0 B-within) stand unchanged; this only changes behaviour on requests that supply `product_id`, which no recorded run does yet.
---

### ADR-035 — Adopt the answer–evidence support gate: GroundedCache's fourth gate, at its published default
**Decided (method)** · 2026-09-21 · *decided with the advisor 2026-09-10, applied to the report and proposal 2026-09-15, recorded here 2026-09-21; ADR-016, ADR-018, ADR-023, ADR-026, ADR-030; report §2.3, §3.2.5, §4.4.2, §5.3.*

The reuse rule gains a fourth and final test, run after similarity, lane/namespace and containment have all accepted, and before a cached answer is served. The **support gate** compares the cached answer against the evidence the incoming query's own retrieval just returned, in two arms. **Lexical:** `S_lex(a, C) = |content-tokens(a) ∩ tokens(C)| / |content-tokens(a)|`, where content tokens exclude a fixed stopword list and tokens under three characters; reuse is refused when `S_lex < tau_s`. **Numeric:** every numeric literal and its unit in the cached answer must also appear in the fresh evidence, or reuse is refused — no threshold, fail-closed by construction. `tau_s` is **pinned at the value published with the gate (0.6) and is not swept**. The gate ships as an explicit **on/off ablation arm** across the frontier, not as an unconditional part of the rule.

- **Rationale — the gap is measured, not hypothetical.** Every test in the rule as it previously stood is computed over the query embedding and over chunk **identifiers**. None of them reads what the cached answer says. On 2026-09-06 a cached answer stating that electronics carry a thirty-day return window was scored against a **warranty** question about the same product: it and a genuine paraphrase of the original return question both scored containment of exactly **0.80**. No threshold on containment separates them — at the frozen retrieval depth the measure moves in steps of one fifth, and the one chunk carrying the entire semantic difference is one of five. ADR-030 attacked this from the partition side with the composite namespace and closed the measured case; the support gate attacks it from the side containment ignores, by reading the two pieces of text the rule has never consulted. On that same pair the cached answer's content tokens — *return*, *window*, *refund*, *day* — barely intersect the warranty chunk's *warranty*, *defect*, *coverage*; `S_lex` collapses and the gate refuses.
- **Rationale — the source paper measures this gate as the load-bearing one.** ADR-026 already cites GroundedCache to narrow C1 and maps three of its four gates onto this system's mechanisms. The fourth was not adopted. That paper's own per-gate ablation identifies the support gate as *the load-bearing safety mechanism* and reports that removing it raises the unsafe-served rate by **+0.125 on HotpotQA and +0.118 on mtRAG** (verified against the full text 2026-09-21; an earlier reading of "+0.12 to +0.13" overstated the upper end). An earlier draft treated it as a component this study chose not to run, which positioned the present rule as leaner than a four-gate conjunction. **That position is withdrawn**: a gate the source paper measures as load-bearing cannot be omitted from a system claiming a safety frontier, and adopting it at the published threshold is more defensible than arguing around it.
- **Rationale — why a numeric arm on top.** This domain is number-dense — *thirty-day*, *fourteen-day*, *1800 W* — and the return-against-warranty trap frequently differs precisely in its number even where the surrounding prose overlaps, which is the case lexical support is weakest on. The construction follows the proof-carrying-numbers protocol: numeric spans mechanically matched under a declared policy, checked by a renderer rather than a model, and **fail-closed**, so a number that cannot be verified blocks reuse rather than passing unremarked. Fail-closed is the correct default where the cost of a wrong commercial commitment is asymmetric.
- **Why this is admissible under constraints that excluded other mechanisms.** Three bind, and the gate satisfies all three. **No model on the serving path** (ADR-016): it tokenises, filters stopwords, intersects two sets and divides — no inference runtime, no learned parameter, no resident memory in an envelope where ~2 GB is one generation slot. **The decision reads provenance, never the query text** (the constraint that removed the bypass classifier, ADR-018): both inputs are artefacts of retrieval and generation, not predictions about wording, so a gate error cannot become a false-hit cause with no bucket to hold it. **Cost**: token arithmetic over a few hundred tokens, against a hit path measured at ~27 ms and dominated by the embedding and retrieval round-trips.
- **Alternatives, and why not:**
  - **Sweep `tau_s` as a fifth dimension.** Rejected — it would put five free parameters against the fixed-threshold baseline's one, worsening the unequal-tuning threat this study already carries, and it would convert a **citation** into a **result** requiring its own defence. Sweeping it, or learning it per entry the way vCache learns τ, is named as future work.
  - **An NLI / entailment gate, negation-aware embeddings, or an LLM judge per query.** Rejected categorically — ML on the hit path, or a break in the frozen embedding model, or paying for the generation the cache exists to avoid. This is a finding rather than a scope excuse: *The Semantic Illusion* evaluates similarity and NLI detectors under conformal calibration and finds both reach a **100 % false-positive rate** at target coverage on the hard cases, while a full large-model judge reaches roughly **7 %** on identical data. The cheap instruments do not reach this case; the instrument that does costs the thing being cached.
  - **A margin / gap check** (rank-1 against rank-2 similarity). Rejected for *this* trap specifically — the measured false hit scored **higher** similarity than the correct reuse (0.9578 against 0.9382), so a margin check would not have flagged it. Cited in related work, not built.
  - **Decline the gate and differentiate against it.** Rejected — see above; the position is not defensible against the source paper's own ablation.
- **Consequences:**
  - **A frozen contract change is required before the gate can run at all.** The gateway holds chunk identifiers and scores, never chunk text. Recorded separately as **ADR-037**.
  - **Configuration 4 becomes two arms, not one run** — gate off and gate on across an otherwise identical configuration, so that the reuse it suppresses and the false hits it prevents are both attributable to it rather than inferred from a conjunction. This is an arm within ADR-023's grid, not a sixth configuration; it doubles configuration 4's runs.
  - **The on/off arm moves into the non-negotiable list** of the drop order, for the same reason ADR-019 put the labelling ablation there: without it a frontier improvement cannot be assigned to containment, to the namespace partition, or to the adopted gate. The **numeric** arm remains droppable — lexical is the arm the source paper measures as load-bearing.
  - **The evaluation log gains a reuse-refusal cause code** distinguishing similarity, namespace, containment and support refusals, and the two support arms are reported separately and never summed. Without it a support refusal is indistinguishable from a namespace refusal and the gate's contribution cannot be attributed. Contract change to `interfaces.md` §H, owed alongside ADR-036's.
  - **One differentiator against GroundedCache is withdrawn**, and recorded as withdrawn rather than quietly dropped. What remains is the partition, the sweep, the envelope, and the published residual — a smaller claim than the study opened with, and the one the evidence supports.
  - **The residual is narrowed, not closed.** Where retrieval genuinely returns the *same* chunk both times and the query flips a condition within it, the fresh evidence is identical either way, support is full regardless of which reading is asked, and containment is 1 by construction. The only available lever is corpus-side — **ADR-038**. The surviving rate is reported as RQ2a with its own interval.
  - **The price of safety is registered in advance, and the full text sharpens what that price is.** GroundedCache's Table 6 reports, against a no-cache baseline: naive caching **1.95×** at USR 0.172, the **no-support** variant **1.48×** at USR 0.125, and the fully gated system **1.04×** at USR 0.000. The collapse from 1.95× to 1.04× is therefore **not** the support gate's doing alone — **1.95× → 1.48× is the other three gates, and 1.48× → 1.04× is the support gate's own price.** That distinction matters here specifically: this study already has GroundedCache's other three gates (similarity, overlap, the dataset-epoch guard — ADR-026), so **1.48× → 1.04× is the figure that transfers**, not 1.95× → 1.04×. If that shape holds, a single speedup number describes neither objective honestly, which is why the headline is a frontier and why a second null is pre-registered.
  - ✅ **Both motivating figures verified against the full text, 2026-09-21** (arXiv HTML rendering of 2605.27494v1), and one was corrected: the ablation is **+0.125 / +0.118**, not "+0.12 to +0.13". Also confirmed at source: the gate's formula is exactly `S(a,C) = |τ(a) ∩ τ(C)| / |τ(a)|` with `τ(x) = {t ∈ toks(x) : t ∉ W ∧ |t| ≥ 3}`, and **`τ_s = 0.6` is the paper's stated default** — so the pinning above cites a real published default rather than a number inferred from an abstract. The paper's evaluation is ~12,000 real generations with Qwen2.5-7B-Instruct on vLLM across two datasets.
- **Falsification / revisit trigger:** if both arms refuse at a rate near zero on `v1`, the gate is inert on this corpus, the two ablation arms coincide, and *that* is the finding — reported, not tuned away. If the lexical arm instead collapses the hit rate into configuration 1's interval, the second pre-registered null applies. Neither outcome is corrected by moving `tau_s`.
- **Invalidates:** none — `experiments/results/` holds no run directories (verified 2026-09-21).

---

### ADR-036 — Retire the unfiltered similarity-only phase, `tau_high`, and the inline counterfactual
**Decided (method)** · 2026-09-21 · *decided with the advisor 2026-09-10, recorded here 2026-09-21; supersedes ADR-030's `tau_high` knob; ADR-019, ADR-023, ADR-026, ADR-029, ADR-035; `interfaces.md` §H, `experiment-protocol.md` §4/§6.*

The cascade's unfiltered Phase-1 Tier-2 search and its `tau_high` short-circuit are **removed** — code, environment variable, and the pinned-default test. The `similarity_only_decision` field is **retired** from the per-request evaluation log. The counterfactual it carried is recovered offline instead, by joining configuration 3's and configuration 4's logs on query identifier, which is valid only on the **static-cache** arm where both runs are guaranteed identical cache state. In its place §H carries the reuse-refusal **cause code** ADR-035 requires.

- **Rationale — correctness alone was not sufficient, and was not the reason.** Phase 1 is already redundant for the served verdict: the lane rule independently re-checks `sim >= tau` against its own namespace-scoped candidate, so the outcome is identical with or without the unfiltered phase. That was known and deliberately judged **insufficient** grounds to remove it, because Phase 1 was the *only* source of `similarity_only_decision`, which `interfaces.md` §H marks measurement-critical.
- **Rationale — what makes it sufficient is the framing pivot.** C1's headline moves away from *"provenance beats similarity-only"* — a claim ADR-026 already partly conceded as concurrent work — and toward the namespace-partitioned containment rule augmented by ADR-035's support gate, with the residual characterised rather than eliminated. Under that framing the inline similarity-only counterfactual is no longer the headline measurement, and the phase that produced it has no remaining function.
- **Rationale — `tau_high` was unsafe in exactly the way it was assumed not to be.** It was shipped disabled at `1.0` on the reasoning that the value was unreachable. It is reachable: a literal repeat re-embeds to a bit-identical vector, giving cosine exactly `1.0`, and the short-circuit then serves a reuse **with no provenance check having run at all**. Separately, ADR-030's own consequence note already recorded that since retrieval is issued concurrently with the embedding, a short-circuit **saves no latency** — retrieval has completed by the time the gate is reached. A knob that cannot buy latency and can serve unchecked reuse is a trap, not an option.
- **Consequence that is easy to miss — the static-cache ablation becomes non-negotiable.** With the inline field gone, *decisions changed by provenance* is a **cross-configuration join**, and a join is only meaningful where both runs saw identical cache state. The previous drop order listed the static-cache arm at position 5 while simultaneously calling that metric non-negotiable (ADR-019). Both could not hold. The arm moves up; the drop order is corrected accordingly.
- **Alternatives, and why not:**
  - **Keep Phase 1 solely to produce the counterfactual.** Rejected — it retains a branch on the measured hit path whose only purpose is measurement, keeps `tau_high` alive with it, and buys a number that the cross-configuration join recovers on the arm where it is actually interpretable.
  - **Keep `tau_high` disabled-but-specified, for the frontier point.** Rejected — the frontier point it would supply is *similarity with no provenance check*, which is configuration 3. Configuration 3 already measures it, as an independent benchmark run rather than as an inline branch.
- **Consequences:**
  - **Configuration 3 is unaffected and still measured.** It is a standalone configuration in ADR-023's grid; it never depended on Phase 1 running inline inside configuration 4 or 5. The GPTCache-equivalent baseline is not lost.
  - `interfaces.md` §H: `similarity_only_decision` removed, refusal cause code added. Contract change, owed together with ADR-035's and ADR-037's in one version bump.
  - `experiment-protocol.md`: *decisions changed by provenance* restated as a cross-configuration join scoped to the static-cache arm; §4's *"% entering the cascade band"* keeps ADR-030's restated reading; the drop order updated per the point above.
  - Code removed: the cascade's unfiltered `k=1` search, `REUSE_TAU_HIGH` and its default-pinning test, and the `reuse_rule=similarity_only` outcome that only a short-circuit could produce. The scoped search, `DecideLane`, the band and the composite namespace of ADR-030 are untouched.
  - The cascade becomes **one** vector search rather than two, which is a small reduction in Tier-2 lookup work; it is not claimed as a latency result, since the hit path is bounded by the retrieval round-trip.
- **Invalidates:** none — `experiments/results/` holds no run directories (verified 2026-09-21). No recorded number was produced by Phase 1 or by a `tau_high` short-circuit; the functional runs of 2026-09-06 are explicitly not citable.

---

### ADR-037 — `Retrieve` returns chunk text: `interfaces.md` v0.9
**Decided (frozen — contract change)** · 2026-09-21 · *`interfaces.md` §B; `contracts/rag/v1/rag.proto`; ADR-008, ADR-014, ADR-033, ADR-034, ADR-035; rules.md #1, #4, #6.*

`RetrieveResponse` gains `repeated string texts`, positionally aligned with `chunk_ids` — `texts[i]` is the text of `chunk_ids[i]`, or the field is absent entirely. `interfaces.md` moves to **v0.9**. Both sides of the seam change: `rag/src/rag/retrieve.py` populates it, `gateway/internal/ragclient/retrieve.go` carries it, and the cascade hands it to the support gate.

- **Rationale.** ADR-035's support gate compares the cached answer against the evidence the incoming query's retrieval just returned. The gateway holds chunk **identifiers** and relevance scores; it has never held chunk text. **The gate cannot run at all without this change** — it is the one contract change ADR-035 requires, and it is the reason ADR-035 alone does not ship a working gate.
- **Why this is not a new coupling to LlamaIndex internals.** `text` is a field `rag/src/rag/store.py:build_schema()` declares, so reading it reads a **schema field**, not a storage-layout detail. ADR-033 established exactly this distinction when the same objection was raised and then found to be wrong: the probe that suggested otherwise had used a malformed key, because corpus keys carry a **double** colon (`corpus::{chunk_id}`) where LlamaIndex appends its own separator to the configured prefix.
- **Alternatives, and why not:**
  - **Fetch the chunk text from Redis in Go, on the hit path.** Rejected — it adds a Redis round-trip to a hit path whose whole cost structure is already the embed and retrieve round-trips, and it re-implements the double-colon corpus-key quirk in a second language, where a divergence would be silent. The retrieval call is already being made; the text is already in hand on the Python side.
  - **Send the cached answer across the seam and compute the gate in the RAG service.** Rejected — the reuse decision lives in `reuse/` by architectural rule (`docs/design/architecture.md` §2). Moving a gate across the seam puts part of the rule in the service the rule is deciding whether to avoid calling, adds an RPC to the hit path, and makes the rule's determinism and cost harder to account for.
  - **Return text only when the caller asks (a `want_text` flag).** Rejected as premature — it adds a second response shape to a frozen contract to save bytes on a path that is about to want text on every Tier-1 miss anyway. Revisit if response size is ever measured as a cost.
- **Consequences:**
  - **ADR-033's three obligations extend to `texts`, and gain a fourth.** Return the ids you were given; preserve rank order; drop a missing id rather than substitute one; **and `texts` must stay positionally aligned with `chunk_ids`**. A misaligned array scores a cached answer against the wrong evidence and produces a support verdict that is wrong with no error anywhere — the same class of silent failure as the three invariants of `interfaces.md` v0.3.
  - Response size grows by roughly `top_k × chunk_size` tokens of text per retrieval. At the frozen retrieval depth and chunk size this is a few kilobytes on a local gRPC seam; it is recorded here so that a later latency reading is not attributed to it without measurement.
  - `interfaces.md` §B and `contracts/rag/v1/rag.proto` both change; the version bump carries ADR-035's and ADR-036's §H changes in the same revision.
  - The corpus-gate path (`make_retriever()`) is untouched, as it was under ADR-034 — it measures unscoped corpus ambiguity and needs no text.
- **Falsification / revisit trigger:** if the support gate is measured inert on `v1` (ADR-035's first trigger), this field is carried at a cost with nothing reading it, and the contract should be revisited rather than left as decoration.
- **Invalidates:** none — `experiments/results/` holds no run directories (verified 2026-09-21). The field is additive; an absent `texts` is today's behaviour exactly.

---

### ADR-038 — Condition-splitting is a `v1` corpus requirement, independent of the chunk-count rule
**Decided (data)** · 2026-09-21 · *`data-card.md` §2, §7; ADR-024 (requirement 3), ADR-028, ADR-035; report §3.6.1.*

`v1`'s policy documents are split on clause and section structure so that **one chunk carries one condition**. A paragraph stating the opened and the unopened condition together, or the return window and the warranty window together, is split before the corpus is frozen. The corpus gate gains a **fifth criterion, G5**: no chunk states two opposing conditions of the same kind. The explicit structured `condition:` tag — a metadata field on each chunk, with reuse additionally requiring tag-set agreement — is **considered and not adopted**; the split alone is required.

- **Rationale.** This is ADR-035's residual, addressed at the only place it can be addressed. Where retrieval genuinely returns the same chunk for two questions that differ only in the condition asked about, containment is **1 by construction**, the support gate sees **full support either way**, and similarity is no help because the token carrying the entire semantic difference is a negation or a single condition word that carries almost no weight in the embedding. Every signal this design permits itself is blind to that case, and the permitted alternatives do not rescue it (ADR-035's alternatives). Splitting conditions apart at authoring time is the **only** lever this design has, and it exists only while the corpus is being written.
- **Why this is a second and independent requirement, not a restatement of ADR-024 requirement 3.** Requirement 3 asks for policy documents long enough to yield at least three chunks, so that **containment has something to sweep** — it is about giving θ a gradient. This requirement is about whether the phenomenon **can be separated at all**. The two must not be conflated: a document can satisfy requirement 3 with three chunks and still state both conditions inside one of them, which satisfies the letter of requirement 3 while leaving the residual structurally unavoidable.
- **Why the explicit tag is not adopted.** It would add a second mechanism — a metadata field, a tag-agreement term in the reuse rule, and an authoring obligation per chunk — to close a case the split already closes, and it would put a fifth term in a rule whose parameter count is already the study's standing unequal-tuning threat. The split is enforceable by a gate criterion over the frozen corpus; a tag would additionally have to be kept correct by hand. Named as future work rather than rejected on merit.
- **Alternatives, and why not:**
  - **Leave the residual entirely to measurement and report it.** Rejected — it is cheap now and impossible after the freeze, and a residual that could have been reduced for the cost of a corpus-authoring rule is not a structural limit, it is an omission.
  - **Reduce the chunk size so conditions separate on their own.** Rejected — `chunk_size` is frozen (ADR-014) and changing it invalidates every cross-configuration comparison; it would also be a probabilistic mitigation where clause-level splitting is a deterministic one.
- **Consequences:**
  - `data-card.md` §7's gate becomes **five** criteria. G5 is **structural** — it runs in stage 1 alongside G3 and G4, over corpus files alone, with no ingested index required.
  - `data-card.md` §2 records condition-splitting as a property of the authored policy documents, alongside ADR-024's per-category warranty windows and ADR-028's B-within stratum.
  - **RQ2a**: the rate at which same-evidence, opposite-condition pairs survive every gate is reported with its own confidence interval, on ADR-028's within-product stratum built to contain them — stated as the boundary of the claim rather than absorbed into it.
  - **A threat to validity, recorded as such.** The measured residual is partly a property of how carefully the author split conditions, and would be worse on a corpus not authored with this failure in mind. This bounds the external validity of the C1 result and belongs in the limitations, not in the engineering backlog.
  - `experiments/scripts/corpus_gate.py` gains the G5 check; the stage-1/stage-2 split of `data-card.md` §7 is unchanged in shape.
- **Falsification / revisit trigger:** if G5 passes on `v1` and RQ2a still measures a material residual, the split was not the binding constraint and the explicit tag — or a finer authoring rule — returns to the table with evidence behind it.
- **Invalidates:** none — `experiments/results/` holds no run directories (verified 2026-09-21), and `v1` is not yet frozen. This requirement is **only** actionable before that freeze.
---

### ADR-039 — `v1` corpus source is Amazon-PQA, and redistribution stays closed
**Decided (data)** · 2026-09-21 · *supersedes the `Amazon-Reviews-2023 × AmazonQA` plan of `data-card.md` §1/§3; ADR-013, ADR-020, ADR-024, ADR-027, ADR-028, ADR-035, ADR-038.*

`v1`'s product and question halves come from **Amazon-PQA** (`s3://amazon-pqa`, AWS Open Data, one JSON-lines file per category), replacing the planned join of `Amazon-Reviews-2023` metadata with `AmazonQA`. Each PQA record carries the question **and** the product content, so the join does not have to be performed and `asin`-against-`parent_asin` stops being a risk to measure. The policy corpus, the update set and the strata labels stay **self-authored**, unchanged. **Redistribution remains closed**: `data/v1/` stays gitignored and ships as a download-and-build script plus a hash manifest, which is `data-card.md` §1's stated fallback and ADR-013's path.

- **Rationale — the join problem is deleted rather than reduced.** `data-card.md` §1 and §3 planned two datasets joined on a product identifier whose semantics the source's own documentation warns about ("the `asin` in previous Amazon datasets is actually parent ID"). An unverified join rate sat under the corpus plan as an unquantified risk. PQA removes the second dataset entirely.
- **Rationale — measured, not assumed (probe, 2026-09-21).** Two complete category files were read, and the question this decision turned on was whether PQA is thick enough per product to seat strata **A** and **C** naturally.

  | | `inkjet_printers` | `chairs` |
  | :--- | ---: | ---: |
  | products | 1,288 | 19,193 |
  | questions | 92,070 | 88,268 |
  | questions per product, median | **8** | 2 |
  | products with ≥ 5 questions | **63.7 %** | 24.3 % (**4,664 products**) |

  Across `inkjet_printers`, **43.6 %** of multi-question products carry at least one genuine near-duplicate question pair (content-word Jaccard 0.45–0.99, exact repeats excluded) — e.g. *"can it print address labels?"* against *"Does it print labels?"*. Strata A and C can therefore be **sampled** rather than authored, which is the advantage the switch was proposed for.
- **Rationale — an argument that did not exist when the switch was proposed: PQA supplies B-within traps naturally.** The same clustering surfaces same-product pairs that read as paraphrases and have **different answers** — *"Does printer work with windows 10?"* against *"Will this unit work with Windows 7?"*; *"will it work with an IPAD 2?"* against *"Does this printer work with an iPad and an iPhone?"*. That is exactly ADR-028's `B-within` stratum and exactly ADR-035's residual, occurring in natural traffic. The C1 result's standing limitation is that the measured residual is *"partly a property of how carefully the author split conditions across chunks"* (ADR-038); traps the author did not construct weaken that objection in a way an authored corpus cannot.
- **⚠️ Redistribution is NOT settled by the licence, and the earlier reading of it was wrong.** The AWS Open Data Registry entry records `License: https://cdla.dev/permissive-1-0/`, which would permit redistribution with attribution. The dataset's **own `readme.txt`** — named as `Documentation:` by that same registry entry — instead carries the ACM personal/classroom notice: *"Permission to make digital or hard copies … for personal or classroom use … provided that copies are not made or distributed for profit or commercial advantage … For all other uses, contact the owner/author(s). Copyright held by the owner/author(s)."* The string "CDLA" does not appear in it. **Where two sources conflict, this study takes the more restrictive one**, because the cost of being wrong is asymmetric and falls on a public repository. Consequence: using PQA for the thesis is the granted case, **publishing a derived corpus is not**, and `data-card.md` §1's `TODO(W8)` is answered *"no, ship the build script"* rather than closed as permitted. The required citation is Rozen et al., NAACL 2021, supplied by the readme.
- **⚠️ The switch does not help ADR-024 requirement 3, and the claim that it does is withdrawn.** It was argued that free-text `bullet_points` would chunk past `chunk_size` more readily than a spec table. Measured: median product prose is **504 characters** (≈ 126 tokens at the frozen `chunk_size = 256`), `product_description` is frequently empty, and only **1.6 %** of products would yield ≥ 3 chunks. PQA products ingest at roughly **one chunk each**. Requirement 3 rests entirely on the **authored policy** half, exactly as it did before. What *does* improve is corpus **diversity**: `dev-v0`'s G1 failure came from 44 chunks in total, where one PQA category alone supplies over a thousand.
- **⚠️ The dataset's documentation does not match its data.** `readme.txt` describes `asin_id`, `bullet_points`, `is_yes-no_question`, `yes-no_answer`, `answer_text`. The bytes carry **`asin`**, **`bullet_point1` … `bullet_point5`**, **`question_type`** (`yes-no` \| `WH`), **`answers`** (a list of objects) and **`answer_aggregated`**. A builder written against the documentation produces empty records with no error — the probe's first run did exactly that. The corpus builder must be written against the bytes and must assert a non-zero parse rate.
- **Alternatives, and why not:**
  - **Keep `Amazon-Reviews-2023 × AmazonQA`.** Rejected — it carries an unmeasured join rate, a documented identifier ambiguity, and the same unresolved redistribution question, for no offsetting benefit.
  - **Author the product catalogue as well, as `dev-v0` did.** Rejected — `dev-v0`'s authored catalogue is precisely what G1 measured at **0 qualifying pairs**, and authored strata A/C paraphrases would make the C1 result a property of the author's paraphrasing rather than of natural traffic. This is the objection natural data exists to answer.
  - **hetPQA, or Amazon ESCI.** Rejected — hetPQA is also Amazon-sourced with the same licence question and less product content; ESCI was already rejected earlier for lacking questions.
  - **Treat the registry's CDLA line as authoritative and publish the corpus.** Rejected — see above.
- **Consequences:**
  - `data-card.md` §1 and §3 are rewritten to PQA: source, access method (public S3 over plain HTTPS; no credentials and no AWS CLI required), the real field names, the category list, and the selection rule.
  - **Selection, not sampling.** Questions-per-product is heavily skewed within a category (printers: p99 = 958, max = 5,741) and varies ~4× *between* two categories both on the original shortlist. A uniform draw from a thin category returns mostly single-question products, from which no A or C pair can be built. The builder selects into the thick tail and records the rule it used.
  - Category choice must now satisfy **two** constraints together — ADR-024 requirement 2 wants categories whose return and warranty windows genuinely differ, and this ADR wants categories thick in questions per product. The earlier shortlist was assembled against the first only.
  - `experiments/scripts/fetch_corpus_v1.py` is superseded and its output `data/v1-draft/` is discarded; both it and `data/v1/` stay out of git.
  - `data-card.md` §1's licence row becomes **"academic use granted; redistribution not granted — build script + hash manifest"**, and the per-artifact `TODO(W8)` rows for the product and question halves are answered by this entry rather than by the freeze.
  - The policy corpus, the update set, ADR-038's G5 condition-splitting and the strata definitions are **untouched** — this ADR changes where product and question text comes from, nothing about the experimental design.
- **Falsification / revisit trigger:** if the selected categories cannot jointly satisfy requirement 2's policy differentiation and this ADR's thickness requirement, the corpus falls back to PQA products with **authored** A/C paraphrases, and the natural-trap argument above is withdrawn with it — stated here so the fallback is not taken silently.
- **Invalidates:** none — `experiments/results/` holds no run directories (verified 2026-09-21) and `v1` is not yet frozen. `dev-v0` is unaffected and remains the functional corpus.
---

### ADR-040 — Co-hosted load generation, bounded: an amendment to ADR-012
**Decided (method)** · 2026-09-21 · *amends ADR-012; ADR-017, ADR-022, ADR-027; `experiment-protocol.md` §1, §4; `super-plan.md` "Measuring without a second machine".*

ADR-012 requires load generation to run off-box. **No second machine exists and none is dated** (confirmed with the author 2026-09-21). Rather than leave that as a silent deviation, ADR-012 is amended: **off-box remains required for any figure reported as a ceiling**, and **co-hosted generation is admissible for bounded-rate sweeps** where (a) the generator's own CPU and resident footprint are measured and recorded for that run, (b) memory pressure stays green throughout with the generator running, and (c) the resulting figure is reported as a **bound** with the direction of the co-hosting bias stated. The green-pressure discard rule of ADR-012 and `experiment-protocol.md` §1 is **unchanged** — a run leaving green is still discarded and repeated at lower load.

- **Rationale — the two measurement regimes are not the same, and lumping them loses the distinction.** The 2026-09-06 run that drove macOS memory pressure to *urgent* was the **Tier-1 μ_hit probe at 400 req/s**, driving a path that serves ~8000 req/s. The main capacity sweep is a different regime entirely: μ_gen ≈ 0.19 req/s caps `λ_max` at ≈ 16 req/s even at the best hit rate the redundancy sweep can reach, so the sweep offers **≲ 16 req/s** and a generator at that rate is cheap. Treating "co-hosting is invalid" as uniform would discard the sweep to protect against a hazard that only the ceiling probe creates.
- **Rationale — the headline claim is an inequality, and the bias runs in its favour.** S1's claim is not a value but that `h* = μ_hit / (μ_gen + μ_hit)` lies **outside** the range of `h` the workload reaches (≈ 0.988), i.e. that the system is generation-bound throughout its operating range (ADR-027). `h*` is **monotone increasing in μ_hit**, and co-hosting **depresses** μ_hit — the generator starves the embedding server that bounds the Tier-2 hit path. A co-hosted measurement is therefore a *lower* bound on μ_hit and hence a *lower* bound on `h*`. At the already-measured co-hosted **61 req/s**, `h* ≥ 0.9969 > 0.988`: the finding stands **at the bound**, and an off-box run could only raise μ_hit and strengthen it. **A bound is sufficient for the claim being made.**
- **What this does NOT license, stated so it cannot be read as blanket permission:**
  - **Any figure presented as a ceiling rather than a bound.** The Tier-1 μ_hit number in particular is reported as a lower bound and labelled as one.
  - **Latency percentiles at high offered rate**, where generator and system under test contend for the same cores. Either the generator's concurrent CPU is reported alongside p95, or p95 claims are restricted to the rates where the footprint measurement shows headroom.
  - **Any relaxation of the green-pressure rule.** Unchanged.
- **Alternatives, and why not:**
  - **Wait for a second machine.** Rejected — there is no date, and the remaining budget cannot absorb an open-ended block on the entire capacity half of the study.
  - **Rent a cloud VM as the generator.** Rejected as the default, kept as an option: the hit path is ~27 ms, so a WAN round-trip of tens of milliseconds would dominate p95 and the measurement would describe the network. It would be usable for goodput and saturation but not for latency, which is a narrower gain than it first appears.
  - **Drop Headline A to a qualitative claim.** Rejected — it is S1, and `Final_Proposal.md` §12 lists the load-testing evaluation as non-negotiable.
  - **Report co-hosted numbers without the footprint measurement.** Rejected — that is the silent deviation this ADR exists to prevent; the measurement is what separates a bound from a guess.
- **Consequences:**
  - `super-plan.md` item **1.6** measures the generator's footprint, and Phase 7 runs under this régime.
  - Every co-hosted figure carries its interference measurement in the run manifest, and the write-up states the limitation rather than arguing around it.
  - ⚠️ **Two margins that must not be conflated.** ADR-027's falsification trigger (μ_hit ≤ ~16 req/s) is **cleared** by the lower bound of 61, but by only **3.8×**. That is a different comparison from *"μ_gen ≪ μ_hit by two to three orders of magnitude"*, which is separately correct (0.19 against 61 is ~320×) and which licenses `h* > 0.99`. The second margin is the one a co-hosted lower bound must clear, and it clears it with far less room, so the two are stated separately wherever both appear. (`Final_Proposal.md` §3's own wording — *"observable only if μ_hit ≤ ~16 req/s"* — is accurate; an earlier note in `two-lane-cache/approvals.md` attributed to it a phrase, *"far above ~16 req/s"*, that it does not contain.)
- **Falsification / revisit trigger:** if item 1.6 measures the generator's footprint as large enough to move the system under test out of green at the sweep's own rates, this amendment does not apply and the sweep cannot be run co-hosted at all — in which case the honest outcome is a reduced load range, reported as such, not a run taken anyway.
- **Invalidates:** none — `experiments/results/` holds no run directories (verified 2026-09-21). The 2026-09-06 co-hosted probe was already marked non-citable and stays so; this ADR governs future runs only.
