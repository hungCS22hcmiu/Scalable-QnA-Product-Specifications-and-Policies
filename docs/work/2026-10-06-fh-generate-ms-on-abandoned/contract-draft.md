# Contract draft — `interfaces.md` v0.12 and ADR-006

**Status: DRAFT for `/approve contract`. Nothing here has been applied.** `docs/contracts/interfaces.md`
and `docs/decisions.md` are unchanged. On approval, plan step 1 applies this text **verbatim**.
**It is doc-only: no field is added, removed or renamed, no key, wire shape, `.proto` or frozen value
changes** (`git diff --exit-code contracts/` stays clean; the diff under `docs/contracts/` is exactly
A1-A5 below). Why it exists at all: `review.md` finding 1. The code now writes `t_generate_ms` where
§H's example comment (*"null unless generation ran"*) can be read as forbidding it, and the selection rule
an analyst needs would otherwise live only in a trail.

**Both sides of the seam.** The writer is the gateway (`httpapi/handler.go`, one statement moved). The
readers are **future**: Phase 7's μ_gen and occupancy statistics and any analysis script. None exists, so
nothing breaks; the draft pins what they may rely on. The Go↔Python wire is untouched.

**Decision for the author:** this is review question 1 (`review.md`). **Default: take it.** If declined,
the plan drops its step 1, §H stays as it is, and the per-statistic selection rule lives in
`super-plan.md` alone.

---

# Part A — `docs/contracts/interfaces.md`, v0.11 → v0.12

## A1. Header

`**Status:** Draft v0.11 · … · **Revised:** 2026-10-06` becomes `**Status:** Draft v0.12 · … · **Revised:**
2026-10-06`.

## A2. New block, inserted after the v0.11 block

> **v0.12 changes.** **Doc-only** (**ADR-006**, `super-plan.md` finding F-H): §H's `t_generate_ms` is now
> stated precisely, and the gateway now matches it. **No field, key, wire shape or frozen value
> changes.** `t_generate_ms` is non-null **iff this request's own `Answer` call was attempted**,
> successful or not (for a record with a non-empty `cache`; see the field note). Until the F-H commit the gateway carried it only on a MISS, so it was null on an
> `ABANDONED` or `GENERATION_FAILED` request whose `Answer` had run, which left a stage that ran with no span,
> against the intent of §H's note that a `t_*_ms` is *"null where the stage did not run"*. **Consequence for analysis: the field's
> presence no longer identifies a MISS**, so a statistic that selected MISS records by *"the field is
> present"* must select on `cache` instead (see the field note). **A log written before the F-H commit has
> null on those `ABANDONED` and `GENERATION_FAILED` records, and their `t_generate_ms` is not comparable
> across it.**

## A3. §H — the example comment

`"t_generate_ms": null,                // null unless generation ran` becomes

`"t_generate_ms": null,                // null unless this request's own Answer call was attempted, successful or not (v0.12)`

## A4. §H — field notes, one new row, inserted after the `t_*_ms` row

