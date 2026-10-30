# `rag/src/rag/` — serving: the gRPC server, retrieval and generation

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `server.py` (89 lines), `retrieve.py` (154), `generate.py`
(48), `cli.py` (38). Governing contract: `interfaces.md` §B; the schema is `contracts/rag/v1/rag.proto`.

## 1. Purpose

It answers the gateway's two gRPC calls: **`Retrieve`** (the top 5 chunks for a question, with their text, and no
generation) and **`Answer`** (generate an answer from chunks). It is the only place the LLM is called. It serves
**C1** (the evidence the reuse rule and the support gate read) and the miss path.

## 2. Boundaries

- It talks to Redis (the corpus index) and Ollama (embedding and generation), never to the cache.
- **`think: false` is frozen**; no call can override it.
- Generated code (`pb/`) is never edited by hand; the servicer wraps `retrieve.py` and `generate.py`.

## 3. Files

### `server.py`

**`RagServicer.Retrieve`**:
1. **Read the epoch first**, before any chunk text (order rule 1). This value is stamped on the response.
2. `retrieve.retrieve(query, top_k or TOP_K, product_id)`.
3. Return `chunk_ids`, `scores` and `texts` **built from one list**, so `texts[i]` is the text of `chunk_ids[i]`
   (proved against Redis by `make seam-check`).

**`RagServicer.Answer`**:
1. Read the epoch first.
2. If the gateway sent `retrieved_chunk_ids`, **fetch exactly those** (`fetch_by_ids`) instead of retrieving again;
   else retrieve, scoped by `product_id`.
3. `generate.generate(query, chunks)`.
4. Yield **one** terminal chunk (`done = true`) with the text, the source chunk IDs, the model ID and the epoch.
   Streaming per token was dropped from scope.

**`build_server(addr)`** binds without starting, so tests bind exactly what production binds. **`SO_REUSEPORT` is
off**: grpcio turns it on by default, which let a second `rag.server` bind the same port and split the gateway's
connections between an old and a new server with no error. Off, the second bind fails.

**`serve()`** runs `epoch.check()` **before** binding: with no valid epoch file, every response would be stamped 0
and the gateway would discard every write-back. Then it starts and prints the epoch path and value.

### `retrieve.py`

**`retrieve(query, top_k, product_id)`** returns `(chunks, epoch)`:
1. Reads the epoch first.
2. Opens the vector store (which waits for a complete index) and runs a top-k search with the query embedding.
3. **With a `product_id`**, two steps:
   - **`_drop_other_products`** removes only chunks of a **different** product, **after** ranking. Everything else
     keeps the rank and mix the search produced. An earlier version filtered **before** ranking to "this product or
     any policy"; in a small corpus that filled the top 5 with policy chunks, pushed SPEC questions into the POLICY
     lane, and caused a real cross-product false hit (live, 10 Sep 2026).
   - **`_ensure_own_chunk`**: if the product's own chunk did not rank, fetch it with one small scoped search and
     splice it in, dropping the lowest-ranked survivor to keep 5. It only ever adds **that one** product's chunk, so
     it can only lower the policy share, never raise it.

**`fetch_by_ids(chunk_ids)`** loads chunks the gateway already retrieved, **keeping its rank order** (generation is
order-sensitive, and the namespace comes from the rank-1 document of each kind). It reads the schema's `text`
field. **A missing ID is dropped, never replaced**: an invented chunk would put text in the answer that no
provenance record accounts for.

**`make_retriever(top_k)`** binds a retriever once, for scripts that issue hundreds of queries (the corpus gate). The
search itself is the same as `retrieve()`.

### `generate.py`

**`generate(query, chunks)`** posts to Ollama's `/api/generate` with `LLM_MODEL`, `stream: false`, `think: false` and
`num_ctx: 8192`, and returns `response`. The prompt (`_PROMPT_TEMPLATE`) is: "Answer the question using ONLY the
context below. If the answer is not contained in the context, say you don't know.", then the chunk texts joined by
blank lines, then the question. One `httpx.Client` per process, with a **120 s** timeout.

### `cli.py`

`rag ask "<question>"` prints the top-k chunks with their IDs: retrieval only, no generation. A developer tool from
the early weeks.

## 4. Callers and callees

- **Started by** `make dev` (`python -m rag.server`), by `make seam-check` on port 50052, and by the live check
  scripts on their own ports.
- **Called by** the gateway's `ragclient` ([`ragclient.md`](../gateway/ragclient.md)).
- **Calls** `epoch.read`, `store.get_vector_store`, `OllamaEmbedding`, and Ollama's `/api/generate`.

## 5. Tests that pin it

| File | Guarantees |
| :--- | :--- |
| `test_server_epoch.py` (6 tests) | `Retrieve`, `Answer` (with and without IDs) and `fetch_by_ids` read the epoch **before** any text |
| `test_retrieve_texts.py` (3) | texts aligned with chunk IDs; an empty retrieval sends no texts; the raw text, not metadata |
| `test_retrieve_scoping.py` (5) | other products dropped, policy kept; no change without a `product_id`; no cross-product contamination; no policy flood for a plain spec question (three need Redis with `v1` ingested, and skip without it) |
| `test_server_bind.py` (2) | a second server cannot share the port; a stopped one can rebind |
| `test_epoch.py::test_serve_refuses_before_binding` | no epoch file, no server |

## 6. Silent failures to watch

- **A cancelled `Answer` keeps running** (finding F-L): nothing checks `context.is_active()`, and `generate` blocks on
  `httpx` for up to 120 s. Ollama's one slot stays busy after the gateway released its permit. It gates Phase 7.
- **An unknown `product_id`** is not rejected: the scoped search returns nothing, or only policy chunks.
- **Sorting or de-duplicating in `fetch_by_ids`** would repartition the cache with no error.
- **Two `rag.server`s on one port** were possible before `SO_REUSEPORT` was turned off; `make dev` also refuses to
  start when the port is held.

## 7. Commit

`29b24a6`.
