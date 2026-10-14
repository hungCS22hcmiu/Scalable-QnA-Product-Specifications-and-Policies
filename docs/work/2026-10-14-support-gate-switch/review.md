# Review — support-gate switch (item 2.4), of `design.md` revision 1

Written by the opus `design-reviewer` subagent on 2026-10-14 and saved by the main session. The main
session re-checked five claims against the code (S1's `entry_id` path, S3's `Final_Proposal.md:397`, S4's
line order, N2's flush tool and N5's script command; marked ✔). Everything else is the reviewer's reading
with its file and line; anything it inferred is marked *inferred*. The reviewer did not edit any file.
Baseline it ran: `go vet ./...` and `go test -count=1 ./...` in `gateway/` were green.

## Verdict

**The code design is sound. Approve it as it is.** The `Judge` change, the `Gate` zero value, the single
`Handler.SupportGate` field, the record key and the parser order are correct against the real code. **No
blocker.**

**The contract text needs four edits before `/approve contract`.** They fix three silent paths and one
wrong claim. Each is one sentence of text, or one line moved in `main.go`:

- S1: rule 11 says its check is impossible. It is possible.
- S2: *decisions changed by provenance* does not say which configuration-4 arm it uses.
- S3: "configurations 1–3 write `on`" conflicts with I7 once configuration 3 exists.
- S4: the startup line can say OFF while the process runs ON.

## Findings, silent first

### S1. should-fix (contract). Rule 11's check is possible today, from `raw/` alone.

The design said a cross-arm cache cannot be checked from `raw/` until P1's manifest exists. That was
reasoned, not measured, and it is false. An `entry_id` is minted once, on a miss (`handler.go:419` ✔).
Both tiers store it (`:436-458`), Tier-1 promotion keeps it (`:343-354`), the MISS record logs it
(`:538` ✔, followers included), hit records log the stored id (`:209` ✔ TIER1_HIT, `:313` ✔ TIER2_HIT),
and `candidate_entry_id` logs it for every judged candidate (`:576`).

So on a cold start this holds: **every `entry_id` on a TIER1_HIT or TIER2_HIT record, and every
`candidate_entry_id`, equals the `entry_id` of some MISS record in the same `requests.jsonl`.** Compare
as sets, not in order: a hit can be logged before the MISS that wrote its entry. *Inferred* from reading
`handler.go`; verify it on a harness log during implementation.

- **Catches:** off-arm promotions served by a later on-arm process (the real false-hit hazard); the
  reverse direction, which inflates hit rate; a same-arm warm start (off then off), which rule 11 as
  written did not cover.
- **Misses:** old entries that are never touched but fill a bounded cache. Capacity is unbounded today.
- **Cost:** no code, no Redis access, so no conflict with ADR-007 or the `dep:` single-writer rule.

The arm that wrote a foreign entry can never be known, not even with P1. So the rule must be about the
**start state**, not the arm. Fix: reword rule 11 as "a measured run starts on a cache it wrote itself
(the static-cache arm, item 6.3, excepted)", and add the invariant above as the check.

### S2. should-fix (what a number means). The 3 ⋈ 4 join no longer says which arm.

*Decisions changed by provenance* is non-negotiable (`Final_Proposal.md:415`, `:595`), defined as
"3 vs 4, static arm", and `interfaces.md:623` says the namespace conjunct's effect "is counted by the
configurations 3 ⋈ 4 join". With two arms the meaning splits: **3 ⋈ 4-off is provenance alone; 3 ⋈
4-on mixes provenance and the support gate.** A join on `config_id` alone pools both arms and gives a
plausible wrong number. The proposal's cache-population argument (`Final_Proposal.md:456`) also applies
between the two arms: refusals cause different write-backs, so the caches drift apart. **A per-request
join between 4-off and 4-on is valid only on the static-cache arm.** Online, compare the arms in
aggregate only. Fix: one paragraph in ADR-010 and one sentence in §H. Nothing is lost if the join is
built later, because every record now carries `support_gate`.

### S3. should-fix (forward). "Configurations 1–3 write `on` and it means nothing there."

