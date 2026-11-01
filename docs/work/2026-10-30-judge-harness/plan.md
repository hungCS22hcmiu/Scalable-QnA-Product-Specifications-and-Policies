# Plan — Judge harness, and P1 first

Design: design.md (approved 2026-10-31)

Order matters in two places. The P1 documents (Phase 3) are written and dated before the first verdict
(Phase 5). And the judge never loads while the generator is loaded. Three steps stop for the author:
4.6, 5.2, and any stop rule that fires (4.7, 5.3, 6.7). Below, **pressure** means
`sysctl -n kern.memorystatus_vm_pressure_level`, read right before the step and written in its `Result:`
line (1 green, 2 yellow, 4 red). Every model-loading step here is `citable: no`. It may run at 1 or 2, and
it stops at 4.

## Phase 1 — Implement

- [x] 1.0 Record the existing tests before any change, for DC 12
  - Files: `docs/work/2026-10-30-judge-harness/evidence/tests-before.txt`
  - Run: `git ls-files -co --exclude-standard -- '*_test.go' 'rag/tests/*.py' 'experiments/tests/*.py' | sort | xargs shasum -a 256 > docs/work/2026-10-30-judge-harness/evidence/tests-before.txt`
  - Pass: the file lists every existing test file with its hash, the untracked ones included
  - Result: wrote evidence/tests-before.txt, 95 test files hashed (the 3 untracked ones, mutation_env_test.go and two rag/tests files, included)

- [x] 1.1 Add `RETRIEVAL_VERSION = "adr-021"`, with a one-line comment: every ADR that changes retrieval
  bumps it
  - Files: `rag/src/rag/config.py`
  - Run: `cd rag && python3 -c "from rag import config; print(config.RETRIEVAL_VERSION)"`
  - Pass: prints `adr-021`
  - Result: added `RETRIEVAL_VERSION = "adr-021"` to rag/src/rag/config.py; the check prints `adr-021`, ruff clean

- [x] 1.2 Write the frozen judge's two files. `prompt-v1.txt` is §3's prompt byte for byte, ending in one
  newline. `judge-v1.json` is §3's record, with `digest` from `/api/tags` (this loads no model) and
  `prompt_sha256` from the file
  - Files: `experiments/judge/prompt-v1.txt`, `experiments/judge/judge-v1.json`
  - Run: `curl -s localhost:11434/api/tags | jq -r '.models[] | select(.name=="gemma3:4b-it-q4_K_M") | .digest'` and `shasum -a 256 experiments/judge/prompt-v1.txt`
  - Pass: both values equal the ones in `judge-v1.json`; the prompt holds exactly the three placeholders
    `{question}`, `{reference}`, `{answer}`
  - Result: wrote experiments/judge/prompt-v1.txt (cut from design.md, 19 lines, 3 placeholders) and judge-v1.json; digest a2af6cc3... and prompt sha256 5e827704... equal the live values

- [x] 1.3 `judge_references.py`, the gold half: `load_split`, `doc_chunk_ids`, `gold_chunk_ids`,
  `gold_problems`, `gold_counts`, and the CLI subcommand `gold-check` (prints counts by stratum and
  `answerable`, exits 1 on any problem)
  - Files: `experiments/scripts/judge_references.py`
  - Run: `ruff check experiments/scripts/judge_references.py && python3 experiments/scripts/judge_references.py gold-check --help`
  - Pass: ruff is clean; the help prints `--split`
  - Result: added the gold half (load_split, corpus_chunks/doc_chunk_ids, gold_chunk_ids, gold_problems, gold_counts, gold-check) to experiments/scripts/judge_references.py; ruff clean, help prints --split

- [x] 1.4 `judge_references.py`, the reference half: `answer_in_process`, `make_reference`,
  `version_block`, `build`, and the CLI subcommand `build`. `build` reads the pressure level, prints it,
  and refuses at 4. At the end it prints the decline count of `answerable: true` references and the
  sha256 of `index.jsonl`
  - Files: `experiments/scripts/judge_references.py`
  - Run: `ruff check experiments/scripts/judge_references.py && python3 experiments/scripts/judge_references.py build --help`
  - Pass: ruff is clean; the help prints `--split` and `--out`
  - Result: added answer_in_process, make_reference, version_block, build (writes out.partial, renames on success; refuses at pressure 4); ruff clean, help prints --split and --out

- [x] 1.5 `judge_references.py`: `sheet` and `score`, and their CLI subcommands. The sheet is Markdown,
  one row per pair (`qa_id`, stratum, gold text, reference, a `sufficient:` cell left empty)
  - Files: `experiments/scripts/judge_references.py`
  - Run: `ruff check experiments/scripts/judge_references.py && python3 experiments/scripts/judge_references.py sheet --help`
  - Pass: ruff is clean; the help prints `--n`, `--min-b-within` and `--seed`
  - Result: added sheet and score; ruff clean, help prints --n, --min-b-within and --seed

- [x] 1.6 `run_manifest.py`, the readers: `read_records`, `arms`, `parse_gateway_log`, `admissibility`
  (§3, "Files")
  - Files: `experiments/scripts/run_manifest.py`
  - Run: `ruff check experiments/scripts/run_manifest.py`
  - Pass: clean
  - Result: added read_records, arms, parse_gateway_log, i9_violations, admissibility to experiments/scripts/run_manifest.py; ruff clean

- [x] 1.7 `run_manifest.py`, the writer: `build_manifest`, `check_manifest`, and the CLI `write` and
  `check`. `write` refuses while `:8080` listens or when `manifest.yaml` exists. It builds `Frozen` from
  the same arguments `make env-check` passes, and takes the `ENVELOPE` line from `env_check.observe` and
  `envelope_line`. The YAML has exactly §3's keys, in §3's order
  - Files: `experiments/scripts/run_manifest.py`
  - Run: `ruff check experiments/scripts/run_manifest.py && python3 experiments/scripts/run_manifest.py write --help`
  - Pass: ruff is clean; the help prints `--run-id`, `--gateway-log` and `--split`
  - Result: added build_manifest, check_manifest (optional log_path), write (refuses :8080 listening or existing manifest; env-check logic via env_check.observe) and check; ruff clean, write --help prints --run-id, --gateway-log, --split

- [x] 1.8 `replay.py`: `replay(split, url, seed=7) -> Counter`, and a CLI. It sends one query at a time in
  a seeded shuffle, leaves `product_id` out when it is empty, sends `X-Thesis-Stratum`, and prints
  progress and the pressure level every 50 requests
  - Files: `experiments/scripts/replay.py`
  - Run: `ruff check experiments/scripts/replay.py && python3 experiments/scripts/replay.py --help`
  - Pass: ruff is clean; the help prints `--split` and `--url`
  - Result: added experiments/scripts/replay.py (order, request_for, http_post, replay; stops at pressure 4); ruff clean, help prints --split and --url

- [x] 1.9 `judge.py`, the pure half: `verdict_key`, `parse_verdict`, `load_answers`, `join`,
  `retrieval_miss`, `layer` (§3, "The verdict key" and "The error layer")
  - Files: `experiments/scripts/judge.py`
  - Run: `ruff check experiments/scripts/judge.py`
  - Pass: clean
  - Result: added verdict_key, parse_verdict, load_answers, join, retrieval_miss, layer (and entry_misses) to experiments/scripts/judge.py; ruff clean

