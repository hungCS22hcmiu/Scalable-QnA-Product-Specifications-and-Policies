# System Architecture & Repository Structure

**Status:** authority for folder structure and module boundaries · **Created:** 2026-08-09 ·
**Revised:** 2026-10-07
**Companion to:** `Final_Proposal.md` §6 (architecture), `contracts/interfaces.md` (frozen
contracts), `decisions.md` (the decision log), `super-plan.md` (build order)

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
├── docs/                         SOURCE OF TRUTH — flattened 2026-09-22
│   ├── super-plan.md               the eight phases and their exit criteria
│   ├── decisions.md                the decision log — an ADR-NNN anywhere in the repo means an entry here
│   ├── Final_Proposal.md           scope, claims, RQs, evaluation  (gitignored)
│   ├── architecture.md             ← this file
│   ├── data-card.md                corpus provenance, licensing, the G1–G5 gate
│   ├── contracts/
│   │   ├── interfaces.md           frozen wire contracts; the version is in its header
│   │   └── requirements.md         FR / NFR / RR — skeleton, unfilled
│   ├── work/<YYYY-MM-DD>-<slug>/   spec · impact · design · review · plan · approvals
│   └── learning/                   submitted prose + study notes  (gitignored)
│
├── .claude/                      workflow automation (hooks, commands, agents)
│
├── contracts/
│   ├── rag/v1/rag.proto          THE seam definition        → contracts/interfaces.md §B
│   └── normalize/cases.json      golden vectors for key normalisation, read by the Go cache tests
│                                 and by the Python corpus gate  → contracts/interfaces.md §D
│
├── gateway/                      Go — THE CONTRIBUTION
│   ├── go.mod
│   ├── cmd/gateway/main.go         wiring + config only, no logic
│   └── internal/
│       ├── httpapi/                POST /ask, the cascade, 503 shedding → contracts/interfaces.md §A
│       ├── cache/                  tier1, tier2, key norm   → contracts/interfaces.md §D, the key-normalisation function
│       ├── reuse/                  lanes + overlap rule     → proposal §5 C1   [C1]
│       ├── deps/                   dependency map, COW, writer goroutine
│       │                                                    → contracts/interfaces.md §E  [C2]  NOT BUILT: a stub doc.go
│       ├── admission/              permit pool, queue, shed → proposal §6.1
│       ├── coalesce/               collapses concurrent duplicate misses onto one execution
│       ├── ragclient/              pooled gRPC + epoch      → contracts/interfaces.md §B
│       ├── ragpb/                  generated stubs — `make proto`, gitignored, never hand-edited
│       ├── embed/                  embedding endpoint       → contracts/interfaces.md §F
│       ├── catalog/                read-only corpus view, demo UI ONLY
│       └── telemetry/              counters, latency split, eval log + answer store
│
├── rag/                          Python — INFRASTRUCTURE (not a contribution)
│   ├── pyproject.toml
│   ├── tests/
│   └── src/rag/
│       ├── server.py               gRPC: Answer + Retrieve
│       ├── ingest.py               chunk → embed → index    → data-card.md
│       ├── retrieve.py             top-k, FLAT, frozen
│       ├── generate.py             Ollama call
│       ├── chunkid.py              {doc_id}#chunk-{ordinal} → contracts/interfaces.md §C
│       ├── config.py               the frozen constants, in one place
│       ├── embedding.py            Ollama embedding client (httpx; adds no dependency)
│       ├── store.py                the shared Redis vector-store schema, so ingest and retrieve cannot drift
│       ├── cli.py                  `rag ask` — the retrieval-only dev CLI
│       └── pb/                     generated stubs — `make proto`, gitignored
│
├── experiments/
│   ├── README.md
│   ├── scripts/                    corpus_gate · env_check · fetch_corpus_v1 · loadgen_footprint
│   │                               · load_burst (not citable) · verify_admission.sh
│   │                               NOT BUILT: workload generator, replay, judge, figures
│   │                               → super-plan items 3.4, 5.1, 5.4
│   ├── k6/                         ask.js · mu_hit.js — run co-hosted (ADR-001)
│   ├── tests/                      pytest for the scripts
│   └── results/{run_id}/
│       ├── manifest.yaml           required; a run without one is invalid
│       ├── raw/                    WRITE-ONCE, gitignored (ADR-005)
│       │   ├── requests.jsonl      one record per request → contracts/interfaces.md §H
│       │   └── answers/            {answer_sha256}.txt, the served text → interfaces.md §H, ADR-005
│       └── figures/                regenerated, gitignored
│
├── ui/                           demo debug view (React + Vite)
│   ├── src/                        built to ui/dist, SERVED BY THE GATEWAY
│   └── dist/                       generated by `make ui`, gitignored
│
└── data/
    ├── README.md
    ├── dev-v0/                     development corpus, not citable → the `dev-v0` rule
    ├── v1/                         frozen experimental corpus (Phase 3) → data-card.md §7
    │                               gitignored; empty until built
    ├── v1-draft/                   fetch_corpus_v1.py's output — gitignored, never frozen, absent until the script runs
    └── raw/pqa/                    Amazon-PQA source files — gitignored permanently, never redistributed (ADR-002)
