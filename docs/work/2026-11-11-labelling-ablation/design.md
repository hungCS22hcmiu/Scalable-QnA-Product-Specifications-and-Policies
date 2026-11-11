# Labelling ablation: the judge against the author, and with a reference against without (item 5.2)

Status: opened 2026-11-11 · spec approved 2026-11-11 · design approved 2026-11-11 · plan approved 2026-11-11
Changed by §3 (2026-11-11): DC 3 takes every frame hit and 21 MISSes; DC 1 also covers the draw; DC 4–7 gain
guards for §3's silent failure modes; DC 7 reports hits and MISSes apart.
Changed by §4 (2026-11-11, after the RCA; the author's choice): `judge-rf-v1` failed its sanity check, so the
author's labels are the reference-free side and no reference-free run is made (Entry 6). DC 1, 2, 5, 7, 8 changed.
Changed by §4 (2026-11-11, the author's decision): 4 labels changed after two AI reviews, a deviation; no DC changed.
Super-plan item: 5.2 — Labelling ablation on ~100 pairs under both schemes; agreement by containment bucket

## 1. Spec

**The change.** Measure how far the frozen judge (`judge-v1`, ADR-022) can be trusted. About 100 served answers
from the judge cost run are labelled **once by the author**, from the question and the gold source documents. The
judge's labels (`judge-v1`, made with the reference) are compared with the author's (made without it). A
reference-free judge (same model) was planned as a second reference-free side; it failed its sanity check, so the
author's labels are the reference-free side (Entry 6). The agreement is recorded overall, and by containment
bucket for circularity. The author's check also gives the first count of error layer 5,
a wrong reference (`metrics.md` R7).

**Why.** δ (item 5.3) must sit clearly above the judge's own error, and nothing has measured that error yet. The
reference-free scheme checks whether the reference makes a label depend on overlap (the "circular labelling" of
`Final_Proposal.md` §5). ADR-022's gold-anchored references should already have removed that loop; this checks it.

**Facts this spec rests on.**
- Source: `2026-11-01T21-17-56_cfg4_judgecost` (configuration 4, gate on, MIXED off, `v1` validation, admissible,
  `citable: no` for its rates). All 622 records were judged by `judge-v1` (163 `INCORRECT`, 0 `UNPARSED`), against
  ADR-023's references. Here the run supplies only the items to label.
- The frame is its served records minus 16 with no `product_id` (ADR-025 now refuses them) and the 6 Tier-2 hits on
  another product's entry (ADR-024 removed them): **600 distinct verdict keys**. That is 521 MISS, 69 hits at
  `source_overlap` 1.0, and 10 hits below 1.0 (2 in [0.8, 1), 6 in [0.6, 0.8), 2 below 0.6). `judge-v1` calls 9 of
  those 10 `INCORRECT`.
- So the low-overlap buckets hold about 10 answers. The circularity result can be stated, but with wide intervals.
- A verdict at `temperature` 0 with a fixed seed does not depend on load: 5.1 re-judged 30 keys with 0 flips.
- The longest gold evidence is 7,766 characters, about 2,000 tokens (`judge_references.py:52`), so a reference-free
  prompt should fit `judge-v1`'s `num_ctx` 4096. Ollama drops text past `num_ctx` with no error.
- ADR-022 left two rubric choices to the author (a bare same-polarity "Yes." is `CORRECT`; so is a partial answer
  that says nothing wrong), and no record of the author's confirmation was found. The author's labels must follow
  the same rubric as the judge.
- The labelling sheet carries PQA-derived text, which may not be published (CLAUDE.md), so it stays gitignored.

**Done conditions.**

1. **Pre-registered first.** `docs/preregistration.md` Entry 5 holds: the reference-free judge record and its sha256;
   the frame, the strata, the bucket edges, the sample size and the seed; the metrics, and the rule that decides
   whether circularity is "bounded" or "quantified"; the stop rules; how an undecided label is counted; and the
   author's confirmation of ADR-022's two rubric choices. Pass: Entry 5's date-time is earlier than the
   `written_at` of the draw, of the sanity runs and of the labelling sheet; and Entry 6 (written after the sanity
   failure) is earlier than the sheet's.
2. **The reference-free judge's sanity check is recorded.** Item 5.1's 12 sanity pairs, each with its gold evidence
   in place of the reference, in 3 runs. Changed 2026-11-11: run 1 failed (8 of 12), so the prompt is not edited and
   `judge-rf-v1` is not used for any score (Entry 6). Pass: three logs; Entry 6 quotes each run's count, and whether
   the same pairs were wrong in all three.
3. **The sample is drawn by rule.** A Makefile target draws 100 keys from the frame, as pre-registered: every hit
   in the frame (79, a census) and 21 MISSes by seed. Run a second time, it re-draws and confirms the file is
   byte-identical. Unit tests pin the frame's two exclusions and the draw on a fixture.
4. **The author's sheet is blind.** Per item it shows the question, the product, the gold evidence text and the
   answer, in a seeded random order. It shows **no** reference, verdict, cache outcome, overlap or stratum; a unit
   test checks that those are absent. A second unit test fills a fixture sheet and checks that every label lands on
   its own key. The sheet is written under a gitignored path.
5. **No reference-free run, and item 5.1's files unchanged.** Changed 2026-11-11 (Entry 6). `ablation/` holds no
   `verdicts-rf.jsonl` or `rf.json`; the `rf` command refuses, and `score` needs no reference-free file (unit tests).
   The sheet's evidence is the reference index's `chunk_ids` (a unit test). `judge-v1`'s files, the references and
   the cost run's `raw/` and `judge/` have the same sha256 before the sheet and after the score.
6. **The author's labels.** Every sampled key carries `CORRECT` or `INCORRECT` from the author; an undecided key is
   counted and reported as Entry 5 says, never guessed. The labels are then locked: the first sheet's sha256 is
   recorded, and the score step refuses if it changed. Only after that, for the keys where `judge-v1` disagrees
   with the author, a second short sheet shows the reference and records whether it is wrong (layer 5).
7. **The scores.** A Makefile target writes and prints, for hits and MISSes apart (never pooled: they are sampled
   at different rates): (a) `judge-v1` against the author: n, agreement with its Wilson interval, Cohen's κ, and
   the recall and precision of `INCORRECT` with Wilson intervals; (b) printed as "not computed", with Entry 6's
   reason; (c) `judge-v1` against the author per hit bucket (n, agreement with Wilson, κ); (d) layer 5, the count
   of wrong references with Wilson over the sample; (e) "bounded" or "quantified", by Entry 6's rule (A1 and A0
   from (c)). Unit tests pin κ, Wilson, the bucket split and the rule against hand-computed values, and check that
   no committed output holds question, answer or evidence text.
8. **Docs.** `metrics.md`: the agreement metric and layer 5's fields. `interfaces.md` §I: the `ablation/` files
   and the label file, with `judge-rf-v1` recorded as failed and unused, as **v0.33**. (`/done` marks the item.)
9. `make verify` passes, and no existing test is edited.

**Out of scope.**
- δ (item 5.3), and any rate of the cost run.
- A new generation run. A second labeller (inter-rater agreement): reported as a limit.
- Any change to `judge-v1`, its prompt, the references or the served generator.
- The test split.

## 2. Impact

**Files and boundaries.**
- `experiments/scripts/`: the reference-free mode and the ablation steps (sample, sheet, score), in a new script,
  `label_ablation.py` (§3); `judge.py` does not change. `experiments/judge/`: `prompt-rf-v1.txt` and `judge-rf-v1.json`. `experiments/tests/`: new tests.
  `Makefile`: new targets. All inside `experiments/`, which reads `raw/` and writes its own outputs; no gateway or
  `rag` change (`architecture.md`).
- Outputs go to a new folder for this task, never into the cost run's `raw/` (write-once). Files that carry text
  are gitignored; keys, labels and scores are not.
- Docs: `preregistration.md` Entries 5 and 6, `metrics.md`, `interfaces.md` §I.

**Frozen values touched.** None changed. **New frozen values:** the reference-free judge (`judge-v1`'s model,
digest and options, with `prompt-rf-v1` and its hash), the sampling rule and seed, and the bucket edges, all
pre-registered in Entry 5 before use. Entry 6 (2026-11-11) makes the author's labels the reference-free side of
Entry 5's metrics; Entry 5 is not edited. `judge-v1`, its prompt, the references and the served generator stay
as they are; DC 5 checks their hashes.
**Prior runs invalidated: none.** The cost run is read, never changed.

**Contract change.** Yes, outside the gateway seam. `interfaces.md` §I gains the `ablation/` files and the
label file (v0.33). `metrics.md` gains the agreement metric and layer 5's fields, as a dated entry. No `.proto`,
gateway or `rag` change; `source_chunk_ids`, `t1_key` and `dataset_epoch` are untouched.

**Measurement change.** New measurements only; no existing metric changes meaning. Layer 5 gets its first count.
The agreement numbers are what item 5.3 sets δ against.

**The author's time.** About 100 labels, then a short second pass on the disagreements. The plan stops for both,
and for the confirmation of the two rubric choices.

**New dependency.** None: κ and Wilson are a few lines of Python. Memory: the judge, `gemma3:4b`, used about
4.3 GB RSS in 5.1's cost run, with the generator unloaded first (ADR-022). No reference-free run is made
(Entry 6); the judge loads only for the sanity runs, `citable: no`.

**Cut scope reinstated.** No.

## 3. Design

**The approach.** A new script, `experiments/scripts/label_ablation.py`, does the work in six commands, each behind
its own Makefile target. It reuses `judge.py` (the frozen judge's checks, `parse_verdict`, `verdict_key`, the
Ollama call) and `judge_references.py` (the corpus text). The reference-free judge is `judge-v1` with exactly one
change, its prompt. The author labels in a Markdown sheet, as in item 5.1's sufficiency check.

Alternatives that lost:
- The steps inside `judge.py`. It is the frozen judge's harness, with 120 tests; a separate script leaves it as it is.
- A new run on today's code. It costs about an hour of generation, and the frame already matches what ADR-024 and
  ADR-025 left.

**After the sanity failure (2026-11-11, the author's choice; Entry 6).** `judge-rf-v1` gave 8 of 12 on the sanity
pairs. It passes invented facts the documents never mention, the error `judge-v1` exists to catch (§4). So no
reference-free run is made, and the author's labels, made without the reference, are the reference-free side.
`judge-rf-v1`, `rf-sanity` and `rf_run` stay, so the failure can be reproduced; the `rf` command refuses, and the
`ablation-rf` target is removed. Entry 6 records this after sanity runs 2 and 3 and before the sheet is written;
Entry 5 is not edited. A limit, stated: the overall and per-bucket agreements now compare the same two labellers,
so item 5.2's "both schemes" are one comparison shown two ways. Alternatives that lost: `prompt-rf-v2` (written
after seeing the 4 failures, it would tune on the check, and spotting a missing fact may be beyond a 4B model); a
larger judge (model and scheme would change together).

**The order.** Each step's output carries `written_at` (UTC); every writer refuses when its output exists.
1. Author stop 1: the author reads `prompt-rf-v1.txt` (below) and confirms ADR-022's two rubric choices. Then
   `docs/preregistration.md` Entry 5 is written, with the sha256 of `judge-rf-v1.json`.
2. `make ablation-draw RUN_ID=…` writes `ablation/draw.json` and `ablation/sample.jsonl`. A second run re-draws in
   memory and prints `identical` or exits 1.
3. `make ablation-rf-sanity` judges item 5.1's 12 sanity pairs (`…/2026-10-30-judge-harness/evidence/private/
   sanity-v1.jsonl`), each with its gold evidence, three times. Any wrong or `UNPARSED` verdict stops the work.
   Run 1 failed; runs 2 and 3 are taken only to record whether the failure is stable, then Entry 6 is written.
4. `make ablation-sheet RUN_ID=…` writes the blind sheet to this trail's `evidence/private/sheet.md` and
   `ablation/items.jsonl` (item number → verdict key).
5. Dropped by Entry 6: no reference-free run, no `verdicts-rf.jsonl` or `rf.json`.
6. Author stop 2: the author writes `label: correct`, `incorrect` or `unsure` under each item.
7. `make ablation-lock RUN_ID=…` writes `ablation/labels.jsonl` with the sheet's sha256, then the second sheet,
   `evidence/private/refsheet.md`, for the keys where `judge-v1` and the author both decided and disagree.
8. Author stop 3: `reference right: yes` or `no` under each item of the second sheet.
9. `make ablation-score RUN_ID=…` re-hashes the first sheet (it must match the lock), writes `ablation/refcheck.jsonl`
   and `ablation/scores.json`, and prints the tables.

**The sample.** The frame is §1's (600 keys). Two strata: **hits**, all 79 in the frame (a census), and **MISS**,
21 drawn by `random.Random(20261111)` from the MISS keys sorted by verdict key. Hit buckets by `source_overlap`:
`1.0` and `below 1.0` decide the circularity rule; `[0.8, 1)`, `[0.6, 0.8)` and `below 0.6` are shown. MISSes are
their own bucket, `generated`. Hits get the census because δ budgets a rate over hits, so the judge's error on hits
is what 5.3 needs; the MISSes check the judge on generated answers, which carry most of the layer counts.

**The reference-free judge.** `judge-rf-v1.json`: version `judge-rf-v1`; `judge-v1`'s model, digest and options
unchanged (`temperature` 0, `seed` 20261031, `num_ctx` 4096, `num_predict` 8); prompt `prompt-rf-v1.txt`. A key's
evidence is the reference index's `chunk_ids` for its `(question, product_id)`, joined by a blank line as `generate`
joins context: the evidence its reference was written from. Sized on the frame, the longest evidence plus answer is
8,066 characters, about 2,300 tokens with the rubric, under 4,096. The prompt follows `prompt-v1` line for line:

```
You check answers from an online shop's assistant.

Question: {question}

Documents, the correct product and policy documents for this question:
{evidence}

Answer to check:
{answer}

Is the answer to check correct for this question, judged against the documents?
- CORRECT: everything it says agrees with the documents. More or fewer details are fine if nothing it says differs.
- INCORRECT: it states a different number, time, condition or fact; it is about a different product or a
  different policy; or it says "yes" where the documents say "no", or the reverse.
- A bare "Yes." or "No." is CORRECT when the documents give the same yes or no.
- If the documents do not answer the question, the answer is CORRECT only if it also gives no answer.
- If the documents give the answer and the answer to check says it does not know, it is INCORRECT.

Reply with exactly one word: CORRECT or INCORRECT.
```

**The sheets.** The first sheet has one section per item: `## Item N`, the question, the product id, the gold
evidence chunk by chunk (as 5.1's sheet shows it), the answer, and an empty `label:` line. Its header restates the
rubric of `prompt-v1`, with "documents" in place of "reference". The second sheet adds the reference answer and the
author's locked label (read-only), and has an empty `reference right:` line.

**The scores** (`metrics.md` M21, new).
- *Agreement:* equal labels over the pairs where both sides decided (the author not `unsure`, the judge not
  `UNPARSED`), with a Wilson interval (R8; `answerability_check.wilson` is reused).
- *Cohen's κ:* `(p_o − p_e) / (1 − p_e)`; `undefined` when `p_e = 1`. No interval (R8: it is not a rate).
- *Recall of `INCORRECT`:* judge `INCORRECT` among author `INCORRECT`; *precision:* author `INCORRECT` among judge
  `INCORRECT`; a Wilson interval each.
- Hits and MISSes are reported apart. The hits figure is the one 5.3 reads.
- *Circularity* (Entry 6; Entry 5 had the reference-free judge in the author's place): A1 = agreement of
  `judge-v1` and the author on hits at 1.0; A0 = the same below 1.0.
  **Bounded** if A0 ≥ A1, or A0's Wilson interval contains A1; **quantified** otherwise, with A1 − A0 reported as
  the inflation. Both are printed with n, so a bound from about 10 pairs reads as weak.
- *Layer 5:* k = the `reference right: no` marks; n = the sample's keys the author decided; Wilson. A reference is
  checked only where the verdicts disagree: a wrong reference that changed no verdict caused no judge error.

**Files.**
- `experiments/scripts/label_ablation.py` (new): `frame(records, judge_records) -> (list[dict], dict[str, int])`
  (the frame, and the excluded counts by reason); `draw(frame, n_miss, seed) -> list[dict]`;
  `evidence(index_row, texts) -> str`; `write_sheet(...)`, `parse_sheet(text) -> dict[int, str]`;
  `ask_judge_rf(question, evidence, answer, cfg, post) -> (reply, seconds, prompt_eval_count)`;
  `rf_sanity(...)`, `rf_run(...)`, `lock(...)`, `write_refsheet(...)`, `parse_refsheet(...)`;
  `agreement(pairs)`, `kappa(pairs) -> float | None`, `circularity(a1, a0) -> str`, `score(...) -> dict`,
  `check_entry6_first(prereg_text, sheet_written_at) -> list[str]`.
  Commands `draw`, `rf-sanity`, `sheet`, `rf` (refuses: Entry 6), `lock`, `score`.
- `experiments/judge/prompt-rf-v1.txt`, `experiments/judge/judge-rf-v1.json` (new).
- `experiments/tests/test_label_ablation.py` (new). `Makefile`: five `ablation-*` targets (`ablation-rf` removed).
- Outputs, committed (IDs, verdicts and labels only): `experiments/results/<run>/ablation/` — `draw.json`,
  `sample.jsonl`, `items.jsonl`, `labels.jsonl`, `refcheck.jsonl`, `scores.json`.
  Private, gitignored: this trail's `evidence/private/sheet.md`, `refsheet.md` and `rf-sanity-{1,2,3}.log`.
- Docs: `preregistration.md` Entries 5 and 6; `metrics.md` M21 and layer 5's fields; `interfaces.md` §I and v0.33.

**Failure modes, silent ones first.**
1. **The author sees the reference or a verdict before labelling.** The agreement comes out too high, with no
   sign. Caught by DC 4 (the absent fields), and by DC 6: the reference appears only in the second sheet, after the lock.
2. **A label lands on the wrong key** (the shuffle). A plausible wrong agreement. Caught by DC 4's round-trip test.
3. **`score` still reads a reference-free file**, or computes circularity from one. (b), (c) or (e) would rest on
   the failed judge. Caught by DC 5's no-file test and DC 7's circularity test. (Entry 5's failure modes "prompt
   cut at `num_ctx`" and "schemes differ in more than the prompt" no longer arise: no reference-free run.)
4. **Entry 6 written after the sheet.** The change could be steered by what the sheet shows. Caught by DC 1.
5. **Hits and MISSes pooled.** One agreement over two sampling rates. Caught by DC 7 (reported apart).
6. **κ or Wilson computed wrong.** Plausible wrong numbers. Caught by DC 7's hand-computed tests.
7. **Labels edited after the second sheet.** The first pass is no longer blind. Caught by DC 6's lock.
8. **Entry 5 written after seeing data.** Caught by DC 1's time order.
9. **Corpus text in a committed file.** A licence breach with no error. Caught by DC 7's no-text test.
10. **The frame keeps a record it should exclude.** Caught by DC 3's tests.

**Edge cases.**
- `unsure`, and an `UNPARSED` verdict: out of their agreement denominators, counted beside. (Entry 5's 2 %
  `UNPARSED` rule for the reference-free run no longer applies: no such run, Entry 6.)
- κ is `undefined` when both sides use only one label.
- `answerable: false` keys follow the rubric's "no answer" rule and are their own row (R6).
- A disagreement where the author is `unsure` is not a disagreement and gets no second-pass item.

**Unknowns.**
- U1: whether `prompt-rf-v1` passes the 12 sanity pairs. Settled 2026-11-11: it does not (8 of 12; §4).
- U2: the size of the second pass. 5.1's numbers suggest 10–20 items.

**Verification.**
- DC 1: Entry 5's and Entry 6's date-times against the `written_at` fields, read by the score step and printed.
- DC 2: the three sanity logs, and a grep of Entry 6. DC 3: `make ablation-draw` twice, and the unit tests.
- DC 4, 6, 7: `pytest experiments/tests/test_label_ablation.py`, and the lock and score steps.
- DC 5: `ls` of `ablation/`, the unit tests, and sha256 of the 5.1 files before the sheet and after the score.
- DC 8: greps of the docs. DC 9: `make verify`, and `git status` shows only new test files.

## 4. Findings

- 2026-11-11: the author confirmed both of ADR-022's rubric choices for `prompt-rf-v1.txt` and the author
  labels: a bare same-polarity "Yes." or "No." is `CORRECT`, and a partial answer that says nothing wrong is
  `CORRECT`.
- 2026-11-11, step 3.2 failed: `make ablation-rf-sanity` run 1 gave 8 of 12, 0 `UNPARSED` (`evidence/private/
  rf-sanity-1.log`). Runs 2 and 3 were not taken. RCA (`rca-analyst`): **not a code bug.** For all 12 pairs the
  evidence is the reference index's `chunk_ids`, byte-equal to what the reference writer read (epoch 0); the fields
  sit in the right slots; the longest failing prompt is 1,328 tokens, under 4096. A rebuilt-prompt probe
  (`citable: no`, pressure 2, nothing written to the repo) gave the same 4 wrong verdicts. The cause is the frozen
  judge without a reference:
  - two `unanswerable-invented` pairs → `CORRECT`: the judge does not notice that a fact is absent from the documents;
  - one `bare-yes-against-no` pair → `CORRECT`: the deciding sentence is lost in 5 chunks of band lists (chunk-0
    alone gives `INCORRECT`; one probe);
  - one `paraphrase` pair → `INCORRECT`: the source omits the unit after "36" (the published PQA file has the same
    gap); restoring it gives `CORRECT`. The rubric still makes the expected `CORRECT` right.
  Entry 5's stop rule holds: the prompt is not edited, and what comes next is the author's call.
- 2026-11-11, step 8.3, **a deviation from Entries 5 and 6** ("labels once, blind"), the author's decision. After
  labelling, the author had two AI agents, Argon 4 and Fable 5.2, label the same 100 items from the sheet, and read
  their output. The agents agree with each other on all 100 items (72 `correct`, 28 `incorrect`). They differed from
  the author on 4 items: 27, 51 and 54 (author `incorrect`, agents `correct`) and 93 (author `correct`, agents
  `incorrect`). The author re-read the four and took the agents' labels on all of them. The main session changed
  the four `label:` lines on the author's instruction; the diff against the original is those four lines only.
  - Locked and scored: the revised sheet, sha256 `b3f689e9…c2e5`, 72 `correct` / 28 `incorrect`, equal to both
    agents on every item. Kept: the original, `evidence/private/sheet.before-ai-review.md` (read-only, sha256
    `3776cdda…5cf7`, 70 / 30), and the agents' files in `evidence/private/100Sample Checkers/`. All gitignored.
  - Fable's file says it got the sheet with the author's labels filled in, blanked them first, and saw items 1–3.
    Argon's input is not recorded. Fable 5.2 is a Claude model, so super-plan line 382 ("not Claude-marked") does
    not hold for these 4 items. The review sent the sheet's PQA-derived text to outside AI services once, which
    ADR-022 avoids for the judge; nothing of it is committed.
  - Step 8.5 (2026-11-12): the author marked the second sheet: item 44 `no`, the other 17 `yes`, written into the
    file by the main session from the author's message. No AI review of the second sheet was reported.
  - What it means: every agreement with the author differs by at most 4 items from the pre-review labels. The
    deviation is stated next to the result, in `deliverables.md` and in the thesis. No DC changes.
