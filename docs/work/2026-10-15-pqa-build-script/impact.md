# Impact — pqa-build-script (item 3.1)

**Written by:** the `impact-analyst` subagent, 2026-10-15, against `spec.md` as of 14:59. I checked two
of its claims in the files myself (marked ✔). **Required phases:** impact · design · design-review ·
implementation. Contract: not required. Experiment: not required.

## The answer

**No frozen value is touched and no prior run is invalidated.** `experiments/results/` holds only
`.gitkeep`. The real risks are quiet ones that the first spec did not cover. In order of harm:

1. **The 175 stale files can leak into `v1`.** `fetch_corpus_v1.py:215-217` wrote
   `data/v1-draft/product-{category}-NN-{slug}.json` from the wrong dataset (Amazon-Reviews-2023). They
   have a valid `product-` prefix and `doc_id == filename`, so they pass `ingest.py:24` and gate G4.
   Spec open question 4 would put 3.2's drafts in the same directory. If 3.6 later copies
   `data/v1-draft/*.json` into `data/v1/`, about 175 wrong products enter the frozen corpus with no error.
2. **A5 cannot catch hash-seed nondeterminism.** Two runs in one pytest process share one
   `PYTHONHASHSEED`, so a set that leaks into a list passes. `sort_keys` sorts dict keys, not lists.
3. **`make demo-reset` can revert the manifest.** ✔ `Makefile:183-188` runs `git checkout -- data/` on any
   tracked change under `data/`. A regenerated, uncommitted `data/pqa-manifest.json` goes back to HEAD,
   and the interim files then disagree with it.
4. **A9's `grep -r fetch_corpus_v1` is the wrong command.** It matches a `.pyc`, walks 1.9 GB of
   `data/raw/pqa/`, and still misses `experiments/README.md:5` (it says "corpus fetcher").

## Touches

| Path | Change |
| :--- | :--- |
| `experiments/scripts/build_pqa.py` | new |
| `experiments/tests/test_build_pqa.py` | new |
| `experiments/scripts/fetch_corpus_v1.py` | delete (and its gitignored `.pyc`) |
| `data/pqa-manifest.json` | new tracked file |
| `data/v1-draft/pqa/<leaf>.jsonl` × 6 | runtime output, gitignored |
| `docs/architecture.md:78`, `:100`, tree `:95-101` | **must change**: name the builder, describe the `pqa/` output, list the manifest |
| `experiments/README.md:5` | **must change**: "corpus fetcher" |
| `.gitignore:27-29` | **must change** (comment only): says "re-run that script" |
| `.gitignore:22-25`, `:34-35` | stale comments, optional |
| `Makefile` and `architecture.md:189` (Corpus row) | **missing from the spec**: `Makefile:2` says add a target, do not invent ad-hoc commands |
| `data/README.md` | unknown, likely an edit (not read: `data/` was denied) |
| `Makefile:18`, `super-plan.md:366`, `category-choice/review.md:28` | history. Leave; the plan row is updated at `/done` |

## Module boundaries

- The paths fit `architecture.md`. The script and test directories are listed; so are `data/v1-draft/` and
  `data/raw/pqa/`. A tracked **file** in `data/` needs no new directory, and `data/workload-{version}.json`
  (`Makefile:402`) is the precedent. The tree should still list the manifest.
- **Ignore rules** (analyst tested them in a scratch repo; ✔ I read `.gitignore:26-36`):
  `data/v1-draft/**` and `data/raw/**` are ignored. **`data/pqa-manifest.json`, its `.tmp`, and any temp
  directory directly under `data/` are NOT ignored.** So the builder's temp directory must sit inside
  `data/v1-draft/`. That also keeps `os.replace` on one filesystem.
- The builder imports nothing from `rag/`.

## Frozen values and prior runs invalidated

- Not touched: `num_ctx`, `OLLAMA_NUM_PARALLEL`, embedding model, `DIM`, `top_k`, chunking, FLAT,
  eviction, capacity ratio, δ, `DATASET_VERSION = "dev-v0"`. **No ADR is needed.**
- **No glob reaches the new output.** `rag.ingest` reads `data/<DATASET_VERSION>/*.json`, non-recursive.
  `corpus_gate.py` globs `corpus_dir/*.json`, non-recursive. `make ingest` takes no path. `catalog/` reads
  Redis only. Nothing globs `data/*.json`, so the manifest is safe too.
- **Indirect link, binds before 3.6.** Three builder rules shape the question pool that `K` (and so
  `cache_capacity = round(0.25 × K)`) will come from: the skip rules, "first record wins" for prose, and
  surrogate replacement. They are free now. At the freeze they become part of the corpus definition, and
  changing one later needs a new `dataset_version`. Write them in `approvals.md` now and in `data-card.md` at 3.6.

## Cut-scope check

