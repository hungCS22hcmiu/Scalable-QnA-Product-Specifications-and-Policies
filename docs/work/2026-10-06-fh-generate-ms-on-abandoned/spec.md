# Spec — fh-generate-ms-on-abandoned

**Scope:** L · **Opened:** 2026-10-06 · **Opener:** `/bugfix`, raised to L (the field is in the
evaluation log, which is the measurement channel) · **Phase:** 1, a prerequisite of item **1.6**
**Revision 3**, after `review.md` (finding numbers in brackets). Rev 2 applied `impact.md`'s nine
corrections; rev 3 makes the contract phase required (a doc-only v0.12) and drops two assertions that
would pin a defect.

## The change in one sentence

A request whose **own** `Answer` call was attempted and did not succeed, recorded `ABANDONED` or
`GENERATION_FAILED`, now carries `t_generate_ms` (how long its own attempt took) in the evaluation
log, instead of null.

## The bug, and its cause

**Cause, one sentence.** `Ask` copies `generateMS` into `rec.GenerateMS` only on the success path,
after the outcome switch (`handler.go:523`), although the `Generations.Do` closure sets it even when
`Answer` fails (`:401`, before the `if err != nil`), so the `ABANDONED` and `GENERATION_FAILED` cases
`return` with the field still null.

Read from the code, not only from the F-H note:
- `generateMS` is a per-`Ask` local, written by the closure and read after `Do` returns. `Do` runs
  the closure on the **caller's goroutine** (`coalesce.go:72`), so there is no race, and a coalesced
  **follower never runs the closure**: its own `generateMS` stays nil by construction.
- `Acquire`'s fast path takes a free permit **without looking at the context** (`pool.go:93-97`), so
  a client that has already left still reaches `Answer`, which fails at once.
- `SHED` and a client that left **while queued** return from `Acquire` before `genStart` is taken
  (`:396`), so `generateMS` is nil on them. They stay null, correctly.

## What it serves

- **Phase 1, a prerequisite of item 1.6** (`super-plan.md`, F-H, *widened to `ABANDONED`* by the F-A
  close): *"Recommended as the next bugfix, before item 1.6 reports its `ABANDONED` count."*
- **Two questions that are unanswerable today, both about a request that did not succeed.**
  1. *Did the abandoned request's own `Answer` get attempted?* F-A's experiment record could only say
     that a filter on `permit_queue_depth >= 1` selects "queued, got the permit, then left", and that
     the rest (took `Acquire`'s fast path and left before or during `Answer`) **cannot be told
     apart**. A non-null `t_generate_ms` separates them, so the **upper bound on orphaned
     generations (F-L)** becomes a tighter bound instead of a filter with a blind spot.
  2. *How long did a failed generation take?* The original F-H. The duration separates an **immediate
     failure (ms) from a long one (s)** and nothing finer [review 10]: under k6 an upstream hang already
     lands in `ABANDONED`, so the **label** separates a hang from a crash, while the **duration** cannot
     separate a hang from a slow generation (both read ≈ 120 s minus the time before `Answer`).

## The reading rule (to be stated, not only implemented)

> **For a record with a non-empty `cache`, `t_generate_ms` is non-null if and only if this request's
> own `Answer` call was attempted**, whether it succeeded or not. It is null for TIER1_HIT and
> TIER2_HIT; for `SHED`; for a request that left or failed **before** it held a permit; and for **every
> coalesced follower** (it never ran the closure). *(The qualifier is the panic path [review 7]: a
> leader that panics after `Answer` is logged with `cache: ""` and no value, as before.)*

What the value means on each path:
- **MISS (success):** unchanged, the time `Answer` took.
- **GENERATION_FAILED (leader):** the time until `Answer` returned its error. A few ms is an
  immediate failure; ≈ 120 s is the `httpx` generate timeout.
- **ABANDONED:** the time until `Answer` returned the cancellation. It is a **censored** observation:
  it is at most the generation's true duration, because `rag.server` **keeps generating after the RPC
  is cancelled** (F-L, `impact.md` of F-A). A few µs means the RPC never left (the client had
  already gone, fast path); a larger value means it reached `rag.server`.
- **A coalesced follower, any outcome:** null. **The converse on `GENERATION_FAILED`:** every
  GENERATION_FAILED *leader* reached `Answer` (`Acquire` returns only `ErrShed` or `ctx.Err()`), so a
  **null on a `GENERATION_FAILED` record means a follower** of an upstream-failed leader (correct
  singleflight behaviour; **F-D is the leader-*cancellation* case**, not this one). **A null on an
  `ABANDONED` record is ambiguous**: a leader that left while queued, or a follower, since
  `rec.Coalesced` is set only on the success path and no failure record carries `coalesced`.
- **Selection rule, per statistic** [review 6]. Until this commit `t_generate_ms != null` meant
  `cache == MISS ∧ ¬coalesced`. It no longer does.
  - **Service-time and μ_gen** statistics select `cache == "MISS" ∧ t_generate_ms != null`, **never "the
    field is present" alone** (a MISS follower's value is null and a leader's is not; `coalesced` is an
    undefined extension, absent on leaders, so it is not the predicate), or they take in censored ABANDONED
    durations and failed-call durations. **While F-L
    is open that is necessary but not sufficient**: a MISS that follows an orphaned generation absorbs
    the remainder (`super-plan.md`, F-L).
  - **Permit-occupancy / utilisation** statistics (item 7.5) **may select on presence**: every `Answer`
    attempt held the permit, and abandoned holds of up to ≈ 120 s were invisible before.
  - Readers filter on `!= null`, never `> 0` (see the µs limitation).

