"""Item 1.4: RetrieveResponse.texts, POSITIONALLY ALIGNED with chunk_ids (interfaces.md B v0.9).

texts[i] must be the text of chunk_ids[i]. A shifted array scores a cached answer against the WRONG
chunk's text and raises no error anywhere, so these tests compare against a fixture keyed by chunk
id, never against the response itself. Both run offline: no Redis, no Ollama.

The live half -- Python -> Go against the real index, with Redis as the oracle -- is
gateway/internal/ragclient/seam_live_test.go, run by `make seam-check`.
(docs/work/2026-10-05-carry-chunk-text/design.md 3a)
"""

from llama_index.core.schema import NodeWithScore, TextNode

from rag import retrieve, server
from rag.pb.rag.v1 import rag_pb2
from rag.retrieve import RetrievedChunk, _to_chunks

# Rank order deliberately NOT sorted by id, and texts that share no prefix and cannot be derived
# from their ids -- so a real retrieval that slipped past the monkeypatch cannot match by accident.
_FIXTURE = [
    RetrievedChunk(
        chunk_id="product-laptops-02#chunk-0",
        score=0.91,
        text="UltraBook Air 13: 13-inch display, 1.2 kg.",
        doc_id="product-laptops-02",
        ordinal=0,
    ),
    RetrievedChunk(
        chunk_id="policy-returns#chunk-2",
        score=0.84,
        text="Opened items may be returned within 15 days.",
        doc_id="policy-returns",
        ordinal=2,
    ),
    RetrievedChunk(
        chunk_id="product-kitchen-05#chunk-0",
        score=0.77,
        text="Air Fryer XL draws 1800W at full heat.",
        doc_id="product-kitchen-05",
        ordinal=0,
    ),
    RetrievedChunk(
        chunk_id="policy-warranty#chunk-0",
        score=0.70,
        text="Warranty claims need the original receipt.",
        doc_id="policy-warranty",
        ordinal=0,
    ),
]


def _patch_retrieve(monkeypatch, chunks):
    """server.py calls retrieve.retrieve through the module (server.py:17), so patching the module
    attribute takes effect. Returns the call log, so a test can prove the patch was hit."""
    calls = []

    def fake_retrieve(query, top_k, product_id):
        calls.append((query, top_k, product_id))
        return list(chunks), 7

    monkeypatch.setattr(retrieve, "retrieve", fake_retrieve)
    return calls


def test_retrieve_sends_texts_aligned_with_chunk_ids(monkeypatch):
    calls = _patch_retrieve(monkeypatch, _FIXTURE)

    resp = server.RagServicer().Retrieve(
        rag_pb2.RetrieveRequest(query="what is the power rating", product_id="product-laptops-02"),
        context=None,
    )

    assert calls, "the monkeypatch was not hit -- server.py no longer calls retrieve.retrieve"
    by_id = {c.chunk_id: c.text for c in _FIXTURE}
    assert len(resp.texts) == len(resp.chunk_ids) == len(_FIXTURE)
    for i, chunk_id in enumerate(resp.chunk_ids):
        assert resp.texts[i] == by_id[chunk_id], (
            f"texts[{i}] is not the text of chunk_ids[{i}] ({chunk_id})"
        )


def test_empty_retrieval_sends_no_texts(monkeypatch):
    _patch_retrieve(monkeypatch, [])

    resp = server.RagServicer().Retrieve(rag_pb2.RetrieveRequest(query="q"), context=None)

    assert list(resp.chunk_ids) == []
    assert list(resp.texts) == []


def test_to_chunks_returns_the_raw_text_not_metadata():
    """texts must be the schema `text` field and nothing else (interfaces.md B). _to_chunks relies
    on get_content()'s default, MetadataMode.NONE. If a LlamaIndex upgrade changed that default,
    every text would carry metadata tokens (doc_id, title, ...), which the support gate's lexical
    arm would count as evidence: a silent false admit. The node here excludes no metadata keys, so
    any mode other than NONE changes the text."""
    raw = "Battery: 52 Wh. Weight: 1.2 kg."
    node = TextNode(
        text=raw,
        metadata={
            "chunk_id": "product-laptops-02#chunk-0",
            "doc_id": "product-laptops-02",
            "ordinal": 0,
            "title": "UltraBook Air 13",
            "category": "laptops",
        },
    )

    [chunk] = _to_chunks([NodeWithScore(node=node, score=0.5)])

    assert chunk.text == raw
