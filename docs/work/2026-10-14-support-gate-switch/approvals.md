# Approvals — support-gate-switch

Scope **L** (`reuse/` is touched, §H changes, the measurement changes). Branch:
`item-2.3-refusal-cause-code`, by the author's choice.

| Phase          | Required    | Approved | When | ADR |
| :---           | :---        | :---     | :--- | :--- |
| impact         | L, M        | yes      | 2026-10-14 | — (the task changes a measured path and the §H contract, so it touches frozen state, but **no frozen value changes and no citable run is invalidated**: `experiments/results/` holds only `.gitkeep`, no `requests.jsonl` exists, and the item-1.6 footprint runs are older than 2.3 and already not comparable, `impact.md` §3. ADR-010 is required at the contract phase) |
| contract       | if §B/§D    | yes      | 2026-10-14 | **ADR-010** (reserved; written at `plan.md` step 8, and it must match `design.md` §6). Approves the `interfaces.md` v0.13 → v0.14 diff as described in `design.md` §6 revision 2: §H gains one required key, `support_gate` (`"on"` \| `"off"`, never null, no `omitempty`) with its reading table for old logs; the `support_lex`/`support_numeric_ok` and `entered_band` rows are reworded; I5 is restated and I7, I8, I9 are added, every reader of `support_gate` filtering `config_id ∈ {4, 5}`; the refusal-rate denominator gains `support_gate == "on"`; joins name their arm (6b); rule 10 gains its on-arm-only clause; rule 11 (a measured run starts on a cache it wrote itself, checked by I9) is added; the version row says a configuration-4 run is identified by `(config_id, mutation, support_gate)`. §A, §B, §D and the `.proto` are unchanged, and Python sends nothing new. **No citable run is invalidated**; a log from before the 2.3 commit `94ed44b` has neither key and is neither arm, and a log from `94ed44b` up to the 2.4 commit lacks `support_gate` and is gate-on. `CLAUDE.md` and `Final_Proposal.md` still say `(config_id, mutation)`: they are the author's files and are not edited by this approval |
| experiment     | if measured | yes      | 2026-10-14 | — (ADR-010 carries it). Approves the measurement change as described in `design.md` §7 revision 2: configuration 4 becomes two arms, and a run is identified by `(config_id, mutation, support_gate)`; on the off-arm the served Tier-2 rule is `similarity ∧ namespace`, so the Tier-2 hit rate, the tier mix (more Tier-1 promotions), the band share and *false hits by cause* move against the on-arm and are reported **per arm**, never pooled; the refusal-rate denominator is `SUPPORT` and `NONE` records with `source_overlap ≥ θ_run`, `support_gate == "on"` and `config_id ∈ {4, 5}`; *decisions changed by provenance* is the 3 ⋈ 4-off join, and a per-request 4-off ⋈ 4-on join is valid only on the static-cache arm; the second pre-registered null is read from the gap between the arms' hit rates, with the share of `SUPPORT` refusals whose `candidate_entry_id` repeats (the `k=1` effect) reported beside it; rule 11 and invariant I9 (a measured run starts on a cache it wrote itself); rule 10 checks the on-arm only, because the off-arm's result does not depend on evidence text; gate latency (about 30 µs per judged candidate, a benchmark, **not** a measurement of the system) is measured at Phase 7 as μ_hit with the gate on against off, on a probe set the gate admits; Phase 4's completeness run uses the off-arm. **No citable run is invalidated** (`experiments/results/` holds only `.gitkeep`, no `requests.jsonl` exists, and item 1.6's footprint runs predate 2.3 and are already not comparable). A log from before `94ed44b` is neither arm; a log from `94ed44b` up to the 2.4 commit is gate-on; two logs must not share a figure across those boundaries |
| implementation | always      | yes      | 2026-10-14 | **ADR-010** (written at `plan.md` step 8). Over `plan.md` steps 0–9 and `design.md` revision 2 as written, with the eight design and review answers in the ledger. The plan's own stops stand: any existing test that changes outcome stops the work for `/rca` (the test is not edited), invariant I9 not exact on a real harness log stops the work before it is written into §H, and a 2.3 mutant that is not red stops it. **No citable run is invalidated** (`impact.md` §3) |

