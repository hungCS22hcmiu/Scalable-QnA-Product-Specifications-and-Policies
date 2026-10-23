# Spec — g1-finding

Scope **L**. Opened 2026-10-22 as `g1-pair-supply`, renamed `g1-statistic` and then `g1-finding` on 2026-10-23 as its
purpose changed twice. Status: **draft 7** (draft 6 + the design review). Nothing here is approved.

**How the task got here.** (1) Item 3.6's first gate run failed G1 (13 + 8 pairs, floor 50) and stopped under S1.
(2) First idea: rework the workload to supply more pairs. A check on existing data (`evidence/l2-feasibility.md`) found no
support. (3) Second idea: change G1 into an existence check (rule R2). The impact analysis then found that the **submitted
proposal already says what to do when G1 fails** (`Final_Proposal.md:497`): report it as a corpus finding that bounds C1's
applicability, "not engineered around". R2 would move the line the proposal named. (4) The author chose to follow that:
**keep G1 and its failed result, and freeze `v1` with the failure on record.** (5) The design review (opus) found the form
sound and asked for seven changes, all applied here (`review.md`). `impact-l2-levers.md` and the R2 parts of `impact.md` are
history.

**This is a fourth option.** S1 in item 3.6 listed three next steps "and no other": accept the failure, reopen 3.3 or 3.4,
change the gate statistic. Freezing with the failure recorded is none of them. The author chose it after seeing 21. The ADR
says so plainly, and 3.6's S1 text is updated when 3.6 reopens.

## The change, in one sentence

Let item 3.6 freeze `v1` with **G1 recorded as failed** — G1's rule, threshold, the corpus and the workload all unchanged
— by writing the decision in ADR-014 first and adding one narrow, explicit allowance to the gate and the freeze tool, tied
to **these exact files**, so that the failure is a visible, recorded finding in the freeze record and in `data-card.md`, and
never a silent pass. The same task corrects the memory-pressure scale the new code and the ADR depend on.

## Why this and not a passing G1

- **It is what the proposal pre-registered.** The falsifier row "The corpus itself" (`Final_Proposal.md:497`) names the case
  "the corpus gate cannot pass G1 … even after the structural requirements of the `v1` corpus model and the B-within /
  B-cross split are met. Thresholds in `data-card.md` §7" and its response: "Reported as a corpus finding that bounds C1's
  applicability — not engineered around with further corpus manipulation." Both structural requirements are met: every
  policy document is 4 chunks (≥ 3), and B-within and B-cross are built.
- **Part of the shortfall is structural, and part is a choice.** On the **product** side it is structural: retrieval is
  scoped to a product and a product has about 3 chunks, so only questions about *different* products can have J ≤ 0.2, and
  all 24 such cross-product pairs come from 5 product pairs. Even with every existing pair inside a split the total is 39,
  below 50 (`evidence/l2-feasibility.md`). On the **policy** side it is not structural: most chunks shared by the reachable
  twin pairs are policy chunks (81 of 127 in validation, 106 of 188 in test), which the author controls, and the gate's own
  advice, "lengthen policy documents" (`corpus_gate.py:823-825`, `data-card.md:306`), was **never tried**. It is declined
  here, after the count was seen, because ADR-012 W5 requires the twins to be minimal pairs and because `Final_Proposal.md:497`
  says not to engineer around the finding. The ADR says "declined", not "structural".
- **The 50 has no derivation** (`data-card.md:306` writes "≥ ~50"; `corpus_gate.py` quotes it). That is a weakness of the
  criterion and the ADR tells it as such. It is a reason to report the failure with its caveats, not to change the
  criterion after seeing 21.
- **A passing G1 by redefinition would carry a claim the data cannot back.** R2 would read "enough pairs to detect a
  signal at all" (`Final_Proposal.md:436`) as "at least one".
- **The authority conflict is named, not hidden.** `Final_Proposal.md:438` makes §7 the authority for what to do on a
  failure, and §7 says "fix the corpus" (`data-card.md:306`, `:327`). The ADR quotes both and settles it by `:497` and `:499`.

## What the finding says (the content the ADR records)

Facts, all from the first run (all 53 memory readings were `1`, the normal level, so the run stands):

- G1: **21 pairs inside a split (13 validation, 8 test)**, plus 18 across the splits (not gated), floor 50. Not met.
- G2: B-within 3 in each split (validation 1 built trap + 2 paraphrase pairs; test 2 built traps + 1 coincidence). Met,
  thinly. S5 was not raised.
