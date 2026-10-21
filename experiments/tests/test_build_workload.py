"""Tests for the workload generator's mechanical half (item 3.4; design.md §6).

The model layer is written by Claude and cannot be re-made, so the import checks are the only thing
between a wrong row and the workload: each test here pins one check on one side of its edge
(T10), or one property of the task plan whose drift would be silent. Products and questions are
synthetic (invented names, no PQA text); the policy documents are the tracked, author-written
`data/policies-v1/`, read as test_check_policies reads them.
"""

import hashlib
import json
import math
import os
import re
import subprocess
import sys

import build_workload
import corpus_gate
import pytest
from build_workload import (
    CONSTANTS,
    POLICY_DIR,
    REPLACED,
    ROUNDS,
    RULES_PATH,
    SHAPES,
    TWIN_WORDINGS_DEPT,
    Record,
    WorkloadStop,
    assign_split,
    assign_stratum,
    blind_key,
    build,
    canonical,
    check_tasks,
    claude_fields,
    construct,
    derived,
    embed_all,
    first_labels,
    import_rows,
    label_tasks,
    load_inputs,
    load_layer,
    make_manifest,
    make_units,
    names_product,
    natural_candidates,
    open_tasks,
    output_files,
    plan_cells,
    policy_sections,
    rank,
    read_inputs,
    simulate_lru,
    swap_directions,
    swap_kind,
    swap_leftover,
    swap_question,
    token_set,
    verify_outputs,
    write_outputs,
    write_sheets,
    write_tasks,
)

RULES_SHA = "0" * 64

# =================================================================================================
# A synthetic selection: three products per department, a few questions each
# =================================================================================================
LEAF = {
    "phones": "unlocked_cell_phones",
    "laptops": "traditional_laptops",
    "electronics": "over-ear_headphones",
    "furniture": "chairs",
}
PRODUCTS = [
    ("product-phones-z1", "phones", "Zenvo X2 Smartphone 64GB Blue", {
        "Feature 1": "6.2 inch display with 64GB of storage",
        "Feature 2": "The 4000 mAh battery lasts up to 2 days on one charge",
        "Feature 3": "Works with Windows 7 for file transfer over USB",
        "Description": "A light phone with a bright screen and a fast charger in the box.",
        "Brand": "Zenvo",
    }),
    ("product-phones-k5", "phones", "Kestrel M5 Phone 32GB Black", {
        "Feature 1": "5.8 inch display with 32GB of storage",
        "Feature 2": "Battery lasts up to 1 day",
        "Description": "A small phone that fits in one hand.",
    }),
    ("product-phones-r1", "phones", "Renewed Zenvo X1 Phone", {
        "Feature 1": "5.5 inch display", "Description": "Tested and cleaned.",
    }),
    ("product-laptops-o14", "laptops", "Orbis 14 Pro Laptop 16GB RAM", {
        "Feature 1": "Backlit keyboard with two brightness levels",
        "Feature 2": "Weighs 1.3 kg with the battery",
    }),
    ("product-laptops-v15", "laptops", "Vantor 15 Air Notebook", {
        "Feature 1": "Full HD screen of 15.6 inches", "Feature 2": "8GB RAM",
    }),
    ("product-electronics-b3", "electronics", "Brava Q3 Over-Ear Headphones", {
        "Feature 1": "Folds flat into the hard case", "Feature 2": "30 hours of playback",
    }),
    ("product-electronics-s7", "electronics", "Solace H7 Wireless Headphones", {
        "Feature 1": "Noise cancelling with three modes", "Feature 2": "20 hours of playback",
    }),
    ("product-furniture-h1", "furniture", "Halden Task Chair Mesh Back", {
        "Feature 1": "Arms adjust up and down by 8 cm", "Feature 2": "Holds up to 120 kg",
    }),
    ("product-furniture-m2", "furniture", "Marlow Mesh Office Chair", {
        "Feature 1": "Fixed arms", "Feature 2": "Holds up to 100 kg",
    }),
]
LINES = [
    ("product-phones-z1", 1, "How long does the battery last?", "spec", True),
    ("product-phones-z1", 2, "Does it work with Windows 7?", "spec", True),
    ("product-phones-z1", 3, "Does it work with Windows 8?", "spec", False),
    ("product-phones-z1", 4, "What is the screen size?", "spec", True),
    ("product-phones-z1", 5, "Is there a warranty on this phone?", "policy", None),
    ("product-phones-z1", 6, "Can I get a replacement if it breaks?", "spec", False),
    ("product-phones-k5", 1, "How much storage does it have?", "spec", True),
    ("product-phones-k5", 2, "Is the battery good?", "spec", True),
    ("product-phones-r1", 1, "Is the screen big?", "spec", False),
    ("product-laptops-o14", 1, "Is the keyboard backlit?", "spec", True),
    ("product-laptops-v15", 1, "How big is the screen?", "spec", True),
    ("product-electronics-b3", 1, "Do these fold flat?", "spec", True),
    ("product-electronics-s7", 1, "How long is the playback?", "spec", True),
    ("product-furniture-h1", 1, "Do the arms adjust?", "spec", True),
    ("product-furniture-m2", 1, "What weight does it hold?", "spec", True),
]


def _items(products=PRODUCTS, lines=LINES):
    for doc_id, dept, title, specs in products:
        yield "product", {"doc_id": doc_id, "title": title, "category": dept, "specs": specs}
    for doc_id, line_no, text, tag, r2 in lines:
        dept = doc_id.split("-")[1]
        yield "question", {
            "doc_id": doc_id, "department": dept, "leaf": LEAF[dept], "line_no": line_no,
            "question_text": text, "question_type": "WH", "tag": tag, "r2_answerable": r2,
        }


@pytest.fixture
def inputs():
    return load_inputs(_items(), POLICY_DIR)


def _rows_file(tmp_path, rows, name="batch.rows.jsonl"):
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def _import(tmp_path, inputs, rows, name="batch.rows.jsonl"):
    layer = tmp_path / "layer.jsonl"
    return import_rows(_rows_file(tmp_path, rows, name), layer, inputs, RULES_SHA), layer


def _rejected(report, key):
    return [p for _, k, ps in report.rejects if k == key for p in ps]


NAMES = {
    "product-phones-z1": "Zenvo X2", "product-phones-k5": "Kestrel M5",
    "product-phones-r1": "Zenvo X1", "product-laptops-o14": "Orbis 14 Pro",
    "product-laptops-v15": "Vantor 15 Air", "product-electronics-b3": "Brava Q3",
    "product-electronics-s7": "Solace H7", "product-furniture-h1": "Halden Task Chair",
    "product-furniture-m2": "Marlow Mesh",
}


def _name_rows():
    return [{"key": f"name:{d}", "type": "name", "name": n} for d, n in NAMES.items()]


