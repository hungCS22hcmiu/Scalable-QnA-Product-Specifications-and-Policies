"""Non-destructive: builds a SEPARATE index (idx:rca-probe) over the same corpus: prefix,
observes it before background indexing finishes, then drops it WITHOUT DD (no key deleted).
idx:corpus is never touched."""
import logging, time, os
logging.disable(logging.INFO)
import numpy as np
from redisvl.index import SearchIndex
from redisvl.query import VectorQuery
from rag import store, config
from rag.embedding import OllamaEmbedding

NAME = "idx:rca-probe"
q = "what is the power rating of this item exactly right now"
emb = OllamaEmbedding()
client = store.get_redis_client()
assert NAME != config.CORPUS_INDEX_NAME

def info(name):
    raw = client.execute_command("FT.INFO", name)
    d = dict(zip(raw[0::2], raw[1::2]))
    g = lambda k: d[k.encode()].decode() if isinstance(d[k.encode()], bytes) else d[k.encode()]
    return g("num_docs"), g("indexing"), g("percent_indexed")

def top5(idx, vec):
    vq = VectorQuery(vector=vec, vector_field_name="vector", return_fields=["chunk_id"], num_results=5)
    return [r["chunk_id"] for r in idx.query(vq)]

vec = emb.get_query_embedding(q)  # warm the model
mismatch = 0
N = int(os.environ.get("N", "10"))
for trial in range(N):
    schema = store.build_schema()
    schema.index.name = NAME
    idx = SearchIndex(schema=schema, redis_url=config.REDIS_URL)
    if idx.exists():
        client.ft(NAME).dropindex(delete_documents=False)
    t0 = time.perf_counter()
    idx.create()                                    # same call retrieve() makes on a missing index
    i0 = info(NAME); t1 = time.perf_counter()
    v = emb.get_query_embedding(q)                  # same gap retrieve() has: one Ollama embed
    t2 = time.perf_counter()
    first = top5(idx, v); i1 = info(NAME)
    while info(NAME)[1] not in ("0", 0):
        time.sleep(0.001)
    t3 = time.perf_counter()
    second = top5(idx, v); i2 = info(NAME)
    same = first == second
    mismatch += not same
    print(f"trial {trial}: after create {i0} | embed gap {1000*(t2-t1):.1f} ms | at 1st search {i1} | "
          f"done after {1000*(t3-t0):.1f} ms {i2} | match={same}"
          + ("" if same else f"\n    first ={first}\n    second={second}"))
    client.ft(NAME).dropindex(delete_documents=False)  # NO DD: keys kept
print(f"mismatches: {mismatch}/{N}")
print("FT._LIST:", client.execute_command("FT._LIST"), "| DB0 size:", client.dbsize())
