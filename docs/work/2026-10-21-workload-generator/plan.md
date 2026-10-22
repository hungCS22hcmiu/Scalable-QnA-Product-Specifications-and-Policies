# Plan — workload-generator (item 3.4)

**Draft 2** · 2026-10-21 · follows `design.md` draft 2 and the proposed answers (`spec.md` 1 – 14).
Each step ends in something that can be checked, and each code step ends green (`make test`,
`ruff check experiments`). Test numbers (T1 …) are `design.md` §6. **Steps 1 – 6 come before any
sheet is read** (W8, W18). Nothing here starts before `/approve implementation`, and the
`interfaces.md` sentence (step 14) also waits for the contract approval.

## A. Before any model text

- [x] **1. Access and memory.** This session reads `data/v1-draft/` only through `make` targets,
      never directly; sheets go to the session scratchpad. Record the memory pressure
      (`sysctl kern.memorystatus_vm_pressure_level`). No model is loaded before step 4.
      ✅ *2026-10-21: level 2 (yellow), no model loaded; `evidence/memory.md`.*
- [x] **2. `.gitignore` first** (W10). Add `data/workload-v1*.json`. *Check:* `git check-ignore`
      matches the whole file and both split files, and does **not** match
      `data/workload-manifest.json`; `data/v1-draft/workload/` is already ignored (`.gitignore:31`).
      Commit on its own. ✅ *2026-10-21, `91f2b7b`; the check passed as written.*
- [x] **3. The gate** (`corpus_gate.py`, `Makefile`). `Query` gains `split`, `cluster_id`,
      `pair_of`; `check_workload_shape` as one more stage-1 `Criterion`; the split files found by
      name, re-derived, and hashed with the whole file; `K` and the capacity per split; stage 2
      scoped (`rag.retrieve.retrieve(q, product_id=...)`), G1 within split, G2 per split, unscoped
      and cross-split reported; `CORPUS_DIR`. Tests T2 (gate side), T14, T17, T18, T24.
      *Check:* `test_the_gate_runs_g5_in_stage_1_and_stops_on_it` passes **unchanged**.
  **Step 3 result (2026-10-21).** Done as written, with four small additions: `Query` also gains
  `probe_kind`, so the trap fraction leaves out `name-swap-same` (design §2.4); the shape check also
  enforces W5 (one Tier-1 form per record across the whole file) and a `qa_id` used once, since
  `pair_of` resolves by it; a split file is re-derived as that split's records in `popularity_rank`
  order, ranks exactly 1 .. n; the norms in the O(K²) cosine pass are computed once (the same value
  bit for bit, tested). The two new stage-1 checks print as `W` and `S` beside G3 – G5. 30 new
  tests (68 → 98); the immutable test passes unchanged. 11 hand mutants, all caught (the digest one only after
  `freeze_files` was split out and tested). `/verify`: gofmt, go vet, go build, go test, ruff,
  pytest (rag 15, experiments 422) and proto regeneration all **PASS**, none skipped (the stubs are
  gitignored, so "drift" means they regenerate and Go builds and tests against them);
  `git status --porcelain data/` empty.
- [x] **4. The pilot** (review U13). Memory check (must not be red; record the level). About 20
      synthetic close / far / name-swap pairs, written for the pilot and containing **no PQA text**,
      embedded with `nomic-embed-text` through the frozen path. `evidence/pilot.md`: each pair's
      cosine against 0.85. This is the **last point** where a constant in `design.md` §2.2 may move;
      any move is written down here with its reason, before step 5.
      ✅ *2026-10-21: 25 pairs, 38 texts; close paraphrases 0.966 – 0.994, far 0.817 – 0.959, name
      swaps 0.668 – 0.803 (all below), same-product traps 0.831 – 0.948, unrelated 0.697 – 0.746.
      **No constant moves** (reasons in `evidence/pilot.md`).*
