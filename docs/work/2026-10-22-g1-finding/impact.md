> **Addendum, 2026-10-23 — read this first.** This analysis was written for rule R2 (change G1 into an existence check).
> The author then chose a different form: keep G1 and its failed result, and freeze `v1` with the failure on record (an
> opt-in `--accept-failed G1` in the gate and the freeze tool). **What still applies:** sections 2 (frozen values, report
> shape, contract), 3 (the reachable-trap definition and the numbers 74/129, 108/155, 182/284), 4 (no run invalidated)
> and 5 (phases), and the finding about `Final_Proposal.md:436` and `:497`. **What does not apply:** everything about
> *changing* G1's floor or its combined form (section 1's rows for `G1_MIN_PAIRS`, `check_g1`, and the two tests that encode
> the floor). Under this form `check_g1`, `G1_MIN_PAIRS` and those tests are **untouched**.
>
> **What this form touches instead (written by the main session, not the analyst; the design review is asked to check it):**
>
> | File | Change | Existing tests affected |
> | :--- | :--- | :--- |
> | `corpus_gate.py` `main` (around `:1547`, `:1620-1650`, the report dict) | the `--accept-failed` argument; `freezable`, `accepted_failures`; the banner; exit code 3; the digest when freezable; the reachable-trap and sample-size statistics | none: opt-in; default path identical |
> | `corpus_gate.py` new functions | `reachable_traps`, `zero_error_trials` | none (new) |
> | `freeze_corpus.py` `run_problems` (`:~284-330`), `compare_runs` (`:339`), `build_record` (`:~380-440`) | accept a report whose failed set equals `accepted_failures` = `{G1}`; both runs equal; `known_failures` in the record | none expected; `test_freeze_corpus.py` fixtures lack the new keys, so the code must treat them as absent = `[]` |
> | `Makefile` `gate-corpus` | `ACCEPT_FAILED` pass-through | none |
> | `decisions.md` | ADR-014, appended | none |
> | `data-card.md` §7 | a status paragraph and the history line (written in 3.6's Block C) | none |
> | `docs/super-plan.md` exit line | the author's amendment | the banner reads the line |
>
> **Unknowns this form adds:** whether exit code 3 is acceptable to `make` and to the plan's steps; whether `passed: false` with a
> digest present confuses any reader of the report (`freeze_corpus.py` reads `snapshot_digest` and `passed` separately);
> whether the opt-in could be widened by accident later (the design binds it to `G1` and to `v1` in code and in a test).

# Impact — g1-statistic (spec draft 5, rule R2)

**Read this first.** No frozen value in the usual list moves (0.85, 0.2, chunking, `top_k`, the embedding model, δ,
`dataset_version`). But the change touches what the **submitted proposal** says about G1. `Final_Proposal.md:436`
says "G1 requires **enough** high-similarity / low-overlap pairs to detect a signal at all". `:497` pre-registers the
response to a G1 failure: "reported as a corpus finding that bounds C1's applicability — not engineered around". R2 turns
"enough" into "≥ 1". It does not touch the corpus, so it is not "engineered around" in the letter. Still, ADR-014 must quote
both lines and say how R2 fits them. Both lines are the author's, and this task does not edit them.

| Package | Touched | Layering |
| :--- | :--- | :--- |
| `experiments/scripts/corpus_gate.py` | yes | ok: no new import |
| `experiments/scripts/freeze_corpus.py` | no | — |
| `docs/` (data-card §7, decisions, super-plan) | yes | — |
| `rag/`, `gateway/`, `docs/contracts/` | no | — |

## 1. Where the floor of 50 and the combined form live

| file:line | What | Under R2 |
| :--- | :--- | :--- |
| `corpus_gate.py:14` | docstring table "≥ ~50" | change |
| `corpus_gate.py:29`, `:773` | "G1 counts within-split pairs" | reword: "in each split" |
| `corpus_gate.py:86` | `G1_MIN_PAIRS = 50` | change |
| `corpus_gate.py:810-826` | `check_g1`: pass, "(need >= 50)", detail | change |
| `corpus_gate.py:1547` | **the combined form**: one `check_g1` over both splits' pairs | one call per split |
| `freeze_corpus.py` | no criterion name, no count, no 50 | none |
| `Makefile:409` | comment "G1..G5" | none |
| `data-card.md:294`, `:306`, `:331` | form note · G1 row "≥ ~50" · `TODO(W8)` | change (A2) |
| `decisions.md:1230` (ADR-013) | "G1 within split" | append-only: ADR-014 supersedes it |
| `super-plan.md:364` | "50 needed" | progress line |
| corpus-freeze `spec.md:108` (S1), `plan.md:95,123,150-151`, `design.md:191` (U5), `impact.md:149` | cite 50 | 3.6's edits (spec A8) |
| corpus-freeze `evidence/gate-failure.md:8,13`, `approvals.md:75`, `review.md:77` | the failure | history: keep |
| 3.4 trail `design.md:243,365,403,498`, `spec.md:98` | "G1 within split" | closed trail: keep |
| **author's:** `Final_Proposal.md:436,497` · `CLAUDE.md:129` · `README.md:150` | "enough" · "G1–G5" · "G1–G5" | 436/497: ADR must reconcile; the other two need no change |
| `interfaces.md` | no hit | none |

| Test (file:line) | Asserts | Under R2 |
| :--- | :--- | :--- |
| `test_corpus_gate.py:215` `test_g1_needs_the_floor` | 49 fails, 50 passes | **stale** (A4) |
| `test_corpus_gate_freeze.py:565` `test_the_breakdown_leaves_g1_and_g2_as_defined` (`:578`) | 1 pair fails | **stale** (A4) |
| `test_corpus_gate_freeze.py:814` `test_main_runs_the_index_check_then_writes_the_new_report_keys` (`:817-818`, fixture `full_run :742`) | exit 1, "[FAIL] G1" | **unknown**: depends on whether the 4-query fake gives a pair in each split. Run it, do not edit it |
| `test_corpus_gate.py:769` (`:781`) | name ends "(within split)" when that scope is passed | neutral if `check_g1(pairs, scope)` stays |
| `test_corpus_gate_freeze.py:964` `_criteria_all_green` | stubs `check_g1(pairs, scope="")` | neutral if the signature stays |
| `test_corpus_gate_freeze.py:872` (`:887-888`) | key names | neutral |
| `test_freeze_corpus.py:240` `_report` (`:251-262`, "need >= 50", 30/30), `:540` | stub strings only | neutral (old text, never parsed) |

## 2. Frozen values, report, contract

- Frozen values: none. The 73 reads δ but does not set it.
- `criteria` goes from 8 entries to 9 (G1 validation, G1 test, like G2). `compare_runs` (`freeze_corpus.py:339`) compares
  the ordered `(name, passed)` list, so it does not depend on names or count. Both runs only need the same code.
- `statistics.g1_pairs_within_split` stays. New keys pass into the freeze record by themselves (`:432`). No record exists
  yet (`FREEZE_VERSION = 1`), so nothing breaks.
- `interfaces.md` v0.15 has no gate surface. **No contract phase.**

## 3. Reachable traps

| Where | Definition |
| :--- | :--- |
| 3.4 `evidence/partner-cosine.md`, `tools/partner_cosine.py:39-40` | a probe (`pair_of` set) that is not `name-swap-same`, with cosine to its partner ≥ 0.85 |
| `corpus_gate.py:654` `trap_fraction` | stratum B-within/B-cross minus `NOT_A_TRAP` (`:96`). No reachability |
| `build_workload.py` | no definition |

The gate has every field it needs: `Query.pair_of` (`:200`), `probe_kind`, `stratum`, `split`, `embedding` (stage 2,
`:806`) and `cosine` (`:679`). W2 (`:490-538`) guarantees that no `pair_of` crosses a split. Run 1 found 0 of 1,274
vectors different from the 3.4 file. So the gate must give exactly **74 of 129 (validation) · 108 of 155 (test) · 182 of
284**. The spec's "about 74 / 108" can be written as exact numbers.

## 4. Runs

`experiments/results/` holds only `.gitkeep`. **Invalidates: none — no runs yet.** 3.6 run 1 (gitignored
`data/v1-draft/gate/run1/report.json`: 8 criteria, G1 13 + 8, 18 across, 1,342) stays as history. Under R2 it would
pass. It has the old shape, so it can never be run 1 of a freeze.

## 5. Phases

No new dependency (plain-Python cosine). No §12 item comes back. Measurement: yes, because the gate is a measurement
and the rule decides how its output is read.

Smallest change: one constant, one call site, the messages, one reported count. Keep `check_g1(pairs, scope)`. Do not
touch `freeze_corpus.py`. Print 73 with its formula; do not compute it from δ in code.

> **Required phases:** impact · experiment · implementation (scope L: plus design and opus design review; no contract)

## Unknowns the design must settle

1. Wilson **two-sided** z = 1.96 gives 73. One-sided 1.645 gives 52. The ADR names which one. δ is provisional, so write "at δ = 5 %".
2. Trap by stratum (`trap_fraction`) or by `pair_of` (3.4 tool)? Pick one. Assert that both give 284.
3. Cosines near 0.85 (policy-kind max 0.852). Show that the gate's `cosine` gives 182, not 181 or 183.
4. The `full_run` outcome under R2 (row 3 of the test table).
5. The names of the two G1 entries, and the stats key for reachable traps.
6. T4 / A5: compare the re-run with run 1's statistics by hand. `compare_runs` cannot pair reports of different shapes.
