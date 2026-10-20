"""Select into the thick tail of Amazon-PQA — super-plan item 3.2.

Reads the 3.1 interim files ONLY through `build_pqa.iter_interim`, applies one pre-registered
selection rule, draws 152 products (38 per department), and writes:

    data/v1-draft/products/product-{department}-{asin}.json   gitignored, the shape rag.ingest reads
    data/v1-draft/question-pool.jsonl                          gitignored, every kept question, tagged
    data/v1-draft/generic-tokens.json                          gitignored, each leaf's common title words
    data/pqa-selection.json                                    TRACKED: counts and digests only

    make pqa-select         # select, then print the report
    make pqa-audit-sheet    # the blind audit sheet (gitignored)
    make pqa-audit-score    # score the marked sheet into the task trail

The design, with the reason for every rule and constant, is
docs/work/2026-10-19-pqa-thick-tail-selection/design.md. In short:

* A question is dropped (price, stock, carrier), or tagged `policy` (return, warranty: answered by
  the authored documents of item 3.3), or tagged `spec`, answerable or not from the product's own
  record by rule R2: the share of the question's content words found in the record, after the
  words common to the leaf's titles are removed, is at least one half. R1, the same without that
  removal, is reported beside it and never selects.
* A product is eligible when it passes the funnel of `STEPS`. Inside each leaf the eligible asins
  are ranked by sha256(seed:asin) and the first `QUOTA[leaf]` are taken. A short leaf stops the run:
  only the author applies the pre-registered fallback (design §2.3).
* The probe's own two pool rules are counted on the same pass and must equal `PROBE_PINS`, so the
  copied filters are shown to act like the 2026-10-03 probe on the real bytes.

Every stop ends the run with exit code 2 and leaves nothing under a final name. Nothing here prints
or records PQA text in a tracked place: the manifest is checked against an allow-list in the tests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import build_pqa

REPO_ROOT = build_pqa.REPO_ROOT
DRAFT_DIR = REPO_ROOT / "data" / "v1-draft"  # gitignored
SELECTION_PATH = REPO_ROOT / "data" / "pqa-selection.json"  # TRACKED: counts and digests only
PRODUCTS = "products"
POOL = "question-pool.jsonl"
GENERIC = "generic-tokens.json"
AUDIT_SHEET = Path("audit") / "sheet.csv"  # under the draft directory, so gitignored
STAGE = "3.2-selection"
SELECTION_VERSION = 1
NOTE = "Item 3.2's draft corpus. It is not the v1 snapshot digest (item 3.6)."
TEMP_PREFIX = ".pqa-select-"  # never .pqa-build- or .pqa-old-, which are 3.1's

# --- Copied from docs/work/2026-10-03-pqa-category-choice/probe.py ("probe" in design §2) --------
# Copied, not imported: the probe is scratch in a task trail. A test reads that file and asserts
# every value below is equal, so the copy cannot drift.
ND_LO, ND_HI = 0.45, 0.99
PAIR_CAP = 100
# STOP is the probe's word list, verbatim; T12 compares the two sets.
STOP = set(
    """
a an the this that these those it its it's is are was were be been being am do does did done doing
will would can could should shall may might must have has had having i me my we our you your he she
they them their there here what which who whom whose when where why how if then than so too very
just only also of in on at to for from by with about as into onto over under up down out off and or
but not no nor any some all each both either neither other such own same more most less few much
many get got gets getting one ones s t
""".split()  # noqa: SIM905
)
POLICY_Q = {
    "warranty": re.compile(r"\bwarrant(y|ies|ee)\b", re.IGNORECASE),
    "return": re.compile(r"\b(return(ed|s|ing)?|refund(ed)?|restock(ing)?)\b", re.IGNORECASE),
}
DYNAMIC_Q = re.compile(
    r"\$\s?\d|\bprices?\b|\bpriced\b|\bcost(s|ing)?\b|\bhow much (is|for|are|does it cost)\b"
    r"|\b(in|out of|back in) stock\b|\bsold out\b|\bon sale\b|\bdiscount|\bcoupon",
    re.IGNORECASE,
)
CARRIER_Q = re.compile(
    r"\b(verizon|at ?& ?t|att|t-?mobile|sprint|cricket|metro ?pcs|straight ?talk|boost|tracfone"
    r"|carrier|unlock(ed|ing)?|sim)\b",
    re.IGNORECASE,
)
CAP_LO, CAP_HI = 5, 50
WARRANTY_TERM = re.compile(
    r"(\d+|one|two|three|five|ten|lifetime)[- ]?(year|yr|month|day)s?[^.]{0,40}warrant"
    r"|warrant[^.]{0,40}?(\d+|one|two|three|five|ten|lifetime)[- ]?(year|yr|month|day)",
    re.IGNORECASE,
)
MIN_BULLETS = 3  # F17

# --- New in item 3.2, fixed before any run (design §2). A change needs a line in approvals.md --
COVERAGE = Fraction(1, 2)
GENERIC_DF = Fraction(1, 10)
MIN_ANSWERABLE = 5
DEPARTMENT_QUOTA = 38
QUOTA_PREREGISTERED = {
    "unlocked_cell_phones": 38,
    "traditional_laptops": 38,
    "led_&_lcd_tvs": 19,
    "over-ear_headphones": 19,
    "chairs": 19,
    "home_office_desks": 19,
}
# The short-leaf fallback (design §2.3), applied ONLY by the author, one step at a time. Step 1 was
# applied on 2026-10-20 after the first live run, in which led_&_lcd_tvs had 13 eligible products
# for a quota of 19 (evidence/live-run.md; approvals.md). The rule itself is unchanged.
FALLBACK_APPLIED = ("step 1: led_&_lcd_tvs gives its shortfall of 6 to over-ear_headphones",)
QUOTA = {
    **QUOTA_PREREGISTERED,
    "led_&_lcd_tvs": 13,
    "over-ear_headphones": 25,
}
SEED = "v1-item-3.2"
AUDIT_ANSWERABLE, AUDIT_UNANSWERABLE = 15, 10  # per department

# The probe's two pool rules, counted on the same pass (design §2.6). `capped` is
# probe_results.json's n_capped_nocarrier; `adr002` is ADR-002's table, re-derived by running
# example_product.py unchanged (docs/work/2026-10-19-pqa-thick-tail-selection/evidence/probe-pins.md).
PROBE_PINS = {
    "capped": {
        "unlocked_cell_phones": 2260,
        "traditional_laptops": 1742,
        "led_&_lcd_tvs": 350,
        "over-ear_headphones": 565,
        "chairs": 914,
        "home_office_desks": 410,
    },
    "adr002": {
        "unlocked_cell_phones": 1811,
        "traditional_laptops": 1312,
        "led_&_lcd_tvs": 302,
        "over-ear_headphones": 399,
        "chairs": 796,
        "home_office_desks": 339,
    },
}

# The funnel, in order (design §2.2). The first step a product fails is where it is counted.
STEPS = (
    "titled",
    "bullets",
    "no_warranty_term",
    "consistent",
    "cap",
    "answerable",
    "pair",
)
ASIN = re.compile(r"[A-Z0-9]{10}")
BUCKETS = ((0, 4), (5, 9), (10, 19), (20, 29), (30, 39), (40, 50))


class SelectionStop(Exception):
    """A stop: the run ends with exit code 2 and nothing is written under a final name."""


# =================================================================================================
# Tokens and tags
# =================================================================================================
def content_tokens(text: str) -> frozenset[str]:
    """The probe's tokenizer: [a-z0-9]+ in lower case, minus STOP, minus one-character tokens.

    It must not be used to label strata (design §2.1): "Windows 7" and "Windows 8" give the same set.
    """
    return frozenset(
        t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP and len(t) > 1
    )


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """The probe's definition, floats included, so the near-duplicate band acts exactly as there."""
    return len(a & b) / len(a | b) if a and b else 0.0


