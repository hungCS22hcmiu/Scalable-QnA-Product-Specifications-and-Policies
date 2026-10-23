# Run A — item 3.6, second part (plan steps 1 – 4)

Counts only; no file name, asin, qa_id or question text. Reports and exports are in `data/v1-draft/gate/freeze-a/` (gitignored).
Date 2026-10-23, commit `a09b48d`, tree clean for `rag/src`, `experiments/scripts` and `Makefile`.

## Preflight (step 1) and assemble (step 2)

Memory level 1 (graph green; `evidence/memory-scale.md`), 67 % free. Redis up (`noeviction`, 44 docs of `dev-v0` before the run), Ollama 0.33.2,
`pqa-select-verify` and `workload-verify` PASS, the three `first-run/` files hash to the values in `2026-10-22-g1-finding/evidence/first-run-pin.md`.
`make corpus-assemble`: 164 files already there, 0 copied, every copy equal to its source; the 167 files hash to the pin `a5708fefa62c…`.

## The run (step 3)

`DATASET_VERSION=v1 make ingest` (164 documents, 539 chunks), `make corpus-index-check` PASS, then `make gate-corpus ACCEPT_FAILED=G1`. The gate
printed `FREEZE WITH A RECORDED FAILURE (G1, ADR-014)` with the pinned digest and exited 3 (`make`: "Error 3"); the report was written.
Stage 2 took 81 s. **Memory: 53 readings, all `1`.** `ungrounded` 0, `own_chunk_missing` 0, S4 and S5 not raised, `flags` empty.
Query vectors against the 3.4 file: 0 of 1,274 differ, largest difference 0.

## Comparison with the first run, by hand (step 4, S1)

| What | Run A | First run | Equal |
| :--- | :--- | :--- | :---: |
| G1 pairs inside a split | 21 = 13 (validation) + 8 (test) | the same | yes |
| G1 pairs across the splits | 18 | 18 | yes |
| Pairs at cosine ≥ 0.85 | 1,342 | 1,342 | yes |
| G2 B-within / B-cross per split | validation 3 / 10, test 3 / 5 | the same | yes |
| Criteria and their pass or fail | G1 FAIL; G2 – G5, W, S PASS | the same | yes |
| Overlap mean / variance, strata, trap fractions, `s5`, pair breakdown, unscoped counts | as in the report | the same | yes (every key of `statistics`) |
| `retrieval-validation.json` sha256 | `1e2e17357c45…` | `1e2e17357c45…` | **yes, byte-identical** |
| `retrieval-test.json` sha256 | `7a90de70423c…` | `7a90de70423c…` | **yes, byte-identical** |
| Chunk digest, stored-vector digest, embedding model digest | equal | equal | yes |
| `K` / capacity: whole, validation, test | 1,274 / 318 · 622 / 156 · 652 / 163 | the same | yes |
| Snapshot digest | `a5708fefa62c…` | (none printed) | equals the pin |

**No stop rule fired.** The only differences from the first run are the commit (`a09b48d` against `a7c1178`, code reviewed in `g1-finding`) and the
clock. A retrieval export that is byte-identical to the first run's, taken at the same green level and from another ingest, is the strongest check
that nothing in the machine or the index moved.
