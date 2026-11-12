# Plan — Figure generators and the raw archive (item 5.4)

Design: design.md (approved 2026-11-12)

Rules for every step (`.claude/rules/execution.md`):
- Nothing in this plan loads a model, so no memory-pressure check is needed. Every number is `citable: no`.
- Never edit, skip or loosen an existing test. Never commit.
- In the cost run, write only two things: the new `archive.sha256` (step 6.1) and the regenerated `figures/`. Never
  write into its `raw/`, `judge/`, `manifest.yaml` or `ablation/`. Never run `raw-restore` on it.
- The tar holds PQA text. It lives only in `~/thesis-raw-archive/`. Never copy it, or anything from `raw/` or `judge/`,
  into the repository or into `evidence/`.
- On a failed check: one quick fix if the cause is obvious and local, run it again, and if it still fails, stop
  and report the full output.
- `R` below means `experiments/results/2026-11-01T21-17-56_cfg4_judgecost`, `T` means
  `docs/work/2026-11-12-figure-generators`, and `A` means `~/thesis-raw-archive`.

## Phase 0 — Baseline

- [x] 0.1 Record the hashes of the locked files (DC 8, "before").
  - Run: `R=experiments/results/2026-11-01T21-17-56_cfg4_judgecost; find "$R/raw" "$R/judge" "$R/manifest.yaml"
    "$R/ablation" -type f -print0 | sort -z | xargs -0 shasum -a 256 >
    docs/work/2026-11-12-figure-generators/evidence/sha_before.txt`
  - Pass: 531 lines: `manifest.yaml`, `raw/requests.jsonl`, 519 answers, 3 `judge/` files and 7 `ablation/` files.
  - Result: wrote evidence/sha_before.txt, 531 lines (2 + 519 answers + 3 judge + 7 ablation).
- [x] 0.2 Baseline `make verify`, before any change.
  - Run: `make verify`
  - Pass: exit 0. If it fails, stop: the failure is not this task's, and the human decides.
  - Result: exit 0; Go all ok, rag 94 passed, experiments 1248 passed, no SKIPPED line.
- [x] 0.3 Confirm nothing is archived yet.
  - Run: `ls "$R/archive.sha256" ~/thesis-raw-archive 2>&1; ls "$R"`
  - Pass: both `ls` targets do not exist; `R` holds `ablation`, `judge`, `manifest.yaml` and `raw` only. If either
    target exists, stop and report.
  - Result: both targets absent; R holds ablation, judge, manifest.yaml, raw only.

## Phase 1 — The matplotlib dependency

- [x] 1.1 Write `experiments/requirements.txt`: a comment (the figures' only pinned dependency; the pin keeps the
  figure bytes fixed, design.md §3), then the line `matplotlib==3.10.8`.
  - Files: `experiments/requirements.txt`
  - Run: `cat experiments/requirements.txt`
  - Pass: exactly one requirement line, `matplotlib==3.10.8`.
  - Result: wrote experiments/requirements.txt: two comment lines and the one line `matplotlib==3.10.8`.
- [x] 1.2 Reinstall matplotlib and its two broken dependencies for arm64. The author approves this command.
  - Run: `python3 -c "import platform; print(platform.machine())"` (must print `arm64`), then
    `pip3 install --force-reinstall --no-deps --no-cache-dir matplotlib==3.10.8 kiwisolver==1.4.9 contourpy==1.3.3`
  - Pass: `python3 -c "import matplotlib, kiwisolver, contourpy; print(matplotlib.__version__)"` prints `3.10.8`
    with no error. If the install is denied or fails, stop and report: never install another version.
  - Result: platform arm64; pip3 installed matplotlib 3.10.8, kiwisolver 1.4.9, contourpy 1.3.3 (arm64 wheels); import prints 3.10.8.

## Phase 2 — `raw_archive.py`