- G3, G4, G5, `W`, `S`: met. 539 chunks, 164 documents, 1,274 queries.
- Reachable traps (partner cosine ≥ 0.85): **as records, 74 of 129 in validation, 108 of 155 in test, 182 of 284** (3.4's
  figures). **As unique pairs** (146 of the 284 records are mutual twins, each naming the other): **45 in validation, 67 in
  test** (the design review's count; Block C reproduces it). Reported by probe kind.
- **No sample size and no power claim stands beside these numbers.** The proposal counts the false-hit rate over hits
  (`Final_Proposal.md:408`), dropped sample-size planning (`:79`) and expects the RQ2a residual to be non-zero (`:412`). A
  zero-error yardstick would start from the wrong premise (design review, finding 1).

What it **bounds** (for the thesis text, which is the author's): the phenomenon C1 studies is present in `v1` but thin. The
comparison of the reuse rule with the best fixed threshold can be resolved only as finely as those counts allow, and its
intervals must be reported. What it does **not** show: that the rule works, or that it fails.

**How C1 is read, in both directions (to be written in ADR-014 before any C1 run; text proposed for the author).** A null
result is reported as "no difference resolvable on a corpus where the phenomenon is thin, at these counts", never as "the
rule fails" and never as "the corpus is at fault". A positive result is reported with the trap counts (records and unique
pairs) and Wilson intervals, never as "enough traps". Neither is changed after the first C1 run.

## The mechanism (what code changes)

Opt-in, narrow, visible, **pinned to this finding**:

- `corpus_gate.py` gets `--accept-failed G1`. Nothing is accepted by default. Only `G1` is a legal value, only for
  `dataset_version v1`, and **only when the snapshot digest equals the pinned constant**
  `a5708fefa62cec0aef5505e9e5242bc04bf351fd02a2efb5da54a98f211bb2e4` (the digest of the 164 corpus files and 3 workload files
  whose run 1 failed, `evidence/first-run-pin.md`). If any corpus or workload file changes, the allowance stops working.
  With it, a run where G1 is the only failed criterion and no flag (S3, S4, S5) is raised is **freezable**: it prints the digest
  under "FREEZE WITH A RECORDED FAILURE (G1, ADR-014)", exits with code 3, and writes `passed: false`, `freezable: true`,
  `accepted_failures: ["G1"]` and the digest. `passed` keeps its strict meaning. Without the flag, behaviour is exactly today's.
- `freeze_corpus.py freeze` accepts a report only if its failed criteria **equal** a **non-empty** `accepted_failures` set
  `{G1}`, its digest equals the pinned constant, and **both runs** accept the same set. The freeze record gets
  `known_failures` (criterion, ADR, the counts, the floor).
- The gate **reports**, beside G1 and in the record's statistics, reachable traps per split and probe kind, as records and
  as unique pairs. It uses 3.4's definition by `probe_kind` (`partner_cosine.py:72`).
- The `Makefile` passes `ACCEPT_FAILED=G1` to `gate-corpus` for the freeze runs. Re-runs write to **new folders**, never
  to `run1/`.
- The memory scale (Block A0): `1` is green. The checks, messages and comments that say `0 = green` are corrected, with a
  single named constant. See "The memory scale".
- No existing test changes except the memory-scale numbers, and only with the author's explicit confirmation. The allowance
  is opt-in, so every other run, fixture and assertion behaves as before.

## The memory scale (decided 2026-10-23, in this task)

`1` is green. The SDK header says `DISPATCH_MEMORYPRESSURE_NORMAL 0x01`, `_WARN 0x02`, `_CRITICAL 0x04`; the machine read `1`
with 47 % free; the author saw the Activity Monitor graph green while the sensor read `1`. The repository's rule "`0` = green"
is wrong, and the 3.6 records that called run 1 "yellow" are corrected. The design review (finding 7) showed this cannot be
left to the next task: ADR-014 says "run 1 stands" because of it, the new tests depend on it, and the `measure` guard and
`verify_admission.sh` gate every later run. So it is **Block A0 here, not a separate task** (the author asked for no separate
heavy task). The places: in `corpus_gate.py` the docstring of `memory_pressure_level` and the two `m != 0` checks (the S3
message and the `flags` list); in `freeze_corpus.py` the `m == 0` test in `run_problems`; in the `Makefile` the guard and
messages in `measure` (around lines 99 – 101), the echo lines at about 330 and 367, and the comments at about 54 and 419; and
`verify_admission.sh` line 10. The tests that stub readings are in `test_corpus_gate_freeze.py` and `test_freeze_corpus.py`;
the change to each is the number only (green `0 → 1`, the old yellow `1 → 2`). **The author confirms these test edits in
`approvals.md` before any test is edited** (`/bugfix` rule: tests are immutable until an RCA shows them stale and the human
confirms). ADR-014 records the encoding. `CLAUDE.md` line 44 and `README.md` line 227 are the author's to correct.

## Phase and item

Phase 3. It exists so that **item 3.6** can finish. Phase 3's exit criterion reads "G1…G5 all pass and `make gate-corpus`
prints the snapshot digest". Under this decision G1 does not pass, so **the exit line needs an amendment, which is the
author's** (the line is read by `.claude/hooks/lib.sh`). Proposed wording is in the ADR. Scope **L**: it adds a gate path on a
measured criterion, edits a frozen document (`data-card.md` §7), changes the memory rule that gates every run, and needs an ADR.

## Acceptance

- **A1. The ADR comes first.** ADR-014 is written and committed before any code or gate change. It holds: the unchanged rule
  and the first result; the three-part reading of the shortfall (structural for products; **declined** for policy documents,
  after the count was seen); the proposal's falsifier row and lines 436, 438, 497, 499, quoted, and the authority conflict
  settled; the fourth option named plainly; the facts above with reachable traps as records and as unique pairs and **no
  sample size**; the "How C1 is read" paragraph; the pinned digest and the hashes of run 1's files; the mechanism and its
  limits; the memory-scale encoding; what the finding does not show; whether the supervisor has seen it; the proposed Phase 3
  exit wording; and `Invalidates: none — no runs yet`. `git log` shows the order.
- **A2. Default behaviour is unchanged.** Without `--accept-failed` a run prints and records what it did before, plus the
  new reported statistics.
- **A3. The allowance is narrow.** Tests show it refuses: any value but `G1`; any version but `v1`; a snapshot digest other
  than the pinned one; a run where another criterion fails; a run with S3, S4 or S5 raised; a report whose failed set differs
  from `accepted_failures` or is empty; two runs that accept different sets; and that nothing is recorded when G1 passes.
- **A4. The failure is visible.** The freeze record holds `known_failures` with the G1 counts and the floor; the gate banner
  says "recorded failure"; `passed` is `false` in the report.
- **A5. The reported statistics are right.** On the real workload the gate reproduces 74/129, 108/155 and 182/284 as records
  and 45 and 67 as unique pairs, and the three trap definitions (by `probe_kind`, by `pair_of`, by stratum) agree on 129 and
  155. This is a Block C check on the real data, not a runtime assert.
- **A6. Nothing else moved.** `git diff` over `rag/`, `gateway/`, the corpus, the workload files, `docs/contracts/` and the
  constants 0.85, 0.2, 50 is empty. The 3.6 re-run reproduces the first run's counts exactly (21 = 13 + 8; 18 across; 1,342
  high-similarity pairs), compared by hand with the preserved copy in `first-run/`.
