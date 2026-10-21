# Rules — the workload's model layer (item 3.4)

**Status: committed before the first sheet is read** (spec W18). `build_workload.py` refuses to
write a sheet or import a row while this file is uncommitted or changed, and records its sha256
with every batch. Changing a rule after the first sheet has been read needs `/approve experiment`
again (plan step 10).

These are the rules of `design.md` draft 2 (§2 – §4, §8), in the exact form the script checks.
Where the design left a detail open, this file fixes it; each such detail is marked **(fixed
here)** and listed again in §10.

## 1. Who writes, and how

- **The writer is Claude** (`claude-opus-5-5`), in this session, never Qwen (the author,
  2026-10-21). A batch written by a subagent records that subagent's model id.
- **The loop:** `make workload-sheets ROUND=<round> OUT=<scratch dir>` writes sheets outside the
  repository. The writer reads one sheet and writes `<sheet>.rows.jsonl` beside it, one JSON object
  per line. `make workload-import IN=<that file>` checks every row and appends the valid ones to
  `data/v1-draft/workload/model-layer.jsonl` (gitignored).
- **A sheet is all the writer reads:** the record, the question, the policy section. The writer
  never opens `data/v1-draft/` itself.
- **A rejected row is written again by the writer, never repaired by a script.** Re-importing a row
  with the same content is skipped; with other content it is rejected, never an overwrite.
- **Rows in one file are checked in a fixed order** (name, label, relabel, policy, natural, seed,
  para, lookalike, d, cell, blind, swap), so a seed and its paraphrases can share a file.
- **Every import** adds one line to `evidence/batches.md`: the time, the file's sha256, the model
  id, this file's sha256 and the counts. No question text and no asin.

## 2. Constants

Fixed before any label is read (design §2.2). The pilot (`evidence/pilot.md`) moved none. A count
is never pushed toward a number by changing one of these after labels exist.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `SEED` | `v1-item-3.4` | every hash order in this item: `sha256(SEED:…)` |
| `MODEL_ID` | `claude-opus-5-5` | the writer, recorded per batch |
| `SPEC_SEEDS_PER_PRODUCT` | 2 | spec seeds per product |
| `PARAPHRASES_PER_SEED` | 2 | one close, one far |
| `SPEC_LOOKALIKES_PER_PRODUCT` | 1 | on the product's first seed |
| `POLICY_PRODUCTS_PER_CELL` | 3 | products in an ordinary policy cell |
| `TWIN_PRODUCTS_PER_CELL` | 20 | products in a minimal-pair cell, both sides |
| `TWIN_WORDINGS_DEPT` | 8 | wordings a side, laptops department-level twins |
| `D_PER_PRODUCT` | 1 | D questions per chosen product |
| `D_PRODUCT_STRIDE` | 2 | every other eligible product, in hash order |
| `UNANSWERABLE_SEEDS` | 13 | per department |
| `UNANSWERABLE_PARAPHRASES` | 1 | per unanswerable seed (a close one) |
| `RELABEL` | 40 | pass-1 questions labelled twice, in a later batch |
| `R2_UNANSWERABLE_SAMPLE` | 40 | per department: R2-unanswerable questions pass 1 labels **(fixed here)** |
| `NATURAL_JACCARD_MIN` | 0.45 | natural-pair candidates: token Jaccard at least this |
| `NATURAL_JACCARD_MAX` | 0.99 | …and at most this (an equal token set is a duplicate) |
| `NATURAL_PER_PRODUCT` | 3 | natural-pair candidates per product **(fixed here)** |
| `MIN_TWINS_PER_SPLIT` | 30 | minimal-pair twins each split must hold, or the build stops |
| `NAME_WORDS` | 2 – 6 | words in a short name |
| `EVIDENCE_WORDS` | 3 – 30 | words in an evidence quote |
| `QUESTION_MAX_WORDS` | 30 | words in a written question |
| `ANSWER_MAX_WORDS` | 30 | words in a written answer **(fixed here)** |
| `ATTRIBUTE_MAX_WORDS` | 6 | words naming a lookalike's attribute **(fixed here)** |
| `R10_NGRAM` | 4 | R10's shared-sequence length |

## 3. Words the checks use

- **Tokens:** lower case, split on anything but `a-z0-9`, one-character tokens and digits kept,
  Lucene's 33 English stop words removed. Never the probe's tokenizer ("Windows 7" and "Windows 8"
  must stay apart). **Raw tokens** are the same without the stop-word step.
- **The record:** the product's title and each of its spec values ("Feature n", "Description",
  "Brand"), white space collapsed. These are the **fields**.
- **Evidence:** a verbatim part of **one** field, 3 – 30 words, case and punctuation as written
  (white space may differ). Two pieces of evidence **overlap** when they sit in the same field and
  their character ranges meet.
