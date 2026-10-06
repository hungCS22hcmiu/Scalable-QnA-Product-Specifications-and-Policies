# Design review — fh-generate-ms-on-abandoned

**Reviewer:** `design-reviewer` subagent (opus), against `spec.md` rev 2, `impact.md`, `design.md` rev 1
and the code. **Verdict: the code change is sound** (moving `rec.GenerateMS = generateMS` to just after
`Do` is correct on every path it traced). **The risks are around it:** the contract decision, two
assertions that would pin a known defect, and one mutation no test catches. Approve once findings 1 and
2 are fixed.

**Path trace it confirms:** `generateMS` is non-nil exactly when this request's own `Answer` returned.
SHED and a client that left while queued return before `genStart`: null. A fast-path-then-left request,
and a queued request admitted with a dead context by the random `select` (`pool.go:110-115`): a few µs.
A GENERATION_FAILED leader and a MISS whose client left after `Answer` succeeded: non-null. A follower is
null on every outcome (the follower branch never calls `fn`). **No aliasing:** each `Ask` has its own
local and its own closure; `msPtr` allocates a fresh float; the record goes to `Log` by value. **No
existing test breaks.**

Its factual claims were checked against the code by tracing (the harness helpers, `Acquire`, the
closure); the two I re-read before acting are the example comments at `interfaces.md:551-552` and the
fact that the queued-then-left leader returns before `rec.PermitWaitMS` is set.

## Findings and resolutions

