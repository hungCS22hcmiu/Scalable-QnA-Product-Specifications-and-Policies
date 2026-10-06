# Approvals — fh-generate-ms-on-abandoned

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | yes      | 2026-10-06 | — (`impact.md` §1, §7: no frozen value touched, no `.proto` or wire shape; **no `run_id` invalidated**, none exist. `interfaces.md` changes only as the doc-only v0.12 of the contract phase) |
| contract       | **required, doc-only** (`interfaces.md` v0.12) | yes | 2026-10-06 | ADR-006, **approved as drafted in `contract-draft.md`** (A1-A5, B1-B2); applied verbatim at plan step 1. Doc-only: no field, key, wire shape, `.proto` or frozen value changes; the diff under `docs/contracts/` is exactly the five hunks A1-A5. **Invalidates no run** (none exist); a log written before the F-H commit has null `t_generate_ms` on ABANDONED and GENERATION_FAILED records and is not comparable across it for those two fields |
| experiment     | **required, record-only** | yes (record-only) | 2026-10-06 | — Experiment record below. Changes which records carry a non-null `t_generate_ms`; changes no label, count, span, hit-path cost or §A response. Invalidates no `run_id`: none exist. The never-sent-tail reading and the `-race` result are recorded at plan step 5 |
| implementation | always   | yes      | 2026-10-06 | ADR-006 (applied at plan step 1) |

## Human decisions

| Date | Decision | Author's words | Invalidates |
| :--- | :--- | :--- | :--- |
| 2026-10-06 | **Open the F-H bugfix next, before item 1.6 reports its `ABANDONED` count** | "oke fix đi, mở bugfix" | — |
| 2026-10-06 | **Take the doc-only `interfaces.md` v0.12 and ADR-006**, as drafted | `/approve contract` | none: no runs; ABANDONED / GENERATION_FAILED `t_generate_ms` not comparable across the commit |

## Open — needs the author (each has a default, taken and reversible)

Gates **`/approve contract`**:
1. ✅ **DECIDED 2026-10-06: taken** (`/approve contract`). *Was:* take the doc-only v0.12 + ADR-006 for §H (`review.md` question 1)? **Default: yes.** The reviewer's
   case: the example comment can be read as forbidding the new values, the per-statistic selection rule
   must live where the field is defined, and the contract says any change needs a `decisions.md` entry.
   If you decline, the plan drops step 1, §H stays as it is, and the rule lives in `super-plan.md` alone.

Does not gate the code:
2. **The threshold for "the RPC never left": 1 ms, with the [1 ms, 100 ms] count reported beside the
   split** (question 2). Pre-registered in the experiment record; **your number to confirm or replace**,
   and it belongs in P1's manifest. Default: 1 ms.
3. **T3 stays, marked ADMISSION-SENSITIVE, with no `t_permit_wait_ms` assertion** (question 3). Default yes.
4. **Record the queued-then-left `t_permit_wait_ms` null as a finding** beside the fast-path one
   (question 4). Default yes.
5. **Is a future F-D fix expected to re-elect followers on an upstream failure too?** (question 5). T5
   ("the follower is null") survives re-election on the leader's *cancellation* but not on an upstream
   failure; it is declared F-D-SENSITIVE. No decision needed now.

## Experiment record (phase approved 2026-10-06, record-only)

Nothing is re-measured: no run exists (`experiments/results/` holds only `.gitkeep`). From the F-H commit
on, the evaluation log is read as follows. *(The §H text that states the rule is `contract-draft.md`,
still awaiting `/approve contract`; this record does not depend on it.)*

**What changes.** Which records carry a non-null `t_generate_ms`: **ABANDONED requests that held a permit**
and **GENERATION_FAILED leaders**, which carried null before. **What does not change:** no `cache` label,
no count, no MISS value, no span, no §A response, no hit-path cost (the fix is one statement moved), and
nothing on the log writer. Item 1.6's `ABANDONED` count stays comparable across the commit.

**The reading rule.** For a record with a non-empty `cache`, `t_generate_ms` is non-null **iff this
request's own `Answer` call was attempted**, successful or not. Null: TIER1_HIT, TIER2_HIT, SHED, a request
that left or failed before it held a permit, and **every coalesced follower**. On GENERATION_FAILED a null
means a follower; on ABANDONED a null is ambiguous (left while queued, or a follower), because `coalesced`
is set only on a served MISS. A leader that panics after `Answer` is logged with `cache: ""` and no value.

**Selection rules, per statistic.**
- **Service-time and μ_gen:** `cache == "MISS" ∧ t_generate_ms != null`, **never "the field is present" alone**
  (a MISS follower's value is null and a leader's is not; `coalesced` is an extension §H does not define and
  is absent on leaders). Until
  this commit presence meant exactly that; it no longer does, and a presence filter would take in ABANDONED
  values censored near 120 s. **While F-L is open this is necessary but not sufficient** (a MISS that
  follows an orphaned generation absorbs the remainder).
- **Permit occupancy / utilisation (item 7.5):** presence is the right selector, since every attempt held
  the permit.
- **Filters use `!= null`, never `> 0`:** a duration under 1 µs is written as `0`.

**ABANDONED's value is censored** (F-L): at most the generation's true duration. It tightens the upper
bound on orphaned generations and does not turn it into a count.

