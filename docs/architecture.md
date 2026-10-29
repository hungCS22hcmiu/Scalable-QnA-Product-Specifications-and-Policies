# System Architecture & Repository Structure

**Status:** authority for folder structure and module boundaries · **Created:** 2026-08-09 ·
**Revised:** 2026-10-29
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
│   ├── 0-Thesis-Report/            the final report: plan, Markdown drafts, figures, LaTeX  (gitignored)
│   └── learning/                   study notes  (gitignored)
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
│   │                               bandFromEnv, retiredEnv, incomplete, finishRun) are pure functions with tests beside it
│   └── internal/
│       ├── httpapi/                POST /ask, the cascade, 503 shedding → contracts/interfaces.md §A
│       │                           · /products and /stats for the demo UI (browse.go)
│       ├── cache/                  tier1, tier2, key norm   → contracts/interfaces.md §D, the key-normalisation function
│       │                           · the gateway-side LRU count, lru:entries (capacity.go)
│       ├── reuse/                  lanes + overlap rule + support arms + the refusal cause (cause.go)  → proposal §5 C1   [C1]
│       ├── deps/                   dependency map, COW, writer goroutine
│       │                                                    → contracts/interfaces.md §E  [C2]  built (item 4.1)
│       ├── admission/              permit pool, queue, shed → proposal §6.1
│       ├── coalesce/               collapses concurrent duplicate misses onto one execution
│       ├── ragclient/              pooled gRPC + epoch      → contracts/interfaces.md §B
│       ├── ragpb/                  generated stubs — `make proto`, gitignored, never hand-edited
│       ├── embed/                  embedding endpoint       → contracts/interfaces.md §F
│       ├── catalog/                read-only corpus view, demo UI ONLY
│       ├── testredis/              the Go tests' Redis connection (test-only) → §2, §4
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
│   │                               · freeze_corpus (item 3.6: make corpus-assemble / -index-check / -freeze / -verify)
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
    ├── v1/                         frozen experimental corpus (Phase 3) → data-card.md §7, ADR-015
    │                               gitignored; built by `make corpus-assemble`; frozen 2026-10-23
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
    ├── v1-freeze.json              TRACKED: the v1 freeze record (item 3.6, ADR-015): the snapshot digest, chunk digest, K, the stack and
    │                               `known_failures` (G1, ADR-014). Digests, counts and statistics only: no file name, asin or path
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

**The import graph, as of 2026-10-28** (`go list` over `gateway/internal/*`, which is where to
re-derive it; item 4.1 added the `httpapi → deps` edge):

```
cmd/gateway ─► httpapi ─┬─► admission
                        ├─► cache
                        ├─► catalog        demo UI only, never reached from /ask
                        ├─► coalesce
                        ├─► deps           imports no internal package; reaches the tiers through `Purger`
                        ├─► embed
                        ├─► ragclient ─► ragpb (generated)
                        ├─► reuse
                        └─► telemetry
```

`httpapi` is the **only** package that imports its siblings. Every other internal package imports
none of them — `ragclient` imports only the generated `ragpb` — which is why `reuse/` is falsifiable
in isolation and `telemetry/` can be imported from anywhere. `cmd/gateway` imports `httpapi` and
every leaf that `httpapi` does except `coalesce`, and it passes `*cache.Store` to `deps.New` as the `Purger`. **This is an observation, not a rule**:
`deps/` reaches the two tiers through that small interface and so imports no sibling, and nothing here
forbids a new edge between two leaf packages. What the table below forbids is unchanged, and any new
edge should be checked against it.

**A leaf importing `httpapi` is a layering violation.** Import cycles do not compile; a *runtime* cycle
(A calls B calls A) is a defect the compiler cannot see.

| Package | Owns | Must never |
| :--- | :--- | :--- |
| `reuse/` | The C1 decision: lane classification, then two chunk-ID sets + similarity → reuse or not | Touch Redis, gRPC, or HTTP. It stays infrastructure-free so C1 is falsifiable in isolation |
| `deps/` | The **only** writer to the dependency records (`dep:*`, `entry:*`), serialized through one goroutine; the copy-on-write snapshot of invalidated `entry_id`s; reaches both tiers only through the `Purger` interface (item 4.1) | Be written from a request goroutine; hold a lock across a Redis round-trip; import a sibling package |
| `admission/` | The **sole** acquire/release point for a generation permit | Be bypassed by any miss path — one chokepoint or the memory guarantee is void |
| `coalesce/` | Collapsing concurrent duplicate misses onto one execution; it wraps the `admission/` call, so followers share the leader's result | Hold a permit of its own — `admission/` stays the sole chokepoint |
| `cache/` | Key normalization, both tiers, and the entry-count bound (`lru:entries`; Redis evicts nothing) | Make a reuse decision — that is `reuse/` |
| `ragclient/` | Pooled gRPC channel; stamps `dataset_epoch` at retrieval | Be constructed per request |
| `testredis/` | The Go tests' Redis connection: reads the address from `GATEWAY_TEST_REDIS` (the throwaway server `make test` starts on port 6390), and refuses a server that holds any search index or any DB 0 key | Be imported by non-test code, or default to `localhost:6379` |
| `telemetry/` | Counters, latency decomposition, the evaluation log and the run's answer store (`raw/answers/`, ADR-005) | Import anything from this repo |
| `catalog/` | A read-only product list for the demo UI | Be reached from `/ask`, hold state, or make any decision |

