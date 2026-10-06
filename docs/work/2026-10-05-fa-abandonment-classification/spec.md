# Spec — fa-abandonment-classification

**Scope:** L · **Opened:** 2026-10-05 · **Opener:** `/bugfix`, raised to L (the cause is in an outcome
label the evaluation counts) · **Phase:** 1, a prerequisite of item **1.6**
**Revision 3**, after `review.md`. Rev 2 applied all 13 of `impact.md`'s corrections, and D1 is the
author's. Rev 3 applies the review's S1–S3 and N1–N5; none of them changes the fix itself.

## The change in one sentence

When a client leaves while a request is still being served, `Ask` records it as **`ABANDONED`**
and writes nothing, instead of recording **`GENERATION_FAILED`** and writing a 502 to a dead
connection.

## The bug, and its cause

**Cause, one sentence.** grpc-go reports a cancelled call as a `*status.Error` with code
`Canceled`, and `errors.Is(err, context.Canceled)` does not match it (probe, grpc-go v1.83.0:
`docs/work/2026-10-04-httpapi-tests/evidence/grpc-cancel-probe.md`). `Ask`'s outcome switch
(`handler.go:494`) tests only `errors.Is`, so a client that leaves **while `Answer` is in flight**
falls through to `case err != nil` and is filed as `GENERATION_FAILED`.

Read from the code, not only from the 1.2 note:
- `ragclient.Answer` returns the `Recv`/`NewStream` error unwrapped (`answer.go:41, :51`).
- `Pool.Acquire` returns `ctx.Err()` (a real `context.Canceled`) **only** for a client that leaves
  while queued (`pool.go:113-114`). That is the one path `TestAbandonedWhileQueuedIsNotAShed` covers.
- At one slot (ADR-003) most misses take `Acquire`'s fast path (`pool.go:93-97`), so most
  abandonments happen at or after `Answer` starts, which is the path that is misclassified.

## What it serves

- **Phase 1, a prerequisite of item 1.6** (`super-plan.md`, *"Found while closing 1.2"*): *"F-A: most
  client abandonments are logged `GENERATION_FAILED`. … Fix it before 1.6 and before any Phase 7
  run."* Item 1.6 measures the system under k6's load, where client timeouts are expected.
- **Why it matters for the numbers.** The two buckets answer different questions:
  `GENERATION_FAILED` is *the upstream returned an error while this request's client was still
  connected* (or, until F-D lands, a coalesced follower inherited its leader's cancellation:
  limitation 8), and `ABANDONED` is *the client stopped waiting*. Today most of the second are filed under the first, so the upstream error rate is
  inflated by requests that were merely slow or whose client left.
- ⚠️ **`ABANDONED` is not client behaviour to exclude** (`review.md` S1). Under a load generator a
  client leaves only on its own timeout (`ask.js`: a constant-arrival-rate scenario with
  `timeout: '120s'`). An `ABANDONED` record there is a request that was **not answered within that
  time**: a **censored latency observation, at least the client timeout**. It counts against S2 and
  goodput, and is at most k6's status-0 count (limitation 9). It is already absent from p99 (k6's
  `answered_latency_ms` holds only `200`s), so excluding it from the failure rate as well would make
  S2's falsification signal disappear with nothing failing.
- `contracts/requirements.md` is still empty, so no `FR/NFR/RR` is cited.

## Why scope L, and which phases

The outcome label is on the measured path: `rec.Cache` feeds the §H record and `Counters`, and
`/bugfix` raises any cause "in anything measured" to L. The fix restores what `handler.go:494-499`
already says it means, and **no contract and no frozen value changes**.
- **Contract phase: not required.** No field, enum value or wire shape moves (`impact.md` §7). The
  §H `cache` enum sync waits for F-B and is not this task's.
- **Experiment phase: required, record-only.** Which requests land in `ABANDONED` and which in
  `GENERATION_FAILED` changes, and the precedence that decides it is written down nowhere else.
  Nothing is re-measured, because no run exists.

## The decision: precedence (D1, the author's)

Per request, after the generation returns `(gen, err)`:

1. `err` is `ErrShed` → **`SHED`**. Unchanged, and above everything below it.
2. `err != nil` and **this request's own client has gone** → **`ABANDONED`**, nothing written. This
   holds whatever `err` is, so a genuine upstream failure for a client that had also left is filed
   here. The log line prints the error.
3. `err != nil` and the client is connected → **`GENERATION_FAILED`** and a 502.
4. `err == nil` → **`MISS`**, whether or not the client has since left: the generation happened and
   wrote back.

## Acceptance — each is a check that can be run

1. **Client leaves while `Answer` is in flight → `ABANDONED`.** With `Answer` held and the client
   context cancelled after the RPC started: the record shows `cache: "ABANDONED"` and
   `shed: false`; no status, header or body was written; the permit is released.
