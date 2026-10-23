# Impact — g1-pair-supply

**Analyst:** the `impact-analyst` subagent, 2026-10-22, on `spec.md` draft 1. It changed no file but this one. Read
only: Redis `--scan` / `DBSIZE`, and three scratch scripts that import `build_workload` and read the gitignored
workload files, printing counts only. No Ollama call, ingest or build.

## Verdict

1. **No run is invalidated and no study-wide frozen value moves. But every lever silently re-draws the
   validation / test split of records that already exist.** `assign_split` step 3 gives each product unit to the
   split with fewer queries so far in its department (`build_workload.py:1738-1747`). On today's files (recomputed
   split = recorded split, 118 of 118 units): one extra record in one product unit moves another unit in **27 of
   74** cases; one more lookalike for each of the 99 products that has one moves **48 of 74** product units and
   **579 of 1,274** records. The 3.4 design says "never re-drawn" (§2.5).
2. **L1 adds about zero G1 pairs on validation evidence:** 0 of 52 validation lookalikes have J ≤ 0.2 with their
   seed; 38 have J = 1 (3.6 `probe-checks.md`, U12 a).
3. **L2 means new units.** Its pairs have J = 0 by scoping (22 of 22 swaps), so its yield is the swaps at
   cosine ≥ 0.85. But a swap must sit in its target's unit (R6; T12, `test_build_workload.py:1046`).
4. **L3 meets ADR-012's rules.** W5 (minimal pairs, the basis of RQ2a) rules out "differentiate". W8's only
   exception is "a recorded §7 fix … that cites the gate output", and the only output is the yellow run 3.6 bars
   from citation.

## 1. Files touched

| Lever | Code | Data | Records |
| :--- | :--- | :--- | :--- |
| L1 | `build_workload.py:70` (`SPEC_LOOKALIKES_PER_PRODUCT`); for > 1 per seed also `:806-808`, `:1618-1626`, `:2377-2381`, 3.6 `tools/evidence_spans.py:51-53`; 3.4 `rules.md` §2, committed first (`:2513-2525`) | model layer, vectors, 3 workload files (gitignored); `data/workload-manifest.json` (tracked) | new ADR; the table below |
| L2 | `make_units` `:723-738`; a filter at `:1628` (`construct` builds **every** `swap` row in the layer, not only open tasks); `rules.md` R6, §6 "Units" | same | same, plus ADR-013's unit sentence |
| L3 | none while each document stays ≤ 800 words (`check_policies.py:50`); `freeze_corpus.py:39` if one is added | `data/policies-v1/*.json` (12, **tracked**), then all of the above (`workload-manifest.json:8` hashes them) | ADR-012; 2026-10-20 trail W1 – W9 |
| all | no Makefile target changes; no import added; `rag/`, `gateway/`, `contracts/` untouched: layering holds | | |
| all | **`build_workload.py:56-59, :2162, :2295`** and 3.4 `tools/partner_cosine.py:17` write into the **closed 3.4 trail**: build, import, labels and author-score overwrite or append its `evidence/` | | |

| Value | Written at |
| :--- | :--- |
| `K` 622 / 652, capacity 156 / 163, 1,274 / 318 | `workload-manifest.json:26-27, :76-78, :126-128`; `decisions.md:55, :1192, :1195, :1206-1208, :1227`; `data-card.md:151`; `super-plan.md:366, :427`; `architecture.md:246`; 3.6 `spec.md:33, :71-72, :96`, `plan.md:106`, `approvals.md:19`. Fixtures only, no change: `test_freeze_corpus.py:267-278, :363-365, :382-385` |
| strata, 94 unanswerable, twins 136 (56 / 80) | `decisions.md:1225, :1243-1252`; `data-card.md:148, :151`; `super-plan.md:427`; manifest `counts` |
| trap fraction 0.2229, reachable 182 / 284 | `workload-manifest.json:73`; `decisions.md:1244, :1275-1282`; `data-card.md:151`; 3.4 `evidence/partner-cosine.md` |
| 546 clusters, 99 lookalikes (124 / 25 / 17), 555 paraphrases | `data-card.md:156`; `decisions.md:1246-1248` |
| manifest `7ee717a8…`, rules `f4035be7…`, units `923a866d…`, assignment `a376c40f…` | `decisions.md:1197, :1202`; `data-card.md:156`; `super-plan.md:427`; `workload-manifest.json:9, :21-22` |
| cross-split 74 / 8 pairs | `decisions.md:1290-1292`; `data-card.md:298` |
| 1,342 / 663 / 554 / 125 | 3.6 `spec.md:94` (A3 ii), `plan.md:13`, `evidence/expected-pairs.md` |
| `interfaces.md` v0.15 | `:80-92, :375, :706`: `K` per split file, **no absolute value**: unchanged |
| `data-card.md` v0.7 | `:3`; L3 only `:77, :116, :121, :334`, `decisions.md:1121-1122, :1179`, `super-plan.md:376, :426` |

