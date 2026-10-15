# Spec — pqa-build-script (super-plan item 3.1)

**Scope:** L · **Opened:** 2026-10-15 · **Revised:** 2026-10-15 after impact and design review · **Branch:** main (the author said main is fine)

**Why L.** The script lives in `experiments/` and decides which records the corpus has. Every later
measurement reads its output. Between M and L we take the larger.

## The change in one sentence

Replace `experiments/scripts/fetch_corpus_v1.py` (it reads the wrong dataset, Amazon-Reviews-2023)
with a builder for the six pinned Amazon-PQA files: it checks the source bytes, parses them against
the real field names, stops on a bad parse, and writes a hash manifest — never the raw text to a
place git can see.

## Phase and item

- **Phase 3**, item **3.1**. Discharges C1 and C3. Rests on ADR-002 and `data-card.md` §1.
- Unblocks **3.2** (selection). 3.2 reads this item's output, through `iter_interim` only.
- `requirements.md` is still empty, so there are no FR / NFR / RR ids to cite.
- Carry-forwards it discharges: item 1.4's note that the builder must not emit text redis-py's strict
  UTF-8 encoder rejects (a lone surrogate), and the 2026-10-03 review's finding 6 (see "Out of scope").

## What the builder does

1. **Verify the sources.** The six leaf files live in `data/raw/pqa/`. Their sizes and sha256 are
   pinned in the script and equal the table in `data-card.md` §1. A missing file, a wrong size or a
   wrong hash stops the run before any parsing and says what to do. **The builder has no network code.**
   Downloading is `make pqa-fetch` (`curl -C -`, resume), a separate step (open question 5).
2. **Parse against the bytes.** Stream each file as bytes lines (the biggest is 821 MB). Read the real
   fields: `asin`, `question_id`, `question_text`, `question_type`, `answers`, `answer_aggregated`,
   `brand_name`, `item_name`, `product_description`, `bullet_point1` … `bullet_point5`. The readme's
   names (`asin_id`, `bullet_points`, `is_yes-no_question`, `yes-no_answer`, `answer_text`) are never read.
3. **Check the parse** with the stops below. All six leaves are checked before any final file is written.
4. **Write.** Build into a temp directory next to the final one, swap the directory in, write the
   manifest **last**.

## The stops

Every stop ends the run with exit code 2 and writes nothing under a final name.

- **Stop 0, source.** Size, then sha256, equal the pinned values.
- **Stop 1, parse rate.** A leaf that parses zero records stops the run. This is the Done-when of 3.1.
- **Stop 2, fields.** (a) A real field that is non-empty in **zero** records of a leaf stops the run.
  The readme trap has a quiet second form: `asin` and `question_text` parse, the bullets are misnamed,
  and every product has empty prose with no error. The floor is one record, not a percentage, because
  the data card says 2.7 – 9.1 % of products have no bullets and no description; any higher floor
  would be invented. (b) A key seen in the file that is not in the real field set stops the run, unless
  it is in `IGNORED_KEYS` with a written reason. This catches a field the builder forgot to list, which (a) cannot.
- **Stop 3, pins.** The counts must equal numbers pinned in the script. They are facts about pinned
  bytes, not settings, and they come from the 2026-10-03 probe, which was written separately.
  *Input pins:* records parsed, products, skipped total. *Output pins:* the `question_type` counts, the
  `answer_aggregated` counts and `prose_median_chars`, **computed by re-reading the interim file as
  written**, using the probe's definition. Stop 1 and 2 check what goes in. Stop 3 is the only check on
  what comes out: a builder that drops `bullet_point5` from every product passes Stops 1 and 2.
  A later change to a pin needs a line in `approvals.md`.
  *Stop 3c, added after the code review:* every line of the written file must equal the product the parser built
  (compared with a digest taken before the writer ran). The aggregates above cannot see a writer that swaps or blanks
  a field that is not one of them.

## Output

