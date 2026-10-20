# Spec — pqa-thick-tail-selection (super-plan item 3.2)

**Scope:** L · **Opened:** 2026-10-19 · **Branch:** main, as for 3.1, unless the author says otherwise

**Why L.** This item decides which products and which questions the frozen corpus has. Every later
measurement reads its output, and `K` (so the cache capacity) is drawn from the question pool it
writes. A silent mistake here costs the study, not an afternoon.

## The change in one sentence

Add a selection script that reads the 3.1 interim files through `iter_interim`, applies one recorded
selection rule (the filters measured on 2026-10-03 plus a new answerability filter), draws about 150
products from the thick tail of the four departments, and writes draft product records, a question
pool and a tracked selection manifest; the rule and the realised questions-per-product distribution
go into `data-card.md`.

## Phase and item

- **Phase 3**, item **3.2**. Discharges C1. Rests on ADR-002 and `data-card.md` §1 and §3.
- **Done when** (`super-plan.md`): *"The selection rule is recorded in `data-card.md`, and the
  realised questions-per-product distribution is reported with it."*
- Unblocks **3.4** (the workload generator), together with 3.3.
- `requirements.md` is still empty, so there are no FR / NFR / RR ids to cite.

**Carry-forwards this item discharges:**

1. 3.1, open question 4, option A (author, 2026-10-15): write drafts to a fresh
   `data/v1-draft/products/` and **refuse to run while `data/v1-draft/product-*.json` exist**.
2. 3.1 review L3: read the interim **only** through `iter_interim`, and record the sha256 of the
   `data/pqa-manifest.json` it consumed.
3. 3.1 spec: the interim's `leaf` is metadata. It must not become `category` and must not reach
   text that is embedded.
4. 3.1 live run: **78 asins** (0.11 %) have product fields that differ between records. Decide.
5. 2026-10-03 review, finding 5: record the **filtered** re-ask rate beside the unfiltered one.
6. ADR-002 consequence and `data-card.md` §1: the selection rule must add an **answerability
   filter**, checked against the 194 PQA questions that carry ePQA's human labels.
7. `data-card.md` §1 `TODO(W8)`s: the final filter rules and product count; the answerability
   criterion and its agreement with those labels; exclude the warranty-term products or scope the
   warranty documents around them.

## The selection rule (proposed — `design.md` §2 has the exact definitions)

Every filter except the answerability filter was measured by the 2026-10-03 probe and is reused
as written there (same regexes, same tokenizer, same near-duplicate band).

- **Questions.** Drop price and stock questions and carrier questions (they must never enter the
  workload). Tag warranty and return questions as **policy** questions: they are answered by the
  authored policy documents (3.3), not by the product record. Tag every other question
  **answerable** or **not answerable** from the product's own record.
- **Products.** Keep a product only if it has ≥ 3 bullets, states no warranty term in its own
  prose, has the same product fields in every record (this removes the 78), has 5–50 questions
  after the drops, has ≥ 5 answerable spec questions, and has ≥ 1 near-duplicate pair among them.
- **The draw.** 38 products per department, 152 in all. A department with two leaves takes 19 from
  each. Inside a leaf the products are ranked by `sha256(seed:asin)` and the first ones are taken.
  If a leaf has fewer eligible products than its quota, the script **stops**: it never relaxes a
  filter by itself.

## Output

- **Product records** (gitignored): `data/v1-draft/products/product-{department}-{asin}.json`, in the
  shape `rag.ingest.load_records` reads today (`doc_id`, `title`, `category`, `specs`). No `leaf`.
- **Question pool** (gitignored): `data/v1-draft/question-pool.jsonl`. The kept questions of the
  selected products, each with its tags. 3.4 reads it.
- **Selection manifest** (tracked, hashes and counts only, no PQA text and no asin):
  `data/pqa-selection.json`. It names the 3.1 manifest it consumed, the rule's parameters and seed,
  the filter funnel per leaf, and the realised questions-per-product distribution.
- **`data-card.md` §1 and §3:** the rule, the product count, the distribution, the answerability
  agreement. This is the Done-when.
- **A one-field change to the 3.1 builder** (only if the 78 are excluded, open question 3): the
  interim keeps only the *count* of products whose records disagree (`build_pqa.py:241`), not which
  ones. Each interim product line gains `fields_conflict`, and `MANIFEST_VERSION` goes to 2
  (`design.md` §5). 3.1 handed the interim schema to 3.2 for this kind of change.
- **An answerability check**, `make pqa-answerability EPQA=<dir>`: the rule against the ePQA labels,
  counts only, into this trail (`design.md` §3).

## Acceptance — each is a command or a test

