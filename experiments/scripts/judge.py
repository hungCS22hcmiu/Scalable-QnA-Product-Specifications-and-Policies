"""Item 5.1: the offline judge harness (docs/work/2026-10-30-judge-harness/design.md, section 3).

    make judge RUN_ID=<id>                 judge every served answer of a finished run (loads the judge)
    make judge-sanity FILE=<sanity.jsonl>  12 hand-made pairs; any wrong verdict stops the work

`run` reads only the run's `raw/`, its `manifest.yaml`, the reference set and the frozen judge
(`experiments/judge/judge-v1.json` and its prompt). It judges each distinct verdict key once, gives every
record the verdict of its key, splits each `INCORRECT` record by error layer, and writes
`results/{run_id}/judge/` beside `raw/`, never inside it. It refuses, before any judge call, when the
manifest and the reference set disagree, when the reference set was not written by the pinned reference
writer (`reference-writer-v1.json`, ADR-023), when the run is not admissible or has `mutation: on`, when
the live judge or the prompt differs from the pre-registered one, when the generator is loaded, and when
the output exists.

The verdict key (interfaces.md section H, v0.28):

    verdict_key = sha256("vk1:" + ns(query_raw) + ns(product_id) + ns(answer_sha256))
    ns(s)       = <byte length of s in UTF-8, decimal> ":" <the UTF-8 bytes of s> ","

Output holds question text and PQA-grounded answers, so `judge/` is gitignored. Messages here name a
record by `request_id` and never quote text.

Exit codes: 0 done; 1 a rule refused, a check failed, or a sanity verdict was wrong.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import corpus_gate
import judge_references as refs
import run_manifest
import yaml

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR") or ROOT / "experiments" / "results")
JUDGE_CFG = ROOT / "experiments" / "judge" / "judge-v1.json"
WRITER_CFG = refs.WRITER_PATH  # reference-writer-v1.json (ADR-023)
PREREGISTRATION = ROOT / "docs" / "preregistration.md"

VERDICTS = ("CORRECT", "INCORRECT", "UNPARSED")
HITS = ("TIER1_HIT", "TIER2_HIT")
LAYERS = ("retrieval", "generation", "inherited", "reuse", "undecided")
SEPARATOR = "#chunk-"
UNPARSED_LIMIT = 0.02  # a run with more UNPARSED verdict keys than this reports no rates (counting-v1)
REJUDGE_N = 30
REJUDGE_SEED = 7
PRESSURE_STOP = 4  # macOS critical (CLAUDE.md, ADR-014)
PRESSURE_EVERY = 50
PROGRESS_EVERY = 25
SHA256_NAME = re.compile(r"^[0-9a-f]{64}$")
WORKLOAD_SPLIT = re.compile(r"workload-v1-(validation|test)\.json$")

# A call into Ollama: (path, body or None) -> the JSON reply. A GET when body is None.
Ollama = Callable[[str, dict | None], dict]


class JudgeRefused(RuntimeError):
    """A rule stopped the judge. The message says which; nothing was judged for it."""


# =================================================================================================
# The pure half: key, parse, answers, join, layers
# =================================================================================================
def _netstring(s: str) -> bytes:
    raw = s.encode("utf-8")
    return str(len(raw)).encode("ascii") + b":" + raw + b","


def verdict_key(query_raw: str, product_id: str, answer_sha256: str) -> str:
    """The key a verdict is stored under (interfaces.md section H, v0.28), lowercase hex.

    Netstrings cannot be split two ways, so no question text can fake a field boundary. `query_raw` is the
    record's field as logged. `product_id` is `""` when the record has none.
    """
    return hashlib.sha256(
        b"vk1:"
        + _netstring(query_raw)
        + _netstring(product_id)
        + _netstring(answer_sha256)
    ).hexdigest()


def parse_verdict(reply: str) -> str:
    """`CORRECT` or `INCORRECT` when the reply, trimmed at both ends, is exactly that word; else
    `UNPARSED`. No case folding, no substring search (`INCORRECT` contains `CORRECT`), no stripping of
    a full stop."""
    word = reply.strip()
    return word if word in ("CORRECT", "INCORRECT") else "UNPARSED"


def load_answers(run_dir: Path, records: list[dict]) -> dict[str, str]:
    """`answer_sha256 -> text` for every answer the records name, each file checked against its name
    (interfaces.md section H, answer-store rule 1). A missing file or a hash that differs raises."""
    answers: dict[str, str] = {}
    for r in records:
        sha = r.get("answer_sha256") or ""
        if not sha or sha in answers:
            continue
        if not SHA256_NAME.match(sha):
            raise JudgeRefused(
                f"{r.get('request_id')}: answer_sha256 is not 64 lowercase hex"
            )
        path = Path(run_dir) / "raw" / "answers" / f"{sha}.txt"
        try:
            data = path.read_bytes()
        except OSError:
            raise JudgeRefused(f"answers/{sha}.txt is missing") from None
        if hashlib.sha256(data).hexdigest() != sha:
            raise JudgeRefused(f"answers/{sha}.txt does not hash to its name")
        try:
            answers[sha] = data.decode("utf-8")
        except UnicodeDecodeError:
            raise JudgeRefused(f"answers/{sha}.txt is not UTF-8") from None
    return answers


def join(records: list[dict], index: list[dict]) -> dict[str, dict]:
    """`request_id -> reference row`, by the exact `(query_raw, product_id or "")`.

    Raises on a record that matches no reference, and on a request_id that repeats: a loose join would
    hand a record another query's reference and a plausible wrong verdict.
    """
    by_pair = {(row["question"], row.get("product_id") or ""): row for row in index}
    joined: dict[str, dict] = {}
    for r in records:
        request_id = r.get("request_id")
        if request_id in joined:
            raise JudgeRefused(f"request_id {request_id} appears twice")
        row = by_pair.get((r.get("query_raw"), r.get("product_id") or ""))
        if row is None:
            raise JudgeRefused(
                f"{request_id}: no workload (question, product_id) matches this record"
            )
        joined[request_id] = row
    return joined


def _doc_of(chunk_id: str) -> str:
    return chunk_id.rpartition(SEPARATOR)[0]


def retrieval_miss(retrieved: list[str] | None, gold_doc_ids: list[str]) -> bool | None:
    """Rule 1 of the layer table. `None` when the record has no retrieval (`retrieved` is null, as on a
    TIER1_HIT). Otherwise true when a gold `product-` document has no chunk in `retrieved`, or a gold
    `policy-` document is not the document of the first `policy-` chunk (none counts as not).

    The first `policy-` chunk is the POLICY lane's namespace document, so no lane rule is copied here.
    """
    if retrieved is None:
        return None
    docs = [_doc_of(c) for c in retrieved]
    first_policy = next((d for d in docs if d.startswith("policy-")), None)
    for gold in gold_doc_ids:
        if gold.startswith("product-") and gold not in docs:
            return True
        if gold.startswith("policy-") and gold != first_policy:
            return True
    return False


def layer(
    record: dict, verdict: str | None, entry_verdict: str | None, miss: bool | None
) -> str | None:
    """The error layer of a record, first match wins (design.md section 3). `None` unless `verdict` is
    `INCORRECT`.

    1 `retrieval`: `miss` is true. 2 `generation`: a MISS. 3 `inherited`: a hit whose entry's MISS was
    `INCORRECT`. 4 `reuse`: a hit whose entry's MISS was `CORRECT`. `undecided`: a hit whose entry's MISS
    is `UNPARSED` or not in the run; it is counted beside the layers and never in one.
    """
    if verdict != "INCORRECT":
        return None
    if miss:
        return "retrieval"
    cache = record.get("cache")
    if cache == "MISS":
        return "generation"
    if cache not in HITS:
        raise JudgeRefused(
            f"{record.get('request_id')}: cache {cache!r} carries a verdict"
        )
    if entry_verdict == "INCORRECT":
        return "inherited"
    if entry_verdict == "CORRECT":
        return "reuse"
    return "undecided"


def entry_misses(records: list[dict]) -> dict[str, dict]:
    """`entry_id -> the MISS record that wrote the entry`: the leader (no `coalesced` key) when there is
    one, else the first MISS in the file. A coalesced follower shares its leader's entry and answer."""
    found: dict[str, dict] = {}
    for r in records:
        entry = r.get("entry_id")
        if r.get("cache") != "MISS" or not entry:
            continue
        held = found.get(entry)
        if held is None or ("coalesced" in held and "coalesced" not in r):
            found[entry] = r
    return found


