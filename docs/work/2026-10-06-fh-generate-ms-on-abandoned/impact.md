# Impact — fh-generate-ms-on-abandoned

**Author of the analysis:** `impact-analyst` subagent, with file:line evidence; synthesised here. Four
of its claims were **re-checked by hand** (✔︎): `rec.Coalesced` is assigned only on the success path,
`Acquire`'s fast path returns a permit with `Waited == 0`, §H's wording, and `msPtr`/`durMS`.

## 1. Verdict

- **No frozen value is touched, no `.proto`, no wire shape. `interfaces.md` changes only as a doc-only
  v0.12 (the contract bullet below). No run is invalidated:** `experiments/results/` holds only `.gitkeep` and there is no `requests.jsonl` anywhere.
- **Contract phase: required, as a doc-only v0.12 + ADR-006** *(revised after `review.md` finding 1; the
  analysis first said "not required")*. §H's field note (✔︎ `interfaces.md:590`, *"`t_*_ms` — Null where
  the stage did not run"*) arguably covers a failed attempt, and the `:590` sentence about an **errored**
  stage is `t_search_ms`'s own, not a general rule. But the example comment (`:552`, *"null unless
  generation ran"*) can be read as forbidding a value on the dead-context fast path (the server sees 0
  RPCs), and **the first analysis was inconsistent**: it treated `:551`'s comment as normative to call the
  fast-path `t_permit_wait_ms` null a defect (§6e) while treating `:552`'s as non-normative to avoid a
  bump. Precedent (v0.6, v0.10) bumps for "restates / changes meaning" with no wire change. **No field, key,
  wire shape, `.proto` or frozen value changes**; drafted in `contract-draft.md`. The author may decline.
- **Experiment phase: required, record-only.** It changes which records carry a non-null field.
- **The risk that could fail silently:** until this commit, `t_generate_ms != null` meant exactly
  `cache == MISS ∧ ¬coalesced`. After it, it does not. A later μ_gen or service-time statistic that
  selects records by *"the field is present"* would quietly take in **censored** ABANDONED durations and
  failed-call durations. The record must say: **select on `cache`, never on presence of the field.**

## 2. Packages and races

| File | Change | Layering |
| :--- | :--- | :--- |
| `gateway/internal/httpapi/handler.go` | move `rec.GenerateMS = generateMS` (`:523`) to just after `Do` returns, before the outcome switch | no import change |
| `gateway/internal/httpapi/<new>_test.go` | new tests only | tests |
| `docs/super-plan.md`, this trail, a dated "superseded" note appended to the F-A trail | the reading rule; stale lines | docs |
| `telemetry/`, `coalesce/`, `admission/`, `ragclient/`, `.proto`, `docs/contracts/` | **not touched** | — |

- `generateMS` is declared at `:386`, written only at `:401` inside the closure, read only at `:523`. The
  closure runs only on `Do`'s **leader** branch, on the **caller's own goroutine** (`coalesce.go:72`,
  `c.val, c.err = fn()`); the follower branch (`coalesce.go:44-48`) returns without calling `fn`. So the
  write and the read are on one goroutine, in order. **No data race is introduced.** The record reaches
  the log writer by value over a channel (`evallog.go`), which orders the pointer's write before the
  writer's read.
- **Smallest change: move one statement, do not add two.** Copy it **after `Do`, not inside the
  closure**: writing it inside would change the leader-panics path for no gain (§6, edge c).
- `permitWait`/`queueDepth` (`:384-385`) are written at `:393` and read only by the dead `_, _ =` at
  `:525`. Pre-existing; not touched.

## 3. Consumers: nothing reads the field

