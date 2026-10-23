# The pin survives `assemble` — g1-finding, Block C step 17

Counts and booleans only; no file name. Run on 2026-10-23 with no Redis and no Ollama.

| Check | Result |
| :--- | :--- |
| Files the snapshot digest covers now (164 corpus files + 3 workload files) | 167 |
| `corpus_gate.snapshot_digest` over them equals `ACCEPTED_SNAPSHOT_DIGEST` (`a5708fefa62c…`) | **yes** |
| `freeze_corpus.assemble` into an empty scratch directory (152 products, 12 policies) | 164 files copied |
| Same file names and same sha256 bytes as `data/v1/` | **yes** |

Why two checks: the digest hashes repo-relative paths, so a scratch directory outside the repository cannot be hashed to
the same value. Equal names, equal bytes and a digest that equals the pin now, together mean a rebuilt `data/v1/` hashes to the
pin. The allowance in the gate and in `freeze` therefore does not break when `data/v1/` is rebuilt.
