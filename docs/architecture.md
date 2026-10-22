# System Architecture & Repository Structure

**Status:** authority for folder structure and module boundaries · **Created:** 2026-08-09 ·
**Revised:** 2026-10-16
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
│   ├── 0. progress 16-10.md        progress report for the supervisor, 2026-10-16
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
│   ├── cmd/gateway/main.go         wiring + config, no request logic. Its env and run-end rules (gateFromEnv,
│   │                               retiredEnv, incomplete, finishRun) are pure functions with tests beside it
│   └── internal/
│       ├── httpapi/                POST /ask, the cascade, 503 shedding → contracts/interfaces.md §A
│       │                           · /products and /stats for the demo UI (browse.go)
│       ├── cache/                  tier1, tier2, key norm   → contracts/interfaces.md §D, the key-normalisation function
│       │                           · the gateway-side LRU count, lru:entries (capacity.go)
│       ├── reuse/                  lanes + overlap rule + support arms + the refusal cause (cause.go)  → proposal §5 C1   [C1]
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
│   ├── scripts/                    corpus_gate (G1–G5; G5 lexical, items 3.3 / 3.5) · env_check · build_pqa
│   │                               · select_pqa · answerability_check (item 3.2) · check_policies (item 3.3)
│   │                               · build_workload (item 3.4: make workload-embed / -build / -verify)
│   │                               · loadgen_footprint · load_burst (not citable) · verify_admission.sh
│   │                               NOT BUILT: replay, judge, figures
│   │                               → super-plan items 5.1, 5.4
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
    ├── policies-v1/                TRACKED: the source of v1's policy documents (item 3.3), author-owned and releasable.
    │                               NOT a dataset version: never VERSION= or DATASET_VERSION; 3.6 copies it into v1/
    ├── v1/                         frozen experimental corpus (Phase 3) → data-card.md §7
    │                               gitignored; empty until built
    ├── v1-draft/                   gitignored, never frozen. Must hold no top-level product-*.json: the retired fetch
    │                               script wrote wrong-dataset ones here; build_pqa.py warns and select_pqa.py refuses
    │   ├── pqa/                      build_pqa.py's interim files, one per leaf (item 3.1); read only through iter_interim
    │   ├── products/                 select_pqa.py's 152 draft records, product-{department}-{asin}.json (item 3.2)
    │   ├── question-pool.jsonl       every kept question of those products, tagged; read only through iter_selection
    │   ├── generic-tokens.json       each leaf's common title words (R2's generic set)
    │   ├── audit/                    the blind audit sheet the author marks (item 3.2)
    │   └── workload/                 item 3.4: the model layer, the vectors and the author-read sheet
    ├── pqa-manifest.json           TRACKED: hashes and counts of the 3.1 interim files, no PQA text. NOT the v1 snapshot digest (item 3.6)
    ├── pqa-selection.json          TRACKED: counts and digests of the 3.2 drafts, no PQA text, no asin. NOT the v1 snapshot digest
    ├── workload-manifest.json      TRACKED: hashes and counts of the item 3.4 build, no PQA text, no asin. NOT the v1 snapshot digest
    ├── workload-v1*.json           gitignored (PQA text): the whole workload and its -validation and -test files.
    │                               Outside v1/ on purpose: rag.ingest globs that folder
    └── raw/                        gitignored permanently, never redistributed
        ├── pqa/                      Amazon-PQA source files (ADR-002)
        └── epqa/                     ePQA CSVs at a pinned commit, for the answerability check only (CDLA-Sharing-1.0)
