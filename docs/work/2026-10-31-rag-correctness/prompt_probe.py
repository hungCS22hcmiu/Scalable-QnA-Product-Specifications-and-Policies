"""Plan §3.1: the generator's prompt, measured on the validation split. citable: no.

Run from the repo root with Redis and Ollama up; no gateway is needed:
    python3 docs/work/2026-10-31-rag-correctness/prompt_probe.py

1. The pairs, fixed by the plan: every paraphrase with its cluster's seed (281), the seed asked first;
   every B-within probe with its pair_of (124), the pair_of asked first.
2. Each distinct first question: retrieve as the Answer RPC does, then one answer under each prompt.
   OLD is generate.py as it stands; NEW is the plan's candidate, sent through the same generate() call
   and settings. Appended to private/answers.jsonl, so a stopped run resumes where it stopped.
3. Each distinct second question: retrieve as the Retrieve RPC does (chunk IDs and texts).
4. The gateway's own gate code judges each pair under each arm (gateway/cmd/gateprobe).
5. The decision rule, fixed in the plan: adopt NEW only if the paraphrase pass rate rises by at least
   X = 15 points AND the B-within pass rate rises by at most Y = 5 points.

Question, answer and chunk text is Amazon-PQA, so it stays under evidence/private/ (gitignored). The
results and the summary beside it hold IDs and numbers only.
"""

import hashlib
import json
import math
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

from rag.retrieve import retrieve

from rag import config, generate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WORKLOAD = ROOT / "data" / "workload-v1-validation.json"
EVIDENCE = HERE / "evidence"
PRIVATE = EVIDENCE / "private" / "prompt-probe"
ANSWERS = PRIVATE / "answers.jsonl"
PAIRS = PRIVATE / "pairs.jsonl"
RESULTS = EVIDENCE / "prompt-probe-results.jsonl"
SUMMARY = EVIDENCE / "prompt-probe-summary.txt"

TAU = 0.85  # the gateway's REUSE_TAU default
X, Y = 15.0, 5.0  # the plan's decision rule, in percentage points

OLD_TEMPLATE = generate._PROMPT_TEMPLATE
# The plan's candidate. Its line breaks in plan.md are the page's wrapping: the instruction is one
# paragraph, as in OLD.
NEW_TEMPLATE = (
    "Answer the question using ONLY the context below. "
    "Answer directly in one or two sentences, using the words and numbers of the context. "
    "Do not mention the context or say where the information is. "
    "If the answer is not contained in the context, say you don't know.\n\n"
    "Context:\n{context}\n\nQuestion: {query}\nAnswer:"
)
ARMS = {"old": OLD_TEMPLATE, "new": NEW_TEMPLATE}

# Reported beside the rule, never part of it. A heuristic: it also counts a "No" written as "the context
# does not mention ...", so the per-answer flags are kept for a read.
DONT_KNOW = re.compile(
    r"\b(?:don[’']t|do not) know\b"
    r"|\bnot (?:contained|mentioned|specified|stated|provided|given|found|available|included|listed)"
    r" in the (?:provided )?(?:context|text)\b"
    r"|\b(?:context|text) (?:does not|doesn[’']t|did not) "
    r"(?:contain|mention|specify|state|provide|include|say|list|give)\b",
    re.IGNORECASE,
)