def _complete_label_round(tmp_path, inputs):
    """Every label-round task done, answerable where the record says so."""
    evidence = {
        "product-phones-z1:1": ("Up to 2 days.", "battery lasts up to 2 days"),
        "product-phones-z1:2": ("Yes.", "Works with Windows 7 for file transfer"),
        "product-phones-z1:4": ("6.2 inches.", "6.2 inch display with 64GB"),
        "product-phones-k5:1": ("32GB.", "5.8 inch display with 32GB of storage"),
        "product-phones-k5:2": ("Up to 1 day.", "Battery lasts up to 1 day"),
        "product-laptops-o14:1": ("Yes.", "Backlit keyboard with two brightness levels"),
        "product-laptops-v15:1": ("15.6 inches.", "Full HD screen of 15.6 inches"),
        "product-electronics-b3:1": ("Yes.", "Folds flat into the hard case"),
        "product-electronics-s7:1": ("20 hours.", "20 hours of playback"),
        "product-furniture-h1:1": ("Yes, by 8 cm.", "Arms adjust up and down by 8 cm"),
        "product-furniture-m2:1": ("Up to 100 kg.", "Holds up to 100 kg"),
    }
    layer = tmp_path / "layer.jsonl"
    layer.write_text("")

    def answer(ref, type_, key):
        if ref in evidence:
            a, e = evidence[ref]
            return {"key": key, "type": type_, "answerable": True, "answer": a, "evidence": e}
        return {"key": key, "type": type_, "answerable": False, "answer": "", "evidence": ""}

    rows = _name_rows()
    rows += [answer(t.context["ref"], "label", t.key) for t in label_tasks(inputs, {})
             if t.type == "label"]
    for t in label_tasks(inputs, {}):
        if t.type == "policy":
            rows.append({"key": t.key, "type": "policy", "assign": "policy-warranty-phones-domestic",
                         "shape": "term", "variant": "", "kind": None})
        if t.type == "natural":
            rows.append({"key": t.key, "type": "natural", "mark": "different",
                         "a_answer": "Yes.", "a_evidence": "Works with Windows 7 for file transfer",
                         "b_answer": "No.", "b_evidence": "Works with Windows 7 for file transfer"})
    report = import_rows(_rows_file(tmp_path, rows, "p1.jsonl"), layer, inputs, RULES_SHA)
    assert not report.rejects, report.rejects
    relabels = [answer(t.context["ref"], "relabel", t.key)
                for t in open_tasks(inputs, load_layer(layer), "label") if t.type == "relabel"]
    report = import_rows(_rows_file(tmp_path, relabels, "p1b.jsonl"), layer, inputs, RULES_SHA)
    assert not report.rejects, report.rejects
    return layer


# =================================================================================================
# Tokens
# =================================================================================================
def test_the_check_tokenizer_keeps_digits_and_one_character_tokens():
    """Impact F12: the probe's tokenizer drops both, so "Windows 7" and "Windows 8" merge."""
    assert token_set("Does it work with Windows 7?") == {"does", "work", "windows", "7"}
    assert token_set("Windows 7") != token_set("Windows 8")


def test_names_product_needs_the_name_whole_and_in_order():
    assert names_product("How long does the Zenvo X2 battery last?", "Zenvo X2")
    assert not names_product("How long does the X2 Zenvo battery last?", "Zenvo X2")
    assert not names_product("How long does the Zenvo X20 battery last?", "Zenvo X2")


# =================================================================================================
# Policy shapes (T20)
# =================================================================================================
def test_shapes_map_by_heading_text_not_position():
    """T20, review L1: the warranty files run covers -> does not cover -> claim -> remedy -> proof."""
    paragraphs = [
        "Opening paragraph with the term.",
        "What the warranty covers", "Covers defects.",
        "What the warranty does not cover", "Not drops.",
        "How to make a claim", "Write to us.",
        "Repair, replacement or refund", "We repair it.",
        "Proof of purchase and transfer", "Keep the receipt.",
    ]
    doc = {"doc_id": "policy-warranty-x", "text": "\n\n".join(paragraphs)}
    sections = policy_sections(doc)
    assert sections["except"] == "Not drops." and sections["start"] == "Write to us."
    assert sections["term"] == "Opening paragraph with the term."


def test_every_real_policy_document_maps_to_six_shapes():
    for path in sorted(POLICY_DIR.glob("*.json")):
        sections = policy_sections(json.loads(path.read_text()))
        assert set(sections) == set(SHAPES) and all(sections.values()), path.name


def test_an_unknown_heading_stops_rather_than_joining_a_section():
    doc = {"doc_id": "policy-x", "text": "Term.\n\nWhat to send back\n\nBody.\n\nShipping costs\n\nBody."}
    with pytest.raises(WorkloadStop, match="unknown heading"):
        policy_sections(doc)


# =================================================================================================
# The task plan
# =================================================================================================
def test_windows_7_and_8_on_one_product_are_a_natural_pair_candidate(inputs):
    """T16 (first half): the pair is offered to Claude to mark; the build merges it into one cluster
    only on a `same` mark."""
    pairs = {(a.ref, b.ref) for a, b, _ in natural_candidates(inputs)}
    assert ("product-phones-z1:2", "product-phones-z1:3") in pairs


def test_pass_1_labels_every_r2_answerable_question_and_the_sample(inputs):
    refs = {t.context["ref"] for t in label_tasks(inputs, {}) if t.type == "label"}
    assert "product-phones-z1:1" in refs  # R2-answerable
    assert "product-phones-z1:3" in refs  # R2-unanswerable, inside the per-department sample
    assert "product-phones-z1:5" not in refs  # a policy question is assigned, not labelled


def test_the_wider_policy_list_catches_a_replacement_question(inputs):
    refs = {t.context["ref"] for t in label_tasks(inputs, {}) if t.type == "policy"}
    assert refs == {"product-phones-z1:5", "product-phones-z1:6"}


def test_a_relabel_opens_only_after_its_first_label(tmp_path, inputs):
    """RELABEL: the repeat is in a later batch, so it is not open in the first one."""
    assert not [t for t in label_tasks(inputs, {}) if t.type == "relabel"]
    report, layer = _import(tmp_path, inputs, [{
        "key": "label:product-phones-z1:1", "type": "label", "answerable": True,
        "answer": "Up to 2 days.", "evidence": "battery lasts up to 2 days"}])
    assert not report.rejects
    keys = {t.key for t in label_tasks(inputs, load_layer(layer)) if t.type == "relabel"}
    assert "relabel:product-phones-z1:1" in keys


def test_the_write_round_opens_only_when_the_label_round_is_complete(tmp_path, inputs):
    report, layer = _import(tmp_path, inputs, _name_rows())
    assert not report.rejects and write_tasks(inputs, load_layer(layer)) == []
    layer = _complete_label_round(tmp_path, inputs)
    assert write_tasks(inputs, load_layer(layer))


def test_seeds_skip_natural_candidates_and_take_answerable_labels(tmp_path, inputs):
    layer = load_layer(_complete_label_round(tmp_path, inputs))
    seeds = {t.context["ref"] for t in write_tasks(inputs, layer)
             if t.type == "seed" and t.context["role"] == "seed"}
    assert "product-phones-z1:2" not in seeds  # a natural candidate
    assert {"product-phones-z1:1", "product-phones-z1:4"} <= seeds


