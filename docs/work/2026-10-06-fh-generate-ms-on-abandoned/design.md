# Design — fh-generate-ms-on-abandoned

**Revision 2**, after `review.md`. The fix itself (§1) is unchanged and was confirmed on every path. What
changed: the contract is now a **doc-only v0.12** (§2), two assertions that would pin a defect are
dropped, a nested-spans test T6 and a mutation F7 are added, T5 is hardened, and T3 is marked
admission-sensitive.

## 1. The fix: move one statement

```
Ask, miss path                                                        before        after
─────────────────────────────────────────────────────────────         ──────        ─────
var generateMS *float64                         (per-Ask local)
gen, err, shared := h.Generations.Do(key, func() {
    permit, err := h.Admission.Acquire(ctx)     ── ErrShed / ctx.Err() ─▶ return before genStart
    …
    genStart := time.Now()
    result, err := h.RAG.Answer(ctx, …)
    generateMS = msPtr(time.Since(genStart))    ◀── set on success AND on error
    if err != nil { return nil, err }
    …write-back…
})
                                                                    ┌─ rec.GenerateMS = generateMS     (NEW, here)
switch {                                                            │
  case ErrShed:      …return                    rec.GenerateMS nil  │  every outcome below inherits it
  case ABANDONED:    …return                    nil  ───────────▶   │  non-nil iff its own Answer was attempted
  case err != nil:   GENERATION_FAILED…return   nil  ───────────▶   │
}                                                                   └─
result := gen; … rec.GenerateMS = generateMS    (was HERE, success only)   ◀── DELETED
```

The assignment goes **immediately after `Do` returns and before the outcome switch**, and the old
assignment on the success path is **deleted**, so there is one site, not two. Every present and future
outcome case inherits it; none has to remember. SHED, a client that left while queued, and every
coalesced follower get nil with **no special case**, because their `generateMS` is never set.

### Why after `Do`, and not inside the closure

The closure already writes `rec.PermitWaitMS` and `rec.PermitQueue` onto the leader's record, so writing
`rec.GenerateMS` there would match precedent and delete the captured `generateMS` local. **Rejected:**
it changes the leader-panics path (`coalesce.go:64-67` re-panics; today that record carries no
`t_generate_ms`, and writing in the closure would give it one on a request that has no `cache` label)
for no gain, and it scatters the rule across the closure instead of keeping one line beside the switch
that classifies. After-`Do` keeps the panic path exactly as it is.

| Alternative | Rejected because |
| :--- | :--- |
| Copy inside each failure case | A new outcome case that forgets it reintroduces the bug silently |
| Write it inside the closure | Changes the panic path; scatters the rule (above) |
| Also move `rec.Coalesced = shared` above the switch | Same flaw, but a **second measurement change** (a new extension field on SHED/ABANDONED/GENERATION_FAILED records; a follower of a shed leader would read SHED plus `coalesced`). Not bundled; recorded next to F-D (`spec.md` open question 4) |
| A new field (`reached_server`) | A new §H field is a contract decision this bug does not need; `t_generate_ms` is enough |
| Move the closure's `generateMS` to a struct on `rec` | No gain; widens the diff |

## 2. Contract of the field after the change

For one `Ask`, `rec.GenerateMS` is **non-nil iff this request's own `Answer` call was attempted**:

| Outcome | `t_generate_ms` | Notes |
| :--- | :--- | :--- |
| TIER1_HIT, TIER2_HIT | null | no generation |
| SHED | null | `Acquire` returned `ErrShed` before `genStart` |
| ABANDONED, left while queued | null | `Acquire` returned `ctx.Err()` before `genStart` |
| ABANDONED, left after the permit | **non-null** | µs: the RPC never left; larger: it reached `rag.server`. **Censored** (F-L) |
| ABANDONED, a follower | null | its closure never ran. **Ambiguous with the queued row** (`coalesced` is absent on failure records) |
| GENERATION_FAILED, leader | **non-null** | the time until `Answer` returned its error |
| GENERATION_FAILED, a follower (F-D) | null | so a null here means a follower |
| MISS, leader | non-null | unchanged |
| MISS, a follower | null | unchanged |

