---
description: Open a task with a durable design trail under docs/work/<YYYY-MM-DD>-<slug>/
argument-hint: <task-slug> <L|M|S> [one-line description]
---

Open task `$1` at scope `$2` and create its trail. **Do not write any source code in this command.**

Prefer the specific openers where one fits — `/feature`, `/bugfix`, `/refactor`, `/investigate`.
They pick a sensible default scope and carry the rules that actually catch mistakes for that kind
of work. Use `/task` when none of them fits.

## Scope — decide this first, and honestly

The gate calibrates on scope (`.claude/hooks/gate-check.sh`), so this letter decides how much
design work is required before source edits unlock. **If you are between two, take the larger.**

| Scope | Requires | Use when |
| :---: | :--- | :--- |
| **L** | spec → impact → **design** → **opus design-review** → plan | A frozen document, `interfaces.md`, the `.proto`, `reuse/`, or anything measured. Where a silent error costs the study rather than an afternoon |
| **M** | spec → impact → plan | Ordinary code: a package, a handler, a script |
| **S** | spec (one paragraph) | Tests, docs, comments, a one-line fix |

Write the letter to the trail's `SCOPE` (step 1 below). **Every scope still ends at `/approve implementation`** —
S is cheap because it needs one document, not because it skips the human.

## The trail

1. **Create `docs/work/<YYYY-MM-DD>-$1/`**, where the date is today's (`date +%F`) — the day the
   task opens, never changed afterwards, so `ls docs/work` reads in the order work began. If that
   folder already exists, stop and say so. Write `SCOPE`, and set `.claude/state/active-task` to
   the **full folder name** (`<YYYY-MM-DD>-$1`), not the bare slug: every `docs/work/<task>/` path
   in the other commands and in `lib.sh` resolves through it.

2. **`spec.md`** — all scopes:
   - The change in one sentence.
   - Which **phase** it serves, and which super-plan item or exit criterion (`docs/super-plan.md`,
     in `docs/super-plan.md`).
   - Which `FR-xx` / `NFR-xx` / `RR-xx` it discharges, once `docs/contracts/requirements.md` is filled.
   - Acceptance: how we will know it is done, as a check that can be run.
   - Out of scope: what this explicitly does not do.

3. **`impact.md`** — scopes **L** and **M**. Delegate to the `impact-analyst` subagent:
   - Which packages does this touch? Does it respect `docs/architecture.md`'s module boundaries?
   - **Does it touch a frozen value or a measured path?** If yes, say **which prior runs it
     invalidates** — that sentence is the point, and nothing enforces it automatically any more.
   - Does it reinstate anything from `Final_Proposal.md` §12's do-not-reinstate list?
   - Does it add a dependency? (needs sign-off — rules #9)
   - Does it change a **contract** (`interfaces.md` surfaces)? → the contract phase becomes required.
   - Does it change **what or how anything is measured**? → the experiment phase becomes required.

4. **`design.md`** — scope **L** only. Sequence or activity diagram, function contracts, failure
   modes, edge cases, and **the unknowns that still need verifying**. Name what you do not know;
   a design that lists no unknowns has not been thought about hard enough.

5. **`review.md`** — scope **L** only. Delegate to the `design-reviewer` subagent (opus). It
   answers "is this design sound, and what is the hidden risk" — which is a different question
   from `impact-analyst`'s "what does this touch". Record its findings and their resolutions.

6. **`plan.md`** — scopes **L** and **M**. An ordered, checkbox implementation plan. Smallest
   change that satisfies the spec; each step independently verifiable.

7. **`approvals.md`** — all scopes. Start the ledger with the required phases, all unchecked:

   ```
   | Phase          | Required | Approved | When | ADR |
   | :---           | :---     | :---     | :--- | :--- |
   | impact         | L, M     |          |      |     |
   | contract       | if §B/§D |          |      |     |
   | experiment     | if measured |       |      |     |
   | implementation | always   |          |      |     |
   ```

   Nothing reads this file automatically since 2026-09-22 — it is the human record of what was
   reviewed, and it is the only such record now that the hooks no longer gate.

Report the trail folder, the scope and why that scope, and the outstanding phases. Then stop.
