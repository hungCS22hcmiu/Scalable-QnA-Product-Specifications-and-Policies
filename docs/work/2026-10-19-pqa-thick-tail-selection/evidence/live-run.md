# Live runs on the real files

**Not measurements.** Corpus builds over pinned bytes: no model is loaded. Memory pressure was level 2
(34 – 42 % free) for all of 2026-10-20; that cannot change a count over fixed bytes.

## Plan step 5 — the builder with `fields_conflict` (2026-10-20)

`make pqa-build` twice, then `make pqa-verify`, on the builder after plan step 4 (109 tests).

| Command | `manifest sha256` |
| :--- | :--- |
| `make pqa-build` (1st) | `741d52e359e2bb95694ffbfa4b80e16941b6d7ec3de813948c5b2ca34c217c3f` |
| `make pqa-build` (2nd) | `741d52e359e2bb95694ffbfa4b80e16941b6d7ec3de813948c5b2ca34c217c3f` |
| `make pqa-verify` | `741d52e359e2bb95694ffbfa4b80e16941b6d7ec3de813948c5b2ca34c217c3f` |

- Every stop passed, the Stop 3 pins unchanged. The new `check_flags` passed on every leaf, so the
  products flagged `fields_conflict` equal `prose_conflicts`: **5 / 21 / 13 / 1 / 31 / 7, 78 in all**,
  the same as the 3.1 live run.
- The counts per leaf (lines, parsed, skipped, products) are identical to 3.1's
  (`docs/work/2026-10-15-pqa-build-script/evidence/live-run.md`).
- Peak RSS 577,650,688 bytes, about 551 MiB.
- The 3.1 manifest `bf0feb48…` is replaced by `741d52e3…`. That was expected: every interim line gained a
  key, `MANIFEST_VERSION` is 2, and `builder_sha256` changed.

## Plan step 16 — the first live selection: a short leaf (2026-10-20)

`make pqa-select` on the selector of `ea63e5d`, memory pressure level 1. 46 s, peak RSS 94 MB.

**The probe pins held**, so the copied filters reproduce the 2026-10-03 probe on the real bytes, for
both pools and all six leaves. **Then the draw stopped (exit 2), as designed:** `led_&_lcd_tvs` has 13
eligible products against a quota of 19. Nothing was written.

The funnel, from a read-only diagnostic (the same `generic_tokens` and `tally` calls, no output files):

| Leaf | In | titled | bullets | no_warranty_term | consistent | cap | answerable | pair | **Eligible** | Quota |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `unlocked_cell_phones` | 15,298 | 0 | 2,818 | 1,145 | 5 | 6,740 | 4,033 | 352 | **205** | 38 |
| `traditional_laptops` | 19,742 | 1 | 2,431 | 4,847 | 15 | 7,508 | 4,593 | 270 | **77** | 38 |
| `led_&_lcd_tvs` | 3,970 | 0 | 465 | 340 | 12 | 2,029 | 1,078 | 33 | **13** | 19 |
| `over-ear_headphones` | 6,605 | 1 | 1,080 | 1,090 | 1 | 2,634 | 1,532 | 215 | **52** | 19 |
| `chairs` | 19,193 | 0 | 1,751 | 1,376 | 29 | 12,303 | 3,484 | 185 | **65** | 19 |
| `home_office_desks` | 6,986 | 0 | 433 | 828 | 7 | 3,830 | 1,727 | 121 | **40** | 19 |

The answerable share of all spec questions, all products of each leaf:

| Leaf | Spec questions | R1 | R2 | R2 tags covered only by the title |
| :--- | ---: | ---: | ---: | ---: |
| phones | 318,316 | 15.2 % | 10.7 % | 6.8 % |
| laptops | 276,942 | 13.9 % | 8.3 % | 9.2 % |
| TVs | 133,927 | 12.2 % | 6.5 % | 6.6 % |
| headphones | 134,789 | 16.0 % | 11.2 % | 5.9 % |
| chairs | 84,266 | 20.9 % | 14.2 % | 6.7 % |
| desks | 53,892 | 17.4 % | 12.2 % | 3.6 % |

All are below ePQA's 22.9 % (an upper bound for a PQA record). The `answerable` step removes the
most products everywhere after `cap`. **Waiting for the author:** the pre-registered fallback, step 1
(design §2.3), would give TVs' shortfall of 6 to `over-ear_headphones` (52 eligible), so TVs 13 +
headphones 25 = 38 for `electronics`.

## Plan step 16 — the selection with fallback step 1 (2026-10-20)

The author applied pre-registered fallback step 1 (`approvals.md`): TVs 13, headphones 25.

