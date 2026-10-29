"""Item 4.4: the update set's probe and its validator.

    make update-set-probe OUT=docs/work/<task>/evidence/private/probe.json
    make update-set-verify

`probe` runs the product-scoped `retrieve` for every validation query (v1 in Redis, the embedding
model only) and writes `qa_id -> chunk_ids`. IDs only: no question text. It is used to pick chunks that
some query retrieves, so that an edit of such a chunk has a dependent to purge.

`verify` checks done condition 1 offline. It rebuilds the v1 chunk texts with
`ingest.records_to_nodes`, which needs no embedding, and checks the manifest hash. It names edits by
`edit_id` and chunks by `chunk_id`, and never prints text, because the set's product text is Amazon-PQA.

The set (`data/update-set-v1.json`, gitignored) is a JSON array of rows, data-card.md section 5:
`edit_id, doc_id, chunk_id, change_type, before, after, expected_effect`.
The manifest (`data/update-set-manifest.json`, tracked) holds the file's sha256 and counts.

Exit codes: 0 done / the set is valid; 1 a check failed.
"""

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SET_PATH = ROOT / "data" / "update-set-v1.json"
MANIFEST_PATH = ROOT / "data" / "update-set-manifest.json"
CORPUS_DIR = ROOT / "data" / "v1"
VALIDATION_PATH = ROOT / "data" / "workload-v1-validation.json"

FIELDS = (
    "edit_id",
    "doc_id",
    "chunk_id",
    "change_type",
    "before",
    "after",
    "expected_effect",
)
CHANGE_TYPES = ("substantive", "cosmetic")
EDITS = 20
PER_TYPE = 10
MIN_PER_KIND = (
    4  # in each half: at least this many policy edits and this many product edits
)
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def kind_of(doc_id: str) -> str:
    return "policy" if doc_id.startswith("policy-") else "product"


def chunk_texts(corpus_dir: Path, dataset_version: str = "v1") -> dict[str, str]:
    """chunk_id -> text, as ingest writes it. Splitting only: no embedding, no Redis."""
    from rag.ingest import load_records, records_to_nodes

    nodes = records_to_nodes(load_records(Path(corpus_dir)), dataset_version)
    return {n.id_: n.text for n in nodes}


