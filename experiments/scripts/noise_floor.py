"""Item 5.3: the judge's noise floor and the correction (docs/work/2026-11-12-delta-noise-floor/design.md, section 3).

How often is `judge-v1` wrong on a hit? Item 5.2 locked the author's labels for the 79 hits of the judge cost
run. This script reads those locked files and counts, over the hits only:

    false alarm   the judge says INCORRECT, the author says correct:  fa / (fa + tn)   the noise floor
    miss          the judge says CORRECT, the author says incorrect:   mi / (mi + tp)
    disagreement  (fa + mi) / decided

Each rate has a Wilson 95 % interval. MISS keys are never pooled in (`metrics.md` M08 is about hits). An
`UNPARSED` verdict or an `unsure` label leaves both sides and is counted in `undecided` (R5).

`corrected_rate` turns a judged rate into an estimate of the true false-hit rate (the Rogan-Gladen estimator)
with a conservative interval. The frontier (item 6.2) imports it. One command:

    make ablation-floor RUN_ID=<id>     # python3 experiments/scripts/noise_floor.py --run-id <id>

It reads `ablation/sample.jsonl`, `labels.jsonl`, `scores.json` and `judge/verdicts.jsonl` of the run, and
writes `ablation/floor.json` (counts and hashes, no text). It loads no model. Every number it prints is
`citable: no`, as item 5.2's are. It refuses when `floor.json` exists, when a label's `sheet_sha256` is not the
one in `scores.json`, when the sample and the labels name different keys, or when a sample key has no verdict.

Exit codes: 0 done; 1 a rule refused (`REFUSED: ...` on stderr).
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from collections.abc import Callable
from pathlib import Path

import label_ablation as la
import select_pqa

FLOOR_Z = 2.394  # the normal quantile for 95 % shared over three intervals (Bonferroni: 1 - 0.05/3 each)
BUCKETS = ("1.0", "below 1.0")
WORKED = (165, 1000)
FORMULA = "corrected = (k/n - FA) / (1 - MI - FA), clipped to [0, 1]"


# =================================================================================================
# The noise floor
# =================================================================================================
def cells(pairs: list[tuple[str, str]]) -> dict[str, int]:
    """Count the four cells over `(judge, author)` pairs of verdict words. A pair with an `UNPARSED` judge
    or an `UNSURE` author is not decided: it leaves both sides and is counted in `undecided` (R5).

    |                  | author CORRECT | author INCORRECT |
    | judge CORRECT    | tn             | mi               |
    | judge INCORRECT  | fa             | tp               |
    """
    out = {"tp": 0, "fa": 0, "mi": 0, "tn": 0, "undecided": 0}
    for judge_word, author_word in pairs:
        if judge_word not in la.DECIDED or author_word not in la.DECIDED:
            out["undecided"] += 1
        elif judge_word == "INCORRECT":
            out["tp" if author_word == "INCORRECT" else "fa"] += 1
        else:
            out["mi" if author_word == "INCORRECT" else "tn"] += 1
    return out


def floor_block(pairs: list[tuple[str, str]]) -> dict:
    """The cells and the three rates. The miss rate is over the author's INCORRECT (`mi + tp`), not over the
    judge's (`fa + tp`), which would be 1 - precision."""
    c = cells(pairs)
    return {
        "cells": c,
        "false_alarm": la._rate(c["fa"], c["fa"] + c["tn"]),
        "miss": la._rate(c["mi"], c["mi"] + c["tp"]),
        "disagreement": la._rate(
            c["fa"] + c["mi"], c["tp"] + c["fa"] + c["mi"] + c["tn"]
        ),
    }


