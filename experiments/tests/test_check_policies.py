"""Tests for item 3.3's policy checker (docs/work/2026-10-20-policy-documents/design.md §6).

Every check guards a silent failure: a document at 2 chunks gives containment nothing to sweep; a
number the support gate cannot attach to its unit refuses a correct answer; an identical chunk
lets the index's tie order pick the namespace; a broken `category` breaks 3.4's join. None of them
raises anywhere else.

No fixture reads `data/`: records are built inline, and folders live in `tmp_path`.
"""

import itertools
import json

import pytest
from check_policies import (
    DEPARTMENTS,
    MIN_WORDS,
    check_chunks,
    check_schema,
    check_terms,
    derive_doc_id,
    main,
    maker_of,
    source_counts,
    split_chunks,
)
from corpus_gate import check_g5

FILLER = [
    "amber", "birch", "cedar", "delta", "ember", "fable", "garnet", "harbor", "indigo", "juniper",
    "kestrel", "lumen", "maple", "nectar", "olive", "pepper", "quartz", "raven", "sable", "tundra",
    "umber", "velvet", "willow", "xenon", "yarrow", "zephyr", "acorn", "bramble", "clover", "dune",
]  # fmt: skip
SENTENCES = [f"{a} {b}" for a, b in itertools.permutations(FILLER, 2)]


def _filler(doc_id: str, tag: str, words: int) -> str:
    """Distinct prose per document: every sentence carries the document's own tag, so no two
    documents share a chunk, and the start rotates with the doc_id."""
    start = sum(map(ord, doc_id)) % len(SENTENCES)
    out, count, i = [], 0, start
    while count < words:
        sentence = f"Our team handles each {SENTENCES[i % len(SENTENCES)]} {tag} request with care."
        out.append(sentence)
        count += len(sentence.split())
        i += 1
    return "\n\n".join(" ".join(out[j : j + 8]) for j in range(0, len(out), 8))


def policy(kind, category, terms, axis=None, value=None, words=600, **override):
    cond = {"axis": axis, "value": value} if axis else None
    record = {
        "doc_id": None,
        "title": (
            f"{'Return Policy' if kind == 'return' else 'Warranty'} - {category.title()}"
            + (f", {value.title()}" if value else "")
        ),
        "category": category,
        "policy_kind": kind,
        "condition": cond,
        "terms": list(terms),
    }
    record["doc_id"] = derive_doc_id(record)
    tag = " ".join(x for x in (category, value, "refund" if kind == "return" else "repair") if x)
    lead = f"This policy applies to {category} for {' and '.join(terms)}."
    record["text"] = lead + "\n\n" + _filler(record["doc_id"], tag, words)
    record.update(override)
    return record


def full_corpus():
    """The 13-document set of design.md §2, with stand-in warranty terms."""
    return [
        policy("return", "phones", ["14 days"], "packaging", "unopened"),
        policy("return", "phones", ["14 days", "$45"], "packaging", "opened"),
        policy("return", "laptops", ["30 days"], "grade", "new"),
        policy("return", "laptops", ["90 days"], "grade", "renewed"),
        policy("return", "electronics", ["30 days"]),
        policy("return", "furniture", ["365 days"], "packaging", "unopened"),
        policy("return", "furniture", ["180 days"], "packaging", "opened"),
        policy("warranty", "phones", ["1 year"], "region", "domestic"),
        policy("warranty", "phones", ["not covered"], "region", "international"),
        policy("warranty", "laptops", ["1 year"], "region", "domestic"),
        policy("warranty", "laptops", ["90 days"], "region", "international"),
        policy("warranty", "electronics", ["1 year"]),
        policy("warranty", "furniture", ["10 years"]),
    ]


def _write(folder, records):
    folder.mkdir(parents=True, exist_ok=True)
    for r in records:
        (folder / f"{r['doc_id']}.json").write_text(json.dumps(r))


# =================================================================================================
# The whole corpus
# =================================================================================================
def test_the_design_set_passes_every_check():
    records = full_corpus()
    assert check_schema(records) == []
    assert check_terms(records) == []
    assert check_chunks(records, split_chunks(records)) == []
    g5, counts = check_g5(records)
    assert g5.passed, g5.detail
    assert counts == {"split_families": 5, "offending_documents": 0}


