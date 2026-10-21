"""Item 3.4: the workload generator -- the mechanical half of the trail's rules.md.

    make workload-status                                  # open tasks per round, counts only
    make workload-sheets ROUND=label OUT=<dir>            # sheets for the next batches, OUTSIDE the repo
    make workload-import IN=<dir>/label-01.rows.jsonl     # check a rows file, append the valid rows

The **model layer** (`data/v1-draft/workload/model-layer.jsonl`, gitignored) is what Claude writes,
by `docs/work/2026-10-21-workload-generator/rules.md`, from sheets this script prepares. Every row
answers one open **task**; every task is derived here, deterministically, from 3.2's selection (read
only through `select_pqa.iter_selection`), 3.3's policy documents and the rows already written. A
row is checked mechanically when it is imported; a failed row is listed and re-done by Claude, never
repaired by a script. Three rounds, in order:

- `label` (pass 1): R1 names, R2 labels (and the RELABEL repeats), R7 policy assignments, R9
  natural-pair marks.
- `write` (pass 2): R3 rewrites, R4 paraphrases, R5 lookalikes, R8 D questions, R7 cell wordings.
  Opens only when the `label` round is complete.
- `check` (pass 2, later batches): every written spec query labelled again on its own, without its
  seed (R2), and the R6 name swaps labelled against the partner's record.

The rules, the constants and the analysis rules were committed before the first sheet was read
(spec W18): `sheets` and `import` refuse to run while rules.md is uncommitted or changed.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
import random
import re
import subprocess
import sys
from collections import Counter, OrderedDict, defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

import check_policies
import corpus_gate
import select_pqa

REPO_ROOT = select_pqa.REPO_ROOT
SELECTION_PATH = select_pqa.SELECTION_PATH
DRAFT_DIR = select_pqa.DRAFT_DIR
POLICY_DIR = check_policies.DEFAULT_DIR
WORK_DIR = DRAFT_DIR / "workload"  # gitignored with data/v1-draft/
LAYER_PATH = WORK_DIR / "model-layer.jsonl"
VECTORS_PATH = WORK_DIR / "vectors.json"
DATA_DIR = REPO_ROOT / "data"
TRAIL = REPO_ROOT / "docs" / "work" / "2026-10-21-workload-generator"
RULES_PATH = TRAIL / "rules.md"
BATCHES_PATH = TRAIL / "evidence" / "batches.md"
BUILD_REPORT_PATH = TRAIL / "evidence" / "build.md"

# =================================================================================================
# The constants (rules.md §2; design.md §2.2). Fixed before any label was read: a count is never
# pushed toward a number by changing one of these after labels exist. A test checks that rules.md
# states every value below.
# =================================================================================================
SEED = "v1-item-3.4"
MODEL_ID = "claude-opus-5-5"
SPEC_SEEDS_PER_PRODUCT = 2
PARAPHRASES_PER_SEED = 2  # one close, one far
SPEC_LOOKALIKES_PER_PRODUCT = 1  # on the product's first seed
POLICY_PRODUCTS_PER_CELL = 3
TWIN_PRODUCTS_PER_CELL = 20
TWIN_WORDINGS_DEPT = 8
D_PER_PRODUCT = 1
D_PRODUCT_STRIDE = 2  # D_PER_PRODUCT for every other product, in hash order
UNANSWERABLE_SEEDS = 13  # per department
UNANSWERABLE_PARAPHRASES = 1
RELABEL = 40
R2_UNANSWERABLE_SAMPLE = 40  # per department: the R2-unanswerable questions pass 1 labels
NATURAL_JACCARD_MIN = 0.45  # select_pqa.ND_LO
NATURAL_JACCARD_MAX = 0.99  # select_pqa.ND_HI: an identical token set is a duplicate, not a pair
NATURAL_PER_PRODUCT = 3
MIN_TWINS_PER_SPLIT = 30
NAME_WORDS = (2, 6)
EVIDENCE_WORDS = (3, 30)
QUESTION_MAX_WORDS = 30
ANSWER_MAX_WORDS = 30
ATTRIBUTE_MAX_WORDS = 6
R10_NGRAM = 4
PRODUCTS_PER_SHEET = 8

CONSTANTS = (
    "SEED", "MODEL_ID", "SPEC_SEEDS_PER_PRODUCT", "PARAPHRASES_PER_SEED",
    "SPEC_LOOKALIKES_PER_PRODUCT", "POLICY_PRODUCTS_PER_CELL", "TWIN_PRODUCTS_PER_CELL",
    "TWIN_WORDINGS_DEPT", "D_PER_PRODUCT", "D_PRODUCT_STRIDE", "UNANSWERABLE_SEEDS",
    "UNANSWERABLE_PARAPHRASES", "RELABEL", "R2_UNANSWERABLE_SAMPLE", "NATURAL_JACCARD_MIN",
    "NATURAL_JACCARD_MAX", "NATURAL_PER_PRODUCT", "MIN_TWINS_PER_SPLIT", "NAME_WORDS",
    "EVIDENCE_WORDS", "QUESTION_MAX_WORDS", "ANSWER_MAX_WORDS", "ATTRIBUTE_MAX_WORDS", "R10_NGRAM",
)

ROUNDS = ("label", "write", "check")

# R7: the pool's own policy tag misses these (ADR-011); a line any of them matches is assigned too.
WIDE_POLICY = re.compile(
    r"\b(replace(ment|ments|d)?|send (it |them )?back|sent back|exchang(e|ed|es|ing))\b",
    re.IGNORECASE,
)

# =================================================================================================
# Tokens and text (rules.md §3). Never the probe's tokenizer, which drops digits and one-character
# tokens: "Windows 7" and "Windows 8" must stay apart (impact F12).
# =================================================================================================
LUCENE_STOP = frozenset(
    """
a an and are as at be but by for if in into is it no not of on or such that the their then there
these they this to was will with
""".split()  # noqa: SIM905
)
assert len(LUCENE_STOP) == 33


def raw_tokens(text: str) -> list[str]:
    """Lower case, split on anything but [a-z0-9]; one-character tokens and digits kept."""
    return re.findall(r"[a-z0-9]+", text.lower())


def tokens(text: str) -> list[str]:
    """`raw_tokens` less Lucene's 33 English stop words: the tokenizer of every check here."""
    return [t for t in raw_tokens(text) if t not in LUCENE_STOP]


def token_set(text: str) -> frozenset[str]:
    return frozenset(tokens(text))


def digits(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"\d+", text))


def digits_besides(text: str, name: str) -> frozenset[str]:
    """R3, R4: the digit set, less the short name's own digits ("Zenvo X2" carries a 2 that the
    original "How long does it last?" lacks; a model number in the original is the name's too)."""
    return digits(text) - digits(name)


def collapse(text: str) -> str:
    return " ".join(text.split())


def n_words(text: str) -> int:
    return len(text.split())


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def polarity(answer: str) -> str | None:
    """"yes" or "no" when the answer's first word is one, else None (R5, R6)."""
    first = raw_tokens(answer)[:1]
    return first[0] if first and first[0] in ("yes", "no") else None


def names_product(question: str, name: str) -> bool:
    """The short name's raw tokens appear in the question, contiguous and in order."""
    q, n = raw_tokens(question), raw_tokens(name)
    return bool(n) and any(q[i : i + len(n)] == n for i in range(len(q) - len(n) + 1))


def h(*parts: object) -> str:
    """Every order in this file: sha256 over SEED and the parts. Never Python's hash()."""
    return hashlib.sha256(":".join([SEED, *map(str, parts)]).encode()).hexdigest()


# =================================================================================================
# Inputs
# =================================================================================================
@dataclass(frozen=True)
class Product:
    doc_id: str
    department: str
    leaf: str
    title: str
    fields: tuple[tuple[str, str], ...]  # (field, whitespace-collapsed text): title, then specs
    risky: bool  # check_policies.RISKY_TITLE on the title or any spec (review L7)

    @property
    def record_tokens(self) -> frozenset[str]:
        return frozenset(t for _, text in self.fields for t in tokens(text))


@dataclass(frozen=True)
class PoolLine:
    doc_id: str
    line_no: int
    department: str
    text: str
    question_type: str
    tag: str
    r2_answerable: bool | None

    @property
    def ref(self) -> str:
        return f"{self.doc_id}:{self.line_no}"


@dataclass
class Inputs:
    products: dict[str, Product]
    pool: dict[str, PoolLine]  # by ref
    policies: dict[str, dict]  # by doc_id
    sections: dict[str, dict[str, str]]  # doc_id -> shape -> text
    cache: dict = field(default_factory=dict, repr=False)

    def lines_of(self, doc_id: str) -> list[PoolLine]:
        return sorted(
            (p for p in self.pool.values() if p.doc_id == doc_id), key=lambda p: p.line_no
        )


def is_risky(record: dict) -> bool:
    texts = [str(record.get("title", "")), *map(str, record.get("specs", {}).values())]
    return any(p.search(t) for p in check_policies.RISKY_TITLE.values() for t in texts)


def make_product(record: dict, leaf: str) -> Product:
    fields = [("title", collapse(str(record["title"])))]
    fields += [(k, collapse(str(v))) for k, v in record["specs"].items()]
    return Product(
        doc_id=record["doc_id"],
        department=record["category"],
        leaf=leaf,
        title=str(record["title"]),
        fields=tuple(fields),
        risky=is_risky(record),
    )


def load_inputs(
    items: Iterable[tuple[str, dict]], policy_dir: Path = POLICY_DIR
) -> Inputs:
    """From `select_pqa.iter_selection`'s stream (spec W3: the only reader of 3.2's drafts) and the
    policy folder. A changed draft stops iter_selection before anything is yielded."""
    records: list[dict] = []
    pool: dict[str, PoolLine] = {}
    leaf_of: dict[str, str] = {}
    for kind, obj in items:
        if kind == "product":
            records.append(obj)
            continue
        line = PoolLine(
            doc_id=obj["doc_id"],
            line_no=int(obj["line_no"]),
            department=obj["department"],
            text=str(obj["question_text"]).strip(),
            question_type=str(obj.get("question_type", "")),
            tag=str(obj["tag"]),
            r2_answerable=obj.get("r2_answerable"),
        )
        pool[line.ref] = line
        leaf_of[line.doc_id] = obj["leaf"]
    homeless = sorted(r["doc_id"] for r in records if r["doc_id"] not in leaf_of)
    if homeless:
        raise WorkloadStop(f"{len(homeless)} product(s) with no pool line, so no leaf to unit them in")
    products = {r["doc_id"]: make_product(r, leaf_of[r["doc_id"]]) for r in records}
    policies = {}
    for path in sorted(policy_dir.glob("*.json")):
        doc = json.loads(path.read_text())
        policies[doc["doc_id"]] = doc
    return Inputs(
        products=products,
        pool=pool,
        policies=policies,
        sections={d: policy_sections(doc) for d, doc in policies.items()},
    )


# =================================================================================================
# Policy shapes (rules.md §7; design.md §2.3). Mapped by heading text, never by position: the
# warranty files run covers -> does not cover -> claim -> remedy -> proof (review L1).
# =================================================================================================
SHAPES = ("term", "what", "start", "remedy", "except", "other")
HEADING_SHAPE = {
    "What to send back": "what",
    "What the warranty covers": "what",
    "What international service covers": "what",
    "How to start a return": "start",
    "How to make a claim": "start",
    "Asking for help abroad": "start",
    "Your refund": "remedy",
    "Repair, replacement or refund": "remedy",
    "Repair or replacement": "remedy",
    "Repairs arranged abroad": "remedy",
    "Items we cannot take back": "except",
    "Pieces we cannot take back": "except",
    "Phones we cannot accept": "except",
    "What the warranty does not cover": "except",
    "What is not covered": "except",
    "Exchanges": "other",
    "Proof of purchase and transfer": "other",
}


class WorkloadStop(Exception):
    """A stop: exit code 2, nothing written."""


def policy_sections(doc: dict) -> dict[str, str]:
    """`term` is the opening paragraph; every other shape is a headed section, found by its
    heading. An unknown heading, a missing shape or a shape found twice stops the run."""
    paragraphs = [p.strip() for p in str(doc["text"]).split("\n\n") if p.strip()]
    sections: dict[str, list[str]] = {"term": [paragraphs[0]]}
    current = "term"
    for p in paragraphs[1:]:
        if p in HEADING_SHAPE:
            current = HEADING_SHAPE[p]
            if current in sections:
                raise WorkloadStop(f"{doc['doc_id']}: shape {current} has two headings")
            sections[current] = []
        elif "\n" not in p and not p.endswith((".", "?", "!", ":")) and len(p) < 60:
            raise WorkloadStop(f"{doc['doc_id']}: unknown heading {p!r}")
        else:
            sections[current].append(p)
    missing = [s for s in SHAPES if s not in sections]
    if missing:
        raise WorkloadStop(f"{doc['doc_id']}: no section for {', '.join(missing)}")
    return {s: "\n\n".join(sections[s]) for s in SHAPES}


def family(doc: dict) -> tuple[str, str]:
    return (str(doc["policy_kind"]), str(doc["category"]))


def sibling(inputs: Inputs, doc_id: str) -> str | None:
    doc = inputs.policies[doc_id]
    if not doc.get("condition"):
        return None
    for other_id, other in sorted(inputs.policies.items()):
        if other_id != doc_id and family(other) == family(doc):
            return other_id
    return None