- **Names the product:** the short name's raw tokens appear in the question, together and in order.
- **Digits:** the runs of `0-9` in a text, **less the short name's own digits** **(fixed here)**:
  "Zenvo X2" carries a 2 that the original "How long does it last?" lacks.
- **One question:** ASCII, at most 30 words, exactly one `?`, at the end.
- **Polarity:** an answer whose first word is "Yes" or "No" has that polarity; any other has none.
- **Tier-1 form:** `corpus_gate.normalize_t1`. No two queries in the workload share one (W5).
- **Condition words:** `corpus_gate.CONDITION_AXES`, G5's list, read by `condition_hits`. "new" and
  "brand-new" count only inside the laptops returns family, as in G5.

## 4. Rounds and row formats

Every row carries `key` and `type`, plus the fields below, and nothing else. The key is the task's
key, printed on the sheet with an empty skeleton to fill.

**Round `label` (pass 1).**

| Type | Fields | Rule |
| :--- | :--- | :--- |
| `name` | `name` | R1 |
| `label` | `answerable` (true / false), `answer`, `evidence` | R2 |
| `relabel` | as `label`; opens only after the first label is imported | R2 |
| `policy` | `assign`, `shape`, `variant`, `kind` | R7 a |
| `natural` | `mark`, `a_answer`, `a_evidence`, `b_answer`, `b_evidence` | R9 |

**Round `write` (pass 2).** Opens only when every `label`-round task is done, the repeats included.

| Type | Fields | Rule |
| :--- | :--- | :--- |
| `seed` | `question` | R3 |
| `para` | `question` | R4 |
| `lookalike` | `question`, `attribute`, `answer`, `evidence` | R5 |
| `d` | `question`, `answer`, `evidence` | R8 |
| `cell` | `wordings` (a list), `origin`, `source` | R7 b, R10 |

**Round `check` (pass 2, later batches).** A task opens once its target row is imported.

| Type | Fields | Rule |
| :--- | :--- | :--- |
| `blind` | as `label` | R2, on the query alone |
| `swap` | as `label`, plus `same_answer` (true / false) | R6 |

A `blind` key is opaque (`blind:` and 16 hex characters), so the sheet does not show the query's
role or seed **(fixed here)**. The sheet lists a product's blind queries in hash order.

## 5. The rules

**R1 Name.** One short name per product: 2 – 6 words, every raw token from the title, ASCII, unique
among the 152 by Tier-1 form. *Checked.* Write the name a shopper would say ("Galaxy A10e").

**R2 Label.** Answerable only if the record states the fact that answers the question, with no
outside knowledge. A yes / no question is answerable if the record settles it either way. Unsure →
not answerable. An answerable label carries `answer` (one line, at most 30 words) and `evidence`
(§3). An unanswerable label carries both empty. *Checked:* the shape and the evidence. Pass 1
labels the original question. The `check` round labels every written spec query **on its own,
without its seed** (`blind`).

**R3 Rewrite** (`seed`). Replace "this", "it", "the item" and the like with the short name; keep
every other word's meaning; add no fact; one question. *Checked:* one question, names the product,
digits equal to the original's, a new Tier-1 form.

**R4 Paraphrase** (`para`). *Close:* change a few words. *Far:* different words and order. Both keep
the short name and the answer, and change no number, unit, model name or value. *Checked:* one
question, names the product, digits equal to the seed's, **no record token the seed lacks**
(catches Verizon → AT&T, front → rear when the record names both), a new Tier-1 form. Its
`blind` evidence must overlap the seed's pass-1 evidence (§8).

**R5 Lookalike.** Same product, a few words changed, a different attribute, with the probe's own
`answer` and `evidence`. *Checked:* one question, names the product, evidence in the record and
**not overlapping the seed's**, and when both answers have a polarity, **a different polarity**;
a new Tier-1 form.

**R6 Name swap.** The script swaps the partner's short name into the product's first seed (both
ways inside a unit pair, round a triple). It drops the swap when a title token unique to the first
product remains (review M5 d). The writer labels the swapped question against the **partner's**
record and marks `same_answer` against the first product's answer, which the sheet shows.
Unanswerable → dropped by the build, counted.

