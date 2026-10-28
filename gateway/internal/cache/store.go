package cache

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/redis/go-redis/v9"
)

// Store owns Tier-1 exact-match reads and writes. It must never make a reuse decision --
// sha256 equality is not a judgement (architecture-guardrails.md).
type Store struct {
	rdb *redis.Client
	dim int // Tier-2 vector width, supplied by main.go from embed.Dim -- see tier2.go
}

func NewStore(rdb *redis.Client, dim int) *Store {
	return &Store{rdb: rdb, dim: dim}
}

// Get looks up the exact-match entry for query, scoped to productID ("" is its own partition,
// never a wildcard -- see Key). The bool is false on a cache miss.
func (s *Store) Get(ctx context.Context, query, productID string) (*Entry, bool, error) {
	key := Key(Normalize(query), productID)
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

// promoteScript is the Tier-1 promotion: it writes the key only while the entry's Tier-2 record exists.
//
// KEYS[1] = t2:{entry_id}, KEYS[2] = the Tier-1 key, KEYS[3] = lru:t1keys:{entry_id}.
// ARGV = answer, source_chunk_ids, model_used, created_at, entry_id. It returns 1 when it wrote, 0 when
// t2:{entry_id} was gone.
//
// ⚠️ The check and the write are ONE script on purpose. A promotion runs in the background after a
// Tier-2 hit, so a trim or a purge of the same entry can run between "is the entry live?" and "write the
// key". With two calls, the promotion could land after dropEntryScript had removed the entry: a Tier-1
// pointer at an evicted or purged entry would serve a stale answer, and its next hit would even put the
// entry back into lru:entries with no t2: record. Redis runs a script as one step, so either the removal
// runs first (the promotion finds no t2: and writes nothing) or the promotion runs first (dropEntryScript
// finds the key in the set and deletes it).
var promoteScript = redis.NewScript(`
if redis.call('EXISTS', KEYS[1]) == 0 then
  return 0
end
redis.call('HSET', KEYS[2],
  'answer', ARGV[1], 'source_chunk_ids', ARGV[2], 'model_used', ARGV[3],
  'created_at', ARGV[4], 'entry_id', ARGV[5])
redis.call('SADD', KEYS[3], KEYS[2])
return 1
`)

// Put writes a Tier-1 record, scoped to productID (see Key). Mints an EntryID if the caller did not
// already set one.
//
// Every Tier-1 write is recorded in lru:t1keys:{EntryID}, in the same atomic step as the hash, so
// eviction and purge can find every key that names an entry (interfaces.md §D, v0.19). A write that
// landed without its set member would be an orphan after eviction, serving an entry outside the cache.
//
// With e.Promotion the write is conditional: it happens only while t2:{EntryID} exists (promoteScript).
// A promotion that finds no t2: record writes nothing and returns nil: the entry left the cache first,
// which is a normal race and not an error.
func (s *Store) Put(ctx context.Context, query, productID string, e Entry) error {
	if e.Promotion && e.EntryID == "" {
		return errors.New("cache: a promotion write needs an EntryID")
	}
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

	key := Key(Normalize(query), productID)
	createdAt := e.CreatedAt.Format(time.RFC3339)

	if e.Promotion {
		return promoteScript.Run(ctx, s.rdb,
			[]string{tier2KeyPrefix + e.EntryID, key, t1KeysKey(e.EntryID)},
			e.Answer, string(sourceChunkIDs), e.ModelUsed, createdAt, e.EntryID).Err()
	}

	pipe := s.rdb.TxPipeline()
	pipe.HSet(ctx, key, map[string]any{
		"answer":           e.Answer,
		"source_chunk_ids": string(sourceChunkIDs),
		"model_used":       e.ModelUsed,
		"created_at":       createdAt,
		"entry_id":         e.EntryID,
	})
	pipe.SAdd(ctx, t1KeysKey(e.EntryID), key)
	_, err = pipe.Exec(ctx)
	return err
}
