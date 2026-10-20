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
