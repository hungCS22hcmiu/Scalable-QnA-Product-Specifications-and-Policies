# Mutations — design.md §5

Each mutation was applied to a fresh copy of `gateway/` (the 1.3 working tree, base `5854cbe`),
never to the working tree itself. **Caught** means the named check went red.

| # | Mutation | Check | Result | What went red |
| :---: | :--- | :--- | :---: | :--- |
| M1 | re-add a global NearestTier2 to cacheStore (interface only) | `go vet ./internal/httpapi/` | **caught** | `cannot use (*fakeStore)(nil) (value of type *fakeStore) as cacheStore value in variable declaration: *fakeStore does not implement cacheStore (missing method NearestTier2)` |
| M1' | call NearestTier2 through a type assertion on *cache.Store | acceptance 1, grep 2 | **caught** | grep 2 finds `_, _ = s.NearestTier2(ctx, vec, 1)`; the httpapi suite alone stays green (invisible to the fake) |
| M2 | report the global nearest on a refusal (global search re-added to interface AND fake) | `go test -count=1 ./internal/httpapi/` | **caught** | `TestIdenticalQuestionAboutAnotherProductIsNotServed`, `TestTier2RefusesAnEntryFromAnotherNamespace` |
| M3 | enter the band on a retrieval failure, before deciding (F-E's shape) | `go test -count=1 ./internal/httpapi/` | **caught** | `TestRetrieveFailureReportsNoTier2Evidence` |
| M4 | EnteredBand <- c.Similarity > tau | `go test -count=1 ./internal/httpapi/` | **caught** | `TestCandidateExactlyAtTauIsServedAndEntersTheBand` |
| M5 | counterfactual on the global nearest (global search re-added to interface AND fake) | `go test -count=1 ./internal/httpapi/` | **caught** | `TestCounterfactualIsComputedOnTheServedEntry` |
| M6 | re-add similarity_only_decision to the record | `go test -count=1 ./internal/httpapi/` | **caught** | `TestRecordCarriesNoSimilarityOnlyDecision` |
| M7a | change the guard's predicate (wrong key) | `go test -count=1 ./cmd/gateway/` | **caught** | `TestRetiredEnvRefusesTauHigh`, `TestRetiredEnvRefusesTauHigh/set` |
| M7b | drop the guard's call from main | acceptance 1, grep 3 | **caught** | grep 3 counts 0, want 1; main_test.go stays green |
| M8 | a short-circuit re-added ENABLED at 1.0 (global search re-added to interface AND fake) | `go test -count=1 ./internal/httpapi/` | **caught** | `TestCandidateExactlyAtTauIsServedAndEntersTheBand`, `TestIdenticalQuestionAboutAnotherProductIsNotServed` |
| M10 | time a no-op search on an empty namespace (drop the early return) | `go test -count=1 ./internal/httpapi/` | **caught** | `TestEmptyNamespaceRunsNoSearch` |
| M11 | derive the namespace after retrieval failed (served without provenance) | `go test -count=1 ./internal/httpapi/` | **caught** | `TestRetrieveFailureDegradesToMiss`, `TestRetrieveFailureReportsNoTier2Evidence` |

| M9 | a short-circuit re-added **disabled** | — | not behaviourally catchable | A disabled branch never fires, so no request can observe it. Acceptance 1's grep catches it only if it reuses the retired names (design.md §5) |

**All runnable mutations caught: yes.**
