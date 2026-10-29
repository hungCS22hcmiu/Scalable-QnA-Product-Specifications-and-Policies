# data/

Corpus snapshots. **The Amazon-derived contents are gitignored** — the PQA subset may not be
redistributable (`docs/data-card.md` §1). Commit a download+build script and a
`.sha256` manifest, never the raw data. **Exceptions, tracked:** `dev-v0/`, `policies-v1/` (the
author-owned policy documents, item 3.3, ADR-012) and the hash manifests and records
`pqa-manifest.json`, `pqa-selection.json`, `v1-freeze.json`, `workload-manifest.json` and
`update-set-manifest.json` (no PQA text).

**Work runs on `v1`.** The author retired `dev-v0` on 2026-10-29 (item 4.4): Redis holds `v1`, and
`make ingest` reads `v1` unless `DATASET_VERSION` says otherwise.

| Dir or file | Built | Status |
| :--- | :--- | :--- |
| `dev-v0/` | W5 | **Retired 2026-10-29.** Kept for history, and because `make demo` and `make demo-reset` still use it (a follow-up). **Not citable in any result.** |
| `policies-v1/` | item 3.3 | **Tracked source of v1's 12 policy documents**, not a dataset version: 3.6 copies it into `v1/`. Checked by `make policy-check`. |
| `v1/` | item 3.6 | **Frozen experimental corpus.** Hashed, versioned, gated by `data-card.md` §7. Checked by `make corpus-verify` (files) and `make corpus-index-check` (Redis). |
| `workload-v1*.json` | item 3.4 | The workload and its validation/test split. **Gitignored**; `workload-manifest.json` holds their hashes. |
| `update-set-v1.json` | item 4.4 | The 20 labelled edits (10 `substantive`, 10 `cosmetic`, `data-card.md` §5). **Gitignored**; `update-set-manifest.json` holds its hash. Checked by `make update-set-verify`. |
| `dataset-epoch` | item 4.2 | The dataset epoch file (ADR-008). **Gitignored**, local state. `make ingest` and every edit advance it. |

See `docs/data-card.md` for why there are two corpora.
