"""Item 4.4, done condition 2: the edit order is write, then advance, then post.

An edit that advances the epoch before it writes lets a retrieval between the two read the old
text under the new epoch. One that posts before it advances lets a generation that started after
the purge write back with the old epoch (interfaces.md E, order rule 2). Both are silent, so the
order is pinned here with fakes that append to ONE list. No Redis, no Ollama, no gateway.
"""

import struct

from rag import config, edit
from rag import embedding as embedding_module

EDIT = edit.Edit(
    edit_id="edit-001",
    doc_id="policy-return",
    chunk_id="policy-return#chunk-0",
    change_type="substantive",
    before="Returns are accepted within 30 days.",
    after="Returns are accepted within 14 days.",
)
VECTOR = b"\x01\x02\x03\x04"


class Recorder:
    """Fakes for embed, write, advance and post that all append to one list."""

    def __init__(self):
        self.calls: list[str] = []
        self.written: list[tuple] = []
        self.posted: list[dict] = []

    def embed(self, text: str) -> bytes:
        self.calls.append("embed")
        self.embedded = text
        return VECTOR

    def write(self, chunk_id, text, vector, allowed):
        self.calls.append("write")
        self.written.append((chunk_id, text, vector, allowed))
        return EDIT.before, b"old-vector"

    def advance(self) -> int:
        self.calls.append("advance")
        return 8

    def post(self, event: dict) -> dict:
        self.calls.append("post")
        self.posted.append(event)
        return {"chunk_id": event["chunk_id"], "purged": [], "failed": [], "errors": []}


def test_apply_calls_write_then_advance_then_post():
    r = Recorder()
    applied = edit.apply(EDIT, write=r.write, advance=r.advance, post=r.post, embed=r.embed)

    assert r.calls == ["embed", "write", "advance", "post"]
    assert r.embedded == EDIT.after
    # What was written is the new text with ITS vector, and the chunk may hold before or after.
    assert r.written == [(EDIT.chunk_id, EDIT.after, VECTOR, (EDIT.before, EDIT.after))]
    event = r.posted[0]
    assert (event["chunk_id"], event["doc_id"], event["change_type"], event["new_text"]) == (
        EDIT.chunk_id,
        EDIT.doc_id,
        "substantive",
        EDIT.after,
    )
    assert event["dataset_version"] == config.DATASET_VERSION
    assert applied.epoch == 8
    assert applied.old_text == EDIT.before
    assert applied.old_vector == b"old-vector"


def test_given_vector_skips_embed():
    r = Recorder()
    edit.apply(EDIT, write=r.write, advance=r.advance, post=r.post, embed=r.embed, vector=b"given")

    assert r.calls == ["write", "advance", "post"]
    assert r.written[0][2] == b"given"


def test_restore_uses_the_same_order():
    r = Recorder()
    reply = edit.restore(
        EDIT.chunk_id,
        EDIT.before,
        b"saved-vector",
        "cosmetic",
        write=r.write,
        advance=r.advance,
        post=r.post,
    )

    assert r.calls == ["write", "advance", "post"]
    # A restore may find any text (the saved bytes are the authority): `allowed` is None.
    assert r.written == [(EDIT.chunk_id, EDIT.before, b"saved-vector", None)]
    assert r.posted[0]["new_text"] == EDIT.before
    assert r.posted[0]["change_type"] == "cosmetic"
    assert reply["chunk_id"] == EDIT.chunk_id


class FakeOllama:
    """Stands in for rag.embedding._client and records the input it is sent."""

    def __init__(self):
        self.inputs: list[list[str]] = []

    def post(self, url, json, timeout):
        self.inputs.append(json["input"])
        outer = self

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"embeddings": [[0.5] * config.EMBEDDING_DIM for _ in outer.inputs[-1]]}

        return Response()


def test_embed_document_uses_the_document_prefix(monkeypatch):
    fake = FakeOllama()
    monkeypatch.setattr(embedding_module, "_client", fake)

    out = edit.embed_document("Returns are accepted within 14 days.")

    # Exactly one prefix: ingest's OllamaEmbedding adds it, and edit.py must not add a second.
    assert fake.inputs == [["search_document: Returns are accepted within 14 days."]]
    assert out == struct.pack(f"<{config.EMBEDDING_DIM}f", *([0.5] * config.EMBEDDING_DIM))
    assert len(out) == 4 * config.EMBEDDING_DIM
