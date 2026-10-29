# Plan — Update set and the edit path

Design: design.md (approved 2026-10-29)

**Rules for every step.**
- **One command at a time** against Redis or Ollama. Never two test runs, or a test and a live run, at once.
- **Memory pressure:** before every step that loads a model, run `sysctl kern.memorystatus_vm_pressure_level`
  and write the level in its Result. It never stops a step (design §1, the human's decision 2026-10-29).
  Every step is `citable: no`.
- **Go Redis tests** run only through `make test-go GO_TEST_PKGS=… GO_TEST_FLAGS='-count=1 -v -run …'`. Check
  each named `--- PASS`. A SKIP of a named test is a failure. `go test -run` with no match exits 0.
- **zsh has no PIPESTATUS.** Put `; echo "exit=$?"` on the command itself, never after a pipe.
- **Never** `FLUSHDB` or `FLUSHALL`, never write `data/v1/`, never commit. Never edit an existing test file,
  except the two that design §4 approves, in steps 8.5 and 8.6 only.
- **Redis holds `v1` from step 5.1 on, and keeps it:** the author retired `dev-v0` on 2026-10-29 (design §4).
  `make verify` fails until step 8.6 moves two live tests to `v1`. Run it only in Phase 9.
- **PQA text is never committed.** Anything holding question or chunk text goes under an `evidence/**/private/`
  folder (gitignored in step 4.6).
- **Step 6.3 is a stop.** Report, and wait to be continued.
- On a failed check: one quick fix if the cause is obvious and local, then run it again. If it still fails,
  stop and report the full output.

## Phase 1 — The gateway waits for the purge

- [x] 1.1 `PurgeResult` and `InvalidateWait` (design §3 Gateway).
  - Files: `gateway/internal/deps/deps.go`
  - Do: add `PurgeResult{ChunkID, Purged, Failed, Errors}` and
    `InvalidateWait(ctx, ev) (PurgeResult, error)`; add `done chan PurgeResult` to `op`.
    `applyInvalidation` counts an entry as failed when any of its three steps fails. Step 4 becomes
    `SREM dep:{c} <purged...>` (skip it when nothing was purged), and its error goes to `Errors`. `done` is
    sent after step 4. `Invalidate` is unchanged. Update the step list in the `applyInvalidation` comment.
  - Run: `cd gateway && go build ./... && go vet ./internal/deps/; echo "exit=$?"`
  - Pass: exit 0.
  - Result: added `PurgeResult`, `InvalidateWait`, `op.done`, `purgeOne`; step 4 is now `SREM` of purged members; build and vet exit 0.
- [x] 1.2 The `deps` tests (DC 4, the Redis half).
  - Files: `gateway/internal/deps/invalidate_wait_test.go` (new). Use `deps_test.go`'s helpers (`testRedis`,
    `newMap`, `seedEntry`, `exists`, `failingPurger`, `realPurger`).
  - Tests:
    - `TestInvalidateWaitReturnsAfterThePurge`: the moment it returns, `t2:E`, `t1:keyE`, `entry:E` and
      `dep:A` are gone, and `Purged` is `[E]`.
    - `TestInvalidateWaitKeepsFailedEntriesInDep`: with `failingPurger`, `Failed` is `[E]`, `dep:A` still
      holds `E`, and `entry:E` is kept.
    - `TestInvalidateWaitRetryPurgesAgain`: a purger that fails once, then works. The second call purges `E`
      and `dep:A` is gone.
    - `TestInvalidateWaitPurgesOnlyThePurged`: two entries under `A`, one fails. `dep:A` holds only the
      failed one.
    - `TestInvalidateWaitHonoursContext`: a slow purger and a cancelled ctx. It returns the ctx error, and
      the purge still finishes (checked after `barrier`).
    - `TestInvalidateWaitAfterCloseFails`.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make test-go GO_TEST_PKGS=./internal/deps/ GO_TEST_FLAGS='-count=1 -v -run TestInvalidateWait'; echo "exit=$?"`
  - Pass: six `--- PASS`, exit 0.
  - Result: added gateway/internal/deps/invalidate_wait_test.go; six TestInvalidateWait tests PASS on the :6390 test Redis, none skipped.
- [x] 1.3 The whole `deps` package still passes.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make test-go GO_TEST_PKGS=./internal/deps/ GO_TEST_FLAGS='-count=1 -v' > /tmp/deps-all.out 2>&1; echo "exit=$?"; grep -cE '^--- PASS' /tmp/deps-all.out; grep -E '^--- (FAIL|SKIP)' /tmp/deps-all.out`
  - Pass: exit 0; no FAIL or SKIP line; `TestPurgeErrorIsCounted` among the passes.
  - Result: whole deps package: 24 tests PASS, no FAIL or SKIP, TestPurgeErrorIsCounted among them (temp output kept in the scratchpad, not /tmp).
- [x] 1.4 The `/invalidate` handler (design §3).
  - Files: `gateway/internal/httpapi/invalidate.go` (new), `gateway/internal/httpapi/handler.go` (the
    `Invalidator invalidator` field only).
  - Run: `cd gateway && go build ./... && go vet ./internal/httpapi/; echo "exit=$?"`
  - Pass: exit 0.
  - Result: added httpapi/invalidate.go (Handler.Invalidate) and the Invalidator field in handler.go; also deps.ErrClosed so the handler can answer 503 for a closed map; build and vet exit 0.
