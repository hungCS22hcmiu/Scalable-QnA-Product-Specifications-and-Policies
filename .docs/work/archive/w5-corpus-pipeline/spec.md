# Task: W5 corpus + retrieval pipeline (tasks 2-7)

**One sentence:** Freeze the embedding model (ADR-003) and chunking config (ADR-014), build
`rag/src/rag/{chunkid,config,embedding,store,ingest,retrieve,cli}.py`, author the `dev-v0` corpus,
ingest it into Redis, and verify `rag ask "…"` returns top-k chunks with chunk IDs for 10 queries.

**Serves:** `docs/time_line.md` W5, blocking gate 2 (freeze ADR-003 + ADR-014 before ingestion) and
the week's exit test (`rag ask` returning chunk IDs for 10 test queries).

**Acceptance:** ADR-003 and ADR-014 flipped from Open to Decided. `make ingest` succeeds against a
real `dev-v0` corpus. `rag ask "<question>"` (installed console script) returns ranked chunk IDs
shaped `{doc_id}#chunk-{ordinal}` for 10 test queries. `redis-cli FT.INFO idx:corpus` confirms the
vector field is `FLAT`. `make lint` and `make test` pass repo-wide.

**Out of scope:** anything gateway-side (W6+), gRPC code generation (W6+), the `v1` corpus (W8),
generation/answering (W6 — this task is retrieval-only, matching `docs/design/architecture.md`'s
W5 build-order: `rag/src/rag/{ingest,retrieve,chunkid}.py`).

**Context:** follows directly from the `w5-feasibility-spike` task (ADR-021, ADR-017 frozen). Full
plan at `/Users/hung/.claude/plans/final-decision-change-from-snazzy-journal.md`.
