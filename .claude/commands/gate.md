---
description: Run the current phase's exit criterion concretely and report PASS or FAIL
argument-hint: [phase number, defaults to current]
---

Prove the phase's exit criterion — **do not self-report it.** Run the actual checks.

The criterion is a **binary test**, not a judgement (`super-plan.md` item template). A phase is
not finished because its time is spent, and it is not finished because the work feels done.

1. **Read the exit criterion** for the phase from the phase plan — `docs/super-plan.md` once #3
   `docs/super-plan.md` — the `**Exit:**` line under its heading. **Quote it verbatim.** If the phase is unset, stop
   and say so; `/phase <n>` sets it.

2. **Decompose it into independently checkable criteria and run each one.** The criteria are
   deliberately written as things that can be executed:

   | Criterion shape | How to check it for real |
   | :--- | :--- |
   | "`v1` frozen + hashed after all gate criteria pass" | `make gate-corpus` exits 0 and prints a digest; `data-card.md` §7 has no `TODO(W8)` in the frozen-statistics list |
   | "`K` recorded and capacity derived" | `data-card.md` carries `K`; `cache_capacity` = `round(0.25 × K)` (ADR-027) |
   | "μ_hit probe recorded" | a run directory exists holding the probe's output, off-box (ADR-012) |
   | "editing a policy purges its dependents from both tiers" | run the edit; assert the `t1:` and `t2:` keys are both gone |
   | "an in-flight generation during an edit is discarded" | force the race; assert `writeback_discarded: true` in the §H log |
   | "completeness and precision reproducible from one script" | run that one script from a clean checkout |

3. **Report a table**: criterion → PASS / FAIL / **NOT RUNNABLE YET** (and what is missing).

   A criterion you cannot execute is **not** a pass. Vacuous passes are the failure mode this
   command exists to prevent — the same failure `make lint` had until 2026-09-21, where a tool
   that ran and failed reported "SKIPPED — not installed" and exited 0.

4. **Before running anything that loads a model**, check memory pressure — `CLAUDE.md`'s
   "Commands that work today". A run taken under yellow or red is invalid and must be discarded
   and repeated (ADR-012).

5. **Record the result** in `docs/worklog/journal.md` as a dated entry with `**Exit test:**`.

6. If FAIL: state the single smallest thing that would move it to PASS. The next phase does not
   open until this one closes.
