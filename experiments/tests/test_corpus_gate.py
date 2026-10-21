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
    Pair,
    Query,
    check_g1,
    check_g2,
    check_g3,
    check_g4,
    check_g5,
    check_split_files,
    check_workload_shape,
    condition_hits,
    cosine,
    derive_capacity,
    derive_split,
    find_pairs,
    freeze_files,
    jaccard,
    k_per_run_file,
    label_pair,
    load_policy_records,
    load_workload,
    normalize_t1,
    retrieve_all,
    similar_pairs,
    snapshot_digest,
    split_pairs,
    split_path,
    trap_fraction,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "contracts" / "normalize" / "cases.json"


# =================================================================================================
# The cross-language pin
# =================================================================================================
def _contract_cases():
    contract = json.loads(CONTRACT.read_text())
    assert contract["contract"] == "tier1-query-normalization"
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
    as SPEC, the mixed lane never fires, and nothing errors — a null result produced by
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
    """⚠️ BYPASS 2026-09-09: the Tier-1 key gained product_id (cache.Key), reversing the
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
# The gate's overlap -- Jaccard, not the rule's containment
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
    """the whole reason for splitting stratum B: if every trap is cross-product, adding
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
    """the capacity ratio. A COUNT of entries, never a byte budget puts enforcement in the gateway
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
    provenance record — must."""
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


# =================================================================================================
# G5 -- condition-splitting (design review H1: a document may name only what it declares)
# =================================================================================================
def _policy(doc_id, kind, category, text, axis=None, value=None):
    cond = {"axis": axis, "value": value} if axis else None
    return {"doc_id": doc_id, "title": doc_id, "category": category, "policy_kind": kind,
            "condition": cond, "text": text}


def _phones_returns(unopened_text="Unopened phones go back within 14 days."):
    return [
        _policy("policy-return-phones-unopened", "return", "phones", unopened_text,
                "packaging", "unopened"),
        _policy("policy-return-phones-opened", "return", "phones",
                "Opened phones carry a restocking fee of $45.", "packaging", "opened"),
    ]


def test_g5_passes_a_clean_split_and_counts_it():
    g5, counts = check_g5(_phones_returns())
    assert g5.passed, g5.detail
    assert counts == {"split_families": 1, "offending_documents": 0}
    assert "lexical" in g5.name and "author's read" in g5.summary


def test_g5_fails_a_document_that_names_only_its_siblings_value():
    """The natural violation: one value named, the other implied. A both-values rule misses it."""
    docs = [
        _policy("policy-warranty-phones-domestic", "warranty", "phones",
                "The warranty is not valid outside the United States.", "region", "domestic"),
        _policy("policy-warranty-phones-international", "warranty", "phones",
                "International service is not covered.", "region", "international"),
    ]
    g5, counts = check_g5(docs)
    assert not g5.passed
    assert counts["offending_documents"] == 1
    assert any("policy-warranty-phones-domestic" in d and "international" in d for d in g5.detail)


def test_g5_names_both_values_when_a_document_holds_both():
    """super-plan item 3.5's Done-when: the gate fails such a corpus and names both."""
    docs = _phones_returns("Unopened phones go back freely; opened ones carry a fee.")
    g5, _ = check_g5(docs)
    line = next(d for d in g5.detail if d.startswith("policy-return-phones-unopened"))
    assert "opened ('opened')" in line and "unopened ('unopened')" in line


def test_g5_fails_an_unsplit_document_that_names_a_condition():
    doc = _policy("policy-return-electronics", "return", "electronics",
                  "Opened TVs carry a fee.")
    assert not check_g5([doc])[0].passed


def test_g5_fails_a_return_document_that_states_the_warranty():
    doc = _policy("policy-return-electronics", "return", "electronics",
                  "Defective items are covered by the warranty.")
    g5, _ = check_g5([doc])
    assert not g5.passed and "kind" in g5.detail[0]


def test_g5_skips_plain_new_outside_the_grade_family_only():
    unsplit = _policy("policy-return-electronics", "return", "electronics",
                      "We refund the amount to a new gift card.")
    assert check_g5([unsplit])[0].passed

    grade = [
        _policy("policy-return-laptops-new", "return", "laptops", "New laptops: 30 days.",
                "grade", "new"),
        _policy("policy-return-laptops-renewed", "return", "laptops",
                "Renewed laptops: 90 days, or a new replacement.", "grade", "renewed"),
    ]
    g5, _ = check_g5(grade)
    assert not g5.passed
    assert any(d.startswith("policy-return-laptops-renewed") for d in g5.detail)


