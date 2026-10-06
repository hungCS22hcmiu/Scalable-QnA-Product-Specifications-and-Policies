# Plan — fa-abandonment-classification

The smallest change that satisfies `spec.md` rev 3, ordered so that each step can be checked on its
own. It follows `design.md` rev 3, after `impact.md` and `review.md`. **One production file changes**
(`gateway/internal/httpapi/handler.go`, one condition and a comment) and **one test file is added**.

## 0. Before any edit

- [x] `review.md` folded into `design.md` rev 3 and `spec.md` rev 3.
- [x] The author ran `/approve impact` · `/approve experiment` · `/approve implementation`, all
      2026-10-05. The experiment phase is **record-only** (`impact.md` §7). The contract phase is
      recorded as not required in `approvals.md`.
- [x] **Baseline on `HEAD` (`47da81e`).** `make verify` exit 0, and
      `cd gateway && go test -count=1 ./...` green, uncached.

## 1. Tests first: each must fail on `HEAD` for the stated reason, or be marked as a pin

- [x] **`gateway/internal/httpapi/abandon_test.go`**, a new file, with the `leavingStore` wrapper
      (`design.md` §5) and T1–T7. Expected on `HEAD`, as measured by `review.md`:

      | Test | On `HEAD` | Why |
      | :--- | :--- | :--- |
      | T1 leaves during `Answer` | **fails** | `GENERATION_FAILED`, a 502 written |
      | T2 leaves after Tier 1 | **fails** | the same, from `Acquire`'s fast path |
      | T3 upstream `CANCELED` / `DEADLINE_EXCEEDED`, live client | **passes, a pin** | the status is not the client leaving |
      | T4 a dead client against a full pool | **passes, a pin** | `ErrShed` is first |
      | T5 a completed generation is not reclassified | **passes, a pin** | `err == nil` is a `MISS`; also confirms U6 |
      | T6 a live follower beside a leaving leader | **passes, a pin** | the follower's 502 is written |
      | T7 a real disconnect | **fails** | the same as T1, over a real connection |

      Any other result stops the plan: a test that passes on `HEAD` when it should fail is vacuous,
      and one that fails when it should pass is wrong.
      **Result on `HEAD`: exactly as the table says.** T1 and T2 fail on `GENERATION_FAILED` with a
      502 body *"rpc error: code = Canceled desc = context canceled"* written; T7 fails on
      `GENERATION_FAILED`; T3–T6 pass.
- [x] `go vet ./internal/httpapi/` is clean, and `go test -count=1 -race` on the new file shows
      exactly T1, T2 and T7 red.
- [x] `git diff --stat` shows **no change to any existing file**: only `abandon_test.go` is new.

## 2. The edit

- [x] **`handler.go`**: add `err != nil && ctx.Err() != nil` to the `ABANDONED` case (or as its own
      case), **below** `ErrShed` and **above** `case err != nil`, reading the request's own `ctx` in
      the switch. Replace the comment at `:495-496` with `design.md` §1's. No import is added.
      **Done when** T1, T2 and T7 pass and the whole existing suite still passes under `-race`.
      **Done:** all seven new tests pass and the existing suite passes under `-race`.

## 3. Check

- [x] `cd gateway && go test -count=1 ./...`, and `-race` for `./internal/httpapi/`: all green.
- [x] The new tests, `-count=100` at `GOMAXPROCS` 1, 2 and 8 under `-race`: stable (the review ran
      300). **All three pass** (5.8 to 6.7 s each).
- [x] **Acceptance 7:** `git diff --stat -- '*_test.go'` is empty; the only added test file is
      untracked `abandon_test.go`. `git diff --stat` among sources shows `handler.go` and nothing else.
      **Confirmed.**
- [x] **Placement, by grep:** `grep -n 'ctx.Err()' gateway/internal/httpapi/handler.go` shows the new
      read **inside the switch** and not inside the `Generations.Do` closure, and the case below
      `ErrShed`. **Confirmed:** the only `ctx.Err()` read in `handler.go` is line 495, inside the
      switch, after `ErrShed` (478) and before `case err != nil` (515); the closure ends before 478.
- [x] **Mutations** M1–M6, plus the variants M4b and M5b (`design.md` §6). Apply each to a scratch
      copy, run the named tests, record red. Results go to `evidence/mutations.md`. All eight pass
      the existing suite, so a green existing suite proves nothing here.
      **All eight caught, exactly as the review measured** (M1: T1, T2, T7; M2: T3, T6; M3: T5; M4,
      M4b, M5: T6; M5b: T3, T6; M6: T4), none by a build error, and **all eight pass the existing
      suite**. `evidence/mutations.md`.
- [x] `make verify` green (exit 0), proto drift none, nothing skipped.

## 4. The experiment record (the approved phase)

- [x] In `approvals.md`, **record-only**, nothing re-measured (`impact.md` §7, `review.md` S1 and S3):
  - **The precedence (D1):** `SHED` > this request's client gone ⇒ `ABANDONED` > `GENERATION_FAILED`;
    `err == nil` ⇒ `MISS` always.
  - **`ABANDONED` under a load generator is a censored latency observation**, at least the client
    timeout. It counts against S2 and goodput and is at most k6's status-0 count (`spec.md` limitation 9). It
    is never excluded as client behaviour. Not comparable across the commit.
  - **The 120 s / 120 s note:** an upstream hang mostly lands in `ABANDONED`, so
    `GENERATION_FAILED ≈ 0` does not show it never hung.
  - **The residual misattributions:** a disconnect the server cannot see (trailing bytes, an
    unterminated chunked body) → `MISS`; a leave at completion → `MISS`, or `ABANDONED` with
    `t_generate_ms` null; F-D's live followers → `ABANDONED`; a genuine upstream failure for a gone
    client → `ABANDONED`.
  - **`ABANDONED` is only an upper bound on orphan exposure** (F-L) until F-H lands.

