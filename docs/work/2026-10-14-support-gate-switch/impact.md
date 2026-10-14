# Impact — support-gate switch (item 2.4)

Written by the `impact-analyst` subagent on 2026-10-14 and saved by the main session. The main session
re-checked five claims against the code (marked ✔). Everything else is the analyst's reading, with
the file and line it gave; anything it inferred is marked *inferred*.

## Summary

- **No frozen value changes.** `num_ctx`, slots, the embedding model, `DIM`, `top_k`, chunking,
  eviction, capacity, δ, `dataset_version`, `τ_s`, the `S_lex` rules and the numeric rules are all
  untouched.
- **The change is still not routine.** Three things move:
  - the served Tier-2 rule now depends on a per-process setting (off-arm: `similarity ∧ namespace`);
  - §H gets a new required key;
  - the identity of a configuration-4 run becomes `(config_id, mutation, support_gate)`.
- **No prior run is invalidated.** `experiments/results/` holds only `.gitkeep` ✔, and no
  `requests.jsonl` exists in the repo. Item 1.6's `footprint-20261006` runs are older than 2.3 and
  ADR-009 already marked them not comparable.
- **Lead risk, and it is a mistake in our own spec.** The spec says "a log without `support_gate` is a
  gate-on log". That is true only for logs written between the 2.3 commit `94ed44b` and the 2.4
  commit. A log from **before** 2.3 also lacks the key, and it had **no gate at all**. See §3.
- **Existing tests that change outcome: 0**, if three conditions hold (§2). Compile-only edits: the
  5 `Judge` call sites.
- **Phases required:** contract (§H v0.13 → v0.14, ADR-010) and experiment.

## 1. Packages and files

| Package | Where | Change |
| :--- | :--- | :--- |
| `reuse` | `cause.go:96-111` | One typed parameter on `Judge`. Off-arm returns `Judgement{Cause: CauseNone}` with `Support == nil`, **after** the NAMESPACE and SIMILARITY checks (`:97-102`) and **before** `CheckSupport` (`:103`). Comments at `:62-69` and `:76-95` go stale. Stays stdlib only. |
| `httpapi` | `handler.go:71-117` | New `Handler` field. |
| `httpapi` | `handler.go:174-182` ✔ | The `rec` literal gains `SupportGate`, next to `ConfigID` and `Mutation`. |
| `httpapi` | `cascade.go:171` | Passes the arm to `Judge`. This is the only production caller. |
| `telemetry` | `evallog.go:30-35` | `SupportGate string` with tag `json:"support_gate"`, **no `omitempty`**. A plain string: `telemetry` imports nothing from this repository (`architecture.md:152`). |
| `cmd/gateway` | `main.go:143-146`, `:205-208`, `:268-274` | A pure parser beside `retiredEnv`, a startup log line, and the field set. Wiring only. |
| `ragclient`, `cache`, `rag/`, `.proto` | — | Nothing changes. One comment goes stale (`ragclient/retrieve.go:28-31`). |

No new import edge and no cycle. **`tryTier2`'s signature must not change**: `cascade_test.go:227` and
`cause_test.go:524` call it directly, so the arm is read from the handler.

## 2. Callers and tests

- **`Judge` callers:** `cascade.go:171` (production), and in `reuse/cause_test.go` lines 60, 90, 111,
  121 and 200 (the last is `BenchmarkJudge`). These are D4's 5 compile-only edits. No script calls
  `Judge`.
- **`mutation-check.py` (2.3 trail) will break** ✔. It matches the source text
  `"c.Entry.Answer, retrieved.Texts, retrieved.ChunkIDs)"` (lines 47-48). If the new parameter is
  **last**, that pattern no longer matches, the script reports SKIP and exits 1, so spec acceptance 9
  ("2.3's 31 mutants still caught") fails as written. Fix: put the parameter **first**, or copy the
  script into this trail with new patterns. The closed 2.3 trail is not edited.
- **`Handler` construction:** `main.go:268` through `NewHandler`, and `harness_test.go:752`, a struct
  literal that every `Ask` test uses. So **the zero value must mean "on"**, or all 16 of 2.3's
  `cause_test.go` tests turn red. Use a field named for the off state (for example `SupportGateOff`).
  Do **not** add a `NewHandler` parameter: the harness does not call `NewHandler`, so it would protect
  nothing.
- **`telemetry.Record` construction:** production only at `handler.go:174`. All test literals are keyed,
  so they compile unchanged. No test asserts an exact key set.
- **Tests that change outcome: 0**, provided: (1) the zero value is on, (2) `tryTier2`'s signature is
  unchanged, (3) the gate-on body of `Judge` is unchanged.

**Two conflicts with "tests are immutable" that need the author:**

