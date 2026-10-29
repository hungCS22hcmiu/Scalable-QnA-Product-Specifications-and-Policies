"""Item 4.4, done condition 1: the update-set validator, on a tiny corpus built in tmp_path.

The corpus has 12 product records and 11 policy records, each one chunk. A GOOD set is built from the
real chunk texts (as `ingest.records_to_nodes` splits them, no embedding), then each test breaks one
thing and expects the validator to say so. Nothing here is Amazon-PQA text.
"""

import hashlib
import json
import re

import update_set as us

PRODUCTS = [f"product-widgets-{i:02d}" for i in range(12)]
POLICIES = ["policy-return-a"] + [f"policy-misc-{i}" for i in range(10)]


def build_corpus(directory):
    directory.mkdir()
    for i, doc in enumerate(PRODUCTS):
        record = {
            "doc_id": doc,
            "title": f"Widget {i}",
            "category": "widgets",
            "specs": {"weight": f"{i + 1} kg", "color": "red"},
        }
        (directory / f"{doc}.json").write_text(json.dumps(record))
    for i, doc in enumerate(POLICIES):
        text = (
            "Items may be returned within 30 days of delivery."
            if doc == "policy-return-a"
            else f"Handling note {i}. Orders ship in {i + 2} days and arrive within 7 days."
        )
        (directory / f"{doc}.json").write_text(
            json.dumps({"doc_id": doc, "title": f"Policy {i}", "text": text})
        )


def after_text(doc, before, change_type):
    """A new chunk text. Substantive changes a fact; cosmetic rewords and keeps every number."""
    if change_type == "substantive":
        if doc == "policy-return-a":
            return before.replace("30 days", "14 days")
        if doc.startswith("policy-"):
            return before.replace("arrive within 7 days", "arrive within 9 days")
        return before.replace("color: red", "color: blue")
    if doc.startswith("policy-"):
        return before.replace("Handling note", "Shipping remark")
    return before.replace("Category: widgets", "Kind: widgets")


def build_set(corpus_dir, plan):
    texts = us.chunk_texts(corpus_dir)
    rows = []
    for n, (doc, change_type) in enumerate(plan, 1):
        chunk = f"{doc}#chunk-0"
        rows.append(
            {
                "edit_id": f"edit-{n:03d}",
                "doc_id": doc,
                "chunk_id": chunk,
                "change_type": change_type,
                "before": texts[chunk],
                "after": after_text(doc, texts[chunk], change_type),
                "expected_effect": "which answers change, or why none do",
            }
        )
    return rows


GOOD_PLAN = (
    [(d, "substantive") for d in POLICIES[:5]]  # includes the 30 -> 14 day return edit
    + [(d, "substantive") for d in PRODUCTS[:5]]
    + [(d, "cosmetic") for d in POLICIES[5:10]]
    + [(d, "cosmetic") for d in PRODUCTS[5:10]]
)


def write_set(tmp_path, rows):
    set_path = tmp_path / "update-set.json"
    set_path.write_text(json.dumps(rows))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"sha256": hashlib.sha256(set_path.read_bytes()).hexdigest()})
    )
    return set_path, manifest


def check(tmp_path, rows):
    corpus = tmp_path / "corpus"
    if not corpus.exists():
        build_corpus(corpus)
    set_path, manifest = write_set(tmp_path, rows)
    return us.verify(set_path, corpus, manifest)


def good_rows(tmp_path, plan=GOOD_PLAN):
    corpus = tmp_path / "corpus"
    build_corpus(corpus)
    return build_set(corpus, plan)


def test_good_set_passes(tmp_path):
    assert check(tmp_path, good_rows(tmp_path)) == []


def test_wrong_counts_fail(tmp_path):
    rows = good_rows(tmp_path)[:-1]  # 19 edits, and only 9 cosmetic

    problems = "\n".join(check(tmp_path, rows))

    assert "19 edits, want 20" in problems
    assert "9 cosmetic edits, want 10" in problems


def test_too_few_policy_or_product_edits_fail(tmp_path):
    # 3 policy + 7 product substantive edits: the substantive half has too few policy edits.
    plan = (
        [(d, "substantive") for d in POLICIES[:3]]
        + [(d, "substantive") for d in PRODUCTS[:7]]
        + [(d, "cosmetic") for d in POLICIES[4:9]]
        + [(d, "cosmetic") for d in PRODUCTS[7:12]]
    )

    problems = "\n".join(check(tmp_path, good_rows(tmp_path, plan)))

    assert "3 policy edits among the substantive ones, want at least 4" in problems


def test_before_not_equal_to_corpus_text_fails(tmp_path):
    rows = good_rows(tmp_path)
    rows[7]["before"] = rows[7]["before"] + " (edited since)"

    problems = check(tmp_path, rows)

    assert any("edit-008" in p and "before is not the v1 text" in p for p in problems)


def test_after_equal_to_before_fails(tmp_path):
    rows = good_rows(tmp_path)
    rows[12]["after"] = rows[12]["before"]

    problems = check(tmp_path, rows)

    assert any("edit-013" in p and "after equals before" in p for p in problems)


def test_cosmetic_edit_changing_a_number_fails(tmp_path):
    rows = good_rows(tmp_path)
    cosmetic = next(
        r
        for r in rows
        if r["change_type"] == "cosmetic" and r["doc_id"].startswith("product-")
    )
    cosmetic["after"] = cosmetic["after"].replace("Widget", "Widget 99 ")

    assert (
        check(tmp_path, rows) == []
    )  # adding a number is allowed: every number of before is kept

    cosmetic["after"] = re.sub(
        r"weight: \d+", "weight: 99", cosmetic["after"]
    )  # loses the old weight
    problems = check(tmp_path, rows)

    assert any(
        cosmetic["edit_id"] in p and "must keep every number" in p for p in problems
    )


def test_duplicate_chunk_fails(tmp_path):
    rows = good_rows(tmp_path)
    rows[1] = {
        **rows[0],
        "edit_id": rows[1]["edit_id"],
    }  # a second edit on the first chunk

    problems = "\n".join(check(tmp_path, rows))

    assert "duplicate chunk policy-return-a#chunk-0" in problems


def test_missing_return_window_edit_fails(tmp_path):
    # Swap the 30 -> 14 day edit for an ordinary policy edit (policy-misc-9 is not used elsewhere).
    plan = [("policy-misc-9" if d == "policy-return-a" else d, t) for d, t in GOOD_PLAN]

    problems = "\n".join(check(tmp_path, good_rows(tmp_path, plan)))

    assert "'30 days' to '14 days'" in problems


def test_manifest_hash_mismatch_fails(tmp_path):
    rows = good_rows(tmp_path)
    set_path, manifest = write_set(tmp_path, rows)
    manifest.write_text(json.dumps({"sha256": "0" * 64}))

    problems = us.verify(set_path, tmp_path / "corpus", manifest)

    assert any("does not match" in p for p in problems)


def test_schema_field_missing_fails(tmp_path):
    rows = good_rows(tmp_path)
    del rows[3]["expected_effect"]

    problems = check(tmp_path, rows)

    assert any("edit-004" in p and "expected_effect" in p for p in problems)
