"""Block C, step 16: the gate's `reachable_traps` on the real workload and the real vectors file.

Read-only, no Redis, no Ollama. It reads data/workload-v1.json and data/v1-draft/workload/vectors.json
(both gitignored), calls corpus_gate.reachable_traps, and writes evidence/reachable-check.md.
Counts only: no question text, no qa_id, no asin.

    python3 docs/work/2026-10-22-g1-finding/tools/reachable_check.py
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "experiments" / "scripts"))

import corpus_gate as g  # noqa: E402

WORKLOAD = REPO / "data" / "workload-v1.json"
VECTORS = REPO / "data" / "v1-draft" / "workload" / "vectors.json"
OUT = REPO / "docs" / "work" / "2026-10-22-g1-finding" / "evidence" / "reachable-check.md"

# What 3.4 and the design review reported (ADR-014's facts). The check fails loudly if they differ.
EXPECT_RECORDS = {"validation": (74, 129), "test": (108, 155), "whole": (182, 284)}
EXPECT_PAIRS = {"validation": 45, "test": 67}
EXPECT_TRAPS = {"validation": 129, "test": 155}


def main() -> int:
    queries = g.load_workload(WORKLOAD)
    vectors = json.loads(VECTORS.read_text())
    for q in queries:
        q.embedding = vectors[q.qa_id]["vector"]
    traps = g.reachable_traps(queries)

    lines = [
        "# Reachable traps on the real workload — g1-finding, Block C step 16",
        "",
        "Written by `tools/reachable_check.py` from `data/workload-v1.json` and the vectors file, through the gate's own",
        "`reachable_traps`. Counts only. A trap is a record with a `probe_kind` other than `name-swap-same`; it is",
        f"reachable when its cosine with its `pair_of` partner is at least {g.SIM_FLOOR}.",
        "",
        "| scope | trap records | reachable | unique pairs | reachable pairs |",
        "| :--- | ---: | ---: | ---: | ---: |",
    ]
    failures = []
    for scope in (*g.SPLITS, "whole"):
        t = traps[scope]["all"]
        lines.append(
            f"| {scope} | {t['records']} | {t['reachable']} | {t['pairs']} | {t['pairs_reachable']} |"
        )
        if (t["reachable"], t["records"]) != EXPECT_RECORDS[scope]:
            failures.append(
                f"{scope}: records {t['reachable']}/{t['records']}, expected {EXPECT_RECORDS[scope]}"
            )
        if scope in EXPECT_PAIRS and t["pairs_reachable"] != EXPECT_PAIRS[scope]:
            failures.append(
                f"{scope}: reachable unique pairs {t['pairs_reachable']}, expected {EXPECT_PAIRS[scope]}"
            )

    lines += ["", "## By probe kind (reachable / records; reachable pairs / unique pairs)", ""]
    kinds = sorted({k for scope in g.SPLITS for k in traps[scope] if k != "all"})
    lines += ["| probe_kind | validation | test |", "| :--- | :--- | :--- |"]
    for kind in kinds:
        cells = []
        for scope in g.SPLITS:
            c = traps[scope].get(kind)
            cells.append(
                f"{c['reachable']}/{c['records']} · {c['pairs_reachable']}/{c['pairs']}" if c else "—"
            )
        lines.append(f"| {kind} | {cells[0]} | {cells[1]} |")

    lines += [
        "",
        "## The three trap definitions agree",
        "",
        "| split | by `probe_kind` | by `pair_of` | by stratum (B-within, B-cross) |",
        "| :--- | ---: | ---: | ---: |",
    ]
    for split in g.SPLITS:
        rs = [q for q in queries if q.split == split and q.probe_kind not in g.NOT_A_TRAP]
        by_kind = sum(1 for q in rs if q.probe_kind)
        by_pair = sum(1 for q in rs if q.pair_of)
        by_stratum = sum(1 for q in rs if q.stratum in ("B-within", "B-cross"))
        lines.append(f"| {split} | {by_kind} | {by_pair} | {by_stratum} |")
        if not (by_kind == by_pair == by_stratum == EXPECT_TRAPS[split]):
            failures.append(
                f"{split}: definitions give {by_kind}, {by_pair}, {by_stratum}; expected {EXPECT_TRAPS[split]}"
            )

    mutual = sum(
        1
        for q in queries
        if q.probe_kind
        and q.probe_kind not in g.NOT_A_TRAP
        and next((p for p in queries if p.qa_id == q.pair_of), None) is not None
        and next(p for p in queries if p.qa_id == q.pair_of).pair_of == q.qa_id
    )
    lines += ["", f"Trap records that are mutual twins (each names the other): {mutual}.", ""]
    lines.append("**Result: " + ("all expected counts reproduced.**" if not failures else "MISMATCH.**"))
    for f in failures:
        lines.append(f"- {f}")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.relative_to(REPO)}")
    for f in failures:
        print("MISMATCH:", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
