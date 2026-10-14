# Spec — support-gate switch (super-plan item 2.4)

## Change, in one sentence

Let each gateway run choose whether the support gate is **on or off** (`SUPPORT_GATE=on|off`), and make
every evaluation record say which one it was, so that configuration 4 can be run and compared as two
arms: gate off and gate on.

## Phase and item

Phase 2, item 2.4 in `docs/super-plan.md`:

> **Both arms switchable per run**, since configuration 4 is two arms rather than one.
>
> Done when: `support_gate` in the run manifest selects the arm, and the off-arm writes `null` for
> both support fields.

Unblocked by 2.2 (done). It also needs 2.3, which is done and is the code this changes. It serves
Phase 2 exit clause 3 ("both arms are independently switchable and both are recorded per request").
Item 2.3 already did the "recorded" half. Discharges **C1** and **C3**. `requirements.md` is
still empty, so there is no `FR-xx` / `NFR-xx` / `RR-xx` to cite.

Why it matters: `Final_Proposal.md` §9.2 reports the gate as an **on/off ablation arm** on the same
frontier, and its second pre-registered null (the gate refuses so much that the hit rate collapses)
can only be shown by running the off-arm. Phase 4's completeness check also needs the off-arm
(ADR-009, forward note).

## What the row says, and what is not true today

Two words in the row do not match the code, so 2.4 is a little more than a flag.

1. **There is no run manifest.** `super-plan.md` P1 says the manifest schema "exists nowhere". The
   gateway is configured by environment variables (`CONFIG_ID`, `MUTATION`, `REUSE_TAU`, …) and
   `experiments/k6/ask.js` only prints values "for manifest.yaml". So "`support_gate` in the run
   manifest" cannot be met literally. 2.4 does not build the manifest (that is P1, and it is
   larger). See D1.
2. **After 2.3, a null does not name the off-arm.** §H v0.13 says the two support fields are `null`
   on many records (refused before the gate, `NOT_SCORED`, no candidate). So a run with no served
   Tier-2 hit cannot be told gate-on from gate-off by the support fields. Only the cause `NONE`
   records can. A log must say which arm it is. See D2.

## Decisions for the author

Recommended; confirmed at `/approve`. They stay changeable until `design.md` is written.

- **D1. Where the switch lives.** Recommended: an environment variable **`SUPPORT_GATE`**, read in
  `cmd/gateway/main.go` like `CONFIG_ID` and `MUTATION`. Values are exactly `on` or `off`; unset
  means `on`; anything else stops the gateway at start (no silent fallback). The startup log says
  which arm is running. The row's "run manifest" then reads: *the manifest P1 defines will record
  this variable*. Other option: write a minimal manifest file now (rejected: it is P1's work and
  decides the shape of every later run).
- **D2. Does every record carry the arm?** Recommended: **yes**. A required key `support_gate`
  (`"on"` | `"off"`) on **every** record, set where `config_id` and `mutation` are set. This is §H
  v0.14 and an ADR. Reason: `raw/` is write-once, and without the manifest the log is the only
  durable record of the arm (the ADR-009 lesson: a field not logged now is missing from every run).
  Other option: no new key and rely on the future manifest (rejected: the log alone could not name
  its arm).
- **D3. What "both arms switchable" means.** Recommended: **the whole gate on or off.** The row, the
  proposal and 2.3's follow-up all mean that. The Phase 2 exit line says "both arms are independently
  switchable", which can be read as lexical and numeric each switchable, so its wording is fixed in
  `super-plan.md`: *the gate is switchable per run, and both of its arms are recorded per request*.
  Other option: three or four modes (lexical only, numeric only). Not recommended: it adds a mode
  nothing in the plan needs, and on a gate-on run the two logged values already show what each arm
  alone would have refused (not exactly: a different refusal leaves a different cache behind).
