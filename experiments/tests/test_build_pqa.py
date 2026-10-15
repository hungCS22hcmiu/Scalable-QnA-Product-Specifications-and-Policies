"""Tests for the Amazon-PQA builder (super-plan item 3.1).

The builder decides which records the corpus has, and a mistake in it raises no error: a misnamed
field gives empty products, a dropped field gives a plausible wrong corpus. Every test here pins a
property whose drift would be silent.

No PQA text and no file under `data/` is read or written. Fixtures are small records written inline,
and every output path is a parameter that points into `tmp_path`.
"""

import dataclasses
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import build_pqa
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_CARD = REPO_ROOT / "docs" / "data-card.md"
PROBE_RESULTS = (
    REPO_ROOT
    / "docs"
    / "work"
    / "2026-10-03-pqa-category-choice"
    / "probe_results.json"
)


# =================================================================================================
# A11: the pins equal the documents they were copied from
# =================================================================================================
def _data_card_sources():
    """`data-card.md` §1's source table: {leaf: (bytes, sha256)}."""
    row = re.compile(
        r"\|\s*`amazon_pqa_([^`]+)\.json`\s*\|\s*([\d,]+)\s*\|\s*`([0-9a-f]{64})`"
    )
    found = {}
    for line in DATA_CARD.read_text(encoding="utf-8").splitlines():
        m = row.search(line)
        if m:
            found[m.group(1)] = (int(m.group(2).replace(",", "")), m.group(3))
    return found


def _data_card_departments():
    """`data-card.md` §1's department table: {leaf: department}."""
    departments = {"phones", "laptops", "electronics", "furniture"}
    found = {}
    for line in DATA_CARD.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) > 3 and cells[1].strip("`") in departments:
            for leaf in re.findall(r"`([^`]+)`", cells[2]):
                found[leaf] = cells[1].strip("`")
    return found


def test_pinned_sources_equal_the_data_card():
    card = _data_card_sources()
    assert len(card) == 6, (
        "the data-card table was not found: this test would pass vacuously"
    )
    assert {s.leaf for s in build_pqa.LEAVES} == set(card)
    for spec in build_pqa.LEAVES:
        assert (spec.bytes, spec.sha256) == card[spec.leaf], spec.leaf


def test_pinned_departments_equal_the_data_card():
    card = _data_card_departments()
    assert len(card) == 6, (
        "the department table was not found: this test would pass vacuously"
    )
    for spec in build_pqa.LEAVES:
        assert spec.department == card[spec.leaf], spec.leaf


def test_pinned_counts_equal_the_probe_results():
    probe = {
        r["file"].removeprefix("amazon_pqa_").removesuffix(".json"): r
        for r in json.loads(PROBE_RESULTS.read_text(encoding="utf-8"))
    }
    for spec in build_pqa.LEAVES:
        p = probe[spec.leaf]
        assert spec.sha256 == p["sha256"], spec.leaf
        assert spec.parsed == p["records_parsed"], spec.leaf
        assert spec.products == p["products"], spec.leaf
        assert spec.skipped_total == p["records_unparsed"], spec.leaf
        assert spec.question_type == p["question_type"], spec.leaf
        assert spec.answer_aggregated == p["answer_aggregated"], spec.leaf
        assert spec.prose_median_chars == p["prose_median_chars"], spec.leaf


def test_pinned_totals_are_the_recorded_ones():
    """1,212,029 questions over 71,794 products: the figures in `data-card.md` §1."""
    assert sum(s.parsed for s in build_pqa.LEAVES) == 1_212_029
    assert sum(s.products for s in build_pqa.LEAVES) == 71_794
    assert sum(s.skipped_total for s in build_pqa.LEAVES) == 4


def test_the_real_field_set_is_the_fourteen_keys_in_the_bytes():
    """Counted from the key census of 2026-10-15 (evidence/key-census.md), not from the readme."""
    assert len(build_pqa.REAL_FIELDS) == 14
    assert len(set(build_pqa.REAL_FIELDS)) == 14
    for readme_name in (
        "asin_id",
        "bullet_points",
        "is_yes-no_question",
        "yes-no_answer",
    ):
        assert readme_name not in build_pqa.REAL_FIELDS
    for n in range(1, 6):
        assert f"bullet_point{n}" in build_pqa.REAL_FIELDS


# =================================================================================================
# Fixtures: small records written inline. No PQA text.
# =================================================================================================
BACKSLASH = chr(
    92
)  # a backslash-u typed in a tool call becomes the character, so build it
LONE_SURROGATE_ESCAPE = BACKSLASH + "ud800"
LONE_SURROGATE_RAW = bytes([0xED, 0xA0, 0x80])  # the UTF-8-style bytes of U+D800


def rec(asin="A1", qid="q1", text="Does it fold flat?", **over):
    """One valid record in the REAL field names."""
    r = {
        "asin": asin,
        "question_id": qid,
        "question_text": text,
        "question_type": "yes-no",
        "answers": [{"answer_text": "Yes it does."}],
        "answer_aggregated": "yes",
        "brand_name": "Acme",
        "item_name": "Acme folding chair",
        "product_description": "A chair.",
        "bullet_point1": "b1",
        "bullet_point2": "b2",
        "bullet_point3": "b3",
        "bullet_point4": "b4",
        "bullet_point5": "b5",
    }
    r.update(over)
    return r


def enc(r) -> bytes:
    return json.dumps(r).encode("utf-8") + b"\n"


def lines_of(*records) -> list[bytes]:
    return [enc(r) for r in records]


def spec_for(parsed, products, skipped_total=0, **over):
    """A fixture LeafSpec with hand-written pins (never computed by the code under test)."""
    kw = {
        "leaf": "fixture",
        "department": "furniture",
        "bytes": 0,
        "sha256": "0" * 64,
        "parsed": parsed,
        "products": products,
        "skipped_total": skipped_total,
        "question_type": {},
        "answer_aggregated": {},
        "prose_median_chars": 0,
    }
    kw.update(over)
    return build_pqa.LeafSpec(**kw)


# =================================================================================================
# parse_leaf
# =================================================================================================
def test_a_clean_fixture_parses_fully():
    result = build_pqa.parse_leaf(
        lines_of(rec("A1", "q1"), rec("A1", "q2", "Is it red?"), rec("A2", "q3"))
    )
    s = result.stats
    assert (s.lines_read, s.parsed, s.products) == (3, 3, 2)
    assert s.skipped_total == 0
    assert [q["question_id"] for q in result.products["A1"]["questions"]] == [
        "q1",
        "q2",
    ]
    assert result.products["A1"]["bullets"] == ["b1", "b2", "b3", "b4", "b5"]


def test_every_line_is_parsed_or_skipped_for_a_named_reason():
    """lines_read == parsed + skipped, with one line for each skip reason."""
    bad_utf8 = b'{"asin": "A9", "question_text": "' + bytes([0xFF]) + b'"}\n'
    result = build_pqa.parse_leaf(
        [
            enc(rec("A1")),
            b"\n",  # blank
            b"{not json\n",  # bad json
            b"[1, 2]\n",  # not an object
            enc(rec(asin="")),  # missing asin
            enc(rec("A3", text="   ")),  # question text blank after strip
            bad_utf8,  # invalid UTF-8 is counted as bad_json
        ]
    )
    s = result.stats
    assert s.lines_read == 7
    assert s.parsed == 1
    assert dict(s.skipped) == {
        build_pqa.BLANK_LINE: 1,
        build_pqa.BAD_JSON: 2,
        build_pqa.NOT_OBJECT: 1,
        build_pqa.MISSING_ASIN: 1,
        build_pqa.BAD_QUESTION_TEXT: 1,
    }
    assert s.lines_read == s.parsed + s.skipped_total


