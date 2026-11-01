"""Top-k retrieval against the Redis FLAT index. Pure library function, no CLI concerns —
W6's gRPC Retrieve handler (interfaces.md §B) imports this unchanged.
"""

from dataclasses import dataclass

from llama_index.core import VectorStoreIndex
from llama_index.core.vector_stores.types import MetadataFilter, MetadataFilters

from rag import config, epoch, store
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
    # Epoch first, before any chunk text (interfaces.md E order rule).
    ep = epoch.read()
    if not chunk_ids:
        return [], ep

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
    return chunks, ep


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


# ADR-021 measured two ways to refill the slots other products' chunks held. True refills only a
# retrieval whose natural top k holds no policy chunk (a pure spec question), so no lane can move;
# False refills every product-scoped retrieval. Fixed by the choice rule in
# docs/work/2026-10-31-rag-correctness/plan.md, step 1.1: True, because on the v1 validation split
# False moved MIXED-on lane counts (MIXED 24 -> 30), while True left every lane count unchanged.
_REFILL_POLICY_FREE_ONLY = True


def _refill_own(natural: list, product_id: str, candidates: list, policy_free_only: bool) -> list:
    """Refill the slots of other products' chunks with this product's best unused chunks (ADR-021).

    Pure, so the rule is testable without Redis. `natural` is the unscoped top k; `candidates` are
    this product's chunks in rank order, from one search filtered on its doc_id.

    Before ADR-021 those slots were simply dropped (_drop_other_products). The natural top k is
    taken over the whole corpus, so for a spec question it is mostly OTHER products' chunks, and
    231 of 431 v1 validation spec questions kept a single chunk of their own product: an answer in
    another chunk was "not in the context", and two paraphrases often kept two different single
    chunks, so the support gate refused a correct reuse.

    Product slots are refilled in score order (all scores come from the same query against the same
    FLAT cosine index); policy slots and their order are untouched. A slot is dropped only when the
    product has too few chunks to fill it. With `policy_free_only`, a retrieval that holds any
    policy chunk is returned exactly as before, so PolicyFraction and the lane cannot move.
    """
    kept = _drop_other_products(natural, product_id)
    if policy_free_only and any(_is_policy(n) for n in natural):
        return kept
    slots = [
        i for i, n in enumerate(natural) if n.metadata.get("doc_id", "").startswith("product-")
    ]
    own = [natural[i] for i in slots if natural[i].metadata.get("doc_id") == product_id]
    if len(own) == len(slots):
        return kept
    present = {n.metadata.get("chunk_id") for n in natural}
    fill = [
        c
        for c in candidates
        if c.metadata.get("doc_id") == product_id and c.metadata.get("chunk_id") not in present
    ]
    pool = sorted(own + fill[: len(slots) - len(own)], key=lambda n: n.score or 0.0, reverse=True)
    refill = iter(pool)
    slot_set = set(slots)
    out = []
    for i, n in enumerate(natural):
        if i not in slot_set:
            out.append(n)
            continue
        nxt = next(refill, None)
        if nxt is not None:
            out.append(nxt)
    return out


def _ensure_own_chunks(index, natural: list, query: str, product_id: str, top_k: int) -> list:
    """Drop other products' chunks and refill their slots with this product's (ADR-021).

    Issues one more search, filtered on this product's doc_id, only when a slot needs refilling.
    """
    needs_refill = any(
        n.metadata.get("doc_id", "").startswith("product-")
        and n.metadata.get("doc_id") != product_id
        for n in natural
    )
    if not needs_refill or (_REFILL_POLICY_FREE_ONLY and any(_is_policy(n) for n in natural)):
        return _drop_other_products(natural, product_id)
    own_filter = MetadataFilters(filters=[MetadataFilter(key="doc_id", value=product_id)])
    candidates = index.as_retriever(similarity_top_k=top_k, filters=own_filter).retrieve(query)
    return _refill_own(natural, product_id, candidates, _REFILL_POLICY_FREE_ONLY)


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


def _is_policy(node) -> bool:
    return node.metadata.get("doc_id", "").startswith("policy-")


def _product_category(nodes: list, product_id: str) -> str:
    """The asked product's category, read from its own chunk's metadata. "" when that chunk is
    absent (an unknown product_id, so _ensure_own_chunk found nothing): then nothing is swapped."""
    for n in nodes:
        if n.metadata.get("doc_id") == product_id:
            return n.metadata.get("category") or ""
    return ""


