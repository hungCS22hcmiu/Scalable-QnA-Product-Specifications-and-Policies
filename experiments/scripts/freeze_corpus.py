"""Freeze the v1 corpus — super-plan item 3.6 (docs/work/2026-10-22-corpus-freeze/design.md §2.2).

    make corpus-assemble       data/v1/ from the drafts and the policy documents (bytes, copied)
    make corpus-index-check    is the index in Redis the corpus on disk? (a run's first step)
    make corpus-freeze         data/v1-freeze.json, from two passing gate runs
    make corpus-verify         do the files, chunks, model and config still match the record?

The record holds digests, counts and statistics only: no file name, asin, qa_id or absolute path.
This repository is public, and 152 of the corpus files carry an asin in their name. The messages
here follow the same rule and count. (`verify` names a covered file that changed only when the
gitignored per-file list from run 1 is there to name it from.)

`freeze` is written once. A different freeze is a different `dataset_version` and a different file.
`assemble` is not a restore path: it copies the sources into a clean `data/v1/` and refuses to
touch anything else (a gap carried to Phase 4, named in ADR-014).

Exit codes: 0 done · 1 a check failed · 2 refused, and nothing was written.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import build_pqa
import corpus_gate
import select_pqa

REPO_ROOT = corpus_gate.REPO_ROOT
VERSION = "v1"
FREEZE_VERSION = 1
EXPECTED_POLICIES = 12  # item 3.3's documents
GITKEEP = ".gitkeep"

# A freeze needs these from a gate report. A report written by an older gate lacks them, and is
# refused by name rather than read with defaults.
REQUIRED_REPORT_KEYS = (
    "dataset", "passed", "snapshot_digest", "files", "criteria", "statistics", "git", "embedding",
    "retrieval", "splitter", "packages", "chunk_digest", "chunk_count", "stored_vector_digest",
    "index_check", "grounding", "memory_pressure", "stage2_seconds",
)  # fmt: skip
# What two runs must agree on exactly. Pair counts may differ and are recorded (S2); these may not.
SAME_IN_BOTH_RUNS = (
    "snapshot_digest", "chunk_digest", "chunk_count", "stored_vector_digest", "embedding",
    "retrieval", "splitter", "packages",
)  # fmt: skip

ASIN = re.compile(r"\b[bB]0[0-9a-zA-Z]{8}\b")
QA_ID = re.compile(r"\bq-[a-z0-9]")


class Refusal(Exception):
    """A rule stopped the command before it wrote anything. Carries one line per reason."""

    def __init__(self, *lines: str):
        super().__init__("; ".join(lines))
        self.lines = list(lines)


@dataclass(frozen=True)
class Paths:
    selection: Path
    draft_dir: Path
    policies_dir: Path
    corpus_dir: Path
    workload: Path
    manifest: Path
    record: Path
    probe_flags: Path
    files_from: (
        Path  # run 1's report: the gitignored per-file list, if it is still there
    )


def default_paths(repo: Path = REPO_ROOT) -> Paths:
    data = repo / "data"
    gate = data / "v1-draft" / "gate"
    return Paths(
        selection=data / "pqa-selection.json",
        draft_dir=data / "v1-draft",
        policies_dir=data / "policies-v1",
        corpus_dir=data / VERSION,
        workload=data / f"workload-{VERSION}.json",
        manifest=data / "workload-manifest.json",
        record=data / f"{VERSION}-freeze.json",
        probe_flags=gate / "probe-flags.json",
        files_from=gate / "run1" / "report.json",
    )


# =================================================================================================
# assemble
# =================================================================================================
def _source_problem(path: Path, prefix: str, raw: bytes) -> str | None:
    try:
        record = json.loads(raw)
    except ValueError:
        return "is not JSON"
    doc_id = record.get("doc_id") if isinstance(record, dict) else None
    if doc_id != path.stem:
        return "has a name that is not its doc_id"
    if not doc_id.startswith(prefix):
        return f"has a doc_id without the {prefix!r} prefix"
    return None


def plan_assembly(p: Paths) -> list[tuple[str, bytes]]:
    """What `data/v1/` will hold, as `(file name, bytes)`. Raises Refusal before anything is written.

    The product files are read straight from the drafts and the policy documents from
    `data/policies-v1/`, never through `select_pqa.iter_selection`, which yields parsed records and
    would change the bytes.
    """
    if p.record.exists():
        raise Refusal(
            f"{p.record.name} exists: v1 is frozen. A different corpus is a different "
            "dataset_version."
        )
    try:
        selection = select_pqa.load_selection(p.selection)
        select_pqa.verify_selection(selection, p.draft_dir)
    except select_pqa.SelectionMismatch as e:
        raise Refusal(f"the drafts do not match the selection manifest ({e})") from e

    products = sorted((p.draft_dir / select_pqa.PRODUCTS).glob("*.json"))
    policies = sorted(p.policies_dir.iterdir()) if p.policies_dir.is_dir() else []
    problems = []
    if len(products) != selection["outputs"]["products"]:
        problems.append(
            f"{len(products)} product file(s); the selection manifest names "
            f"{selection['outputs']['products']}"
        )
    if len(policies) != EXPECTED_POLICIES:
        problems.append(
            f"{len(policies)} policy document(s); {EXPECTED_POLICIES} expected"
        )

    files: list[tuple[str, bytes]] = []
    kinds: Counter[str] = Counter()
    for path, prefix in [(x, "product-") for x in products] + [
        (x, "policy-") for x in policies
    ]:
        if path.suffix != ".json" or not path.is_file():
            kinds["is not a .json file"] += 1
            continue
        raw = path.read_bytes()
        problem = _source_problem(path, prefix, raw)
        if problem:
            kinds[problem] += 1
        else:
            files.append((path.name, raw))
    problems += [f"{n} source file(s) {kind}" for kind, n in sorted(kinds.items())]
    if problems:
        raise Refusal(*problems)

    want = dict(files)
    held = (
        {e.name: e for e in p.corpus_dir.iterdir() if e.name != GITKEEP}
        if p.corpus_dir.is_dir()
        else {}
    )
    stray = [n for n in held if n not in want]
    differing = [
        n
        for n, e in held.items()
        if n in want and (not e.is_file() or e.read_bytes() != want[n])
    ]
    if stray or differing:
        raise Refusal(
            f"{p.corpus_dir.name}/ holds {len(stray)} file(s) that are not part of the corpus and "
            f"{len(differing)} that differ from their source. Assemble never deletes or overwrites: "
            "clear the directory yourself, then run it again."
        )
    return files


def assemble(p: Paths) -> dict[str, int]:
    files = plan_assembly(p)
    p.corpus_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name, raw in files:
        dst = p.corpus_dir / name
        if dst.exists():  # the plan checked that it is the same bytes
            continue
        tmp = dst.with_name(f".{name}.tmp")
        tmp.write_bytes(raw)
        os.replace(tmp, dst)
        copied += 1
    # Each copy against its source, read again from disk: a copy that differs is a failure, loudly.
    sources = {path.name: path for path in _source_paths(p)}
    wrong = sum(
        build_pqa.sha256_file(p.corpus_dir / name)
        != build_pqa.sha256_file(sources[name])
        for name, _ in files
    )
    if wrong:
        raise RuntimeError(f"{wrong} copied file(s) differ from their source")
    return {
        "products": sum(1 for n, _ in files if n.startswith("product-")),
        "policies": sum(1 for n, _ in files if n.startswith("policy-")),
        "copied": copied,
        "present": len(files) - copied,
    }


def _source_paths(p: Paths) -> list[Path]:
    return sorted((p.draft_dir / select_pqa.PRODUCTS).glob("*.json")) + sorted(
        p.policies_dir.glob("*.json")
    )


def cmd_assemble(p: Paths) -> int:
    n = assemble(p)
    total = n["products"] + n["policies"]
    print(
        f"assembled {p.corpus_dir.name}/: {n['products']} product + {n['policies']} policy = "
        f"{total} files ({n['copied']} copied, {n['present']} already there); every copy equals its "
        "source by sha256"
    )
    return 0


# =================================================================================================
# check-index
# =================================================================================================
def _load_record(p: Paths) -> dict | None:
    return json.loads(p.record.read_text()) if p.record.is_file() else None


def cmd_check_index(p: Paths, client=None, base_url: str | None = None) -> int:
    """Is the index in Redis the corpus on disk? The first step of every run on v1, and of every
    reference generation (ADR-014): after this item Redis holds dev-v0, and a run on that proves
    nothing and says nothing."""
    from rag import config, store

    record = _load_record(p)
    result = corpus_gate.index_check(
        client or store.get_redis_client(),
        p.corpus_dir,
        VERSION,
        base_url or config.OLLAMA_BASE_URL,
        recorded_vector_digest=record["stored_vector_digest"] if record else None,
        recorded_model_digest=record["embedding"]["digest"] if record else None,
    )
    if not result.passed:
        for line in result.failures:
            print(f"[FAIL] {line}")
        print(
            f"\nThe index in Redis is not the {VERSION} corpus. Re-ingest it "
            f"(DATASET_VERSION={VERSION} make ingest) and check again."
        )
        return 1
    compared = (
        "and compared with the record" if record else "(no freeze record yet: measured)"
    )
    print(
        f"[PASS] the index is the {VERSION} corpus: {result.chunk_count} chunks; ids, texts, "
        f"vectors and the embedding model's digest checked {compared}"
    )
    return 0


# =================================================================================================
# freeze
# =================================================================================================
def load_report(path: Path) -> dict:
    if not path.is_file():
        raise Refusal(f"no gate report at {path.name}")
    try:
        return json.loads(path.read_text())
    except ValueError as e:
        raise Refusal(f"{path.name} is not JSON") from e


def run_problems(name: str, r: dict) -> list[str]:
    """Why one run's report cannot be frozen. The gate's own pass or fail is one reason among
    several: a pass on the wrong index, a dirty tree or a yellow reading is still not a freeze."""
    missing = [k for k in REQUIRED_REPORT_KEYS if k not in r]
    if "statistics" in r and not {"s5", "run_files", "pair_breakdown"} <= set(
        r["statistics"]
    ):
        missing.append("statistics.{s5,run_files,pair_breakdown}")
    if missing:
        return [
            f"{name}: the report lacks {', '.join(missing)} (written by an older gate?)"
        ]

    out = []
    if r["dataset"] != VERSION:
        out.append(
            f"{name}: the report is for dataset {r['dataset']!r}, not {VERSION!r}"
        )
    if not r["passed"]:
        out.append(f"{name}: the gate did not pass")
    if not r["snapshot_digest"]:
        out.append(f"{name}: the report has no snapshot digest")
    if not r["index_check"].get("passed"):
        out.append(f"{name}: the index check did not pass")
    g = r["grounding"]
    if g["ungrounded"] or g["own_chunk_missing"]:
        out.append(
            f"{name}: {g['ungrounded']} ungrounded and {g['own_chunk_missing']} own-chunk-missing "
            "query(ies) (S4)"
        )
    if not r["git"]["tree_clean"]:
        out.append(f"{name}: the code that measures was not a clean commit")
    readings = r["memory_pressure"]["readings"]
    not_green = [m for m in readings if not (type(m) is int and m == 0)]
    if not readings or not_green:
        out.append(
            f"{name}: memory pressure was not green, or could not be read, at {len(not_green)} of "
            f"{len(readings)} reading(s) (S3)"
        )
    raised = sorted(s for s, flag in r["statistics"]["s5"].items() if flag)
    if raised:
        out.append(
            f"{name}: S5 raised in {', '.join(raised)}: G2 is met by paraphrases only"
        )
    return out


def compare_runs(r1: dict, r2: dict) -> tuple[list[str], list[str]]:
    """`(problems, notes)`. Two runs of the same files and the same stack must agree on pass or fail
    and on the stack; they may differ in counts, which are recorded, and run 1 is the figure (S2)."""
    problems = []
    if [(c["name"], c["passed"]) for c in r1["criteria"]] != [
        (c["name"], c["passed"]) for c in r2["criteria"]
    ]:
        problems.append(
            "the two runs differ on pass or fail (S2): an /investigate, never a best of three"
        )
    for key in SAME_IN_BOTH_RUNS:
        if r1[key] != r2[key]:
            problems.append(f"the two runs differ in {key}")
    if r1["git"]["commit"] != r2["git"]["commit"]:
        problems.append("the two runs ran at different commits")

    s1, s2 = r1["statistics"], r2["statistics"]
    differing = sorted(k for k in set(s1) | set(s2) if s1.get(k) != s2.get(k))
    notes = (
        [f"statistics differ between the runs in: {', '.join(differing)}"]
        if differing
        else []
    )
    return problems, notes


def recompute_problems(p: Paths, r1: dict) -> list[str]:
    """Freeze recomputes the digests itself and does not trust the report's copy."""
    out = []
    for needed in (p.manifest, p.probe_flags):
        if not needed.is_file():
            out.append(f"{needed.name} is missing")
    try:
        digest, per_file = corpus_gate.snapshot_digest(
            corpus_gate.freeze_files(p.corpus_dir, p.workload)
        )
    except OSError:
        return [*out, "a file the snapshot digest covers cannot be read"]
    if digest != r1["snapshot_digest"]:
        out.append(
            "the files now hash to a different snapshot digest than run 1 reported"
        )
    if len(per_file) != len(r1["files"]):
        out.append(
            f"{len(per_file)} file(s) are covered now; run 1 covered {len(r1['files'])}"
        )
    chunk, count = corpus_gate.chunk_digest(p.corpus_dir, VERSION)
    if (chunk, count) != (r1["chunk_digest"], r1["chunk_count"]):
        out.append(
            "the corpus now chunks to a different chunk digest than run 1 reported"
        )
    return out


