# Project Timeline — Thesis Phase · ⚠️ RETIRED 2026-09-21

> ## This file no longer plans the work. **`docs/super-plan.md` does.**
>
> It was written before the code existed, and the codebase has since run ahead of it in some
> places and stayed empty in others. Three of its instructions were actively wrong by the time it
> was retired: its W12 row said to populate `similarity_only_decision` (**retired by ADR-036**),
> its W8 detail described the Amazon-Reviews-2023 × AmazonQA join and *"measure the join rate
> first"* (**replaced by ADR-039**), and its Phase 5 scheduled `admission/` and `telemetry/` as
> future work when both were already built and tested. **Do not act on anything below.**
>
> **Two sections here are still live and have no other home**, which is why the file is kept
> rather than deleted: the **Risk Register** and the **Learning Path**. Read those; treat the
> Phase Plan and Working Detail as the historical record of how the schedule was planned before
> there was code to plan against.
>
> `.claude/hooks/lib.sh` reads `super-plan.md` first and falls back here only for a phase the
> super plan does not carry.

**Project:** Scalable QA Platform for E-Commerce via Provenance-Aware Semantic Caching (`Final_Proposal.md`)
**Basis:** part-time alongside full-time employment — 2–3 days/week ≈ **15 h**
**Revised:** 2026-09-02 — replanned by phase and exit criterion rather than by date · **Retired 2026-09-21** into `super-plan.md`

> **Pre-thesis is closed.** The runway shipped a working end-to-end prototype and the submitted report. Everything below is thesis-phase work. Remaining budget **≈ 225 h** to completion in **December 2026**.

---

## Ground Rules

1. **The platform is the thesis, the containment rule is the swing.** A working, measured platform earns the grade. Never let research work starve platform work.
2. **Drop order under pressure** — the single authoritative list is `Final_Proposal.md` §12. Do not restate it here or anywhere else, so it cannot drift.
3. **Two corpora, deliberately.** `dev-v0` is throwaway and **not citable in any result**. `v1` is the frozen experimental corpus and the only one a measurement may use (ADR-020).
4. **Timebox external things.** Dataset wrangling and tool setup always overrun. When the box is spent, cut scope rather than extend.
5. **Every phase ends with something runnable.** The exit criterion is a binary test, not a judgement. A phase is not finished because its time is spent.
6. **Advisor checkpoint every two weeks**, even if only a short status mail.

---

## Phase Plan — superseded

⚠️ **Superseded by `super-plan.md`, which re-derived these boundaries from the critical path.** Kept as the record of the pre-code plan. The exit criterion is the gate. Phases are sequential and a phase does not open until its predecessor's criterion is met.

| Phase | Focus | Exit criterion |
| :--- | :--- | :--- |
| **0 — Runway** ✅ | Working pipeline and the pre-thesis report | **Met.** Envelope frozen from measurement (ADR-017, ADR-021), `rag/` and gateway running, `dev-v0` ingested, report submitted |
| **1 — Experimental apparatus** | Freeze `v1`. Derive capacity. Probe μ_hit. Stand up off-box load | `v1` frozen + hashed after **all five gate criteria** pass (G1…G5 — `data-card.md` §7; it was three, ADR-032 added G4 and ADR-038 added G5) · `K` recorded and capacity derived · **μ_hit probe recorded** · k6 drives the gateway from a second machine |
| **2 — Invalidation and literature** | Dependency map, epoch guard, purge. Clear the remaining unverified citations | Editing a policy purges exactly its dependents from **both** tiers · an in-flight generation during an edit is **discarded, not written back** · completeness and precision reproducible from one script · every ⬜ row in proposal §10.1 cleared or rewritten |
| **3 — The rule and the judged set** | Containment rule, cascade, judge harness, labelling ablation | Live gateway decides reuse by the rule, hit-path p95 reported **inclusive** of overlap cost · both agreement numbers recorded · δ finalised |
| **4 — Correctness evaluation** | Five configurations at `mutation: off`, θ/τ sweeps, isolation controls | **Headline B** exists with its isolation controls, reported on the held-out split with Wilson intervals |
| **5 — Systems hardening** | Permit pool, bounded queue, shedding, coalescing, telemetry | Overload **sheds instead of swapping**, pressure stays green at full admission · a thundering herd of N identical queries triggers exactly one backend call |
| **6 — Scalability campaigns** | Redundancy × load sweeps, μ_hit run, invalidation under load | **Headline A** curve family exists, measured λ_max plotted against the model · all results frozen, every figure regenerable from scripts |
| **7 — Write-up and defence** | Thesis document, artefact packaging, rehearsal | Submission-ready thesis and a rehearsed defence |

**Deliverables** are listed once, in `Final_Proposal.md` §13. They are not restated here.

---

## Working Detail — superseded, and partly WRONG

