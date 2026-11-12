# Finalise δ against the judge's measured error (item 5.3)

Status: opened 2026-11-12 · spec approved 2026-11-12 · design approved 2026-11-12 · plan approved 2026-11-12 (in chat)
Changed by §3 (2026-11-12): option A is taken (the spec's recommendation; the author approved the spec without
naming another). DC 2, 3 and 5 are sharper. The code is a new script and a new test file (§2).
Changed at design approval (2026-11-12): DC 4's pass also compares Entry 7 with `floor.json` (failure mode 8);
DC 7 counts six existing `ablation/` files, not five.
Super-plan item: 5.3 — Finalise δ against the measured judge error

## 1. Spec

**The change.** Compute the judge's error on hits from item 5.2's locked files into one new file, and fix δ against
it in ADR-026 and pre-registration Entry 7, before item 6.1 writes its first entry.

**Why.** The proposal chose δ "for measurability": the judge's own error against the human sample is the noise
floor of M08, and "a budget below it cannot be certified" (`Final_Proposal.md` §9, "Target operating point").
δ ≤ 5 % stays provisional until that error is known (`decisions.md`, inherited state; `metrics.md` M08). Item 6.1's
selection objective for "the best fixed threshold" needs a final δ.

**Facts this spec rests on.** Worked out by hand from `scores.json` and `labels.jsonl` on 2026-11-12. DC 1 must
reproduce them.
- Source: the 79 hits of item 5.2, from the cost run `2026-11-01T21-17-56_cfg4_judgecost` (configuration 4, gate on,
  MIXED off, `v1` validation, τ 0.85, `citable: no`). The author labelled 27 `incorrect` and 52 `correct`.
  `judge-v1` called 27 `INCORRECT`, and 20 of those are the author's 27.
- **False alarms** (the judge says `INCORRECT`, the author says `correct`): 7 of 52 = 13.5 %, Wilson 95 % [6.7, 25.3].
  All 7 are in the `1.0` overlap bucket (7 of 51).
- **Misses** (the judge says `CORRECT`, the author says `incorrect`): 7 of 27 = 25.9 % [13.2, 44.7].
- **Disagreement:** 14 of 79 = 17.7 % [10.9, 27.6]. 1 of the 14 is a wrong reference (layer 5), so reference error
  is already inside this number, not beside it.
- So a cache with **no** false hits would be judged about 13.5 % wrong, and a true rate of 5 % would be judged about
  16.5 %. Even the low end of the false-alarm interval (6.7 %) is above 5 %. **With `judge-v1` alone, δ = 5 %
  cannot be certified.**
- Verdicts at temperature 0 do not depend on load (5.1 re-judged 30 keys with 0 flips), so the pressure of 1–2
  during the cost run's judging does not change these counts. They stay `citable: no`, like every number from 5.2.
- 5.2's deviation (4 labels changed after two AI reviews) barely moves the floor. With the original labels, the
  hits give 7 false alarms of 51, 8 misses of 28 and 15 disagreements of 79 (items 51, 54 and 93 are hits;
  item 27 is a MISS).

**The choice this task records: (A).** δ stays 5 %. ADR-026 says the judge alone cannot certify it, and M08 prints a
corrected rate beside the judged one (§3). Not taken: (B) raise δ above the floor, past about 25–28 %, which makes a
weak headline; (C) the author labels the hits at every reported operating point, which needs many more labels from
one labeller who also wrote the rule.

**Done conditions.**

1. **The floor is computed by rule.** `make ablation-floor RUN_ID=<id>` reads the run's `ablation/sample.jsonl`,
   `ablation/labels.jsonl`, `ablation/scores.json` and `judge/verdicts.jsonl`, and writes `ablation/floor.json`. For
   hits overall and per bucket (`1.0`, `below 1.0`), it gives false alarms, misses and disagreement, each as k, n,
   rate and Wilson 95 %, plus the correction's `z` and worked value. It refuses if `floor.json` exists, or if a
   label's `sheet_sha256` differs from `scores.json`'s. Pass, on the cost run: 7/52 [0.067, 0.253], 7/27
   [0.132, 0.447], 14/79 [0.109, 0.276]; and these agree with `scores.json` (14 = 79 − 65 from agreement; 7 = 27 − 20
   from recall and from precision).
