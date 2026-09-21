---
description: Human approval of a design phase — only `/approve implementation` unlocks source edits
argument-hint: impact | contract | experiment | implementation [ADR-NNN]
---

Record human approval of phase **$1** for the active task.

**This command represents a human decision. Never invoke it on your own initiative, and never approve a
phase the human has not actually reviewed.** If asked to "just approve everything", refuse and explain
that the gate exists because frozen-value changes fail silently.

1. Read `.claude/state/active-task`. If empty, stop — there is nothing to approve.

2. **Verify the phase artifact exists and is non-trivial:**
   - `impact` → `.docs/work/<task>/impact.md` with the frozen-artifact question actually answered
   - `contract` → the `interfaces.md` diff is described and both sides of the seam are accounted for
   - `experiment` → the measurement change is described against `experiment-protocol.md` §4
   - `implementation` → **all other required phases already approved**

   If an artifact is missing or empty, refuse and say which.

3. **If the task touches a frozen value**, an ADR is mandatory. Record `ADR-NNN` (from `$2`) in
   `approvals.md`. Without it the frozen-guard hook will keep blocking, and that is correct behaviour —
   do not work around it by editing the hook or the pattern file.

4. **Update `approvals.md`**: set Approved=yes, the date, and the ADR if any.

5. **Only for `implementation`**: write `.docs/work/<task>/READY_TO_IMPLEMENT` containing the approval
   date and the list of approved phases. This is the marker `gate-check.sh` reads.

6. Report which phases remain, or that implementation is now unlocked.
