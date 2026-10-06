# Shakedown — plan step 5 (2026-10-06)

Exploratory. **No number from it is kept as evidence.** What is kept is what it found about the
instrument and the runbook, because three of the findings changed the approved design (recorded as
design.md v2.1 and in `approvals.md`).

Two short runs (8 req/s, 15 s, 1 repetition, all-hit row and mixed row) and one interrupted run, against
`make dev` with a throwaway `RUN_ID` and an absolute `RESULTS_DIR` in the session scratchpad.

| # | Found | Cause | Fix |
| :-: | :--- | :--- | :--- |
| 1 | `run` aborted before sampling: *no llama-server serves the LLM blob* | `resolve_sut` ran **before** the warm-up, but the runners do not exist until the models are loaded, and the warm-up is what loads them | Warm-up first, then `assert_models_loaded`, then `resolve_sut` |
| 2 | The mixed row aborted: *the refresh question was not a MISS in 3 tries* | The refresh sent a "novel" question through the gateway. Every such question is the same template, so the first was cached and the rest **Tier-2-hit it**: the embedder was refreshed and the LLM never was. The MISS assertion the review asked for is what caught it | The refresh now sends the request `make env-check` uses to load the frozen envelope: `/api/generate` with `options.num_ctx` and no prompt, and `/api/embed`. The service passes the same `options.num_ctx` (`rag/src/rag/generate.py`), so it asks for the same runner. The post-checks stay: `ollama ps` must show the LLM at `num_ctx`, and the runner PIDs must be unchanged |
| 3 | The sampler's own cost was **5.07 % of a core, about 3× the k6 it measured** (1.80 %) | One `ps` over ~9 SUT pids costs ~25 ms per tick against ~3 ms for one pid; `sysctl` is ~2.4 ms | The SUT processes are sampled every 5th tick (`--sut-every`); k6 and the memory sysctls stay at every tick. The overhead fell to 2.2–2.7 % on a **15 s** row, which exaggerates fixed costs (two `footprint` calls). It is still the same order as k6 at 8 req/s. **It is reported beside k6's figure, and Phase 7 inherits it** |
| 4 | Redis held 64 `t1:` and 20 `t2:` entries after two short runs | The mixed workload is **seeded**, so a second repetition finds the whole workload cached by the first; the repetitions would not be samples of the same cold-start regime | `flush_cache()` (prefix-only: `t1: t2: dep: entry: lru:`, never `corpus:`, verified) runs at the start of `run` and **before every mixed repetition**. It deletes keys, not `FLUSHALL`, so the `idx:cache` index survives. The "no reset at the start" line of design v2 was right for the all-hit rows only |
| 5 | A table cell for the SUT's CPU was missing | Acceptance 2 lists the SUT's total CPU; only the CSV columns existed | `summarize` now renders a SUT-CPU table over the same window. An all-hit row of 15 s shows "—" (only one SUT sample falls inside the 5–10 s window); a 60 s row has ~10 |
| 6 | `SIGTERM` to the sampler while a **real** k6 ran | — | Exit status 143, **no k6 left behind**, and the interrupted row wrote no `run-*.json`, so it cannot enter a table |
| 7 | The `top` spot check in probes.md U1 still disagrees (79.2 % for a ~100 % busy loop) | Unexplained | Not used; recorded |

**What the shakedown did not exercise:** a 60 s row (so no steady-state window of the real length), more
than one repetition, rates above 8 req/s, and the ratio of the SUT's CPU to k6's under the all-hit regime.