def test_units_are_pairs_with_one_closing_triple_per_odd_leaf(inputs):
    units = make_units(inputs)
    phones = [u for u in units if u[0].startswith("product-phones")]
    assert len(phones) == 1 and len(phones[0]) == 3  # three phones: one triple
    assert sorted(d for u in units for d in u) == sorted(d for d, *_ in PRODUCTS)


def test_swaps_go_both_ways_in_a_pair_and_round_a_triple():
    assert swap_directions([("a", "b")]) == [("a", "b"), ("b", "a")]
    assert swap_directions([("a", "b", "c")]) == [("a", "b"), ("b", "c"), ("c", "a")]


def test_a_swap_that_leaves_a_word_unique_to_the_first_product_is_dropped(inputs):
    """R6, review M5 d."""
    q = swap_question("Is the Zenvo X2 Blue the 64GB model?", "Zenvo X2", "Kestrel M5")
    assert q == "Is the Kestrel M5 Blue the 64GB model?"
    assert swap_leftover(inputs, q, "product-phones-z1", "product-phones-k5") == ["64gb", "blue"]
    clean = swap_question("How long does the Zenvo X2 battery last?", "Zenvo X2", "Kestrel M5")
    assert swap_leftover(inputs, clean, "product-phones-z1", "product-phones-k5") == []


def test_policy_cells_pair_twins_regions_and_kinds_on_the_same_products(tmp_path, inputs):
    layer = load_layer(_complete_label_round(tmp_path, inputs))
    cells = {c.cell_id: c for c in plan_cells(inputs, layer)}
    assert not any((c.doc_id, c.shape) in REPLACED and not c.variant
                   and c.twin_group is None for c in cells.values())
    fee_o = cells["policy-return-phones-opened:term:fee"]
    fee_u = cells["policy-return-phones-unopened:term:fee"]
    assert fee_o.products == fee_u.products and fee_o.pair_cell == fee_u.cell_id
    assert "product-phones-r1" not in fee_o.products  # risky: "Renewed" in the title
    intl = cells["policy-warranty-phones-international:what"]
    assert intl.probe_kind == "policy-region"
    assert intl.products == cells["policy-warranty-phones-domestic:what"].products
    kind = cells["policy-warranty-electronics:term"]
    assert kind.probe_kind == "policy-kind" and kind.pair_cell == "policy-return-electronics:term"
    assert kind.products == cells["policy-return-electronics:term"].products
    dept = cells["policy-return-laptops-renewed:term:dept"]
    assert dept.products == () and dept.wordings == TWIN_WORDINGS_DEPT
    ordinary = [c for c in cells.values() if c.twin_group is None]
    assert len(ordinary) == 66 and len(cells) == 74


def test_blind_keys_do_not_show_the_role_or_the_seed():
    key = blind_key("para:product-phones-z1:1:far")
    assert key.startswith("blind:") and "para" not in key and "z1" not in key


# =================================================================================================
# Import mechanics
# =================================================================================================
def test_an_import_stores_the_derived_fields_and_skips_an_identical_repeat(tmp_path, inputs):
    rows = [{"key": "name:product-phones-z1", "type": "name", "name": "Zenvo X2"}]
    report, layer = _import(tmp_path, inputs, rows)
    assert report.accepted["name"] == 1
    stored = load_layer(layer)["name:product-phones-z1"]
    assert stored["doc_id"] == "product-phones-z1" and stored["_rules"] == RULES_SHA[:16]
    again = import_rows(_rows_file(tmp_path, rows, "again.jsonl"), layer, inputs, RULES_SHA)
    assert again.skipped == 1 and not again.rejects


def test_an_import_never_overwrites_a_row(tmp_path, inputs):
    _, layer = _import(tmp_path, inputs, [{"key": "name:product-phones-z1", "type": "name",
                                           "name": "Zenvo X2"}])
    other = [{"key": "name:product-phones-z1", "type": "name", "name": "Zenvo X2 Smartphone"}]
    report = import_rows(_rows_file(tmp_path, other, "o.jsonl"), layer, inputs, RULES_SHA)
    assert "already in the model layer with other content" in _rejected(report, other[0]["key"])


def test_an_import_rejects_unknown_fields_and_tasks_that_are_not_open(tmp_path, inputs):
    rows = [
        {"key": "name:product-phones-z1", "type": "name", "name": "Zenvo X2", "note": "x"},
        {"key": "seed:product-phones-z1:1", "type": "seed", "question": "?"},
        {"key": "name:product-phones-nope", "type": "name", "name": "Nope Phone"},
    ]
    report, _ = _import(tmp_path, inputs, rows)
    assert "fields not in a name row: ['note']" in _rejected(report, rows[0]["key"])[0]
    assert "not an open task" in _rejected(report, rows[1]["key"])[0]
    assert "not an open task" in _rejected(report, rows[2]["key"])[0]


def test_every_row_type_has_a_fixed_field_list():
    assert claude_fields("seed") == {"key", "type", "question"}
    assert claude_fields("cell") == {"key", "type", "wordings", "origin", "source"}


# =================================================================================================
# T10: each check, one row on each side of its edge
# =================================================================================================
@pytest.mark.parametrize(
    "name,ok",
    [("Zenvo X2", True), ("Zenvo", False), ("Zenvo X2 Smartphone 64GB Blue X2 Zenvo", False),
     ("Zenvo X3", False), ("Zenvo X2 é", False)],
)
def test_r1_names(tmp_path, inputs, name, ok):
    report, _ = _import(tmp_path, inputs, [{"key": "name:product-phones-z1", "type": "name",
                                            "name": name}])
    assert (not report.rejects) == ok, report.rejects


def test_r1_names_are_unique(tmp_path):
    twins = [("product-phones-a", "phones", "Zenvo X2 Phone", {"Feature 1": "A phone."}),
             ("product-phones-b", "phones", "Zenvo X2 Phone Pro", {"Feature 1": "A phone."})]
    lines = [("product-phones-a", 1, "Is it light?", "spec", True),
             ("product-phones-b", 1, "Is it light?", "spec", True)]
    inputs = load_inputs(_items(twins, lines), POLICY_DIR)
    rows = [{"key": "name:product-phones-a", "type": "name", "name": "Zenvo X2"},
            {"key": "name:product-phones-b", "type": "name", "name": "zenvo x2"}]
    report, _ = _import(tmp_path, inputs, rows)
    assert "already the short name of another product" in _rejected(report, rows[1]["key"])[0]


