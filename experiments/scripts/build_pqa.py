"""Amazon-PQA builder — super-plan item 3.1, replacing `fetch_corpus_v1.py`.

Checks the six pinned PQA leaf files, parses them against the REAL field names, stops on a bad
parse, and writes (a) one gitignored interim file per leaf and (b) a hash manifest that holds only
hashes and counts. It has no network code: downloading is `make pqa-fetch` (curl, resume).

    make pqa-fetch      # download or resume the six files into data/raw/pqa/
    make pqa-build      # verify, parse, check, write the interim files and the manifest
    make pqa-verify     # offline: hash the files on disk against the tracked manifest

## Why it stops so often

The dataset's readme names fields the data does not use (`asin_id`, `bullet_points`, ...). A builder
written from it returns empty records and raises no error. So the builder has four stops, and any of
them ends the run with exit code 2 and writes nothing under a final name:

| Stop | Checks | Catches |
| :-- | :--- | :--- |
| 0 | size, then sha256, of the source file | a wrong, short or changed file |
| 1 | at least one record parsed | the readme's field names |
| 2 | every real field non-empty at least once; no key outside the real set | misnamed bullets; a field the builder forgot to list |
| 3a | on the input: records parsed, products, records skipped equal the pinned numbers | a parser that reads more or fewer records than the probe |
| 3b | on the interim file as written: product and question counts, `question_type` counts, `answer_aggregated` counts and `prose_median_chars` equal the pinned numbers | a writer that drops a bullet or swaps two aggregates |
| 3c | every line of the interim file equals the product the parser built (a digest taken before the writer ran) | a writer that swaps, blanks or shortens any other field |

The pins (3a, 3b) are facts about pinned bytes, not settings. They come from the 2026-10-03 probe,
which was written separately (`docs/work/2026-10-03-pqa-category-choice/probe_results.json`). A change
to a pin needs a line in the task's `approvals.md`. 3c compares the writer with the parser, not with
the probe: a parser that reads a field consistently wrong (for example `item_name` into the `brand_name`
slot) passes 3b and 3c. The tests pin each field's slot with hand-written values for that reason.

The manifest is NOT the corpus snapshot digest. That is item 3.6's (`make gate-corpus`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import resource
import shutil
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = (
    REPO_ROOT / "data" / "raw" / "pqa"
)  # gitignored permanently; never redistributed
INTERIM_DIR = REPO_ROOT / "data" / "v1-draft" / "pqa"  # gitignored (data/v1-draft/)
MANIFEST_PATH = (
    REPO_ROOT / "data" / "pqa-manifest.json"
)  # TRACKED: hashes and counts only
BASE_URL = "https://amazon-pqa.s3.amazonaws.com"
MANIFEST_VERSION = 1
MANIFEST_NOTE = (
    "Covers the 3.1 interim files only. It is not the v1 snapshot digest (item 3.6)."
)

# Why each skipped line is skipped. A line is parsed or skipped for exactly one of these.
BLANK_LINE = "blank_line"
BAD_JSON = "bad_json"  # includes invalid UTF-8: json.loads(bytes) raises UnicodeDecodeError, a ValueError
NOT_OBJECT = "not_object"
MISSING_ASIN = "missing_asin"
BAD_QUESTION_TEXT = "bad_question_text"  # missing, not a string, or blank after strip
SKIP_REASONS = (BLANK_LINE, BAD_JSON, NOT_OBJECT, MISSING_ASIN, BAD_QUESTION_TEXT)

REPLACEMENT = chr(0xFFFD)
# json.loads accepts a lone surrogate (as an escape, and as the raw bytes ED A0 80). It cannot be
# written as UTF-8 and redis-py's strict encoder rejects it, so it is replaced and counted (D9).
_LONE_SURROGATE = re.compile("[" + chr(0xD800) + "-" + chr(0xDFFF) + "]")

# --- The real field set ---------------------------------------------------------------------------
# Counted from the bytes (evidence/key-census.md, 2026-10-15), NOT from the dataset's readme.
BULLET_FIELDS = tuple(f"bullet_point{n}" for n in range(1, 6))
PROSE_FIELDS = (*BULLET_FIELDS, "product_description")
REAL_FIELDS = (
    "asin",
    "question_id",
    "question_text",
    "question_type",
    "answers",
    "answer_aggregated",
    "brand_name",
    "item_name",
    "product_description",
    *BULLET_FIELDS,
)

# Keys that are seen in the data but deliberately unused, each with a written reason. Empty on
# purpose: a key outside REAL_FIELDS stops the run, so adding an entry is a decision, not a default.
IGNORED_KEYS: dict[str, str] = {}


@dataclass(frozen=True)
class LeafSpec:
    """One source file and the numbers that pin what parsing it must give."""

    leaf: str
    department: str
    bytes: int
    sha256: str
    parsed: int
    products: int
    skipped_total: int
    question_type: dict[str, int] = field(default_factory=dict)
    answer_aggregated: dict[str, int] = field(default_factory=dict)
    prose_median_chars: int = 0

    @property
    def filename(self) -> str:
        return f"amazon_pqa_{self.leaf}.json"


# Order is the order of `data-card.md` §1's table, and the order everything is written in.
# bytes and sha256: data-card.md §1 (checked by test_pinned_sources_equal_the_data_card).
# department: ADR-002 (checked against the data-card department table).
# parsed .. prose_median_chars: probe_results.json (checked by test_pinned_counts_equal_the_probe_results).
LEAVES: tuple[LeafSpec, ...] = (
    LeafSpec(
        leaf="unlocked_cell_phones",
        department="phones",
        bytes=821_444_488,
        sha256="007178b847b2fb2b3bbdee7a79982dfcf7c51818f7cc909c5b4b5381c249424c",
        parsed=499_535,
        products=15_298,
        skipped_total=4,
        question_type={"yes-no": 282_910, "WH": 216_625},
        answer_aggregated={
            "yes": 136_380,
            "N/A": 216_625,
            "no": 37_112,
            "neutral": 109_418,
        },
        prose_median_chars=782,
    ),
    LeafSpec(
        leaf="traditional_laptops",
        department="laptops",
        bytes=403_702_059,
        sha256="86452e67a51d029d8ff7419b2f4fe3037c2a1fcf27a2de199d859e35bf098b5f",
        parsed=291_896,
        products=19_742,
        skipped_total=0,
        question_type={"WH": 129_157, "yes-no": 162_739},
        answer_aggregated={
            "N/A": 129_157,
            "neutral": 64_594,
            "yes": 64_087,
            "no": 34_058,
        },
        prose_median_chars=749,
    ),
    LeafSpec(
        leaf="led_&_lcd_tvs",
        department="electronics",
        bytes=178_273_635,
        sha256="bd8e9530c3ae2b678fd773c612e612770ce7b601b3b340d38f468767861622f1",
        parsed=137_881,
        products=3_970,
        skipped_total=0,
        question_type={"yes-no": 70_023, "WH": 67_858},
        answer_aggregated={
            "neutral": 32_878,
            "no": 10_917,
            "N/A": 67_858,
            "yes": 26_228,
        },
        prose_median_chars=413,
    ),
    LeafSpec(
        leaf="over-ear_headphones",
        department="electronics",
        bytes=278_531_682,
        sha256="b784c7e144257dbc1eb77e76ab46aaaba786d73280b533701a2314860344b320",
        parsed=139_146,
        products=6_605,
        skipped_total=0,
        question_type={"yes-no": 73_432, "WH": 65_714},
        answer_aggregated={
            "neutral": 35_245,
            "yes": 26_609,
            "N/A": 65_714,
            "no": 11_578,
        },
        prose_median_chars=957,
    ),
    LeafSpec(
        leaf="chairs",
        department="furniture",
        bytes=138_252_584,
        sha256="b015bea4871be949d5ca332a605fb0b1f1ebba5d89a903e277a857b1567b73c0",
        parsed=88_268,
        products=19_193,
        skipped_total=0,
        question_type={"WH": 56_312, "yes-no": 31_956},
        answer_aggregated={"N/A": 56_312, "yes": 8_675, "neutral": 15_937, "no": 7_344},
        prose_median_chars=517,
    ),
    LeafSpec(
        leaf="home_office_desks",
        department="furniture",
        bytes=95_549_762,
        sha256="2d89b15fc9c592539a4af9f4806517896e04594c7333ffdd68e5418a34fcba74",
        parsed=55_303,
        products=6_986,
        skipped_total=0,
        question_type={"WH": 32_101, "yes-no": 23_202},
        answer_aggregated={"N/A": 32_101, "neutral": 11_634, "yes": 7_250, "no": 4_318},
        prose_median_chars=672,
    ),
)


# =================================================================================================
# Parsing: one leaf, as a stream of bytes lines
# =================================================================================================
@dataclass
class LeafStats:
    """Everything counted while parsing one leaf. Counted, never inferred."""

    lines_read: int = 0
    parsed: int = 0
    products: int = 0
    skipped: Counter = field(default_factory=Counter)
    key_census: Counter = field(
        default_factory=Counter
    )  # every key of every JSON object line
    field_nonempty: Counter = field(default_factory=Counter)  # over parsed records
    question_type: Counter = field(default_factory=Counter)
    answer_aggregated: Counter = field(default_factory=Counter)
    bad_type: Counter = field(
        default_factory=Counter
    )  # a value of the wrong type, by field
    answers_bad: int = 0  # answers entries without a string answer_text, dropped
    prose_conflicts: int = 0  # asins whose product fields differ between records
    duplicate_question_ids: int = 0
    surrogate_replacements: int = 0

    @property
    def skipped_total(self) -> int:
        return sum(self.skipped.values())


@dataclass
class LeafResult:
    products: dict[str, dict]
    stats: LeafStats


# Fields read as plain strings. asin and question_text are validated first; answers is a list.
_TEXT_FIELDS = tuple(
    f for f in REAL_FIELDS if f not in ("asin", "question_text", "answers")
)


def _clean(text: str, stats: LeafStats) -> str:
    cleaned, n = _LONE_SURROGATE.subn(REPLACEMENT, text)
    stats.surrogate_replacements += n
    return cleaned


def _text_field(obj: dict, name: str, stats: LeafStats) -> str:
    """A string field, cleaned. Absent or null gives "". A wrong type gives "" and is COUNTED:
    str() on a list would put "['a']" into the prose with no error (D12)."""
    value = obj.get(name)
    if value is None:
        return ""
    if not isinstance(value, str):
        stats.bad_type[name] += 1
        return ""
    return _clean(value, stats)


def _answers(obj: dict, stats: LeafStats) -> list[str]:
    value = obj.get("answers")
    if value is None:
        return []
    if not isinstance(value, list):
        stats.bad_type["answers"] += 1
        return []
    out = []
    for item in value:
        text = item.get("answer_text") if isinstance(item, dict) else None
        if isinstance(text, str):
            out.append(_clean(text, stats))
        else:
            stats.answers_bad += 1
    return out


def parse_leaf(lines: Iterable[bytes]) -> LeafResult:
    """Parse one leaf. Pure: no file, no network, no clock. This is the test seam.

    `lines` must be bytes lines split on b"\\n" only, which is what iterating a file opened in
    binary mode gives. str.splitlines() would split a valid JSON line that holds U+2028 into two
    silent bad_json skips.

    Product fields come from the FIRST PARSED record of an asin, not the first line. A later record
    of the same asin with different product fields is counted in `prose_conflicts`, not hidden.
    """
    stats = LeafStats()
    products: dict[str, dict] = {}
    conflicted: set[str] = set()
    seen_question_ids: set[str] = set()

    for line_no, raw in enumerate(lines, start=1):
        stats.lines_read += 1
        if not raw.strip():
            stats.skipped[BLANK_LINE] += 1
            continue
        try:
            obj = json.loads(raw)
        except ValueError:  # JSONDecodeError, and UnicodeDecodeError for invalid UTF-8
            stats.skipped[BAD_JSON] += 1
            continue
        if not isinstance(obj, dict):
            stats.skipped[NOT_OBJECT] += 1
            continue
        stats.key_census.update(obj.keys())

        asin = obj.get("asin")
        if not isinstance(asin, str) or not asin:
            stats.skipped[MISSING_ASIN] += 1
            continue
        question = obj.get("question_text")
        if not isinstance(question, str) or not question.strip():
            stats.skipped[BAD_QUESTION_TEXT] += 1
            continue

        stats.parsed += 1
        text = {name: _text_field(obj, name, stats) for name in _TEXT_FIELDS}
        text["asin"] = _clean(asin, stats)
        text["question_text"] = _clean(question, stats)
        answers = _answers(obj, stats)
        for name in REAL_FIELDS:
            present = bool(answers) if name == "answers" else bool(text[name].strip())
            if present:
                stats.field_nonempty[name] += 1
        stats.question_type[text["question_type"]] += 1
        stats.answer_aggregated[text["answer_aggregated"]] += 1

        question_id = text["question_id"]
        if question_id:
            if question_id in seen_question_ids:
                stats.duplicate_question_ids += 1
            else:
                seen_question_ids.add(question_id)

        asin = text["asin"]
        fields = {
            "item_name": text["item_name"],
            "brand_name": text["brand_name"],
            "bullets": [text[f] for f in BULLET_FIELDS],
            "product_description": text["product_description"],
        }
        product = products.get(asin)
        if product is None:
            product = {"asin": asin, **fields, "questions": []}
            products[asin] = product
        elif any(product[k] != v for k, v in fields.items()):
            conflicted.add(asin)
        product["questions"].append(
            {
                "line_no": line_no,
                "question_id": question_id,
                "question_text": text["question_text"],
                "question_type": text["question_type"],
                "answer_aggregated": text["answer_aggregated"],
                "answers": answers,
            }
        )

    stats.products = len(products)
    stats.prose_conflicts = len(conflicted)
    if stats.lines_read != stats.parsed + stats.skipped_total:
        raise RuntimeError(
            f"line accounting broke: {stats.lines_read} read, {stats.parsed} parsed, "
            f"{stats.skipped_total} skipped"
        )
    return LeafResult(products=products, stats=stats)


# =================================================================================================
# Stops 1, 2 and 3 (input pins)
# =================================================================================================
def unknown_keys(stats: LeafStats) -> dict[str, int]:
    """Keys seen that are not real fields, with counts. Whether one is allowed is check_leaf's call."""
    return {k: n for k, n in sorted(stats.key_census.items()) if k not in REAL_FIELDS}


