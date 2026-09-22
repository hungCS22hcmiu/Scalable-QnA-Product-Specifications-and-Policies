---
description: Find out — produce an answer and evidence, never a code change
argument-hint: <slug> [the question]
---

Open an **investigation**: a question to answer, not work to ship.

1. Create `.docs/work/$1/` with `SCOPE` = **S** and a `spec.md` whose first line is **the question**,
   stated so that it has a checkable answer. "Is X slow?" is not one. "Is the Tier-2 hit path
   bounded by the embedding round-trip or by Retrieve?" is.
2. **Do not set `READY_TO_IMPLEMENT`, and do not edit source.** The gate will refuse anyway; that
   is the point. An investigation that starts fixing things stops being evidence.
3. Record findings in `spec.md` as you go — including the ones that disprove what you expected.
   Those are the valuable half, and they are the half that gets lost.
4. **Every number carries its conditions**: corpus, configuration, memory pressure, and whether it
   is citable at all. `dev-v0` never is (ADR-020). A functional run says so in the same sentence
   as its number, or it will be read as a result later.
5. Close by stating the answer, the evidence for it, and **what it changes** — an ADR, a new task,
   or nothing. "Nothing" is a legitimate and useful outcome; say it plainly.

If the answer turns out to need a code change, that is a **separate** task: `/feature`, `/bugfix`
or `/refactor`, opened afterwards, citing this trail.