**`interfaces.md` gets a doc-only v0.12** and a short **ADR-006** (`contract-draft.md`; review finding 1):
the example comment *"null unless generation ran"* can be read as forbidding the new values, the
selection rule an analyst needs must live where the field is defined, and the contract says any change
needs a `decisions.md` entry. No field, key, wire shape or frozen value changes. **For a record with a
non-empty `cache`** (a leader that panics after `Answer` is logged with `cache: ""` and no value, as
before).

## 3. Failure modes and edge cases

| Case | Result | Why it is safe |
| :--- | :--- | :--- |
| Leader panics in the closure | `cache: ""`, `t_generate_ms` null, as today | the copy is after `Do`, which re-panics before reaching it |
| Client left after Tier 1, permit free | ABANDONED, non-null, a few µs, `answerCalls()==0` | `Acquire`'s fast path ignores the context (`pool.go:93-97`) |
| Queued leader whose client leaves as a permit frees | may be admitted with a dead context: non-null µs, `permit_queue_depth >= 1` | F-A's `permit_queue_depth >= 1` orphan filter wrongly includes it; this field **plus the pre-registered threshold** excludes it (non-null alone includes it) |
| `0 < d < 1 µs` | written as `0`, **non-null** | readers filter `!= null`, never `> 0` |
| Exact zero `Duration` | null | cannot occur in practice |
| Race on `generateMS` | none | the closure runs on the leader's goroutine (`coalesce.go:72`); a follower never reads another request's local |
| Log writer | unaffected | `Record` shape unchanged, passed by value; no answer file on these paths |

## 4. Tests (one new file, `gateway/internal/httpapi/generatems_test.go`; no existing test is edited)

The header names the two stale comments (`ask_test.go:404`, `abandon_test.go:64-65`) it supersedes,
following F-A's precedent. **Every assertion on the value is a lower bound** (never an upper bound on
its own, which would make it timing-flaky), every hold is ≥ 25 ms so the bound means something, and
**no test asserts `t_permit_wait_ms`**: it is null on the fast path and after a queued-then-left, both
wrong under §H and both recorded findings, and pinning either would make the later fix an edit of an
immutable test.

