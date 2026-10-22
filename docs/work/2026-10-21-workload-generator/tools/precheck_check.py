"""Pre-check a check-round rows file (blind, swap) against its sheet with build_workload's check_label.

Read-only: prints the problems and never edits a row. It checks the shape and the evidence only; it
never shows the reference label, so the blind label stays blind. The records come from the sheet
text, which `make workload-sheets` wrote; data/v1-draft/ is not read here.
Usage: precheck_check.py <sheet.md> <rows.jsonl>
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/Users/hung/Desktop/Sem1/thesis/experiments/scripts")
import build_workload as bw

sheet_path, rows_path = map(Path, sys.argv[1:])
products: dict[str, bw.Product] = {}
task_doc: dict[str, str] = {}
doc = None
fields: list[tuple[str, str]] = []
in_task = False
for raw in sheet_path.read_text().splitlines():
    m = re.match(r"## `([^`]+)` · (\w+) · (\S+)", raw)
    if m:
        doc, dept, leaf = m.groups()
        fields, in_task = [], False
        continue
    m = re.match(r"- \*\*(.+?)\*\*: (.*)$", raw)
    if m and doc and not in_task:
        fields.append((m.group(1), bw.collapse(m.group(2))))
        products[doc] = bw.Product(doc, dept, leaf, fields[0][1], tuple(fields), False)
        continue
    m = re.match(r"### `([^`]+)`", raw)
    if m:
        task_doc[m.group(1)] = doc
        in_task = True

rows = [json.loads(x) for x in rows_path.read_text().splitlines() if x.strip()]
keys = [r["key"] for r in rows]
missing = sorted(set(task_doc) - set(keys))
extra = sorted(set(keys) - set(task_doc))
dupes = sorted({k for k in keys if keys.count(k) > 1})
bad = 0
for r in rows:
    if r["key"] not in task_doc:
        continue
    type_ = r["key"].split(":")[0]
    product = products[task_doc[r["key"]]]
    if set(r) - bw.claude_fields(type_) or r.get("type") != type_:
        problems = ["fields or type wrong"]
    else:
        problems = bw.check_label(r, product)
        if type_ == "swap" and not problems and r["answerable"] and not isinstance(r.get("same_answer"), bool):
            problems.append("same_answer: true or false, for an answerable swap")
    if problems:
        bad += 1
        print(f"PROBLEM {r['key']}")
        for p in problems:
            print(f"   {p}")
n_ans = sum(1 for r in rows if r.get("answerable"))
print(f"{len(rows)} rows ({n_ans} answerable), {len(task_doc)} tasks, {bad} with problems, "
      f"missing {missing}, extra {extra}, duplicated {dupes}")
sys.exit(1 if bad or missing or extra or dupes else 0)
