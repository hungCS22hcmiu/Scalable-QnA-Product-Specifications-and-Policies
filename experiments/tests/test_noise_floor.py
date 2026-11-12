"""Item 5.3 (docs/work/2026-11-12-delta-noise-floor/design.md): the judge's noise floor and the correction.

The floor first: four cells, three rates, and their Wilson intervals on a fixture where all four cells and
both margins differ, so a miss rate taken over the wrong margin gives another number. Then the correction
(`corrected_rate`) against hand-computed values and a brute-force grid. Then `run_floor` on a temp folder.

No Ollama, no Redis, no network.
"""

import hashlib
import itertools
import json

import label_ablation as la
import noise_floor as nf
import pytest
import select_pqa


# =================================================================================================
# The floor (DC 2)
# =================================================================================================
def pairs_of(tp, fa, mi, tn):
    """`(judge, author)` verdict-word pairs with the given counts in the four cells."""
    return (
        [("INCORRECT", "INCORRECT")] * tp
        + [("INCORRECT", "CORRECT")] * fa
        + [("CORRECT", "INCORRECT")] * mi
        + [("CORRECT", "CORRECT")] * tn
    )


def test_floor_cells_and_the_three_rates():
    block = nf.floor_block(pairs_of(tp=5, fa=3, mi=2, tn=10))
    assert block["cells"] == {"tp": 5, "fa": 3, "mi": 2, "tn": 10, "undecided": 0}
    for name, k, n in (
        ("false_alarm", 3, 13),
        ("miss", 2, 7),
        ("disagreement", 5, 20),
    ):
        got = block[name]
        assert (got["k"], got["n"]) == (k, n)
        assert got["rate"] == round(k / n, 4)
        assert got["wilson95"] == select_pqa.wilson(k, n)


def test_floor_miss_is_over_the_authors_incorrect_not_the_judges():
    # failure mode 1: over the judge's INCORRECT the rate would be 1 - precision = 3/8
    block = nf.floor_block(pairs_of(tp=5, fa=3, mi=2, tn=10))
    miss = block["miss"]
    assert miss["k"] / miss["n"] != 3 / 8
    assert miss["k"] / miss["n"] == 2 / 7
    # and the false alarm is over the author's CORRECT (13), not the judge's CORRECT (12)
    fa = block["false_alarm"]
    assert fa["n"] == 13 and fa["n"] != 12


def test_floor_undecided_pairs_leave_both_sides_of_every_rate():
    # R5: a judge UNPARSED or an author UNSURE is counted in `undecided` and in no rate
    base = nf.floor_block(pairs_of(tp=5, fa=3, mi=2, tn=10))
    more = nf.floor_block(
        pairs_of(tp=5, fa=3, mi=2, tn=10)
        + [("UNPARSED", "CORRECT"), ("INCORRECT", "UNSURE")]
    )
    assert more["cells"]["undecided"] == 2
    for name in ("false_alarm", "miss", "disagreement"):
        assert more[name] == base[name]
    for name in ("tp", "fa", "mi", "tn"):
        assert more["cells"][name] == base["cells"][name]


def test_floor_with_no_pair_has_no_rate():
    block = nf.floor_block([])
    for name in ("false_alarm", "miss", "disagreement"):
        assert block[name]["n"] == 0
        assert block[name]["rate"] is None
        assert block[name]["wilson95"] is None


def sample_row(key, stratum, bucket, answerable=True):
    return {
        "verdict_key": key,
        "stratum": stratum,
        "bucket": bucket,
        "answerable": answerable,
    }


