# Project Timeline — Pre-Thesis & Thesis

**Project:** Scalable QA Platform for E-Commerce via RAG-Aware Semantic Caching (see `pre_thesis-Proposal.md`)
**Schedule basis:** part-time, ~20 h/week · start **Mon Jul 13, 2026**
**Phases:** Pre-thesis **Weeks 1–9** (Jul 13 – Sep 13, ~180 h) → Thesis **Weeks 10–22** (Sep 14 – Dec 13, ~260 h) → Buffer into mid-Jan 2027 if the 4th thesis month is available.

---

## Ground Rules

1. **The platform is the thesis; the predictor is the swing.** A working, measured platform earns the grade (proposal §10). Never let predictor work starve platform work.
2. **Drop order under pressure** (from proposal §10): droppable in order — short paper → SSE streaming → semantic routing (RQ4) → request coalescing → (last resort) the learned predictor, falling back to a fixed threshold. **Never droppable:** tiered caching, source-aware invalidation, load-testing evaluation, GPTCache/vCache comparison.
3. **Timebox external things.** Dataset wrangling, GPTCache/vCache integration, and tool setup always overrun — each gets a hard weekly budget below; when it's spent, cut scope, don't extend.
4. **Every week ends with something runnable or written.** The "Done when" column is the weekly exit test — if it's not met by Sunday, next week starts by meeting it, not by starting new work.
5. **Suggested weekly rhythm (20 h):** two weekday evenings (2 × 3 h) for learning/reading/small tasks + two weekend blocks (2 × 7 h) for deep build work.
6. **Advisor checkpoint every 2 weeks** (end of even-numbered weeks), even if just a short status mail: what's done, what's blocked, next two weeks.

---

## Phase 1 — Pre-Thesis (Weeks 1–9 · Jul 13 – Sep 13, 2026)

**Goal:** defend the proposal with a **working end-to-end prototype** (base RAG pipeline + Tier-1 exact + Tier-2 fixed-threshold cache behind the Go gateway) and preliminary numbers.

| Week | Dates | Focus | Key tasks | Learning (do first) | Done when |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | Jul 13–19 | Learning sprint 1 + environment | Install Ollama, pull Gemma 4 E4B + a small embedding model; run first generations and embeddings from Python; `git init` the repo, scaffold `gateway/` (Go), `rag/` (Python), `docs/`, `experiments/` | Python crash course for Java/Go devs (official tutorial §3–§9); what embeddings/vector similarity are; how RAG works end-to-end (retrieve → augment → generate) | A Python script embeds 10 sentences, finds nearest neighbors, and gets a Gemma answer to a question with a pasted-in context chunk |
| **2** | Jul 20–26 | Literature review | Read the 4 core papers: GPTCache, vCache (arXiv:2502.03771), **Apple's Krites** (arXiv:2602.13165 — deep read, it's the nearest competitor), offline/online semantic caching (arXiv:2508.07675); sweep the RAGCache / cache-augmented-generation line (expected examiner question); write 1-page related-work notes each, focused on "how they decide reuse" and "what they can't do" | How to read a systems paper (abstract → figures → method → eval) | 4 related-work summaries committed; a half-page positioning note stating this work's differentiation in your own words |
| **3** | Jul 27–Aug 2 | Datasets — **timebox: this week only** | Download McAuley-lab Amazon Q&A/product data; select a category subset (~500–2,000 products); extract real questions + reference answers; draft policy corpus v0 (5–10 policy documents modelled on real stores) | pandas basics for dataset filtering | A frozen `data/` snapshot: corpus (products + policies) and query workload with reference answers, documented in a README |
| **4** | Aug 3–9 | Base RAG pipeline (Python) I | LlamaIndex ingestion: chunk corpus, embed, index into Redis; retrieval returning top-k chunks **with stable chunk IDs** (design these now — invalidation depends on them) | LlamaIndex docs (ingestion pipeline, vector store integrations); Redis Stack vector search concepts | `rag ask "question"` retrieves relevant chunks from Redis for 10 test queries |
| **5** | Aug 10–16 | Base RAG pipeline (Python) II | Wire retrieval → prompt → Gemma generation; expose as gRPC service (answer + source chunk IDs in response); measure single-request miss latency | gRPC in Python (you know it from Go — just the Python server side) | End-to-end answer with source attribution over gRPC; p50 miss latency recorded |
| **6** | Aug 17–23 | Go gateway v1 | HTTP API (Gin/Fiber); **Tier-1 exact-match cache** (normalized-query hash → answer in Redis); miss path calls Python over gRPC; write-back with provenance tags (chunk IDs); stand up the **dedicated embedding server** (separate from the LLM runtime) | RedisVL / Redis vector search *from Go* (go-redis + RediSearch commands) | Same question twice: first hits Python, second returns from Tier 1 in <10 ms |
| **7** | Aug 24–30 | Tier-2 semantic cache | Query embedding via the embedding server; kNN over cache entries in Redis **directly from Go**; fixed-threshold τ hit/miss decision; write-back to both tiers | Cosine similarity + kNN index behavior (HNSW basics, conceptual only) | A paraphrase of a cached question returns the cached answer; an unrelated question correctly misses |
| **8** | Aug 31–Sep 6 | Preliminary numbers + demo | Generate paraphrase set for ~50 seed questions; measure Tier-1/Tier-2 hit rates at 2–3 τ values; one k6 load curve (cache-on vs cache-off, single skew, generator on a second machine if available); polish the demo flow | k6 basics (scenarios, VUs, thresholds) | One hit-rate table + one throughput/latency plot, committed to `experiments/` |
| **9** | Sep 7–13 | Pre-thesis report + defense | Update proposal with actual preliminary numbers; write the pre-thesis report; build slides; rehearse the demo (record a video fallback); **buffer for overrun from W1–8** | — | Report submitted; demo runs twice in a row without touching code |