- [x] 1.5 The handler tests (DC 4, the HTTP half).
  - Files: `gateway/internal/httpapi/invalidate_test.go` (new), with a fake invalidator that records calls.
  - Tests:
    - `TestInvalidateEndpointRepliesWithThePurgeResult` (200; JSON `purged`; the event fields reach the
      fake);
    - `TestInvalidateEndpointFailedPurgeIs500`;
    - `TestInvalidateEndpointRefusesNonLoopback` (`RemoteAddr` `203.0.113.5:1234` → 403, fake not called);
    - `TestInvalidateEndpointRefusesBadBody`, with subtests for: not JSON; an unknown field; an empty
      `chunk_id`; `change_type` `"minor"`; a body over 1 MB. Each gives 400, and the fake is not called.
    - `TestInvalidateEndpointRefusesGet` (405);
    - `TestInvalidateEndpointWithoutMapIs503`;
    - `TestInvalidateEndpointClosedMapIs503`.
  - Run: `cd gateway && go test -count=1 -v -run TestInvalidateEndpoint ./internal/httpapi/; echo "exit=$?"`
  - Pass: seven `--- PASS` (and the subtests), exit 0.
  - Result: added httpapi/invalidate_test.go; all seven TestInvalidateEndpoint tests PASS (with subtests), fake invalidator, no Redis.
- [x] 1.6 Wire it in `main.go`.
  - Files: `gateway/cmd/gateway/main.go`: `handler.Invalidator = depMap`, and
    `mux.HandleFunc("/invalidate", handler.Invalidate)`.
  - Run: `cd gateway && go build ./... && go vet ./... && go test -count=1 ./cmd/gateway/ ./internal/httpapi/; echo "exit=$?"`
  - Pass: exit 0; both `ok`.
  - Result: main.go sets handler.Invalidator = depMap and routes /invalidate; build, vet ./..., cmd/gateway and httpapi tests ok; deps package re-run after adding ErrClosed: 24 PASS.

## Phase 2 — The edit tool

- [x] 2.1 `rag.edit` (design §3, the edit tool).
  - Files: `rag/src/rag/edit.py` (new): `Edit`, `Applied`, `load_edit`, `embed_document`, `apply`,
    `restore`, `main`.
    - `write` is a function over a redis client. It refuses a missing key, and a `text` that is neither
      `before` nor `after`. It returns the old `text` and the old `vector` bytes.
    - `post` uses `httpx`, with a timeout of 30 s.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && ruff check rag && python3 -c "import rag.edit"; echo "exit=$?"`
  - Pass: exit 0.
  - Result: added rag/src/rag/edit.py (Edit, Applied, load_edit, embed_document, apply, restore, redis_writer, make_post, main); ruff check rag and import rag.edit exit 0.
- [x] 2.2 The order test (DC 2).
  - Files: `rag/tests/test_edit_order.py` (new). Fakes for `write`, `advance`, `post` and `embed` append to
    one list.
  - Tests:
    - `test_apply_calls_write_then_advance_then_post`, which asserts the exact list
      `["embed", "write", "advance", "post"]`;
    - `test_given_vector_skips_embed`;
    - `test_restore_uses_the_same_order`;
    - `test_embed_document_uses_the_document_prefix` (a fake Ollama client records the input).
  - Run: `cd rag && pytest -q tests/test_edit_order.py; echo "exit=$?"`
  - Pass: 4 passed, exit 0.
  - Result: added rag/tests/test_edit_order.py; 4 passed (order embed,write,advance,post; given vector; restore; single document prefix).
- [x] 2.3 The failure tests (DC 3).
  - Files: `rag/tests/test_edit_failures.py` (new).
  - Tests:
    - `test_post_transport_error_exits_nonzero_naming_the_chunk`;
    - `test_post_500_exits_nonzero_naming_the_chunk`;
    - `test_rerun_on_after_text_advances_and_posts_again`;
    - `test_foreign_text_is_refused_before_any_side_effect` (no write, no advance, no post);
    - `test_missing_key_is_refused`;
    - `test_relative_epoch_file_is_refused`.
  - Run: `cd rag && pytest -q tests/test_edit_failures.py; echo "exit=$?"`
  - Pass: 6 passed, exit 0.
  - Result: added rag/tests/test_edit_failures.py; 6 passed (transport error and 500 exit non-zero naming the chunk; re-run; foreign text; missing key; relative epoch path).

## Phase 3 — The scorer and the snapshot

- [x] 3.1 The scorer (design §3, `score_update_set.py`).
  - Files: `experiments/scripts/score_update_set.py` (new).
  - Do: read `oracle.json`, `labels.json`, `snapshot-before.json`, `snapshot-after.json`, `replies.json`
    and `reask.json`. Write `score.json` (sorted keys, no time) and print it. Exit 1 on any failed check.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && ruff check experiments && python3 experiments/scripts/score_update_set.py --help; echo "exit=$?"`
  - Pass: exit 0.
  - Result: added experiments/scripts/score_update_set.py (load, present, score, render, main; also checks labels distinct, every edit has a reply, and some present entries depend on no edited chunk); ruff check experiments and --help exit 0.
