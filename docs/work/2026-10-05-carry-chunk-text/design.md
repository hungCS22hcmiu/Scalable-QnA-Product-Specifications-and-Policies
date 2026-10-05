# Design — carry-chunk-text

**Revision 3**, after `impact.md` (its §8 hazards S1–S10 and corrections table) and `review.md`
(S1–S5, N1–N6, all applied; its "Resolutions" table maps each to a section here). It reads with
`spec.md`.

## 1. Shape

Two production edits, about fifteen lines in total, and three layers of test. The production change
is small on purpose. **What the task is really for is the check:** one that can tell a correctly
aligned `texts` from one shifted by one place, using an oracle that neither side's code supplies,
run by a target that cannot pass without running it (`review.md` S1, S2).

```
 Redis  corpus::<id>  { text, doc_id, ordinal, vector, _node_content(text removed), ... }
   │  FT.SEARCH (LlamaIndex, return_fields ⊇ text)                ← the ORACLE reads the same hash
   ▼
 retrieve.retrieve() ── _to_chunks: RetrievedChunk{chunk_id, score, text, ...}   (one list)
   │
   ▼
 server.RagServicer.Retrieve
   chunk_ids = [c.chunk_id ...]   scores = [c.score ...]   texts = [c.text ...]   ← EDIT 1
   │  protobuf, repeated fields keep order
   ▼
 ragclient.Retrieve
   len(texts) == 0              → Texts = nil
   len(texts) == len(chunk_ids) → Texts = texts                                    ← EDIT 2
   otherwise                    → ErrTextsMisaligned ("no partial population")
   │
   ▼
 httpapi (unchanged: retrieved.Texts has no reader until 2.1)
```

## 2. The production edits

### Edit 1 — `rag/src/rag/server.py`, `Retrieve`

```python
return rag_pb2.RetrieveResponse(
    chunk_ids=[c.chunk_id for c in chunks],
    scores=[c.score for c in chunks],
    dataset_epoch=epoch,
    texts=[c.text for c in chunks],
)
```

**Alignment holds by construction** (`review.md`, "Checked and found sound"; N6). All three arrays
come from one `chunks` list, and `_to_chunks` runs once, on the final list (`retrieve.py:128-132`).
Before that point the pipeline only filters and reorders **node objects**, and each node carries its
own id and text together:
- `_drop_other_products` filters nodes, so a text never leaves its id.
- `_ensure_own_chunk`'s splice **is** a second query (`retrieve.py:116`). Its node is built by the
  same `_extract_node_and_score` with the same `return_fields`, then prepended as one object:
  `(own_nodes + nodes)[:top_k]` (`:119`).

**`c.text` is the schema field the contract names** (`interfaces.md:212`). U1 is settled by reading
(`review.md` U1):
- `NodeWithScore.get_content` defaults to `MetadataMode.NONE`;
- `TextNode` then returns `self.text`;
- the Redis store sets `self.text` from the hash's `text` field (`…/redis/base.py:785`), which is in
  the default `return_fields` (`:177-181`).

`_node_content` is written with its text removed (`base.py:344-345`; a live key holds `text: ''`),
so there is no second copy that could drift. The gate's evidence (`Retrieve`) and the text
generation is grounded on (`fetch_by_ids`, `retrieve.py:47-49`) are the same field. 3c still
verifies it byte for byte.

### Edit 2 — `gateway/internal/ragclient/retrieve.go`

```go
// ErrTextsMisaligned: the service sent texts that cannot be aligned with chunk_ids
// (interfaces.md §B: "there is no partial population").
var ErrTextsMisaligned = errors.New("ragclient: texts not aligned with chunk_ids")

type RetrieveResult struct {
	ChunkIDs     []string
	Scores       []float32
	DatasetEpoch uint64
	// Texts[i] is the text of ChunkIDs[i] (interfaces.md §B), or nil when the service sent none.
	// Alignment cannot be checked here -- only length can -- so it rests on server.py building both
	// arrays from one list, and on the seam test that compares them against Redis.
	//
	// Texts == nil with len(ChunkIDs) > 0 means the service returned chunks WITHOUT evidence text,
	// e.g. a server that predates texts. A reader (the support gate) must not score such a request,
	// must not refuse it as SUPPORT, and must not log it as the gate-off arm (support_lex: null):
	// each would misattribute a stale server to the gate. Key on len(ChunkIDs) > 0, because an
	// empty retrieval is nil too.
	Texts []string
}
```

