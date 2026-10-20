# Policy scope: does the pool ask about store policies beyond returns and warranty?

**Why:** item 3.3 dropped shipping because "the pool has no shipping tag". But 3.2's tagger only
looks for return / refund / restocking and warranty words, so the absence of a tag is not evidence
that no other policy question exists. Asked by the author, 2026-10-21.

## 1. Keyword counts (upper bounds)

`policy_scope_probe.py` (this folder), reading the pool only through `select_pqa.iter_selection`,
counts only. 4,706 pool questions; 127 are already tagged policy (returns, warranty).

| Topic | Hits | of which tagged policy |
| :--- | ---: | ---: |
| shipping / delivery | 49 (phones 19, furniture 14, laptops 10, electronics 6) | 2 |
| ships abroad / customs | 5 (phones) | 0 |
| exchange | 1 | 0 |
| installation / assembly service | 121 (furniture 72) | 1 |
| cancel an order | 13 (electronics 12) | 0 |
| payment / financing | 0 | 0 |
| protection plan / insurance | 12 | 4 |
| condition: new / used / genuine | 121 (phones 49) | 10 |
| seller / sold by | 15 | 3 |
| gift / gift receipt | 6 | 1 |

Questions not tagged policy that hit any topic: **309** (electronics 64, furniture 114, laptops 56,
phones 75). A keyword hit is not a policy question ("noise cancelling" hits *cancel*; "is assembly
hard?" hits *assembly*).

## 2. The marking rule (fixed before any row was read)

A seeded sample of 10 hits per topic (100 rows, seed `v1-item-3.3:policy-scope`). By the author's
decision (2026-10-21) the sample is **marked by a model (Claude) at the author's request**, read in
the session scratchpad only; the labels go back to the gitignored audit file, and only counts come
here.

- **`is_store_policy` = y** when the answer is set by **the store's own terms of service** —
  returns, exchanges, refunds, warranty or protection, shipping or delivery service, international
  shipping, installation or assembly *service*, order cancellation, payment options — and would be
  the **same for every product in the department**. **n** when the answer is a property of the
  product or of one listing (what is in the box, whether assembly is hard, whether this listing is
  new or used, who the seller is), or when the question is not a question about buying at all.
- **`stable` = y** (marked only when `is_store_policy` = y) when the answer is a fixed term that
  does not change with the date, a promotion, stock, price, the buyer's address or one order (for
  example "do you ship to Canada?" or "is there a fee for an opened phone?"). **n** when it does
  (delivery dates, shipping fees, "will it arrive by Friday?", order status).
- **When unsure, mark n.** Only a y / y question could be grounded in an authored policy document.

**What would change the decision:** if a topic outside returns and warranty has **≥ 3 of 10** sample
rows marked y / y, its estimated count of stable store-policy questions (hits × the y / y share) is
reported to the author, who decides whether 3.3 adds documents for it (which reopens the design
and the experiment approval). Otherwise the two-kind corpus stands, and these numbers are recorded
as the evidence.

## 3. Result (marked 2026-10-21 by Claude at the author's request, by §2's rule)

The sample holds **72 rows, not 100**: four topics have fewer than 10 hits (exchange 1, ships abroad
5, gift 6, payment 0). Labels: `data/v1-draft/audit/policy-scope-sample.csv` (gitignored).

| Topic | Rows | Store policy | Stable store policy | Est. stable in the pool (hits × share) |
| :--- | ---: | ---: | ---: | ---: |
| shipping / delivery | 10 | 6 | 2 | ≈ 10 of 49 |
| ships abroad / customs | 5 | 5 | **4** | ≈ 4 of 5 |
| exchange | 1 | 0 | 0 | 0 |
| installation / assembly service | 10 | 0 | 0 | 0 |
| cancel an order | 10 | 0 | 0 | 0 |
| protection plan / insurance | 10 | 4 | **4** | ≈ 5 of 12 |
| condition: new / used / genuine | 10 | 1 | 1 | ≈ 12 of 121 |
| seller / sold by | 10 | 2 | 1 | ≈ 2 of 15 |
| gift / gift receipt | 6 | 3 | 2 | ≈ 2 of 6 |

**What the stable store-policy rows are** (described, not quoted):
- **"Do you ship to <country>?"** — the only new stable topic: 4 of the 5 abroad rows and 1 of the
  shipping rows, all phones.
- **Buying or using a protection plan** — 2 rows; the other 2 stable protection rows are warranty
  questions already tagged policy.
- **Return or warranty questions in other words** — a damaged item that arrived broken ("can you
  send a replacement?"), return shipping cost, "what is the warranty?" inside a gift or condition
  question. These are the two kinds the corpus already has; several of them were **not tagged
  policy** by 3.2's tagger (it has no "replacement" or "send back" word).
- **Dynamic, not stable:** delivery time and dates, shipping fees and customs duties (4 of the 6
  shipping policy rows, 1 abroad row, 1 seller row, 1 gift row). Under `CLAUDE.md` these bypass the
  cache, so they could never be grounded in a cached policy document anyway.
- **Not policy at all:** every installation / assembly row (product questions: tools, "does it need
  assembly?"), every "cancel" row (noise-cancelling headphones), and nearly all condition and seller
  rows (one listing, not the store).

**Against the decision rule (§2):** two topics reach ≥ 3 stable rows: **ships abroad** (4 of 5;
≈ 4 questions in the pool, all phones) and **protection plan** (4 of 10; ≈ 5 in the pool, of which
about half are warranty questions already covered). Together, stable store-policy questions outside
returns and warranty are **about 6 – 10 of 4,706 (≈ 0.1 – 0.2 %)**, against 127 return and warranty
questions. Reported to the author, who decides.

**For 3.4, whatever the decision:** 3.2's policy tagger misses return-kind questions worded as
"replacement" or "send back", so its 127 is a low count of real return and warranty questions.