@pytest.mark.parametrize(
    "answer,evidence,ok",
    [
        ("Up to 2 days.", "battery lasts up to 2 days", True),
        ("Up to 2 days.", "battery  lasts\nup to 2 days", True),  # white space collapses
        ("Up to 2 days.", "Battery lasts up to 2 days", False),  # verbatim: case counts
        ("Up to 2 days.", "lasts up", False),  # under 3 words
        ("Up to 2 days.", "The 4000 mAh battery lasts up to 2 days on one charge and more", False),
        ("", "battery lasts up to 2 days", False),
        ("Up to\n2 days.", "battery lasts up to 2 days", False),
    ],
)
def test_r2_labels(tmp_path, inputs, answer, evidence, ok):
    row = {"key": "label:product-phones-z1:1", "type": "label", "answerable": True,
           "answer": answer, "evidence": evidence}
    report, _ = _import(tmp_path, inputs, [row])
    assert (not report.rejects) == ok, report.rejects


def test_r2_an_unanswerable_label_carries_no_evidence(tmp_path, inputs):
    row = {"key": "label:product-phones-z1:1", "type": "label", "answerable": False,
           "answer": "", "evidence": "battery lasts up to 2 days"}
    report, _ = _import(tmp_path, inputs, [row])
    assert report.rejects


def test_r7_assignments(tmp_path, inputs):
    rows = [
        {"key": "policy:product-phones-z1:5", "type": "policy",
         "assign": "policy-warranty-laptops", "shape": "term", "variant": "", "kind": None},
        {"key": "policy:product-phones-z1:6", "type": "policy", "assign": "ambiguous",
         "shape": "remedy", "variant": "fee", "kind": "return"},
    ]
    report, _ = _import(tmp_path, inputs, rows)
    assert "not a phones document" in _rejected(report, rows[0]["key"])[0]
    assert "only for a phones return `term`" in _rejected(report, rows[1]["key"])[0]


def test_r9_a_same_or_different_mark_needs_evidence_for_both(tmp_path, inputs):
    key = "natural:product-phones-z1:2:3"
    row = {"key": key, "type": "natural", "mark": "different", "a_answer": "Yes.",
           "a_evidence": "Works with Windows 7 for file transfer", "b_answer": "", "b_evidence": ""}
    report, _ = _import(tmp_path, inputs, [row])
    assert any(p.startswith("b_") for p in _rejected(report, key))


def _write_round(tmp_path, inputs):
    layer = _complete_label_round(tmp_path, inputs)
    return layer, {t.key: t for t in write_tasks(inputs, load_layer(layer))}


def _write(tmp_path, inputs, layer, rows, name="w.jsonl"):
    return import_rows(_rows_file(tmp_path, rows, name), layer, inputs, RULES_SHA)


SEED_KEY = "seed:product-phones-z1:1"


@pytest.mark.parametrize(
    "question,ok",
    [
        ("How long does the Zenvo X2 battery last?", True),
        ("How long does the battery last?", False),  # no short name
        ("How long does the Zenvo X2 battery last in 3 days?", False),  # a digit added
        ("Does the Zenvo X2 battery last?", True),  # the name's own 2 is not a new digit
        ("How long does the Zenvo X2 battery last? Really?", False),  # two questions
        ("How long does the Zenvo X2 battery last", False),
        ("How long does the Zenvo X2 battery last — really?", False),  # not ASCII
        ("How " + "very " * 26 + "long does the Zenvo X2 last?", False),  # over 30 words
    ],
)
def test_r3_rewrites(tmp_path, inputs, question, ok):
    layer, _ = _write_round(tmp_path, inputs)
    report = _write(tmp_path, inputs, layer, [{"key": SEED_KEY, "type": "seed",
                                               "question": question}])
    assert (not report.rejects) == ok, report.rejects


def test_r4_rejects_a_paraphrase_that_adds_a_record_word(tmp_path, inputs):
    """T21, review M5 b: "charge" is in the record and not in the seed; it can change the answer."""
    layer, _ = _write_round(tmp_path, inputs)
    seed = {"key": SEED_KEY, "type": "seed", "question": "How long does the Zenvo X2 battery last?"}
    good = {"key": "para:product-phones-z1:1:close", "type": "para",
            "question": "How long will the Zenvo X2 battery last?"}
    bad = {"key": "para:product-phones-z1:1:far", "type": "para",
           "question": "On one charge, how long does the Zenvo X2 keep going?"}
    report = _write(tmp_path, inputs, layer, [bad, good, seed])  # the seed is checked first
    assert report.accepted["seed"] == 1 and report.accepted["para"] == 1
    assert "record words the seed lacks: charge" in _rejected(report, bad["key"])[0]


def test_w5_a_query_whose_tier1_form_is_taken_is_rejected(tmp_path, inputs):
    layer, _ = _write_round(tmp_path, inputs)
    seed = {"key": SEED_KEY, "type": "seed", "question": "How long does the Zenvo X2 battery last?"}
    para = {"key": "para:product-phones-z1:1:close", "type": "para",
            "question": "how long does the zenvo x2 battery last?"}
    report = _write(tmp_path, inputs, layer, [seed, para])
    assert "Tier-1 form" in _rejected(report, para["key"])[0]


def test_r5_a_lookalike_needs_its_own_evidence(tmp_path, inputs):
    """T22: a probe is kept only when its evidence differs from the seed's."""
    layer, tasks = _write_round(tmp_path, inputs)
    key = next(k for k in tasks if k.startswith("lookalike:product-phones-z1:"))
    seed_ref = key.split(":", 1)[1]
    seed_q = {"product-phones-z1:1": "How long does the Zenvo X2 battery last?",
              "product-phones-z1:4": "What is the screen size of the Zenvo X2?"}[seed_ref]
    seed_ev = first_labels(load_layer(layer))[seed_ref]["evidence"]
    seed = {"key": f"seed:{seed_ref}", "type": "seed", "question": seed_q}
    copy = {"key": key, "type": "lookalike", "question": "Does the Zenvo X2 charge fast?",
            "attribute": "charging", "answer": "It says so.", "evidence": seed_ev}
    report = _write(tmp_path, inputs, layer, [seed, copy])
    assert "overlaps the seed's evidence" in _rejected(report, key)[0]
    own = {**copy, "evidence": "a fast charger in the box"}
    report = _write(tmp_path, inputs, layer, [own], "own.jsonl")
    assert not _rejected(report, key), report.rejects


def test_r5_a_yes_no_lookalike_needs_the_other_polarity(tmp_path, inputs):
    layer, tasks = _write_round(tmp_path, inputs)
    key = next(k for k in tasks if k.startswith("lookalike:product-laptops-o14:"))
    seed = {"key": "seed:product-laptops-o14:1", "type": "seed",
            "question": "Is the Orbis 14 Pro keyboard backlit?"}
    same = {"key": key, "type": "lookalike", "question": "Does the Orbis 14 Pro weigh 1.3 kg?",
            "attribute": "weight", "answer": "Yes.", "evidence": "Weighs 1.3 kg with the battery"}
    report = _write(tmp_path, inputs, layer, [seed, same])
    assert "the same yes / no" in _rejected(report, key)[0]


def _cell_row(cell_id, wordings, origin="claude", source=None):
    return {"key": f"cell:{cell_id}", "type": "cell", "wordings": wordings, "origin": origin,
            "source": source}