`Retrieve` reads `resp.GetTexts()` and enforces the one part of the invariant a client *can* see.

| Wire shape | Result | Why |
| :--- | :--- | :--- |
| `len(texts) == 0` | `Texts = nil`, no error | `interfaces.md:209`: *"or the field is absent entirely"*. Covers `chunk_ids` empty too |
| `len(texts) == len(chunk_ids)` | `Texts = texts` | The contract case |
| anything else, either direction | `fmt.Errorf("%w: %d texts for %d chunk_ids", ErrTextsMisaligned, …)` | `interfaces.md:210`. A partial array cannot be aligned, and there is no safe way to guess which element is missing. The sentinel lets the unit test assert **which** error (`errors.Is`) and lets the gateway's log line name the cause (`impact.md` §5, S8) |

On the error, `httpapi` takes its existing path (`handler.go:265-268`): it logs `retrieve failed,
degrading to MISS`, leaves `retrieved` nil, and 1.2 already tests that exit. **No new outcome, no
§H change.** It adds one more cause behind the existing null `retrieved_chunk_ids` (`impact.md` §5),
and the in-tree server cannot reach it.

**What the client does not check: empty elements.** An aligned array of `""` passes. The contract
forbids a partial array, not an empty element, so `ragclient` does not invent a rule the contract
lacks. The live test asserts non-empty (§3c), and 2.1 inherits the note (`impact.md` S7).

### D1 — absent `texts`: **decided D1-a** (contract-literal), on the reviewer's condition

An absent `texts` is `nil` with no error. `review.md` approved it and corrected the argument:

1. **D1-b would need the contract phase.** The v0.9 note gives *"an absent `texts` is today's
   behaviour exactly"* as the reason §B's change is additive (`interfaces.md:44`). Rejecting absence
   at the only client changes what that frozen sentence means, and the spec declares no contract
   change.
2. **D1-b is less loud than it looks before 1.3.** A retrieve error leaves `retrieved == nil`. On a
   banded request F-E then records `entered_band: true`, `source_overlap: 0` (`cascade.go:106-112`).
   So a stale server would show up in §H as **provenance** refusals. D1-b moves the misattribution;
   it does not remove it.
3. **A stale server is a property of a process, not of a request.** It is closed by a run that owns
   its server (§3d here; `rag-server-reuseport` for `make dev` and `make measure`), and by 2.1
   counting `Texts == nil && len(ChunkIDs) > 0` as a distinct condition. The gateway's own connection
   is the only vantage point that certifies the gateway's instance.

**The condition (`review.md` S3):** the hand-off must live where 2.1's author will read it. It is in
Edit 2's doc comment above, and at `/done` the same sentence goes into super-plan's 2.1 row. The
reviewer adds, as PLAUSIBLE, that a gRPC client reconnecting on a `SO_REUSEPORT` port can move
between instances, so a run could be *partly* without texts. That strengthens the case for closing
`rag-server-reuseport` before 2.1's live reproduction and before Phase 7 (`approvals.md`, Open).

## 3. The tests

### 3a. Python unit — `rag/tests/test_retrieve_texts.py` (new)

Two tests, no Redis and no Ollama. U3 is settled: `import rag.server` succeeds with both pointed at
a closed port, and nothing connects at import time (`review.md` U3).

**Servicer alignment:**
- Monkeypatch `rag.retrieve.retrieve`. `server.py:17` calls it through the module, so patching the
  module attribute takes effect. Return 3–5 `RetrievedChunk` with **distinct, non-prefix-sharing**
  texts not derivable from their IDs, in a **non-sorted** id order, plus an epoch.
- The fake records that it was called, and the test asserts that. If the patch ever misses
  (`server.py` switching to `from rag.retrieve import retrieve`), a real retrieval cannot pass by
  accident (`impact.md` S10).
