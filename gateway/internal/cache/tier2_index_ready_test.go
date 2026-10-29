package cache

import (
	"context"
	"fmt"
	"math/rand"
	"testing"
	"time"

	"github.com/hung/thesis/gateway/internal/testredis"
	"github.com/redis/go-redis/v9"
)

// Problem 3 of docs/work/2026-10-29-redis-index-lifecycle/ (RCA, evidence/rca/).
//
// FT.CREATE returns in under a millisecond and indexes the t2:* hashes that already exist in the
// BACKGROUND. A KNN sent before that scan ends returns nothing, or a different entry from the same
// namespace, with no error. So a gateway that starts on a warm cache serves its first requests from
// a partial index, and the Tier-2 hit rate looks lower for no visible reason. These tests pin the
// fix: EnsureCacheIndex returns only when the index is complete.
//
// They need DB 0, because the search module creates indexes only there, so they run on
// testredis.Client(t, 0): the throwaway server that `make test` starts, never :6379.

const (
	readyEntries = 1000
	readyFiller  = 500
	readyNames   = 10
)

type seededEntry struct {
	id, namespace string
	vec           []float32
}

// seedWarmCache writes readyEntries t2:* vector hashes (the schema's fields, through PutTier2) and
// readyFiller unrelated keys, so the background scan has real work and has to walk past keys it
// does not index. It writes before any index exists, which is the state after an index drop.
func seedWarmCache(t *testing.T, s *Store) []seededEntry {
	t.Helper()
	ctx := context.Background()
	rng := rand.New(rand.NewSource(20261029))
	out := make([]seededEntry, 0, readyEntries)
	for i := 0; i < readyEntries; i++ {
		vec := make([]float32, s.dim)
		for j := range vec {
			vec[j] = float32(rng.NormFloat64())
		}
		e := seededEntry{id: fmt.Sprintf("ready%04d", i), namespace: fmt.Sprintf("ns-ready-%d", i%readyNames), vec: vec}
		err := s.PutTier2(ctx, Tier2Entry{
			EntryID:        e.id,
			QueryText:      fmt.Sprintf("question %d", i),
			Answer:         "a",
			SourceChunkIDs: []string{fmt.Sprintf("doc-%d#chunk-0", i)},
			T1Key:          fmt.Sprintf("t1:ready%04d", i),
			DatasetEpoch:   1,
			Namespace:      e.namespace,
			Lane:           "STRICT",
		}, vec)
		if err != nil {
			t.Fatalf("seeding entry %d: %v", i, err)
		}
		out = append(out, e)
	}
	pipe := s.rdb.Pipeline()
	for i := 0; i < readyFiller; i++ {
		pipe.Set(ctx, fmt.Sprintf("filler:%d", i), "x", 0)
	}
	if _, err := pipe.Exec(ctx); err != nil {
		t.Fatalf("seeding filler keys: %v", err)
	}
	return out
}

// dropCacheIndexAtEnd drops idx:cache without DD (the documents stay) when the test ends. It is
// registered after testredis.Client's own cleanup, so it runs first.
func dropCacheIndexAtEnd(t *testing.T, rdb *redis.Client) {
	t.Helper()
	t.Cleanup(func() { _ = rdb.FTDropIndex(context.Background(), CacheIndexName).Err() })
}

// requireComplete is the whole claim: at once, with no sleep, the index is finished and a search
// finds the entry that was written.
func requireComplete(t *testing.T, s *Store, seeded []seededEntry) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	info, err := s.rdb.FTInfo(ctx, CacheIndexName).Result()
	if err != nil {
		t.Fatalf("FT.INFO right after EnsureCacheIndex: %v", err)
	}
	if info.Indexing != 0 {
		t.Errorf("Indexing = %d right after EnsureCacheIndex returned (PercentIndexed %.3f): the index is still being built", info.Indexing, info.PercentIndexed)
	}
	if info.NumDocs != readyEntries {
		t.Errorf("NumDocs = %d right after EnsureCacheIndex returned, want %d", info.NumDocs, readyEntries)
	}

	// Entries spread across the keyspace, so a half-finished scan cannot pass by luck.
	for _, i := range []int{0, readyEntries / 2, readyEntries - 1} {
		want := seeded[i]
		got, err := s.NearestTier2InNamespace(ctx, want.vec, want.namespace, 1)
		if err != nil {
			t.Fatalf("NearestTier2InNamespace for %s: %v", want.id, err)
		}
		if len(got) != 1 || got[0].Entry.EntryID != want.id || got[0].Similarity < 0.999 {
			t.Errorf("searching entry %s in %s returned %+v, want that entry at similarity ~1", want.id, want.namespace, got)
		}
	}
}

func TestEnsureCacheIndexReturnsOnlyWhenIndexed(t *testing.T) {
	rdb := testredis.Client(t, 0)
	s := NewStore(rdb, 768)
	seeded := seedWarmCache(t, s)
	dropCacheIndexAtEnd(t, rdb)

	if err := s.EnsureCacheIndex(context.Background()); err != nil {
		t.Fatalf("EnsureCacheIndex: %v", err)
	}
	requireComplete(t, s, seeded)
}

// The second path: another process (or an earlier gateway start) created the index a moment ago and
// its scan is still running. FT.CREATE then answers "already exists", which used to count as ready.
func TestEnsureCacheIndexWaitsWhenItAlreadyExists(t *testing.T) {
	rdb := testredis.Client(t, 0)
	s := NewStore(rdb, 768)
	seeded := seedWarmCache(t, s)
	dropCacheIndexAtEnd(t, rdb)
	ctx := context.Background()

	// The same schema as EnsureCacheIndex, sent raw.
	if err := rdb.Do(ctx, "FT.CREATE", CacheIndexName, "ON", "HASH", "PREFIX", "1", tier2KeyPrefix, "SCHEMA",
		vectorFieldName, "VECTOR", "FLAT", "6", "TYPE", "FLOAT32", "DIM", "768", "DISTANCE_METRIC", "COSINE",
		"query_text", "TEXT", "t1_key", "TAG", "dataset_epoch", "NUMERIC", "namespace", "TAG", "lane", "TAG").Err(); err != nil {
		t.Fatalf("raw FT.CREATE: %v", err)
	}
	// Set-up check: the scan must still be running, or this test proves nothing.
	if info, err := rdb.FTInfo(ctx, CacheIndexName).Result(); err != nil || info.Indexing != 1 {
		t.Fatalf("set-up: want the scan running right after FT.CREATE, got Indexing=%d err=%v", info.Indexing, err)
	}

	if err := s.EnsureCacheIndex(ctx); err != nil {
		t.Fatalf("EnsureCacheIndex while the index exists and is scanning: %v", err)
	}
	requireComplete(t, s, seeded)
}
