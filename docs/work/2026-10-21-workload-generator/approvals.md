# Approvals — workload-generator

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | yes      | 2026-10-21 | ADR-013 (to write, plan step 15) |
| contract       | if §B/§D | yes      | 2026-10-21 | ADR-013 (to write, plan step 15) |
| experiment     | if measured | yes   | 2026-10-21 | ADR-013 (to write, plan step 15) |
| implementation | always   | yes      | 2026-10-21 | ADR-013 (to write, plan step 15) |

**Decided by the author before the trail opened (2026-10-21):** the answerability labeller is
**Claude** ("claude again obviously, due to its ability"). Never Qwen. What this means for the
Phase 5 judge is `spec.md` open question 1.

**Open questions** (`spec.md`, 1 to 14; 12 – 14 added after the impact analysis): **all accepted
as proposed** at the experiment approval (2026-10-21), the answers in `design.md` §10. Open
question 1 among them: the rule stays, so **the Phase 5 judge (item 5.1) is not Claude**. Undoing
that later needs ADR-013 (or a later ADR) to say why one model may do both.

**Phases required, per `impact.md`:** impact · **contract** (narrow: `interfaces.md` §D's definition
of `K`, only if open question 6 is accepted) · **experiment** (this item fixes `K`, the strata, the
split, the popularity order and the unanswerable population) · implementation.

**Design review:** done 2026-10-21, verdict *sound, with changes* (opus `design-reviewer`, on
design draft 1.1). Every finding accepted and merged into `design.md` **draft 2** and `plan.md`
**draft 2** (`review.md`). The biggest changes: B-within split by `probe_kind`, so RQ2a reads only
condition twins; four minimal-pair twin groups paired across the splits, ≥ 30 twins per split; the
gate's stage 2 retrieves scoped, as the runs do; product-pair units; the analysis rules A1 – A4
pre-registered in `rules.md` before the first sheet; a pilot on synthetic text before that commit.

**Impact approved 2026-10-21** by the author, on `impact.md` (F1 – F19). It accepts that open
question 6 touches a frozen value: `C / K = 0.25` keeps 0.25, but `K` would mean the distinct-query
count of the file a run draws from. The contract phase stays open for that one §D sentence.

**Contract approved 2026-10-21** by the author. This accepts open question 6 (`K` per run file).
The change is one sentence at `interfaces.md:361` and the v0.15 header and history row. The exact
wording and both sides of the seam were added to `design.md` §2.7 at this approval and shown to the
author: the gate prints `K` per file, and the gateway reads only an absolute `CACHE_CAPACITY`, so
no Go, wire, §H or `.proto` change. The edit itself waits for plan step 14.

**Experiment approved 2026-10-21** by the author, on `design.md` draft 2 (with the §2.7 contract
note) and `plan.md` draft 2. It fixes what the study will measure on: `K` per run file, the five
strata and the `probe_kind` values, the split by product-pair and (shape group, department) units,
the per-record stratified popularity rank, unanswerable queries inside the run files, G1 within
split and G2 per split, and the analysis rules A1 – A4. Two stop rules bind the build: pass 1
yield below 200 (plan step 8), and 3 or more of the author's 30 rows breaking their rule (step 10).
Either one stops the work; changing a rule after that needs this phase approved again.

**Invalidates:** none — no runs exist (`experiments/results/` holds only `.gitkeep`, checked again
at the impact approval). It binds
forward: after 3.6, changing the rank seed, the split unit or its seed, the A / C rule, the model
layer or the "K per run file" rule needs a new `dataset_version` (impact).

**Step 10 reader (2026-10-22).** The experiment approval names "the author's 30 rows". On
2026-10-22 the author told Claude to do the read and removed the three `Read` denies on
`data/raw`, `data/v1-draft` and `data/v1` in `.claude/settings.json`. Claude had advised against it
(it wrote and blind-checked the rows). No rule, constant or stop threshold changed; only who
reads. Result: 0 of 30 break their rule (`evidence/author-read.md`). The read is not independent,
and ADR-013 and the data card must say so. Invalidates: none.