Also required at scope L, and not in the template's table: `design.md`, `review.md` (opus
design-review), `plan.md`. **`design.md` revision 2 written 2026-10-14**, after the opus review
(`review.md`: sound, no blocker, 4 should-fix, 6 notes; all folded in). `plan.md` written 2026-10-14.
The design is not a phase the ledger approves; the contract, experiment and implementation phases below
are still open.

## Decisions D1–D4

Recommended in `spec.md`. **All four accepted as recommended, 2026-10-14** ("yes"). The first option
in each line is the accepted one. D4 includes the author's confirmation of a compile-only edit of
the 5 `Judge` call sites in `reuse/cause_test.go` (no assertion changes).

- **D1.** Switch is the env var **`SUPPORT_GATE=on|off`**, unset = on, anything else stops start · write a minimal manifest now.
- **D2.** Every record carries a required **`support_gate`** key (§H v0.14) · rely on the future manifest.
- **D3.** "Switchable" means the **whole gate on or off**; fix the Phase 2 exit wording · separate lexical-only and numeric-only modes.
- **D4.** Add one parameter to `Judge` and **confirm a compile-only edit of its 5 call sites** in `reuse/cause_test.go` · keep `Judge` as a wrapper and add a second entry point.

## Human decisions

| Date | Decision | Author's words | Invalidates |
| :--- | :--- | :--- | :--- |
| 2026-10-14 | **Open item 2.4 at scope L** (`/feature support-gate-switch`, raised to L because `reuse/` is touched), on the current branch `item-2.3-refusal-cause-code` | "investigate current codebase, progress on superplan, recent commit and open a task for phase 2.4 we will do this on this current branch" | — |
| 2026-10-14 | **D1–D4 accepted as recommended** (env var `SUPPORT_GATE`; required per-record `support_gate` key; whole gate on/off with the Phase 2 exit wording fixed; one parameter to `Judge`, with a compile-only edit of its 5 call sites in `reuse/cause_test.go` confirmed). Asked once as one question; the reply covered all four | "yes" | — |
| 2026-10-14 | **`/approve impact`** — `impact.md` accepted as the blast-radius analysis, including its correction of the old-log reading rule (`impact.md` §3). This approves the analysis only. It does **not** answer A1 and A2 (still open, below), it does not approve the contract or experiment phases, and it does not unlock source edits | — (slash command) | no citable run (`impact.md` §3) |
| 2026-10-14 | **A1 and A2 accepted as recommended.** A1: the existing `TestJudgeAgreesWithDecideLane` stays compile-only (gate on) and a new `TestJudgeAgreesWithDecideLaneGateOff` is added. A2: one line, `rec.str("support_gate", "on")`, is added to `checkEveryRecord` in `harness_test.go`. Both are confirmed test-file touches; they take effect only when `/approve implementation` unlocks them. Asked once; the reply covered both | "yes for A1 and A2" | — |
| 2026-10-14 | **Q1–Q4 and R1–R4 accepted as recommended** (A2 widened: an additive `harness_test.go` edit; no code enforces rule 11; the run identity goes to ADR-010 first; the stale-server rule is stated and tested, with no new check; rule 11 is about the start state and checked offline by I9; joins name their arm; the `config_id ∈ {4, 5}` filter; the startup line after the assignment). Asked once as one question; the reply covered all eight | "yes" | — |
| 2026-10-14 | **`/approve contract`** — the `interfaces.md` v0.13 → v0.14 diff in `design.md` §6 revision 2 accepted. This approves the contract change only. It does **not** approve the measurement change (`experiment`, still open), it does not edit `CLAUDE.md` or `Final_Proposal.md`, and it does not unlock source edits | — (slash command) | no citable run (`impact.md` §3) |
| 2026-10-14 | **`/approve experiment`** — the measurement change in `design.md` §7 revision 2 accepted, including rule 11 with invariant I9, the per-arm metric definitions, the refusal-rate filter and the joins naming their arm. This approves the experiment phase only. It does **not** unlock source edits: `/approve implementation` is still needed | — (slash command) | no citable run (`impact.md` §3) |
| 2026-10-14 | **`/approve implementation`** — unlocks, per `plan.md` steps 0–9: new `reuse/gate.go`, `reuse/gate_test.go`, `telemetry/support_gate_field_test.go`, `cmd/gateway/gate_env_test.go`, `httpapi/support_gate_test.go`, and `mutation-check.py` in this trail; edits to `reuse/cause.go`, `httpapi/cascade.go`, `httpapi/handler.go`, `telemetry/evallog.go`, `cmd/gateway/main.go`; the two confirmed edits to existing tests, `reuse/cause_test.go` (the 5 `Judge` call sites, compile-only) and `httpapi/harness_test.go` (additive: `offArm` and the `want` branch; the handler literal at `:752` untouched); comment-only edits to `reuse/support.go`, `ragclient/retrieve.go`, `httpapi/types.go`; and the doc rows in `interfaces.md`, `decisions.md`, `super-plan.md`, `architecture.md`, `README.md`. **Not** unlocked: any other existing `*_test.go`, `cache/`, non-comment code in `ragclient/`, the `.proto`, `rag/`, the Makefile, `CLAUDE.md`, `Final_Proposal.md`. Given after the impact, contract and experiment approvals. The author's words ask to execute all the steps; the main session reads that as steps 0–9 up to and including `/ai-review`, and holds `/done` for the author's own word, because `/done` closes the task and records the outcome | "start to execute all the steps" | no citable run (`impact.md` §3) |
| 2026-10-14 | **`/done`** — closes the task after `/ai-review` (no blocker; 2 fixed, 1 accepted, 1 recorded). Asked once ("shall I run `/done`?"); the author ran the slash command. The Phase 2 exit line was run concretely: three clauses met, clause 1 depends on the author's reading, and the phase stays open on the real-answer sample | — (slash command) | no citable run (`impact.md` §3) |