def test_condition_words_respect_word_boundaries():
    assert "new" not in condition_hits("renewed laptops").get("grade", {})
    assert "opened" not in condition_hits("unopened boxes").get("packaging", {})
    assert "opened" in condition_hits("un-opened boxes")["packaging"]  # loud, not silent
    assert "international" in condition_hits("service outside the U.S. only")["region"]


def test_g5_ignores_products_and_reports_every_offender():
    product = {"doc_id": "product-laptops-b0000000001", "title": "Renewed laptop, new battery",
               "category": "laptops", "specs": {}}
    bad = [
        _policy("policy-return-electronics", "return", "electronics", "Opened items: a fee."),
        _policy("policy-warranty-electronics", "warranty", "electronics", "Sealed boxes only."),
    ]
    g5, counts = check_g5([product, *bad])
    assert counts["offending_documents"] == 2 and len(g5.detail) == 2
    assert "0/2 policy documents clean" in g5.summary  # the product is not counted as a policy


def test_load_policy_records_reads_whole_policy_records_only(tmp_path):
    (tmp_path / "policy-warranty-furniture.json").write_text(
        json.dumps({"doc_id": "policy-warranty-furniture", "text": "Ten years."})
    )
    (tmp_path / "product-furniture-x.json").write_text(json.dumps({"doc_id": "product-furniture-x"}))
    records = load_policy_records(tmp_path)
    assert [r["doc_id"] for r in records] == ["policy-warranty-furniture"]
    assert records[0]["text"] == "Ten years."



# =================================================================================================
# G5 -- /ai-review fixes (2026-10-21)
# =================================================================================================
@pytest.mark.parametrize(
    "text",
    [
        "The warranty is not valid outside the\nUnited States.",  # a line break inside the phrase
        "The warranty is not valid outside  the United States.",  # a double space
        "Not valid outside of the United States.",
        "Not valid outside the USA.",
        "Foreign service is not offered.",
        "Not valid in other countries.",
    ],
)
def test_g5_catches_the_reworded_sibling_value(text):
    """F2: the design review's own H1 example, one rewording away from passing."""
    doc = _policy("policy-warranty-phones-domestic", "warranty", "phones", text, "region", "domestic")
    assert not check_g5([doc])[0].passed


def test_g5_catches_reworded_packaging_words():
    for text in ("Unsealed phones carry a fee.", "Reopened phones carry a fee.",
                 "Before you open the box, read this."):
        doc = _policy("policy-return-phones-unopened", "return", "phones", text,
                      "packaging", "unopened")
        assert not check_g5([doc])[0].passed, text


def test_g5_fails_a_corpus_with_no_policy_documents():
    """F7: a v1 corpus that lost its policy copy must not pass G5 as "0/0 clean"."""
    product = {"doc_id": "product-phones-b0000000001", "title": "Phone", "category": "phones"}
    g5, counts = check_g5([product])
    assert not g5.passed and counts["offending_documents"] == 0


def test_the_gate_runs_g5_in_stage_1_and_stops_on_it(tmp_path, monkeypatch, capsys):
    """F8: G5 is wired into the gate itself, not only into make policy-check."""
    import corpus_gate

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "policy-return-electronics.json").write_text(json.dumps(
        _policy("policy-return-electronics", "return", "electronics", "Opened TVs carry a fee.")))
    workload = tmp_path / "workload.json"
    workload.write_text(json.dumps([{"question": "How long is the return window for TVs?"}]))
    monkeypatch.setattr("sys.argv", ["corpus_gate.py", "--corpus-dir", str(corpus),
                                     "--workload", str(workload), "--structural-only"])
    assert corpus_gate.main() == 1
    out = capsys.readouterr().out
    assert "[FAIL] G5" in out and "STOP" in out


# =================================================================================================
# Item 3.4 -- the workload's shape, its split files, K per run file, scoped stage 2
# (docs/work/2026-10-21-workload-generator/design.md §2.7 and §5; tests T2, T14, T17, T18, T24)
# =================================================================================================
def _w(qa_id, question, split, stratum="A", cluster_id="", pair_of="", probe_kind="",
       product_id="product-phones-x1"):
    return Query(qa_id=qa_id, question=question, split=split, stratum=stratum,
                 cluster_id=cluster_id or f"c-{qa_id}", pair_of=pair_of, probe_kind=probe_kind,
                 product_id=product_id)


