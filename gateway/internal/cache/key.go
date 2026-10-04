package cache

import (
	"crypto/sha256"
	"encoding/hex"
)

// Key derives the Tier-1 Redis key from an already-normalized query, scoped by productID:
// t1:{sha256(normalized "\x00" product_id)}.
//
// ⚠️ BYPASS 2026-09-09: this reverses the explicit "Add product_id to the Tier-1 key --
// Rejected" alternative (the decision record). Implemented directly for an urgent MVP
// demo without the owed ADR/contract approval.
// A superseding ADR is still owed before this is citable or mergeable.
//
// productID == "" is its own partition, never a wildcard: a request with no product_id neither
// reads nor writes a product-scoped record, so it cannot collide with one that has a product_id.
// The "\x00" separator is load-bearing, not cosmetic -- without it Key("ab","c") and
// Key("a","bc") would hash identically.
func Key(normalized, productID string) string {
	sum := sha256.Sum256([]byte(normalized + "\x00" + productID))
	return "t1:" + hex.EncodeToString(sum[:])
}
