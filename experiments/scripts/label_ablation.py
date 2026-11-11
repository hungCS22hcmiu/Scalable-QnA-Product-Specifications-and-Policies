"""Item 5.2: the labelling ablation (docs/work/2026-11-11-labelling-ablation/design.md, section 3).

How far can the frozen judge (`judge-v1`, ADR-022) be trusted, and does its reference make a label depend on
overlap? About 100 served answers of the judge cost run are labelled once by the author, from the question and
the gold source documents, without the reference. The judge's labels (`judge-v1`, made with the reference) are
compared with the author's. A reference-free judge (`judge-rf-v1`: `judge-v1` with only its prompt changed, the
gold evidence in place of the reference) was planned as a second reference-free side. It failed its sanity
check, so it is used for no score and the author's labels are the reference-free side (pre-registration
Entry 6). Six commands, each behind a `make ablation-*` target (`rf` has none, see below):

    draw       RUN_ID   the sample: every hit of the frame, plus 21 MISS keys by seed. A second run re-draws
                        in memory and prints `identical`, or exits 1.
    rf-sanity  FILE     item 5.1's 12 sanity pairs through the reference-free judge (loads the judge)
    sheet      RUN_ID   the author's blind sheet and `items.jsonl` (item number -> verdict key)
    rf         RUN_ID   retired by Entry 6: prints REFUSED and exits 1 before any Ollama call. `rf_run` stays,
                        with its tests, so the failure can be reproduced
    lock       RUN_ID   reads the author's labels, writes `labels.jsonl` with the sheet's sha256, then the
                        second sheet (the reference, for the decided disagreements with `judge-v1`)
    score      RUN_ID   re-hashes the first sheet, reads the second, writes `refcheck.jsonl` and
                        `scores.json`, and prints the tables. It reads no reference-free file.

The two sheets hold question text and PQA-grounded text, so they stay under a gitignored path. Every file under
`results/<run>/ablation/` holds IDs, verdicts, labels and counts only. Messages here name a key by its prefix,
never by text. Every writer refuses when its output exists. Each output carries `written_at` (UTC), so the
score step can show that pre-registration Entry 5 came first, and Entry 6 before the sheet.

Exit codes: 0 done; 1 a rule refused, a check failed, a sanity verdict was wrong, or `draw` found a difference.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import random
import re
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import corpus_gate
import judge
import judge_references as refs
import run_manifest
import select_pqa
import yaml

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = judge.RESULTS_DIR
JUDGE_CFG = judge.JUDGE_CFG
RF_CFG = ROOT / "experiments" / "judge" / "judge-rf-v1.json"
PREREGISTRATION = judge.PREREGISTRATION
TRAIL = ROOT / "docs" / "work" / "2026-11-11-labelling-ablation"
SHEET_PATH = TRAIL / "evidence" / "private" / "sheet.md"
REFSHEET_PATH = TRAIL / "evidence" / "private" / "refsheet.md"

SEED = 20261111  # Entry 5: the MISS draw; the sheet's order reuses it
N_MISS = 21
SOURCE_JUDGE = "judge-v1"
RF_VERSION = "judge-rf-v1"
FRAME_CACHES = ("MISS", "TIER2_HIT")
HIT_BUCKETS = ("1.0", "[0.8, 1)", "[0.6, 0.8)", "below 0.6")
MISS_BUCKET = "generated"
LABEL_WORDS = ("correct", "incorrect", "unsure")
LABEL_TO_VERDICT = {"correct": "CORRECT", "incorrect": "INCORRECT", "unsure": "UNSURE"}
DECIDED = ("CORRECT", "INCORRECT")
STRATA = ("hit", "MISS")
UNPARSED_LIMIT = judge.UNPARSED_LIMIT
PRESSURE_EVERY = 25

ITEM = re.compile(r"^## Item (\d+)[ \t]*$", re.MULTILINE)
LABEL = re.compile(r"^label:[ \t]*(\S*)[ \t]*$", re.MULTILINE)
REFERENCE_RIGHT = refs.REFERENCE_RIGHT
ENTRY_5 = re.compile(
    r"^## Entry 5 — (\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})Z\b", re.MULTILINE
)
ENTRY_6 = re.compile(
    r"^## Entry 6 — (\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})Z\b", re.MULTILINE
)
RF_FAILED = "judge-rf-v1: failed its sanity check, used for no score (Entry 6)"
RF_RETIRED = "retired by Entry 6: judge-rf-v1 failed its sanity check"
WRITTEN_AT_LINE = re.compile(r"^written_at: (\S+)\s*$", re.MULTILINE)


class AblationRefused(RuntimeError):
    """A rule stopped the step. The message says which; nothing was written for it."""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _short(key: str) -> str:
    return key[:12]


# =================================================================================================
# The pure half: frame, draw, evidence, sheets, agreement
# =================================================================================================
def hit_bucket(overlap: float) -> str:
    """The bucket of a hit by its `source_overlap` (Entry 5): `1.0`, `[0.8, 1)`, `[0.6, 0.8)`, `below 0.6`."""
    if overlap >= 1.0:
        return "1.0"
    if overlap >= 0.8:
        return "[0.8, 1)"
    if overlap >= 0.6:
        return "[0.6, 0.8)"
    return "below 0.6"


def frame(
    records: list[dict], judge_records: list[dict]
) -> tuple[list[dict], dict[str, int]]:
    """The frame (Entry 5): the run's served records, one row per distinct verdict key, minus the records
    with no `product_id` (ADR-025 refuses them now) and minus the Tier-2 hits whose entry was written for
    another product (ADR-024 removed them). Returns the rows and the excluded counts by reason.

    A hit's entry is the MISS that wrote it (`judge.entry_misses`). Any record that is not a MISS or a
    Tier-2 hit, or that has no verdict key, stops the frame: this rule knows no other shape, and a quiet
    skip would shrink the frame with no sign.
    """
    judged = {r["request_id"]: r for r in judge_records}
    miss_of = judge.entry_misses(records)
    excluded = {"no_product_id": 0, "cross_product_hit": 0}
    rows: dict[str, dict] = {}
    for r in records:
        request_id = r.get("request_id")
        cache = r.get("cache")
        if cache not in FRAME_CACHES:
            raise AblationRefused(f"{request_id}: cache {cache!r} is not in the frame")
        product_id = r.get("product_id") or ""
        if not product_id:
            excluded["no_product_id"] += 1
            continue
        if cache == "TIER2_HIT":
            entry = miss_of.get(r.get("entry_id"))
            if entry is None:
                raise AblationRefused(f"{request_id}: a hit whose entry has no MISS")
            if (entry.get("product_id") or "") != product_id:
                excluded["cross_product_hit"] += 1
                continue
        verdict_row = judged.get(request_id)
        if verdict_row is None or not verdict_row.get("verdict_key"):
            raise AblationRefused(f"{request_id}: no verdict key in the judge records")
        key = verdict_row["verdict_key"]
        if key in rows:
            continue  # one row per distinct verdict key: the first record wins
        if cache == "TIER2_HIT":
            overlap = r.get("source_overlap")
            if overlap is None:
                raise AblationRefused(f"{request_id}: a hit with no source_overlap")
            overlap = float(overlap)
            stratum, bucket = "hit", hit_bucket(overlap)
        else:
            overlap, stratum, bucket = None, "MISS", MISS_BUCKET
        rows[key] = {
            "verdict_key": key,
            "request_id": request_id,
            "cache": cache,
            "stratum": stratum,
            "bucket": bucket,
            "source_overlap": overlap,
            "qa_id": verdict_row["qa_id"],
            "answerable": verdict_row["answerable"],
            "workload_stratum": verdict_row["stratum"],
        }
    return list(rows.values()), excluded


def draw(frame_rows: list[dict], n_miss: int, seed: int) -> list[dict]:
    """The sample (Entry 5): every hit of the frame (a census), and `n_miss` MISS rows chosen by
    `random.Random(seed).sample` from the MISS keys sorted by verdict key. Hits first, then MISSes, each
    sorted by verdict key, so two calls give the same list."""
    hits = sorted(
        (r for r in frame_rows if r["stratum"] == "hit"), key=lambda r: r["verdict_key"]
    )
    misses = {r["verdict_key"]: r for r in frame_rows if r["stratum"] == "MISS"}
    if n_miss > len(misses):
        raise AblationRefused(
            f"asked for {n_miss} MISS keys, the frame has {len(misses)}"
        )
    picked = random.Random(seed).sample(sorted(misses), n_miss)
    return hits + [misses[k] for k in sorted(picked)]


def evidence(index_row: dict, texts: dict[str, str]) -> str:
    """A key's evidence (Entry 5): the texts of the reference index's `chunk_ids`, in that order, joined by
    a blank line as `generate` joins its context. It is the text the key's reference was written from."""
    return "\n\n".join(texts[c] for c in index_row["chunk_ids"])