@pytest.mark.parametrize(
    "cell_id,wording,problem",
    [
        ("policy-return-phones-opened:term:fee",
         "Is there a restocking fee if I return the {name} once it has been opened?", None),
        ("policy-return-phones-opened:term:fee",
         "Is there a restocking fee if I return the {name} after use?",
         "does not name its condition"),
        ("policy-return-phones-opened:term:fee",
         "Is there a restocking fee on an opened {name} that was still sealed?", "unopened"),
        ("policy-return-phones-opened:term:fee",
         "Is there a restocking fee if I return the opened phone?", "'{name}' exactly once"),
        ("policy-return-electronics:what",
         "What must I send back with the {name} under the warranty?", "kind = warranty"),
        ("policy-warranty-furniture:term", "How long is the warranty on the {name}?", None),
    ],
)
def test_r7_cell_wordings(tmp_path, inputs, cell_id, wording, problem):
    layer, _ = _write_round(tmp_path, inputs)
    report = _write(tmp_path, inputs, layer, [_cell_row(cell_id, [wording])])
    found = _rejected(report, f"cell:{cell_id}")
    if problem is None:
        assert not found, found
    else:
        assert any(problem in p for p in found), found


def test_r10_rejects_a_wording_that_shares_four_words_with_a_policy_document(tmp_path, inputs):
    """T23, review M6 b: the opened phones document says "inspected, cleaned and repackaged
    before it can be sold again"."""
    layer, _ = _write_round(tmp_path, inputs)
    copied = ("Is the opened {name} inspected, cleaned and repackaged before it can be sold "
              "again, with a restocking fee?")
    report = _write(tmp_path, inputs, layer,
                    [_cell_row("policy-return-phones-opened:term:fee", [copied])])
    assert any("(R10)" in p for p in _rejected(report, "cell:policy-return-phones-opened:term:fee"))


def test_r7_department_level_wordings_name_no_product(tmp_path, inputs):
    layer, _ = _write_round(tmp_path, inputs)
    wordings = [f"How many days do I have to return a renewed laptop, case {i}?" for i in range(7)]
    wordings.append("How many days do I have to return the renewed {name}?")
    report = _write(tmp_path, inputs, layer,
                    [_cell_row("policy-return-laptops-renewed:term:dept", wordings)])
    assert any("names no product" in p
               for p in _rejected(report, "cell:policy-return-laptops-renewed:term:dept"))


def test_r7_a_template_names_a_real_question_assigned_to_its_cell(tmp_path, inputs):
    layer, _ = _write_round(tmp_path, inputs)
    good = _cell_row("policy-warranty-phones-domestic:term",
                     ["How long is the domestic warranty on the {name}?"],
                     origin="pqa-template", source="product-phones-z1:5")
    wrong = _cell_row("policy-warranty-phones-domestic:what",
                      ["What does the domestic warranty on the {name} cover?"],
                      origin="pqa-template", source="product-phones-z1:5")
    report = _write(tmp_path, inputs, layer, [good, wrong])
    assert not _rejected(report, good["key"])
    assert "another kind, department or shape" in _rejected(report, wrong["key"])[0]


def test_r8_a_d_answer_holds_the_documents_term(tmp_path, inputs):
    layer, tasks = _write_round(tmp_path, inputs)
    key = next(k for k in tasks if k.startswith("d:product-phones"))
    policy = tasks[key].context["policy"]
    name = NAMES[key[2:]]
    term = json.loads((POLICY_DIR / f"{policy}.json").read_text())["terms"][0]
    cond = "domestic" if policy.endswith("domestic") else ("unopened" if "unopened" in policy else "")
    q = f"How big is the screen of the {cond} {name}, and how long is its warranty?"
    if "return" in policy:
        q = f"How big is the screen of the {cond} {name}, and when must I send it back?"
    ev = {"Zenvo X2": "6.2 inch display with 64GB", "Kestrel M5": "5.8 inch display with 32GB"}[name]
    good = {"key": key, "type": "d", "question": q, "answer": f"6 inches; {term}.", "evidence": ev}
    report = _write(tmp_path, inputs, layer, [good])
    assert not _rejected(report, key), report.rejects
    bad = {**good, "key": key, "answer": "6 inches."}
    layer2 = tmp_path / "second"
    layer2.mkdir()
    layer2, _ = _write_round(layer2, inputs)
    report = _write(tmp_path, inputs, layer2, [bad], "bad.jsonl")
    assert "holds none of the document's terms" in _rejected(report, key)[0]


# =================================================================================================
# The check round
# =================================================================================================
def test_the_check_round_opens_a_blind_label_for_each_written_query(tmp_path, inputs):
    layer, _ = _write_round(tmp_path, inputs)
    seed = {"key": SEED_KEY, "type": "seed", "question": "How long does the Zenvo X2 battery last?"}
    _write(tmp_path, inputs, layer, [seed])
    targets = {t.context["target"] for t in check_tasks(inputs, load_layer(layer))
               if t.type == "blind"}
    assert targets == {SEED_KEY}


# =================================================================================================
# Sheets (T15)
# =================================================================================================
def test_sheets_are_refused_inside_the_repository(tmp_path, monkeypatch, inputs):
    """T15: a sheet holds PQA text and asins. The repository root is pointed at a temporary
    folder, so a broken refusal writes there and never into the real repository."""
    import build_workload

    monkeypatch.setattr(build_workload, "REPO_ROOT", tmp_path / "repo")
    inside = tmp_path / "repo" / "data" / "sheets"
    with pytest.raises(WorkloadStop, match="inside the repository"):
        write_sheets(inputs, {}, "label", inside, RULES_SHA)
    assert not inside.exists()


def test_sheets_hold_one_skeleton_per_open_task(tmp_path, inputs):
    out = tmp_path / "sheets"
    paths = write_sheets(inputs, {}, "label", out, RULES_SHA, per_sheet=4)
    text = "\n".join(p.read_text() for p in paths)
    skeletons = [json.loads(m) for m in re.findall(r"```json\n(.*?)\n```", text)]
    assert sorted(s["key"] for s in skeletons) == sorted(t.key for t in label_tasks(inputs, {}))
    assert len(paths) == 3  # nine products, four a sheet


# =================================================================================================
# rules.md states the constants (W18)
# =================================================================================================
def test_rules_md_states_every_constant():
    import build_workload

    if not RULES_PATH.is_file():
        pytest.skip("rules.md is written in the same step")
    text = RULES_PATH.read_text()
    for name in CONSTANTS:
        value = getattr(build_workload, name)
        shown = value if not isinstance(value, tuple) else f"{value[0]} – {value[1]}"
        assert re.search(rf"`{name}`\s*\|\s*`?{re.escape(str(shown))}`?", text), name


# =================================================================================================
# W3: 3.2's drafts are read only through iter_selection, which stops on a mismatch
# =================================================================================================
def test_a_missing_or_changed_selection_stops_before_anything_is_read(tmp_path):
    with pytest.raises(WorkloadStop, match="do not match their manifest"):
        read_inputs(tmp_path / "pqa-selection.json", tmp_path / "drafts", POLICY_DIR)