## Questions from the review (`design.md` §11, R1–R4) and from the design (Q1–Q4)

**All eight answered "yes", as recommended, 2026-10-14** (see the decisions table). Asked once as one
question; the single reply covered all eight. The first option of each is the accepted one.

The reviewer recommended yes to all four R-questions, and agreed with Q1, Q3 and Q4 below.

- **R1.** Rule 11 is about the start state: "a measured run starts on a cache it wrote itself (the
  static-cache arm excepted)", checked offline by invariant I9 over `entry_id`s. Replaces the revision-1
  claim that the check was impossible. Recommended: yes.
- **R2.** ADR-010 names the arm in each join: 3 ⋈ 4-off for provenance; a per-request 4-off ⋈ 4-on join
  only on the static-cache arm. Recommended: yes.
- **R3.** Every rule that reads `support_gate` also filters `config_id ∈ {4, 5}`. Recommended: yes.
- **R4.** The startup line is printed after the field is set and from it; P1's manifest takes the arm
  from the records. Recommended: yes.

### Q1–Q4 from the design (`design.md` §11)

Q2 is reworded in revision 2: no code enforces rule 11, and the `SCAN` alternative is dropped.
**Accepted: Q1** (the additive `harness_test.go` edit, with the handler literal at `:752` untouched),
**Q2** (no code enforces rule 11), **Q3** (ADR-010 first; the run-identity lines in `CLAUDE.md` and
`Final_Proposal.md` are the author's to edit, see the note below), **Q4** (state the stale-server rule in
§H and test it, no new check).

- **Q1.** Widen A2: an additive edit of `harness_test.go` (a field `offArm bool` and a 4-line `want`
  branch in `checkEveryRecord`; the handler literal at `:752` stays untouched), because a literal `"on"`
  fails every off-arm test. Recommended: yes.
- **Q2.** No code enforces rule 11 (reworded in revision 2; the rule and its offline check are R1).
  Recommended: yes.
- **Q3.** The run identity `(config_id, mutation, support_gate)` in `CLAUDE.md:202-203` and
  `Final_Proposal.md:391`: ADR-010 first, then the author edits those lines. Recommended: yes.
- **Q4.** A stale server on the off-arm: state it in §H and test it, no new check. Recommended: yes.

## Questions from the impact analysis (A1, A2)

Both touch test files, which are immutable unless the author confirms. **Both answered "yes" on
2026-10-14, as recommended** (see the decisions table above).

