---
description: Sweep the frozen documents for drift, stale references, and reinstated scope
---

Run the documentation consistency sweep. Report a table: check → PASS / **DRIFT** (with the offending
lines). This catches the failure mode that iterative editing produces: two documents that each look fine
and disagree with each other.

Run these and interpret the hits — a hit is not automatically a failure, but every hit must be either an
intentional record of a change or a defect.

```bash
# 1. Dropped scope must appear only as a record of removal, never as a live commitment
rg -n 'learned predictor|predictor-gated|GPTCache/vCache integration|semantic routing|SSE|bypass.classifier' \
   docs/ README.md CLAUDE.md --glob '!docs/archive/**'

# 2. Frozen index: every HNSW mention must say "never mid-study"
rg -n 'HNSW' docs/ --glob '!docs/archive/**'

# 3. Config ladder is 1..5 everywhere, never 1..8
rg -n 'config_id|eight config|1\.\.8' docs/

# 4. Schedule: no stale weeks or dates after ADR-020
rg -n 'Sep 13|W5–W9|W10–W22|W9 report|13 weeks' docs/ README.md CLAUDE.md --glob '!docs/archive/**'

# 5. Every "proposal §N" reference resolves to a heading in Final_Proposal.md
rg -ho 'proposal §[0-9]+(\.[0-9])?' docs/*.md | sort -u

# 6. Contract field names agree between interfaces.md and defense_demo.md
rg -n 'source_overlap|reuse_confidence|t1_key|dataset_epoch' docs/interfaces.md docs/defense_demo.md

# 7. Nothing untracked that should be committed
git status --short
```

**Checks that require reading, not grepping:**

- Do `Final_Proposal.md` §12's drop order and `time_line.md` Ground Rule 2 list the same items in the
  same order?
- Do the frozen-value lists in `interfaces.md`, `experiment-protocol.md` §1, and
  `.docs/ai/frozen-values.txt` cover the same set?
- Does every **Open** ADR still have a decide-by week that has not already passed?

Report drift with exact replacement wording. Do not fix silently — show the diff you propose, since
these documents are frozen and changes to three of them require an ADR.
