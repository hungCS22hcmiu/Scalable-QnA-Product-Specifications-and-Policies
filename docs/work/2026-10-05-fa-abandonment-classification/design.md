# Design — fa-abandonment-classification

**Revision 3**, after `review.md`. It reads with `spec.md` rev 3 and `approvals.md`.
**Decided by the author:** D1, the precedence (`approvals.md`).

**Changed from rev 2** (`review.md`; the fix itself is unchanged and was approved as written):
- **S2:** T6 is rebuilt: different raw text for the follower, the gate opened after the leader
  returns, no leader assertion. As written it failed on every version and constrained F-D.
- **S1:** the comment at the case no longer says the client left is "not an error the gateway
  caused"; the experiment record says `ABANDONED` under a load generator is a censored latency
  observation (§7, F8).
- **S3:** the F-L handoff states that `ABANDONED` is only an upper bound on orphan exposure (§7, F9).
- **N1–N5:** all six mutations pass the existing suite (§6); T7's reading recipe (§5); T2's gRPC
  comment; T5 relabelled a D1 pin; the write-back note (§7, F10).

**Changed from rev 1 (kept):**
- The coalescing matrix is now the analyst's measured one (§3), with a third column.
- The tests are rebuilt on a **cache wrapper** that cancels the request's context at a chosen point
  (§5). It replaces rev 1's pre-cancelled context (a fake-only path) and rev 1's follower stand-in
  for "a completed generation".
- Two wrong fixes the existing suite cannot catch are added: **M-closure** and **M-order** (§6).
- F-L, F-H widening, the limitations and the S6 assumption comment are added.

## 1. Shape

```
 Ask ─► Tier 1 ─► embed ∥ retrieve ─► Tier 2 ─► miss path ─► Generations.Do(key, closure) ─► (gen, err, shared)
                                                              closure: Acquire(leader ctx) ─► Answer(leader ctx) ─► write-back

 switch after Do                         TODAY                          AFTER  (D1)
   errors.Is(err, ErrShed)               503 shed                       unchanged, still first
   errors.Is(err, Canceled | Deadline)   ABANDONED, write nothing       unchanged
   err != nil ∧ ctx.Err() != nil         (falls to the next case)       ABANDONED, write nothing      ← new
   err != nil                            GENERATION_FAILED + 502        unchanged, now reached only with a live client
   err == nil                            MISS                           unchanged
```

The whole change is one extra condition in one `switch`, in `httpapi/handler.go`, plus a comment:

```go
case errors.Is(err, context.Canceled), errors.Is(err, context.DeadlineExceeded),
	err != nil && ctx.Err() != nil:
	// The client left. Under a load generator that is a timeout, and it counts against S2: it is
	// not client behaviour to exclude. Nothing is written, because a body to a dead connection would
	// only muddy the counts. A shed is above this case and an upstream error with a live client is
	// below it.
	//
	// ctx is THIS request's own context (r.Context(), set at the top of Ask). It is read here, after
	// Do returns, and never inside the Do closure: the closure runs under the leader's context, and
	// reading that would hand a coalesced follower the leader's cancellation (F-D).
	//
	// This relies on the request context being cancelled only by the client. main.go sets no server
	// timeout and no BaseContext. A future server-side deadline would be filed here as a client
	// leaving; context.Cause is the tool if that ever stops holding.
```

It must sit **below** `ErrShed` and **above** `case err != nil`. Nothing else changes: not
`ragclient`, `admission`, `coalesce`, the harness, or any existing test. No import is added.

## 2. Why classify by the request's own context

The error that comes back from `Answer` cannot tell a client leaving from an upstream failure. The
request's own context can. Four ways to make the label right, and why the last:

| Option | Where | What it gets wrong (all measured by `impact.md`) |
| :--- | :--- | :--- |
| **A. Map the status code** | handler or `ragclient`: `Canceled`/`DeadlineExceeded` → context error | `rag.server` can raise both codes itself with the client still connected (a restart, its own timeout). They would be filed as the client leaving, so a real gateway-side failure vanishes from `GENERATION_FAILED`. It also imports `grpc/status` into `httpapi` |
| **B. Return `ctx.Err()` from `ragclient`** | `ragclient.Answer` | The closure runs under the **leader's** context, so every coalesced follower receives the leader's `context.Canceled`: a live follower becomes `ABANDONED`, nothing written, an empty `200`. F-D widened from one cell to two |
| **C. Normalise inside the closure** | the `Do` closure | Same as B: the leader's context reaches the followers |
| **D. Ask the caller's own context, in the switch** (chosen) | the handler's switch | Each request is judged by its own client. A live client's `ctx.Err()` is nil, so the switch reduces to today's, byte for byte |