Nothing is reinstated. The builder only hashes, parses and counts: no classifier, no ML runtime, no
routing. The price / stock / carrier filters are 3.2's, as corpus-construction rules, not the dropped
runtime bypass classifier. Dropping community answer text agrees with the proposal ("community answers
are not ground truth"). It does not block the ePQA validation join, which keys on `asin` + `question_text`.

## Dependencies

**None new. Standard library only, and keep the old script's optional `certifi` import. It is needed
here:** `python3` is the python.org 3.13.0 build, its OpenSSL cert directory is empty, so plain
`ssl.create_default_context()` fails HTTPS to S3. `certifi` 2025.11.12 is already installed (pulled in
by `httpx` and `requests`) but not declared for `experiments/`. If it is missing, fail loudly and say how
to fix it. Do not use `requests` or `httpx`.

## Test and lint plumbing

- **`make test` picks up the new file with no config change.** `Makefile:290` runs
  `pytest experiments/tests -q`; `conftest.py:7` puts `experiments/scripts/` on `sys.path`; 155 tests are
  collected today.
- **`make lint` finds ruff** (`Makefile:20` adds the user base to `PATH`; ruff 0.16.3). `experiments/` has
  no ruff config, so ruff defaults apply: line length 88, a large default rule set that floats with the
  ruff version. A blind `except` is flagged for free, which supports design D7.
- **Tests must never write under `data/`.** Every output path (interim dir, manifest, temp dir) is a
  parameter, and tests use `tmp_path`. Otherwise `make test` rewrites the tracked manifest.
- **A6:** the standard library's `SimpleHTTPRequestHandler` ignores `Range` and answers 200. The fake
  server needs its own handler. Test both 206 and the 200 fallback (truncate and restart).
- `make verify` never runs A7. That is correct.

## Risks the spec missed

| # | Risk | Fix |
| :-: | :--- | :--- |
| 1 | Stale-file contamination (top item above) | Either delete the 175 files (author's OK needed), or decide now that 3.2 writes to a fresh `data/v1-draft/products/` |
| 2 | A5 blind to hash seed | Run the builder twice as **subprocesses** with `PYTHONHASHSEED=0` and `=1`; compare bytes |
| 3 | `make demo-reset` reverts the manifest | Narrow its restore to `data/dev-v0/` (one line), or record the hazard |
| 4 | The reader half of all-or-nothing has no owner: a crash between renames leaves new interim files beside an old manifest | Rename the manifest **last**, and put "3.2 checks each interim sha256 against the manifest before reading" in 3.2's spec |
| 5 | A9 command is wrong | `git grep -n fetch_corpus_v1`, plus a manual look at the README row |
| 6 | A8 checks half | Also assert `git check-ignore data/pqa-manifest.json` exits **1** (not ignored) |
| 7 | The real HTTPS / S3 path is never run (files are on disk). Double-encoding `&` gives a 403 that looks like a permission error. An unquoted `amazon_pqa_led_&_lcd_tvs.json` in shell backgrounds the command | Add one by-hand HEAD request per leaf to A7 (200 and `Content-Length` = pinned bytes). Quote the name in any recipe |
| 8 | A7 reproduces the probe only if the skip rule matches `probe.py:88-91` (strip, then test empty). **71,794 is a sum of per-leaf distinct asins**, not a cross-leaf distinct count. "Questions" counts records, not distinct `question_id`s | Keep both meanings apart in the manifest |
| 9 | Spec says "two stops" but A7 cites "Stop 3" | Define Stop 3 in the spec |
| 10 | Two carry-forwards unstated: the interim's `leaf` must not become `category` or reach embedded text (category-choice `review.md:25`); 1.4's note on strict UTF-8 is discharged by open question 3 | Cite both |
| 11 | A non-string bullet or description passed through `str()` puts `"['…']"` into prose | Count a per-field `bad_type` instead of coercing |
| 12 | The category-choice trail assumed "the 3.1 builder" writes the product records; the spec defers that to 3.2 | Close open question 4 before 3.2 opens |

**Smallest change.** The analyst says to **cut `--check`** (design D6): run the builder, then
`git diff --exit-code data/pqa-manifest.json`, which gives the same guarantee with no code. Keep Stop 3,
A11 and the cross-leaf counts. *Decision on this goes in the merge pass after the design review.*

## Unknowns

- A nested `data/.gitignore` may exist (`data/` could not be listed). A8's real `git check-ignore` closes it.
- `data/README.md` was not read. It likely needs the builder's name and the manifest path.
- What is in `data/v1-draft/` is inferred from the old script, not listed.
- The real field set, prose conflicts, duplicate `question_id`s, cross-leaf asins, any field empty in a
  whole leaf: all need the first real run (`design.md` §7).
- Peak memory while parsing the 499,535-record leaf: estimated 250 – 500 MB, not measured. Do not run it
  during a measured run.
