package cache

import "time"

// Entry is the Tier-1 exact-match cache record (interfaces.md §D; the key includes product_id,
// ADR-018 -- see cache.Key):
//
//	KEY   t1:{sha256(normalized_query "\x00" product_id)}      # HASH
//	      answer            <string>
//	      source_chunk_ids  <json array>
//	      model_used        <string>
//	      created_at        <rfc3339>
//	      entry_id          <ulid>            # links to the Tier-2 record / dependency map
//
// The record holds no `t1_key`: that field lives on the Tier-2 record (interfaces.md §D: "the Tier-1
// key this entry was co-written with"), and every Tier-1 key of an entry, promoted ones included, is
// listed in lru:t1keys:{entry_id} (capacity.go), so the trim and the purge can find it.
type Entry struct {
	Answer         string
	SourceChunkIDs []string
	ModelUsed      string
	CreatedAt      time.Time
	EntryID        string

	// Promotion marks a Tier-1 write that copies an entry which already lives in Tier 2 (the handler's
	// promotion after a Tier-2 hit). Such a write happens only while t2:{EntryID} still exists, and the
	// key is recorded in lru:t1keys:{EntryID} (interfaces.md §D, v0.19). Store.Put needs a non-empty
	// EntryID for it. The handler sets this on the Tier-2 promotion and nowhere else.
	Promotion bool
}