def _is_foreign_policy(node, category: str) -> bool:
    """A policy chunk of ANOTHER category. A policy with no category applies to every product and
    is never foreign."""
    cat = node.metadata.get("category") or ""
    return _is_policy(node) and cat != "" and cat != category


def _swap_foreign_policies(nodes: list, category: str, candidates: list) -> list:
    """Replace each other-category policy chunk with the best unused same-category one (ADR-020).

    Pure, so the rule is testable without Redis. `candidates` are this category's policy chunks in
    rank order, from one filtered search; anything else in them is ignored.

    The COUNT of policy chunks is the natural ranking's and is never changed, only WHICH policy
    fills each policy slot. PolicyFraction (reuse/lane.go) reads that count, so the lane cannot
    move, and a plain spec question (no policy chunk) is returned untouched -- the flooding
    regression _drop_other_products' docstring records cannot come back through here. A slot is
    removed only when the category has too few policy chunks to fill it.

    The policy slots are refilled in score order, because the POLICY lane's namespace is the
    rank-1 policy document: a replacement that scores higher than a policy which ranked
    naturally must take the earlier slot, or the namespace would name the weaker document.
    Product slots keep their positions. All scores come from the same query against the same
    FLAT cosine index, so they compare.
    """
    if not category or not any(_is_foreign_policy(n, category) for n in nodes):
        return nodes
    slots = [i for i, n in enumerate(nodes) if _is_policy(n)]
    kept = [nodes[i] for i in slots if not _is_foreign_policy(nodes[i], category)]
    present = {n.metadata.get("chunk_id") for n in nodes}
    fill = [
        c
        for c in candidates
        if _is_policy(c)
        and (c.metadata.get("category") or "") == category
        and c.metadata.get("chunk_id") not in present
    ]
    pool = sorted(kept + fill[: len(slots) - len(kept)], key=lambda n: n.score or 0.0, reverse=True)
    refill = iter(pool)
    slot_set = set(slots)
    out = []
    for i, n in enumerate(nodes):
        if i not in slot_set:
            out.append(n)
            continue
        nxt = next(refill, None)
        if nxt is not None:
            out.append(nxt)
    return out


def _ensure_category_policies(index, nodes: list, query: str, product_id: str, top_k: int) -> list:
    """Product-scoped retrieval keeps only policy chunks of the asked product's category (ADR-020).

    The policy corpus is per category, and the windows differ (laptops new 30 days, phones 14,
    furniture opened 180), but nothing in the ranking knew the product's category. Measured on
    v1 before this fix (validation split, citable: no): 13 of 170 policy-lane questions ranked
    another category's policy first, and a question that does not name its category -- "can I
    return this if I opened it?" -- did so for every product outside the one category that won.
    Rank-1 policy is the POLICY lane's namespace, so that was a wrong answer and a wrong cache
    partition at once.

    Runs after _ensure_own_chunk, which supplies the product's own chunk and so its category.
    Issues one more, category-filtered search only when a foreign policy chunk is present.
    """
    category = _product_category(nodes, product_id)
    if not category or not any(_is_foreign_policy(n, category) for n in nodes):
        return nodes
    policy_filter = MetadataFilters(
        filters=[
            MetadataFilter(key="kind", value="policy"),
            MetadataFilter(key="category", value=category),
        ]
    )
    candidates = index.as_retriever(similarity_top_k=2 * top_k, filters=policy_filter).retrieve(
        query
    )
    return _swap_foreign_policies(nodes, category, candidates)


def retrieve(
    query: str, top_k: int = config.TOP_K, product_id: str | None = None
) -> tuple[list[RetrievedChunk], int]:
    """Returns (ranked chunks, dataset_epoch). The epoch is read first, before any chunk text
    (interfaces.md E order rule); 0 means the epoch file could not be read (rag/epoch.py)."""
    ep = epoch.read()
    vector_store = store.get_vector_store(overwrite=False)
    index = VectorStoreIndex.from_vector_store(vector_store, embed_model=OllamaEmbedding())
    nodes = index.as_retriever(similarity_top_k=top_k).retrieve(query)
    if product_id:
        nodes = _ensure_own_chunks(index, nodes, query, product_id, top_k)
        nodes = _ensure_own_chunk(index, nodes, query, product_id, top_k)
        nodes = _ensure_category_policies(index, nodes, query, product_id, top_k)
    return _to_chunks(nodes), ep


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
