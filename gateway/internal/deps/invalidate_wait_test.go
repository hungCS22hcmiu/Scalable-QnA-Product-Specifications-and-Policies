package deps

import (
	"context"
	"errors"
	"reflect"
	"sync/atomic"
	"testing"
	"time"
)

// Item 4.4, done condition 4 (the Redis half): InvalidateWait replies after the whole purge, and a
// failed entry stays in dep:{chunk}. The helpers are deps_test.go's.

// flakyPurger fails its first `failures` calls and then purges for real.
type flakyPurger struct {
	inner    Purger
	failures int64
	calls    atomic.Int64
}

func (p *flakyPurger) PurgeEntry(ctx context.Context, entryID, t1Key string) error {
	if p.calls.Add(1) <= p.failures {
		return errors.New("purge refused by the test (flaky)")
	}
	return p.inner.PurgeEntry(ctx, entryID, t1Key)
}

// selectivePurger refuses the entries in failFor and purges the rest for real.
type selectivePurger struct {
	inner   Purger
	failFor map[string]bool
}

func (p selectivePurger) PurgeEntry(ctx context.Context, entryID, t1Key string) error {
	if p.failFor[entryID] {
		return errors.New("purge of " + entryID + " refused by the test")
	}
	return p.inner.PurgeEntry(ctx, entryID, t1Key)
}

// The moment InvalidateWait returns, every record of the entry is gone. There is no barrier here on
// purpose: the point of the method is that the caller needs none.
func TestInvalidateWaitReturnsAfterThePurge(t *testing.T) {
	rdb := testRedis(t)
	m := newMap(t, rdb, realPurger(rdb), 16)
	seedEntry(t, rdb, "E", "t1:keyE", true)
	m.Register(Registration{EntryID: "E", Sources: []string{"A"}, T1Key: "t1:keyE"})
	barrier(t, m) // only so that the registration has reached Redis

	for _, k := range []string{"t2:E", "t1:keyE", "entry:E", "dep:A"} {
		if !exists(t, rdb, k) {
			t.Fatalf("%s is missing before the invalidation: the fixture shows nothing", k)
		}
	}

	res, err := m.InvalidateWait(context.Background(), Event{ChunkID: "A", ChangeType: "substantive"})
	if err != nil {
		t.Fatal(err)
	}
	if res.ChunkID != "A" {
		t.Fatalf("ChunkID = %q, want A", res.ChunkID)
	}
	if !reflect.DeepEqual(res.Purged, []string{"E"}) {
		t.Fatalf("Purged = %v, want [E]", res.Purged)
	}
	if len(res.Failed) != 0 || len(res.Errors) != 0 {
		t.Fatalf("Failed = %v, Errors = %v, want none", res.Failed, res.Errors)
	}
	for _, k := range []string{"t2:E", "t1:keyE", "entry:E", "dep:A"} {
		if exists(t, rdb, k) {
			t.Fatalf("%s survived: InvalidateWait returned before the purge finished", k)
		}
	}
	if inLRU(t, rdb, "E") {
		t.Fatal("E is still in lru:entries")
	}
	if !m.Invalidated("E") {
		t.Fatal("E is not tombstoned")
	}
}

// A failed purge reports the entry as failed, and the entry stays where a second call can find it.
func TestInvalidateWaitKeepsFailedEntriesInDep(t *testing.T) {
	rdb := testRedis(t)
	m := newMap(t, rdb, failingPurger{}, 16)
	seedEntry(t, rdb, "E", "t1:keyE", true)
	m.Register(Registration{EntryID: "E", Sources: []string{"A"}, T1Key: "t1:keyE"})

	res, err := m.InvalidateWait(context.Background(), Event{ChunkID: "A"})
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(res.Failed, []string{"E"}) || len(res.Purged) != 0 {
		t.Fatalf("Failed = %v, Purged = %v; want [E] and none", res.Failed, res.Purged)
	}
	if !isMember(t, rdb, "dep:A", "E") {
		t.Fatal("dep:A lost E although its purge failed: nothing could purge it again")
	}
	if !exists(t, rdb, "entry:E") {
		t.Fatal("entry:E was deleted after a failed purge: its t1_key is lost")
	}
	if !exists(t, rdb, "t2:E") {
		t.Fatal("t2:E is gone although the purger refused; the fixture shows nothing")
	}
	if !m.Invalidated("E") {
		t.Fatal("the tombstone was lost when the purge failed")
	}
}

