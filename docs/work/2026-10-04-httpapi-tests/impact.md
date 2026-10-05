# Impact — httpapi-tests

*`impact-analyst` (opus), 2026-10-04. Recorded as returned. The corrections it implies for `spec.md`
and `design.md` are listed at the end. They are **not** applied here.*

> **No frozen value is touched, and no run is invalidated, because none exists.** The one source
> change sits on the measured path, but it changes types only. Nine `h.Cache.*` call sites become
> interface dispatches. A scratch benchmark measured 2.05 ns per call either way, with 0 allocs. That
> is about 500× below the 1 µs resolution of every §H timing field (`handler.go:539`). **The real risk
> here is fidelity, not invalidation:**
> - the fake becomes the only executable witness of Tier-2 semantics;
> - 1.3 will legitimately move some of these tests' values (§7);
> - reading for this task found **two more silent measurement defects**, F-E and F-F, on paths these
>   tests traverse. No test may pin either of them.

## Packages touched

| Path | Change | Layering |
| :--- | :--- | :--- |
| `gateway/internal/httpapi/handler.go:57-58, :100-101` | `Handler.Cache` and `NewHandler`'s first parameter change type, from `*cache.Store` to an unexported interface | No import change. `httpapi → cache` already exists |
| `httpapi/` (new file, or inside `handler.go`) | The 8-method interface. It names `cache.Entry`, `Tier2Entry`, `Candidate` and `EvictedEntry`, all already imported | — |
| `httpapi/*_test.go` (new) | Tests, the fake cache, the gRPC fake, the embed fake | Test-only imports: `ragpb`, `grpc`, `grpc/codes`, `grpc/status`, `net`, `net/http/httptest` |
| `gateway/internal/coalesce/coalesce.go:94-102` | Add exported `Waiters(key)` wrapping `waiters` | No import change |
| `gateway/cmd/gateway/main.go:213` | **None.** It passes `store` (`:87`) and never reads `handler.Cache` | — |
| `gateway/go.mod`, `go.sum` | None | — |
| At `/done`: `architecture.md:143`, `CLAUDE.md` ("`httpapi/` has zero tests"), `super-plan.md:124` | Text | — |

## 1. Layering

The change respects the layering. `architecture.md:89-93` describes the request flow, not an import
chain. `go list` shows the real import graph is a star:
- `httpapi` imports `admission`, `cache`, `catalog`, `coalesce`, `embed`, `ragclient`, `reuse` and
  `telemetry`.
- None of those imports another internal package, except `ragclient → ragpb`.
- `telemetry` imports nothing internal.

No import points left and there is no cycle, before or after the change.

**Test-only exception:** the tests import `ragpb` directly, skipping `ragclient`. That is
acceptable only in `_test.go`, because `ragpb` is the far side of the seam being faked. The
production package must never import it.

**Pre-existing doc gap:** `architecture.md` §1 (`:43-53`) lists neither `internal/coalesce/` nor
`internal/ragpb/`.

The eight methods match the call sites exactly:

| Method | Call site |
| :--- | :--- |
| `Get` | `handler.go:182` |
| `BumpHitCount` | `handler.go:307` |
| `Put` | `handler.go:330` (promotion), `:420` (write-back) |
| `PutTier2` | `handler.go:430` |
| `TrimToCapacity` | `handler.go:451` |
| `Touch` | `handler.go:531` |
| `NearestTier2` | `cascade.go:82` |
| `NearestTier2InNamespace` | `cascade.go:132` |

`browse.go` never touches `h.Cache`.

## 2. Frozen values, measured path, invalidated runs

**Frozen values touched: none.**

| Frozen value | Where it lives | Effect of this change |
| :--- | :--- | :--- |
| `num_ctx`, `OLLAMA_NUM_PARALLEL` | permit count at `main.go:168-169` | not touched |
| Embedding model, `DIM` | `embed/client.go:23, :26` | not touched. Tests should read `embed.Dim`, not a literal 768 |
| `top_k` | `topKServerDefault = 0` at `handler.go:30` | not touched |
| Chunking, `dataset_version` | Python side | not in scope |
| FLAT index | `cache/tier2.go:81-85` | not touched. The fake's brute-force exact cosine is FLAT-equivalent and test-only |
| Eviction policy, capacity | `capacity.go`, `Handler.Capacity` | not touched |
| δ | — | not touched |