def test_floor_compute_floor_uses_hits_only_and_splits_the_buckets():
    # key: (stratum, bucket, judge verdict, author label)
    spec = {
        "h1": ("hit", "1.0", "INCORRECT", "incorrect"),  # tp
        "h2": ("hit", "1.0", "INCORRECT", "correct"),  # fa
        "h3": ("hit", "1.0", "CORRECT", "correct"),  # tn
        "h4": ("hit", "[0.8, 1)", "CORRECT", "incorrect"),  # mi
        "h5": ("hit", "[0.6, 0.8)", "INCORRECT", "correct"),  # fa
        "h6": ("hit", "below 0.6", "CORRECT", "correct"),  # tn
        # MISS keys: pooled in, they would add one fa and one mi (failure mode 3)
        "m1": ("MISS", "generated", "INCORRECT", "correct"),
        "m2": ("MISS", "generated", "CORRECT", "incorrect"),
    }
    # the one answerable: false hit counts like any other (R6)
    sample = [
        sample_row(k, s, b, answerable=(k != "h3")) for k, (s, b, _, _) in spec.items()
    ]
    verdicts = {k: v for k, (_, _, v, _) in spec.items()}
    labels = {k: a for k, (_, _, _, a) in spec.items()}
    floor = nf.compute_floor(sample, verdicts, labels)
    assert floor["hits"]["cells"] == {
        "tp": 1,
        "fa": 2,
        "mi": 1,
        "tn": 2,
        "undecided": 0,
    }
    assert tuple(floor["by_bucket"]) == nf.BUCKETS == ("1.0", "below 1.0")
    assert floor["by_bucket"]["1.0"]["cells"] == {
        "tp": 1,
        "fa": 1,
        "mi": 0,
        "tn": 1,
        "undecided": 0,
    }
    # [0.8, 1), [0.6, 0.8) and below 0.6 all fall into `below 1.0`
    assert floor["by_bucket"]["below 1.0"]["cells"] == {
        "tp": 0,
        "fa": 1,
        "mi": 1,
        "tn": 1,
        "undecided": 0,
    }


# =================================================================================================
# The correction (DC 5)
# =================================================================================================
COST_RUN_FLOOR = pairs_of(tp=20, fa=7, mi=7, tn=45)  # the cost run's hits: 7/52, 7/27


def cost_floor():
    return nf.floor_block(COST_RUN_FLOOR)


def test_corrected_rate_worked_value_of_the_cost_runs_floor():
    got = nf.corrected_rate(165, 1000, cost_floor())
    assert got["corrected"] == 0.0501
    assert got["unclipped"] == 0.0501
    assert got["interval"] == [0.0, 0.3038]
    assert got["consistent"] is True
    assert got["z"] == nf.FLOOR_Z == 2.394
    assert (got["judged"]["k"], got["judged"]["n"]) == (165, 1000)
    assert got["judged"]["wilson95"] == select_pqa.wilson(165, 1000)
    assert nf.WORKED == (165, 1000)


def test_corrected_rate_is_clipped_at_zero_and_keeps_the_unclipped_value():
    got = nf.corrected_rate(134, 1000, cost_floor())
    assert got["corrected"] == 0.0
    assert got["unclipped"] == -0.001
    assert got["interval"] == [0.0, 0.2307]
    assert got["consistent"] is True


def test_corrected_rate_below_the_floor_is_inconsistent_not_zero():
    # failure mode 6: a judged rate far below the floor must not read as "no false hits"
    got = nf.corrected_rate(0, 200, cost_floor())
    assert got["consistent"] is False
    assert got["corrected"] is None
    assert got["interval"] is None
    assert got["unclipped"] < 0  # kept, so the reader can see how far below it is


def test_corrected_rate_above_the_ceiling_is_inconsistent():
    # all judged INCORRECT: more than 1 - MI_lo, the most a judge with this miss rate can give
    got = nf.corrected_rate(1000, 1000, cost_floor())
    assert got["consistent"] is False
    assert got["corrected"] is None
    assert got["interval"] is None


def test_corrected_rate_changes_when_false_alarm_and_miss_are_swapped():
    # failure mode 2: fa 7 of 27 and mi 7 of 52 (the cost run's two rates exchanged)
    swapped = nf.floor_block(pairs_of(tp=45, fa=7, mi=7, tn=20))
    assert swapped["false_alarm"]["n"] == 27 and swapped["miss"]["n"] == 52
    normal = nf.corrected_rate(165, 1000, cost_floor())
    other = nf.corrected_rate(165, 1000, swapped)
    assert other["corrected"] != normal["corrected"]
    assert other["unclipped"] != normal["unclipped"]


def clipped_formula(p, fa, mi):
    return min(1.0, max(0.0, (p - fa) / (1 - mi - fa)))


