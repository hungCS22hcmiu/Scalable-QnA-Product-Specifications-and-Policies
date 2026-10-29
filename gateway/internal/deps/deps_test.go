package deps

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"sort"
	"sync"
	"testing"
	"time"

	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/testredis"
	"github.com/redis/go-redis/v9"
)

// testRedis runs these tests on the throwaway test Redis that `make test` starts
// (testredis.EnvAddr), in logical DB 14, and never on the live server. A logical DB isolates keys,
// not indexes: on this server FLUSHDB drops every search index in every DB, and an index covers
// every DB, so a flush "of DB 14" on :6379 would delete the live idx:corpus and idx:cache
// (RCA 2026-10-29). testredis.Client refuses a server that looks live before it flushes. With the
// variable unset the test SKIPS; under `make test`, which sets the required flag, it fails
// instead, and the plan treats a SKIP as a failed step.
func testRedis(t *testing.T) *redis.Client {
	t.Helper()
	return testredis.Client(t, 14)
}

// newMap builds a Map and closes it when the test ends. Cleanups run last-in first-out, so a test
// that holds the writer must register its release AFTER newMap.
func newMap(t *testing.T, rdb *redis.Client, p Purger, queue int) *Map {
	t.Helper()
	m := New(rdb, p, queue)
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := m.Close(ctx); err != nil {
			t.Errorf("closing the map: %v", err)
		}
	})
	return m
}

// barrier returns once every earlier message has been handled in full. The queue is FIFO and one
// goroutine handles it, so an Invalidate of a chunk nobody depends on cannot be acked before the
// registrations and purges ahead of it are done.
func barrier(t *testing.T, m *Map) {
	t.Helper()
	ids, err := m.Invalidate(Event{ChunkID: "barrier-unused-chunk"})
	if err != nil || len(ids) != 0 {
		t.Fatalf("barrier: ids=%v err=%v", ids, err)
	}
}

// seedEntry writes the cache state of one entry the way a write-back does: the Tier-1 record (naming
// the entry), optionally the Tier-2 record (carrying t1_key), and the lru:entries member.
func seedEntry(t *testing.T, rdb *redis.Client, entryID, t1Key string, withT2 bool) {
	t.Helper()
	ctx := context.Background()
	if err := rdb.HSet(ctx, t1Key, map[string]any{"answer": "a", "entry_id": entryID}).Err(); err != nil {
		t.Fatal(err)
	}
	if withT2 {
		if err := rdb.HSet(ctx, "t2:"+entryID, map[string]any{"t1_key": t1Key, "answer": "a"}).Err(); err != nil {
			t.Fatal(err)
		}
	}
	if err := rdb.ZAdd(ctx, "lru:entries", redis.Z{Score: float64(time.Now().UnixNano()), Member: entryID}).Err(); err != nil {
		t.Fatal(err)
	}
}

func exists(t *testing.T, rdb *redis.Client, key string) bool {
	t.Helper()
	n, err := rdb.Exists(context.Background(), key).Result()
	if err != nil {
		t.Fatal(err)
	}
	return n == 1
}

func inLRU(t *testing.T, rdb *redis.Client, entryID string) bool {
	t.Helper()
	_, err := rdb.ZScore(context.Background(), "lru:entries", entryID).Result()
	if err != nil && !errors.Is(err, redis.Nil) {
		t.Fatal(err)
	}
	return err == nil
}

func isMember(t *testing.T, rdb *redis.Client, set, member string) bool {
	t.Helper()
	ok, err := rdb.SIsMember(context.Background(), set, member).Result()
	if err != nil {
		t.Fatal(err)
	}
	return ok
}

func sorted(ids []string) []string {
	out := append([]string(nil), ids...)
	sort.Strings(out)
	return out
}

// realPurger is the production Purger: *cache.Store.
func realPurger(rdb *redis.Client) Purger { return cache.NewStore(rdb, 768) }

// holdingPurger wraps a Purger and blocks every PurgeEntry until Release. entered is signalled each
// time the writer arrives inside a purge, so a test knows the writer is held.
type holdingPurger struct {
	inner   Purger
	entered chan string
	release chan struct{}
	once    sync.Once
}

func newHoldingPurger(inner Purger) *holdingPurger {
	return &holdingPurger{inner: inner, entered: make(chan string, 16), release: make(chan struct{})}
}

func (p *holdingPurger) PurgeEntry(ctx context.Context, entryID, t1Key string) error {
	p.entered <- entryID
	<-p.release
	return p.inner.PurgeEntry(ctx, entryID, t1Key)
}

func (p *holdingPurger) Release() { p.once.Do(func() { close(p.release) }) }

type failingPurger struct{}

