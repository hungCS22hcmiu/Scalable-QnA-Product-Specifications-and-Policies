"""Item 6.0a: scope_trial reads two runs and applies the adoption rule (design.md section 1).

Every test uses small synthetic records and judge rows: no run, no model. The rule's two tests, the lane of
a Tier-1 hit, the cluster count and the refusal of runs in the wrong order each get one case, because a
mistake in any of them gives a plausible verdict and no error.
"""

import json

import pytest
import scope_trial as st


def rec(i, cache, lane, arm, entry="", **extra):
    r = {
        "request_id": f"r{i}",
        "cache": cache,
        "query_lane": lane,
        "scope_arm": arm,
        "entry_id": entry,
        "hit_scope": None,
        "write_scope": None,
        "no_answer": False,
    }
    r.update(extra)
    return r


def row(i, verdict, qa=None):
    return {"request_id": f"r{i}", "verdict": verdict, "qa_id": qa or f"q{i}"}


def judged(rows):
    return {r["request_id"]: r for r in rows}


CLUSTERS = {f"q{i}": f"c{i // 2}" for i in range(100)}


def test_wilson_matches_a_known_value():
    low, high = st.wilson(5, 10)
    assert low == pytest.approx(0.2366, abs=1e-3)
    assert high == pytest.approx(0.7634, abs=1e-3)
    assert st.wilson(0, 0) is None


def test_a_tier1_hit_takes_the_lane_of_the_miss_that_wrote_its_entry():
    records = [
        rec(1, "MISS", "POLICY", "on", entry="E1"),
        rec(2, "TIER1_HIT", None, "on", entry="E1"),
        rec(3, "TIER1_HIT", None, "on", entry="E-unknown"),
    ]
    lane = st.lanes(records)
    assert lane == {"r1": "POLICY", "r2": "POLICY", "r3": "UNKNOWN"}


def test_the_tally_counts_hits_by_verdict_and_misses_apart():
    records = [
        rec(1, "MISS", "POLICY", "on", entry="E1", write_scope="shared"),
        rec(2, "TIER2_HIT", "POLICY", "on", entry="E1", hit_scope="shared"),
        rec(3, "TIER2_HIT", "POLICY", "on", entry="E1", hit_scope="product"),
        rec(4, "TIER2_HIT", "POLICY", "on", entry="E1", hit_scope="product"),
        rec(5, "MISS", "SPEC", "on", entry="E2"),
    ]
    rows = judged(
        [
            row(1, "INCORRECT"),
            row(2, "CORRECT"),
            row(3, "INCORRECT"),
            row(4, "UNPARSED"),
            row(5, "CORRECT"),
        ]
    )
    t = st.tally(records, rows, CLUSTERS)["POLICY"]
    assert (t["requests"], t["hits"], t["correct"], t["wrong"], t["unjudged"]) == (
        4,
        3,
        1,
        1,
        1,
    )
    assert (t["misses"], t["misses_wrong"]) == (1, 1)
    assert t["hit_scope"] == {"shared": 1, "product": 2}
    assert t["write_scope"] == {"shared": 1}
    assert t["wrong_share"] == pytest.approx(1 / 3)


def test_a_cluster_is_wrong_when_any_of_its_hits_is_wrong():
    # q2 and q3 share cluster c1; q2 is right and q3 is wrong, so c1 is one wrong cluster of two.
    records = [
        rec(2, "TIER2_HIT", "POLICY", "on", entry="E"),
        rec(3, "TIER2_HIT", "POLICY", "on", entry="E"),
        rec(4, "TIER2_HIT", "POLICY", "on", entry="E"),
    ]
    rows = judged([row(2, "CORRECT"), row(3, "INCORRECT"), row(4, "CORRECT")])
    t = st.tally(records, rows, CLUSTERS)["POLICY"]
    assert (t["hit_clusters"], t["wrong_clusters"]) == (2, 1)
    assert t["wrong"] == 1