## 2. Frozen values and what is invalidated

| Question | Answer |
| :--- | :--- |
| Frozen value touched? | **No.** `num_ctx`, the slot, embedding model, `DIM`, `top_k` 5, chunking 256 / 40, FLAT, `noeviction`, ratio 0.25, δ, gate constants (`corpus_gate.py:84-86`) all untouched. `v1` is not frozen, so ADR-013's new-`dataset_version` rule (`decisions.md:1307-1309`, "after 3.6") does not fire; `K` was "not frozen here" (`data-card.md:151`) |
| **Runs invalidated** | **None — no runs yet.** `experiments/results/` holds only `.gitkeep`; Redis holds 44 `corpus:` keys (`dev-v0`) and no `t1:` / `t2:` / `lru:` / `dep:` key (checked today) |
| Artefacts replaced | the 3 workload files and manifest, vectors, the 3.4 assignment (L1, L2) and unit list (L2), ADR-013's statistics, `data-card.md` v0.7 counts, 3.6 expected pairs and probe flags `0e6745e3…`; 3.6's G1 = 21 becomes history. L3 adds the policy digest, ADR-012's author read, golden digest `b2959feb…` |
| ADR | a **new** data ADR (`decisions.md:13-15`: append, never rewrite). `rules.md` §2: "a count is never pushed toward a number by changing one of these after labels exist" — L1 is exactly that, so the ADR must say it was decided after G1 was seen (S1 option 2) |

## 3. What must be re-done downstream

| Artefact | L1 | L2 | L3 |
| :--- | :--- | :--- | :--- |
| vectors (`make workload-embed`) | all re-embedded (`:2100-2107`) | same | only if a wording changes |
| model layer (append-only) | + `lookalike`, + `blind` | + `swap`; the 74 old ones still built unless filtered | cells / D if R10 fails; **R10 runs at import only** (`:1082, :1103`): a new policy text is never re-checked against old wordings (silent) |
| blind label check | every new lookalike | none (R6 labels against the partner) | none |
| 30-row read | re-sampled: first 5 per type by key hash (`:2430-2441`), `--force` overwrites | same (`swap`) | `cell`, `d` if rewritten |
| probe flags, evidence spans | regenerate; `evidence_spans.py:51-53` knows one lookalike per seed | regenerate | regenerate |
| 3.6 `expected_pairs.py`, A3 (ii) | new numbers | same | same |
| `golden_nodes.py:29` (`v1`: 539) | no | no | new digest; count if chunks change |
| split | **re-drawn** (Verdict 1); no cluster crosses (a unit is a union of clusters) | re-drawn; up to 940 records get a new `split_unit` | policy units fixed (steps 1 – 2 read no counts) |
| rank | +1 B-within record moves 369 of 622 validation ranks, 383 of 652 test (`:1770-1788`) | same | — |
| **L1 defect** | at `SPEC_LOOKALIKES_PER_PRODUCT = 2`, `first_seed` holds the *second* seed (`:1618-1619`), so every swap fails `:1630-1632`: B-cross 22 → 0, no stop. Supply: 90 products have a second seed | | |

