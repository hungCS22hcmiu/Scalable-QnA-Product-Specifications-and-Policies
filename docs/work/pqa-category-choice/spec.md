**Question:** Which three to five Amazon-PQA categories can supply `v1`'s ~150 products such that **(a)** each chosen category holds **≥ 50 products that carry ≥ 5 questions *and* at least one near-duplicate question pair**, and **(b)** the chosen set spans **≥ 2 distinct return windows and ≥ 2 distinct warranty windows** as published by real retailers or manufacturers?

# Investigation — PQA category choice

**Scope:** S · **Opened:** 2026-10-03 · **Kind:** investigation — writes no source, sets no `READY_TO_IMPLEMENT`
**Phase note:** opened while the banner reads **Phase 1**. This is Phase 3 item 3.2 groundwork, taken
out of order at the author's request (2026-10-03). It changes no code and freezes nothing.

## Why this question

The 2026-09-21 PQA probe left three calls to the human. Two were decided and sit in
`decisions.md` → *Inherited state* (adopt PQA; redistribution stays closed). The third —
**which categories** — was never answered and is `data-card.md` §1's open `TODO`.

The choice has to satisfy two constraints that are independent of each other
(`data-card.md` §1, last bullet), and the earlier shortlist was assembled against **(b) only** —
nobody measured (a) for it:

| | Constraint | Source | Why it binds |
| :---: | :--- | :--- | :--- |
| **(a)** | Thick in questions per product, with genuine paraphrase clusters | `data-card.md` §1 "select into the thick tail" | A single-question product yields no stratum A or C pair at all |
| **(b)** | Return **and** warranty windows that genuinely differ across categories | `data-card.md` §2 requirement 2 | One global window makes every policy question retrieve the same chunk; overlap ≈ 1 everywhere and C1 is null by construction of the corpus |

## Where the thresholds come from

- **≥ 50 products per category** — `~150 products across ≥ 3 categories` (`data-card.md` §1) is
  ≥ 50 per category at the minimum category count. Derived, not chosen.
- **≥ 5 questions** — the cut the 2026-09-21 probe reported against; kept so the numbers compare.
- **Near-duplicate pair** — the 2026-09-21 probe's definition, reimplemented: content-word Jaccard
  in **[0.45, 0.99]**, exact repeats excluded. The original script was lost with its scratchpad, so
  `inkjet_printers` is re-run as a **reproduction check** against the recorded 43.6 %.
- **≥ 2 distinct windows of each kind** — the minimum at which "differ across categories" is true.
  No higher floor is set: there is no evidence to derive one from.

## Method

1. List the category files in `s3://amazon-pqa` over plain HTTPS.
2. Shortlist candidates on constraint (b) — categories whose real-world return and warranty terms
   plausibly differ — then measure every one of them on (a), which is the step the earlier
   shortlist skipped.
3. Download each candidate to the scratchpad (never into `data/`), hash it, and run one probe
   script over all of them. Per category: products, questions, questions-per-product distribution,
   products with ≥ 5 questions, share and count of those with ≥ 1 near-duplicate pair, natural
   `B-within` *candidates* (near-duplicate yes/no pairs whose `answer_aggregated` disagrees),
   rate of questions that already mention warranty / return (the stratum D seam), and product
   prose length.
4. Ground constraint (b) in published retailer and manufacturer policy pages, cited.

**Conditions on every number below.** Source bytes are Amazon-PQA as downloaded on the date
stated; nothing is ingested, embedded or retrieved; no Ollama, no gateway, no corpus gate. These
are **dataset-selection statistics, not results** — none is a measurement of the system, and none
is citable as one. Near-duplicate detection is **lexical**, so it finds stratum A readily and
undercounts stratum C (different wording, same grounding), which only the frozen embedding model
can see.

## Findings

*(recorded as they come in, including the ones that contradict the expectation)*

### F1 — The bucket holds 100 category files; ten were shortlisted on constraint (b)

`s3://amazon-pqa` listed over HTTPS on 2026-10-03: 100 `amazon_pqa_<category>.json` files
(68 MB – 821 MB), plus the 2.27 GB archive and `readme.txt`. Shortlisted for plausibly distinct
return/warranty terms, before any thickness number was seen: `inkjet_printers` (also the
reproduction check), `chairs`, `mattresses`, `home_office_desks`, `bed_frames`, `led_&_lcd_tvs`,
`video_projectors`, `quadcopters_&_multirotors`, `carrier_cell_phones`, `over-ear_headphones`.
Downloaded to the session scratchpad, never into `data/`.

### F2 — The probe reproduces the 2026-09-21 numbers

Rewritten from scratch, because the original script was lost. On `inkjet_printers`
(sha256 `2b1ad4fc…aa43d90a`, 134,353,943 bytes): 1,288 products, 92,070 questions, 0 unparsed
records, mean 71.5 questions per product, 82.5 % with ≥ 2, 63.7 % with ≥ 5 — all identical to the
record — and **43.5 %** of multi-question products with a near-duplicate pair against the recorded
**43.6 %**. Median shows 8.5 instead of 8 only because `statistics.median` averages the two middle
values of an even-length list. **The near-duplicate definition is reproduced closely enough to
compare categories on it.**

### F3 — ✗ Disproved: opposite community answers do not find B-within pairs

The first version counted near-duplicate yes/no pairs whose `answer_aggregated` disagreed as
"natural B-within candidates". Every example it returned was **the same question answered
differently by different shoppers**: *"Is this printer wireless?"* → `no` against *"is this
wireless"* → `yes`. That is **community-answer noise**, not a condition flip, and the metric was
relabelled `pct_nd_answer_disagree`. It is still worth keeping: it measures directly the claim in
`data-card.md` §3 that PQA's answers are not ground truth (4.0 % of near-duplicate yes/no pairs in
`inkjet_printers` contradict each other).

A separate detector replaced it: pairs at content-word Jaccard ≥ 0.30 that differ by one or two
tokens on each side, with a numeric token on both sides of the difference. It returns the shape
`data-card.md` §3 describes — *"print on 11X14 paper?"* / *"print on 11X17 paper?"*,
*"compatible with windows 10?"* / *"…windows 8?"* — on **82** `inkjet_printers` products. These are
**candidates**, not labelled pairs: whether the answers actually differ is decided at workload
build, not here.

### F4 — Product prose already makes warranty claims

The first record read carries `bullet_point5: "Backed by a 1-year warranty"`. In
`inkjet_printers`, **10.6 %** of products state a warranty term in their own prose. This was not
anticipated, and it bears on the authored policy corpus: a warranty question about such a product
will retrieve a **product** chunk asserting one term and a **policy** chunk asserting the
category's term. If the two disagree, the reference answer `LLM(retrieve(q), q)` is grounded in
contradictory evidence. Measured per category below.

### F5 — Return windows differ by category at every major retailer checked (primary sources)

Fetched 2026-10-03 from the retailers' own pages. Where a secondary summary disagreed with the
primary page, the primary is recorded and the disagreement noted.

| Retailer (source) | Default | Category-specific windows | Opened-vs-unopened conditions |
| :--- | :--- | :--- | :--- |
| **Amazon** — help node `GKM69DUUYKQWKWX7` | **30 days** | Apple **15**; **mattresses (excl. crib) 90**; Renewed 90 | 100 % restocking on opened software / video games |
| **Best Buy** — return & exchange policy | **15 days** (members 60) | Activatable devices **14** | **15 % fee on opened** drones, digital cameras, camcorders, **projectors**, projector screens; **$45 on opened** activatable devices; none if unopened |
| **Target** — help article *Returns* | **90 days** (unopened, new) | **Electronics 30**; Apple/Beats **14**; mobile phones **14**; own brands 365 | Up to **$35** restocking on **opened** mobile phones; none if unopened |
| Walmart — *secondary only*; the primary page served a CAPTCHA | 90 days | Electronics (TVs, laptops, drones…) 30; wireless phones 14 | Opened phones exchange-only |

