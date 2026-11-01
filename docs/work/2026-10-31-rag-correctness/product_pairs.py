"""Rescue (trap) and false-miss (paraphrase) pairs on one product, against the running demo gateway.

citable: no. Questions are authored here from the product's chunks, plus the one validation trap pair;
the test split is not used.
"""

import json
import re
import urllib.request

from rag.retrieve import fetch_by_ids

P = "product-electronics-b07b63r768"
OTHER_HEADPHONES = "product-electronics-b07r8pr5yz"
FURNITURE = "product-furniture-b000as7sy8"

STOP = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "if",
    "in",
    "into",
    "is",
    "it",
    "no",
    "not",
    "of",
    "on",
    "or",
    "such",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "they",
    "this",
    "to",
    "was",
    "will",
    "with",
}

# (label, pid of Q1, Q1, pid of Q2, Q2, what a correct system does)
RESCUE = [
    (
        "T1 return vs warranty (validation pair)",
        P,
        "What is the return policy for the ismtstore Noise Cancelling Headphones?",
        P,
        "For how long does the company give the warranty on the ismtstore Noise Cancelling Headphones?",
        "different policy document",
    ),
    (
        "T2 battery: Bluetooth only vs ANC on",
        P,
        "How many hours does the battery last with Bluetooth only?",
        P,
        "How many hours does the battery last with noise cancelling and Bluetooth on?",
        "15-20 h vs 12 h",
    ),
    (
        "T3 charge time vs battery life",
        P,
        "How long does it take to fully charge?",
        P,
        "How long does the battery last?",
        "2-3 h vs 15-20 h",
    ),
    (
        "T4 mic exists vs mic in wired mode",
        P,
        "Does it have a built-in mic?",
        P,
        "Does the built-in mic work in wired mode?",
        "Yes vs No",
    ),
    (
        "T5 blocks traffic vs blocks voices",
        P,
        "Does the noise cancelling block city traffic noise?",
        P,
        "Does the noise cancelling block human voices?",
        "Yes vs No",
    ),
    (
        "T6 standby vs playtime",
        P,
        "What is the standby time?",
        P,
        "What is the play time?",
        "400+ h vs 15-20 h",
    ),
    (
        "T7 same question, other headphones",
        OTHER_HEADPHONES,
        "How long does the battery last?",
        P,
        "How long does the battery last?",
        "different product",
    ),
    (
        "T8 same policy question, other category",
        FURNITURE,
        "Can I return this if I opened it?",
        P,
        "Can I return this if I opened it?",
        "furniture vs electronics policy",
    ),
]

PARAPHRASES = [
    (
        "P1 ANC",
        "Does it have active noise cancellation?",
        "Do these headphones support ANC?",
    ),
    (
        "P2 wired",
        "Can I use these headphones with a cable?",
        "Do they work in wired mode with an aux cable?",
    ),
    (
        "P3 range",
        "What is the Bluetooth range?",
        "How far can I be from my phone with Bluetooth?",
    ),
    (
        "P4 charge time",
        "What is the charging time?",
        "How many hours does a full charge take?",
    ),
    (
        "P5 foldable",
        "Are these headphones foldable?",
        "Can the headphones fold for travel?",
    ),
    ("P6 bag", "Does it come with a carrying bag?", "Is a carrying case included?"),
    (
        "P7 pairing",
        "How do I pair these headphones?",
        "How can I connect them to my phone via Bluetooth?",
    ),
    (
        "P8 battery capacity",
        "What is the battery capacity?",
        "How big is the battery in mAh?",
    ),
]


def toks(s):
    return re.findall(r"[a-z0-9]+", s.lower())


def s_lex(answer, chunk_ids):
    content = {t for t in toks(answer) if len(t) >= 3 and t not in STOP}
    chunks, _ = fetch_by_ids(chunk_ids)
    ev = set(toks("\n".join(c.text for c in chunks)))
    return (sum(t in ev for t in content) / len(content)) if content else 0.0


def ask(q, pid):
    body = json.dumps({"question": q, "product_id": pid}).encode()
    req = urllib.request.Request(
        "http://localhost:8080/ask",
        data=body,
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def short(s, n=110):
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def run(label, p1, q1, p2, q2, note):
    a1, a2 = ask(q1, p1), ask(q2, p2)
    sim = a2.get("similarity")
    sim_s = f"{sim:.3f}" if isinstance(sim, (int, float)) else "-"
    sl = s_lex(a1["answer"], a2["sources"])
    print(f"\n{label}  [{note}]")
    print(f"  Q1 {q1!r} -> {a1['cache']}  ns={a1.get('namespace')}")
    print(f"     A1: {short(a1['answer'])}")
    print(
        f"  Q2 {q2!r} -> {a2['cache']}  sim={sim_s}  S_lex(A1 vs Q2 evidence)={sl:.2f}  ns={a2.get('namespace')}"
    )
    print(
        f"     A2: {short(a2['answer'])}   sources={[c.split('#')[1] if '#' in c and c.startswith(P) else c for c in a2['sources']]}"
    )


print(
    "=== RESCUE: traps a similarity-only cache would get wrong (a correct system answers Q2 with MISS)"
)
for row in RESCUE:
    run(*row)
print(
    "\n=== FALSE-MISS candidates: true paraphrases (a correct system answers Q2 with TIER2_HIT)"
)
for label, q1, q2 in PARAPHRASES:
    run(label, P, q1, P, q2, "should reuse")
