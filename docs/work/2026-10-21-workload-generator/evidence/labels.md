# Pass-1 labels — item 3.4 (written by `make workload-labels`)

## Yield: Claude-answerable among the labelled spec questions

| Department | R2-answerable | R2-unanswerable (sample) | Both |
| :--- | ---: | ---: | ---: |
| electronics | 94 / 297 | 1 / 40 | 95 / 337 |
| furniture | 90 / 277 | 9 / 40 | 99 / 317 |
| laptops | 120 / 297 | 4 / 40 | 124 / 337 |
| phones | 123 / 309 | 7 / 40 | 130 / 349 |
| **all** | 427 / 1180 | 21 / 160 | 448 / 1340 |

U1 check: yield 448 against the floor 200 → continue.

## R2 against Claude (Claude's label as the reference)

- Precision of R2 (Claude-answerable among R2-answerable): 427 / 1180 (0.362, Wilson 95 % 0.3349 – 0.3897)
- NPV of R2 (Claude-unanswerable among the R2-unanswerable sample): 139 / 160 (0.869, Wilson 95 % 0.8077 – 0.9125)
  The sample is the first 40 per department in hash order, so the NPV estimates the pool's R2-unanswerable spec questions; the precision is a census.

## Repeat agreement (RELABEL = 40)

- Same answerable flag: 38 / 40 (0.950, Wilson 95 % 0.835 – 0.9862)
- Pass 1 answerable, repeat not: 0 · pass 1 not, repeat answerable: 2
- Both answerable, evidence overlapping (same field, spans intersect): 16 / 16

## Imports (evidence/batches.md)

- pass 1: 20 batches · 1898 rows accepted · 0 skipped · 1 rejected
- relabel: 5 batches · 40 rows accepted · 0 skipped · 0 rejected

## Policy assignments (R7 a)

| Department | assigned | ambiguous | not_covered | not_policy |
| :--- | ---: | ---: | ---: | ---: |
| electronics | 16 | 0 | 1 | 13 |
| furniture | 13 | 17 | 1 | 12 |
| laptops | 25 | 0 | 19 | 16 |
| phones | 22 | 16 | 1 | 2 |
| **all** | 76 | 33 | 22 | 43 |

Assigned, by document, shape and variant:

- policy-return-electronics · remedy: 1
- policy-return-electronics · start: 1
- policy-return-electronics · term: 5
- policy-return-laptops-new · term: 3
- policy-return-laptops-renewed · term: 1
- policy-warranty-electronics · remedy: 2
- policy-warranty-electronics · term: 7
- policy-warranty-furniture · except: 1
- policy-warranty-furniture · remedy: 1
- policy-warranty-furniture · term: 10
- policy-warranty-furniture · what: 1
- policy-warranty-laptops · except: 1
- policy-warranty-laptops · start: 2
- policy-warranty-laptops · term: 17
- policy-warranty-laptops · what: 1
- policy-warranty-phones-domestic · term: 4
- policy-warranty-phones-international · term: 18

Ambiguous, by kind and shape:

- return · remedy: 1
- return · start: 3
- return · term: 18
- return · what: 1
- warranty · remedy: 1
- warranty · term: 9

## Names, natural pairs and what pass 2 draws on

- Names: 152 of 152 products
- Natural pairs: different 6, same 36, unanswerable 190
- Spec seeds: 214 (2 per product; 62 products have fewer)
- Unanswerable seeds: 52 (13 per department at most)
