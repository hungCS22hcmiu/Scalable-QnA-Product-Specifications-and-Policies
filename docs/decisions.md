# Decision log

**Status:** in force · **Opened:** 2026-09-22 · **Numbering starts at ADR-001.**

This log was opened fresh for the thesis phase. The pre-thesis decision log — a separate
document with its own numbering that reached 041 — was deleted on 2026-09-22 and **nothing here
refers to it**. An `ADR-NNN` in this file means an entry in this file and nothing else.

---

## How to use this file

One entry per architecturally significant choice. Append; never renumber, never delete. A
decision that turns out wrong is superseded by a new entry, and both stay — the write-up's design
chapter is built from this history, and so is the defence.

**Every entry must carry an `Invalidates:` line.** It is the single most important sentence in the
record, because it is the only thing that answers *"are these two numbers comparable?"* months
later. An entry without it is not finished. Write `none — no runs yet` when that is the truth.

```markdown
### ADR-NNN — <title>
**Decided (scope | method | frozen | data)** · <YYYY-MM-DD> · *<documents this touches>*

<one-paragraph statement of the decision>

- **Rationale:** why, and why now.
- **Alternatives:** what was rejected, and on what evidence.
- **Consequences:** what this makes true, and what it costs.
- **Invalidates:** which prior runs or results are now void — or `none — no runs yet`.
```

Nothing enforces this automatically. The hook that used to gate frozen-value edits was removed on
2026-09-22 along with the files it read, so a frozen value can now be changed with no error and no
warning. Writing the entry is the only trace such a change leaves.

---

## Summary

| ADR | Title | Status | Invalidates |
| :--- | :--- | :--- | :--- |
| ADR-001 | *Reserved* — co-hosted load generation and the load generator's footprint (`super-plan.md` item 1.6; named by Phase 1's exit criterion) | not yet written | — |
| ADR-002 | `v1` draws from six Amazon-PQA leaves mapped onto four departments | in force | none — no runs yet |

---

## Inherited state — decided before this log existed

These were settled during the pre-thesis phase and are **in force**. They carry no number here
because they were not decided under this log; their full reasoning lives in git history. Treat them
as frozen: changing any one of them invalidates every measurement taken before the change, and
doing so needs a **new numbered entry** in this file saying exactly that.

| What | Value | Why it is frozen |
| :--- | :--- | :--- |
| Generation model | **Qwen 3.5 2B** via Ollama, `q4_K_M`, `think: false` | Chosen by measurement over five candidates. It replaced Gemma 4 E4B, which entered yellow memory pressure at even the lightest config on this machine's real available RAM |
| Embedding model | **`nomic-embed-text`**, 768-dim, served by Ollama | Never an in-process PyTorch stack — ~2 GB resident for a ~400 MB model, which is a whole generation slot |
| Memory envelope | `num_ctx = 8192`, `OLLAMA_NUM_PARALLEL = 4` | The largest cell of the feasibility grid that held macOS green pressure, at 1.7 GB resident. μ_gen ≈ 28.2 tok/s aggregate was measured **at this pair** and means nothing away from it |
| Vector index | **FLAT (exact)**, COSINE | Approximate retrieval would make `retrieve(q)` nondeterministic and inject overlap noise indistinguishable from the provenance signal. No mid-study HNSW, ever |
| Retrieval depth | `top_k` fixed | It is the denominator of the containment measure; changing it rescales θ silently |
| Cache capacity | `C / K = 0.25` | A ratio of the frozen workload's distinct-query count, so capacity scales with the corpus instead of being a magic number. The **gateway** enforces it; Redis evicts nothing |
| False-hit budget | **δ ≤ 5 %**, provisional | The target operating point for θ/τ tuning until the judge's measured error floor finalises it |
| Support-gate threshold | **`τ_s = 0.6`**, pinned | Taken from the published value. It is **never swept** — sweeping it would turn an adopted mechanism into a tuned one |
| Doc-id kind prefix | `policy-` / `product-` | The reuse rule's lane selection depends on it, so it is a contract and not a naming habit |
| Corpus | `v1` from **Amazon-PQA**; redistribution **not granted** | Ship a download-and-build script plus a hash manifest, never the raw corpus. Cite Rozen et al., NAACL-HLT 2021. `dev-v0` is the development corpus and is **not citable in any result** |
| Load generation | **co-hosted**, reported as such | No second machine exists. The capacity claim is stated as a lower bound rather than a ceiling — see `super-plan.md`, "Measuring without a second machine" |

## Open questions carried into the thesis phase

| # | Question | Blocks |
| :--- | :--- | :--- |
| **F1** | Ollama overrides `OLLAMA_NUM_PARALLEL` to `-np 1` for this model. If the permit pool bounds to a concurrency the model server never offers, every shed rate measured so far describes the harness rather than the gateway | **No admission-control number is citable until this resolves.** Phase 1, item 1.1 |
| **P1** | The run-manifest schema, the frozen judge prompt, the operational metric definitions and the pre-registration record were deleted with the old protocol document and exist nowhere — not in the proposal, not in code. `experiments/k6/ask.js` still prints values "for manifest.yaml" | Phases 5, 6 and 7 all produce artefacts with no defined shape |

