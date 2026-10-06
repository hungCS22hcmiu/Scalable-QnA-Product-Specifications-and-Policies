# Design review — fa-abandonment-classification

**Reviewer:** `design-reviewer` (opus), 2026-10-05. This reviews `design.md` rev 2, together with `spec.md` rev 2, `impact.md` and `approvals.md` (D1).

**Method:** read-only against the repository. Ollama was not called, no model was loaded, and Redis was not touched. Memory pressure read 2 throughout. That does not affect these results because nothing here measured a latency. `git status` shows the working tree unchanged. All probes ran in scratch copies under the session scratchpad (`fa-review/`, not in the repo):
- **`head/`** is today's code. **`fix/`** is the design applied **exactly as §1 writes it**: one extra conjunct in the `ABANDONED` case plus the comment, and no other edit.
- **T1–T7 were written as §5 specifies them**, using the `leavingStore` wrapper around `*fakeStore`.
- **Runs on both versions.** The new tests and the whole existing `httpapi` suite were run on both versions, under `-race`. The new tests were also run 300 times each, at GOMAXPROCS 1, 2 and 8.
- **A coalescing-matrix probe** printed every participant's outcome, cell by cell, on both versions.
- **Eight mutation copies**: M1–M6, plus M4b and M5b variants.
- **A sketch of a plausible F-D fix** (a live follower retries once) to test the "constrains no F-D design" claim.

**CONFIRMED** means checked against the code, by a run, or in the grpc-go v1.83.0 / go-redis v9.22.0 module source. **PLAUSIBLE** means reasoned only. The reviewer has no write tool, so Claude saved this report as returned.

**Verdict: the fix is sound, correctly placed, and the smallest one. Approve the code change as written.** The test design needs two corrections before implementation, because T6 as written fails on every version (S2). The experiment record is missing what the relabelled bucket *means* under a load generator (S1) and cannot support the F-L count it promises (S3). None of this changes the one line in `handler.go`.

## Findings, most severe first

