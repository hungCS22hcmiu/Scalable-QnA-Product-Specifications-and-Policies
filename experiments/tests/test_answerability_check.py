"""Tests for answerability_check.py (item 3.2, design §3.1, test T15). Hand-made fixtures only."""

import csv
import hashlib
import json

import answerability_check as ac
import build_pqa
import pytest

BULLETS = ("alpha bravo", "charlie delta", "echo foxtrot", "golf hotel", "india juliet")


def rec(asin, qid, text):
    r = {
        "asin": asin,
        "question_id": qid,
        "question_text": text,
        "question_type": "yes-no",
        "answers": [{"answer_text": "yes"}],
        "answer_aggregated": "yes",
        "brand_name": "Acme",
        "item_name": "Acme Chair Model",
        "product_description": "A chair.",
    }
    for i, b in enumerate(BULLETS, start=1):
        r[f"bullet_point{i}"] = b
    return r


def write_interim(tmp_path, records, leaf="chairs"):
    interim = tmp_path / "v1-draft" / "pqa"
    interim.mkdir(parents=True)
    result = build_pqa.parse_leaf([json.dumps(r).encode() + b"\n" for r in records])
    spec = build_pqa.LeafSpec(
        leaf=leaf,
        department="furniture",
        bytes=0,
        sha256="0" * 64,
        parsed=result.stats.parsed,
        products=result.stats.products,
        skipped_total=0,
    )
    info = build_pqa.write_interim(result.products, spec, interim)
    entry = build_pqa.leaf_entry(result.stats, info, build_pqa.summarise_interim(info.path))
    manifest = build_pqa.build_manifest((spec,), {leaf: entry}, {leaf: frozenset(result.products)})
    path = tmp_path / "pqa-manifest.json"
    path.write_bytes(build_pqa.manifest_bytes(manifest))
    return path, interim


COLUMNS = ["qid", "question", "ASIN", "candidate", "source", "qa_pair_id", "title", "label", "answer"]


def write_epqa(tmp_path, rows):
    """rows: (asin, question, source, label, candidate). Spread over the three files."""
    d = tmp_path / "epqa"
    d.mkdir()
    files = {}
    for k, name in enumerate(("train.csv", "dev.csv", "test.csv")):
        path = d / name
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(COLUMNS)
            for n, (asin, q, source, label, cand) in enumerate(rows):
                if n % 3 == k:
                    w.writerow([f"q{n}", q, asin, cand, source, "", "t", label, ""])
        data = path.read_bytes()
        files[name] = (len(data), hashlib.sha256(data).hexdigest())
    return d, files


A, B = "B000000001", "B000000002"
PQA = [
    rec(A, "a1", "Is it alpha bravo charlie?"),  # R2 answerable
    rec(A, "a2", "Is it alpha bravo charlie?"),  # the same text again: 2 lines, 1 unit
    rec(A, "a3", "Does it have zulu yankee?"),  # R2 unanswerable
    rec(A, "a4", "What is the return window?"),  # policy: counted apart
    rec(B, "b1", "Does it echo foxtrot golf?"),  # R2 answerable
    rec(B, "b2", "Is it not in the epqa set?"),  # no match
]
EPQA = [
    (A, "  is it ALPHA bravo charlie? ", "bullet", "1", "zulu"),
    (A, "is it alpha bravo charlie?", "bullet", "2", "alpha bravo charlie"),  # a 1 and a 2: yes
    (A, "does it have zulu yankee?", "bullet", "1", "zulu"),  # only 1s: no
    (A, "does it have zulu yankee?", "attribute", "2", "zulu yankee"),  # secondary only
    (A, "what is the return window?", "description", "2", "thirty days"),
    (B, "does it echo foxtrot golf?", "description", "2", "zulu yankee xray"),  # not contained
]


def run(tmp_path, pins=None, files_override=None):
    manifest, interim = write_interim(tmp_path, PQA)
    epqa_dir, files = write_epqa(tmp_path, EPQA)
    out = tmp_path / "answerability.json"
    code = ac.check(
        manifest,
        interim,
        epqa_dir,
        out,
        files=files_override or files,
        pins=pins or {"chairs": 5},
    )
    return code, out