# =================================================================================================
# Ollama: the frozen judge, preflight, one call
# =================================================================================================
def load_judge(path: Path = JUDGE_CFG) -> dict:
    """`judge-v1.json` as a dict, with three values read from the files: `cfg_sha256` (the file's hash,
    which the pre-registration holds), `prompt_text` and `prompt_file_sha256`."""
    path = Path(path)
    raw = path.read_bytes()
    cfg = json.loads(raw)
    prompt = (path.parent / cfg["prompt_file"]).read_bytes()
    return {
        **cfg,
        "cfg_sha256": hashlib.sha256(raw).hexdigest(),
        "prompt_text": prompt.decode("utf-8"),
        "prompt_file_sha256": hashlib.sha256(prompt).hexdigest(),
    }


def judge_problems(
    cfg: dict, prereg_text: str, ollama: Ollama, generator_model: str | None
) -> list[str]:
    """What stops a judge call, whether or not a run is involved: the live digest or the prompt file
    differs from `judge-v1.json`, the pre-registration does not hold that file's hash, the model is not
    pulled, or the generator is loaded."""
    problems: list[str] = []
    live = {m["name"]: m["digest"] for m in ollama("/api/tags", None).get("models", [])}
    if cfg["model"] not in live:
        problems.append(f"the judge {cfg['model']} is not in /api/tags")
    elif live[cfg["model"]] != cfg["digest"]:
        problems.append(
            f"the live digest of {cfg['model']} is {live[cfg['model']][:12]}..., "
            f"judge-v1.json has {cfg['digest'][:12]}..."
        )
    if cfg["prompt_file_sha256"] != cfg["prompt_sha256"]:
        problems.append("the prompt file's hash is not the one in judge-v1.json")
    if cfg["cfg_sha256"] not in prereg_text:
        problems.append("preregistration.md does not hold the sha256 of judge-v1.json")
    if generator_model:
        loaded = [m["name"] for m in ollama("/api/ps", None).get("models", [])]
        if generator_model in loaded:
            problems.append(
                f"the generator {generator_model} is loaded; unload it first"
            )
    return problems


