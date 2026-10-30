# `gateway/internal/deps/` — the dependency map, the purge and the epoch reader

**Describes:** commit `29b24a6` (30 Oct 2026); last changed in `68d732e` (item 4.4). **Files:** `deps.go`
(413 lines), `epoch.go` (71 lines), `doc.go`, and six test files. Governing contract: `interfaces.md` §E.
**The system view** (why blind purge, the epoch race, results) is in
[`Invalidation.md`](../../Cache_Invalidation/Invalidation.md). The Redis records are in
`Redis-Data Structure.md` §8. This doc explains the code.

## 1. Purpose

It records which source chunks every cached answer used, and when a chunk is edited it removes every answer
built on it, from both tiers. It also reads the dataset epoch for the write-back guard. It serves **C2**.

## 2. Boundaries

- It imports **no** package from this repository. It reaches the two cache tiers only through the small
  `Purger` interface, which `*cache.Store` satisfies; `cache/` keeps owning the key layout.
- It is the **only** writer of `dep:*` and `entry:*`, and it writes them from **one** goroutine, never from a
  request goroutine. The prefixes appear in `deps.go` only.
- It must never hold a lock across a Redis call (`docs/architecture.md` §2).

## 3. `deps.go`

### Types

- **`Registration`**: one new answer's `EntryID`, its `Sources` (chunk IDs), its `T1Key`, and the
  `DatasetEpoch` its chunks were read under.
- **`Event`**: one source edit (`ChunkID`, `DocID`, `ChangeType`, `NewText`, `DatasetVersion`, `TS`). **Only
  `ChunkID` drives the purge.** The rest is recorded; `ChangeType` is never a gate.
- **`Purger`**: `PurgeEntry(ctx, entryID, t1Key)`, which removes one entry from both tiers.
- **`PurgeResult`**: what a finished purge did: `Purged` and `Failed` (sorted, never nil) and `Errors`.
- **`op`**: one message to the writer, a registration **or** an event, with buffered reply channels so the
  writer never blocks on a caller that left.
- **`ErrClosed`**: returned after `Close`, so `httpapi` can answer 503 ("shutting down") instead of 500.

### `Map`

`Map` holds the Redis client, the `Purger`, the channel to the writer, and:
- **`snap`**, an `atomic.Pointer` to the set of invalidated entry IDs (the tombstones). The writer builds a new
  set and stores it; it never changes a set after storing it.
- **`epoch`**, an `atomic.Pointer` to the epoch source, nil until `SetEpochSource` (the late check is off).
- four counters: `dropped`, `registerErrors`, `purgeErrors`, `lateDiscards`.

The in-process set is **not** a copy of `dep:*`. Redis stays the authority for "who depends on this chunk",
so entries written by an earlier gateway process are purged too.

### Public methods

- **`New(rdb, purger, queue)`** builds the map with an empty snapshot and starts the writer. `main.go` uses a
  queue of 1,024.
- **`Register(r)`** queues a registration and returns once it is **queued**, not written. **It takes no
  context**: the write-back runs inside the coalesced generation, and a registration that gave up on a
  cancelled client would leave an answer no purge can reach. It waits while the queue is full. After `Close` it
  is counted in `Dropped()` and logged.
- **`Invalidate(ev)`** queues the event and returns the dependent IDs **once their tombstones are visible**.
  The Redis purge runs after that, off the caller's path. After `Close` it returns `ErrClosed`.
- **`InvalidateWait(ctx, ev)`** does the same and also waits for the whole purge, returning a `PurgeResult`. A
  cancelled `ctx` stops the **wait**, not the purge, which is already queued and runs to the end.
- **`SetEpochSource(src)`** turns the late check on (nil turns it off). Safe while the writer runs.
- **`Invalidated(entryID)`**: one atomic load and one map lookup. No lock, no Redis. This is the hit path's
  check.
- **`Close(ctx)`** stops intake, lets the writer drain the queue, and waits. A second call returns nil.
- **Counters:** `Dropped()`, `RegisterErrors()`, `PurgeErrors()`, `LateDiscards()`.

### The writer

**`run()`** handles messages in arrival order, so a registration can never race a purge on the same key.

**`applyRegistration(r)`**:
1. **The late rule:** with an epoch source set, read the epoch. If it differs from `r.DatasetEpoch`, or the
   read fails, call `discardLate` and stop.
2. Encode the sources as JSON. An encoding error is counted in `RegisterErrors`.
3. In **one transaction**: `SADD dep:{c} entryID` for each source, and `HSET entry:{entryID}` with `t1_key` and
   `source_chunk_ids`. An answer with no sources writes `entry:` only; no edit can reach it, which is right. A
   Redis error is counted in `RegisterErrors`.

**`discardLate(r, …)`** tombstones the entry, purges it from both tiers, writes **no** `dep:` or `entry:` record,
and counts it in `LateDiscards`. These are discarded write-backs, not a completeness failure.

