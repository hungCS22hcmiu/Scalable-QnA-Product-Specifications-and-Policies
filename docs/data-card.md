# Data Card

**Status:** stub v0.3 — scaffold now, **fill and freeze at timeline W8** · **Created:** 2026-07-23 · **Revised:** 2026-09-02 (ADR-027, ADR-028)
**Companion to:** `Final_Proposal.md` (§9.3 datasets), `interfaces.md` (§C chunk-IDs, §D Tier-1 key), `decisions.md` (ADR-008, ADR-013, ADR-014, ADR-016, ADR-020, ADR-024, **ADR-027**, **ADR-028**).

**Purpose.** Document provenance, licensing, schema, and versioning for every data artifact the study consumes or produces, so results are reproducible and the open-source deliverable (proposal §13) is legally clean. Items marked **`TODO(W8)`** are filled when the corpus is frozen.

**Freeze policy.** At **W8** the experimental snapshot `v1` is frozen and hashed. `dataset_version`, `snapshot_sha256`, and **`K` (distinct-query count, which sets cache capacity — ADR-027)** are recorded here and in every run manifest (`experiment-protocol.md`). Re-chunking or corpus edits bump the version (ADR-008). **No experiment runs against an unfrozen corpus**, and none against one that has not passed all three gate criteria in §7.

> ⚠️ **Two corpora — do not conflate them (ADR-020).**
>
> | Corpus | Built | Size | Status |
> | :--- | :--- | :--- | :--- |
> | **`dev-v0`** | W5 | ~40 products, 4 policy docs, no category balance | **Throwaway.** Exists only to make the pipeline run during the 3-week runway. Not hashed, not versioned, **not citable in any result.** Discarded after W8 |
> | **`v1`** | W8 | ~150 products, **≥3 categories**, per-category policies | The **frozen experimental corpus**. Hashed, versioned, and gated by §7 |
>
> Both use the **same frozen embedding model and chunking config** (ADR-003/ADR-014, frozen W5), so `v1` is a content expansion rather than a re-chunk. Any number in the pre-thesis report that comes from `dev-v0` must be labelled preliminary and non-authoritative.

> **Sizes cut by ADR-016.** Product subset 500–2,000 → **~150**; policy corpus 5–10 → **8** documents; the reuse-safety training set is replaced by a smaller **judged evaluation set** (no training, so no splits). A small clean corpus beats a large messy one, and W8 is a hard timebox.

| Artifact | Source | License posture | Frozen |
| :--- | :--- | :--- | :--- |
| Product catalog (~150) | McAuley-lab Amazon product data | ⚠️ redistribution TBD | `TODO(W8)` |
| Query workload + reference answers | AmazonQA / McAuley-lab | ⚠️ redistribution TBD | `TODO(W8)` |
| Policy corpus (8 docs) | self-authored | author-owned → releasable | `TODO(W8)` |
| Paraphrase stress set | mined + machine-generated | derivative — see below | `TODO(W8)` |
| Update set (~20 edits) | self-authored edits | author-owned | `TODO(W8)` |
| Judged evaluation set | auto-generated + ~100 human-verified | author-owned | thesis W14 |

---

## 1. Product catalog (Amazon / McAuley-lab)
- **Source:** McAuley-lab Amazon datasets (product specifications). `TODO(W8): exact dataset name, version, URL, access date.`
- **⚠️ License / redistribution:** the Hugging Face dataset card for `Amazon-Reviews-2023` **states no license**, so redistribution terms are unresolved and the `TODO` below stands. Default to the download-and-build-script fallback. Verify the dataset's terms **before** committing any of it to the public repo. If redistribution is not permitted, ship a **download+build script** and a hash manifest instead of the raw data, and reconcile with the project LICENSE (ADR-013).
- **Subset criteria:** **~150 products across ≥ 3 categories** (proposal §9.3, timeline W8). Small on purpose — the corpus exists to exercise the cache, not to stress retrieval — but **not single-category**: see the sensitivity gate in §7. `TODO(W8): categories, filter rules, final product count.`