def preflight(
    manifest: dict,
    ref_version: dict,
    judge_cfg: dict,
    prereg_text: str,
    ollama: Ollama,
    *,
    manifest_problems: list[str] | tuple[str, ...] = (),
    out_dir: Path | None = None,
    writer_cfg: dict | None = None,
) -> list[str]:
    """Every reason not to start, as messages. An empty list means the run may be judged.

    Refuses when the manifest check fails (`manifest_problems`), the manifest says `admissible: false`,
    or the run has `mutation: on`; when the manifest and the reference set differ on the corpus digest,
    `retrieval_version`, the retrieval source hash, `top_k` or one of the six generator fields (its
    prompt hash, `prompt_sha256`, included); when the reference set has no `reference_writer`, or its
    `model`, `digest`, `options`, `think` or `prompt_sha256` differs from `writer_cfg` (ADR-023; by
    default `reference-writer-v1.json`); when `judge_problems` finds one; and when the output folder (or
    its `.partial`) exists.
    """
    problems = [f"manifest check: {p}" for p in manifest_problems]
    if (manifest.get("admissibility") or {}).get("admissible") is not True:
        problems.append("the manifest does not say admissible: true")
    mutation = (manifest.get("arms") or {}).get("mutation")
    if mutation != "off":
        problems.append(
            f"the run has mutation: {mutation}; only mutation: off is judged here"
        )

    # One line per section, so the compared fields can be read (and grepped) at a glance.
    # fmt: off
    version_fields = (
        ("corpus", ("snapshot_digest",)),
        ("retrieval", ("retrieval_version", "retrieve_py_sha256", "top_k")),
        ("generator", ("model", "digest", "num_ctx", "think", "temperature", "prompt_sha256")),
    )
    # fmt: on
    for section, keys in version_fields:
        have = manifest.get(section) or {}
        want = ref_version.get(section) or {}
        for key in keys:
            if key not in have or key not in want or have[key] != want[key]:
                problems.append(
                    f"{section}.{key}: the manifest has {have.get(key)!r}, "
                    f"the reference set has {want.get(key)!r}"
                )

    # The reference writer is not in the manifest: the reference set is compared with its pinned file.
    writer = refs.load_writer() if writer_cfg is None else writer_cfg
    made_by = ref_version.get("reference_writer") or {}
    if not made_by:
        problems.append(
            "reference_writer: the reference set has no reference_writer block"
        )
    else:
        for key in ("model", "digest", "options", "think", "prompt_sha256"):
            if key not in made_by or key not in writer or made_by[key] != writer[key]:
                problems.append(
                    f"reference_writer.{key}: the reference set has {made_by.get(key)!r}, "
                    f"reference-writer-v1.json has {writer.get(key)!r}"
                )

    generator = (manifest.get("generator") or {}).get("model")
    problems += judge_problems(judge_cfg, prereg_text, ollama, generator)
    if out_dir is not None:
        for folder in (
            Path(out_dir),
            Path(out_dir).with_name(Path(out_dir).name + ".partial"),
        ):
            if folder.exists():
                problems.append(f"{folder} exists; judge output is never overwritten")
    return problems


