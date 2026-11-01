# Deliverables — Judge harness, and P1 first

Closed 2026-11-01 · super-plan item 5.1

## What shipped

- **P1.** `docs/contracts/metrics.md` (`counting-v1`, 20 entries, the five error layers, the three counting choices);
  the run manifest (`interfaces.md` §I, `make run-manifest`, `make run-manifest-check`); `docs/preregistration.md`
  (Entries 1–4, and the names reserved for item 6.1).
- **The frozen judge** (ADR-022): `gemma3:4b-it-q4_K_M`, digest `a2af6cc3…f5a`, `prompt-v1.txt`, `temperature` 0,
  seed 20261031, `num_ctx` 4096. The verdict key `vk1` (`interfaces.md` §H v0.28, golden key `d2f8597f…bb41`).
- **Gold-anchored references from a pinned writer** (ADR-023, `interfaces.md` v0.29): `qwen3.5:4b-q4_K_M` at
  `temperature` 0 answers each query's gold evidence; 622 references, `index.jsonl` sha256 `0e843899…974a` (Entry 4).
  The served generator is unchanged (2B, `temperature` 1). The 2B set stays as a baseline in `validation-qwen2b-t1/`.
- **The harness:** `judge.py` (`run`, `sanity`), `judge_references.py` (`gold-check`, `build`, `sheet`, `score`),
  `replay.py`; seven Makefile targets. One cost run and `evidence/cost.md`.

## Files changed

- **New:** `experiments/scripts/{judge,judge_references,run_manifest,replay}.py`; `experiments/judge/` (judge config,
  prompt, writer config); `experiments/tests/test_{judge,judge_references,run_manifest,replay}.py`;
  `docs/contracts/metrics.md`; `docs/preregistration.md`; the cost run's `manifest.yaml`.
- **Changed:** `Makefile`, `.gitignore`, `interfaces.md` (v0.28, v0.29), `decisions.md` (ADR-022, ADR-023),
  `architecture.md`, `experiments/README.md`. `rag/src/rag/config.py`'s `RETRIEVAL_VERSION` was committed in `883aea5`.
- **Gitignored, local only:** `experiments/references/`, the run's `raw/` and `judge/`, `evidence/private/`.

## How it was verified (main session, Phase 7, 2026-11-01)

1. `metrics.md`: the greps give `20` and `0`; every entry has the six parts (7.2).
2. Manifest: `test_run_manifest.py` 118 passed; `make run-manifest-check` exits 0 on the cost run (7.3).
3. Pre-registration: the judge file's hash is found; Entries 1–4 predate the first verdict, 5.3 at ~21:10 (7.4).
4. Verdict key: `-k key` 16 passed; the golden key is in §H (7.5).
5. ADR-022: heading and row found; the live digest equals `judge-v1.json` (7.6).
6. Gold audit: `make judge-gold-check SPLIT=validation` exit 0; 78 passed (7.7).
7. References: 622 rows, 622 distinct `(question, product_id)`; a second build is refused (7.8).
8. Sufficiency: v2 failed (`reference right` 25 / 5); after ADR-023, v3 passed, 28 / 2 and 27 / 3, exit 0 (10.11, 7.9).
9. Harness: `test_judge.py` 120 passed; a second `make judge` is refused, output unchanged (7.10).
10. Sanity: 12 of 12, 0 `UNPARSED`, the same verdicts in three runs (5.3, 7.11).
11. Cost: `evidence/cost.md` holds every field; `raw/` is ignored (7.12).
12. `make verify` exit 0 (Go ok, rag 83, experiments 1117 passed, nothing SKIPPED); no existing test changed (7.13).

## Numbers (all `v1` validation, all citable: no)

- **Reference error, the author's sheet** (30 pairs, seed 7): the 4B writer's references are wrong in 3 of 30
  (10 %, Wilson [3.5, 25.6] %), the 2B ones in 5 of 30 (17 %, [7.3, 33.6] %). 53 of 582 answerable 4B references
  decline (2B: 78). Pressure 1–2 while the references were written.
- **Cost run** `2026-11-01T21-17-56_cfg4_judgecost` (configuration 4, gate on, MIXED off, `mutation: off`, capacity
  156; pressure 1 in the replay, 1–2 in the judge): 622 records, 528 MISS, 94 Tier-2 hits, 0 Tier-1 hits. The judge:
  622 keys, median 1.48 s and p95 2.51 s per verdict, 1,047 s wall, 0 `UNPARSED`, 0 of 30 re-judged keys flip;
  memory about 4.3 GB (RSS; `footprint` 1.22 GB leaves out the mapped weights).
- **Layers** of the 163 `INCORRECT` records: retrieval 17, generation 121, inherited 9, reuse 16. MISS 132 of 528
  wrong; Tier-2 hits 31 of 94. A functional run: no rate here is used for any choice.

## Deferred and follow-ups

- **5.2:** both agreements, with Cohen's κ and the recall of `INCORRECT`, one rubric for both schemes. **5.3:** δ
  against the judge's error *and* the reference error measured above. **5.4:** the figure generators.
- Test-split references (about 65 min) before any test-split run. Judging under `mutation: on` (6.5) is refused.
- `make_reference`'s own default is still the 2B (`answer_in_process`); only `build()` defaults to the writer.
- **On the record:** the v3 marks are the author's, with feedback from an AI assistant; before marking, the author had
  seen the comparison's wrong rows for the 4B; row 19 decides the pass at the limit (`no` there would stop).
- `Final_Proposal.md` §5 C1 and §9.3 still define the reference as `LLM(retrieve(q), q)` (the author's file).
