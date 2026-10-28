# Plan — Epoch-guarded write-back

Design: design.md (approved 2026-10-28)

**Before any step:** `redis-cli PING` answers `PONG`. The new Go Redis test uses DB 14 through 4.1's helpers,
which call `FLUSHDB`. On this server a `FLUSHDB` drops every search index in every DB (4.1 design §4), so
**never run a Go Redis test in parallel with another Redis test, `make verify` or step 4.8.** Run
commands one at a time.

Never edit an existing `_test.go` or `rag/tests/*` file. `go test -run` and `pytest -k` exit 0 when nothing
matches, so every test step runs with `-v`, and its Pass line names the tests that must pass. A `SKIP` is a
failed step. Only step 4.8 loads a model. Every other step is `citable: no` and needs no memory check.

## Phase 0 — Baseline

- [x] 0.1 Hash every existing test file (DC 13; 4.1's tests are not committed, so git cannot see an edit).
  - Files: `docs/work/2026-10-28-epoch-guard/evidence/test-hashes-before.txt` (new)
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && { find gateway -name '*_test.go'; find rag/tests experiments/tests -name '*.py'; } | sort | xargs shasum -a 256 > docs/work/2026-10-28-epoch-guard/evidence/test-hashes-before.txt && wc -l docs/work/2026-10-28-epoch-guard/evidence/test-hashes-before.txt`
  - Pass: the file exists with one line per test file (more than 40 lines).
  - Result: wrote evidence/test-hashes-before.txt with 62 lines (one per test file) before any change.

## Phase 1 — Implement

- [x] 1.1 The Python epoch module.
  - Files: `rag/src/rag/epoch.py` (new)
  - Do: exactly design §3 "Files — Python", `epoch.py`. `ENV`, `NOT_READ = 0`, `EpochError`; `read()`
    never raises; `check()` raises `EpochError` for unset, empty, relative, missing, not an integer, below 1;
    `require_path()`; `advance()` with `fcntl.flock` on `<file>.lock`, temp file in the same directory,
    `fsync`, `os.replace`, and `EpochError` on a present but invalid file; a `__main__` with `advance` and
    `show`. The path is read from the environment at call time, never at import. Standard library only.
  - Run: `cd rag && python3 -c "import rag.epoch" && ruff check src/rag/epoch.py`
  - Pass: imports; ruff clean.
  - Result: added rag/src/rag/epoch.py; imports, ruff clean (ruff is in ~/Library/Python/3.13/bin, not on PATH; added it to PATH for the run).

- [x] 1.2 Stamp the epoch read first, in the server and in retrieve.
  - Files: `rag/src/rag/server.py`, `rag/src/rag/retrieve.py`, `rag/src/rag/config.py`
  - Do:
    - `server.py`: `ep = epoch.read()` as the first statement of `Retrieve` and of `Answer`, and both
      responses carry `ep`, never the epoch returned by `retrieve.*`. Comment why: the read must come
      before the chunk texts (§E order rule). `serve()` calls `epoch.check()` before `build_server`, and the
      listen line also prints the path and the value.
    - `retrieve.py`: in `fetch_by_ids` and `retrieve`, read `epoch.read()` into a local as the first
      statement and return it in place of `config.DATASET_EPOCH_STUB`. The return shape stays the same.
    - `config.py`: delete the stub block; leave one comment line pointing to `rag/epoch.py`.
  - Run: `cd rag && python3 -m pytest -q && grep -rn "DATASET_EPOCH_STUB" src`
  - Pass: every existing rag test passes; the grep prints nothing.
  - Result: server.py, retrieve.py, config.py edited (epoch read first, stub removed); 23 rag tests pass, grep empty, ruff clean.

- [x] 1.3 Ingest advances the epoch after the index is written.
  - Files: `rag/src/rag/ingest.py`
  - Do: move the `vector_store … VectorStoreIndex(...)` block of `main()`, unchanged, into
    `_write_index(nodes)`. `main()` calls `epoch.require_path()` first (before `load_records`), then loads,
    splits, `_write_index(all_nodes)`, then `epoch.advance()`, and prints the new epoch. Do not run ingest.
  - Run: `cd rag && python3 -m pytest -q tests/test_ingest_nodes.py tests/test_dataset_version.py && ruff check src`
  - Pass: those tests pass; ruff clean.
  - Result: ingest.py now has _write_index(nodes); main() runs require_path, load, split, _write_index, advance; 8 tests pass, ruff clean.

- [x] 1.4 The Go epoch reader.
  - Files: `gateway/internal/deps/epoch.go` (new)
  - Do: `EpochSource`, `EpochFile`, `OpenEpochFile(path) (*EpochFile, uint64, error)` (refuses a relative
    path, a missing file, a non-integer after `strings.TrimSpace`, and a value below 1), `Current()` (reads
    the file on every call, same rules), `Path()`. Standard library only.
  - Run: `cd gateway && go build ./... && go vet ./internal/deps/`
  - Pass: builds; vet clean.
  - Result: added gateway/internal/deps/epoch.go (EpochSource, EpochFile, OpenEpochFile, Current, Path); builds, vet clean.

- [x] 1.5 The writer's late check.
  - Files: `gateway/internal/deps/deps.go`
  - Do: as design §3. `SetEpochSource(src EpochSource)` stores the source atomically. `LateDiscards() int64`.
    A helper `tombstone(ids ...string)` holds the copy-and-swap, and `applyInvalidation` uses it too. At the
    top of `applyRegistration`: if a source is set, and `Current()` errors or differs from `r.DatasetEpoch`,
    then tombstone `r.EntryID`, call `m.purge.PurgeEntry(ctx, r.EntryID, r.T1Key)` (an error goes through
    `purgeFailed`), `lateDiscards.Add(1)`, log the entry and both epochs, and return. `New`'s signature does
    not change.
  - Run: `cd gateway && go build ./... && go vet ./internal/deps/ && go test -count=1 -v ./internal/deps/ 2>&1 | grep -E "^(--- |ok|FAIL)"`
  - Pass: every 4.1 deps test prints `--- PASS`; no `--- SKIP`; `ok`.
  - Result: deps.go gained SetEpochSource, LateDiscards, tombstone() and the late check in applyRegistration; all 11 4.1 deps tests PASS, no SKIP, ok.

- [x] 1.6 The guard in the write-back.
  - Files: `gateway/internal/httpapi/handler.go`
  - Do: as design §3. `epochSource` interface, `var _ epochSource = (*deps.EpochFile)(nil)`, `Epoch epochSource`
    field (comment: nil turns the guard off; `cmd/gateway` always sets it, DC 9). `generation.Discarded`. The
    guard in the closure after `writeNS` and before `h.Cache.Put`: on an error or a mismatch, set
    `rec.WritebackDisc = true`, log `request_id` with both epochs or the error, and return a generation with
    `Discarded: true` and no `EntryID`. No `Put`, `PutTier2`, `Register`, `touch` or `TrimToCapacity` on that
    path. After `Do`, when `gen.Discarded`: `rec.EntryID, rec.EntrySources = "", nil`. The response does not
    change.
  - Run: `cd gateway && go build ./... && go test -count=1 ./internal/httpapi/`
  - Pass: builds; every existing httpapi test passes (they leave `Epoch` nil).
  - Result: handler.go gained epochSource, Handler.Epoch, generation.Discarded, the guard in the closure and the entry_id "" rewrite; builds, existing httpapi tests ok.

- [x] 1.7 The record field's comment.
  - Files: `gateway/internal/telemetry/evallog.go`
  - Do: on `WritebackDisc`, a comment saying true iff this request's own write-back was discarded by the
    epoch guard; never on a coalesced follower; the record then has `entry_id ""`; §H v0.18.
  - Run: `cd gateway && go build ./... && go test -count=1 ./internal/telemetry/`
  - Pass: builds; telemetry tests pass.
  - Result: comment added on WritebackDisc in evallog.go (gofmt re-aligned the neighbouring field block, whitespace only); builds, telemetry tests ok.

- [x] 1.8 Wire the epoch in `main`.
  - Files: `gateway/cmd/gateway/main.go`
  - Do:
    - `func epochFromEnv(lookup func(string) (string, bool)) (*deps.EpochFile, uint64, error)`: unset or empty
      gives an error naming `DATASET_EPOCH_FILE`; otherwise `deps.OpenEpochFile`. A doc comment in the style
      of `bandFromEnv`.
    - Call `epochFile, epochNow, err := epochFromEnv(os.LookupEnv)` right after the `bandFromEnv` block;
      `log.Fatalf` on error; then `log.Printf("gateway: dataset_epoch_file=%s epoch=%d (ADR-008)", …)`.
    - After `depMap := deps.New(rdb, store, 1024)`: `depMap.SetEpochSource(epochFile)`. After the handler is
      built: `handler.Epoch = epochFile`.
    - At shutdown, after the dependency-map counters: if `depMap.LateDiscards() > 0`, log it as discarded
      write-backs (the epoch advanced before registration), not as incompleteness.
  - Run: `cd gateway && go build ./... && go vet ./cmd/gateway/ && go test -count=1 -v ./cmd/gateway/ 2>&1 | grep -E "^(--- |ok|FAIL)"`
  - Pass: builds; vet clean; every existing cmd/gateway test passes, including `TestBandFromEnvRunsBeforeSideEffects`
    and `TestMainWiresDeps`.
  - Result: main.go gained epochFromEnv, the start-up read and log, SetEpochSource, handler.Epoch and the LateDiscards shutdown line; builds, vet clean, 13 cmd/gateway tests PASS incl. TestBandFromEnvRunsBeforeSideEffects and TestMainWiresDeps.

- [x] 1.9 Makefile and `.gitignore`.
  - Files: `Makefile`, `.gitignore`
  - Do:
    - Makefile, after the `OLLAMA_NUM_PARALLEL` export block: `DATASET_EPOCH_FILE ?= $(CURDIR)/data/dataset-epoch`
      and `export DATASET_EPOCH_FILE`, with a comment (ADR-008; absolute because the two services run from
      different directories; every recipe, `seam-check`'s `rag.server` included, inherits it).
    - Target `epoch-advance: ## Item 4.2: advance the dataset epoch (ADR-008); creates the file at 1`, running
      `cd $(RAG) && $(PY) -m rag.epoch advance`.
    - Target `epoch-race-check: ## Item 4.2 DC 10: …` that prints the memory pressure level like `seam-check`,
      then runs `$(PY) experiments/scripts/epoch_race_check.py --evidence-dir $(EVIDENCE)`, with
      `EVIDENCE ?= docs/work/2026-10-28-epoch-guard/evidence/race`.
    - `.gitignore`, in the corpus section: `data/dataset-epoch` and `data/dataset-epoch.lock`.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make help | grep -E "epoch-(advance|race-check)" && make -n epoch-advance && grep -n "export DATASET_EPOCH_FILE" Makefile`
  - Pass: both targets listed; the dry run shows `python3 -m rag.epoch advance`; the export line exists.
  - Result: Makefile has the exported DATASET_EPOCH_FILE, epoch-advance, epoch-race-check (and both added to .PHONY); .gitignore lists the file and its lock; help lists both, dry run shows `cd rag && python3 -m rag.epoch advance`.

- [x] 1.10 Create the real epoch file.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make epoch-advance && cat data/dataset-epoch && git status --porcelain data/`
  - Pass: prints the path and `1` (the corpus in Redis was ingested before the file existed); `git status`
    shows nothing new under `data/`.
  - Result: created data/dataset-epoch at 1 (printed `dataset_epoch_file=/Users/hung/Desktop/Sem1/thesis/data/dataset-epoch epoch=1`); git status --porcelain data/ prints nothing.

- [x] 1.11 The live-check script.
  - Files: `experiments/scripts/epoch_race_check.py` (new)
  - Do: design §3, steps 1–8 under "the live check". Use the `redis` Python package already in the rag
    environment and `subprocess`. Ports `127.0.0.1:50053` (rag.server) and `127.0.0.1:18080` (gateway),
    `MUTATION=on`, a temp `DATASET_EPOCH_FILE` at 1, a temp `RESULTS_DIR` and `RUN_ID`. Refuse to start if
    either port is taken. It prints one PASS or FAIL line per check, and exits non-zero on any FAIL, or with
    "race not forced". Cleanup deletes only A's keys and **never** calls `FLUSHDB`. Do not run it here.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && python3 -m py_compile experiments/scripts/epoch_race_check.py && python3 experiments/scripts/epoch_race_check.py --help && ruff check experiments/scripts/epoch_race_check.py && grep -c -i "flushdb" experiments/scripts/epoch_race_check.py`
  - Pass: compiles; `--help` prints; ruff clean; the `flushdb` count is 0, or every hit is a comment saying never.
  - Result: added experiments/scripts/epoch_race_check.py (not run); compiles, --help prints, ruff clean; 3 `flushdb` hits, all comments saying never.

- [x] 1.12 Contract to v0.18.
  - Files: `docs/contracts/interfaces.md`
  - Do:
    - Line 3: `Draft v0.17` → `Draft v0.18`.
    - §E: replace the `dataset:epoch` block and its v0.17 note with the epoch file. Cover:
      `DATASET_EPOCH_FILE`, absolute, one decimal integer ≥ 1, 0 means not read; who reads it (Python first in
      each RPC, the gateway at write-back, the deps writer at registration); who advances it (ingest, and
      the edit in item 4.4) and how (lock, temp file, rename); the start-up refusal on both sides; the guard
      (any mismatch or a read error discards: no tier write, no registration); the two order rules; the late
      rule and `LateDiscards`.
    - §B: no change.
    - §H: rewrite the `writeback_discarded` row. True iff this request's own write-back was discarded; never
      on a coalesced follower; the record then has `entry_id ""` and `entry_sources` null; a late discard is
      not in any record and is counted in the gateway's shutdown line. Add invariant **I13**: under
      `mutation: off`, `writeback_discarded` is never true.
    - Versioning: `Current version` → v0.18 (2026-10-28), and a new top row stating these, with no wire or
      `.proto` change.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && grep -n "v0.18\|DATASET_EPOCH_FILE\|I13\|LateDiscards" docs/contracts/interfaces.md | cut -c1-120 && grep -n "KEY   dataset:epoch" docs/contracts/interfaces.md`
  - Pass: header, §E file text, §H row, I13 and the version row appear; the last grep prints nothing.
  - Result: interfaces.md is v0.18: §E file/guard/order rules/late rule, §H writeback_discarded row + entry_id clause + I13, version row; header, §E, I13 and version row appear, `KEY   dataset:epoch` grep empty.

- [x] 1.13 Architecture, the Redis notes, and the 4.4 hand-off.
  - Files: `docs/architecture.md`, `docs/Redis-Data Structure.md`, `docs/super-plan.md`
  - Do:
    - `architecture.md`: the "The epoch is a constant" bullet (it is built: the file, the guard, the late
      check); invariant 4 (built in item 4.2); the "Not built" row (remove the epoch guard); the "C2's
      dependency map … The epoch guard is not (item 4.2)" sentence.
    - `Redis-Data Structure.md`: §8's "(item 4.2, not built)" line, the ADR-008 paragraph's "Today the epoch is
      the constant `DATASET_EPOCH_STUB = 0`…" sentence, the "Not built yet (item 4.2)" line, the
      `dataset_epoch` rows that say "Always `0` today" / "Stub `0` today", and §1's "guard is not built yet
      (item 4.2)" line.
    - `super-plan.md` row 4.4: add one sentence. Its design must test the edit order (new text, then advance
      the epoch, then invalidate), because a wrong order lets a stale write-back pass with no trace (item
      4.2, design §3 failure mode 10).
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && grep -n "4.2" docs/architecture.md "docs/Redis-Data Structure.md" | grep -i "not built\|stub\|constant"; grep -n "^| 4.4 " docs/super-plan.md | grep -c "edit order"`
  - Pass: the first grep prints nothing; the second prints 1.
  - Result: architecture.md, Redis-Data Structure.md and super-plan row 4.4 updated; first grep prints nothing, second prints 1. Also changed in the Redis notes: the example record's dataset_epoch 0 to 1, and known-gap 4 (it said §E names a Redis key; v0.18 removed that).

## Phase 2 — Unit tests

- [x] 2.1 Python: the epoch file and the start-up check (DC 1, DC 8).
  - Files: `rag/tests/test_epoch.py` (new)
  - Do: each test sets `DATASET_EPOCH_FILE` with `monkeypatch.setenv` to a file under `tmp_path`, or
    `delenv`. Tests:
    - `test_advance_creates_a_missing_file_at_one`
    - `test_advance_increments_and_leaves_no_temp_file`
    - `test_concurrent_advances_lose_nothing`: 8 threads × 25 advances end at 200.
    - `test_advance_refuses_a_corrupt_file`: it raises, and the file is unchanged.
    - `test_read_returns_the_value`, with a trailing newline.
    - `test_read_returns_not_read_on_failure`, parametrized: unset, empty, missing, `abc`, `0`, `-3`.
    - `test_check_refuses`, parametrized: unset, empty, relative, missing, `abc`, `0`.
    - `test_check_accepts_a_valid_file`
    - `test_serve_refuses_before_binding`: patch `server.build_server` to record calls; with a bad
      environment, `server.serve()` raises `EpochError` and `build_server` was never called.
  - Run: `cd rag && python3 -m pytest -v tests/test_epoch.py`
  - Pass: every test above `PASSED`; none `SKIPPED`.
  - Result: added rag/tests/test_epoch.py; 21 PASSED (parametrized cases included), none SKIPPED, ruff clean.

- [x] 2.2 Python: read first, on every path (DC 2).
  - Files: `rag/tests/test_server_epoch.py` (new)
  - Do: the epoch file holds 41. Patched `retrieve.retrieve` / `retrieve.fetch_by_ids` return a decoy epoch
    999 and append `"texts"` to an order list. A wrapper around `epoch.read` appends `"epoch"`.
    `generate.generate` is patched to return a fixed string. Tests:
    - `test_retrieve_stamps_the_epoch_read_first`
    - `test_answer_with_ids_stamps_the_epoch_read_first`
    - `test_answer_without_ids_stamps_the_epoch_read_first`

    Each checks `dataset_epoch == 41` and that the order starts `["epoch", "texts"]`. Also:
    - `test_fetch_by_ids_reads_the_epoch_before_the_texts`: a fake Redis client from
      `store.get_redis_client` records `hmget`.
    - `test_retrieve_reads_the_epoch_before_the_index`: `store.get_vector_store` records, then raises a
      sentinel.
    - `test_ingest_advances_after_writing_the_index`: patch `ingest.load_records`, `ingest._write_index`,
      `epoch.require_path` and `epoch.advance`. The order is `require_path`, `_write_index`, `advance`.
  - Run: `cd rag && python3 -m pytest -v tests/test_server_epoch.py`
  - Pass: every test above `PASSED`; none `SKIPPED`.
  - Result: added rag/tests/test_server_epoch.py; 6 PASSED, none SKIPPED; a temporary swap of the read order in Retrieve made the order test fail, then restored.

- [x] 2.3 Go: the reader (DC 1, DC 8).
  - Files: `gateway/internal/deps/epoch_test.go` (new)
  - Do (no Redis):
    - `TestEpochFileRereadsEveryCall`: write 3, `Current` → 3; rewrite 4, `Current` → 4.
    - `TestEpochFileOpenRefuses`, a table: relative, missing, `abc`, `0`, `""`, `-1`.
    - `TestEpochFileOpenAcceptsTrailingNewline`.
  - Run: `cd gateway && go test -count=1 -v -run TestEpochFile ./internal/deps/`
  - Pass: the three tests `--- PASS`.
  - Result: added gateway/internal/deps/epoch_test.go; the three tests PASS (the refuse table has 6 subtests PASS).

- [x] 2.4 Go: the late registration (DC 7).
  - Files: `gateway/internal/deps/late_test.go` (new, `package deps`)
  - Do: use 4.1's `testRedis`, `newMap`, `seedEntry`, `barrier`, `exists`, `inLRU`, `realPurger`, and a small
    fake `EpochSource` (value, error). Tests:
    - `TestLateRegistrationIsPurged`: `seedEntry(E, "t1:k", withT2 true)`, source at 8, `Register(E, sources
      {A, B}, T1Key "t1:k", DatasetEpoch 7)`, barrier. Then no `t1:k`, `t2:E`, `entry:E`, `dep:A`, `dep:B`;
      not in LRU; `Invalidated(E)`; `LateDiscards() == 1`.
    - `TestLateRegistrationReadErrorPurges`: the source returns an error; the same result.
    - `TestLateRegistrationCurrentEpochIsKept`: source at 7; `dep:A`, `dep:B` and `entry:E` exist;
      `LateDiscards() == 0`; not `Invalidated`.
  - Run: `cd gateway && go test -count=1 -v -run TestLateRegistration ./internal/deps/`
  - Pass: three `--- PASS`; no `--- SKIP`.
  - Result: added gateway/internal/deps/late_test.go; three tests PASS against Redis DB 14, no SKIP. (FT._LIST is empty afterwards: the known FLUSHDB-drops-indexes hazard, 4.1 design section 4.)

- [x] 2.5 Go: start-up (DC 8).
  - Files: `gateway/cmd/gateway/epoch_env_test.go` (new)
  - Do: `TestEpochFromEnv`, a table using `lookupFrom` from `lane_env_test.go`: unset, empty, relative,
    missing, `abc`, `0` → error; a valid temp file → its path and value. `TestEpochFromEnvRunsBeforeSideEffects`
    follows `TestBandFromEnvRunsBeforeSideEffects`: `epochFromEnv(os.LookupEnv)` comes before
    `redis.NewClient(`, `ragclient.New(` and `telemetry.Open(`, and `dataset_epoch_file=` is logged.
  - Run: `cd gateway && go test -count=1 -v -run TestEpochFromEnv ./cmd/gateway/`
  - Pass: both tests `--- PASS`.
  - Result: added gateway/cmd/gateway/epoch_env_test.go; TestEpochFromEnv (7 subtests) and TestEpochFromEnvRunsBeforeSideEffects PASS.

- [x] 2.6 Go: the wiring (DC 9).
  - Files: `gateway/cmd/gateway/epoch_wiring_test.go` (new)
  - Do: `TestMainWiresEpoch`. Read `main.go` and drop the lines whose trimmed text starts with `//`. Then
    require, in this order:
    - `epochFile, epochNow, err := epochFromEnv(os.LookupEnv)`;
    - `depMap := deps.New(` before `depMap.SetEpochSource(epochFile)`;
    - `httpapi.NewHandler(` before `handler.Epoch = epochFile`;
    - `depMap.LateDiscards()` before `finishRun(evalLog)`.

    The test fails if any of these is missing.
  - Run: `cd gateway && go test -count=1 -v -run TestMainWiresEpoch ./cmd/gateway/`
  - Pass: `--- PASS`.
  - Result: added gateway/cmd/gateway/epoch_wiring_test.go; TestMainWiresEpoch PASS.

## Phase 3 — Integration tests

- [x] 3.1 `httpapi`: the guard on the request path (DC 3, 4, 5, 6).
  - Files: `gateway/internal/httpapi/epoch_guard_test.go` (new)
  - Do: a `fakeEpoch` (mutex, value, error). Each test: `hs := newHarness(t, 1, 0)`, `fd := newFakeDeps()`,
    `hs.h.Deps = fd`, `hs.h.Epoch = …`, `hs.embedFresh(q)`, then ask and read the record. Tests:
    - `TestEpochGuardDiscardsAdvancedEpoch`: source `testEpoch+1`. The response carries the answer. The
      record has `cache` `MISS`, `writeback_discarded` true, `entry_id` `""`, `entry_sources` null.
      `callCount("Put")` and `callCount("PutTier2")` are 0, and there are no registrations, no touches and no
      trims.
    - `TestEpochGuardDiscardsOlderEpoch`: source `testEpoch-1`; the same result.
    - `TestEpochGuardKeepsEqualEpoch`: source `testEpoch`. One `Put`, one `PutTier2`, one registration,
      `writeback_discarded` false, `entry_id` non-empty.
    - `TestEpochGuardOffWithoutSource`: `Epoch` nil; written back, false.
    - `TestEpochGuardFailsClosedOnReadError`: the source errors; discarded, true.
    - `TestEpochGuardFlagsLeaderOnly`: `holdAnswers()`, then a leader and a coalesced follower on one
      question, then open the gate. The leader's record is true, the follower's (`coalesced` true) is false,
      both have `entry_id` `""`, and both responses carry the answer.
  - Run: `cd gateway && go test -count=1 -v -run TestEpochGuard ./internal/httpapi/`
  - Pass: six `--- PASS`.
  - Result: added gateway/internal/httpapi/epoch_guard_test.go; six TestEpochGuard tests PASS; a temporary change of the compare to 'now > stamped' made the older-epoch test fail, then restored.

## Phase 4 — Run and verify

Run every step alone, in order. Nothing else may touch Redis while a step runs.

- [x] 4.1 `redis-cli PING` → `PONG`, then `make verify`.
  - Pass: exit 0; no FAIL; any SKIPPED target listed by name.
  - Result: PONG, then make verify (Go test cache cleared first, run alone) exit 0: ruff All checks passed, Go packages ok, pytest 50 passed, experiments 731 passed; no FAIL, no SKIPPED target. Output: evidence/verify.out.
- [x] 4.2 DC 1 — `cd rag && python3 -m pytest -v tests/test_epoch.py -k "advance or read"`;
  `cd gateway && go test -count=1 -v -run TestEpochFile ./internal/deps/`;
  `grep -rn "DATASET_EPOCH_STUB\|dataset:epoch" rag/src gateway --include='*.py' --include='*.go'`
  - Pass: all `PASSED` / `--- PASS`; the grep prints nothing.
  - Result: pytest -k 'advance or read': 13 passed, 8 deselected; TestEpochFile tests (3, 6 subtests) --- PASS; the grep printed nothing (exit 1).
- [x] 4.3 DC 2 — `cd rag && python3 -m pytest -v tests/test_server_epoch.py`
  - Pass: six `PASSED`.
  - Result: test_server_epoch.py: six PASSED, none SKIPPED.
- [x] 4.4 DC 3–6 — `cd gateway && go test -count=1 -v -run TestEpochGuard ./internal/httpapi/`
  - Pass: six `--- PASS`.
  - Result: six TestEpochGuard tests --- PASS (DC 3-6).
- [x] 4.5 DC 7 — `cd gateway && go test -count=1 -v -run TestLateRegistration ./internal/deps/`
  - Pass: three `--- PASS`; no `--- SKIP`.
  - Result: three TestLateRegistration tests --- PASS on Redis DB 14, no SKIP (DC 7).
- [x] 4.6 DC 8 — `cd gateway && go test -count=1 -v -run TestEpochFromEnv ./cmd/gateway/`;
  `cd rag && python3 -m pytest -v tests/test_epoch.py -k "check or serve"`
  - Pass: two `--- PASS`; every selected test `PASSED`.
  - Result: TestEpochFromEnv and TestEpochFromEnvRunsBeforeSideEffects --- PASS; pytest -k 'check or serve': 8 passed, 13 deselected (DC 8).
- [x] 4.7 DC 9 — `cd gateway && go test -count=1 -v -run TestMainWiresEpoch ./cmd/gateway/`
  - Pass: `--- PASS`.
  - Result: TestMainWiresEpoch --- PASS (DC 9).
- [x] 4.8 DC 10 — the live race. `citable: no`. **Loads the LLM.**
  - Before running, check all of these:
    - `sysctl kern.memorystatus_vm_pressure_level` is 1 or 2; at 4, stop and report.
    - `redis-cli PING` answers `PONG`.
    - `curl -s localhost:11434/api/version` answers.
    - Nothing else is running.
  - Then run: `make epoch-race-check`.
  - Pass:
    - exit 0;
    - every check line PASS;
    - `evidence/race/` holds both records, the key diff, both logs and the pressure level;
    - the report states the pressure level next to the result.
  - A "race not forced" result is the timing miss in design §3 Unknowns. Re-run once. A second miss is a
    failed step.
  - Result: make epoch-race-check exit 0 on the first attempt, all 16 check lines PASS (B: MISS, writeback_discarded true, entry_id empty, entry_sources null, 7.8 s generation, advance at +1.5 s; no t1:/t2:/entry: key appeared); memory pressure level 2 (yellow) before and after, citable: no. Evidence: evidence/race/ and evidence/race-make-attempt1.out.
- [x] 4.9 DC 11 — `grep -n "v0.18\|DATASET_EPOCH_FILE\|I13" docs/contracts/interfaces.md | cut -c1-100`;
  `grep -n "4.2" docs/architecture.md "docs/Redis-Data Structure.md" | grep -i "not built\|stub\|constant"`;
  `grep -n "^| 4.4 " docs/super-plan.md | grep -c "edit order"`
  - Pass: the v0.18 header, §E, §H row, I13 and version row appear; the second grep is empty; the count is 1.
  - Result: v0.18 header (line 3), section E file text (lines 468-486), section H row (699), I13 (715) and version rows (735, 739) appear; second grep prints nothing; edit-order count is 1.
- [x] 4.10 DC 12 — `make verify` passed in 4.1, with Redis up. Record any SKIPPED names.
  - Result: same run as 4.1: make verify exit 0 with Redis up; no SKIPPED target (ruff and both pytest runs executed).
- [x] 4.11 DC 13 — `git status --porcelain -- '*_test.go' 'rag/tests/*'` and
  `cd /Users/hung/Desktop/Sem1/thesis && shasum -a 256 -c docs/work/2026-10-28-epoch-guard/evidence/test-hashes-before.txt | grep -v ": OK$"`
  - Pass: every git line starts with `??` or `A `; the shasum filter prints nothing.
  - Result: git status shows only ?? lines (12 test files, all new); shasum -c on test-hashes-before.txt: 62 OK, filter printed nothing.

## Phase 5 — Changes asked for at review (2026-10-28)

The human approved two stale-text fixes at review. Both are a comment or a status line, so the main session
made them, and no behaviour changed.

- [x] 5.1 `deps/doc.go`: replace "The epoch guard is item 4.2, not here" with what 4.2 added to `deps`.
  - Files: `gateway/internal/deps/doc.go`
  - Run: `make verify` (alone, Go test cache cleared), then the 4.11 hash check.
  - Result: see the Result line of 5.3.
- [x] 5.2 ADR-008: the index row says it is built in 4.2, and a dated "Built" note goes under its header.
  The decision text is unchanged.
  - Files: `docs/decisions.md`
  - Run: `grep -n "^| ADR-008" docs/decisions.md`
  - Result: the row says "built in item 4.2, 2026-10-28"; the note is above the unchanged first paragraph.
- [x] 5.3 Re-check after 5.1–5.2.
  - Result: `make verify` alone, Go test cache cleared: exit 0, 9 Go packages ok, 50 + 731 pytest passed, ruff clean, no SKIP (`evidence/verify-review.out`); the 4.11 hash check prints no changed file.
