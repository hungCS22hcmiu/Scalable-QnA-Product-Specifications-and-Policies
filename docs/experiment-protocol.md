# Experiment Protocol & Reproducibility

**Status:** Draft v0.3 · **Created:** 2026-07-23 · **Revised:** 2026-09-02 (ADR-027, ADR-028, ADR-029)
**Companion to:** `Final_Proposal.md` (§7 environment, §9 evaluation, §10 budget), `decisions.md` (frozen choices), `data-card.md` (dataset versions).

**Purpose.** Make the proposal's promised rigor operational — "every figure regenerable from scripts" (proposal §7/§11). This document defines *what is frozen*, *what is recorded per run*, *exactly how each metric is measured*, and *how significance is computed*, so a result is reproducible and a reviewer can regenerate any figure from raw data. Nothing here adds claims beyond the proposal; it pins measurement so the claims are checkable.

---

## 1. Reproducibility invariants

**Frozen for the whole study** (a mid-study change invalidates cross-config/cross-load comparisons — proposal §10; see `decisions.md`):
- LLM: Qwen 3.5 2B / Ollama / 4-bit (`q4_K_M`) / `num_ctx=8192` / `think: false` on every call (ADR-021, supersedes ADR-002).
- Embedding model + dimension: `nomic-embed-text`, 768-dim (ADR-003) — identical across all **5** configs (proposal §9.2).
- Chunking config: `chunk_size=256`, `chunk_overlap=40` (ADR-014) and chunk-ID scheme (`interfaces.md` §C).
- **Cache-capacity ratio `C/K = 0.25`** (ADR-027) — the *ratio* is frozen, the absolute is `round(0.25 × K)` derived at corpus freeze from `K`, the distinct-query count. An absolute capacity is **not** frozen, because at `C ≥ K` nothing is ever evicted and the redundancy sweep of §6 collapses to a constant at every skew level. Plus the **two-region eviction policy** — cache entries under LRU, dependency state under `noeviction` (ADR-005).
- Dataset snapshot (`data-card.md`, `dataset_version` + `snapshot_sha256`).

- `top_k = 5` (ADR-014) and the **FLAT (exact) vector index** — no mid-study HNSW upgrade; approximate retrieval would inject overlap noise indistinguishable from C1's signal.
- `num_ctx = 8192` and `OLLAMA_NUM_PARALLEL = 4` — **frozen from the feasibility spike below** (ADR-017), not assumed.
- The two-region Redis eviction policy (`interfaces.md` §D): cache under LRU, dependency state under `noeviction`.

**Recorded once per experiment campaign** (environment card, committed with results):
- Versions: Go, Python, Ollama, model tags, Redis, RedisVL, k6/Locust.
- Hardware: MacBook M1, 16 GB (proposal §7); load-generator machine spec.
- `OLLAMA_NUM_PARALLEL` (pinned; sets the parallel-generation ceiling the admission pool is sized against).
- **gRPC channel configuration** — number of channels and `MaxConcurrentStreams` per connection, plus keepalive settings. ⚠️ Not optional and not left at defaults: HTTP/2 caps concurrent streams per connection, so an exhausted channel queues **client-side** and is indistinguishable from gateway saturation in the admission-control results (ADR-007, proposal §7.0, §9.4). The transport stack is **identical across all configurations** so that a frontier difference cannot originate in it.
- **Client-side gRPC queueing** is measured and reported **separately from permit-queue depth** — conflating them would misattribute a transport limit to the admission policy.

### 1.1 Feasibility spike and memory budget — **precedes all implementation**

The envelope is measured before it is claimed (proposal §7). Grid: `num_ctx ∈ {4096, 8192} × OLLAMA_NUM_PARALLEL ∈ {1,2,4}`, realistic ~2K-token prompts, each cell driven to sustained concurrency. Per cell record peak footprint, `memory_pressure` zone, `sysctl vm.swapusage`, and aggregate tokens/sec. Freeze the largest pair that holds **green** under sustained load.

