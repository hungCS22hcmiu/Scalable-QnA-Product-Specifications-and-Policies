import logging
logging.disable(logging.INFO)
from rag.retrieve import retrieve
q = "what is the power rating of this item exactly right now"
runs = []
for i in range(15):
    chunks, _ = retrieve(q, top_k=10)
    runs.append([(c.chunk_id, round(c.score, 9)) for c in chunks])
print("distinct top-10 rankings over 15 warm calls:", len({tuple(r) for r in runs}))
for cid, s in runs[0]:
    print(f"  {s:.9f}  {cid}")
