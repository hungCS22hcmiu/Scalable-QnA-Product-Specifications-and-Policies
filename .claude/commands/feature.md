---
description: Open a task for new behaviour — defaults to scope M
argument-hint: <slug> [one-line description]
---

Open a **feature** task: behaviour that does not exist yet.

Run `/task $1 M $2`, then adjust the scope **upward** if any of these hold — do not ask, check:

- it changes `docs/interfaces.md`, `contracts/rag/v1/rag.proto`, or any Go↔Python wire shape → **L**
- it touches `gateway/internal/reuse/` → **L**. The reuse decision is the research contribution;
  an error there is a wrong number, not a wrong screen
- it changes what or how anything is measured (`telemetry/`, `experiments/`) → **L**
- it needs a frozen value to change → **L**, and `/adr` comes first

A feature is the default case for M: new code, existing seams, existing measurements.

State which scope you chose and why, in one line, before writing anything.
