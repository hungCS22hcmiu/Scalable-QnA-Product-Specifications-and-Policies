"""Document metadata for the scope arm (item 6.0a, ADR-030): `make docmeta`.

One step, run once per corpus, before the gateway starts. It reads data/{DATASET_VERSION}/*.json and
writes one Redis hash per document, `docmeta:{doc_id}` (interfaces.md C):

  category     every document (products and policies)
  title_vec    products only: the title embedded with the `search_document:` prefix, float32
               little-endian, the same encoding as `t2:*`
  bound_words  products only: a JSON list of the words that belong to this product alone

The gateway reads these hashes at start (cache.Store.LoadDocMeta). Its scope test (reuse/scope.go)
asks whether an answer names the product, so it needs the bound words; its projection needs the
title vector. Both use THIS tokenizer, which is pinned by contracts/scope/cases.json and read by a
Go test and a pytest, because a difference between the two languages is silent (a bound word is
never found, and an answer that names its product is stored for every product).

A product-bound word is a token of the product's title and spec values that is in no policy document
of its category and occurs in at most `cut` (10 %) of the products. The cut is pinned, never swept.

Only the embedding model is loaded. Check `sysctl kern.memorystatus_vm_pressure_level` first.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path

from rag import config

KEY_PREFIX = "docmeta:"
CUT = 0.10  # pinned (design.md 3.3 D); the share of products a word may occur in and still be bound

_SPLIT = re.compile(r"[^A-Za-z0-9]+")


def scope_tokens(text: str) -> set[str]:
    """ASCII letters and digits make tokens; the case of an ASCII letter is folded; every other
    character (punctuation, spaces, accents, letters of other scripts) separates tokens; a token of
    under two characters is dropped.

    The same function as reuse.ScopeTokens in Go; contracts/scope/cases.json pins both. Splitting
    on the ASCII classes first, and folding case after, keeps the two languages equal on non-ASCII
    text, where `str.lower()` and Go's case mapping can differ.
    """
    return {t.lower() for t in _SPLIT.split(text) if len(t) >= 2}


def product_text(record: dict) -> str:
    """The text a product's bound words come from: its title and its spec VALUES, never the keys."""
    parts = [record["title"]]
    for value in record["specs"].values():
        parts.append(value if isinstance(value, str) else json.dumps(value))
    return "\n".join(parts)


def policy_text(record: dict) -> str:
    return f"{record['title']}\n{record['text']}"


def bound_words(
    product_tokens: Iterable[str],
    category_policy_tokens: set[str],
    df: dict[str, int],
    n_products: int,
    cut: float = CUT,
) -> list[str]:
    """The words of one product that name it: in no policy document of its category, and in at
    most `cut` of the products. `df[token]` is how many products' text holds the token. Sorted."""
    return sorted(
        t
        for t in set(product_tokens)
        if t not in category_policy_tokens and df.get(t, 0) / n_products <= cut
    )


def build(corpus_dir: Path | None = None) -> list[dict]:
    """One row per document, in doc_id order, with no model needed.

    `{"doc_id", "category", "kind"}`, and for a product also `"title"` (the text `write` embeds) and
    `"bound_words"`. Raises on a document with no `category` key.
    """
    from rag import ingest

    records = ingest.load_records(Path(corpus_dir) if corpus_dir else ingest.DATA_DIR)
    for r in records:
        if "category" not in r:
            raise ValueError(f"{r['doc_id']}: no category")
    products = [r for r in records if ingest.record_kind(r["doc_id"]) == "product"]
    policies = [r for r in records if ingest.record_kind(r["doc_id"]) == "policy"]

    policy_tokens: dict[str, set[str]] = {}
    for p in policies:
        policy_tokens.setdefault(p["category"], set()).update(scope_tokens(policy_text(p)))

    product_tokens = {p["doc_id"]: scope_tokens(product_text(p)) for p in products}
    df: Counter = Counter()
    for tokens in product_tokens.values():
        df.update(tokens)

    rows = []
    for r in records:
        row = {
            "doc_id": r["doc_id"],
            "category": r["category"],
            "kind": ingest.record_kind(r["doc_id"]),
        }
        if row["kind"] == "product":
            row["title"] = r["title"]
            row["bound_words"] = bound_words(
                product_tokens[r["doc_id"]],
                policy_tokens.get(r["category"], set()),
                df,
                len(products),
            )
        rows.append(row)
    return rows


def encode_vector(vec: list[float]) -> bytes:
    """float32 little-endian, as the gateway writes `t2:*` embeddings."""
    import struct

    return struct.pack(f"<{len(vec)}f", *vec)


def embed_titles(titles: list[str]) -> list[list[float]]:
    """The titles through the pinned embedding model, with the `search_document:` prefix."""
    from rag.embedding import OllamaEmbedding

    return OllamaEmbedding()._get_text_embeddings(titles)


def write(
    client, rows: list[dict], embed: Callable[[list[str]], list[list[float]]] = embed_titles
) -> dict:
    """Write `docmeta:{doc_id}` for every row, and remove a `docmeta:*` key that no row names.

    Returns the counts the step reports. Raises if an embedding does not have the pinned dimension.
    """
    products = [r for r in rows if r["kind"] == "product"]
    vectors = embed([r["title"] for r in products]) if products else []
    if len(vectors) != len(products):
        raise ValueError(f"{len(products)} titles but {len(vectors)} vectors")
    by_doc = {}
    for r, vec in zip(products, vectors, strict=True):
        if len(vec) != config.EMBEDDING_DIM:
            raise ValueError(
                f"{r['doc_id']}: title vector has {len(vec)} dims, not {config.EMBEDDING_DIM}"
            )
        by_doc[r["doc_id"]] = vec

    wanted = {f"{KEY_PREFIX}{r['doc_id']}" for r in rows}
    pipe = client.pipeline()
    for r in rows:
        key = f"{KEY_PREFIX}{r['doc_id']}"
        mapping = {"category": r["category"]}
        if r["kind"] == "product":
            mapping["title_vec"] = encode_vector(by_doc[r["doc_id"]])
            mapping["bound_words"] = json.dumps(r["bound_words"])
        pipe.delete(key)  # a rewrite never leaves a field of the old version behind
        pipe.hset(key, mapping=mapping)
    stale = [
        k for k in client.scan_iter(match=f"{KEY_PREFIX}*", count=500) if k.decode() not in wanted
    ]
    for k in stale:
        pipe.delete(k)
    pipe.execute()
    return {
        "docs": len(rows),
        "categories": sum(1 for r in rows if r["category"]),
        "title_vectors": len(by_doc),
        "products": len(products),
        "stale_removed": len(stale),
    }


def main() -> int:
    from rag import store

    rows = build()
    counts = write(store.get_redis_client(), rows)
    print(
        f"docmeta: {counts['categories']} categories for {counts['docs']} documents, "
        f"{counts['title_vectors']} title vectors for {counts['products']} products, "
        f"{counts['stale_removed']} stale keys removed"
    )
    bound = [len(r["bound_words"]) for r in rows if r["kind"] == "product"]
    if bound:
        mean = sum(bound) / len(bound)
        print(
            f"docmeta: bound words per product: min {min(bound)}, max {max(bound)}, mean {mean:.1f}"
        )
    ok = counts["categories"] == counts["docs"] and counts["title_vectors"] == counts["products"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
