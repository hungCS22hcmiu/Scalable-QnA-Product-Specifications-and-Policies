"""Plan step 12: the measurements earlier items carried to 3.6, read from the gate's export.

Read-only, and counts only: the output holds no qa_id, no question text and no asin. They are
recorded, not acted on (spec "Carried into this item"); if one shows a problem it becomes a new task.

    python3 docs/work/2026-10-22-corpus-freeze/tools/probe_checks.py --export-dir data/v1-draft/gate/run1

| Output | Rule | Reads |
| :--- | :--- | :--- |
| scoped- and unscoped-set sizes | distribution per split, beside G1 | both |
| U12 (a) | per probe, the Jaccard of its scoped top-k with its partner's | both |
| U12 (b) | per probe, whether the two evidence spans share a chunk (flags file) | both |
| U11 | is the seed's evidence chunk in the scoped top-k: any chunk, all chunks | both |
| U10 | `policy_frac` of the policy queries, and the lane under each band | validation only |
| sibling rate | does a condition twin's top-k hold a chunk of the other twin's document | validation only |
| units | does every unit in v1's policy terms sit in the gateway's numeric unit list | the 12 policy files |

U10 and the sibling rate read validation only. A table of them on the test split, read later to pick
the lane band, would be tuning on test (ADR-012), so the functions refuse it, whatever the caller asks.

The evidence strings come from `evidence_spans.py`. A span is mapped to the chunks it touches by
character offsets in the document text (whitespace collapsed), so a span over two chunks is reported
as "any" and "all".
"""

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "experiments" / "scripts"))
import corpus_gate

SPLITS = corpus_gate.SPLITS
TWIN_KINDS = ("policy-condition", "condition-department")
# The gateway's lane band (cmd/gateway/main.go): the collapsed default, and the measured candidate.
# Read here, never changed.
BANDS = {"default, collapsed (Lo = Hi = 0.20)": (0.20, 0.20), "candidate [0.20, 0.60)": (0.20, 0.60)}
J_BINS = ("0", "(0, 0.2]", "(0.2, 0.5]", "(0.5, 1)", "1")
GO_NUMERIC = REPO / "gateway" / "internal" / "reuse" / "support_numeric.go"
OUT = REPO / "docs" / "work" / "2026-10-22-corpus-freeze" / "evidence" / "probe-checks.md"
FLAGS = REPO / "data" / "v1-draft" / "gate" / "probe-flags.json"


class Refused(Exception):
    """A rule stopped the check before it read anything it must not."""


# =================================================================================================
# Evidence span -> chunks
# =================================================================================================
def collapse_with_map(text: str) -> tuple[str, list[int]]:
    """`" ".join(text.split())` and, for each character of the result, its index in `text`. A run
    of whitespace becomes one space, mapped to the first character of the run."""
    chars: list[str] = []
    index: list[int] = []
    gap: int | None = None  # where a run of whitespace after some text began
    for i, ch in enumerate(text):
        if ch.isspace():
            if gap is None and chars:
                gap = i
            continue
        if gap is not None:
            chars.append(" ")
            index.append(gap)
            gap = None
        chars.append(ch)
        index.append(i)
    return "".join(chars), index


def evidence_chunks(text: str, chunks: list[tuple[str, int, int]], evidence: str) -> list[str] | None:
    """The chunks whose character range touches the evidence span, or None if the span is not in
    the document text. `chunks` are `(chunk_id, start, end)` in the document text."""
    needle = " ".join(evidence.split())
    if not needle:
        return None
    collapsed, index = collapse_with_map(text)
    at = collapsed.find(needle)
    if at < 0:
        return None
    start, end = index[at], index[at + len(needle) - 1] + 1
    return [cid for cid, s, e in chunks if s < end and start < e]


