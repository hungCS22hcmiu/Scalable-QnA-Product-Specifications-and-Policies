// Scratch copy of gateway/internal/cache/tier2.go's EnsureCacheIndex + nearest(), run against a
// PRIVATE redis on :6391 only. It reproduces what the live gateway sees (a) when idx:cache is
// missing and (b) when a KNN returns a doc whose hash lives in another logical db.
package main

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"math"
	"math/rand"
	"os"
	"strconv"
	"strings"

	"github.com/redis/go-redis/v9"
)

const dim = 768

func enc(v []float32) string {
	b := make([]byte, 4*len(v))
	for i, x := range v {
		binary.LittleEndian.PutUint32(b[i*4:], math.Float32bits(x))
	}
	return string(b)
}

func randVec(seed int64) []float32 {
	r := rand.New(rand.NewSource(seed))
	v := make([]float32, dim)
	var n float64
	for i := range v {
		v[i] = float32(r.NormFloat64())
		n += float64(v[i] * v[i])
	}
	for i := range v {
		v[i] /= float32(math.Sqrt(n))
	}
	return v
}

func ensure(ctx context.Context, rdb *redis.Client, name string) error {
	err := rdb.FTCreate(ctx, name,
		&redis.FTCreateOptions{OnHash: true, Prefix: []any{"t2:"}},
		&redis.FieldSchema{FieldName: "embedding", FieldType: redis.SearchFieldTypeVector,
			VectorArgs: &redis.FTVectorArgs{FlatOptions: &redis.FTFlatOptions{Type: "FLOAT32", Dim: dim, DistanceMetric: "COSINE"}}},
		&redis.FieldSchema{FieldName: "query_text", FieldType: redis.SearchFieldTypeText},
		&redis.FieldSchema{FieldName: "t1_key", FieldType: redis.SearchFieldTypeTag},
		&redis.FieldSchema{FieldName: "dataset_epoch", FieldType: redis.SearchFieldTypeNumeric},
		&redis.FieldSchema{FieldName: "namespace", FieldType: redis.SearchFieldTypeTag},
		&redis.FieldSchema{FieldName: "lane", FieldType: redis.SearchFieldTypeTag},
	).Err()
	if err != nil && strings.Contains(strings.ToLower(err.Error()), "already exists") {
		return nil
	}
	return err
}

// nearest is tier2.go's nearest(), parsing included, with the index name as a parameter.
func nearest(ctx context.Context, rdb *redis.Client, index, filter string, vec []float32, k int) ([]string, error) {
	res, err := rdb.FTSearchWithArgs(ctx, index,
		fmt.Sprintf("%s=>[KNN %d @%s $vec AS %s]", filter, k, "embedding", "dist"),
		&redis.FTSearchOptions{
			Params: map[string]any{"vec": enc(vec)}, DialectVersion: 2,
			SortBy: []redis.FTSearchSortBy{{FieldName: "dist", Asc: true}}, LimitOffset: 0, Limit: k,
			Return: []redis.FTSearchReturn{{FieldName: "dist"}, {FieldName: "answer"}, {FieldName: "source_chunk_ids"}},
		}).Result()
	if err != nil {
		return nil, err
	}
	var out []string
	for _, d := range res.Docs {
		if raw := d.Fields["source_chunk_ids"]; raw != "" {
			var ids []string
			if err := json.Unmarshal([]byte(raw), &ids); err != nil {
				return nil, err
			}
		}
		dist, err := strconv.ParseFloat(d.Fields["dist"], 64)
		if err != nil {
			return nil, fmt.Errorf("cache: entry %s returned no %s: %w", strings.TrimPrefix(d.ID, "t2:"), "dist", err)
		}
		out = append(out, fmt.Sprintf("%s sim=%.4f answer=%q", d.ID, 1-dist, d.Fields["answer"]))
	}
	return out, nil
}

func main() {
	if os.Getenv("PROBE_PORT") != "6391" {
		panic("private instance only: set PROBE_PORT=6391")
	}
	ctx := context.Background()
	db0 := redis.NewClient(&redis.Options{Addr: "localhost:6391"}) // same options as main.go
	db15 := redis.NewClient(&redis.Options{Addr: "localhost:6391", DB: 15})
	must := func(err error) {
		if err != nil {
			panic(err)
		}
	}
	must(db0.FlushAll(ctx).Err())

	// (a) idx:cache missing: what the gateway's Tier-2 search returns.
	_, err := nearest(ctx, db0, "idx:cache", "(@namespace:{ns1})", randVec(1), 1)
	fmt.Printf("(a) index missing: err=%v\n", err)
	// PutTier2 on a missing index: HSET succeeds, nothing indexes it.
	err = db0.HSet(ctx, "t2:LIVE", map[string]any{"embedding": enc(randVec(2)), "answer": "live", "namespace": "ns1", "source_chunk_ids": `["c#0"]`}).Err()
	fmt.Printf("(a) PutTier2-like HSET with index missing: err=%v\n", err)

	// (a2) EnsureCacheIndex from DB 15 (what a test would hit).
	fmt.Printf("(a2) EnsureCacheIndex from DB 15: err=%v\n", ensure(ctx, db15, "idx:cache"))
	must(ensure(ctx, db0, "idx:cache"))
	fmt.Printf("(a2) EnsureCacheIndex from DB 15 when idx:cache EXISTS: err=%v\n", ensure(ctx, db15, "idx:cache"))

	// (b) a test-shaped hash in DB 15 WITHOUT a vector (what cache/deps tests write today).
	must(db15.HSet(ctx, "t2:victim", map[string]any{"t1_key": "t1:victimkey", "answer": "a"}).Err())
	info, _ := db0.Do(ctx, "FT.INFO", "idx:cache").Result()
	fmt.Printf("(b) after a vector-less t2: HSET in DB 15, FT.INFO num_docs: %v\n", numDocs(info))
	r, err := nearest(ctx, db0, "idx:cache", "(@namespace:{ns1})", randVec(2), 1)
	fmt.Printf("(b) live KNN k=1: %v err=%v\n", r, err)

	// (c) a hash WITH a vector in DB 15, in the live namespace (a future Tier-2 integration test).
	must(db15.HSet(ctx, "t2:GHOST", map[string]any{"embedding": enc(randVec(3)), "answer": "ghost", "namespace": "ns1"}).Err())
	r, err = nearest(ctx, db0, "idx:cache", "(@namespace:{ns1})", randVec(2), 1)
	fmt.Printf("(c) live KNN k=1, query = the LIVE entry's own vector: %v err=%v\n", r, err)
	r, err = nearest(ctx, db0, "idx:cache", "(@namespace:{ns1})", randVec(3), 1)
	fmt.Printf("(c) live KNN k=1, query near the ghost: %v err=%v\n", r, err)
	must(db0.FlushAll(ctx).Err())
}

func numDocs(info any) any {
	switch m := info.(type) {
	case map[any]any:
		return m["num_docs"]
	case []any:
		for i := 0; i+1 < len(m); i += 2 {
			if m[i] == "num_docs" {
				return m[i+1]
			}
		}
	}
	return info
}
