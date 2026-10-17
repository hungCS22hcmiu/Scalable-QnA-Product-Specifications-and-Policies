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
    "s1": (P3, "What is the battery life of these earbuds?"),
    "p1": (P3, "What's the battery life of these earbuds?"),
    "p2": (P3, "What is the battery life on these earbuds?"),
    "p3": (P3, "Tell me the battery life of these earbuds."),
    "p4": (P3, "What battery life do these earbuds have?"),
    "p5": (P3, "How good is the battery life of these earbuds?"),
    "p6": (P3, "What is the battery life of the earbuds?"),
    "n1": (P3, "Do these earbuds have noise cancelling?"),
    "n2": (P3, "Do these earbuds have noise cancellation?"),
    "n3": (P3, "Do these earbuds have active noise cancelling?"),
    "r1": (P3, "Can I return these headphones after 30 days?"),
    "r1a": (ANC, "Can I return these headphones after 30 days?"),
    "r3": (SOFA, "Can I return this after 30 days?"),
    "w4": (LAP, "How long is the warranty on this?"),
    "w5": (P3, "How long is the warranty on these?"),
    "w6": (LAP, "How long is the warranty on this laptop?"),
    "w7": (P3, "How long is the warranty on these headphones?"),
    "b1": (P3, "How long does the battery last?"),
    "b2": (PRO, "How long does the battery last?"),
}

PAIRS = [
    ("s1", "p1"), ("s1", "p2"), ("s1", "p3"), ("s1", "p4"), ("s1", "p5"), ("s1", "p6"),
    ("n1", "n2"), ("n1", "n3"), ("r1", "r1a"), ("r1", "r3"),
    ("w4", "w5"), ("w4", "w6"), ("w4", "w7"), ("w5", "w6"), ("w6", "w7"), ("w5", "w7"),
    ("b1", "w5"), ("b1", "w7"), ("b1", "w4"), ("b1", "w6"), ("b1", "b2"),
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
