"""Item 6.0a (ADR-030), done condition 7: the Python side of contracts/scope/cases.json.

Go (reuse/scope.go) reads the same file in gateway/internal/reuse/scope_contract_test.go. The tokenizer
builds the bound-word lists here and tests answers there; the projection calibrates tau_P here and
serves there. Nothing in either build makes the two agree, and a difference is silent, so both sides
assert against this one file.
"""

import json
import math
from pathlib import Path

import pytest
import scope_calibrate as sc

from rag import docmeta

CASES = json.loads(
    (
        Path(__file__).resolve().parents[2] / "contracts" / "scope" / "cases.json"
    ).read_text()
)


def test_the_contract_is_the_one_this_test_asserts():
    assert CASES["contract"] == "scope-by-evidence"
    # an empty list would pass vacuously on both sides
    assert (
        len(CASES["tokenize"]) >= 8
        and len(CASES["scope"]) >= 8
        and len(CASES["project"]) >= 6
    )


@pytest.mark.parametrize("case", CASES["tokenize"], ids=lambda c: c["name"])
def test_scope_tokens_meets_every_tokenize_case(case):
    assert sorted(docmeta.scope_tokens(case["in"])) == case["out"]


@pytest.mark.parametrize("case", CASES["project"], ids=lambda c: c["name"])
def test_the_projection_meets_every_project_case(case):
    got = sc.project(case["v"], case["t"])
    if case["out"] is None:
        assert got is None
        return
    assert got is not None
    assert max(abs(a - b) for a, b in zip(got, case["out"], strict=True)) <= case["tol"]


@pytest.mark.parametrize(
    "case",
    [c for c in CASES["project"] if c["out"] is not None],
    ids=lambda c: c["name"],
)
def test_a_projected_vector_is_unit_and_orthogonal_to_t(case):
    got = sc.project(case["v"], case["t"])
    norm_t = math.sqrt(sum(x * x for x in case["t"]))
    assert abs(math.sqrt(sum(x * x for x in got)) - 1) < 1e-6
    assert abs(sum(a * b / norm_t for a, b in zip(got, case["t"], strict=True))) < 1e-6


def test_every_scope_case_answer_tokenizes_without_error():
    # the Go test decides the scope; here the answers are only checked to be usable text
    for case in CASES["scope"]:
        assert isinstance(docmeta.scope_tokens(case["answer"]), set)
        assert case["out"] in ("product", "shared")


# --- bound_words (docmeta) ---------------------------------------------------------------------


def df_for(products):
    df = {}
    for tokens in products:
        for t in tokens:
            df[t] = df.get(t, 0) + 1
    return df


def test_a_word_in_the_categorys_policies_is_not_bound():
    products = [{"bravia", "tv", "hdmi"}] + [{"other"} for _ in range(19)]
    df = df_for(products)
    got = docmeta.bound_words(products[0], {"tv"}, df, 20)
    assert (
        "tv" not in got
    )  # in the category's policy documents: a neutral answer may say it
    assert got == ["bravia", "hdmi"]


def test_a_word_above_the_cut_is_not_bound():
    # 20 products; "hdmi" is in 3 of them (15 %, above the 10 % cut), "bravia" in 1 (5 %)
    products = [{"bravia", "hdmi"}, {"hdmi"}, {"hdmi"}] + [{"other"} for _ in range(17)]
    df = df_for(products)
    assert docmeta.bound_words(products[0], set(), df, 20) == ["bravia"]


def test_a_word_at_exactly_the_cut_is_bound():
    # "hdmi" is in 2 of 20 products: exactly 10 %, so it stays bound (at most the cut)
    products = [{"bravia", "hdmi"}, {"hdmi"}] + [{"other"} for _ in range(18)]
    df = df_for(products)
    assert docmeta.bound_words(products[0], set(), df, 20) == ["bravia", "hdmi"]


def test_bound_words_are_sorted_and_unique():
    got = docmeta.bound_words(
        ["zeta", "alpha", "alpha"], set(), {"zeta": 1, "alpha": 1}, 100
    )
    assert got == ["alpha", "zeta"]


def test_the_cut_is_pinned_at_ten_percent():
    assert docmeta.CUT == 0.10 and sc.CUT == 0.10


def test_product_text_uses_the_title_and_the_spec_values_never_the_keys():
    text = docmeta.product_text(
        {"title": "Sony Bravia", "specs": {"Feature 1": "Panel 1080p", "Brand": "Sony"}}
    )
    tokens = docmeta.scope_tokens(text)
    assert {"sony", "bravia", "panel", "1080p"} <= tokens
    assert "feature" not in tokens and "brand" not in tokens


def test_build_on_the_real_corpus_gives_every_document_a_category():
    rows = docmeta.build()
    assert len(rows) == 164
    assert all(r["category"] for r in rows)
    products = [r for r in rows if r["kind"] == "product"]
    assert len(products) == 152
    assert all(isinstance(r["bound_words"], list) for r in products)