- **A1. Spec acceptance 4 against D4.** Acceptance 4 says `TestJudgeAgreesWithDecideLane` runs with both
  values. That is a structural edit, more than D4's "compile-only, no assertion changes".
  Recommended: leave that test compile-only (gate on), and add a **new**
  `TestJudgeAgreesWithDecideLaneGateOff`: cause is `NONE` exactly when the lane rule reuses,
  `Support == nil` always, never `SUPPORT` or `NOT_SCORED`, even with refusing evidence and nil texts.
- **A2. The strongest guard is a one-line edit to a test helper.** In `checkEveryRecord`
  (`harness_test.go:1023-1031`) ✔, next to `config_id` and `mutation`, add `rec.str("support_gate", "on")`.
  It tightens the check and loosens nothing, and then every existing `Ask` test, on every exit,
  asserts the key and the safe zero value. It is still a test-file edit. The other way is new tests
  per exit.

## 3. Frozen values, measured paths, and how to read an old log

- **Frozen-table row that becomes false:** `decisions.md:74`, "The served rule is similarity ∧
  namespace ∧ support … Serve only on NONE". The served rule is now per arm, and ADR-010 amends it.
  The row's own trigger ("after the first run on v1") has not happened, but the ADR is needed anyway
  because §H changes.
- **Measured path that changes:** on the off-arm Tier-2 serves `similarity ∧ namespace`. That moves
  the hit rate, the tier mix (more Tier-1 promotions), the band share (on the off-arm `entered_band`
  is again about the same as the TIER2_HIT indicator), and μ_hit (the off-arm skips about 30 µs per
  judged candidate; a benchmark, not citable).
- **Invalidates: none, because there are no runs yet.**

**How to read a log.** Logs carry no gateway SHA until P1, so **key presence is the only marker**. That
is why `support_gate` must not have `omitempty`.

| `refusal_cause` key | `support_gate` key | Meaning |
| :--- | :--- | :--- |
| absent | absent | **Before 2.3.** No gate, no zero-chunk guard, older meanings (ADR-009). **Neither arm.** Never read as gate-on, never pooled as an off-arm. |
| present | absent | **2.3 era** (`94ed44b` to the 2.4 commit). Gate on, hard-wired. |
| present | `"on"` or `"off"` | Read the key. Any other value, including `""`, is a defect. |

An off-arm log is **not** a pre-2.3 log. They differ on the zero-chunk guard, on `similarity`,
`reuse_rule` and `t_search_ms` for zero chunks, and on the five 2.3 keys.

## 4. Readers of null support fields and causes

| Reader | On the off-arm | Verdict |
| :--- | :--- | :--- |
| I1, I3, I4, I6 | Hold. | OK |
| I2′ (`interfaces.md:636`) | A banded non-hit happens only through the `NAMESPACE` alarm. Holds. | OK |
| **I5** (`:639`) | "(until item 2.4's gate-off arm)" is misplaced: the off-arm never writes `SUPPORT`, so nothing relaxes. | **Restate** |
| **New invariant** | v0.13 has no clause "gate on ∧ `NONE` ⇒ both non-null". Add: `support_gate=="on" ∧ cause=="NONE"` ⇒ both support fields non-null; `support_gate=="off"` ⇒ both null and cause ∉ {`SUPPORT`, `NOT_SCORED`}. It catches a run labelled with the wrong arm, whenever the run has at least one Tier-2 hit or `SUPPORT`/`NOT_SCORED` record. | **Add** |
| Field note (`:625`) | "The arms are told apart only among cause `NONE`" becomes: told apart by `support_gate`; null support fields are a cross-check. | Restate |
| **Refusal-rate denominator** (`:642`) | Today: cause ∈ {`SUPPORT`, `NONE`} with `source_overlap ≥ θ_run`. On a pooled log the off-arm `NONE` rows join the denominator with zero refusals, so the rate is **silently diluted**. | **Add `support_gate == "on"`** (the proposal says "4 (on-arm), 5") |
| Band share | Still from `entered_band` alone; report it per arm. | OK |
| **Run rule 10** (`:644`) | `NOT_SCORED` is never written on the off-arm, so the rule is **vacuously met** by an off-arm run on a stale server. §H already says rule 10 checks the gate-on arm only. | v0.14 must say what checks the off-arm (risk 7) |
| NOT_SCORED ERROR line (`handler.go:588-592`) | Never fires on the off-arm. | Same blind spot |
| `recordCause` (`handler.go:574-593`) | `Cause = NONE`, `Support = nil` gives `refusal_cause: "NONE"` and null support fields. Correct, no edit. | OK |
| Comments | `Judgement.Support` (`cause.go:66-67`) and `tier2Outcome.Support` (`cascade.go:68-70`) say "non-nil exactly when the candidate cleared the lane rule and tau". Restate as "exactly when the gate ran". `supportSummary` prints "not run"; "gate off" reads better. | Cosmetic |
| `checkCauseInvariants` (`cause_test.go:367-405`) | Gate-on only. Do not edit it; the new tests need an arm-aware helper. | — |

