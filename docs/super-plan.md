# Super Plan — execution to submission

**Status:** skeleton · **Created:** 2026-09-21 · **Shape approved:** 2026-09-21 (`Pre-thesis_Sweeping.md` §3)
**Companion to:** `requirements.md` (what must be true), `time_line.md` (the phase plan this will retire), `decisions.md` (what was decided), `learning/Final_Proposal.md` §12 (drop order) and §13 (deliverables).

> ⚠️ **This document is deliberately empty of plan items.** Per `Pre-thesis_Sweeping.md` §3: create
> the structure first, fill it only after final sign-off on the shape. The item template below shows
> exactly what a filled row looks like; the phase sections are placeholders.

---

## What this document owns, and what it must never restate

There were **four** places describing what to do next: `time_line.md`, `Final_Proposal.md` §11, §12
and §13, and the pre-thesis report §5.1. Four sources for one plan is how a plan drifts.

| Owner | Owns |
| :--- | :--- |
| **`super-plan.md`** (this file) | **Execution.** The ordered items, who they discharge, what unblocks them, and what "done" means for each |
| `Final_Proposal.md` §12 | **Drop order under pressure.** Never restated here — many documents cite §12, and a second copy is exactly what would drift when schedule pressure arrives |
| `Final_Proposal.md` §13 | **Deliverables.** Never restated here |
| `requirements.md` | **What must be true.** Items cite `FR-xx` / `NFR-xx` / `RR-xx`; they do not re-argue them |
| `decisions.md` | **Why.** Items cite `ADR-NNN`; they do not re-argue it |

**`time_line.md` is retired into this file** — but **not yet**. Two things have to happen first:
its phase table and exit criteria must be carried across, and `.claude/hooks/lib.sh` must stop
reading it (`current_week()`, `week_row()`, and the session banner grep `| **<week>**` with
"Done when" as column 5). That second part is `Pre-thesis_Sweeping.md` **#4**, the harness
re-engineering. Deleting `time_line.md` before #4 lands breaks `/week`, `/gate` and the banner.
Until then the two coexist and **`time_line.md` remains authoritative for the phase plan.**

---

## Item template

Every item is a row of this shape. An item that cannot fill the citation columns is not ready to
be planned — it needs a requirement, or an ADR, or both, first.

| # | Item | Discharges | Decided by | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| *0* | *(example, not an item) Resolve F1 — establish whether Ollama's `-np 1` override makes the permit pool bound to a concurrency the model server never offers* | *NFR-xx (shedding), RR-xx (admissibility of any shed rate)* | *ADR-017, ADR-022* | *now — nothing blocks it* | *A recorded run in which offered concurrency, admitted concurrency and Ollama's actual parallelism are the same number, or a documented reason they cannot be* |

Two columns earn their place and are easy to skip:

- **"Unblocked when"** is what makes the order *derivable* rather than asserted. An item whose
  blocker is another item creates the sequence automatically; an item blocked by a human decision
  says so, by name, so it is visible that it is waiting on a person rather than on work.
- **"Done when"** is a **binary test**, the same discipline `time_line.md`'s exit criteria already
  use. "Improved", "hardened" and "investigated" are not done-conditions. An item is not finished
  because its time is spent.

---

## Standing constraints on every item

These are not items. They hold across all of them, and an item that violates one is wrong
regardless of how well it is executed.

1. **F1 sits above the order.** No admission-control number is citable until it resolves
   (`Recommended_system.md` §4, `Pre-thesis_Sweeping.md` §0.2).
2. **The platform is the thesis.** Research work never starves platform work.
3. **`dev-v0` is not citable in any result.** Only the frozen `v1` (ADR-020, ADR-039).
4. **Runs taken under yellow or red memory pressure are discarded and repeated** (ADR-012,
   `experiment-protocol.md` §1).
5. **A frozen value changes only through an ADR**, and the ADR states what it invalidates
   (`.docs/ai/rules.md` #1).

---

## Phases

Carried across from `time_line.md` when this file is filled. Headings exist so that filling it is
an append, not a redesign.

### Phase 1 — Experimental apparatus
`TODO(after sign-off)`

### Phase 2 — Invalidation and literature
`TODO(after sign-off)`

### Phase 3 — The rule and the judged set
`TODO(after sign-off)`

### Phase 4 — Correctness evaluation
`TODO(after sign-off)`

### Phase 5 — Systems hardening
`TODO(after sign-off)`

### Phase 6 — Scalability campaigns
`TODO(after sign-off)`

### Phase 7 — Write-up and defence
`TODO(after sign-off)`
