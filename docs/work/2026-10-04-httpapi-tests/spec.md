# Spec — httpapi-tests

**Scope:** L · **Opened:** 2026-10-04 · **Phase:** 1, item **1.2**

## The change in one sentence

Add tests to `gateway/internal/httpapi` that drive `Ask` down every one of its exit paths and assert,
on each, both the HTTP response (`interfaces.md` §A) and the evaluation-log record (§H). The only
source change is the smallest one that makes the cache replaceable by an in-memory fake.

## What it serves

- **Phase 1, item 1.2** (`super-plan.md`): *"Every exit path of `Ask` — TIER1_HIT, TIER2_HIT,
  MISS, SHED, ABANDONED, GENERATION_FAILED — has a test asserting its response **and** its eval
  record."*
- **Exit-criterion clause discharged:** *"`httpapi` has tests covering every exit path of `Ask`."*
- **Standing constraint 6:** *"No measurement runs off an untested instrument."* Every number in
  the thesis passes through `Ask`, and the package has 983 lines and no tests.
- **Discharges:** **C1** (the cascade is where the reuse rule is applied) and **C3** (the eval
  record is the measurement). `contracts/requirements.md` is still empty, so no FR/NFR/RR ID can
  be cited yet.
- **Unblocks:** 1.3, which must not delete branches that nothing tests, and 1.4.

## Why scope L

`httpapi` is the measured path, so a silent error here costs the study rather than an afternoon.
The task also has to change source on that path, because the cache cannot be faked today (see
below). Both are L criteria. A test-only task would be S. This one is not.

## The exit paths, as the code stands (`handler.go` at `e47c206`)

| # | Path | Where | Response | Eval record |
| :---: | :--- | :--- | :--- | :--- |
| 1 | Wrong method | `:132` | 405 | none: returns before the deferred emit |
| 2 | Malformed body or empty question | `:138` | 400 | none: same |
| 3 | Tier-1 lookup error | `:185` | 500 | **one record, `cache` = `""`** (finding F-B) |
| 4 | **TIER1_HIT** | `:188` | 200 | `TIER1_HIT` |
| 5 | **TIER2_HIT** | `:295` | 200 | `TIER2_HIT`, plus async hit-count bump and Tier-1 promotion |
| 6 | **MISS**, leader | `:498` | 200 | `MISS`, `coalesced` absent |
| 7 | **MISS**, coalesced follower | `:498` | 200 | `MISS`, `coalesced: true` |
| 8 | **SHED** | `:469` | 503 + `Retry-After: 2` | `SHED`, `shed: true` |
| 9 | **ABANDONED** | `:485` | none written | `ABANDONED` |
| 10 | **GENERATION_FAILED** | `:491` | 502 | `GENERATION_FAILED` |

Four further paths **end in MISS by degrading**, and each is a promise the code makes in a comment
that nothing checks: an embedding failure (`:239`), a retrieval failure (`:250`), a Tier-2 search
failure (`cascade.go:85`, `:135`), and a failed write-back that must not fail the request (`:412`).

## Acceptance (each a check that can be run)

1. `cd gateway && go test -race -count=1 ./internal/httpapi/` passes. `make verify` does not run
   `-race` (`Makefile:259`), so this is a one-off check, and its result is recorded in `plan.md`.
2. Each of the six outcomes the item names (paths 4, 5, 6 and 7, 8, 9, 10) has at least one test
   asserting **the response and the eval record**. Paths 1–3 and the four degradations have tests
   asserting what no finding contradicts. For path 3 that is only the single record, because its
   status code belongs to F-B's fix.
3. The tests need **no Redis, no Ollama and no Python**. The cache is an in-memory fake. The RAG
   service is an in-process gRPC server behind the real `ragclient.Client`. The embedder is an
   `httptest` server behind the real `embed.Client`. Eval records are read back from a real
   `telemetry.Logger` file in `t.TempDir()`.
