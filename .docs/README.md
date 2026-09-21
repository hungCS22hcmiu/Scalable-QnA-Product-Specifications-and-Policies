# `.docs/` — the AI workflow trail

**This directory is the AI workflow's task trail and rules layer. It is committed.**

## Relationship to `docs/`

| | `docs/` | `.docs/` |
| :--- | :--- | :--- |
| Authored by | **Human** | The AI workflow |
| Contains | The frozen thesis documents — proposal, interfaces, protocol, ADRs, data card, timeline, demo, architecture | Task trail (`work/`) and agent-facing rules (`ai/`) |
| Authority | **Source of truth** | Points *at* `docs/`; never restates it |
| Changes | Require an ADR when frozen | Append-only trail; rules updated when `docs/` changes |

**Do not mix them.** `docs/` is what the thesis is. `.docs/` is how the work got done. If you find
yourself copying a rule out of `docs/` into `.docs/ai/rules.md`, stop — cite the section instead. One
place to update.

## Layout

```
.docs/
  ai/
    rules.md                    numbered trip-wires; each cites its governing doc section
    architecture-guardrails.md  module boundaries agents must not cross
    review-checklist.md         what the review subagents check
    frozen-values.txt           regex patterns the frozen-guard hook enforces
  work/<task-slug>/
    spec.md                     what and why
    impact.md                   what it touches; frozen artifacts; runs invalidated
    plan.md                     ordered steps, checked off as work proceeds
    review.md                   AI-review findings and resolutions
    approvals.md                the ledger — who approved which phase, when, citing which ADR
    READY_TO_IMPLEMENT          marker written only by `/approve implementation`
```

## Why the trail exists

Beyond process hygiene: **W20–W22 must write an evaluation chapter and a design chapter.** "What did I
actually do, in what order, and why" is a question the write-up will ask and memory will not answer.
The trail is the raw material for that, and it is why `.docs/` is committed rather than ignored.
