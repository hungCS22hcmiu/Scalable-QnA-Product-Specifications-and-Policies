# Plan — rag-server-reuseport

Scope S: `spec.md` is the design document. This file holds the steps as executed and the outcome
that `/done` records.

## Steps

- [x] Reproduce both causes with no model loaded (`evidence/repro.txt`).
- [x] `/approve implementation` at scope S (2026-10-05).
- [x] Refactor only: `serve()` builds its server through `build_server(addr)`.
- [x] Witness first: `test_second_server_cannot_share_the_port` fails on the refactored tree with
      `DID NOT RAISE RuntimeError` (`evidence/witness-before-fix.txt`).
- [x] Fix (a): `options=[("grpc.so_reuseport", 0)]`. Witness and restart test pass.
- [x] Fix (b): `exec` in `make dev`, plus the port pre-check (amendment) and the `lsof` hint
      (`evidence/after-fix.txt`).
- [x] `make verify`; `make seam-check` against the refactored server at pressure 1
      (`evidence/seam-check-after-fix.txt`).
- [x] `/ai-review`: two low findings, both fixed: the listen poll replaces `sleep 2`, and the
      `:port` is validated (`review.md`, `evidence/dev-startup-checks.txt`).
- [x] `make verify` again after the Makefile change.

## Outcome — closed 2026-10-05

**Shipped.**
- `rag/src/rag/server.py`: `build_server(addr)`, with `SO_REUSEPORT` off. A second server on the
  same address raises `RuntimeError`.
- `Makefile` `dev`: `exec` (no orphan); port validation; a pre-check that refuses to start beside a
  held port; and the gateway starts only once its own server PID listens (≤ 30 s), not after a fixed
  `sleep 2`.
- `rag/tests/test_server_bind.py`: the witness, and the restart guard.

**Checks at close.** `make verify` green with nothing skipped: gofmt, vet, build, `go test`, ruff,
pytest 15 + 94. Proto drift none. `/ai-review`: no contract or wrong-number finding; two low gaps
fixed.

**Scope was honest, and it grew inside S.** The work never reached `reuse/`, the wire contract or a
measured path. It did grow twice inside the `make dev` recipe: the pre-check (found while
implementing) and the listen poll (from `/ai-review`). Both are shell guards for the same bug, both
recorded as amendments in `spec.md`. The growth shows the first spec under-specified (b): `exec` was
necessary but not sufficient.

**Frozen values or contracts:** none. No `run_id` exists, and none is invalidated.

**Deferred.** The wildcard/specific coexistence on macOS (`0.0.0.0:P` and `127.0.0.1:P`), which
needs a non-default `RAG_GRPC_ADDR`. Recorded in `spec.md` and `super-plan.md`; not worth a task
unless a non-default address is ever used.

**Follow-up worth a task:** none from this bug. Phase 1's next is 1.3.
