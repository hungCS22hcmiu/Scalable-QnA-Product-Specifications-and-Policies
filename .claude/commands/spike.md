---
description: W5 feasibility spike — measure the memory envelope, freeze it, record μ_gen
---

Run the feasibility spike. **This blocks all W5 ingestion** (ADR-017) and must complete before the
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
  happen now, in W5, before ingestion.

Report the chosen pair, μ_gen, the headroom, and which go/no-go branch was taken.
