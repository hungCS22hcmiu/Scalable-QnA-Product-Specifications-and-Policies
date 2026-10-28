package cache

import (
	"context"
	"reflect"
	"sort"
	"testing"
	"time"
)

// Item 4.3. Eviction removes every Tier-1 pointer of a victim, and only the ones that still name it.

// fullEntry writes entry id the way a miss and a later Tier-2 hit do: a miss Put under q1, the t2:
// record carrying that key, and a promoted Put under q2. It returns the two Tier-1 keys.
func fullEntry(t *testing.T, s *Store, id, q1, q2 string) (miss, promoted string) {
	t.Helper()
	ctx := context.Background()
	if err := s.Put(ctx, q1, "p1", Entry{Answer: "a-" + id, EntryID: id}); err != nil {
		t.Fatal(err)
	}
	liveTier2(t, s, id, t1Q(q1))
	if err := s.Put(ctx, q2, "p1", Entry{Answer: "a-" + id, EntryID: id, Promotion: true}); err != nil {
		t.Fatal(err)
	}
	return t1Q(q1), t1Q(q2)
}

// snapshotEntry returns every field of the keys that belong to one entry, plus its lru:entries score,
// so a test can show that an entry it did not evict is byte for byte unchanged.
func snapshotEntry(t *testing.T, s *Store, id string, t1Keys ...string) map[string]any {
	t.Helper()
	ctx := context.Background()
	out := map[string]any{}
	for _, k := range append([]string{tier2KeyPrefix + id}, t1Keys...) {
		h, err := s.rdb.HGetAll(ctx, k).Result()
		if err != nil {
			t.Fatal(err)
		}
		out[k] = h
	}
	out[t1KeysKey(id)] = setMembers(t, s, t1KeysKey(id))
	score, err := s.rdb.ZScore(ctx, lruKey, id).Result()
	if err != nil {
		t.Fatalf("%s is not in lru:entries: %v", id, err)
	}
	out[lruKey] = score
	return out
}

// DC 3. E has a t2: record and two Tier-1 keys; F is Tier-1 only; G is the newest. Trimming to one
// evicts E and F, and leaves neither a Tier-1 key, a t2: record, a set nor an lru:entries member.
func TestTrimDropsEveryTier1Key(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	base := time.Now()

	k1, k2 := fullEntry(t, s, "E", "e miss question", "e promoted question")
	k3 := t1Q("f only question")
	if err := s.Put(ctx, "f only question", "p1", Entry{Answer: "a-F", EntryID: "F"}); err != nil {
		t.Fatal(err)
	}
	k4, k5 := fullEntry(t, s, "G", "g miss question", "g promoted question")

	// Oldest to newest: E, F, G. The handler touches after each write.
	for i, id := range []string{"E", "F", "G"} {
		if err := s.Touch(ctx, id, base.Add(time.Duration(i-3)*time.Minute).UnixNano()); err != nil {
			t.Fatal(err)
		}
	}
	gBefore := snapshotEntry(t, s, "G", k4, k5)

	evicted, err := s.TrimToCapacity(ctx, 1)
	if err != nil {
		t.Fatal(err)
	}
	if len(evicted) != 2 || evicted[0].EntryID != "E" || evicted[1].EntryID != "F" {
		t.Fatalf("evicted %+v, want exactly E then F", evicted)
	}

	requireExists(t, s, 0, k1, k2, k3, tier2KeyPrefix+"E", tier2KeyPrefix+"F", t1KeysKey("E"), t1KeysKey("F"))
	for _, id := range []string{"E", "F"} {
		if lruHas(t, s, id) {
			t.Fatalf("%s is still in lru:entries", id)
		}
	}

	wantE := []string{k1, k2}
	sort.Strings(wantE)
	gotE := append([]string(nil), evicted[0].T1Keys...)
	sort.Strings(gotE)
	if !reflect.DeepEqual(gotE, wantE) {
		t.Fatalf("E T1Keys = %v, want %v", gotE, wantE)
	}
	if evicted[0].T1Key != k1 {
		t.Fatalf("E T1Key = %q, want the t2: record's t1_key %q", evicted[0].T1Key, k1)
	}
	if !reflect.DeepEqual(evicted[1].T1Keys, []string{k3}) {
		t.Fatalf("F T1Keys = %v, want [%s]", evicted[1].T1Keys, k3)
	}
	if evicted[1].T1Key != "" {
		t.Fatalf("F T1Key = %q, want empty: a Tier-1-only entry has no t2: record", evicted[1].T1Key)
	}

	if gAfter := snapshotEntry(t, s, "G", k4, k5); !reflect.DeepEqual(gBefore, gAfter) {
		t.Fatalf("G changed:\nbefore %v\nafter  %v", gBefore, gAfter)
	}
}

// DC 4. Tier 1 is keyed by the normalised query, so a newer entry can own a key that E's set lists.
// Evicting E must leave that key alone, and still remove the rest of E.
func TestTrimDropsLeaveAReusedKey(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	base := time.Now()

	k1, k2 := fullEntry(t, s, "E", "e miss question", "e promoted question")
	fullEntry(t, s, "G", "g miss question", "g promoted question")
	for i, id := range []string{"E", "G"} {
		if err := s.Touch(ctx, id, base.Add(time.Duration(i-2)*time.Minute).UnixNano()); err != nil {
			t.Fatal(err)
		}
	}
	// A newer entry E2 now owns k1.
	if err := s.rdb.HSet(ctx, k1, "entry_id", "E2").Err(); err != nil {
		t.Fatal(err)
	}

	evicted, err := s.TrimToCapacity(ctx, 1)
	if err != nil {
		t.Fatal(err)
	}
	if len(evicted) != 1 || evicted[0].EntryID != "E" {
		t.Fatalf("evicted %+v, want exactly E", evicted)
	}

	requireExists(t, s, 1, k1)
	if got, err := s.rdb.HGet(ctx, k1, "entry_id").Result(); err != nil || got != "E2" {
		t.Fatalf("%s entry_id = %q (err %v), want it left naming E2", k1, got, err)
	}
	requireExists(t, s, 0, k2, tier2KeyPrefix+"E", t1KeysKey("E"))
	if lruHas(t, s, "E") {
		t.Fatal("E is still in lru:entries")
	}
	if !reflect.DeepEqual(evicted[0].T1Keys, []string{k2}) {
		t.Fatalf("E T1Keys = %v, want only the key it still owned, [%s]", evicted[0].T1Keys, k2)
	}
}
