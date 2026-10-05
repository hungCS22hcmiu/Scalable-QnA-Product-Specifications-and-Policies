# Design — httpapi-tests

**Scope:** L · **Spec:** `spec.md` · **Item:** 1.2 · **Revision 2**, 2026-10-04. Rev 2 applies
the resolutions in `review.md`: S1–S9 and N1–N6.

## 1. Shape of the harness

Each test builds its own `Handler` and calls `Ask` directly. There is no HTTP server on the gateway
side. Only the cache is faked at the Go level. The RAG service and the embedder are faked **at the
wire**, behind the real clients, so the tests also exercise how those clients surface errors.
F-A shows that how they surface errors is exactly where a misclassification hides.

```
test ─► h.Ask(w, req.WithContext(ctx))                   one Handler, one Logger per test
          │
          ├─ Cache ──────► fakeStore                     in-memory model   ← the only change in httpapi
          ├─ RAG ────────► ragclient.New(lis.Addr()) ──gRPC──► fakeRAG    grpc.NewServer on 127.0.0.1:0
          ├─ Embed ──────► embed.New(ts.URL, model) ──HTTP──► /api/embed  httptest.Server, 768-dim
          ├─ Admission ──► admission.New(permits, queue)     real
          ├─ Generations ► coalesce.Group (zero value)       real; Waiters() read by the test (U5)
          └─ Eval ───────► telemetry.Open(t.TempDir(), "t")  real; Close(), then read the JSONL
```

The Handler is configured the way `cmd/gateway/main.go` configures it, minus anything 1.3
deletes:
- `Thresholds{Tau: 0.85, Theta: 0.60}`, `LaneBand{Lo: 0.20, Hi: 0.20}`, `Capacity: 0`.
- `RunID`, `ConfigID` and `Mutation` set to non-default values, so the record has to carry them
  (S9).
- **`TauHigh` is never named.** Its zero value leaves the branch disabled, and the literal still
  compiles after 1.3 deletes the field.

## 2. The source changes

**One interface in `httpapi`.** Real Redis is ruled out for Tier 2, because **RediSearch refuses
to build an index outside DB 0**. Checked 2026-10-04: `FT.CREATE` on `-n 15` returns `Cannot create
index on db != 0`. DB 0 holds `idx:corpus` and the dev cache, and the `idx:cache`, `t1:` and `t2:`
names are constants (`tier2.go:23`, `:29`; `key.go:22`). A test there would write into the cache a
running gateway reads. `cache/capacity_test.go` gets away with DB 15 because it needs no index, and
it skips when Redis is down. A test that skips does not count as a covered path.

```go
// cacheStore is the part of *cache.Store that the request path uses. It exists so the tests can
// drive every exit path of Ask without Redis: RediSearch indexes only DB 0, which the dev cache
// occupies. *cache.Store is the only production implementation.
type cacheStore interface {
	Get(ctx context.Context, query, productID string) (*cache.Entry, bool, error)
	Put(ctx context.Context, query, productID string, e cache.Entry) error
	PutTier2(ctx context.Context, e cache.Tier2Entry, vec []float32) error
	NearestTier2(ctx context.Context, vec []float32, k int) ([]cache.Candidate, error)
	NearestTier2InNamespace(ctx context.Context, vec []float32, namespace string, k int) ([]cache.Candidate, error)
	BumpHitCount(ctx context.Context, entryID string) error
	Touch(ctx context.Context, entryID string, nowUnixNano int64) error
	TrimToCapacity(ctx context.Context, capacity int) ([]cache.EvictedEntry, error)
}

var _ cacheStore = (*cache.Store)(nil) // the real store must keep satisfying it
```

- `Handler.Cache` changes from `*cache.Store` to `cacheStore`, and so does `NewHandler`'s first
  parameter. `main.go` passes a `*cache.Store`, so it **compiles unchanged** (spec acceptance 5).
- **Nothing else in `httpapi` changes:** no method body, no ordering, no log line.
- **Cost on the hit path:** about 2 ns per call, the same for a direct call and an interface call
  (`impact.md` §2). Every §H timing is rounded to whole microseconds.
