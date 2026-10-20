# Spec — policy-documents (super-plan item 3.3)

**Scope:** L · **Opened:** 2026-10-20 · **Branch:** main, as for 3.1 and 3.2, unless the author says otherwise

**Why L.** The policy documents are half of the frozen `v1` corpus, and every policy result reads
them. How the opposing conditions are written decides what RQ2a can measure: `data-card.md` §3
already says the measured residual is "partly a property of how carefully the author split
conditions". This item also fixes the policy-document schema that 3.4 (the workload) and 3.5 (G5)
read. A silent mistake here costs the study, not an afternoon.

## The change in one sentence

Write about 13 store policy documents (returns and warranty, per department, with each opposing
condition in its own document) by a set of writing rules fixed before any text is written, plus a
check, `make policy-check`, that proves every document makes ≥ 3 chunks with the real splitter and
that no document names two opposing conditions.

## Phase and item

- **Phase 3**, item **3.3**. Discharges C1 and C2. Rests on ADR-002 and `data-card.md` §2 and §7.
- **Done when** (`super-plan.md`): *"Every policy document yields ≥3 chunks and **no two opposing
  conditions share a `doc_id`**. Note this raises the count above 8: one category's return policy
  split into *opened* / *unopened* is two documents."*
- Unblocks **3.4** (with 3.2, done) and **3.5**.
- `requirements.md` is still empty, so there are no FR / NFR / RR ids to cite.

**Carry-forwards this item discharges:**

1. ADR-002 and `data-card.md` §2: **a primary source is required for every warranty term before it
   is written**; the sources so far are secondary. ADR-002 also says the written terms "may need to
   differ more than the published ones do". Decide (open question 2).
2. `data-card.md` §2 requirements 1–3: every policy record carries a non-empty `category` equal to a
   department (the join key); warranty differs per department, not only returns; every document
   makes ≥ 3 chunks.
3. `data-card.md` §2: the count "~13" is **fixed at this item**; `TODO(W8): list of policy doc_ids
   and titles`.
