# Super Plan — execution to submission

**Status:** in force · **Created:** 2026-09-21 · **Revised:** 2026-10-04
**Companion to:** `contracts/requirements.md` (what must be true), `decisions.md` (why),
`Final_Proposal.md` §12 (drop order) and §13 (deliverables).

This file owns **execution**. It is derived from the critical path through the codebase as it
actually stands, not from the phase order that predated the code — see "Why the phases moved".

---

## What this document owns, and what it must never restate

Several documents used to describe what to do next at once. One plan with four sources is how a
plan drifts, so ownership is split explicitly:

| Owner | Owns |
| :--- | :--- |
| **`super-plan.md`** (this file) | **Execution.** The ordered items, what they discharge, what unblocks them, and what "done" means for each |
| `Final_Proposal.md` §12 | **Drop order under pressure.** Never restated here — many documents cite §12, and a second copy is exactly what would drift when schedule pressure arrives |
| `Final_Proposal.md` §13 | **Deliverables.** Never restated here |
| `contracts/requirements.md` | **What must be true.** Items cite `FR-xx` / `NFR-xx` / `RR-xx`; they do not re-argue them |
| `decisions.md` | **Why.** Items name what they rest on; they do not re-argue it |

**The week-based schedule this replaced was deleted on 2026-09-22.** Nothing in this file refers
to it. Two sections it carried — the **Risk Register** and the **Learning Path** — have no home
and were not recovered.

⚠️ **`contracts/requirements.md` is still empty**, so the *Discharges* column below cites the **contribution**
(C1 / C2 / C3) and the **scalability clause** (S1–S4) it serves — both of which *are* defined, in
`Final_Proposal.md` §5 and §3. Requirement IDs replace those citations when `requirements.md` is
filled; the column is not left blank in the meantime, because an item that discharges nothing
identifiable should not be in a plan at all.

---

## The spine — why safety and throughput are one problem here

`Final_Proposal.md` §3 fixes capacity as **λ_max = min( μ_gen / (1 − h) , μ_hit / h )**. `μ_gen` is
fixed by the envelope (one generation slot, ADR-003) and planned at ≈ 0.19 req/s, a projection from
the spike that Phase 7 re-measures. So **`h`, the hit rate, is the only free variable that raises
capacity** — and `h ≤ ρ` for any cache that serves no false hit, because `h > ρ` is reachable only
by being wrong.

Three consequences, and they are why the phases are ordered the way they are:

1. **The safety work *is* the throughput work.** A gate that refuses unsafe reuse is what licenses
   running a *lower* θ/τ at the same δ, which raises `h`, which raises λ_max. The support gate of
   the support gate is the highest-value unbuilt item for **both** halves of the objective — it is not a
   correctness tax paid against throughput.
2. **Admission control does not raise capacity; it protects it.** It is S2 (stability), not S1
   (capacity), and it is **already built**. It is sized to the one slot the model server actually
   serves (ADR-003, which resolved finding F1), and it protects **queueing delay and goodput, not
   memory**: memory is fixed when Ollama loads the runner.
3. **Tier-1 promotion is an unmeasured throughput lever already in the tree.** μ_hit is ~8000 req/s
   on Tier 1 against ~61 on Tier 2, so the **tier mix** moves μ_hit more than any Tier-2
   micro-optimisation can. `handler.go` began promoting Tier-2 hits into Tier 1 on 2026-09-10 and
   nothing has measured the effect.

One rule binds over all of it: **never tune to make a headline work.** Thresholds are swept, tuned
on validation, reported on held-out test. The deliverable is a **frontier**, never a tuned point.

---

## Item template

Every item is a row of this shape. An item that cannot fill the citation columns is not ready to
be planned — it needs a requirement, or an ADR, or both, first.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |

Two columns earn their place and are easy to skip:

- **"Unblocked when"** is what makes the order *derivable* rather than asserted. An item whose
  blocker is another item creates the sequence automatically; an item blocked by a human decision
  says so, by name, so it is visible that it is waiting on a person rather than on work.
  **Once an item's "Done when" test passes**, its own cell becomes `✅ Done <date>`, followed by
  its ADR, if any, and its trail. Every other row that lists it as a blocker marks it `✅` too
  (`7.1, 1.1 ✅`), so the column shows at a glance what is finished and what still blocks.