def test_main_passes_a_valid_folder_and_fails_a_broken_one(tmp_path):
    _write(tmp_path / "ok", full_corpus())
    assert main(["--dir", str(tmp_path / "ok")]) == 0

    broken = full_corpus()
    broken[0]["text"] += " Opened items are welcome too."  # the unopened document names its sibling
    _write(tmp_path / "bad", broken)
    assert main(["--dir", str(tmp_path / "bad")]) == 1


def test_main_exits_2_on_a_missing_or_empty_folder(tmp_path):
    assert main(["--dir", str(tmp_path / "absent")]) == 2
    (tmp_path / "empty").mkdir()
    assert main(["--dir", str(tmp_path / "empty")]) == 2


# =================================================================================================
# P1, P4, P13 -- chunks
# =================================================================================================
def test_a_two_chunk_document_fails_and_is_named():
    short = policy("return", "electronics", ["30 days"], words=250)
    chunks = split_chunks([short])
    assert len(chunks[short["doc_id"]]) < 3
    assert any(short["doc_id"] in p and "needs >= 3" in p for p in check_chunks([short], chunks))


def test_a_three_chunk_document_passes():
    record = policy("return", "electronics", ["30 days"], words=MIN_WORDS)
    chunks = split_chunks([record])
    assert len(chunks[record["doc_id"]]) >= 3
    assert check_chunks([record], chunks) == []


def test_identical_chunks_in_two_documents_fail():
    a = policy("return", "electronics", ["30 days"])
    b = policy("warranty", "electronics", ["1 year"])
    chunks = {a["doc_id"]: ["30 days here", "same text", "x"], b["doc_id"]: ["1 year", "same  text ", "y"]}
    problems = check_chunks([a, b], chunks)
    assert any("identical" in p for p in problems)


def test_a_main_term_outside_chunk_0_fails():
    record = policy("return", "electronics", ["30 days"])
    chunks = {record["doc_id"]: ["no term here", "within 30 days", "z"]}
    assert any("chunk 0" in p for p in check_chunks([record], chunks))


# =================================================================================================
# P3 -- schema
# =================================================================================================
@pytest.mark.parametrize(
    "override,needle",
    [
        ({"category": "phone"}, "category"),
        ({"policy_kind": "returns"}, "policy_kind"),
        ({"condition": {"axis": "colour", "value": "red"}}, "condition axis"),
        ({"condition": {"axis": "packaging", "value": "used"}}, "condition value"),
        ({"doc_id": "policy-returns-electronics"}, "derived"),
        ({"title": "Return Policy – Electronics"}, "ASCII"),
        ({"shipping": "free"}, "fields"),
    ],
)
def test_a_schema_fault_fails(override, needle):
    records = full_corpus()
    records[4] = {**records[4], **override}  # the electronics return document
    problems = check_schema(records)
    assert any(needle in p for p in problems), problems


def test_a_missing_field_fails():
    records = full_corpus()
    del records[4]["terms"]
    assert any("missing ['terms']" in p for p in check_schema(records))


def test_a_split_family_with_one_value_only_fails():
    records = [r for r in full_corpus() if r["doc_id"] != "policy-return-phones-opened"]
    assert any("complete split" in p for p in check_schema(records))


def test_a_department_without_a_warranty_document_fails():
    records = [r for r in full_corpus() if r["doc_id"] != "policy-warranty-furniture"]
    assert any("no warranty document for furniture" in p for p in check_schema(records))


def test_a_title_that_does_not_name_its_value_fails():
    records = full_corpus()
    records[1]["title"] = "Return Policy - Phones"
    assert any("title does not name" in p for p in check_schema(records))


def test_word_count_outside_the_band_fails():
    records = full_corpus()
    records[4] = policy("return", "electronics", ["30 days"], words=900)
    assert any("outside" in p for p in check_schema(records))


def test_departments_come_from_the_builder():
    assert DEPARTMENTS == ("phones", "laptops", "electronics", "furniture")


# =================================================================================================
# P12 -- terms and numbers
# =================================================================================================
def _with_text(record, extra):
    return {**record, "text": record["text"] + " " + extra}


