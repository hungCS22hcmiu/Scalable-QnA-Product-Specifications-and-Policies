# Is L2 (name-similar swap partners) likely to reach 50? — a check on existing data

Written 2026-10-23, before `design.md`. Counts only. It reads the **existing** workload, the existing vectors file and the
3.4 model layer; no new embedding was computed, so the rule "choose partners by names, before any cosine" (spec,
decision 4) is not affected.

## What the existing data say

| Question | Count |
| :--- | :--- |
| G1 pairs today (J ≤ 0.2, cosine ≥ 0.85): inside a split + across the splits | 21 + 18 = **39** |
| Ceiling if every one of those 39 sat inside a split, with no new pair | **39**, below 50 |
| Cross-product query pairs at cosine ≥ 0.85 (J = 0 by scoping), single-document queries | 24 |
| ...of which come from how many distinct **product pairs** | **5** (10, 4, 4, 3, 3 query pairs) |
| Of the 24: share a first title word and sit in different splits / differ and sit in different splits / differ and sit in the same split | 10 / 4 / 10 |
| Name swaps (22 kept) whose two products share a first title word | 2 of 22, cosines 0.77 and 0.79 |
| Name swaps at cosine ≥ 0.85 | 0 of 22 (highest 0.804) |
| Product pairs, ranked by short-name token overlap (Jaccard): ≥ 0.6 / ≥ 0.5 / ≥ 0.4 | 9 / 34 / 47 (none ≥ 0.8) |
| Where the 5 productive pairs rank in that list (0 = most similar names) | 37, 41, 46, 103, 336 |
| Units today whose products share a first title word | 7 of 74 |
| Products sharing a first title word with another in the same leaf | 87 of 152 |

## What it means

1. **The supply is lumpy.** All high-similarity cross-product pairs come from 5 product pairs. G1 is decided by a handful
   of look-alike products, not by a mass of swaps.
2. **Name similarity does not find them.** The 36 pairs with the most similar short names contain none of the 5 productive
   pairs. A names-only partner rule (the decided L2 rule) has no support in this data; a brand-sharing swap still sat at
   0.77 – 0.79.
3. **Regrouping alone cannot reach 50.** Putting all 39 existing pairs inside the splits gives 39. The rest (11 or more)
   would have to come from new product pairs that happen to embed close, which the data give no way to choose in advance.
4. **The structural reason.** Retrieval is scoped to the product and a product has about 3 chunks, so a pair of questions
   about one product has J = 1 and only pairs of questions about *different* products can have J ≤ 0.2. Those pairs need
   two products whose questions embed within 0.15 of each other, and a corpus of 152 mostly different products has few.

## Limits of this check

- Name similarity is measured by token overlap of the short names and by the first title word. A better name feature might
  do better; this check does not show that none exists.
- Five product pairs is a small sample; "does not predict" here means "no support yet".
- The policy twins (L3) are a different mechanism and are not covered.
