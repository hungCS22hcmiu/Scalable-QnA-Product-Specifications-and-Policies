"""Shared Redis vector-store schema factory.

ingest.py (writer) and retrieve.py (reader) must build the IDENTICAL schema — RedisVectorStore
has no from_existing_index(); reconnecting means re-declaring the same IndexSchema. A drift
between the two would be a silent-failure class of bug (a silent-failure class), so this lives in
one place.

Vector field algorithm is "flat" — frozen study-wide, never HNSW (interfaces.md §D).
Redis & LlamaIndex require id/doc_id/text/vector as the base fields; the rest are ours.
"""

import redis
from llama_index.vector_stores.redis import RedisVectorStore
from redisvl.schema import IndexSchema

from rag import config


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


def get_vector_store(overwrite: bool) -> RedisVectorStore:
    return RedisVectorStore(
        schema=build_schema(),
        redis_url=config.REDIS_URL,
        overwrite=overwrite,
    )


def get_redis_client() -> redis.Redis:
    """Plain client for reads that do not need the vector store.

    ⚠️ Corpus keys carry a DOUBLE colon -- `corpus::{chunk_id}` -- because LlamaIndex appends its
    own separator to the configured prefix. Building the key with a single colon finds nothing,
    silently, with every lookup simply returning empty. The Go side documents the same quirk in
    cache/tier2.go for the mirror-image reason.
    """
    return redis.from_url(config.REDIS_URL)
