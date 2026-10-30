# `experiments/scripts/` — building the corpus and the workload

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `build_pqa.py` (1,067 lines), `select_pqa.py` (1,207),
`answerability_check.py` (237), `check_policies.py` (424), `build_workload.py` (2,693). The provenance, licences,
schemas and counts are in `docs/data-card.md`; the decisions are ADR-002 and ADR-011 to ADR-015.

## 1. Purpose

These five scripts take raw Amazon-PQA files and our own policy texts to the **frozen `v1` corpus** (152 products,
12 policies) and the **frozen workload** (1,274 questions). Every rule was written down before the data was looked
at, and every script **stops** rather than guess. They serve **C1** and **C3**: the reuse rule can only be tested
on a corpus that contains the trap it targets.

## 2. Boundaries and shared rules

- **Amazon-PQA text is never published.** Its redistribution is not granted. Every PQA-derived file is gitignored
  (`data/raw/`, `data/v1-draft/`, `data/v1/`); the tracked files hold **hashes and counts only**, and the tests
  check them against an allow-list.
- **A stop writes nothing under a final name** and exits with code 2.
- They run in the order below. None of them loads the LLM.

## 3. The scripts, in pipeline order

### `build_pqa.py` — item 3.1: check and parse the raw PQA files

`make pqa-fetch` downloads (or resumes) the six pinned PQA leaf files, about 1.9 GB, into `data/raw/pqa/`. Then
`make pqa-build` checks and parses them, and `make pqa-verify` re-hashes them offline.

**Why it stops so often.** The dataset's readme names fields the data does not use; a builder written from it
returns empty records and raises no error. So there are four stops: the file's **size and SHA-256** (stop 0); **at
least one record** parsed (stop 1); **every real field non-empty at least once, and no unknown key** (stop 2); and
the **counts** of records, products, question types and aggregates equal the numbers pinned by an earlier,
separate probe, plus a check that every written line equals what the parser built (stops 3a–3c).

**Writes:** one gitignored interim file per leaf (`data/v1-draft/pqa/`), and the tracked hash manifest
`data/pqa-manifest.json`.

### `select_pqa.py` — item 3.2: draw 152 products

`make pqa-select`, `make pqa-select-verify`, `make pqa-audit-sheet`, `make pqa-audit-score`.

It reads the interim files only through `build_pqa.iter_interim` and applies **one pre-registered rule**:
- each question is **dropped** (price, stock, carrier), tagged **`policy`** (returns and warranty, answered by our
  policy documents), or tagged **`spec`**, and a spec question is **answerable** by rule R2: at least half of its
  content words appear in the product's own record, after the words common to that leaf's titles are removed. R1,
  the same without that removal, is reported but never selects;
- a product is **eligible** if it passes a fixed funnel (`STEPS`);
- inside each leaf, eligible products are ranked by `sha256(seed:asin)` and the first `QUOTA[leaf]` are taken:
  **38 per department**, 152 in all. A short leaf stops the run; only the author may apply the fallback.

**Writes:** `data/v1-draft/products/product-{department}-{asin}.json` (the shape `rag.ingest` reads), the question
pool, the leaves' common title words (all gitignored), and the tracked `data/pqa-selection.json` (counts and digests).
The audit commands produce a blind sheet for the author and score it with a Wilson interval.

### `answerability_check.py` — item 3.2: check rule R2 against human labels

`make epqa-fetch` (three ePQA CSVs, 46 MB, CDLA-Sharing-1.0), then `make pqa-answerability`. It matches PQA questions
to ePQA's human labels by `(asin, lower-cased question)` and reports how often R2 and R1 agree with them. **Descriptive
only**: no number from it decides anything. Output: counts only, into the task trail.

### `check_policies.py` — item 3.3: check the 12 policy documents

`make policy-check` (`POLICY_DIR=` to point elsewhere); offline, so it is the loop to run while writing. It checks
the rules fixed before the first document was written:
- **schema**: seven fields; the `doc_id` derived from department, policy kind and condition; every department has a
  return and a warranty family; ASCII only;
- **terms and numbers**: the only numbers in a text are its declared `terms`, written with the unit attached (what the
  support gate's numeric arm reads); siblings' terms differ;
- **chunks**: through the real ingest path, at least 3 chunks, chunk 0 holds the main term, no two chunks identical
  (identical text embeds identically, and the index's tie order would then pick the namespace);
- **G5**: `corpus_gate.check_g5`, the one implementation of the condition scan.

`make policy-sources` reports brand and risky-title counts of the selection (counts only).

### `build_workload.py` — item 3.4: the 1,274 questions

**The model layer** (`data/v1-draft/workload/model-layer.jsonl`, gitignored) is written by Claude, task by task, under
`docs/work/2026-10-21-workload-generator/rules.md`. This script does the mechanical half:
- `make workload-status`: open tasks per round (counts only);
- `make workload-sheets ROUND=… OUT=<dir>`: sheets for the next tasks, written **outside the repository**;
- `make workload-import IN=…`: checks a rows file and appends only valid rows. **A failed row is re-done by the
  writer, never repaired by a script**;
- three rounds in order: `label` (names, answerability labels, policy assignments, natural pairs), `write`
  (rewrites, paraphrases, lookalike traps, stratum-D questions), `check` (each written question labelled again
  without its seed, and the name-swap traps);
- `make workload-labels`, `workload-author-sheet` and `workload-author-score`: reports and the author's 30-row read;
- `make workload-embed` (loads `nomic-embed-text`), then `make workload-build` writes `data/workload-v1*.json` (the
  whole file and the two split files) and `data/workload-manifest.json`; `make workload-verify` re-checks them.

**`sheets` and `import` refuse to run while `rules.md` is uncommitted or changed**: the rules came before the data.

## 4. Callers and callees

- Run by hand through `make`, in the order above; the result feeds [`gate-and-freeze.md`](gate-and-freeze.md).
- `check_policies.py` imports `corpus_gate.check_g5` and `rag.ingest`; `select_pqa.py` and `build_workload.py` read
  earlier stages only through their `iter_*` functions.

## 5. Tests that pin them

`experiments/tests/`: `test_build_pqa.py`, `test_select_pqa.py`, `test_answerability_check.py`,
`test_check_policies.py`, `test_build_workload.py`. They pin each field's slot with hand-written values (a parser
that reads a field into the wrong slot would pass the count checks), the selection rule, the policy rules, and the
import checks. They run in `make test`.

## 6. Silent failures to watch

- **A wrong field name** returns empty records with no error; that is why stop 2 exists.
- **PQA text in a tracked file** would break the licence. Keep every text-bearing output gitignored.
- **A row repaired by a script** would bypass the pre-registered rules; re-do it instead.
- **These scripts describe `v1`.** The corpus is frozen (23 Oct 2026); re-running them makes a new dataset version,
  not a fix.

## 7. Commit

`29b24a6`.