4. `data-card.md` Schemas: `TODO(W8): finalize the policy document` (the QA pair stays 3.4's).
5. `data-card.md` §7: `TODO(W8): opposing-condition pairs sharing a doc_id, before and after
   splitting (G5)`. This item supplies both numbers.
6. 3.2 review L3: the question pool has **no shipping tag** and only 127 policy questions (92
   warranty, 35 return). This informs open question 1.
7. ADR-002: `laptops` and `electronics` share 30-day returns **by design** (it measures what the
   namespace costs in refused safe reuse). Keep it.

## The document set (proposed — `design.md` §2 has the full table)

13 documents: 4 departments × (returns, warranty) = 8, and 5 of them split into two by a condition
that changes the answer. No shipping document.

| Kind | phones | laptops | electronics | furniture |
| :--- | :--- | :--- | :--- | :--- |
| returns | opened / unopened | new / renewed | one document | opened / unopened |
| warranty | domestic / international | domestic / international | one document | one document |

## Output

- **13 policy records** in a new **tracked** folder `data/policies-v1/`, one file each,
  `{doc_id}.json`, in the shape `rag.ingest.load_records` reads today plus three fields that G5,
  the checker and 3.4 read and ingest ignores (`policy_kind`, `condition`, `terms`; `design.md` §3). They are author-owned and releasable, so they
  belong in git. 3.6 copies them into `data/v1/` with the products.
- **A check, `make policy-check`** (`experiments/scripts/check_policies.py`): schema, ≥ 3 chunks
  through the real `record_to_document` + `SentenceSplitter` at 256 / 40, the condition scan, no
  identical chunks. No Redis, no Ollama.
- **The sources**, `evidence/sources.md` in this trail: URL, fetch date and the one line that states
  each term. Never the page's wording beyond that line.
- **`data-card.md`** §2 (the doc_id list, the terms, the sources, the writing rules), Schemas (the
  policy document), §7 (the G5 before / after counts). **`architecture.md`** (the new folder, the
  new script). **ADR-012** (data), if the author agrees (open question 8).

## Acceptance — each is a command, a test or a recorded read

| # | Check | How |
| :-: | :--- | :--- |
| P1 | Every document makes ≥ 3 chunks through `rag.ingest.record_to_document` and `SentenceSplitter(256, 40)`; a 2-chunk fixture fails and names the document | `make policy-check` + unit test |
| P2 | No document names a condition value it did not declare (one with no condition names none); a fixture that names its sibling's value fails, and one that names both values fails **and names both** (`design.md` §6, review H1) | `make policy-check` + unit test |
| P3 | Schema: `doc_id` equals the file name and begins with `policy-`; `category` is one of the four departments; `policy_kind` is `return` or `warranty`; `condition` is null or an axis and value from the frozen list; no two documents share (`policy_kind`, `category`, `condition`); a split family has both values. `rag.ingest.load_records` accepts the folder | `make policy-check` + unit tests |
| P4 | No two chunks in the policy corpus have identical text | `make policy-check` + unit test |
| P5 | Every term (each window, fee and warranty length) has a primary source in `evidence/sources.md`, fetched before the document that uses it was written | read + git log |
| P6 | The writing rules and the condition list are committed **before** the first document | git log |
| P7 | No retrieval or embedding run on these documents is part of this item; the first one is G1 / G2 at 3.6 | read |
| P8 | The author has read every document and approved it; recorded in `approvals.md` | read |
| P9 | `data-card.md` §2, Schemas and §7 (G5 before / after) are filled; `architecture.md` lists the folder and the script | read |
| P10 | `make test` and `ruff check experiments` pass; `git status --porcelain data/` is the same before and after `make test` | commands |
| P11 | `record_to_document(policy).metadata` has exactly `doc_id`, `kind`, `category`, `title`: the new fields never reach chunk metadata (review L7) | unit test |
| P12 | Every number in a document is one of its `terms`, written as in `terms`; at most one duration and one amount; the two siblings' `terms` differ (review H2, M3) | `make policy-check` + unit tests |
| P13 | Chunk 0 of every document holds its main term (review L3) | `make policy-check` + unit test |

## Out of scope

- The workload, strata, query rewriting, policy-question wording (3.4). The freeze, `K`, the
  capacity and building `data/v1/` (3.6).
- Any change to `rag/` (ingest, chunking, `DATASET_VERSION`), `interfaces.md`, the `.proto` or
  `reuse/`.
- Any retrieval, embedding or LLM run on the new documents.
- The Phase 4 edit set (the controlled policy edits of RQ3).
- Deleting or changing anything in `data/dev-v0/`.
- G5 inside `corpus_gate.py` — **unless** the author picks that in open question 7.

## Open questions for the author

Each has a proposal. `design.md` §9 gives the reasons.

1. **Shipping.** Drop it (proposed: no shipping question exists in the pool, and a global shipping
   document adds no condition), keep one global document with `category: null`, or one per
   department?
2. **Warranty terms.** Take each term as it is from a primary source (proposed: phones, laptops and
   electronics will probably all be about 1 year, and that sameness then measures the namespace cost,
   as laptops and electronics returns already do), or write terms that differ by department and say
   in the data card that they are invented?
3. **Furniture returns.** IKEA's pair, opened 180 / unopened 365 days (proposed: one source covers
   both sides), or Target's 90 days for one side?
4. **Phones, opened.** Best Buy, 14 days and a $45 restocking fee (proposed: one source for the
   window and the fee), or Target's "up to $35"?
5. **Where the files live.** A tracked `data/policies-v1/` (proposed), or gitignored
   `data/v1-draft/policies/`? Note: this session's permissions deny Read and Bash on `data/`, so
   writing the documents needs that access.
6. **Who writes the text.** Claude drafts each document by the rules, you read and approve each one,
   and `data-card.md` says so (proposed), or you write them?
7. **G5.** Write the condition scan **once**, as G5 in `corpus_gate.py`, and have `make
   policy-check` call it, so 3.5 closes with this item (proposed: one implementation, never a
   mirror, which is the G3 lesson), or keep a scan in the checker now and move it at 3.5?
8. **ADR-012** (data): record the set, the schema, the sources and the writing rules, written at the
   end with the real terms (proposed, as 3.2 did with ADR-011), or no ADR?
9. **How the two sibling documents differ** (added after the design review, H3). As **minimal
   pairs**: the same text in every section, except that each section names the document's own
   condition once and the term sentences differ (proposed: which sibling ranks first then turns on
   the condition word, which is what RQ2a asks about), or only the opening section names the
   condition and the rest is worded freely (reads more like a real page, but drafting then moves
   the result)?
10. **The laptops new / renewed split** (added after the review, M5). Keep it (proposed: real stores
    split it, and it adds a lookalike pair and a namespace for G1), recording that it feeds no
    natural same-product pair, since a listing is either new or renewed; or drop it (12 documents)?