- **"Done when"** is a **binary test**. "Improved", "hardened" and "investigated" are not
  done-conditions. An item is not finished because its time is spent.

---

## Standing constraints on every item

These are not items. They hold across all of them, and an item that violates one is wrong
regardless of how well it is executed.

1. ~~**F1 sits above the order.** No admission-control number is citable until it resolves.~~
   **Resolved by ADR-003 (2026-10-04, item 1.1).** One slot is frozen, the gateway grants one permit,
   and `make env-check` verifies the live runner. Admission numbers are citable from here on, subject
   to the other constraints, and q is pre-registered per item 7.5.
2. **The platform is the thesis.** Research work never starves platform work.
3. **`dev-v0` is not citable in any result.** Only the frozen `v1`.
4. **Runs taken under yellow or red memory pressure are discarded and repeated.** A run taken
   outside green pressure measures the swap, not the system.
5. **A frozen value changes only through a numbered entry in `decisions.md`**, and that entry
   states what it invalidates. Nothing enforces this — it is the only trace such a change leaves.
6. **No measurement runs off an untested instrument.** Added 2026-09-21: `httpapi/` carried 856
   lines and zero tests while every number in the thesis passed through it. Phase 1 exists for this.

---

## Phases

Eight phases. Each ends on a binary exit test; the next does not open until it passes. Hour figures
are indicative against the ≈ 225 h remaining — `Final_Proposal.md` §12's drop order is the release
valve, not these numbers.

### Phase 1 — Instrument integrity

**Exit:** `httpapi` has tests covering every exit path of `Ask` · `make env-check` fails when the effective Ollama slot count differs from the frozen value · `texts` flows Python → Go with positional alignment asserted · no retired branch remains in the cascade · a judged answer is recoverable from `raw/` alone · the load generator's footprint is measured and the co-hosted-measurement decision is recorded as ADR-001.

*Nothing measured before this closes is evidence of anything.* ~25 h.

**Progress, 2026-10-05:** 3 of 6 exit clauses met: the `env-check` clause by item 1.1, the
`httpapi` clause by item 1.2, and the `texts` alignment clause by item 1.4. 1.3, 1.5 and 1.6 are
all unblocked.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 1.1 | **Resolve F1.** Ollama overrides `OLLAMA_NUM_PARALLEL` to `-np 1` for qwen3.5. Add a check that reads the **effective** slot count from the live runner (its argv `-np` and its own `/props` `total_slots`; ADR-003 records why not the server log) rather than the requested value, and write the ADR deciding what μ_gen ≈ 28.2 tok/s means if it was a one-slot number recorded as a four-slot aggregate | S1, S2 | memory envelope, admission control | ✅ **Done 2026-10-04** — ADR-003, trail `docs/work/2026-10-04-resolve-f1/` | `make env-check` fails when effective ≠ frozen, and an ADR records the consequence for μ_gen |
| 1.2 | **Tests for `httpapi/`.** The cascade, the miss path, coalescing-wraps-admission nesting, Tier-1 promotion, and the single-exit eval-record emit | C1, C3 | standing constraint 6 | ✅ **Done 2026-10-04** — no ADR (no frozen value or contract changed), trail `docs/work/2026-10-04-httpapi-tests/` | Every exit path of `Ask` — TIER1_HIT, TIER2_HIT, MISS, SHED, ABANDONED, GENERATION_FAILED — has a test asserting its response **and** its eval record |
| 1.3 | **Remove the retired cascade branch.** Delete the unfiltered cascade phase, `tau_high` / `REUSE_TAU_HIGH`, and `similarity_only_decision`. Correct the stale pinned default in `rule_test.go` (claims `1.0`; ships `math.Inf(1)`) | C1, C3 | retiring the unfiltered phase | 1.2 ✅ — do not delete branches that nothing tests. 1.2's trail names the only two of its tests 1.3 may change (`approvals.md`, item 2) | The cascade issues one scoped search; `grep -r tau_high` finds only history; §H no longer carries the retired field |
| 1.4 | **Carry chunk text across the seam.** `server.py` populates `texts`; `ragclient` receives it. Proto and both stubs are already done | C1 | `Retrieve` returns text | ✅ **Done 2026-10-05** — no ADR (no frozen value or contract changed), trail `docs/work/2026-10-05-carry-chunk-text/`. Re-run `make seam-check` after any retrieval or LlamaIndex change: `make verify` never runs the live path | An end-to-end test asserts `texts[i]` is the text of `chunk_ids[i]`, and a deliberately shifted array fails it |
| 1.5 | **Answer-text storage.** §H stores `answer_sha256`, never the text, and judging runs offline with the generator unloaded. Recovering text from a bounded LRU afterwards is unsound. Content-addressed `raw/answers/{answer_sha256}.txt` | C3 | needs a numbered decision — it changes §H, which is frozen | now | A run's answers are reconstructable from `raw/` alone, with the cache flushed |
| 1.6 | **Characterise the load generator's footprint** and **record the co-hosted-measurement decision** as the first entry in `decisions.md` (see "Measuring without a second machine") | S1, S2 | measurement validity | now | k6's CPU and RSS at the sweep's actual rates are recorded, with the SUT's pressure zone alongside, and the ADR states what is citable co-hosted and what is not |