func (failingPurger) PurgeEntry(context.Context, string, string) error {
	return errors.New("purge refused by the test")
}

// DC 1.
func TestRegisterWritesDepAndEntry(t *testing.T) {
	rdb := testRedis(t)
	ctx := context.Background()
	m := newMap(t, rdb, realPurger(rdb), 16)
	seedEntry(t, rdb, "E", "t1:keyE", true)

	m.Register(Registration{EntryID: "E", Sources: []string{"A", "B"}, T1Key: "t1:keyE", DatasetEpoch: 7})
	barrier(t, m)

	for _, c := range []string{"A", "B"} {
		if !isMember(t, rdb, "dep:"+c, "E") {
			t.Fatalf("dep:%s does not contain E", c)
		}
	}
	got, err := rdb.HGetAll(ctx, "entry:E").Result()
	if err != nil {
		t.Fatal(err)
	}
	if got["t1_key"] != "t1:keyE" {
		t.Fatalf("entry:E t1_key = %q, want t1:keyE", got["t1_key"])
	}
	var sources []string
	if err := json.Unmarshal([]byte(got["source_chunk_ids"]), &sources); err != nil {
		t.Fatalf("entry:E source_chunk_ids %q: %v", got["source_chunk_ids"], err)
	}
	if !reflect.DeepEqual(sources, []string{"A", "B"}) {
		t.Fatalf("entry:E source_chunk_ids = %v, want [A B]", sources)
	}
}

// DC 1, second half: a write-back with no Tier-2 record (the embedding failed) registers the same.
func TestRegisterWithoutTier2Entry(t *testing.T) {
	rdb := testRedis(t)
	ctx := context.Background()
	m := newMap(t, rdb, realPurger(rdb), 16)
	seedEntry(t, rdb, "T1ONLY", "t1:keyT1", false)

	m.Register(Registration{EntryID: "T1ONLY", Sources: []string{"A", "C"}, T1Key: "t1:keyT1"})
	barrier(t, m)

	if exists(t, rdb, "t2:T1ONLY") {
		t.Fatal("the fixture has a t2 record; this test is about an entry without one")
	}
	for _, c := range []string{"A", "C"} {
		if !isMember(t, rdb, "dep:"+c, "T1ONLY") {
			t.Fatalf("dep:%s does not contain T1ONLY", c)
		}
	}
	if k, _ := rdb.HGet(ctx, "entry:T1ONLY", "t1_key").Result(); k != "t1:keyT1" {
		t.Fatalf("entry:T1ONLY t1_key = %q, want t1:keyT1", k)
	}
	raw, _ := rdb.HGet(ctx, "entry:T1ONLY", "source_chunk_ids").Result()
	var sources []string
	if err := json.Unmarshal([]byte(raw), &sources); err != nil || !reflect.DeepEqual(sources, []string{"A", "C"}) {
		t.Fatalf("entry:T1ONLY source_chunk_ids = %q (err %v), want [A C]", raw, err)
	}
}

// DC 2. E1 {A,B}, E2 {B,C}, E3 {C}; invalidate B. The purge is complete (E1 and E2 are gone from
// every record) and exact (E3 is untouched, so over-invalidation is not hiding in the count).
func TestInvalidatePurgesExactlyDependents(t *testing.T) {
	rdb := testRedis(t)
	m := newMap(t, rdb, realPurger(rdb), 16)

	entries := []struct {
		id      string
		sources []string
	}{
		{"E1", []string{"A", "B"}},
		{"E2", []string{"B", "C"}},
		{"E3", []string{"C"}},
	}
	for _, e := range entries {
		seedEntry(t, rdb, e.id, "t1:key"+e.id, true)
		m.Register(Registration{EntryID: e.id, Sources: e.sources, T1Key: "t1:key" + e.id})
	}
	barrier(t, m)

	ids, err := m.Invalidate(Event{ChunkID: "B", ChangeType: "substantive"})
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(sorted(ids), []string{"E1", "E2"}) {
		t.Fatalf("Invalidate(B) returned %v, want [E1 E2]", ids)
	}
	barrier(t, m) // the purge runs after the ack; the barrier waits for it

	for _, id := range []string{"E1", "E2"} {
		for _, k := range []string{"t1:key" + id, "t2:" + id, "entry:" + id} {
			if exists(t, rdb, k) {
				t.Fatalf("%s survived the purge of B", k)
			}
		}
		if inLRU(t, rdb, id) {
			t.Fatalf("%s is still in lru:entries", id)
		}
	}
	if exists(t, rdb, "dep:B") {
		t.Fatal("dep:B survived its own invalidation")
	}

	for _, k := range []string{"t1:keyE3", "t2:E3", "entry:E3"} {
		if !exists(t, rdb, k) {
			t.Fatalf("%s was purged but E3 does not depend on B", k)
		}
	}
	if !inLRU(t, rdb, "E3") {
		t.Fatal("E3 left lru:entries")
	}
	if !isMember(t, rdb, "dep:C", "E3") {
		t.Fatal("dep:C no longer contains E3")
	}
	if m.Invalidated("E3") {
		t.Fatal("E3 is tombstoned but does not depend on B")
	}
}

