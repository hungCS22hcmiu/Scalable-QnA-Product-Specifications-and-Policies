"""Plan step 1: the pair counts the gate must reproduce, derived offline before any gate run.

Read-only. It reads data/workload-v1.json and the 3.4 vectors file, and writes
evidence/expected-pairs.md. Counts only: no question text, no qa_id, no asin.

numpy screens the 811 k pairs; every pair it keeps is then recomputed with corpus_gate's own
plain-Python cosine, so the counts here follow the gate's arithmetic and not numpy's.

    python3 docs/work/2026-10-22-corpus-freeze/tools/expected_pairs.py
"""

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "experiments" / "scripts"))
import corpus_gate as gate

WORKLOAD = REPO / "data" / "workload-v1.json"
VECTORS = REPO / "data" / "v1-draft" / "workload" / "vectors.json"
OUT = REPO / "docs" / "work" / "2026-10-22-corpus-freeze" / "evidence" / "expected-pairs.md"
SCREEN = gate.SIM_FLOOR - 0.01  # numpy keeps everything this close; the gate's cosine decides
BAND = 0.001


def main():
    records = json.loads(WORKLOAD.read_text())
    vec = {k: v["vector"] for k, v in json.loads(VECTORS.read_text()).items()}
    ids = [r["qa_id"] for r in records]
    split = [r["split"] for r in records]
    lists = [vec[i] for i in ids]
    norms = [gate._norm(v) for v in lists]

    m = np.array(lists, dtype=np.float64)
    m /= np.linalg.norm(m, axis=1, keepdims=True)
    gram = m @ m.T
    ii, jj = np.where(np.triu(gram >= SCREEN, k=1))

    kept = []  # (i, j, gate cosine)
    for i, j in zip(ii.tolist(), jj.tolist(), strict=True):
        kept.append((i, j, gate._cosine_with_norms(lists[i], lists[j], norms[i], norms[j])))
    pairs = [p for p in kept if p[2] >= gate.SIM_FLOOR]

    def where(i, j):
        if split[i] == split[j]:
            return split[i]
        return "across"

    counts = {"validation": 0, "test": 0, "across": 0}
    for i, j, _ in pairs:
        counts[where(i, j)] += 1

    near = [p for p in kept if abs(p[2] - gate.SIM_FLOOR) <= BAND]
    near_counts = {"validation": 0, "test": 0, "across": 0}
    for i, j, _ in near:
        near_counts[where(i, j)] += 1
    nearest = min(abs(p[2] - gate.SIM_FLOOR) for p in kept)
    above = sum(p[2] >= gate.SIM_FLOOR for p in near)

    # numpy against the gate's arithmetic: the largest difference over the pairs near the line.
    diff = max(abs(float(gram[i, j]) - c) for i, j, c in near)

    lines = [
        "# Expected similar-pair counts — item 3.6, plan step 1",
        "",
        "Written by `tools/expected_pairs.py` from `data/workload-v1.json` and the 3.4 vectors file,",
        "before any gate run on `v1`. Counts only. These are the expected values for acceptance A3 (ii):",
        f"the gate's `similar_pairs` (cosine ≥ {gate.SIM_FLOOR}) must give the same three numbers.",
        "",
        f"Queries: {len(records)}. Cosines are `corpus_gate._cosine_with_norms` on the stored vectors.",
        "",
        f"## Pairs with cosine ≥ {gate.SIM_FLOOR}",
        "",
        "| where | pairs |",
        "| :--- | ---: |",
        f"| inside validation | {counts['validation']} |",
        f"| inside test | {counts['test']} |",
        f"| across the splits | {counts['across']} |",
        f"| **all** | **{len(pairs)}** |",
        "",
        f"## Pairs within ±{BAND} of {gate.SIM_FLOOR}",
        "",
        "A pair this close to the line is the one an embedding that moved in the last digits would flip.",
        "",
        "| where | pairs |",
        "| :--- | ---: |",
        f"| inside validation | {near_counts['validation']} |",
        f"| inside test | {near_counts['test']} |",
        f"| across the splits | {near_counts['across']} |",
        f"| **all** | **{len(near)}** ({above} at or above the line) |",
        "",
        f"Nearest pair to the line: |cosine − {gate.SIM_FLOOR}| = {nearest:.2e}.",
        f"Largest numpy-against-gate difference over those pairs: {diff:.1e}.",
    ]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.relative_to(REPO)}")
    print(f"all={len(pairs)} " + " ".join(f"{k}={v}" for k, v in counts.items()))
    print(f"near={len(near)} nearest={nearest:.2e} numpy-vs-gate={diff:.1e}")


if __name__ == "__main__":
    main()
