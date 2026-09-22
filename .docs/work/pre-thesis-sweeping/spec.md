# Spec — pre-thesis-sweeping

**Opened:** 2026-09-21 · **Driver:** `Pre-thesis_Sweeping.md` (root), opened 2026-09-15.

## What this task is

Close out everything still sitting in the pre-thesis phase so the thesis phase starts from a base
that has stopped moving. The scope, the ordering and the blocking findings are **owned by
`Pre-thesis_Sweeping.md`** and are not restated here — that file is the working document and this
trail records execution against it.

Agreed order (author, 2026-09-21): **0 → 5 → 3 → 4 → 2 → 1(remainder)**, with **F1 sitting outside
and above it**.

## What this task is not

- It is **not** task `two-lane-cache`. That task is still open with the workflow deliberately
  bypassed (its own `approvals.md` records this); `Pre-thesis_Sweeping.md` §0.2 requires it to be
  closed properly or explicitly abandoned, and that decision has not been taken.
- It does **not** implement what the ADRs below decide. ADR-035's support gate, ADR-036's removals,
  ADR-037's seam change and ADR-038's corpus rule are **decisions recorded**, not code written. The
  build order for them is `Recommended_system.md` §4/§8, and F1 precedes all of it.

## Done when

Every row of `Pre-thesis_Sweeping.md`'s status board is either done or has moved into an ADR, a
requirements document, or the super plan — at which point that file is deleted, per its own stated
lifespan.
