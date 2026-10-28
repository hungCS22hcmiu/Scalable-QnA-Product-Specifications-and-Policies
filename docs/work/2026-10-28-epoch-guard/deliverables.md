# Deliverables — Epoch-guarded write-back

Closed 2026-10-28 · super-plan item 4.2 · carries out ADR-008, no new ADR (`interfaces.md` v0.18)

## What shipped

- **The epoch is real.** It is one integer ≥ 1 in the file named by `DATASET_EPOCH_FILE`, never in Redis.
  - The Makefile exports `$(CURDIR)/data/dataset-epoch`, which is gitignored.
  - `rag/src/rag/epoch.py` reads it, and advances it under a file lock with a temp file and a rename.
  - `make epoch-advance` and ingest (after every chunk is written) advance it.
- **Python stamps the epoch it read first,** before any chunk text, in `Retrieve` and `Answer`.
- **The gateway discards a stale write-back.** If the epoch now differs from Answer's, in either direction,
  or cannot be read, there is no tier write and no registration. The client still gets the answer, and the
  leader's record has `writeback_discarded: true`, `entry_id ""` and `entry_sources` null. A coalesced
  follower's record is not flagged.
- **The deps writer closes the late gap.** A registration whose epoch is no longer current is tombstoned
  and purged from both tiers, not registered, and counted in `LateDiscards`, which the gateway logs at
  shutdown.
- **Both services refuse to start** when the file is unset, empty, relative, missing, not an integer, or
  below 1.

## Files changed

- Python: `epoch.py` (new), `server.py`, `retrieve.py`, `ingest.py` (`_write_index` split out), `config.py`.
- Go: `deps/epoch.go` (new), `deps/deps.go`, `deps/doc.go`, `httpapi/handler.go`, `cmd/gateway/main.go`,
  `telemetry/evallog.go` (comment; gofmt re-aligned the block).
- `Makefile` (export, `epoch-advance`, `epoch-race-check`), `.gitignore`, `experiments/scripts/epoch_race_check.py`.
- New tests: `rag/tests/test_epoch.py`, `rag/tests/test_server_epoch.py`, `deps/epoch_test.go`,
  `deps/late_test.go`, `httpapi/epoch_guard_test.go`, `cmd/gateway/epoch_env_test.go`,
  `cmd/gateway/epoch_wiring_test.go`. No existing test was edited.
- Docs: `interfaces.md` v0.18 (§E file and rules, §H row, I13), `architecture.md`,
  `Redis-Data Structure.md`, `super-plan.md` (row 4.4 hand-off, row 4.2), `decisions.md` (ADR-008 status).

## How it was verified

The main session re-ran these on 2026-10-28, one at a time, after the executor and again after Phase 5.

| DC | Command | Result |
| :--- | :--- | :--- |
| 1 | `pytest tests/test_epoch.py -k "advance or read"`; `go test -run TestEpochFile`; the grep | 13 passed; 3 pass; grep empty |
| 2 | `pytest tests/test_server_epoch.py` | 6 passed |
| 3–6 | `go test -run TestEpochGuard ./internal/httpapi/` | 6 pass |
| 7 | `go test -run TestLateRegistration ./internal/deps/` (DB 14) | 3 pass, no SKIP |
| 8 | `go test -run TestEpochFromEnv`; `pytest -k "check or serve"` | 2 pass; 8 passed |
| 9 | `go test -run TestMainWiresEpoch ./cmd/gateway/` | pass |
| 10 | `make epoch-race-check` | every check PASS, twice (see Numbers) |
| 11 | greps on `interfaces.md`, `architecture.md`, `Redis-Data Structure.md`, super-plan row 4.4 | all present; no stale "not built" |
| 12 | `make verify`, alone, Go test cache cleared | exit 0; no FAIL; no SKIPPED target (`evidence/verify-review.out`) |
| 13 | `git status`; `shasum -c evidence/test-hashes-before.txt` | new files only; 62 of 62 unchanged |

The item's "Done when" is met. Forcing the race gave `writeback_discarded: true`, and no `t1:`, `t2:` or
`entry:` key appeared for that request (DC 10). The "edit" in that run was an epoch advance; a real
policy text edit needs item 4.4.

## Numbers

DC 10 is a functional check, not a measurement: `citable: no`. It ran against the `dev-v0` corpus in Redis,
with the default thresholds, `MUTATION=on` and its own temp epoch file. Memory pressure was level 2 (yellow)
before and after both runs.
- **Executor's run** (`evidence/race/`): B took 7.8 s and the epoch advanced at +1.5 s.
- **Main session's run** (`evidence/race-recheck/`): B took 11.0 s and the epoch advanced at +1.5 s.

## Deferred and follow-ups

- **Item 4.4 must test the edit order** (new text, then advance, then `Invalidate`; design §3 failure mode
  10). It is written into row 4.4.
- **Hits do not compare epochs.** A Redis restore mid-run is not detected (design §3 Unknowns). Within one
  process, 4.1's tombstones still refuse a purged entry.
- **`advance()` also refuses a file holding 0.** That fits "never a silent reset", but no test pins it.
- **The live script leaves its temp directory** (the gateway binary and a copy of the results) under
  `$TMPDIR`. `rag.server` prints a `KeyboardInterrupt` traceback on SIGINT, and the stop itself works.
- **Go Redis tests empty `FT._LIST`** (4.1 §4). The first RAG query rebuilds `idx:corpus`.
- **Carried from 4.1:** a failed purge still deletes `dep:{chunk}`. The reset for run rule 11 has no owner.
