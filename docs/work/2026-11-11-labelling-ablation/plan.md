# Plan — Labelling ablation: the judge against the author, and with a reference against without (item 5.2)

Design: design.md (approved 2026-11-11)

**Changed 2026-11-11 after the RCA** (design.md §4, the author's choice; Entry 6): every step marked `[-]` is
superseded by Phases 7–10. **Run Phases 7–10 only**; the `[-]` steps are kept as the record.

**Rules for every step.**
- `$T` means `docs/work/2026-11-11-labelling-ablation`; `$R` means `experiments/results/2026-11-01T21-17-56_cfg4_judgecost`;
  `$A` means `$R/ablation`. A command that uses them starts with
  `T=docs/work/2026-11-11-labelling-ablation; R=experiments/results/2026-11-01T21-17-56_cfg4_judgecost; A=$R/ablation;`.
  Every command runs from the repo root.
- **Every command that runs Python tools starts with `export PATH="$HOME/Library/Python/3.13/bin:$PATH"`.**
- A step marked **(model)** loads the judge. Right before it, run `sysctl -n kern.memorystatus_vm_pressure_level` and
  write the level in the step's Result. `4`: stop and report. A `citable: yes` step runs only at `1`; at `2`, stop
  and report.
- The generator must not be loaded during a judge step (ADR-022); the script refuses if `/api/ps` lists it.
- **An author step is a stop.** The executor stops and reports; the main session asks the author and continues it.
- Never edit an existing test, `judge.py`, `judge_references.py`, anything in `$R/raw/` or `$R/judge/`,
  `experiments/judge/judge-v1.json` or `prompt-v1.txt`. Never commit or push.
- No question, answer or evidence text goes into a committed file or into this trail outside `evidence/private/`.
- On a failed check: one quick fix only if the cause is obvious and local, then stop and report (`execution.md`).
- Baseline, 2026-11-11: `make verify` passes (rag 94, experiments 1117, Go all ok).

## Phase 1 — The instrument and the pre-registration (no model)

- [x] 1.1 Write the reference-free judge record.
  - Files: `experiments/judge/prompt-rf-v1.txt`, `experiments/judge/judge-rf-v1.json` (new)
  - What: `prompt-rf-v1.txt` is the prompt in design.md §3, byte for byte, ending in one newline (as
    `prompt-v1.txt` does; compare with `tail -c 1`). `judge-rf-v1.json` is `judge-v1.json` with `version`
    `"judge-rf-v1"`, `prompt_file` `"prompt-rf-v1.txt"` and `prompt_sha256` the new file's sha256; `model`, `digest`
    and `options` copied unchanged, in the same key order and formatting as `judge-v1.json`.
  - Run: `cd experiments/judge && shasum -a 256 prompt-rf-v1.txt judge-rf-v1.json && python3 -c "import json; a=json.load(open('judge-v1.json')); b=json.load(open('judge-rf-v1.json')); print(all(a[k]==b[k] for k in ('model','digest','options')), b['prompt_sha256'])"`
  - Pass: `True`, and `prompt_sha256` equals the printed hash of `prompt-rf-v1.txt`.
  - Result: wrote both files; prompt matches design.md §3 lines 156-174 (diff empty), ends in one newline; prints `True 66c655dc...e61b` (prompt sha256 = record's `prompt_sha256`); `judge-rf-v1.json` sha256 `032513a3636766557b507b14184d53ee90604e588ead084c62f899b2d589462e`; diff against `judge-v1.json` shows only version, prompt_file, prompt_sha256.

- [x] 1.2 The author confirms the rubric. **Author check.**
  - Precondition: design.md §4 holds the author's dated confirmation of ADR-022's two rubric choices (a bare
    same-polarity "Yes." is `CORRECT`; so is a partial answer that says nothing wrong). If it does not, stop and
    report: the main session asks the author.
  - Run: `T=docs/work/2026-11-11-labelling-ablation; grep -n "rubric" $T/design.md | tail -3`
  - Pass: a §4 line with the confirmation and its date.
  - Result: design.md line 244 (§4) holds "2026-11-11: the author confirmed both of ADR-022's rubric choices for `prompt-rf-v1.txt` and the author labels".

- [x] 1.3 Write pre-registration Entry 5.
  - Files: `docs/preregistration.md` (append only; Entries 1–4 unchanged)
  - What: a heading `## Entry 5 — 2026-11-11 <HH:MM>Z — the labelling ablation (item 5.2)`, with the UTC time from
    `date -u +%H:%M`, in the style of Entry 4: one intro paragraph (written before any reference-free verdict, before
    the draw and before the labelling sheet; item 5.2; trail `docs/work/2026-11-11-labelling-ablation/`; it cites
    Entry 1 and edits no earlier entry). Then a table `Item | Value | Read from` with these rows, every value read
    from the file named: the reference-free judge record and its sha256 (`shasum -a 256 judge-rf-v1.json`); its
    prompt and the prompt's sha256; "model, digest and options equal `judge-v1`'s"; the source run `$R`'s id; the
    frame (served records, minus no `product_id` and minus Tier-2 hits on another product's entry); the strata
    (all hits, a census; 21 MISSes by `random.Random(20261111)` over MISS keys sorted by verdict key); the bucket
    edges (`1.0`, `below 1.0`; shown: `[0.8, 1)`, `[0.6, 0.8)`, `below 0.6`; MISS = `generated`); the evidence rule
    (the reference index's `chunk_ids`, joined by a blank line). Then three short lists, copied from design.md §3
    "The scores" and "Edge cases": **the metrics** (agreement, κ, recall and precision of `INCORRECT`, hits and
    MISSes apart, the circularity rule word for word, layer 5); **the counting** (`unsure` and `UNPARSED` out of
    their denominators, counted beside; `answerable: false` its own row); **the stop rules** (any wrong or
    `UNPARSED` sanity verdict: stop, no prompt edit; reference-free `UNPARSED` above 2 %: its rows are not
    reported; any `prompt_eval_count` at or above `num_ctx`: stop). Last, one line: the author's confirmation of
    the two rubric choices, with its date, quoting design.md §4.
  - Run: `grep -n "^## Entry" docs/preregistration.md; grep -c "$(shasum -a 256 experiments/judge/judge-rf-v1.json | cut -c1-64)" docs/preregistration.md; git diff -U0 docs/preregistration.md | grep -c '^-[^-]'`
  - Pass: five entries, the fifth with a UTC time; the record's sha256 found once; `0` removed lines.
  - Result: appended Entry 5 at line 161 of docs/preregistration.md, `2026-11-11 05:41Z`; record sha256 `032513a3...462e` found once; git diff shows 0 removed lines; no draw, verdict or sheet existed when written.

## Phase 2 — The script and its tests (no model)

- [x] 2.1 Write the pure half of `label_ablation.py`, with its tests.
  - Files: `experiments/scripts/label_ablation.py` (new), `experiments/tests/test_label_ablation.py` (new)
  - What (design.md §3 "Files"): a module docstring like `judge.py`'s (what it does, the six commands, that sheets
    are private and outputs hold IDs only, exit codes). `frame`, `draw`, `evidence`, `write_sheet`, `parse_sheet`,
    `write_refsheet`, `parse_refsheet`, `agreement`, `kappa`, `circularity`. Wilson: reuse `select_pqa.wilson` (the
    one `answerability_check.wilson` calls). Read `judge.py`, `judge_references.py` (`sheet`, `score`, `_mark`) and
    `experiments/tests/test_judge.py` first, and follow their style. Tests, with these names:
    - `test_frame_excludes_no_product_and_cross_product_hits` (DC 3): a fixture with one record of each kind;
      the excluded counts by reason are `{"no_product_id": 1, "cross_product_hit": 1}`.
    - `test_draw_takes_every_hit_and_n_misses_by_seed` (DC 3): on a fixture, every hit is in the sample, exactly
      `n_miss` MISSes are, and two calls give equal lists.
    - `test_sheet_hides_what_the_author_must_not_see` (DC 4): the sheet text holds no reference text, no
      `CORRECT`/`INCORRECT` verdict word outside the rubric header, and none of `cache`, `TIER2_HIT`, `MISS`,
      `overlap`, `stratum`, `similarity`.
    - `test_labels_round_trip_to_their_keys` (DC 4): write a fixture sheet, fill each `label:` line with a label
      chosen per key, parse it, and every key gets its own label.
    - `test_evidence_is_the_reference_chunk_list` (DC 5): `evidence(row, texts)` is the texts of `row["chunk_ids"]`
      in order, joined by `"\n\n"`.
    - `test_agreement_kappa_recall_precision_by_hand` (DC 7): the table "both CORRECT 40, both INCORRECT 10, judge
      INCORRECT/author CORRECT 5, judge CORRECT/author INCORRECT 5" gives agreement 50/60 with Wilson
      [0.7197, 0.9069], κ 0.5556 (5/9), recall 10/15 and precision 10/15, each Wilson [0.4171, 0.8482]
      (4 decimals); a table with only `CORRECT` on both sides gives κ `None`; `unsure` and `UNPARSED` pairs leave
      the denominators.
    - `test_circularity_rule` (DC 7): A1 0.9 with A0 8/10 is `bounded` (Wilson [0.4902, 0.9433] holds 0.9); A1 0.9
      with A0 3/10 is `quantified` (Wilson [0.1078, 0.6032]), with the gap 0.6.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; pytest experiments/tests/test_label_ablation.py -v 2>&1 | tail -15`
  - Pass: every test passes.
  - Result: wrote experiments/scripts/label_ablation.py (pure half, and the commands ahead of 2.2) and 44 tests in experiments/tests/test_label_ablation.py; all pass; Wilson/kappa/circularity match the hand values; in-memory frame on the cost run gives 600 keys, excluded 16 and 6, sample 100 (79 hits: 69/2/6/2; 21 MISS).

- [x] 2.2 Write the commands, with their tests.
  - Files: `experiments/scripts/label_ablation.py`, `experiments/tests/test_label_ablation.py`
  - What: `ask_judge_rf` (one `/api/generate` call built as `judge.ask_judge` builds it, with `{question}`,
    `{evidence}` and `{answer}`; returns the reply, the seconds and the reply's `prompt_eval_count`); `rf_sanity`,
    `rf_run`, `lock`, `score`, and the six commands of design.md §3 "The order", with argparse as in `judge.py`.
    Checks: `rf_sanity` and `rf_run` call `judge.judge_problems` with `judge-rf-v1.json` (digest, prompt hash,
    pre-registration, generator unloaded) and refuse if the record's `model`, `digest` or `options` differ from
    `judge-v1.json`'s; `rf_run` reads pressure before the first call and every 25 calls (stop at `4`), records
    every `prompt_eval_count`, and stops at the first one at or above `num_ctx`; every writer refuses when its
    output exists; `lock` refuses an unmarked item or a word other than `correct`, `incorrect`, `unsure`, and
    stores the sheet's sha256; `score` refuses when the sheet's sha256 differs from the lock, reads every
    `written_at` and Entry 5's time, and prints `entry 5 first: yes` or exits 1. Every output file carries
    `written_at`. Tests, with these names (use a fake Ollama callable, as `test_judge.py` does):
    - `test_rf_record_matches_judge_v1` (DC 5): on the real `experiments/judge/` files.
    - `test_rf_run_stops_on_a_cut_prompt` (DC 5): a fake reply with `prompt_eval_count` 4096 stops the run, and no
      output file is left behind.
    - `test_lock_refuses_a_changed_sheet` (DC 6): lock, edit the sheet, and `score` refuses.
    - `test_refsheet_holds_only_decided_disagreements` (DC 6): `unsure` items and agreements are left out.
    - `test_committed_outputs_hold_no_text` (DC 7): run draw, sheet, rf (fake), lock and score on a fixture
      `tmp_path` run, then search every file under its `ablation/` for the fixture's question, answer and evidence
      strings: none is found.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; pytest experiments/tests/test_label_ablation.py -v 2>&1 | tail -20`
  - Pass: every test passes.
  - Result: commands (draw, rf-sanity, sheet, rf, lock, score) are in label_ablation.py; 92 tests in test_label_ablation.py pass (the five named tests included); fixing a zip(strict) bug in `_sections` for an empty second sheet was the only failure, found by my own test.

- [x] 2.3 Add the Makefile targets.
  - Files: `Makefile`
  - What: six targets, each with a `## Item 5.2: …` help line, in the style of `judge` and `judge-sanity`
    (`RUN_ID` required where it is used; a model target first echoes the pressure level):
    `ablation-draw`, `ablation-rf-sanity` (`FILE` defaults to
    `docs/work/2026-10-30-judge-harness/evidence/private/sanity-v1.jsonl`), `ablation-sheet` (writes
    `docs/work/2026-11-11-labelling-ablation/evidence/private/sheet.md`), `ablation-rf`, `ablation-lock` (writes
    `…/private/refsheet.md`), `ablation-score`. Add the six to `.PHONY`.
  - Run: `make help | grep -c 'Item 5.2'`
  - Pass: `6`.
  - Result: added the six `ablation-*` targets before `load-smoke:` and to `.PHONY` (Edit tool); `make help | grep -c 'Item 5.2'` prints 6; dry runs show the right commands, default FILE, and the usage line (exit 2) without RUN_ID.

- [x] 2.4 Lint and the whole suite.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; make lint && pytest experiments/tests -q 2>&1 | tail -3`
  - Pass: no lint error; the experiments suite passes (1117 plus the new tests).
  - Result: `make lint` clean (gofmt, go vet, ruff all passed); `pytest experiments/tests -q` gives 1209 passed (1117 baseline + 92 new).

## Phase 3 — Draw, sanity, sheet, and the reference-free run

- [x] 3.1 Draw the sample, twice.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; R=experiments/results/2026-11-01T21-17-56_cfg4_judgecost; make ablation-draw RUN_ID=2026-11-01T21-17-56_cfg4_judgecost && make ablation-draw RUN_ID=2026-11-01T21-17-56_cfg4_judgecost; cat $R/ablation/draw.json`
  - Pass: `draw.json` shows the frame 600, excluded `no_product_id` 16 and `cross_product_hit` 6, the sample 100
    (79 hits: 69 at `1.0`, 2 `[0.8, 1)`, 6 `[0.6, 0.8)`, 2 `below 0.6`; 21 MISS); the second run prints `identical`.
    Other counts: stop and report.
  - Result: draw.json shows frame 600 (521 MISS, 79 hits), excluded no_product_id 16 and cross_product_hit 6, sample 100 (69 at 1.0, 2 [0.8, 1), 6 [0.6, 0.8), 2 below 0.6; 21 MISS), written_at 2026-11-11T05:58:57Z; the second run printed `identical`; sample_sha256 721c490d...2fe2.

- [-] 3.2 **(model)** The reference-free judge's sanity check. `citable: no`.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; T=docs/work/2026-11-11-labelling-ablation; for i in 1 2 3; do make ablation-rf-sanity 2>&1 | tee $T/evidence/private/rf-sanity-$i.log | tail -2; done`
  - Pass: `12 of 12 correct, 0 UNPARSED` three times, with the same verdicts. Anything else: stop and report; the
    prompt is not edited (a new version is the author's call).
  - Result: run 1 only, pressure 1: `8 of 12 correct, 0 UNPARSED`, exit 1 (`$T/evidence/private/rf-sanity-1.log`);
    stopped. RCA in design.md §4: not a code bug. Superseded by 7.1–7.2.

- [-] 3.3 Hash item 5.1's files before the run.
  - Run: `T=docs/work/2026-11-11-labelling-ablation; R=experiments/results/2026-11-01T21-17-56_cfg4_judgecost; shasum -a 256 experiments/judge/judge-v1.json experiments/judge/prompt-v1.txt experiments/references/validation/index.jsonl $R/manifest.yaml $R/raw/requests.jsonl $R/judge/verdicts.jsonl $R/judge/records.jsonl $R/judge/summary.json | tee $T/evidence/sha_before.txt`
  - Pass: eight lines.
  - Result:

- [-] 3.4 Write the blind sheet.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; T=docs/work/2026-11-11-labelling-ablation; R=experiments/results/2026-11-01T21-17-56_cfg4_judgecost; make ablation-sheet RUN_ID=2026-11-01T21-17-56_cfg4_judgecost && grep -c '^## Item ' $T/evidence/private/sheet.md && wc -l < $R/ablation/items.jsonl && git check-ignore $T/evidence/private/sheet.md`
  - Pass: `100`, `100`, and the path printed (it is ignored).
  - Result:

- [-] 3.5 **(model)** The reference-free run. **`citable: yes`: green only.**
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; T=docs/work/2026-11-11-labelling-ablation; R=experiments/results/2026-11-01T21-17-56_cfg4_judgecost; make ablation-rf RUN_ID=2026-11-01T21-17-56_cfg4_judgecost 2>&1 | tail -8; cat $R/ablation/rf.json; shasum -a 256 -c $T/evidence/sha_before.txt`
  - Pass: 100 verdicts; `UNPARSED` at most 2; the largest `prompt_eval_count` below 4096; every pressure reading
    `1`; all eight hashes `OK`. A reading of `2`: stop and report (the run must be repeated in green).
  - Result:

## Phase 4 — The author's labels (author steps)

- [-] 4.1 The author labels the sheet. **Author step: stop.**
  - What: the executor stops and reports. The author writes `label: correct`, `label: incorrect` or `label: unsure`
    under each of the 100 items of `$T/evidence/private/sheet.md`, by the rubric in its header, and says "done".
  - Result:

- [-] 4.2 Lock the labels and write the second sheet.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; T=docs/work/2026-11-11-labelling-ablation; R=experiments/results/2026-11-01T21-17-56_cfg4_judgecost; make ablation-lock RUN_ID=2026-11-01T21-17-56_cfg4_judgecost 2>&1 | tail -6; wc -l < $R/ablation/labels.jsonl; grep -c '^## Item ' $T/evidence/private/refsheet.md`
  - Pass: 100 labels (the `unsure` count printed); the sheet's sha256 printed; the second sheet's item count equals
    the printed count of decided disagreements. A refusal (an unmarked item, an unknown word): stop and report.
  - Result:

- [-] 4.3 The author marks the second sheet. **Author step: stop.**
  - What: the executor stops and reports. The author writes `reference right: yes` or `no` under each item of
    `$T/evidence/private/refsheet.md`, and says "done".
  - Result:

## Phase 5 — The scores and the docs

- [-] 5.1 Score.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; T=docs/work/2026-11-11-labelling-ablation; make ablation-score RUN_ID=2026-11-01T21-17-56_cfg4_judgecost 2>&1 | tee $T/evidence/scores.out`
  - Pass: exit 0; `entry 5 first: yes`; the lock's sha256 matches; tables (a)–(e) of DC 7 printed, hits and MISSes
    apart, each rate with its Wilson interval and n; `bounded` or `quantified` printed; `scores.json` written.
  - Result:

- [-] 5.2 Add M21 and layer 5's fields to `metrics.md`.
  - Files: `docs/contracts/metrics.md`
  - What: a new `### M21 — Judge agreement (item 5.2)` after M20, with the six parts M20 has (**Claim**,
    **Formula**, **Filter**, **Denominator**, **Interval**, **Cells**/**Data**), taken from design.md §3 "The
    scores"; a row for M21 in the Index; and, in R7's layer-5 paragraph, one sentence naming the fields:
    `ablation/refcheck.jsonl` (`verdict_key`, `reference_right`) and the `layer5` block of `ablation/scores.json`.
    Nothing else changes.
  - Run: `grep -n "M21" docs/contracts/metrics.md | cut -c1-80; grep -c "refcheck.jsonl" docs/contracts/metrics.md`
  - Pass: M21 in the Index and as a heading; the count at least `1`.
  - Result:

- [-] 5.3 Restate §I and bump the contract to v0.33.
  - Files: `docs/contracts/interfaces.md`
  - What: (1) line 3, `Draft v0.32` becomes `Draft v0.33`, and `**Revised:** 2026-11-10` becomes `**Revised:** 2026-11-11`;
    (2) `**Current version: v0.32** (2026-11-10).` becomes `**Current version: v0.33** (2026-11-11).`;
    (3) a new subsection `### The labelling ablation (item 5.2, v0.33)` right before the `---` that ends §I: one
    paragraph on `judge-rf-v1.json` (`judge-v1` with only the prompt changed; evidence = the reference index's
    `chunk_ids`), the six `make ablation-*` targets and their refusals (design.md §3), and a table `File | Holds`
    for the eight files of `ablation/` (IDs, verdicts, labels and counts only; committed) and the two private
    sheets (gitignored); (4) a versioning row right after the `v0.32` row:
    `| **v0.33** | 2026-11-11 | **The labelling ablation** (item 5.2; trail `docs/work/2026-11-11-labelling-ablation/`). §I gains the reference-free judge (`judge-rf-v1`: `judge-v1` with only its prompt changed) and the `ablation/` files. No wire, `.proto`, Redis or §H change; `judge-v1`, its prompt, the references and the served generator are unchanged. No citable run exists, so none is invalidated |`
  - Run: `grep -n "v0.33" docs/contracts/interfaces.md | cut -c1-70; grep -n '^| \*\*v0.3[23]\*\*' docs/contracts/interfaces.md | cut -c1-25`
  - Pass: `v0.33` on line 3, the current-version line, the subsection heading and the new row; the v0.33 row's line
    number is one more than the v0.32 row's.
  - Result:

## Phase 6 — Run and verify, every done condition (numbered as design.md §1)

- [-] 6.1 `make verify`
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; make verify 2>&1 | tail -40`
  - Pass: no FAIL; Go, rag and experiments suites ran. Any SKIPPED target is listed by name.
  - Result:
- [-] 6.2 DC 1 — pre-registered first.
  - Run: `T=docs/work/2026-11-11-labelling-ablation; grep -n "^## Entry 5" docs/preregistration.md; grep -n "entry 5 first" $T/evidence/scores.out`
  - Pass: Entry 5 has a UTC time; `entry 5 first: yes`.
  - Result:
- [-] 6.3 DC 2 — the sanity check.
  - Run: `T=docs/work/2026-11-11-labelling-ablation; tail -1 $T/evidence/private/rf-sanity-{1,2,3}.log`
  - Pass: `12 of 12 correct, 0 UNPARSED` three times.
  - Result:
- [-] 6.4 DC 3 — the draw.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; make ablation-draw RUN_ID=2026-11-01T21-17-56_cfg4_judgecost; pytest experiments/tests/test_label_ablation.py -k "frame or draw" -q`
  - Pass: `identical`; the tests pass.
  - Result:
- [-] 6.5 DC 4 — the blind sheet.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; T=docs/work/2026-11-11-labelling-ablation; pytest experiments/tests/test_label_ablation.py -k "hides or round_trip" -q; git check-ignore $T/evidence/private/sheet.md`
  - Pass: the tests pass; the path is printed.
  - Result:
- [-] 6.6 DC 5 — the reference-free verdicts.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; T=docs/work/2026-11-11-labelling-ablation; R=experiments/results/2026-11-01T21-17-56_cfg4_judgecost; cat $R/ablation/rf.json; shasum -a 256 -c $T/evidence/sha_before.txt; pytest experiments/tests/test_label_ablation.py -k "rf_record or cut_prompt or evidence" -q`
  - Pass: as in 3.5; all eight `OK`; the tests pass.
  - Result:
- [-] 6.7 DC 6 — the labels and the lock.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; R=experiments/results/2026-11-01T21-17-56_cfg4_judgecost; wc -l < $R/ablation/labels.jsonl; wc -l < $R/ablation/refcheck.jsonl; pytest experiments/tests/test_label_ablation.py -k "lock or refsheet" -q`
  - Pass: `100`; the decided-disagreement count of 4.2; the tests pass.
  - Result:
- [-] 6.8 DC 7 — the scores.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; T=docs/work/2026-11-11-labelling-ablation; cat $T/evidence/scores.out; pytest experiments/tests/test_label_ablation.py -k "kappa or circularity or no_text" -q`
  - Pass: as in 5.1; the tests pass.
  - Result:
- [-] 6.9 DC 8 — the docs.
  - Run: the Run commands of 5.2 and 5.3.
  - Pass: as in 5.2 and 5.3.
  - Result:
- [-] 6.10 DC 9 — `make verify`, and no existing test or frozen file edited.
  - Run: `git status --porcelain experiments rag gateway Makefile docs/preregistration.md`
  - Pass: 6.1 passed; ` M` only on `Makefile` and `docs/preregistration.md` (and `gateway/cmd/gateway/main.go`,
    the earlier drain fix, not touched here); the new script, test, two `judge/` files and the `ablation/` folder
    show `??`; no ` M` under `experiments/tests/`, `experiments/judge/` or `experiments/scripts/`.
  - Result:

## Phase 7 — After the RCA: record the failure, write Entry 6, retire the reference-free run

- [x] 7.1 **(model)** Sanity runs 2 and 3, to record whether the failure is stable. `citable: no` (yellow allowed,
  said in the Result; `4`: stop).
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; T=docs/work/2026-11-11-labelling-ablation; for i in 2 3; do make ablation-rf-sanity 2>&1 | tee $T/evidence/private/rf-sanity-$i.log | tail -2; done; grep -h WRONG $T/evidence/private/rf-sanity-{1,2,3}.log | grep -o 'q-[^ ]*' | sort | uniq -c`
  - Pass: each run ends `8 of 12 correct, 0 UNPARSED`, and the last command shows the 4 `qa_id`s of design.md §4,
    each counted `3`. Anything else is not a failure of this step: write it in the Result, then stop and report
    (Entry 6 must say it).
  - Result: runs 2 and 3 each end `8 of 12 correct, 0 UNPARSED` (pressure 1 before run 2; **2 (yellow) before run 3**, `citable: no`, so allowed); the verdict lines of all 3 logs are identical (same md5) and each of the 4 wrong `qa_id`s counts `3`; run written_at 05:59:21Z, 06:35:42Z, 06:36:38Z.

- [x] 7.2 Write pre-registration Entry 6, before the sheet exists.
  - Files: `docs/preregistration.md` (append only; Entries 1–5 unchanged)
  - What: a heading `## Entry 6 — 2026-11-11 <HH:MM>Z — the labelling ablation after the sanity failure (item 5.2)`,
    with the UTC time from `date -u +%H:%M`. One intro paragraph: written after `judge-rf-v1`'s three sanity runs
    and before the labelling sheet; trail `docs/work/2026-11-11-labelling-ablation/`; it cites Entry 5 and edits no
    earlier entry. Then four short lists (IDs only, no question, answer or evidence text):
    - **What happened:** each run's last line, from the three logs; whether the same pairs were wrong in all three;
      the wrong pairs by `kind` and `qa_id`; the cause, from design.md §4 in one or two sentences (not a code bug:
      without a reference the judge passes facts the documents never mention).
    - **The decision** (the author's, 2026-11-11): no new prompt version; no reference-free run; `judge-rf-v1` is
      used for no score; the author's labels, made without the reference (Entry 5), are the reference-free side.
    - **What changes in Entry 5:** (b) is not computed; (c) is `judge-v1` against the author per hit bucket;
      circularity: A1 = agreement of `judge-v1` and the author on hits at 1.0, A0 = the same below 1.0, and the
      bounded/quantified rule otherwise word for word as in Entry 5; the stop rules on the reference-free run's
      `UNPARSED` and `prompt_eval_count` no longer apply. Everything else in Entry 5 holds.
    - **The limit:** the overall and per-bucket agreements compare the same two labellers, so item 5.2's "both
      schemes" are one comparison shown two ways; one labeller, no inter-rater check.
  - Run: `T=docs/work/2026-11-11-labelling-ablation; grep -n "^## Entry" docs/preregistration.md; git diff -U0 docs/preregistration.md | grep -c '^-[^-]'; ls $T/evidence/private/sheet.md 2>&1 | tail -1`
  - Pass: six entries, the sixth with a UTC time; `0` removed lines; `No such file` for the sheet.
  - Result: appended Entry 6 at line 213 of docs/preregistration.md, `2026-11-11 06:37Z` (written 06:37-06:38Z); six entries; 0 removed lines; no sheet existed (`No such file`); it quotes the 3 runs (8 of 12 each, pressure 1/1/2), the 4 same wrong pairs by kind and qa_id, the author's decision, the changes to Entry 5 and the limit.

- [x] 7.3 Change `score`, retire the `rf` command, and remove `ablation-rf`.
  - Files: `experiments/scripts/label_ablation.py`, `experiments/tests/test_label_ablation.py`, `Makefile`
  - What (design.md §3 "After the sanity failure"):
    1. `score` reads no `verdicts-rf.jsonl` or `rf.json`: its key check is labels = items = sample, and `_times`
       drops the two reference-free entries. The Entry 5 check is otherwise unchanged (draw, sheet, sanity logs).
    2. `ENTRY_6` (as `ENTRY_5`) and `check_entry6_first(prereg_text, sheet_written_at)`: the first instant after
       Entry 6's minute must be earlier than the sheet's `written_at`. `score` prints `entry 6 first: yes`, or
       prints `entry 6 first: NO` and refuses.
    3. `_by_stratum` drops `rf_vs_author` and `judge_vs_rf`, and adds `judge_vs_author_by_bucket`: for hits over
       `1.0`, `[0.8, 1)`, `[0.6, 0.8)`, `below 0.6` and `below 1.0`; for MISS over `generated`. Circularity is
       `circularity(by_bucket["1.0"], by_bucket["below 1.0"])` of that block; fix its docstring to say "the author".
    4. `scores.json`: drop `rf_rows_reportable`; `judge_rf` becomes `"judge-rf-v1: failed its sanity check, used
       for no score (Entry 6)"`; add `"entry6_first": true` and `"reference_free_side": "author"`.
    5. `format_scores`: `(b) not computed: judge-rf-v1 failed its sanity check (Entry 6)`; `(c) judge-v1 vs
       author, by bucket` with one line per bucket; (d) and (e) as now.
    6. The `rf` command prints `REFUSED: retired by Entry 6: judge-rf-v1 failed its sanity check` and returns 1,
       before any Ollama call. `rf_run`, `rf_sanity` and `ask_judge_rf` stay, with their tests.
    7. `Makefile`: remove the `ablation-rf` target and its `.PHONY` entry (Edit tool, not a shell script).
    Tests: a test written in this task that feeds reference-free verdicts to `score` may change to the new design;
    name each changed test in the Result. No test that existed before this task is touched. New tests:
    - `test_score_needs_no_rf_files` (DC 5): a fixture run with no `verdicts-rf.jsonl` or `rf.json` scores.
    - `test_circularity_is_judge_v1_against_author` (DC 7): hits at 1.0 where `judge-v1` and the author agree on 9
      of 10, below 1.0 on 3 of 10: `quantified`, A1 0.9, A0 0.3, inflation 0.6; and a reference-free verdict file
      placed in the fixture with opposite verdicts does not change the result.
    - `test_score_refuses_entry6_after_the_sheet` (DC 1): Entry 6's minute after the sheet's `written_at` refuses;
      before it prints `entry 6 first: yes`.
    - `test_rf_command_is_retired` (DC 5): `main(["rf", "--run-id", "x"])` returns 1, calls no Ollama and writes
      nothing.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; pytest experiments/tests/test_label_ablation.py -q 2>&1 | tail -3; make help | grep -c 'Item 5.2'; grep -c '^ablation-rf:' Makefile`
  - Pass: every test passes; `5`; `0`.
  - Result: all 7 changes done (script: `score` reads no rf file, `check_entry6_first`, `_by_stratum`/`format_scores`/`scores.json`, `rf` command refuses; Makefile via Edit tool: `ablation-rf` and its `.PHONY` entry removed); 103 tests pass, `make help | grep -c 'Item 5.2'` prints 5, `grep -c '^ablation-rf:' Makefile` prints 0. This task's own tests changed: fixture `World._build` (prereg now holds Entry 6) and `prepared()` (no rf run); `test_rf_run_refuses_when_its_output_exists` and `test_the_reference_free_replies_hold_only_a_verdict_word` (now run `rf` themselves); `test_score_buckets_split_the_hits` (new key `judge_vs_author_by_bucket`, MISS bucket checked); `test_score_prints_the_tables` (new (b)/(c) lines, entry 5 and 6 lines); `test_committed_outputs_hold_no_text` (6 files, no rf files); `test_score_does_not_report_the_reference_free_rows_when_it_was_over_two_percent` deleted (no such path now). New: `test_score_needs_no_rf_files`, `test_circularity_is_judge_v1_against_author` (2 params, with and without rf files placed), `test_circularity_is_bounded_when_the_below_1_agreement_holds_up`, `test_score_refuses_entry6_after_the_sheet`, `test_score_prints_entry6_first_yes_when_it_came_before_the_sheet`, `test_score_refuses_a_preregistration_without_entry6`, 3 entry6 unit tests, `test_the_real_preregistration_has_entry6_with_a_time`, `test_rf_command_is_retired`. No pre-task test touched (`git status` under experiments/tests shows only the new file).

- [x] 7.4 Lint and the whole suite.
  - Run: as 2.4.
  - Pass: no lint error; the experiments suite passes (1117 plus this task's tests).
  - Result: `make lint` clean (gofmt, go vet, ruff); `pytest experiments/tests -q` gives 1220 passed (1117 baseline + 103 of this task).

## Phase 8 — The sheet and the author's labels

- [x] 8.1 Hash item 5.1's files before the sheet.
  - Run: the Run line of 3.3. Pass: eight lines.
  - Result: 8 lines in `$T/evidence/sha_before.txt`; `judge-v1.json` is `1beb1fbd...` (Entry 1) and the reference `index.jsonl` is `0e843899...` (Entry 4), as pre-registered.

- [x] 8.2 Write the blind sheet.
  - Run: the Run line of 3.4. Pass: `100`, `100`, and the path printed (it is ignored).
  - Result: sheet written 2026-11-11T06:43:24Z (after Entry 6, 06:37Z): `grep -c '^## Item '` prints 100, `items.jsonl` has 100 lines, `git check-ignore` prints the sheet path (ignored); header holds only the rubric, no verdict, reference, cache or overlap field.

- [x] 8.3 The author labels the sheet. **Author step: stop.** As 4.1.
  - Result: The author labelled a copy outside the repo; the main session copied the labels verbatim into `evidence/private/sheet.md` (diff: the 100 `label:` lines only): 70 correct / 30 incorrect / 0 unsure, sha256 `3776cdda…5cf7`, kept read-only as `evidence/private/sheet.before-ai-review.md`. Then a deviation from Entries 5 and 6 (design.md §4, the author's decision): after reading two AI reviews the author changed items 27, 51 and 54 to `correct` and 93 to `incorrect`; the main session edited those four lines on the author's instruction. Final: 72 correct / 28 incorrect, sha256 `b3f689e9b1d883d1727ca65514dc11d382484221f5c1ad5f45992e01f9abc2e5`.

- [x] 8.4 Lock the labels and write the second sheet.
  - Run: the Run line of 4.2. Pass: as 4.2.
  - Result: no model loaded; `make ablation-lock` wrote `labels.jsonl` (100 rows, written_at 2026-11-11T16:12:13Z, every row carries sheet sha256 `b3f689e9…c2e5`, equal to `shasum -a 256` of the sheet now) and the second sheet `evidence/private/refsheet.md` (gitignored): 72 correct / 28 incorrect / 0 unsure; 18 decided disagreements with judge-v1 (14 hits, 4 MISS); `grep -c '^## Item '` on the second sheet prints 18.

- [x] 8.5 The author marks the second sheet. **Author step: stop.** As 4.3.
  - Result: The author marked all 18 (2026-11-12): item 44 `reference right: no`, the other 17 `yes`. The author gave the marks in chat and the main session wrote them into `evidence/private/refsheet.md` (diff: the 18 `reference right:` lines only; `parse_refsheet` reads 18 marks). Before that, on the author's request, the main session moved each locked label next to its answer (layout only: `parse_refsheet` gave the same result before and after, and every label shown equals the first sheet).

## Phase 9 — The scores and the docs

- [x] 9.1 Score.
  - Run: the Run line of 5.1, then `T=docs/work/2026-11-11-labelling-ablation; R=experiments/results/2026-11-01T21-17-56_cfg4_judgecost; ls $R/ablation; shasum -a 256 -c $T/evidence/sha_before.txt`
  - Pass: exit 0; `entry 5 first: yes`; `entry 6 first: yes`; the lock's sha256 matches; for hits and MISSes apart:
    (a) with Wilson, κ, recall and precision; (b) `not computed` with Entry 6's reason; (c) by bucket; (d); then
    (e) `bounded` or `quantified` with A1, A0 and n. `scores.json` written. `ls` shows no `verdicts-rf.jsonl` or
    `rf.json`; all eight hashes `OK`.
  - Result: no model loaded; `make ablation-score` exit 0, output in `$T/evidence/scores.out`: `entry 5 first: yes` (5 written_at fields), `entry 6 first: yes`, sheet sha256 `b3f689e9…c2e5` equals the lock's (score refuses otherwise), tables (a)–(e) for hits and MISS apart (hits: agreement 65/79 [0.724, 0.891], κ 0.606; MISS: 17/21 [0.600, 0.923], κ -0.077), layer 5 hits 1/79 and MISS 0/21, circularity `bounded` (A1 0.797 n 69, A0 1.000 n 10); `scores.json` and `refcheck.jsonl` (18 rows: 17 yes, 1 no) written; `ls ablation/` has no `verdicts-rf.jsonl` or `rf.json`; all eight 5.1 hashes `OK`.

- [x] 9.2 Add M21 and layer 5's fields to `metrics.md`.
  - What: as 5.2, with two differences: the circularity formula is Entry 6's (`judge-v1` against the author), and
    one sentence says `judge-rf-v1` failed its sanity check and is used for no score (Entry 6).
  - Run and Pass: as 5.2.
  - Result: added `### M21 — Judge agreement (item 5.2)` after M20 (six parts, circularity as Entry 6, `judge-rf-v1` failed and unused), an Index row (line 119), and the two layer-5 field names in R7 (line 81); `grep -n M21` shows Index and heading (lines 119, 447), `grep -c refcheck.jsonl` prints 2; 37 lines added, 1 changed (run before 9.1 by the main session's order; needs no score).

- [x] 9.3 Restate §I and bump the contract to v0.33.
  - What: as 5.3, with these differences. (3) The subsection paragraph: `judge-rf-v1.json` (`judge-v1` with only
    the prompt changed) is recorded, failed its sanity check and is used for no score (Entry 6); the five
    `make ablation-*` targets and their refusals; the `rf` command refuses. The table covers the six files of
    `ablation/` (`draw.json`, `sample.jsonl`, `items.jsonl`, `labels.jsonl`, `refcheck.jsonl`, `scores.json`;
    committed) and the private sheets and sanity logs (gitignored). (4) The row:
    `| **v0.33** | 2026-11-11 | **The labelling ablation** (item 5.2; trail `docs/work/2026-11-11-labelling-ablation/`). §I gains the `ablation/` files and records `judge-rf-v1` (`judge-v1` with only its prompt changed), which failed its sanity check and is used for no score (Entry 6). No wire, `.proto`, Redis or §H change; `judge-v1`, its prompt, the references and the served generator are unchanged. No citable run exists, so none is invalidated |`
  - Run and Pass: as 5.3.
  - Result: interfaces.md: line 3 `Draft v0.33` / `Revised: 2026-11-11`, the current-version line (996) now v0.33, new subsection `### The labelling ablation (item 5.2, v0.33)` before the `---` that ends §I (heading line 950; five targets and their refusals, the `rf` command's refusal, an 8-row `File | Holds` table), and the v0.33 row (1005) right after the v0.32 row (1004); `grep -n v0.33` shows lines 3, 950, 996, 1005; 43 lines added, 2 changed (run before 9.1 by the main session's order; needs no score).

## Phase 10 — Run and verify, every done condition (numbered as design.md §1)

- [x] 10.1 `make verify`
  - Run: as 6.1. Pass: no FAIL; Go, rag and experiments suites ran. Any SKIPPED target is listed by name.
  - Result: exit 0; lint clean, `go build` ok, Go packages all `ok` (some `(cached)`; none has FAIL), rag 94 passed, experiments 1220 passed; no SKIPPED target (0 matches for SKIPPED or FAIL in the output).
- [x] 10.2 DC 1 — pre-registered first.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; T=docs/work/2026-11-11-labelling-ablation; grep -n "^## Entry [56]" docs/preregistration.md; grep -n "entry [56] first" $T/evidence/scores.out; pytest experiments/tests/test_label_ablation.py -k entry6 -q`
  - Pass: both entries have a UTC time; `entry 5 first: yes` and `entry 6 first: yes`; the test passes.
  - Result: Entry 5 (line 161, 05:41Z) and Entry 6 (line 213, 06:37Z) both have a UTC time; `scores.out` shows `entry 5 first: yes (checked 5 written_at fields)` and `entry 6 first: yes (before the sheet)`; `pytest -k entry6` gives 7 passed.
- [x] 10.3 DC 2 — the sanity check is recorded.
  - Run: `T=docs/work/2026-11-11-labelling-ablation; tail -1 $T/evidence/private/rf-sanity-{1,2,3}.log; sed -n '/^## Entry 6/,$p' docs/preregistration.md | grep -c '8 of 12'`
  - Pass: three last lines, as 7.1 recorded; the count at least `1`.
  - Result: `tail -1` of each log is make's `Error 1` line (the logs hold make's failed exit, as in 7.1's `tail -2`); the line before it in all three logs is `8 of 12 correct, 0 UNPARSED`; Entry 6 holds `8 of 12` 3 times (count 3 on its lines).
- [x] 10.4 DC 3 — the draw. Run and Pass: as 6.4.
  - Result: `make ablation-draw` prints `identical` (a third draw; `sample.jsonl` untouched); `pytest -k "frame or draw"` gives 13 passed.
- [x] 10.5 DC 4 — the blind sheet. Run and Pass: as 6.5.
  - Result: `pytest -k "hides or round_trip"` gives 2 passed (`test_sheet_hides_what_the_author_must_not_see`, `test_labels_round_trip_to_their_keys`); `git check-ignore` prints the sheet path (ignored).
- [x] 10.6 DC 5 — no reference-free run; 5.1's files unchanged.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; T=docs/work/2026-11-11-labelling-ablation; R=experiments/results/2026-11-01T21-17-56_cfg4_judgecost; ls $R/ablation; shasum -a 256 -c $T/evidence/sha_before.txt; pytest experiments/tests/test_label_ablation.py -k "no_rf_files or rf_command_is_retired or evidence" -q`
  - Pass: no `verdicts-rf.jsonl` or `rf.json`; all eight `OK`; the tests pass.
  - Result: `ls ablation/` shows draw.json, items.jsonl, labels.jsonl, refcheck.jsonl, sample.jsonl, scores.json (no `verdicts-rf.jsonl`, no `rf.json`); all eight 5.1 hashes `OK` after the score; `pytest -k "no_rf_files or rf_command_is_retired or evidence"` gives 6 passed.
- [x] 10.7 DC 6 — the labels and the lock. Run and Pass: as 6.7.
  - Result: `labels.jsonl` 100 lines; `refcheck.jsonl` 18 lines (the 18 decided disagreements of 8.4); `pytest -k "lock or refsheet"` gives 8 passed.
- [x] 10.8 DC 7 — the scores.
  - Run: as 6.8, with `-k "kappa or circularity or no_text"`.
  - Pass: as 9.1; the tests pass, `test_circularity_is_judge_v1_against_author` among them.
  - Result: `scores.out` (29 lines) is the 9.1 output, unchanged (tables (a)–(e), hits and MISS apart, `bounded`); `pytest -k "kappa or circularity or no_text"` gives 10 passed, including both parameters of `test_circularity_is_judge_v1_against_author` and `test_committed_outputs_hold_no_text`.
- [x] 10.9 DC 8 — the docs. Run and Pass: as 9.2 and 9.3.
  - Result: metrics.md: M21 in R7 (line 82), the Index (line 120) and as the heading (line 448), `grep -c refcheck.jsonl` prints 2; interfaces.md: `v0.33` on lines 3, 950 (subsection heading), 996 (current version) and 1005 (the row, one line after the v0.32 row at 1004); Phase 11 greps also hold (`four more` 1, `three more` 0, `M20 and M21 do` on line 55 in R5, `verdicts.jsonl` count 2).
- [x] 10.10 DC 9 — `make verify`, and no existing test or frozen file edited. Run and Pass: as 6.10.
  - Result: 10.1 passed; `git status --porcelain experiments rag gateway Makefile docs/preregistration.md` shows ` M` only on `Makefile`, `docs/preregistration.md` and `gateway/cmd/gateway/main.go` (the earlier drain fix, not touched here); `??` on `label_ablation.py`, `test_label_ablation.py`, `judge-rf-v1.json`, `prompt-rf-v1.txt` and `ablation/`; no ` M` under `experiments/tests/`, `experiments/judge/` or `experiments/scripts/`. `preregistration.md`: 0 removed lines; `Makefile`: 1 removed line (the `.PHONY` line, extended). `docs/contracts/{interfaces,metrics}.md` are also ` M` (the 9.2, 9.3 and Phase 11 edits).

## Phase 11 — Two `metrics.md` passages that M21 made stale (found in 9.2, 2026-11-11)

The executor's 9.2 report. Doc edits only, with the Edit tool; no score needed. Run before Phase 10, so that 10.9
(DC 8) covers them. The main session checked the second fact: on the cost run, `records.jsonl` and `verdicts.jsonl`
give the same verdict for every key (622 keyed records, 0 differ).

- [x] 11.1 "What this is" counts M21.
  - What: in `docs/contracts/metrics.md`, "and three more: μ_gen (M18), μ_hit (M19) and the miss-path error rate
    (M20)" becomes "and four more: μ_gen (M18), μ_hit (M19), the miss-path error rate (M20) and judge agreement
    (M21)". Nothing else in the paragraph changes.
  - Run: `grep -c "four more" docs/contracts/metrics.md; grep -c "three more" docs/contracts/metrics.md`
  - Pass: `1`; `0`.
  - Result: edited line 10 of `docs/contracts/metrics.md` (Edit tool); `grep -c "four more"` prints 1 and `grep -c "three more"` prints 0; the rest of the paragraph is unchanged.
- [x] 11.2 R5 names M21 and the file it reads.
  - What: in R5, "Only M08, M12, M13, M16 and M20 do." becomes "Only M08, M12, M13, M16, M20 and M21 do. M21 reads
    by verdict key from `judge/verdicts.jsonl`, the verdict that `records.jsonl` carries for the same key."
  - Run: `grep -n "M20 and M21 do" docs/contracts/metrics.md; grep -c "verdicts.jsonl" docs/contracts/metrics.md`
  - Pass: one line, inside R5; the count is one more than before the edit.
  - Result: edited R5's last bullet (Edit tool; the sentence wraps to a second line, so the new text stays inside R5); `grep -n "M20 and M21 do"` shows line 55 only; `grep -c "verdicts.jsonl"` was 1 before the edit and is 2 after.
