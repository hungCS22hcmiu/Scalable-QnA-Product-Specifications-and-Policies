# Approvals — refusal-cause-code

| Phase          | Required    | Approved | When | ADR |
| :---           | :---        | :---     | :--- | :--- |
| impact         | L, M        | yes      | 2026-10-14 | — (the task changes a measured path and the §H contract, so it touches frozen state; **no citable run is invalidated**: `experiments/results/` is empty, and item 1.6's `footprint-20261006-b` Tier-2 hits were served with no gate and are not comparable across the 2.3 commit, `impact.md` §2. ADR-009 is required at the contract phase) |
| contract       | if §B/§D    | yes      | 2026-10-14 | **ADR-009** (reserved; written at `plan.md` step 8, and it must match `design.md` §6). Approves the `interfaces.md` v0.12 → v0.13 diff as described in `design.md` §6: §A reworded, §H gains 5 keys (`refusal_cause`, `support_lex`, `support_numeric_ok` required; `candidate_entry_id`, `candidate_sources` extensions), value `NOT_SCORED`, null rules, invariants I1–I6, rule 10, the `entry_*` field note. §B and the `.proto` are unchanged (Python sends nothing new). **No citable run is invalidated**; logs from before the 2.3 commit carry `TIER2_HIT`, `entered_band` and `source_overlap` under an older meaning and lack all five keys |
| experiment     | if measured | yes      | 2026-10-14 | — (ADR-009 carries it). Approves the measurement change as described in `design.md` §7: the served Tier-2 rule becomes similarity ∧ namespace ∧ support, so the Tier-2 hit rate, the tier mix, the band share and *false hits by cause* move; the refusal-rate denominator (`SUPPORT` and `NONE` records with `source_overlap ≥ θ_run`, `NOT_SCORED` excluded); rule 10 (any `NOT_SCORED` record makes a run inadmissible, decidable from `raw/`); gate latency (about 30 µs for both arms, **inferred and not measured**, no span, lands in `t_total − Σ t_*`, measured at Phase 7 with the gate on against off). **No citable run is invalidated** (`experiments/results/` is empty; `footprint-20261006-b`'s 250 `TIER2_HIT` were served with no gate and are not comparable across the 2.3 commit). A log from before the 2.3 commit and one from after must not share a figure |
| implementation | always      | yes      | 2026-10-14 | **ADR-009** (written at `plan.md` step 8). Over `plan.md` steps 1–9 and `design.md` revision 2 as written, with the ten design answers in the ledger. The plan's own stops stand: step 1e stops for the author before any wiring, and any existing test that changes outcome stops the work for `/rca` (the test is not edited). **No citable run is invalidated** (`impact.md` §2) |

## Decisions D1–D3

Recommended in `spec.md`; not yet answered by the author.

- **D1.** Chunk IDs with no evidence text: **refuse as `NOT_SCORED`** · serve and mark.
- **D2.** Served = **`NONE`**, no candidate judged = **`null`**.
- **D3.** Gate **always on** in 2.3 (switch is 2.4) · minimal `Handler` field now.

## Human decisions

| Date | Decision | Author's words | Invalidates |
| :--- | :--- | :--- | :--- |
| 2026-10-14 | **Open item 2.3 at scope L** (`/task refusal-cause-code L`), with D1–D3 as recommended in chat and the real-answer sample as plan step 1 | "yes, open it now, phase 2.3" | — |
| 2026-10-14 | **`/approve impact`** — `impact.md` accepted as the blast-radius analysis. This approves the analysis only. It does **not** answer A1–A5 (A1, the wrong acceptance 1, still blocks `design.md`), it does **not** confirm D1–D3, and it does not unlock source edits. The contract and experiment phases are still required | — (slash command) | no citable run (`impact.md` §2) |
| 2026-10-14 | **`/approve implementation` was refused**: the other required phases did not exist (no `design.md`, `review.md`, `plan.md`; `contract` and `experiment` unapproved). Nothing was written | — (slash command) | — |
| 2026-10-14 | **A1: accept the restated acceptance 1** (warranty = MISS, cause `null`; a synthetic case reaches `SUPPORT`). Asked once; the reply covered A1 only. A2 was **not** asked separately: `design.md` uses the recommended order and marks it unconfirmed | "yes" | — |
| 2026-10-14 | **Q1–Q10 from the design review: all accepted as recommended.** Q1 log `candidate_entry_id` and `candidate_sources` · Q2 `NOT_SCORED` makes a run inadmissible (rule 10, one ERROR line) · Q3 sample part (c) · Q4 `NAMESPACE` before `SIMILARITY` · Q5 refuse as `NOT_SCORED` · Q6 `NONE` = served, `null` = no candidate · Q7 gate always on, 2.4 adds one parameter to `Judge` · Q8 dev-v0 logs are **not** the first logged run (the trigger is the first run on v1) · Q9 leave ADR-001's `latency_ms` sentence alone · Q10 no `refusal_cause` in the HTTP response. D1–D3 and A2–A5 are settled by the same answers | "yes" | — |
| 2026-10-14 | **`/approve contract`** — the `interfaces.md` diff in `design.md` §6 accepted. This approves the contract change only. It does **not** approve the measurement change (`experiment`, still open) and it does not unlock source edits | — (slash command) | no citable run (`impact.md` §2) |
| 2026-10-14 | **`/approve experiment`** — the measurement change in `design.md` §7 accepted, including rule 10 and the refusal-rate denominator. This approves the experiment phase only. It does **not** unlock source edits: `/approve implementation` is still needed | — (slash command) | no citable run (`impact.md` §2) |
| 2026-10-14 | **`/approve implementation`** — unlocks, per `plan.md` steps 1–9: `reuse/cause.go`, `reuse/cause_test.go`, `telemetry/cause_fields_test.go`, `httpapi/cause_test.go`, `httpapi/cause_seams_test.go`, `ragclient/support_sample_live_test.go`; edits to `httpapi/cascade.go`, `httpapi/handler.go`, `telemetry/evallog.go`; comment-only edits to `httpapi/types.go`, `reuse/{support,support_numeric,rule,doc}.go`; and the doc rows in `interfaces.md`, `decisions.md`, `super-plan.md`, `architecture.md`, `README.md`. **Not** unlocked: any existing `*_test.go`, `cache/`, `cmd/gateway/`, the `.proto`, `rag/`, the Makefile, `Final_Proposal.md`. Given after the contract and experiment approvals; the ten design questions were answered "as recommended" before it | — (slash command) | no citable run (`impact.md` §2) |
| 2026-10-14 | **`/done`** — closes the task with plan steps 1c–1e (the real-answer sample) deferred and named as a follow-up that blocks Phase 2. Asked once, with the recommendation to run the sample first; the author chose to close | "yeah we can done" | no citable run (`impact.md` §2) |
| 2026-10-14 | **Go for step 1a and all remaining steps.** Read by the main session as the author's go for `plan.md` steps 2–9 after step 1, **except** that step 1e's stop still applies if the sample shows the gate refusing most real paraphrases (the second pre-registered null). **Reordered because of memory pressure:** the live sample (1c–1e) needs the LLM and the pressure was level 2 with 4.2 GB of 5 GB swap used, which the yellow allowance does not cover, so the offline steps 2–9 run first and the sample runs when pressure allows or the author says so. The sample's questions were frozen first (1a), so the reorder cannot influence them | "yeah, proceed with step 1a, then all of remaining steps" | — |

## Recorded follow-ups carried in

- From 2.1 and 2.2: the real-answer sample (spec acceptance 10); a "not scored" value in §H; the
  zero-chunk hole closed in the cascade; `cascade.go:45-47` comment goes stale; `support_lex`'s
  denominator in any report is judged candidates only.
- For 2.4: the Phase 2 exit line says "both arms are independently switchable", but row 2.4 and
  the proposal mean the whole gate on/off. Fix the wording when 2.4 opens.

## Answered

- **A1. ✅ "yes", 2026-10-14.** Acceptance 1 was wrong (`impact.md` §3.4). The namespace search
  refuses the measured warranty case before the gate runs. Restated in `spec.md`: warranty =
  `MISS` with cause `null`, plus a synthetic case that reaches `SUPPORT`. Consequence: Phase 2
  exit clause 1 is met by the arms (2.1, 2.2), not by the cascade.

## Answered — the design review's ten questions (`review.md`, 2026-10-14)

**All answered "yes, as recommended" on 2026-10-14.** The table is kept as the record of what
was asked. Q1 and Q2 are the old A4 and A5.

| Q | Question | Answer |
| :-: | :--- | :--- |
| Q1 (A4) | Log `candidate_entry_id` and `candidate_sources` on every judged record? | **yes** (other: only `candidate_entry_id`; or nothing, with a doc-only rule) |
| Q2 (A5) | Does any `NOT_SCORED` record make a run inadmissible (new §H rule 10, one ERROR log line)? | **yes** (other: also a shutdown counter in `cmd/gateway`; or no) |
| Q3 | Add part (c), negative pairs, to the real-answer sample? | **yes** |
| Q4 (A2) | `NAMESPACE` before `SIMILARITY`? | **yes** |
| Q5 (D1) | Refuse with cause `NOT_SCORED` when the server sends no texts? | **yes** |
| Q6 (D2) | `NONE` when served, `null` when no candidate was judged? | **yes** |
| Q7 (D3) | Gate always on in 2.3; 2.4 adds one parameter to `Judge`? | **yes** |
| Q8 (A3) | Do dev-v0 logs count as "the first logged run" for the frozen rows? | **no**: the trigger is the first run on v1 |
| Q9 | Leave ADR-001's `latency_ms` sentence out of v0.13? | **yes** |
| Q10 | Add `refusal_cause` to the HTTP response now? | **no** (revisit in a demo pass) |

The first review finding to know about: on a support refusal the record pairs the candidate's
`source_overlap` with the **new** entry's `entry_sources`, so an offline Jaccard reads 1.0 on every
refusal (`review.md` F1). Q1 is what fixes it.

## Implementation record

### Step 1a (2026-10-14): questions frozen

`sample-questions.md`: part (a) 16 floor questions, part (b) the 5 `mu_hit.js` pairs, part (c) 6
negative pairs (4 same-namespace, 2 gate-alone). Built from the dev-v0 chunks quoted in the 2.1
trail's `design.md`; `data/` was not read.

**sha256 of `sample-questions.md`: `93bc8f43f239b1819ab3d641fa53501bdf2e3e9766a3a9d613f675974ebdc033`**
(recorded before any answer exists; any edit before the first run must record the new hash here and
say why, and none is allowed after). The author did not read the file before it was frozen; the
sample has not run, so there is still time to read it, and a change is allowed only until the first
answer is generated. The live test refuses to run if the file's hash is not this one.

### Step 1b (2026-10-14): starting point

- `git rev-parse HEAD`: `21e4f1b34c8afaea212a279c872c995ca163dbd5` (main). The trail and every edit
  below are uncommitted.
- `kern.memorystatus_vm_pressure_level`: **2** (urgent), swap 4253 MB of 5120 MB used, no Ollama model
  loaded. **Not run under level 2**: it is outside the yellow allowance and the sample would add the
  LLM (about 1.7 GB resident) and the embedding model.
- Pinning tests green at this HEAD, `go test -count=1 ./internal/reuse`: ok. These cover the
  stopwords, the tokenizer, the numeric rules R1–R9 and the unit list. From here on, any edit to
  them comes **after** the sample.

### Plan steps 2–8 (2026-10-14): what was built

- **Step 2** `reuse/cause.go` + `cause_test.go`. `BenchmarkJudge` (both arms, pinned paraphrase
  evidence, M1, not a measurement of the system): **about 29.6 µs/op, 20 408 B/op, 383 allocs/op**
  (the `/ai-review` re-ran it three times: 29.7 to 29.9 µs). `impact.md` §9 estimated about 30 µs and
  382 allocs. The 0.2 % of a Tier-2 request is still an inference, because the 16 ms it divides by has no
  `RUN_ID`.
- **Step 3** five fields in `telemetry/evallog.go`; tests in the new `cause_fields_test.go`.
- **Steps 4–5** `cascade.go`, `handler.go`. **All 44 pre-existing `httpapi` tests passed unchanged**
  after each step (`impact.md` §3: 0 expected). No existing test file was edited (`git diff --name-only`
  shows none).
- **Step 6** `cause_test.go`, `cause_seams_test.go`: 15 tests, then 3 more after `/ai-review` (18).
  The three seams are wrappers in the new file (`anyNamespaceStore`, `textlessRAG`, `zeroChunkRAG`);
  `harness_test.go` is untouched. `go test -count=1 -race ./internal/httpapi` passes.
- **Step 7** `mutation-check.py`: first **27 edits, 27 red** (one survivor on the first run, fixed:
  dropping the chunk IDs inside `CheckSupport`'s lexical call was masked because the other arm still
  reported "unscored"; `TestCheckSupportRunsBothArms` now pins each arm). After `/ai-review` the list is
  **31 edits, 31 red, 0 survivors**. The script's earlier note calling "pass the entry's source IDs"
  equivalent was **wrong** and is corrected (finding F3). It proves those 31 are caught, not that every
  edit is.
- **Step 8** `interfaces.md` v0.13, ADR-009 (`decisions.md`), `super-plan.md` (row 2.3 and the Phase 2
  progress line), `architecture.md`, `README.md`, and the stale code comments (`cascade.go`,
  `handler.go`, `types.go`, `support.go`, `support_numeric.go`, `rule.go`, `doc.go`).
- **Step 1c** `ragclient/support_sample_live_test.go` is written, compiles, and **skips** without
  `RAG_SEAM_ADDR` and `RAG_SAMPLE=1`. It reads the frozen question file and fails if its sha256 is not
  the one recorded above. **It has not been run.**

### Stale lines in `Final_Proposal.md` — for the author (the file is not edited)

| Line | Says | Now |
| :-: | :--- | :--- |
| 155 | the served Tier-2 decision is `sim ≥ τ ∧ namespace` only; the support gate is not built yet | served rule is `sim ∧ namespace ∧ support` since 2.3 (ADR-009); θ is still not in it (F-K) |
| 190 | % entering the cascade band is identical to a Tier-2 hit | it is the hit share **plus** the support refusals; compute it from `entered_band` alone |
| 226 | the list of `refusal_cause` values | adds `NOT_SCORED`; `null` = no candidate judged; `CONTAINMENT` is never written |
| 411 | the refusal rate counts a reuse "that similarity, namespace **and containment** had all accepted" | 2.3 logs refusals after similarity ∧ namespace only (F-K). Offline: `SUPPORT` among records with `source_overlap ≥ θ_run`, `NOT_SCORED` excluded; θ_run is not in `raw/` until the P1 manifest |

### The real-answer sample (plan steps 1c–1e): NOT RUN

Memory pressure was **level 2** (urgent) with 4253 MB of 5120 MB swap used (4428 MB at the end of the
turn), no model of mine loaded, when the sample was due. Level 2 is outside the yellow allowance, and the
sample loads the LLM (about 1.7 GB), so it was not started. Steps 2–9 do not need a model and ran first.
**Consequence: the gate is wired before `τ_s = 0.6` has been looked at on a real generated answer**, which
`design.md` §10 wanted the other way round. No rule was changed, so nothing depends on the order; but the
numbers are still owed, and `super-plan.md` and ADR-009 say so.

### `/ai-review` (2026-10-14): resolved

`contract-reviewer`: 0 High, 2 Medium, 5 Low (`review.md`, last part). All resolved or recorded; none is
left unresolved. Net changes: 3 more tests (`TestCauseIsNullOnEveryExitWithNoCandidate`,
`TestCauseEmptyNamespaceExitHasNoCauseAndRunsNoSearch`,
`TestCauseStaleServerWithAnUnprovenancedCandidateIsStillNotScored`); `mutation-check.py` is now **31
edits, 31 red, 0 survivors**; wording fixes in ADR-009, `super-plan.md`, `interfaces.md` and two code
comments. No frozen value was touched.

**For the author (outside what this item was unlocked for):**
- `Makefile:353`: the `support-check` comment says "the gate is not wired in yet".
- `Makefile` `demo` step 3 asserts nothing, so a gate refusal shows there as MISS, ambiguous with a filter
  fault. A one-line assertion or a note would fix it.
- `ragclient/support_live_test.go:26`: the header says "the gate is not wired into the cascade" (an
  existing test file, immutable without an RCA).
- `Final_Proposal.md` lines 155, 190, 226, 411 (the table above).

## Status (2026-10-14, end of the implementation turn)

- Done: `SCOPE` (L), `spec.md`, `impact.md`, `design.md` (rev 2), `review.md` (design review + `/ai-review`),
  `plan.md`. Approved by the author: impact, contract, experiment, implementation (2026-10-14).
- **Built and verified:** plan steps 1a, 1b, 2, 3, 4, 5, 6, 7, 8, 9 (except `make support-check`).
  `make verify` exit 0; `go test -count=1 -race ./...` passes; `TestNoThetaSeparatesTheMeasuredPair` and the
  2.1 and 2.2 Done-when tests pass unchanged; 31 hand mutants, 31 red. Nothing is committed.
- **Open: plan steps 1c–1e, the real-answer sample.** The test is written, hashed to the frozen question
  file, compiles, and skips. It has not run because memory pressure is level 2 (swap 4428 of 5120 MB).
  To run it (after reading `sysctl kern.memorystatus_vm_pressure_level` and closing apps):
  start `rag.server` on a free port, then
  `RAG_SEAM_ADDR=127.0.0.1:<port> RAG_SAMPLE=1 go test -count=1 -timeout 30m -v -run '^TestSupportSample$' ./internal/ragclient/ | tee sample-results.md`
  from `gateway/`. Then fill the table in step 1d here and send it to the author.
- **Closed by `/done` the same day**, at the author's word, with the sample deferred. `READY_TO_IMPLEMENT` was
  deleted and the gate re-locked. The sample still blocks closing Phase 2.
