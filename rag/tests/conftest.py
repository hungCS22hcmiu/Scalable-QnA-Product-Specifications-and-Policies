"""Shared test fixtures: a fake Ollama that can answer slowly, or never, and that notices when its
client closes the connection.

The F-L tests (test_server_cancel.py, test_server_shutdown.py) need to see one thing Ollama does and
a mock cannot show: it stops generating when the HTTP client that asked for the answer goes away.
So the fake is a raw-socket HTTP/1.1 server. It records each request body, waits `delay` seconds
(forever when `delay` is None), and during that wait it watches the socket. If the client closes
first, it records the time in `.closed_at`; if the delay ends first, it sends one JSON answer.
That makes "the Ollama request was closed within 0.5 s of the cancel" a plain assertion.
No Ollama, no Redis, no model. (docs/work/2026-11-10-fl-cancel-and-rag-shutdown/design.md section 3)
"""

import json
import socket
import threading
import time

import pytest


class FakeOllama:
    """A local HTTP server that plays Ollama's /api/generate for the tests.

    .url       base URL, for config.OLLAMA_BASE_URL or the OLLAMA_BASE_URL variable
    .bodies    the parsed JSON body of each request, in arrival order
    .closed_at time.monotonic() of each connection the client closed before the answer was sent
    .answered  how many requests got their answer
    """

    def __init__(self, delay: float | None, text: str = "the full fake answer"):
        self.delay = delay
        self.text = text
        self.bodies: list[dict] = []
        self.closed_at: list[float] = []
        self.answered = 0
        self._conns: list[socket.socket] = []
        self._lock = threading.Lock()
        self._closing = False
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(16)
        # A timeout so the accept loop notices close(): closing a listening socket from another
        # thread does not reliably wake a blocked accept().
        self._listener.settimeout(0.1)
        self.url = f"http://127.0.0.1:{self._listener.getsockname()[1]}"
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self) -> None:
        while not self._closing:
            try:
                conn, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with self._lock:
                self._conns.append(conn)
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _read_request(self, conn: socket.socket) -> dict | None:
        """The parsed JSON body, or None when the client left before sending a whole request."""
        buf = b""
        while b"\r\n\r\n" not in buf:
            data = conn.recv(65536)
            if not data:
                return None
            buf += data
        head, _, rest = buf.partition(b"\r\n\r\n")
        length = 0
        for line in head.split(b"\r\n")[1:]:
            name, _, value = line.partition(b":")
            if name.strip().lower() == b"content-length":
                length = int(value.strip())
        while len(rest) < length:
            data = conn.recv(65536)
            if not data:
                return None
            rest += data
        return json.loads(rest[:length])

    def _serve(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(5.0)
            body = self._read_request(conn)
            if body is None:
                return
            self.bodies.append(body)
            deadline = None if self.delay is None else time.monotonic() + self.delay
            conn.settimeout(0.02)
            while deadline is None or time.monotonic() < deadline:
                try:
                    data = conn.recv(4096)
                except TimeoutError:
                    continue
                except OSError:  # a reset is also a client that left
                    data = b""
                if not data:  # the client closed its end: this is what Ollama sees on a cancel
                    if not self._closing:
                        self.closed_at.append(time.monotonic())
                    return
            payload = json.dumps({"model": "fake", "response": self.text, "done": True}).encode()
            conn.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                b"Content-Length: " + str(len(payload)).encode() + b"\r\n"
                b"Connection: close\r\n\r\n" + payload
            )
            self.answered += 1
        except OSError:
            pass  # the client left while the answer was being sent: nothing to record
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def close(self) -> None:
        """Shut the listener and every accepted connection, so no gRPC worker stays blocked on
        this fake after its test."""
        self._closing = True
        try:
            self._listener.close()
        except OSError:
            pass
        with self._lock:
            conns = list(self._conns)
        for conn in conns:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass


@pytest.fixture
def fake_ollama():
    """A factory: fake_ollama(delay, text="the full fake answer") -> FakeOllama. Every server it
    made is closed at teardown."""
    made: list[FakeOllama] = []

    def factory(delay: float | None, text: str = "the full fake answer") -> FakeOllama:
        fake = FakeOllama(delay, text)
        made.append(fake)
        return fake

    yield factory
    for fake in made:
        fake.close()