def _run_summary(r: dict) -> dict:
    readings = r["memory_pressure"]["readings"]
    return {
        "stage2_seconds": r["stage2_seconds"],
        "memory_readings": len(readings),
        "memory_max": max(readings),
        "query_vectors_vs_file": r.get("query_vectors_vs_file"),
    }


def build_record(
    p: Paths, r1: dict, r2: dict, notes: list[str], today: datetime.date
) -> dict:
    stats = r1["statistics"]
    return {
        "freeze_version": FREEZE_VERSION,
        "dataset_version": VERSION,
        "frozen_on": today.isoformat(),
        "git_commit": r1["git"]["commit"],
        "snapshot_digest": r1["snapshot_digest"],
        "file_count": len(r1["files"]),
        "chunk_digest": r1["chunk_digest"],
        "chunk_count": r1["chunk_count"],
        "stored_vector_digest": r1["stored_vector_digest"],
        "splitter": r1["splitter"],
        "embedding": r1["embedding"],
        "retrieval": r1["retrieval"],
        "packages": r1["packages"],
        "workload_manifest_sha256": build_pqa.sha256_file(p.manifest),
        "probe_flags_sha256": build_pqa.sha256_file(p.probe_flags),
        # The integers the gate printed. Never recomputed: Python's round() is half-to-even.
        "run_files": {
            name: {
                "k_distinct_queries": v["k_distinct_queries"],
                "cache_capacity": v["cache_capacity"],
            }
            for name, v in stats["run_files"].items()
        },
        "criteria": [
            {"name": c["name"], "passed": c["passed"], "summary": c["summary"]}
            for c in r1["criteria"]
        ],
        "grounding": r1["grounding"],
        "pair_breakdown": stats["pair_breakdown"],
        "statistics": {
            k: v for k, v in stats.items() if k not in ("run_files", "pair_breakdown")
        },
        "gate_run": {
            "run1": _run_summary(r1),
            "run2": _run_summary(r2),
            "comparison": notes,
        },
    }


