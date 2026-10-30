# `gateway/internal/coalesce/` — one generation for identical questions in flight

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `coalesce.go`, `coalesce_test.go`.
**The system view** is in [`Admission Control.md`](../../Admission%20Control/Admission%20Control.md) §6.

## 1. Purpose

When N identical questions miss the cache at the same time, only one of them generates; the others wait and
share its result. This saves the scarcest resource, and it keeps the no-cache baseline honest: its
generation count must depend on how often the workload repeats, not on the load generator's concurrency.
It serves **S1/S2**.

## 2. Boundaries

- It imports nothing from this repository.
- It **wraps** the admission call; it never holds a permit of its own (`docs/architecture.md` §2).
- It is hand-written rather than `golang.org/x/sync/singleflight`: a new dependency needs sign-off, and the
  code is about forty lines.

## 3. `coalesce.go`

**`Group[T]`** runs one function per key at a time. Its zero value is ready to use. It holds a mutex and a map
from key to the call in flight.

**`call[T]`** is one execution: a `done` channel closed when it finishes, its result (`val`, `err`), and
`waiting`, the number of callers that joined it. `waiting` is the raw signal for "generations avoided by
coalescing", which cache hits cannot give.

**`Do(key, fn)`** returns `(val, err, shared)`:
1. Under the lock, if a call for `key` is in flight, increment its `waiting`, unlock, wait on `done`, and
   return its result with `shared = true`. This caller is a **follower**.
2. Otherwise register a new call, unlock, and run `fn`. This caller is the **leader**; it returns
   `shared = false`.
3. A deferred function **releases** the call when `fn` returns, and also when it panics.

**Release order: delete the key, then wake the waiters** (`release`). The other order would let a waiter wake,
call `Do` with the same key, find the finished call still in the map, and get its old result for ever.

**A panic in `fn`** is converted to an error for the followers (`coalesce: shared call panicked`), then
re-raised for the leader. Without this, every follower would get a zero value with a nil error and serve it
as a successful answer.

**Test seams:** `inflight()` (keys in flight), `Waiters(key)` and `waiters(key)` (callers blocked on a key).
They take the lock, so they never run on a request path.

## 4. Callers and callees

- **Called by** `httpapi.(*Handler).Ask` as `h.Generations.Do(t1Key, …)`. The key is the Tier-1 key, which
  includes `product_id` (ADR-018), so the same words about two products never share an answer.
- **The closure it runs** takes the admission permit, calls `Answer`, and writes back. So the leader holds
  the permit; followers hold none.

## 5. Tests that pin it

| Test | Guarantees |
| :--- | :--- |
| `TestConcurrentDuplicatesRunTheFunctionOnce` | N concurrent callers with one key run `fn` once, and all get its result |
| `TestDifferentKeysDoNotShare` | different keys run separately |
| `TestKeyIsReleasedSoLaterCallersReRun` | a caller after the call finished runs `fn` again |
| `TestErrorReachesEveryWaiter` | the leader's error reaches every follower |
| `TestPanicBecomesAnErrorForWaiters` | a panic gives followers an error, never a zero-value success |

In `httpapi`: `TestCoalescingWrapsAdmission` (one permit for N identical misses) and
`TestCoalescingNeverCrossesProducts`.

## 6. Silent failures to watch

- **`fn` runs under the leader's context.** If the leader's client leaves, the shared call is cancelled and a
  follower with a live client fails too (finding F-D, open). Followers do not elect a new leader.
- **A key without `product_id`** would share one product's answer with another. The key is `t1Key`; keep it so.
- **`shared` is logged only on a served MISS** (`coalesced`, finding F-O), so a follower of a failed leader is
  hard to tell from a leader in the log.

## 7. Commit

`29b24a6`. The package last changed in `8d637f7` (item 1.2).