def chunk_geometry(corpus_dir: Path):
    """`(document text by doc_id, [(chunk_id, start, end)] by doc_id)` for a corpus directory, from
    ingest's own split function."""
    from rag.ingest import load_records, record_to_document, records_to_nodes

    records = load_records(corpus_dir)
    texts = {r["doc_id"]: record_to_document(r).text for r in records}
    chunks: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for node in records_to_nodes(records, "v1"):
        chunks[node.metadata["doc_id"]].append((node.id_, node.start_char_idx, node.end_char_idx))
    return texts, chunks


def evidence_chunk_sets(spans: dict[str, dict], texts, chunks) -> tuple[dict, Counter]:
    """`qa_id -> list of chunk ids` (None if the span was not found) for every given span."""
    out: dict[str, list[str] | None] = {}
    counts: Counter = Counter()
    for qa_id, span in spans.items():
        doc = span["doc_id"]
        if doc not in texts:
            out[qa_id] = None
            counts["the span's document is not in the corpus"] += 1
            continue
        found = evidence_chunks(texts[doc], chunks[doc], span["evidence"])
        out[qa_id] = found
        counts["located" if found else "not located in the document text"] += 1
        if found and len(found) > 1:
            counts["located, over more than one chunk"] += 1
    return out, counts


# =================================================================================================
# The checks. Plain data in, plain data out.
# =================================================================================================
def _by_split(records: list[dict], split: str) -> list[dict]:
    return [r for r in records if r["split"] == split]


def size_distribution(records, retrieval, split) -> dict[str, Counter]:
    out = {"scoped": Counter(), "unscoped": Counter()}
    for r in _by_split(records, split):
        row = retrieval[split][r["qa_id"]]
        out["scoped"][row["n_scoped"]] += 1
        out["unscoped"][row["n_unscoped"]] += 1
    return out


def _j_bin(j: float) -> str:
    if j == 0:
        return "0"
    if j == 1:
        return "1"
    if j <= 0.2:
        return "(0, 0.2]"
    return "(0.2, 0.5]" if j <= 0.5 else "(0.5, 1)"


