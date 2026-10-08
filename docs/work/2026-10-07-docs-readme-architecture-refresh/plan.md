# Plan / outcome — docs-readme-architecture-refresh

Scope S needs only `spec.md`; this file exists to carry the `/done` outcome record.

**Closed:** 2026-10-07

## What shipped

- `README.md` — Phase 1 → met, Phase 2 → current; Status states what is *served*
  (`similarity ∧ namespace`, F-K open, support gate unbuilt) and what is not built (C2, any citable
  result); invalidation reworded from present tense to "design / not built"; Gateway stack row
  corrected (no `x/sync`, hand-rolled coalescer, no `atomic.Pointer` yet); Load-testing row aligned with
  ADR-001; new Documents section; layout and "Running it" completed.
- `docs/architecture.md` — §1 tree reconciled with the disk (incl. `coalesce/`, `ragpb/`, `decisions.md`,
  `rag/` modules, `experiments/*`, `data/*`; week labels removed); §2 gains the observed import graph
  beside the request order, and a `coalesce/` boundary row; §3 states what the Tier-2 row serves today;
  §4 names all 23 `make` targets; §5 inventory re-dated 2026-10-07 (`embed` is untested; `httpapi` is
  tested).

## Acceptance — what was actually run

| Check | Result |
| :--- | :--- |
| Every `make help` target appears in architecture.md §4 | pass (23 of 23) |
| Every `make X` named in either file is a target | pass (one hit, "make any decision", is prose) |
| Every dir/module under `gateway/internal`, `rag/src/rag`, `experiments` is in the §1 tree | pass |
| `go list` over `gateway/internal/*` reproduces §2's import statement | pass |
| Every `ADR-NNN` cited resolves to an entry that says what the sentence claims | pass (001, 002, 003, 004, 005; read against `decisions.md`) |
| `make check` — stale-schedule sweep | clean |
| `git diff` touches only `README.md` and `docs/architecture.md` | pass |

**Not run, by the author's decision:** `/verify` and `/ai-review` (see `approvals.md`). Nothing outside
two `.md` files changed, so there was no build, test or lint surface for either to cover.

## Scope honesty

S was honest. No frozen document, seam, `.proto`, `reuse/` or measured path was touched; `interfaces.md`
was not edited and no version bumped. One thing worth stating rather than closing quietly:
`architecture.md` is the **module-boundary authority**, and this edit added a `coalesce/` row to its
"Must never" table ("hold a permit of its own"). It restates what the code and `admission/`'s sole-
chokepoint rule already imply (`coalesce` imports nothing, so it cannot call `admission`); it adds no
constraint the code does not already meet. If the author reads boundary edits as L, that row is the one
to review.

## Deferred / follow-up

- **`CLAUDE.md` is stale and was out of scope:** `interfaces.md` "at v0.9" (it is v0.12); the
  `singleflight` / semaphore / `atomic.Pointer` claims (`:129-134`) that the README row no longer makes.
  → a one-line `/task` at scope S.
- **README now states "Phase 1 exit criterion met 2026-10-07"**, mirroring `super-plan.md`'s own Progress
  note. This task did **not** re-run Phase 1's exit clauses by hand; the plan says they are re-run when
  the phase is closed. Until then the README line is only as strong as that note.
- `data/README.md` still carries week labels (`W5`, `W8` in its table) — untouched here. (Read from the
  file earlier in the session; not re-grepped at close, the check was denied.)

## Contract / frozen-value check

None changed. No `interfaces.md` bump required. `approvals.md` records **Invalidates: nothing** (prose
only; no `run_id` exists).

## Phase exit

This task served no Phase 2 exit clause and did not complete the phase: the support gate is unbuilt, so
the Phase 2 `**Exit:**` line was not run. No `super-plan.md` item's "Done when" was passed, so nothing
was marked.
