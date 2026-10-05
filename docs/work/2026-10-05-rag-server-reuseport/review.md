# Review — rag-server-reuseport

## `/ai-review`, 2026-10-05

**Reviewer:** `contract-reviewer`, in the general pass over `docs/architecture.md`. The diff touches
no contract surface or wire field, and there is no scope-L design to review. Scope: `git diff`
(`rag/src/rag/server.py`, `Makefile` `dev`) plus `rag/tests/test_server_bind.py`. Read-only, with
`pytest rag/tests/test_server_bind.py` (4/4 runs pass) and `make -n dev`. It did not run `make dev`
or start any server.

**Verdict: no contract finding and no silent-wrong-number finding.** Two low-severity gaps in the
`make dev` pre-check, both **fixed**.

| # | Sev. | Finding | Check | Resolution |
| :---: | :---: | :--- | :---: | :--- |
| 1 | low | **The pre-check can miss a listener, and the `sleep 2` race was still there behind it.** `lsof` without root lists only the caller's sockets, so a stale `rag.server` owned by another user passes the pre-check (`Makefile`, `dev`). The new server's bind then fails (SO_REUSEPORT off), but `make dev` sees that only if the process exits inside the fixed `sleep 2`. If import plus bind takes longer, `kill -0` passes, the gateway starts, and it dials the stale server | PLAUSIBLE | **Fixed.** `sleep 2; kill -0` is replaced by a poll of up to 30 s, until **this PID** listens on the port (`lsof -a -p $rag_pid … -sTCP:LISTEN`). `lsof` always sees the caller's own process. The gateway now starts only once our server is serving; a bind failure is "exited on startup", and a server that never binds fails after 30 s. Exercised through the real recipe with a stand-in server (`evidence/dev-startup-checks.txt`): a 3 s bind waits and proceeds; die, never-binds and held port all FAIL; no stub is left running |
| 2 | low | **A host-only `RAG_GRPC_ADDR`** (e.g. `localhost`) leaves `rag_port=localhost`, so `lsof -iTCP:localhost` matches nothing and the pre-check passes silently | PLAUSIBLE | **Fixed.** The recipe requires the address to end in a numeric `:port` and fails before starting anything otherwise (`evidence/dev-startup-checks.txt`, "host-only") |

**Checked clean by the reviewer:**
- `serve()` is unchanged apart from the option: same address, start, print and wait.
  `build_server` is exactly what `serve()` calls, so the tests exercise the production path.
- The tests do not flake: port 0 is ephemeral, and rebinding after `stop().wait()` works.
- `exec` makes `$!` the Python process, and the quoting is correct.
- `seam-check` is the only other place that starts `rag.server`. It already uses `exec` and a
  private port.
- No `.proto`, §B, frozen value, eviction region, provenance field or measured path is touched.

**Doc follow-up noted by the reviewer:** the `super-plan.md` entries that describe this bug (the
"Found while closing 1.1" bullet and the "Found while closing 1.4" bullet) need their status
updated. Done at `/done`.

**Unresolved findings: none.** `/done` is not blocked.
