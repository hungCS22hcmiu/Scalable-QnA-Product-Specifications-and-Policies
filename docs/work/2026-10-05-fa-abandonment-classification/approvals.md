# Approvals — fa-abandonment-classification

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | yes      | 2026-10-05 | — (no frozen value touched; no `run_id` invalidated: none exist, `impact.md` §1) |
| contract       | if §B/§D | not required | 2026-10-05 | `impact.md` §7: no field, enum value or wire shape changes |
| experiment     | if measured | yes (record-only) | 2026-10-05 | — Which requests land in `ABANDONED` versus `GENERATION_FAILED` changes (`impact.md` §7); the precedence, the censored-latency reading and the orphan upper bound are recorded (`spec.md` limitations 1–6; `plan.md` step 4). Nothing re-measured. Invalidates no `run_id`: none exist. Logs are not comparable across the commit for that split |
| implementation | always   | yes      | 2026-10-05 | — (no ADR: no frozen value and no contract changes) |

## Human decisions

| Date | Decision | Author's words | Invalidates |
| :--- | :--- | :--- | :--- |
| 2026-10-05 | **Open the F-A bugfix before 1.5 and 1.6** | "ok bugfix trước đi" | — |
| 2026-10-05 | **D1: when the client has gone AND the upstream also failed for real, the label is `ABANDONED`.** Precedence: `SHED` > this request's client gone ⇒ `ABANDONED` > `GENERATION_FAILED`; `err == nil` is always `MISS`. A genuine upstream failure for a client that had also left is therefore not counted as `GENERATION_FAILED`; the log line still prints the error. The alternative (also require a `Canceled`/`DeadlineExceeded` status) was rejected: it needs gRPC types in `httpapi` or a change to `ragclient` | Chose *"ABANDONED thắng (Recommended)"* | none: no runs exist; a future log is not comparable across the commit for the `ABANDONED` / `GENERATION_FAILED` split |

## Open — needs the author

None for this task. `impact.md` raised one decision (D1, above) and it is made.

**For the author, not blocking this task: F-L** (`impact.md` §5). `rag.server` keeps generating after its
RPC is cancelled, so an abandoned request still holds Ollama's one slot after the gateway releases its
permit. It must be fixed, or shown not to occur, before Phase 7, and item 1.6 has to account for it.
`/done` records it in `super-plan.md`. Whether it is fixed before 1.6 is the author's call.

## Experiment record (phase approved 2026-10-05, record-only)

Nothing is re-measured: no run exists. From this commit on, the miss path files a failed request
as follows. **A log written before it is not comparable for the `ABANDONED` / `GENERATION_FAILED`
split; every other field is comparable.**

**The precedence (D1).** For one request, in order:
1. `ErrShed` → **`SHED`**, even if the client has since left.
2. This request's own client has gone → **`ABANDONED`**, nothing written, whatever the error was.
3. The error is real and the client is connected → **`GENERATION_FAILED`** and a 502.
4. `err == nil` → **`MISS`**, whether or not the client has since left.

| Request | Before | After |
| :--- | :--- | :--- |
| Client leaves while `Answer` is in flight | `GENERATION_FAILED`, 502 written | **`ABANDONED`**, nothing written |
| Client leaves after Tier 1, during embed or retrieve | `GENERATION_FAILED`, 502 written | **`ABANDONED`** (the server never sees the RPC) |
| Client leaves while queued for the permit | `ABANDONED`; a coin flip with `GENERATION_FAILED` when the permit freed at the same moment | `ABANDONED`, always |
| Upstream `CANCELED` / `DEADLINE_EXCEEDED` raised by `rag.server`, client connected | `GENERATION_FAILED` | same |
| Client gone, pool and queue full | `SHED` | same |
| Generation completed, client leaves during write-back | `MISS` | same |
| Coalesced follower, live client, leader's client left during `Answer` | `GENERATION_FAILED`, 502 | same |
| Coalesced follower whose own client has gone | `GENERATION_FAILED` | `ABANDONED` |

