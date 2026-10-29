"""Item 4.4, done condition 9: the scorer on small fixtures.

Each test builds a tiny evidence folder in tmp_path from a GOOD baseline and changes one thing. The
baseline: edit-001 is a substantive edit of C1 and edit-002 a cosmetic edit of C2. E1 depends on C1,
E2 on C2, and E3 on C3, which nobody edited. The edits purge E1 and E2 and leave E3. The failures
these tests pin are silent in a real run: an entry that was never stored counted as purged, an
eviction that looks like a purge, a dependent left in one tier.
"""

import copy
import json

import score_update_set as scorer

GOOD = {
    "oracle": [
        {"qa_id": "q1", "entry_id": "E1", "entry_sources": ["C1"], "outcome": "MISS"},
        {"qa_id": "q2", "entry_id": "E2", "entry_sources": ["C2"], "outcome": "MISS"},
        {"qa_id": "q3", "entry_id": "E3", "entry_sources": ["C3"], "outcome": "MISS"},
    ],
    "labels": [
        {"edit_id": "edit-001", "chunk_id": "C1", "change_type": "substantive"},
        {"edit_id": "edit-002", "chunk_id": "C2", "change_type": "cosmetic"},
    ],
    "before": {
        "E1": {"t1_keys": ["t1:a"], "t2": True, "entry": True},
        "E2": {"t1_keys": ["t1:b"], "t2": True, "entry": True},
        "E3": {"t1_keys": ["t1:c"], "t2": True, "entry": True},
    },
    "after": {
        "E3": {"t1_keys": ["t1:c"], "t2": True, "entry": True},
    },
    "replies": [
        {
            "edit_id": "edit-001",
            "chunk_id": "C1",
            "ok": True,
            "purged": ["E1"],
            "failed": [],
            "errors": [],
        },
        {
            "edit_id": "edit-002",
            "chunk_id": "C2",
            "ok": True,
            "purged": ["E2"],
            "failed": [],
            "errors": [],
        },
    ],
    "reask": [
        {"qa_id": "q1", "outcome": "MISS", "entry_id": "E9"},
        {"qa_id": "q2", "outcome": "MISS", "entry_id": "E10"},
    ],
}

FILES = {
    "oracle": "oracle.json",
    "labels": "labels.json",
    "before": "snapshot-before.json",
    "after": "snapshot-after.json",
    "replies": "replies.json",
    "reask": "reask.json",
}


def write(folder, data):
    """The input files go in folder/private/, as the live run writes them; score.json lands in folder."""
    (folder / "private").mkdir(parents=True, exist_ok=True)
    for key, filename in FILES.items():
        (folder / "private" / filename).write_text(json.dumps(data[key]))
    return folder


def run(tmp_path, mutate=None):
    """Score a fixture and return (exit code, score.json as a dict)."""
    data = copy.deepcopy(GOOD)
    if mutate:
        mutate(data)
    folder = write(tmp_path / "evidence", data)
    code = scorer.main([str(folder)])
    return code, json.loads((folder / "score.json").read_text())


def test_entry_absent_before_is_not_counted(tmp_path):
    # E4 depends on C1 and was logged, but it was never stored: no key in the before snapshot.
    def mutate(d):
        d["oracle"].append(
            {
                "qa_id": "q4",
                "entry_id": "E4",
                "entry_sources": ["C1"],
                "outcome": "MISS",
            }
        )

    code, result = run(tmp_path, mutate)

    assert code == 0, result["failures"]
    assert result["counts"]["entries_in_oracle"] == 4
    assert result["counts"]["present_before"] == 3  # E4 is not present before
    assert result["counts"]["dependents"] == 2  # so it is not a dependent
    assert result["completeness"] == 1.0
    assert (
        result["exactness"] == 0
    )  # and, being absent after too, it is not a gone non-dependent


def test_gone_non_dependent_breaks_exactness(tmp_path):
    # E3 depends on nothing that was edited, yet it is gone after: an eviction or an over-purge.
    def mutate(d):
        d["after"] = {}

    code, result = run(tmp_path, mutate)

    assert code == 1
    assert result["exactness"] == 1
    assert result["non_dependents_gone"] == ["E3"]
    assert "exactness_is_0" in result["failures"]