def check_leaf(
    stats: LeafStats, spec: LeafSpec, ignored_keys: dict[str, str] | None = None
) -> list[str]:
    """Return the reasons to stop, in stop order. An empty list means the leaf passed.

    Stop 1 and Stop 2 return as soon as they fail, so the first message is the first stop that
    tripped. Stop 3 here is the INPUT pins; the output pins need the written file (summarise_interim).
    """
    ignored = IGNORED_KEYS if ignored_keys is None else ignored_keys
    unexpected = sorted(
        ((k, n) for k, n in unknown_keys(stats).items() if k not in ignored),
        key=lambda kn: (-kn[1], kn[0]),
    )

    if stats.parsed == 0:
        missing = [f for f in REAL_FIELDS if stats.key_census[f] == 0]
        seen = ", ".join(f"{k!r} x{n}" for k, n in unexpected[:5]) or "none"
        message = (
            f"Stop 1: {spec.leaf}: 0 of {stats.lines_read} lines parsed. Real fields found in no "
            f"record: {missing}. Keys seen instead: {seen}. The dataset readme names fields the "
            f"data does not use; the builder reads the bytes' names."
        )
        return [message]

    failures = []
    for name in REAL_FIELDS:
        if stats.field_nonempty[name] == 0:
            where = (
                "is empty"
                if stats.key_census[name]
                else "never appears (the key is absent)"
            )
            failures.append(
                f"Stop 2: {spec.leaf}: field {name!r} {where} in all {stats.parsed:,} parsed records."
            )
    for key, n in unexpected:
        failures.append(
            f"Stop 2: {spec.leaf}: key {key!r} appears in {n:,} records but is not a real field and "
            f"not in IGNORED_KEYS. Add it to REAL_FIELDS or to IGNORED_KEYS, with a reason."
        )
    if failures:
        return failures

    for what, got, want in (
        ("records parsed", stats.parsed, spec.parsed),
        ("products", stats.products, spec.products),
        ("records skipped", stats.skipped_total, spec.skipped_total),
    ):
        if got != want:
            failures.append(
                f"Stop 3: {spec.leaf}: {what} = {got:,}, pinned {want:,}. The parser disagrees with "
                f"the 2026-10-03 probe that wrote the pin."
            )
    return failures