- Call `RagServicer().Retrieve(RetrieveRequest(query=…, product_id=…), context=None)`.
- Assert `len(resp.texts) == len(resp.chunk_ids) == n` and `resp.texts[i] == by_id[resp.chunk_ids[i]]`
  for every `i`, where `by_id` is built from the **fixture**, not from the response.
- Also: an empty retrieval yields `chunk_ids == []` and `texts == []`.

**`_to_chunks` returns the raw text** (`review.md` S5, the one silent part of F4c):
- Build a `TextNode` with non-empty metadata (`chunk_id`, `doc_id`, `ordinal`, plus a `title`),
  wrap it in `NodeWithScore`, and pass it through `_to_chunks`.
- Assert `chunk.text == raw_text` exactly.
- This pins `MetadataMode.NONE` semantics offline. If a LlamaIndex upgrade changes the
  `get_content` default to `ALL`, every `texts[i]` would carry metadata tokens, and 2.1's `S_lex`
  would count them as evidence. That is a silent false admit, and this catches it inside
  `make verify`. No production change.

### 3b. Go unit — `gateway/internal/ragclient/retrieve_texts_test.go` (new)

**`retrieve_test.go` stays byte-identical.** Tests are immutable, and giving its
`fakeRagServiceClient` a response field would edit it (`impact.md` §7). The new file has its own
fake, which returns a configured `*RetrieveResponse`. One table-driven test, one row per wire shape:

| Row | Wire `chunk_ids` / `texts` | Asserts |
| :--- | :--- | :--- |
| aligned | 3 / 3, in **non-sorted, non-palindromic** order | `Texts` equals the wire array element for element; `err == nil` |
| absent | 3 / 0 | `Texts == nil`; `err == nil` |
| empty retrieval | 0 / 0 | `Texts == nil`, `ChunkIDs` empty; `err == nil` |
| short | 3 / 2 | `errors.Is(err, ErrTextsMisaligned)`; result nil |
| long | 3 / 4 | `errors.Is(err, ErrTextsMisaligned)`; result nil |
| texts without ids | 0 / 2 | `errors.Is(err, ErrTextsMisaligned)`; result nil |

The aligned fixture's order is what lets a sort or a reverse inside `ragclient` fail it
(`review.md` S4). The existing `fakeRagServiceClient` returns `&RetrieveResponse{}`, the
empty-retrieval row, so `TestRetrievePassesProductID` and `TestRetrieveEmptyProductIDIsZeroValue`
stay green unchanged.

### 3c. End to end, Python → Go, live — `gateway/internal/ragclient/seam_live_test.go` (new)

**The point of the task.** The real `ragclient.New(addr)` dials a Python server started from the
working tree (§3d), and each `texts[i]` is compared with `HGET corpus::<chunk_ids[i]> text` read
**directly from Redis** by go-redis. The oracle shares data with the server, not code. A wrong DB,
instance or key format returns `redis.Nil`, which fails (`review.md`, "Checked and found sound").

**Package and boundary** (`impact.md` §1): `package ragclient_test`, so the test sees only the
exported API. go-redis is a test-only import, with `cache/capacity_test.go` as precedent. It never
imports `cache` or `catalog`. It sends `top_k = 0`, as the gateway does.

**Gating:**
- The test reads `RAG_SEAM_ADDR`. Unset: `t.Skip("set RAG_SEAM_ADDR -- run make seam-check")`. It
  **compiles** in every `go test ./...`, so a broken build cannot hide. That a skip still exits 0 is
  closed in the target, not here (§3d, `review.md` S1).
- Set: every failure to reach the server or Redis is `t.Fatal`, **never** `t.Skip`.
- Redis address from `REDIS_URL` (default `redis://localhost:6379/0`), the same variable the Python
  server reads (`config.py:23`), so both read one Redis. Access is **read-only**, `HGet` only, on
  DB 0, with `corpus::` hard-coded (the key `retrieve.py:47` builds; U6 settled: all 44 keys'
  suffixes equal their `chunk_id`). It never uses `FLUSHDB` and never writes.
- The oracle uses `HGet(...).Result()` and fails on `redis.Nil`. `.Val()` returns `""` for a missing
  key, and `"" == ""` would pass if the server also sent an empty text (`impact.md` S6).