**R7 Policy.** *(a) Assign.* Each real pool policy question (§6) gets `assign`: a policy `doc_id` of
its own department, or `ambiguous` (its condition cannot be known; give `kind` and `shape`),
`not_covered` or `not_policy` (`shape` null). An assigned or ambiguous question carries its `shape`
(§7); `variant: "fee"` marks a phones return `term` question about the fee. *(b) Cell wordings.*
Each policy cell (§7) gets its wordings: one per product-level cell, with `{name}` exactly once
where the product goes; `TWIN_WORDINGS_DEPT` for a department-level cell, naming no product. A
wording starts from a real question assigned to the cell's department, kind and shape (or ambiguous
with that kind and shape) where one fits: `origin: "pqa-template"`, `source: "<doc_id>:<line_no>"`.
Only where none fits does the writer write one: `origin: "claude"`, `source: null`. *Checked:* one
question each; `{name}` as above; on a split family the wording names its own condition value and
not the sibling's, **with a word from G5's list** ("opened", not "after opening"); on an unsplit family it names no condition; it names no word of the other kind
("warranty" in a return question); R10; no two wordings of a cell share a Tier-1 form; a
`pqa-template` source was assigned to that department, kind and shape. **(fixed here):** a real
policy question is used as a cell's source wording, re-targeted; it does not become a query about
its own product (design R7's "assigned ones are rewritten" read this way, so one cell is one
question and one cluster).

**R8 D** (`d`). One question about one product that needs a product fact (with `evidence`) and its
policy document's term. *Checked:* one question, names the product, evidence in the record, the
answer holds one of the document's `terms` exactly as written, the condition rule of R7 for that
document, R10, a new Tier-1 form.

**R9 Natural pairs.** For each candidate pair (§6) the writer marks `same` (one answer), `different`
(two answers) or `unanswerable` (either side), with `answer` and `evidence` for both sides unless
unanswerable. *Checked:* the mark, and both answers and evidence when the mark is not
`unanswerable`. A pair is never one cluster without a `same` mark.

**R10 No shared policy wording.** No policy wording or D question shares a 4-token sequence with any
policy document's title and text, after the short name, every term string and every condition word
are taken out of both. *Checked.*

## 6. Which questions and products (the script's choices)

- **Pass-1 labels:** every R2-answerable spec question, and per department the first
  `R2_UNANSWERABLE_SAMPLE` R2-unanswerable spec questions in `sha256(SEED:r2-sample:<doc_id>:<line_no>)`
  order. **Repeats:** the first `RELABEL` of those in `relabel` hash order.
- **Policy questions:** every pool line tagged `policy`, and every other line that names
  "replace(ment)", "send (it / them) back", "sent back" or "exchange" (ADR-011: the tag misses
  them).
- **Natural candidates:** pairs of spec questions on one product with token Jaccard in [0.45, 0.99],
  taken greedily by Jaccard (ties by hash) so no question is in two pairs, at most
  `NATURAL_PER_PRODUCT` a product.
- **Spec seeds:** per product, its Claude-answerable pass-1 labels (from both R2 tags, review L6)
  outside the natural candidates, in `seed` hash order: the first two. The first one also gets the
  lookalike and the name swaps.
- **Unanswerable seeds:** per department, its Claude-unanswerable pass-1 labels outside the natural
  candidates, in `unanswerable` hash order: the first 13, each with one close paraphrase.
- **Eligible products** for a policy or D query (W6): not flagged by `check_policies.RISKY_TITLE` in
  the title **or any spec** (review L7), and a short name that names no condition word.
- **D:** per department, the eligible products in `d` hash order, every other one. The k-th of them
  uses the department's warranty document when k is even and its return document when k is odd; on
  a split family, the default condition (unopened, new, domestic) **(fixed here)**.
- **Units:** per leaf, products in `unit` hash order, two at a time; an odd leaf ends in one triple.

## 7. Policy shapes, cells and twins

**Shapes** are found by heading text, never by position (review L1). `term` is the opening paragraph,
the only place a number answers.

| Shape | Return document heading | Warranty document heading |
| :--- | :--- | :--- |
| `term` | the opening paragraph | the opening paragraph |
| `what` | What to send back | What the warranty covers / What international service covers |
| `start` | How to start a return | How to make a claim / Asking for help abroad |
| `remedy` | Your refund | Repair, replacement or refund / Repair or replacement / Repairs arranged abroad |
| `except` | Items / Pieces / Phones we cannot take back or accept | What the warranty does not cover / What is not covered |
| `other` | Exchanges | Proof of purchase and transfer |

**Cells.** A cell is (document, shape), one question meaning, one cluster. Every (document, shape)
is an **ordinary cell** of 3 products, except the six the twin groups replace. **74 cells:** 66
ordinary, 8 twin.