def pressure():
    return subprocess.run(
        ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()[:12]


def build_pairs(items):
    seeds = {i["cluster_id"]: i for i in items if i["role"] == "seed"}
    by_id = {i["qa_id"]: i for i in items}
    pairs = [
        ("paraphrase", seeds[i["cluster_id"]], i)
        for i in items
        if i["role"] == "paraphrase"
    ]
    pairs += [
        ("trap", by_id[i["pair_of"]], i) for i in items if i["stratum"] == "B-within"
    ]
    counts = Counter(k for k, _, _ in pairs)
    if counts != Counter(paraphrase=281, trap=124):
        raise SystemExit(
            f"FAIL — the plan fixes 281 paraphrase and 124 B-within pairs, found {dict(counts)}"
        )
    return pairs


def generate_with(template, query, chunks):
    """generate() itself, with only the prompt template swapped for this one call."""
    saved = generate._PROMPT_TEMPLATE
    generate._PROMPT_TEMPLATE = template
    try:
        return generate.generate(query, chunks)
    finally:
        generate._PROMPT_TEMPLATE = saved


def answer_firsts(firsts):
    done = {}
    if ANSWERS.exists():
        for line in ANSWERS.read_text().splitlines():
            row = json.loads(line)
            done[row["qa_id"]] = row
    todo = [q for q in firsts if q["qa_id"] not in done]
    print(
        f"first questions: {len(firsts)}, already answered {len(done)}, to answer {len(todo)}"
    )
    with ANSWERS.open("a") as f:
        for n, q in enumerate(todo, 1):
            before = pressure()
            chunks, _ = retrieve(
                q["question"], top_k=config.TOP_K, product_id=q["product_id"] or ""
            )
            row = {
                "qa_id": q["qa_id"],
                "answerable": q["answerable"],
                "chunk_ids": [c.chunk_id for c in chunks],
                "answers": {
                    arm: generate_with(t, q["question"], chunks)
                    for arm, t in ARMS.items()
                },
            }
            row["pressure"] = [before, pressure()]
            f.write(json.dumps(row) + "\n")
            f.flush()
            done[q["qa_id"]] = row
            if n % 10 == 0 or n == len(todo):
                print(
                    f"  {n}/{len(todo)}  pressure {row['pressure']}  {time.strftime('%H:%M:%S')}",
                    flush=True,
                )
    return done


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def summarise(results, answers, pairs_n):
    out = [
        "Plan §3.1 — the generator's prompt, validation split. citable: no.",
        f"Run {time.strftime('%Y-%m-%d %H:%M')}; tau {TAU}; gate on, both arms; MIXED off; one sample per arm.",
        f"Templates: old {sha(OLD_TEMPLATE)}, new {sha(NEW_TEMPLATE)} (sha256, first 12).",
        f"Pairs judged {len(results)} of {pairs_n}.",
        "",
    ]
    rise = {}
    for kind in ("paraphrase", "trap"):
        rows = [r for r in results if r["kind"] == kind]
        n = len(rows)
        rates = {}
        for arm in ARMS:
            k = sum(r["arms"][arm]["served"] for r in rows)
            lo, hi = wilson(k, n)
            rates[arm] = 100 * k / n
            causes = Counter(r["arms"][arm]["cause"] for r in rows)
            ns_sup = sum(
                r["entry_ns"] != ""
                and r["entry_ns"] == r["query_ns"]
                and r["arms"][arm]["support_admits"]
                for r in rows
            )
            out.append(
                f"{kind:<10} {arm}: pass {k}/{n} = {rates[arm]:.1f} % (Wilson 95 % {100 * lo:.1f}–{100 * hi:.1f})"
                f"  causes {dict(sorted(causes.items()))}  namespace+support at any tau {ns_sup}/{n}"
            )
        rise[kind] = rates["new"] - rates["old"]
        out.append(f"{kind:<10} rise: {rise[kind]:+.1f} points")
        out.append("")
    adopt = rise["paraphrase"] >= X and rise["trap"] <= Y
    out.append(
        f"Rule: paraphrase rise {rise['paraphrase']:+.1f} >= {X:.0f} is {rise['paraphrase'] >= X}; "
        f"trap rise {rise['trap']:+.1f} <= {Y:.0f} is {rise['trap'] <= Y}. "
        f"Decision: {'ADOPT the candidate' if adopt else 'KEEP the old prompt'}."
    )
    out.append("")
    answerable = [a for a in answers.values() if a["answerable"]]
    for arm in ARMS:
        k = sum(bool(DONT_KNOW.search(a["answers"][arm])) for a in answerable)
        words = sorted(len(a["answers"][arm].split()) for a in answers.values())
        out.append(
            f'Beside the rule, {arm}: "don\'t know" on answerable first questions {k}/{len(answerable)}'
            f" ({100 * k / len(answerable):.1f} %); answer length median {words[len(words) // 2]} words."
        )
    readings = Counter(p for a in answers.values() for p in a["pressure"])
    out.append(
        f"Pressure readings over the generation: {dict(sorted(readings.items()))}."
    )
    return "\n".join(out)


def main():
    for p in (RESULTS, SUMMARY):
        if p.exists():
            raise SystemExit(
                f"FAIL — {p} exists; a finished run is not overwritten. Move it to re-judge."
            )
    PRIVATE.mkdir(parents=True, exist_ok=True)
    print(f"pressure at start: {pressure()}")
    pairs = build_pairs(json.loads(WORKLOAD.read_text()))

    firsts = {q["qa_id"]: q for _, q, _ in pairs}
    answers = answer_firsts(sorted(firsts.values(), key=lambda q: q["qa_id"]))

    seconds = {q["qa_id"]: q for _, _, q in pairs}
    evidence = {}
    for q in seconds.values():
        chunks, _ = retrieve(
            q["question"], top_k=config.TOP_K, product_id=q["product_id"] or ""
        )
        evidence[q["qa_id"]] = chunks
    print(f"second questions retrieved: {len(evidence)}")

    with PAIRS.open("w") as f:
        for kind, q1, q2 in pairs:
            a, chunks = answers[q1["qa_id"]], evidence[q2["qa_id"]]
            row = {
                "kind": kind,
                "first_id": q1["qa_id"],
                "second_id": q2["qa_id"],
                "q1": q1["question"],
                "pid1": q1["product_id"] or "",
                "chunks1": a["chunk_ids"],
                "answers": a["answers"],
                "q2": q2["question"],
                "pid2": q2["product_id"] or "",
                "chunks2": [c.chunk_id for c in chunks],
                "texts2": [c.text for c in chunks],
            }
            f.write(json.dumps(row) + "\n")

    subprocess.run(
        [
            "go",
            "run",
            "./cmd/gateprobe",
            "-in",
            str(PAIRS),
            "-out",
            str(RESULTS),
            "-tau",
            str(TAU),
        ],
        cwd=ROOT / "gateway",
        check=True,
    )
    results = [json.loads(line) for line in RESULTS.read_text().splitlines()]
    text = summarise(results, answers, len(pairs))
    SUMMARY.write_text(text + "\n")
    print("\n" + text)
    print(f"\npressure at end: {pressure()}")


if __name__ == "__main__":
    main()