- **D4. The shape of `Judge`.** Item 2.3's answer Q7 was: add **one parameter to `Judge`**, no
  second code path. That changes the signature, and `reuse/cause_test.go` calls `Judge` at 5 places.
  Tests are immutable unless the author confirms. Recommended: add the parameter, and the author
  confirms a **compile-only** edit of those 5 call sites (they pass the gate as on; no assertion
  changes). Reason: every caller must state the gate, so a forgotten one is a compile error and
  cannot silently ignore the switch. Other option: keep `Judge` as a thin wrapper that always means
  "on" and add a second entry point. That needs no test edit, but production code that calls the
  wrong one skips the switch with no error.

## Acceptance

Checks that can be run. Handler checks use fakes (no Redis, Ollama or Python), as in
`httpapi/ask_test.go` and 2.3's `cause_test.go`.

1. **Parsing.** `SUPPORT_GATE` unset gives on; `on` gives on; `off` gives off; `ON`, `0`, `true`,
   `""` set explicitly, and any other value are refused at start. A pure function, tested like
   `retiredEnv`.
2. **Off-arm through `Ask`.** The same seeded fixtures 2.3 uses for a `SUPPORT` refusal (one that
   only the lexical arm refuses, one that only the numeric arm refuses): with the gate **on** each
   is a MISS with cause `SUPPORT`; with the gate **off** each is a `TIER2_HIT` with cause `NONE`,
   `support_lex: null`, `support_numeric_ok: null`.
3. **The off-arm does not run the gate.** `Judge` with the gate off, given evidence that the gate
   would refuse, returns `NONE` and no support result (`Support == nil`). A test cannot tell "not run"
   from "run and discarded", so the rest is shown by reading the code (`design.md` §10, the known
   equivalent edit).
4. **Judge agrees with `DecideLane` on both values.** *(Reworded after `impact.md` §2, A1.)* The
   existing `TestJudgeAgreesWithDecideLane` stays compile-only (gate on). A **new**
   `TestJudgeAgreesWithDecideLaneGateOff` covers every input the old one covers: cause is `NONE`
   exactly when the lane rule reuses, `Support == nil` always, never `SUPPORT` or `NOT_SCORED`, even
   with refusing evidence and nil texts.
5. **Causes before the gate are the same on both arms.** `NAMESPACE`, `SIMILARITY` and `null`
   (no candidate, zero chunks) are identical with the gate on and off.
6. **Every record names the arm.** `support_gate` is present on every exit of `Ask` that writes a
   record: Tier-1 lookup error, Tier-1 hit, Tier-2 hit, MISS, SHED, ABANDONED, GENERATION_FAILED. (The
   405 and 400 exits write no record, and did not before.) A test reads the `requests.jsonl` the
   logger wrote. The key has no `omitempty`.
7. **A new invariant, checked offline.** `support_gate == "off"` implies both support fields are
   `null` and the cause is never `SUPPORT` or `NOT_SCORED`. I5 in §H is restated to say so.
8. **Safe zero value.** A `Handler` built as a struct literal, as the test harness does
   (`httpapi/harness_test.go:752`, which every `Ask` test goes through), runs with the gate **on**. A
   test fails if a zero value turns it off.
9. **Regression.** `TestNoThetaSeparatesTheMeasuredPair` passes; the 60 `httpapi` tests (44 from
   before 2.3, 16 from 2.3) and the `reuse` tests pass unchanged apart from the D4 call-site edit; `make verify` exits 0 with `ruff`
   on `PATH`. 2.3's 31 hand mutants are still caught, and new mutants for the switch are caught
   (default flipped to off; off-arm still calls the gate; the key missing on one exit; the key
   written as the wrong arm). `mutation-check.py` matches the text of the `Judge` call, so the new
   `Judge` parameter goes **first** (the old pattern still matches), or the script is copied into
   this trail with new patterns. The closed 2.3 trail is not edited (`impact.md` §2).
