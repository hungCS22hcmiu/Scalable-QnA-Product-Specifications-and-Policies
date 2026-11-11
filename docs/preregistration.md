# Pre-registration record

**This file is append-only.** Every entry is dated. An entry is never edited, reordered or deleted after it is
written. A mistake is corrected by a new entry that cites the old one and says what changed. The reason: a value that is
fixed before the data exists cannot be tuned to the data, and this file is the proof of the order.

**Entries.** Each entry has a heading `## Entry N — <date> — <title>`, numbered in the order they are written, and
holds values (a model, a digest, a hash, a rule) that can be checked against a file. Prose that argues a choice belongs
in `decisions.md`, in the ADR the entry cites.

**Who reads it.** `make judge` and `make judge-sanity` refuse to run unless this file contains the sha256 of
`experiments/judge/judge-v1.json`. So Entry 1 must stay as it is, and a changed judge needs a new entry first.

**Where the rest lives.** The rules that count each metric are `contracts/metrics.md`. The key and the file layouts
are `contracts/interfaces.md` §H and §I. The reasons are ADR-022.

---

## Entry 1 — 2026-11-01 — the frozen judge, the verdict key, the reference definition, the counting rules

Written before the judge's first verdict. Item 5.1 of `super-plan.md`; trail `docs/work/2026-10-30-judge-harness/`;
decision record ADR-022. Every value below was read from the file named beside it.

| Item | Value | Read from |
| :--- | :--- | :--- |
| Judge model | `gemma3:4b-it-q4_K_M` | `experiments/judge/judge-v1.json` |
| Judge model digest | `a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a` | `judge-v1.json`; the live `/api/tags` agrees (checked 2026-11-01) |
| Prompt version | `prompt-v1` | `experiments/judge/prompt-v1.txt` |
| Prompt sha256 | `5e827704cdcbabaab800173b3588dc2a266c0c17559600502ea96b0615d3e57a` | `judge-v1.json`; `shasum -a 256 prompt-v1.txt` agrees |
| Judge options | `temperature` 0 · `seed` 20261031 · `num_ctx` 4096 · `num_predict` 8 | `judge-v1.json` |
| Thinking | `think: false` is sent only to a model whose `/api/show` lists `thinking`. gemma3 does not list it, so none is sent | ADR-022 |
| Judge record | version `judge-v1`; sha256 **`1beb1fbd864f919994e9588852cbbaf8f6448b5ede16f547471a022150594d11`** | `shasum -a 256 experiments/judge/judge-v1.json` |
| Reply parse | The reply, white space trimmed at both ends, must equal `CORRECT` or `INCORRECT`. Anything else is `UNPARSED`, with the raw reply stored. No case folding, no substring search, no stripping of a full stop | `interfaces.md` §I |
| Verdict key | `vk1`: `sha256( "vk1:" + ns(query_raw) + ns(product_id) + ns(answer_sha256) )`, with `ns(s)` = the UTF-8 byte length in decimal, `:`, the bytes, `,`. Pinned: `Is the café mug 12 oz?` + `product-x` + the empty answer's hash gives `d2f8597f95e17b78e95c3a62c7f4c2c229e25fe21bb544e5c45647200c5fbb41` | `interfaces.md` §H; `evidence/golden-key.txt` |
| Reference definition | **Gold-anchored.** `Answer(query, product_id, gold evidence)`: the served generator and its prompt, given every chunk of the query's `doc_ids` in document order from frozen `v1`, not what the system retrieved. One reference per distinct `(question, product_id)`, generated once, stored by its sha256. The generator's digest and settings, its prompt's hash and the corpus digest are written to the set's `version.json` when it is built | ADR-022; `interfaces.md` §I |
| Counting rules | `counting-v1`, `contracts/metrics.md`, dated 2026-11-01 | `contracts/metrics.md` |

**Counting choices fixed with it** (`metrics.md`). Every wrong hit counts in the false-hit rate, whatever its error
layer. The `answerable: false` queries count like any other and are their own row. `UNPARSED` leaves both the numerator
and the denominator. The layers are reported apart and never as one number.

**Stop rules fixed with it.** Each is a number written before the data.
- More than 3 of the 30 gold-evidence and reference pairs marked insufficient by the author: stop, and run no verdict.
- Any of the 12 sanity pairs judged wrongly, or `UNPARSED`: stop. The prompt is not edited. A new prompt is a new
  version and a new entry here, and the author decides.
