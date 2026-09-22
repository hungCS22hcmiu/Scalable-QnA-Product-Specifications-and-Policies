"""Generation over retrieved context, via Ollama — httpx only, same calling convention as
embedding.py (no new dependency).

Reads frozen values (LLM_MODEL, LLM_THINK, LLM_NUM_CTX) from config.py only. Never accepts a
per-call override: `think: false` is frozen. The hidden chain-of-thought mode
inflates latency ~5x with no quality benefit, and a request-level override would silently
reintroduce that regression.
"""

import httpx

from rag import config
from rag.retrieve import RetrievedChunk

_TIMEOUT = 120.0

# One client per process, reused across calls. httpx.Client is thread-safe and holds a
# keep-alive connection pool, so the concurrent Answer RPCs server.py dispatches from its
# thread pool share connections instead of opening (and tearing down) one per generation.
# Module-level rather than per-call because the gRPC server is long-lived; for the CLI,
# process exit is sufficient cleanup.
_client = httpx.Client(timeout=_TIMEOUT)

_PROMPT_TEMPLATE = (
    "Answer the question using ONLY the context below. "
    "If the answer is not contained in the context, say you don't know.\n\n"
    "Context:\n{context}\n\nQuestion: {query}\nAnswer:"
)


def _build_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    context = "\n\n".join(c.text for c in chunks)
    return _PROMPT_TEMPLATE.format(context=context, query=query)


def generate(query: str, chunks: list[RetrievedChunk]) -> str:
    resp = _client.post(
        f"{config.OLLAMA_BASE_URL}/api/generate",
        json={
            "model": config.LLM_MODEL,
            "prompt": _build_prompt(query, chunks),
            "stream": False,
            "think": config.LLM_THINK,
            "options": {"num_ctx": config.LLM_NUM_CTX},
        },
    )
    resp.raise_for_status()
    return resp.json()["response"]