**Found while closing 1.1, not yet items — each waits on the author's decision:**

- ✅ **`rag-server-reuseport`, resolved 2026-10-05** as a bugfix outside the exit line (trail
  `docs/work/2026-10-05-rag-server-reuseport/`). `rag/src/rag/server.py` bound with gRPC's default
  `SO_REUSEPORT`, so a second server silently shared port 50051 and a run could be answered by a
  stale instance (six were found on 2026-10-03). The server now binds with `SO_REUSEPORT` off, so a
  second bind on the same address raises. **Residual, recorded rather than fixed:** a wildcard and a
  specific address (`0.0.0.0:P` and `127.0.0.1:P`) can still coexist on macOS. That needs a
  non-default `RAG_GRPC_ADDR`.
- **Generation determinism (U8).** The Modelfile sets `temperature 1` and `generate.py` does not
  override it, so the same miss can produce different answers from run to run. It bears on judging
  (5.1) and on reproducibility. It needs an investigation before 1.5 or 5.1 is built on it.
- **For the advisor:** withdraw the proposal's `OLLAMA_NUM_PARALLEL` sweep (§6.2), which cannot run
  on this model and stack (ADR-003). This is a human decision, and it must be settled before Phase 7.

**Found while closing 1.2, not yet items — each waits on the author's decision** (full list F-A to
F-K in `docs/work/2026-10-04-httpapi-tests/spec.md`; order in that trail's `approvals.md`, item 3):

- **F-K: the served Tier-2 rule is similarity ∧ namespace, not the four claimed conjuncts.** θ
  reaches only the logged counterfactual and `ConfigID` selects nothing, so **6.1's θ sweep would
  move no served decision**. No ADR records the change. It needs an owner: an ADR that makes the
  namespace rule the claim, or an item (probably in Phase 2) that puts θ into the served decision.
- **F-A: most client abandonments are logged `GENERATION_FAILED`.** A cancellation that reaches a
  gRPC call surfaces as a gRPC status, not `context.Canceled`. Fix it before 1.6 and before any
  Phase 7 run.
- **F-F: the eval log closes while shutdown is still draining.** Requests in flight at SIGTERM
  vanish from `requests.jsonl` with `Dropped()` at 0. It is avoided by stopping the load before
  SIGTERM, and the fix is cheap. Fix it before Phase 7.

**Found while closing 1.4, not yet items — each waits on the author's decision** (trail
`docs/work/2026-10-05-carry-chunk-text/`, `approvals.md`):

- ✅ **`make dev` orphaned `rag.server`, resolved 2026-10-05** with `rag-server-reuseport`.
  Confirmed under `/bin/bash` 3.2: `$!` was the subshell, so the trap left the server bound to
  `:50051`. The fix has three parts:
  - `make dev` now `exec`s the server, so `$!` is the server itself;
  - it refuses to start if the port is already held;
  - it starts the gateway only once its own server PID is listening, replacing a `sleep 2` that a
    late bind failure slipped past.

  2.1's obligation on nil `Texts` stands regardless: the gateway's own connection is still the only
  check on the gateway's instance.
- **For 3.1:** the PQA builder must not emit text that redis-py's strict UTF-8 encoder rejects (a
  lone surrogate from a JSON `\ud800` escape); it would fail `make ingest` (PLAUSIBLE; 1.4
  `review.md` N5).

