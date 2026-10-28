package httpapi

// Item 4.1's hit-path check and registration, driven through Ask with a fake dependency map. No Redis:
// the map's own behaviour belongs to deps/'s tests; what httpapi owes is asking it at the right two
// points, refusing what it says is invalidated, and registering every write-back.

import (
	"net/http"
	"reflect"
	"sync"
	"testing"

	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/deps"
)

// fakeDeps satisfies dependencyMap. It holds a set of invalidated entry IDs and remembers every
// registration, in order.
type fakeDeps struct {
	mu          sync.Mutex
	invalidated map[string]bool
	regs        []deps.Registration
}

var _ dependencyMap = (*fakeDeps)(nil)

func newFakeDeps(invalidated ...string) *fakeDeps {
	f := &fakeDeps{invalidated: map[string]bool{}}
	for _, id := range invalidated {
		f.invalidated[id] = true
	}
	return f
}

func (f *fakeDeps) Register(r deps.Registration) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.regs = append(f.regs, r)
}

func (f *fakeDeps) Invalidated(entryID string) bool {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.invalidated[entryID]
}

func (f *fakeDeps) registrations() []deps.Registration {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]deps.Registration(nil), f.regs...)
}

// A Tier-1 hit on an entry the map reports invalidated is NOT served. The request goes on as a Tier-1
// miss, so it reaches the embedder, and the record names the entry it refused.
func TestInvalidatedTier1HitIsNotServed(t *testing.T) {
	hs := newHarness(t, 1, 0)
	const q = "What is the Aurora kettle made of?"
	const staleID = "01STALETIER1ENTRY0000000001"
	hs.store.seedTier1(q, kettle.id, cache.Entry{
		Answer:         kettle.otherAnswer,
		SourceChunkIDs: kettle.answerSources(),
		ModelUsed:      testModel,
		EntryID:        staleID,
	})
	hs.h.Deps = newFakeDeps(staleID)
	hs.embedFresh(q)

	c := hs.ask(t, askReq{question: q, productID: kettle.id})
	hs.records(t)

	if c.w.Code != http.StatusOK {
		t.Fatalf("status %d, want 200: %s", c.w.Code, c.w.Body)
	}
	resp := c.response(t)
	if got := resp.text("answer"); got == kettle.otherAnswer {
		t.Fatalf("the invalidated Tier-1 answer %q was served", got)
	}
	if got := resp.text("cache"); got == "TIER1_HIT" {
		t.Fatalf("cache = TIER1_HIT for an invalidated entry")
	}

	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.str("invalidated_entry_id", staleID)
	if got := rec.text("entry_id"); got == staleID {
		t.Errorf("the record's entry_id is the invalidated entry; it should name the entry the miss wrote")
	}
	// It went on to Tier 2: the embedder ran, which a served Tier-1 hit never does.
	if calls, _ := hs.embedder.counts(); calls == 0 {
		t.Errorf("the embedder never ran: the request did not go on to Tier 2")
	}
}

// A Tier-2 candidate the map reports invalidated is dropped BEFORE it is judged: the request is a MISS
// with no cause, no candidate and no rule, and the record names the entry.
func TestInvalidatedTier2CandidateIsDropped(t *testing.T) {
	hs := newHarness(t, 1, 0)
	e := hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	hs.h.Deps = newFakeDeps(e.EntryID)

	c := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
	hs.records(t)

	// The search returns one candidate (k=1): it was found, and then dropped.
	if got := hs.store.callCount("NearestTier2InNamespace"); got != 1 {
		t.Fatalf("%d Tier-2 searches, want 1", got)
	}
	c.response(t).str("cache", "MISS")
	rec := c.record(t)
	rec.str("cache", "MISS")
	rec.null("refusal_cause")
	rec.absent("reuse_rule")
	rec.absent("candidate_entry_id")
	rec.null("similarity")
	rec.str("invalidated_entry_id", e.EntryID)
	if got := rec.text("entry_id"); got == e.EntryID {
		t.Errorf("the record's entry_id is the invalidated entry; it should name the entry the miss wrote")
	}
	if n := len(hs.rag.answerCalls()); n != 1 {
		t.Errorf("Answer called %d times, want 1: a dropped candidate is a miss", n)
	}
}

// A hit on any other entry is served as before, and the record carries no invalidated_entry_id.
func TestValidEntryIsStillServed(t *testing.T) {
	hs := newHarness(t, 1, 0)
	e := hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
	hs.h.Deps = newFakeDeps("01SOMEOTHERENTRY00000000001")

	c := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
	waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
	waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 1 })
	hs.records(t)

	c.response(t).str("cache", "TIER2_HIT")
	rec := c.record(t)
	rec.str("cache", "TIER2_HIT")
	rec.str("entry_id", e.EntryID)
	rec.absent("invalidated_entry_id")
	if n := len(hs.rag.answerCalls()); n != 0 {
		t.Errorf("Answer called %d times on a served hit", n)
	}
}

// Every write-back registers its entry once, with the entry's own identity: the record's entry_id,
// Answer's sources (not Retrieve's) and the Tier-1 key. The second request has no embedding, so it
// writes Tier 1 only -- and it must register too, or its entry is unpurgeable.
func TestMissRegistersItsEntry(t *testing.T) {
	hs := newHarness(t, 1, 0)
	fake := newFakeDeps()
	hs.h.Deps = fake

	const q1 = "Does the Aurora Kettle switch itself OFF?"
	const q2 = "Can I descale the Aurora kettle with citric acid?"
	hs.embedFresh(q1)
	first := hs.ask(t, askReq{question: q1, productID: kettle.id})
	if got := len(fake.registrations()); got != 1 {
		t.Fatalf("%d registrations after the first miss, want 1", got)
	}

	hs.embedder.failEverything() // no vector from here on: Tier 1 only
	second := hs.ask(t, askReq{question: q2, productID: kettle.id})
	hs.records(t)

	if got := hs.store.callCount("PutTier2"); got != 1 {
		t.Fatalf("%d Tier-2 writes, want 1 (the second miss has no vector)", got)
	}
	regs := fake.registrations()
	if len(regs) != 2 {
		t.Fatalf("%d registrations, want 2 (one per miss)", len(regs))
	}
	for i, c := range []*call{first, second} {
		rec := c.record(t)
		rec.str("cache", "MISS")
		want := deps.Registration{
			EntryID:      rec.text("entry_id"),
			Sources:      kettle.answerSources(),
			T1Key:        rec.text("t1_key"),
			DatasetEpoch: testEpoch,
		}
		if !reflect.DeepEqual(regs[i], want) {
			t.Errorf("registration %d = %+v, want %+v", i, regs[i], want)
		}
	}
	if regs[0].EntryID == regs[1].EntryID {
		t.Errorf("both misses registered entry %s", regs[0].EntryID)
	}
}
