# Deliverables — Stop abandoned generations (F-L), and a graceful shutdown for rag.server

Closed 2026-11-10 · super-plan item: none — closes finding F-L (`docs/super-plan.md`), which gated 7.1 and 7.5

## What shipped

- **The stop reaches Ollama.** When an `Answer` RPC ends (the client left, or the shutdown grace ran out),
  rag.server closes its Ollama request within about 50 ms, and Ollama drops it. The request body and the
  prompt are unchanged.
- **Graceful shutdown.** On SIGTERM, and on SIGINT unless it was ignored at start, rag.server refuses new RPCs,
  waits up to `RAG_SHUTDOWN_GRACE_S` (default 60 s) for the calls in flight, then exits with code 0. A second
  signal ends it at once.
- **A residual, found in build** (design.md §4). Ollama frees its one slot only after it has read the whole
  prompt. A cancel during the prefill still holds the slot for the rest of that prefill, out of the gateway's
  sight. A whole prefill took 1.94 s for a 987-token prompt.

## Files changed

- `rag/src/rag/generate.py`: `Cancelled`, `stop_when`, `_request_body`, `_post_until_stop`. One
  `httpx.AsyncClient` per call replaces the module-level client. `_PROMPT_TEMPLATE` and `_build_prompt` are
  untouched.
- `rag/src/rag/server.py`: `_stop_on_rpc_end`, the stop in `Answer`, `_install_shutdown`, the `serve()` changes.
- `rag/src/rag/config.py`: `SHUTDOWN_GRACE_S` (not a frozen value).
- New tests: `rag/tests/conftest.py` (`FakeOllama`), `test_server_cancel.py` (6), `test_server_shutdown.py` (5),
  `serve_with_fakes.py` (the subprocess entry point, not collected).
- `docs/contracts/interfaces.md` v0.31 (§H `t_generate_ms` note, doc-only). `docs/super-plan.md`: F-L ✅.
- **Frozen values touched: none. Prior runs invalidated: none** (design.md §2). No ADR.
- Not this task: `gateway/cmd/gateway/main.go` (the gateway drain fix, made in chat on 2026-11-10) is also
  uncommitted.

## How it was verified

Main session re-run, 2026-11-10, after the executor:
- `make verify` → exit 0. ruff, go vet and go build are clean. Go tests ok (cached; no Go change). rag 94 passed,
  experiments 1117 passed. Nothing SKIPPED.
- DC 1 → 4 passed. The failure on the unfixed code is saved in `evidence/dc1_before.out`.
- DC 2 → 2 passed. The template and prompt sha256 equal `evidence/golden_before.out`.
- DC 3 → 3 passed (SIGTERM, SIGINT, SIGINT ignored at start). DC 4 → 2 passed.
- DC 5 → before: GAP 34.715 s. After, drop at 1 s: gap 1.258 s ≤ 1.94 s. After, drop at 4 s: PASS, gap
  0.040 s ≤ 0.5 s. 5 of 5 valid rounds in each.
- DC 6 → v0.31 on `interfaces.md` lines 3, 775, 954, 961; `While F-L is open` count 0; the super-plan ✅ line
  shows; `still gates` count 0.
- DC 7 → `git status --porcelain rag/tests` shows 4 new files, no ` M`.

## Numbers

All `citable: no`. Corpus `v1`, product `product-laptops-b07qvm5x8w`, the `make dev` demo stack (no `RUN_ID`).
- F-L probe gap, median of 5 minus median of 5: before the fix 34.715 s (pressure 2 → 1). After the fix,
  drop at 1 s: 1.258 s (1 → 1). Drop at 4 s: 0.040 s (1 → 2).
- Prefill, straight to Ollama, pressure 1: a 987-token prompt prefills in 1.94 s warm (about 506 tokens/s).
  A cut inside the prefill leaves the rest of it. A cut after it leaves 0.03 s (`evidence/rca_prefill*.out`,
  `evidence/rca_cancel_timing.out`).
- Per-call cost of the new client (U2): +15.9 ms median (old 0.547 ms, new 16.432 ms, 100 calls each,
  against an instant fake, no model; `evidence/bench_generate_overhead.out`).

## Deferred and follow-ups

- **Phase 7 (7.1, 7.5) must count the prefill residual.** An abandoned request can hold Ollama's slot for up
  to one prefill after the gateway frees its permit, so (1 + q) · S can be exceeded by that much. Nothing in
  scope removes it: the Ollama version and the runner flags are pinned.
- U2's +15.9 ms per generation is inside μ_gen when Phase 7 re-measures it.
- Steps 4.2–4.4 and Phase 5 are marked `- [-]`: replaced by Phases 6–7 after 4.2 failed (design.md §4).
- Two errors in Phase 6's text were fixed by hand: the v0.31 row's place and the bold markers (design.md §4).
- Out of scope, unchanged: F-D (a follower of a departed leader fails) and F-F (the eval log closes while
  draining).
- The F-L bullet keeps its old sentence "The F-A review recommends gating Phase 7", as history.
- `.ruff_cache/` in this folder is a stray cache. It is gitignored and can be deleted.
