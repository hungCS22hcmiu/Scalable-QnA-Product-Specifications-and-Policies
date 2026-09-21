# `.claude/` — workflow automation

Tooling is **tracked**; only `settings.local.json`, `state/` and `scheduled_tasks.lock` are ignored. The
workflow is part of the thesis's reproducibility story, not personal config.

> Tracked in fact as well as in claim only since **2026-09-21**. Until then `.gitignore` ignored this
> whole directory and `.docs/` with it, so this sentence and `.docs/README.md`'s "It is committed" were
> both false — see `Pre-thesis_Sweeping.md` §4.5.

## The weekly rhythm

```
Monday      /week          what is due, did last week close, open the worklog
during      /task <slug>   open a design trail   (W8+: required before source edits)
            /approve …     human unlock, phase by phase
            /verify        build + test + lint
            /ai-review     subagents check the diff against the written rules
            /rca           only after /verify fails twice
            /done          close, re-lock
end of day  /log           hours, what happened, blockers
Sunday      /gate          run the exit test for real; PASS or FAIL
anytime     /task-status · /adr · /consistency · /spike (W5)
```

## The gate, and why it is aimed where it is

In a normal backend repo a phase gate stops unreviewed architectural drift. Here the failure mode is
different and quieter: **changing a frozen experimental value produces no error and no visible bug**, and
silently invalidates every measurement taken before it. You find out in W20 when the numbers do not
reconcile. So the enforcement is aimed at frozen artifacts first.

| Layer | When | What it does |
| :--- | :--- | :--- |
| `frozen-guard.sh` | **always, including the runway** | Blocks edits that *configure* a frozen value, edits to the three frozen docs, and writes to `results/*/raw/`. Releases when the active task's `approvals.md` cites an ADR |
| `gate-check.sh` | **W8 onward** | Blocks source edits until `/approve implementation` writes `READY_TO_IMPLEMENT`. Lightweight in W5–W7 (ADR-020) |

The week is computed from the calendar (W1 Monday = `2026-07-13`), so there is no state to drift.

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
| `/week` | Orient for the current week — restate the target, verify last week closed, open the worklog |
| `/task <slug>` | Open a task with a durable design trail under `.docs/work/<slug>/` |
| `/approve <phase>` | Human approval of a design phase — only `/approve implementation` unlocks source edits |
| `/verify` | Build + test + lint; reports SKIPPED for absent tooling, never a vacuous pass |
| `/ai-review` | Review the working diff against written checklists via the review subagents |
| `/rca` | Structured root-cause analysis, invoked only after `/verify` fails twice |
| `/done` | Close the active task, re-lock the gate, record the outcome |
| `/log [note]` | Append a dated entry to this week's worklog |
| `/gate [week]` | Run that week's "Done when" exit test concretely — PASS or FAIL |
| `/task-status` | Report current state compactly — week, active task, gate state, outstanding phases |
| `/adr [title]` | Record an architecturally significant decision in `docs/decisions.md` |
| `/consistency` | Sweep the frozen documents for drift, stale references, reinstated scope |
| `/spike` | W5 feasibility spike — measure the memory envelope, freeze it, record μ_gen (blocks W5 ingestion until done) |

## Subagents

| Agent | Model | Tools | Purpose |
| :--- | :--- | :--- | :--- |
| `impact-analyst` | opus | Read, Grep, Glob, Bash | Pre-implementation blast-radius analysis — which packages/frozen artifacts/prior runs a change would invalidate; writes `impact.md` |
| `contract-reviewer` | sonnet | Read, Grep, Glob, Bash | Reviews diffs touching the Go↔Python seam, Redis schemas, wire fields, or chunk IDs against `interfaces.md` |
| `experiment-reviewer` | sonnet | Read, Grep, Glob, Bash | Reviews diffs touching measurement/metrics/judging/thresholds against the frozen experiment protocol, incl. research-integrity check |
| `rca-analyst` | opus | Read, Grep, Glob, Bash | Structured root-cause analysis after two failed `/verify` attempts; treats tests as immutable unless it can prove staleness |

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
  Exit 2 = blocked, 0 = allowed. Simulate a later week with `THESIS_RUNWAY_LAST_WEEK=0`.

## Where the rules live

`.docs/ai/rules.md` holds the ten trip-wires; each cites its governing section in `docs/` rather than
restating it. Review subagents Read it at review time, so there is one place to update. The engineering
standards suite is deliberately deferred to W6, to be derived from real Go code rather than invented
against an empty repo.