- **A1.** Keep `TestJudgeAgreesWithDecideLane` compile-only (gate on), and add a **new**
  `TestJudgeAgreesWithDecideLaneGateOff` · edit the existing test to run both values. Recommended: the
  new test. It matches D4 ("compile-only, no assertion changes"). Spec acceptance 4 is already reworded.
- **A2.** Add one line, `rec.str("support_gate", "on")`, to `checkEveryRecord` in `harness_test.go`
  (next to `config_id` and `mutation`) · leave the helper alone and write new per-exit tests.
  Recommended: add the line. It only tightens the check, and then every existing `Ask` test asserts the
  key and the safe zero value on every exit.

Also noted, not a question yet: the run identity in `CLAUDE.md:202-203` and `Final_Proposal.md:391`
becomes `(config_id, mutation, support_gate)` for configuration 4. Those are the author's files and are
not edited without the author's OK. ADR-010 will carry the change.

## Evidence from the implementation (2026-10-14)

- **Step 0, baseline.** HEAD `94ed44b`. `go vet ./...` and `go test -count=1 ./...` green. The 2.3 mutation
  script, copied into this trail with `./cmd/gateway` added to its test command, on the **unmodified**
  tree: 31 edits, 31 red, 0 survivors.
- **Steps 1–6.** 18 new tests: `reuse` 6, `telemetry` 2, `cmd/gateway` 2, `httpapi` 8. The **60 existing
  `httpapi` tests pass with unchanged outcomes**, and each now also asserts `support_gate == "on"` on every
  record (the additive harness edit). The existing `reuse` tests are unchanged apart from the 5 `Judge` call
  sites (each gained `GateOn,`). `go test -count=1 ./...` green; `-race` green on `reuse`, `httpapi`,
  `telemetry` and `cmd/gateway`; `gofmt -l gateway/` empty. `TestNoThetaSeparatesTheMeasuredPair`,
  `TestSupportLexicalSeparatesTheMeasuredPair`, `TestNumericDoneWhen` and `TestNumericMeasuredPair` pass.
- **Test files edited, as the author confirmed:** `reuse/cause_test.go` (5 lines, compile-only) and
  `httpapi/harness_test.go` (the `offArm` field and the `wantGate` branch in `checkEveryRecord`; the handler
  literal in `newHarness` was **not** edited).
- **Stop rule 2 (invariant I9) did not trigger.** `TestSupportGateColdStartInvariant` passes on a real
  harness log with a Tier-2 hit on a MISS's entry, the Tier-1 hit its promotion makes possible, a coalesced
  leader and follower, and a refused candidate. It fails, naming the entry, on a Tier-2 hit, a Tier-1 hit and
  a refused candidate that the run did not write. The review's inference about how `entry_id` flows
  (`design.md` S1) holds in the harness.
- **Manual checks of `main()`** (it has no test). Source order by `grep -n`: `retiredEnv` line 164,
  `gateFromEnv` 169, `redis.NewClient` 179, `ragclient.New` 181, `EnsureCacheIndex` 191, `telemetry.Open`
  283, `handler.SupportGate = supportGate` 301, the startup lines 307 onward. The built binary with
  `SUPPORT_GATE` set to `bad`, `` (empty), `ON` and `off ` (trailing space) exits 1, names the variable and
  both allowed values, and creates no run directory. With `off`, `on` and unset it gets past the parser;
  against the real Redis for 3 seconds (no log, no models) its startup line names the arm and the rule-11
  reminder. `make dev` itself was **not** run (it also starts `rag.server`).
- **Step 7, mutants.** 47 edits, **47 red, 0 survivors or problems**: the 31 of 2.3 and 16 new. One of the new
  ones (the zero value of `Gate` is off) is caught by **existing** tests as well, through the harness guard.
  Known equivalent edit, not in the list: the off branch calls `CheckSupport` and discards the result.
  Caught by the compiler and not in the script: forgetting `handler.SupportGate = supportGate` (the variable
  would be unused).
- **Step 9.** `make verify` exit 0 with `ruff` on `PATH`, 0 SKIPPED, `155 passed` in `experiments/tests` and
  `15 passed` in `rag/tests`.

## For the author — stale lines I did not edit

None of these needs the code to change. They are statements that are now wrong or incomplete.

