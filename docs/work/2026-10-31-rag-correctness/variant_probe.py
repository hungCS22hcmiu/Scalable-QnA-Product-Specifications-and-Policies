"""Plan step 1.1: measure ADR-021's two refill variants on the v1 validation split. citable: no.

Run from the repo root, with v1 in Redis (embedding model only):
    python3 docs/work/2026-10-31-rag-correctness/variant_probe.py
Prints, for "before" (ADR-020 retrieval, refill off), V1 (always refill) and V2 (refill only when no
policy chunk ranked): own-chunk counts per spec question, lane counts under both MIXED arms, the
category probe, the rank-1 policy against the gold one, the condition-routing probe, and the five
cases of plan step 1.2. Counts and document IDs only.
"""

import collections
import json
import re

from rag import retrieve as R

SPLIT = {
    "policy-return-phones-opened": "opened",
    "policy-return-phones-unopened": "unopened",
    "policy-return-furniture-opened": "opened",
    "policy-return-furniture-unopened": "unopened",
    "policy-return-laptops-new": "new",
    "policy-return-laptops-renewed": "renewed",
    "policy-warranty-phones-domestic": "domestic",
    "policy-warranty-phones-international": "international",
}
SYN = {
    "unopened": ["still sealed", "never opened", "brand-new in its sealed box"],
    "opened": ["used", "unboxed", "already taken out of the box"],
    "renewed": ["refurbished", "pre-owned"],
    "new": ["brand-new", "factory-sealed"],
    "international": ["overseas", "imported"],
    "domestic": ["US", "local"],
}
CASES = [
    ("product-electronics-b07r8pr5yz", "What comes in the box?", {"#chunk-5"}),
    (
        "product-electronics-b07r8pr5yz",
        "How long does a full charge take?",
        {"#chunk-0", "#chunk-5"},
    ),
    ("product-electronics-b07b63r768", "Are these headphones foldable?", {"#chunk-1"}),
    ("product-electronics-b07b63r768", "What is the standby time?", {"#chunk-1"}),
    ("product-electronics-b07b63r768", "Is a carrying case included?", {"#chunk-1"}),
]


def lane(ids, hi):
    if not ids:
        return "SPEC"
    frac = sum(i.startswith("policy-") for i in ids) / len(ids)
    if frac == 0:
        return "SPEC"
    if frac == 1 or frac >= hi:
        return "POLICY"
    return "MIXED" if frac >= 0.20 else "SPEC"


def ids_of(q, pid):
    chunks, _ = R.retrieve(q, product_id=pid or None)
    return [c.chunk_id for c in chunks]


def first_policy(ids):
    return next((i.split("#")[0] for i in ids if i.startswith("policy-")), None)


def measure(name):
    with open("data/workload-v1-validation.json") as f:
        items = json.load(f)
    own, lanes_off, lanes_on = (
        collections.Counter(),
        collections.Counter(),
        collections.Counter(),
    )
    foreign = r1_wrong = grounded = 0
    cond = {True: [0, 0], False: [0, 0]}
    for i in items:
        pid = i.get("product_id")
        ids = ids_of(i["question"], pid)
        lanes_off[lane(ids, 0.20)] += 1
        lanes_on[lane(ids, 0.60)] += 1
        if pid and all(d.startswith("product-") for d in i["doc_ids"]):
            own[sum(x.split("#")[0] == pid for x in ids)] += 1
        pol = [x.split("#")[0] for x in ids if x.startswith("policy-")]
        if pid and pol:
            cat = pid.split("-")[1]
            foreign += any(d.split("-")[2] != cat for d in pol)
            gold = [d for d in i["doc_ids"] if d.startswith("policy-")]
            if gold:
                grounded += 1
                r1_wrong += pol[0] not in gold
        gold_c = [d for d in i["doc_ids"] if d in SPLIT]
        if gold_c:
            lit = re.search(rf"\b{SPLIT[gold_c[0]]}\b", i["question"], re.IGNORECASE) is not None
            cond[lit][1] += 1
            cond[lit][0] += first_policy(ids) == gold_c[0]
    seen, syn_ok, syn_n = set(), 0, 0
    for i in items:
        gold_c = [d for d in i["doc_ids"] if d in SPLIT]
        if not gold_c:
            continue
        word = SPLIT[gold_c[0]]
        if (
            not re.search(rf"\b{word}\b", i["question"], re.IGNORECASE)
            or (gold_c[0], i["product_id"]) in seen
        ):
            continue
        seen.add((gold_c[0], i["product_id"]))
        for s in SYN[word]:
            q = re.sub(rf"\b{word}\b", s, i["question"], count=1, flags=re.IGNORECASE)
            syn_n += 1
            syn_ok += first_policy(ids_of(q, i.get("product_id"))) == gold_c[0]
        if len(seen) >= 16:
            break
    cases = sum(any(f"{p}{s}" in ids_of(q, p) for s in want) for p, q, want in CASES)
    print(f"\n== {name}")
    print(
        "  own-product chunks per spec question:",
        dict(sorted(own.items())),
        f"(n={sum(own.values())})",
    )
    print(
        "  lanes, MIXED off:",
        dict(sorted(lanes_off.items())),
        "| MIXED on:",
        dict(sorted(lanes_on.items())),
    )
    print(f"  foreign-category policy chunk: {foreign}", end="")
    print(f" | rank-1 policy not gold: {r1_wrong} / {grounded}")
    present, absent = cond[True], cond[False]
    print(f"  condition-routing: word present {present[0]}/{present[1]},", end="")
    print(f" absent {absent[0]}/{absent[1]}, synonyms {syn_ok}/{syn_n}")
    print(f"  plan 1.2 cases retrieving their answer chunk: {cases}/5")


orig_refill = R._ensure_own_chunks
R._ensure_own_chunks = lambda index, natural, q, pid, k: R._drop_other_products(
    natural, pid
)
measure("before (ADR-020 retrieval, no refill)")
R._ensure_own_chunks = orig_refill
for name, flag in (
    ("V1 always refill", False),
    ("V2 refill only when no policy chunk", True),
):
    R._REFILL_POLICY_FREE_ONLY = flag
    measure(name)
