"""Item 4.4: the run-rule-11 cache reset (interfaces.md, run rule 11).

    make cache-reset

Deletes every `t1:`, `t2:`, `lru:`, `dep:` and `entry:` key by SCAN + UNLINK, and nothing else. A
measured run must start on a cache it wrote itself, and the dependency records must go too: a leftover
`entry:` or `dep:` record names an entry that no longer exists, and a tombstone in a live gateway would
point at a deleted key.

NEVER FLUSHDB or FLUSHALL. On this Redis either one drops every search index, in every DB, including
`idx:corpus` (RCA 2026-10-29, docs/work/2026-10-29-redis-index-lifecycle/). After the delete the
script checks that the five prefixes are empty, that the number of `corpus:` keys has not changed, and
that `FT._LIST` lists the same indexes as before.

It refuses while a gateway port (8080, 18080, 18081) is listening: a reset under a live gateway leaves
the gateway's in-process tombstones pointing at deleted keys. A gateway on another port is not seen.
"""

import argparse
import os
import subprocess
import sys

PREFIXES = ("t1:", "t2:", "lru:", "dep:", "entry:")
CORPUS_PREFIX = "corpus:"
GATEWAY_PORTS = (8080, 18080, 18081)
BATCH = 1000


class ResetRefused(RuntimeError):
    """The reset did not start: a gateway is listening. Nothing was deleted."""


class ResetFailed(RuntimeError):
    """The reset ran and a check after it failed. The message says which."""


def _count(client, prefix: str) -> int:
    return sum(1 for _ in client.scan_iter(match=f"{prefix}*", count=BATCH))


def _index_list(client) -> list[str]:
    return sorted(
        i.decode() if isinstance(i, bytes) else i
        for i in client.execute_command("FT._LIST")
    )


def reset(client, *, listening: list[int]) -> dict[str, int]:
    """Delete the cache and dependency keys. Returns how many keys went, per prefix.

    `listening` is the gateway ports that have a listener. A non-empty list refuses the reset before
    anything is touched.
    """
    if listening:
        raise ResetRefused(
            f"a gateway is listening on port(s) {sorted(listening)}; stop it first. "
            "Nothing was deleted."
        )

    corpus_before = _count(client, CORPUS_PREFIX)
    indexes_before = _index_list(client)

    deleted: dict[str, int] = {}
    for prefix in PREFIXES:
        n = 0
        batch: list = []
        for key in client.scan_iter(match=f"{prefix}*", count=BATCH):
            batch.append(key)
            if len(batch) >= BATCH:
                n += client.unlink(*batch)
                batch = []
        if batch:
            n += client.unlink(*batch)
        deleted[prefix] = n

    left = {p: _count(client, p) for p in PREFIXES}
    if any(left.values()):
        raise ResetFailed(
            f"keys survived the reset: { {p: c for p, c in left.items() if c} }"
        )
    corpus_after = _count(client, CORPUS_PREFIX)
    if corpus_after != corpus_before:
        raise ResetFailed(
            f"corpus: keys changed from {corpus_before} to {corpus_after}"
        )
    indexes_after = _index_list(client)
    if indexes_after != indexes_before:
        raise ResetFailed(f"FT._LIST changed from {indexes_before} to {indexes_after}")
    return deleted


def listening_ports(ports=GATEWAY_PORTS) -> list[int]:
    """The ports in `ports` that have a TCP listener, found with lsof."""
    found = []
    for port in ports:
        out = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.stdout.strip():
            found.append(port)
    return found


def main(argv: list[str] | None = None) -> int:
    import redis

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--redis-url", default=os.environ.get("REDIS_URL", "redis://localhost:6379")
    )
    args = parser.parse_args(argv)

    client = redis.from_url(args.redis_url)
    try:
        deleted = reset(client, listening=listening_ports())
    except (ResetRefused, ResetFailed) as e:
        print(f"cache-reset FAILED: {e}", file=sys.stderr)
        return 1
    except redis.RedisError as e:
        print(f"cache-reset FAILED: redis: {e!r}", file=sys.stderr)
        return 1

    for prefix, n in deleted.items():
        print(f"deleted {prefix:<7} {n}")
    print(
        f"corpus: keys {_count(client, CORPUS_PREFIX)}; FT._LIST {_index_list(client)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
