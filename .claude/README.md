# `.claude/` — workflow automation

Tooling is **tracked**; only `settings.local.json`, `state/` and `scheduled_tasks.lock` are ignored. The
workflow is part of the thesis's reproducibility story, not personal config.

> Tracked in fact as well as in claim only since **2026-09-21**. Until then `.gitignore` ignored this
> whole directory and `.docs/` with it, so this sentence and `.docs/README.md`'s "It is committed" were
> both false — see `Pre-thesis_Sweeping.md` §4.5.

## The rhythm

Weeks were removed **2026-09-21** (`Pre-thesis_Sweeping.md` #4). The schedule is **phases with
binary exit criteria**, and the amount of process a change must pay is set by **its scope**, not
by the date. A one-line fix late in the schedule was paying ceremony it never needed; a seam
change early in the schedule was paying none when it always did.

```
starting    /phase          what phase, what closes it, how far off it is
            /phase <n>      switch — reports whether the phase being left actually closed
during      /feature <slug> new behaviour            → scope M
            /bugfix <slug>  something is wrong       → scope S
            /refactor <slug> same behaviour, better  → scope M
            /investigate <slug> answer a question, write no code
            /task <slug> <L|M|S>   when none of those fit
            /approve …      human unlock, phase by phase — required at EVERY scope
            /verify         build + test + lint
            /ai-review      subagents check the diff against the written rules
            /rca            only after /verify fails twice
            /done           close, re-lock
end of day  /log            hours, what happened, blockers → docs/worklog/journal.md
phase end   /gate           run the exit criterion for real; PASS or FAIL
anytime     /task-status · /adr · /consistency · /spike (spent — see its header)
```

## The scope ladder

Written to `.docs/work/<slug>/SCOPE` by the opener. `gate-check.sh` reads it.

| Scope | Design documents required first | Use when |
| :---: | :--- | :--- |
| **L** | spec → impact → **design** → **opus design-review** → plan | A frozen document, `interfaces.md`, the `.proto`, `reuse/`, or anything measured |
| **M** | spec → impact → plan | Ordinary code: a package, a handler, a script |
| **S** | spec (one paragraph) | Tests, docs, comments, a one-line fix |

Three things make this a ladder rather than three ways out:

- **Every scope ends at `/approve implementation`.** S is cheap because it needs one document
  before that approval, not because it skips the human.
- **An unset scope blocks.** It is not defaulted to S — an unlabelled task would otherwise take
  the cheapest path automatically, which is the hole three tiers invite.
- **`frozen-guard.sh` is armed at every scope**, unchanged. It is not part of the ladder.

When you are between two scopes, take the larger. `/done` asks whether the scope was honest, and a
scope that turned out wrong is a finding about the ladder worth recording.

## The gate, and why it is aimed where it is

In a normal backend repo a phase gate stops unreviewed architectural drift. Here the failure mode is
different and quieter: **changing a frozen experimental value produces no error and no visible bug**, and
silently invalidates every measurement taken before it. You find out in W20 when the numbers do not
reconcile. So the enforcement is aimed at frozen artifacts first.

| Layer | When | What it does |
| :--- | :--- | :--- |
| `frozen-guard.sh` | **always, at every scope** | Blocks edits that *configure* a frozen value, edits to the three frozen docs, and writes to `results/*/raw/`. Releases when the active task's `approvals.md` cites an ADR |
| `gate-check.sh` | **always, calibrated by scope** | Blocks source edits until the task's scope has produced its design documents **and** `/approve implementation` wrote `READY_TO_IMPLEMENT` |

The phase is explicit state (`.claude/state/phase`), not computed from the calendar: a phase ends
when its exit criterion passes, which is a binary test and not a date.

## Design notes worth knowing before you change a hook

- **`frozen-guard` distinguishes configuring from discussing.** `num_ctx = 8192` blocks;
  `func F(top_k int)`, a proto field number, a comment, or a grep pattern does not. Patterns in
  `.docs/ai/frozen-values.txt` must match an **assignment**. A guard that cries wolf gets disabled — every
  false positive is a real cost.
- **`.claude/*`, `.docs/*`, `docs/*`, `*.md`, `*.proto` and the `Makefile` are exempt from the value
  scan.** They describe values rather than setting them. `.claude/*` is exempt *first*, deliberately: a
  self-referential guard with no bootstrap exemption locks its own source and wedges the repo.
- **The hook payload is read once at source time.** Reading it lazily inside a function fails silently,
  because command substitution runs in a subshell and the second read gets an already-consumed stdin.
- **A malformed payload blocks rather than allows.** Failing open on a guarded path is worse than a
  false alarm.

## Commands

| Command | Purpose |
| :--- | :--- |
| `/phase [n]` | Orient in the current phase — its exit criterion, how far off it is, what is open. With `n`, switch, reporting first whether the phase being left actually closed |
| `/feature <slug>` | Open a task for new behaviour — scope M, raised to L at a seam or in `reuse/` |
| `/bugfix <slug>` | Open a task for something wrong — scope S, and it refuses a fix whose cause is unknown |
| `/refactor <slug>` | Same behaviour, better structure — scope M; no test may change, golden values must reproduce |
| `/investigate <slug>` | Answer a question and produce evidence. Writes no source, ever |
| `/task <slug> <L\|M\|S>` | Open a task with a durable design trail, when none of the four fits |
| `/approve <phase>` | Human approval of a design phase — only `/approve implementation` unlocks source edits |
| `/verify` | Build + test + lint; reports SKIPPED for absent tooling, never a vacuous pass |
| `/ai-review` | Review the working diff against written checklists via the review subagents |
| `/rca` | Structured root-cause analysis, invoked only after `/verify` fails twice |
| `/done` | Close the active task, re-lock the gate, record the outcome |
| `/log [note]` | Append a dated entry to `docs/worklog/journal.md` |
| `/gate [phase]` | Run that phase's exit criterion concretely — PASS or FAIL, never a self-assessment |
| `/task-status` | Report current state compactly — phase, active task, scope, gate state, outstanding phases |
| `/adr [title]` | Record an architecturally significant decision in `docs/decisions.md` |
| `/consistency` | Sweep the frozen documents for drift, stale references, reinstated scope |
| `/spike` | **Spent.** The envelope is frozen (ADR-017) and re-running it re-freezes nothing. Kept because the method is what the design chapter describes, and a hardware change would need it run again — under a new ADR |

## Subagents

| Agent | Model | Tools | Purpose |
| :--- | :--- | :--- | :--- |
| `impact-analyst` | opus | Read, Grep, Glob, Bash | Pre-implementation blast-radius analysis — which packages/frozen artifacts/prior runs a change would invalidate; writes `impact.md` |
| `contract-reviewer` | sonnet | Read, Grep, Glob, Bash | Reviews diffs touching the Go↔Python seam, Redis schemas, wire fields, or chunk IDs against `interfaces.md` |
| `experiment-reviewer` | sonnet | Read, Grep, Glob, Bash | Reviews diffs touching measurement/metrics/judging/thresholds against the frozen experiment protocol, incl. research-integrity check |
| `rca-analyst` | opus | Read, Grep, Glob, Bash | Structured root-cause analysis after two failed `/verify` attempts; treats tests as immutable unless it can prove staleness |
| `design-reviewer` | opus | Read, Grep, Glob, Bash | **Scope-L only, before any code.** Is the design sound, and what is the hidden risk — a different question from `impact-analyst`'s blast radius. Ranks silent failure paths first, because this project's characteristic bug raises no error |

## Escape hatches

- Legitimate frozen change → `/adr`, cite it in `approvals.md`, retry. **This is the intended path.**
- Emergency → comment the hook out of `settings.json`, do the work, put it back, and record why in the
  worklog. Do not edit `frozen-values.txt` to dodge a specific block — that removes the guard for
  everyone, permanently, and silently.
- Test a hook by hand:
  ```bash
  jq -nc --arg p "$PWD/rag/x.py" --arg c 'num_ctx = 8192' \
    '{tool_name:"Write",tool_input:{file_path:$p,content:$c}}' | .claude/hooks/frozen-guard.sh; echo $?
  ```
  Exit 2 = blocked, 0 = allowed. Test the scope ladder by writing `L`, `M` or `S` to the active
  task's `SCOPE` file and re-running; `THESIS_PHASE_FILE` points `current_phase()` elsewhere.

## Where the rules live

`.docs/ai/rules.md` holds the ten trip-wires; each cites its governing section in `docs/` rather than
restating it. Review subagents Read it at review time, so there is one place to update. The engineering
standards suite is deliberately deferred to W6, to be derived from real Go code rather than invented
against an empty repo.
