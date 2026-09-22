"""Tests for the corpus sensitivity gate (data-card.md §7).

The gate decides whether a corpus may be frozen, so its failure mode is the expensive one: a gate
that passes a bad corpus is only discovered weeks later, when C1 returns a null result that cannot
be attributed to the rule or to the data. Every test here pins a property whose drift would be
silent.

No corpus fixtures on disk: the real one lives under `data/`, which these tests deliberately do
not read (it is the human's artifact, and reading it would make the tests depend on a corpus that
does not exist yet). Records are built inline.
"""

import json
from pathlib import Path

import pytest
from corpus_gate import (
    Query,
    check_g1,
    check_g2,
    check_g3,
    check_g4,
    cosine,
    derive_capacity,
    find_pairs,
    jaccard,
    label_pair,
    normalize_t1,
    snapshot_digest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "contracts" / "normalize" / "cases.json"


# =================================================================================================
# The cross-language pin
# =================================================================================================
def _contract_cases():
    contract = json.loads(CONTRACT.read_text())
    assert contract["adr"] == "ADR-015"
    assert contract["cases"], "an empty contract would pass vacuously on both sides"
    return [(c["name"], c["in"], c["out"]) for c in contract["cases"]]


@pytest.mark.parametrize("name,text,want", _contract_cases())
def test_normalize_matches_cross_language_contract(name, text, want):
    """G3 groups queries the way Tier 1 will, and Tier 1 is implemented in Go.

    `gateway/internal/cache/normalize_contract_test.go` asserts the same file. If the two ever
    diverge, one of these two tests fails — which is the only reason the divergence would ever be
    noticed, since both sides individually keep working.
    """
    assert normalize_t1(text) == want, name


def test_normalize_is_idempotent():
    for text in ("How Long Is The WARRANTY?", "  laptop ,  headphones  ", "???", ""):
        once = normalize_t1(text)
        assert normalize_t1(once) == once


# =================================================================================================
# G4 -- doc-id kind prefix
# =================================================================================================
def test_g4_passes_a_prefixed_corpus():
    assert check_g4(["product-b08xyz", "policy-returns-electronics"]).passed


def test_g4_reports_every_offender_not_just_the_first():
    """`rag.ingest` raises on the first bad doc-id; the gate must list them all in one pass so the
    corpus is re-slugged once rather than iterated file by file."""
    result = check_g4(["product-ok", "returns-policy", "warranty", "policy-ok"])
    assert not result.passed
    assert len(result.detail) == 2


def test_g4_rejects_a_prefixless_corpus_rather_than_defaulting_it():
    """The failure this criterion exists for: without a prefix the lane rule reads every question
    as SPEC (ADR-030), the mixed lane never fires, and nothing errors — a null result produced by
    the corpus rather than by the rule."""
    assert not check_g4(["b08xyz", "returns-electronics"]).passed


# =================================================================================================
# G3 -- Tier-1 collisions
# =================================================================================================
def _q(qa_id, question, doc_ids=(), product_id="", stratum="", answer=""):
    return Query(
        qa_id=qa_id,
        question=question,
        doc_ids=tuple(doc_ids),
        product_id=product_id,
        stratum=stratum,
        reference_answer=answer,
    )


def test_g3_catches_a_collision_created_by_punctuation_stripping():
    """interfaces.md §D's documented lossy case: stripping punctuation collapses `Model A-1` and
    `Model A1`. Harmless within one product, not harmless across two — and Tier 1 runs no reuse
    rule, so the second query is served the first one's answer permanently."""
    result, _ = check_g3(
        [
            _q("q1", "warranty for Model A-1", doc_ids=["policy-warranty-electronics"]),
            _q("q2", "warranty for Model A1", doc_ids=["policy-warranty-kitchen"]),
        ]
    )
    assert not result.passed
    assert "Model A-1" in result.detail[0] or "model a1" in result.detail[0]


def test_g3_treats_an_agreeing_duplicate_as_benign_not_a_collision():
    """The same question asked twice is legal. Counting it as a collision would fail every
    realistic workload, and the count is reported separately because many benign duplicates mean
    the effective K is smaller than the record count."""
    result, benign = check_g3(
        [
            _q("q1", "how long is the warranty?", doc_ids=["policy-warranty"], answer="two years"),
            _q("q2", "How long is the warranty", doc_ids=["policy-warranty"], answer="two years"),
        ]
    )
    assert result.passed
    assert benign == 1


def test_g3_flags_duplicates_that_agree_on_docs_but_not_on_the_answer():
    """Disagreement is on `doc_ids` OR `reference_answer` — either one makes the Tier-1 hit wrong."""
    result, _ = check_g3(
        [
            _q("q1", "how long is the warranty", doc_ids=["policy-warranty"], answer="two years"),
            _q("q2", "how long is the warranty", doc_ids=["policy-warranty"], answer="one year"),
        ]
    )
    assert not result.passed


def test_g3_passes_a_clean_workload():
    result, benign = check_g3([_q("q1", "battery life"), _q("q2", "return window")])
    assert result.passed and benign == 0


def test_g3_different_product_id_no_longer_collides():
    """⚠️ BYPASS 2026-09-09: the Tier-1 key gained product_id (cache.Key), reversing ADR-028's
    "product_id in the Tier-1 key -- Rejected". The same literal question, disagreeing doc_ids,
    asked about two DIFFERENT products, is no longer a Tier-1 collision -- it hashes to two
    different Redis keys and can no longer be served wrongly from one write."""
    result, _ = check_g3(
        [
            _q("q1", "how long is the battery life", doc_ids=["product-headphones-03"],
               product_id="product-headphones-03"),
            _q("q2", "how long is the battery life", doc_ids=["product-headphones-04"],
               product_id="product-headphones-04"),
        ]
    )
    assert result.passed


def test_g3_same_product_id_still_collides():
    """The partition is (normalize(q), product_id), not product_id alone: two disagreeing
    queries under the SAME product still collide, exactly as before this bypass."""
    result, _ = check_g3(
        [
            _q("q1", "how long is the warranty", doc_ids=["policy-warranty"],
               product_id="product-headphones-03", answer="two years"),
            _q("q2", "how long is the warranty", doc_ids=["policy-returns-electronics"],
               product_id="product-headphones-03", answer="30 days"),
        ]
    )
    assert not result.passed


# =================================================================================================
# The gate's overlap -- Jaccard, not the rule's containment (ADR-024)
# =================================================================================================
def test_jaccard_is_symmetric_unlike_the_rule():
    a, b = ("c1", "c2"), ("c1", "c2", "c3", "c4", "c5")
    assert jaccard(a, b) == jaccard(b, a) == pytest.approx(0.4)


def test_jaccard_of_two_empty_sets_is_zero_not_one():
    """Vacuous agreement is not evidence of shared provenance. Scoring it 1 would push a pair of
    ungrounded queries above the ceiling and quietly drop it from G1's count."""
    assert jaccard((), ()) == 0.0


def test_jaccard_ceiling_admits_at_most_one_shared_chunk_at_the_frozen_depth():
    """data-card.md §7's claim, made executable: at equal retrieval depth, `J <= 0.2` means at most
    one chunk in common. Two shared chunks out of five each gives J = 2/8 = 0.25 > 0.2."""
    five_a = tuple(f"a{i}" for i in range(5))
    one_shared = ("a0",) + tuple(f"b{i}" for i in range(4))
    two_shared = ("a0", "a1") + tuple(f"b{i}" for i in range(3))
    assert jaccard(five_a, one_shared) <= 0.2
    assert jaccard(five_a, two_shared) > 0.2


# =================================================================================================
# G1 / G2
# =================================================================================================
def test_g1_needs_the_floor():
    def pairs(n):
        from corpus_gate import Pair

        return [Pair(f"a{i}", f"b{i}", 0.9, 0.0, "B-within") for i in range(n)]

    assert not check_g1(pairs(49)).passed
    assert check_g1(pairs(50)).passed


def test_g2_fails_a_corpus_whose_traps_are_all_cross_product():
    """ADR-028's whole reason for splitting stratum B: if every trap is cross-product, adding
    `product_id` to the cache key reproduces C1's benefit at zero cost and C1 is redundant by
    construction of the corpus."""
    from corpus_gate import Pair

    result = check_g2([Pair("a", "b", 0.9, 0.0, "B-cross") for _ in range(80)])
    assert not result.passed


def test_g2_passes_on_a_single_within_product_trap():
    """No numeric floor above zero is set (data-card.md §7): there is no evidence yet from which to
    derive one, and an invented threshold is less defensible than a stated gap."""
    from corpus_gate import Pair

    assert check_g2([Pair("a", "b", 0.9, 0.0, "B-within")]).passed


def test_an_unlabelled_pair_is_never_folded_into_b_cross():
    """Guessing an unlabelled pair into either bucket is guessing at exactly the quantity G2
    measures."""
    assert label_pair(_q("a", "?", product_id=""), _q("b", "?", product_id="p1")) == "unlabelled"
    assert label_pair(_q("a", "?", product_id="p1"), _q("b", "?", product_id="p1")) == "B-within"
    assert label_pair(_q("a", "?", product_id="p1"), _q("b", "?", product_id="p2")) == "B-cross"


def test_find_pairs_counts_overlap_over_all_high_similarity_pairs():
    """§7's overlap-variance statistic is over ALL high-similarity pairs, not only those clearing
    the low-overlap ceiling — a corpus where every lookalike also shares its grounding has overlap
    ≈ 1 everywhere and cannot produce a C1 signal, which shows in the distribution first."""
    same = [1.0, 0.0]
    a = Query("a", "x", product_id="p1", embedding=same, retrieved=("c1", "c2"))
    b = Query("b", "y", product_id="p2", embedding=same, retrieved=("c3", "c4"))
    c = Query("c", "z", product_id="p3", embedding=same, retrieved=("c1", "c2"))
    pairs, overlaps = find_pairs([a, b, c])

    assert len(overlaps) == 3  # every high-similarity pair contributes
    assert len(pairs) == 2  # only the two that also ground differently
    assert sorted(overlaps) == [0.0, 0.0, 1.0]


def test_find_pairs_ignores_dissimilar_queries():
    a = Query("a", "x", embedding=[1.0, 0.0], retrieved=("c1",))
    b = Query("b", "y", embedding=[0.0, 1.0], retrieved=("c2",))
    pairs, overlaps = find_pairs([a, b])
    assert pairs == [] and overlaps == []


def test_cosine_of_a_zero_vector_is_zero_not_nan():
    """An embedding call that returned zeros would otherwise poison every comparison with NaN, and
    NaN fails every threshold silently rather than loudly."""
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


# =================================================================================================
# Capacity and the freeze record
# =================================================================================================
def test_capacity_is_a_quarter_of_k_rounded():
    """ADR-027. A COUNT of entries, never a byte budget — ADR-031 puts enforcement in the gateway
    for exactly that reason."""
    assert derive_capacity(240) == 60
    assert derive_capacity(1) == 0  # round(0.25) == 0 under banker's rounding; K this small is not
    assert derive_capacity(200) == 50  # a real workload, and an unbounded cache is the honest default


def test_snapshot_digest_changes_when_a_file_changes(tmp_path):
    a, b = tmp_path / "product-1.json", tmp_path / "product-2.json"
    a.write_text('{"doc_id":"product-1"}')
    b.write_text('{"doc_id":"product-2"}')

    import corpus_gate

    original_root = corpus_gate.REPO_ROOT
    corpus_gate.REPO_ROOT = tmp_path
    try:
        before, _ = snapshot_digest([a, b])
        a.write_text('{"doc_id":"product-1","title":"edited"}')
        after, _ = snapshot_digest([a, b])
        assert before != after
    finally:
        corpus_gate.REPO_ROOT = original_root


def test_snapshot_digest_is_order_independent_but_rename_sensitive(tmp_path):
    """The digest hashes a sorted (path, file-hash) manifest, so directory iteration order cannot
    change it, but a rename — which reassigns chunk IDs and therefore breaks every cached
    provenance record (ADR-008) — must."""
    a, b = tmp_path / "product-1.json", tmp_path / "product-2.json"
    a.write_text("{}")
    b.write_text("{}")

    import corpus_gate

    original_root = corpus_gate.REPO_ROOT
    corpus_gate.REPO_ROOT = tmp_path
    try:
        before = snapshot_digest([a, b])[0]
        assert snapshot_digest([b, a])[0] == before

        renamed = tmp_path / "product-9.json"
        b.rename(renamed)
        assert snapshot_digest([a, renamed])[0] != before
    finally:
        corpus_gate.REPO_ROOT = original_root
