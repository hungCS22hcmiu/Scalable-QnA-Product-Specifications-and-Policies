# Spec — corpus-freeze (item 3.6)

**Scope L.** Draft 3, 2026-10-22 (draft 1 + `impact.md` + `review.md`). Opened by `/task corpus-freeze L`.

## The change, in one sentence

Build `data/v1/`, ingest it, run the full corpus gate (G1 – G5) on the ingested index, and — only if
it passes — freeze: print the snapshot digest, record `K` and the capacity for each run file, and
fill every frozen corpus statistic in `data-card.md` §7.

## Phase and item

Phase 3, item 3.6 (`docs/super-plan.md`). It discharges C1, C3 and S1 and is the last open item of
Phase 3. The Phase 3 exit has three clauses, and this item closes all three:

1. G1 … G5 all pass and `make gate-corpus` prints the snapshot digest.
2. `K`, the derived capacity and every frozen corpus statistic are in `data-card.md`.
3. The validation and test splits are frozen with the dataset.

Item's own Done-when: *the digest prints, every `TODO(W8)` in `data-card.md` §7 is filled, and no
experiment runs against an unfrozen corpus.*

`docs/contracts/requirements.md` is still a skeleton, so no `FR` / `NFR` / `RR` id exists to cite.
The nearest thing is a research requirement: a result on an unfrozen corpus is void and nothing
says so (the failure mode in `.claude/README.md`).

## Where we start (checked 2026-10-22, and again by `impact.md`)

- `data/v1/` holds only `.gitkeep`. It does not exist as a corpus yet.
- The parts exist elsewhere: 152 product records in `data/v1-draft/products/` (gitignored; digest
  `d373c4b0…a468` matches `data/pqa-selection.json`) and 12 policy documents in the tracked
  `data/policies-v1/`.
- The workload is final from 3.4: three gitignored files (1,274 / 622 / 652 queries) and the
  tracked `data/workload-manifest.json`.
- The structural gate (G3, G4, G5, `W`, `S`) passed on the draft build over 164 documents. **G1 and
  G2 have never run on an ingested `v1`.** They may fail.
- `rag.ingest` reads `data/<config.DATASET_VERSION>/`, and `DATASET_VERSION` is the constant
  `"dev-v0"` in `rag/src/rag/config.py`. Nothing else reads it: retrieval, the server and the
  gateway serve whatever Redis holds.
- Redis holds the `dev-v0` index (44 chunks, tagged `dataset_version = dev-v0`). `rag.ingest` drops
  it and its `corpus::*` hashes before it writes. The cache keys are not touched and are empty.
- **The gate hashes files but measures whatever is in Redis, and nothing checks that they are the
  same corpus** (`impact.md`, Verdict). This is the main hole this task must close.
- 13 `TODO(W8)` markers are open in `data-card.md`. Ten are this item's (rows 23 – 25 and 27 of the
  artifact table, and the six in §7). Three are not: the definition line at the top, the update set's
  table row and its §5 line (Phase 4).

## What this item does

1. **Assemble `data/v1/`** from the two sources, by copying bytes. Run `make pqa-select-verify` and
   `make workload-verify` first.
2. **Ingest `v1`** into Redis, with a way to name the version (open question 1).
3. **Run the full gate** twice, each run starting from a fresh ingest, under green memory pressure.
   Stage 2 first checks that the index is the corpus (new, additive, and also a command of its own),
   then embeds 1,274 queries and retrieves each one scoped and unscoped. The gate also reports G1 and
   G2 broken down by pair type, so a pass on paraphrase pairs can be seen.
4. **Freeze** if it passes: the digest over the corpus and the three workload files; a chunk digest;
   the retrieval stack (model digest, Ollama version, retrieval config, package versions, the commit);
   the freeze record; a verify command.
5. **Fill `data-card.md`** — the ten markers, 3.1's skip rules, a correction to §7's sentence "at equal
   `top_k` … orders pairs identically" (scoped sets differ in size), and `data-card.md:14` (which says
   `dev-v0` is discarded after the freeze; four live checks and the demo still need it).
6. **Take the measurements earlier items carried here** and write them as counts. They are recorded,
   not acted on. They run on a failed gate too, because they are how a failure is read.
