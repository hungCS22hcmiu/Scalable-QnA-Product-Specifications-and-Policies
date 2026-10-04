// Package admission — Resource governance: permit pool, bounded queue, graceful shed.
//
// Governing document: Final_Proposal.md §6.1
// Boundaries: docs/architecture.md §2. Violating them fails silently, so read it
// before changing this package's dependencies.
package admission
