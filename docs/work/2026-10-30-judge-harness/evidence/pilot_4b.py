"""Diagnostic pilot (2026-11-01, citable: no): regenerate the 30 sufficiency-sheet references with another
generator setting, and nothing else. Not part of the frozen protocol; never writes experiments/references/.

Each reference uses what `judge_references.build` uses: the gold chunks from `retrieve.fetch_by_ids`, in the
index's order, and `generate._build_prompt` (the served prompt, unchanged). Only the model and the options
differ: `temperature 0` and a fixed seed, so a rerun gives the same text. `think: false` as on every call.

Usage (from the repo root):
    python3 docs/work/2026-10-30-judge-harness/evidence/pilot_4b.py ARM MODEL
ARM names the output folder under evidence/private/pilot-4b/; it refuses a folder that exists.
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "experiments/scripts")
import judge_references as jr

from rag import config, generate, retrieve

TRAIL = Path("docs/work/2026-10-30-judge-harness/evidence")
SHEET = TRAIL / "private/sufficiency-v2.md"
OUT_ROOT = TRAIL / "private/pilot-4b"
OPTIONS = {"num_ctx": config.LLM_NUM_CTX, "temperature": 0, "seed": 20261101}


def pressure() -> int:
    out = subprocess.run(
        ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(out.stdout.strip())


def sheet_rows() -> list[dict]:
    """The 30 rows of sufficiency-v2.md, in its order, with the author's two marks."""
    text = SHEET.read_text()
    index = {r["qa_id"]: r for r in jr.read_index(jr.REFERENCES_DIR / "validation")}
    rows = []
    for part in re.split(r"(?m)^(?=## \d+\. )", text)[1:]:
        m = re.match(r"## (\d+)\. (\S+)", part)
        row = dict(index[m.group(2)])
        row["row"] = int(m.group(1))
        row["sufficient"] = jr.SUFFICIENT.findall(part)[-1]
        row["reference_right_2b"] = jr.REFERENCE_RIGHT.findall(part)[-1]
        rows.append(row)
    assert [r["row"] for r in rows] == list(range(1, 31))
    return rows


def main(arm: str, model: str) -> int:
    out = OUT_ROOT / arm
    if out.exists():
        print(f"REFUSED: {out} exists")
        return 1
    base = config.OLLAMA_BASE_URL.rstrip("/")
    tags = jr.http_json(f"{base}/api/tags")
    digest = next(m["digest"] for m in tags["models"] if m["name"] == model)
    level = pressure()
    print(f"pressure before {arm}: {level}")
    if level >= 4:
        print("STOP: pressure is critical (4)")
        return 1

    (out / "answers").mkdir(parents=True)
    rows, readings = [], [level]
    for r in sheet_rows():
        chunks, _ = retrieve.fetch_by_ids(list(r["chunk_ids"]))
        if [c.chunk_id for c in chunks] != list(r["chunk_ids"]):
            raise SystemExit(
                f"row {r['row']}: fetch_by_ids did not return the gold chunks in order"
            )
        t0 = time.monotonic()
        reply = jr.http_json(
            f"{base}/api/generate",
            {
                "model": model,
                "prompt": generate._build_prompt(r["question"], chunks),
                "stream": False,
                "think": False,
                "options": OPTIONS,
            },
            timeout=600.0,
        )
        text = reply["response"]
        sha = jr.sha256_bytes(text.encode("utf-8"))
        (out / "answers" / f"{sha}.txt").write_text(text)
        rows.append(
            {
                "row": r["row"],
                "qa_id": r["qa_id"],
                "stratum": r["stratum"],
                "sufficient": r["sufficient"],
                "reference_right_2b": r["reference_right_2b"],
                "reference_sha256_2b": r["reference_sha256"],
                "reference_sha256": sha,
                "declines": bool(jr.DONT_KNOW.search(text)),
                "seconds": round(time.monotonic() - t0, 1),
            }
        )
        if r["row"] % 10 == 0:
            readings.append(pressure())
            print(f"  {r['row']}/30; pressure {readings[-1]}")
    (out / "index.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
    (out / "version.json").write_text(
        json.dumps(
            {
                "arm": arm,
                "model": model,
                "digest": digest,
                "options": OPTIONS,
                "think": False,
                "prompt_sha256": jr.sha256_bytes(
                    generate._PROMPT_TEMPLATE.encode("utf-8")
                ),
                "reference_set": "00c9a33310a66542d739a860e3e77a162658a5dddaefa00fbc3e8ea30ca558e3",
                "pressure_readings": readings,
                "written": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
            indent=2,
        )
        + "\n"
    )
    print(
        f"wrote {out}: 30 references; index sha256 {jr.sha256_file(out / 'index.jsonl')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
