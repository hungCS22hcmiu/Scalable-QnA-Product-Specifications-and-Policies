# System Architecture & Repository Structure

**Status:** authority for folder structure and module boundaries · **Created:** 2026-08-09
**Companion to:** `Final_Proposal.md` §6 (architecture), `interfaces.md` (frozen contracts),
`time_line.md` (build order)

This document is the **baseline** the codebase is built against. `Final_Proposal.md` §6 says *what* the
system does; this says *where each part lives and what it may depend on*. Where they disagree, the
proposal governs the design and this governs the layout.

---

## 1. Canonical tree

Every directory is annotated with the document that governs its contents. **A directory not listed here
should not exist**; a directory listed here that is missing has simply not been built yet (see §5).

```
thesis/
├── CLAUDE.md                     agent instructions
├── README.md                     landing page + document index
├── Makefile                      the single command surface — see §4
│
├── docs/                         HUMAN-AUTHORED source of truth (frozen)
│   ├── Final_Proposal.md           scope, claims, RQs, evaluation
│   ├── design/architecture.md      ← this file
│   ├── interfaces.md               frozen wire contracts (v0.3)
│   ├── experiment-protocol.md      measurement spec, run manifests, statistics
│   ├── decisions.md                ADR log (ADR-001…020)
│   ├── data-card.md                corpus provenance, licensing, the W8 gate
│   ├── time_line.md                week plan, exit tests, risk register
│   ├── defense_demo.md             demo script + debug-UI contract
│   ├── worklog/W05.md … W22.md     weekly work log
│   └── archive/                    superseded documents, retained
│
├── .docs/                        AI WORKFLOW trail — see .docs/README.md
│   ├── ai/{rules,architecture-guardrails,review-checklist,frozen-values}
│   └── work/<task-slug>/          spec · impact · plan · review · approvals
│
├── .claude/                      workflow automation (hooks, commands, agents)
│
├── contracts/
│   └── rag/v1/rag.proto          THE seam definition        → interfaces.md §B
│
├── gateway/                      Go — THE CONTRIBUTION
│   ├── go.mod
│   ├── cmd/gateway/main.go         wiring + config only, no logic
│   └── internal/
│       ├── httpapi/                POST /ask, 503 shedding  → interfaces.md §A
│       ├── cache/                  tier1, tier2, key norm   → interfaces.md §D, ADR-015
│       ├── reuse/                  overlap rule + cascade   → proposal §5 C1   [C1]
│       ├── deps/                   dependency map, COW, writer goroutine
│       │                                                    → interfaces.md §E  [C2]
│       ├── admission/              permit pool, queue, shed → proposal §6.1
│       ├── ragclient/              pooled gRPC + epoch      → interfaces.md §B
│       ├── embed/                  embedding endpoint       → interfaces.md §F
│       └── telemetry/              counters, latency split  → experiment-protocol.md §4
│
├── rag/                          Python — INFRASTRUCTURE (not a contribution)
│   ├── pyproject.toml
│   └── src/rag/
│       ├── server.py               gRPC: Answer + Retrieve
│       ├── ingest.py               chunk → embed → index    → data-card.md
│       ├── retrieve.py             top-k, FLAT, frozen
│       ├── generate.py             Ollama call
│       └── chunkid.py              {doc_id}#chunk-{ordinal} → interfaces.md §C
│
├── experiments/
│   ├── scripts/                    workload gen, replay, judge, figures
│   ├── k6/                         load scenarios (W8+)
│   └── results/{run_id}/
│       ├── manifest.yaml           required; a run without one is invalid
│       ├── raw/                    WRITE-ONCE                → experiment-protocol.md §3
│       └── figures/                regenerated, gitignored
│
└── data/
    ├── dev-v0/                     W5 throwaway, not citable → ADR-020
    └── v1/                         W8 frozen experimental    → data-card.md §7
```

## 2. Layering

