"""Plan step 12, unknown U4: which evidence string belongs to which workload qa_id.

Read-only. The evidence is in the model layer (gitignored), keyed by the model layer's own keys;
the workload is keyed by qa_id. `build_workload.construct` joins them with fixed id stems, and this
follows the same stems (build_workload.py:1598-1665), so a record gets the evidence its row has:

    q-{doc}-{line}-seed          the seed's first label       (an answerable seed)
    q-{doc}-{line}-para-*        the same label: a paraphrase asks the same thing
    q-{doc}-{line}-look          the lookalike row's own evidence
    q-{doc}-x-{from}-{line}      the name-swap row's evidence, in the swapped-to product
    q-{doc}-{line}-natural       the natural pair's a_ or b_ evidence

A policy cell, a D query and an unanswerable seed have none, and are not in the output.

Writes data/v1-draft/gate/evidence-spans.json (gitignored: qa_ids and PQA text). Prints counts only.

    python3 docs/work/2026-10-22-corpus-freeze/tools/evidence_spans.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "experiments" / "scripts"))
import build_workload as bw
import corpus_gate
import select_pqa

WORKLOAD = REPO / "data" / "workload-v1.json"
OUT = REPO / "data" / "v1-draft" / "gate" / "evidence-spans.json"


def evidence_by_qa_id(inputs, layer) -> dict[str, dict]:
    labels = bw.first_labels(layer)
    out: dict[str, dict] = {}

    def put(qa_id: str, doc_id: str, evidence: str) -> None:
        if evidence:
            out[qa_id] = {"doc_id": doc_id, "evidence": evidence}

    for doc_id, refs in bw.seed_refs(inputs, layer).items():
        for ref in refs:
            line, label = inputs.pool[ref], labels[ref]
            stem = f"q-{doc_id}-{line.line_no}"
            if label["answerable"]:
                put(f"{stem}-seed", doc_id, label["evidence"])
                for kind in ("close", "far"):
                    put(f"{stem}-para-{kind}", doc_id, label["evidence"])
            row = layer.get(f"lookalike:{ref}")
            if row:
                put(f"{stem}-look", doc_id, row["evidence"])

    for row in bw.rows_of(layer, "swap"):
        line = inputs.pool[row["ref"]]
        put(f"q-{row['doc_id']}-x-{row['from']}-{line.line_no}", row["doc_id"], row["evidence"])

    for row in bw.natural_pairs_kept(layer):
        for side in ("a", "b"):
            line = inputs.pool[row[side]]
            put(f"q-{row['doc_id']}-{line.line_no}-natural", row["doc_id"], row[f"{side}_evidence"])
    return out


def main():
    inputs = bw.load_inputs(
        select_pqa.iter_selection(select_pqa.SELECTION_PATH, select_pqa.DRAFT_DIR), bw.POLICY_DIR
    )
    layer = bw.load_layer(bw.LAYER_PATH)
    found = evidence_by_qa_id(inputs, layer)

    records = json.loads(WORKLOAD.read_text())
    in_workload = {r["qa_id"]: r for r in records}
    kept = {qa_id: v for qa_id, v in found.items() if qa_id in in_workload}
    corpus_gate.require_git_ignored(OUT)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(sorted(kept.items())), indent=0))

    print(f"evidence strings the model layer gives: {len(found)}")
    print(f"  of those, qa_ids in the workload   : {len(kept)}")
    print(f"  not in the workload (dropped)      : {len(found) - len(kept)}")
    by_kind: Counter = Counter()
    for r in records:
        has = r["qa_id"] in kept
        by_kind[(r["role"], r["probe_kind"] or "-", has)] += 1
    print("\nworkload records by role and probe kind: with evidence / without")
    for role, kind in sorted({(a, b) for a, b, _ in by_kind}):
        print(f"  {role:<10} {kind:<22} {by_kind[(role, kind, True)]:>4} / {by_kind[(role, kind, False)]:>4}")
    print(f"\nwrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