- [x] **5. `rules.md`, the constants and the import checks.** `rules.md` in this trail holds R1 –
      R10 (`design.md` §4) with their sheet and row formats, the shape table (§2.3), the twin groups,
      the constants (§2.2), `SEED`, and the analysis rules A1 – A4 (§8). `build_workload.py`:
      `write_sheets` and `import_rows` with every mechanical check; `make workload-sheets`,
      `workload-import`. Tests T10, T15, T16, T20 – T23. **Commit here: everything that decides what
      the model layer may contain is in git before any sheet is read.**
  **Step 5 result (2026-10-21).** `rules.md` (R1 – R10 with row formats, the constants, the shapes,
  cells and twins, how the build reads the rows, A1 – A4) and `build_workload.py`'s first half: the
  task plan for the three rounds (`label`, `write`, `check`), the sheets (refused inside the
  repository), and the import with every mechanical check; `make workload-status`,
  `workload-sheets`, `workload-import`; `evidence/batches.md`. `sheets` and `import` refuse to run
  while `rules.md` is uncommitted or changed. **Ten details the design left open are fixed in
  `rules.md` §10** (among them: `R2_UNANSWERABLE_SAMPLE = 40` per department; digits compared less
  the short name's digits, found when a correct rewrite of a question about "Zenvo X2" was
  rejected; a real policy question is a cell's source wording, not its own query; the product
  choice per cell). 63 tests (synthetic products, the real policy documents), and a test that
  `rules.md` states every constant. 25 hand mutants, all caught (two only after their tests were
  rebuilt: R1 uniqueness, and the repository refusal, whose mutant had written fixture sheets into
  `data/sheets/`; removed, and the test now points the root at a temporary folder). `/verify`:
  gofmt, go vet, go build, go test, ruff, pytest (rag 15, experiments 485) and proto all **PASS**,
  none skipped; `git status --porcelain data/` empty.
- [x] **6. The offline builder.** `build`, `make_units`, `assign_split`, `assign_stratum`, `rank`,
      `simulate_lru`, `write_outputs`, `verify`, `embed_all` (injected embedder); `make
      workload-embed`, `workload-build`, `workload-verify`. Tests T1, T3 – T9, T11 – T13, T19, on
      fixtures. Commit. The whole build path is fixed before any model row exists.
  **Step 6 result (2026-10-21).** `build_workload.py`'s second half, as `design.md` §2.4 – §2.7
  and `rules.md` §8 say: the records from the model layer with the blind-label drop rules; units
  (product pairs; (shape group, department)); the split (the two minimal-pair unit pairs first,
  then the other policy units alternating across departments, then product units balanced per
  department); the stratum by precedence; the stratified rank in exact fractions; the
  nearest-foreign cosine; the cross-split leak cosines (U9, D against `term`); the seeded LRU
  simulation and the exact traffic shares per skew; outputs written through the ignored work folder
  with the manifest last; `verify` re-hashes and re-runs the gate's split-file check, W6 and W16;
  `embed` refuses in red memory. Three faults found in my own first draft, before any test: product
  units ordered by department instead of leaf; temporary output files under a name `.gitignore`
  does not cover (a crash could have left PQA text visible to git); the U9 statistic missing. 26
  new tests (89 in the file), among them T4 in two subprocesses with `PYTHONHASHSEED` 0 and 1. 21
  hand mutants, all caught (four only after a test was added: the axis check, the blind
  agreement, the temporary-file cleanup on a failed write, the condition check on a filled policy
  query). The real inputs: `workload-build` and `workload-verify` stop cleanly with no layer.
  `/verify`: gofmt, go vet, go build, go test, ruff, pytest (rag 15, experiments 511) and proto all
  **PASS**, none skipped; `git status --porcelain data/` empty.

## B. The model layer

- [x] **7. Pass 1 — labels.** `make workload-sheets OUT=<scratchpad>` in batches. Claude writes R1
      (names), R2 (every R2-answerable spec question and the R2-unanswerable sample), R7 (policy
      assignments) and R9 (natural-pair marks), following `rules.md` only. `make workload-import`
      after each batch; rejects are re-done, never edited by a script. Each batch's sha256, model id
      and time go to `evidence/batches.md` and are committed (impact F10). `RELABEL = 40` questions
      come back in a later batch.
  **Step 7 result (2026-10-21).** 19 label sheets, one re-done row and 5 relabel sheets, all
  imported; every batch line is in `evidence/batches.md`, committed in five commits. Pass 1
  accepted 1,898 rows: 1,340 labels, 152 names, 232 natural-pair marks, 174 policy assignments.
  **One reject:** an answerable label whose only evidence ("iOS 9") was 2 words, under
  `EVIDENCE_WORDS`' 3. No longer span holds the fact, so it was re-done as not answerable. This is
  a miss the rule causes, not a labelling error. **One error caught before import:** on sheet 9 an
  evidence span was verbatim but did not support the answer. The import cannot see this kind of
  error (the span is in the record); the blind relabel of step 9 and the author's read of step 10
  are what cover it. Conventions kept across the sheets, for the author to check in step 10: a
  record that claims worldwide use ("works worldwide", "U.S. and world", "Global 4G LTE") makes a
  country question answerable; a carrier the record does not name stays not answerable (which
  network a carrier uses is outside knowledge); a return question that says neither opened nor
  unopened is `ambiguous`; a phones warranty question takes its product's region when the record
  states it, and is `ambiguous` otherwise. The relabel sheets reuse the names `label-01` …
  `label-05`; `batches.md` tells them apart by sha256 and by "relabel" in the Accepted column.