Configuration 3 is fixed-τ with no gate (`Final_Proposal.md:397` ✔). When F-K gives it a path, its
served hits will log cause `NONE` with null support fields. With the label `on` that **breaks I7's
on-clause in a healthy run**, and those rows would enter the new refusal-rate denominator with zero
refusals. The proposal limits the refusal rate to "4 (on-arm), 5" (`Final_Proposal.md:411`). Fix: every
rule that reads `support_gate` (I7's on-clause, the refusal-rate denominator, the per-arm metrics) also
filters `config_id ∈ {4, 5}`. What configurations 1–3 write is left to F-K's owner (recommended:
truthfully `off`, meaning the gate did not run).

### S4. should-fix (operator). The startup line may not describe the process.

The design printed `support_gate=…` before `handler.SupportGate = gate`. In `main.go` the `tau=` line is
at `:205` and the handler is built at `:268` ✔. If `main.go` parsed `SUPPORT_GATE=off` but forgot the
assignment, no test would catch it (`main()` is untested, and the mutant list had no such entry). The
process would print OFF and run ON, and the records would honestly say `on`, so I7 stays silent. A run
named `cfg4-off` would become a second on-arm run. Fix: print the line **after** the assignment and from
`handler.SupportGate`; add "`main.go` assigns the field" to the plan's manual checks; in the P1 forward
note say the manifest takes the arm from the records, or checks that the environment and the records
agree, and never from the environment alone.

### Notes

- **N1.** Q2's alternative (a `SCAN` guard when the off-arm starts) guards the wrong side: the false hits
  come from an **on-arm** process serving off-arm promotions. A guard at on-arm start would block every
  warm start. One more reason to use S1's offline check.
- **N2.** The flush tool exists: `python3 experiments/scripts/loadgen_footprint.py flush-cache` (`:558`,
  `:1066` ✔), or `make demo-reset`. Name it in the rule. After C2 the tool refuses whenever `dep:` or
  `entry:` exist, and deleting `t2:` alone would leave dependency sets pointing at nothing. So "never
  `dep:`/`entry:`" works only until Phase 4; say that Phase 4 defines the reset after that.
- **N3.** The Phase 7 forward note ("μ_hit with the gate on against off measures the gate's cost") is
  reasoned, not measured: the arms differ in hit mix and in the background writes each hit triggers
  (`BumpHitCount` plus the Tier-1 `Put`, `handler.go:320-354`). Fix: "on a probe set the gate admits, so
  both arms serve the same hits".
- **N4.** The `k=1` search inflates the on-arm's price (ADR-009's known limit: a refused entry stays the
  nearest and refuses each paraphrase in turn). Part of the gap between the arms' hit rates is this
  effect, and that gap is what the second pre-registered null reads. Fix: one sentence in ADR-010, and
  report the share of `SUPPORT` refusals whose `candidate_entry_id` repeats next to the gap.
- **N5.** The copied script runs `go test ./internal/reuse ./internal/httpapi ./internal/telemetry`
  (`mutation-check.py:101` ✔). The mutant "`gateFromEnv` reads empty as unset" lives in `cmd/gateway`, so
  it would report GREEN unless `./cmd/gateway` is added to that command.
- **N6.** Small inaccuracies in the design text:
  - §10 said `records(t)` runs on "every call of every test". Four tests never call it
    (`TestARealDisconnectIsRecordedAbandoned`, `TestRejectsBadMethodAndBody`,
    `TestEmptyNamespaceRunsNoSearch`, `TestCauseEmptyNamespaceExitHasNoCauseAndRunsNoSearch`); only the
    first writes a record, and `TestSupportGateKeyOnEveryExit` covers ABANDONED. Harmless.
  - The mutant row "runs the gate unless `g == GateOn`" reads inverted; the intended mutant is "skip the
    gate whenever `g != GateOn`".
  - Q4's reason: F6 relies on the *decision* not reading `Texts`; a log-only read would not break that.
    The real reason to skip the ERROR line on the off-arm is that it adds nothing there.
  - `type Gate int` accepts untyped constants, so `Judge(1, …)` compiles. "A caller has to say which one
    it wants" is too strong. Acceptable.
  - `checkCauseInvariants`' I5 comment (`cause_test.go:385`, "the gate-off arm of item 2.4 will relax the
    last") goes stale. Tests are immutable, so record it in the plan.

## Checked against the code and sound

- **`Judge` keeps 2.3's behaviour.** With the off branch after SIMILARITY (`cause.go:97-102`), a zero
  `NamespaceDecision` still gives NAMESPACE and NaN still gives SIMILARITY on both arms. `Served()` is
  unchanged.
