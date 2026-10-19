# Plan — tier2-explainer

Scope S: the one-paragraph spec in `spec.md` is the plan. This file records verification and the
outcome.

## Verification — 2026-10-19

`make verify` on `5281575` (the merged PR #8):

| Target | Result |
| :--- | :--- |
| gofmt | PASS |
| go vet | PASS |
| ruff | PASS |
| go build | PASS |
| go test | PASS |
| pytest `rag/` | PASS (15) |
| pytest `experiments/` | PASS (258) |
| Proto drift | not run — `make verify` has no proto target |

Spec acceptance test (`go test ./internal/reuse -run 'TestNoThetaSeparatesTheMeasuredPair|TestSupportLexicalSeparatesTheMeasuredPair|TestNumericMeasuredPair|TestJudgeAgreesWithDecideLane' -count=1`):
PASS, 5 tests (the pattern also matches `TestJudgeAgreesWithDecideLaneGateOff`).

## Outcome — closed 2026-10-19

**Shipped** (PR #8, merged 2026-10-17): `docs/Tier 2.md`, the Tier-2 explainer; §1.6 "Manual demo on
the UI page" in `docs/0. progress 16-10.md`; the README refresh. No code, contract or frozen value
changed. No item's "Done when" was passed, and the Phase 3 exit is unchanged.

**Review:** waived by the author (`review.md`).

**Follow-up worth a task** (from `spec.md`, "Found by the preview"; all in `reuse/`, so scope L):
the POLICY namespace follows the question's words, not the product's category; product scoping lets
one policy chunk decide the lane; the single warranty document puts every category in one namespace
(the G5 residual, and item 3.3's to fix by splitting documents).
