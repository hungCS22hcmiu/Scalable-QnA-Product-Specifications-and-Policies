# Plan — Finalise δ against the judge's measured error (item 5.3)

Design: design.md (approved 2026-11-12)

Rules for every step (`.claude/rules/execution.md`):
- Nothing in this plan loads a model, so no memory-pressure check is needed. Every number is `citable: no`.
- Never edit, skip or loosen an existing test. Never write into the cost run's `raw/`, `judge/`, `manifest.yaml`
  or its six existing `ablation/` files. Never commit.
- On a failed check: one quick fix if the cause is obvious and local, run it again, and if it still fails, stop
  and report the full output.
- `R` below means `experiments/results/2026-11-01T21-17-56_cfg4_judgecost`, and `T` means
  `docs/work/2026-11-12-delta-noise-floor`.

## Phase 0 — Baseline

- [x] 0.1 Record the hashes of the locked files (DC 7, "before").
  - Run: `R=experiments/results/2026-11-01T21-17-56_cfg4_judgecost; find "$R/raw" "$R/judge" "$R/manifest.yaml"
    "$R/ablation" -type f ! -name floor.json -print0 | sort -z | xargs -0 shasum -a 256 >
    docs/work/2026-11-12-delta-noise-floor/evidence/sha_before.txt`
  - Pass: the file exists. It lists `manifest.yaml`, the files under `raw/` and `judge/`, and exactly six
    `ablation/` files (`draw.json`, `items.jsonl`, `labels.jsonl`, `refcheck.jsonl`, `sample.jsonl`, `scores.json`).
  - Result: wrote evidence/sha_before.txt, 530 lines (manifest.yaml, raw/requests.jsonl, 519 answers, 3 judge files, the six ablation files)
- [x] 0.2 Baseline `make verify`, before any change.
  - Run: `make verify`
  - Pass: exit 0. If it fails, stop: the failure is not this task's, and the human decides.
  - Result: exit 0; Go cached ok, rag 94 passed, experiments 1220 passed, ruff all checks passed, no SKIPPED

## Phase 1 — Implement

- [x] 1.1 Create `experiments/scripts/noise_floor.py` with its docstring (what item 5.3 measures, one command,
  exit codes), `import label_ablation as la` and `import select_pqa`, the constants `FLOOR_Z = 2.394`,
  `BUCKETS = ("1.0", "below 1.0")` and `WORKED = (165, 1000)`, and the pure floor functions from §3 "The noise
  floor":
  - `cells(pairs)`: counts `tp`, `fa`, `mi`, `tn` over pairs `(judge, author)` where both are in `la.DECIDED`, and
    `undecided` for the rest.
  - `floor_block(pairs)`: `cells`, and `false_alarm = la._rate(fa, fa + tn)`, `miss = la._rate(mi, mi + tp)`,
    `disagreement = la._rate(fa + mi, tp + fa + mi + tn)`.
  - `compute_floor(sample, verdicts, labels)`: only rows with `stratum == "hit"`. The author's word is mapped with
    `la.LABEL_TO_VERDICT`. It returns `hits` (all hit keys) and `by_bucket` (`1.0`: `bucket == "1.0"`; `below 1.0`:
    every other hit bucket).
  - Files: `experiments/scripts/noise_floor.py`
  - Run: `python3 -c "import sys; sys.path.insert(0, 'experiments/scripts'); import noise_floor"`
  - Pass: imports with no error.
  - Result: added experiments/scripts/noise_floor.py (cells, floor_block, compute_floor and the later functions); imports with no error; ruff clean