| # | Test | Asserts |
| :-: | :--- | :--- |
| T1 | `TestAFailedGenerationRecordsHowLongItTook` | the `Answer` hook waits ≥ 25 ms then returns `codes.Internal`; the record is GENERATION_FAILED, `t_generate_ms` non-null and ≥ 25 |
| T2 | `TestClientLeavingDuringAnswerRecordsHowLongItWasHeld` | `Answer` held; the test sees `answerCalls()==1` (after `genStart`, by causality: the fake server's handler cannot run before it), waits ≥ 25 ms, cancels; ABANDONED; `t_generate_ms` ≥ **25** (the constant, not a nanosecond `held`) |
| T3 | `TestClientLeftBeforeTheRPCStillRecordsAnAttempt` | **ADMISSION-SENSITIVE** (it pins that `Acquire`'s fast path ignores the context, `pool.go:93-97`; a later `Acquire` that checks it flips this to null). The F-A T2 shape (`leavingStore`, `afterGet`): ABANDONED, `answerCalls()==0`, `t_generate_ms` **non-null**. Asserts nothing about its size or about `t_permit_wait_ms`; `t.Logf`s the value so `-count=N` under `-race` shows the never-sent tail |
| T4 | `TestClientLeavingWhileQueuedRecordsNoAttempt` | one permit held by a gated leader; a second request queues and its client leaves: ABANDONED, `t_generate_ms` **null**. Only that field |
| T5 | `TestAFailedLeaderRecordsAnAttemptButItsFollowerDoesNot` | **F-D-SENSITIVE.** Coalesced pair, distinct raw text and one key. `waitFor(Waiters(key)==1)` and `len(answerCalls())==1` **before** the leader fails (a follower that failed to coalesce would be SHED, also null); the leader fails with `codes.Internal` and a **live** client; the gate is in `hs.gates` and the hook honours `ctx`. The leader's value is non-null and ≥ the hold; the follower's is **null**. **Must not assert** the follower's `cache`, status, body or the absence of `coalesced` |
| T6 | `TestTheSpansNest` | `newHarness(t, 1, 1)`: B queues behind a gated A; the test waits for `Queued()==1`, sleeps ≥ 25 ms, replaces the hook with a failing one via `onAnswer` (A's call already captured its own) and opens A's gate: A is a MISS, B GENERATION_FAILED. For B: `t_permit_wait_ms + t_generate_ms ≤ t_total_ms` **in integer µs**. Nested and disjoint spans, and µs truncation preserves ≤, so it cannot be timing-flaky |
| T7 | `TestAMissGenerationTimeExcludesItsWriteBack` | **a declared guard, green on correct code** (implementation review): the Tier-1 write-back is held 100 ms via `slowPutStore`; `t_total_ms − t_generate_ms ≥ 99` ms. A lower bound on the difference |
| T8 | `TestACoalescedMissFollowerCarriesNoGenerationTime` | **a declared guard, green on correct code**: a coalesced MISS pair; the follower (identified by `coalesced`, present on a served MISS follower) has `t_generate_ms` null, the leader non-null |
| — | existing `ask_test.go:95,465` (MISS non-null), `:356` (SHED null), `:62` (hit null) | unchanged, and they must still pass |

**Mutations**, each applied to a copy of `gateway/` and each expected to be caught by a named new test,
as in 1.2/1.3/F-A/1.5:

| # | Mutation | Caught by |
| :-: | :--- | :--- |
| F1 | revert the fix (copy only on success) | T1, T2, T3, T5, T6 |
| F2 | copy only for GENERATION_FAILED | T2, T3 |
| F3 | copy only for ABANDONED | T1, T5, T6 |
| F4 | assign a constant non-nil value before the switch (followers, queued and SHED carry it) | T4, T5 (and the existing `ask_test.go:356`) |
| F5 | copy only inside the success branch of the closure | T1, T2, T3 |
| F6 | `rec.GenerateMS = msPtr(time.Since(start))` (total request time, not the generation's) | T6 |
| F7 | `genStart` moved above `Acquire` (MISS and failure values include permit wait) | T6 |
| F8 | the MISS span runs to the **end** of the closure (it includes write-back) | T7 |
| F9 | a coalesced MISS follower is given a generation time (a copied or shared span) | T8 |

## 5. Unknowns that still need verifying

1. ~~Does `answerCalls()==1` happen after `genStart`?~~ **Settled by causality** (review 8): the fake
   server's handler cannot run before the gateway's `genStart`. Not something a test can confirm.
2. **T3's non-null** depends on `Acquire`'s fast path ignoring the context: read from `pool.go:93-97` and
   pinned by F-A's T2; this test adds the field and is declared ADMISSION-SENSITIVE.
3. ~~T4's `t_permit_wait_ms`~~ **Settled** (review 2): not asserted by any test.
4. ~~F6~~ **Caught by T6** (review 3), and F7 with it.
5. **The 1 ms threshold and its [1 ms, 100 ms] gap check** (`spec.md` open question 3): pre-registered
   in the experiment record; **the author's number**. Whether the never-sent tail stays under it is
   *not known*: T3's `t.Logf` under `-race` gives a first reading, the first `RUN_ID` the real one.
6. **Two pre-existing findings** are recorded, not fixed: `t_permit_wait_ms` null on every fast-path
   request, and on a request that queued then left.
7. **T6's `Queued()==1` wait and the 25 ms sleep** are the only timing in the file. The sleep is a floor
   that makes F6/F7 visible (the assertion is an inequality and cannot flake high); the `waitFor` is the
   harness's 5 s-bounded poll.
