# Journal

Append-only. Newest entries at the bottom. Format and rules: `README.md` in this directory.

Pre-thesis weeks are in `W05.md`, `W06.md`, `W08.md` and are not migrated here.

---

## 2026-09-21 · Phase 1 · <hours>h

**Did.** Pre-thesis sweep, in the agreed order 0 → 5 → 3 → 4 → 2 → 1
(`Pre-thesis_Sweeping.md`). **#0**: wrote **ADR-035…038** — the advisor-approved pivot of
2026-09-10 had been applied to the report on 2026-09-15 but had no entry in the decision log at
all — and carried them into the contracts in the same pass rather than leaving the lag ADR-032
left: `interfaces.md` → **v0.9**, `experiment-protocol.md`, `data-card.md` (**G5**), the `.proto`,
`CLAUDE.md`. **#5**: ran the PQA probe and wrote **ADR-039**. **#3**: created
`docs/requirements.md` and `docs/super-plan.md`, empty by design. **#4**: replaced the week-coupled
harness with phase + scope. Base commit first — 120 files of Tier-2 / reuse-rule work had been
sitting uncommitted, and `.claude/` and `.docs/` are now actually tracked.

**Found.**
- **`make lint` was passing vacuously.** `command -v X && X … || echo "SKIPPED — not installed"`
  printed the not-installed message when the tool was **present and failing**, and exited 0. It
  had been hiding a live ruff error in `fetch_corpus_v1.py`. Both fixed.
- **Amazon-PQA is thick enough**: `inkjet_printers` 1,288 products / 92,070 questions, median 8
  questions per product, 63.7 % with ≥ 5; 43.6 % of multi-question products carry a genuine
  near-duplicate pair. `chairs` is thinner per product (median 2) but has 19,193 products.
  Strata A and C can be sampled rather than authored.
- **PQA supplies B-within traps naturally** — "works with Windows 10?" against "works with
  Windows 7?" on one product. That is ADR-035's residual occurring in real traffic, and it
  weakens the standing limitation that the measured residual is partly an artefact of the
  author's own chunk splitting.
- **The PQA licence does NOT close `data-card.md` §1's TODO(W8).** AWS's registry says
  CDLA-Permissive-1.0; the dataset's own readme — which that registry entry names as its
  documentation — carries the ACM personal/classroom notice and never says "CDLA". Taking the
  more restrictive: academic use granted, redistribution not. `v1` ships as a build script plus a
  hash manifest.
- **PQA does not help ADR-024 requirement 3**, contrary to what was argued when the switch was
  proposed: median product prose is 504 chars and 1.6 % of products reach three chunks.
  Requirement 3 rests on the authored policy half, as before.
- **The PQA readme's field list does not match its own data** (`asin` not `asin_id`,
  `bullet_point1..5` not `bullet_points`). The probe's first run returned zero parseable records
  for exactly that reason. The corpus builder must be written against the bytes.
- **`.gitignore` ignored `.claude/` and `.docs/` entirely** while both their READMEs claimed the
  opposite. The task trail called "the raw material for the write-up" had no version history and
  no remote copy.

**Decisions.** ADR-035, ADR-036, ADR-037, ADR-038, ADR-039. Plus three workflow calls by the
author: track `.claude/` and `.docs/`; `journal.md` replaces the weekly worklog; the scope ladder
is L / M / S with `/approve implementation` required at every scope.

**Blocked.** Nothing new. **F1 remains open and still outranks everything** — no
admission-control number is citable until it resolves. Task `two-lane-cache` is still open with
the workflow deliberately bypassed and needs an explicit close or abandon.

**Exit test.** Not run. Phase 1's criterion needs `v1`, which ADR-039 has only just decided the
source of.

**Next.** Finish sweep #2 and #1, then either close `two-lane-cache` or abandon it explicitly,
then F1.

---

## 2026-09-21 (second entry) · Phase 1 · <hours>h

A second entry for the same day rather than an edit to the one above, which was written while
#2 and #1 were still open. Append-only means the first entry stays as the record of what was
true when it was written (`README.md`).

**Did.** Finished the sweep. **#2**: archived five closed pre-thesis trails to
`.docs/work/archive/` with a README, reclassified `mvp-advisor-demo` (its approved decisions had
already become ADR-035…038), pruned `settings.local.json` 52 → 24. **#1**: rewrote the dataset
sections of the report and proposal to PQA, verified the last unverified matrix row and both
carried numbers.

**Found.** Verification changed two claims rather than confirming them.

- **The GroundedCache ablation figure was wrong as carried.** It is **+0.125 / +0.118** across the
  two datasets, not "+0.12–0.13". Read from the abstract originally; the full text is specific.
- **The speedup claim was incomplete in a way that mattered.** Both documents carried
  1.95× → 1.04× as the price of full gating. The full text has an intermediate row the abstract
  does not: the **no-support** variant at **1.48× at USR 0.125**. So the other three gates account
  for 1.95× → 1.48×, and the adopted support gate accounts for **1.48× → 1.04×**. This study
  already holds analogues of the other three (ADR-026), so the smaller figure is the one that
  transfers. The claim got weaker in one direction and more defensible in the other.
- **`τ_s = 0.6` is genuinely the paper's published default**, and its formula matches ADR-035
  verbatim. The pin cites a real default rather than an inference.
- **FreshCache verified, and it strengthened the positioning rather than collapsing it.** Its rule
  is a fitted exponential-decay model plus a **learned MLP** against per-tier error budgets — a
  learned model on the reuse decision, which is the line ADR-016 does not cross. Unlike ADR-026,
  where verification collapsed a novelty claim, this one sharpened a distinction.

**Decisions.** None new. ADR-035 amended in place with the verified figures.

**Blocked.** One item of the sweep is left and it is blocked on a decision, not on work: report
§5.1 and proposal §11 restate a plan `super-plan.md` replaces, and that file is empty by design
pending sign-off on content. **F1 still outranks everything.** `two-lane-cache` still needs an
explicit close or abandon.

**Exit test.** Not run — Phase 1 needs `v1`, whose source ADR-039 has only just settled.

**Next.** Fill the super plan and requirements, or resolve F1. F1 is the one that threatens an
already-measured contribution.