The only references are `handler.go:386/401/523`, `evallog.go:57` and tests. No Python; k6's
`ask.js` and `mu_hit.js` read only the HTTP `body.cache` and latency; `load_burst.py` uses HTTP
`wall_ms`; `ui/src` uses §A's `latency_ms`; neither the Makefile nor `make demo` reads it;
`Counters.record` (`browse.go`) reads only `rec.Cache` and `rec.Coalesced`, so `/stats` is unchanged.
No mean or percentile of it exists today. **Two future skews:** (i) the presence equivalence above;
(ii) §H's *"gateway overhead = t_total − Σ t_*"*: before the fix a failed or abandoned generation's
whole duration counted as overhead, after it that time moves into `t_generate_ms`. A correction, but
not comparable across the commit.

## 4. Existing tests: none pins the bug, none must change

Assertions on the field: `ask_test.go:62` (TIER1_HIT, null), `:95` (MISS, non-null), `:356` (SHED,
null: still null, `Acquire` returns `ErrShed` before `genStart`), `:465` (MISS leader, non-null),
`evallog_test.go:70` (a hand-built record). The 1.2 and F-A tests **deliberately** leave it unasserted on
GENERATION_FAILED and ABANDONED and name F-H as the reason (`ask_test.go:404`, `abandon_test.go:64-65`).
`ask_test.go:371-401` (queued then left) and `abandon_test.go` T2-T7 do not assert it;
`checkEveryRecord` does not read it. **No existing test fails, so this is not a "tests are immutable"
stop.** Those two comments become stale; F-A's precedent (`abandon_test.go:13-15`) is to leave a stale
comment in a closed test and name it in the new file's header. **All new assertions go in a new test
file**, because adding them to `TestAbandonedWhileQueuedIsNotAShed` or
`TestGenerationFailureIsNotServedOrCached` would edit immutable tests.

## 5. Guidance this fix makes stale *(narrowed by `review.md` finding 9)*

Edited in place: `super-plan.md` (`:172-173` "upper bound … until F-H lands", which stays an upper bound
so it is rephrased; `:187-191` the F-H entry, now resolved; **and the pointer at `:165-166` that sends
readers to F-A's `approvals.md` for the reading of ABANDONED**, which still says `t_generate_ms` is null
on all of them). **One** dated "superseded by `2026-10-06-fh-generate-ms-on-abandoned`" note is appended to
F-A's `approvals.md` (`:59-68`, especially `:66`, `:88`, `:111-113`). The rest of the F-A trail (`spec`,
`plan`, `design`, `review`, `impact`) and the 1.2 trail are **not touched**: dated trails are historical,
and about twenty appended lines would be churn. Nothing in `decisions.md` (before ADR-006) is stale.

## 6. Edge cases

- **(a) A client that left after Tier 1, with a free permit.** Embed and retrieve fail on the dead
  context and degrade; `Acquire`'s fast path ignores the context (`pool.go:93-97`); `genStart`; `Answer`
  fails before sending. ABANDONED with a **few µs** non-null. **The same happens to a queued leader
  whose client leaves just as a permit frees:** the `select` at `pool.go:110-115` picks at random, so it
  can be admitted with a dead context, with `permit_queue_depth >= 1` and a µs-scale value. F-A's
  `permit_queue_depth >= 1` orphan filter wrongly includes it today; `t_generate_ms` excludes it.
- **(b) `msPtr` and zero.** `msPtr` returns nil only for `d == 0`; `durMS` truncates to whole µs, so
  `0 < d < 1 µs` is written as **`0`, which is non-null**. Readers filter on `!= null`, never `> 0`.
  An exact zero cannot occur: a gRPC call spans many clock ticks.
- **(c) A leader that panics in the closure.** `coalesce.go:64-67` gives followers an error and
  re-panics; the deferred emit logs `cache: ""` with no `t_generate_ms`. The fix does not change that
  **as long as the copy stays after `Do`**.
- **(d) An F-D follower of a failed leader.** Its closure never runs, so the value is null. **And
  `coalesced` is set on no failure path** (✔︎ `rec.Coalesced = shared` only at `:524`). So after the fix:
  a **null on a GENERATION_FAILED record means a follower** (every GENERATION_FAILED leader reached
  `Answer`, since `Acquire` returns only `ErrShed` or `ctx.Err()`); a **null on an ABANDONED record is
  ambiguous** (a leader that left while queued, or a follower).
