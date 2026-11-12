"""Item 5.4: make_figures.py (the registry, the values, the files, and the guards before anything is drawn).

The value tests read the tracked `ablation/scores.json` and `floor.json` of the judge cost run. The `main` tests
use a temp results folder with a fake `raw/` and `judge/`: no test reads or writes a real run's `raw/`.
"""

import copy
import hashlib
import json
import math
import shutil

import make_figures as m
import matplotlib
import pytest
import raw_archive as ra
import yaml

REAL = m.ROOT / "experiments" / "results" / "2026-11-01T21-17-56_cfg4_judgecost"
SCORES = json.loads((REAL / "ablation" / "scores.json").read_text())
FLOOR = json.loads((REAL / "ablation" / "floor.json").read_text())
F10_NAME, F16_NAME = "F10-agreement-by-bucket", "F16-noise-floor-correction"
BUCKETS = ["1.0", "[0.8, 1)", "[0.6, 0.8)", "below 0.6", "generated"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_run(results, run_id, *, ablation=True, archive_to=None):
    """A fake run with a tiny `raw/` and `judge/`, and (unless `ablation` is False) copies of the real run's
    tracked `ablation/scores.json` and `floor.json`. With `archive_to`, it is archived there."""
    run = results / run_id
    (run / "raw" / "answers").mkdir(parents=True)
    data = b"an answer"
    (run / "raw" / "answers" / f"{sha(data)}.txt").write_bytes(data)
    (run / "raw" / "requests.jsonl").write_text(
        json.dumps({"answer_sha256": sha(data)}) + "\n"
    )
    (run / "manifest.yaml").write_text(
        yaml.safe_dump({"run_id": run_id, "records": {"count": 1}})
    )
    (run / "judge").mkdir()
    (run / "judge" / "verdicts.jsonl").write_text("{}\n")
    if ablation:
        (run / "ablation").mkdir()
        for name in ("scores.json", "floor.json"):
            shutil.copy(REAL / "ablation" / name, run / "ablation" / name)
    if archive_to is not None:
        ra.archive(run, archive_to)
    return run


@pytest.fixture
def results(tmp_path):
    folder = tmp_path / "results"
    folder.mkdir()
    return folder


def tree_hashes(folder):
    return {
        p.relative_to(folder).as_posix(): sha(p.read_bytes())
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


# -------------------------------------------------------------------------------------------------
# the pin
# -------------------------------------------------------------------------------------------------
def test_pinned_version_is_the_installed_one():
    assert m.pinned_version() == "3.10.8"
    assert m.pinned_version() == matplotlib.__version__


# -------------------------------------------------------------------------------------------------
# F10's values (done condition 4)
# -------------------------------------------------------------------------------------------------
def test_f10_values_are_the_five_buckets_copied_from_scores():
    points = m.f10_values(SCORES)["points"]
    assert [p["bucket"] for p in points] == BUCKETS
    hit = SCORES["by_stratum"]["hit"]["judge_vs_author_by_bucket"]
    miss = SCORES["by_stratum"]["MISS"]["judge_vs_author_by_bucket"]["generated"]
    for p in points:
        src = miss if p["bucket"] == "generated" else hit[p["bucket"]]
        for key in ("k", "n", "rate", "wilson95", "kappa"):
            assert p[key] == src[key], (p["bucket"], key)
        assert p["group"] == ("MISS" if p["bucket"] == "generated" else "hit")


def test_f10_hit_buckets_sum_to_the_hit_stratum_and_below_one_is_not_plotted():
    points = m.f10_values(SCORES)["points"]
    assert sum(p["n"] for p in points if p["group"] == "hit") == 79
    assert 79 == SCORES["by_stratum"]["hit"]["judge_vs_author"]["n"]
    assert "below 1.0" not in [p["bucket"] for p in points]


def test_f10_values_raise_when_a_hit_bucket_n_changes():
    bad = copy.deepcopy(SCORES)
    bad["by_stratum"]["hit"]["judge_vs_author_by_bucket"]["[0.6, 0.8)"]["n"] += 1
    with pytest.raises(ValueError, match="add up to 80"):
        m.f10_values(bad)


def test_draw_f10_has_five_bars_with_the_recorded_rates_and_labels():
    payload = m.f10_payload(REAL)
    fig = m.draw_f10(payload)
    ax = fig.axes[0]
    assert [p.get_height() for p in ax.patches] == [
        p["rate"] for p in payload["values"]["points"]
    ]
    assert [t.get_text() for t in ax.get_xticklabels()] == [
        "1.0",
        "[0.8, 1)",
        "[0.6, 0.8)",
        "below 0.6",
        "MISS (generated)",
    ]
    texts = [t.get_text() for t in ax.texts]
    assert texts == ["n = 69", "n = 2", "n = 6", "n = 2", "n = 21"]
    assert ax.get_ylim() == (0, 1)
    assert "citable: no" in " ".join(t.get_text() for t in fig.texts)


# -------------------------------------------------------------------------------------------------
# F16's values (done condition 4)
# -------------------------------------------------------------------------------------------------
def by_k(values):
    return {p["judged"]["k"]: p for p in values["points"]}


def test_f16_values_hold_m08s_worked_points():
    values = m.f16_values(FLOOR)
    points = by_k(values)
    assert len(values["points"]) == 401
    assert (points[165]["corrected"], points[165]["interval"]) == (
        0.0501,
        [0.0, 0.3038],
    )
    assert (points[134]["corrected"], points[134]["interval"]) == (0.0, [0.0, 0.2307])
    assert points[0]["corrected"] is None
    assert points[0]["interval"] is None
    assert values["delta"] == 0.05
    assert values["false_alarm"]["rate"] == FLOOR["hits"]["false_alarm"]["rate"]
    assert values["n"] == 1000


def test_f16_points_are_the_corrected_rate_function_unchanged():
    from noise_floor import corrected_rate

    points = by_k(m.f16_values(FLOOR))
    for k in (0, 50, 134, 165, 300, 400):
        assert points[k] == corrected_rate(k, 1000, FLOOR["hits"])


def test_f16_line_has_nan_not_zero_where_corrected_is_none():
    payload = m.f16_payload(REAL)
    fig = m.draw_f16(payload)
    line = next(l for l in fig.axes[0].get_lines() if l.get_label() == "corrected rate")
    ys = list(line.get_ydata())
    points = payload["values"]["points"]
    assert len(ys) == len(points) == 401
    assert math.isnan(ys[0])
    nones = [i for i, p in enumerate(points) if p["corrected"] is None]
    assert nones and all(math.isnan(ys[i]) for i in nones)
    assert all(
        not math.isnan(ys[i])
        for i, p in enumerate(points)
        if p["corrected"] is not None
    )
    # a true 0 (clipped, but consistent) is a value, not a gap
    assert ys[134] == 0.0


def test_f16_draws_delta_and_the_noise_floor():
    fig = m.draw_f16(m.f16_payload(REAL))
    ax = fig.axes[0]
    labels = [l.get_label() for l in ax.get_lines()]
    assert any(label.startswith("δ = 5") for label in labels)
    assert any(label.startswith("noise floor (13.5") for label in labels)
    assert ax.get_xlim() == (0, 0.40) and ax.get_ylim() == (0, 0.40)


# -------------------------------------------------------------------------------------------------
# citable
# -------------------------------------------------------------------------------------------------
def test_citable_is_true_only_when_every_source_says_true():
    assert m.is_citable({"citable": True}) is True
    assert m.is_citable({"citable": True}, {"citable": True}) is True
    assert m.is_citable({"citable": True}, {"citable": False}) is False
    assert m.is_citable({"citable": "true"}) is False
    assert m.is_citable({}) is False
    assert m.is_citable() is False


def test_f10_is_not_citable_because_scores_json_has_no_such_field():
    assert "citable" not in SCORES
    assert m.f10_payload(REAL)["citable"] is False


def test_f16_is_not_citable_because_floor_json_says_false(results):
    assert FLOOR["citable"] is False
    assert m.f16_payload(REAL)["citable"] is False
    run = make_run(results, "run-citable")
    floor = json.loads((run / "ablation" / "floor.json").read_text())
    floor["citable"] = True
    (run / "ablation" / "floor.json").write_text(json.dumps(floor))
    payload = m.f16_payload(run)
    assert payload["citable"] is True
    assert "citable: yes" in " ".join(t.get_text() for t in m.draw_f16(payload).texts)


# -------------------------------------------------------------------------------------------------
# save
# -------------------------------------------------------------------------------------------------
def test_save_writes_a_pdf_without_a_date_and_a_json_without_a_timestamp(tmp_path):
    payload = m.f10_payload(REAL)
    m.save(m.draw_f10(payload), payload, tmp_path, F10_NAME)
    pdf = (tmp_path / f"{F10_NAME}.pdf").read_bytes()
    assert pdf.startswith(b"%PDF") and b"/CreationDate" not in pdf
    text = (tmp_path / f"{F10_NAME}.json").read_text()
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert "written_at" not in text
    doc = json.loads(text)
    assert set(doc) == {"figure", "run_id", "citable", "source", "values"}
    assert doc["figure"] == F10_NAME and doc["run_id"] == REAL.name
    assert doc["citable"] is False
    assert doc["source"] == [
        {
            "path": "ablation/scores.json",
            "sha256": sha((REAL / "ablation" / "scores.json").read_bytes()),
        }
    ]
    assert text == json.dumps(doc, sort_keys=True, indent=2) + "\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        f"{F10_NAME}.json",
        f"{F10_NAME}.pdf",
    ]


@pytest.mark.parametrize(
    "name,payload_fn,draw_fn",
    [(F10_NAME, m.f10_payload, m.draw_f10), (F16_NAME, m.f16_payload, m.draw_f16)],
)
def test_saving_the_same_figure_twice_gives_the_same_bytes(
    tmp_path, name, payload_fn, draw_fn
):
    payload = payload_fn(REAL)
    m.save(draw_fn(payload), payload, tmp_path / "one", name)
    m.save(draw_fn(payload_fn(REAL)), payload_fn(REAL), tmp_path / "two", name)
    assert tree_hashes(tmp_path / "one") == tree_hashes(tmp_path / "two")


def test_f16_json_keeps_the_zero_point_as_null(tmp_path):
    payload = m.f16_payload(REAL)
    m.save(m.draw_f16(payload), payload, tmp_path, F16_NAME)
    doc = json.loads((tmp_path / f"{F16_NAME}.json").read_text())
    points = {p["judged"]["k"]: p for p in doc["values"]["points"]}
    assert points[0]["corrected"] is None and points[0]["interval"] is None
    assert (points[165]["corrected"], points[165]["interval"]) == (
        0.0501,
        [0.0, 0.3038],
    )


# -------------------------------------------------------------------------------------------------
# list_runs
# -------------------------------------------------------------------------------------------------
def test_list_runs_returns_folders_with_a_manifest_and_logs_the_rest(results):
    make_run(results, "b-run")
    make_run(results, "a-run")
    (results / "not-a-run").mkdir()
    (results / ".gitkeep").write_text("")
    logged = []
    runs = m.list_runs(results, log=logged.append)
    assert [r.name for r in runs] == ["a-run", "b-run"]
    assert logged == ["skipped not-a-run: no manifest.yaml"]
    assert m.list_runs(results / "missing") == []


# -------------------------------------------------------------------------------------------------
# main (done conditions 3 and 5)
# -------------------------------------------------------------------------------------------------
def run_main(results, capsys):
    code = m.main(["--results-dir", str(results)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_main_builds_both_figures_and_the_values_match_scores(
    results, tmp_path, capsys
):
    run = make_run(results, "run-a", archive_to=tmp_path / "archive")
    code, out, _ = run_main(results, capsys)
    assert code == 0
    assert out.splitlines() == [f"built {F10_NAME} run-a", f"built {F16_NAME} run-a"]
    assert sorted(p.name for p in (run / "figures").iterdir()) == [
        f"{F10_NAME}.json",
        f"{F10_NAME}.pdf",
        f"{F16_NAME}.json",
        f"{F16_NAME}.pdf",
    ]
    doc = json.loads((run / "figures" / f"{F10_NAME}.json").read_text())
    assert doc["run_id"] == "run-a" and doc["citable"] is False
    for p, bucket in zip(doc["values"]["points"], BUCKETS):
        assert p["bucket"] == bucket
    assert [p["n"] for p in doc["values"]["points"]] == [69, 2, 6, 2, 21]


def test_main_twice_gives_the_same_bytes(results, tmp_path, capsys):
    run = make_run(results, "run-a", archive_to=tmp_path / "archive")
    assert run_main(results, capsys)[0] == 0
    first = tree_hashes(run / "figures")
    assert run_main(results, capsys)[0] == 0
    assert tree_hashes(run / "figures") == first
    assert len(first) == 4


def test_main_removes_a_stale_file_from_figures(results, tmp_path, capsys):
    run = make_run(results, "run-a", archive_to=tmp_path / "archive")
    (run / "figures").mkdir()
    (run / "figures" / "F99-dropped.pdf").write_bytes(b"old")
    assert run_main(results, capsys)[0] == 0
    assert not (run / "figures" / "F99-dropped.pdf").exists()


def test_main_exits_1_for_a_run_with_no_hash_list(results, capsys):
    run = make_run(results, "run-a")
    code, out, _ = run_main(results, capsys)
    assert code == 1
    assert "run-a: no hash list" in out
    assert not (run / "figures").exists()


def test_main_exits_1_when_raw_is_gone_and_names_the_restore(results, tmp_path, capsys):
    run = make_run(results, "run-a", archive_to=tmp_path / "archive")
    shutil.rmtree(run / "raw")
    code, out, _ = run_main(results, capsys)
    assert code == 1
    assert "no raw/" in out and "make raw-restore RUN_ID=run-a" in out
    assert not (run / "figures").exists()


def test_main_exits_1_on_one_changed_raw_byte_and_draws_nothing(
    results, tmp_path, capsys
):
    ok = make_run(results, "run-a", archive_to=tmp_path / "archive")
    bad = make_run(results, "run-b", archive_to=tmp_path / "archive")
    (ok / "figures").mkdir()
    (ok / "figures" / "keep.pdf").write_bytes(b"left alone")
    target = bad / "raw" / "requests.jsonl"
    data = bytearray(target.read_bytes())
    data[2] ^= 1
    target.write_bytes(bytes(data))
    code, out, _ = run_main(results, capsys)
    assert code == 1
    assert "run-b: changed: raw/requests.jsonl" in out
    assert not (bad / "figures").exists()
    assert sorted(p.name for p in (ok / "figures").iterdir()) == ["keep.pdf"]


def test_main_prints_not_applicable_for_a_run_with_no_ablation(
    results, tmp_path, capsys
):
    make_run(results, "run-a", archive_to=tmp_path / "archive")
    other = make_run(results, "run-b", ablation=False, archive_to=tmp_path / "archive")
    code, out, _ = run_main(results, capsys)
    assert code == 0
    lines = out.splitlines()
    assert f"built {F10_NAME} run-a" in lines
    assert f"not applicable {F10_NAME} run-b: ablation/scores.json" in lines
    assert f"not applicable {F16_NAME} run-b: ablation/floor.json" in lines
    assert not (other / "figures").exists()


def test_main_prints_skipped_for_a_folder_with_no_manifest(results, tmp_path, capsys):
    make_run(results, "run-a", archive_to=tmp_path / "archive")
    (results / "stray").mkdir()
    code, out, _ = run_main(results, capsys)
    assert code == 0
    assert "skipped stray: no manifest.yaml" in out.splitlines()


def test_main_exits_1_when_a_registered_figure_is_built_for_no_run(
    results, tmp_path, capsys, monkeypatch
):
    make_run(results, "run-a", archive_to=tmp_path / "archive")
    nowhere = m.FigureSpec(
        "F99-nowhere", ("ablation/none.json",), lambda run: {}, lambda payload: None
    )
    monkeypatch.setattr(m, "FIGURES", (*m.FIGURES, nowhere))
    code, out, err = run_main(results, capsys)
    assert code == 1
    assert "F99-nowhere was built for no run" in err
    assert "not applicable F99-nowhere run-a: ablation/none.json" in out


def test_main_exits_1_when_there_is_no_run(results, capsys):
    code, _, err = run_main(results, capsys)
    assert code == 1 and "built for no run" in err


def test_main_returns_2_and_writes_nothing_for_another_matplotlib(
    results, tmp_path, capsys, monkeypatch
):
    run = make_run(results, "run-a", archive_to=tmp_path / "archive")
    (run / "figures").mkdir()
    (run / "figures" / "keep.pdf").write_bytes(b"left alone")
    monkeypatch.setattr(matplotlib, "__version__", "0.0")
    code, out, err = run_main(results, capsys)
    assert code == 2
    assert "REFUSED" in err and "0.0" in err and "3.10.8" in err
    assert out == ""
    assert sorted(p.name for p in (run / "figures").iterdir()) == ["keep.pdf"]