`| `t_generate_ms` | **v0.12.** Non-null **iff this request's own `Answer` call was attempted**, whether it succeeded or not, for a record with a non-empty `cache`. **Null:** TIER1_HIT, TIER2_HIT, SHED, a request that left or failed **before it held a permit**, and **every coalesced follower** of any outcome (its closure never ran). **Non-null:** a MISS leader (the time `Answer` took, before write-back), a **GENERATION_FAILED leader** (the time until `Answer` returned its error), and an **ABANDONED** request that held a permit. On ABANDONED it is **censored**: at most the generation's true duration, because `rag.server` may keep generating after its RPC is cancelled (F-L, a `super-plan.md` finding). A few microseconds **indicates** the RPC never left (the client had already gone and `Acquire` took its fast path, or a queued request whose client left as a permit freed won the random `select` and was admitted with a dead context); a larger value **indicates** it reached `rag.server`, and **any threshold between the two is fixed by the analysis before it looks at the distribution** (never tuned after), **with the count of ABANDONED values between 1 ms and 100 ms reported beside any split and the split called unresolved if that count is not negligible (ADR-006)**. A cancel during a lazy connect can land between the two. **Reading it:** (i) **service-time and μ_gen statistics select `cache == "MISS" ∧ t_generate_ms != null`, never "the field is present" alone**: a MISS follower's value is always null and a MISS leader's is not, so this selects exactly the leaders that the field's presence selected before v0.12. (`coalesced` is a gateway extension field that §H does not define, and it is **absent**, never `false`, on a leader, so do not test `coalesced == false`.) While F-L is open that is necessary but not sufficient (a MISS that follows an orphaned generation absorbs the remainder); (ii) **permit-occupancy statistics may select on presence**, since every attempt held the permit, **but `t_generate_ms` is a lower bound on a MISS's hold** (the permit is held through write-back, which the value excludes) **and no permit exists when admission is disabled**; (iii) filter on `!= null`, never `> 0`, because a duration under 1 µs is written as `0`; (iv) **a null on a GENERATION_FAILED record means a follower**, and **a null on an ABANDONED record is ambiguous** (left while queued, or a follower), because the extension field `coalesced` is set only on a served MISS; (v) the difference `t_total − Σ t_*` is **not a clean "gateway overhead"**: it no longer counts a failed generation's time (it did before v0.12), it is **understated** because `t_embed_ms` and `t_overlap_ms` run concurrently, and a MISS's write-back and a follower's wait on the leader land in it; (vi) **non-null no longer implies an answer was served** (ABANDONED and GENERATION_FAILED carry it with `answer_sha256 == ""`), and ⚠️ **`t_permit_wait_ms` is null on a fast-path request, after a request that queued and then left, and when admission is disabled**, so `t_permit_wait_ms != null` is **not** "a permit was held" and a mean over it is biased (ADR-006). **Not comparable across the F-H commit** for ABANDONED and GENERATION_FAILED records; logs carry no gateway SHA until P1, so take any run recorded after that commit |`

## A5. Versioning

- `**Current version: v0.11** (2026-10-06).` → `**Current version: v0.12** (2026-10-06).`
- New first row in the table (above v0.11):

`| **v0.12** | 2026-10-06 | **Doc-only.** §H's `t_generate_ms` is stated precisely: non-null iff the request's own `Answer` call was attempted, successful or not (for a record with a non-empty `cache`), so it is now also non-null on ABANDONED and GENERATION_FAILED leaders that reached `Answer` (**ADR-006**, finding F-H). The example comment is rewritten and a field note added with the per-statistic selection rule. No field, key, wire shape, `.proto` or frozen value changes. The field's presence no longer identifies a MISS. ABANDONED and GENERATION_FAILED records' `t_generate_ms` is not comparable across the F-H commit |`

## A6. §H — the `t_*_ms` row, one sentence (post-approval correction, 2026-10-06)

The `t_*_ms` row's *"the difference is gateway overhead and is reported as such"* contradicted the new
`t_generate_ms` row's item (v) (the difference is **not** a clean overhead). It becomes: *"the difference is
reported as gateway overhead **only with the caveats in the `t_generate_ms` row, item (v)** (it is not a clean
overhead)"*. This is a sixth hunk beyond A1-A5, recorded in `approvals.md`.

---

# Part B — `docs/decisions.md`, ADR-006

## B1. Summary table, one new row

`| ADR-006 | `t_generate_ms` means "this request's own `Answer` call was attempted" | in force (one open item: the 1 ms threshold) | none — no runs yet; ABANDONED and GENERATION_FAILED records' `t_generate_ms` is null before the F-H commit and not comparable across it, and any derived overhead is not either |`

## B2. The entry, appended after ADR-005

### ADR-006 — `t_generate_ms` means "this request's own `Answer` call was attempted"
**Decided (method)** · 2026-10-06 · *`interfaces.md` §H v0.12, `gateway/internal/httpapi/handler.go`, `super-plan.md` finding F-H; trail `docs/work/2026-10-06-fh-generate-ms-on-abandoned/`*

The evaluation log's `t_generate_ms` is non-null **iff this request's own `Answer` call was attempted**,
whether it succeeded or not (for a record with a non-empty `cache`; a leader that panics after `Answer` is
logged with `cache: ""` and no value). The gateway now carries it on `ABANDONED` and `GENERATION_FAILED` leaders
that reached `Answer`, where it previously carried it on a MISS only. §H is amended to say so (v0.12,
doc-only). No field, key, wire shape or frozen value changes.