- More than 2 % of a run's verdict keys `UNPARSED`: that run's verdict-based rates are not reported.

**Not in this entry.** The reference set's hash (the sha256 of its `index.jsonl`) does not exist yet. It is recorded in
a later entry, before the first verdict. The judge's agreement with the author's labels (item 5.2) and δ (item 5.3) are
measured later and are not pre-registered here.

---

## Names reserved for item 6.1 — 2026-11-01

Item 6.1 pre-registers the sweep before it runs (`Final_Proposal.md` §9.4; `super-plan.md` item 6.1). These four names
are reserved now and have **no content**. Item 6.1 appends each as a dated entry that cites its name, before a single
sweep point runs. The names are never edited.

| Name | What the entry will fix | Content |
| :--- | :--- | :--- |
| `6.1-a` | The granularity of the τ sweep | (empty) |
| `6.1-b` | The written selection objective for "the best fixed threshold" | (empty) |
| `6.1-c` | The lane-band bounds | (empty) |
| `6.1-d` | The range of θ | (empty) |

---

## Entry 2 — 2026-11-01 — the validation reference set

Written before the judge's first verdict: `experiments/results/` holds no run at the time of writing. Item 5.1 of
`super-plan.md`; trail `docs/work/2026-10-30-judge-harness/`. This is the entry that Entry 1 ("Not in this entry") said
would follow. It cites Entry 1 and changes nothing in it. The set was built by `make judge-references SPLIT=validation`
under the definition in Entry 1 (gold-anchored). Every value below was read from the file named beside it.

| Item | Value | Read from |
| :--- | :--- | :--- |
| Reference set | `experiments/references/validation/`, split `validation`, 622 references (one per distinct `(question, product_id)`), 608 distinct answer files | `version.json`; `wc -l index.jsonl`; `ls answers/` |
| Reference set hash | sha256 of `index.jsonl`: **`00c9a33310a66542d739a860e3e77a162658a5dddaefa00fbc3e8ea30ca558e3`** | `shasum -a 256 experiments/references/validation/index.jsonl`; the build's last log line agrees |
| `version.json` sha256 | `ed6e2878e5637b3fbe4dcd86859bb2f7a01fb7b7073f51eacd6abe232a7a95a4` | `shasum -a 256 experiments/references/validation/version.json` |
| Built at | `2026-11-01T06:27:47+00:00` | `version.json` |
| Generator | `qwen3.5:2b-q4_K_M` · digest `124a03c347777e8e4e5955c33610ae01d9d90d8c2a718bfba069c498d5c7f3c9` · `num_ctx` 8192 · `think` false · `temperature` 1.0 · prompt sha256 `3e224f4500a18dc065ab6e24c46e25302ac275f8e145085bfb211bcf65ba67dd` | `version.json`, `generator` |
| Corpus | dataset `v1` · snapshot digest `a5708fefa62cec0aef5505e9e5242bc04bf351fd02a2efb5da54a98f211bb2e4` | `version.json`, `corpus` |
| Retrieval | `retrieval_version` `adr-021` · `retrieve.py` sha256 `22ddbce24fbede8f5d16e78510291befdee2b7c7b621dce94c31587a90199ed6` · `top_k` 5 | `version.json`, `retrieval` |

**What the hash fixes.** The reference answers are not edited, rebuilt or replaced after this entry. A different set
(another split, another generator sample) has a different hash and needs its own entry first. `make judge` compares
the manifest's version fields with `version.json` and refuses on a difference.

**Not in this entry.** The author's read of the 30 gold-evidence and reference pairs (item 5.1, step 4.6) has not
happened at the time of writing. Its result and its stop rule are in Entry 1.

---

## Entry 3 — 2026-11-01 — the `reference right` cell on the sufficiency sheet

Written before the judge's first verdict: `experiments/results/` holds no run at the time of writing. Item 5.1 of
`super-plan.md`; trail `docs/work/2026-10-30-judge-harness/`. It cites Entry 1 (the `sufficient` stop rule) and
Entry 2 (the reference set and its hash) and changes nothing in either. It adds a second cell and a second stop rule
beside Entry 1's. The author chose this on 2026-11-01, after reading the decline count. Every value below was read from
the file named beside it.

