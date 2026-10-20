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
