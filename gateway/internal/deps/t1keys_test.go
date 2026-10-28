package deps

import (
	"context"
	"testing"

	"github.com/hung/thesis/gateway/internal/cache"
)

// Item 4.3, done condition 5 (the end-to-end half). An entry that holds a miss key and a promoted
// key is invalidated through the real dependency map and the real cache.Store as its Purger. Afterwards
// no Tier-1 key names the entry, and its set is gone.
func TestInvalidateDropsPromotedKey(t *testing.T) {
	rdb := testRedis(t)
	ctx := context.Background()
	store := cache.NewStore(rdb, 768)
	m := newMap(t, rdb, store, 16)

	const q1, q2, pid = "does it have anc", "is anc on this one", "p1"
	k1 := cache.Key(cache.Normalize(q1), pid)
	k2 := cache.Key(cache.Normalize(q2), pid)

	// E is written the way the handler writes it: a miss Put, its t2: record, then a promoted Put.
	if err := store.Put(ctx, q1, pid, cache.Entry{Answer: "a", EntryID: "E"}); err != nil {
		t.Fatal(err)
	}
	if err := rdb.HSet(ctx, "t2:E", map[string]any{"t1_key": k1, "answer": "a"}).Err(); err != nil {
		t.Fatal(err)
	}
	if err := store.Put(ctx, q2, pid, cache.Entry{Answer: "a", EntryID: "E", Promotion: true}); err != nil {
		t.Fatal(err)
	}
	if err := store.Touch(ctx, "E", 1); err != nil {
		t.Fatal(err)
	}
	for _, k := range []string{k1, k2} {
		if !isMember(t, rdb, "lru:t1keys:E", k) {
			t.Fatalf("setup: lru:t1keys:E does not list %s", k)
		}
	}

	m.Register(Registration{EntryID: "E", Sources: []string{"A"}, T1Key: k1})
	barrier(t, m)
	if _, err := m.Invalidate(Event{ChunkID: "A"}); err != nil {
		t.Fatal(err)
	}
	barrier(t, m)

	for _, k := range []string{k1, k2, "t2:E", "lru:t1keys:E", "entry:E"} {
		if exists(t, rdb, k) {
			t.Fatalf("%s survived the purge", k)
		}
	}
	if inLRU(t, rdb, "E") {
		t.Fatal("E is still in lru:entries")
	}

	// No Tier-1 key of any name may still point at E: scan them all.
	iter := rdb.Scan(ctx, 0, "t1:*", 100).Iterator()
	for iter.Next(ctx) {
		if id, err := rdb.HGet(ctx, iter.Val(), "entry_id").Result(); err == nil && id == "E" {
			t.Fatalf("%s still names E after the purge", iter.Val())
		}
	}
	if err := iter.Err(); err != nil {
		t.Fatal(err)
	}
}