def forbidden_content(record: dict) -> list[str]:
    """What must never reach the tracked record: an asin, a qa_id, an absolute path. Counts only."""
    strings: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                strings.append(str(k))
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            strings.append(node)

    walk(record)
    found = {
        "an asin": sum(bool(ASIN.search(s)) for s in strings),
        "a qa_id": sum(bool(QA_ID.search(s)) for s in strings),
        "an absolute path": sum(s.startswith("/") or "/Users/" in s for s in strings),
    }
    return [
        f"{n} string(s) in the record look like {what}"
        for what, n in found.items()
        if n
    ]


def cmd_freeze(
    p: Paths, run1: Path, run2: Path, today: datetime.date | None = None
) -> int:
    r1, r2 = load_report(run1), load_report(run2)
    problems = []
    if p.record.exists():
        problems.append(f"{p.record.name} exists: v1 is already frozen")
    problems += run_problems("run 1", r1) + run_problems("run 2", r2)
    notes: list[str] = []
    if not problems:  # compare and recompute only reports that are whole
        compared, notes = compare_runs(r1, r2)
        problems += compared + recompute_problems(p, r1)
    if problems:
        raise Refusal(*problems)

    record = build_record(
        p,
        r1,
        r2,
        notes,
        today or datetime.datetime.now(datetime.timezone.utc).astimezone().date(),
    )
    leaks = forbidden_content(record)
    if leaks:
        raise Refusal(*leaks)
    with p.record.open("x") as f:  # "x": written once
        f.write(json.dumps(record, indent=2) + "\n")

    print(f"froze {VERSION}: {p.record.name} written")
    print(
        f"  snapshot digest : {record['snapshot_digest']}  ({record['file_count']} files)"
    )
    print(
        f"  chunk digest    : {record['chunk_digest']}  ({record['chunk_count']} chunks)"
    )
    for name, v in record["run_files"].items():
        print(
            f"  {name:<10} K={v['k_distinct_queries']:<5} capacity={v['cache_capacity']}"
        )
    for note in notes:
        print(f"  note: {note} (run 1 is the figure)")
    return 0