DEFAULT_CONDITION = {"packaging": "unopened", "grade": "new", "region": "domestic"}


def department_doc(inputs: Inputs, department: str, kind: str) -> str:
    """The department's document of one kind; on a split family, the default condition's."""
    for doc_id, doc in sorted(inputs.policies.items()):
        if family(doc) != (kind, department):
            continue
        cond = doc.get("condition")
        if not cond or DEFAULT_CONDITION.get(cond["axis"]) == cond["value"]:
            return doc_id
    raise WorkloadStop(f"no {kind} document for {department}")


def condition_problems(inputs: Inputs, text: str, doc_id: str) -> list[str]:
    """R7: a query names its own document's condition value and kind, and nothing else.

    The G5 word list (`corpus_gate.condition_hits`, one implementation). Grade's plain words
    ("new") count only inside a family split by grade, as in G5."""
    doc = inputs.policies[doc_id]
    cond = doc.get("condition") if isinstance(doc.get("condition"), dict) else None
    allowed = {("kind", doc["policy_kind"])}
    if cond:
        allowed.add((cond["axis"], cond["value"]))
    grade_family = cond is not None and cond["axis"] == "grade"
    problems = []
    named = set()
    for axis, values in corpus_gate.condition_hits(text).items():
        for value, words in values.items():
            if axis == "grade" and not grade_family:
                words = [w for w in words if w not in corpus_gate.GRADE_PLAIN_WORDS]
            if not words:
                continue
            named.add((axis, value))
            if (axis, value) not in allowed:
                problems.append(f"names {axis} = {value} ({', '.join(words)}), not this document's")
    if cond and (cond["axis"], cond["value"]) not in named:
        problems.append(f"does not name its condition, {cond['axis']} = {cond['value']}")
    return problems


def name_is_neutral(name: str) -> bool:
    """A short name that names no condition value of any axis (plain grade words included), so
    it can be put into any policy query without naming a condition by accident."""
    return not corpus_gate.condition_hits(name)


def r10_problem(inputs: Inputs, text: str, name: str = "") -> str | None:
    """R10: no 4-token sequence shared with any policy document, after the name, every term string
    and every condition word are taken out of both texts (review M6 b)."""
    remove = set(raw_tokens(name))
    for doc in inputs.policies.values():
        for term in doc["terms"]:
            remove |= set(raw_tokens(term))
    for values in corpus_gate.CONDITION_AXES.values():
        for words in values.values():
            for w in words:
                remove |= set(raw_tokens(w))
    q = [t for t in tokens(text.replace("{name}", " ")) if t not in remove]
    grams = {tuple(q[i : i + R10_NGRAM]) for i in range(len(q) - R10_NGRAM + 1)}
    if not grams:
        return None
    for doc_id, doc in sorted(inputs.policies.items()):
        p = [t for t in tokens(doc["title"] + "\n" + doc["text"]) if t not in remove]
        shared = grams & {tuple(p[i : i + R10_NGRAM]) for i in range(len(p) - R10_NGRAM + 1)}
        if shared:
            return f"shares {' '.join(min(shared))!r} with {doc_id}"
    return None


# =================================================================================================
# The model layer
# =================================================================================================
def load_layer(path: Path) -> dict[str, dict]:
    layer: dict[str, dict] = {}
    if not path.is_file():
        return layer
    with path.open() as f:
        for n, raw in enumerate(f, 1):
            if raw.strip():
                row = json.loads(raw)
                if row["key"] in layer:
                    raise WorkloadStop(f"{path}: key {row['key']} twice (line {n})")
                layer[row["key"]] = row
    return layer


def rows_of(layer: dict[str, dict], type_: str) -> list[dict]:
    return [r for k, r in sorted(layer.items()) if r["type"] == type_]


def short_names(layer: dict[str, dict]) -> dict[str, str]:
    return {r["doc_id"]: r["name"] for r in rows_of(layer, "name")}


# =================================================================================================
# Tasks (rules.md §6): what each round asks for, derived from the inputs and the rows so far
# =================================================================================================
def of_inputs(fn: Callable[[Inputs], object]) -> Callable:
    """Memoise a function of the inputs alone; the task plan asks for the same lists often."""

    def wrapper(inputs: Inputs):
        if fn.__name__ not in inputs.cache:
            inputs.cache[fn.__name__] = fn(inputs)
        return inputs.cache[fn.__name__]

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


@dataclass(frozen=True)
class Task:
    key: str
    type: str
    round: str
    group: str  # the product (or department, for cells) whose sheet section shows it
    context: dict = field(default_factory=dict, compare=False, hash=False)


def spec_lines(inputs: Inputs, doc_id: str | None = None) -> list[PoolLine]:
    return [
        p
        for p in inputs.pool.values()
        if p.tag == "spec" and (doc_id is None or p.doc_id == doc_id)
    ]


@of_inputs
def label_targets(inputs: Inputs) -> list[PoolLine]:
    """Every R2-answerable spec question, and per department the first R2_UNANSWERABLE_SAMPLE
    R2-unanswerable ones in hash order (spec carry-forward 2)."""
    chosen = [p for p in spec_lines(inputs) if p.r2_answerable]
    by_dept: dict[str, list[PoolLine]] = defaultdict(list)
    for p in spec_lines(inputs):
        if not p.r2_answerable:
            by_dept[p.department].append(p)
    for dept in sorted(by_dept):
        group = sorted(by_dept[dept], key=lambda p: h("r2-sample", p.ref))
        chosen += group[:R2_UNANSWERABLE_SAMPLE]
    return sorted(chosen, key=lambda p: (p.doc_id, p.line_no))


@of_inputs
def relabel_targets(inputs: Inputs) -> list[PoolLine]:
    return sorted(label_targets(inputs), key=lambda p: h("relabel", p.ref))[:RELABEL]


@of_inputs
def policy_targets(inputs: Inputs) -> list[PoolLine]:
    return sorted(
        (p for p in inputs.pool.values() if p.tag == "policy" or WIDE_POLICY.search(p.text)),
        key=lambda p: (p.doc_id, p.line_no),
    )


@of_inputs
def natural_candidates(inputs: Inputs) -> list[tuple[PoolLine, PoolLine, float]]:
    """R9: pairs of spec questions on one product, token Jaccard in [0.45, 0.99], greedy by
    Jaccard (ties by hash) so no question is in two pairs, at most NATURAL_PER_PRODUCT each."""
    out = []
    for doc_id in sorted(inputs.products):
        lines = sorted(spec_lines(inputs, doc_id), key=lambda p: p.line_no)
        toks = [token_set(p.text) for p in lines]
        pairs = []
        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                jac = jaccard(toks[i], toks[j])
                if NATURAL_JACCARD_MIN <= jac <= NATURAL_JACCARD_MAX:
                    pairs.append((lines[i], lines[j], jac))
        pairs.sort(key=lambda t: (-t[2], h("natural", t[0].ref, t[1].ref)))
        used: set[str] = set()
        kept = 0
        for a, b, jac in pairs:
            if kept == NATURAL_PER_PRODUCT:
                break
            if a.ref in used or b.ref in used:
                continue
            used |= {a.ref, b.ref}
            out.append((a, b, jac))
            kept += 1
    return out


@of_inputs
def natural_members(inputs: Inputs) -> set[str]:
    return {p.ref for a, b, _ in natural_candidates(inputs) for p in (a, b)}


def first_labels(layer: dict[str, dict]) -> dict[str, dict]:
    """The pass-1 label of each labelled question (the RELABEL repeat is reported, never used)."""
    return {f"{r['doc_id']}:{r['line_no']}": r for r in rows_of(layer, "label")}


def seed_refs(inputs: Inputs, layer: dict[str, dict]) -> dict[str, list[str]]:
    """Per product, its Claude-answerable labelled questions (both R2 tags, review L6) outside the
    natural candidates, in hash order: the first SPEC_SEEDS_PER_PRODUCT."""
    labels = first_labels(layer)
    natural = natural_members(inputs)
    out: dict[str, list[str]] = {}
    for doc_id in sorted(inputs.products):
        refs = [
            ref
            for ref, r in labels.items()
            if r["doc_id"] == doc_id and r["answerable"] and ref not in natural
        ]
        out[doc_id] = sorted(refs, key=lambda ref: h("seed", ref))[:SPEC_SEEDS_PER_PRODUCT]
    return out


def unanswerable_refs(inputs: Inputs, layer: dict[str, dict]) -> list[str]:
    """Per department, its Claude-unanswerable labelled questions outside the natural candidates,
    in hash order: the first UNANSWERABLE_SEEDS."""
    labels = first_labels(layer)
    natural = natural_members(inputs)
    by_dept: dict[str, list[str]] = defaultdict(list)
    for ref, r in labels.items():
        if not r["answerable"] and ref not in natural:
            by_dept[inputs.pool[ref].department].append(ref)
    out = []
    for dept in sorted(by_dept):
        out += sorted(by_dept[dept], key=lambda ref: h("unanswerable", ref))[:UNANSWERABLE_SEEDS]
    return out


def natural_pairs_kept(layer: dict[str, dict]) -> list[dict]:
    """Natural candidates Claude marked `same` or `different`, both sides answerable."""
    return [r for r in rows_of(layer, "natural") if r["mark"] in ("same", "different")]


def eligible_products(inputs: Inputs, layer: dict[str, dict], department: str) -> list[str]:
    """Products a policy or D query may name (spec W6): not risky, and a short name that names no
    condition. In no particular order; each use sorts them by its own hash."""
    names = short_names(layer)
    return sorted(
        d
        for d, p in inputs.products.items()
        if p.department == department and not p.risky and name_is_neutral(names.get(d, ""))
    )


def d_assignments(inputs: Inputs, layer: dict[str, dict]) -> dict[str, str]:
    """R8: per department, every other eligible product in hash order gets one D question; the
    k-th of them uses the department's warranty document if k is even, its return document if odd
    (the default condition on a split family)."""
    out = {}
    for dept in departments(inputs):
        ordered = sorted(eligible_products(inputs, layer, dept), key=lambda d: h("d", d))
        for k, doc_id in enumerate(ordered[::D_PRODUCT_STRIDE]):
            kind = "warranty" if k % 2 == 0 else "return"
            out[doc_id] = department_doc(inputs, dept, kind)
    return out


def departments(inputs: Inputs) -> list[str]:
    return sorted({p.department for p in inputs.products.values()})


# --- policy cells --------------------------------------------------------------------------------
@dataclass(frozen=True)
class Cell:
    cell_id: str
    doc_id: str
    shape: str
    variant: str  # "" | "fee" | "dept"
    products: tuple[str, ...]  # empty for a department-level cell
    wordings: int
    twin_group: str | None = None
    probe_kind: str | None = None
    pair_cell: str | None = None


# The four minimal-pair groups (design.md §2.3, review H2): cells whose two sides' answers differ,
# read from the files. Each side's query on a product is built against the other side's query on
# the same product (or the same wording index, for the department-level laptops cells).
TWIN_GROUPS = {
    "phones-returns-term-fee": (
        ("policy-return-phones-opened", "term", "fee"),
        ("policy-return-phones-unopened", "term", "fee"),
    ),
    "phones-returns-remedy": (
        ("policy-return-phones-opened", "remedy", ""),
        ("policy-return-phones-unopened", "remedy", ""),
    ),
    "furniture-returns-term": (
        ("policy-return-furniture-opened", "term", ""),
        ("policy-return-furniture-unopened", "term", ""),
    ),
    "laptops-returns-term": (
        ("policy-return-laptops-new", "term", "dept"),
        ("policy-return-laptops-renewed", "term", "dept"),
    ),
}
# Product-level cells the twin groups replace: no ordinary 3-product cell is built for these.
REPLACED = {
    ("policy-return-phones-opened", "remedy"),
    ("policy-return-phones-unopened", "remedy"),
    ("policy-return-furniture-opened", "term"),
    ("policy-return-furniture-unopened", "term"),
    ("policy-return-laptops-new", "term"),
    ("policy-return-laptops-renewed", "term"),
}


def cell_id(doc_id: str, shape: str, variant: str = "") -> str:
    return f"{doc_id}:{shape}" + (f":{variant}" if variant else "")


