"""Which store-policy topics does the 3.2 question pool ask about, beyond returns and warranty?

Counts only on stdout: no question text, no asin. Reads the pool only through
select_pqa.iter_selection (ADR-011). Each topic is a keyword pattern, so a count is an UPPER BOUND
("deliver" also matches "delivers great sound"). For precision, a seeded sample of each topic is
written to the gitignored data/v1-draft/audit/policy-scope-sample.csv for the author to mark;
nothing from it is printed.

    python3 docs/work/2026-10-20-policy-documents/evidence/policy_scope_probe.py
"""

import csv
import hashlib
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "experiments" / "scripts"))
import select_pqa  # noqa: E402

TOPICS = {
    "shipping / delivery": r"\b(ship|ships|shipped|shipping|deliver|delivery|delivered|arrive|arrives|arrival)\b",
    "ships abroad / customs": r"\b(ship|ships|shipping|deliver|delivery)\b.*\b(canada|uk|europe|australia|india|mexico|international|overseas|abroad|outside)\b|\bcustoms\b",
    "exchange": r"\bexchang(e|ed|es|ing)\b",
    "installation / assembly service": r"\b(install|installation|installed|installer|assembly|assemble|assembled|set ?up)\b",
    "cancel an order": r"\bcancel(led|ed|ing|lation)?\b",
    "payment / financing": r"\b(financing|finance|installments?|paypal|credit card|pay pal|layaway)\b",
    "protection plan / insurance": r"\b(protection plan|insurance|squaretrade|asurion|care ?pack|extended)\b",
    "condition: new / used / genuine": r"\b(brand new|used|refurbished|renewed|open box|genuine|authentic|original box|counterfeit|fake)\b",
    "seller / sold by": r"\b(seller|sold by|fulfilled by|third party)\b",
    "gift / gift receipt": r"\bgift\b",
}
PATTERNS = {t: re.compile(p, re.IGNORECASE) for t, p in TOPICS.items()}
SAMPLE_PER_TOPIC = 10
SEED = "v1-item-3.3:policy-scope"
SAMPLE_PATH = select_pqa.DRAFT_DIR / "audit" / "policy-scope-sample.csv"


def main() -> int:
    questions = [
        item
        for kind, item in select_pqa.iter_selection(select_pqa.SELECTION_PATH, select_pqa.DRAFT_DIR)
        if kind == "question"
    ]
    by_topic: dict[str, Counter] = defaultdict(Counter)
    hits: dict[str, list[dict]] = defaultdict(list)
    any_topic = Counter()
    for q in questions:
        text = str(q.get("question_text", ""))
        matched = [t for t, rx in PATTERNS.items() if rx.search(text)]
        for t in matched:
            by_topic[t][q["department"]] += 1
            by_topic[t]["tag=" + q["tag"]] += 1
            hits[t].append(q)
        if matched and q["tag"] != "policy":
            any_topic[q["department"]] += 1

    departments = sorted({q["department"] for q in questions})
    print(f"{len(questions)} pool questions (read through select_pqa.iter_selection); counts are UPPER BOUNDS\n")
    print(f"  {'topic':<34}" + "".join(f"{d:>12}" for d in departments) + f"{'total':>8}{'tag=policy':>12}")
    for t in TOPICS:
        c = by_topic[t]
        total = sum(c[d] for d in departments)
        print(f"  {t:<34}" + "".join(f"{c[d]:>12}" for d in departments) + f"{total:>8}{c['tag=policy']:>12}")
    print(f"\n  questions NOT tagged policy that hit any topic: "
          + ", ".join(f"{d} {any_topic[d]}" for d in departments) + f"; total {sum(any_topic.values())}")

    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SAMPLE_PATH.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["topic", "department", "tag", "question_text", "is_store_policy (y/n)", "stable (y/n)"])
        for t in TOPICS:
            ranked = sorted(hits[t], key=lambda q: hashlib.sha256(f"{SEED}:{t}:{q['question_id']}".encode()).hexdigest())
            for q in ranked[:SAMPLE_PER_TOPIC]:
                w.writerow([t, q["department"], q["tag"], q["question_text"], "", ""])
    print(f"\n  sample for the author ({SAMPLE_PER_TOPIC} per topic, seeded): data/v1-draft/audit/{SAMPLE_PATH.name} (gitignored)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
