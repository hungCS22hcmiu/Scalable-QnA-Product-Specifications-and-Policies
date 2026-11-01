"""Does product-scoped retrieval bring in policy chunks from ANOTHER category? v1 validation. citable: no.

For each validation query: the product's category (from product_id), the categories of the policy chunks
in the scoped top-k, and the category of the rank-1 policy chunk (the POLICY lane's namespace and the
policy half of the MIXED namespace). Lanes are recomputed as the gateway would: closed band (MIXED off,
>= 0.20 -> POLICY) and the on band [0.20, 0.60). Prints counts and doc IDs only.
"""

import collections
import json

from rag import retrieve


def cat_of_product(pid):
    return pid.split("-")[1] if pid else None


def cat_of_policy(doc_id):
    # policy-{kind}-{category}[-{condition}]
    return doc_id.split("-")[2]


def lane(frac, hi):
    if frac == 0:
        return "SPEC"
    if frac == 1 or frac >= hi:
        return "POLICY"
    if frac >= 0.20:
        return "MIXED"
    return "SPEC"


with open("data/workload-v1-validation.json") as f:
    items = json.load(f)

rows = []
for i in items:
    pid = i.get("product_id")
    chunks, _ = retrieve.retrieve(i["question"], product_id=pid or None)
    ids = [c.chunk_id for c in chunks]
    pol = [x.split("#")[0] for x in ids if x.startswith("policy-")]
    frac = len(pol) / len(ids) if ids else 0.0
    gold_pol = [d for d in i["doc_ids"] if d.startswith("policy-")]
    rows.append(
        {
            "stratum": i["stratum"],
            "pcat": cat_of_product(pid),
            "pol": pol,
            "rank1": pol[0] if pol else None,
            "gold_pol": gold_pol,
            "lane_off": lane(frac, 0.20),
            "lane_on": lane(frac, 0.60),
            "has_pid": bool(pid),
        }
    )

print(
    f"validation queries: {len(rows)}; with product_id: {sum(r['has_pid'] for r in rows)}"
)


def report(name, sub):
    with_pol = [r for r in sub if r["pol"] and r["pcat"]]
    any_wrong = [
        r for r in with_pol if any(cat_of_policy(d) != r["pcat"] for d in r["pol"])
    ]
    r1_wrong = [r for r in with_pol if cat_of_policy(r["rank1"]) != r["pcat"]]
    gold = [r for r in with_pol if r["gold_pol"]]
    r1_not_gold = [r for r in gold if r["rank1"] not in r["gold_pol"]]
    print(
        f"  {name:<34} n={len(sub):>3} | with policy chunk {len(with_pol):>3}"
        f" | any other-category policy chunk {len(any_wrong):>3}"
        f" | rank-1 policy other category {len(r1_wrong):>3}"
        f" | policy-grounded {len(gold):>3}, rank-1 != gold {len(r1_not_gold):>3}"
    )
    return r1_wrong


print("\nBY LANE, MIXED off (the default band)")
for ln in ("SPEC", "POLICY"):
    report(f"lane {ln}", [r for r in rows if r["lane_off"] == ln])
print("\nBY LANE, MIXED on [0.20, 0.60)")
for ln in ("SPEC", "MIXED", "POLICY"):
    report(f"lane {ln}", [r for r in rows if r["lane_on"] == ln])
print("\nBY STRATUM")
for st in sorted({r["stratum"] for r in rows}):
    report(f"stratum {st}", [r for r in rows if r["stratum"] == st])

print(
    "\nRANK-1 OTHER-CATEGORY CASES among policy-grounded queries (product category -> rank-1 doc), counts"
)
c = collections.Counter(
    (r["pcat"], r["rank1"])
    for r in rows
    if r["gold_pol"]
    and r["pol"]
    and r["pcat"]
    and cat_of_policy(r["rank1"]) != r["pcat"]
)
for (pc, d), n in c.most_common():
    print(f"  {n:>3}  {pc:<12} -> {d}")