- **1.3 can shrink the interface.** When `NearestTier2` leaves it, the fake keeps a method nothing
  calls, so 1.3 does not have to edit a test file to compile.

**One read-only method in `coalesce`** (U5, option (a)). It wraps the existing method rather than
renaming it, because `coalesce_test.go:62`, `:137` and `:178` call `waiters`:

```go
// Waiters reports how many callers are blocked on key's in-flight call. A test seam for packages
// that coalesce through a Group (httpapi's coalescing test); never call it on a request path,
// since it takes the group's lock.
func (g *Group[T]) Waiters(key string) int { return g.waiters(key) }
```

The RAG client and the embedder **keep their concrete types**. Faking them at the wire needs no
interface, and it is the only way to see F-A.

## 3. The fakes and the fixture rule

**The fixture rule (S1).** Every Tier-2 fixture satisfies **every** reuse conjunct except the one
under test. That covers the conjuncts served today and the ones the thesis claims, which Phase 2
adds to this path (F-K):

| Conjunct | How the fixture satisfies it |
| :--- | :--- |
| similarity ≥ τ | Cosine τ + 0.10 for a hit. Below τ means τ − 0.10. **No test similarity lies within 0.05 of τ** (N2): the embed client narrows to float32 while the fake computes in float64 |
| namespace | SPEC lane, `product_id` set, and retrieval grounded in that product's document |
| containment ≥ θ | `retrieve(q).chunk_ids ⊇ entry.source_chunk_ids`, so the overlap is 1.0 |
| support (Phase 2) | The seeded answer is a **verbatim substring of `texts[0]`**, the text of the product chunk, and contains **no numerals** |

A test that refuses on one conjunct changes **only that one**: a different product for namespace,
a lower cosine for τ. Its MISS then has exactly one explanation.

**`fakeStore`** is an in-memory *model* of the store, not a per-call script. A script would encode
today's call sequence, and 1.3 changes that sequence.
- **Tier 1** is a map keyed by `cache.Key(cache.Normalize(q), productID)`. Those are the real key
  functions, so the fake partitions exactly as `Store.Get` and `Store.Put` do (`store.go:25`,
  `:67`).
- **Tier 2** is a slice of `(Tier2Entry, vec)`:
  - `NearestTier2` returns the highest cosine, as the raw cosine. That equals the real store's
    `1 − COSINE distance` (`tier2.go:232`).
  - `NearestTier2InNamespace` filters on an equal `Namespace` first. An **empty namespace returns
    nothing** (`tier2.go:153-157`).
- **Errors** can be injected per method. Each injected error that is actually returned is counted
  (`injectedReturned`), so a degradation test can prove its failure fired (S2).
- **Every write is recorded:** Tier 1, Tier 2, `BumpHitCount` and `Touch`. A `waitFor` helper with
  a deadline covers the two writes `Ask` makes **after** it returns, the bump and the Tier-1
  promotion (`handler.go:304`, `:327`).
- **The residual risk is stated.** The fake encodes three of the store's semantics: key
  partitioning, an empty namespace returning nothing, and similarity as cosine. If `cache.Store`
  diverged from them, these tests would not notice. That is for `cache/`'s own tests.

**`fakeRAG`** is a `ragpb.RagServiceServer` with per-test hooks `retrieve(req)` and
`answer(req, stream)`.
- **It is strict (N1).** A request with `TopK != 0` gets an error, which checks
  `topKServerDefault` (`handler.go:30`).
- It records every request and counts calls.
- **Retrieve** fills `texts` **positionally aligned with `chunk_ids`**. `ragclient` ignores the field
  today, and 1.4 can start reading it without these tests changing.
- **Answer** returns a `source_chunk_ids` set that **differs from the IDs it was given**: it drops
  the last one, as the service may (S7). Its `dataset_epoch` **equals** Retrieve's (S6).
- **A blocking hook selects on the test's release channel or `stream.Context().Done()`** (S4). A
  hook therefore never outlives its RPC, since `grpc.Server.Stop` does not wait for handlers.
- It runs on a real loopback listener, because `ragclient.New` takes only a target string and
  cannot be handed a `bufconn` dialer.