- **The zero value means on everywhere.** `GateOn = 0`. The only production `Handler` is built at
  `main.go:268`; `NewHandler` leaves the field zero; the harness literal (`harness_test.go:752-763`) does
  not set it; there is no other `package main`.
- **The key is on every record.** One `Record` literal (`handler.go:174`), one `Log` call (`:193`). The
  405 and 400 exits (`:150-159`) return before the deferred emit. No other writer exists.
- **F6 is true in code.** The only non-test reader of `retrieved.Texts` is `cascade.go:171`. Write-back,
  promotion, coalescing, the answer store, `browse.go` and `types.go` never read it. One gap left: the RAG
  server's version is not recorded; that is P1's, and it is the same on both arms.
- **I7 holds on every on-arm path.** `NONE` comes only from a scored result (`cause.go:110`, then
  `handler.go:584-586`); Tier-1 records have a null cause; coalesced followers run their own `tryTier2`;
  a MISS after a refusal is never `NONE`.
- **I2′–I6 hold on the off-arm**, and `checkCauseInvariants` does not depend on the arm.
- **The widened A2 edit does not hide a flipped zero value.** The literal `"on"` does not depend on the
  field, and not editing the handler literal at `:752` is correct.
- **The 2.3 mutation patterns survive.** Each pattern at `mutation-check.py:38-84` still matches exactly
  once with the new parameter first.
- **The parser runs early enough.** `gateFromEnv` after `retiredEnv` (`main.go:144`) runs before
  `EnsureCacheIndex` (`:165`), before every `getenvFloat`/`getenvInt` `Fatalf` (`:176-246`), and before
  `telemetry.Open` (`:257`).
- **Scope is clean.** No frozen value changes, no cut scope returns, `reuse/` stays standard-library only,
  `telemetry/` imports nothing.

## Unknowns

**Settled by this review: design unknown 1 (the environment through `make` and `go run`).** On a scratch
Makefile with the same recipe shape and GNU Make 3.81: `make t SUPPORT_GATE=off` and
`SUPPORT_GATE=off make t` both reach a `go run` child as `off`; `SUPPORT_GATE=` arrives set and empty
(refused, as intended); `'SUPPORT_GATE=off '` arrives with the space (refused loudly). The real
`make dev` was not run, because it needs Redis.

**Still open:** whether S1's invariant is exact (inferred; verify on one harness log); design unknowns
2–6 stand.

## Questions the reviewer put to the author

1. Rule 11 becomes "every measured run starts on a cache it wrote itself (the static-cache arm excepted)",
   checked offline by the `entry_id` invariant. **Recommend yes.**
2. ADR-010 names the arm in each join, and limits per-request joins between the arms to the static-cache
   arm: 3 ⋈ 4-off for provenance; 4-off ⋈ 4-on on the static arm for the gate. State it now; build it with
   F-K. **Recommend yes.**
3. Every rule that reads `support_gate` also filters `config_id ∈ {4, 5}`, and the sentence
   "configurations 1–3 write `on`, meaningless" goes. **Recommend yes.**
4. The startup line is printed from `handler.SupportGate` after it is set, and P1's manifest takes the arm
   from the records. **Recommend yes.**

On the design's own questions: **Q1 agree. Q3 agree. Q4 agree** with the recommendation, for the reason in
N6. **Q2:** agree that nothing goes in code; disagree that the rule "cannot be checked" (S1), and disagree
with its alternative (N1).

## Resolutions (where `design.md` revision 2 handles each)

| Finding | Handled in design rev 2 | Needs the author |
| :--- | :--- | :--- |
| S1 | §6 item 7 (rule 11 reworded), new invariant I9, §10 test, §11 R1 | R1 |
| S2 | §6 item 6b, ADR-010 bullet, §7 | R2 |
| S3 | §6 items 2, 5, 6 (the `config_id ∈ {4,5}` filter) | R3 |
| S4 | §3, §4 (line printed after the assignment), §8 F14, ADR-010 P1 note | R4 |
| N1 | §11 Q2 (alternative dropped), §12 | — |
| N2 | §6 item 7 (tool named, Phase 4 note) | — |
| N3 | ADR-010 forward note, §7 | — |
| N4 | ADR-010 bullet, §7 | — |
| N5 | §10 (script command gains `./cmd/gateway`) | — |
| N6 | §10, §11 Q4, §2 (text corrections) | — |

---

# `/ai-review` of the implementation, 2026-10-14

