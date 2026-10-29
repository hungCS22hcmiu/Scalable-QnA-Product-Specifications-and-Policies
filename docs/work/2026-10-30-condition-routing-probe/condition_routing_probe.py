"""Does product-scoped retrieval put the RIGHT condition document first? v1 validation split. citable: no.

The policy lane's namespace is the document of the highest-ranked policy chunk, so this is exactly the
signal that separates an "opened" question from an "unopened" one.
"""

import json
import re

from rag import retrieve

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


def first_policy_doc(question, product_id):
    chunks, _ = retrieve.retrieve(question, product_id=product_id or None)
    for c in chunks:
        if c.chunk_id.startswith("policy-"):
            return c.chunk_id.split("#")[0]
    return None


with open("data/workload-v1-validation.json") as f:
    items = json.load(f)

# Part 1: the authored validation questions.
rows = []
for i in items:
    gold = [d for d in i["doc_ids"] if d in SPLIT]
    if not gold:
        continue
    gold = gold[0]
    word = SPLIT[gold]
    literal = re.search(rf"\b{word}\b", i["question"], re.I) is not None
    got = first_policy_doc(i["question"], i.get("product_id"))
    rows.append((gold, literal, got))

print("PART 1 - validation questions on a condition-split policy")
for lit in (True, False):
    sub = [r for r in rows if r[1] == lit]
    if sub:
        ok = sum(r[2] == r[0] for r in sub)
        print(
            f"  condition word {'present' if lit else 'absent '}: {ok}/{len(sub)} rank-1 policy doc correct"
        )
wrong = [r for r in rows if r[2] != r[0]]
print("  wrong cases (gold -> got):", sorted({(g, str(x)) for g, _, x in wrong})[:12])

# Part 2: synonym rewrites of real validation questions (authored here, not part of the workload).
SYN = {
    "unopened": ["still sealed", "never opened", "brand-new in its sealed box"],
    "opened": ["used", "unboxed", "already taken out of the box"],
    "renewed": ["refurbished", "pre-owned"],
    "new": ["brand-new", "factory-sealed"],
    "international": ["overseas", "imported"],
    "domestic": ["US", "local"],
}
print("\nPART 2 - synonym rewrites")
seen = set()
tot = ok = 0
for i in items:
    gold = [d for d in i["doc_ids"] if d in SPLIT]
    if not gold:
        continue
    gold = gold[0]
    word = SPLIT[gold]
    if (
        not re.search(rf"\b{word}\b", i["question"], re.I)
        or (gold, i["product_id"]) in seen
    ):
        continue
    seen.add((gold, i["product_id"]))
    for syn in SYN[word]:
        q = re.sub(rf"\b{word}\b", syn, i["question"], count=1, flags=re.I)
        got = first_policy_doc(q, i.get("product_id"))
        tot += 1
        ok += got == gold
        if got != gold:
            print(f"  WRONG {word!r}->{syn!r}: got {got}")
    if len(seen) >= 16:
        break
print(f"  synonym rewrites: {ok}/{tot} rank-1 policy doc correct")
