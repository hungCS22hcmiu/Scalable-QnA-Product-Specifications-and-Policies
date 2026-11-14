package cache

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"math"
	"strings"
)

// Document metadata for the scope arm (item 6.0a, ADR-030): the `docmeta:{doc_id}` hashes that
// `make docmeta` writes (interfaces.md C). They live in cache/ and not in catalog/: catalog/ is the demo
// UI's product list and is never reached from /ask, and cache/ is the package that already reads Redis
// for the request path. Like the rest of this package it stores and returns data, and decides nothing:
// reuse/ owns the scope test.

const docMetaKeyPrefix = "docmeta:"

// DocMeta is one document's metadata as the hash holds it. A policy document has a Category only. A
// product also has a TitleVec (float32 little-endian, the width of the Tier-2 vectors) and BoundWords.
// reuse.DocMeta has the same fields; cmd/gateway converts one to the other, so reuse/ imports nothing.
type DocMeta struct {
	Category   string
	TitleVec   []float32
	BoundWords map[string]struct{}
}

// LoadDocMeta reads every `docmeta:*` hash, by SCAN (never KEYS, which blocks Redis for the whole
// keyspace), and returns them by doc_id. It is called once at start, so the hit path never reads Redis
// for metadata. It returns an error, and no partial map, when a title vector does not have the Tier-2
// width or a bound-word list is not JSON: a metadata record that is half read would make the scope test
// answer "neutral" for every answer of that product, with no error anywhere.
func (s *Store) LoadDocMeta(ctx context.Context) (map[string]DocMeta, error) {
	out := make(map[string]DocMeta)
	iter := s.rdb.Scan(ctx, 0, docMetaKeyPrefix+"*", 500).Iterator()
	for iter.Next(ctx) {
		key := iter.Val()
		fields, err := s.rdb.HGetAll(ctx, key).Result()
		if err != nil {
			return nil, fmt.Errorf("cache: reading %s: %w", key, err)
		}
		meta, err := s.decodeDocMeta(key, fields)
		if err != nil {
			return nil, err
		}
		out[strings.TrimPrefix(key, docMetaKeyPrefix)] = meta
	}
	if err := iter.Err(); err != nil {
		return nil, fmt.Errorf("cache: scanning %s*: %w", docMetaKeyPrefix, err)
	}
	return out, nil
}

func (s *Store) decodeDocMeta(key string, fields map[string]string) (DocMeta, error) {
	meta := DocMeta{Category: fields["category"]}
	if raw, ok := fields["title_vec"]; ok {
		if len(raw) != 4*s.dim {
			return DocMeta{}, fmt.Errorf("cache: %s has a title_vec of %d bytes, the Tier-2 width is %d dims (%d bytes)",
				key, len(raw), s.dim, 4*s.dim)
		}
		meta.TitleVec = make([]float32, s.dim)
		for i := range meta.TitleVec {
			meta.TitleVec[i] = math.Float32frombits(binary.LittleEndian.Uint32([]byte(raw[i*4 : i*4+4])))
		}
	}
	if raw, ok := fields["bound_words"]; ok {
		var words []string
		if err := json.Unmarshal([]byte(raw), &words); err != nil {
			return DocMeta{}, fmt.Errorf("cache: %s has unreadable bound_words: %w", key, err)
		}
		meta.BoundWords = make(map[string]struct{}, len(words))
		for _, w := range words {
			meta.BoundWords[w] = struct{}{}
		}
	}
	return meta, nil
}
