# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

> **The documentation was consolidated on 2026-09-22 and the decision log restarted at ADR-001.**
> `docs/` is now the single tree: the plan, the contracts, the corpus card, the decision log, and
> the task trails under `docs/work/`. Source comments were swept in the same pass, so an
> `ADR-NNN` anywhere in this repository now means an entry in `decisions.md` and nothing else.
> Resolve a frozen value from `decisions.md` or `contracts/interfaces.md`, never from memory.

## Repository status

Both services are real and running end-to-end.

- **Python RAG service** (`rag/src/rag/`) — ingestion, chunking, embedding, retrieval, and the gRPC
  server. Works today.
- **Go gateway** (`gateway/internal/`) — `httpapi` (569 lines), `reuse` (732), `cache` (662),
  `telemetry` (234), `coalesce` (216), `admission` (197), `ragclient`, `embed`, `catalog`. The
  two-tier cache, the reuse rule with its three lanes, admission control and request coalescing are
  all built and tested.
- **Not built:** `gateway/internal/deps/` is a one-line stub — **C2, source-aware invalidation,
  does not exist**. `httpapi/` has **zero tests** despite every measured number passing through it.

**Commands that work today:**
- `cd rag && pip3 install -e '.[dev]'` — install the RAG service + dev tools.
- **Before any local-AI command** (`make ingest`, `rag ask`, gRPC generation) — check memory is
  under the ~9–10 GB "other apps" ceiling **every time, not once**. Authoritative signal:
  `sysctl kern.memorystatus_vm_pressure_level` with the model loaded — `0` = green (proceed),
  `1`/`2` = yellow/urgent (close apps and recheck). Pressure has regressed to yellow purely from
  ordinary app load — extra browser tabs, editor windows, chat sessions — with no code or config
  change. **Runs taken under yellow/red are invalid and must be discarded and repeated.**
- Redis must be **`redis-stack-server`**, not plain Homebrew `redis` — the plain formula ships a
  config referencing search-module files it does not bundle and crashes on start. It installs as a
  **cask**, so `brew services` cannot manage it; persistence is a manual LaunchAgent at
  `~/Library/LaunchAgents/com.redis-stack.server.plist` (`RunAtLoad` + `KeepAlive`). Check with
  `launchctl list | grep redis-stack` and `redis-cli PING`.
- `make ingest` — chunk + embed `data/dev-v0/*.json` into Redis.
- `rag ask "<question>"` — retrieval-only CLI, prints top-k chunks with chunk IDs.
- `make lint` / `make test` / `make verify` / `make check` — repo-wide checks. If `ruff`/`pytest`
  report `SKIPPED — not installed` despite being pip-installed, they likely landed in
  `~/Library/Python/3.13/bin` rather than on `PATH`.

## What this project is

A **scalable RAG question-answering platform** for e-commerce product specs and store policies. The
engineering contribution is a **high-concurrency Go gateway acting as an admission controller and
resource governor**, using RAG-aware caching to perform **load conversion** — turning compute-bound
LLM generation into memory-bound cache lookups — so a fixed 16 GB machine absorbs redundant load
without swapping or OOM.

The research claim: a **namespace-partitioned source-containment rule over retrieval provenance**,
augmented by a **deterministic answer–evidence support gate**, sustains more reuse than the best
fixed similarity threshold at a stated false-hit budget — with the residual it does *not* close
(same-evidence, opposite-condition queries) carried inside the claim rather than deferred to a
limitations section. **Provenance-gated reuse is not claimed as novel** (two 2026 systems,
GroundedCache and FinCacheServe, already gate reuse on retrieval context) and **the support gate is
adopted from prior work, not claimed**. Weighting: **60 % systems / 25 % applied-LLM / 15 % semantic
cache**. Full framing: `docs/Final_Proposal.md` §1 and §2.

## Workflow

**Read `.claude/README.md` once before working here.**

