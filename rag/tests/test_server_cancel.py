"""F-L: a cancelled Answer must stop the Ollama request, and the request itself must not change.

Before the fix, server.py never looked at the RPC's end and generate.py blocked on one httpx.post,
so Ollama kept generating an answer nobody would read, and the next admitted request queued inside
Ollama, out of the gateway's sight. The failure is silent: the next request just looks slow.

So these tests run the real build_server against a fake Ollama (conftest.FakeOllama) that answers
slowly and records when its client closes the connection. No Ollama, no Redis, no model.

  DC 1  the cancel reaches the wire, a stopped Answer sends no chunk, and a cancel never reaches
        another request;
  DC 2  the body sent to Ollama and the prompt are what they were before the change. The expected
        body is written out as literals, never read from config, so a drifting frozen value shows.

(docs/work/2026-11-10-fl-cancel-and-rag-shutdown/design.md section 1 and 3)
"""

import hashlib
import threading
import time

import grpc
import pytest

from rag import config, epoch, generate, retrieve, server
from rag.pb.rag.v1 import rag_pb2, rag_pb2_grpc
from rag.retrieve import RetrievedChunk

_CHUNK = RetrievedChunk(
    chunk_id="product-laptops-02#chunk-0",
    score=0.9,
    text="UltraBook Air 13: 13-inch display, 1.2 kg.",
    doc_id="product-laptops-02",
    ordinal=0,
)

_FULL_TEXT = "the full fake answer"

# Moved at item 6.0a (ADR-029; the human approved it in that task's design.md section 4).
# The served prompt now has a system text and a new user template. The two pins it replaces
# (3e224f45..., c4f5162b...) belong to the reference writer's own file,
# experiments/judge/reference-prompt-v1.txt, and are pinned there.
_SERVED_PROMPT_SHA256 = "7a6acf979a041a7683e67a8453de1316636410998d2c225ef12f7b2179fe3929"
_PROMPT_SHA256 = "42acfc09a6bb9486e42f4f442cbcfe9cf4b0d8c0298ae6197c23f76dc8d2176d"


class FakeContext:
    """What Answer needs from a gRPC context: add_callback. `registered` is what it returns, the
    way grpc does: False means the RPC had already ended and the callback will never run."""

    def __init__(self, registered: bool):
        self.registered = registered
        self.callbacks = []

    def add_callback(self, callback):
        self.callbacks.append(callback)
        return self.registered

    def fire(self):
        for callback in self.callbacks:
            callback()


