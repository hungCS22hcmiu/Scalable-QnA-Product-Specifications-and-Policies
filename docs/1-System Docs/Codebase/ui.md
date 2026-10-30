# `ui/` — the demo page

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `ui/src/main.jsx` (20 lines), `api.js` (42), `Counters.jsx`
(67), `pages/ProductList.jsx` (56), `pages/ProductChat.jsx` (177), `styles.css`. React 19, React Router 7, built with
Vite 6.

## 1. Purpose

A small page for the live demo: pick a product, ask questions about it, and watch the cache work. It serves **no
thesis claim**; it makes the claims visible. It is never on a measured path.

## 2. Boundaries

- **Node is a build-time tool only.** `make ui` builds `ui/dist/`, and the **gateway serves it** (`UI_DIR`), so no Node
  process competes for memory at demo time, and the page has the same origin as `/ask` (no CORS).
- It calls only `/products`, `/stats` and `/ask`.

## 3. Files

**`main.jsx`** sets up two routes with a **hash router**: `/` (the product list) and `/p/:docId` (one product's chat). A
hash route survives copy, paste and reload in many tabs, which is how the demo is driven. (The gateway also has a
fallback to `index.html`; with hash routes it is not needed.)

**`api.js`**, every call to the gateway in one place:
- `fetchProducts()` → `GET /products`; `fetchStats()` → `GET /stats`.
- `ask(question, productId)` → `POST /ask`, returning `{ ok, status, body, wallMs }`. **A 503 is not an error here**:
  `ok` and `status` are kept apart so a shed is shown as the gateway working. `wallMs` is measured in the browser and
  shown **beside** the gateway's own `latency_ms`; with many tabs, the gap between them is queueing.

**`Counters.jsx`** polls `/stats` **once a second** and shows **generations avoided**, the **hit rate**, and the
counts of requests, Tier-1 hits, Tier-2 hits, misses, sheds, coalesced requests and generations run. It polls the gateway rather than counting in the page, because the demo runs several
tabs and each tab would otherwise see only its own slice. The demo contract makes this sidebar required.

**`pages/ProductList.jsx`** lists the products from `/products`.

**`pages/ProductChat.jsx`** sends questions for one product and shows each answer with its `cache` outcome, its two
latencies and its sources. A 503 has its own state. **The trap, made visible:** if a source is a product document other
than the page's own, the answer was grounded on a product the user did not ask about.

## 4. Callers and callees

- **Built by** `make ui`; **served by** the gateway at `/` when `UI_DIR` points at `ui/dist/` (`make dev` sets it).
- **Calls** the gateway's `/products`, `/stats` and `/ask` ([`httpapi.md`](gateway/httpapi.md)).

## 5. Tests that pin it

None. It is a demo.

## 6. Silent failures to watch

- **The demo scripts still assume `dev-v0`.** `make demo` and `make demo-reset` are pinned to the retired corpus;
  `demo-reset` refuses while Redis holds `v1`, so it cannot wipe `v1` by accident. Moving the demo to `v1` is open
  (Phase 8).
- **An empty product list** means the corpus index changed shape, not that there are no products
  ([`catalog.md`](gateway/catalog.md)).

## 7. Commit

`29b24a6`.