**A run in between crashed on a report, not on the rule.** `SentenceSplitter` refused one record of the
TV **probe pool** (a 1,353-character title: the metadata, which holds the title, was longer than the
256-token chunk). A read-only diagnostic found it the only one: 0 of the 152 selected and 0 of the 452
eligible products are affected. Nothing was published. The fix (no rule change): the report counts such a
record in the probe pool, and **stops the run if a selected product has one**, because `make ingest` would
fail on it. Two tests.

**Then two runs, memory pressure level 1, 50 s, peak RSS 233 MB:**

| | |
| :--- | :--- |
| consumed `pqa-manifest.json` | `741d52e3…` (as `make pqa-verify`) |
| `selection sha256`, run 1 and run 2 | `036dcae86afbf5cd40daf1ab6436966c2cc64a298736a9c44cb39a8312c0df23` both |
| `make pqa-select-verify` | passes |
| products | **152**: phones 38, laptops 38, TVs 13 + headphones 25, chairs 19 + desks 19 |
| question pool | **4,706** lines: 1,180 answerable spec, 3,399 unanswerable spec, 127 policy (92 warranty, 35 return) |

The probe pins held on both runs. Per selected product (median, min–max):

| Leaf | Kept | Policy | Answerable (R2) | Unanswerable |
| :--- | :--- | :--- | :--- | :--- |
| phones | 36 (11–49) | 1 (0–5) | 8 (5–16) | 24 (4–41) |
| laptops | 34 (13–50) | 1 (0–4) | 7 (5–15) | 26 (8–44) |
| TVs | 36 (12–50) | 0 (0–2) | 6 (5–14) | 29 (4–38) |
| headphones | 23 (7–48) | 0 (0–1) | 6 (5–22) | 15 (1–32) |
| chairs | 25 (11–47) | 0 (0–5) | 6 (5–13) | 20 (4–42) |
| desks | 29 (11–49) | 0 (0–2) | 7 (5–13) | 20 (4–39) |

**Three things the author should read:**

1. **The selection leans hard toward long product text (review M4, confirmed).** Median embedded text,
   characters / chunks, selected against the probe pool: phones 1,711 / 3 against 1,068 / 2; laptops
   1,201 / 3 against 763 / 2; TVs 918 / 2 against 561 / 1; headphones 2,769 / 5 against 1,384 / 2; chairs
   985 / 2 against 757 / 1; desks 1,739 / 3 against 771 / 1. The `data-card.md` §1 statement that PQA
   products chunk to about one chunk is not true of the selected corpus. More chunks per product gives
   containment more of a gradient: a corpus property that moves in the headline's direction.
2. **R2-answerable share:** 20–36 % of the selected products' spec questions, against 6.5–14 % over all
   products. The `answerable` and `pair` steps select for it, as designed.
3. **Policy questions are scarce:** 127 in the pool, median 0 or 1 per product. 3.4's policy wording will
   have to come from more than these products.

Re-asks, pooled, `1 − clusters / questions` (exact only / all): unfiltered phones 3.1 % / 10.1 %,
filtered 3.1 % / 11.6 %; the per-leaf counts are in the manifest. Digit flips: 0 or 1 per leaf filtered,
3 – 68 unfiltered. Carrier drops: phones 163,844 questions; laptops 1,095; TVs 283; headphones 136;
chairs 41; desks 20. The non-phone ones are probably mis-drops (review L3 showed "bass boost" matches
`CARRIER_Q`); they were not read one by one.

## After `/ai-review` — the re-run (2026-10-20)

The review's code fixes (the pool fields renamed `r2_answerable` / `r1_answerable`; no character histogram;
the chunker and the llama-index-core version recorded in the manifest; the audit sheet protected once marked)
change `select_pqa.py`, so the selection was run again, twice, at memory pressure level 1:

| | Before | After |
| :--- | :--- | :--- |
| products digest (`outputs.products_sha256`) | `d373c4b0…` | `d373c4b0…` **unchanged** |
| generic-token digest | `42cd6b65…` | `42cd6b65…` **unchanged** |
| question pool digest | `803c8388…` | `50cdcb03…` (the field rename only; 4,706 lines both) |
| selection manifest sha256 | `036dcae8…` | `5033ad96…`, the same on both runs |
| `make pqa-select-verify` | passes | passes |
| `make pqa-audit-score` | 21 / 39 / 1 / 39 | 21 / 39 / 1 / 39, `audit.json` byte-identical |

The 152 records are byte-identical, so the rule and the draw did not move. The manifest now records
`chunker: {chunk_size 256, chunk_overlap 40, llama_index_core 0.14.23}`. **The anchor for reproducibility is
the products digest**, not the selection manifest's hash, which also covers the selector file.
