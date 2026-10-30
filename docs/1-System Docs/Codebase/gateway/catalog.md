# `gateway/internal/catalog/` — the product list for the demo page

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `catalog.go` (102 lines).

## 1. Purpose

It lists the products in the corpus so the demo page can show a product picker. It serves **none** of the
thesis claims. It is never called by `POST /ask`, holds no cache, and makes no decision.

## 2. Boundaries

- It reads `idx:corpus`, an index owned by the Python service (`rag/src/rag/store.py`). This read across the
  boundary is allowed only because it is demo-only and read-only.
- It is kept out of `cache/` on purpose: `cache/` owns the answer cache, and mixing a corpus reader into it
  would hide which index a function touches.
- It must never be reached from `/ask`, hold state, or decide anything (`docs/architecture.md` §2).

## 3. `catalog.go`

**Constants.** `corpusIndex = "idx:corpus"` and the tag value `product` mirror `store.py`'s schema. They are
copied, not shared, because the two services share no config. `maxProducts = 2000` bounds the search: the
frozen corpus has 152 products, so this is headroom, not paging.

**`Product`** is one **document**, not one chunk: `DocID`, `Title`, `Category`.

**`Products(ctx)`**:
1. Runs `FT.SEARCH idx:corpus "@kind:{product}"`, returning only `doc_id`, `title` and `category`. It never
   returns `text` or `vector`, which the list does not need.
2. Keeps the first chunk of each `doc_id`. Every chunk of a document carries the same metadata, so this
   removes duplicates rather than choosing.
3. Sorts by category, then title, so the page is stable across reloads.

## 4. Callers and callees

- **Built by** `cmd/gateway/main.go`: `handler.Catalog = catalog.New(rdb)`.
- **Called by** `httpapi`'s `GET /products` (`browse.go`), which returns an empty list when there is no catalog.

## 5. Tests that pin it

None. It is demo-only.

## 6. Silent failures to watch

- **A schema change in Python** (a renamed index, or no `kind` tag) gives an **empty list, not an error**, and
  **nothing checks it at start-up**: `main.go` only calls `catalog.New`. (The comment used to claim a start-up check;
  it was corrected on 30 Oct 2026.)

## 7. Commit

`29b24a6`. The package last changed in `21aaaec` (the docs consolidation, comments only).