### Pre-thesis deliverables (end of Week 9)

- ✅ Revised proposal (already done) + **pre-thesis report** with preliminary results
- ✅ **Working prototype**: Go gateway (Tier 1 + Tier 2 fixed-τ) → Python RAG → Gemma, all provenance-tagged
- ✅ Frozen datasets with README (corpus, query workload, paraphrase set)
- ✅ Related-work summaries (4 papers) + positioning note
- ✅ Preliminary numbers: hit-rate table, one load curve
- ✅ Defense slides + rehearsed demo (with video fallback)

---

## Phase 2 — Thesis (Weeks 10–22 · Sep 14 – Dec 13, 2026)

**Goal:** the research core (invalidation + RAG-aware predictor), the full decoupled evaluation (offline correctness / online scalability), external baselines, and the written thesis.

| Week | Dates | Focus | Key tasks | Learning (do first) | Done when |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **10** | Sep 14–20 | Source-aware invalidation I | Source→entry dependency map in Redis; purge-on-edit flow; controlled update set (~20 spec/policy edits) | — (pure backend work — your home turf) | Editing a policy doc purges exactly its dependent cache entries |
| **11** | Sep 21–27 | Source-aware invalidation II | Completeness/precision measurement harness; handle multi-chunk answers and re-chunking (stable chunk IDs from W4 pay off here) | — | Completeness & precision numbers for the update set, reproducible via one script |
| **12** | Sep 28–Oct 4 | Learning sprint 2 + label pipeline | ML fundamentals: binary classification, train/val/test splits, precision/recall, ROC-AUC, calibration; build the label generator: (query, cached-answer) pairs judged by a **different model** than the generator | scikit-learn getting-started; StatQuest-level intuition for AUC/PR is enough — no deep learning needed | Label pipeline produces reuse-safe/unsafe labels for 200 pairs; you can explain AUC to your advisor |
| **13** | Oct 5–11 | Reuse-safety dataset | Scale label generation; hand-verify ~200 labels, record judge–human agreement — this measured judge error is the **noise floor**; finalize δ against it (provisional δ ≤ 5%, proposal §8); binomial power analysis sizing the judged hits behind each frontier point; freeze train/val/test splits | Rule of three / bootstrap CI / binomial power (one evening) | Frozen labelled dataset + judge-agreement number + a power note fixing δ and per-point sample sizes |
| **14** | Oct 12–18 | Train the predictor | Feature extraction (similarity, **source-chunk overlap**, answer/question-type); first evaluate the **deterministic source-overlap rule** (θ sweep — the signal alone); then train gradient-boosted trees; offline frontier vs fixed-τ sweep and vs the rule | scikit-learn `GradientBoostingClassifier` / feature importance | Offline frontier plot: predictor vs deterministic rule vs fixed-τ, with CIs — signal-vs-learning attribution visible |
| **15** | Oct 19–25 | Integrate predictor into gateway | Serve the predictor to Go (sidecar HTTP/gRPC or exported model — pick the simplest that keeps hit-path p95 low); overlap feature computed **in Go against Redis** (no Python on the hit path); measure decision-time cost | — | Live gateway uses the predictor; hit-path p95 with feature cost reported |
| **16** | Oct 26–Nov 1 | External baselines — **timebox: 2 weeks hard** | GPTCache + vCache on the frozen workload, same embedding model, same δ; adapt the offline replay harness to run all 8 configs (proposal §7.2) | GPTCache/vCache READMEs and configs | Both baselines produce hit/false-hit numbers on the shared workload |
| **17** | Nov 2–8 | Offline correctness evaluation | Run all 8 configurations; frontier plot at the finalized δ (predictor vs deterministic rule vs fixed-τ vs GPTCache vs vCache); gateway hardening in parallel: coalescing (`singleflight`), backpressure; SSE only if time remains (droppable) | — | **Headline result B** figure exists with CIs |
| **18** | Nov 9–15 | Scalability experiments I | Off-box k6 harness; redundancy (Zipf-skew) × load sweep for the headline pair (no-cache vs full system); green-memory-pressure discipline; ~5 repetitions per point | — | **Headline result A** curve family exists |
| **19** | Nov 16–22 | Scalability experiments II | Saturation analysis; **invalidation-under-load** run (edits fire mid-load-test — miss-storm/latency-spike check); fill any missing repetitions; freeze all results | — | All experiment data frozen; every figure regenerable from scripts |
| **20** | Nov 23–29 | Write-up I | Thesis skeleton; background + related work (reuse W2 notes); architecture chapter (reuse proposal §4) | — | 50 % draft: background, related work, design chapters done |
| **21** | Nov 30–Dec 6 | Write-up II | Evaluation chapter around the two headline figures; honest limitations; package the **benchmark artifact** (workload generator + update set + metrics harness, README'd) | — | Full draft to advisor; artifact repo runs from a clean clone |
| **22** | Dec 7–13 | Defense prep + buffer | Revise from advisor feedback; slides; demo rehearsal; **buffer for W10–21 overrun** | — | Submission-ready thesis + rehearsed defense |
| **+** | Dec 14 – mid-Jan | Extended buffer (if month 4 exists) | Overflow for experiments/writing; only if everything above is done: the optional short paper (stretch) | — | — |

### Thesis deliverables (end of Week 22)

Matching proposal §11:

1. ✅ Containerized open-source platform (Go gateway + Python RAG + local LLM)
2. ✅ RAG-aware reuse-safety predictor + judge-validated labelled dataset
3. ✅ Scalability benchmarks: throughput/latency under concurrency, cache-on vs cache-off, across the redundancy sweep (Headline A)
4. ✅ Caching-quality evaluation: predictor vs deterministic source-overlap rule vs fixed-τ vs GPTCache vs vCache at the finalized δ (provisionally ≤ 5%), with CIs (Headline B) + invalidation completeness/precision
5. ✅ Runnable benchmark artifact (workload generator, update set, metrics harness)
6. ✅ **Thesis document + defense**

---

## Learning Path (consolidated)

Everything below is "just enough to build" — no course detours. Total learning load ≈ 35–40 h spread across the schedule.

| Topic | When | Why you need it | Resource |
| :--- | :--- | :--- | :--- |
| Python (for a Java/Go dev) | W1 | The RAG service and all experiment scripts | Official tutorial, docs.python.org — §3–§9 only |
| Embeddings, vector similarity, RAG concept | W1 | The entire mental model of the system | Ollama docs (embeddings API) + any current "RAG from scratch" walkthrough; build the W1 script yourself |
| Reading systems papers | W2 | Related work + defense questions | Read abstract → figures → method → eval; 1-page notes each |
| pandas (filtering/joining) | W3 | Dataset preparation | 10-minutes-to-pandas, pandas.pydata.org |
| LlamaIndex | W4–5 | Ingestion, chunking, retrieval | docs.llamaindex.ai — ingestion pipeline + Redis vector store guide |
| gRPC (Python server side) | W5 | Go↔Python boundary | grpc.io Python basics tutorial |
| Redis vector search from Go | W6–7 | The hit path lives in Go + Redis | redis.io vector search docs + go-redis |
| k6 load testing | W8 | All scalability experiments | grafana.com/docs/k6 — scenarios, VUs, thresholds |
| ML classification basics + scikit-learn | W12 | Contribution 1 | scikit-learn.org getting started; AUC/PR/calibration intuition |
| Basic experiment statistics | W13 | Honest CIs at the false-hit budget δ; sizing judged hits per frontier point | Rule of three, bootstrap CIs, binomial power — one evening of reading |

**Deliberately not learning:** deep learning, model training/fine-tuning, PyTorch, LangChain, Kubernetes. The LLM and embedding models are consumed black boxes (proposal §3).

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
| :--- | :--- | :--- | :--- |
| Dataset wrangling overruns (W3) | High | Delays everything downstream | Hard 1-week timebox; a smaller clean subset beats a bigger messy one; freeze and move on |
| vCache/GPTCache integration cost (W16) | High | Eats evaluation weeks | 2-week hard timebox; if vCache won't integrate, reimplement its per-entry-threshold *policy* inside the replay harness and state so honestly |
| M1 memory pressure invalidates runs (W18–19) | Medium | Re-running load sweeps | Green-pressure discipline from proposal §5.1; drop concurrent-run count before dropping experiments; schedule sweeps early in the week so reruns fit |
| Part-time schedule slip | Medium | Compounding delay | "Done when" gates + biweekly advisor checkpoints; apply drop order at the *first* slipped fortnight, not the last |
| Predictor doesn't beat baselines | Medium | Weakens headline B | Explicitly acceptable per proposal (reportable negative result); platform + invalidation + evaluation still complete the thesis |
| No second machine for load generation | Medium | Contaminated latency numbers | Borrow any laptop for W8/W18–19 only; else measure and report generator interference (proposal §5.1) |
| Judge labels too noisy (W13) | Low–Med | Predictor ceiling unclear | ~200 human-verified labels quantify the noise; report agreement and interpret results against it |

---

*Cross-references: proposal §9 (indicative phases), §10 (scope guardrails & drop order), §11 (deliverables); `defense_demo.md` (what to show the council — the five-step demo script and debug-UI spec rehearsed in W9 and W22). Dates assume a Mon–Sun week; the advisor checkpoint lands at the end of even weeks.*
