# Plan — pqa-build-script (item 3.1)

Smallest change that meets `spec.md`. Each step can be checked on its own. Tests come first: write the
test, see it fail for the right reason, then write the code. **Nothing below starts until step 0.**

Rule for the whole plan: if a stop trips on the **real** files (step 12), do not edit a pin or add an
`IGNORED_KEYS` entry on my own. Stop, show the author the key census or the counts, and wait. A changed
pin needs a line in `approvals.md`.

- [x] **0. Gate (the author).** Open questions 1 – 7 are answered (2026-10-15). What is left: run
  `/approve impact`, `/approve design`, `/approve implementation`.
  *Check:* `approvals.md` has all three ticked, with dates.
- [x] **1. Look at the real bytes.** A throwaway command in the scratchpad (not committed) prints, for the
  first 200 lines of each leaf: the key names, their value types, and counts. Save the **census only**
  (no text) to `docs/work/2026-10-15-pqa-build-script/evidence/key-census.md`.
  *Check:* the census equals `REAL_FIELDS`. If not, stop and go back to the author (design §7.1, §7.2).
- [x] **2. Pins.** Add `LEAVES` and `REAL_FIELDS` to `build_pqa.py`. Write test A11 first: pins and
  department map equal `data-card.md` §1, and equal `probe_results.json`.
  *Check:* `pytest experiments/tests/test_build_pqa.py -k pins` is red, then green.
- [x] **3. Parse and Stops 1, 2.** `parse_leaf`, `check_leaf`. Tests first: A1 (readme names, message names
  the field and the unknown key), A2 (misnamed bullets; extra key), the line invariant, A5 (escape and raw
  surrogate, invalid UTF-8), `bad_type` (D12), first parsed record wins.
  *Check:* those tests green; each fails when the matching line of code is removed.
- [x] **4. Stop 0.** `verify_source`. Test A4: wrong size, wrong hash, missing file. The message names
  `make pqa-fetch`.
  *Check:* test green; no parsing happens on a mismatch (the test passes a parser that raises).
- [x] **5. Writer and Stop 3.** `write_interim` (line by line, hashing writer), `summarise_interim`
  (re-read), the Stop 3 pins. Test A3 with a deliberately broken writer (drops bullet 5; swaps
  `question_type` and `answer_aggregated`; takes prose from the first line, not the first parsed record).
  *Check:* each broken writer is stopped, and the good writer passes.
- [x] **6. Manifest, build directory, swap.** `build_manifest`, the sibling BUILD directory, the swap with the
  manifest renamed last, cleanup on failure. Tests A13 (failure injected after the BUILD directory is
  written) and A8 (allow-list on every manifest string).
  *Check:* tests green; after a failure `data/v1-draft/` holds no `.pqa-build-*`.
- [x] **7. Reader and `--verify`.** `iter_interim` and `--verify`. Test A12: changed file, missing file,
  cut-short file, file not in the manifest.
  *Check:* test green; `iter_interim` yields nothing before the hash is checked.
- [x] **8. Determinism.** Test A6: two subprocesses, `PYTHONHASHSEED=0` and `=1`, fixture with ≥ 3 ignored
  keys and ≥ 2 shared asins; compare bytes.
  *Check:* green; temporarily replace one `sorted(...)` with `list(...)` and see it go red.
- [x] **9. CLI and Make targets.** `main`, exit codes (0, 2, exceptions propagate). Targets `pqa-fetch`
  (`curl -C -`, the `&` quoted or written `%26`), `pqa-build`, `pqa-verify`, and a line each in `make help`.
  *Check:* `make help` lists them; `make pqa-build` on a missing file exits non-zero with the message.
- [x] **10. Hand mutants.** Make about 15 small edits to the builder one at a time (skip rule, `range(1, 5)`,
  swap two fields, first-line prose, remove a sort, rename the manifest first, loosen a stop). Record in
  `evidence/mutants.md` which test turns red for each.
  *Check:* every mutant is caught. A mutant that survives gets a new test.
