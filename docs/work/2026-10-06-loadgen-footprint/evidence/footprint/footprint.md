# Load-generator footprint — item 1.6

> **EXPLORATORY and INDICATIVE, unconditionally** (ADR-001). Memory pressure was recorded, never gated; the
> run is classified exploratory under standing constraint 4. Nothing here is a thesis result, and the
> Phase 7 p95 rule does not read this table: every co-hosted p95 is reported with k6's own concurrent CPU.

Gateway/rag git SHA `17bf221dd686` · tree dirty: True · **gateway/rag dirty: False** · k6 v1.7.1 (commit/devel, go1.26.1, darwin/arm64) · 8 logical cores (4 P + 4 E) · `OLLAMA_KEEP_ALIVE` 5m0s

Steady-state window: the ticks from 5 s after the child started to 5 s before its last tick (49 – 50 s of a 60 s run; the endpoints are tick times, which jitter). CPU is **% of one core** (100 = one core) and, beside it, % of the whole machine (a coarse divisor: the cores are not equal). RSS is `ru_maxrss` in 10^6 bytes, a floor under pressure; `phys_footprint` is as `footprint` reports it (MiB) and is read twice per row, so the figure shown is the larger of two spot readings, not an exact peak.

## All-hit regime (the 5-question smoke set after warm-up; Ollama idle)

| offered req/s | reps | achieved | k6 CPU mean (% core) | spread over reps | % machine | RSS peak MB | vus_max | sampler overhead (% core) |
| ---: | ---: | ---: | ---: | :--- | ---: | ---: | ---: | ---: |
| 2 | 3 | 2.01 | 1.01 | 0.88 – 1.10 | 0.126 | 54 | 40 | 2.66 |
| 8 | 3 | 8.01 | 1.94 | 1.82 – 2.04 | 0.242 | 56 | 40 | 2.39 |
| 16 | 3 | 16.02 | 2.70 | 2.28 – 3.20 | 0.337 | 56 | 40 | 2.29 |
| 32 | 3 | 32.02 | 4.80 | 4.58 – 5.10 | 0.600 | 59 | 40 | 2.75 |

**All-hit fit:** CPU % = **0.81** (fixed cost, intercept) + **0.124** × achieved req/s (marginal cost, slope; 0.0012 CPU-seconds per request). Total ÷ N is not used: at low rates the fixed start-up cost per request exceeds the marginal one.

## Per run