def plan_cells(inputs: Inputs, layer: dict[str, dict]) -> list[Cell]:
    """Rules.md §7. Product choice, per department, from its eligible products:

    - a twin cell takes the first TWIN_PRODUCTS_PER_CELL in `h("policy", doc_id)` order, the same
      products on both sides;
    - an international phones warranty cell takes its domestic sibling's products (policy-region);
    - a warranty `term` cell takes the first 3 products of the department's return `term` cell it
      is built against (policy-kind; laptops has no product-level return `term` cell, so none);
    - every other cell takes the first POLICY_PRODUCTS_PER_CELL in `h("policy", cell, doc_id)`
      order.
    """
    cells: dict[str, Cell] = {}
    twin_side = {side: (g, sides) for g, sides in TWIN_GROUPS.items() for side in sides}
    order = {
        dept: sorted(eligible_products(inputs, layer, dept), key=lambda d: h("policy", d))
        for dept in departments(inputs)
    }

    for (doc_id, shape, variant), (group, sides) in sorted(twin_side.items()):
        doc = inputs.policies[doc_id]
        other = next(s for s in sides if s[0] != doc_id)
        dept_level = variant == "dept"
        cells[cell_id(doc_id, shape, variant)] = Cell(
            cell_id=cell_id(doc_id, shape, variant),
            doc_id=doc_id,
            shape=shape,
            variant=variant,
            products=() if dept_level else tuple(order[doc["category"]][:TWIN_PRODUCTS_PER_CELL]),
            wordings=TWIN_WORDINGS_DEPT if dept_level else 1,
            twin_group=group,
            probe_kind="condition-department" if dept_level else "policy-condition",
            pair_cell=cell_id(*other),
        )

    def first_three(cid: str, dept: str) -> tuple[str, ...]:
        ranked = sorted(order[dept], key=lambda d: h("policy", cid, d))
        return tuple(ranked[:POLICY_PRODUCTS_PER_CELL])

    deferred = []
    for doc_id, doc in sorted(inputs.policies.items()):
        for shape in SHAPES:
            if (doc_id, shape) in REPLACED:
                continue
            cid = cell_id(doc_id, shape)
            cond = doc.get("condition") or {}
            if cond.get("value") == "international":
                deferred.append((cid, doc_id, shape, "region"))
            elif doc["policy_kind"] == "warranty" and shape == "term":
                deferred.append((cid, doc_id, shape, "kind"))
            else:
                cells[cid] = Cell(cid, doc_id, shape, "", first_three(cid, doc["category"]), 1)
    # kind before region: the domestic phones `term` cell is kind-paired, and the international
    # `term` cell then takes its products.
    for cid, doc_id, shape, how in sorted(deferred, key=lambda t: (t[3] != "kind", t[0])):
        doc = inputs.policies[doc_id]
        if how == "region":
            pair = cell_id(sibling(inputs, doc_id) or "", shape)
            cells[cid] = Cell(cid, doc_id, shape, "", cells[pair].products, 1, None,
                              "policy-region", pair)
            continue
        ret = cell_id(department_doc(inputs, doc["category"], "return"), "term")
        if ret in cells and cells[ret].products:
            prods = cells[ret].products[:POLICY_PRODUCTS_PER_CELL]
            cells[cid] = Cell(cid, doc_id, shape, "", prods, 1, None, "policy-kind", ret)
        else:
            cells[cid] = Cell(cid, doc_id, shape, "", first_three(cid, doc["category"]), 1)
    return [cells[c] for c in sorted(cells)]


# --- units and name swaps (design.md §2.5) -------------------------------------------------------
@of_inputs
def make_units(inputs: Inputs) -> list[tuple[str, ...]]:
    """Per leaf, products in `h("unit", doc_id)` order, two at a time; an odd leaf's last unit is a
    triple. B-cross is built inside a unit, so it is known before the split."""
    by_leaf: dict[str, list[str]] = defaultdict(list)
    for doc_id, p in inputs.products.items():
        by_leaf[p.leaf].append(doc_id)
    units = []
    for leaf in sorted(by_leaf):
        ordered = sorted(by_leaf[leaf], key=lambda d: h("unit", d))
        pairs = [tuple(ordered[i : i + 2]) for i in range(0, len(ordered) - len(ordered) % 2, 2)]
        if len(ordered) % 2 and pairs:
            pairs[-1] = (*pairs[-1], ordered[-1])
        elif len(ordered) % 2:
            pairs.append((ordered[-1],))  # a leaf of one: a unit with no B-cross
        units += pairs
    return units


def swap_directions(units: list[tuple[str, ...]]) -> list[tuple[str, str]]:
    """(A, B): A's first seed asked with B's name. Both ways in a pair; round a triple."""
    out = []
    for unit in units:
        if len(unit) == 2:
            out += [(unit[0], unit[1]), (unit[1], unit[0])]
        elif len(unit) == 3:
            out += [(unit[0], unit[1]), (unit[1], unit[2]), (unit[2], unit[0])]
    return out


def swap_question(question: str, name_a: str, name_b: str) -> str | None:
    """The seed with A's short name replaced by B's, case-insensitively, or None if A's name is not
    in it as written."""
    pattern = re.compile(re.escape(name_a), re.IGNORECASE)
    if not pattern.search(question):
        return None
    return pattern.sub(lambda _: name_b, question)


def swap_leftover(inputs: Inputs, question: str, a: str, b: str) -> list[str]:
    """R6 (review M5 d): title tokens unique to A that remain in the swapped question."""
    unique_a = token_set(inputs.products[a].title) - token_set(inputs.products[b].title)
    return sorted(token_set(question) & unique_a)


# --- the three rounds ----------------------------------------------------------------------------
def label_tasks(inputs: Inputs, layer: dict[str, dict]) -> list[Task]:
    tasks = []
    for doc_id in sorted(inputs.products):
        tasks.append(Task(f"name:{doc_id}", "name", "label", doc_id))
    for p in label_targets(inputs):
        tasks.append(Task(f"label:{p.ref}", "label", "label", p.doc_id, {"ref": p.ref}))
    labelled = first_labels(layer)
    for p in relabel_targets(inputs):
        if p.ref in labelled:  # opens only once the first label exists: a later batch
            tasks.append(Task(f"relabel:{p.ref}", "relabel", "label", p.doc_id, {"ref": p.ref}))
    for p in policy_targets(inputs):
        tasks.append(Task(f"policy:{p.ref}", "policy", "label", p.doc_id, {"ref": p.ref}))
    for a, b, jac in natural_candidates(inputs):
        tasks.append(
            Task(f"natural:{a.ref}:{b.line_no}", "natural", "label", a.doc_id,
                 {"a": a.ref, "b": b.ref, "jaccard": round(jac, 3)})
        )
    return tasks


def round_complete(tasks: list[Task], layer: dict[str, dict]) -> bool:
    return all(t.key in layer for t in tasks)


def write_tasks(inputs: Inputs, layer: dict[str, dict]) -> list[Task]:
    # Complete means every name, label, policy and natural task, and every RELABEL repeat: the
    # repeats open only once all their first labels exist, so all of them are in this list then.
    if not round_complete(label_tasks(inputs, layer), layer):
        return []
    tasks = []
    labels = first_labels(layer)
    for doc_id, refs in seed_refs(inputs, layer).items():
        for i, ref in enumerate(refs):
            ctx = {"ref": ref, "role": "seed", "label": labels[ref]}
            tasks.append(Task(f"seed:{ref}", "seed", "write", doc_id, ctx))
            for kind in ("close", "far")[:PARAPHRASES_PER_SEED]:
                tasks.append(Task(f"para:{ref}:{kind}", "para", "write", doc_id,
                                  {"ref": ref, "kind": kind, "label": labels[ref]}))
            if i < SPEC_LOOKALIKES_PER_PRODUCT:
                tasks.append(Task(f"lookalike:{ref}", "lookalike", "write", doc_id,
                                  {"ref": ref, "label": labels[ref]}))
    for r in natural_pairs_kept(layer):
        for side in ("a", "b"):
            ref = r[side]
            tasks.append(Task(f"seed:{ref}", "seed", "write", r["doc_id"],
                              {"ref": ref, "role": "natural", "natural": r["key"]}))
    for ref in unanswerable_refs(inputs, layer):
        doc_id = inputs.pool[ref].doc_id
        tasks.append(Task(f"seed:{ref}", "seed", "write", doc_id, {"ref": ref, "role": "unanswerable"}))
        for kind in ("close",)[:UNANSWERABLE_PARAPHRASES]:
            tasks.append(Task(f"para:{ref}:{kind}", "para", "write", doc_id,
                              {"ref": ref, "kind": kind, "label": labels[ref]}))
    for doc_id, policy in sorted(d_assignments(inputs, layer).items()):
        tasks.append(Task(f"d:{doc_id}", "d", "write", doc_id, {"policy": policy}))
    for cell in plan_cells(inputs, layer):
        tasks.append(Task(f"cell:{cell.cell_id}", "cell", "write",
                          inputs.policies[cell.doc_id]["category"], {"cell": cell}))
    return tasks


# Written spec queries labelled again on their own in the check round, by row type.
BLIND_TYPES = ("seed", "para", "lookalike")


def blind_key(target: str) -> str:
    """Opaque, so the key on the sheet does not tell the labeller the query's role or seed."""
    return "blind:" + h("blind", target)[:16]


def check_tasks(inputs: Inputs, layer: dict[str, dict]) -> list[Task]:
    tasks = []
    for key, row in sorted(layer.items()):
        if row["type"] in BLIND_TYPES:
            tasks.append(Task(blind_key(key), "blind", "check", row["doc_id"], {"target": key}))
    names = short_names(layer)
    seeds = seed_refs(inputs, layer)
    for a, b in swap_directions(make_units(inputs)):
        if not seeds.get(a):
            continue
        ref = seeds[a][0]
        seed_row = layer.get(f"seed:{ref}")
        if seed_row is None:
            continue
        q = swap_question(seed_row["question"], names[a], names[b])
        if q is None or swap_leftover(inputs, q, a, b):
            continue  # dropped and counted by the build (R6)
        tasks.append(Task(f"swap:{ref}:{b}", "swap", "check", b,
                          {"ref": ref, "from": a, "question": q}))
    return tasks


def all_tasks(inputs: Inputs, layer: dict[str, dict]) -> dict[str, list[Task]]:
    return {
        "label": label_tasks(inputs, layer),
        "write": write_tasks(inputs, layer),
        "check": check_tasks(inputs, layer),
    }


def open_tasks(inputs: Inputs, layer: dict[str, dict], round_: str) -> list[Task]:
    return [t for t in all_tasks(inputs, layer)[round_] if t.key not in layer]


# =================================================================================================
# Row checks (rules.md §5). Each returns the problems; an empty list accepts the row.
# =================================================================================================
def locate(product: Product, evidence: str) -> tuple[int, int, int] | None:
    """(field index, start, end) of the evidence's first occurrence, whitespace collapsed."""
    ev = collapse(evidence)
    if not ev:
        return None
    for i, (_, text) in enumerate(product.fields):
        at = text.find(ev)
        if at >= 0:
            return (i, at, at + len(ev))
    return None


def overlaps(product: Product, ev_a: str, ev_b: str) -> bool:
    """Two evidence spans overlap: the same field, and their character ranges intersect."""
    a, b = locate(product, ev_a), locate(product, ev_b)
    return bool(a and b and a[0] == b[0] and a[1] < b[2] and b[1] < a[2])


def check_answer(row: dict, product: Product, prefix: str = "") -> list[str]:
    """R2: an answerable label carries a one-line answer and verbatim evidence of 3-30 words."""
    answer, evidence = row.get(f"{prefix}answer", ""), row.get(f"{prefix}evidence", "")
    problems = []
    if not isinstance(answer, str) or not answer.strip() or "\n" in answer:
        problems.append(f"{prefix}answer: one line, not empty")
    elif n_words(answer) > ANSWER_MAX_WORDS:
        problems.append(f"{prefix}answer: more than {ANSWER_MAX_WORDS} words")
    lo, hi = EVIDENCE_WORDS
    if not isinstance(evidence, str) or not lo <= n_words(evidence) <= hi:
        problems.append(f"{prefix}evidence: {lo}-{hi} words")
    elif locate(product, evidence) is None:
        problems.append(f"{prefix}evidence: not a verbatim part of one field of the record")
    return problems


def check_label(row: dict, product: Product) -> list[str]:
    if not isinstance(row.get("answerable"), bool):
        return ["answerable: true or false"]
    if row["answerable"]:
        return check_answer(row, product)
    if row.get("answer") or row.get("evidence"):
        return ["an unanswerable label carries no answer and no evidence"]
    return []


def check_question(text: object, name: str | None) -> list[str]:
    """One question, ASCII, at most QUESTION_MAX_WORDS words, naming the product when it has one."""
    if not isinstance(text, str) or not text.strip():
        return ["question: empty"]
    problems = []
    if not text.isascii():
        problems.append("question: not ASCII")
    if n_words(text) > QUESTION_MAX_WORDS:
        problems.append(f"question: more than {QUESTION_MAX_WORDS} words")
    if text.count("?") != 1 or not text.rstrip().endswith("?"):
        problems.append("question: exactly one '?', at the end")
    if name is not None and not names_product(text, name):
        problems.append(f"question: does not name the product as {name!r}")
    return problems


@dataclass
class Context:
    """What a row is checked against: the inputs, the layer, this file's accepted rows, and every
    Tier-1 form already used."""

    inputs: Inputs
    layer: dict[str, dict]
    accepted: dict[str, dict] = field(default_factory=dict)
    forms: set[str] = field(default_factory=set)

    def row(self, key: str) -> dict | None:
        return self.accepted.get(key) or self.layer.get(key)

    def names(self) -> dict[str, str]:
        out = short_names(self.layer)
        out.update({r["doc_id"]: r["name"] for r in self.accepted.values() if r["type"] == "name"})
        return out


def written_question_forms(layer: dict[str, dict]) -> set[str]:
    return {
        corpus_gate.normalize_t1(r["question"])
        for r in layer.values()
        if r["type"] in ("seed", "para", "lookalike", "d")
    }


def check_new_form(ctx: Context, question: str) -> list[str]:
    if corpus_gate.normalize_t1(question) in ctx.forms:
        return ["question: its Tier-1 form is already used by another query (W5)"]
    return []


