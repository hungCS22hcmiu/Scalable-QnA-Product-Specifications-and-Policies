package deps

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"sync"
	"sync/atomic"
	"time"

	"github.com/redis/go-redis/v9"
)

// Redis key prefixes of the dependency region (interfaces.md §E). They appear in THIS file only:
// the grep in the task's done condition 6 depends on it, and so does the invariant that one
// goroutine writes these keys.
const (
	depPrefix   = "dep:"
	entryPrefix = "entry:"
)

// Registration is what a write-back tells the map: this entry depends on these source chunks.
type Registration struct {
	EntryID string
	Sources []string
	T1Key   string

	// DatasetEpoch is the epoch the generation's chunks were read under. When an EpochSource is set
	// (SetEpochSource), the writer compares it with the file's value and refuses a registration that
	// differs: an edit landed between the write-back and this registration (item 4.2, ADR-008).
	DatasetEpoch uint64
}

// Event is one source edit, as in interfaces.md §E. Only ChunkID drives the purge; the other fields
// are recorded for item 4.4's update set and are never a gate (change_type is measured, not used).
type Event struct {
	ChunkID        string
	DocID          string
	ChangeType     string
	NewText        string
	DatasetVersion string
	TS             time.Time
}

// Purger removes one entry from both cache tiers. *cache.Store satisfies it. Taking an interface
// keeps deps/ free of any internal import: cache/ keeps owning the key layout of both tiers.
type Purger interface {
	PurgeEntry(ctx context.Context, entryID, t1Key string) error
}

type invalidateResult struct {
	ids []string
	err error
}

// op is one message to the writer: a registration or an invalidation, never both.
type op struct {
	reg *Registration
	ev  *Event
	ack chan invalidateResult // buffered (1), so the writer never blocks on a caller that left
}

// Map is the dependency map. ONE goroutine (run) writes dep:* and entry:*. Everything else talks to
// it through a channel, so a registration can never race a purge on the same key.
//
// Redis dep:{chunk_id} stays the authority for "who depends on this chunk", so an entry written by
// an earlier gateway process is purged too. The in-process snapshot is not a mirror of that map. It
// holds only the entry IDs that have been invalidated, which is all the hit path needs to ask.
type Map struct {
	rdb   *redis.Client
	purge Purger

	ch   chan op
	done chan struct{}

	mu     sync.RWMutex // guards closed and the send/close of ch
	closed bool

	// snap is copy-on-write: the writer builds a new set, stores it, and never mutates it again.
	// A reader does one atomic load and one lookup, with no lock and no Redis call.
	snap atomic.Pointer[map[string]struct{}]

	// epoch is the source the writer checks a registration against. nil until SetEpochSource, which
	// leaves the late check off (item 4.1's tests run that way).
	epoch atomic.Pointer[EpochSource]

	dropped        atomic.Int64
	registerErrors atomic.Int64
	purgeErrors    atomic.Int64
	lateDiscards   atomic.Int64
}

// New builds the map and starts its writer goroutine. queue is the channel capacity.
func New(rdb *redis.Client, p Purger, queue int) *Map {
	if queue < 0 {
		queue = 0
	}
	m := &Map{
		rdb:   rdb,
		purge: p,
		ch:    make(chan op, queue),
		done:  make(chan struct{}),
	}
	empty := map[string]struct{}{}
	m.snap.Store(&empty)
	go m.run()
	return m
}

// Register records that EntryID depends on every chunk in Sources. It blocks while the queue is full
// and returns once the registration is queued, not once Redis has it.
//
// ⚠️ It takes NO context, on purpose. The write-back runs inside the coalesced generation, and a
// client that left cancels its context. A registration that gave up on a cancelled context would
// leave the entry in Redis with no dependency record, so no purge could ever reach it -- completeness
// below 1 with no error. It waits on the channel instead, and the writer only stops at Close.
//
// After Close the registration is counted in Dropped() and logged. It is never dropped with no trace.
func (m *Map) Register(r Registration) {
	m.mu.RLock()
	if m.closed {
		m.mu.RUnlock()
		m.dropped.Add(1)
		log.Printf("deps: registration of %s refused, the map is closed (counted in Dropped)", r.EntryID)
		return
	}
	m.ch <- op{reg: &r}
	m.mu.RUnlock()
}

