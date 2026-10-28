"""Non-destructive, same as race_probe.py: throwaway idx:rca-probe, dropped WITHOUT DD."""
import logging, time, os, statistics
logging.disable(logging.INFO)
from redisvl.index import SearchIndex
from redisvl.query import VectorQuery
from rag import store, config
from rag.embedding import OllamaEmbedding

NAME = "idx:rca-probe"
q = "what is the power rating of this item exactly right now"
client = store.get_redis_client()
vec = OllamaEmbedding().get_query_embedding(q)
TRUTH = ['product-kitchen-09#chunk-0', 'product-kitchen-08#chunk-0', 'product-kitchen-07#chunk-0',
         'product-kitchen-01#chunk-0', 'product-kitchen-10#chunk-0']

def indexing():
    raw = client.execute_command("FT.INFO", NAME)
    d = dict(zip(raw[0::2], raw[1::2]))
    return int(d[b"indexing"]), int(d[b"num_docs"])

def top5(idx):
    vq = VectorQuery(vector=vec, vector_field_name="vector", return_fields=["chunk_id"], num_results=5)
    return [r["chunk_id"] for r in idx.query(vq)]

done_ms, wrong = [], 0
N = int(os.environ.get("N", "20"))
for trial in range(N):
    schema = store.build_schema(); schema.index.name = NAME
    idx = SearchIndex(schema=schema, redis_url=config.REDIS_URL)
    if idx.exists():
        client.ft(NAME).dropindex(delete_documents=False)
    t0 = time.perf_counter()
    idx.create()
    early = top5(idx)                      # search with NO gap: vector already computed
    st = indexing()
    while indexing()[0]:
        pass
    done_ms.append(1000 * (time.perf_counter() - t0))
    late = top5(idx)
    wrong += early != TRUTH
    if trial < 4 or early != TRUTH:
        print(f"trial {trial}: num_docs at early search ~{st[1]}/44 | early={[c.split('#')[0][8:] for c in early]} "
              f"| late==truth {late == TRUTH}")
    client.ft(NAME).dropindex(delete_documents=False)   # NO DD
print(f"early search wrong: {wrong}/{N}")
print(f"indexing finished after create: min {min(done_ms):.1f} ms, median {statistics.median(done_ms):.1f} ms, max {max(done_ms):.1f} ms")
print("FT._LIST:", client.execute_command("FT._LIST"), "| DB0 size:", client.dbsize())