2. **Unit tests for the floor.** On a fixture where all four cells and both margins differ (so a miss rate taken
   over the judge's `INCORRECT` instead of the author's gives a different number), they pin the three rates and
   their Wilson bounds. They check that an author `unsure` and a judge `UNPARSED` leave the denominator (R5). They
   check every refusal: `floor.json` exists, the label hash differs, and a sample key has no verdict.
3. **ADR-026 fixes δ.** It gives: δ = 5 %, final; the two rules (a point **holds δ** when its corrected rate is
   ≤ 5 %; it is **certified at δ** only when the upper end of the corrected interval is ≤ 5 %); the floor numbers,
   equal to `floor.json`, with the run and `citable: no`; the deviation's effect (7/51 with the original labels); and
   what happens to the 3.5 % second row (`Final_Proposal.md` §9.2). It says that the gap is the reason the judge
   cannot certify δ. It has an `Invalidates:` line. The δ row of "Inherited state" says final, ADR-026, and no
   longer "provisional". Pass: `grep -n "ADR-026" docs/decisions.md` shows the entry and the row, and the entry's
   three counts equal `floor.json`'s.
4. **Pre-registered before the sweep.** `docs/preregistration.md` Entry 7 states δ, the floor, the correction and the
   two rules, with `floor.json`'s sha256. Pass: Entry 7 exists; its three counts and its sha256 equal `floor.json`'s;
   the four 6.1 names still read `(empty)`; `experiments/results/` holds no run other than the cost run.
5. **The corrected rate is a tested function.** Unit tests pin `noise_floor.corrected_rate` with the cost run's
   floor: 165 of 1000 judged gives 0.0501 with the interval [0, 0.3038]; 0 of 200 gives `consistent: false` and no
   interval (never `[0, 0]`); swapping the false-alarm and miss rates changes the result; the interval's ends equal
   the min and max of a brute-force grid over the same box (within 1e-4); and a floor with 10 times the counts gives
   a strictly narrower interval. `metrics.md` M08 gives the formula, the interval method, this worked value and the
   two rules.
6. **Docs.** `metrics.md` M08: the "provisional" sentence points to ADR-026. `interfaces.md` §I: `noise_floor.py`
   and `ablation/floor.json`, as **v0.34**. (`/done` marks the item in `super-plan.md`.)
7. **Nothing locked changes.** The sha256 of the cost run's `raw/`, `manifest.yaml`, `judge/` and the six existing
   `ablation/` files is the same before and after the task.
8. `make verify` passes, and no existing test is edited.

**Out of scope.**
- Any model run, new verdicts, new labels, or a second labeller. Nothing in this task loads a model.
- A new judge version to lower the floor (a new prompt, a new entry, new labels). Possible, but it is a new item.
- The sweep and its selection objective (6.1), any configuration's false-hit rate (6.2), and the figures (5.4).
- Correcting M20 (the miss path): its floor would rest on 21 MISS keys.
- The test split.

## 2. Impact

**Files and boundaries.**
- New `experiments/scripts/noise_floor.py` (the floor and the correction) and new
  `experiments/tests/test_noise_floor.py`. `Makefile`: `ablation-floor`. `label_ablation.py` and its tests do not
  change. Everything stays inside `experiments/`: it reads the run's files and writes one new file. No gateway or
  `rag` change (`architecture.md`).
- New output: `experiments/results/2026-11-01T21-17-56_cfg4_judgecost/ablation/floor.json`, committed. It holds
  counts and hashes, no text.
- Docs: `decisions.md` (ADR-026, its Summary row and the δ row), `preregistration.md` Entry 7, `metrics.md` M08,
  `interfaces.md` §I, and `super-plan.md` at `/done`.

