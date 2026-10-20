# Design — pqa-thick-tail-selection (item 3.2)

**Status:** draft 3, 2026-10-19. The impact findings (`impact.md`) and the design review
(`review.md`, verdict *sound with changes*) are merged. The open questions in `spec.md` are answered
here with the proposed option; §6 names what changes if the author picks another.

## 1. What runs, in order

```
make pqa-select
  │
  ├─ guard: data/v1-draft/product-*.json exist?  ── yes ──> exit 2, nothing written
  ├─ read data/pqa-manifest.json ONCE; keep its bytes and their sha256
  ├─ pass 1, iter_interim: title token counts per leaf → the generic set G_leaf      §2.1
  ├─ pass 2, iter_interim, for each product line (leaf order, then asin order):
  │     tag every question                       §2.1
  │     count the probe's two pools              §2.6
  │     test the product filters                 §2.2  → funnel counts per leaf
  │     count re-asks (all products)             §2.4  → unfiltered re-ask counts
  │     keep the product if eligible
  ├─ probe pools ≠ their pins?                    ── yes ──> exit 2, names the leaf and the pool
  ├─ re-hash the manifest file, re-run verify_interim  ── changed ──> exit 2   (impact F8)
  ├─ draw per leaf                               §2.3  → pool < quota?  ── yes ──> exit 2
  ├─ write into data/v1-draft/.pqa-select-<pid>/  (products/, question-pool.jsonl)
  ├─ swap both into place; on a failure, restore the old pair      (as build_pqa.publish)
  ├─ write data/pqa-selection.json LAST, print the report          §2.4
  └─ on every exit path: remove .pqa-select-* (never .pqa-build-* or .pqa-old-*, 3.1's)

make pqa-audit-sheet    → the blind audit sheet, gitignored            §3.2
make pqa-answerability EPQA=<dir>  → agreement with ePQA's labels      §3.1
```

`iter_interim` hashes all six files before it yields, on each pass. Pass 1 reads only titles. Two
passes cost about twice `pqa-build`'s read time (≈ 41 s each) and keep only one leaf's title counts
and the eligible products in memory.

Before any of this, **the builder gains one flag** (§5): the interim does not say which products
had records that disagree. It keeps only the count (`prose_conflicts`, `build_pqa.py:241`).

## 2. The rule

Every constant is pinned in `select_pqa.py` and copied into the manifest's `rule` block. **probe**
constants are copied (not imported: `probe.py` is scratch in a trail) from
`docs/work/2026-10-03-pqa-category-choice/probe.py`, and a test loads that file by path and asserts
each `.pattern`, `.flags` and value is equal (T12). **new** constants are set here, before any run.
The department of each leaf comes from `build_pqa.LEAVES`, never a second table.

**The whole rule, the seed, both answerability rules, the audit design and the short-leaf fallback
are pre-registered:** they are committed (plan step 9) before any live run and before ePQA is
fetched, so no number this item produces could have shaped them. A later change to a **new**
constant or a pin needs an `approvals.md` line.