Secondary sources contradicted primary twice: one summary gave Target's Apple window as 15 days
(primary: **14**), another gave Amazon's mattress window as 100 days (primary: **90**). Neither
secondary figure is used.

### F6 — Warranty terms differ by category far more than return windows do (secondary sources)

Manufacturer warranty pages were not fetched individually; these figures are **secondary** and
need a primary citation before any of them is written into an authored policy document.

| Category | Typical manufacturer warranty | Within-product split (natural opposing condition) |
| :--- | :--- | :--- |
| Inkjet printers | **1 year** limited (HP) | — |
| Video projectors | **2 years** (Epson) | **Lamp: 90 days** against the body's 2 years |
| Drones | **3–12 months by component** (DJI) | Aircraft vs battery vs gimbal |
| TVs | **1 year** parts and labour (industry norm) | — |
| Office chairs | **12 years** (Herman Miller); **lifetime** frame / 12-year mechanism (Steelcase) | Frame vs mechanism vs fabric |
| Mattresses | **10 years** + **100-night trial** (Casper, Tuft & Needle) | Trial window vs warranty term |

**IKEA** (primary, *Return policy* page, fetched 2026-10-03) adds the opposing condition for
furniture directly: **365 days unopened, 180 days opened**. Wayfair's page returned HTTP 429 and
is not used.