**How to read `ABANDONED`** (`review.md` S1, S3):
- **Under a load generator it is a censored latency observation, at least the client timeout.** A k6
  client leaves only on its own timeout (`ask.js`: `timeout: '120s'`), so each record is a request
  that went unanswered that long. It **counts against S2 and goodput** and is at most k6's status-0
  count (see the reconciliation below). It is **never excluded from the analysis as client behaviour**, and it is
  already absent from p99 (k6's `answered_latency_ms` holds only `200`s).
- **An upstream hang mostly lands in `ABANDONED`**, not `GENERATION_FAILED`. The generate timeout
  (`httpx`, `generate.py:15`) and k6's are both 120 s, but k6's clock starts at the request and
  includes the queue wait, so k6 usually leaves first. **`GENERATION_FAILED ≈ 0` in a run does not
  show that the upstream never hung.**
- **It is only an upper bound on orphaned generations (F-L)** (corrected by the implementation
  review, C3). A request that left while queued has `t_permit_wait_ms` null and
  `permit_queue_depth` 0. One that took `Acquire`'s fast path and left before `Answer` (the server
  sees 0 RPCs, no orphan) or during `Answer` (an orphan) also has both null/0, so those two cannot be
  told apart. One that **queued, got the permit, then left** has `t_permit_wait_ms` non-null and
  `permit_queue_depth >= 1`: it was admitted, so its `Answer` was attempted, and a filter on
  `permit_queue_depth >= 1` (the field is a non-nullable `int`, so not on presence) selects that
  orphan-candidate subset. `t_generate_ms` is null on all of them. A null `t_permit_wait_ms` rules
  out only the queued-and-left case. F-H's widening (copy `t_generate_ms` into the `ABANDONED` case)
  is what would separate the rest.
- **`GENERATION_FAILED > 0` does not show an upstream fault, until F-D lands** (C2). A live follower
  of a leader cancelled during `Answer` inherits the leader's cancellation and is recorded
  `GENERATION_FAILED` with a 502 whose body reads *"rpc error: code = Canceled"*. One departed leader
  therefore gives one `ABANDONED` and N `GENERATION_FAILED`. This mirrors the `GENERATION_FAILED ≈ 0`
  caveat above: neither a zero nor a non-zero count of that bucket isolates the upstream.

**The residual misattributions, each a request in the wrong bucket:**
- **A disconnect the server cannot see** (a body with trailing bytes, an unterminated chunked body):
  `r.Context()` is cancelled only once the body has been read to EOF, so the request runs to
  completion and is recorded `MISS` and counted as server-side goodput. An exact-`Content-Length`
  body (k6, curl, urllib, the UI) is detected. A client that half-closes its write side after sending
  would be read as gone (none of those tools does).
- **A coalesced follower whose client left while the leader's generation succeeded** (C1): followers
  wait on the leader and never watch their own context (`coalesce.go:44-47`), so the server saw a
  disconnect and still records **`MISS`**, `coalesced`, written to a dead connection. Under Zipf
  redundancy with a saturated slot, waiting followers are the likely source of the gap between
  `ABANDONED` and k6's status-0 count.
- **A client that leaves as the generation finishes:** after `Answer` returned, `MISS` (and with the
  real store the write-back then fails on the dead context, F-J); just before the result arrives,
  `ABANDONED` with `t_generate_ms` null (F-H).
- **F-D's live followers** (the leader left while queued): `ABANDONED`, nothing written, an empty
  `200` on the wire. k6 counts that in `goodput` and again in `error_rate`.
- **A genuine upstream failure for a client that had also left:** `ABANDONED` (D1). The log line
  prints the error.

**Client and server counts reconcile as** (corrected by the implementation review, C1): excluding
F-D's live followers, every `ABANDONED` is a client that left, so **`ABANDONED` is at most k6's
status-0 count**. The converse does not hold: a status 0 can be a `MISS` (a disconnect the server
never saw, or a waiting follower whose leader succeeded), or leave **no server record** (a transport
error). F-D's live followers are the opposite case: `ABANDONED` on the server and a `200` on the
client.

**Open, for item 1.6:** whether a k6 timeout closes the connection, so that `r.Context()` is
cancelled, is proven here only for Go's own client (test T7). The first run with a `RUN_ID` settles it.

**F-L and Phase 7.** `rag.server` keeps generating after its RPC is cancelled (`impact.md` §5,
probed), so an abandoned request still holds Ollama's one slot after the gateway releases its permit.
The review recommends gating **Phase 7 (7.1, 7.5)** on it and having **item 1.6 report the
`ABANDONED` count**.

## Taken by Claude as a default, open to reversal

- **S3, option (a)** (`review.md`): F-H's widening stays out of this task, and the experiment record
  states that `ABANDONED` is only an upper bound on orphan exposure until F-H lands. **Recommended
  next: F-H as its own bugfix, before item 1.6 reports its `ABANDONED` count.**
- **F-L gating** (`review.md` Q8): gate Phase 7 (7.1, 7.5) on it, not item 1.6. This corrects an
  earlier summary that said 1.6.

## Notes

- `/bugfix` raised this to **L** without asking: the outcome label is on the measured path.
- The `/task` template rendered with its arguments shifted ("task `L` at scope `Client`"). The
  intended values were used: slug `fa-abandonment-classification`, scope `L`.