| Item | Value | Read from |
| :--- | :--- | :--- |
| Why a second cell | `sufficient` asks only if the gold evidence answers the question. A reference can still be wrong, or decline, although the evidence answers, and then the judge grades a correct answer `INCORRECT` | `design.md` §3, failure mode 14 |
| Declining references | **78 of 582** `answerable: true` references match the decline pattern | the last lines of `evidence/private/references.log` (step 4.3) |
| The sheet | `evidence/private/sufficiency-v2.md`: 30 pairs, at least 10 B-within (17 drawn), seed **7**. The same 30 pairs in the same order as the unmarked `sufficiency-v1.md`, which is not used | `python3 experiments/scripts/judge_references.py sheet --split validation --seed 7`; the `## ` lines of v1 and v2 are identical |
| Cell 1 | `sufficient: yes\|no`: the gold evidence is enough to answer the question | Entry 1; the sheet's header |
| Cell 2 | `reference right: yes\|no`: the reference answer is correct by the gold evidence. A reference that declines is right only when the evidence does not answer the question | the sheet's header |
| Reference set | the set in Entry 2, unchanged: `index.jsonl` sha256 `00c9a33310a66542d739a860e3e77a162658a5dddaefa00fbc3e8ea30ca558e3` | Entry 2 |

**Stop rule fixed with it.** More than 3 of the 30 pairs marked `no` in `sufficient`: stop, and run no verdict (Entry 1,
unchanged). More than 3 of the 30 pairs marked `no` in `reference right`: stop, and run no verdict. The two counts are
read apart and never added. `judge_references.py score` prints both and exits 1 when either is over 3, or when any cell
of either kind is unmarked. Three `no` in a cell passes it.

**Not in this entry.** The author's marks do not exist at the time of writing: no cell of `sufficiency-v2.md` is
marked. The count of `reference right: no` is also a first measure of reference error for item 5.3. It is not
pre-registered as a result.

---

## Entry 4 — 2026-11-01 — the reference writer, and the validation reference set rebuilt with it

Written before the judge's first verdict: `experiments/results/` holds no run at the time of writing. Item 5.1 of
`super-plan.md`; trail `docs/work/2026-10-30-judge-harness/`; decision record ADR-023. It cites Entry 1 (the reference
definition), Entry 2 (the 2B reference set) and Entry 3 (the `reference right` cell and its stop rule), and edits none
of them. It changes one thing in Entry 1: **who writes the reference**. The gold evidence, the served prompt, the
verdict key, the judge and the counting rules are the ones in Entry 1. The served generator is unchanged. Every value
below was read from the file named beside it.

| Item | Value | Read from |
| :--- | :--- | :--- |
| Reference definition | `LLM_w(gold(q), q)`: the served prompt (`generate._PROMPT_TEMPLATE`) over every chunk of the query's `doc_ids` in document order, answered by the **reference writer** `LLM_w`, not by the served generator. One reference per distinct `(question, product_id)` | ADR-023 |
| Reference writer | `qwen3.5:4b-q4_K_M` · digest `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd` · `think` false · `num_ctx` 8192 · `temperature` 0 · `seed` 20261101 · prompt sha256 `3e224f4500a18dc065ab6e24c46e25302ac275f8e145085bfb211bcf65ba67dd` | `experiments/judge/reference-writer-v1.json`; `version.json`, `reference_writer`; the live `/api/tags` agrees |
| Writer record | version `reference-writer-v1`; sha256 **`1060f41e7f20f11e4c912364f25bdc87a964cabc2d2b219859e4eeb8106b1e27`** | `shasum -a 256 experiments/judge/reference-writer-v1.json` |
| Reference set | `experiments/references/validation/`, split `validation`, 622 references, 507 distinct answer files | `version.json`; `wc -l index.jsonl`; `ls answers/` |
| Reference set hash | sha256 of `index.jsonl`: **`0e84389981f4bfcdfa6cd3fbd0e7b5bf9662facba02564ca562e7a65520c974a`** | `shasum -a 256 experiments/references/validation/index.jsonl`; the build's last log line agrees |
| `version.json` sha256 | `11bcc1ce730777594ec7ba2a66a8efe5c6817720820a061e58a8fb29e0fb2f42` | `shasum -a 256 experiments/references/validation/version.json` |
| Built at | `2026-11-01T10:33:02+00:00` | `version.json` |
| Declining references | **53 of 582** `answerable: true` references match the decline pattern (Entry 3: 78 of 582 for the 2B set) | the last lines of `evidence/private/references-4b.log` |
| Served generator | unchanged: `qwen3.5:2b-q4_K_M` · digest `124a03c347777e8e4e5955c33610ae01d9d90d8c2a718bfba069c498d5c7f3c9` · `temperature` 1.0 | `version.json`, `generator` |
| Corpus and retrieval | dataset `v1` · snapshot digest `a5708fefa62cec0aef5505e9e5242bc04bf351fd02a2efb5da54a98f211bb2e4` · `retrieval_version` `adr-021` · `retrieve.py` sha256 `22ddbce24fbede8f5d16e78510291befdee2b7c7b621dce94c31587a90199ed6` · `top_k` 5 | `version.json`, `corpus` and `retrieval` |
| The 2B set | moved, not edited, to `experiments/references/validation-qwen2b-t1/`; `index.jsonl` sha256 still `00c9a33310a66542d739a860e3e77a162658a5dddaefa00fbc3e8ea30ca558e3` (Entry 2). It is kept as the baseline and is not used for any verdict | `shasum -a 256 experiments/references/validation-qwen2b-t1/index.jsonl` |