# =================================================================================================
# Stop 0: the source file
# =================================================================================================
class SourceMismatch(Exception):
    """A source file is missing, short, or not the pinned bytes. Nothing has been parsed yet."""


_BLOCK = 1 << 20  # 1 MiB: the biggest leaf is 821 MB and is never held in memory


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_source(path: Path, spec: LeafSpec) -> None:
    """Size first (cheap, and it tells a partial download from a corrupt file), then sha256.

    Always re-hashes: size + mtime would be a shortcut that fails silently, and 1.9 GB hashes in
    well under a minute (D8).
    """
    if not path.is_file():
        raise SourceMismatch(
            f"Stop 0: {spec.leaf}: {path} is missing. Run `make pqa-fetch`."
        )
    size = path.stat().st_size
    if size < spec.bytes:
        raise SourceMismatch(
            f"Stop 0: {spec.leaf}: {path.name} is {size:,} bytes, pinned {spec.bytes:,}. "
            f"That is a partial download: run `make pqa-fetch` again, it will resume."
        )
    if size > spec.bytes:
        raise SourceMismatch(
            f"Stop 0: {spec.leaf}: {path.name} is {size:,} bytes, pinned {spec.bytes:,}. "
            f"It is longer than the pinned file: delete it and run `make pqa-fetch`."
        )
    digest = sha256_file(path)
    if digest != spec.sha256:
        raise SourceMismatch(
            f"Stop 0: {spec.leaf}: {path.name} has the pinned size but its sha256 is {digest}, "
            f"pinned {spec.sha256}. The file is corrupt or changed: delete it and run "
            f"`make pqa-fetch` (curl cannot repair a full-size bad file)."
        )