@pytest.mark.parametrize(
    "extra,needle",
    [
        ("Refunds arrive in 5 business days.", "numbers outside"),
        ("Coverage lasts one year.", "in words"),
        ("Coverage lasts a year.", "in words"),
    ],
)
def test_a_stray_number_fails(extra, needle):
    records = full_corpus()
    records[4] = _with_text(records[4], extra)
    assert any(needle in p for p in check_terms(records))


def test_a_term_written_differently_fails():
    record = policy("return", "electronics", ["30 days"])
    record["text"] = record["text"].replace("30 days", "30 calendar days")
    problems = check_terms([record])
    assert any("not written in the text" in p for p in problems)
    assert any("numbers outside" in p for p in problems)


def test_two_durations_fail_and_an_amount_cannot_lead():
    assert any("at most one" in p for p in check_terms([policy("return", "electronics", ["30 days", "90 days"])]))
    assert any("main term" in p for p in check_terms([policy("return", "phones", ["$45", "14 days"])]))


def test_a_malformed_term_fails():
    assert any("is not" in p for p in check_terms([policy("return", "electronics", ["30 calendar days"])]))


def test_siblings_with_the_same_terms_fail():
    records = full_corpus()
    records[10] = policy("warranty", "laptops", ["1 year"], "region", "international")
    assert any("same terms" in p for p in check_terms(records))


# =================================================================================================
# P11 -- the new fields never reach chunk metadata
# =================================================================================================
def test_the_new_fields_never_reach_chunk_metadata():
    """A condition tag in the index would invite a filter on it from query words: a condition
    classifier on the hit path, which Final_Proposal.md:435 rejected (impact.md §3)."""
    from rag.ingest import record_to_document

    record = full_corpus()[1]
    document = record_to_document(record)
    assert set(document.metadata) == {"doc_id", "kind", "category", "title"}
    bare = {k: record[k] for k in ("doc_id", "title", "category", "text")}
    assert record_to_document(bare).text == document.text


# =================================================================================================
# Source counts -- counts only (plan steps 1-2)
# =================================================================================================
def test_source_counts_gives_the_maker_rule_and_counts_only():
    """The maker rule takes the most common brand (case-folded, ties alphabetical) per department
    and per leaf; the risky-title counts are counts, never titles."""
    stream = [
        ("product", {"doc_id": "p1", "title": "Phone X (Renewed)", "category": "phones", "specs": {"Brand": "Acme"}}),
        ("product", {"doc_id": "p2", "title": "Phone Y International Version", "category": "phones", "specs": {"Brand": "ACME"}}),
        ("product", {"doc_id": "p3", "title": "Phone Z", "category": "phones", "specs": {"Brand": "Bolt"}}),
        ("product", {"doc_id": "p4", "title": "Desk", "category": "furniture", "specs": {}}),
        ("question", {"doc_id": "p1", "leaf": "unlocked_cell_phones"}),
        ("question", {"doc_id": "p3", "leaf": "unlocked_cell_phones"}),
        ("question", {"doc_id": "p4", "leaf": "home_office_desks"}),
    ]
    counts = source_counts(stream)
    assert counts["products"] == 4
    # "Acme" and "ACME" are one brand; the shown spelling ties 1-1 and breaks by code point.
    assert counts["top_brands"]["phones"] == [("ACME", 2), ("Bolt", 1)]
    # one display spelling per brand, chosen over all products
    assert counts["top_brands"]["unlocked_cell_phones"] == [("ACME", 1), ("Bolt", 1)]  # p1, p3
    assert counts["top_brands"]["furniture"] == [("Desk", 1)]  # no Brand: the title's first word
    assert counts["risky_titles"]["phones"] == {
        "renewed or refurbished": 1, "international version": 1, "no warranty": 0, "any": 2,
    }
    assert "Phone X (Renewed)" not in repr(counts)  # no title ever leaves this function


def test_the_maker_is_the_brand_field_else_the_first_title_word():
    assert maker_of({"title": "Zeta phone", "specs": {"Brand": "Acme"}}) == "Acme"
    assert maker_of({"title": "Acme-Pro 15.6 laptop", "specs": {}}) == "Acme-Pro"
    assert maker_of({"title": "  (Renewed) Bolt X", "specs": {"Brand": " "}}) == "Renewed"
    assert maker_of({"title": "", "specs": {}}) == "<none>"
