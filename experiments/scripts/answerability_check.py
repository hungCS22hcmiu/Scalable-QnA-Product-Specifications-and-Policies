"""Check the answerability rule against ePQA's human labels — super-plan item 3.2, design §3.1.

    make epqa-fetch          # download the three ePQA CSVs (46 MB, CDLA-Sharing-1.0) into data/raw/epqa/
    make pqa-answerability   # the agreement of R2 and R1 with ePQA's labels, counts only

Descriptive only: no threshold decides anything (design §3). The numbers go to the author.

* **Matching.** A PQA question matches when `(asin, question_text.strip().lower())` equals an ePQA
  question's `(ASIN, question.strip().lower())`, the 2026-10-03 probe's rule
  (`docs/work/2026-10-03-pqa-category-choice/scripts/epqa_probe.py:75-81`). The probe counted PQA
  LINES; that count is pinned (`MATCHED_LINES`, review M1). Scored units are distinct
  `(asin, normalised text)` pairs.
* **ePQA's label for a unit**, fixed before the labels were fetched: answerable when ANY ePQA row with
  that key has label "2" from a counted source; "0" and "1" never make it answerable. Primary:
  `bullet`, `description`. Secondary: also `attribute`, `attributes`, `json`. Tertiary (review M7):
  only label-2 `bullet` / `description` candidates whose content tokens are at least 4/5 contained in
  our record, so the evidence ePQA saw is really in the record the rule reads.
* **The rule's label:** `select_pqa.tag`, imported, for R2 and R1. Policy and dropped questions are
  counted apart and left out of the agreement.

Output: printed, and a counts-only JSON (no question text, no asin) into the task trail.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import build_pqa
import select_pqa

EPQA_DIR = build_pqa.REPO_ROOT / "data" / "raw" / "epqa"  # gitignored (data/raw/)
EPQA_COMMIT = "cec976cc2f2218aa76e562ecc9c7d79f1f3271bc"  # github.com/amazon-science/contextual-product-qa
EPQA_URL = f"https://raw.githubusercontent.com/amazon-science/contextual-product-qa/{EPQA_COMMIT}/ePQA"
# Sizes from the repository tree at EPQA_COMMIT (GitHub API); sha256 from the first download,
# 2026-10-20T09:15:09Z (evidence/epqa-fetch.log). A Git LFS pointer file would fail both.
EPQA_FILES = {
    "train.csv": (37486800, "b63de9681b770573240367e919f7f04f087f6a4745ab1f79a77e6b800105ea25"),
    "dev.csv": (2986475, "ec5c486592b59f2efb30abceb57c76fa55c2ff55333720a41d347cec601b024a"),
    "test.csv": (5871044, "a01387cf43b6c9f2e24ea32b0a06aedad29eb7c65ba4a5009fe818409cef7dab"),
}
OUT = (
    build_pqa.REPO_ROOT
    / "docs"
    / "work"
    / "2026-10-19-pqa-thick-tail-selection"
    / "evidence"
    / "answerability.json"
)

# The probe's count of matched PQA lines, per leaf (2026-10-03 spec F20; design §3.1).
MATCHED_LINES = {
    "unlocked_cell_phones": 143,
    "traditional_laptops": 5,
    "led_&_lcd_tvs": 21,
    "over-ear_headphones": 19,
    "chairs": 2,
    "home_office_desks": 4,
}
PRIMARY = frozenset({"bullet", "description"})
SECONDARY = PRIMARY | {"attribute", "attributes", "json"}
CONTAINMENT = Fraction(4, 5)
LABELS = ("primary", "secondary", "tertiary")
RULES = ("r2", "r1")


class CheckStop(Exception):
    """The check cannot be trusted: exit 2."""


def norm(text: str) -> str:
    return text.strip().lower()


def verify_sources(epqa_dir: Path, files: dict[str, tuple[int, str]] = EPQA_FILES) -> None:
    for name, (size, sha256) in files.items():
        path = epqa_dir / name
        if not path.is_file():
            raise CheckStop(f"{path} is missing. Run `make epqa-fetch`.")
        if path.stat().st_size != size:
            raise CheckStop(f"{path} is {path.stat().st_size:,} bytes, pinned {size:,}.")
        if build_pqa.sha256_file(path) != sha256:
            raise CheckStop(f"{path} has the pinned size but not the pinned sha256.")


def read_epqa(epqa_dir: Path, files: dict[str, tuple[int, str]] = EPQA_FILES) -> dict:
    """{(asin, normalised question): [(source, label, candidate), ...]} over every split."""
    rows: dict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)
    for name in files:
        with (epqa_dir / name).open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                rows[(r["ASIN"], norm(r["question"]))].append(
                    (r["source"], r["label"], r["candidate"])
                )
    return rows


def epqa_labels(rows: list[tuple[str, str, str]], record: frozenset[str]) -> dict[str, bool]:
    def any_two(sources: frozenset[str], contained: bool = False) -> bool:
        for source, label, candidate in rows:
            if label != "2" or source not in sources:
                continue
            if not contained:
                return True
            c = select_pqa.content_tokens(candidate)
            if c and Fraction(len(c & record), len(c)) >= CONTAINMENT:
                return True
        return False

    return {
        "primary": any_two(PRIMARY),
        "secondary": any_two(SECONDARY),
        "tertiary": any_two(PRIMARY, contained=True),
    }


def wilson(k: int, n: int) -> list[float] | None:
    return select_pqa.wilson(k, n)


def agreement(cells: Counter) -> dict:
    tp, fp, fn, tn = (cells[k] for k in ("tp", "fp", "fn", "tn"))
    n = tp + fp + fn + tn
    out = {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": n}
    if not n:
        return out
    observed = (tp + tn) / n
    expected = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / (n * n)
    out["agreement"] = round(observed, 4)
    out["kappa"] = round((observed - expected) / (1 - expected), 4) if expected != 1 else None
    out["precision"] = {"k": tp, "n": tp + fp, "wilson95": wilson(tp, tp + fp)}
    out["recall"] = {"k": tp, "n": tp + fn, "wilson95": wilson(tp, tp + fn)}
    return out


def check(
    manifest_path: Path,
    interim_dir: Path,
    epqa_dir: Path,
    out_path: Path,
    files: dict[str, tuple[int, str]] = EPQA_FILES,
    pins: dict[str, int] = MATCHED_LINES,
) -> int:
    try:
        verify_sources(epqa_dir, files)
        epqa = read_epqa(epqa_dir, files)
        asins = {a for a, _ in epqa}
        generic = select_pqa.generic_tokens(manifest_path, interim_dir)
        lines = Counter()
        units: dict[tuple[str, str], tuple[str, select_pqa.Tag, frozenset[str]]] = {}
        for leaf, line in build_pqa.iter_interim(manifest_path, interim_dir):
            if line["asin"] not in asins:
                continue
            tokens = select_pqa.record_tokens(line)
            for q in line["questions"]:
                key = (line["asin"], norm(q["question_text"]))
                if key not in epqa:
                    continue
                lines[leaf] += 1
                if key not in units:
                    units[key] = (leaf, select_pqa.tag(q["question_text"], tokens, generic[leaf]), tokens.all)
        got = {leaf: lines[leaf] for leaf in pins}
        if got != pins:
            raise CheckStop(f"matched PQA lines per leaf {got}, pinned {pins} (review M1)")
    except (CheckStop, build_pqa.ManifestError, build_pqa.InterimMismatch) as error:
        print(f"stop: {error}", file=sys.stderr)
        return 2

    kinds: Counter = Counter()
    per_leaf: dict[str, Counter] = defaultdict(Counter)
    cells = {(label, rule): Counter() for label in LABELS for rule in RULES}
    for key, (leaf, t, record) in sorted(units.items()):
        kinds[t.kind] += 1
        per_leaf[leaf][t.kind] += 1
        if t.kind != "spec":
            continue
        truth = epqa_labels(epqa[key], record)
        for label in LABELS:
            per_leaf[leaf][f"{label}_answerable"] += truth[label]
            for rule, said in (("r2", t.answerable), ("r1", t.answerable_r1)):
                cell = ("tp" if truth[label] else "fp") if said else ("fn" if truth[label] else "tn")
                cells[(label, rule)][cell] += 1
        per_leaf[leaf]["r2_answerable"] += t.answerable
        per_leaf[leaf]["r1_answerable"] += t.answerable_r1
    result = {
        "epqa_commit": EPQA_COMMIT,
        "epqa_sha256": {name: sha for name, (_, sha) in files.items()},
        "pqa_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "selector_sha256": build_pqa.sha256_file(Path(select_pqa.__file__)),
        "matched_lines": dict(lines),
        "units": len(units),
        "unit_kinds": dict(sorted(kinds.items())),
        "per_leaf": {leaf: dict(sorted(c.items())) for leaf, c in sorted(per_leaf.items())},
        "agreement": {
            label: {rule: agreement(cells[(label, rule)]) for rule in RULES} for label in LABELS
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"matched lines {sum(lines.values())}, units {len(units)}, kinds {dict(kinds)}")
    for label in LABELS:
        for rule in RULES:
            a = result["agreement"][label][rule]
            if not a["n"]:
                continue
            p, r = a["precision"], a["recall"]
            print(
                f"  {label:<9} {rule}: n {a['n']:>3}  agree {a['agreement']:.3f}  kappa {a['kappa']}"
                f"  precision {p['k']}/{p['n']} {p['wilson95']}  recall {r['k']}/{r['n']} {r['wilson95']}"
            )
    print(f"wrote {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--list", action="store_true", help="print file, url, bytes for make")
    parser.add_argument("--epqa-dir", type=Path, default=EPQA_DIR)
    parser.add_argument("--manifest", type=Path, default=build_pqa.MANIFEST_PATH)
    parser.add_argument("--interim-dir", type=Path, default=build_pqa.INTERIM_DIR)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    if args.list:
        for name, (size, _) in EPQA_FILES.items():
            print(f"{name} {EPQA_URL}/{name} {size}")
        return 0
    return check(args.manifest, args.interim_dir, args.epqa_dir, args.out)


if __name__ == "__main__":
    sys.exit(main())
