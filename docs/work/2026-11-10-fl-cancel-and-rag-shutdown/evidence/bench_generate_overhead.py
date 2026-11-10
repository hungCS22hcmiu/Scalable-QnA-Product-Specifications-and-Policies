"""U2 of design.md section 3, citable: no, not gated: what does the per-call client cost?

generate() now runs one httpx.AsyncClient inside asyncio.run for every call. Before, it posted
through one module-level httpx.Client. This times 100 calls of each against an instant fake Ollama
(rag/tests/conftest.py, delay 0) and prints the two medians and their difference in ms. Old and new
calls alternate, so a slow moment on the machine hits both.

Caveat: the fake closes every connection (`Connection: close`), so the old path also opens a new
local connection on each call. The difference is therefore the cost of the event loop and the
client object, not of the connection. Run from rag/:  python3 ../<this file>
"""

import statistics
import sys
import time
from pathlib import Path

import httpx
from rag.retrieve import RetrievedChunk

from rag import config, generate

ROOT = Path(__file__).resolve().parents[4]
CALLS = 100
WARMUP = 5
CHUNK = RetrievedChunk(
    chunk_id="product-laptops-02#chunk-0",
    score=0.9,
    text="UltraBook Air 13: 13-inch display, 1.2 kg.",
    doc_id="product-laptops-02",
    ordinal=0,
)

# A copy of the old generate(): one client for the process, the same body.
_old_client = httpx.Client(timeout=120.0)


def old_generate(query, chunks):
    resp = _old_client.post(
        f"{config.OLLAMA_BASE_URL}/api/generate",
        json=generate._request_body(query, chunks),
    )
    resp.raise_for_status()
    return resp.json()["response"]


def timed(fn):
    start = time.perf_counter()
    text = fn("How heavy is it?", [CHUNK])
    elapsed = (time.perf_counter() - start) * 1000
    assert text == "the full fake answer"
    return elapsed


def main():
    sys.path.insert(0, str(ROOT / "rag" / "tests"))
    from conftest import FakeOllama

    fake = FakeOllama(delay=0)
    config.OLLAMA_BASE_URL = fake.url
    try:
        for _ in range(WARMUP):
            timed(old_generate)
            timed(generate.generate)
        old, new = [], []
        for _ in range(CALLS):
            old.append(timed(old_generate))
            new.append(timed(generate.generate))
    finally:
        fake.close()
    m_old, m_new = statistics.median(old), statistics.median(new)
    print(f"calls: {CALLS} each, against an instant fake Ollama (citable: no)")
    print(f"old path (one shared httpx.Client), median: {m_old:.3f} ms")
    print(f"new path (AsyncClient + asyncio.run per call), median: {m_new:.3f} ms")
    print(f"difference (new - old): {m_new - m_old:+.3f} ms")
    print(
        "caveat: the fake closes every connection, so the old path also opens a new local"
    )
    print(
        "connection per call; the difference is the event loop and client, not the connection."
    )


if __name__ == "__main__":
    main()
