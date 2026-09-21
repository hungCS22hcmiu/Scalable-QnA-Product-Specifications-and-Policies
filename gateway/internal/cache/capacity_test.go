package cache

import (
	"context"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

// testStore isolates itself in logical DB 15. Never DB 0: this machine is shared with other
// projects and the thesis corpus, and `make demo-reset` refuses to FLUSHALL precisely because a
// stray key can belong to someone else. FLUSHDB on 15 touches nothing else.
func testStore(t *testing.T) *Store {
	t.Helper()
	rdb := redis.NewClient(&redis.Options{Addr: "localhost:6379", DB: 15})
	ctx := context.Background()
	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Skipf("redis not reachable, skipping: %v", err)
	}
	if err := rdb.FlushDB(ctx).Err(); err != nil {
		t.Fatalf("flushing test db: %v", err)
	}
	t.Cleanup(func() { _ = rdb.FlushDB(ctx); _ = rdb.Close() })
	return NewStore(rdb, 768)
}

// seed writes just enough of an entry pair for eviction to have something to delete.
func seed(t *testing.T, s *Store, entryID, t1Key string, at time.Time) {
	t.Helper()
	ctx := context.Background()
	if err := s.rdb.HSet(ctx, tier2KeyPrefix+entryID, map[string]any{"t1_key": t1Key, "answer": "a"}).Err(); err != nil {
		t.Fatal(err)
	}
	if err := s.rdb.HSet(ctx, t1Key, map[string]any{"answer": "a", "entry_id": entryID}).Err(); err != nil {
		t.Fatal(err)
	}
	if err := s.Touch(ctx, entryID, at.UnixNano()); err != nil {
		t.Fatal(err)
	}
}

func TestTrimEvictsLeastRecentlyUsedFirst(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	base := time.Now()

	// c is oldest, then a, then b -- deliberately not insertion order, so a test that passes by
	// evicting "the first one written" fails.
	seed(t, s, "a", "t1:aaa", base.Add(-2*time.Minute))
	seed(t, s, "b", "t1:bbb", base.Add(-1*time.Minute))
	seed(t, s, "c", "t1:ccc", base.Add(-3*time.Minute))

	evicted, err := s.TrimToCapacity(ctx, 2)
	if err != nil {
		t.Fatal(err)
	}
	if len(evicted) != 1 || evicted[0].EntryID != "c" {
		t.Fatalf("evicted %+v, want exactly the least-recently-used entry c", evicted)
	}
	if n, _ := s.CachedEntries(ctx); n != 2 {
		t.Fatalf("%d entries remain, want 2", n)
	}
}

// ⚠️ The invariant that makes capacity mean anything. Deleting only the Tier-2 record would leave
// Tier 1 serving the same answer from a bare hash lookup that runs no reuse rule -- so the entry
// would still be served while being absent from the cache the experiment believes it is bounding,
// and the capacity sweep would measure nothing.
func TestEvictionRemovesBothTiers(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	seed(t, s, "victim", "t1:victimkey", time.Now().Add(-time.Hour))
	seed(t, s, "keeper", "t1:keeperkey", time.Now())

	if _, err := s.TrimToCapacity(ctx, 1); err != nil {
		t.Fatal(err)
	}
	for _, k := range []string{tier2KeyPrefix + "victim", "t1:victimkey"} {
		if n, _ := s.rdb.Exists(ctx, k).Result(); n != 0 {
			t.Fatalf("%s survived eviction -- the tiers were not removed together", k)
		}
	}
	for _, k := range []string{tier2KeyPrefix + "keeper", "t1:keeperkey"} {
		if n, _ := s.rdb.Exists(ctx, k).Result(); n != 1 {
			t.Fatalf("%s was evicted but should have been kept", k)
		}
	}
}

// Touching an entry must save it. Without this the "LRU" is insertion order wearing its name.
func TestTouchRescuesAnOtherwiseDoomedEntry(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	seed(t, s, "old", "t1:old", time.Now().Add(-time.Hour))
	seed(t, s, "new", "t1:new", time.Now())

	if err := s.Touch(ctx, "old", time.Now().Add(time.Minute).UnixNano()); err != nil {
		t.Fatal(err)
	}
	evicted, err := s.TrimToCapacity(ctx, 1)
	if err != nil {
		t.Fatal(err)
	}
	if len(evicted) != 1 || evicted[0].EntryID != "new" {
		t.Fatalf("evicted %+v; the touched entry should have survived and 'new' should have gone", evicted)
	}
}

// Capacity 0 means unbounded, and must be a no-op rather than "evict everything".
func TestZeroCapacityEvictsNothing(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	for _, id := range []string{"a", "b", "c"} {
		seed(t, s, id, "t1:"+id, time.Now())
	}
	for _, capacity := range []int{0, -1} {
		evicted, err := s.TrimToCapacity(ctx, capacity)
		if err != nil || len(evicted) != 0 {
			t.Fatalf("capacity=%d evicted %+v (err %v), want nothing", capacity, evicted, err)
		}
	}
	if n, _ := s.CachedEntries(ctx); n != 3 {
		t.Fatalf("%d entries remain, want all 3", n)
	}
}

// Eviction must never touch the dependency region. An evicted dep record makes its entries
// permanently unpurgeable and breaks C2 completeness silently (rules.md #5, ADR-005).
func TestEvictionLeavesDependencyRecordsAlone(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	if err := s.rdb.SAdd(ctx, "dep:policy-warranty#chunk-0", "victim").Err(); err != nil {
		t.Fatal(err)
	}
	if err := s.rdb.HSet(ctx, "entry:victim", "sources", "[]").Err(); err != nil {
		t.Fatal(err)
	}
	seed(t, s, "victim", "t1:victimkey", time.Now().Add(-time.Hour))
	seed(t, s, "keeper", "t1:keeperkey", time.Now())

	if _, err := s.TrimToCapacity(ctx, 1); err != nil {
		t.Fatal(err)
	}
	for _, k := range []string{"dep:policy-warranty#chunk-0", "entry:victim"} {
		if n, _ := s.rdb.Exists(ctx, k).Result(); n != 1 {
			t.Fatalf("%s was removed by cache eviction -- C2 completeness is broken silently", k)
		}
	}
}