The schedule is **phases with binary exit criteria** (`docs/super-plan.md`), and rigor is set by the
**scope** of a change, not by the calendar. Any instruction that says "from W8" or "this week" is
stale — report it rather than acting on it.

- **Orienting:** `/phase` → work. `/task-status` answers "where am I". The phase's `**Exit:**` line
  prints in the session banner; run it **by hand** to close a phase — each criterion names a command
  or an artefact, never a judgement.
- **Changes:** open with `/feature` · `/bugfix` · `/refactor` · `/investigate`, or
  `/task <slug> <L|M|S>`. Each writes a durable trail under `docs/work/<YYYY-MM-DD>-<slug>/` and
  a `SCOPE`. Then `/verify` → `/ai-review` → `/done`. On a failed `/verify`: exactly **one** quick fix, then `/rca`.
  **Tests are immutable** unless an RCA proves staleness and the human confirms.
- **The scope ladder** — `L` (`docs/contracts/interfaces.md`, the `.proto`, `reuse/`, anything
  measured) needs spec → impact → design → **opus design-review** → plan; `M` (ordinary code) needs
  spec → impact → plan; `S` (tests, docs, one-liners) needs a one-paragraph spec. **Between two,
  take the larger.**
- **Commands:** use the **Makefile** (`make help`) — do not invent ad-hoc invocations.
- **No hook blocks any more.** `frozen-guard.sh` and `gate-check.sh` were removed 2026-09-22 because
  both read deleted files and were failing open silently. The surviving hooks are advisory:
  `inject-context.sh` (banner), `done-check.sh` (end-of-turn reminder), `format-lint.sh`.
  **Consequence: nothing will stop you changing a frozen value.** Writing down what a change
  invalidates, in the task's `approvals.md`, is now the only record that it happened.

## Documents

- **`docs/super-plan.md`** — ⭐ **the phase plan, in force.** Eight phases derived from the critical
  path, each with a binary `**Exit:**` line that `.claude/hooks/lib.sh` reads for the banner. Its
  spine: `μ_gen` is frozen, so `h` is the only free variable in `λ_max`, and `h ≤ ρ` for any cache
  serving no false hit — which makes **minimising false hits and serving more requests the same
  frontier**, not two tracks. Also carries "Measuring without a second machine".
- **`docs/Final_Proposal.md`** — the source of truth for framing: contributions, architecture,
  stack, research questions, evaluation design, scope guardrails. §12 (drop order) and §13
  (deliverables) are authoritative and never restated elsewhere. **Gitignored** — it is submitted
  prose and this remote is public.
- **`docs/architecture.md`** — **the folder-structure and module-boundary authority.** Read it
  before creating a directory or adding an import.
- **`docs/contracts/interfaces.md`** — interface and data contracts (HTTP `/ask`, Go↔Python gRPC
  including the retrieval-only RPC, the stable chunk-ID scheme, Redis cache/dependency schemas,
  invalidation event). **At v0.9.** Code at the seam must conform.
- **`docs/contracts/requirements.md`** — skeleton, deliberately unfilled. Requirements split
  **three** ways: **FR** (what the system does) · **NFR** (how well) · **RR — Research
  Requirements** (what makes a measurement admissible). RR exists because most binding constraints
  here are neither behaviours nor runtime qualities, and filing them under NFR hides the failure
  mode: violating an NFR makes the system worse *visibly*, violating an RR voids the result
  *silently*.
- **`docs/data-card.md`** — corpus/workload provenance, licensing, schemas, versioning. §7's gate
  has **five** criteria (G1–G5). G5 is condition-splitting: **no two opposing conditions of the
  same kind share a `doc_id`** — the only lever against the support gate's residual, and it exists
  only before the corpus freeze.
