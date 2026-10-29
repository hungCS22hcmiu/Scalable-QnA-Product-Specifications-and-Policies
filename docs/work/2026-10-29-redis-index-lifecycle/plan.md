# Plan — Redis index lifecycle: the Go tests and the live services share one server

Design: design.md (approved 2026-10-29). A bugfix: each problem's failing witness comes before its fix.

**Before any step:** `redis-cli PING` answers `PONG`. Run **one command at a time**: no Redis test, `make`
target or check runs in parallel with another.
- **Until Phase 2 is done,** any `go test` of `cache` or `deps` drops the live `idx:corpus` and `idx:cache`.
  That is the bug. `idx:corpus` is rebuilt on the next RAG read (it waits since 4.3), and the gateway is not
  running.
- **The only edits to existing test files** are the two helpers, approved on 2026-10-29: `testStore` in
  `cache/capacity_test.go` and `testRedis` in `deps/deps_test.go`. Nothing else in an existing test changes.
- `go test -run` exits 0 when nothing matches, so every test step uses `-v`, and its Pass line names the
  tests. A `--- SKIP` is a failed step.
- The steps that load the embedding model are `make test` / `make verify` (the RAG tests) and step 1.1's
  rebuild of `idx:corpus`. Check `sysctl kern.memorystatus_vm_pressure_level` first: 1 or 2 may proceed
  (`citable: no`; write the level next to the result), 4 stops.

## Phase 1 — The failing witness for problem 2

