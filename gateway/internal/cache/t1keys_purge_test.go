package cache

import (
	"context"
	"reflect"
	"testing"
	"time"
)

// Item 4.3. The purge removes every Tier-1 pointer of an entry, and only the ones that still name it.

// DC 5, the cache half. E has a miss key and a promoted key. PurgeEntry(E, "") deletes both, the set,
// t2:E and the lru:entries member, and leaves another entry alone.
func TestPurgeDropsEveryTier1Key(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()

	k1, k2 := fullEntry(t, s, "E", "e miss question", "e promoted question")
	k3, k4 := fullEntry(t, s, "G", "g miss question", "g promoted question")
	for _, id := range []string{"E", "G"} {
		if err := s.Touch(ctx, id, time.Now().UnixNano()); err != nil {
			t.Fatal(err)
		}
	}
	gBefore := snapshotEntry(t, s, "G", k3, k4)

	if err := s.PurgeEntry(ctx, "E", ""); err != nil {
		t.Fatal(err)
	}

	requireExists(t, s, 0, k1, k2, tier2KeyPrefix+"E", t1KeysKey("E"))
	if lruHas(t, s, "E") {
		t.Fatal("E is still in lru:entries")
	}
	if gAfter := snapshotEntry(t, s, "G", k3, k4); !reflect.DeepEqual(gBefore, gAfter) {
		t.Fatalf("the purge of E changed G:\nbefore %v\nafter  %v", gBefore, gAfter)
	}
}

// DC 5. The promoted key was taken over by a newer entry E2, so the purge of E must leave it, while
// still removing the miss key and everything else of E.
func TestPurgeDropsLeaveAReusedKey(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()

	k1, k2 := fullEntry(t, s, "E", "e miss question", "e promoted question")
	if err := s.Touch(ctx, "E", time.Now().UnixNano()); err != nil {
		t.Fatal(err)
	}
	if err := s.rdb.HSet(ctx, k2, "entry_id", "E2").Err(); err != nil {
		t.Fatal(err)
	}

	if err := s.PurgeEntry(ctx, "E", ""); err != nil {
		t.Fatal(err)
	}

	requireExists(t, s, 1, k2)
	if got, err := s.rdb.HGet(ctx, k2, "entry_id").Result(); err != nil || got != "E2" {
		t.Fatalf("%s entry_id = %q (err %v), want it left naming E2", k2, got, err)
	}
	requireExists(t, s, 0, k1, tier2KeyPrefix+"E", t1KeysKey("E"))
	if lruHas(t, s, "E") {
		t.Fatal("E is still in lru:entries")
	}
}