**The embedder** is an `httptest.Server` on `/api/embed`. It maps each `input` string, with the
`search_query: ` prefix included, to a 768-dim vector from a per-test table. **An unknown input
gets a 500 (N1)**, which checks the prefix. A controlled similarity is built as
`cos α·e₀ + sin α·e₁`.

**The helpers.**
- **`askOnce`** runs one `Ask`, closes the Logger, and decodes the JSONL into **`map[string]any`**,
  not into `telemetry.Record`, so that `null` and `0` stay distinguishable.
- **`askMany`** runs several requests concurrently, joins every one of them, closes the Logger, and
  matches records to requests by **`query_raw`** (S3).
- **Both helpers check, on every request (S9):**
  - The record count equals the number of `Ask` calls, which is the single-exit emit of §H.
  - `Counters.Requests` equals the record count.
  - The record carries `run_id`, `config_id`, `mutation` and `product_id`.
  - Every request sends `X-Thesis-Stratum`, and the record echoes it as `stratum`.
  - **On every 200:** the record's `request_id` equals the response's, and its `answer_sha256`
    equals sha256 of the response's `answer`. These are the join key and the judge's dedupe key.
- **The response writer.** `httptest.ResponseRecorder` reports 200 even when nothing was written,
  so the tests wrap it in a writer that records whether `WriteHeader` or `Write` was ever called.

## 4. Test inventory

Field names are §H's. "null" means the JSON key is present with a `null` value. Every test also
gets the helper checks above.

