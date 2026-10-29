// Package testredis gives the Go tests their Redis connection, and refuses to give them the live one.
//
// It is imported only by _test.go files. Nothing outside a test may import it.
//
// Two facts about this server (search 2.10.20) decide the design (RCA 2026-10-29, see
// docs/work/2026-10-29-redis-index-lifecycle/):
//
//  1. FLUSHDB and FLUSHALL drop every search index, in every DB, even on an empty DB.
//  2. An index covers every DB. Index names and indexed keys are global, so a t2:* hash written in
//     DB 15 enters DB 0's idx:cache.
//
// So a test that flushes "its own" DB on the live server still deletes the live idx:corpus and
// idx:cache, and its hashes can show up in them. Logical DBs isolate keys, not indexes. The Redis
// tests therefore run only against the throwaway server that `make test` starts (port 6390), whose
// address arrives in EnvAddr. There is no default address, and in particular never localhost:6379.
package testredis

import (
	"context"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	// EnvAddr holds the host:port of the test server. Unset means "no test server": the test skips.
	EnvAddr = "GATEWAY_TEST_REDIS"
	// EnvRequired, when set to anything but "" or "0", turns every skip into a failure. `make test`
	// sets it, so a dead or missing test server cannot make the suite pass by skipping.
	EnvRequired = "GATEWAY_TEST_REDIS_REQUIRED"
)

// Client returns a client on the test server's logical DB db, empty, and flushes it again when the
// test ends. Order matters: read the address, ping, check the server is not a live one, only then
// flush. A server that fails the check is never written to.
//
// A test that needs an index must use db 0, because the search module creates indexes only there.
func Client(t testing.TB, db int) *redis.Client {
	t.Helper()
	addr := os.Getenv(EnvAddr)
	if addr == "" {
		unavailable(t, "%s is not set: run the Redis tests through `make test`", EnvAddr)
		return nil
	}
	rdb := redis.NewClient(&redis.Options{Addr: addr, DB: db})
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		_ = rdb.Close()
		unavailable(t, "test redis %s=%s is not reachable: %v", EnvAddr, addr, err)
		return nil
	}
	if err := CheckNotLive(ctx, rdb); err != nil {
		_ = rdb.Close()
		t.Fatalf("refusing %s=%s: %v", EnvAddr, addr, err)
	}
	if err := rdb.FlushDB(ctx).Err(); err != nil {
		_ = rdb.Close()
		t.Fatalf("flushing test db %d: %v", db, err)
	}
	t.Cleanup(func() {
		c, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = rdb.FlushDB(c)
		_ = rdb.Close()
	})
	return rdb
}

// CheckNotLive returns an error when the server behind rdb looks like a live one: it holds any
// search index, or any key in DB 0. A fresh test server holds neither. It only reads.
func CheckNotLive(ctx context.Context, rdb *redis.Client) error {
	indexes, err := rdb.FT_List(ctx).Result()
	if err != nil {
		return fmt.Errorf("cannot list search indexes (is the search module loaded?): %w", err)
	}
	if len(indexes) > 0 {
		return fmt.Errorf("the server holds search index(es) %v: a flush would drop them", indexes)
	}
	o := rdb.Options()
	db0 := redis.NewClient(&redis.Options{Addr: o.Addr, Username: o.Username, Password: o.Password, DB: 0})
	defer func() { _ = db0.Close() }()
	n, err := db0.DBSize(ctx).Result()
	if err != nil {
		return fmt.Errorf("cannot count DB 0 keys: %w", err)
	}
	if n > 0 {
		return fmt.Errorf("DB 0 holds %d key(s): this looks like a live server", n)
	}
	return nil
}

// unavailable skips the test, or fails it when EnvRequired is on.
func unavailable(t testing.TB, format string, args ...any) {
	t.Helper()
	if v := os.Getenv(EnvRequired); v != "" && v != "0" {
		t.Fatalf(format, args...)
	}
	t.Skipf(format, args...)
}