| # | Tag | Finding | Resolution |
| :-: | :---: | :--- | :--- |
| 1 | MUST | **Leaving `interfaces.md` untouched is not honest.** After the fix the code writes a non-null value where a literal reading of the example comment (`:552` *"null unless generation ran"*) forbids one: on the dead-context fast path the server sees 0 RPCs, so no generation ran. The "sibling sentence" `impact.md` cites (`:590`, *"errored still carries its span"*) is the v0.10 note on `t_search_ms`, not a general `t_*_ms` rule. **And the analysis was inconsistent:** `impact.md` §6e treats the comment at `:551` as normative to call the fast-path `t_permit_wait_ms` null a defect, while §1 treats the comment at `:552` as non-normative to avoid a version bump. The concrete failure: a Phase 7 analyst reads `:552` and selects MISS service times by `t_generate_ms != null`, taking in ABANDONED values censored near 120 s and biasing μ_gen. The guard (the selection rule) would otherwise live only in a trail's `approvals.md` and a `super-plan.md` finding that gets closed. Precedent: v0.6 and v0.10 bumped for "restates / changes meaning" with no wire change | **Adopted as the default; the author confirms at `/approve contract`.** A **doc-only v0.12**: the `:552` comment is rewritten, a `t_generate_ms` row is added to the field notes (censored on ABANDONED, null on followers, the per-statistic selection rule, not comparable across the commit for ABANDONED/GENERATION_FAILED), a Versioning row, and a short **ADR-006** (the contract says *"any change requires a new entry in `decisions.md`"*). No `.proto`, no wire change. `impact.md` §1 and `spec.md` acceptance 8 are corrected: **the contract phase is now required.** Drafted in `contract-draft.md`. If the author declines, the plan drops that step and the selection rule lives in `super-plan.md` alone |
| 2 | MUST | **Two assertions would pin a known defect.** `design.md` T3 asserts `t_permit_wait_ms` null on the fast path, the very contradiction `impact.md` §6e records against `:551`. `spec.md` acceptance 4 asserts `t_permit_wait_ms` null for a request that **queued and then left**: a permit was requested and waited for, so null is wrong under either reading of §H. That one is **a new finding**, not recorded anywhere (F-A's `approvals.md:61` states it as plain fact). Either would turn a later fix into an edit of an immutable test | **Adopted.** Both assertions are dropped; **the tests assert only `t_generate_ms`** (design unknown 3's default made binding). The queued-then-left `t_permit_wait_ms` null is recorded as a new finding beside §6e |
| 3 | SHOULD | **F6 is catchable, and a related mutation that changes what MISS measures goes uncaught.** Lower bounds catch neither F6 (the span from `Ask`'s start) nor a new **F7**: `genStart` moved above `Acquire`, which silently makes MISS `t_generate_ms` include permit wait and shifts μ_gen | **Adopted.** A new test **T6**: request B queues behind a gated A; the test waits for `Queued()==1`, sleeps ≥ 25 ms, switches the hook to a failing one with `onAnswer` (A's call has already captured its hook, so A stays a MISS and B ends GENERATION_FAILED), opens A's gate, and asserts `t_permit_wait_ms + t_generate_ms ≤ t_total_ms` **in integer µs**. The three spans are nested and disjoint and µs truncation preserves ≤, so it cannot be timing-flaky; under F6 or F7 the sum exceeds the total by ~25 ms. F7 added to the list |
| 4 | SHOULD | **T5 can pass vacuously, or pin F-D.** At `pool(1,0)` a follower that failed to coalesce would be SHED, also null, so T5 would pass for the wrong reason | **Adopted.** `waitFor(Waiters(key)==1)` and `len(answerCalls())==1` before the leader fails; the leader's failure is an **upstream** status (`codes.Internal`) with its client live (a cancellation is F-D's case, and an F-D fix that re-elects the follower would legitimately make its value non-null); the gate is registered in `hs.gates` and the hook honours `ctx`; the leader's value is a lower bound. **Must not assert** the follower's `cache`, status, body, or the absence of `coalesced`. T5 is declared **F-D-SENSITIVE**. Wording fixed: a follower of an upstream-failed leader is correct singleflight behaviour, not F-D |
| 5 | SHOULD | **The 1 ms threshold rests on reasoning, not measurement.** What defends the split is the gap (µs for an RPC that never left, against seconds for one cancelled during a real generation under k6's 120 s), not the number. Failure mode: the never-sent tail exceeds 1 ms under `-race`, GC pauses, co-hosted CPU contention, or a cancel during lazy connect, and a never-sent call reads as one that reached `rag.server`, with nothing to flag it. Also `design.md`'s "this field excludes it" (the `select`-race admission) is true only once the threshold is applied | **Adopted.** 1 ms is pre-registered **together with a check**: the count of ABANDONED values in [1 ms, 100 ms] is reported beside the split, and the split is called unresolved if that count is not negligible. T3 `t.Logf`s its value so `-count=N` under `-race` can show the never-sent tail. The `design.md` sentence is qualified. The threshold remains **the author's to confirm** |
| 6 | SHOULD | **"Never select on presence" is too blunt, and not sufficient.** For permit occupancy or utilisation (item 7.5), presence is the right selector: every `Answer` attempt held the permit, and abandoned holds of up to ~120 s were invisible before. For μ_gen, `MISS ∧ coalesced != true` is necessary but **not sufficient while F-L stands** (a MISS following an orphan "absorbs the remainder", `super-plan.md:179`) | **Adopted.** The rule is stated **per statistic**, and the μ_gen clause says "while F-L is open" |
| 7 | NOTE | **The panic path breaks the "iff".** If anything after `Answer` in the closure panics, the deferred emit logs `cache: ""` with `t_generate_ms` null although `Answer` ran | **Adopted.** The reading rule is qualified to **records with a non-empty `cache`**. The copy stays after `Do` (inside the closure would follow the rule more closely but changes the panic path; accepted as a trade) |
| 8 | NOTE | Test hygiene: T2 compares against the 25 ms constant or a µs-floored held time, not a nanosecond `held`; T3 must not assert "a few µs"; T3 pins `Acquire`'s fast path ignoring the context, so declare it **ADMISSION-SENSITIVE** (the "1.3-SENSITIVE" precedent); design unknown 1 is settled by causality (the fake server's handler cannot run before `genStart`), not by a test | **Adopted** |
| 9 | NOTE | **Stale guidance:** `super-plan.md:165-166` sends readers to F-A's `approvals.md` for the reading of ABANDONED, so item 1.6 would read `approvals.md:66` ("null on all of them"). Append the superseded note to **F-A's `approvals.md` only**: roughly 20 lines across closed spec/plan/design/review files is churn, and dated trails are historical by construction | **Adopted.** The pointer is updated to the new record (and to §H after v0.12); the single dated note goes on F-A's `approvals.md`; `impact.md` §5's longer list is withdrawn |
| 10 | NOTE | **Measurement.** `Counters`, `/stats`, k6 and the UI are unaffected. Logs carry no gateway SHA until P1, so 1.6's first `RUN_ID` must be taken **after** this commit. And `spec.md`'s "hang vs crash": under k6 a hang always lands in ABANDONED, so the **label** already separates a hang from a crash; the **duration** cannot separate a hang from a slow generation (both read ≈ 120 s minus the time before `Answer`) | **Adopted.** The spec's purpose statement is corrected: the duration separates an immediate failure (ms) from a long one (s) and nothing finer. A note for 1.6 is added |