// The retry that the failure above makes possible: the same call purges the entry the second time.
func TestInvalidateWaitRetryPurgesAgain(t *testing.T) {
	rdb := testRedis(t)
	p := &flakyPurger{inner: realPurger(rdb), failures: 1}
	m := newMap(t, rdb, p, 16)
	seedEntry(t, rdb, "E", "t1:keyE", true)
	m.Register(Registration{EntryID: "E", Sources: []string{"A"}, T1Key: "t1:keyE"})

	first, err := m.InvalidateWait(context.Background(), Event{ChunkID: "A"})
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(first.Failed, []string{"E"}) {
		t.Fatalf("first call: Failed = %v, want [E]", first.Failed)
	}

	second, err := m.InvalidateWait(context.Background(), Event{ChunkID: "A"})
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(second.Purged, []string{"E"}) || len(second.Failed) != 0 {
		t.Fatalf("second call: Purged = %v, Failed = %v; want [E] and none", second.Purged, second.Failed)
	}
	for _, k := range []string{"t2:E", "t1:keyE", "entry:E", "dep:A"} {
		if exists(t, rdb, k) {
			t.Fatalf("%s survived the retry", k)
		}
	}
}

// Two entries under A, one fails: dep:A keeps exactly the failed one.
func TestInvalidateWaitPurgesOnlyThePurged(t *testing.T) {
	rdb := testRedis(t)
	m := newMap(t, rdb, selectivePurger{inner: realPurger(rdb), failFor: map[string]bool{"E2": true}}, 16)
	for _, id := range []string{"E1", "E2"} {
		seedEntry(t, rdb, id, "t1:key"+id, true)
		m.Register(Registration{EntryID: id, Sources: []string{"A"}, T1Key: "t1:key" + id})
	}

	res, err := m.InvalidateWait(context.Background(), Event{ChunkID: "A"})
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(res.Purged, []string{"E1"}) || !reflect.DeepEqual(res.Failed, []string{"E2"}) {
		t.Fatalf("Purged = %v, Failed = %v; want [E1] and [E2]", res.Purged, res.Failed)
	}

	members, err := rdb.SMembers(context.Background(), "dep:A").Result()
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(members, []string{"E2"}) {
		t.Fatalf("dep:A holds %v, want only the failed entry [E2]", members)
	}
	if exists(t, rdb, "entry:E1") || exists(t, rdb, "t2:E1") || exists(t, rdb, "t1:keyE1") {
		t.Fatal("E1 was purged but a record of it survived")
	}
	if !exists(t, rdb, "entry:E2") || !exists(t, rdb, "t2:E2") {
		t.Fatal("E2 failed to purge but its records are gone")
	}
}

// A cancelled wait is an error for the caller, and the purge still runs to the end in the writer.
func TestInvalidateWaitHonoursContext(t *testing.T) {
	rdb := testRedis(t)
	hold := newHoldingPurger(realPurger(rdb))
	m := newMap(t, rdb, hold, 16)
	t.Cleanup(hold.Release) // after newMap, so it runs before Close and Close can drain

	seedEntry(t, rdb, "E", "t1:keyE", true)
	m.Register(Registration{EntryID: "E", Sources: []string{"A"}, T1Key: "t1:keyE"})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	errc := make(chan error, 1)
	go func() {
		_, err := m.InvalidateWait(ctx, Event{ChunkID: "A"})
		errc <- err
	}()

	select {
	case <-hold.entered: // the writer is inside the purge of E
	case <-time.After(5 * time.Second):
		t.Fatal("the writer never reached the purge")
	}
	cancel()
	select {
	case err := <-errc:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("InvalidateWait returned %v, want context.Canceled", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("InvalidateWait did not return after the context was cancelled")
	}
	if !exists(t, rdb, "t2:E") {
		t.Fatal("t2:E is already gone: the purge was not held back, so this test shows nothing")
	}

	hold.Release()
	barrier(t, m)
	for _, k := range []string{"t2:E", "t1:keyE", "entry:E", "dep:A"} {
		if exists(t, rdb, k) {
			t.Fatalf("%s survived: the cancelled wait stopped the purge", k)
		}
	}
}

// After Close it is an error, as for Invalidate, and nothing is purged.
func TestInvalidateWaitAfterCloseFails(t *testing.T) {
	rdb := testRedis(t)
	m := newMap(t, rdb, realPurger(rdb), 4)
	seedEntry(t, rdb, "E", "t1:keyE", true)
	m.Register(Registration{EntryID: "E", Sources: []string{"A"}, T1Key: "t1:keyE"})
	if err := m.Close(context.Background()); err != nil { // drains the registration
		t.Fatal(err)
	}

	res, err := m.InvalidateWait(context.Background(), Event{ChunkID: "A"})
	if err == nil {
		t.Fatalf("InvalidateWait after Close returned %#v and no error", res)
	}
	if m.Invalidated("E") {
		t.Fatal("E is tombstoned by an invalidation that was refused")
	}
	if !exists(t, rdb, "t2:E") || !exists(t, rdb, "t1:keyE") || !exists(t, rdb, "dep:A") {
		t.Fatal("a refused invalidation purged something")
	}
}