def test_line_no_counts_every_source_line_including_skipped_ones():
    result = build_pqa.parse_leaf(
        [b"\n", enc(rec("A1", "q1")), b"{bad\n", enc(rec("A1", "q2"))]
    )
    assert [q["line_no"] for q in result.products["A1"]["questions"]] == [2, 4]


def test_product_fields_come_from_the_first_parsed_record_not_the_first_line():
    skipped_first = rec("A9", "q0", text="", bullet_point1="from the skipped line")
    first = rec("A9", "q1", bullet_point1="first parsed")
    later = rec("A9", "q2", bullet_point1="a later record")
    result = build_pqa.parse_leaf(lines_of(skipped_first, first, later))
    assert result.products["A9"]["bullets"][0] == "first parsed"
    assert (
        result.stats.prose_conflicts == 1
    )  # one asin whose prose differs between records


def test_duplicate_question_ids_are_counted_and_kept():
    result = build_pqa.parse_leaf(
        lines_of(rec("A1", "dup"), rec("A2", "dup"), rec("A3", "ok"))
    )
    assert result.stats.duplicate_question_ids == 1
    assert result.stats.parsed == 3


def test_a_non_string_field_is_counted_not_coerced():
    result = build_pqa.parse_leaf(
        lines_of(rec("A1", bullet_point2=["a", "b"], item_name=7))
    )
    s = result.stats
    assert s.bad_type["bullet_point2"] == 1
    assert s.bad_type["item_name"] == 1
    product = result.products["A1"]
    assert product["bullets"][1] == ""  # never "['a', 'b']"
    assert product["item_name"] == ""


def test_answers_without_a_string_answer_text_are_dropped_and_counted():
    answers = [{"answer_text": "ok"}, {"other": 1}, "text", {"answer_text": 5}]
    result = build_pqa.parse_leaf(lines_of(rec("A1", answers=answers)))
    assert result.products["A1"]["questions"][0]["answers"] == ["ok"]
    assert result.stats.answers_bad == 3


def test_lone_surrogates_are_replaced_and_counted_in_both_forms():
    """As the JSON escape, and as raw bytes: json.loads accepts both and yields a lone surrogate."""
    as_escape = enc(rec("A1", "q1", text="x@@y")).replace(
        b"@@", LONE_SURROGATE_ESCAPE.encode("ascii")
    )
    as_raw = (
        json.dumps(rec("A1", "q2", text="x@@y"), ensure_ascii=False)
        .encode("utf-8")
        .replace(b"@@", LONE_SURROGATE_RAW)
        + b"\n"
    )
    result = build_pqa.parse_leaf([as_escape, as_raw])
    texts = [q["question_text"] for q in result.products["A1"]["questions"]]
    replaced = "x" + chr(0xFFFD) + "y"  # U+FFFD, the replacement character
    assert texts == [replaced, replaced]
    assert result.stats.surrogate_replacements == 2
    for text in texts:
        text.encode("utf-8")  # would raise on a lone surrogate


# =================================================================================================
# check_leaf: Stops 1 and 2
# =================================================================================================
def readme_record(asin="A1"):
    """The dataset readme's names, not the data's. A builder written from it parses nothing."""
    return {
        "asin_id": asin,
        "question_id": "q1",
        "question_text": "Does it fold flat?",
        "is_yes-no_question": True,
        "yes-no_answer": "yes",
        "bullet_points": ["b1", "b2"],
        "answer_text": "Yes it does.",
    }


def test_stop_1_readme_field_names_parse_zero_and_the_message_names_the_field():
    result = build_pqa.parse_leaf(lines_of(*[readme_record(f"A{n}") for n in range(5)]))
    assert result.stats.parsed == 0
    failures = build_pqa.check_leaf(result.stats, spec_for(parsed=5, products=5))
    assert len(failures) == 1
    msg = failures[0]
    assert msg.startswith("Stop 1")
    assert "'asin'" in msg  # the field it could not find
    assert "'asin_id'" in msg  # the key it saw instead
    assert "readme" in msg


def test_stop_1_an_empty_file_stops():
    result = build_pqa.parse_leaf([])
    failures = build_pqa.check_leaf(result.stats, spec_for(parsed=1, products=1))
    assert failures and failures[0].startswith("Stop 1")


def test_stop_2a_misnamed_bullets_pass_stop_1_but_not_stop_2():
    """The quiet form of the readme trap: asin and question_text parse, the bullets do not."""
    renamed = []
    for n in range(4):
        r = rec(f"A{n}", f"q{n}")
        for i in range(1, 6):
            del r[f"bullet_point{i}"]
        r["bullet_points"] = ["b1", "b2"]
        renamed.append(r)
    result = build_pqa.parse_leaf(lines_of(*renamed))
    assert result.stats.parsed == 4  # Stop 1 would pass
    failures = build_pqa.check_leaf(result.stats, spec_for(parsed=4, products=4))
    assert failures and failures[0].startswith("Stop 2")
    assert "bullet_point1" in failures[0]


def test_stop_2a_a_field_empty_in_every_record_stops():
    result = build_pqa.parse_leaf(
        lines_of(*[rec(f"A{n}", bullet_point5="") for n in range(3)])
    )
    failures = build_pqa.check_leaf(result.stats, spec_for(parsed=3, products=3))
    assert failures and "bullet_point5" in failures[0]


def test_stop_2a_one_non_empty_record_is_enough():
    records = [rec("A1", bullet_point5=""), rec("A2", bullet_point5="x")]
    result = build_pqa.parse_leaf(lines_of(*records))
    assert build_pqa.check_leaf(result.stats, spec_for(parsed=2, products=2)) == []


def test_stop_2b_a_key_outside_the_real_set_stops_and_is_named():
    result = build_pqa.parse_leaf(lines_of(rec("A1", bullet_point6="extra"), rec("A2")))
    failures = build_pqa.check_leaf(result.stats, spec_for(parsed=2, products=2))
    assert failures and failures[0].startswith("Stop 2")
    assert "bullet_point6" in failures[0]


def test_stop_2b_an_ignored_key_is_allowed_and_reported():
    result = build_pqa.parse_leaf(lines_of(rec("A1", extra="x"), rec("A2")))
    spec = spec_for(parsed=2, products=2)
    assert (
        build_pqa.check_leaf(result.stats, spec, ignored_keys={"extra": "a reason"})
        == []
    )
    assert build_pqa.unknown_keys(result.stats) == {"extra": 1}


# =================================================================================================
# check_leaf: Stop 3, input pins
# =================================================================================================
def test_stop_3_matching_input_pins_pass():
    result = build_pqa.parse_leaf(
        lines_of(rec("A1", "q1"), rec("A1", "q2"), rec("A2", "q3"))
    )
    assert build_pqa.check_leaf(result.stats, spec_for(parsed=3, products=2)) == []


def test_stop_3_a_wrong_parsed_products_or_skipped_count_stops():
    result = build_pqa.parse_leaf(lines_of(rec("A1", "q1"), rec("A2", "q2")))
    for wrong in (
        spec_for(parsed=3, products=2),
        spec_for(parsed=2, products=3),
        spec_for(parsed=2, products=2, skipped_total=1),
    ):
        failures = build_pqa.check_leaf(result.stats, wrong)
        assert failures and failures[0].startswith("Stop 3"), wrong


# =================================================================================================
# Stop 0: the source file
# =================================================================================================
def write_source(tmp_path, content=b"some bytes\n"):
    path = tmp_path / "amazon_pqa_fixture.json"
    path.write_bytes(content)
    return path, hashlib.sha256(content).hexdigest()