4. **The tests can fail.** Each mutation in `design.md` §7, applied by hand, makes at least one
   test fail. The results are recorded in `plan.md`. Example: swap the coalescing and admission
   nesting, or drop the deferred emit.
5. `make verify` stays green, and `gateway/cmd/gateway/main.go` compiles **unchanged**.
6. No test references a field or branch that item 1.3 deletes (`TauHigh`,
   `similarity_only_decision`, `Decision.SimilarityOnly`). Any test whose expectation 1.3 is
   *expected* to change is named in `approvals.md` before 1.3 starts (`design.md` §5).

## Findings made while reading for this task

F-A to F-D came from reading for this spec. F-E and F-F came from `impact.md` §8, and F-G to F-K
from `review.md`. F-A, F-C, F-D, F-E and F-F are restated here as the review corrected them.

**None is fixed in this task.** Each becomes a separate `/bugfix`, or for F-K a decision, and **no
test in this task pins the defective behaviour**. A test that asserted a bug would make the bug
immutable.

| # | Finding | Status | Consequence for the measurement |
| :--- | :--- | :--- | :--- |
| **F-A** | **Any client cancellation that reaches a gRPC call is logged `GENERATION_FAILED` and answered 502, not `ABANDONED`.**<br>• `ragclient` returns gRPC's `*status.Error` (code `Canceled`) unwrapped, and `errors.Is(err, context.Canceled)` is false for it.<br>• `Acquire`'s fast path takes a free permit **without checking the context** (`pool.go:93-97`). So a client that left during embed or retrieval still has `Answer` called on its dead context.<br>• Only a cancellation **while queued for the permit** reaches the `ABANDONED` branch | **Confirmed**, by probe (`evidence/grpc-cancel-probe.md`) and against the grpc source (`review.md`) | `ABANDONED` is undercounted and `GENERATION_FAILED` overcounted. At one slot most misses take the fast path, so under client timeouts this covers **most abandonments** |
| **F-B** | A Tier-1 lookup error writes one record with `cache` = `""` | Read from code | A seventh, unnamed outcome. `types.go:68-71` says a blank `cache` is indistinguishable from a lost record |
| **F-C** | An **uncontended** MISS logs `t_permit_wait_ms: null`, although a permit was requested. `msPtr` maps the zero `Waited` of an uncontended `Acquire` to `nil` | Read from code | §H says *"null unless a permit was requested"*. It can still be recovered offline from `cache = MISS` **and not `coalesced`**, because followers request no permit. So no data is lost, but the field does not mean what the contract says |
| **F-D** | **A coalesced follower inherits the leader's cancellation** (`coalesce.go:39`, documented there).<br>• If the leader is cancelled while queued, a follower whose client is still connected is logged `ABANDONED` and receives an **implicit `200` with an empty body**.<br>• If the leader is cancelled after taking the permit, the follower gets a 502 (F-A) | Confirmed by reading | A live client gets nothing, yet sees **success**: a load generator that checks only the status counts it as served, while §H counts it as having left. The k6 checks should require a non-empty `answer` |
| **F-E** | **A genuine `Retrieve` error produces a fake zero-overlap refusal.** If the nearest entry is at or above τ, `cascade.go:106` sets `EnteredBand` **before** the nil check at `:110`, and `Ask` then reads a zero `Decision`.<br>• Record: `entered_band: true`, `source_overlap: 0`, `similarity_only_decision: "MISS"`.<br>• Response: `source_overlap: 0`, `overlap_decision: false` | Confirmed by reading | High similarity with zero overlap is the lookalike-trap signature C1 counts. It is separable offline only by `retrieved_chunk_ids == null`. It affects runs in which the RAG service **errors**. A client cancellation during `Retrieve` ends in F-A instead. 1.3 probably removes it, and 1.3's spec should say whether it does |
| **F-F** | **The eval log is closed while shutdown is still draining.** `ListenAndServe` returns `ErrServerClosed` as soon as `Shutdown` *starts* (documented `net/http` behaviour). `main.go:257` then closes the log, and `main` returns, while handlers are still running | Confirmed by reading | Requests in flight at SIGTERM are **cut off and missing** from `requests.jsonl`. `Log` after `Close` returns silently, so `Dropped()` stays 0 and the INCOMPLETE check (`main.go:263`) does not fire. A racing `Log` panics inside a handler goroutine, which net/http recovers, so the gateway does not crash. **Avoided** whenever the harness stops the load generator before SIGTERM. The fix is cheap: close the log after `Shutdown` returns |
| **F-G** | **On a TIER2_HIT where the nearest entry overall is not the one served, `source_overlap` (response and §H) and `overlap_decision` describe the nearest entry, not the served one.** `Decision` is computed on `nearest` (`cascade.go:116`), the served `Candidate` is the scoped entry (`:152`, `:161`), and `handler.go:268-276` reads the overlap from `Decision`. `NSDecision.Overlap`, computed for the served entry (`:160`), is never read | Confirmed (`review.md`) | One entry's `entry_id` and `entry_sources` are logged with another entry's `source_overlap`. It happens whenever another namespace holds a closer entry, such as the same question cached for another product (B-cross). 1.3, by removing `nearest`, probably fixes it, and its spec should say so |
| **F-H** | **`GENERATION_FAILED` drops `t_generate_ms` although the generation ran.** It is computed at `handler.go:394` but copied into the record only on success (`:501`) | Confirmed (`review.md`) | A failed generation's duration is what separates a client timeout (F-A) from an immediate failure |
| **F-I** | The async Tier-1 promotion and the hit-count bump are **unguarded writes**, landing up to 2 s after the hit (`handler.go:304-338`). Once C2 purges entries, the promotion can write an unpurgeable Tier-1 copy of a purged answer, and `HINCRBY` recreates a stub `t2:` hash (`tier2.go:240-242`) | Plausible (C2 not built) | An input to Phase 4's design, not a bug today |
| **F-J** | **A failed write-back leaves no trace in §H.** Only stderr records it (`handler.go:420-445`). The record says MISS, with an `entry_id` that was never stored and `writeback_discarded: false` | Confirmed (`review.md`) | Under Redis trouble the hit rate falls with nothing in the measurement channel to explain it |
| **F-K** | **The rule that serves Tier 2 today is not the rule the thesis claims.** Served decisions use similarity ∧ namespace (`lane.go:292-296`: *"There is deliberately no containment term"*), and θ reaches only the logged counterfactual. `ConfigID` is logged but selects nothing (`handler.go:77`). The claim (`CLAUDE.md`, `Final_Proposal.md:150`) has four conjuncts, and item 6.1 sweeps θ | Confirmed by reading. **No entry in `decisions.md` records the change** | A θ sweep over this code moves no served decision. **This is the author's decision, above this task** (`approvals.md`, item 5). This task's fixtures satisfy all four conjuncts so they hold whichever way it goes |

## Out of scope

- Fixing F-A to F-J, and deciding F-K. Each fix becomes its own `/bugfix`, whose failing test
  is written there, first.
- Syncing §H's `cache` enum with the code. §H lists three values (`interfaces.md:445`), and the
  code emits six (`types.go:64-74`): SHED, ABANDONED and GENERATION_FAILED are documented
  extensions. The tests assert all six and label the three as extensions. **No BYPASS stub is
  added** to cover §A's fourth value, because the bypass classifier is cut scope.
- Removing the retired cascade branch (1.3), and carrying `texts` across the seam (1.4).
- The §H v0.9 fields (`refusal_cause`, `support_lex`, `support_numeric_ok`), which are Phase 2.
- `GET /stats` and `GET /products`, beyond the counters `Ask` itself bumps.
- Tests for `cmd/gateway` and `catalog/`.
- Any change to what is measured. `impact.md` confirms there is none.
