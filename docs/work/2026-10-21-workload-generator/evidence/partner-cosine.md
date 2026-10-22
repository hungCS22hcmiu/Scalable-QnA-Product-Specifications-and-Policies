# Partner cosine and reachable traps — item 3.4 (review F1, F3, F8)

Written by `tools/partner_cosine.py` from `data/workload-v1.json` and the vectors file; counts only. The build report does not show these.

## Each probe against its `pair_of` target

| probe_kind | n | median | max | ≥ 0.85 |
| :--- | ---: | ---: | ---: | ---: |
| condition-department | 16 | 0.951 | 0.968 | 16 |
| name-swap | 12 | 0.723 | 0.804 | 0 |
| name-swap-same | 10 | 0.763 | 0.793 | 0 |
| natural | 10 | 0.818 | 0.888 | 4 |
| policy-condition | 120 | 0.960 | 0.978 | 120 |
| policy-kind | 9 | 0.801 | 0.852 | 1 |
| policy-region | 18 | 0.960 | 0.976 | 18 |
| spec-attribute | 99 | 0.803 | 0.947 | 23 |

## Reachable traps

A trap is a probe other than `name-swap-same`. It is reachable when its cosine with its partner is at least 0.85.

| file | records | traps | reachable | trap fraction | reachable fraction |
| :--- | ---: | ---: | ---: | ---: | ---: |
| whole | 1274 | 284 | 182 | 0.2229 | 0.1429 |
| validation | 622 | 129 | 74 | 0.2074 | 0.1190 |
| test | 652 | 155 | 108 | 0.2377 | 0.1656 |

## Minimal-pair twins

| split | twin records | twin pairs |
| :--- | ---: | ---: |
| validation | 56 | 28 |
| test | 80 | 40 |

## Query pairs on one policy document, in different splits, cosine ≥ 0.85

| pair | count |
| :--- | ---: |
| cell against cell | 74 |
| with a D query | 8 |

## If the whole file were a run file (`ask.js` takes the file index as the rank)

| skew | share of traffic on test records |
| ---: | ---: |
| 0.8 | 0.170 |
| 1.1 | 0.064 |
| 1.4 | 0.016 |