- **A7. The memory scale is whole.** No `0 = green` remains in code, Makefile messages or comments (a grep lists what is
  left, and the author's two files are named). The new tests use the named constant. `make measure`'s guard accepts `1` and
  refuses `2` and `4`.
- **A8. `make verify` is green** with Redis on `dev-v0`, and no existing test changed except the numbers confirmed in A7.
- **A9. Hygiene.** No asin and no qa_id in a changed tracked file.
- **A10. Handoff.** `plan.md` ends with: the finding in one sentence, the numbers, and the edits 3.6 must make when it
  reopens (its S1 text, A3 (ii), A5, the plan lines that say "G1 ≥ 50 must pass", its freeze ADR becoming **ADR-015**, new
  folders for its re-runs).

## Stop rules (proposed; they bind once approved)

- **T1. The author does not approve this form.** Close as S1 option (1): the failure is reported and nothing is frozen.
- **T2. A change beyond the allowance and the memory scale** (another criterion, 0.85, 0.2, 50, the corpus, the workload). Stop.
- **T3. The ADR is not committed before the code.** Do not write code.
- **T4. A number of the re-run differs from the preserved first run's** (other than the memory readings). Stop, investigate.
- **T5. The allowance would accept anything but G1 on these files.** Stop; that is a different decision.
- **T6. An asin or qa_id in a tracked file.** Stop, remove, log.
- **T7. The author has not confirmed the memory-scale test edits.** Block A0 does not edit a test.

## Out of scope

- Any change to G1's rule, threshold or pair definition, to G2 – G5, `W`, `S`, the constants 0.85 and 0.2.
- Any change to the corpus, the workload, the policy documents, the split, `K`. In particular lengthening the policy documents
  is declined (above), not forgotten.
- The freeze itself, `data-card.md` §7's markers, the record's other fields, run 2: item 3.6.
- The thesis text on C1's applicability, `Final_Proposal.md`, `CLAUDE.md`, `README.md`: the author's.

## Open questions (for the author)

1. **Approve this form (the pinned allowance, opt-in, G1 on these exact files)?** *Proposed:* yes. The approval itself is
   `/approve experiment`.
2. **The Phase 3 exit wording.** *Proposed:* "G2…G5 pass, G1 is recorded as ADR-014's finding with its counts, and
   `make gate-corpus` prints the snapshot digest under a recorded failure · `K`, the derived capacity and every frozen corpus
   statistic are recorded in `data-card.md` · the validation/test splits are frozen with the dataset." The author edits
   `docs/super-plan.md` or says to.
3. **Do you confirm the memory-scale test edits (numbers only: green `0 → 1`, the old yellow `1 → 2`)?** *Proposed:* yes,
   after the RCA in `plan.md` Block A0 lists each one. Without it, Block A0 stops (T7).
4. **Is the "How C1 is read" paragraph acceptable as proposed?** *Proposed:* yes; it is the author's wording in the end.
5. **Does the supervisor see this before the ADR is final?** *Still open; advice, not a gate.* The ADR says in its text
   whether they have.