def verify(set_path: Path, corpus_dir: Path, manifest_path: Path) -> list[str]:
    """Every problem with the set, as a list of messages. An empty list means it is valid.

    A message names an edit by `edit_id` or a chunk by `chunk_id` and never quotes text.
    """
    problems: list[str] = []
    try:
        rows = json.loads(Path(set_path).read_text())
    except (OSError, ValueError) as e:
        return [f"{set_path}: cannot be read as JSON ({type(e).__name__})"]
    if not isinstance(rows, list):
        return [f"{set_path}: expected a JSON array of edits"]

    # Schema first: the checks below read these fields.
    for i, row in enumerate(rows):
        name = row.get("edit_id", f"row {i}") if isinstance(row, dict) else f"row {i}"
        if not isinstance(row, dict):
            problems.append(f"{name}: not an object")
            continue
        for field in FIELDS:
            if not isinstance(row.get(field), str) or not row[field]:
                problems.append(
                    f"{name}: field {field!r} is missing or not a non-empty string"
                )
    if problems:
        return problems

    if len(rows) != EDITS:
        problems.append(f"{len(rows)} edits, want {EDITS}")
    ids = [r["edit_id"] for r in rows]
    for dup in sorted(k for k, n in Counter(ids).items() if n > 1):
        problems.append(f"duplicate edit_id {dup}")
    chunk_counts = Counter(r["chunk_id"] for r in rows)
    for dup in sorted(k for k, n in chunk_counts.items() if n > 1):
        problems.append(
            f"duplicate chunk {dup}: {chunk_counts[dup]} edits on one chunk"
        )

    for r in rows:
        if r["change_type"] not in CHANGE_TYPES:
            problems.append(
                f"{r['edit_id']}: change_type {r['change_type']!r} is not in {CHANGE_TYPES}"
            )
        if r["chunk_id"].split("#", 1)[0] != r["doc_id"]:
            problems.append(
                f"{r['edit_id']}: chunk {r['chunk_id']} is not in doc {r['doc_id']}"
            )

    for change_type in CHANGE_TYPES:
        half = [r for r in rows if r["change_type"] == change_type]
        if len(half) != PER_TYPE:
            problems.append(f"{len(half)} {change_type} edits, want {PER_TYPE}")
        for kind in ("policy", "product"):
            n = sum(1 for r in half if kind_of(r["doc_id"]) == kind)
            if n < MIN_PER_KIND:
                problems.append(
                    f"{n} {kind} edits among the {change_type} ones, want at least {MIN_PER_KIND}"
                )

    texts = chunk_texts(corpus_dir)
    for r in rows:
        eid, chunk = r["edit_id"], r["chunk_id"]
        if chunk not in texts:
            problems.append(f"{eid}: chunk {chunk} is not in the corpus")
        elif r["before"] != texts[chunk]:
            problems.append(f"{eid}: before is not the v1 text of {chunk}")
        if r["after"] == r["before"]:
            problems.append(f"{eid}: after equals before")
        if r["change_type"] == "cosmetic":
            lost = Counter(NUMBER.findall(r["before"])) - Counter(
                NUMBER.findall(r["after"])
            )
            if lost:
                problems.append(
                    f"{eid}: a cosmetic edit must keep every number of its before; "
                    f"{sum(lost.values())} number(s) lost"
                )

    if not any(
        r["change_type"] == "substantive"
        and r["doc_id"].startswith("policy-return")
        and "30 days" in r["before"]
        and "14 days" in r["after"]
        for r in rows
    ):
        problems.append(
            "no substantive policy-return edit changes '30 days' to '14 days'"
        )

    try:
        manifest = json.loads(Path(manifest_path).read_text())
        want = manifest["sha256"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        problems.append(f"{manifest_path}: no readable sha256 ({type(e).__name__})")
    else:
        got = sha256_file(set_path)
        if got != want:
            problems.append(
                f"manifest sha256 {want[:12]}... does not match the set's {got[:12]}..."
            )
    return problems


def probe(out_path: Path, workload_path: Path = VALIDATION_PATH) -> int:
    """qa_id -> chunk_ids for every validation query, by the product-scoped `retrieve`.

    The same call the RAG server makes for the gateway, so a chunk the probe ties to a query is a chunk
    the live run's retrieval will return for it.
    """
    from rag.retrieve import retrieve

    rows = json.loads(Path(workload_path).read_text())
    result: dict[str, list[str]] = {}
    for i, row in enumerate(rows, 1):
        chunks, _epoch = retrieve(row["question"], product_id=row.get("product_id"))
        result[row["qa_id"]] = [c.chunk_id for c in chunks]
        if i % 50 == 0 or i == len(rows):
            print(f"probed {i}/{len(rows)}", flush=True)
    Path(out_path).write_text(json.dumps(result, sort_keys=True, indent=1) + "\n")
    print(f"wrote {out_path}: {len(result)} queries, IDs only")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser(
        "probe", help="qa_id -> chunk_ids for the validation queries"
    )
    p_probe.add_argument("--out", required=True, type=Path)
    p_probe.add_argument("--workload", type=Path, default=VALIDATION_PATH)

    p_verify = sub.add_parser("verify", help="check the update set offline")
    p_verify.add_argument("--set", type=Path, default=SET_PATH, dest="set_path")
    p_verify.add_argument("--corpus-dir", type=Path, default=CORPUS_DIR)
    p_verify.add_argument("--manifest", type=Path, default=MANIFEST_PATH)

    args = parser.parse_args(argv)
    if args.command == "probe":
        return probe(args.out, args.workload)

    problems = verify(args.set_path, args.corpus_dir, args.manifest)
    for p in problems:
        print(f"FAIL  {p}")
    if problems:
        print(f"update-set-verify: {len(problems)} problem(s)")
        return 1
    print(
        f"update-set-verify: ok ({EDITS} edits, {PER_TYPE} substantive, {PER_TYPE} cosmetic)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
