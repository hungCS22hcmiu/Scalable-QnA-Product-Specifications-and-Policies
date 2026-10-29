# Deliverables — Redis index lifecycle (bugfix)

Closed 2026-10-29 · super-plan item: none — blocks 4.4 · no new ADR (`interfaces.md` v0.20)

## What shipped

- **The Go Redis tests have their own Redis.** `make test-go` starts `redis-server` with the search module on
  `127.0.0.1:6390`, with no persistence. It runs `go test -p 1` there and stops the server on every exit. It
  refuses a taken port. `make test` and `make verify` call it, and `make test-isolation-check` is the same run.
- **A sentinel guards the live server.** `make test-go` creates `idx:gotest-sentinel` on `:6379` and fails if
  it is gone after the tests. So a Go test that reaches the live server again is caught.
- **`gateway/internal/testredis`** (test-only): `Client(t, db)` reads `GATEWAY_TEST_REDIS` (no default). It
  pings, refuses a server with any search index or any DB 0 key (`CheckNotLive`), and only then flushes.
  `GATEWAY_TEST_REDIS_REQUIRED=1`, set by `make`, turns a skip into a failure.
- **The gateway serves only a complete `idx:cache`.** `EnsureCacheIndex` waits until `FT.INFO` shows
  `indexing` 0 and `percent_indexed` 1, also when the index "already exists" in the middle of a scan. After
  10 s it returns an error, and the gateway does not start.
- **Run rule 12.** A Tier-2 search error marks the record `tier2_search_failed`. The logger counts it, and
  `incomplete()` names it, so the run is not admissible. Before, it looked like a colder cache.

## Files changed

- `Makefile`: `test-go`, `test-isolation-check`, `test`.
- Gateway: `internal/testredis/testredis.go` (new), `cache/tier2.go`, `cmd/gateway/main.go`,
  `httpapi/cascade.go`, `httpapi/handler.go`, `telemetry/evallog.go`.
- **Existing tests, approved by the human on 2026-10-29:** only the helpers `testStore`
  (`cache/capacity_test.go`) and `testRedis` (`deps/deps_test.go`). No assertion changed.
- New tests: `testredis/testredis_test.go`, `cache/tier2_index_ready_test.go`, `cache/wait_indexed_test.go`,
  and `tier2_search_error_test.go` in `httpapi/`, `telemetry/` and `cmd/gateway/`.
- Docs: `interfaces.md` v0.20 (§D sentence, §H key, rule 12), `architecture.md`, `Redis-Data Structure.md`.

## How it was verified

The main session re-ran these on 2026-10-29, one at a time. Outputs are in `evidence/recheck/`.

| DC | Command | Result |
| :--- | :--- | :--- |
| 1 | `make test-isolation-check GO_TEST_FLAGS=-count=1` | exit 0; `idx:corpus` before and after. Before the fix the sentinel was gone (`evidence/isolation-before.out`) |
| 2 | port 6390 held by `python3 -m http.server`; then a failing `make test-go` | refused, exit 2; after the failure nothing on 6390, no test server left |
| 3 | `make test-go GO_TEST_PKGS=./internal/testredis/ GO_TEST_FLAGS='-count=1 -v'` | 4 PASS; no Go test outside `ragclient/` names `:6379`, no flush outside `testredis` |
| 4 | dead address + required flag; then the variable unset | `--- FAIL`, exit 1; then `--- SKIP` naming `GATEWAY_TEST_REDIS` |
| 5 | `TestEnsureCacheIndex*` through `make test-go`; `TestWaitIndexed*` | 2 + 4 PASS. Before the fix both FAIL: `indexing` 1, `num_docs` 0 and 2 of 1000 |
| 6 | the four rule-12 tests; `TestCauseIsNullOnEveryExitWithNoCandidate` | 4 PASS; the cause test passes with its 3 subtests |
| 7 | greps on the three docs | v0.20 (l.3), §D (l.455), §H key (l.719), rule 12 (l.747); the other two docs match |
| 8 | `make verify`, Go test cache cleared | exit 0; 10 Go packages `ok`; pytest 52 + 731 passed; no SKIPPED target |
| 9 | `git diff --stat -- '*_test.go'` | only the two helper files; the six new test files are `??` |

Two extra checks. **Mutation:** with the marker line removed from `cascade.go`, the httpapi rule-12 test
fails (`no "tier2_search_failed" key`); the file was restored byte for byte. **Cold start:** a new empty
`idx:cache` on a throwaway server shows `indexing` 0 and `percent_indexed` 1, so the wait does not block it.

## Numbers

None citable. `make verify` took 61 s and the Go tests about 12 s, on this machine at memory pressure level 2
(yellow), dev-v0 corpus: timings, `citable: no`. The cost of `-p 1` alone was not measured.

## Deferred and follow-ups

- **Open decision: make `-count=1` the default of `make test-go`.** Go replays cached results, so a
  `make verify` with no Go change passes the isolation check without touching Redis. Any Go change forces a
  real run. Cost: about 10 s per `make verify`.
- **Still on `:6379`:** the RAG Python tests (they read the ingested corpus; they do not flush), and the
  read-only `ragclient` live tests, which skip unless `RAG_SEAM_ADDR` is set.
- The logger counts a marked record before it queues it, so a record that a full buffer drops still counts.
- **Carried:** the reset for run rule 11 has no owner; a failed purge still deletes `dep:{chunk}`;
  `interfaces.md` §E "Purge decision" line; 4.4 must test the edit order.
