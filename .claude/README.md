# `.claude/` — workflow automation

Tooling is **tracked**; only `settings.local.json`, `state/` and `scheduled_tasks.lock` are ignored.
The workflow is part of the thesis's reproducibility story, not personal config.

> **Consolidated 2026-09-22.** Task trails live in `docs/work/<slug>/`. The two blocking hooks —
> `frozen-guard.sh` and `gate-check.sh` — were removed in the same pass, because both read files
> that no longer exist and a guard that fails open silently is worse than no guard: it still reads
> as protection. **Rigor is now a convention these commands describe, not a
> mechanism anything enforces.** Nothing will stop you changing a frozen value; writing down what
> a change invalidates is therefore more important than it was, not less.

## The rhythm

Weeks were removed **2026-09-21**. The schedule is **phases with binary exit criteria**, and the
amount of process a change pays is set by **its scope**, not by the date. A one-line fix late in
the schedule was paying ceremony it never needed; a seam change early was paying none when it
always did.

```
starting    /phase          what phase, what closes it, how far off it is
            /phase <n>      switch — reports whether the phase being left actually closed
during      /feature <slug> new behaviour            → scope M
            /bugfix <slug>  something is wrong       → scope S
            /refactor <slug> same behaviour, better  → scope M
            /investigate <slug> answer a question, write no code
            /task <slug> <L|M|S>   when none of those fit
            /approve …      human sign-off, phase by phase — expected at EVERY scope
            /verify         build + test + lint
            /ai-review      subagents check the diff against the written rules
            /rca            only after /verify fails twice
            /done           close the task, record the outcome
anytime     /task-status
```

## The scope ladder

Written to `docs/work/<slug>/SCOPE` by the opener.

| Scope | Design documents first | Use when |
| :---: | :--- | :--- |
| **L** | spec → impact → **design** → **opus design-review** → plan | `docs/contracts/interfaces.md`, the `.proto`, `reuse/`, or anything measured |
| **M** | spec → impact → plan | Ordinary code: a package, a handler, a script |
| **S** | spec (one paragraph) | Tests, docs, comments, a one-line fix |

- **Every scope ends at `/approve implementation`.** S is cheap because it needs one document
  before that sign-off, not because it skips the human.
- **An unset scope is not S.** An unlabelled task taking the cheapest path by default is the hole
  three tiers invite. The session banner reports `scope UNSET` so it stays visible.
- **Between two scopes, take the larger.** `/done` asks whether the scope was honest; a scope that
  turned out wrong is a finding about the ladder worth recording.

## What the hooks still do

All three are advisory. None blocks.

| Hook | When | What it does |
| :--- | :--- | :--- |
| `inject-context.sh` | every prompt | Prints the phase, its `**Exit:**` line from `docs/super-plan.md`, and the active task's scope and lock state |
| `done-check.sh` | end of turn | Reminds you of an unset phase or an open task. Never blocks |
| `format-lint.sh` | after an edit | `gofmt` / `ruff` on what was just written; reminds you to `make proto` when the `.proto` changed |

The phase is explicit state (`.claude/state/phase`), not computed from the calendar: a phase ends
when its exit criterion passes, which is a binary test and not a date. Run that criterion by hand
— each one names a command or an artefact, never a judgement.

## The failure mode this workflow is shaped around

In a normal backend repo, process stops unreviewed architectural drift. Here the failure mode is
quieter: **changing a frozen experimental value produces no error and no visible bug**, and
silently invalidates every measurement taken before it. You find out at write-up time, when the
numbers do not reconcile and months of runs are void.

That is why `impact.md` asks *which prior runs does this invalidate* and why `/done` refuses to
close quietly on a scope that turned out wrong. Since 2026-09-22 those questions are the **only**
line of defence — no hook checks them.

## Commands

| Command | Purpose |
| :--- | :--- |
| `/phase [n]` | Orient in the current phase — its exit criterion, how far off it is, what is open. With `n`, switch, reporting first whether the phase being left actually closed |
| `/feature <slug>` | Open a task for new behaviour — scope M, raised to L at a seam or in `reuse/` |
| `/bugfix <slug>` | Open a task for something wrong — scope S, and it refuses a fix whose cause is unknown |
| `/refactor <slug>` | Same behaviour, better structure — scope M; no test may change, golden values must reproduce |
| `/investigate <slug>` | Answer a question and produce evidence. Writes no source, ever |
| `/task <slug> <L\|M\|S>` | Open a task with a durable design trail, when none of the four fits |
| `/approve <phase>` | Human sign-off on a design phase; `/approve implementation` records that code may start |
| `/verify` | Build + test + lint; reports SKIPPED for absent tooling, never a vacuous pass |
| `/ai-review` | Review the working diff against written checklists via the review subagents |
| `/rca` | Structured root-cause analysis, invoked only after `/verify` fails twice |
| `/done` | Close the active task and record the outcome |
| `/task-status` | Report current state compactly — phase, active task, scope, outstanding phases |

## Subagents

| Agent | Model | Purpose |
| :--- | :--- | :--- |
| `impact-analyst` | opus | Pre-implementation blast-radius — which packages and which prior runs a change would invalidate; writes `impact.md` |
| `design-reviewer` | opus | **Scope-L only, before any code.** Is the design sound, and what is the hidden risk — a different question from blast radius. Ranks silent failure paths first, because this project's characteristic bug raises no error |
| `contract-reviewer` | sonnet | Reviews diffs touching the Go↔Python seam, Redis schemas, wire fields, or chunk IDs against `docs/contracts/interfaces.md` |
| `rca-analyst` | opus | Root-cause analysis after two failed `/verify` attempts; treats tests as immutable unless it can prove staleness |

## Testing a hook by hand

```bash
echo '{}' | .claude/hooks/inject-context.sh    # the session banner
echo '{}' | .claude/hooks/done-check.sh        # the end-of-turn checklist
```

`THESIS_PHASE_FILE` points `current_phase()` at a different file. Scope is read from the active
task's `SCOPE`, so writing `L`, `M` or `S` there changes what the banner reports.
