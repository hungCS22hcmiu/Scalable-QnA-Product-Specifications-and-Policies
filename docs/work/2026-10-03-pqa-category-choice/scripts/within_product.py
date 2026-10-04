"""Within-product paraphrase structure, on the pool v1 would draw from. Scratch, lexical only."""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pqa_category_probe as P  # noqa: E402  same filters and near-duplicate band

RAW = Path("/Users/hung/Desktop/Sem1/thesis/data/raw/pqa")
LEAVES = [("unlocked_cell_phones", "phones"), ("traditional_laptops", "laptops"),
          ("led_&_lcd_tvs", "electronics"), ("over-ear_headphones", "electronics"),
          ("chairs", "furniture"), ("home_office_desks", "furniture")]


def clusters(qs):
    """Union-find over pairs that are exact repeats (same content tokens) or lexical near-duplicates."""
    toks = [P.content_tokens(q) for q in qs]
    parent = list(range(len(qs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    exact = near = 0
    for i in range(len(qs)):
        for j in range(i + 1, len(qs)):
            if not toks[i] or not toks[j]:
                continue
            if toks[i] == toks[j]:
                exact += 1
            elif P.ND_LO <= P.jaccard(toks[i], toks[j]) <= P.ND_HI:
                near += 1
            else:
                continue
            parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(len(qs)):
        groups[find(i)].append(qs[i])
    return list(groups.values()), exact, near


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * (len(xs) - 1)))]


print(f"{'leaf':22}{'pool':>6}{'q/prod':>8} | {'in-cluster %':>27} | {'redundancy %':>27} | {'largest':>8}")
print(f"{'':22}{'':>6}{'median':>8} | {'median':>9}{'p75':>9}{'p90':>9} | {'median':>9}{'p75':>9}{'p90':>9} | {'median':>8}")
examples = {}
for leaf, dept in LEAVES:
    rows, first = defaultdict(list), {}
    for line in open(RAW / f"amazon_pqa_{leaf}.json", "rb"):
        r = json.loads(line)
        q = (r.get("question_text") or "").strip()
        if r.get("asin") and q and not (P.DYNAMIC_Q.search(q) or P.CARRIER_Q.search(q)):
            rows[r["asin"]].append(q)
            first.setdefault(r["asin"], r)
    stats = []
    for a, qs in rows.items():
        if not P.CAP_LO <= len(qs) <= P.CAP_HI:
            continue
        if sum(1 for i in range(1, 6) if (first[a].get(f"bullet_point{i}") or "").strip()) < 3:
            continue
        g, exact, near = clusters(qs)
        if exact + near == 0:
            continue                      # the selection rule requires >= 1 pair
        n = len(qs)
        inc = sum(len(x) for x in g if len(x) > 1) / n
        red = 1 - len(g) / n
        stats.append((a, n, inc, red, max(len(x) for x in g), g))
    ns = [s[1] for s in stats]
    inc = [100 * s[2] for s in stats]
    red = [100 * s[3] for s in stats]
    big = [s[4] for s in stats]
    print(f"{leaf:22}{len(stats):>6}{statistics.median(ns):>8} | {statistics.median(inc):>9.1f}{pct(inc,.75):>9.1f}{pct(inc,.9):>9.1f}"
          f" | {statistics.median(red):>9.1f}{pct(red,.75):>9.1f}{pct(red,.9):>9.1f} | {statistics.median(big):>8}")
    # the product at the median redundancy, as a concrete example
    stats.sort(key=lambda s: (s[3], s[0]))
    examples[leaf] = stats[int(0.9 * (len(stats) - 1))]
    hi = [x for x in stats if x[3] >= 0.15]
    print(f"{'':22}products with redundancy >= 15 %: {len(hi)}  (median q/prod {statistics.median(x[1] for x in hi) if hi else 0})")

for leaf in ["unlocked_cell_phones", "chairs"]:
    a, n, inc, red, big, g = examples[leaf]
    print(f"\n=== p90-redundancy example, {leaf}: {a}, {n} questions, {len(g)} clusters, "
          f"in-cluster {100*inc:.0f}%, redundancy {100*red:.0f}%")
    for x in sorted(g, key=len, reverse=True):
        if len(x) > 1:
            print("  cluster:", " | ".join(q[:55] for q in x))
