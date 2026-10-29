"""Problem 2 probe: are index names / indexed keyspace global across logical dbs? PRIVATE instance only."""
import sys
import numpy as np
import redis

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6391
assert PORT != 6379, "refusing to run on the live server"
DIM = 768

def c(db):
    return redis.Redis(port=PORT, db=db)

def info(name, db=0):
    i = c(db).execute_command("FT.INFO", name)
    d = dict(zip([k.decode() if isinstance(k, bytes) else k for k in i[::2]], i[1::2]))
    return {k: d[k] for k in ("num_docs", "indexing", "percent_indexed")}

def vec(seed):
    v = np.random.default_rng(seed).standard_normal(DIM).astype(np.float32)
    return (v / np.linalg.norm(v)).astype("<f4").tobytes()

def create_cache_like(name, prefix, db=0):
    # same schema as gateway/internal/cache/tier2.go EnsureCacheIndex
    return c(db).execute_command(
        "FT.CREATE", name, "ON", "HASH", "PREFIX", "1", prefix, "SCHEMA",
        "embedding", "VECTOR", "FLAT", "6", "TYPE", "FLOAT32", "DIM", str(DIM), "DISTANCE_METRIC", "COSINE",
        "query_text", "TEXT", "t1_key", "TAG", "dataset_epoch", "NUMERIC", "namespace", "TAG", "lane", "TAG")

def knn(name, db, q, filt="*"):
    r = c(db).execute_command(
        "FT.SEARCH", name, f"{filt}=>[KNN 3 @embedding $vec AS dist]", "PARAMS", "2", "vec", q,
        "SORTBY", "dist", "ASC", "RETURN", "2", "dist", "answer", "LIMIT", "0", "3", "DIALECT", "2")
    return r

c(0).flushall()
# 1. a hash in db 15 BEFORE the index exists
c(15).hset("t2:pre15", mapping={"embedding": vec(1), "answer": "from-db15-pre", "namespace": "ns1"})
c(0).hset("t2:live0", mapping={"embedding": vec(2), "answer": "from-db0", "namespace": "ns1"})
print("create in db0:", create_cache_like("idx:x", "t2:"))
import time; time.sleep(0.2)
print("1. after create (scan):", info("idx:x"))

# 2. HSET in db 15 AFTER the index exists
c(15).hset("t2:post15", mapping={"embedding": vec(3), "answer": "from-db15-post", "namespace": "ns1"})
print("2. after HSET t2:post15 in db15:", info("idx:x"))

# 3. KNN from db 0 with the query equal to the db15 vector
print("3a. KNN from db0, q=vec(3):", knn("idx:x", 0, vec(3)))
print("3b. KNN from db15, q=vec(3):", knn("idx:x", 15, vec(3)))
print("3c. KNN from db0 with namespace filter:", knn("idx:x", 0, vec(3), "(@namespace:{ns1})"))

# 4. FT.CREATE of an EXISTING name from db 15, and of a NEW name from db 15
for nm in ("idx:x", "idx:new"):
    try:
        print(f"4. FT.CREATE {nm} from db15:", create_cache_like(nm, "t2:", db=15))
    except Exception as e:  # noqa: BLE001
        print(f"4. FT.CREATE {nm} from db15 -> error: {e}")

# 5. DEL the db-15 key: is the doc removed from idx:x?
c(15).delete("t2:post15")
print("5. after DEL t2:post15 in db15:", info("idx:x"))
print("5b. KNN from db0 after DEL:", knn("idx:x", 0, vec(3)))

# 6. same key name in db 0 and db 15: DEL in db 15 when db 0 holds t2:live0
c(15).hset("t2:live0", mapping={"embedding": vec(9), "answer": "db15-shadow", "namespace": "ns1"})
print("6a. after db15 HSET of a key name that db0 also holds:", info("idx:x"))
print("6b. KNN from db0 q=vec(2) (db0's own vector):", knn("idx:x", 0, vec(2)))
print("6c. KNN from db0 q=vec(9) (db15's vector):", knn("idx:x", 0, vec(9)))
c(15).delete("t2:live0")
print("6d. after DEL t2:live0 in db15 (db0 copy still exists):", info("idx:x"), "db0 EXISTS t2:live0 =", c(0).exists("t2:live0"))
print("6e. KNN from db0 q=vec(2):", knn("idx:x", 0, vec(2)))

# 7. FT.SEARCH on a missing index name: exact error text
try:
    knn("idx:rca2-missing", 0, vec(2))
except Exception as e:  # noqa: BLE001
    print("7. FT.SEARCH missing index -> error:", repr(e))
c(0).flushall()