| run | status | k6 CPU mean | p95 / max per 1 s (quantised) | p95 / max over 5 s | RSS MB | footprint probes MB | dropped | T1 / T2 / MISS | shed | exit | discarded ticks | flags |
| :--- | :--- | ---: | :--- | :--- | ---: | :--- | ---: | :--- | ---: | ---: | ---: | :--- |
| allhit-r16-rep1 | kept | 2.28 | 4.0 / 5.0 | 3.0 / 3.2 | 49 | 24, 26 | 0 | 961 / 0 / 0 | 0 | 0 | 0 | — |
| allhit-r16-rep2 | kept | 3.20 | 5.0 / 5.0 | 3.5 / 3.6 | 56 | 23, 24 | 0 | 961 / 0 / 0 | 0 | 0 | 0 | — |
| allhit-r16-rep3 | kept | 2.61 | 5.0 / 5.0 | 3.0 / 3.2 | 56 | 24, 25 | 0 | 961 / 0 / 0 | 0 | 0 | 0 | — |
| allhit-r2-rep1 | kept | 0.88 | 2.0 / 3.0 | 1.3 / 1.4 | 53 | 21, 24 | 0 | 121 / 0 / 0 | 0 | 0 | 0 | — |
| allhit-r2-rep2 | kept | 1.10 | 3.0 / 3.0 | 1.5 / 1.6 | 54 | 21, 24 | 0 | 121 / 0 / 0 | 0 | 0 | 0 | — |
| allhit-r2-rep3 | kept | 1.04 | 3.0 / 3.0 | 1.3 / 1.4 | 54 | 22, 24 | 0 | 120 / 0 / 0 | 0 | 0 | 0 | — |
| allhit-r32-rep1 | kept | 5.10 | 7.0 / 8.0 | 5.4 / 5.6 | 59 | 24, 27 | 0 | 1921 / 0 / 0 | 0 | 0 | 0 | — |
| allhit-r32-rep2 | kept | 4.71 | 7.0 / 8.1 | 5.5 / 5.6 | 56 | 25, 27 | 0 | 1921 / 0 / 0 | 0 | 0 | 0 | — |
| allhit-r32-rep3 | kept | 4.58 | 7.0 / 7.0 | 5.2 / 5.4 | 57 | 24, 26 | 0 | 1921 / 0 / 0 | 0 | 0 | 0 | — |
| allhit-r8-rep1 | kept | 1.96 | 4.0 / 4.0 | 2.4 / 2.4 | 54 | 23, 24 | 0 | 481 / 0 / 0 | 0 | 0 | 0 | — |
| allhit-r8-rep2 | kept | 1.82 | 3.0 / 4.0 | 2.4 / 2.4 | 55 | 23, 25 | 0 | 481 / 0 / 0 | 0 | 0 | 0 | — |
| allhit-r8-rep3 | kept | 2.04 | 4.0 / 4.1 | 2.4 / 2.4 | 56 | 23, 25 | 0 | 480 / 0 / 0 | 0 | 0 | 0 | — |
| mixed-r8-rep1 | EXCLUDED | 0.00 | 0.0 / 0.0 | 0.0 / 0.0 | 34 | — | 0 | 0 / 0 / 0 | 0 | 107 | 0 | exit_status, unattained, errors_in_mixed, no_k6_summary, no_steady_window |
| mixed-r8-rep2 | EXCLUDED | 0.00 | 0.0 / 0.0 | 0.0 / 0.0 | 33 | — | 0 | 0 / 0 / 0 | 0 | 107 | 0 | exit_status, unattained, errors_in_mixed, no_k6_summary, no_steady_window |
| mixed-r8-rep3 | EXCLUDED | 0.00 | 0.0 / 0.0 | 0.0 / 0.0 | 34 | — | 0 | 0 / 0 / 0 | 0 | 107 | 0 | exit_status, unattained, errors_in_mixed, no_k6_summary, no_steady_window |

## SUT processes' CPU over the same window (% of one core; sampled every 5th tick)

| run | gateway | rag.server | redis | ollama serve | LLM runner | embed runner | SUT total | LLM runner RSS MiB (min – max) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| allhit-r16-rep1 | 1.3 | 0.1 | 0.4 | 0.0 | 0.2 | 0.5 | 2.4 | 13 – 16 |
| allhit-r16-rep2 | 1.9 | 0.2 | 0.5 | 0.0 | 0.2 | 0.4 | 3.1 | 14 – 14 |
| allhit-r16-rep3 | 1.5 | 0.1 | 0.4 | 0.0 | 0.2 | 0.4 | 2.5 | 13 – 14 |
| allhit-r2-rep1 | 0.2 | 0.1 | 0.2 | 0.0 | 0.5 | 0.4 | 1.4 | 2070 – 2334 |
| allhit-r2-rep2 | 0.3 | 0.2 | 0.2 | 0.0 | 0.5 | 0.4 | 1.5 | 2070 – 2071 |
| allhit-r2-rep3 | 0.2 | 0.1 | 0.2 | 0.0 | 0.4 | 0.4 | 1.4 | 2047 – 2070 |
| allhit-r32-rep1 | 3.4 | 0.2 | 0.6 | 0.0 | 0.2 | 0.4 | 4.8 | 14 – 14 |
| allhit-r32-rep2 | 3.1 | 0.1 | 0.6 | 0.0 | 0.2 | 0.4 | 4.4 | 13 – 14 |
| allhit-r32-rep3 | 3.0 | 0.1 | 0.6 | 0.0 | 0.2 | 0.4 | 4.4 | 14 – 14 |
| allhit-r8-rep1 | 1.0 | 0.2 | 0.3 | 0.0 | 0.2 | 0.4 | 2.0 | 19 – 2048 |
| allhit-r8-rep2 | 0.9 | 0.2 | 0.3 | 0.0 | 0.2 | 0.4 | 1.9 | 14 – 19 |
| allhit-r8-rep3 | 1.0 | 0.2 | 0.3 | 0.0 | 0.2 | 0.4 | 2.0 | 15 – 15 |
| mixed-r8-rep1 | — | — | — | — | — | — | — | — |
| mixed-r8-rep2 | — | — | — | — | — | — | — | — |
| mixed-r8-rep3 | — | — | — | — | — | — | — | — |