2. **Client leaves after Tier 1, during embed or retrieve → `ABANDONED`.** A cache wrapper in the
   new test file cancels the request's context as `Get` returns its miss. Embed and retrieve fail
   and degrade, the miss path takes the free permit, and `Answer` fails on the client side:
   `ABANDONED`, nothing written, and the server **never saw the RPC**.
   *(Not "cancelled before `Ask`": real Redis rejects a dead context at Tier 1, so that request
   ends as F-B in production. `fakeStore` ignores the context, which would test a path that does
   not exist.)*
3. **A live client sees no change:**
   - an upstream **`CANCELED` or `DEADLINE_EXCEEDED`** raised by `rag.server` itself (a restart is
     the real case) is `GENERATION_FAILED` and a 502;
   - a client that is gone and meets a **full pool and queue** is still **`SHED`**.

   The fix classifies by *this request's own context*, never by the status code, and sits **below**
   the shed case.
4. **A completed generation is never reclassified.** The cache wrapper cancels the request's
   context inside write-back (`Put`/`PutTier2`) after `Answer` has succeeded: the record stays
   **`MISS`**.
5. **A live follower is not made worse.** The leader's client leaves during `Answer`; a follower
   that joined the same generation stays connected. The follower **got a written response and is
   not `ABANDONED`**. The test does **not** assert `502` or `GENERATION_FAILED`: that would pin F-D's
   defect. It does not assert the leader's label either (acceptance 1 owns that). The follower asks
   the same question in different raw text, so the two records can be told apart, and the gate is
   opened after the leader returns, so a follower that is retried can finish. A future F-D fix that
   answers or retries the follower still passes (measured against a sketch of one, `review.md` S2).
6. **A real disconnect is recorded `ABANDONED`.** One test through `httptest.NewServer` and a real
   client that cancels mid-request, with an exact-`Content-Length` body (`bytes.Reader`). The harness
   injects a context, so it does not show that closing a connection cancels `r.Context()` here.
