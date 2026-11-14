"""Item 5.1: send every query of a workload split to a running gateway, once.

    make replay SPLIT=validation

The run's `RUN_ID` is set on the gateway (`RUN_ID=... make dev`), which writes the evaluation log. This
script only sends the questions. It is NOT a load driver: one query at a time, in a seeded shuffle, so a
run is repeatable. Phase 6's rate sweep stays with k6 (`experiments/k6/ask.js`).

Each request is `POST /ask {question, product_id}`, with `product_id` left out when the query has none
(interfaces.md section A), and an `X-Thesis-Stratum` header (section A, the workload's label). It prints
progress and the macOS memory pressure level every 50 requests, and stops at level 4.

A query with no `product_id` is not sent (item 6.0a, ADR-025's decision): the command skips it before it
orders the rest, and the summary says `skipped_no_product_id`. Validation has 16 such queries, so a
validation replay sends 606. The seeded order is drawn over the queries that remain, so two replays of
one split see the same sequence. The test split has none.

Exit codes: 0 every request got an HTTP answer; 1 a request failed or the replay stopped.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable

import corpus_gate
import judge_references as refs

SPLITS = ("validation", "test")
DEFAULT_URL = "http://localhost:8080"
PROGRESS_EVERY = 50
PRESSURE_STOP = 4  # macOS critical (CLAUDE.md, ADR-014)
TIMEOUT_S = 300.0  # a cold generation on this envelope takes seconds; a timeout would read as an error


class ReplayStopped(RuntimeError):
    """The replay stopped before the last query. The message says why."""


def order(queries: list[dict], seed: int = 7) -> list[dict]:
    """The queries in a seeded shuffle: the same seed gives the same order."""
    shuffled = list(queries)
    random.Random(seed).shuffle(shuffled)
    return shuffled


def request_for(query: dict) -> tuple[dict, dict]:
    """(body, headers) of one `/ask` request. `product_id` is left out when the query has none."""
    body = {"question": query["question"]}
    if query.get("product_id"):
        body["product_id"] = query["product_id"]
    headers = {"Content-Type": "application/json"}
    if query.get("stratum"):
        headers["X-Thesis-Stratum"] = query["stratum"]
    return body, headers


def http_post(
    url: str, body: dict, headers: dict, timeout: float
) -> tuple[int, dict | None]:
    """POST JSON. Returns (status, reply as JSON or None). A 4xx or 5xx is a status, not a raise."""
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except ValueError:
            return e.code, None


def replay(
    split: str,
    url: str,
    seed: int = 7,
    *,
    queries: list[dict] | None = None,
    post: Callable[[str, dict, dict, float], tuple[int, dict | None]] = http_post,
    pressure: Callable[[], int | None] = corpus_gate.memory_pressure_level,
    log: Callable[[str], None] = print,
    skip_no_product_id: bool = False,
) -> Counter:
    """Send every query once. Returns counts: `sent`, `http_<status>`, `cache_<value>`, `errors`.

    A 503 is a shed, counted as `http_503`, never an error. A connection failure is `errors`. Stops
    (raises `ReplayStopped`) when the pressure level is 4.

    With `skip_no_product_id` (the command sets it), a query whose `product_id` is empty or missing is
    dropped before the order is drawn, and `skipped_no_product_id` holds how many. It is off by default
    only so that a direct call keeps sending every query, as the tests of item 5.1 expect.
    """
    queries = refs.load_split(split) if queries is None else queries
    skipped = 0
    if skip_no_product_id:
        kept = [q for q in queries if q.get("product_id")]
        skipped = len(queries) - len(kept)
        queries = kept
    todo = order(queries, seed)
    endpoint = url.rstrip("/") + "/ask"
    counts: Counter = Counter()
    if skip_no_product_id:
        counts["skipped_no_product_id"] = skipped

    level = pressure()
    log(
        f"  memory pressure level: {level} (1 green, 2 warn, 4 critical); {len(todo)} queries"
        + (f", {skipped} skipped (no product_id)" if skip_no_product_id else "")
    )
    if level == PRESSURE_STOP:
        raise ReplayStopped(
            "memory pressure is critical (4); close apps and check again"
        )

    for i, query in enumerate(todo, 1):
        body, headers = request_for(query)
        try:
            status, reply = post(endpoint, body, headers, TIMEOUT_S)
        except OSError:
            counts["errors"] += 1
        else:
            counts[f"http_{status}"] += 1
            if status == 200 and reply is not None:
                counts[f"cache_{reply.get('cache')}"] += 1
        counts["sent"] += 1
        if i % PROGRESS_EVERY == 0 or i == len(todo):
            level = pressure()
            log(
                f"  {i}/{len(todo)} sent; pressure level {level}; {dict(sorted(counts.items()))}"
            )
            if level == PRESSURE_STOP:
                raise ReplayStopped(
                    f"memory pressure is critical (4) after {i} requests"
                )
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--split", choices=SPLITS, required=True)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)
    try:
        counts = replay(args.split, args.url, args.seed, skip_no_product_id=True)
    except ReplayStopped as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        return 1
    print(f"done: {dict(sorted(counts.items()))}")
    return 1 if counts["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
