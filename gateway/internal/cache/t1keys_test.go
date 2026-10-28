package cache

import (
	"context"
	"reflect"
	"sort"
	"testing"
)

// Item 4.3. Every Tier-1 key that names an entry is recorded in lru:t1keys:{entry_id}, and a
// promotion is written only while the entry's t2: record exists (interfaces.md §D, v0.19).

// t1Q builds the Tier-1 key of a question in product p1, the way Put does.
func t1Q(question string) string { return Key(Normalize(question), "p1") }

// setMembers returns the sorted members of a Redis SET.
func setMembers(t *testing.T, s *Store, key string) []string {
	t.Helper()
	m, err := s.rdb.SMembers(context.Background(), key).Result()
	if err != nil {
		t.Fatal(err)
	}
	sort.Strings(m)
	return m
}

// liveTier2 writes a bare t2:{entryID} record, as seed does, so a promotion has an entry to point at.
func liveTier2(t *testing.T, s *Store, entryID, t1Key string) {
	t.Helper()
	if err := s.rdb.HSet(context.Background(), tier2KeyPrefix+entryID, map[string]any{"t1_key": t1Key, "answer": "a"}).Err(); err != nil {
		t.Fatal(err)
	}
}

// DC 1. The miss write-back and the promotion each add their key to the entry's set, and both
// Tier-1 hashes name the entry.
func TestPutRecordsTier1Key(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	k1, k2 := t1Q("does it have anc"), t1Q("is anc on this one")

	if err := s.Put(ctx, "does it have anc", "p1", Entry{Answer: "a", EntryID: "E"}); err != nil {
		t.Fatal(err)
	}
	liveTier2(t, s, "E", k1)
	if err := s.Put(ctx, "is anc on this one", "p1", Entry{Answer: "a", EntryID: "E", Promotion: true}); err != nil {
		t.Fatal(err)
	}

	want := []string{k1, k2}
	sort.Strings(want)
	if got := setMembers(t, s, t1KeysKey("E")); !reflect.DeepEqual(got, want) {
		t.Fatalf("%s = %v, want exactly %v", t1KeysKey("E"), got, want)
	}
	for _, k := range want {
		if got, err := s.rdb.HGet(ctx, k, "entry_id").Result(); err != nil || got != "E" {
			t.Fatalf("%s entry_id = %q (err %v), want E", k, got, err)
		}
	}
}

// DC 2. With no t2:E a promotion writes neither the key nor the set member; with t2:E it writes both.
func TestPromotionNeedsTier2(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	k := t1Q("a repeated paraphrase")
	promote := func() error {
		return s.Put(ctx, "a repeated paraphrase", "p1", Entry{Answer: "a", EntryID: "E", Promotion: true})
	}

	if err := promote(); err != nil {
		t.Fatalf("a promotion of a removed entry is not an error, got %v", err)
	}
	requireExists(t, s, 0, k, t1KeysKey("E"))

	liveTier2(t, s, "E", "t1:miss")
	if err := promote(); err != nil {
		t.Fatal(err)
	}
	requireExists(t, s, 1, k, t1KeysKey("E"))
	if got := setMembers(t, s, t1KeysKey("E")); !reflect.DeepEqual(got, []string{k}) {
		t.Fatalf("%s = %v, want [%s]", t1KeysKey("E"), got, k)
	}
}

// A promotion with no EntryID has no t2: record to check and no set to join. It is an error, and it
// writes nothing.
func TestPromotionWithoutEntryIDFails(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()

	if err := s.Put(ctx, "some question", "p1", Entry{Answer: "a", Promotion: true}); err == nil {
		t.Fatal("a promotion with no EntryID returned nil, want an error")
	}
	if n, err := s.rdb.DBSize(ctx).Result(); err != nil || n != 0 {
		t.Fatalf("DBSize = %d (err %v), want 0: the failed promotion wrote something", n, err)
	}
}