**A stale RAG server on the off-arm** (chunk IDs, no texts): `ragclient` accepts it
(`retrieve.go:51-52`), `Judge`-off returns `NONE`, and the candidate is **served**. The record says
cause `NONE` with null support fields. Nothing in `raw/` and nothing in the process log shows it.
Misaligned texts (present, wrong length) are still a retrieve error on both arms: a MISS with cause
`null`.

## 5. Silent paths for the switch itself

- **One field, two uses.** Derive the `Judge` argument (`cascade.go:171`) and the record label
  (`handler.go:174`) from the **same** `Handler` field. Two sources is the "key written as the wrong
  arm" defect.
- **Every exit of `Ask` gets the key** if it is set in the literal at `handler.go:174-182` ✔. The
  deferred single emit logs that `rec` on every exit after it: Tier-1 lookup error (`cache ""`, which
  spec acceptance 6 did not list), TIER1_HIT, TIER2_HIT, MISS, SHED, ABANDONED, GENERATION_FAILED.
  The two exits before it (405 and 400) write no record at all; that is old and unchanged. If the key
  were set later, Tier-1 records would carry `""`.
- **Coalesced followers** each run their own `Ask` and `tryTier2` on the same handler, so they get the
  same arm. Write-back, coalescing and the epoch stamp do not read the gate.
- **The arm is per process**: set before `ListenAndServe`, read-only after, so no data race.
- **Tier-1 promotion runs on every served Tier-2 hit** ✔ (`handler.go:343-354`, a detached `Cache.Put`).
  So the off-arm promotes answers that no gate checked, and they **persist in Redis after the process
  ends**. A later **gate-on** process serves them as TIER1_HIT, which runs no rule, and the record still
  says `support_gate: "on"`. This is silent contamination between arms (risk 6).

## 6. Scope, dependencies, contracts, Makefile, stale text

- **Do-not-reinstate list:** nothing touched. The on/off ablation arm is on the **non-negotiable**
  list (`Final_Proposal.md:595`), so 2.4 is required scope.
- **No new dependency.** One bool per process and about 21 bytes per JSONL line.
- **Contracts:** §H only. The §A response is unchanged (recommended: keep it so, the arm belongs to the
  process). §B, §D and the `.proto` are unchanged.
- **Makefile: no edit needed.** `make dev` runs `go run ./cmd/gateway` with no `env -i`
  (`Makefile:149-150`), and GNU Make 3.81 exports command-line variables to recipes, so
  `make dev SUPPORT_GATE=off` reaches the gateway. `make dev SUPPORT_GATE=` exports an empty value,
  which D1 refuses at start (loud, intended). *Inferred:* that `go run` passes the environment through.
- **Text that goes stale after 2.4:**
  - `README.md:66-68` and `:160-162`; `architecture.md:168-170` and `:205`;
  - `super-plan.md:345` (exit wording, D3), `:349`, `:356`, `:379`;
  - `decisions.md:74` (frozen row), `:84` (P1: the manifest must record `SUPPORT_GATE`), and the ADR table;
  - `interfaces.md:3`, `:80-93`, `:547-553`, `:625`, `:639`, `:642`, `:644`, `:656-660`;
  - comments in `reuse/support.go:10` and `ragclient/retrieve.go:28-31`;
  - **`CLAUDE.md:202-203`** ("a run is identified by `(config_id, mutation)`") and
    `Final_Proposal.md:391`. Both are the author's files: **not edited without the author's OK.**
- **Not stale:** `experiments/k6/ask.js` and `mu_hit.js` print manifest lines but cannot see the
  gateway's arm, so the future manifest must take it from the startup log or the records.
- **Old, not 2.4's:** `Makefile:353` ("the gate is not wired in yet") has been wrong since 2.3.

## 7. Phases and the ADR

- **Contract phase: required.** §H v0.14: the required key (no `omitempty`), the reading table in §3,
  I5 restated plus the new arm invariant, rule 10's off-arm blind spot, the refusal-rate filter, the
  example JSON.
- **Experiment phase: required.** A new run dimension; the off-arm's `TIER2_HIT` means
  `similarity ∧ namespace`; per-arm metric definitions; cache state between arms; the stale-server
  precondition.