def test_stop_0_a_matching_file_passes(tmp_path):
    path, digest = write_source(tmp_path)
    spec = spec_for(1, 1, bytes=path.stat().st_size, sha256=digest)
    build_pqa.verify_source(path, spec)


def test_stop_0_a_missing_file_names_the_fetch_target(tmp_path):
    spec = spec_for(1, 1, bytes=5, sha256="0" * 64)
    with pytest.raises(build_pqa.SourceMismatch, match="make pqa-fetch"):
        build_pqa.verify_source(tmp_path / "absent.json", spec)


def test_stop_0_a_short_file_is_a_partial_download_and_says_to_resume(tmp_path):
    path, digest = write_source(tmp_path, b"0123456789")
    spec = spec_for(1, 1, bytes=100, sha256=digest)
    with pytest.raises(build_pqa.SourceMismatch, match="resume"):
        build_pqa.verify_source(path, spec)


def test_stop_0_a_longer_file_says_it_is_longer_and_to_delete_it(tmp_path):
    """The hash would refuse it anyway, but 'has the pinned size' would be a false message."""
    path, digest = write_source(tmp_path, b"0123456789-and-more")
    spec = spec_for(1, 1, bytes=10, sha256=digest)
    with pytest.raises(build_pqa.SourceMismatch) as excinfo:
        build_pqa.verify_source(path, spec)
    message = str(excinfo.value)
    assert "longer" in message and "delete" in message
    assert "pinned size" not in message


def test_stop_0_a_full_size_file_with_a_wrong_hash_says_to_delete_it(tmp_path):
    """curl -C - cannot repair a full-size bad file, so the message must not say 'resume'."""
    path, _ = write_source(tmp_path, b"0123456789")
    spec = spec_for(1, 1, bytes=10, sha256="f" * 64)
    with pytest.raises(build_pqa.SourceMismatch) as excinfo:
        build_pqa.verify_source(path, spec)
    message = str(excinfo.value)
    assert "sha256" in message and "delete" in message and "make pqa-fetch" in message
    assert "resume" not in message


def test_stop_0_a_changed_byte_of_the_same_size_is_caught(tmp_path):
    original = b"0123456789"
    _, digest = write_source(tmp_path, original)
    path = tmp_path / "amazon_pqa_fixture.json"
    path.write_bytes(b"012345678X")  # same size, one byte different
    spec = spec_for(1, 1, bytes=len(original), sha256=digest)
    with pytest.raises(build_pqa.SourceMismatch, match="sha256"):
        build_pqa.verify_source(path, spec)


# =================================================================================================
# The writer and Stop 3's OUTPUT pins
# =================================================================================================
def fixture_leaf():
    """Three questions over two products. Pins below are written by hand from the records above."""
    result = build_pqa.parse_leaf(
        lines_of(rec("A2", "q3"), rec("A1", "q1"), rec("A1", "q2", "Is it red?"))
    )
    # prose = "b1 b2 b3 b4 b5 A chair." = 23 characters, the same for both products.
    spec = spec_for(
        parsed=3,
        products=2,
        question_type={"yes-no": 3},
        answer_aggregated={"yes": 3},
        prose_median_chars=23,
    )
    return result, spec


def test_the_writer_output_passes_the_output_pins(tmp_path):
    result, spec = fixture_leaf()
    assert build_pqa.check_leaf(result.stats, spec) == []
    info = build_pqa.write_interim(result.products, spec, tmp_path)
    summary = build_pqa.summarise_interim(info.path)
    assert build_pqa.check_output(summary, spec) == []
    assert (summary.products, summary.questions) == (2, 3)


def test_the_interim_is_sorted_by_asin_and_carries_leaf_and_department(tmp_path):
    result, spec = fixture_leaf()
    info = build_pqa.write_interim(result.products, spec, tmp_path)
    rows = [
        json.loads(line) for line in info.path.read_text(encoding="utf-8").splitlines()
    ]
    assert [r["asin"] for r in rows] == ["A1", "A2"]  # the input order was A2, A1
    assert {(r["leaf"], r["department"]) for r in rows} == {("fixture", "furniture")}
    assert rows[0]["questions"][0]["line_no"] == 2


def test_the_hashing_writer_reports_the_size_and_hash_of_the_file_it_wrote(tmp_path):
    result, spec = fixture_leaf()
    info = build_pqa.write_interim(result.products, spec, tmp_path)
    data = info.path.read_bytes()
    assert (info.bytes, info.sha256) == (len(data), hashlib.sha256(data).hexdigest())


def test_an_unreplaced_lone_surrogate_fails_loudly_at_write(tmp_path):
    """ensure_ascii=False keeps this loud: otherwise the escape is written and `make ingest` fails."""
    result, spec = fixture_leaf()
    result.products["A1"]["item_name"] = "bad" + chr(0xD800)
    with pytest.raises(UnicodeEncodeError):
        build_pqa.write_interim(result.products, spec, tmp_path)


def _broken_writer(monkeypatch, tmp_path, change):
    """Install a product_line that makes one mistake, write, and return the output-pin failures."""
    good = build_pqa.product_line

    def broken(product, spec):
        return change(good(product, spec))

    monkeypatch.setattr(build_pqa, "product_line", broken)
    result, spec = fixture_leaf()
    # Stops 1 to 3 on the INPUT still pass: the stops that read the source cannot see this mistake.
    assert build_pqa.check_leaf(result.stats, spec) == []
    info = build_pqa.write_interim(result.products, spec, tmp_path)
    return build_pqa.check_output(build_pqa.summarise_interim(info.path), spec)


def test_stop_3_catches_a_writer_that_drops_the_fifth_bullet(monkeypatch, tmp_path):
    """The range(1, 5) off-by-one: every product loses a bullet and Stops 1 and 2 pass."""

    def drop_bullet5(line):
        line["bullets"] = line["bullets"][:4]
        return line

    failures = _broken_writer(monkeypatch, tmp_path, drop_bullet5)
    assert failures and "prose_median_chars" in failures[0]


def test_stop_3_catches_a_writer_that_swaps_question_type_and_answer_aggregated(
    monkeypatch, tmp_path
):
    def swap(line):
        for q in line["questions"]:
            q["question_type"], q["answer_aggregated"] = (
                q["answer_aggregated"],
                q["question_type"],
            )
        return line

    failures = _broken_writer(monkeypatch, tmp_path, swap)
    assert any("question_type" in f for f in failures)
    assert any("answer_aggregated" in f for f in failures)


def test_stop_3_catches_a_writer_that_loses_a_question(monkeypatch, tmp_path):
    def lose_one(line):
        line["questions"] = line["questions"][:1]
        return line

    failures = _broken_writer(monkeypatch, tmp_path, lose_one)
    assert any("questions" in f for f in failures)


def test_stop_3_catches_a_writer_that_empties_the_description(monkeypatch, tmp_path):
    def blank(line):
        line["product_description"] = ""
        return line

    failures = _broken_writer(monkeypatch, tmp_path, blank)
    assert failures and "prose_median_chars" in failures[0]