def ask_judge(
    question: str, reference: str, answer: str, cfg: dict, post: Ollama
) -> tuple[str, float]:
    """One `/api/generate` call with `stream: false`. Returns the reply and the seconds it took.

    `think: false` is sent only when the run found that the model lists `thinking` (`cfg["send_think"]`).
    """
    body = {
        "model": cfg["model"],
        "prompt": cfg["prompt_text"].format(
            question=question, reference=reference, answer=answer
        ),
        "stream": False,
        "options": cfg["options"],
    }
    if cfg.get("send_think"):
        body["think"] = False
    start = time.monotonic()
    reply = post("/api/generate", body)
    return reply["response"], time.monotonic() - start


def _percentile(sorted_values: list[float], q: float) -> float:
    """Nearest-rank percentile of an already sorted list."""
    return sorted_values[max(0, math.ceil(q * len(sorted_values)) - 1)]


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()
    ]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    Path(path).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    )


def _check_pressure(
    pressure: Callable[[], int | None], readings: list, log, when: str
) -> None:
    level = pressure()
    readings.append(level)
    log(f"  memory pressure level: {level} ({when}; 1 green, 2 warn, 4 critical)")
    if level == PRESSURE_STOP:
        raise JudgeRefused(f"memory pressure is critical (4) {when}")


