# Plan — httpapi-tests

Smallest change that satisfies `spec.md`. Each step is checked before the next starts.

## 0. Before any edit

- [x] `/approve implementation` recorded. Open items 1, 2 and 4 were decided on 2026-10-04 (`approvals.md`).
- [x] Nothing here needs Ollama, Redis or the Python service. Memory pressure is irrelevant to
      this task, and no measurement is taken.

## 1. The seam — `gateway/internal/httpapi/handler.go`

- [x] Add `cacheStore` and `var _ cacheStore = (*cache.Store)(nil)` (`design.md` §2).
- [x] `Handler.Cache` and `NewHandler`'s first parameter become `cacheStore`. Nothing else changes.
- [x] **Done when:** `cd gateway && go build ./... && go vet ./...` pass; `go test ./...` passes
      with no test file touched; and `git diff --stat` lists only `handler.go`, with `main.go`
      untouched.

## 2. The coalescing seam (U5 = (a), confirmed 2026-10-04) — `gateway/internal/coalesce/coalesce.go`

- [x] Add exported `Waiters(key string) int`, wrapping the existing `waiters` rather than renaming
      it (`design.md` §2).
- [x] **Done when:** `go test ./internal/coalesce/` passes with `coalesce_test.go` untouched.

## 3. Harness — `gateway/internal/httpapi/harness_test.go`

- [x] Build everything in `design.md` §3:
      - `fakeStore`, with an `injectedReturned` count and `waitFor`;
      - a strict `fakeRAG`: `TopK != 0` is an error, `texts` are aligned, `Answer` drops the last
        source, and Answer's epoch equals Retrieve's;
      - a strict `/api/embed` server: unknown input → 500;
      - the vector builder, and a fixture builder that satisfies all four conjuncts;
      - `askOnce` and `askMany`, with the S9 checks;
      - the recording `ResponseWriter`;
      - a `newHandler(t, opts)` whose cleanup runs in the order of `design.md` §8.
- [x] **Done when:** a trivial TIER1_HIT test runs green under `-race`, which proves the
      harness is wired.

## 4. Tests — `gateway/internal/httpapi/ask_test.go`

One path at a time, in the order of `design.md` §4, each run under `go test -race -count=1`
before the next is written:

- [x] TIER1_HIT
- [x] MISS, with both tiers under one identity
- [x] MISS, then a paraphrase as TIER2_HIT (the round trip)
- [x] TIER2_HIT, with promotion
- [x] The cross-namespace refusal; below τ
- [x] SHED, at `pool(1,1)` with C queued
- [x] ABANDONED while queued (join B before releasing A)
- [x] GENERATION_FAILED
- [x] Coalescing wraps admission; coalescing never crosses products
- [x] The four degradations, each with a would-be TIER2_HIT seeded
- [x] Tier-1 lookup error (one record only); 405 and 400

**If a test fails against the unchanged handler:** stop. Either the test is wrong, or this is a new
finding. A new finding is recorded, the test is reduced so that it does not pin the defect, and a
`/bugfix` is opened. The handler is **not** fixed inside this task.

## 5. Mutations — prove the tests can fail

- [x] Apply M1 to M14 (`design.md` §7) one at a time; run the package; record which test failed;
      revert.
- [x] **Done when:** every mutation is caught, and `git diff gateway/internal/httpapi/handler.go`
      shows only step 1's change, and `coalesce.go` only step 2's.

## 6. Close

- [x] `make verify`.
- [x] Record F-A to F-J as follow-ups and F-K as the author's decision, with the order the author chose (`approvals.md`, open item 3).
- [x] `/ai-review`: 7 findings, all fixed (`review.md`).
- [x] `/done`, 2026-10-04. 1.2 is marked done in `super-plan.md`.

## Verification

All run 2026-10-04 on this machine. Nothing needed Ollama, Redis or the Python service.

| Step | Check | Result |
| :---: | :--- | :--- |
| 1 | `go build ./... && go vet ./... && go test ./...` with no test file touched; `main.go` unchanged | **PASS**. `git diff --stat` lists only `handler.go` under `gateway/` |
| 2 | `go test ./internal/coalesce/`, `coalesce_test.go` untouched | **PASS** |
| 3 | `TestTier1HitServesTheStoredAnswer` under `-race` | **PASS**: the harness is wired |
| 4 | `go test -race -count=1 ./internal/httpapi/` (acceptance 1) | **PASS**, 17 tests. U2 resolved: `-race` flags nothing in `Ask`. **After `/ai-review`: 20 tests, PASS** |
| 4 | Flakiness: `-race -count=50`, then `-count=200 -shuffle=on` | **PASS**, no failure in either. Repeated after `/ai-review`: **PASS** |
| 5 | Mutations M1–M14 (`evidence/mutate.py`, output in `evidence/mutations.txt`) | **All 14 CAUGHT**, each by the test `design.md` §7 names, most by others too. Source restored after each |
| 5 | Two extra mutations checking the strict fakes (N1): `topKServerDefault = 5` (X1), the nomic prefix dropped (X2) | **Both CAUGHT**, by 14 and 13 tests |
| 5 | `git diff gateway/` after the mutations | Only step 1's change in `handler.go` and step 2's in `coalesce.go` |
| 6 | `make verify` (gofmt, vet, ruff, build, go test, pytest) | **PASS**, exit 0, before and after `/ai-review`. Proto drift is not part of `make verify` and was not run: **SKIPPED**. No `.proto` or stub changed |
| 6 | `/ai-review`: `contract-reviewer` and `design-reviewer` in parallel | 7 findings (I-1 to I-7), no blocker, **all fixed** (`review.md`, "Implementation review"). Mutations M15–M27 prove each fix: **all CAUGHT** |

