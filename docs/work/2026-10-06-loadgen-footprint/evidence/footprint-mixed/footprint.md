# Load-generator footprint — item 1.6

> **EXPLORATORY and INDICATIVE, unconditionally** (ADR-001). Memory pressure was recorded, never gated; the
> run is classified exploratory under standing constraint 4. Nothing here is a thesis result, and the
> Phase 7 p95 rule does not read this table: every co-hosted p95 is reported with k6's own concurrent CPU.

Gateway/rag git SHA `17bf221dd686` · tree dirty: True · **gateway/rag dirty: False** · k6 v1.7.1 (commit/devel, go1.26.1, darwin/arm64) · 8 logical cores (4 P + 4 E) · `OLLAMA_KEEP_ALIVE` 5m0s

Steady-state window: the ticks from 5 s after the child started to 5 s before its last tick (49 – 50 s of a 60 s run; the endpoints are tick times, which jitter). CPU is **% of one core** (100 = one core) and, beside it, % of the whole machine (a coarse divisor: the cores are not equal). RSS is `ru_maxrss` in 10^6 bytes, a floor under pressure; `phys_footprint` is as `footprint` reports it (MiB) and is read twice per row, so the figure shown is the larger of two spot readings, not an exact peak.

## Mixed regime (Zipf over the smoke set + 300 suffixed variants; Tier-2, misses and sheds occur)

| offered req/s | reps | achieved | k6 CPU mean (% core) | spread over reps | % machine | RSS peak MB | vus_max | sampler overhead (% core) |
| ---: | ---: | ---: | ---: | :--- | ---: | ---: | ---: | ---: |
| 8 | 3 | 8.02 | 1.41 | 1.37 – 1.48 | 0.176 | 56 | 40 | 2.33 |

## Per run

| run | status | k6 CPU mean | p95 / max per 1 s (quantised) | p95 / max over 5 s | RSS MB | footprint probes MB | dropped | T1 / T2 / MISS | shed | exit | discarded ticks | flags |
| :--- | :--- | ---: | :--- | :--- | ---: | :--- | ---: | :--- | ---: | ---: | ---: | :--- |
| mixed-r8-rep1 | kept | 1.37 | 3.0 / 3.0 | 1.6 / 1.7 | 55 | 25, 27 | 0 | 263 / 84 / 41 | 93 | 0 | 0 | — |
| mixed-r8-rep2 | kept | 1.48 | 2.9 / 3.0 | 1.8 / 1.8 | 52 | 25, 28 | 0 | 269 / 75 / 56 | 81 | 0 | 0 | — |
| mixed-r8-rep3 | kept | 1.38 | 3.0 / 3.0 | 1.6 / 1.7 | 56 | 25, 27 | 0 | 278 / 91 / 49 | 63 | 0 | 0 | — |

## SUT processes' CPU over the same window (% of one core; sampled every 5th tick)

| run | gateway | rag.server | redis | ollama serve | LLM runner | embed runner | SUT total | LLM runner RSS MiB (min – max) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| mixed-r8-rep1 | 1.4 | 3.9 | 0.7 | 6.5 | 54.9 | 29.9 | 97.2 | 333 – 705 |
| mixed-r8-rep2 | 1.4 | 3.8 | 0.7 | 6.1 | 43.4 | 26.2 | 81.7 | 286 – 968 |
| mixed-r8-rep3 | 1.4 | 3.6 | 0.7 | 5.7 | 41.2 | 24.1 | 76.5 | 351 – 941 |

## Rows left out of the table

- none

## SUT memory readings, raw (never mapped to a colour: the sysctl's encoding is unverified)

| run | pressure level (min–max) | memstatus_level (min–max) | swap used MB (min–max) | swap-ins / swap-outs | page-ins / page-outs |
| :--- | :--- | :--- | :--- | :--- | :--- |
| mixed-r8-rep1 | 2 – 2 | 30 – 38 | 9006.06 – 9038.06 | 1547 / 0 | 25041 / 198 |
| mixed-r8-rep2 | 2 – 2 | 28 – 35 | 9133.38 – 9157.38 | 1083 / 908 | 9349 / 330 |
| mixed-r8-rep3 | 2 – 2 | 31 – 35 | 9125.38 – 9133.38 | 197 / 0 | 4055 / 215 |

## Not settled by this run

- `ABANDONED` and `GENERATION_FAILED` counts are **vacuous for the all-hit regime** (nothing waits on a generation, so nothing reaches k6's 120 s timeout); they do not settle F-L or the k6-cancel question.
- CPU share is **not an interference measurement**: it does not measure cache, memory-bandwidth or scheduler contention against the embedding server.
