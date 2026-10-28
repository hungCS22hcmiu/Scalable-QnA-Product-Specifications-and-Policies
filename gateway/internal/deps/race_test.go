package deps

import (
	"context"
	"fmt"
	"sync"
	"testing"

	"github.com/redis/go-redis/v9"
)

// DC 6. Registrations, invalidations and snapshot reads at once, under -race.
//
// The shape: 8 goroutines register 50 entries each over 10 chunks while 2 goroutines invalidate
// chunks and 4 goroutines read Invalidated in a loop. Then, once every registration has been queued,
// every chunk is invalidated once more: for those invalidations all registrations of the chunk are
// ahead of it in the one queue. Every ID any invalidation returned must then have no t2:, t1: or
// entry: record and a tombstone, and every registered entry must have been returned by some
// invalidation -- a registration that slipped past the writer would show as an entry no one purged.
func TestConcurrentRegisterInvalidateRead(t *testing.T) {
	const (
		registrars     = 8
		perRegistrar   = 50
		chunks         = 10
		invalidators   = 2
		earlyPerWorker = 20
		readers        = 4
	)
	rdb := testRedis(t)
	m := newMap(t, rdb, realPurger(rdb), 64)
	ctx := context.Background()

	chunkID := func(i int) string { return fmt.Sprintf("chunk-%d", i%chunks) }
	type entry struct {
		id      string
		t1Key   string
		sources []string
	}
	var all []entry
	for w := 0; w < registrars; w++ {
		for i := 0; i < perRegistrar; i++ {
			id := fmt.Sprintf("w%d-e%d", w, i)
			srcs := []string{chunkID(w*7 + i)}
			if second := chunkID(w + i*3); second != srcs[0] {
				srcs = append(srcs, second)
			}
			all = append(all, entry{id: id, t1Key: "t1:key-" + id, sources: srcs})
		}
	}

	// The cache state the purge has to remove.
	pipe := rdb.Pipeline()
	for _, e := range all {
		pipe.HSet(ctx, e.t1Key, map[string]any{"answer": "a", "entry_id": e.id})
		pipe.HSet(ctx, "t2:"+e.id, map[string]any{"t1_key": e.t1Key, "answer": "a"})
		pipe.ZAdd(ctx, "lru:entries", redis.Z{Score: 1, Member: e.id})
	}
	if _, err := pipe.Exec(ctx); err != nil {
		t.Fatal(err)
	}

	var (
		mu       sync.Mutex
		returned = map[string]bool{}
	)
	record := func(ids []string) {
		mu.Lock()
		defer mu.Unlock()
		for _, id := range ids {
			returned[id] = true
		}
	}

	stop := make(chan struct{})
	var readersWG sync.WaitGroup
	for r := 0; r < readers; r++ {
		readersWG.Add(1)
		go func() {
			defer readersWG.Done()
			seen := map[string]bool{}
			for {
				select {
				case <-stop:
					return
				default:
				}
				for _, e := range all {
					v := m.Invalidated(e.id)
					if seen[e.id] && !v {
						t.Errorf("tombstone for %s was lost", e.id)
						return
					}
					if v {
						seen[e.id] = true
					}
				}
			}
		}()
	}

	var writersWG sync.WaitGroup
	for w := 0; w < registrars; w++ {
		writersWG.Add(1)
		go func(w int) {
			defer writersWG.Done()
			for i := 0; i < perRegistrar; i++ {
				e := all[w*perRegistrar+i]
				m.Register(Registration{EntryID: e.id, Sources: e.sources, T1Key: e.t1Key})
			}
		}(w)
	}
	var invalidatorsWG sync.WaitGroup
	for g := 0; g < invalidators; g++ {
		invalidatorsWG.Add(1)
		go func(g int) {
			defer invalidatorsWG.Done()
			for k := 0; k < earlyPerWorker; k++ {
				ids, err := m.Invalidate(Event{ChunkID: chunkID(g*5 + k)})
				if err != nil {
					t.Errorf("early Invalidate: %v", err)
					return
				}
				record(ids)
			}
		}(g)
	}
	writersWG.Wait()
	invalidatorsWG.Wait()

	// Every registration is queued. Invalidate every chunk once more, two goroutines at a time.
	var finalWG sync.WaitGroup
	for g := 0; g < invalidators; g++ {
		finalWG.Add(1)
		go func(g int) {
			defer finalWG.Done()
			for c := g; c < chunks; c += invalidators {
				ids, err := m.Invalidate(Event{ChunkID: chunkID(c)})
				if err != nil {
					t.Errorf("final Invalidate: %v", err)
					return
				}
				record(ids)
			}
		}(g)
	}
	finalWG.Wait()
	barrier(t, m) // the purge of the last chunk runs after its ack
	close(stop)
	readersWG.Wait()

	for _, e := range all {
		if !returned[e.id] {
			t.Errorf("%s was registered but no invalidation returned it: the registration was lost", e.id)
			continue
		}
		if !m.Invalidated(e.id) {
			t.Errorf("%s was returned by an invalidation but is not tombstoned", e.id)
		}
		for _, k := range []string{"t2:" + e.id, e.t1Key, "entry:" + e.id} {
			if exists(t, rdb, k) {
				t.Errorf("%s survived the purge of every chunk", k)
			}
		}
		if inLRU(t, rdb, e.id) {
			t.Errorf("%s is still in lru:entries", e.id)
		}
	}
	if m.PurgeErrors() != 0 || m.RegisterErrors() != 0 || m.Dropped() != 0 {
		t.Errorf("counters: purge=%d register=%d dropped=%d, want all 0", m.PurgeErrors(), m.RegisterErrors(), m.Dropped())
	}
}
