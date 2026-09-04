# Decision Log (ADRs)

**Status:** living document · **Created:** 2026-07-23 · **Last revised:** 2026-09-02 (ADR-026 … ADR-029)
**Companion to:** `Final_Proposal.md` (rationale source), `interfaces.md` (schemas these decisions pin), `time_line.md` (decide-by weeks).

> **Read ADR-016 first.** It records the 2026-08-09 scope reduction and supersedes or closes several entries below. Section references in older entries point at the archived proposal; the mapping to current sections is in ADR-016.

**How to use.** One entry per architecturally significant choice. `Decided` choices are **frozen** for the study (swapping a frozen model/threshold mid-study invalidates cross-configuration comparisons — proposal §10). `Open` choices carry a **decide-by week** from `time_line.md`; when resolved, flip the status, add the date, and keep the entry (do not delete — the write-up's design chapter and the defense Q&A draw from this history). Entries seeded from the proposal are dated 2026-07-23 and marked *ratified in proposal*.

| ID | Decision | Status | Decide-by |
| :--- | :--- | :--- | :--- |
| ADR-001 | Go for the gateway | Decided | — |
| ADR-002 | Gemma 4 E4B / Ollama / 4-bit | **Superseded by ADR-021** | — |
| ADR-003 | Embedding model: `nomic-embed-text`, 768-dim | **Decided (frozen)** | — |
| ADR-004 | Redis + RedisVL for cache & corpus vectors; no Elasticsearch | Decided | — |
| ADR-005 | Bounded cache, fixed capacity + LRU | **Decided** (capacity set by ADR-027) | — |
| ADR-006 | False-hit budget δ ≤ 5% | Decided (provisional) | finalize W14 |
| ADR-007 | gRPC, with a retrieval-only RPC for the C1 cascade | Decided | — |
| ADR-008 | Stable chunk-ID scheme `{doc_id}#chunk-{ordinal}` | Decided | — |
| ADR-009 | Single-node envelope; scale-out = future work | Decided (scope) | — |
| ADR-010 | Predictor-gated invalidation w/ blind-purge fallback | **Superseded by ADR-016** | — |
| ADR-011 | Small routing model (RQ4) | **Rejected by ADR-016** | — |
| ADR-012 | Load generation off-box | Decided | — |
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