| Test | Path | Set-up | Asserts on the response | Asserts on the record |
| :--- | :---: | :--- | :--- | :--- |
| `TestTier1HitServesTheStoredAnswer` | 4 | Seed Tier 1 | 200; `cache`, `answer`, `sources`, `model_used`; `similarity` and `source_overlap` render `null` (§A) | `TIER1_HIT`; `entry_id`; `entry_sources`; `t_embed_ms`, `t_search_ms`, `t_overlap_ms`, `t_permit_wait_ms`, `t_generate_ms` null (the stages did not run); **embedder and RAG never called** |
| `TestMissGeneratesOnceAndWritesBothTiersUnderOneIdentity` | 6 | Empty cache; question in mixed case | 200 `MISS`; `answer` and `sources` from `Answer` | `MISS`; `t_generate_ms` non-null; `retrieved_chunk_ids` = Retrieve's; `dataset_epoch_at_retrieval` = the shared epoch.<br>**Written:** Tier-1 and Tier-2 `entry_id` = the record's; **both tiers hold Answer's source set**, not Retrieve's (S7); Tier-2 `t1_key` = the record's `t1_key` = `cache.Key(Normalize(q), pid)` (invariant 2); Tier-2 `dataset_epoch` = the shared epoch (S6).<br>`Answer` received Retrieve's IDs, so there is one retrieval. Repeating the question gives `TIER1_HIT` with the same `entry_id` |
| `TestMissThenParaphraseIsATier2Hit` | 6 → 5 | MISS on *q*; then paraphrase *q′*, same product and retrieval, cos τ + 0.10 | *q′*: 200 `TIER2_HIT` | *q′*'s `entry_id` = *q*'s. The partition the MISS **wrote** is the one the paraphrase is served from (S7) |
| `TestTier2HitInsideTheNamespaceAndPromotesToTier1` | 5 | **One** seeded Tier-2 entry, per the fixture rule | 200 `TIER2_HIT`; `similarity` non-null; `source_overlap` non-null (§A: null only when the cascade did not run, N4); `lane`, `namespace` | `TIER2_HIT`; `entry_id` = seeded; `entered_band`; **no `Answer` call**. After the async writes: one `BumpHitCount`, and a Tier-1 write with the **same** `entry_id`. Repeating the question gives `TIER1_HIT` with it |
| `TestTier2RefusesAnEntryFromAnotherNamespace` | 6 | Fixture rule, except the entry is grounded in **another product** | 200 `MISS`; `similarity` non-null | `MISS`; `entered_band`; a generation ran. **Declared 1.3-sensitive** (§5) |
| `TestBelowTauDoesNotEnterTheBand` | 6 | Fixture rule, except cos = τ − 0.10, **same namespace** (S1) | 200 `MISS`; `source_overlap` null | `MISS`; `entered_band` false. **Declared 1.3-sensitive** (§5) |
| `TestShedWhenPermitAndQueueAreBothFull` | 8 | `admission.New(1, 1)`. Request A blocks in `Answer`; wait for `InFlight()==1`. C, a different question, queues; wait for `Queued()==1`. Then B, a third question (N3) | B: **503**, `Retry-After: 2`, JSON `{error: busy, reason: generation_pool_saturated, request_id}` with `request_id` = B's record's | B: `SHED`, `shed: true`, **`permit_queue_depth: 1`**, `t_generate_ms` null. After release: A and C complete as `MISS`. `Counters.Shed` = 1 |
| `TestAbandonedWhileQueuedIsNotAShed` | 9 | `admission.New(1, 1)`. A blocks in `Answer`. B is **a different question** (S3); wait for `Queued()==1`; cancel B; **join B**. Only then release A and join it | B: **nothing written** | B: `ABANDONED`, `shed: false`. `Counters.Shed` = 0 |
| `TestGenerationFailureIsNotServedOrCached` | 10 | `Answer` returns `status.Error(codes.Internal, …)` | **502** | `GENERATION_FAILED`, `shed: false`; **neither tier written**. `t_generate_ms` not asserted (F-H) |
| `TestCoalescingWrapsAdmission` | 6, 7 | `admission.New(1, 0)`. Four identical concurrent questions. The leader's `Answer` blocks until `h.Generations.Waiters(t1Key) == 3` | Four 200 `MISS`, same `answer` | **One `Answer` call, zero sheds.** One record without `coalesced`, three with `coalesced: true`, all with the same `entry_id`. The leader's `t_generate_ms` is non-null; the followers' is not asserted (N5). `Counters`: Generated 1, Coalesced 3 |
| `TestCoalescingNeverCrossesProducts` | 6 | `admission.New(2, 0)`. The same question under two `product_id`s, concurrently. Both `Answer`s block until `InFlight()==2` (S8) | Two 200 `MISS`, each with **its own** product's answer | **Two `Answer` calls, two `entry_id`s**, no `coalesced` |
| `TestEmbedFailureDegradesToMiss` | — | A would-be TIER2_HIT is seeded (S2); the embedder returns 500 | 200 `MISS` | `MISS`; `similarity` null; `entered_band` false; Tier 1 written, **Tier 2 not**, since there is no vector |
| `TestRetrieveFailureDegradesToMiss` | — | A would-be TIER2_HIT is seeded (S2); `Retrieve` returns an error | 200 `MISS` | `MISS`; `retrieved_chunk_ids` and `dataset_epoch_at_retrieval` null; `Answer` received **no** IDs. **`entered_band`, `source_overlap` and `similarity` are not asserted:** F-E makes them wrong today |
| `TestTier2SearchFailureDegradesToMiss` | — | A would-be TIER2_HIT is seeded; an error is injected on **both** search methods (S2) | 200 `MISS` | `MISS`, and `fakeStore.injectedReturned > 0` |
| `TestWritebackFailureStillServesTheAnswer` | — | `Put` and `PutTier2` return errors | 200 `MISS` with the answer | `MISS` with `entry_id`. `writeback_discarded` is not asserted (F-J) |
| `TestTier1LookupErrorStillEmitsOneRecord` | 3 | `Get` returns an error | **Not asserted** (S5: the status belongs to F-B's fix) | **Exactly one record** and `Counters.Requests == 1`. Its `cache` is not asserted (F-B) |
| `TestRejectsBadMethodAndBody` | 1, 2 | GET; an empty question; invalid JSON | 405; 400; 400 | Not asserted: whether a malformed request counts as a request in §H is not decided here |

**Added after the implementation review** (`review.md`, I-1 to I-7):

| Test | Path | Set-up | Asserts |
| :--- | :---: | :--- | :--- |
| `TestAnotherNamespaceAboveTauDoesNotLiftAnEntryBelowTau` | 6 | Another namespace's entry at `hitCos`; an in-namespace entry at τ − 0.10 carrying `otherAnswer` | 200 `MISS`, the generated answer, one `Answer` call. Nothing 1.3 changes |
| `TestRecordCarriesTheRetrievalEpoch` | 6 | Answer reports `testEpoch + 1` | `dataset_epoch_at_retrieval` = Retrieve's. The stored Tier-2 epoch is Phase 4's to decide |
| `TestBoundedCacheTouchesTheServedEntryAndTrimsToCapacity` | 4, 5, 6 | `Capacity` 2 | Touch receives each served entry in order; Trim receives `[2]` |

Existing rows changed:
- **`TestTier2Hit…`** asserts the values, not only their presence: similarity, overlap = 1, the
  record's provenance, and the promotion's and the repeat's provenance.
- **`TestTier2RefusesAnEntryFromAnotherNamespace`** changes only the namespace of `hitFixture`
  (S1).
- **`TestTier2SearchFailure…`** has two subtests: both searches, and the scoped search only.
- **The coalescing tests** take `coalesced` absent or false as the leader.
- **`TestWritebackFailure…`** no longer asserts `entry_id` (F-J).

**Not asserted anywhere:**
- `similarity_only_decision` and `reuse_rule` for a similarity-only hit, which 1.3 retires.
- `overlap_decision`, the containment counterfactual, whose future after 1.3 is open (U6) and
  which F-G corrupts on some hits.
- Any timing **value**. A timing's null-ness is asserted only for the stages that cross a wire
  (`t_embed_ms`, `t_overlap_ms`, `t_generate_ms`), and where §H requires null because the stage did
  not run (TIER1_HIT). `msPtr` maps an exact zero to null, and the impact analysis measured 9
  exact-zero spans in 200,000 on this M1. So `t_search_ms` against the in-memory fake can render
  null at random.
- The three outcomes outside §H's enum are asserted as the code emits them and **labelled
  extensions** in the test (`types.go:68-71`). §H lists three values. Syncing it is a follow-up.
- Anything F-A to F-J would contradict.

## 5. What later items may and may not change

**1.3** replaces the unfiltered k=1 search, which applies the τ gate to the **global** nearest,
with a single namespace-scoped search. Two tests assert behaviour that belongs to the unfiltered
phase:
- **`TestTier2RefusesAnEntryFromAnotherNamespace`** asserts a non-null `similarity` on a refusal.
  Today that value comes from the global nearest. After 1.3, the scoped search finds nothing, so
  `similarity` may become `null`. That changes what the demo shows. §A says *"a high-similarity,
  low-overlap miss is the lookalike trap"*, so 1.3 has to decide this deliberately.
- **`TestBelowTauDoesNotEnterTheBand`** assumes the τ gate runs before the namespace decides.

Both are named in `approvals.md` **now**. 1.3 changes them only under a recorded decision.

Everything else is kept stable **by how it is built**:
- `TestTier2Hit…` seeds **one** entry, so the global and in-namespace nearest are the same entry,
  and F-G cannot arise.
- No test counts `NearestTier2` calls or asserts `overlap_decision`.
- The degradation tests count injected errors, not named calls.
- The retrieval-failure test asserts only what F-E does not corrupt.

**Phase 2** (the support gate and the cause code) **must not change any outcome these tests
assert.** The fixture rule (§3) satisfies the support conjunct in every hit fixture. If Phase 2
turns one of these hits into a refusal, the gate is wrong, not the test.

**1.4** changes nothing: the fake already sends aligned `texts`.

## 6. Unknowns

| # | Unknown | Status |
| :---: | :--- | :--- |
| U1 | Does a client cancellation reach `Ask` as `context.Canceled`? | **Resolved: no**, by probe (`evidence/grpc-cancel-probe.md`) and by the reviewer against the grpc source → **F-A**, which is broader than first stated |
| U2 | Does `go test -race` flag anything in `Ask`? | **Resolved: no.** 17 tests, `-race -count=50`, nothing flagged (`plan.md`, Verification) |
| U3 | Do detached goroutines outlive a test? | **Resolved:** the only ones are the TIER2_HIT bump and promotion, which the tests wait on |
| U4 | Can `ResponseRecorder` tell "nothing written" from 200? | **Resolved: no**, so the tests use a recording wrapper |
| U5 | How does the coalescing test know three followers are waiting? | **Resolved: option (a)**, `coalesce.Group.Waiters`, which the reviewer confirmed is sufficient (`review.md`). The author confirmed it on 2026-10-04 (`approvals.md`) |
| U6 | Does `overlap_decision` survive 1.3? | Open; not asserted |
| U7 | Can `Generations.Do` return `(nil, nil)`? | **Resolved: no** (`review.md`) |
| U8 | Is the Phase 2 gate on or off in a zero-value `Handler`? | Settled at 2.4. The fixture rule makes it moot for these tests |

## 7. Mutations: the tests must be able to fail

Each mutation is applied by hand, the suite is run, and the mutation is reverted. The result goes
into `plan.md`. A mutation that no test catches is a gap to close before `/done`.

| # | Mutation | Expected to fail |
| :---: | :--- | :--- |
| M1 | Acquire the permit **outside** `Generations.Do` | `TestCoalescingWrapsAdmission` (by deadline) |
| M2 | Move `h.Eval.Log(rec)` out of the defer and into the MISS branch only | The record-count check on every non-MISS path |
| M3 | Recompute the Tier-2 `T1Key` from the **raw** question | `TestMissGenerates…` (mixed-case question) |
| M4 | Mint a second `entry_id` for the Tier-2 write | `TestMissGenerates…`; `TestMissThenParaphrase…` |
| M5 | Drop `rec.Shed = true` | `TestShedWhenPermitAndQueueAreBothFull` |
| M6 | Serve Tier 2 on `t2.Found && similarity ≥ τ`, ignoring the namespace decision | `TestTier2RefusesAnEntryFromAnotherNamespace` |
| M7 | Delete the Tier-1 promotion goroutine | `TestTier2HitInsideTheNamespace…` (by deadline) |
| M8 | Return 500 when the Tier-1 write-back fails | `TestWritebackFailureStillServesTheAnswer` |
| M9 | Classify a context cancellation as `SHED` | `TestAbandonedWhileQueuedIsNotAShed` |
| M10 | Always pass `nil` retrieved IDs to `Answer` | `TestMissGenerates…` |
| M11 | Coalesce on the normalized question alone, without `product_id` | `TestCoalescingNeverCrossesProducts` (by deadline) |
| M12 | Omit `Namespace` from the `PutTier2` entry | `TestMissThenParaphraseIsATier2Hit` |
| M13 | Write Retrieve's chunk IDs instead of Answer's to both tiers | `TestMissGenerates…` |
| M14 | Drop the `X-Thesis-Stratum` read | The helpers' `stratum` check |
| M15–M27 | Added after the implementation review: the measured values on the hit path (M15–M20), the record's epoch (M21), capacity and LRU (M22–M24), the cascade's second error branch (M25), τ on the served candidate (M26), and the namespace term once θ is served (M27) | `review.md`, Resolutions; all CAUGHT |

## 8. Failure modes of the tests themselves

- **Flakiness from timing.** No `time.Sleep` decides an outcome. Waits poll `InFlight()`,
  `Queued()`, `Waiters()` or the fakes' counters, under a deadline that **fails** the test and
  never passes it.
- **Cleanup order (S4).** `t.Cleanup` runs these steps in order:
  1. Release every blocked hook.
  2. `Stop` the gRPC server.
  3. Join every `Ask` goroutine the test spawned, under a deadline.
  4. Close the embed server.
  5. `Close` the Logger.

  Closing the Logger before the joins would let a late `Log` panic with "send on closed channel"
  on a test goroutine. That kills the whole binary and hides the failure that triggered cleanup.
- **Pollution.** Each test owns its Handler, Logger directory, fakes and ports. Nothing is shared
  at package level.
- **The suite does not prove:**
  - Redis semantics, which belong to `cache/`.
  - The Python service's behaviour.
  - Any latency value.
  - `GET /stats` and `/products`.