- **`docs/work/`** — task trails. One directory per task, named `<YYYY-MM-DD>-<slug>` after the
  day it opened, so a listing reads oldest first; `.claude/state/active-task` holds the full name
  of the one in progress. Each holds `SCOPE`, `spec.md`, `impact.md`, `design.md`, `review.md`,
  `plan.md`, `approvals.md`, `READY_TO_IMPLEMENT`.
- **`docs/learning/`** — submitted prose and study notes. **Gitignored**, same reason as above.
- **`README.md`** (repo root) — landing page.

## Intended architecture

Two-tier cache in front of a RAG pipeline, decoupled by language and responsibility:

- **Go gateway** (the contribution) — concurrent request handling; a **bounded generation-concurrency
  pool** (semaphore) sized to the slots the model server actually serves, which is one
  (ADR-003); **backpressure / graceful load shedding** (`503 busy, retry`) so overload surfaces as
  counted shedding instead of queueing invisibly inside Ollama; Tier-1 exact-match cache; Tier-2 semantic
  cache (embed + similarity search + the source-overlap reuse rule); request coalescing
  (`singleflight`); and a **thread-safe source→entry dependency map** for invalidation (read-mostly,
  `atomic.Pointer` copy-on-write, mutated out-of-band by a channel-fed writer goroutine).
- **Python RAG service** — ingestion/chunking/embedding (LlamaIndex), retrieval, calls the local
  LLM. Speaks gRPC to Go. Invoked on a miss, or for the cascade's retrieval-only call.
- **Local LLM** — **Qwen 3.5 2B** via Ollama, 4-bit `q4_K_M`, `num_ctx` fixed at 8192,
  **`think: false` required on every call**. It replaced the originally-frozen Gemma 4 E4B, which
  entered yellow memory pressure at even the lightest config on this machine's real available RAM.
  Older prose may still say "Gemma" — it is wrong. Embeddings: **`nomic-embed-text`, 768-dim**,
  served by Ollama, never an in-process PyTorch stack (~2 GB for a ~400 MB model). Ollama runs
  **natively on the host, never in Docker** — macOS containers have no Metal passthrough, and a
  CPU-bound LLM invalidates every latency measurement.
- **Redis** — cache store + vector search for Tier 2.

## Constraints any code change must respect

- **Cache only the "stable" slice** (product specs, policies). Dynamic content — stock, price,
  order status — must classify-and-bypass to a live source and never enter the cache.
- **Freeze the LLM and embedding model.** Swapping either mid-study invalidates every
  cross-configuration comparison.
- **Bounded cache**: fixed capacity, LRU eviction, always. Capacity is derived as `0.25 × K` from
  the frozen workload's distinct-query count, and the **gateway** enforces it — Redis evicts
  nothing.
- **Hardware envelope**: a single MacBook M1, 16 GB unified memory, **one generation slot**
  (ADR-003: Ollama serves Qwen 3.5 at one slot whatever `OLLAMA_NUM_PARALLEL` requests, so the old
  "frozen at 4" was never served), with `num_ctx = 8192`, Ollama **0.33.2** and the weights blob
  pinned, all verified against the live runner by `make env-check`. μ_gen ≈ 28.2 tok/s is a
  one-slot **planning figure** until Phase 7 re-measures it. **Ollama.app auto-update stays off**,
  and the Ollama app is not used during a run. This machine also runs unrelated projects, so the real ceiling is
  ~9–10 GB used / ~5–6 GB free before any Ollama test — materially tighter than "16 GB nominal".
- **Load generation is co-hosted, and reported as such.** A second machine was required by the
  original decision and none exists. The headline capacity claim survives because it is an
  *inequality*: `h*` is monotone increasing in `μ_hit`, and co-hosting depresses `μ_hit`, so a
  co-hosted figure is a **lower bound** on both. What it does **not** rescue: any number presented
  as a ceiling (the Tier-1 `μ_hit` probe especially), and p95 at high offered rate. See
  `docs/super-plan.md` "Measuring without a second machine".