## Acceptance — each a check that can be run

1. **`GENERATION_FAILED`, leader, live client:** `t_generate_ms` is non-null and **at least** the delay
   injected before the failure (≥ 20 ms, so the bound means something). A lower bound only: an upper
   bound would make the test timing-flaky.
2. **`ABANDONED`, client leaves during `Answer`:** non-null, and at least the time the test held
   `Answer`, **measured from the moment it sees `answerCalls() == 1`** (which is after `genStart`) to
   `cancel()`; held ≥ 20 ms.
3. **`ABANDONED`, client left before the RPC** (it left after Tier 1 and took the fast path):
   non-null. `answerCalls()` is still 0, which is what "the RPC never left" means. **Asserts nothing
   about the value's size or about `t_permit_wait_ms`**; it `t.Logf`s the value so `-count=N` under
   `-race` can show the never-sent tail [review 5]; declared **ADMISSION-SENSITIVE** (a later `Acquire`
   that checks the context would make it null) [review 8].
4. **`ABANDONED` while queued:** `t_generate_ms` **null**: its own `Answer` was never attempted. A pin,
   against copying a stale value into the case. **It asserts only `t_generate_ms`** [review 2]: its
   `t_permit_wait_ms` is null too, but that is wrong under §H (a permit was requested and waited for) and
   is a recorded finding, so pinning it would turn the later fix into an edit of an immutable test.
5. **`SHED`:** null (the existing test already pins it).
6. **Coalesced pair, the leader's `Answer` fails:** the leader's record is non-null, the follower's is
   **null**. The follower is told apart **by distinct raw text that normalises to the same key**
   (`abandon_test.go:221-225`), **not** by `coalesced: true`. Required so it cannot pass vacuously
   [review 4]: wait for `Waiters(key) == 1` and `len(answerCalls()) == 1` **before** the leader fails (a
   follower that failed to coalesce would be SHED, also null); the leader fails with an **upstream**
   status (`codes.Internal`) and a **live client** (a cancellation is F-D's case); the gate is in
   `hs.gates` and the hook honours `ctx`. **Must not assert** the follower's `cache`, status, body or
   the absence of `coalesced`. Declared **F-D-SENSITIVE**: an F-D fix that re-elects followers on an
   upstream failure would legitimately make the follower's value non-null.
6b. **The spans nest** [review 3]: a request B queues behind a gated A (`newHarness(t, 1, 1)`); the test
   waits for `Queued()==1`, sleeps ≥ 25 ms, replaces the hook with a failing one (`onAnswer`; A's call
   has already captured its own) and opens A's gate, so A is a MISS and B a GENERATION_FAILED. For B,
   **`t_permit_wait_ms + t_generate_ms ≤ t_total_ms` in integer µs**. The three spans are nested and
   disjoint and µs truncation preserves ≤, so it cannot be timing-flaky; it fails if the generation span
   starts at `Ask`'s beginning (F6) or above `Acquire` (F7).
6c. **A coalesced MISS follower carries no generation time** [implementation review]: a leader's value is
   non-null and the follower's is null. The v0.12 selection rule (`cache == "MISS" ∧ t_generate_ms != null`)
   selects exactly the leaders only because of this.
6d. **A MISS's value excludes write-back** [implementation review]: with the Tier-1 write-back held 100 ms,
   `t_total_ms − t_generate_ms` is at least that. §H says the value is *"the time `Answer` took, before
   write-back"*, and a span running to the end of the closure would inflate mu_gen by the cache's round trips.
7. **MISS unchanged:** every existing test passes with no edit. **No existing test is edited:** every
   new assertion is in a **new test file**, because adding them to `TestAbandonedWhileQueuedIsNotAShed`
   or `TestGenerationFailureIsNotServedOrCached` would edit immutable tests. The two comments that
   say "not asserted (F-H)" become stale and stay, named in the new file's header (F-A's precedent).
