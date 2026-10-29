"""Item 4.4, done condition 5: the cache reset deletes five prefixes and nothing else.

A fake client holds a set of key names. It raises if `flushdb` or `flushall` is called, because on
this Redis either one drops every search index (RCA 2026-10-29). No Redis, no gateway.
"""

import fnmatch

import cache_reset
import pytest

FIVE = ("t1:", "t2:", "lru:", "dep:", "entry:")


class FakeClient:
    def __init__(self, keys, indexes=("idx:corpus", "idx:cache")):
        self.keys = set(keys)
        self.indexes = list(indexes)
        self.unlink_calls = 0

    def scan_iter(self, match="*", count=None):
        for key in sorted(self.keys):
            if fnmatch.fnmatchcase(key, match):
                yield key

    def unlink(self, *keys):
        self.unlink_calls += 1
        gone = self.keys & set(keys)
        self.keys -= gone
        return len(gone)

    def execute_command(self, *args):
        assert args == ("FT._LIST",), f"unexpected command {args}"
        return [i.encode() for i in self.indexes]

    def flushdb(self, *a, **k):
        raise AssertionError("FLUSHDB must never be called")

    def flushall(self, *a, **k):
        raise AssertionError("FLUSHALL must never be called")


def a_cache():
    keys = {f"corpus::policy-return#chunk-{i}" for i in range(3)}
    for prefix in FIVE:
        keys.update(f"{prefix}{name}" for name in ("a", "b", "c"))
    return FakeClient(keys)


def count(client, prefix):
    return sum(1 for k in client.keys if k.startswith(prefix))


def test_reset_empties_the_five_prefixes():
    client = a_cache()

    deleted = cache_reset.reset(client, listening=[])

    assert deleted == {prefix: 3 for prefix in FIVE}
    assert [count(client, p) for p in FIVE] == [0, 0, 0, 0, 0]


def test_reset_keeps_corpus_keys_and_index_list():
    client = a_cache()
    corpus_before = {k for k in client.keys if k.startswith("corpus:")}

    cache_reset.reset(client, listening=[])

    assert {k for k in client.keys if k.startswith("corpus:")} == corpus_before
    assert client.indexes == ["idx:corpus", "idx:cache"]


def test_reset_refuses_while_a_gateway_listens():
    client = a_cache()
    before = set(client.keys)

    with pytest.raises(cache_reset.ResetRefused, match="18081"):
        cache_reset.reset(client, listening=[18081])

    assert client.keys == before  # deletes nothing
    assert client.unlink_calls == 0


def test_reset_never_flushes():
    client = a_cache()  # raises if flushdb or flushall is called

    cache_reset.reset(client, listening=[])

    # And a reset on a cache that is already empty still flushes nothing.
    cache_reset.reset(client, listening=[])