### Phase 2 — The support gate

**Exit:** the gate refuses the measured warranty case and admits the measured paraphrase · every Tier-2 refusal carries a cause code · both arms are independently switchable and both are recorded per request · the decisive-similarity regression still reproduces.

*The highest-value unbuilt item for both halves of the objective.* ~20 h.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 2.1 | **Lexical arm.** `S_lex(a,C) = \|content-tokens(a) ∩ tokens(C)\| / \|content-tokens(a)\|`, stop-words and tokens under three characters removed. `τ_s` **pinned at 0.6**, never swept. ⚠️ **`RetrieveResult.Texts == nil` with `len(ChunkIDs) > 0` means the service sent no evidence text** (e.g. a stale pre-1.4 server): do not score it, do not refuse it as `SUPPORT`, and do not log it as the gate-off arm (`support_lex: null`) — each misattributes a stale server to the gate. Key on `len(ChunkIDs) > 0`, since an empty retrieval is nil too, and count the condition (1.4 trail, `review.md` S3) | C1 | the support gate | 1.4 ✅ — the gate cannot run without chunk text | On the pair pinned in `lane_test.go` (0.9382 paraphrase, 0.9208 warranty, containment 0.80 each) the gate admits the first and refuses the second |
| 2.2 | **Numeric arm.** Every numeric literal and its unit in the cached answer must appear in the fresh evidence. **Fail-closed** | C1 | the support gate | 2.1 | A cached "30-day" answer is refused against evidence carrying only "14-day"; an unparseable number blocks rather than passes |
| 2.3 | **Refusal cause code** in §H: `SIMILARITY` \| `NAMESPACE` \| `CONTAINMENT` \| `SUPPORT` \| `NONE`, plus `support_lex` and `support_numeric_ok` | C1, C3 | the support gate | 2.1 | Every Tier-2 decision in the log carries exactly one cause; a support refusal is distinguishable from a namespace refusal offline |
| 2.4 | **Both arms switchable per run**, since configuration 4 is two arms rather than one | C1, C3 | the support gate, config × mutation grid | 2.2 | `support_gate` in the run manifest selects the arm, and the off-arm writes `null` for both support fields |

### Phase 3 — Corpus and workload

**Exit:** G1…G5 all pass and `make gate-corpus` prints the snapshot digest · `K`, the derived capacity and every frozen corpus statistic are recorded in `data-card.md` · the validation/test splits are frozen with the dataset.

*Four jobs, not a download. Longest lead, and it can fail its own gate and need rework.* ~45 h.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 3.1 | **PQA build script**, replacing `fetch_corpus_v1.py`. ⚠️ **Write it against the bytes, not the readme** — the dataset's own documentation names fields the data does not use, and a builder written from it returns empty records **silently** | C1, C3 | Amazon-PQA | now | The script asserts a non-zero parse rate and refuses to write on zero; it emits a **hash manifest**, never the raw corpus |
| 3.2 | **Select into the thick tail.** Questions-per-product is skewed within a category and varies ~4× between categories; a uniform draw returns mostly single-question products, from which no stratum A or C pair can be built | C1 | Amazon-PQA | 3.1 | The selection rule is recorded in `data-card.md`, and the realised questions-per-product distribution is reported with it |
| 3.3 | **Author the policy documents.** Per-category return *and* warranty windows that genuinely differ, ≥3 chunks each, and ⚠️ **opposing conditions in separate documents, not separate chunks** — a chunk-level split is invisible to the namespace, which is document-granular by design, and leaves all four conjuncts blind at once | C1, C2 | `v1` corpus model, condition-splitting, opposing conditions in distinct documents | now | Every policy document yields ≥3 chunks and **no two opposing conditions share a `doc_id`**. Note this raises the count above 8: one category's return policy split into *opened* / *unopened* is two documents |
| 3.4 | **Workload generator** — does not exist. Strata A / B-within / B-cross / C / D, Zipf popularity, and the validation/test split partitioned **by seed-question cluster**, never by pair, which would leak paraphrases | C1, C3 | `v1` corpus model, B-within / B-cross split | 3.2, 3.3 | Every query carries exactly one stratum and one split assignment; no seed cluster spans both splits |
| 3.5 | **G5 in `corpus_gate.py`.** `data-card.md` §7 requires five criteria; the code implements four. Structural, stage 1, beside G3 and G4 | C1 | condition-splitting, opposing conditions in distinct documents | 3.3 | The gate fails a corpus where two opposing conditions share a `doc_id`, and names both |
| 3.6 | **Gate, freeze, hash.** Record `K`; derive `cache_capacity = round(0.25 × K)` | C1, C3, S1 | capacity ratio, `data-card.md` §7 | 3.4, 3.5 | The digest prints, every `TODO(W8)` in `data-card.md` §7 is filled, and no experiment runs against an unfrozen corpus |