@pytest.mark.parametrize("k,n", [(165, 1000), (50, 300)])
def test_corrected_rate_interval_equals_a_brute_force_grid_over_the_box(k, n):
    # failure mode 7: the 8 corners must hold the extremes of the formula over the whole box
    z = nf.FLOOR_Z
    boxes = [
        select_pqa.wilson(k, n, z),
        select_pqa.wilson(7, 52, z),
        select_pqa.wilson(7, 27, z),
    ]
    axes = [[lo + (hi - lo) * i / 20 for i in range(21)] for lo, hi in boxes]
    values = [clipped_formula(*point) for point in itertools.product(*axes)]
    got = nf.corrected_rate(k, n, cost_floor())
    assert got["consistent"] is True
    assert got["interval"][0] == pytest.approx(min(values), abs=1e-4)
    assert got["interval"][1] == pytest.approx(max(values), abs=1e-4)


def test_corrected_rate_ten_times_the_labels_gives_a_narrower_interval():
    # failure mode 5: the floor's own uncertainty must be inside the interval, so more labels narrow it
    small = nf.corrected_rate(165, 1000, cost_floor())
    big = nf.corrected_rate(165, 1000, nf.floor_block(pairs_of(200, 70, 70, 450)))
    assert big["z"] == nf.FLOOR_Z == 2.394
    width_small = small["interval"][1] - small["interval"][0]
    width_big = big["interval"][1] - big["interval"][0]
    assert width_big < width_small
    assert big["corrected"] == small["corrected"]  # same point estimate, same rates


def test_corrected_rate_refuses_a_floor_too_uncertain_to_correct():
    # tp 1, fa 1, mi 1, tn 1: FA = MI = 1/2, so 1 - MI - FA is 0 and the box makes it negative
    with pytest.raises(la.AblationRefused, match="too uncertain"):
        nf.corrected_rate(165, 1000, nf.floor_block(pairs_of(1, 1, 1, 1)))


def test_corrected_rate_refuses_a_floor_with_no_author_correct_hit():
    with pytest.raises(la.AblationRefused):
        nf.corrected_rate(165, 1000, nf.floor_block(pairs_of(tp=5, fa=0, mi=2, tn=0)))


def test_corrected_rate_with_no_hits_at_the_point_has_nothing_to_correct():
    got = nf.corrected_rate(0, 0, cost_floor())
    assert got["judged"]["n"] == 0
    assert got["judged"]["rate"] is None
    assert got["corrected"] is None
    assert got["unclipped"] is None
    assert got["interval"] is None


# =================================================================================================
# run_floor on a temp folder (DC 1, DC 2)
# =================================================================================================
SHEET = "b" * 64
RUN = "2026-11-01T00-00-00_cfg4_fixture"


def key_of(i):
    return hashlib.sha256(f"key-{i}".encode()).hexdigest()


def fixture_rows():
    """(stratum, bucket, judge verdict, author label): 38 hits and 8 MISSes. Pooled in, the MISSes would add
    four false alarms and four misses. The hits are many enough for the correction to be defined (a floor of
    about eight keys is refused as too uncertain, which a test below checks)."""
    return (
        [("hit", "1.0", "INCORRECT", "incorrect")] * 10  # tp
        + [("hit", "1.0", "INCORRECT", "correct")] * 2  # fa
        + [("hit", "1.0", "CORRECT", "incorrect")] * 2  # mi
        + [("hit", "1.0", "CORRECT", "correct")] * 20  # tn
        + [("hit", "[0.8, 1)", "CORRECT", "correct")] * 3  # tn
        + [("hit", "below 0.6", "INCORRECT", "incorrect")]  # tp
        + [("MISS", "generated", "INCORRECT", "correct")] * 4
        + [("MISS", "generated", "CORRECT", "incorrect")] * 4
    )


