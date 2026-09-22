package cache

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"math"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

// Tier-2 semantic cache: the vector-searchable half of interfaces.md D.
//
// This file stores and retrieves CANDIDATES. It never decides whether a candidate may be reused --
// that judgement is reuse/'s, and keeping it out of here is what lets C1 be falsified in isolation
// (docs/design/architecture.md 2: "cache/ ... must not make a reuse decision").

const (
	CacheIndexName = "idx:cache"

	// Written by Go directly, so the key has ONE colon. The Python side's corpus keys have two
	// (`corpus::product-01#chunk-0`) because LlamaIndex appends its own separator to the
	// configured prefix. FT.CREATE's PREFIX must match what is actually written: a mismatch
	// indexes nothing, and every lookup then misses with no error at all.
	tier2KeyPrefix = "t2:"

	vectorFieldName = "embedding"
	distanceAlias   = "dist"
)

// Tier2Entry is the t2:{entry_id} hash of interfaces.md D.
type Tier2Entry struct {
	EntryID        string
	QueryText      string
	Answer         string
	SourceChunkIDs []string

	// T1Key is the Tier-1 key this entry was co-written with. It is REQUIRED and is not
	// reconstructible later: Tier 1 is keyed by sha256(normalized_query "\x00" product_id)
	// (⚠️ product_id joined the key 2026-09-09, bypass -- see cache.Key), which cannot be
	// computed from an entry_id. Without it the Phase-2 invalidator purges the t2 record and
	// leaves the t1 copy serving stale content -- a completeness hole no Tier-2 test reveals
	// (interfaces.md D).
	T1Key string

	DatasetEpoch  uint64
	SourceOverlap float64
	HitCount      int64
	CreatedAt     time.Time

	// Namespace and Lane are the two-lane experiment's partition (.docs/work/two-lane-cache).
	// Stored, never interpreted here: cache/ must not make a reuse decision
	// (architecture.md 2), so it carries the partition the way it carries source_chunk_ids --
	// as recorded provenance for reuse/ to judge.
	Namespace string
	Lane      string
}

// Candidate is a nearest-neighbour result: what was stored, plus how close the query was.
// Similarity, not distance -- see NearestTier2.
type Candidate struct {
	Entry      Tier2Entry
	Similarity float64
}

// EnsureCacheIndex creates idx:cache if it is absent. Safe to call on every startup.
func (s *Store) EnsureCacheIndex(ctx context.Context) error {
	err := s.rdb.FTCreate(ctx, CacheIndexName,
		&redis.FTCreateOptions{OnHash: true, Prefix: []any{tier2KeyPrefix}},
		&redis.FieldSchema{
			FieldName: vectorFieldName,
			FieldType: redis.SearchFieldTypeVector,
			VectorArgs: &redis.FTVectorArgs{
				// FLAT is frozen study-wide and must never become HNSW mid-study: approximate
				// retrieval makes the candidate set nondeterministic, injecting overlap noise
				// that is indistinguishable from C1's own signal (interfaces.md D, rules.md #1).
				FlatOptions: &redis.FTFlatOptions{
					Type:           "FLOAT32",
					Dim:            s.dim,
					DistanceMetric: "COSINE",
				},
			},
		},
		&redis.FieldSchema{FieldName: "query_text", FieldType: redis.SearchFieldTypeText},
		&redis.FieldSchema{FieldName: "t1_key", FieldType: redis.SearchFieldTypeTag},
		&redis.FieldSchema{FieldName: "dataset_epoch", FieldType: redis.SearchFieldTypeNumeric},
		// TAG rather than TEXT: a namespace is an identifier compared for equality, never
		// tokenised. TEXT would stem `policy-returns-electronics` and make two distinct
		// namespaces collide silently.
		&redis.FieldSchema{FieldName: "namespace", FieldType: redis.SearchFieldTypeTag},
		&redis.FieldSchema{FieldName: "lane", FieldType: redis.SearchFieldTypeTag},
	).Err()

	if err != nil && strings.Contains(strings.ToLower(err.Error()), "already exists") {
		return nil
	}
	return err
}

// PutTier2 writes the t2 record. The caller supplies entry_id and t1_key so both tiers are
// written from one miss with identical identity -- divergence there breaks purge in Phase 2.
func (s *Store) PutTier2(ctx context.Context, e Tier2Entry, vec []float32) error {
	if len(vec) != s.dim {
		return fmt.Errorf("cache: embedding has %d dims, index expects %d", len(vec), s.dim)
	}
	sourceChunkIDs, err := json.Marshal(e.SourceChunkIDs)
	if err != nil {
		return err
	}
	if e.CreatedAt.IsZero() {
		e.CreatedAt = time.Now().UTC()
	}

	return s.rdb.HSet(ctx, tier2KeyPrefix+e.EntryID, map[string]any{
		vectorFieldName:    encodeVector(vec),
		"query_text":       e.QueryText,
		"answer":           e.Answer,
		"source_chunk_ids": string(sourceChunkIDs),
		"t1_key":           e.T1Key,
		"dataset_epoch":    e.DatasetEpoch,
		"source_overlap":   e.SourceOverlap,
		"hit_count":        e.HitCount,
		"created_at":       e.CreatedAt.Format(time.RFC3339),
		"namespace":        e.Namespace,
		"lane":             e.Lane,
	}).Err()
}

// NearestTier2 returns the k nearest entries by cosine similarity, over the whole cache.
func (s *Store) NearestTier2(ctx context.Context, vec []float32, k int) ([]Candidate, error) {
	return s.nearest(ctx, "*", vec, k)
}