def test_lines_and_units_are_counted_apart(tmp_path):
    code, out = run(tmp_path)
    assert code == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["matched_lines"] == {"chairs": 5}
    assert result["units"] == 4
    assert result["unit_kinds"] == {"policy": 1, "spec": 3}


def test_label_combination_and_the_two_by_two_tables(tmp_path):
    _, out = run(tmp_path)
    a = json.loads(out.read_text(encoding="utf-8"))["agreement"]
    # units: alpha (R2 yes; primary yes, secondary yes, tertiary yes)
    #        zulu  (R2 no;  primary no,  secondary yes, tertiary no)
    #        echo  (R2 yes; primary yes, secondary yes, tertiary no: candidate not in the record)
    assert {k: a["primary"]["r2"][k] for k in ("tp", "fp", "fn", "tn")} == {
        "tp": 2, "fp": 0, "fn": 0, "tn": 1
    }
    assert {k: a["secondary"]["r2"][k] for k in ("tp", "fp", "fn", "tn")} == {
        "tp": 2, "fp": 0, "fn": 1, "tn": 0
    }
    assert {k: a["tertiary"]["r2"][k] for k in ("tp", "fp", "fn", "tn")} == {
        "tp": 1, "fp": 1, "fn": 0, "tn": 1
    }
    assert a["primary"]["r2"]["agreement"] == 1.0


def test_the_output_holds_no_question_text_and_no_asin(tmp_path):
    _, out = run(tmp_path)
    data = out.read_bytes()
    assert b"alpha" not in data and b"zulu" not in data
    assert A.encode() not in data and B.encode() not in data


def test_a_line_count_off_its_pin_stops(tmp_path, capsys):
    code, out = run(tmp_path, pins={"chairs": 4})
    assert code == 2 and not out.exists()
    assert "pinned" in capsys.readouterr().err


def test_a_changed_epqa_file_stops(tmp_path):
    files = {"train.csv": (1, "0" * 64), "dev.csv": (1, "0" * 64), "test.csv": (1, "0" * 64)}
    code, _ = run(tmp_path, files_override=files)
    assert code == 2


def test_the_pins_are_the_probes_194():
    assert sum(ac.MATCHED_LINES.values()) == 194
    assert list(ac.MATCHED_LINES) == [s.leaf for s in build_pqa.LEAVES]


@pytest.mark.parametrize(
    "cells, kappa",
    [({"tp": 5, "fp": 0, "fn": 0, "tn": 5}, 1.0), ({"tp": 5, "fp": 5, "fn": 5, "tn": 5}, 0.0)],
)
def test_kappa_on_hand_computed_tables(cells, kappa):
    from collections import Counter

    assert ac.agreement(Counter(cells))["kappa"] == kappa


# /ai-review 2026-10-20, finding 10: the per-leaf pin, the containment share and the hash branch.
def test_the_matched_line_pins_are_the_probes_per_leaf_counts():
    assert ac.MATCHED_LINES == {
        "unlocked_cell_phones": 143,
        "traditional_laptops": 5,
        "led_&_lcd_tvs": 21,
        "over-ear_headphones": 19,
        "chairs": 2,
        "home_office_desks": 4,
    }


def test_the_tertiary_containment_share_is_four_fifths():
    from fractions import Fraction

    assert Fraction(4, 5) == ac.CONTAINMENT
    record = frozenset({"alpha", "bravo", "charlie", "delta"})
    four_of_five = [("bullet", "2", "alpha bravo charlie delta zulu")]
    three_of_five = [("bullet", "2", "alpha bravo charlie zulu yankee")]
    assert ac.epqa_labels(four_of_five, record)["tertiary"]
    assert not ac.epqa_labels(three_of_five, record)["tertiary"]


def test_a_file_of_the_pinned_size_with_another_hash_stops(tmp_path):
    epqa_dir, files = write_epqa(tmp_path, EPQA)
    name = "dev.csv"
    data = (epqa_dir / name).read_bytes()
    (epqa_dir / name).write_bytes(data[:-1] + (b"X" if data[-1:] != b"X" else b"Y"))
    with pytest.raises(ac.CheckStop, match="sha256"):
        ac.verify_sources(epqa_dir, files)