## 2. Policy corpus (self-authored)
- **Provenance:** **8** policy documents (returns, warranty, shipping) authored in-house, modelled on real store policy pages. Author-owned → freely releasable.
- **⚠️ Per-category, not global.** Return/warranty windows must **genuinely differ across the product categories** of §1. A single global return policy makes every policy question retrieve the same chunk, drives source overlap to ≈ 1 everywhere, and nulls C1 by construction of the corpus rather than by finding (§7).
- **Why in-house:** the invalidation experiment (RQ3) needs *controlled* edits; only a corpus under the author's control permits that (proposal §9.3). Policy documents are also where the lookalike traps live — two categories with genuinely different return windows is what makes the provenance signal testable.
- **⚠️ Four structural requirements for `v1` (ADR-024), each measured against what `dev-v0` actually produced:**
  1. **A product↔policy join key.** Policy records carry `category`; product records already do. In `dev-v0` the ingest writes `category: ""` for *every* policy, so the tag is empty on all four policy documents and **there is no join in either direction** — which makes a mixed specification + policy question structurally ungroundable.
  2. **Per-category *warranty* windows, not only return windows.** `dev-v0` shipped one global `policy-warranty` and one global `policy-shipping`, leaving **exactly one differentiated axis (returns) covering two of four categories** — `kitchen` has no return policy at all.
  3. **Policy documents long enough to chunk into ≥ 3 chunks.** `dev-v0` ingested 44 documents into **44 chunks — one per document**, because the authored text falls under `chunk_size = 256`. A singleton `sources(e)` makes `overlap = |A ∩ B| / |B|` take only **0 or 1**: θ has nothing to sweep and the C1 frontier degenerates to a step function. ADR-014 anticipated this from the `chunk_size` direction; `dev-v0` reached it from the *document-length* direction instead.
  4. **A stratum taxonomy that separates provenance from wording** (below).
- `TODO(W8): list of policy doc_ids and titles.`

### Query strata for `v1` (ADR-024)

The three existing strata (natural cluster / generated paraphrase / constructed trap) cannot distinguish *similar query, same provenance* from *differently worded, same provenance* — both land in the first two. `v1` tags every query with exactly one of:

| Stratum | Query similarity | Provenance | What it tests |
| :---: | :--- | :--- | :--- |
| **A** | high | **same** | Safe reuse — the case a semantic cache *should* serve |
| **B-cross** | high | **different**, *different product* | The lookalike trap across products. **A `product_id` cache key also solves this one** |
| **B-within** | high | **different**, *same product* | ⚠️ The trap **only provenance solves**. See the gate criterion in §7 |
| **C** | low (different wording) | same | Why exact-match alone is insufficient — Tier 2's reason to exist |
| **D** | any | spans **product and policy** | Multi-source-type grounding. Requires requirement 1 above; **impossible in `dev-v0`** |

> ⚠️ **Why B is split (ADR-028).** If every B pair is *cross-product*, then adding `product_id` to the cache key reproduces C1's entire benefit at zero cost, with no retrieval round-trip on the hit path — and C1 is redundant **by construction of the corpus**. `product_id` is metadata known *before* retrieval. Provenance is the grounding, known only *after* it. B-within pairs are the cases where those two differ, and they are what makes the rule non-redundant. Build them as same-product pairs differing in policy dimension or applicable condition: *"how long is the **warranty** period"* vs *"how long is the **return** period"*, or *"can I return this if it's **opened**"* vs *"…**unopened**"*. These exist only if policy documents chunk finely enough to separate conditions, which is a **second, independent reason** for requirement 3 above.

## 3. Query workload

**The workload is split by half, and only one half can be sourced from real traffic.**

| Half | Source | Why |
| :--- | :--- | :--- |
| **Product-specification questions** | Real shopper questions from **AmazonQA** (McAuley, UCSD) | Carries genuine paraphrase structure — many users, same intent, different words |
| **Policy questions** | **Authored in-house** | ⚠️ **AmazonQA contains no policy questions at all.** It is product Q&A. Questions about return windows or warranty terms grounded in *store policy documents* do not exist in it. This is a constraint, not a convenience — and stratum B lives mostly in this half |