def compute_floor(
    sample: list[dict], verdicts: dict[str, str], labels: dict[str, str]
) -> dict:
    """The floor over the hits of `sample` (`stratum == "hit"`; the MISS keys are left out), overall and
    per bucket: `1.0`, and `below 1.0` (every other hit bucket). `verdicts` is key -> judge verdict word,
    `labels` is key -> the author's label word."""
    hits = [r for r in sample if r["stratum"] == "hit"]

    def pairs(rows: list[dict]) -> list[tuple[str, str]]:
        return [
            (
                verdicts[r["verdict_key"]],
                la.LABEL_TO_VERDICT[labels[r["verdict_key"]]],
            )
            for r in rows
        ]

    by_bucket = {
        BUCKETS[0]: floor_block(pairs([r for r in hits if r["bucket"] == "1.0"])),
        BUCKETS[1]: floor_block(pairs([r for r in hits if r["bucket"] != "1.0"])),
    }
    return {"hits": floor_block(pairs(hits)), "by_bucket": by_bucket}


# =================================================================================================
# The correction
# =================================================================================================
def _clipped(p: float, fa: float, mi: float) -> float:
    return min(1.0, max(0.0, (p - fa) / (1 - mi - fa)))


def corrected_rate(k: int, n: int, floor: dict, z: float = FLOOR_Z) -> dict:
    """The Rogan-Gladen estimate of the true false-hit rate, for `k` of `n` hits judged INCORRECT.

    `floor` is a `floor_block` (it reads `false_alarm` and `miss`). `corrected = (k/n - FA) / (1 - MI - FA)`,
    clipped to [0, 1]; `unclipped` is the value before the clip. The interval is the min and max of the
    clipped formula over the 8 corners of the box of Wilson intervals (at `z`) of `k/n`, `FA` and `MI`. The
    formula is monotone in each rate alone while the denominator is positive, so the corners hold the
    extremes. Raises `AblationRefused` when the denominator is not positive at the worst corner. `consistent`
    is false when the judged interval lies wholly below the floor's false-alarm interval, or wholly above
    `1 - MI_lo`; `corrected` and `interval` are then `None` (never `[0, 0]`).
    """
    judged = la._rate(k, n)
    if n == 0:
        return {
            "judged": judged,
            "corrected": None,
            "unclipped": None,
            "interval": None,
            "consistent": None,
            "z": z,
        }
    fa_k, fa_n = floor["false_alarm"]["k"], floor["false_alarm"]["n"]
    mi_k, mi_n = floor["miss"]["k"], floor["miss"]["n"]
    if fa_n == 0 or mi_n == 0:
        raise la.AblationRefused(
            "the floor has no author-correct or no author-incorrect hit; it cannot correct"
        )
    p_lo, p_hi = select_pqa.wilson(k, n, z)
    f_lo, f_hi = select_pqa.wilson(fa_k, fa_n, z)
    m_lo, m_hi = select_pqa.wilson(mi_k, mi_n, z)
    if 1 - m_hi - f_hi <= 0:
        raise la.AblationRefused(
            "the judge's error is too uncertain to correct (1 - MI - FA is not positive at the worst corner)"
        )
    fa, mi, p = fa_k / fa_n, mi_k / mi_n, k / n
    unclipped = (p - fa) / (1 - mi - fa)
    consistent = not (p_hi < f_lo or p_lo > 1 - m_lo)
    result = {
        "judged": judged,
        "corrected": None,
        "unclipped": round(unclipped, 4),
        "interval": None,
        "consistent": consistent,
        "z": z,
    }
    if consistent:
        values = [
            _clipped(pp, ff, mm)
            for pp, ff, mm in itertools.product(
                (p_lo, p_hi), (f_lo, f_hi), (m_lo, m_hi)
            )
        ]
        result["corrected"] = round(min(1.0, max(0.0, unclipped)), 4)
        result["interval"] = [round(min(values), 4), round(max(values), 4)]
    return result


# =================================================================================================
# The command
# =================================================================================================
def _short_keys(keys: list[str]) -> str:
    return ", ".join(la._short(k) for k in keys[:5])


