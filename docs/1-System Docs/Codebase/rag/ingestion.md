# `rag/src/rag/` — ingestion: JSON files to the Redis corpus index

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `config.py` (47 lines), `chunkid.py` (20), `embedding.py` (70),
`store.py` (105), `ingest.py` (132). Governing contract: `interfaces.md` §C (chunk IDs). The Redis records it writes
are in `Redis-Data Structure.md` §3.

## 1. Purpose

It turns the corpus files (`data/v1/*.json`, 152 products and 12 policies) into chunks, embeds each chunk with
`nomic-embed-text`, and writes them to `idx:corpus`. It runs offline (`make ingest`), never during a request.
Everything retrieval and the reuse rule read starts here, so it serves **C1** and the frozen setup.

## 2. Boundaries

- It owns the corpus index and its schema. The gateway reads that index only for the demo product list
  ([`catalog.md`](../gateway/catalog.md)).
- Embeddings come from Ollama over HTTP; there is **no PyTorch stack** in the process.
- It never writes the cache (`t1:`, `t2:`), and it never writes `data/v1/`.

## 3. Files

### `config.py` — the frozen values

`EMBEDDING_MODEL = nomic-embed-text`, `EMBEDDING_DIM = 768`, `CHUNK_SIZE = 256`, `CHUNK_OVERLAP = 40`, `TOP_K = 5`,
`CORPUS_INDEX_NAME = idx:corpus`, `CORPUS_KEY_PREFIX = corpus:`, `LLM_MODEL = qwen3.5:2b-q4_K_M`,
`LLM_MODEL_ID = qwen3.5-2b`, `LLM_THINK = False`, `LLM_NUM_CTX = 8192`. From the environment: `DATASET_VERSION`
(**default `v1`** since 29 Oct 2026; empty counts as unset), `OLLAMA_BASE_URL`, `REDIS_URL`, `RAG_GRPC_ADDR`
(default `0.0.0.0:50051`). Changing a frozen value mid-study invalidates every comparison.

### `chunkid.py` — the stable chunk ID

`make_chunk_id(doc_id, n)` returns `{doc_id}#chunk-{n}`; it refuses a `doc_id` that already contains `#chunk-`, which
would make the ID ambiguous. `parse_chunk_id` splits it back. These IDs are what the reuse rule, the dependency map
and every log record use, so they must never change for the same text.

### `embedding.py` — `OllamaEmbedding`

A small LlamaIndex `BaseEmbedding` that calls Ollama's `/api/embed` with `httpx` (about 40 lines instead of a new
dependency). **Documents** get the prefix `search_document: ` and **queries** `search_query: `; the Go gateway uses
the same query prefix ([`embed.md`](../gateway/embed.md)). Leaving a prefix out raises no error but degrades every
similarity. The sync path shares one `httpx.Client`; the async methods exist only to satisfy the base class.

### `store.py` — the index schema

**`build_schema()`** defines `idx:corpus`: a hash index on prefix `corpus:` with `id`, `doc_id`, `text`, a **FLAT**
cosine vector of 768 float32 (frozen; never HNSW), `chunk_id`, `ordinal`, `category`, `kind` (`product` or `policy`)
and `dataset_version`. LlamaIndex appends its own separator, so the keys are `corpus::{chunk_id}` (two colons).

**`get_vector_store(overwrite)`** returns a LlamaIndex `RedisVectorStore` and then **waits until the index is
complete** (`wait_until_indexed`, up to 5 s, else `IndexNotReady`). `FT.CREATE` returns at once and fills the index
in the background; a search before that sees part of the corpus with no error.

**`get_redis_client()`** is a plain client for reads that need no vector store.

### `ingest.py` — `make ingest`

1. **Check the epoch path first** (`epoch.require_path()`), so a long ingest cannot fail at the end.
2. **`load_records`**: every `*.json` in `data/{DATASET_VERSION}/`, sorted. Each file's `doc_id` must equal its
   file name, `doc_id`s must be unique, and there must be at least one file.
3. **`records_to_nodes`**, the one split loop (the corpus gate's chunk digest uses it too):
   - `record_kind` reads `product` or `policy` from the `doc_id` prefix and **refuses any other prefix**, because the
     reuse rule reads the kind from it;
   - a product becomes `Product / Category / Specs` lines, a policy becomes its title and text;
   - LlamaIndex's `SentenceSplitter` cuts it into chunks of 256 tokens with 40 overlapping;
   - each chunk gets its stable ID, `ordinal` and `dataset_version`, and **every metadata key is kept out of the
     embedded text** (and out of the LLM text).
4. **`_write_index`** embeds and writes all nodes with `overwrite=True`, replacing the old index.
5. **Advance the epoch** only after every chunk is written (`interfaces.md` §E). Advanced first, a retrieval in
   between would read old chunks under the new epoch.

It reads `data/{DATASET_VERSION}/` (default `v1`).

## 4. Callers and callees

- **Run by** `make ingest` (`python -m rag.ingest`). Check memory pressure first: it loads the embedding model.
- **Used by** `retrieve.py` and `server.py` (the same schema and embedding), `edit.py` (the document prefix), and the
  corpus-gate scripts (`records_to_nodes`, `make_retriever`).

## 5. Tests that pin it

| File | Guarantees |
| :--- | :--- |
| `test_chunkid.py` (5 tests) | the ID scheme, round trip, ordinal 0, ambiguous IDs refused |
| `test_ingest_nodes.py` (5) | stable IDs, ordinals from 0 per document, the version label, metadata kept out of the embedded text, same records → same IDs and texts |
| `test_dataset_version.py` (3) | `DATASET_VERSION` defaults to `v1`; empty counts as unset |
| `test_store_index_ready.py`, `test_store_index_timeout.py` | the store returns only after background indexing finishes, and raises if it never does |
| `test_server_epoch.py::test_ingest_advances_after_writing_the_index` | the epoch advances after the write |

## 6. Silent failures to watch

- **A missing `search_document:` prefix**, or a different embedding model with the same width, degrades every
  retrieval with no error.
- **A `doc_id` without `product-` / `policy-`** is refused here; without that check, every question would fall into
  the SPEC lane.
- **Re-chunking** (a new `CHUNK_SIZE` or overlap) changes every chunk ID and every provenance record: it is a new
  dataset version, not an edit.
- **`FLUSHDB`** anywhere drops `idx:corpus`; re-run `make ingest` (with `DATASET_VERSION=v1`).

## 7. Commit

`29b24a6`.