| Component | Budget | How obtained |
| :--- | :--- | :--- |
| macOS baseline (other apps) | ~9–10 GB used / ~5–6 GB free — author-maintained operating discipline, not a dedicated empty-machine baseline (`decisions.md` ADR-017) | `vm_stat` / `memory_pressure`, other apps closed to this ceiling before testing |
| LLM weights + KV cache resident | **1.6–1.7 GB** (Qwen 3.5 2B, `q4_K_M`, `think:false`, across `num_ctx∈{4096,8192}`) | `ollama ps` after generation |
| KV cache per concurrent sequence | **~0.1 GB** delta, `NUM_PARALLEL` 1→4 — nearly flat for this model | Peak delta, `ollama ps` |
| Embedding model (via Ollama) | **274 MB on disk** (`nomic-embed-text`, 768-dim) | Frozen 2026-08-15, ADR-003. Resident footprint under load `TODO(W7)` — it sits on the hit path and bounds μ_hit |
| Python RAG service | `TODO(W6)` | **Built at W5** (`rag/src/rag/` ingests, embeds, retrieves); footprint not yet measured — this is ADR-017's carried re-verification action |
| Redis (cache + corpus vectors + dependency map) | `TODO(W6)` | **Stood up at W5** (`redis-stack-server`, corpus index live); expected tens of MB (ADR-017), not yet measured |
| Go gateway | `TODO(W6)` | not yet built (`gateway/cmd/gateway/main.go` is a no-op stub); expected ~20 MB |
| **Headroom at frozen setting** | ~3.3–4.3 GB remaining within the ~5–6 GB operating ceiling, **LLM-only** — re-verify once Redis/gateway/Python/embedding are also resident | 16 GB total − ~9–10 GB other apps − 1.7 GB LLM |

**μ_gen = 28.2 tokens/sec aggregate** at the frozen setting (`num_ctx=8192`, `NUM_PARALLEL=4`; 4 concurrent realistic-length generations to completion) — the denominator of every load-conversion claim (proposal §3). This is a spike-level measurement; a fuller sustained-load characterization is the W7 in-process probe and the W18–19 campaigns.

**Go/no-go — resolved.** The original frozen model (Gemma 4 E4B/E2B) entered yellow pressure even at `NUM_PARALLEL=1`, `num_ctx=4096` — the escalation branch below fired. Five alternative models were measured; Qwen 3.5 2B was chosen (ADR-021) and holds **green at `NUM_PARALLEL=4`, `num_ctx=8192`** — the largest cell tested — with **1.7 GB resident**, comfortably inside the operating ceiling. The admission pool is therefore sized against a real `NUM_PARALLEL=4` ceiling, not degraded to a single-generation mutex.

## 2. Run-manifest schema

Every run writes `manifest.yaml` next to its raw output. A run is invalid without a complete manifest.

```yaml
run_id: 2026-11-18T14-03-02_cfg4_zipf1.1_np2
git_sha: "abc1234"                 # code state
config_id: 4                        # 1..5, proposal §9.2
mutation: off                       # off|on — source-mutation factor (ADR-023); (config_id, mutation) identifies a run
dataset_version: "v1"
snapshot_sha256: "…"
seeds: { workload: 42, sampler: 7 }
ollama_num_parallel: 2
embedding_model: "<frozen-id>"
llm_tag: "qwen3.5-2b-q4_K_M"        # ADR-021
distinct_queries_K: 2400            # frozen corpus statistic (data-card.md §7)
cache_capacity_ratio: 0.25          # frozen study-wide (ADR-027)
cache_capacity: 600                 # = round(ratio * K); derived, never set independently
mu_hit_probe_rps: 118               # Phase 1 probe; sets the analytic crossover h* (ADR-027)
delta: 0.05                         # false-hit budget in force
zipf_skew: 1.1                      # workload redundancy knob (proposal §9.1)
k6_scenario: { vus: 50, rate_rps: 120, duration: "10m" }
memory_pressure: {
  min_zone: green, yellow_secs: 0, red_secs: 0,   # validity gate — filled post-run; see §4
  free_gb_start: 5.8, free_gb_min: 5.1,            # `vm_stat`-derived free estimate; diagnostic only
  swap_used_mb_start: 0, swap_used_mb_max: 0       # `sysctl vm.swapusage`; diagnostic only
}
hardware: { sut: "m1-16gb", loadgen: "…" }
timestamp: "2026-11-18T14:03:02Z"
notes: ""
```

## 3. Results layout

```
experiments/
  results/
    {run_id}/
      manifest.yaml         # §2 — immutable
      raw/                  # immutable: k6 json, judge outputs, pressure samples
        requests.jsonl      #   per-request evaluation log — schema in interfaces.md §H (ADR-029)
      figures/              # regenerated from raw/ by scripts; never hand-edited
  scripts/                  # workload gen, replay harness, judge, figure generators
```

