---
description: Append a dated entry to docs/worklog/journal.md
argument-hint: [what happened]
---

Append to **`docs/worklog/journal.md`** — one append-only journal, not one file per week
(changed 2026-09-21, `Pre-thesis_Sweeping.md` #4). Dropping weeks would otherwise drop the
chronology and the hours, and `docs/worklog/README.md` says both are the raw material for the
design and evaluation chapters. `W05.md`, `W06.md` and `W08.md` stay where they are, unedited.

**Append, never rewrite.** Earlier entries are a record of what was believed at the time. If an
entry turns out to have been wrong, write a new entry saying so and what replaced it — do not
edit the old one. That correction trail is itself evidence for the write-up.

Entry format:

```markdown
## YYYY-MM-DD · Phase <n> · <hours>h

**Did.** What actually changed, in the repo, in one or two sentences. Name files or ADRs.

**Found.** Anything measured, or any belief that turned out to be wrong. Numbers with their
conditions attached — corpus, configuration, pressure — or they are not reusable later.

**Blocked.** What stopped, and on what or whom. Say "nothing" rather than omitting it.

**Next.** The single next thing.
```

Rules:

1. **Hours are recorded honestly**, including short days. The remaining-budget claim in `super-plan.md`
   is checkable only if the numbers are real.
2. **A number without its conditions is not a result.** Corpus, configuration, memory pressure,
   and whether the run is citable at all (`dev-v0` never is — ADR-020).
3. **If `$ARGUMENTS` is empty**, reconstruct the entry from the session: what was edited, what
   was verified, what failed. Ask for the hours; do not invent them.
4. **Do not restate what `docs/` already says.** Cite the ADR or the section.
