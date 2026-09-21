---
description: Record an architecturally significant decision in docs/decisions.md
argument-hint: [short title of the decision]
---

Add an ADR to `docs/decisions.md`. This is the only sanctioned way to change a frozen value.

1. **Next ID** — scan the summary table for the highest `ADR-NNN` and use N+1. Never reuse or renumber.

2. **Ask the human for anything you do not know.** Never invent a rationale. You need: what is being
   decided, why now, what alternatives were rejected and why.

3. **Write the entry** in the file's existing house style:

   ```markdown
   ### ADR-NNN — <title>
   **Decided (scope|method|frozen)** · <YYYY-MM-DD> · *proposal §N; <other docs>.*

   <one-paragraph statement of the decision>

   - **Rationale:** ...
   - **Alternatives:** ... (and why rejected)
   - **Consequences:** ...
   ```

4. **⚠️ If this changes a frozen value**, the entry **must** contain an explicit line:

   > **Invalidates:** <which prior runs / results are now void, or "none — no runs yet">

   This is the single most important sentence in the record. Without it the decision log cannot answer
   "are these two numbers comparable?" in W20. **Refuse to write the ADR without it.**

   The frozen set is listed in `.docs/ai/frozen-values.txt` and in the `interfaces.md`
   "Frozen study-wide" line — read it rather than relying on memory.

5. **Add the summary-table row** at the top of the file, matching the existing column format.

6. **If a previous ADR is superseded**, mark it — do not delete it. Use the existing convention
   (`**Superseded by ADR-NNN**`, strikethrough on the old decision, and what is now in force).

7. **Cite the ADR** in `.docs/work/<task>/approvals.md` if a task is active — this is what releases the
   frozen-guard hook.

Report the ID and the one-line decision.
