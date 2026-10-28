# Plan — Dependency map and blind purge (C2)

Design: design.md (approved 2026-10-28)

**Before any step:** `redis-cli PING` answers `PONG` (redis-stack-server, CLAUDE.md). The new tests use Redis
DB 14 (`deps/`) and DB 15 (`cache/`, through the existing `testStore`). A test that prints `--- SKIP` because
Redis is down is a failed step, not a pass.

No step loads a model, so no memory-pressure check is needed and no step produces a citable number. Never edit
an existing `_test.go` file. `go test -run` with a pattern that matches nothing exits 0, so every test step runs
with `-v` and its Pass names the tests that must print `--- PASS`.

## Phase 1 — Implement

- [x] 1.1 The two-tier purge in `cache`.
  - Files: `gateway/internal/cache/purge.go` (new)
  - Do: `func (s *Store) PurgeEntry(ctx context.Context, entryID, t1Key string) error`. If `t1Key` is empty,
    `HGET t2:{entryID} t1_key` first (`redis.Nil` → empty). Then one Lua script (`redis.NewScript`), with
    `KEYS = {t2:{entryID}, lru:entries}` and `ARGV = {entryID, t1Key}`:
    `DEL KEYS[1]`; if `ARGV[2] ~= ''` and `HGET ARGV[2] entry_id == ARGV[1]` then `DEL ARGV[2]`;
    `ZREM KEYS[2] ARGV[1]`. Comment: the t1 key is passed in ARGV because its name is only known at run time;
    this is fine on the single standalone server the envelope fixes. Use `tier2KeyPrefix` and `lruKey`.
  - Run: `cd gateway && go build ./... && go test -count=1 ./internal/cache/`
  - Pass: builds; existing cache tests pass (with Redis up, none skipped).
  - Result: added gateway/internal/cache/purge.go (PurgeEntry + Lua compare-and-delete); builds; 16 existing cache tests PASS, 0 SKIP.

- [x] 1.2 The `deps` package.
  - Files: `gateway/internal/deps/deps.go` (new); keep `doc.go`, and update its comment to say what is built.
  - Do, exactly as design §3 "Files":
    - Types `Registration`, `Event`, `Purger`; `Map` with `rdb`, `purge`, `ch chan op`, `mu sync.RWMutex`,
      `closed bool`, `snap atomic.Pointer[map[string]struct{}]` (starts as an empty map), `done chan struct{}`,
      and three `atomic.Int64` counters (`dropped`, `registerErrors`, `purgeErrors`).
    - `op` carries either a `*Registration` or an `*Event` plus an `ack chan invalidateResult`.
    - `New(rdb, p, queue)` makes the channel with capacity `queue` and starts `go m.run()`.
    - `Register(r)`: `mu.RLock()`; if `closed`: `RUnlock`, `dropped.Add(1)`, log once per call, return. Else
      send on `ch` (blocking while full), then `RUnlock`. No context parameter.
    - `Invalidate(ev)`: same lock pattern; if closed return an error; send an op with a fresh `ack` channel,
      `RUnlock`, then wait on `ack` and return its IDs and error.
    - `Invalidated(id)`: `_, ok := (*m.snap.Load())[id]; return ok`.
    - `Close(ctx)`: `mu.Lock()`; if already closed unlock and return nil; set `closed`, `close(ch)`, unlock; wait
      for `done` or `ctx.Done()` (return `ctx.Err()`).
    - `run()`: `for op := range m.ch { … }`, then `close(m.done)`. A writer context is `context.Background()`.
      Registration: one `TxPipeline` with `SADD dep:{c} E` per source and `HSET entry:E t1_key <k>
      source_chunk_ids <json>`; on error `registerErrors.Add(1)` and log. Invalidation: `SMEMBERS dep:{chunk}`;
      on error, ack the error and continue with the next op. Otherwise copy the snapshot map, add the IDs,
      `snap.Store`, ack the IDs. Then for each ID: `HGET entry:E t1_key` (nil → ""), `purge.PurgeEntry(ctx, E,
      t1)`, `DEL entry:E`; any error → `purgeErrors.Add(1)`, log, continue. Finally `DEL dep:{chunk}`
      (an error is a purge error).
    - `Dropped()`, `RegisterErrors()`, `PurgeErrors()`.
    - Key strings `"dep:"` and `"entry:"` appear in this file only.
  - Run: `cd gateway && go build ./... && go vet ./internal/deps/`
  - Pass: builds; vet clean.
  - Result: added gateway/internal/deps/deps.go (Map, writer goroutine, COW snapshot, 3 counters) and updated doc.go; builds, vet clean.

