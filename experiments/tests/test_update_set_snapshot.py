"""Item 4.4, done condition 9: the snapshot finds what the cache's own bookkeeping misses.

A fake redis client holds a dict of keys. No Redis, no gateway. The silent failure this pins: a
promoted Tier-1 key that `lru:t1keys:{entry_id}` does not list. A check that read that set would call
the entry purged while its Tier-1 copy was still being served.
"""

import fnmatch

import update_set_check as usc


class FakeClient:
    """scan_iter and hget over a dict of hashes; it records every pattern it was asked for."""

    def __init__(self, hashes: dict):
        self.hashes = hashes
        self.patterns: list[str] = []

    def scan_iter(self, match="*", count=None):
        self.patterns.append(match)
        for key in sorted(self.hashes):
            if fnmatch.fnmatchcase(key, match):
                yield key

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)


def test_snapshot_finds_t1_key_missing_from_lru_t1keys():
    client = FakeClient(
        {
            "t1:aaa": {"entry_id": "E1", "answer": "x"},
            "t1:bbb": {"entry_id": "E1", "answer": "x"},  # the promoted key
            "lru:t1keys:E1": {},  # stands in for the set; it lists only t1:aaa
            "t2:E1": {"t1_key": "t1:aaa"},
        }
    )

    snap = usc.snapshot(client)

    assert snap["E1"]["t1_keys"] == ["t1:aaa", "t1:bbb"]
    assert snap["E1"]["t2"] is True


def test_snapshot_reads_t2_and_entry_records():
    client = FakeClient(
        {
            "t1:aaa": {"entry_id": "E1"},
            "t2:E1": {"t1_key": "t1:aaa"},
            "entry:E1": {"t1_key": "t1:aaa"},
            "t2:E2": {"t1_key": "t1:zzz"},  # a Tier-2 record whose Tier-1 key is gone
            "entry:E3": {"t1_key": ""},  # a registration with nothing else left
            "t1:orphan": {"answer": "no entry_id field"},
        }
    )

    snap = usc.snapshot(client)

    assert snap["E1"] == {"t1_keys": ["t1:aaa"], "t2": True, "entry": True}
    assert snap["E2"] == {"t1_keys": [], "t2": True, "entry": False}
    assert snap["E3"] == {"t1_keys": [], "t2": False, "entry": True}
    assert snap[usc.NO_ENTRY_ID]["t1_keys"] == ["t1:orphan"]
    assert list(snap) == sorted(
        snap
    )  # a stable order, so a saved snapshot is the same bytes twice


def test_snapshot_ignores_corpus_keys():
    client = FakeClient(
        {
            "corpus::policy-return#chunk-0": {"text": "a policy", "entry_id": "E1"},
            "lru:entries": {},
            "lru:t1keys:E1": {},
            "dep:policy-return#chunk-0": {},
            "idx:cache": {},
        }
    )

    assert usc.snapshot(client) == {}
    # It asked for exactly the three families, and never for corpus keys.
    assert client.patterns == ["t1:*", "t2:*", "entry:*"]
