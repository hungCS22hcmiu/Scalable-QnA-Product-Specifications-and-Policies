"""rag-server-reuseport: one rag.server per address, and a restart still works.

grpcio enables SO_REUSEPORT by default, so a second rag.server could bind the address a stale one
already held, and the kernel split the gateway's connections between them with no error anywhere:
six stale instances were found that way on 2026-10-03. These tests bind exactly what serve()
binds (build_server), on loopback, with no Redis and no model.
(docs/work/2026-10-05-rag-server-reuseport/spec.md)
"""

import pytest

from rag.server import build_server


def test_second_server_cannot_share_the_port():
    first, port = build_server("127.0.0.1:0")
    first.start()
    second = None
    try:
        with pytest.raises(RuntimeError):
            second, _ = build_server(f"127.0.0.1:{port}")
    finally:
        if second is not None:
            second.stop(None)
        first.stop(None).wait()


def test_a_stopped_server_can_rebind_its_port():
    """The guard against over-fixing: refusing a SHARED port must not refuse a FREED one, or every
    restart right after a kill would fail."""
    first, port = build_server("127.0.0.1:0")
    first.start()
    first.stop(None).wait()

    again, again_port = build_server(f"127.0.0.1:{port}")
    try:
        assert again_port == port
    finally:
        again.stop(None)
