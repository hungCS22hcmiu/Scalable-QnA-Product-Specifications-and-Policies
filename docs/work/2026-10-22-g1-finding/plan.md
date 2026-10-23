# Plan — g1-finding

Scope **L**. Draft 1, 2026-10-23, for `spec.md` draft 7 and `design.md` draft 2. Every step is checkable. No source or test file is
touched until `/approve implementation`, and **no test is edited until the author confirms step 4**. Each block is committed
alone, when the author asks, and `make verify` runs after each code block.

## Block 0 — documents first (no source)

- [x] **1. Preserve run 1 and pin its digest.** Done 2026-10-23: `data/v1-draft/gate/first-run/` (gitignored) and
  `evidence/first-run-pin.md`. *Check:* the hashes in the file match `shasum -a 256` of the three files; the digest begins
  `a5708fefa62c`, as run 1 printed.
- [x] **2. Draft ADR-014 in `docs/decisions.md`** (append only). *Drafted 2026-10-23: 150 lines added at the end plus one index row (line 56); the author reads it next.* Contents: `spec.md` A1. *Check:* each A1 item is present; the
  quotations of `Final_Proposal.md:436, :438, :497, :499` are exact; a grep for an asin or qa_id finds none; the author reads it.
- [ ] **3. Commit ADR-014 alone** (when the author asks). *Check:* `git log` shows it before any code commit of this task.

## Block A0 — the memory scale (the author confirms the test edits first)

- [x] **4. List the existing tests that assert the wrong scale.** *Done 2026-10-23: 8 edits, all numbers only; the list and the basis for the author's confirmation are in `approvals.md`.* For each: file, test, stubbed readings, the one-number change.
  No edit. The author confirms the list in `approvals.md` (T7). *Check:* the list covers every hit of the grep
  `memory_pressure|readings|\[0\]` in `experiments/tests/` that treats `0` as green or `1` as not green.
- [x] **5. Failing tests first.** *Done 2026-10-23: 15 new tests (6 in the gate file, 9 in the freeze file); 8 failed today, for the missing constant, the missing level words in the S3 message, and `[0, 0]` / `[0]` being accepted.* New tests on the corrected scale: readings `[1, 1, 1]` do not raise S3 and let a run pass;
  `freeze` accepts reports with readings `[1, 1, 1, 1]`; `[1, 2]`, `[1, 4]`, `[1, None]`, `[1, True]` and `[]` are refused by
  both. *Check:* they fail today, for that reason.
- [x] **6. The code.** *Done 2026-10-23: `GREEN_LEVEL`, `PRESSURE_NAMES`, `describe_pressure` in the gate; the S3 message names the levels seen; `freeze` reads the constant; Makefile guard, echo lines and comments; `verify_admission.sh`; one docstring in `loadgen_footprint.py`. The 8 listed test edits are numbers only. `make verify`: 694 experiments + 23 rag tests, Go ok, no FAIL, no SKIPPED. `grep` for the old rule finds none in code, Makefile or scripts.* `GREEN_LEVEL` and `PRESSURE_NAMES` in `corpus_gate.py`; the S3 message, the `flags` list and the count
  use them; `freeze_corpus.py` `run_problems` reads the constant; the `Makefile` guard, messages and comments; the
  `verify_admission.sh` comment. The confirmed existing tests change by their numbers. *Check:* new tests pass; `make verify`
  green; `grep -rn "0 = green\|0=green\|want 0\|= 0 first"` over code, Makefile and scripts finds none (CLAUDE.md and
  README.md named for the author).
- [x] **7. The guard, by its shell test.** *Done: the recipe text copied into a scratch Makefile with the sensor stubbed. Level 1 exits 0 and prints OK; levels 2, 4 and 0 fail with the three-level message.* Run the `measure` recipe's condition with `zone` set to 1, 2 and 4 in a scratch
  shell. *Check:* accepts 1; refuses 2 and 4 with the new message. No load is run.
- [x] **8. Commit A0 alone.** *Done 2026-10-23, on the author's instruction to execute the remaining steps.*

