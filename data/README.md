# data/

Corpus snapshots. **The Amazon-derived contents are gitignored** — the PQA subset may not be
redistributable (`docs/data-card.md` §1). Commit a download+build script and a
`.sha256` manifest, never the raw data. **Exceptions, tracked:** `dev-v0/`, `policies-v1/` (the
author-owned policy documents, item 3.3, ADR-012) and the hash manifests `pqa-manifest.json`,
`pqa-selection.json` (no PQA text).

| Dir | Built | Status |
| :--- | :--- | :--- |
| `dev-v0/` | W5 | **Throwaway.** Makes the pipeline run. Not hashed, not versioned, **not citable in any result.** |
| `policies-v1/` | item 3.3 | **Tracked source of v1's 12 policy documents**, not a dataset version: 3.6 copies it into `v1/`. Checked by `make policy-check`. |
| `v1/` | W8 | **Frozen experimental corpus.** Hashed, versioned, gated by `data-card.md` §7. |

See `docs/data-card.md` for why there are two.
