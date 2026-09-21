"""Ad-hoc admission-control load burst -- NOT a measurement script, NOT citable. Fires a large,
mixed batch of concurrent requests (fresh questions + exact duplicates + paraphrases) at a running
gateway to observe, empirically, whether the permit pool / queue / shed / coalescing mechanism
behaves as designed under real concurrent load. For a citable number use `make measure` /
`experiments/k6/`; this is a quick, throwaway stress probe.

Usage:
    python3 experiments/scripts/load_burst.py [--total 150] [--concurrency 25] [--url http://localhost:8080/ask]

Respects CLAUDE.md's standing rule: check memory pressure before running, every time.
"""

import argparse
import json
import random
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

CATEGORIES = ["laptops", "headphones", "kitchen", "furniture"]
PRODUCTS_PER_CATEGORY = 10

SPEC_TEMPLATES = {
    "laptops": [
        "how much RAM does this laptop have",
        "what is the battery life",
        "how much does this laptop weigh",
        "what is the storage capacity",
    ],
    "headphones": [
        "how long does the battery last",
        "is this noise cancelling",
        "what is the connectivity type",
        "how much does this weigh",
    ],
    "kitchen": [
        "how many watts does this use",
        "what is the capacity",
        "what type of appliance is this",
    ],
    "furniture": [
        "what material is this made of",
        "what are the dimensions",
        "how many seats does it have",
    ],
}

# A few hand-written paraphrases per template, so a fraction of the burst exercises Tier 2
# rather than either exact-repeat (Tier 1) or a genuinely novel question (a fresh MISS).
PARAPHRASES = {
    "how much RAM does this laptop have": ["what's the memory size on this laptop", "how much memory does it come with"],
    "how long does the battery last": ["what's the battery life like", "battery life in hours"],
    "what material is this made of": ["what's it made from", "what is the build material"],
    "how many watts does this use": ["what is the power rating", "how much power does it draw"],
}


def build_question_pool(total: int, seed: int) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    fresh: list[tuple[str, str]] = []
    for cat in CATEGORIES:
        for i in range(1, PRODUCTS_PER_CATEGORY + 1):
            product_id = f"product-{cat}-{i:02d}"
            for template in SPEC_TEMPLATES[cat]:
                fresh.append((template, product_id))
    rng.shuffle(fresh)

    pool: list[tuple[str, str]] = []
    n_fresh = int(total * 0.55)
    n_dupe = int(total * 0.25)
    n_para = total - n_fresh - n_dupe

    chosen_fresh = fresh[:n_fresh]
    pool.extend(chosen_fresh)

    # Exact duplicates -- tests singleflight coalescing when they land concurrently, and Tier-1
    # promotion/reuse when they land after the first has already completed.
    for _ in range(n_dupe):
        pool.append(rng.choice(chosen_fresh))

    # Paraphrases -- tests Tier-2 reuse under load. Falls back to a random fresh pair if the
    # chosen template has no hand-written paraphrase.
    paraphrasable = [(q, p) for q, p in chosen_fresh if q in PARAPHRASES]
    for _ in range(n_para):
        if paraphrasable:
            q, p = rng.choice(paraphrasable)
            pool.append((rng.choice(PARAPHRASES[q]), p))
        else:
            pool.append(rng.choice(chosen_fresh))

    rng.shuffle(pool)
    return pool


def fire(url: str, question: str, product_id: str) -> dict:
    body = json.dumps({"question": question, "product_id": product_id}).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            wall_ms = (time.monotonic() - t0) * 1000
            payload = json.loads(resp.read())
            return {"status": resp.status, "wall_ms": wall_ms, "body": payload}
    except urllib.error.HTTPError as e:
        wall_ms = (time.monotonic() - t0) * 1000
        try:
            payload = json.loads(e.read())
        except Exception:  # noqa: BLE001 -- best-effort body parse, any failure means "no body"
            payload = {}
        return {"status": e.code, "wall_ms": wall_ms, "body": payload}
    except Exception as e:  # noqa: BLE001 -- record any client-side failure, never crash the burst
        wall_ms = (time.monotonic() - t0) * 1000
        return {"status": 0, "wall_ms": wall_ms, "body": {}, "error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--total", type=int, default=150)
    ap.add_argument("--concurrency", type=int, default=25)
    ap.add_argument("--url", default="http://localhost:8080/ask")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    pool = build_question_pool(args.total, args.seed)
    print(f"== load burst: {len(pool)} requests, concurrency={args.concurrency} ==")
    print(f"   distinct (question, product_id) pairs: {len(set(pool))}")

    results = []
    t_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = [ex.submit(fire, args.url, q, p) for q, p in pool]
        for fut in as_completed(futures):
            results.append(fut.result())
    wall_total = time.monotonic() - t_start

    status_counts = Counter(r["status"] for r in results)
    cache_counts = Counter(r["body"].get("cache", "?") for r in results if r["status"] == 200)

    miss_lat = [r["wall_ms"] for r in results if r["status"] == 200 and r["body"].get("cache") == "MISS"]
    hit_lat = [
        r["wall_ms"]
        for r in results
        if r["status"] == 200 and r["body"].get("cache") in ("TIER1_HIT", "TIER2_HIT")
    ]

    def pct(xs, p):
        if not xs:
            return None
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(len(xs) * p))]

    print(f"\n== results, wall clock: {wall_total:.1f}s ==")
    print(f"status: {dict(status_counts)}")
    print(f"cache (of 200s): {dict(cache_counts)}")
    print(
        f"MISS latency (ms): n={len(miss_lat)} "
        f"p50={pct(miss_lat, .5)} p95={pct(miss_lat, .95)} max={max(miss_lat) if miss_lat else None}"
    )
    print(
        f"HIT  latency (ms): n={len(hit_lat)} "
        f"p50={pct(hit_lat, .5)} p95={pct(hit_lat, .95)} max={max(hit_lat) if hit_lat else None}"
    )

    sheds = [r for r in results if r["status"] == 503]
    if sheds:
        reasons = Counter(r["body"].get("reason", "?") for r in sheds)
        print(f"\n503 shed reasons: {dict(reasons)}")

    errors = [r for r in results if r["status"] == 0]
    if errors:
        print(f"\n⚠️ {len(errors)} requests errored client-side (not a shed, not a 200):")
        for r in errors[:5]:
            print(f"   {r.get('error')}")

    print(
        "\nNot citable -- functional/throwaway probe only. For a real number use `make measure`."
    )


if __name__ == "__main__":
    main()