- [x] 3.2 The scorer tests (DC 9).
  - Files: `experiments/tests/test_score_update_set.py` (new), on small JSON fixtures in `tmp_path`.
  - Tests:
    - `test_entry_absent_before_is_not_counted`;
    - `test_gone_non_dependent_breaks_exactness`;
    - `test_dependent_left_in_tier1_only_breaks_completeness`;
    - `test_entry_under_both_labels_counts_as_needed`;
    - `test_reply_naming_an_unknown_entry_fails`;
    - `test_dependent_not_named_in_any_reply_fails`;
    - `test_edit_with_no_dependent_fails`;
    - `test_reask_hit_on_a_dependent_fails`;
    - `test_two_runs_print_identical_bytes`.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && pytest -q experiments/tests/test_score_update_set.py; echo "exit=$?"`
  - Pass: 9 passed, exit 0.
  - Result: added experiments/tests/test_score_update_set.py; 9 passed (nine fixtures from one good baseline; byte-identical output across two runs).
- [x] 3.3 The snapshot (design §3, "The snapshots").
  - Files: `experiments/scripts/update_set_check.py` (new; for now only `snapshot(client) -> dict` and
    the module skeleton), `experiments/tests/test_update_set_snapshot.py` (new, fake client).
  - Tests:
    - `test_snapshot_finds_t1_key_missing_from_lru_t1keys`;
    - `test_snapshot_reads_t2_and_entry_records`;
    - `test_snapshot_ignores_corpus_keys`.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && pytest -q experiments/tests/test_update_set_snapshot.py; echo "exit=$?"`
  - Pass: 3 passed, exit 0.
  - Result: added experiments/scripts/update_set_check.py (skeleton + snapshot()) and experiments/tests/test_update_set_snapshot.py; 3 passed (finds a t1: key that lru:t1keys does not list).

## Phase 4 — The reset, the validator, the Makefile

- [x] 4.1 The cache reset (DC 5).
  - Files: `experiments/scripts/cache_reset.py` (new), `experiments/tests/test_cache_reset.py` (new, fake
    client; it raises if `flushdb`/`flushall` is called).
  - Tests:
    - `test_reset_empties_the_five_prefixes`;
    - `test_reset_keeps_corpus_keys_and_index_list`;
    - `test_reset_refuses_while_a_gateway_listens` (deletes nothing);
    - `test_reset_never_flushes`.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && pytest -q experiments/tests/test_cache_reset.py; echo "exit=$?"`
  - Pass: 4 passed, exit 0.
  - Result: added experiments/scripts/cache_reset.py (reset, listening_ports, main) and experiments/tests/test_cache_reset.py; 4 passed, the fake raises on flushdb/flushall.
- [x] 4.2 The update-set validator and probe (DC 1).
  - Files: `experiments/scripts/update_set.py` (new: `probe`, `verify`),
    `experiments/tests/test_update_set.py` (new). The tests use a tiny corpus dir and set in `tmp_path`;
    `verify` takes `--corpus-dir`, `--set` and `--manifest`, with the real paths as defaults.
  - Tests:
    - `test_good_set_passes`;
    - `test_wrong_counts_fail`;
    - `test_too_few_policy_or_product_edits_fail`;
    - `test_before_not_equal_to_corpus_text_fails`;
    - `test_after_equal_to_before_fails`;
    - `test_cosmetic_edit_changing_a_number_fails`;
    - `test_duplicate_chunk_fails`;
    - `test_missing_return_window_edit_fails`;
    - `test_manifest_hash_mismatch_fails`;
    - `test_schema_field_missing_fails`.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && pytest -q experiments/tests/test_update_set.py; echo "exit=$?"`
  - Pass: 10 passed, exit 0.
  - Result: added experiments/scripts/update_set.py (probe, verify, chunk_texts) and experiments/tests/test_update_set.py; 10 passed.
- [x] 4.3 The live-run script (design §3, `update_set_check.py`).
  - Files: `experiments/scripts/update_set_check.py`. Reuse `epoch_race_check.py`'s process handling:
    import it, or copy only what is needed, and say which in the Result. Phases: preconditions, race,
    fill, edits, DC 13 reads, re-ask, restore, evidence, scorer.
    - It refuses an `--evidence-dir` that already holds files.
    - Text-bearing files go to `<dir>/private/`.
    - It writes `pressure.txt` at start and after the fill, and records its own run time.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && ruff check experiments && python3 experiments/scripts/update_set_check.py --help; echo "exit=$?"`
  - Pass: exit 0.
  - Result: wrote experiments/scripts/update_set_check.py (snapshot, plan_fill, Services, the 8-phase run; imports epoch_race_check for Checks, wait_listening, stop, read_records, pressure_level, SCRUBBED_ENV); race and fill use two rag.server/gateway lifetimes because cache-reset refuses under a live gateway; ruff and --help exit 0, snapshot tests still 3 passed.
- [x] 4.4 The Makefile targets.
  - Files: `Makefile`:
    - `update-set-probe` (`OUT=`), `update-set-verify`, `cache-reset`, `update-set-check` and
      `update-set-score`, each with a `##` help line;
    - `update-set-check` and `update-set-score` refuse unless `EVIDENCE` was given on the command line:
      `test "$(origin EVIDENCE)" = "command line"`, because `EVIDENCE` already has 4.2's default;
    - `update-set-check` and `update-set-probe` print the pressure level first, as `epoch-race-check` does.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make help | grep -E "update-set|cache-reset"; make update-set-check; echo "exit=$?"`
  - Pass: five help lines; the bare `make update-set-check` exits non-zero and asks for `EVIDENCE=`.
  - Result: added update-set-probe, update-set-verify, cache-reset, update-set-check, update-set-score to the Makefile (and .PHONY); make help shows five lines; bare make update-set-check exits 2 asking for EVIDENCE=.
- [x] 4.5 Lint the new code.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make lint; echo "exit=$?"`
  - Pass: exit 0.
  - Result: make lint exit 0 (gofmt, go vet ./..., ruff check rag experiments all clean).
