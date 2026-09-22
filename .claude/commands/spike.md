---
description: Feasibility spike — measure the memory envelope and record mu_gen. SPENT: the envelope is already frozen
---

> ⚠️ **This spike has already been run and its result is frozen.** ADR-017 froze `num_ctx = 8192`
> and `OLLAMA_NUM_PARALLEL = 4` at μ_gen ≈ 28.2 tok/s from the 2026-08-15 run, and ADR-021 replaced
> the generation model on its evidence. **Re-running it does not re-freeze anything**: a different
> result is a reason to write an ADR, not a reason to change a value. Kept because the method is
> what the write-up's design chapter has to describe, and because a hardware change would need it
> run again — under a new ADR, never silently.

Run the feasibility spike. **This blocks all ingestion** (ADR-017) and must complete before the
embedding model and chunking config are frozen.

## Why this exists

`num_ctx = 8192` was never checked against a memory budget. KV cache at 8,192 tokens costs on the order
of a gigabyte **per concurrent sequence**, while prompts here run ~1.5–2.5K tokens — so it may be
over-provisioned by ~2×, and that difference decides whether `OLLAMA_NUM_PARALLEL ≥ 2` is reachable at
all. Both values are frozen study-wide, so they must be set from measurement, before ingestion, never after.

## Procedure

1. **Baseline** — everything else closed: `vm_stat`, `memory_pressure`, `sysctl hw.memsize`.
2. **Model footprint** — `ollama pull` the chosen tags, run one generation, record resident size from
   `ollama ps` and the on-disk size.
3. **The grid** — `num_ctx ∈ {4096, 8192} × OLLAMA_NUM_PARALLEL ∈ {1, 2, 4}`. Per cell, drive sustained
   concurrent generations with realistic ~2K-token prompts and record:
   - peak footprint · `memory_pressure` zone · `sysctl vm.swapusage`
   - **aggregate tokens/sec → this is μ_gen**
4. **Repeat surviving cells** with Redis and a stub Python service resident.
5. **Freeze** the largest pair that holds **green** under sustained load.

## Outputs — all three are required

- The **memory-budget table** in `experiment-protocol.md` §1.1, `TODO(spike)` cells filled.
- **ADR-017** flipped from Open to Decided, recording the frozen `num_ctx` and `OLLAMA_NUM_PARALLEL`.
- **μ_gen** recorded — it is the denominator of every load-conversion claim in proposal §3.

Writing these touches frozen values, so the guard will block until ADR-017 is cited in the active task's
`approvals.md`. That is the intended path: `/adr` first, then the edits.

## Go / no-go

- No green cell at `OLLAMA_NUM_PARALLEL ≥ 2` → the admission pool admits one generation at a time and
  "bounded concurrency pool" degenerates to a mutex. The thesis survives, but proposal §5/§6.2 must be
  reframed around queueing and shedding **before the Aug 31 report**.
- **Not even `NUM_PARALLEL = 1` green at `num_ctx = 4096`** → the binding constraint is the model, not
  concurrency. Escalate to a smaller quantization or model. That breaks ADR-002's freeze, so it must
  happen before ingestion.

Report the chosen pair, μ_gen, the headroom, and which go/no-go branch was taken.