**What the hash fixes.** The reference answers in `experiments/references/validation/` are not edited, rebuilt or
replaced after this entry. Entry 2's set is superseded for verdicts. `make judge` refuses a set whose `version.json`
has no `reference_writer`, or whose writer differs from `reference-writer-v1.json` in `model`, `digest`, `options`,
`think` or `prompt_sha256`, and it still compares the manifest's version fields with `version.json`.

**Stop rule, unchanged.** The author marks `reference right` again on `sufficiency-v3.md`: the same 30 pairs in the
same order (seed **7**), blind. The `sufficient` marks are copied from the author's marks on `sufficiency-v2.md`,
because the gold evidence of the 30 pairs has not changed. More than 3 of the 30 pairs marked `no` in either cell:
stop, and run no verdict (Entries 1 and 3).

**Not in this entry.** The author's marks on `sufficiency-v3.md` do not exist at the time of writing. No verdict has
run.

---

## Entry 5 — 2026-11-11 05:41Z — the labelling ablation (item 5.2)

Written before any reference-free verdict, before the draw of the sample and before the labelling sheet: the files
`ablation/draw.json`, `ablation/verdicts-rf.jsonl` and the sheet do not exist at the time of writing. Item 5.2 of
`super-plan.md`; trail `docs/work/2026-11-11-labelling-ablation/`. It cites Entry 1 (the frozen judge, the verdict key,
the counting rules, the stop rules) and Entry 4 (the reference set), and edits none of them. `judge-v1`, its prompt, the
references and the served generator are unchanged. Every value below was read from the file named beside it.