- ⚠️ **The dataset's answers are NOT ground truth.** `experiment-protocol.md` §4 defines the reference as `reference(q) = LLM(retrieve(q), q)`, generated by the full pipeline. AmazonQA's answers are **community answers** — subjective, sometimes wrong, and explicitly modelled as ambiguous by the source paper. They are used as *question* provenance only. An earlier draft of this card described the workload as coming "with reference answers", which was misleading and is corrected here.
- ⚠️ **Join risk — verify before building (`TODO(W8)`).** AmazonQA is the **2016** release, keyed on `asin`, with timestamps around 2014. `Amazon-Reviews-2023` (§1) is keyed on **`parent_asin`**. ASIN coverage across a near-decade gap is **unverified**. Measure the join rate first: if too few AmazonQA questions map onto products in the selected 2023 subset, either select products *from* the QA-covered set or author more of the workload, and record which was done.
- **Queries must be self-contained (ADR-028).** Real AmazonQA questions are asked *on a product page* and are therefore elliptical — "does this fit?", "how long is the warranty?". The `/ask` contract carries no product context (`interfaces.md` §A), so every workload query must name its product or category in the query text. Rewriting is required, and it is reported as a limitation rather than presented as raw real traffic.
- `TODO(W8): question count K, join rate achieved, rewrite policy, per-stratum counts.`

## 4. Paraphrase stress set
- Natural paraphrase clusters mined from the Q&A data + machine-generated paraphrases of seed questions, built so exact-match fails and Tier-2 is genuinely exercised; also the redundancy driver for load tests (Zipf-distributed, **3 skew levels** — proposal §9.1).
- **Lookalike traps** are part of this set: near-identical question pairs that ground in *different* chunks. These are the cases RQ2 turns on, and one of them is `defense_demo.md` step 4.
- `TODO(W8): #clusters, #lookalike pairs, generation model/prompt for machine paraphrases (record for reproducibility).`

## 5. Update-set catalog (RQ3)
Controlled spec/policy edits, **split by whether the edit changes the answer**. With blind purge as the only policy (ADR-010 superseded), the split now serves a measurement purpose: it quantifies how often blind purge **over-invalidates** on answer-preserving edits — the precision cost the design accepts in exchange for guaranteed completeness (proposal §5 C2, RQ3, §9.3).

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

`TODO(W8): ~20 edits (built W10), balanced across substantive/cosmetic; include the 30→14 day return edit used in defense_demo.md step 5.`

## 6. Judged evaluation set (Contribution 1)
Replaces the train/validation/test reuse-safety dataset of v0.1 — **nothing is trained** after ADR-016, so the set exists only to score correctness.

- **Build:** for every cache hit produced by a configuration, the returned answer is judged against the full-pipeline reference by an **LLM judge different from the answer generator** (avoiding self-agreement bias), using the frozen prompt in `experiment-protocol.md` §4. Built at thesis W13–W14.
- **Deduplication:** verdicts are keyed by `sha256(query ‖ candidate_answer)` and cached across configurations — configs return identical answers for the same query constantly, and this is what keeps the judging bill affordable.
- **Validation:** **~100** pairs human-verified; judge–human agreement is reported as the false-hit metric's **noise floor**, which δ must clearly exceed (proposal §10; ADR-006).
- **No splits, no leakage concern:** there is no training set to leak into.
- `TODO(thesis W14): judged-pair count, judge model id, agreement number, measured judging wall-clock cost.`

---

## Schemas (frozen shapes)
`TODO(W8): finalize; sketches below.`

```json
// product record
{ "doc_id": "product-B08XYZ", "title": "...", "specs": {"...": "..."}, "category": "..." }

// policy document  — `category` is the product<->policy join key (ADR-024); null only for
//                     genuinely global policies, which v1 keeps to a minimum
{ "doc_id": "policy-returns-electronics", "title": "Return Policy — Electronics",
  "category": "electronics", "text": "..." }

// QA pair  — `stratum` is one of A | B-within | B-cross | C | D (see section 2, ADR-028)
//            `reference_answer` is pipeline-generated at eval time, NOT from the source dataset (§3)
{ "qa_id": "...", "question": "...", "reference_answer": "...",
  "doc_ids": ["policy-returns-electronics"], "product_id": "product-B08XYZ",
  "stratum": "B-within" }
```