### Phase 4 — Invalidation (C2)

**Exit:** editing a policy purges exactly its dependents from **both** tiers · an in-flight generation during an edit is discarded with `writeback_discarded: true` in the log · completeness and precision are reproducible from one script.

*`deps/` is a six-line `doc.go` today. C2 does not exist.* ~30 h.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 4.1 | **Dependency map.** `dep:{chunk_id} → SET(entry_id)` in the `noeviction` region, in-process copy-on-write index, single writer goroutine, purge hitting both tiers via `t1_key` | C2, S4 | inherited decision, invalidation under load, `interfaces.md` §E | 3.6 | A policy edit purges its dependents from `t1:` and `t2:` and leaves unaffected entries alone |
| 4.2 | **Epoch-guarded write-back**, and make it set `writeback_discarded` — the field is logged today and **never assigned** | C2, C3 | `interfaces.md` §E, evaluation log | 4.1 | Forcing the race produces `writeback_discarded: true`; the stale answer never reaches the cache |
| 4.3 | ⚠️ **Fix the promoted-`t1_key` bug before it detonates.** Tier-1 promotion mints a second, untracked `t1_key` per entry — harmless *only* while capacity is unbounded and C2 is unbuilt. Phase 3 bounds capacity and this phase ships C2; **both preconditions expire here** | C2, S3 | needs a decision: track multiple `t1_key`s, or drop promoted keys on purge | 4.1 | A purge removes every Tier-1 pointer at the entry, promoted ones included; an eviction leaves no orphan |
| 4.4 | **Update set**, ~20 edits, balanced `substantive` / `cosmetic`, so over-invalidation is measured rather than assumed | C2 | `v1` corpus model | 3.6 | Completeness and precision computed from one script against the labelled set |

### Phase 5 — Judging, δ, and the figure pipeline

**Exit:** judge-to-human and reference-anchored-against-reference-free agreement are both recorded · δ is finalised against the measured noise floor · `make figures` regenerates every figure from `raw/` on a clean checkout.

*The judge harness and the figure generators do not exist; `experiments/README.md` claims both do.* ~25 h.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 5.1 | **Judge harness** — does not exist. Frozen prompt, judge model ≠ generator, offline batch with the generator unloaded, verdicts deduped by `answer_sha256`, reading Phase 1's answer store | C1, C3 | scope reduction | 1.5, 3.6 | Judge model id and prompt version are frozen and recorded **before** any frontier is computed, and per-configuration cost is measured before scaling to five |
| 5.2 | **Labelling ablation** on ~100 pairs under both schemes; agreement reported **by containment bucket** | C1 | validity is method | 5.1 | Both agreement numbers recorded; circularity bounded or quantified |
| 5.3 | **Finalise δ** against the measured judge error | C1 | false-hit budget | 5.2 | δ is fixed and clearly exceeds the noise floor, or the gap is reported as the reason it cannot be |
| 5.4 | **Figure generators** — do not exist. `make figures` invokes an absent script with no guard | C3 | `raw/` is write-once | 5.1 | `make figures` regenerates every figure from write-once `raw/` on a clean checkout, and never the reverse |

### Phase 6 — Headline B, the frontier

**Exit:** Headline B exists on the held-out split with both isolation controls · the B-within against B-cross split is reported · RQ2a is reported beside it with its own interval.

