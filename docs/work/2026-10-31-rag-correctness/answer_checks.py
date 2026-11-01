"""Plan §1.5: the five cases of §1.2, each asked once, against the RUNNING demo gateway (make dev). citable: no.

A repeated question is a Tier-1 hit, so each of the three rounds starts cold: stop the gateway,
`make cache-reset`, restart it, then run this from the repo root.
"""

import json
import subprocess
import urllib.request

CASES = [
    ("product-electronics-b07r8pr5yz", "What comes in the box?", "the box list"),
    (
        "product-electronics-b07r8pr5yz",
        "How long does a full charge take?",
        "1.5-2 hours",
    ),
    ("product-electronics-b07b63r768", "Are these headphones foldable?", "foldable"),
    ("product-electronics-b07b63r768", "What is the standby time?", "400 hours"),
    (
        "product-electronics-b07b63r768",
        "Is a carrying case included?",
        "the carrying bag",
    ),
]


def pressure():
    return subprocess.run(
        ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def ask(q, pid):
    body = json.dumps({"question": q, "product_id": pid}).encode()
    req = urllib.request.Request(
        "http://localhost:8080/ask",
        data=body,
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


print(f"pressure before: {pressure()}")
for pid, q, fact in CASES:
    a = ask(q, pid)
    srcs = [
        s.split("#", 1)[1] if s.startswith(pid + "#") else s
        for s in a.get("sources", [])
    ]
    print(f"\n{pid}  {q!r}  [must state: {fact}]")
    print(f"  -> {a['cache']}  lane={a.get('lane')}  sources={srcs}")
    print(f"  answer: {' '.join(a['answer'].split())}")
print(f"\npressure after: {pressure()}")
