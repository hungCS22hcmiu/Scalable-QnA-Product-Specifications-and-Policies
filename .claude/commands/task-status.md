---
description: Where am I — week, active task, gate state, outstanding phases
---

Report current state compactly. No preamble, no advice unless something is blocking.

1. **Week** — number, date range, phase (runway ≤W7 / thesis ≥W8), and the gate mode that implies.

2. **This week's Done-when**, verbatim from `docs/time_line.md`, and whether it is met (check the
   worklog; if unrecorded, say "unverified — run `/gate`").

3. **Active task** from `.claude/state/active-task`, or "none". If one is active:
   - the approvals table from `.docs/work/<task>/approvals.md`
   - whether `READY_TO_IMPLEMENT` exists (implementation LOCKED / UNLOCKED)
   - unchecked steps remaining in `plan.md`
   - unresolved findings in `review.md`

4. **Open blocking decisions** — scan `docs/decisions.md` for rows marked **Open** whose decide-by week
   is ≤ the current week. These block work; list them.

5. **Uncommitted work** — `git status --short`, summarized (counts, not a file dump).

End with the single most useful next action. One line.