**`tombstone(ids…)`** copies the current set, adds the IDs, and swaps the pointer. Only the writer calls it, so
no update can be lost. A reader holds either the old set or the new one. The set only grows.

**`applyInvalidation(ev, ack, done)`**, in this order:
1. `SMEMBERS dep:{chunk}`. On error, reply with the error and stop: nothing was purged.
2. **Tombstone** all of them, **before** deleting anything.
3. **Reply** to `Invalidate` with the IDs. From here every hit on them is refused.
4. `purgeOne` each entry, sorting them into `Purged` and `Failed`.
5. `SREM dep:{chunk}` of the **purged** entries only. A failed entry stays listed, so a retry, or a restarted
   gateway, finds it. Redis deletes the set when it is empty.
6. Send the `PurgeResult` (for `InvalidateWait` only).

**`purgeOne(id)`** reads `t1_key` from `entry:{id}` (a missing record is fine: the `Purger` then reads it from
`t2:{id}`), calls `PurgeEntry`, and only then deletes `entry:{id}`. If the tiers were not purged, `entry:` is
kept, because it still holds the Tier-1 key. Each failed step is counted in `PurgeErrors` and logged.

## 4. `epoch.go`

- **`EpochSource`**: `Current() (uint64, error)`. The write-back guard in `httpapi` and the late check here
  both take it, so a test can supply any value or error.
- **`EpochFile`**: the real source, one decimal integer ≥ 1 in a file outside Redis (ADR-008).
- **`OpenEpochFile(path)`** refuses a **relative** path (the gateway and `rag.server` run from different
  directories), a missing file, a non-integer, and a value below 1. It returns the file and its value.
- **`Current()`** re-reads the file **on every call**. A cached value would miss an advance and let a stale
  write-back pass. A trailing newline or spaces are allowed; anything else fails, so the guard fails closed.
- **`Path()`** is for the start-up log line.

## 5. Callers and callees

- **`cmd/gateway/main.go`**: `deps.New(rdb, store, 1024)`, `SetEpochSource(epochFile)`, and at shutdown
  `Close`, then logs `Dropped`, `RegisterErrors`, `PurgeErrors` and `LateDiscards` when non-zero.
- **`httpapi`**: `Register` after each write-back (`handler.go`); `Invalidated` on a Tier-1 hit (`handler.go`)
  and on a Tier-2 candidate (`cascade.go`); `InvalidateWait` in `POST /invalidate` (`invalidate.go`).
- **Calls** Redis, and `cache.Store.PurgeEntry` through `Purger`.

## 6. Tests that pin it

The Redis tests run on the throwaway server (`make test-go`, port 6390; see [`testredis.md`](testredis.md)).

| File | Tests | Guarantees |
| :--- | :--- | :--- |
| `deps_test.go` | `TestRegisterWritesDepAndEntry`, `TestRegisterWithoutTier2Entry` | both records are written, also for a Tier-1-only answer |
| | `TestInvalidatePurgesExactlyDependents`, `TestInvalidatePurgesTier1OnlyEntry` | the purge removes every dependent and nothing else |
| | `TestInvalidatedVisibleBeforePurge` | tombstones are visible before anything is deleted |
| | `TestRegisterWaitsWhenQueueFull`, `TestRegisterAfterCloseIsCounted`, `TestRegisterErrorIsCounted`, `TestPurgeErrorIsCounted`, `TestInvalidateAfterCloseFails` | nothing is lost without a count |
| `invalidate_wait_test.go` | six `TestInvalidateWait*` tests | it returns after the purge; failed entries stay in `dep:` and a retry purges them; it honours `ctx`; it refuses after `Close` |
| `late_test.go` | `TestLateRegistrationIsPurged`, `TestLateRegistrationReadErrorPurges`, `TestLateRegistrationCurrentEpochIsKept` | the late rule, failing closed |
| `epoch_test.go` | `TestEpochFileRereadsEveryCall`, `TestEpochFileOpenRefuses`, `TestEpochFileOpenAcceptsTrailingNewline` | the file is re-read every call, and bad files are refused |
| `t1keys_test.go` | `TestInvalidateDropsPromotedKey` | a promoted Tier-1 key is purged too |
| `race_test.go` | `TestConcurrentRegisterInvalidateRead` | registrations, purges and `Invalidated` reads are race-free |

## 7. Silent failures to watch

- **A registration that never happens** leaves an answer no purge can reach. Watch `Dropped()` and
  `RegisterErrors()` at shutdown. The update-set scorer reads sources from the evaluation log, never from
  `dep:*`, so it would still catch the miss.
- **A failed purge plus a restart**: the tombstone is lost with the process, and the leftover Redis copy can
  be served until a retry purges it.
- **The tombstone set only grows** and is copied on every purge. Cheap at this scale; not bounded.

## 8. Commit

`29b24a6`; last changed in `68d732e`.
