# Requirements — FR · NFR · RR

**Status:** skeleton · **Created:** 2026-09-21 · **Shape approved:** 2026-09-21 (`Pre-thesis_Sweeping.md` §3)
**Companion to:** `learning/Final_Proposal.md` (why), `design/architecture.md` (where), `interfaces.md` (contracts), `decisions.md` (what was decided), `super-plan.md` (when, and by whom, in what order).

> ⚠️ **This document is deliberately empty of requirements.** The agreed sequence is *create the
> structure first, fill it only after final sign-off on the shape* — so that the shape can be argued
> about without a hundred rows of content making it expensive to change. Every section below states
> what belongs in it and gives one worked example, marked as an example. **Adding real rows before
> sign-off defeats the purpose of creating it empty.**

---

## Why three categories and not two

The conventional split is functional against non-functional. It does not fit this project, and
forcing it loses the part that matters most.

Most of this study's binding constraints are neither behaviours the system performs nor qualities it
exhibits at runtime. They are **obligations on how the work is measured** — values frozen before the
first run, memory pressure that must read green or the run is discarded, a false-hit budget,
thresholds that must be swept rather than hand-set, nulls registered before the data is seen, tuning
on validation and reporting on test. Filed under NFR they read as performance targets, which they
are not: missing an NFR makes the system worse, while missing one of these makes the **result
invalid**, and no amount of engineering afterwards recovers it.

So requirements split **three** ways:

| | Category | Asks | Failure mode when violated |
| :--- | :--- | :--- | :--- |
| **FR** | Functional | *What the system does* — the behaviour an observer could check by using it | A feature is missing or wrong |
| **NFR** | Non-functional | *How well it does it* — performance, reliability, observability, operability | The system is worse, and it is visible |
| **RR** | **Research** | *What makes the measurement admissible* — validity, comparability, pre-registration, provenance of numbers | **The result is void, silently, and usually discovered late** |

**RR is the category that defends the thesis in front of the committee.** It is also the one a
normal engineering template has no slot for, which is precisely why it gets its own.

---

## ID scheme and traceability

- IDs are `FR-01`, `NFR-01`, `RR-01` — **never renumbered**, never reused. A withdrawn requirement is
  marked withdrawn in place, with the ADR that withdrew it, exactly as `decisions.md` handles a
  superseded ADR.
- Every requirement cites its **source**: a section of the proposal, a `docs/` contract, or an ADR.
  A requirement with no source is either invented or undocumented, and both need fixing before it
  is admitted.
- Every requirement carries a **verification method** — the test, the script, the gate criterion, or
  the run that demonstrates it. "Reviewed by inspection" is allowed only where nothing executable
  can exist, and must say why.
- Every **super-plan item cites the requirement IDs it discharges**, and every requirement is
  reachable from at least one super-plan item. The chain
  **requirement → design → code → measurement** is the point of the exercise; an unreachable
  requirement and an uncited plan item are both defects in the plan.

Row format:

| ID | Requirement | Source | Verified by | Status |
| :--- | :--- | :--- | :--- | :--- |

---

## FR — Functional requirements

*What the system does. One row per externally checkable behaviour.*

| ID | Requirement | Source | Verified by | Status |
| :--- | :--- | :--- | :--- | :--- |
| *FR-00* | *(example, not a requirement) A request whose normalised text and `product_id` match a cached entry is served from Tier 1 without retrieval or generation.* | *`interfaces.md` §D* | *`cache` package tests + an end-to-end run showing `cache: TIER1_HIT`* | *example* |

`TODO(after sign-off): fill from Final_Proposal.md §6 and interfaces.md §A/§B/§D/§E.`

---

## NFR — Non-functional requirements

*Performance, reliability, observability, operability. Each one needs a number or a bound, or it is
not a requirement — it is a wish.*

| ID | Requirement | Source | Verified by | Status |
| :--- | :--- | :--- | :--- | :--- |
| *NFR-00* | *(example, not a requirement) Under overload the gateway sheds with `503` + `Retry-After` rather than admitting work that swaps; memory pressure stays green at full admission.* | *ADR-022, proposal §7* | *`make load-*` run at saturation with pressure sampled throughout* | *example* |

`TODO(after sign-off): fill from Final_Proposal.md §7/§9, ADR-017, ADR-022, ADR-027.`

---

## RR — Research requirements

*What makes a number admissible. Violating one of these does not degrade the system — it voids the
measurement, usually without any error being raised.*

| ID | Requirement | Source | Verified by | Status |
| :--- | :--- | :--- | :--- | :--- |
| *RR-00* | *(example, not a requirement) Every threshold the reuse rule exposes is swept; none is hand-set. `tau_s` is the one pinned value and is pinned at its published default, reported as an on/off arm.* | *ADR-035, proposal §9.2* | *Run manifests covering the sweep grid; `support_gate` recorded per run* | *example* |

`TODO(after sign-off): fill from experiment-protocol.md §1/§3/§5/§6, data-card.md §7, ADR-006,
ADR-012, ADR-017, ADR-019, ADR-023, ADR-027, ADR-028, ADR-029, ADR-035, ADR-036, ADR-038, ADR-039.`

---

## What does NOT belong here

- **Rationale.** It lives in `decisions.md` and the proposal. A requirement cites; it does not argue.
- **The drop order.** `Final_Proposal.md` §12 owns it. Restating it here creates a second copy that
  will drift, and the drop order is exactly the thing that must not drift under schedule pressure.
- **Deliverables.** `Final_Proposal.md` §13 owns them.
- **Schedule.** `super-plan.md` owns it.