def test_dependent_left_in_tier1_only_breaks_completeness(tmp_path):
    def mutate(d):
        d["after"]["E1"] = {"t1_keys": ["t1:a"], "t2": False, "entry": False}

    code, result = run(tmp_path, mutate)

    assert code == 1
    assert result["completeness"] == 0.5
    assert result["dependents_not_gone"] == ["E1"]
    assert "completeness_is_1" in result["failures"]


def test_entry_under_both_labels_counts_as_needed(tmp_path):
    # E1 depends on a substantive chunk (C1) AND a cosmetic one (C2). E2 depends on C2 only.
    def mutate(d):
        d["oracle"][0]["entry_sources"] = ["C1", "C2"]
        d["replies"][1]["purged"] = ["E1", "E2"]

    code, result = run(tmp_path, mutate)

    assert code == 0, result["failures"]
    assert result["counts"]["needed"] == 1  # E1 only
    assert result["precision"] == 0.5
    per_edit = {row["edit_id"]: row for row in result["per_edit"]}
    assert per_edit["edit-001"]["dependents"] == 1
    assert per_edit["edit-002"]["dependents"] == 2  # E1 and E2 both depend on C2


def test_reply_naming_an_unknown_entry_fails(tmp_path):
    def mutate(d):
        d["replies"][0]["purged"] = ["E1", "GHOST"]

    code, result = run(tmp_path, mutate)

    assert code == 1
    assert result["failures"] == ["reply_entries_are_in_the_oracle"]


def test_dependent_not_named_in_any_reply_fails(tmp_path):
    # E1 is gone, but no reply says it was purged: the purge result and the cache disagree.
    def mutate(d):
        d["replies"][0]["purged"] = []

    code, result = run(tmp_path, mutate)

    assert code == 1
    assert result["failures"] == ["dependents_are_named_in_replies"]


def test_edit_with_no_dependent_fails(tmp_path):
    # edit-003 edits C9, which no logged entry cites: the edit tested nothing.
    def mutate(d):
        d["labels"].append(
            {"edit_id": "edit-003", "chunk_id": "C9", "change_type": "cosmetic"}
        )
        d["replies"].append(
            {
                "edit_id": "edit-003",
                "chunk_id": "C9",
                "ok": True,
                "purged": [],
                "failed": [],
                "errors": [],
            }
        )

    code, result = run(tmp_path, mutate)

    assert code == 1
    assert result["failures"] == ["every_edit_has_a_dependent"]
    per_edit = {row["edit_id"]: row for row in result["per_edit"]}
    assert per_edit["edit-003"]["dependents"] == 0


def test_reask_hit_on_a_dependent_fails(tmp_path):
    def mutate(d):
        d["reask"] = [{"qa_id": "q1", "outcome": "TIER2_HIT", "entry_id": "E1"}]

    code, result = run(tmp_path, mutate)

    assert code == 1
    assert result["failures"] == ["no_reask_hits_a_dependent"]
    assert result["counts"]["reask_hits_on_dependents"] == 1


def test_two_runs_print_identical_bytes(tmp_path, capsys):
    folder = write(tmp_path / "evidence", copy.deepcopy(GOOD))

    scorer.main([str(folder)])
    first = capsys.readouterr().out
    first_file = (folder / "score.json").read_text()
    scorer.main([str(folder)])
    second = capsys.readouterr().out
    second_file = (folder / "score.json").read_text()

    assert first == second
    assert first == first_file == second_file  # what is printed is what is saved
    assert list(json.loads(first)) == sorted(json.loads(first))  # sorted keys

    # score.json is the one committed file: no chunk ID and no qa_id in it, only counts by edit_id.
    for private_id in ("C1", "C2", "C3", "q1", "q2", "q3"):
        assert private_id not in first
    assert sorted(p.name for p in folder.iterdir()) == ["private", "score.json"]

    # And the baseline itself is a pass, so the failures above come from the one change each makes.
    result = json.loads(first)
    assert result["ok"], result["failures"]
    assert (result["completeness"], result["exactness"], result["precision"]) == (
        1.0,
        0,
        0.5,
    )
    assert (
        result["counts"]["present_before"] == 3 and result["counts"]["dependents"] == 2
    )
