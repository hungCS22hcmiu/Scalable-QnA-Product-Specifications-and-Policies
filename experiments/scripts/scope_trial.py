"""Item 6.0a: read the two trial runs (scope arm off, scope arm on) and apply the adoption rule.

    make scope-trial RUNS="<run_id off> <run_id on>"

Reads, for each run, `raw/requests.jsonl` and `judge/records.jsonl` (judge-v1's verdict for every
request), and the workload's `cluster_id`. Writes nothing under `raw/` or `judge/`. It prints, per lane
(POLICY, SPEC, MIXED) and per arm: requests, hits, judged correct, judged wrong, and Wilson 95 %
intervals for the wrong share of hits, over requests and over clusters. Then the two tests of the
adoption rule (design.md section 1) and the verdict `ADOPT` or `KEEP OFF`.

Definitions
  hit      a record whose `cache` is TIER1_HIT or TIER2_HIT.
  lane     the record's `query_lane`. A Tier-1 hit runs before retrieval, so it has none: it takes the lane
           of the MISS that wrote its entry (`entry_id`), as the judge finds an entry's MISS. A record
           with no lane either way is `UNKNOWN`, counted and shown.
  correct  judge verdict CORRECT.  wrong  verdict INCORRECT.  A hit with another or no verdict (UNPARSED,
           or no answer to judge) is counted as `unjudged` and in neither.
  cluster  the workload's `cluster_id`. A cluster is wrong when any of its hits in the lane is wrong.

The adoption rule (fixed before any replay; scope `on` becomes the served default only if BOTH hold)
  1. POLICY-lane hits judged correct rise by at least 20: correct(on) - correct(off) >= 20.
  2. With the arm on, wrong / hits of the POLICY lane is at most wrong / misses of the POLICY lane in the
     same run, plus 5 points. A miss is a record with `cache` MISS.

Exit codes: 0 done; 1 an input is missing or the runs are not (off, on).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR") or ROOT / "experiments" / "results")
WORKLOAD = ROOT / "data" / "workload-v1-validation.json"
HITS = ("TIER1_HIT", "TIER2_HIT")
LANES = ("POLICY", "SPEC", "MIXED", "UNKNOWN")
MIN_RISE = 20  # rule 1: judged-correct POLICY hits, on minus off
MARGIN = 0.05  # rule 2: wrong share of hits may exceed the wrong share of misses by this much


class TrialError(RuntimeError):
    """An input is missing or wrong. The message says which."""


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """Wilson score interval for k of n, as [low, high]. None when n is 0."""
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [max(0.0, centre - half), min(1.0, centre + half)]


def _read_jsonl(path: Path) -> list[dict]:
    try:
        text = path.read_text()
    except OSError as e:
        raise TrialError(f"cannot read {path}: {e.strerror}") from None
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            raise TrialError(f"{path} line {n} is not JSON") from None
    if not rows:
        raise TrialError(f"{path} holds no rows")
    return rows


def load_run(
    run_id: str, results_dir: Path = RESULTS_DIR
) -> tuple[list[dict], dict[str, dict]]:
    """(the run's request records, request_id -> its judge record)."""
    run_dir = Path(results_dir) / run_id
    records = _read_jsonl(run_dir / "raw" / "requests.jsonl")
    judged = {
        r["request_id"]: r for r in _read_jsonl(run_dir / "judge" / "records.jsonl")
    }
    return records, judged


def arm_of(records: list[dict]) -> str | None:
    """The run's `scope_arm`, read from its records; None when they disagree or carry none."""
    values = {r.get("scope_arm") for r in records}
    return values.pop() if len(values) == 1 else None


def lanes(records: list[dict]) -> dict[str, str]:
    """request_id -> lane. A request without `query_lane` (a Tier-1 hit) takes the lane of the MISS that
    wrote its entry; with none of them it is UNKNOWN."""
    entry_lane: dict[str, str] = {}
    for r in records:
        if r.get("cache") == "MISS" and r.get("entry_id") and r.get("query_lane"):
            entry_lane.setdefault(r["entry_id"], r["query_lane"])
    out = {}
    for r in records:
        lane = (
            r.get("query_lane") or entry_lane.get(r.get("entry_id") or "") or "UNKNOWN"
        )
        out[r["request_id"]] = lane
    return out


def tally(
    records: list[dict],
    judged: dict[str, dict],
    cluster_of: dict[str, str],
) -> dict:
    """Per lane: requests, hits, correct, wrong, unjudged, misses (with wrong), clusters, and the Wilson
    intervals of the wrong share of hits over requests and over clusters."""
    lane_of = lanes(records)
    out = {}
    for lane in LANES:
        mine = [r for r in records if lane_of[r["request_id"]] == lane]
        hits = [r for r in mine if r.get("cache") in HITS]
        misses = [r for r in mine if r.get("cache") == "MISS"]

        def verdict(r):
            row = judged.get(r["request_id"])
            return row.get("verdict") if row else None

        correct = sum(1 for r in hits if verdict(r) == "CORRECT")
        wrong = sum(1 for r in hits if verdict(r) == "INCORRECT")
        miss_wrong = sum(1 for r in misses if verdict(r) == "INCORRECT")
        clusters: dict[str, bool] = defaultdict(bool)  # cluster -> any hit wrong
        for r in hits:
            row = judged.get(r["request_id"]) or {}
            cluster = (
                cluster_of.get(row.get("qa_id") or "")
                or f"unclustered:{r['request_id']}"
            )
            clusters[cluster] = clusters[cluster] or verdict(r) == "INCORRECT"
        wrong_clusters = sum(1 for bad in clusters.values() if bad)
        out[lane] = {
            "requests": len(mine),
            "hits": len(hits),
            "hit_rate": len(hits) / len(mine) if mine else None,
            "correct": correct,
            "wrong": wrong,
            "unjudged": len(hits) - correct - wrong,
            "wrong_share": wrong / len(hits) if hits else None,
            "wrong_wilson_requests": wilson(wrong, len(hits)),
            "hit_clusters": len(clusters),
            "wrong_clusters": wrong_clusters,
            "wrong_wilson_clusters": wilson(wrong_clusters, len(clusters)),
            "misses": len(misses),
            "misses_wrong": miss_wrong,
            "misses_wrong_share": miss_wrong / len(misses) if misses else None,
            "hit_scope": dict(Counter(r.get("hit_scope") for r in hits)),
            "write_scope": dict(
                Counter(r.get("write_scope") for r in misses if r.get("entry_id"))
            ),
            "no_answer": sum(1 for r in mine if r.get("no_answer")),
        }
    return out


def verdict_of_rule(off: dict, on: dict) -> dict:
    """The two tests of the adoption rule on the POLICY lane of each run's tally."""
    rise = on["POLICY"]["correct"] - off["POLICY"]["correct"]
    hit_share = on["POLICY"]["wrong_share"]
    miss_share = on["POLICY"]["misses_wrong_share"]
    rule2 = (
        None
        if hit_share is None or miss_share is None
        else hit_share <= miss_share + MARGIN
    )
    rule1 = rise >= MIN_RISE
    return {
        "rule1_rise": rise,
        "rule1_min": MIN_RISE,
        "rule1_pass": rule1,
        "rule2_hit_wrong_share": hit_share,
        "rule2_miss_wrong_share": miss_share,
        "rule2_margin": MARGIN,
        "rule2_pass": rule2,
        "verdict": "ADOPT" if rule1 and rule2 else "KEEP OFF",
    }


def _fmt(x, pct: bool = True) -> str:
    if x is None:
        return "n/a"
    return f"{x:.3f}" if pct else str(x)


def _wil(w) -> str:
    return "n/a" if w is None else f"[{w[0]:.3f}, {w[1]:.3f}]"


def render(off_id: str, on_id: str, off: dict, on: dict, rule: dict) -> str:
    lines = [f"scope-trial: off = {off_id}", f"             on  = {on_id}", ""]
    header = (
        "lane    arm  requests  hits  hit_rate  correct  wrong  unjudged  "
        "wrong/hits  Wilson(requests)  clusters  wrong_cl  Wilson(clusters)"
    )
    lines.append(header)
    for lane in LANES:
        for arm, t in (("off", off), ("on", on)):
            x = t[lane]
            if x["requests"] == 0:
                continue
            lines.append(
                f"{lane:<7} {arm:<4} {x['requests']:>8}  {x['hits']:>4}  {_fmt(x['hit_rate']):>8}  "
                f"{x['correct']:>7}  {x['wrong']:>5}  {x['unjudged']:>8}  {_fmt(x['wrong_share']):>10}  "
                f"{_wil(x['wrong_wilson_requests']):>16}  {x['hit_clusters']:>8}  "
                f"{x['wrong_clusters']:>8}  {_wil(x['wrong_wilson_clusters'])}"
            )
    lines.append("")
    for arm, t in (("off", off), ("on", on)):
        x = t["POLICY"]
        lines.append(
            f"POLICY {arm}: misses {x['misses']}, judged wrong {x['misses_wrong']} "
            f"({_fmt(x['misses_wrong_share'])}); hit_scope {x['hit_scope']}; "
            f"write_scope {x['write_scope']}; no_answer {x['no_answer']}"
        )
    for arm, t in (("off", off), ("on", on)):
        if t["UNKNOWN"]["requests"]:
            lines.append(
                f"{arm}: {t['UNKNOWN']['requests']} request(s) with no lane (UNKNOWN)"
            )
    rule2_text = "n/a"
    if rule["rule2_pass"] is not None:
        rule2_text = "pass" if rule["rule2_pass"] else "FAIL"
    rule1_text = "pass" if rule["rule1_pass"] else "FAIL"
    lines.append("")
    lines.append(
        f"rule 1: POLICY hits judged correct, on minus off = {rule['rule1_rise']} "
        f"(need at least {rule['rule1_min']}): {rule1_text}"
    )
    lines.append(
        f"rule 2: with the arm on, wrong share of POLICY hits {_fmt(rule['rule2_hit_wrong_share'])} "
        f"against wrong share of POLICY misses {_fmt(rule['rule2_miss_wrong_share'])} "
        f"+ {rule['rule2_margin']:.2f}: {rule2_text}"
    )
    lines.append(f"verdict: {rule['verdict']}")
    return "\n".join(lines)


def cluster_map(path: Path = WORKLOAD) -> dict[str, str]:
    return {q["qa_id"]: q["cluster_id"] for q in json.loads(Path(path).read_text())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "runs", nargs=2, metavar="RUN_ID", help="the arm-off run, then the arm-on run"
    )
    ap.add_argument("--results-dir", default=str(RESULTS_DIR))
    ap.add_argument("--out", required=True, help="where to write the JSON result")
    args = ap.parse_args(argv)
    off_id, on_id = args.runs
    try:
        off_records, off_judged = load_run(off_id, Path(args.results_dir))
        on_records, on_judged = load_run(on_id, Path(args.results_dir))
        for name, records, expected in (
            (off_id, off_records, "off"),
            (on_id, on_records, "on"),
        ):
            if arm_of(records) != expected:
                raise TrialError(
                    f"{name}: the records' scope_arm is {arm_of(records)!r}, not {expected!r}"
                )
        clusters = cluster_map()
    except (TrialError, OSError, ValueError, KeyError) as e:
        print(f"scope-trial FAILED: {e}", file=sys.stderr)
        return 1
    off = tally(off_records, off_judged, clusters)
    on = tally(on_records, on_judged, clusters)
    rule = verdict_of_rule(off, on)
    print(render(off_id, on_id, off, on, rule))
    Path(args.out).write_text(
        json.dumps(
            {"off_run": off_id, "on_run": on_id, "off": off, "on": on, "rule": rule},
            indent=2,
        )
        + "\n"
    )
    print(f"\n  wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
