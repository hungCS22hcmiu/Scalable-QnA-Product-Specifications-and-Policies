package testredis

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

// rawClient connects to EnvAddr on DB 0 without Client's guard, and skips (or fails, under the
// required flag) the same way Client does when the address is unset or the server is down. It never
// flushes: these tests may be pointed at a server by mistake, and must not be able to hurt it.
func rawClient(t *testing.T) (*redis.Client, context.Context) {
	t.Helper()
	addr := os.Getenv(EnvAddr)
	if addr == "" {
		unavailable(t, "%s is not set: run the Redis tests through `make test`", EnvAddr)
	}
	rdb := redis.NewClient(&redis.Options{Addr: addr, DB: 0})
	t.Cleanup(func() { _ = rdb.Close() })
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	t.Cleanup(cancel)
	if err := rdb.Ping(ctx).Err(); err != nil {
		unavailable(t, "test redis %s=%s is not reachable: %v", EnvAddr, addr, err)
	}
	return rdb, ctx
}

// requireClean fails the test if the server is not clean, so a "refuses" test can never pass
// because of something that was already on the server.
func requireClean(t *testing.T, ctx context.Context, rdb *redis.Client) {
	t.Helper()
	if err := CheckNotLive(ctx, rdb); err != nil {
		t.Fatalf("precondition: the test server should be clean, but: %v", err)
	}
}

func TestCheckNotLiveAcceptsACleanServer(t *testing.T) {
	rdb, ctx := rawClient(t)
	if err := CheckNotLive(ctx, rdb); err != nil {
		t.Fatalf("a clean test server was refused: %v", err)
	}
}

func TestCheckNotLiveRefusesAnIndex(t *testing.T) {
	rdb, ctx := rawClient(t)
	requireClean(t, ctx, rdb)

	const idx = "idx:testredis-guard"
	err := rdb.Do(ctx, "FT.CREATE", idx, "ON", "HASH", "PREFIX", "1", "testredis-guard-nomatch:", "SCHEMA", "f", "TEXT").Err()
	if err != nil {
		t.Fatalf("creating the throwaway index: %v", err)
	}
	// FT.DROPINDEX without DD: it removes the index only, never the documents.
	t.Cleanup(func() { _ = rdb.Do(context.Background(), "FT.DROPINDEX", idx).Err() })

	err = CheckNotLive(ctx, rdb)
	if err == nil {
		t.Fatal("a server that holds a search index was accepted")
	}
	if !strings.Contains(err.Error(), idx) {
		t.Fatalf("the error should name the index %s, got: %v", idx, err)
	}
}

func TestCheckNotLiveRefusesDB0Keys(t *testing.T) {
	rdb, ctx := rawClient(t)
	requireClean(t, ctx, rdb)

	const key = "testredis-guard-key"
	if err := rdb.Set(ctx, key, "x", 0).Err(); err != nil {
		t.Fatalf("writing the DB 0 key: %v", err)
	}
	t.Cleanup(func() { _ = rdb.Del(context.Background(), key).Err() })

	err := CheckNotLive(ctx, rdb)
	if err == nil {
		t.Fatal("a server that holds a DB 0 key was accepted")
	}
	if !strings.Contains(err.Error(), "DB 0") {
		t.Fatalf("the error should say DB 0, got: %v", err)
	}
}

// Client must run the guard before it deletes anything. This reads the source because the order is
// the property: a Client that flushed first would pass every other test and still wipe a live server.
func TestClientChecksBeforeFlushing(t *testing.T) {
	src, err := os.ReadFile("testredis.go")
	if err != nil {
		t.Fatal(err)
	}
	var code []string
	for _, line := range strings.Split(string(src), "\n") {
		if strings.HasPrefix(strings.TrimSpace(line), "//") {
			continue
		}
		code = append(code, line)
	}
	all := strings.Join(code, "\n")

	start := strings.Index(all, "func Client(")
	if start < 0 {
		t.Fatal("func Client( not found in testredis.go")
	}
	body := all[start:]
	if end := strings.Index(body, "\n}\n"); end >= 0 {
		body = body[:end]
	}

	check := strings.Index(body, "CheckNotLive(")
	flush := strings.Index(body, "FlushDB(")
	if check < 0 {
		t.Fatal("Client never calls CheckNotLive(")
	}
	if flush < 0 {
		t.Fatal("Client never calls FlushDB(: the test is reading the wrong function")
	}
	if check > flush {
		t.Fatal("Client calls FlushDB( before CheckNotLive(: a live server would be wiped before the guard runs")
	}
}
