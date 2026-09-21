---
description: Orient in the current phase — what closes it, what is open, what is next
argument-hint: [phase-number to switch to]
---

Replaces `/week`. Weeks were removed 2026-09-21 (`Pre-thesis_Sweeping.md` #4): a week number
said what the date was, never what you were trying to finish. A phase ends when its **exit
criterion** passes, which is a binary test (`time_line.md` Ground Rules 5).

**If `$1` is given**, switch to that phase: write it to `.claude/state/phase`, and **before doing
so** report whether the phase being left actually met its exit criterion. Do not switch silently —
a phase left open is the thing this command exists to make visible. If it was not met, say so and
ask whether to switch anyway.

**With no argument**, orient:

1. **State the phase and its exit criterion**, read from the phase plan — `docs/super-plan.md`
   once #3 is filled, `docs/time_line.md` until then. Quote the criterion; do not paraphrase it.
2. **Say plainly how far from that criterion the repo is.** Check it, do not assume: if the
   criterion names a frozen corpus, look for the snapshot hash; if it names a recorded number,
   look for the run directory. "In progress" is not an answer — name what is missing.
3. **Report the open task**, its scope, and which design documents its scope still owes
   (`/task-status` has the detail; summarise here).
4. **Report standing blockers** that outrank the phase — `Pre-thesis_Sweeping.md` §0.2 and
   `super-plan.md` "Standing constraints". F1 in particular: no admission-control number is
   citable while it is open.
5. **Check the journal** — if `docs/worklog/journal.md` has no entry in the last few working
   days, say so.

Do not open a task, write code, or edit `docs/` from this command. It orients; it does not act.
