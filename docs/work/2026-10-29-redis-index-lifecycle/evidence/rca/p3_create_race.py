"""Problem 3 probe: does FT.CREATE (idx:cache schema) return before existing hashes are indexed,
and how long is a namespace-filtered KNN partial? Throwaway index name + prefix; PRIVATE instance
only by default. Synthetic float32 vectors, no model."""
import random
import sys
import time

import numpy as np
import redis

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6391
assert PORT != 6379, "the destructive set-up below runs FLUSHALL: private instance only"
DIM, IDX, PFX = 768, "idx:rca2-cache", "rca2:t2:"
N_NS = 100          # namespaces (product ids); entries spread over them
FILLER = 539        # v1 corpus chunk count: other keys the background scan walks past
TRIALS = 30
r = redis.Redis(port=PORT, db=0)

def info():
    i = r.execute_command("FT.INFO", IDX)
    d = dict(zip([k.decode() for k in i[::2]], i[1::2]))
    return int(d["num_docs"]), int(d["indexing"]), float(d["percent_indexed"])

def create():
    return r.execute_command(
        "FT.CREATE", IDX, "ON", "HASH", "PREFIX", "1", PFX, "SCHEMA",
        "embedding", "VECTOR", "FLAT", "6", "TYPE", "FLOAT32", "DIM", str(DIM), "DISTANCE_METRIC", "COSINE",
        "query_text", "TEXT", "t1_key", "TAG", "dataset_epoch", "NUMERIC", "namespace", "TAG", "lane", "TAG")

def drop():
    try:
        r.execute_command("FT.DROPINDEX", IDX)  # never DD
    except redis.ResponseError:
        pass

def knn(qbytes, ns):
    res = r.execute_command(
        "FT.SEARCH", IDX, f"(@namespace:{{{ns}}})=>[KNN 1 @embedding $vec AS dist]", "PARAMS", "2", "vec", qbytes,
        "SORTBY", "dist", "ASC", "RETURN", "1", "dist", "LIMIT", "0", "1", "DIALECT", "2")
    return res[1].decode() if res[0] else None

def populate(n):
    r.flushall()
    rng = np.random.default_rng(n)
    vecs = rng.standard_normal((n, DIM)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    p = r.pipeline(transaction=False)
    for i in range(n):
        p.hset(f"{PFX}E{i:05d}", mapping={
            "embedding": vecs[i].astype("<f4").tobytes(), "query_text": f"question {i}", "answer": f"answer {i}",
            "source_chunk_ids": '["c#0"]', "t1_key": f"rca2:t1:{i}", "dataset_epoch": 0,
            "namespace": f"ns{i % N_NS}", "lane": "SPEC"})
        p.hset(f"rca2:t1:{i}", mapping={"answer": "a", "entry_id": f"E{i:05d}"})   # t1-like, not indexed
    for j in range(FILLER):
        p.hset(f"rca2:corpus:{j}", mapping={"text": "x" * 200})
    p.execute()
    return vecs

def trial(vecs, n, delay_s):
    drop()
    i = random.randrange(n)
    q = vecs[i].astype("<f4").tobytes()
    t0 = time.perf_counter()
    create()
    t_ret = time.perf_counter()
    if delay_s:
        time.sleep(delay_s)
    nd, ing, pct = info()
    got = knn(q, f"ns{i % N_NS}")
    while info()[1] != 0:
        pass
    t_done = time.perf_counter()
    outcome = "correct" if got == f"{PFX}E{i:05d}" else ("EMPTY" if got is None else "OTHER")
    return outcome, nd, ing, pct, (t_done - t_ret) * 1e3, (t_ret - t0) * 1e3

print(f"port={PORT} index={IDX} prefix={PFX} dim={DIM} namespaces={N_NS} filler_keys={FILLER} trials={TRIALS}")
for n in (44, 163, 318, 1274, 5000):
    vecs = populate(n)
    for delay_ms in (0, 5, 20, 50):
        rows = [trial(vecs, n, delay_ms / 1e3) for _ in range(TRIALS)]
        outs = [x[0] for x in rows]
        nd = [x[1] for x in rows]
        done = sorted(x[4] for x in rows)
        create_ms = sorted(x[5] for x in rows)
        print(f"N={n:5d} delay={delay_ms:2d}ms  correct={outs.count('correct'):2d}/{TRIALS} empty={outs.count('EMPTY'):2d} "
              f"other={outs.count('OTHER'):2d}  num_docs@first-read min/med/max={min(nd)}/{sorted(nd)[len(nd)//2]}/{max(nd)} of {n}  "
              f"indexing=1 at first read: {sum(1 for x in rows if x[2])}/{TRIALS}  "
              f"FT.CREATE call {create_ms[len(create_ms)//2]:.2f}ms  create->indexing==0 med/max={done[len(done)//2]:.1f}/{done[-1]:.1f}ms")
drop()

# Sanity: once the index is complete, is a new HSET searchable immediately (PutTier2 then a search)?
vecs = populate(318)
create()
while info()[1] != 0:
    pass
v = np.random.default_rng(7).standard_normal(DIM).astype(np.float32); v /= np.linalg.norm(v)
p = r.pipeline(transaction=False)
p.hset(f"{PFX}NEW", mapping={"embedding": v.astype("<f4").tobytes(), "namespace": "nsX", "answer": "n"})
p.execute_command("FT.SEARCH", IDX, "(@namespace:{nsX})=>[KNN 1 @embedding $vec AS dist]", "PARAMS", "2", "vec",
                  v.astype("<f4").tobytes(), "RETURN", "1", "dist", "DIALECT", "2")
print("HSET then KNN in one pipeline, complete index:", p.execute()[1])

# FT.CREATE of a name that already exists while its scan is still running: EnsureCacheIndex's swallow path
drop(); create()
try:
    create()
except redis.ResponseError as e:
    print("second FT.CREATE during the scan:", e, "| info right after:", info())
drop()
r.flushall()