def prose(line: dict) -> str:
    """Bullets and description joined by one space, NOT stripped: example_product.py's join, which
    the `adr002` pins were counted with (design §2, review M5)."""
    return " ".join([*line["bullets"], line["product_description"]])


@dataclass(frozen=True)
class RecordTokens:
    title: frozenset[str]  # content_tokens(item_name)
    rest: frozenset[str]  # content_tokens(brand_name + prose)

    @property
    def all(self) -> frozenset[str]:
        return self.title | self.rest


def record_tokens(line: dict) -> RecordTokens:
    return RecordTokens(
        title=content_tokens(line["item_name"]),
        rest=content_tokens(line["brand_name"] + " " + prose(line)),
    )


@dataclass(frozen=True)
class Tag:
    kind: str  # "dynamic" | "carrier" | "policy" | "spec"
    policy_kinds: tuple[str, ...] = ()
    answerable: bool = False  # R2, the selecting rule
    answerable_r1: bool = False  # reported only
    q_tokens: int = 0  # |Q'|
    covered: int = 0  # |Q' ∩ R|
    title_only: bool = False  # R2-answerable, and no covered token is outside the title


def _covers(covered: int, total: int) -> bool:
    return total > 0 and Fraction(covered, total) >= COVERAGE


def tag(question_text: str, record: RecordTokens, generic: frozenset[str]) -> Tag:
    """Design §2.1. The first step that matches decides."""
    text = question_text.strip()
    if DYNAMIC_Q.search(text):
        return Tag("dynamic")
    if CARRIER_Q.search(text):
        return Tag("carrier")
    kinds = tuple(sorted(k for k, rx in POLICY_Q.items() if rx.search(text)))
    if kinds:
        return Tag("policy", policy_kinds=kinds)
    q = content_tokens(text)
    r = record.all
    q2 = q - generic
    covered = q2 & r
    answerable = _covers(len(covered), len(q2))
    return Tag(
        "spec",
        answerable=answerable,
        answerable_r1=_covers(len(q & r), len(q)),
        q_tokens=len(q2),
        covered=len(covered),
        title_only=answerable and not (covered & record.rest),
    )


# =================================================================================================
# The funnel and the probe's pools
# =================================================================================================
def has_near_duplicate_pair(token_sets: list[frozenset[str]]) -> bool:
    for i, t in enumerate(token_sets):
        for u in token_sets[i + 1 :]:
            if t != u and ND_LO <= jaccard(t, u) <= ND_HI:
                return True
    return False


@dataclass
class Evaluated:
    """One product after tagging: its kept questions with their tags and token sets."""

    line: dict
    kept: list[tuple[dict, Tag, frozenset[str]]]
    dropped: Counter
    failed: str | None  # the first funnel step it fails, or None if eligible

    @property
    def answerable(self) -> list[tuple[dict, Tag, frozenset[str]]]:
        return [k for k in self.kept if k[1].kind == "spec" and k[1].answerable]


def bullets_present(line: dict) -> int:
    return sum(1 for b in line["bullets"] if b.strip())


def first_failure(line: dict, kept: list[tuple[dict, Tag, frozenset[str]]]) -> str | None:
    """Design §2.2, in STEPS order. `fields_conflict` is read first, on every line, with no
    default: a line without it comes from an interim older than MANIFEST_VERSION 2 and must not
    read as consistent (review L4)."""
    conflict = line["fields_conflict"]
    if not isinstance(conflict, bool):
        raise SelectionStop(f"an interim line carries a non-boolean fields_conflict: {conflict!r}")
    if not line["item_name"].strip():
        return "titled"
    if bullets_present(line) < MIN_BULLETS:
        return "bullets"
    if WARRANTY_TERM.search(line["item_name"]) or WARRANTY_TERM.search(prose(line)):
        return "no_warranty_term"
    if conflict:
        return "consistent"
    if not CAP_LO <= len(kept) <= CAP_HI:
        return "cap"
    answerable = [k for k in kept if k[1].kind == "spec" and k[1].answerable]
    if len(answerable) < MIN_ANSWERABLE:
        return "answerable"
    if not has_near_duplicate_pair([k[2] for k in answerable]):
        return "pair"
    return None