// Invalidate purges every entry that depends on ev.ChunkID, from both tiers. It returns the IDs it
// found once their tombstones are visible to Invalidated -- the Redis purge runs after that, off the
// caller's path. Calling it after Close is an error and purges nothing.
func (m *Map) Invalidate(ev Event) ([]string, error) {
	m.mu.RLock()
	if m.closed {
		m.mu.RUnlock()
		return nil, errors.New("deps: map is closed, invalidation refused")
	}
	ack := make(chan invalidateResult, 1)
	m.ch <- op{ev: &ev, ack: ack}
	m.mu.RUnlock()

	res := <-ack
	return res.ids, res.err
}

// SetEpochSource turns on the writer's late check. A registration whose DatasetEpoch differs from the
// source's value, or whose read fails, is not registered: the writer tombstones the entry and purges
// it from both tiers instead. Safe to call while the writer runs. A nil source turns the check off.
func (m *Map) SetEpochSource(src EpochSource) {
	if src == nil {
		m.epoch.Store(nil)
		return
	}
	m.epoch.Store(&src)
}

// Invalidated reports whether entryID has been invalidated in this process. One atomic load and one
// map lookup: no lock, no Redis. The hit path reads Redis first and asks this second, so a hit that
// could still see a purged entry also sees its tombstone.
func (m *Map) Invalidated(entryID string) bool {
	_, ok := (*m.snap.Load())[entryID]
	return ok
}

