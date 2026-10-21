#!/usr/bin/env python3
"""Pre-check a write-round rows file against its sheet with build_workload's own check_row.

Read-only: prints the problems and never edits a row (rejects are re-done by hand). The records
come from the sheet text, which `make workload-sheets` wrote; data/v1-draft/ is not read here.
Usage: precheck.py <sheet.md> <rows.jsonl> [earlier rows files ...]
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/Users/hung/Desktop/Sem1/thesis/experiments/scripts")
import build_workload as bw  # noqa: E402
import corpus_gate  # noqa: E402

sheet_path, rows_path, *prior = map(Path, sys.argv[1:])
inputs = bw.load_inputs(iter([]), bw.POLICY_DIR)
names: dict[str, str] = {}
tasks: dict[str, bw.Task] = {}
labels: dict[str, dict] = {}  # seed key -> pass-1 label shown on the sheet
cell_sources: dict[str, list[str]] = {}

doc = dept = leaf = None
fields: list[tuple[str, str]] = []
key = None
for raw in sheet_path.read_text().splitlines():
    m = re.match(r"## `([^`]+)` · (\w+) · (\S+)(?: · short name \*\*(.+)\*\*)?$", raw)
    if m:
        doc, dept, leaf, name = m.groups()
        names[doc] = name
        fields = []
        key = None
        continue
    m = re.match(r"## Policy cells · (\w+)", raw)
    if m:
        doc, dept, key = None, m.group(1), None
        continue
    m = re.match(r"- \*\*(.+?)\*\*: (.*)$", raw)
    if m and key is None and doc:
        fields.append((m.group(1), bw.collapse(m.group(2))))
        title = fields[0][1]
        inputs.products[doc] = bw.Product(doc, dept, leaf, title, tuple(fields), False)
        continue
    m = re.match(r"### `([^`]+)`", raw)
    if m:
        key = m.group(1)
        type_ = key.split(":")[0]
        parts = key.split(":")
        if type_ in ("seed", "para", "lookalike"):
            ref = f"{parts[1]}:{parts[2]}"
            ctx = {"ref": ref}
            if type_ == "para":
                ctx["kind"] = parts[3]
            if type_ == "lookalike":
                ctx["label"] = labels.get(f"seed:{ref}", {})
            tasks[key] = bw.Task(key, type_, "write", doc, ctx)
        elif type_ == "d":
            tasks[key] = bw.Task(key, "d", "write", doc, {})
        elif type_ == "cell":
            cell_sources[key] = []
        continue
    if key is None:
        continue
    t = tasks.get(key)
    m = re.match(r"Original question: (.*)$", raw)
    if m:
        ref = t.context["ref"]
        d_, line_no = ref.rsplit(":", 1)
        inputs.pool[ref] = bw.PoolLine(d_, int(line_no), dept, m.group(1).strip(), "", "spec", None)
        continue
    m = re.match(r"(?:Your pass-1 answer|Seed answer): (.*) \| evidence: (.*)$", raw)
    if m and t is not None:
        labels[key if t.type == "seed" else f"seed:{t.context['ref']}"] = {
            "answer": m.group(1), "evidence": m.group(2)}
        if t.type == "lookalike":
            t.context["label"] = labels[f"seed:{t.context['ref']}"]
        continue
    m = re.match(r"Policy document: (\S+)", raw)
    if m and t is not None and t.type == "d":
        t.context["policy"] = m.group(1)
        continue
    m = re.match(r"Document: (\S+) · shape `(\w+)`", raw)
    if m:
        cell_doc, shape = m.groups()
        continue
    m = re.match(r"Wordings: (\d+)", raw)
    if m:
        variant = key.split(":")[3] if key.count(":") >= 3 else ""
        cell = bw.Cell(key.split(":", 1)[1], cell_doc, shape, variant, (), int(m.group(1)))
        tasks[key] = bw.Task(key, "cell", "write", dept, {"cell": cell})
        continue
    m = re.match(r"- `([^`]+)`: ", raw)
    if m and key.startswith("cell:"):
        cell_sources[key].append(m.group(1))

layer = {f"name:{d}": {"type": "name", "doc_id": d, "name": n} for d, n in names.items() if n}
forms = set()
for p in prior:
    for raw in p.read_text().splitlines():
        if raw.strip():
            r = json.loads(raw)
            if r["type"] in ("seed", "para", "lookalike", "d"):
                forms.add(corpus_gate.normalize_t1(r["question"]))
            if r["type"] == "seed":  # a paraphrase in a later file finds its seed
                layer[r["key"]] = r
ctx = bw.Context(inputs, layer, forms=forms)

rows = [json.loads(x) for x in rows_path.read_text().splitlines() if x.strip()]
keys = [r["key"] for r in rows]
missing = sorted(set(tasks) - set(keys))
extra = sorted(set(keys) - set(tasks))
bad = 0
for r in sorted(rows, key=lambda r: bw.TYPE_ORDER.index(r["type"])):
    t = tasks.get(r["key"])
    if t is None:
        continue
    if set(r) - bw.claude_fields(t.type) or r.get("type") != t.type:
        problems = ["fields or type wrong"]
    elif t.type == "cell":
        problems = bw.check_row({**r, "origin": "claude", "source": None}, t, ctx)
        if r.get("origin") == "pqa-template" and r.get("source") not in cell_sources[r["key"]]:
            problems.append("source: not one of the sheet's real pool questions")
        if r.get("origin") == "claude" and r.get("source") is not None:
            problems.append("source: null when origin is claude")
    else:
        problems = bw.check_row(r, t, ctx)
    if problems:
        bad += 1
        print(f"PROBLEM {r['key']}")
        for p in problems:
            print(f"   {p}")
        continue
    ctx.accepted[r["key"]] = {**r, "doc_id": t.group}
    if t.type in ("seed", "para", "lookalike", "d"):
        ctx.forms.add(corpus_gate.normalize_t1(r["question"]))
print(f"{len(rows)} rows, {len(tasks)} tasks, {bad} with problems, missing {missing}, extra {extra}")
sys.exit(1 if bad or missing or extra else 0)