```

**`ui/` is build-time Node only.** The bundle is served by the Go gateway (`spaHandler` in
`cmd/gateway/main.go`), so no dev server runs during a demo or a measured run and nothing competes
with the model for the memory envelope. `catalog/` exists solely to render its product
list: read-only, never on the hit path, and it reads the *corpus* index that `rag/` owns — a
deliberate cross-boundary read, justified only by being demo-only.

## 2. Layering

**The order a request passes through** — what §3 describes. This is *not* the import graph:

```
Tier-1   httpapi → cache.tier1
Tier-2   httpapi → embed ∥ ragclient.Retrieve → reuse (lane) → cache.tier2 (scoped kNN) → reuse (decide)
Miss     httpapi → coalesce → admission → ragclient.Answer → ⟦gRPC seam⟧ → rag/ → Ollama
```

**The import graph, as of 2026-10-07** (`go list` over `gateway/internal/*`, which is where to
re-derive it):

```
cmd/gateway ─► httpapi ─┬─► admission
                        ├─► cache
                        ├─► catalog        demo UI only, never reached from /ask
                        ├─► coalesce
                        ├─► embed
                        ├─► ragclient ─► ragpb (generated)
                        ├─► reuse
                        └─► telemetry
```

`httpapi` is the **only** package that imports its siblings. Every other internal package imports
none of them — `ragclient` imports only the generated `ragpb` — which is why `reuse/` is falsifiable
in isolation and `telemetry/` can be imported from anywhere. `cmd/gateway` imports `httpapi` and
every leaf that `httpapi` does except `coalesce`. **This is an observation, not a rule**: Phase 4's `deps/` will legitimately need `cache`,
and nothing here forbids a new edge between two leaf packages. What the table below forbids is
unchanged, and any new edge should be checked against it.

**A leaf importing `httpapi` is a layering violation.** Import cycles do not compile; a *runtime* cycle
(A calls B calls A) is a defect the compiler cannot see.

| Package | Owns | Must never |
| :--- | :--- | :--- |
| `reuse/` | The C1 decision: lane classification, then two chunk-ID sets + similarity → reuse or not | Touch Redis, gRPC, or HTTP. It stays infrastructure-free so C1 is falsifiable in isolation |
| `deps/` | *(not built)* The **only** writer to the no-eviction region, serialized through one goroutine | Be written from a request goroutine; hold a lock across a Redis round-trip |
| `admission/` | The **sole** acquire/release point for a generation permit | Be bypassed by any miss path — one chokepoint or the memory guarantee is void |
| `coalesce/` | Collapsing concurrent duplicate misses onto one execution; it wraps the `admission/` call, so followers share the leader's result | Hold a permit of its own — `admission/` stays the sole chokepoint |
| `cache/` | Key normalization and both tiers | Make a reuse decision — that is `reuse/` |
| `ragclient/` | Pooled gRPC channel; stamps `dataset_epoch` at retrieval | Be constructed per request |
| `telemetry/` | Counters, latency decomposition, the evaluation log and the run's answer store (`raw/answers/`, ADR-005) | Import anything from this repo |
| `catalog/` | A read-only product list for the demo UI | Be reached from `/ask`, hold state, or make any decision |

## 3. Request paths

| Path | Flow | Cost |
| :--- | :--- | :--- |
| **Tier-1 hit** | `httpapi → cache.tier1` (hash lookup) | ~ms, no embedding, no search |
| **Tier-2 hit** | `→ embed ∥ ragclient.Retrieve` (concurrent) `→ reuse` lane + namespace `→ cache.tier2` kNN **scoped to that namespace** (one search) `→ reuse.DecideLane` | ~tens of ms: the slower of embed and retrieve, plus one search. The unfiltered short-circuit phase is retired (ADR-004) |
| **Miss** | `→ coalesce` (one leader per Tier-1 key) `→ admission.Acquire → ragclient.Answer → LLM →` write back **both** tiers + `t1_key` + epoch | seconds |
| **Shed** | permit unavailable inside budget → `503 busy, retry` | counted as graceful degradation, never as served load |
| **Invalidation** | *(not built — Phase 4)* edit → channel → single writer → COW swap → Redis purge (both tiers), **off** the critical path | — |

**What the Tier-2 row serves today is `similarity ∧ namespace`.** `DecideLane` computes the
containment test, but its result reaches only the logged counterfactual (finding F-K, `super-plan.md`;
ADR-004 records what it does not ratify), and the support gate is Phase 2. The four-conjunct rule is the
design this row is built toward, not what it currently decides.

**Where the contributions live:** C1 → `reuse/` · C2 → `deps/` (+ the epoch check in `ragclient/` and
write-back) · resource governance → `admission/` · the measurement protocol → `experiments/`.
C2 is not built.

## 4. Command surface

Use `make`; do not invent ad-hoc invocations. `make help` is the authority; the targets, grouped:

| Group | Targets |
| :--- | :--- |
| **Run** | `dev` · `ask` · `ingest` · `ui` · `demo` · `demo-reset` |
| **Check the code** | `verify` (= `lint` + build + `test`) · `lint` · `test` · `seam-check` — the one live check; `verify` never runs it |
| **Check the envelope** | `env-check` (ADR-003, loads both models) · `redis-check` · `measure` (gates a *measured* run on green pressure) |
| **Exploratory, not citable** | `load-smoke` · `mu-hit` · `footprint` (**deletes** `t1:` / `t2:` / `lru:` cache keys; needs `make dev`) |
| **Corpus** | `gate-corpus` — runs the G1–G5 gate and, if it passes, prints the snapshot hash |
| **Housekeeping** | `setup` · `proto` · `spike` (spent: the envelope is frozen) · `check` (documentation consistency sweep) |
| **Not yet runnable** | `figures` — it invokes `experiments/scripts/make_figures.py`, which does not exist (super-plan item 5.4) |

## 5. Build order

The tree above is the target. What is real at any moment follows **`docs/super-plan.md`**.

> ⚠️ **The week-based table that stood here was retired on 2026-09-21.** It had become misleading in both directions: it scheduled
> `gateway/internal/{admission,telemetry}` for "W16–W17" when both were built and tested, and it
> gave `gateway/internal/deps/` a slot it never occupied — that package is still a six-line
> `doc.go`. A build order that disagrees with the tree teaches you to stop trusting it.

**What is actually built, 2026-10-07** — the inventory, not a schedule:

| State | Packages |
| :--- | :--- |
| **Built and tested** | `rag/src/rag/*` · `contracts/` · `gateway/internal/{cache, coalesce, admission, telemetry, ragclient, reuse, httpapi}` · `cmd/gateway` — `httpapi` is tested on every exit path of `Ask` (item 1.2) |
| **Built, no tests** | `gateway/internal/{embed, catalog}` — `embed` was listed as tested here until 2026-10-07; it has no test file |
| **Not built** | `gateway/internal/deps/` (C2, a stub `doc.go`) · the answer–evidence support gate (Phase 2) · `data/v1/` · the workload generator, replay harness, judge harness and figure generators (`experiments/scripts/` — items 3.4, 5.1, 5.4) |

## 6. Invariants that fail silently

Each of these produces **no error** when violated — which is why they are invariants rather than
guidelines, and since 2026-09-22 **no hook enforces any of them** — the guard that did was
removed when the files it read were deleted.

1. A frozen value changes only deliberately, and the change record states **which prior runs it
   invalidates**. That sentence is now written by hand into the task's `approvals.md` (and, for a
   numbered decision, the `Invalidates:` line in `decisions.md`) or it is written nowhere.
2. Dependency state lives under `noeviction`; only cache entries are LRU.
3. `t1_key` is written with every Tier-2 record, or Tier-1 survives invalidation.
4. `dataset_epoch` is stamped at retrieval and **compared at write-back**.
5. `experiments/results/*/raw/` is write-once.
6. The vector index is **FLAT**, frozen study-wide — no mid-study HNSW.
7. No ML runtime on the hit path; embeddings come from Ollama.