def _run(correct_off, correct_on, wrong_on, miss_wrong_on, misses_on):
    off = [rec(i, "TIER2_HIT", "POLICY", "off", entry="E") for i in range(correct_off)]
    off_rows = [row(i, "CORRECT") for i in range(correct_off)]
    base = 100
    on = [
        rec(base + i, "TIER2_HIT", "POLICY", "on", entry="E")
        for i in range(correct_on + wrong_on)
    ]
    on_rows = [
        row(base + i, "CORRECT" if i < correct_on else "INCORRECT")
        for i in range(correct_on + wrong_on)
    ]
    start = base + correct_on + wrong_on
    on += [
        rec(start + i, "MISS", "POLICY", "on", entry=f"M{i}") for i in range(misses_on)
    ]
    on_rows += [
        row(start + i, "INCORRECT" if i < miss_wrong_on else "CORRECT")
        for i in range(misses_on)
    ]
    clusters = {f"q{i}": f"c{i}" for i in range(1000)}
    return (
        st.tally(off, judged(off_rows), clusters),
        st.tally(on, judged(on_rows), clusters),
    )


def test_adopt_when_both_rules_hold():
    off, on = _run(
        correct_off=10, correct_on=40, wrong_on=2, miss_wrong_on=5, misses_on=50
    )
    rule = st.verdict_of_rule(off, on)
    assert rule["rule1_rise"] == 30 and rule["rule1_pass"] is True
    assert rule["rule2_pass"] is True  # 2/42 = 0.048 against 5/50 = 0.10 + 0.05
    assert rule["verdict"] == "ADOPT"


def test_keep_off_when_the_rise_is_below_20():
    off, on = _run(
        correct_off=10, correct_on=29, wrong_on=0, miss_wrong_on=0, misses_on=50
    )
    rule = st.verdict_of_rule(off, on)
    assert rule["rule1_rise"] == 19 and rule["rule1_pass"] is False
    assert rule["verdict"] == "KEEP OFF"


def test_keep_off_when_the_hits_are_wronger_than_the_misses_plus_5_points():
    off, on = _run(
        correct_off=0, correct_on=30, wrong_on=10, miss_wrong_on=5, misses_on=50
    )
    rule = st.verdict_of_rule(off, on)
    assert rule["rule1_pass"] is True
    assert rule["rule2_hit_wrong_share"] == pytest.approx(0.25)
    assert rule["rule2_miss_wrong_share"] == pytest.approx(0.10)
    assert rule["rule2_pass"] is False and rule["verdict"] == "KEEP OFF"


def test_exactly_20_and_exactly_5_points_pass():
    off, on = _run(
        correct_off=0, correct_on=20, wrong_on=0, miss_wrong_on=0, misses_on=10
    )
    assert st.verdict_of_rule(off, on)["rule1_pass"] is True
    # wrong share of hits 0.15 against 0.10 + 0.05: equal, so it passes
    off, on = _run(
        correct_off=0, correct_on=17, wrong_on=3, miss_wrong_on=1, misses_on=10
    )
    assert st.verdict_of_rule(off, on)["rule2_pass"] is True


def test_the_command_refuses_runs_in_the_wrong_order(tmp_path, capsys, monkeypatch):
    def write(run_id, arm):
        d = tmp_path / run_id
        (d / "raw").mkdir(parents=True)
        (d / "judge").mkdir()
        (d / "raw" / "requests.jsonl").write_text(
            json.dumps(rec(1, "MISS", "POLICY", arm, entry="E")) + "\n"
        )
        (d / "judge" / "records.jsonl").write_text(json.dumps(row(1, "CORRECT")) + "\n")

    write("run-a", "on")
    write("run-b", "off")
    monkeypatch.setattr(st, "cluster_map", lambda: {"q1": "c1"})
    code = st.main(
        [
            "run-a",
            "run-b",
            "--results-dir",
            str(tmp_path),
            "--out",
            str(tmp_path / "o.json"),
        ]
    )
    assert code == 1
    assert "scope_arm" in capsys.readouterr().err