- [x] 1.2 Add `corrected_rate(k, n, floor, z=FLOOR_Z)` exactly as §3 "The correction" says. `floor` is a
  `floor_block` dict (it reads `false_alarm` and `miss` k and n).
  - `n == 0`: `judged` is `la._rate(0, 0)`, and `corrected`, `unclipped` and `interval` are `None`.
  - Point: `FA = fa_k / fa_n`, `MI = mi_k / mi_n`; `unclipped = (k/n − FA) / (1 − MI − FA)`, and `corrected` is it
    clipped to [0, 1]. Both are rounded to 4.
  - Box: `P`, `F`, `M` = `select_pqa.wilson(·, ·, z)` of `k/n`, `FA` and `MI`. If `1 − M_hi − F_hi ≤ 0`, raise
    `la.AblationRefused` ("the judge's error is too uncertain to correct").
  - Consistency: `consistent = not (P_hi < F_lo or P_lo > 1 − M_lo)`. If it is false, `corrected` and `interval`
    are `None` (`unclipped` is kept).
  - Interval: the min and max of the clipped formula over the 8 corners of `P × F × M`, rounded to 4.
  - Return `{"judged", "corrected", "unclipped", "interval", "consistent", "z"}`.
  - Files: `experiments/scripts/noise_floor.py`
  - Run: `python3 -c "import sys; sys.path.insert(0, 'experiments/scripts'); import noise_floor as nf;
    f = nf.floor_block([('INCORRECT','INCORRECT')]*20 + [('INCORRECT','CORRECT')]*7 + [('CORRECT','INCORRECT')]*7 +
    [('CORRECT','CORRECT')]*45); print(nf.corrected_rate(165, 1000, f))"`
  - Pass: prints `corrected` 0.0501, `interval` [0.0, 0.3038], `consistent` True.
  - Result: corrected_rate added; the check prints corrected 0.0501, interval [0.0, 0.3038], consistent True