**The "RPC never left" split (pre-registered before anyone looks at the ABANDONED distribution).**
*Default threshold: 1 ms*, **together with a check**: report the **count of ABANDONED values in
[1 ms, 100 ms]** beside the split, and call the split **unresolved** if that count is not negligible. The
*gap* defends the split, not the number: µs for an RPC that never left against seconds for one cancelled
during a real generation. The failure mode is a never-sent tail above 1 ms (under `-race`, GC pauses,
co-hosted CPU contention, a cancel during a lazy connect). **The number is the author's to confirm or
replace**, never tuned after the fact, and belongs in P1's manifest.

**Comparability across the commit.** A log written before it has null `t_generate_ms` on those two record
kinds, and any derived overhead (`t_total − Σ t_*`) is not comparable either. Every other field is.
**Item 1.6's first `RUN_ID` is taken after this commit** (logs carry no gateway SHA until P1).

**Recorded at plan step 5** (`evidence/never-sent-tail.md`; exploratory, memory pressure level 1, not
citable): `go test -race` on `httpapi` **ok**. T3's never-sent `t_generate_ms` over 30 runs: **1-12 µs
without `-race`, 12-31 µs under it, 0 of 30 at or above 1 ms** (the worst case is 32× below the default).
That reading is a unit fixture and says nothing of co-hosted CPU contention, GC pauses or a lazy connect,
which is why the pre-registered [1 ms, 100 ms] count check exists. **The first `RUN_ID` is the real reading.**

## Post-approval wording corrections to the approved contract text (2026-10-06)

The contract was approved as drafted. Applying it, a `contract-reviewer` pass found wording that could
produce a wrong number or a false "iff". Corrected in `interfaces.md`, `decisions.md` and
`contract-draft.md` (kept in sync) **before anything is committed**. **None changes a behaviour, a field,
a key or a frozen value**; each makes a sentence true or an instruction safe. Recorded because the author
approved the earlier wording, **and one of them changes the selection rule in the experiment record
above, which was also approved**.

- **The selection rule no longer rests on `coalesced`** (finding 1). `coalesced` is a gateway extension
  field §H does not define, `omitempty`, so **absent, never `false`, on a leader**: `coalesced == false`
  selects nothing. The predicate is now **`cache == "MISS" ∧ t_generate_ms != null`**: a MISS follower's
  value is always null and a leader's is not, so it selects exactly the leaders that presence selected
  before v0.12. The experiment record, `spec.md`, ADR-006 and §H are updated to say so.
- **Permit occupancy** (2): `t_generate_ms` is a **lower bound** on a MISS's hold (the permit is held
  through write-back, which the value excludes), and no permit exists when admission is disabled.
- **`t_total − Σ t_*` is not a clean "gateway overhead"** (3): it is understated by the embed/retrieval
  overlap (the two run concurrently), and a MISS's write-back and a follower's wait land in it.
- **`t_permit_wait_ms`** (4): the field row now carries a ⚠️ that it is null on a fast-path request, after
  a queued-then-left request, and when admission is disabled, so `!= null` is not "a permit was held".
- **"Means" became "indicates"** and the select-race case was added (5): a queued request whose client
  leaves as a permit frees can win the random `select` and reach `Answer` with a dead context. The §H row
  now carries the [1 ms, 100 ms] count check and cites ADR-006.
- **The "iff" qualifier** (6): "for a record with a non-empty `cache`" now appears in the v0.12 block, the
  Versioning row and ADR-006, not only the field note.
- **Smaller:** the comparability caveat now says logs carry no gateway SHA until P1, so take a run
  recorded after the commit (8); "contradicted §H's own rule" softened to a tightening (9); the row says
  non-null no longer implies an answer was served, and points F-L at `super-plan.md` (10); ADR-006 defines
  F-L and F-D in one line each, its Summary row gains "and any derived overhead", and **the 1 ms threshold
  is now a `⟦PENDING⟧` in the ADR** (11), so ADR-006 has **one** open marker, the author's to close.
- **Not changed:** the stale-text findings (7) are plan step 6's; finding 12 (seam clean) needed nothing.

**And one more, from the implementation review (finding I3):** the `t_*_ms` row's *"the difference is gateway
overhead and is reported as such"* contradicted the new row's item (v). It now says the difference is
reported as overhead *only with the caveats in the `t_generate_ms` row, item (v)*. **A sixth hunk beyond
the approved A1-A5**, recorded as `contract-draft.md` A6. Behaviour-neutral, like the rest. Also: the same
review added **T7** (a MISS's span excludes write-back) and **T8** (a coalesced MISS follower is null) as
declared guards, with mutations **F8** and **F9**, because §H states both and no test could fail on either.

## Notes

- `/bugfix` raised this to **L** without asking: `t_generate_ms` is a field of the evaluation log, which
  is the measurement channel (the same reason F-A was L).
- The `/bugfix` template again rendered with unreplaced placeholders (`/task $1 S $2`). The intended
  values were used: slug `fh-generate-ms-on-abandoned`, scope `L`. Fourth time in this repository.
- **No existing test pins the bug.** Checked before opening: the 1.2 and F-A tests deliberately leave
  `t_generate_ms` unasserted on `GENERATION_FAILED` and `ABANDONED` (`ask_test.go:404`,
  `abandon_test.go:64`), naming F-H as the reason. So no test has to change.
