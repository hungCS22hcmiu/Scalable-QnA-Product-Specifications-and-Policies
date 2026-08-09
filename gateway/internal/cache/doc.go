// Package cache — Tier-1 exact + Tier-2 semantic; owns key normalization.
//
// Governing document: interfaces.md §D, ADR-015
// Boundaries: docs/design/architecture.md §2. Violating them fails silently; see
// .docs/ai/architecture-guardrails.md before changing this package's dependencies.
package cache