def _good_workload():
    return [
        _w("v1", "How heavy is the Galaxy A10e?", "validation", cluster_id="c1"),
        _w("v2", "What does the Galaxy A10e weigh?", "validation", stratum="C", cluster_id="c1"),
        _w("v3", "How heavy is the Moto G7?", "validation", stratum="B-cross", pair_of="v1",
           probe_kind="name-swap", product_id="product-phones-x2"),
        _w("t1", "How long is the warranty on the Pixel 3?", "test", stratum="C",
           product_id="product-phones-x3"),
        _w("t2", "How long is the return window on the Pixel 3?", "test", stratum="B-within",
           pair_of="t1", probe_kind="policy-kind", product_id="product-phones-x3"),
    ]


def test_a_well_formed_workload_passes_the_shape_check():
    """T17: the shape check passes what the builder is meant to write."""
    shape = check_workload_shape(_good_workload())
    assert shape.passed, shape.detail
    assert "validation=3 test=2" in shape.summary


def test_the_shape_check_names_a_cluster_that_spans_both_splits():
    """T2 / W2: a cluster split in two leaks its paraphrases into test."""
    queries = _good_workload()
    queries[1].split = "test"  # v2 shares cluster c1 with v1, which stays in validation
    shape = check_workload_shape(queries)
    assert not shape.passed
    assert any("cluster c1 spans" in d for d in shape.detail)


def test_the_shape_check_names_a_probe_split_from_its_target():
    """T2 / W2: a probe in one split file and its target in the other is a trap no run contains."""
    queries = _good_workload()
    queries[4].split = "validation"  # t2 is built against t1, which stays in test
    queries[4].cluster_id = "c-t2"
    shape = check_workload_shape(queries)
    assert not shape.passed
    assert any("t2 (validation) is built against t1 (test)" in d for d in shape.detail)


@pytest.mark.parametrize(
    "field,value",
    [("stratum", ""), ("stratum", "B"), ("split", ""), ("split", "train"), ("cluster_id", "")],
)
def test_the_shape_check_needs_one_stratum_split_and_cluster_per_record(field, value):
    """W1: every record carries exactly one of each, from the allowed values."""
    queries = _good_workload()
    setattr(queries[0], field, value)
    shape = check_workload_shape(queries)
    assert not shape.passed
    assert any(d.startswith("v1:") for d in shape.detail)


def test_the_shape_check_fails_one_tier1_form_even_across_products():
    """W5 is stricter than G3: G3 partitions by product_id, W5 does not, so the offline join on
    `query_normalized` stays exact whether or not a run sends product_id."""
    queries = _good_workload()
    queries.append(_w("t3", "how heavy is the GALAXY A10e", "test",
                      product_id="product-phones-x9"))
    assert check_g3(queries)[0].passed
    shape = check_workload_shape(queries)
    assert not shape.passed
    assert any("v1, t3" in d for d in shape.detail)


def test_the_shape_check_fails_an_empty_split_a_dangling_probe_and_a_reused_id():
    queries = [q for q in _good_workload() if q.split == "validation"]
    queries[2].pair_of = "nowhere"
    queries.append(_w("v1", "Is the Galaxy A10e waterproof?", "validation"))
    shape = check_workload_shape(queries)
    text = "\n".join(shape.detail)
    assert "split 'test' holds no record" in text
    assert "pair_of nowhere names no record" in text
    assert "qa_id v1 is used by 2 records" in text


def test_the_shape_check_caps_each_kind_of_problem():
    queries = [_w(f"q{i}", f"question number {i}", "validation", stratum="") for i in range(25)]
    shape = check_workload_shape(queries)
    stratum_lines = [d for d in shape.detail if "stratum" in d]
    assert len(stratum_lines) == 11 and stratum_lines[-1].startswith("... and 15 more")


def test_k_and_the_trap_fraction_are_per_run_file():
    """T14 / impact F1: a run's capacity is round(0.25 * K) of the file it draws from."""
    assert k_per_run_file(_good_workload()) == {"whole": 5, "validation": 3, "test": 2}


def test_the_trap_fraction_leaves_out_a_same_answer_name_swap():
    """design.md §2.4: name-swap-same measures what the namespace costs and is not a trap."""
    queries = [
        Query("a", "?", stratum="A"),
        Query("b", "?", stratum="B-cross", probe_kind="name-swap"),
        Query("c", "?", stratum="B-cross", probe_kind="name-swap-same"),
        Query("d", "?", stratum="B-within", probe_kind="policy-condition"),
    ]
    assert trap_fraction(queries) == 0.5