- **Govern admission to the served slots.** Bound in-flight generations to the slots the model
  server actually serves (one, ADR-003), and shed with backpressure rather than let work queue
  invisibly inside Ollama. The pool bounds **queueing delay and goodput**. Memory is fixed when
  Ollama loads the runner, and admitting requests adds none. Runs are valid only in macOS green
  pressure.
- **Provenance-first, and deterministic.** The reuse decision is four conjuncts:
  `sim(q,e) ≥ τ  ∧  namespace(q) = namespace(e)  ∧  overlap(retrieve(q), sources(e)) ≥ θ  ∧
  support(answer(e), text(retrieve(q)))`. It is a **rule computed in Go** — set intersection over
  chunk IDs and token overlap — not a learned model. **There is no ML runtime on the hit path.**
  θ and τ are **swept, never hand-set**; `τ_s` for the support gate is pinned at 0.6 and never
  swept. The reuse decision must never read the query text as a *predictive* signal.
- **Invalidation is blind dependency-purge.** Source edits purge every dependent entry via the
  dependency map — guaranteed-complete. Predictor-gated purging was removed. The update set's
  `substantive`/`cosmetic` split exists to *measure* over-invalidation, never to gate it.
- **Single-node envelope; no scale-out.** Horizontal scaling, multi-pod, DB sharding, and a
  fronting load balancer are out of scope. The contribution is single-envelope load conversion.
- **δ ≤ 5 %** is the provisional false-hit budget — the target operating point for θ/τ tuning until
  the judge's measured error finalises it. Report rates with **Wilson score intervals**.
- **Five cache configurations**, not eight: no-cache · exact-only · fixed-τ · source-overlap rule ·
  full tiered system — **crossed with a binary `mutation: off|on` factor**. A run is identified by
  `(config_id, mutation)`, never `config_id` alone.
- **Do not reintroduce cut scope.** The learned reuse-safety predictor, predictor-gated
  invalidation, GPTCache/vCache *integration*, semantic routing, SSE streaming, and the **bypass
  classifier** are out of scope. If a task seems to need one, flag it rather than building it.
- **Three correctness invariants** — each closes a *silent* failure path, so none is optional:
  1. **Dependency records must not be evictable.** An evicted `dep:*` / `entry:*` record makes its
     entries unpurgeable and breaks invalidation completeness with no error.
  2. **`t1_key` on every Tier-2 record.** The Tier-1 hash is not computable from `entry_id`, so
     without it purges silently miss Tier 1.
  3. **Epoch-guarded write-back.** Retrieval stamps `dataset_epoch`; write-back discards if it
     advanced. Otherwise a generation in flight during an edit resurrects stale data after the purge.
- **Validity is method, not polish.** The reference-free labelling ablation, the validation/test
  split partitioned **by seed-question cluster** (splitting by pair leaks paraphrases), and the
  decisions-changed-by-provenance metric sit **above** judged-sample size in the drop order. Never
  quietly trade them for a bigger sample.
- **Never tune to make a headline work.** A measurement is evidence, not a target. Thresholds are
  swept, tuned on validation, and reported on held-out test. A pre-registered null is a result.
- **`dev-v0` is not citable in any result.** It is the development corpus.
- **Amazon-PQA redistribution is not granted.** `data/v1/` and `data/v1-draft/` stay gitignored;
  ship a download-and-build script plus a hash manifest, never the raw corpus. Required citation:
  Rozen et al., NAACL-HLT 2021.
- **`experiments/results/*/raw/` and `manifest.yaml` are write-once.** Figures regenerate FROM raw,
  never the reverse. If a run is wrong, record a new `run_id` — do not edit history.
- **The platform is the thesis.** Non-negotiable: tiered caching, source-aware invalidation, the
  concurrency-safe gateway with admission control and memory-pressure discipline, the load-testing
  evaluation. Everything else follows the drop order in `Final_Proposal.md` §12 — assume it is
  optional and do not gold-plate it.