8. **The contract: a doc-only v0.12 and ADR-006** [review 1] (drafted in `contract-draft.md`; **default
   yes, the author confirms at `/approve contract`**). `git diff --exit-code contracts/` stays clean (the
   `.proto`); the diff under `docs/contracts/` is exactly the five hunks of the draft. Checked by grep:
   `grep -n 'Current version.*v0.12' docs/contracts/interfaces.md`; the example comment
   `grep -n '// null unless this request' docs/contracts/interfaces.md`; `grep -n 'ADR-006'
   docs/decisions.md`; and `grep -n 'null unless generation ran' docs/contracts/interfaces.md` finds
   nothing.
9. `make verify` exit 0; `go test -race` on `httpapi` once, recorded.

## Not in this task

- **F-L** (`rag.server` keeps generating after cancel) and **F-D** (a follower inherits its leader's
  cancellation). Both stay open and both are named in the reading rule.
- **A new field** (a `reached_server` flag, an RPC-sent timestamp). `t_generate_ms` is enough, and a
  new §H field is a contract decision this bug does not need.
- **What `t_generate_ms` measures on a success.** It stays the time `Answer` took, before write-back.
- Changing how `ABANDONED` or `GENERATION_FAILED` is decided (F-A, done).
- Item 1.6 itself, or editing its README.

## Open questions

1. **Does §H already say this?** *Not unambiguously* [review 1]. The field note (*"null where the stage did
   not run"*) is normative and arguably covers it, but the example comment (*"null unless generation
   ran"*) can be read as forbidding a value on a request that made no RPC, the `:590` sentence about an
   errored stage is `t_search_ms`'s and not a general rule, and the selection rule an analyst needs would
   otherwise live in a closed trail. **Default: a doc-only v0.12 plus ADR-006, which makes the contract
   phase required.** The author may decline; then `§H` stays and the rule lives in `super-plan.md` alone.
2. ✅ **The stale reading guidance.** `super-plan.md` is edited in place, **including the pointer at
   `:165-166` that sends readers to F-A's `approvals.md`** (which says "null on all of them"), now
   pointing to this record and to §H v0.12. **One** dated "superseded" note is appended to F-A's
   `approvals.md` [review 9]; the closed spec/plan/design/review files are not touched (dated trails are
   historical, and ~20 appended lines would be churn).
3. **The threshold for "the RPC never left".** "A few µs" is an order of magnitude, not a field: a
   cancel that races the stream setup can land between. If an analysis wants to split ABANDONED into
   *never reached `rag.server`* and *reached it*, it needs a threshold, and that threshold must be
   **fixed before anyone looks at the ABANDONED distribution** (the never-tune rule). **Recorded default:
   1 ms, pre-registered together with a check** [review 5]: the **count of ABANDONED values in
   [1 ms, 100 ms] is reported beside the split, and the split is called unresolved if that count is not
   negligible.** The *gap* defends the split, not the number: µs for an RPC that never left against
   seconds for one cancelled during a real generation. The failure mode is a never-sent tail above 1 ms
   (under `-race`, GC pauses, co-hosted CPU contention, a cancel during a lazy connect). **The number is
   the author's to confirm or replace**, and it belongs in P1's manifest.
4. **`rec.Coalesced = shared` has the same flaw** (assigned only on the success path). Moving it above
   the switch would make follower failures identifiable and resolve the ambiguous ABANDONED null, but it
   is a **second measurement change** (an extension field appears on SHED/ABANDONED/GENERATION_FAILED
   records; a follower of a shed leader would read SHED plus `coalesced`). **Default: not bundled;
   recorded as a finding next to F-D.**

## Limitations to record

- `msPtr` returns nil only for an exact zero `Duration`, but `durMS` truncates to whole microseconds, so
  `0 < d < 1 µs` is written as **`0`, a non-null value**. Filter on `!= null`, never `> 0`. An exact zero
  cannot occur in practice: a gRPC call spans many ticks of the ~42 ns clock.
- **`t_permit_wait_ms` is also null on a request that queued and then left** [review 2]: the closure
  returns before it is set, though a permit was requested and waited for. A second pre-existing finding,
  recorded with the next one.
- **`t_permit_wait_ms` is null on every fast-path request** (`Acquire` returns `&Permit{pool: p}` with
  `Waited == 0` and `msPtr(0)` is nil), which contradicts §H's *"null unless a permit was requested"*.
  Pre-existing, not caused or fixed here; recorded as a finding. It does not change F-A's guidance (only
  a request that **queued** has it non-null).
- `ABANDONED`'s value is **censored**, not the generation's duration, and says nothing about whether
  `rag.server` finished (F-L).
- Logs written before this commit have null on these records. Every other field is comparable; the
  `ABANDONED` / `GENERATION_FAILED` records' `t_generate_ms` is not.