def u12a(records, retrieval, split) -> dict[str, dict]:
    """Per probe kind: how many probes, the bins of J(scoped, partner's scoped) and the median."""
    by_id = {r["qa_id"]: r for r in records}
    values: dict[str, list[float]] = defaultdict(list)
    missing: Counter = Counter()
    for r in _by_split(records, split):
        if not r["pair_of"]:
            continue
        partner = retrieval[split].get(r["pair_of"])
        if partner is None or by_id[r["pair_of"]]["split"] != split:
            missing[r["probe_kind"]] += 1
            continue
        values[r["probe_kind"]].append(
            corpus_gate.jaccard(tuple(retrieval[split][r["qa_id"]]["scoped"]), tuple(partner["scoped"]))
        )
    out = {}
    for kind in sorted(set(values) | set(missing)):
        v = sorted(values[kind])
        out[kind] = {
            "n": len(v),
            "no partner in this split": missing[kind],
            "bins": dict(Counter(_j_bin(j) for j in v)),
            "median": v[len(v) // 2] if v else None,
        }
    return out


def u12b(records, evidence) -> tuple[dict[str, dict], dict[str, dict[str, Counter]]]:
    """`(flags, table)`. For every probe: do its evidence span and its partner's share a chunk?
    True or False when both are located, None when either has no span or it was not found. The
    flags are independent of any retrieval, so they are the same for every run."""
    flags: dict[str, dict] = {}
    table: dict[str, dict[str, Counter]] = {s: defaultdict(Counter) for s in SPLITS}
    for r in records:
        if not r["pair_of"]:
            continue
        mine, theirs = evidence.get(r["qa_id"]), evidence.get(r["pair_of"])
        shares = None if not mine or not theirs else bool(set(mine) & set(theirs))
        flags[r["qa_id"]] = {"partner": r["pair_of"], "shares_chunk": shares}
        label = {True: "share a chunk", False: "disjoint", None: "no span"}[shares]
        table[r["split"]][r["probe_kind"]][label] += 1
    return dict(sorted(flags.items())), table


def u11(records, retrieval, evidence, split) -> dict[str, int]:
    """For the seeds with an evidence span: is the span's chunk in the scoped top-k."""
    out: Counter = Counter()
    for r in _by_split(records, split):
        if r["role"] != "seed" or r["qa_id"] not in evidence:
            continue
        out["seeds with an evidence span"] += 1
        chunks = evidence[r["qa_id"]]
        if not chunks:
            out["span not located"] += 1
            continue
        out["span located"] += 1
        if len(chunks) > 1:
            out["span over more than one chunk"] += 1
        row = retrieval[split][r["qa_id"]]
        for where in ("scoped", "unscoped"):
            got = set(row[where])
            out[f"any chunk of the span in the {where} top-k"] += bool(set(chunks) & got)
            out[f"all chunks of the span in the {where} top-k"] += set(chunks) <= got
    return dict(out)


def policy_fraction(chunk_ids) -> float:
    """gateway/internal/reuse/lane.go PolicyFraction."""
    return sum(c.startswith("policy-") for c in chunk_ids) / len(chunk_ids) if chunk_ids else 0.0


def classify(frac: float, lo: float, hi: float, empty: bool = False) -> str:
    """lane.go Classify: SPEC below Lo, MIXED from Lo to Hi, POLICY from Hi; 0 is SPEC, 1 POLICY."""
    if empty or frac == 0:
        return "SPEC"
    if frac == 1 or frac >= hi:
        return "POLICY"
    return "MIXED" if frac >= lo else "SPEC"


def _require_validation(records, retrieval, split, what):
    if split != "validation":
        raise Refused(f"{what} is read on validation only (ADR-012); refused on {split!r}")
    mine = {r["qa_id"] for r in _by_split(records, split)}
    wrong = [q for q in retrieval[split] if q not in mine]
    if wrong:
        raise Refused(f"{what}: {len(wrong)} row(s) in the validation export are not validation records")


def u10(records, retrieval, split) -> dict:
    """The `policy_frac` distribution of the policy queries, and how each band classifies them."""
    _require_validation(records, retrieval, split, "U10")
    groups = {
        "policy queries": lambda r: r["doc_ids"][0].startswith("policy-"),
        "D queries (a product and a policy)": lambda r: r["role"] == "d",
        "product-only queries": lambda r: all(d.startswith("product-") for d in r["doc_ids"]),
    }
    out = {}
    for name, member in groups.items():
        rows = [retrieval[split][r["qa_id"]]["scoped"] for r in _by_split(records, split) if member(r)]
        fracs = [policy_fraction(ids) for ids in rows]
        out[name] = {
            "n": len(rows),
            "policy_frac": dict(sorted(Counter(round(f, 3) for f in fracs).items())),
            "lanes": {
                band: dict(Counter(classify(f, lo, hi, empty=not ids) for f, ids in zip(fracs, rows, strict=True)))
                for band, (lo, hi) in BANDS.items()
            },
        }
    return out


def sibling_rate(records, retrieval, split) -> dict[str, int]:
    """For each condition twin: does its scoped top-k hold a chunk of its own document, and of the
    other twin's document?"""
    _require_validation(records, retrieval, split, "the sibling rate")
    by_id = {r["qa_id"]: r for r in records}
    out: Counter = Counter()
    for r in _by_split(records, split):
        if r["probe_kind"] not in TWIN_KINDS:
            continue
        docs = {c.split("#")[0] for c in retrieval[split][r["qa_id"]]["scoped"]}
        own, sibling = r["doc_ids"][0], by_id[r["pair_of"]]["doc_ids"][0]
        out["twin records"] += 1
        out["top-k holds a chunk of its own document"] += own in docs
        out["top-k holds a chunk of the other twin's document"] += sibling in docs
        out["top-k holds both"] += own in docs and sibling in docs
        out["top-k holds the other twin's document and not its own"] += sibling in docs and own not in docs
    return dict(out)


# --- the numeric unit list ------------------------------------------------------------------------
def go_unit_list(source: str) -> tuple[set[str], dict[str, str], str]:
    units = re.search(r"var numUnits = map\[string\]struct\{\}\{(.*?)\n\}", source, re.DOTALL)
    alias = re.search(r"var numUnitAlias = map\[string\]string\{(.*?)\n\}", source, re.DOTALL)
    currency = re.search(r'const numCurrency = "([^"]+)"', source)
    if not (units and alias and currency):
        raise Refused("the numeric unit list was not found in support_numeric.go")
    return (
        set(re.findall(r'"([a-z]+)": \{\}', units.group(1))),
        dict(re.findall(r'"([a-z]+)": "([a-z]+)"', alias.group(1))),
        currency.group(1),
    )


def canon_unit(word: str, units: set[str], alias: dict[str, str]) -> str | None:
    """A mirror of support_numeric.go canonUnit."""
    if word in alias:
        return alias[word]
    if word in units:
        return word
    if len(word) >= 3 and word.endswith("s"):
        stem = word[:-1]
        return alias.get(stem) or (stem if stem in units else None)
    return None


def unit_check(policy_dir: Path, go_source: str) -> dict:
    units, alias, currency = go_unit_list(go_source)
    out: Counter = Counter()
    unlisted: Counter = Counter()
    for path in sorted(policy_dir.glob("*.json")):
        for term in json.loads(path.read_text()).get("terms", []):
            out["policy terms"] += 1
            found = re.search(rf"(?P<cur>[{re.escape(currency)}])?\s*\d[\d.,]*\s*(?P<word>[A-Za-z]+)?", term)
            if not found:
                out["terms without a number"] += 1
            elif found["cur"]:
                out["terms read by a currency symbol"] += 1
            elif found["word"] and canon_unit(found["word"].lower(), units, alias):
                out["terms read by a listed unit"] += 1
            else:
                out["terms with a number and no listed unit"] += 1
                unlisted[(found["word"] or "(none)").lower()] += 1
    return {"counts": dict(out), "unlisted words": dict(unlisted)}


# =================================================================================================
# Reading the export, writing the output
# =================================================================================================
def load_export(export_dir: Path, records: list[dict]) -> dict[str, dict[str, dict]]:
    """`{split: {qa_id: row}}`. A file whose rows belong to the other split is refused."""
    by_id = {r["qa_id"]: r for r in records}
    out = {}
    for split in SPLITS:
        rows = json.loads((export_dir / f"retrieval-{split}.json").read_text())
        wrong = sum(by_id[row["qa_id"]]["split"] != split for row in rows)
        if wrong:
            raise Refused(f"retrieval-{split}.json holds {wrong} row(s) of the other split")
        out[split] = {row["qa_id"]: row for row in rows}
    return out


def _table(header: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| :--- " + "| ---: " * (len(header) - 1) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return lines + [""]


def render(result: dict) -> list[str]:
    lines = ["# Carried measurements — item 3.6, plan step 12", "",
             "Written by `tools/probe_checks.py`. Counts only: no qa_id, no question text, no asin.",
             "Recorded, not acted on. U10 and the sibling rate are on validation only (ADR-012).", ""]
    lines += ["## Evidence spans (U4)", ""]
    lines += _table(["what", "n"], [[k, v] for k, v in result["spans"].items()])
    lines += ["## Retrieved-set sizes (beside G1)", ""]
    for split in SPLITS:
        sizes = result["sizes"][split]
        keys = sorted(set(sizes["scoped"]) | set(sizes["unscoped"]))
        lines += [f"**{split}**", ""]
        lines += _table(["size", "scoped", "unscoped"], [[k, sizes["scoped"][k], sizes["unscoped"][k]] for k in keys])
    lines += ["## U12 (a): J(scoped top-k, partner's scoped top-k), per probe", ""]
    for split in SPLITS:
        lines += [f"**{split}**", ""]
        rows = [[k, v["n"], v["no partner in this split"], *[v["bins"].get(b, 0) for b in J_BINS],
                 "-" if v["median"] is None else f"{v['median']:.3f}"]
                for k, v in result["u12a"][split].items()]
        lines += _table(["probe kind", "n", "no partner", *J_BINS, "median"], rows)
    lines += ["## U12 (b): do a probe's evidence span and its partner's share a chunk", "",
              "`no span`: a policy cell has none, or the span was not found. The per-probe flags are in a",
              f"gitignored file; their sha256 is `{result['flags_sha256']}`.", ""]
    for split in SPLITS:
        lines += [f"**{split}**", ""]
        rows = [[k, c["share a chunk"], c["disjoint"], c["no span"]] for k, c in sorted(result["u12b"][split].items())]
        lines += _table(["probe kind", "share a chunk", "disjoint", "no span"], rows)
    lines += ["## U11: is the seed's evidence chunk in the top-k", ""]
    for split in SPLITS:
        lines += [f"**{split}**", ""]
        lines += _table(["what", "n"], [[k, v] for k, v in result["u11"][split].items()])
    lines += ["## U10: `policy_frac` of the retrieval, validation only", ""]
    for name, g in result["u10"].items():
        lines += [f"**{name}** (n = {g['n']})", ""]
        lines += _table(["policy_frac", "n"], [[k, v] for k, v in g["policy_frac"].items()])
        lanes = ["SPEC", "MIXED", "POLICY"]
        lines += _table(["band", *lanes], [[b, *[c.get(lane, 0) for lane in lanes]] for b, c in g["lanes"].items()])
    lines += ["## Sibling rate, validation only", ""]
    lines += _table(["what", "n"], [[k, v] for k, v in result["sibling"].items()])
    lines += ["## Policy terms against the gateway's numeric unit list", ""]
    lines += _table(["what", "n"], [[k, v] for k, v in result["units"]["counts"].items()])
    if result["units"]["unlisted words"]:
        lines += ["Words after a number that are not listed units: "
                  + ", ".join(f"`{w}` ({n})" for w, n in sorted(result["units"]["unlisted words"].items())), ""]
    return lines


def write_flags(path: Path, flags: dict) -> str:
    corpus_gate.require_git_ignored(path)  # the flags hold qa_ids
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"version": 1, "flags": flags}, indent=1, sort_keys=True)
    path.write_text(body)
    return hashlib.sha256(body.encode()).hexdigest()