// DC 3. An entry written with no t2: record is purged through the t1_key that entry:E recorded.
func TestInvalidatePurgesTier1OnlyEntry(t *testing.T) {
	rdb := testRedis(t)
	m := newMap(t, rdb, realPurger(rdb), 16)
	seedEntry(t, rdb, "T1ONLY", "t1:onlykey", false)
	m.Register(Registration{EntryID: "T1ONLY", Sources: []string{"A"}, T1Key: "t1:onlykey"})
	barrier(t, m)

	if _, err := m.Invalidate(Event{ChunkID: "A"}); err != nil {
		t.Fatal(err)
	}
	barrier(t, m)

	for _, k := range []string{"t1:onlykey", "entry:T1ONLY"} {
		if exists(t, rdb, k) {
			t.Fatalf("%s survived: a Tier-1-only entry is unpurgeable", k)
		}
	}
	if inLRU(t, rdb, "T1ONLY") {
		t.Fatal("T1ONLY is still in lru:entries")
	}
}

// DC 5a. Invalidate returns once the tombstones are visible, while the Redis purge is still held back.
func TestInvalidatedVisibleBeforePurge(t *testing.T) {
	rdb := testRedis(t)
	hold := newHoldingPurger(realPurger(rdb))
	m := newMap(t, rdb, hold, 16)
	t.Cleanup(hold.Release) // runs before the map's Close, so Close can drain

	seedEntry(t, rdb, "E1", "t1:keyE1", true)
	seedEntry(t, rdb, "E3", "t1:keyE3", true)
	m.Register(Registration{EntryID: "E1", Sources: []string{"A"}, T1Key: "t1:keyE1"})
	m.Register(Registration{EntryID: "E3", Sources: []string{"Z"}, T1Key: "t1:keyE3"})

	ids, err := m.Invalidate(Event{ChunkID: "A"})
	if err != nil || !reflect.DeepEqual(ids, []string{"E1"}) {
		t.Fatalf("Invalidate(A) = %v, %v; want [E1]", ids, err)
	}
	select {
	case <-hold.entered: // the writer is now inside the purge of E1
	case <-time.After(5 * time.Second):
		t.Fatal("the writer never reached the purge")
	}

	if !m.Invalidated("E1") {
		t.Fatal("E1 is not refused although Invalidate has returned")
	}
	if !exists(t, rdb, "t2:E1") {
		t.Fatal("t2:E1 is already gone: the purge was not held back, so this test shows nothing")
	}
	if m.Invalidated("E3") {
		t.Fatal("E3 is refused but none of its chunks was invalidated")
	}

	hold.Release()
	barrier(t, m)
	if exists(t, rdb, "t2:E1") {
		t.Fatal("t2:E1 survived once the purge was released")
	}
	if !m.Invalidated("E1") {
		t.Fatal("the tombstone was lost after the purge")
	}
}

// DC 7. A full queue makes Register wait. It does not drop.
func TestRegisterWaitsWhenQueueFull(t *testing.T) {
	rdb := testRedis(t)
	hold := newHoldingPurger(realPurger(rdb))
	m := newMap(t, rdb, hold, 1)
	t.Cleanup(hold.Release)

	// Hold the writer inside a purge.
	seedEntry(t, rdb, "E1", "t1:keyE1", true)
	m.Register(Registration{EntryID: "E1", Sources: []string{"A"}, T1Key: "t1:keyE1"})
	if _, err := m.Invalidate(Event{ChunkID: "A"}); err != nil {
		t.Fatal(err)
	}
	select {
	case <-hold.entered:
	case <-time.After(5 * time.Second):
		t.Fatal("the writer never reached the purge")
	}

	// The queue holds one message. Fill it, then send one more.
	m.Register(Registration{EntryID: "FILL", Sources: []string{"F"}, T1Key: "t1:keyFILL"})
	returned := make(chan struct{})
	go func() {
		m.Register(Registration{EntryID: "EXTRA", Sources: []string{"X"}, T1Key: "t1:keyEXTRA"})
		close(returned)
	}()
	select {
	case <-returned:
		t.Fatal("Register returned although the queue was full and the writer held: it dropped or skipped")
	case <-time.After(200 * time.Millisecond):
	}

	hold.Release()
	select {
	case <-returned:
	case <-time.After(5 * time.Second):
		t.Fatal("the waiting Register never returned after the writer was released")
	}
	barrier(t, m)

	for _, c := range []struct{ set, id string }{{"dep:F", "FILL"}, {"dep:X", "EXTRA"}} {
		if !isMember(t, rdb, c.set, c.id) {
			t.Fatalf("%s does not contain %s: the registration was lost", c.set, c.id)
		}
	}
	if m.Dropped() != 0 {
		t.Fatalf("Dropped() = %d, want 0: nothing was refused", m.Dropped())
	}
}

