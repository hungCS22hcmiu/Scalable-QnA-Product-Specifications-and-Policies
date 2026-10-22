# Expected similar-pair counts — item 3.6, plan step 1

Written by `tools/expected_pairs.py` from `data/workload-v1.json` and the 3.4 vectors file,
before any gate run on `v1`. Counts only. These are the expected values for acceptance A3 (ii):
the gate's `similar_pairs` (cosine ≥ 0.85) must give the same three numbers.

Queries: 1274. Cosines are `corpus_gate._cosine_with_norms` on the stored vectors.

## Pairs with cosine ≥ 0.85

| where | pairs |
| :--- | ---: |
| inside validation | 663 |
| inside test | 554 |
| across the splits | 125 |
| **all** | **1342** |

## Pairs within ±0.001 of 0.85

A pair this close to the line is the one an embedding that moved in the last digits would flip.

| where | pairs |
| :--- | ---: |
| inside validation | 11 |
| inside test | 14 |
| across the splits | 11 |
| **all** | **36** (19 at or above the line) |

Nearest pair to the line: |cosine − 0.85| = 1.79e-05.
Largest numpy-against-gate difference over those pairs: 1.2e-15.
