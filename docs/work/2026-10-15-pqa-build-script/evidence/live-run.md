# Live run on the six real files (plan step 12, acceptance A7)

**Final run:** 2026-10-15, on the final builder (103 tests, 75 mutants). It follows an earlier run on a
previous version of the builder; both are described below. **Not a measurement.** It is a corpus build.
Memory pressure before the final run:

```
kern.memorystatus_vm_pressure_level: 1
System-wide memory free percentage: 61%
```

Pressure level 1 with 61 % free, Ollama idle. A corpus build needs about 585 MiB (below), and nothing here
is cited as a measurement, so the run was not repeated under level 0.

## What the real files gave

All stops passed on the first run against the real bytes, then again on the final builder. That includes Stop 3's
**output** pins (`question_type` counts, `answer_aggregated` counts, `prose_median_chars`, read back from the
interim file as written), which came from the 2026-10-03 probe, a separate program. The new field-by-field
round trip (Stop 3c) also passed on all 1,212,029 questions.

```
leaf                       lines    parsed  skipped  products
unlocked_cell_phones     499,539   499,535        4    15,298
traditional_laptops      291,896   291,896        0    19,742
led_&_lcd_tvs            137,881   137,881        0     3,970
over-ear_headphones      139,146   139,146        0     6,605
chairs                    88,268    88,268        0    19,193
home_office_desks         55,303    55,303        0     6,986

leaf                   prose_conflicts  duplicate_qids  surrogates  bad_type  answers_bad
unlocked_cell_phones                 5               0           0         0            0
traditional_laptops                 21               0           0         0            0
led_&_lcd_tvs                       13               0           0         0            0
over-ear_headphones                  1               0           0         0            0
chairs                              31               0           0         0            0
home_office_desks                    7               0           0         0            0
skipped, unlocked_cell_phones: bad_question_text 4
asins shared between leaves: none
totals: questions 1,212,029, products 71,794 (sum of leaf distinct), 71,794 distinct across leaves
```

Peak RSS, printed to stderr by the same runs: 614,481,920 and 613,859,328 bytes. `ru_maxrss` is bytes on macOS,
so **about 586 MiB** (design estimate: 250 – 500 MB; the first version of the builder peaked at 551 – 567 MiB, and the
round trip added about 20 MiB). Wall time 41.4 s for a build (user 38.9 s).

## Determinism and verify

Three commands, three identical manifest hashes. The manifest holds the sha256 of all six interim files, so
this is also a byte-for-byte check of the interim files across two builds.

| Command | `manifest sha256` |
| :--- | :--- |
| `make pqa-build` (1st) | `bf0feb48802fae20afde94257adefd3b743738a3d3a76f719c4582b2eb98465a` |
| `make pqa-build` (2nd) | `bf0feb48802fae20afde94257adefd3b743738a3d3a76f719c4582b2eb98465a` |
| `make pqa-verify` | `bf0feb48802fae20afde94257adefd3b743738a3d3a76f719c4582b2eb98465a` |

No `builder_sha256` warning from `pqa-verify` (the manifest names the builder as it is now). Earlier runs, with
earlier versions of the builder, also agreed with themselves (`b8d8361a…`, then `5be6f1a4…`); each hash changed
when the builder changed, as `builder_sha256` makes it do. **The manifest on disk was written by the final builder.**

> **A correction to the plan.** Plan step 12 and spec A7 said to compare builds with
> `git diff --exit-code data/pqa-manifest.json`. The manifest was an untracked new file, so that command
> would have passed vacuously. The builder now prints the manifest's own sha256 and the runs are compared
> by that (test `test_build_and_verify_print_the_sha256_of_the_manifest_file`). Once the manifest is
> committed, `git diff --exit-code` becomes a real check as well.

## The six HEAD requests (A7, by hand)

Read-only `curl -sI` to the dataset's public S3 host, one per source, URLs taken from `build_pqa.py --list`
(run on the earlier version of the builder; `--list` has not changed since):

```
amazon_pqa_unlocked_cell_phones.json     status=200 content-length=821444488 pinned=821444488  ok
amazon_pqa_traditional_laptops.json      status=200 content-length=403702059 pinned=403702059  ok
amazon_pqa_led_&_lcd_tvs.json            status=200 content-length=178273635 pinned=178273635  ok
amazon_pqa_over-ear_headphones.json      status=200 content-length=278531682 pinned=278531682  ok
amazon_pqa_chairs.json                   status=200 content-length=138252584 pinned=138252584  ok
amazon_pqa_home_office_desks.json        status=200 content-length=95549762 pinned=95549762  ok
```

The `&` in `led_&_lcd_tvs` is `%26` in the URL, and that works. **The real download was not run**: all six files
were already on disk. `make pqa-fetch` against the real host printed `present` six times and made no request.
After the `/ai-review`, the target was also run with a **stub `curl`** on an empty directory (6 calls, correct
`&` file name and `%26` URL, no false errors), with one file already the right size (skipped, 5 calls), and with a
failing `curl` (`make` stops with `Error 1`). **The resume path (`curl -C -`) has still never run against the real
host.**

## A8 and A10, final state

| Check | Result |
| :--- | :--- |
| `git check-ignore -q data/pqa-manifest.json` | exit **1**: not ignored, so it can be committed |
| `git check-ignore -q 'data/v1-draft/pqa/led_&_lcd_tvs.jsonl'` | exit **0**: ignored |
| `git check-ignore -q 'data/v1-draft/.pqa-build-1/interim/x.jsonl'` | exit **0**: the temp directory is ignored |
| `git status --porcelain data/` before and after three real runs | identical: `?? data/pqa-manifest.json` (a new file, not yet committed) |
| `git status --porcelain data/` before and after `make test` | identical (run earlier) |

## What the run settled (design §7)

| # | Unknown | Answer |
| :-: | :--- | :--- |
| 1 | Real field set | Matches (`key-census.md`), and Stop 2(b) found no extra key in all 1,212,029 records |
| 2 | A field empty in a whole leaf | None: Stop 2(a) passed on all six |
| 3 | `&` in the URL | `%26` works (200) |
| 4 | Prose that differs between records of one asin | **78 asins of 71,794 (0.11 %)**: 5, 21, 13, 1, 31, 7 per leaf in the order of the table. The first parsed record wins for those |
| 5 | The same asin in two leaves | **None.** 71,794 distinct across leaves, equal to the sum |
| 6 | Duplicate `question_id` | **0** in every leaf |
| 7 | Reason for the 4 skipped | All 4 are `bad_question_text`, all in `unlocked_cell_phones` |
| 8 | Peak memory | about 586 MiB |
| 9 | **The 175 stale files in `data/v1-draft/`** | **The builder found none.** On every real build it globs `data/v1-draft/product-*.json` and warns if any exist; it did not warn. So the wrong-dataset files that the spec, `impact.md` and `.gitignore` describe are **not on this disk now**. They may have been removed, or may only ever have been staged in git. The warning stays as a guard, and 3.2's refusal to run while such files exist stays on its list |
| – | Lone surrogates, wrong-type values, bad `answers` entries | **0, 0, 0** |