# =================================================================================================
# Plan step 6: the build. A complete synthetic model layer, written straight into the layer the
# way the import stores rows (the import's checks are tested above), and a fake embedder.
# =================================================================================================
EVIDENCE = {
    "product-phones-z1:1": ("Up to 2 days.", "battery lasts up to 2 days"),
    "product-phones-z1:2": ("Yes.", "Works with Windows 7 for file transfer"),
    "product-phones-z1:4": ("6.2 inches.", "6.2 inch display with 64GB"),
    "product-phones-k5:1": ("32GB.", "5.8 inch display with 32GB of storage"),
    "product-phones-k5:2": ("Up to 1 day.", "Battery lasts up to 1 day"),
    "product-laptops-o14:1": ("Yes.", "Backlit keyboard with two brightness levels"),
    "product-laptops-v15:1": ("15.6 inches.", "Full HD screen of 15.6 inches"),
    "product-electronics-b3:1": ("Yes.", "Folds flat into the hard case"),
    "product-electronics-s7:1": ("20 hours.", "20 hours of playback"),
    "product-furniture-h1:1": ("Yes, by 8 cm.", "Arms adjust up and down by 8 cm"),
    "product-furniture-m2:1": ("Up to 100 kg.", "Holds up to 100 kg"),
}


def _tag(key):
    return hashlib.sha256(key.encode()).hexdigest()[:6]


def _cond_word(inputs, doc_id):
    cond = inputs.policies[doc_id].get("condition")
    return corpus_gate.CONDITION_AXES[cond["axis"]][cond["value"]][0] if cond else ""


def _auto_row(task, inputs, layer):
    """A valid row for any task, the way a careful writer would fill it."""
    key, t, c = task.key, task.type, task.context
    names = build_workload.short_names(layer)
    if t == "name":
        return {"key": key, "type": t, "name": NAMES[task.group]}
    if t in ("label", "relabel"):
        ans = EVIDENCE.get(c["ref"])
        return {"key": key, "type": t, "answerable": bool(ans), "answer": ans[0] if ans else "",
                "evidence": ans[1] if ans else ""}
    if t == "policy":
        return {"key": key, "type": t, "assign": "policy-warranty-phones-domestic",
                "shape": "term", "variant": "", "kind": None}
    if t == "natural":
        ev = "Works with Windows 7 for file transfer"
        return {"key": key, "type": t, "mark": "different", "a_answer": "Yes.", "a_evidence": ev,
                "b_answer": "No.", "b_evidence": ev}
    if t in ("seed", "para"):
        return {"key": key, "type": t,
                "question": f"What about the {names[task.group]}, case {_tag(key)}?"}
    if t == "lookalike":
        ev = inputs.products[task.group].fields[-1][1]
        return {"key": key, "type": t, "question": f"Is the {names[task.group]} {_tag(key)}?",
                "attribute": "other", "answer": "No.", "evidence": ev}
    if t == "d":
        doc = inputs.policies[c["policy"]]
        return {"key": key, "type": t,
                "question": f"What about the {_cond_word(inputs, doc['doc_id'])} "
                            f"{names[task.group]} {_tag(key)}?",
                "answer": f"It is {doc['terms'][0]}.",
                "evidence": inputs.products[task.group].fields[-1][1]}
    if t == "cell":
        cell = c["cell"]
        word = _cond_word(inputs, cell.doc_id)
        doc = inputs.policies[cell.doc_id]
        stem = f"For {doc['policy_kind']} {cell.shape} {cell.variant} {doc['category']}".strip()
        if cell.variant == "dept":
            ws = [f"{stem}, what applies to a {word} laptop, case {i}?" for i in range(cell.wordings)]
        else:
            ws = [f"{stem}, what applies to the {{name}}" + (f" when {word}" if word else "") + "?"]
        return {"key": key, "type": t, "wordings": ws, "origin": "claude", "source": None}
    if t == "blind":
        target = layer[c["target"]]
        labels = first_labels(layer)
        if target["type"] == "lookalike":
            return {"key": key, "type": t, "answerable": True, "answer": "No.",
                    "evidence": target["evidence"]}
        ref = target["ref"]
        if target["type"] == "seed" and target["role"] == "natural":
            nat = next(r for r in layer.values() if r["type"] == "natural" and ref in (r["a"], r["b"]))
            side = "a" if nat["a"] == ref else "b"
            return {"key": key, "type": t, "answerable": True, "answer": "x",
                    "evidence": nat[f"{side}_evidence"]}
        label = labels[ref]
        return {"key": key, "type": t, "answerable": label["answerable"],
                "answer": label["answer"], "evidence": label["evidence"]}
    if t == "swap":
        return {"key": key, "type": t, "answerable": True, "answer": "Maybe.",
                "evidence": inputs.products[task.group].fields[-1][1], "same_answer": False}
    raise ValueError(t)


def _auto_layer(inputs):
    layer = {}
    for round_ in ROUNDS:
        while True:
            tasks = build_workload.open_tasks(inputs, layer, round_)
            if not tasks:
                break
            for task in tasks:
                row = _auto_row(task, inputs, layer)
                layer[task.key] = {**row, **derived(task, inputs), "_batch": "t", "_round": round_}
    return layer


def _fake_embed(text):
    digest = hashlib.sha256(text.encode()).digest()
    return [b / 255 - 0.5 for b in digest[:8]]


@pytest.fixture
def complete(inputs, monkeypatch):
    """A complete layer and its vectors. Nine products cannot reach 30 minimal-pair twins a
    split, so the floor is lowered here; T19 tests it at its real value."""
    monkeypatch.setattr(build_workload, "MIN_TWINS_PER_SPLIT", 1)
    layer = _auto_layer(inputs)
    return layer, embed_all(inputs, layer, _fake_embed)


def test_t1_every_record_has_one_stratum_one_split_and_one_cluster(inputs, complete):
    workload = build(inputs, *complete)
    assert workload.records
    for r in workload.records:
        assert r.stratum in corpus_gate.STRATA and r.split in corpus_gate.SPLITS and r.cluster_id


def test_t3_a_question_changed_after_embedding_stops_the_build(inputs, complete):
    layer, vectors = complete
    key = next(k for k, r in layer.items() if r["type"] == "seed")
    layer[key] = {**layer[key], "question": layer[key]["question"].replace("case", "item")}
    with pytest.raises(WorkloadStop, match="no current vector"):
        build(inputs, layer, vectors)


def test_t3_the_build_needs_every_round_complete(inputs, complete):
    layer, vectors = complete
    del layer[next(k for k, r in layer.items() if r["type"] == "blind")]
    with pytest.raises(WorkloadStop, match="round check has 1 open task"):
        build(inputs, layer, vectors)


DRIVER = """
import json, sys, hashlib
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import build_workload as b
b.MIN_TWINS_PER_SPLIT = 1
inputs = b.load_inputs(iter(json.load(open(sys.argv[2]))), b.POLICY_DIR)
w = b.build(inputs, b.load_layer(Path(sys.argv[3])), json.load(open(sys.argv[4])))
files = b.output_files(w)
blob = b"".join(files[k] for k in sorted(files)) + b.canonical(b.make_manifest(w, files, {}))
print(hashlib.sha256(blob).hexdigest())
"""


