package deps

import (
	"errors"
	"sync"
	"testing"
)

// fakeEpoch is an EpochSource a test controls: a value, or an error.
type fakeEpoch struct {
	mu  sync.Mutex
	v   uint64
	err error
}

func (f *fakeEpoch) Current() (uint64, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.v, f.err
}

// The late rule (item 4.2, interfaces.md §E). The write-back guard in httpapi passed, then an edit
// advanced the epoch and ran its Invalidate before this entry was registered. That Invalidate could not
// see the entry, so without the writer's own check nothing would ever purge it, and no error would say so.
// The entry is already in both tiers when the registration arrives, which is how these tests seed it.

func TestLateRegistrationIsPurged(t *testing.T) {
	rdb := testRedis(t)
	m := newMap(t, rdb, realPurger(rdb), 16)
	m.SetEpochSource(&fakeEpoch{v: 8})
	seedEntry(t, rdb, "E", "t1:k", true)

	m.Register(Registration{EntryID: "E", Sources: []string{"A", "B"}, T1Key: "t1:k", DatasetEpoch: 7})
	barrier(t, m)

	for _, key := range []string{"t1:k", "t2:E", "entry:E", "dep:A", "dep:B"} {
		if exists(t, rdb, key) {
			t.Errorf("%s still exists after a late registration", key)
		}
	}
	if inLRU(t, rdb, "E") {
		t.Error("E is still in lru:entries")
	}
	if !m.Invalidated("E") {
		t.Error("E is not tombstoned, so a hit on it would be served")
	}
	if got := m.LateDiscards(); got != 1 {
		t.Errorf("LateDiscards() = %d, want 1", got)
	}
}

func TestLateRegistrationReadErrorPurges(t *testing.T) {
	rdb := testRedis(t)
	m := newMap(t, rdb, realPurger(rdb), 16)
	m.SetEpochSource(&fakeEpoch{err: errors.New("epoch file unreadable")})
	seedEntry(t, rdb, "E", "t1:k", true)

	m.Register(Registration{EntryID: "E", Sources: []string{"A", "B"}, T1Key: "t1:k", DatasetEpoch: 7})
	barrier(t, m)

	for _, key := range []string{"t1:k", "t2:E", "entry:E", "dep:A", "dep:B"} {
		if exists(t, rdb, key) {
			t.Errorf("%s still exists after a registration whose epoch read failed", key)
		}
	}
	if inLRU(t, rdb, "E") {
		t.Error("E is still in lru:entries")
	}
	if !m.Invalidated("E") {
		t.Error("E is not tombstoned")
	}
	if got := m.LateDiscards(); got != 1 {
		t.Errorf("LateDiscards() = %d, want 1", got)
	}
}

// TestLateRegistrationCurrentEpochIsKept is the guard against over-fixing: a registration stamped
// with the current epoch is registered as before, and nothing is purged.
func TestLateRegistrationCurrentEpochIsKept(t *testing.T) {
	rdb := testRedis(t)
	m := newMap(t, rdb, realPurger(rdb), 16)
	m.SetEpochSource(&fakeEpoch{v: 7})
	seedEntry(t, rdb, "E", "t1:k", true)

	m.Register(Registration{EntryID: "E", Sources: []string{"A", "B"}, T1Key: "t1:k", DatasetEpoch: 7})
	barrier(t, m)

	for _, key := range []string{"dep:A", "dep:B", "entry:E", "t1:k", "t2:E"} {
		if !exists(t, rdb, key) {
			t.Errorf("%s is missing after a registration under the current epoch", key)
		}
	}
	if !isMember(t, rdb, "dep:A", "E") || !isMember(t, rdb, "dep:B", "E") {
		t.Error("E is not listed under both of its sources")
	}
	if got := m.LateDiscards(); got != 0 {
		t.Errorf("LateDiscards() = %d, want 0", got)
	}
	if m.Invalidated("E") {
		t.Error("E is tombstoned although its epoch is current")
	}
}