7. **Write ADR-014** ("`v1` is frozen"), and restore the `dev-v0` index so `make verify` passes.
   ADR-014 says Redis holds `dev-v0` after this item, so every `v1` run and every reference generation
   must re-ingest `v1` and pass `make corpus-index-check` first (the wiring is P1's).

## Carried into this item (ADR-011, ADR-012, ADR-013)

- `K` and `round(0.25 × K)` for each run file: validation 622 → 156 and test 652 → 163. The whole
  file (1,274 → 318) is a gate figure. Python's `round` is half-to-even: record the integers the gate
  prints, and never recompute them elsewhere.
- G1 and G2 per split on the ingested `v1`, scoped, with unscoped beside, and **broken down** by pair type
  (same `cluster_id`, `pair_of` partners, other) and by `doc_ids` (same, different). The size distribution of
  the scoped sets, beside G1.
- Per-stratum and per-`probe_kind` counts, and the trap fraction, for each split.
- For each probe, from the export: the scoped-retrieval Jaccard with its partner (U12 a), whether the two
  evidence spans share a chunk (U12 b; the flags are frozen by hash), and whether the seed's evidence span
  is in the scoped top-k (U11).
- **Validation only:** `policy_frac` of the policy queries under each candidate lane band (U10), and how
  often one twin's top-k holds a chunk of the other twin's document (the sibling rate, ADR-012). A
  table of these on the test split that a later task reads to pick the band would be tuning on test.
- `make policy-check` run on `data/policies-v1/`; the numeric unit list checked against v1's terms
  (days, months, years, `$`).
- 3.1's skip rules ("first parsed record wins", surrogate replacement) written into `data-card.md`.

## Acceptance — checks that can be run

| # | Check | Pass when |
| :-: | :--- | :--- |
| A1 | `make corpus-assemble`, then `ls data/v1` | 152 `product-*` and 12 `policy-*` files; each copy's sha256 equals its source's; the drafts pass `verify_selection` |
| A2 | `make gate-corpus` (full) | `PASS` for the index check, G1 – G5, `W` and `S`, then a `FREEZE` block with a snapshot digest over 167 files; `ungrounded` and `own_chunk_missing` are 0; every memory reading the gate took is 0 |
| A3 | the second run, from a fresh ingest | (i) the query vectors equal 3.4's `vectors.json` exactly (report how many differ and the largest difference); (ii) the similar-pair counts equal the offline ones, re-derived in plan step 1 (the review counted 1,342 at ≥ 0.85; 663 and 554 inside a split; 125 across); (iii) the ordered scoped and unscoped id lists equal run 1's, query by query; (iv) the stored-vector digest equals run 1's; (v) G1 and G2 counts equal. (The file digest repeating proves nothing: it hashes files only) |
| A4 | the freeze record, `make corpus-verify`, `make corpus-index-check` | the record holds the digest, version, `K`, capacity per file, chunk digest, stored-vector digest, the retrieval stack (model tag and digest, Ollama version, retrieval config, package versions, `git_commit`), the manifest and probe-flag hashes, the pair breakdown and the statistics, and **no file name, asin, `qa_id` or absolute path**. `verify` exits 0 on the frozen files and non-zero when one byte of one file, the model digest or the retrieval config changes (tests). `check-index` exits non-zero on an index that holds `dev-v0` (a test) |
| A5 | `K` 622 / 652; capacity 156 / 163 | the same integers in the gate output, the record and `data-card.md` |
| A6 | chunk digest | recorded; the offline digest equals the chunk ids and texts read from Redis (the index check); the `ingest.py` refactor leaves the golden node-dump digests of `dev-v0` and `v1` unchanged |
| A7 | `grep -n "TODO(W8)" docs/data-card.md` | only the three that are not this item's remain |
| A8 | the evidence files | U10, U11, U12 (a and b) and the sibling rate are each a table of counts, plus the pair breakdown and the set sizes. U10 and the sibling rate are on validation only, and the script refuses the test file. No `qa_id`, asin or question text; every attempt, the discarded ones too, is logged |
| A9 | order of the end: freeze, then `DATASET_VERSION=dev-v0 make ingest`, then `make verify` | `make verify` passes; no existing test was changed |
| A10 | memory | the pressure level was `0` before and after each Ollama command; the gate reads it itself and writes the readings to its report. A run under yellow is discarded, logged and repeated |
| A11 | `docs/decisions.md` | ADR-014 exists, says what `v1 frozen` binds, and says `Invalidates: none — no runs yet` |

## Stop rules — fixed now, before any gate run on `v1`

- **S1. A criterion fails.** If G1, G2, G3, G4, G5, `W` or `S` fails on the ingested index, stop.
  Write the counts into `evidence/` and run the read-only checks (they are how the failure is read).
  Skip `freeze`. **Do not edit the corpus, the workload, the rules, the thresholds (0.85, 0.2, 50),
  the chunking or the retrieval config inside this task** to make it pass. The next steps that exist
  are these, chosen by the author after the numbers are shown, and no other: (1) accept the failure as
  the result and report it; (2) reopen item 3.3 or 3.4 under its own approvals (for example, longer
  policy documents, or a different twin design); (3) change the gate statistic, which is **its own ADR
  with its own pre-registration, never decided in this task**.
- **S2. Two runs disagree.** "Run 1" is the first run with a passed index check and every memory
  reading green. If the two runs differ on pass or fail, stop: that is an `/investigate`, never a best
  of three. If they differ only in counts, record both, and the frozen figure is run 1's. Every
  attempt, the discarded ones too, is logged in `evidence/`.
- **S3. Yellow or red memory pressure** at any reading: discard the run, log it and repeat it.
- **S4. A query retrieves nothing, or lacks a chunk of its own product** (`ungrounded` or
  `own_chunk_missing` above 0): stop. The index check should have caught a wrong index first; if it
  did not, the check is wrong and that is a finding.
- **S5. A pass by paraphrase pairs.** If G2 in a split is met only by pairs of the same `cluster_id`,
  it is read as "passed by definition; no built trap". Stop before `freeze` and show the breakdown to
  the author.
- The index check **failing** is not S1. It is a precondition: re-ingest and run again.

## Out of scope

- Any edit to the corpus, workload, rules or thresholds (S1). Any change under `gateway/internal/reuse/`
  or to the gateway's constants (the lane band, the unit list): measured and reported here, changed
  only by a task of their own.
- Flipping the default of `DATASET_VERSION` to `v1`, a pin of `llama-index-core` in `pyproject.toml`
  (needs the author's sign-off), any change to `DATASET_EPOCH_STUB` (Phase 4), and the `retrieve_all`
  docstring (`corpus_gate.py:795`).
- Run wiring for P1: the run manifest, `CACHE_CAPACITY` from the run file's `K`, the stale `K`
  comment at `gateway/cmd/gateway/main.go:267-268`, and a call to `corpus-verify` at run start.
- The update set (Phase 4), the judge (Phase 5), the faster scoped retriever (its own `rag/` task; after
  the freeze it must return the same ids in the same order), and a restore path for `data/v1/` (it has
  no git; a `--restore` belongs to Phase 4 and ADR-014 names the gap).
- `CLAUDE.md` and `Final_Proposal.md` (the author's to edit). The `K` sentence in `CLAUDE.md` is
  still the single-`K` meaning.

## Open questions — each with a proposed answer

1. **How does `rag.ingest` get the version?** Proposed: (a) `DATASET_VERSION` read from the
   environment, default `dev-v0`, with three guards: the index check; `demo-reset` passes
   `DATASET_VERSION=dev-v0` explicitly (an exported shell variable would otherwise leak into it); and
   `ingest` is **not** wired to Make's `VERSION`, which is `v1` everywhere and would flip the default by
   accident. The other option (b), flipping the default, makes seam-check, support-check and `make verify`
   fail until `dev-v0` is re-ingested by hand, and the demo silently run on `v1`.
2. **Where is the freeze written down?** Proposed: a tracked `data/v1-freeze.json` with digests, counts
   and statistics only. **No file names:** 152 of them hold an asin, and no asin goes in a tracked file.
   The per-file list and the gate reports stay in the gitignored `data/v1-draft/`.
3. **Failure policy.** Proposed: stop rule S1 as written.
4. **Carried measurements.** Proposed: recorded only, U10 and the sibling rate on validation only. If one
   shows a problem, it becomes a new task.
5. **Numeric unit list.** Proposed: a read-only check of v1's policy terms against the list, recorded
   in ADR-014. **No hash of the Go file** in the record (any comment edit would fail `corpus-verify`
   forever); `TestNumericUnitListPinned` already pins the list in `make verify`. A missing unit is a
   finding, not an edit.
6. **Chunk digest.** Proposed: one shared split function in `rag/ingest.py` (a behaviour-preserving
   refactor; a full node-dump digest of `dev-v0` and of the 164 `v1` inputs, taken with the old code,
   must be identical after), used by `ingest` and by the digest; the digest is then compared with the
   chunk ids and texts in Redis, which is stronger than a count.
7. **Does the record cover the model layer?** Proposed: the record stores the sha256 of
   `data/workload-manifest.json`, which already hashes the model layer and the rules. The gate's digest
   stays as it is.
8. **Does run 2 re-ingest?** Proposed: yes. Run 2 is `make ingest`, then the gate. It tests the
   document side of the embeddings as well as the query side.
9. **The `llama-index-core` pin.** Proposed: record the installed version in the freeze record and have
   `corpus-verify` fail when it differs. No change to `pyproject.toml`.
10. **S1's list and S5.** Proposed as written in the stop rules: the allowed next steps after a fail are
    fixed now, and a pass by paraphrase pairs stops for the author. These are the two new
    pre-registered rules the review added; they are part of what the experiment approval covers.
11. **Restore path.** Proposed: dropped here and carried to Phase 4 (the smaller choice). Say if you want
    `assemble --restore` built in this item.
