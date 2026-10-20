"""Item 3.3: check the authored policy documents before they join the corpus.

    make policy-check                          # data/policies-v1, the tracked source folder
    make policy-check POLICY_DIR=<folder>

`data/policies-v1/` is the source of v1's policy documents, **not a dataset version**: 3.6 copies it
into `data/v1/`. Everything here is offline (no Redis, no Ollama, no model), so it is the loop to
run while writing. The rules it checks are `docs/work/2026-10-20-policy-documents/design.md` §3–§6,
committed before the first document was written:

- **Schema** (P3): seven fields; `category` a department; `policy_kind` a pool tag; `condition` null
  or one declared axis and value; `doc_id` derived from those three; every department has a return
  and a warranty family, and every family is one document or a complete split; the title names
  the declared value; ASCII only.
- **Terms and numbers** (P12): the only numbers in a text are its `terms`, written exactly as in
  `terms` (a number and its unit attached, which is what the support gate's numeric arm reads);
  at most one duration and one amount; no duration in words; siblings' terms differ.
- **Chunks** (P1, P4, P13): the real ingest path, `rag.ingest.record_to_document` then
  `SentenceSplitter` at the frozen size and overlap; >= 3 chunks; chunk 0 holds the main term;
  no two chunks identical (identical text embeds identically, and the index's tie order would then
  pick the namespace).
- **G5** (P2): `corpus_gate.check_g5`, the one implementation of the condition scan.

Exit 0 on pass; 1 on any failure (every failure printed); 2 when the folder is missing or empty.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path

import build_pqa
import select_pqa
from corpus_gate import CONDITION_AXES, check_g5, condition_hits

REPO_ROOT = build_pqa.REPO_ROOT
DEFAULT_DIR = REPO_ROOT / "data" / "policies-v1"  # TRACKED: author-owned, releasable

# --- design.md §3–§4, fixed before the first document. A change needs a line in approvals.md ------
FIELDS = ("doc_id", "title", "category", "policy_kind", "condition", "terms", "text")
DEPARTMENTS = tuple(dict.fromkeys(leaf.department for leaf in build_pqa.LEAVES))
POLICY_KINDS = tuple(select_pqa.POLICY_Q)  # "warranty", "return": the pool's policy_kinds
CONDITION_AXIS_NAMES = tuple(a for a in CONDITION_AXES if a != "kind")
MIN_CHUNKS = 3
MIN_WORDS, MAX_WORDS = 550, 800  # W2; the floor is the margin against splitter drift (§7.1)

DURATION_UNITS = ("day", "days", "month", "months", "year", "years")
TERM_RE = re.compile(rf"^(?:(\d+) (?:{'|'.join(DURATION_UNITS)})|\$(\d+)|not covered|not accepted)$")
# A number in words before a unit, one optional word between ("three business days", "forty-five
# dollars"): the support gate's numeric arm reads number words before its listed units
# (reuse/support_numeric.go), so W7 forbids them (/ai-review F5).
WORDED_DURATION_RE = re.compile(
    r"(?<![a-z0-9])(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
    r"sixty|seventy|eighty|ninety|hundred)[ -](?:[a-z]+[ -])?"
    r"(?:second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years|"
    r"percent|dollar|dollars|cent|cents)(?![a-z0-9])"
)
PLACEHOLDER_RE = re.compile(r"[{}<>]")
DIGITS_RE = re.compile(r"\d+")
TOKEN_RE = re.compile(r"[a-z0-9]+")


def derive_doc_id(record: dict) -> str:
    """`policy-{policy_kind}-{category}`, plus `-{value}` when a condition is set (design §2)."""
    doc_id = f"policy-{record.get('policy_kind')}-{record.get('category')}"
    cond = record.get("condition")
    if isinstance(cond, dict):
        doc_id += f"-{cond.get('value')}"
    return doc_id


def _families(records: list[dict]) -> dict[tuple[object, object], list[dict]]:
    families: dict[tuple[object, object], list[dict]] = defaultdict(list)
    for r in records:
        families[(r.get("policy_kind"), r.get("category"))].append(r)
    return families


def _word_in(word: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(word.lower())}(?![a-z0-9])", text.lower()) is not None


# =================================================================================================
# Schema (P3)
# =================================================================================================
def check_schema(records: list[dict]) -> list[str]:
    problems = []
    for r in records:
        doc_id = r.get("doc_id", "<no doc_id>")
        missing, extra = set(FIELDS) - set(r), set(r) - set(FIELDS)
        if missing or extra:
            problems.append(f"{doc_id}: fields — missing {sorted(missing)}, extra {sorted(extra)}")
        if not str(doc_id).startswith("policy-"):
            problems.append(f"{doc_id}: not a policy- record; this folder holds policies only")
        if r.get("category") not in DEPARTMENTS:
            problems.append(f"{doc_id}: category {r.get('category')!r} is not one of {DEPARTMENTS}")
        if r.get("policy_kind") not in POLICY_KINDS:
            problems.append(f"{doc_id}: policy_kind {r.get('policy_kind')!r} is not one of {POLICY_KINDS}")
        cond = r.get("condition")
        if cond is not None:
            if not isinstance(cond, dict) or set(cond) != {"axis", "value"}:
                problems.append(f"{doc_id}: condition must be null or {{axis, value}}, got {cond!r}")
            elif cond["axis"] not in CONDITION_AXIS_NAMES:
                problems.append(f"{doc_id}: condition axis {cond['axis']!r} is not one of {CONDITION_AXIS_NAMES}")
            elif cond["value"] not in CONDITION_AXES[cond["axis"]]:
                problems.append(f"{doc_id}: condition value {cond['value']!r} is not a value of {cond['axis']!r}")
            elif not _word_in(cond["value"], str(r.get("title", ""))):
                problems.append(f"{doc_id}: the title does not name its condition value {cond['value']!r}")
        if doc_id != derive_doc_id(r):
            problems.append(f"{doc_id}: doc_id differs from the derived {derive_doc_id(r)!r}")
        for name in ("title", "text"):
            value = r.get(name)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"{doc_id}: {name} is empty")
            elif not value.isascii():
                bad = sorted({ch for ch in value if not ch.isascii()})
                problems.append(f"{doc_id}: {name} is not ASCII (W9): {bad}")
            elif PLACEHOLDER_RE.search(value):
                # A template placeholder left in the text ("For {v} service") passed every other
                # check and the author's read (/ai-review F1).
                problems.append(f"{doc_id}: {name} holds a placeholder: {PLACEHOLDER_RE.findall(value)}")
        if isinstance(r.get("text"), str):
            words = len(r["text"].split())
            if not MIN_WORDS <= words <= MAX_WORDS:
                problems.append(f"{doc_id}: {words} words, outside {MIN_WORDS}–{MAX_WORDS} (W2)")

    families = _families(records)
    for kind in POLICY_KINDS:
        for department in DEPARTMENTS:
            if (kind, department) not in families:
                problems.append(f"no {kind} document for {department}")
    for (kind, department), members in sorted(families.items(), key=str):
        conds = [m.get("condition") for m in members]
        if len(members) == 1 and conds[0] is None:
            continue
        axes = {c.get("axis") for c in conds if isinstance(c, dict)}
        values = {c.get("value") for c in conds if isinstance(c, dict)}
        complete = (
            len(members) == 2
            and all(isinstance(c, dict) for c in conds)
            and len(axes) == 1
            and values == set(CONDITION_AXES.get(next(iter(axes)), {}))
        )
        if not complete:
            ids = sorted(str(m.get("doc_id")) for m in members)
            problems.append(f"family ({kind}, {department}) is neither one document nor a complete split: {ids}")
    return problems


# =================================================================================================
# Terms and numbers (P12)
# =================================================================================================
def _term_spans(term: str, text: str) -> list[tuple[int, int]]:
    pattern = rf"(?<![a-z0-9$]){re.escape(term.lower())}(?![a-z0-9])"
    return [m.span() for m in re.finditer(pattern, text.lower())]


def check_terms(records: list[dict]) -> list[str]:
    problems = []
    for r in records:
        doc_id = r.get("doc_id", "<no doc_id>")
        terms = r.get("terms")
        if not isinstance(terms, list) or not terms or not all(isinstance(t, str) for t in terms):
            problems.append(f"{doc_id}: terms must be a non-empty list of strings")
            continue
        parsed = [TERM_RE.match(t) for t in terms]
        for t, m in zip(terms, parsed, strict=True):
            if not m:
                problems.append(f"{doc_id}: term {t!r} is not '<n> <day|month|year>(s)', '$<n>', 'not covered' or 'not accepted'")
        if not all(parsed):
            continue
        durations = [t for t, m in zip(terms, parsed, strict=True) if m.group(1)]
        amounts = [t for t, m in zip(terms, parsed, strict=True) if m.group(2)]
        if len(durations) > 1 or len(amounts) > 1:
            problems.append(f"{doc_id}: at most one duration and one amount, got {terms}")
        if parsed[0].group(2):
            problems.append(f"{doc_id}: the main term (first) must be a duration or 'not covered' / 'not accepted', got {terms[0]!r}")

        body = f"{r.get('title', '')}\n{r.get('text', '')}"
        spans = [s for t in terms for s in _term_spans(t, body)]
        for t in terms:
            if not _term_spans(t, body):
                problems.append(f"{doc_id}: term {t!r} is not written in the text as in terms (W3)")
        stray = [
            m.group()
            for m in DIGITS_RE.finditer(body)
            if not any(a <= m.start() and m.end() <= b for a, b in spans)
        ]
        if stray:
            problems.append(f"{doc_id}: numbers outside its terms (W7): {stray}")
        worded = [m.group() for m in WORDED_DURATION_RE.finditer(body.lower())]
        if worded:
            problems.append(f"{doc_id}: a duration written in words (W7): {worded}")

    for (kind, department), members in sorted(_families(records).items(), key=str):
        if len(members) == 2 and members[0].get("terms") == members[1].get("terms"):
            ids = sorted(str(m.get("doc_id")) for m in members)
            problems.append(f"family ({kind}, {department}): the two sides have the same terms, so it is not a split (§2 fallback): {ids}")
    return problems


# =================================================================================================
# Chunks (P1, P4, P13)
# =================================================================================================
def describe_chunker() -> dict:
    """What the chunk counts depend on: the frozen size and overlap, and the unpinned version."""
    from importlib.metadata import version

    from rag import config

    return {
        "kind": "rag.ingest.record_to_document + SentenceSplitter",
        "chunk_size": config.CHUNK_SIZE,
        "chunk_overlap": config.CHUNK_OVERLAP,
        "llama_index_core": version("llama-index-core"),
    }


def split_chunks(records: list[dict]) -> dict[str, list[str]]:
    """Each record's chunk texts, exactly as `make ingest` would split it. The record goes through
    `record_to_document` because metadata counts against the chunk size while splitting."""
    from llama_index.core.node_parser import SentenceSplitter
    from rag.ingest import record_to_document

    from rag import config

    splitter = SentenceSplitter(chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP)
    return {
        r["doc_id"]: [n.get_content() for n in splitter.get_nodes_from_documents([record_to_document(r)])]
        for r in records
    }


def check_chunks(records: list[dict], chunks: dict[str, list[str]]) -> list[str]:
    problems = []
    for r in records:
        doc_id = r["doc_id"]
        texts = chunks[doc_id]
        if len(texts) < MIN_CHUNKS:
            problems.append(f"{doc_id}: {len(texts)} chunk(s), needs >= {MIN_CHUNKS}")
        terms = r.get("terms") or []
        if texts and terms and not _term_spans(terms[0], texts[0]):
            problems.append(f"{doc_id}: chunk 0 does not hold the main term {terms[0]!r} (W3)")

    seen: dict[str, str] = {}
    for doc_id, texts in sorted(chunks.items()):
        for i, text in enumerate(texts):
            key = " ".join(text.split())
            here = f"{doc_id}#chunk-{i}"
            if key in seen:
                problems.append(f"{here} is identical to {seen[key]}")
            else:
                seen[key] = here
    return problems


# =================================================================================================
# Source counts (plan steps 1-2): counts only, never a title or a question
# =================================================================================================
RISKY_TITLE = {
    "renewed or refurbished": re.compile(r"\b(renewed|refurbished)\b", re.IGNORECASE),
    "international version": re.compile(r"\binternational version\b", re.IGNORECASE),
    "no warranty": re.compile(r"\bno warranty\b", re.IGNORECASE),
}


TITLE_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9&'.-]*")


def maker_of(product: dict) -> str:
    """The maker rule, amended by the author on 2026-10-21 before any maker page was fetched
    (evidence/sources.md): the Brand field, or else the first word of the title. The plain Brand
    rule failed on the data: most selected products carry no Brand (phones 32 of 38)."""
    brand = str(product.get("specs", {}).get("Brand", "")).strip()
    if brand:
        return brand
    m = TITLE_WORD_RE.search(str(product.get("title", "")))
    return m.group().rstrip(".-'") if m else "<none>"


def source_counts(items: Iterable[tuple[str, dict]]) -> dict:
    """From `select_pqa.iter_selection`'s stream: brand counts per department and per leaf (the
    maker rule of evidence/sources.md), and per department how many titles carry a word that can
    contradict a policy document (design U8). Brands are counted case-folded."""
    products, leaf_of = [], {}
    for kind, item in items:
        if kind == "product":
            products.append(item)
        else:
            leaf_of[item["doc_id"]] = item["leaf"]

    brands: dict[str, Counter] = defaultdict(Counter)
    spelling: dict[str, Counter] = defaultdict(Counter)
    risky: dict[str, Counter] = defaultdict(Counter)
    for p in products:
        brand = maker_of(p)
        key = brand.casefold()
        spelling[key][brand] += 1
        for group in (p["category"], leaf_of.get(p["doc_id"], "<no leaf>")):
            brands[group][key] += 1
        hits = [bool(pattern.search(str(p.get("title", "")))) for pattern in RISKY_TITLE.values()]
        for label, hit in zip(RISKY_TITLE, hits, strict=True):
            risky[p["category"]][label] += hit
        risky[p["category"]]["any"] += any(hits)  # distinct products

    def name(key: str) -> str:  # the most common spelling; ties alphabetical
        return min(spelling[key].items(), key=lambda kv: (-kv[1], kv[0]))[0]

    return {
        "products": len(products),
        "top_brands": {
            group: [(name(k), n) for k, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
            for group, c in sorted(brands.items())
        },
        "risky_titles": {dept: dict(c) for dept, c in sorted(risky.items())},
    }


def print_source_counts() -> int:
    counts = source_counts(select_pqa.iter_selection(select_pqa.SELECTION_PATH, select_pqa.DRAFT_DIR))
    print(f"{counts['products']} selected products (read through select_pqa.iter_selection)\n")
    print("  top brands (count), per department and per leaf; the maker rule takes the first:")
    for group, top in counts["top_brands"].items():
        print(f"    {group:<24} " + ", ".join(f"{b} ({n})" for b, n in top))
    print("\n  titles that can contradict a policy document (design U8), per department:")
    for dept, c in counts["risky_titles"].items():
        print(f"    {dept:<24} " + ", ".join(f"{label}: {n}" for label, n in c.items()))
    return 0


# =================================================================================================
# Report
# =================================================================================================
def _jaccard(a: str, b: str) -> float:
    sa, sb = set(TOKEN_RE.findall(a.lower())), set(TOKEN_RE.findall(b.lower()))
    return len(sa & sb) / len(sa | sb) if sa | sb else 0.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(DEFAULT_DIR), help="the policy folder (default: data/policies-v1)")
    ap.add_argument(
        "--product-counts",
        action="store_true",
        help="print the brand and risky-title counts of the 3.2 selection (counts only) and exit",
    )
    args = ap.parse_args(argv)
    if args.product_counts:
        return print_source_counts()

    folder = Path(args.dir)
    if not folder.is_dir() or not any(folder.glob("*.json")):
        print(f"FAIL — no policy documents (*.json) under {folder}")
        return 2

    from rag.ingest import load_records

    try:
        records = load_records(folder)  # doc_id == file name, unique
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        print(f"FAIL — the folder cannot be read the way rag.ingest reads it: {e!r}")
        return 1
    if not all(isinstance(r, dict) for r in records):
        print("FAIL — every file must hold one JSON object")
        return 1
    problems = check_schema(records) + check_terms(records)
    # Split only records ingest could split, so one malformed record is reported, not a traceback
    # (/ai-review F6); the schema problems above already name it.
    splittable = [
        r
        for r in records
        if str(r.get("doc_id", "")).startswith("policy-")
        and isinstance(r.get("title"), str)
        and isinstance(r.get("text"), str)
    ]
    chunks = split_chunks(splittable)
    problems += check_chunks([r for r in records if r["doc_id"] in chunks], chunks)
    g5, g5_counts = check_g5(splittable)

    print(f"policies {folder}")
    print(f"chunker  {describe_chunker()}\n")
    print(f"  {'doc_id':<42} {'words':>5} {'chunks':>6} {'value':>7} {'term@0':>6}")
    for r in sorted(records, key=lambda r: r["doc_id"]):
        texts = chunks.get(r["doc_id"], [])
        raw = r.get("condition")
        cond = raw if isinstance(raw, dict) and {"axis", "value"} <= set(raw) else None
        naming = (
            f"{sum(1 for t in texts if cond['value'] in condition_hits(t).get(cond['axis'], {}))}/{len(texts)}"
            if cond
            else "—"
        )
        terms = r.get("terms") or [""]
        term0 = "yes" if texts and terms[0] and _term_spans(terms[0], texts[0]) else "NO"
        print(f"  {r['doc_id']:<42} {len(str(r.get('text', '')).split()):>5} {len(texts):>6} {naming:>7} {term0:>6}")

    print("\n  sibling token Jaccard (a statistic, not a gate):")
    for (kind, department), members in sorted(_families(records).items(), key=str):
        if len(members) == 2:
            a, b = sorted(members, key=lambda m: str(m.get("doc_id")))
            print(f"    {a['doc_id']} ~ {b['doc_id']}: {_jaccard(str(a.get('text', '')), str(b.get('text', ''))):.3f}")

    print(f"\n  G5 before (families split): {g5_counts['split_families']}")
    print(f"  G5 after (documents naming an undeclared value): {g5_counts['offending_documents']}")

    print()
    mark = "PASS" if g5.passed else "FAIL"
    print(f"  [{mark}] {g5.name}\n         {g5.summary}")
    for line in g5.detail:
        print(f"         {line}")
    print(f"  [{'PASS' if not problems else 'FAIL'}] schema, terms and chunks")
    for line in problems:
        print(f"         {line}")

    return 0 if g5.passed and not problems else 1


if __name__ == "__main__":
    sys.exit(main())