**What F5 and F6 settle about constraint (b):** every candidate pair of {electronics, furniture,
mattresses} differs on *both* axes in published policy, so (b) does not discriminate between
those families — it discriminates *against* picking three categories from one family (three
electronics categories share Target's 30 days and a 1-year warranty). Constraint (a) has to do
the ranking.

### F7 — `chairs` clears (a) by volume, not by clustering — and its flips are mostly price

`chairs` (sha256 recorded in the results table below): 19,193 products, median **2** questions,
24.3 % with ≥ 5 — **4,665** products, against **4,664** in the 2026-09-21 record; the one-product
difference is unexplained and too small to matter. But only **11.0 %** of its multi-question
products carry a near-duplicate pair, against **43.5 %** in `inkjet_printers`: chairs questions are
spread thin across many products rather than clustered on a few. It still clears the ≥ 50 floor
twenty times over (1,039 usable after the dynamic filter of F8).

Its value-flip candidates (F3) are a different kind from printers'. Printers flip on **paper size
and OS version** — specification slots. Chairs flip mostly on **price** — *"how many chairs for
69.99"* / *"…for $119.99"* — and on weight limits and door widths. The price flips are **dynamic
content** and can never enter the workload.

### F8 — Dynamic questions are a small tax, not a constraint

Price and stock questions must never enter the cache (CLAUDE.md, "cache only the stable slice"),
so the probe re-derives the usable pool with them removed first (`n_usable_static`). An indicator
regex, not a classifier: `$`+digit, *price*, *cost*, *how much is/for*, *in/out of stock*,
*on sale*, *discount*, *coupon*. Dynamic share: **1.4 %** of `inkjet_printers` questions (usable
pool unchanged at 458), **2.1 %** of `chairs` (1,066 → 1,039). At these rates the filter never
decides a category.

### F9 — ✗ Disproved: "PQA contains no policy questions at all" (`data-card.md` §3)

`data-card.md` §3 states that PQA *"contains no policy questions at all"* and that the policy half
of the workload must therefore be authored. **Measured, it does contain them** — hundreds per
category:

| | warranty questions | return questions | products asking **both** |
| :--- | ---: | ---: | ---: |
| `inkjet_printers` | 509 | 260 | 84 |
| `chairs` | 917 | 1,323 | 187 |
| `home_office_desks` | 204 | 561 | 47 |

Counts are regex matches (`warrant(y|ies|ee)`; `return(ed|s|ing)?|refund(ed)?|restock(ing)?`), so
their precision was checked by reading a seeded random sample (seed `20261003`; labelled by
Claude during this investigation, **not human-verified**):

- **Warranty matches are almost all genuine policy questions** — `chairs` 8/8, `inkjet_printers`
  7/8 (the eighth is a defect complaint). *"how long is the warranty?"*, *"Is there a warranty for
  this chair?"*, *"Does this come with a mechanism warranty?"*
- **Return matches are mixed and category-dependent.** `chairs` 9/10 genuine — *"What is the return
  policy?"*, *"Are there free returns?"*. `inkjet_printers` about 5/10 — the rest are order status
  (*"My order was cancelled, I have yet to receive my refund"* — dynamic, never cacheable),
  support complaints, and false positives (*"print avery return address labels"*).

**What survives of the data card's claim.** It is right that no *store policy document* exists to
ground these questions: shoppers asked about Amazon's or the seller's terms, and other shoppers
answered. In `v1` the grounding would still be the authored per-category policy corpus. What is
wrong is that the **questions** must be authored. Their *wording* is available as real traffic.

**Why it matters.** Three things the data card currently treats as author-constructed can be
partly *sampled* instead:

1. **Policy-half wording.** Real phrasings, including elliptical ones (*"warranty"*, as a whole
   question), which `data-card.md` §3's rewrite rule then has to make self-contained.
2. **Natural opposing conditions.** *"What do I need to return this item **unused**?"* names a
   condition unprompted — G5's subject matter, arriving as traffic.
3. **Policy-dimension `B-within` pairs.** `data-card.md` §2 says B-within pairs are *built* as
   same-product pairs differing in policy dimension — *"how long is the **warranty** period"* vs
   *"how long is the **return** period"*. **84 / 187 / 47 products** already carry both questions.
   The same objection F3's numeric flips weaken — that the measured residual reflects how the
   author built the traps — is weakened here too, on the stratum that matters most.

### F10 — All eight measured categories clear constraint (a), by at least 9×

Probe: `probe.py` in this trail (results in `probe_results.json`). Every file's byte count matches
the bucket listing; every file parses with **zero** unparsed records except
`carrier_cell_phones`, whose one is an empty `question_text` **in the source** (record 112,456,
`question_id TxTXCYTFWD4PDH`) — a builder must skip isolated empties while still asserting a
non-zero parse rate. `mattresses` was resumed mid-download and parses clean.

"Usable" = ≥ 5 questions after removing dynamic ones (F8) **and** ≥ 1 near-duplicate pair.
"Capped" = the same, restricted to products with **5–50** questions, so that `K` stays bounded
(`inkjet_printers` reaches p90 = 169 and max = 5,741 questions per product).

| Category | Family | Products | Questions | Median q/p | ≥ 5 q | ND % | Usable | **Capped** | Flips | Both-policy | Warranty term in usable prose | Answer disagree |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `inkjet_printers` | electronics | 1,288 | 92,070 | 8.5 | 63.7 % | **43.5** | 458 | **182** | 82 | 84 | 6.3 % | 4.0 % |
| `quadcopters_&_multirotors` | electronics | 4,566 | 77,559 | 4 | 45.9 % | 23.1 | 739 | **446** | 62 | **229** | 6.3 % | 4.2 % |
| `video_projectors` | electronics | 4,633 | 106,685 | 5 | 50.4 % | 22.2 | 753 | **349** | 59 | 126 | **32.9 %** | 2.4 % |
| `over-ear_headphones` | electronics | 6,605 | 139,146 | 4 | 48.6 % | 21.0 | 987 | **564** | **87** | 237 | 16.8 % | 1.9 % |
| `carrier_cell_phones` | electronics | 2,466 | 114,240 | 11 | 65.6 % | **51.5** | 1,044 | **587** | 39 | 155 | 3.5 % | **7.3 %** |
| `chairs` | furniture | 19,193 | 88,268 | 2 | 24.3 % | 11.0 | 1,039 | **914** | 16 | 187 | 5.3 % | 1.0 % |
| `home_office_desks` | furniture | 6,986 | 55,303 | 3 | 35.3 % | 12.3 | 536 | **410** | 30 | 47 | 13.8 % | 2.8 % |
| `mattresses` | mattresses | 6,567 | 81,087 | 3 | 37.3 % | 21.1 | 871 | **580** | 7 | **482** | **44.2 %** | 3.8 % |

*ND % = share of multi-question products with a near-duplicate pair. Flips = products with a
numeric value-flip candidate (F3). Both-policy = products asked about warranty **and** returns
(F9). Warranty term in usable prose = F4's conflict risk. Answer disagree = community-answer noise
(F3).*

**Constraint (a) therefore does not rank these categories** — the smallest capped pool is 3.6× the
floor. A 50-product draw yields ~750–1,300 product questions per category before deduplication
and rewriting.

`bed_frames` and `led_&_lcd_tvs` were **not measured**: both downloads throttled to ~20 KB/s and
were stopped. Each is an alternate within a family that is already measured.

### F11 — Phones are excluded by their questions, not their numbers

`carrier_cell_phones` has the densest clustering of all (51.5 %), but **33.1 %** of its questions
mention a carrier, unlocking or a SIM (`verizon|at&t|t-mobile|sprint|cricket|…|unlock|sim`),
against 0.1 % in `inkjet_printers` and 0.2 % in `quadcopters_&_multirotors`. Those answers depend
on carrier networks — neither on a product document nor on a store policy — so a third of the
category could not be grounded in `v1` at all. It also has the noisiest answers (7.3 %).

---

## Answer

**All eight measured categories satisfy (a); (b) is satisfied by any set that spans at least two of
the three families.** So the question as posed has many correct answers, and the choice is made
on the secondary measures. The recommendation:

### Recommended — `inkjet_printers`, `quadcopters_&_multirotors`, `chairs`, `mattresses` (~38 products each)

| Category | Why it is in | What it costs |
| :--- | :--- | :--- |
| `inkjet_printers` | Densest clustering in scope (43.5 %); numeric flips on **specification** slots (paper size, OS version); continuity with every example `data-card.md` already cites | No published category-specific opposing condition — its B-within supply is spec-side only. Smallest capped pool (182), still 3.6× the floor |
| `quadcopters_&_multirotors` | The only low-conflict electronics category with a **published, category-specific opposing condition**: Best Buy's 15 % restocking fee on *opened* drones, none if unopened. Component-level warranty (3–12 months). Most both-policy products of the low-conflict electronics (229). A same-family **lookalike** to printers: both "electronics, 30 days" at Target, different terms elsewhere | A second electronics category means one more set of policy documents to author |
| `chairs` | Largest pool (914 capped); cleanest return-question precision (9/10); furniture's opposing condition is published (IKEA: 365 days unopened, 180 opened); multi-year warranty split by component (frame / mechanism / fabric) | Thin clustering (11.0 %): its A and C supply comes from volume, not density |
| `mattresses` | The only category whose distinct window is published **by Amazon itself** — 90 days against the 30-day default — i.e. by the retailer PQA's data comes from. 10-year warranty plus a trial period. Largest policy-question supply (482 both-policy products) | **44.2 % of usable products state a warranty term in their own prose** (F4). Excluding them leaves roughly 325 capped products; otherwise the authored warranty documents must be scoped around them |

**(b) on this set:** return windows — Amazon 30 vs **90** (mattresses); Target electronics 30 vs
general 90; Best Buy's opened-fee regime applies to drones only → **≥ 2 distinct** ✓. Warranty —
1 year (printers), 3–12 months by component (drones), 12 years to lifetime by component (premium
chairs), 10 years (mattresses) → **≥ 2 distinct** ✓, *on secondary sources (F6), which need primary
citations before any of them is authored into a policy document.*

**Fallback — three categories, ~50 each:** drop `quadcopters_&_multirotors`, leaving one per
family. It still passes (a) and (b). It loses the same-family lookalike and the only electronics
opposing condition, and it saves one category's policy documents — material, because item 3.3's
authoring cost scales with category count and G5 splits add documents on top.

**Not chosen:** `carrier_cell_phones` (F11). `video_projectors` — strong policy story (opened fee;
lamp 90 days vs body 2 years) but 32.9 % prose conflict; the alternate for drones.
`over-ear_headphones` — most flips (87), but no category-specific term in any primary source
(Target's 14 days is a *brand* rule, Apple/Beats). `home_office_desks` — dominated by `chairs` on
every measure. `bed_frames`, `led_&_lcd_tvs` — not measured.

## What this changes

1. **A decision for the author, then an ADR.** The categories are a frozen data choice and need a
   numbered entry with an `Invalidates:` line (`none — no runs yet` holds: nothing has run on `v1`).
   ⚠️ **It must not take ADR-001** — Phase 1's exit criterion reserves ADR-001 for the
   co-hosted-measurement decision. Either that is written first, or this takes the next number and
   001 stays reserved.
2. **`data-card.md` corrections, owed whichever set is chosen** (a scope-S docs task):
   - §3 — *"PQA contains no policy questions at all"* is false as measured (F9).
   - §1 — the category files, access date (`2026-10-03T09:47:49Z`), sizes and hashes (table below).
   - Freeze policy — *"all three gate criteria"* → five (G1–G5).
3. **Inputs to Phase 3, no task opened:**
   - **3.1 builder** — skip isolated empty `question_text`; keep the non-zero-parse assertion.
   - **3.2 selection rule** — cap questions per product (5–50 tested); remove dynamic questions;
     decide F4: exclude products that state a warranty term, or scope the authored warranty
     documents to store terms only.
   - **3.3 authoring** — F5's primary-source table is the starting point; F6's warranty figures
     need primary citations first.
   - **3.4 workload** — policy wording and policy-dimension B-within pairs can be partly
     **sampled** (F9); numeric flip candidates (F3) are the spec-side B-within supply.
   - **`K`** — a 38–50-product draw per category puts `K` in the low thousands. At μ_gen ≈ 0.19
     req/s, every 1,000 distinct queries cost ≈ 1.5 h of reference generation — and μ_gen itself is
     open under **F1**.
4. **No code changes.**

### Source manifest (downloaded 2026-10-03T09:47:49Z, `https://amazon-pqa.s3.amazonaws.com/`)

| File | Bytes | sha256 |
| :--- | ---: | :--- |
| `amazon_pqa_inkjet_printers.json` | 134,353,943 | `2b1ad4fc49ce8fca9ca29cb782ae7f12f3830aafda63e2200de1de8aaa43d90a` |
| `amazon_pqa_chairs.json` | 138,252,584 | `b015bea4871be949d5ca332a605fb0b1f1ebba5d89a903e277a857b1567b73c0` |
| `amazon_pqa_home_office_desks.json` | 95,549,762 | `2d89b15fc9c592539a4af9f4806517896e04594c7333ffdd68e5418a34fcba74` |
| `amazon_pqa_mattresses.json` | 152,793,447 | `9959b58046529bfcbfa05076f735f474409a5dc34b754914cccf4b3731c80fdf` |
| `amazon_pqa_video_projectors.json` | 243,675,719 | `4822926966308448ffe81dcb60ef7a8f585d0c43b8c37d381c111911d7eb03a0` |
| `amazon_pqa_quadcopters_&_multirotors.json` | 172,268,436 | `c5a3a53cc24c819d4db7fa898ea00a9b94042771f909a1f0c4e5451ab0a8a818` |
| `amazon_pqa_carrier_cell_phones.json` | 153,301,436 | `3ead62b2d7e26077193942037ec25a2089eba9e9086f819b85216b8cdaabac05` |
| `amazon_pqa_over-ear_headphones.json` | 278,531,682 | `b784c7e144257dbc1eb77e76ab46aaaba786d73280b533701a2314860344b320` |

**Sources (fetched 2026-10-03).** Primary: Amazon *Return Policy* (help node
`GKM69DUUYKQWKWX7`); Best Buy *Return & Exchange Policy*; Target *Returns*; IKEA US *Return
policy*. Secondary, not to be authored from without a primary: Walmart category windows (primary
page served a CAPTCHA); HP, Epson, DJI, Herman Miller, Steelcase, Casper, Tuft & Needle and TV
warranty terms.

---

## Revision 1 — 2026-10-03: the author rejects the leaf-category set

**Author's direction:** *"inkjet_printers, quadcopters_&_multirotors, chairs, mattresses are too
specific and not really common … I want something related to Furniture, Electronics, phone,
laptop."* This adds a constraint the original question did not state:

**(c) Categories are store departments a shopper would recognise** — furniture, electronics,
phones, laptops — not PQA's narrow leaves.

**Consequence for method.** PQA has **no** department-level file; all 100 files are leaves. So
(c) is met by **mapping leaves onto departments**, and the department becomes the `category`
join key that product and policy records share (`data-card.md` §2 requirement 1). A department
may draw on more than one leaf. Candidate leaves per department:

| Department | Leaf files | Status |
| :--- | :--- | :--- |
| Furniture | `chairs`, `home_office_desks` | measured (F10) |
| Electronics | `over-ear_headphones` (measured), `led_&_lcd_tvs` (retry) | partial |
| Phones | `unlocked_cell_phones` (821 MB), `carrier_cell_phones` (measured, F11) | downloading |
| Laptops | `traditional_laptops` (404 MB) | downloading |

**This also strengthens (b) rather than weakening it.** Target's own page (F5) assigns these
departments three different windows — phones **14**, electronics **30**, general merchandise
(furniture) **90** — and a restocking fee on *opened* phones only. Phones and electronics are a
**same-family lookalike** with different answers: *"how long can I return this phone?"* and
*"…these headphones?"* are near-identical queries grounded in different documents, which is
exactly the pair C1 is meant to separate.

**F11 is revisited, not assumed.** Phones were excluded because 33.1 % of `carrier_cell_phones`
questions concern carriers, unlocking or SIMs. Phones are now a required department, so the
question becomes whether the pool **after removing those questions** still clears (a) — and
whether `unlocked_cell_phones` carries fewer of them.

### F12 — ✗ F11 overstated: phones survive the carrier filter

`probe.py` now builds the capped pool (5–50 questions, dynamic removed) twice: once as before, once
with carrier / unlock / SIM questions also removed. It reproduces the one-off numbers recorded in
F10 (`inkjet_printers` 182, `carrier_cell_phones` 587), so the cap is now part of the script rather
than an ad-hoc command.

**`carrier_cell_phones` without carrier questions: 387 capped products** — 7.7× the ≥ 50 floor.
F11's reasoning ("a third of the category could not be grounded") was right about the questions and
wrong about the consequence: removing them is a filter, like F8's price filter, and the pool
survives it. Phones were excluded on a judgement the numbers did not support. The cost that
remains is real but smaller: the filter must exist in the selection rule, and phone answers are
still the noisiest measured (7.3 % disagreement on near-duplicate yes/no pairs).

### F13 — `led_&_lcd_tvs` is the strongest electronics leaf measured

Retried and completed (178,273,635 bytes, sha256 `bd8e9530…7861622f1`, 0 unparsed). 3,970
products, 137,881 questions, median 5, 52.4 % with ≥ 5; **33.4 %** of multi-question products
carry a near-duplicate pair — third-densest after phones and printers. **350** capped products
(carrier filter removes nothing: 0.2 %). 80 products with numeric flips (*"110v or 220v"*, model
comparisons), **230** both-policy products, and the **lowest** product-prose warranty conflict
measured (**3.4 %** of usable products). One flip shape is dynamic and slipped F8's regex —
*"When will the 950H 55" be available?"* — so the selection filter needs *available/release* terms
too.

### F14 — Laptops have no primary-sourced window distinct from general electronics

Apple's own page (fetched 2026-10-03): **14 days** for products bought from Apple, opened or not,
in original condition — a **brand** rule covering Macs and iPhones alike, not a laptop rule.
Best Buy files laptops under "most products" (15 days, no fee); Target under electronics (30);
Amazon under the default (30). A laptop-specific 15 % restocking fee on opened units (Dell,
Newegg) appears **only in secondary sources**.

**Consequence.** A laptops department either shares the electronics terms, or adopts a
secondary-sourced opened-laptop fee once a primary is found. Sharing is not a defect: it puts two
policy documents with **the same answer** under **different `doc_id`s**, which is where the
namespace conjunct refuses a reuse that would have been safe — the over-refusal cost of
partitioning, measured rather than assumed. It is a different test from the phones-vs-electronics
lookalike, not a weaker one.

### F15 — `unlocked_cell_phones` is the phones leaf, and it brings its own opposing condition

821,444,488 bytes (matches the listing), sha256 `007178b8…5381c249424c`; 4 unparsed records, all
empty `question_text` in the source (`TxJK9CNBWVT7F9`, `Tx1E1OLW47L66RS`, `Tx2F91V1U44D66O`,
`Tx38C12TK4OI99A`). Probed **streamed** — peak RSS 187 MB. *Memory pressure read `1` (yellow)
before this run; irrelevant to these numbers, which are deterministic counts over a file, but it
means the machine was not fit for any system measurement at the time.*

15,298 products, 499,535 questions, median 7, 58.7 % with ≥ 5, **45.9 %** near-duplicate
clustering. Carrier / unlock / SIM questions: **32.9 %** — the same rate as
`carrier_cell_phones` — and after removing them **2,260 capped products** remain, 45× the floor
and 5.8× `carrier_cell_phones`' 387. Answer noise 6.6 %; prose warranty conflict 6.5 %.

**12,585 warranty questions**, and **21.6 %** of them name a jurisdiction — *"Will the warranty
work in India?"*, *"does the phone have international warranty"*. **Domestic against international
warranty** is an opposing condition of exactly G5's kind, raised by shoppers rather than
constructed: two warranty documents (`policy-warranty-phones-domestic`,
`policy-warranty-phones-international`, say) whose questions read nearly the same.

**Unlocked over carrier** on every axis measured except none: larger pool, more policy questions
(961 both-policy products against 155), lower noise, the same carrier rate.

### F16 — `traditional_laptops` is large, intact, and shares the international-warranty condition with phones

Downloaded as byte ranges because single connections throttled to ~15 KB/s. **Integrity:** every
range and sub-range is exactly its expected length; the joined file is 403,702,059 bytes, matching
the listing; all **21** join offsets fall inside records that parse; 0 unparsed overall. sha256
`86452e67…9e35bf098b5f`. *An attempt to verify against the S3 ETag failed for a reason unrelated to
the data:* the ETags are multipart (`-24`), so they depend on the uploader's part size, which is
not published. Bounding it from the part counts of six files gives 17,113,427–17,226,844 bytes
— not a standard size — and the guess of 16.5 MiB failed on every file, including ones downloaded
whole. ETag verification is **not** claimed for any file here.

19,742 products, 291,896 questions, median 3, 41.1 % with ≥ 5, 21.7 % clustering; **1,742** capped
products (carrier filter removes nothing: 0.4 %). **100** products with numeric flips, all
specification-side — *"8gb or 12 gb ram?"* / *"upgrade ram to 16 gb?"*, *"7th or 8th
generation?"*. 9,801 warranty questions; 430 both-policy products; prose warranty conflict 11.2 %.

**Warranty questions naming US / international / global** (same regex for every row):

| `traditional_laptops` | `unlocked_cell_phones` | `over-ear_headphones` | `led_&_lcd_tvs` | `chairs` | `home_office_desks` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| **26.4 %** (2,588) | **21.6 %** (2,721) | 8.5 % | 2.8 % | 0.3 % | 0.0 % |

The domestic-vs-international condition is concentrated in phones and laptops and almost absent
elsewhere. Refurbished / renewed / used is smaller (4.2 % of laptop warranty questions) but is the
one condition with a **primary** window: Amazon gives Renewed products **90 days** against **30**.

---

## Answer — Revision 1 (departments)

**All four requested departments can be built from PQA, and every leaf proposed clears (a) by at
least 7×.** The smallest capped pool in the set is `led_&_lcd_tvs` at 350.

| Department (`category`) | Leaf file(s) | Capped pool | Clustering | Return window — primary | Opposing conditions available |
| :--- | :--- | ---: | ---: | :--- | :--- |
| **`phones`** | `unlocked_cell_phones` | 2,260 *(carrier questions removed)* | 45.9 % | **14 days** — Target; Best Buy (activatable) | **Opened → restocking fee** (Target ≤ $35, Best Buy $45), none unopened — *primary*. **Domestic vs international warranty** — 21.6 % of warranty questions |
| **`laptops`** | `traditional_laptops` | 1,742 | 21.7 % | **30 days** — Target electronics; 15 at Best Buy | **Domestic vs international warranty** — 26.4 %. **New vs Renewed** — Amazon 30 vs 90, *primary* |
| **`electronics`** | `led_&_lcd_tvs` + `over-ear_headphones` | 350 + 564 | 33.4 / 21.0 % | **30 days** — Target electronics | None from a primary source for TVs or headphones |
| **`furniture`** | `chairs` + `home_office_desks` | 914 + 410 | 11.0 / 12.3 % | **90 days** — Target general merchandise | **Opened vs unopened** — IKEA 180 vs 365, *primary* |

~150 products → **~38 per department**; a two-leaf department splits its share between leaves
(~19 each), which every leaf clears many times over.

**(b) on this set:** return windows **14 / 30 / 30 / 90** — three distinct values on Target's page
alone ✓. Warranty: ~1 year for phones, laptops, TVs and headphones against multi-year furniture —
two distinct ✓, *on secondary sources (F6); primary citations still owed before authoring.*

**What the set gives C1, by construction of real policy rather than by authoring:**

- **Different answers, near-identical questions:** phones (14) vs electronics (30) on returns;
  phones vs laptops on international warranty. Lookalikes the namespace conjunct must separate.
- **Same answer, different documents:** laptops vs electronics share 30 days (F14) — where
  partitioning refuses a safe reuse, so its cost is measured rather than assumed.
- **Opposing conditions of G5's kind, with primary sources:** opened/unopened phones, opened/
  unopened furniture, new/renewed laptops; plus domestic/international warranty from traffic.

**Costs to carry into Phase 3:**

1. **Phones need the carrier filter** (32.9 % of questions) in the selection rule — a filter, as
   F12 showed, not a disqualifier.
2. **Electronics has no primary-sourced opposing condition.** G5 holds trivially there; the
   department contributes lookalikes, not condition pairs.
3. **`unlocked_cell_phones` is 821 MB** and the laptop file throttled badly: the 3.1 builder must
   download with resume and ranges, and verify by byte count and parse, since the ETags cannot be
   checked (F16).
4. **Prose warranty conflict is moderate everywhere** (3.4–16.8 %) — `mattresses`' 44 % is gone with
   the leaf-category set — but F4's decision is still owed.

**Supersedes** the leaf-category recommendation above. That analysis stands as evidence; its
choice does not.

### Source manifest — additions (downloaded 2026-10-03, `https://amazon-pqa.s3.amazonaws.com/`)

| File | Bytes | sha256 |
| :--- | ---: | :--- |
| `amazon_pqa_unlocked_cell_phones.json` | 821,444,488 | `007178b847b2fb2b3bbdee7a79982dfcf7c51818f7cc909c5b4b5381c249424c` |
| `amazon_pqa_traditional_laptops.json` | 403,702,059 | `86452e67a51d029d8ff7419b2f4fe3037c2a1fcf27a2de199d859e35bf098b5f` |
| `amazon_pqa_led_&_lcd_tvs.json` | 178,273,635 | `bd8e9530c3ae2b678fd773c612e612770ce7b601b3b340d38f468767861622f1` |

Additional primary source: Apple *Sales & Refunds* (14 days, opened or not, original condition).

### Kept on disk — 2026-10-03

At the author's request, the six files of Revision 1's department set were copied out of the
session scratchpad, which does not survive the session, into **`data/raw/pqa/`**:
`unlocked_cell_phones`, `traditional_laptops`, `led_&_lcd_tvs`, `over-ear_headphones`, `chairs`,
`home_office_desks`.

- **`.gitignore` gained `data/raw/` first**, verified with `git check-ignore` before any byte was
  copied. Only `data/v1/` and `data/v1-draft/` were ignored before; PQA redistribution is not
  granted and the remote is public.
- **Not under `data/v1/`** — `rag.ingest` globs that directory and asserts `doc_id == filename`.
- **All six verified** with `shasum -a 256 -c` against the manifests above: OK. `git status` sees
  nothing under `data/`.
- This copies source bytes only. It does **not** decide the department set, and it is not the
  frozen corpus. The item 3.1 builder may read from here instead of re-downloading, provided it
  re-checks these hashes.

### F17 — ⚠️ Most real PQA questions are not answerable from their own product record

Built two `v1` product records from `data/raw/pqa` the way the item 3.1 builder would
(`specs` ← `bullet_point1..5`, `product_description`, `brand_name`; rendered by the real
`rag.ingest.product_to_text`; split by the real `SentenceSplitter` at the frozen 256 / 40).
Chosen deterministically: qualifying products closest to 15 questions, then by `asin`.

**First draw exposed empty products.** `B007Q45N8M` (Dell Latitude E6420) has **no bullets and no
description** — `specs = {}`, the document is its title alone, and none of its 15 questions can be
grounded. Measured across the six leaves: **2.7–9.1 %** of products have empty prose and
**6.2–18.4 %** have fewer than three bullets. A **≥ 3 bullets** filter, plus F4's
no-warranty-term filter, leaves capped pools of **302** (`led_&_lcd_tvs`) to **1,811**
(`unlocked_cell_phones`): cheap, and it belongs in the 3.2 selection rule.

**Second draw shows the deeper issue.** `B0085H655O` (Acer Aspire S3, 6 spec lines, 433 chars,
**1 chunk** — F4/`data-card.md` §1 confirmed) has 15 questions. Read by Claude, not human-verified:
**1** is answerable from the record (*"How is the battery life?"* → 5.5 hours), **2** are policy
questions (*"guarentee"*, *"how long is my garanty for a refurbicshed ultrabook"*), and **12** ask
what the listing does not say — touchscreen, backlit keyboard, DVD drive, Ethernet, charger
included. A furniture draw (`B001FOR904`, TMS cross-back stools) is similar: of the 9 questions
read, about 2 are answerable (*"two in a box?"* ← "Set of 2"; seat height ← "24 inch").

This is **not a defect of the selection**. It is what PQA is: shoppers ask what the page does not
answer — the dataset's own paper answers them from *other* products' Q&A for that reason.

**Why it matters for validity.** The reference is `LLM(retrieve(q), q)`. For an unanswerable
question it is some form of *"the information is not available"*, and two such answers agree.

- **Reuse becomes trivially safe.** A workload dominated by unanswerable questions inflates the
  safe-hit rate for every configuration and compresses the frontier C1 is measured on.
- **Natural traps stop being traps.** F3's numeric flips (*"8gb or 12gb ram?"* / *"upgrade to 16
  gb?"*) separate only if the record distinguishes the values. If both answers are "not stated",
  the pair is a safe reuse, not a B-within trap.
- **The support gate degenerates.** `S_lex` over an "information not available" answer has almost
  no content tokens to check.

**What it changes.** The workload needs an **answerability criterion** at item 3.2 / 3.4. Questions
are kept only where the product record (or a policy document) contains the answer, or
unanswerable questions become a stratum of their own, reported separately and never mixed into
the headline. How answerability is decided — a lexical rule, an LLM label with model and prompt
recorded, or curation — is a **decision not yet taken**, and every option shrinks the
per-product question supply, so the capped pools above are **upper bounds**. Two examples are not
a measurement: the answerable share must be measured on a labelled sample before the selection
rule is frozen.

### F18 — ⚠️ PQA was never shown to be the best available source; one unevaluated alternative fits F17

The author asked why PQA is the optimal raw dataset. **It has not been shown to be.** It was
adopted on 2026-09-21 against exactly **one** alternative — `Amazon-Reviews-2023` metadata joined
to `AmazonQA` — and this investigation chose categories *within* PQA without searching beyond it.

What PQA was measured to give, against that alternative: question and product content in one
record (no join); thick per-product question tails; natural paraphrase clusters (strata A, C);
natural numeric and policy-dimension B-within candidates (F3, F9); real policy-question wording
(F9); department-sized leaves (Revision 1). What it was measured to cost: no redistribution;
~1 chunk per product (F4); empty products (F17); **most questions unanswerable from their own
product record (F17)**; elliptical questions; community answers that are noise.

**An alternative found on 2026-10-03 and not yet evaluated: ePQA** (Amazon Science,
`github.com/amazon-science/contextual-product-qa`, README read 2026-10-03). Per that README —
*secondary until the data itself is read*:

- Each record carries `question`, `candidate` (a snippet of product information), `label`
  (**0 irrelevant / 1 helpful but incomplete / 2 fully answering**), a **manually written**
  `answer`, `source`, `context`, `ASIN`. Multiple questions per product; categories unrestricted.
- Splits 131,520 / 1,000 / 2,000 questions (per the xPQA paper's description of ePQA).
- Licence stated as **"CDLA 1.0 Sharing"** — if that is CDLA-Sharing-1.0 and the data's own files
  agree, redistribution **is** permitted, which PQA's is not. Not verified: this is the same kind
  of claim that F-reversal 1 of the 2026-09-21 probe found contradicted by the dataset's own
  readme.

**Why it matters:** ePQA's label is precisely F17's missing answerability criterion, assigned by
annotators rather than by this study. **What is unknown and decides it:** whether the candidates
reconstruct a whole product record or only snippets; questions per product and paraphrase
clustering (the cache workload needs redundancy, not just labels); coverage of phones, laptops,
electronics and furniture; and whether its `ASIN`s overlap PQA's — if they do, ePQA labels could
serve as the answerability filter **on** PQA questions rather than replace them.

semiPQA (same repository; ~11 k questions over JSON attribute data, ECNLP 2022) is noted and judged
a weaker fit on the README alone: small, attribute-only, no evidence of per-product clustering.

**What it changes:** nothing is frozen, so this is still cheap to check. A short measurement of
ePQA on the same probe metrics, plus its licence text, belongs **before** the department ADR is
written — after the corpus freeze the choice is unrecoverable.

### F19 — Survey of alternative sources (2026-10-03): none supplies what PQA does

Searched at the author's request before measuring ePQA. Each candidate was scored against what
`v1` needs: product content per product; real questions tied to products **with per-product
redundancy** (the cache workload); answerability from product content; coverage of the four
departments; licence; anything for the policy half. Sources are listed under F20.

| Source | What it is | Fails on |
| :--- | :--- | :--- |
| **AmazonQA** (Gupta et al., IJCAI 2019) | 923 k questions, 156 k products, answerable / unanswerable labels **against reviews** | Evidence is reviews, not specifications — outside the stable slice the cache may serve. Licence not stated |
| **hetPQA** (Amazon, ECNLP 2022) | Six evidence sources, binary labels | **Toys & games only** |
| **semiPQA** (Amazon, ECNLP 2022) | 10,949 written questions over JSON attributes | Attribute-only, written rather than natural, no per-product redundancy |
| **xPQA** (Amazon, ACL 2023) | 12 languages, 500 / 1,000 questions each | Small, multilingual; English evidence only |
| **HomeDepotQA** (Adobe, 2019) | 7,119 question–specification pairs, 153 products, crowd-written | **No public release found** |
| **McMarket** (EMNLP 2024) | 7 M questions, 17 marketplaces | Review-based, multilingual, LLM-labelled |
| JD product QA (`gsh199449/productqa`) | 470 k products | Chinese |
| Flipkart PQA (2020) | 80 M products | **Not public**. Its finding is used below |
| Bitext retail chatbot | 44,884 synthetic Q/A over 46 intents | Synthetic, no products, no documents |
| **DRIP-R** (EMNLP Findings 2026, CC BY 4.0) | 400 return-negotiation scenarios grounded in **Amazon's real return policy** | No gold answers **by design**. Useful as a reference for authoring the policy half, not as a workload |
| Shopify catalogue, WDC Products, ABO | Product content | No questions |

**One finding transfers:** Flipkart's study (Roy et al., 2020, *"Using Large Pretrained Language
Models for Answering User Queries from Product Specifications"*) states in its Introduction that
*"a large fraction of user queries (∼20%)"* can be answered from product specifications — verified
in the paper's text, not only its abstract, which gives no number. An **independent** measurement
of F17's phenomenon on a different retailer's traffic.

### F20 — ePQA measured: it does not replace PQA, but it can calibrate the answerability filter

Downloaded from `github.com/amazon-science/contextual-product-qa` (`ePQA/{train,dev,test}.csv`,
46 MB). **Licence verified in the repository's own `LICENSE`: `SPDX-License-Identifier:
CDLA-Sharing-1.0`** — redistribution under the same terms is permitted, unlike PQA.

| | ePQA |
| :--- | ---: |
| questions / ASINs / candidates per question | 15,152 / 5,697 / 10.0 |
| questions with a **fully answering** candidate (label 2) | 71.9 % |
| … from a **specification** source (`attribute`, `bullet`, `description`) | **22.9 %** |
| … from reviews or community answers only | 49.0 % |
| questions per ASIN — mean / median / max | **2.66 / 3 / 6** |
| ASINs with ≥ 5 questions | **52** |
| multi-question ASINs with a near-duplicate pair | **0.3 %** (14) |

1. **ePQA fails constraint (a) outright.** It is a deduplicated benchmark sample — at most six
   questions per product, almost no paraphrase clustering — not traffic. A cache study needs
   redundant traffic; PQA has it (F10), ePQA does not.
2. **F17 is confirmed three ways.** Spec-answerable share: **22.9 %** in ePQA, *with* structured
   attributes that PQA lacks; **~20 %** at Flipkart; about **1 in 15** in the hand-read PQA laptop
   example. It is a property of real shopping questions, not of PQA, so **no source fixes it**. It
   is fixed by a filter.
3. **ePQA supplies human labels on PQA's own questions.** 142 ASINs and **295 questions** appear in
   both, matched on exact question text. Within Revision 1's six leaves: `unlocked_cell_phones`
   **143**, `led_&_lcd_tvs` 21, `over-ear_headphones` 19, `traditional_laptops` 5,
   `home_office_desks` 4, `chairs` 2 — **194**. That is too few to *be* the filter, but enough to
   **validate** whichever answerability rule is adopted against human labels, the way judge–human
   agreement validates the judge. Caveat: ePQA's evidence includes JSON attributes that `v1`'s
   product records will not carry, so its "answerable" is an upper bound on answerability against
   a PQA record.

**Answer to F18's question:** PQA remains the best available **workload** source — the only one
measured that combines product content, real questions and per-product redundancy in one record.
It is kept for **that**, not because it is clean. What changes is that F17's answerability
filter is now a required part of item 3.2, with ePQA's overlap as its validation set. A
consequence not yet measured: at ~20 % answerable, a product needs roughly 25 questions to keep 5
answerable ones, so the 5–50 cap and every capped pool in this trail are **upper bounds** until
the filter exists.

### F21 — Within-product paraphrasing is low: clusters are pairs, not families

The author asked how much the questions **about one product** paraphrase each other. Measured on
the pool `v1` would draw from (5–50 questions after dynamic and carrier removal, ≥ 3 bullets, ≥ 1
pair). Per product, questions are grouped by union-find over pairs that are **exact repeats**
(identical content tokens) **or** lexical near-duplicates (F2's band). *In-cluster* = share of a
product's questions with at least one partner. *Redundancy* = 1 − clusters / questions: the share
of questions that re-ask something already asked — the cacheable fraction. Lexical only:
embedding measurement was blocked by **yellow** memory pressure (level 1) at the time.

| Leaf | Pool | Median q / product | In-cluster — median / p75 / p90 | Redundancy — median / p75 / p90 | Largest cluster, median | Products with redundancy ≥ 15 % |
| :--- | ---: | ---: | :--- | :--- | ---: | ---: |
| `unlocked_cell_phones` | 2,638 | 21 | 18.2 / 26.7 / 36.8 % | **10.0** / 14.7 / 20.0 % | 2 | 652 |
| `traditional_laptops` | 2,492 | 20 | 16.7 / 25.0 / 34.6 % | **8.8** / 13.3 / 20.0 % | 2 | 481 |
| `led_&_lcd_tvs` | 490 | 24.5 | 13.6 / 21.1 / 28.6 % | **7.1** / 11.1 / 15.4 % | 2 | 52 |
| `over-ear_headphones` | 912 | 20 | 16.0 / 25.0 / 33.3 % | **8.3** / 13.0 / 19.4 % | 2 | 158 |
| `chairs` | 1,604 | 12 | 22.9 / 33.3 / 40.0 % | **12.5** / 16.7 / 20.0 % | 2 | 540 |
| `home_office_desks` | 792 | 17 | 18.2 / 28.6 / 40.0 % | **9.4** / 14.3 / 20.0 % | 2 | 178 |

*Pools are larger than F10's / F17's because exact repeats now count as a pair; F10's
near-duplicate test excluded them.*

1. **A typical product has ~20 questions and one paraphrase pair.** Redundancy is 7–12.5 % at the
   median, and the largest cluster is **2** at the median in every leaf. Natural traffic about one
   product does not form large families of rewordings.
2. **The high tail is partly an artefact.** Products with redundancy ≥ 15 % are small (median 7–13
   questions), and both p90 examples are **exact repeats** — *"Is this the XT1103 model?"* twice,
   *"What color are the legs on the chairs?"* twice. Exact repeats are **Tier-1** material, not
   the reworded pairs Tier 2 exists for.
3. **Lexical measurement undercounts stratum C** (same intent, different words), which only the
   frozen embedding can see. These figures are a **lower bound** on within-product paraphrasing.

**What it changes.** Natural within-product paraphrasing **cannot carry Tier-2's traffic alone**.
`data-card.md` §4 already plans machine-generated paraphrases of seed questions, and this makes
them the volume source rather than a supplement. Natural pairs remain the **validity anchor**:
real wording, and natural traps. That raises a reporting obligation, because generated paraphrases
are plausibly *easier* — closer in embedding space — than real ones. Hit rate and false-hit rate
must be reported **separately for natural and generated pairs**, or the headline is carried by
the generator's style rather than by the cache. The embedding-based measurement of this table
(frozen `nomic-embed-text`, `search_query: ` prefix as in `gateway/internal/embed/client.go`, τ
swept, within- vs cross-product) is owed once pressure is green.

### F22 — F21 measures the dataset's selection, not real traffic; the thesis must model redundancy, not inherit it

The author's objection: in real traffic — a flash sale — one product can receive tens of thousands
of questions, heavily paraphrased, so is F21 a property of the dataset rather than of reality?
**Largely yes, and the distinction belongs in the write-up.**

- **What PQA records is posted questions, not traffic.** A shopper posts to the public Q&A board
  only when the board, already shown on the page, does not answer them. Guidance on the feature
  tells shoppers to check existing questions first (secondary sources, see below). The board
  therefore acts as a **deduplicating filter**: PQA is closer to a catalogue of *distinct intents
  per product* than to a log of how often each intent is asked. Low within-product paraphrasing
  (F21) is what such a filter produces. *This mechanism is inferred from how the feature works,
  not measured; no source quantifies how many would-be questions are suppressed.*
- **No public measurement of per-product query redundancy in e-commerce was found.** The closest
  quantitative figure is MeanCache's (Gill et al., arXiv 2403.02694, §III-C): *"about 31% of user
  queries were similar to previous ones"* — but that is **20 ChatGPT users' own histories**, ~27 k
  queries, an academic setting, and repetition **by the same user**, not many users asking about
  one product. Its authors note the ratio *"may vary in other contexts"*. It supports
  "real traffic repeats"; it does **not** support any particular flash-sale figure. AliMe
  (Alibaba) reports millions of questions per day but no repetition rate.
- **Flash-sale redundancy is partly outside the cache's slice.** The questions a sale
  concentrates — price, stock, discount validity, delivery, order status — are **dynamic** and
  must bypass the cache (CLAUDE.md). Specification and policy questions asked during a sale are
  the cacheable part. *Reasoned, not measured.* Concurrent **identical** requests in a burst are
  what request coalescing (`singleflight`) collapses — the burst case is served by C3's machinery
  as much as by the reuse rule.

**What it changes — framing, not data.** The design already separates the two things F21 conflates.
**PQA supplies intents and real wording.** **Traffic redundancy is a controlled variable**: Zipf
popularity at three skews (`super-plan.md` 7.1), with results reported **across** the skew range
rather than at one assumed real-world level. Because no public per-product traffic log exists,
sweeping redundancy is the defensible choice, and the write-up should say why in those terms: the
dataset under-represents redundancy by construction, so redundancy is modelled and swept, never
inherited from the dataset. What F21 does constrain is **wording diversity per intent**: how many
distinct real phrasings each intent has. That is what generated paraphrases supply, with F21's
natural-vs-generated reporting obligation.

Sources: MeanCache — arxiv.org/html/2403.02694v4 §III-C · AliMe Assist — arxiv.org/abs/1801.05032
· Amazon Q&A feature descriptions (secondary): amalyze.com/en/?p=29440, ecommerceguide.com/patterns/qa-block/.

### F23 — Questions per product, and why per-product paraphrasing is not the only source of reuse

**Distribution over all products in the six `data/raw/pqa` files** (non-empty questions):

| Leaf | Products | Mean | Median | p75 | p90 | Max | 1 question | ≥ 5 | ≥ 20 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `unlocked_cell_phones` | 15,298 | 32.7 | 7 | 26 | 80 | 1,852 | 20.0 % | 58.7 % | 30.4 % |
| `traditional_laptops` | 19,742 | 14.8 | 3 | 10 | 30 | 3,550 | 32.2 % | 41.1 % | 15.1 % |
| `led_&_lcd_tvs` | 3,970 | 34.7 | 5 | 27 | 90 | 1,786 | 24.7 % | 52.4 % | 29.3 % |
| `over-ear_headphones` | 6,605 | 21.1 | 4 | 14 | 39 | 3,586 | 25.7 % | 48.6 % | 19.0 % |
| `chairs` | 19,193 | 4.6 | 2 | 4 | 10 | 367 | 41.7 % | 24.3 % | 3.7 % |
| `home_office_desks` | 6,986 | 7.9 | 3 | 7 | 18 | 620 | 33.3 % | 35.3 % | 8.9 % |
| **all six** | **71,794** | **16.9** | **3** | 10 | 33 | 3,586 | 31.2 % | 41.1 % | 15.9 % |

The **top 10 % of products hold 70.6 %** of all questions, so the mean (16.9) describes almost no
product; the median (3) is the typical one. In the pool `v1` draws from, the median is 12–24.5
(F21).

**The cache is not per-product for every question** (`gateway/internal/reuse/lane.go`, header):
only the **spec** lane's namespace is the product. A **policy**-grounded question's namespace is
the **policy document**, *"the same answer for every product the policy governs"*, so one cached
answer serves the same policy question about every product in the department. A **mixed**
question's namespace is the (product, policy) pair. Reuse therefore has two sources: paraphrases
**within** a product (spec lane, F21: low) and the same policy question **across** products
(policy lane, F9: thousands per leaf, e.g. 12,585 warranty questions in `unlocked_cell_phones`).
F21's low figure constrains the first source, not the second.

### F24 — Of 100 questions about one product, 84–95 ask something not already asked

Products with ≥ 100 questions; the first N in file order; distinct intents = union-find clusters
over exact repeats and lexical near-duplicates (F2's band). All questions, dynamic and carrier
included, because the question is about intent novelty, not cacheability. Lexical only, since
memory pressure was still **yellow**.

| Leaf | Products ≥ 100 q | New in first 10 | in 20 | in 50 | **in 100** | p25–p75 per 100 |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| `unlocked_cell_phones` | 1,204 | 9.8 | 19.1 | 45.2 | **83.5** | 79–89 |
| `traditional_laptops` | 462 | 9.9 | 19.6 | 47.8 | **92.3** | 90–96 |
| `led_&_lcd_tvs` | 357 | 9.9 | 19.8 | 48.4 | **94.1** | 92–97 |
| `over-ear_headphones` | 233 | 9.9 | 19.8 | 48.7 | **94.6** | 93–97 |
| `chairs` | 31 | 9.7 | 19.1 | 46.4 | **88.5** | 85–92 |
| `home_office_desks` | 48 | 9.9 | 19.6 | 48.2 | **93.7** | 92–97 |

1. **The novelty curve barely bends.** New intents keep arriving almost one per question up to 100:
   PQA's per-product questions are a **long tail of distinct intents**, not a few intents asked
   many times. Phones repeat most (16.5 per 100), consistent with their carrier questions.
2. **This is an upper bound on novelty, for two independent reasons.** Lexical matching misses
   reworded paraphrases (an embedding would merge more clusters), and the Q&A board deduplicates
   what gets posted (F22). Real traffic re-asks more; how much more is not measurable from any
   public source found.
3. **It is within-product only.** The same policy question across products — the policy lane's
   reuse (F23) — is not counted here.

**What it changes:** nothing new. It quantifies F21 and F22 in the author's terms, and it is the
number that justifies modelling redundancy (Zipf) rather than replaying PQA's per-product order.

### F25 — Embedding confirms F24, and shows real paraphrases and traps sharing the 0.80–0.85 band

**Conditions.** Frozen `nomic-embed-text` via Ollama, `search_query: ` prefix exactly as
`gateway/internal/embed/client.go` applies it, cosine over unit vectors. Run under memory pressure
**1 → 2 (urgent)**, explicitly approved by the author for exploratory work (memory:
green-pressure-only-for-thesis-runs). Embedding values are deterministic, so the counts are
unaffected; no timing from this run is used. **Exploratory, not citable.** Sample: up to 150
products with ≥ 100 questions per leaf, chosen by `sha1(asin)` order (all 31 `chairs`, all 48
`home_office_desks`), first 100 questions each, 67,900 embeddings. A question is a **re-ask** at τ
if some *earlier* question about the same product has cosine ≥ τ — the hit a similarity-only cache
holding every prior answer would serve.

**New questions per 100:**

| Leaf | Lexical (same sample) | cos ≥ 0.80 | cos ≥ 0.85 | cos ≥ 0.90 | cos ≥ 0.95 |
| :--- | ---: | ---: | ---: | ---: | ---: |
| `unlocked_cell_phones` | 85.3 | 78.7 | 87.6 | 92.9 | 96.0 |
| `traditional_laptops` | 92.5 | 87.3 | 92.3 | 95.5 | 97.3 |
| `led_&_lcd_tvs` | 94.0 | 87.8 | 93.7 | 96.6 | 97.8 |
| `over-ear_headphones` | 95.0 | 90.4 | 95.1 | 97.1 | 97.9 |
| `chairs` | 89.2 | 76.2 | 86.3 | 92.0 | 94.9 |
| `home_office_desks` | 94.0 | 81.3 | 91.7 | 95.5 | 97.4 |

1. **F24 holds under the frozen embedding.** At cos ≥ 0.85, the G1 threshold, 5–14 of 100
   questions re-ask something, about what the lexical test found. Only at 0.80 does it reach 10–24
   per 100, and point 3 shows that band is not all safe.
2. **The embedding finds stratum C the lexical test cannot.** Pairs merged at ≥ 0.90 with lexical
   Jaccard < 0.45: *"How wide is the seat?"* ~ *"What is the width of the seat?"* (0.958), *"Can I
   add more memory?"* ~ *"can you add more ram?"* (0.925), *"can they work on a computer"* ~ *"do
   they work on computers?"* (0.957).
3. **⭐ Real paraphrases and traps overlap in the same band** (10 products × 100 questions each for
   phones and laptops, every question against its most similar earlier one; read by Claude, not
   human-verified):
   - **[0.80, 0.85)** mixes both. Paraphrases: *"does it have wi-fi?"* ~ *"wifi?"* (0.806); the
     smoke-test pair *"does it have bluetooth?"* ~ *"is bluetooth supported?"* (0.826). Traps:
     *"Does it have USB ports"* ~ *"Does it have an Ethernet port?"* (0.801), *"El teclado viene
     latinoamericano?"* ~ *"El teclado es retroiluminado?"* (0.805), *"work worldwide?"* ~ *"work
     in India?"* (0.837).
   - **[0.85, 0.90)** is mostly paraphrase — *"camera"* ~ *"webcam"* (0.853), *"touchscreen?"* ~
     *"touch screen display?"* (0.865) — with version-specific near-misses: *"come with windows?"*
     ~ *"come with windows 7"* (0.881).
   - **[0.90, 1.0]** is paraphrase and literal repeats, with subtle condition changes still
     present: *"work at Venezuela con movistar"* ~ *"work at Venezuela?"* (0.974).

   **No single τ separates the two populations.** A threshold low enough to catch *"wifi?"* also
   admits *"USB"* for *"Ethernet"*. That is RQ2's premise — similarity alone is not a reuse-safety
   signal — appearing in natural traffic, under the frozen model, before any rule is applied.
   These pairs are candidate material for the natural B-within stratum (F3) and, once labelled, for
   the frontier's trap side.

**Sources:** AmazonQA — arxiv.org/abs/1908.04364 · hetPQA / semiPQA / ePQA / xPQA —
github.com/amazon-science/contextual-product-qa, aclanthology.org/2022.ecnlp-1.14,
arxiv.org/abs/2305.09249 · HomeDepotQA — arxiv.org/abs/1901.02539 · McMarket —
aclanthology.org/2024.emnlp-main.625 · Flipkart — arxiv.org/abs/2005.14613 · DRIP-R —
arxiv.org/abs/2605.07699, github.com/ITU-NLP/drip-r-bench · KaPQA — arxiv.org/abs/2407.16073 ·
eCeLLM / ECInstruct — arxiv.org/abs/2402.08831 · Hugging Face: `bitext/Bitext-retail-ecommerce-llm-chatbot-training-dataset`,
`Shopify/product-catalogue`, `wdc/products-2017`.

---

## Outcome — 2026-10-04

**Decided:** the author approved Revision 1's four-department set (`approvals.md`). Recorded as
**ADR-002** in `docs/decisions.md`, with ADR-001 left reserved for the co-hosted-measurement
decision that Phase 1's exit criterion names.

**Applied to `docs/data-card.md`** (v0.3 → v0.4):

- the header and status;
- the freeze policy's *"three gate criteria"* → five (G1–G5);
- the artifact table (source mapping; policy corpus ~13 documents);
- §1 — source files with sizes and sha256, download and verification guidance, departments, the
  per-department choice table, the proposed selection rule, the answerability requirement, and
  empty and thin products;
- §2 — provenance (~13 documents) and per-department windows from primary sources;
- §3 — the withdrawn claim that PQA holds no policy questions, and the corrected account of
  within-product paraphrasing.

**Left open, deliberately** (listed in `approvals.md`): a `source_category` schema field; renaming
`TODO(W8)`; the answerability criterion; the paraphrase generator; the `SO_REUSEPORT` bugfix.
The question this investigation asked is answered. Those items belong to Phase 3 tasks
(items 3.1–3.4) and a separate `/bugfix`, opened when their phase is.
