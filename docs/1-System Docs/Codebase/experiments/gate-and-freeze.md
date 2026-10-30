# `experiments/scripts/` — the corpus gate and the freeze

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `corpus_gate.py` (1,908 lines), `freeze_corpus.py` (823). The
criteria are `docs/data-card.md` §7; the decisions are ADR-014 (G1 recorded as failed) and ADR-015 (the freeze).

## 1. Purpose

**The gate** checks, before the corpus is frozen, that it still **contains the effect the study needs**: questions
that are similar but ground differently. **The freeze** writes one record of what `v1` is, so every later run can
check it is using the same data. They serve **C1** and **C3**.

## 2. Boundaries

- The gate **refuses to print a snapshot digest** unless every criterion passes, so "frozen" cannot happen by accident.
- The freeze record holds **digests, counts and statistics only**: no file name, ASIN, `qa_id` or absolute path,
  because 152 corpus files carry an ASIN in their name and this repository is public.

## 3. `corpus_gate.py`

`make gate-corpus VERSION=v1 WORKLOAD=data/workload-v1.json`. Check memory pressure first: stage 2 embeds.

**The five criteria:**

| | Criterion | On failure |
| :-- | :--- | :--- |
| **G1** | at least about 50 pairs with high similarity and low evidence overlap | fix the corpus, not the rule |
| **G2** | at least one `B-within` trap (same product, different evidence) | rebuild: a cross-product-only corpus is beaten by a cache key |
| **G3** | zero Tier-1 collisions in the workload | change the question text |
| **G4** | every `doc_id` starts with `policy-` or `product-` | re-name before ingestion |
| **G5** | no policy document names a condition it does not declare | split the conditions into separate documents |

**Two stages**, because G1 and G2 need retrieval:
- **Stage 1, structural** (`--structural-only` runs it alone): G4, G3, G5, and two workload checks
  (`check_workload_shape`: one stratum, split and cluster per record, no cluster across the splits;
  `check_split_files`: the split files are re-derived from the whole file and hashed with it). It reads files only.
  **A stage-1 failure stops the run before anything is embedded.**
- **Stage 2, retrieval** (needs `make ingest`): G1 and G2, with retrieval **scoped by each question's `product_id`**,
  as a run's is. The unscoped result is reported beside it, never gated on.

**The gate's overlap is not the rule's.** The rule's containment is asymmetric and defined between a question and a
cached entry. The gate compares two questions, so it uses symmetric Jaccard over the two top-5 sets. It is a corpus
property, never the rule's operating value.

**G5 here is a lexical scan** over the declared condition axes (`CONDITION_AXES`). It is a floor; the author's read of
every policy document is the other half.

**`K` and the capacity** are printed per run file: `capacity = round(0.25 × K)`, where `K` is the distinct-question
count of the file a run draws from (`CAPACITY_RATIO = 0.25`).

**The one exception (ADR-014).** `--accept-failed G1` lets a run where **only G1** failed, and no flag was raised, print
its digest as **"FREEZE WITH A RECORDED FAILURE"**. Only G1, only for `v1`, and only when the snapshot digest equals
the pinned `ACCEPTED_SNAPSHOT_DIGEST`. `passed` stays false.

**Exit codes:** 0 every criterion passed · 3 freezable with a recorded failure (not a pass) · 1 anything else.

The report also records the git state, package versions, the memory pressure, and digests of the chunk texts and
vectors, and it checks the index against the files on disk (`index_check`).

## 4. `freeze_corpus.py`

| Command | Does |
| :--- | :--- |
| `make corpus-assemble` | builds `data/v1/` from the selection drafts and the policy documents, byte for byte, into a clean folder; touches nothing else |
| `make corpus-index-check` | is the index in Redis the corpus on disk? A run's first step |
| `make corpus-freeze` | writes `data/v1-freeze.json` from **two** passing gate runs (or two that both record G1 as failed, listed as `known_failures`) |
| `make corpus-verify` | do the files, chunks, model and config still match the record? |

**`freeze` runs once.** A different freeze is a different `dataset_version` and a different file. `assemble` is not a
restore path. Exit codes: 0 done · 1 a check failed · 2 refused, nothing written.

## 5. Tests that pin it

`test_corpus_gate.py`, `test_corpus_gate_freeze.py` and `test_freeze_corpus.py` in `experiments/tests/`: each
criterion, the two stages, the G1 exception and its pinned digest, the record's forbidden content (no names, ASINs or
paths), and the two-run comparison.

## 6. Silent failures to watch

- **Reading the gate's Jaccard as the rule's overlap** mixes a corpus property with an operating value.
- **A capacity from the whole workload file** instead of the run file would make the cache too large for the run.
- **`v1` failed G1** (21 trap pairs against about 50). This is recorded, not hidden: it limits the power to show C1
  on same-product traps (ADR-014).

## 7. Commit

`29b24a6`.