- [x] 1.3 Add `run_floor`, `format_floor` and `main` (§3 "Files").
  - `run_floor` refuses (`la.AblationRefused`), before writing, when: `ablation/floor.json` exists; the set of
    `sheet_sha256` in `labels.jsonl` is not `{scores.json["sheet_sha256"]}`; the sample's keys are not the labels'
    keys; or a sample key has no verdict in `judge/verdicts.jsonl`.
  - It then writes `floor.json` with `la._write_new`. Fields: `written_at`, `run_id`, `judge` (`la.SOURCE_JUDGE`),
    `sheet_sha256`, `labels_sha256` (sha256 of the bytes of `labels.jsonl`), `citable: false`, `hits`, `by_bucket`,
    and `correction` {`formula` (the text of §3's formula), `z`, `worked`: `corrected_rate(*WORKED, hits)`}. It
    holds no verdict key and no text.
  - `format_floor` prints one line per rate, as `k/n = rate [low, high]`, for hits and each bucket, then the worked
    value.
  - `main`: `--run-id` (required) and `--results-dir` (default `la.RESULTS_DIR`). On `la.AblationRefused` it
    prints `REFUSED: …` to stderr and returns 1.
  - Files: `experiments/scripts/noise_floor.py`
  - Run: `python3 experiments/scripts/noise_floor.py --help`
  - Pass: the help text shows `--run-id` and `--results-dir`.
  - Result: run_floor, format_floor and main added; --help shows --run-id and --results-dir
- [x] 1.4 Add the Makefile target `ablation-floor`, right after `ablation-score`, and add it to `.PHONY`.
  - Text: `ablation-floor: ## Item 5.3: the judge's noise floor and the correction, from the locked ablation files
    (RUN_ID=<id>)`, a guard `@test -n "$(RUN_ID)" || { echo "usage: make ablation-floor RUN_ID=<id>"; exit 2; }`,
    then `$(PY) experiments/scripts/noise_floor.py --run-id "$(RUN_ID)"`.
  - Files: `Makefile`
  - Run: `make help | grep ablation-floor`
  - Pass: one line, with the help text above.
  - Result: added the ablation-floor target after ablation-score and in .PHONY; make help shows one line

## Phase 2 — Unit tests

All in the new file `experiments/tests/test_noise_floor.py`, with a docstring naming item 5.3 and the trail. No
Ollama, no network.

- [x] 2.1 The floor (DC 2). Fixture: `tp` 5, `fa` 3, `mi` 2, `tn` 10, built as `(judge, author)` pairs.
  - `cells` gives those four counts. `false_alarm` is 3/13, `miss` is 2/7, `disagreement` is 5/20. Each `wilson95`
    equals `select_pqa.wilson(k, n)`.
  - Also assert `miss["k"] / miss["n"] != 3 / 8` (1 − precision): failure mode 1.
  - R5: adding one `('UNPARSED', 'CORRECT')` pair and one `('INCORRECT', 'UNSURE')` pair leaves every rate the same
    and makes `undecided` 2.
  - `compute_floor` on a small sample with hits and MISSes: the MISS keys are absent from `hits` (failure mode 3),
    and the bucket split puts `[0.8, 1)`, `[0.6, 0.8)` and `below 0.6` into `below 1.0`.
  - Files: `experiments/tests/test_noise_floor.py`
  - Run: `pytest experiments/tests/test_noise_floor.py -q -k floor`
  - Pass: all pass.
  - Result: added 5 floor tests in experiments/tests/test_noise_floor.py (cells, margins 2/7 not 3/8, R5 undecided, empty, hits-only and buckets); 5 pass
- [x] 2.2 The correction (DC 5). The floor fixture is `tp` 20, `fa` 7, `mi` 7, `tn` 45 (the cost run's counts).
  - 165/1000 gives `corrected` 0.0501 and `interval` [0.0, 0.3038], `consistent` True.
  - 134/1000 gives `corrected` 0.0, `unclipped` −0.001, `interval` [0.0, 0.2307].
  - 0/200 gives `consistent` False, `corrected` None and `interval` None (failure mode 6).
  - Swap: a floor with `fa` and `mi` exchanged in meaning (`fa` 7 of 27, `mi` 7 of 52; fixture `tp` 45, `fa` 7,
    `mi` 7, `tn` 20) gives a different `corrected` for 165/1000 (failure mode 2).
  - Grid: for 165/1000 and for 50/300, the interval's ends equal the min and max of the clipped formula over a
    grid of 21 evenly spaced points per rate across the same `z` = 2.394 box, within 1e-4 (failure mode 7).
  - 10×: a floor with `tp` 200, `fa` 70, `mi` 70, `tn` 450 gives a strictly smaller interval width for 165/1000
    (failure mode 5). `z` is `FLOOR_Z` = 2.394 in the result.
  - Refusal: a floor whose box makes `1 − M_hi − F_hi ≤ 0` (for example `tp` 1, `fa` 1, `mi` 1, `tn` 1) raises
    `la.AblationRefused`.
  - `n` 0 gives `judged` with n 0, and `corrected`, `unclipped` and `interval` None.
  - Files: `experiments/tests/test_noise_floor.py`
  - Run: `pytest experiments/tests/test_noise_floor.py -q -k correct`
  - Pass: all pass.
  - Result: added the correction tests (0.0501 [0.0, 0.3038]; 134/1000 -> 0.0, -0.001, [0.0, 0.2307]; 0/200 inconsistent; swap; 21-point grid; 10x; refusals; n 0); `-k correct` 12 pass. Fix on the way: corrected_rate now checks the box before dividing, else tp 1 fa 1 mi 1 tn 1 raised ZeroDivisionError
- [x] 2.3 `run_floor` on a temp folder (DC 1, DC 2). Build `<tmp>/<run>/ablation/` with `sample.jsonl`,
  `labels.jsonl` and `scores.json`, and `<tmp>/<run>/judge/verdicts.jsonl`, for about 8 keys (hits and MISSes).
  - It writes `floor.json` with every field of step 1.3, and `labels_sha256` equals the file's sha256.
  - `floor.json` holds no verdict key and no `query`, `answer` or `evidence` field (search its text).
  - Refusals, each with nothing written: `floor.json` exists (and is unchanged); a label row's `sheet_sha256`
    differs from `scores.json`'s (failure mode 4); a sample key is missing from `verdicts.jsonl`.
  - `main` returns 1 and prints `REFUSED:` on a refusal.
  - Files: `experiments/tests/test_noise_floor.py`
  - Run: `pytest experiments/tests/test_noise_floor.py -q`
  - Pass: all pass.
  - Result: added 12 run_floor tests (fields, labels_sha256, no text, unsure, 3 refusals plus extras, main exit 1/0); whole file 28 pass. Fixture has 46 keys, not about 8: a floor of 8 keys is refused as too uncertain (tested)

## Phase 3 — Run on the cost run

- [x] 3.1 Compute the floor (DC 1). Loads no model; `citable: no`.
  - Run: `make ablation-floor RUN_ID=2026-11-01T21-17-56_cfg4_judgecost 2>&1 | tee
    docs/work/2026-11-12-delta-noise-floor/evidence/floor.out`
  - Pass: exit 0, and `$R/ablation/floor.json` exists. Hits: false alarm `7/52 = 0.135 [0.067, 0.253]`; miss
    `7/27 = 0.259 [0.132, 0.447]`; disagreement `14/79 = 0.177 [0.109, 0.276]`. Bucket `1.0`: false alarm 7/51.
    Worked value 165/1000: 0.0501 [0.0, 0.3038].
  - Result: exit 0; floor.json written; hits fa 7/52 = 0.135 [0.067, 0.253], miss 7/27 = 0.259 [0.132, 0.447], disagreement 14/79 = 0.177 [0.109, 0.276]; bucket 1.0 fa 7/51; worked 165/1000 = 0.0501 [0.0, 0.3038]; all golden values reproduce
- [x] 3.2 Cross-check against `scores.json` (DC 1).
  - Run: `python3 -c "import json; R='experiments/results/2026-11-01T21-17-56_cfg4_judgecost/ablation/';
    s=json.load(open(R+'scores.json'))['by_stratum']['hit']['judge_vs_author']; f=json.load(open(R+'floor.json'))['hits'];
    print(s['n']-s['k']==f['disagreement']['k'], s['recall']['n']-s['recall']['k']==f['miss']['k'],
    s['precision']['n']-s['precision']['k']==f['false_alarm']['k'])"`
  - Pass: prints `True True True`.
  - Result: prints True True True
- [x] 3.3 Record `floor.json`'s sha256 for Entry 7.
  - Run: `shasum -a 256 experiments/results/2026-11-01T21-17-56_cfg4_judgecost/ablation/floor.json | tee -a
    docs/work/2026-11-12-delta-noise-floor/evidence/floor.out`
  - Pass: one line with a 64-character hash.
  - Result: sha256 ca82488e3f51b46314ea9631af30f85fdad6ea6b1b76f0d004ff0b6404e36204 appended to evidence/floor.out

## Phase 4 — Docs

Every number below is copied from `evidence/floor.out`, never from memory. Write in the style of CLAUDE.md "How
to write".

- [x] 4.1 ADR-026 in `docs/decisions.md` (DC 3), as a new `### ADR-026 — …` right after ADR-025, in ADR-025's
  format. Title: "δ stays 5 %, read through a correction for `judge-v1`'s measured error; the judge alone cannot
  certify it". Line 2: `**Decided (method)** · 2026-11-12 · the author · *super-plan.md item 5.3; metrics.md M08;
  preregistration.md Entry 7; trail docs/work/2026-11-12-delta-noise-floor/*`. Body: the decision, then
  Rationale, Alternatives, Consequences and `Invalidates:`, with exactly the content listed in design.md §3
  "ADR-026's content" and "What M08 does at δ". It quotes the three counts with their Wilson intervals, the run,
  `citable: no`, the deviation's effect (7/51 with the original labels) and the 3.5 % row.
  - Also: a Summary row for ADR-026 (status `in force (the author, 2026-11-12)`, invalidates `none — no M08 rate has
    been reported against δ`), and the "Inherited state" δ row's value becomes `**δ = 5 %**, final (ADR-026)`, with
    its reason cell naming the correction and "holds δ, never certified".
  - Files: `docs/decisions.md`
  - Run: `grep -n "ADR-026" docs/decisions.md`
  - Pass: the heading, the Summary row and the δ row all appear; the entry has an `**Invalidates:**` line.
  - Result: ADR-026 added after ADR-025 (decisions.md line 2140), plus its Summary row (line 68) and the δ row (line 87); the entry has an Invalidates line; counts copied from floor.out
- [x] 4.2 Pre-registration Entry 7 (DC 4), appended at the end of `docs/preregistration.md` after a `---` line.
  Heading: `## Entry 7 — <date -u +"%F %H:%M">Z — δ and the judge's noise floor (item 5.3)`. Content per design.md
  §3 "Entry 7's content": δ, the three counts with their Wilson intervals, the formula, `z` 2.394, the interval
  method, the two rules, the worked value and `floor.json`'s sha256 from step 3.3. Say that it comes before any
  6.1 entry. No earlier entry is edited.
  - Files: `docs/preregistration.md`
  - Run: `grep -n "^## Entry 7" docs/preregistration.md; grep -c "| (empty) |" docs/preregistration.md; git diff
    docs/preregistration.md | grep -c "^-[^-]"`
  - Pass: one heading line; `4`; `0` (no line removed).
  - Result: Entry 7 appended to preregistration.md (2026-11-12 08:36Z, floor.json sha256 ca82488e…6204); grep gives one heading, 4, 0 removed lines
- [x] 4.3 `docs/contracts/metrics.md` M08 (DC 5, DC 6). Replace "δ ≤ 5 % is provisional until the judge's error is
  measured (item 5.3)." with a sentence that names δ = 5 % as final (ADR-026). Add a dated note, in M21's style:
  `*Added 2026-11-12 (ADR-026, item 5.3). It adds a number beside the judged rate; no rule above changes.*` Then a
  bullet "Corrected rate" under Formula: the formula, the clip, `unclipped`, the reading of `floor.json`'s `hits`.
  Under Interval: the Wilson box at `z` 2.394 and its 8 corners, `consistent: false`, the two rules ("holds δ",
  "certified at δ"), and the worked value 165/1000 → 0.0501 [0, 0.3038].
  - Files: `docs/contracts/metrics.md`
  - Run: `grep -n "ADR-026\|provisional" docs/contracts/metrics.md`
  - Pass: ADR-026 appears in M08; no line in M08 still calls δ provisional.
  - Result: M08 now says δ = 5 % is final (ADR-026), has the dated note, a Corrected rate bullet, the box interval, consistent: false, the two rules and the worked value 0.0501 [0, 0.3038]; grep finds no "provisional" left
- [x] 4.4 `docs/contracts/interfaces.md` §I (DC 6). After the labelling-ablation part, add `### The noise floor
  (item 5.3, v0.34)`: what `noise_floor.py` and `make ablation-floor RUN_ID=…` do, its refusals, and one table row
  for `results/{run_id}/ablation/floor.json` (fields of step 1.3; committed). Then v0.34 in three places: the
  `**Status:**` line (`Draft v0.34`, `Revised: 2026-11-12`), `**Current version: v0.34** (2026-11-12).`, and a new
  table row right after v0.33's.
  - Files: `docs/contracts/interfaces.md`
  - Run: `grep -n "v0.34" docs/contracts/interfaces.md`
  - Pass: at least four lines (the status line, the section heading, "Current version" and the table row).
  - Result: interfaces.md: new section "The noise floor (item 5.3, v0.34)" with the floor.json row; v0.34 in the Status line, the section heading, Current version and a table row after v0.33's

## Phase 5 — Run and verify

- [x] 5.1 `make verify`
  - Pass: exit 0, no FAIL; any SKIPPED target listed by name.
  - Result: exit 0; Go ok (cached), rag 94 passed, experiments 1248 passed (1220 before + 28 new), ruff all checks passed; no FAIL, no SKIPPED
- [x] 5.2 Done condition 1 — the floor is computed by rule.
  - Run: `cat docs/work/2026-11-12-delta-noise-floor/evidence/floor.out`, then step 3.2's command again.
  - Pass: the golden values of step 3.1; `True True True`.
  - Result: floor.out shows the golden values (7/52 [0.067, 0.253], 7/27 [0.132, 0.447], 14/79 [0.109, 0.276], bucket 1.0 fa 7/51, worked 0.0501 [0.0, 0.3038]); step 3.2's command prints True True True
- [x] 5.3 Done condition 2 — unit tests for the floor.
  - Run: `pytest experiments/tests/test_noise_floor.py -q -k "floor or run"`
  - Pass: all pass, and the tests of steps 2.1 and 2.3 are among them.
  - Result: `-k "floor or run"`: 28 passed, including all 5 floor tests of 2.1 and the 12 run_floor tests of 2.3 (the module name matches `floor`, so every test is selected)
- [x] 5.4 Done condition 3 — ADR-026 fixes δ.
  - Run: `grep -n "ADR-026" docs/decisions.md`; read the entry.
  - Pass: the entry, the Summary row and the δ row; the entry's three counts equal `floor.json`'s; it gives both
    rules, the deviation's effect, the 3.5 % row, and an `Invalidates:` line.
  - Result: grep shows the ADR-026 heading (line 2140), Summary row (68) and δ row (87); its counts 7/52, 7/27, 14/79 and sha256 equal floor.out; both rules, 7/51 deviation line, 3.5 % row and Invalidates line are in
- [x] 5.5 Done condition 4 — pre-registered before the sweep.
  - Run: `grep -n "^## Entry 7" docs/preregistration.md; grep -c "| (empty) |" docs/preregistration.md; ls
    experiments/results/`; compare Entry 7's counts and sha256 with `floor.json` and step 3.3.
  - Pass: one heading; `4`; only `2026-11-01T21-17-56_cfg4_judgecost`; the counts and the sha256 are equal.
  - Result: one `## Entry 7` heading (line 270); `| (empty) |` count 4; results/ holds only 2026-11-01T21-17-56_cfg4_judgecost; Entry 7's three counts and sha256 ca82488e… equal floor.json and step 3.3
- [x] 5.6 Done condition 5 — the corrected rate is a tested function.
  - Run: `pytest experiments/tests/test_noise_floor.py -q -k correct`; `grep -n "0.0501" docs/contracts/metrics.md`
  - Pass: all pass; the worked value appears in M08.
  - Result: `-k correct`: 12 passed; 0.0501 appears in M08 (line 265)
- [x] 5.7 Done condition 6 — docs.
  - Run: `grep -n "ADR-026" docs/contracts/metrics.md; grep -n "v0.34\|floor.json" docs/contracts/interfaces.md`
  - Pass: M08 cites ADR-026; §I names `noise_floor.py` and `floor.json`; v0.34 in its three places.
  - Result: M08 cites ADR-026 (5 lines); interfaces.md names noise_floor.py and floor.json, v0.34 at lines 3, 990, 1016, 1026
- [x] 5.8 Done condition 7 — nothing locked changes.
  - Run: step 0.1's command with `sha_after.txt` in place of `sha_before.txt`, then `diff
    docs/work/2026-11-12-delta-noise-floor/evidence/sha_before.txt
    docs/work/2026-11-12-delta-noise-floor/evidence/sha_after.txt`
  - Pass: `diff` prints nothing.
  - Result: sha_after.txt has 530 lines; diff against sha_before.txt prints nothing
- [x] 5.9 Done condition 8 — `make verify` passes, and no existing test is edited.
  - Run: `git diff --stat -- experiments/tests/ rag/tests/ gateway/; git status --porcelain -- experiments/tests/`
  - Pass: step 5.1 passed; the diff shows nothing under the test folders (`gateway/cmd/gateway/main.go`, uncommitted
    before this task, is not this task's); the status shows only `?? experiments/tests/test_noise_floor.py`.
  - Result: step 5.1 passed; `git diff --stat` shows only gateway/cmd/gateway/main.go (not this task's); `git status --porcelain -- experiments/tests/` shows only `?? experiments/tests/test_noise_floor.py`
