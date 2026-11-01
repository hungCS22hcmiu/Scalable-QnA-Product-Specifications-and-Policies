# Cost of the judge, one functional run (DC 11)

Written 2026-11-01. Numbers only: no question text, no answer text, no product titles.
Every number below is `citable: no`. It comes from one functional run on the validation split, with
the machine in pressure 1 or 2, and no rate here is used for any choice.

## The run

- Run id `2026-11-01T21-17-56_cfg4_judgecost`: configuration 4, `support_gate` on, MIXED off,
  `mutation` off, `CACHE_CAPACITY` 156, one replay of the 622 validation queries (seed 7); citable: no.
- Judge `judge-v1` (`gemma3:4b-it-q4_K_M`), reference set `0e843899…974a` (the 4B writer, Entry 4 of
  `docs/preregistration.md`); citable: no.
- The manifest says `admissible: true`, and `make run-manifest-check` exits 0; citable: no.

## Records and keys

- The replay sent 622 requests and all 622 got HTTP 200, with 0 SHED; citable: no.
- The log holds 528 MISS records and 94 hit records (all 94 are TIER2_HIT, 0 are TIER1_HIT); citable: no.
- There are 622 distinct verdict keys, one per record, so the judge made 622 calls; citable: no.
- Verdicts: CORRECT 459, INCORRECT 163, UNPARSED 0; citable: no.
- By cache, MISS has 396 CORRECT and 132 INCORRECT, and TIER2_HIT has 63 CORRECT and 31 INCORRECT; citable: no.
- `UNPARSED` is 0 of 622 keys (0.0 %), under the 2 % stop rule, so `rates_reportable` is true; citable: no.

## Time

- Seconds per verdict: median 1.483 s, p95 2.510 s, mean 1.609 s (1000.6 s over 622 keys); citable: no.
- The judge's wall time was 1047.1 s (17.5 min), 21:52:56 to 22:10:23 +07; 1000.6 s of it is the 622 verdict
  calls, and 46.5 s is the 30 re-judged keys, the load and the writes; citable: no.
- For context, the replay's wall time was 1963 s (32.7 min), 21:18:39 to 21:51:22 +07; citable: no.

## Pressure and memory

- Replay: pressure 1 at all 13 progress lines and at all 33 one-minute samples; peak 1, never 4; citable: no.
- Judge: `summary.json` holds 13 readings, 8 at level 1 and 5 at level 2; the 18 one-minute samples are 10 at
  level 1 and 8 at level 2; peak 2, never 4. By the one-minute samples, pressure was 1 until 22:02 and 2 from 22:03 to the end; citable: no.
- Swap used stayed between 4.0 and 4.2 GB of 5.1 GB through both stages; citable: no.
- The judge's footprint, read with `footprint -p <runner pid>` as ADR-017 says (runner pid 53748, 34 samples
  every 30 s): 1163 to 1230 MB, peak 1230 MB, and 1229 MB at the first reading; citable: no.
- Of the 1229 MB, `footprint` lists 1080 MB as `untagged (VM_ALLOCATE)`, 96 MB `MALLOC_LARGE` and 43 MB
  `MALLOC_SMALL`; it lists no mapped-file category above 0.2 MB. The weights file is 3.3 GB on disk, so the
  figure may not show the weights; the swap and pressure readings above are the machine-wide signals; citable: no.
- Settled by the main session at step 7.11 (the judge loaded again for the sanity pairs, pressure 1): Ollama's
  `size` 3.72 GB, the runner's RSS 4.26 GB, `footprint` 1.22 GB, the weights blob 3.34 GB. `footprint` leaves out
  the weights mapped from file, as the generator comparison found (`docs/work/2026-11-01-generator-selection/
  README.md`, Memory), so the judge's memory is read as the largest of the three, about 4.3 GB; citable: no.

## Error layers (counts of INCORRECT records, not rates)

- `retrieval` 17 (11 MISS, 6 TIER2_HIT), `generation` 121, `inherited` 9, `reuse` 16, `undecided` 0; the sum
  is 163, equal to the INCORRECT count; citable: no.

## Re-judged keys

- 30 keys (seed 7) were judged a second time, and 0 of the 30 flipped, so `temperature 0` with a seed repeated
  itself on Ollama 0.33.2 in this run; citable: no.

## Projected judge time

The unit: a run with `n` answered records takes about `1.609 s × n + 46.5 s` of judge time (the mean per
verdict and the fixed part above); citable: no. In a once-through replay every `(question, product_id)` is
distinct, so `n` is the split size and one run costs the same in every cell:
- one validation run, n = 622: 1047 s (17.5 min); citable: no.
- one test run, n = 652: 1095 s (18.3 min); citable: no.

The cells come from `docs/super-plan.md` Phase 6 (6.2, 6.3, 6.5). At `mutation: off` there are 7: configuration
1, 2, 3, 4 with gate off and MIXED off, 4 with gate on and MIXED off, 4 with gate on and MIXED on, and 5.

| Part | Runs | Arithmetic | Judge time |
| :--- | :---: | :--- | :--- |
| 7 cells, validation, one run each | 7 | 7 × 1047 s = 7330 s | 2.04 h |
| 7 cells, test, one run each (6.2: report on test) | 7 | 7 × 1095 s = 7668 s | 2.13 h |
| Both splits, one pass | 14 | 7330 s + 7668 s = 14997 s | 4.17 h |
| Each extra sweep point, 5 cells that use τ (3, 4 × 3, 5) | 5 | 5 × 1047 s = 5235 s | 1.45 h |
| Static-cache arm (6.3), 6 cells with a cache, both splits | 12 | 6 × (1047 s + 1095 s) = 12855 s | 3.57 h |
| `(3, on)` and `(5, on)` (6.5), test | 2 | 2 × 1095 s = 2191 s | 0.61 h |

All rows are citable: no. Four things the table does not settle:
- The number of τ points `S` is pinned by item 6.1, and is not known. If configurations 1 and 2 (no τ) run once
  and the other five cells run `S` points on validation, validation costs `(2 + 5 S) × 1047 s`. Test stays 7 runs.
  S = 1 gives 4.17 h for both splits, S = 5 gives 9.98 h (27 validation runs, 7.85 h, plus 2.13 h), and S = 10
  gives 17.25 h (52 validation runs, 15.12 h, plus 2.13 h); citable: no.
- The static arm row assumes configuration 1 has no cache to fill, and one run per cell and split, unswept.
  6.3 does not say whether the static arm is swept; citable: no.
- `judge.py` refuses `mutation: on` today (the gold text depends on the epoch; design.md, out of scope), so the
  `(3, on)` and `(5, on)` row is a time only if a later task lets it judge them. Its `n` could also exceed the
  split size; citable: no.
- The test runs need a test-split reference set first, which is out of scope here. The validation set took about
  62 min to write, so 652 queries would take about 65 min; citable: no.

The per-key time depends on the length of the reference and the answer, and a cell's answers differ (a
no-cache run answers every query afresh). The projection holds one measured mean and is a guide, not a bound;
citable: no.