- [x] 1.1 The isolation check, against today's set-up.
  - Files: `Makefile`
  - Do: add `test-isolation-check: ## Bugfix 2026-10-29: the Go tests must not drop the live server's indexes`.
    For now it does five things:
    1. drop a stale `idx:gotest-sentinel` if one exists;
    2. `redis-cli FT.CREATE idx:gotest-sentinel ON HASH PREFIX 1 gotest-sentinel-nomatch: SCHEMA f TEXT`;
    3. run `cd $(GATEWAY) && go test -count=1 ./internal/cache/ ./internal/deps/` (today's command);
    4. check that `redis-cli FT._LIST` still lists the sentinel, and drop it without `DD`;
    5. exit non-zero if it was gone.

    Phase 2 rewires it.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && redis-cli FT._LIST; make test-isolation-check > docs/work/2026-10-29-redis-index-lifecycle/evidence/isolation-before.out 2>&1; echo "exit=$?"; tail -5 docs/work/2026-10-29-redis-index-lifecycle/evidence/isolation-before.out; redis-cli FT._LIST`
  - Pass: **it FAILS** (`exit` non-zero), because the sentinel is gone after the Go tests: the reason in §1.
    The second `FT._LIST` is empty.
  - Result: added `test-isolation-check` to Makefile; exit=2 (sentinel gone, cache and deps tests both `ok`), `idx:corpus` before and nothing after; evidence/isolation-before.out; pressure 2.

## Phase 2 — Fix problem 2: the tests get their own Redis

- [x] 2.1 The test-only package.
  - Files: `gateway/internal/testredis/testredis.go` (new)
  - Do: exactly design §3: `EnvAddr`, `EnvRequired`, `Client(t testing.TB, db int)` (read → ping →
    `CheckNotLive` → `FLUSHDB` + cleanup, in that order), and `CheckNotLive(ctx, rdb)` (read-only). The doc
    comment states the RCA's two facts.
  - Run: `cd gateway && go build ./... && go vet ./internal/testredis/`
  - Pass: builds; vet clean.
  - Result: added gateway/internal/testredis/testredis.go (EnvAddr, EnvRequired, Client, CheckNotLive); build and vet clean, gofmt clean.

- [x] 2.2 The two approved helper edits.
  - Files: `gateway/internal/cache/capacity_test.go` (`testStore` and its comment only),
    `gateway/internal/deps/deps_test.go` (`testRedis` and its comment only).
  - Do: replace each helper's address, ping, skip and first `FLUSHDB` with `testredis.Client(t, 15)` /
    `testredis.Client(t, 14)`. Keep its name, its signature and what it returns. Rewrite its comment to the
    true premise (design §3). Touch no other line in either file.
  - Run: `cd gateway && go build ./... && go vet ./internal/cache/ ./internal/deps/ && git diff --stat -- '*_test.go'`
  - Pass: builds; vet clean; the diff lists only these two files.
  - Result: testStore and testRedis now call testredis.Client(t, 15/14), comments rewritten, one import swapped per file; build and vet clean, diff stat lists only capacity_test.go and deps_test.go.

- [x] 2.3 `make test` starts and stops the test Redis.
  - Files: `Makefile`
  - Do: as design §3:
    - `TEST_REDIS_PORT ?= 6390`, `REDISEARCH_SO` (derived from the real path of `redis-server`),
      `GO_TEST_PKGS ?= ./...` and `GO_TEST_FLAGS ?=`;
    - the `test-go` target, with the steps of §3, the sentinel included and the stop in a `trap`;
    - `test` calls `test-go`, then the two pytest steps as now;
    - `test-isolation-check` becomes an alias of `test-go`;
    - all three targets go in `.PHONY` if the file uses it.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make help | grep -E "test-go|test-isolation-check" && grep -n "go test -p 1" Makefile`
  - Pass: both targets are listed; the grep prints the line.
  - Result: Makefile now has test-go (sentinel, test server on 6390 with trap, `go test -p 1`), test-isolation-check as its alias, `test` calling test-go; both targets in `make help`, grep prints Makefile:342.

- [x] 2.4 The witness passes now.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && redis-cli FT._LIST; make test-isolation-check GO_TEST_FLAGS=-count=1 > docs/work/2026-10-29-redis-index-lifecycle/evidence/isolation-after.out 2>&1; echo "exit=$?"; grep -E "^(ok|FAIL|---)" docs/work/2026-10-29-redis-index-lifecycle/evidence/isolation-after.out | head -20; redis-cli FT._LIST; lsof -nP -iTCP:6390 -sTCP:LISTEN`
  - Pass:
    - `exit=0`, and every Go package is `ok`;
    - `FT._LIST` after the run is the same as before it: no new index, and no lost index;
    - nothing listens on 6390;
    - the output has no `--- SKIP`;
    - record the run time.
  - Result: exit=0, 12 s wall clock, all packages ok, no SKIP, nothing on 6390; FT._LIST empty before and after (1.1 had already dropped idx:corpus, so "no lost index" is weak here; 6.2 re-checks); evidence/isolation-after.out; pressure 2.

- [x] 2.5 The guard tests (DC 3).
  - Files: `gateway/internal/testredis/testredis_test.go` (new)
  - Do: use a raw client on `EnvAddr`, and skip the same way `Client` does when it is unset. Tests:
    - `TestCheckNotLiveAcceptsACleanServer`;
    - `TestCheckNotLiveRefusesAnIndex`: create a throwaway index on DB 0, assert an error, drop it without `DD`;
    - `TestCheckNotLiveRefusesDB0Keys`: one key in DB 0, assert an error, delete it;
    - `TestClientChecksBeforeFlushing`: read `testredis.go`, drop its comment lines, and require that
      `CheckNotLive(` comes before `FlushDB(` inside `Client`.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make test-go GO_TEST_PKGS=./internal/testredis/ GO_TEST_FLAGS='-count=1 -v'`
  - Pass: four `--- PASS`; no `--- SKIP`.
  - Result: added gateway/internal/testredis/testredis_test.go; four `--- PASS`, no SKIP, exit=0, nothing left on 6390; pressure 2 (no model).

## Phase 3 — Problem 3: the failing test, then the start-up wait

- [x] 3.1 The failing test.
  - Files: `gateway/internal/cache/tier2_index_ready_test.go` (new)
  - Do: `TestEnsureCacheIndexReturnsOnlyWhenIndexed`, on `testredis.Client(t, 0)`:
    - seed 1000 `t2:*` hashes with 768-dim float32 vectors and the schema's fields, plus about 500 filler
      keys;
    - call `EnsureCacheIndex`;
    - at once, `FTInfo` must show `Indexing == 0` and `NumDocs == 1000`, and `NearestTier2InNamespace` on
      one seeded vector, in its namespace, must return that entry;
    - cleanup drops `idx:cache` without `DD`.

    Also `TestEnsureCacheIndexWaitsWhenItAlreadyExists`: the same, but it sends a raw `FT.CREATE` first,
    then calls `EnsureCacheIndex` while the scan runs. Do not touch `tier2.go` yet.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make test-go GO_TEST_PKGS=./internal/cache/ GO_TEST_FLAGS="-count=1 -v -run TestEnsureCacheIndex" > docs/work/2026-10-29-redis-index-lifecycle/evidence/index-ready-before.out 2>&1; echo "exit=$?"; grep -E "^(--- |ok|FAIL)|Indexing|NumDocs" docs/work/2026-10-29-redis-index-lifecycle/evidence/index-ready-before.out | head`
  - Pass: **both tests FAIL**, because `Indexing` is 1 or `NumDocs` is below 1000 (the reason in §1), not
    because of a set-up error. Nothing listens on 6390 afterwards.
  - Result: added cache/tier2_index_ready_test.go; both tests FAIL on `Indexing = 1`, `NumDocs` 0 and 2 (want 1000), and the KNN returns []; no set-up error, 6390 free; evidence/index-ready-before.out; pressure 1.

- [x] 3.2 The fix.
  - Files: `gateway/internal/cache/tier2.go`, `gateway/cmd/gateway/main.go` (the comment only)
  - Do: as design §3: "already exists" goes on to the wait; add `waitIndexed`, and
    `indexReadyTimeout = 10 * time.Second`. A comment says why, pointing to this trail's §1. Update the
    comment at the `EnsureCacheIndex` call in `main.go`.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && make test-go GO_TEST_PKGS=./internal/cache/ GO_TEST_FLAGS="-count=1 -v -run TestEnsureCacheIndex" > docs/work/2026-10-29-redis-index-lifecycle/evidence/index-ready-after.out 2>&1; echo "exit=$?"; grep -E "^(--- |ok|FAIL)" docs/work/2026-10-29-redis-index-lifecycle/evidence/index-ready-after.out`
  - Pass: `exit=0`; both tests `--- PASS`.
  - Result: tier2.go: "already exists" now goes on to `waitIndexed` (new, 10 s `indexReadyTimeout`, 5 ms poll); main.go comment updated; both tests `--- PASS`, exit=0, 6390 free; evidence/index-ready-after.out; pressure 1.

- [x] 3.3 The wait's own unit tests.
  - Files: `gateway/internal/cache/wait_indexed_test.go` (new, no Redis)
  - Do: these use a fake `info` func:
    - `TestWaitIndexedReturnsWhenComplete`;
    - `TestWaitIndexedTimesOut`: always `Indexing` 1. It returns an error after at least the timeout, and the
      error names the last values;
    - `TestWaitIndexedIsNotFooledByZeroValues`: `Indexing` 0 with `PercentIndexed` 0. It is not ready, so it
      times out;
    - `TestWaitIndexedReturnsReadErrors`.
  - Run: `cd gateway && go test -count=1 -v -run TestWaitIndexed ./internal/cache/`
  - Pass: four `--- PASS`.
  - Result: added cache/wait_indexed_test.go (fake FT.INFO, no Redis); four `--- PASS`, exit=0.

## Phase 4 — Run rule 12: a Tier-2 search error voids the run

- [x] 4.1 The record key, and the log's count.
  - Files: `gateway/internal/telemetry/evallog.go`
  - Do: as design §3: `Tier2SearchFailed bool` with `json:"tier2_search_failed,omitempty"`; the counter,
    incremented where a record is accepted; `Tier2SearchFailures() int64`.
  - Run: `cd gateway && go build ./... && go test -count=1 ./internal/telemetry/`
  - Pass: builds; the existing telemetry tests pass.
  - Result: evallog.go: `Record.Tier2SearchFailed` (`tier2_search_failed,omitempty`), `tier2SearchFailures` counted in `Log` before the enqueue, `Tier2SearchFailures()`; build ok, telemetry tests ok, gofmt clean.

- [x] 4.2 Mark the record on the request path.
  - Files: `gateway/internal/httpapi/cascade.go`, `gateway/internal/httpapi/handler.go`
  - Do: `tier2Outcome.SearchFailed`, set in the existing search-error branch, which still degrades to a
    MISS. Then `rec.Tier2SearchFailed = t2.SearchFailed`.
  - Run: `cd gateway && go build ./... && go test -count=1 ./internal/httpapi/`
  - Pass: `ok` (the httpapi tests use fakes, no Redis). `TestCauseIsNullOnEveryExitWithNoCandidate` is
    included and passes unchanged.
  - Result: cascade.go `tier2Outcome.SearchFailed` set in the search-error branch (still a MISS), handler.go `rec.Tier2SearchFailed = t2.SearchFailed`; httpapi `ok`, TestCauseIsNullOnEveryExitWithNoCandidate PASS with its 3 subtests, 0 SKIP.

- [x] 4.3 `incomplete()` refuses the run.
  - Files: `gateway/cmd/gateway/main.go`
  - Do: `runCounts.Tier2SearchFailures`, filled in `finishRun` from `l.Tier2SearchFailures()`, and the reason
    in `incomplete()` naming the count and §H rule 12.
  - Run: `cd gateway && go build ./... && go vet ./cmd/gateway/ && go test -count=1 ./cmd/gateway/`
  - Pass: builds; vet clean; every existing `cmd/gateway` test passes.
  - Result: main.go: `runCounts.Tier2SearchFailures`, filled in `finishRun` after Close, reason "N request(s) hit a Tier-2 search error (interfaces.md §H rule 12)" in `incomplete()`; build, vet, gofmt clean; cmd/gateway `ok`.

- [x] 4.4 The tests for rule 12 (DC 6).
  - Files: `gateway/internal/httpapi/tier2_search_error_test.go`, `gateway/internal/telemetry/tier2_search_error_test.go`,
    `gateway/cmd/gateway/tier2_search_error_test.go` (all new; no Redis).
  - Do:
    - httpapi, `TestTier2SearchErrorMarksTheRecord`: `hs.store.fail("NearestTier2InNamespace", …)`, then the
      record has `cache` MISS and `tier2_search_failed` true. A normal MISS on another question has the key
      absent.
    - telemetry, `TestTier2SearchErrorIsCounted`: write two marked records and one unmarked; the count is 2.
    - cmd/gateway:
      - `TestIncompleteNamesTier2SearchFailures`: `runCounts{Tier2SearchFailures: 2}` gives a verdict naming
        it;
      - `TestFinishRunCountsTier2SearchFailures`: a logger that accepted a marked record makes `finishRun`
        return a non-nil verdict.
  - Run: `cd gateway && go test -count=1 -v -run 'TestTier2SearchError' ./internal/httpapi/ ./internal/telemetry/ && go test -count=1 -v -run 'TestIncompleteNamesTier2|TestFinishRunCountsTier2' ./cmd/gateway/`
  - Pass: four `--- PASS`.
  - Result: added three tier2_search_error_test.go files (httpapi, telemetry, cmd/gateway; no Redis); four `--- PASS`; the httpapi test also checks the Logger counter (1 after a failed search, 0 after a normal MISS).

## Phase 5 — Docs

- [x] 5.1 The contract to v0.20.
  - Files: `docs/contracts/interfaces.md`
  - Do:
    - line 3: `v0.19` → `v0.20`;
    - §H gets a `tier2_search_failed` row: an extension, present only when this request's Tier-2 search
      returned an error; the request still degrades to a MISS;
    - **run rule 12**, beside rule 10: a run with any such record is not admissible. The gateway also
      counts them and reports the run INCOMPLETE. The reason: an index lost during a run (another
      process's `FLUSHDB`) otherwise looks like a colder cache;
    - §D, after the `idx:cache` block, one sentence: at start the gateway waits until the index is fully
      built (`EnsureCacheIndex`, `FT.INFO`), and a timeout stops it;
    - `Current version` → v0.20 (2026-10-29), and the version row.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && grep -n "v0.20\|tier2_search_failed\|rule 12" docs/contracts/interfaces.md | cut -c1-110`
  - Pass: the header, §H row, rule 12, §D sentence and version lines appear.
  - Result: interfaces.md v0.19 -> v0.20: header (l.3), §D sentence (l.455), §H `tier2_search_failed` row (l.719), run rule 12 after rule 11 (l.747), current version and version row (l.759, l.763); grep shows all six.

- [x] 5.2 Architecture and the Redis notes.
  - Files: `docs/architecture.md`, `docs/Redis-Data Structure.md`
  - Do:
    - `architecture.md`: a `testredis/` row in the package table (from §3), and two sentences under the
      commands or test section. They say: the Go Redis tests run only against `make test`'s throwaway server
      on 6390, never against :6379; and `FLUSHDB` on this server drops every index.
    - `Redis-Data Structure.md`: the two `FLUSHDB` facts (every index, every DB), the test server, and the
      start-up wait.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && grep -n "testredis\|6390" docs/architecture.md "docs/Redis-Data Structure.md" | cut -c1-110`
  - Pass: at least one line in each file.
  - Result: architecture.md: tree entry, `testredis/` package-table row, test-server paragraph in §4, `test-go`/`test-isolation-check` added to the "Check the code" row; Redis-Data Structure.md §5.4: the two FLUSHDB facts, the test server, the start-up wait; grep shows 3 lines in architecture.md and 1 in the Redis notes.

## Phase 6 — Run and verify

Run every step alone, in order. Check memory pressure before 6.1.

- [x] 6.1 DC 8 — `redis-cli PING`; `go clean -testcache`; then
  `make verify > docs/work/2026-10-29-redis-index-lifecycle/evidence/verify.out 2>&1; echo "exit=$?"`.
  Record the time it took.
  - Pass: `exit=0`; no FAIL; no SKIPPED target; no `--- SKIP` in the Go output.
  - Result: exit=0 in 62 s; Go: 13 packages `ok` (none FAIL), ruff passed, pytest 52 + 731 passed; no SKIPPED target; no FAIL/SKIP text in evidence/verify.out (Go ran without -v, but the required flag makes a Redis skip a FAIL); pressure 2 (citable: no).
- [x] 6.2 DC 1 — `make test-isolation-check GO_TEST_FLAGS=-count=1; echo "exit=$?"`, with `redis-cli FT._LIST`
  before and after.
  - Pass: `exit=0`; `FT._LIST` is the same before and after.
  - Result: exit=0, 10 packages ok, no FAIL/SKIP; `FT._LIST` = `idx:corpus` before and after (a real live index this time; evidence/isolation-6.2.out).
- [x] 6.3 DC 2 — `lsof -nP -iTCP:6390 -sTCP:LISTEN` prints nothing; `grep -n "go test -p 1" Makefile`. Then hold
  the port with `python3 -m http.server 6390 --bind 127.0.0.1 &`, run `make test-go; echo "exit=$?"`, and
  kill the listener.
  - Pass: nothing listens; the grep prints; `make test-go` exits non-zero, saying the port is taken.
  - Result: nothing on 6390; grep prints Makefile:342; with a python listener on 6390 `make test-go` printed "FAIL: port 6390 is taken ... Refusing to start" and exit=2; the listener was killed, no sentinel left, `FT._LIST` = `idx:corpus`.
- [x] 6.4 DC 3 — the step 2.5 command.
  - Pass: four `--- PASS`.
  - Result: four `--- PASS`, no SKIP, exit=0, `FT._LIST` = `idx:corpus` before and after, nothing on 6390.
- [x] 6.5 DC 4 — `cd gateway && GATEWAY_TEST_REDIS=127.0.0.1:1 GATEWAY_TEST_REDIS_REQUIRED=1 go test -count=1 -v -run TestRegisterWritesDepAndEntry ./internal/deps/; echo "exit=$?"`, then `cd gateway && env -u GATEWAY_TEST_REDIS -u GATEWAY_TEST_REDIS_REQUIRED go test -count=1 -v -run TestRegisterWritesDepAndEntry ./internal/deps/`
  - Pass: the first prints `--- FAIL` (not SKIP) and a non-zero exit. The second prints `--- SKIP` with a
    message naming `GATEWAY_TEST_REDIS`.
  - Result: dead address + required flag: `--- FAIL` ("test redis ... is not reachable"), exit=1; variable unset: `--- SKIP` with "GATEWAY_TEST_REDIS is not set: run the Redis tests through `make test`".
- [x] 6.6 DC 5 — the step 3.2 command, then the step 3.3 command.
  - Pass: two and four `--- PASS`.
  - Result: two `--- PASS` (TestEnsureCacheIndex* on the test server, make exit 0, `FT._LIST` still `idx:corpus`) and four `--- PASS` (TestWaitIndexed*).
- [x] 6.7 DC 6 — the step 4.4 commands, then `cd gateway && go test -count=1 -v -run TestCauseIsNullOnEveryExitWithNoCandidate ./internal/httpapi/`
  - Pass: four `--- PASS`, then that test `--- PASS` with its three subtests.
  - Result: four `--- PASS` (httpapi, telemetry, two in cmd/gateway), then TestCauseIsNullOnEveryExitWithNoCandidate `--- PASS` with embed_failure, retrieve_failure, search_error.
- [x] 6.8 DC 7 — the greps of steps 5.1 and 5.2.
  - Pass: as in 5.1 and 5.2.
  - Result: interfaces.md shows header v0.20, §D sentence, §H row, rule 12 and both version lines (l.3, 455, 719, 747, 759, 763); architecture.md has 3 testredis/6390 lines, Redis-Data Structure.md has 1.
- [x] 6.9 DC 9 — `cd /Users/hung/Desktop/Sem1/thesis && git diff --stat -- '*_test.go' && git diff -- gateway/internal/cache/capacity_test.go gateway/internal/deps/deps_test.go && git status --porcelain -- '*_test.go'`
  - Pass:
    - the stat lists only the two files;
    - their diff touches only `testStore` / `testRedis`, their comments, and any import change;
    - every other test file is `??`.
  - Result: stat lists only capacity_test.go (21 lines) and deps_test.go (23); their diff is the two helpers, their comments and one import each (`redis` swapped for `testredis` in cache; `testredis` added in deps); the six other test files are `??`.