| File | Line | What it says | What is true after 2.4 |
| :--- | :--- | :--- | :--- |
| `CLAUDE.md` | 202 | a run is identified by `(config_id, mutation)` | a configuration-4 run is `(config_id, mutation, support_gate)` (ADR-010); configuration 5 is gate-on |
| `docs/Final_Proposal.md` | 391 | the same sentence | the same |
| `Makefile` | 353 | "the gate is not wired in yet" | wired since 2.3, switchable since 2.4 (wrong since 2.3) |
| `gateway/internal/reuse/support_numeric.go` | 16 | "The on/off switch is item 2.4." (a comment) | the switch exists (`gate.go`). Comment only; not on the unlocked list |
| `gateway/internal/httpapi/cause_test.go` | 386 | "the gate-off arm of item 2.4 will relax the last" (a comment) | it does not relax anything: the off-arm never writes `SUPPORT`. Tests are immutable |
| `Makefile` | `demo` step 3 | asserts nothing (from 2.3) | unchanged |
| `gateway/internal/ragclient/support_live_test.go` | 26 | "not wired into the cascade" (a comment) | wired since 2.3. Test file, immutable |
| `gateway/internal/ragclient/support_sample_live_test.go` | 4 | "not wired into the cascade" (a comment) | wired since 2.3. Test file, immutable |
| `CLAUDE.md` | 121 | `interfaces.md` is "At v0.9" | it is v0.14 |
| `CLAUDE.md` | 32-33 | file line counts (`reuse` 732, `httpapi` 569, …) | out of date |
| `docs/Final_Proposal.md` | 155 | "the support gate is not built yet" | served since 2.3, switchable since 2.4 |

## Corrections made after `/approve contract` (from `/ai-review`) — for the author to object to

The contract diff in `design.md` §6 was approved as written. `/ai-review` found two sentences in it that were
**false or unsafe against the code**. Both are corrected, because the first one told an analyst to dismiss the
only alarm for rule 11. Neither changes a rule, a key, a null rule or a number. If you disagree, say so and I
revert the sentence; the earlier wording is in `design.md` revision 2's history and in `review.md`.

1. **I9's second limit** (`interfaces.md` I9, ADR-010 "Known limits", `design.md` §6 item 5 and §11): the text
   said a MISS leader whose client left during write-back (F-J) can leave an entry that no record names. It
   cannot: the write-back closure logs its errors and always returns the generation, so that record is still a
   MISS and still names the entry. The one real false alarm is a MISS record lost to F-F (shutdown with a
   request in flight).
2. **Rule 11's example command** (`interfaces.md` rule 11, `design.md` §6 item 7): the text named `make
   demo-reset` beside `flush-cache`. `demo-reset` runs `FLUSHALL`, restores `data/` and re-ingests, so it
   deletes `corpus:`, which the same sentence says never to touch. Now only `loadgen_footprint.py flush-cache`
   is named, and `demo-reset` is called demos-only.

## `/ai-review` result (2026-10-14)

`contract-reviewer`: no blocker, no silent failure in the running code (`review.md`, last part). 4 findings:
2 fixed (above), 1 accepted with reasons (`main()` wiring has no test; design F14; options for you in
`review.md` finding 3), 1 recorded for you (stale comments outside the unlocked list, in the table above). One
weak test assertion fixed (a positive control added to `TestSupportGateOffDoesNotReadEvidence`). The reviewer
re-ran the 47 mutants: 47 red.

## Recorded follow-ups carried in

- From 2.3 (`docs/work/2026-10-14-refusal-cause-code/approvals.md`): the Phase 2 exit line says "both
  arms are independently switchable" but means the whole gate on or off. Fixed when 2.4 closes (D3).
- From ADR-009: 2.4 adds one parameter to `Judge`, and the consistency test covers both values (D4).
- From ADR-009 and `super-plan.md` Phase 4: Phase 4's completeness run must use the gate-off arm
  that this item builds, or read `dep:*` and `entry:*` directly.
- **Still open from 2.3 and not part of 2.4:** the real-answer sample (`τ_s = 0.6` on generated
  answers). It blocks closing Phase 2. Memory pressure was level 2 when 2.3 closed.