def check_row(row: dict, task: Task, ctx: Context) -> list[str]:
    inputs = ctx.inputs
    t = task.type
    product = inputs.products.get(task.group)
    names = ctx.names()

    if t == "name":
        name = row.get("name", "")
        lo, hi = NAME_WORDS
        problems = []
        if not isinstance(name, str) or not name.isascii() or not lo <= n_words(name) <= hi:
            return [f"name: {lo}-{hi} ASCII words"]
        extra = set(raw_tokens(name)) - set(raw_tokens(product.title))
        if extra:
            problems.append(f"name: words not in the title: {', '.join(sorted(extra))}")
        taken = {
            corpus_gate.normalize_t1(n): d for d, n in names.items() if d != product.doc_id
        }
        if corpus_gate.normalize_t1(name) in taken:
            problems.append("name: already the short name of another product")
        return problems

    if t in ("label", "relabel"):
        return check_label(row, product)

    if t == "policy":
        line = inputs.pool[task.context["ref"]]
        assign, shape, variant = row.get("assign"), row.get("shape"), row.get("variant", "")
        special = ("ambiguous", "not_covered", "not_policy")
        if assign in ("not_covered", "not_policy"):
            return [] if shape is None else ["shape: null unless assigned or ambiguous"]
        if shape not in SHAPES:
            return [f"shape: one of {', '.join(SHAPES)}"]
        if assign == "ambiguous":
            kind = row.get("kind")
            if kind not in ("return", "warranty"):
                return ["kind: return or warranty, for an ambiguous question"]
            doc_kind_dept = (kind, line.department)
        elif assign in inputs.policies:
            doc = inputs.policies[assign]
            doc_kind_dept = family(doc)
            if doc["category"] != line.department:
                return [f"assign: {assign} is not a {line.department} document"]
        else:
            return [f"assign: a policy doc_id or one of {', '.join(special)}"]
        if variant not in ("", "fee"):
            return ["variant: '' or 'fee'"]
        if variant == "fee" and not (doc_kind_dept == ("return", "phones") and shape == "term"):
            return ["variant: 'fee' only for a phones return `term` question"]
        return []

    if t == "natural":
        mark = row.get("mark")
        if mark not in ("same", "different", "unanswerable"):
            return ["mark: same, different or unanswerable"]
        if mark == "unanswerable":
            return []
        return check_answer(row, product, "a_") + check_answer(row, product, "b_")

    if t == "seed":
        line = inputs.pool[task.context["ref"]]
        q = row.get("question")
        problems = check_question(q, names[task.group])
        if problems:
            return problems
        name = names[task.group]
        if digits_besides(q, name) != digits_besides(line.text, name):
            problems.append(
                f"question: digits {sorted(digits_besides(q, name))} differ from the original's "
                f"{sorted(digits_besides(line.text, name))} (R3)"
            )
        return problems + check_new_form(ctx, q)

    if t == "para":
        seed = ctx.row(f"seed:{task.context['ref']}")
        if seed is None:
            return ["write and import the seed's rewrite first (this file or an earlier one)"]
        q = row.get("question")
        problems = check_question(q, names[task.group])
        if problems:
            return problems
        name = names[task.group]
        if digits_besides(q, name) != digits_besides(seed["question"], name):
            problems.append("question: digits differ from the seed's (R4)")
        added = (token_set(q) & product.record_tokens) - token_set(seed["question"])
        if added:
            problems.append(f"question: record words the seed lacks: {', '.join(sorted(added))} (R4)")
        return problems + check_new_form(ctx, q)

    if t == "lookalike":
        label = task.context["label"]
        q = row.get("question")
        problems = check_question(q, names[task.group])
        attribute = row.get("attribute", "")
        if not isinstance(attribute, str) or not 1 <= n_words(attribute) <= ATTRIBUTE_MAX_WORDS:
            problems.append(f"attribute: 1-{ATTRIBUTE_MAX_WORDS} words")
        problems += check_answer(row, product)
        if problems:
            return problems
        if overlaps(product, row["evidence"], label["evidence"]):
            problems.append("evidence: overlaps the seed's evidence; a lookalike needs its own (R5)")
        pa, pb = polarity(row["answer"]), polarity(label["answer"])
        if pa and pb and pa == pb:
            problems.append("answer: the same yes / no as the seed's (R5)")
        return problems + check_new_form(ctx, q)

    if t == "d":
        doc = inputs.policies[task.context["policy"]]
        q = row.get("question")
        problems = check_question(q, names[task.group]) + check_answer(row, product)
        if problems:
            return problems
        if not any(term in row["answer"] for term in doc["terms"]):
            problems.append(f"answer: holds none of the document's terms {doc['terms']} (R8)")
        problems += condition_problems(inputs, q, doc["doc_id"])
        r10 = r10_problem(inputs, q, names[task.group])
        if r10:
            problems.append(f"question: {r10} (R10)")
        return problems + check_new_form(ctx, q)

    if t == "cell":
        cell: Cell = task.context["cell"]
        wordings = row.get("wordings")
        if not isinstance(wordings, list) or len(wordings) != cell.wordings:
            return [f"wordings: a list of {cell.wordings}"]
        problems = []
        for i, w in enumerate(wordings):
            label = f"wording {i + 1}"
            dept_level = cell.variant == "dept"
            ps = check_question(w, None)
            if isinstance(w, str):
                if dept_level and "{name}" in w:
                    ps.append("names no product (department level)")
                if not dept_level and w.count("{name}") != 1:
                    ps.append("holds '{name}' exactly once")
                ps += condition_problems(inputs, w.replace("{name}", "it"), cell.doc_id)
                r10 = r10_problem(inputs, w)
                if r10:
                    ps.append(f"{r10} (R10)")
            problems += [f"{label}: {p}" for p in ps]
        forms = [corpus_gate.normalize_t1(w) for w in wordings if isinstance(w, str)]
        if len(set(forms)) != len(forms):
            problems.append("wordings: two share one Tier-1 form")
        origin, source = row.get("origin"), row.get("source")
        if origin == "claude":
            if source is not None:
                problems.append("source: null when origin is claude")
        elif origin == "pqa-template":
            problems += check_cell_source(ctx, cell, source)
        else:
            problems.append("origin: pqa-template or claude")
        return problems

    if t == "blind":
        target = ctx.row(task.context["target"])
        return check_label(row, inputs.products[target["doc_id"]])

    if t == "swap":
        problems = check_label(row, product)
        if not problems and row["answerable"] and not isinstance(row.get("same_answer"), bool):
            problems.append("same_answer: true or false, for an answerable swap")
        return problems

    return [f"no check for row type {t}"]


def check_cell_source(ctx: Context, cell: Cell, source: object) -> list[str]:
    """A `pqa-template` wording names the real pool question it came from: one assigned (R7) to
    this cell's department, kind and shape, or ambiguous with that kind and shape."""
    if not isinstance(source, str):
        return ["source: the pool question's doc_id:line_no, for origin pqa-template"]
    row = ctx.row(f"policy:{source}")
    if row is None:
        return [f"source: {source} is not an assigned pool policy question"]
    doc = ctx.inputs.policies[cell.doc_id]
    if row["assign"] in ctx.inputs.policies:
        kind = ctx.inputs.policies[row["assign"]]["policy_kind"]
    else:
        kind = row.get("kind")
    line = ctx.inputs.pool[source]
    if (kind, line.department, row.get("shape")) != (doc["policy_kind"], doc["category"], cell.shape):
        return [f"source: {source} was assigned to another kind, department or shape"]
    return []


# =================================================================================================
# Import (rules.md §1): a rows file in, the valid rows appended, the rejects listed
# =================================================================================================
def claude_fields(type_: str) -> frozenset[str]:
    """The fields a row of this type may carry: its skeleton's."""
    probe = Task("k", type_, "", "", {"cell": Cell("", "", "", "", (), 1)})
    return frozenset(skeleton(probe))


def derived(task: Task, inputs: Inputs) -> dict:
    """What the import stores beside Claude's fields, read from the task, so that every later step
    finds a row's product and question without parsing its key."""
    c, t = task.context, task.type
    if t == "name":
        return {"doc_id": task.group}
    if t in ("label", "relabel", "policy"):
        line = inputs.pool[c["ref"]]
        return {"doc_id": line.doc_id, "line_no": line.line_no}
    if t == "natural":
        return {"doc_id": task.group, "a": c["a"], "b": c["b"]}
    if t == "seed":
        return {"doc_id": task.group, "ref": c["ref"], "role": c["role"]}
    if t == "para":
        return {"doc_id": task.group, "ref": c["ref"], "para_kind": c["kind"]}
    if t == "lookalike":
        return {"doc_id": task.group, "ref": c["ref"]}
    if t == "d":
        return {"doc_id": task.group, "policy": c["policy"]}
    if t == "cell":
        return {"cell_id": c["cell"].cell_id, "department": task.group}
    if t == "blind":
        return {"target": c["target"], "doc_id": task.group}
    if t == "swap":
        return {"doc_id": task.group, "ref": c["ref"], "from": c["from"], "question": c["question"]}
    raise ValueError(t)


TYPE_ORDER = (
    "name", "label", "relabel", "policy", "natural", "seed", "para", "lookalike", "d", "cell",
    "blind", "swap",
)


@dataclass
class ImportReport:
    batch: str
    sha256: str
    accepted: Counter = field(default_factory=Counter)
    skipped: int = 0
    rejects: list[tuple[int, str, list[str]]] = field(default_factory=list)


def _comparable(row: dict) -> dict:
    return {k: v for k, v in row.items() if k in claude_fields(row["type"])}


