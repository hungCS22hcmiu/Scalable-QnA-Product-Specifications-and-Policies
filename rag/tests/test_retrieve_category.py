"""Product-scoped retrieval keeps only the asked product's category of policy (ADR-020).

Before ADR-020 the ranking did not know the product's category, so a question that does not name it
ranked one category's policy first for every product: "how long is the warranty on this?" got
policy-warranty-laptops for an electronics product. The fix SWAPS each other-category policy chunk
for the best same-category one, keeping the count of policy chunks, so the lane cannot move.

Pure tests always run; the live tests need Redis with v1 ingested and the embedding model, and are
skipped, loudly, otherwise -- the same convention as test_retrieve_scoping.py.
"""

import pytest

from rag import retrieve as retrieve_mod
from rag import store
from rag.retrieve import _product_category, _swap_foreign_policies, retrieve


def _redis_reachable() -> bool:
    try:
        store.get_redis_client().ping()
        return True
    except Exception:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_reachable(), reason="Redis not reachable -- start it and `make ingest` first"
)


class _Node:
    def __init__(self, chunk_id: str, category: str, score: float):
        doc_id = chunk_id.split("#")[0]
        self.metadata = {"chunk_id": chunk_id, "doc_id": doc_id, "category": category}
        self.score = score


def _ids(nodes):
    return [n.metadata["chunk_id"] for n in nodes]


OWN = "product-electronics-x1"


def test_a_spec_question_with_no_policy_chunk_is_untouched():
    nodes = [
        _Node(f"{OWN}#chunk-0", "electronics", 0.9),
        _Node(f"{OWN}#chunk-1", "electronics", 0.8),
    ]
    cands = [_Node("policy-warranty-electronics#chunk-0", "electronics", 0.5)]
    assert _swap_foreign_policies(nodes, "electronics", cands) is nodes


def test_a_foreign_policy_is_replaced_and_the_policy_count_is_kept():
    nodes = [
        _Node(f"{OWN}#chunk-0", "electronics", 0.9),
        _Node("policy-warranty-laptops#chunk-0", "laptops", 0.8),
        _Node("policy-warranty-laptops#chunk-1", "laptops", 0.7),
    ]
    cands = [
        _Node("policy-warranty-electronics#chunk-0", "electronics", 0.6),
        _Node("policy-warranty-electronics#chunk-1", "electronics", 0.5),
    ]
    out = _swap_foreign_policies(nodes, "electronics", cands)
    assert _ids(out) == [
        f"{OWN}#chunk-0",
        "policy-warranty-electronics#chunk-0",
        "policy-warranty-electronics#chunk-1",
    ]


def test_policy_slots_are_refilled_in_score_order():
    # A replacement that outscores a natural same-category policy takes the earlier slot, so the
    # rank-1 policy document (the POLICY namespace) is the best one of the right category.
    nodes = [
        _Node(f"{OWN}#chunk-0", "electronics", 0.9),
        _Node("policy-warranty-laptops#chunk-0", "laptops", 0.8),
        _Node(f"{OWN}#chunk-1", "electronics", 0.75),
        _Node("policy-return-electronics#chunk-2", "electronics", 0.6),
    ]
    cands = [
        _Node("policy-warranty-electronics#chunk-0", "electronics", 0.7),
        _Node("policy-return-electronics#chunk-2", "electronics", 0.6),
    ]
    out = _swap_foreign_policies(nodes, "electronics", cands)
    assert _ids(out) == [
        f"{OWN}#chunk-0",
        "policy-warranty-electronics#chunk-0",
        f"{OWN}#chunk-1",
        "policy-return-electronics#chunk-2",
    ]


def test_an_unknown_category_changes_nothing():
    nodes = [_Node("policy-warranty-laptops#chunk-0", "laptops", 0.8)]
    cands = [_Node("policy-warranty-electronics#chunk-0", "electronics", 0.6)]
    assert _swap_foreign_policies(nodes, "", cands) is nodes


def test_a_policy_with_no_category_is_never_foreign():
    nodes = [_Node(f"{OWN}#chunk-0", "electronics", 0.9), _Node("policy-shipping#chunk-0", "", 0.8)]
    cands = [_Node("policy-warranty-electronics#chunk-0", "electronics", 0.6)]
    assert _swap_foreign_policies(nodes, "electronics", cands) is nodes


def test_a_slot_is_removed_only_when_the_category_runs_out():
    nodes = [
        _Node(f"{OWN}#chunk-0", "electronics", 0.9),
        _Node("policy-warranty-laptops#chunk-0", "laptops", 0.8),
        _Node("policy-warranty-laptops#chunk-1", "laptops", 0.7),
    ]
    cands = [_Node("policy-warranty-electronics#chunk-0", "electronics", 0.6)]
    out = _swap_foreign_policies(nodes, "electronics", cands)
    assert _ids(out) == [f"{OWN}#chunk-0", "policy-warranty-electronics#chunk-0"]


def test_candidates_already_present_or_of_another_category_are_ignored():
    nodes = [
        _Node("policy-warranty-electronics#chunk-0", "electronics", 0.85),
        _Node("policy-warranty-laptops#chunk-0", "laptops", 0.8),
    ]
    cands = [
        _Node("policy-warranty-electronics#chunk-0", "electronics", 0.85),
        _Node("policy-warranty-phones-domestic#chunk-0", "phones", 0.84),
        _Node("policy-warranty-electronics#chunk-1", "electronics", 0.6),
    ]
    out = _swap_foreign_policies(nodes, "electronics", cands)
    assert _ids(out) == [
        "policy-warranty-electronics#chunk-0",
        "policy-warranty-electronics#chunk-1",
    ]


def test_product_category_comes_from_the_own_chunk():
    nodes = [
        _Node("policy-warranty-laptops#chunk-0", "laptops", 0.8),
        _Node(f"{OWN}#chunk-0", "electronics", 0.7),
    ]
    assert _product_category(nodes, OWN) == "electronics"
    assert _product_category(nodes, "product-electronics-absent") == ""


def _policy_docs(chunks):
    return [c.doc_id for c in chunks if c.doc_id.startswith("policy-")]


@requires_redis
@pytest.mark.parametrize(
    ("question", "product_id", "category", "rank1_prefix"),
    [
        (
            "how long is the warranty on this?",
            "product-electronics-b002ixeb1g",
            "electronics",
            "policy-warranty-electronics",
        ),
        (
            "can I return this if I opened it?",
            "product-laptops-b004gmsh80",
            "laptops",
            "policy-return-laptops",
        ),
    ],
)
def test_a_question_that_does_not_name_its_category_gets_its_own_policy(
    question, product_id, category, rank1_prefix, monkeypatch
):
    scoped, _ = retrieve(question, top_k=5, product_id=product_id)
    docs = _policy_docs(scoped)
    assert docs, "the swap must keep the policy slots the natural ranking gave"
    assert all(d.split("-")[2] == category for d in docs), docs
    assert docs[0].startswith(rank1_prefix), docs

    # Companion check: without the swap, this exact query ranks ANOTHER category's policy first,
    # with the same number of policy chunks -- so the test exercises the bug and the lane is kept.
    monkeypatch.setattr(retrieve_mod, "_ensure_category_policies", lambda i, n, q, p, k: n)
    natural, _ = retrieve(question, top_k=5, product_id=product_id)
    natural_docs = _policy_docs(natural)
    assert natural_docs and natural_docs[0].split("-")[2] != category, natural_docs
    assert len(natural_docs) == len(docs)