- **(e) A pre-existing finding that bears on F-A's guidance.** `rec.PermitWaitMS`/`PermitQueue` are
  written onto the leader's record on every path that got a permit, ABANDONED and GENERATION_FAILED
  included, **but `t_permit_wait_ms` is non-null only when the leader queued**: the fast path returns
  `&Permit{pool: p}` with `Waited == 0` (✔︎ `pool.go:95`) and `msPtr(0)` is nil. That contradicts §H's
  *"null unless a permit was requested"* (`interfaces.md:551`) on every fast-path request, MISS
  included. Not caused or fixed here: recorded as a new finding.
- **(f) The log writer.** The `Record` shape is unchanged; `Log` is non-blocking and takes the record
  by value; no answer file is written (`answer_sha256` is `""` on these paths). No effect on `Dropped()`.

## 7. Frozen values and what is measured

None frozen, no ADR. **What changes:** which §H records carry a non-null `t_generate_ms` (ABANDONED
leaders that held a permit, GENERATION_FAILED leaders). **What does not:** no `cache` label, no count, no
MISS value, no §A response. Item 1.6's `ABANDONED` count stays comparable across the commit;
`t_generate_ms` on ABANDONED/GENERATION_FAILED records, and any derived overhead, do not.
**Invalidates: none — no runs yet.** Nothing from `Final_Proposal.md` §12 is reinstated, and no
dependency is added.

## 8. Corrections to `spec.md` (applied in revision 2)

1. `coalesce.go:73` → `:72`.
2. **Acceptance 6 fails as written**: the follower's record does not carry `coalesced: true` (✔︎ set only
   at `:524`). Identify the follower by **distinct raw text that normalises to the same key**
   (`abandon_test.go:221-225`); the harness matches a 502 by `query_raw`.
3. **Reading rule:** add the converse (null on GENERATION_FAILED ⇒ a follower) and that null on ABANDONED
   is ambiguous.
4. **Limitations:** exact zero → null, but `0 < d < 1 µs` → `0` (non-null): filter on `!= null`.
5. **Acceptance 8:** `git diff --exit-code contracts/` checks only `contracts/rag/v1/rag.proto`; §H is in
   `docs/contracts/`. Use `git diff --exit-code contracts/ docs/contracts/`.
6. All new assertions in a **new test file** (say so).
7. **"A few µs means the RPC never left" is an order-of-magnitude rule of thumb, not a field.** A cancel
   that races the stream setup can land in between. The threshold is fixed **in advance** (below).
8. **Add the selection rule.** *(Superseded by the contract review: the final rule is
   `cache == "MISS" ∧ t_generate_ms != null`, never presence alone, because `coalesced` is an extension
   §H does not define and is absent on leaders. See `approvals.md`, post-approval corrections.)*
9. Open question 2's stale-guidance list: use §5 above.

## 9. Risks passed to design review

1. The presence equivalence breaks (§1): it must be a selection rule in the experiment record.
2. **Should `rec.Coalesced = shared` also move above the switch?** Same flaw, one line, and it would make
   acceptance 6 work as first written and resolve the ambiguous ABANDONED nulls. But it is a **second**
   measurement change (an extension field would appear on SHED/ABANDONED/GENERATION_FAILED records, and a
   follower of a shed leader would read SHED plus `coalesced`). **Default: not bundled; recorded next to
   F-D.**
3. `t_permit_wait_ms` null on the fast path (§6e): a new finding that changes how F-A's record reads
   admission.
4. Fix the µs-versus-reached threshold **before** anyone looks at the ABANDONED distribution (the
   never-tune rule).
5. Where the copy goes (after `Do`); run `go test -race ./internal/httpapi/` once, since `make test` does
   not run `-race`.
6. Acceptance 1 and 2 are **lower bounds only**; for 2, time from the moment the test sees
   `answerCalls()==1` (which is after `genStart`) to `cancel()`, and hold `Answer` ≥ 20 ms so the bound
   means something.