# =================================================================================================
# run
# =================================================================================================
def run(
    run_id: str,
    *,
    results_dir: Path = RESULTS_DIR,
    refs_root: Path = refs.REFERENCES_DIR,
    judge_path: Path = JUDGE_CFG,
    writer_path: Path = WRITER_CFG,
    prereg_path: Path = PREREGISTRATION,
    ollama: Ollama,
    pressure: Callable[[], int | None] = corpus_gate.memory_pressure_level,
    log: Callable[[str], None] = print,
) -> dict:
    """Judge a finished run. Writes `results/{run_id}/judge/` and returns its summary.

    Everything that can refuse does so before the first judge call. The output goes to `judge.partial/`
    (one row per verdict key, flushed as it is made) and is renamed to `judge/` after the last step.
    """
    started = time.monotonic()
    run_dir = Path(results_dir) / run_id
    out_dir = run_dir / "judge"
    partial = out_dir.with_name("judge.partial")

    manifest_path = run_dir / "manifest.yaml"
    if not manifest_path.is_file():
        raise JudgeRefused(f"no manifest.yaml in {run_dir}")
    manifest = yaml.safe_load(manifest_path.read_text())
    split = WORKLOAD_SPLIT.search(str((manifest.get("workload") or {}).get("file", "")))
    if split is None:
        raise JudgeRefused("the manifest's workload file is not a v1 split file")
    refs_dir = Path(refs_root) / split.group(1)
    try:
        ref_version = json.loads((refs_dir / "version.json").read_text())
        index_bytes = (refs_dir / "index.jsonl").read_bytes()
        prereg_text = Path(prereg_path).read_text()
        writer = refs.load_writer(writer_path)
    except OSError as e:
        raise JudgeRefused(f"cannot read {e.filename}: {e.strerror}") from None
    index = [
        json.loads(line)
        for line in index_bytes.decode("utf-8").splitlines()
        if line.strip()
    ]
    cfg = load_judge(judge_path)

    problems = preflight(
        manifest,
        ref_version,
        cfg,
        prereg_text,
        ollama,
        manifest_problems=run_manifest.check_manifest(run_dir),
        out_dir=out_dir,
        writer_cfg=writer,
    )
    if problems:
        raise JudgeRefused("; ".join(problems))

    readings: list = []
    _check_pressure(pressure, readings, log, "before the first verdict")
    show = ollama("/api/show", {"model": cfg["model"]})
    cfg = {**cfg, "send_think": "thinking" in (show.get("capabilities") or [])}

    records = run_manifest.read_records(run_dir)
    answers = load_answers(run_dir, records)
    joined = join(records, index)

    # One judge call per distinct key, in the order the keys first appear.
    todo: dict[str, dict] = {}
    key_of: dict[str, str | None] = {}
    for r in records:
        sha = r.get("answer_sha256") or ""
        if not sha:
            key_of[r["request_id"]] = None
            continue
        key = verdict_key(r["query_raw"], r.get("product_id") or "", sha)
        key_of[r["request_id"]] = key
        if key not in todo:
            ref = joined[r["request_id"]]
            reference_text = (
                refs_dir / "answers" / f"{ref['reference_sha256']}.txt"
            ).read_text()
            todo[key] = {
                "question": r["query_raw"],
                "reference": reference_text,
                "reference_sha256": ref["reference_sha256"],
                "answer": answers[sha],
            }

    partial.mkdir(parents=True)
    verdicts: dict[str, dict] = {}
    seconds: list[float] = []
    with open(partial / "verdicts.jsonl", "w") as f:
        for i, (key, item) in enumerate(todo.items(), 1):
            reply, took = ask_judge(
                item["question"], item["reference"], item["answer"], cfg, ollama
            )
            row = {
                "verdict_key": key,
                "verdict": parse_verdict(reply),
                "reply": reply,
                "seconds": took,
                "reference_sha256": item["reference_sha256"],
            }
            verdicts[key] = row
            seconds.append(took)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            if i % PROGRESS_EVERY == 0 or i == len(todo):
                log(f"  {i}/{len(todo)} verdict keys judged")
            if i % PRESSURE_EVERY == 0:
                _check_pressure(pressure, readings, log, f"after {i} verdict keys")

    # The judge at temperature 0 with a seed should repeat itself. 30 keys are asked again to show it.
    again = random.Random(REJUDGE_SEED).sample(list(todo), min(REJUDGE_N, len(todo)))
    flips = []
    for key in again:
        item = todo[key]
        reply, _ = ask_judge(
            item["question"], item["reference"], item["answer"], cfg, ollama
        )
        if parse_verdict(reply) != verdicts[key]["verdict"]:
            flips.append(key)

    miss_of = entry_misses(records)
    rows = []
    for r in records:
        ref = joined[r["request_id"]]
        key = key_of[r["request_id"]]
        verdict = verdicts[key]["verdict"] if key else None
        entry_miss = miss_of.get(r.get("entry_id")) if r.get("cache") in HITS else None
        entry_key = key_of[entry_miss["request_id"]] if entry_miss else None
        entry_verdict = verdicts[entry_key]["verdict"] if entry_key else None
        miss = retrieval_miss(r.get("retrieved_chunk_ids"), ref["gold_doc_ids"])
        rows.append(
            {
                "request_id": r["request_id"],
                "cache": r.get("cache"),
                "qa_id": ref["qa_id"],
                "stratum": ref["stratum"],
                "answerable": ref["answerable"],
                "verdict_key": key,
                "verdict": verdict,
                "layer": layer(r, verdict, entry_verdict, miss),
                "retrieval_miss": miss,
                "gold_doc_ids": ref["gold_doc_ids"],
                "retrieved_chunk_ids": r.get("retrieved_chunk_ids"),
                "entry_sources": r.get("entry_sources"),
                "candidate_sources": r.get("candidate_sources"),
                "entry_miss_request_id": entry_miss["request_id"]
                if entry_miss
                else None,
                "reference_sha256": ref["reference_sha256"],
                "reference_version": hashlib.sha256(index_bytes).hexdigest(),
                "manifest_sha256": hashlib.sha256(
                    manifest_path.read_bytes()
                ).hexdigest(),
                "judge_version": cfg["version"],
            }
        )
    _write_jsonl(partial / "records.jsonl", rows)

    counted = Counter(v["verdict"] for v in verdicts.values())
    ordered = sorted(seconds)
    unparsed_share = counted["UNPARSED"] / len(verdicts) if verdicts else 0.0
    summary = {
        "run_id": run_id,
        "judge_version": cfg["version"],
        "reference_set_sha256": hashlib.sha256(index_bytes).hexdigest(),
        "records": {
            "total": len(records),
            "judged": sum(1 for row in rows if row["verdict"] is not None),
            "by_cache": dict(sorted(Counter(r.get("cache") for r in records).items())),
            "judged_by_cache": dict(
                sorted(
                    Counter(
                        row["cache"] for row in rows if row["verdict"] is not None
                    ).items()
                )
            ),
        },
        "verdict_keys": len(verdicts),
        "verdicts": {v: counted[v] for v in VERDICTS},
        "unparsed_share": unparsed_share,
        "rates_reportable": unparsed_share <= UNPARSED_LIMIT,
        "layers": {
            name: sum(1 for row in rows if row["layer"] == name) for name in LAYERS
        },
        "seconds_per_verdict": {
            "median": statistics.median(ordered) if ordered else None,
            "p95": _percentile(ordered, 0.95) if ordered else None,
            "total": sum(ordered),
        },
        "wall_seconds": time.monotonic() - started,
        "pressure_readings": readings,
        "rejudge": {"keys": len(again), "flips": len(flips), "flipped_keys": flips},
    }
    (partial / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    partial.rename(out_dir)
    log(
        f"  wrote {out_dir}: {len(rows)} records, {len(verdicts)} verdict keys, {dict(counted)}"
    )
    if not summary["rates_reportable"]:
        log(
            f"  STOP: UNPARSED is {unparsed_share:.1%} of verdict keys, over {UNPARSED_LIMIT:.0%}"
        )
    return summary


# =================================================================================================
# sanity
# =================================================================================================
def sanity(
    file: Path,
    *,
    refs_dir: Path = refs.REFERENCES_DIR / "validation",
    judge_path: Path = JUDGE_CFG,
    prereg_path: Path = PREREGISTRATION,
    generator_model: str | None = None,
    ollama: Ollama,
    pressure: Callable[[], int | None] = corpus_gate.memory_pressure_level,
    log: Callable[[str], None] = print,
) -> int:
    """Judge hand-made pairs. Each row of `file` is `qa_id`, an authored `answer` and an `expected`
    verdict (and a `kind`). Returns 0 only when every verdict is the expected one and none is
    `UNPARSED`. The judge is checked as `run` checks it: digest, prompt, pre-registration, generator
    unloaded."""
    cfg = load_judge(judge_path)
    problems = judge_problems(
        cfg, Path(prereg_path).read_text(), ollama, generator_model
    )
    if problems:
        raise JudgeRefused("; ".join(problems))
    _check_pressure(pressure, [], log, "before the first verdict")
    show = ollama("/api/show", {"model": cfg["model"]})
    cfg = {**cfg, "send_think": "thinking" in (show.get("capabilities") or [])}

    refs_dir = Path(refs_dir)
    by_qa = {row["qa_id"]: row for row in _read_jsonl(refs_dir / "index.jsonl")}
    rows = _read_jsonl(Path(file))
    wrong = 0
    unparsed = 0
    for row in rows:
        ref = by_qa.get(row["qa_id"])
        if ref is None:
            raise JudgeRefused(f"{row['qa_id']} is not in the reference set")
        reference = (
            refs_dir / "answers" / f"{ref['reference_sha256']}.txt"
        ).read_text()
        reply, _ = ask_judge(ref["question"], reference, row["answer"], cfg, ollama)
        got = parse_verdict(reply)
        unparsed += got == "UNPARSED"
        ok = got == row["expected"]
        wrong += not ok
        log(
            f"  {'ok  ' if ok else 'WRONG'} {row.get('kind', '?'):<22} {row['qa_id']}: "
            f"expected {row['expected']}, got {got}"
        )
    log(f"  {len(rows) - wrong} of {len(rows)} correct, {unparsed} UNPARSED")
    return 0 if wrong == 0 else 1


# =================================================================================================
# Command line
# =================================================================================================
def make_ollama(base_url: str, timeout: float = 120.0) -> Ollama:
    base = base_url.rstrip("/")

    def call(path: str, body: dict | None = None) -> dict:
        return refs.http_json(base + path, body, timeout=timeout)

    return call


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="judge a finished run (loads the judge)")
    p_run.add_argument("--run-id", required=True)
    p_run.add_argument("--results-dir", type=Path, default=RESULTS_DIR)

    p_san = sub.add_parser(
        "sanity", help="judge hand-made pairs; any wrong verdict exits 1"
    )
    p_san.add_argument("--file", type=Path, required=True)
    p_san.add_argument("--split", choices=refs.BUILD_SPLITS, default="validation")

    args = ap.parse_args(argv)
    from rag import config

    ollama = make_ollama(config.OLLAMA_BASE_URL)
    try:
        if args.command == "run":
            run(args.run_id, results_dir=args.results_dir, ollama=ollama)
            return 0
        return sanity(
            args.file,
            refs_dir=refs.REFERENCES_DIR / args.split,
            generator_model=config.LLM_MODEL,
            ollama=ollama,
        )
    except (JudgeRefused, run_manifest.ManifestError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
