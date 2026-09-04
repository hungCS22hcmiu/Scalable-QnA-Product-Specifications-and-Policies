"""Ollama embedding client for LlamaIndex — httpx only, no new dependency.

Deliberately NOT the llama-index-embeddings-ollama package: adding a new top-level
dependency needs sign-off (.docs/ai/rules.md #9); httpx is already declared and Ollama's
/api/embed is a plain HTTP endpoint, so a ~40-line custom BaseEmbedding subclass is enough.

Nomic prefix convention (silent-degradation risk if skipped, decisions.md ADR-003):
indexed chunk text gets "search_document: ", queries get "search_query: ".
"""

import httpx
from llama_index.core.base.embeddings.base import BaseEmbedding

from rag import config

# One client per process, reused across calls -- see generate.py for the same reasoning.
# Timeout is passed per request rather than set here, because `timeout` is a per-instance
# pydantic field on OllamaEmbedding and a client-level default would silently ignore it.
#
# Only the SYNC path shares a client. The async methods below keep their per-call
# AsyncClient: an httpx.AsyncClient binds to the event loop it is used from, so a
# module-level one is a real hazard -- and nothing in this service calls the async path
# (retrieve.py and ingest.py are both sync). They exist only to satisfy BaseEmbedding.
_client = httpx.Client()


class OllamaEmbedding(BaseEmbedding):
    base_url: str = config.OLLAMA_BASE_URL
    timeout: float = 60.0

    def __init__(self, model_name: str = config.EMBEDDING_MODEL, **kwargs):
        super().__init__(model_name=model_name, **kwargs)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        resp = _client.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model_name, "input": texts},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]

    async def _aembed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model_name, "input": texts},
            )
            resp.raise_for_status()
            return resp.json()["embeddings"]

    # --- documents: "search_document: " prefix ---
    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return self._embed([f"search_document: {t}" for t in texts])

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embeddings([text])[0]

    async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return await self._aembed([f"search_document: {t}" for t in texts])

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return (await self._aget_text_embeddings([text]))[0]

    # --- queries: "search_query: " prefix ---
    def _get_query_embedding(self, query: str) -> list[float]:
        return self._embed([f"search_query: {query}"])[0]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return (await self._aembed([f"search_query: {query}"]))[0]