~30 h.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 6.1 | ⚠️ **Pre-register the sweep before running it.** `Final_Proposal.md` §9.4 books this debt in its own words: θ's range is *"not stated anywhere"*, τ's granularity is unstated, the lane-band bounds are unspecified, and *"the best fixed threshold"* has **no written selection objective** | C1, C3 | `Final_Proposal.md` §9.4 books the debt but names no home for it — see P1 in `decisions.md` | 5.3 | All four are pinned in `decisions.md`, dated, **before** a single sweep point runs |
| 6.2 | **Five configurations at `mutation: off`**, with configuration 4 as **two arms** (support gate off and on). Sweep on validation, report on held-out test, Wilson intervals | C1 | config × mutation grid, the support gate | 6.1 | Every point carries its interval; no threshold was chosen on the test split |
| 6.3 | **Isolation controls.** Static-cache ablation — **non-negotiable** since retiring the inline counterfactual made decisions-changed-by-provenance a cross-configuration join valid only on that arm — and stratified reporting | C1 | validity is method, retiring the unfiltered phase, B-within / B-cross split | 6.2 | Both frontiers reported; disagreement between them reported as a finding rather than reconciled |
| 6.4 | **RQ2a — the residual.** Same-evidence, opposite-condition pairs surviving every gate, on the B-within stratum built to contain them. Reported **beside** the headline, never inside it | C1 | the support gate, condition-splitting | 6.2 | RQ2a has its own Wilson interval and is stated as the boundary of the claim |

### Phase 7 — Headline A, capacity (co-hosted)

**Exit:** Headline A exists with every contributing run in green pressure · `h*` is computed from both measured service rates and shown to lie outside the reachable range **at the lower bound** · every figure regenerates from `raw/` · every co-hosted number carries its interference measurement.

*Run under the co-hosted régime described below. Nothing here is scheduled as if a second machine will appear.* ~30 h.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 7.1 | **Redundancy × load sweep**, co-hosted. Three Zipf skews, cache-on against cache-off, ≥3 repetitions per point, pressure sampled at ≥1 Hz | S1, S2 | measurement validity as amended, capacity ratio | 1.6, 6.2 | Curves exist at every point and the **hit-rate spread across the three skews is non-zero** — a flat spread means capacity was mis-derived, not that the cache does not work |
| 7.2 | **μ_hit in both modes, reported as a lower bound.** Tier-1 and Tier-2 are different ceilings and the tier mix is itself a function of redundancy, so the second term of λ_max is evaluated **per sweep point**, never once from an average. `nomic-embed-text` also serves one slot (resolve-f1, U7), so the embedding round-trip may be what bounds Tier-2 μ_hit | S1 | capacity ratio, `interfaces.md` §F | 7.1 | Both figures recorded with the co-hosting bias direction stated; `h*` at the lower bound compared against the reachable range of `h` |
| 7.3 | **Measure the Tier-1 promotion effect on tier mix** — a built, unmeasured throughput lever, and the cheapest remaining way to raise μ_hit | S1 | — needs no new decision; the code shipped 2026-09-10 | 7.1 | The tier mix with promotion on and off is reported at matched workload |
| 7.4 | **Invalidation under load**, fast-path p99 and reader stall while purges fire | C2, S4 | invalidation under load | 4.2, 7.1 | The read fast path does not stall behind an invalidation, or the stall is measured and reported |
| 7.5 | **Saturation analysis and freeze.** Shed rate and permit-queue depth at saturation; goodput never counts sheds. State which μ_gen is reported: the permit also covers the Answer RPC and write-back, so a gateway-measured μ_gen ≤ Ollama's (resolve-f1, N7) | S1, S2 | admission control, `Final_Proposal.md` §3, ADR-003 | 7.1, 1.1 ✅ | Headline A exists; measured λ_max plotted against the model; the queue budget q was pre-registered before the first saturation run and is recorded per run (ADR-003); all results frozen and every figure regenerable |

### Phase 8 — Write-up and defence

**Exit:** a submission-ready thesis and a rehearsed defence.

