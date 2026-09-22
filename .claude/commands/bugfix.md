---
description: Open a task for something that is wrong — defaults to scope S
argument-hint: <slug> [what is broken]
---

Open a **bugfix** task. Run `/task $1 S $2`.

**Before choosing S, establish that you know the cause.** A bugfix whose cause is unknown is an
investigation wearing a fix's clothes, and it is the single most common way a "one-line change"
turns into a seam change halfway through. If you cannot name the cause in one sentence, run
`/investigate` instead and come back.

Raise the scope, without asking:

- the cause is in `reuse/`, at a seam, or in anything measured → **L**
- the fix changes behaviour beyond restoring what was intended → **M**, because that is a feature
- **a test would have to change** → stop. Tests are immutable unless an RCA proves staleness and
  the human confirms (`.docs/ai/rules.md`, `/rca`). A failing test that is "obviously wrong" has
  been right often enough that the rule exists

**Write the failing case first**, as a test, before the fix — then the fix has a witness and the
bug cannot come back silently.