def import_rows(
    in_path: Path,
    layer_path: Path,
    inputs: Inputs,
    rules_sha256: str,
    model_id: str = MODEL_ID,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ImportReport:
    """Check every row of a rows file against its open task; append the valid ones.

    Re-importing a key with the same content is skipped; with different content it is a reject,
    never an overwrite. Rows are checked in TYPE_ORDER, so a seed is accepted before the
    paraphrases written against it in the same file.
    """
    data = in_path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    report = ImportReport(batch=sha[:16], sha256=sha)
    layer = load_layer(layer_path)
    tasks = {t.key: t for r in ROUNDS for t in open_tasks(inputs, layer, r)}
    ctx = Context(inputs, layer, forms=written_question_forms(layer))

    parsed: list[tuple[int, dict]] = []
    seen: set[str] = set()
    for n, raw in enumerate(data.decode().splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as e:
            report.rejects.append((n, "?", [f"not JSON: {e.msg}"]))
            continue
        key = row.get("key") if isinstance(row, dict) else None
        if not isinstance(key, str):
            report.rejects.append((n, "?", ["no key"]))
            continue
        if key in seen:
            report.rejects.append((n, key, ["this key twice in one file"]))
            continue
        seen.add(key)
        if key in layer:
            if _comparable(layer[key]) == _comparable(row) and set(row) <= claude_fields(row.get("type", "")):
                report.skipped += 1
            else:
                report.rejects.append((n, key, ["already in the model layer with other content"]))
            continue
        task = tasks.get(key)
        if task is None:
            report.rejects.append((n, key, ["not an open task (unknown, or its round is not open)"]))
            continue
        if row.get("type") != task.type:
            report.rejects.append((n, key, [f"type: {task.type}"]))
            continue
        unknown = set(row) - claude_fields(task.type)
        if unknown:
            report.rejects.append((n, key, [f"fields not in a {task.type} row: {sorted(unknown)}"]))
            continue
        parsed.append((n, row))

    stamp = {"_batch": report.batch, "_model": model_id, "_rules": rules_sha256[:16]}
    out = []
    for n, row in sorted(parsed, key=lambda t: (TYPE_ORDER.index(t[1]["type"]), t[0])):
        task = tasks[row["key"]]
        problems = check_row(row, task, ctx)
        if problems:
            report.rejects.append((n, row["key"], problems))
            continue
        stored = {**row, **derived(task, inputs), **stamp, "_round": task.round,
                  "_at": now().isoformat(timespec="seconds")}
        ctx.accepted[row["key"]] = stored
        if row["type"] in ("seed", "para", "lookalike", "d"):
            ctx.forms.add(corpus_gate.normalize_t1(row["question"]))
        out.append(stored)
        report.accepted[row["type"]] += 1

    if out:
        layer_path.parent.mkdir(parents=True, exist_ok=True)
        with layer_path.open("a") as f:
            for row in out:
                f.write(json.dumps(row, sort_keys=True) + "\n")
    report.rejects.sort()
    return report


def batch_line(report: ImportReport, file_name: str, rules_sha256: str, model_id: str,
               at: datetime) -> str:
    """One row of evidence/batches.md: counts and hashes only, no question and no asin."""
    accepted = ", ".join(f"{t} {n}" for t, n in sorted(report.accepted.items())) or "none"
    return (
        f"| {at.isoformat(timespec='seconds')} | `{file_name}` | `{report.sha256[:16]}` | "
        f"{model_id} | `{rules_sha256[:16]}` | {accepted} | {report.skipped} | "
        f"{len(report.rejects)} |"
    )


# =================================================================================================
# Sheets (rules.md §4): written OUTSIDE the repository, because they hold PQA text
# =================================================================================================
def refuse_inside_repo(out_dir: Path) -> None:
    """Spec T15: a sheet holds PQA text and asins, so it may never land where git can see it."""
    if out_dir.resolve().is_relative_to(REPO_ROOT.resolve()):
        raise WorkloadStop(f"{out_dir} is inside the repository; sheets go to a scratch directory")


def skeleton(task: Task) -> dict:
    base = {"key": task.key, "type": task.type}
    t = task.type
    if t == "name":
        return {**base, "name": ""}
    if t in ("label", "relabel", "blind"):
        return {**base, "answerable": None, "answer": "", "evidence": ""}
    if t == "policy":
        return {**base, "assign": "", "shape": None, "variant": "", "kind": None}
    if t == "natural":
        return {**base, "mark": "", "a_answer": "", "a_evidence": "", "b_answer": "",
                "b_evidence": ""}
    if t in ("seed", "para"):
        return {**base, "question": ""}
    if t == "lookalike":
        return {**base, "question": "", "attribute": "", "answer": "", "evidence": ""}
    if t == "d":
        return {**base, "question": "", "answer": "", "evidence": ""}
    if t == "cell":
        n = task.context["cell"].wordings
        return {**base, "wordings": [""] * n, "origin": "", "source": None}
    if t == "swap":
        return {**base, "answerable": None, "answer": "", "evidence": "", "same_answer": None}
    raise ValueError(t)


def render_task(task: Task, inputs: Inputs, layer: dict[str, dict]) -> list[str]:
    c = task.context
    out = [f"### `{task.key}`", ""]
    pool = inputs.pool
    if task.type in ("label", "relabel", "policy"):
        out.append(f"Question: {pool[c['ref']].text}")
    elif task.type == "natural":
        out += [f"Question a: {pool[c['a']].text}", f"Question b: {pool[c['b']].text}"]
    elif task.type == "seed":
        out.append(f"Original question: {pool[c['ref']].text}")
        if c.get("role") == "seed":
            out.append(f"Your pass-1 answer: {c['label']['answer']} | evidence: {c['label']['evidence']}")
        out.append(f"Role: {c['role']}")
    elif task.type == "para":
        out.append(f"Paraphrase ({c['kind']}) of the rewrite you write as `seed:{c['ref']}`")
        if c["label"]["answerable"]:
            out.append(f"Pass-1 answer: {c['label']['answer']} | evidence: {c['label']['evidence']}")
    elif task.type == "lookalike":
        out += [
            f"Seed: the rewrite you write as `seed:{c['ref']}`",
            f"Seed answer: {c['label']['answer']} | evidence: {c['label']['evidence']}",
        ]
    elif task.type == "d":
        doc = inputs.policies[c["policy"]]
        cond = doc.get("condition")
        out += [
            f"Policy document: {doc['doc_id']} (terms: {', '.join(doc['terms'])})",
            f"Name its condition: {cond['axis']} = {cond['value']}" if cond else "No condition.",
        ]
    elif task.type == "blind":
        out.append(f"Query: {layer[c['target']]['question']}")
    elif task.type == "swap":
        seed_label = first_labels(layer)[c["ref"]]
        out += [
            f"Query: {c['question']}",
            f"The other product's answer to its own version: {seed_label['answer']}",
        ]
    elif task.type == "cell":
        cell: Cell = c["cell"]
        doc = inputs.policies[cell.doc_id]
        cond = doc.get("condition")
        out += [
            f"Document: {doc['doc_id']} · shape `{cell.shape}`"
            + (f" · variant `{cell.variant}`" if cell.variant else ""),
            f"Terms: {', '.join(doc['terms'])}",
            f"Name its condition: {cond['axis']} = {cond['value']}" if cond else "No condition.",
            f"Wordings: {cell.wordings}"
            + (" (no product named)" if cell.variant == "dept" else " (each with {name} once)"),
        ]
        if cell.twin_group:
            out.append(f"Minimal pair with `cell:{cell.pair_cell}` ({cell.twin_group})")
        out += ["", "Section text:", "", "> " + inputs.sections[cell.doc_id][cell.shape].replace("\n\n", "\n>\n> ")]
        sources = cell_sources(inputs, layer, cell)
        if sources:
            out += ["", "Real pool questions for this kind, department and shape:"]
            out += [f"- `{ref}`: {pool[ref].text}" for ref in sources]
    out += ["", "```json", json.dumps(skeleton(task)), "```", ""]
    return out


def cell_sources(inputs: Inputs, layer: dict[str, dict], cell: Cell) -> list[str]:
    doc = inputs.policies[cell.doc_id]
    out = []
    for r in rows_of(layer, "policy"):
        ref = f"{r['doc_id']}:{r['line_no']}"
        if r["assign"] in inputs.policies:
            kind = inputs.policies[r["assign"]]["policy_kind"]
        elif r["assign"] == "ambiguous":
            kind = r.get("kind")
        else:
            continue
        line = inputs.pool[ref]
        if (kind, line.department, r.get("shape")) == (doc["policy_kind"], doc["category"], cell.shape):
            out.append(ref)
    return out


def render_product(inputs: Inputs, layer: dict[str, dict], doc_id: str) -> list[str]:
    p = inputs.products[doc_id]
    name = short_names(layer).get(doc_id)
    out = [f"## `{doc_id}` · {p.department} · {p.leaf}" + (f" · short name **{name}**" if name else ""), ""]
    out += ["Record (quote evidence verbatim from ONE field):", ""]
    out += [f"- **{f}**: {text}" for f, text in p.fields]
    return out + [""]


ROUND_RULES = {
    "label": "R1 (name), R2 (label, relabel), R7 (policy), R9 (natural)",
    "write": "R3 (seed), R4 (para), R5 (lookalike), R8 (d), R7 and R10 (cell)",
    "check": "R2 (blind: label the query on its own), R6 (swap)",
}


def write_sheets(
    inputs: Inputs, layer: dict[str, dict], round_: str, out_dir: Path, rules_sha256: str,
    per_sheet: int = PRODUCTS_PER_SHEET,
) -> list[Path]:
    refuse_inside_repo(out_dir)
    tasks = open_tasks(inputs, layer, round_)
    groups: dict[str, list[Task]] = defaultdict(list)
    for t in tasks:
        groups[t.group].append(t)
    product_groups = [g for g in sorted(groups) if g in inputs.products]
    other_groups = [g for g in sorted(groups) if g not in inputs.products]
    if round_ == "check":
        for g in product_groups:  # a blind sheet does not read in seed-then-paraphrase order
            groups[g].sort(key=lambda t: h("sheet", t.key))
    chunks = [product_groups[i : i + per_sheet] for i in range(0, len(product_groups), per_sheet)]
    chunks += [[g] for g in other_groups]  # one department's cells per sheet

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for n, chunk in enumerate(chunks, 1):
        name = f"{round_}-{n:02d}"
        lines = [
            f"# Sheet {name} — round `{round_}`",
            "",
            (
                f"Follow {RULES_PATH.relative_to(REPO_ROOT)} (sha256 `{rules_sha256[:16]}`): "
                f"{ROUND_RULES[round_]}."
            ),
            f"Write one JSON object per line into `{name}.rows.jsonl` beside this sheet, then run",
            f"`make workload-import IN={out_dir / (name + '.rows.jsonl')}`.",
            "",
        ]
        for g in chunk:
            if g in inputs.products:
                lines += render_product(inputs, layer, g)
            else:
                lines += [f"## Policy cells · {g}", ""]
            for t in groups[g]:
                lines += render_task(t, inputs, layer)
        path = out_dir / f"{name}.md"
        path.write_text("\n".join(lines))
        paths.append(path)
    return paths


# =================================================================================================
# The build (plan step 6; design.md §2.4 - §2.7; rules.md §8). No model and no network: the model
# layer and the vectors are inputs, hashed into the manifest.
# =================================================================================================
WORKLOAD_VERSION = "v1"
STAGE = "3.4-workload"
STRATA = corpus_gate.STRATA
SPLITS = corpus_gate.SPLITS
STRATUM_ORDER = ("A", "C", "B-within", "B-cross", "D")  # the rank's tie order (design §2.6)
MINIMAL_PAIR_KINDS = ("policy-condition", "condition-department")
CONDITION_AXIS_NAMES = ("packaging", "grade", "region")
SKEWS = (0.8, 1.1, 1.4)  # illustrative only; the run values are item 7.1's
LRU_REQUESTS = 3000
# The four minimal-pair groups' units, paired so each split gets two (design §2.5, review H2).
TWIN_UNIT_PAIRS = (
    ("phones-term/phones-remedy", ("u-phones-term", "u-phones-return-remedy")),
    ("furniture-term/laptops-term", ("u-furniture-term", "u-laptops-term")),
)


@dataclass
class Record:
    """One workload query. `to_json` gives design.md §3's schema."""

    qa_id: str
    question: str
    doc_ids: tuple[str, ...]
    product_id: str | None
    cluster_id: str
    split_unit: str
    role: str  # seed | paraphrase | natural | probe | d
    origin: str  # pqa | pqa-template | claude
    answerable: bool
    r2_answerable: bool | None
    department: str
    pair_of: str | None = None
    probe_kind: str | None = None
    axis: str | None = None  # the policy document's condition axis (W16)
    stratum: str = ""
    split: str = ""
    popularity_rank: int = 0
    nearest_foreign_cos: float | None = None
    nearest_foreign_same_product: bool | None = None

    def to_json(self) -> dict:
        return {
            "qa_id": self.qa_id,
            "question": self.question,
            "reference_answer": "",
            "doc_ids": list(self.doc_ids),
            "product_id": self.product_id,
            "stratum": self.stratum,
            "probe_kind": self.probe_kind,
            "split": self.split,
            "cluster_id": self.cluster_id,
            "split_unit": self.split_unit,
            "pair_of": self.pair_of,
            "role": self.role,
            "origin": self.origin,
            "answerable": self.answerable,
            "r2_answerable": self.r2_answerable,
            "nearest_foreign_cos": self.nearest_foreign_cos,
            "nearest_foreign_same_product": self.nearest_foreign_same_product,
            "popularity_rank": self.popularity_rank,
        }


def require_complete(inputs: Inputs, layer: dict[str, dict]) -> None:
    for round_ in ROUNDS:
        tasks = all_tasks(inputs, layer)[round_]
        if not tasks:
            raise WorkloadStop(f"round {round_} is not open yet")
        missing = [t for t in tasks if t.key not in layer]
        if missing:
            raise WorkloadStop(f"round {round_} has {len(missing)} open task(s)")


def blind_agrees(inputs: Inputs, layer: dict[str, dict], target: str, answerable: bool,
                 evidence: str | None = None) -> bool:
    """rules.md §8: the query labelled on its own must agree with what it was written to be."""
    row = layer[blind_key(target)]
    if not answerable:
        return not row["answerable"]
    product = inputs.products[layer[target]["doc_id"]]
    return bool(row["answerable"]) and evidence is not None and overlaps(
        product, row["evidence"], evidence
    )


def unit_of_products(inputs: Inputs) -> dict[str, str]:
    return {d: f"u-{unit[0]}" for unit in make_units(inputs) for d in unit}


def policy_unit(doc: dict, shape: str) -> str:
    """(shape group, department): `term` holds both kinds, so a kind twin never crosses; every
    other shape is one group per kind (design §2.5). 11 groups a department."""
    group = "term" if shape == "term" else f"{doc['policy_kind']}-{shape}"
    return f"u-{doc['category']}-{group}"


def swap_kind(swap_answer: str, seed_answer: str, same_answer: object) -> str:
    """rules.md §8, review M5 c: a swap whose answer differs is a trap (`name-swap`); one whose
    answer is the same is kept as `name-swap-same`, never a trap. Two polarities decide; without
    them the writer's `same_answer` mark does."""
    pa, pb = polarity(swap_answer), polarity(seed_answer)
    same = (pa == pb) if pa and pb else bool(same_answer)
    return "name-swap-same" if same else "name-swap"


def construct(inputs: Inputs, layer: dict[str, dict]) -> tuple[list[Record], Counter]:
    """Every query the model layer yields, with the drops counted (rules.md §8). Pure."""
    require_complete(inputs, layer)
    labels, names = first_labels(layer), short_names(layer)
    unit_of = unit_of_products(inputs)
    drops: Counter = Counter()
    out: list[Record] = []

    def spec(qa_id, question, doc_id, cluster, role, origin, answerable, r2, **kw) -> Record:
        rec = Record(qa_id, question, (doc_id,), doc_id, cluster, unit_of[doc_id], role, origin,
                     answerable, r2, inputs.products[doc_id].department, **kw)
        out.append(rec)
        return rec

    first_seed: dict[str, Record] = {}
    for doc_id, refs in seed_refs(inputs, layer).items():
        for i, ref in enumerate(refs):
            line, label = inputs.pool[ref], labels[ref]
            stem = f"q-{doc_id}-{line.line_no}"
            cluster = f"c-{doc_id}-{line.line_no}"
            dependants = PARAPHRASES_PER_SEED + (1 if i < SPEC_LOOKALIKES_PER_PRODUCT else 0)
            if not blind_agrees(inputs, layer, f"seed:{ref}", True, label["evidence"]):
                drops["spec seed: the blind label disagrees (its cluster and probes go too)"] += 1
                drops["spec query dropped with its seed"] += dependants
                continue
            seed = spec(f"{stem}-seed", layer[f"seed:{ref}"]["question"], doc_id, cluster, "seed",
                        "pqa", True, line.r2_answerable)
            for kind in ("close", "far")[:PARAPHRASES_PER_SEED]:
                key = f"para:{ref}:{kind}"
                if blind_agrees(inputs, layer, key, True, label["evidence"]):
                    spec(f"{stem}-para-{kind}", layer[key]["question"], doc_id, cluster,
                         "paraphrase", "claude", True, None)
                else:
                    drops["paraphrase: the blind label disagrees"] += 1
            if i < SPEC_LOOKALIKES_PER_PRODUCT:
                first_seed[doc_id] = seed
                key = f"lookalike:{ref}"
                row = layer[key]
                if blind_agrees(inputs, layer, key, True, row["evidence"]):
                    spec(f"{stem}-look", row["question"], doc_id, f"{cluster}-look", "probe",
                         "claude", True, None, pair_of=seed.qa_id, probe_kind="spec-attribute")
                else:
                    drops["lookalike: the blind label disagrees"] += 1

    for row in rows_of(layer, "swap"):
        a, b, ref = row["from"], row["doc_id"], row["ref"]
        seed = first_seed.get(a)
        if seed is None or seed.qa_id != f"q-{a}-{inputs.pool[ref].line_no}-seed":
            drops["name swap: its seed was dropped"] += 1
            continue
        if not row["answerable"]:
            drops["name swap: the partner's record cannot answer it"] += 1
            continue
        # The seed's real wording re-targeted to another product: pqa-template (rules.md §8).
        spec(f"q-{b}-x-{a}-{inputs.pool[ref].line_no}", row["question"], b,
             f"c-{b}-x-{a}", "probe", "pqa-template", True, None, pair_of=seed.qa_id,
             probe_kind=swap_kind(row["answer"], labels[ref]["answer"], row["same_answer"]))

    for row in natural_pairs_kept(layer):
        sides = {s: inputs.pool[row[s]] for s in ("a", "b")}
        if not all(blind_agrees(inputs, layer, f"seed:{row[s]}", True, row[f"{s}_evidence"])
                   for s in sides):
            drops["natural pair: a blind label disagrees"] += 1
            continue
        doc_id = row["doc_id"]
        ids = {s: f"q-{doc_id}-{sides[s].line_no}-natural" for s in sides}
        for s, other in (("a", "b"), ("b", "a")):
            line = sides[s]
            if row["mark"] == "same":
                spec(ids[s], layer[f"seed:{row[s]}"]["question"], doc_id,
                     f"c-{doc_id}-{sides['a'].line_no}-natural", "natural", "pqa", True,
                     line.r2_answerable)
            else:
                spec(ids[s], layer[f"seed:{row[s]}"]["question"], doc_id,
                     f"c-{doc_id}-{line.line_no}-natural", "probe", "pqa", True,
                     line.r2_answerable, pair_of=ids[other], probe_kind="natural")
    drops["natural pair: marked unanswerable"] += sum(
        1 for r in rows_of(layer, "natural") if r["mark"] == "unanswerable"
    )

    for ref in unanswerable_refs(inputs, layer):
        line = inputs.pool[ref]
        stem, cluster = f"q-{line.doc_id}-{line.line_no}-u", f"c-{line.doc_id}-{line.line_no}-u"
        if not blind_agrees(inputs, layer, f"seed:{ref}", False):
            drops["unanswerable seed: the blind label finds an answer"] += 1
            drops["unanswerable query dropped with its seed"] += UNANSWERABLE_PARAPHRASES
            continue
        spec(f"{stem}-seed", layer[f"seed:{ref}"]["question"], line.doc_id, cluster, "seed",
             "pqa", False, line.r2_answerable)
        for kind in ("close",)[:UNANSWERABLE_PARAPHRASES]:
            key = f"para:{ref}:{kind}"
            if blind_agrees(inputs, layer, key, False):
                spec(f"{stem}-para-{kind}", layer[key]["question"], line.doc_id, cluster,
                     "paraphrase", "claude", False, None)
            else:
                drops["unanswerable paraphrase: the blind label finds an answer"] += 1

    for doc_id, policy in sorted(d_assignments(inputs, layer).items()):
        out.append(Record(f"q-{doc_id}-d", layer[f"d:{doc_id}"]["question"], (doc_id, policy),
                          doc_id, f"c-{doc_id}-d", unit_of[doc_id], "d", "claude", True, None,
                          inputs.products[doc_id].department))

    for cell in plan_cells(inputs, layer):
        row = layer[f"cell:{cell.cell_id}"]
        doc = inputs.policies[cell.doc_id]
        axis = doc["condition"]["axis"] if doc.get("condition") else None
        unit = policy_unit(doc, cell.shape)
        if cell.variant == "dept":
            members = [(f"w{i + 1}", None, w) for i, w in enumerate(row["wordings"])]
        else:
            members = [(p, p, row["wordings"][0].replace("{name}", names[p]))
                       for p in cell.products]
        for n, (tag, product_id, question) in enumerate(members):
            problems = condition_problems(inputs, question, cell.doc_id)
            if problems:
                raise WorkloadStop(f"cell {cell.cell_id}: a filled query {problems[0]}")
            pair = f"q-{cell.pair_cell}-{tag}" if cell.pair_cell else None
            role = "probe" if pair else ("seed" if n == 0 else "paraphrase")
            out.append(Record(f"q-{cell.cell_id}-{tag}", question, (cell.doc_id,), product_id,
                              f"c-{cell.cell_id}", unit, role, row["origin"], True, None,
                              doc["category"], pair_of=pair,
                              probe_kind=cell.probe_kind if pair else None, axis=axis))
    return out, drops


def assign_split(records: list[Record], inputs: Inputs) -> dict[str, str]:
    """design.md §2.5, pre-registered and never re-drawn:

    1. the four minimal-pair groups' units, each pair to opposite splits, the direction by the
       first bit of `sha256(SEED:twin:<pair>)`;
    2. every other policy unit, departments in order and each department's units in hash order,
       alternating validation, test, ... and continuing across departments from step 1's count;
    3. product units, leaves in order and each leaf's units in hash order, each to the split with
       fewer queries so far in its department (ties: validation).
    """
    by_unit: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        by_unit[r.split_unit].append(r)
    split_of: dict[str, str] = {}
    count = 0
    for pair_name, units in TWIN_UNIT_PAIRS:
        first = int(h("twin", pair_name)[0], 16) >> 3  # the first bit
        for unit, s in zip(units, (SPLITS[first], SPLITS[1 - first]), strict=True):
            if unit in by_unit:
                split_of[unit] = s
            count += 1
    policy_units = sorted(
        (u for u, rs in by_unit.items() if rs[0].doc_ids[0].startswith("policy-") and
         u not in split_of),
        key=lambda u: (by_unit[u][0].department, h("policy-unit", u)),
    )
    for unit in policy_units:
        split_of[unit] = SPLITS[count % 2]
        count += 1
    totals: Counter = Counter()
    for unit, s in split_of.items():
        totals[(by_unit[unit][0].department, s)] += len(by_unit[unit])
    leaf_units = sorted((u for u in by_unit if u not in split_of),
                        key=lambda u: (inputs.products[u[2:]].leaf, h("unit-split", u)))
    for unit in leaf_units:
        dept = by_unit[unit][0].department
        s = min(SPLITS, key=lambda s: (totals[(dept, s)], SPLITS.index(s)))
        split_of[unit] = s
        totals[(dept, s)] += len(by_unit[unit])
    return split_of


def assign_stratum(rec: Record, by_id: dict[str, Record], members: list[Record],
                   vectors: dict[str, list[float]]) -> str:
    """design.md §2.4, first match wins: D, B-within, B-cross, A, C."""
    kinds = {d.split("-", 1)[0] for d in rec.doc_ids}
    if {"product", "policy"} <= kinds:
        return "D"
    if rec.pair_of:
        target = by_id[rec.pair_of]
        if rec.probe_kind == "condition-department" or target.product_id == rec.product_id:
            return "B-within"
        return "B-cross"
    best = max(
        (corpus_gate.cosine(vectors[rec.qa_id], vectors[m.qa_id]) for m in members
         if m.qa_id != rec.qa_id),
        default=-1.0,
    )
    return "A" if best >= corpus_gate.SIM_FLOOR else "C"


def rank(records: list[Record]) -> list[Record]:
    """design.md §2.6: per record, stratified. Inside a split, each stratum's records in
    `sha256(SEED:rank:qa_id)` order; at every position the stratum furthest below its share of
    records so far goes next (exact fractions; ties in STRATUM_ORDER). Every prefix holds each
    stratum's count within one of its share."""
    by = {s: sorted((r for r in records if r.stratum == s), key=lambda r: h("rank", r.qa_id))
          for s in STRATUM_ORDER}
    n = len(records)
    taken: Counter = Counter()
    out = []
    for pos in range(1, n + 1):
        live = [s for s in STRATUM_ORDER if taken[s] < len(by[s])]
        best = max(live, key=lambda s: (Fraction(len(by[s]) * pos, n) - taken[s],
                                        -STRATUM_ORDER.index(s)))
        out.append(by[best][taken[best]])
        taken[best] += 1
    for i, r in enumerate(out, 1):
        r.popularity_rank = i
    return out


def nearest_foreign(records: list[Record], vectors: dict[str, list[float]]) -> None:
    """design.md §3, review M3: per record, the highest cosine to a same-split query with other
    `doc_ids`, and whether that query is about the same product. The traps nobody built."""
    norms = {r.qa_id: corpus_gate._norm(vectors[r.qa_id]) for r in records}
    for s in SPLITS:
        group = [r for r in records if r.split == s]
        best: dict[str, tuple[float, Record | None]] = {r.qa_id: (-1.0, None) for r in group}
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if set(a.doc_ids) == set(b.doc_ids):
                    continue
                sim = corpus_gate._cosine_with_norms(vectors[a.qa_id], vectors[b.qa_id],
                                                     norms[a.qa_id], norms[b.qa_id])
                for x, y in ((a, b), (b, a)):
                    if sim > best[x.qa_id][0]:
                        best[x.qa_id] = (sim, y)
        for r in group:
            sim, other = best[r.qa_id]
            if other is not None:
                r.nearest_foreign_cos = round(sim, 4)
                r.nearest_foreign_same_product = (
                    r.product_id is not None and other.product_id == r.product_id
                )


@dataclass
class Workload:
    records: list[Record]  # validation by rank, then test by rank
    split_of: dict[str, str]
    drops: Counter
    leaks: dict = field(default_factory=dict)


def cross_split_leaks(records: list[Record], vectors: dict[str, list[float]]) -> dict:
    """design.md §2.5 and U9: the leak the split leaves. The highest cosine between two queries
    on one document in different splits, and between a D query and a `term` query of its policy
    document in different splits."""
    on_doc: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        for d in r.doc_ids:
            on_doc[d].append(r)
    same_doc = d_term = -1.0
    for rs in on_doc.values():
        for i, a in enumerate(rs):
            for b in rs[i + 1:]:
                if a.split == b.split:
                    continue
                sim = corpus_gate.cosine(vectors[a.qa_id], vectors[b.qa_id])
                same_doc = max(same_doc, sim)
                if {a.role, b.role} & {"d"} and any(":term" in x.qa_id for x in (a, b)):
                    d_term = max(d_term, sim)
    return {"same_document_max_cosine": round(same_doc, 4) if same_doc >= 0 else None,
            "d_against_term_max_cosine": round(d_term, 4) if d_term >= 0 else None}


def build(inputs: Inputs, layer: dict[str, dict], vectors: dict[str, dict]) -> Workload:
    """Pure: model layer and vectors in, the ranked and split workload out. Stops (never re-draws)
    on any failed check."""
    records, drops = construct(inputs, layer)
    stale = [r.qa_id for r in records
             if r.qa_id not in vectors or vectors[r.qa_id]["question"] != r.question]
    if stale:
        raise WorkloadStop(f"{len(stale)} quer(y|ies) have no current vector; run workload-embed")
    vec = {r.qa_id: vectors[r.qa_id]["vector"] for r in records}
    split_of = assign_split(records, inputs)
    by_id = {r.qa_id: r for r in records}
    clusters: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        r.split = split_of[r.split_unit]
        clusters[r.cluster_id].append(r)
    for r in records:
        r.stratum = assign_stratum(r, by_id, clusters[r.cluster_id], vec)
    nearest_foreign(records, vec)
    ranked = [r for s in SPLITS for r in rank([x for x in records if x.split == s])]
    check_workload(inputs, ranked)
    return Workload(ranked, split_of, drops, cross_split_leaks(ranked, vec))


def check_workload(inputs: Inputs, records: list[Record]) -> None:
    """W1, W2, W5 (the gate's own shape check), W6 and W16. A failure stops the build."""
    queries = [corpus_gate.Query(r.qa_id, r.question, r.doc_ids, r.product_id or "", r.stratum,
                                 "", r.split, r.cluster_id, r.pair_of or "", r.probe_kind or "")
               for r in records]
    shape = corpus_gate.check_workload_shape(queries)
    problems = list(shape.detail)
    for r in records:
        if r.product_id is not None and r.product_id not in inputs.products:
            problems.append(f"{r.qa_id}: product_id is not a selected product (W6)")
        for d in r.doc_ids:
            if d not in inputs.products and d not in inputs.policies:
                problems.append(f"{r.qa_id}: doc_id {d} is not in the corpus (W6)")
        policy_lane = any(d.startswith("policy-") for d in r.doc_ids)
        if policy_lane and r.product_id and inputs.products[r.product_id].risky:
            problems.append(f"{r.qa_id}: names a risky product in a policy or D query (W6)")
    for dept in sorted({r.department for r in records}):
        for s in SPLITS:
            if not any(r.department == dept and r.split == s for r in records):
                problems.append(f"department {dept} has no query in {s} (W16)")
    for axis in CONDITION_AXIS_NAMES:
        for s in SPLITS:
            if not any(r.axis == axis and r.split == s for r in records):
                problems.append(f"condition axis {axis} has no query in {s} (W16)")
    for s in SPLITS:
        twins = sum(1 for r in records if r.split == s and r.probe_kind in MINIMAL_PAIR_KINDS)
        if twins < MIN_TWINS_PER_SPLIT:
            problems.append(f"{s} holds {twins} minimal-pair twins, below {MIN_TWINS_PER_SPLIT}"
                            " (W16, T19)")
    if problems:
        raise WorkloadStop("the workload fails its checks:\n  " + "\n  ".join(problems[:20]))


# --- what the runs will see (design.md §2.6, review M1, L5) ----------------------------------------
def zipf_cdf(n: int, skew: float) -> list[float]:
    """`ask.js`'s CDF: P(rank) proportional to 1 / rank^skew over ranks 1..n."""
    weights = [1 / (i + 1) ** skew for i in range(n)]
    total = sum(weights)
    out, acc = [], 0.0
    for w in weights:
        acc += w
        out.append(acc / total)
    return out


def traffic_shares(records: list[Record], skew: float) -> dict[str, dict[str, float]]:
    """The exact share of requests per stratum and per probe kind at one skew, from the ranks."""
    weights = [1 / r.popularity_rank ** skew for r in records]
    total = sum(weights)
    strata: Counter = Counter()
    kinds: Counter = Counter()
    for r, w in zip(records, weights, strict=True):
        strata[r.stratum] += w / total
        kinds[r.probe_kind or "none"] += w / total
    return {"stratum": {k: round(v, 4) for k, v in sorted(strata.items())},
            "probe_kind": {k: round(v, 4) for k, v in sorted(kinds.items())}}


def simulate_lru(records: list[Record], skew: float, requests: int = LRU_REQUESTS) -> dict:
    """A seeded, model-free run of one split file: Zipf over its ranks (as `ask.js`), an LRU of
    `round(0.25 x K)` entries, one entry per query. Counts Tier-1 repeats, misses that find a
    cluster-mate cached (where Tier 2 would decide), and each probe kind requested while its
    partner is cached (an encounter with its trap)."""
    split = records[0].split if records else ""
    rng = random.Random(int(h("lru", split, skew)[:16], 16))
    cdf = zipf_cdf(len(records), skew)
    capacity = corpus_gate.derive_capacity(len(records))
    cache: OrderedDict[str, Record] = OrderedDict()
    live_clusters: Counter = Counter()
    tier1 = tier2_chance = 0
    encounters: Counter = Counter()
    for _ in range(requests):
        r = records[bisect.bisect_left(cdf, rng.random())]
        if r.qa_id in cache:
            tier1 += 1
            cache.move_to_end(r.qa_id)
            continue
        if live_clusters[r.cluster_id]:
            tier2_chance += 1
        if r.pair_of and r.pair_of in cache:
            encounters[r.probe_kind] += 1
        cache[r.qa_id] = r
        live_clusters[r.cluster_id] += 1
        if capacity and len(cache) > capacity:
            _, old = cache.popitem(last=False)
            live_clusters[old.cluster_id] -= 1
    return {
        "capacity": capacity,
        "requests": requests,
        "tier1_hit_rate": round(tier1 / requests, 4),
        "misses_with_a_cached_cluster_mate": tier2_chance,
        "probe_encounters": dict(sorted(encounters.items())),
    }


# --- outputs ---------------------------------------------------------------------------------------
def canonical(obj: object) -> bytes:
    return (json.dumps(obj, indent=1, ensure_ascii=True) + "\n").encode()


def counts_of(records: list[Record]) -> dict:
    return {
        "records": len(records),
        "k_distinct_queries": len({corpus_gate.normalize_t1(r.question) for r in records}),
        "cache_capacity": corpus_gate.derive_capacity(
            len({corpus_gate.normalize_t1(r.question) for r in records})),
        "strata": dict(sorted(Counter(r.stratum for r in records).items())),
        "probe_kind": dict(sorted(Counter(r.probe_kind or "none" for r in records).items())),
        "role": dict(sorted(Counter(r.role for r in records).items())),
        "origin": dict(sorted(Counter(r.origin for r in records).items())),
        "department": dict(sorted(Counter(r.department for r in records).items())),
        "axis": dict(sorted(Counter(r.axis or "none" for r in records).items())),
        "answerable_false": sum(1 for r in records if not r.answerable),
        "minimal_pair_twins": sum(1 for r in records if r.probe_kind in MINIMAL_PAIR_KINDS),
        "trap_fraction": round(corpus_gate.trap_fraction(
            [corpus_gate.Query(r.qa_id, r.question, stratum=r.stratum,
                               probe_kind=r.probe_kind or "") for r in records]), 4),
    }


def make_manifest(workload: Workload, files: dict[str, bytes], inputs_digest: dict) -> dict:
    """The tracked record (spec W9): hashes and counts only. No question, no asin, no qa_id; the
    product units appear only as a hash of their list."""
    units = sorted(workload.split_of)
    product_units = [u for u in units if u.startswith("u-product-")]
    return {
        "stage": STAGE,
        "workload_version": WORKLOAD_VERSION,
        "seed": SEED,
        "model_id": MODEL_ID,
        "inputs": inputs_digest,
        "outputs": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
        "units": {
            "product_units": len(product_units),
            "policy_units": len(units) - len(product_units),
            "unit_list_sha256": hashlib.sha256(canonical(units)).hexdigest(),
            "assignment_sha256": hashlib.sha256(
                canonical(sorted(workload.split_of.items()))).hexdigest(),
        },
        "counts": {
            "whole": counts_of(workload.records),
            **{s: counts_of([r for r in workload.records if r.split == s]) for s in SPLITS},
        },
        "drops": dict(sorted(workload.drops.items())),
        "cross_split": workload.leaks,
    }


def output_files(workload: Workload) -> dict[str, bytes]:
    whole = [r.to_json() for r in workload.records]
    files = {f"workload-{WORKLOAD_VERSION}.json": canonical(whole)}
    for s in SPLITS:
        files[f"workload-{WORKLOAD_VERSION}-{s}.json"] = canonical(corpus_gate.derive_split(whole, s))
    return files


MANIFEST_NAME = "workload-manifest.json"


def write_outputs(files: dict[str, bytes], manifest: dict, data_dir: Path,
                  work_dir: Path = WORK_DIR) -> None:
    """Every file to a temporary name in the ignored work folder first (it holds PQA text, so a
    crash must not leave it where git can see it), then into place, the manifest last: a run that
    dies half way leaves a manifest that no longer matches, and `workload-verify` says so."""
    work_dir.mkdir(parents=True, exist_ok=True)
    tmp = {name: work_dir / f".tmp-{os.getpid()}-{name}" for name in [*files, MANIFEST_NAME]}
    try:
        for name, data in files.items():
            tmp[name].write_bytes(data)
        tmp[MANIFEST_NAME].write_bytes(canonical(manifest))
        for name in [*files, MANIFEST_NAME]:
            os.replace(tmp[name], data_dir / name)
    finally:
        for path in tmp.values():
            path.unlink(missing_ok=True)


def verify_outputs(inputs: Inputs, data_dir: Path) -> list[str]:
    """`make workload-verify`: re-hash the three files against the manifest, re-derive the split
    files (the gate's own check), and re-run the shape, W6 and W16 checks on what is on disk."""
    manifest_path = data_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        return [f"no {MANIFEST_NAME}"]
    manifest = json.loads(manifest_path.read_text())
    problems = []
    for name, digest in manifest["outputs"].items():
        path = data_dir / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"{name} is missing or differs from the manifest")
    if problems:
        return problems
    whole = data_dir / f"workload-{WORKLOAD_VERSION}.json"
    split_files = corpus_gate.check_split_files(whole)
    problems += split_files.detail
    records = [
        Record(r["qa_id"], r["question"], tuple(r["doc_ids"]), r["product_id"], r["cluster_id"],
               r["split_unit"], r["role"], r["origin"], r["answerable"], r["r2_answerable"],
               _department(inputs, r), r["pair_of"], r["probe_kind"], _axis(inputs, r),
               r["stratum"], r["split"], r["popularity_rank"])
        for r in json.loads(whole.read_text())
    ]
    try:
        check_workload(inputs, records)
    except WorkloadStop as e:
        problems.append(str(e))
    return problems


def _department(inputs: Inputs, r: dict) -> str:
    d = r["doc_ids"][0]
    return inputs.products[d].department if d in inputs.products else inputs.policies[d]["category"]


def _axis(inputs: Inputs, r: dict) -> str | None:
    for d in r["doc_ids"]:
        cond = inputs.policies.get(d, {}).get("condition")
        if cond and len(r["doc_ids"]) == 1:
            return cond["axis"]
    return None


def embed_all(inputs: Inputs, layer: dict[str, dict],
              embed: Callable[[str], list[float]]) -> dict[str, dict]:
    """The only model call: every query's vector under the frozen query path (`search_query: `),
    keyed by qa_id with its text, so a changed question cannot reuse an old vector. `embed` is
    injected; tests pass a fake."""
    records, _ = construct(inputs, layer)
    return {r.qa_id: {"question": r.question, "vector": embed(r.question)}
            for r in sorted(records, key=lambda r: r.qa_id)}


def build_report(workload: Workload, manifest: dict) -> str:
    """evidence/build.md: counts only -- no question, no asin, no qa_id."""
    lines = ["# Build report — item 3.4 (written by `make workload-build`)", ""]
    for name in ("whole", *SPLITS):
        c = manifest["counts"][name]
        lines += [
            f"## {name}", "",
            (
                f"- records {c['records']} · K {c['k_distinct_queries']} · capacity "
                f"{c['cache_capacity']} · unanswerable {c['answerable_false']} · minimal-pair "
                f"twins {c['minimal_pair_twins']} · trap fraction {c['trap_fraction']}"
            ),
            f"- strata {c['strata']}",
            f"- probe kinds {c['probe_kind']}",
            f"- departments {c['department']} · axes {c['axis']}",
            f"- roles {c['role']} · origins {c['origin']}",
            "",
        ]
    for s in SPLITS:
        recs = [r for r in workload.records if r.split == s]
        lines += [f"## {s}: what a run sees", ""]
        for skew in SKEWS:
            sim = simulate_lru(recs, skew)
            shares = traffic_shares(recs, skew)
            lines += [
                f"- skew {skew}: traffic by stratum {shares['stratum']}",
                f"  by probe kind {shares['probe_kind']}",
                (
                    f"  LRU ({sim['requests']} requests, capacity {sim['capacity']}): Tier-1 hit "
                    f"rate {sim['tier1_hit_rate']}, misses with a cached cluster-mate "
                    f"{sim['misses_with_a_cached_cluster_mate']}, probe encounters "
                    f"{sim['probe_encounters']}"
                ),
            ]
        lines.append("")
    lines += ["## Cosines", ""]
    for s in STRATA:
        vals = sorted(r.nearest_foreign_cos for r in workload.records
                      if r.stratum == s and r.nearest_foreign_cos is not None)
        if vals:
            lines.append(f"- {s}: nearest foreign cosine min {vals[0]} · median "
                         f"{vals[len(vals) // 2]} · max {vals[-1]} · ≥ 0.85: "
                         f"{sum(v >= corpus_gate.SIM_FLOOR for v in vals)}")
    lines += [f"- across the splits: {workload.leaks}"]
    lines += ["", "## Drops (rules.md §8)", ""]
    lines += [f"- {k}: {v}" for k, v in sorted(workload.drops.items())] or ["- none"]
    return "\n".join(lines) + "\n"


# =================================================================================================
# The pass-1 report (plan step 8)
# =================================================================================================
LABELS_REPORT_PATH = TRAIL / "evidence" / "labels.md"
YIELD_FLOOR = 200  # design U1: below it the spec half shrinks, and the author decides
LABEL_ROUND_TYPES = frozenset({"name", "label", "policy", "natural"})
NOT_ASSIGNED = ("ambiguous", "not_covered", "not_policy")


def _rate(k: int, n: int) -> str:
    ci = select_pqa.wilson(k, n)
    return f"{k} / {n} ({k / n:.3f}, Wilson 95 % {ci[0]} – {ci[1]})" if ci else f"{k} / {n}"


def batch_totals(text: str) -> dict[str, Counter]:
    """Batches and rows accepted, skipped and rejected, per label-round kind, from the table in
    evidence/batches.md. A later round's batches are left out."""
    out = {"pass 1": Counter(), "relabel": Counter()}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 8 or not cells[0][:4].isdigit():
            continue
        accepted = Counter({t: int(n) for t, n in (p.rsplit(" ", 1) for p in cells[5].split(", "))})
        if set(accepted) == {"relabel"}:
            kind = "relabel"
        elif set(accepted) <= LABEL_ROUND_TYPES:
            kind = "pass 1"
        else:
            continue
        out[kind].update(batches=1, accepted=accepted.total(), skipped=int(cells[6]),
                         rejected=int(cells[7]))
    return out


def labels_report(inputs: Inputs, layer: dict[str, dict], batches_text: str) -> str:
    """evidence/labels.md: counts only -- no question, no asin, no product doc_id."""
    labels = first_labels(layer)
    depts = departments(inputs)
    by: dict[tuple[str, bool], list[bool]] = defaultdict(list)  # (department, R2 tag) -> Claude
    for ref, r in labels.items():
        line = inputs.pool[ref]
        by[(line.department, bool(line.r2_answerable))].append(bool(r["answerable"]))

    def cell(rows: list[bool]) -> str:
        return f"{sum(rows)} / {len(rows)}"

    lines = ["# Pass-1 labels — item 3.4 (written by `make workload-labels`)", ""]
    lines += [
        "## Yield: Claude-answerable among the labelled spec questions", "",
        "| Department | R2-answerable | R2-unanswerable (sample) | Both |",
        "| :--- | ---: | ---: | ---: |",
    ]
    for d in [*depts, None]:
        keep = [d] if d else depts
        yes = [v for k in keep for v in by[(k, True)]]
        no = [v for k in keep for v in by[(k, False)]]
        lines.append(f"| {d or '**all**'} | {cell(yes)} | {cell(no)} | {cell(yes + no)} |")
    yes_all = [v for d in depts for v in by[(d, True)]]
    no_all = [v for d in depts for v in by[(d, False)]]
    total = sum(yes_all) + sum(no_all)
    verdict = "continue" if total >= YIELD_FLOOR else "STOP: show the author (plan step 8)"
    lines += ["", f"U1 check: yield {total} against the floor {YIELD_FLOOR} → {verdict}.", ""]

    precision = _rate(sum(yes_all), len(yes_all))
    npv = _rate(len(no_all) - sum(no_all), len(no_all))
    lines += [
        "## R2 against Claude (Claude's label as the reference)", "",
        f"- Precision of R2 (Claude-answerable among R2-answerable): {precision}",
        f"- NPV of R2 (Claude-unanswerable among the R2-unanswerable sample): {npv}",
        (f"  The sample is the first {R2_UNANSWERABLE_SAMPLE} per department in hash order, so the "
         "NPV estimates the pool's R2-unanswerable spec questions; the precision is a census."),
        "",
    ]

    pairs = [(labels[f"{r['doc_id']}:{r['line_no']}"], r) for r in rows_of(layer, "relabel")]
    both = [(a, b) for a, b in pairs if a["answerable"] and b["answerable"]]
    same = _rate(sum(a["answerable"] == b["answerable"] for a, b in pairs), len(pairs))
    lost = sum(a["answerable"] and not b["answerable"] for a, b in pairs)
    gained = sum(b["answerable"] and not a["answerable"] for a, b in pairs)
    overlap = sum(overlaps(inputs.products[a["doc_id"]], a["evidence"], b["evidence"])
                  for a, b in both)
    lines += [
        f"## Repeat agreement (RELABEL = {RELABEL})", "",
        f"- Same answerable flag: {same}",
        f"- Pass 1 answerable, repeat not: {lost} · pass 1 not, repeat answerable: {gained}",
        f"- Both answerable, evidence overlapping (same field, spans intersect): {overlap} / {len(both)}",
        "",
    ]

    lines += ["## Imports (evidence/batches.md)", ""]
    for kind, c in batch_totals(batches_text).items():
        lines.append(f"- {kind}: {c['batches']} batches · {c['accepted']} rows accepted · "
                     f"{c['skipped']} skipped · {c['rejected']} rejected")
    lines.append("")

    policy = rows_of(layer, "policy")

    def kind_of(r: dict) -> str:
        return r["assign"] if r["assign"] in NOT_ASSIGNED else "assigned"

    lines += [
        "## Policy assignments (R7 a)", "",
        "| Department | assigned | ambiguous | not_covered | not_policy |",
        "| :--- | ---: | ---: | ---: | ---: |",
    ]
    for d in [*depts, None]:
        c = Counter(kind_of(r) for r in policy if d is None or inputs.products[r["doc_id"]].department == d)
        lines.append(f"| {d or '**all**'} | " + " | ".join(
            str(c[k]) for k in ("assigned", *NOT_ASSIGNED)) + " |")
    assigned = Counter((r["assign"], r["shape"], r["variant"]) for r in policy if kind_of(r) == "assigned")
    ambiguous = Counter((r["kind"], r["shape"]) for r in policy if r["assign"] == "ambiguous")
    lines += ["", "Assigned, by document, shape and variant:", ""]
    lines += [f"- {doc} · {shape}{' · ' + v if v else ''}: {n}"
              for (doc, shape, v), n in sorted(assigned.items())] or ["- none"]
    lines += ["", "Ambiguous, by kind and shape:", ""]
    lines += [f"- {k} · {shape}: {n}" for (k, shape), n in sorted(ambiguous.items())] or ["- none"]

    marks = Counter(r["mark"] for r in rows_of(layer, "natural"))
    seeds = seed_refs(inputs, layer)
    short = sum(len(v) < SPEC_SEEDS_PER_PRODUCT for v in seeds.values())
    n_seeds = sum(len(v) for v in seeds.values())
    n_unanswerable = len(unanswerable_refs(inputs, layer))
    lines += [
        "", "## Names, natural pairs and what pass 2 draws on", "",
        f"- Names: {len(rows_of(layer, 'name'))} of {len(inputs.products)} products",
        "- Natural pairs: " + ", ".join(f"{m} {n}" for m, n in sorted(marks.items())),
        f"- Spec seeds: {n_seeds} ({SPEC_SEEDS_PER_PRODUCT} per product; {short} products have fewer)",
        f"- Unanswerable seeds: {n_unanswerable} ({UNANSWERABLE_SEEDS} per department at most)",
    ]
    return "\n".join(lines) + "\n"


# =================================================================================================
# CLI
# =================================================================================================
def rules_sha256_committed(rules_path: Path = RULES_PATH) -> str:
    """rules.md's sha256, refusing while it is missing, uncommitted or changed (spec W8, W18)."""
    if not rules_path.is_file():
        raise WorkloadStop(f"{rules_path} does not exist")
    rel = rules_path.relative_to(REPO_ROOT)
    git = ["git", "-C", str(REPO_ROOT)]
    tracked = subprocess.run([*git, "ls-files", "--error-unmatch", str(rel)],
                             capture_output=True, check=False)
    clean = subprocess.run([*git, "diff", "--quiet", "HEAD", "--", str(rel)],
                           capture_output=True, check=False)
    if tracked.returncode or clean.returncode:
        raise WorkloadStop(f"{rel} is not committed as it stands; commit the rules first (W18)")
    return hashlib.sha256(rules_path.read_bytes()).hexdigest()


def read_inputs(selection: Path, draft_dir: Path, policy_dir: Path) -> Inputs:
    try:
        return load_inputs(select_pqa.iter_selection(selection, draft_dir), policy_dir)
    except select_pqa.SelectionMismatch as e:
        raise WorkloadStop(f"the 3.2 drafts do not match their manifest: {e}") from e


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs_digest(selection: Path, policy_dir: Path, layer_path: Path, vectors_path: Path,
                  rules_sha: str) -> dict:
    policies = sorted((p.name, sha256_file(p)) for p in policy_dir.glob("*.json"))
    return {
        "selection_sha256": sha256_file(selection),
        "policies_sha256": hashlib.sha256(canonical(policies)).hexdigest(),
        "rules_sha256": rules_sha,
        "model_layer_sha256": sha256_file(layer_path),
        "vectors_sha256": sha256_file(vectors_path),
    }


MEMORY_RED = 4  # kern.memorystatus_vm_pressure_level: critical


def memory_level() -> int | None:
    out = subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
                         capture_output=True, text=True, check=False)
    return int(out.stdout) if out.returncode == 0 and out.stdout.strip().isdigit() else None


