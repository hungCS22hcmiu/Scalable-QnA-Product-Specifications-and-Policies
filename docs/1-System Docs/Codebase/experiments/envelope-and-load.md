# `experiments/` — the envelope check and the load tools

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `scripts/env_check.py` (578 lines),
`scripts/loadgen_footprint.py` (1,087), `scripts/load_burst.py` (185), `scripts/verify_admission.sh` (104),
`k6/ask.js` (186), `k6/mu_hit.js` (291). The decisions are ADR-001 (co-hosted load), ADR-003 (one slot) and ADR-017
(no prompt cache).

## 1. Purpose

They check that the machine is in the **frozen state** before a run, and they **generate load** against the gateway.
They serve **S1/S2** (Headline A) and **C3**: a number taken outside the frozen envelope, or with a load generator
that lies about failures, is not admissible.

## 2. Boundaries

- **Load generation is co-hosted** (ADR-001): k6 runs on the same machine, so goodput and μ_hit are **lower bounds**,
  the shed rate is an **upper bound**, and latency percentiles are reported only with k6's own CPU use.
- `make measure` is the **gate** for a measured run: green memory pressure, `env-check`, `redis-check`. A yellow or
  red run is invalid and must be repeated.

## 3. The scripts

### `env_check.py` — `make env-check`

Reads the **live runner**, never the requested configuration. Finding F1 is why: `OLLAMA_NUM_PARALLEL=4` was requested
and checked for seven weeks while Ollama served one slot. It loads both models (about 2.1 GB).

| Frozen value | Observed from |
| :--- | :--- |
| slot count (1) | the runner's argv (`-np`) **and** its own `/props` (`total_slots`) |
| `num_ctx` (8192) | argv `-c` = num_ctx × slots, and `/props` per-slot `n_ctx` |
| Ollama version (0.33.2) | the server's `/api/version` |
| the LLM weights blob | the tag's `FROM` blob, the runner's `--model`, and `/props` `model_path` |
| prompt cache off (ADR-017) | argv `--cache-ram`, else `LLAMA_ARG_CACHE_RAM` in the runner's environment (`ps eww`); unset fails |
| context checkpoints off (ADR-017) | argv `--ctx-checkpoints`, else `LLAMA_ARG_CTX_CHECKPOINTS`; unset fails |

argv is what Ollama **asked of** the runner; `/props` is what the runner **did**; they must agree. It picks exactly one
`llama-server` whose model is the frozen blob and whose parent is the Ollama server. It **fails closed** when anything
cannot be established, and prints an `ENVELOPE` line a run can be re-checked against. Not checked: the runner's batch
size (`-b 512` or `1024`), an open finding.

### `k6/ask.js` — the load scenario for `POST /ask`

Run by `make load-smoke` (a shakedown, not a measurement) and, later, by the Phase 7 sweep. What it is careful about:
1. **A 503 is not a failure.** It is the shed contract; counting it as an error would make overload look like a
   defect exactly where the gateway behaved correctly.
2. **Goodput excludes sheds.**
3. **Query choice is Zipf with a swept skew**, never uniform (the cache would look useless) and never a fixed cycle
   (it would look perfect). Redundancy is the independent variable.
It sends each record's `product_id`, and draws from **one split file**.

### `k6/mu_hit.js` — the μ_hit probe (item 7.2), `make mu-hit`

Measures the hit-path rate. The cache is **pre-warmed and the warm-up verified** in `setup()` (excluded from the
metrics); **a mid-run MISS fails the probe** (usually a capacity smaller than the probe set); Tier 1 and Tier 2 are
**reported separately**; saturation is checked, not assumed. Co-hosted, its result is a **lower bound**. It matters
because `h* = μ_hit / (μ_gen + μ_hit)`: a μ_hit at or below about 16 req/s would change the capacity argument.

### `loadgen_footprint.py` — `make footprint` (item 1.6)

**Exploratory**: what a co-hosted k6 costs the machine (CPU and memory), at the sweep's rates. k6 runs as a **child**,
so its exit status, total CPU and peak memory come from `os.wait4`; CPU is a difference of cumulative `ps cputime`,
never `ps %cpu` (a decayed average on macOS). It imports nothing from `rag`, so LlamaIndex is not in the instrument's
own memory. **It deletes the `t1:`, `t2:` and `lru:` cache keys** before its mixed rows. Result: k6's CPU % ≈ 0.81 +
0.124 × req/s (ADR-001).

### `load_burst.py` and `verify_admission.sh` — hand checks of admission

`load_burst.py` fires a large mixed batch (new questions, duplicates, paraphrases) to watch the pool, the queue, the
shed and coalescing under load. `verify_admission.sh` (`make verify-admission`) fires 8 distinct and 5 identical
questions; with one permit and `GEN_QUEUE_BUDGET=0` it expects 1 × 200 and 7 × 503, and one shared generation. It was
run on `v1` on 30 Oct 2026 and gave exactly that (`Admission Control.md` §12). **Neither is a measurement.**

## 4. Callers and callees

- `make env-check`, `make measure`, `make load-smoke`, `make mu-hit`, `make footprint`, `make verify-admission`.
- They call the gateway over HTTP, Ollama's API, `ps`, `sysctl`, `vm_stat` and `footprint`.

## 5. Tests that pin them

`experiments/tests/test_env_check.py`, `test_env_check_runner_cache.py` (the runner parsing and every refusal) and
`test_loadgen_footprint.py` (the parsing of `ps` output, the sampling arithmetic). The k6 scripts and the two hand
checks have no unit tests.

## 6. Silent failures to watch

- **Checking the requested value instead of the live runner** (finding F1).
- **k6 counting a 503 as an error**, or counting sheds in goodput.
- **Reading a co-hosted μ_hit as a ceiling**: it is a lower bound.
- **Running at yellow pressure**: the result is invalid. `make measure` refuses it.

## 7. Commit

`29b24a6`; `verify_admission.sh` changed after it, on 30 Oct 2026 (uncommitted: `v1` products and the `local` fix).
