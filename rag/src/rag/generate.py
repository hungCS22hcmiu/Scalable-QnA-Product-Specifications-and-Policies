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
import hashlib
import re
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


# The served prompt has two parts: a system text and a user template (item 6.0a, ADR-029).
# It asks for a short, direct answer that never mentions the context, and for the sentinel
# NO_ANSWER when the facts do not hold the answer. The old one-part template is saved verbatim
# in experiments/judge/reference-prompt-v1.txt: the reference writer (ADR-023) keeps using it.
_SYSTEM_PROMPT = "\n".join(
    [
        "You answer shoppers' questions about one product and the store's policies.",
        "Use only the facts given with the question.",
        "",
        "Rules:",
        "- Answer in one or two short sentences.",
        "- Start with the answer itself.",
        "- Never mention the facts, the context, a document, or where the information comes from.",
        "- Do not greet the shopper. Do not repeat the product's name.",
        "- Use the exact numbers and terms from the facts.",
        "- If the facts do not answer the question, reply with exactly: NO_ANSWER",
        "",
        "Example",
        "Facts: Unopened items can be returned within 30 days of delivery for a full refund.",
        "Question: I never opened the box. Can I still send it back?",
        "Answer: Yes. Unopened items can be returned within 30 days of delivery for a full refund.",
    ]
)

_PROMPT_TEMPLATE = "Facts:\n{context}\n\nQuestion: {query}\nAnswer:"

# What a customer sees instead of the sentinel. The gateway never caches an answer that carries it.
FALLBACK_ANSWER = (
    "Sorry, I don't have that detail for this product. "
    "Please check the product page or contact our support team."
)

_NO_ANSWER_RE = re.compile(r"\bno[ _]?answer\b", re.IGNORECASE)


def finalize(text: str) -> tuple[str, bool]:
    """Fail-closed: if the output holds the sentinel anywhere, return the fixed sentence and True.

    The sentinel must never reach a customer, so a match anywhere counts, in any case.
    """
    if _NO_ANSWER_RE.search(text):
        return FALLBACK_ANSWER, True
    return text, False


def prompt_sha256() -> str:
    """sha256 of the system text, a NUL byte, then the user template: both parts are pinned."""
    return hashlib.sha256((_SYSTEM_PROMPT + "\x00" + _PROMPT_TEMPLATE).encode("utf-8")).hexdigest()


def _build_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    context = "\n\n".join(c.text for c in chunks)
    return _PROMPT_TEMPLATE.format(context=context, query=query)


def _request_body(query: str, chunks: list[RetrievedChunk]) -> dict:
    return {
        "model": config.LLM_MODEL,
        "system": _SYSTEM_PROMPT,
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
