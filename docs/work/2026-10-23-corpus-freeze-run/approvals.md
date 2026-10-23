# Approvals — corpus-freeze-run

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | yes      | 2026-10-23 | ADR-014 (committed, status "proposed"); ADR-015 to write |
| contract       | if §B/§D | not required (`impact.md`: no `interfaces.md` surface) | | |
| experiment     | if measured | yes   | 2026-10-23 | ADR-014 |
| implementation | always   | yes      | 2026-10-23 | ADR-014; ADR-015 to write |

**Opened 2026-10-23** by the author's request to finish item 3.6, as the successor the old trail promised. Scope **L** (a measured gate, a frozen
document, the freeze). Design and design review are **inherited** from `2026-10-22-corpus-freeze` and `2026-10-22-g1-finding` (`design.md`,
`review.md`), and this is stated in `spec.md`.

**What the author is asked to approve:**

| Item | Answer | When |
| :--- | :--- | :--- |
| `/approve impact` (`impact.md`: new `data/v1-freeze.json`, `data-card.md` §7, ADR-015, no code, no prior run invalidated) | **yes** (`/approve impact`, typed by the author) | 2026-10-23 |
| `/approve experiment` (`spec.md`: the rewritten stop rules S1 – S6, acceptance A1 – A11 with the ADR-014 changes, memory `1`, two runs into `freeze-a/` and `freeze-b/`, the pinned digest) | **yes** (`/approve experiment`, typed by the author) | 2026-10-23 |
| Inherit the design and the reviews, or ask for new ones (`spec.md` question 1) | **inherit** (taken from `/approve experiment`, as announced in chat; the author did not ask for new ones) | 2026-10-23 |
| Read ADR-014 before the freeze, and set its index status (question 2) | | |
| Phase 3 exit wording in `docs/super-plan.md` (question 3) | | |
| `/approve implementation` | **yes** (`/approve implementation`, typed by the author) | 2026-10-23 |

**Invalidates: none — no runs yet** (`experiments/results/` holds only `.gitkeep`; Redis holds `dev-v0`). The run that exists, item 3.6's first
gate run, stands as ADR-014's finding and is preserved in `data/v1-draft/gate/first-run/`.

**Impact approved 2026-10-23** by the author (`/approve impact`), on `impact.md`. This approves the blast-radius reading only: one new tracked file
(`data/v1-freeze.json`), the edits to `data-card.md` §7, ADR-015, the documentation entries, Redis holding `v1` during the runs and `dev-v0`
after, and **no change to code, tests or any existing frozen value** (0.85, 0.2, 50, chunking, `top_k`, the embedding model, the corpus and the
workload files all stay). **Invalidates: none — no runs yet** (`experiments/results/` holds only `.gitkeep`). The first gate run stays as
ADR-014's finding. It does **not** approve the experiment phase (the rewritten stop rules S1 – S6 and the acceptance), the choice to inherit the
design and the reviews, or implementation.

**Experiment approved 2026-10-23** by the author (`/approve experiment`), on `spec.md` draft 1, `impact.md`, `design.md` (inherited) and `plan.md`
draft 1. It fixes, **before any run**: the form (two gate runs on `v1` with `ACCEPT_FAILED=G1`, each exit code 3, into `freeze-a/` and
`freeze-b/`, then `freeze`); the **stop rules S1 – S6** as rewritten (G1 failing as in the first run is not a stop; any other criterion, a
different G1 count, a different digest, a changed code tree, or any memory reading but `1` is); the **acceptance A1 – A11**; the pinned digest
`a5708fefa62c…`; the first run's counts (21 = 13 + 8, 18 across, 1,342) and retrieval-export hashes as the comparison; memory `1` = green, checked
against the Activity Monitor graph (`evidence/memory-scale.md`). **Changing any of these after the first run needs this phase approved again.**
**Invalidates: none — no runs yet.** The first gate run is not invalidated; it stands as ADR-014's finding.

**It does not approve** implementation, which is the next command. Not covered by this approval and still the author's: the Phase 3 exit
wording in `docs/super-plan.md`, reading ADR-014 and moving its index status from "proposed", and `CLAUDE.md`, `README.md:227` and the thesis text.

**Before the first gate run the author must also:** bring the memory level to `1` (close apps; this machine reads `2` when idle with the usual
work open) and keep it there for each run.

**Implementation approved 2026-10-23** by the author (`/approve implementation`), after impact and experiment; the contract phase is not required.
`READY_TO_IMPLEMENT` is written. This unlocks the plan in its own order. The gate runs (steps 3 and 5) need memory level `1` at the start and
throughout; a reading of anything else discards the run (S3). No code, test, corpus or workload file is edited (S6). Commits are made when the
author asks. **Invalidates: none — no runs yet.**

**Closed 2026-10-23 (`/done`).** All 13 plan steps are done. The amended Phase 3 exit holds (`evidence/phase3-exit.md`). `READY_TO_IMPLEMENT` is
deleted and the gate is relocked. **Invalidates: none — no runs yet** (`experiments/results/` holds only `.gitkeep`); no frozen value moved. Taken from
the author's chat instruction to freeze and close Phase 3 (not typed as a command): the **Phase 3 exit line in `docs/super-plan.md` was amended** to
ADR-014's proposed wording, and ADR-014's index status moved to "in force for the form". Still the author's: the "How C1 is read" paragraph, the
supervisor line, `CLAUDE.md:44`, `README.md:227`, whether a `v2` follows.
