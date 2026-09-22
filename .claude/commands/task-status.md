---
description: Where am I — phase, active task, scope, gate state, outstanding phases
---

Report current state compactly. No preamble, no advice unless something is blocking.

1. **Phase** — the number from `.claude/state/phase` (or "UNSET"), and its exit criterion
   verbatim from the phase plan. Whether it is met: check it; if unverified, say
   "unverified" and name what would settle it, rather than guessing.

2. **Active task** from `.claude/state/active-task`, or "none". If one is active:
   - its **scope** from `docs/work/<task>/SCOPE` (L / M / S), and what that scope requires
   - which required documents exist and which do not — this is exactly what the gate checks
   - whether `READY_TO_IMPLEMENT` exists (implementation LOCKED / UNLOCKED)
   - the approvals table from `approvals.md`
   - unchecked steps remaining in `plan.md`; unresolved findings in `review.md`

3. **Standing blockers that outrank the phase** — `docs/super-plan.md` "Standing constraints".
   Name F1 explicitly if it is still open: no admission-control number is citable while it is.

4. **Uncommitted work** — `git status --short`, summarised as counts, never a file dump.

End with the single most useful next action. One line.
