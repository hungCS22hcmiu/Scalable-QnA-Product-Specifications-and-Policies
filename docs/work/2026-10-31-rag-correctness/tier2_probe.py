"""Tier-2 probe against the RUNNING demo gateway (make dev). citable: no.

Part A: paraphrase pairs on one product. Ask Q1, then Q2; report Q2's outcome and S_lex of Q1's answer
against Q2's evidence (the support gate's lexical arm, re-implemented from reuse/support.go).
Part B: self-support. For validation queries, S_lex of each fresh MISS answer against ITS OWN sources:
the share >= 0.6 is the share of answers a same-evidence paraphrase could ever reuse with the gate on.
"""

import json
import random
import re
import sys
import urllib.request

from rag.retrieve import fetch_by_ids

STOP = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if", "in", "into", "is", "it", "no",
    "not", "of", "on", "or", "such", "that", "the", "their", "then", "there", "these", "they", "this",
    "to", "was", "will", "with",
}


def toks(s):
    return re.findall(r"[a-z0-9]+", s.lower())


def s_lex(answer, chunk_ids):
    content = {t for t in toks(answer) if len(t) >= 3 and t not in STOP}
    chunks, _ = fetch_by_ids(chunk_ids)
    ev = set(toks("\n".join(c.text for c in chunks)))
    if not content:
        return 0.0, [], []
    hit = sorted(t for t in content if t in ev)
    return len(hit) / len(content), hit, sorted(content - set(hit))


def ask(q, pid):
    body = json.dumps({"question": q, "product_id": pid}).encode()
    req = urllib.request.Request(
        "http://localhost:8080/ask",
        data=body,
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


PID = "product-electronics-b07r8pr5yz"
PAIRS = [
    (
        "What is the Bluetooth signal range?",
        "How far does the Bluetooth connection reach?",
    ),
    (
        "How long does a full charge take?",
        "How many hours does it take to fully charge?",
    ),
    ("Can I use them with an audio cable?", "Do they have a wired mode with a cable?"),
    ("What comes in the box?", "What is included in the package?"),
    ("What is the frequency range?", "What frequency range do they cover?"),
    ("How do I switch the EQ mode?", "How can I change the EQ mode?"),
    ("What is the charging voltage?", "Which charging voltage does it use?"),
    ("Are the earcups swiveling?", "Do the earcups swivel?"),
]

if "B" not in sys.argv[1:]:
    print("PART A - paraphrase pairs on", PID)
    for q1, q2 in PAIRS:
        a1 = ask(q1, PID)
        a2 = ask(q2, PID)
        sim = a2.get("similarity")
        sim_s = f"{sim:.3f}" if isinstance(sim, (int, float)) else "-"
        s, hit, miss = s_lex(a1["answer"], a2["sources"])
        print(f"\nQ1 {q1!r} -> {a1['cache']}")
        print(f"   A1: {a1['answer'][:160]!r}")
        print(f"Q2 {q2!r} -> {a2['cache']}  sim={sim_s}")
        print(f"   S_lex(A1 vs Q2 evidence) = {s:.2f}   missing: {miss}")

if "A" not in sys.argv[1:]:
    print("\nPART B - self-support of fresh MISS answers, validation queries")
    with open("data/workload-v1-validation.json") as f:
        items = json.load(f)
    random.seed(7)
    sample = random.sample(
        [i for i in items if i.get("product_id") and i.get("answerable")], 30
    )
    rows = []
    for i in sample:
        a = ask(i["question"], i["product_id"])
        if a["cache"] != "MISS" or not a.get("sources"):
            continue
        s, _, miss = s_lex(a["answer"], a["sources"])
        rows.append((s, a["lane"], miss[:8], len(a["answer"])))
    passed = sum(1 for r in rows if r[0] >= 0.6)
    print(
        f"  MISS answers scored: {len(rows)}   S_lex >= 0.6 on own evidence: {passed} ({passed / max(1, len(rows)):.0%})"
    )
    for lane in sorted({r[1] for r in rows}):
        sub = [r for r in rows if r[1] == lane]
        p = sum(1 for r in sub if r[0] >= 0.6)
        print(f"  lane {lane:<7} {p}/{len(sub)} pass")
    rows.sort()
    print("  distribution:", [round(r[0], 2) for r in rows])
    words = {}
    for r in rows:
        for w in r[2]:
            words[w] = words.get(w, 0) + 1
    print(
        "  most common missing tokens:", sorted(words.items(), key=lambda x: -x[1])[:15]
    )