## 3. The coalescing matrix: what a live follower receives does not move

Leader and follower share one generation. The closure runs under the leader's context. The follower
receives the leader's error, but its own `ctx` is its own. Measured by `impact.md` §3 (cell 3 is
reasoned).

| # | Cell | Leader, today → after | Follower, **live client**, today → after | Follower, **client gone**, today → after |
| :---: | :--- | :--- | :--- | :--- |
| 1 | Leader cancelled while **queued** | `ABANDONED` → same | `ABANDONED`, nothing written: an **empty 200** on the wire (F-D) → **same** | `ABANDONED` → same |
| 2 | Leader cancelled **during `Answer`** | `GENERATION_FAILED` 502 (**F-A**) → **`ABANDONED`** | `GENERATION_FAILED` 502 → **same** | `GENERATION_FAILED` → **`ABANDONED`** |
| 3 | Leader's client left **before `Answer`** | `GENERATION_FAILED` → **`ABANDONED`** | `GENERATION_FAILED` 502 → same | → `ABANDONED` |
| 4 | Leader **succeeds**, a follower's client left | `MISS` → same | `MISS` → same | `MISS`, `coalesced`, 200 to a dead connection → **same** |
| 5 | Leader's upstream **genuinely fails**, leader live | `GENERATION_FAILED` 502 → same | `GENERATION_FAILED` 502 → same | `GENERATION_FAILED` → **`ABANDONED`** (D1) |

**The follower with a live client is identical in every cell.** The only followers that change are
those whose own client has gone (cells 2, 3, 5). That is the rule working, and `spec.md` says so.

## 4. Function contract

For a request whose generation returned `(gen, err, shared)`, the cases in order:

1. `errors.Is(err, admission.ErrShed)`: unchanged. A dead client meeting a full pool is still
   `SHED`: `Acquire` reads no context before the queue.
2. `errors.Is(err, context.Canceled)` or `errors.Is(err, context.DeadlineExceeded)`: unchanged. A
   queued `Acquire` returns a raw `context.Canceled`. Today, when the permit frees at the same
   moment, `select` may take the permit instead and call `Answer` on a dead context: a coin flip
   between `ABANDONED` and `GENERATION_FAILED` (1.2 `review.md` S3). After the fix both land
   `ABANDONED`, so the flake disappears.
3. **New:** `err != nil && ctx.Err() != nil`. This request's client has gone and the generation
   failed, for any reason (D1). Record `ABANDONED`, write nothing.
4. `err != nil`: unchanged, now reached only with a live client.
5. `err == nil`: unchanged. A generation that **completed** is a `MISS` whether or not the client has
   since left. The `err != nil` guard in case 3 is what keeps it that way.

**The snapshot.** `ctx.Err()` is read once, after `Do` returns. A client that leaves in the
microseconds between an error and that read is filed `ABANDONED`. That is accurate, and the window is
negligible.

**Left alone.** `Pool.Acquire`'s fast path takes a free permit without reading the context, so a
request already gone holds it for the microseconds `Answer` takes to fail. The label is right. The
`ABANDONED` log line (`handler.go:498`) says *"while generating"* for a leave that happened earlier;
stderr is not the measurement channel, and it is not reworded.

## 5. Tests

All new, in `gateway/internal/httpapi/abandon_test.go`, on the existing harness. **No existing test
changes** (spec acceptance 7).

**The seam.** A local type in the new file wraps `*fakeStore` (it still satisfies `cacheStore`) and
cancels one request's context at a chosen call, keyed on the **question text** so that no other
request is touched and `hs.h.Cache` can be assigned before any request starts (no race):

```go
type leavingStore struct {
	*fakeStore
	afterGet, afterPut string             // the question whose client leaves
	leave              context.CancelFunc // cancels that request's context
}
// Get: call fakeStore.Get, then if query == afterGet { leave() }, return its miss.
// Put: if query == afterPut { leave() } before delegating (the first write-back, after a success).
```