Written by the `contract-reviewer` subagent on the working diff (9 modified files, 5 new Go files) and saved
by the main session. The main session re-checked findings 1 and 2 against the code before acting (marked ✔).
The reviewer edited no file.

## Verdict

**The code is clean against the contract. No silent failure and no wrong-number path in the Go code. No
blocker.** The reviewer ran `go vet`, `go test -count=1 ./...`, `gofmt -l`, `-race -count=3` on the four changed
packages, re-ran `mutation-check.py` (**47 edits, 47 red, 0 survivors**, matching the claim), and built the
gateway and ran it with `SUPPORT_GATE` set to `bad`, empty, `ON` and `off ` (each exits 1, names the variable
and both allowed values, creates no run directory). By hand it moved the label to after `tryTier2` (red) and
made the Tier-1 promotion mint a new `entry_id` (red, `TestSupportGateColdStartInvariant`).

Four problems, none in the running code: two false or unsafe sentences in the new contract text, the untested
wiring in `main()` (known), and a few stale comments.

## Findings, most severe first, and how each was resolved

### 1. CONFIRMED ✔. I9's second "limit" is false, and it weakens the check — **fixed**

`interfaces.md` I9, ADR-010 "Known limits" and `design.md` §6 item 5 said a MISS leader whose client left during
write-back (super-plan F-J) "can leave an entry that no record names", so a later hit on it is a false alarm.
The code says otherwise: the write-back closure (`handler.go:449-495`) only logs its errors and always returns
`&generation{... EntryID ...}, nil`, so the leader reaches `rec.Cache, rec.EntryID = cacheMiss, gen.EntryID`
(`handler.go:551`), and `TestACompletedGenerationIsStillAMissWhenTheClientHasLeft` (`abandon_test.go:192`) pins
that case as a MISS. F-J (super-plan.md:204) is a different fact (a Tier-1 entry with no Tier-2 record). Why it
mattered: I9 is the only guard for rule 11, and the sentence told an analyst to read an I9 hit as "probably F-J"
and dismiss it, which is the silent fault the rule exists to catch.

**Resolution.** The F-J limit is deleted from `interfaces.md` (I9), `decisions.md` (ADR-010) and `design.md`
(§6 item 5, §11 unknown 7). The one remaining false alarm is stated truthfully: a MISS record that never reached
the log (F-F, a request in flight at SIGTERM can vanish with `Dropped()` at 0). The first limit (old entries that
are never touched, which matters only once capacity is bounded) stays. **This is a correction to text the author
approved at `/approve contract`.** It removes a false caveat and changes no rule, no key and no number; it is
recorded in `approvals.md` under "Corrections made after `/approve contract`" so the author can object.

### 2. CONFIRMED ✔. Rule 11 recommends a command that breaks its own text — **fixed**

`interfaces.md` rule 11 said "never `corpus:` … for example by `flush-cache` or `make demo-reset`". `make
demo-reset` (`Makefile:164-203`) runs `FLUSHALL`, runs `git checkout -- data/` and re-ingests the corpus (it also
needs Ollama). That deletes `corpus:` and, after Phase 4, `dep:` and `entry:`. `loadgen_footprint.py flush-cache`
refuses to do that (`:541-545`, `:558-580`).

**Resolution.** Rule 11 now names only `loadgen_footprint.py flush-cache` and says why `make demo-reset` is not
an example (demos only). `design.md` §6 item 7 is corrected the same way. Same note in `approvals.md`.

### 3. CONFIRMED gap, known — **accepted**

Nothing tests the env-to-handler wiring in `main()` (`main.go:164-170`, `:298-315`): that `gateFromEnv` is
called, that it runs before `telemetry.Open`, that `handler.SupportGate = supportGate` is set, and which branch the
startup line takes. The reviewer's scratch mutants (the startup branch swapped; the assignment changed to
`reuse.GateOn` with `_ = supportGate`) passed the whole suite. Failure mode: an arm the operator meant as "off"
runs as "on", the records honestly say `on`, and I7 cannot see it.

**Why accepted.** This is design failure mode F14, planned in `plan.md` step 5 as a manual check, and it was
done (`approvals.md`, "Evidence from the implementation"). Mitigations already in place: the startup line is
printed **after** the assignment and **from the handler's field**, so a forgotten or wrong assignment prints
the wrong arm at start; plain deletion of the assignment does not compile (the variable would be unused); and
P1's manifest takes the arm from the records, not from the environment. The check must be repeated on any later
change to `main.go`. **Options if the author wants it closed:** (a) a small run-time self-check in `main()` that
re-reads the environment after the assignment and exits if the handler disagrees; (b) move the wiring out of
`main()` into a function the package can test. Both are beyond the approved design (design.md §4 and F14), so
neither was done.