# =================================================================================================
# verify
# =================================================================================================
def current_retrieval_config() -> dict:
    """The retrieval settings as the code declares them, with no Redis: Redis holds dev-v0 once
    this item is done."""
    from rag import config, store

    field = store.build_schema().fields["vector"]
    return {
        "top_k": config.TOP_K,
        "index": field.attrs.algorithm.value,
        "metric": field.attrs.distance_metric.value,
        "dim": field.attrs.dims,
        "data_type": field.attrs.datatype.value,
    }


def current_splitter() -> dict:
    from rag import config

    return {"chunk_size": config.CHUNK_SIZE, "chunk_overlap": config.CHUNK_OVERLAP}


def _first_differing_file(p: Paths, per_file: list[tuple[str, str]]) -> str | None:
    if not p.files_from.is_file():
        return None
    try:
        listed = {
            f["path"]: f["sha256"]
            for f in json.loads(p.files_from.read_text())["files"]
        }
    except (ValueError, KeyError):
        return None
    now = dict(per_file)
    return next(
        (
            rel
            for rel in sorted(set(listed) | set(now))
            if listed.get(rel) != now.get(rel)
        ),
        None,
    )


def cmd_verify(p: Paths, ollama_get=None, base_url: str | None = None) -> int:
    """Do the frozen files, the chunking, the embedding model and the retrieval config still match?

    A missing file is a failure, never a skip. A package-version change fails only if the chunk
    digest also moved; on its own it warns, because the digest is what the version could change.
    """
    import httpx

    from rag import config

    record = _load_record(p)
    if record is None:
        print(f"[FAIL] no freeze record at {p.record.name}")
        return 1
    ollama_get = ollama_get or corpus_gate.ollama_get
    base_url = base_url or config.OLLAMA_BASE_URL
    failures: list[str] = []
    warnings: list[str] = []

    # 1. the files
    try:
        digest, per_file = corpus_gate.snapshot_digest(
            corpus_gate.freeze_files(p.corpus_dir, p.workload)
        )
    except OSError:
        digest, per_file = "", []
        failures.append("a file the snapshot digest covers cannot be read (missing?)")
    if digest and (
        digest != record["snapshot_digest"] or len(per_file) != record["file_count"]
    ):
        named = _first_differing_file(p, per_file)
        failures.append(
            f"the files no longer hash to the recorded snapshot digest ({len(per_file)} file(s) now, "
            f"{record['file_count']} recorded)"
            + (f"; first difference: {named}" if named else "")
        )

    # 2. the chunks
    try:
        chunk, count = corpus_gate.chunk_digest(p.corpus_dir, VERSION)
    except (OSError, ValueError, KeyError) as e:
        chunk, count = "", 0
        failures.append(f"the corpus cannot be chunked ({type(e).__name__})")
    chunk_moved = bool(chunk) and (chunk, count) != (
        record["chunk_digest"],
        record["chunk_count"],
    )
    if chunk_moved:
        failures.append(
            "the corpus now chunks to a different chunk digest than the record"
        )

    # 3. the workload's manifest and the probe flags
    for label, path, key in (
        ("the workload manifest", p.manifest, "workload_manifest_sha256"),
        ("the probe-flag file", p.probe_flags, "probe_flags_sha256"),
    ):
        if not path.is_file():
            failures.append(f"{label} is missing")
        elif build_pqa.sha256_file(path) != record[key]:
            failures.append(f"{label} differs from the record")

    # 4. the embedding model
    try:
        models = ollama_get(base_url, "/api/tags")["models"]
        version = ollama_get(base_url, "/api/version")["version"]
    except (httpx.HTTPError, KeyError, ValueError) as e:
        failures.append(f"Ollama did not answer properly ({type(e).__name__})")
    else:
        model_failures, _ = corpus_gate.verify_model(
            models, record["embedding"]["tag"], record["embedding"]["digest"]
        )
        failures += [f.replace("test 5: ", "") for f in model_failures]
        if version != record["embedding"]["ollama_version"]:
            warnings.append(
                f"Ollama is {version}; the record was taken on {record['embedding']['ollama_version']}"
            )

    # 5. the retrieval config and the splitter
    if current_retrieval_config() != record["retrieval"]:
        failures.append("the retrieval config differs from the record")
    if current_splitter() != record["splitter"]:
        failures.append("the chunk size or overlap differs from the record")

    # 6. the packages
    now = corpus_gate.package_versions(tuple(record["packages"]))
    changed = sorted(k for k, v in record["packages"].items() if now.get(k) != v)
    if changed and chunk_moved:
        failures.append(
            f"package version(s) changed ({', '.join(changed)}) and the chunks moved with them"
        )
    elif changed:
        warnings.append(
            f"package version(s) changed ({', '.join(changed)}); the chunk digest did not move"
        )

    for line in warnings:
        print(f"[WARN] {line}")
    for line in failures:
        print(f"[FAIL] {line}")
    if failures:
        return 1
    print(
        f"[PASS] {VERSION} still matches {p.record.name}: {record['file_count']} files, "
        f"{record['chunk_count']} chunks, the embedding model and the retrieval config"
    )
    return 0


