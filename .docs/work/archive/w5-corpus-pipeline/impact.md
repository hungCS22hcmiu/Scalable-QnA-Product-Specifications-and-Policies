# Impact analysis

**Packages touched:** `rag/` only (new package contents under `rag/src/rag/`, `rag/tests/`). No
`gateway/` changes — correct per `docs/design/architecture.md`'s W5/W6 build-order split.

**Touches a frozen artifact — yes, two:** ADR-003 (embedding model) and ADR-014 (chunking config),
both currently `Open`, decide-by W5. This task flips both to `Decided`.

**Invalidates:** none — no experiment runs exist yet.

**Reinstates anything from `Final_Proposal.md` §12's do-not-reinstate list?** No.

**Adds a dependency?** No new top-level dependency. `embedding.py` calls Ollama's `/api/embed` via
`httpx` (already declared) rather than adding the `llama-index-embeddings-ollama` package.
`tiktoken` arrives transitively via `llama-index-core` (confirmed in the `pip install -e '.[dev]'`
output) — not a new top-level dependency requiring separate sign-off.

**Changes a contract (`interfaces.md` surfaces)?** No wire-shape change. The Redis schema built
here (`idx:corpus`, `corpus:*`) is the RAG service's own corpus index, distinct from and not
touching `interfaces.md` §D's `idx:cache`/`t1:*`/`t2:*` (the gateway's answer cache, W6/W7). No
contract phase required.

**Changes what or how anything is measured?** `experiment-protocol.md` §1's "Frozen for the whole
study" list gains the actual embedding model/dim and chunking values (currently cites the ADRs
without values, since they were Open). **Experiment phase: required.**

**Implementation phase:** required — this task lands real source code (`rag/src/rag/*.py`,
`rag/tests/*`, `data/dev-v0/*.json`).