// Close stops intake, lets the writer drain the queue and waits for it. A second call returns nil.
func (m *Map) Close(ctx context.Context) error {
	m.mu.Lock()
	if m.closed {
		m.mu.Unlock()
		return nil
	}
	m.closed = true
	close(m.ch)
	m.mu.Unlock()

	select {
	case <-m.done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// Dropped counts registrations refused because the map was closed.
func (m *Map) Dropped() int64 { return m.dropped.Load() }

// RegisterErrors counts registrations whose Redis write failed. The entry then has no dependency
// record: the same hole as a dropped registration.
func (m *Map) RegisterErrors() int64 { return m.registerErrors.Load() }

// PurgeErrors counts Redis calls that failed during a purge. The tombstone stays, so this process
// still refuses the entry; a restarted process would not.
func (m *Map) PurgeErrors() int64 { return m.purgeErrors.Load() }

// LateDiscards counts registrations the writer refused because the dataset epoch had advanced since
// the write-back's check (interfaces.md §E, the late rule). Each one is a stale entry that was
// written to the tiers and then purged. They are discarded write-backs, not incompleteness.
func (m *Map) LateDiscards() int64 { return m.lateDiscards.Load() }

// run is the one writer. It handles registrations and invalidations in arrival order.
func (m *Map) run() {
	defer close(m.done)
	ctx := context.Background()
	for o := range m.ch {
		switch {
		case o.reg != nil:
			m.applyRegistration(ctx, *o.reg)
		case o.ev != nil:
			m.applyInvalidation(ctx, *o.ev, o.ack)
		}
	}
}

// applyRegistration writes dep:{c} for each source and entry:{E}, in one transaction. An entry with
// no sources writes entry:{E} only: it depends on no chunk, so no event can purge it, which is right.
//
// With an epoch source set it checks first (the late rule, item 4.2). The write-back guard in httpapi
// passed, but an edit can advance the epoch and run its Invalidate before this registration lands. That
// Invalidate could not see the entry, so nothing would ever purge it. A mismatch, or a read error
// (fail closed), tombstones the entry and purges it from both tiers, and writes no dep: or entry:
// record.
func (m *Map) applyRegistration(ctx context.Context, r Registration) {
	if src := m.epoch.Load(); src != nil {
		now, err := (*src).Current()
		if err != nil || now != r.DatasetEpoch {
			m.discardLate(ctx, r, now, err)
			return
		}
	}

	sources := r.Sources
	if sources == nil {
		sources = []string{}
	}
	raw, err := json.Marshal(sources)
	if err != nil {
		m.registerErrors.Add(1)
		log.Printf("deps: registering %s: encoding sources: %v (counted in RegisterErrors)", r.EntryID, err)
		return
	}

	pipe := m.rdb.TxPipeline()
	for _, c := range sources {
		pipe.SAdd(ctx, depPrefix+c, r.EntryID)
	}
	pipe.HSet(ctx, entryPrefix+r.EntryID, map[string]any{
		"t1_key":           r.T1Key,
		"source_chunk_ids": string(raw),
	})
	if _, err := pipe.Exec(ctx); err != nil {
		m.registerErrors.Add(1)
		log.Printf("deps: registering %s: %v (counted in RegisterErrors)", r.EntryID, err)
	}
}

// discardLate refuses a registration made under an epoch that is no longer current.
func (m *Map) discardLate(ctx context.Context, r Registration, now uint64, readErr error) {
	m.tombstone(r.EntryID)
	if err := m.purge.PurgeEntry(ctx, r.EntryID, r.T1Key); err != nil {
		m.purgeFailed(r.EntryID, "purging a late registration", err)
	}
	m.lateDiscards.Add(1)
	if readErr != nil {
		log.Printf("deps: late registration of %s discarded: epoch read failed: %v (counted in LateDiscards)", r.EntryID, readErr)
		return
	}
	log.Printf("deps: late registration of %s discarded: stamped epoch %d, current %d (counted in LateDiscards)", r.EntryID, r.DatasetEpoch, now)
}

// tombstone adds ids to the invalidated set: copy, add, atomic swap. Only the writer calls it, so
// there is no concurrent writer to lose an update to. A reader holds the old set or the new one.
func (m *Map) tombstone(ids ...string) {
	if len(ids) == 0 {
		return
	}
	old := *m.snap.Load()
	next := make(map[string]struct{}, len(old)+len(ids))
	for k := range old {
		next[k] = struct{}{}
	}
	for _, id := range ids {
		next[id] = struct{}{}
	}
	m.snap.Store(&next)
}

// applyInvalidation is the purge. Order matters:
//
//  1. SMEMBERS dep:{chunk}      who depends on it
//  2. swap the snapshot         tombstones visible BEFORE anything is deleted
//  3. ack the caller            it may now rely on the entries being refused
//  4. purge each entry          both tiers, then entry:{E}
//  5. DEL dep:{chunk}
//
// A Redis error on one entry is counted and logged, and the loop goes on. The tombstone stays.
func (m *Map) applyInvalidation(ctx context.Context, ev Event, ack chan invalidateResult) {
	ids, err := m.rdb.SMembers(ctx, depPrefix+ev.ChunkID).Result()
	if err != nil {
		ack <- invalidateResult{err: err}
		return
	}

	m.tombstone(ids...)
	ack <- invalidateResult{ids: ids}

	for _, id := range ids {
		t1Key, err := m.rdb.HGet(ctx, entryPrefix+id, "t1_key").Result()
		if err != nil && !errors.Is(err, redis.Nil) {
			m.purgeFailed(id, "reading t1_key", err)
			continue
		}
		// An empty t1Key (no entry:{E} record, or an empty field) makes the Purger read t2:{E}.
		if err := m.purge.PurgeEntry(ctx, id, t1Key); err != nil {
			// Keep entry:{E} when the tiers were not purged: it still holds the t1_key.
			m.purgeFailed(id, "purging tiers", err)
			continue
		}
		if err := m.rdb.Del(ctx, entryPrefix+id).Err(); err != nil {
			m.purgeFailed(id, "deleting entry record", err)
		}
	}

	if err := m.rdb.Del(ctx, depPrefix+ev.ChunkID).Err(); err != nil {
		m.purgeFailed(ev.ChunkID, "deleting dependency set", err)
	}
}

func (m *Map) purgeFailed(what, step string, err error) {
	m.purgeErrors.Add(1)
	log.Printf("deps: purge of %s failed while %s: %v (counted in PurgeErrors)", what, step, err)
}
