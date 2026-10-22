"""Partner cosines, reachable traps and cross-split near-duplicates (review F1, F3, F8).

Read-only: it reads data/workload-v1.json and the vectors file, and writes
evidence/partner-cosine.md. Counts only: no question text, no qa_id, no asin.

    python3 docs/work/2026-10-21-workload-generator/tools/partner_cosine.py
"""

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
WORKLOAD = REPO / "data" / "workload-v1.json"
VECTORS = REPO / "data" / "v1-draft" / "workload" / "vectors.json"
OUT = REPO / "docs" / "work" / "2026-10-21-workload-generator" / "evidence" / "partner-cosine.md"
FLOOR = 0.85  # corpus_gate.SIM_FLOOR: the lowest tau a run sweeps to, with the same meaning as A / C
SKEWS = (0.8, 1.1, 1.4)


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


def median(values):
    s = sorted(values)
    return s[len(s) // 2]


def main():
    records = json.loads(WORKLOAD.read_text())
    vec = {k: v["vector"] for k, v in json.loads(VECTORS.read_text()).items()}
    by_id = {r["qa_id"]: r for r in records}

    partner = {}
    for r in records:
        if r["pair_of"]:
            partner[r["qa_id"]] = cosine(vec[r["qa_id"]], vec[r["pair_of"]])

    kinds = defaultdict(list)
    for r in records:
        if r["qa_id"] in partner:
            kinds[r["probe_kind"]].append(partner[r["qa_id"]])

    intro = ("Written by `tools/partner_cosine.py` from `data/workload-v1.json` and the vectors file;"
             " counts only. The build report does not show these.")
    lines = [
        "# Partner cosine and reachable traps — item 3.4 (review F1, F3, F8)",
        "",
        intro,
        "",
        "## Each probe against its `pair_of` target",
        "",
        f"| probe_kind | n | median | max | ≥ {FLOOR} |",
        "| :--- | ---: | ---: | ---: | ---: |",
    ]
    for kind in sorted(kinds):
        v = kinds[kind]
        lines.append(f"| {kind} | {len(v)} | {median(v):.3f} | {max(v):.3f} |"
                     f" {sum(x >= FLOOR for x in v)} |")

    trap_note = (f"A trap is a probe other than `name-swap-same`. It is reachable when its cosine"
                 f" with its partner is at least {FLOOR}.")
    lines += ["", "## Reachable traps", "", trap_note, "",
              "| file | records | traps | reachable | trap fraction | reachable fraction |",
              "| :--- | ---: | ---: | ---: | ---: | ---: |"]
    for name, rs in (("whole", records),
                     ("validation", [r for r in records if r["split"] == "validation"]),
                     ("test", [r for r in records if r["split"] == "test"])):
        traps = [r for r in rs if r["probe_kind"] not in (None, "name-swap-same")]
        reach = [r for r in traps if partner.get(r["qa_id"], 0) >= FLOOR]
        lines.append(f"| {name} | {len(rs)} | {len(traps)} | {len(reach)} |"
                     f" {len(traps) / len(rs):.4f} | {len(reach) / len(rs):.4f} |")

    twin_kinds = ("policy-condition", "condition-department")
    lines += ["", "## Minimal-pair twins", "",
              "| split | twin records | twin pairs |", "| :--- | ---: | ---: |"]
    for split in ("validation", "test"):
        twins = [r for r in records if r["split"] == split and r["probe_kind"] in twin_kinds]
        lines.append(f"| {split} | {len(twins)} | {len(twins) // 2} |")

    cells, d = defaultdict(list), defaultdict(list)
    for r in records:
        if r["role"] == "d":
            d[r["doc_ids"][1]].append(r)
        elif r["doc_ids"][0].startswith("policy-"):
            cells[r["doc_ids"][0]].append(r)
    counts = Counter()
    for doc in set(cells) | set(d):
        group = [(r, False) for r in cells[doc]] + [(r, True) for r in d[doc]]
        for i, (a, a_d) in enumerate(group):
            for b, b_d in group[i + 1:]:
                if a["split"] != b["split"] and cosine(vec[a["qa_id"]], vec[b["qa_id"]]) >= FLOOR:
                    counts["with a D query" if a_d or b_d else "cell against cell"] += 1
    lines += ["", f"## Query pairs on one policy document, in different splits, cosine ≥ {FLOOR}", "",
              "| pair | count |", "| :--- | ---: |"]
    for k in ("cell against cell", "with a D query"):
        lines.append(f"| {k} | {counts[k]} |")

    lines += ["", "## If the whole file were a run file (`ask.js` takes the file index as the rank)", "",
              "| skew | share of traffic on test records |", "| ---: | ---: |"]
    for skew in SKEWS:
        w = [1 / (i + 1) ** skew for i in range(len(records))]
        test = sum(x for x, r in zip(w, records, strict=True) if r["split"] == "test")
        lines.append(f"| {skew} | {test / sum(w):.3f} |")
    assert len(by_id) == len(records)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
