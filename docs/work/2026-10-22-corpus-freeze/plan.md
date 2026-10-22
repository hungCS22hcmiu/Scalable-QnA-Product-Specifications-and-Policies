# Plan — corpus-freeze (item 3.6)

**Draft 1, 2026-10-22**, on `design.md` draft 3 and `spec.md` draft 3. Nothing here starts before
`/approve implementation`. Each step names how it is checked. Tests are written with the code, and **no
existing test is changed**.

Three blocks, in this order (design §7): **code** (Redis holds `dev-v0`, `make verify` stays green) →
**measurement** (Redis holds `v1`) → **restore and close**.

## Block 0 — fix the expected values before the code exists

- [x] **1. Pre-registered values, offline.** In `tools/`, re-derive from `data/v1-draft/workload/vectors.json`:
  the pair counts at cosine ≥ 0.85 (the review counted 1,342 in all; 663 validation, 554 test, 125 across),
  the 36 pairs within ±0.001 of 0.85. Write them to `evidence/expected-pairs.md`.
  *Check:* the numbers equal the review's, or the difference is explained before any run. These are the
  expected values for A3 (ii).
- [x] **2. Golden node dump, taken with the OLD `ingest.py`.** A tool builds the full node dump (id, text,
  metadata in order, excluded keys, start and end index, `ref_doc_id`) for `data/dev-v0/` (44 nodes) and for
  the 152 drafts + 12 policies read straight from `data/v1-draft/products/` and `data/policies-v1/`
  (539 nodes). Only the two digests go to `evidence/golden-nodes.md`.
  *Check:* the tool runs twice and gives the same digests. This step must come before step 4.

## Block A — code (Redis holds `dev-v0`)

- [x] **3. Version switch.** `config.py:19` reads `DATASET_VERSION` from the environment, default `dev-v0`.
  `demo-reset` passes `DATASET_VERSION=dev-v0`. `ingest` is not wired to Make's `VERSION`.
  *Check:* a test: unset gives `dev-v0`, `v1` in the environment gives `v1`. `make -n demo-reset` shows the pin.
- [x] **4. Refactor `ingest.py`.** Move the split loop to `records_to_nodes(records, dataset_version)`; `main`
  calls it. Keep `record_to_document`, `load_records`, `product_to_text`.
  *Check:* the step-2 tool, rerun, gives the **same two digests**; `make test` unchanged and green.
- [x] **5. `corpus_gate.py` — chunk digest and the index check (A).** `chunk_digest(corpus_dir)`; one function
  with tests 1 – 5 of design §2.4; stage 2 calls it before any embedding.
  *Check:* unit tests with a fake client, one per failure: a wrong version tag, a missing chunk, a changed
  text, a changed vector, a wrong model digest, `num_docs` or `hash_indexing_failures` off. Messages print
  counts only.
- [x] **6. `corpus_gate.py` — report additions (C).** `ungrounded`, `own_chunk_missing`, memory readings
  taken by the gate itself, `tree_clean` and `git_commit`, model tag and digest, `ollama_version`, retrieval
  config, package versions, stage-2 time, stored-vector digest, and the J ≤ 0.2 count beside the histogram.
  *Check:* tests on synthetic data; an existing report key keeps its name and meaning.
- [x] **7. `corpus_gate.py` — the pair breakdown and S5.** Pair type (same `cluster_id`, `pair_of`, other) ×
  `doc_ids` (same, different), per split, for G1 and G2; a flag when G2 in a split is met only by
  same-`cluster_id` pairs.
  *Check:* tests with synthetic pairs, including a G2 met only by paraphrases (the flag is raised) and one
  met by a built trap (not raised). G1 and G2 pass/fail values are unchanged by the breakdown.
- [x] **8. `corpus_gate.py` — the export (B).** `--retrieval-out DIR`: one file per split, ordered scoped and
  unscoped ids, set sizes, query-vector sha256.
  *Check:* a test on a fake retriever; the file path is under the gitignored `data/v1-draft/`.
- [x] **9. `freeze_corpus.py` — `assemble`.** *Check:* tests for each refusal: a differing file, a stray
  `*.json`, a name that is not its `doc_id`, a missing prefix, the record present, `verify_selection` failing;
  and for success: bytes equal, second run changes nothing.
- [x] **10. `freeze_corpus.py` — `check-index`, `freeze`, `verify`.** *Check:* tests for every `freeze`
  refusal in design §2.2 (failed report, digest mismatch, version not `v1`, run 2 not passed, `ungrounded`,
  dirty tree, memory above 0, S5, record exists); the record holds no file name, asin, `qa_id` or absolute
  path (a test that scans it); `verify` exits non-zero on one flipped byte, a changed model digest and a
  changed retrieval config, and warns (does not fail) on a package version alone.
- [x] **11. Makefile.** `corpus-assemble`, `corpus-index-check`, `corpus-freeze`, `corpus-verify`, with help
  lines and the memory-check note beside every target that runs Ollama.
  *Check:* `make help` lists them; `make -n` of each shows the right command.
- [x] **12. `tools/probe_checks.py`.** Scoped-set sizes, U12 (a, b), U11 (any and all), U10 (distribution),
  sibling rate, unit check. Counts only. Refuses U10 and the sibling rate on the test file.
  *Check:* a synthetic run; a test that the test file is refused; the per-probe flag file path is gitignored.
