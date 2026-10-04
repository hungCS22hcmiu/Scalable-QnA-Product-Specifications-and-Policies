"""Show what ONE v1 product record would look like if built from data/raw/pqa today.
Scratch illustration for investigation `pqa-category-choice` -- not the builder (item 3.1)."""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path("/Users/hung/Desktop/Sem1/thesis")
sys.path.insert(0, str(REPO / "rag" / "src"))
sys.path.insert(0, str(Path(__file__).parent))
import pqa_category_probe as P  # noqa: E402  same filters and near-duplicate test as the probe

LEAF, CATEGORY = sys.argv[1], sys.argv[2]
rows = defaultdict(list)
first = {}
for line in open(REPO / "data/raw/pqa" / f"amazon_pqa_{LEAF}.json", "rb"):
    r = json.loads(line)
    q = (r.get("question_text") or "").strip()
    if not r.get("asin") or not q:
        continue
    rows[r["asin"]].append(r)
    first.setdefault(r["asin"], r)


def keep(q):
    return not (P.DYNAMIC_Q.search(q) or P.CARRIER_Q.search(q))


def prose(r):
    return " ".join((r.get(f) or "") for f in P.PROSE_FIELDS)


cands = []
for asin, rs in rows.items():
    qs = [r["question_text"].strip() for r in rs if keep(r["question_text"])]
    bullets = sum(1 for i in range(1, 6) if (first[asin].get(f"bullet_point{i}") or "").strip())
    if (not P.CAP_LO <= len(qs) <= P.CAP_HI or bullets < 3
            or P.WARRANTY_TERM.search(prose(first[asin]))):
        continue
    toks = [P.content_tokens(q) for q in qs]
    pairs = [(qs[i], qs[j]) for i in range(len(qs)) for j in range(i + 1, len(qs))
             if toks[i] != toks[j] and P.ND_LO <= P.jaccard(toks[i], toks[j]) <= P.ND_HI]
    if pairs:
        cands.append((abs(len(qs) - 15), asin, qs, pairs))
cands.sort()
_, asin, qs, pairs = cands[0]          # deterministic: closest to 15 questions, then by asin
r = first[asin]

specs = {}
for i in range(1, 6):
    v = (r.get(f"bullet_point{i}") or "").strip()
    if v:
        specs[f"Feature {i}"] = v
if (r.get("product_description") or "").strip():
    specs["Description"] = r["product_description"].strip()
if (r.get("brand_name") or "").strip():
    specs["Brand"] = r["brand_name"].strip()

record = {
    "doc_id": f"product-{CATEGORY}-{asin.lower()}",
    "title": r["item_name"].strip(),
    "category": CATEGORY,
    "source_category": LEAF,
    "specs": specs,
}
print(f"=== candidates qualifying: {len(cands)}; chosen asin {asin}\n")
print(json.dumps(record, indent=2, ensure_ascii=False))

from rag.ingest import product_to_text  # noqa: E402  the real renderer
text = product_to_text(record)
print(f"\n=== rendered by rag.ingest.product_to_text ({len(text)} chars)\n{text}")
try:
    from llama_index.core import Document
    from llama_index.core.node_parser import SentenceSplitter
    from rag import config
    nodes = SentenceSplitter(chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP) \
        .get_nodes_from_documents([Document(text=text)])
    print(f"\n=== chunks at chunk_size={config.CHUNK_SIZE}, overlap={config.CHUNK_OVERLAP}: {len(nodes)}")
except Exception as e:  # noqa: BLE001
    print(f"\n=== chunk count unavailable: {e}")

dropped = [x["question_text"].strip() for x in rows[asin] if not keep(x["question_text"])]
print(f"\n=== its questions: {len(rows[asin])} raw, {len(qs)} kept, {len(dropped)} filtered")
for q in qs:
    print("   ", q[:110])
for q in dropped:
    print("  x", q[:110])
print("\n=== near-duplicate pairs (stratum A/C material)")
for a, b in pairs[:4]:
    print(f"    {a[:60]!r}  ~  {b[:60]!r}")
