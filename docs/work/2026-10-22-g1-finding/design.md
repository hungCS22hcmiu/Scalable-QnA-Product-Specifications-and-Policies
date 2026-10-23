# Design — g1-finding

Scope **L**. Draft 2, 2026-10-23 (draft 1 + the design review, `review.md`). For `spec.md` draft 7. Nothing here is built.

## 1. The idea in one picture

```
Block 0   run 1's report preserved (first-run/) and its snapshot digest pinned          [done 2026-10-23]
          ADR-014 written and committed FIRST (finding, bounds, mechanism, pin, memory scale, exit wording)
Block A0  memory scale: 1 = green, one named constant, checks/messages/comments corrected
Block A   corpus_gate.py   --accept-failed G1      (opt-in · G1 only · version v1 · digest == pinned constant)
             G1 FAIL, all else PASS, no S3/S4/S5 flag
                │  passed=false (strict, unchanged)   freezable=true   accepted_failures=["G1"]
                ▼  prints the digest under "FREEZE WITH A RECORDED FAILURE (G1, ADR-014)"   exit 3
Block B   freeze_corpus.py freeze  <run1>/report.json <run2>/report.json     (3.6 runs these, in NEW folders)
             accepts iff failed criteria == non-empty accepted_failures == {G1} in BOTH runs, same set,
             and the digest == the pinned constant
                ▼
          data/v1-freeze.json   known_failures: [{criterion: G1, adr: ADR-014, counts…, floor: 50}]
Block C   the new statistics checked against the real workload (no Redis, no Ollama)
```

Default behaviour (no flag) is **today's, byte for byte**, apart from the memory-scale numbers in A0. That keeps every other test as it is.

## 2. Function contracts

### 2.1 `corpus_gate.py`

| Item | Contract |
| :--- | :--- |
| `GREEN_LEVEL = 1`, `PRESSURE_NAMES = {1: "normal", 2: "warn", 4: "critical"}` (A0) | the single definition of green. The S3 message, the `flags` list and the S3 count use it. `memory_pressure_level()` still returns the raw sysctl value or `None` |
| `ACCEPTABLE_FAILURES = ("G1",)`, `ACCEPTABLE_VERSION = "v1"`, `FINDING_ADR = "ADR-014"`, `ACCEPTED_SNAPSHOT_DIGEST = "a5708fef…bb2e4"` (the full value from `evidence/first-run-pin.md`) | module constants; the only place the allowance is named |
| `--accept-failed ID[,ID…]` | default none. Any id not in `ACCEPTABLE_FAILURES` → `SystemExit` with a message, before any work. `--version` must equal `ACCEPTABLE_VERSION`, else `SystemExit`. Validated next to the other early checks |
| `failed_ids` | `{c.name.split()[0] for c in criteria if not c.passed}` (`G1`, `G2`, `G3`, `W`, `S` …; every name begins with its id and a space) |
| `accepted` | `failed_ids ∩ set(args.accept_failed)`, **and empty unless `digest == ACCEPTED_SNAPSHOT_DIGEST`** |
| `freezable` | `failed_ids` non-empty and `failed_ids ⊆ accepted` and `not flags`. `passed` stays `criteria_passed and not flags` |
| digest | printed and recorded when `passed or freezable` |
| banner when `freezable and not passed` | `--- FREEZE WITH A RECORDED FAILURE (G1, ADR-014) ---`, the digest, the failed criterion with its counts and floor, "this is not a pass". After the criteria list: "G1 failed and is accepted as a recorded failure (ADR-014)" |
| banner when the flag was given but not honoured | says why: digest differs, or another criterion failed, or a flag was raised |
| exit code | `0` if `passed`; `3` if `freezable and not passed`; `1` otherwise. In the module docstring and the Makefile comment. The docstring lines 5 – 6 ("freezes only when all pass") are updated |
| report | existing keys unchanged. New: `freezable`, `accepted_failures`, `flags`, `statistics.reachable_traps`. `passed` stays `false` for an accepted run |
| `reachable_traps(queries) → {split: {kind: {"records": n, "reachable": m, "pairs": p, "pairs_reachable": q}}, "whole": …}` | 3.4's definition (`partner_cosine.py:72`): a trap is a probe whose `probe_kind` is one of the trap kinds (not `name-swap-same`) and whose `pair_of` is set; reachable when `cosine(probe, partner) ≥ SIM_FLOOR`. `pairs` counts a twin pair once (both records name each other). Uses the vectors the gate already holds. Pure |
| printing | beside the G1 line: the reachable-trap table, labelled "reported, not gated", with **no sample size** |

### 2.2 `freeze_corpus.py`

| Item | Contract |
| :--- | :--- |
| `run_problems` | the "did not pass" problem is raised unless `r["passed"]` **or** the third path holds: `acc = r.get("accepted_failures", [])` is non-empty, `failed = {c["name"].split()[0] for c in r["criteria"] if not c["passed"]}` equals `set(acc)`, `set(acc) ⊆ ACCEPTABLE_FAILURES`, `r.get("freezable")` is true, and `r["snapshot_digest"] == ACCEPTED_SNAPSHOT_DIGEST`. A report without the new keys has `acc = []`: every existing fixture and test is unchanged. The memory check reads `GREEN_LEVEL` from the gate (A0) |
| `compare_runs` | one added check: `r1.get("accepted_failures", []) != r2.get("accepted_failures", [])` → "the two runs accept different failures" |
| `build_record` | adds `known_failures`: for each accepted id, `{criterion, adr: FINDING_ADR, floor: G1_MIN_PAIRS, counts: statistics.g1_pairs_within_split, across: statistics.g1_pairs_across_splits}`; `[]` when nothing was accepted. `FREEZE_VERSION` stays 1: no record exists yet |
| `verify` | unchanged |
| `forbidden_content` | unchanged; counts only |

