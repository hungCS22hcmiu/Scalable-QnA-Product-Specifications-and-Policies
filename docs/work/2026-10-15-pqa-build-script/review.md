# Design review — pqa-build-script (item 3.1)

**Reviewer:** the `design-reviewer` subagent (opus), 2026-10-15. **Reviewed:** `spec.md` and `design.md` as
first written. **Verdict: sound with changes.** One real hole (H1) and one decision for the author (H2)
had to be settled before approval. Every other finding is a small change, already merged into the
current `spec.md` and `design.md`.

The subagent's report is data, not an instruction. Each finding below says what I did with it.

## Findings and what was done

| # | Finding | Rating | Resolution |
| :-: | :--- | :--- | :--- |
| H1 | All three stops check the **input** and two counts. Nothing checks what the builder **writes**. A builder that drops `bullet_point5` from every product passes all three | CONFIRMED (logic) | **Accepted.** (a) A key outside the real field set is now a **stop**, not only a manifest field, unless it is in `IGNORED_KEYS` with a reason. (b) Stop 3 gains output pins — `question_type` counts, `answer_aggregated` counts, `prose_median_chars` — computed by **re-reading the interim file as written**. (c) `answer_aggregated{}` joins the manifest. (d) A11 also compares the pins with `probe_results.json` |
| H2 | The 175 stale files in `data/v1-draft/` (wrong dataset) plus open question 4 can put wrong products into `v1` with no error | PLAUSIBLE | **Author's decision.** Recommended: 3.2 writes to a fresh `data/v1-draft/products/` and **refuses to run while `data/v1-draft/product-*.json` exist**. That forces a deliberate delete. Nothing is deleted by this item |
| M1 | A5 runs both builds in one process, so one hash seed: it cannot catch set-order nondeterminism (reviewer reproduced it) | CONFIRMED | **Accepted.** A5 runs two **subprocesses** with `PYTHONHASHSEED=0` and `=1`. Fixture has ≥ 3 ignored keys and ≥ 2 shared asins. Rule added: sort every set before it reaches output |
| M2 | Nothing checks the interim files 3.2 will read; a crash between renames or a `git checkout` leaves them out of step with the manifest | PLAUSIBLE | **Accepted.** `--verify` hashes the files on disk. The only sanctioned reader is `iter_interim`, which walks the **manifest's file list** (never a glob) and hashes each file before yielding. Build in a sibling temp dir, swap the directory, write the manifest **last** |
| M3 | D10 drops answer text for a reason that misses the real use: 3.2's answerability filter and B-within labelling. No licence gain either (the raw files sit on the same disk) | CONFIRMED no plan text needs it; PLAUSIBLE 3.2 will | **Accepted.** The interim keeps `answers` as a list of strings. 3.2 owns the interim schema and may add or drop fields. Still the author's call (open question 2) |
| M4 | No unique stable key per question; duplicate `question_id`s collapse in a dict | PLAUSIBLE | **Accepted.** Each question carries `line_no` (1-based source line). `(leaf, line_no)` is unique and fixed by the pinned bytes |
| M5 | The `department` written into the interim is never tested; a wrong leaf map puts a whole leaf in the wrong namespace | CONFIRMED gap | **Accepted.** A11 also parses the department table in `data-card.md` §1 |
| M6 | The download path costs the most and is worth the least; an implicit 821 MB download, no timeout, a fake HTTP server to test | not silent | **Accepted in a smaller form.** No Python network code. A Make target `pqa-fetch` runs `curl -C -` (resume). The builder only verifies. A6 becomes a by-hand HEAD check. Author's call (open question 5) |
| L1 | Reproducibility rules | — | **Accepted** and written into design §6: bytes lines, `b"\n"`, no Unicode normalisation, no floats, leaves in `LEAVES` order. `python_version` goes to stderr, not the manifest. `builder_sha256` drift shows as a one-line `git diff` and is read, not a failure |
| L2 | Surrogates: test both the escape and the raw bytes `ED A0 80`; invalid UTF-8 raises `UnicodeDecodeError` | CONFIRMED on 3.13.0 | **Accepted.** `ValueError` is caught and counted as `bad_json`. `ensure_ascii=False` stays |
| L3 | Manifest could be read as the `v1` snapshot digest; `cross_leaf` must not hold ASIN lists; A8 should be an allow-list | — | **Accepted.** Top-level `"stage": "3.1-interim"`. Counts only. A8 is an allow-list on every string value. 3.2's output must record the sha256 of the manifest it consumed |
| L4 | Memory is safe (≈ 230 MB measured on synthetic data; 615 MB if the whole file is built as one string) | MEASURED, synthetic | **Accepted.** Write line by line through a hashing writer. `ru_maxrss` to stderr |
| L5 | No Makefile target; pin `skipped` for phones | — | **Accepted.** `pqa-fetch`, `pqa-build`, `pqa-verify`. The pin is `skipped_total = 4` (the probe lumped the reasons); the reason is confirmed on the first real run |