The build is deterministic, but **not append-only**: rank, split and `nearest_foreign_cos` of old records move.
"Only add, never rewrite" needs `assign_split` and `rank` to keep the 3.4 values for old records, a rule change.

## 4. Scope, dependency, contract, measurement

| Question | Answer |
| :--- | :--- |
| Dropped scope (`Final_Proposal.md:599`) | none. It deepens §9.4 limitation 1 ("the corpus is deliberately selected to contain the phenomenon"); the ADR says so |
| New dependency | none: Ollama `nomic-embed-text`; Claude in session (PQA text to Anthropic again, ADR-013) |
| Contract | none: §D has no value, §H's strata are unchanged; a new `probe_kind` is a `data-card.md:227-228` change. **Contract phase not required** |
| Measurement | strata, `K`, split, trap fraction, B-cross, a G1 reading rule (A2), a run budget. **Experiment phase required** |

## 5. ADR-014

| Cites ADR-014 as the freeze ADR | Lines |
| :--- | :--- |
| 3.6 `approvals.md` | `:5, :7, :8` (`:76` already voids them) |
| 3.6 `design.md` / `impact.md` | `:24, :131, :149, :195` / `:36, :104, :245` |
| 3.6 `spec.md` / `plan.md` | `:65-66, :102` (A11), `:139, :158` / `:112, :162, :164` |
| code, tests, Makefile | none (`review.md:86`); `decisions.md` ends at ADR-013 |

If this task takes ADR-014, 3.6's A11 passes on the wrong entry: 3.6 renumbers A11 and `plan.md:112, :162` to ADR-015
and records it. Its A3 (ii) and A5 numbers change, so its experiment approval must be given again.

## 6. Hidden coupling

| Coupling | Consequence |
| :--- | :--- |
| 50 is on 13 + 8 | sizing the change to reach 50 reads the 8 test pairs; size it from validation, by a rule fixed before run 1 |
| the split is drawn after the items | "validation only" (A6) has no fixed set until old assignments are pinned |
| U10, sibling rate (3.6 `design.md:129-130`) | policy units: L1 and L2 do not move them; L3 changes their inputs |
| swap text is made by script (`:752-758`) | its cosine is known before any label; "keep partners ≥ 0.85" passes G1 by construction |
| L2's J = 0 comes from scoping by `product_id` | these are the pairs a `product_id` key solves (`data-card.md:135`); G2 still guards B-within |
| A2 counts same `cluster_id` | swaps are clusters of one; twin sides are different clusters with 20 × 20 pairs in one unit, so A2 cannot see a pass by one template |
| 0.85, 0.2, 50 (`corpus_gate.py:84-86`); twin floor 30 | unchanged; L1 and L2 leave the twins as they are |

## Smallest change

Cut L1: no validation yield, the most labelling. Defer L3 until a green gate run exists to cite, and then only
"lengthen, keep W5". L2 is the one lever with a mechanism: accept one re-draw of the split, by a name rule fixed
before any cosine is computed.

## Required phases

> **Required phases:** impact · experiment · implementation (contract: not required). Scope L: design and the opus
> design review too.

## Unknowns the design must settle

1. Pin the 3.4 split and ranks for old records, or accept a re-drawn split and fix which records are validation
   before any choice.
2. L2's partner rule: names only, or screened by cosine (then pre-registered and reported as selection on the gate).
3. The 74 old swap rows: filter `construct`, or remove rows from an append-only layer.
4. Evidence paths: the 3.4 trail, or new ones.
5. A2's threshold and template pairs; the run budget (spec question 3).
6. **The memory scale.** Every reading in the 3.4 and 3.6 logs is 1 or 2, never 0; it read 1 today.
   `build_workload.py:2551` treats 4 as critical, which matches macOS's 1 / 2 / 4 (normal / warn / critical), not
   CLAUDE.md's 0 / 1 / 2. If 1 is normal, A1's "every reading 0" can never pass. Check this before the first run.
7. Whether 21 holds at green: the first green run is the baseline.
