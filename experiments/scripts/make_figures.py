"""Item 5.4: the figure generators (docs/work/2026-11-12-figure-generators/design.md, section 3).

    make figures        # PYTHONHASHSEED=0 python3 experiments/scripts/make_figures.py

Draws every registered figure (`FIGURES`) for every run under `experiments/results/`, from the run's tracked files
only (`ablation/scores.json`, `ablation/floor.json`), and writes them under `results/<run_id>/figures/` as
`<name>.pdf` and `<name>.json`. The JSON holds the values the PDF plots, the source files' sha256 and `citable`
(true only when the source says so). Nothing under `raw/` or `judge/` is read here.

A figure is drawn only for a run whose `raw/` and `judge/` are present and unchanged: `raw_archive.check` runs
first, on every run. A run that fails it stops the whole command with nothing drawn, and the message names the
file (and `make raw-restore RUN_ID=<id>` when `raw/` is missing). `figures/` is then emptied (it only ever holds
regenerated files, so a figure dropped from the list cannot leave a stale PDF behind). For each figure and run it
prints `built <figure> <run_id>`, or `not applicable <figure> <run_id>: <input>` naming the first missing input.
A folder with no `manifest.yaml` is not a run (interfaces.md section I): `skipped <folder>: no manifest.yaml`.

The same bytes: matplotlib is pinned in `experiments/requirements.txt` and any other version is refused before a
figure is drawn; the PDF holds no date; the font is the one matplotlib bundles; figures are built with
`matplotlib.figure.Figure()`, never `pyplot`. Every figure is `citable: no` unless its source says `citable: true`.

Exit codes: 0 done; 1 a run failed `raw_archive.check`, or a registered figure was built for no run; 2 the
matplotlib version is not the pin (or matplotlib cannot be imported).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import label_ablation as la
import noise_floor
import raw_archive

if TYPE_CHECKING:
    from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = raw_archive.RESULTS_DIR
PIN_FILE = ROOT / "experiments" / "requirements.txt"

# Okabe-Ito, the palette of docs/0-Thesis-Report/plan/figures.md section 0.2.
TIER2_BLUE = "#0072B2"
MISS_ORANGE = "#E69F00"
VERMILLION = "#D55E00"
GREY = "#555555"
DELTA = 0.05  # the false-hit budget (ADR-026), read here, never changed
F10_INPUTS = ("ablation/scores.json",)
F16_INPUTS = ("ablation/floor.json",)
FONT = "DejaVu Sans"  # bundled with matplotlib; figures.md asks for Helvetica, a system font, which can change the bytes


def pinned_version() -> str:
    """The matplotlib version in `experiments/requirements.txt` (its `matplotlib==X` line)."""
    for line in PIN_FILE.read_text().splitlines():
        m = re.fullmatch(r"\s*matplotlib==(\S+)\s*", line)
        if m:
            return m.group(1)
    raise RuntimeError(f"{PIN_FILE} has no 'matplotlib==<version>' line")


@dataclass(frozen=True)
class FigureSpec:
    """One registered figure.

    `inputs` are paths relative to the run folder. `values(run_dir)` reads them and returns the payload
    `{"run_id", "citable", "source", "values"}`; `draw(payload)` returns the figure. A later item adds its
    figures to `FIGURES`.
    """

    name: str
    inputs: tuple[str, ...]
    values: Callable[[Path], dict]
    draw: Callable[[dict], Figure]


def style() -> None:
    """Backend `pdf`, the bundled font, Type 3 fonts (the bytes do not depend on a system font), Okabe-Ito."""
    import matplotlib

    matplotlib.use("pdf")
    matplotlib.rcParams.update(
        {
            "font.family": FONT,
            "pdf.fonttype": 3,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "legend.frameon": False,
        }
    )


def list_runs(results_dir: Path, log: Callable[[str], None] = print) -> list[Path]:
    """The folders of `results_dir` that hold `manifest.yaml`, sorted. Any other folder is not a run (a run
    without a manifest is invalid, interfaces.md section I): it is logged as `skipped <folder>: no manifest.yaml`."""
    base = Path(results_dir)
    if not base.is_dir():
        return []
    runs = []
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        if (folder / "manifest.yaml").is_file():
            runs.append(folder)
        else:
            log(f"skipped {folder.name}: no manifest.yaml")
    return runs


# =================================================================================================
# F10: the judge's agreement with the author, by containment bucket
# =================================================================================================
def _agreement_point(bucket: str, group: str, block: dict) -> dict:
    """One bar, copied from a `scores.json` bucket (never recomputed)."""
    return {
        "bucket": bucket,
        "group": group,
        "k": block["k"],
        "n": block["n"],
        "rate": block["rate"],
        "wilson95": block["wilson95"],
        "kappa": block["kappa"],
    }


def f10_values(scores: dict) -> dict:
    """The points F10 plots, copied from `scores.json`: the four hit buckets of `label_ablation.HIT_BUCKETS`, in
    that order, then the MISS stratum's `generated` bucket (group `MISS`). Each point carries `k`, `n`, `rate`,
    `wilson95` and `kappa`.

    `below 1.0` is a sum of three plotted buckets, so it is left out. Raises `ValueError` when the four hit
    buckets' `n` do not add up to the hit stratum's `judge_vs_author.n` (a bucket would be missing or doubled).
    """
    hit = scores["by_stratum"]["hit"]
    points = [
        _agreement_point(bucket, "hit", hit["judge_vs_author_by_bucket"][bucket])
        for bucket in la.HIT_BUCKETS
    ]
    total, expected = sum(p["n"] for p in points), hit["judge_vs_author"]["n"]
    if total != expected:
        raise ValueError(
            f"the hit buckets' n add up to {total}, the hit stratum's n is {expected}"
        )
    miss = scores["by_stratum"]["MISS"]["judge_vs_author_by_bucket"][la.MISS_BUCKET]
    points.append(_agreement_point(la.MISS_BUCKET, "MISS", miss))
    return {"points": points}


def _footer(fig: Figure, payload: dict) -> None:
    citable = "yes" if payload["citable"] else "no"
    fig.text(
        0.01,
        0.012,
        f"run {payload['run_id']} \u00b7 citable: {citable}",
        fontsize=7,
        color=GREY,
        ha="left",
        va="bottom",
    )


def draw_f10(payload: dict) -> Figure:
    """Bars of the judge-to-author agreement per bucket, Wilson error bars, `n` above each bar. Hit buckets in
    Tier 2 blue, the MISS group in orange and set apart."""
    from matplotlib.figure import Figure
    from matplotlib.patches import Patch

    style()
    points = payload["values"]["points"]
    colours = {"hit": TIER2_BLUE, "MISS": MISS_ORANGE}
    hits = [p for p in points if p["group"] == "hit"]
    positions = [
        i if p["group"] == "hit" else len(hits) + 0.5 + (i - len(hits))
        for i, p in enumerate(points)
    ]

    fig = Figure(figsize=(7.0, 4.6))
    ax = fig.subplots()
    fig.subplots_adjust(top=0.85, bottom=0.25, left=0.11, right=0.97)
    for pos, p in zip(positions, points):
        if p["rate"] is not None:
            low, high = p["wilson95"]
            ax.bar(pos, p["rate"], width=0.6, color=colours[p["group"]])
            ax.errorbar(
                pos,
                p["rate"],
                yerr=[[p["rate"] - low], [high - p["rate"]]],
                color="black",
                capsize=4,
                linewidth=1,
            )
            top = min(high, 1.0)
        else:
            top = 0.0
        ax.text(pos, top + 0.02, f"n = {p['n']}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(positions)
    ax.set_xticklabels(
        ["MISS (generated)" if p["group"] == "MISS" else p["bucket"] for p in points]
    )
    ax.set_ylim(0, 1)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xlabel("containment bucket")
    ax.set_ylabel("agreement (judge-v1 = author)")
    ax.set_title("Judge agreement with the author, by containment bucket", pad=16)
    fig.legend(
        handles=[
            Patch(color=TIER2_BLUE, label="hit (Tier 2)"),
            Patch(color=MISS_ORANGE, label="MISS (generated)"),
        ],
        loc="lower center",
        ncol=2,
        bbox_to_anchor=(0.5, 0.045),
    )
    _footer(fig, payload)
    return fig


# =================================================================================================
# F16: the noise-floor correction
# =================================================================================================
def f16_values(floor: dict, n: int = 1000) -> dict:
    """The points F16 plots: for `k` judged-INCORRECT hits of `n`, from 0 to 40 % of `n`, the result of
    `noise_floor.corrected_rate(k, n, floor["hits"])`, plus `delta` and the floor's `false_alarm` rate.

    `n` 1000 is the worked size of metrics.md M08, so the figure is illustrative. A point the floor calls
    inconsistent has `corrected: None` (never 0).
    """
    block = floor["hits"]
    points = [
        noise_floor.corrected_rate(k, n, block) for k in range(round(0.40 * n) + 1)
    ]
    return {
        "n": n,
        "delta": DELTA,
        "false_alarm": block["false_alarm"],
        "points": points,
    }


def _gappy(values: list) -> list[float]:
    """None becomes NaN, which matplotlib draws as a gap and never as 0."""
    return [float("nan") if v is None else v for v in values]


def draw_f16(payload: dict) -> Figure:
    """The corrected rate against the judged rate as a line, its interval as a band, the identity line dashed (a
    judge with no error), delta as a horizontal line and the noise floor as a dotted vertical line."""
    from matplotlib.figure import Figure

    style()
    v = payload["values"]
    points = v["points"]
    xs = [p["judged"]["rate"] for p in points]
    corrected = _gappy([p["corrected"] for p in points])
    low = _gappy([None if p["interval"] is None else p["interval"][0] for p in points])
    high = _gappy([None if p["interval"] is None else p["interval"][1] for p in points])
    floor_rate = v["false_alarm"]["rate"]

    fig = Figure(figsize=(6.4, 5.8))
    ax = fig.subplots()
    fig.subplots_adjust(top=0.91, bottom=0.26, left=0.12, right=0.96)
    ax.fill_between(
        xs,
        low,
        high,
        color=TIER2_BLUE,
        alpha=0.2,
        linewidth=0,
        label=f"interval (Wilson, z = {points[0]['z']})",
    )
    ax.plot(xs, corrected, color=TIER2_BLUE, linewidth=1.8, label="corrected rate")
    ax.plot(
        [0, 0.4],
        [0, 0.4],
        color=GREY,
        linestyle="--",
        linewidth=1,
        label="judge with no error",
    )
    ax.axhline(
        v["delta"],
        color=VERMILLION,
        linewidth=1.2,
        label=f"\u03b4 = {100 * v['delta']:g} %",
    )
    ax.axvline(
        floor_rate,
        color="black",
        linestyle=":",
        linewidth=1.2,
        label=f"noise floor ({100 * floor_rate:.1f} %)",
    )
    ax.set_xlim(0, 0.40)
    ax.set_ylim(0, 0.40)
    ax.set_xlabel(f"judged rate (n = {v['n']}, illustrative)")
    ax.set_ylabel("corrected rate")
    ax.set_title(
        "Judged against corrected false-hit rate (judge-v1's noise floor)", pad=10
    )
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=3,
        bbox_to_anchor=(0.5, 0.04),
    )
    _footer(fig, payload)
    return fig


# =================================================================================================
# What a figure writes
# =================================================================================================
def is_citable(*sources: dict) -> bool:
    """True only when every source file says `citable: true`. A source with no `citable` field (`scores.json`)
    is not citable."""
    return bool(sources) and all(doc.get("citable") is True for doc in sources)


def _payload(
    run_dir: Path, inputs: tuple[str, ...], values: Callable[[list[dict]], dict]
) -> dict:
    """`{"run_id", "citable", "source", "values"}` of a run's figure: reads each input (JSON), records its path
    and sha256, and passes the parsed documents to `values`."""
    run_dir = Path(run_dir)
    docs = [json.loads((run_dir / rel).read_text()) for rel in inputs]
    return {
        "run_id": run_dir.name,
        "citable": is_citable(*docs),
        "source": [
            {
                "path": rel,
                "sha256": hashlib.sha256((run_dir / rel).read_bytes()).hexdigest(),
            }
            for rel in inputs
        ],
        "values": values(docs),
    }


def f10_payload(run_dir: Path) -> dict:
    return _payload(run_dir, F10_INPUTS, lambda docs: f10_values(docs[0]))


def f16_payload(run_dir: Path) -> dict:
    return _payload(run_dir, F16_INPUTS, lambda docs: f16_values(docs[0]))


def _write_atomic(path: Path, data: bytes) -> None:
    """Write through a temp file and a rename, so a figure is never half written."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def save(fig: Figure, payload: dict, out_dir: Path, name: str) -> None:
    """Write `<name>.pdf` (no `CreationDate`) and `<name>.json` into `out_dir`, both through a temp file and a
    rename. The JSON is `figure`, `run_id`, `citable`, `source` and `values`, with sorted keys, indent 2 and a
    final newline. Neither file holds a timestamp, so the same input gives the same bytes."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / f"{name}.pdf"
    tmp = out_dir / f"{name}.pdf.tmp"
    fig.savefig(str(tmp), format="pdf", metadata={"CreationDate": None})
    os.replace(tmp, pdf)
    doc = {
        "figure": name,
        "run_id": payload["run_id"],
        "citable": payload["citable"],
        "source": payload["source"],
        "values": payload["values"],
    }
    text = json.dumps(doc, sort_keys=True, indent=2, allow_nan=False) + "\n"
    _write_atomic(out_dir / f"{name}.json", text.encode())


# =================================================================================================
# The registry and the command
# =================================================================================================
F10 = FigureSpec("F10-agreement-by-bucket", F10_INPUTS, f10_payload, draw_f10)
F16 = FigureSpec("F16-noise-floor-correction", F16_INPUTS, f16_payload, draw_f16)
FIGURES = (F10, F16)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    args = ap.parse_args(argv)

    # 1. the version, before anything is drawn
    try:
        import matplotlib
    except ImportError as e:
        print(f"REFUSED: matplotlib cannot be imported: {e}", file=sys.stderr)
        return 2
    pinned = pinned_version()
    if matplotlib.__version__ != pinned:
        print(
            f"REFUSED: matplotlib {matplotlib.__version__} is installed, {PIN_FILE.name} pins {pinned}; "
            "the same bytes need the same version. Nothing was drawn.",
            file=sys.stderr,
        )
        return 2

    # 2. every run must have raw/ and judge/ present and unchanged
    runs = list_runs(args.results_dir)
    problems = 0
    for run_dir in runs:
        found = raw_archive.check(run_dir)
        for problem in found:
            print(f"FAIL  {run_dir.name}: {problem}")
        if "no raw/" in found:
            print(f"  restore it with: make raw-restore RUN_ID={run_dir.name}")
        problems += len(found)
    if problems:
        print("make figures: a run is not intact, so nothing was drawn")
        return 1

    # 3. figures/ only ever holds regenerated files, so it is emptied first
    for run_dir in runs:
        out_dir = run_dir / "figures"
        if out_dir.is_symlink():
            out_dir.unlink()
        elif out_dir.exists():
            shutil.rmtree(out_dir)

    # 4. draw
    built = dict.fromkeys((spec.name for spec in FIGURES), 0)
    for run_dir in runs:
        for spec in FIGURES:
            missing = [rel for rel in spec.inputs if not (run_dir / rel).is_file()]
            if missing:
                print(f"not applicable {spec.name} {run_dir.name}: {missing[0]}")
                continue
            payload = spec.values(run_dir)
            save(spec.draw(payload), payload, run_dir / "figures", spec.name)
            built[spec.name] += 1
            print(f"built {spec.name} {run_dir.name}")

    # 5. a registered figure that applies to no run is a figure nobody checked
    nowhere = [name for name, n in built.items() if n == 0]
    for name in nowhere:
        print(f"FAIL  {name} was built for no run", file=sys.stderr)
    return 1 if nowhere else 0


if __name__ == "__main__":
    sys.exit(main())