~40 h.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 8.1 | Chapter skeleton, background and related work, architecture chapter | — | — | 6.4 | 50 % draft |
| 8.2 | Evaluation chapter built around the two headline figures, with the limitations stated rather than defended — including everything measured co-hosted, and that the backend serves **one generation stream** (ADR-003) | — | ADR-003 | 7.5 | Full draft to advisor, **and** the admission-control text frames the pool as queueing and shedding at one slot, never as a memory bound (ADR-003 — the reframing the W5 spike's no-go branch required) |
| 8.3 | Revision, slides, rehearsal. **Buffer** | — | — | 8.2 | Submission-ready and rehearsed |

---

## Measuring without a second machine

Confirmed with the author on **2026-09-21: no second machine exists and none is dated.** The
original validity rule required off-box load generation, and the risk register's own mitigation is
*"measure and report generator interference."* This is that, made concrete. **It needs its own
entry in `decisions.md`** — the alternative is a silent deviation from a frozen decision, which is
the failure mode this repo exists to prevent.

**Two cases, and they must not be lumped together.** The 2026-09-06 run that drove memory pressure
to *urgent* was the **Tier-1 μ_hit probe at 400 rps**, saturating an ~8000 req/s path. The main
capacity sweep is a different regime: μ_gen ≈ 0.19 req/s caps λ_max at ≈ 16 req/s even at the best
reachable hit rate, so the sweep offers ≲ 16 req/s and a generator at that rate costs little.
Whether "little" is small enough is **item 1.6's measurement**, not an assumption.

**Why the headline claim survives co-hosting.** S1's claim is an *inequality*, not a value: that
`h* = μ_hit / (μ_gen + μ_hit)` lies **outside** the range of `h` the workload reaches (≈ 0.988), so
the system is generation-bound throughout its operating range. `h*` is monotone increasing in μ_hit,
and **co-hosting depresses μ_hit** — the generator starves the embedding server that bounds the
Tier-2 hit path. A co-hosted measurement is therefore a *lower* bound on μ_hit and so a *lower*
bound on `h*`. At the already-measured co-hosted 61 req/s, `h* ≥ 0.9969 > 0.988` and the finding
stands; an off-box run could only raise μ_hit and strengthen it. **A bound is sufficient for the
claim being made** — and that is stated in the ADR rather than left for an examiner to find.

What is **not** rescued, and is reported as a limitation rather than argued around:

- Any figure presented as a **ceiling** rather than a bound — the Tier-1 μ_hit number in particular.
- Latency percentiles at high offered rate, where generator and system under test contend for the
  same cores. Either report the generator's concurrent CPU alongside p95, or restrict p95 claims to
  the rates where item 1.6's footprint measurement shows headroom.
- **Two different margins must not be conflated.** *"μ_gen ≪ μ_hit by two to three orders of
  magnitude"* is about `μ_gen` against `μ_hit` and is **correct** (0.19 against 61 is ~320×). The
  margin over the capacity-ratio falsification trigger is a **different** comparison and is only **3.8×**
  (61 against ~16 req/s). Keep them apart wherever both appear: the first licenses `h* > 0.99`,
  the second is the one a co-hosted lower bound has to clear, and it clears it with far less room.
  `22-load-conversion.md` already states the 3.8× figure; the proposal's own wording
  (*"observable only if μ_hit ≤ ~16 req/s"*) is accurate and needs no change.

---

## Why the phases moved

The schedule this replaced was written before the code existed. The codebase has since run ahead of
it in some places and stayed empty in others, so the old boundaries no longer describe the work.

| | Old plan | Here | Because |
| :--- | :--- | :--- | :--- |
| Systems hardening | Phase 5, a build phase | **Not a phase** | `admission/`, `coalesce/` and `telemetry/` are built and tested. It becomes verification inside Phase 7 |
| Support gate | absent | **Phase 2** | Decided after the old plan was written, and it is the highest-value unbuilt item for both halves of the objective |
| Instrument integrity | absent | **Phase 1** | `httpapi/` had 856 lines and zero tests; F1 had no ADR and no detector |
| Corpus | one row | **Phase 3** | Four jobs, and the source changed to Amazon-PQA after the old plan was written |
| Judge, workload generator, figures | assumed to exist | named as **unbuilt** | None of the three exists; `make figures` invokes an absent script |
| Invalidation (C2) | Phase 2 | **Phase 4** | Unchanged in substance, but it now carries the promoted-`t1_key` fix, which its own preconditions expire on |

---

*Cross-references: `Final_Proposal.md` §3 (scalability clauses), §5 (contributions), §9 (evaluation
design), §12 (drop order — authoritative), §13 (deliverables — authoritative) · `data-card.md` §7
(corpus gate — authoritative) · `contracts/interfaces.md` §E, §H · `decisions.md` (inherited state,
and every decision taken from 2026-09-22 on).*
