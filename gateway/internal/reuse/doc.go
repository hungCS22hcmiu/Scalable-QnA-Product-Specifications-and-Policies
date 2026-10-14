// Package reuse — C1: the source-overlap reuse rule and the cascade.
// The answer-evidence support gate's two arms live here too (support.go, support_numeric.go), and
// cause.go combines them with the lane rule into the one refusal cause (item 2.3).
//
// Governing document: Final_Proposal.md §5 C1
// Boundaries: docs/architecture.md §2. Violating them fails silently, so read it
// before changing this package's dependencies.
package reuse
