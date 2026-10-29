"""F-K evidence: containment overlap of product-scoped retrievals, by pair kind, on the v1 VALIDATION split.

overlap(q, e) = |retrieved(q) ∩ retrieved(e)| / |retrieved(e)|, as gateway/internal/reuse/rule.go Overlap
(the entry e's retrieval stands in for its recorded sources). Each query is retrieved with its own
product_id, as rag.server does. citable: no. Writes one JSON line per pair, then a summary.
"""

import json
import statistics as st
import sys
from collections import defaultdict

from rag import retrieve

out_path = sys.argv[1]
items = json.load(open("data/workload-v1-validation.json"))
by_id = {i["qa_id"]: i for i in items}
seed_of_cluster = {i["cluster_id"]: i["qa_id"] for i in items if i["role"] == "seed"}

pairs = []  # (kind, q_id, e_id)
for i in items:
    if i["role"] == "paraphrase" and i["cluster_id"] in seed_of_cluster:
        pairs.append(
            (
                "A-paraphrase (should reuse)",
                i["qa_id"],
                seed_of_cluster[i["cluster_id"]],
            )
        )
    if i.get("pair_of") and i["pair_of"] in by_id:
        pairs.append(
            (f"{i['stratum']} probe (should refuse)", i["qa_id"], i["pair_of"])
        )

cache = {}


def ids(qa_id):
    if qa_id not in cache:
        it = by_id[qa_id]
        chunks, _ = retrieve.retrieve(
            it["question"], product_id=it.get("product_id") or None
        )
        cache[qa_id] = [c.chunk_id for c in chunks]
    return cache[qa_id]


def overlap(retrieved, sources):
    src = set(sources)
    if not src:
        return 0.0
    return len(set(retrieved) & src) / len(src)


rows = defaultdict(list)
with open(out_path, "w") as f:
    for n, (kind, q, e) in enumerate(pairs, 1):
        o = overlap(ids(q), ids(e))
        same_product = by_id[q].get("product_id") == by_id[e].get("product_id")
        rows[kind].append(o)
        f.write(
            json.dumps(
                {
                    "kind": kind,
                    "q": q,
                    "e": e,
                    "same_product": same_product,
                    "overlap": o,
                }
            )
            + "\n"
        )
        if n % 50 == 0:
            print(f"{n}/{len(pairs)} pairs", file=sys.stderr, flush=True)

print(f"pairs: {len(pairs)}, distinct queries retrieved: {len(cache)}")
for kind in sorted(rows):
    v = rows[kind]
    print(
        f"{kind:34s} n={len(v):3d}  mean={st.mean(v):.3f}  median={st.median(v):.2f}  "
        f"=1.0: {sum(x == 1.0 for x in v) / len(v):.0%}  >=0.6: {sum(x >= 0.6 for x in v) / len(v):.0%}  "
        f"<=0.2: {sum(x <= 0.2 for x in v) / len(v):.0%}"
    )