def run_floor(
    run_id: str,
    *,
    results_dir: Path = la.RESULTS_DIR,
    now: Callable[[], str] = la._now,
    log: Callable[[str], None] = print,
) -> dict:
    """Compute the floor of a run's locked files and write `ablation/floor.json`. Refuses, before it writes,
    when `floor.json` exists, when a label's `sheet_sha256` is not `scores.json`'s, when the sample's keys
    are not the labels' keys, or when a sample key has no verdict in `judge/verdicts.jsonl`."""
    run_dir = Path(results_dir) / run_id
    adir = la._ablation_dir(results_dir, run_id)
    out_path = adir / "floor.json"
    if out_path.exists():
        raise la.AblationRefused(
            f"{out_path} exists; ablation output is never overwritten"
        )
    sample = la._load_sample(adir)
    labels_path = adir / "labels.jsonl"
    scores_path = adir / "scores.json"
    verdicts_path = run_dir / "judge" / "verdicts.jsonl"
    for path in (labels_path, scores_path, verdicts_path):
        if not path.is_file():
            raise la.AblationRefused(f"no {path}")
    label_rows = la._read_jsonl(labels_path)
    scores = json.loads(scores_path.read_text())
    shas = {r["sheet_sha256"] for r in label_rows}
    if shas != {scores["sheet_sha256"]}:
        raise la.AblationRefused(
            "the labels are not the scored ones: a sheet_sha256 in labels.jsonl differs from scores.json"
        )
    keys = [r["verdict_key"] for r in sample]
    if set(keys) != {r["verdict_key"] for r in label_rows}:
        raise la.AblationRefused("the sample and the labels name different keys")
    verdicts = la._verdict_map(verdicts_path)
    missing = [k for k in keys if k not in verdicts]
    if missing:
        raise la.AblationRefused(
            f"{len(missing)} sample keys have no verdict in judge/verdicts.jsonl ({_short_keys(missing)})"
        )
    labels = {r["verdict_key"]: r["label"] for r in label_rows}

    floor = compute_floor(sample, verdicts, labels)
    doc = {
        "written_at": now(),
        "run_id": run_id,
        "judge": la.SOURCE_JUDGE,
        "sheet_sha256": scores["sheet_sha256"],
        "labels_sha256": hashlib.sha256(labels_path.read_bytes()).hexdigest(),
        "citable": False,
        "hits": floor["hits"],
        "by_bucket": floor["by_bucket"],
        "correction": {
            "formula": FORMULA,
            "z": FLOOR_Z,
            "worked": corrected_rate(*WORKED, floor["hits"]),
        },
    }
    la._write_new(out_path, json.dumps(doc, indent=2) + "\n")
    for line in format_floor(doc):
        log(line)
    log(f"  wrote {out_path}")
    return doc


def _fmt_block(name: str, block: dict) -> list[str]:
    c = block["cells"]
    return [
        f"{name}: tp {c['tp']}, fa {c['fa']}, mi {c['mi']}, tn {c['tn']}, undecided {c['undecided']}",
        f"    false alarm  {la._fmt_rate(block['false_alarm'])}",
        f"    miss         {la._fmt_rate(block['miss'])}",
        f"    disagreement {la._fmt_rate(block['disagreement'])}",
    ]


def format_floor(floor: dict) -> list[str]:
    """One line per rate (`k/n = rate [low, high]`) for the hits and each bucket, then the worked value."""
    lines = [
        (
            f"the noise floor of {floor['judge']} against the author, over hits "
            f"(run {floor['run_id']}, citable: no)"
        )
    ]
    lines += _fmt_block("hits", floor["hits"])
    for bucket in BUCKETS:
        lines += _fmt_block(f"bucket {bucket}", floor["by_bucket"][bucket])
    w = floor["correction"]["worked"]
    interval = (
        "none" if w["interval"] is None else f"[{w['interval'][0]}, {w['interval'][1]}]"
    )
    worked = (
        f"worked value {w['judged']['k']}/{w['judged']['n']}: corrected {w['corrected']} "
        f"{interval} (unclipped {w['unclipped']}, consistent {w['consistent']})"
    )
    lines += [
        f"correction: {floor['correction']['formula']}, z {floor['correction']['z']}",
        worked,
    ]
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--results-dir", type=Path, default=la.RESULTS_DIR)
    args = ap.parse_args(argv)
    try:
        run_floor(args.run_id, results_dir=args.results_dir)
    except la.AblationRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
