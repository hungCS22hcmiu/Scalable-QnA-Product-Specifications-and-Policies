# Deliverables — Dependency map and blind purge (C2)

Closed 2026-10-28 · super-plan item 4.1 · no new ADR (`interfaces.md` v0.17)

## What shipped

- `gateway/internal/deps/` is built. One writer goroutine, fed by one buffered channel, owns `dep:{chunk_id}`
  (SET of `entry_id`) and the new `entry:{entry_id}` (HASH: `t1_key`, `source_chunk_ids`). Every write-back
  registers its entry, whatever its two cache writes returned, with no context. `Invalidate(event)` purges
  every dependent entry from both tiers and touches nothing else.
- **Tombstones on both hit paths.** The writer swaps a copy-on-write set of invalidated `entry_id`s in
  *before* it deletes anything. A Tier-1 hit or a Tier-2 candidate on such an entry is not served, and the
  record names it in `invalidated_entry_id`.
- **The Tier-1 delete is a compare-and-delete** (`cache.PurgeEntry`, one Lua script). It deletes `t1:k`
  only if that record still names the purged entry, so a newer entry on the same key survives.
- **Nothing is lost with no trace.** A full queue makes `Register` wait. A registration after `Close`, a
  failed registration write and a failed purge call are each counted (`Dropped`, `RegisterErrors`,
  `PurgeErrors`). The gateway logs them at shutdown.

## Files changed

- New code: `cache/purge.go`, `deps/deps.go`.
- Changed: `deps/doc.go`, `telemetry/evallog.go` (`InvalidatedEntryID`), `httpapi/handler.go`,
  `httpapi/cascade.go`, `cmd/gateway/main.go`.
- New tests: `cache/purge_test.go`, `deps/deps_test.go`, `deps/race_test.go`, `httpapi/invalidation_test.go`,
  `cmd/gateway/deps_wiring_test.go`. No existing test was edited.
- Docs: `interfaces.md` (v0.17: §E `entry:*`, register / purge / hit-path steps, ADR-008 note; §H
  `invalidated_entry_id`), `architecture.md`, `Redis-Data Structure.md` (§1 map, §8, §9 gap 5).

## How it was verified

The main session re-ran everything on 2026-10-28 after the executor, with Redis up and `-count=1`. Go is
under `gateway/`.

| DC | Command | Result |
| :--- | :--- | :--- |
| 1, 2, 3, 5a, 7 | `go test -v ./internal/deps/` | 10 named tests `--- PASS`, no SKIP |
| 4 | `go test -v -run TestPurgeEntry ./internal/cache/` | 3 tests pass |
| 5b | `go test -v -run 'TestInvalidated\|TestValidEntryIsStillServed\|TestMissRegistersItsEntry' ./internal/httpapi/` | 4 tests pass |
| 6 | `go test -race ./internal/deps/`; grep for `"dep:` / `"entry:` | `ok`, no race; only `deps/deps.go` |
| 8 | `go test -v -run TestEvictionLeavesDependencyRecordsAlone ./internal/cache/` | pass, unchanged |
| 9 | greps on the three docs | v0.17 header, version line and row; `entry:` record; §H row; no "not built" for `deps/` |
| 10 | `make verify` | exit 0 run alone with the Go test cache cleared; no SKIPPED target (see below) |
| 11 | `git status --porcelain -- '*_test.go'` | 5 lines, all `??` |
| 12 | `go test -v -run TestMainWiresDeps ./cmd/gateway/` | pass |

**DC 10 failed once first.** That was my run, not the code. I ran the Go tests in parallel with
`make verify`, and on this Redis a `FLUSHDB` on any DB drops every search index, so `idx:corpus` was
rebuilt mid-test (design.md §4; `evidence/verify-1-parallel-fail.out`,
`evidence/verify-3-uncached-pass.out`).

The item's "Done when" (a policy edit purges its dependents from `t1:` and `t2:` and leaves the rest) is
shown by DC 2. It runs through the Go call `Invalidate` on test chunk IDs `A`/`B`/`C` in Redis DB 14. The
purge reads no chunk type. No live edit was made, because no transport exists yet.

## Numbers

None. No step loaded a model or measured anything. Memory pressure was green (level 1) at the re-check.

## Deferred and follow-ups

- **A failed purge still deletes `dep:{chunk}`.** The failure is counted and logged (DC 7), but a second
  edit of the same chunk will not find that entry again. A fix is to keep `dep:{chunk}` when any purge failed.
- **Test flushes drop live indexes** (design.md §4). Never run Go Redis tests while a gateway or RAG run
  is live. No item owns a guard yet.
- **The shutdown window.** A write-back still running when `Close` runs is counted in `Dropped()`, not
  registered (the existing F-F finding).
- **Owned elsewhere:** the register-after-purge race and `writeback_discarded` (4.2, via
  `Registration.DatasetEpoch`); promoted Tier-1 keys (4.3); the edit transport, update set and
  completeness / precision script (4.4); the reset for run rule 11 (no owner).
- **`CLAUDE.md`** still says `deps/` is a stub and C2 does not exist. It is the author's file.
