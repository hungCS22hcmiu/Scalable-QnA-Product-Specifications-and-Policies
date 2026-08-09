// Package deps — C2: source-to-entry dependency map, copy-on-write reads, single writer goroutine.
//
// Governing document: interfaces.md §E
// Boundaries: docs/design/architecture.md §2. Violating them fails silently; see
// .docs/ai/architecture-guardrails.md before changing this package's dependencies.
package deps