### 4. CONFIRMED. Stale statements left in code — **recorded for the author**

- `reuse/support_numeric.go:15-16`: "The on/off switch is item 2.4." New with 2.4 (the same sentence in
  `support.go` was fixed). The file is **not** on the plan's comment-only list, so it is not edited; listed for
  the author.
- `httpapi/cause_test.go:386`, `Makefile:353`: already in `approvals.md`.
- `ragclient/support_live_test.go:26` and `ragclient/support_sample_live_test.go:4`: "not wired into the
  cascade", wrong since 2.3. Test files, immutable. **Added** to the author's table in `approvals.md`.

## Answers to the six questions (reviewer, summarised)

1. **Silent or wrong-number paths: none found.** One `Record` literal (`handler.go:182`), one non-test `Judge`
   caller (`cascade.go:175`) that receives the field that labels the record, the label sits before every exit
   that emits a record, the only non-test reader of `retrieved.Texts` is that `Judge` call, an unknown `Gate`
   value runs the gate and prints `invalid`.
2. **Code against contract:** field name, type, null rules, no `omitempty`, strings, constancy: all match. True
   against the code: the startup order, `gateFromEnv`'s behaviour, the `entry_id` flow, the cited line numbers.
   The only false claim was finding 1.
3. **Frozen values and imports: none changed.** `reuse` and `telemetry` import nothing from the repository;
   `reuse` gains only `fmt`.
4. **Tests: none vacuous.** One weak assertion: the "no NOT_SCORED alarm line" check in
   `TestSupportGateOffDoesNotReadEvidence` had no positive control. **Fixed:** the on-arm half of the same test
   now asserts exactly one alarm line, so the zero in the off-arm half can only mean "the line was not written
   here". What the 16 new mutants do not catch: the `main()` wiring (finding 3); the documented equivalent edit
   (the off branch runs `CheckSupport` and discards it, which matters only for the Phase 7 claim that the gate
   costs about 30 µs, a claim that rests on code reading; a benchmark under load gave 48 µs); the "label set after
   `tryTier2`" mutant is not in the script (run by hand by the reviewer, red); no mutant covers I7, I8 or I9,
   because they are test-local helpers and no analysis code exists yet.
5. **Docs:** no "always on" or "v0.13 as current" remains outside history. For the author only (`CLAUDE.md`
   and `Final_Proposal.md` were not edited): `CLAUDE.md:202-203` run identity; `CLAUDE.md:121` says
   `interfaces.md` is "At v0.9" (it is v0.14); `CLAUDE.md:32-33` file line counts are out of date;
   `Final_Proposal.md:391` the same run identity; `Final_Proposal.md:155` says "the support gate is not built
   yet", false since 2.3. All added to the author's table in `approvals.md`.
6. **Do-not-reinstate list and scope: none.** No manifest, shadow scoring, runtime switch, `CONFIG_ID` check or
   Makefile edit. `CLAUDE.md` and `Final_Proposal.md` untouched (mtimes checked).

## Plan compliance (reviewer)

The changed files match the plan's list exactly (`httpapi/types.go` was listed and needed no edit). Existing
tests were edited only as confirmed: `reuse/cause_test.go` (5 lines, `GateOn,` added) and `httpapi/harness_test.go`
(the additive `offArm` field and `wantGate` branch; the handler literal in `newHarness` is untouched). The 18 new
tests and 47 mutants match `approvals.md` and the super-plan row.

## Resolution summary

| # | Finding | Status |
| :-: | :--- | :--- |
| 1 | I9's F-J limit is false | **fixed** (`interfaces.md`, ADR-010, `design.md`); a correction after `/approve contract`, flagged |
| 2 | Rule 11 names `make demo-reset` | **fixed** (`interfaces.md`, `design.md`); same flag |
| 3 | `main()` wiring untested | **accepted** (F14, manual check done, mitigations listed); options (a), (b) for the author |
| 4 | Stale comments | **recorded for the author** (4 files outside the unlocked list) |
| note | Weak assertion, no positive control | **fixed** (`support_gate_test.go`) |