# =================================================================================================
# build(): the manifest, the all-or-nothing swap
# =================================================================================================
def make_leaf(raw_dir, leaf, department, records, **pins):
    """Write a fixture source file and return its spec. bytes and sha256 are computed here, by the
    test, so they do not depend on the code under test."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    data = b"".join(enc(r) if isinstance(r, dict) else r for r in records)
    (raw_dir / f"amazon_pqa_{leaf}.json").write_bytes(data)
    return spec_for(
        leaf=leaf,
        department=department,
        bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        **pins,
    )


def two_leaf_fixture(tmp_path):
    """chairs: 3 questions over A1, A2. desks: 2 questions over A2, A9. A2 is in both leaves."""
    raw = tmp_path / "raw"
    common = {"question_type": {"yes-no": 3}, "answer_aggregated": {"yes": 3}}
    chairs = make_leaf(
        raw,
        "chairs",
        "furniture",
        [rec("A1", "q1"), rec("A1", "q2", "Is it red?"), rec("A2", "q3")],
        parsed=3,
        products=2,
        prose_median_chars=23,
        **common,
    )
    desks = make_leaf(
        raw,
        "desks",
        "furniture",
        [rec("A2", "q4"), rec("A9", "q5")],
        parsed=2,
        products=2,
        prose_median_chars=23,
        question_type={"yes-no": 2},
        answer_aggregated={"yes": 2},
    )
    return (chairs, desks), raw


def paths(tmp_path):
    return {
        "interim_dir": tmp_path / "v1-draft" / "pqa",
        "manifest_path": tmp_path / "pqa-manifest.json",
    }


def test_a_good_build_writes_the_interim_files_and_the_manifest(tmp_path, capsys):
    leaves, raw = two_leaf_fixture(tmp_path)
    p = paths(tmp_path)
    assert build_pqa.build(leaves, raw, **p) == 0
    assert sorted(f.name for f in p["interim_dir"].iterdir()) == [
        "chairs.jsonl",
        "desks.jsonl",
    ]
    m = json.loads(p["manifest_path"].read_text(encoding="utf-8"))
    assert m["stage"] == "3.1-interim"
    assert "not the v1 snapshot" in m["note"]
    assert [s["leaf"] for s in m["sources"]] == ["chairs", "desks"]  # LEAVES order
    assert m["leaves"]["chairs"]["questions"] == 3
    assert (
        m["leaves"]["chairs"]["interim_sha256"]
        == hashlib.sha256((p["interim_dir"] / "chairs.jsonl").read_bytes()).hexdigest()
    )
    # Two meanings of "products" kept apart: A2 is in both leaves.
    assert m["totals"] == {
        "products_distinct_across_leaves": 3,
        "products_sum_of_leaf_distinct": 4,
        "questions": 5,
    }
    assert m["cross_leaf"] == {"chairs|desks": 1}
    assert [d.name for d in (tmp_path / "v1-draft").iterdir()] == [
        "pqa"
    ]  # no temp dir left


def test_the_manifest_carries_the_builder_hash_and_no_pqa_text(tmp_path):
    leaves, raw = two_leaf_fixture(tmp_path)
    p = paths(tmp_path)
    build_pqa.build(leaves, raw, **p)
    text = p["manifest_path"].read_text(encoding="utf-8")
    m = json.loads(text)
    script = Path(build_pqa.__file__).read_bytes()
    assert m["builder_sha256"] == hashlib.sha256(script).hexdigest()
    # Distinctive strings only: a short one such as "b1" can occur inside a hex digest.
    for free_text in (
        "Does it fold flat?",
        "Is it red?",
        "Yes it does.",
        "Acme",
        "A chair.",
    ):
        assert free_text not in text


def _strings(node):
    """Every string in a JSON value, keys included."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def test_every_string_in_the_manifest_is_a_name_a_digest_a_url_or_a_fixed_reason(
    tmp_path,
):
    """An allow-list, not a search for known text: it also stops text nobody thought of."""
    leaves, raw = two_leaf_fixture(tmp_path)
    p = paths(tmp_path)
    build_pqa.build(leaves, raw, **p)
    m = json.loads(p["manifest_path"].read_text(encoding="utf-8"))
    name = re.compile(r"[a-z0-9_&|.\-]{1,80}")
    hex64 = re.compile(r"[0-9a-f]{64}")
    url = re.compile(re.escape(build_pqa.BASE_URL) + r"/[A-Za-z0-9_%.\-]+\.json")
    for s in _strings(m):
        assert (
            hex64.fullmatch(s)
            or name.fullmatch(s)
            or url.fullmatch(s)
            or s
            in (
                build_pqa.MANIFEST_NOTE,
                "3.1-interim",
                "N/A",
                "WH",
            )  # keys of the real counts
        ), s


def test_a_stop_on_the_second_leaf_leaves_nothing_from_the_first(tmp_path, capsys):
    leaves, raw = two_leaf_fixture(tmp_path)
    broken = make_leaf(  # same leaf name as desks, but a wrong pin
        raw,
        "desks",
        "furniture",
        [rec("A2", "q4"), rec("A9", "q5")],
        parsed=99,
        products=2,
    )
    p = paths(tmp_path)
    assert build_pqa.build((leaves[0], broken), raw, **p) == 2
    assert not p["interim_dir"].exists()
    assert not p["manifest_path"].exists()
    assert not any(
        d.name.startswith(".pqa-") for d in (tmp_path / "v1-draft").iterdir()
    )
    assert "Stop 3" in capsys.readouterr().err


def test_a_source_mismatch_stops_before_any_parsing(tmp_path, monkeypatch, capsys):
    leaves, raw = two_leaf_fixture(tmp_path)
    (raw / leaves[0].filename).write_bytes(b"tampered")

    def must_not_run(lines):
        raise AssertionError("parse_leaf ran on a file that failed Stop 0")

    monkeypatch.setattr(build_pqa, "parse_leaf", must_not_run)
    p = paths(tmp_path)
    assert build_pqa.build(leaves, raw, **p) == 2
    assert not p["manifest_path"].exists()
    assert "Stop 0" in capsys.readouterr().err


def test_a_rebuild_replaces_the_previous_interim_files_and_manifest(tmp_path):
    leaves, raw = two_leaf_fixture(tmp_path)
    p = paths(tmp_path)
    p["interim_dir"].mkdir(parents=True)
    (p["interim_dir"] / "stale.jsonl").write_text("stale")
    p["manifest_path"].write_text("OLD")
    assert build_pqa.build(leaves, raw, **p) == 0
    assert not (p["interim_dir"] / "stale.jsonl").exists()
    assert (
        json.loads(p["manifest_path"].read_text(encoding="utf-8"))["stage"]
        == "3.1-interim"
    )


@pytest.mark.parametrize("fail_on_call", [1, 2, 3])
def test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest(
    tmp_path, monkeypatch, fail_on_call
):
    """A13. Call 1 moves the old directory aside, 2 moves the new one in, 3 replaces the manifest.
    Whichever fails, the interim files and the manifest must still be a matching OLD pair."""
    leaves, raw = two_leaf_fixture(tmp_path)
    p = paths(tmp_path)
    p["interim_dir"].mkdir(parents=True)
    (p["interim_dir"] / "old.jsonl").write_text("old interim")
    p["manifest_path"].write_text("OLD")

    real_replace = build_pqa.os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == fail_on_call:
            raise OSError("injected")
        return real_replace(src, dst)

    monkeypatch.setattr(build_pqa.os, "replace", flaky)
    with pytest.raises(OSError, match="injected"):
        build_pqa.build(leaves, raw, **p)
    assert (p["interim_dir"] / "old.jsonl").read_text() == "old interim"
    assert [f.name for f in p["interim_dir"].iterdir()] == ["old.jsonl"]
    assert p["manifest_path"].read_text() == "OLD"
    assert [d.name for d in (tmp_path / "v1-draft").iterdir()] == [
        "pqa"
    ]  # no temp dir left


