# Block A log — corpus-freeze (item 3.6), 2026-10-22

Plan steps 1 – 14. Counts and digests only: no asin, no qa_id, no question text.
Redis was not touched (it still holds `dev-v0`), and no Ollama model was loaded.

## Step results

| Step | What | Result |
| :-: | :--- | :--- |
| 1 | `tools/expected_pairs.py` | 1,342 pairs at cosine ≥ 0.85: 663 validation, 554 test, 125 across. 36 pairs within ±0.001 of 0.85. Nearest pair to the line is 1.8e-05 away; numpy and the gate's arithmetic differ by 1e-15. Same as the review. (`expected-pairs.md`) |
| 2 | `tools/golden_nodes.py --record`, old `ingest.py` | `dev-v0`: 44 nodes. `v1`: 539 nodes. Three runs gave the same digests. (`golden-nodes.md`) |
| 3 | `DATASET_VERSION` from the environment, default `dev-v0`; `demo-reset` pinned | 3 tests. `make -n demo-reset` shows the pin, also with `DATASET_VERSION=v1` exported. |
| 4 | `records_to_nodes` out of `ingest.main` | `golden_nodes.py --check`: both digests identical after the move. 5 new tests. |
| 5 | `chunk_digest`, `index_check` (tests 1 – 5) | One test per failure, 14 ways to be wrong. Messages carry counts, never ids. |
| 6 | report additions | `ungrounded`, `own_chunk_missing`, memory readings, git state, model digest, Ollama version, retrieval config, package versions, stage-2 time, vector digest, J ≤ 0.2 count. Every old report key kept. |
| 7 | pair breakdown and S5 | Pair type (built trap, paraphrase, other) × same or different documents, per split, for G1 and G2. |
| 8 | `--retrieval-out` export | One file per split. Refused where git does not ignore the path, and checked before the run starts. |
| 9, 10 | `freeze_corpus.py` | `assemble`, `check-index`, `freeze`, `verify`. 79 tests: every refusal, every failure, nothing written on a refusal. |
| 11 | Makefile | `corpus-assemble`, `corpus-index-check`, `corpus-freeze`, `corpus-verify`; `gate-corpus` takes `RETRIEVAL_OUT` and `VECTORS`. |
| 12 | `tools/probe_checks.py` | 50 tests. U10 and the sibling rate refuse the test split in code. |
| 13 | `make verify` | PASS (see the table in the chat reply). No existing test changed. |
| 14 | asin hygiene | No hit in the 25 changed or new files. |

## Findings while building

1. **Stale links in every multi-chunk node.** The splitter links each chunk to its neighbours by a random
   UUID. `ingest` renames the chunk afterwards and leaves those links, so PREVIOUS and NEXT hold random ids
   that change on every run (513 of the 539 `v1` nodes). They are written to Redis inside `_node_content`.
   It does no harm to retrieval. But nothing may hash `_node_content` or a whole hash. The index check hashes
   `chunk_id` and `text` only. The golden dump labels each UUID in order of first appearance.
2. **U11 holds** (design §8): on the live `dev-v0` index, the stored `text` is byte-equal to the node text,
   44 of 44.
3. **U4 resolved** (offline, read-only, on the real model layer and the real chunking): 873 evidence strings
   in the model layer, 777 of them for records in the workload. **All 777 are found in their document text**,
   and 94 of them cross a chunk boundary. Every spec probe has one (99 spec-attribute, 22 name-swap, 10
   natural). A policy cell and a D query have none.
4. **U12 (b), early look.** The flags need no retrieval. Of the spec-attribute probes, 58 of 99 have an
   evidence span in the same chunk as their partner's (30 of 52 in validation, 28 of 47 in test). For natural
   pairs it is 8 of 10 (4 of 4 validation, 4 of 6 test). These are the "same evidence" probes. The real table
   is written at step 20.
5. **Unit check, early look.** All 13 policy terms are read: 11 by a listed unit, 1 by the `$` symbol, 1 has
   no number. No term has a number and no listed unit. The unit list needs no change.

## Where this went beyond or beside the plan text

- `--vectors FILE` on the gate: compares the run's query vectors with 3.4's `vectors.json` and reports how
  many differ and the largest difference. Acceptance A3 (i) asks for both numbers and the vectors are not
  stored anywhere else.
- `freeze` also compares the two reports (S2): it refuses if the runs differ on pass or fail, on the stored
  vector digest, the model, the packages or the commit, and only *records* a difference in counts. The plan
  names "run 2's comparison", and this is what it checks.
- `tools/evidence_spans.py` (new): maps each evidence string to its `qa_id` with the same id stems as
  `build_workload.construct`. `probe_checks.py` needs it. It writes a gitignored file.
- The `probe_checks.py` tests live next to the tool and run by hand:
  `python3 -m pytest docs/work/2026-10-22-corpus-freeze/tools -q`. They are not in `make test`, because
  the tool is in the task trail.
- The gate's old warning `retrieved NOTHING: [qa_ids]` printed qa_ids. It now prints counts (S4). No test
  depended on it.
- `corpus_gate.py` was not ruff-formatted before and is still not (a format run would touch about 600 old
  lines). The new files are formatted.

## Not done (by design)

Commit (step 15, the author's call). Everything in Block B: no ingest of `v1`, no gate run, no freeze.
