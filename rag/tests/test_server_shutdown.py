"""rag.server stops cleanly on SIGTERM and SIGINT: the Answer calls in flight finish, new RPCs are
refused, and the process exits with code 0.

Before this, serve() had no signal handler. `make dev` stops the server with SIGTERM, which ended
it at once, so an Answer in flight failed while the gateway was still draining. These tests start
the REAL serve() as a subprocess (serve_with_fakes.py, no Redis) against a fake Ollama
(conftest.FakeOllama), because a handler that is missing from the served path shows only when a
signal kills an Answer in flight.

  DC 3  a signal finishes the Answer in flight, a new RPC is UNAVAILABLE, the process exits 0; the
        same for SIGINT; a SIGINT that was ignored at start (as `make dev` starts the server) stays
        ignored, and SIGTERM still shuts the server down;
  DC 4  a generation that never finishes is cancelled when the grace ends (its Ollama request is
        closed, the cancel path of test_server_cancel.py) and the process exits within grace + 2 s;
        a second signal ends the process at once.

(docs/work/2026-11-10-fl-cancel-and-rag-shutdown/design.md section 1 and 3)
"""

import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import grpc
import pytest

from rag.pb.rag.v1 import rag_pb2, rag_pb2_grpc

_HERE = Path(__file__).resolve().parent
_FULL_TEXT = "the full fake answer"
_REFUSING = "refusing new RPCs"


def _wait_for(predicate, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _request() -> rag_pb2.AnswerRequest:
    return rag_pb2.AnswerRequest(
        query="How heavy is it?", retrieved_chunk_ids=["product-laptops-02#chunk-0"]
    )


class Served:
    """A rag.server subprocess, its output file, and the channels opened to it."""

    def __init__(self, proc: subprocess.Popen, port: int, log: Path):
        self.proc = proc
        self.port = port
        self.log = log
        self._channels: list[grpc.Channel] = []

    def stub(self) -> rag_pb2_grpc.RagServiceStub:
        """A stub on a NEW channel."""
        channel = grpc.insecure_channel(f"127.0.0.1:{self.port}")
        self._channels.append(channel)
        return rag_pb2_grpc.RagServiceStub(channel)

    def output(self) -> str:
        return self.log.read_text()

    def wait_for_output(self, text: str, timeout: float) -> bool:
        return _wait_for(lambda: text in self.output(), timeout)

    def close(self) -> None:
        for channel in self._channels:
            channel.close()
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()


@pytest.fixture
def serve(tmp_path):
    """start(fake, grace, ignore_sigint=False) -> Served. Any process still alive is killed at
    teardown."""
    started: list[Served] = []

    def start(fake, grace: float, ignore_sigint: bool = False) -> Served:
        epoch_file = tmp_path / "dataset-epoch"
        epoch_file.write_text("41\n")
        port = _free_port()
        env = {
            **os.environ,
            "RAG_GRPC_ADDR": f"127.0.0.1:{port}",
            "OLLAMA_BASE_URL": fake.url,
            "DATASET_EPOCH_FILE": str(epoch_file),
            "RAG_SHUTDOWN_GRACE_S": str(grace),
        }
        log = tmp_path / f"rag-server-{len(started)}.log"
        # `make dev` starts rag.server in the background, where SIGINT is ignored: the same here.
        preexec = (lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)) if ignore_sigint else None
        with log.open("w") as out:
            proc = subprocess.Popen(
                [sys.executable, str(_HERE / "serve_with_fakes.py")],
                env=env,
                stdout=out,
                stderr=subprocess.STDOUT,
                preexec_fn=preexec,
            )
        served = Served(proc, port, log)
        started.append(served)

        def accepting() -> bool:
            if proc.poll() is not None:
                pytest.fail(
                    f"rag.server exited at start with {proc.returncode}:\n{served.output()}"
                )
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            except OSError:
                return False
            return True

        assert _wait_for(accepting, 10.0), f"rag.server did not accept in 10 s:\n{served.output()}"
        return served

    yield start
    for served in started:
        served.close()


