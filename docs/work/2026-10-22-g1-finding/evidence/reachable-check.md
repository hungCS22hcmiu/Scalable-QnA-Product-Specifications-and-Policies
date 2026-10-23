# Reachable traps on the real workload — g1-finding, Block C step 16

Written by `tools/reachable_check.py` from `data/workload-v1.json` and the vectors file, through the gate's own
`reachable_traps`. Counts only. A trap is a record with a `probe_kind` other than `name-swap-same`; it is
reachable when its cosine with its `pair_of` partner is at least 0.85.

| scope | trap records | reachable | unique pairs | reachable pairs |
| :--- | ---: | ---: | ---: | ---: |
| validation | 129 | 74 | 99 | 45 |
| test | 155 | 108 | 112 | 67 |
| whole | 284 | 182 | 211 | 112 |

## By probe kind (reachable / records; reachable pairs / unique pairs)

| probe_kind | validation | test |
| :--- | :--- | :--- |
| condition-department | 16/16 · 8/8 | — |
| name-swap | 0/5 · 0/5 | 0/7 · 0/7 |
| natural | 2/4 · 1/2 | 2/6 · 1/3 |
| policy-condition | 40/40 · 20/20 | 80/80 · 40/40 |
| policy-kind | 0/6 · 0/6 | 1/3 · 1/3 |
| policy-region | 6/6 · 6/6 | 12/12 · 12/12 |
| spec-attribute | 10/52 · 10/52 | 13/47 · 13/47 |

## The three trap definitions agree

| split | by `probe_kind` | by `pair_of` | by stratum (B-within, B-cross) |
| :--- | ---: | ---: | ---: |
| validation | 129 | 129 | 129 |
| test | 155 | 155 | 155 |

Trap records that are mutual twins (each names the other): 146.

**Result: all expected counts reproduced.**