- **ADR-010 must say:**
  - **Invalidates:** none, no runs yet. Logs from `94ed44b` to the 2.4 commit lack `support_gate` and
    are gate-on. Logs before `94ed44b` lack it **and** `refusal_cause`, are **neither arm**, and stay
    non-comparable (ADR-009).
  - **Supersedes:** ADR-009's "always on"; the `decisions.md:74` statement of the served rule (now per
    arm); the run identity in `CLAUDE.md`, `Final_Proposal.md:391` and §9.2, which becomes
    `(config_id, mutation, support_gate)` for configuration 4.
  - **Configuration 5 is gate-on by definition.** The analysis rejects `(5, *, off)` until F-K gives
    `CONFIG_ID` a meaning.
  - **Forward notes:** P1's manifest records `SUPPORT_GATE`; Phase 4's completeness run uses the
    off-arm; Phase 7's μ_hit with the gate on against off measures the gate's cost.
  - **Row 2.4's Done-when** ("`support_gate` in the run manifest") is met by the D1 reading. Say so
    outright.

## 8. Hidden risks, ranked (silent first)

1. **Pre-2.3 logs read as gate-on** by "no key ⇒ gate-on". Guard: key on `refusal_cause` presence (§3).
2. **Arm label and arm behaviour come from two values.** Guard: one `Handler` field, and the new
   offline arm invariant (§4).
3. **Zero value off.** If the field is named for "on", or `main.go` forgets to set it, production
   silently changes arm. Guard: a field named for the off state, and spec acceptance 8.
4. **Key set after Tier 1, or given `omitempty`.** Tier-1 records then carry `""` or no key and the
   reading rule calls them gate-on. Guard: set it in the literal at `handler.go:174`, no `omitempty`,
   a test on every exit.
5. **`""` handling.** `getenv` (`main.go:30-35`) and `retiredEnv`'s shape `func(string) string` cannot tell
   unset from empty, so `""` would quietly become "on" and break D1. Guard: the parser takes
   `func(string) (string, bool)` (`os.LookupEnv`).
6. **Cross-arm cache carry-over** through Tier-1 promotion (§5). Guard: a run starts on a cache with
   `t1:`, `t2:` and `lru:` flushed, or records its starting cache state. The experiment phase decides.
   Item 6.3's static-cache arm needs the same care.
7. **Stale RAG server invisible on the off-arm.** Rule 10 is vacuous and no ERROR line fires.
   `make seam-check` checks its own server on `:50052`, not the gateway's. The real guard is launching
   through `make dev`, which owns its server and refuses a held port. The other option is to fire the
   existing one-time ERROR line on "chunk IDs, no texts" on **both** arms: an instrument check that
   changes no decision. This is the design's call; spec acceptance 3 forbids only reaching the gate's
   arms.
8. **Pooled-arm metrics** (refusal rate, band share, false hits) silently diluted. Guard: the §H reading
   rule filters by `support_gate`.
9. **A bad value burns the `RUN_ID`** if it is parsed after `telemetry.Open` (`main.go:257`), the F-M
   pattern `getenvInt("CONFIG_ID")` already has. Guard: parse at `main.go:144`, beside `retiredEnv`.
10. **`CONFIG_ID=5` with `SUPPORT_GATE=off`** is a mislabelled run. Out of scope per the spec; the ADR
    states the rule.
11. **Loud, not silent:** the mutation-script SKIP (§2); A1 and A2 (§2).

## Unknowns the analyst could not verify

- Whether measured runs in Phases 6 and 7 will be launched through `make dev`. No measured-run launcher
  exists (*inferred* from item 1.6's practice).
- Whether P1 puts the arm into the `run_id` name.
- How configurations 1–3 should read `support_gate` once they are built (*inferred*: they log "on" by
  default, which means nothing there).
- The real-answer sample (2.3 acceptance 10) is still open. It decides whether the two arms differ at
  all on real answers. 2.4 neither runs nor changes it.

## Smallest change that meets the spec

- **Do:**
  - one typed parameter on `Judge`, placed **first** (for example `reuse.GateOn` / `reuse.GateOff`, so a
    bare `true` cannot be misread), with the off branch after SIMILARITY;
  - `Handler.SupportGateOff bool`;
  - `SupportGate` in the `rec` literal, derived from that field;
  - `telemetry.Record.SupportGate string`, no `omitempty`;
  - a pure parser in `main.go` using `LookupEnv`, called before `telemetry.Open`, and a startup log line;
  - the 5 compile-only test edits, and new test files;
  - `interfaces.md` v0.14, ADR-010, and the doc lines in §6.
- **Cut:** a `NewHandler` parameter; any §A response field or `/stats` counter; a Makefile edit; the
  manifest; shadow scoring; a `CONFIG_ID` cross-check; editing the 2.3 trail's `mutation-check.py` in place.

> **Required phases:** impact · contract · experiment · implementation (scope L: design → opus
> design-review → plan come in between).