## What the review says the design gets right

One assignment site before the switch, so every future outcome case inherits it, and the old
success-only line deleted. Not bundling the `rec.Coalesced` move: the F-L bound does not need it (a null
ABANDONED is never an orphan, whichever kind it is), and followers can be recovered offline with a
`t1_key` time-interval join. Correct claims throughout: follower null by construction, every
GENERATION_FAILED leader reached `Answer`, the µs-zero limitation (filter on `!= null`), the
presence-equivalence hazard, `-race` run once. A new test file with no edits to immutable tests and
lower bounds only. **The harness supports every fixture:** a delayed failing hook (`onAnswer`), a gated
`Answer` plus cancel (`holdAnswers`), `leavingStore`, a queued second request, and a pair with distinct
raw texts matched by `query_raw` because 502 bodies are not JSON.

## Questions the review puts to the author (carried to `approvals.md`, defaults taken)

1. **Take the doc-only v0.12 for §H in this commit?** Default **yes**: adds a contract phase and
   ADR-006.
2. **1 ms and the [1 ms, 100 ms] gap count: into P1's manifest now, or fixed in the experiment phase?**
   Default: pre-registered in the experiment record; P1 copies it.
3. **T3 stays**, marked ADMISSION-SENSITIVE, with no `t_permit_wait_ms` assertion. Default yes.
4. **Record the queued-then-left `t_permit_wait_ms` null as a finding beside §6e.** Default yes.
5. **Is a future F-D fix expected to re-elect followers on an upstream failure as well as on the leader's
   cancellation?** T5's "follower is null" survives the second but not the first; declared
   F-D-SENSITIVE.

---

# Implementation review — `/ai-review`, 2026-10-06

Two reviewers read the diff, the new tests and the contract: the **`contract-reviewer`** (code and tests
against §H v0.12 and ADR-006; it reproduced mutations on scratch copies) and the
**`feature-dev:code-reviewer`** (static; it had no shell). **No MUST-FIX.** Both traced every path through
`Ask` after `Do` returns (SHED, queued-then-left, fast-path-then-left, GENERATION_FAILED, MISS, a MISS whose
client left, every follower, a panicking leader) and found the one moved statement correct. The contract
reviewer also ran the six new tests 50 times under `-race`, and 40 times each at `-cpu 1,4` under ten
busy-loop processes, with no flake, and measured T3's never-sent value over 100 `-race` runs at 12-25 µs.