- [x] **8. Report pass 1** (`evidence/labels.md`, counts only): the yield, by R2 tag; R2 against
      Claude (precision, NPV, Wilson intervals); the repeat agreement; the rejects; the policy
      assignments. **If the yield is below 200** (U1), stop and show the author. The constants do not
      move.
  **Step 8 result (2026-10-21).** The plan named no command for this report, so I added one:
  `make workload-labels` (`labels_report`, `batch_totals`, and a `labels` command that refuses
  until the label round is complete). 5 new tests (94 in the file); 3 hand mutants, all caught (the
  guard removed, the NPV numerator, the direction of a repeat change). **Yield 448** (427 of 1,180
  R2-answerable, 21 of the 160-question sample): above the floor of 200 and inside ADR-011's
  285 – 560, so the plan goes on and no constant moves. R2 precision 0.362 (Wilson 0.335 – 0.390),
  NPV 0.869 (0.808 – 0.913). **Repeat agreement 38 of 40** (0.835 – 0.986). Both changes went from
  not answerable to answerable, so the repeat was never stricter than pass 1. All 16
  both-answerable pairs quote overlapping evidence. 5 of the 40 repeats (from sheets 17 – 19) were
  labelled earlier in the same context window, so those 5 are less independent; all 5 agreed.
  Policy: 76 assigned, 33 `ambiguous`, 22 `not_covered`, 43 `not_policy`. Natural pairs: 36
  `same`, 6 `different`, 190 `unanswerable`. **Pass 2 gets fewer spec seeds than the design
  expected:** 214, not about 304, because 62 of the 152 products have fewer than 2 Claude-answerable
  labels outside the natural candidates; 52 unanswerable seeds. The design says these counts are
  expectations, not targets, so nothing is changed to reach 304. `/verify`: gofmt, go vet, go
  build, go test, ruff, pytest (rag 15, experiments 516) and proto all **PASS**, none skipped.
- [x] **9. Pass 2 — writing.** The script picks the seeds from the labels (deterministic) and writes
      the pass-2 sheets. Claude writes R3, R4, R5 (with answers and evidence), R6 labels, R7 built
      policy questions (from pool wording first), R8, and labels every written query on its own
      (R2, without its seed). Import and batch records as in step 7.
  **Step 9 result (2026-10-22).** Both rounds are complete; `make workload-status` shows every task
  done. **Write round:** 22 sheets, 1,097 rows imported (350 seed, 480 para, 124 lookalike, 69 D,
  74 cell). One reject: a paraphrase used "hard", a record word ("Hard Drive"), which R4 forbids.
  It was re-done as `write-10b` and the reject stays counted in `batches.md`. **Check round:** 18
  sheets, 1,028 rows, 0 rejects. Blind: 826 answerable, 128 not answerable (954). Swap: 23
  answerable (10 `same_answer`, 13 not), 51 not answerable (74); the build drops the 51. **The
  reject counts measure little.** Before each import, rows went through a read-only pre-check:
  `tools/precheck.py` (write round, `build_workload.check_row`) and `tools/precheck_check.py`
  (check round, `check_label`), both on the record text the sheet shows. The check-round pre-check
  tests only the shape and the evidence span; it never shows the reference label. **How many blind
  labels disagree is not counted here.** `construct` counts it, and `make workload-build` writes
  it into `evidence/build.md` (step 12); no extra read of the drafts was made for it.
  **Independence:** the check round ran in a new context window after a compaction, so no
  write-round or pass-1 sheet was in view, except that the swap sheets show the first product's
  answer by design (R6). It is still the same model with the same habits, so the blind check is
  not an independent labeller; step 10 is the outside check. **Conventions in the check round,
  for the author's read:**
  - The blind labels are **stricter than step 7 on country questions**. "Works worldwide", "any
    GSM network around the world" and "all worldwide GSM networks" still make a country
    answerable. A hedged claim ("most GSM SIM cards in U.S. and world", "Global 4G LTE",
    "US + Global") now does not. About 20 blind country queries (Galaxy J7 Pro, J4 Core, A50 and
    A51) are labelled not answerable for this reason, so the build will drop them as
    disagreements. They were left as labelled: changing them after reading the step-7 convention
    would no longer be blind.
  - A record that contradicts itself makes the question not answerable: 6th against 7th
    generation, polyester against nylon seat, 5000 against 3000 mAh, T-Mobile yes against no.
  - A complete "package included" list settles what is not in the box ("no mug"). A feature
    list that leaves something out does not settle it ("no USB port").
  - A network line that names only 2G or 3G settles "is it 4G?" as no.