**Per mutation, the test `design.md` §7 expected, and what actually failed:**

| # | Expected | Failed |
| :---: | :--- | :--- |
| M1 | `TestCoalescingWrapsAdmission` (deadline) | that test |
| M2 | the record-count check on non-MISS paths | 8 tests: every non-MISS path, plus the two whose second request is a hit |
| M3 | `TestMissGenerates…` | that test |
| M4 | `TestMissGenerates…`, `TestMissThenParaphrase…` | both |
| M5 | `TestShedWhenPermitAndQueueAreBothFull` | that test |
| M6 | `TestTier2RefusesAnEntryFromAnotherNamespace` | that test, and `TestRetrieveFailureDegradesToMiss` |
| M7 | `TestTier2HitInsideTheNamespace…` (deadline) | that test, and `TestMissThenParaphrase…` |
| M8 | `TestWritebackFailureStillServesTheAnswer` | that test |
| M9 | `TestAbandonedWhileQueuedIsNotAShed` | that test |
| M10 | `TestMissGenerates…` | that test |
| M11 | `TestCoalescingNeverCrossesProducts` (deadline) | that test, and `TestCoalescingWrapsAdmission` |
| M12 | `TestMissThenParaphraseIsATier2Hit` | that test, and `TestMissGenerates…` |
| M13 | `TestMissGenerates…` | that test |
| M14 | the helpers' `stratum` check | all 16 tests that go through `records()` |

**No test failed against the unchanged handler,** so no new finding came out of step 4.

## Follow-ups

None is fixed here, and no test pins any of them (`spec.md`, findings).

- **Bugfixes, F-A to F-J.** The order is still the author's decision (`approvals.md`, item 3). The
  recommendation stands: F-A and F-F (and F-D's client-side 200) before 1.6 and before any Phase 7
  run; 1.3's spec states whether it removes F-E and F-G; then F-B, F-C, F-H, F-J; F-I is an input
  to Phase 4's design.
- **F-K** is the author's decision (`approvals.md`, item 5): an ADR that makes the namespace rule
  the claim, or an item that puts θ into the served decision.
- **For 1.3:** the two declared tests, `telemetry/evallog_test.go:69` and `reuse/rule_test.go`
  (`approvals.md`, the note under the decisions).
- **For the follow-up already listed in `impact.md`:** sync §H's `cache` enum with the six values
  the code emits.

## Outcome

**Closed 2026-10-04. Item 1.2's "Done when" test passes**, and with it the Phase 1 exit clause
"`httpapi` has tests covering every exit path of `Ask`".

**What shipped:**
- **Source, type-only:**
  - `handler.go`: the unexported `cacheStore` interface. `Handler.Cache` and `NewHandler`'s first
    parameter use it, and `main.go` is unchanged.
  - `coalesce.go`: the read-only `Waiters`.
  - Nothing measured or counted changes (`approvals.md`: invalidates nothing).
- **`harness_test.go`** (scaffolding, `approvals.md` item 4):
  - an in-memory model of the store;
  - the RAG service and the embedder faked at the wire, behind the real clients;
  - strict fakes whose violations fail the test;
  - one record per call, matched and checked on every request (S9).
- **`ask_test.go`:** 20 tests and 5 subtests, every one under `-race`.
  - They cover the six named outcomes, response and record, plus 405 and 400.
  - Also the Tier-1 lookup error, the four degradations, coalescing in both directions, and the
    B-cross τ case.
  - Also the record's epoch, and LRU touch and trim at bounded capacity.
- **Evidence:** `evidence/mutate.py` reproduces 29 mutations, all caught; the output is in
  `evidence/mutations.txt`.

**Deferred, on purpose:**
- **F-A to F-J**, each its own `/bugfix`. The order is the author's call (`approvals.md`, item 3).
- **F-K**, the author's decision (`approvals.md`, item 5). It is now also flagged in
  `super-plan.md` under Phase 1, because it makes 6.1's θ sweep move no served decision.
- **Which epoch the Tier-2 record stores:** Phase 4's epoch guard decides it (`review.md`, I-4).
- **Eviction semantics and invariant 2 on eviction:** `cache/`'s tests, with Redis.

**Follow-ups worth a task:** F-A and F-F before 1.6 and before any Phase 7 run. F-K before 6.1 is
designed. The §H `cache` enum sync. 1.3, whose spec must name the two declared tests,
`evallog_test.go:69` and `rule_test.go`, and say whether it removes F-E and F-G.

**Was the scope honest? Yes, L.** The task changed source on the measured path, and nothing beyond
it: no frozen document, no contract, no `reuse/`, no `.proto`.