- **Context deadline 90 s** per call. The first `Retrieve` loads `nomic-embed-text`, and the Python
  embed timeout is 60 s (`embedding.py:29`). A deadline error says *"cold embedding load or seam
  fault"* so the cause is not misread (`review.md` N4).

**Structure:** one `TestSeam` with subtests `L1`, `L2`, `L3`, `shift`. §3d's output check looks
for exactly these names.

**Cases** (dev-v0; a correctness check, not a result, so `dev-v0` is allowed):

| # | Query | `product_id` | Why |
| :---: | :--- | :--- | :--- |
| L1 | `"what is the power rating of this item exactly right now"` | — | The unscoped path. **Issued twice**, and the two `chunk_ids` must be identical (U7): "absent from L1" in L2 must not rest on an untested assumption that the query embedding is bit-identical across calls |
| L2 | same | `product-laptops-02` | **The splice path.** `product-laptops-02#chunk-0` contains no power or watt term while 11 of 44 chunks do, so it is *expected* not to rank naturally. That is reasoned, not pinned by an existing test (`review.md` N1; `test_retrieve_scoping.py:78, :84` assert only the kitchen chunk). The test asserts the splice fired: the chunk is **absent** from L1 and at **index 0** of L2 (`retrieve.py:119`). L2 may be a single chunk |
| L3 | a policy question, e.g. `"can I return an opened item"` | — | Policy chunks, a different kind |

For each case, a shared checker `checkAligned(ids, texts, oracle) error`, applied **before** any
loop can pass vacuously (`impact.md` S1):
1. `len(texts) == len(ids) ≥ 1`. An absent `texts` **fails** here: the server under test must send
   it.
2. Every `texts[i]` is non-empty.
3. `texts[i] == oracle(ids[i])` for every `i`, byte for byte.

**The `shift` subtest (acceptance 4)** runs on L1, the unscoped response (5 chunks on dev-v0):
- Preconditions, each a `t.Fatal`: `len ≥ 2`, and the texts are pairwise distinct. Otherwise a
  rotation could match by accident. No two of the 44 dev-v0 chunks share a text (`impact.md` S1).
- `checkAligned(ids, rotate(texts, 1), oracle)` must return an error. If it returns nil, the
  subtest fails with *"the checker cannot see a shift"*. With ≥ 2 distinct texts a rotation
  mismatches at every index, so an order-insensitive checker is caught too.

### 3d. `make seam-check` — the target owns its server

**Why the target owns the server** (`review.md` S2): a check against whatever listens on `:50051`
detects an ambiguous port, not a stale process. A `make dev` started before the last edit to
`server.py` is one listener running old code. A server started by the target from the working tree
certifies the code in the tree, restarts itself for every mutation run, and leaves the dev stack
alone.

The recipe, in one shell under `set -euo pipefail`:
1. Print `kern.memorystatus_vm_pressure_level`. Not a measurement, so yellow does not invalidate
   it; the level is recorded, not gated on.
2. `redis-cli PING`, else fail.
3. Informational only: the number of unique PIDs listening on `:50051`
   (`lsof -t -iTCP:50051 -sTCP:LISTEN | sort -u | wc -l`), for `rag-server-reuseport` (N3).
4. Fail if `127.0.0.1:50052` (`SEAM_PORT`) already has a listener.
5. Start `cd rag && RAG_GRPC_ADDR=127.0.0.1:$(SEAM_PORT) REDIS_URL=… $(PY) -m rag.server &`, with a
   `trap` that kills it on `EXIT INT TERM` (the pattern `Makefile:122-126` already uses).
6. Wait for the listener, polling, with a 30 s timeout. Fail if the process exits first.
7. `RAG_SEAM_ADDR=127.0.0.1:$(SEAM_PORT) REDIS_URL=… go test -count=1 -v -run '^TestSeam$'
   ./internal/ragclient/ 2>&1 | tee $(SEAM_LOG)`.
8. **Output check** (`review.md` S1). Fail unless `$(SEAM_LOG)` contains `--- PASS: TestSeam` and
   `--- PASS: TestSeam/L1`, `/L2`, `/L3` and `/shift`, and contains **none** of `--- SKIP`,
   `no tests to run` or `(cached)`.

