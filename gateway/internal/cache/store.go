package cache

import (
	"context"
	"encoding/json"
	"time"

	"github.com/redis/go-redis/v9"
)

// Store owns Tier-1 exact-match reads and writes. It must never make a reuse decision --
// sha256 equality is not a judgement (architecture-guardrails.md).
type Store struct {
	rdb *redis.Client
}

func NewStore(rdb *redis.Client) *Store {
	return &Store{rdb: rdb}
}

// Get looks up the exact-match entry for query. The bool is false on a cache miss.
func (s *Store) Get(ctx context.Context, query string) (*Entry, bool, error) {
	key := Key(Normalize(query))
	fields, err := s.rdb.HGetAll(ctx, key).Result()
	if err != nil {
		return nil, false, err
	}
	if len(fields) == 0 {
		return nil, false, nil
	}

	var sourceChunkIDs []string
	if err := json.Unmarshal([]byte(fields["source_chunk_ids"]), &sourceChunkIDs); err != nil {
		return nil, false, err
	}
	createdAt, err := time.Parse(time.RFC3339, fields["created_at"])
	if err != nil {
		return nil, false, err
	}

	return &Entry{
		Answer:         fields["answer"],
		SourceChunkIDs: sourceChunkIDs,
		ModelUsed:      fields["model_used"],
		CreatedAt:      createdAt,
		EntryID:        fields["entry_id"],
	}, true, nil
}

// Put writes back a full-miss result. Mints an EntryID if the caller did not already set one.
func (s *Store) Put(ctx context.Context, query string, e Entry) error {
	if e.EntryID == "" {
		e.EntryID = NewEntryID()
	}
	if e.CreatedAt.IsZero() {
		e.CreatedAt = time.Now().UTC()
	}

	sourceChunkIDs, err := json.Marshal(e.SourceChunkIDs)
	if err != nil {
		return err
	}

	key := Key(Normalize(query))
	return s.rdb.HSet(ctx, key, map[string]any{
		"answer":           e.Answer,
		"source_chunk_ids": string(sourceChunkIDs),
		"model_used":       e.ModelUsed,
		"created_at":       e.CreatedAt.Format(time.RFC3339),
		"entry_id":         e.EntryID,
	}).Err()
}
