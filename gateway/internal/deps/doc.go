// Package deps — C2: source-to-entry dependency map, copy-on-write reads, single writer goroutine.
//
// Built in item 4.1. One writer goroutine owns the dep:* and entry:* records (interfaces.md §E).
// Register queues a write-back's dependencies; Invalidate purges every dependent entry from both
// tiers through the Purger interface; Invalidated is the hit-path check, one atomic load of a
// copy-on-write snapshot of invalidated entry IDs. The purge is blind: change_type is never a gate.
// Item 4.2 added the epoch reader (EpochFile) and the writer's late check (SetEpochSource,
// LateDiscards): a registration made under an epoch that is no longer current is purged, not
// registered. The write-back guard itself is in httpapi.
//
// Governing document: interfaces.md §E
// Boundaries: docs/architecture.md §2. Violating them fails silently, so read it
// before changing this package's dependencies.
package deps