def test_load_workload_reads_the_new_fields_and_treats_null_as_empty(tmp_path):
    path = tmp_path / "workload-v1.json"
    path.write_text(json.dumps([
        {"qa_id": "t2", "question": "How long is the return window on the Pixel 3?",
         "doc_ids": ["policy-return-phones-unopened"], "product_id": None, "stratum": "B-within",
         "split": "test", "cluster_id": "c3", "pair_of": "t1", "probe_kind": "policy-kind"},
        {"question": "Bare record", "pair_of": None, "doc_ids": None},
    ]))
    a, b = load_workload(path)
    assert (a.split, a.cluster_id, a.pair_of, a.probe_kind, a.product_id) == (
        "test", "c3", "t1", "policy-kind", "")
    assert (b.qa_id, b.pair_of, b.doc_ids, b.split) == ("q0001", "", (), "")


# --- the split files (impact F2, review L4; T18) --------------------------------------------------
def _records():
    """The whole file, deliberately NOT in rank order, so the derivation must sort."""
    def rec(qa_id, question, split, rank, stratum="A", cluster="c1", pair_of=None):
        return {"qa_id": qa_id, "question": question, "doc_ids": ["product-phones-x1"],
                "product_id": "product-phones-x1", "stratum": stratum, "split": split,
                "cluster_id": cluster, "pair_of": pair_of, "probe_kind": None,
                "popularity_rank": rank}

    return [
        rec("v1", "How heavy is the Galaxy A10e?", "validation", 2),
        rec("v2", "What does the Galaxy A10e weigh?", "validation", 1),
        rec("t1", "How long is the battery life of the Galaxy A10e?", "test", 1, "C", "c2"),
        rec("t2", "Does the Galaxy A10e have a headphone jack?", "test", 2, "B-within", "c3", "t1"),
    ]


def _write_workload(directory, records, splits=("validation", "test")):
    whole = directory / "workload-v1.json"
    whole.write_text(json.dumps(records))
    for s in splits:
        split_path(whole, s).write_text(json.dumps(derive_split(records, s)))
    return whole


def test_split_files_are_found_by_name_beside_the_whole_file():
    whole = Path("data/workload-v1.json")
    assert split_path(whole, "validation") == Path("data/workload-v1-validation.json")
    assert split_path(whole, "test") == Path("data/workload-v1-test.json")


def test_derive_split_orders_by_popularity_rank():
    assert [r["qa_id"] for r in derive_split(_records(), "validation")] == ["v2", "v1"]


@pytest.mark.parametrize("bad", [None, 3, True, "1"])
def test_derive_split_needs_ranks_exactly_one_to_n(bad):
    records = _records()
    records[0]["popularity_rank"] = bad
    with pytest.raises(ValueError, match="popularity_rank"):
        derive_split(records, "validation")


def test_split_files_that_match_the_whole_file_pass(tmp_path):
    whole = _write_workload(tmp_path, _records())
    result = check_split_files(whole)
    assert result.passed, result.detail


def test_a_missing_split_file_fails(tmp_path):
    """T18: the gate fails on a missing split file rather than hashing two files of three."""
    whole = _write_workload(tmp_path, _records(), splits=("validation",))
    result = check_split_files(whole)
    assert not result.passed
    assert result.detail == ["no split file at workload-v1-test.json"]


def test_a_reordered_split_file_fails_and_changes_the_digest(tmp_path):
    """T18: a re-sorted split file is a different workload under the same name. The gate fails
    it, and the digest over the three files moves with it."""
    import corpus_gate

    whole = _write_workload(tmp_path, _records())
    files = [whole] + [split_path(whole, s) for s in ("validation", "test")]
    original_root = corpus_gate.REPO_ROOT
    corpus_gate.REPO_ROOT = tmp_path
    try:
        before, _ = snapshot_digest(files)
        test_file = split_path(whole, "test")
        test_file.write_text(json.dumps(list(reversed(json.loads(test_file.read_text())))))
        after, _ = snapshot_digest(files)
    finally:
        corpus_gate.REPO_ROOT = original_root
    assert before != after
    result = check_split_files(whole)
    assert not result.passed
    assert "workload-v1-test.json differs" in result.detail[0] and "position 1" in result.detail[0]


def test_a_split_file_with_an_edited_record_fails(tmp_path):
    records = _records()
    whole = _write_workload(tmp_path, records)
    stale = derive_split(records, "validation")
    stale[1]["stratum"] = "C"
    split_path(whole, "validation").write_text(json.dumps(stale))
    result = check_split_files(whole)
    assert not result.passed and "position 2" in result.detail[0]


