// Package deps — C2: source-to-entry dependency map, copy-on-write reads, single writer goroutine.
//
// Governing document: interfaces.md §E
// Boundaries: docs/architecture.md §2. Violating them fails silently, so read it
// before changing this package's dependencies.
package deps
