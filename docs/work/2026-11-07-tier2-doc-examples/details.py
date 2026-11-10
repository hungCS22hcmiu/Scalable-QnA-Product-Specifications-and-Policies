"""Details for the Tier 2 doc examples (run of 7 Nov 2026). Read-only: the Redis corpus, Ollama
embeddings and the retriever. Writes nothing to Redis.

    python3 details.py lex sim        # gate words and question similarities (Redis + Ollama)
    cd rag && python3 ../docs/work/2026-11-07-tier2-doc-examples/details.py ret   # retrieval

`lex` reads the answers from runs/<label>.json, which ask.sh writes next to this file.
"""

import json
import math
import os
import re
import subprocess
import sys
import urllib.request

S = os.path.dirname(os.path.abspath(__file__))
# The 33 stopwords of gateway/internal/reuse/support.go (supportStopwords).
STOP = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if", "in", "into", "is", "it",
    "no", "not", "of", "on", "or", "such", "that", "the", "their", "then", "there", "these", "they",
    "this", "to", "was", "will", "with",
}  # fmt: skip


def toks(s):
    return re.findall(r"[a-z0-9]+", s.lower())


def content(s):
    return {t for t in toks(s) if len(t) >= 3 and t not in STOP}


def chunk_text(cid):
    out = subprocess.run(
        ["redis-cli", "HGET", f"corpus::{cid}", "text"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout


def run(label):
    """The saved response of one request: runs/<label>.json from a fresh ask.sh run, else the
    7 Nov 2026 run in evidence/responses.jsonl."""
    path = f"{S}/runs/{label}.json"
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    with open(f"{S}/evidence/responses.jsonl") as f:
        return next(r for r in map(json.loads, f) if r["label"] == label)


def lex(answer_label, evidence_ids, name):
    c = content(run(answer_label)["answer"])
    ev = set()
    for cid in evidence_ids:
        ev |= set(toks(chunk_text(cid)))
    found = sorted(c & ev)
    print(f"[{name}] answer={answer_label} content={len(c)} found={len(found)} "
          f"lex={len(found) / len(c):.4f}")  # fmt: skip
    print("   missing:", sorted(c - ev))


A_RET = [
    "product-electronics-b07zj7qg33#chunk-1",
    "policy-return-electronics#chunk-0",
    "policy-return-electronics#chunk-1",
    "policy-return-electronics#chunk-2",
    "policy-warranty-electronics#chunk-2",
]
A5_RET = ["product-electronics-b079jfb616#chunk-1", *A_RET[1:]]
B3_RET = [
    "product-electronics-b07zj7qg33#chunk-1",
    "policy-warranty-electronics#chunk-0",
    "policy-warranty-electronics#chunk-1",
    "policy-return-electronics#chunk-0",
]
B4_RET = ["product-electronics-b079jfb616#chunk-1", *B3_RET[1:]]
D_RET = [f"product-laptops-b07qvm5x8w#chunk-{i}" for i in range(3)]

Q = {
    "A1": "Can I get a full refund on these headphones 30 days after delivery?",
    "A3": "Is a full refund possible for these headphones 30 days after delivery?",
    "A4": "Can I get a full refund on this sofa 30 days after delivery?",
    "B1": "How long do I have to return these headphones?",
    "B2": "How long is the warranty on these headphones?",
    "B3": "What warranty period do these headphones come with?",
    "D1": "Which graphics card does this laptop have?",
    "D2": "What GPU is in this laptop?",
    "D3": "How much RAM does this laptop have?",
}

if "lex" in sys.argv:
    lex("A1", A_RET, "A3 judged A1's entry")
    lex("A1", A5_RET, "A5 judged A1's entry")
    lex("B2", B3_RET, "B3 judged B2's entry")
    lex("B2", B4_RET, "B4 judged B2's entry")
    lex("D1", D_RET, "D2 judged D1's entry")
    for cid in [*B3_RET, B4_RET[0]]:
        print("   soundcore in", cid, "soundcore" in toks(chunk_text(cid)))

if "sim" in sys.argv:
    body = {
        "model": "nomic-embed-text",
        "input": ["search_query: " + q for q in Q.values()],
    }
    req = urllib.request.Request(
        "http://localhost:11434/api/embed",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        embs = dict(zip(Q, json.load(r)["embeddings"], strict=True))

    def cos(a, b):
        x, y = embs[a], embs[b]
        dot = sum(i * j for i, j in zip(x, y, strict=True))
        return dot / math.sqrt(sum(i * i for i in x) * sum(j * j for j in y))

    pairs = [("A1", "A3"), ("A1", "A4"), ("A1", "B1"), ("A1", "B2"), ("B1", "B2"), ("B2", "B3"),
             ("A1", "B3"), ("D1", "D2"), ("D1", "D3"), ("D2", "D3")]  # fmt: skip
    for a, b in pairs:
        print(f"cos({a},{b}) = {cos(a, b):.4f}")

if "ret" in sys.argv:
    from rag import retrieve

    cases = [
        ("A1", "product-electronics-b07zj7qg33"),
        ("A4", "product-furniture-b019x98zxm"),
        ("B2", "product-electronics-b07zj7qg33"),
        ("D1", "product-laptops-b07qvm5x8w"),
    ]
    for label, pid in cases:
        for p in (None, pid):
            chunks, ep = retrieve.retrieve(Q[label], product_id=p)
            print(f"[{label}] product_id={p} epoch={ep}")
            for c in chunks:
                print(f"     {c.score:.4f}  {c.chunk_id}")
