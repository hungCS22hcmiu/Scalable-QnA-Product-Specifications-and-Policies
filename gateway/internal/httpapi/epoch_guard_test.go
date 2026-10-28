package httpapi

// Item 4.2's write-back guard, driven through Ask with a fake epoch source and 4.1's fake dependency
// map. No Redis: the epoch file's own behaviour belongs to deps/'s tests, and the writer's late check to
// deps/'s Redis tests. What httpapi owes is comparing Answer's epoch with the source's at write-back,
// discarding on ANY difference or read error, writing nothing when it discards, and flagging the record
// once.
//
// The failure each test guards is silent. A stale write-back that passes caches an answer over
// superseded text with no trace, and a discard that names an entry points every offline join at a record
// that never existed (docs/work/2026-10-28-epoch-guard/design.md section 3, failure modes 2, 7 and 8).

import (
	"bytes"
	"errors"
	"log"
	"net/http"
	"strings"
	"sync"
	"testing"

	"github.com/hung/thesis/gateway/internal/cache"
)

// fakeEpoch is an epochSource a test controls: a value, or an error.
type fakeEpoch struct {
	mu    sync.Mutex
	v     uint64
	err   error
	reads int
}

var _ epochSource = (*fakeEpoch)(nil)

func (f *fakeEpoch) Current() (uint64, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.reads++
	return f.v, f.err
}

func (f *fakeEpoch) readCount() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.reads
}

// logBuffer collects the process log for one test, under a lock: Ask logs from its own goroutine.
type logBuffer struct {
	mu  sync.Mutex
	buf bytes.Buffer
}

func (b *logBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.Write(p)
}

func (b *logBuffer) String() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.String()
}

func captureLog(t *testing.T) *logBuffer {
	t.Helper()
	b := &logBuffer{}
	prev := log.Writer()
	log.SetOutput(b)
	t.Cleanup(func() { log.SetOutput(prev) })
	return b
}

// guardHarness is the common setup: one permit, a fake dependency map, the epoch source under test, and
// a bounded cache (Capacity 2) so that a touch, which is skipped when the cache is unbounded, would be
// visible if a discarded write-back made one.
func guardHarness(t *testing.T, src epochSource) (*harness, *fakeDeps) {
	t.Helper()
	hs := newHarness(t, 1, 0)
	fd := newFakeDeps()
	hs.h.Deps = fd
	hs.h.Epoch = src
	hs.h.Capacity = 2
	return hs, fd
}

// assertNothingWritten checks that a discarded write-back reached no tier, no LRU and no dependency map.
func assertNothingWritten(t *testing.T, hs *harness, fd *fakeDeps) {
	t.Helper()
	for _, method := range []string{"Put", "PutTier2", "Touch", "TrimToCapacity"} {
		if n := hs.store.callCount(method); n != 0 {
			t.Errorf("%s called %d time(s) after a discarded write-back, want 0", method, n)
		}
	}
	if regs := fd.registrations(); len(regs) != 0 {
		t.Errorf("%d registration(s) after a discarded write-back, want 0: %+v", len(regs), regs)
	}
}

// assertDiscardedRecord checks what a client and an analysis see after a discard: the answer is served,
// and the record is a MISS with the flag set and no entry.
func assertDiscardedRecord(t *testing.T, c *call) {
	t.Helper()
	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
	}
	resp := c.response(t)
	resp.str("cache", "MISS")
	resp.str("answer", kettle.answer)
	resp.strs("sources", kettle.answerSources()) // the response still lists the answer's sources

	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.boolean("writeback_discarded", true)
	rec.str("entry_id", "")
	rec.null("entry_sources")
}

// An epoch that advanced between Retrieve and write-back: Answer reports testEpoch, the source says one
// more. Nothing is written and the record says so.
func TestEpochGuardDiscardsAdvancedEpoch(t *testing.T) {
	src := &fakeEpoch{v: testEpoch + 1}
	hs, fd := guardHarness(t, src)
	logs := captureLog(t)
	const q = "Does the Aurora kettle switch itself off?"
	hs.embedFresh(q)

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	assertDiscardedRecord(t, c)
	assertNothingWritten(t, hs, fd)
	if got := src.readCount(); got != 1 {
		t.Errorf("the epoch source was read %d times, want 1 (once per write-back)", got)
	}
	// The discard is logged with both epochs, so a run can show why a write-back was refused.
	if want := "answer epoch 7, current epoch 8"; !strings.Contains(logs.String(), want) {
		t.Errorf("the log has no %q; got:\n%s", want, logs.String())
	}
}

// Any mismatch discards, not only an advance. A source BEHIND Answer's epoch (the two services read
// different files, or the file stepped back) is just as wrong, and a guard that tested "now > stamped"
// would write this one back.
func TestEpochGuardDiscardsOlderEpoch(t *testing.T) {
	src := &fakeEpoch{v: testEpoch - 1}
	hs, fd := guardHarness(t, src)
	const q = "Does the Aurora kettle switch itself off?"
	hs.embedFresh(q)

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	assertDiscardedRecord(t, c)
	assertNothingWritten(t, hs, fd)
}