## Rows left out of the table

- `mixed-r8-rep1`: exit_status, unattained, errors_in_mixed, no_k6_summary, no_steady_window
- `mixed-r8-rep2`: exit_status, unattained, errors_in_mixed, no_k6_summary, no_steady_window
- `mixed-r8-rep3`: exit_status, unattained, errors_in_mixed, no_k6_summary, no_steady_window

## SUT memory readings, raw (never mapped to a colour: the sysctl's encoding is unverified)

| run | pressure level (min–max) | memstatus_level (min–max) | swap used MB (min–max) | swap-ins / swap-outs | page-ins / page-outs |
| :--- | :--- | :--- | :--- | :--- | :--- |
| allhit-r16-rep1 | 2 – 2 | 32 – 44 | 8356.06 – 8504.81 | 7980 / 11512 | 98377 / 587 |
| allhit-r16-rep2 | 2 – 2 | 40 – 42 | 8495.94 – 8495.94 | 256 / 0 | 6190 / 257 |
| allhit-r16-rep3 | 2 – 2 | 33 – 41 | 8471.94 – 8485.69 | 1620 / 880 | 16963 / 213 |
| allhit-r2-rep1 | 2 – 2 | 32 – 39 | 8396 – 8396 | 392 / 0 | 39852 / 225 |
| allhit-r2-rep2 | 2 – 2 | 35 – 40 | 8380 – 8388 | 168 / 0 | 10843 / 98 |
| allhit-r2-rep3 | 2 – 2 | 32 – 41 | 8380 – 8380 | 196 / 0 | 18539 / 307 |
| allhit-r32-rep1 | 2 – 2 | 38 – 40 | 8469.69 – 8469.69 | 310 / 0 | 3141 / 200 |
| allhit-r32-rep2 | 2 – 2 | 32 – 42 | 8437.69 – 8469.69 | 2447 / 0 | 28667 / 531 |
| allhit-r32-rep3 | 2 – 2 | 38 – 41 | 8429.69 – 8437.69 | 334 / 0 | 3568 / 198 |
| allhit-r8-rep1 | 1 – 2 | 39 – 55 | 8364 – 8380 | 1266 / 0 | 9937 / 88 |
| allhit-r8-rep2 | 2 – 2 | 33 – 40 | 8364 – 8460.06 | 531 / 6148 | 20249 / 431 |
| allhit-r8-rep3 | 2 – 2 | 42 – 45 | 8444.06 – 8444.06 | 235 / 0 | 3444 / 63 |
| mixed-r8-rep1 | — | — | — | 28 / 0 | 2190 / 0 |
| mixed-r8-rep2 | — | — | — | 8 / 0 | 453 / 0 |
| mixed-r8-rep3 | — | — | — | 8 / 0 | 1982 / 0 |

## Not settled by this run

- `ABANDONED` and `GENERATION_FAILED` counts are **vacuous for the all-hit regime** (nothing waits on a generation, so nothing reaches k6's 120 s timeout); they do not settle F-L or the k6-cancel question.
- CPU share is **not an interference measurement**: it does not measure cache, memory-bandwidth or scheduler contention against the embedding server.
