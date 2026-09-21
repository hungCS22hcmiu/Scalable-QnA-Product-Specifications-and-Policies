# Architecture guardrails (AI-facing)

Boundaries that must not be crossed. The structural authority is
[`docs/design/architecture.md`](../../docs/design/architecture.md); this file is the short agent-facing
form of the invariants that break something real when violated.

---

## Layering

```
httpapi  →  admission  →  cache  →  reuse  →  ragclient  →  (gRPC seam)  →  rag/
                            ↓         ↑
                          deps    embed
                       telemetry (cross-cutting, imported by all, imports none)
```

**Dependencies point right and down. Never the reverse.** A package importing something to its left is
a layering violation, and a cycle is a defect regardless of whether Go's compiler accepts it.

## Package invariants

| Package | Must | Must never |
| :--- | :--- | :--- |
| `reuse/` | Take two chunk-ID sets + a similarity score, return a decision | Touch Redis, gRPC, or HTTP. It must stay unit-testable with no infrastructure — this is what keeps C1 falsifiable in isolation |
| `deps/` | Own the **only** writer to the no-eviction region, serialized through one goroutine | Be written from a request goroutine, or hold a lock across a Redis round-trip |
| `admission/` | Be the **sole** place a generation permit is acquired or released | Be bypassed by any miss path — one chokepoint or the memory guarantee is void |
| `cache/` | Own key normalization (ADR-015) and both tiers | Make a reuse decision — that belongs to `reuse/` |
| `ragclient/` | Own the pooled gRPC channel and the epoch stamp | Be constructed per request |
| `telemetry/` | Be importable by everything | Import anything from this repo — it must have no repo dependencies |

## The seam

- **gRPC only.** Nothing under `gateway/internal/` shells out to Python, and `rag/` never calls back
  into the gateway.
- `contracts/rag/v1/rag.proto` is the single definition. Both sides generate from it (`make proto`).
- The epoch travels **with** retrieval results and is compared at write-back. Dropping it reintroduces
  the resurrection race (rules #6).

## Concurrency

- Read path: **wait-free**. Readers dereference an immutable snapshot; no reader ever blocks behind an
  invalidation.
- Write path: one goroutine, fed by a buffered channel. Writer-writer races eliminated by construction,
  not by locking discipline.
- Purges run **off** the critical path, including the Redis fan-out across both tiers.

## Experiments

- `experiments/results/{run_id}/raw/` is write-once. `figures/` is disposable and gitignored.
- Every run writes a complete `manifest.yaml` first; a run without one is invalid, not fixable.
- Measurement code is not application code — it may not import `gateway/internal/`.

## When a guardrail and a deadline conflict

Say so and stop. Every invariant above exists because violating it fails **silently** — the thesis
does not get a compiler error, it gets a number that is quietly wrong three months later.
