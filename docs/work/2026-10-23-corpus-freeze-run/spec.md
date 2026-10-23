# Spec — corpus-freeze-run (item 3.6, second part)

Scope **L**. Draft 1, 2026-10-23. Opened because item 3.6 stopped under S1 (`2026-10-22-corpus-freeze`) and task `2026-10-22-g1-finding`
then decided and built the way to freeze with G1 on record (ADR-014). The old trail said a successor task would do the freeze. This is it.
Nothing here is approved.

## The change, in one sentence

Run the corpus gate twice on the ingested `v1` with `ACCEPT_FAILED=G1`, freeze `v1` (`data/v1-freeze.json`, with `known_failures`), fill
`data-card.md` §7, write **ADR-015** ("`v1` is frozen"), and put the `dev-v0` index back — without changing the corpus, the workload,
a threshold or any code.

## What is inherited, and what changes

The design and the design reviews are **inherited, not repeated**: `2026-10-22-corpus-freeze/design.md` and `review.md` (the freeze
tooling), and `2026-10-22-g1-finding/design.md` and `review.md` (the allowance, with an opus design review and a code review). The code
is built and committed (`a7c1178`, `33e1ec3`, `37e0e8f`, `e6dc08c`, `fdbe4a9`, `a4cf009`). This task runs it and writes the documents. If you
want a fresh design and review anyway, say so; the ladder asks for them at scope L, and this is the one place the trail skips them.

The old spec's acceptance (A1 – A11) and stop rules (S1 – S5) stand, with these changes, which come from ADR-014:

1. **S1 is rewritten.** The three options it listed are no longer the whole list (ADR-014 added a fourth: freeze with the failure on
   record). Under `ACCEPT_FAILED=G1`, **G1 failing is not a stop**. Any other criterion failing is. G1 failing with counts different from
   the first run (21 = 13 + 8 inside a split, 18 across, 1,342 pairs at cosine ≥ 0.85) **is** a stop (ADR-014, "the counts are compared by hand").
2. **Memory is `1`.** Everywhere the old spec says "level 0" or "green = 0" (A2, A10, S3, step 16), read **1** (normal). Any other reading
   discards the run.
3. **A2:** instead of a `FREEZE` block, each run prints `FREEZE WITH A RECORDED FAILURE (G1, ADR-014)` and the gate exits **3**. `make`
   shows "Error 3" and the report is already written.
4. **A3** adds: (vi) the counts equal the first run's, listed above, and the two retrieval exports have the **same sha256** as the first
   run's (`1e2e1735…` validation, `7a90de70…` test; `2026-10-22-g1-finding/evidence/first-run-pin.md`). The pinned snapshot digest
   `a5708fefa62c…` must be the digest each run prints.
5. **A4** adds: the record holds `known_failures` for G1 (ADR-014, floor 50, the counts 13 / 8 / 18). **A5** is unchanged (K 622 / 652,
   capacity 156 / 163).
6. **A11 becomes ADR-015.** ADR-014 is the finding; ADR-015 says what "`v1` is frozen" binds, that G1 is recorded as failed there, and
   that Redis holds `dev-v0` afterwards.
7. **Both runs go to new folders:** `data/v1-draft/gate/freeze-a/` and `freeze-b/`. `run1/` and `first-run/` hold the failed first run
   and are not written to.
8. **Phase 3's exit line** ("G1…G5 all pass") cannot be met as written. Its wording is **the author's** (`docs/super-plan.md`);
   ADR-014 proposes text. This task runs the exit by hand against the amended line, once the author has set it.

## Acceptance (the old table, as changed above)

| # | Check | Pass when |
| :-: | :--- | :--- |
| A1 | `make corpus-assemble` (again), `ls data/v1` | 164 files; every copy equals its source; the snapshot digest of the 167 files equals the pin |
| A2 | `make gate-corpus ACCEPT_FAILED=G1 …` (each run) | index check PASS; G2 – G5, `W`, `S` PASS; G1 FAIL with 13 + 8; the recorded-failure block with the pinned digest; exit 3; `ungrounded` and `own_chunk_missing` 0; every memory reading `1` |
| A3 | run B from a fresh ingest | (i) – (v) as in the old spec, plus (vi) above |
| A4 | `data/v1-freeze.json`, `make corpus-verify`, `make corpus-index-check` | as in the old spec, plus `known_failures`; no file name, asin, qa_id or absolute path |
| A5 | K and capacity | 622 / 652 and 156 / 163 in the gate output, the record and `data-card.md` |
| A6 | chunk digest | recorded and equal to the one read from Redis |
| A7 | `grep -n "TODO(W8)" docs/data-card.md` | only the three that are not this item's remain; §7 says G1 is recorded as failed (ADR-014), and line 258 ("refuses to print a snapshot hash unless all five…") is corrected |
| A8 | evidence | the carried measurements (U10, U11, U12, sibling rate, unit check) are already in `2026-10-22-corpus-freeze/evidence/probe-checks.md`; re-run `probe_checks.py` on `freeze-a` only if a count differs |
| A9 | `DATASET_VERSION=dev-v0 make ingest`, then `make verify` | green, no test changed |
| A10 | memory | `sysctl kern.memorystatus_vm_pressure_level` reads 1 before each run; the gate's own readings are all 1 |
| A11 | `docs/decisions.md` | ADR-015 exists, says `Invalidates: none — no runs yet`; ADR-014's index status is the author's to move from "proposed" |

## Stop rules (the old S1 – S5, as rewritten)

- **S1.** A criterion other than G1 fails, or G1's counts differ from the first run's, or the printed digest is not the pin. Stop. Write
  the counts into `evidence/`. Edit nothing to make it pass.
- **S2.** The two runs differ on pass or fail, on the accepted set, or in any count: stop (`/investigate`, never a best of three).
- **S3.** Any memory reading but `1`: discard the run, log it, repeat it.
- **S4.** `ungrounded` or `own_chunk_missing` above 0: stop.
- **S5.** G2 met only by paraphrase pairs: stop and show the author.
- **S6.** The code changes during the task (`git` shows `rag/src`, `experiments/scripts` or `Makefile` dirty): the gate's `tree_clean` would
  be false and `freeze` would refuse. Stop and commit or revert first.
- The index check failing is a precondition, not a stop: re-ingest and run again.

## Out of scope

Any edit to the corpus, the workload, a threshold, the code, `gateway/`, `rag/`, `docs/contracts/`. The Phase 3 exit wording,
`CLAUDE.md`, `README.md:227`, `Final_Proposal.md`, the thesis text on C1 (all the author's). A restore path for `data/v1/` (Phase 4).
The faster scoped retriever, `CACHE_CAPACITY` wiring and the stale `K` comment (P1).

## Open questions (for the author)

1. **Inherit the design and the reviews (as above), or ask for new ones?** *Proposed:* inherit.
2. **Does the author read ADR-014 before the freeze?** The freeze record cites it. *Proposed:* yes, and move its index status to "in force" or
   say what to change. Not a gate for the gate runs; it is for the freeze step.
3. **Phase 3 exit wording.** *Proposed:* ADR-014's text. The author edits `docs/super-plan.md` or says to.
