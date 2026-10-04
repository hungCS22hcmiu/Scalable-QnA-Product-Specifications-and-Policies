---
description: Review the working diff against the written checklists using the review subagents
---

Review the current diff. **Reviewers read the rules docs at review time — do not paste a checklist into
the prompt.** Point them at the files so there is one place to update.

1. **Scope the diff:** `git diff` plus untracked files under `gateway/ rag/ contracts/ experiments/`.
   If the diff is empty, say so and stop.

2. **Route to reviewers by what the diff touches** (run applicable ones in parallel):

   | Diff touches | Agent | Reads |
   | :--- | :--- | :--- |
   | `contracts/`, `interfaces.md` surfaces, Redis schema, wire fields | `contract-reviewer` | `docs/contracts/interfaces.md`, `docs/architecture.md` |
   | a scope-L design, before implementation | `design-reviewer` | the task trail, `docs/super-plan.md` |

   If neither applies, run `contract-reviewer` in a general pass over `docs/architecture.md`.

3. **Findings must be actionable.** Each one names file, line, and the rule or doc section violated.
   Reject style opinions. Report only what would **fail silently** or **produce a wrong number** — those
   are this repo's real failure modes.

4. **Write results to `docs/work/<task>/review.md`**, most severe first, each marked
   `CONFIRMED` or `PLAUSIBLE`.

5. **Resolve each finding** before `/done`: fix it, or record why it is accepted. An unresolved finding
   blocks `/done`.

Pay particular attention to rules #1 (frozen values), #5 (eviction regions), #6 (provenance fields) and
#10 (never tune to make a headline work) — all four fail without any error.
