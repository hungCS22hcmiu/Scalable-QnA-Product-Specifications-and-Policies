"""Shared Redis vector-store schema factory.

ingest.py (writer) and retrieve.py (reader) must build the IDENTICAL schema — RedisVectorStore
has no from_existing_index(); reconnecting means re-declaring the same IndexSchema. A drift
between the two would be a silent-failure class of bug (a silent-failure class), so this lives in
one place.

Vector field algorithm is "flat" — frozen study-wide, never HNSW (interfaces.md §D).
Redis & LlamaIndex require id/doc_id/text/vector as the base fields; the rest are ours.
"""

import time

import redis
from llama_index.vector_stores.redis import RedisVectorStore
from redisvl.schema import IndexSchema

from rag import config


class IndexNotReady(RuntimeError):
    """The corpus index did not finish building within the time limit."""


def build_schema() -> IndexSchema:
    return IndexSchema.from_dict(
        {
            "index": {
                "name": config.CORPUS_INDEX_NAME,
                "prefix": config.CORPUS_KEY_PREFIX,
                "storage_type": "hash",
            },
            "fields": [
                {"name": "id", "type": "tag"},
                {"name": "doc_id", "type": "tag"},
                {"name": "text", "type": "text"},
                {
                    "name": "vector",
                    "type": "vector",
                    "attrs": {
                        "algorithm": "flat",  # frozen — never HNSW
                        "dims": config.EMBEDDING_DIM,
                        "distance_metric": "cosine",
                        "datatype": "float32",
                    },
                },
                {"name": "chunk_id", "type": "tag"},
                {"name": "ordinal", "type": "numeric"},
                {"name": "category", "type": "tag"},
                {"name": "kind", "type": "tag"},  # "product" | "policy"
                {"name": "dataset_version", "type": "tag"},
            ],
        }
    )


def wait_until_indexed(
    client: redis.Redis, index_name: str, timeout_s: float = 5.0, poll_s: float = 0.005
) -> None:
    """Return only when `index_name` is fully built. Raise IndexNotReady if it never is.

    Polls FT.INFO until `indexing` is 0 and `percent_indexed` is at least 1, both read as numbers.
    It never returns early: when `timeout_s` passes first it raises, naming the index and the last
    values it saw, so a search never runs on a partial index.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        info = client.ft(index_name).info()
        indexing = float(info["indexing"])
        percent_indexed = float(info["percent_indexed"])
        if indexing == 0 and percent_indexed >= 1:
            return
        if time.monotonic() >= deadline:
            raise IndexNotReady(
                f"index {index_name} not fully built after {timeout_s}s: "
                f"indexing={indexing}, percent_indexed={percent_indexed}"
            )
        time.sleep(poll_s)


def get_vector_store(overwrite: bool) -> RedisVectorStore:
    vector_store = RedisVectorStore(
        schema=build_schema(),
        redis_url=config.REDIS_URL,
        overwrite=overwrite,
    )
    # ⚠️ RedisVectorStore creates a missing index with FT.CREATE, which returns at once, and
    # RediSearch then fills the index in the background. A KNN search sent before that finishes
    # sees PART of the corpus and raises no error, so the same query returns a different top-k
    # (design.md section 4 of docs/work/2026-10-28-promoted-t1-keys). Wait here, so every caller
    # searches a complete index. The sync client is used because `vector_store.client` is the
    # async one. Cost: one FT.INFO per Python retrieval, off the Go hit path.
    wait_until_indexed(get_redis_client(), config.CORPUS_INDEX_NAME)
    return vector_store


def get_redis_client() -> redis.Redis:
    """Plain client for reads that do not need the vector store.

    ⚠️ Corpus keys carry a DOUBLE colon -- `corpus::{chunk_id}` -- because LlamaIndex appends its
    own separator to the configured prefix. Building the key with a single colon finds nothing,
    silently, with every lookup simply returning empty. The Go side documents the same quirk in
    cache/tier2.go for the mirror-image reason.
    """
    return redis.from_url(config.REDIS_URL)
