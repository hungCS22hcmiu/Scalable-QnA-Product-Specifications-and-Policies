# Gate failure — item 3.6, run 1 (stop rule S1)

Plan step 19. Counts only: no file name, asin, qa_id or question text. Nothing was edited to make the
gate pass. The full report is `data/v1-draft/gate/run1/report.json` (gitignored).

## Result

**G1 failed: 21 pairs with cosine ≥ 0.85 and J ≤ 0.2 inside a split (validation 13, test 8); the gate needs ≥ 50.**
Nothing is frozen and no snapshot digest was printed. Steps 21 and 22 (run 2, freeze) are skipped.

| criterion | result | counts |
| :--- | :--- | :--- |
| G1 high-similarity / low-overlap pairs | **FAIL** | 21 within split (13 + 8), need ≥ 50 |
| G2 within-product traps, validation | pass | B-within 3, B-cross 10, unlabelled 0 |
| G2 within-product traps, test | pass | B-within 3, B-cross 5, unlabelled 0 |
| G3 Tier-1 collisions | pass | 0 groups, 0 benign duplicates |
| G4 doc-id kind prefix | pass | 164 of 164 |
| G5 condition-splitting | pass | 4 families split, 12 of 12 policy documents clean |
| W workload shape | pass | 1274 records |
| S split files | pass | |

S5 (G2 met only by same-cluster paraphrase pairs) was **not** raised, in either split. S4 was not raised:
`ungrounded` 0, `own_chunk_missing` 0.

## The run

| what | value |
| :--- | :--- |
| ingest | 164 documents, 539 chunks, 19 s |
| index check (tests 1 – 5) | pass |
| stage 2 (U2) | 86 s |
| query vectors against the 3.4 file (U1) | 0 of 1274 differ, largest difference 0 |
| `high_sim_pairs` (cosine ≥ 0.85) | 1342; `expected-pairs.md` says 1342 (A3 ii, total) |
| K, whole / validation / test | 1274 / 622 / 652 |
| capacity, whole / validation / test | 318 / 156 / 163 |
| memory readings | 53, all **1** = the normal level on macOS's scale. See "Memory" below |

## G1 in detail

Pairs with J ≤ 0.2: 21 inside a split, 18 across the splits (not gated), 39 in all, out of 1342 high-similarity pairs.

| J of the pair | pairs (all 1342) |
| :--- | ---: |
| 0.0 – 0.1 | 27 |
| 0.1 – 0.2 | 9 |
| 0.2 – 0.3 | 56 |
| 0.3 – 0.4 | 16 |
| 0.4 – 0.5 | 136 |
| 0.5 – 0.6 | 76 |
| 0.6 – 0.7 | 186 |
| 0.7 – 0.8 | 16 |
| 0.8 – 0.9 | 12 |
| 0.9 – 1.0 | 808 |

The gate counts J ≤ 0.2, so the 3 pairs at exactly J = 0.2 (inside the 0.2 – 0.3 row) are in the 39: 27 + 9 + 3.

Who made the 21 (same documents | different documents):

| split | pair_of | same_cluster | other |
| :--- | :--- | :--- | :--- |
| validation (13) | 0 \| 1 | 2 \| 0 | 0 \| 10 |
| test (8) | 0 \| 2 | 4 \| 0 | 0 \| 2 |

Unscoped, for comparison (not gated): validation G1 2, test G1 12.

## G2 in detail

G2 passes with B-within 3 in each split, but 3 is not 3 built traps. Who made them (same documents | different documents):

| split | pair_of | same_cluster | other |
| :--- | :--- | :--- | :--- |
| validation (3) | 0 \| 1 | 2 \| 0 | 0 \| 0 |
| test (3) | 0 \| 2 | 0 \| 0 | 0 \| 1 |

So validation has 1 built trap and 2 paraphrase pairs from the same documents; test has 2 built traps and 1 coincidence
between different documents. `label_pair` labels by `product_id` only, so a same-source paraphrase pair counts as
B-within. S5 fires only if *all* the B-within pairs are paraphrases; 2 of 3 does not trigger it. Read "G2 pass" with this
table beside it.

## Where the designed pairs sit

Cosine of a probe to its partner, from the 3.4 vectors file (counts of probes with cosine ≥ 0.85, out of n):

| probe kind | validation | test |
| :--- | :--- | :--- |
| name-swap | 0 of 5 | 0 of 7 |
| name-swap-same | 0 of 6 | 0 of 4 |
| policy-condition | 40 of 40 | 80 of 80 |
| policy-region | 6 of 6 | 12 of 12 |
| condition-department | 16 of 16 | — |
| spec-attribute | 10 of 52 | 13 of 47 |

The highest name-swap cosine is 0.804. The policy-condition pairs are all far above 0.85 (0.936 – 0.978), but their
scoped top-k overlap is mostly J in (0.2, 0.5] (`probe-checks.md`, U12 a): 0 of 40 validation and 2 of 80 test sit at
J ≤ 0.2. They are high-similarity pairs that share part of their evidence, so G1 does not count them.

## Memory

At the preflight the level read 2 with no model loaded; it read 1 later and stayed 1 for the whole run.

**Correction (2026-10-22, later).** This record first called the run yellow and its numbers indicative. That was wrong. On this Mac the sysctl returns 1 (normal), 2 (warn) or 4 (critical): `DISPATCH_MEMORYPRESSURE_*` in the SDK's `dispatch/source.h`, and a reading of 1 with 47 % of memory free (checked in the `g1-finding` trail). So all 53 readings were at the **normal level**; only the preflight reading of 2 (warn) was not. The repo's rule "0 = green" counted 1 as not green, and the author's S3 waiver (`approvals.md`) was given on that reading. **These numbers stand as a run at the normal level**, pending the author's confirmation of the encoding. The code and CLAUDE.md still say 0; correcting them is a small step of the task that re-runs 3.6 (`g1-finding/spec.md`, section "The memory scale"). Supporting evidence that memory did not change the figures: the stored vectors equal the 3.4 file exactly (0 of 1274 differ), and the gate's pair arithmetic equals the offline count (1342).

## What is left

`data/v1/` is assembled (164 files, gitignored). Redis holds `dev-v0` again (44 documents, 44 chunks; restored at 23:06,
step 24). A fix is the author's decision: it is a change of corpus or workload, which are frozen inputs of 3.1 and 3.4, or a
change of criterion G1, which is `data-card.md` §7.