def evaluate(line: dict, generic: frozenset[str]) -> Evaluated:
    tokens = record_tokens(line)
    kept = []
    dropped: Counter = Counter()
    for q in line["questions"]:
        t = tag(q["question_text"], tokens, generic)
        if t.kind in ("dynamic", "carrier"):
            dropped[t.kind] += 1
        else:
            kept.append((q, t, content_tokens(q["question_text"])))
    return Evaluated(line=line, kept=kept, dropped=dropped, failed=first_failure(line, kept))


def probe_pools(ev: Evaluated) -> tuple[bool, bool]:
    """The probe's own rules (design §2.6): `capped` and `adr002`. Kept = dynamic and carrier
    dropped, which is the probe's `keep`; the pair is among ALL kept questions."""
    capped = CAP_LO <= len(ev.kept) <= CAP_HI and has_near_duplicate_pair(
        [k[2] for k in ev.kept]
    )
    adr002 = (
        capped
        and bullets_present(ev.line) >= MIN_BULLETS
        and not WARRANTY_TERM.search(prose(ev.line))
    )
    return capped, adr002


# =================================================================================================
# Re-asks (design §2.4)
# =================================================================================================
@dataclass
class ReAsk:
    questions: int = 0
    clusters_exact: int = 0  # union-find over identical token sets only
    clusters_all: int = 0  # union-find over identical token sets OR the near-duplicate band
    digit_flips: int = 0  # identical token sets whose raw digit strings differ: value flips

    def add(self, texts: list[str]) -> None:
        n = len(texts)
        toks = [content_tokens(t) for t in texts]
        digits = [tuple(re.findall(r"\d+", t)) for t in texts]
        exact = list(range(n))
        every = list(range(n))

        def find(parent: list[int], i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(n):
            for j in range(i + 1, n):
                if toks[i] == toks[j]:
                    exact[find(exact, i)] = find(exact, j)
                    every[find(every, i)] = find(every, j)
                    if digits[i] != digits[j]:
                        self.digit_flips += 1
                elif ND_LO <= jaccard(toks[i], toks[j]) <= ND_HI:
                    every[find(every, i)] = find(every, j)
        self.questions += n
        self.clusters_exact += len({find(exact, i) for i in range(n)})
        self.clusters_all += len({find(every, i) for i in range(n)})

    def as_dict(self) -> dict:
        return {
            "questions": self.questions,
            "clusters_exact": self.clusters_exact,
            "clusters_all": self.clusters_all,
            "digit_flips": self.digit_flips,
        }


# =================================================================================================
# Records
# =================================================================================================
def specs_of(line: dict) -> dict[str, str]:
    """`Feature n` by source slot, then Description, then Brand. Insertion order IS the embedded
    order (rag.ingest.product_to_text renders specs in dict order), so it is never sorted."""
    specs: dict[str, str] = {}
    for slot, bullet in enumerate(line["bullets"], start=1):
        if bullet.strip():
            specs[f"Feature {slot}"] = bullet.strip()
    if line["product_description"].strip():
        specs["Description"] = line["product_description"].strip()
    if line["brand_name"].strip():
        specs["Brand"] = line["brand_name"].strip()
    return specs


def doc_id_of(line: dict) -> str:
    asin = line["asin"]
    if not ASIN.fullmatch(asin):
        raise SelectionStop(
            f"an asin does not match [A-Z0-9]{{10}} ({len(asin)} characters); it is refused "
            f"before it is lower-cased, so two asins can never merge into one doc_id"
        )
    return f"product-{line['department']}-{asin.lower()}"


def product_record(line: dict, doc_id: str | None = None) -> dict:
    """The shape rag.ingest.load_records reads. No leaf, and no `source_category`."""
    return {
        "doc_id": doc_id if doc_id is not None else doc_id_of(line),
        "title": line["item_name"].strip(),
        "category": line["department"],
        "specs": specs_of(line),
    }


def pool_lines(doc_id: str, ev: Evaluated) -> list[dict]:
    out = []
    for q, t, _ in ev.kept:
        spec = t.kind == "spec"
        out.append(
            {
                "doc_id": doc_id,
                "department": ev.line["department"],
                "leaf": ev.line["leaf"],
                "line_no": q["line_no"],
                "question_id": q["question_id"],
                "question_text": q["question_text"],
                "question_type": q["question_type"],
                "answer_aggregated": q["answer_aggregated"],
                "answers": q["answers"],
                "tag": t.kind,
                "policy_kinds": list(t.policy_kinds),
                # null on policy questions: answerability against the product does not apply
                "answerable": t.answerable if spec else None,
                "answerable_r1": t.answerable_r1 if spec else None,
                "q_tokens": t.q_tokens if spec else None,
                "covered": t.covered if spec else None,
            }
        )
    return out


def rank(asin: str) -> str:
    return hashlib.sha256(f"{SEED}:{asin}".encode()).hexdigest()


def draw(eligible: dict[str, list[str]], quota: dict[str, int]) -> dict[str, list[str]]:
    """Design §2.3: per leaf, the first quota[leaf] asins by sha256(seed:asin)."""
    short = [leaf for leaf, n in quota.items() if len(eligible.get(leaf, [])) < n]
    if short:
        detail = ", ".join(
            f"{leaf}: {len(eligible.get(leaf, []))} eligible, quota {quota[leaf]}"
            for leaf in quota
        )
        raise SelectionStop(
            f"too few eligible products in {', '.join(short)} ({detail}). The rule is not relaxed "
            f"here: only the author applies the pre-registered fallback (design §2.3)."
        )
    return {leaf: sorted(eligible[leaf], key=rank)[: quota[leaf]] for leaf in quota}


# =================================================================================================
# Statistics for the report (integers and digests only: no floats in the manifest)
# =================================================================================================
def distribution(values: list[int]) -> dict:
    s = sorted(values)
    n = len(s)
    if not n:
        return {"n": 0}
    return {
        "n": n,
        "min": s[0],
        "median": s[n // 2],  # upper median, as 3.1's prose_median_chars
        "p90": s[(9 * (n - 1)) // 10],  # the probe's int(0.9 * (n - 1)), in exact arithmetic
        "max": s[-1],
        "hist": {
            f"{lo}-{hi}": sum(1 for v in s if lo <= v <= hi) for lo, hi in BUCKETS
        },
    }


def counts_of(evs: Iterable[Evaluated]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(list)
    for ev in evs:
        spec = [k for k in ev.kept if k[1].kind == "spec"]
        out["kept"].append(len(ev.kept))
        out["policy"].append(sum(1 for k in ev.kept if k[1].kind == "policy"))
        out["answerable"].append(sum(1 for k in spec if k[1].answerable))
        out["unanswerable"].append(sum(1 for k in spec if not k[1].answerable))
    return out


@dataclass
class Share:
    spec: int = 0
    r1: int = 0
    r2: int = 0
    title_only: int = 0

    def add(self, ev: Evaluated) -> None:
        for _, t, _ in ev.kept:
            if t.kind == "spec":
                self.spec += 1
                self.r1 += t.answerable_r1
                self.r2 += t.answerable
                self.title_only += t.title_only

    def as_dict(self) -> dict:
        return {"spec": self.spec, "r1": self.r1, "r2": self.r2, "r2_title_only": self.title_only}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def products_digest(products_dir: Path) -> tuple[int, str]:
    """sha256 of the sorted (file name, file sha256) pairs of EVERY entry in the directory."""
    pairs = sorted(
        [p.name, build_pqa.sha256_file(p) if p.is_file() else "not-a-file"]
        for p in products_dir.iterdir()
    )
    return len(pairs), _sha256_bytes(_canonical(pairs))


def default_chunker() -> Callable[[dict], tuple[int, int]]:
    """(characters of the embedded text, chunks) for one record, exactly as `make ingest` would
    split it: rag.ingest.record_to_document, then SentenceSplitter at the frozen 256 / 40. No model
    is loaded. Imported here, not at the top, so the selector does not need rag to tag or draw."""
    from llama_index.core.node_parser import SentenceSplitter
    from rag.ingest import product_to_text, record_to_document

    from rag import config

    splitter = SentenceSplitter(chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP)

    def measure(record: dict) -> tuple[int, int]:
        nodes = splitter.get_nodes_from_documents([record_to_document(record)])
        return len(product_to_text(record)), len(nodes)

    return measure


# =================================================================================================
# The run
# =================================================================================================
@dataclass
class LeafTally:
    department: str = ""
    products_in: int = 0
    removed: Counter = field(default_factory=Counter)
    dropped: Counter = field(default_factory=Counter)
    capped: int = 0
    adr002: int = 0
    share_all: Share = field(default_factory=Share)
    reask_unfiltered: ReAsk = field(default_factory=ReAsk)
    eligible: dict[str, Evaluated] = field(default_factory=dict)
    adr002_records: list[dict] = field(default_factory=list)


def generic_tokens(manifest_path: Path, interim_dir: Path) -> dict[str, frozenset[str]]:
    """Pass 1: a token is generic in a leaf if it is in at least GENERIC_DF of the leaf's titles."""
    titles: dict[str, Counter] = defaultdict(Counter)
    products: Counter = Counter()
    for leaf, line in build_pqa.iter_interim(manifest_path, interim_dir):
        products[leaf] += 1
        titles[leaf].update(content_tokens(line["item_name"]))
    return {
        leaf: frozenset(
            t
            for t, c in titles[leaf].items()
            if Fraction(c, products[leaf]) >= GENERIC_DF
        )
        for leaf in products
    }


def tally(
    manifest_path: Path, interim_dir: Path, generic: dict[str, frozenset[str]]
) -> dict[str, LeafTally]:
    """Pass 2: tag, count the funnel and the probe's pools, keep the eligible products."""
    tallies: dict[str, LeafTally] = defaultdict(LeafTally)
    for leaf, line in build_pqa.iter_interim(manifest_path, interim_dir):
        t = tallies[leaf]
        t.department = line["department"]
        t.products_in += 1
        ev = evaluate(line, generic[leaf])
        t.dropped.update(ev.dropped)
        t.share_all.add(ev)
        if len(ev.kept) >= 2:
            t.reask_unfiltered.add([k[0]["question_text"] for k in ev.kept[:PAIR_CAP]])
        capped, adr002 = probe_pools(ev)
        t.capped += capped
        t.adr002 += adr002
        if adr002:
            # The same doc_id form as a selected record, without the asin check: the chunker
            # counts the metadata, so a doc_id of another length would change the chunk count.
            doc_id = f"product-{line['department']}-{line['asin'].lower()}"
            t.adr002_records.append(product_record(line, doc_id=doc_id))
        if ev.failed is None:
            t.eligible[line["asin"]] = ev
        else:
            t.removed[ev.failed] += 1
    return dict(tallies)


def check_pins(tallies: dict[str, LeafTally], pins: dict[str, dict[str, int]]) -> None:
    misses = []
    for pool, by_leaf in pins.items():
        for leaf, want in by_leaf.items():
            got = getattr(tallies[leaf], pool) if leaf in tallies else 0
            if got != want:
                misses.append(f"{leaf}: probe pool {pool} = {got}, pinned {want}")
    if misses:
        raise SelectionStop(
            "the probe's own pool rules do not reproduce on these bytes: "
            + "; ".join(misses)
            + ". The copied filters act differently from the probe (design §2.6)."
        )


def _remove_stale(draft_dir: Path) -> None:
    if not draft_dir.is_dir():
        return
    for child in sorted(draft_dir.iterdir()):
        if child.name.startswith(TEMP_PREFIX):
            print(f"removing the leftover of a crashed run: {child.name}", file=sys.stderr)
            shutil.rmtree(child, ignore_errors=True)


def guard(draft_dir: Path) -> None:
    """3.1 open question 4, option A: refuse while the retired script's product-*.json exist."""
    stale = sorted(draft_dir.glob("product-*.json")) if draft_dir.is_dir() else []
    if stale:
        raise SelectionStop(
            f"{len(stale)} product-*.json exist directly in {draft_dir}. They are from the retired "
            f"fetch script (wrong dataset). Delete them deliberately, then run again."
        )


def publish(work: Path, draft_dir: Path, selection_path: Path) -> None:
    """Swap the three outputs in, then write the manifest LAST. A failure part-way restores the old
    set, so the outputs and the manifest are a matching set, old or new, never mixed."""
    names = (PRODUCTS, POOL, GENERIC)
    old = draft_dir / f"{TEMP_PREFIX}old-{os.getpid()}"
    old.mkdir()
    moved_old: list[str] = []
    moved_new: list[str] = []
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        for name in names:
            if (draft_dir / name).exists():
                os.replace(draft_dir / name, old / name)
                moved_old.append(name)
        for name in names:
            os.replace(work / name, draft_dir / name)
            moved_new.append(name)
        os.replace(work / "selection.json", selection_path)  # LAST
    except BaseException:
        for name in reversed(moved_new):
            os.replace(draft_dir / name, work / name)
        for name in reversed(moved_old):
            os.replace(old / name, draft_dir / name)
        old.rmdir()  # empty again; reached only if every restore succeeded
        raise
    shutil.rmtree(old, ignore_errors=True)


def build_selection(
    consumed_sha256: str,
    tallies: dict[str, LeafTally],
    chosen: dict[str, list[str]],
    generic: dict[str, frozenset[str]],
    quota: dict[str, int],
    pins: dict[str, dict[str, int]],
    prose_stats: dict[str, dict],
    outputs: dict,
    fallback: tuple[str, ...] = (),
) -> dict:
    """Counts and digests only. Every string is a name, a digest, a regex source, the seed or a
    fixed label (the tests check it against an allow-list)."""
    leaves = list(quota)
    departments = sorted({tallies[leaf].department for leaf in leaves})
    funnel = {}
    for leaf in leaves:
        t = tallies[leaf]
        funnel[leaf] = {
            "department": t.department,
            "products_in": t.products_in,
            "removed": {step: t.removed[step] for step in STEPS},
            "eligible": len(t.eligible),
            "quota": quota[leaf],
            "selected": len(chosen[leaf]),
            "questions_dropped": {"dynamic": t.dropped["dynamic"], "carrier": t.dropped["carrier"]},
        }
    selected_evs = {leaf: [tallies[leaf].eligible[a] for a in chosen[leaf]] for leaf in leaves}
    groups = dict(selected_evs)  # per leaf, then per department
    for d in departments:
        groups[d] = [
            ev for leaf in leaves if tallies[leaf].department == d for ev in selected_evs[leaf]
        ]
    dist = {
        name: {kind: distribution(v) for kind, v in sorted(counts_of(evs).items())}
        for name, evs in groups.items()
    }
    share = {}
    for leaf in leaves:
        sel = Share()
        for ev in selected_evs[leaf]:
            sel.add(ev)
        share[leaf] = {"all": tallies[leaf].share_all.as_dict(), "selected": sel.as_dict()}
    reask = {}
    for leaf in leaves:
        filtered = ReAsk()
        for ev in selected_evs[leaf]:
            filtered.add([k[0]["question_text"] for k in ev.kept])
        reask[leaf] = {
            "unfiltered": tallies[leaf].reask_unfiltered.as_dict(),
            "filtered": filtered.as_dict(),
        }
    return {
        "stage": STAGE,
        "selection_version": SELECTION_VERSION,
        "note": NOTE,
        "consumed": {"pqa_manifest_sha256": consumed_sha256},
        "selector_sha256": build_pqa.sha256_file(Path(__file__)),
        "rule": {
            "coverage": f"{COVERAGE.numerator}/{COVERAGE.denominator}",
            "generic_df": f"{GENERIC_DF.numerator}/{GENERIC_DF.denominator}",
            "min_answerable": MIN_ANSWERABLE,
            "min_bullets": MIN_BULLETS,
            "cap": [CAP_LO, CAP_HI],
            "near_duplicate_band": [repr(ND_LO), repr(ND_HI)],
            "pair_cap": PAIR_CAP,
            "quota": dict(quota),
            "quota_preregistered": dict(QUOTA_PREREGISTERED),
            "seed": SEED,
            "audit_per_department": {
                "answerable": AUDIT_ANSWERABLE,
                "unanswerable": AUDIT_UNANSWERABLE,
            },
            "steps": list(STEPS),
            "regex": {
                "dynamic": DYNAMIC_Q.pattern,
                "carrier": CARRIER_Q.pattern,
                "policy_return": POLICY_Q["return"].pattern,
                "policy_warranty": POLICY_Q["warranty"].pattern,
                "warranty_term": WARRANTY_TERM.pattern,
            },
            "stop_words_sha256": _sha256_bytes(" ".join(sorted(STOP)).encode()),
            "probe_pins": pins,
            "fallback_applied": list(fallback),
        },
        "generic": {
            leaf: {
                "size": len(generic[leaf]),
                "sha256": _sha256_bytes(_canonical(sorted(generic[leaf]))),
            }
            for leaf in leaves
        },
        "funnel": funnel,
        "probe_pools": {
            leaf: {"capped": tallies[leaf].capped, "adr002": tallies[leaf].adr002}
            for leaf in leaves
        },
        "distribution": dist,
        "answerable_share": share,
        "prose": prose_stats,
        "reask": reask,
        "outputs": outputs,
    }


def _prose_stats(
    tallies: dict[str, LeafTally],
    chosen: dict[str, list[str]],
    records: dict[str, dict],
    chunker: Callable[[dict], tuple[int, int]],
) -> dict[str, dict]:
    """A record the frozen splitter refuses (SentenceSplitter raises ValueError when the metadata,
    which holds the title, is longer than the chunk size) would make `make ingest` fail. In the
    probe pool it is counted; among the selected products it stops the run. Found on the first
    run with fallback step 1: one TV in the probe pool, a title of 1,353 characters."""
    out = {}
    for leaf, asins in chosen.items():
        groups = {
            "selected": [records[a] for a in asins],
            "probe_pool": tallies[leaf].adr002_records,
        }
        out[leaf] = {}
        for name, recs in groups.items():
            measured, unchunkable = [], 0
            for r in recs:
                try:
                    measured.append(chunker(r))
                except ValueError:
                    unchunkable += 1
            if name == "selected" and unchunkable:
                raise SelectionStop(
                    f"{leaf}: {unchunkable} selected product(s) cannot be chunked by the frozen "
                    f"splitter, so `make ingest` would fail on them"
                )
            out[leaf][name] = {
                "chars": distribution([m[0] for m in measured]),
                "chunks": distribution([m[1] for m in measured]),
                "unchunkable": unchunkable,
            }
    return out


def write_outputs(
    work: Path,
    tallies: dict[str, LeafTally],
    chosen: dict[str, list[str]],
    generic: dict[str, frozenset[str]],
) -> tuple[dict[str, dict], dict]:
    """Write the records, the pool and the generic words into `work`. Returns the records by asin
    and the `outputs` block of the manifest."""
    products_dir = work / PRODUCTS
    products_dir.mkdir()
    records: dict[str, dict] = {}
    pool: list[dict] = []
    seen: set[str] = set()
    for leaf, asins in chosen.items():
        for asin in asins:
            ev = tallies[leaf].eligible[asin]
            doc_id = doc_id_of(ev.line)
            if doc_id in seen:
                raise SelectionStop("two selected products would share one doc_id")
            seen.add(doc_id)
            record = product_record(ev.line, doc_id)
            records[asin] = record
            text = json.dumps(record, ensure_ascii=False, indent=2) + "\n"  # NOT sort_keys (T5)
            (products_dir / f"{doc_id}.json").write_bytes(text.encode("utf-8"))
            pool.extend(pool_lines(doc_id, ev))
    pool.sort(key=lambda q: (q["doc_id"], q["line_no"]))
    pool_bytes = b"".join(_canonical(q) + b"\n" for q in pool)
    (work / POOL).write_bytes(pool_bytes)
    generic_bytes = _canonical({leaf: sorted(words) for leaf, words in sorted(generic.items())})
    (work / GENERIC).write_bytes(generic_bytes + b"\n")
    n, digest = products_digest(products_dir)
    outputs = {
        "products": n,
        "products_sha256": digest,
        "question_pool_lines": len(pool),
        "question_pool_sha256": _sha256_bytes(pool_bytes),
        "generic_tokens_sha256": _sha256_bytes(generic_bytes + b"\n"),
    }
    return records, outputs


def select(
    manifest_path: Path,
    interim_dir: Path,
    draft_dir: Path,
    selection_path: Path,
    quota: dict[str, int] | None = None,
    pins: dict[str, dict[str, int]] | None = None,
    chunker: Callable[[dict], tuple[int, int]] | None = None,
    fallback: tuple[str, ...] | None = None,
) -> int:
    """Run the selection. Returns 0, or 2 if a stop tripped. Any other exception propagates.

    With no `quota`, the real QUOTA and the fallback steps applied to it are used and recorded."""
    if fallback is None:
        fallback = FALLBACK_APPLIED if quota is None else ()
    quota = QUOTA if quota is None else quota
    pins = PROBE_PINS if pins is None else pins
    work = draft_dir / f"{TEMP_PREFIX}{os.getpid()}"
    try:
        guard(draft_dir)
        _remove_stale(draft_dir)
        consumed = manifest_path.read_bytes()  # read ONCE; its hash is what the output records
        consumed_sha256 = _sha256_bytes(consumed)
        generic = generic_tokens(manifest_path, interim_dir)
        tallies = tally(manifest_path, interim_dir, generic)
        missing = [leaf for leaf in quota if leaf not in tallies]
        if missing:
            raise SelectionStop(f"the interim has no products for {', '.join(missing)}")
        check_pins(tallies, pins)
        # Impact F8: nothing may have changed while it was read.
        if manifest_path.read_bytes() != consumed:
            raise SelectionStop(f"{manifest_path} changed while the interim was being read")
        build_pqa.verify_interim(json.loads(consumed), interim_dir)
        chosen = draw({leaf: sorted(t.eligible) for leaf, t in tallies.items()}, quota)
        work.mkdir(parents=True)
        records, outputs = write_outputs(work, tallies, chosen, generic)
        prose_stats = _prose_stats(tallies, chosen, records, chunker or default_chunker())
        selection = build_selection(
            consumed_sha256, tallies, chosen, generic, quota, pins, prose_stats, outputs, fallback
        )
        data = _canonical(selection) + b"\n"
        (work / "selection.json").write_bytes(data)
        publish(work, draft_dir, selection_path)
        print_report(selection)
        print(f"consumed pqa-manifest.json sha256: {consumed_sha256}")
        print(f"selection sha256: {_sha256_bytes(data)}")
        return 0
    except (
        SelectionStop,
        build_pqa.ManifestError,
        build_pqa.InterimMismatch,
    ) as error:
        print(f"stop: {error}", file=sys.stderr)
        print("Nothing was written under a final name.", file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(work, ignore_errors=True)


def print_report(selection: dict) -> None:
    """Counts a human should read on every run. Never PQA text."""
    funnel = selection["funnel"]
    print(f"{'leaf':<22}{'in':>8}" + "".join(f"{s[:9]:>10}" for s in STEPS) + f"{'eligible':>10}{'quota':>7}")
    for leaf, f in funnel.items():
        removed = "".join(f"{f['removed'][s]:>10,}" for s in STEPS)
        print(f"{leaf:<22}{f['products_in']:>8,}{removed}{f['eligible']:>10,}{f['quota']:>7}")
    print()
    print(f"{'leaf':<22}{'capped':>8}{'adr002':>8}{'dyn drop':>10}{'carr drop':>10}")
    for leaf, p in selection["probe_pools"].items():
        d = funnel[leaf]["questions_dropped"]
        print(f"{leaf:<22}{p['capped']:>8,}{p['adr002']:>8,}{d['dynamic']:>10,}{d['carrier']:>10,}")
    print()
    print(f"{'leaf':<22}{'spec q':>9}{'R1 %':>7}{'R2 %':>7}{'title%':>7}   selected: {'R1 %':>5}{'R2 %':>6}")
    for leaf, s in selection["answerable_share"].items():
        a, b = s["all"], s["selected"]

        def pct(n: int, d: int) -> str:
            return f"{100 * n / d:.1f}" if d else "-"

        print(
            f"{leaf:<22}{a['spec']:>9,}{pct(a['r1'], a['spec']):>7}{pct(a['r2'], a['spec']):>7}"
            f"{pct(a['r2_title_only'], a['r2']):>7}             {pct(b['r1'], b['spec']):>5}"
            f"{pct(b['r2'], b['spec']):>6}"
        )
    print()
    print("questions per selected product: median (min-max) of kept / policy / answerable / unanswerable")
    for name, d in selection["distribution"].items():
        cells = "  ".join(
            f"{k} {v['median']} ({v['min']}-{v['max']})" if v["n"] else f"{k} -"
            for k, v in d.items()
        )
        print(f"  {name:<22}{cells}")
    print()
    print("re-asks: questions, clusters (exact only / all), digit flips -- unfiltered | filtered")
    for leaf, r in selection["reask"].items():
        u, f = r["unfiltered"], r["filtered"]
        print(
            f"  {leaf:<22}{u['questions']:>9,} {u['clusters_exact']:>8,} {u['clusters_all']:>8,}"
            f" {u['digit_flips']:>6,}  | {f['questions']:>6,} {f['clusters_exact']:>6,}"
            f" {f['clusters_all']:>6,} {f['digit_flips']:>4,}"
        )
    print()
    print("embedded text, median chars / chunks -- selected | probe pool")
    for leaf, p in selection["prose"].items():
        s, q = p["selected"], p["probe_pool"]
        print(
            f"  {leaf:<22}{s['chars'].get('median', '-'):>6} / {s['chunks'].get('median', '-')}"
            f"   | {q['chars'].get('median', '-'):>6} / {q['chunks'].get('median', '-')}"
        )
    o = selection["outputs"]
    print()
    print(f"products {o['products']}, question pool lines {o['question_pool_lines']:,}")


# =================================================================================================
# The sanctioned reader of 3.2's outputs (review M6)
# =================================================================================================
class SelectionMismatch(Exception):
    """The selection manifest is missing or wrong, or an output is not what it names."""


def load_selection(path: Path) -> dict:
    if not path.is_file():
        raise SelectionMismatch(f"{path} does not exist. Run `make pqa-select`.")
    selection = json.loads(path.read_bytes())
    if selection.get("stage") != STAGE or selection.get("selection_version") != SELECTION_VERSION:
        raise SelectionMismatch(f"{path} is not a {STAGE} manifest of version {SELECTION_VERSION}.")
    return selection


def verify_selection(selection: dict, draft_dir: Path) -> None:
    o = selection["outputs"]
    products_dir = draft_dir / PRODUCTS
    if not products_dir.is_dir():
        raise SelectionMismatch(f"{products_dir} is missing. Run `make pqa-select`.")
    if products_digest(products_dir) != (o["products"], o["products_sha256"]):
        raise SelectionMismatch(
            f"{products_dir} differs from the selection manifest (a file changed, is missing or "
            f"is extra). Run `make pqa-select`."
        )
    for name, key in ((POOL, "question_pool_sha256"), (GENERIC, "generic_tokens_sha256")):
        path = draft_dir / name
        if not path.is_file() or build_pqa.sha256_file(path) != o[key]:
            raise SelectionMismatch(f"{path} differs from the selection manifest. Run `make pqa-select`.")


def iter_selection(selection_path: Path, draft_dir: Path) -> Iterator[tuple[str, dict]]:
    """The only sanctioned reader of 3.2's outputs. Yields ("product", record) for every record in
    file-name order, then ("question", line) for every pool line. Everything is hashed against the
    selection manifest on the first next(), before anything is yielded."""
    selection = load_selection(selection_path)
    verify_selection(selection, draft_dir)
    for path in sorted((draft_dir / PRODUCTS).iterdir()):
        yield "product", json.loads(path.read_bytes())
    with (draft_dir / POOL).open("rb") as f:
        for raw in f:
            yield "question", json.loads(raw)


# =================================================================================================
# The blind audit (design §3.2)
# =================================================================================================
def audit_rank(doc_id: str, line_no: int) -> str:
    return hashlib.sha256(f"{SEED}:audit:{doc_id}:{line_no}".encode()).hexdigest()


def audit_sample(pool: list[dict]) -> list[dict]:
    """Per department: the AUDIT_ANSWERABLE R2-answerable and AUDIT_UNANSWERABLE R2-unanswerable
    spec questions with the lowest audit rank; all of them in audit-rank order."""
    by_dept: dict[str, dict[bool, list[dict]]] = defaultdict(lambda: {True: [], False: []})
    for q in pool:
        if q["tag"] == "spec":
            by_dept[q["department"]][q["answerable"]].append(q)
    sample = []
    for dept in sorted(by_dept):
        for answerable, n in ((True, AUDIT_ANSWERABLE), (False, AUDIT_UNANSWERABLE)):
            group = sorted(by_dept[dept][answerable], key=lambda q: audit_rank(q["doc_id"], q["line_no"]))
            if len(group) < n:
                raise SelectionStop(f"{dept}: only {len(group)} questions for an audit group of {n}")
            sample.extend(group[:n])
    return sorted(sample, key=lambda q: audit_rank(q["doc_id"], q["line_no"]))


def _read_selection(selection_path: Path, draft_dir: Path) -> tuple[dict[str, dict], list[dict]]:
    records: dict[str, dict] = {}
    pool: list[dict] = []
    for kind, obj in iter_selection(selection_path, draft_dir):
        if kind == "product":
            records[obj["doc_id"]] = obj
        else:
            pool.append(obj)
    return records, pool


SHEET_COLUMNS = ("item", "doc_id", "line_no", "question", "product_text", "answerable")


def write_audit_sheet(selection_path: Path, draft_dir: Path, sheet_path: Path) -> int:
    """The sheet carries no tag: the auditor marks `answerable` yes or no from the text alone."""
    from rag.ingest import product_to_text

    try:
        records, pool = _read_selection(selection_path, draft_dir)
        sample = audit_sample(pool)
    except (SelectionMismatch, SelectionStop) as error:
        print(f"stop: {error}", file=sys.stderr)
        return 2
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    with sheet_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(SHEET_COLUMNS)
        for item, q in enumerate(sample, start=1):
            text = product_to_text(records[q["doc_id"]])
            writer.writerow([item, q["doc_id"], q["line_no"], q["question_text"].strip(), text, ""])
    print(f"wrote {len(sample)} questions to {sheet_path}. Mark `answerable` yes or no in each row.")
    return 0


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """95 % Wilson score interval for k successes in n."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(centre - half, 4), round(centre + half, 4)]


def score_audit(selection_path: Path, draft_dir: Path, sheet_path: Path, out_path: Path) -> int:
    """Precision of R2 (over the tagged answerable), the negative predictive value (over the tagged
    unanswerable), and recall re-weighted to the selected pool's tag counts, because the sample is
    stratified 15 : 10 and is not the pool's ratio. Counts only into `out_path`."""
    try:
        _, pool = _read_selection(selection_path, draft_dir)
        sample = audit_sample(pool)
    except (SelectionMismatch, SelectionStop) as error:
        print(f"stop: {error}", file=sys.stderr)
        return 2
    with sheet_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    expected = {(q["doc_id"], q["line_no"]): q for q in sample}
    got = {(r["doc_id"], int(r["line_no"])): r for r in rows}
    if set(got) != set(expected) or len(rows) != len(sample):
        print("stop: the sheet's rows are not the audit sample. Regenerate it.", file=sys.stderr)
        return 2
    bad = [r["item"] for r in rows if r["answerable"].strip().lower() not in ("yes", "no")]
    if bad:
        print(f"stop: rows {', '.join(bad)} are not marked yes or no.", file=sys.stderr)
        return 2
    cells: dict[str, Counter] = defaultdict(Counter)
    for key, q in expected.items():
        human = got[key]["answerable"].strip().lower() == "yes"
        cells[q["department"]][("tp" if human else "fp") if q["answerable"] else ("fn" if human else "tn")] += 1
    pooled: Counter = Counter()
    for c in cells.values():
        pooled.update(c)
    tagged = sum(1 for q in pool if q["tag"] == "spec" and q["answerable"])
    untagged = sum(1 for q in pool if q["tag"] == "spec" and not q["answerable"])
    precision_n = pooled["tp"] + pooled["fp"]
    npv_n = pooled["tn"] + pooled["fn"]
    precision = pooled["tp"] / precision_n if precision_n else 0.0
    false_omission = pooled["fn"] / npv_n if npv_n else 0.0
    recall = None
    if precision * tagged + false_omission * untagged:
        recall = round(precision * tagged / (precision * tagged + false_omission * untagged), 4)
    result = {
        "rule": "R2",
        "sample": {"per_department": {"answerable": AUDIT_ANSWERABLE, "unanswerable": AUDIT_UNANSWERABLE}},
        "per_department": {d: {k: c[k] for k in ("tp", "fp", "fn", "tn")} for d, c in sorted(cells.items())},
        "pooled": {k: pooled[k] for k in ("tp", "fp", "fn", "tn")},
        "precision": {"k": pooled["tp"], "n": precision_n, "wilson95": wilson(pooled["tp"], precision_n)},
        "npv": {"k": pooled["tn"], "n": npv_n, "wilson95": wilson(pooled["tn"], npv_n)},
        "pool_spec_tags": {"answerable": tagged, "unanswerable": untagged},
        "recall_reweighted": recall,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["pooled"]), json.dumps(result["precision"]), f"recall~{recall}")
    return 0


# =================================================================================================
# The command line
# =================================================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--manifest", type=Path, default=build_pqa.MANIFEST_PATH)
    parser.add_argument("--interim-dir", type=Path, default=build_pqa.INTERIM_DIR)
    parser.add_argument("--draft-dir", type=Path, default=DRAFT_DIR)
    parser.add_argument("--selection", type=Path, default=SELECTION_PATH)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true", help="hash the outputs against the manifest")
    mode.add_argument("--audit-sheet", action="store_true", help="write the blind audit sheet")
    mode.add_argument("--audit-score", type=Path, metavar="OUT", help="score the marked sheet into OUT")
    args = parser.parse_args(argv)
    sheet = args.draft_dir / AUDIT_SHEET
    if args.verify:
        try:
            verify_selection(load_selection(args.selection), args.draft_dir)
        except SelectionMismatch as error:
            print(str(error), file=sys.stderr)
            return 2
        print(f"verified: the outputs in {args.draft_dir} match {args.selection.name}")
        return 0
    if args.audit_sheet:
        return write_audit_sheet(args.selection, args.draft_dir, sheet)
    if args.audit_score:
        return score_audit(args.selection, args.draft_dir, sheet, args.audit_score)
    return select(args.manifest, args.interim_dir, args.draft_dir, args.selection)


if __name__ == "__main__":
    sys.exit(main())