def status_lines(inputs: Inputs, layer: dict[str, dict]) -> Iterator[str]:
    tasks = all_tasks(inputs, layer)
    for round_ in ROUNDS:
        by_type = Counter(t.type for t in tasks[round_])
        done = Counter(t.type for t in tasks[round_] if t.key in layer)
        if not by_type:
            yield f"{round_:<6} not open"
            continue
        parts = ", ".join(f"{t} {done[t]}/{n}" for t, n in sorted(by_type.items()))
        yield f"{round_:<6} {parts}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--selection", type=Path, default=SELECTION_PATH)
    ap.add_argument("--draft-dir", type=Path, default=DRAFT_DIR)
    ap.add_argument("--policy-dir", type=Path, default=POLICY_DIR)
    ap.add_argument("--layer", type=Path, default=LAYER_PATH)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="open tasks per round, counts only")
    sub.add_parser("labels", help="write the pass-1 report, evidence/labels.md (counts only)")
    sp = sub.add_parser("sheets", help="write the open tasks of one round as sheets")
    sp.add_argument("--round", choices=ROUNDS, required=True)
    sp.add_argument("--out", type=Path, required=True)
    ip = sub.add_parser("import", help="check a rows file and append its valid rows")
    ip.add_argument("rows", type=Path)
    ip.add_argument("--model", default=MODEL_ID)
    sub.add_parser("embed", help="embed every query with the frozen model (Ollama)")
    sub.add_parser("build", help="build the workload files and the manifest (no model)")
    sub.add_parser("verify", help="re-hash and re-check the workload files (no model)")
    args = ap.parse_args(argv)

    try:
        inputs = read_inputs(args.selection, args.draft_dir, args.policy_dir)
        layer = load_layer(args.layer)
        if args.command == "status":
            for line in status_lines(inputs, layer):
                print(line)
            return 0
        if args.command == "labels":
            if not round_complete(all_tasks(inputs, layer)["label"], layer):
                raise WorkloadStop("the label round is not complete; see make workload-status")
            text = labels_report(inputs, layer, BATCHES_PATH.read_text())
            LABELS_REPORT_PATH.write_text(text)
            print(text, end="")
            return 0
        if args.command == "verify":
            problems = verify_outputs(inputs, DATA_DIR)
            for line in problems:
                print(f"  FAIL {line}")
            if problems:
                return 2
            manifest = json.loads((DATA_DIR / MANIFEST_NAME).read_text())
            for name in ("whole", *SPLITS):
                c = manifest["counts"][name]
                print(f"  {name:<10} K={c['k_distinct_queries']} capacity={c['cache_capacity']}")
            print("workload-verify: PASS")
            return 0
        rules_sha = rules_sha256_committed()
        if args.command == "embed":
            level = memory_level()
            print(f"memory pressure level: {level} (record it in evidence/memory.md)")
            if level is None or level >= MEMORY_RED:
                raise WorkloadStop("memory pressure is red or unknown; no model is loaded")
            # Imported here, so no other command needs Ollama or the rag package.
            from rag.embedding import OllamaEmbedding

            embedder = OllamaEmbedding()
            vectors = embed_all(inputs, layer, embedder.get_query_embedding)
            WORK_DIR.mkdir(parents=True, exist_ok=True)
            VECTORS_PATH.write_bytes(canonical(vectors))
            print(f"{len(vectors)} vectors -> {VECTORS_PATH} (sha256 {sha256_file(VECTORS_PATH)[:16]})")
            return 0
        if args.command == "build":
            if not VECTORS_PATH.is_file():
                raise WorkloadStop("no vectors; run make workload-embed first")
            vectors = json.loads(VECTORS_PATH.read_text())
            workload = build(inputs, layer, vectors)
            files = output_files(workload)
            digest = inputs_digest(args.selection, args.policy_dir, args.layer, VECTORS_PATH,
                                   rules_sha)
            manifest = make_manifest(workload, files, digest)
            write_outputs(files, manifest, DATA_DIR)
            BUILD_REPORT_PATH.write_text(build_report(workload, manifest))
            for name in ("whole", *SPLITS):
                c = manifest["counts"][name]
                print(f"  {name:<10} records={c['records']} K={c['k_distinct_queries']} "
                      f"capacity={c['cache_capacity']} twins={c['minimal_pair_twins']}")
            print(f"manifest sha256 {sha256_file(DATA_DIR / MANIFEST_NAME)}")
            return 0
        if args.command == "sheets":
            paths = write_sheets(inputs, layer, args.round, args.out, rules_sha)
            n = len(open_tasks(inputs, layer, args.round))
            print(f"{len(paths)} sheet(s), {n} open task(s) -> {args.out}")
            return 0
        at = datetime.now(UTC)
        report = import_rows(args.rows, args.layer, inputs, rules_sha, args.model, lambda: at)
        for n, key, problems in report.rejects:
            print(f"  REJECT line {n} {key}")
            for p in problems:
                print(f"         {p}")
        line = batch_line(report, args.rows.name, rules_sha, args.model, at)
        print(line)
        if report.accepted:
            with BATCHES_PATH.open("a") as f:
                f.write(line + "\n")
        return 1 if report.rejects else 0
    except WorkloadStop as e:
        print(f"STOP — {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