def test_t4_outputs_are_byte_identical_under_two_hash_seeds(tmp_path, inputs, complete):
    """W4: no set or dict order may reach an output."""
    layer, vectors = complete
    (tmp_path / "items.json").write_text(json.dumps([list(i) for i in _items()]))
    (tmp_path / "layer.jsonl").write_text("".join(json.dumps(r) + "\n" for r in layer.values()))
    (tmp_path / "vectors.json").write_text(json.dumps(vectors))
    scripts = os.path.dirname(build_workload.__file__)
    digests = set()
    for seed in ("0", "1"):
        out = subprocess.run(
            [sys.executable, "-c", DRIVER, scripts, str(tmp_path / "items.json"),
             str(tmp_path / "layer.jsonl"), str(tmp_path / "vectors.json")],
            capture_output=True, text=True, env={**os.environ, "PYTHONHASHSEED": seed}, check=False,
        )
        assert out.returncode == 0, out.stderr
        digests.add(out.stdout.strip())
    assert len(digests) == 1


def test_t5_two_records_with_one_tier1_form_stop_the_build(inputs, complete):
    layer, vectors = complete
    seeds = [k for k, r in layer.items() if r["type"] == "seed" and r["role"] == "seed"]
    first = layer[seeds[0]]["question"]
    layer[seeds[1]] = {**layer[seeds[1]], "question": first.upper()}
    vectors = embed_all(inputs, layer, _fake_embed)
    with pytest.raises(WorkloadStop, match="Tier-1 form"):
        build(inputs, layer, vectors)


def test_t6_a_risky_product_or_an_unknown_doc_id_stops_the_check(inputs, complete):
    workload = build(inputs, *complete)
    rec = next(r for r in workload.records if r.doc_ids[0].startswith("policy-") and r.product_id)
    rec.product_id = "product-phones-r1"  # "Renewed" in the title
    with pytest.raises(WorkloadStop, match="risky product"):
        build_workload.check_workload(inputs, workload.records)
    rec.product_id = None
    rec.doc_ids = ("policy-return-nowhere",)
    with pytest.raises(WorkloadStop, match="not in the corpus"):
        build_workload.check_workload(inputs, workload.records)


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def test_t7_the_manifest_holds_no_question_no_doc_id_and_no_qa_id(inputs, complete):
    """W9: the tracked manifest is hashes and counts only."""
    workload = build(inputs, *complete)
    files = output_files(workload)
    manifest = make_manifest(workload, files, {"selection_sha256": "a" * 64})
    questions = {r.question for r in workload.records}
    for s in _strings(manifest):
        assert "product-" not in s and not s.startswith("q-") and s not in questions, s
        assert "z1" not in s and "k5" not in s, s


def test_t8_the_rank_holds_every_prefix_within_one_of_its_share():
    """W11, review L5: each stratum's count in any prefix is within one of its share, and the
    order inside a stratum is the hash, not the order the records were built in."""
    sizes = {"A": 9, "C": 5, "B-within": 3, "B-cross": 2, "D": 1}
    recs = [Record(f"q{s}{i}", "?", ("product-x",), "product-x", "c", "u", "seed", "pqa", True,
                   None, "phones", stratum=s) for s, n in sizes.items() for i in range(n)]
    ranked = rank(recs)
    n = len(ranked)
    for k in range(1, n + 1):
        prefix = ranked[:k]
        for s, size in sizes.items():
            assert abs(sum(r.stratum == s for r in prefix) - size * k / n) < 1, (s, k)
    a_order = [r.qa_id for r in ranked if r.stratum == "A"]
    assert a_order == sorted(a_order, key=lambda q: build_workload.h("rank", q))
    assert [r.popularity_rank for r in ranked] == list(range(1, n + 1))
    assert [r.stratum for r in ranked[:4]] != ["A"] * 4


def _rec(qa_id, product, cluster, pair_of=None, kind=None, doc_ids=None):
    return Record(qa_id, "?", tuple(doc_ids or [product or "policy-x"]), product, cluster, "u",
                  "seed", "pqa", True, None, "phones", pair_of=pair_of, probe_kind=kind)


def test_t9_stratum_precedence_one_case_each_and_a_cosine_of_exactly_085():
    a, b = [1.0, 0.0], [0.85, math.sqrt(1 - 0.85 ** 2)]
    assert corpus_gate.cosine(a, b) == 0.85  # the fixture's own edge
    target = _rec("t", "p1", "c1")
    cases = {
        "D": _rec("d", "p1", "c9", doc_ids=["product-p1", "policy-x"]),
        "B-within": _rec("w", "p1", "c2", pair_of="t", kind="spec-attribute"),
        "B-cross": _rec("x", "p2", "c3", pair_of="t", kind="name-swap"),
        "A": _rec("a", "p1", "c1"),
    }
    dept = _rec("dw", None, "c4", pair_of="t", kind="condition-department")
    by_id = {r.qa_id: r for r in [target, dept, *cases.values()]}
    vectors = {"t": a, "a": b, "d": a, "w": a, "x": a, "dw": a}
    for want, rec in cases.items():
        assert assign_stratum(rec, by_id, [target, rec], vectors) == want, want
    assert assign_stratum(dept, by_id, [dept], vectors) == "B-within"
    vectors["a"] = [0.84, math.sqrt(1 - 0.84 ** 2)]
    assert assign_stratum(cases["A"], by_id, [target, cases["A"]], vectors) == "C"


def test_t11_the_split_pairs_the_minimal_pair_groups_and_alternates_the_rest(inputs, complete):
    records, _ = construct(inputs, complete[0])
    split_of = assign_split(records, inputs)
    assert split_of == assign_split(records, inputs)  # determinism
    assert split_of["u-phones-term"] != split_of["u-phones-return-remedy"]
    assert split_of["u-furniture-term"] != split_of["u-laptops-term"]
    paired = {u for _, us in build_workload.TWIN_UNIT_PAIRS for u in us}
    dept = {r.split_unit: r.department for r in records}
    rest = sorted((u for u in split_of if not u.startswith("u-product-") and u not in paired),
                  key=lambda u: (dept[u], build_workload.h("policy-unit", u)))
    assert [split_of[u] for u in rest] == [corpus_gate.SPLITS[i % 2] for i in range(4, 4 + len(rest))]


def test_t11_every_axis_and_department_lands_in_both_splits(inputs, complete):
    workload = build(inputs, *complete)
    for axis in ("packaging", "grade", "region"):
        assert {r.split for r in workload.records if r.axis == axis} == set(corpus_gate.SPLITS)


def test_t12_a_name_swap_sits_in_its_targets_unit(inputs, complete):
    """B-cross is built inside a product-pair unit, so the split can never separate a swap from
    the seed it imitates."""
    workload = build(inputs, *complete)
    by_id = {r.qa_id: r for r in workload.records}
    swaps = [r for r in workload.records if r.probe_kind in ("name-swap", "name-swap-same")]
    assert swaps
    for r in swaps:
        assert r.split_unit == by_id[r.pair_of].split_unit and r.stratum == "B-cross"