Rule: `raw/` is write-once; every figure is produced by a script reading `raw/` (+ manifest), so a `make figures` from a clean checkout reproduces the paper's plots.

## 4. Operational metric definitions

Precise counting rules — ambiguity here is what makes "numbers" unreproducible.

**Every metric below is computed from `raw/requests.jsonl`** (`interfaces.md` §H, ADR-029), joined to judge verdicts by `request_id`. Two metrics depend on fields that **cannot be reconstructed after the run**: *decisions changed by provenance* needs `similarity_only_decision`, recorded at the moment the rule ran, and the judge dedupe needs `answer_sha256`, taken when the answer was served.

**Cache outcome (per request).** Exactly one of `TIER1_HIT | TIER2_HIT | MISS | BYPASS` from the `/ask` response (`interfaces.md` §A). `hit = TIER1_HIT ∨ TIER2_HIT`. Hit ratio = hits ÷ total. **`BYPASS` does not occur in the evaluation workload** — the bypass path is a demo-only stub and is not an evaluated component (ADR-018).

**Goodput vs. shed.** Throughput is **goodput**: successfully answered requests per second. `503` shed responses are counted and reported as a separate rate and **never as served load** — otherwise proposal §3's S2 (stability) is satisfiable at S1's (capacity) expense by shedding everything.

**Hit-path latency, decomposed.** Reported as {Tier-1 lookup, embedding call, vector search, overlap check} rather than a single total, since the embedding round-trip sits on the hit path and bounds μ_hit. **Short-circuit hits and cascade-band hits are reported separately** — only the latter pay for retrieval. Also recorded per run: **% of queries entering the band** (the share that paid), reported at every frontier point alongside hit rate.

**End-to-end p95 at matched hit rate (latency fairness).** For each frontier point, also record end-to-end p95 for config 3 and config 4 **at the operating points where their hit rates match**. This is the number that answers whether the provenance rule leaves the *user* better off: a rule that buys reuse but spends more wall-clock per request than the avoided generations save is not an improvement, and the comparison must make that visible rather than letting the avoided generation hide the added retrieval.

**False hit (headline, proposal §9.2).** A hit whose returned answer is judged incorrect vs. the full-pipeline reference. Scored by an **LLM judge that is a different model from the answer generator** (proposal §9.3). The judge prompt is **frozen** (below); ties/uncertain → counted as incorrect (conservative). False-hit rate = false hits ÷ hits.

> **Judging is the hidden cost of this evaluation.** Every judged pair is a local LLM call. **Dedupe by `sha256(query ‖ candidate_answer)` and cache the verdict** — configurations return identical cached answers for the same query constantly, so unique pairs are far fewer than configs × frontier points × hits. Measure the per-config judged-pair count and wall-clock cost at W13 *before* scaling to all five configs.
>
> **Judging runs offline, in batch, with the generator unloaded.** The judge is a different model from the generator and the 16 GB envelope cannot hold both; running them concurrently would force Ollama to swap models and perturb any measurement in flight. Judging happens after all serving runs complete, never during one.

**⚠️ Labelling circularity and the reference-free ablation (C1 validity).** The label above is *"differs from `reference(q) = LLM(retrieve(q), q)`"*. When source overlap is low, the reference is generated from **different context** than the cached answer was, so it diverges — meaning **low overlap partially predicts the label the overlap rule is scored against**. Judge–human agreement does **not** address this: it validates the *judge*, not the *label-generating procedure*.

The ~100 human-verified pairs are therefore labelled under **two schemes**:

| Scheme | Prompt inputs | What it measures |
| :--- | :--- | :--- |
| **Reference-anchored** (frozen template below) | QUESTION + REFERENCE + SOURCE + CANDIDATE | The production metric; judge–human agreement = the noise floor δ must exceed |
| **Reference-free** (ablation) | QUESTION + SOURCE + CANDIDATE, **reference withheld** | Whether serving this answer is correct *on its own terms*, independent of what the pipeline would have produced |

Report **agreement between the two schemes, broken out by overlap bucket** ([0, 0.2), [0.2, 0.6), [0.6, 1.0]). Uniform agreement bounds the circularity empirically and can be shown on one slide. Agreement that degrades at low overlap **quantifies the inflation of C1's measured advantage**, and the headline is discounted accordingly. This ablation is part of the method and is not droppable (proposal §12).