```
httpapi → admission → cache → reuse → ragclient → ⟦gRPC seam⟧ → rag/
                        ↓        ↑
                      deps     embed
              telemetry  (imported by all, imports none)
```

**Dependencies point right and down.** An import pointing left is a layering violation; a cycle is a
defect even if the compiler accepts it.

| Package | Owns | Must never |
| :--- | :--- | :--- |
| `reuse/` | The C1 decision: two chunk-ID sets + similarity → reuse or not | Touch Redis, gRPC, or HTTP. It stays infrastructure-free so C1 is falsifiable in isolation |
| `deps/` | The **only** writer to the no-eviction region, serialized through one goroutine | Be written from a request goroutine; hold a lock across a Redis round-trip |
| `admission/` | The **sole** acquire/release point for a generation permit | Be bypassed by any miss path — one chokepoint or the memory guarantee is void |
| `cache/` | Key normalization (ADR-015) and both tiers | Make a reuse decision — that is `reuse/` |
| `ragclient/` | Pooled gRPC channel; stamps `dataset_epoch` at retrieval | Be constructed per request |
| `telemetry/` | Counters and latency decomposition | Import anything from this repo |

## 3. Request paths

| Path | Flow | Cost |
| :--- | :--- | :--- |
| **Tier-1 hit** | `httpapi → cache.tier1` (hash lookup) | ~ms, no embedding, no search |
| **Tier-2 hit (short-circuit)** | `→ embed → cache.tier2` kNN `→ reuse` (similarity resolves it) | ~tens of ms |
| **Tier-2 hit (cascade band)** | `→ ragclient.Retrieve → reuse` (overlap ∧ similarity) | + one gRPC round-trip; **reported separately** (proposal §9.2) |
| **Miss** | `→ admission.Acquire → ragclient.Answer → LLM →` write back **both** tiers + `t1_key` + epoch | seconds |
| **Shed** | permit unavailable inside budget → `503 busy, retry` | counted as graceful degradation, never as served load |
| **Invalidation** | edit → channel → single writer → COW swap → Redis purge (both tiers), **off** the critical path | — |

**Where the contributions live:** C1 → `reuse/` · C2 → `deps/` (+ the epoch check in `ragclient/` and
write-back) · resource governance → `admission/` · the measurement protocol → `experiments/`.

## 4. Command surface

Use `make`; do not invent ad-hoc invocations. Targets: `spike` · `ingest` · `dev` · `ask` ·
`demo-reset` (promised in `defense_demo.md` §4) · `proto` · `test` · `lint` · `verify` · `figures` ·
`check`.

## 5. Build order

The tree above is the target. What is real at any moment follows `time_line.md`:

| Weeks | Lands |
| :--- | :--- |
| W5 | `rag/src/rag/{ingest,retrieve,chunkid}.py`, `data/dev-v0/`, the frozen envelope |
| W6 | `rag/src/rag/{generate,server}.py`, `contracts/`, `gateway/{cmd,internal/{httpapi,cache,ragclient}}` |
| W7 | `gateway/internal/{embed,reuse}` (fixed τ), first `experiments/scripts/` |
| W8 | `data/v1/`, `experiments/k6/` |
| W9–W11 | `gateway/internal/deps/` |
| W12–W15 | `reuse/` overlap rule + cascade, judge harness |
| W16–W17 | `gateway/internal/{admission,telemetry}` |

## 6. Invariants that fail silently

Each of these produces **no error** when violated — which is why they are invariants rather than
guidelines. Full statements in `.docs/ai/rules.md`.

1. Frozen values change only via ADR, and the ADR states **which prior runs it invalidates**.
2. Dependency state lives under `noeviction`; only cache entries are LRU.
3. `t1_key` is written with every Tier-2 record, or Tier-1 survives invalidation.
4. `dataset_epoch` is stamped at retrieval and **compared at write-back**.
5. `experiments/results/*/raw/` is write-once.
6. The vector index is **FLAT**, frozen study-wide — no mid-study HNSW.
7. No ML runtime on the hit path; embeddings come from Ollama.
