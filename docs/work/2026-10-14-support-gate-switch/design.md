# Design — support-gate switch (super-plan item 2.4)

Revision 2, 2026-10-14. Revision 1 was reviewed by the opus `design-reviewer` (`review.md`: sound, no
blocker, 4 should-fix, 6 notes). All design changes are in this revision. Written in plain English;
names, numbers and frozen values are exact. Inputs: `spec.md`, `impact.md` (approved), and the
author's answers D1–D4, A1 and A2 (`approvals.md`). Where this design needs the author again, it says
**[Q#]** (from revision 1) or **[R#]** (from the review); the questions are collected in §11 and were
**all answered "yes", as recommended, by the author on 2026-10-14** (`approvals.md`). The contract,
experiment and implementation phases are still not approved.

## Changes since revision 1

- **S1.** Rule 11 was wrong to call its check impossible. It is now about the **start state** ("a measured
  run starts on a cache it wrote itself"), checked offline by a new invariant I9 over `entry_id`s (§6
  items 5 and 7, §10) **[R1]**.
- **S2.** §6 item 6b and ADR-010 say which arm each join uses. A per-request join between the two
  configuration-4 arms is valid only on the static-cache arm **[R2]**.
- **S3.** Every rule that reads `support_gate` also filters `config_id ∈ {4, 5}`. The sentence
  "configurations 1–3 write `on` and it means nothing there" is removed (§6 items 2, 5, 6) **[R3]**.
- **S4.** The startup line is printed after `handler.SupportGate` is set, and from it (§3, §4). New
  failure mode F14, and a note for P1's manifest **[R4]**.
- **N1–N6.** The Q2 alternative is dropped; rule 11 names the flush tool and says Phase 4 redefines the
  reset; the Phase 7 and `k=1` notes are added to ADR-010; the mutation script also tests `./cmd/gateway`;
  four small text errors are fixed (§10, §11).

## 1. The design in one paragraph

A new small type, `reuse.Gate` (`GateOn`, `GateOff`), is passed as the **first parameter** of
`Thresholds.Judge`. Only `GateOff` skips the support gate; any other value runs it. The gateway reads
`SUPPORT_GATE` once at start (`on`, `off`, or unset meaning `on`; anything else stops the process
before it touches Redis or opens the log). The value lives in **one** field, `Handler.SupportGate`,
whose zero value is `GateOn`. That one field feeds both the `Judge` call and the new required record
key `support_gate`, so the behaviour and its label cannot come from two places. §H goes to v0.14 and
ADR-010 records the change. The off-arm returns cause `NONE` with no support result and null support
fields; every cause that comes before the gate (`NAMESPACE`, `SIMILARITY`, `null`) is the same on
both arms.

## 2. Decisions this design rests on

| # | Decision | Status |
| :-- | :--- | :--- |
| D1 | Env var `SUPPORT_GATE=on\|off`; unset = on; anything else stops start | **accepted** 2026-10-14 |
| D2 | Required per-record key `support_gate` (§H v0.14) | **accepted** |
| D3 | "Switchable" means the whole gate on or off; the Phase 2 exit wording is fixed | **accepted** |
| D4 | One parameter to `Judge`; compile-only edit of its 5 call sites in `reuse/cause_test.go` | **accepted** |
| A1 | `TestJudgeAgreesWithDecideLane` stays compile-only; a new `…GateOff` test is added | **accepted** |
| A2 | One line added to `checkEveryRecord` in `harness_test.go` | **accepted, but §10 shows it needs widening → [Q1]** |
| G1 | `Gate` is a typed integer, `GateOn = 0`, in a new file `reuse/gate.go`; the parameter is **first** | this design |
| G2 | One field, `Handler.SupportGate reuse.Gate`, zero value = on; it feeds the `Judge` call and the record label | this design |
| G3 | The parser is `reuse.ParseGate` (exact strings only) plus `gateFromEnv` in `main.go` using `os.LookupEnv`, called before `telemetry.Open` | this design |
| G4 | The record key is a plain `string`, `json:"support_gate"`, **no `omitempty`**, set in the `rec` literal where `config_id` and `mutation` are set | this design |
| G5 | The off-arm branch sits **after** the `SIMILARITY` check and **before** `CheckSupport` | this design |
| G6 | A stale RAG server on the off-arm is **not** a gap and gets no new check (§8, F6) | this design → reviewer to challenge |
| G7 | Cache state is a new run rule (rule 11): **a measured run starts on a cache it wrote itself**. It is an operator duty in code terms (nothing blocks a start), and it is **checked offline** by invariant I9 | this design, changed by review S1 → **[Q2], [R1]** |
| G8 | A configuration-4 run is identified by `(config_id, mutation, support_gate)`; configuration 5 is gate-on. Every rule that reads `support_gate` filters `config_id ∈ {4, 5}` | this design, changed by review S3 → ADR-010; `CLAUDE.md` waits for the author **[Q3], [R3]** |
| G9 | No Makefile edit, no §A response field, no `/stats` counter, no `NewHandler` parameter | this design |
| G10 | The startup line is printed **after** `handler.SupportGate` is set, and from that field | review S4 → **[R4]** |
| G11 | Joins name their arm: 3 ⋈ 4-off for provenance; a per-request 4-off ⋈ 4-on join only on the static-cache arm | review S2 → ADR-010 **[R2]** |

**Why `Gate` is a type and not a `bool`** (D4 said "one parameter"; the type is the safe form of it).
A bare `true` at a call site cannot be read without the signature, and a flipped meaning compiles. With
`reuse.GateOn` and `reuse.GateOff` a caller reads which one it wants, and a call that forgets the
parameter does not compile. (A `Gate` is an integer type, so an untyped constant such as `Judge(1, …)`
still compiles; a reviewer would catch it, and the compiler does not. Acceptable.) Only the exact value `GateOff` skips the gate, so a value nobody planned
for (a future constant, a corrupted int) **runs** the gate. The unsafe direction needs a deliberate
`GateOff`.

**Why the parameter is first.** The 2.3 mutation script matches the text
`"c.Entry.Answer, retrieved.Texts, retrieved.ChunkIDs)"` (`mutation-check.py:47-48`). With the new
parameter first, that text is unchanged and the script keeps working (`impact.md` §2).

## 3. Flow

```
main
 ├─ retiredEnv(...)                         (unchanged)
 ├─ gateFromEnv(os.LookupEnv)       [NEW]   error → log.Fatalf, BEFORE redis, ragclient, telemetry.Open
 ├─ ... redis, rag, embedder, thresholds, band, pool, capacity, telemetry.Open ...
 ├─ handler := NewHandler(...)
 ├─ handler.SupportGate = gate      [NEW]   beside ConfigID and Mutation
 └─ log "support_gate=<handler.SupportGate>"  [NEW]   one line, AFTER the assignment and read from the field (S4)

Ask
 ├─ rec := telemetry.Record{ ..., ConfigID, Mutation, SupportGate: h.SupportGate.String() }   [NEW]
 │       (the literal at handler.go:174, before any exit that writes a record)
 ├─ Tier 1 miss
 ├─ embed ‖ retrieve                       (unchanged)
 └─ tryTier2
      1-6  unchanged (zero chunks, namespace, one scoped search, DecideLane, band)
      7    h.Thresholds.Judge(h.SupportGate, NSDecision, sim, answer, texts, ids)   [first arg NEW]
      8    Served = (Cause == NONE)                                  (unchanged)
```

Step 7, inside `Judge` (new line marked):

```
nsOK := d.Match && (d.Rule != RuleComposite || d.LaneMatch)
!nsOK                    → NAMESPACE      (gate not run, either arm)
!(similarity >= t.Tau)   → SIMILARITY     (gate not run, either arm; NaN refuses)
g == GateOff             → NONE, Support nil          [NEW: the gate is not run]
sr := CheckSupport(...)                                (gate on)
!sr.Scored()             → NOT_SCORED
sr.Refuses()             → SUPPORT
otherwise                → NONE
```

The off branch is placed **after** the two checks so that a zero `NamespaceDecision`, a NaN
similarity and a wrong-namespace candidate are refused on both arms. It cannot turn them into `NONE`.

## 4. Function contracts

`reuse/gate.go` (new), standard library only:

```go
// Gate says whether the support gate runs. The zero value is GateOn, so a struct that never sets it
// runs the gate: a forgotten field must not switch the research arm.
type Gate int

const (
    GateOn  Gate = iota // 0: the gate runs
    GateOff             // the ablation arm: the gate is not run
)

// String is the value written to the record's support_gate key and printed at start.
// An unknown value gives "invalid", which §H calls a defect.
func (g Gate) String() string

// ParseGate accepts exactly "on" and "off". Not "ON", not "", not " on", not "true", not "0".
func ParseGate(s string) (Gate, error)
```

`reuse/cause.go`:

```go
func (t Thresholds) Judge(g Gate, d NamespaceDecision, similarity float64,
    answer string, texts, retrievedChunkIDs []string) Judgement
```

- `g == GateOff` returns `Judgement{Cause: CauseNone}` with `Support == nil`, after the namespace and
  similarity checks. Any other `g` runs the gate exactly as in 2.3. **The gate-on body is not
  edited**, so the 2.3 tests and mutants still describe it.
- The doc comment on `Judgement.Support` becomes "non-nil exactly when the gate ran" (it said "when the
  candidate cleared the lane rule and tau"). The comment on `Judge` gains the off line.
- `Served()` is unchanged: `Cause == NONE` is the only serve rule on both arms.

`httpapi/handler.go`: `Handler` gains `SupportGate reuse.Gate` (documented as "zero value = on"),
next to `ConfigID` and `Mutation`. The `rec` literal at `handler.go:174` gains
`SupportGate: h.SupportGate.String()`. `NewHandler` is **not** changed. `recordCause` is not changed:
with `Cause = NONE` and `Support = nil` it already writes `refusal_cause: "NONE"` and leaves both
support fields null (`handler.go:574-593`).

`httpapi/cascade.go`: the call at `:171` passes `h.SupportGate`. `tryTier2`'s signature does not
change (two tests call it directly). `supportSummary` prints "gate off" for a nil result when the arm
is off; this is a log line only.

`telemetry/evallog.go`: after `Mutation`, `SupportGate string \`json:"support_gate"\``. A plain
string: `telemetry` imports nothing from this repository.

`cmd/gateway/main.go`:

```go
// gateFromEnv: unset → GateOn. Set, even to "", → ParseGate, so SUPPORT_GATE= is an error, not "on".
func gateFromEnv(lookup func(string) (string, bool)) (reuse.Gate, error)
```

It is called right after `retiredEnv`, so a bad value stops the process before `telemetry.Open`
(`main.go:257`) creates a run directory. This avoids the F-M pattern, where `getenvInt("CONFIG_ID")`
fails after the run id is burned. `os.LookupEnv` is used because `getenv` (`main.go:30-35`) cannot tell
"unset" from "empty". The error names the variable and the two allowed values.

The startup line is printed **after** `handler.SupportGate = gate` (`main.go:273`, beside `ConfigID`),
**not** beside the `tau=` line at `:205`, and it prints `handler.SupportGate.String()` and not the
parsed variable (review S4). If the assignment were forgotten, the line would then say `on` and the
mismatch with the operator's `SUPPORT_GATE=off` would be visible. `main()` has no test, so "main.go
assigns the field" is a manual check in the plan.

```
gateway: support_gate=on   (default: a candidate that clears tau and the namespace is refused if the answer is unsupported by this request's evidence)
gateway: support_gate=OFF  -- the ablation arm: Tier-2 serves on similarity and namespace only.
         support_numeric/support_lex are not computed. A measured run starts on a cache it wrote itself: empty t1:, t2: and lru: first (interfaces.md rule 11).
```

## 5. What each state logs

`sim` = `similarity`. "–" means null. The new column is `support_gate`.

| State | `cache` | `refusal_cause` | `support_lex` / `support_numeric_ok` | `support_gate` |
| :--- | :--- | :--- | :--- | :--- |
| Any exit that writes a record | any | (as in 2.3) | (as in 2.3) | `on` or `off`, the process's arm |
| **On-arm**, served | TIER2_HIT | `NONE` | number / bool | `on` |
| **On-arm**, a support arm refuses | MISS… | `SUPPORT` | number / bool | `on` |
| **On-arm**, stale server | MISS… | `NOT_SCORED` | – / – | `on` |
| **Off-arm**, candidate cleared τ and the namespace | TIER2_HIT | `NONE` | – / – | `off` |
| **Off-arm**, stale server | TIER2_HIT | `NONE` | – / – | `off` |
| Either arm, below τ / alarm / no candidate | MISS… | `SIMILARITY` / `NAMESPACE` / – | – / – | the arm |

On the off-arm `entered_band` is true on every TIER2_HIT (and on a `NAMESPACE` alarm that cleared τ),
so it again equals the TIER2_HIT indicator, as it did before 2.3. Read band share **per arm**.

## 6. The contract diff, for `/approve contract`

`interfaces.md` v0.13 → v0.14, §H only. §A (the response), §B, §D and the `.proto` are unchanged: the
arm belongs to the process, not to the request. The seam has two sides here: Python sends nothing new
(the off-arm simply does not read `Texts`); Go writes one new key.

1. **Example JSON** (`interfaces.md:547-553`): add `"support_gate": "on",  // v0.14 — on|off` after
   `mutation`.
2. **New field row `support_gate`.** `"on"` or `"off"`, on **every** record, never null, no
   `omitempty`. The arm the gateway process ran. Meaningful for configurations 4 and 5 only, so
   **every rule below that reads it also filters `config_id ∈ {4, 5}`** (review S3). Configuration 3
   will have no gate and will log cause `NONE` with null support fields; if it were labelled `on`, I7's
   on-clause would fail in a healthy run. What configurations 1–3 write is left to the owner of F-K
   (recommended: `off`, meaning the gate did not run). Any other value, including `""`, is a defect. It
   is constant across a run. **Reading an old log**, by key presence, because logs carry no gateway SHA
   until P1:

   | `refusal_cause` key | `support_gate` key | Meaning |
   | :--- | :--- | :--- |
   | absent | absent | **Before the 2.3 commit `94ed44b`.** No gate, no zero-chunk guard, older meanings (ADR-009). **Neither arm.** Never read as gate-on, never pooled as an off-arm |
   | present | absent | **2.3 era**, `94ed44b` up to the 2.4 commit. Gate on, hard-wired |
   | present | `"on"` / `"off"` | Read the key |

3. **`support_lex` / `support_numeric_ok` row.** Replace the v0.13 sentences "*So `null` no longer
   identifies the gate-off arm on its own … rule 10 checks the gate-on arm only*" with: the arm is
   named by `support_gate`; null support fields are only a cross-check. On the off-arm the gate does not
   read evidence text, so a stale server cannot change what the arm serves, and rule 10 has nothing to
   check there (§8, F6).
4. **`entered_band` row:** one sentence: on the off-arm it again equals the TIER2_HIT indicator, apart
   from the `NAMESPACE` alarm.
5. **Invariants.**
   - **I5 restated:** `support_lex` and `support_numeric_ok` are both null or both non-null;
     non-null implies cause ∈ {`NONE`, `SUPPORT`}; cause `SUPPORT` implies non-null. (The v0.13
     parenthetical "until item 2.4's gate-off arm" is removed: the off-arm never writes `SUPPORT`, so
     nothing relaxes.)
   - **I7 (new), the arm:** `support_gate ∈ {"on","off"}` and constant across the run;
     `support_gate == "off"` ⇒ both support fields null and cause ∉ {`SUPPORT`, `NOT_SCORED`};
     `support_gate == "on" ∧ config_id ∈ {4, 5} ∧ refusal_cause == "NONE"` ⇒ both support fields
     non-null. This catches a run labelled with the wrong arm, whenever the run has at least one Tier-2
     hit or `SUPPORT` / `NOT_SCORED` record.
   - **I8 (new):** `config_id == 5` ⇒ `support_gate == "on"`. Configuration 5 is defined with the gate
     on; a record that says otherwise is a mislabelled run and an analysis rejects it. `CONFIG_ID`
     selects nothing yet (F-K), so the gateway does not check this at start (out of scope).
   - **I9 (new), the cold start (rule 11) (review S1).** In a run that started on a cache it wrote
     itself, every `entry_id` on a `TIER1_HIT` or `TIER2_HIT` record, and every `candidate_entry_id`,
     equals the `entry_id` of some `MISS` record in the same `requests.jsonl`. Compare as **sets**, not
     in order: a hit can be logged before the MISS that wrote its entry. A run that violates I9 met an
     entry it did not write. It rests on how `entry_id` flows: minted once on a miss
     (`handler.go:419`), kept by both tiers and by Tier-1 promotion, logged on the MISS record
     (`:538`, followers included) and on hit records (`:209`, `:313`) and as `candidate_entry_id`
     (`:576`). *Inferred from the code; the plan verifies it on a harness log.* **Two limits.** It
     cannot see old entries that are never touched, which matters only once capacity is bounded. And a
     MISS record that never reached the log (super-plan F-F: a request in flight at SIGTERM can vanish
     with `Dropped()` at 0) can leave an entry that no record names, so a hit on it near the end of a
     run is a false alarm. *(Corrected after `/ai-review`, finding 1: revision 2 said a MISS leader whose
     client left during write-back (F-J) is a false alarm. It is not: the write-back closure only logs its
     errors and always returns the generation, so that leader's record is still a MISS and still names
     the entry.)*
6. **Offline reading rules.** The refusal-rate denominator gains `support_gate == "on" ∧ config_id ∈
   {4, 5}` (today: cause ∈ {`SUPPORT`, `NONE`} and `source_overlap ≥ θ_run`). Without it, off-arm
   `NONE` rows enter with zero refusals and the rate is diluted with no error; the proposal limits the
   refusal rate to "4 (on-arm), 5". Band share, hit rate and false hits by cause are reported **per
   arm**, never pooled.

   **6b. Joins name their arm (review S2).** *Decisions changed by provenance* is a 3 ⋈ 4 join, and
   configuration 4 is now two arms. **3 ⋈ 4-off is provenance alone; 3 ⋈ 4-on mixes provenance with the
   support gate.** A join on `config_id` alone pools both and gives a plausible wrong number. The
   sentence at `interfaces.md:623` ("counted by the configurations 3 ⋈ 4 join") gains "on the off-arm".
   A per-request join between 4-off and 4-on is valid only on the **static-cache arm** (item 6.3): online,
   a refusal causes a different write-back, so the two caches drift apart (`Final_Proposal.md`, cache
   population). Online, compare the arms in aggregate only (hit rate, false-hit rate). Nothing is lost if
   a join is built later, because every record carries `support_gate`.
7. **New rule 11 — a measured run starts on a cache it wrote itself (v0.14) (review S1).** The off-arm
   writes Tier-2 entries and Tier-1 promotions that no gate checked, and they stay in Redis after the
   process ends. A later gate-on process serves them as `TIER1_HIT`, which runs no rule, while its
   records say `support_gate: "on"`. The reverse direction inflates the hit rate, and an off-then-off
   warm start has the same fault. **The rule is about the start state, not the arm**, because the arm
   that wrote a foreign entry can never be known, not even with P1's manifest. So **a measured run
   starts with `t1:`, `t2:` and `lru:` empty** (never `corpus:`; `dep:` and `entry:` until Phase 4), by
   `python3 experiments/scripts/loadgen_footprint.py flush-cache`. *(Corrected after `/ai-review`,
   finding 2: revision 2 also named `make demo-reset`. That target runs `FLUSHALL`, restores `data/` and
   re-ingests the corpus, so it deletes `corpus:` and is for demos only.)* Exceptions: the
   static-cache arm (item 6.3), which fills its cache on purpose and is not decided here, and a warm-up
   done through the same gateway process inside the run (its MISS records are in the log). **A run that
   violates I9 is not admissible**, and I9 is the check; it needs only `raw/`. Nothing blocks a start.
   After C2 the flush tool refuses whenever `dep:` or `entry:` exist, and deleting `t2:` alone would
   leave dependency sets pointing at nothing, so **Phase 4 defines the reset** and this sentence stops
   being enough.
8. **Rule 10** gains one clause: it applies to the gate-on arm only, and why (item 3).
9. **Version table and `Current version`:** v0.14. The row says: one new required key; the served rule
   is now per arm; **a configuration-4 run is identified by `(config_id, mutation, support_gate)`**;
   a log from the 2.3 era lacks the key and is gate-on; a log from before 2.3 is neither arm.

**ADR-010** records the above in `decisions.md`, with a summary row. It states:
- *Decided:* the switch, the key, the typed parameter, the rules above.
- *Supersedes, without editing them:* ADR-009's "always on" and its forward note that 2.4 "adds one
  parameter to `Judge`" (done); the `decisions.md:74` statement of the served rule ("similarity ∧
  namespace ∧ support … serve only on `NONE`"), which becomes **per arm**. That frozen-table row's
  own trigger ("after the first run on `v1`") has not happened, so the row is amended in place and
  ADR-010 is the numbered entry that says so.
- *Run identity:* `(config_id, mutation, support_gate)` for configuration 4. `CLAUDE.md:202-203` and
  `Final_Proposal.md:391` still say `(config_id, mutation)`. They are the author's files and are
  **not edited without the author's OK [Q3]**. Until then ADR-010 is the authority.
- *Row 2.4's Done-when* ("`support_gate` in the run manifest") is met by the D1 reading: the manifest
  does not exist (P1), the gateway reads `SUPPORT_GATE`, and P1's manifest must record it. Say so
  outright.
- *Joins and the price of the gate:* the paragraph in §6 item 6b. And **the second pre-registered
  null reads the gap between the arms' hit rates, and part of that gap is ADR-009's `k=1` effect**: a
  refused entry stays the nearest one and refuses each paraphrase in turn (review N4). Report the share
  of `SUPPORT` refusals whose `candidate_entry_id` repeats next to the gap; it is computable from `raw/`.
- *Forward notes:* **P1's manifest records `SUPPORT_GATE` but takes the arm from the records, or checks
  that the environment and the records agree, and never takes it from the environment alone** (review
  S4). Phase 4's completeness run uses the off-arm (or reads `dep:*`/`entry:*` directly), and Phase 4
  defines the cache reset that rule 11 needs once `dep:`/`entry:` exist. Phase 7 compares μ_hit with the
  gate on against off **on a probe set the gate admits, so both arms serve the same hits**: the arms
  differ in hit mix and in the background writes each hit triggers (`BumpHitCount` and the Tier-1
  promotion), so an unmatched comparison is not the gate's cost alone (review N3).
- *Invalidates:* none citable. `experiments/results/` holds only `.gitkeep`. See §7.

## 7. The measurement change, for `/approve experiment`

- **What changes.** A new run dimension. On the off-arm the served Tier-2 rule is
  `similarity ∧ namespace`, so the Tier-2 hit rate, the tier mix (more Tier-1 promotions), the band
  share and *false hits by cause* all move against the on-arm. The two arms are reported apart.
- **What it invalidates.** Nothing citable (`impact.md` §3). Item 1.6's footprint runs are older than
  2.3 and already not comparable. Logs written between `94ed44b` and the 2.4 commit are gate-on.
- **Metric definitions.** Refusal rate: §6 item 6. *% entering the cascade band*: from `entered_band`
  alone, per arm. The proposal's second pre-registered null (the gate refuses so much that the hit rate
  collapses) is read from the on-arm hit rate against the off-arm hit rate, which is why the off-arm
  must exist, with the `k=1` repeat share reported beside the gap (§6, ADR-010). *Decisions changed by
  provenance*: 3 ⋈ 4-off (§6 item 6b).
- **Gate cost.** About 30 µs for both arms per judged candidate (a benchmark, not a measurement of the
  system). The off-arm skips it. Phase 7 measures μ_hit with the gate on against off, **on a probe set
  the gate admits** (§6, ADR-010).
- **Stale server.** Rule 10 guards the on-arm. The off-arm's result does not depend on evidence text
  (§8, F6).
- **Cache state.** Rule 11 and invariant I9: a measured run starts on a cache it wrote itself.
- **Run identity.** `(config_id, mutation, support_gate)` for configuration 4; configuration 5 is on.
- **Phase 4.** The completeness run must use the off-arm, or read `dep:*` and `entry:*` directly,
  because the on-arm's numeric check can hide a missed purge (ADR-009).

## 8. Failure modes, silent ones first

| # | What goes wrong | Why it is silent | Guard |
| :-- | :--- | :--- | :--- |
| F1 | A pre-2.3 log is read as gate-on by "no key means on" | the log has no `support_gate` and no `refusal_cause`; it looks like an on-arm run with no hits | the reading table keys on `refusal_cause` presence (§6 item 2); no `omitempty` |
| F2 | The label and the behaviour come from two values | both compile; the label says on while the gate is off | one field, `Handler.SupportGate`, feeds both; invariant I7 catches the mismatch offline whenever the run has a Tier-2 hit or a `SUPPORT` record |
| F3 | The zero value of `Handler` is the off arm | a struct literal that forgets the field silently ablates the gate in production and in every test | `GateOn` is `0`; `TestSupportGateZeroValueIsOn`; the handler-level zero-value test; the unchanged harness literal at `harness_test.go:752` never sets the field |
| F4 | The key is set later (in `recordCause`, after `tryTier2`) or has `omitempty` | Tier-1 records then carry `""` or no key, and the reading rule calls them gate-on | set in the `rec` literal at `handler.go:174`; no `omitempty`; a test on every exit (acceptance 6) |
| F5 | `SUPPORT_GATE=` (empty) quietly becomes "on" | `getenv` reads empty as unset | `os.LookupEnv`; set-but-empty is an error; `TestGateFromEnv` |
| F6 | A stale RAG server (chunk IDs, no texts) on the off-arm | nothing in `raw/` or the process log shows it, and rule 10 is vacuous there | **not a gap:** the only non-test reader of `Texts` is the `Judge` call (`cascade.go:171`), and the off-arm returns before it reads them, so the off-arm serves the same entries with or without a stale server. Rule 10 exists because the on-arm's hit rate would describe the server; the off-arm's cannot. Misaligned texts are still a retrieve error on both arms. Stated in §H so it is a rule, not an accident; the test `TestSupportGateOffDoesNotReadEvidence` pins it |
| F7 | Entries written before the run (by the other arm, or by an earlier run of the same arm) are served in it | the answers are real and the records say `on` | rule 11 (start with `t1:`, `t2:`, `lru:` empty); **checked offline by invariant I9**; the startup line; nothing blocks a start **[R1]** |
| F8 | Pooled-arm metrics (refusal rate, band share, false hits) are diluted | the numbers are plausible | the reading rules filter by `support_gate` **and `config_id ∈ {4, 5}`** (§6 item 6) |
| F9 | A bad value burns the `RUN_ID` | the run directory exists and is empty | `gateFromEnv` runs before `telemetry.Open` |
| F10 | `Judge` is called without the arm at some new call site | a wrapper would compile and ignore the switch | there is no wrapper: the parameter is required, so a missing one does not compile |
| F11 | A future edit to `Judge` moves the off branch before the namespace or similarity check | a wrong-namespace candidate is served on the off-arm | `TestJudgeAgreesWithDecideLaneGateOff`; mutant "move the off branch to the top" |
| F12 | `CONFIG_ID=5` with `SUPPORT_GATE=off` | the run is mislabelled | I8 offline; the gateway does not check (out of scope) |
| F13 | `mutation-check.py` stops matching and reports SKIP | acceptance 9 fails loudly, not silently | the parameter is first; the script is copied into this trail, never edited in 2.3's; its `go test` command also lists `./cmd/gateway` (review N5) |
| F14 | The startup line says OFF while the process runs ON (the parsed value is never assigned to the handler) | the records honestly say `on`, so I7 is silent, and `main()` has no test; a run named `cfg4-off` becomes a second on-arm run | the line is printed **after** the assignment and from `handler.SupportGate` (§4); "main.go assigns the field" is a manual plan check; P1's manifest takes the arm from the records, not from the environment alone **[R4]** |
| F15 | A join on `config_id` alone pools the two configuration-4 arms | *decisions changed by provenance* becomes a plausible wrong number: provenance plus the support gate | §6 item 6b and ADR-010 name the arm in each join; every record carries `support_gate` so the right join can be built later **[R2]** |
| F16 | A future configuration 3 (no gate) is labelled `on` | it logs cause `NONE` with null support fields, which breaks I7's on-clause in a healthy run and enters the refusal-rate denominator with zero refusals | every rule that reads `support_gate` also filters `config_id ∈ {4, 5}`; what 1–3 write is F-K's owner's call **[R3]** |

## 9. Edge cases

- **Zero `NamespaceDecision`.** `NAMESPACE` on both arms, never `NONE`.
- **NaN similarity.** `SIMILARITY` on both arms (the check is written positively).
- **A cached answer of `""` or stopwords only.** On the on-arm it is refused as `SUPPORT` (2.1's rule);
  on the off-arm it is served, as it was before 2.3. That difference is the point of the arm.
- **No Redis keys for the arm.** Nothing is stored in Redis (ADR-007: Redis holds only derived state;
  `dep:`/`entry:` have one writer). A marker key was considered and rejected (§12).
- **Functional run** (`RUN_ID` unset, as `make dev` runs). No log is written, but the startup line still
  names the arm.
- **Coalesced followers** each run their own `Ask` and `tryTier2` on the same handler, so they carry the
  same arm. Write-back, coalescing and the epoch stamp do not read the gate.
- **Tier-1 promotion** runs on every served Tier-2 hit, on both arms (`handler.go:343-354`). On the
  off-arm it promotes answers that no gate checked. That is the reason for rule 11.
- **A same-arm warm start** (off then off, or on then on) is also a rule 11 violation, and I9 sees it:
  the second run's hits name entries that no MISS record in its own log wrote.
- **Shed, abandoned, failed generation.** These keep `support_gate` and the Tier-2 cause they earned
  (the record is built once and emitted once).
- **The 405 and 400 exits** write no record, as before.
- **An unknown `Gate` value** (not reachable from `ParseGate`) runs the gate and prints `invalid`.
- **Race.** The arm is set before `ListenAndServe` and never changed, so there is no data race and no
  lock. A runtime switch is out of scope.

## 10. Tests

Existing tests: **0 change outcome** (`impact.md` §2). Compile-only: the 5 `Judge` call sites in
`reuse/cause_test.go` (lines 60, 90, 111, 121, 200) gain `GateOn,` as the first argument (D4, confirmed).
`TestJudgeAgreesWithDecideLane` stays otherwise untouched (A1).

New tests (names say `SupportGate`, because `httpapi`'s harness already has an unrelated type `gate`,
a blocking hook):

| File | Test | Checks | Acceptance |
| :--- | :--- | :--- | :---: |
| `reuse/gate_test.go` | `TestSupportGateZeroValueIsOn` | `Gate(0) == GateOn`; `GateOn.String() == "on"`; `GateOff.String() == "off"`; `Gate(7).String() == "invalid"` | 8 |
| | `TestParseGate` | `on`, `off` ok; `""`, `ON`, `Off`, ` on`, `on\n`, `0`, `true`, `1` all error | 1 |
| | `TestJudgeGateOffServesWhatTheGateRefuses` | the 2.3 table (`TestJudgeCauses`) with `GateOff`: `NAMESPACE` / `SIMILARITY` rows unchanged; every row that reached the gate is `NONE` with `Support == nil`, including nil texts and refusing evidence | 2, 3, 5 |
| | `TestJudgeAgreesWithDecideLaneGateOff` (A1) | the full grid of `TestJudgeAgreesWithDecideLane`, with refusing evidence and nil texts: `NONE` exactly when `d.Reuse`; `Support == nil` always; never `SUPPORT`, `NOT_SCORED` or `CONTAINMENT`; zero decision is `NAMESPACE` | 4 |
| | `TestJudgeBothArmsAgreeBeforeTheGate` | over the grid: on-cause ∈ {`NAMESPACE`, `SIMILARITY`} ⇒ off-cause is the same | 5 |
| | `TestJudgeUnknownGateRunsTheGate` | `Gate(7)` behaves as on | F3 |
| `telemetry/support_gate_field_test.go` | `TestSupportGateKeyIsAlwaysWritten` | a zero `Record` renders `"support_gate":""` (key present, no `omitempty`) | 6 |
| `cmd/gateway/gate_env_test.go` | `TestGateFromEnv` | unset → on; `on`; `off`; set-but-empty → error; `ON` → error; the error names `SUPPORT_GATE` | 1 |
| `httpapi/support_gate_test.go` | `TestSupportGateZeroHandlerRunsTheGate` | a harness `Handler` with the field never set refuses the 2.3 `SUPPORT` fixtures | 8 |
| | `TestSupportGateOffServesWhatTheGateRefuses` | the lexical-only and numeric-only fixtures: on → MISS / `SUPPORT`; off → TIER2_HIT / `NONE`, both support fields null, `support_gate: "off"` | 2 |
| | `TestSupportGateOffDoesNotReadEvidence` | stale server (nil texts) on the off-arm: served, `NONE`, null fields; on the on-arm the same request is `NOT_SCORED` | F6 |
| | `TestSupportGateOffCausesBeforeTheGateAreUnchanged` | below τ → `SIMILARITY`; wrong-namespace candidate → `NAMESPACE`; cold namespace and zero chunks → null, MISS | 5 |
| | `TestSupportGateKeyOnEveryExit` | both arms, each exit that writes a record: lookup error, TIER1_HIT, TIER2_HIT, MISS, SHED, ABANDONED, GENERATION_FAILED | 6 |
| | `TestSupportGateInvariants` | helper `checkGateInvariants` (I7, with its `config_id ∈ {4, 5}` filter) over off-arm and on-arm runs; constant across the run | 7 |
| | `TestSupportGateColdStartInvariant` | helper `checkColdStart` (I9) over a run that served a Tier-2 hit and a Tier-1 hit on entries its own MISS records wrote: passes; then a store seeded directly with an entry no MISS in the log wrote, hit by a request: **fails**, and names the id. Also the verification of the review's S1 inference on a real harness log | rule 11 |

**Harness edit (A2) needs widening → [Q1].** `hs.records(t)` calls `checkEveryRecord` on every call of
every test that calls `records(t)` (`harness_test.go:1018`; four tests never call it and only one of
them writes a record, ABANDONED, which `TestSupportGateKeyOnEveryExit` covers). A literal `rec.str("support_gate", "on")` would fail every
off-arm test. The smallest edit that keeps the literal as the guard for the default harness is
additive: a field `offArm bool` on `harness` (zero = false = on), and in `checkEveryRecord`

```go
want := "on" // the harness literal at :752 never sets SupportGate, so this is the zero value's label
if hs.offArm {
    want = "off"
}
rec.str("support_gate", want)
```

plus a helper in the new test file, `func (hs *harness) useGateOff()`, that sets
`hs.h.SupportGate = reuse.GateOff` and `hs.offArm = true`. Every existing test then asserts, on every
exit, that the zero-value handler wrote `"on"`. The handler literal at `:752` is **not** edited. Using
`hs.h.SupportGate.String()` instead of the literal was rejected: it would compare the label to the same
field and pass if the zero value ever became off.

**A stale comment, recorded and not edited** (tests are immutable): `checkCauseInvariants`' I5 comment
at `cause_test.go:385` says "the gate-off arm of item 2.4 will relax the last". After 2.4 it is wrong
(the off-arm never writes `SUPPORT`, so nothing relaxes). It is a comment only; the plan records it.

**Mutants.** The 2.3 script is **copied** into this trail (`mutation-check.py`, same depth, so
`parents[3]` still finds the repo) with one change to the copy, its `go test` line also listing
`./cmd/gateway` (otherwise the `gateFromEnv` mutant lives outside the tested packages and reads as a
false survivor, review N5). It is run first with the 2.3 mutants only: all must still be red. Then
these are added, each of which must turn a test red:

| Mutant | Caught by |
| :--- | :--- |
| `GateOn` and `GateOff` swapped (`iota` order) | `TestSupportGateZeroValueIsOn` |
| the off branch moved above the namespace check | `TestJudgeAgreesWithDecideLaneGateOff` |
| the off branch moved above the similarity check | `TestJudgeBothArmsAgreeBeforeTheGate` |
| off branch returns `Support: &sr` (still runs the gate) | `TestJudgeGateOffServesWhatTheGateRefuses` |
| `Judge` skips the gate whenever `g != GateOn` (so an unknown value skips it) | `TestJudgeUnknownGateRunsTheGate` || the call in `cascade.go` passes `reuse.GateOn` | `TestSupportGateOffServesWhatTheGateRefuses` |
| the record literal uses a constant `"on"` | `TestSupportGateKeyOnEveryExit` (off-arm) |
| the record literal is set after `tryTier2` | `TestSupportGateKeyOnEveryExit` (Tier-1 exits) |
| `support_gate` gets `omitempty` | `TestSupportGateKeyIsAlwaysWritten` |
| `gateFromEnv` reads empty as unset | `TestGateFromEnv` |
| `gateFromEnv` runs after `telemetry.Open` | a source-order test is not practical; caught by review of `main.go` and listed as a manual check in the plan |

**Known equivalent edit, not in the list** (it cannot change a result): the off branch calls
`CheckSupport` and throws the result away. It would cost about 30 µs and change nothing a record can
show. Acceptance 3 ("the off-arm does not run the gate") is therefore shown by `Support == nil` and by
reading the code, not by a test that could tell the two apart.

## 11. Questions for the author, and unknowns

**Questions** (each with a recommendation):

- **Q1. A2 widened.** The one-line edit to `checkEveryRecord` is not enough (§10). Allow an additive edit
  of `harness_test.go`: a field `offArm bool` and a 4-line `want` branch in `checkEveryRecord`; the
  handler literal at `:752` stays untouched. Recommended: yes. Alternative: no edit to the harness, and
  the off-arm tests skip `records(t)` (they would need their own matcher, which duplicates 40 lines).
- **Q2. Nothing in code enforces rule 11.** A Redis marker key would add schema and break ADR-007's
  "derived state only". Recommended: no code, the rule is stated, repeated in the startup line, and
  checked offline by I9 (see R1). The `SCAN`/`DBSIZE` check at start that revision 1 offered as an
  alternative is **dropped** (review N1): it would guard the wrong side. The false hits come from an
  **on-arm** process serving off-arm promotions, a guard when the off-arm starts does nothing for that,
  and a guard when the on-arm starts would block every deliberate warm start.
- **Q3. The run identity in the author's files.** ADR-010 says a configuration-4 run is
  `(config_id, mutation, support_gate)`. `CLAUDE.md:202-203` and `Final_Proposal.md:391` still say
  `(config_id, mutation)`. Recommended: ADR-010 first; the author edits those two lines, or says
  "edit them" at `/approve implementation`.
- **Q4. Stale server on the off-arm (G6).** Recommended: state it in §H and test it, no new check
  (F6). Alternative: fire the one-time ERROR line on both arms. F6 relies on the *decision* not reading
  `Texts`, and a log-only read would not break that; the real reason to skip the line is that it adds
  nothing on the off-arm, whose result a stale server cannot change (review N6).

**Questions from the review** (the reviewer recommends yes to all four; the reviewer agrees with Q1, Q3
and Q4):

- **R1. Rule 11 about the start state, checked offline.** "A measured run starts on a cache it wrote
  itself (the static-cache arm excepted)", with invariant I9 as the check (§6 items 5 and 7). Replaces
  the revision-1 claim that the check was impossible. Recommended: yes.
- **R2. Joins name their arm.** ADR-010 states: 3 ⋈ 4-off for provenance; a per-request 4-off ⋈ 4-on join
  only on the static-cache arm. Stated now, built with F-K. Recommended: yes.
- **R3. The `config_id ∈ {4, 5}` filter.** Every rule that reads `support_gate` also filters on it, and
  the sentence "configurations 1–3 write `on`, meaningless" is removed. Recommended: yes.
- **R4. The startup line after the assignment.** Printed from `handler.SupportGate`, and P1's manifest
  takes the arm from the records. Recommended: yes.

**Unknowns that still need verifying:**

1. ~~Whether `go run` passes the environment through `make dev SUPPORT_GATE=off`.~~ **Settled by the
   review** on a scratch Makefile with the same recipe shape and GNU Make 3.81: `make t SUPPORT_GATE=off`
   and `SUPPORT_GATE=off make t` both reach a `go run` child as `off`; `SUPPORT_GATE=` arrives set and
   empty (refused); `'SUPPORT_GATE=off '` arrives with the space (refused loudly). The real `make dev`
   needs Redis and was not run; the plan keeps one optional check.
2. Whether the new `Judge` parameter changes any benchmark enough to matter. `BenchmarkJudge` is
   compile-only edited; its number is not citable either way.
3. Whether all 2.3 mutants stay red after the new parameter. The plan runs the script before and after.
4. The real-answer sample (2.3 acceptance 10) is still open. It decides whether the two arms differ at
   all on real answers; 2.4 neither runs nor changes it.
5. Whether P1 puts the arm into the `run_id` name. Not decided here.
6. What configurations 1–3 write for `support_gate` once built. This design leaves it to the owner of F-K
   (recommended: `off`, meaning the gate did not run) and filters every reader on `config_id ∈ {4, 5}`.
7. Whether I9 is exact. It is inferred from reading `handler.go`; `TestSupportGateColdStartInvariant`
   verifies it on a real harness log. The one known false alarm is a MISS record lost to F-F (see §6
   item 5); the F-J edge named here in revision 2 was wrong (`/ai-review`, finding 1).

## 12. Alternatives not taken, and out of scope, restated

- A `bool` parameter (rejected, §2). A wrapper that keeps the old `Judge` signature (rejected, F10).
- A minimal manifest file now (rejected: P1's work, and it fixes the shape of every later run).
- Shadow scoring on the off-arm (rejected: different measurement; the Done-when says null).
- A Redis marker key to detect a cross-arm cache (rejected, Q2). A `SCAN`/`DBSIZE` check at start
  (rejected: it guards the wrong side, review N1).
- Separate lexical-only and numeric-only modes (rejected, D3).
- A `refusal_cause` or `support_gate` field in the HTTP response (rejected: the arm is a property of
  the process).
- A `CONFIG_ID` cross-check at start (out of scope, F-K).
- The run manifest, the real-answer sample, θ in the served rule, configuration 3, a second candidate,
  any change to `τ_s`, the stopword list, the numeric rules or the unit list, any ML on the hit path.
- The Makefile: not edited. `Makefile:353` ("the gate is not wired in yet") has been wrong since 2.3 and
  is left to the author, as in 2.3.