| # | Tag | Finding (reviewer) | Resolution |
| :-: | :---: | :--- | :--- |
| I1 | SHOULD, CONFIRMED | **A surviving mutation on the MISS span.** §H says a MISS's value is *"the time `Answer` took, before write-back"*, and clause (ii) says it is a lower bound on the permit hold *because* it excludes write-back. Reproduced: adding `generateMS = msPtr(time.Since(genStart))` just before `return &generation{` (after Put, PutTier2, touch and TrimToCapacity) passes the whole suite. μ_gen would be silently inflated by the cache's round trips (CT 1) | **Fixed.** T7 `TestAMissGenerationTimeExcludesItsWriteBack` (a `slowPutStore` holds the Tier-1 write-back 100 ms; `t_total_ms − t_generate_ms ≥ 99`) and mutation **F8** |
| I2 | NOTE, CONFIRMED | **No test pins that a coalesced MISS follower has `t_generate_ms` null** (CR 1; `ask_test.go:465` skips followers explicitly, N5). The v0.12 selection rule `MISS ∧ t_generate_ms != null` selects exactly the leaders only because of this. A later change that copies the leader's span to followers on the success path would pass every test and F1-F7 (all act before the switch) and double-count μ_gen and occupancy | **Fixed.** T8 `TestACoalescedMissFollowerCarriesNoGenerationTime` and mutation **F9** |
| I3 | SHOULD, CONFIRMED | **§H's two rows disagree.** The `t_*_ms` row (`:601`) still said *"the difference is gateway overhead and is reported as such"* while the new `t_generate_ms` row's item (v) says it is **not** a clean overhead (CT 2) | **Fixed.** One sentence in `:601` now says the difference is reported as overhead *only with the caveats in the `t_generate_ms` row, item (v)*. A sixth hunk beyond the approved five: recorded in `approvals.md` and as `contract-draft.md` A6 |
| I4 | NOTE, CONFIRMED | The test file's header said *"No test here asserts `t_permit_wait_ms`"*, but T6 reads it as a precondition and `Fatalf`s if it is null (CT 3). T6's use is a lower bound on a queued-then-**served** request, so it survives an F-N fix | **Fixed.** The header now says no test **pins the null cases**; T6 reads it only as a precondition |
| I5 | NOTE, CONFIRMED | `impact.md` §8 item 8 still said to select `cache == "MISS" ∧ coalesced != true`, *"never `t_generate_ms != null`"*, the reverse of the final rule (CT 4). The trail is still open | **Fixed.** Marked superseded in place, pointing at `approvals.md`'s post-approval corrections |
| I6 | NOTE, CONFIRMED | **The panic path is unenforced.** A `Put` that panics gives one record with `cache=""` and `t_generate_ms=nil` (true, reproduced), but moving the copy into the closure, or guarding it with `!shared`, passes every test, so "deliberately NOT inside the closure" is a comment, not a check (CT 5, CR 3) | **Accepted.** §H qualifies the rule with "for a record with a non-empty `cache`", so either placement is within the contract. Recorded, not tested: a test would pin an implementation detail the contract does not require |
| I7 | NOTE, PLAUSIBLE, negligible | `msPtr` returns nil for an exact-zero `Duration`, so T3's `genMS` would `Fatalf` if `Answer` on a dead context returned within one clock tick (CR 2). The tick is ~41 ns; the recorded minimum is 1 µs | **Accepted.** Already a stated limitation (spec: µs and zero) |
| I8 | NOTE | The approvals provenance for impact, experiment and implementation carries no author-words entry (CT) | **Accepted**, same shape as every earlier trail: the `/approve <phase>` commands are the record |

## Checked and clean (CONFIRMED by the reviewers)

Only `:482` reads `rec.GenerateMS`; `Counters` read only `Cache` and `Coalesced`; `permitWait` and
`queueDepth` are unaffected; against HEAD's handler T1, T2, T3, T5 and T6 fail by assertion and T4
passes, as `plan.md` says; the six tests have no name collisions, leak no goroutine or gate, and have no
upward-flaky assertion (T6's precondition `wait >= held` holds deterministically, and the integer-µs
inequality cannot flake high); T4 and T5 cannot pass vacuously (a shed B would never reach `Queued()==1`,
and `Waiters(key)==1` plus `answerCalls()==1` rule out a follower that failed to coalesce); every clause of
the §H row and the v0.12 block is true of the code; `grep 'null unless generation ran'` is empty; only
`handler.go` and docs changed, no existing test file is modified, the `.proto` is untouched, and the hit
path gains nothing; the F-H and F-N/F-O entries in `super-plan.md` and the one superseded note in F-A's
`approvals.md` are in place; a reviewer re-ran F3, F5 and F7 and matched `mutations.md`.

**No MUST-FIX. Every SHOULD-FIX is fixed (I1, I3) and every NOTE is fixed or accepted with its reason.**