- [x] 4.6 `.gitignore`.
  - Files: `.gitignore`: add `data/update-set-v1.json` beside the workload line, and
    `docs/work/*/evidence/**/private/`, each with a one-line reason (PQA text, redistribution not granted).
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && git check-ignore -v data/update-set-v1.json docs/work/2026-10-29-update-set/evidence/live1/private/requests.jsonl; echo "exit=$?"`
  - Pass: both paths printed, exit 0.
  - Result: added data/update-set-v1.json and docs/work/*/evidence/**/private/ to .gitignore, each with a reason; git check-ignore prints both paths (and the tracked manifest is not ignored), exit 0.

## Phase 5 — `v1` in Redis (DC 6)

- [x] 5.1 Ingest `v1`. Loads the embedding model; record the pressure.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && redis-cli FT._LIST; DATASET_VERSION=v1 make ingest > docs/work/2026-10-29-update-set/evidence/ingest-v1.out 2>&1; echo "exit=$?"; tail -3 docs/work/2026-10-29-update-set/evidence/ingest-v1.out; redis-cli FT.INFO idx:corpus | grep -A1 -x num_docs`
  - Pass: exit 0; 164 docs and 539 chunks; `num_docs` 539.
  - Result: DATASET_VERSION=v1 make ingest exit 0: 164 docs, 539 chunks, num_docs 539, epoch file 1 -> 2; pressure 1 (green); output in evidence/ingest-v1.out.
- [x] 5.2 The index is the frozen corpus.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make corpus-index-check > docs/work/2026-10-29-update-set/evidence/corpus-index-check-1.out 2>&1; echo "exit=$?"; tail -5 docs/work/2026-10-29-update-set/evidence/corpus-index-check-1.out`
  - Pass: exit 0.
  - Result: make corpus-index-check exit 0: "the index is the v1 corpus: 539 chunks"; output in evidence/corpus-index-check-1.out.
- [x] 5.3 4.2's live race on `v1`. Loads the LLM; record the pressure.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make epoch-race-check EVIDENCE=docs/work/2026-10-29-update-set/evidence/private/race-v1; echo "exit=$?"`
  - Pass: exit 0. Exit 2 ("race not forced") is not a failure: run it once more, into `race-v1b`.
  - Then copy the IDs-only summary into `evidence/race-v1-summary.txt`: the two records' `cache`,
    `writeback_discarded` and `entry_id`, the key diff, and the pressure.
  - Result: make epoch-race-check on v1 exited 0 (PASS, no re-run needed): record B discarded (entry_id empty), no key appeared after A; pressure 1 before, 2 after; summary in evidence/race-v1-summary.txt, raw in evidence/private/race-v1 (gitignored).

## Phase 6 — The update set (DC 1)

- [x] 6.1 The probe. Loads the embedding model; record the pressure.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make update-set-probe OUT=docs/work/2026-10-29-update-set/evidence/probe.json; echo "exit=$?"`
  - Pass: exit 0. Every validation query (622) has its `chunk_ids`, and the file holds IDs only.
  - Result: make update-set-probe exit 0 in 20 s: the probe file (moved to evidence/private/probe.json in step 6.4) holds 622/622 validation queries with 1-5 chunk_ids each, IDs only (no text); pressure 2 (yellow, recorded, not a gate).
- [x] 6.2 Draft the set (design §3, "Drafting the set").
  - Files: `data/update-set-v1.json`, `data/update-set-manifest.json`,
    `docs/work/2026-10-29-update-set/evidence/private/update-set-review.md`.
    - Only chunks that at least 2 validation questions retrieve (the probe).
    - 10 `substantive` and 10 `cosmetic`, with at least 4 policy and 4 product edits in each half, and 20
      different chunks.
    - The 30 → 14 day edit is on a `policy-return-*` chunk whose `v1` text says "30 days".
    - The review sheet is one row per edit: `edit_id`, `chunk_id`, `change_type`, `before` → `after` with
      the changed words marked, and `expected_effect`.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make update-set-verify; echo "exit=$?"`
  - Pass: exit 0.
  - Result: drafted data/update-set-v1.json (gitignored), data/update-set-manifest.json (sha256 df3ae7d4...e247c2) and evidence/private/update-set-review.md: 20 edits, 10 substantive + 10 cosmetic, 5 policy + 5 product in each half, edit-001 is the 30 -> 14 day edit on policy-return-electronics#chunk-0, every chunk retrieved by 5+ validation clusters; make update-set-verify exit 0.