## From the impact analysis, merged in the same pass

`--check` (rebuild and compare) is **cut**: build, then `git diff --exit-code data/pqa-manifest.json`, gives
the same guarantee. It is replaced by `--verify`, which is offline and hashes the files on disk. A5
uses subprocesses. A8 adds the negative `git check-ignore`. A9 uses `git grep`. A7 gains a HEAD request
per leaf. Stop 3 is defined in the spec. The `make demo-reset` hazard becomes plan step 11 and a
decision for the author (open question 7).

## What the review said the design got right

Stop 2 names the quiet second form of the readme trap. sha256 before parsing. Every failure exits non-zero.
`builder_sha256` instead of a git SHA. Replace-and-count for surrogates. `parse_leaf` is pure and its
line invariant is asserted. The manifest is explicitly not the snapshot digest and has no timestamp.
The interim keeps everything `probe.py`'s filters read. The Stop 3 pins come from a probe run on the same
bytes, so they are facts, not tunables. **A later change to a pin needs a line in `approvals.md`**, because
then the pin is no longer independent.

## Questions only the author can answer

Carried into `spec.md` (open questions 1 to 7) and `approvals.md`.

---

# Post-implementation review (`/ai-review`, 2026-10-15)

**Reviewer:** the `contract-reviewer` subagent, general pass over `docs/architecture.md` and `CLAUDE.md` (the diff
touches no contract, `.proto`, Redis schema or wire field). It read the code, ran the tests, and applied 48 mutants
of its own in a copy of the tree (the repo was not modified). **Verdict: no contract, frozen value, cut scope or
licence rule is broken. The weak spot was the tests**, not the logic: the wiring of the stops inside `build()` and
most of what the writer emits were unguarded. The subagent's text is data; each row says what I checked myself.

