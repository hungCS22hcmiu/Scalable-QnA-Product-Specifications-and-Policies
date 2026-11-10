"""Generation over retrieved context, via Ollama — httpx only, same calling convention as
embedding.py (no new dependency).

Reads frozen values (LLM_MODEL, LLM_THINK, LLM_NUM_CTX) from config.py only. Never accepts a
per-call override: `think: false` is frozen. The hidden chain-of-thought mode
inflates latency ~5x with no quality benefit, and a request-level override would silently
reintroduce that regression.

F-L: the Ollama request can be stopped. server.py hands this module a threading.Event through
stop_when(); gRPC sets it when the RPC ends, and generate() then cancels its HTTP request. That
closes the connection, and Ollama stops generating. Before this, a generation whose client had left
ran on, and the next request queued behind it inside Ollama, out of the gateway's sight.
"""

import asyncio
import contextlib
import contextvars
import threading
from collections.abc import Iterator

import httpx

from rag import config
from rag.retrieve import RetrievedChunk

_TIMEOUT = 120.0

# How often a running request looks at the stop event. A finished answer is never delayed by it:
# asyncio.wait returns the moment the request is done.
_STOP_POLL_S = 0.05

# The stop event of the Answer RPC running in THIS thread, or None. A context variable, not an
# argument, so generate(query, chunks) keeps its signature and scripts can still call it as before.
# stop_when() resets it, so a worker thread that is reused never keeps an old event.
_stop: contextvars.ContextVar[threading.Event | None] = contextvars.ContextVar(
    "rag_generate_stop", default=None
)


class Cancelled(Exception):
    """The RPC ended before the answer was ready. There is no answer, not even a partial one."""


@contextlib.contextmanager
def stop_when(stop: threading.Event) -> Iterator[None]:
    """For the block, generate() stops (raises Cancelled) once `stop` is set."""
    token = _stop.set(stop)
    try:
        yield
    finally:
        _stop.reset(token)


_PROMPT_TEMPLATE = (
    "Answer the question using ONLY the context below. "
    "If the answer is not contained in the context, say you don't know.\n\n"
    "Context:\n{context}\n\nQuestion: {query}\nAnswer:"
)


def _build_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    context = "\n\n".join(c.text for c in chunks)
    return _PROMPT_TEMPLATE.format(context=context, query=query)


def _request_body(query: str, chunks: list[RetrievedChunk]) -> dict:
    return {
        "model": config.LLM_MODEL,
        "prompt": _build_prompt(query, chunks),
        "stream": False,
        "think": config.LLM_THINK,
        "options": {"num_ctx": config.LLM_NUM_CTX},
    }


async def _post_until_stop(body: dict, stop: threading.Event | None) -> str:
    # One client per call, not one per process. Cancelling the task that runs the POST closes this
    # call's TCP connection, and Ollama then stops generating (P2 and U1 in the F-L task's
    # design.md). The price is a new event loop and a new local connection for each generation.
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        task = asyncio.create_task(client.post(f"{config.OLLAMA_BASE_URL}/api/generate", json=body))
        while True:
            done, _ = await asyncio.wait({task}, timeout=_STOP_POLL_S)
            if done:
                break
            if stop is not None and stop.is_set():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                raise Cancelled
        resp = task.result()
    resp.raise_for_status()
    return resp.json()["response"]


def generate(query: str, chunks: list[RetrievedChunk]) -> str:
    stop = _stop.get()
    if stop is not None and stop.is_set():
        raise Cancelled
    return asyncio.run(_post_until_stop(_request_body(query, chunks), stop))
