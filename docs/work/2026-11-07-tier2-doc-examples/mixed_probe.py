"""Read-only: which candidate questions land in the MIXED lane (band [0.20, 0.60)) with a product_id."""

from rag import retrieve

H1 = "product-electronics-b07zj7qg33"
H2 = "product-electronics-b079jfb616"
LAP = "product-laptops-b07qvm5x8w"
CASES = [
    (
        H1,
        "How long does the battery of these headphones last, and how long is the warranty?",
    ),
    (
        H1,
        "What is the battery life of these headphones, and what warranty do they come with?",
    ),
    (
        H2,
        "How long does the battery of these headphones last, and how long is the warranty?",
    ),
    (
        H1,
        "Do these headphones have noise cancelling, and can I return them within 30 days?",
    ),
    (
        H1,
        "How long is the warranty on these headphones, and do they support Bluetooth 5.0?",
    ),
    (LAP, "How much RAM does this laptop have, and how long is its warranty?"),
    (
        LAP,
        "What GPU does this laptop have, and how many days do I have to return it if it is new?",
    ),
]


def lane(ids):
    pol = [i for i in ids if i.startswith("policy-")]
    f = len(pol) / len(ids)
    if f == 0:
        return f, "SPEC"
    if f == 1 or f >= 0.60:
        return f, "POLICY"
    return f, "MIXED"


for pid, q in CASES:
    chunks, _ = retrieve.retrieve(q, product_id=pid)
    ids = [c.chunk_id for c in chunks]
    f, ln = lane(ids)
    top_pol = next((i.split("#")[0] for i in ids if i.startswith("policy-")), "")
    top_prod = pid
    ns = {"SPEC": top_prod, "POLICY": top_pol, "MIXED": f"{top_prod}|{top_pol}"}[ln]
    print(f"{ln:6} f={f:.2f} ns={ns}\n   Q: {q}\n   {ids}")