**Measured path: touched in type only.**
- The timed spans that now enclose a dispatched call are `t_tier1_ms` (`handler.go:181-183`) and
  `t_search_ms` (`cascade.go:81-83, :131-133`).
- The write-back calls (`:420-451`) run inside the permit hold, so a gateway-measured μ_gen absorbs
  them too (resolve-f1, N7).
- Cost, from a scratch benchmark on go1.26.1 darwin/arm64 with a non-inlined method: direct call
  2.05 ns, interface call 2.05 ns, 0 allocs either way. These methods are never inlined anyway,
  because each one is a Redis round-trip.
- §H rounds every span to whole µs (`durMS`, `handler.go:539`). The added cost is below the
  instrument's resolution.
- The `Waiters` seam is read-only and never called on the request path. **Keep it that way:** it
  takes `g.mu`, the same lock every `Do` takes.

**`run_id`s invalidated: none.** `experiments/results/` holds only `.gitkeep`, and the only commit
that ever touched it is `3901066`. The non-citable dev-v0 μ_hit probes (Tier-1 ≈ 8000 req/s, about
125 µs per request) are not affected by 2 ns.

## 3. Reinstates cut scope?

**No.** Nothing on `Final_Proposal.md:590`'s list is touched. Three cautions:
- **No `BYPASS` path or classifier stub** to "cover" the fourth enum value of §A. `types.go:33`
  names `BYPASS`, but no code produces it, so it stays untested.
- **No SSE.** The gRPC fake sends one terminal chunk.
- **No HNSW.**

## 4. New dependency?

**None.** `grpc`, `grpc/codes` and `grpc/status` are already in the module graph (`ragpb` imports
all three, per `go list`). `httptest` and `net` are stdlib. There is no resident footprint: this is
test binary only, and the interface adds no package to the gateway.

**Do not reach for:**
- `bufconn`. It is in the same module, but `ragclient.New` accepts no dialer, so it would force a
  `ragclient` source change.
- `miniredis`. It is a new dependency and has no `FT.SEARCH`.
- `testify` or `goleak`. Both are new dependencies and need sign-off (`coalesce.go:9`).

## 5. Contract change?

**No. The contract phase is not required.**

| Surface | Status |
| :--- | :--- |
| §A response (`types.go:31-61`) | unchanged |
| §H record (`evallog.go:22-74`) | unchanged |
| The `.proto` and `ragpb` | unchanged, no regeneration |
| §D Redis schema | unchanged. The fake is not a schema |

The tests do become the **first executable statement** of three existing code↔contract gaps. The
design should mark these as extensions rather than pin them unannounced:
- **§H's `cache` enum** (`interfaces.md:445`) lists `TIER1_HIT | TIER2_HIT | MISS`. The code emits
  six values (`types.go:64-75`). `super-plan.md` 1.2 itself names the six, so these tests are
  correct to assert them. §H still needs a dated doc sync through `decisions.md`, which is
  `interfaces.md:497`'s rule. That is not this task.