---

## Decisions

*ADR-001 is reserved for the co-hosted-measurement decision named by Phase 1's exit criterion and is
not yet written.*

### ADR-002 — `v1` draws from six Amazon-PQA leaves, mapped onto four departments
**Decided (data)** · 2026-10-04 · *`data-card.md` §1–§3, `docs/work/pqa-category-choice/`*

`v1`'s product catalog and question workload come from six Amazon-PQA leaf files, mapped onto four
store departments. The department is the `category` value that product and policy records share —
the product↔policy join key of `data-card.md` §2 requirement 1. PQA has no department-level file;
every one of its 100 files is a leaf.

| `category` | Leaf file(s) | Pool under the proposed filters |
| :--- | :--- | ---: |
| `phones` | `unlocked_cell_phones` | 1,811 |
| `laptops` | `traditional_laptops` | 1,312 |
| `electronics` | `led_&_lcd_tvs` + `over-ear_headphones` | 302 + 399 |
| `furniture` | `chairs` + `home_office_desks` | 796 + 339 |

About 150 products, ~38 per department. The source bytes are pinned by sha256 in `data-card.md` §1.
*Pool* = products with 5–50 questions after removing price, stock and carrier questions, ≥ 3
bullets, no warranty term in their own prose, and at least one near-duplicate question pair
(content-word Jaccard 0.45–0.99, exact repeats excluded). The filters are proposed, not frozen;
they are fixed at `super-plan.md` item 3.2.

- **Rationale:** The author required departments a shopper recognises over PQA's narrow leaves.
  Every leaf clears the ≥ 50-products-per-category floor (from ~150 products over ≥ 3 categories)
  at least **6×**. Published return windows take **three distinct values** across the four —
  **14 / 30 / 30 / 90 days** for phones / laptops / electronics / furniture on Target's own
  returns page. Laptops and electronics share 30 days by design. `data-card.md` §2 requirement 2
  asks for differing **warranty** windows as well, and on current evidence that holds only weakly:
  ~1 year for phones, laptops and electronics against multi-year furniture, from **secondary**
  sources. A primary citation is owed before authoring, and the authored warranty terms may need
  to differ more than the published ones do. Opposing conditions of G5's kind are available from
  primary sources (opened vs unopened phones and furniture; new vs renewed laptops) and from
  traffic (domestic vs international warranty: 21.6 % of phone and 26.4 % of laptop warranty
  questions).
- **Alternatives:**
  - The leaf set `inkjet_printers`, `quadcopters_&_multirotors`, `chairs`, `mattresses` —
    recommended first on secondary measures and rejected by the author as too narrow. The
    evidence stays in the trail.
  - `carrier_cell_phones` for phones — dominated by `unlocked_cell_phones`: pool 387 against 2,260
    after the carrier filter, at the same carrier-question rate (~33 %).
  - **ePQA** (Amazon Science) as a replacement source — CDLA-Sharing-1.0 permits redistribution,
    which PQA's terms do not, but 2.66 questions per product and 0.3 % near-duplicate clustering
    give no traffic redundancy for a cache study. Kept instead as a **validation set** for the
    answerability filter: 194 questions in these six leaves carry ePQA's human labels.
  - Ten further sources were surveyed (AmazonQA, hetPQA, semiPQA, xPQA, HomeDepotQA, McMarket, JD
    product QA, Flipkart, Bitext, DRIP-R). None combines product content, real questions and
    per-product redundancy.
- **Consequences:**
  - Item 3.2's selection rule must add an **answerability filter**. Only ~20–23 % of real product
    questions are answerable from product specifications (ePQA 22.9 %; Flipkart ~20 %), so every
    pool above is an **upper bound** until that filter exists.
  - Natural within-product paraphrasing is low: 5–14 re-asks per 100 questions at cosine ≥ 0.85
    under the frozen embedding. **Generated paraphrases become Tier 2's volume source.** Natural and
    generated pairs are reported separately, and traffic redundancy is modelled by Zipf, never
    inherited from PQA, whose public Q&A board deduplicates what gets posted.
  - Real paraphrases and traps share the 0.80–0.85 cosine band in natural traffic (*"wifi?"* ~
    *"wi-fi?"* at 0.806 against *"USB ports"* ~ *"Ethernet port"* at 0.801). This is RQ2's premise
    observed before any rule is applied, and the B-within stratum can draw on it.
  - The policy corpus grows from 8 to ~13 documents (fixed at item 3.3). `electronics` contributes
    lookalikes but no primary-sourced condition pair. `laptops` and `electronics` share 30-day
    terms, which is where namespace partitioning refuses a safe reuse.
  - `data-card.md` §3's statement that PQA contains no policy questions is withdrawn. Policy
    *wording* can be sampled (thousands of warranty and return questions per leaf); policy
    *grounding* stays authored.
  - The raw files live in `data/raw/pqa/`, gitignored permanently, and are never redistributed.
    The builder verifies sha256 and a non-zero parse rate; the S3 ETags are multipart with an
    unpublished part size and cannot be checked.
- **Invalidates:** none — no runs yet on `v1`. `dev-v0` results stay non-citable, unchanged.