- [ ] **10. The author's read** (review M6 d). A seeded sample of **30** rows across the row types,
      written by `make` to a gitignored sheet for the author: does each keep (paraphrase) or change
      (probe) the answer as its rule says, and does it read as a shopper's question? **Stop rule,
      fixed now:** if 3 or more of the 30 break their rule, stop; a rule change is recorded in
      `approvals.md` and needs the experiment phase approved again. Counts only into
      `evidence/author-read.md`.

## C. Embed, build, verify

- [ ] **11. Embed.** Memory check first (record the level); `make workload-embed`
      (`nomic-embed-text` through Ollama; no Qwen). The vectors file is hashed into the manifest.
- [ ] **12. Build twice and verify.** `make workload-build` twice: one manifest sha256. Then `make
      workload-verify` and `make gate-corpus STRUCTURAL=1 CORPUS_DIR=<temp: drafts + policies>`
      (W12). `evidence/build.md`: counts per stratum, `probe_kind`, split, department and axis; the
      minimal-pair twins per split; `K_validation`, `K_test`, `K_total`; the trap fraction by records
      and the exact traffic shares per skew; the LRU simulation per skew; the cosine distribution per
      stratum; the highest cross-split cosine between same-document queries (U9) and between D and
      `term` queries. A failed check stops the build; the seed is not re-drawn.

## D. Records

- [ ] **13.** `data-card.md` §2 (natural against built B-within, with the real count, U16), §3
      (rewrite policy, per-stratum counts; the "/ask carries no product context" line), §4
      (clusters, lookalikes, the model id and `rules.md`'s sha256), §6 (the "no splits" line), §7
      (the shape check, scoped stage 2, G1 / G2 per split, the digest over three files), Schemas (the
      QA pair); `experiments/k6/README.md:34`; `experiments/README.md:5`; `architecture.md` (the
      script, the files, the targets). Remove only the `TODO(W8)`s this item fills.
- [ ] **14.** `interfaces.md` §D: the one sentence defining `K` per run file, v0.15 — **only after
      the contract phase is approved**.
- [ ] **15. ADR-013 (data)** with the real counts: the rules and the model layer, the model id, the
      PQA-to-Anthropic flow, the units and the minimal-pair pairing, the stratified rank, `K` per run
      file, G1 / G2 per split and scoped, the labeller-is-not-the-judge rule, Claude on both sides as
      a threat with its controls, ADR-011's "separate stratum" read as "separate population".
      `Invalidates: none — no runs yet`, and what binds forward.
- [ ] **16.** `super-plan.md`: the 3.4 row and the Phase 3 progress paragraph; the carries to 3.6,
      5.1, 5.2, 6.1 / 6.3, 7.2 and P1 (`design.md` §11).
- [ ] **17.** `/verify`, then `/ai-review`, then `/done`.

**Not in this plan:** building `data/v1/`, ingesting, G1 / G2 on the real index, the freeze, `K` in
`data-card.md` §7 (3.6); any change to `ask.js`, `mu_hit.js` or `rag/`; reference answers; any Qwen
call.