def _wait_for(predicate, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


@pytest.fixture
def stack(tmp_path, monkeypatch, fake_ollama):
    """An epoch file holding 41, retrieval patched to one fixed chunk, and a start(delay) that
    makes a fake Ollama and points config.OLLAMA_BASE_URL at it."""
    path = tmp_path / "dataset-epoch"
    path.write_text("41\n")
    monkeypatch.setenv(epoch.ENV, str(path))
    monkeypatch.setattr(retrieve, "fetch_by_ids", lambda *a, **k: ([_CHUNK], 41))
    monkeypatch.setattr(retrieve, "retrieve", lambda *a, **k: ([_CHUNK], 41))

    def start(delay, text=_FULL_TEXT):
        fake = fake_ollama(delay, text)
        monkeypatch.setattr(config, "OLLAMA_BASE_URL", fake.url)
        return fake

    return start


@pytest.fixture
def served():
    """start() -> a RagService stub on a real build_server. Stopped at teardown."""
    started = []

    def start():
        srv, port = server.build_server("127.0.0.1:0")
        srv.start()
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        started.append((srv, channel))
        return rag_pb2_grpc.RagServiceStub(channel)

    yield start
    for srv, channel in started:
        channel.close()
        srv.stop(None)


def _request() -> rag_pb2.AnswerRequest:
    return rag_pb2.AnswerRequest(query="How heavy is it?", retrieved_chunk_ids=[_CHUNK.chunk_id])


def test_cancel_closes_the_ollama_request(stack, served):
    """DC 1a. The client cancels Answer at +0.2 s; the fake must see its connection closed within
    0.5 s. Before the fix the fake's request ran to its end (5 s)."""
    fake = stack(5)
    stub = served()

    call = stub.Answer(_request())
    assert _wait_for(lambda: len(fake.bodies) == 1, 2.0), "Answer never reached the fake Ollama"
    time.sleep(0.2)
    call.cancel()
    cancelled_at = time.monotonic()
    _wait_for(lambda: fake.closed_at, 1.0)

    assert fake.closed_at and fake.closed_at[0] - cancelled_at <= 0.5, (
        "F-L: the Ollama request was not closed within 0.5 s of the cancel"
    )


def test_stopped_answer_sends_no_chunk(stack):
    """DC 1b. An Answer whose RPC ends during generation yields nothing, and its Ollama request is
    closed. Called directly, with a context whose callback the test fires."""
    fake = stack(5)
    ctx = FakeContext(registered=True)

    def fire_after_body():
        _wait_for(lambda: fake.bodies, 2.0)
        time.sleep(0.2)
        ctx.fire()

    firer = threading.Thread(target=fire_after_body, daemon=True)
    firer.start()
    chunks = list(server.RagServicer().Answer(_request(), ctx))
    firer.join(timeout=5)

    assert chunks == []
    assert _wait_for(lambda: fake.closed_at, 0.5)


def test_stop_before_generation_makes_no_ollama_call(stack):
    """DC 1b. add_callback returns False: the RPC had already ended. Nothing is generated and no
    request reaches Ollama."""
    fake = stack(0)

    chunks = list(server.RagServicer().Answer(_request(), FakeContext(registered=False)))

    assert chunks == []
    assert fake.bodies == []


def test_a_cancel_does_not_reach_another_request(stack, served):
    """DC 1c. Two Answers at once on a real server. The first is cancelled; the second, whose
    client stays, returns the full text, and so does a third sent after the cancel (it may run on
    the worker thread the first one used, so a stop left in that thread would cut it)."""
    fake = stack(1.0)
    stub = served()

    first = stub.Answer(_request())
    second = stub.Answer(_request())
    second_chunks = []
    reader = threading.Thread(target=lambda: second_chunks.extend(second), daemon=True)
    reader.start()

    assert _wait_for(lambda: len(fake.bodies) == 2, 2.0), "both Answers must reach the fake"
    time.sleep(0.2)
    first.cancel()
    reader.join(timeout=5)

    assert [c.text for c in second_chunks] == [_FULL_TEXT]

    third = list(stub.Answer(_request()))
    assert [c.text for c in third] == [_FULL_TEXT]


def test_request_body_is_unchanged(stack):
    """DC 2. The body sent to Ollama is exactly today's. Literals, not config, so a changed frozen
    value or a field added by the new client shows."""
    fake = stack(0)

    text = generate.generate("How heavy is it?", [_CHUNK])

    assert text == _FULL_TEXT
    assert fake.bodies == [
        {
            "model": "qwen3.5:2b-q4_K_M",
            "system": generate._SYSTEM_PROMPT,
            "prompt": generate._build_prompt("How heavy is it?", [_CHUNK]),
            "stream": False,
            "think": False,
            "options": {"num_ctx": 8192},
        }
    ]


def test_prompt_is_unchanged():
    """DC 2. run_manifest.py writes generate.prompt_sha256() (system text and template together)
    as the manifest's generator.prompt_sha256, so it may change only with an ADR."""
    assert generate.prompt_sha256() == _SERVED_PROMPT_SHA256
    prompt = generate._build_prompt("How heavy is it?", [_CHUNK])
    assert hashlib.sha256(prompt.encode()).hexdigest() == _PROMPT_SHA256
