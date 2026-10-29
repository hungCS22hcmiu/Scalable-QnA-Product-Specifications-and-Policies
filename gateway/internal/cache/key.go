package cache

import (
	"crypto/sha256"
	"encoding/hex"
)

// Key derives the Tier-1 Redis key from an already-normalized query, scoped by productID:
// t1:{sha256(normalized "\x00" product_id)}.
//
// ADR-018 (interfaces.md §D, v0.23): product_id is part of the key. Tier 1 runs no reuse rule,
// so the same normalized question asked about two products must not share an entry. Built
// 2026-09-09, before any run, against the proposal's rejected alternative; ADR-018 records it.
// On the frozen v1 workload no normalized question is shared across products, so no hit changes.
//
// productID == "" is its own partition, never a wildcard: a request with no product_id neither
// reads nor writes a product-scoped record, so it cannot collide with one that has a product_id.
// The "\x00" separator is load-bearing, not cosmetic -- without it Key("ab","c") and
// Key("a","bc") would hash identically.
func Key(normalized, productID string) string {
	sum := sha256.Sum256([]byte(normalized + "\x00" + productID))
	return "t1:" + hex.EncodeToString(sum[:])
}
