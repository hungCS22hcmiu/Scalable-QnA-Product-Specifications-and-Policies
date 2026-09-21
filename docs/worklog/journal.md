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