// DC 7. After Close a registration is refused, but counted and never lost without a trace.
func TestRegisterAfterCloseIsCounted(t *testing.T) {
	rdb := testRedis(t)
	m := newMap(t, rdb, realPurger(rdb), 4)

	if err := m.Close(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := m.Close(context.Background()); err != nil {
		t.Fatalf("a second Close returned %v, want nil", err)
	}
	m.Register(Registration{EntryID: "LATE", Sources: []string{"A"}, T1Key: "t1:late"})
	m.Register(Registration{EntryID: "LATER", Sources: []string{"A"}, T1Key: "t1:later"})

	if m.Dropped() != 2 {
		t.Fatalf("Dropped() = %d, want 2", m.Dropped())
	}
	if exists(t, rdb, "dep:A") || exists(t, rdb, "entry:LATE") {
		t.Fatal("a registration made after Close reached Redis")
	}
}

// DC 7. A registration whose Redis write fails is counted. The client below cannot connect.
func TestRegisterErrorIsCounted(t *testing.T) {
	bad := redis.NewClient(&redis.Options{Addr: "localhost:1", DialTimeout: 200 * time.Millisecond, MaxRetries: -1})
	t.Cleanup(func() { _ = bad.Close() })
	m := New(bad, failingPurger{}, 4)

	m.Register(Registration{EntryID: "E", Sources: []string{"A"}, T1Key: "t1:k"})
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := m.Close(ctx); err != nil { // Close drains the queue, so the write has been attempted
		t.Fatal(err)
	}
	if m.RegisterErrors() != 1 {
		t.Fatalf("RegisterErrors() = %d, want 1", m.RegisterErrors())
	}
	if m.Dropped() != 0 {
		t.Fatalf("Dropped() = %d, want 0", m.Dropped())
	}
}

// DC 7. A purge whose Redis call fails is counted, and the tombstone still holds: this process keeps
// refusing the entry even though its Redis copy is still there.
func TestPurgeErrorIsCounted(t *testing.T) {
	rdb := testRedis(t)
	m := newMap(t, rdb, failingPurger{}, 16)
	seedEntry(t, rdb, "E", "t1:keyE", true)
	m.Register(Registration{EntryID: "E", Sources: []string{"A"}, T1Key: "t1:keyE"})

	ids, err := m.Invalidate(Event{ChunkID: "A"})
	if err != nil || !reflect.DeepEqual(ids, []string{"E"}) {
		t.Fatalf("Invalidate(A) = %v, %v; want [E]", ids, err)
	}
	barrier(t, m)

	if m.PurgeErrors() != 1 {
		t.Fatalf("PurgeErrors() = %d, want 1", m.PurgeErrors())
	}
	if !m.Invalidated("E") {
		t.Fatal("the tombstone was lost when the purge failed")
	}
	if !exists(t, rdb, "t2:E") {
		t.Fatal("t2:E is gone although the purger refused; the fixture shows nothing")
	}
	if !exists(t, rdb, "entry:E") {
		t.Fatal("entry:E was deleted after a failed purge: its t1_key is lost")
	}
}

// DC 7. Invalidate after Close is an error and purges nothing.
func TestInvalidateAfterCloseFails(t *testing.T) {
	rdb := testRedis(t)
	m := newMap(t, rdb, realPurger(rdb), 4)
	seedEntry(t, rdb, "E", "t1:keyE", true)
	m.Register(Registration{EntryID: "E", Sources: []string{"A"}, T1Key: "t1:keyE"})
	if err := m.Close(context.Background()); err != nil { // drains the registration
		t.Fatal(err)
	}

	ids, err := m.Invalidate(Event{ChunkID: "A"})
	if err == nil {
		t.Fatalf("Invalidate after Close returned ids=%v and no error", ids)
	}
	if m.Invalidated("E") {
		t.Fatal("E is tombstoned by an invalidation that was refused")
	}
	if !exists(t, rdb, "t2:E") || !exists(t, rdb, "t1:keyE") {
		t.Fatal("a refused invalidation purged something")
	}
}