- [x] 1.3 The record key.
  - Files: `gateway/internal/telemetry/evallog.go`
  - Do: add `InvalidatedEntryID string` with tag `json:"invalidated_entry_id,omitempty"` near `EntryID`, with a
    comment: §H v0.17 extension, present iff the request met an entry the dependency map had invalidated and did
    not serve it; names the first such entry.
  - Run: `cd gateway && go build ./... && go test -count=1 ./internal/telemetry/`
  - Pass: builds; existing telemetry tests pass.
  - Result: added InvalidatedEntryID (omitempty) to telemetry.Record in the extension block; builds; telemetry tests pass.

- [x] 1.4 The hit-path checks and the registration in `httpapi`.
  - Files: `gateway/internal/httpapi/handler.go`, `gateway/internal/httpapi/cascade.go`
  - Do:
    - In `handler.go`: `type dependencyMap interface { Register(deps.Registration); Invalidated(entryID string)
      bool }` and a `Deps dependencyMap` field on `Handler`, commented: nil disables both (struct-literal tests),
      `cmd/gateway` always sets it (DC 12).
    - Tier 1: just before `if hit {`, add: if `hit && h.Deps != nil && h.Deps.Invalidated(entry.EntryID)` then
      `rec.InvalidatedEntryID = entry.EntryID` and `hit = false`. The request then goes on as a Tier-1 miss.
    - Write-back, inside the generation closure, after the `Put` and `PutTier2` blocks and before `h.touch`:
      if `h.Deps != nil`, `h.Deps.Register(deps.Registration{EntryID: entryID, Sources:
      result.SourceChunkIDs, T1Key: t1Key, DatasetEpoch: result.DatasetEpoch})`. Comment why it runs whatever
      the two writes returned, and why it takes no context (design §3).
    - `cascade.go`: add `InvalidatedEntryID string` to `tier2Outcome`. In `tryTier2`, right after
      `c := scoped[0]` and **before** `out.Found, out.Candidate = true, c`: if `h.Deps != nil &&
      h.Deps.Invalidated(c.Entry.EntryID)`, set `out.InvalidatedEntryID = c.Entry.EntryID` and `return out`.
    - `handler.go`, after `t2 := h.tryTier2(…)`: `if rec.InvalidatedEntryID == "" { rec.InvalidatedEntryID =
      t2.InvalidatedEntryID }`.
  - Run: `cd gateway && go build ./... && go test -count=1 ./internal/httpapi/`
  - Pass: builds; every existing httpapi test passes (they leave `Deps` nil).
  - Result: handler.go gained dependencyMap, Handler.Deps, the Tier-1 check, Register in the write-back; cascade.go gained the Tier-2 check; builds; existing httpapi tests pass.

- [x] 1.5 Wire it in `main`.
  - Files: `gateway/cmd/gateway/main.go`
  - Do: after `store := cache.NewStore(…)` and its index check, `depMap := deps.New(rdb, store, 1024)`. After the
    handler is built, `handler.Deps = depMap`. After `srv.ListenAndServe()` returns and before
    `finishRun(evalLog)`: `depMap.Close` with a 10 s context (log a non-nil error), then log `Dropped()`,
    `RegisterErrors()` and `PurgeErrors()` when any is non-zero, saying the dependency map is incomplete.
    Comment: `ListenAndServe` returns as soon as `Shutdown` starts, so a write-back still in flight can
    register after `Close`; it is counted in `Dropped()`, not lost (the existing F-F window, not widened).
  - Run: `cd gateway && go build ./... && go vet ./cmd/gateway/ && go test -count=1 ./cmd/gateway/`
  - Pass: builds; vet clean; existing cmd/gateway tests pass.
  - Result: main.go builds depMap, sets handler.Deps, closes it before finishRun and logs the three counters; builds, vet clean, cmd/gateway tests pass.

