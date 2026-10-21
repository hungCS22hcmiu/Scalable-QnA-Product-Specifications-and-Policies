"""Corpus sensitivity gate — the executable form of `data-card.md` §7.

C1 can only produce a signal where queries are **similar but ground differently**. The reduced
corpus risks removing the phenomenon it studies. This gate catches that *before* the
snapshot is hashed, while the corpus can still be fixed — and it refuses to print a snapshot hash
unless every criterion passes, so "frozen" cannot happen by accident.

    make gate-corpus VERSION=v1 WORKLOAD=data/workload-v1.json

## The five criteria (data-card.md §7)

| | Criterion | On failure |
| :-- | :--- | :--- |
| **G1** | high-similarity / low-overlap pairs ≥ ~50            | fix the corpus, not the rule |
| **G2** | `B-within` > 0                                       | rebuild — a cross-product-only corpus is defeated by a cache key |
| **G3** | zero Tier-1 collisions                               | disambiguate the query text |
| **G4** | every `doc_id` starts with `policy-` or `product-`   | re-slug before ingestion |
| **G5** | no policy document names a condition it does not declare | author the conditions into separate documents |

G5 here is a **lexical scan over the declared axes** (`CONDITION_AXES`). It is a floor, not a proof
of §7's G5: the author's read of every policy document is the other half of the criterion.

## The workload and its split files (item 3.4)

A run draws from **one split file** (`ask.js` takes the file it is given), so the gate reads the
workload the way the runs will. Stage 1 also checks the workload's shape (`check_workload_shape`:
one stratum, one split and one cluster per record, no cluster or probe across the splits, one Tier-1
form per record) and its two split files (`check_split_files`: found by name beside the whole file,
re-derived from it, then hashed with it). `K` and the capacity are printed per run file; G1 counts
within-split pairs and G2 must hold inside each split (docs/work/2026-10-21-workload-generator/
design.md §2.7).

## Two stages, because §7's "do not proceed to ingestion" reads as a contradiction otherwise

§7 says a failure means *"do not proceed to ingestion"*, yet G1/G2 are defined over `retrieve(q)`,
which needs an ingested index. The resolution is that the criteria split cleanly by what they need:

- **Stage 1 — structural.** G4, G3, G5 and the two workload checks read the corpus files and the
  workload files only. They are genuinely pre-ingestion, and `--structural-only` runs them alone.
  While the policy documents are being written, before any workload exists, `make policy-check`
  runs G5 on its own.
- **Stage 2 — retrieval.** G1 and G2 need the frozen retrieval path, so they run against an
  ingested index (`make ingest`). Ingesting to *measure* is not ingesting to *ship*: nothing is
  frozen until this gate passes, and re-ingestion is idempotent (`overwrite=True`). Retrieval is
  **scoped by each query's `product_id`**, as a run's is (`ask.js` sends it whenever a record has
  one); the unscoped retrieval is reported beside it, never gated on.

Stage 1 failing aborts before stage 2, so a mis-slugged corpus is never embedded.

## Which overlap — the gate's is not the rule's

The rule's overlap is `|A ∩ B| / |B|` between a query's retrieval and a *cached entry's*
provenance: **asymmetric, and therefore not well-defined for the query–query pairs this gate
counts.** The gate uses symmetric Jaccard over the two top-k retrieval sets. At equal `top_k` it is
monotone in `|A ∩ B|` and orders pairs identically to `|A ∩ B| / k`; at the frozen retrieval depth,
`J ≤ 0.2` admits at most one shared chunk. **The gate statistic is a corpus property, never the
rule's operating metric**, and the two are reported separately so they cannot be conflated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import operator
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# --- §7's constants -----------------------------------------------------------------------------
# Not frozen values in the ADR sense (they govern a corpus check, not a measured configuration),
# but changing one changes which corpora are admissible, so they live here named rather than
# inline.
SIM_FLOOR = 0.85  # "sim >= 0.85"  -- the pair must be a genuine lookalike
JACCARD_CEILING = 0.2  # "J <= 0.2" -- ...that nonetheless grounds elsewhere
G1_MIN_PAIRS = 50  # "high-similarity / low-overlap pairs >= ~50"
CAPACITY_RATIO = 0.25  # the capacity ratio: capacity = round(ratio * K)

DOC_ID_PREFIXES = ("product-", "policy-")

# The workload's shape (item 3.4, design.md §2.4 and §2.5). One stratum and one split per record.
STRATA = ("A", "B-within", "B-cross", "C", "D")
SPLITS = ("validation", "test")
# A B-cross probe whose answer equals its target's. Kept, because it measures what the namespace
# costs, but it is NOT a trap (design.md §2.4), so the trap fraction leaves it out.
NOT_A_TRAP = ("name-swap-same",)
# Problem lines printed per kind before "... and N more": a workload missing a field on every record
# would otherwise print a line per record.
DETAIL_CAP = 10

# G5's word list (docs/work/2026-10-20-policy-documents/design.md §5), committed before the first
# policy document was written, and WIDENED by /ai-review F2 (2026-10-21) after the text existed;
# none of the 12 documents hit an added word. Lower case. Errs wide: a wrong hit costs a reworded
# sentence, a miss is silent. A change after the freeze changes which corpora are admissible.
CONDITION_AXES: dict[str, dict[str, tuple[str, ...]]] = {
    "packaging": {
        "opened": ("opened", "open-box", "open box", "open the box", "unsealed", "reopened"),
        "unopened": ("unopened", "sealed", "factory-sealed"),
    },
    "grade": {
        "new": ("new", "brand-new"),
        "renewed": ("renewed", "refurbished", "pre-owned", "second-hand"),
    },
    "region": {
        "domestic": ("domestic", "us model", "us version", "u.s. model", "u.s. version"),
        "international": (
            "international",
            "abroad",
            "overseas",
            "outside the united states",
            "outside of the united states",
            "outside the us",
            "outside of the us",
            "outside the u.s.",
            "outside the usa",
            "outside the u.s.a.",
            "non-us",
            "non-u.s.",
            "foreign",
            "other countries",
            "worldwide",
            "imported",
            "country of purchase",
        ),
    },
    # Return and warranty are opposing conditions of the same kind too (data-card.md §2's B-within
    # example: "warranty period" against "return period"), so each kind may not name the other.
    "kind": {
        "return": ("return window", "return period", "restocking"),
        "warranty": ("warranty", "warranties"),
    },
}
# Ordinary English outside a family split by grade ("refunded to a new gift card"), so these are
# scanned only inside one. "used" is deliberately absent: "if the item has been used" is ordinary
# return wording and would fail every document.
GRADE_PLAIN_WORDS = ("new", "brand-new")


# =================================================================================================
# the Tier-1 normalization contract normalization -- a MIRROR of gateway/internal/cache/normalize.go
# =================================================================================================
def normalize_t1(query: str) -> str:
    """Tier-1 normalization: lowercase, collapse whitespace, strip punctuation and symbols.

    ⚠️ This is a second implementation of a function that already exists in Go, and the Go one is
    authoritative because it is the one that actually runs on the hit path. The duplication is
    unavoidable — G3 has to group queries the way Tier 1 will — and it is dangerous in both
    directions: a looser mirror lets the gate pass a corpus that collides in production, a tighter
    one rejects a corpus Tier 1 would have handled. Both failures are silent.

    So the two are pinned to the shared golden vectors in `contracts/normalize/cases.json`, which
    `experiments/tests/test_corpus_gate.py` and `cache.TestNormalizeMatchesCrossLanguageContract`
    both assert against. Do not edit this function without running both.

    Go's `unicode.IsPunct`/`IsSymbol` test the Unicode P and S categories, which is what
    `unicodedata.category(...)[0]` gives here; Go's `unicode.IsSpace` and Python's `str.isspace()`
    agree on every character that reaches a query in practice.
    """
    out: list[str] = []
    prev_space = False
    for ch in query.lower():
        if ch.isspace():
            if not prev_space and out:
                out.append(" ")
            prev_space = True
        elif unicodedata.category(ch)[0] in ("P", "S"):
            continue  # stripped -- never replaced by a space, or "laptop,headphones" would split
        else:
            out.append(ch)
            prev_space = False
    return "".join(out).strip()


# =================================================================================================
# Inputs
# =================================================================================================
@dataclass
class Query:
    """One workload record (data-card.md §6). Only `question` is required to load one;
    `check_workload_shape` is what requires the rest."""

    qa_id: str
    question: str
    doc_ids: tuple[str, ...] = ()
    product_id: str = ""
    stratum: str = ""
    reference_answer: str = ""
    split: str = ""
    cluster_id: str = ""
    pair_of: str = ""  # the qa_id a probe was built against; "" on every non-probe
    probe_kind: str = ""

    # filled by stage 2
    embedding: list[float] = field(default_factory=list, repr=False)
    retrieved: tuple[str, ...] = ()  # scoped by product_id, as a run retrieves
    retrieved_unscoped: tuple[str, ...] = ()  # reported beside, never gated on


def load_corpus_doc_ids(corpus_dir: Path) -> list[str]:
    """Every `doc_id` in the corpus, read the same way `rag.ingest` reads it.

    Deliberately re-reads the files rather than importing `rag.ingest.load_records`: that function
    raises on the first structural problem, and G4 must report *every* offending doc-id in one pass
    so the human re-slugs once instead of iterating file by file.
    """
    doc_ids = []
    for path in sorted(corpus_dir.glob("*.json")):
        with open(path) as f:
            record = json.load(f)
        doc_ids.append(record.get("doc_id", f"<missing doc_id in {path.name}>"))
    if not doc_ids:
        raise SystemExit(f"FAIL — no *.json records under {corpus_dir}")
    return doc_ids


def load_policy_records(corpus_dir: Path) -> list[dict]:
    """Every `policy-` record in the corpus, whole: G5 reads the title and text, not only the id.

    Re-reads the files for the same reason as `load_corpus_doc_ids`, and keeps every policy record
    whatever its other fields hold, so G5 reports every offender in one pass. Product records are
    skipped: G5 is about policy documents (a product's own text may say "new" and "renewed").
    """
    records = []
    for path in sorted(corpus_dir.glob("*.json")):
        with open(path) as f:
            record = json.load(f)
        if str(record.get("doc_id", "")).startswith("policy-"):
            records.append(record)
    return records


def load_workload(path: Path) -> list[Query]:
    """The frozen query set.

    ⚠️ It must NOT live inside `data/{version}/`. `rag.ingest` globs `*.json` there and asserts
    `doc_id == filename`, so a workload file dropped in the corpus directory fails ingestion — or
    worse, if it happened to carry a `doc_id`, would be embedded as a corpus document. Keep it a
    sibling: `data/workload-{version}.json`.
    """
    with open(path) as f:
        records = json.load(f)
    if not isinstance(records, list):
        raise SystemExit(f"FAIL — {path} must be a JSON array of workload records")

    # Lenient by design: a missing or null field loads as "" and is reported by
    # check_workload_shape, beside G3 - G5, rather than stopping the load at the first record.
    queries = []
    for i, r in enumerate(records):
        if not r.get("question"):
            raise SystemExit(f"FAIL — {path} record {i} has no `question`")
        queries.append(
            Query(
                qa_id=r.get("qa_id") or f"q{i:04d}",
                question=r["question"],
                doc_ids=tuple(r.get("doc_ids") or ()),
                product_id=r.get("product_id") or "",
                stratum=r.get("stratum") or "",
                reference_answer=r.get("reference_answer") or "",
                split=r.get("split") or "",
                cluster_id=r.get("cluster_id") or "",
                pair_of=r.get("pair_of") or "",
                probe_kind=r.get("probe_kind") or "",
            )
        )
    return queries


# =================================================================================================
# Stage 1 -- structural criteria (no infrastructure)
# =================================================================================================
@dataclass
class Criterion:
    name: str
    passed: bool
    summary: str
    detail: list[str] = field(default_factory=list)


def check_g4(doc_ids: list[str]) -> Criterion:
    """Every doc_id begins with `policy-` or `product-` (interfaces.md §C).

    A corpus that omits the prefix does not fail loudly: the reuse rule reads a question's lane
    from the prefix, so every question would classify into the spec lane, the lane
    machinery would report plausible values throughout, and the mixed lane would never fire — a
    null result produced by the corpus rather than by the rule.

    `rag.ingest.record_kind()` enforces the same rule, so this is also a check that ingestion was
    actually the path taken.
    """
    bad = [d for d in doc_ids if not d.startswith(DOC_ID_PREFIXES)]
    return Criterion(
        name="G4  doc-id kind prefix",
        passed=not bad,
        summary=f"{len(doc_ids) - len(bad)}/{len(doc_ids)} doc_ids carry a kind prefix",
        detail=[f"no product-/policy- prefix: {d}" for d in bad],
    )


def check_g3(queries: list[Query]) -> tuple[Criterion, int]:
    """Zero Tier-1 collisions: no two queries sharing `(normalize(q), product_id)` may disagree.

    ⚠️ BYPASS 2026-09-09: the partition key gained `product_id` because the Tier-1 cache key did
    (gateway/internal/cache/key.go), reversing the "product_id in the Tier-1 key --
    Rejected" without the owed superseding ADR.
    Grouping by `normalize(q)` alone, as before, would now check a STRICTER invariant than Tier 1
    actually needs: two queries with the same text but different `product_id` no longer share a
    Redis key, so they can no longer collide there either.

    Tier 1 is a bare hash lookup that runs NO reuse rule (interfaces.md §D), so a collision is
    unguarded and silent — the second query is served the first one's answer permanently, and the
    resulting false hit is charged to a reuse rule that never ran.

    Disagreement is on `doc_ids` or `reference_answer`. A group that agrees on both is a **benign
    duplicate** — the same question asked twice — which is legal and is reported separately,
    because a workload with many of them has a smaller effective K than its record count suggests.

    Returns the criterion and the benign-duplicate group count.
    """
    groups: dict[tuple[str, str], list[Query]] = defaultdict(list)
    for q in queries:
        groups[(normalize_t1(q.question), q.product_id or "")].append(q)

    colliding, benign = [], 0
    for key, members in sorted(groups.items()):
        if len(members) == 1:
            continue
        answers = {(m.doc_ids, m.reference_answer) for m in members}
        if len(answers) == 1:
            benign += 1
            continue
        norm_q, product_id = key
        colliding.append(
            f"(normalize(q), product_id)=({norm_q!r}, {product_id!r}) is shared by "
            f"{len(members)} queries that disagree:\n"
            + "\n".join(
                f"        {m.qa_id}: {m.question!r}  doc_ids={list(m.doc_ids)}" for m in members
            )
        )

    return (
        Criterion(
            name="G3  Tier-1 collisions",
            passed=not colliding,
            summary=(
                f"{len(colliding)} colliding group(s), {benign} benign duplicate group(s) "
                f"over {len(groups)} distinct (normalized query, product_id) partitions"
            ),
            detail=colliding,
        ),
        benign,
    )


def _word_pattern(word: str) -> re.Pattern[str]:
    # A match may not touch an ASCII letter or digit on either side: "opened" is not found inside
    # "unopened", "new" not inside "renewed", but "un-opened" DOES hit "opened" (a loud error).
    return re.compile(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])")


_CONDITION_PATTERNS = {
    axis: {value: [(w, _word_pattern(w)) for w in words] for value, words in values.items()}
    for axis, values in CONDITION_AXES.items()
}


def condition_hits(text: str) -> dict[str, dict[str, list[str]]]:
    """For each axis, each value whose words appear in `text`, with the words found. Pure.

    White space is collapsed first, so a phrase still matches across a line break or a double
    space ("outside the\nUnited States"), which would otherwise pass silently (/ai-review F2)."""
    lowered = " ".join(text.lower().split())
    hits: dict[str, dict[str, list[str]]] = {}
    for axis, values in _CONDITION_PATTERNS.items():
        for value, patterns in values.items():
            found = [w for w, pattern in patterns if pattern.search(lowered)]
            if found:
                hits.setdefault(axis, {})[value] = found
    return hits


def check_g5(records: list[dict]) -> tuple[Criterion, dict[str, int]]:
    """No policy document names a condition value it does not declare (data-card.md §7, G5).

    §7's G5 is "no two opposing conditions of the same kind share a `doc_id`". Failing only a
    document that names BOTH values would miss the natural violation: a domestic warranty that says
    "not valid outside the United States" names one value and still holds two answers under one id
    (design review H1). So a document may name only its declared condition and its own kind
    (`policy_kind`); one with no condition names no value of any axis. Grade's plain words are
    scanned only inside a family split by grade.

    ⚠️ Lexical, over the declared axes only: "if the seal is broken" passes. The author's read of
    every document is the other half of G5, and the summary says so.

    Returns the criterion and the counts data-card.md §7 records: `split_families` (before: the
    families that would hold an opposing pair under one id if they were not split) and
    `offending_documents` (after: must be 0).
    """
    policies = [r for r in records if str(r.get("doc_id", "")).startswith("policy-")]

    family_values: dict[tuple[object, object], set[tuple[str, str]]] = defaultdict(set)
    for r in policies:
        cond = r.get("condition")
        if isinstance(cond, dict):
            family_values[(r.get("policy_kind"), r.get("category"))].add(
                (str(cond.get("axis")), str(cond.get("value")))
            )
    split_families = sum(
        1
        for values in family_values.values()
        for axis in {a for a, _ in values}
        if {v for a, v in values if a == axis} == set(CONDITION_AXES.get(axis, {}))
    )

    detail, offenders = [], set()
    for r in sorted(policies, key=lambda r: str(r.get("doc_id"))):
        doc_id = str(r.get("doc_id"))
        cond = r.get("condition") if isinstance(r.get("condition"), dict) else {}
        allowed = {("kind", r.get("policy_kind"))}
        if cond:
            allowed.add((cond.get("axis"), cond.get("value")))
        family = (r.get("policy_kind"), r.get("category"))
        grade_split = any(a == "grade" for a, _ in family_values.get(family, set()))

        hits = condition_hits(f"{r.get('title', '')}\n{r.get('text', '')}")
        for axis, values in sorted(hits.items()):
            if axis == "grade" and not grade_split:
                values = {
                    v: kept
                    for v, ws in values.items()
                    if (kept := [w for w in ws if w not in GRADE_PLAIN_WORDS])
                }
            undeclared = sorted(v for v in values if (axis, v) not in allowed)
            if not undeclared:
                continue
            offenders.add(doc_id)
            named = " and ".join(
                f"{v} ({', '.join(repr(w) for w in values[v])})" for v in sorted(values)
            )
            if len(values) > 1:
                detail.append(f"{doc_id}: {axis} = {named}")
            else:
                detail.append(f"{doc_id}: names {axis} = {named}, which it does not declare")

    if not policies:
        # A v1 corpus that lost its policy copy would otherwise print "0/0 clean" and pass
        # (/ai-review F7).
        detail.append("no policy- documents in the corpus: G5 has nothing to check")
    clean = len(policies) - len(offenders)
    return (
        Criterion(
            name="G5  condition-splitting (declared axes, lexical)",
            passed=bool(policies) and not offenders,
            summary=(
                f"{split_families} famil{'y' if split_families == 1 else 'ies'} split, "
                f"{clean}/{len(policies)} policy documents clean; the author's read of every "
                f"document is the other half of G5"
            ),
            detail=detail,
        ),
        {"split_families": split_families, "offending_documents": len(offenders)},
    )


def _capped(problems: dict[str, list[str]]) -> list[str]:
    """Every kind of problem, each listed up to DETAIL_CAP lines and then counted."""
    lines = []
    for kind in sorted(problems):
        found = problems[kind]
        lines += found[:DETAIL_CAP]
        if len(found) > DETAIL_CAP:
            lines.append(f"... and {len(found) - DETAIL_CAP} more: {kind}")
    return lines


def check_workload_shape(queries: list[Query]) -> Criterion:
    """The workload's own shape (item 3.4, spec W1, W2, W5): what every later number assumes.

    - **One stratum** of `STRATA`, **one split** of `SPLITS` and a **`cluster_id`** on every
      record, and a `qa_id` used once (W1).
    - **No cluster and no `pair_of` link across the splits** (W2). A cluster split in two leaks its
      paraphrases into test, and a probe split from its target is a trap no run ever contains,
      because a run draws from one split file. A `pair_of` that names no record fails too.
    - **Both splits non-empty.**
    - **One `normalize_t1` form per record across the WHOLE file** (W5). Stricter than G3, which
      partitions by `product_id`: it keeps the offline join on `query_normalized` exact whether or
      not a run sends `product_id`, and it makes `K` equal the record count.

    A Criterion, never a SystemExit, so it is reported beside G3 - G5 in one pass. The workload
    builder calls this same function.
    """
    problems: dict[str, list[str]] = defaultdict(list)

    by_id: dict[str, Query] = {}
    for qa_id, n in sorted(Counter(q.qa_id for q in queries).items()):
        if n > 1:
            problems["a qa_id used twice"].append(f"qa_id {qa_id} is used by {n} records")
    for q in queries:
        by_id.setdefault(q.qa_id, q)
        if q.stratum not in STRATA:
            problems["no stratum"].append(
                f"{q.qa_id}: stratum {q.stratum!r} is not one of {', '.join(STRATA)}"
            )
        if q.split not in SPLITS:
            problems["no split"].append(
                f"{q.qa_id}: split {q.split!r} is not one of {', '.join(SPLITS)}"
            )
        if not q.cluster_id:
            problems["no cluster_id"].append(f"{q.qa_id}: no cluster_id")

    clusters: dict[str, list[Query]] = defaultdict(list)
    for q in queries:
        if q.cluster_id:
            clusters[q.cluster_id].append(q)
    for cluster_id, members in sorted(clusters.items()):
        splits = sorted({m.split for m in members})
        if len(splits) > 1:
            problems["a cluster across the splits"].append(
                f"cluster {cluster_id} spans {' and '.join(repr(s) for s in splits)}: "
                + ", ".join(f"{m.qa_id} ({m.split})" for m in members)
            )

    for q in queries:
        if not q.pair_of:
            continue
        target = by_id.get(q.pair_of)
        if target is None:
            problems["a pair_of that names no record"].append(
                f"{q.qa_id}: pair_of {q.pair_of} names no record"
            )
        elif target.split != q.split:
            problems["a pair across the splits"].append(
                f"{q.qa_id} ({q.split}) is built against {target.qa_id} ({target.split}): "
                "the pair crosses the splits"
            )

    per_split = Counter(q.split for q in queries)
    for split in SPLITS:
        if not per_split[split]:
            problems["an empty split"].append(f"split {split!r} holds no record")

    forms: dict[str, list[str]] = defaultdict(list)
    for q in queries:
        forms[normalize_t1(q.question)].append(q.qa_id)
    for ids in sorted(forms.values()):
        if len(ids) > 1:
            problems["one Tier-1 form, two records"].append(
                f"{len(ids)} records normalise to one Tier-1 form: {', '.join(ids)}"
            )

    n_problems = sum(len(v) for v in problems.values())
    return Criterion(
        name="W   workload shape (stratum, split, cluster, one Tier-1 form)",
        passed=not problems,
        summary=(
            f"{len(queries)} records · "
            + " ".join(f"{s}={per_split[s]}" for s in SPLITS)
            + f" · {len(clusters)} clusters · {sum(1 for q in queries if q.pair_of)} probes"
            + f" · {n_problems} problem(s)"
        ),
        detail=_capped(problems),
    )


def split_path(workload_path: Path, split: str) -> Path:
    """`data/workload-v1.json` -> `data/workload-v1-validation.json`: found by name, beside it."""
    return workload_path.with_name(f"{workload_path.stem}-{split}{workload_path.suffix}")


def derive_split(records: list[dict], split: str) -> list[dict]:
    """One split file's content, re-derived from the whole file: that split's records, in
    `popularity_rank` order. `ask.js` takes the file index as the Zipf rank, so the order IS the
    popularity, and the same records in another order are a different workload.

    Raises ValueError unless that split's ranks are exactly 1 .. n.
    """
    mine = [r for r in records if r.get("split") == split]
    ranks = [r.get("popularity_rank") for r in mine]
    integers = all(type(rank) is int for rank in ranks)  # `is int`: True is not a rank
    if not integers or sorted(ranks) != list(range(1, len(mine) + 1)):
        raise ValueError(
            f"the {split} records' popularity_rank values are not exactly 1 .. {len(mine)}"
        )
    return sorted(mine, key=lambda r: r["popularity_rank"])


def check_split_files(workload_path: Path) -> Criterion:
    """Both split files exist beside the whole file and equal what it re-derives (impact F2,
    review L4).

    A run draws from ONE split file, so a split file re-sorted or edited after the freeze would
    change every hit rate while the whole file, and a digest over it alone, stayed the same. So the
    gate re-derives each split file from the whole file, fails if one is missing or differs, and
    only then are all three hashed into the snapshot digest.
    """
    with open(workload_path) as f:
        records = json.load(f)

    problems: list[str] = []
    for split in SPLITS:
        path = split_path(workload_path, split)
        if not path.is_file():
            problems.append(f"no split file at {path.name}")
            continue
        try:
            want = derive_split(records, split)
        except ValueError as e:
            problems.append(f"{workload_path.name}: {e}")
            continue
        with open(path) as f:
            have = json.load(f)
        if have == want:
            continue
        if not isinstance(have, list) or len(have) != len(want):
            n = len(have) if isinstance(have, list) else "not a list"
            problems.append(f"{path.name} holds {n} records; the whole file gives {len(want)}")
            continue
        first = next(i for i, (h, w) in enumerate(zip(have, want)) if h != w)
        problems.append(
            f"{path.name} differs from the whole file's {split} records, first at position "
            f"{first + 1} (popularity_rank order)"
        )

    return Criterion(
        name="S   split files (found by name, re-derived from the whole file)",
        passed=not problems,
        summary=", ".join(split_path(workload_path, s).name for s in SPLITS)
        + (" match the whole file" if not problems else f": {len(problems)} problem(s)"),
        detail=problems,
    )


def k_per_run_file(queries: list[Query]) -> dict[str, int]:
    """`K` of every file a run may draw from: the whole file and each split (impact F1, ADR-013).

    A run's capacity is `round(0.25 × K)` of the file it draws from, never of the whole file:
    `K_total` would give a split run a cache about half its own working set.
    """
    k = {"whole": len({normalize_t1(q.question) for q in queries})}
    for split in SPLITS:
        k[split] = len({normalize_t1(q.question) for q in queries if q.split == split})
    return k


def trap_fraction(queries: list[Query]) -> float:
    """The share of records built as traps: B-within and B-cross, less `NOT_A_TRAP` probes."""
    if not queries:
        return 0.0
    traps = sum(
        1
        for q in queries
        if q.stratum in ("B-within", "B-cross") and q.probe_kind not in NOT_A_TRAP
    )
    return traps / len(queries)


# =================================================================================================
# Stage 2 -- retrieval criteria
# =================================================================================================
def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _cosine_with_norms(a: list[float], b: list[float], na: float, nb: float) -> float:
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(map(operator.mul, a, b)) / (na * nb)


def cosine(a: list[float], b: list[float]) -> float:
    """Plain-Python cosine. No numpy: adding a top-level dependency needs sign-off.

    O(K²·d) for the whole sweep. `similar_pairs` computes each norm once and gets the same value
    bit for bit, which keeps a workload of ~1,500 queries to minutes, the right trade for a check
    that runs once per corpus freeze.
    """
    return _cosine_with_norms(a, b, _norm(a), _norm(b))


def jaccard(a: tuple[str, ...], b: tuple[str, ...]) -> float:
    """Symmetric |A ∩ B| / |A ∪ B| — the GATE's overlap, not the rule's.

    Two empty retrieval sets score 0, not 1. Vacuous agreement is not evidence of shared
    provenance, and scoring it 1 would quietly exclude the pair from G1's low-overlap count.
    """
    sa, sb = set(a), set(b)
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


@dataclass
class Pair:
    left: str
    right: str
    similarity: float
    jaccard: float
    label: str  # "B-within" | "B-cross" | "unlabelled"


def label_pair(a: Query, b: Query) -> str:
    """B-within (same product, different grounding) vs B-cross (different product).

    A pair where either side has no `product_id` is **unlabelled**, never folded into B-cross.
    G2 exists because a cross-product-only corpus is defeated by adding `product_id` to the cache
    key, which would make C1 redundant by construction; guessing an unlabelled pair into either
    bucket is guessing at exactly the quantity the criterion measures.
    """
    if not a.product_id or not b.product_id:
        return "unlabelled"
    return "B-within" if a.product_id == b.product_id else "B-cross"


def similar_pairs(queries: list[Query]) -> list[tuple[int, int, float]]:
    """Every `(i, j, cosine)` with `cosine >= SIM_FLOOR`: the one O(K²·d) pass, shared by the
    scoped and the unscoped overlap so the slow part runs once."""
    norms = [_norm(q.embedding) for q in queries]
    out = []
    n = len(queries)
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine_with_norms(queries[i].embedding, queries[j].embedding, norms[i], norms[j])
            if sim >= SIM_FLOOR:
                out.append((i, j, sim))
    return out


def find_pairs(
    queries: list[Query],
    similar: list[tuple[int, int, float]] | None = None,
    unscoped: bool = False,
) -> tuple[list[Pair], list[float]]:
    """All high-similarity pairs, and the Jaccard of every one of them.

    The second return value is §7's overlap-variance statistic: the distribution of overlap across
    *all* high-similarity pairs, not only the ones that clear the low-overlap ceiling. A corpus
    where every high-similarity pair also shares its grounding has overlap ≈ 1 everywhere and
    cannot produce a C1 signal — that is visible in the distribution long before G1's count says so.

    The overlap is over the scoped retrieval, as a run retrieves; `unscoped=True` gives the
    unscoped one, which is reported and never gated on.
    """
    if similar is None:
        similar = similar_pairs(queries)
    hits: list[Pair] = []
    overlaps: list[float] = []
    for i, j, sim in similar:
        a, b = queries[i], queries[j]
        if unscoped:
            j_overlap = jaccard(a.retrieved_unscoped, b.retrieved_unscoped)
        else:
            j_overlap = jaccard(a.retrieved, b.retrieved)
        overlaps.append(j_overlap)
        if j_overlap <= JACCARD_CEILING:
            hits.append(Pair(a.qa_id, b.qa_id, sim, j_overlap, label_pair(a, b)))
    return hits, overlaps


def split_pairs(pairs: list[Pair], queries: list[Query]) -> tuple[dict[str, list[Pair]], list[Pair]]:
    """The pairs inside each split, and the pairs across the splits (impact F3, open question 14).

    A run draws from one split file, so only two queries in the same file can ever meet in one
    cache. G1 counts the within-split pairs and G2 must hold inside each split; a cross-split pair
    is reported apart and gates nothing.
    """
    split_of = {q.qa_id: q.split for q in queries}
    within: dict[str, list[Pair]] = {s: [] for s in SPLITS}
    across: list[Pair] = []
    for p in pairs:
        s = split_of.get(p.left)
        if s in within and split_of.get(p.right) == s:
            within[s].append(p)
        else:
            across.append(p)
    return within, across


def retrieve_all(
    queries: list[Query],
    embed: Callable[[str], list[float]],
    retrieve_scoped: Callable[[str, str | None], Iterable[str]],
    retrieve_unscoped: Callable[[str], Iterable[str]],
    progress: Callable[[str], None] = print,
) -> None:
    """Fill each query's embedding, its scoped retrieval and its unscoped one, in place.

    Scoped is what a run does (design review H3): `ask.js` sends `product_id` whenever a record has
    one, and the RAG service then keeps that product's chunks and all policy chunks (interfaces.md
    v0.8). A query with no `product_id` is retrieved unscoped in both. The three callables are
    injected so a test can record the calls; `main` passes the frozen path.
    """
    for n, q in enumerate(queries, 1):
        q.embedding = embed(q.question)
        q.retrieved = tuple(retrieve_scoped(q.question, q.product_id or None))
        q.retrieved_unscoped = tuple(retrieve_unscoped(q.question))
        if n % 25 == 0 or n == len(queries):
            progress(f"  {n}/{len(queries)}")


def check_g1(pairs: list[Pair], scope: str = "") -> Criterion:
    return Criterion(
        name="G1  high-similarity / low-overlap pairs" + (f" ({scope})" if scope else ""),
        passed=len(pairs) >= G1_MIN_PAIRS,
        summary=(
            f"{len(pairs)} pair(s) with sim >= {SIM_FLOOR} and J <= {JACCARD_CEILING} "
            f"(need >= {G1_MIN_PAIRS})"
        ),
        detail=(
            []
            if len(pairs) >= G1_MIN_PAIRS
            else [
                (
                    "Fix the CORPUS, not the rule (data-card.md §7): add categories, differentiate "
                    "policy windows per category, lengthen policy documents so they chunk into >= 3 "
                    "chunks (the v1 corpus model requirement 3), then re-run."
                )
            ]
        ),
    )


def check_g2(pairs: list[Pair], scope: str = "") -> Criterion:
    counts = Counter(p.label for p in pairs)
    within, cross, unlabelled = counts["B-within"], counts["B-cross"], counts["unlabelled"]
    ratio = f"{within / cross:.2f}" if cross else "n/a"
    return Criterion(
        name="G2  within-product traps exist" + (f" ({scope})" if scope else ""),
        passed=within > 0,
        summary=f"B-within={within}  B-cross={cross}  ratio={ratio}  unlabelled={unlabelled}",
        detail=(
            []
            if within > 0
            else [
                (
                    "Every trap in this corpus is cross-product, so adding `product_id` to the "
                    "cache key reproduces C1's entire benefit at zero cost and C1 is redundant BY "
                    "CONSTRUCTION OF THE CORPUS. Build same-product pairs that differ "
                    "in policy dimension or applicable condition — warranty vs return period, "
                    "opened vs unopened — which exist only if policy documents chunk finely "
                    "enough to separate conditions."
                )
            ]
            + (
                [
                    (
                        f"NOTE: {unlabelled} pair(s) could not be labelled because a `product_id` "
                        "was missing. They are excluded from both counts, never assumed cross."
                    )
                ]
                if unlabelled
                else []
            )
        ),
    )


# =================================================================================================
# Snapshot
# =================================================================================================
def snapshot_digest(paths: list[Path]) -> tuple[str, list[tuple[str, str]]]:
    """`sha256` over a sorted (relative path, file digest) manifest — the freeze record.

    Hashes the manifest rather than concatenated bytes so that a rename, an added file, and a
    deleted file each change the digest. Paths are repo-relative and sorted, so the digest does not
    depend on where the repo is checked out or on directory iteration order.
    """
    per_file = []
    for p in sorted(paths):
        # A path outside the repo can only be a --corpus-dir dry run, which is never frozen; fall
        # back to the bare name rather than raising, so the dry run still exercises this code.
        try:
            rel = p.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = p.name
        per_file.append((rel, hashlib.sha256(p.read_bytes()).hexdigest()))
    manifest = "\n".join(f"{rel}  {digest}" for rel, digest in per_file)
    return hashlib.sha256(manifest.encode()).hexdigest(), per_file


def freeze_files(corpus_dir: Path, workload_path: Path) -> list[Path]:
    """What the snapshot digest covers: every corpus record, the whole workload file and its two
    split files (impact F2). A run draws from a split file, so a digest without them would stay the
    same while a run's workload changed."""
    run_files = [workload_path] + [split_path(workload_path, s) for s in SPLITS]
    return sorted(corpus_dir.glob("*.json")) + run_files