# =================================================================================================
# The writer, and Stop 3's output pins
# =================================================================================================
def _digest(value: object) -> str:
    """sha256 of the canonical JSON of a value. The same call on a parsed product and on a line read
    back from the interim file gives the same digest only if every field is equal."""
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class InterimInfo:
    path: Path
    bytes: int
    sha256: str
    # asin -> digest of the product taken BEFORE product_line runs. A writer that edits the shared
    # lists in place (a .sort(), a .pop()) would otherwise change what it is compared with.
    digests: dict[str, str] = field(default_factory=dict, compare=False, repr=False)


def product_line(product: dict, spec: LeafSpec) -> dict:
    """One interim line. `leaf` and `department` are metadata for 3.2: the leaf must never become
    the `category` of a product record or reach text that is embedded."""
    return {
        "asin": product["asin"],
        "leaf": spec.leaf,
        "department": spec.department,
        "item_name": product["item_name"],
        "brand_name": product["brand_name"],
        "bullets": product["bullets"],
        "product_description": product["product_description"],
        "questions": product["questions"],
    }


def write_interim(
    products: dict[str, dict], spec: LeafSpec, directory: Path
) -> InterimInfo:
    """Write one leaf, line by line, through a hashing writer. Sorted by asin, so the bytes do not
    depend on file order or on the hash seed.

    ensure_ascii=False keeps a missed lone surrogate loud: it raises here instead of being written
    as an escape and failing later in `make ingest`.
    """
    path = directory / f"{spec.leaf}.jsonl"
    digest = hashlib.sha256()
    digests: dict[str, str] = {}
    size = 0
    with path.open("wb") as f:
        for asin in sorted(products):
            digests[asin] = _digest(products[asin])
            line = json.dumps(
                product_line(products[asin], spec),
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            data = (line + "\n").encode("utf-8")
            f.write(data)
            digest.update(data)
            size += len(data)
    return InterimInfo(
        path=path, bytes=size, sha256=digest.hexdigest(), digests=digests
    )


@dataclass(frozen=True)
class InterimSummary:
    products: int
    questions: int
    question_type: dict[str, int]
    answer_aggregated: dict[str, int]
    prose_median_chars: int


def summarise_interim(path: Path) -> InterimSummary:
    """Re-read the interim file AS WRITTEN and count it again, independently of the parser's stats.

    This is the only check on what comes out. Stops 1 and 2 read the source, so a writer that drops
    `bullet_point5` from every product passes them.

    prose_median_chars uses the probe's definition: the five bullets and the description, each
    stripped, joined by one space, stripped; the upper median of the lengths.
    """
    question_type: Counter = Counter()
    answer_aggregated: Counter = Counter()
    lengths: list[int] = []
    questions = 0
    with path.open("rb") as f:
        for raw in f:
            line = json.loads(raw)
            prose = " ".join(
                s.strip() for s in (*line["bullets"], line["product_description"])
            )
            lengths.append(len(prose.strip()))
            for q in line["questions"]:
                questions += 1
                question_type[q["question_type"]] += 1
                answer_aggregated[q["answer_aggregated"]] += 1
    lengths.sort()
    return InterimSummary(
        products=len(lengths),
        questions=questions,
        question_type=dict(question_type),
        answer_aggregated=dict(answer_aggregated),
        prose_median_chars=lengths[len(lengths) // 2] if lengths else 0,
    )


def check_output(summary: InterimSummary, spec: LeafSpec) -> list[str]:
    """Stop 3, output side: the written file must match the pins. Empty list = pass."""
    failures = []
    for what, got, want in (
        ("products", summary.products, spec.products),
        ("questions", summary.questions, spec.parsed),
        ("question_type counts", summary.question_type, spec.question_type),
        ("answer_aggregated counts", summary.answer_aggregated, spec.answer_aggregated),
        ("prose_median_chars", summary.prose_median_chars, spec.prose_median_chars),
    ):
        if got != want:
            failures.append(
                f"Stop 3: {spec.leaf}: the interim file as written has {what} = {got}, pinned "
                f"{want}. The writer drops, swaps or changes a field."
            )
    return failures


def check_round_trip(info: InterimInfo, spec: LeafSpec) -> list[str]:
    """Stop 3, output side, FIELD BY FIELD: every line of the written file must equal the product the
    parser built, and every product must be there exactly once. Empty list = pass.

    The aggregate pins in check_output see counts and a median. They cannot see a writer that swaps
    item_name and brand_name, blanks a field, keeps one answer of two, or shifts a line number: each
    keeps every aggregate intact. This compares every value, against a digest taken BEFORE the writer
    ran. Messages name a line number, never a value (a value is PQA text).
    """

    def fail(detail: str) -> list[str]:
        message = (
            f"Stop 3: {spec.leaf}: the interim file as written differs from what was parsed: "
            f"{detail}. The writer drops, swaps or changes a field."
        )
        return [message]

    seen: set[str] = set()
    with info.path.open("rb") as f:
        for number, raw in enumerate(f, start=1):
            line = json.loads(raw)
            if (line.pop("leaf", None), line.pop("department", None)) != (
                spec.leaf,
                spec.department,
            ):
                return fail(f"line {number} has the wrong leaf or department")
            asin = line.get("asin")
            if asin not in info.digests:
                return fail(f"line {number} holds an asin that was never parsed")
            if asin in seen:
                return fail(f"line {number} repeats an asin")
            if _digest(line) != info.digests[asin]:
                return fail(f"line {number} has a field that differs")
            seen.add(asin)
    if len(seen) != len(info.digests):
        return fail(f"{len(info.digests) - len(seen)} parsed product(s) are missing")
    return []


# =================================================================================================
# The manifest
# =================================================================================================
class StopError(Exception):
    """One or more stops tripped. `failures` are the messages, in stop order."""

    def __init__(self, failures: list[str]):
        super().__init__("\n".join(failures))
        self.failures = failures


def source_entry(spec: LeafSpec) -> dict:
    return {
        "leaf": spec.leaf,
        "department": spec.department,
        "file": spec.filename,
        "url": f"{BASE_URL}/{quote(spec.filename)}",  # the & in led_&_lcd_tvs becomes %26
        "bytes": spec.bytes,
        "sha256": spec.sha256,
    }


def leaf_entry(stats: LeafStats, info: InterimInfo, summary: InterimSummary) -> dict:
    """Counts only. Every value is a number, a name or a digest: never PQA text."""
    return {
        "lines_read": stats.lines_read,
        "records_parsed": stats.parsed,
        "skipped": {reason: stats.skipped[reason] for reason in SKIP_REASONS},
        "products": stats.products,
        "questions": stats.parsed,  # records, not distinct question_ids (see duplicate_question_ids)
        "field_nonempty": {name: stats.field_nonempty[name] for name in REAL_FIELDS},
        "unknown_keys": unknown_keys(
            stats
        ),  # only IGNORED_KEYS can be here: others stop the run
        "question_type": dict(sorted(stats.question_type.items())),
        "answer_aggregated": dict(sorted(stats.answer_aggregated.items())),
        "bad_type": dict(sorted(stats.bad_type.items())),
        "answers_bad": stats.answers_bad,
        "prose_conflicts": stats.prose_conflicts,
        "duplicate_question_ids": stats.duplicate_question_ids,
        "surrogate_replacements": stats.surrogate_replacements,
        "prose_median_chars": summary.prose_median_chars,
        "interim_file": info.path.name,
        "interim_bytes": info.bytes,
        "interim_sha256": info.sha256,
    }


def build_manifest(
    leaves: tuple[LeafSpec, ...],
    entries: dict[str, dict],
    asins: dict[str, frozenset[str]],
) -> dict:
    """Hashes and counts. Nothing in it depends on time, host, or hash seed."""
    cross_leaf = {}
    for i, a in enumerate(leaves):
        for b in leaves[i + 1 :]:
            cross_leaf[f"{a.leaf}|{b.leaf}"] = len(asins[a.leaf] & asins[b.leaf])
    union = set().union(*asins.values()) if asins else set()
    return {
        "manifest_version": MANIFEST_VERSION,
        "stage": "3.1-interim",
        "note": MANIFEST_NOTE,
        "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "sources": [source_entry(spec) for spec in leaves],
        "leaves": {spec.leaf: entries[spec.leaf] for spec in leaves},
        "cross_leaf": cross_leaf,  # counts only, never lists of asins
        "totals": {
            "questions": sum(e["questions"] for e in entries.values()),
            # A sum of per-leaf distinct asins; a product listed in two leaves counts twice.
            "products_sum_of_leaf_distinct": sum(
                e["products"] for e in entries.values()
            ),
            "products_distinct_across_leaves": len(union),
        },
    }


def manifest_bytes(manifest: dict) -> bytes:
    text = json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False)
    return (text + "\n").encode("utf-8")


# =================================================================================================
# Build: all six leaves are checked and written to a temp directory before anything is published
# =================================================================================================
def _warn_about_stale_product_files(parent: Path) -> None:
    """The retired fetch script left product-*.json from the WRONG dataset (Amazon-Reviews-2023) in
    data/v1-draft/. They have a valid product- prefix and doc_id == filename, so ingestion and gate G4
    would accept them. Say so on every build until someone removes them."""
    stale = sorted(parent.glob("product-*.json")) if parent.is_dir() else []
    if stale:
        print(
            f"WARNING: {len(stale)} stale product-*.json in {parent} from the retired fetch script "
            f"(wrong dataset, Amazon-Reviews-2023). They are not the corpus: do not copy, freeze or "
            f"ingest them.",
            file=sys.stderr,
        )


def _remove_stale(parent: Path) -> None:
    """Remove temp directories a crashed run left behind. They are derived and rebuildable."""
    if not parent.is_dir():
        return
    for child in sorted(parent.iterdir()):
        if child.name.startswith((".pqa-build-", ".pqa-old-")):
            print(
                f"removing the leftover of a crashed run: {child.name}", file=sys.stderr
            )
            shutil.rmtree(child, ignore_errors=True)


def publish(work: Path, interim_dir: Path, manifest_path: Path) -> None:
    """Swap the new interim directory in and write the manifest LAST.

    Several renames are not atomic together, so a failure part-way rolls back: the interim files and
    the manifest must still be a matching pair, old or new, never one of each. If the process is
    killed between renames the pair can disagree, and `--verify` and `iter_interim` catch that by
    hashing before they trust a file.
    """
    old = interim_dir.with_name(f".pqa-old-{os.getpid()}")
    moved_old = moved_new = False
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if interim_dir.exists():
            os.replace(interim_dir, old)
            moved_old = True
        os.replace(work / "interim", interim_dir)
        moved_new = True
        os.replace(work / "manifest.json", manifest_path)  # LAST
    except BaseException:
        if moved_new:
            os.replace(interim_dir, work / "interim")
        if moved_old:
            os.replace(old, interim_dir)
        raise
    shutil.rmtree(old, ignore_errors=True)


def print_report(
    leaves: tuple[LeafSpec, ...], entries: dict[str, dict], manifest: dict
) -> None:
    """The counts a human should look at on every build. Reported, never hidden, never a failure."""
    print()
    print(
        f"{'leaf':<22}{'prose_conflicts':>16}{'duplicate_qids':>16}{'surrogates':>12}"
        f"{'bad_type':>10}{'answers_bad':>13}"
    )
    for spec in leaves:
        e = entries[spec.leaf]
        print(
            f"{spec.leaf:<22}{e['prose_conflicts']:>16,}{e['duplicate_question_ids']:>16,}"
            f"{e['surrogate_replacements']:>12,}{sum(e['bad_type'].values()):>10,}"
            f"{e['answers_bad']:>13,}"
        )
    for spec in leaves:
        reasons = {r: n for r, n in entries[spec.leaf]["skipped"].items() if n}
        if reasons:
            print(
                f"skipped, {spec.leaf}: "
                + ", ".join(f"{r} {n:,}" for r, n in reasons.items())
            )
    shared = {pair: n for pair, n in manifest["cross_leaf"].items() if n}
    print(
        "asins shared between leaves: "
        + (", ".join(f"{k}: {n:,}" for k, n in shared.items()) or "none")
    )
    t = manifest["totals"]
    print(
        f"totals: questions {t['questions']:,}, products {t['products_sum_of_leaf_distinct']:,} "
        f"(sum of leaf distinct), {t['products_distinct_across_leaves']:,} distinct across leaves"
    )


def build(
    leaves: tuple[LeafSpec, ...],
    raw_dir: Path,
    interim_dir: Path,
    manifest_path: Path,
    ignored_keys: dict[str, str] | None = None,
) -> int:
    """Run Stops 0 to 3 on every leaf, then publish. Returns 0, or 2 if a stop tripped.

    Any other exception propagates, so the process exits non-zero (D7): a wrapper that trusts
    exit 0 must never accept an empty or half-built run.
    """
    work = interim_dir.parent / f".pqa-build-{os.getpid()}"
    _remove_stale(interim_dir.parent)
    _warn_about_stale_product_files(interim_dir.parent)
    (work / "interim").mkdir(parents=True)
    try:
        entries: dict[str, dict] = {}
        asins: dict[str, frozenset[str]] = {}
        print(f"{'leaf':<22}{'lines':>10}{'parsed':>10}{'skipped':>9}{'products':>10}")
        # Stop 0 for EVERY source before any parsing: a bad sixth file must not cost five parses.
        for spec in leaves:
            verify_source(raw_dir / spec.filename, spec)
        for spec in leaves:
            path = raw_dir / spec.filename
            with path.open("rb") as f:
                result = parse_leaf(f)  # bytes lines
            # Stops 1 and 2, then the Stop 3 pins on the input.
            failures = check_leaf(result.stats, spec, ignored_keys)
            if failures:
                raise StopError(failures)
            info = write_interim(result.products, spec, work / "interim")
            summary = summarise_interim(info.path)
            # Stop 3 on what was WRITTEN: the aggregate pins, then every field against the parse.
            failures = check_output(summary, spec)
            failures += check_round_trip(info, spec)
            if failures:
                raise StopError(failures)
            s = result.stats
            print(
                f"{spec.leaf:<22}{s.lines_read:>10,}{s.parsed:>10,}{s.skipped_total:>9,}"
                f"{s.products:>10,}"
            )
            entries[spec.leaf] = leaf_entry(s, info, summary)
            asins[spec.leaf] = frozenset(result.products)
            del result
        manifest = build_manifest(leaves, entries, asins)
        print_report(leaves, entries, manifest)
        data = manifest_bytes(manifest)
        (work / "manifest.json").write_bytes(data)
        publish(work, interim_dir, manifest_path)
        # Item 3.2 records the hash of the manifest it consumed; two builds can be compared by it.
        print(f"manifest sha256: {hashlib.sha256(data).hexdigest()}")
    except (SourceMismatch, StopError) as error:
        print(str(error), file=sys.stderr)
        print("Nothing was written under a final name.", file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(work, ignore_errors=True)
    # ru_maxrss is bytes on macOS and kilobytes on Linux. Stderr only: never in the manifest.
    print(
        f"peak RSS (ru_maxrss, raw units): {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss:,}",
        file=sys.stderr,
    )
    return 0


# =================================================================================================
# The reader, and --verify: nothing is trusted until it has been hashed
# =================================================================================================
class ManifestError(Exception):
    """The manifest is missing, unreadable, or not a 3.1 manifest."""


class InterimMismatch(Exception):
    """An interim file is missing, cut short, or not the bytes the manifest names."""


def load_manifest(path: Path) -> dict:
    if not path.is_file():
        raise ManifestError(f"{path} does not exist. Run `make pqa-build`.")
    try:
        manifest = json.loads(path.read_bytes())
    except ValueError as error:
        raise ManifestError(
            f"{path} is not valid JSON ({error}). Run `make pqa-build`."
        ) from error
    if not isinstance(manifest, dict) or manifest.get("stage") != "3.1-interim":
        raise ManifestError(
            f"{path} is not a 3.1 interim manifest (stage != '3.1-interim')."
        )
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ManifestError(
            f"{path} has manifest_version {manifest.get('manifest_version')!r}, this builder "
            f"reads {MANIFEST_VERSION}. Run `make pqa-build`."
        )
    return manifest


def verify_interim(manifest: dict, interim_dir: Path) -> None:
    """Hash EVERY interim file the manifest names. A crash between renames, or an older manifest
    restored by git (the interim files are gitignored), leaves the two out of step; this is what
    notices."""
    for leaf, entry in manifest["leaves"].items():
        path = interim_dir / entry["interim_file"]
        if not path.is_file():
            raise InterimMismatch(
                f"{leaf}: interim file {path} is missing. Run `make pqa-build`."
            )
        size = path.stat().st_size
        if size != entry["interim_bytes"]:
            raise InterimMismatch(
                f"{leaf}: {path.name} is {size:,} bytes, the manifest says "
                f"{entry['interim_bytes']:,}. Run `make pqa-build`."
            )
        if sha256_file(path) != entry["interim_sha256"]:
            raise InterimMismatch(
                f"{leaf}: {path.name} has the right size but its sha256 differs from the "
                f"manifest's. Run `make pqa-build`."
            )


def iter_interim(manifest_path: Path, interim_dir: Path) -> Iterator[tuple[str, dict]]:
    """The only sanctioned reader of the interim files (D14). Yields (leaf, product line).

    It walks the manifest's file list and never globs, so a stray file cannot get in. All files are
    hashed on the first next(), before any line is yielded: a changed file raises before 3.2 has
    consumed anything.
    """
    manifest = load_manifest(manifest_path)
    verify_interim(manifest, interim_dir)
    for source in manifest["sources"]:
        leaf = source["leaf"]
        with (interim_dir / manifest["leaves"][leaf]["interim_file"]).open("rb") as f:
            for raw in f:
                yield leaf, json.loads(raw)


def verify(manifest_path: Path, raw_dir: Path, interim_dir: Path) -> int:
    """Offline, no parsing: hash the raw files and the interim files on disk against the manifest."""
    try:
        manifest = load_manifest(manifest_path)
        for source in manifest["sources"]:
            pinned = LeafSpec(
                leaf=source["leaf"],
                department=source["department"],
                bytes=source["bytes"],
                sha256=source["sha256"],
                parsed=0,
                products=0,
                skipped_total=0,
            )
            verify_source(raw_dir / source["file"], pinned)
        verify_interim(manifest, interim_dir)
    except (ManifestError, SourceMismatch, InterimMismatch) as error:
        print(str(error), file=sys.stderr)
        return 2
    here = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if manifest["builder_sha256"] != here:
        print(
            "warning: builder_sha256 in the manifest differs from this script. A CRLF checkout or a "
            "reformat does this; a real change to the builder does too. Read the git diff.",
            file=sys.stderr,
        )
    n = len(manifest["sources"])
    print(
        f"verified: {n} source files and {n} interim files match {manifest_path.name}"
    )
    print(f"manifest sha256: {hashlib.sha256(manifest_path.read_bytes()).hexdigest()}")
    return 0


# =================================================================================================
# Command line
# =================================================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Amazon-PQA builder (super-plan item 3.1). Use `make pqa-build` / `pqa-verify`."
    )
    parser.add_argument(
        "--verify", action="store_true", help="offline: hash files against the manifest"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print 'file url bytes' per source (for make)",
    )
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--interim-dir", type=Path, default=INTERIM_DIR)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    args = parser.parse_args(argv)

    if args.list:
        for spec in LEAVES:
            print(spec.filename, source_entry(spec)["url"], spec.bytes)
        return 0
    if args.verify:
        return verify(args.manifest, args.raw_dir, args.interim_dir)
    return build(LEAVES, args.raw_dir, args.interim_dir, args.manifest)


if __name__ == "__main__":
    sys.exit(main())