- Frozen judge template (v1):
  ```
  System: You are a strict grader. Decide if the CANDIDATE answers the QUESTION
  as correctly as the REFERENCE, given the SOURCE. Reply exactly: CORRECT | INCORRECT | UNSURE.
  QUESTION: {q}
  REFERENCE: {ref}
  SOURCE: {source_chunks}
  CANDIDATE: {cached_answer}
  ```
  `UNSURE` maps to INCORRECT for the metric. Judge model id + template version recorded in the manifest campaign card.

**Latency.** Two measurements, never conflated:
- *End-to-end* — measured by the off-box generator (k6/Locust), the number quoted for user-facing p50/p95/p99.
- *Internal* — gateway spans (`latency_ms` in `/ask`), for decomposition. **Hit-path latency is reported inclusive of the C1 feature-cascade cost** (proposal §5 C1, §9.1).

**Throughput / saturation.** Sustained served rps before saturation; **saturation** = the load beyond which p95 end-to-end exceeds its bounded-latency SLO or memory pressure leaves green (whichever first). `503`/shed responses (`interfaces.md` §A) are counted as graceful-degradation events, not failures.

**Memory-pressure stability (systems headline, proposal §9.1).** Sample macOS pressure at ≥1 Hz during each run (`memory_pressure` / `sysctl kern.memorystatus_vm_pressure_level`); record seconds in green/yellow/red. **Validity rule (unchanged — the gate is the zone, not a GB number):** a run that enters yellow/red is discarded and repeated at lower load (swapping contaminates latency — proposal §7). **Diagnostic-only fields** (`free_gb_start/min`, `swap_used_mb_start/max` in the manifest's `memory_pressure` block, §2) are sampled alongside the zone at the same ≥1 Hz cadence — they explain *how close to the edge* a passing run was and make a borderline pass distinguishable from one with real headroom, but they never gate validity themselves; only `min_zone` does. CPU/RAM plateau ("flatlining") sampled likewise.

**Load-conversion ratio.** Share of non-bypass load served from cache without a generation permit. Also: tokens/compute saved, embedding calls saved (Tier-1 share).

**Invalidation (proposal §5 C2, RQ3).** Purge policy is **blind dependency-purge** (ADR-010 superseded by ADR-016).
- *Completeness* — fraction of substantive edits after which **no** stale answer survives.
- *Precision* — fraction of purges that were necessary (not over-purging unaffected entries).
- *Over-invalidation on cosmetic edits* — share of purges triggered by answer-preserving edits, from the update-set `change_type` (`data-card.md` §5). Blind purge is expected to over-invalidate here; the number is **reported, not corrected** — recovering it with a predictor gate is future work (proposal §14).
- *Lock contention* — fast-path p99 and reader-stall while edits fire mid-load, across `RWMutex` vs. `atomic.Pointer` (proposal §9.1).

**Decisions changed by provenance** — share of Tier-2 candidates where the containment test flips the similarity-only outcome (proposal §9.2), computed as the disagreement rate between `cache` and `similarity_only_decision` in the §H log. If this is near zero, the signal is thin regardless of where the frontier sits. ⚠️ The counterfactual **must be recorded at serve time** — it cannot be re-derived later against cache state that no longer exists, and without it the pre-registered null of §6 is uninterpretable.

**False-hits-by-cause** (reuse-decision error vs. staleness) tracked separately so the reuse rule is not blamed for invalidation faults (proposal §9.2). ⚠️ **A third cause — a Tier-1 hash collision — has no bucket here and must not arise.** Tier 1 runs no reuse rule, so such a hit would be silently charged to the reuse rule. It is excluded by corpus construction rather than by measurement: gate criterion **G3** (`data-card.md` §7, ADR-028) fails any corpus in which two queries with different answers share a normalized form. *Bypass-classifier accuracy was removed as a metric by ADR-018 and the bypass-misroute cause with it — `BYPASS` does not occur in the evaluation workload, so hit ratio is hits ÷ total.*

## 5. Statistics

- **Threshold tuning is split-disciplined.** The overlap rule exposes three free parameters (τ, θ, cascade band) against the fixed-threshold baseline's one, so a frontier gap could arise from selection alone. All thresholds are tuned on a **validation split partitioned by seed-question cluster** (not by individual pair, which would leak paraphrases across the split) and reported on a **held-out test split**. Both splits are frozen with the dataset.
- **Isolation controls for the frontier.** (i) **Static-cache ablation** — the frontier is also computed against a pre-populated, frozen, write-disabled cache identical across configs, since online caches diverge in contents under different reuse rules and stop being a comparison on identical state. (ii) **Stratified reporting** — the frontier is reported separately **per stratum** (`data-card.md` §2), with the stratum fractions stated. ⚠️ **The `B-within` / `B-cross` split is load-bearing (ADR-028):** if the rule's advantage rests entirely on `B-cross`, then a `product_id` cache key would have achieved the same result at no hit-path cost, and that is what gets reported.
- **Repetitions:** **≥3** per operating point (5 where time permits — timeline W18); report mean + CI.
- **CIs:** bootstrap for latency/throughput; **Wilson score intervals** for rates (hit rate, false-hit rate, staleness). Wilson replaces the binomial power analysis of the previous version: the power calculation implied ~10k judged hits per frontier point, a judging volume the reduced budget cannot fund (ADR-016). Overlapping intervals are reported as *not resolvable at this sample size* rather than argued around.
- **δ finalization (W14):** measure judge error against the **~100-pair** human-verified sample; δ must clearly exceed it. δ ≤ 5% provisional until then (ADR-006).

## 6. Pre-registration

Stated before runs, so the analysis is confirmatory (proposal §9–§10):
- **Headline A (systems):** goodput/latency-vs-concurrency across the Zipf-skew redundancy sweep (**3 levels**), cache-on vs. cache-off, annotated with memory-pressure/CPU-RAM stability and admission-control shedding — cache-on sustains higher load at bounded latency and flatlines within the envelope. The sweep has dynamic range only because capacity is `0.25 × K` (ADR-027); at `C ≥ K` the hit rate is ≈ 1.000 at every skew level and the sweep reports a constant.
- **S1 is a model-fit claim against the binding term, and the crossover is computed rather than observed (ADR-027).** Both service rates are measured directly — μ_gen under sustained load, μ_hit by the 100 %-hit run. The crossover `h* = μ_hit/(μ_gen + μ_hit)` is then **derived from those measurements** and reported alongside the range of `h` the workload actually reaches. With μ_gen ≈ 0.19 req/s, `h*` exceeds 0.99 for any plausible μ_hit, while the best hit rate obtainable in a non-degenerate sweep is ≈ 0.988. **The pre-registered expectation is therefore that `h*` lies outside the reachable range, and that the finding is `the system is generation-bound throughout its operating range`** — reported as a quantitative result, not as a failed measurement. If the Phase 1 μ_hit probe returns ≤ ~16 req/s the crossover *is* reachable and the empirical wording is restored.
- **Headline B (research):** hit-rate / false-hit-rate frontier of the **source-overlap rule** (config 4) vs. the **fixed-threshold τ sweep** (config 3, which is also GPTCache's decision rule) — with Wilson intervals — showing more reuse at equal-or-lower error at δ.
- **Falsifiable claim:** *at δ ≤ 5%, on the held-out test split, the source-overlap rule sustains a higher hit rate than the best fixed threshold* — at equal embedding model and cache capacity, with hit-path p95 reported alongside.
- **Pre-registered null interpretation.** If the frontiers coincide, the reported finding is: *the provenance test changed the reuse decision on only V % of candidate hits; in this corpus, semantically similar queries overwhelmingly ground in identical chunks, so the signal is near-degenerate at this corpus size and diversity — we cannot conclude it is uninformative in general.* This requires **decisions-changed-by-provenance** and the corpus **overlap-variance statistic** (`data-card.md`), both collected regardless of outcome. Registering the null now is what prevents it from reading as an excuse later.
- **μ_hit is measured directly** by a 100 %-hit load test (pre-warmed cache, cached queries only, driven to saturation), so proposal §3's λ_max model can be plotted against measured data rather than asserted. A coarse **μ_hit probe runs earlier, as a Phase 1 exit criterion**, because `h*` and therefore S1's wording depend on it.
- **Out of scope, stated up front:** vCache is compared on **design, not measurement** (ADR-016); no empirical vCache curve appears in Headline B.