**Frozen values touched.** **δ** (`decisions.md`, inherited state: "δ ≤ 5 %, provisional"). Its value stays 5 %, and
ADR-026 makes it final. **New frozen values:** the correction formula, its interval method with `z` = 2.394, and the
two rules ("holds δ", "certified at δ"), all in ADR-026 and Entry 7 before item 6.1. **New recorded value:** the noise
floor (`floor.json`). Nothing else changes: `judge-v1`, its prompt, the references, `τ_s` and the served generator
stay as they are.
**Prior runs invalidated: none.** No frontier point and no M08 rate has been reported against δ. The only run, the
cost run, is read and never changed (DC 7).

**Contract change.** Outside the gateway seam only: `interfaces.md` §I gains `noise_floor.py` and `ablation/floor.json`
(v0.34). No `.proto`, gateway or `rag` change. `source_chunk_ids`, `t1_key` and `dataset_epoch` are untouched.

**Measurement change.** Yes. M08's budget becomes final, and M08 gains a second number, the corrected rate with its
interval, printed beside the judged rate. The judged rate keeps its meaning and its counting rule, so the rules stay
`counting-v1`. The entry is dated, as M21's was.

**New dependency.** None (standard library and `select_pqa.wilson`). No model loads, so no memory-pressure check is
needed.

**Cut scope reinstated.** No.

**The author's time.** Reading ADR-026 and Entry 7.

## 3. Design

**Approach.** A new script, `noise_floor.py`, reads 5.2's locked files and writes `ablation/floor.json`. The same
module holds `corrected_rate`, which the frontier (6.2) will import. ADR-026 and Entry 7 then quote `floor.json`.
Two alternatives were beaten:
- **A `floor` command inside `label_ablation.py`.** Not taken: that file (1,361 lines) is item 5.2's record, and the
  correction is a separate job.
- **A seeded Monte Carlo interval over Beta draws.** It gives a narrower interval, but Python does not promise the
  same `betavariate` stream across versions, so a recorded interval might not regenerate (5.4). The box below is
  deterministic and conservative.

**The noise floor.** It is computed over the hits of `sample.jsonl` (`stratum == "hit"`, all 79, with the one
`answerable: false` hit counted like any other, R6). Each key gives a pair (judge verdict, author verdict); the
author's word is mapped with `LABEL_TO_VERDICT`. Only decided pairs count: a judge `UNPARSED` or an author `UNSURE`
leaves both sides and is counted in `undecided` (R5). There are four cells:

| | author `CORRECT` | author `INCORRECT` |
| :--- | :--- | :--- |
| judge `CORRECT` | `tn` | `mi` |
| judge `INCORRECT` | `fa` | `tp` |

- **False alarm** = `fa / (fa + tn)`, over the author's `CORRECT`. **Miss** = `mi / (mi + tp)`, over the author's
  `INCORRECT`. **Disagreement** = `(fa + mi) / decided`. Each gets a Wilson 95 % interval (R8).
- The same is printed per bucket (`1.0`, `below 1.0`), but the correction uses only the overall hits. Below 1.0 has
  one author-`CORRECT` hit.
- ADR-026 names the false-alarm rate as **the** noise floor: it is the judged rate of a cache with no false hits.
  The other two are printed beside it.

**The correction** (the Rogan–Gladen estimator). For `k` of `n` hits judged `INCORRECT` at an operating point, with
`FA` and `MI` the floor's false-alarm and miss rates:

`corrected = (k/n − FA) / (1 − MI − FA)`, clipped to [0, 1]. The value before clipping is kept as `unclipped`.