| # | Sev. | Finding | Check | Smallest fix (the author decides) |
| :---: | :---: | :--- | :---: | :--- |
| **S1** | should-fix (experiment record) | **Under k6, `ABANDONED` is a latency failure of the system under test, but the fix files it under a label the code calls "not an error the gateway caused".**<br>• `ask.js` uses `constant-arrival-rate` with `timeout: '120s'`. A k6 VU never leaves on its own: it leaves only when the system did not answer within 120 s. So in a Phase 7 run, every `ABANDONED` except F-D's followers is a request whose latency exceeded 120 s.<br>• Today those requests land in `GENERATION_FAILED`, an error bucket. After the fix they land in `ABANDONED`. The comment the fix keeps (`handler.go:495`) says *"Not a shed, not an error the gateway caused"*. The spec gives the reason for the fix as *"clients that simply left"*.<br>• An analysis that follows those words will drop the records from the failure rate. They are already absent from p99: k6's `answered_latency_ms` holds only 200s, and §H's served buckets exclude them.<br>• That removes S2's falsification signal (*"excess is queued, not shed"*; p99 > 2×). Nothing fails; the number just looks better.<br>• **D1 makes it worse in one specific way.** `generate.py`'s httpx timeout is also 120 s, but it starts when the generate call starts. k6's clock started earlier, at the request, so it includes queue wait. An Ollama hang therefore mostly ends with k6 leaving first, and is recorded `ABANDONED`. So `GENERATION_FAILED ≈ 0` in a run does **not** show that the upstream never hung | Constants and executor CONFIRMED (`ask.js:93,124`, `generate.py:15`, `handler.go:495`). Which clock fires first is PLAUSIBLE | **Record-only:**<br>• Add one paragraph to the experiment record. In a load-generator run, `ABANDONED` (minus F-D followers) is a **censored latency observation, ≥ the client timeout**. It counts against S2 and goodput, and reconciles 1:1 with k6's status-0 count. It is never excluded from the analysis as client behaviour.<br>• Add the 120 s/120 s note.<br>• In the case's comment (which the design already edits), replace "not an error the gateway caused" with wording that does not prejudge the cause, e.g. *"the client left; under a load generator that is a timeout, counted against S2"*.<br>• Fix the spec's "clients that simply left" rationale to match |
| **S2** | should-fix (tests) | **T6 as written fails on HEAD and on the fix, and as written it does constrain F-D.**<br>• **(a) Record matching.** Leader and follower share one question, and neither returns a JSON `request_id`: the follower's 502 is plain text. `records()` therefore falls back to matching on `query_raw` and hits `t.Fatalf("… matches more than one unclaimed record")` (`harness_test.go:1006`). Measured on both versions.<br>• **(b) The gate is never opened.** Under a plausible F-D fix (a live follower retries as the new leader), the follower's retry blocks on the held gate and the test dies with *"an Ask call did not return within 5s"*. Measured with the `fd_retry` sketch. That contradicts §5's *"they hold for any F-D fix that answers or retries the follower"*.<br>• **(c) The leader assertion.** `leader ABANDONED` makes T6 fail on HEAD, so it is not the pin the table says it is. It also duplicates T1 | CONFIRMED (runs) | Three changes, with no harness change:<br>• Give the follower a different raw question that normalises to the same `t1_key` (`"Is the Aurora kettle cordless?"` / `"is the aurora kettle cordless"`), and `embedFresh` both.<br>• Call `g.open()` after `leader.wait(t)`.<br>• Drop the leader assertion; T1 owns it.<br>Measured result (T6c): it passes on HEAD and on the fix, passes under the retrying F-D sketch (follower `MISS` 200), and still catches M2, M4, M4b, M5 and M5b |
| **S3** | should-fix (experiment record / F-L handoff) | **§H cannot separate the abandonments that leave an orphaned generation (F-L) from those that do not, and the 1.6 metric `impact.md` §5 proposes cannot be computed.**<br>• Measured on the fix, three kinds of abandonment produce the same record: left while queued (no orphan), left before `Answer` (T2's path: 0 RPCs, no orphan), and left during `Answer` (orphan). All three carry `t_permit_wait_ms: null`, `permit_queue_depth: 0`, `t_generate_ms: null` and no `coalesced`. A follower's `ABANDONED` looks the same as well.<br>• `PermitQueue` is a non-nullable `int` (`evallog.go:51`). So *"count `ABANDONED` records carrying `permit_queue_depth`"* selects every record.<br>• Design §7 F1 says the fix *"makes these events visible as `ABANDONED`"*. That is true of the bucket, not of the F-L subset | CONFIRMED (matrix probe; `evallog.go`) | Pick one:<br>• **(a)** In the F-L entry `/done` writes, state that `ABANDONED` (minus F-D) is only an **upper bound** on orphan exposure until F-H lands.<br>• **(b)** Land F-H's widening before 1.6: copy `generateMS` into the `ABANDONED` case. Then `t_generate_ms != null` on an `ABANDONED` means this request's own `Answer` was attempted. A value of a few µs means the RPC never left (T2's path); anything larger means it reached `rag.server`.<br>The cut in the spec can stand if (a) is written down |
| N1 | nit | **§6 understates the mutation gap. All six mutations, not just the three marked ◆, pass the whole existing suite** (measured). The new file is the only guard for every one of them. T6 (corrected) also catches M2, and the original T6's leader half also catches M1 | CONFIRMED | Drop the ◆ distinction. Use the measured table below in `evidence/mutations.md` |
| N2 | nit | **T7 cannot use `hs.records`.** It does not go through `hs.start`, so `records()` would `Fatalf` on 1 record for 0 calls. The design does not say how T7 reads its record. A late `Log` racing the harness's `Eval.Close` is the panic `harness_test.go:769-771` warns about | CONFIRMED (run) | This works and was stable 300 times under `-race`:<br>• `defer srv.Close()`, so the handler is drained before `t.Cleanup` runs;<br>• `waitFor(Counters.Requests == 1)`;<br>• `srv.Close()`, then `hs.h.Eval.Close()` (idempotent);<br>• `readJSONL(t, hs.logPath)`, then assert one record with `cache: ABANDONED` |
| N3 | nit | **T2's `answerCalls() == 0` is stable, and it pins a grpc-go detail.** In grpc-go v1.83.0, `newAttemptLocked` checks `cs.ctx.Err()` before picking a transport (`stream.go:455`), so an `Answer` on a dead context never sends HEADERS. It held in 300 runs at GOMAXPROCS 1, 2 and 8 | CONFIRMED (source and runs) | Keep the assertion, with a comment naming the grpc behaviour. Say that if a grpc upgrade breaks it, pre-`Answer` leavers now create F-L orphans: re-scope F-L, do not weaken the assertion |
| N4 | nit | **T5 is mislabelled "F-D-sensitive".** It has nothing to do with coalescing. It pins D1 rule 4 (`err == nil` ⇒ `MISS`), which is right | CONFIRMED | Label it a D1 pin |
| N5 | forward, out of scope | **Write-back runs on the client's context as two separate HSETs** (`store.go:68`, `tier2.go:118`). go-redis checks the context before taking a connection (`pool.go:1164-1170`). A leave between the two writes therefore leaves a Tier-1 entry with no Tier-2 record carrying its `t1_key`. That is invariant 2's silent purge miss once C2 exists. The window is one Redis round trip. The fix does not change it, and T5 (on the fake) cannot see it | CONFIRMED (reading) | Add it to F-J's trail and to Phase 2's design input: run write-back on `context.WithoutCancel(ctx)` with a timeout, as the Tier-1 promotion already does |

### Mutations (measured, `-race`; T6 run as its corrected form)

| # | Mutation | New tests that fail | Existing suite |
| :---: | :--- | :--- | :--- |
| M1 | condition dropped | T1, T2, T6 (leader half), T7 | passes |
| M2 | keyed on `status.Code` ∈ {Canceled, DeadlineExceeded} | T3 (both subtests), T6 | passes |
| M3 | `err != nil` guard dropped | T5 | passes |
| M4 | classified in the closure (`return nil, ctx.Err()`), switch as today | T6 | passes |
| M4b | M4 plus the new switch case | T6 | passes |
| M5 | `ragclient.Answer` returns `ctx.Err()` (Option B) | T6 | passes |
| M5b | `ragclient` maps status `Canceled` → `context.Canceled` | T3/Canceled, T6 | passes |
| M6 | new case placed above `ErrShed` | T4 | passes |

## The numbered questions

1. **The fix changes no outcome that §3 says is unchanged (CONFIRMED, matrix probe on both versions).** Followers used raw questions that normalise to one key.
   - **Cell 1** (leader cancelled while queued): leader, live follower and gone follower are all `ABANDONED` with nothing written, on both versions. That is F-D's empty 200.
   - **Cell 2** (leader cancelled during `Answer`): the leader goes `GENERATION_FAILED` 502 → `ABANDONED`. **The live follower stays `GENERATION_FAILED` with a 502, body byte-identical** (`rpc error: code = Canceled desc = context canceled`). The gone follower goes `GENERATION_FAILED` → `ABANDONED`.
   - **Cell 4** (leader succeeds, a follower's client has left): all three are `MISS` 200 with `coalesced: true` on the followers, on both versions.
   - **Leader succeeds but its own client leaves during write-back** (cell 4b): leader `MISS` 200 and live follower `MISS` 200, on both versions.
   - **Cell 5** (genuine `Internal` failure, leader live): leader and live follower `GENERATION_FAILED` 502, unchanged. The gone follower becomes `ABANDONED` (D1).
   - **Cell 3 is still not orchestrable** without a hook. It is strengthened, though: a pre-`Answer` cancellation (T2 on HEAD) yields the same `status Canceled` value as cell 2. The switch is a function of the error's class and the request's own context, so cell 3's follower gets cell 2's outcome (PLAUSIBLE, with a measured basis).
2. **`leavingStore` is deterministic and race-free (CONFIRMED).**
   - The cancel runs synchronously on the request goroutine before `Get` (or `Put`) returns, so every later call sees a dead context.
   - `hs.h.Cache` is assigned before `hs.start`'s `go` statement, so the assignment happens before the request starts. `-race` was clean over 900 runs.
   - Keying on the question text holds for T2, T4 and T5. With a shared question, whichever request's `Get` ran first would fire the one `CancelFunc`. T6 avoids this because it uses the gate, and the corrected T6 uses different raw text anyway.
   - `Put` as the cancel point does give `err == nil ∧ ctx.Err() != nil` at the switch. M3 (guard dropped) fails T5 and only T5, which proves both conditions hold there.
3. **T2 behaves as claimed (CONFIRMED).**
   - The embedder saw 0 requests, and Retrieve and Answer each saw 0 RPCs. The record is not a 500 and not `""`.
   - On HEAD the response is a 502 whose body is a gRPC status. That proves the request took `Acquire`'s fast path and called `Answer`: a queued `Acquire` returns a raw `context.Canceled`, which would already be `ABANDONED` on HEAD.
   - `InFlight()` is 0 afterwards.
   - `answerCalls() == 0` is stable (N3). Keep it, with the comment.
4. **T4 is deterministic, and M6 flips it (CONFIRMED).**
   - `waitFor(InFlight() == 1)` comes before B starts, and at pool(1,0) B's `Acquire` must return `ErrShed`. B cannot coalesce onto A because the questions differ.
   - M6 fails T4 and nothing else.
5. **`hs.records`.**
   - **T6:** matching does not survive a shared question (S2a, measured). Differing raw text with the same normalised form fixes it with no harness change.
   - **T7:** cannot use `records()`. Read it as in N2.
6. **T5 and T6.**
   - **T5** pins D1 rule 4. That is legitimate, and F-D is not involved (N4).
   - **T6 as written constrains F-D**, because the held gate blocks a retrying fix (S2b, measured).
   - **The corrected T6** passes under the retrying F-D sketch (follower `MISS` 200). It should also pass a ref-counted shared-context F-D fix, where the leader returns on its own context and the generation continues for the follower (PLAUSIBLE).
   - **Constraint still left:** T1 and the leader half of T6 rule out an F-D fix that keeps a departed leader waiting on a detached generation. Dropping the leader half (S2c) leaves only T1 holding that line, and T1 is this task's own claim.
7. **D1: three consequences the record does not yet state.**
   - k6 timeouts become `ABANDONED` and must still count against S2 (S1).
   - Because both timeouts are 120 s, upstream hangs land in `ABANDONED` (S1).
   - `ABANDONED` cannot be broken down by leader or follower, or by orphan or not (S3). F-D's live followers also carry no `coalesced` flag in §H. `rec.Coalesced` is set only on `MISS` (`handler.go:511`).

   **Otherwise the precedence, the residual misattributions and the client/server reconciliation in `impact.md` §7 are complete.**
8. **F-L: ship this fix alone.** It does not lose value because of F-L.
   - The fix is what makes abandonment-during-`Answer` countable at all. Before it, those requests are mixed into `GENERATION_FAILED` with real failures.
   - **What I would tell the author:**
     - **Gate Phase 7 (7.1, 7.5) on F-L, not item 1.6.** 1.6's done-when is k6's CPU and RSS with the SUT's pressure zone. An orphan adds no memory, since Ollama's footprint is fixed at load (ADR-003), so F-L cannot move 1.6's number (PLAUSIBLE). 1.6 should only report the `ABANDONED` count.
     - **Do F-H's widening next**, or at least before 1.6 reports that count, so the orphan subset can be identified (S3).
     - With k6's 120 s timeout against an admitted-latency bound of (1+q)·S, abandonment during `Answer` should be near zero. If 1.6 or 7.x measures exactly that, F-L can be closed by measurement rather than code.
9. **Other things checked.**
   - **Tier-2 candidate while the client leaves:** this was probed (T2's path with a seeded hit is the same code). The request degrades to `ABANDONED` with `similarity: null`, and no orphan is created.
   - **`Counters`:** both buckets count in `Requests` only. `records()`' `Counters.Requests` check passed on every run.
   - **The log line** now prints a gRPC status. It is harmless.
   - **k6** counts the leave in `error_rate`. See S1.
   - **F-H widening:** see S3.
   - **New: write-back on a dead context.** See N5.

## Unknowns

| # | Unknown | What settles it |
| :---: | :--- | :--- |
| U1 | Whether a k6 timeout closes the TCP connection, so that `r.Context()` is cancelled. T7 proves this for Go's own client. k6 is Go-based (PLAUSIBLE) | One k6 run with `timeout: 2s` against a gateway whose `rag.server` is a stub that sleeps. No Ollama is needed. Check that the record reads `ABANDONED` |
| U2 | Which 120 s clock fires first on an upstream hang (S1) | Reasoned. It could be read from records if F-H puts `t_generate_ms` on both buckets |
| U3 | Cell 3's follower | Reasoned from the error value, which was measured to be the same as cell 2's (Q1) |
| U4 | A client that half-closes its write side after sending is read as gone (net/http's background read sees EOF). Neither k6, curl, urllib nor `fetch` does this (PLAUSIBLE) | Record it as a limitation if any harness tool is found to half-close |
| U5 | Whether 1.6 or 7.x runs show any `ABANDONED` at all | The first run with a `RUN_ID` |

## Checked and found sound

- **The fix's shape.** It is one conjunct, read from this request's own context after `Do` returns, below `ErrShed` and above `case err != nil`. It adds no import, and `go vet` is clean. For a live client the switch behaves exactly as today. That was measured in every cell, not just argued.
- **The rest of the suite.** The whole existing `httpapi` suite passes on the fix under `-race`, including `TestAbandonedWhileQueuedIsNotAShed`. The rest of the module passes too, except `cache`'s cross-language contract test. That test reads `../../../contracts/normalize/cases.json`, which the scratch copy does not contain, so it is unrelated.
- **The new tests discriminate as the table says.** T1, T2 and T7 fail on HEAD and pass on the fix. T3, T4 and T5 pass on both. T6 does too once corrected. Every mutation is caught.
- **The queued `select` coin flip goes away.** An `Answer` on a dead context is `status Canceled` and now lands in `ABANDONED` (by reading, plus T2's path).
- **Principles.** The decision stays a Go rule. There is no model on the hit path, the query text is not read, and the hit path is untouched. No cut scope returns. No smaller design exists.
- **The S6 assumption holds today.** `main.go:244` sets no timeout and no `BaseContext`, and serves HTTP/1.1 only.

---

**Summary:** 0 blocking, 3 should-fix (S1–S3), 5 nits (N1–N5). The code change is approved as written.

**Most urgent:** S1. It is the "a metric's definition moves" case: client timeouts leave the error bucket for one the code describes as not the gateway's fault. Then S2, without which T6 cannot run.

## Resolutions (2026-10-05)

Every finding above is resolved. None is left open. The code change was approved as written, so the
fix in `design.md` §1 is unchanged; the corrections are to the tests, the comment and the records.

| # | Resolution | Where |
| :---: | :--- | :--- |
| S1 | **Fixed, record-only plus a comment.** The spec's rationale no longer says "clients that simply left": the two buckets answer different questions, and `ABANDONED` under a load generator is a **censored latency observation**, at least the client timeout, counted against S2 and never excluded. The 120 s / 120 s note is a recorded limitation. The comment at the case drops "not an error the gateway caused" for wording that holds under a load generator | `spec.md` (rationale, limitation 5, acceptance 9); `design.md` §1 and §7 F8; `plan.md` step 4 |
| S2 | **Fixed.** T6 is rebuilt as the review measured it: a follower in different raw text with the same normalised key, both `embedFresh`ed; `g.open()` after the leader returns; no leader assertion (T1 owns it). It passes on `HEAD`, on the fix and under a retrying F-D sketch | `design.md` §5; `spec.md` acceptance 5 |
| S3 | **Decided by default, open to reversal: option (a).** The spec's cut stands (F-H stays out of this task), and the experiment record and the F-L entry say that `ABANDONED` (minus F-D's followers) is only an **upper bound** on orphan exposure until F-H lands. **Option (b), F-H's widening before 1.6, is recommended as the next bugfix**; the author decides | `spec.md` (limitation 6, out of scope); `design.md` §7 F9; `approvals.md`; `plan.md` step 5 |
| N1 | **Fixed.** The ◆ distinction is dropped: all eight mutations pass the existing suite, and the measured table is the one `evidence/mutations.md` will use. M4b and M5b are added | `design.md` §6 |
| N2 | **Fixed.** T7's reading recipe is written down | `design.md` §5 |
| N3 | **Fixed.** T2 keeps `answerCalls() == 0`, with a comment naming the grpc-go behaviour and what to do if an upgrade breaks it | `design.md` §5 |
| N4 | **Fixed.** T5 is a D1 pin, not F-D-sensitive | `design.md` §5 |
| N5 | **Recorded forward**, not this fix: write-back on the client's context, in two writes, for F-J's trail and Phase 2's design | `spec.md` (out of scope); `design.md` §7 F10; `plan.md` step 5 |
| Q8 | **F-L gating revised.** The review recommends gating **Phase 7**, not item 1.6, because an orphan adds no memory (PLAUSIBLE); 1.6 reports the `ABANDONED` count. This corrects the earlier summary, which said F-L gates 1.6 | `spec.md` (out of scope); `plan.md` step 5 |

---

# Implementation review — `/ai-review`, 2026-10-05

**Reviewer:** `contract-reviewer` (sonnet), a general pass: the diff touches no contract surface, wire
field, `.proto` or Redis schema, so no specialised reviewer applied. It reviewed the working-tree diff
against `47da81e` (`handler.go`, one hunk) plus the untracked `abandon_test.go`, and checked the task's
prose against the code. It ran `go vet ./...`, `gofmt -l` and `go test -count=1 -race`, the seven new
tests 30 times each at `GOMAXPROCS` 1, 2 and 8, and four of the mutations on a scratch copy it then
removed. It edited no file; Claude recorded its report here.

**Verdict: the code conforms to the contract, `spec.md` and `design.md`. No contract or seam-field
finding and no code defect.** Three findings, all in the trail's prose, each of which could make an
analyst read a bucket wrongly with no failing check.

## Findings, most severe first

| # | Sev. | Finding | Check | Resolution |
| :---: | :---: | :--- | :---: | :--- |
| C1 | low | **"`ABANDONED` reconciles one-to-one with k6's status-0 count" is false** (`approvals.md`, `spec.md`, `design.md` F8, `plan.md`).<br>• `coalesce.go:44-47`: a follower waits on `<-c.done` and never watches its own context. A follower whose client left while waiting, behind a leader that then succeeds, returns `err == nil`: it is recorded `MISS`, `coalesced`, and written to a dead connection. The server saw the disconnect and still counts it as served.<br>• The reconcile sentence said a status 0 is `MISS` only "when the disconnect was not seen", and the residual list omitted this case.<br>• k6's status 0 also covers transport errors that leave no server record.<br>• Under Zipf redundancy with a saturated slot, waiting followers are the likely source of the gap | CONFIRMED (`coalesce.go:44-47` read; design cell 4 measured by the design review) | **Fixed.** "One-to-one" is replaced by **"`ABANDONED` is at most k6's status-0 count"** (excluding F-D's live followers, which are `ABANDONED` on the server and a `200` on the client). The waiting follower is added to the residual misattributions, and the reconciliation sentence now covers a `MISS` that is a follower and a request with no server record. `spec.md` limitation 9 (new); `approvals.md`; `design.md` F8; `plan.md` |
| C2 | low | **"`GENERATION_FAILED` is *the upstream returned an error*" overstates the bucket after the fix.**<br>• A live follower of a leader cancelled during `Answer` stays `GENERATION_FAILED` with a 502 whose body is *"rpc error: code = Canceled"* (measured in the design review). It inherits the leader's cancellation through `coalesce.Do`; the upstream did not fail.<br>• One departed leader now gives one `ABANDONED` and N `GENERATION_FAILED`, one per live follower.<br>• So `GENERATION_FAILED > 0` does not show an upstream fault until F-D lands. The residual list named only the queued-leader followers (the empty `200`) | CONFIRMED (`review.md` Q1, cell 2) | **Fixed.** The bucket's definition now reads *"the upstream returned an error while this request's client was still connected (or, until F-D lands, a coalesced follower inherited its leader's cancellation)"*. A new limitation records it as the mirror of the `GENERATION_FAILED ≈ 0` caveat: neither a zero nor a non-zero count isolates the upstream. `spec.md` limitation 8 (new); `approvals.md` |
| C3 | low | **"Left while queued, before `Answer` and during `Answer` all produce the same record" is overgeneral.**<br>• `handler.go:395-396` writes `rec.PermitWaitMS, rec.PermitQueue` inside the closure as soon as `Acquire` succeeds. On the slow path `Waited > 0` and `QueueDepth >= 1`.<br>• A request that queued, got the permit, then left during `Answer` is therefore `ABANDONED` with a **non-null** `t_permit_wait_ms` and a queue depth of at least 1: an orphan-candidate subset a record filter can already select.<br>• The "upper bound only" conclusion stands. None of the new tests uses a queue, so none would show this | CONFIRMED (`handler.go:395-396`, `pool.go:113-116` read; not probed) | **Fixed.** The statement is split into three cases: left while queued (null/0); fast path then left before or during `Answer` (also null/0, indistinguishable from each other); queued, admitted, then left (non-null, `permit_queue_depth >= 1`, filterable on the value and not on presence, since the field is a non-nullable `int`). A null `t_permit_wait_ms` rules out only the queued-and-left case. `ABANDONED` is still only an upper bound until F-H lands. `spec.md` limitation 6; `approvals.md`; `design.md` F9. No test is added: the finding concerns what the record shows, not how the request is classified |

## Checked and found clean (the reviewer's list, condensed)

- **The code against `spec.md` and `design.md`.**
  - One hunk at `handler.go:494-495`, with no import line touched.
  - The new condition sits after `ErrShed` (`:478`) and before `case err != nil` (`:515`).
  - The only `ctx.Err()` read in non-test code is `:495`, inside the switch, and none is in the `Do` closure (`:389-475`).
  - `ctx` is `r.Context()` at `:158` and is never reassigned. `/ask` is wired directly (`main.go:221`).
  - `main.go:244` sets no server timeout and no `BaseContext`, so the comment's assumption holds today.
- **Acceptance 7.** `git diff --stat -- '*_test.go'` is empty; only `handler.go` is modified and
  `abandon_test.go` and the trail are untracked.
- **The tests.**
  - `go vet`, `gofmt` and `go test -race` are clean; the seven new tests passed 30 times each at three `GOMAXPROCS`.
  - T1–T7 match `design.md` §5. T6 asserts nothing about the leader and no `502`, opens the gate after `leader.wait`, and `t.Fatalf`s if its fixture drifts. T7 does not use `hs.records`. T2 keeps `answerCalls() == 0` with the grpc-go comment; `stream.go:454-457` in v1.83.0 confirms the check.
  - Four mutations re-run (M1, M2, M3, M6) match `evidence/mutations.md`.
- **Contract.** No field or enum value changes: `ABANDONED` and `GENERATION_FAILED` already exist (`types.go:75-76`) as extensions outside §A and §H's `cache` enum, and `interfaces.md` promises nothing about a 502 or about abandonment. `Counters` cannot show the fix (`browse.go:85-86`). The k6 facts hold (`ask.js:124`, `:141`; `generate.py:15`).
- **Layering.** No import added to `handler.go`. The test file adds only `grpc/codes` and `grpc/status`, which `ask_test.go` already uses. No gRPC type leaked into non-test `httpapi`. `source_chunk_ids`, `t1_key` and `dataset_epoch` are untouched.
- **A note, not a finding.** The mixed-log marker (*logs are not comparable across this commit for the `ABANDONED` / `GENERATION_FAILED` split*) lives only in `approvals.md`. Nothing in §H or a manifest identifies the gateway revision. No run exists; P1's manifest should record the gateway SHA.

**Unresolved findings: none.**