## 5. Review and close

- [x] `/ai-review` (`contract-reviewer`, a general pass: no contract surface moves). The code
      conforms; three prose findings (C1–C3) were fixed (`review.md`).
- [x] `/done` (2026-10-05). It records:
  - `super-plan.md:158-160`: **F-A resolved**, with the date and this trail;
  - **F-L**, a new finding, with the review's recommendation to gate **Phase 7 (7.1, 7.5)** on it and
    to have **item 1.6 report the `ABANDONED` count**, and the note that F-L can be closed by
    measurement if abandonment during `Answer` is shown to be about zero;
  - **F-H widened to `ABANDONED`**, recommended as the next bugfix, before 1.6 reports its count;
  - **F-J / Phase 2:** the write-back on the client's context, in two writes (`review.md` N5);
  - **for item 1.6:** U7, whether a k6 timeout closes the connection, settled by the first run with
    a `RUN_ID`;
  - **the stale comment** at `ask_test.go:369-370`, recorded and not edited, as 1.3 did;
  - whether scope L was honest.

## Outcome (2026-10-05, `/done`)

**`/verify` before closing** (`make verify` exit 0, plus proto drift run separately). **Nothing is
SKIPPED:**

| Target | Result |
| :--- | :--- |
| gofmt | **PASS** |
| go vet | **PASS** |
| go build | **PASS** |
| go test | **PASS** (also `-race` on `./internal/httpapi/`) |
| ruff | **PASS** |
| pytest `rag/` | **PASS** (15) |
| pytest `experiments/` | **PASS** (94) |
| proto drift | **PASS** (`make proto`, no diff on either stub) |

**Shipped:**
- **The fix:** one condition, `err != nil && ctx.Err() != nil`, in the outcome switch of
  `gateway/internal/httpapi/handler.go`, below `ErrShed` and above `case err != nil`, read from the
  request's own context after `Do` returns. A client that leaves while its request is being served is
  recorded `ABANDONED` with nothing written, instead of `GENERATION_FAILED` and a 502 to a dead
  connection. A new comment names the assumption that only the client cancels the request context.
- **Tests:** `abandon_test.go`, seven tests (T1–T7) on a `leavingStore` wrapper. T1, T2 and T7 failed
  on `HEAD` for the stated reason; T3–T6 passed as pins. No existing test file changed.
- **Evidence:** `evidence/mutations.md`. All eight mutations (M1–M6, M4b, M5b) are caught by the new
  tests, none by a build error, and **every one passes the existing suite**.
- **Records:** the experiment record in `approvals.md` (the precedence D1, a before-and-after table,
  how to read `ABANDONED`, the residual misattributions, the client/server reconciliation);
  `super-plan.md` (F-A resolved, F-L, F-H widened, the F-J write-back note, notes for 1.6).

**The scope was honest: L.** The change sits on the measured path (the outcome label feeds §H and
`Counters`) and it touched no frozen value, no contract, no `reuse/` and no seam. No phase was
skipped: spec → impact → design → opus design-review → plan, with impact, experiment (record-only)
and implementation approved and contract recorded as not required. The heavy process bought three
things: the design review caught that rev 2's T6 failed on every version and constrained F-D; the
impact analysis found F-L and that acceptance 2 as written tested a path only `fakeStore` has; and
the implementation review caught three overstated sentences in the experiment record.

**Frozen value / contract.** Neither changed, so `interfaces.md` was **not** version-bumped, and no
ADR was written. `approvals.md` names the invalidation: **no `run_id`, because no run exists.** A log
written after this commit is not comparable with an earlier one for the `ABANDONED` /
`GENERATION_FAILED` split; every other field is comparable.

**Phase 1 exit criterion, run literally.** `go test ./internal/httpapi/` passes, and the grep for
`TauHigh`, `REUSE_TAU_HIGH` and `similarity_only` in non-test code finds only the startup guard and a
history comment. `make env-check` and `make seam-check` were **not re-run**: both load models and
memory pressure read 2 (urgent), so a run would be invalid (`CLAUDE.md`). Their last results stand
(1.1 and 1.4's evidence). **The phase is still open**, as before: 4 of 6 clauses, with item 1.5
(answers recoverable from `raw/`) and item 1.6 (the load generator's footprint and ADR-001) unmet.
This task was a prerequisite of 1.6, not an exit clause, so the progress line is unchanged.

**Deferred, each worth a task when its time comes:**
1. **F-H, widened to `ABANDONED`.** Recommended **next, before 1.6 reports its `ABANDONED` count**: it
   is what separates the orphan-candidate subset. The author decides.
2. **F-L.** Gates Phase 7 (7.1, 7.5), not 1.6, by the review's reading (PLAUSIBLE). Fix it, or show
   abandonment during `Answer` is about zero. The author decides whether before 1.6.
3. **F-D** (a coalesced follower inherits the leader's cancellation). Its live followers are still
   `ABANDONED` with an empty `200`, or `GENERATION_FAILED` with a 502. T6 constrains no F-D design.
4. **F-J / Phase 2:** write-back on the client's context, in two writes; and the mixed-log marker
   (P1's manifest should record the gateway SHA).
5. **For 1.6:** whether a k6 timeout closes the connection (proven only for Go's own client, T7).
6. **`ask_test.go:369-370`** (*"a cancellation that reaches a gRPC call is logged GENERATION_FAILED
   today (F-A)"*) is now false. It is left as it was, as 1.3 left its own stale comments, so that
   `git diff` on `ask_test.go` stays an audit (acceptance 7).
7. **The §H `cache` enum sync** waits for F-B and is not this task's.

