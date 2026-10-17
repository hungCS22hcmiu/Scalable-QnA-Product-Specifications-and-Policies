"""Read-only preview for the manual Tier-2 demo: retrieval (as the gateway's Retrieve call does it,
with product scoping), the lane and namespace that reuse/lane.go would derive (default band
Lo = Hi = 0.20, MIXED off), and query-to-query cosine similarity (search_query: prefix, as
gateway/internal/embed does). Touches no cache key. Exploratory, not a measurement."""

import json
import math
import urllib.request

from rag import retrieve

P3, PRO, ANC, SOFA, LAP = (
    "product-headphones-03",
    "product-headphones-04",
    "product-headphones-01",
    "product-furniture-04",
    "product-laptops-01",
)

QUESTIONS = {
    "a1": (P3, "Which Bluetooth version do these earbuds use?"),
    "a4": (P3, "What version of Bluetooth do these earbuds have?"),
    "a4b": (P3, "What Bluetooth version do these earbuds support?"),
    "s1": (P3, "What is the battery life of these earbuds?"),
    "p4": (P3, "What battery life do these earbuds have?"),
    "g1": (P3, "How much do these earbuds weigh?"),
    "g2": (P3, "What is the weight of these earbuds?"),
    "aP": (PRO, "Which Bluetooth version do these earbuds use?"),
}

PAIRS = [
    ("a1", "a4"), ("a1", "a4b"), ("a1", "s1"), ("s1", "p4"), ("a1", "p4"), ("g1", "g2"),
    ("a1", "g1"), ("s1", "g1"), ("a1", "aP"),
]


def lane_and_ns(ids, product_id, lo=0.20, hi=0.20):
    if not ids:
        return "SPEC", "(zero chunks: no Tier-2 attempt)"
    frac = sum(i.startswith("policy-") for i in ids) / len(ids)
    if frac == 0:
        lane = "SPEC"
    elif frac == 1 or frac >= hi:
        lane = "POLICY"
    elif frac >= lo:
        lane = "MIXED"
    else:
        lane = "SPEC"
    doc = lambda p: next((i.split("#")[0] for i in ids if i.startswith(p)), "")
    if lane == "SPEC":
        ns = product_id or doc("product-")
    elif lane == "POLICY":
        ns = doc("policy-")
    else:
        ns = f"{product_id or doc('product-')}|{doc('policy-')}"
    return f"{lane} (policy {frac:.2f})", ns


def embed(text):
    body = json.dumps({"model": "nomic-embed-text", "input": ["search_query: " + text]}).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/embed", body, {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["embeddings"][0]


def cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


if __name__ == "__main__":
    vecs = {}
    for key, (pid, q) in QUESTIONS.items():
        chunks, _ = retrieve.retrieve(q, product_id=pid)
        ids = [c.chunk_id for c in chunks]
        lane, ns = lane_and_ns(ids, pid)
        print(f"{key:4} [{pid}] {q}\n     {lane}  ns={ns}\n     {ids}")
        vecs[key] = embed(q)
    print()
    for a, b in PAIRS:
        print(f"sim {a:4} ~ {b:4} = {cos(vecs[a], vecs[b]):.4f}")
