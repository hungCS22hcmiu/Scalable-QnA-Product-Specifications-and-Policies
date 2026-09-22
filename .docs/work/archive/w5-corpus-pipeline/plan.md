# Plan

- [x] Install prerequisites: Redis (via `redis-stack`, after the plain `redis` formula's default
      config turned out to reference module files it doesn't bundle), `pip3 install -e '.[dev]'`,
      pull `nomic-embed-text`, confirm 768-dim empirically.
- [x] Write ADR-003 (embedding model: `nomic-embed-text`, 768-dim) and ADR-014 (chunking:
      chunk_size=256, chunk_overlap=40, top_k=5) to `docs/decisions.md`.
- [x] Update `docs/experiment-protocol.md` §1's frozen-LLM-adjacent lines with the actual values.
- [x] Build `rag/src/rag/{__init__,config,chunkid,embedding,store,ingest,retrieve,cli}.py` +
      `rag/tests/test_chunkid.py` + `[project.scripts]` in `rag/pyproject.toml`.
- [x] Author `data/dev-v0/*.json` (40 products across 4 categories + 4 policy docs,
      self-authored; electronics=30-day return, furniture=14-day+15% restocking fee).
- [x] Run `python3 -m rag.ingest`; verified `FT.INFO idx:corpus` shows FLAT, dim 768, cosine, 0
      indexing errors.
- [x] Run `rag ask "…"` for 10 test queries; all returned correctly-shaped chunk IDs with sane
      top-1 matches, including correct category discrimination (furniture vs electronics policy).
- [x] `make verify` (lint + build + test) — all green, 5/5 pytest.
- [x] Appended `/log` entry to `docs/worklog/W05.md`, exit test marked PASS.

**Environment note (not in original plan):** Homebrew's plain `redis` 8.10 formula ships a config
that loads module files (`redisearch.so` etc.) it doesn't bundle — crashes on start. Switched to
`redis-stack-server` (official Redis Labs cask), which bundles them; works cleanly. Also found and
fixed a stray x86_64 numpy/Pillow in the system Framework Python's site-packages shadowing the
correct arm64 build pip installed to user-site — `pip3 install --user --force-reinstall` fixed it.
Neither was pre-existing user work; both were side effects of this session's own installs.