Why each guard exists:
- `-count=1`: Go caches a result keyed on env vars and files, not on network state, so a second run
  would print `(cached)` without dialing (`impact.md` S2).
- The output check: `go test -run` with no matching test prints `PASS` and exits 0, and so does a
  skip. Confirmed by the reviewer on 2026-10-05, when `TestSeam` did not exist yet.

`SEAM_LOG` defaults to a temp file. For the evidence run it is set to
`docs/work/2026-10-05-carry-chunk-text/evidence/seam-check.txt`. The target goes in `.PHONY` and in
`make help`. It needs Redis and the **embedding** model, not the LLM.

**What `make verify` does not cover** (`review.md` S5, restating `impact.md` S4): with
`RAG_SEAM_ADDR` unset the live test skips. Of F4c's three parts, (a) the `get_content` default is
now caught offline by 3a's second test, and (b) the legacy branch cannot reach `texts` (it raises
`KeyError` in `_to_chunks` first, which is loud). Only (c), `text` dropping out of `return_fields`,
needs the live stack. It yields `""` and 3c's step 2 catches it, but **only when 3c runs**. So
`make seam-check` is re-run by hand after any LlamaIndex upgrade or retrieval change.

## 4. Mutations — each test, and each guard, must be able to fail

Run by hand once, results in `evidence/mutations.txt`. A mutation that no test catches is a gap in
the design, not a pass: stop and report it.

**Code mutations:**

| # | Mutation | Must be caught by |
| :---: | :--- | :--- |
| M1 | `server.py` omits `texts` | 3a servicer (length 0 ≠ n); 3c step 1 |
| M2 | `server.py` sends `texts` reversed, or rotated by one | 3a servicer; 3c step 3 |
| M3 | `retrieve.py:_to_chunks` uses `n.get_content(MetadataMode.ALL)` (moved from `server.py`, where it cannot be written; `review.md` S4) | 3a `_to_chunks` test (offline); 3c step 3 |
| M3-eq | the same with `MetadataMode.LLM` or `EMBED` | **Equivalent on the live corpus**: ingest excludes every metadata key from both (`ingest.py:88-89`), so 3c is right to pass them. 3a's `_to_chunks` test, whose node has no exclusions, catches them anyway. Recorded, not a gap |
| M4 | `ragclient` never reads `GetTexts()` | 3b aligned |
| M5 | `ragclient` drops the length check | 3b short, long, texts-without-ids |
| M6 | `checkAligned` skips step 3 (always passes) | 3c `shift` |
| M7 | `ragclient` checks only `len(texts) < len(chunk_ids)` | 3b long, texts-without-ids |
| M8 | The oracle uses `.Val()`, and the server sends `""` for one chunk | 3c step 2 and the `redis.Nil` handling |
| M9 | `ragclient` sorts or reverses `Texts` | 3b aligned (non-sorted, non-palindromic fixture) |

**First run (2026-10-05) found two gaps; both fixed, second run 0 gaps** (`evidence/mutations.txt`):
- **M9a/M9b MISSED by 3b.** The test handed `tc.texts` to the fake, and `GetTexts()` returns that
  same slice, so a client reordering `Texts` in place rewrote the expected values too: the test
  compared a slice with itself. The non-sorted fixture could not help. Fix: the fake receives
  `slices.Clone` of ids and texts. 3c caught M9a all along (every subtest fails), so the gap was
  offline-only.
- **M5 "caught" by the compiler, not the test.** Deleting the `case` left `fmt` unused. Fix: the
  mutation disables the case (`case false && …`); it is now caught by the short, long and
  texts-without-ids rows.

**Target mutations** (`review.md` S4: the guards are one-line edits away from a vacuous pass):

| # | Mutation | Must happen |
| :---: | :--- | :--- |
| T1 | Run `make seam-check` twice in a row | The second run still shows the subtests executing; no `(cached)` |
| T2 | Run the test with `RAG_SEAM_ADDR` pointed at a closed port | Non-zero exit, not a skip |
| T3 | Rename `TestSeam` | `make seam-check` exits non-zero (step 8) |
| T4 | Drop `RAG_SEAM_ADDR` from step 7 | `make seam-check` exits non-zero on `--- SKIP` (step 8) |