| # | Check | How |
| :-: | :--- | :--- |
| A1 | With a `data/v1-draft/product-*.json` present, the script exits 2 and writes nothing | unit test |
| A2 | It reads the interim only through `iter_interim`; a changed interim file stops it before anything is written | unit test |
| A3 | Two runs in subprocesses with `PYTHONHASHSEED=0` and `=1` give byte-identical outputs and manifest | unit test |
| A4 | Every record: `doc_id` begins with `product-` and equals its file name; `category` is one of the four departments; no `leaf` key; the leaf name appears nowhere in the record. `rag.ingest.load_records` accepts the output directory | unit test |
| A5 | Every string value in the selection manifest is on an allow-list (digests, field and leaf names, fixed labels). No asin, no question text | unit test |
| A6 | Each filter and tag has hand-made fixtures on both sides of its edge (near-duplicate band at 0.45 and 0.99, exact repeats, 3 vs 2 bullets, 5 vs 4 answerable, 50 vs 51 questions, a warranty term, records that disagree) | unit tests |
| A7 | The draw takes exactly the quota per leaf and department; a pool smaller than its quota exits 2 and names the leaf | unit test |
| A8 | **Live run** on the real interim: the funnel and the distribution print; two runs print the same manifest sha256; the 3.1 manifest sha256 it records equals `make pqa-verify`'s | by hand; `make verify` never runs it |
| A9 | The answerability rule's agreement with the ePQA labels is recorded with Wilson intervals. **The rule is committed before the agreement is computed**, and the commit order shows it | command + git log |
| A10 | `data-card.md` holds the rule, the count and the distribution (Done-when) | read |
| A11 | `make test` and `ruff check experiments` pass; `git status --porcelain data/` is the same before and after `make test` | commands |
| A12 | On the live run, the probe's own pool rule, counted on the same pass, gives ADR-002's six pools (1,811 / 1,312 / 302 / 399 / 796 / 339); a difference exits 2 before the draw (`design.md` §2.6) | live run + unit test |
| A13 | The answerability join finds 194 PQA lines (143 / 5 / 21 / 19 / 2 / 4 in `LEAVES` order), or exits 2 | live run + unit test |
| A14 | The blind audit of 100 selected questions is marked by the author and scored: R2's precision and recall with Wilson intervals (`design.md` §3.2) | by hand + command |
| A15 | 3.4 can read the outputs only through `iter_selection`, which refuses a changed product file or pool | unit test |

## Out of scope

- Policy documents (3.3). The workload: strata, Zipf, splits, paraphrases, and rewriting
  questions so they name their product (3.4). G5 (3.5). The freeze, `K` and the capacity (3.6).
- Any change to `rag/` (ingest, chunking, `DATASET_VERSION`), `corpus_gate.py`, `interfaces.md`,
  the `.proto` or ADR-002's department map.
- Deleting any old file under `data/`.
- An LLM in the selection path, unless the author picks that option for the answerability filter.

## Open questions for the author

Each has a proposal. `design.md` §6 gives the reasons.

1. **Answerability: how is it decided?** Proposed (changed after the design review): a **lexical
   rule, R2**, that first removes the leaf's common title words, so "How tall is the chair?" does
   not pass on "chair" alone; the plain rule R1 is reported beside it. Both are fixed before any data
   is seen, then checked two ways: against the 194 ePQA labels, and by **a blind audit of 100
   questions from the selected products, marked by you (about one hour)**. Other options: an LLM
   label (model and prompt recorded; never Qwen or the Phase 5 judge), or hand curation of every
   selected question.
2. **The draw inside a leaf:** a seeded hash rank (proposed), or the thickest products first?
3. **The 78 asins whose records disagree:** exclude (proposed), or keep the first record?
4. **Products that state a warranty term:** exclude (proposed; this is the probe's pool), or keep
   them and scope the warranty documents around them? The review adds: test the **title** too,
   since it is embedded (proposed).
5. **Two-leaf departments:** 19 + 19 (proposed), or split in proportion to the pools?
6. **`doc_id`:** `product-{department}-{asin, lower case}` (proposed, as in the 2026-10-03 example),
   or an ordinal such as `product-laptops-07`?
7. **ePQA:** may the script's helper download the ePQA CSVs (46 MB, CDLA-Sharing-1.0) from GitHub
   into a gitignored folder? The 2026-10-03 probe read them from `scripts/epqa/` in its trail,
   and that folder is not there now. Whether a copy exists under `data/` is unchecked (Bash is
   denied on `data/` paths in this session).
8. **The near-duplicate pair:** must it be among **answerable** questions (proposed: an A or C pair
   of unanswerable questions is safe by construction), or among all kept questions, as in ADR-002's
   pools? With the proposal, ADR-002's pool sizes stay true only of the probe's rule, which A12 checks.

9. **Spec questions the record cannot answer** (review H2): keep them as **a separate stratum,
   reported apart and never in the headline** (proposed), or drop them? The headline would cover
   answerable spec questions and policy questions. 3.4 inherits this.
10. **If a leaf cannot fill its quota** (review L1), the fallback, fixed now: first give the shortfall
    to the sibling leaf in the same department; then let the pair step use all kept questions.
    Beyond that, only your post-hoc decision. The seed and the answerability rule never change.
11. **ADR-011** (data), recommended by the impact analysis: it records the frozen rule, since
    ADR-002 says its filters are fixed at this item. Written at the end, with the live numbers.