def _answer_in_thread(served: Served, result: dict, timeout: float = 30.0) -> threading.Thread:
    """Starts an Answer on its own channel. result gets "chunks", or "error" when the RPC fails."""
    stub = served.stub()

    def run():
        try:
            result["chunks"] = list(stub.Answer(_request(), timeout=timeout))
        except grpc.RpcError as e:
            result["error"] = e

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT], ids=["SIGTERM", "SIGINT"])
def test_signal_finishes_the_answer_in_flight(serve, fake_ollama, sig):
    """DC 3a-c. A signal during an Answer: the Answer returns its full text, a new RPC is refused
    with UNAVAILABLE, and the process exits 0 before the grace (10 s) ends."""
    fake = fake_ollama(1.5)
    served = serve(fake, grace=10)
    result: dict = {}
    thread = _answer_in_thread(served, result)
    assert _wait_for(lambda: len(fake.bodies) == 1, 5.0), "Answer never reached the fake Ollama"

    t0 = time.monotonic()
    served.proc.send_signal(sig)
    assert served.wait_for_output(_REFUSING, 3.0), f"no shutdown line:\n{served.output()}"
    time.sleep(0.2)  # the handler prints, then calls server.stop(grace)

    with pytest.raises(grpc.RpcError) as refused:  # (b)
        list(served.stub().Answer(_request(), timeout=2))
    assert refused.value.code() == grpc.StatusCode.UNAVAILABLE

    thread.join(timeout=10)
    assert "error" not in result, result.get("error")  # (a)
    assert [c.text for c in result["chunks"]] == [_FULL_TEXT]

    assert served.proc.wait(timeout=10) == 0  # (c)
    assert time.monotonic() - t0 < 10


def test_sigint_ignored_at_start_stays_ignored(serve, fake_ollama):
    """DC 3d. Started with SIGINT ignored, as `make dev` starts it, SIGINT changes nothing and
    SIGTERM still shuts the server down."""
    fake = fake_ollama(0)
    served = serve(fake, grace=10, ignore_sigint=True)

    served.proc.send_signal(signal.SIGINT)
    time.sleep(1.0)

    assert served.proc.poll() is None, (
        f"SIGINT stopped a server that ignored it:\n{served.output()}"
    )
    chunks = list(served.stub().Answer(_request(), timeout=5))
    assert [c.text for c in chunks] == [_FULL_TEXT]

    served.proc.send_signal(signal.SIGTERM)
    assert served.proc.wait(timeout=5) == 0


def test_grace_end_stops_a_stuck_generation(serve, fake_ollama):
    """DC 4. The fake never answers. When the grace (2 s) ends, gRPC cancels the RPC, the Ollama
    request is closed, and the process has exited within grace + 2 s."""
    fake = fake_ollama(None)
    served = serve(fake, grace=2)
    result: dict = {}
    _answer_in_thread(served, result)
    assert _wait_for(lambda: len(fake.bodies) == 1, 5.0), "Answer never reached the fake Ollama"

    t0 = time.monotonic()
    served.proc.send_signal(signal.SIGTERM)

    assert _wait_for(lambda: fake.closed_at, 3.0), "the Ollama request was not closed by t0 + 3 s"
    assert _wait_for(lambda: served.proc.poll() is not None, max(0.0, t0 + 4 - time.monotonic())), (
        f"rag.server had not exited by t0 + 4 s:\n{served.output()}"
    )


def test_second_signal_exits_at_once(serve, fake_ollama):
    """DC 4. With a long grace (60 s) and a generation that never ends, a second SIGTERM ends the
    process at once, by the default action."""
    fake = fake_ollama(None)
    served = serve(fake, grace=60)
    result: dict = {}
    _answer_in_thread(served, result)
    assert _wait_for(lambda: len(fake.bodies) == 1, 5.0), "Answer never reached the fake Ollama"

    served.proc.send_signal(signal.SIGTERM)
    assert served.wait_for_output(_REFUSING, 3.0), f"no shutdown line:\n{served.output()}"
    time.sleep(0.5)
    assert served.proc.poll() is None  # the grace is 60 s: still waiting
    served.proc.send_signal(signal.SIGTERM)

    assert served.proc.wait(timeout=2) == -signal.SIGTERM
