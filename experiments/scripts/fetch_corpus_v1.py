"""Fetch a small product-catalog subset from Amazon-Reviews-2023 metadata (McAuley-Lab),
staged for `v1` corpus review -- this is NOT the frozen `data/v1/` corpus.

⚠️ Output goes to `data/v1-draft/`, deliberately separate from `data/v1/` (`data-card.md`
§1 `TODO(W8)`). The author's own plan (`the advisor review`
§4/§7) is to decide condition-tagging with the advisor before committing to the real `v1`
corpus -- this script produces a subset to LOOK AT before that decision, not the frozen
snapshot. Nothing here is hashed or versioned; `make gate-corpus` is not run against it.

⚠️ Source-data license is UNRESOLVED (`data-card.md` line 34: "redistribution TBD"). This
script does not commit anything to git by itself -- that is a separate, human decision once
the license question (see the licence checklist) is answered. Do not `git add`
`data/v1-draft/` until then.

Streams each category's metadata file (gzip'd JSONL, hosted at mcauleylab.ucsd.edu) and stops
once enough qualifying products are found per category, rather than downloading the full file
(each raw category file can be 100s of MB to several GB; only ~150-200 products are needed
total).

    python3 experiments/scripts/fetch_corpus_v1.py
    python3 experiments/scripts/fetch_corpus_v1.py --per-category 40 --out data/v1-draft

Field names verified against the dataset's own documentation (huggingface.co/datasets/
McAuley-Lab/Amazon-Reviews-2023, 2026-09-09): `title` (str), `categories` (list),
`details` (dict -- brand/material/size/etc, used here as `specs`), `parent_asin` (str,
the actual product id per the dataset's own guidance -- "the 'asin' in previous Amazon
datasets is actually parent ID").
"""

import argparse
import gzip
import json
import re
import ssl
import sys
import urllib.request
from pathlib import Path

# macOS python.org builds ship without the system CA bundle wired up by default (a well-known
# local-environment gap, not a network/script issue -- see "Install Certificates.command" in the
# Python.app folder). Using certifi's bundle directly makes this script work without requiring
# that one-time system fix; fall back to the platform default if certifi isn't installed.
try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

BASE_URL = "https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/raw/meta_categories"

# Raw Amazon-Reviews-2023 category slug -> this project's category label.
#
# ⚠️ There is no "Furniture" category in this dataset (verified 2026-09-09 against the
# project's own category listing) -- Home_and_Kitchen is the closest real category and is
# used here as a stand-in. If the author wants a cleaner electronics/furniture/kitchen split
# matching dev-v0's example categories, that needs either a keyword filter within
# Home_and_Kitchen or accepting the mapping below; flagging rather than silently deciding.
CATEGORIES = {
    "Electronics": "electronics",
    "Home_and_Kitchen": "home_kitchen",  # stand-in for "furniture" -- see note above
    "Appliances": "appliances",
    "Office_Products": "office",
    "Sports_and_Outdoors": "sports",
}

# Keys that are near-universal shipping/catalog boilerplate rather than product-specific
# content -- present on almost every listing regardless of how well-specced it actually is, so
# counting them toward "this product has enough detail" was letting logistics-only products
# through (verified 2026-09-09: an HDMI splitter had 6 `details` keys and every one of them
# was from this list; none said anything about ports or resolution).
GENERIC_DETAIL_KEYS = {
    "product dimensions", "item weight", "package dimensions", "item model number",
    "is discontinued by manufacturer", "date first available", "manufacturer", "asin",
    "customer reviews", "best sellers rank", "domestic shipping", "international shipping",
    "shipping weight", "package weight", "item package quantity", "unit count",
}

MIN_SUBSTANTIVE_DETAILS = 3  # `details` keys left AFTER removing GENERIC_DETAIL_KEYS
MIN_NARRATIVE_CHARS = 60     # ...or this many chars of combined features+description text
USER_AGENT = "Mozilla/5.0 (thesis-corpus-fetch/1.0)"


def slugify(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len].strip("-") or "item"


def _join_text(items, limit: int) -> str:
    text = " ".join(str(x).strip() for x in items if str(x).strip())
    return text[:limit].rstrip()


def _substantive_detail_count(details: dict) -> int:
    return sum(1 for k in details if str(k).strip().lower() not in GENERIC_DETAIL_KEYS)


