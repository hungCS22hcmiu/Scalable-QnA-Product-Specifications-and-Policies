# Deliverables — Figure generators and the raw archive (item 5.4)

Closed 2026-11-12 · super-plan item 5.4 · ADR-027 · `interfaces.md` v0.35 · Phase 5 closed

## What shipped

- **`make figures`** (`make_figures.py`) draws F10 (judge agreement by containment bucket) and F16 (the noise-floor
  correction) as PDFs, each with a `<name>.json` of the plotted values. It checks every run's `raw/` and `judge/`
  first and draws nothing from a run that is missing or changed. It refuses any matplotlib other than the pin.
- **The raw archive** (`raw_archive.py`, ADR-027): one tar per run in `~/thesis-raw-archive/`, outside the
  repository, and a tracked `archive.sha256` per run. `make raw-archive`, `raw-check` and `raw-restore`.
- **`make figures-clean-check`**: the Phase 5 exit test. A clean copy plus the archive gives the same figure bytes.
- Docs: ADR-027 and its Summary row; `interfaces.md` §I at v0.35; the stale "not built" lines in `architecture.md`,
  `Evaluation.md` and `CLAUDE.md`.

## Files changed

- New: `experiments/scripts/raw_archive.py`, `make_figures.py`, `figures_clean_check.sh`, `experiments/requirements.txt`
  (`matplotlib==3.10.8`), `experiments/tests/test_raw_archive.py` (56 tests), `test_make_figures.py` (28 tests), and
  the cost run's `archive.sha256` (523 lines, hashes and paths only).
- Modified: `Makefile`, `docs/decisions.md`, `docs/contracts/interfaces.md`, `docs/architecture.md`,
  `docs/1-System Docs/Pipelines/Evaluation.md`, `CLAUDE.md`, `docs/super-plan.md`.
- **Frozen values touched: none. Prior runs invalidated: none.** The contract change is additive (§I).
- Outside the repository: `~/thesis-raw-archive/2026-11-01T21-17-56_cfg4_judgecost.tar` (2,426,880 bytes, PQA text).
- On this machine: matplotlib 3.10.8, kiwisolver 1.4.9, contourpy 1.3.3 and fonttools 4.61.0 reinstalled for arm64.
- Not this task: `gateway/cmd/gateway/main.go` (the drain fix) is still uncommitted.

## How it was verified

Main session, 2026-11-12, after the executor:
- `make verify` → exit 0. Go packages `ok`; rag 94 passed; experiments 1332 passed (1248 + 84 new). No SKIPPED target.
- DC 1 → 523 list lines = 523 files = 523 tar files, each hashing to its line; 519 answers named by their hash,
  519 of 519 `answer_sha256` present, 622 records = `records.count`; a second archive → `REFUSED`, exit 2.
- DC 2 → `make raw-check` → `ok (523 files)`; the change, deletion, addition and bad-member tests pass.
- DC 3 → `make figures` → two `built` lines, four files; the zero-built, stale-file and version-guard tests pass.
- DC 4 → tests compare F10 with `scores.json` (`n` sum 79, no `below 1.0`) and F16 with M08 (165 → 0.0501
  [0, 0.3038], 134 → 0 [0, 0.2307], 0 → null, drawn as a gap).
- DC 5 → two runs → `SAME` for all four files.
- DC 6 → `make figures-clean-check` → exit 0: the copy first fails naming `raw/`, then restores, checks, and prints
  `IDENTICAL 4 files`.
- DC 7 → only the two new test files under the test folders. DC 8 → 531 locked hashes, `diff` empty. DC 9 → ADR-027,
  four `v0.35`, no stale line.
- Both figures were drawn to PNG and looked at: titles, axes, error bars, `n` labels, the δ line and the footer.
- Phase 5 exit, run for real: Entries 5 and 6 and `scores.json` (agreement), ADR-026 (δ), `figures-clean-check` → 0.

## Numbers

All `citable: no`. Source: the cost run `2026-11-01T21-17-56_cfg4_judgecost` (corpus `v1` validation, configuration
4, gate on, MIXED off, τ 0.85, `mutation: off`). Nothing loaded a model, so memory pressure does not apply.
- F10: hit buckets `1.0` 55/69, `[0.8, 1)` 2/2, `[0.6, 0.8)` 6/6, `below 0.6` 2/2; MISS 17/21 (values from
  `scores.json`, item 5.2).
- F16: 401 points at n = 1000 (illustrative), from `floor.json` (item 5.3).
- `make figures`: peak memory 87,752,704 bytes (about 84 MiB), 0.65 s.

## Deferred and follow-ups

- **The author:** back up `~/thesis-raw-archive/` to private storage (ADR-027). It is the only copy outside the run.
- **Executor deviations, accepted:** `check()` reports a bad list or a symlink as a problem line; a payload dict goes
  to `draw` and `save`; extra refusals (a repeated list path, a leftover `.tar.partial`, a `--run-id` that is a path);
  tar read errors become `ArchiveRefused`; the F16 legend sits below the plot.
- **Phase 9 (build fixes):** fontTools was also x86_64 and was reinstalled, not pinned (with `pdf.fonttype` 3 it does
  not draw). `raw_archive check` with no run named now fails when it checks nothing.
- F16 is a new figure; the report's `figures.md` list does not have it yet. F1 and F2 are not drawn.
- Stale text left: `CLAUDE.md` "Not built yet" still names the judge harness; `Evaluation.md`'s table is dated 30 Oct.
- The x86_64 copies of the four packages remain in the framework site-packages, shadowed by the user-site copies.