- [x] 2.1 Create `experiments/scripts/raw_archive.py` with its docstring (what it does, the three commands, the exit
  codes, ADR-027), the constants `HASH_LIST`, `FOLDERS`, `IGNORED`, `ArchiveRefused(Exception)`, and
  `hash_tree`, `format_list`, `read_list` exactly as §3 says. Defaults: `RESULTS_DIR` from `$RESULTS_DIR`, else
  `<repo>/experiments/results`; `ARCHIVE_DIR` from `$RAW_ARCHIVE_DIR`, else `~/thesis-raw-archive`.
  - Files: `experiments/scripts/raw_archive.py`
  - Run: `python3 -c "import sys; sys.path.insert(0, 'experiments/scripts'); import raw_archive"`
  - Pass: imports with no error.
  - Result: created raw_archive.py (docstring, constants, ArchiveRefused, hash_tree, format_list, read_list); imports, ruff clean.
- [x] 2.2 Add `check(run_dir)` as §3 says: problems are strings `no hash list`, `no raw/`, `missing: <path>`,
  `changed: <path>`, `added: <path>`, sorted by path.
  - Files: `experiments/scripts/raw_archive.py`
  - Run: `ruff check experiments/scripts/raw_archive.py`
  - Pass: no error.
  - Result: added check(); problems sorted by path; a bad list or a symlink is one problem line (`bad hash list:`, `unsafe:`); ruff clean.
