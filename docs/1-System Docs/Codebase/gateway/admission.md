# `gateway/internal/admission/` — the generation permit pool

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `pool.go` (120 lines), `pool_test.go`.
**The system view** (why one permit, what it protects, how it is measured) is in
[`Admission Control.md`](../../Admission%20Control/Admission%20Control.md). This doc explains the code.

## 1. Purpose

It bounds how many generations run at once, lets a bounded number of callers wait, and refuses the rest. It
serves **S2** (stability under overload). It bounds **queueing delay and goodput, not memory** (ADR-003).

## 2. Boundaries

- It imports nothing from this repository.
- It must be the **only** place a generation permit is taken, and no miss path may skip it. `httpapi` has
  exactly one call site (`docs/architecture.md` §2): otherwise the queue moves into Ollama, where it is neither
  counted nor shed (ADR-003).

## 3. `pool.go`

**`ErrShed`** is the error for "the permit and the queue are both taken". It is kept apart from a cancelled
context on purpose: a shed is a decision the gateway made and must be counted; a cancellation is the client
leaving and must not be.

**`Pool`** holds three things:
- `permits`, a buffered channel whose capacity is the number of permits. Sending into it takes a permit;
  receiving from it gives one back.
- `queue`, a buffered channel whose capacity is the queue budget. Sending into it takes a place in the queue.
- `depth`, an atomic counter of callers waiting now.

Two bounds, not one: with permits alone, an overloaded gateway would block callers forever, and overload
would show as exploding latency instead of a counted shed.

**`New(permits, queueBudget)`** builds the pool. A permit count of 0 or less returns an **empty pool**, which
admits everything (admission control off). A negative queue budget becomes 0.

**`Enabled()`** reports whether the pool bounds anything (`permits != nil`).

**`Permit`** is one held slot. It carries `Waited` and `QueueDepth`, which feed the log fields
`t_permit_wait_ms` and `permit_queue_depth`, and a `once` flag.

**`Release()`** gives the permit back **once**. It uses an atomic compare-and-swap on `once`, so a second call
does nothing. A double release would silently add a permit and let two generations run at once. Releasing a
nil permit, or one from a disabled pool, is also a no-op.

**`Acquire(ctx)`**, step by step:
1. **Disabled pool:** return an empty `Permit` at once.
2. **Fast path:** try to send into `permits` without waiting. If it works, return a permit with
   `Waited = 0` and `QueueDepth = 0`. The queue is never touched.
3. **Join the queue:** try to send into `queue` without waiting. If the queue is full, return `ErrShed`.
4. **Count the waiter:** `depth.Add(1)`; that value, which includes this caller, becomes `QueueDepth`. A
   deferred function decrements `depth` and frees the queue place when the caller leaves the queue, either
   way.
5. **Wait** for whichever comes first: a permit (return it, with `Waited` = time since the start), or
   `ctx.Done()` (return `ctx.Err()`, never `ErrShed`).

**`InFlight()`** and **`Queued()`** report the held permits and the waiting callers. They are for the start-up
banner and the log, never for a decision. `httpapi` writes `Queued()` into the record of a shed request.

## 4. Callers and callees

- **Built by** `cmd/gateway/main.go`: `admission.New(permits, queueBudget)`, with `OLLAMA_NUM_PARALLEL`
  (default 1) and `GEN_QUEUE_BUDGET` (default 2 × permits).
- **Called by** `httpapi.(*Handler).Ask`, inside the coalescing closure: `Acquire`, then
  `defer permit.Release()`, held through `Answer` and the write-back.
- **Calls** nothing outside the standard library.

## 5. Tests that pin it (`pool_test.go`)

| Test | Guarantees |
| :--- | :--- |
| `TestNeverAdmitsMoreThanPermits` | concurrent callers never hold more permits than the pool has |
| `TestShedsWhenPermitsAndQueueAreBothFull` | `ErrShed` comes exactly when both are full |
| `TestCancelledWaiterIsNotAShed` | a caller whose context ends while queued gets `ctx.Err()`, not `ErrShed` |
| `TestDoubleReleaseDoesNotRaiseCapacity` | a second `Release` adds no permit |
| `TestDisabledPoolAdmitsEverything` | `New(0, …)` admits every caller |
| `TestWaitedIsRecordedOnlyWhenTheCallerActuallyQueued` | `Waited` is zero on the fast path, set after queueing |

## 6. Silent failures to watch

- **More permits than served slots.** `OLLAMA_NUM_PARALLEL` above 1 only prints a warning. The extra requests
  queue inside Ollama, and every shed rate then describes Ollama's queue (ADR-003).
- **A second call site.** Any new miss path that generates without `Acquire` bypasses the bound with no error.
- **Admission off by accident.** `OLLAMA_NUM_PARALLEL=0` disables the pool; the start-up log says so, nothing
  else does.
- **A zero wait is logged as null** (finding F-N): `httpapi` converts `Waited == 0` to null, so the fast path
  and "no permit asked" look the same in the log.

## 7. Commit

`29b24a6`. The package last changed in `5bc45bf` (ADR-003, 4 Oct 2026), which reframed it around one permit.
