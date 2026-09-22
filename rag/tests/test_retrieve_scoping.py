"""Product-scoped retrieval (corrected): Retrieve/Answer gain product_id, scoping
the corpus search to that
product's own chunk. Implemented as a POST-filter on the natural, unscoped ranking (drop other
products' chunks, then splice this product's own chunk in only if it didn't naturally rank) --
not a pre-filter that would force every policy chunk into the candidate pool and saturate
PolicyFraction (reuse/lane.go), which is exactly the regression this file also pins.

Pure tests always run; the live tests need a running Redis with the dev-v0 corpus ingested and
are skipped, loudly, otherwise -- never a silent pass (this repo's own /verify philosophy).
"""

import pytest

from rag import store
from rag.retrieve import _drop_other_products, retrieve


def _redis_reachable() -> bool:
    try:
        store.get_redis_client().ping()
        return True
    except Exception:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_reachable(), reason="Redis not reachable -- start it and `make ingest` first"
)


class _FakeNode:
    def __init__(self, doc_id: str):
        self.metadata = {"doc_id": doc_id}


def test_drop_other_products_keeps_policy_and_own_chunk():
    nodes = [
        _FakeNode("product-laptops-02"),
        _FakeNode("policy-warranty"),
        _FakeNode("product-kitchen-05"),
        _FakeNode("policy-shipping"),
    ]
    kept = _drop_other_products(nodes, "product-laptops-02")
    assert [n.metadata["doc_id"] for n in kept] == [
        "product-laptops-02",
        "policy-warranty",
        "policy-shipping",
    ]


def test_drop_other_products_no_product_chunk_present():
    nodes = [_FakeNode("policy-warranty"), _FakeNode("policy-shipping")]
    kept = _drop_other_products(nodes, "product-laptops-02")
    assert [n.metadata["doc_id"] for n in kept] == ["policy-warranty", "policy-shipping"]


@requires_redis
def test_retrieve_unscoped_behaviour_is_unchanged_when_product_id_absent():
    query = "what is the power rating of this item exactly right now"
    unscoped, _ = retrieve(query, top_k=5)
    explicit_none, _ = retrieve(query, top_k=5, product_id=None)
    assert [c.chunk_id for c in unscoped] == [c.chunk_id for c in explicit_none]
    assert [c.score for c in unscoped] == [c.score for c in explicit_none]


@requires_redis
def test_product_scoping_prevents_cross_product_contamination():
    """The original bug, reproduced and pinned. product-laptops-02 (UltraBook Air 13) has no
    "power" spec at all; product-kitchen-05 (Air Fryer XL) does ("power": "1800W"). Unscoped,
    the literal word "power" pulls in the kitchen chunk regardless of which product is actually
    being asked about -- confirmed live 2026-09-09/10. Scoped by product_id, that chunk must
    never come back.
    """
    query = "what is the power rating of this item exactly right now"

    scoped, _ = retrieve(query, top_k=5, product_id="product-laptops-02")
    scoped_doc_ids = {c.doc_id for c in scoped}
    assert not any(d.startswith("product-kitchen") for d in scoped_doc_ids)

    # Companion sanity check: truly unscoped, this exact query DOES pull in a kitchen chunk --
    # proves the test above exercises the actual bug precondition, not a vacuous pass.
    unscoped, _ = retrieve(query, top_k=5)
    unscoped_doc_ids = {c.doc_id for c in unscoped}
    assert any(d.startswith("product-kitchen") for d in unscoped_doc_ids)


@requires_redis
def test_scoping_does_not_flood_policy_chunks_for_a_plain_spec_question():
    """The regression, reproduced and pinned. A prior version of this fix pre-filtered the
    candidate pool to "this product OR any policy chunk" -- in dev-v0 (4 policy docs, 1 chunk
    per product) that pool has only 5 members, so nearly every candidate came back regardless
    of relevance, and PolicyFraction (reuse/lane.go) saturated toward ~0.8 for almost any
    product-scoped question. Confirmed live 2026-09-10: product-kitchen-05, which genuinely has
    a power spec, got served product-laptops-02's cached "no power info" answer because both
    collapsed into the same policy-dominated namespace. This asserts the corrected behaviour:
    a plain spec question scoped to a product that HAS the answer must not come back
    policy-dominated.
    """
    scoped, _ = retrieve(
        "how many watts does this appliance use", top_k=5, product_id="product-kitchen-05"
    )
    policy_count = sum(1 for c in scoped if c.doc_id.startswith("policy-"))
    assert policy_count < len(scoped), (
        f"retrieval for a plain spec question came back policy-dominated "
        f"({policy_count}/{len(scoped)} policy chunks) -- PolicyFraction would misclassify "
        f"this as the POLICY lane"
    )
    assert any(c.doc_id == "product-kitchen-05" for c in scoped)