```

**`ui/` is build-time Node only.** The bundle is served by the Go gateway (`spaHandler` in
`cmd/gateway/main.go`), so no dev server runs during a demo or a measured run and nothing competes
with the model for the memory envelope. `catalog/` exists solely to render its product
list: read-only, never on the hit path, and it reads the *corpus* index that `rag/` owns — a
deliberate cross-boundary read, justified only by being demo-only.

**Redis is not in the tree because it holds no file of record.** Everything in it is derived
(ADR-007): `corpus::{chunk_id}` text and vectors are rebuilt by `make ingest`, and `t1:*`, `t2:*`,
`dep:*` and `lru:entries` are cache state. The corpus of record is `data/<dataset_version>/*.json`
plus the frozen chunking config. Losing Redis costs hit rate and a rebuild, never data — but while it
is down the system is down, because the corpus index lives there too.

## 2. Layering

**The order a request passes through** — what §3 describes. This is *not* the import graph:

```
Tier-1   httpapi → cache.tier1
Tier-2   httpapi → embed ∥ ragclient.Retrieve → reuse (lane) → cache.tier2 (scoped kNN) → reuse (decide)
Miss     httpapi → coalesce → admission → ragclient.Answer → ⟦gRPC seam⟧ → rag/ → Ollama
```

**The import graph, as of 2026-10-16** (`go list` over `gateway/internal/*`, which is where to
re-derive it; unchanged since 2026-10-07):

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
| `deps/` | *(not built)* The **only** writer to the dependency records (`dep:*`), serialized through one goroutine | Be written from a request goroutine; hold a lock across a Redis round-trip |
| `admission/` | The **sole** acquire/release point for a generation permit | Be bypassed by any miss path — one chokepoint or the memory guarantee is void |
| `coalesce/` | Collapsing concurrent duplicate misses onto one execution; it wraps the `admission/` call, so followers share the leader's result | Hold a permit of its own — `admission/` stays the sole chokepoint |
| `cache/` | Key normalization, both tiers, and the entry-count bound (`lru:entries`; Redis evicts nothing) | Make a reuse decision — that is `reuse/` |
| `ragclient/` | Pooled gRPC channel; stamps `dataset_epoch` at retrieval | Be constructed per request |
| `telemetry/` | Counters, latency decomposition, the evaluation log and the run's answer store (`raw/answers/`, ADR-005) | Import anything from this repo |
| `catalog/` | A read-only product list for the demo UI | Be reached from `/ask`, hold state, or make any decision |

## 3. Request paths

| Path | Flow | Cost |
| :--- | :--- | :--- |
| **Tier-1 hit** | `httpapi → cache.tier1` (hash lookup) | ~ms, no embedding, no search |
| **Tier-2 hit** | `→ embed ∥ ragclient.Retrieve` (concurrent) `→ reuse` lane + namespace `→ cache.tier2` kNN **scoped to that namespace** (one search) `→ reuse.DecideLane → reuse.Thresholds.Judge`. On a serve, the hit-count bump and a Tier-1 promotion run in the background, off the hit path | ~tens of ms: the slower of embed and retrieve, plus one search. The unfiltered short-circuit phase is retired (ADR-004) |
| **Miss** | `→ coalesce` (one leader per Tier-1 key) `→ admission.Acquire → ragclient.Answer` (it sends the chunk IDs already retrieved, so Python grounds on them and does not retrieve again) `→ LLM →` write back **both** tiers + `t1_key` + epoch `→ cache.TrimToCapacity` (deletes both tiers of each victim) | seconds |
| **Shed** | permit unavailable inside budget → `503 busy, retry` | counted as graceful degradation, never as served load |
| **Invalidation** | *(not built — Phase 4)* edit → channel → single writer → COW swap → Redis purge (both tiers), **off** the critical path | — |

**What the Tier-2 row serves today is `similarity ∧ namespace ∧ support` with the gate on, and
`similarity ∧ namespace` with it off** (items 2.3 and 2.4, ADR-009 and ADR-010).
`DecideLane` still computes the containment test, but its result reaches only the logged counterfactual
(finding F-K, `super-plan.md`; ADR-004 records what it does not ratify), so θ is not in the served rule
and `CONTAINMENT` is never written as a refusal cause. The support gate is called from the cascade
through `reuse.Thresholds.Judge`, which returns the one refusal cause. Its first parameter is the arm,
`reuse.Gate`: `SUPPORT_GATE=on|off` is read once in `cmd/gateway` (unset = on), held in one field,
`Handler.SupportGate`, and written to every evaluation record as `support_gate`. The four-conjunct rule
is still the design this row is built toward, with θ the missing term.

**Three parts of these paths are written but do nothing yet.** Each waits for a named item:

- **The epoch is a constant.** Python returns `DATASET_EPOCH_STUB = 0` (`rag/src/rag/config.py`), and
  write-back stores it but never compares it, so `writeback_discarded` is logged and never set
  (item 4.2). When it is built, the epoch must come from the corpus of record, never from a Redis key
  (ADR-008).
- **A promoted Tier-1 key is not tracked.** The Tier-2 record holds one `t1_key`, the one written at
  miss time. The key a Tier-2 serve promotes is a second pointer at the same entry, and neither the
  trim nor a future purge can find it (item 4.3).
- **The trim does nothing by default.** `CACHE_CAPACITY` unset or `0` means unbounded, so hit rates
  today are an upper bound. It is set to `round(0.25 × K)` once `K` is frozen (item 3.6).

**Where the contributions live:** C1 → `reuse/` · C2 → `deps/` (+ the epoch check in `ragclient/` and
write-back) · resource governance → `admission/` · the measurement protocol → `experiments/`.
C2 is not built.

## 4. Command surface

Use `make`; do not invent ad-hoc invocations. `make help` is the authority; the targets, grouped:

| Group | Targets |
| :--- | :--- |
| **Run** | `dev` · `ask` · `ingest` · `ui` · `demo` · `demo-reset` |
| **Check the code** | `verify` (= `lint` + build + `test`) · `lint` · `test` · `seam-check` (item 1.4) and `support-check` (item 2.1) — the two live checks; `verify` never runs either |
| **Check the envelope** | `env-check` (ADR-003, loads both models) · `redis-check` · `measure` (gates a *measured* run on green pressure) |
| **Exploratory, not citable** | `load-smoke` · `mu-hit` · `footprint` (**deletes** `t1:` / `t2:` / `lru:` cache keys; needs `make dev`) |
| **Corpus** | `gate-corpus` — runs the G1–G5 gate and, if it passes, prints the snapshot hash · `pqa-fetch` (curl, resume) · `pqa-build` (Stops 0–3, then the interim files and `data/pqa-manifest.json`) · `pqa-verify` (offline hash check) — item 3.1 · `pqa-select`, `pqa-select-verify`, `pqa-audit-sheet`, `pqa-audit-score`, `epqa-fetch`, `pqa-answerability` — item 3.2 · `policy-check` (schema, terms, ≥ 3 chunks, G5 on `data/policies-v1/`; offline) — item 3.3 |
| **Housekeeping** | `setup` · `proto` · `spike` (spent: the envelope is frozen) · `check` (documentation consistency sweep) |
| **Not yet runnable** | `figures` — it invokes `experiments/scripts/make_figures.py`, which does not exist (super-plan item 5.4) |

## 5. Build order

The tree above is the target. What is real at any moment follows **`docs/super-plan.md`**.

> ⚠️ **The week-based table that stood here was retired on 2026-09-21.** It had become misleading in both directions: it scheduled
> `gateway/internal/{admission,telemetry}` for "W16–W17" when both were built and tested, and it
> gave `gateway/internal/deps/` a slot it never occupied — that package is still a six-line
> `doc.go`. A build order that disagrees with the tree teaches you to stop trusting it.

**What is actually built, 2026-10-16** — the inventory, not a schedule:

| State | Packages |
| :--- | :--- |
| **Built and tested** | `rag/src/rag/*` · `contracts/` · `gateway/internal/{cache, coalesce, admission, telemetry, ragclient, reuse, httpapi}` (`reuse` includes the support arms, the refusal cause and the gate's on/off switch, item 2.4) · `cmd/gateway` — `httpapi` is tested on every exit path of `Ask` (item 1.2) · `experiments/scripts/build_pqa.py` (item 3.1, the Amazon-PQA builder; run on the six real files 2026-10-15) · `experiments/scripts/select_pqa.py` and `answerability_check.py` (item 3.2; the selection ran 2026-10-20: 152 draft products) · `experiments/scripts/build_workload.py` (item 3.4; the draft build ran 2026-10-22: 1,274 queries) |
| **Built, no tests** | `gateway/internal/{embed, catalog}` — `embed` was listed as tested here until 2026-10-07; it has no test file |
| **Not built** | `gateway/internal/deps/` (C2, a stub `doc.go`) · the epoch guard on write-back (item 4.2) · `data/v1/` (the 3.2 drafts are in `data/v1-draft/`; the policy documents are item 3.3, in `data/policies-v1/`) · the replay harness, judge harness and figure generators (`experiments/scripts/` — items 5.1, 5.4) |

## 6. Invariants that fail silently

Each of these produces **no error** when violated — which is why they are invariants rather than
guidelines, and since 2026-09-22 **no hook enforces any of them** — the guard that did was
removed when the files it read were deleted.

1. A frozen value changes only deliberately, and the change record states **which prior runs it
   invalidates**. That sentence is now written by hand into the task's `approvals.md` (and, for a
   numbered decision, the `Invalidates:` line in `decisions.md`) or it is written nowhere.
2. Redis evicts nothing (`make redis-check` fails the run otherwise). Only the gateway removes
   entries, by trimming cache entries through `lru:entries`, and it never touches `dep:*`
   (`interfaces.md` §D, since v0.6).
3. `t1_key` is written with every Tier-2 record, or Tier-1 survives invalidation. A Tier-1 key
   added later by promotion is **not** covered yet (item 4.3, §3).
4. `dataset_epoch` is stamped at retrieval and **compared at write-back**, and it is never a Redis
   key (ADR-008). Today it is a constant and the comparison is not built (item 4.2), so no run has
   this guarantee yet.
5. `experiments/results/*/raw/` is write-once.
6. The vector index is **FLAT**, frozen study-wide — no mid-study HNSW.
7. No ML runtime on the hit path; embeddings come from Ollama.
