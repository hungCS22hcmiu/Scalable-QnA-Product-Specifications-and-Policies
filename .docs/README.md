# `.docs/` — the AI workflow trail

**This directory is the AI workflow's task trail and rules layer. It is committed.**

> True in fact only since **2026-09-21**. Until then `.gitignore` excluded `.docs/` entirely while
> this line claimed otherwise, so the trail below had no version history and no remote copy —
> `Pre-thesis_Sweeping.md` §4.5.

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
    SCOPE                       one letter, L|M|S — decides how much of the below is required
    spec.md                     what and why                          (every scope)
    impact.md                   what it touches; frozen artifacts; runs invalidated   (L, M)
    design.md                   diagrams, contracts, failure modes, unknowns          (L)
    review.md                   design-reviewer findings, then AI-review findings     (L)
    plan.md                     ordered steps, checked off as work proceeds           (L, M)
    approvals.md                the ledger — who approved which phase, when, citing which ADR
    READY_TO_IMPLEMENT          marker written only by `/approve implementation`      (every scope)
  work/archive/                 closed pre-thesis trails — read-only, see its README
```

**Scope decides the trail, not the calendar** (changed 2026-09-21, `Pre-thesis_Sweeping.md` #4).
`L` is anything touching a frozen document, `interfaces.md`, the `.proto`, `reuse/`, or something
measured. `M` is ordinary code. `S` is tests, docs and one-liners. Every scope still ends at
`/approve implementation`, and an **unset** `SCOPE` blocks rather than defaulting to `S`.

## Why the trail exists

Beyond process hygiene: **the write-up must produce an evaluation chapter and a design chapter.**
"What did I actually do, in what order, and why" is a question the write-up will ask and memory will
not answer. The trail is the raw material for that, and it is why `.docs/` is committed rather than
ignored. A closed trail is therefore **archived, never deleted** — see `work/archive/README.md`.
