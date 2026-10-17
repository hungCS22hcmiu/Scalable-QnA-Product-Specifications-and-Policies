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
    "q1": (P3, "How long does the battery last?"),
    "q1b": (P3, "What is the battery life of the EarBuds Pop 3?"),
    "q3": (P3, "What is the battery life of these earbuds?"),
    "q3b": (P3, "How many hours of battery do I get?"),
    "q3c": (P3, "How long will the battery last on a full charge?"),
    "q5": (P3, "How much do they weigh?"),
    "q5b": (P3, "Do they have noise cancelling?"),
    "q6": (PRO, "How long does the battery last?"),
    "q6b": (ANC, "How long does the battery last?"),
    "q7": (P3, "Can I return these after 30 days?"),
    "q7b": (P3, "Can I get a full refund if I return them within 30 days?"),
    "q8": (P3, "Is it possible to return them 30 days after delivery?"),
    "q8b": (P3, "Am I still allowed to send these back after 30 days?"),
    "q9": (PRO, "Can I return these after 30 days?"),
    "q9b": (ANC, "Can I return these after 30 days?"),
    "q10": (P3, "How long is the warranty on these?"),
    "q11": (SOFA, "Can I return this after 30 days?"),
    "q12": (P3, "Who pays for return shipping if I change my mind?"),
    "w1": (LAP, "How long is the warranty on this laptop?"),
    "w2": (P3, "How long is the warranty on these headphones?"),
    "w3": (ANC, "How long is the warranty on these headphones?"),
    "m1": (P3, "How long is the warranty on these, and what is their battery life?"),
}

PAIRS = [
    ("q1", "q1b"), ("q1", "q3"), ("q1", "q3b"), ("q1", "q3c"), ("q1", "q5"), ("q1", "q5b"),
    ("q1", "q6"), ("q7", "q7b"), ("q7", "q8"), ("q7", "q8b"), ("q7", "q9"), ("q7", "q10"),
    ("q7", "q11"), ("q7", "q12"), ("w1", "w2"), ("w1", "w3"), ("w2", "w3"), ("q10", "w2"),
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
