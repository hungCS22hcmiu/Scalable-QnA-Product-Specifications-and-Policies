"""Build N distinct RAG prompts exactly as rag.server would (retrieve with product scope + _build_prompt)."""
import json, sys
from rag import retrieve
from rag.generate import _build_prompt

wl, out, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
items = json.load(open(wl))
seen_c, seen_p, picked = set(), set(), []
for it in items:  # distinct cluster AND distinct product, so no two prompts share a context
    if it["cluster_id"] in seen_c or it["product_id"] in seen_p:
        continue
    seen_c.add(it["cluster_id"]); seen_p.add(it["product_id"]); picked.append(it)
    if len(picked) == n:
        break
with open(out, "w") as f:
    for it in picked:
        chunks, ep = retrieve.retrieve(it["question"], product_id=it["product_id"])
        p = _build_prompt(it["question"], chunks)
        f.write(json.dumps({"qa_id": it["qa_id"], "product_id": it["product_id"], "chunk_ids": [c.chunk_id for c in chunks], "prompt": p}) + "\n")
print(len(picked), "prompts written")