- [x] 1.6 Contract to v0.17.
  - Files: `docs/contracts/interfaces.md`
  - Do:
    - Line 3: `Draft v0.16` → `Draft v0.17`; `Revised:` → `2026-10-28`.
    - §E: under the `dep:{chunk_id}` block, add the `entry:{entry_id}` HASH (`t1_key`, `source_chunk_ids`) and
      why it exists (a Tier-1-only entry; item 4.3's promoted keys). Replace the "Fast-path index" paragraph's
      vague part with what is built: one writer goroutine, the snapshot of invalidated `entry_id`s swapped
      before any delete, the hit-path check on both tiers. Add the purge steps (SMEMBERS, swap, purge each
      entry with the Tier-1 compare-and-delete, `DEL entry:E`, `DEL dep:{chunk_id}`) and the registration step.
      Under "Dataset epoch", add one line: ADR-008 overrides the `dataset:epoch` key shown here; item 4.2
      builds the epoch.
    - §H: an `invalidated_entry_id` row after `candidate_entry_id`: extension, v0.17, present iff the request
      met an invalidated entry and did not serve it; on Tier 1 the request goes on to Tier 2; on Tier 2 the
      candidate is dropped before it is judged, so `refusal_cause` is null and I3 still holds; names the first
      such entry; never present under `mutation: off`.
    - Versioning: `Current version` → v0.17 (2026-10-28) and a new top row: C2's dependency map is built (item
      4.1); §E gains `entry:*`, the register and purge steps and the hit-path check; §H gains
      `invalidated_entry_id`; no wire shape, §A, §B, §D or `.proto` change; under `mutation: off` nothing
      changes; under `mutation: on` a hit on an invalidated entry becomes a miss.
  - Run: `grep -n "v0.17\|entry:{entry_id}\|invalidated_entry_id" docs/contracts/interfaces.md`
  - Pass: header, `Current version`, version row, the `entry:` record and the §H row all appear.
  - Result: interfaces.md now v0.17 (header, current version, version row, §E entry:* + register/purge/hit-path + ADR-008 note, §H invalidated_entry_id row); all five greps appear.

- [x] 1.7 Architecture and the Redis notes.
  - Files: `docs/architecture.md`, `docs/Redis-Data Structure.md`
  - Do: `architecture.md`: the `deps/` row of the boundary table (drop "*(not built)*"; owns `dep:*` and
    `entry:*`; reaches the tiers through `Purger`); the **Invalidation** row of the path table (drop "not built",
    describe the built path); the "Not built" inventory row (remove `deps/`; add `deps` to "Built and tested");
    the sentence "C2 is not built." after "Where the contributions live" (C2's map is built; the epoch guard is
    item 4.2); the `deps/` tree line (it stays as is if still accurate). `Redis-Data Structure.md` §8: retitle
    from "not built yet" to built in item 4.1, describe `entry:*` as written, and match the purge steps;
    keep the ADR-008 epoch paragraph and say the epoch guard is item 4.2.
  - Run: `grep -n "not built\|Not built" docs/architecture.md "docs/Redis-Data Structure.md"`
  - Pass: no line says `deps/` or C2's map is not built; the epoch guard (4.2) may still say so.
  - Result: architecture.md (deps row, Invalidation row, inventory, C2 sentence, import graph/tree) and Redis-Data Structure.md (§1 box, §8 rewritten, §9 gap 5) updated; grep left only epoch-guard (4.2) and replay/judge lines.

## Phase 2 — Unit tests