| # | Test | Asserts | On `HEAD` | Catches |
| :---: | :--- | :--- | :--- | :--- |
| T1 | **leaves during `Answer`** | `holdAnswers`; once the `Answer` call is recorded, cancel the client context. `cache: ABANDONED`, `shed: false`, nothing written, the permit released (`InFlight() == 0`). **Not** `t_generate_ms` (F-H) | **fails** | the fix dropped |
| T2 | **leaves after Tier 1** | `leavingStore{afterGet: q}`: embed and retrieve fail on the dead context and degrade, the miss path takes the free permit, `Answer` fails client-side. `ABANDONED`, nothing written, and `len(hs.rag.answerCalls()) == 0`. **The assertion pins a grpc-go detail**: `newAttemptLocked` checks `cs.ctx.Err()` before picking a transport (v1.83.0, `stream.go:455`), so an `Answer` on a dead context never sends HEADERS. The test comment says so, and says that if a grpc upgrade breaks it, pre-`Answer` leavers now create F-L orphans: re-scope F-L, do not weaken the assertion | **fails** | the fix dropped |
| T3 | **upstream `CANCELED` / `DEADLINE_EXCEEDED`, live client** | `onAnswer` returns `status.Error(code, …)` for each code, as subtests: `GENERATION_FAILED` and a 502 | **passes, a pin** | status-code keying |
| T4 | **a dead client against a full pool** | pool(1,0), `waitFor(InFlight() == 1)` with A held by the gate, then B's client leaves after Tier 1 (`leavingStore`) and B finds permit and queue full: **`SHED`**, 503. B cannot coalesce onto A: the questions differ | **passes, a pin** | the case placed above `ErrShed` |
| T5 | **a completed generation is not reclassified** | `leavingStore{afterPut: q}`: `Answer` succeeds, the client leaves during write-back. `cache: MISS`. **A D1 pin** (rule 4, `err == nil` ⇒ `MISS`); it has nothing to do with coalescing | **passes, a pin** | the `err != nil` guard dropped |
| T6 | **a live follower beside a leaving leader** | leader asks `"Is the Aurora kettle cordless?"` (cancellable context); the follower asks `"is the aurora kettle cordless"` (live): different raw text, the same normalised `t1_key`, both `embedFresh`ed. Hold `Answer`; wait for the `Answer` call and `Waiters(key) == 1`; cancel the leader; `leader.wait`; **then `g.open()`**; `follower.wait`. The follower is **not** `ABANDONED` and **something was written**. **Not** `502`. **No assertion about the leader** (T1 owns it) | **passes, a pin** | classification in the closure or `ragclient`; keying on the status code |
| T7 | **a real disconnect** | `httptest.NewServer` around `Ask`, a real client with an exact-`Content-Length` body (`bytes.Reader`) cancelled once `Answer` has started. **Read the record without `hs.records`** (the call does not go through `hs.start`): `defer srv.Close()` so the handler is drained before `t.Cleanup`; `waitFor(Counters.Requests == 1)`; `srv.Close()`; `hs.h.Eval.Close()` (idempotent); `readJSONL(t, hs.logPath)`; assert one record, `cache: ABANDONED`. Stable 300 times under `-race` | **fails** | the fix dropped, and whether a closed connection cancels `r.Context()` here |

**T3–T6 are pins, which pass on `HEAD`, and each constrains a real way to get the fix wrong.** T6 is
`DECLARED F-D-SENSITIVE` in the file. It holds today, and it holds for a plausible F-D fix in which a
live follower retries as the new leader (measured against a sketch, follower `MISS` 200) or for a
shared-context fix that keeps the generation going for the follower (PLAUSIBLE). What it forbids is
this fix making a live follower worse. T1 is what rules out an F-D fix that keeps a departed leader
waiting on a detached generation. T5 is a D1 pin, not an F-D one.

**T7 and the body.** Detection rests on the body reaching EOF (`spec.md`, limitation 1). The test uses
the exact-length shape that k6, curl and the UI send, and says so in a comment. It does not assert
the padded or chunked cases: those are recorded limitations, not behaviour to protect.

## 6. Mutations: each must be caught

Each is a scratch copy, run once against the new suite, results in `evidence/mutations.md`. **All of
them pass the entire existing suite** (measured by the review), so the new file is the only guard for
every one.

| # | Mutation | Caught by |
| :---: | :--- | :--- |
| M1 | Drop the new condition | T1, T2, T7 |
| M2 | Key it on the gRPC status code (`Canceled` / `DeadlineExceeded`) instead of `ctx.Err()` | T3, T6 |
| M3 | Drop the `err != nil` guard | T5 |
| M4 | Classify inside the closure, from the leader's context (`return nil, ctx.Err()`) | T6 |
| M4b | M4 plus the new switch case | T6 |
| M5 | Return `ctx.Err()` from `ragclient.Answer` (Option B) | T6 |
| M5b | Map status `Canceled` → `context.Canceled` in `ragclient` | T3, T6 |
| M6 | Place the new case above `ErrShed` | T4 |

## 7. Failure modes, silent first