def test_stale_temp_directories_from_a_crashed_run_are_removed(tmp_path, capsys):
    leaves, raw = two_leaf_fixture(tmp_path)
    p = paths(tmp_path)
    parent = p["interim_dir"].parent
    (parent / ".pqa-build-123").mkdir(parents=True)
    (parent / ".pqa-old-123").mkdir()
    assert build_pqa.build(leaves, raw, **p) == 0
    assert [d.name for d in parent.iterdir()] == ["pqa"]
    assert ".pqa-build-123" in capsys.readouterr().err


# =================================================================================================
# iter_interim and --verify: nothing is trusted until it has been hashed
# =================================================================================================
def built(tmp_path):
    leaves, raw = two_leaf_fixture(tmp_path)
    p = paths(tmp_path)
    assert build_pqa.build(leaves, raw, **p) == 0
    return leaves, raw, p


def test_iter_interim_yields_every_product_in_manifest_order(tmp_path):
    _, _, p = built(tmp_path)
    got = list(build_pqa.iter_interim(p["manifest_path"], p["interim_dir"]))
    assert [(leaf, row["asin"]) for leaf, row in got] == [
        ("chairs", "A1"),
        ("chairs", "A2"),
        ("desks", "A2"),
        ("desks", "A9"),
    ]


def test_iter_interim_raises_before_yielding_when_any_file_was_changed(tmp_path):
    """The changed file is the SECOND leaf's: the first line of the first leaf must not come out."""
    _, _, p = built(tmp_path)
    target = p["interim_dir"] / "desks.jsonl"
    data = bytearray(target.read_bytes())
    data[10] ^= 0x01  # same size, one bit different
    target.write_bytes(bytes(data))
    iterator = build_pqa.iter_interim(p["manifest_path"], p["interim_dir"])
    with pytest.raises(build_pqa.InterimMismatch, match="sha256"):
        next(iterator)


def test_iter_interim_raises_on_a_cut_short_file(tmp_path):
    _, _, p = built(tmp_path)
    target = p["interim_dir"] / "chairs.jsonl"
    target.write_bytes(target.read_bytes()[:-5])
    with pytest.raises(build_pqa.InterimMismatch, match="bytes"):
        next(build_pqa.iter_interim(p["manifest_path"], p["interim_dir"]))


def test_iter_interim_raises_on_a_missing_file(tmp_path):
    _, _, p = built(tmp_path)
    (p["interim_dir"] / "desks.jsonl").unlink()
    with pytest.raises(build_pqa.InterimMismatch, match="missing"):
        next(build_pqa.iter_interim(p["manifest_path"], p["interim_dir"]))


def test_iter_interim_ignores_a_file_that_is_not_in_the_manifest(tmp_path):
    """It walks the manifest's list and never globs: a stray file cannot get into 3.2's input."""
    _, _, p = built(tmp_path)
    (p["interim_dir"] / "stray.jsonl").write_text('{"asin": "STRAY"}\n')
    got = [
        row["asin"]
        for _, row in build_pqa.iter_interim(p["manifest_path"], p["interim_dir"])
    ]
    assert "STRAY" not in got and len(got) == 4


def test_a_missing_or_unreadable_manifest_says_to_build(tmp_path):
    p = paths(tmp_path)
    with pytest.raises(build_pqa.ManifestError, match="make pqa-build"):
        next(build_pqa.iter_interim(p["manifest_path"], p["interim_dir"]))
    p["manifest_path"].write_text("{not json")
    with pytest.raises(build_pqa.ManifestError):
        next(build_pqa.iter_interim(p["manifest_path"], p["interim_dir"]))


def test_verify_passes_on_a_good_build(tmp_path, capsys):
    _, raw, p = built(tmp_path)
    assert build_pqa.verify(raw_dir=raw, **p) == 0


def test_verify_fails_when_a_source_file_changed(tmp_path, capsys):
    leaves, raw, p = built(tmp_path)
    (raw / leaves[0].filename).write_bytes(b"changed")
    assert build_pqa.verify(raw_dir=raw, **p) == 2
    assert "Stop 0" in capsys.readouterr().err


def test_verify_fails_when_an_interim_file_changed(tmp_path, capsys):
    _, raw, p = built(tmp_path)
    (p["interim_dir"] / "chairs.jsonl").write_bytes(b"{}\n")
    assert build_pqa.verify(raw_dir=raw, **p) == 2


def test_verify_fails_when_the_manifest_belongs_to_a_different_build(tmp_path):
    """A crash between renames, or an older manifest restored by git, looks like this."""
    _, raw, p = built(tmp_path)
    m = json.loads(p["manifest_path"].read_text(encoding="utf-8"))
    m["leaves"]["chairs"]["interim_sha256"] = "0" * 64
    p["manifest_path"].write_text(json.dumps(m), encoding="utf-8")
    assert build_pqa.verify(raw_dir=raw, **p) == 2


def test_verify_only_warns_when_the_builder_script_changed(tmp_path, capsys):
    """builder_sha256 changes with a CRLF checkout or a reformat. It is read, not a failure."""
    _, raw, p = built(tmp_path)
    m = json.loads(p["manifest_path"].read_text(encoding="utf-8"))
    m["builder_sha256"] = "0" * 64
    p["manifest_path"].write_text(json.dumps(m), encoding="utf-8")
    assert build_pqa.verify(raw_dir=raw, **p) == 0
    assert "builder" in capsys.readouterr().err


# =================================================================================================
# A6: byte-identical output under different hash seeds
# =================================================================================================
DRIVER = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import build_pqa
leaves = tuple(build_pqa.LeafSpec(**d) for d in json.loads(Path(sys.argv[2]).read_text()))
ignored = json.loads(Path(sys.argv[3]).read_text())
code = build_pqa.build(leaves, Path(sys.argv[4]), Path(sys.argv[5]), Path(sys.argv[6]), ignored)
sys.exit(code)
"""
IGNORED_FOR_THE_TEST = {"x_alpha": "test", "x_beta": "test", "x_gamma": "test"}


def test_two_builds_under_different_hash_seeds_are_byte_identical(tmp_path):
    """Python randomises string hashes once per process, so two builds in ONE process would share a
    seed and pass even if the output followed a set's order. Two processes with two seeds cannot."""
    raw = tmp_path / "raw"
    extra = {
        "x_alpha": 1,
        "x_beta": "b",
        "x_gamma": [1],
    }  # 3 ignored keys: a set could reorder them
    chairs = make_leaf(
        raw,
        "chairs",
        "furniture",
        [rec("A1", "q1", **extra), rec("A2", "q2"), rec("A3", "q3")],
        parsed=3,
        products=3,
        prose_median_chars=23,
        question_type={"yes-no": 3},
        answer_aggregated={"yes": 3},
    )
    desks = make_leaf(
        raw,
        "desks",
        "furniture",
        [
            rec("A2", "q4"),
            rec("A3", "q5", **extra),
            rec("A9", "q6"),
        ],  # A2, A3 shared: 2 asins
        parsed=3,
        products=3,
        prose_median_chars=23,
        question_type={"yes-no": 3},
        answer_aggregated={"yes": 3},
    )
    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER, encoding="utf-8")
    specs = tmp_path / "specs.json"
    specs.write_text(
        json.dumps([dataclasses.asdict(s) for s in (chairs, desks)]), encoding="utf-8"
    )
    ignored = tmp_path / "ignored.json"
    ignored.write_text(json.dumps(IGNORED_FOR_THE_TEST), encoding="utf-8")
    scripts = str(Path(build_pqa.__file__).parent)

    outputs = []
    for seed in ("0", "1"):
        out = tmp_path / f"seed{seed}"
        env = {**os.environ, "PYTHONHASHSEED": seed}
        subprocess.run(
            [
                sys.executable,
                str(driver),
                scripts,
                str(specs),
                str(ignored),
                str(raw),
                str(out / "v1-draft" / "pqa"),
                str(out / "pqa-manifest.json"),
            ],
            check=True,
            env=env,
            capture_output=True,
        )
        outputs.append(
            {
                "manifest": (out / "pqa-manifest.json").read_bytes(),
                "chairs": (out / "v1-draft" / "pqa" / "chairs.jsonl").read_bytes(),
                "desks": (out / "v1-draft" / "pqa" / "desks.jsonl").read_bytes(),
            }
        )
    assert outputs[0] == outputs[1]
    manifest = json.loads(outputs[0]["manifest"])
    # The test is not vacuous: the ignored keys and the shared asins really are in the output.
    assert sorted(manifest["leaves"]["chairs"]["unknown_keys"]) == sorted(
        IGNORED_FOR_THE_TEST
    )
    assert manifest["cross_leaf"] == {"chairs|desks": 2}