- [x] 2.1 `cache`: the purge (DC 4).
  - Files: `gateway/internal/cache/purge_test.go` (new), using `testStore` and `seed` from `capacity_test.go`.
  - Do: `TestPurgeEntryDeletesBothTiers` (t2, t1 and the lru member go; another entry's keys stay);
    `TestPurgeEntryLeavesReusedTier1Key` (seed `E` with `t1:k`, then overwrite `t1:k`'s `entry_id` with `E2`;
    `PurgeEntry(E, "t1:k")` leaves `t1:k`); `TestPurgeEntryReadsT1KeyFromTier2` (`t1Key` empty, the key comes from
    `t2:E`).
  - Run: `cd gateway && go test -count=1 -v -run 'TestPurgeEntry' ./internal/cache/`
  - Pass: the three tests print `--- PASS`; none `--- SKIP`.
  - Result: added cache/purge_test.go (3 tests); TestPurgeEntryDeletesBothTiers, ...LeavesReusedTier1Key, ...ReadsT1KeyFromTier2 all PASS, 0 SKIP (EVAL works on this Redis).

- [x] 2.2 `deps`: registration, purge, tombstones, counters (DC 1, 2, 3, 5a, 7).
  - Files: `gateway/internal/deps/deps_test.go` (new, `package deps`).
  - Do: a helper that opens Redis DB 14, `t.Skipf` if `PING` fails, `FlushDB` before and after, and builds
    `cache.NewStore(rdb, 768)` as the `Purger`. A helper `seedEntry(E, t1Key, sources, withT2 bool)` that writes
    `t1:` (`entry_id` = E), optionally `t2:` (`t1_key`), and an `lru:entries` member, the way
    `capacity_test.go`'s `seed` does. After `Register` calls, use an `Invalidate` of an unused chunk as a barrier
    (the queue is FIFO). Tests:
    - `TestRegisterWritesDepAndEntry` and `TestRegisterWithoutTier2Entry` (DC 1).
    - `TestInvalidatePurgesExactlyDependents` (DC 2): the `E1 {A,B}`, `E2 {B,C}`, `E3 {C}` case of §1, also
      checking the returned IDs are `{E1, E2}`.
    - `TestInvalidatePurgesTier1OnlyEntry` (DC 3).
    - `TestInvalidatedVisibleBeforePurge` (DC 5a): a `Purger` that blocks until released; after `Invalidate`
      returns, `Invalidated(E1)` is true and `EXISTS t2:E1` is 1; `Invalidated(E3)` is false; release, then
      `t2:E1` is gone.
    - `TestRegisterWaitsWhenQueueFull` (DC 7): `queue` 1, the writer held inside a blocked purge, the queue
      filled, one more `Register` in a goroutine has not returned; release; it returns and its `dep:` record
      exists; `Dropped()` is 0.
    - `TestRegisterAfterCloseIsCounted`, `TestRegisterErrorIsCounted` (a client at `localhost:1`),
      `TestPurgeErrorIsCounted` (a `Purger` that returns an error; the tombstone still holds),
      `TestInvalidateAfterCloseFails` (DC 7).
  - Run: `cd gateway && go test -count=1 -v ./internal/deps/`
  - Pass: every test above prints `--- PASS`; no `--- SKIP`.
  - Result: added deps/deps_test.go (10 tests, Redis DB 14); all 10 PASS, 0 SKIP.

- [x] 2.3 `deps`: one writer under `-race` (DC 6).
  - Files: `gateway/internal/deps/race_test.go` (new).
  - Do: `TestConcurrentRegisterInvalidateRead`: 8 goroutines register 50 entries each over 10 chunks, 2
    goroutines invalidate chunks, 4 goroutines read `Invalidated` in a loop; then a barrier. Check: for every
    chunk whose invalidation ran after all its registrations (track with the returned IDs), every returned ID
    has no `t2:` key and `Invalidated` is true.
  - Run: `cd gateway && go test -race -count=1 -v -run TestConcurrentRegisterInvalidateRead ./internal/deps/`
  - Pass: `--- PASS`, and no `WARNING: DATA RACE` in the output.
  - Result: added deps/race_test.go (400 entries, 8 registrars, 2 invalidators, 4 readers); PASS under -race, no DATA RACE (also 5 repeats).

- [x] 2.4 `cmd/gateway`: the wiring (DC 12).
  - Files: `gateway/cmd/gateway/deps_wiring_test.go` (new).
  - Do: `TestMainWiresDeps`: read `main.go`, drop lines whose trimmed text starts with `//`; require
    `deps.New(` and `handler.Deps = depMap` (the latter after `httpapi.NewHandler(`), and the first index of
    `srv.Shutdown(` < `depMap.Close(` < `finishRun(evalLog)`. Fail if any needle is missing.
  - Run: `cd gateway && go test -count=1 -v -run TestMainWiresDeps ./cmd/gateway/`
  - Pass: `--- PASS`.
  - Result: added cmd/gateway/deps_wiring_test.go (TestMainWiresDeps, comment lines dropped, also checks `depMap := deps.New(`); PASS.

## Phase 3 — Integration tests

- [x] 3.1 `httpapi`: the hit path and the registration (DC 5b).
  - Files: `gateway/internal/httpapi/invalidation_test.go` (new).
  - Do: a `fakeDeps` (mutex; a set of invalidated IDs; a slice of registrations) satisfying `dependencyMap`.
    Each test: `hs := newHarness(t, 1, 0)`, `hs.h.Deps = fake`, then `hs.records(t)` and `c.record(t)`.
    - `TestInvalidatedTier1HitIsNotServed`: `hs.store.seedTier1(q, kettle.id, cache.Entry{Answer:
      kettle.otherAnswer, …, EntryID: E})`, `E` invalidated, `hs.embedFresh(q)`; the response is not
      `kettle.otherAnswer`; record `cache` is not `TIER1_HIT`, `invalidated_entry_id` is `E`.
    - `TestInvalidatedTier2CandidateIsDropped`: `e := hs.seedHit(kettle, q1, 1)`, `e.EntryID` invalidated,
      `hs.askNear(t, q2, 1, hitCos, kettle)`; record `cache` `MISS`, `refusal_cause` null, `reuse_rule` absent,
      `invalidated_entry_id` = `e.EntryID`.
    - `TestValidEntryIsStillServed`: the same seeding with a different ID invalidated; `TIER2_HIT`, and
      `invalidated_entry_id` absent.
    - `TestMissRegistersItsEntry`: a plain MISS registers once, with `EntryID` = the record's `entry_id`,
      `Sources` = `kettle.answerSources()`, `T1Key` = the record's `t1_key`. Then a second MISS with
      `hs.embedder.failEverything()` (Tier 1 only) also registers once.
  - Run: `cd gateway && go test -count=1 -v -run 'TestInvalidated|TestValidEntryIsStillServed|TestMissRegistersItsEntry' ./internal/httpapi/`
  - Pass: the four tests print `--- PASS`.
  - Result: added httpapi/invalidation_test.go (fakeDeps + 4 tests, no Redis); TestInvalidatedTier1HitIsNotServed, ...Tier2CandidateIsDropped, TestValidEntryIsStillServed, TestMissRegistersItsEntry all PASS.

## Phase 4 — Run and verify

- [x] 4.1 `redis-cli PING` → `PONG`, then `make verify`
  - Pass: no FAIL; any SKIPPED target listed by name.
  - Result: `redis-cli PING` PONG; `make verify` exit 0 (go vet, build, go test ./..., ruff, 23 rag tests, 731 passed); no SKIPPED, no SKIP in the output.
- [x] 4.2 DC 1, 2, 3, 5a, 7 — `cd gateway && go test -count=1 -v ./internal/deps/ 2>&1 | grep -E "^(--- |ok|FAIL)"`
  - Pass: every test from step 2.2 `--- PASS`; no `--- SKIP`; `ok`.
  - Result: 11 deps tests PASS (the 10 from 2.2 plus TestConcurrentRegisterInvalidateRead), 0 SKIP; `ok github.com/hung/thesis/gateway/internal/deps`.
- [x] 4.3 DC 4 — `cd gateway && go test -count=1 -v -run TestPurgeEntry ./internal/cache/`
  - Pass: three `--- PASS`; no `--- SKIP`.
  - Result: TestPurgeEntryDeletesBothTiers, ...LeavesReusedTier1Key, ...ReadsT1KeyFromTier2 all PASS; 0 SKIP.
- [x] 4.4 DC 5b — the step 3.1 command.
  - Pass: four `--- PASS`.
  - Result: TestInvalidatedTier1HitIsNotServed, TestInvalidatedTier2CandidateIsDropped, TestValidEntryIsStillServed, TestMissRegistersItsEntry all PASS.
- [x] 4.5 DC 6 — `cd gateway && go test -race -count=1 ./internal/deps/` and
  `grep -rn '"dep:\|"entry:' gateway --include='*.go' | grep -v '_test.go'`
  - Pass: `ok` with no data race; the grep lists files under `gateway/internal/deps/` only.
  - Result: `go test -race -count=1 ./internal/deps/` ok, no data race; grep lists only gateway/internal/deps/deps.go (lines 19-20).
- [x] 4.6 DC 8 — `cd gateway && go test -count=1 -v -run TestEvictionLeavesDependencyRecordsAlone ./internal/cache/`
  - Pass: `--- PASS`; no `--- SKIP`.
  - Result: TestEvictionLeavesDependencyRecordsAlone PASS; 0 SKIP.
- [x] 4.7 DC 9 — `grep -n "v0.17\|entry:{entry_id}\|invalidated_entry_id" docs/contracts/interfaces.md`;
  `grep -n "deps/" docs/architecture.md`; `grep -n "^## 8" "docs/Redis-Data Structure.md"`
  - Pass: the v0.17 header, version line and row, `entry:` and §H row appear; the `deps/` row no longer says
    not built; §8's title no longer says not built.
  - Result: interfaces.md v0.17 header (line 3), `entry:{entry_id}` (444-453), purge steps (482), §H row (689), current version (726), version row (730); architecture.md `deps/` row (181) has no 'not built'; Redis-Data Structure.md §8 retitled 'invalidation (built in item 4.1)'.
- [x] 4.8 DC 10 — `make verify` passed in 4.1, with Redis up. Record any SKIPPED names.
  - Result: `make verify` passed in 4.1 with Redis up (PONG); SKIPPED targets: none.
- [x] 4.9 DC 11 — `git status --porcelain -- '*_test.go'`
  - Pass: every line starts with `??` or `A `; none with `M` or `D`.
  - Result: `git status --porcelain -- '*_test.go'` shows 5 lines, all `??` (deps_wiring_test.go, purge_test.go, deps_test.go, race_test.go, invalidation_test.go); no M or D.
- [x] 4.10 DC 12 — `cd gateway && go test -count=1 -v -run TestMainWiresDeps ./cmd/gateway/`
  - Pass: `--- PASS`.
  - Result: TestMainWiresDeps PASS.
