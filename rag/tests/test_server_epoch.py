"""Item 4.2: the epoch is read BEFORE the chunk texts, on every path that stamps it.

The failure is silent. Read after the texts, a retrieval that straddled an edit would carry the NEW
epoch over the OLD text, pass the gateway's write-back guard and cache stale text with no trace
(interfaces.md E, order rule 1). So each test records the order of two events, "epoch" (epoch.read)
and "texts" (the chunk-text read), and requires the epoch first. The patched retrieval returns a
decoy epoch (999), so a response that took the retrieval's value instead of the file's would show.

Ingest has the same kind of rule: the epoch advances only AFTER every chunk is written. Everything
here is offline: no Redis, no Ollama.
(docs/work/2026-10-28-epoch-guard/design.md section 3)
"""

from pathlib import Path

import pytest

from rag import epoch, generate, ingest, retrieve, server, store
from rag.pb.rag.v1 import rag_pb2
from rag.retrieve import RetrievedChunk

FILE_EPOCH = 41
DECOY_EPOCH = 999

_CHUNK = RetrievedChunk(
    chunk_id="product-laptops-02#chunk-0",
    score=0.9,
    text="UltraBook Air 13: 13-inch display, 1.2 kg.",
    doc_id="product-laptops-02",
    ordinal=0,
)


@pytest.fixture
def order(tmp_path, monkeypatch):
    """The epoch file holds 41, and the list records "epoch" each time epoch.read runs."""
    path = tmp_path / "dataset-epoch"
    path.write_text(f"{FILE_EPOCH}\n")
    monkeypatch.setenv(epoch.ENV, str(path))

    events: list[str] = []
    real_read = epoch.read

    def recording_read():
        events.append("epoch")
        return real_read()

    monkeypatch.setattr(epoch, "read", recording_read)
    return events


def _patch_retrieval(monkeypatch, events):
    """retrieve.retrieve and retrieve.fetch_by_ids return a decoy epoch and record "texts"."""

    def fake_retrieve(query, top_k, product_id):
        events.append("texts")
        return [_CHUNK], DECOY_EPOCH

    def fake_fetch(chunk_ids):
        events.append("texts")
        return [_CHUNK], DECOY_EPOCH

    monkeypatch.setattr(retrieve, "retrieve", fake_retrieve)
    monkeypatch.setattr(retrieve, "fetch_by_ids", fake_fetch)
    monkeypatch.setattr(generate, "generate", lambda query, chunks: "an answer")


def test_retrieve_stamps_the_epoch_read_first(order, monkeypatch):
    _patch_retrieval(monkeypatch, order)

    resp = server.RagServicer().Retrieve(
        rag_pb2.RetrieveRequest(query="q", product_id="product-laptops-02"), context=None
    )

    assert resp.dataset_epoch == FILE_EPOCH
    assert order[:2] == ["epoch", "texts"]


def test_answer_with_ids_stamps_the_epoch_read_first(order, monkeypatch):
    _patch_retrieval(monkeypatch, order)

    [chunk] = list(
        server.RagServicer().Answer(
            rag_pb2.AnswerRequest(query="q", retrieved_chunk_ids=[_CHUNK.chunk_id]), context=None
        )
    )

    assert chunk.dataset_epoch == FILE_EPOCH
    assert chunk.text == "an answer"
    assert order[:2] == ["epoch", "texts"]


def test_answer_without_ids_stamps_the_epoch_read_first(order, monkeypatch):
    _patch_retrieval(monkeypatch, order)

    [chunk] = list(
        server.RagServicer().Answer(
            rag_pb2.AnswerRequest(query="q", product_id="product-laptops-02"), context=None
        )
    )

    assert chunk.dataset_epoch == FILE_EPOCH
    assert order[:2] == ["epoch", "texts"]


def test_fetch_by_ids_reads_the_epoch_before_the_texts(order, monkeypatch):
    class FakeRedis:
        def hmget(self, key, fields):
            order.append("texts")
            return [b"some text", b"product-laptops-02", b"0"]

    monkeypatch.setattr(store, "get_redis_client", lambda: FakeRedis())

    chunks, ep = retrieve.fetch_by_ids(["product-laptops-02#chunk-0"])

    assert [c.text for c in chunks] == ["some text"]
    assert ep == FILE_EPOCH
    assert order[:2] == ["epoch", "texts"]


def test_retrieve_reads_the_epoch_before_the_index(order, monkeypatch):
    class Reached(Exception):
        pass

    def fake_vector_store(overwrite):
        order.append("index")
        raise Reached

    monkeypatch.setattr(store, "get_vector_store", fake_vector_store)

    with pytest.raises(Reached):
        retrieve.retrieve("q")

    assert order == ["epoch", "index"]


def test_ingest_advances_after_writing_the_index(monkeypatch):
    events: list[str] = []

    def require_path():
        events.append("require_path")
        return Path("dataset-epoch")

    def load_records(data_dir):
        events.append("load_records")
        return []

    def write_index(nodes):
        events.append("write_index")

    def advance():
        events.append("advance")
        return 2

    monkeypatch.setattr(epoch, "require_path", require_path)
    monkeypatch.setattr(ingest, "load_records", load_records)
    monkeypatch.setattr(ingest, "records_to_nodes", lambda records, version: [])
    monkeypatch.setattr(ingest, "_write_index", write_index)
    monkeypatch.setattr(epoch, "advance", advance)

    ingest.main()

    # The path is checked first so a long ingest cannot fail at the end for want of it, and the
    # epoch advances only once every chunk is written.
    assert events == ["require_path", "load_records", "write_index", "advance"]
