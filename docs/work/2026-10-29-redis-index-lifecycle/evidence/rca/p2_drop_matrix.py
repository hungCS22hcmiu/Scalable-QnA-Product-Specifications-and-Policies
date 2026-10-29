"""Problem 2 probe: which commands drop RediSearch indexes. PRIVATE instance only (port 6391)."""
import sys
import redis

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6391
assert PORT != 6379, "refusing to run destructive probe on the live server"

def c(db):
    return redis.Redis(port=PORT, db=db, decode_responses=True)

def lst():
    return sorted(c(0).execute_command("FT._LIST"))

def setup():
    c(0).flushall()
    # both in db 0: RediSearch 2.10.20 refuses FT.CREATE on db != 0
    c(0).execute_command("FT.CREATE", "idx:a", "ON", "HASH", "PREFIX", "1", "a:", "SCHEMA", "f", "TEXT")
    c(0).execute_command("FT.CREATE", "idx:b", "ON", "HASH", "PREFIX", "1", "b:", "SCHEMA", "f", "TEXT")
    c(0).hset("a:1", "f", "hello")
    c(0).hset("b:1", "f", "hello")

def ndocs(name, db=0):
    info = c(db).execute_command("FT.INFO", name)
    d = dict(zip(info[::2], info[1::2]))
    return d["num_docs"]

cases = [
    ("FLUSHDB on EMPTY db 5", lambda: c(5).flushdb()),
    ("FLUSHDB ASYNC on EMPTY db 5", lambda: c(5).execute_command("FLUSHDB", "ASYNC")),
    ("FLUSHDB SYNC on EMPTY db 5", lambda: c(5).execute_command("FLUSHDB", "SYNC")),
    ("FLUSHDB on db 7 holding 1 key, no index", lambda: (c(7).set("x", 1), c(7).flushdb())),
    ("FLUSHALL", lambda: c(9).flushall()),
    ("SWAPDB 5 6 (both empty)", lambda: c(0).swapdb(5, 6)),
    ("SWAPDB 0 5 (db0 has idx:a docs)", lambda: c(0).swapdb(0, 5)),
    ("DEL every a: key in db 0", lambda: c(0).delete("a:1")),
    ("UNLINK every a: key in db 0", lambda: c(0).unlink("a:1")),
    ("MOVE a:1 from db 0 to db 5", lambda: c(0).move("a:1", 5)),
    ("RENAME a:1 -> z:1 in db 0", lambda: c(0).rename("a:1", "z:1")),
    ("FT.DROPINDEX idx:b (no DD)", lambda: c(0).execute_command("FT.DROPINDEX", "idx:b")),
]

for label, fn in cases:
    setup()
    before = lst()
    try:
        fn()
        err = ""
    except Exception as e:  # noqa: BLE001
        err = f"  (command error: {e})"
    after = lst()
    extra = ""
    if "idx:a" in after:
        extra = f"  idx:a num_docs={ndocs('idx:a')}"
    print(f"{label:45s} before={before} after={after}{extra}{err}")
c(0).flushall()