## 3. Request paths

| Path | Flow | Cost |
| :--- | :--- | :--- |
| **Tier-1 hit** | `httpapi → cache.tier1` (hash lookup) | ~ms, no embedding, no search |
| **Tier-2 hit** | `→ embed ∥ ragclient.Retrieve` (concurrent) `→ reuse` lane + namespace `→ cache.tier2` kNN **scoped to that namespace** (one search) `→ reuse.DecideLane → reuse.Thresholds.Judge`. On a serve, the hit-count bump and a Tier-1 promotion run in the background, off the hit path | ~tens of ms: the slower of embed and retrieve, plus one search. The unfiltered short-circuit phase is retired (ADR-004) |
| **Miss** | `→ coalesce` (one leader per Tier-1 key) `→ admission.Acquire → ragclient.Answer` (it sends the chunk IDs already retrieved, so Python grounds on them and does not retrieve again) `→ LLM →` write back **both** tiers + `t1_key` + epoch `→ cache.TrimToCapacity` (deletes both tiers of each victim) | seconds |
| **Shed** | permit unavailable inside budget → `503 busy, retry` | counted as graceful degradation, never as served load |
| **Invalidation** | `deps.Invalidate(event)` → channel → single writer → `SMEMBERS dep:{chunk}` → COW swap of the tombstones → `Purger.PurgeEntry` per entry (both tiers) → `DEL entry:E`, `DEL dep:{chunk}`. The Redis purge runs **off** the caller's path. A hit checks the snapshot after it reads Redis (item 4.1). How an edit reaches the gateway is item 4.4 | — |

**What the Tier-2 row serves today is `similarity ∧ namespace ∧ support` with the gate on, and
`similarity ∧ namespace` with it off** (items 2.3 and 2.4, ADR-009 and ADR-010).
`DecideLane` still computes the containment test, but its result reaches only the logged counterfactual
(finding F-K, `super-plan.md`; ADR-004 records what it does not ratify), so θ is not in the served rule
and `CONTAINMENT` is never written as a refusal cause. The support gate is called from the cascade
through `reuse.Thresholds.Judge`, which returns the one refusal cause. Its first parameter is the arm,
`reuse.Gate`: `SUPPORT_GATE=on|off` is read once in `cmd/gateway` (unset = on), held in one field,
`Handler.SupportGate`, and written to every evaluation record as `support_gate`. The four-conjunct rule
is still the design this row is built toward, with θ the missing term.

**One part of these paths is written but does nothing yet.** It waits for a named item:

- **The trim does nothing by default.** `CACHE_CAPACITY` unset or `0` means unbounded, so hit rates
  today are an upper bound. It is set to `round(0.25 × K)`, with the `K` of the run file, once `K` is frozen (item 3.6).

**The dataset epoch is built (item 4.2).** It is one integer in a file named by `DATASET_EPOCH_FILE`,
never a Redis key (ADR-008). `rag.server` reads it first in each RPC and stamps it. The gateway
compares it at write-back and discards the write-back on any difference or read error
(`writeback_discarded`). The dependency map's writer compares it once more at registration, which closes
the gap between the guard and the registration (`LateDiscards`). Neither service starts without the
file. The rules are in `interfaces.md` §E.

**Where the contributions live:** C1 → `reuse/` · C2 → `deps/` (+ the epoch check in `ragclient/` and
write-back) · resource governance → `admission/` · the measurement protocol → `experiments/`.
C2's dependency map and blind purge are built (item 4.1), and so is the epoch guard (item 4.2).

## 4. Command surface

Use `make`; do not invent ad-hoc invocations. `make help` is the authority; the targets, grouped:

| Group | Targets |
| :--- | :--- |
| **Run** | `dev` · `ask` · `ingest` · `ui` · `demo` · `demo-reset` |
| **Check the code** | `verify` (= `lint` + build + `test`) · `lint` · `test` · `test-go` · `test-isolation-check` · `seam-check` (item 1.4) and `support-check` (item 2.1) — the two live checks; `verify` never runs either |
| **Check the envelope** | `env-check` (ADR-003, loads both models) · `redis-check` · `measure` (gates a *measured* run on green pressure) |
| **Exploratory, not citable** | `load-smoke` · `mu-hit` · `footprint` (**deletes** `t1:` / `t2:` / `lru:` cache keys; needs `make dev`) |
| **Corpus** | `gate-corpus` — runs the G1–G5 gate and, if it passes, prints the snapshot hash (with `ACCEPT_FAILED=G1`, ADR-014: prints it as a recorded failure and exits 3) · `corpus-assemble` · `corpus-index-check` · `corpus-freeze` · `corpus-verify` — item 3.6, ADR-015 · `pqa-fetch` (curl, resume) · `pqa-build` (Stops 0–3, then the interim files and `data/pqa-manifest.json`) · `pqa-verify` (offline hash check) — item 3.1 · `pqa-select`, `pqa-select-verify`, `pqa-audit-sheet`, `pqa-audit-score`, `epqa-fetch`, `pqa-answerability` — item 3.2 · `policy-check` (schema, terms, ≥ 3 chunks, G5 on `data/policies-v1/`; offline) — item 3.3 |
| **Housekeeping** | `setup` · `proto` · `spike` (spent: the envelope is frozen) · `check` (documentation consistency sweep) |
| **Not yet runnable** | `figures` — it invokes `experiments/scripts/make_figures.py`, which does not exist (super-plan item 5.4) |

**The Go Redis tests run only against `make test`'s throwaway Redis on port 6390, never against :6379.** On this server `FLUSHDB` and `FLUSHALL` drop every search index in every DB, and an index covers every DB, so a test that flushes "its own" DB on the live server deletes `idx:corpus` and `idx:cache` (bugfix `2026-10-29-redis-index-lifecycle`; `make test-isolation-check` proves a sentinel index on :6379 survives the Go tests, and `make verify` runs it).

## 5. Build order

The tree above is the target. What is real at any moment follows **`docs/super-plan.md`**.

> ⚠️ **The week-based table that stood here was retired on 2026-09-21.** It had become misleading in both directions: it scheduled
> `gateway/internal/{admission,telemetry}` for "W16–W17" when both were built and tested, and it
> gave `gateway/internal/deps/` a slot it never occupied — that package stayed a six-line
> `doc.go` until item 4.1. A build order that disagrees with the tree teaches you to stop trusting it.

**What is actually built, 2026-10-28** — the inventory, not a schedule:

| State | Packages |
| :--- | :--- |
| **Built and tested** | `rag/src/rag/*` · `contracts/` · `gateway/internal/{cache, coalesce, admission, telemetry, ragclient, reuse, httpapi, deps}` (`reuse` includes the support arms, the refusal cause and the gate's on/off switch, item 2.4; `deps` is the dependency map and blind purge, item 4.1, and the epoch reader and late check, item 4.2) · `cmd/gateway` — `httpapi` is tested on every exit path of `Ask` (item 1.2) · `experiments/scripts/build_pqa.py` (item 3.1, the Amazon-PQA builder; run on the six real files 2026-10-15) · `experiments/scripts/select_pqa.py` and `answerability_check.py` (item 3.2; the selection ran 2026-10-20: 152 draft products) · `experiments/scripts/build_workload.py` (item 3.4; the draft build ran 2026-10-22: 1,274 queries) |
| **Built, no tests** | `gateway/internal/{embed, catalog}` — `embed` was listed as tested here until 2026-10-07; it has no test file |
| **Not built** | a restore path for `data/v1/` (it has no git; `make corpus-assemble` rebuilds it from the drafts and `data/policies-v1/`; Phase 4) · the replay harness, judge harness and figure generators (`experiments/scripts/` — items 5.1, 5.4) |

## 6. Invariants that fail silently

Each of these produces **no error** when violated — which is why they are invariants rather than
guidelines, and since 2026-09-22 **no hook enforces any of them** — the guard that did was
removed when the files it read were deleted.

1. A frozen value changes only deliberately, and the change record states **which prior runs it
   invalidates**. That sentence is now written by hand into §2 Impact of the task's `design.md` (and,
   for a numbered decision, the `Invalidates:` line in `decisions.md`) or it is written nowhere.
2. Redis evicts nothing (`make redis-check` fails the run otherwise). Only the gateway removes
   entries, by trimming cache entries through `lru:entries`, and it never touches `dep:*`
   (`interfaces.md` §D, since v0.6).
3. `t1_key` is written with every Tier-2 record, or Tier-1 survives invalidation. Every Tier-1 key,
   promoted ones included, is also recorded in `lru:t1keys:{entry_id}` in the same atomic step as its
   write (item 4.3), so the trim and the purge find it. A promotion is written only while `t2:` exists.
4. `dataset_epoch` is stamped at retrieval and **compared at write-back**, and it is never a Redis
   key (ADR-008). Built in item 4.2: Python reads the epoch file before the chunk texts, the gateway
   compares at write-back, and the dependency map's writer compares again at registration.
5. `experiments/results/*/raw/` is write-once.
6. The vector index is **FLAT**, frozen study-wide — no mid-study HNSW.
7. No ML runtime on the hit path; embeddings come from Ollama.
