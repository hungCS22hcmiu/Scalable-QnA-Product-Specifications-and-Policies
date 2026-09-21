---
description: Close the active task, re-lock the gate, and record the outcome
---

Close the active task. Refuse to close if any check below fails — say which and stop.

1. **Preconditions:**
   - `/verify` passed (SKIPPED targets are acceptable and must be listed).
   - `/ai-review` findings are all resolved or explicitly accepted in `review.md`.
   - Every step in `plan.md` is checked off, or the unchecked ones are explained.

2. **Record the outcome** in `.docs/work/<task>/plan.md`: what shipped, what was deferred, and any
   follow-up worth a new task.

3. **Did this change a frozen value or a contract?** If yes, confirm the ADR exists in `docs/decisions.md`
   and that `interfaces.md` was version-bumped. If a frozen value changed, confirm the ADR names **which
   prior runs are invalidated** — that sentence is the whole point of the record.

4. **Update this week's worklog** (`docs/worklog/W<NN>.md`): what happened, decisions, blockers.

5. **Re-lock:** delete `.docs/work/<task>/READY_TO_IMPLEMENT` and clear `.claude/state/active-task`.
   The gate returns to blocking (from W8; in the runway it was already lightweight).

6. **Suggest a commit** — do not run it unless asked:
   ```
   W<NN>: <what changed>

   <why, one or two lines>
   Task: .docs/work/<task>/
   ```

7. **Check the weekly exit test.** If this task completed the week's Done-when, say so and suggest
   `/gate` to verify it concretely rather than asserting it.