def test_the_gate_prints_k_and_capacity_per_run_file_and_passes_a_good_workload(
    tmp_path, monkeypatch, capsys
):
    """T14 and T17: stage 1 end to end on a well-formed workload and a clean corpus."""
    import corpus_gate

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "policy-return-electronics.json").write_text(json.dumps(
        _policy("policy-return-electronics", "return", "electronics",
                "Items go back within 30 days.")))
    (corpus / "product-phones-x1.json").write_text(json.dumps({"doc_id": "product-phones-x1"}))
    whole = _write_workload(tmp_path, _records())
    monkeypatch.setattr("sys.argv", ["corpus_gate.py", "--corpus-dir", str(corpus),
                                     "--workload", str(whole), "--structural-only"])
    assert corpus_gate.main() == 0
    out = capsys.readouterr().out
    assert "whole K=4 capacity=1" in out
    assert "validation K=2 capacity=0" in out and "test K=2 capacity=0" in out
    assert "[PASS] W   workload shape" in out and "[PASS] S   split files" in out


# --- stage 2: scoped retrieval, pairs per split (review H3, impact F3; T24) ------------------------
def test_stage_2_retrieves_scoped_by_each_querys_product_id():
    """T24: G1 and G2 must measure the retrieval a run does, and a run sends product_id."""
    scoped_calls, unscoped_calls = [], []
    queries = [Query("a", "How heavy is it?", product_id="product-phones-x1"),
               Query("b", "How long is the return window?")]
    retrieve_all(
        queries,
        embed=lambda text: [1.0, 0.0],
        retrieve_scoped=lambda text, pid: scoped_calls.append((text, pid)) or [f"s-{pid}"],
        retrieve_unscoped=lambda text: unscoped_calls.append(text) or ["u"],
        progress=lambda _: None,
    )
    assert scoped_calls == [("How heavy is it?", "product-phones-x1"),
                            ("How long is the return window?", None)]
    assert unscoped_calls == ["How heavy is it?", "How long is the return window?"]
    assert queries[0].retrieved == ("s-product-phones-x1",)
    assert queries[0].retrieved_unscoped == ("u",)


def test_find_pairs_reads_the_unscoped_retrieval_only_when_asked():
    same = [1.0, 0.0]
    a = Query("a", "x", product_id="p1", embedding=same, retrieved=("c1",),
              retrieved_unscoped=("c9",))
    b = Query("b", "y", product_id="p1", embedding=same, retrieved=("c2",),
              retrieved_unscoped=("c9",))
    similar = similar_pairs([a, b])
    assert len(find_pairs([a, b], similar)[0]) == 1  # scoped: two chunks apart, a G1 pair
    assert find_pairs([a, b], similar, unscoped=True)[0] == []  # unscoped: one chunk shared


def test_similar_pairs_gives_the_cosine_bit_for_bit():
    """The shared pass computes each norm once; it must still give cosine()'s exact value, or a
    pair at the floor could pass one and fail the other."""
    import random

    rng = random.Random(7)
    vecs = [[rng.uniform(-1, 1) for _ in range(16)] for _ in range(4)]
    vecs[1] = [x + rng.uniform(-0.05, 0.05) for x in vecs[0]]
    queries = [Query(f"q{i}", "?", embedding=v) for i, v in enumerate(vecs)]
    found = similar_pairs(queries)
    assert found, "the fixture must hold a pair above the floor"
    for i, j, sim in found:
        assert sim == cosine(vecs[i], vecs[j])


def test_g1_and_g2_count_only_pairs_inside_one_split():
    """Impact F3: two queries in different split files never meet in one run's cache."""
    queries = [Query("v1", "x", split="validation", product_id="p1"),
               Query("v2", "y", split="validation", product_id="p1"),
               Query("t1", "z", split="test", product_id="p1")]
    pairs = [Pair("v1", "v2", 0.9, 0.0, "B-within"), Pair("v1", "t1", 0.9, 0.0, "B-within")]
    within, across = split_pairs(pairs, queries)
    assert [p.right for p in within["validation"]] == ["v2"]
    assert within["test"] == [] and [p.right for p in across] == ["t1"]
    assert check_g2(within["validation"], scope="validation").passed
    g2_test = check_g2(within["test"], scope="test")
    assert not g2_test.passed and g2_test.name.endswith("(test)")
    assert check_g1(within["validation"], scope="within split").name.endswith("(within split)")


def test_the_digest_covers_the_corpus_and_all_three_workload_files(tmp_path):
    """Impact F2: the freeze record names every file a run can draw from."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "product-phones-x1.json").write_text("{}")
    whole = _write_workload(tmp_path, _records())
    names = [p.name for p in freeze_files(corpus, whole)]
    assert names == ["product-phones-x1.json", "workload-v1.json", "workload-v1-validation.json",
                     "workload-v1-test.json"]
