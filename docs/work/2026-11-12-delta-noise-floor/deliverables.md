# Deliverables — Finalise δ against the judge's measured error (item 5.3)

Closed 2026-11-12 · super-plan item 5.3 · ADR-026 · pre-registration Entry 7

## What shipped

- `noise_floor.py` and `make ablation-floor`. They count `judge-v1`'s errors on hits against the author's locked
  labels (item 5.2) and write `ablation/floor.json`. The same module holds `corrected_rate`, the Rogan–Gladen
  correction with a deterministic Wilson-box interval (`z` 2.394), for the frontier (6.2) to import.
- **ADR-026:** δ = 5 %, final. The judge's false-alarm rate (the noise floor) is above it, so `judge-v1` alone cannot
  certify δ. A point **holds δ** when its corrected rate is ≤ 5 %; it is **certified at δ** only when its interval's
  upper end is ≤ 5 %. The thesis says "holds δ", never "certified".
- **Entry 7:** δ, the floor, the correction, the two rules and `floor.json`'s sha256, before any 6.1 entry.
- Docs: the δ row and a Summary row in `decisions.md`; M08 in `metrics.md`; §I in `interfaces.md`, **v0.34**.

## Files changed

- New: `experiments/scripts/noise_floor.py`, `experiments/tests/test_noise_floor.py` (28 tests), and the cost run's
  `ablation/floor.json` (counts and hashes, no text).
- Modified: `Makefile`, `docs/decisions.md`, `docs/preregistration.md` (46 lines added, 0 removed),
  `docs/contracts/metrics.md`, `docs/contracts/interfaces.md`.
- **Frozen values:** δ is finalised, and its value stays 5 %. New frozen values: the correction formula, its interval
  method at `z` 2.394, and the two rules. **Prior runs invalidated: none.**
- Not this task: `gateway/cmd/gateway/main.go` (the drain fix) is still uncommitted.

## How it was verified

Main session, 2026-11-12, after the executor:
- `make verify` → exit 0. Every Go package `ok` (cached; 4 have no test files); rag 94 passed; experiments 1248 passed
  (1220 + 28 new). No SKIPPED target.
- DC 1 → `floor.json` gives 7/52 [0.0668, 0.2527], 7/27 [0.1317, 0.4468] and 14/79 [0.1086, 0.2758]; the cross-check
  against `scores.json` prints `True True True`.
- DC 2 → 28 passed. The fixture has different margins (miss 2/7, 1 − precision 3/8); R5 and every refusal are tested.
- DC 3 → the ADR-026 heading, its Summary row and the δ row; its counts equal `floor.json`'s; it has `Invalidates:`.
- DC 4 → Entry 7 at 08:36Z; `(empty)` four times; `results/` holds only the cost run; sha256 `ca82488e…6204` equal.
- DC 5 → 165/1000 → 0.0501 [0, 0.3038]; 0/200 inconsistent; the swap, grid and 10× tests pass; 0.0501 is in M08.
- DC 6 → M08 cites ADR-026 and no longer says "provisional"; `v0.34` is in `interfaces.md` four times.
- DC 7 → recomputed by the main session: 530 hashes, and the `diff` with `sha_before.txt` prints nothing.
- DC 8 → under the test folders, only `?? experiments/tests/test_noise_floor.py`.

## Numbers

All `citable: no`. Source: the cost run `2026-11-01T21-17-56_cfg4_judgecost` (corpus `v1` validation, configuration 4,
gate on, MIXED off, τ 0.85, `mutation: off`; pressure 1–2 while it was judged, and verdicts at temperature 0 do not
depend on load). The floor step loads no model. Intervals are Wilson 95 %.
- Hits (79): **false alarm 7/52 = 0.135 [0.067, 0.253]** (the noise floor); miss 7/27 = 0.259 [0.132, 0.447];
  disagreement 14/79 = 0.177 [0.109, 0.276].
- Bucket `1.0`: false alarm 7/51, miss 7/18, disagreement 14/69. Bucket `below 1.0`: 0/1, 0/9, 0/10.
- With the labels as they were before 5.2's deviation: 7/51, 8/28, 15/79.
- Correction: 165/1000 → 0.0501 [0, 0.3038]; 134/1000 → 0 (unclipped −0.001) [0, 0.2307]. A true 5 % is judged
  about 16.5 %; a corrected 3.5 % is a judged 15.6 %.

## Deferred and follow-ups

- **Executor deviations, accepted:** the box check runs before the division (a 0 denominator had crashed); an extra
  refusal when the floor has no author-`correct` or no author-`incorrect` hit; for `n` 0, `consistent` is `None` and
  `z` is kept; step 2.3's fixture has 46 keys (8 keys are refused as too uncertain, tested apart).
- Cosmetic: `floor.json` holds one `-0.0` (a Wilson lower bound in `below 1.0`), from `select_pqa.wilson`'s rounding.
  The correction does not use it.
- **For 6.1-b:** choose "holds δ" or "certified at δ" for the selection objective. With this floor, no point can be
  certified.
- Not measured: whether `FA` and `MI` stay the same at other configurations, τ values and strata (ADR-026). More
  author labels would narrow the floor (its n are 52 and 27).
- **The Phase 5 exit is not met** (run 2026-11-12): agreement is recorded (5.2) and δ is final (5.3), but
  `make figures` exits 2 because `make_figures.py` does not exist (5.4).