// NearestTier2InNamespace returns the k nearest entries WITHIN one namespace, as a RediSearch
// hybrid query (`(@namespace:{ns})=>[KNN k ...]`) rather than an over-fetch filtered in Go.
//
// This is an optimisation, NOT the rule. reuse.DecideLane still re-checks namespace equality on
// whatever comes back, so the invariant is enforced in reuse/ where architecture.md 2 requires it
// and cache/ still "must not make a reuse decision" -- if this filter were ever wrong, the Go
// check would refuse anyway and the test suite says so.
//
// It replaces a fan-out that was both wasteful and WRONG. Fetching the k nearest overall and
// discarding the ones in other namespaces means that when the k nearest all belong elsewhere, a
// perfectly good in-namespace entry sitting at rank k+1 is never seen -- a false miss that gets
// steadily worse as the cache fills, and that would read as an eviction effect in a load test
// while having nothing to do with eviction. Asking Redis for the nearest IN the namespace has no
// such horizon.
func (s *Store) NearestTier2InNamespace(ctx context.Context, vec []float32, namespace string, k int) ([]Candidate, error) {
	if namespace == "" {
		// An empty namespace is UNMATCHABLE, never a wildcard (reuse.MatchNamespace). Returning
		// the whole cache here would invert that into "matches everything".
		return nil, nil
	}
	return s.nearest(ctx, "(@namespace:{"+escapeTag(namespace)+"})", vec, k)
}

// escapeTag escapes a TAG value for a RediSearch query. Namespaces are doc_ids joined by "|",
// and both "-" and "|" are query syntax: unescaped, `product-headphones-03` parses as a negation
// and matches nothing, silently, with every lookup becoming a miss and no error anywhere.
func escapeTag(v string) string {
	var b strings.Builder
	b.Grow(len(v) * 2)
	for _, r := range v {
		if !(r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || r == '_') {
			b.WriteByte('\\')
		}
		b.WriteRune(r)
	}
	return b.String()
}

func (s *Store) nearest(ctx context.Context, filter string, vec []float32, k int) ([]Candidate, error) {
	res, err := s.rdb.FTSearchWithArgs(ctx, CacheIndexName,
		fmt.Sprintf("%s=>[KNN %d @%s $vec AS %s]", filter, k, vectorFieldName, distanceAlias),
		&redis.FTSearchOptions{
			Params:         map[string]any{"vec": encodeVector(vec)},
			DialectVersion: 2,
			SortBy:         []redis.FTSearchSortBy{{FieldName: distanceAlias, Asc: true}},
			LimitOffset:    0,
			Limit:          k,
			// Deliberately NOT returning `embedding`: it would come back as a ~3KB raw blob
			// inside Fields map[string]string on every single hit-path lookup.
			Return: []redis.FTSearchReturn{
				{FieldName: distanceAlias},
				{FieldName: "query_text"},
				{FieldName: "answer"},
				{FieldName: "source_chunk_ids"},
				{FieldName: "t1_key"},
				{FieldName: "dataset_epoch"},
				{FieldName: "source_overlap"},
				{FieldName: "hit_count"},
				{FieldName: "created_at"},
				{FieldName: "namespace"},
				{FieldName: "lane"},
			},
		}).Result()
	if err != nil {
		return nil, err
	}

	out := make([]Candidate, 0, len(res.Docs))
	for _, d := range res.Docs {
		e := Tier2Entry{
			EntryID:   strings.TrimPrefix(d.ID, tier2KeyPrefix),
			QueryText: d.Fields["query_text"],
			Answer:    d.Fields["answer"],
			T1Key:     d.Fields["t1_key"],
			Namespace: d.Fields["namespace"],
			Lane:      d.Fields["lane"],
		}
		if raw := d.Fields["source_chunk_ids"]; raw != "" {
			if err := json.Unmarshal([]byte(raw), &e.SourceChunkIDs); err != nil {
				return nil, fmt.Errorf("cache: entry %s has unreadable source_chunk_ids: %w", e.EntryID, err)
			}
		}
		e.DatasetEpoch, _ = strconv.ParseUint(d.Fields["dataset_epoch"], 10, 64)
		e.SourceOverlap, _ = strconv.ParseFloat(d.Fields["source_overlap"], 64)
		e.HitCount, _ = strconv.ParseInt(d.Fields["hit_count"], 10, 64)
		e.CreatedAt, _ = time.Parse(time.RFC3339, d.Fields["created_at"])

		// Redis returns cosine DISTANCE, not similarity. Getting this backwards is silent and
		// total: every lookalike would pass the threshold and every true paraphrase would be
		// refused, with the rule still appearing to "work".
		dist, err := strconv.ParseFloat(d.Fields[distanceAlias], 64)
		if err != nil {
			return nil, fmt.Errorf("cache: entry %s returned no %s: %w", e.EntryID, distanceAlias, err)
		}
		out = append(out, Candidate{Entry: e, Similarity: 1 - dist})
	}
	return out, nil
}

// BumpHitCount increments the reuse counter on a served Tier-2 entry. Fire-and-forget: a failed
// increment must never fail a request that was already answered correctly. This is the raw
// material for the demo's "generations avoided" counter (defense_demo.md 3).
func (s *Store) BumpHitCount(ctx context.Context, entryID string) error {
	return s.rdb.HIncrBy(ctx, tier2KeyPrefix+entryID, "hit_count", 1).Err()
}

// encodeVector packs float32s little-endian, the layout Redis expects for a FLOAT32 vector field.
// float64 here would double the width and be rejected or misread.
func encodeVector(vec []float32) string {
	buf := make([]byte, 4*len(vec))
	for i, v := range vec {
		binary.LittleEndian.PutUint32(buf[i*4:], math.Float32bits(v))
	}
	return string(buf)
}