| Item | Value | Read from |
| :--- | :--- | :--- |
| Reference-free judge record | version `judge-rf-v1`; sha256 **`032513a3636766557b507b14184d53ee90604e588ead084c62f899b2d589462e`** | `shasum -a 256 experiments/judge/judge-rf-v1.json` |
| Reference-free prompt | `prompt-rf-v1`; sha256 `66c655dce75e68fb6a5e3c54d73c5fc6a696e562c4d84336818085c5dfe0e61b` | `experiments/judge/judge-rf-v1.json`, `prompt_sha256`; `shasum -a 256 experiments/judge/prompt-rf-v1.txt` agrees |
| Model, digest and options | equal `judge-v1`'s: `gemma3:4b-it-q4_K_M` · digest `a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a` · `temperature` 0 · `seed` 20261031 · `num_ctx` 4096 · `num_predict` 8. Only the prompt differs | `judge-rf-v1.json` against `judge-v1.json` (checked 2026-11-11) |
| Source run | `2026-11-01T21-17-56_cfg4_judgecost` (configuration 4, gate on, MIXED off, `v1` validation). It supplies the items to label; none of its rates is used | `experiments/results/2026-11-01T21-17-56_cfg4_judgecost/manifest.yaml`, `run_id` |
| Frame | the run's served records, minus the records with no `product_id`, and minus the Tier-2 hits on another product's entry. 600 distinct verdict keys: 521 MISS, 69 hits at `source_overlap` 1.0, 10 hits below 1.0. The draw prints the counts and the excluded counts by reason (16 and 6) | `design.md` §1 and §3; `ablation/draw.json` (to be written) |
| Strata | **hits**: every hit in the frame, a census (79). **MISS**: 21 drawn by `random.Random(20261111)` from the MISS keys sorted by verdict key. Sample size 100 | `design.md` §3, "The sample" |
| Bucket edges | by `source_overlap` on hits: `1.0` and `below 1.0` decide the circularity rule; shown only: `[0.8, 1)`, `[0.6, 0.8)`, `below 0.6`. A MISS is its own bucket, `generated` | `design.md` §3, "The sample" |
| Evidence rule | a key's evidence is the reference index's `chunk_ids` for its `(question, product_id)`, the chunk texts joined by a blank line as `generate` joins its context | `experiments/references/validation/index.jsonl`, `chunk_ids`; `design.md` §3 |
| Sanity set | item 5.1's 12 sanity pairs, each with its gold evidence in place of the reference | `docs/work/2026-10-30-judge-harness/evidence/private/sanity-v1.jsonl` |
| Author's labels | one per sampled key, from the question and the gold source documents, `correct`, `incorrect` or `unsure`; blind (no reference, verdict, cache outcome, overlap or stratum on the sheet); locked by the sha256 of the first sheet before the second sheet shows any reference | `design.md` §3, "The order" |

**The metrics** (`design.md` §3, "The scores"; `metrics.md` M21, new).
- Agreement: equal labels over the pairs where both sides decided, with a Wilson interval. Cohen's κ, `undefined` when
  both sides use only one label, with no interval. Recall and precision of `INCORRECT`, a Wilson interval each.
- Hits and MISSes are reported apart and never pooled: they are sampled at different rates. The hits figure is the one
  item 5.3 reads.
- Circularity: A1 = agreement of `judge-v1` and the reference-free judge on hits at 1.0; A0 = the same below 1.0.
  **Bounded** if A0 ≥ A1, or A0's Wilson interval contains A1; **quantified** otherwise, with A1 − A0 reported as the
  inflation. Both are printed with n, so a bound from about 10 pairs reads as weak.
- Layer 5: k = the `reference right: no` marks; n = the sample's keys the author decided; Wilson. A reference is
  checked only where `judge-v1` and the author both decided and disagree.

**The counting** (`design.md` §3, "Edge cases").
- An author `unsure` and a judge `UNPARSED` are out of their agreement denominators, and are counted and reported beside
  them. A disagreement where the author is `unsure` is not a disagreement and gets no second-pass item. Nothing is guessed.
- `answerable: false` keys follow the rubric's "no answer" rule and are their own row.

**The stop rules.**
- Any wrong or `UNPARSED` verdict on the 12 sanity pairs, or a verdict that differs between the 3 runs: stop. The prompt
  is not edited. A new prompt is a new version and a new entry, and the author decides (Entry 1).
- More than 2 % of the reference-free run's sampled keys `UNPARSED`: its rows are not reported.
- Any call whose `prompt_eval_count` is at or above `num_ctx` (4096): stop.

**The author's confirmation of ADR-022's two rubric choices.** `design.md` §4, 2026-11-11: "the author confirmed both of
ADR-022's rubric choices for `prompt-rf-v1.txt` and the author labels: a bare same-polarity "Yes." or "No." is
`CORRECT`, and a partial answer that says nothing wrong is `CORRECT`."

**Not in this entry.** No reference-free verdict, no draw and no label exists at the time of writing. δ (item 5.3) is
not set here.

---

## Entry 6 — 2026-11-11 06:37Z — the labelling ablation after the sanity failure (item 5.2)