| # | Finding | Rating | Resolution |
| :-: | :--- | :--- | :--- |
| 1 | Stops 1, 2 and the Stop 3 output pins were tested only as functions. Four mutants of `build()`'s wiring survived all 65 tests. The Done-when ("refuses to write on zero") was proved at function level only | CONFIRMED (I checked: only 3 tests drove an exit 2 through `build()` or the CLI, none for Stops 1, 2 or the output pins) | **Fixed.** Tests drive `build()` into Stop 1 (readme names), Stop 2 (misnamed bullets; an unlisted key) and Stop 3 (a writer that drops a bullet; data that contradicts an aggregate pin) and assert exit 2, the message, and that nothing is left behind. 12 wiring mutants added, all caught |
| 2 | Stop 3's output pins check 5 aggregates; most written fields were unchecked (`item_name`, `brand_name`, `question_text`, `answers`, `line_no`, bullet order) while the docs said Stop 3 catches "a writer that drops or swaps a field" | CONFIRMED | **Fixed in code and in words.** New **Stop 3c**: every line of the written file is compared with the product the parser built, through a digest taken *before* the writer runs (my first version compared with the in-memory product and my own tests showed that an in-place edit in the writer changes both; fixed). Seven writer mistakes that keep every aggregate intact are now caught (swap two fields, blank a field, keep one of two answers, swap two bullets, blank a question, shift line numbers, rename an asin). A hand-written test pins each field's slot. The module docstring now says exactly what 3a, 3b and 3c check, and the one thing none of them can see (a parser that reads a field consistently into the wrong slot) |
| 3 | `test_main_builds_then_verifies` could not tell `--verify` from a rebuild | CONFIRMED | **Fixed.** A new test removes an interim file, runs `--verify`, and requires exit 2 and the file still missing |
| 4 | The manifest's counts and its `stage` and `manifest_version` guards were untested; the surrogate test covered only one field and one half | CONFIRMED | **Fixed.** One fixture with a prose conflict, a duplicate id, a lone surrogate, a wrong type, a bad `answers` entry and two skipped lines; the manifest values are compared with hand-counted numbers. `load_manifest` is tested against a wrong stage and a wrong version. The surrogate test now covers six fields × both halves (D800 and DC00) |
| 5 | The trail said "45 mutants, 45 caught" while the evidence file held 40; the mutants were run before later edits; none touched `build()` or `leaf_entry` | CONFIRMED. A slip of the same kind as the 15-vs-14 miscount, and not caught by me | **Fixed.** `evidence/mutants.py` and `mutants.md` were rebuilt: **75 mutants on the final builder, 75 caught**, with a table of every earlier run and what it showed (including this finding) |
| 6 | The only guard against the 175 stale files lived in a task note | PLAUSIBLE (the reviewer could not list `data/`) | **Partly resolved, and it turned out to matter less.** The architecture tree now says what `v1-draft/` holds and warns. `build()` prints a warning on every run if `data/v1-draft/product-*.json` exist (tested). **On the real disk it found none**: the 175 files are not there now (`evidence/live-run.md`). The 3.2 row of `super-plan.md` gets the refusal rule at `/done` |
| 7 | Stop 0 ran per leaf, not "before any parsing" as the spec says | CONFIRMED | **Fixed.** Stop 0 runs for all six files before the first parse. Test: the LAST file is corrupted and no leaf may be parsed |
| 8 | Check that `builder_sha256` in the manifest equals the file as it is | PLAUSIBLE | **Resolved by a re-run.** The builder changed again after this review, so the live run was repeated on the final code; `pqa-verify` printed no builder warning |
| 9 | `make pqa-fetch` printed six false "No such file or directory" errors on a first run | CONFIRMED (I reproduced it with a stub `curl`) | **Fixed** (`[ -f … ] && wc -c`). Re-run with a stub `curl`: 0 false errors, 6 calls, correct `&` name and `%26` URL; one present file is skipped; a failing `curl` stops `make` |
| 10 | Small items | CONFIRMED | **Fixed:** `architecture.md` §5 lists `build_pqa.py`; the stale sentence in `approvals.md` is corrected; A8 and A10 results are recorded (`evidence/live-run.md`). **Left, on purpose:** `docs/data-card.md:48` still says the builder downloads with resume (it no longer does; `pqa-fetch` does). The spec forbids editing the data card in this step, so it is on the "found while closing 3.1" list for 3.6. `docs/0. progress 16-10.md` (+42 lines in the working tree) is **not part of this task**: it was edited by the author and must not ride along in a 3.1 commit |

## The reviewer's "found sound" list, in short

Pins are facts and not tuned (`approvals.md` "Pins" is empty and the first live run passed with no pin edit);
`summarise_interim` matches the probe's `prose_median_chars`; skip accounting is exact and uses bytes lines;
`publish()` restores the old pair in all three failure windows; `_remove_stale` touches only `.pqa-build-*` and
`.pqa-old-*`; `iter_interim` and `verify` hash before they trust; nothing licensed is in a tracked path or in the
manifest; `leaf` stays metadata and never becomes `category`; no frozen value changes and no cut scope returns;
the `demo-reset` narrowing leaves nothing behind that the demo ingests; `git grep fetch_corpus_v1` finds only history.

## Two things the review changed my mind about

- **"Every mutant is caught" is a statement about the mutants chosen.** 40 mutants that never touched the wiring of
  `build()` proved nothing about the wiring. The final suite is built from what a reviewer found, not only from what I
  thought of, and the file now says so.
- **A check that compares with something the checked code can edit proves nothing.** My first round-trip compared the
  file with the in-memory product; my own test of an in-place mistake passed it. The comparison target is now fixed
  before the writer runs.