- [x] **13. `make verify` green on `dev-v0`.** Run `make lint`, `make test`, `make verify`.
  *Check:* all pass; the diff shows **no existing test edited** (`git diff -- '*test*'` shows only added
  files or added tests). On a failure: one quick fix, then `/rca`.
- [x] **14. Asin hygiene on the diff.** *Check:* a grep of every changed tracked file for the asin pattern
  and for `qa_id`s finds none.
- [ ] **15. Commit the code** (the author asks for it, or approves it). The gate must run on a clean tree
  for `rag/src`, `experiments/scripts` and `Makefile`.

**Block A result, 2026-10-22.** Steps 1 – 14 done; step 15 (commit) waits for the author. Details,
commands and counts: `evidence/block-a-log.md`. `/verify` (`make verify`): lint, Go build and tests,
23 `rag` tests and 672 `experiments` tests all pass; **no existing test was changed** (only four new
test files were added, plus `tools/test_probe_checks.py`, 50 tests, run by hand). Proto drift: SKIPPED,
the stubs are gitignored so there is no baseline.

> **Stop for the author:** the code block is done. The measurement block starts only after the author says
> go, because it ingests over `dev-v0` and takes the machine for several minutes.

## Block B — measurement (Redis holds `v1`)

Every command below that loads a model is preceded by `sysctl kern.memorystatus_vm_pressure_level` = `0`.
Every attempt is logged in `evidence/attempts.md` (time, command, memory readings, outcome), the discarded
ones too.

- [ ] **16. Preflight.** `make pqa-select-verify`, `make workload-verify`, `make redis-check`,
  `launchctl list | grep redis-stack`, Ollama up, `make env-check`'s version facts (Ollama 0.33.2),
  memory level 0 with the embedding model loaded.
  *Check:* all pass; the pressure reading is written down.
- [ ] **17. Assemble.** `make corpus-assemble`.
  *Check:* A1: 152 + 12 files, each copy's sha256 equals its source's, `ls data/v1 | wc -l` is 164.
- [ ] **18. Run 1.** `DATASET_VERSION=v1 make ingest`, then `make corpus-index-check`, then `make gate-corpus`
  with the report and export going to `data/v1-draft/gate/run1/`.
  *Check:* the index check passes; the gate prints its result; the time is recorded (U2).
  **If memory goes above 0 at any reading, discard and repeat (S3).**
- [ ] **19. Decision point.** Read the result.
  - Any criterion fails, or `ungrounded` / `own_chunk_missing` is above 0, or S5 is raised →
    **S1/S4/S5: run step 20, write `evidence/gate-failure.md` (counts only), skip steps 21 – 22, do step 26,
    and tell the author.** Do not edit anything to make it pass.
  - All pass and no flag → go on.
- [ ] **20. Read-only checks.** `tools/probe_checks.py` over the export (also on a failed run).
  *Check:* each output is a table of counts in `evidence/` (A8).
- [ ] **21. Run 2.** A fresh `DATASET_VERSION=v1 make ingest`, the index check, the gate (output to `run2/`).
  *Check:* A3 (i) – (v). A difference in pass/fail is an `/investigate` (S2); a difference in counts only is
  recorded and run 1 stays the figure.
- [ ] **22. Freeze.** `make corpus-freeze`, then `make corpus-verify` and `make corpus-index-check`.
  *Check:* A4 and A5: the record exists, holds no file name, and `K` 622 / 652 and capacity 156 / 163 equal
  the gate's output. Flip one byte of a copy in a scratch directory and see `verify` fail (also a test).

## Block C — restore and close

- [ ] **23. Documents.** `data-card.md`: the ten markers, the pair breakdown, the J ≤ 0.2 note, the two
  corrections (§7's monotonicity sentence; line 14), 3.1's skip rules. `decisions.md`: **ADR-014**
  ("`v1` is frozen": what it binds, `Invalidates: none — no runs yet`, Redis holds `dev-v0` afterwards,
  the Phase 4 restore gap, the unit check, the Claude-on-both-sides note carried from ADR-013). `architecture.md`
  (the tree at 106 – 107, 116 – 118, 229, 248 and the new files), `README.md:205`, `experiments/README.md`
  if it lists scripts, `super-plan.md` (item 3.6, the progress paragraph, the carries to P1 and Phase 4).
  *Check:* A7 `grep -n "TODO(W8)" docs/data-card.md` leaves the three not ours; a grep of the changed
  docs for asins finds none; the K and capacity integers are copied from the gate output.
- [ ] **24. Restore `dev-v0`.** `DATASET_VERSION=dev-v0 make ingest`, then `make verify`.
  *Check:* A9: green, with no test changed.
- [ ] **25. Phase 3 exit, by hand.** Run the three clauses: the digest printed; `data-card.md` has `K`,
  capacity and the statistics; the splits are frozen with the dataset. *Check:* each clause is a command or
  a file, not a judgement.
- [ ] **26. Close.** `/verify`, `/ai-review`, `/done`; record the outcome, and whether scope L was honest.
  On a stopped run (step 19) `/done` records the stop as the outcome, with the numbers.

## Not in this plan

Flipping the default version; `pyproject.toml`; `DATASET_EPOCH_STUB`; `CACHE_CAPACITY` wiring and the stale
`K` comment (P1); `assemble --restore` (Phase 4); the faster scoped retriever; `CLAUDE.md` and
`Final_Proposal.md` (the author's); any change to `reuse/`, the gateway, the corpus, the workload, or a threshold.
