---
description: Start or resume the current thesis week — restate the target, verify last week closed, open the worklog
---

Orient the session for the current week. Do this in order and report concisely.

1. **Resolve the week.** `bash .claude/hooks/lib.sh` is not runnable directly — instead compute:
   W1 Monday is `2026-07-13`, so `week = ((today - 2026-07-13) / 7) + 1`. State the week number and
   its date range. Cross-check against the phase table in `docs/time_line.md`.

2. **Read this week's row** in `docs/time_line.md` (Phase 1 table for W5–W7, Phase 2 for W8–W22).
   Report verbatim: **Focus**, **Key tasks**, and **Done when**. Do not paraphrase "Done when" — it is
   the binary exit test.

3. **Verify the previous week actually closed.** Open `docs/worklog/W<prev>.md`. If its exit test is not
   recorded as PASS, say so plainly and state that this week begins by closing it — per Ground Rule 5 in
   `docs/time_line.md`, next week starts by meeting last week's gate, not by starting new work.

4. **Open the worklog** for this week at `docs/worklog/W<NN>.md` if it does not exist, using the template
   in `docs/worklog/README.md`. Fill in the goal and Done-when from step 2.

5. **Check the blocking gates for this week specifically:**
   - W5 → is the feasibility spike done (ADR-017 frozen)? Are ADR-003 and ADR-014 still Open?
   - W8 → has the corpus sensitivity gate run before `v1` was hashed?
   - W10 → are the `[verify]` markers in `Final_Proposal.md` §10 still outstanding?
   Report any that are unmet — they block the rest of the week.

6. **Seed a task list** for the week's key tasks, ordered so blocking items come first.

Keep the output short: week, dates, focus, tasks, Done-when, gate status. No preamble.