# =================================================================================================
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("assemble", help="data/v1/ from the drafts and the policy documents")
    sub.add_parser("check-index", help="is the index in Redis the corpus on disk?")
    freeze = sub.add_parser(
        "freeze", help="write data/v1-freeze.json from two passing gate runs"
    )
    freeze.add_argument("--run1", type=Path, required=True, help="run 1's gate report")
    freeze.add_argument("--run2", type=Path, required=True, help="run 2's gate report")
    freeze.add_argument(
        "--probe-flags", type=Path, help="the per-probe flag file (gitignored)"
    )
    verify = sub.add_parser(
        "verify", help="do the files, chunks, model and config still match?"
    )
    verify.add_argument(
        "--files-from", type=Path, help="run 1's report, to name a changed file"
    )
    args = ap.parse_args(argv)

    p = default_paths()
    overrides = {}
    if getattr(args, "probe_flags", None):
        overrides["probe_flags"] = args.probe_flags
    if getattr(args, "files_from", None):
        overrides["files_from"] = args.files_from
    if overrides:
        p = Paths(**{**p.__dict__, **overrides})

    try:
        if args.command == "assemble":
            return cmd_assemble(p)
        if args.command == "check-index":
            return cmd_check_index(p)
        if args.command == "freeze":
            return cmd_freeze(p, args.run1, args.run2)
        return cmd_verify(p)
    except Refusal as e:
        print("REFUSED — nothing was written:", file=sys.stderr)
        for line in e.lines:
            print(f"  {line}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