- **Interim files** (gitignored, derived from licensed text): `data/v1-draft/pqa/<leaf>.jsonl`, one line
  per product, sorted by `asin`. A line holds the product fields once, `leaf`, `department`, and its
  questions as `{line_no, question_id, question_text, question_type, answer_aggregated, answers}`.
  `line_no` is the 1-based source line, so `(leaf, line_no)` is unique and fixed by the pinned bytes.
  `answers` is the list of answer strings (open question 2). **3.2 owns this schema from here** and may
  add or drop fields; it then rebuilds the manifest.
- **Manifest** (tracked, only hashes and counts, no PQA text): `data/pqa-manifest.json`.
  It says `"stage": "3.1-interim"` and that it is **not** the `v1` snapshot digest (that is item 3.6's).
  Contents are listed in `design.md` §4.
- **The only sanctioned reader** is `iter_interim(manifest, interim_dir)`. It walks the manifest's file
  list, never a glob, and hashes each file before it yields a line.

## Acceptance — each is a command or a test

| # | Check | How |
| :-: | :--- | :--- |
| A1 | A fixture in the **readme's** field names parses zero records. Exit 2, no file written, and the message names the field it could not find and the unknown key it saw instead | unit test |
| A2 | `asin` and `question_text` right, all five bullets misnamed: stopped by Stop 2(a). An extra key such as `bullet_point6`: stopped by Stop 2(b) | unit tests |
| A3 | A builder that drops one bullet from the output is stopped by Stop 3's output pins | unit test with a deliberately broken writer |
| A4 | A wrong size or sha256 stops the run before parsing. The message names `make pqa-fetch` and says to delete a full-size file that fails the hash | unit test |
| A5 | A lone surrogate, as the escape `\ud800` **and** as the raw bytes `ED A0 80`, does not crash the write and is counted. Invalid UTF-8 on a line is counted as `bad_json` | unit test |
| A6 | Two builds in **subprocesses** with `PYTHONHASHSEED=0` and `=1` give byte-identical interim files and manifest. The fixture has ≥ 3 ignored keys and ≥ 2 shared asins, so the order can differ | unit test |
| A7 | On the six real files: all stops pass; the totals are 1,212,029 questions and 71,794 products (sum of per-leaf distinct asins); skipped total 4, all in `unlocked_cell_phones` (probe numbers). A second build prints the same `manifest sha256` as the first (*changed during the build: `git diff` on a new untracked file passes vacuously; see `evidence/live-run.md`*). `make pqa-verify` passes. By hand, one HEAD request per leaf returns 200 and a `Content-Length` equal to the pinned bytes (this also settles the `&` in the `led_&_lcd_tvs` name) | live run, by hand; `make verify` never runs it |
| A8 | Every string value in the manifest is a hex digest, a field name, a leaf or department name, a file name, a URL or a fixed skip reason. `git check-ignore data/pqa-manifest.json` exits **1** (tracked). `git check-ignore data/v1-draft/pqa/<leaf>.jsonl` exits **0** | unit test + two commands |
| A9 | `git grep -n fetch_corpus_v1` finds only history lines, and `experiments/README.md:5` no longer says "corpus fetcher" (checked by eye) | command |
| A10 | `make test` and `ruff check experiments` pass. Run `ruff` by hand: `make lint` prints SKIPPED when ruff is not on `PATH`. After `make test`, `git status --porcelain data/` is the same as before it (tests never write there) | commands |
| A11 | The sizes, sha256 and leaf → department map pinned in the script equal the table in `data-card.md` §1. The pinned `parsed`, `products`, skipped total, `question_type`, `answer_aggregated` and `prose_median_chars` equal `docs/work/2026-10-03-pqa-category-choice/probe_results.json` | unit test |
| A12 | `iter_interim` raises before yielding when an interim file is changed, missing or cut short. A file not in the manifest is ignored | unit test |
| A13 | A failure injected after the temp directory is written leaves the old `pqa/` and the old manifest untouched, and no temp directory behind | unit test |
| A14 | `build()` itself, not only `check_leaf`, ends in exit 2 with nothing left behind for: readme names (Stop 1), misnamed bullets (Stop 2), an unlisted key (Stop 2b), data that contradicts an aggregate pin (3b), and a writer that drops a bullet | unit tests |
| A15 | Seven writer mistakes that keep every aggregate intact are caught by Stop 3c; `check_round_trip` notices a repeated line, a missing product, and a wrong leaf, and names a line, never a value | unit tests |
| A16 | `--verify` is not a rebuild; the manifest's counts equal hand-counted numbers; `load_manifest` rejects a wrong stage and a wrong version | unit tests |
| A17 | Stop 0 runs on all six sources before any parse | unit test |

## Out of scope

- **Selection** (thick tail, price / stock / carrier filters, near-duplicate pairs) — item 3.2.
- The **answerability filter** — not designed; part of 3.2.
- **Writing `product-*.json` records** (doc_id, `category`, `specs`) and chunking. No item owns this
  today. Proposed: 3.2, into a fresh `data/v1-draft/products/` (open question 4).
- **The interim's `leaf` field is metadata only.** At 3.2 it must not become `category` or reach text that
  is embedded (`ingest.py` embeds the `Category:` line). Leaf provenance in the retrieval text would let
  it leak into the namespace.
- Policy documents (3.3), workload generator (3.4), G5 (3.5), freeze and digest (3.6).
- **Deleting the 175 stale files** that `fetch_corpus_v1.py` left in `data/v1-draft/`. They are from the
  wrong dataset. Removing them is the author's call (open question 4).
- Any change to ADR-002, the text of `data-card.md`, `corpus_gate.py`, `interfaces.md` or the `.proto`.
  A `data-card.md` edit that the manifest needs is a separate step with its own OK.
- Parallel byte-range downloads and any Python network code.

## Open questions — resolved by the author on 2026-10-15

**All seven: yes to the proposal in each. Question 4: option A** (3.2 writes to a fresh
`data/v1-draft/products/` and refuses to run while the 175 old files exist; nothing is deleted by 3.1).
Question 5: `curl -C -` in a Make target. Question 7: narrow `make demo-reset` to `data/dev-v0/`.
The text below is kept as asked.

1. **Manifest path.** One tracked **file**, `data/pqa-manifest.json` (no new directory; the precedent is
   `data/workload-{version}.json`). Proposed. It is not covered by any ignore rule today.
2. **Keep the answer strings in the interim?** *Changed after review.* Proposed: **yes**, as a list of
   strings. Dropping them saves about 120 MB and gains no licence safety (the raw files with the same
   text sit on the same disk, both gitignored), and 3.2's answerability filter or B-within labelling may
   need them. A rebuild takes minutes.
3. **Lone surrogate:** replace with U+FFFD and count, or drop the whole record and count? Proposed:
   **replace and count**: dropping a question changes the question count, and so `K`'s source, without a trace.
4. **The 175 stale files and the `product-*.json` writer.** Proposed: 3.2 writes drafts into a fresh
   `data/v1-draft/products/` and **refuses to run while `data/v1-draft/product-*.json` exist**, so the
   delete is a deliberate act. Or: you delete the 175 files now. Either way, 3.6 freezes from the new
   directory only.
5. **Download.** Proposed: a Make target `pqa-fetch` with `curl -C -` (about ten lines, no Python
   network code, no CA bundle problem), and the builder only verifies. The alternative is Python
   Range/resume behind an explicit `--download`, which needs a fake-server test.
6. **Who owns the interim schema?** Proposed: 3.2, as written above.
7. **`make demo-reset` runs `git checkout -- data/`** (`Makefile:183-188`). It would silently revert a
   regenerated, uncommitted `data/pqa-manifest.json`. Proposed: narrow that restore to `data/dev-v0/`,
   which is the corpus the target ingests. This is a one-line change to a target outside 3.1's files, so
   it needs your OK.

## What I could not check

`data/` could not be listed from this session (Bash was denied on `data/` paths). The real field set is
taken from `data-card.md` §1 and the 2026-10-03 probe, not re-read from the bytes. The first
implementation step prints the key census of a few real lines per leaf. Stop 3 and A7 catch a mistake here.