# =================================================================================================
# Report
# =================================================================================================
def histogram(values: list[float], buckets: int = 10) -> list[tuple[str, int]]:
    """Equal-width buckets over [0, 1]. J = 1.0 lands in the last bucket, not a bucket of its own."""
    counts = [0] * buckets
    for v in values:
        counts[min(int(v * buckets), buckets - 1)] += 1
    return [(f"{i / buckets:.1f}-{(i + 1) / buckets:.1f}", c) for i, c in enumerate(counts)]


def derive_capacity(k: int) -> int:
    """the capacity ratio: `round(0.25 × K)` ENTRIES, where K is the distinct-query count of the
    workload file the run draws from (`k_per_run_file`, ADR-013).

    A COUNT, not a byte budget puts enforcement in the gateway for exactly this reason.
    Feed the result to the gateway as CACHE_CAPACITY and record it in every run manifest.
    """
    return round(CAPACITY_RATIO * k)


def emit(criteria: list[Criterion]) -> bool:
    print()
    all_passed = True
    for c in criteria:
        mark = "PASS" if c.passed else "FAIL"
        print(f"  [{mark}] {c.name}")
        print(f"         {c.summary}")
        for line in c.detail:
            for sub in line.split("\n"):
                print(f"         {sub}")
        all_passed = all_passed and c.passed
    return all_passed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default="v1", help="corpus directory under data/ (default: v1)")
    ap.add_argument(
        "--corpus-dir",
        default=None,
        help="override the corpus location (default: data/{version}). For dry-running the gate "
        "against a scratch corpus before the real one exists.",
    )
    ap.add_argument(
        "--workload",
        default=None,
        help="workload JSON array (default: data/workload-{version}.json). Must live OUTSIDE "
        "data/{version}/ -- rag.ingest globs that directory.",
    )
    ap.add_argument(
        "--structural-only",
        action="store_true",
        help="run G3, G4 and G5 only. No Redis, no Ollama, no ingested index -- the loop to run "
        "while authoring the corpus.",
    )
    ap.add_argument("--report", default=None, help="also write the full result as JSON here")
    args = ap.parse_args()

    corpus_dir = Path(args.corpus_dir) if args.corpus_dir else REPO_ROOT / "data" / args.version
    workload_path = (
        Path(args.workload) if args.workload else REPO_ROOT / "data" / f"workload-{args.version}.json"
    )
    if not corpus_dir.is_dir():
        print(f"FAIL — no corpus at {corpus_dir}")
        return 1
    if not workload_path.is_file():
        print(f"FAIL — no workload at {workload_path}")
        return 1

    print(f"corpus   {corpus_dir}")
    print(f"workload {workload_path}")

    doc_ids = load_corpus_doc_ids(corpus_dir)
    policies = load_policy_records(corpus_dir)
    queries = load_workload(workload_path)

    # --- stage 1 --------------------------------------------------------------------------------
    g4 = check_g4(doc_ids)
    g3, benign_groups = check_g3(queries)
    g5, g5_counts = check_g5(policies)
    shape = check_workload_shape(queries)
    split_files = check_split_files(workload_path)
    criteria = [g3, g4, g5, shape, split_files]

    k = k_per_run_file(queries)
    print(f"\n{len(doc_ids)} corpus documents · {len(queries)} workload records · K={k['whole']} distinct")
    print(
        "K and capacity per run file: "
        + " · ".join(f"{name} K={n} capacity={derive_capacity(n)}" for name, n in k.items())
    )

    if not emit(criteria):
        print("\n  STOP — a structural criterion failed. Do not ingest; fix the corpus or the "
              "workload first.")
        return 1
    if args.structural_only:
        print("\n  Structural criteria pass (G3, G4, G5, the workload shape, the split files). "
              "Re-run without --structural-only for G1/G2.")
        return 0

    # --- stage 2 --------------------------------------------------------------------------------
    # Imported here, not at module scope, so --structural-only needs neither Redis nor Ollama.
    from rag.embedding import OllamaEmbedding
    from rag.retrieve import make_retriever, retrieve

    print("\nembedding the workload and retrieving, scoped and unscoped "
          "(frozen path: nomic-embed-text + FLAT)...")
    embedder = OllamaEmbedding()
    unscoped_retriever = make_retriever()
    retrieve_all(
        queries,
        embed=embedder.get_query_embedding,
        # retrieve() rebuilds the index on every call (rag/src/rag/retrieve.py): slow at ~1,500
        # queries, and still the path a run takes. A faster scoped retriever is its own rag/ task.
        retrieve_scoped=lambda text, pid: [c.chunk_id for c in retrieve(text, product_id=pid)[0]],
        retrieve_unscoped=lambda text: [c.chunk_id for c in unscoped_retriever(text)],
    )

    ungrounded = [q.qa_id for q in queries if not q.retrieved]
    if ungrounded:
        print(f"\n  WARNING — {len(ungrounded)} quer(y|ies) retrieved NOTHING: {ungrounded[:10]}")
        print("            They cannot contribute to G1 and are usually an un-ingested corpus.")

    similar = similar_pairs(queries)
    pairs, overlaps = find_pairs(queries, similar)
    within, across = split_pairs(pairs, queries)
    g1 = check_g1([p for s in SPLITS for p in within[s]], scope="within split")
    g2s = [check_g2(within[s], scope=s) for s in SPLITS]
    criteria += [g1, *g2s]
    passed = emit([g1, *g2s]) and all(c.passed for c in (g3, g4, g5, shape, split_files))

    unscoped_pairs, _ = find_pairs(queries, similar, unscoped=True)
    unscoped_within, _ = split_pairs(unscoped_pairs, queries)

    # --- the statistics data-card.md §7 records at freeze -----------------------------------------
    mean_overlap = sum(overlaps) / len(overlaps) if overlaps else 0.0
    var_overlap = (
        sum((o - mean_overlap) ** 2 for o in overlaps) / len(overlaps) if overlaps else 0.0
    )
    in_split = {s: [q for q in queries if q.split == s] for s in SPLITS}
    strata = {
        s: dict(sorted(Counter(q.stratum for q in in_split[s]).items())) for s in SPLITS
    }

    print("\n--- statistics to record in data-card.md §7 ---")
    print(f"  G1 pairs (sim>={SIM_FLOOR}, J<={JACCARD_CEILING}), scoped : "
          + " ".join(f"{s}={len(within[s])}" for s in SPLITS)
          + f" · across the splits={len(across)} (not gated)")
    for g2 in g2s:
        print(f"  {g2.name[4:]:<44}: {g2.summary}")
    print("  unscoped, for comparison (not gated)        : "
          + " ".join(
              f"{s}: G1={len(unscoped_within[s])} "
              f"B-within={sum(1 for p in unscoped_within[s] if p.label == 'B-within')}"
              for s in SPLITS
          ))
    print(f"  Tier-1 collision groups / benign duplicates  : 0 / {benign_groups}")
    print(f"  overlap across ALL high-sim pairs (scoped)   : n={len(overlaps)} "
          f"mean={mean_overlap:.3f} var={var_overlap:.4f}")
    for label, count in histogram(overlaps):
        if count:
            print(f"      J {label}: {count}")
    for s in SPLITS:
        print(f"  {s:<10} per-stratum counts              : {strata[s]}")
        print(f"  {s:<10} trap fraction                   : {trap_fraction(in_split[s]):.3f}")
    print(f"  trap fraction of the whole file              : {trap_fraction(queries):.3f}")
    for name, n in k.items():
        print(f"  {name:<10} K={n:<6} derived cache capacity (round({CAPACITY_RATIO}*K)) = "
              f"{derive_capacity(n)}")

    # --- freeze ------------------------------------------------------------------------------------
    digest, per_file = snapshot_digest(freeze_files(corpus_dir, workload_path))
    if passed:
        print("\n--- FREEZE ---")
        print(f"  dataset version : {args.version}")
        print(f"  snapshot digest : {digest}")
        print(f"  over            : {len(per_file)} files")
        print("\n  All five criteria pass. Record the version, the digest, and K and the capacity")
        print("  of each run file in data-card.md §7 and in every run manifest (the evaluation).")
        print("  G5 here is lexical: the author's read of every policy document is the other half")
        print("  of G5 (data-card.md §7), and it must be recorded before this digest is frozen.")
    else:
        print("\n  NOT FROZEN — a criterion failed, so no snapshot digest is printed.")
        print(f"  (it would have been {digest[:12]}…; fix the corpus and re-run)")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "dataset": args.version,
                    "workload": str(workload_path),
                    "passed": passed,
                    "snapshot_digest": digest if passed else None,
                    "files": [{"path": p, "sha256": d} for p, d in per_file],
                    "criteria": [
                        {"name": c.name, "passed": c.passed, "summary": c.summary} for c in criteria
                    ],
                    "statistics": {
                        "g1_pairs_within_split": {s: len(within[s]) for s in SPLITS},
                        "g1_pairs_across_splits": len(across),
                        "b_within": {
                            s: sum(1 for p in within[s] if p.label == "B-within") for s in SPLITS
                        },
                        "b_cross": {
                            s: sum(1 for p in within[s] if p.label == "B-cross") for s in SPLITS
                        },
                        "b_unlabelled": {
                            s: sum(1 for p in within[s] if p.label == "unlabelled") for s in SPLITS
                        },
                        "unscoped": {
                            s: {
                                "g1_pairs": len(unscoped_within[s]),
                                "b_within": sum(
                                    1 for p in unscoped_within[s] if p.label == "B-within"
                                ),
                            }
                            for s in SPLITS
                        },
                        "benign_duplicate_groups": benign_groups,
                        "high_sim_pairs": len(overlaps),
                        "overlap_mean": mean_overlap,
                        "overlap_variance": var_overlap,
                        "strata": strata,
                        "trap_fraction": {
                            **{s: trap_fraction(in_split[s]) for s in SPLITS},
                            "whole": trap_fraction(queries),
                        },
                        "run_files": {
                            name: {
                                "path": str(split_path(workload_path, name))
                                if name in SPLITS
                                else str(workload_path),
                                "k_distinct_queries": n,
                                "cache_capacity": derive_capacity(n),
                            }
                            for name, n in k.items()
                        },
                        "g5_split_families": g5_counts["split_families"],
                        "g5_offending_documents": g5_counts["offending_documents"],
                    },
                },
                indent=2,
            )
        )
        print(f"\n  report -> {report_path}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