| # | Failure | Silent? | Closed by |
| :---: | :--- | :--- | :--- |
| F1 | **F-L:** an abandoned request still holds Ollama's one slot after the gateway releases its permit, so the next request queues invisibly inside Ollama and its `t_generate_ms` absorbs the remainder | **yes** | **Not closed here.** Out of scope; recorded in `super-plan.md` at `/done`. The review's recommendation is to gate Phase 7 on it and not item 1.6 (`spec.md`). The fix makes abandonment during `Answer` countable as a bucket, without making it cost nothing |
| F2 | A wrong fix that the existing suite passes (M2, M4, M6) | **yes** | T3, T6, T4 |
| F3 | A disconnect the server cannot see (trailing bytes, an unterminated chunked body) is recorded `MISS` and counted as server-side goodput | **yes** | Limitation 1, in the experiment record. The inputs that k6, curl and the UI send are detected |
| F4 | A completed generation relabelled `ABANDONED` | **yes** | T5, M3 |
| F5 | A genuine upstream failure for a client that had also left is filed `ABANDONED` (D1) | **yes**, a decided cost | The precedence is written in the experiment record; the log line prints the error |
| F6 | A future server-side deadline is filed as a client leaving | **yes**, later | The comment at the case (acceptance 9) |
| F7 | `Counters` and the record disagree | no | Both are driven from `rec.Cache` at the single deferred exit, so they agree by construction. `/stats` counts both buckets in `requests` only, so it cannot show the fix |
| F8 | **An analysis treats `ABANDONED` as client behaviour and drops it from the failure rate.** Under k6 a client leaves only on its timeout, so each record is a request unanswered within 120 s. Already absent from p99, it would vanish from S2's signal too, and nothing would fail | **yes** | The comment at the case, the spec's rationale, and the experiment record (a censored latency observation, counted against S2, at most k6's status-0 count, which also holds `MISS`es: `spec.md` limitation 9). Nothing in code can enforce an analysis rule |
| F9 | **`ABANDONED` is read as the count of orphaned generations (F-L).** Left while queued, and a fast-path leave before or during `Answer`, give the same null/0 permit fields; only a request that queued, got the permit and then left carries `permit_queue_depth >= 1` (the field is a non-nullable `int`, so filter on the value, not on presence) | **yes** | The experiment record and the F-L entry state that `ABANDONED` (minus F-D's followers) is only an **upper bound** until F-H lands. F-H's widening is recommended next |
| F10 | **Write-back on the client's context, in two writes:** a leave between them leaves a Tier-1 entry with no Tier-2 record carrying its `t1_key` (invariant 2) | **yes**, once C2 exists | Not this fix: it does not change the window, and T5 on the fake cannot see it. Recorded for F-J's trail and Phase 2's design |

## 8. Unknowns

| # | Unknown | Status |
| :---: | :--- | :--- |
| U1 | Whether a closed connection cancels `r.Context()` in this handler | **Settled by probe** (`impact.md` §4): yes for an exact-`Content-Length` body, no for trailing bytes or a chunked body not at EOF. T7 pins the first |
| U2 | Whether `rag.server` stops generating when its RPC is cancelled | **Settled by probe** (`impact.md` §5): **no.** F-L |
| U3 | Whether T5 and T6 pin more than this fix owes | **Settled by `review.md`:** T5 pins D1 rule 4; T6 as corrected passes a retrying F-D sketch |
| U4 | Whether `grpc` fails an `Answer` on a dead context before sending it, so that T2's `answerCalls() == 0` is stable | **Settled by `review.md`** (source and 300 runs at GOMAXPROCS 1, 2, 8). Kept, with a comment (N3) |
| U7 | Whether a k6 timeout closes the TCP connection, so that `r.Context()` is cancelled (k6 is Go-based, PLAUSIBLE). T7 proves it for Go's own client only | The first run with a `RUN_ID`, in item 1.6. One k6 run with `timeout: 2s` against a stub that sleeps would settle it without Ollama |
| U8 | A client that half-closes its write side after sending is read as gone. Neither k6, curl, urllib nor `fetch` does | Record it as a limitation if a harness tool is found to |
| U5 | The cell-3 follower (joining in the microsecond between the leader's leave and the `Answer` failure) | Reasoned only; no test, no change in the live-follower column either way |
| U6 | Whether `leavingStore`'s cancel in `Put` lands before the closure returns, so that `err == nil` and `ctx.Err() != nil` hold together | **Settled by reading:** the Tier-1 `Put` is the first write-back, inside the closure (`handler.go:429`), and the closure returns `(gen, nil)` after `TrimToCapacity` (`:469`). T5 cancels in `Put` only, so `PutTier2` needs no hook. The first plan step confirms it against `HEAD` |
