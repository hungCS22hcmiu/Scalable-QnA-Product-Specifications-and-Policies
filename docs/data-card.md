# Data Card

**Status:** v0.4 — sources chosen (ADR-002), corpus **not yet frozen** · scaffold now, **fill and freeze at timeline W8** · **Created:** 2026-07-23 · **Revised:** 2026-10-04
**Companion to:** `Final_Proposal.md` (§9.3 datasets), `contracts/interfaces.md` (§C chunk-IDs, §D Tier-1 key), `decisions.md` (inherited state and every decision from 2026-09-22 on).

**Purpose.** Document provenance, licensing, schema, and versioning for every data artifact the study consumes or produces, so results are reproducible and the open-source deliverable (proposal §13) is legally clean. Items marked **`TODO(W8)`** are filled when the corpus is frozen.

**Freeze policy.** At **W8** the experimental snapshot `v1` is frozen and hashed. `dataset_version`, `snapshot_sha256`, and **`K` (distinct-query count, which sets cache capacity)** are recorded here and in every run manifest (the evaluation Re-chunking or corpus edits bump the version. **No experiment runs against an unfrozen corpus**, and none against one that has not passed all five gate criteria in §7 (G1–G5).

> ⚠️ **Two corpora — do not conflate them.**
>
> | Corpus | Built | Size | Status |
> | :--- | :--- | :--- | :--- |
> | **`dev-v0`** | W5 | ~40 products, 4 policy docs, no category balance | **Throwaway.** Exists only to make the pipeline run during the 3-week runway. Not hashed, not versioned, **not citable in any result.** Discarded after W8 |
> | **`v1`** | W8 | ~150 products, **≥3 categories**, per-category policies | The **frozen experimental corpus**. Hashed, versioned, and gated by §7 |
>
> Both use the **same frozen embedding model and chunking config** (the frozen embedding model/the frozen chunking, frozen W5), so `v1` is a content expansion rather than a re-chunk. Any number in the pre-thesis report that comes from `dev-v0` must be labelled preliminary and non-authoritative.

> **Sizes cut by the scope reduction (2026-08-09).** Product subset 500–2,000 → **~150**; policy corpus 5–10 → **8** documents (raised to **~13** by ADR-002, because opposing conditions live in separate documents); the reuse-safety training set is replaced by a smaller **judged evaluation set** (no training, so no splits). A small clean corpus beats a large messy one, and W8 is a hard timebox.

| Artifact | Source | License posture | Frozen |
| :--- | :--- | :--- | :--- |
| Product catalog (~150) | **Amazon-PQA** — six leaf files → four departments (ADR-002) | **academic use granted; redistribution NOT granted** → build script + hash manifest | `TODO(W8)` |
| Query workload | **Amazon-PQA** — same records as the catalog | **academic use granted; redistribution NOT granted** → build script + hash manifest | `TODO(W8)` |
| Policy corpus (~13 docs) | self-authored | author-owned → releasable | `TODO(W8)` |
| Paraphrase stress set | mined + machine-generated | derivative — see below | `TODO(W8)` |
| Update set (~20 edits) | self-authored edits | author-owned | `TODO(W8)` |
| Judged evaluation set | auto-generated + ~100 human-verified | author-owned | thesis W14 |
| Run outputs: `experiments/results/*/raw/` (evaluation log, served answer text) | the gateway, over the artifacts above | **derivative of Amazon-PQA** (verbatim question text; LLM answers grounded on PQA chunks) → **gitignored, never published**; `manifest.yaml` may be tracked (ADR-005) | per run |

---

## 1. Product catalog (Amazon-PQA)

> **Changed 2026-09-21 — the source is now Amazon-PQA.** The source was `Amazon-Reviews-2023` metadata joined to `AmazonQA`. It is now **Amazon-PQA**, where each record carries the question *and* the product content, so no join is performed and `asin`-against-`parent_asin` stops being a risk to measure. §3 changes with it.

- **Source:** **Amazon-PQA**, AWS Open Data, `s3://amazon-pqa` — one JSON-lines file per category, served over **plain HTTPS with no credentials and no AWS CLI** (`https://amazon-pqa.s3.amazonaws.com/amazon_pqa_<category>.json`). Download only the category files listed below, never the full archive (2.27 GB compressed; ~17 GB of JSON across all 100 files). **Chosen 2026-10-04 (ADR-002); downloaded 2026-10-03; kept gitignored in `data/raw/pqa/`:**

  | File | Bytes | sha256 |
  | :--- | ---: | :--- |
  | `amazon_pqa_unlocked_cell_phones.json` | 821,444,488 | `007178b847b2fb2b3bbdee7a79982dfcf7c51818f7cc909c5b4b5381c249424c` |
  | `amazon_pqa_traditional_laptops.json` | 403,702,059 | `86452e67a51d029d8ff7419b2f4fe3037c2a1fcf27a2de199d859e35bf098b5f` |
  | `amazon_pqa_led_&_lcd_tvs.json` | 178,273,635 | `bd8e9530c3ae2b678fd773c612e612770ce7b601b3b340d38f468767861622f1` |
  | `amazon_pqa_over-ear_headphones.json` | 278,531,682 | `b784c7e144257dbc1eb77e76ab46aaaba786d73280b533701a2314860344b320` |
  | `amazon_pqa_chairs.json` | 138,252,584 | `b015bea4871be949d5ca332a605fb0b1f1ebba5d89a903e277a857b1567b73c0` |
  | `amazon_pqa_home_office_desks.json` | 95,549,762 | `2d89b15fc9c592539a4af9f4806517896e04594c7333ffdd68e5418a34fcba74` |

  Together: **1,212,029 questions over 71,794 products**. ⚠️ **Verify by sha256 and parse rate, not by ETag.** The S3 ETags are multipart with an unpublished part size, so they cannot be recomputed. Single connections can throttle to ~15 KB/s, so the builder downloads with resume and byte ranges. Four records in `unlocked_cell_phones` carry an empty `question_text` in the source: skip them and still assert a non-zero parse rate.
- **⚠️ License / redistribution — academic use granted, redistribution NOT granted.** Two sources conflict and this study takes the more restrictive, because the cost of being wrong falls on a public repository. The AWS Open Data Registry entry records `License: https://cdla.dev/permissive-1-0/`; the dataset's **own `readme.txt`** — which that same entry names as its `Documentation` — instead carries the ACM personal/classroom notice: *"Permission to make digital or hard copies … for personal or classroom use … provided that copies are not made or distributed for profit or commercial advantage … For all other uses, contact the owner/author(s)."* The string "CDLA" appears nowhere in it. **Therefore:** using PQA for this thesis is the granted case; publishing a derived corpus is not. `data/v1/` stays gitignored and ships as a **download-and-build script plus a hash manifest**, reconciled with the project LICENSE. **Required citation:** Rozen, Carmel, Mejer, Mirkis and Ziser, *"Answering Product-Questions by Utilizing Questions from Other Contextually Similar Products"*, NAACL-HLT 2021 — BibTeX in the dataset readme.
- **⚠️ The dataset's documentation does not match its data — write the builder against the bytes.** `readme.txt` describes `asin_id`, `bullet_points`, `is_yes-no_question`, `yes-no_answer`, `answer_text`. The records actually carry **`asin`**, **`bullet_point1` … `bullet_point5`**, **`question_type`** (`"yes-no"` | `"WH"`), **`answers`** (a list of `{answer_text}`) and **`answer_aggregated`**, alongside `question_id`, `question_text`, `brand_name`, `item_name`, `product_description`. A builder written against the documentation produces **empty records with no error**; the builder must assert a non-zero parse rate.
- **⚠️ PQA products chunk to roughly one chunk each, and that is fine — but it is not requirement 3.** Measured 2026-09-21: median product prose (five bullets plus description) is **504 characters**, ≈ 126 tokens at the frozen `chunk_size = 256`, with `product_description` frequently empty; only **1.6 %** of products would reach ≥ 3 chunks. The earlier argument that prose would chunk more readily than a spec table is **withdrawn**. `v1` corpus requirement 3 rests entirely on the **authored policy** half of §2. What PQA does fix is corpus *diversity*: `dev-v0`'s G1 = 0 came from 44 chunks in total, where one PQA category supplies over a thousand.
- **Subset criteria:** **~150 products across ≥ 3 categories** (proposal §9.3, timeline W8). Small on purpose — the corpus exists to exercise the cache, not to stress retrieval — but **not single-category**: see the sensitivity gate in §7. **Categories are four store departments** (ADR-002). PQA has no department-level file, so each department draws on one or two leaves, and the department is the `category` that product and policy records share (§2 requirement 1). `TODO(W8): final filter rules, final product count.`
- **⚠️ Select into the thick tail; do NOT sample uniformly.** Questions per product is heavily skewed *within* a category and varies ~4× *between* categories on the original shortlist — `inkjet_printers` median **8** (63.7 % of products with ≥ 5 questions), `chairs` median **2** (24.3 %, but 19,193 products, so 4,664 still clear it). A uniform draw from a thin category returns mostly single-question products, from which **no stratum A or C pair can be built at all**. Record the selection rule used.
- **⚠️ Category choice must satisfy two constraints at once.** §2's requirement 2 wants categories whose return *and* warranty windows genuinely differ; this section wants categories thick in questions per product. They are independent, and the shortlist in earlier planning was assembled against the first only. **Resolved 2026-10-04 (ADR-002)**, with the author's own requirement added as a third constraint, recognisable departments:

  | `category` | Leaf file(s) | What drove the choice | Pool* |
  | :--- | :--- | :--- | ---: |
  | `phones` | `unlocked_cell_phones` | Department required by the author. Preferred to `carrier_cell_phones` on every measure; 14-day window and an opened-vs-unopened fee (Target, Best Buy) | 1,811 |
  | `laptops` | `traditional_laptops` | Department required by the author. 30-day window; new vs renewed (Amazon 30 vs 90) | 1,312 |
  | `electronics` | `led_&_lcd_tvs` + `over-ear_headphones` | TVs: densest clustering among non-phone electronics leaves, lowest prose-warranty conflict. Headphones broaden the department | 302 + 399 |
  | `furniture` | `chairs` + `home_office_desks` | Largest pool; 90-day general-merchandise window (Target); opened vs unopened (IKEA 180 vs 365) | 796 + 339 |

  \*Products with 5–50 questions after removing price, stock and carrier questions, ≥ 3 bullets, no warranty term in their own prose, and ≥ 1 near-duplicate question pair (content-word Jaccard 0.45–0.99; exact repeats excluded). **These are upper bounds**: the answerability filter below will shrink them. Evidence: `docs/work/2026-10-03-pqa-category-choice/`.
- **⚠️ Selection rule — proposed, frozen at `super-plan.md` item 3.2.** Every filter in the footnote above is measured and cheap. One more is required and not yet designed. ⚠️ **Most real questions are not answerable from their own product record**: ~20–23 % are answerable from specifications (ePQA 22.9 %; Flipkart ~20 %), and a hand-read laptop example had 1 in 15. Without an **answerability filter**, the reference `LLM(retrieve(q), q)` becomes "not available" for most queries, reuse becomes trivially safe, and natural traps stop being traps. 194 questions in the six leaves carry ePQA's human answerability labels and serve as the filter's validation set. `TODO(W8): the answerability criterion and its agreement with those labels.`
- **Empty and thin products exist.** 2.7–9.1 % of products per leaf have no bullets and no description, and the document is then the title alone. The ≥ 3-bullets filter removes them. 3.4–16.8 % state a warranty term in their own prose, which can contradict the authored warranty documents of §2. `TODO(W8): exclude them, or scope the authored warranty documents around them.`

## 2. Policy corpus (self-authored)
- **Provenance:** **~13** policy documents (returns, warranty, shipping) authored in-house, modelled on real store policy pages. Author-owned → freely releasable. The count rose from 8 because opposing conditions live in separate documents (G5); it is fixed at `super-plan.md` item 3.3.
- **Per-department windows, modelled on published policy** (primary sources, fetched 2026-10-03):

  | `category` | Return window — modelled on | Opposing conditions available |
  | :--- | :--- | :--- |
  | `phones` | 14 days — Target; Best Buy (activatable devices) | opened (restocking fee: Target up to $35, Best Buy $45) vs unopened; domestic vs international warranty (21.6 % of phone warranty questions) |
  | `laptops` | 30 days — Target electronics | new (30) vs renewed (90) — Amazon; domestic vs international warranty (26.4 %) |
  | `electronics` | 30 days — Target electronics | none found in a primary source |
  | `furniture` | 90 days — Target general merchandise | opened (180) vs unopened (365) — IKEA |

  Warranty terms (~1 year for phones, laptops and electronics; multi-year for furniture) come from **secondary** sources so far. A primary citation is required before any of them is authored. `laptops` and `electronics` share 30-day terms by design: identical answers under different `doc_id`s measure what namespace partitioning costs in refused safe reuse.
- **⚠️ Per-category, not global.** Return/warranty windows must **genuinely differ across the product categories** of §1. A single global return policy makes every policy question retrieve the same chunk, drives source overlap to ≈ 1 everywhere, and nulls C1 by construction of the corpus rather than by finding (§7).
- **Why in-house:** the invalidation experiment (RQ3) needs *controlled* edits; only a corpus under the author's control permits that (proposal §9.3). Policy documents are also where the lookalike traps live — two categories with genuinely different return windows is what makes the provenance signal testable.
- **⚠️ Four structural requirements for `v1`, each measured against what `dev-v0` actually produced:**
  1. **A product↔policy join key.** Policy records carry `category`; product records already do. In `dev-v0` the ingest writes `category: ""` for *every* policy, so the tag is empty on all four policy documents and **there is no join in either direction** — which makes a mixed specification + policy question structurally ungroundable.
  2. **Per-category *warranty* windows, not only return windows.** `dev-v0` shipped one global `policy-warranty` and one global `policy-shipping`, leaving **exactly one differentiated axis (returns) covering two of four categories** — `kitchen` has no return policy at all.
  3. **Policy documents long enough to chunk into ≥ 3 chunks.** `dev-v0` ingested 44 documents into **44 chunks — one per document**, because the authored text falls under `chunk_size = 256`. A singleton `sources(e)` makes `overlap = |A ∩ B| / |B|` take only **0 or 1**: θ has nothing to sweep and the C1 frontier degenerates to a step function. the frozen chunking anticipated this from the `chunk_size` direction; `dev-v0` reached it from the *document-length* direction instead.
  4. **A stratum taxonomy that separates provenance from wording** (below).
- `TODO(W8): list of policy doc_ids and titles.`

### Query strata for `v1`

The three existing strata (natural cluster / generated paraphrase / constructed trap) cannot distinguish *similar query, same provenance* from *differently worded, same provenance* — both land in the first two. `v1` tags every query with exactly one of:

| Stratum | Query similarity | Provenance | What it tests |
| :---: | :--- | :--- | :--- |
| **A** | high | **same** | Safe reuse — the case a semantic cache *should* serve |
| **B-cross** | high | **different**, *different product* | The lookalike trap across products. **A `product_id` cache key also solves this one** |
| **B-within** | high | **different**, *same product* | ⚠️ The trap **only provenance solves**. See the gate criterion in §7 |
| **C** | low (different wording) | same | Why exact-match alone is insufficient — Tier 2's reason to exist |
| **D** | any | spans **product and policy** | Multi-source-type grounding. Requires requirement 1 above; **impossible in `dev-v0`** |

> ⚠️ **Why B is split.** If every B pair is *cross-product*, then adding `product_id` to the cache key reproduces C1's entire benefit at zero cost, with no retrieval round-trip on the hit path — and C1 is redundant **by construction of the corpus**. `product_id` is metadata known *before* retrieval. Provenance is the grounding, known only *after* it. B-within pairs are the cases where those two differ, and they are what makes the rule non-redundant. Build them as same-product pairs differing in policy dimension or applicable condition: *"how long is the **warranty** period"* vs *"how long is the **return** period"*, or *"can I return this if it's **opened**"* vs *"…**unopened**"*. These exist only if policy documents chunk finely enough to separate conditions, which is a **second, independent reason** for requirement 3 above.

## 3. Query workload

**The workload is split by half. Both halves take their wording from real traffic, but only the product half takes its grounding from real content.**

| Half | Source | Why |
| :--- | :--- | :--- |
| **Product-specification questions** | Real shopper questions from **Amazon-PQA** — the same records that supply §1's product content | Real wording and real traps. ⚠️ **Corrected 2026-10-03:** paraphrase *within one product* is low. Of 100 questions about one product, 5–14 re-ask something already asked (frozen embedding, cosine ≥ 0.85), and clusters are pairs, not families. PQA records what shoppers *post*, after the public Q&A board has shown them what was already asked, so it under-represents traffic redundancy by construction. **Redundancy is therefore modelled (Zipf) and machine-generated paraphrases supply Tier 2's volume**, with natural and generated pairs reported separately (§4) |
| **Policy questions** | **Wording sampled from PQA where possible; grounding always authored** | ⚠️ **Corrected 2026-10-03.** An earlier version said PQA contains no policy questions at all. Measured, it contains thousands per leaf — e.g. 12,585 warranty questions in `unlocked_cell_phones` — such as *"What is the return policy?"* and *"Does the warranty remain valid in India?"* What does not exist is a **store policy document** to ground them, so their grounding is the authored corpus of §2. Their wording is real traffic; their answers are not. Because the policy lane's namespace is the policy document, one cached answer serves the same question about every product in a department |

- ⚠️ **The dataset's answers are NOT ground truth.** The evaluation defines the reference as `reference(q) = LLM(retrieve(q), q)`, generated by the full pipeline. PQA's `answers` are **community answers** — subjective, sometimes wrong, sometimes contradicting each other within one record (median 1–2 per question, up to 56). They are used as *question* provenance only. An earlier draft of this card described the workload as coming "with reference answers", which was misleading and is corrected here.
- ✅ **The join risk is deleted, not reduced.** This bullet previously recorded an unverified ASIN-coverage risk across a near-decade gap between AmazonQA (2016, `asin`) and `Amazon-Reviews-2023` (`parent_asin`). PQA carries the question and the product content **in the same record**, so there is no join to measure and no coverage to verify.
- ⭐ **PQA supplies `B-within` traps naturally, and this matters for validity.** The same paraphrase clustering that yields strata A and C also surfaces same-product pairs that read as paraphrases and have **different answers** — *"Does printer work with windows 10?"* against *"Will this unit work with Windows 7?"*. These are the Tier-1 collision invariant `B-within` stratum and the support gate residual, occurring in real traffic. The standing limitation on the C1 result is that the measured residual is partly a property of how carefully the author split conditions; traps the author did not construct weaken that objection in a way an authored workload cannot. `TODO(W8): count of natural vs. constructed B-within pairs.`
- **Queries must be self-contained.** Real PQA questions are asked *on a product page* and are therefore elliptical — "does this fit?", "how long is the warranty?". The `/ask` contract carries no product context (`interfaces.md` §A), so every workload query must name its product or category in the query text. Rewriting is required, and it is reported as a limitation rather than presented as raw real traffic.
- `TODO(W8): question count K, selection rule used, rewrite policy, per-stratum counts.`

## 4. Paraphrase stress set
- Natural paraphrase clusters mined from the Q&A data + machine-generated paraphrases of seed questions, built so exact-match fails and Tier-2 is genuinely exercised; also the redundancy driver for load tests (Zipf-distributed, **3 skew levels** — proposal §9.1).
- **Lookalike traps** are part of this set: near-identical question pairs that ground in *different* chunks. These are the cases RQ2 turns on, and one of them is the demo script .
- `TODO(W8): #clusters, #lookalike pairs, generation model/prompt for machine paraphrases (record for reproducibility).`

## 5. Update-set catalog (RQ3)
Controlled spec/policy edits, **split by whether the edit changes the answer**. With blind purge as the only policy — the predictor that would have gated it was withdrawn — the split now serves a measurement purpose: it quantifies how often blind purge **over-invalidates** on answer-preserving edits — the precision cost the design accepts in exchange for guaranteed completeness (proposal §5 C2, RQ3, §9.3).

Schema (one row per edit):

| Field | Type | Notes |
| :--- | :--- | :--- |
| `edit_id` | string | e.g. `edit-007` |
| `doc_id` | string | target document (`interfaces.md` §C) |
| `chunk_id` | string | target chunk, `{doc_id}#chunk-{ordinal}` |
| `change_type` | enum | `substantive` (answer-changing) \| `cosmetic` (answer-preserving) |
| `before` | string | original chunk text |
| `after` | string | edited chunk text |
| `expected_effect` | string | which cached answers should go stale (substantive) or stay valid (cosmetic) |

`TODO(W8): ~20 edits (built W10), balanced across substantive/cosmetic; include the 30→14 day return edit used in the demo step 5.`

## 6. Judged evaluation set (Contribution 1)
Replaces the train/validation/test reuse-safety dataset of v0.1 — **nothing is trained** after the scope reduction, so the set exists only to score correctness.

- **Build:** for every cache hit produced by a configuration, the returned answer is judged against the full-pipeline reference by an **LLM judge different from the answer generator** (avoiding self-agreement bias), using the frozen prompt in the evaluation . Built at thesis W13–W14.
- **Deduplication:** verdicts are keyed by `sha256(query ‖ candidate_answer)` and cached across configurations — configs return identical answers for the same query constantly, and this is what keeps the judging bill affordable.
- **Validation:** **~100** pairs human-verified; judge–human agreement is reported as the false-hit metric's **noise floor**, which δ must clearly exceed (proposal §10; the false-hit budget).
- **No splits, no leakage concern:** there is no training set to leak into.
- `TODO(thesis W14): judged-pair count, judge model id, agreement number, measured judging wall-clock cost.`

---

## Schemas (frozen shapes)
`TODO(W8): finalize; sketches below.`

```json
// product record
{ "doc_id": "product-B08XYZ", "title": "...", "specs": {"...": "..."}, "category": "..." }

// policy document  — `category` is the product<->policy join key; null only for
//                     genuinely global policies, which v1 keeps to a minimum
{ "doc_id": "policy-returns-electronics", "title": "Return Policy — Electronics",
  "category": "electronics", "text": "..." }

// QA pair  — `stratum` is one of A | B-within | B-cross | C | D (see section 2)
//            `reference_answer` is pipeline-generated at eval time, NOT from the source dataset (§3)
{ "qa_id": "...", "question": "...", "reference_answer": "...",
  "doc_ids": ["policy-returns-electronics"], "product_id": "product-B08XYZ",
  "stratum": "B-within" }
```

## 7. Corpus sensitivity gate ⚠️ — run **before** the W8 freeze

C1 can only produce a signal where queries are **similar but ground differently**. The reduced corpus risks removing the phenomenon it studies: if every policy question retrieves the same few chunks, overlap ≈ 1 everywhere and the rule can never change a decision. This gate catches that *before* the snapshot is hashed, when the corpus can still be fixed.

**Applies to `v1` only** — `dev-v0` is not gated, because nothing is measured on it.

**Procedure (~30 lines, W8):** embed all workload queries with the frozen embedding model; compute pairwise similarity; retrieve top-k for each; then count pairs satisfying **`sim ≥ 0.85` AND `J ≤ 0.2`**.

> **Implemented and runnable (2026-09-06):** `experiments/scripts/corpus_gate.py`, via `make gate-corpus`.
> It computes every statistic listed below and **refuses to print a snapshot hash unless all four
> criteria pass**, so "frozen" cannot happen by accident.
> ⚠️ **"Four" means G1–G4. G5 is not implemented yet** (`super-plan.md` item 3.5). Until it is, a
> passing gate run says nothing about G5, even though the freeze policy requires all five. Check G5
> by hand before any freeze.
>
> **The workload file must live OUTSIDE `data/{version}/`** — `rag.ingest` globs that directory and
> asserts `doc_id == filename`, so a workload dropped in it breaks ingestion. Convention:
> `data/workload-{version}.json`, passed as `make gate-corpus WORKLOAD=…`.
>
> **Two stages, which resolves an apparent contradiction in the outcome table below.** A failure is
> said to mean *"do not proceed to ingestion"*, yet G1/G2 are defined over `retrieve(q)` and so need
> an ingested index. They split by what they need: **G3, G4 and G5 are structural** — corpus files and
> the workload file only, and `make gate-corpus STRUCTURAL=1` runs them alone, which is the loop to
> run while authoring. **G1 and G2 need the frozen retrieval path.** Stage 1 failing aborts before
> stage 2, so a mis-slugged corpus is never embedded.
>
> **G3's normalization is a second implementation of a Go function** and the Go one is what actually
> runs on the hit path. A looser mirror lets the gate pass a corpus that collides in production; a
> tighter one rejects a corpus Tier 1 would have handled — both silent. The two are pinned to shared
> golden vectors in `contracts/normalize/cases.json`, asserted from both languages.
>
> **Shakedown against `dev-v0` (2026-09-06, not a gate result — `dev-v0` is not gated).**
> 24 questions, 44 documents: G3 and G4 pass; **G1 = 0 pairs** and **G2 = 0 B-within**. Across the
> 16 high-similarity pairs the mean Jaccard is **0.68** and *no pair at all* falls below the 0.2
> ceiling — the lowest occupied histogram bucket is 0.2–0.3. This is `v1` corpus requirement 3 measured
> rather than predicted: 44 documents ingesting to 44 chunks gives every question a near-identical
> retrieval set, so the corpus cannot express the phenomenon C1 studies. It is the concrete target
> `v1` has to clear.

> ⚠️ **Which overlap — the gate's is not the rule's.** The rule's overlap is `|A ∩ B| / |B|`, between a query's retrieval and a *cached entry's* provenance — **asymmetric, and therefore not well-defined for a query–query pair**, which is what this gate counts. The gate uses symmetric Jaccard `J(A,B) = |A ∩ B| / |A ∪ B|` over the two top-k retrieval sets. At equal `top_k` this is monotone in `|A ∩ B|` and orders pairs identically to `|A ∩ B| / k`; at `top_k = 5`, `J ≤ 0.2` admits **at most one shared chunk**. The gate statistic is a **corpus property**, never the rule's operating metric, and the two are reported separately so they cannot be conflated.

**Five criteria, all of which must pass before the snapshot is hashed.**

| # | Criterion | On failure |
| :---: | :--- | :--- |
| **G1** | High-similarity / low-overlap pairs **≥ ~50** | **Fix the corpus, not the rule** — add categories, differentiate policy windows per category, re-run |
| **G2** | **`B-within` > 0** | Rebuild. A corpus of only cross-product traps is defeated by a one-line change to the cache key, and C1 would be redundant by construction |
| **G3** | **Zero Tier-1 collisions** | Disambiguate the offending query text. Do not proceed to ingestion |
| **G4** | **Every `doc_id` begins with `policy-` or `product-`** (the doc-id kind prefix, `interfaces.md` §C v0.6) | Re-slug the offending documents before ingestion |
| **G5** | **No two opposing conditions of the same kind share a `doc_id`** (amended 2026-09-21 to document granularity) | Author the conditions into separate documents. Do not proceed to ingestion — this is unfixable after the freeze |

**G2 — the within/cross split.** Every pair counted by G1 is additionally labelled `B-within` (same product, different grounding) or `B-cross` (different product). The gate reports both counts. **No numeric floor above zero is set**: there is no evidence yet from which to derive one, and an invented threshold is less defensible than a stated gap. The first gate run on `v1` supplies the number, and it is recorded below as a frozen corpus statistic.

**G4 — the doc-id kind prefix.** The reuse rule reads a question's lane from the *prefix* of the documents its retrieval returned, so the prefix is the only place a document's kind is recorded. A corpus that omits it does not fail loudly: every question classifies into the spec lane, the lane machinery reports plausible values throughout, and the mixed lane never fires — a null result produced by the corpus rather than by the rule. It is a one-line check over the ingested doc-ids and runs alongside G1. Ingestion enforces the same rule (`rag/src/rag/ingest.py:record_kind()`), so G4 is a check that ingestion was actually the path taken.

**G5 — condition-splitting, at DOCUMENT granularity.** `v1` corpus requirement 3 asks for policy documents long enough to yield at least three chunks, so that **containment has a gradient to sweep**. G5 asks something different and independent: that **opposing conditions do not share a `doc_id`**.

⚠️ **The granularity was wrong when first written, and the correction matters.** Condition-splitting originally required one *chunk* per condition. `reuse.Namespace` takes its policy component from the `doc_id` of the rank-1 policy chunk, and `reuse/lane.go`'s `docID()` deliberately strips `#chunk-{ordinal}` so that re-chunking cannot silently repartition the cache. An intra-document split is therefore **invisible to the namespace**. Worse, where retrieval returns both chunks — the expected case, since the embedding carries almost no weight on a negation — all four conjuncts of the reuse rule go blind at once: similarity cannot separate two near-identical questions, the namespace is the same document, containment is 1.0 over the same chunk set, and the support gate sees the text of *both* conditions in the concatenated evidence. **At document granularity the namespace conjunct separates them**, using machinery that already exists.

The check is structural — it reads the corpus files, needs no ingested index, and runs in stage 1 alongside G3 and G4. It does **not** eliminate the residual: it still depends on retrieval ranking the correct condition document first. The difference is categorical rather than probabilistic — under a chunk-level split the pair *cannot* be separated by any conjunct; under a document-level split it *can* be, and the rate at which it actually is is what **RQ2a** measures on the `B-within` stratum built to contain it.

**G3 — the Tier-1 collision check.** Tier 1 is a bare hash lookup that runs **no reuse rule** (`interfaces.md` §D), so a collision is unguarded and silent. Procedure: group all workload queries by `normalize(q)` using the key-normalisation function function, and fail any group whose members disagree on `doc_ids` or `reference_answer`. Note that stripping punctuation collapses `Model A-1` and `Model A1`. The check is ~30 lines and runs alongside G1.

| Outcome | Action |
| :--- | :--- |
| G1 ∧ G2 ∧ G3 ∧ G4 ∧ G5 all pass | Freeze and hash the corpus. Record the statistics below |
| Any criterion fails | Fix the corpus, re-run all five. Do not proceed to ingestion |

**Recorded as frozen corpus statistics** (they are also what make a null C1 interpretable rather than merely disappointing — proposal §5 C1 fallback). Every one of them is printed by `make gate-corpus`, and `REPORT=<path>` additionally writes them as JSON so the freeze record is machine-readable rather than transcribed by hand:

- `TODO(W8): count of high-similarity / low-overlap pairs (G1).`
- `TODO(W8): B-within and B-cross counts and their ratio (G2).`
- `TODO(W8): Tier-1 collision groups found, and benign duplicate groups (G3).`
- `TODO(W8): opposing-condition pairs sharing a doc_id, before and after splitting (G5).`
- `TODO(W8): distribution of source-overlap across all high-similarity pairs (the overlap-variance statistic).`
- `TODO(W8): per-stratum query counts (A / B-within / B-cross / C / D, §2) and the trap fraction of the workload.`
- `TODO(W8): K — the count of distinct queries in the frozen workload.` ⚠️ **Cache capacity derives from this**: `cache_capacity = round(0.25 × K)`. Record both `K` and the derived capacity here and in every run manifest.

## Ethics / PII
Public, non-personal data only. No user accounts, no personalization (proposal §6.3) — answers that vary by locale/membership are treated as dynamic and bypass the cache, so no personal data enters the corpus or cache.