def run(records, retrieval, spans, texts, chunks, policy_dir, go_source, flags_path) -> dict:
    evidence, span_counts = evidence_chunk_sets(spans, texts, chunks)
    flags, table = u12b(records, evidence)
    return {
        "spans": dict(span_counts),
        "sizes": {s: size_distribution(records, retrieval, s) for s in SPLITS},
        "u12a": {s: u12a(records, retrieval, s) for s in SPLITS},
        "u12b": table,
        "flags_sha256": write_flags(flags_path, flags),
        "u11": {s: u11(records, retrieval, evidence, s) for s in SPLITS},
        "u10": u10(records, retrieval, "validation"),
        "sibling": sibling_rate(records, retrieval, "validation"),
        "units": unit_check(policy_dir, go_source),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--export-dir", type=Path, required=True, help="the gate's --retrieval-out directory")
    ap.add_argument("--corpus-dir", type=Path, default=REPO / "data" / "v1")
    ap.add_argument("--workload", type=Path, default=REPO / "data" / "workload-v1.json")
    ap.add_argument("--evidence", type=Path, default=REPO / "data" / "v1-draft" / "gate" / "evidence-spans.json")
    ap.add_argument("--policy-dir", type=Path, default=REPO / "data" / "policies-v1")
    ap.add_argument("--flags-out", type=Path, default=FLAGS)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)

    records = json.loads(args.workload.read_text())
    texts, chunks = chunk_geometry(args.corpus_dir)
    try:
        result = run(
            records, load_export(args.export_dir, records), json.loads(args.evidence.read_text()),
            texts, chunks, args.policy_dir, GO_NUMERIC.read_text(), args.flags_out,
        )
    except Refused as e:
        print(f"REFUSED — {e}", file=sys.stderr)
        return 2
    args.out.write_text("\n".join(render(result)) + "\n")
    print(f"wrote {args.out.relative_to(REPO)}; flags sha256 {result['flags_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
