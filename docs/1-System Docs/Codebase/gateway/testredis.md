# `gateway/internal/testredis/` — the Redis that Go tests use

**Describes:** commit `29b24a6` (30 Oct 2026); the package was added in `bb7173c`. **Files:** `testredis.go`
(103 lines), `testredis_test.go`. Background: trail `docs/work/2026-10-29-redis-index-lifecycle/`.

## 1. Purpose

It gives Go tests a Redis connection, and refuses to give them the live one. It serves no thesis claim
directly; it protects the live indexes that every measurement needs.

## 2. Boundaries

- Only `_test.go` files may import it.
- It has **no default address**, and in particular never `localhost:6379`.

## 3. `testredis.go`

**Why it exists.** Two facts about this Redis (search module 2.10.20), found in an RCA on 29 Oct 2026:
1. `FLUSHDB` and `FLUSHALL` drop **every** search index, in every DB, even on an empty DB.
2. An index covers every DB, so a `t2:*` hash written in DB 15 enters DB 0's `idx:cache`.

So a test that flushes "its own" DB on the live server still deletes the live `idx:corpus` and `idx:cache`.
Logical DBs isolate keys, not indexes. The Go Redis tests therefore run only on a throwaway server.

**Constants.**
- `EnvAddr = "GATEWAY_TEST_REDIS"`: the test server's `host:port`. Unset means "no test server", and the test
  skips.
- `EnvRequired = "GATEWAY_TEST_REDIS_REQUIRED"`: when set (not "" or "0"), a skip becomes a failure. `make test`
  sets it, so a dead test server cannot make the suite pass by skipping.

**`Client(t, db)`** returns a client on logical DB `db`, empty, and flushes it again when the test ends. The
order matters: read the address, ping, run `CheckNotLive`, and **only then** flush. A server that fails the
check is never written to. A test that needs an index must use DB 0, where the search module creates indexes.

**`CheckNotLive(ctx, rdb)`** returns an error if the server holds **any** search index or **any** key in DB 0. A
fresh test server holds neither. It only reads.

**`unavailable(t, …)`** skips the test, or fails it when `EnvRequired` is on.

## 4. Callers and callees

- **Used by** the Redis tests of `cache` (two files) and `deps` (one file). `httpapi`'s tests use fakes and need no
  Redis.
- **Started by** `make test-go` (also run by `make test`): it starts a throwaway `redis-stack-server` on port
  6390, sets both variables, runs `go test -p 1`, and fails if the live server lost an index meanwhile.

## 5. Tests that pin it

| Test | Guarantees |
| :--- | :--- |
| `TestCheckNotLiveAcceptsACleanServer` | an empty server passes |
| `TestCheckNotLiveRefusesAnIndex` | a server with any index is refused |
| `TestCheckNotLiveRefusesDB0Keys` | a server with keys in DB 0 is refused |
| `TestClientChecksBeforeFlushing` | nothing is flushed on a server that fails the check |

## 6. Silent failures to watch

- **Running `go test` by hand without the variables** skips every Redis test. The suite then passes while
  testing nothing. Use `make test-go`.
- **Any `FLUSHDB` against the live server**, from a test, a script or a shell, drops every index. Re-ingest is
  then needed.

## 7. Commit

`29b24a6`. The package was added in `bb7173c` and has not changed since.