## 5. Failure modes — silent first

| # | Failure | Silent? | Closed by |
| :---: | :--- | :--- | :--- |
| F1 | The live check runs against a server whose code is not the working tree's (`SO_REUSEPORT`, `server.py:52`; or a `make dev` started before the last edit) | **yes** | The target starts its own server from the tree on a private port (§3d steps 4–6) |
| F2 | The shift test passes because adjacent texts are equal | **yes** | Distinctness precondition |
| F3 | The oracle is derived from the code under test | **yes** | The oracle is a raw Redis `HGET`, never `fetch_by_ids` or a Python helper |
| F4 | `RAG_SEAM_ADDR` set but the stack is down, and the test skips | **yes** | `t.Fatal` when set (T2) |
| F4b | A cached `go test` pass is read as a live pass | **yes** | `-count=1`, and step 8 rejects `(cached)` (T1) |
| F4c | `make verify` passes after a LlamaIndex change breaks the text mapping | (a) **yes**, now closed; (c) **yes**, between seam checks | (a) 3a's `_to_chunks` test; (b) cannot reach `texts`; (c) 3c step 2, when `make seam-check` runs |
| F5 | Absent `texts` after 2.1 is logged as a SUPPORT refusal, or as `support_lex: null` on the gate-on arm | **yes**, later | D1's condition: the `Texts` doc comment, and super-plan's 2.1 row at `/done` |
| F6 | Invalid UTF-8 in a chunk's text | no, before it can reach `Retrieve` | redis-py's strict encoder makes `make ingest` fail on a lone surrogate (`review.md` N5, PLAUSIBLE). Handed to 3.1 as "the builder must not emit it" |
| F7 | Response size on the hit path | no | 1.3–2.7 KB per response on dev-v0, ≤ ~5.7 KB on v1; serialisation only, no extra Redis read (`impact.md` §2) |
| F8 | `make seam-check` passes without running the test: no match for `-run`, or a skip | **yes** | Step 8's output check (T3, T4) |
| F9 | A gRPC reconnect on a shared port moves a run between instances, so it is partly without texts | **yes**, later (PLAUSIBLE) | Out of scope. `rag-server-reuseport` should close before 2.1's live reproduction and Phase 7 |

## 6. What later items may and may not change

- **2.1** reads `RetrieveResult.Texts`. It **must** treat `Texts == nil && len(ChunkIDs) > 0` as its
  own condition: not scored, not a SUPPORT refusal, not logged as gate-off. It should count it,
  since the gateway's connection is the only vantage point on the gateway's instance. Whether that
  needs its own §H value is 2.1's and 2.3's contract question. 2.1 may not reorder or filter `Texts`
  apart from `ChunkIDs`.
- **1.3** removes the unfiltered cascade phase. The file sets are disjoint (`impact.md` §7), so
  there is no ordering conflict. This task adds **no** `httpapi` test for "misaligned texts → MISS":
  it would pin F-E's signature, which 1.3 removes, and it would be an `ask_test.go` assertion.
- **3.1** (PQA build script) must not emit text that redis-py's strict encoder rejects (F6).
- `httpapi/harness_test.go`'s aligned-`texts` fake stays as it is. This task adds no harness
  behaviour.

## 7. Unknowns

| # | Unknown | Status |
| :---: | :--- | :--- |
| U1 | `c.text` equals the Redis hash `text` field byte for byte | **Settled by reading** (§2). 3c still verifies it live |
| U2 | L2 fires the splice on the current dev-v0 index | **Open.** 3c asserts it. If it does not fire, pick another pair; do not drop the assertion |
| U3 | `rag.server` imports with Redis and Ollama unreachable | **Settled** (`review.md` U3) |
| U4 | Listeners on `:50051` | **Moot** under §3d; reported as an informational line |
| U5 | Invalid UTF-8 in Amazon-PQA text | **Handed to 3.1** (F6) |
| U6 | The corpus is in DB 0, and key suffix = `chunk_id` | **Settled** (`review.md` U6: all 44 keys) |
| U7 | The Ollama query embedding is bit-identical across two calls, so L1 and L2 see the same unscoped ranking | **Open.** 3c issues L1 twice and compares |
