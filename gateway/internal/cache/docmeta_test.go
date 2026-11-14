package cache

import (
	"context"
	"encoding/binary"
	"math"
	"strings"
	"testing"

	"github.com/hung/thesis/gateway/internal/testredis"
)

// Item 6.0a (ADR-030): LoadDocMeta reads the `docmeta:*` hashes that `make docmeta` writes. The hashes are
// written by Python and read by Go, so the byte layout of the title vector (float32 little-endian) and the
// JSON of the bound words are the seam. A shifted or short vector would make the projection wrong with no
// error, so a bad width stops the load.

func titleBytes(dim int, f func(i int) float32) string {
	buf := make([]byte, 4*dim)
	for i := 0; i < dim; i++ {
		binary.LittleEndian.PutUint32(buf[i*4:], math.Float32bits(f(i)))
	}
	return string(buf)
}

func TestLoadDocMetaReadsCategoryTitleVectorAndBoundWords(t *testing.T) {
	rdb := testredis.Client(t, 14)
	s := NewStore(rdb, 768)
	ctx := context.Background()

	if err := rdb.HSet(ctx, "docmeta:product-electronics-a", map[string]any{
		"category":    "electronics",
		"title_vec":   titleBytes(768, func(i int) float32 { return float32(i) / 1000 }),
		"bound_words": `["aurora","kettle"]`,
	}).Err(); err != nil {
		t.Fatal(err)
	}
	if err := rdb.HSet(ctx, "docmeta:policy-return-electronics", map[string]any{"category": "electronics"}).Err(); err != nil {
		t.Fatal(err)
	}
	// Keys that are not docmeta must not be read.
	if err := rdb.HSet(ctx, "corpus::product-electronics-a#chunk-0", map[string]any{"text": "x"}).Err(); err != nil {
		t.Fatal(err)
	}

	got, err := s.LoadDocMeta(ctx)
	if err != nil {
		t.Fatalf("LoadDocMeta: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("loaded %d documents, want 2: %v", len(got), got)
	}
	p := got["product-electronics-a"]
	if p.Category != "electronics" || len(p.TitleVec) != 768 {
		t.Fatalf("product: category %q, %d dims", p.Category, len(p.TitleVec))
	}
	if p.TitleVec[0] != 0 || p.TitleVec[500] != float32(500)/1000 {
		t.Errorf("the title vector was not decoded as float32 little-endian: [0]=%v [500]=%v", p.TitleVec[0], p.TitleVec[500])
	}
	if _, ok := p.BoundWords["aurora"]; !ok || len(p.BoundWords) != 2 {
		t.Errorf("bound words = %v, want aurora and kettle", p.BoundWords)
	}
	pol := got["policy-return-electronics"]
	if pol.Category != "electronics" || pol.TitleVec != nil || pol.BoundWords != nil {
		t.Errorf("a policy document has a category only: %+v", pol)
	}
}

func TestLoadDocMetaRefusesATitleVectorOfTheWrongWidth(t *testing.T) {
	rdb := testredis.Client(t, 14)
	s := NewStore(rdb, 768)
	ctx := context.Background()
	if err := rdb.HSet(ctx, "docmeta:product-x", map[string]any{
		"category": "electronics", "title_vec": titleBytes(767, func(int) float32 { return 1 }), "bound_words": "[]",
	}).Err(); err != nil {
		t.Fatal(err)
	}
	_, err := s.LoadDocMeta(ctx)
	if err == nil || !strings.Contains(err.Error(), "title_vec") {
		t.Fatalf("LoadDocMeta = %v, want an error naming title_vec", err)
	}
}

func TestLoadDocMetaRefusesBoundWordsThatAreNotJSON(t *testing.T) {
	rdb := testredis.Client(t, 14)
	s := NewStore(rdb, 768)
	ctx := context.Background()
	if err := rdb.HSet(ctx, "docmeta:product-x", map[string]any{"category": "electronics", "bound_words": "aurora,kettle"}).Err(); err != nil {
		t.Fatal(err)
	}
	if _, err := s.LoadDocMeta(ctx); err == nil || !strings.Contains(err.Error(), "bound_words") {
		t.Fatalf("LoadDocMeta = %v, want an error naming bound_words", err)
	}
}

func TestLoadDocMetaOnAnEmptyServerIsEmptyNotAnError(t *testing.T) {
	rdb := testredis.Client(t, 14)
	got, err := NewStore(rdb, 768).LoadDocMeta(context.Background())
	if err != nil || len(got) != 0 {
		t.Fatalf("LoadDocMeta on an empty DB = %v, %v; want an empty map", got, err)
	}
}
