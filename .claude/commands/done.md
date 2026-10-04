---
description: Close the active task, re-lock the gate, and record the outcome
---

Close the active task. Refuse to close if any check below fails — say which and stop.

1. **Preconditions:**
   - `/verify` passed (SKIPPED targets are acceptable and must be listed **by name**; a target
     that ran and failed is not a SKIP).
   - `/ai-review` findings are all resolved or explicitly accepted in `review.md`.
   - Every step in `plan.md` is checked off, or the unchecked ones are explained.
   - **The scope was honest.** If the work turned out to touch a frozen document, a seam, or
     `reuse/` while the task was opened at M or S, say so here rather than closing quietly — a
     scope that was wrong is a finding about the ladder, and the ladder is only as good as this
     check.

2. **Record the outcome** in `docs/work/<task>/plan.md`: what shipped, what was deferred, and any
   follow-up worth a new task.

3. **Did this change a frozen value or a contract?** If yes, confirm `docs/contracts/interfaces.md`
   was version-bumped, and that `approvals.md` names **which prior runs are invalidated** — that
   sentence is the whole point of the record, and nothing else captures it.

4. **Re-lock:** delete `docs/work/<task>/READY_TO_IMPLEMENT` and clear `.claude/state/active-task`.
   Leave `SCOPE` in place — the trail should keep saying what rigor this change was held to.
   The gate returns to blocking source edits immediately.

5. **Suggest a commit** — do not run it unless asked:
   ```
   <what changed>

   <why, one or two lines>
   Task: docs/work/<task>/  (scope <L|M|S>)
   ```

6. **Check the phase exit criterion.** If this task completed it, say so — and run the
   `**Exit:**` line from `docs/super-plan.md` concretely rather than asserting it. There is no
   command for this since 2026-09-22; the criterion names a command or an artefact, so run that.

7. **Mark the item in `docs/super-plan.md`**, if this task passed an item's "Done when" test. Its
   "Unblocked when" cell becomes `✅ Done <date> — <ADR>, trail docs/work/<task>/`, every row that
   lists it as a blocker marks it `✅`, and the phase's **Progress** line is updated. Do not mark
   an item whose test was not actually run.
