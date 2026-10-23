# Run B — from a fresh ingest (plan steps 5 – 6)

Counts only. Reports and exports are in `data/v1-draft/gate/freeze-b/` (gitignored). Same day, same commit, same procedure as run A.

`DATASET_VERSION=v1 make ingest` again (164 documents, 539 chunks; "Index already exists, overwriting"), `make corpus-index-check` PASS, then the same
`make gate-corpus ACCEPT_FAILED=G1`. Recorded-failure block with the pinned digest, exit 3, report written. Stage 2 took 81.2 s (A: 81.4 s; first
run: 86.0 s). **Memory: 53 readings, all `1`.** `ungrounded` 0, `own_chunk_missing` 0, `flags` empty, S5 not raised, query vectors 0 of 1,274 differ.

## A3, checked

| | Result |
| :--- | :--- |
| (i) query vectors equal 3.4's `vectors.json` | 0 of 1,274 differ, largest difference 0 (both runs) |
| (ii) similar-pair counts | 1,342 at ≥ 0.85, as the first run and the offline count |
| (iii) the ordered scoped and unscoped id lists equal run 1's, query by query | the two retrieval exports have the same sha256 in A, B and the first run |
| (iv) the stored-vector digest | equal in A, B and the first run |
| (v) G1 and G2 counts | equal (21 = 13 + 8; B-within 3 and 3) |
| (vi) the counts and export hashes of the first run | equal, as in `run-a.md` |

`statistics` is identical key for key between A and B. `compare_runs` (the check `freeze` makes) returns no problem and no note. Both reports say
`passed: false`, `freezable: true`, `accepted_failures: ["G1"]`. **Nothing has been frozen yet** (step 7).
