# Deliverables — Update set and the edit path

Closed 2026-10-29 · super-plan item 4.4 · no new ADR (`interfaces.md` v0.21) · Phase 4 closed

## What shipped

- **The edit path.** `python -m rag.edit` embeds the new text the way ingest does, writes `text` and
  `vector` on `corpus::{chunk_id}`, advances the epoch, then calls `POST /invalidate`. A failed call makes
  it exit non-zero, and running the same edit again is safe.
- **`POST /invalidate`** (loopback only) replies only after the Redis purge has finished, and lists what
  was purged and what failed. A failed entry now stays in `dep:{chunk}`, so a retry can still find it. This
  closes 4.1's follow-up.
- **The update set:** 20 edits on `v1`, 10 `substantive` and 10 `cosmetic`, 5 policy and 5 product in each
  half, including the 30 → 14 day return edit. The author reviewed every label on 2026-10-29.
- **`make cache-reset`**, the reset run rule 11 needed: it clears `t1:`, `t2:`, `lru:`, `dep:` and `entry:`,
  never uses `FLUSHDB`, and refuses while a gateway runs.
- **One live run, `make update-set-check`, and one scorer, `make update-set-score`.** The scorer's oracle
  is the evaluation log, never `dep:*`, and its snapshot scans every `t1:*` key.
- **`dev-v0` retired** (the author's decision): Redis holds `v1`, and `rag.config` defaults to it. Two
  existing test files moved to `v1`, with the author's approval (design §4).

## Files changed

- Gateway: `deps/deps.go`, `httpapi/invalidate.go` (new), `httpapi/handler.go`, `cmd/gateway/main.go`.
- RAG: `rag/src/rag/edit.py` (new), `rag/src/rag/config.py`.
- Scripts: `experiments/scripts/update_set.py`, `cache_reset.py`, `update_set_check.py`,
  `score_update_set.py` (all new).
- New tests: `deps/invalidate_wait_test.go`, `httpapi/invalidate_test.go`, `rag/tests/test_edit_order.py`,
  `test_edit_failures.py`, and `experiments/tests/test_update_set.py`, `test_update_set_snapshot.py`,
  `test_score_update_set.py`, `test_cache_reset.py`.
- Existing tests, approved (design §4): `rag/tests/test_dataset_version.py`, `test_retrieve_scoping.py`.
- Data and config: `data/update-set-manifest.json` (the set itself is gitignored), `Makefile`,
  `.gitignore`, `data/README.md`.
- Docs: `interfaces.md` v0.21, `data-card.md` §5, `architecture.md`.

## How it was verified

The main session re-ran these on 2026-10-29, one at a time. Outputs are in `evidence/recheck/` and
`evidence/live3/`.

| DC | Command | Result |
| :--- | :--- | :--- |
| 1 | `make update-set-verify`; §4 | ok, 20 edits; review recorded |
| 2, 3 | the edit-tool tests; a swapped-order mutant | 4 + 6 passed; the mutant fails; the file was restored |
| 4 | `TestInvalidateWait*` (test Redis), `TestInvalidateEndpoint*` | 6 + 7 PASS |
| 5, 9 | the reset, scorer, snapshot and validator tests | 4 + 22 passed |
| 6 | `make corpus-index-check`; `make epoch-race-check` on `v1` | both pass |
| 7, 8, 13 | `make update-set-check EVIDENCE=…/live3` | exit 0 in 521 s; all checks pass |
| 9 | `make update-set-score` twice on `live3`; `live2` | byte-identical; `live2` complete |
| 10 | `make corpus-index-check`, `make corpus-verify` | `v1` whole, 539 chunks; 0 cache keys |
| 11 | greps on the three docs | present |
| 12 | `make verify`, alone, on `v1` | exit 0; only the two approved test files modified |

The Phase 4 exit line was run against `live3`; see the super-plan's Progress line for 2026-10-29 (later).

## Numbers

All are from three functional runs on the frozen `v1` corpus, with `MUTATION=on`, `CACHE_CAPACITY`
unbounded and default arms, at memory pressure 1–2. **None is citable** (the author's decision for 4.4).
- Completeness was **1.0** in all three runs: 57 of 57, 57 of 57, and 59 of 59 dependents.
- Exactness was **0** in all three.
- Precision was **0.684, 0.702 and 0.695**. It is judged per edit, not per entry: every dependent of a
  `substantive` edit counts as needed.
- Run time was 476, 383 and 521 s. Per Qwen request, the medians were about 1.3 s to read the prompt and
  2.0 s to generate (Ollama log, `live3`).

## Deferred and follow-ups

- **Next: a /bugfix for Ollama's prompt cache.** llama-server's default prompt cache of up to 8 GB reached
  5.9 GB in a run, and 116 of 130 prompts reused nothing. It must be off before any Phase 7 measurement.
- `make demo-reset` (`FLUSHALL`, then `dev-v0`) would wipe `v1` from Redis. `make demo` and `make seam-check`
  still assume `dev-v0`.
- No super-plan item owns RQ3's swept TTL baseline.
- CLAUDE.md (the author's file) still says `deps/` is a stub, that `make ingest` reads `dev-v0`, and that
  `interfaces.md` is at v0.9.
