# Deliverables — Labelling ablation: the judge against the author (item 5.2)

Closed 2026-11-12 · super-plan item 5.2 · pre-registration Entries 5 and 6 (no ADR)

## What shipped

- `label_ablation.py` with five `make ablation-*` targets: draw, rf-sanity, sheet, lock, score. The `rf` command refuses.
- 100 keys drawn by rule: every hit of the frame (79, a census) and 21 MISSes by seed 20261111. The author labelled
  them blind; the labels were locked by the sheet's sha256; a second sheet of the 18 decided disagreements recorded
  whether the reference was wrong (layer 5); the score step wrote `scores.json` and `refcheck.jsonl`.
- `judge-rf-v1` (`judge-v1` with only its prompt changed) is recorded. It failed its sanity check and is used for no
  score. The author's labels are the reference-free side (Entry 6), so "both schemes" are one comparison shown two ways.
- Docs: Entries 5 and 6 in `preregistration.md`; M21, R7's layer-5 fields, R5 and the metric count in `metrics.md`;
  `interfaces.md` v0.33 (§I's `ablation/` files).

## Files changed

- New: `experiments/scripts/label_ablation.py`, `experiments/tests/test_label_ablation.py` (103 tests),
  `experiments/judge/judge-rf-v1.json`, `prompt-rf-v1.txt`, and six files in the cost run's `ablation/` (no text).
- Modified: `Makefile`, `docs/preregistration.md` (109 lines added, 0 removed), `docs/contracts/metrics.md`,
  `docs/contracts/interfaces.md`.
- Gitignored, under `evidence/private/`: `sheet.md`, `sheet.before-ai-review.md`, `refsheet.md`, the three sanity
  logs, and `100Sample Checkers/`. They hold PQA-derived text.
- **Frozen values touched: none. Prior runs invalidated: none.** The cost run is read, never changed.
- Not this task: `gateway/cmd/gateway/main.go` (the drain fix) is still uncommitted.

## How it was verified

Main session, 2026-11-12, after the executor:
- `make verify` → exit 0. Lint clean; every Go package `ok` (cached; 4 have no test files); rag 94 passed;
  experiments 1220 passed. No SKIPPED target.
- DC 1 → Entry 5 (05:41Z) is before the draw (05:58:57Z), the sanity runs (05:59:21, 06:35:42, 06:36:38Z) and the
  sheet (06:43:24Z); Entry 6 (06:37Z) is before the sheet. The score prints both `yes`; `-k entry6`: 7 passed.
- DC 2 → all three logs read `8 of 12 correct, 0 UNPARSED`; Entry 6 quotes it, and the same 4 pairs failed each time.
- DC 3 → `make ablation-draw` prints `identical`; 13 passed. DC 4 → 2 passed; the sheet path is ignored.
- DC 5 → no `verdicts-rf.jsonl` or `rf.json`; all eight 5.1 hashes `OK`; 6 passed.
- DC 6 → `labels.jsonl` has 100 rows, all with sha256 `b3f689e9…c2e5`; `refcheck.jsonl` has 18; 8 passed.
- DC 7 → 10 passed. The main session recomputed (a), (c), (d) and (e) from the label, verdict and sample files
  without the task's code: every number below is equal.
- DC 8 → M21 in R7, the Index and its heading; `v0.33` in four places, its row right after v0.32.
- DC 9 → outside this task, only `gateway/cmd/gateway/main.go` is modified; no existing test is edited.

## Numbers

All `citable: no`. Cost run `2026-11-01T21-17-56_cfg4_judgecost`: corpus `v1` validation, configuration 4, gate on,
MIXED off, τ 0.85, `mutation: off`, before ADR-024. The score loads no model. Author: 72 `correct`, 28 `incorrect`,
0 `unsure`. Intervals are Wilson 95 %.
- Hits (79): agreement 65/79 = 0.823 [0.724, 0.891], κ 0.606; recall of `INCORRECT` 20/27 = 0.741 [0.553, 0.868];
  precision 20/27 = 0.741.
- MISS (21): agreement 17/21 = 0.810 [0.600, 0.923], κ −0.077; recall 0/1; precision 0/3.
- By bucket: `1.0` 55/69 = 0.797 [0.688, 0.875], κ 0.474; `[0.8, 1)` 2/2; `[0.6, 0.8)` 6/6; `below 0.6` 2/2;
  `below 1.0` 10/10 [0.723, 1.000].
- Circularity: **bounded**, A1 0.797 (n 69), A0 1.000 (n 10). A bound from 10 pairs is weak.
- Layer 5: hits 1/79 = 0.013 [0.002, 0.068] (item 44; 14 checked); MISS 0/21 [0.000, 0.155] (4 checked).
- `judge-rf-v1` sanity: 8 of 12, in each of 3 runs.

## Deferred and follow-ups

- **A deviation from Entries 5 and 6** (design.md §4). After labelling, the author read two AI reviews (Argon 4,
  Fable 5.2) and changed 4 labels: 27, 51 and 54 to `correct`, 93 to `incorrect`. The original 70/30 labels are kept
  (sha256 `3776cdda…5cf7`); with them, each agreement above would differ by at most 4 items. Fable 5.2 is a Claude
  model, so "not Claude-marked" does not hold for those 4. The review sent PQA-derived text off the machine once.
  The thesis states this next to the result.
- **The limit:** one labeller and no inter-rater check.
- The 20 plan steps marked `[-]` were superseded by Phases 7–10 after the RCA of step 3.2 (design.md §4).
- On the second sheet, the main session moved each locked label next to its answer (layout only) and wrote in the
  author's marks from chat.
- **For item 5.3:** 17 of the 18 disagreements are the judge's own errors, 1 is a wrong reference. On hits, the judge
  and the author both count 27 of 79 `INCORRECT`, yet they differ on 14 keys.
- **The Phase 5 exit is not met:** δ is not final (5.3), and `make figures` fails because `make_figures.py` does not
  exist (5.4).
