"""Category-selection probe for Amazon-PQA. Investigation `pqa-category-choice` -- scratch, not source.

Written against the bytes (asin, bullet_point1..5, question_type, answers[], answer_aggregated),
not against readme.txt, which names fields the data does not use.

    python3 pqa_category_probe.py <file.json> [...]   -> prints a table, writes probe_results.json
"""

import hashlib
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ND_LO, ND_HI = 0.45, 0.99   # near-duplicate band, content-word Jaccard (2026-09-21 probe definition)
FLIP_LO = 0.30              # looser band for value-flip candidates: "windows 10" vs "windows 7" is J = 0.33
PAIR_CAP = 100              # questions per product considered for pairwise checks (file order)
STOP = set("""
a an the this that these those it its it's is are was were be been being am do does did done doing
will would can could should shall may might must have has had having i me my we our you your he she
they them their there here what which who whom whose when where why how if then than so too very
just only also of in on at to for from by with about as into onto over under up down out off and or
but not no nor any some all each both either neither other such own same more most less few much
many get got gets getting one ones s t
""".split())
POLICY_Q = {
    "warranty": re.compile(r"\bwarrant(y|ies|ee)\b", re.I),
    "return": re.compile(r"\b(return(ed|s|ing)?|refund(ed)?|restock(ing)?)\b", re.I),
}
# Dynamic content (price, stock) must never enter the cache, so it never enters the workload either.
# An indicator, not a classifier: "how much weight" is excluded, "$" followed by a digit is not.
DYNAMIC_Q = re.compile(
    r"\$\s?\d|\bprices?\b|\bpriced\b|\bcost(s|ing)?\b|\bhow much (is|for|are|does it cost)\b"
    r"|\b(in|out of|back in) stock\b|\bsold out\b|\bon sale\b|\bdiscount|\bcoupon",
    re.I,
)
# Carrier / unlock / SIM questions: answered by the carrier's network, not by a product document or
# a store policy (investigation F11). Reported, and removed for the capped pool's second variant.
CARRIER_Q = re.compile(
    r"\b(verizon|at ?& ?t|att|t-?mobile|sprint|cricket|metro ?pcs|straight ?talk|boost|tracfone"
    r"|carrier|unlock(ed|ing)?|sim)\b",
    re.I,
)
CAP_LO, CAP_HI = 5, 50      # questions per product admitted to the capped pool, so K stays bounded
WARRANTY_TERM = re.compile(
    r"(\d+|one|two|three|five|ten|lifetime)[- ]?(year|yr|month|day)s?[^.]{0,40}warrant"
    r"|warrant[^.]{0,40}?(\d+|one|two|three|five|ten|lifetime)[- ]?(year|yr|month|day)",
    re.I,
)
PROSE_FIELDS = ["bullet_point1", "bullet_point2", "bullet_point3", "bullet_point4",
                "bullet_point5", "product_description"]


def content_tokens(text):
    return frozenset(t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP and len(t) > 1)


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def pct(n, d):
    return round(100.0 * n / d, 1) if d else 0.0