- [x] 1.10 `judge.py`, the run half: `preflight`, `ask_judge`, `run`, `sanity`, and the CLI `run` and
  `sanity`. `run` reads the pressure level, prints it, refuses at 4, and stores every reading in
  `summary.json`. After the last key it re-judges 30 keys (seed 7) and stores the flips in `summary.json`
  - Files: `experiments/scripts/judge.py`
  - Run: `ruff check experiments/scripts/judge.py && python3 experiments/scripts/judge.py run --help`
  - Pass: ruff is clean; the help prints `--run-id`
  - Result: added load_judge, judge_problems, preflight, ask_judge, run (writes judge.partial/, renames to judge/; pressure readings and 30 re-judged keys in summary.json), sanity and the CLI; ruff clean, run --help prints --run-id

- [x] 1.11 Makefile targets, all on `$(PY)`, each with a `##` help line: `run-manifest RUN_ID= GATEWAY_LOG=
  SPLIT=` (passes `env-check`'s four frozen arguments), `run-manifest-check RUN_ID=`, `judge-gold-check
  SPLIT=`, `judge-references SPLIT=`, `judge RUN_ID=`, `judge-sanity FILE=`, `replay SPLIT=`. A missing
  argument fails with a usage line, as `update-set-check` does
  - Files: `Makefile`
  - Run: `make help | grep -E 'run-manifest|judge|replay'` and `make judge 2>&1 | head -2`
  - Pass: seven targets listed; `make judge` with no `RUN_ID` fails with a usage line
  - Result: added judge-gold-check, judge-references, replay, run-manifest, run-manifest-check, judge, judge-sanity to the Makefile (and .PHONY); help lists 7, make judge with no RUN_ID prints a usage line and exits 2

- [x] 1.12 `.gitignore`: add `experiments/references/` and `experiments/results/*/judge/`, each with a
  one-line reason (question text and PQA-grounded answers)
  - Files: `.gitignore`
  - Run: `git check-ignore -v experiments/references/validation/index.jsonl experiments/results/x/judge/verdicts.jsonl; git check-ignore experiments/results/x/manifest.yaml`
  - Pass: the first two are ignored; `manifest.yaml` is not (the second command prints nothing)
  - Result: added experiments/references/, experiments/results/*/judge/ (and judge.partial/, the in-progress copy) to .gitignore; the first two paths are ignored, manifest.yaml is not (second command prints nothing)

## Phase 2 — Unit tests

All tests use fakes and temp folders: no Ollama, no Redis, no network.

- [x] 2.1 The verdict key's golden value, computed outside Python. Input: `query_raw` =
  `Is the café mug 12 oz?` (one non-ASCII character, so a character-count netstring gives a different key),
  `product_id` = `product-x`, `answer_sha256` = the empty answer's hash
  - Files: `docs/work/2026-10-30-judge-harness/evidence/golden-key.txt`
  - Run: `q='Is the café mug 12 oz?'; p='product-x'; a=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855; ns() { printf '%s:%s,' "$(printf '%s' "$1" | wc -c | tr -d ' ')" "$1"; }; { printf 'vk1:'; ns "$q"; ns "$p"; ns "$a"; } | shasum -a 256 | tee docs/work/2026-10-30-judge-harness/evidence/golden-key.txt`
  - Pass: one 64-character hex value; the netstring for `q` starts `23:` (23 bytes, 22 characters)
  - Result: wrote evidence/golden-key.txt: d2f8597f95e17b78e95c3a62c7f4c2c229e25fe21bb544e5c45647200c5fbb41, computed with printf/wc/shasum; the q netstring starts 23: (23 bytes, 22 characters)

- [x] 2.2 `test_judge.py`, DC 4: the golden key from 2.1; `(q1, A)` and `(q2, A)` give two keys; one
  `(q, A)` under two `product_id`s gives two keys; `product_id` `""` is a valid field
  - Files: `experiments/tests/test_judge.py`
  - Run: `pytest experiments/tests/test_judge.py -q -k key`
  - Pass: all pass; the golden value in the test equals `golden-key.txt`
  - Result: wrote experiments/tests/test_judge.py with 12 key tests (golden value d2f8597f..., equal to evidence/golden-key.txt; two-keys cases; boundary cases); pytest -k key: 12 passed

- [x] 2.3 `test_judge.py`, DC 9: one or more tests per DC 9 bullet, each named `test_dc9_<topic>`, with a
  fake judge and a fake Ollama. The fixture run gives each layer (`retrieval`, `generation`,
  `inherited`, `reuse`, `undecided`) exactly once. The parse tests include `INCORRECT`, `correct`,
  `CORRECT.`, `INCORRECT CORRECT` and an empty reply. Each preflight refusal in §3 has its own case
  - Files: `experiments/tests/test_judge.py`
  - Run: `pytest experiments/tests/test_judge.py -q`
  - Pass: all pass; `grep -c 'def test_dc9_' experiments/tests/test_judge.py` is at least 7
  - Result: added 56 test_dc9_ tests to experiments/tests/test_judge.py (fixture run gives each layer once; parse, join, preflight refusals, write-once, re-judge, sanity); 111 pass; mutation checks on parse, key, layer, join, preflight, hash check and output path each made tests fail, then judge.py was restored (identical)

- [x] 2.4 `test_judge_references.py`, DC 6 and DC 7: gold order (documents in `doc_ids` order, chunks in
  ordinal order); each `gold_problems` failure (unknown doc, wrong kinds for the stratum, a non-empty
  `reference_answer`, a set over 24,000 characters); `make_reference` refuses an empty list and a reply with
  other `source_chunk_ids`; `build` refuses a folder that exists
  - Files: `experiments/tests/test_judge_references.py`
  - Run: `pytest experiments/tests/test_judge_references.py -q`
  - Pass: all pass
  - Result: wrote experiments/tests/test_judge_references.py, 69 tests (gold order, each gold_problems failure, make_reference refusals, answer_in_process with the handler's collaborators faked, build refusals and write-once, sheet and score); 69 pass; mutation checks on gold order, sources check, empty list, write-once, index check, pressure, dedupe and limits each failed tests, then the script was restored (identical)

- [x] 2.5 `test_run_manifest.py`, DC 2: `arms` raises when one differs; the log parse reads each value and
  raises on another run id or a missing value; admissibility fails each of rule 6 (no `shutting down`
  line, and an `INCOMPLETE` line), rule 10, rule 12 and I9; `check_manifest` refuses a missing field, a
  record whose arm differs, and a log arm that differs from the records
  - Files: `experiments/tests/test_run_manifest.py`
  - Run: `pytest experiments/tests/test_run_manifest.py -q`
  - Pass: all pass
  - Result: wrote experiments/tests/test_run_manifest.py, 115 tests (arms, log parse per value and per refusal, rules 6/10/12 and I9, build_manifest key order and values, each check refusal, write refusals); 115 pass; mutation checks on each rule and refusal failed tests, then the script was restored; also added an empty-records guard to arms()

- [x] 2.6 `test_replay.py`: the same seed gives the same order; the header is sent; no `product_id` key
  when it is empty
  - Files: `experiments/tests/test_replay.py`
  - Run: `pytest experiments/tests/test_replay.py -q`
  - Pass: all pass
  - Result: wrote experiments/tests/test_replay.py, 23 tests (same seed same order, header sent, no product_id key when empty or absent, one-at-a-time, counts, pressure every 50 and stop at 4, HTTP wrapper); 23 pass; mutation checks (no shuffle, unseeded, product_id always, no header, 503 as error, pressure 4) each failed tests, then the script was restored

- [x] 2.7 The whole suite and lint
  - Run: `make lint && make test`
  - Pass: no FAIL; any SKIPPED listed by name
  - Result: make lint clean (gofmt, go vet, ruff); make test exit 0: Go packages ok, rag 83 passed, experiments 1096 passed (318 new); no FAIL, nothing SKIPPED; the hash diff against tests-before.txt shows only 4 new test files (0 changed or removed)

## Phase 3 — The P1 documents, before any verdict

- [x] 3.1 `docs/contracts/metrics.md` (DC 1). Dated at the top, `counting-v1`. One entry per metric row of
  `docs/learning/Final_Proposal.md` §9.1 (6 rows) and §9.2 (11 rows), plus μ_gen, μ_hit and the miss-path
  error rate: 20 entries, each headed `### M<nn> — <name>`, each with the six parts of §3. Also: the five
  error layers as rules over stored fields, reported apart; the three counting choices as §3 states them
  (every wrong hit counts; `answerable: false` counts, with its own row; the 2 % `UNPARSED` rule); `cache`
  and `refusal_cause` are the served decision and `source_overlap` a counterfactual (ADR-019). Formulas
  §H already gives are cited, not restated
  - Files: `docs/contracts/metrics.md`
  - Run: `grep -c '^### M[0-9][0-9] — ' docs/contracts/metrics.md; grep -c TODO docs/contracts/metrics.md`
  - Pass: `20`, then `0`
  - Result: wrote docs/contracts/metrics.md (counting-v1, dated 2026-11-01): 20 entries M01-M20, each with the six parts; shared rules R1-R8 (cells, splits, served decision vs counterfactual ADR-019, verdicts and the 2 % UNPARSED rule, answerable:false row, five error layers reported apart, Wilson); grep -c entries gives 20, grep -c TODO gives 0

- [x] 3.2 `interfaces.md` v0.28: §H's "item 5.1 fixes it" becomes the key formula from §3, with the pinned
  key from 2.1; new §I gives `manifest.yaml`, the reference set's layout and the judge output's layout;
  a v0.28 row in the version table
  - Files: `docs/contracts/interfaces.md`
  - Run: `grep -c 'item 5.1 fixes it' docs/contracts/interfaces.md; grep -F "$(cut -c1-64 docs/work/2026-10-30-judge-harness/evidence/golden-key.txt)" docs/contracts/interfaces.md | head -1; grep -n '^## I\. \|Current version: v0.28' docs/contracts/interfaces.md`
  - Pass: `0`; the pinned key is found; both headings are found
  - Result: interfaces.md v0.28: section H's open key sentence replaced by the vk1 formula, its inputs and the pinned key d2f8597f... (found by the grep); new section I (manifest.yaml with the six-field generator block, reference set, judge output, what make judge refuses); v0.28 row, Current version and the status line updated; the grep for the old phrase gives 0

- [x] 3.3 `decisions.md`: ADR-022 (DC 5) in the existing ADR form: the model, its digest, the prompt
  version and sha256, the options, the gold-anchored reference and why (36 of 42 B-within passes), the two
  rubric choices, `Invalidates: none — no runs yet`. Its summary row. The P1 row in "Open questions" is
  marked closed, pointing at 5.1's trail
  - Files: `docs/decisions.md`
  - Run: `grep -n '^### ADR-022\|^| ADR-022' docs/decisions.md; grep -c "$(jq -r .digest experiments/judge/judge-v1.json)" docs/decisions.md`
  - Pass: both lines found; the digest appears at least once
  - Result: decisions.md: ADR-022 added at the end in ADR-021's form (model and full digest, prompt version and sha256, options, gold-anchored reference and why with 26 of 167 and 36 of 42, the two rubric choices, Invalidates: none — no runs yet), its summary row after ADR-021's, and the P1 row marked closed pointing at the trail; both greps find their lines, the digest appears once

- [x] 3.4 `docs/preregistration.md` (DC 3): append-only, a rule at the top saying so. The first entry,
  dated: the judge model and digest, the prompt version and sha256, the options, the sha256 of
  `judge-v1.json`, the verdict key (`vk1`), the reference definition (gold-anchored), `counting-v1`.
  Item 6.1's four entries named, left empty
  - Files: `docs/preregistration.md`
  - Run: `grep -c "$(shasum -a 256 experiments/judge/judge-v1.json | cut -c1-64)" docs/preregistration.md`
  - Pass: at least `1`
  - Result: wrote docs/preregistration.md: append-only rule at the top; Entry 1 dated 2026-11-01 with the judge model and full digest, prompt-v1 and its sha256, the options, judge-v1.json's sha256 1beb1fbd..., the vk1 key with the pinned value, the gold-anchored reference definition, counting-v1, and three stop rules; the four item 6.1 names (6.1-a to 6.1-d) reserved, empty; the grep finds the hash once, and judge.load_judge confirms the file contains it

- [x] 3.5 `architecture.md` lists the new files and folders (`experiments/judge/`,
  `experiments/references/`, the four scripts); `experiments/README.md` no longer says the judge and replay
  harnesses do not exist
  - Files: `docs/architecture.md`, `experiments/README.md`
  - Run: `grep -c 'judge.py\|run_manifest.py\|replay.py\|judge_references.py' docs/architecture.md; grep -n 'judge harness.*do NOT exist\|replay harness, judge harness' experiments/README.md docs/architecture.md`
  - Pass: at least 4; the second grep prints nothing
  - Result: architecture.md lists the four scripts (one line each in the tree), experiments/judge/, experiments/references/{split}/, results/{run_id}/judge/, docs/contracts/metrics.md, docs/preregistration.md, a command-table row for the 7 targets and the inventory rows; experiments/README.md says the judge, replay, reference and manifest scripts exist and that only the figure generators do not; first grep gives 5, second prints nothing

## Phase 4 — Gold and references (the generator loads)

- [x] 4.1 DC 6, the gold audit, offline
  - Run: `make judge-gold-check SPLIT=validation`
  - Pass: exits 0; prints counts by stratum and by `answerable` (622 queries, 40 `answerable: false`, 33
    with two documents)
  - Result: exit 0; 622 queries (622 distinct pairs); A 371, B-cross 11, B-within 124, C 83, D 33; answerable true 582, false 40; 33 with two documents

- [x] 4.2 The index in Redis is the frozen corpus
  - Run: `make corpus-index-check`
  - Pass: exits 0
  - Result: exit 0; PASS, the index is the v1 corpus (539 chunks; ids, texts, vectors and the embedding model's digest checked)

- [x] 4.3 DC 7, the references. Read pressure first. Run it in the background; it takes about an hour
  - Run: `make judge-references SPLIT=validation 2>&1 | tee docs/work/2026-10-30-judge-harness/evidence/private/references.log`
  - Pass: exits 0; `experiments/references/validation/` holds `index.jsonl` (one row per distinct
    `(question, product_id)`), `answers/` and `version.json`; the log ends with the decline count and the
    index hash
  - citable: no
  - Result: pressure 1 before the run, level 2 (yellow) at every progress line during it (citable: no, so it ran); 622/622 references, 608 answer files, index.jsonl 622 rows; 78 of 582 answerable:true references decline; index.jsonl sha256 00c9a33310a66542d739a860e3e77a162658a5dddaefa00fbc3e8ea30ca558e3

- [x] 4.4 Append the second dated entry to `preregistration.md`: the reference set's hash (the sha256 of
  `index.jsonl`) and its `version.json`
  - Files: `docs/preregistration.md`
  - Run: `grep -c "$(shasum -a 256 experiments/references/validation/index.jsonl | cut -c1-64)" docs/preregistration.md`
  - Pass: `1`
  - Result: appended Entry 2 (2026-11-01) at the end, after the 6.1 names; it holds the index.jsonl sha256 00c9a333..., version.json's sha256 ed6e2878... and every version.json field; Entry 1 untouched; the grep prints 1

- [x] 4.5 DC 8, the sufficiency sheet
  - Run: `python3 experiments/scripts/judge_references.py sheet --split validation --out docs/work/2026-10-30-judge-harness/evidence/private/sufficiency-v1.md`
  - Pass: 30 rows, at least 10 of them B-within; the file is gitignored (`git check-ignore` prints it)
  - Result: wrote evidence/private/sufficiency-v1.md: 30 rows (A 11, B-within 17, C 2), all 30 `sufficient:` cells empty; git check-ignore prints the path (.gitignore:52)

- [x] 4.6 **STOP for the author.** Report the decline count from 4.3, and ask the author to mark every
  `sufficient:` and `reference right:` cell in `sufficiency-v2.md` (Phase 9). Resume only when the author says it is marked
  - Pass: the author confirms
  - Result: the author gave all 60 marks in chat (2026-11-01); the main session copied them into sufficiency-v2.md row by row (60 changed lines, rows 1–30 checked in order)

- [x] 4.7 Score the sheet. **Stop rule:** more than 3 `no` in either cell → stop and report; no verdict runs
  - Run: `python3 experiments/scripts/judge_references.py score docs/work/2026-10-30-judge-harness/evidence/private/sufficiency-v2.md`
  - Pass: 30 pairs marked in both cells, at most 3 `no` in each
  - Result: on v2 the stop rule fired (reference right 25 yes / 5 no); passed on v3 at step 10.11 (sufficient 28 / 2, reference right 27 / 3, exit 0), with the 4B set of Entry 4

## Phase 5 — Sanity pairs (the judge loads)

- [x] 5.1 Draft the 12 sanity rows (DC 10), two of each kind: the return/warranty trap, a wrong product, a
  bare "Yes." against a "No" reference, a same-polarity bare "Yes.", an unanswerable question with an
  invented answer, a true paraphrase. Each row: `qa_id` from the validation split, an authored `answer`,
  `expected`, and a `kind` field
  - Files: `docs/work/2026-10-30-judge-harness/evidence/private/sanity-v1.jsonl`
  - Run: `jq -r .kind docs/work/2026-10-30-judge-harness/evidence/private/sanity-v1.jsonl | sort | uniq -c`
  - Pass: six kinds, two rows each
  - Result: drafted by the main session on 2026-11-01 while the author marked v3 (10.10), before 4.7, against the 4B set (Entry 4); six kinds, two rows each, 8 INCORRECT and 4 CORRECT; every `qa_id` is in the set and none is one of the sheet's 30; if 10.11 fails and the set changes, redraft

- [x] 5.2 **STOP for the author.** Ask the author to check every `expected` in `sanity-v1.jsonl`. Resume
  only when the author confirms
  - Pass: the author confirms
  - Result: the main session showed each row's question, 4B reference, answer and `expected` in chat; the author confirmed 12 of 12 (2026-11-01). Row 12's answer lost the word "about" before the check

- [x] 5.3 Unload the generator, read pressure, then run the sanity pairs. **Stop rule:** any wrong verdict
  → stop and report. Do not edit the prompt: a new prompt is a new version and a new DC 3 entry, the
  author's call
  - Run: `ollama stop qwen3.5:2b-q4_K_M; curl -s localhost:11434/api/ps | jq -r '.models[].name'; make judge-sanity FILE=docs/work/2026-10-30-judge-harness/evidence/private/sanity-v1.jsonl`
  - Pass: `/api/ps` does not list `qwen3.5:2b-q4_K_M`; 12 of 12 correct, 0 `UNPARSED`; exit 0
  - citable: no
  - Result: 2026-11-01 ~21:10 +07, the judge's first verdict (Entry 4 was written ~17:34 the same day); `/api/ps` empty before, judge digest a2af6cc3…f5a; `12 of 12 correct, 0 UNPARSED`; pressure 1 before, 2 after (citable: no); the exit code was lost to zsh's `PIPESTATUS`, so it was run again with the judge still loaded: `make exit 0` and the same 12 verdicts; logs `evidence/private/sanity-run-1.log`, `-2.log`

## Phase 6 — The cost run (DC 11)

All of it is `citable: no`, and the run's `raw/` stays gitignored. No frontier is computed from it, and no
rate from it is used for any choice. `RUN_ID` below is `<date>T<time>_cfg4_judgecost`, fixed in 6.2.

- [x] 6.1 Read pressure, stop the judge, reset the cache
  - Run: `ollama stop gemma3:4b-it-q4_K_M; make cache-reset`
  - Pass: `cache-reset` exits 0
  - Result: 2026-11-01 21:18 +07, pressure 2 before (citable: no); the judge stopped (`/api/ps` empty); `make cache-reset` exit 0, deleted t1 30, t2 29, lru 29, dep 86, entry 29 (leftovers of earlier tests), corpus 539 keys intact

- [x] 6.2 Start the gateway in the background (it loads both models)
  - Run: `RUN_ID=$(date +%Y-%m-%dT%H-%M-%S)_cfg4_judgecost CONFIG_ID=4 SUPPORT_GATE=on MUTATION=off CACHE_CAPACITY=156 make dev 2>&1 | tee docs/work/2026-10-30-judge-harness/evidence/private/gateway-cost.log`
  - Pass: the log shows `evaluation log -> …/<RUN_ID>/raw/`, `support_gate=on`, `mixed_lane=off` and
    `cache_capacity=156`
  - citable: no
  - Result: RUN_ID `2026-11-01T21-17-56_cfg4_judgecost`; pressure 1 before (citable: no); log (evidence/private/gateway-cost.log) shows `evaluation log -> …/2026-11-01T21-17-56_cfg4_judgecost/raw/requests.jsonl`, `support_gate=on`, `mixed_lane=off` (lane_band=[0.20,0.20)), `cache_capacity=156`, tau=0.850; gateway binary pid 47391 (go run parent 47386) listens on :8080, rag.server pid 47372; Ollama's LLAMA_ARG_CACHE_RAM and CTX_CHECKPOINTS are 0 (ADR-017 fine)

- [x] 6.3 Replay the validation split once (about 1–2 hours)
  - Run: `make replay SPLIT=validation`
  - Pass: 622 requests sent; no SHED; pressure never 4
  - citable: no
  - Result: 622 of 622 sent, 622 HTTP 200, `make replay` exit 0, 0 SHED; raw/requests.jsonl 622 rows: 528 MISS, 94 TIER2_HIT, 0 TIER1_HIT; wall 1963 s (21:18:39 to 21:51:22 +07, 32.7 min, not the 1-2 h guessed); pressure 1 at every one of the 13 replay progress lines and all 33 one-minute samples (peak 1, never 4; swap used 4.1-4.2 GB); citable: no; logs evidence/private/replay-cost.log, pressure-replay.log

- [x] 6.4 Stop the gateway with SIGINT
  - Run: `kill -INT <the gateway's pid>`
  - Pass: the log has `shutting down, flushing the evaluation log` and no `THIS RUN IS INCOMPLETE`; `:8080`
    no longer listens
  - Result: `kill -INT 47391` (the gateway binary) at 21:51:46 +07; the log has `shutting down, flushing the evaluation log` once and `THIS RUN IS INCOMPLETE` 0 times; `lsof` shows nothing on :8080 or :50051, `make dev` exited 0; raw/requests.jsonl 622 rows, raw/answers/ 519 files

- [x] 6.5 The manifest (DC 2, live). Read pressure: `env-check`'s probe warms the generator again
  - Run: `make run-manifest RUN_ID=<RUN_ID> GATEWAY_LOG=docs/work/2026-10-30-judge-harness/evidence/private/gateway-cost.log SPLIT=validation && make run-manifest-check RUN_ID=<RUN_ID> GATEWAY_LOG=docs/work/2026-10-30-judge-harness/evidence/private/gateway-cost.log`
  - Pass: both exit 0; `manifest.yaml` says `admissible: true` and `arms` is `{4, off, on, off}`
  - citable: no
  - Result: pressure 1 before and after (citable: no); `make run-manifest` exit 0 and `make run-manifest-check` (with GATEWAY_LOG) exit 0, `run-manifest-check: ok`; manifest.yaml: arms {config_id 4, mutation off, support_gate on, mixed_lane off}, records 622 (MISS 528, TIER2_HIT 94), admissibility rules 6, 10, 12, I9 all true, `admissible: true`, ENVELOPE np=1 ctx=8192 version=0.33.2, git_sha 883aea5 dirty false, retrieval adr-021 top_k 5, tau 0.85; manifest.yaml is not gitignored (tracked, no text in it)

- [x] 6.6 Unload the generator; read pressure
  - Run: `ollama stop qwen3.5:2b-q4_K_M; curl -s localhost:11434/api/ps | jq -r '.models[].name'`
  - Pass: `qwen3.5:2b-q4_K_M` is not listed
  - Result: pressure 1 before and after; `ollama stop` exit 0; `/api/ps` lists only `nomic-embed-text:latest` (the embedder from the manifest's probe, not the generator)

- [x] 6.7 Judge the run. **Stop rule:** more than 2 % of verdict keys `UNPARSED` → stop and report (prompt v2
  is the author's call)
  - Run: `make judge RUN_ID=<RUN_ID>`
  - Pass: exits 0; `experiments/results/<RUN_ID>/judge/` holds `verdicts.jsonl`, `records.jsonl` and
    `summary.json`; every record with an answer has one verdict
  - citable: no
  - Result: `make judge` exit 0 (21:52:56 to 22:10:23 +07, 1047 s), pressure 1 before, 1 or 2 during (13 in-run readings, 18 one-minute samples, peak 2, never 4; citable: no); 622 verdict keys: CORRECT 459, INCORRECT 163, UNPARSED 0 (0.0 %, under the 2 % stop rule); judge/ holds verdicts.jsonl (622 rows), records.jsonl (622 rows, none without a verdict), summary.json; 1.48 s per verdict median, 2.51 s p95; 30 re-judged keys, 0 flips; judge/ is gitignored

- [x] 6.8 Write `evidence/cost.md` from `summary.json` and the pressure readings: hit and MISS records,
  distinct keys, seconds per verdict (median, p95), wall time, the judge's footprint (`footprint`, as
  ADR-017), pressure, `UNPARSED`, the count per layer, the flips among 30 re-judged keys, and the projected
  judge time for every Phase 6 configuration and arm in `docs/super-plan.md`. It states `citable: no` in the
  sentence of every number
  - Files: `docs/work/2026-10-30-judge-harness/evidence/cost.md`
  - Run: `grep -c 'citable: no' docs/work/2026-10-30-judge-harness/evidence/cost.md`
  - Pass: at least 1; every field listed above is present
  - Result: wrote evidence/cost.md (88 lines, numbers only, not gitignored); `grep -c 'citable: no'` gives 29; it holds 528 MISS and 94 hit records, 622 keys, 1.48 s median and 2.51 s p95 per verdict, wall 1047 s, footprint 1163-1230 MB (runner pid 53748), pressure 1 or 2 (peak 2), UNPARSED 0, layers 17/121/9/16/0, 0 flips of 30, and the projection (7 cells x 1047 s validation + 7 x 1095 s test = 4.17 h per pass, with the sweep, static-arm and mutation-on rows and their open points)

## Phase 7 — Run and verify

The main session re-runs each of these itself; the executor's report is not evidence.

- [x] 7.1 `make verify`
  - Pass: no FAIL; any SKIPPED target listed by name
  - Result: make verify exit 0: lint `All checks passed!`, Go 10 packages ok, rag 83 passed, experiments 1117 passed; no FAIL, nothing SKIPPED
- [x] 7.2 Done condition 1 — `metrics.md`
  - Run: 3.1's two greps; read that each entry has the six parts and the three counting choices
  - Pass: `20`, `0`, and nothing missing
  - Result: `20`, `0`; a script found all six parts (Claim, Formula, Filter, Denominator, Interval, Cells) in each of the 20 entries; the three counting choices are there (every wrong hit counts, M08; `answerable: false` its own row, R6; the 2 % `UNPARSED` rule)
- [x] 7.3 Done condition 2 — the run manifest
  - Run: `pytest experiments/tests/test_run_manifest.py -q && make run-manifest-check RUN_ID=<RUN_ID> GATEWAY_LOG=docs/work/2026-10-30-judge-harness/evidence/private/gateway-cost.log`
  - Pass: all pass; exit 0
  - Result: test_run_manifest.py 118 passed; `make run-manifest-check RUN_ID=2026-11-01T21-17-56_cfg4_judgecost GATEWAY_LOG=…/gateway-cost.log` exit 0
- [x] 7.4 Done condition 3 — the pre-registration record
  - Run: 3.4's and 4.4's greps; compare both entries' dates with the date in 5.3's `Result:` line, the first
    verdict
  - Pass: both hashes are found; both entries are dated on or before the first verdict
  - Result: judge-v1.json's sha256 found 1×; the current set's hash (Entry 4) 1×, Entry 2's hash 3× (Entries 2–4); Entries 1–4 are dated 2026-11-01, and the first verdict (5.3) came at ~21:10 that day, after Entry 4 (~17:34)
- [x] 7.5 Done condition 4 — the verdict key
  - Run: `pytest experiments/tests/test_judge.py -q -k key`; 3.2's pinned-key grep
  - Pass: all pass; §H's key equals `golden-key.txt`
  - Result: `-k key` 16 passed; `item 5.1 fixes it` 0; the golden key d2f8597f…bb41 is in §H; the §I heading is found; the version line now reads `Current version: v0.29` (Phase 10 moved it from v0.28)
- [x] 7.6 Done condition 5 — ADR-022
  - Run: 3.3's greps; `curl -s localhost:11434/api/tags | jq -r '.models[] | select(.name=="gemma3:4b-it-q4_K_M") | .digest'`
  - Pass: ADR-022 and its row are there; the live digest equals `judge-v1.json` and the ADR
  - Result: ADR-022's heading and table row found; the judge digest appears 1× in decisions.md; the live digest a2af6cc3…f5a equals judge-v1.json's
- [x] 7.7 Done condition 6 — the gold audit
  - Run: `make judge-gold-check SPLIT=validation && pytest experiments/tests/test_judge_references.py -q`
  - Pass: both pass
  - Result: `make judge-gold-check SPLIT=validation` exit 0; test_judge_references.py 78 passed
- [x] 7.8 Done condition 7 — the references
  - Run: `pytest experiments/tests/test_judge_references.py -q`; `wc -l experiments/references/validation/index.jsonl`; `make judge-references SPLIT=validation`
  - Pass: tests pass; one row per distinct `(question, product_id)`; the second build refuses because the
    folder exists
  - Result: 78 passed; index.jsonl 622 rows, 622 distinct `(question, product_id)`; the second build prints `REFUSED: …/validation exists; a reference set is never overwritten` (make exit 2); the index hash is unchanged (0e843899…) and no model loaded
- [x] 7.9 Done condition 8 — gold sufficiency
  - Run: 4.7's `score`
  - Pass: at most 3 `no` in each cell; the decline count is in 4.3's `Result:`; Entry 3 is in `preregistration.md`
  - Result: `score` on sufficiency-v3.md (where 4.7 passed, step 10.11): 28 / 2 and 27 / 3, `ok`, exit 0; the decline counts are in 4.3's Result (78, the 2B set) and 10.7's (53, the 4B set); Entry 3 is in preregistration.md
- [x] 7.10 Done condition 9 — the harness
  - Run: `pytest experiments/tests/test_judge.py -q`; `make judge RUN_ID=<RUN_ID>`
  - Pass: all pass; the second `make judge` refuses because the output exists
  - Result: test_judge.py 120 passed; the second `make judge` prints `REFUSED: …/judge exists; judge output is never overwritten` (make exit 2); the three output files' sha256 are unchanged and no model loaded
- [x] 7.11 Done condition 10 — sanity pairs
  - Run: `make judge-sanity FILE=docs/work/2026-10-30-judge-harness/evidence/private/sanity-v1.jsonl` (generator
    unloaded, pressure read)
  - Pass: 12 of 12; exit 0
  - citable: no
  - Result: generator not loaded, pressure 1 before and after; `12 of 12 correct, 0 UNPARSED`, make exit 0, the same 12 verdicts as 5.3
- [x] 7.12 Done condition 11 — the cost
  - Run: read `evidence/cost.md` against DC 11's list; `git check-ignore experiments/results/<RUN_ID>/raw/requests.jsonl`
  - Pass: every field present; `raw/` is ignored
  - Result: cost.md holds every DC 11 field (hit and MISS records, distinct keys, s per verdict median and p95, wall time, footprint, pressure, `UNPARSED`, layers, flips, the projection) and says citable: no beside each number; `raw/requests.jsonl` is ignored. The main session added the judge's memory read three ways at 7.11 (Ollama 3.72 GB, RSS 4.26 GB, footprint 1.22 GB)
- [x] 7.13 Done condition 12 — verify, docs, tests untouched
  - Run: `make verify`; 3.5's greps; `git ls-files -co --exclude-standard -- '*_test.go' 'rag/tests/*.py' 'experiments/tests/*.py' | sort | xargs shasum -a 256 | diff docs/work/2026-10-30-judge-harness/evidence/tests-before.txt - | grep '^<'`
  - Pass: `make verify` passes; the docs greps pass; the diff prints no `<` line (no existing test changed
    or removed; new test files show only as `>`)
  - Result: make verify passed (7.1); the architecture grep gives 5 and the do-NOT-exist grep prints nothing; the hash diff against tests-before.txt prints 0 `<` lines (4 `>`, the task's new test files)

## Phase 8 — Fixes from the review of Phases 1–2 (2026-11-01)

From design.md §4. Run it **right after Phase 2, before Phase 3**: step 3.2 writes §I from the final manifest
keys. Steps 6.5 and 7.3 above now pass `GATEWAY_LOG=` to `run-manifest-check`. No step here loads a model.

- [x] 8.1 `generator_block()` also returns `prompt_sha256` (sha256 of `generate._PROMPT_TEMPLATE`), last;
  `version_block()` no longer has it at the top level
  - Files: `experiments/scripts/judge_references.py`
  - Run: `ruff check experiments/scripts/judge_references.py && python3 -c "import sys; sys.path.insert(0, 'experiments/scripts'); import judge_references as jr; print(list(jr.generator_block()))"` (reads `/api/tags` and `/api/show` only)
  - Pass: ruff is clean; prints the six keys `model, digest, num_ctx, think, temperature, prompt_sha256`
  - Result: generator_block() now ends with prompt_sha256 (sha256 of generate._PROMPT_TEMPLATE) and version_block() no longer has it at the top level; ruff clean; the call (reads /api/tags and /api/show only, /api/ps stayed empty) prints model, digest, num_ctx, think, temperature, prompt_sha256

- [x] 8.2 `run_manifest.py` requires `generator.prompt_sha256`, after `generator.temperature`
  - Files: `experiments/scripts/run_manifest.py`
  - Run: `ruff check experiments/scripts/run_manifest.py && grep -c '"generator.prompt_sha256"' experiments/scripts/run_manifest.py`
  - Pass: ruff is clean; `1`
  - Result: run_manifest.py REQUIRED now lists generator.prompt_sha256 right after generator.temperature; ruff clean, grep -c gives 1

- [x] 8.3 `preflight` compares `prompt_sha256` with the other five `generator` fields
  - Files: `experiments/scripts/judge.py`
  - Run: `ruff check experiments/scripts/judge.py && grep -n '"generator", (' experiments/scripts/judge.py`
  - Pass: ruff is clean; the line lists six keys, `prompt_sha256` last
  - Result: preflight now compares all six generator fields, prompt_sha256 last; the three field lists sit in one '# fmt: off' block so the grep line shows the six keys (ruff format would otherwise wrap that tuple and the plan's grep would print nothing); ruff clean

- [x] 8.4 Tests, only in this task's own test files (none is in `evidence/tests-before.txt`): the fakes' generator
  blocks gain `prompt_sha256`; `test_judge_references.py`'s `version_block` and `generator_block` tests expect it
  inside `generator`; new `test_check_refuses_a_manifest_without_the_generator_prompt` in `test_run_manifest.py`;
  new `test_dc9_preflight_refuses_another_generator_prompt` in `test_judge.py`
  - Files: `experiments/tests/test_judge_references.py`, `experiments/tests/test_run_manifest.py`, `experiments/tests/test_judge.py`
  - Run: `pytest experiments/tests/test_judge_references.py experiments/tests/test_run_manifest.py experiments/tests/test_judge.py -q`
  - Pass: all pass; both new test names are found by `grep`
  - Result: updated only test_judge.py, test_judge_references.py and test_run_manifest.py (none is in tests-before.txt): fakes' generator blocks carry prompt_sha256, version.json fixture has it only inside generator, version_block/generator_block tests expect it there; added the two named tests (test_check_refuses_a_manifest_without_the_generator_prompt, test_dc9_preflight_refuses_another_generator_prompt), 3 more tests and 2 parametrized cases; 302 pass (295 before); mutations (5-field preflight, REQUIRED without the key, generator_block without the hash) each failed tests, then restored (identical)

- [x] 8.5 The whole suite and lint, and no existing test changed
  - Run: `make lint && make test`; then 7.13's `git ls-files … | diff docs/work/2026-10-30-judge-harness/evidence/tests-before.txt - | grep '^<'`
  - Pass: no FAIL, any SKIPPED listed by name; the diff prints no `<` line
  - Result: make lint clean; make test exit 0 (rag 83 passed, experiments 1103 passed, Go ok), no FAIL, nothing SKIPPED; the hash diff against tests-before.txt prints 0 lines starting with '<' (only the 4 new test files show as '>')

## Phase 9 — `reference right`, from the review of Round 1 (2026-11-01)

From design.md §4 (Round 1) and failure mode 14. Run it **now, after 4.5 and before 4.6**. Steps 4.6, 4.7 and 7.9
above now read `sufficiency-v2.md` and count both cells. `sufficiency-v1.md` is unmarked and is left as it is. No step
here loads a model.

- [x] 9.1 `sheet()` writes a `reference right:` line right after each `sufficient:` line, and the sheet's header
  explains it in two sentences: write `yes` if the reference answer is correct by the gold evidence, `no` if it is
  wrong; a reference that declines is right only when the evidence does not answer. A module regex `REFERENCE_RIGHT`
  beside `SUFFICIENT`. `score()` keeps every key it returns today and adds `ref_yes`, `ref_no`, `ref_unmarked`,
  `ref_other`, read the same way (last match in the section, case-folded). The `score` CLI prints both counts; it
  returns 1 while any cell of either kind is unmarked or other, and 1 with a `STOP` line when either `no` count is
  over 3 (design.md DC 8)
  - Files: `experiments/scripts/judge_references.py`
  - Run: `ruff check experiments/scripts/judge_references.py && grep -c 'reference right:' experiments/scripts/judge_references.py`
  - Pass: ruff is clean; at least 1
  - Result: added REFERENCE_RIGHT, the `reference right:` line and a two-sentence header note in sheet(), and ref_yes/ref_no/ref_unmarked/ref_other in score() plus the CLI (both counts, FAIL on any open cell, STOP on either no over 3); ruff clean (ruff is in ~/Library/Python/3.13/bin), grep -c gives 9

- [x] 9.2 Tests, only in `experiments/tests/test_judge_references.py` (not in `evidence/tests-before.txt`): the
  `marked()` helper marks both cells; the exact-dict assertion in `test_sheet_writes_30_pairs_with_at_least_10_b_within`
  gains the four `ref_` keys; new `test_sheet_writes_a_reference_right_cell_per_pair`,
  `test_score_counts_reference_right_marks`, `test_score_cli_stops_on_more_than_3_wrong_references` and
  `test_score_cli_fails_while_a_reference_cell_is_unmarked`
  - Files: `experiments/tests/test_judge_references.py`
  - Run: `pytest experiments/tests/test_judge_references.py -q`
  - Pass: all pass; the four new test names are found by `grep`
  - Result: marked() now marks both cells (ref_marks defaults to all yes), the exact-dict test gains the four ref_ keys, and the four named tests were added to test_judge_references.py only (not in tests-before.txt); 74 passed, each new name found once by grep

- [x] 9.3 The whole suite and lint, and no existing test changed
  - Run: `make lint && make test`; then 7.13's `git ls-files … | diff docs/work/2026-10-30-judge-harness/evidence/tests-before.txt - | grep '^<'`
  - Pass: no FAIL, any SKIPPED listed by name; the diff prints no `<` line
  - Result: make lint clean; make test exit 0 (Go ok, rag 83 passed, experiments 1107 passed), no FAIL, nothing SKIPPED; the hash diff against tests-before.txt prints 0 `<` lines (4 `>` lines, the new test files)

- [x] 9.4 The v2 sheet, the same seed as v1
  - Run: `python3 experiments/scripts/judge_references.py sheet --split validation --out docs/work/2026-10-30-judge-harness/evidence/private/sufficiency-v2.md`; then `diff <(grep '^## ' docs/work/2026-10-30-judge-harness/evidence/private/sufficiency-v1.md) <(grep '^## ' docs/work/2026-10-30-judge-harness/evidence/private/sufficiency-v2.md)`; `grep -c '^reference right:$' docs/work/2026-10-30-judge-harness/evidence/private/sufficiency-v2.md`; `git check-ignore docs/work/2026-10-30-judge-harness/evidence/private/sufficiency-v2.md`
  - Pass: 30 rows, 17 B-within; the diff prints nothing (the same 30 pairs, in the same order); `30`; `check-ignore` prints the path
  - Result: wrote evidence/private/sufficiency-v2.md: 30 rows, 17 B-within; the `## ` diff against v1 is empty (same 30 pairs, same order); `reference right:` empty-cell lines 30; check-ignore prints the path

- [x] 9.5 Append Entry 3 to `preregistration.md`, dated 2026-11-01, before the first verdict: it cites Entries 1 and 2,
  adds the `reference right` cell and its stop rule (more than 3 `no` of 30 → stop before any verdict) beside Entry 1's
  `sufficient` rule, and records the decline count (78 of 582) and the sheet's seed (7). Entries 1 and 2 are not edited
  - Files: `docs/preregistration.md`
  - Run: before the edit `cp docs/preregistration.md "$TMPDIR/prereg-before.md"`; after it `cmp -n "$(stat -f%z "$TMPDIR/prereg-before.md")" "$TMPDIR/prereg-before.md" docs/preregistration.md && grep -c '^## Entry 3 ' docs/preregistration.md && ls experiments/results/`
  - Pass: `cmp` prints nothing (the old text is an exact prefix); `1`; no run directory holds a `judge/` folder
  - Result: appended Entry 3 (2026-11-01) at the end: cites Entries 1 and 2, adds the `reference right` cell and its stop rule (over 3 `no` of 30), the decline count 78 of 582 and seed 7; the old text is an exact prefix (BSD `cmp -n` prints `EOF on` whenever the files differ in size, so I checked `head -c 7533 docs/preregistration.md | cmp - $TMPDIR/prereg-before.md`: no output, exit 0, equal sha256); `grep -c '^## Entry 3 '` gives 1; experiments/results/ holds only .gitkeep, no judge/ folder

## Phase 10 — The reference writer, ADR-023 (2026-11-01)

From design.md §4 (ADR-023) and failure mode 15. Run it **now**; 4.7 is ticked when 10.11 passes. The served generator,
the judge and the prompt do not change. Only 10.7 loads a model (the writer), and it is `citable: no`.

- [x] 10.1 Write `experiments/judge/reference-writer-v1.json`: `version` `reference-writer-v1`, `model`
  `qwen3.5:4b-q4_K_M`, `digest` `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`, `options`
  `{num_ctx 8192, temperature 0, seed 20261101}`, `think` false, `prompt_sha256`
  `3e224f4500a18dc065ab6e24c46e25302ac275f8e145085bfb211bcf65ba67dd`
  - Files: `experiments/judge/reference-writer-v1.json`
  - Run: `python3 -c "import json,hashlib,urllib.request as u; w=json.load(open('experiments/judge/reference-writer-v1.json')); t=json.load(u.urlopen('http://localhost:11434/api/tags')); from rag import generate; print([m['digest'] for m in t['models'] if m['name']==w['model']]==[w['digest']], hashlib.sha256(generate._PROMPT_TEMPLATE.encode()).hexdigest()==w['prompt_sha256'])"`
  - Pass: prints `True True`
  - Result: wrote experiments/judge/reference-writer-v1.json; the live /api/tags digest and the served prompt's sha256 both match (`True True`)

- [x] 10.2 `judge_references.py`: `WRITER_PATH`, `load_writer()`, `writer_block(http)` (refuses when the tag is not in
  `/api/tags`, its live digest differs, or the prompt hash differs), `answer_with_writer(query, product_id,
  chunk_ids)` (`retrieve.fetch_by_ids`, `generate._build_prompt`, then `/api/generate` with the writer's model and
  options, `think: false` when `/api/show` lists `thinking`; returns the text and the IDs `fetch_by_ids` returned).
  `version_block()` adds `reference_writer` from `writer_block()`; `build()`'s default `answer` is
  `answer_with_writer`. `answer_in_process` stays, unused by default
  - Files: `experiments/scripts/judge_references.py`
  - Run: `ruff check experiments/scripts/judge_references.py && python3 -c "import sys; sys.path.insert(0,'experiments/scripts'); import judge_references as jr; print(jr.writer_block()['model'])"` (reads `/api/tags` and `/api/show` only)
  - Pass: ruff is clean; prints `qwen3.5:4b-q4_K_M`
  - Result: added WRITER_PATH, load_writer, writer_block and answer_with_writer; version_block gains `reference_writer`; build() now defaults to answer_with_writer (make_reference's own default is still answer_in_process); ruff clean, `writer_block()['model']` prints qwen3.5:4b-q4_K_M, and the 4B's /api/show lists `thinking`, so `think: false` is sent

- [x] 10.3 `judge.py`: `preflight` refuses when the reference set's `version.json` has no `reference_writer`, or when
  any of its `model`, `digest`, `options`, `think`, `prompt_sha256` differs from `reference-writer-v1.json`. The
  `generator` comparison stays as it is
  - Files: `experiments/scripts/judge.py`
  - Run: `ruff check experiments/scripts/judge.py && grep -c 'reference_writer' experiments/scripts/judge.py`
  - Pass: ruff is clean; at least 1
  - Result: preflight takes `writer_cfg` (default: reference-writer-v1.json) and refuses a version.json without `reference_writer` or with a different model, digest, options, think or prompt_sha256; run() reads it from a new `writer_path`; ruff clean, grep -c gives 4

- [x] 10.4 Tests, only in this task's own files (none is in `evidence/tests-before.txt`): the fakes' `version.json`
  gains `reference_writer`; new `test_writer_block_refuses_another_live_digest`,
  `test_answer_with_writer_sends_the_writer_model_and_options`, `test_version_block_carries_the_reference_writer`,
  `test_build_defaults_to_the_reference_writer` in `test_judge_references.py`; new
  `test_dc9_preflight_refuses_another_reference_writer` and `test_dc9_preflight_refuses_a_set_without_a_writer` in
  `test_judge.py`
  - Files: `experiments/tests/test_judge_references.py`, `experiments/tests/test_judge.py`
  - Run: `pytest experiments/tests/test_judge_references.py experiments/tests/test_judge.py -q`
  - Pass: all pass; the six new test names are found by `grep`
  - Result: the fakes now write `reference-writer-v1.json` and a `reference_writer` block (fake_http, build_world, World.writer_path, 3 direct preflight calls take `writer_cfg`); six new tests added (one is parametrized over 5 fields); 198 passed in the two files (was 74 + 114), each new name found once by grep; a mutation (digest dropped from the compared keys) failed the digest case

- [x] 10.5 The whole suite and lint, and no existing test changed
  - Run: `make lint && make test`; then 7.13's `git ls-files … | diff docs/work/2026-10-30-judge-harness/evidence/tests-before.txt - | grep '^<'`
  - Pass: no FAIL, any SKIPPED listed by name; the diff prints no `<` line
  - Result: make lint clean; make test exit 0 (Go ok, rag 83 passed, experiments 1117 passed = 1107 + 10 new cases), no FAIL, nothing SKIPPED; the hash diff against tests-before.txt prints 0 `<` lines (4 `>` lines, the new test files)

- [x] 10.6 Keep Entry 2's set as the baseline: `mv experiments/references/validation experiments/references/validation-qwen2b-t1`
  - Run: `shasum -a 256 experiments/references/validation-qwen2b-t1/index.jsonl; ls experiments/references/`
  - Pass: the hash is Entry 2's `00c9a333…58e3`; `validation` is no longer listed
  - Result: moved experiments/references/validation to validation-qwen2b-t1 (gitignored, local only); index.jsonl sha256 is 00c9a33310a66542d739a860e3e77a162658a5dddaefa00fbc3e8ea30ca558e3, the same as Entry 2; `ls` lists only validation-qwen2b-t1

- [x] 10.7 Rebuild the references with the writer. Read pressure first (1 or 2 runs, 4 stops). In the background;
  about an hour. Afterwards `ollama stop qwen3.5:4b-q4_K_M`
  - Run: `make judge-references SPLIT=validation 2>&1 | tee docs/work/2026-10-30-judge-harness/evidence/private/references-4b.log`
  - Pass: `make` exits 0; `index.jsonl` has 622 rows; `version.json`'s `reference_writer` has `model`
    `qwen3.5:4b-q4_K_M` and the digest of 10.1; the log ends with the decline count and the index hash
  - citable: no
  - Result: pressure 1 before the run (read twice, and again by the build), level 2 (yellow) at the 50/100/150-reference lines, 1 from 200 on, never 4 (citable: no, so it ran); `make` exit status 0 (from PIPESTATUS, not tee's); index.jsonl 622 rows, 507 answer files; version.json `reference_writer` is qwen3.5:4b-q4_K_M with digest 2a654d98…eefd; 53 of 582 answerable:true references decline (was 78); index.jsonl sha256 0e84389981f4bfcdfa6cd3fbd0e7b5bf9662facba02564ca562e7a65520c974a, version.json sha256 11bcc1ce730777594ec7ba2a66a8efe5c6817720820a061e58a8fb29e0fb2f42; ~62 min; writer unloaded (`/api/ps` empty)

- [x] 10.8 Append Entry 4 to `preregistration.md`, dated 2026-11-01, before the first verdict: it cites ADR-023 and
  Entries 2 and 3; it records the new set's hash, the sha256 of its `version.json`, the writer's fields, the decline
  count, and the 2B set's new path with its unchanged hash. Entries 1–3 are not edited
  - Files: `docs/preregistration.md`
  - Run: before the edit `cp docs/preregistration.md "$TMPDIR/prereg-before-4.md"`; after it `head -c "$(stat -f%z "$TMPDIR/prereg-before-4.md")" docs/preregistration.md | cmp - "$TMPDIR/prereg-before-4.md" && grep -c "$(shasum -a 256 experiments/references/validation/index.jsonl | cut -c1-64)" docs/preregistration.md && ls experiments/results/`
  - Pass: `cmp` prints nothing; `1`; no run directory holds a `judge/` folder
  - Result: appended Entry 4 (2026-11-01) at the end of docs/preregistration.md with the new set's hash 0e843899…974a, version.json sha256 11bcc1ce…2fb42, the writer's fields and file sha256 1060f41e…1e27, the decline count 53 of 582, and the 2B set's new path with its unchanged hash; `head -c … | cmp` prints nothing (the old text is an exact prefix), the new hash is found once, `ls experiments/results/` shows only .gitkeep

- [x] 10.9 Sheet v3, the same seed, with the author's v2 `sufficient` marks copied in and `reference right` left empty
  - Run: `python3 experiments/scripts/judge_references.py sheet --split validation --out docs/work/2026-10-30-judge-harness/evidence/private/sufficiency-v3.md`; then copy each v2 row's `sufficient:` mark into the v3 row with the same number after checking that the two rows' `## n. qa_id` lines are equal; then `diff <(grep -E '^(## |sufficient:)' …/sufficiency-v2.md) <(grep -E '^(## |sufficient:)' …/sufficiency-v3.md)`, `grep -c '^reference right:$' …/sufficiency-v3.md`, `git check-ignore …/sufficiency-v3.md`
  - Pass: the diff prints nothing; `30`; `check-ignore` prints the path
  - Result: wrote evidence/private/sufficiency-v3.md (30 pairs, 17 B-within); a script in the scratchpad copied the 30 `sufficient:` marks (28 yes, 2 no) from v2 after checking that every `## n. qa_id` line is equal; the `^(## |sufficient:)` diff of v2 and v3 prints nothing; `reference right:` empty-cell lines 30 (none copied, none read); check-ignore prints the path

- [x] 10.10 **STOP for the author.** Ask the author to mark every `reference right:` cell in `sufficiency-v3.md`,
  blind: the main session shows no provisional marks. Resume only when the author says it is marked
  - Pass: the author confirms
  - Result: the author gave the 30 marks in chat (2026-11-01; the author's marks, with feedback from an AI assistant, in the author's words); the main session wrote them in (30 changed lines); row 19 is `yes` as the author's total (27 / 3) gives, the note beside it was the feedback's; no provisional mark was shown, but the author had seen the comparison README's wrong rows for the 4B (17, 25) earlier that day

- [x] 10.11 Score v3 under step 4.7's stop rule: more than 3 `no` in either cell → stop and report; no verdict runs
  - Run: `python3 experiments/scripts/judge_references.py score docs/work/2026-10-30-judge-harness/evidence/private/sufficiency-v3.md`
  - Pass: 30 pairs marked in both cells, at most 3 `no` in each; then tick 4.7 with a `Result:` that cites 10.11
  - Result: `30 pairs (17 B-within): 28 yes, 2 no, 0 unmarked`; `reference right: 27 yes, 3 no, 0 unmarked`; `ok  at most 3 no in each cell`, exit 0. No: sufficient rows 11, 25; reference right rows 17, 23, 25. Passes at the limit; row 19 decides it (`no` there would stop). 4.7 ticked
