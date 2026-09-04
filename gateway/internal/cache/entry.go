package cache

import "time"

// Entry is the Tier-1 exact-match cache record (interfaces.md §D):
//
//	KEY   t1:{sha256(normalized_query)}      # HASH
//	      answer            <string>
//	      source_chunk_ids  <json array>
//	      model_used        <string>
//	      created_at        <rfc3339>
//	      entry_id          <ulid>            # links to the Tier-2 record / dependency map
//
// No `t1_key` or other Tier-2 field this week -- t1_key is written BY Tier-2 (interfaces.md
// §D: "the Tier-1 key this entry was co-written with"), and Tier-2 doesn't exist until W7.
type Entry struct {
	Answer         string
	SourceChunkIDs []string
	ModelUsed      string
	CreatedAt      time.Time
	EntryID        string
}