- [x] 2.3 Add `cross_check(run_dir)` as §3 says (answer names, referenced answers, the record count against
  `manifest.yaml`'s `records.count`, read with `yaml.safe_load`).
  - Files: `experiments/scripts/raw_archive.py`
  - Run: `ruff check experiments/scripts/raw_archive.py`
  - Pass: no error.
  - Result: added cross_check() (answer names, referenced answers, line count vs records.count); ruff clean; on the cost run it returns [] (read-only).
- [x] 2.4 Add `archive(run_dir, archive_dir)` in §3's five-step order. The tar is uncompressed, files only, members
  sorted by path, named relative to the run folder (`raw/...`, `judge/...`). Create `archive_dir` if it is missing.
  - Files: `experiments/scripts/raw_archive.py`
  - Run: `ruff check experiments/scripts/raw_archive.py`
  - Pass: no error.
  - Result: added archive() in the five-step order (uncompressed tar, files only, sorted, mtime kept, read back, list last); ruff clean after one local fix (B023: added _sha256_stream).
- [x] 2.5 Add `restore(run_dir, archive_dir)` as §3 says: every refusal happens before any member is extracted, then
  `extractall(path=run_dir, filter="data")`, then `check`. A non-empty `check` raises `ArchiveRefused` naming each
  problem.
  - Files: `experiments/scripts/raw_archive.py`
  - Run: `ruff check experiments/scripts/raw_archive.py`
  - Pass: no error.
  - Result: added restore(): refuses before extracting (list/tar missing, raw/ or judge/ present, non-regular or out-of-folder member), then extractall(filter=data) and check(); ruff clean.
- [x] 2.6 Add `main(argv)` with the subcommands and options of §3, and `if __name__ == "__main__": sys.exit(main())`.
  `archive` prints the number of files and the two paths written; `check` prints `ok <run_id> (<n> files)` or each
  problem; `ArchiveRefused` prints `REFUSED: <reason>` and returns 2.
  - Files: `experiments/scripts/raw_archive.py`
  - Run: `python3 experiments/scripts/raw_archive.py --help`
  - Pass: lists `archive`, `check` and `restore`.
  - Result: added main() with archive/check/restore, --results-dir, --archive-dir, exit 0/1/2; --help lists the three commands.

## Phase 3 — `make_figures.py`

- [x] 3.1 Create `experiments/scripts/make_figures.py` with its docstring (what it draws, from what, the exit codes,
  item 5.4), `PIN_FILE`, `pinned_version()`, `FigureSpec`, `style()` and `list_runs()` as §3 says. Import
  `raw_archive`, `noise_floor` and `label_ablation`; import matplotlib only inside the functions that draw, after
  `matplotlib.use("pdf")`.
  - Files: `experiments/scripts/make_figures.py`
  - Run: `python3 -c "import sys; sys.path.insert(0, 'experiments/scripts'); import make_figures as m;
    print(m.pinned_version())"`
  - Pass: prints `3.10.8`.
  - Result: created make_figures.py (docstring, PIN_FILE, pinned_version, FigureSpec, style, list_runs); pinned_version() prints 3.10.8; ruff clean.
- [x] 3.2 Add `f10_values(scores)` and `draw_f10(values)` as §3 says. Title "Judge agreement with the author, by
  containment bucket"; y axis "agreement (judge-v1 = author)" from 0 to 1; x labels are the bucket names, and the
  MISS group is labelled "MISS (generated)".
  - Files: `experiments/scripts/make_figures.py`
  - Run: `python3 -c "import sys, json; sys.path.insert(0, 'experiments/scripts'); import make_figures as m;
    v = m.f10_values(json.load(open('$R/ablation/scores.json'))); print([(p['bucket'], p['k'], p['n']) for p in
    v['points']])"` (with `R` set as above)
  - Pass: `[('1.0', 55, 69), ('[0.8, 1)', 2, 2), ('[0.6, 0.8)', 6, 6), ('below 0.6', 2, 2), ('generated', 17, 21)]`.
  - Result: added f10_values (4 hit buckets + MISS generated, n-sum check) and draw_f10; prints the 5 expected (bucket, k, n) tuples; ruff clean.
- [x] 3.3 Add `f16_values(floor, n=1000)` and `draw_f16(values)` as §3 says. Title "Judged against corrected
  false-hit rate (judge-v1's noise floor)"; x "judged rate (n = 1000, illustrative)"; y "corrected rate"; both from 0
  to 0.40. Null points become `nan` in the plotted arrays.
  - Files: `experiments/scripts/make_figures.py`
  - Run: `python3 -c "import sys, json; sys.path.insert(0, 'experiments/scripts'); import make_figures as m;
    v = m.f16_values(json.load(open('$R/ablation/floor.json'))); p = {x['judged']['k']: x for x in v['points']};
    print(len(v['points']), p[165]['corrected'], p[165]['interval'], p[0]['corrected'])"`
  - Pass: `401 0.0501 [0.0, 0.3038] None`.
  - Result: added f16_values (401 points, delta, false_alarm) and draw_f16; prints '401 0.0501 [0.0, 0.3038] None'; ruff clean.
- [x] 3.4 Add `save(fig, values, out_dir, name)` and the `<name>.json` layout of §3 (`figure`, `run_id`, `citable`,
  `source`, `values`), with the footer text added in `draw_*` from `run_id` and `citable`.
  - Files: `experiments/scripts/make_figures.py`
  - Run: `ruff check experiments/scripts/make_figures.py`
  - Pass: no error.
  - Result: added is_citable, f10_payload/f16_payload and save() (PDF without CreationDate, sorted JSON with figure/run_id/citable/source/values); footer is in draw_*; ruff clean.
- [x] 3.5 Add `FIGURES` (F10: name `F10-agreement-by-bucket`, input `ablation/scores.json`; F16: name
  `F16-noise-floor-correction`, input `ablation/floor.json`) and `main(argv)` in §3's five-step order. Output lines:
  `built <figure> <run_id>`, `not applicable <figure> <run_id>: <input>`, `skipped <folder>: no manifest.yaml`.
  - Files: `experiments/scripts/make_figures.py`
  - Run: `python3 experiments/scripts/make_figures.py --help`
  - Pass: shows `--results-dir`.
  - Result: added F10/F16 specs, FIGURES and main() in the five-step order; --help shows --results-dir; ruff clean.

## Phase 4 — Makefile and the clean-copy check

- [x] 4.1 Add to the `Makefile`, after `ablation-floor`: `RAW_ARCHIVE_DIR ?= $(HOME)/thesis-raw-archive`, and the
  targets `raw-archive` (needs `RUN_ID`), `raw-check` (`RUN_ID` optional), `raw-restore` (needs `RUN_ID`) and
  `figures-clean-check`, each with a `##` help line naming item 5.4. Each passes `--archive-dir "$(RAW_ARCHIVE_DIR)"`
  where it applies. Change `figures` to `PYTHONHASHSEED=0 $(PY) experiments/scripts/make_figures.py`. Add the four
  new targets to `.PHONY`.
  - Files: `Makefile`
  - Run: `make help | grep -E "raw-archive|raw-check|raw-restore|figures"`
  - Pass: five lines (`figures` and the four new targets).
  - Result: Makefile: RAW_ARCHIVE_DIR, raw-archive, raw-check, raw-restore, figures-clean-check, figures with PYTHONHASHSEED=0, 4 new .PHONY names; make help shows the five lines.
- [x] 4.2 Create `experiments/scripts/figures_clean_check.sh` (`set -euo pipefail`, executable) with §3's five steps.
  The copy goes in `mktemp -d`, removed by a `trap` on exit. Step 2 copies only files that exist. Step 3 runs
  `env -u RESULTS_DIR make figures` in the copy and keeps its output. It prints one line per step.
  - Files: `experiments/scripts/figures_clean_check.sh`
  - Run: `bash -n experiments/scripts/figures_clean_check.sh && test -x experiments/scripts/figures_clean_check.sh`
  - Pass: exit 0.
  - Result: wrote experiments/scripts/figures_clean_check.sh (executable, set -euo pipefail, mktemp copy removed by trap, five steps, one line each); bash -n passes.

## Phase 5 — Unit tests

- [x] 5.1 Write `experiments/tests/test_raw_archive.py`. A helper builds a fake run in `tmp_path`: `manifest.yaml`
  with `records.count`, `raw/requests.jsonl` (with one null `answer_sha256`), three content-addressed answers and
  `judge/verdicts.jsonl`. Tests:
  - `hash_tree` is sorted and POSIX, skips `.DS_Store`, and refuses a symlink;
  - `format_list` and `read_list` round-trip; a malformed line raises;
  - `archive` writes one list line per file and a tar whose members are the list's paths;
  - `archive` refuses, writing nothing, when the list exists, the tar exists, `manifest.yaml` is missing or `raw/`
    is missing;
  - `cross_check` refuses a misnamed answer, a referenced answer with no file, and a record count unlike the
    manifest's, and nothing is written;
  - `check` returns `[]` on an intact run, and `changed:`, `missing:` and `added:` naming the file for one changed
    byte, one deleted file and one added file; an added `.DS_Store` gives `[]`;
  - a round trip (archive, delete `raw/` and `judge/`, restore) gives the same bytes and `check` returns `[]`;
  - `restore` refuses when `raw/` exists, when `judge/` exists, when the tar is missing and when the list is missing;
  - `restore` refuses a tar member `../evil`, an absolute path, a symlink and `manifest.yaml` (outside the two
    folders), and afterwards `raw/`, `judge/` and the evil file do not exist;
  - a run with no `judge/` archives and restores `raw/` only;
  - `main`: `archive` returns 0, then 2 the second time; `check` returns 0, then 1 after a change; `restore` returns
    2 on a refusal; `check` with no `--run-id` checks every run that has a manifest, reports a run with no list as
    `no hash list` (exit 1), and exits 1 when there is no run at all (step 9.2).
  - Files: `experiments/tests/test_raw_archive.py`
  - Run: `pytest experiments/tests/test_raw_archive.py -q`
  - Pass: all pass.
  - Result: wrote experiments/tests/test_raw_archive.py, 56 tests pass (hash_tree, list, archive, cross_check, check, restore refusals incl. 5 bad-member kinds, main, Phase 9 check rules); also wrapped tar read errors in _verify_tar as ArchiveRefused.
- [x] 5.2 Write `experiments/tests/test_make_figures.py`. Tests:
  - `pinned_version()` is `3.10.8`, and equals `matplotlib.__version__`;
  - `f10_values` on the tracked `R/ablation/scores.json`: the five buckets in order; `k`, `n`, `rate` and `wilson95`
    equal `scores.json`'s; the four hit buckets' `n` sum to 79; no point is named `below 1.0`;
  - `f10_values` raises when one hit bucket's `n` is changed in a copy;
  - `f16_values` on the tracked `R/ablation/floor.json`: 401 points; 165 gives 0.0501 [0.0, 0.3038]; 134 gives 0.0
    [0.0, 0.2307]; 0 gives `corrected` None;
  - the F16 line's y data is `nan`, not 0, where `corrected` is None;
  - `save`: the PDF has no `/CreationDate`; the JSON ends with a newline and has no `written_at`; saving the same
    figure twice gives the same bytes;
  - `citable`: F10 is false (no field in `scores.json`), a source with `citable: true` gives true, `floor.json` gives
    false;
  - `main` on a temp results folder (a copy of the tracked `ablation/` files, a fake `raw/` and `judge/`, archived
    with `raw_archive.archive`): exit 0 and two `built` lines; a stale file in `figures/` is gone; a run with no
    hash list exits 1; with `raw/` deleted it exits 1, and the output names `raw/` and `make raw-restore`; with one
    changed `raw/` byte it exits 1 and `figures/` is not written; a run with no `ablation/` prints
    `not applicable`; a folder with no manifest prints `skipped`; a registered figure that applies to no run exits 1
    (monkeypatch `FIGURES`);
  - with `matplotlib.__version__` monkeypatched to `0.0`, `main` returns 2 and writes nothing.
  - Files: `experiments/tests/test_make_figures.py`
  - Run: `pytest experiments/tests/test_make_figures.py -q`
  - Pass: all pass.
  - Result: wrote experiments/tests/test_make_figures.py, 28 tests pass (pin, F10/F16 values vs tracked files and M08, nan gap, save bytes, citable, main guards).
- [x] 5.3 The whole experiments suite and lint.
  - Run: `pytest experiments/tests -q && ruff check experiments`
  - Pass: all pass (1,248 earlier tests plus the new ones); ruff clean.
  - Result: pytest experiments/tests: 1332 passed (1248 earlier + 56 + 28 new); ruff check experiments clean.

## Phase 6 — Live steps on the cost run (citable: no)

- [x] 6.1 Archive the cost run.
  - Run: `make raw-archive RUN_ID=2026-11-01T21-17-56_cfg4_judgecost 2>&1 | tee $T/evidence/raw-archive.out`
  - Pass: exit 0; it reports 523 files; `$R/archive.sha256` and `~/thesis-raw-archive/2026-11-01T21-17-56_cfg4_judgecost.tar`
    exist.
  - Result: exit 0; 523 files; wrote archive.sha256 (76,636 bytes) and ~/thesis-raw-archive/<run>.tar (2,426,880 bytes).
- [x] 6.2 A second archive is refused.
  - Run: `make raw-archive RUN_ID=2026-11-01T21-17-56_cfg4_judgecost 2>&1 | tee $T/evidence/raw-archive-again.out;
    echo "exit ${PIPESTATUS[0]}"`
  - Pass: non-zero exit and a `REFUSED` line; the list and the tar are unchanged (same `shasum` as after 6.1).
  - Result: second make raw-archive printed REFUSED (archive.sha256 exists), exit 2; list and tar have the same sha256 as after 6.1.
- [x] 6.3 An independent check of the list.
  - Run: `(cd $R && shasum -a 256 -c archive.sha256 | grep -vc ': OK$')`
  - Pass: prints `0`.
  - Result: shasum -a 256 -c archive.sha256 in the run folder: 523 OK, 0 not OK (grep -vc prints 0).
- [x] 6.4 Draw the figures, and measure memory.
  - Run: `/usr/bin/time -l make figures 2>&1 | tee $T/evidence/figures.out`
  - Pass: exit 0; two `built` lines; `$R/figures/` holds four files (two `.pdf`, two `.json`). Record the maximum
    resident set size in the Result line.
  - Result: exit 0; two built lines; figures/ holds 2 pdf + 2 json; maximum resident set size 87,752,704 bytes (about 84 MiB), 0.65 s; citable: no.
- [x] 6.5 Look at both PDFs (open them with the Read tool).
  - Pass: each has its title, axis labels, the δ line (F16), error bars and `n` labels (F10), and the footer
    `run 2026-11-01T21-17-56_cfg4_judgecost · citable: no`. Nothing overlaps or is cut off.
  - Result: read both PDFs: title, axis labels, delta line (F16), error bars and n labels (F10) and the footer 'run 2026-11-01T21-17-56_cfg4_judgecost · citable: no' are all present; nothing overlaps or is cut off.

## Phase 7 — Docs

- [x] 7.1 `docs/decisions.md`: add ADR-027 after ADR-026, with everything §3 "Docs" lists and an `Invalidates: none`
  line, and its row in the Summary table.
  - Files: `docs/decisions.md`
  - Run: `grep -n "ADR-027" docs/decisions.md`
  - Pass: the heading, the Summary row and `Invalidates:` inside the entry.
  - Result: added ADR-027 (archive, hash list, restore, private backup, the eleven-day limit, matplotlib pin, Invalidates: none) after ADR-026, and its Summary row; grep finds heading, row and Invalidates.
- [x] 7.2 `docs/contracts/interfaces.md`: add §I "The raw archive and figures (item 5.4, v0.35)" after "The noise
  floor", and move the status line, "Current version" and the versioning table to v0.35.
  - Files: `docs/contracts/interfaces.md`
  - Run: `grep -c "v0.35" docs/contracts/interfaces.md`
  - Pass: at least 4.
  - Result: added §I 'The raw archive and figures (item 5.4, v0.35)' (layout, file table, five targets) after the noise floor; status line, Current version, section heading and versioning row are v0.35 (grep -c = 4).
- [x] 7.3 `docs/architecture.md`, `docs/1-System Docs/Pipelines/Evaluation.md` and `CLAUDE.md`: change only the
  stale words §3 "Docs" names; add `archive.sha256` to the results tree in `architecture.md`.
  - Files: those three
  - Run: `grep -n "make_figures.py\|figure generators" docs/architecture.md "docs/1-System Docs/Pipelines/Evaluation.md" CLAUDE.md`
  - Pass: no line says the generators are not built or that the script does not exist.
  - Result: architecture.md: NOT BUILT line replaced by the three new scripts, requirements.txt and archive.sha256 added to the tree, 'Not yet runnable' row and 'Not built' item changed; Evaluation.md §3 row now built; CLAUDE.md 'Not built yet' no longer names figure generators; grep finds no stale line.

## Phase 8 — Run and verify (every done condition)

- [x] 8.1 `make verify`
  - Pass: exit 0; no FAIL; no SKIPPED target.
  - Result: make verify exit 0: go vet/build/tests ok, rag 94 passed, experiments 1332 passed, ruff clean, no SKIPPED, no FAIL.
- [x] 8.2 DC 1 — the archive.
  - Run: `wc -l < $R/archive.sha256; find $R/raw $R/judge -type f ! -name .DS_Store | wc -l;
    tar -tf ~/thesis-raw-archive/2026-11-01T21-17-56_cfg4_judgecost.tar | wc -l;
    pytest experiments/tests/test_raw_archive.py -q -k "cross_check or archive"`
  - Pass: 523, 523, 523; tests pass; 6.2 showed the second archive refused.
  - Result: list 523 lines, find 523 files, tar 523 members; 519 answers named by their hash, 519 of 519 answer_sha256 have a file, 622 request lines = records.count, every tar member hashes to its line; 56 tests pass (the -k also matched the whole file); 6.2 showed the second archive refused.
- [x] 8.3 DC 2 — the check and the restore refusals.
  - Run: `make raw-check RUN_ID=2026-11-01T21-17-56_cfg4_judgecost; pytest experiments/tests/test_raw_archive.py -q -k "check or restore"`
  - Pass: `ok` and exit 0; tests pass.
  - Result: make raw-check printed 'ok <run> (523 files)', exit 0; 31 check/restore tests pass (change, deletion, addition, bad members, refusals).
- [x] 8.4 DC 3 — the figures.
  - Run: `make figures; ls $R/figures; pytest experiments/tests/test_make_figures.py -q -k "main"`
  - Pass: two `built` lines, four files, tests pass.
  - Result: make figures exit 0, two built lines, figures/ holds 4 files; 11 main tests pass (zero-built exit, stale file, version guard, hash-list and raw guards).
- [x] 8.5 DC 4 — the values match the source.
  - Run: `pytest experiments/tests/test_make_figures.py -q -k "f10 or f16 or citable"`
  - Pass: all pass.
  - Result: 14 tests pass (F10 values vs scores.json and the 79 sum, F16 points vs M08 and the null/nan gap, citable rules).
- [x] 8.6 DC 5 — the same bytes.
  - Run: `make figures >/dev/null && shasum -a 256 $R/figures/* > $T/evidence/figures_1.sha && make figures
    >/dev/null && shasum -a 256 $R/figures/* > $T/evidence/figures_2.sha && diff $T/evidence/figures_1.sha
    $T/evidence/figures_2.sha && echo SAME`
  - Pass: prints `SAME`.
  - Result: two make figures runs (separate processes) gave identical sha256 for all 4 files; diff printed SAME (evidence/figures_1.sha, figures_2.sha).
- [x] 8.7 DC 6 — clean checkout plus archive.
  - Run: `make figures-clean-check 2>&1 | tee $T/evidence/clean-check.out`
  - Pass: exit 0; the first `make figures` failed naming `raw/`; restore and check passed; `IDENTICAL 4 files`.
  - Result: exit 0: step 3 make figures failed in the copy and named the missing raw/; step 4 restored and checked 1 run; step 5 'IDENTICAL 4 files' (copy of 1114 files; evidence/clean-check.out).
- [x] 8.8 DC 7 — tests untouched.
  - Run: `git status --short -- experiments/tests rag/tests ':(glob)gateway/**/*_test.go' | grep -v "^?? ";
    git status --short experiments/tests`
  - Pass: the first command prints nothing; the second prints only the two new test files. (`gateway/cmd/gateway/main.go`
    is the author's uncommitted drain fix, not a test, and not this task's.)
  - Result: first git status (excluding untracked) printed nothing; experiments/tests shows only the two new files test_make_figures.py and test_raw_archive.py.
- [x] 8.9 DC 8 — write-once intact.
  - Run: the 0.1 command with `sha_after.txt`, then `diff $T/evidence/sha_before.txt $T/evidence/sha_after.txt`
  - Pass: `diff` prints nothing; both files have 531 lines.
  - Result: sha_before.txt and sha_after.txt both 531 lines; diff prints nothing (raw/, judge/, ablation/, manifest.yaml unchanged).
- [x] 8.10 DC 9 — docs.
  - Run: `grep -n "### ADR-027" docs/decisions.md; grep -c "v0.35" docs/contracts/interfaces.md;
    grep -n "NOT BUILT: figures\|not yet runnable.*figures\|figure generators (\`make figures\`) | ⬜" docs/architecture.md "docs/1-System Docs/Pipelines/Evaluation.md"; grep -n "Not built yet" CLAUDE.md`
  - Pass: the ADR heading; a count of at least 4; no stale line; `CLAUDE.md`'s line no longer names the figure
    generators.
  - Result: ADR-027 heading at decisions.md:2213; interfaces.md has 4 'v0.35'; no stale 'not built' line in architecture.md or Evaluation.md; CLAUDE.md's 'Not built yet' no longer names the figure generators.

## Phase 9 — Fixes found during the build (run before Phase 4, then resume at 4.1)

Found 2026-11-12 after step 3.5: drawing a PDF fails because `fontTools` is also built for x86_64, and step 1.2's
check did not import it. design.md §3 now covers it (`requirements.txt`, Unknowns). The main session also tightened
`raw_archive check` with no `--run-id` (§3 `main`), because it passed with nothing checked.

- [x] 9.1 Reinstall fontTools for arm64, at the version already installed. The author approves this command.
  - Run: `pip3 install --force-reinstall --no-deps --no-cache-dir fonttools==4.61.0`
  - Pass: `python3 -c "import matplotlib.backends.backend_pdf, fontTools.subset, fontTools; print(fontTools.version)"`
    prints `4.61.0` with no error. If the install is denied or fails, stop and report.
  - Result: reinstalled fonttools 4.61.0 (universal2 wheel, user site); the pass import prints 4.61.0 with no error.
- [x] 9.2 `raw_archive.main`: `check` with no `--run-id` checks every run folder that has `manifest.yaml` (a run with no
  hash list is the problem `no hash list`), and exits 1 with `FAIL: no run to check` when there is none.
  - Files: `experiments/scripts/raw_archive.py`
  - Run: `ruff check experiments/scripts/raw_archive.py && python3 experiments/scripts/raw_archive.py check; echo "exit $?"`
  - Pass: ruff clean. Today the cost run has no list yet, so it prints `no hash list` for it and `exit 1`.
  - Result: check with no --run-id now checks every run with a manifest.yaml; cost run prints 'no hash list' and exit 1; an empty results dir prints 'FAIL: no run to check', exit 1; ruff clean.