7. **No existing test changes**, not even a comment. `git diff` on every existing `_test.go` file is
   empty. `ask_test.go:369-370` (*"a cancellation that reaches a gRPC call is logged
   GENERATION_FAILED today (F-A)"*) becomes false, and is recorded in `plan.md`, not edited, as
   1.3 did with its stale comments. New tests go in a **new** file.
8. **Mutations are caught** (`design.md` §6): the fix dropped; keyed on the gRPC status code (in the
   handler and in `ragclient`); the `err != nil` guard dropped; classified inside the closure or in
   `ragclient` from the leader's context; and placed above the shed case. **Every one passes the
   whole existing suite** (measured by the review), so the new file is the only guard for each.
9. **The code says what it assumes, and does not prejudge the cause.** The comment at the case
   replaces *"not an error the gateway caused"* (`handler.go:495`) with wording that holds under a
   load generator: the client left, and that is a timeout counted against S2. It also states the
   assumption that the request context is cancelled only by the client (`main.go:244` sets no
   server timeout or `BaseContext`), so a future server-side deadline would be filed as a client
   leaving, and `context.Cause` is the tool if that changes.
10. `make verify` is green.

## Limitations, recorded rather than fixed

These go in the experiment record, because each leaves a request in a bucket it does not belong to.
1. **A disconnect the server cannot see.** `r.Context()` is cancelled only once `Decode` has read the
   body to EOF. An exact-`Content-Length` body (k6, curl, urllib, the UI) is detected at once. A body
   with trailing bytes, or a chunked body whose terminator has not arrived, is not: the request runs
   to completion and is recorded `MISS`. Draining the body would remove the dependence; it is cut.
2. **A client that leaves as the generation finishes.** After `Answer` returned: `MISS` (correct),
   though the write-back then fails on a dead context with the real store (F-J). Just before the
   result arrives: `ABANDONED` with `t_generate_ms` null (F-H).
3. **F-D's live followers** (the leader left while queued) stay `ABANDONED` with an empty `200`.
4. **A genuine upstream failure for a client that had also left** is `ABANDONED` (D1).
5. **Under k6, `ABANDONED` (minus F-D's followers) is a censored latency observation** (see above),
   and **an upstream hang mostly lands in it** (`review.md` S1). The generate timeout (`httpx`,
   `generate.py:15`) and k6's (`ask.js:124`) are both 120 s, but k6's clock starts at the request and
   includes the queue wait, so k6 usually leaves first. **`GENERATION_FAILED ≈ 0` in a run does not
   show that the upstream never hung.**
6. **`ABANDONED` cannot be fully broken down in §H** (`review.md` S3; corrected by the
   implementation review, C3). Three kinds of leave can look alike, and one cannot:
   - **Left while queued** (never got the permit; no orphan): `t_permit_wait_ms` null,
     `permit_queue_depth` 0.
   - **Took `Acquire`'s fast path, then left before `Answer`** (the server sees 0 RPCs; no orphan) or
     **during `Answer`** (an orphan, F-L): both also leave `t_permit_wait_ms` null and
     `permit_queue_depth` 0. These two are indistinguishable.
   - **Queued, got the permit, then left during `Answer`:** `t_permit_wait_ms` is **non-null** and
     `permit_queue_depth` is **≥ 1** (`handler.go:395-396` sets both as soon as `Acquire` succeeds).
     It was admitted, so its `Answer` was attempted: an **orphan candidate** a filter can select (on
     `permit_queue_depth >= 1`, not on presence: the field is a non-nullable `int`).

   `t_generate_ms` is null on all of them (F-H), and a follower's `ABANDONED` looks the same. A null
   `t_permit_wait_ms` therefore rules out only the queued-and-left case, not an orphan.
   **`ABANDONED` (minus F-D's followers) is only an upper bound on orphan exposure until F-H
   lands.**
7. **Whether a k6 timeout closes the connection** so that `r.Context()` is cancelled is unproven
   (k6 is Go-based, PLAUSIBLE). Test T7 proves it for Go's own client. The first run with a `RUN_ID`
   settles it.
8. **`GENERATION_FAILED > 0` does not show an upstream fault, until F-D lands** (implementation
   review, C2). A live follower of a leader cancelled during `Answer` inherits the leader's
   cancellation through `coalesce.Do` and is recorded `GENERATION_FAILED` with a 502 whose body reads
   *"rpc error: code = Canceled"*. After the fix, one departed leader gives `ABANDONED` for the
   leader and `GENERATION_FAILED` for each live follower. This is the mirror of limitation 5's
   `GENERATION_FAILED ≈ 0` caveat: neither a zero nor a non-zero count of that bucket isolates the
   upstream.
9. **`ABANDONED` against k6's status-0 count** (implementation review, C1). Excluding F-D's live
   followers, every `ABANDONED` is a client that left, so `ABANDONED` is **at most** k6's status-0
   count. The converse does not hold. A status 0 can be:
   - a **`MISS`**, for a disconnect the server never saw (limitation 1), **or for a coalesced
     follower whose client left while the leader's generation succeeded**: followers wait on the
     leader and never watch their own context (`coalesce.go:44-47`), so the server saw the
     disconnect and still records `MISS` with `coalesced`, written to a dead connection. Under Zipf
     redundancy with a saturated slot, waiting followers are the likely source of this gap;
   - a request with **no server record at all** (a transport error).

   F-D's live followers are the opposite case: `ABANDONED` on the server and a `200` on the client.

## Out of scope

- **F-D.** The fix must not change what a follower with a live client receives. A follower whose
  **own** client has gone moves `GENERATION_FAILED` → `ABANDONED`, which is the rule working.
- **F-H**, widened: `t_generate_ms` is dropped on `GENERATION_FAILED` **and now on `ABANDONED`**,
  where most generation time spent on failures will land. Copying `generateMS` into the `ABANDONED`
  case would let a non-null value mean *this request's own `Answer` was attempted* (a few µs: the RPC
  never left; more: it reached `rag.server`) and so identify the orphan subset. **Recommended as the
  next bugfix, before item 1.6 reports its `ABANDONED` count** (`review.md` S3, option b); the author
  decides. **F-C**, **F-J**: each its own bugfix.
- **Write-back runs on the client's context, as two separate writes** (`store.go:68`,
  `tier2.go:118`; `review.md` N5). A client leaving between them leaves a Tier-1 entry with no
  Tier-2 record carrying its `t1_key`, which is invariant 2's silent purge miss once C2 exists. The
  window is one Redis round trip and this fix does not change it. Recorded for F-J's trail and
  Phase 2's design: run write-back on `context.WithoutCancel(ctx)` with a timeout, as the Tier-1
  promotion already does.
- **`Pool.Acquire`'s fast path, `coalesce.go`, `ragclient/`, the harness.** Unchanged. The fast path
  costs a request that is already gone one microsecond of a permit, and no wrong label.
- **F-L, `rag.server` keeps generating after its RPC is cancelled** (`impact.md` §5, probed): an
  abandoned request still holds Ollama's one slot after the gateway releases its permit. It is a
  separate finding. `/done` records it in `super-plan.md`. **The review's recommendation: gate
  Phase 7 (7.1, 7.5) on it, not item 1.6.** An orphan adds no memory, because Ollama's footprint is
  fixed when it loads (ADR-003), so F-L cannot move 1.6's CPU/RSS number (PLAUSIBLE); item 1.6 should
  report the `ABANDONED` count. With k6's 120 s timeout against an admitted-latency bound of
  (1 + q) · S, abandonment during `Answer` should be near zero, and a run that measures exactly that
  would close F-L by measurement. Whether to fix it before 1.6 is the author's.
- The §H `cache` enum sync (waits for F-B), the k6 non-empty-`answer` check (F-D's other half), and
  item 1.6 itself.
