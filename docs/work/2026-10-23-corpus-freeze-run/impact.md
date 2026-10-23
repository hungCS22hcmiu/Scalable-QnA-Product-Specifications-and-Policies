# Impact — corpus-freeze-run

Written by the main session, 2026-10-23, not by the `impact-analyst` subagent: the blast radius was analysed twice already
(`2026-10-22-corpus-freeze/impact.md`, `2026-10-22-g1-finding/impact.md`), and nothing new is built here.

## What it touches

| Where | Change |
| :--- | :--- |
| `data/v1-freeze.json` | **New tracked file**: digests, counts, statistics, `known_failures`. No file name, asin, qa_id or path (the tool refuses otherwise). |
| `data/v1-draft/gate/freeze-a/`, `freeze-b/` | New, gitignored: the two reports and their retrieval exports. |
| Redis | Holds `v1` during the runs (the `dev-v0` index is replaced), then `dev-v0` again at the end (A9). No cache key exists. |
| `docs/data-card.md` | §7: the ten markers, the pair breakdown, a status paragraph for G1, two corrections (the monotonicity sentence; line 14), line 258. A frozen document. |
| `docs/decisions.md` | ADR-015, appended. |
| `docs/architecture.md`, `README.md` (entries for the new files), `docs/super-plan.md` (item 3.6 progress) | Documentation only. |
| Code (`rag/`, `gateway/`, `experiments/scripts/`, `Makefile`), tests, `docs/contracts/` | **Nothing.** Stop rule S6 makes a change to the first three a stop. |

## Frozen values

This task **creates** the frozen state: `dataset_version v1`, the snapshot digest (pinned `a5708fefa62c…`), `K` 622 / 652, capacity 156 /
163, the chunk digest, the retrieval stack. It moves **no existing frozen value**: 0.85, 0.2, 50, the chunking (256 / 40), `top_k` 5, the
embedding model and the corpus and workload files all stay.

## Which prior runs does it invalidate?

**None — no runs yet.** `experiments/results/` holds only `.gitkeep`. The only prior measurement is item 3.6's first gate run, which is
kept as the finding (ADR-014) and preserved in `data/v1-draft/gate/first-run/`.

## Other questions

- Adds a dependency? No. Reinstates cut scope? No. Changes a contract (`interfaces.md`)? No, so the contract phase is not required.
- Changes what or how anything is measured? It runs a measured gate and makes the corpus citable, so the **experiment phase is required**
  (it fixes the rewritten stop rules and the acceptance above before the first run).
- Cost and time: each gate run was about two minutes of embedding and retrieval on the first run (ingest 19 s, stage 2 86 s), plus
  `make ingest`. The machine must read memory level `1` before each.