# =================================================================================================
# The command line
# =================================================================================================
def test_main_builds_then_verifies(tmp_path, monkeypatch):
    leaves, raw = two_leaf_fixture(tmp_path)
    p = paths(tmp_path)
    monkeypatch.setattr(build_pqa, "LEAVES", leaves)
    common = ["--raw-dir", str(raw), "--interim-dir", str(p["interim_dir"])]
    common += ["--manifest", str(p["manifest_path"])]
    assert build_pqa.main(common) == 0
    assert build_pqa.main(["--verify", *common]) == 0


def test_main_list_prints_file_url_and_bytes_for_the_makefile(capsys):
    assert build_pqa.main(["--list"]) == 0
    rows = [line.split(" ") for line in capsys.readouterr().out.splitlines()]
    assert len(rows) == 6
    for (name, url, size), spec in zip(rows, build_pqa.LEAVES, strict=True):
        assert name == spec.filename and int(size) == spec.bytes
        assert url.startswith(build_pqa.BASE_URL + "/") and " " not in url
    by_name = {name: url for name, url, _ in rows}
    # The & in the leaf name is %26 in the URL, and still & in the file name.
    assert by_name["amazon_pqa_led_&_lcd_tvs.json"].endswith(
        "/amazon_pqa_led_%26_lcd_tvs.json"
    )


def test_the_command_line_exits_2_and_writes_nothing_when_the_sources_are_missing(
    tmp_path,
):
    """The real LEAVES against an empty directory: Stop 0, exit 2, and no file under any path."""
    script = Path(build_pqa.__file__)
    run = subprocess.run(
        [
            sys.executable,
            str(script),
            "--raw-dir",
            str(tmp_path / "empty"),
            "--interim-dir",
            str(tmp_path / "v1-draft" / "pqa"),
            "--manifest",
            str(tmp_path / "pqa-manifest.json"),
        ],
        capture_output=True,
        text=True,
        check=False,  # the exit code is the thing under test
    )
    assert run.returncode == 2
    assert "make pqa-fetch" in run.stderr
    assert not (tmp_path / "pqa-manifest.json").exists()
    assert not (tmp_path / "v1-draft" / "pqa").exists()
    assert [
        d.name for d in (tmp_path / "v1-draft").iterdir()
    ] == []  # the temp dir is gone


def test_an_unexpected_error_is_not_swallowed_into_exit_0(tmp_path, monkeypatch):
    """D7. The old script printed FAILED and exited 0; a wrapper trusting exit 0 took an empty run."""
    leaves, raw = two_leaf_fixture(tmp_path)

    def boom(lines):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(build_pqa, "parse_leaf", boom)
    with pytest.raises(RuntimeError, match="unexpected"):
        build_pqa.build(leaves, raw, **paths(tmp_path))


# =================================================================================================
# The manifest's own hash: what 3.2 records as the manifest it consumed
# =================================================================================================
def test_build_and_verify_print_the_sha256_of_the_manifest_file(tmp_path, capsys):
    leaves, raw = two_leaf_fixture(tmp_path)
    p = paths(tmp_path)
    assert build_pqa.build(leaves, raw, **p) == 0
    digest = hashlib.sha256(p["manifest_path"].read_bytes()).hexdigest()
    assert f"manifest sha256: {digest}" in capsys.readouterr().out
    assert build_pqa.verify(raw_dir=raw, **p) == 0
    assert f"manifest sha256: {digest}" in capsys.readouterr().out


def test_the_build_prints_the_counts_a_human_should_look_at(tmp_path, capsys):
    """Prose conflicts, duplicates, surrogates, bad types and shared asins are reported, never hidden."""
    leaves, raw = two_leaf_fixture(tmp_path)
    assert build_pqa.build(leaves, raw, **paths(tmp_path)) == 0
    out = capsys.readouterr().out
    for column in (
        "prose_conflicts",
        "duplicate_qids",
        "surrogates",
        "bad_type",
        "answers_bad",
    ):
        assert column in out
    assert "asins shared between leaves: chairs|desks: 1" in out  # A2 is in both leaves
    assert "questions 5" in out and "products 4 (sum of leaf distinct)" in out
    assert "3 distinct across leaves" in out


