# `contracts/` — files that two languages must agree on

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `contracts/rag/v1/rag.proto` (82 lines) and
`contracts/normalize/cases.json` (27 cases). The written contract they serve is `docs/contracts/interfaces.md`.

## 1. Purpose

Go and Python are two services. Where both must do **exactly the same thing**, the agreement lives here, in one file
that both read, instead of in two pieces of code that happen to match. It serves **C3** (and the seam every claim
passes through).

## 2. Boundaries

- **Generated code is never edited by hand.** `make proto` regenerates the Go (`gateway/internal/ragpb/`) and Python
  (`rag/src/rag/pb/`) stubs from the `.proto`.
- Changing an existing `out` in `cases.json` changes the frozen normalisation and **needs a numbered decision**. Adding
  a case is cheap and is the right answer to any normalisation question.

## 3. `rag/v1/rag.proto` — the gRPC schema (`interfaces.md` §B)

**`RagService`** has two calls:
- **`Retrieve(RetrieveRequest) → RetrieveResponse`**, retrieval without generation, for the Tier-2 cascade.
- **`Answer(AnswerRequest) → stream AnswerChunk`**, the miss path. The stream sends **one** terminal chunk in scope
  (per-token streaming was dropped).

| Message | Fields |
| :--- | :--- |
| `RetrieveRequest` | `query`, `top_k` (0 = the server's `TOP_K`), `product_id` (optional; scopes the search) |
| `RetrieveResponse` | `chunk_ids` (ranked, stable IDs, §C), `scores` (aligned), `dataset_epoch` (read before the texts, §E), `texts` (aligned with `chunk_ids`, or empty from an old server) |
| `AnswerRequest` | `query`, `top_k`, `stream` (false), `retrieved_chunk_ids` (ground on exactly these, no second retrieval), `product_id` |
| `AnswerChunk` | `text`, `done` (true on the terminal chunk), `source_chunk_ids` (provenance for C1 and C2), `model_used` (constant), `dataset_epoch` (gates the write-back) |

Fields were added over time (`texts` in §B v0.9, `retrieved_chunk_ids` in v0.7, `product_id` in v0.8) with new
numbers, never by changing old ones, so an older peer still parses a newer message. Who reads each field and why is in
[`ragclient.md`](gateway/ragclient.md) and [`rag/serving.md`](rag/serving.md).

## 4. `normalize/cases.json` — Tier-1 normalisation, pinned

**Why it exists.** Tier 1 is a bare hash of the normalised question and runs no reuse rule. Go normalises on the hit
path (`cache.Normalize`); Python mirrors it for gate **G3**, which fails a workload where two questions with different
grounding normalise to the same text. If Python were **looser** than Go, G3 would miss a real collision; if **tighter**,
it would reject a corpus Tier 1 handles. Either failure is silent, so **both sides test against this file**, not
against their own expectations.

**The 27 cases** cover: lower-casing; collapsing spaces, tabs, new lines and the non-breaking space; trimming; stripping
punctuation and symbols (apostrophes, slash, em dash, underscore, percent, plus, curly quotes); punctuation only, or
white space only, becoming empty; **the documented loss** of the hyphen ("Model A-1" and "Model A1" become the same
text); **no stemming**, **no stopword removal**; digits survive; **accents are kept**.

**Read by:** `gateway/internal/cache/normalize_contract_test.go` (Go) and `experiments/tests/test_corpus_gate.py`
(Python).

## 5. Tests that pin it

`TestNormalizeMatchesCrossLanguageContract` (Go) and the corpus-gate test (Python) both run every case. The `.proto` is
pinned by the generated stubs and by the live `make seam-check`.

## 6. Silent failures to watch

- **A hand-edited stub** would drift from the `.proto` with no error until a field is missing at run time.
- **Reusing a field number** for a different meaning would make an old and a new peer read garbage.
- **A Go or Python normaliser change** without a matching case would let G3 and Tier 1 disagree.

## 7. Commit

`29b24a6`.