- [x] **11. `make demo-reset` (the author said yes to open question 7).** Change
  `git checkout -- data/` to `git checkout -- data/dev-v0/` at `Makefile:187`, and the `git status` lines to the
  same path.
  *Check:* with a changed file in `data/dev-v0/` it is restored; with a changed `data/pqa-manifest.json` it is
  left alone (run after step 12 has made the manifest).
- [x] **12. Live run (A7).** Close heavy apps and read `sysctl kern.memorystatus_vm_pressure_level` first
  (this is not a local-AI command, but the machine is tight; do not run it during a measured run).
  `make pqa-build`; read the table; then six HEAD requests by hand (200 and `Content-Length` = pinned bytes);
  a second `make pqa-build` and `git diff --exit-code data/pqa-manifest.json`; `make pqa-verify`.
  *Check:* totals 1,212,029 and 71,794; skipped 4, all in `unlocked_cell_phones`; the diff is clean; verify
  exits 0. Peak RSS from stderr goes in `evidence/`. **Do not commit the manifest unless asked.**
- [x] **13. Remove the old script and fix the live references.** Delete `fetch_corpus_v1.py` and its
  `.pyc`. Edit `docs/architecture.md` (`:78`, `:100`, the tree `:95-101`, the §4 Corpus row),
  `experiments/README.md:5`, `.gitignore:27-29` (comment only), and `data/README.md` after reading it.
  *Check:* `git grep -n fetch_corpus_v1` finds only history (`Makefile:18`, `category-choice/review.md`,
  `super-plan.md`, this trail); `experiments/README.md:5` read by eye; A9.