RUBRIC_HEADER = [
    "For each item, read the question, the product and the documents, then the answer to check.",
    "Write one word after `label:` at the end of the item: `correct`, `incorrect` or `unsure`.",
    "Leave nothing else on that line. This is the rubric the judge uses:",
    "",
    "- CORRECT: everything the answer says agrees with the documents. More or fewer details are fine",
    "  if nothing it says differs.",
    "- INCORRECT: it states a different number, time, condition or fact; it is about a different product",
    '  or a different policy; or it says "yes" where the documents say "no", or the reverse.',
    '- A bare "Yes." or "No." is CORRECT when the documents give the same yes or no.',
    "- If the documents do not answer the question, the answer is CORRECT only if it also gives no answer.",
    "- If the documents give the answer and the answer says it does not know, it is INCORRECT.",
    "",
    "Use `unsure` only when you cannot decide from the documents. It is counted and never guessed.",
    "",
]


def _check_safe(item: dict) -> None:
    """A text line that looks like a section heading or a mark line would change what the parser reads."""
    texts = [item["question"], item["answer"], item.get("reference", "")]
    texts += [t for _, t in item["chunks"]]
    for text in texts:
        for line in text.splitlines():
            if (
                ITEM.match(line)
                or LABEL.match(line)
                or REFERENCE_RIGHT.match(line)
                or line.startswith("author label:")
            ):
                raise AblationRefused(
                    f"key {_short(item['verdict_key'])}: a text line looks like a sheet field"
                )


def _item_lines(item: dict) -> list[str]:
    lines = [
        f"## Item {item['item']}",
        "",
        f"product: {item['product_id']}",
        "",
        "### question",
        "",
        item["question"],
        "",
        "### documents",
        "",
    ]
    for chunk_id, text in item["chunks"]:
        lines += [f"[{chunk_id}]", "", text, ""]
    lines += ["### answer to check", "", item["answer"], ""]
    return lines