def qualifies(record: dict) -> bool:
    title = (record.get("title") or "").strip()
    if not title:
        return False
    details = record.get("details") or {}
    substantive = _substantive_detail_count(details) if isinstance(details, dict) else 0
    narrative_len = len(_join_text(record.get("features") or [], 600)) + len(
        _join_text(record.get("description") or [], 600)
    )
    # Either path is enough: a product with several genuine (non-boilerplate) spec attributes,
    # OR one with a real sentence or two of feature/description text -- rejects the
    # logistics-only case without requiring every product to have both.
    return substantive >= MIN_SUBSTANTIVE_DETAILS or narrative_len >= MIN_NARRATIVE_CHARS


def to_project_schema(record: dict, category_label: str, doc_id: str) -> dict:
    # Matches rag/src/rag/ingest.py:product_to_text() -- reads record['title'],
    # record['category'], record['specs'] (dict, rendered as "- key: value" bullets).
    # doc_id carries the "product-" prefix the doc-id kind prefix/data-card.md §7 G4 require.
    #
    # `specs` folds in FOUR raw-metadata fields, not just `details`, because `details` alone
    # is frequently logistics metadata (dimensions, ship date, manufacturer) rather than the
    # functional information a spec question actually needs -- verified against real records
    # 2026-09-09 (see the qualifies() comment above). `features`/`description` carry that
    # missing content; folding them into `specs` (rather than changing ingest.py's rendering)
    # keeps this script self-contained and touches no pipeline source.
    details = record.get("details") or {}
    specs = {str(k): str(v) for k, v in list(details.items())[:12]}  # cap for chunk_size sanity

    features = record.get("features") or []
    if features:
        text = _join_text(features, limit=600)
        if text:
            specs["Features"] = text

    description = record.get("description") or []
    if description:
        text = _join_text(description, limit=600)
        if text:
            specs["Description"] = text

    price = record.get("price")
    if price not in (None, "", "None"):
        specs["Price (USD)"] = str(price)

    store = record.get("store")
    if store:
        specs["Brand/Store"] = str(store)

    return {
        "doc_id": doc_id,
        "title": record.get("title", "").strip(),
        "category": category_label,
        "specs": specs,
    }


def fetch_category(category_slug: str, category_label: str, n: int, timeout: int):
    url = f"{BASE_URL}/meta_{category_slug}.jsonl.gz"
    print(f"  streaming {url}", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    found = []
    seen_asins = set()
    with (
        urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as resp,
        gzip.GzipFile(fileobj=resp) as gz,
    ):
        for raw_line in gz:
            if len(found) >= n:
                break
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            asin = record.get("parent_asin") or ""
            if not asin or asin in seen_asins or not qualifies(record):
                continue
            seen_asins.add(asin)
            found.append(record)
    return found


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--per-category", type=int, default=35, help="products to keep per category")
    ap.add_argument("--out", default="data/v1-draft", help="staging output directory")
    ap.add_argument("--timeout", type=int, default=60, help="per-request socket timeout, seconds")
    ap.add_argument(
        "--keep-existing", action="store_true",
        help="skip clearing --out first (default clears it, since filenames embed a title slug "
             "and a stricter/looser qualifies() between runs picks different products, leaving "
             "stale files behind under old slugs rather than overwriting them)",
    )
    args = ap.parse_args()

    out_dir = Path(args.out)
    if out_dir.exists() and not args.keep_existing:
        stale = sorted(out_dir.glob("product-*.json"))
        for f in stale:
            f.unlink()
        if stale:
            print(f"cleared {len(stale)} file(s) from a previous run in {out_dir}/")
    out_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    summary = []
    for category_slug, category_label in CATEGORIES.items():
        print(f"[{category_label}] fetching up to {args.per_category} products...")
        try:
            records = fetch_category(category_slug, category_label, args.per_category, args.timeout)
        except Exception as e:  # noqa: BLE001 -- this is a best-effort fetch script, not gateway code
            print(f"[{category_label}] FAILED: {e}", file=sys.stderr)
            summary.append((category_label, 0))
            continue

        for i, record in enumerate(records, start=1):
            slug = slugify(record.get("title", "") or f"item-{i}")
            doc_id = f"product-{category_label}-{i:02d}-{slug}"[:80]
            product = to_project_schema(record, category_label, doc_id)
            (out_dir / f"{doc_id}.json").write_text(
                json.dumps(product, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        print(f"[{category_label}] wrote {len(records)} products")
        summary.append((category_label, len(records)))
        total += len(records)

    print("\n--- summary ---")
    for label, count in summary:
        print(f"  {label:<15} {count}")
    print(f"  {'TOTAL':<15} {total}")
    print(f"\nWritten to {out_dir}/ -- draft only, not the frozen data/v1/ corpus.")
    if total < 150:
        print(f"⚠️  {total} < 150 target — raise --per-category or check network/category names.")


if __name__ == "__main__":
    main()
