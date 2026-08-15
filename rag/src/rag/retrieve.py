"""Top-k retrieval against the Redis FLAT index. Pure library function, no CLI concerns —
W6's gRPC Retrieve handler (interfaces.md §B) imports this unchanged.
"""

from dataclasses import dataclass

from llama_index.core import VectorStoreIndex

from rag import config, store
from rag.embedding import OllamaEmbedding


@dataclass
class RetrievedChunk:
    chunk_id: str
    score: float
    text: str
    doc_id: str
    ordinal: int


def retrieve(query: str, top_k: int = config.TOP_K) -> tuple[list[RetrievedChunk], int]:
    """Returns (ranked chunks, dataset_epoch). Epoch is a stub until W9-11 (interfaces.md §E)."""
    vector_store = store.get_vector_store(overwrite=False)
    index = VectorStoreIndex.from_vector_store(vector_store, embed_model=OllamaEmbedding())
    nodes = index.as_retriever(similarity_top_k=top_k).retrieve(query)

    chunks = [
        RetrievedChunk(
            chunk_id=n.metadata["chunk_id"],
            score=n.score or 0.0,
            text=n.get_content(),
            doc_id=n.metadata["doc_id"],
            ordinal=n.metadata["ordinal"],
        )
        for n in nodes
    ]
    return chunks, config.DATASET_EPOCH_STUB
