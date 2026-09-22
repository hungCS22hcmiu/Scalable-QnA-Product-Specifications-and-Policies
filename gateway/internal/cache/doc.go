// Package cache — Tier-1 exact + Tier-2 semantic; owns key normalization.
//
// Governing document: interfaces.md §D, the Tier-1 normalization contract
// Boundaries: docs/architecture.md §2. Violating them fails silently, so read it
// before changing this package's dependencies.
package cache