def probe(path):
    h = hashlib.sha256()
    with path.open("rb") as f:          # streamed: the largest category file is 821 MB
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    sha = h.hexdigest()
    lines = path.open("rb")

    by_asin = defaultdict(list)
    prose = {}
    parsed = bad = 0
    agg = Counter()
    qtype = Counter()
    pol = Counter()
    for line in lines:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        asin, q = r.get("asin") or "", (r.get("question_text") or "").strip()
        if not asin or not q:
            bad += 1
            continue
        parsed += 1
        by_asin[asin].append((q, r.get("question_type"), r.get("answer_aggregated")))
        agg[r.get("answer_aggregated")] += 1
        qtype[r.get("question_type")] += 1
        for k, rx in POLICY_Q.items():
            if rx.search(q):
                pol[k] += 1
        if asin not in prose:
            prose[asin] = " ".join((r.get(f) or "").strip() for f in PROSE_FIELDS).strip()
    if parsed == 0:
        raise SystemExit(f"{path.name}: ZERO parseable records -- builder is reading the wrong fields")

    qpp = sorted(len(v) for v in by_asin.values())
    multi = [a for a, v in by_asin.items() if len(v) >= 2]
    thick = [a for a, v in by_asin.items() if len(v) >= 5]

    nd_multi = set()          # products (>= 2 q) with >= 1 near-duplicate pair -- reproduction metric
    nd_pairs = 0
    disagree_pairs = 0        # near-duplicate yes/no pairs whose community answers disagree: answer NOISE
    flip_pairs = 0            # same question shape, one numeric slot swapped: B-within CANDIDATES
    flip_products = set()
    examples = {"disagree": [], "flip": []}
    for a in multi:
        qs = by_asin[a][:PAIR_CAP]
        toks = [content_tokens(q) for q, _, _ in qs]
        for i in range(len(qs)):
            for j in range(i + 1, len(qs)):
                if toks[i] == toks[j]:
                    continue  # exact repeat after normalisation: excluded, as in the 2026-09-21 probe
                s = jaccard(toks[i], toks[j])
                (qi, ti, ai), (qj, tj, aj) = qs[i], qs[j]
                if ND_LO <= s <= ND_HI:
                    nd_pairs += 1
                    nd_multi.add(a)
                    if ti == tj == "yes-no" and {ai, aj} == {"yes", "no"}:
                        disagree_pairs += 1
                        if len(examples["disagree"]) < 3:
                            examples["disagree"].append([qi, ai, qj, aj, round(s, 2)])
                if s >= FLIP_LO:
                    da, db = toks[i] - toks[j], toks[j] - toks[i]
                    if (1 <= len(da) <= 2 and 1 <= len(db) <= 2 and len(toks[i] & toks[j]) >= 2
                            and any(c.isdigit() for t in da for c in t)
                            and any(c.isdigit() for t in db for c in t)):
                        flip_pairs += 1
                        flip_products.add(a)
                        if len(examples["flip"]) < 5:
                            examples["flip"].append([qi, qj, round(s, 2)])

    usable = [a for a in thick if a in nd_multi]

    # Products already asking BOTH policy dimensions: the shape data-card.md section 2 says B-within
    # pairs must be BUILT from ("how long is the warranty" vs "how long is the return period").
    has = {k: {a for a, v in by_asin.items() if any(rx.search(q) for q, _, _ in v)}
           for k, rx in POLICY_Q.items()}
    both_policy = has["warranty"] & has["return"]

    # The same test with dynamic questions removed first -- the pool a static workload can draw on.
    n_dynamic = 0
    usable_static = []
    for a, v in by_asin.items():
        qs = [q for q, _, _ in v if not DYNAMIC_Q.search(q)]
        n_dynamic += len(v) - len(qs)
        if len(qs) < 5:
            continue
        toks = [content_tokens(q) for q in qs[:PAIR_CAP]]
        if any(t != u and ND_LO <= jaccard(t, u) <= ND_HI
               for i, t in enumerate(toks) for u in toks[i + 1:]):
            usable_static.append(a)
    def capped_pool(drop):
        n = 0
        for v in by_asin.values():
            qs = [q for q, _, _ in v if not drop(q)]
            if not CAP_LO <= len(qs) <= CAP_HI:
                continue
            toks = [content_tokens(q) for q in qs]
            if any(t != u and ND_LO <= jaccard(t, u) <= ND_HI
                   for i, t in enumerate(toks) for u in toks[i + 1:]):
                n += 1
        return n

    n_carrier = sum(1 for v in by_asin.values() for q, _, _ in v if CARRIER_Q.search(q))
    n_capped = capped_pool(lambda q: DYNAMIC_Q.search(q))
    n_capped_nocarrier = capped_pool(lambda q: DYNAMIC_Q.search(q) or CARRIER_Q.search(q))

    plen = sorted(len(prose[a]) for a in by_asin)
    warr_prose = sum(1 for a in by_asin if re.search(r"warrant", prose[a], re.I))
    warr_term = sum(1 for a in by_asin if WARRANTY_TERM.search(prose[a]))
    usable_warr_term = sum(1 for a in usable if WARRANTY_TERM.search(prose[a]))

    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha,
        "records_parsed": parsed,
        "records_unparsed": bad,
        "products": len(by_asin),
        "questions": parsed,
        "qpp_mean": round(statistics.mean(qpp), 1),
        "qpp_median": statistics.median(qpp),
        "qpp_p90": qpp[int(0.9 * (len(qpp) - 1))],
        "qpp_max": qpp[-1],
        "pct_ge2": pct(len(multi), len(by_asin)),
        "pct_ge5": pct(len(thick), len(by_asin)),
        "n_ge5": len(thick),
        "pct_multi_with_nd": pct(len(nd_multi), len(multi)),
        "nd_pairs": nd_pairs,
        "n_usable_ge5_and_nd": len(usable),
        "pct_q_dynamic": pct(n_dynamic, parsed),
        "n_usable_static": len(usable_static),
        "pct_q_carrier": pct(n_carrier, parsed),
        "n_capped": n_capped,
        "n_capped_nocarrier": n_capped_nocarrier,
        "nd_answer_disagree_pairs": disagree_pairs,
        "pct_nd_answer_disagree": pct(disagree_pairs, nd_pairs),
        "flip_candidate_pairs": flip_pairs,
        "flip_candidate_products": len(flip_products),
        "examples": examples,
        "pct_q_warranty": pct(pol["warranty"], parsed),
        "pct_q_return": pct(pol["return"], parsed),
        "n_q_warranty": pol["warranty"],
        "n_q_return": pol["return"],
        "n_products_warranty_q": len(has["warranty"]),
        "n_products_return_q": len(has["return"]),
        "n_products_both_policy_q": len(both_policy),
        "prose_median_chars": plen[len(plen) // 2],
        "pct_prose_mentions_warranty": pct(warr_prose, len(by_asin)),
        "pct_prose_states_warranty_term": pct(warr_term, len(by_asin)),
        "pct_usable_prose_states_warranty_term": pct(usable_warr_term, len(usable)),
        "question_type": dict(qtype),
        "answer_aggregated": dict(agg),
    }


def main():
    out = [probe(Path(p)) for p in sys.argv[1:]]
    Path(__file__).with_name("probe_results.json").write_text(json.dumps(out, indent=1))
    cols = ["products", "questions", "qpp_median", "pct_ge5", "n_ge5", "pct_multi_with_nd",
            "pct_q_dynamic", "n_capped", "pct_q_carrier", "n_capped_nocarrier", "pct_nd_answer_disagree", "flip_candidate_products", "n_q_warranty", "n_q_return", "n_products_both_policy_q",
            "prose_median_chars", "pct_prose_states_warranty_term"]
    print("category".ljust(28) + "".join(c[:12].rjust(13) for c in cols))
    for r in out:
        name = r["file"].removeprefix("amazon_pqa_").removesuffix(".json")
        print(name[:27].ljust(28) + "".join(str(r[c]).rjust(13) for c in cols))


if __name__ == "__main__":
    main()
