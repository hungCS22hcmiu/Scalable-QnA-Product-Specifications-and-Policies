"""Product-scoped retrieval keeps enough of the asked product's own chunks (ADR-021).

Before ADR-021 the natural top k was taken over the whole corpus and other products' chunks were
then dropped, so 231 of 431 validation spec questions kept a single chunk of their own product,
and an answer in another chunk was "not in the context". Each live case below was seen on
2026-10-31 and must retrieve the chunk that holds its answer.

Live tests need Redis with v1 ingested and the embedding model, and are skipped, loudly,
otherwise -- the same convention as test_retrieve_scoping.py.
"""

import pytest

from rag import store
from rag.retrieve import _refill_own, retrieve

OWN = "product-electronics-x1"
OTHER = "product-electronics-x2"


class _Node:
    def __init__(self, chunk_id: str, score: float):
        self.metadata = {"chunk_id": chunk_id, "doc_id": chunk_id.split("#")[0]}
        self.score = score


def _ids(nodes):
    return [n.metadata["chunk_id"] for n in nodes]


def test_other_products_slots_are_refilled_in_score_order():
    natural = [
        _Node(f"{OTHER}#chunk-0", 0.9),
        _Node(f"{OWN}#chunk-2", 0.8),
        _Node(f"{OTHER}#chunk-1", 0.7),
    ]
    cands = [
        _Node(f"{OWN}#chunk-5", 0.85),
        _Node(f"{OWN}#chunk-2", 0.8),
        _Node(f"{OWN}#chunk-1", 0.6),
    ]
    out = _refill_own(natural, OWN, cands, policy_free_only=True)
    assert _ids(out) == [f"{OWN}#chunk-5", f"{OWN}#chunk-2", f"{OWN}#chunk-1"]


def test_no_chunk_twice_no_other_product_and_at_most_the_natural_length():
    natural = [_Node(f"{OTHER}#chunk-{i}", 0.9 - i / 10) for i in range(5)]
    cands = [_Node(f"{OWN}#chunk-{i}", 0.5 - i / 10) for i in range(3)] + [
        _Node(f"{OTHER}#chunk-9", 0.99)
    ]
    out = _ids(_refill_own(natural, OWN, cands, policy_free_only=True))
    assert len(out) == len(set(out)) <= len(natural)
    assert all(c.startswith(OWN) for c in out)


def test_a_slot_is_dropped_only_when_the_product_runs_out():
    natural = [_Node(f"{OTHER}#chunk-0", 0.9), _Node(f"{OTHER}#chunk-1", 0.8)]
    out = _refill_own(natural, OWN, [_Node(f"{OWN}#chunk-0", 0.5)], policy_free_only=True)
    assert _ids(out) == [f"{OWN}#chunk-0"]


def test_with_a_policy_chunk_v2_returns_the_old_result_untouched():
    natural = [
        _Node(f"{OTHER}#chunk-0", 0.9),
        _Node("policy-return-electronics#chunk-1", 0.85),
        _Node(f"{OWN}#chunk-1", 0.8),
    ]
    out = _refill_own(natural, OWN, [_Node(f"{OWN}#chunk-0", 0.7)], policy_free_only=True)
    assert _ids(out) == ["policy-return-electronics#chunk-1", f"{OWN}#chunk-1"]


def test_v1_refills_product_slots_and_leaves_policy_slots_in_place():
    natural = [
        _Node(f"{OTHER}#chunk-0", 0.9),
        _Node("policy-return-electronics#chunk-1", 0.85),
        _Node(f"{OWN}#chunk-1", 0.8),
    ]
    out = _refill_own(natural, OWN, [_Node(f"{OWN}#chunk-0", 0.7)], policy_free_only=False)
    assert _ids(out) == [f"{OWN}#chunk-1", "policy-return-electronics#chunk-1", f"{OWN}#chunk-0"]


def test_nothing_to_refill_when_every_product_slot_is_already_own():
    natural = [_Node(f"{OWN}#chunk-0", 0.9), _Node(f"{OWN}#chunk-1", 0.8)]
    out = _refill_own(natural, OWN, [_Node(f"{OWN}#chunk-3", 0.95)], policy_free_only=True)
    assert _ids(out) == [f"{OWN}#chunk-0", f"{OWN}#chunk-1"]


def _redis_reachable() -> bool:
    try:
        store.get_redis_client().ping()
        return True
    except Exception:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_reachable(), reason="Redis not reachable -- start it and `make ingest` first"
)


@requires_redis
@pytest.mark.parametrize(
    ("product_id", "question", "any_of"),
    [
        ("product-electronics-b07r8pr5yz", "What comes in the box?", {"#chunk-5"}),
        (
            "product-electronics-b07r8pr5yz",
            "How long does a full charge take?",
            {"#chunk-0", "#chunk-5"},
        ),
        ("product-electronics-b07b63r768", "Are these headphones foldable?", {"#chunk-1"}),
        ("product-electronics-b07b63r768", "What is the standby time?", {"#chunk-1"}),
        ("product-electronics-b07b63r768", "Is a carrying case included?", {"#chunk-1"}),
    ],
)
def test_the_chunk_holding_the_answer_is_retrieved(product_id, question, any_of):
    chunks, _ = retrieve(question, top_k=5, product_id=product_id)
    got = [c.chunk_id for c in chunks]
    assert any(f"{product_id}{suffix}" in got for suffix in any_of), got
