# Probes — plan step 1 (2026-10-06)

One-off commands, run from the session scratchpad; **no source in the repo was changed**. Machine state at
the time: macOS pressure sysctl read **2** (and `memstatus_level` 42–46), Ollama 0.33.2 running with no model
loaded, Redis up (44 `corpus:*`, 4 `t1:*`, 3 `t2:*`), k6 v1.7.1. These are **exploratory** readings under
standing constraint 4 and are not citable as measurements.

| # | Unknown | Result | Consequence for the design |
| :-: | :--- | :--- | :--- |
| **U13** | Does `Popen` lose the exit code once `os.wait4` has reaped the child? | **Confirmed.** Child exited **99**; `wait4` status decoded to 99; afterwards `Popen.poll()` returned **0** and `returncode` was **0**. | Exit status comes from `wait4` only; never `Popen.wait/poll/communicate` (design §3, F15) |
| **U3** | `ru_maxrss` unit | **Bytes.** A bare Python child reported `14,761,984` (14.7 MB; as KB it would be 14 GB). | Self-test T4 still asserts it with a known block |
| — | `wait4(WNOHANG)` while the child is alive | Returns `(0, 0, rusage)` with **all-zero rusage**, not `None` | The loop must never keep that value (design §3) — confirmed real |
| **U1** | Is the `cputime`-delta method right? | **Yes.** A single busy loop: ΔCPU **4.01 s** over Δwall **4.02 s** = **99.7 %** of one core. `ps %cpu` on a *fresh* busy loop also read ~98 % (it only diverges on varying load, so this probe cannot show it is wrong). **`top -l 2 -s 3` reported 79.2 % for the same process — unexplained**, and disagrees with both the cputime delta and the wall clock. | `top` is **not** used. The arbiter in the self-test is the child's own `process_time()`, as designed. The discrepancy is recorded rather than explained |
| **F11** | `ps -o cputime=` format | `MMM:SS.ss` with **no hour field**: `809:39.09`, `604:26.57`, `4631:14.66` (a 77-hour process) | `parse_cputime` must accept `M:SS.ss`; confirmed that a `HH:MM:SS` parser would misread these |
| **U2** | `footprint -p` without root | **Works** on a child (Python, 53 MB: **68 ms** CPU), on a non-child (`ollama serve`: 30 ms), on the LLM runner (**2,644 MB** footprint: **96 ms** CPU), on the embedding runner (40 MB: 40 ms), on the gateway (9,970 KB: 31 ms) and `rag.server` (131 MB: 30 ms) | Cost is 30–100 ms per call, so it stays out of the 1 Hz loop. Two calls on k6 per row ≈ 0.14 CPU-s per 60 s row, charged to the sampler's overhead. **Note:** the LLM runner's `phys_footprint` (2,644 MB) is above its RSS (2,254 MB) |
| **U4** | `--summary-export` beside `handleSummary` | **Works.** Attained run (5 rps × 6 s): `iterations` 30, `vus_max` 5, `goodput_requests` 30, `error_rate.value` 0, **`dropped_iterations` absent**. Unattained run (50 rps offered, 4 VUs, 0.5 s responses): `iterations` 48 (7.56/s), **`dropped_iterations` 253**. **k6 exited 0 in both** | `dropped_iterations` defaults to 0. **An unattained run does not fail k6**, so the 95 % rule is the only guard. `cache_tier2_hit` and `cache_miss` are **absent when zero** (a Counter that was never added to) — default 0. `vus_max` equals the preallocated `VUS` in the attained run, which confirms F12 |
| **U12** | `OLLAMA_KEEP_ALIVE` | **`5m0s`** in `~/.ollama/logs/server.log`; live `ollama ps` showed `UNTIL 4 minutes from now` one minute after a request | The per-row refresh design stands; the interval (≈ 80 s) is well inside it |
| **U14** | Cache key prefixes | `corpus:` (ingest), `t1:` (HASH), `t2:` (HASH, `idx:cache` ON PREFIX `t2:`), `dep:` (SET), `entry:`, `lru:entries` (zset); `demo-reset`'s own foreign-key guard lists exactly `corpus:|t1:|t2:|dep:|entry:|lru:` | The fallback flush deletes `t1:* t2:* dep:* entry:* lru:*` and **never `corpus:*`**; it leaves the `idx:cache` index in place (the gateway re-ensures it at startup) |
| **U7** | `RUN_ID` + absolute `RESULTS_DIR` through `make dev` | **As designed.** The gateway logged `evaluation log -> <scratchpad>/results/probe-u7-1/raw/requests.jsonl, answer text -> raw/answers/`; nothing appeared under `experiments/results/` or `gateway/`. Gateway banner: `admission permits=1 queue_budget=2`, **`cache_capacity=0 UNBOUNDED`** | Confirms decision 7. Note the unbounded cache and `queue_budget=2` for the mixed row's expectations |
| **U9** | Do the smoke questions return 200? | Question 1 (`what is the battery life of the EarBuds Pop 3`): **200, `cache: MISS`, 5.4 s**, model `qwen3.5-2b`, both models then resident (`qwen3.5:2b-q4_K_M` 1.6 GB, `nomic-embed-text` 370 MB, 100 % GPU, context 8192 / 2048). The other four are checked by the driver's warm-up | — |
| — | Which `llama-server` is which | Two children of `ollama serve`: the LLM runner is the one whose `--model` is `LLM_BLOB` (`sha256-7a3a8d55…`, pid 41480, RSS 2.25 GB); the other (`sha256-970aa74c…`, pid 41479, RSS 0.31 GB) is the embedding runner. Gateway listens on `:8080`, `rag.server` on `:50051`, Redis on `:6379` | PID resolution: by port for the three services; the LLM runner by `env_check.find_llm_runner(rows, LLM_BLOB, serve_pid)`; the embedding runner as the other `llama-server` child of the same parent, asserting exactly one |
| — | Does importing `env_check` pull in `rag`? | Its top-level imports are stdlib only; `config` is referenced inside `observe` (line ~277). **Unverified that the import is lazy** — a new test (T10) asserts `rag` is absent from `sys.modules` after importing the sampler | Add **T10** to the self-test |

## Open after the probes

- **Runner `footprint` cost under load** was measured with the models idle. It may differ during a row; the
  per-row overhead column will show it.
- **`top`'s 79.2 %** is unexplained. It does not affect the method (the arbiter is the child's own
  `process_time()`), but it should not be quoted as agreement.
- Nothing here overturns a design assumption. **One addition:** T10 (no `rag` import).
