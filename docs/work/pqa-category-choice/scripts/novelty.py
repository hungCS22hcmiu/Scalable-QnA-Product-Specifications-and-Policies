"""Of N questions about one product, how many ask something not already asked? Scratch, lexical."""
import json, statistics, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import pqa_category_probe as P

def n_intents(qs):
    toks = [P.content_tokens(q) for q in qs]
    parent = list(range(len(qs)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i in range(len(qs)):
        for j in range(i + 1, len(qs)):
            a, b = toks[i], toks[j]
            if a and b and (a == b or P.ND_LO <= P.jaccard(a, b) <= P.ND_HI):
                parent[find(i)] = find(j)
    return len({find(i) for i in range(len(qs))})

RAW = Path("/Users/hung/Desktop/Sem1/thesis/data/raw/pqa")
NS = [10, 20, 50, 100]
print(f"{'leaf':22}{'products >=100 q':>17} | " + "".join(f"{'new / '+str(n):>12}" for n in NS) + f"{'  new per 100 (p25-p75)':>26}")
for leaf in ["unlocked_cell_phones", "traditional_laptops", "led_&_lcd_tvs", "over-ear_headphones", "chairs", "home_office_desks"]:
    rows = defaultdict(list)
    for l in open(RAW / f"amazon_pqa_{leaf}.json", "rb"):
        r = json.loads(l); q = (r.get("question_text") or "").strip()
        if r.get("asin") and q: rows[r["asin"]].append(q)
    prods = [qs[:100] for qs in rows.values() if len(qs) >= 100]
    res = {n: [n_intents(qs[:n]) for qs in prods] for n in NS}
    r100 = sorted(res[100])
    print(f"{leaf:22}{len(prods):>17} | " + "".join(f"{statistics.mean(res[n]):>9.1f}/{n:<2}" for n in NS)
          + f"{r100[len(r100)//4]:>16}-{r100[3*len(r100)//4]}")
