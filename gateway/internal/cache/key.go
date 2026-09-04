package cache

import (
	"crypto/sha256"
	"encoding/hex"
)

// Key derives the Tier-1 Redis key from an already-normalized query: t1:{sha256(normalized)}
// (interfaces.md §D).
func Key(normalized string) string {
	sum := sha256.Sum256([]byte(normalized))
	return "t1:" + hex.EncodeToString(sum[:])
}
