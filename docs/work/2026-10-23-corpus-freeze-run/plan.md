# Plan — corpus-freeze-run

Scope **L**. Draft 1, 2026-10-23, for `spec.md` draft 1. No gate run, ingest or edit is made until `/approve implementation`. Every run needs
memory level **1**. Commits are made when the author asks. Counts only in `evidence/`: no asin, qa_id, file name or question text.

## Memory level 1 is needed in steps 3 and 5 only (the ingest, the index check and the gate of each run, about 2 – 3 minutes each)

Nothing else loads a model or reads the level. The gate enforces it (it flags S3 on any reading but `1` and then cannot freeze); `freeze` re-checks
the readings saved in both reports. Steps 1, 2, 4, 6 – 10, 12 and 13 need no particular level. Step 11 (the `dev-v0` ingest) loads the embedding model
but is not a measured run.

## Block A — before the first run

- [x] **1. Preflight.** *Done 2026-10-23: level 1 (graph green), all checks pass; see `evidence/run-a.md`.* The author closes apps until `sysctl -n kern.memorystatus_vm_pressure_level` reads `1`; the reading is written down.
  `make redis-check`, `launchctl list | grep redis-stack`, Ollama up and at 0.33.2 (`curl -s localhost:11434/api/version`; not `make env-check`, which loads both models, about 2.1 GB), `make pqa-select-verify`,
  `make workload-verify`; `git status --short -- rag/src experiments/scripts Makefile` is empty (S6); the three files in
  `data/v1-draft/gate/first-run/` still hash to the values in `2026-10-22-g1-finding/evidence/first-run-pin.md`.
  *Check:* all pass; the level is recorded.
- [x] **2. Assemble again.** *Done: 164 present, 0 copied, 167 files hash to the pin.* `make corpus-assemble` (idempotent). *Check:* A1: 164 files present, none copied, and the snapshot digest of the
  167 files equals `a5708fefa62c…`.

## Block B — the runs and the freeze

- [x] **3. Run A.** *Done 2026-10-23 12:12: exit 3, recorded-failure block, 53 readings all 1.* `DATASET_VERSION=v1 make ingest`, `make corpus-index-check`, then
  `make gate-corpus ACCEPT_FAILED=G1 REPORT=data/v1-draft/gate/freeze-a/report.json RETRIEVAL_OUT=data/v1-draft/gate/freeze-a VECTORS=data/v1-draft/workload/vectors.json`.
  `make` ends with "Error 3": that is the expected recorded-failure exit. *Check:* A2.
- [x] **4. Compare run A with the first run, by hand (S1).** *Done: every number equal, exports byte-identical; `evidence/run-a.md`.* G1 21 = 13 + 8, 18 across, 1,342 pairs; the printed digest is the pin;
  `shasum -a 256` of the two retrieval exports equals the first run's; memory readings all `1`; S4 and S5 not raised.
  Write `evidence/run-a.md`. *Check:* every number equal. **Any difference: stop (S1), write it down, tell the author.**
- [x] **5. Run B, from a fresh ingest.** *Done: same result.* The same three commands, output to `freeze-b/`. *Check:* A2 again.
- [x] **6. Compare B with A.** *Done: A3 (i) – (vi) hold; `evidence/run-b.md`.* A3 (i) – (vi); the two runs agree on pass/fail, accepted set, digest, chunk digest, stored-vector digest and stack.
  Write `evidence/run-b.md`. A difference in pass/fail or the accepted set is S2 (`/investigate`).
- [x] **7. Freeze.** *Done 2026-10-23: `data/v1-freeze.json` written once; `corpus-verify` PASS; `corpus-index-check` PASS (with the record). No file name, asin, qa_id or path in it; `known_failures` lists G1.* `make corpus-freeze RUN1=data/v1-draft/gate/freeze-a/report.json RUN2=data/v1-draft/gate/freeze-b/report.json`, then
  `make corpus-verify` and `make corpus-index-check`. *Check:* A4, A5, A6: the record exists, holds `known_failures` and no file name, asin,
  qa_id or path; `corpus-verify` exits 0.

## Block C — documents, restore, close