- **Interval.** Each of the three rates (`k/n`, `FA`, `MI`) gets a Wilson interval at `z` = 2.394, the normal quantile
  for 95 % shared over three intervals (Bonferroni: each at 1 − 0.05/3). The corrected interval is the min and max of
  the clipped formula over the 8 corners of that box. Corners are enough: when the denominator is positive, the
  formula is monotone in each rate taken alone (increasing in `k/n`; in `MI` its sign is that of `k/n − FA`; in `FA`,
  that of `k/n − (1 − MI)`). Joint coverage is at least 95 %, so the interval is conservative.
- **Refused:** the denominator `1 − MI − FA` is ≤ 0 at any corner (the judge is too uncertain to correct). With this
  floor its smallest corner value is 0.226.
- **Inconsistent:** the judged interval lies wholly below `FA`'s lower end, or wholly above `1 − MI_lo` (the highest
  rate a judge with this miss rate can give, where `MI_lo` is `MI`'s lower end). The data then contradict the floor:
  it does not hold at this point. `consistent` is false, and `corrected` and `interval` are `None`.
- **Worked values** (to be pinned): 165/1000 gives 0.0501 [0, 0.3038]; 134/1000 gives 0 (unclipped −0.001)
  [0, 0.2307]; 0/200 is inconsistent. Wilson bounds come rounded to 4 decimals from `select_pqa.wilson`, and the
  results are rounded to 4.

**What M08 does at δ (ADR-026).** δ = 5 %, final. M08 prints the judged rate as before and, beside it, the corrected
rate with its interval.
- A point **holds δ** when its corrected rate is ≤ 0.05. It is **certified at δ** only when its interval's upper end
  is ≤ 0.05.
- With this floor no point can be certified: even a judged rate at the floor (134/1000) has an upper end of 0.23.
  The thesis says "holds δ", never "certified". Item 6.1-b chooses which rule its selection uses.
- The 3.5 % row stays a second row on the same scale (a corrected 3.5 % is a judged 15.6 %), also uncertified.
- M20 is not corrected (Out of scope).

**ADR-026's content.** *Decided (method)*, 2026-11-12, the author.
- **Decision:** as above.
- **Rationale:** the proposal's definition; the three numbers; what a cache with no false hits would score.
- **Alternatives:** (B), (C), a new judge version, and the Monte Carlo interval.
- **Consequences:**
  - **The correction assumes that `FA` and `MI` hold at every point, configuration and stratum.** They were measured
    only at configuration 4, τ 0.85, gate on, on validation, and mostly in bucket `1.0`. This is an assumption, not
    a measurement.
  - More author labels would narrow the box: the floor's n are 52 and 27.
  - M20 is not corrected.
- **Invalidates:** none.

**Entry 7's content.** A dated heading (`## Entry 7 — YYYY-MM-DD HH:MMZ — …`), then δ, the floor's three counts with
their Wilson intervals, the formula, `z`, the two rules, the worked value and `floor.json`'s sha256. It is written
before any 6.1 entry, and no entry before it is edited.

**Files.**
- New `experiments/scripts/noise_floor.py`, which imports `label_ablation as la` for `LABEL_TO_VERDICT`, `DECIDED`,
  `AblationRefused`, `_rate`, `_read_jsonl`, `_write_new`, `_ablation_dir` and `_now`.
  - `FLOOR_Z = 2.394`; `BUCKETS = ("1.0", "below 1.0")`; `WORKED = (165, 1000)`.
  - `cells(pairs: list[tuple[str, str]]) -> dict[str, int]`: `tp`, `fa`, `mi`, `tn`, `undecided`. A pair is
    `(judge, author)` in verdict words.
  - `floor_block(pairs: list[tuple[str, str]]) -> dict`: `cells`, `false_alarm`, `miss`, `disagreement`, each
    rate a `la._rate`.
  - `compute_floor(sample: list[dict], verdicts: dict[str, str], labels: dict[str, str]) -> dict`: `hits`, and
    `by_bucket` keyed by `BUCKETS`.
  - `corrected_rate(k: int, n: int, floor: dict, z: float = FLOOR_Z) -> dict`: `judged` (`la._rate`), `corrected`,
    `unclipped`, `interval`, `consistent`, `z`. For `n` 0: `judged` shows n 0, and the rest is `None` (R8).
  - `run_floor(run_id: str, *, results_dir: Path = la.RESULTS_DIR, now=la._now, log=print) -> dict`: the checks,
    then it writes `floor.json` and prints.
  - `format_floor(floor: dict) -> list[str]`. `main(argv: list[str] | None = None) -> int`: `--run-id` and
    `--results-dir`; exits 1 on a refusal, printing `REFUSED: …`.