- **Rationale:**
  - **The code left a stage that ran with no span**, against the intent of §H's note that a `t_*_ms` is
    null where its stage did not run (a one-directional rule, so this is a tightening, not a breach). The
    stage (the gateway's span around `ragclient.Answer`) ran on a failed or cancelled attempt, and the
    closure computed the duration, then dropped it on every non-success path.
  - **It answers two questions that were unanswerable.** *Did an abandoned request's own `Answer` get
    attempted?* Before, only a filter on `permit_queue_depth >= 1` selected one subset and could not see a
    request that took `Acquire`'s fast path and left. *How long did a failed generation take?* The
    duration separates an immediate failure (ms) from a long one (s). It cannot separate an upstream hang
    from a slow generation: under k6 both read ≈ 120 s minus the time before `Answer`, and a hang already
    lands in `ABANDONED`.
  - **Why a contract entry for a one-line fix.** The field's *presence* used to mean exactly
    `cache == MISS ∧ ¬coalesced`. It no longer does. An analyst reading the example comment who selects
    MISS service times by presence would take in ABANDONED durations censored near 120 s and bias μ_gen,
    silently. The selection rule must live where the field is defined, not in a trail.
- **Alternatives:**
  - **Leave §H unchanged and record the rule in the trail.** Rejected by the design review: the example
    comment *"null unless generation ran"* can be read as forbidding the new values (the fast-path
    dead-context request makes no RPC), and a trail is closed when its task is.
  - **A new field** (`reached_server`, an RPC-sent timestamp). Rejected: a new §H field is a contract
    decision this bug does not need, and `t_generate_ms` plus the threshold below is enough.
  - **Also move `rec.Coalesced = shared` above the outcome switch.** Rejected for now: the same flaw, but
    a **second measurement change** (an extension field would appear on SHED, ABANDONED and
    GENERATION_FAILED records, and a follower of a shed leader would read SHED plus `coalesced`). Recorded
    as a finding next to F-D.
  - **Copy the value inside the closure** rather than after `Do`. Rejected: it changes the leader-panics
    path for no gain.
- **Consequences:**
  - **Per-statistic selection** (§H v0.12 field note): service-time and μ_gen select
    `cache == "MISS" ∧ t_generate_ms != null` (a MISS follower's value is null, a leader's is not, so this
    is exactly what presence selected before; `coalesced` is an extension field §H does not define and is
    **absent**, never `false`, on a leader), and while F-L is open that is necessary but **not
    sufficient**; permit-occupancy statistics may select on presence, but `t_generate_ms` is a **lower
    bound** on a MISS's hold (the permit is held through write-back) and no permit exists when admission
    is disabled; filters use `!= null`, never `> 0`.
  - **What a null means after the fix:** on GENERATION_FAILED a follower; on ABANDONED either a request
    that left while queued or a follower (`coalesced` is set only on a served MISS), so the two cannot be
    told apart offline except by a `t1_key` time-interval join. **F-L** is the `super-plan.md` finding that
    `rag.server` keeps generating after its RPC is cancelled; **F-D** is the one that a coalesced follower
    inherits its leader's cancellation.
  - **ABANDONED's value is censored** (F-L): at most the generation's true duration, and silent on
    whether `rag.server` finished. It tightens the orphan upper bound; it does not turn it into a count.
  - **The "RPC never left" split needs a threshold, and the threshold is pre-registered before anyone
    looks at the distribution.** *Default: 1 ms.* The gap defends the split, not the number: microseconds
    for an RPC that never left against seconds for one cancelled during a real generation. The failure
    mode is a never-sent tail above 1 ms (under `-race`, GC pauses, co-hosted CPU contention, a cancel
    during a lazy connect), which would read as "reached `rag.server`" with nothing to flag it. So an
    analysis **reports the count of ABANDONED values in [1 ms, 100 ms] beside the split and calls it
    unresolved if that count is not negligible.** The number is the author's to confirm and belongs in
    P1's manifest. ⟦PENDING: the author confirms or replaces the 1 ms default⟧
  - **Recorded, not fixed here:**
    - `t_permit_wait_ms` is **null on every fast-path request** (`Acquire` returns a permit with
      `Waited == 0` and the gateway renders a zero duration as null), which contradicts §H's *"null
      unless a permit was requested"*;
    - **and on a request that queued and then left**, because the closure returns before it is set;
    - `coalesced` is set only on a served MISS.
  - **Nothing here changes a count or a label.** Item 1.6's `ABANDONED` count is comparable across the
    commit. **1.6's first `RUN_ID` must be taken after this commit**: logs carry no gateway SHA until P1.
- **Invalidates:** none — no runs yet. A log written before the F-H commit has null `t_generate_ms` on
  `ABANDONED` and `GENERATION_FAILED` records; those two fields are **not comparable across it**, and any
  derived overhead is not either.
