# Worklog

One file per week, `W05.md` … `W22.md`. Append-only. Written by `/log`, opened by `/week`.

**Why it exists.** W20–W22 must write a design chapter and an evaluation chapter, and both ask "what did
you actually do, in what order, and why" — a question memory will not answer four months later. This is
the raw material. It is also how the risk register in `time_line.md` stays honest: a log that records
only wins is worse than no log.

## Entry template

```markdown
# W05 · Aug 10–16 · <focus from time_line.md>

**Goal:** <the week's focus>
**Done when:** <the exit test, verbatim from time_line.md>

---

### YYYY-MM-DD  ·  <hours>h

**Did:** <concrete. "Built ingest.py; retrieval returns chunk IDs for 8/10 test queries" —
not "worked on the RAG service">

**Decisions:** <any, with the ADR if one was written, or "none">

**Blockers:** <what stopped progress, or "none">

**Exit test:** <not attempted | FAIL: reason | PASS>

**Next:** <the single next action>
```

## Rules

- **Append only.** Never rewrite a past entry — it is an audit trail, not a summary.
- **Record the hours.** The whole schedule assumes ~15 h/week; the write-up will want the real
  distribution, including the weeks that got 4.
- **Record failure plainly.** A week that produced nothing should say so.
- **Close the week** with the exit-test result from `/gate`, not a self-assessment.
