package cache

import (
	"context"
	"strings"
	"testing"
)

// Item 4.3, done condition 7. After a mixed sequence of misses, Tier-1-only writes, promotions, a trim
// and a purge, no Tier-1 key is left that points at an entry outside the cache, and no set is left for
// an entry outside the cache. The sequence runs through the real store and touches each entry after
// each write, as the handler does.
func TestNoOrphan(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()

	var tick int64
	touch := func(id string) {
		t.Helper()
		tick++
		if err := s.Touch(ctx, id, tick); err != nil {
			t.Fatal(err)
		}
	}
	// miss is one full-miss write-back: the Tier-1 key and, when withT2, the Tier-2 record.
	miss := func(id, question string, withT2 bool) {
		t.Helper()
		if err := s.Put(ctx, question, "p1", Entry{Answer: "a-" + id, EntryID: id}); err != nil {
			t.Fatal(err)
		}
		if withT2 {
			liveTier2(t, s, id, t1Q(question))
		}
		touch(id)
	}
	promote := func(id, question string) {
		t.Helper()
		if err := s.Put(ctx, question, "p1", Entry{Answer: "a-" + id, EntryID: id, Promotion: true}); err != nil {
			t.Fatal(err)
		}
	}

	// Four full entries and two Tier-1 only (the embedding failed, so there is no t2: record).
	miss("F1", "f1 question", true)
	miss("T1", "t1 only question", false)
	miss("F2", "f2 question", true)
	miss("F3", "f3 question", true)
	miss("T2", "t2 only question", false)
	miss("F4", "f4 question", true)

	// Two promotions of live entries. Each is a Tier-2 hit, so the handler touches the entry too.
	promote("F4", "f4 paraphrase")
	touch("F4")
	promote("F3", "f3 paraphrase")
	touch("F3")

	// The oldest three by access are F1, T1 and F2.
	evicted, err := s.TrimToCapacity(ctx, 3)
	if err != nil {
		t.Fatal(err)
	}
	if len(evicted) != 3 {
		t.Fatalf("evicted %+v, want three victims", evicted)
	}

	// A promotion of F2, which the trim has just removed, must write nothing.
	promote("F2", "f2 paraphrase")
	requireExists(t, s, 0, t1Q("f2 paraphrase"), t1KeysKey("F2"))

	// Purge one of the entries that is left.
	if err := s.PurgeEntry(ctx, "F4", ""); err != nil {
		t.Fatal(err)
	}

	members, err := s.rdb.ZRange(ctx, lruKey, 0, -1).Result()
	if err != nil {
		t.Fatal(err)
	}
	live := map[string]bool{}
	for _, id := range members {
		live[id] = true
	}
	if len(live) != 2 || !live["T2"] || !live["F3"] {
		t.Fatalf("lru:entries = %v, want exactly T2 and F3", members)
	}

	// Every t1:* key names an entry that is a member of lru:entries.
	t1Count := 0
	it := s.rdb.Scan(ctx, 0, "t1:*", 100).Iterator()
	for it.Next(ctx) {
		t1Count++
		id, err := s.rdb.HGet(ctx, it.Val(), "entry_id").Result()
		if err != nil {
			t.Fatalf("%s: reading entry_id: %v", it.Val(), err)
		}
		if !live[id] {
			t.Fatalf("orphan: %s names %q, which is not in lru:entries", it.Val(), id)
		}
	}
	if err := it.Err(); err != nil {
		t.Fatal(err)
	}
	// T2 holds one Tier-1 key and F3 holds two. A scan that found none would pass the loop above for
	// the wrong reason.
	if t1Count != 3 {
		t.Fatalf("%d t1:* keys remain, want 3 (T2: 1, F3: 2)", t1Count)
	}

	// Every lru:t1keys:* set belongs to such a member, and every key it lists exists and names it.
	setCount := 0
	it = s.rdb.Scan(ctx, 0, t1KeysPrefix+"*", 100).Iterator()
	for it.Next(ctx) {
		setCount++
		id := strings.TrimPrefix(it.Val(), t1KeysPrefix)
		if !live[id] {
			t.Fatalf("orphan set: %s belongs to %q, which is not in lru:entries", it.Val(), id)
		}
		for _, k := range setMembers(t, s, it.Val()) {
			got, err := s.rdb.HGet(ctx, k, "entry_id").Result()
			if err != nil || got != id {
				t.Fatalf("%s lists %s, whose entry_id is %q (err %v), want %s", it.Val(), k, got, err, id)
			}
		}
	}
	if err := it.Err(); err != nil {
		t.Fatal(err)
	}
	if setCount != 2 {
		t.Fatalf("%d lru:t1keys:* sets remain, want 2 (T2 and F3)", setCount)
	}
}