## Block A — the gate allowance

- [x] **9. Failing tests first** *Done 2026-10-23: 22 new tests (pin, refusals, accepted run, not-honoured cases, `reachable_traps`); they failed for the missing constants and flag.* (`spec.md` A3, A4): refuses a value but `G1`; a version but `v1`; a digest but the pinned one;
  another failed criterion; S3, S4 or S5 raised; ordinary banner and exit when G1 passes; the accepted run prints the
  recorded-failure banner, exits 3, writes `passed:false`, `freezable:true`, `accepted_failures:["G1"]` and the digest; the
  default path unchanged. Tests for `reachable_traps` on a synthetic workload (records vs unique pairs; `name-swap-same`
  excluded; a probe without `probe_kind` ignored). *Check:* they fail today.
- [x] **10. The code.** *Done 2026-10-23: constants, `parse_accept_failed`, `--accept-failed`, the pin, `freezable`, banner, exit 3, report keys, `reachable_traps` and its printing, module docstring, Makefile `ACCEPT_FAILED`. All old tests pass; the two Block A0 numeric edits are the only edited tests.* Constants, `--accept-failed`, the pin, `freezable`, banners, exit 3, report keys, `reachable_traps`,
  the printing, the module docstring (lines 5 – 6). *Check:* new tests pass, every old test passes unedited.
- [x] **11. Exit code 3 under `make`.** *Done: a scratch recipe that writes a file and exits 3 — `make` printed "Error 3" and the file was still there.* A scratch Makefile whose recipe exits 3. *Check:* `make` stops with "Error 3" and
  the report is still written by the gate.
- [x] **12. `make verify`; commit A** *Done 2026-10-23: 716 experiments + 23 rag tests, Go ok, no FAIL, no SKIPPED. Committed on the author's instruction to execute the remaining steps.* (when the author asks).

## Block B — the freeze tool

- [ ] **13. Failing tests first:** `freeze` accepts two reports that both accept `{G1}`, digest equal to the pin; refuses an
  empty or different set, a report whose failed set differs, runs that accept different sets, a digest other than the pin, a
  report without the new keys under the new path; `known_failures` is in the record with the counts and the floor; the record
  holds no asin, qa_id or path. *Check:* they fail today.
- [ ] **14. The code:** `run_problems`, `compare_runs`, `build_record` as in `design.md` 2.2. *Check:* new pass, old pass unedited.
- [ ] **15. `make verify`; commit B** (when the author asks).

## Block C — the real data (no Redis, no Ollama)

- [ ] **16. `tools/reachable_check.py` in this trail** reads `data/workload-v1.json` and `data/v1-draft/workload/vectors.json`
  and calls the gate's `reachable_traps`. *Check:* 74/129, 108/155, 182/284 as records; 45 and 67 as unique pairs; the three
  trap definitions (by `probe_kind`, by `pair_of`, by stratum) give 129 and 155. Counts only, in `evidence/reachable-check.md`.
- [ ] **17. The pin survives `assemble`.** `freeze_corpus.py assemble` into a scratch directory, recompute the snapshot digest.
  *Check:* it equals the pinned constant.
- [ ] **18. Hygiene.** A grep of every changed tracked file for the asin and qa_id patterns. *Check:* none.

## Close

- [ ] **19. `/verify`, `/ai-review`, `/done`.** Outcome in this file: what shipped; the finding in one sentence; the numbers;
  whether scope L was honest; **the handoff to 3.6** (`spec.md` A10): its S1 text, A3 (ii), A5, the lines that say "G1 ≥ 50 must
  pass", its freeze ADR becoming ADR-015, its re-runs into new folders with `ACCEPT_FAILED=G1`. No gate run on `v1` is made in
  this task.

## Not in this plan

Any gate run on `v1`; the freeze; `data-card.md` §7; changing G1, 0.85, 0.2 or 50; the corpus or the workload; lengthening the
policy documents; the Phase 3 exit wording, the thesis text, `CLAUDE.md`, `README.md`, `Final_Proposal.md` (the author's).
