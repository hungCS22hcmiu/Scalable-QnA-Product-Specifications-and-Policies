# Impact — carry-chunk-text

*`impact-analyst` (opus), 2026-10-05. Recorded as returned. The corrections it implies for `spec.md`
and `design.md` are listed at the end. They are **not** applied here.*

> **No frozen value is touched and no run is invalidated, because none exists.**
> `experiments/results/` holds only `.gitkeep`.
>
> The change is on the measured path. `Retrieve` runs on every Tier-1 miss, inside `t_overlap_ms`.
> But a scratch benchmark puts the added work at **0.6–1.6 µs per Tier-1 miss**: Python serialise
> plus Go unmarshal, from dev-v0 typical up to a v1 upper bound. The span is ~18 ms, so the cost
> is at most one or two ticks of §H's 1 µs resolution.
>
> **It is conformance to §B v0.9, not a contract change.**
>
> **The real risk is vacuity and indistinguishability, not invalidation:**
> - **A stale server looks compliant.** An absent `texts` is legal (`interfaces.md:209`). So a
>   **pre-1.4 server answering on :50051** (the open `rag-server-reuseport` hazard) looks exactly
>   like a compliant one, and no error is raised anywhere. The live test is the only detector, and
>   only if it fails on absent texts before it loops.
> - **The live check can pass while proving nothing.** It can pass **without dialing** (the
>   `go test` result cache). It can also pass **over zero elements**: an empty or length-1 array
>   makes the alignment loop, the distinctness precondition and the rotation all vacuous.
> - **Precondition: item 1.2's work is uncommitted.** `ask_test.go` and `harness_test.go` are
>   untracked (`??`); `handler.go` and `coalesce.go` are modified (` M`). So acceptance 5 ("no
>   assertion in `ask_test.go` changes") has no baseline to diff against. Commit 1.2 first.

## Packages touched

| Path | Change | Layering |
| :--- | :--- | :--- |
| `rag/src/rag/server.py:18-22` | Add `texts=[c.text for c in chunks]` beside `chunk_ids` and `scores`, built from the **same** list | No import change |
| `gateway/internal/ragclient/retrieve.go:13-17, :32-36` | Add `RetrieveResult.Texts []string`. `len(texts) == 0` → `nil`. `0 < len(texts) ≠ len(chunk_ids)` → sentinel error | Stdlib only (`errors` is already imported by the package). The production graph stays `ragclient → ragpb` |
| `ragclient/` new `_test.go`, `package ragclient` | Unit tests, with their **own** fake | `ragpb`, `grpc`: already test imports (`go list`) |
| `ragclient/` new `_test.go`, `package ragclient_test` | Live, env-gated, end-to-end | Test-only: `ragclient`, `go-redis/v9`. See §1 |
| `rag/tests/` new `test_*.py` | pytest unit test of `RagServicer.Retrieve`, with `retrieve.retrieve` monkeypatched | `rag.server`, `rag.retrieve`, `rag_pb2` |
| `Makefile:38` plus one new target | The live check, added to `.PHONY` | — |
| `docs/work/2026-10-05-carry-chunk-text/evidence/` | One live run, plus the pressure level read before it | — |
| **Unchanged** | `contracts/rag/v1/rag.proto`, `ragpb/`, `rag/src/rag/pb/`, `interfaces.md`, `httpapi/*`, `reuse/*`, `cmd/gateway/main.go`, `retrieve.py`, `go.mod`, `go.sum`, `pyproject.toml` | — |
| At `/done` | `super-plan.md:118-119` (progress line), `:126` (the 1.4 row), `:164` (mark 1.4 done in 2.1's "Unblocked when"); `architecture.md:125-127` (§4 target list); `CLAUDE.md` "Commands that work today" | Text |

## 1. Layering

**The production imports do not change.**
- `go list` today: `ragclient` imports `context`, `errors`, `ragpb`, `grpc`,
  `grpc/credentials/insecure` and `io`.
- `go list -deps ./internal/ragclient | grep -c redis` is `0`. It must still be `0` afterwards.
  Put that grep in `/verify`.

**Where the live test lives:** in `ragclient`, as an external test package (`package ragclient_test`).
A `_test.go` there importing go-redis is acceptable:
- **No layering violation.** `architecture.md:90-93` governs the production graph. A test-only
  import of an external library points left at no internal package. It cannot create a cycle,
  because go-redis imports nothing of ours. Precedent: `cache/capacity_test.go:8` already imports
  go-redis in a test.
- **No ownership violation.** `ragclient`'s only "must never" (`architecture.md:105`) is being
  constructed per request. One `ragclient.New` per test does not break it.
- **The cross-boundary read is justified, and required.** Reading `corpus::*` from the gateway side
  reads an index that the Python service owns. `catalog/` already makes the same kind of read
  (`catalog.go:1-11`, `architecture.md:83-85`), on the same justification: read-only, and on no
  request path. It is also required here, because the oracle must be independent of both sides. It
  therefore cannot go through `catalog` (FT.SEARCH, demo-only) or `cache`.
- **The external package is the better choice, not just an acceptable one.** It can reach only
  `ragclient.New` and `Retrieve`, so it exercises the production dial and decode path. It cannot
  reach `c.rpc` the way the in-package fakes do (`retrieve_test.go:27-28`).

**Not elsewhere:**

| Candidate | Why not |
| :--- | :--- |
| `httpapi/` | 1.2's S11 forbids go-redis in any `httpapi` `_test.go` (`2026-10-04-httpapi-tests/impact.md:192`). And the seam under test is `ragclient`, not `Ask` |
| A new `gateway/test/e2e/` or `internal/e2e/` | `architecture.md:15-16`: *"A directory not listed here should not exist."* It would need an architecture amendment, for nothing gained |
| `cmd/gateway/` | Wiring only (`architecture.md:42`) |
| A Python gRPC client in `rag/tests/` | Proves Python → Python. It skips `ragclient`'s decode, which is half of what 1.4 must prove |

**Two constraints on that file:**
- **Hard-code `"corpus::"`**, citing `store.py:62` and `cache/tier2.go:25-27`. **Do not import
  `cache` or `catalog`** for the constant. `ragclient → cache` points left even in a test, and
  neither package owns the corpus key.
- **Strictly read-only against DB 0.** RediSearch indexes only DB 0
  (`2026-10-04-httpapi-tests/approvals.md:48-49`). DB 0 holds the corpus (44 `corpus::*` keys), the
  dev cache (4 `t1:`, 3 `t2:`), and, on this shared machine, possibly other projects' keys. **Do not
  copy `capacity_test.go:14-25`.** Its DB 15 holds no corpus, so every `HGET` would return
  `redis.Nil`. Its `FlushDB`, pointed at DB 0, would destroy the corpus index. `HGet` is the only
  command the test may issue.

**Gate it with an environment variable, not a build tag.**
- A build-tagged file is invisible to `go vet ./...` (`Makefile:270`), so it rots unnoticed. An
  env-gated file compiles on every `make verify`.
- When the variable is set, an unreachable server or Redis must `t.Fatal`, never `t.Skip`.

## 2. Frozen values, measured path, invalidated runs

**Frozen values touched: none.**

| Frozen value | Where | Effect |
| :--- | :--- | :--- |
| `num_ctx`, `OLLAMA_NUM_PARALLEL` | `config.py:44`, `Makefile:30` | Not touched |
| Embedding model, `DIM` | `config.py:10-11` | Not touched. The live check loads `nomic-embed-text` through the server's `Retrieve` (≈ 0.37 GB, `Makefile:113`) |
| `top_k` | `config.py:16`. The gateway sends 0 (`handler.go:263`) | Not touched. The live test must also send 0, as production does |
| Chunking (`CHUNK_SIZE=256`, `CHUNK_OVERLAP=40`), `dataset_version` | `config.py:14-15, :19` | Not touched |
| FLAT index | `store.py:35` | Not touched |
| Eviction policy, capacity, δ | gateway | Not touched |

**Measured path: touched, below the noise.**
- `Retrieve` runs concurrently with the embedding on every Tier-1 miss (`handler.go:260-271`). Its
  span is `timings.Overlap`, logged as §H `t_overlap_ms`.
- It is on the critical path of a Tier-2 hit, because both embeddings share `nomic-embed-text`'s
  single slot (`super-plan.md:232`).
- Tier-1 hits return at `handler.go:204-222`, before `Retrieve`, so they are unaffected.

**Payload and cost.** Chunk sizes come from `redis-cli HSTRLEN` over the 44 dev-v0 chunks: min
131 B, mean 212 B, max 588 B. The four largest are the policy documents, at 508–588 B. The costs
come from a scratch benchmark on this M1, run on a copy of the module in the session scratchpad
(nothing committed): Go `proto.Unmarshal`, and Python `RetrieveResponse(...).SerializeToString()`
on the upb backend, with five chunk IDs.

| Case | Wire bytes | Go unmarshal | Python build + serialise | Added per Tier-1 miss |
| :--- | ---: | ---: | ---: | ---: |
| Today (no `texts`) | 202 | 440 ns · 632 B · 11 allocs | 1.27 µs | — |
| dev-v0 typical (5 × 212 B) | 1,277 | 670 ns · 1,992 B · 20 allocs | 1.61 µs | +0.57 µs |
| dev-v0 worst (top 5 = four policies + the largest product, 2,455 B) | 2,672 | 826 ns · 3,416 B · 20 allocs | 1.76 µs | +0.88 µs |
| v1 upper bound (estimate: 256 tokens × ~4.3 B ≈ 1.1 KB, × 5) | 5,717 | 1,205 ns · 6,632 B · 20 allocs | 2.08 µs | +1.58 µs |

- **No extra round-trip.** Even the largest case is one HTTP/2 DATA frame (default maximum
  16 KB) over loopback. gRPC's 4 MB receive limit is nowhere near.
- **Below the instrument.** Against `Retrieve`'s ~18 ms (`handler.go:235`), the added time is
  ≤ 0.01 %. §H rounds to 1 µs (`durMS`, `handler.go:555`), so this is one or two ticks on a span
  whose run-to-run jitter is milliseconds (Ollama embedding).
- **No memory concern.** On the gateway heap it is ≤ 6.6 KB and 9 more allocations per Tier-1
  miss, held for the life of the request. At the sweep's ≲ 16 req/s (`super-plan.md:261-262`),
  that is ~100 KB/s of garbage, which is negligible in the envelope.

**`run_id`s invalidated: none.** `experiments/results/` contains only `.gitkeep`, and the only
commit that ever touched it is `3901066` (the 2026-08-09 scaffold).

**The planning figures.** The Tier-2 μ_hit of ≈ 61 req/s was measured co-hosted on dev-v0,
2026-09-06 (`Final_Proposal.md:101`), and is cited at `super-plan.md:56, :270`. It was
**necessarily taken without texts**: `texts` entered §B at v0.9 on 2026-09-21
(`interfaces.md:503`), and `server.py` has never populated it. What that means:
- **It is not invalidated.** It was never citable (`decisions.md:67`, standing constraint 3). Its
  only job is to anchor a lower-bound argument, whose threshold is μ_hit ≳ 15.6 req/s
  (`h* > 0.988 ⟺ μ_hit > 0.988 × 0.19 / 0.012`).
  - At 61 req/s the per-hit budget is ~16.4 ms, and 1.6 µs moves it by < 0.01 %.
  - The 3.8× margin (`super-plan.md:280-284`) is unchanged to three significant figures.
- **It already describes a different system, in bigger ways.** Since 2026-09-06, `τ_high` has
  been retired and retrieval has moved onto every Tier-1 miss (`Final_Proposal.md:101`). Texts is
  the smallest of these drifts.
- **Phase 7 measures with `texts` on** (spec "Out of scope", last bullet). That is correct: the
  measured system is the one that carries texts. No texts-off baseline is needed, because no
  comparison across this change exists.
- **The Tier-1 ≈ 8000 req/s probe** never reaches `Retrieve`, so it is untouched.

## 3. Reinstates cut scope?

**No.** Nothing on `Final_Proposal.md:590`'s list is touched. `texts` exists for the support gate,
which is in scope: it arrived at v0.9 (`interfaces.md:34-45`), and the gate is adopted from prior
work rather than claimed (`CLAUDE.md`).

Three cautions:
- **No ML runtime on the hit path.** The gateway receives strings. There is no tokenizer model and
  no embedding of `texts`. 2.1's tokenisation must stay a pure-Go stop-word filter.
- **Texts are retrieval evidence, not query text.** Reading them does not breach "the reuse
  decision must never read the query text as a predictive signal".
- **No streaming.** `Retrieve` stays unary, and `Answer` is untouched.

## 4. New dependency?

**None.**
- **Go:** `github.com/redis/go-redis/v9 v9.22.0` is already a direct requirement in
  `gateway/go.mod`, imported by `cache`, `catalog` and `cmd/gateway`. The test import adds no line
  to `go.mod` or `go.sum`. `grpc` and `ragpb` are already test imports of `ragclient`.
- **Python:** pytest's built-in `monkeypatch`. No new package in `pyproject.toml`.
- **Resident footprint: zero.** Test-only imports never reach the gateway binary. The runtime cost
  is the ≤ 6.6 KB per request in §2.

**Do not reach for:**
- `testify`.
- `miniredis`. It has no `FT.SEARCH`, and the oracle needs the real corpus anyway.
- `bufconn`. `ragclient.New` takes no dialer (`2026-10-04-httpapi-tests/impact.md:107-108`).

## 5. Contract change?

**No. This is conformance to v0.9, and the contract phase is not required.**

| Surface | Status | Evidence |
| :--- | :--- | :--- |
| §B `RetrieveResponse.texts = 4` | Already frozen; unchanged | `interfaces.md:190-196, :209-219`; the v0.9 row at `:503`; `rag.proto:41-51`; `rag.pb.go:113, :169` (`GetTexts`); `rag_pb2.py` (descriptor; checked by building `RetrieveResponse(texts=…)` in the benchmark). No `make proto` |
| §B "absent entirely or aligned; there is no partial population" | **Enforced at the client for the first time** | `interfaces.md:209-210`, `rag.proto:42-43`. The v0.9 note calls an absent `texts` "today's behaviour exactly" (`:44`), so nil on absence is required, not optional |
| §D Redis schema | Unchanged. Texts are not stored | — |
| §H record | Unchanged. Texts are not logged (spec, "Out of scope") | `evallog.go` untouched |
| `interfaces.md:212-213` | `texts` **is** the schema `text` field | This pins what 2.1 gets: raw chunk text, with **no** metadata (title, category). Metadata-enriched evidence would be a §B change |

**Does the partial-population error change §H semantics?** No field, value or count changes. One
new cause is added behind an existing null:
- **Before:** a malformed response is accepted, and its `texts` are dropped.
- **After:** `Retrieve` returns an error, so `retrieved == nil` (`handler.go:265-268`). Then
  `retrieved_chunk_ids` and `dataset_epoch_at_retrieval` are logged as null (`:297-301`). On the
  miss path, `Answer` falls back to its own retrieval (`:388-391, :409`).
- **Unreachable with the in-tree server**, because all three arrays come from one `chunks` list.
  Only a modified or foreign server can reach it.
- **If it is reached,** two existing behaviours of "retrieval failed" follow. The new error only
  adds a way in:
  - Before 1.3, with the nearest entry ≥ τ, F-E fabricates `entered_band: true` and
    `source_overlap: 0` (`cascade.go:106-112`).
  - The fallback re-embeds inside the permit. That adds ~18 ms to `t_generate_ms`, and to a μ_gen
    measured at the gateway (resolve-f1, N7).
- **Make it distinguishable.** Use a sentinel error (`ErrTextsMisaligned`, matched with
  `errors.Is`):
  - The unit test then asserts **which** error. A test that only checks `err != nil` also passes
    on an unrelated failure.
  - The gateway's stdout line then names the cause.

## 6. Measurement change?

**No. The experiment phase is not required.** What §H logs, when it logs it, and how outcomes are
counted are all unchanged. The one timed span that encloses new work grows by 0.6–1.6 µs (§2), and
no earlier run exists to compare against.

**The answer flips to yes if any of these slips in:**
- `texts`, or its hash or length, written to §H.
- Python fetching the text with a **second** Redis read (`fetch_by_ids`, `HMGET`) instead of
  reading `c.text`. That adds a round-trip inside `t_overlap_ms` on every Tier-1 miss.
- `Answer` accepting texts from the gateway to skip `fetch_by_ids`. That is a §B change, and it
  moves work inside the permit.
- Any consumer of `Texts` in `httpapi/` or `reuse/`. That is 2.1's, with its own impact.
- A startup or per-request "texts present" probe on the request path.

## 7. Interactions

**1.2's harness and `ask_test.go`: no assertion or check changes.**
- The wire fake builds `ChunkIds` and `Texts` from the same `p.texts` (`harness_test.go:127-133,
  :492-503`). Their lengths are equal by construction, so the new error cannot fire.
- Error injection returns `nil, err` before any response is built (`:517-519`). So
  `TestRetrieveFailureDegradesToMiss` (`ask_test.go:551-577`) is unaffected.
- `ask_test.go` builds no `RetrieveResponse` of its own (checked by grep).
- The header lists "misaligned texts" as a strict check (`harness_test.go:5-8`). That is a
  property the fake **produces**, not one it checks. 1.4 needs no harness change, so approvals
  item 4 does not come into play.

**Every `RetrieveResponse` in the gateway tests:**

| Site | `chunk_ids` / `texts` | Under the new check |
| :--- | :--- | :--- |
| `httpapi/harness_test.go:497-502` | n / n, from the same source | Aligned, no error |
| `ragclient/retrieve_test.go:21` | 0 / 0 (`&RetrieveResponse{}`) | Absent → `nil`, no error. `TestRetrievePassesProductID` and `TestRetrieveEmptyProductIDIsZeroValue` stay green |
| `ragclient/answer_test.go` | No `Retrieve` response | — |

None of them becomes a degraded MISS.
- **Keep `retrieve_test.go` byte-identical.** Put the new configurable fake in a new file.
- Adding a response field to `fakeRagServiceClient` (`:14-22`) would edit an existing test file,
  and tests are immutable.

**1.3 (remove the retired branch): no ordering conflict.**
- **The file sets are disjoint.**
  - 1.4: `server.py`, `ragclient/retrieve.go`, and new test files.
  - 1.3: `cascade.go`, `handler.go`, `reuse/rule.go`, `telemetry/evallog.go`, and the two named
    `ask_test.go` tests.
- **Nothing of 1.4's moves if 1.3 removes F-E,** because 1.4 adds no test that pins F-E's
  signature.
- **Do not add an `httpapi` test for "misaligned texts → MISS".** It would pin F-E, and it would be
  an `ask_test.go` assertion.
- Both tasks should branch from a **committed** 1.2.

**What 2.1 (the lexical arm) needs from this task:**
- **`RetrieveResult.Texts`, aligned with `ChunkIDs`.** `tryTier2` already receives `retrieved`
  (`cascade.go:74`), so no signature changes.
- **`nil` on absence, with no error.** **2.1 decides what absence means** (spec, "Out of scope").
  Two traps, both in §H:
  - **(a)** Refusing on absent texts with `refusal_cause: SUPPORT` inflates the gate's measured
    contribution with refusals it never computed (`interfaces.md:486`).
  - **(b)** Logging absent texts as `support_lex: null` on the gate-on arm writes the signature §H
    reserves for the **gate-off** arm (`:487`). The request is silently misattributed.
  - An absent-evidence cause may need its own §H value. That is a contract question for 2.1 and
    2.3, not for this task.
- **A fixture that already suits the gate.** Every fixture answer is a verbatim, numeral-free
  substring of chunk 0 (`harness_test.go:149-163`).
- **A template.** 1.4's live test is the pattern for 2.1's live reproduction of the
  `lane_test.go` pair.

**`rag-server-reuseport` (`super-plan.md:132-135`, `server.py:52`): this is where absent texts
become dangerous.**
- **A stale run leaves no trace.** A server started before 1.4 returns no `texts`, and ragclient
  accepts that as legal absence: no error, no log. The gateway dials once and multiplexes over
  that connection (`client.go:9-12`). If the connection landed on a stale instance, the whole run
  is texts-less, and nothing records it.
- **Harmless today, not after 2.1.** Nothing reads `Texts` yet. After 2.1, a stale instance
  silently disables the gate or refuses everything, depending on (a) and (b) above.
- **The live test does not certify the gateway's instance.** It opens its own connection. On a
  port shared through `SO_REUSEPORT`, nothing guarantees that connection reaches the instance the
  gateway is pinned to. A pass certifies the instance the **test** reached, not the gateway's.
- **A cheap guard fits inside this task's Make target:** fail unless
  `lsof -nP -iTCP:50051 -sTCP:LISTEN` shows exactly one listener (none was running during this
  analysis). It does not fix the hazard, which stays the author's decision. It stops 1.4's
  evidence being recorded against an ambiguous port.

## 8. What would fail silently

Ranked.

| # | Hazard | Evidence | Design must |
| :---: | :--- | :--- | :--- |
| S1 | **A vacuous live pass over zero or one element.** `for i := range texts` passes on an empty array. "Pairwise distinct" is vacuously true when the length is ≤ 1. Rotating a length-1 array changes nothing | Absence is legal (`interfaces.md:209`). With `product_id`, `_drop_other_products` (`retrieve.py:77-102`) can leave only the spliced chunk: length 1 | Assert `len(texts) == len(chunk_ids) ≥ 2` **before** any loop, and fail when texts are absent. Run the rotation on the **unscoped** response (5 chunks on dev-v0). Measured: no two of the 44 dev-v0 chunks share a text, so the distinctness precondition can be met |
| S2 | **The `go test` result cache.** A second run of the live target prints `ok … (cached)` without dialing. Go keys its cache on env vars and files read, not on network state | `Makefile:258` passes no `-count` | The target runs `go test -count=1 -v -run '<live>' ./internal/ragclient/`. `-v` makes a SKIP visible |
| S3 | **A stale server looks the same as absent texts** (§7) | `server.py:50-52`, `super-plan.md:132-135` | The single-listener check in the target. S1's "fail when absent" is the only detector inside the test. Hand traps (a) and (b) to 2.1 |
| S4 | **`make verify` never runs the oracle.** The live test skips whenever the env var is unset, and `go test ./...` prints `ok` either way. So a later break in LlamaIndex's text mapping passes `verify`. Three ways it can break: the schema `text` field is dropped, and LlamaIndex falls back to `_node_content` (`…/redis/base.py:785`); the legacy `except` branch sets `text=""` (`:789`); the `get_content` default changes. Today `BaseNode` defaults to `MetadataMode.ALL` and `TextNode` and `NodeWithScore` to `NONE` (llama-index-core 0.14.23), while `pyproject.toml` pins only `>=0.11` | `Makefile:258-261, :274-276` | State in `plan.md` that the pytest and Go unit tests cover only the servicer and the client, and that the evidence file is the only record of the live path. Do **not** edit `_to_chunks` in this task: it also feeds generation |
| S5 | **The splice is never actually exercised.** If the product's chunk ranks naturally, `_ensure_own_chunk` returns early (`retrieve.py:113-114`), and acceptance 3's "with `product_id`" covers nothing | `retrieve.py:105-119` | Pair the scoped call with an **unscoped call on the same query**. Assert the product's chunk is absent from the unscoped result and at index 0 of the scoped one (`(own_nodes + nodes)[:top_k]`, `:119`) |
| S6 | **`redis.Nil` read as `""`.** `HGet(...).Val()` returns `""` for a missing key or field. If the server also sent `""` (S4's legacy branch), `"" == ""` passes. A key built with a single colon also finds nothing | go-redis; `store.py:62`; `tier2.go:25-27` | Use `.Result()` and fail on `redis.Nil`. Assert every `texts[i]` is non-empty |
| S7 | **An empty-string element passes the length check.** An aligned array of `""` counts as populated, and ragclient accepts it. 2.1's `S_lex` would then score 0 and refuse: a silent fail-closed | `interfaces.md:209` forbids a partial array, not an empty element | ragclient should **not** enforce non-empty, because the contract does not. The live test asserts it (S6), and 2.1 records it |
| S8 | **The misalignment error widens an existing null** | §5 | Use a sentinel error, matched with `errors.Is` in the unit test. Cover **both** directions, `len(texts) < len(chunk_ids)` **and** `>`, plus `chunk_ids` empty with `texts` non-empty. A one-sided check (`<`) passes a one-sided test |
| S9 | **A destructive copy of the cache-test pattern** | `capacity_test.go:14-25` | Read-only, DB 0, `HGet` only (§1). Not silent, but irreversible on a shared machine |
| S10 | **The monkeypatch target.** `server.py:17` resolves `retrieve.retrieve` at call time, so patching `rag.retrieve.retrieve` works. If the import ever becomes `from rag.retrieve import retrieve`, the patch misses: the "unit" test then hits live Redis and Ollama, or skips | `server.py:10, :17` | The fake asserts it was called. The fixture's texts are not derivable from its IDs, so a real retrieval cannot match them |

## Smallest change that satisfies the spec

**Keep:**
- **`server.py`:** one keyword argument, `texts=[c.text for c in chunks]`. Same list, same order,
  no second Redis read.
- **`retrieve.go`:** `Texts`, normalised so that `len == 0` → `nil`, and a sentinel error on
  `0 < len(texts) ≠ len(chunk_ids)`.
- **Unit tests:** one pytest file, and one new Go test file with its own fake. Cases: aligned,
  absent, shorter, longer, and empty IDs.
- **One live test file, `package ragclient_test`:**
  - env-gated, and Fatal (not Skip) when enabled and unreachable;
  - read-only `HGet` on DB 0, with `corpus::` hard-coded, sending `top_k = 0`;
  - covers an unscoped query, and a scoped one where the splice is proven to fire;
  - asserts length ≥ 2 and pairwise-distinct texts, and that the rotated array fails.
- **One Make target**, added to `.PHONY`:
  - prints the pressure level;
  - checks `redis-cli PING` and a single listener on `:50051`;
  - runs with `-count=1 -v`.

  The live check is not a citable measurement, so standing constraint 4's green-only rule does not
  bind it. **Record** the pressure level; do not gate on it. It read `1` (yellow) during this
  analysis, 2026-10-05.

**Cut:**
- Any change or test in `httpapi/` or `reuse/`.
- A `scores` length check.
- `texts` on `AnswerRequest`.
- Logging `texts`.
- An explicit `metadata_mode` in `_to_chunks`.
- A startup probe in `main.go`.
- A new e2e directory.
- Build tags.
- Fixing `rag-server-reuseport` or F-E here.
- A policy for absent texts. That is 2.1's.

## Invalidates

Nothing.
- **`run_id`s:** none exist.
- **Frozen values:** none changed, so no ADR is required.
- **Planning figures:** the Tier-2 μ_hit of ≈ 61 req/s (not citable, taken before texts) moves by
  < 0.01 %. The Tier-1 ≈ 8000 req/s probe never reaches `Retrieve`.

> **Required phases:** impact · implementation, plus design → opus design-review → plan for scope L.
> **Contract not required:** `texts` is §B v0.9 as frozen. No `.proto`, stub, §D or §H surface
> changes. **Experiment not required:** nothing logged or counted changes, and the one timed span
> grows by 0.6–1.6 µs.
> **Precondition, not a phase:** commit item 1.2's work before implementation, so that acceptance 5
> can be checked as `git diff --exit-code -- gateway/internal/httpapi/`.

---

## Corrections this implies for the trail (not applied)

| # | Where | Correction |
| :---: | :--- | :--- |
| 1 | `spec.md` acceptance 3 | Replace "covers a query with `product_id`" with: the splice must be **shown to fire**, absent from the unscoped result and at index 0 of the scoped one (S5) |
| 2 | `spec.md` acceptance 3–4 | Add, before any loop: `len(texts) == len(chunk_ids) ≥ 2`, and every element non-empty. The rotation runs on the unscoped response (S1, S6) |
| 3 | `spec.md` acceptance 2 | "Partial" means **both** directions, plus empty IDs. Assert the sentinel with `errors.Is`, not `err != nil` (S8) |
| 4 | `spec.md` acceptance 5 | Commit 1.2 first. The check becomes `git diff --exit-code -- gateway/internal/httpapi/` |
| 5 | `spec.md` acceptance 6, `plan.md` | The target runs `-count=1 -v`, checks for a single `:50051` listener, and the test Fatals rather than Skips when enabled (S2, S3) |
| 6 | `spec.md` "Out of scope" | Name 2.1's two traps for absent texts: `refusal_cause: SUPPORT` and `support_lex: null` (§7) |
| 7 | `design.md` | The live test goes in `package ragclient_test`: read-only `HGet` on DB 0, no import of `cache` or `catalog` (§1, S9) |
| 8 | At `/done` | `architecture.md` §4 target list; `super-plan.md:118-119, :126, :164` |
