"""Tests for probe_checks.py (plan step 12), on synthetic data.

    python3 -m pytest docs/work/2026-10-22-corpus-freeze/tools -q

These are not part of `make test`: the tool lives in the task trail. Every id and text here is made
up; none looks like an asin.
"""

import json
from pathlib import Path

import probe_checks as pc
import pytest

REPO = pc.REPO
corpus_gate = pc.corpus_gate  # probe_checks puts experiments/scripts on sys.path


# =================================================================================================
# Evidence span -> chunks
# =================================================================================================
@pytest.mark.parametrize(
    "text",
    ["a b", "  lead and trail  ", "tabs\tand\nnewlines  here", "one", "", "   ", "x   y   z"],
)
def test_collapse_with_map_equals_split_join_and_maps_each_character(text):
    collapsed, index = pc.collapse_with_map(text)
    assert collapsed == " ".join(text.split())
    assert len(index) == len(collapsed)
    for ch, i in zip(collapsed, index, strict=True):
        assert text[i].isspace() if ch == " " else text[i] == ch


DOC = "Weight: 170 g.  Battery: 4000 mAh,\nlasts two days.  Colour: black."
#      0         1         2         3         4         5
CHUNKS = [("d#chunk-0", 0, 38), ("d#chunk-1", 30, len(DOC))]  # they overlap on [30, 38)


def test_a_span_inside_one_chunk_touches_only_it():
    assert pc.evidence_chunks(DOC, CHUNKS, "Weight: 170 g.") == ["d#chunk-0"]
    assert pc.evidence_chunks(DOC, CHUNKS, "Colour: black.") == ["d#chunk-1"]


def test_a_span_in_the_overlap_or_across_the_boundary_touches_both():
    assert DOC[30:38] in DOC
    assert pc.evidence_chunks(DOC, CHUNKS, DOC[30:38].strip()) == ["d#chunk-0", "d#chunk-1"]
    assert pc.evidence_chunks(DOC, CHUNKS, "4000 mAh, lasts two days.") == ["d#chunk-0", "d#chunk-1"]


def test_evidence_is_found_whatever_its_whitespace():
    assert pc.evidence_chunks(DOC, CHUNKS, "Battery:   4000 mAh,\n lasts two days.") is not None
    assert pc.evidence_chunks(DOC, CHUNKS, "") is None
    assert pc.evidence_chunks(DOC, CHUNKS, "   ") is None


def test_evidence_that_is_not_in_the_document_is_none_not_empty():
    assert pc.evidence_chunks(DOC, CHUNKS, "Weight: 171 g.") is None