- `floor.json`: `written_at`, `run_id`, `judge` (`judge-v1`), `sheet_sha256`, `labels_sha256` (of the bytes of
  `labels.jsonl`), `citable: false`, `hits`, `by_bucket`, and `correction` {`formula`, `z`, `worked`}.
- New `experiments/tests/test_noise_floor.py`. Pure tests on fixtures, then `run_floor` on a temp folder. No Ollama.
- `Makefile`: `ablation-floor`, added to `.PHONY` after `ablation-score`, with a `## Item 5.3: …` help line.
- Docs: ADR-026 and its Summary row, and the δ row, in `decisions.md`; Entry 7; M08; §I and v0.34 in its three
  places (the status line, "Current version", and the table row).

**Failure modes, silent first.**
1. **The miss rate is taken over the judge's `INCORRECT` (1 − precision).** On this data both are 7/27, so the real
   run passes and the next run is wrong. → DC 2's fixture has different margins (for example `tp` 5, `fa` 3, `mi` 2,
   `tn` 10: the miss rate is 2/7, 1 − precision is 3/8).
2. **`FA` and `MI` are swapped in the correction.** The value is plausible. → DC 5's swap test, and the worked value
   (a swap gives 0, not 0.0501).
3. **MISS keys are pooled into the floor.** That gives 18/100, also plausible. → DC 1's 14/79.
4. **The labels are not the scored ones** (the original sheet, or a re-lock). That gives 7/51. → the hash check
   against `scores.json` (DC 1, refusal tested in DC 2).
5. **The interval is too narrow** (`z` 1.96, or the floor's uncertainty left out). → DC 5's pinned interval and the
   10× test.
6. **A judged rate below the floor shows as 0 [0, 0]**, read as "no false hits". → `consistent: false` (DC 5, 0/200).
7. **The corners miss the extreme.** → DC 5's brute-force grid (21 points per rate).
8. **ADR-026 or Entry 7 copies a number wrongly.** → DC 3 and DC 4 compare them with `floor.json`.

Loud failures: `floor.json` exists; the denominator is ≤ 0; a sample key has no verdict. Each is a refusal with
exit 1.

**Edge cases.** `n` 0 at a point. `k` 0 or `k = n`. Undecided pairs (none in this data; the rule is tested). Below
1.0, `fa + tn` is 1, so its false-alarm interval is wide; it is printed and not used.

**Unknowns.**
- **Does the floor transport?** Is the judge's error the same at other configurations, τ values and strata? It is
  not measured. Only labelling hits from another cell would settle it; ADR-026 states it as an assumption.
- **The box's true coverage.** It is at least 95 %; how much more is not known. It is stated as conservative.
- **The deviation's effect** is measured, not unknown: 7/51 against 7/52 (§1).

**Verification.**
- DC 1: `make ablation-floor RUN_ID=2026-11-01T21-17-56_cfg4_judgecost` (loads no model, `citable: no`). Compare the
  printout with the golden values. Recompute the three counts from `scores.json` with a one-line `python3 -c`.
- DC 2, DC 5: `make test` (`test_noise_floor.py`).
- DC 3, 4, 6: `grep`, then compare with `floor.json` by eye in the main session.
- DC 7: `shasum -a 256` of the listed files into `evidence/sha_before.txt` before step 1, and `sha_after.txt` at the
  end; `diff` prints nothing.
- DC 8: `make verify`; `git diff --stat -- experiments/tests/` shows only the new file.
