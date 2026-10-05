# Spec — rag-server-reuseport

**Scope:** S · **Opened:** 2026-10-05 · **Kind:** bugfix · **Phase:** 1, a follow-up, not an
exit-clause item. It was found while closing `pqa-category-choice` and `resolve-f1`, and widened
while closing 1.4 (`super-plan.md`, "Found while closing 1.1" and "Found while closing 1.4").

## The bug, and its two causes, each in one sentence

A run can be answered by a stale `rag.server` with no error anywhere, because of two causes. Both
were reproduced on 2026-10-05 (`evidence/repro.txt`).
- **(a)** `rag/src/rag/server.py:54` builds its gRPC server with grpcio's defaults, which enable
  `SO_REUSEPORT`. So a second `rag.server` binds `0.0.0.0:50051` alongside a stale one, and the
  kernel splits connections between them silently.
- **(b)** `make dev` starts the server as `( cd $(RAG) && $(PY) -m rag.server ) &`. Under
  `/bin/bash` 3.2, `$!` is the subshell, so the recipe's trap kills the subshell and **orphans**
  the server, which keeps holding the port (`Makefile:122-124`).

Together they produced the six stale instances of 2026-10-03.

## The fix: restore what was intended

- **(a)** Build the server with `options=[("grpc.so_reuseport", 0)]`. A second server on the same
  address then fails at bind with `RuntimeError`, so `make dev` reports *"rag.server exited on
  startup"* instead of sharing the port. A restart right after a kill still works, because
  `SO_REUSEADDR` is unaffected (`evidence/repro.txt`). For testability, `serve()` builds its
  server through a small `build_server(addr)` that returns the server and its bound port.
  `serve()` is otherwise unchanged.
- **(b)** `exec $(PY) -m rag.server` inside the `make dev` subshell, as `make seam-check` already
  does, so `$!` is the server and the trap kills it. The startup-failure message gains a hint:
  another `rag.server` may hold `:50051`, see `lsof -nP -iTCP:50051 -sTCP:LISTEN`.

**Amendment, made during implementation (2026-10-05).** `exec` alone does not close (b)'s silent
path. `make dev` checks its server with `sleep 2; kill -0`. A new server that fails to bind only
after 2 s (import is ~1.6 s, slower under pressure) passes that check, and then the gateway dials
`localhost:50051` and reaches the **stale** listener. So `make dev` also gets a **port pre-check**,
as `make seam-check` already has. If anything already listens on the port, it fails, names the
PID, and starts nothing. Recorded in `approvals.md` as a default open to reversal.

**Second amendment, after `/ai-review` (2026-10-05).** The reviewer showed the pre-check can miss a
listener owned by another user, which leaves the `sleep 2` race behind it. `make dev` now waits up
to 30 s for **its own PID** to listen on the port before it starts the gateway, instead of
`sleep 2; kill -0`. It also requires `RAG_GRPC_ADDR` to end in a numeric `:port` (`review.md`,
findings 1 and 2).

## Acceptance

1. **Witness first.** A pytest calls `build_server` twice on the same `127.0.0.1` port, with the
   first started, and asserts the second raises `RuntimeError`. It is written after the pure
   `build_server` refactor and **before** the option is added. It must **fail** on that tree,
   because the second bind succeeds. That failure is the bug, captured; it is recorded in
   `evidence/`.
2. With the option added, the witness passes, and so does a second test: a server stopped and
   rebuilt on the same port binds again (the restart path).
3. The (b) fragment, re-run with `sleep` as in `evidence/repro.txt` but in the fixed recipe's
   shape, leaves no orphan. Recorded in `evidence/`. There is no automated test, because nothing
   in this repo tests Makefile recipes; under (a), any orphan that survives now fails loudly.
4. `make verify` passes, and no existing test changes.

## Out of scope

- **The wildcard-versus-specific residual.** With (a) fixed, `0.0.0.0:P` and `127.0.0.1:P` can
  still both bind (BSD `SO_REUSEADDR`, which gRPC sets unconditionally). It is reachable only with
  a non-default `RAG_GRPC_ADDR`. `make seam-check` already refuses a taken port by any address.
  Recorded, not fixed.
- Gateway-side detection of a server without `texts` (2.1's, per its super-plan row).
- `make measure` does not start `rag.server` today, so it is not changed.

## Why S, not larger

- **The cause is not in `reuse/`, not in the wire contract (§B), and not in any code that handles
  a request.** It is a socket option at process start and a shell recipe.
- **No measured number or frozen value moves.** The fix only refuses a state, a shared port, that
  no valid run may be in.
- **The `build_server` extraction is structure only.** It exists so the witness can call exactly
  what `serve()` calls.
- **If the author reads the server bootstrap as "at a seam", this is L.** That is the author's call
  at `/approve`.

## Outcome so far (2026-10-05, before `/done`)

- **Witness:** `test_second_server_cannot_share_the_port` failed on the refactored tree with
  `DID NOT RAISE RuntimeError` (`evidence/witness-before-fix.txt`), and passes with the option.
  The restart test passes both before and after.
- **(b):** with `exec`, `$!` is the server; there is no orphan after the trap. `make dev` refuses
  beside a held `:50051` and starts neither `rag.server` nor the gateway (`evidence/after-fix.txt`).
- `make verify` is green: pytest 15 + 94, Go unchanged, ruff clean, no existing test changed.
  `make seam-check` passes against the refactored server at pressure 1
  (`evidence/seam-check-after-fix.txt`).
- After `/ai-review`: the real `make dev` recipe, driven by a stand-in server with no gateway,
  waits for a slow bind and fails on die, never-binds, a held port and a host-only address, with
  no stub left running (`evidence/dev-startup-checks.txt`). `make verify` is still green.
