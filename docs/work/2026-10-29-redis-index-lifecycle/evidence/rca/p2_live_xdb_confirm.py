"""Live-server confirmation, non-destructive: throwaway index idx:rca2-xdb (prefix rca2:xdb:, which no
DB 0 key has), keys only in EMPTY db 13, no FLUSHDB, FT.DROPINDEX without DD, delete only own keys."""
import redis
L0 = redis.Redis(port=6379, db=0, decode_responses=True)
L13 = redis.Redis(port=6379, db=13, decode_responses=True)
assert L13.dbsize() == 0, "db 13 not empty: stop"
assert not L0.keys("rca2:*"), "db 0 has rca2:* keys: stop"
before = sorted(L0.execute_command("FT._LIST"))
print("FT._LIST before:", before)
try:
    L13.execute_command("FT.CREATE", "idx:rca2-xdb13", "ON", "HASH", "PREFIX", "1", "rca2:xdb:", "SCHEMA", "f", "TAG")
    print("FT.CREATE from db13: OK (unexpected)")
except redis.ResponseError as e:
    print("FT.CREATE from db13 ->", e)
L0.execute_command("FT.CREATE", "idx:rca2-xdb", "ON", "HASH", "PREFIX", "1", "rca2:xdb:", "SCHEMA", "f", "TAG")
def nd():
    i = L0.execute_command("FT.INFO", "idx:rca2-xdb")
    return dict(zip(i[::2], i[1::2]))["num_docs"]
import time; time.sleep(0.2)
print("num_docs after create (db0 has no rca2:xdb: keys):", nd())
L13.hset("rca2:xdb:1", mapping={"f": "t"})
print("num_docs after HSET rca2:xdb:1 in db13:", nd())
print("FT.SEARCH from db0 @f:{t}:", L0.execute_command("FT.SEARCH", "idx:rca2-xdb", "@f:{t}"))
L13.delete("rca2:xdb:1")
print("num_docs after DEL in db13:", nd())
L0.execute_command("FT.DROPINDEX", "idx:rca2-xdb")  # no DD
after = sorted(L0.execute_command("FT._LIST"))
print("FT._LIST after:", after, "| unchanged:", after == before, "| db13 size:", L13.dbsize(), "| db0 size:", L0.dbsize())