// The guard against over-fixing: equal epochs write back and register exactly as before, with the flag
// false and a real entry on the record.
func TestEpochGuardKeepsEqualEpoch(t *testing.T) {
	src := &fakeEpoch{v: testEpoch}
	hs, fd := guardHarness(t, src)
	const q = "Does the Aurora kettle switch itself off?"
	hs.embedFresh(q)

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
	}
	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.boolean("writeback_discarded", false)
	if id := rec.text("entry_id"); id == "" {
		t.Error("entry_id is empty although the write-back was kept")
	}
	rec.strs("entry_sources", kettle.answerSources())

	for method, want := range map[string]int{"Put": 1, "PutTier2": 1, "Touch": 1, "TrimToCapacity": 1} {
		if got := hs.store.callCount(method); got != want {
			t.Errorf("%s called %d time(s), want %d", method, got, want)
		}
	}
	regs := fd.registrations()
	if len(regs) != 1 {
		t.Fatalf("%d registrations, want 1", len(regs))
	}
	if regs[0].DatasetEpoch != testEpoch {
		t.Errorf("registration carries epoch %d, want %d", regs[0].DatasetEpoch, testEpoch)
	}
}

// A nil source turns the guard off: this is what every handler built as a literal gets, and what the
// older tests rely on. Answer's epoch is made to differ from Retrieve's here to show that no comparison
// of any kind happens.
func TestEpochGuardOffWithoutSource(t *testing.T) {
	hs, fd := guardHarness(t, nil)
	hs.rag.answerAtEpoch(testEpoch + 1)
	const q = "Does the Aurora kettle switch itself off?"
	hs.embedFresh(q)

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.boolean("writeback_discarded", false)
	if hs.store.callCount("Put") != 1 || hs.store.callCount("PutTier2") != 1 {
		t.Errorf("Put %d, PutTier2 %d; want 1 and 1 with the guard off",
			hs.store.callCount("Put"), hs.store.callCount("PutTier2"))
	}
	if len(fd.registrations()) != 1 {
		t.Errorf("%d registrations, want 1 with the guard off", len(fd.registrations()))
	}
}

// A source that cannot be read fails CLOSED: the write-back is discarded, flagged, and the error logged.
// Writing back on a failed read would let a stale answer through exactly when the file is unreadable.
func TestEpochGuardFailsClosedOnReadError(t *testing.T) {
	src := &fakeEpoch{err: errors.New("epoch file unreadable")}
	hs, fd := guardHarness(t, src)
	logs := captureLog(t)
	const q = "Does the Aurora kettle switch itself off?"
	hs.embedFresh(q)

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	assertDiscardedRecord(t, c)
	assertNothingWritten(t, hs, fd)
	if want := "epoch file unreadable"; !strings.Contains(logs.String(), want) {
		t.Errorf("the read error was not logged: no %q in\n%s", want, logs.String())
	}
}

// One discard, one flag. A leader and a coalesced follower share the discarded generation, but the
// write-back runs once, in the leader's closure, so only the leader's record carries
// writeback_discarded. Both name no entry, and both clients get the answer. A flag on the follower too
// would count every discard twice.
func TestEpochGuardFlagsLeaderOnly(t *testing.T) {
	src := &fakeEpoch{v: testEpoch + 1}
	hs, fd := guardHarness(t, src)
	const q = "Does the Aurora kettle switch itself off?"
	hs.embedFresh(q)
	g := hs.holdAnswers()
	key := cache.Key(cache.Normalize(q), kettle.id)

	first := hs.start(askReq{question: q, productID: kettle.id})
	second := hs.start(askReq{question: q, productID: kettle.id})
	waitFor(t, "the follower to wait on the leader", func() bool { return hs.h.Generations.Waiters(key) == 1 })
	g.open()
	hs.records(t)

	leaders, followers := 0, 0
	for _, c := range []*call{first, second} {
		if c.w.Code != http.StatusOK {
			t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
		}
		c.response(t).str("answer", kettle.answer)

		rec := c.record(t)
		rec.str("cache", "MISS")
		rec.str("entry_id", "")
		rec.null("entry_sources")
		if follower, _ := c.rec["coalesced"].(bool); follower {
			followers++
			rec.boolean("writeback_discarded", false)
		} else {
			leaders++
			rec.boolean("writeback_discarded", true)
		}
	}
	if leaders != 1 || followers != 1 {
		t.Fatalf("%d leader(s) and %d follower(s), want 1 and 1", leaders, followers)
	}
	assertNothingWritten(t, hs, fd)
	if got := src.readCount(); got != 1 {
		t.Errorf("the epoch source was read %d times, want 1: the follower's closure never runs", got)
	}
}
