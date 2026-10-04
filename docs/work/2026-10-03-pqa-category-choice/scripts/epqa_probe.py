"""ePQA against the same questions asked of PQA. Investigation `pqa-category-choice` -- scratch."""

import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pqa_category_probe as P  # noqa: E402  same near-duplicate definition as the PQA probe

HERE = Path(__file__).parent
SPEC_SOURCES = {"bullet", "attribute", "description", "json", "attributes"}

rows = []
for split in ["train", "dev", "test"]:
    with open(HERE / "epqa" / f"ePQA_{split}.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["split"] = split
            rows.append(r)

src = Counter(r["source"] for r in rows)
lab = Counter(r["label"] for r in rows)
qs = {}                                     # (split, qid) -> question record
for r in rows:
    k = (r["split"], r["qid"])
    q = qs.setdefault(k, {"q": r["question"].strip(), "asin": r["ASIN"], "title": r["title"],
                          "labels": [], "split": r["split"]})
    q["labels"].append((r["source"], r["label"]))

n = len(qs)
full_any = sum(1 for q in qs.values() if any(l == "2" for _, l in q["labels"]))
full_spec = sum(1 for q in qs.values() if any(l == "2" and s in SPEC_SOURCES for s, l in q["labels"]))
full_review_only = sum(1 for q in qs.values()
                       if any(l == "2" for _, l in q["labels"])
                       and not any(l == "2" and s in SPEC_SOURCES for s, l in q["labels"]))

by_asin = defaultdict(list)
for q in qs.values():
    by_asin[q["asin"]].append(q["q"])
qpp = sorted(len(v) for v in by_asin.values())
multi = [a for a, v in by_asin.items() if len(v) >= 2]
nd = 0
for a in multi:
    t = [P.content_tokens(x) for x in by_asin[a][:P.PAIR_CAP]]
    if any(x != y and P.ND_LO <= P.jaccard(x, y) <= P.ND_HI for i, x in enumerate(t) for y in t[i + 1:]):
        nd += 1
cand_per_q = statistics.mean(len(q["labels"]) for q in qs.values())

print(f"rows {len(rows):,}   questions {n:,}   ASINs {len(by_asin):,}   candidates/question {cand_per_q:.1f}")
print(f"sources {dict(src)}")
print(f"labels  {dict(lab)}")
print(f"questions with a FULLY answering candidate (label 2): {full_any:,} ({100*full_any/n:.1f}%)")
print(f"  ... from a SPEC source {sorted(SPEC_SOURCES & set(src))}: {full_spec:,} ({100*full_spec/n:.1f}%)")
print(f"  ... only from review/cqa: {full_review_only:,} ({100*full_review_only/n:.1f}%)")
print(f"questions per ASIN: mean {statistics.mean(qpp):.2f}  median {statistics.median(qpp)}  "
      f"max {qpp[-1]}  ASINs with >=2: {len(multi):,}  >=5: {sum(1 for x in qpp if x >= 5):,}")
print(f"multi-question ASINs with a near-duplicate pair: {nd:,} ({100*nd/max(1,len(multi)):.1f}%)")

# ASIN overlap with every PQA leaf file on disk, and exact question-text overlap.
eq = defaultdict(set)
for q in qs.values():
    eq[q["asin"]].add(q["q"].lower())
paths = sorted(Path("/Users/hung/Desktop/Sem1/thesis/data/raw/pqa").glob("amazon_pqa_*.json")) + \
        sorted((HERE / "pqa").glob("amazon_pqa_*.json"))
seen_leaf = set()
tot_asin = tot_q = 0
for p in paths:
    leaf = p.name[len("amazon_pqa_"):-5]
    if leaf in seen_leaf:
        continue
    seen_leaf.add(leaf)
    hit_asin, hit_q = set(), 0
    for line in p.open("rb"):
        r = json.loads(line)
        a = r.get("asin")
        if a in eq:
            hit_asin.add(a)
            if (r.get("question_text") or "").strip().lower() in eq[a]:
                hit_q += 1
    tot_asin += len(hit_asin)
    tot_q += hit_q
    print(f"  overlap with PQA {leaf:28} ASINs {len(hit_asin):>4}   identical questions {hit_q:>4}")
print(f"  total over {len(seen_leaf)} PQA leaves: ASINs {tot_asin}, identical questions {tot_q}")
print("\nexamples of spec-answerable questions:")
k = 0
for q in qs.values():
    if any(l == "2" and s in SPEC_SOURCES for s, l in q["labels"]):
        print(f"   [{q['asin']}] {q['q'][:80]!r}  — {q['title'][:50]!r}")
        k += 1
        if k == 5:
            break