| Constant | Value | Origin |
| :--- | :--- | :--- |
| `STOP`, `content_tokens` | the probe's stop list; `[a-z0-9]+`, lower case, length > 1 | probe |
| `DYNAMIC_Q`, `CARRIER_Q`, `POLICY_Q`, `WARRANTY_TERM` | the probe's regexes, unchanged | probe |
| `ND_LO`, `ND_HI` | 0.45, 0.99 (content-word Jaccard; identical token sets excluded) | probe |
| `CAP_LO`, `CAP_HI` | 5, 50 kept questions per product | probe |
| `MIN_BULLETS` | 3 non-empty bullets | probe (F17) |
| `PAIR_CAP` | 100 questions, for the unfiltered re-ask counts only | probe |
| `COVERAGE` | 0.5 | **new** |
| `GENERIC_DF` | 0.10: a token is generic in a leaf if it is in ≥ 10 % of that leaf's titles | **new** (review H1) |
| `MIN_ANSWERABLE` | 5 answerable spec questions | **new** (the probe's floor of 5, moved onto answerable questions) |
| `QUOTA` | 38 per department; 19 + 19 where a department has two leaves | **new** (ADR-002's "~38") |
| `SEED` | `"v1-item-3.2"` | **new** |
| `AUDIT` | 15 answerable + 10 unanswerable spec questions per department, 100 in all | **new** (review H1) |

`prose(p)` means `" ".join(p["bullets"] + [p["product_description"]])` with **no strip**, as
`example_product.py:31-32` joins it (the interim keeps the raw strings). One definition, used in
§2.2 and §2.6 (review M5).

### 2.1 Tagging a question

The first step that matches decides.

1. `DYNAMIC_Q` matches → **dropped** (price, stock). It never reaches the pool.
2. `CARRIER_Q` matches → **dropped** (carrier, unlock, SIM).
3. `POLICY_Q` matches → **`policy`**, with `policy_kinds` ⊆ {`return`, `warranty`}. Answered by the
   authored documents of 3.3, so not tested against the product.
4. Otherwise a **`spec`** question, tagged `answerable` true or false by **rule R2**:

   ```
   R      = content_tokens(item_name + " " + brand_name + " " + prose(p))
   G_leaf = { t : t is in content_tokens(title) for ≥ GENERIC_DF of the leaf's products }
   Q      = content_tokens(question_text)
   Q'     = Q − G_leaf
   R2:  answerable  ⇔  Q' ≠ ∅  ∧  |Q' ∩ R| / |Q'| ≥ COVERAGE
   R1:  the same with Q in place of Q'          (reported beside R2, never used to select)
   ```

   `R` is the text the record will embed (§2.5) minus its `Category:` line, so the department word
   cannot make a question answerable. `G_leaf` comes from **all** products of the leaf (pass 1).

**Why R2, decided before any data (review H1).** Under R1, "How tall is the chair?" scores 1/2 on
"chair" alone and passes against a record with no height. That failure is silent: a too-generous
rule fills every quota and trips no stop, and it hits short furniture, TV and headphone questions
hardest, where ePQA has almost no labels. R2 removes the leaf's product nouns first, so "chair" no
longer counts. **R2's own failure is too strict,** and it is loud, not silent: "Is it wireless?"
loses "wireless" if most headphone titles carry it, the question becomes not answerable, and the
pool shrinks (the quota stop catches a pool that shrinks too far). Both rules are reported.

**What both rules get wrong, stated before they are measured:** synonyms and split units fail
("waterproof" against "water resistant"; "8gb" against "8 GB", because "8" is one character and is
dropped); and presence is not an answer (a record that says "bluetooth" does not answer "does the
bluetooth work with my car?"). §3 measures them.

**A limitation on C1, recorded now (impact).** The rule keeps questions whose words are in the
record. Retrieval finds those records more easily and `S_lex` scores their answers higher, so the
workload leans toward the cases the support gate admits. This goes into `data-card.md` beside the
rule and into the thesis's threats to validity.

**The tokenizer must not label strata (review M3).** It drops one-character tokens, so "works with
Windows 7?" and "…Windows 8?" have the same token set, and so do "iPhone 6 or 7" and "7 or 8". These
are natural B-within traps that look like exact repeats here. The pool's schema says so, for 3.4.

### 2.2 Product filters (the funnel)

Each product is tested in this order; the first failure is counted at that step, per leaf. The
order changes where a product is counted, never whether it is eligible.

| Step | A product passes when |
| :--- | :--- |
| `titled` | `item_name.strip()` is not empty |
| `bullets` | ≥ `MIN_BULLETS` entries of `bullets` are non-empty after strip |
| `no_warranty_term` | `WARRANTY_TERM` matches neither `item_name` nor `prose(p)` (review L2: the title is embedded too) |
| `consistent` | `line["fields_conflict"]` is false — read directly, never `.get(…, False)` (§5, review L4) |
| `cap` | `CAP_LO` ≤ kept questions ≤ `CAP_HI` (kept = policy + spec) |
| `answerable` | ≥ `MIN_ANSWERABLE` spec questions answerable under R2 |
| `pair` | ≥ 1 pair of R2-answerable spec questions with `ND_LO` ≤ Jaccard ≤ `ND_HI` and different token sets |

**The `pair` step is stricter than the probe's** (spec open question 8): the probe took a pair among
all kept questions. A pair of questions the record cannot answer is safe reuse by construction
(F17), so it does not count. ADR-002's pool sizes stay true only of the probe's rule, and §2.6 checks
exactly that. The review notes this adds to §2.4's prose-length bias and to the short-leaf risk.

### 2.3 The draw, and a short leaf

For each leaf, the eligible asins are sorted by `sha256(f"{SEED}:{asin}")` (hex, ascending) and the
first `QUOTA[leaf]` are taken. It is the same on every Python version, needs no sorted-set step, and
removing one product does not reorder the others.

If a leaf has fewer eligible products than its quota, the run **exits 2** and prints every leaf's
pool and quota. It never changes the rule by itself. **The fallback, pre-registered (review L1)** —
applied only by the author, one step at a time, each step an `approvals.md` line and part of
ADR-011, with the first run's funnel kept beside the new one in `evidence/`:

1. In a two-leaf department, give the short leaf's shortfall to its sibling leaf.
2. Then the `pair` step uses all kept questions (the probe's rule), for every leaf.
3. Beyond that, nothing is pre-registered: the author decides, and it is reported as post hoc.

**The seed and the answerability rule are never changed** to fill a quota or to pass G1 at 3.6:
that would be tuning.

### 2.4 What is reported

Printed and written to the manifest, per leaf and per department:

- **The funnel:** products in, and the count removed at each step of §2.2; and questions dropped
  as dynamic and as carrier (non-phone leaves should drop almost none as carrier, review L3).
- **The realised questions-per-product distribution** of the selected products, for kept, policy,
  answerable spec and unanswerable spec questions: min, median, p90, max (`p90 = sorted[int(0.9 ×
  (n − 1))]`, the probe's index rule), and a histogram in the buckets 5–9, 10–19, 20–29, 30–39,
  40–50. This is the Done-when's "distribution".
- **The answerable share** of spec questions under R1 and under R2, per leaf, over all products and
  over the selected ones, next to ePQA's 22.9 % (an upper bound for a PQA record); and the share of
  R2-answerable tags whose covered tokens come **only from the title** (review H1).
- **Prose length and chunk count** of the selected products against the probe pool (§2.6), per leaf:
  median characters of `product_to_text(record)` and the chunk count from `SentenceSplitter` at the
  frozen 256 / 40. No model is loaded. `rag` is imported inside this one function (review M4).
- **Re-asks, filtered beside unfiltered** (2026-10-03 review, finding 5), in **two parts**: exact
  repeats (identical token sets) and near-duplicates (the band), each as questions and clusters,
  with clusters from union-find over both; plus the count of exact repeats whose **raw digit
  strings differ** (review M3: these are value flips, not re-asks). *Unfiltered* = every product of
  the leaf with ≥ 2 kept questions, first `PAIR_CAP` in file order. *Filtered* = the selected
  products, all kept questions. The rate is pooled, `1 − Σ clusters / Σ questions`. It is comparable
  with neither `data-card.md` §3's "5–14 per 100" (embeddings, cosine ≥ 0.85, products with ≥ 100
  questions) nor F21 (per-product medians) (review L5).

### 2.5 Output files

**Product record**, `data/v1-draft/products/product-{department}-{asin.lower()}.json`:

```json
{ "doc_id": "product-phones-b07xyz1234",
  "title": "<item_name, stripped>",
  "category": "phones",
  "specs": { "Feature 1": "...", "Feature 3": "...", "Description": "...", "Brand": "..." } }
```

- `specs` keys in this fixed order: `Feature n` for each non-empty bullet (stripped), numbered by
  its source slot, so gaps are possible; then `Description`; then `Brand`, each if non-empty. This
  is the 2026-10-03 example's shape. **`sort_keys` is not used for the record**: `product_to_text`
  renders `specs` in dict order, and the order is part of the embedded text. All other output is
  written with sorted keys.
- No `leaf` or `source_category` key, and no value equal to a leaf id. Not a substring test:
  `chairs` is an ordinary word in titles (impact F2).
- The asin must match `^[A-Z0-9]{10}$` **before** it is lower-cased, so lower-casing cannot merge two
  asins. The writer asserts every `doc_id` is unique.

**Question pool**, `data/v1-draft/question-pool.jsonl`, one line per kept question of a selected
product, sorted by `(doc_id, line_no)`:

```json
{ "doc_id": "...", "department": "phones", "leaf": "unlocked_cell_phones",
  "line_no": 1234, "question_id": "...", "question_text": "...", "question_type": "yes-no",
  "answer_aggregated": "yes", "answers": ["..."],
  "tag": "spec", "answerable": true, "answerable_r1": true, "policy_kinds": [],
  "q_tokens": 3, "covered": 2 }
```

- `leaf` is here and only here: the pool is never ingested.
- `answers` stays for 3.4's B-within labelling (3.1 review M3). `q_tokens` and `covered` (for R2)
  are integers kept for sensitivity analysis only.
- **Unanswerable spec questions stay in the pool, tagged** (review H2, spec open question 9). The
  proposal handed to 3.4 as a constraint: they form **a separate stratum, reported apart, never in
  the headline**; the headline covers answerable spec questions and policy questions.
- The schema says: the `content_tokens` tokenizer must not be used to label strata (§2.1).

**Selection manifest**, `data/pqa-selection.json`, tracked:

```
stage: "3.2-selection" · manifest_version: 1 · note (not the v1 snapshot digest; that is 3.6)
consumed: { pqa_manifest_sha256 }
selector_sha256
rule: { every constant of §2, the regex source strings, SEED, the fallback steps applied (none) }
generic: { leaf: { size, sha256 of the sorted token list } }
funnel, probe_pools, distribution, answerable_share, prose, reask   (as in §2.4)
outputs: { products: 152, products_sha256, question_pool_lines, question_pool_sha256 }
```

`products_sha256` is the sha256 of the sorted `(file name, file sha256)` pairs. The allow-list (T6)
admits digests, field, leaf and department names, the regex source strings, the seed and fixed
labels: **no asin, no `doc_id`, no question text, no title word.**

**The asin rule, stated once (impact).** Asins may appear in `doc_id`s, gitignored files, Redis and
`raw/` logs: an asin is Amazon's public id, not PQA text. **Tracked machine-readable files hold counts
and digests only.** Printed output and evidence files name counts, never questions. The generic token
lists are printed to the terminal and kept in a gitignored file, not in the trail.

**The sanctioned reader, `iter_selection()` (review M6).** It loads `pqa-selection.json`, hashes every
product file and the pool against it, and only then yields. 3.4 and 3.6 read the drafts through it,
as 3.2 reads the interim through `iter_interim`.

### 2.6 The probe check (impact F4, review M5)

On pass 2, each product is also counted against the probe's own two pool rules, which ran on the
same bytes on 2026-10-03:

| Pool | Rule | Source of the pin |
| :--- | :--- | :--- |
| `capped` | 5–50 kept questions (dynamic and carrier dropped) and ≥ 1 near-duplicate pair among all kept | `probe_results.json` `n_capped_nocarrier`, a recorded program output |
| `adr002` | `capped`, plus ≥ 3 bullets and no `WARRANTY_TERM` in `prose(p)` (title not tested) | ADR-002's table; prose only, so **re-derived first** (plan step 3) |

| Leaf | phones | laptops | TVs | headphones | chairs | desks |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `capped` | 2,260 | 1,742 | 350 | 565 | 914 | 410 |
| `adr002` | 1,811 | 1,312 | 302 | 399 | 796 | 339 |

A difference exits 2 and names the leaf and the pool. Two pins narrow a mismatch: if `capped` holds
and `adr002` does not, the bullets or warranty step differs. **Before any code**, plan step 3 runs
`example_product.py` unchanged on the six raw leaves and records its "candidates qualifying" count,
so the `adr002` pins rest on a program output too. A pin changed after that needs an `approvals.md`
line.

## 3. Checking the answerability rule

Two checks, pre-registered now, **descriptive only**: no threshold decides anything automatically.
The numbers go to the author before the `data-card.md` edit. **A rule written after either check is
seen is labelled in-sample** and judged on a fresh audit sample, never on ePQA's 194 (review M2).

### 3.1 Against ePQA's labels

`experiments/scripts/answerability_check.py`, `make pqa-answerability EPQA=<dir>`.

- **Input:** the three ePQA CSVs, sha256-pinned (§6.7), and the interim through `iter_interim`.
- **The reproduction pin (review M1):** PQA **lines** whose `(asin, question_text.strip().lower())`
  matches an ePQA question, counted as `epqa_probe.py:75-81` did, must be **194**: 143 / 5 / 21 / 19 /
  2 / 4 in `LEAVES` order. A different count exits 2.
- **The scored unit:** each distinct `(asin, normalised text)` among them, counted and reported
  beside the line count.
- **ePQA's label, fixed now.** A unit is *answerable* when **any** ePQA row with that key has label
  `2` from a counted source; `0` and `1` never make it answerable. *Primary:* sources `bullet` and
  `description`, which a PQA record also has. *Secondary:* add `attribute`, `attributes`, `json`.
  *Tertiary (review M7):* only the label-2 candidates from `bullet` / `description` whose content
  tokens are ≥ 0.8 contained in the PQA record's `R`, i.e. the evidence ePQA saw is really in our
  record.
- **The rule's label:** `tag()` from `select_pqa.py`, imported, run on the matched question against
  its own interim product, for R2 and R1. Policy and dropped questions are counted apart.
- **Reported:** the 2 × 2 table, agreement, Cohen's κ, precision and recall, each with a 95 % Wilson
  interval, **pooled over the six leaves**; per-leaf counts **without** intervals.
- Output: printed, and `evidence/answerability.json` (counts only) in this trail.

### 3.2 A blind audit of the selected pool (review H1)

The only check on the population the study uses, and the only one that sees furniture.

- **The sample:** per department, the 15 R2-answerable and the 10 R2-unanswerable spec questions of
  the selected products with the lowest `sha256(f"{SEED}:audit:{doc_id}:{line_no}")`, 100 in all.
- **The sheet:** `make pqa-audit-sheet` writes the 100, shuffled by that hash, each with its product
  record's text, and **without** the tag, to `data/v1-draft/audit/sheet.csv` (gitignored). The
  author marks each *answerable from this text: yes / no*. About one hour.
- **Scored by** `make pqa-audit-score`: R2's precision (over the 60 tagged answerable) and recall
  (over the 100), with Wilson intervals, per department as counts and pooled with intervals. Counts
  only into `evidence/audit.json`.
- The auditor is the author, not a model: a model label would be a third rule, not a check.

## 4. Tests

`experiments/tests/test_select_pqa.py` (and `test_answerability_check.py`). Fixtures are built in
`tmp_path` with a fake interim and a fake 3.1 manifest written through `build_pqa`'s own writer, so
the hashes are real. Nothing writes outside `tmp_path`.

| # | Test |
| :-: | :--- |
| T1 | A `product-x.json` in the fake `v1-draft/` → exit 2, no output, no temp dir |
| T2 | An interim file changed after its manifest → exit 2 before anything is written |
| T3 | Two subprocess runs, `PYTHONHASHSEED=0` and `=1` → byte-identical outputs and manifest |
| T4 | `doc_id` prefix, `doc_id` = file stem, `category` in the four, no `leaf` / `source_category` key, no value equal to a leaf id; a lower-case or 9-character asin is refused; `rag.ingest.load_records(out_dir)` accepts the output (imported in the test only) |
| T5 | `specs` order: bullets 1, 3, 5 + description + brand render through `product_to_text` to the exact expected text |
| T6 | Manifest allow-list on every string value |
| T7 | Tag order: a price question that says "warranty" is dropped, not policy |
| T8 | R2 edges: coverage exactly 0.5 passes, just below fails; `Q' = ∅` is not answerable; a generic token does not count; the `Category` word does not count; R1 differs from R2 on "How tall is the chair?" |
| T9 | Each funnel step on both sides of its edge; the funnel adds up to products in; a title warranty term fails `no_warranty_term` |
| T10 | Quota exact per leaf; a short pool exits 2 and names the leaf |
| T11 | Removing one eligible product does not change the order of the others |
| T12 | Every **probe** constant equals `probe.py`'s, read from that file |
| T13 | A dynamic or carrier question never appears in the pool |
| T14 | Re-ask counts on a hand-made product: exact and near-duplicate parts and the digit-flip count equal hand counts ("Windows 7" / "Windows 8" is a digit flip) |
| T15 | `answerability_check`: the line count and the unit count, all three ePQA labels, "a 1 and a 2 → answerable, only 1s → not", the 2 × 2 table; a line count off its pin exits 2 |
| T16 | A fixture whose `capped` or `adr002` count misses its pin exits 2 before the draw, naming the pool |
| T17 | An interim file or the manifest changed **during** the pass exits 2 before anything is written |
| T18 | `.pqa-select-*` is gone after a success and after each exit 2; a `.pqa-build-*` directory beside it is untouched |
| T19 | `iter_selection` raises before yielding when a product file or the pool is changed, missing or extra; a failed swap restores the old pair |
| T20 | A line without `fields_conflict` raises (it is never read with a default) |
| T21 | The audit sample is 15 + 10 per department, carries no tag column, and the same seed gives the same sheet |

The builder change (§5) adds tests to `test_build_pqa.py` and keeps all 103 green.

## 5. The builder change (3.1 owns the code, 3.2 owns the schema)

`parse_leaf` already builds the `conflicted` set (`build_pqa.py:309`). It sets
`fields_conflict = asin in conflicted` **on the product dict itself**, after the loop and before
`write_interim`. It must be in that dict, not only in `product_line`: `_digest` (`:551`) and the
round-trip test (`test_build_pqa.py:1259`) both compare against the dict, so a flag added only in
`product_line` fails loudly (review L4).

- Stop 3a / 3b pins do not change: no record, question or prose changes.
- New check: `prose_conflicts` equals the number of products with the flag.
- `MANIFEST_VERSION` → 2; `load_manifest` refuses version 1, so `select_pqa` cannot read a stale
  interim. The manifest hash `bf0feb48…` is replaced; nothing outside the 3.1 trail pins it (the
  review ran `git grep`).

## 6. Decisions, with reasons (the spec's open questions)

1. **A lexical rule, R2 (with R1 reported), plus a blind audit.** Deterministic, no model, seconds
   over 1.2 M questions, testable. An LLM label over ~10⁵ questions takes hours locally and either
   couples the filter to the generator or sends PQA text to an outside API; if one were chosen it
   must be neither Qwen nor the Phase 5 judge (impact). Hand curation of every question is many hours
   and cannot be re-run; a 100-question audit is one hour and checks the rule instead of replacing it.
   *If an LLM label:* §2.1 step 4 and §3 change.
2. **Hash rank, not thickest first.** Thickest first pushes products to the cap, raises `K` (≈ 1.5 h of
   reference generation per 1,000 distinct queries) and makes the sample unrepresentative. *If
   thickest:* §2.3 only.
3. **Exclude the 78.** Two versions of a product's prose give the support gate no single truth. Cost:
   §5. *If keep-first:* drop §5 and `consistent`; then not even the number affected can be counted.
4. **Exclude warranty-term products, title included.** Their text can contradict 3.3's warranty
   documents. *If keep:* 3.3 scopes its warranty documents around them.
5. **19 + 19.** Proportional would give TVs 16 / headphones 22 and chairs 27 / desks 11. *If
   proportional:* `QUOTA` only.
6. **`product-{department}-{asin}`.** Stable across a re-draw, traceable, legal under §C. An ordinal
   would give one id to a different product after a re-draw, which §C forbids. The form reaches every
   chunk id, Tier-2 namespace and `dep:` key from 3.6 on (impact F13).
7. **Download ePQA** with `make epqa-fetch` (`curl`, a pinned commit, into `data/raw/epqa/`, which is
   ignored; `data/epqa/` is not). The three sha256 are pinned on the first fetch; an LFS pointer fails
   the pin. The fetch is logged **after** the rule commit (review L6: the commit order alone proves
   when the rule was written, not when the labels were first seen).
8. **The `pair` step counts answerable questions only** (§2.2). *If all kept:* `pair` uses all kept
   questions, and fallback step 2 is already spent.
9. **Unanswerable spec questions: a separate stratum, never in the headline** (review H2). Dropping
   them would remove unanswerable paraphrase pairs, which are safe reuse that containment refuses when
   retrieval wanders, and that would quietly favour the headline. *If dropped:* the pool still keeps
   them tagged; 3.4 drops them, and `data-card.md` says so.
10. **The short-leaf fallback** of §2.3, pre-registered.
11. **ADR-011 (data),** written at the end with the live numbers: the frozen rule, the seed, R2, the
    two new filters, any fallback step applied.

## 7. Failure modes

| What goes wrong | What catches it |
| :--- | :--- |
| A field read under the wrong name, so every product fails a step | The probe pins (§2.6) exit 2 before the draw |
| The copied filters differ from the probe in a small way | Two pins per leaf; `example_product.py` re-run first |
| The answerability rule is too generous and fills every quota quietly | R2's generic set; the answerable share beside ePQA's 22.9 %; the title-only share; the blind audit |
| The leaf reaches `category` or the embedded text | T4 |
| The draw depends on set or dict order | Hash rank over sorted asins; T3 |
| A stale or edited interim, or one changed during the pass | `iter_interim`; the re-check after the pass; `MANIFEST_VERSION` 2; T2, T17 |
| Products and pool out of step after a crash or a hand edit | Swap with restore; `iter_selection`; T19 |
| Old wrong-dataset `product-*.json` in `data/v1-draft/` | The guard; T1 |
| A rule edited after its agreement is seen | Pre-registration; the fetch logged after the rule commit; any later rule labelled in-sample |
| The seed changed to get a nicer draw or to pass G1 | `SEED` pinned; §2.3 forbids it; `approvals.md` |
| `sort_keys` reorders `specs` and changes the embedded text | T5 |
| A dynamic question reaches the workload through the pool | T13 |
| A value flip counted as a re-ask, or labelled stratum A by 3.4 | Digit-flip count (§2.4); the pool schema warns 3.4 |
| A missing `fields_conflict` read as false | No default; T20 |
| Two products get one `doc_id` | The asin pattern before lower-casing; the uniqueness assert |

## 8. What I do not know yet

1. **Whether each leaf fills its quota** under R2 and the stricter `pair` step. TVs had 302 before
   them and need 19; desks have a median of 17 kept questions. The first live run answers it.
2. **How good R2 is.** ePQA's 194 are 143 phones, and 2 chairs and 4 desks; its labels are per
   candidate snippet from its own crawl, so "no label 2" means "no snippet answered", not "the record
   lacks it" (review M7). The audit is the real check, and it is 100 questions.
3. **How much R2 over-corrects** — how many truly answerable questions lose their key word to
   `G_leaf`. The audit's recall measures it.
4. **The ePQA files:** URLs at a pinned commit, LFS or not, their sha256.
5. **Whether the `adr002` pins reproduce.** Expected (the review compared `parse_leaf` with
   `example_product.py` field by field), but no saved output holds those six numbers yet.
6. **How far the selection leans toward long-prose products** (review M4). Coverage grows with `R`;
   §2.4 reports prose length and chunk count against the probe pool.
7. **How many policy questions the selected products carry** per department, and how many are
   mis-tagged ("return key" on laptops; no shipping tag exists) — for 3.3 and 3.4 (review L3).
8. **Memory and time** of two passes: expected about twice `pqa-build`'s read (≈ 586 MiB peak).
   Re-running `example_product.py` on the 821 MB phone leaf holds every record in memory, likely
   several GB: check pressure first.
