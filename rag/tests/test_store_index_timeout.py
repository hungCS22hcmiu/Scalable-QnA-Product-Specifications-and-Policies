"""`wait_until_indexed` raises instead of returning when an index never finishes building.

No Redis: a fake client whose FT.INFO always says the index is still indexing.
"""

import time

import pytest

from rag import store


class _FakeIndex:
    def __init__(self, info: dict):
        self._info = info

    def info(self) -> dict:
        return self._info


class _FakeClient:
    """Stands in for redis.Redis: only `.ft(name).info()` is used."""

    def __init__(self, info: dict):
        self._info = info
        self.names: list[str] = []

    def ft(self, name: str) -> _FakeIndex:
        self.names.append(name)
        return _FakeIndex(self._info)


def test_wait_until_indexed_raises_when_indexing_never_finishes():
    client = _FakeClient({"indexing": 1, "percent_indexed": "0.25", "num_docs": 11})
    timeout_s = 0.05

    start = time.monotonic()
    with pytest.raises(store.IndexNotReady) as exc:
        store.wait_until_indexed(client, "idx:never-ready", timeout_s=timeout_s, poll_s=0.005)
    elapsed = time.monotonic() - start

    assert elapsed >= timeout_s, f"raised after {elapsed:.3f}s, before the {timeout_s}s limit"
    assert "idx:never-ready" in str(exc.value)
    assert client.names, "the fake FT.INFO was never asked"
