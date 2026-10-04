# data/

Corpus snapshots. **Contents are gitignored** — the Amazon-derived subset may not be
redistributable (`docs/data-card.md` §1). Commit a download+build script and a
`.sha256` manifest, never the raw data.

| Dir | Built | Status |
| :--- | :--- | :--- |
| `dev-v0/` | W5 | **Throwaway.** Makes the pipeline run. Not hashed, not versioned, **not citable in any result.** |
| `v1/` | W8 | **Frozen experimental corpus.** Hashed, versioned, gated by `data-card.md` §7. |

See `docs/data-card.md` for why there are two.