⚠️ **Do not act on this section.** See the retirement note at the top of the file for the three instructions that were wrong when it was retired.

⚠️ **Week numbers are now vestigial.** They were retained as the handle `/week` and the session
banner read; the harness stopped reading them on **2026-09-21** (`Pre-thesis_Sweeping.md` #4) and
now reads the **phase** table above via `.claude/hooks/lib.sh:phase_row()`. `/week` no longer
exists — `/phase` replaces it. The week columns below are kept only because this file's detail has
not yet been carried into `docs/super-plan.md`, which owns execution once #3 is filled. **Nothing
reads them, and nothing should start.**

### Phase 1 — Experimental apparatus

| Week | Focus | Key tasks | Done when |
| :--- | :--- | :--- | :--- |
| **8** | **Freeze the corpus** | Build `v1` to the structural requirements of **ADR-024** and **ADR-028**. Run the gate — procedure and criteria are in `data-card.md` §7, not restated here. Record `K` and derive `cache_capacity = round(0.25 × K)` (**ADR-027**). Run a coarse **μ_hit probe** on the existing gateway: pre-warm, replay cached queries, drive to saturation. Stand up the off-box k6 harness | `v1` frozen + hashed after **G1…G5 all pass** · `K` and derived capacity recorded in `data-card.md` · **μ_hit recorded** — it decides whether S1's wording stands (ADR-027) · k6 drives the gateway from a second machine |

> **Building `v1` is four jobs, not a download** (`data-card.md` §1–§4). Each has already been
> flagged as a risk there; they are listed here because any one of them can slip the freeze:
>
> 1. **Catalog** — ~150 products from McAuley-lab `Amazon-Reviews-2023`. ⚠️ Its dataset card
>    **states no license**, so redistribution is unresolved: default to shipping a
>    **download + build script and a hash manifest**, not the raw data (ADR-013). `data/v1/` stays
>    gitignored until the terms are verified.
> 2. **Product questions** — mined from **AmazonQA**. ⚠️ **Measure the join rate first.** AmazonQA
>    is the 2016 release keyed on `asin`; the catalog is keyed on `parent_asin`. Coverage across a
>    near-decade gap is unverified. If too few questions map, either select products *from* the
>    QA-covered set or author more of the workload — and record which was done.
> 3. **Policy questions — authored in-house, because they do not exist.** AmazonQA is product Q&A
>    and contains **no policy questions at all**. Return windows, warranty terms, restocking fees:
>    all written by hand. This is where **stratum B mostly lives**, so it is not a small side job.
> 4. **Rewrite every query to be self-contained.** Real AmazonQA questions are asked on a product
>    page and are elliptical — *"does this fit?"*, *"how long is the warranty?"* — while `/ask`
>    carries no product context (`interfaces.md` §A). Rewriting is required, and it is **reported
>    as a limitation**, never presented as raw real traffic.
>
> Tag each query with its **stratum** (A / B-within / B-cross / C / D) *and* its paraphrase type.
> Neither can be retrofitted once the snapshot is hashed.

> ⚠️ **μ_hit is the one that can change the report.** `Final_Proposal.md` §3 and the submitted report both state that the load-conversion crossover is computed rather than observed, on the basis that μ_hit is far above ~16 req/s. If the probe returns **≤ ~16 req/s**, that reasoning inverts and S1's empirical wording is restored (ADR-027). Measure it before writing anything further that depends on it.

### Phase 2 — Invalidation and literature

| Week | Focus | Key tasks | Done when |
| :--- | :--- | :--- | :--- |
| **9** | Dependency map | `dep:*` under `noeviction` in its own region, in-process index, purge through a single writer goroutine hitting **both** tiers via `t1_key`, **epoch-guarded write-back**. Stand up the **per-request evaluation log** (`interfaces.md` §H, ADR-029) — fields populate as features land, and it blocks every later measurement | Editing a policy purges exactly its dependents · an in-flight generation during an edit is discarded · `raw/requests.jsonl` written and parseable |

> ⚠️ **The evaluation log is how every accuracy number gets computed — and it currently cannot
> feed the judge.** `interfaces.md` §H records one JSONL row per request with the cache outcome,
> `similarity`, `source_overlap`, `entered_band`, `similarity_only_decision`, both chunk-ID lists
> and the stage timings. Four metrics in `experiment-protocol.md` §4 are **not computable without
> it**, and two of its fields (`similarity_only_decision`, `answer_sha256`) **cannot be
> reconstructed after the run**.
>
> **The gap:** §H stores `answer_sha256`, never the answer **text**, and `raw/` is specified as
> "k6 json, judge outputs, pressure samples" — nothing durably holds the served answers. But §4
> requires judging to run **offline, in batch, with the generator unloaded**, and a judge needs
> the candidate answer text. Recovering it from the cache afterwards is unsound: the cache is
> bounded at `round(0.25 × K)` with LRU eviction, so any answer evicted mid-run is gone — and
> `raw/` is write-once, so this cannot be patched after the fact.
>
> **Likely fix, cheap:** a content-addressed `raw/answers/{answer_sha256}.txt`. It dedupes for
> free — identical answers across configurations collapse to one file — and it is keyed by a field
> §H already carries. **Needs an ADR** before W9, since §H and `experiment-protocol.md` §3 are
> both frozen.

| **10** | Literature verification | Clear the remaining ⬜ rows in proposal §10.1. **Partly discharged already** — the block was pulled forward and produced ADR-026, which found two systems occupying C1 and narrowed the claim. What remains: FreshCache and the serving-scheduler row, plus reading GroundedCache and FinCacheServe in full, since they now carry the positioning | Every ⬜ cleared or the claim rewritten. A characterisation that fails is **corrected, not defended** |
| **11** | Guard and update set | Copy-on-write guard shipped. `RWMutex` comparison as a synthetic microbenchmark sweeping edit rate. ~20-edit update set, balanced `substantive` / `cosmetic`. Completeness and precision harness against a **swept** TTL baseline — cell `(3, on)` of ADR-023 | Completeness and precision reproducible from one script · microbenchmark curve exists |

### Phase 3 — The rule and the judged set

| Week | Focus | Key tasks | Done when |
| :--- | :--- | :--- | :--- |
| **12** | Containment rule | Containment computed **in Go against Redis** as set intersection over chunk IDs. The θ ∧ τ decision and the cascade band. Populate `similarity_only_decision` in the §H log — the counterfactual cannot be reconstructed later, and without it the pre-registered null is uninterpretable | Live gateway decides reuse by the rule · hit-path p95 reported inclusive of overlap cost · % entering the band recorded per request |
| **13** | Judge harness | Frozen prompt, judge model **different from the generator**, offline batch with the generator unloaded. Dedupe verdicts by `answer_sha256`. Measure per-config judged-pair count and wall-clock **before** scaling to five configurations | Judging cost measured and affordable at five configurations · **judge model id and prompt version frozen and recorded** before any frontier is computed |
| **14** | Labelling ablation | Hand-verify ~100 pairs under **both** schemes (ADR-019). Record judge-to-human agreement and reference-anchored-against-reference-free agreement **by containment bucket**. Finalise δ | Both agreement numbers recorded · δ finalised against the measured noise floor · circularity bounded or quantified |

### Phase 4 — Correctness evaluation

| Week | Focus | Key tasks | Done when |
| :--- | :--- | :--- | :--- |
| **15** | Headline B | All five configurations at `mutation: off`. Sweep τ and θ **on the validation split**, report on **held-out test**. Wilson intervals. Hit-path p95 and band-entry share per point. End-to-end p95 at matched hit rate. Static-cache ablation. **Frontier reported per stratum, including the B-within against B-cross split** (ADR-028) | **Headline B** exists with its isolation controls · the B-within result is reported, since it is what answers the product-identifier objection |

> **Tuning theme — W15 is where the reuse formula gets properly exercised, not just measured.**
> The sweep in the row above is currently one line; the intent is a thorough pass. Run many cases
> and many *kinds* of paraphrase over `v1`, watch where the rule holds and where it breaks, and
> use that to improve the Tier-2 decision — the goal being the highest hit rate that keeps
> false hits inside δ. Adding something at Tier 1 is in scope to *consider* here too.
>
> Three constraints, so this stays evaluation and does not become tuning-to-taste:
>
> 1. **Tune on the validation split, report on held-out test** (`experiment-protocol.md` §5).
>    Non-droppable (proposal §12). The deliverable is a **frontier**, not a tuned point.
> 2. **Tier 1 may be measured, not changed.** `cache/` must never make a reuse decision
>    (`architecture-guardrails.md`), and a more aggressive `Normalize` would also threaten G3's
>    zero-collision invariant. Any Tier-1 idea enters as a reported ablation; the shipped function
>    stays ADR-015's.
> 3. **Pin the sweep before running it.** `Final_Proposal.md` §9.4 already books this debt in its
>    own words — *"θ's range is not stated anywhere"*, τ's granularity unstated, the cascade-band
>    bounds unspecified, and *"the best fixed threshold"* with no written selection objective —
>    and names `experiment-protocol.md` as where they are fixed, *"before the sweep runs"*.
>    Note the band needs its **quantity** defined before any bound means anything: `entered_band`
>    is a boolean everywhere today.
>
> **Deferred by decision (2026-09-05).** Scoped only if the topic is approved at the advisor
> meeting; there is no point specifying a sweep for a study that may be rescoped. See
> `worklog/W08.md` for the findings behind these three constraints.

### Phase 5 — Systems hardening

| Week | Focus | Key tasks | Done when |
| :--- | :--- | :--- | :--- |
| **16** | Admission control | Permit semaphore sized from ADR-017's frozen envelope. Bounded queue, then `503 busy, retry`. Memory-pressure sampling at ≥1 Hz. Goodput-against-shed accounting | Overload sheds instead of swapping · pressure stays green at full admission |
| **17** | Coalescing and telemetry | Request coalescing (`singleflight`). Telemetry export. Hit-path latency decomposition into {lookup, embed, search, overlap} | A thundering herd of N identical queries triggers exactly one backend call · decomposition present in the §H log |

### Phase 6 — Scalability campaigns

| Week | Focus | Key tasks | Done when |
| :--- | :--- | :--- | :--- |
| **18** | Load sweeps | Redundancy (3 Zipf skews) × load, cache-on against cache-off. **100 %-hit run for μ_hit** under sustained load. ≥3 repetitions per point. Green-pressure discipline | Curves exist at every point · **hit-rate spread across the three skews is non-zero** — if it is flat, capacity was mis-derived (ADR-027) |
| **19** | Saturation and mutation | Saturation analysis. Invalidation-under-load run. Fill missing repetitions. **Freeze all results** | **Headline A** exists · measured λ_max plotted against the model, with `h*` computed from both measured service rates · every figure regenerable from `raw/` |

### Phase 7 — Write-up and defence

| Week | Focus | Key tasks | Done when |
| :--- | :--- | :--- | :--- |
| **20** | Skeleton and background | Chapter skeleton. Background and related work, reusing the verification block's notes. Architecture chapter | 50 % draft |
| **21** | Evaluation chapter | Built around the two headline figures. Honest limitations, including vCache and GroundedCache compared on design rather than measured. Package the benchmark artefact | Full draft to advisor |
| **22** | Revision and rehearsal | Revise from advisor feedback. Slides. Rehearse the full five-step demo. **Buffer** | Submission-ready thesis and rehearsed defence |

---

## Learning Path — still live

Mostly discharged in the runway. What remains:

| Topic | Phase | Why |
| :--- | :--- | :--- |
| k6 load testing | 1 | Every scalability experiment |
| Wilson intervals and bootstrap CIs | 3 | Honest error bars on rates |

**Deliberately not learning:** deep learning, model training, scikit-learn, PyTorch, LangChain, Kubernetes. After ADR-016 no ML expertise is on the critical path.

---

## Risk Register — still live

| Risk | Likelihood | Impact | Mitigation |
| :--- | :---: | :---: | :--- |
| ~~Envelope does not fit at `NUM_PARALLEL ≥ 2`~~ **— materialised and resolved** | — | — | The runway spike found the original model entered yellow pressure at the lightest configuration. Five alternatives were measured and Qwen 3.5 2B frozen (ADR-021), holding green at the largest cell tested |
| ~~A §10 novelty claim fails verification~~ **— materialised and resolved** | — | — | The block was pulled forward and **did** fail: two 2026 systems occupy C1's mechanism. The claim was narrowed rather than defended (ADR-026). The platform and the systems pillar are untouched |
| **Corpus cannot produce B-within pairs** | Medium | **High** | Gate criterion G2 fails the corpus rather than the rule. If the phenomenon is genuinely thin, it is reported as a corpus finding bounding C1's applicability |
| **μ_hit falls below ~16 req/s** | Low | Medium | S1's wording inverts back to the empirical form. Cheap to detect — it is a Phase 1 exit criterion, deliberately placed before anything depends on it |
| **Redundancy sweep comes out flat** | Low | High | Capacity is derived as a ratio of `K` rather than set absolutely (ADR-027). Detected at Phase 6 by a near-zero hit-rate spread, which would mean `K` was miscounted |
| Labelling circularity inflates C1 | Medium | High | Reference-free ablation on the same ~100 pairs (ADR-019), agreement by containment bucket, headline discounted if it degrades at low containment |
| Judging wall-clock exceeds Phase 3 | Medium | High | Dedupe by `answer_sha256`, judge hits only, cap frontier points, measure per-config cost **before** scaling |
| Part-time slip | High | Medium | Exit criteria gate progression, not the calendar. Phase 7's buffer week is the only slack — spend it on overrun, not new scope |
| No second machine for load generation | Medium | Medium | Needed from Phase 1. Otherwise measure and report generator interference (ADR-012) |

---

*Cross-references: `Final_Proposal.md` §11 (phases), §12 (drop order — authoritative), §13 (deliverables — authoritative) · `data-card.md` §7 (corpus gate — authoritative) · `decisions.md` ADR-020, ADR-024, **ADR-026**, **ADR-027**, **ADR-028**, **ADR-029** · `interfaces.md` §H (evaluation log).*
