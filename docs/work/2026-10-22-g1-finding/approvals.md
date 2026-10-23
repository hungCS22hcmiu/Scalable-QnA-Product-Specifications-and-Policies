# Approvals — g1-finding

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | yes      | 2026-10-23 | ADR-014 (to write first, plan step 2) |
| contract       | if §B/§D | not required (`impact.md` §2 and §4: `interfaces.md` v0.15 holds no gate surface) | | |
| experiment     | if measured | yes   | 2026-10-23 | ADR-014 (to write first, plan step 2) |
| implementation | always   | yes      | 2026-10-23 | ADR-014 (to write first, plan step 2) |

**Opened 2026-10-22** as `g1-pair-supply` by `/task`, after item 3.6 stopped under S1 (G1 = 21, floor 50). The purpose
changed twice and the folder was renamed twice (`g1-statistic`, then `g1-finding`). Scope **L**: it adds a gate path on a
measured criterion, edits a frozen document (`data-card.md` §7) and needs an ADR.

**Decisions made by the author in chat, in order (2026-10-23):**
1. S1's option (2), reworking the workload, was chosen; a check on existing data then found no support for it. **Void.**
2. Follow the recommendation to change the G1 rule, then rule **R2** (an existence check). **Void.** The impact analysis
   found that `Final_Proposal.md:497` pre-registers the response to a G1 failure as a reported corpus finding, "not
   engineered around", and R2 would move the line it names.
3. **Current: follow the recommendation and the sub-agent's finding — keep G1 and its failed result, and freeze `v1` with the
   failure on record** (S1 option (1) plus a narrow, explicit allowance in the gate and the freeze tool). Chosen by the
   author in chat, 2026-10-23.
4. ADR numbers: this task writes ADR-014; item 3.6's freeze ADR becomes ADR-015.
5. The memory scale: `1` is green; the code fix is a step of the 3.6 re-run (see `spec.md`).

**State of the trail (2026-10-23):** `spec.md` draft 7 · `impact.md` (subagent, written for R2, with an addendum for this
form) · `design.md` draft 2 · `review.md` (opus `design-reviewer`: right shape, seven findings, all applied) · `plan.md` draft 1 ·
`evidence/` (`l2-feasibility.md`, `first-run-pin.md`). `impact-l2-levers.md` is history. Run 1's report is preserved in
`data/v1-draft/gate/first-run/`. Nothing is approved. **No source or test file is touched.**

**What the author is asked to approve, and to decide:**

| Item | Answer | When |
| :--- | :--- | :--- |
| `/approve impact` (the blast radius: `impact.md` with its addendum, and the finding on `Final_Proposal.md:436, :497`) | **yes** (`/approve impact`, typed by the author) | 2026-10-23 |
| `/approve experiment` (the form: pinned, opt-in allowance for G1 on these files; the reachable traps reported with no sample size; stop rules T1 – T7; acceptance A1 – A10) | **yes** (`/approve experiment`, typed by the author) | 2026-10-23 |
| Confirm the memory-scale test edits (numbers only: green `0 → 1`, the old yellow `1 → 2`), after plan step 4 lists them | | |
| The "How C1 is read" paragraph (`spec.md`) is acceptable as proposed | | |
| The Phase 3 exit wording (`spec.md` question 2): the author edits `docs/super-plan.md` or says to | | |
| Whether the supervisor sees ADR-014 first | | |
| `/approve implementation` (after the ADR is committed) | **yes** (`/approve implementation`, typed by the author) | 2026-10-23 |

**Impact approved 2026-10-23** by the author (`/approve impact`), on `impact.md` with its addendum. This approves the
blast-radius reading only: the files and targets touched (`corpus_gate.py` `main`, `freeze_corpus.py` `run_problems` /
`compare_runs` / `build_record`, the `Makefile`, `verify_admission.sh`, `decisions.md`, and later `data-card.md` §7), the finding
that **no frozen value moves** (0.85, 0.2, 50, chunking, `top_k`, the embedding model, `dataset_version` all stay) and that the
proposal's lines 436 and 497 govern the response to a G1 failure. Two things the reader should know: the addendum on this form was
written by the main session, not the impact analyst, and the design review (`review.md`) read it and found it consistent; and the
analysis itself was written for rule R2, so only the sections the addendum names still apply.