def build_run(tmp_path, rows=None):
    """Write `<tmp>/<RUN>/ablation/{sample,labels}.jsonl`, `scores.json` and `judge/verdicts.jsonl`."""
    rows = fixture_rows() if rows is None else rows
    adir = tmp_path / RUN / "ablation"
    jdir = tmp_path / RUN / "judge"
    adir.mkdir(parents=True)
    jdir.mkdir(parents=True)
    keys = [key_of(i) for i in range(len(rows))]
    sample = [
        {"verdict_key": k, "stratum": s, "bucket": b, "answerable": True}
        for k, (s, b, _, _) in zip(keys, rows)
    ]
    labels = [
        {
            "item": i + 1,
            "verdict_key": k,
            "label": a,
            "sheet_sha256": SHEET,
            "written_at": "2026-11-11T16:12:13+00:00",
        }
        for i, (k, (_, _, _, a)) in enumerate(zip(keys, rows))
    ]
    verdicts = [
        {"verdict_key": k, "verdict": v, "reply": v, "seconds": 1.0}
        for k, (_, _, v, _) in zip(keys, rows)
    ]
    (adir / "sample.jsonl").write_text(la._jsonl_text(sample))
    (adir / "labels.jsonl").write_text(la._jsonl_text(labels))
    (adir / "scores.json").write_text(json.dumps({"sheet_sha256": SHEET}) + "\n")
    (jdir / "verdicts.jsonl").write_text(la._jsonl_text(verdicts))
    return keys


def run_it(tmp_path, log=None):
    return nf.run_floor(
        RUN,
        results_dir=tmp_path,
        now=lambda: "2026-11-12T10:00:00+00:00",
        log=(log or (lambda line: None)),
    )


def floor_path(tmp_path):
    return tmp_path / RUN / "ablation" / "floor.json"


def test_run_floor_writes_floor_json_with_every_field(tmp_path):
    build_run(tmp_path)
    logged = []
    doc = run_it(tmp_path, log=logged.append)
    on_disk = json.loads(floor_path(tmp_path).read_text())
    assert on_disk == doc
    assert set(on_disk) == {
        "written_at",
        "run_id",
        "judge",
        "sheet_sha256",
        "labels_sha256",
        "citable",
        "hits",
        "by_bucket",
        "correction",
    }
    assert on_disk["written_at"] == "2026-11-12T10:00:00+00:00"
    assert on_disk["run_id"] == RUN
    assert on_disk["judge"] == "judge-v1"
    assert on_disk["sheet_sha256"] == SHEET
    assert on_disk["citable"] is False
    labels_file = tmp_path / RUN / "ablation" / "labels.jsonl"
    assert on_disk["labels_sha256"] == hashlib.sha256(labels_file.read_bytes()).hexdigest()
    # hits only: the MISS keys are not pooled (failure mode 3)
    assert on_disk["hits"]["cells"] == {
        "tp": 11,
        "fa": 2,
        "mi": 2,
        "tn": 23,
        "undecided": 0,
    }
    assert on_disk["hits"]["false_alarm"]["n"] == 25
    assert list(on_disk["by_bucket"]) == list(nf.BUCKETS)
    assert on_disk["by_bucket"]["1.0"]["cells"]["tp"] == 10
    assert on_disk["by_bucket"]["below 1.0"]["cells"] == {
        "tp": 1,
        "fa": 0,
        "mi": 0,
        "tn": 3,
        "undecided": 0,
    }
    correction = on_disk["correction"]
    assert set(correction) == {"formula", "z", "worked"}
    assert correction["formula"] == nf.FORMULA
    assert correction["z"] == nf.FLOOR_Z
    assert correction["worked"] == nf.corrected_rate(*nf.WORKED, on_disk["hits"])
    assert "citable: no" in logged[0]
    assert logged[-1].startswith("  wrote ") and "floor.json" in logged[-1]


def test_run_floor_text_holds_no_verdict_key_and_no_question_or_answer(tmp_path):
    keys = build_run(tmp_path)
    run_it(tmp_path)
    text = floor_path(tmp_path).read_text()
    for key in keys:
        assert key not in text and key[:12] not in text
    for word in ('"query', '"answer', '"evidence', '"reply'):
        assert word not in text


def test_run_floor_counts_an_unsure_label_as_undecided(tmp_path):
    rows = fixture_rows()
    rows[-9] = ("hit", "below 0.6", "INCORRECT", "unsure")  # was a tp
    build_run(tmp_path, rows)
    doc = run_it(tmp_path)
    assert doc["hits"]["cells"]["undecided"] == 1
    assert doc["hits"]["cells"]["tp"] == 10


