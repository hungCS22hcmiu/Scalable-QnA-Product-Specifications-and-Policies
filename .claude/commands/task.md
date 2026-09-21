---
description: Open a task with a durable design trail under .docs/work/<slug>/
argument-hint: <task-slug> [one-line description]
---

Open task `$1` and create its trail. **Do not write any source code in this command.**

1. **Create `.docs/work/$1/`** and set `.claude/state/active-task` to `$1`.

2. **`spec.md`** — what and why:
   - The change in one sentence.
   - Which week and which `docs/time_line.md` task it serves.
   - Acceptance: how we will know it is done (tie to the week's Done-when where possible).
   - Out of scope: what this explicitly does not do.

3. **`impact.md`** — delegate to the `impact-analyst` subagent. It must answer:
   - Which packages does this touch? Does it respect the layering in `.docs/ai/architecture-guardrails.md`?
   - **Does it touch a frozen artifact?** If yes: which ADR, and **which prior runs it invalidates**.
   - Does it reinstate anything from `Final_Proposal.md` §12's do-not-reinstate list?
   - Does it add a dependency? (needs sign-off — rules #9)
   - Does it change a **contract** (`interfaces.md` surfaces)? → the contract phase becomes required.
   - Does it change **what or how anything is measured**? → the experiment phase becomes required.

4. **`plan.md`** — an ordered, checkbox implementation plan. Smallest change that satisfies the spec.
   Each step should be independently verifiable.

5. **`approvals.md`** — start the ledger with the required phases from step 3, all unchecked:

   ```
   | Phase          | Required | Approved | When | ADR |
   | impact         | yes      | no       |      |     |
   | contract       | ?        | no       |      |     |
   | experiment     | ?        | no       |      |     |
   | implementation | yes      | no       |      |     |
   ```

6. **Report** the required phases and the exact `/approve` calls needed to unlock implementation.

**Gate reminder:** in W5–W7 the phase gate is lightweight, so source edits are allowed without
`READY_TO_IMPLEMENT` — but the frozen-value tripwire is armed regardless. From W8 the gate is hard.