def test_chunk_geometry_gives_ingests_own_chunks_and_a_span_is_found_in_them(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    sentences = [f"Clause {i} applies within thirty days." for i in range(60)]
    (corpus / "policy-test.json").write_text(
        json.dumps({"doc_id": "policy-test", "title": "T", "category": "c", "text": " ".join(sentences)})
    )
    texts, chunks = pc.chunk_geometry(corpus)
    assert len(chunks["policy-test"]) > 1
    first = pc.evidence_chunks(texts["policy-test"], chunks["policy-test"], sentences[0])
    last = pc.evidence_chunks(texts["policy-test"], chunks["policy-test"], sentences[-1])
    assert first[0] == "policy-test#chunk-0" and last[-1] == chunks["policy-test"][-1][0]
    assert first != last


def test_evidence_chunk_sets_counts_what_it_could_not_place():
    spans = {
        "a": {"doc_id": "d", "evidence": "Weight: 170 g."},
        "b": {"doc_id": "d", "evidence": "nowhere in the text"},
        "c": {"doc_id": "gone", "evidence": "x"},
        "e": {"doc_id": "d", "evidence": "4000 mAh, lasts two days."},
    }
    sets, counts = pc.evidence_chunk_sets(spans, {"d": DOC}, {"d": CHUNKS})
    assert sets["a"] == ["d#chunk-0"] and sets["b"] is None and sets["c"] is None
    assert counts["located"] == 2 and counts["not located in the document text"] == 1
    assert counts["the span's document is not in the corpus"] == 1
    assert counts["located, over more than one chunk"] == 1


# =================================================================================================
# A small synthetic workload and its retrieval
# =================================================================================================
def rec(qa_id, split="validation", role="seed", kind=None, pair_of=None, docs=("product-a",)):
    return {"qa_id": qa_id, "split": split, "role": role, "probe_kind": kind, "pair_of": pair_of,
            "doc_ids": list(docs), "stratum": "A"}


def row(scoped, unscoped=None):
    unscoped = scoped if unscoped is None else unscoped
    return {"scoped": scoped, "unscoped": unscoped, "n_scoped": len(scoped), "n_unscoped": len(unscoped)}


RECORDS = [
    rec("s1"),
    rec("p1", role="probe", kind="spec-attribute", pair_of="s1"),
    rec("s2", docs=("product-b",)),
    rec("s3", docs=("product-c",)),
    rec("p2", role="probe", kind="name-swap", pair_of="s2", docs=("product-a",)),
    rec("t1", role="probe", kind="policy-condition", pair_of="t2", docs=("policy-r-opened",)),
    rec("t2", role="probe", kind="policy-condition", pair_of="t1", docs=("policy-r-sealed",)),
    rec("d1", role="d", docs=("product-a", "policy-w")),
    rec("x1", split="test"),
    rec("x2", split="test", role="probe", kind="spec-attribute", pair_of="x1"),
]
RETRIEVAL = {
    "validation": {
        "s1": row(["product-a#chunk-0", "product-a#chunk-1"]),
        "p1": row(["product-a#chunk-1", "product-a#chunk-2", "product-a#chunk-3"]),
        "s2": row(["product-b#chunk-0"]),
        "s3": row(["product-c#chunk-0"]),
        "p2": row(["product-a#chunk-0", "policy-w#chunk-0"]),
        "t1": row(["policy-r-opened#chunk-0", "policy-r-opened#chunk-1", "policy-r-sealed#chunk-0"]),
        "t2": row(["policy-r-sealed#chunk-0", "product-a#chunk-0", "product-a#chunk-1"]),
        "d1": row(["product-a#chunk-0", "policy-w#chunk-0", "policy-w#chunk-1", "policy-x#chunk-0", "policy-y#chunk-0"]),
    },
    "test": {"x1": row(["product-a#chunk-0"]), "x2": row(["product-a#chunk-0"])},
}


def test_set_sizes_are_counted_per_split():
    sizes = pc.size_distribution(RECORDS, RETRIEVAL, "validation")
    assert sizes["scoped"] == {1: 2, 2: 2, 3: 3, 5: 1}
    assert pc.size_distribution(RECORDS, RETRIEVAL, "test")["scoped"] == {1: 2}


def test_u12a_bins_the_jaccard_of_each_probe_with_its_partner():
    out = pc.u12a(RECORDS, RETRIEVAL, "validation")
    # p1 against s1 shares chunk-1: 1 of 4 = 0.25; p2 against s2 shares nothing; t1 and t2 share 1 of 5
    assert out["spec-attribute"]["bins"] == {"(0.2, 0.5]": 1} and out["spec-attribute"]["median"] == 0.25
    assert out["name-swap"]["bins"] == {"0": 1}
    assert out["policy-condition"]["n"] == 2
    assert pc.u12a(RECORDS, RETRIEVAL, "test")["spec-attribute"]["bins"] == {"1": 1}


def test_u12a_counts_a_probe_whose_partner_is_in_the_other_split():
    records = [rec("a"), rec("b", split="test", role="probe", kind="natural", pair_of="a")]
    retrieval = {"validation": {"a": row(["c"])}, "test": {"b": row(["c"])}}
    assert pc.u12a(records, retrieval, "test")["natural"]["no partner in this split"] == 1


def test_u12b_says_share_disjoint_or_no_span_and_does_not_read_the_retrieval():
    evidence = {"s1": ["d#chunk-0"], "p1": ["d#chunk-0", "d#chunk-1"], "s2": ["e#chunk-0"],
                "p2": ["d#chunk-5"], "x1": ["d#chunk-0"], "x2": None}
    flags, table = pc.u12b(RECORDS, evidence)
    assert flags["p1"] == {"partner": "s1", "shares_chunk": True}
    assert flags["p2"]["shares_chunk"] is False
    assert flags["t2"]["shares_chunk"] is None  # a policy cell has no span
    assert flags["x2"]["shares_chunk"] is None  # a span that was not found
    assert table["validation"]["spec-attribute"]["share a chunk"] == 1
    assert table["validation"]["name-swap"]["disjoint"] == 1
    assert table["validation"]["policy-condition"]["no span"] == 2
    assert list(flags) == sorted(flags)


def test_u11_is_any_and_all_over_a_span_that_crosses_two_chunks():
    evidence = {"s1": ["product-a#chunk-0", "product-a#chunk-1"], "s2": ["product-b#chunk-9"], "s3": None}
    out = pc.u11(RECORDS, RETRIEVAL, evidence, "validation")
    assert out["seeds with an evidence span"] == 3
    assert out["span located"] == 2 and out["span not located"] == 1 and out["span over more than one chunk"] == 1
    assert out["any chunk of the span in the scoped top-k"] == 1  # s1 (both chunks) ; s2 misses
    assert out["all chunks of the span in the scoped top-k"] == 1
    evidence["s1"] = ["product-a#chunk-1", "product-a#chunk-7"]  # one retrieved, one not
    out = pc.u11(RECORDS, RETRIEVAL, evidence, "validation")
    assert out["any chunk of the span in the scoped top-k"] == 1
    assert out["all chunks of the span in the scoped top-k"] == 0


# --- lane.go ----------------------------------------------------------------------------------------
def test_policy_fraction_mirrors_the_gateways():
    assert pc.policy_fraction([]) == 0
    assert pc.policy_fraction(["product-a#chunk-0"]) == 0
    assert pc.policy_fraction(["policy-a#chunk-0", "product-a#chunk-0"]) == 0.5
    assert pc.policy_fraction(["policy-a#chunk-0"] * 3 + ["product-a#chunk-0"] * 2) == 0.6


@pytest.mark.parametrize(
    "frac,collapsed,candidate",
    [(0.0, "SPEC", "SPEC"), (0.2, "POLICY", "MIXED"), (0.4, "POLICY", "MIXED"),
     (0.6, "POLICY", "POLICY"), (0.8, "POLICY", "POLICY"), (1.0, "POLICY", "POLICY")],
)
def test_classify_mirrors_lane_go_under_both_bands(frac, collapsed, candidate):
    assert pc.classify(frac, 0.2, 0.2) == collapsed
    assert pc.classify(frac, 0.2, 0.6) == candidate


def test_an_empty_retrieval_is_spec_in_every_band():
    assert pc.classify(0.0, 0.2, 0.6, empty=True) == "SPEC"


def test_u10_groups_the_queries_and_applies_both_bands():
    out = pc.u10(RECORDS, RETRIEVAL, "validation")
    assert out["policy queries"]["n"] == 2  # t1 and t2
    assert out["policy queries"]["policy_frac"] == {1.0: 1, 0.333: 1}
    assert out["D queries (a product and a policy)"]["policy_frac"] == {0.8: 1}
    lanes = out["D queries (a product and a policy)"]["lanes"]
    assert lanes["default, collapsed (Lo = Hi = 0.20)"] == {"POLICY": 1}
    assert lanes["candidate [0.20, 0.60)"] == {"POLICY": 1}
    assert out["policy queries"]["lanes"]["candidate [0.20, 0.60)"] == {"POLICY": 1, "MIXED": 1}
    assert out["product-only queries"]["n"] == 5  # s1 p1 s2 s3 p2


# --- the two refusals ----------------------------------------------------------------------------------
@pytest.mark.parametrize("check", [pc.u10, pc.sibling_rate])
def test_u10_and_the_sibling_rate_refuse_the_test_split(check):
    with pytest.raises(pc.Refused, match="validation only"):
        check(RECORDS, RETRIEVAL, "test")


@pytest.mark.parametrize("check", [pc.u10, pc.sibling_rate])
def test_a_validation_export_that_holds_test_rows_is_refused(check):
    smuggled = {"validation": {**RETRIEVAL["validation"], "x1": row(["product-a#chunk-0"])}}
    with pytest.raises(pc.Refused, match="not validation records"):
        check(RECORDS, smuggled, "validation")


def test_load_export_refuses_a_file_that_holds_the_other_splits_rows(tmp_path):
    for split in pc.SPLITS:
        (tmp_path / f"retrieval-{split}.json").write_text(
            json.dumps([{"qa_id": "x1", **RETRIEVAL["test"]["x1"]}])
        )
    with pytest.raises(pc.Refused, match="other split"):
        pc.load_export(tmp_path, RECORDS)


def test_load_export_reads_the_two_files_by_split(tmp_path):
    for split in pc.SPLITS:
        rows = [{"qa_id": q, **v} for q, v in RETRIEVAL[split].items()]
        (tmp_path / f"retrieval-{split}.json").write_text(json.dumps(rows))
    loaded = pc.load_export(tmp_path, RECORDS)
    assert set(loaded["validation"]) == set(RETRIEVAL["validation"]) and set(loaded["test"]) == {"x1", "x2"}


def test_sibling_rate_counts_the_other_twins_document_in_the_top_k():
    out = pc.sibling_rate(RECORDS, RETRIEVAL, "validation")
    # t1 (opened) holds a chunk of its own and of the sealed twin's document; t2 (sealed) holds only its own
    assert out["twin records"] == 2
    assert out["top-k holds a chunk of its own document"] == 2
    assert out["top-k holds a chunk of the other twin's document"] == 1
    assert out["top-k holds both"] == 1
    assert out["top-k holds the other twin's document and not its own"] == 0


# =================================================================================================
# The numeric unit list
# =================================================================================================
def test_the_parser_reads_the_real_unit_list_the_way_the_go_test_pins_it():
    units, alias, currency = pc.go_unit_list(pc.GO_NUMERIC.read_text())
    assert len(units) == 35 and {"day", "month", "year", "g", "percent"} <= units
    assert len(alias) == 15 and alias["hrs"] == "hour" and alias["feet"] == "ft"
    assert currency == "$€£"


@pytest.mark.parametrize(
    "word,want", [("days", "day"), ("day", "day"), ("hrs", "hour"), ("vs", None), ("v", "v"), ("weeks", "week"),
                  ("fortnight", None), ("feet", "ft")],
)
def test_canon_unit_drops_a_plural_s_only_when_two_letters_remain(word, want):
    units, alias, _ = pc.go_unit_list(pc.GO_NUMERIC.read_text())
    assert pc.canon_unit(word, units, alias) == want


def test_unit_check_reads_each_kind_of_term(tmp_path):
    terms = ["30 days", "1 year", "10 years", "12 months", "$45", "not covered", "7 fortnights", "14"]
    (tmp_path / "policy-t.json").write_text(json.dumps({"terms": terms}))
    out = pc.unit_check(tmp_path, pc.GO_NUMERIC.read_text())
    assert out["counts"] == {
        "policy terms": 8, "terms read by a listed unit": 4, "terms read by a currency symbol": 1,
        "terms without a number": 1, "terms with a number and no listed unit": 2,
    }
    assert out["unlisted words"] == {"fortnights": 1, "(none)": 1}


def test_the_real_policy_terms_are_all_read():
    out = pc.unit_check(REPO / "data" / "policies-v1", pc.GO_NUMERIC.read_text())
    assert out["counts"]["policy terms"] > 0
    assert "terms with a number and no listed unit" not in out["counts"]


# =================================================================================================
# The whole run, the rendering and the flag file
# =================================================================================================
def _run(tmp_path, flags_name="flags.json"):
    spans = {"s1": {"doc_id": "d", "evidence": "Weight: 170 g."}, "p1": {"doc_id": "d", "evidence": "Colour: black."}}
    return pc.run(RECORDS, RETRIEVAL, spans, {"d": DOC}, {"d": CHUNKS}, REPO / "data" / "policies-v1",
                  pc.GO_NUMERIC.read_text(), tmp_path / flags_name)


def test_a_synthetic_run_produces_every_table(tmp_path):
    result = _run(tmp_path)
    assert set(result) == {"spans", "sizes", "u12a", "u12b", "flags_sha256", "u11", "u10", "sibling", "units"}
    text = "\n".join(pc.render(result))
    for heading in ("Evidence spans", "Retrieved-set sizes", "U12 (a)", "U12 (b)", "U11", "U10", "Sibling rate",
                    "numeric unit list"):
        assert heading in text


def test_the_rendered_output_holds_no_qa_id_and_no_text(tmp_path):
    text = "\n".join(pc.render(_run(tmp_path)))
    for qa_id in ("s1", "p1", "t1", "x1", "product-a", "policy-r", "Weight", "Colour"):
        assert f"`{qa_id}`" not in text and qa_id not in text.replace("policy_frac", "")


def test_the_flag_file_is_deterministic_and_its_hash_is_the_files(tmp_path):
    first = _run(tmp_path, "one.json")["flags_sha256"]
    second = _run(tmp_path, "two.json")["flags_sha256"]
    assert first == second
    import hashlib

    assert hashlib.sha256((tmp_path / "one.json").read_bytes()).hexdigest() == first
    flags = json.loads((tmp_path / "one.json").read_text())["flags"]
    assert flags["p1"]["shares_chunk"] is False and flags["p2"]["shares_chunk"] is None


def test_the_per_probe_flag_file_is_written_only_where_git_ignores_it():
    corpus_gate.require_git_ignored(pc.FLAGS)  # the default path is under data/v1-draft/
    with pytest.raises(SystemExit, match="not gitignored"):
        pc.write_flags(REPO / "docs" / "work" / "2026-10-22-corpus-freeze" / "flags.json", {})
    assert not (REPO / "docs" / "work" / "2026-10-22-corpus-freeze" / "flags.json").exists()


def test_the_default_output_is_in_the_task_trail():
    assert pc.OUT == Path(REPO / "docs/work/2026-10-22-corpus-freeze/evidence/probe-checks.md")
