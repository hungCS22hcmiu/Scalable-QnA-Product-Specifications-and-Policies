"""Top-k retrieval against the Redis FLAT index. Pure library function, no CLI concerns —
W6's gRPC Retrieve handler (interfaces.md §B) imports this unchanged.
"""

from dataclasses import dataclass

from llama_index.core import VectorStoreIndex
from llama_index.core.vector_stores.types import MetadataFilter, MetadataFilters

from rag import config, store
from rag.embedding import OllamaEmbedding


@dataclass
class RetrievedChunk:
    chunk_id: str
    score: float
    text: str
    doc_id: str
    ordinal: int


def fetch_by_ids(chunk_ids: list[str]) -> tuple[list[RetrievedChunk], int]:
    """Load chunks the CALLER already retrieved, preserving its rank order.

    This is the second half of single-retrieval: the gateway retrieves once, concurrently with its
    embedding, and hands the ids here so Answer does not retrieve again. The saving is not the
    vector search — it is the query EMBEDDING that a second retrieval would redo.

    Reads the `text` field declared in store.build_schema(), not any LlamaIndex-internal field,
    so this does not couple generation to the library's storage layout.

    ⚠️ Rank order is the caller's and must be preserved: generation is order-sensitive, and the
    reuse rule's namespace is derived from the RANK-1 document of each kind. Sorting or
    de-duplicating here would silently repartition the cache.

    A chunk id that is absent is DROPPED rather than substituted. Fabricating a chunk would put
    text into the answer that no provenance record accounts for; a short context is visible in the
    answer, an invented one is not.
    """
    if not chunk_ids:
        return [], config.DATASET_EPOCH_STUB

    client = store.get_redis_client()
    chunks: list[RetrievedChunk] = []
    for chunk_id in chunk_ids:
        key = f"{config.CORPUS_KEY_PREFIX}:{chunk_id}"
        fields = client.hmget(key, ["text", "doc_id", "ordinal"])
        text = fields[0]
        if not text:
            continue
        chunks.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                score=0.0,  # the caller ranked these; no score is recomputed here
                text=text.decode() if isinstance(text, bytes) else text,
                doc_id=(fields[1].decode() if isinstance(fields[1], bytes) else fields[1]) or "",
                ordinal=int(fields[2]) if fields[2] else 0,
            )
        )
    return chunks, config.DATASET_EPOCH_STUB


def _to_chunks(nodes) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=n.metadata["chunk_id"],
            score=n.score or 0.0,
            text=n.get_content(),
            doc_id=n.metadata["doc_id"],
            ordinal=n.metadata["ordinal"],
        )
        for n in nodes
    ]


def _drop_other_products(nodes: list, product_id: str) -> list:
    """Post-filter, not pre-filter (corrected). Drops only a chunk that belongs to a
    DIFFERENT product; everything else -- including any policy chunk -- keeps the natural rank
    order and composition the unscoped search actually produced. Policy content survives here
    only because it genuinely ranked, never because a blanket eligibility filter forced it in.

    The original v1 of this fix pre-filtered candidates to "this product OR any policy", which
    in a small corpus (four policy docs, one chunk per product) shrinks the eligible pool to
    near top_k -- so nearly every candidate returned, regardless of relevance, and
    PolicyFraction (reuse/lane.go) saturated toward ~0.8 for almost any product-scoped query,
    misclassifying plain SPEC questions as POLICY and collapsing their namespace to whichever
    policy doc ranked first -- a namespace shared by every OTHER product asked a similar
    question. Confirmed live 2026-09-10: product-kitchen-05 (Air Fryer XL, has a real 1800W
    power spec) was served product-laptops-02's "no power info" cached answer this way -- a
    genuine cross-product false hit, worse than the bug product scoping set out to
    close. Filtering
    AFTER ranking instead of before it removes the failure mode at its source.
    """
    return [
        n
        for n in nodes
        if not (
            n.metadata.get("doc_id", "").startswith("product-")
            and n.metadata.get("doc_id") != product_id
        )
    ]


def _ensure_own_chunk(index, nodes: list, query: str, product_id: str, top_k: int) -> list:
    """If product_id's own chunk did not naturally rank -- the generic-phrasing
    failure product scoping exists to close -- fetch it with one small,
    product-scoped search and splice it in, dropping
    the lowest-ranked survivor to stay within top_k. Never force-includes anything else: only
    ever the ONE chunk this specific product owns, so this can only ever push PolicyFraction
    down (a product chunk added to the denominator) or leave it unchanged, never up.
    """
    if any(n.metadata.get("doc_id") == product_id for n in nodes):
        return nodes
    own_filter = MetadataFilters(filters=[MetadataFilter(key="doc_id", value=product_id)])
    own_nodes = index.as_retriever(similarity_top_k=1, filters=own_filter).retrieve(query)
    if not own_nodes:
        return nodes
    return (own_nodes + nodes)[:top_k]


def retrieve(
    query: str, top_k: int = config.TOP_K, product_id: str | None = None
) -> tuple[list[RetrievedChunk], int]:
    """Returns (ranked chunks, dataset_epoch). Epoch is a stub until W9-11 (interfaces.md §E)."""
    vector_store = store.get_vector_store(overwrite=False)
    index = VectorStoreIndex.from_vector_store(vector_store, embed_model=OllamaEmbedding())
    nodes = index.as_retriever(similarity_top_k=top_k).retrieve(query)
    if product_id:
        nodes = _drop_other_products(nodes, product_id)
        nodes = _ensure_own_chunk(index, nodes, query, product_id, top_k)
    return _to_chunks(nodes), config.DATASET_EPOCH_STUB


def make_retriever(top_k: int = config.TOP_K):
    """A retriever bound once, for callers that issue MANY queries in one process.

    retrieve() above reconnects the vector store and rebuilds the index on every call, which is
    right for the one-query-per-RPC server but is the dominant cost when the corpus gate sweeps a
    few hundred workload queries (data-card.md §7). The retrieval path itself is identical —
    same frozen schema, same FLAT index, same top_k — so the gate measures what production does.
    """
    vector_store = store.get_vector_store(overwrite=False)
    index = VectorStoreIndex.from_vector_store(vector_store, embed_model=OllamaEmbedding())
    retriever = index.as_retriever(similarity_top_k=top_k)

    def run(query: str) -> list[RetrievedChunk]:
        return _to_chunks(retriever.retrieve(query))

    return run