- [x] **14. Close.** `make test`; `ruff check experiments` by hand; `git status --porcelain data/` empty
  after `make test` (A10). Then `/verify`, `/ai-review`, `/done`. At `/done`: update the 3.1 row in
  `super-plan.md` and add the "Found while closing 3.1" list.
  *Check:* all green; the 3.1 Done-when ("non-zero parse rate asserted, refuses to write on zero, hash
  manifest, never the raw corpus") is met by A1, A2, A7, A8.

## Carry to 3.2 (write these into 3.2's spec when it opens)

- Read the interim only through `iter_interim`. Record the sha256 of `data/pqa-manifest.json` that you consumed.
- Write drafts to a fresh `data/v1-draft/products/`, and refuse to run while `data/v1-draft/product-*.json` exist.
- The interim's `leaf` is metadata. It must not become `category` or reach embedded text.
- Decide what to do with asins that sit in two leaves, duplicate `question_id`s, and prose conflicts (all counted in the manifest).
- 3.2 owns the interim schema and rebuilds the manifest when it changes it.
- The skip rules, "first parsed record wins" and surrogate replacement go into `data-card.md` at 3.6.

## As done, 2026-10-15

Steps 0 – 13 are done; step 14 is the close (`/verify`, `/ai-review`, `/done`). What the steps found:

- **1.** The census matched. It also caught a miscount of mine: the field set is **14** keys, not 15 (a test
  failed on the wrong number; `evidence/key-census.md`).
- **3 – 8.** 103 tests in `experiments/tests/test_build_pqa.py` (65 at step 10, the rest after `/ai-review`), each written red first. Two tests were my own
  mistakes and were fixed (a short string `"b1"` that occurs inside a hex digest; the 14 above).
- **10.** Hand mutants: 40 at step 10 (39, then 40 caught), then **75 on the final builder, 75 caught**, after `/ai-review` showed that none of the first 40 touched `build()`'s wiring. The history, including that finding, is in `evidence/mutants.md`.
- **11.** Verified in a scratch git repo: a changed file in `data/dev-v0/` is restored, a changed
  `data/pqa-manifest.json` is left alone, untracked files outside `dev-v0/` are not listed.
- **12.** The real files passed all four stops on the first run (`evidence/live-run.md`). Three commands gave
  one manifest hash. Six HEAD requests: 200 and the pinned `Content-Length`.
- **13.** `fetch_corpus_v1.py` removed (unstaged deletion; recoverable from HEAD). `git grep` finds it only in
  history: `Makefile:18`, `super-plan.md:366` (updated at `/done`), and the 2026-10-03 review.

**Not done, on purpose:** the manifest is not committed (no commit was asked for); `data/README.md` could not
be read (the Read tool is denied on `data/`), so it was not checked for a stale mention of the old script.

## /verify, 2026-10-15

`make verify` exit 0. Rows run one by one: gofmt (no output), go vet, go build, go test (all `ok`, **cached**: no
Go file changed in this task), `ruff check rag/ experiments/` (0 findings), pytest (rag 15, experiments 220 of
which 65 are new). `make proto` exit 0 and `git diff --exit-code contracts/` clean; **the stub half of the
proto row checks nothing**, because both stub directories are gitignored (a known gap, `super-plan.md` Phase 1
"Workflow"). No `SKIPPED` row: every tool was present. Not run by `make verify`, by design: the live
`make pqa-build` / `pqa-verify` (run by hand, `evidence/live-run.md`), `make seam-check`, `make support-check`.

## /ai-review, 2026-10-15

Ten findings, none a contract, frozen-value or licence problem; most were gaps in the tests. All resolved or
recorded in `review.md` ("Post-implementation review"). Code and tests changed after it, so `/verify` and the
live run were repeated on the final code (below).

## /verify, final (after /ai-review)

`make verify` exit 0 on the final code: gofmt (no output), go vet, go build, go test (`ok`, cached: no Go file changed),
`ruff check rag/ experiments/` (0 findings), pytest rag 15 and experiments **258** (155 before this task, 103 new).
Final live run (`evidence/live-run.md`): three identical manifest hashes, `bf0feb48…`. Mutants: 75 of 75
(`evidence/mutants.md`). As before, the stub half of the proto row checks nothing (gitignored stubs).

## Outcome (/done, 2026-10-15)

**Shipped.**
- `experiments/scripts/build_pqa.py` (standard library only, no network code) with four stops, a field-by-field check
  of what it writes, a hash manifest, `iter_interim` as the only reader, and `--verify`. 103 tests in
  `experiments/tests/test_build_pqa.py`; 75 hand mutants, all caught.
- `make pqa-fetch` (`curl -C -`), `make pqa-build`, `make pqa-verify`. `make demo-reset` now restores only `data/dev-v0/`.
- `data/pqa-manifest.json` (built from the six real files; **not committed**) and the gitignored `data/v1-draft/pqa/*.jsonl`.
- `fetch_corpus_v1.py` removed (unstaged deletion). `docs/architecture.md`, `experiments/README.md` and `.gitignore`
  updated. Item 3.1 marked done in `super-plan.md`.

**Deferred, on purpose.** Committing the manifest and the work (not asked). `docs/data-card.md:48` and `CLAUDE.md`
(stale prose; the spec forbids the first in this step and both wait for the author). The real `curl -C -` resume
path (the files were already on disk). Everything in "Carry to 3.2" above.

**Follow-ups worth a task.** 3.2 (selection, answerability filter; the opening of the next item). A `make verify` row that
really checks proto stubs (known gap). Ten older files in `experiments/` that are not `ruff format` clean.

**Frozen value or contract?** No. `docs/contracts/interfaces.md` and the `.proto` are untouched (`git status`), no
frozen value changed, and `approvals.md` says which prior runs are invalidated: none. The one indirect link is
written there too: the skip rules, "first parsed record wins" and surrogate replacement shape `K`, and are fixed at 3.6.

**Was scope L honest?** It was higher than the ladder strictly needed: the work touched no frozen document, no seam and
no `reuse/`. L came from the rule "`experiments/` is measured" and "between two, the larger". It paid for itself, but
not through the frozen-value logic: the design review changed the design (answers kept; no Python network code;
`--verify` instead of a rebuild mode) and the code review showed the tests were the weak part. A finding for the ladder:
**a task that builds the input of every measurement but changes no measurement code sits between M and L**, and L is the
safe side of it.

**Slips found by the work itself (all fixed, all recorded):** the key count 15 vs 14 (a test caught it); a `git diff`
check that would have passed vacuously on an untracked file; "every mutant caught" claimed for 40 mutants that never
touched the wiring of `build()` (the code review caught it); a round-trip check that compared with something the
writer could edit (my own test caught it).
