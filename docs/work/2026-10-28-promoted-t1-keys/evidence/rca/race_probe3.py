"""Exact test replica against a throwaway index: config.CORPUS_INDEX_NAME is overridden IN THIS
PROCESS ONLY, so retrieve() runs its real code path against idx:rca-probe. Dropped WITHOUT DD."""
import logging, os
logging.disable(logging.INFO)
from rag import config, store
config.CORPUS_INDEX_NAME = "idx:rca-probe"
from rag.retrieve import retrieve

client = store.get_redis_client()
q = "what is the power rating of this item exactly right now"
retrieve(q, top_k=5)  # warm Ollama + httpx connection, like an earlier test would
def drop():
    if b"idx:rca-probe" in client.execute_command("FT._LIST"):
        client.ft("idx:rca-probe").dropindex(delete_documents=False)   # NO DD
N = int(os.environ.get("N", "100")); fails = 0
for t in range(N):
    drop()                                            # index absent, as after the Go tests
    a, _ = retrieve(q, top_k=5)                       # creates the index, then searches
    b, _ = retrieve(q, top_k=5, product_id=None)
    if [c.chunk_id for c in a] != [c.chunk_id for c in b]:
        fails += 1
        if fails <= 5:
            print(f"trial {t}: first ={[c.chunk_id.split('#')[0][8:] for c in a]}\n          second={[c.chunk_id.split('#')[0][8:] for c in b]}")
drop()
print(f"test assertion would fail: {fails}/{N}")
print("FT._LIST:", client.execute_command("FT._LIST"), "| DB0 size:", client.dbsize())