- [x] **8. `data-card.md` §7.** *Done: nine markers filled, status paragraph, line-258 note, monotonicity correction, `dev-v0` row, 3.1 skip rules; 4 `grep` matches remain (purpose sentence + 3 not ours).* The ten markers filled from the gate output (digest, `K`, capacity, G1 – G5 results, pair breakdown, overlap
  distribution); a status paragraph for G1 ("recorded as failed, 21 pairs against a floor of 50, ADR-014; this is not a pass"); line 258
  corrected; the two corrections carried from the old plan (§7's monotonicity sentence; line 14, `dev-v0` is kept); 3.1's skip rules.
  *Check:* A7 (`grep -n "TODO(W8)" docs/data-card.md` leaves the three not ours); a grep of the changed docs for asins finds none; every
  integer is copied from the gate output.
- [x] **9. ADR-015** *Done: appended, plus its index row; ADR-014's index status updated.* in `docs/decisions.md` ("`v1` is frozen"): what it binds; that G1 is recorded as failed there (ADR-014); the pinned
  digest and `K`; Redis holds `dev-v0` afterwards and every `v1` run starts with `DATASET_VERSION=v1 make ingest` and `make corpus-index-check`;
  the Phase 4 restore gap; the unit check from `probe-checks.md`; the "Claude is on both sides" note carried from ADR-013;
  `Invalidates: none — no runs yet`. *Check:* A11.
- [x] **10. Other documents.** *Done: `architecture.md`, `experiments/README.md`, `docs/super-plan.md` (item 3.6 done, progress paragraph, blockers marked). The Phase 3 exit line was amended at the author's instruction to close the phase, to ADR-014's wording. `README.md` has no entry to change (its `0 = green` line is the author's).* `architecture.md` (the new files), `README.md` entry, `experiments/README.md` if it lists scripts,
  `docs/super-plan.md` item 3.6 progress and its "Done" cell — **not** the Phase 3 exit line, which is the author's.
- [x] **11. Restore `dev-v0`.** *Done: Redis holds `dev-v0` (44 docs, 44 chunks); `make verify` PASS, 731 experiments + 23 rag tests, Go ok, nothing skipped, no test changed.* `DATASET_VERSION=dev-v0 make ingest`, then `make verify`. *Check:* A9: green, no test changed.
- [x] **12. Phase 3 exit, by hand,** *Done: all three clauses of the amended line hold; `evidence/phase3-exit.md`.* against the line the author has set: the digest was printed, `K`, the capacity and the statistics are in
  `data-card.md`, the splits are frozen with the dataset. *Check:* each clause is a command or a file.
- [x] **13. Close.** *Done 2026-10-23: `/verify` PASS (above); `/ai-review`: the diff holds documents and one tracked data record, no code, so there is nothing to route to a reviewer; `/done` below.* `/verify`, `/ai-review` (a docs-only diff: say so), `/done`. The outcome goes in this file: the numbers, whether scope L
  was honest, and what is left for P1 and Phase 4.

## Outcome (2026-10-23)

**What shipped.** `v1` is frozen: `data/v1-freeze.json` (167 files, snapshot digest `a5708fefa62c…`, 539 chunks, `K` 622 / 652, capacity 156 / 163),
with **G1 recorded as failed** (21 of 50). Two fresh-ingest gate runs (exit 3, memory `1` throughout) agreed with each other and with the first run
on every count and digest, and their retrieval exports are byte-identical to the first run's. `data-card.md` §7 is filled, **ADR-015** is written,
item 3.6 and Phase 3 are marked done in `docs/super-plan.md`, the Phase 3 exit line is amended (ADR-014's wording), and Redis holds `dev-v0` again.
No code, test, corpus or workload file was touched in this task.

**Deferred, and where it goes.** A restore path for `data/v1/` (Phase 4). P1: `CACHE_CAPACITY` from the run file's `K`, the stale `K` comment at
`gateway/cmd/gateway/main.go:267-268`, `corpus-verify` at run start. Three `TODO(W8)` markers that belong to the paraphrase set and the update set.
The author's: ADR-014's "How C1 is read" paragraph and supervisor line; whether a `v2` follows (with the supervisor, before Phase 4); `CLAUDE.md:44`
and `README.md:227` (still `0 = green`); moving `.claude/state/phase` to 4 when the thesis review is done. A pre-registration checkpoint before the
first measured run (Phase 5 or 6) was proposed in chat and is not in the plan.

**Was scope L honest?** Yes for what it touched (a measured gate, a frozen document, the freeze record). One honest note: the ladder asks for a design and
an opus design review at L, and this task **inherited** them from the two earlier tasks instead of repeating them, because it built nothing. The author
was told in the spec and accepted it at `/approve experiment`.

**Suggested commit** (not run): `Item 3.6 done: freeze v1 with G1 recorded as failed (ADR-015); Phase 3 closed`, with `data/v1-freeze.json`,
`docs/data-card.md`, `docs/decisions.md`, `docs/architecture.md`, `experiments/README.md`, `docs/super-plan.md` and this task's folder. Keep
`.claude/settings.json` out. The 3.6 record corrections in `docs/work/2026-10-22-corpus-freeze/` are separate, uncommitted edits.

## Not in this plan

Any edit to code, tests, the corpus, the workload, a threshold, `gateway/`, `rag/` or `docs/contracts/`. The Phase 3 exit wording, `CLAUDE.md`,
`README.md:227`, `Final_Proposal.md`, the thesis text.
