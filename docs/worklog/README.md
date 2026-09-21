# Worklog

**`journal.md`** — one append-only journal, dated, no week structure. Written by `/log`.

`W05.md`, `W06.md` and `W08.md` are the **pre-thesis record** and stay exactly as they are. They
are not migrated into the journal and not edited: they hold the μ_hit probe numbers, the G1 = 0 /
G2 = 0 shakedown, the memory-envelope measurements behind ADR-017 and ADR-021, and the reasoning
behind ADR-030…033. Deleting or rewriting them would destroy evidence.

> **Changed 2026-09-21** (`Pre-thesis_Sweeping.md` #4). The worklog was one file per week, opened
> by `/week`. Weeks were removed from the workflow because a week number recorded the date and not
> the work. Dropping them would otherwise have dropped the **chronology and the hours** with them
> — and those are exactly what this directory exists to preserve — so the weekly files became one
> dated journal rather than nothing.

**Why it exists.** The write-up must produce a design chapter and an evaluation chapter, and both
ask "what did you actually do, in what order, and why" — a question memory will not answer four
months later. This is the raw material. It is also how the risk register stays honest: a log that
records only wins is worse than no log.

## Entry template

```markdown
## YYYY-MM-DD · Phase <n> · <hours>h

**Did.** Concrete. "Built ingest.py; retrieval returns chunk IDs for 8/10 test queries" —
not "worked on the RAG service". Name files, ADRs, task slugs.

**Found.** Anything measured, and anything believed that turned out to be wrong. Numbers carry
their conditions — corpus, configuration, memory pressure — or they are not reusable later.

**Decisions.** With the ADR if one was written, or "none".

**Blocked.** What stopped, and on what or whom. "Nothing" rather than omitted.

**Exit test.** Only when `/gate` was run: PASS / FAIL with the reason. Never a self-assessment.

**Next.** The single next action.
```

## Rules

- **Append only.** Never rewrite a past entry — it is an audit trail, not a summary. If an entry
  turns out to have been wrong, write a new one saying so. The correction trail is itself evidence.
- **Record the hours.** The budget in `time_line.md` is checkable only against real numbers,
  including the days that got two.
- **Record failure plainly.** A day that produced nothing should say so.
- **A number without its conditions is not a result**, and `dev-v0` is never citable (ADR-020).
- **Close a phase** with the exit-test result from `/gate`, not a self-assessment.
