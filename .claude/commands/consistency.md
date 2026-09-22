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

# 4. Schedule: weeks were removed 2026-09-21 — find the ones still being used as a HANDLE
#    (prose that records WHEN something happened is history and must stay: "W5 spike", "W08.md")
rg -n 'this week|next week|by W[0-9]+|decide-by W[0-9]+|W[0-9]+ onward' docs/ README.md CLAUDE.md .claude/ .docs/ --glob '!docs/archive/**' --glob '!docs/worklog/W0*.md'

# 4b. The phase plan has ONE owner: super-plan.md. time_line.md is RETIRED (2026-09-21), and any
#     instruction read out of it is a bug -- three of its rows were wrong when it was retired.
rg -n '^\*\*Exit:\*\*' docs/super-plan.md
rg -n 'RETIRED' docs/time_line.md

# 5. Every "proposal §N" reference resolves to a heading in Final_Proposal.md
rg -ho 'proposal §[0-9]+(\.[0-9])?' docs/*.md | sort -u

# 6. Contract field names agree between interfaces.md and defense_demo.md
rg -n 'source_overlap|reuse_confidence|t1_key|dataset_epoch' docs/interfaces.md docs/defense_demo.md

# 7. Nothing untracked that should be committed
git status --short
```

**Checks that require reading, not grepping:**

- Does anything still take an *instruction* from `time_line.md`? It is retired; only its Risk
  Register and Learning Path are live, and `super-plan.md` owns execution.
- Do the frozen-value lists in `interfaces.md`, `experiment-protocol.md` §1, and
  `.docs/ai/frozen-values.txt` cover the same set?
- Does every **Open** ADR still have a decide-by that resolves? Decide-by used to be a week
  number; weeks are gone, so a row still reading "W14" is **stale by construction** — report it,
  and propose the phase it belongs to rather than reinterpreting it silently.
- Does `docs/requirements.md` have any requirement no super-plan item cites, or any super-plan
  item citing no requirement? Both are defects in the plan (`requirements.md` "Traceability").

Report drift with exact replacement wording. Do not fix silently — show the diff you propose, since
these documents are frozen and changes to three of them require an ADR.
