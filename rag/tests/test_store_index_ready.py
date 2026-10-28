"""The corpus index is fully built before the RAG read path searches it.

`FT.CREATE` returns at once and RediSearch fills the index in the background. A search sent before
that finishes sees part of the corpus and raises no error: the same query returns a different top-k
(docs/work/2026-10-28-promoted-t1-keys/design.md section 4). `store.get_vector_store` must therefore
not return until the index is complete.

This test builds a THROWAWAY index (`idx:test-ready`) over the same `corpus:` prefix. It never calls
FLUSHDB, never touches `idx:corpus`, and drops its own index with FT.DROPINDEX without DD, so no
document is deleted. It needs a running Redis with the dev-v0 corpus ingested, and is skipped,
loudly, otherwise.
"""

import pytest
import redis

from rag import config, store

THROWAWAY_INDEX = "idx:test-ready"
LIVE_INDEX = "idx:corpus"


def _redis_reachable() -> bool:
    try:
        store.get_redis_client().ping()
        return True
    except Exception:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_reachable(), reason="Redis not reachable -- start it and `make ingest` first"
)


def _drop_if_exists(client: redis.Redis, name: str) -> None:
    """FT.DROPINDEX without DD: the index goes, the documents stay."""
    try:
        client.ft(name).dropindex(delete_documents=False)
    except redis.ResponseError as exc:
        if "unknown index name" not in str(exc).lower():
            raise


def _corpus_key_count(client: redis.Redis) -> int:
    # Corpus keys carry a DOUBLE colon: `corpus::{chunk_id}` (see store.get_redis_client).
    return sum(1 for _ in client.scan_iter(match="corpus::*", count=1000))


@requires_redis
def test_get_vector_store_returns_only_after_background_indexing_finishes(monkeypatch):
    monkeypatch.setattr(config, "CORPUS_INDEX_NAME", THROWAWAY_INDEX)
    # Refuse to run against the live index: this test drops the index it names.
    assert config.CORPUS_INDEX_NAME != LIVE_INDEX, (
        "refusing to run: the patched name is the live index"
    )

    client = store.get_redis_client()
    try:
        _drop_if_exists(client, THROWAWAY_INDEX)
        expected = _corpus_key_count(client)
        assert expected > 0, "no corpus::* keys -- run `make ingest` first"

        store.get_vector_store(overwrite=False)
        # Read at once, with no sleep: a half-built index shows here, not a few milliseconds later.
        info = client.ft(THROWAWAY_INDEX).info()

        indexing = float(info["indexing"])
        num_docs = int(float(info["num_docs"]))
        assert indexing == 0, (
            f"get_vector_store returned while the index was still building: {info}"
        )
        assert num_docs == expected, (
            f"get_vector_store returned with {num_docs} of {expected} documents indexed"
        )
    finally:
        _drop_if_exists(client, THROWAWAY_INDEX)