| Twin group | Cells, both sides | Differs by | Size | `probe_kind` |
| :--- | :--- | :--- | :--- | :--- |
| phones returns `term`, **fee** | opened / unopened, `variant: fee` (added; the window cells stay ordinary) | $45 against no fee | 20 products | `policy-condition` |
| phones returns `remedy` | opened / unopened (replaces the ordinary cells) | refund less the fee against the full refund | 20 products | `policy-condition` |
| furniture returns `term` | opened / unopened (replaces the ordinary cells) | 180 against 365 days | 20 products | `policy-condition` |
| laptops returns `term` | new / renewed, department level, no product named (replaces the ordinary cells) | 30 against 90 days | 8 wordings | `condition-department` |
| phones warranty, every shape | international built against domestic | covered against not covered | 3 products | `policy-region` |
| warranty `term`, every department but laptops | warranty `term` built against the department's return `term` | length against window | 3 products | `policy-kind` |

**Products per cell (fixed here)**, from the department's eligible products: a twin cell takes the
first 20 in `policy` hash order, the same on both sides; an international phones cell takes its
domestic sibling's 3; a warranty `term` cell takes the first 3 of the return `term` cell it is built
against (laptops has no product-level return `term` cell, so its warranty `term` cell is ordinary);
every other cell takes the first 3 in its own `policy:<cell>` hash order. Laptops returns `term` is
**department level only**, so no laptop is named against the renewed window.

## 8. How the build reads the rows (fixed here; applied at plan step 6)

- **A `blind` label must agree, or the query is dropped and counted** (review M5 a, e). A spec seed
  or a paraphrase: answerable, with evidence overlapping the seed's pass-1 evidence. A lookalike:
  answerable, overlapping its own evidence. A natural-pair query: answerable, overlapping its side's
  evidence in the `natural` row. An unanswerable seed or its paraphrase: not answerable.
- **A dropped seed takes its cluster with it**: its paraphrases, and the lookalike and the swaps
  built against it. Nothing replaces it; no seed is re-drawn.
- **A swap:** answerable and different → `name-swap` (a trap); answerable and the same →
  `name-swap-same` (kept, never a trap). When both answers have a polarity, the polarities decide;
  otherwise `same_answer` does. Unanswerable → dropped.
- **A natural pair:** `same` → one cluster of two (`role: natural`); `different` → two queries, each
  built against the other (`probe_kind: natural`); `unanswerable` → dropped.
- **Clusters and probes:** a spec seed and its paraphrases are one cluster; a lookalike, a swap and
  a D question are each a cluster of one; a policy cell is one cluster (for a department-level cell,
  its 8 wordings). Condition twins point at each other; a region twin points at its domestic query;
  a kind twin points at the return `term` query of the same product.
- The RELABEL repeats are reported (agreement), never used. Strata, units, the split and the rank
  follow `design.md` §2.4 – §2.6.

## 9. Pre-registered analysis rules (design §8, review Q11)

Phase 6 computes these; changing one needs an ADR.

- **A1 — Pair level** (review M2, Q4). Per-stratum figures and RQ2a are computed per (query, judged
  candidate) pair: `candidate_entry_id` → the MISS record that wrote the entry (I9 guarantees one) →
  its `query_normalized` → the workload record → its `cluster_id`, `doc_ids` and `probe_kind`. RQ2a
  = the share of condition-twin requests, made while their twin's entry was live, that were served
  from it. Per-stratum results are also given by the logged `similarity` in bins of 0.02 from 0.80.
- **A2 — Which probes each figure reads** (review H1). "B-within against B-cross" (§9.2 (ii)) reads
  the provenance-different kinds: `policy-kind`, `policy-region`, `name-swap`, and the
  `spec-attribute` and `natural` probes whose 3.6 measurement shows different evidence chunks. RQ2a
  reads `policy-condition` and `condition-department`. `name-swap-same` is never a trap and appears
  only in the namespace-cost row.
- **A3 — A robustness row by wording source** (review M6 c). The headline is also reported on
  `origin ∈ {pqa, pqa-template}` alone.
- **A4 — The static arm's warm set** (review M1). Warm with one record per cluster (its lowest rank)
  plus every `pair_of` target; replay every other record once, in rank order. Item 6.3 uses this set
  unless an ADR changes it.

## 10. Details fixed here that the design left open

1. `R2_UNANSWERABLE_SAMPLE = 40` per department, the size of the R2-unanswerable sample.
2. `NATURAL_PER_PRODUCT = 3`, taken greedily so no question is in two pairs.
3. Digits are compared **less the short name's digits**.
4. `ANSWER_MAX_WORDS = 30`, `ATTRIBUTE_MAX_WORDS = 6`, and "one question" means one `?`, at the end.
5. A real policy question is a cell's **source wording**, not a query about its own product.
6. Laptops returns `term` is department level only.
7. The product choice per cell, and D's document (warranty and return alternating, the default
   condition on a split family).
8. A product is eligible for a policy or D query only if its short name names no condition word.
9. `blind` keys are opaque; a blind sheet is in hash order.
10. The build's agreement and drop rules (§8).