def test_the_build_prints_why_lines_were_skipped(tmp_path, capsys):
    """The probe lumped every skip together; the first real run must say which reason each one is."""
    raw = tmp_path / "raw"
    spec = make_leaf(
        raw,
        "chairs",
        "furniture",
        [
            rec("A1", "q1"),
            rec("A2", "q2", text="  "),
            b"{bad\n",
            rec("A3", "q3", text=""),
        ],
        parsed=1,
        products=1,
        skipped_total=3,
        prose_median_chars=23,
        question_type={"yes-no": 1},
        answer_aggregated={"yes": 1},
    )
    assert build_pqa.build((spec,), raw, **paths(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "skipped, chairs: bad_json 1, bad_question_text 2" in out


# =================================================================================================
# /ai-review finding 1: the stops must be wired into build(), not only correct as functions
# =================================================================================================
def one_leaf(tmp_path, records, **pins):
    """One fixture leaf 'chairs' with hand-written pins; returns (specs, raw_dir)."""
    raw = tmp_path / "raw"
    kw = {
        "parsed": len(records),
        "products": len(records),
        "prose_median_chars": 23,
        "question_type": {"yes-no": len(records)},
        "answer_aggregated": {"yes": len(records)},
    }
    kw.update(pins)
    return (make_leaf(raw, "chairs", "furniture", records, **kw),), raw


def assert_nothing_written(tmp_path):
    p = paths(tmp_path)
    assert not p["interim_dir"].exists()
    assert not p["manifest_path"].exists()
    parent = p["interim_dir"].parent
    assert not parent.exists() or [d.name for d in parent.iterdir()] == []


def test_build_stops_on_readme_field_names_and_writes_nothing(tmp_path, capsys):
    """The Done-when of 3.1, driven end to end: Stop 1 through build(), exit 2, no file."""
    leaves, raw = one_leaf(tmp_path, [readme_record(f"A{n}") for n in range(3)])
    assert build_pqa.build(leaves, raw, **paths(tmp_path)) == 2
    err = capsys.readouterr().err
    assert "Stop 1" in err and "'asin_id'" in err
    assert_nothing_written(tmp_path)


def test_build_stops_on_misnamed_bullets_and_writes_nothing(tmp_path, capsys):
    records = []
    for n in range(3):
        r = rec(f"A{n}", f"q{n}")
        for i in range(1, 6):
            del r[f"bullet_point{i}"]
        records.append(r)
    leaves, raw = one_leaf(tmp_path, records)
    assert build_pqa.build(leaves, raw, **paths(tmp_path)) == 2
    assert "Stop 2" in capsys.readouterr().err
    assert_nothing_written(tmp_path)


def test_build_stops_on_an_unlisted_key_and_writes_nothing(tmp_path, capsys):
    leaves, raw = one_leaf(
        tmp_path, [rec("A1", "q1", bullet_point6="x"), rec("A2", "q2")]
    )
    assert build_pqa.build(leaves, raw, **paths(tmp_path)) == 2
    err = capsys.readouterr().err
    assert "Stop 2" in err and "bullet_point6" in err
    assert_nothing_written(tmp_path)


def test_build_stops_when_the_writer_drops_a_bullet_and_writes_nothing(
    tmp_path, monkeypatch, capsys
):
    """Stops 1 and 2 read the source and pass. Only the output check can see this, and it must run
    inside build(), because the real data passes whether or not it runs."""
    good = build_pqa.product_line

    def drop_bullet5(product, spec):
        line = good(product, spec)
        line["bullets"] = line["bullets"][:4]
        return line

    monkeypatch.setattr(build_pqa, "product_line", drop_bullet5)
    leaves, raw = one_leaf(tmp_path, [rec("A1", "q1"), rec("A2", "q2")])
    assert build_pqa.build(leaves, raw, **paths(tmp_path)) == 2
    err = capsys.readouterr().err
    assert "Stop 3" in err and "as written" in err
    assert_nothing_written(tmp_path)


# =================================================================================================
# /ai-review finding 2: the writer is checked field by field against what was parsed
# =================================================================================================
DISTINCT_PROSE_CHARS = len(
    "one 1 two 1 three 1 four 1 five 1 description 1"
)  # same for n = 0..9


def distinct_record(asin, n):
    """Every field gets a value of its own, so a swap or a drop cannot hide behind equal values."""
    return rec(
        asin,
        f"qid-{n}",
        f"question text {n}?",
        question_type="yes-no",
        answer_aggregated="yes",
        answers=[
            {"answer_text": f"first answer {n}"},
            {"answer_text": f"second answer {n}"},
        ],
        brand_name=f"brand {n}",
        item_name=f"item {n}",
        product_description=f"description {n}",
        bullet_point1=f"one {n}",
        bullet_point2=f"two {n}",
        bullet_point3=f"three {n}",
        bullet_point4=f"four {n}",
        bullet_point5=f"five {n}",
    )


def test_each_real_field_lands_in_its_own_slot_of_the_product(tmp_path):
    """Hand-written expected values: a parser that reads brand_name into item_name fails here."""
    result = build_pqa.parse_leaf(lines_of(distinct_record("A1", 7)))
    product = result.products["A1"]
    assert product["item_name"] == "item 7"
    assert product["brand_name"] == "brand 7"
    assert product["product_description"] == "description 7"
    assert product["bullets"] == ["one 7", "two 7", "three 7", "four 7", "five 7"]
    (question,) = product["questions"]
    assert question["question_id"] == "qid-7"
    assert question["question_text"] == "question text 7?"
    assert question["answers"] == ["first answer 7", "second answer 7"]
    assert (question["question_type"], question["answer_aggregated"]) == (
        "yes-no",
        "yes",
    )


def test_a_good_build_round_trips_every_field_through_the_interim_file(tmp_path):
    leaves, raw = one_leaf(
        tmp_path,
        [distinct_record(f"A{n}", n) for n in range(4)],
        prose_median_chars=DISTINCT_PROSE_CHARS,
    )
    p = paths(tmp_path)
    assert build_pqa.build(leaves, raw, **p) == 0
    parsed = build_pqa.parse_leaf(
        (raw / leaves[0].filename).read_bytes().splitlines(keepends=True)
    ).products
    read_back = {row["asin"]: row for _, row in build_pqa.iter_interim(**_reader(p))}
    assert sorted(read_back) == sorted(parsed)
    for asin, row in read_back.items():
        assert (row.pop("leaf"), row.pop("department")) == ("chairs", "furniture")
        assert row == parsed[asin], asin


def _reader(p):
    return {"manifest_path": p["manifest_path"], "interim_dir": p["interim_dir"]}


def _swap_item_and_brand(line):
    line["item_name"], line["brand_name"] = line["brand_name"], line["item_name"]
    return line


def _blank_brand(line):
    line["brand_name"] = ""
    return line


def _keep_one_answer(line):
    for q in line["questions"]:
        q["answers"] = q["answers"][:1]
    return line


def _swap_bullets_four_and_five(line):
    b = line["bullets"]
    b[3], b[4] = b[4], b[3]
    return line


def _blank_question_text(line):
    for q in line["questions"]:
        q["question_text"] = ""
    return line


def _shift_line_numbers(line):
    for q in line["questions"]:
        q["line_no"] += 1
    return line


def _rename_the_asin(line):
    line["asin"] = "ZZ" + line["asin"]
    return line


@pytest.mark.parametrize(
    "mistake",
    [
        _swap_item_and_brand,
        _blank_brand,
        _keep_one_answer,
        _swap_bullets_four_and_five,
        _blank_question_text,
        _shift_line_numbers,
        _rename_the_asin,
    ],
)
def test_build_stops_on_any_field_the_writer_changes(
    tmp_path, monkeypatch, capsys, mistake
):
    """These mistakes keep every aggregate pin intact (counts, medians): only a field-by-field
    comparison with what was parsed can see them."""
    good = build_pqa.product_line
    monkeypatch.setattr(
        build_pqa, "product_line", lambda product, spec: mistake(good(product, spec))
    )
    leaves, raw = one_leaf(
        tmp_path,
        [distinct_record(f"A{n}", n) for n in range(3)],
        prose_median_chars=DISTINCT_PROSE_CHARS,
    )
    assert build_pqa.build(leaves, raw, **paths(tmp_path)) == 2
    err = capsys.readouterr().err
    assert "Stop 3" in err and "differs from what was parsed" in err
    assert_nothing_written(tmp_path)


# =================================================================================================
# /ai-review finding 3: --verify must not be a rebuild
# =================================================================================================
def test_verify_does_not_rebuild_a_missing_interim_file(tmp_path, monkeypatch):
    leaves, raw = two_leaf_fixture(tmp_path)
    p = paths(tmp_path)
    monkeypatch.setattr(build_pqa, "LEAVES", leaves)
    common = ["--raw-dir", str(raw), "--interim-dir", str(p["interim_dir"])]
    common += ["--manifest", str(p["manifest_path"])]
    assert build_pqa.main(common) == 0
    (p["interim_dir"] / "chairs.jsonl").unlink()
    assert build_pqa.main(["--verify", *common]) == 2  # a rebuild would return 0
    assert not (
        p["interim_dir"] / "chairs.jsonl"
    ).exists()  # and would have written it back


# =================================================================================================
# /ai-review finding 4: the counts in the tracked manifest, and its guards
# =================================================================================================
def counted_fixture(tmp_path):
    raw = tmp_path / "raw"
    surrogate = enc(rec("A3", "q4", text="x@@y")).replace(
        b"@@", LONE_SURROGATE_ESCAPE.encode("ascii")
    )
    records = [
        rec("A1", "q1"),
        b"\n",  # blank
        rec("A1", "q2", bullet_point1="different"),  # prose conflict for A1
        rec("A2", "q2"),  # duplicate question_id q2
        b"{bad\n",  # bad json
        surrogate,  # one lone surrogate
        rec("A4", "q5", item_name=7),  # wrong type
        rec(
            "A5", "q6", answers=[{"answer_text": "ok"}, {"other": 1}]
        ),  # one bad answers entry
    ]
    spec = make_leaf(
        raw,
        "chairs",
        "furniture",
        records,
        parsed=6,
        products=5,
        skipped_total=2,
        prose_median_chars=23,
        question_type={"yes-no": 6},
        answer_aggregated={"yes": 6},
    )
    return (spec,), raw


def test_the_manifest_counts_equal_hand_counted_numbers(tmp_path):
    leaves, raw = counted_fixture(tmp_path)
    p = paths(tmp_path)
    assert build_pqa.build(leaves, raw, **p) == 0
    entry = json.loads(p["manifest_path"].read_text(encoding="utf-8"))["leaves"][
        "chairs"
    ]
    assert entry["lines_read"] == 8
    assert entry["records_parsed"] == 6 and entry["questions"] == 6
    assert entry["skipped"] == {
        "blank_line": 1,
        "bad_json": 1,
        "not_object": 0,
        "missing_asin": 0,
        "bad_question_text": 0,
    }
    assert entry["products"] == 5
    assert entry["prose_conflicts"] == 1
    assert entry["duplicate_question_ids"] == 1
    assert entry["surrogate_replacements"] == 1
    assert entry["bad_type"] == {"item_name": 1}
    assert entry["answers_bad"] == 1
    assert entry["question_type"] == {"yes-no": 6}
    assert entry["answer_aggregated"] == {"yes": 6}
    assert entry["prose_median_chars"] == 23
    nonempty = dict.fromkeys(build_pqa.REAL_FIELDS, 6)
    nonempty["item_name"] = 5  # the wrong-type value counts as empty
    assert entry["field_nonempty"] == nonempty
    assert entry["unknown_keys"] == {}


@pytest.mark.parametrize("which", ["high", "low"])
@pytest.mark.parametrize(
    "field",
    ["asin", "question_id", "item_name", "brand_name", "bullet_point3", "answer_text"],
)
def test_a_lone_surrogate_in_any_text_field_is_replaced_and_the_file_is_writable(
    tmp_path, field, which
):
    """High (D800) and low (DC00) halves, in a key field, a product field, and an answer."""
    escape = BACKSLASH + ("ud800" if which == "high" else "udc00")
    if field == "answer_text":
        r = rec("A1", "q1", answers=[{"answer_text": "ans@@"}])
    elif field == "asin":
        r = rec("val@@", "q1")
    else:
        r = rec("A1", "q1", **{field: "val@@"})
    line = enc(r).replace(b"@@", escape.encode("ascii"))
    result = build_pqa.parse_leaf([line])
    assert result.stats.surrogate_replacements == 1
    spec = spec_for(parsed=1, products=1)
    build_pqa.write_interim(
        result.products, spec, tmp_path
    )  # raises on a surviving surrogate


def test_load_manifest_rejects_a_wrong_stage_and_a_wrong_version(tmp_path):
    leaves, raw = two_leaf_fixture(tmp_path)
    p = paths(tmp_path)
    build_pqa.build(leaves, raw, **p)
    good = json.loads(p["manifest_path"].read_text(encoding="utf-8"))
    for key, value, match in (
        ("stage", "v1-snapshot", "stage"),
        ("manifest_version", 99, "manifest_version"),
    ):
        bad = {**good, key: value}
        p["manifest_path"].write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(build_pqa.ManifestError, match=match):
            build_pqa.load_manifest(p["manifest_path"])


# =================================================================================================
# /ai-review findings 6 and 7
# =================================================================================================
def test_every_source_is_checked_before_any_leaf_is_parsed(
    tmp_path, monkeypatch, capsys
):
    """Spec Stop 0: 'before any parsing'. The LAST file is the bad one; no leaf may have been parsed."""
    leaves, raw = two_leaf_fixture(tmp_path)
    (raw / leaves[-1].filename).write_bytes(b"tampered")
    parsed = []
    real = build_pqa.parse_leaf
    monkeypatch.setattr(
        build_pqa, "parse_leaf", lambda lines: parsed.append(1) or real(lines)
    )
    assert build_pqa.build(leaves, raw, **paths(tmp_path)) == 2
    assert parsed == []
    assert "Stop 0" in capsys.readouterr().err


def test_the_stale_files_of_the_retired_script_are_reported_on_every_build(
    tmp_path, capsys
):
    """175 wrong-dataset product-*.json sit in data/v1-draft/. Nothing may take them for the corpus."""
    leaves, raw = two_leaf_fixture(tmp_path)
    p = paths(tmp_path)
    parent = p["interim_dir"].parent
    parent.mkdir(parents=True)
    for name in ("product-a.json", "product-b.json"):
        (parent / name).write_text("{}")
    assert build_pqa.build(leaves, raw, **p) == 0
    err = capsys.readouterr().err
    assert "2 stale product-*.json" in err and "wrong dataset" in err
    assert sorted(f.name for f in parent.glob("product-*.json")) == [
        "product-a.json",
        "product-b.json",
    ]


@pytest.mark.parametrize(
    "pin",
    [
        {"question_type": {"WH": 2}},
        {"answer_aggregated": {"no": 2}},
        {"prose_median_chars": 99},
    ],
)
def test_build_stops_when_consistent_data_contradicts_an_aggregate_pin(
    tmp_path, capsys, pin
):
    """The writer and the parse agree here, so only the pins from the separate probe can object. This
    keeps the pin check's wiring tested on its own, apart from the field-by-field round trip."""
    leaves, raw = one_leaf(tmp_path, [rec("A1", "q1"), rec("A2", "q2")], **pin)
    assert build_pqa.build(leaves, raw, **paths(tmp_path)) == 2
    err = capsys.readouterr().err
    assert "Stop 3" in err and "as written has" in err
    assert "differs from what was parsed" not in err  # the round trip had no complaint
    assert_nothing_written(tmp_path)


# =================================================================================================
# check_round_trip, directly: the three things the aggregate pins would also notice at build level
# =================================================================================================
def _written(tmp_path):
    result, spec = fixture_leaf()
    info = build_pqa.write_interim(result.products, spec, tmp_path)
    return info, spec, info.path.read_bytes().splitlines(keepends=True)


def test_the_round_trip_passes_an_untouched_file(tmp_path):
    info, spec, _ = _written(tmp_path)
    assert build_pqa.check_round_trip(info, spec) == []


def test_the_round_trip_notices_a_repeated_product_line(tmp_path):
    info, spec, lines = _written(tmp_path)
    info.path.write_bytes(lines[0] + lines[0])
    failures = build_pqa.check_round_trip(info, spec)
    assert failures and "repeats an asin" in failures[0]


def test_the_round_trip_notices_a_missing_product(tmp_path):
    info, spec, lines = _written(tmp_path)
    info.path.write_bytes(lines[0])
    failures = build_pqa.check_round_trip(info, spec)
    assert failures and "missing" in failures[0]


def test_the_round_trip_notices_a_wrong_leaf(tmp_path):
    info, spec, lines = _written(tmp_path)
    info.path.write_bytes(
        lines[0].replace(b'"leaf":"fixture"', b'"leaf":"other"') + lines[1]
    )
    failures = build_pqa.check_round_trip(info, spec)
    assert failures and "wrong leaf or department" in failures[0]


def test_the_round_trip_messages_name_a_line_and_never_a_value(tmp_path):
    info, spec, lines = _written(tmp_path)
    info.path.write_bytes(
        lines[0].replace(b"Acme folding chair", b"SECRET PQA TEXT") + lines[1]
    )
    (message,) = build_pqa.check_round_trip(info, spec)
    assert "line 1" in message and "SECRET PQA TEXT" not in message