### 2.3 `Makefile`, `verify_admission.sh`

`gate-corpus` passes `$(if $(ACCEPT_FAILED),--accept-failed $(ACCEPT_FAILED),)`; its comment says: `ACCEPT_FAILED=G1` only for the two `v1` freeze runs, under ADR-014, with `REPORT=` and `RETRIEVAL_OUT=` pointing at **new** folders. A0: the `measure` guard accepts `1` and refuses `2` and `4` with a message that names the three levels; the echo lines at about 330 and 367 and the comments at about 54 and 419 say "1 = normal (green)"; `verify_admission.sh` line 10 says "want 1".

### 2.4 Documents (this task)

`decisions.md` gets **ADR-014**, written and committed first (contents in `spec.md` A1). `gate-corpus` help text and the gate's docstring are updated in code blocks. `data-card.md` §7 (including line 258, which becomes false) and 3.6's other documents are written by 3.6's Block C.

## 3. Failure modes

| Failure | Silent? | Guard |
| :--- | :--- | :--- |
| The allowance is used for another criterion, another version, or other files | would be | arg parser; the pinned digest in the gate **and** in `freeze`; a test for each |
| `freezable` true although another criterion failed | would be | `failed_ids ⊆ accepted` in the gate; `freeze` re-derives the failed set from the report's `criteria` |
| A flagged run (S3, S4, S5) is frozen under the allowance | would be | `freezable` requires `not flags`; `freeze` still runs its own S3 – S5 checks |
| Run 2 skipped the flag or accepted a different set | would be | the added check in `compare_runs`; the `(name, passed)` lists must already match |
| The record hides the failure | would be | `known_failures`; `passed:false`; the banner; exit 3 |
| A reader takes a digest as a pass | would be | banner, exit 3, `known_failures`, ADR-014, the `data-card.md` status paragraph (3.6) |
| The re-run overwrites run 1 and T4 compares it with itself | would be | run 1 preserved in `first-run/` with hashes; 3.6 writes to new folders |
| Reachable traps read as a power claim | would be | no sample size anywhere; records and unique pairs side by side; ADR text says what they do not show |
| A0 changes the memory number and a test stubbing `0` fails | loud | the author confirms the numbers-only edit before it is made (T7) |
| A0 and the allowance edited together hide each other's failures | possible | A0 is its own block, committed alone, and `make verify` is run after it and after each later block |

## 4. Edge cases

- G1 passes in a future run: `accepted_failures` is `[]`, `passed` is true, the banner is the ordinary one.
- Two failed criteria, one accepted: `freezable` false; "NOT FROZEN — a criterion failed" as today, plus the reason the flag was not honoured.
- `--accept-failed G1` on a corpus other than `v1`, or with a changed file: refused with the reason.
- A comma list with spaces or repeats: stripped and collapsed.
- A report from an older gate (no new keys): `freeze` treats it as accepting nothing.
- Exit code 3 under `make`: the target shows "Error 3". The plan's steps read the report, not the exit code.
- A `full_run` fixture query with `pair_of` but no `probe_kind` (`t2`): `reachable_traps` ignores it (3.4's definition). Agreement of the three trap definitions is checked on the real data in Block C only.

## 5. Unknowns that still need verifying

1. **Unique-pair counts 45 and 67** come from the design review's script. Block C reproduces them with the gate's function.
2. **Cosines at the edge.** The policy-kind maximum is 0.852. The gate's `cosine` must give 182 exactly (A5).
3. **Exit code 3 and `make`**, confirmed by running the target with the flag in a scratch case.
4. **`test_main_runs_the_index_check_then_writes_the_new_report_keys`** and the other `full_run` tests: default path unchanged, so they should pass; run, not edit.
5. **Whether the digest pin is robust to `assemble`**: `data/v1/` is rebuilt deterministically (A1 of 3.6 checks sha256 equality); confirmed once more in Block C by recomputing the digest from a fresh `assemble` into a scratch directory.
6. **The Phase 3 exit wording** is the author's; the hook reads that line. This task does not edit it.
7. **What "bounds C1's applicability" says in the thesis** is the author's and the supervisor's.

## 6. Order of work

0. **Block 0 (docs, no source).** Preserve run 1 and pin the digest: **done** (`evidence/first-run-pin.md`). Write ADR-014; **commit it**. *Check:* `git log` shows it before any code.
1. **Block A0 (memory scale).** The author confirms the test edits first (T7). A failing test first: readings `[1, 1, 1]` are green, `[1, 2]`, `[1, 4]`, `[1, None]`, `[1, True]`, `[]` are not (gate S3, `freeze`). Then the constant and the checks, then the Makefile and `verify_admission.sh` text. The listed existing tests change by their numbers only. *Check:* new tests pass; `make verify` green; a grep shows no `0 = green` left outside CLAUDE.md and README.md.
2. **Block A (gate).** Failing tests first (A3), then `--accept-failed`, the pin, `freezable`, banner, exit 3, `reachable_traps`. *Check:* new tests pass, old pass unedited; `make verify` green.
3. **Block B (freeze tool).** Failing tests first, then `run_problems`, `compare_runs`, `build_record`. *Check:* same.
4. **Block C (real data, no Redis, no Ollama).** `reachable_traps` on the real workload and vectors file: 74/129, 108/155, 182/284 and 45, 67; the three trap definitions agree on 129 and 155; the digest recomputed from a scratch `assemble` equals the pin. *Check:* A5.
5. **Close.** `/verify`, `/ai-review`, `/done`; hand off to 3.6 (A10). No gate run on `v1` is made here.