## 7. Corpus sensitivity gate ⚠️ — run **before** the W8 freeze

C1 can only produce a signal where queries are **similar but ground differently**. The reduced corpus (ADR-016) risks removing the phenomenon it studies: if every policy question retrieves the same few chunks, overlap ≈ 1 everywhere and the rule can never change a decision. This gate catches that *before* the snapshot is hashed, when the corpus can still be fixed.

**Applies to `v1` only** — `dev-v0` is not gated, because nothing is measured on it (ADR-020).

**Procedure (~30 lines, W8):** embed all workload queries with the frozen embedding model; compute pairwise similarity; retrieve top-k for each; then count pairs satisfying **`sim ≥ 0.85` AND `J ≤ 0.2`**.

> ⚠️ **Which overlap — the gate's is not the rule's (ADR-024).** The rule's overlap is `|A ∩ B| / |B|`, between a query's retrieval and a *cached entry's* provenance — **asymmetric, and therefore not well-defined for a query–query pair**, which is what this gate counts. The gate uses symmetric Jaccard `J(A,B) = |A ∩ B| / |A ∪ B|` over the two top-k retrieval sets. At equal `top_k` this is monotone in `|A ∩ B|` and orders pairs identically to `|A ∩ B| / k`; at `top_k = 5`, `J ≤ 0.2` admits **at most one shared chunk**. The gate statistic is a **corpus property**, never the rule's operating metric, and the two are reported separately so they cannot be conflated.

**Three criteria, all of which must pass before the snapshot is hashed.**

| # | Criterion | On failure |
| :---: | :--- | :--- |
| **G1** | High-similarity / low-overlap pairs **≥ ~50** | **Fix the corpus, not the rule** — add categories, differentiate policy windows per category, re-run |
| **G2** | **`B-within` > 0** (ADR-028) | Rebuild. A corpus of only cross-product traps is defeated by a one-line change to the cache key, and C1 would be redundant by construction |
| **G3** | **Zero Tier-1 collisions** (ADR-028) | Disambiguate the offending query text. Do not proceed to ingestion |

**G2 — the within/cross split.** Every pair counted by G1 is additionally labelled `B-within` (same product, different grounding) or `B-cross` (different product). The gate reports both counts. **No numeric floor above zero is set**: there is no evidence yet from which to derive one, and an invented threshold is less defensible than a stated gap. The first gate run on `v1` supplies the number, and it is recorded below as a frozen corpus statistic.

**G3 — the Tier-1 collision check.** Tier 1 is a bare hash lookup that runs **no reuse rule** (`interfaces.md` §D), so a collision is unguarded and silent. Procedure: group all workload queries by `normalize(q)` using the ADR-015 function, and fail any group whose members disagree on `doc_ids` or `reference_answer`. Note that stripping punctuation collapses `Model A-1` and `Model A1`. The check is ~30 lines and runs alongside G1.

| Outcome | Action |
| :--- | :--- |
| G1 ∧ G2 ∧ G3 all pass | Freeze and hash the corpus. Record the statistics below |
| Any criterion fails | Fix the corpus, re-run all three. Do not proceed to ingestion |

**Recorded as frozen corpus statistics** (they are also what make a null C1 interpretable rather than merely disappointing — proposal §5 C1 fallback):

- `TODO(W8): count of high-similarity / low-overlap pairs (G1).`
- `TODO(W8): B-within and B-cross counts and their ratio (G2).`
- `TODO(W8): Tier-1 collision groups found, and benign duplicate groups (G3).`
- `TODO(W8): distribution of source-overlap across all high-similarity pairs (the overlap-variance statistic).`
- `TODO(W8): per-stratum query counts (A / B-within / B-cross / C / D, §2) and the trap fraction of the workload.`
- `TODO(W8): K — the count of distinct queries in the frozen workload.` ⚠️ **Cache capacity derives from this**: `cache_capacity = round(0.25 × K)` (ADR-027). Record both `K` and the derived capacity here and in every run manifest.

## Ethics / PII
Public, non-personal data only. No user accounts, no personalization (proposal §6.3) — answers that vary by locale/membership are treated as dynamic and bypass the cache, so no personal data enters the corpus or cache.