def test_t13_twins_only_where_the_answers_differ(tmp_path, inputs):
    layer = load_layer(_complete_label_round(tmp_path, inputs))
    cells = {c.cell_id: c for c in plan_cells(inputs, layer)}
    assert cells["policy-return-phones-opened:term"].twin_group is None  # 14 days both: no twin
    assert cells["policy-return-phones-opened:term:fee"].twin_group == "phones-returns-term-fee"
    assert cells["policy-return-phones-opened:remedy"].twin_group == "phones-returns-remedy"
    assert cells["policy-return-electronics:what"].twin_group is None


def test_t16_a_windows_7_and_8_pair_marked_different_is_never_one_cluster(inputs, complete):
    workload = build(inputs, *complete)
    nat = [r for r in workload.records if r.probe_kind == "natural"]
    assert len(nat) == 2 and nat[0].cluster_id != nat[1].cluster_id
    assert {nat[0].pair_of, nat[1].pair_of} == {nat[0].qa_id, nat[1].qa_id}
    assert all(r.stratum == "B-within" for r in nat)


def test_t19_the_build_stops_below_30_minimal_pair_twins_a_split(inputs, complete, monkeypatch):
    monkeypatch.setattr(build_workload, "MIN_TWINS_PER_SPLIT", 30)
    with pytest.raises(WorkloadStop, match="minimal-pair twins, below 30"):
        build(inputs, *complete)


@pytest.mark.parametrize(
    "swap,seed,mark,want",
    [
        ("No.", "Yes.", True, "name-swap"),  # polarities decide, over the mark
        ("Yes, it does.", "Yes.", False, "name-swap-same"),
        ("About 3 days.", "Up to 2 days.", False, "name-swap"),  # no polarity: the mark
        ("About 2 days.", "Up to 2 days.", True, "name-swap-same"),
    ],
)
def test_t22_a_same_answer_swap_is_kept_but_never_a_trap(swap, seed, mark, want):
    assert swap_kind(swap, seed, mark) == want


def test_policy_queries_fill_the_cell_wording_and_point_at_their_twin(inputs, complete):
    workload = build(inputs, *complete)
    by_id = {r.qa_id: r for r in workload.records}
    opened = [r for r in workload.records if r.qa_id.startswith("q-policy-return-phones-opened:term:fee")]
    assert opened and all(by_id[r.pair_of].qa_id.startswith("q-policy-return-phones-unopened:term:fee")
                          for r in opened)
    assert all(r.stratum == "B-within" and r.probe_kind == "policy-condition" for r in opened)
    dept = [r for r in workload.records if ":term:dept" in r.qa_id]
    assert len(dept) == 2 * TWIN_WORDINGS_DEPT and all(r.product_id is None for r in dept)


def test_outputs_verify_and_a_reordered_split_file_fails(tmp_path, inputs, complete):
    """W15: the split files are exact projections of the whole file; verify re-derives them."""
    workload = build(inputs, *complete)
    files = output_files(workload)
    data, work = tmp_path / "data", tmp_path / "work"
    data.mkdir()
    write_outputs(files, make_manifest(workload, files, {}), data, work)
    assert sorted(p.name for p in data.iterdir()) == sorted([*files, "workload-manifest.json"])
    assert not list(work.iterdir())  # no temporary file left behind
    assert verify_outputs(inputs, data) == []
    test_file = data / "workload-v1-test.json"
    test_file.write_bytes(canonical(list(reversed(json.loads(test_file.read_text())))))
    assert any("differs from the manifest" in p for p in verify_outputs(inputs, data))


def test_the_lru_simulation_is_seeded_and_counts_trap_encounters(inputs, complete):
    workload = build(inputs, *complete)
    recs = [r for r in workload.records if r.split == "validation"]
    once, again = simulate_lru(recs, 1.1), simulate_lru(recs, 1.1)
    assert once == again and once["capacity"] == corpus_gate.derive_capacity(len(recs))
    assert 0 <= once["tier1_hit_rate"] <= 1


def test_w16_an_axis_in_one_split_only_stops_the_check(inputs, complete):
    workload = build(inputs, *complete)
    for r in workload.records:
        if r.axis == "region":
            r.split = "validation"
    with pytest.raises(WorkloadStop, match="condition axis region has no query in test"):
        build_workload.check_workload(inputs, workload.records)


def test_a_disagreeing_blind_label_drops_the_query_and_counts_it(inputs, complete):
    """rules.md §8 (review M5 a): a paraphrase whose own label cites other evidence is dropped; a
    seed whose own label disagrees takes its paraphrases and its lookalike with it."""
    layer, vectors = complete
    para = next(k for k, r in sorted(layer.items()) if r["type"] == "para"
                and first_labels(layer)[r["ref"]]["answerable"])
    other = inputs.products[layer[para]["doc_id"]].fields[0][1]  # the title: not the seed's evidence
    layer[blind_key(para)] = {**layer[blind_key(para)], "answerable": True, "evidence": other}
    workload = build(inputs, layer, vectors)
    assert workload.drops["paraphrase: the blind label disagrees"] == 1
    assert not any(r.question == layer[para]["question"] for r in workload.records)

    seed_key = f"seed:{layer[para]['ref']}"
    layer[blind_key(seed_key)] = {**layer[blind_key(seed_key)], "answerable": False,
                                  "answer": "", "evidence": ""}
    workload = build(inputs, layer, vectors)
    assert workload.drops["spec seed: the blind label disagrees (its cluster and probes go too)"] == 1
    assert not any(r.cluster_id.startswith(f"c-{layer[seed_key]['doc_id']}-"
                                           f"{seed_key.rsplit(':', 1)[1]}")
                   for r in workload.records)


def test_a_filled_policy_query_must_still_name_its_condition(inputs, complete):
    layer, _ = complete
    key = "cell:policy-return-phones-opened:what"
    layer[key] = {**layer[key], "wordings": ["What do I send back with the {name}?"]}
    with pytest.raises(WorkloadStop, match="does not name its condition"):
        build(inputs, layer, embed_all(inputs, layer, _fake_embed))


def test_a_failed_write_leaves_no_temporary_file_and_no_manifest(tmp_path, inputs, complete,
                                                                 monkeypatch):
    workload = build(inputs, *complete)
    files = output_files(workload)
    data, work = tmp_path / "data", tmp_path / "work"
    data.mkdir()
    real_replace, calls = os.replace, []

    def failing_replace(src, dst):
        calls.append(dst)
        if len(calls) == 2:
            raise OSError("disk full")
        real_replace(src, dst)

    monkeypatch.setattr(build_workload.os, "replace", failing_replace)
    with pytest.raises(OSError):
        write_outputs(files, make_manifest(workload, files, {}), data, work)
    assert not list(work.iterdir()) and not (data / "workload-manifest.json").exists()
