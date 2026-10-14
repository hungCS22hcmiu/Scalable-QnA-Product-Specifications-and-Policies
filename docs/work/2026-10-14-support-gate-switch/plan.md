# Plan — support-gate switch (item 2.4)

Do nothing here until `/approve implementation` (which needs `/approve contract` and `/approve
experiment` first). Smallest change that meets `spec.md`. Design: `design.md` revision 2. All answers
are in (`approvals.md`, 2026-10-14): D1–D4, A1, A2, Q1–Q4, R1–R4, all "yes" as recommended. So:
`SUPPORT_GATE=on|off` (D1); a required `support_gate` key (D2); the whole gate on or off (D3); one
typed parameter to `Judge`, first, with a compile-only edit of its 5 call sites (D4); the existing
consistency test stays and a new `…GateOff` test is added (A1); the harness gets an additive edit
(A2, Q1); rule 11 is about the start state and checked by I9 (Q2, R1); joins name their arm (R2); the
`config_id ∈ {4, 5}` filter (R3); the startup line after the assignment (R4).

Files this plan may touch:
- **New:** `reuse/gate.go`, `reuse/gate_test.go`, `telemetry/support_gate_field_test.go`,
  `cmd/gateway/gate_env_test.go`, `httpapi/support_gate_test.go`; `mutation-check.py` (a copy of 2.3's)
  in this trail.
- **Edited, source:** `reuse/cause.go`, `httpapi/cascade.go`, `httpapi/handler.go`,
  `telemetry/evallog.go`, `cmd/gateway/main.go`.
- **Edited, existing tests, as confirmed by the author:** `reuse/cause_test.go` (the 5 `Judge` call sites,
  **compile-only**, `GateOn,` added as the first argument; no assertion changes) and
  `httpapi/harness_test.go` (additive: a field `offArm bool` on `harness`, and the `want` branch in
  `checkEveryRecord`; **the handler literal at `:752` is not edited**).
- **Edited, comments only:** `reuse/support.go`, `ragclient/retrieve.go`, `httpapi/types.go`.
- **Edited, docs:** `docs/contracts/interfaces.md`, `docs/decisions.md`, `docs/super-plan.md`,
  `docs/architecture.md`, `README.md`; this trail.
- **Not:** any other existing `*_test.go`, `cache/`, non-comment code in `ragclient/`, the `.proto`,
  `rag/`, the Makefile, `CLAUDE.md`, `Final_Proposal.md` (the author's files; stale lines are listed in
  `approvals.md` instead).

**Stop rules.** (1) If any existing test changes outcome, stop and run `/rca`; do not edit the test.
(2) If invariant I9 is not exact on a real harness log (step 4), stop and report to the author before
writing it into §H. (3) If a 2.3 mutant is not red, or the script reports SKIP, stop. (4) The memory
rule applies only if a step starts Ollama or `rag.server`: none of the required steps does.

## Step 0 — baseline

- [x] `cd gateway && go vet ./... && go test -count=1 ./...` green. Record `git rev-parse HEAD`. *(done: green; HEAD `94ed44b`)*
- [x] Copy `docs/work/2026-10-14-refusal-cause-code/mutation-check.py` to this trail. In the copy, add
  `"./cmd/gateway"` to the `go test` command (review N5). Run it on the **unmodified** tree: every 2.3
  mutant must be red. This is the baseline that step 7 compares against. *(done: 31 edits, 31 red, 0 survivors)*
- [x] Check: both results are written in `approvals.md`.

## Step 1 — `reuse/gate.go` (not wired)

Tests first, in `reuse/gate_test.go`:
- [x] `TestSupportGateZeroValueIsOn`: `Gate(0) == GateOn`; `GateOn.String() == "on"`;
  `GateOff.String() == "off"`; `Gate(7).String() == "invalid"`.
- [x] `TestParseGate`: `on` and `off` succeed; `""`, `ON`, `Off`, ` on`, `on\n`, `0`, `true`, `1` all
  return an error.

Then `reuse/gate.go`: `type Gate int` with `GateOn Gate = iota` first and `GateOff`; `String()`;
`ParseGate`. Standard library only.
- [x] Check: `go test -count=1 ./internal/reuse -run 'SupportGate|ParseGate'` green; `go list -deps` of
  `reuse` still shows nothing from this repository.

## Step 2 — `Judge(g Gate, …)`

Tests first, in `reuse/gate_test.go` (they do not compile until the signature changes):
- [x] `TestJudgeGateOffServesWhatTheGateRefuses`: the table of `TestJudgeCauses` with `GateOff`:
  `NAMESPACE` and `SIMILARITY` rows unchanged; every row that reached the gate is `NONE` with
  `Support == nil`, including nil texts and refusing evidence.
- [x] `TestJudgeAgreesWithDecideLaneGateOff` (A1): the full grid of the existing test, with refusing
  evidence and nil texts: `NONE` exactly when `d.Reuse`; `Support == nil` always; never `SUPPORT`,
  `NOT_SCORED` or `CONTAINMENT`; a zero `NamespaceDecision` is `NAMESPACE`.
- [x] `TestJudgeBothArmsAgreeBeforeTheGate`: over the grid, an on-arm cause of `NAMESPACE` or
  `SIMILARITY` is the same cause on the off-arm.
- [x] `TestJudgeUnknownGateRunsTheGate`: `Gate(7)` behaves as on.

Then `reuse/cause.go`: the new first parameter; after the `SIMILARITY` check and before `CheckSupport`,
`if g == GateOff { return Judgement{Cause: CauseNone} }`. **The gate-on body is not edited.** Update the
doc comments on `Judgement.Support` ("non-nil exactly when the gate ran") and on `Judge`.
- [x] Edit the 5 call sites in `reuse/cause_test.go` (lines 60, 90, 111, 121, 200): add `GateOn,` first.
  Nothing else in that file changes.
- [x] Check: `go test -count=1 ./internal/reuse` green, the existing tests' outcomes unchanged
  (stop rule 1). `httpapi` does not compile yet; step 4 fixes it.

## Step 3 — `telemetry/evallog.go`

- [x] Test first, `telemetry/support_gate_field_test.go`: `TestSupportGateKeyIsAlwaysWritten`: a zero
  `Record` renders `"support_gate":""` (the key is present).
- [x] Add `SupportGate string \`json:"support_gate"\`` after `Mutation` (no `omitempty`).
- [x] Check: `go test -count=1 ./internal/telemetry` green, existing tests unchanged.

## Step 4 — `httpapi`

Harness first (additive, Q1): in `harness_test.go`, a field `offArm bool` on `harness`, and in
`checkEveryRecord`

```go
want := "on" // the harness literal at :752 never sets SupportGate, so this is the zero value's label
if hs.offArm {
    want = "off"
}
rec.str("support_gate", want)
```

- [x] Tests, `httpapi/support_gate_test.go`, with helper `useGateOff()` (sets
  `hs.h.SupportGate = reuse.GateOff` and `hs.offArm = true`), `checkGateInvariants` (I7 with its
  `config_id ∈ {4, 5}` filter) and `checkColdStart` (I9):
  - `TestSupportGateZeroHandlerRunsTheGate`
  - `TestSupportGateOffServesWhatTheGateRefuses` (lexical-only and numeric-only fixtures, on then off)
  - `TestSupportGateOffDoesNotReadEvidence` (stale server: off serves `NONE` with null fields; on is
    `NOT_SCORED`)
  - `TestSupportGateOffCausesBeforeTheGateAreUnchanged`
  - `TestSupportGateKeyOnEveryExit` (both arms: Tier-1 lookup error, TIER1_HIT, TIER2_HIT, MISS, SHED,
    ABANDONED, GENERATION_FAILED)
  - `TestSupportGateInvariants`
  - `TestSupportGateColdStartInvariant` (passes on a run whose entries its own MISS records wrote; fails,
    naming the id, when a request hits an entry seeded straight into the store)
- [x] Then production: `Handler.SupportGate reuse.Gate` (documented "zero value = on") beside
  `ConfigID` and `Mutation`; `SupportGate: h.SupportGate.String()` in the `rec` literal at
  `handler.go:174`; `h.SupportGate` as the first argument at `cascade.go:171`; `supportSummary` says "gate
  off" when the arm is off. `NewHandler` and `tryTier2`'s signature are **not** changed.
- [x] Check: `go test -count=1 ./internal/httpapi` green. **The 60 existing tests (44 + 16) pass with
  unchanged outcomes**, and now each asserts `support_gate == "on"` on every record (stop rule 1).
- [x] **Stop rule 2.** `TestSupportGateColdStartInvariant` passes on a real harness log, including a
  coalesced follower and a Tier-1 promotion. If it does not, stop: report which record broke I9.

## Step 5 — `cmd/gateway/main.go`

- [x] Test first, `cmd/gateway/gate_env_test.go`: `TestGateFromEnv`: unset gives `GateOn`; `on`; `off`;
  set-but-empty is an error; `ON` is an error; the error names `SUPPORT_GATE` and the two allowed values.
- [x] `gateFromEnv(lookup func(string) (string, bool)) (reuse.Gate, error)`, called **right after
  `retiredEnv`** with `os.LookupEnv`; an error is `log.Fatalf("gateway: %v", err)`. Then
  `handler.SupportGate = gate` beside `handler.ConfigID`, and the startup line **after** it, printing
  `handler.SupportGate.String()` (design §4).
- [x] Check: `go test -count=1 ./cmd/gateway` green. *(done)* **Manual checks** (`main()` has no test): (a) the
  source order, by `grep -n` on `main.go`: `gateFromEnv` is before `redis.NewClient` and `telemetry.Open`;
  `handler.SupportGate =` is before the startup line; (b) `cd gateway && SUPPORT_GATE=bad go run
  ./cmd/gateway` exits non-zero at once, names the variable, and touches neither Redis nor
  `experiments/results/`; (c) `SUPPORT_GATE= go run ./cmd/gateway` is refused the same way.

## Step 6 — whole-gateway check

- [x] `cd gateway && go build ./... && go vet ./... && go test -count=1 ./...` green.
- [x] `go test -count=1 -race ./internal/reuse ./internal/httpapi ./internal/telemetry ./cmd/gateway`
  green. `gofmt -l gateway/` empty.
- [x] `TestNoThetaSeparatesTheMeasuredPair` and the item 2.1, 2.2 and 2.3 tests pass unchanged.

## Step 7 — mutants

- [x] Run the copied script with the 2.3 mutants only: all red, no SKIP (stop rule 3).
- [x] Add the 2.4 mutants of `design.md` §10, with patterns written against the code as implemented:
  `GateOn`/`GateOff` swapped; the off branch above the namespace check; above the similarity check;
  the off branch returning `Support: &sr`; `Judge` skipping the gate whenever `g != GateOn`; the
  `cascade.go` call passing `reuse.GateOn`; the record literal using a constant `"on"`; the record
  literal set after `tryTier2`; `omitempty` on `support_gate`; `gateFromEnv` reading empty as unset.
  Each must turn a test red. If one stays green, add a test and repeat.
- [x] Record the count in `approvals.md`. *(done: 47 edits, 47 red, 0 survivors or problems)* Known equivalent edit, not in the list: the off branch calls
  `CheckSupport` and discards it.

## Step 8 — documents

- [x] `interfaces.md` v0.14 exactly as `design.md` §6: the example JSON; the `support_gate` row with its
  reading table; the `support_lex`/`support_numeric_ok` and `entered_band` rows; I5 restated, and I7,
  I8, I9; the refusal-rate denominator and 6b (the sentence at `:623` gains "on the off-arm"); rule 10's
  clause; rule 11; the version row and `Current version`. §A, §B, §D and the `.proto` are unchanged.
- [x] `decisions.md`: **ADR-010** and its summary row, with `Invalidates:`; the frozen-table row at `:74`
  amended to the served rule per arm; the P1 row (`:84`) says the manifest records `SUPPORT_GATE` and
  takes the arm from the records. ADR-010 carries: the switch and key; the typed parameter; rules 11 and
  I9; the join paragraph (6b); the `k=1` repeat-share sentence; the Phase 7 probe-set sentence; the Phase 4
  reset note; the run identity, with `CLAUDE.md` and `Final_Proposal.md` left to the author; row 2.4's
  Done-when is met by the D1 reading, stated outright.
- [x] `super-plan.md`: row 2.4 `✅ Done`, its trail and ADR; row 2.3's blockers; the Phase 2 progress
  paragraph; the exit-line wording (D3); the Phase 4 note (the off-arm now exists); the F-K parenthetical.
  Do not restate the exit line's clauses beyond the wording fix.
- [x] `architecture.md` (`:168-170`, `:205`) and `README.md` (`:66-68`, `:160-162`): the gate is
  switchable.
- [x] Stale comments: `reuse/support.go:10`, `ragclient/retrieve.go:28-31`, `httpapi/cascade.go`
  (63-73, 76-80, 157-160), `httpapi/handler.go` (308-310, 563-571), `httpapi/types.go`.
- [x] `approvals.md`, lines for the author: `CLAUDE.md:202-203` and `Final_Proposal.md:391` (the run
  identity); `Makefile:353`; the stale I5 comment at `cause_test.go:385`; `make demo` step 3 (still no
  assertion).
- [x] Check: `grep -n "v0.13" docs/contracts/interfaces.md` leaves only history; `make check` reads
  consistently.

## Step 9 — verify and close

- [x] `make verify` exit 0 with `ruff` on `PATH` (`export PATH="$HOME/Library/Python/3.13/bin:$PATH"`),
  and nothing SKIPPED inside it. *(done: exit 0, 0 SKIPPED, `gofmt -l gateway/` empty)*
- [x] Optional, only if Redis is up and memory pressure is green: `make dev SUPPORT_GATE=off`, read the
  startup line, stop it. Not required. *(done in a lighter form: the built gateway binary run against the real Redis for 3 s with `SUPPORT_GATE` `off`, `on` and unset, no log, no models; the startup lines name the arm. `make dev` itself was not run: it also starts `rag.server`.)*
- [x] `/ai-review` *(done: no blocker; 4 findings, 2 fixed, 1 accepted, 1 recorded for the author; `review.md`, last part)*
- [x] `/done` *(run 2026-10-14 by the author's slash command; see Outcome)*. The outcome states what stays open: the real-answer sample (2.3's
  acceptance 10) still blocks closing Phase 2, and 2.4 does not run it.

## Do not

- Change a threshold, `τ_s`, a stopword, the tokenizer, a numeric rule or the unit list.
- Edit the gate-on body of `Judge`, any assertion in an existing test, or the handler literal at
  `harness_test.go:752`.
- Add a wrapper that keeps the old `Judge` signature, a `NewHandler` parameter, a response field, a
  `/stats` counter, a Redis marker key, a `CONFIG_ID` check, or shadow scoring on the off-arm.
- Edit `CLAUDE.md`, `Final_Proposal.md` or the Makefile.
- Tune anything to make a number look better.

## Outcome (2026-10-14, `/done`)

**Shipped.** The support gate has an on/off switch. `SUPPORT_GATE=on|off` (unset = on; anything else stops
the gateway before it opens Redis, the RAG connection or the evaluation log) chooses the arm of configuration 4
for a process. `reuse.Gate` (`GateOn` is the zero value) is the **first** parameter of `Thresholds.Judge`;
only `GateOff` skips the gate, and it does so after the namespace and similarity checks, returning cause `NONE`
with no support result. One field, `Handler.SupportGate`, feeds both the `Judge` call and the new required
record key `support_gate`, so the behaviour and its label cannot differ. `interfaces.md` **v0.14** (the key, its
reading table for old logs, invariants I5 restated and I7, I8, I9, the arm and configuration filter on the
refusal-rate denominator, *Joins name their arm*, rule 10 on the gate-on arm only, run rule 11), **ADR-010**,
the frozen-table row for the refusal cause amended to the per-arm rule, the P1 row, `super-plan.md`
(row 2.4, the Phase 2 progress paragraph and exit-line wording, notes carried into Phases 4, 6 and 7),
`architecture.md` and `README.md`. 18 new tests (`reuse` 6, `telemetry` 2, `cmd/gateway` 2, `httpapi` 8).
The 60 existing `httpapi` tests pass with unchanged outcomes and now each asserts `support_gate == "on"` on
every record. Existing tests edited, as the author confirmed: `reuse/cause_test.go` (5 call sites,
compile-only) and `httpapi/harness_test.go` (additive: `offArm` and a `wantGate` branch; the handler literal
untouched). **47 hand mutants, all caught** (the 31 of 2.3 and 16 new). `make verify` exit 0, nothing SKIPPED;
`-race` green on the four changed packages; `gofmt -l gateway/` empty.

**Deferred or open.**
- **The real-answer sample (2.3's acceptance 10) still has not run, and still blocks closing Phase 2.** Memory
  pressure read **level 2** again at close. 2.4 neither runs nor changes it.
- **`main()` has no test** (design F14, accepted at `/ai-review`, finding 3). Mitigated by printing the
  startup line from the handler's field after the assignment, and the manual check was done; it must be
  repeated on any later change to `main.go`. Options to close it are in `review.md`.
- **I7, I8 and I9 exist as test helpers only.** No analysis code reads a finished log yet; they move to
  `experiments/scripts/` when Phase 5 starts.
- **Stale lines I was not allowed to edit** are in a table in `approvals.md`: `CLAUDE.md` (the run identity,
  "At v0.9", the line counts), `Final_Proposal.md` (lines 155 and 391), `Makefile:353`, and four comments in
  files outside the unlocked list or in immutable tests.
- **Two corrections to text approved at `/approve contract`**, made after `/ai-review` (I9's false F-J caveat;
  rule 11's `make demo-reset` example). They remove a false caveat and an unsafe example and change no rule,
  key or number; they are listed in `approvals.md` for the author to object to.

**Was the scope honest?** Yes. Opened at L: it changed `reuse/`, `interfaces.md` §H, `telemetry/` and what is
measured, and every one of those needed the review it got. Two findings for the ladder:
1. **A contract sentence that describes code behaviour was approved without being checked against the code.**
   The F-J caveat on I9 was written from memory, passed `/approve contract`, and was caught only by
   `/ai-review`. Suggestion: at `/approve contract`, each sentence of the diff that states what the code does
   is marked *verified* (with the line) or *inferred*, and an *inferred* one blocks the approval.
2. **The slash-command argument substitution is wrong.** `/task support-gate-switch L` rendered its first
   argument as "L" (the folder would have been `…-L`), and `/approve implementation start …` rendered the
   phase as "start". I used the real slug and phase by hand each time and said so. The templates in
   `.claude/commands/` should be checked.

**Contract and frozen values.** `interfaces.md` bumped v0.13 to v0.14. **Prior runs invalidated: none
citable** (`experiments/results/` holds only `.gitkeep`; no `requests.jsonl` exists). A log from the 2.3
commit `94ed44b` up to the 2.4 commit lacks `support_gate` and is **gate-on**; a log from before `94ed44b`
has neither key and is **neither arm**. No frozen value changed: `τ_s`, the stopwords, the tokenizer, the
numeric rules, the unit list and the cause strings and order are untouched. The refusal-cause row in
`decisions.md`'s frozen table was amended to the per-arm rule (its own trigger, the first run on `v1`, has not
happened). **A configuration-4 run is now identified by `(config_id, mutation, support_gate)`**; `CLAUDE.md` and
`Final_Proposal.md` still say `(config_id, mutation)` and wait for the author.

**Phase 2 exit line, run concretely (2026-10-14): NOT closed.**
1. *refuses the measured warranty case and admits the measured paraphrase*: the arms do it on the pinned texts
   (`TestSupportLexicalSeparatesTheMeasuredPair`, `TestNumericMeasuredPair`, `TestNumericDoneWhen` PASS) with an
   authored cached answer. Through `Ask` the namespace search refuses the warranty case first, so it is a MISS
   with cause `null` (`TestCauseWarrantyCaseIsNullBecauseTheNamespaceHoldsNothing` PASS) and the paraphrase is a
   `TIER2_HIT` with cause `NONE` (`TestCauseServedHitIsNoneWithBothArms` PASS). Whether that meets the clause
   is still the author's call (ADR-009).
2. *every Tier-2 refusal carries a cause code*: **met** (`TestCauseOfflineReading`,
   `TestCauseIsNullOnEveryExitWithNoCandidate`, `TestJudgeAgreesWithDecideLane` PASS).
3. *the gate is switchable per run and both of its arms are recorded per request*: **met**
   (`TestSupportGateOffServesWhatTheGateRefuses`, `TestSupportGateKeyOnEveryExit`, `TestSupportGateInvariants`,
   `TestGateFromEnv` PASS; `support_gate` is written in `gate.go`, `handler.go`, `evallog.go` and `main.go`;
   `support_lex` and `support_numeric_ok` are recorded as before, null on the off-arm).
4. *the decisive-similarity regression still reproduces*: **met** (`TestNoThetaSeparatesTheMeasuredPair` PASS).

So three clauses are met, clause 1 depends on the author's reading, and the phase stays open on the
real-answer sample.

**Follow-ups worth a task.**
1. **Run the real-answer sample** (`/investigate`, no code) when memory pressure allows. It blocks Phase 2.
2. **The author's edits:** the run identity in `CLAUDE.md:202-203` and `Final_Proposal.md:391`, and the rest of
   the table in `approvals.md`.
3. **Decide whether to close the `main()` wiring gap** (`review.md` finding 3, options a and b).
4. **F-K still has no owner** (θ is not in the served rule, so `CONTAINMENT` is never written), and with it
   what configurations 1–3 write for `support_gate` (recommended: `off`).
5. **Carried forward, not blocking:** P1's manifest records `SUPPORT_GATE` from the records; Phase 4 defines the
   cache reset that rule 11 needs and runs its completeness check on the off-arm; Phase 6 reports per arm and
   uses the 3 ⋈ 4-off join; Phase 7 compares μ_hit with the gate on against off on a probe set the gate
   admits; analysis scripts for I7, I8 and I9 when `raw/` analysis begins.

**Suggested commit** (not run). The branch `item-2.3-refusal-cause-code` already holds the 2.3 commit
`94ed44b`, so a pull request from it carries both items.

```
Item 2.4: switch the support gate on or off per run, and name the arm in every record

SUPPORT_GATE=on|off picks the arm of configuration 4 for a gateway process. reuse.Gate is the first
parameter of Judge; one Handler field feeds the call and the new required support_gate record key.
interfaces.md v0.14, ADR-010. No citable run is invalidated.

Not done: the real-answer sample from 2.3 (still blocks Phase 2); CLAUDE.md and Final_Proposal.md
still name the run identity (config_id, mutation).

Task: docs/work/2026-10-14-support-gate-switch/  (scope L)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
```
