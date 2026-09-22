# Spec

**Change.** Build the W6 slice of the platform: on the Python side, generation
(`rag/src/rag/generate.py`, Qwen 3.5 2B via Ollama, `think: false`) and a gRPC server
(`rag/src/rag/server.py`) exposing `Answer` + `Retrieve`; on the Go side, the gateway skeleton —
`POST /ask` (`gateway/internal/httpapi`), the Tier-1 exact-match cache
(`gateway/internal/cache`), and the pooled gRPC client (`gateway/internal/ragclient`) — so a
question round-trips end-to-end with source attribution.

**Serves:** `docs/time_line.md` Phase 1, Week 6 row ("RAG end-to-end + gateway skeleton").

**Acceptance** (verbatim Done-when, `time_line.md` W6):
- End-to-end answer with source attribution over gRPC; p50 miss latency recorded.
- Same question twice: first hits Python, second returns from Tier 1 in <10 ms.

**Out of scope** (later weeks / other tasks per `docs/design/architecture.md` §5 build order and
`Final_Proposal.md` §12):
- Tier-2 semantic cache, `gateway/internal/embed` — **W7**.
- Source-overlap rule, `gateway/internal/reuse` — **W12–W15**.
- Dependency map / invalidation, `gateway/internal/deps` — **W9–W11**.
- Admission control / backpressure, `gateway/internal/telemetry` — **W16–W17**.
- Bypass classifier logic beyond the existing stub contract (§G) — demo stub only, ADR-018.
- SSE streaming — dropped, ADR-016.
- k6 / off-box load harness — **W8**.
- Any change to `contracts/rag/v1/rag.proto` — it's already scaffolded and generates cleanly on
  both sides (`make proto` W5); this task consumes the existing contract, does not edit it.
