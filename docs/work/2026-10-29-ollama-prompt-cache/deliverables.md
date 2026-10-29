# Deliverables — Ollama's runner keeps every prompt in RAM

Closed 2026-10-29 · super-plan item: none — blocks 7.1 and every citable run that loads the LLM · ADR-017

## What shipped

- **The fix, as configuration.** `make ollama-env` sets `LLAMA_ARG_CACHE_RAM=0` and
  `LLAMA_ARG_CTX_CHECKPOINTS=0` in launchd's environment, then relaunches Ollama.app through `env -i`,
  so no shell's environment reaches it. It must run after every reboot.
- **The guard.** `make env-check` now reads both settings from the live runner (argv first, then its
  environment) and fails when either is not 0, or cannot be read. It prints a
  `RUNNER_CACHE cache_ram=0 ctx_checkpoints=0 runner_pid=…` line before `ENVELOPE`.
- **The record.** ADR-017 (amends ADR-003) and `interfaces.md` v0.22. "1.7 GB resident" in `README.md`
  and `decisions.md` is corrected to the measured footprint.

## Files changed

- `experiments/scripts/env_check.py`: `CacheSetting`, `runner_env`, `runner_cache`, `check_runner_cache`,
  `runner_cache_line`, `_read_runner_env`, and two `main()` arguments. The edit hook re-wrapped the file
  at 88 columns, so about 120 of its 278 diff lines are the change (design §4 F7).
- `experiments/tests/test_env_check_runner_cache.py` (new, 21 tests). `test_env_check.py` is untouched.
- `Makefile`: `RUNNER_CACHE_RAM`, `RUNNER_CTX_CHECKPOINTS`, `env-check` arguments, the `ollama-env` target.
- `docs/decisions.md` (ADR-017, its Summary row, two "amended by ADR-017" notes),
  `docs/contracts/interfaces.md` (v0.22), `README.md`.
- The trail's `evidence/`. The two `prompts.jsonl` files hold Amazon-PQA text, so they sit under the
  gitignored `private/` with IDs-only manifests beside them (F5). Three env dumps were cut to their
  `LLAMA_*` / `OLLAMA_*` lines, because they held the RCA shell's tokens (F1).

## How it was verified (the main session's own re-run, 2026-10-29)

1. Witness: `pytest … -k fails_on_the_captured_cache_on_runner` → failed before the fix (`assert 0 == 1`, `evidence/phase1-witness.txt`), passes after.
2. `pytest experiments/tests/test_env_check_runner_cache.py` → 21 passed.
3. `pytest experiments/tests` → 778 passed; `git diff --quiet experiments/tests/test_env_check.py` → 0.
4. Variables unset, clean relaunch, `make env-check` → FAIL naming both settings; make exits 2, the script 1 (`evidence/recheck/dc4-*.txt`). DC 4 was reworded to say so (F4).
5. `make ollama-env` → 0; `make env-check` → 0, `RUNNER_CACHE cache_ram=0 ctx_checkpoints=0`, `ENVELOPE` last; `ollama serve` has 18 variables, both at 0, no `_` (`evidence/recheck/dc5-*.txt`).
6–8. `run_arm.py` (300 prompts) → `repeat.py` → `verdict.py` → all 8 lines PASS (`evidence/recheck/verdict.txt`).
9. The four record checks of step 7.9 → `1`, two Makefile lines, two `interfaces.md` hits, `OK`.
10. `make verify` → exit 0, no FAIL, no SKIPPED (`evidence/recheck/make-verify.txt`).

## Numbers

All are on Ollama 0.33.2, `qwen3.5:2b-q4_K_M`, `num_ctx` 8192, one slot. Prompts are built from the
`v1` validation split and sent straight to `/api/generate`: no gateway, no Redis cache. All are
**citable: no**.

| Run | Footprint | Speed (median) | Pressure |
| :--- | :--- | :--- | :--- |
| RCA, cache on, 50 prompts, `-b 512` | 3,066 → 7,088 MB (+82 MB per prompt) | prefill 479, decode 35.5 tok/s | 2 |
| Executor, fixed, 300 prompts, `-b 1024` | 3,059 after load; mean of 1–50 is 2,588, of 251–300 is 2,589 (+1 MB) | prefill 484, decode 34.8 tok/s | 2 on requests 1–3, then 1 |
| Main session re-check, same 300 prompts, `-b 1024` | 3,059 after load; 3,083 → 3,084 (+1 MB) | prefill 477, decode 33.4 tok/s | 1 |

- **Repeat prefill**, the same 658-token prompt three times:
  - executor run: 1.340, 1.334 and 1.359 s;
  - re-check: 1.373, 1.340 and 1.314 s;
  - before, with checkpoints on: 1.29 s, then 0.05 s.
- **Footprint at load:** 3.03–3.07 GB. The vision encoder is 855 MB of it, fixed (RCA, measured by
  hand). The level while serving varies between runs (2.58 or 3.08 GB), and it is flat in both (F6).

## Deferred and follow-ups

- **Batch size (F3):** the runner gets `-b 512` or `-b 1024`, and nothing pins or records it. Decide
  before Phase 7.
- **Phase 7 (item 7.1):** record the runner's footprint during the sweeps. That would catch a leak under
  0.4 MB per request, and the embedding runner's memory under load.
- **Reboot:** surviving a reboot is reasoned, not tested. At the first reboot, `env-check` should fail
  until `make ollama-env` runs.
- **The author's files:**
  - `CLAUDE.md`: the hardware-envelope bullet should name the two settings and `make ollama-env`;
    `:185–186` is true again only while they are set.
  - `Final_Proposal.md`: `:280`, `:333`, `:340`.
  - `docs/Issue_phase4.md`: Issue 1 can be marked resolved.
- **Issue 2** (tools still tied to `dev-v0`) is the next small task.
- The 4.4 run's full Ollama log (21 MB) rotated away during this task's restarts, as the author
  accepted. `E/live-4.4-server-log-excerpt.txt` is the record.
