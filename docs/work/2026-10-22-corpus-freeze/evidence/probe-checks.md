# Carried measurements — item 3.6, plan step 12

Written by `tools/probe_checks.py`. Counts only: no qa_id, no question text, no asin.
Recorded, not acted on. U10 and the sibling rate are on validation only (ADR-012).

## Evidence spans (U4)

| what | n |
| :--- | ---: |
| located | 777 |
| located, over more than one chunk | 94 |

## Retrieved-set sizes (beside G1)

**validation**

| size | scoped | unscoped |
| :--- | ---: | ---: |
| 1 | 230 | 0 |
| 2 | 134 | 0 |
| 3 | 67 | 0 |
| 4 | 42 | 0 |
| 5 | 149 | 622 |

**test**

| size | scoped | unscoped |
| :--- | ---: | ---: |
| 1 | 217 | 0 |
| 2 | 171 | 0 |
| 3 | 75 | 0 |
| 4 | 47 | 0 |
| 5 | 142 | 652 |

## U12 (a): J(scoped top-k, partner's scoped top-k), per probe

**validation**

| probe kind | n | no partner | 0 | (0, 0.2] | (0.2, 0.5] | (0.5, 1) | 1 | median |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| condition-department | 16 | 0 | 0 | 0 | 0 | 8 | 8 | 1.000 |
| name-swap | 5 | 0 | 5 | 0 | 0 | 0 | 0 | 0.000 |
| name-swap-same | 6 | 0 | 6 | 0 | 0 | 0 | 0 | 0.000 |
| natural | 4 | 0 | 0 | 0 | 0 | 0 | 4 | 1.000 |
| policy-condition | 40 | 0 | 0 | 0 | 34 | 6 | 0 | 0.429 |
| policy-kind | 6 | 0 | 1 | 2 | 3 | 0 | 0 | 0.250 |
| policy-region | 6 | 0 | 0 | 1 | 4 | 1 | 0 | 0.500 |
| spec-attribute | 52 | 0 | 0 | 0 | 8 | 6 | 38 | 1.000 |

**test**

| probe kind | n | no partner | 0 | (0, 0.2] | (0.2, 0.5] | (0.5, 1) | 1 | median |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| name-swap | 7 | 0 | 7 | 0 | 0 | 0 | 0 | 0.000 |
| name-swap-same | 4 | 0 | 4 | 0 | 0 | 0 | 0 | 0.000 |
| natural | 6 | 0 | 0 | 0 | 0 | 0 | 6 | 1.000 |
| policy-condition | 80 | 0 | 0 | 2 | 48 | 18 | 12 | 0.429 |
| policy-kind | 3 | 0 | 0 | 1 | 2 | 0 | 0 | 0.250 |
| policy-region | 12 | 0 | 0 | 0 | 5 | 4 | 3 | 0.667 |
| spec-attribute | 47 | 0 | 0 | 0 | 6 | 5 | 36 | 1.000 |

## U12 (b): do a probe's evidence span and its partner's share a chunk

`no span`: a policy cell has none, or the span was not found. The per-probe flags are in a
gitignored file; their sha256 is `0e6745e3d786450cbd452022ce5f7a6828aee5830ba04ee4bc371bb5a58f4929`.

**validation**

| probe kind | share a chunk | disjoint | no span |
| :--- | ---: | ---: | ---: |
| condition-department | 0 | 0 | 16 |
| name-swap | 0 | 5 | 0 |
| name-swap-same | 0 | 6 | 0 |
| natural | 4 | 0 | 0 |
| policy-condition | 0 | 0 | 40 |
| policy-kind | 0 | 0 | 6 |
| policy-region | 0 | 0 | 6 |
| spec-attribute | 30 | 22 | 0 |

**test**

| probe kind | share a chunk | disjoint | no span |
| :--- | ---: | ---: | ---: |
| name-swap | 0 | 7 | 0 |
| name-swap-same | 0 | 4 | 0 |
| natural | 4 | 2 | 0 |
| policy-condition | 0 | 0 | 80 |
| policy-kind | 0 | 0 | 3 |
| policy-region | 0 | 0 | 12 |
| spec-attribute | 28 | 19 | 0 |

## U11: is the seed's evidence chunk in the top-k

**validation**

| what | n |
| :--- | ---: |
| seeds with an evidence span | 101 |
| span located | 101 |
| any chunk of the span in the scoped top-k | 75 |
| all chunks of the span in the scoped top-k | 68 |
| any chunk of the span in the unscoped top-k | 75 |
| all chunks of the span in the unscoped top-k | 68 |
| span over more than one chunk | 10 |

**test**

| what | n |
| :--- | ---: |
| seeds with an evidence span | 97 |
| span located | 97 |
| span over more than one chunk | 12 |
| any chunk of the span in the scoped top-k | 66 |
| all chunks of the span in the scoped top-k | 61 |
| any chunk of the span in the unscoped top-k | 66 |
| all chunks of the span in the unscoped top-k | 61 |

## U10: `policy_frac` of the retrieval, validation only

**policy queries** (n = 158)

| policy_frac | n |
| :--- | ---: |
| 0.0 | 2 |
| 0.25 | 2 |
| 0.333 | 3 |
| 0.5 | 4 |
| 0.6 | 15 |
| 0.667 | 5 |
| 0.75 | 12 |
| 0.8 | 99 |
| 1.0 | 16 |

| band | SPEC | MIXED | POLICY |
| :--- | ---: | ---: | ---: |
| default, collapsed (Lo = Hi = 0.20) | 2 | 0 | 156 |
| candidate [0.20, 0.60) | 2 | 9 | 147 |

**D queries (a product and a policy)** (n = 33)

| policy_frac | n |
| :--- | ---: |
| 0.0 | 6 |
| 0.2 | 1 |
| 0.25 | 1 |
| 0.333 | 5 |
| 0.5 | 5 |
| 0.6 | 3 |
| 0.667 | 2 |
| 0.75 | 2 |
| 0.8 | 8 |

| band | SPEC | MIXED | POLICY |
| :--- | ---: | ---: | ---: |
| default, collapsed (Lo = Hi = 0.20) | 6 | 0 | 27 |
| candidate [0.20, 0.60) | 6 | 12 | 15 |

**product-only queries** (n = 431)

| policy_frac | n |
| :--- | ---: |
| 0.0 | 428 |
| 0.333 | 1 |
| 0.5 | 2 |

| band | SPEC | MIXED | POLICY |
| :--- | ---: | ---: | ---: |
| default, collapsed (Lo = Hi = 0.20) | 428 | 0 | 3 |
| candidate [0.20, 0.60) | 428 | 3 | 0 |

## Sibling rate, validation only

| what | n |
| :--- | ---: |
| twin records | 56 |
| top-k holds a chunk of its own document | 56 |
| top-k holds a chunk of the other twin's document | 51 |
| top-k holds both | 51 |
| top-k holds the other twin's document and not its own | 0 |

## Policy terms against the gateway's numeric unit list

| what | n |
| :--- | ---: |
| policy terms | 13 |
| terms read by a listed unit | 11 |
| terms read by a currency symbol | 1 |
| terms without a number | 1 |