10. **Docs agree.** `interfaces.md` v0.13 → v0.14 (§H key, the null rule, I5, a new arm invariant, the
    refusal-rate filter on `support_gate == "on"`, and the reading rule for old logs: **no
    `refusal_cause` and no `support_gate` = before 2.3, neither arm; `refusal_cause` present and no
    `support_gate` = gate-on, hard-wired by 2.3**; see `impact.md` §3, which corrects an earlier
    wording of this line that called every log without the key gate-on); an
    ADR in `decisions.md`; `super-plan.md` row 2.4 `✅ Done`, the Phase 2 progress paragraph, and the
    exit-line wording (D3); `architecture.md` and `README.md` only where they state the served rule.

11. **The cold-start check (rule 11, added after the design review).** A test helper implements the
    invariant I9 of `design.md` §6: every `entry_id` on a hit record and every `candidate_entry_id`
    equals the `entry_id` of some MISS record in the same log (compared as sets). It passes on a run
    whose entries were all written by its own MISS records, and it fails, naming the id, when a request
    hits an entry that was seeded into the store directly. The invariant I7 and the refusal-rate
    denominator also filter on `config_id ∈ {4, 5}` (`design.md` §6).

## Out of scope

- The run manifest (P1). 2.4 adds a variable and a log key, not a manifest.
- Switching the lexical and numeric arms separately (D3).
- **Shadow scoring on the off-arm** (computing and logging the gate's verdict without enforcing it).
  The Done-when says `null`. It would give a free "what the gate would have refused" column, but it
  puts gate code on a path labelled gate-off, and it is a different measurement.
- A runtime switch: no HTTP endpoint, no signal. The arm is fixed for the life of the process.
- Checking `SUPPORT_GATE` against `CONFIG_ID`. `ConfigID` selects nothing today (super-plan F-K), so
  a check would be ahead of the code. Configuration 5 is defined with the gate on; a run that sets
  both is the operator's to avoid until F-K has an owner.
- The real-answer sample (2.3's acceptance 10). It is still open, it still blocks closing Phase 2,
  and 2.4 does not change it or run it.
- θ in the served rule (F-K), configuration 3's path, a second candidate, any change to `τ_s`, the
  stopword list, the numeric rules or the unit list.
- Any ML on the hit path, and anything from the do-not-reinstate list.

## Open for the design

Not decisions for the author yet; `design.md` must settle them.

- How the zero value stays "on" (a field named for the off state, or a constructor that sets it).
- Whether a configuration-4 run is now identified by `(config_id, mutation, support_gate)`.
  `CLAUDE.md` says a run is identified by `(config_id, mutation)`; the new ADR must say what changes
  and what it invalidates.
- Whether the Makefile needs an edit. `make dev SUPPORT_GATE=off` should reach the gateway through
  the environment with no edit; the design confirms it, because the Makefile is not unlocked.
- **Cache carried between arms** (`impact.md` §5, risk 6). Tier-1 promotion writes answers that no
  gate checked into Redis on the off-arm, and they outlive the process. A later gate-on run serves
  them as Tier-1 hits. The experiment phase decides the rule (recommended: a run starts with `t1:`,
  `t2:` and `lru:` flushed).
- **A stale RAG server on the off-arm is invisible** (`impact.md` §4, risk 7). Decide whether to fire
  the existing one-time ERROR line on "chunk IDs, no texts" on both arms (an instrument check, no
  decision changes), or only state the blind spot in §H. For `design-reviewer`.
- How the parser tells unset from empty (`os.LookupEnv`), and that it runs before `telemetry.Open`, so
  a bad value cannot burn a `RUN_ID`.
- Edits to the author's files (`CLAUDE.md:202-203`, `Final_Proposal.md:391`: the run identity)
  wait for the author's OK; they are not part of this task's unlocked set.
- The branch: the author chose to work on `item-2.3-refusal-cause-code`, which already holds 2.3's
  commit `94ed44b`. The pull request from this branch will therefore carry 2.3 and 2.4 together.