**Invalidates: none — no runs yet** (`experiments/results/` holds only `.gitkeep`; Redis holds `dev-v0`, no cache key). It changes
how item 3.6's first gate result is read and which numbers 3.6's trail cites. It replaces no corpus file, no workload file and no
digest input: the pinned snapshot digest `a5708fefa62c…` is the digest of the files as they stand.

**It does not approve** the experiment phase (the pinned allowance, stop rules T1 – T7, acceptance A1 – A10), the memory-scale
test edits, the "How C1 is read" paragraph, the Phase 3 exit wording, or implementation. Those are the other rows above.

**Experiment approved 2026-10-23** by the author (`/approve experiment`), on `spec.md` draft 7, `design.md` draft 2 and `plan.md`
draft 1. It fixes, before any further gate run on `v1`: the **form** (keep G1, its threshold 50, its pair definition and its
failed result unchanged; freeze `v1` with the failure recorded, which is a fourth option beyond S1's three, chosen by the author
after seeing 21); the **mechanism** (an opt-in `--accept-failed G1`, only for `dataset_version v1`, only when the snapshot digest
equals the pinned `a5708fefa62c…`, `passed` stays `false`, exit code 3, `known_failures` in the freeze record, both runs must
accept the same set); the **reported statistics** (reachable traps per split and probe kind, as records and as unique pairs, with
**no sample size and no power claim**); the **stop rules T1 – T7**; **acceptance A1 – A10**; and that the memory scale is read as
`1` = green from Block A0 on. **Changing any of these after the first run of the new code needs this phase approved again.**

**Invalidates: none — no runs yet** (`experiments/results/` holds only `.gitkeep`). The run that already exists, item 3.6's
first gate run, is not invalidated: it stands as the finding, and its report is preserved in
`data/v1-draft/gate/first-run/` (hashes in `evidence/first-run-pin.md`).

**It does not approve**, and these stay open in the table above: the memory-scale **test edits** (T7: no test is edited until the
author confirms the list of plan step 4), the "How C1 is read" paragraph, the Phase 3 **exit wording**, whether the supervisor sees
ADR-014, and **implementation**. ADR-014 is still unwritten; T3 forbids code before it is committed.

**Implementation approved 2026-10-23** by the author (`/approve implementation`), after impact and experiment; the contract phase is
not required. `READY_TO_IMPLEMENT` is written. This unlocks the plan, **in its own order and with its own gates**:
- **Plan step 2 (draft ADR-014) comes first.** It is a document. Stop rule **T3** forbids any code before ADR-014 is committed, and
  the commit (plan step 3) is made when the author asks.
- **Block A0's test edits wait for the author's confirmation** of the list in plan step 4 (stop rule **T7**). The approval of
  implementation is not that confirmation.
- Blocks A, B and C follow, each committed alone when the author asks, with `make verify` after each code block.
- **No gate run on `v1` is made in this task.** The re-runs and the freeze are item 3.6's.

**ADR-014 drafted 2026-10-23** (plan step 2), not committed. Three parts of it are marked as the author's to accept: the "How C1 is read" paragraph, the proposed Phase 3 exit wording, and the supervisor line ("not recorded yet"). Every quotation from `Final_Proposal.md` and `data-card.md` was checked by script against the files. T3 holds until the author asks for the commit (plan step 3).

**Memory-scale test edits (plan step 4, T7) — the list, 2026-10-23.** The author said in chat, after ADR-014 was drafted and
committed (a59e0e5): "feel free to execute all of the remaining steps". That is taken as the confirmation of this list **on one
condition set by the spec: each edit changes a number only** (green `0 → 1`, the old yellow `1 → 2`). If any edit needs more than
a number, work stops and the author is asked. The existing tests that assume the wrong scale, and nothing else:

| # | File : line | Test (or fixture) | Change |
| :--- | :--- | :--- | :--- |
| 1 | `test_corpus_gate_freeze.py:774` | `full_run` fixture | readings `[0] * 100` → `[1] * 100` |
| 2 | `test_corpus_gate_freeze.py:855-857` | the report test | `set(readings) == {0}` → `{1}` |
| 3 | `test_corpus_gate_freeze.py:941, 945` | `test_main_flags_a_yellow_reading_and_the_report_keeps_it` | `[0, 0, 1] + [0] * 100` → `[1, 1, 2] + [1] * 100`; `assert 1 in` → `assert 2 in` |
| 4 | `test_corpus_gate_freeze.py:992` | `test_a_yellow_reading_stops_a_run_the_criteria_pass` | `[0, 0, 1] + [0] * 100` → `[1, 1, 2] + [1] * 100` |
| 5 | `test_freeze_corpus.py:302` | the report fixture | `[0, 0, 0, 0]` → `[1, 1, 1, 1]` |
| 6 | `test_freeze_corpus.py:377` | the expected record | `"memory_max": 0` → `1` |
| 7 | `test_freeze_corpus.py:486` | the parametrised refusal | `[0, 1, 0]` → `[1, 2, 1]` |
| 8 | `test_freeze_corpus.py:490` | the parametrised refusal | `[0, None, 0]` → `[1, None, 1]` |

**Checked and left unchanged:** `test_freeze_corpus.py:494` (`[]`) and `:498` (`[True]`: a bool equals 1 in Python, and `freeze`
refuses it because `type(m) is int` is required, so it is a stronger test on the new scale); `:577` (`[2]`: warn, still refused);
`test_corpus_gate_freeze.py:368` (parses the raw sysctl text, no scale); `test_loadgen_footprint.py:480` (a raw reading, no scale).
New tests are added for the corrected scale (plan step 5). They are additions, not edits.

**Still open, and not answered by this approval:** the memory-scale test edits (T7), the "How C1 is read" paragraph, the Phase 3
exit wording (the author's), and whether the supervisor sees ADR-014. **Invalidates: none — no runs yet.**

**Required phases:** impact · experiment (the gate path is a measurement and the allowance decides how a failure is
read) · implementation. The memory-scale correction (Block A0) is part of this task, by the design review's finding 7. Contract: not required (`interfaces.md` v0.15 has no gate surface). Scope L also needs the design
and the opus design review.

**Invalidates:** no run (`experiments/results/` holds only `.gitkeep`). It changes how 3.6's first gate result is read (G1 =
21 becomes a recorded finding, not a stop for rework), and which numbers 3.6's trail cites (S1's list, A3 (ii), A5, "G1 ≥ 50
must pass", the freeze ADR number). It changes no corpus file, no workload file and no digest input.

**Author's items (not done by this task):** the Phase 3 exit wording in `docs/super-plan.md`; the thesis text on C1's
applicability; `CLAUDE.md` and `README.md`; whether the supervisor sees the ADR.

**Closed 2026-10-23 (`/done`).** All 19 plan steps are done. `/verify` passed (731 experiments + 23 rag tests, Go ok, nothing skipped);
`/ai-review` found four items, resolved in `review.md`. `READY_TO_IMPLEMENT` is deleted and the gate is relocked. **Invalidates: none —
no runs yet** (`experiments/results/` still holds only `.gitkeep`); no frozen value moved (0.85, 0.2, 50, the corpus, the workload and
the pinned digest are unchanged). Still the author's, as before: the "How C1 is read" paragraph, the Phase 3 exit wording in
`docs/super-plan.md`, the ADR-014 supervisor line and index status ("proposed"), `CLAUDE.md:44`, `README.md:227`, the thesis text.