- [x] 6.3 **STOP: the author reviews the labels.** Report the review sheet's path and the counts, and wait to
  be continued. The main session asks the author and writes the review line in design §4 with the date.
  Any label the author changes is fixed in the set, and step 6.2's Run is repeated.
  - Pass: design §4 holds "Update set reviewed by the author on <date>", and `make update-set-verify`
    exits 0 after any change.
  - Result: design.md section 4 holds "Update set reviewed by the author on 2026-10-29" (all 20 labels approved, the four product rewordings included as cosmetic); no change to the set; make update-set-verify re-run: exit 0.
- [x] 6.4 ID files go private (the author's decision, design §4 and DC 9).
  - Files: move `evidence/probe.json` to `evidence/private/probe.json` (`git mv` is not needed: it is not
    tracked), and change `update_set_check.py`'s default probe path. Change `update_set_check.py` so that
    every file with a `qa_id` or a chunk ID goes to `EVIDENCE/private/`; only `score.json` and `pressure.txt`
    stay in `EVIDENCE/`. `score_update_set.py` reads from `EVIDENCE/private/`, and `score.json` keys its
    per-edit counts by `edit_id` and holds no chunk ID or `qa_id`. Update the new tests and their fixtures
    to match. Correct `race-v1-summary.txt` too, if it names a chunk or product ID.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && ruff check experiments && pytest -q experiments/tests/test_score_update_set.py experiments/tests/test_update_set_snapshot.py; echo "exit=$?"; grep -rlE 'b0[0-9a-z]{8}|q-(product|policy)-' docs/work/2026-10-29-update-set --exclude-dir=private; echo "grep-exit=$?"`
  - Pass: 9 and 3 passed, exit 0; the grep finds no file (`grep-exit=1`).
  - Result: moved probe.json to evidence/private/ (DEFAULT_PROBE, Makefile hint, docstring updated); update_set_check.py now writes oracle, labels, both snapshots, replies, reask, race, dc13, summary and run-time to EVIDENCE/private/, and only pressure.txt and score.json to EVIDENCE/; scorer reads EVIDENCE/private/ and per_edit drops chunk_id; tests adapted (9 + 3 = 12 passed, plus a no-ID check on score.json); race-v1-summary.txt already held no chunk or product ID; grep of the trail outside private/ finds no file.

## Phase 7 — The live runs (DC 5, 7, 8, 9, 10, 13)

- [x] 7.1 Reset the real cache. No gateway is running.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && redis-cli FT._LIST; make cache-reset; echo "exit=$?"; redis-cli FT._LIST; for p in 't1:*' 't2:*' 'lru:*' 'dep:*' 'entry:*'; do printf '%s %s\n' "$p" "$(redis-cli --scan --pattern "$p" | wc -l)"; done; redis-cli FT.INFO idx:corpus | grep -A1 -x num_docs`
  - Pass: exit 0; the five counts are 0; `FT._LIST` unchanged; `num_docs` 539.
  - Result: make cache-reset exit 0: deleted t1/t2/lru/dep/entry 0 each (cache was already empty), corpus: keys 539, FT._LIST idx:corpus + idx:cache unchanged, five counts 0, num_docs 539.
- [x] 7.2 The first live run. Loads both models; record the pressure.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make update-set-check EVIDENCE=docs/work/2026-10-29-update-set/evidence/live1; echo "exit=$?"`
  - Pass: exit 0. The script's checks hold:
    - the race record lists the edited chunk and is discarded;
    - every edit has a dependent;
    - completeness is 1 and exactness is 0, and every reply is 200 with nothing failed;
    - no re-ask hits a dependent;
    - every `dc13.json` row passes;
    - every chunk is restored.
  - Result: write precision, the counts and the run time. Exit 2 means "race not forced": run it again
    into `live1b`.
  - Result: exit 0 on the first try (no live1b needed), run time 476 s, pressure 1 at start and 2 after the fill and at the end (recorded, not a gate). Completeness 1.0 (57/57 dependents gone), exactness 0, precision 0.684 (39 of 57 purged dependents needed a substantive edit); 70 fill questions gave 67 MISS and 3 TIER2_HIT; 67 entries present before, 10 depend on no edited chunk; 20 edits, every one has 2-9 dependents, all 20 replies 200 with nothing failed; 57 re-asks, all MISS, none hit a dependent; race: chunk in retrieved_chunk_ids, writeback_discarded true, entry_id empty, 0 keys; DC 13 20/20 rows pass (stored vector bytes equal 20/20, before-vs-ingested cosine 1.0); 20/20 chunks restored, cache keys gone. Committed: live1/score.json and live1/pressure.txt only; the rest is in live1/private/.
- [x] 7.3 The scorer is reproducible.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make update-set-score EVIDENCE=docs/work/2026-10-29-update-set/evidence/live1 > /tmp/s1.json; make update-set-score EVIDENCE=docs/work/2026-10-29-update-set/evidence/live1 > /tmp/s2.json; cmp /tmp/s1.json /tmp/s2.json && cmp /tmp/s1.json docs/work/2026-10-29-update-set/evidence/live1/score.json; echo "exit=$?"`
  - Pass: exit 0.
  - Result: make update-set-score on live1 twice: the two outputs are byte-identical (cmp) and equal live1/score.json (cmp), exit 0; temp outputs kept in the scratchpad, not /tmp.
- [x] 7.4 The second live run. Loads both models; record the pressure.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make update-set-check EVIDENCE=docs/work/2026-10-29-update-set/evidence/live2; echo "exit=$?"`
  - Pass: exit 0; completeness 1, exactness 0.
  - Result: exit 0 on the first try, run time 383 s, pressure 2 (yellow) at start and at the end (recorded, not a gate). Completeness 1.0, exactness 0, precision 0.702 (40 of 57 dependents needed a substantive edit; live1 gave 0.684, 39 of 57, so a second run moves precision by one entry because the fill answers differ). Same counts as live1: 67 MISS, 3 TIER2_HIT, 57 dependents. All replies 200, no re-ask hit, DC 13 20/20, race discarded with 0 keys, 20/20 chunks restored.
- [x] 7.5 `v1` is whole again.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make corpus-index-check > docs/work/2026-10-29-update-set/evidence/corpus-index-check-2.out 2>&1; echo "exit=$?"; make corpus-verify; echo "exit=$?"; for p in 't1:*' 't2:*' 'lru:*' 'dep:*' 'entry:*'; do printf '%s %s\n' "$p" "$(redis-cli --scan --pattern "$p" | wc -l)"; done`
  - Pass: both exit 0; the five counts are 0.
  - Result: corpus-index-check exit 0 ("the index is the v1 corpus: 539 chunks", evidence/corpus-index-check-2.out); corpus-verify exit 0 ("v1 still matches v1-freeze.json: 167 files, 539 chunks"); the five cache counts are 0.
- [x] 7.6 Redis keeps `v1` (`dev-v0` is retired, design §4). No ingest.
  - Run: `redis-cli FT.INFO idx:corpus | grep -A1 -x num_docs; redis-cli FT._LIST`
  - Pass: `num_docs` 539; `idx:corpus` is listed.
  - Result: no ingest: num_docs 539, FT._LIST lists idx:corpus (and idx:cache); Redis keeps v1.

## Phase 8 — Docs, and retiring `dev-v0` (DC 11, DC 12)

- [x] 8.1 `interfaces.md` v0.21.
  - Files: `docs/contracts/interfaces.md`:
    - the header version;
    - §E: a short "Edit transport (v0.21)" block, with `POST /invalidate`'s request (the event), reply
      (`chunk_id, purged, failed, errors`), status codes and loopback rule; the edit order as `rag.edit`
      runs it; and step 4 as `SREM` of the purged members;
    - rule 11 names `make cache-reset` for `dep:` and `entry:`, replacing "until Phase 4";
    - a version-history row.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && grep -n "v0.21\|/invalidate\|cache-reset\|SREM dep" docs/contracts/interfaces.md | cut -c1-110`
  - Pass: the header, the §E block, the step-4 line, rule 11 and the history row all show.
  - Result: interfaces.md is v0.21: header, new "Edit transport (v0.21)" block in section E (POST /invalidate request, reply, status table, loopback rule, edit order), purge step 4 as SREM of purged members, rule 11 names make cache-reset, history row added; the grep shows all five.
- [x] 8.2 `data-card.md` §5.
  - Files: `docs/data-card.md` §5: replace the `TODO(W8)` line with the built set. Give its path, the
    manifest hash, the counts by type and kind, the drafting rules, the 30 → 14 day edit, and the review
    date. No PQA text.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && awk '/^## 5\./,/^## 6\./' docs/data-card.md | grep -c "TODO"; grep -n "update-set-v1" docs/data-card.md`
  - Pass: `0`, and the path shows.
  - Result: data-card.md section 5: TODO replaced by the built set (path, manifest hash, counts by type and kind, drafting rules, the 30 -> 14 day edit, review date 2026-10-29, no PQA text); the source table row for the update set also updated; TODO count in section 5 is 0 and the path shows.
- [x] 8.3 `architecture.md`.
  - Files: `docs/architecture.md`: `rag/src/rag/edit.py` in the tree; `/invalidate` in the `httpapi/` row;
    the four scripts; and the new targets in the commands table.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && grep -n "edit.py\|/invalidate\|update_set\|cache-reset" docs/architecture.md | cut -c1-110`
  - Pass: each one shows.
  - Result: architecture.md: edit.py in the rag tree, /invalidate in the httpapi row, InvalidateWait in the deps row, the four scripts, the two data files, and a new "Update set" row in the commands table; the grep shows each.
- [x] 8.4 `rag.config` defaults to `v1` (design §3, "Retiring `dev-v0`").
  - Files: `rag/src/rag/config.py` (the default and its comment), `Makefile` (the `ingest` help text and its
    comment: default `v1`).
  - Run: `cd /Users/hung/Desktop/Sem1/thesis/rag && env -u DATASET_VERSION python3 -c "from rag import config; print(config.DATASET_VERSION)"; DATASET_VERSION= python3 -c "from rag import config; print(config.DATASET_VERSION)"`
  - Pass: `v1` twice.
  - Result: rag/src/rag/config.py defaults DATASET_VERSION to v1 (comment says why); Makefile ingest help and comments say default v1 (and the stale "Redis holds dev-v0 again" comment is corrected); both unset and empty print v1; ruff clean.
- [x] 8.5 `test_dataset_version.py` (approved edit, design §4).
  - Files: `rag/tests/test_dataset_version.py`: in `test_unset_gives_dev_v0` and `test_empty_counts_as_unset`,
    the expected value changes from `"dev-v0"` to `"v1"`. Rename the first test to `test_unset_gives_v1`.
    Change nothing else.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && python3 -m pytest -q rag/tests/test_dataset_version.py; echo "exit=$?"; git diff --stat -- rag/tests/test_dataset_version.py`
  - Pass: 3 passed; the diff touches only those lines.
  - Result: test_dataset_version.py: test_unset_gives_dev_v0 renamed test_unset_gives_v1 and the two expected values changed from "dev-v0" to "v1"; 3 passed; git diff touches only those 3 lines (3 insertions, 3 deletions).
- [x] 8.6 Move the two live scoping tests to `v1` (approved edit, design §4). Loads the embedding model; record
  the pressure.
  - Files: `rag/tests/test_retrieve_scoping.py`, in the two failing tests only:
    `test_product_scoping_prevents_cross_product_contamination` and
    `test_scoping_does_not_flood_policy_chunks_for_a_plain_spec_question`.
    - Pick two `v1` products of different categories. One has a spec, such as power in watts, that the other
      lacks. Find them by reading their chunks in Redis and by running unscoped `retrieve`, so the unscoped
      self-check really shows the other product leaking in.
    - Change only the product IDs, the query text if the spec needs it, and the docstrings' `dev-v0` names.
    - Every `assert` stays as it is.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && python3 -m pytest -q -rs rag/tests/test_retrieve_scoping.py; echo "exit=$?"; git diff -- rag/tests/test_retrieve_scoping.py | grep -E '^[-+][^-+]' | grep -c assert`
  - Pass (corrected by the main session, 2026-10-29: the plan's count was wrong): 5 passed, no skip; the
    diff changes only product IDs, the query, docstrings, and the product string inside three `assert`
    lines (count 6: 3 removed, 3 added); what each `assert` checks is unchanged.
  - Result (the author accepted this diff on 2026-10-29, design §4): the two tests now run on `v1` products (a furniture product
    with no power spec, and a laptop that lists a 45 W adapter; unscoped retrieval pulls laptop chunks in,
    scoped retrieval never does; the IDs are in the test file, not here, because they carry an ASIN) and `test_retrieve_scoping.py` gives 5 passed, no skip. Two pass conditions cannot
    hold as written. (1) The file has 5 tests, not 7 (the 2 failed + 5 passed in `rag-live-tests-on-v1.out` counted
    several files). (2) Three `assert` lines name the `dev-v0` product IDs (`product-kitchen`, `product-kitchen-05`),
    so moving to `v1` products changes those three lines: only the string literal in each, never the logic. The
    `grep -c assert` count is 6 (3 removed, 3 added), not 0. Please confirm or revert.

## Phase 9 — Run and verify

Run every step alone, in order. `v1` is in Redis (step 7.6).

- [x] 9.1 DC 12. Loads the embedding model; record the pressure.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && (cd gateway && go clean -testcache); make verify > docs/work/2026-10-29-update-set/evidence/verify.out 2>&1; echo "exit=$?"; grep -nE "FAIL|SKIP" docs/work/2026-10-29-update-set/evidence/verify.out; git status --porcelain | grep -E "_test\.go|rag/tests/|experiments/tests/" | grep -v '^??'`
  - Pass: exit 0; no FAIL or SKIPPED target; the last grep prints exactly the two approved files,
    `rag/tests/test_dataset_version.py` and `rag/tests/test_retrieve_scoping.py`.
  - Result: make verify exit 0, run alone with v1 in Redis (pressure 2, recorded): lint ok, go build ok, 10 Go packages ok, rag 62 passed, experiments 757 passed, no FAIL or SKIP in evidence/verify.out; git status shows exactly the two approved modified test files (test_dataset_version.py, test_retrieve_scoping.py) and no other modified test; Redis still has idx:corpus + idx:cache, num_docs 539, five cache prefixes 0.
- [x] 9.2 DC 1.
  - Run: `make update-set-verify; echo "exit=$?"; grep -n "reviewed by the author" docs/work/2026-10-29-update-set/design.md`
  - Pass: exit 0; the review line shows.
  - Result: make update-set-verify exit 0 (20 edits, 10 substantive, 10 cosmetic); design.md section 4 holds "Update set reviewed by the author on 2026-10-29".
- [x] 9.3 DC 2.
  - Run: the step 2.2 command. Then two mutations, one at a time. Copy `rag/src/rag/edit.py` to `/tmp`, swap
    `write` and `advance` in `apply`, and run the test, which must FAIL. Restore with `cp` and `cmp`. Do the
    same with `advance` and `post`.
  - Pass: 4 passed; both mutants FAIL; `cmp` shows the file restored.
  - Result: test_edit_order.py 4 passed; mutant 1 (advance before write) gives 2 failed, mutant 2 (post before advance) gives 2 failed; after each, cp from the scratchpad copy and cmp show edit.py restored; final run 4 passed (backup kept in the scratchpad, not /tmp).
- [x] 9.4 DC 3: the step 2.3 command. Pass: 6 passed.
  - Result: test_edit_failures.py: 6 passed.
- [x] 9.5 DC 4: the step 1.2 and 1.5 commands. Pass: six and seven `--- PASS`.
  - Result: six TestInvalidateWait tests PASS (test Redis :6390) and seven TestInvalidateEndpoint tests PASS (with subtests), exit 0.
- [x] 9.6 DC 5: the step 4.1 command, and the reset counts in `live1`'s evidence. Pass: 4 passed; counts as
  in 7.1.
  - Result: test_cache_reset.py 4 passed; the live runs reset the real server to zero in all five prefixes (reset line {t1:0,t2:0,lru:0,dep:0,entry:0}, corpus: 539 keys and FT._LIST unchanged) and ended with "the cache keys the run wrote are gone [0 entries left]"; same counts as 7.1.
- [x] 9.7 DC 6: the files from steps 5.1–5.3.
  - Run: `grep -n "539" docs/work/2026-10-29-update-set/evidence/ingest-v1.out; tail -2 docs/work/2026-10-29-update-set/evidence/corpus-index-check-1.out; cat docs/work/2026-10-29-update-set/evidence/race-v1-summary.txt`
  - Pass: 539 chunks; the check passed; the race record is discarded.
  - Result: ingest-v1.out shows 164 docs and 539 chunks; corpus-index-check-1.out shows PASS (539 chunks); race-v1-summary.txt shows record B writeback_discarded=True with an empty entry_id.
- [x] 9.8 DC 7 and 13.
  - Run: `python3 -c "import json; s=json.load(open('docs/work/2026-10-29-update-set/evidence/live1/score.json')); print(s)"` and the same for `live1/private/dc13.json`.
  - Pass: completeness 1; exactness 0; no failed reply; every edit has a dependent; no re-ask hit; every
    `dc13` row passes.
  - Result: live1/score.json: completeness 1.0, exactness 0, precision 0.684, all ten checks true (replies ok, every edit has a dependent, no re-ask hit); live1/private/dc13.json: 20 of 20 rows pass (fetch_by_ids and retrieve return the after text, stored vector cosine 1.0, before-vs-ingested cosine 1.0).
- [x] 9.9 DC 8: read `live1/private/race.json`.
  - Pass: the edited chunk is in `retrieved_chunk_ids`; `writeback_discarded` is true; no key.
  - Result: live1/private/race.json: the edited chunk is in retrieved_chunk_ids, writeback_discarded true, entry_id empty, cache_keys_after empty ({}), HTTP 200.
- [x] 9.10 DC 9:
  - the step 7.3 command;
  - the step 3.2 and 3.3 commands;
  - `make update-set-score EVIDENCE=docs/work/2026-10-29-update-set/evidence/live2`.

  Pass: `cmp` exit 0; 9 and 3 passed; `live2` completeness 1, exactness 0.
  - Result: update-set-score on live1 twice gives byte-identical output equal to score.json (cmp exit 0); test_score_update_set.py 9 passed; test_update_set_snapshot.py 3 passed; live2: completeness 1.0, exactness 0, precision 0.702, ok true.
- [x] 9.11 DC 10:
  - the file from step 7.5;
  - `redis-cli FT.INFO idx:corpus | grep -A1 -x num_docs`;
  - `make corpus-verify`.

  Pass: check 2 passed; `num_docs` 539; `corpus-verify` exit 0.
  - Result: corpus-index-check-2.out PASS (539 chunks); num_docs 539; make corpus-verify exit 0 (v1 still matches v1-freeze.json); no ingest was needed, and data/v1 was never written.
- [x] 9.12 DC 11: the greps of steps 8.1–8.3. Pass: as there.
  - Result: the 8.1, 8.2 and 8.3 greps re-run: interfaces.md has v0.21, /invalidate, SREM dep and cache-reset; data-card section 5 has 0 TODO and names update-set-v1; architecture.md names edit.py, /invalidate, update_set and cache-reset.
- [x] 9.13 No PQA text and no ID file is tracked.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && git status --porcelain --untracked-files=all docs/work/2026-10-29-update-set data | grep -E "private/|update-set-v1.json"; echo "exit=$?"; grep -rlE 'b0[0-9a-z]{8}|q-(product|policy)-' docs/work/2026-10-29-update-set --exclude-dir=private; echo "grep-exit=$?"`
  - Pass: the first grep prints nothing (exit 1); the second finds no file (`grep-exit=1`).
  - Result: git status shows no private/ path and no update-set-v1.json among the trail and data files; the grep for ASIN-like IDs and qa_ids outside private/ finds no file (grep-exit 1). Committed live evidence is only live1/ and live2/ score.json and pressure.txt.
