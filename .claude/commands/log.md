---
description: Append a dated entry to this week's worklog
argument-hint: [optional note to include]
---

Append an entry to `docs/worklog/W<NN>.md` for the current week. Create the file from the template in
`docs/worklog/README.md` if it does not exist.

Entry format:

```markdown
### <YYYY-MM-DD>  ·  <hours>h

**Did:** <what actually happened — concrete, not "worked on the gateway">

**Decisions:** <any; link the ADR if one was written, or "none">

**Blockers:** <what stopped progress, or "none">

**Exit test:** <not attempted | FAIL: reason | PASS>

**Next:** <the single next action>
```

Rules:

- **Ask for the hours** if not supplied. The hour count matters — the whole schedule is built on
  ~15 h/week and the write-up will want the real distribution.
- **"Did" must be concrete.** "Built ingest.py; retrieval returns chunk IDs for 8/10 test queries" is
  useful. "Worked on RAG" is not.
- **Be honest about failure.** A week that produced nothing should say so. The risk register in
  `docs/time_line.md` assumes slippage is visible; a log that only records wins is worse than no log.
- If a decision was made that changes a frozen value or a contract, say so and prompt for `/adr`.
- Do not rewrite previous entries. The log is append-only — it is an audit trail, not a summary.
