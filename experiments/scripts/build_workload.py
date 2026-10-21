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
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
TRAIL = REPO_ROOT / "docs" / "work" / "2026-10-21-workload-generator"
RULES_PATH = TRAIL / "rules.md"
BATCHES_PATH = TRAIL / "evidence" / "batches.md"

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
    sp = sub.add_parser("sheets", help="write the open tasks of one round as sheets")
    sp.add_argument("--round", choices=ROUNDS, required=True)
    sp.add_argument("--out", type=Path, required=True)
    ip = sub.add_parser("import", help="check a rows file and append its valid rows")
    ip.add_argument("rows", type=Path)
    ip.add_argument("--model", default=MODEL_ID)
    args = ap.parse_args(argv)

    try:
        inputs = read_inputs(args.selection, args.draft_dir, args.policy_dir)
        layer = load_layer(args.layer)
        if args.command == "status":
            for line in status_lines(inputs, layer):
                print(line)
            return 0
        rules_sha = rules_sha256_committed()
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
