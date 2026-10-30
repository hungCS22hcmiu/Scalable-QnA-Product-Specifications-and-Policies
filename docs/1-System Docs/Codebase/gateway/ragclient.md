# `gateway/internal/ragclient/` — the gRPC client to the Python RAG service

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `client.go`, `retrieve.go`, `answer.go`, `doc.go`, the
generated `ragpb/`, and six test files. Governing contract: `interfaces.md` §B; the schema is
`contracts/rag/v1/rag.proto` (see [`contracts.md`](../contracts.md)).

## 1. Purpose

It is the gateway's only way to reach the Python service. It makes two calls: **`Retrieve`** (find the
chunks for a question, without generating) and **`Answer`** (generate an answer). It serves **C1** (the
cascade needs the question's chunks before it can judge a cached answer) and the miss path.

## 2. Boundaries

- It imports only the generated `ragpb` package.
- It is built **once** at start, never per request. gRPC carries many concurrent calls over one HTTP/2
  connection, so no pool of its own is needed.

## 3. Files

### `client.go`

**`Client`** holds the one gRPC connection. **`New(target)`** dials `host:port` once, without TLS (one machine).
**`Close()`** closes it.

### `retrieve.go`

**`RetrieveResult`** holds `ChunkIDs`, `Scores`, `DatasetEpoch` and `Texts`. `Texts[i]` is the text of
`ChunkIDs[i]`, used by the support gate. **`Texts == nil` with chunks present** means a server that sent no
evidence text (an old server). The gate must then neither score nor refuse the request, and the record must
not look like the gate-off arm: each would blame the gate for a stale server.

**`ErrTextsMisaligned`**: the server sent texts, but not exactly one per chunk. There is no safe way to guess
which one is missing, so the whole response is refused.

**`Retrieve(ctx, query, topK, productID)`**:
1. Calls the `Retrieve` RPC. **Pass `topK = 0`**, so the server uses its own `TOP_K` from `rag/src/rag/config.py`;
   a number here would drift if the chunking changed.
2. `productID`, when set, makes the server **scope** the search: this product's chunks plus every policy chunk
   (`interfaces.md` §B v0.8). It never changes how the reuse decision reads the result.
3. No texts at all is allowed (nil). A different count is `ErrTextsMisaligned`.
4. Only the **length** is checked here. That `Texts[i]` really belongs to `ChunkIDs[i]` rests on the server
   building both from one list, and on the live seam test.

### `answer.go`

**`AnswerResult`** holds `Text`, `SourceChunkIDs`, `ModelUsed` and `DatasetEpoch`.

**`Answer(ctx, query, topK, retrievedChunkIDs, productID)`**:
1. Calls the streaming `Answer` RPC.
2. **`retrievedChunkIDs`**, when not empty, tells the server to generate from **exactly these chunks** instead
   of retrieving again (§B v0.7). The gateway has already retrieved, so this saves a second retrieval and a
   second query embedding. With nil, the server retrieves for itself, scoped by `productID`.
3. Reads the stream until it ends and keeps the chunk marked `Done`. Today the server sends one chunk; the loop
   is defensive.
4. **No terminal chunk is an error**, never an empty answer.

The returned `DatasetEpoch` is the one `Answer` read **first**, before the chunk texts. The write-back guard
compares it with the epoch file (`Invalidation.md` §9).

## 4. Callers and callees

- **Built by** `cmd/gateway/main.go` with `RAG_GRPC_ADDR` (default `localhost:50051`).
- **Called by** `httpapi`: `Retrieve` in the Tier-2 cascade (at the same time as the embedding), and `Answer`
  inside the coalescing closure, after the permit.
- **Calls** `rag.server` (`rag/src/rag/server.py`).

## 5. Tests that pin it

| Test | Guarantees |
| :--- | :--- |
| `TestRetrievePassesProductID`, `TestRetrieveEmptyProductIDIsZeroValue` | `product_id` reaches the request, and empty stays empty |
| `TestAnswerPassesProductID`, `TestAnswerEmptyProductIDIsZeroValue` | the same for `Answer` |
| `TestRetrieveTexts` | texts are passed through, absent texts become nil, a count mismatch is refused |
| `TestSeam` (live, `make seam-check`) | every `texts[i]` equals Redis's text of `chunk_ids[i]`, on `v1` |
| `TestSupportLive` (live, `make support-check`) | the lexical support gate scores live retrieved text as expected |
| `TestSupportSample` (live, manual) | a sample of real generated answers against their evidence; loads the LLM |

The live tests skip unless `RAG_SEAM_ADDR` is set, so `make verify` never needs the live stack. Once it is set,
anything unreachable is a failure, never a skip. Their oracle is Redis's data, not the server's code.

## 6. Silent failures to watch

- **Misaligned texts of the right length.** If the server ever built `texts` from a different list than
  `chunk_ids`, the length check would pass and the support gate would score the wrong evidence. Only
  `make seam-check` catches it; re-run it after any retrieval change.
- **A cancelled `Answer` keeps generating** on the server (finding F-L): the server does not check for the
  cancel, so Ollama's slot stays busy after the gateway released its permit.
- **An unknown `product_id`** is rejected nowhere: a scoped retrieval for it returns nothing, or only policy
  chunks, with no error (found 29 Oct 2026).

## 7. Commit

`29b24a6`.