Written after `judge-rf-v1`'s three sanity runs and before the labelling sheet: `evidence/private/sheet.md` and
`ablation/items.jsonl` do not exist at the time of writing, and no label exists. Item 5.2 of `super-plan.md`; trail
`docs/work/2026-11-11-labelling-ablation/`. It cites Entry 5 and edits none of the earlier entries. It changes one
thing in Entry 5: **who makes the reference-free labels**. The frame, the draw, the strata, the bucket edges, the
metrics, the rubric and its two confirmed choices, and `judge-v1` are the ones in Entries 1 and 5. The draw
(`ablation/draw.json`, `sample_sha256` `721c490da4a9303ea779d573feb2ba52c05e167424f31035ef2d953010572fe2`) was
written at 2026-11-11T05:58:57Z, before this entry, and is not repeated. IDs only: no question, answer or evidence
text is in this entry.

**What happened.** The 12 sanity pairs of item 5.1 were judged by `judge-rf-v1` (record sha256
`032513a3636766557b507b14184d53ee90604e588ead084c62f899b2d589462e`), each with its gold evidence in place of the
reference, three times (`make ablation-rf-sanity`; `evidence/private/rf-sanity-{1,2,3}.log`, gitignored).

| Run | written_at (UTC) | Memory pressure | Last line |
| :--- | :--- | :--- | :--- |
| 1 | 2026-11-11T05:59:21 | 1 | `8 of 12 correct, 0 UNPARSED` |
| 2 | 2026-11-11T06:35:42 | 1 | `8 of 12 correct, 0 UNPARSED` |
| 3 | 2026-11-11T06:36:38 | 2 (`citable: no`) | `8 of 12 correct, 0 UNPARSED` |

- The same 4 pairs were wrong in all three runs, and the 8 verdict lines of the other pairs were the same in all three
  (the verdict lines of the three logs are byte-equal). The wrong pairs, by `kind` and `qa_id`:
  - `bare-yes-against-no`, `q-product-phones-b07ck7kb95-394147-seed`: expected `INCORRECT`, got `CORRECT`
  - `unanswerable-invented`, `q-product-furniture-b0034jxwwc-53228-u-seed`: expected `INCORRECT`, got `CORRECT`
  - `unanswerable-invented`, `q-product-laptops-b07wgqwnlf-46510-u-seed`: expected `INCORRECT`, got `CORRECT`
  - `paraphrase`, `q-product-furniture-b07gbsvygk-17484-seed`: expected `CORRECT`, got `INCORRECT`
- The cause (`design.md` §4, the RCA): not a code bug. The evidence is the reference index's `chunk_ids`, the same
  chunks the reference writer read, and the longest failing prompt is far below `num_ctx`. Without a reference, the
  frozen judge passes facts that the documents never mention, which is the error `judge-v1` exists to catch.

**The decision** (the author's, 2026-11-11).
- No new prompt version: a `prompt-rf-v2` written after seeing these 4 failures would be tuned on the check.
- No reference-free run is made. `judge-rf-v1` is used for no score. `ablation/` holds no `verdicts-rf.jsonl` or
  `rf.json`.
- The author's labels, made without the reference (Entry 5: from the question and the gold source documents), are the
  reference-free side.

**What changes in Entry 5.**
- (b), the reference-free judge against the author, is not computed.
- (c) is `judge-v1` against the author, per hit bucket (`1.0`, `[0.8, 1)`, `[0.6, 0.8)`, `below 0.6`, `below 1.0`), and
  for MISS the bucket `generated`: n, agreement with Wilson, κ.
- Circularity: A1 = agreement of `judge-v1` and the author on hits at 1.0; A0 = the same on hits below 1.0. **Bounded**
  if A0 ≥ A1, or A0's Wilson interval contains A1; **quantified** otherwise, with A1 − A0 reported as the inflation.
  Both are printed with n, so a bound from about 10 pairs reads as weak.
- The stop rules on the reference-free run (`UNPARSED` above 2 %; `prompt_eval_count` at or above `num_ctx`) no longer
  apply: no such run is made. The sanity stop rule was applied: the prompt is not edited.
- Everything else in Entry 5 holds: the frame, the sample, the metrics (agreement, κ, recall and precision of
  `INCORRECT`, layer 5), hits and MISSes apart, and the counting rules (`unsure` and `UNPARSED` out of their
  denominators, counted beside; `answerable: false` its own row).

**The limit.** The overall and the per-bucket agreements now compare the same two labellers, `judge-v1` and the
author. So item 5.2's "both schemes" are one comparison shown two ways. There is one labeller and no inter-rater
check.