def test_run_floor_refuses_when_floor_json_exists_and_leaves_it_unchanged(tmp_path):
    build_run(tmp_path)
    floor_path(tmp_path).write_text("{}\n")
    with pytest.raises(la.AblationRefused, match="exists"):
        run_it(tmp_path)
    assert floor_path(tmp_path).read_text() == "{}\n"


@pytest.mark.parametrize("which", ["one", "all"])
def test_run_floor_refuses_labels_that_are_not_the_scored_ones(tmp_path, which):
    # failure mode 4: the original sheet, or a re-lock, would give a different (plausible) floor
    keys = build_run(tmp_path)
    labels_file = tmp_path / RUN / "ablation" / "labels.jsonl"
    rows = la._read_jsonl(labels_file)
    for row in rows if which == "all" else rows[:1]:
        row["sheet_sha256"] = "d" * 64
    labels_file.write_text(la._jsonl_text(rows))
    assert len(keys) == len(rows)
    with pytest.raises(la.AblationRefused, match="not the scored ones"):
        run_it(tmp_path)
    assert not floor_path(tmp_path).exists()


def test_run_floor_refuses_a_sample_key_with_no_verdict(tmp_path):
    keys = build_run(tmp_path)
    verdicts_file = tmp_path / RUN / "judge" / "verdicts.jsonl"
    rows = la._read_jsonl(verdicts_file)
    verdicts_file.write_text(la._jsonl_text(rows[:-1]))
    with pytest.raises(la.AblationRefused, match="no verdict") as caught:
        run_it(tmp_path)
    assert keys[-1][:12] in str(caught.value)  # named by its prefix, never by text
    assert not floor_path(tmp_path).exists()


def test_run_floor_refuses_when_the_labels_name_other_keys(tmp_path):
    build_run(tmp_path)
    labels_file = tmp_path / RUN / "ablation" / "labels.jsonl"
    rows = la._read_jsonl(labels_file)
    labels_file.write_text(la._jsonl_text(rows[:-1]))
    with pytest.raises(la.AblationRefused, match="different keys"):
        run_it(tmp_path)
    assert not floor_path(tmp_path).exists()


def test_run_floor_refuses_a_missing_scores_file(tmp_path):
    build_run(tmp_path)
    (tmp_path / RUN / "ablation" / "scores.json").unlink()
    with pytest.raises(la.AblationRefused, match="scores.json"):
        run_it(tmp_path)
    assert not floor_path(tmp_path).exists()


def test_run_floor_refuses_a_floor_of_about_eight_keys_as_too_uncertain(tmp_path):
    rows = [
        ("hit", "1.0", "INCORRECT", "incorrect"),
        ("hit", "1.0", "INCORRECT", "incorrect"),
        ("hit", "1.0", "INCORRECT", "correct"),
        ("hit", "1.0", "CORRECT", "incorrect"),
        ("hit", "1.0", "CORRECT", "correct"),
        ("MISS", "generated", "CORRECT", "correct"),
        ("MISS", "generated", "INCORRECT", "incorrect"),
        ("MISS", "generated", "CORRECT", "correct"),
    ]
    build_run(tmp_path, rows)
    with pytest.raises(la.AblationRefused, match="too uncertain"):
        run_it(tmp_path)
    assert not floor_path(tmp_path).exists()


def test_run_floor_main_returns_one_and_prints_refused_on_a_refusal(tmp_path, capsys):
    build_run(tmp_path)
    floor_path(tmp_path).write_text("{}\n")
    code = nf.main(["--run-id", RUN, "--results-dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("REFUSED:")
    assert floor_path(tmp_path).read_text() == "{}\n"


def test_run_floor_main_returns_zero_and_prints_the_floor(tmp_path, capsys):
    build_run(tmp_path)
    code = nf.main(["--run-id", RUN, "--results-dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert code == 0
    assert "false alarm" in captured.out and "worked value 165/1000" in captured.out
    assert floor_path(tmp_path).is_file()
