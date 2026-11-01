# Metric definitions and counting rules

**Status:** `counting-v1` · **Dated:** 2026-11-01 · **Owner:** thesis author · **Item:** 5.1 (the metric-definition
part of P1, `decisions.md`)
**Companion to:** `interfaces.md` §H (the record) and §I (the manifest and the judge's output),
`Final_Proposal.md` §9.1–§9.2 (the metric rows), `preregistration.md`, ADR-022.

**What this is.** `Final_Proposal.md` §9.1 says the counting rules for every metric must exist before Phase 5 produces
its first artefact. This file is that record. It has one entry for each of the 17 metric rows of §9.1 (6 rows, M01–M06)
and §9.2 (11 rows, M07–M17), and three more: μ_gen (M18), μ_hit (M19) and the miss-path error rate (M20). It was
written before the judge's first verdict.

**Version.** These rules are `counting-v1`. A run, a table or a figure names the version it used. A change after any
number was counted with these rules is `counting-v2`, with its own date. This version is never edited to fit a result.

**How to read an entry.** Each entry has the same six parts.
- **Claim:** what the metric exists to settle. A metric that proves nothing is removed, not reported (§9.1).
- **Formula:** over §H fields, the manifest, or the judge's `records.jsonl` (§I).
- **Filter:** which records count: the cell `(config_id, mutation, support_gate, mixed_lane)`, the stratum, the split.
- **Denominator:** what a rate is divided by.
- **Interval:** Wilson for a rate; the repetitions themselves for anything else.
- **Cells:** which cells of the configuration × mutation grid report it, and which item builds its data if that
  does not exist yet.

---

## Shared rules

**R1 — A run is one cell.** The cell is `manifest.arms`, which `make run-manifest` reads from the records (ADR-010),
never from the environment. Cells are never pooled. A rule that reads `support_gate` also filters
`config_id ∈ {4, 5}` (§H). Only a run with `manifest.admissibility.admissible: true` counts. That field holds run
rules 6, 10 and 12 and invariant I9 (§H), decided from `raw/` and the gateway's log (§I).

**R2 — Splits.** Thresholds are swept and tuned on `validation`. Rates are reported on `test`. Every printed number
names its split. A rate whose threshold was chosen on the split it reports is not a result.

**R3 — The served decision and the counterfactual (ADR-019).** `cache` and `refusal_cause` are the served decision.
`source_overlap` and `overlap_decision` are a counterfactual: what the containment rule would have decided. θ is not
part of the served rule and is not swept. No metric explains a served outcome by `source_overlap ≥ θ`. One metric,
M11, uses that test as a filter on records already served, because §H's denominator does.

**R4 — Served, hit, miss.**
- *Served* means `answer_sha256 != ""`. A record with `""` (SHED, ABANDONED, GENERATION_FAILED, or a Tier-1 lookup
  error) is counted and reported, never judged, and never in a hit-rate denominator.
- A *hit* is `cache ∈ {TIER1_HIT, TIER2_HIT}`. A *miss* is `cache == MISS`.
- Counting is per record, so per request. A run that replays each query once is per query by construction. A Zipf run
  weights a popular wrong answer by its popularity, and says so.

**R5 — Verdicts.** The judge gives each record the verdict of its verdict key (§H, v0.28): `CORRECT`, `INCORRECT` or
`UNPARSED`.
- `UNPARSED` is a broken instrument, not a label. It leaves both the numerator and the denominator, and is counted
  beside.
- If more than **2 %** of a run's verdict keys are `UNPARSED`, that run's verdict-based rates are not reported
  (`summary.json`, `rates_reportable`, §I).
- A metric that reads a verdict reads it from `judge/records.jsonl`. Only M08, M12, M13, M16 and M20 do.

**R6 — `answerable: false` queries count like any other.** The rubric makes a "don't know" `CORRECT` for them and an
invented answer `INCORRECT`. Every verdict-based table has their count as its own row.

**R7 — The error layers.** Each `INCORRECT` record gets one layer, first match wins from 1 to 4. The layers are
reported apart, as counts and as rates, and never added into one number.

| # | Layer | Rule over stored fields |
| :---: | :--- | :--- |
| 1 | `retrieval` | `retrieved_chunk_ids` is not null, and a gold `product-` document has no chunk in it, or a gold `policy-` document is not the document of its first `policy-` chunk (none counts as not). Stored as `retrieval_miss` on every record that has a retrieval, `CORRECT` ones too |
| 2 | `generation` | `cache == MISS` |
| 3 | `inherited` | a hit, and the MISS record that wrote its entry has verdict `INCORRECT` |
| 4 | `reuse` | a hit, and that MISS record has verdict `CORRECT` |
| — | `undecided` | a hit whose entry's MISS has verdict `UNPARSED`, or has no MISS record in the run. Counted beside the layers, in none of them |
| 5 | `reference` | not assigned by the harness. See below |

- *The entry's MISS* is the MISS record with the same `entry_id` as the hit: the leader, when coalesced followers
  share the entry. On a hit, `entry_id` names the served entry (§H). I9 makes sure the MISS is in the run.
- A TIER1_HIT has no retrieval, so layer 1 never fires on it. Its layer comes from its entry's MISS, like a
  TIER2_HIT's. This holds for a promoted key too.
- Layer 1 reads only chunk IDs. The first `policy-` chunk is the POLICY lane's namespace document, so no lane rule
  is copied into the harness.
- *Layer 5, `reference`.* A reference is one text of the temperature-0 reference writer (ADR-023), so it can be wrong. Item 5.2's
  human check marks a sampled pair whose reference is wrong. The count is reported beside the four layers, with its
  own Wilson interval over that sample. It never moves a record between layers 1–4. Its sheet and fields are 5.2's.

**R8 — Intervals and percentiles.**
- A rate `k / n` has a Wilson score interval, 95 %, `z = 1.96`:
  `( p + z²/2n ± z · √( p(1−p)/n + z²/4n² ) ) / ( 1 + z²/n )`, with `p = k / n`. For `n = 0` there is no rate and no
  interval: the cell prints `n = 0`.
- Wilson treats requests as independent trials. They are not quite (a cache fills as a run goes), so the interval
  describes this sample, not the spread of repeated runs.
- A percentile is nearest-rank: the value at rank `⌈q·n⌉` of the sorted values.
- A number that is not a rate (goodput, a latency, a service rate) gets no parametric interval. Every repetition is
  shown, with its minimum and maximum.

---

## Index

| # | Metric | Proposal row | Numbers come from | Verdict | Data built by |
| :---: | :--- | :--- | :--- | :---: | :--- |
| M01 | Goodput and latency percentiles | §9.1 | `raw/`, k6 | no | 7.1 |
| M02 | Saturation point and load-conversion ratio | §9.1 | `raw/`, k6, M18, M19 | no | 7.1, 7.5 |
| M03 | Memory-pressure stability | §9.1 | pressure sampler | no | 7.1 |
| M04 | CPU / RAM flatlining | §9.1 | process sampler | no | 7.1 |
| M05 | Admission-control behaviour | §9.1 | `raw/`, gateway start log | no | 7.5 |
| M06 | Invalidation under load | §9.1 | `raw/`, edit times | no | 7.4 |
| M07 | Cache hit ratio | §9.2 | `raw/` | no | 6.2 |
| M08 | False-hit rate (headline) | §9.2 | `judge/records.jsonl` | **yes** | 6.2 |
| M09 | Hit-path p95 | §9.2 | `raw/` | no | 6.2 |
| M10 | % reaching the provenance check | §9.2 | `raw/` | no | now, config 4 |
| M11 | Support-gate refusal rate, by arm | §9.2 | `raw/`, manifest | no | now, config 4 |
| M12 | Residual false-hit rate (RQ2a) | §9.2 | `judge/records.jsonl` | **yes** | 6.4 |
| M13 | Staleness rate | §9.2 | `judge/records.jsonl`, edit log | **yes** | 6.5 |
| M14 | Invalidation completeness and precision | §9.2 | update-set check | no | 4.4 (functional), 6.5 |
| M15 | Decisions changed by provenance | §9.2 | two runs' `raw/` | no | 6.0, 6.3 |
| M16 | False hits by cause | §9.2 | `judge/records.jsonl`, edit log | **yes** | 6.5 |
| M17 | Compute and embedding calls saved | §9.2 | `raw/` | no | 6.2 |
| M18 | μ_gen | §9.1 (text) | `raw/`, Ollama | no | 7.5 |
| M19 | μ_hit | §9.1 (text) | `raw/`, k6 | no | 7.2 |
| M20 | Miss-path error rate | — | `judge/records.jsonl` | **yes** | now, config 4 |

---

## Headline A — scalability (§9.1)

### M01 — Goodput and latency percentiles

- **Claim:** S1 capacity (RQ1). Cache-on sustains a higher goodput than cache-off at bounded latency. It is disproved
  if it does not.
- **Formula:** goodput = (served records with `ts` inside the window) ÷ (window seconds). The window is the load
  driver's scenario, from its first request to its last response. No warm-up is cut unless the item that runs the
  sweep pre-registers the cut. A shed (`shed == true`) is never served load. Latency p50, p95 and p99 are over
  `t_total_ms` of the served records. The client's end-to-end time (k6) is reported beside it and named, never mixed
  with it.
- **Filter:** `mutation: off`. One cell per curve: configurations 1, 2 and 5 (the ladder, item 7.1). Each of the
  three Zipf skews and each offered rate is its own point. No stratum split.
- **Denominator:** window seconds for goodput. The served records of the point for a percentile.
- **Interval:** none. At least 3 repetitions per point, each shown, with the minimum and maximum. Co-hosted, so a p95
  is printed only with k6's concurrent CPU from the same run, and a figure is a bound, never a ceiling (ADR-001).
- **Cells:** 1, 2, 5 at `mutation: off`. **Data:** item 7.1, not built.

### M02 — Saturation point and load-conversion ratio

- **Claim:** S1 model fit. Sustained load tracks the binding term of `λ_max = min( μ_gen / (1 − h), μ_hit / h )`
  across the redundancy sweep. The crossover `h*` is computed from M18 and M19, never located empirically. If it lies
  outside the hit rates the workload reaches, that is the finding.
- **Formula:**
  - Load-conversion ratio = `1 − G / S`. `S` is the served records. `G` is the records with
    `cache == MISS ∧ t_generate_ms != null` (the leaders that generated, §H `t_generate_ms` reading rule i). Every hit
    and every coalesced follower counts as converted: none of them generated.
  - Saturation point = the lowest offered rate in the sweep at which the median repetition's goodput (M01) is below
    0.95 × the offered rate. The 0.95 is a counting choice made here, 2026-11-01, before any Phase 7 run.
  - `h*` = the `h` at which `μ_gen / (1 − h) = μ_hit / h`, computed from M18 and M19 at the same sweep point.
- **Filter:** as M01. The tier mix is a function of redundancy, so `h` and `μ_hit` are taken per sweep point, never
  once from an average (item 7.2).
- **Denominator:** `S` for the ratio. Offered requests for the saturation test.
- **Interval:** the ratio has a Wilson interval (`k = S − G`, `n = S`). The saturation point has none: the
  repetitions are shown.
- **Cells:** 1, 2, 5 at `mutation: off`. **Data:** items 7.1 and 7.5, not built.

### M03 — Memory-pressure stability

- **Claim:** S2 stability, and the validity gate itself. A run that leaves green is discarded, not annotated.
- **Formula:** green share = (samples with `kern.memorystatus_vm_pressure_level == 1`) ÷ (all samples), sampled at
  1 Hz or faster for the whole run. Swap delta = `vm.swapusage` used at the end minus at the start.
- **Filter:** every run whose number reaches the thesis, any cell.
- **Denominator:** samples.
- **Interval:** none. It is a gate. A citable run has green share 1.0 and swap delta 0. Any other value voids the
  run, and the run is repeated under a new `run_id`. A functional run records the same two numbers and is not citable
  (CLAUDE.md).
- **Cells:** all. **Data:** the sampler of item 7.1 (`loadgen_footprint.py` is the model), not part of §H.

### M04 — CPU and RAM flatlining

- **Claim:** S2. Resource use plateaus under overload (governed) instead of spiking into swap (collapse). It is the
  qualitative companion to M05; without it "stable" rests on one number.
- **Formula:** per process (gateway, `rag.server`, the Ollama runners, the load generator), CPU % and resident memory
  at 1 Hz. The saturated window is cut into three equal thirds. The table gives each third's median beside the whole
  window's median.
- **Filter:** the saturated points of M01, governed and ungoverned arms.
- **Denominator:** none. This entry is a figure and a table.
- **Interval:** none. No threshold for "flat" is set here. It is read from the figure. The only binary reading is M03's:
  swap growth is collapse.
- **Cells:** 1, 2, 5 at `mutation: off`. **Data:** item 7.1, not built.

### M05 — Admission-control behaviour

- **Claim:** S2, and the test of the admission pool's size. Goodput falling or p99 exploding at saturation means the
  pool is mis-sized or shedding is not engaging. Sustained yellow voids the run (M03), it does not indict the pool
  (ADR-003).
- **Formula:**
  - Shed rate = records with `shed == true` ÷ all records of the point.
  - Queue depth = the distribution of `permit_queue_depth` over records with `t_generate_ms != null` or `shed == true`
    (every attempt held a permit, §H reading rule ii). Report the maximum and the p95. `t_permit_wait_ms != null`
    is not "a permit was held" and is not used for the selection.
  - Permit wait = the distribution of `t_permit_wait_ms` over the records where it is not null, named as that.
- **Filter:** the governed arm (one permit, the queue budget `q`) against the ungoverned arm (more permits than the
  served slot). The two arms' permits and `q` are read from the gateway's start log
  (`gateway: admission permits=… queue_budget=…`), kept beside the run, because `manifest.yaml` v1 has no field for
  them.
- **Denominator:** all records of the point, for the shed rate.
- **Interval:** the shed rate has a Wilson interval. Queue depth has none: the repetitions are shown.
- **Cells:** 5 (and 1, 2 as the ladder needs), `mutation: off`. **Data:** item 7.5, not built.

### M06 — Invalidation under load

- **Claim:** S4, safety under mutation (RQ3). The read fast path does not stall behind an invalidation.
- **Formula:** an *edit window* runs from the start of a `POST /invalidate` to its reply (§E). Fast-path p99 =
  the p99 of `t_total_ms` over hit records whose `ts` falls inside an edit window. Baseline p99 = the same over hit
  records in windows of equal length with no edit. Reader stall = the baseline p99 subtracted from the edit-window
  p99, and the largest `t_total_ms` among the edit-window hits.
- **Filter:** hit records, configuration 5, `mutation: on`.
- **Denominator:** the hit records of each window kind.
- **Interval:** none. Each repetition is shown. The `RWMutex`-against-copy-on-write comparison is not measured here
  (dropped, `Final_Proposal.md` §12).
- **Cells:** (5, on). **Data:** item 7.4, not built. The edit times are not in `raw/` yet (§H, answer-store
  rule 8).

---

## Headline B — caching quality and correctness (§9.2)

### M07 — Cache hit ratio

- **Claim:** reuse volume. It is necessary but not sufficient: it means nothing without M08 beside it.
- **Formula:** hit ratio = (records with `cache ∈ {TIER1_HIT, TIER2_HIT}`) ÷ (served records). Also reported: the
  TIER1_HIT share and the TIER2_HIT share of served records.
- **Filter:** one cell per row. Per stratum (A, B-within, B-cross, C, D) and over all strata. Per split (R2).
- **Denominator:** served records (R4). SHED, ABANDONED and GENERATION_FAILED are counted beside, not in it.
- **Interval:** Wilson, `k` = hits, `n` = served records.
- **Cells:** all configurations with a cache, `mutation: off`. Configuration 4 has its three arms (gate off and MIXED
  off, gate on and MIXED off, gate on and MIXED on), never pooled. **Data:** item 6.2. Configurations 1–3 wait for
  item 6.0.

### M08 — False-hit rate (headline)

- **Claim:** S3 correctness (RQ2). The cost of caching in wrong answers. The headline claim fails if the rule cannot
  hold δ. δ ≤ 5 % is provisional until the judge's error is measured (item 5.3).
- **Formula:** false-hit rate = `k / n`. `k` is the judged hits with verdict `INCORRECT`. `n` is the judged hits: hits
  with verdict `CORRECT` or `INCORRECT` (`UNPARSED` leaves both).
  - Every wrong hit counts, whatever its layer. An inherited error and a retrieval error are wrong answers too: the
    user gets a wrong answer either way.
  - Printed beside it, always: the count of `k` in each layer (R7: `retrieval`, `inherited`, `reuse`, `undecided`),
    the `UNPARSED` count, and M20, the miss-path error rate, as the baseline.
- **Filter:** `mutation: off`. One cell per row. Per stratum and over all strata. The `answerable: false` queries are
  their own row (R6). Tuned on `validation`, reported on `test` (R2). The operating point `(τ, …)` is named.
- **Denominator:** judged hits.
- **Interval:** Wilson.
- **Cells:** configurations 2–5, `mutation: off` (configuration 2 has Tier-1 hits only). **Data:** the judge harness
  builds the verdicts and layers now, for configuration 4. Item 6.2 runs the other cells, and they wait for item 6.0.

### M09 — Hit-path p95

- **Claim:** C1's cost side. The rule is disproved if provenance buys reuse the latency budget cannot afford.
- **Formula:** p95 of `t_total_ms` over hit records, reported **per frontier point**, so configuration 4's retrieval
  cost shows in the same figure as its hit-rate gain. Also reported: the same p95 over TIER2_HIT alone (Tier 1 would
  hide it), and the end-to-end p95 over all served records for configurations 3 and 4 **at matched hit rate**.
- **Filter:** configurations 3 and 4, `mutation: off`, each frontier point `(τ, …)`.
- **Denominator:** the hit records (or served records) of the point.
- **Interval:** none. The repetitions are shown, with `n` beside each percentile. Co-hosted: a p95 is a bound (ADR-001).
- **Cells:** 3, 4. **Data:** item 6.2. Configuration 3 waits for item 6.0.

### M10 — Percent reaching the provenance check

- **Claim:** an invariant check, not a cost metric. Retrieval is issued on every Tier-1 miss, so band share no longer
  bounds what the rule costs.
- **Formula:** as `interfaces.md` §H, v0.10: among records with `similarity != null`, the share with
  `reuse_rule ∈ {namespace, composite}`. Cited, not restated. Beside it, per arm, the band share: the share of
  records past Tier 1 with `entered_band: true` (§H, v0.10 and v0.13).
- **Filter:** configuration 4 and 5, per arm.
- **Denominator:** as §H.
- **Interval:** none. The share is 1.0 by construction. A value below 1.0 is a defect (a gate was re-added before the
  lane rule) and stops the work. It is not a result.
- **Cells:** 4, 5. **Data:** `raw/`, now for configuration 4.

### M11 — Support-gate refusal rate, decomposed by arm

- **Claim:** the support gate's isolated contribution. If both arms are near 0, the gate is inert on this corpus and
  the frontier's two ablation arms coincide, which is the finding. A refusal is never confused with a namespace refusal
  (`refusal_cause`).
- **Formula:** for the candidates that reached the gate:
  - lexical refusals = records with `support_lex < 0.6` (`τ_s`, pinned);
  - numeric refusals = records with `support_numeric_ok == false`;
  - the two are reported separately, each as its own rate, with the count of records that both arms refused. They are
    never summed.
  - The gate's own refusals, `refusal_cause == SUPPORT`, are printed beside as a third number. It is not the sum of the
    other two, because one record can be in both.
- **Filter:** `support_gate == on` and `config_id ∈ {4, 5}`. `NOT_SCORED` is excluded and counted beside: it is a
  count of a broken instrument, not of a gate decision (run rule 10).
- **Denominator:** as `interfaces.md` §H, "Offline reading rules (v0.14)": records with `refusal_cause ∈ {SUPPORT,
  NONE}` and `source_overlap ≥ θ_run`. `θ_run` is `manifest.cache.theta_run`. Since θ is not served (R3), that test is
  a filter on a logged counterfactual. The same rates without it (all records with `refusal_cause ∈ {SUPPORT, NONE}`,
  the candidates that cleared τ and the namespace) are printed beside.
- **Interval:** Wilson, for each rate.
- **Cells:** (4, gate on) in its MIXED arms, and 5. **Data:** `raw/`, now for configuration 4.

### M12 — Residual false-hit rate on same-evidence pairs (RQ2a)

- **Claim:** the characterised structural limit. False hits survive every gate because the query and the entry
  retrieve the same evidence and differ only in the condition asked about. It bounds C1's applicability. It is
  expected to be non-zero. A value of zero would mean the corpus lacks the case, not that the mechanism closed it.
- **Formula:** residual rate = `k / n`.
  - `n` is the judged TIER2_HITs in stratum B-within.
  - `k` is those with verdict `INCORRECT` and the same evidence: `set(retrieved_chunk_ids) == set(entry_sources)`.
  - Printed beside it: the INCORRECT hits with different evidence (the gates could have seen a difference); the layer
    of each `k` (R7); and the share of `n` that has the same evidence.
- **Filter:** stratum B-within, `mutation: off`, `cache == TIER2_HIT`. A TIER1_HIT has no retrieval, so it has no
  evidence to compare. A repeat of an earlier false hit through a promoted Tier-1 key is counted in M08, not here.
- **Denominator:** judged B-within TIER2_HITs.
- **Interval:** Wilson. Reported **beside** the headline, never inside it.
- **Cells:** 4 (all three arms) and 5, `mutation: off`. **Data:** the harness builds the verdicts now for
  configuration 4. Item 6.4 reports it. The test split is read only there.

### M13 — Staleness rate

- **Claim:** S3 under churn (RQ3). The core of the `(3, on)` against `(5, on)` comparison: a conventional cache under
  source change against the full system.
- **Formula:** a hit is *exposed* when its entry was written before an edit to one of the chunks in its
  `entry_sources`, and the hit is served after that edit. The entry's write time is the `ts` of its MISS (R7, the
  entry's MISS). A hit is *stale* when it is exposed and its verdict is `INCORRECT` against a reference built from the
  **post-edit** text. Staleness rate = stale hits ÷ exposed hits.
  - A cosmetic edit keeps the answer, so an exposed hit after one is not stale unless the judge says so.
  - Hits that are not exposed are not in the rate.
- **Filter:** `mutation: on`; hit records; split `test`.
- **Denominator:** judged exposed hits.
- **Interval:** Wilson.
- **Cells:** (3, on), (5, on), and (4, on) if it runs. **Data:** item 6.5, not built. The edit times are not in
  `raw/` (§H, answer-store rule 8). The post-edit references are not the 5.1 reference set, which is `mutation: off`
  only, and the harness refuses a `mutation: on` run today.

### M14 — Invalidation completeness and precision

- **Claim:** C2 (RQ3). No stale entry survives a change, and unaffected entries are not over-purged. Completeness below
  1 means the dependency map or the epoch guard is broken. It stops the item as a defect. It is never a number to
  report.
- **Formula:** as `score_update_set.py` (item 4.4), over the entries present before the edits.
  - *Dependents* `D`: entries whose sources, from the MISS records, meet an edited chunk.
  - *Gone* `G`: entries with no `t1:` key and no `t2:` record after the purge.
  - Completeness = `|D ∩ G| / |D|`.
  - Exactness = `|G ∖ D|`, which must be 0.
  - Precision = the share of `D ∩ G` whose sources meet a `substantive` edit. An entry under both a substantive and a
    cosmetic edit counts as needed.
  - Over-invalidation = the `D ∩ G` entries whose sources meet only `cosmetic` edits.
- **Filter:** configuration 5, `mutation: on`. Split into `substantive` and `cosmetic` edits.
- **Denominator:** `|D|` for completeness and `|D ∩ G|` for precision.
- **Interval:** Wilson, for completeness and precision.
- **Cells:** (5, on). **Data:** item 4.4 built the check and ran it as a functional run, not citable. Item 6.5 repeats
  it under the held-out split.

### M15 — Decisions changed by provenance

- **Claim:** the null-result enabler. How often the rule changes the similarity-only outcome. If rarely, the signal is
  thin wherever the frontier stands. Collected whatever the outcome: without it, a null is uninterpretable.
- **Formula:** a join of configuration 3's records with configuration 4's on query identity, `(query_raw, product_id)`.
  A decision is `(cache, entry_id)`. A decision changed when the two runs' decisions on a query differ. Rate = queries
  with a changed decision ÷ queries in both runs. As `interfaces.md` §H, "Joins name their arm": 3 ⋈ 4 with the gate
  off is provenance alone; 3 ⋈ 4 with the gate on mixes provenance with the support gate, and both name their arm.
  Whether a changed decision was right is not counted here: M08 gives each side's false-hit rate.
- **Filter:** the static-cache arm only, where both runs start from the same pre-populated, frozen, write-disabled
  cache. Online, a refusal causes a different write-back and the two caches drift apart. `mutation: off`.
- **Denominator:** queries present in both runs.
- **Interval:** Wilson.
- **Cells:** 3 against 4 (gate off, MIXED off), and against 4 (gate on). **Data:** not built. The static-cache arm is
  item 6.3, configuration 3's served path is item 6.0, and the join script has no item yet (super-plan F-K).

### M16 — False hits by cause

- **Claim:** attribution. Reuse-decision error and staleness are kept separate, so the rule is not blamed for
  invalidation faults.
- **Formula:** every `INCORRECT` hit gets one cause, first match wins: `stale` (M13's test), then the layers of R7 in
  their order (`retrieval`, `inherited`, `reuse`, `undecided`). The table has one row per cause, each as a count and as
  a rate over judged hits. Layer 5, `reference`, is printed beside as the 5.2 sample's count (R7). The rows are never
  added into one number.
- **Filter:** hits; `mutation: on` for the `stale` row. Under `mutation: off` no edit runs, so `stale` is 0 and the
  rows equal M08's layer counts.
- **Denominator:** judged hits.
- **Interval:** Wilson, for each row.
- **Cells:** (5, on), and every `mutation: off` cell for the layers. **Data:** the layers exist now for
  `mutation: off`. The `stale` row waits for item 6.5.

### M17 — Compute and embedding calls saved

- **Claim:** load conversion (§3), and the only justification for keeping Tier 1 as its own tier.
- **Formula:**
  - Generations avoided on hits = records with `cache ∈ {TIER1_HIT, TIER2_HIT}`.
  - Embedding calls saved by Tier 1 = records with `cache == TIER1_HIT` and `t_embed_ms == null`. Embedding calls
    made = records with `t_embed_ms != null`.
  - Coalesced MISS followers also avoid a generation. They are counted apart, as singleflight's saving, never as the
    cache's.
  - Each is a count, and a share of served records.
- **Filter:** one cell per row, `mutation: off`.
- **Denominator:** served records, for the shares.
- **Interval:** Wilson, for the shares.
- **Cells:** configuration 2 is the only cell that isolates embedding calls saved. Configuration 1 saves none.
  **Data:** item 6.2. Configurations 1 and 2 wait for item 6.0.

---

## Service rates and the baseline

### M18 — μ_gen

- **Claim:** the miss path's sustainable generation rate at the frozen one-slot envelope (ADR-003). It is the first
  term of `λ_max`.
- **Formula:** two figures, always named.
  - *Requests per second:* `1 / mean(t_generate_ms / 1000)` over the records with `cache == MISS ∧ t_generate_ms != null`
    (§H reading rule i), taken from a run with no load generator and a single stream, so nothing queues. The permit
    also covers the `Answer` RPC and the write-back, so this figure is at most Ollama's.
  - *Tokens per second:* Ollama's `eval_count` ÷ `eval_duration` for the same generations, read by the item 7.5 probe.
    It is not in §H. The spike's 28.2 tok/s has no surviving log and no recorded method (ADR-003), so this is the
    first written definition.
- **Filter:** configuration 1 or 5, `mutation: off`, cold cache. ABANDONED records are left out: their
  `t_generate_ms` is censored.
- **Denominator:** the MISS leaders.
- **Interval:** none. The repetitions are shown. The planning figures are 28.2 tok/s and 0.19 req/s, until Phase 7
  re-measures them under sustained load. The two are reported together, and the entry says which is used for `h*`.
- **Cells:** 1 and 5. **Data:** item 7.5, not built.

### M19 — μ_hit

- **Claim:** the hit path's service rate, the second term of `λ_max`. A 100 %-hit load test, in both modes (Tier 1 and
  Tier 2), because the two are different ceilings.
- **Formula:** pre-warm the cache, replay only cached queries, drive to saturation. μ_hit = the highest M01 goodput of
  the point, median repetition. A point with any MISS in its window is void. The hit-path latency is split into
  `t_tier1_ms`, `t_embed_ms`, `t_search_ms` and `t_overlap_ms`, each reported alone. They are not summed:
  `t_overlap_ms` runs at the same time as `t_embed_ms` (§H).
- **Filter:** TIER1_HIT mode and TIER2_HIT mode, each its own figure. `mutation: off`. A run starts on a cache it wrote
  itself (§H rule 11).
- **Denominator:** window seconds.
- **Interval:** none. The repetitions are shown. A co-hosted μ_hit is a **lower bound**, never a ceiling (ADR-001).
  The Tier-1 probe is the number most exposed to this.
- **Cells:** 4 and 5 for Tier 2, 2 for Tier 1. **Data:** item 7.2, not built.

### M20 — Miss-path error rate

- **Claim:** the baseline for M08. The share of wrong answers the system gives when it generates, with no reuse. The
  cache is charged only for what it adds to this.
- **Formula:** miss-path error rate = `k / n`. `k` is the MISS records with verdict `INCORRECT`. `n` is the MISS
  records with verdict `CORRECT` or `INCORRECT`. Printed beside it: the layer of each `k`. A MISS has only two layers,
  `retrieval` and `generation`.
- **Filter:** `cache == MISS` and `answer_sha256 != ""`, `mutation: off`. Per stratum and over all strata. The
  `answerable: false` queries are their own row (R6). Coalesced followers are MISS records and count.
- **Denominator:** judged MISS records.
- **Interval:** Wilson.
- **Cells:** every `mutation: off` cell. Configuration 1 (every request generates) is the cleanest baseline.
  **Data:** the harness builds it now, for configuration 4.