def write_sheet(items: list[dict], out: Path, written_at: str) -> None:
    """The author's blind sheet. One section per item: the question, the product, the gold evidence chunk by
    chunk, the answer, and an empty `label:` line. No reference, verdict, cache outcome, overlap or stratum.
    Writes once; never over a file that exists."""
    out = Path(out)
    if out.exists():
        raise AblationRefused(
            f"{out} exists; the author's labels are never overwritten"
        )
    lines = [
        f"# Labelling sheet, item 5.2, {len(items)} items",
        "",
        f"written_at: {written_at}",
        "",
        *RUBRIC_HEADER,
    ]
    for item in items:
        _check_safe(item)
        lines += _item_lines(item)
        lines += ["### label", "", "label:", ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _sections(text: str) -> dict[int, str]:
    found = list(ITEM.finditer(text))
    sections: dict[int, str] = {}
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(text)
        number = int(m.group(1))
        if number in sections:
            raise AblationRefused(f"item {number} appears twice on the sheet")
        sections[number] = text[m.start() : end]
    return sections


def _mark(pattern: re.Pattern[str], section: str) -> str:
    found = pattern.findall(section)
    return found[-1].lower() if found else ""


def parse_sheet(text: str) -> dict[int, str]:
    """`item number -> the word after label:` (case-folded; `""` when the line is empty or unreadable)."""
    return {n: _mark(LABEL, s) for n, s in _sections(text).items()}


def write_refsheet(items: list[dict], out: Path, written_at: str) -> None:
    """The second sheet: each item adds the reference answer and the author's locked label (read-only), and
    an empty `reference right:` line. Writes once."""
    out = Path(out)
    if out.exists():
        raise AblationRefused(f"{out} exists; the author's marks are never overwritten")
    lines = [
        f"# Reference check, item 5.2, {len(items)} items",
        "",
        f"written_at: {written_at}",
        "",
        "These are the items where the judge and your label both decided and differ. For each, read the",
        "reference answer the judge saw. Write `yes` after `reference right:` if it is correct by the",
        "documents, or `no` if it is wrong. A reference that declines is right only when the documents",
        "do not answer the question. Your label above is locked and is not changed here.",
        "",
    ]
    for item in items:
        _check_safe(item)
        lines += _item_lines(item)
        lines += [
            "### reference answer",
            "",
            item["reference"],
            "",
            "### mark",
            "",
            f"author label: {item['label']}",
            "reference right:",
            "",
        ]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def parse_refsheet(text: str) -> dict[int, str]:
    """`item number -> the word after reference right:` (case-folded; `""` when empty)."""
    return {n: _mark(REFERENCE_RIGHT, s) for n, s in _sections(text).items()}


def _rate(k: int, n: int) -> dict:
    return {
        "k": k,
        "n": n,
        "rate": round(k / n, 4) if n else None,
        "wilson95": select_pqa.wilson(k, n),
    }


def agreement(pairs: list[tuple[str, str]]) -> dict:
    """Agreement of a judge with a second labeller over `(judge, other)` pairs of words.

    A pair counts only when both sides decided (`CORRECT` or `INCORRECT`); an `UNPARSED` or `UNSURE` side
    puts the pair in `undecided`. `agree` over `n` with a Wilson interval (metrics R8), Cohen's kappa
    (no interval: it is not a rate), and the recall and precision of `INCORRECT` with the judge as the
    predictor: recall = judge `INCORRECT` among other `INCORRECT`; precision = other `INCORRECT` among
    judge `INCORRECT`.
    """
    decided = [(a, b) for a, b in pairs if a in DECIDED and b in DECIDED]
    both_incorrect = sum(1 for a, b in decided if a == b == "INCORRECT")
    agree = sum(1 for a, b in decided if a == b)
    return {
        **_rate(agree, len(decided)),
        "undecided": len(pairs) - len(decided),
        "kappa": kappa(pairs),
        "recall": _rate(both_incorrect, sum(1 for _, b in decided if b == "INCORRECT")),
        "precision": _rate(
            both_incorrect, sum(1 for a, _ in decided if a == "INCORRECT")
        ),
    }


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa `(p_o - p_e) / (1 - p_e)` over the decided pairs, to 4 decimals. `None` when there is
    no decided pair or when `p_e` is 1 (both sides use only one label)."""
    decided = [(a, b) for a, b in pairs if a in DECIDED and b in DECIDED]
    n = len(decided)
    if n == 0:
        return None
    p_o = sum(1 for a, b in decided if a == b) / n
    p_e = sum(
        (sum(1 for a, _ in decided if a == w) / n)
        * (sum(1 for _, b in decided if b == w) / n)
        for w in DECIDED
    )
    if math.isclose(p_e, 1.0):
        return None
    return round((p_o - p_e) / (1 - p_e), 4)


def circularity(a1: dict, a0: dict) -> dict:
    """The circularity rule (Entry 6; Entry 5 had a reference-free judge in the author's place). `a1` and
    `a0` are `agreement` dicts of `judge-v1` against the author on hits at 1.0 and on hits below 1.0.

    **bounded** if A0 >= A1, or A0's Wilson interval contains A1; **quantified** otherwise, with
    A1 - A0 as the inflation. `undefined` when either side has no decided pair.
    """
    if not a1["n"] or not a0["n"]:
        return {
            "result": "undefined",
            "inflation": None,
            "a1": a1["rate"],
            "a0": a0["rate"],
        }
    low, high = a0["wilson95"]
    bounded = a0["rate"] >= a1["rate"] or low <= a1["rate"] <= high
    return {
        "result": "bounded" if bounded else "quantified",
        "inflation": None if bounded else round(a1["rate"] - a0["rate"], 4),
        "a1": a1["rate"],
        "a0": a0["rate"],
        "n_a1": a1["n"],
        "n_a0": a0["n"],
    }


def disagreements(
    labels: dict[str, str], verdicts: dict[str, str], order: list[str]
) -> list[str]:
    """The keys, in `order`, where `judge-v1` and the author both decided and differ. An `unsure` author
    and an `UNPARSED` verdict are not a disagreement."""
    out = []
    for key in order:
        mine = LABEL_TO_VERDICT[labels[key]]
        theirs = verdicts[key]
        if mine in DECIDED and theirs in DECIDED and mine != theirs:
            out.append(key)
    return out


# =================================================================================================
# Files
# =================================================================================================
def _read_jsonl(path: Path) -> list[dict]:
    return judge._read_jsonl(path)


def _jsonl_text(rows: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def _write_new(path: Path, text: str) -> None:
    path = Path(path)
    if path.exists():
        raise AblationRefused(f"{path} exists; ablation output is never overwritten")
    with open(path, "x", encoding="utf-8") as f:
        f.write(text)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ablation_dir(results_dir: Path, run_id: str) -> Path:
    return Path(results_dir) / run_id / "ablation"


def _load_run(results_dir: Path, run_id: str) -> tuple[Path, list[dict], list[dict]]:
    """The source run's records and judge records. Refuses a run that is not admissible, has
    `mutation: on`, or was not judged by `judge-v1`."""
    run_dir = Path(results_dir) / run_id
    manifest_path = run_dir / "manifest.yaml"
    if not manifest_path.is_file():
        raise AblationRefused(f"no manifest.yaml in {run_dir}")
    manifest = yaml.safe_load(manifest_path.read_text())
    if (manifest.get("admissibility") or {}).get("admissible") is not True:
        raise AblationRefused("the manifest does not say admissible: true")
    if (manifest.get("arms") or {}).get("mutation") != "off":
        raise AblationRefused("the run has mutation: on; only mutation: off is sampled")
    judge_path = run_dir / "judge" / "records.jsonl"
    if not judge_path.is_file():
        raise AblationRefused(f"no judge/records.jsonl in {run_dir}")
    judge_records = _read_jsonl(judge_path)
    others = {r["judge_version"] for r in judge_records} - {SOURCE_JUDGE}
    if others:
        raise AblationRefused(
            f"the run was judged by {sorted(others)}, not {SOURCE_JUDGE}"
        )
    return run_dir, run_manifest.read_records(run_dir), judge_records


def _verdict_map(path: Path) -> dict[str, str]:
    return {r["verdict_key"]: r["verdict"] for r in _read_jsonl(path)}


def _load_sample(adir: Path) -> list[dict]:
    path = adir / "sample.jsonl"
    if not path.is_file():
        raise AblationRefused(f"no {path}; run the draw first")
    return _read_jsonl(path)


def _count_by(rows: list[dict], field: str) -> dict:
    return dict(sorted(Counter(r[field] for r in rows).items()))


# =================================================================================================
# draw
# =================================================================================================
def _draw_summary(
    run_id: str,
    rows: list[dict],
    excluded: dict,
    sample: list[dict],
    sample_sha256: str,
) -> dict:
    return {
        "run_id": run_id,
        "source_judge": SOURCE_JUDGE,
        "seed": SEED,
        "n_miss": N_MISS,
        "frame": {
            "keys": len(rows),
            "excluded": excluded,
            "by_stratum": _count_by(rows, "stratum"),
            "by_bucket": _count_by(rows, "bucket"),
        },
        "sample": {
            "keys": len(sample),
            "by_stratum": _count_by(sample, "stratum"),
            "by_bucket": _count_by(sample, "bucket"),
            "answerable_false": sum(1 for r in sample if not r["answerable"]),
        },
        "sample_sha256": sample_sha256,
    }


def run_draw(
    run_id: str,
    *,
    results_dir: Path = RESULTS_DIR,
    n_miss: int = N_MISS,
    seed: int = SEED,
    now: Callable[[], str] = _now,
    log: Callable[[str], None] = print,
) -> int:
    """Draw the sample and write `ablation/draw.json` and `ablation/sample.jsonl`. When both exist, draw
    again in memory instead and compare: returns 0 and prints `identical`, or returns 1."""
    _, records, judge_records = _load_run(results_dir, run_id)
    adir = _ablation_dir(results_dir, run_id)
    rows, excluded = frame(records, judge_records)
    sample = draw(rows, n_miss, seed)
    sample_text = _jsonl_text(sample)
    summary = _draw_summary(run_id, rows, excluded, sample, _sha256_text(sample_text))

    draw_path, sample_path = adir / "draw.json", adir / "sample.jsonl"
    if draw_path.exists() and sample_path.exists():
        problems = []
        if sample_path.read_text(encoding="utf-8") != sample_text:
            problems.append("sample.jsonl differs from a fresh draw")
        written = json.loads(draw_path.read_text())
        written.pop("written_at", None)
        if written != summary:
            problems.append("draw.json differs from a fresh draw")
        if problems:
            log("DIFFERENT: " + "; ".join(problems))
            return 1
        log("identical")
        return 0
    if draw_path.exists() or sample_path.exists():
        raise AblationRefused(f"only one of {draw_path} and {sample_path} exists")

    adir.mkdir(parents=True, exist_ok=True)
    _write_new(sample_path, sample_text)
    _write_new(draw_path, json.dumps({"written_at": now(), **summary}, indent=2) + "\n")
    log(
        f"  frame {len(rows)} keys, excluded {excluded}; sample {len(sample)} keys "
        f"{summary['sample']['by_stratum']}, hit buckets "
        f"{ {b: n for b, n in summary['sample']['by_bucket'].items() if b != MISS_BUCKET} }"
    )
    log(f"  wrote {draw_path} and {sample_path}")
    return 0


# =================================================================================================
# The items: question, product, evidence and answer of every sampled key
# =================================================================================================
def load_items(
    run_dir: Path,
    sample: list[dict],
    refs_dir: Path,
    texts: dict[str, str],
) -> dict[str, dict]:
    """`verdict key -> item` for the sampled keys: the question, the product, the gold evidence chunks
    (the reference index's `chunk_ids`), the answer, and the reference. Refuses when a sampled key does not
    recompute from its record (the sample is not this run's), or when no reference matches the key's
    `(question, product_id)`."""
    records = {r["request_id"]: r for r in run_manifest.read_records(run_dir)}
    sampled = []
    for row in sample:
        r = records.get(row["request_id"])
        if r is None:
            raise AblationRefused(f"{row['request_id']}: not a record of the run")
        sampled.append(r)
    answers = judge.load_answers(run_dir, sampled)
    index = refs.read_index(refs_dir)
    by_pair = {(r["question"], r.get("product_id") or ""): r for r in index}
    items: dict[str, dict] = {}
    for row, r in zip(sample, sampled, strict=True):
        product_id = r.get("product_id") or ""
        key = judge.verdict_key(
            r["query_raw"], product_id, r.get("answer_sha256") or ""
        )
        if key != row["verdict_key"]:
            raise AblationRefused(
                f"{row['request_id']}: the verdict key does not recompute from its record"
            )
        ref = by_pair.get((r["query_raw"], product_id))
        if ref is None:
            raise AblationRefused(f"{row['request_id']}: no reference for its question")
        if ref["qa_id"] != row["qa_id"]:
            raise AblationRefused(
                f"{row['request_id']}: qa_id differs from the reference's"
            )
        reference = (
            Path(refs_dir) / "answers" / f"{ref['reference_sha256']}.txt"
        ).read_text()
        items[key] = {
            "verdict_key": key,
            "question": r["query_raw"],
            "product_id": product_id,
            "chunk_ids": list(ref["chunk_ids"]),
            "chunks": [(c, texts[c]) for c in ref["chunk_ids"]],
            "evidence": evidence(ref, texts),
            "answer": answers[r["answer_sha256"]],
            "reference": reference,
        }
    return items


def _default_texts() -> dict[str, str]:
    return refs.corpus_chunks(refs.CORPUS_DIR)[1]


def _shuffled(sample: list[dict], seed: int) -> list[dict]:
    order = sorted(sample, key=lambda r: r["verdict_key"])
    random.Random(seed).shuffle(order)
    return order


# =================================================================================================
# sheet
# =================================================================================================
def run_sheet(
    run_id: str,
    *,
    results_dir: Path = RESULTS_DIR,
    sheet_path: Path = SHEET_PATH,
    refs_dir: Path = refs.REFERENCES_DIR / "validation",
    texts: dict[str, str] | None = None,
    seed: int = SEED,
    now: Callable[[], str] = _now,
    log: Callable[[str], None] = print,
) -> int:
    """Write the blind sheet (private) and `ablation/items.jsonl` (item number -> verdict key)."""
    run_dir = Path(results_dir) / run_id
    adir = _ablation_dir(results_dir, run_id)
    sample = _load_sample(adir)
    items_path = adir / "items.jsonl"
    for path in (items_path, Path(sheet_path)):
        if path.exists():
            raise AblationRefused(f"{path} exists; the sheet is written once")
    items = load_items(
        run_dir, sample, refs_dir, _default_texts() if texts is None else texts
    )
    order = _shuffled(sample, seed)
    when = now()
    numbered = [{**items[r["verdict_key"]], "item": n} for n, r in enumerate(order, 1)]
    write_sheet(numbered, sheet_path, when)
    _write_new(
        items_path,
        _jsonl_text(
            [
                {
                    "item": it["item"],
                    "verdict_key": it["verdict_key"],
                    "written_at": when,
                }
                for it in numbered
            ]
        ),
    )
    log(f"  wrote {sheet_path} ({len(numbered)} items) and {items_path}")
    return 0


# =================================================================================================
# The reference-free judge
# =================================================================================================
def rf_problems(
    rf_cfg: dict,
    v1_cfg: dict,
    prereg_text: str,
    ollama: judge.Ollama,
    generator_model: str | None,
) -> list[str]:
    """What stops a reference-free call: everything `judge.judge_problems` checks for `judge-rf-v1.json`,
    and a `model`, `digest` or `options` that differs from `judge-v1.json`'s (the two schemes may differ
    in the prompt only)."""
    problems = judge.judge_problems(rf_cfg, prereg_text, ollama, generator_model)
    for key in ("model", "digest", "options"):
        if rf_cfg.get(key) != v1_cfg.get(key):
            problems.append(
                f"{key}: judge-rf-v1.json has {rf_cfg.get(key)!r}, judge-v1.json has {v1_cfg.get(key)!r}"
            )
    return problems


def ask_judge_rf(
    question: str, evidence_text: str, answer: str, cfg: dict, post: judge.Ollama
) -> tuple[str, float, int | None]:
    """One `/api/generate` call with `stream: false`, built as `judge.ask_judge` builds it, with the gold
    evidence in place of the reference. Returns the reply, the seconds, and the reply's
    `prompt_eval_count` (`None` when the reply has none)."""
    body = {
        "model": cfg["model"],
        "prompt": cfg["prompt_text"].format(
            question=question, evidence=evidence_text, answer=answer
        ),
        "stream": False,
        "options": cfg["options"],
    }
    if cfg.get("send_think"):
        body["think"] = False
    start = time.monotonic()
    reply = post("/api/generate", body)
    return reply["response"], time.monotonic() - start, reply.get("prompt_eval_count")


def _with_think(cfg: dict, ollama: judge.Ollama) -> dict:
    show = ollama("/api/show", {"model": cfg["model"]})
    return {**cfg, "send_think": "thinking" in (show.get("capabilities") or [])}


def rf_sanity(
    file: Path,
    *,
    refs_dir: Path = refs.REFERENCES_DIR / "validation",
    rf_path: Path = RF_CFG,
    judge_path: Path = JUDGE_CFG,
    prereg_path: Path = PREREGISTRATION,
    generator_model: str | None = None,
    texts: dict[str, str] | None = None,
    ollama: judge.Ollama,
    pressure: Callable[[], int | None] = corpus_gate.memory_pressure_level,
    now: Callable[[], str] = _now,
    log: Callable[[str], None] = print,
) -> int:
    """Judge item 5.1's hand-made pairs without the reference, each with its gold evidence. Returns 0 only
    when every verdict is the expected one and none is `UNPARSED`. The prompt is not edited on a failure:
    a new version is the author's call (ADR-022)."""
    cfg = judge.load_judge(rf_path)
    problems = rf_problems(
        cfg,
        judge.load_judge(judge_path),
        Path(prereg_path).read_text(),
        ollama,
        generator_model,
    )
    if problems:
        raise AblationRefused("; ".join(problems))
    judge._check_pressure(pressure, [], log, "before the first verdict")
    cfg = _with_think(cfg, ollama)
    texts = _default_texts() if texts is None else texts

    log(f"written_at: {now()}")
    by_qa = {row["qa_id"]: row for row in refs.read_index(refs_dir)}
    rows = _read_jsonl(Path(file))
    wrong = unparsed = 0
    for row in rows:
        ref = by_qa.get(row["qa_id"])
        if ref is None:
            raise AblationRefused(f"{row['qa_id']} is not in the reference set")
        reply, _, _ = ask_judge_rf(
            ref["question"], evidence(ref, texts), row["answer"], cfg, ollama
        )
        got = judge.parse_verdict(reply)
        unparsed += got == "UNPARSED"
        ok = got == row["expected"]
        wrong += not ok
        log(
            f"  {'ok  ' if ok else 'WRONG'} {row.get('kind', '?'):<22} {row['qa_id']}: "
            f"expected {row['expected']}, got {got}"
        )
    log(f"  {len(rows) - wrong} of {len(rows)} correct, {unparsed} UNPARSED")
    return 0 if wrong == 0 else 1


def rf_run(
    run_id: str,
    *,
    results_dir: Path = RESULTS_DIR,
    refs_dir: Path = refs.REFERENCES_DIR / "validation",
    rf_path: Path = RF_CFG,
    judge_path: Path = JUDGE_CFG,
    prereg_path: Path = PREREGISTRATION,
    generator_model: str | None = None,
    texts: dict[str, str] | None = None,
    ollama: judge.Ollama,
    pressure: Callable[[], int | None] = corpus_gate.memory_pressure_level,
    now: Callable[[], str] = _now,
    log: Callable[[str], None] = print,
) -> dict:
    """The reference-free verdict of every sampled key. Writes `ablation/verdicts-rf.jsonl` and
    `ablation/rf.json` after the last call, and nothing when a rule stops the run first.

    Stops at the first call whose `prompt_eval_count` is missing or at or above `num_ctx` (Ollama drops
    prompt text past `num_ctx` with no error), and at memory pressure 4. More than 2 % `UNPARSED` is
    written, with `rows_reportable: false`.
    """
    started = time.monotonic()
    run_dir = Path(results_dir) / run_id
    adir = _ablation_dir(results_dir, run_id)
    sample = _load_sample(adir)
    out_rows, out_summary = adir / "verdicts-rf.jsonl", adir / "rf.json"
    for path in (out_rows, out_summary):
        if path.exists():
            raise AblationRefused(
                f"{path} exists; ablation output is never overwritten"
            )

    cfg = judge.load_judge(rf_path)
    problems = rf_problems(
        cfg,
        judge.load_judge(judge_path),
        Path(prereg_path).read_text(),
        ollama,
        generator_model,
    )
    if problems:
        raise AblationRefused("; ".join(problems))
    items = load_items(
        run_dir, sample, refs_dir, _default_texts() if texts is None else texts
    )

    readings: list = []
    judge._check_pressure(pressure, readings, log, "before the first verdict")
    cfg = _with_think(cfg, ollama)
    num_ctx = cfg["options"]["num_ctx"]

    rows: list[dict] = []
    for i, row in enumerate(sample, 1):
        item = items[row["verdict_key"]]
        reply, took, eval_count = ask_judge_rf(
            item["question"], item["evidence"], item["answer"], cfg, ollama
        )
        if eval_count is None or eval_count >= num_ctx:
            raise AblationRefused(
                f"key {_short(row['verdict_key'])}: prompt_eval_count is {eval_count}, "
                f"num_ctx is {num_ctx}; the prompt may be cut"
            )
        rows.append(
            {
                "verdict_key": row["verdict_key"],
                "verdict": judge.parse_verdict(reply),
                "reply": reply,
                "seconds": took,
                "prompt_eval_count": eval_count,
                "written_at": now(),
            }
        )
        if i % judge.PROGRESS_EVERY == 0 or i == len(sample):
            log(f"  {i}/{len(sample)} keys judged")
        if i % PRESSURE_EVERY == 0 and i < len(sample):
            judge._check_pressure(pressure, readings, log, f"after {i} keys")
    judge._check_pressure(pressure, readings, log, "after the last key")

    counted = Counter(r["verdict"] for r in rows)
    seconds = sorted(r["seconds"] for r in rows)
    share = counted["UNPARSED"] / len(rows) if rows else 0.0
    summary = {
        "written_at": now(),
        "run_id": run_id,
        "judge_version": cfg["version"],
        "record_sha256": cfg["cfg_sha256"],
        "prompt_sha256": cfg["prompt_sha256"],
        "model": cfg["model"],
        "digest": cfg["digest"],
        "options": cfg["options"],
        "keys": len(rows),
        "verdicts": {v: counted[v] for v in judge.VERDICTS},
        "unparsed_share": share,
        "rows_reportable": share <= UNPARSED_LIMIT,
        "num_ctx": num_ctx,
        "max_prompt_eval_count": max(r["prompt_eval_count"] for r in rows),
        "all_prompt_eval_counts_below_num_ctx": True,
        "pressure_readings": readings,
        "seconds_per_verdict": {
            "median": statistics.median(seconds) if seconds else None,
            "p95": judge._percentile(seconds, 0.95) if seconds else None,
            "total": sum(seconds),
        },
        "wall_seconds": time.monotonic() - started,
    }
    _write_new(out_rows, _jsonl_text(rows))
    _write_new(out_summary, json.dumps(summary, indent=2) + "\n")
    log(f"  wrote {out_rows} and {out_summary}: {dict(counted)}")
    if not summary["rows_reportable"]:
        log(
            f"  STOP: UNPARSED is {share:.1%} of keys, over {UNPARSED_LIMIT:.0%}; "
            "its rows are not reported"
        )
    return summary


# =================================================================================================
# lock
# =================================================================================================
def _items_of(adir: Path) -> list[dict]:
    path = adir / "items.jsonl"
    if not path.is_file():
        raise AblationRefused(f"no {path}; write the sheet first")
    return sorted(_read_jsonl(path), key=lambda r: r["item"])


def lock(
    run_id: str,
    *,
    results_dir: Path = RESULTS_DIR,
    sheet_path: Path = SHEET_PATH,
    refsheet_path: Path = REFSHEET_PATH,
    refs_dir: Path = refs.REFERENCES_DIR / "validation",
    texts: dict[str, str] | None = None,
    now: Callable[[], str] = _now,
    log: Callable[[str], None] = print,
) -> dict:
    """Lock the author's labels and write the second sheet.

    Reads the first sheet, refuses an unmarked item or a word other than `correct`, `incorrect` or
    `unsure`, writes `ablation/labels.jsonl` (each row carries the sheet's sha256), then writes the second
    sheet for the keys where `judge-v1` and the author both decided and disagree.
    """
    run_dir = Path(results_dir) / run_id
    adir = _ablation_dir(results_dir, run_id)
    labels_path = adir / "labels.jsonl"
    for path in (labels_path, Path(refsheet_path)):
        if path.exists():
            raise AblationRefused(f"{path} exists; the lock is written once")
    items = _items_of(adir)
    sheet_bytes = Path(sheet_path).read_bytes()
    marks = parse_sheet(sheet_bytes.decode("utf-8"))
    if set(marks) != {it["item"] for it in items}:
        raise AblationRefused("the sheet's items are not the items of items.jsonl")
    unmarked = sorted(n for n, w in marks.items() if w == "")
    if unmarked:
        raise AblationRefused(f"{len(unmarked)} items unmarked: {unmarked[:10]}")
    unknown = sorted(n for n, w in marks.items() if w not in LABEL_WORDS)
    if unknown:
        raise AblationRefused(
            f"items {unknown[:10]} carry a word other than {LABEL_WORDS}"
        )

    sheet_sha = hashlib.sha256(sheet_bytes).hexdigest()
    when = now()
    key_of = {it["item"]: it["verdict_key"] for it in items}
    labels = {key_of[n]: marks[n] for n in marks}
    label_rows = [
        {
            "item": it["item"],
            "verdict_key": it["verdict_key"],
            "label": marks[it["item"]],
            "sheet_sha256": sheet_sha,
            "written_at": when,
        }
        for it in items
    ]
    verdicts = _verdict_map(run_dir / "judge" / "verdicts.jsonl")
    order = [it["verdict_key"] for it in items]
    wrong = disagreements(labels, verdicts, order)

    sample = {r["verdict_key"]: r for r in _load_sample(adir)}
    second = []
    if wrong:
        loaded = load_items(
            run_dir,
            [sample[k] for k in wrong],
            refs_dir,
            _default_texts() if texts is None else texts,
        )
        number = {it["verdict_key"]: it["item"] for it in items}
        second = [{**loaded[k], "item": number[k], "label": labels[k]} for k in wrong]
    _write_new(labels_path, _jsonl_text(label_rows))
    write_refsheet(second, refsheet_path, when)

    counts = Counter(labels.values())
    by_stratum = Counter(sample[k]["stratum"] for k in wrong)
    log(
        f"  {len(label_rows)} labels: {counts['correct']} correct, {counts['incorrect']} incorrect, "
        f"{counts['unsure']} unsure"
    )
    log(f"  first sheet sha256 {sheet_sha}")
    log(
        f"  decided disagreements with {SOURCE_JUDGE}: {len(wrong)} "
        f"({by_stratum['hit']} hits, {by_stratum['MISS']} MISS); second sheet {refsheet_path}"
    )
    return {
        "labels": len(label_rows),
        "counts": dict(counts),
        "sheet_sha256": sheet_sha,
        "disagreements": len(wrong),
    }


# =================================================================================================
# score
# =================================================================================================
def _entry_end(
    pattern: re.Pattern[str], number: int, prereg_text: str
) -> datetime.datetime:
    """The first instant after an entry's stated minute. The entry's heading has minute resolution, so a
    `written_at` inside that minute cannot be shown to come later."""
    m = pattern.search(prereg_text)
    if m is None:
        raise AblationRefused(
            f"preregistration.md has no Entry {number} with a UTC time"
        )
    year, month, day, hour, minute = (int(g) for g in m.groups())
    start = datetime.datetime(
        year, month, day, hour, minute, tzinfo=datetime.timezone.utc
    )
    return start + datetime.timedelta(minutes=1)


def entry5_end(prereg_text: str) -> datetime.datetime:
    """The first instant after Entry 5's stated minute."""
    return _entry_end(ENTRY_5, 5, prereg_text)


def entry6_end(prereg_text: str) -> datetime.datetime:
    """The first instant after Entry 6's stated minute."""
    return _entry_end(ENTRY_6, 6, prereg_text)


def _later_than(
    bound: datetime.datetime, times: dict[str, str], entry: int
) -> list[str]:
    problems = []
    for name, stamp in times.items():
        when = datetime.datetime.fromisoformat(stamp)
        if when.tzinfo is None:
            when = when.replace(tzinfo=datetime.timezone.utc)
        if when < bound:
            problems.append(f"{name} written_at {stamp} is not after Entry {entry}")
    return problems


def check_entry5_first(prereg_text: str, times: dict[str, str]) -> list[str]:
    """`written_at` fields that are not later than Entry 5, as messages. Empty means Entry 5 came first."""
    return _later_than(entry5_end(prereg_text), times, 5)


def check_entry6_first(prereg_text: str, sheet_written_at: str) -> list[str]:
    """The sheet's `written_at` when it is not later than Entry 6, as a message. Empty means Entry 6 (written
    after the sanity failure) came before the sheet, so the sheet could not steer the change."""
    return _later_than(entry6_end(prereg_text), {"sheet": sheet_written_at}, 6)


def _times(adir: Path, sheet_written: str, sanity_logs: list[Path]) -> dict[str, str]:
    """The `written_at` of the draw, of the sheet, and of the sanity logs that carry one. No reference-free
    file is read: none exists (Entry 6)."""
    times = {
        "draw.json": json.loads((adir / "draw.json").read_text())["written_at"],
        "sheet": sheet_written,
    }
    for path in sanity_logs:
        found = WRITTEN_AT_LINE.search(Path(path).read_text(errors="replace"))
        if found:
            times[Path(path).name] = found.group(1)
    return times


def _pairs(keys: list[str], left: dict[str, str], right: dict[str, str]) -> list[tuple]:
    return [(left[k], right[k]) for k in keys]


def _block(pairs: list[tuple[str, str]]) -> dict:
    return agreement(pairs)


def _by_stratum(sample: list[dict], v1: dict, author: dict) -> dict:
    """Per stratum (hits and MISSes apart): `judge-v1` against the author, the `answerable: false` row, and
    the same agreement per bucket. Hits are split into `1.0`, `[0.8, 1)`, `[0.6, 0.8)`, `below 0.6` and
    `below 1.0` (the union of the last three); MISSes are the one bucket `generated`."""
    out = {}
    for stratum in STRATA:
        rows = [r for r in sample if r["stratum"] == stratum]
        keys = [r["verdict_key"] for r in rows]
        block = {
            "keys": len(keys),
            "judge_vs_author": _block(_pairs(keys, v1, author)),
        }
        false_keys = [r["verdict_key"] for r in rows if not r["answerable"]]
        block["answerable_false_judge_vs_author"] = _block(
            _pairs(false_keys, v1, author)
        )
        if stratum == "hit":
            names = (*HIT_BUCKETS, "below 1.0")
        else:
            names = (MISS_BUCKET,)
        by_bucket = {}
        for name in names:
            in_bucket = [
                r["verdict_key"]
                for r in rows
                if (
                    r["bucket"] != "1.0" if name == "below 1.0" else r["bucket"] == name
                )
            ]
            by_bucket[name] = {
                "keys": len(in_bucket),
                **_block(_pairs(in_bucket, v1, author)),
            }
        block["judge_vs_author_by_bucket"] = by_bucket
        out[stratum] = block
    return out


def score(
    run_id: str,
    *,
    results_dir: Path = RESULTS_DIR,
    prereg_path: Path = PREREGISTRATION,
    sheet_path: Path = SHEET_PATH,
    refsheet_path: Path = REFSHEET_PATH,
    sanity_logs: list[Path] | None = None,
    now: Callable[[], str] = _now,
    log: Callable[[str], None] = print,
) -> dict:
    """Score the ablation (`metrics.md` M21). Refuses, before it writes, when the first sheet's sha256
    differs from the lock, when the second sheet is not exactly the decided disagreements or has an
    unmarked item, when Entry 5 is not earlier than the draw, the sheet and the sanity logs, or when Entry 6
    is not earlier than the sheet. Reads no reference-free file (Entry 6). Writes `ablation/refcheck.jsonl`
    and `ablation/scores.json`, and prints the tables through `log`.
    """
    run_dir = Path(results_dir) / run_id
    adir = _ablation_dir(results_dir, run_id)
    out_refcheck, out_scores = adir / "refcheck.jsonl", adir / "scores.json"
    for path in (out_refcheck, out_scores):
        if path.exists():
            raise AblationRefused(
                f"{path} exists; ablation output is never overwritten"
            )

    sample = _load_sample(adir)
    items = _items_of(adir)
    label_rows = _read_jsonl(adir / "labels.jsonl")
    shas = {r["sheet_sha256"] for r in label_rows}
    now_sha = hashlib.sha256(Path(sheet_path).read_bytes()).hexdigest()
    if shas != {now_sha}:
        raise AblationRefused(
            "the first sheet changed after the lock: its sha256 is not the one in labels.jsonl"
        )
    keys = [r["verdict_key"] for r in sample]
    if not (
        {r["verdict_key"] for r in label_rows}
        == {it["verdict_key"] for it in items}
        == set(keys)
    ):
        raise AblationRefused("the sample, the items and the labels differ")

    prereg_text = Path(prereg_path).read_text()
    times = _times(adir, items[0]["written_at"], list(sanity_logs or []))
    late = check_entry5_first(prereg_text, times)
    if late:
        log("entry 5 first: NO")
        raise AblationRefused("; ".join(late))
    log(f"entry 5 first: yes (checked {len(times)} written_at fields)")
    late = check_entry6_first(prereg_text, items[0]["written_at"])
    if late:
        log("entry 6 first: NO")
        raise AblationRefused("; ".join(late))
    log("entry 6 first: yes (before the sheet)")

    v1 = _verdict_map(run_dir / "judge" / "verdicts.jsonl")
    labels = {r["verdict_key"]: r["label"] for r in label_rows}
    author = {k: LABEL_TO_VERDICT[w] for k, w in labels.items()}
    order = [it["verdict_key"] for it in items]
    sample_by_key = {r["verdict_key"]: r for r in sample}

    # the second sheet: exactly the decided disagreements, each marked yes or no
    wrong = disagreements(labels, v1, order)
    marks = parse_refsheet(Path(refsheet_path).read_text(encoding="utf-8"))
    number = {it["verdict_key"]: it["item"] for it in items}
    if set(marks) != {number[k] for k in wrong}:
        raise AblationRefused("the second sheet is not the decided disagreements")
    bad = sorted(n for n, w in marks.items() if w not in ("yes", "no"))
    if bad:
        raise AblationRefused(f"second sheet items {bad[:10]} are not marked yes or no")
    when = now()
    refcheck = [
        {
            "item": number[k],
            "verdict_key": k,
            "reference_right": marks[number[k]],
            "written_at": when,
        }
        for k in wrong
    ]

    scores = {
        "written_at": when,
        "run_id": run_id,
        "judge": SOURCE_JUDGE,
        "judge_rf": RF_FAILED,
        "reference_free_side": "author",
        "sheet_sha256": now_sha,
        "entry5_first": True,
        "entry6_first": True,
        "sample_keys": len(sample),
        "author_labels": dict(sorted(Counter(labels.values()).items())),
        "by_stratum": _by_stratum(sample, v1, author),
    }
    layer5 = {}
    for stratum in STRATA:
        decided = [
            k
            for k in keys
            if sample_by_key[k]["stratum"] == stratum and author[k] in DECIDED
        ]
        no = [
            k
            for k in wrong
            if sample_by_key[k]["stratum"] == stratum and marks[number[k]] == "no"
        ]
        layer5[stratum] = {
            **_rate(len(no), len(decided)),
            "checked": sum(1 for k in wrong if sample_by_key[k]["stratum"] == stratum),
        }
    scores["layer5"] = layer5
    by_bucket = scores["by_stratum"]["hit"]["judge_vs_author_by_bucket"]
    scores["circularity"] = circularity(by_bucket["1.0"], by_bucket["below 1.0"])

    _write_new(out_refcheck, _jsonl_text(refcheck))
    _write_new(out_scores, json.dumps(scores, indent=2) + "\n")
    for line in format_scores(scores):
        log(line)
    log(f"  wrote {out_scores} and {out_refcheck}")
    return scores


def _fmt_rate(block: dict) -> str:
    if not block["n"]:
        return "n/a (n 0)"
    low, high = block["wilson95"]
    return f"{block['k']}/{block['n']} = {block['rate']:.3f} [{low:.3f}, {high:.3f}]"


def _fmt_agreement(block: dict) -> str:
    kappa_text = "undefined" if block["kappa"] is None else f"{block['kappa']:.3f}"
    return f"agreement {_fmt_rate(block)}, kappa {kappa_text}, undecided {block['undecided']}"


def _fmt_recall_precision(block: dict) -> str:
    recall = _fmt_rate(block["recall"])
    precision = _fmt_rate(block["precision"])
    return f"    recall of INCORRECT {recall}; precision {precision}"


def format_scores(scores: dict) -> list[str]:
    """The tables of DC 7, one block per stratum (hits and MISSes are never pooled)."""
    lines = []
    for stratum in STRATA:
        block = scores["by_stratum"][stratum]
        lines += [
            "",
            f"== {stratum} ({block['keys']} keys) ==",
            f"(a) {SOURCE_JUDGE} vs author: {_fmt_agreement(block['judge_vs_author'])}",
            _fmt_recall_precision(block["judge_vs_author"]),
            f"    answerable false: {_fmt_agreement(block['answerable_false_judge_vs_author'])}",
        ]
        lines += [
            f"(b) not computed: {RF_VERSION} failed its sanity check (Entry 6)",
            f"(c) {SOURCE_JUDGE} vs author, by bucket:",
        ]
        for bucket, b in block["judge_vs_author_by_bucket"].items():
            lines.append(
                f"    bucket {bucket:<11} (n keys {b['keys']}) {_fmt_agreement(b)}"
            )
        lines.append(
            f"(d) layer 5, wrong references: {_fmt_rate(scores['layer5'][stratum])}"
            f" ({scores['layer5'][stratum]['checked']} checked)"
        )
    c = scores["circularity"]
    lines += ["", f"(e) circularity: {c['result']}"]
    if c["result"] in ("bounded", "quantified"):
        lines.append(
            f"    A1 {c['a1']:.3f} (n {c['n_a1']}), A0 {c['a0']:.3f} (n {c['n_a0']})"
            + (
                f", inflation {c['inflation']:.3f}"
                if c["inflation"] is not None
                else ""
            )
        )
    return lines


# =================================================================================================
# Command line
# =================================================================================================
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)

    def with_run(name: str, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--run-id", required=True)
        p.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
        return p

    with_run("draw", "draw the sample, or confirm a second draw is identical")
    p_sanity = sub.add_parser("rf-sanity", help="the 12 sanity pairs, reference-free")
    p_sanity.add_argument("--file", type=Path, required=True)
    p_sheet = with_run("sheet", "write the author's blind sheet")
    p_sheet.add_argument("--sheet", type=Path, default=SHEET_PATH)
    with_run("rf", "retired by Entry 6: refuses and exits 1 (no reference-free run)")
    p_lock = with_run("lock", "lock the author's labels and write the second sheet")
    p_lock.add_argument("--sheet", type=Path, default=SHEET_PATH)
    p_lock.add_argument("--refsheet", type=Path, default=REFSHEET_PATH)
    p_score = with_run("score", "score the ablation and print the tables")
    p_score.add_argument("--sheet", type=Path, default=SHEET_PATH)
    p_score.add_argument("--refsheet", type=Path, default=REFSHEET_PATH)

    args = ap.parse_args(argv)
    try:
        if args.command == "rf":
            # Entry 6: judge-rf-v1 failed its sanity check and is used for no score. Refuse before any
            # Ollama call and before anything is read or written.
            raise AblationRefused(RF_RETIRED)
        if args.command == "draw":
            return run_draw(args.run_id, results_dir=args.results_dir)
        if args.command == "sheet":
            return run_sheet(
                args.run_id, results_dir=args.results_dir, sheet_path=args.sheet
            )
        if args.command == "lock":
            lock(
                args.run_id,
                results_dir=args.results_dir,
                sheet_path=args.sheet,
                refsheet_path=args.refsheet,
            )
            return 0
        if args.command == "score":
            score(
                args.run_id,
                results_dir=args.results_dir,
                sheet_path=args.sheet,
                refsheet_path=args.refsheet,
                sanity_logs=sorted(args.sheet.parent.glob("rf-sanity-*.log")),
            )
            return 0

        from rag import config

        ollama = judge.make_ollama(config.OLLAMA_BASE_URL)
        return rf_sanity(args.file, generator_model=config.LLM_MODEL, ollama=ollama)
    except (AblationRefused, judge.JudgeRefused, run_manifest.ManifestError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