- **§H extensions:** `coalesced`, `reuse_rule` and `product_id` (`evallog.go:58-73`: "Promoting it
  needs an ADR").
- **§A extensions:** `lane`, `namespace`, `reuse_rule` and `overlap_decision` (`types.go:41-60`).

## 6. Measurement change?

**No. The experiment phase is not required.** What is logged, when, and how it is counted are all
unchanged.

The answer **flips to yes** if any of these slips in:
- a fix for F-A to F-F;
- any edit to `msPtr`, `durMS` or the deferred emit (`handler.go:165-178`) made to ease testing;
- `Waiters` being read on the request path, or its value logged.

Each of those needs its own `/bugfix` with its own impact.

## 7. Interactions with 1.3 and 1.4

**1.3** removes three things: the unfiltered phase (`cascade.go:79-105`), `TauHigh`
(`rule.go:112`) and `similarity_only_decision` (`handler.go:286-291`). On a MISS, every value below
comes from the **unfiltered nearest** today. After 1.3 it comes from the scoped search, or is null.

**Declare these in `approvals.md` before 1.3 starts (spec acceptance 6):**

| Test (by scenario; design names it) | Values 1.3 may change | Why |
| :--- | :--- | :--- |
| Cross-namespace lookalike refused (nearest overall ≥ τ, in another namespace) | `similarity`, `entered_band`, `source_overlap`, response `overlap_decision` | All are read off `nearest` (`cascade.go:94-98, :106, :116, :160`) |
| Retrieval-failure degradation (`handler.go:250`) | `similarity`, `entered_band`, `source_overlap`, `t_search_ms` | The unfiltered search runs without a namespace today. After 1.3, no namespace means no search. Also F-E |
| Any TIER2_HIT where nearest-overall ≠ nearest-in-namespace | response `overlap_decision` | `Decide` runs on `nearest` (`cascade.go:116`) |
| Anything that counts `NearestTier2` calls, and the fake's `NearestTier2` | method removed | It leaves the interface. To assert "no Tier-2 work on TIER1_HIT", count embed-server calls instead |
| **Existing:** `telemetry/evallog_test.go:69` | key list includes `similarity_only_decision` | field retired |
| **Existing:** `reuse/rule_test.go:99-100, :121-135, :182-213` | `SimilarityOnly`, `TauHigh` | 1.3 already names the stale `:185` pin |

**Must not change under 1.3:** the `cache` outcome and the HTTP status of every test above. If 1.3
changes an outcome, that is a behaviour change, not an expected one.

**Fixture rules that keep this list short:**
- Use one entry per namespace, so that nearest-overall equals nearest-in-namespace everywhere except
  the named tests.
- Build `reuse.Thresholds{Tau, Theta}` without `TauHigh`. The zero value disables the branch
  (`cascade.go:102`) and still compiles after 1.3.

**1.4:** no expected changes, **provided the gRPC fake populates `texts` positionally aligned from
day one** (`rag.pb.go:113`).
- `ragclient` drops `texts` today (`retrieve.go:13-17`).
- 1.4 may make it enforce "no partial population" (`interfaces.md:209-211`), or require `texts`
  outright for the gate. Either way, a fake that omits `texts` would turn every `Retrieve` into a
  failure, and every TIER2_HIT test would flip to MISS through the degradation path.

## 8. What would fail silently

| # | Hazard | Evidence | Design must |
| :---: | :--- | :--- | :--- |
| S1 | **Detached goroutines outlive `Ask`**: the hit-count bump and the Tier-1 promotion | `handler.go:304-310, :327-338`; `bumpTimeout` 2 s at `:47` | Treat a repeated question as racy: the second request is TIER1_HIT or TIER2_HIT depending on whether the promotion `Put` has landed. Wait on a fake-side signal channel, never a sleep. Read fake state under its lock, after the signal. Fake methods must never call `t.*`, which panics after the test ends |
| S2 | **Async logger** | `evallog.go:133-137, :155-158` | `Close` before reading, and only after every `Ask`, including goroutine-spawned ones, has returned. A `Log` after `Close` is discarded **without** incrementing `Dropped`. A `Log` racing `Close` can panic with "send on closed channel". Assert that the record count equals the number of `Ask` calls (0 for paths 1–2): `Dropped() == 0` alone still passes when a record is missing |
| S3 | Decoding into the writer's own struct | `evallog.go:22-74`, `types.go:31-61` | Decode into `map[string]any`. Round-tripping through `telemetry.Record` or `askResponse` hides tag drift from §H, and it cannot tell null from absent from zero. Never assert the full key set: it contains `similarity_only_decision` (1.3) |
| S4 | `ResponseRecorder` defaults `Code` to 200 | `httptest.NewRecorder` | For ABANDONED's "none written", assert an empty body **and** an empty header map. `Code` is 200 either way, and identical to F-D's empty 200 |
| S5 | A fast fake trips `msPtr`'s "zero means absent" | `handler.go:169-172, :541-547` | In a scratch probe on this M1 (41 ns clock tick), 9 of 200,000 near-empty in-memory calls timed exactly 0, which renders as `null`. Sub-µs spans render as `0.0`. So: never assert `t_search_ms > 0`. Assert non-null only where the fake searched a non-empty store. Assert null only where the stage provably did not run (TIER1_HIT, `pastTier1` false) |
| S6 | Data races | `handler.go:224-255, :386-387` | **None found in `Ask` by reading.** The `timings` fields are distinct words joined by `wg.Wait`. The `Do` closure writes the leader's own `rec` synchronously. Shared slices are only read. Not verified by `-race`, because no tests exist yet. Races would come from the scaffolding: the fake must copy slices in and out (Redis returns fresh slices, so aliasing would create races production cannot have); use per-test servers and fakes, or no `t.Parallel`; join spawned `Ask` goroutines before `Close` |
| S7 | `make verify` runs no `-race` | `Makefile:259` | Acceptance 1 is therefore a one-off check, and a later race passes `make verify`. Say so in `plan.md`. Adding `-race` is a separate S task |
| S8 | Typed-nil `*cache.Store` in the interface | no `h.Cache == nil` anywhere; `main.go:87, :213` | **No silent path today.** Nothing nil-checks it, and a typed nil panics on the first `Get` (`store.go:25-26`). Three methods do succeed on a nil receiver: `capacity.go:41-43, :62-64` and `tier2.go:153-157`. So a future no-cache config (config 1) must not be built as "nil store". No guard is needed now |
| S9 | A blocked gRPC handler | grpc `Server.GracefulStop` | The fake `Answer` that holds the permit (SHED, ABANDONED, coalescing) must select on `stream.Context().Done()`. Clean up with `Stop`. `GracefulStop` hangs on a blocked handler |
| S10 | **Fake fidelity** | `store.go:24-26`; `tier2.go:107-109, :153-157, :228-232`; `cascade.go:139-140` | Key Tier 1 with `cache.Key(cache.Normalize(q), pid)`. Return cosine similarity: Redis returns `1 − dist`, and the store converts it. An empty namespace returns `nil, nil`. Reject `len(vec) != embed.Dim`. **No τ or namespace decision inside the fake**: the Go check is the enforcement. Keep test similarities at least 1e-3 away from τ, because the fake computes in float64 and Redis in float32. **Residual:** `nearest`, `PutTier2` and `Get` have no real-Redis test (the cache tests cover only capacity, normalisation and tag escaping), so the fake encodes assumptions nothing else checks |
| S11 | Real Redis touched by accident | `Makefile:94-104`, `:201` | `make measure` does not check for a cold cache; only `demo` does. A test that wrote to DB 0 would leave `t2:` entries in `idx:cache` for the next measured run to serve from. No `httpapi` `_test.go` may import `go-redis`; check it with a grep in `/verify` |
| S12 | GENERATION_FAILED test returning `codes.Canceled` | F-A | Use `codes.Internal` or `codes.Unavailable`. `Canceled` pins F-A |
| S13 | Coalesced follower timings | `handler.go:386-387, :501`; `interfaces.md:488` | A follower logs `t_generate_ms` and `t_permit_wait_ms` as null. §H counts total − Σstages as "gateway overhead", so a follower's multi-second wait reads as overhead unless the analysis filters on `coalesced`. This is recoverable, not a logging defect. Do not pin it until design decides |

### New findings: add to `spec.md`'s table; no test pins either

| # | Finding | Status | Consequence |
| :--- | :--- | :--- | :--- |
| **F-E** | **A retrieval failure fabricates a zero-overlap banded refusal.** When `Retrieve` fails and the nearest entry is ≥ τ: `cascade.go:106` sets `EnteredBand` **before** the nil check at `:110-112`, then `handler.go:268-276, :286-291` read a zero `Decision`. The log gets `entered_band: true`, `source_overlap: 0` and `similarity_only_decision: "MISS"`. The response gets `source_overlap: 0` and `overlap_decision: false` | Read from code | High similarity with zero overlap is exactly the lookalike-trap signature C1 counts. `similarity_only_decision` is wrong outright, because similarity cleared τ. It is separable offline only by `retrieved_chunk_ids == null`. A client timeout during `Retrieve` reaches this path. 1.3 likely removes it incidentally. The spec's retrieval-failure test should assert only `cache`, status and `retrieved_chunk_ids: null` |
| **F-F** | **The eval log closes while shutdown drains.** `ListenAndServe` returns `ErrServerClosed` as soon as `Shutdown` **starts** (documented net/http behaviour). So `main.go:257-260` closes the log while in-flight handlers are still running | Read from code | Requests in flight at SIGTERM are **missing** from `requests.jsonl`, and `Dropped() == 0`, so `main.go:263`'s INCOMPLETE check does not fire. In the race window, the gateway instead panics with "send on closed channel" (`evallog.go:136` against `:158`) |

## Smallest change that satisfies the spec

**Keep:**
- One unexported 8-method interface: the type of `Handler.Cache` and of `NewHandler`'s first
  parameter.
- The in-memory fake, in `_test.go`.
- A gRPC fake on `127.0.0.1:0` behind `ragclient.New`, and an `httptest` embedder behind
  `embed.New`.
- A real `telemetry.Logger` in `t.TempDir()`.
- **One** exported `Waiters(key)` that **wraps** `waiters` rather than renaming it.
  `coalesce_test.go:62, :137, :178` call `waiters`, and tests are immutable.

`Waiters` is justified. Without it, the last thing a follower does that a test can observe is a
fake search, and there is still pure computation between that and `Do`. Releasing the leader on
that signal is a race.

**Cut:**
- A shared fake package such as `internal/cache/cachetest`. It is a new directory, and
  `architecture.md:15-16` forbids unlisted ones.
- Dialer options on `ragclient`.
- A nil guard in `NewHandler`.
- `-race` in the Makefile (separate S task).
- Fixes for F-A to F-F.
- `/stats` and `/products` tests beyond `Counters`.
- `testify`, `goleak`, `miniredis`.

**Mutation targets for `design.md` §7.** These are cheap, and they guard frozen plumbing:
- The fake `Retrieve` and `Answer` assert `TopK == 0` (`handler.go:30`).
- `Answer` receives exactly `Retrieve`'s chunk IDs (v0.7, `:393`).
- The embed request carries `search_query: ` and `nomic-embed-text` (`embed/client.go:18, :26`).
- The same question under two `product_id`s, concurrently, produces **two** generations (the
  coalesce key is `t1Key`, `handler.go:366-370`).
- A fake that returns a wrong-namespace candidate is refused by the Go check (`cascade.go:139-140`).
- Swapping the coalescing/admission nesting at `pool(1,0)` turns N−1 coalesced requests into N−1
  sheds.

## Invalidates

Nothing.
- **`run_id`s:** none exist.
- **Frozen values:** none changed.
- **Non-citable dev-v0 μ_hit probes:** not affected.

> **Required phases:** impact · implementation, plus design → opus design-review → plan for scope L.
> **Contract not required:** no §A–§H, `.proto` or §D surface changes. **Experiment not required:**
> nothing measured or counted changes, and the dispatch cost is below the instrument's resolution.

---

## Corrections this implies for the trail (not applied)

| # | Where | Correction |
| :---: | :--- | :--- |
| 1 | `spec.md` findings | Add F-E and F-F |
| 2 | `spec.md` "four degradations" | For the retrieval-failure test, assert `cache`, status and `retrieved_chunk_ids: null` only (F-E) |
| 3 | `spec.md` path 9 | "None written" is observed as an empty body and an empty header map; `rr.Code` is 200 regardless |
| 4 | `spec.md` acceptance 1 | `-race` is not in `make verify` (`Makefile:259`); state it as a one-off check |
| 5 | `design.md` §5 / `approvals.md` | Name the §7 scenarios, plus `evallog_test.go:69` and `rule_test.go`, as expected to change under 1.3 |
| 6 | Follow-up, not this task | Sync §H's `cache` enum (`interfaces.md:445`) with the six values the code emits. Add `internal/coalesce/` and `internal/ragpb/` to `architecture.md` §1 |
