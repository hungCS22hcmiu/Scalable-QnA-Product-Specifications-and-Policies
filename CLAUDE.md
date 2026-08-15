# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

Build work started **W5 (Aug 10, 2026)** and is **in progress**. The Python RAG service
(`rag/src/rag/`) is real and working — corpus ingestion, chunking, embedding, and retrieval run
end-to-end against Redis. The Go gateway (`gateway/`) is still scaffold-only (package-doc stubs,
no logic) — its build starts **W6** per `docs/design/architecture.md` §5's build order; don't add
gateway logic before then unless a task explicitly says otherwise.

**Commands that work today:**
- `cd rag && pip3 install -e '.[dev]'` — install the RAG service + dev tools.
- Redis needs **`redis-stack-server`**, not plain Homebrew `redis` — the plain `redis` 8.10
  formula ships a config that references search-module files it doesn't bundle and crashes on
  start. `brew install redis-stack` (tap `redis-stack/redis-stack`) instead; see
  `docs/worklog/W05.md`'s 2026-08-15 entry.
- `make ingest` — chunk + embed `data/dev-v0/*.json` into Redis (`python3 -m rag.ingest`).
- `rag ask "<question>"` (or `python3 -m rag.cli ask "<question>"` if the console-script isn't on
  `PATH`) — retrieval-only CLI, prints top-k chunks with chunk IDs. This is the W5 exit test.
- `make lint` / `make test` / `make verify` — repo-wide checks. If `ruff`/`pytest` report
  `SKIPPED — not installed` despite being pip-installed, they likely landed in
  `~/Library/Python/3.13/bin`, not on `PATH` — add it or invoke them by full path.

**Scope was reduced on 2026-08-09** (`docs/decisions.md` **ADR-016**) to fit a ~250-hour part-time budget and a backend-engineering skill profile. Read ADR-016 before acting on anything that looks like it involves machine learning — it probably was cut.

## What this project is

A **scalable RAG question-answering platform** for e-commerce product specs and store policies. The engineering contribution is a **high-concurrency Go gateway that acts as an admission controller and resource governor**, using RAG-aware caching to perform **load conversion** — turning compute-bound LLM generation into memory-bound cache lookups — so a fixed 16 GB machine absorbs redundant load without swapping or OOM. Its research claim is that **retrieval provenance** beats embedding similarity as a reuse-safety signal, tested with a *deterministic* source-overlap rule. The contribution is weighted **60 % systems design / 25 % applied-LLM / 15 % semantic cache** (proposal §2 *Contribution Profile*). The full framing lives in `docs/Final_Proposal.md` — read §1 "Proposal at a Glance" and §2 "Contribution Profile" first.

## Workflow

This repo has an enforced workflow. **Read `.claude/README.md` once before working here.**

- **Weekly:** `/week` (what is due) → work → `/log` (hours, blockers) → `/gate` (run the exit test for
  real). `/task-status` answers "where am I".
- **Changes:** `/task <slug>` opens a design trail under `.docs/work/`; `/approve <phase>` is a **human**
  decision; `/verify` → `/ai-review` → `/done`. On a failed `/verify`: exactly **one** quick fix, then
  `/rca` takes over. **Tests are immutable** unless an RCA proves staleness and the human confirms.
- **Commands:** use the **Makefile** (`make help`) — do not invent ad-hoc invocations.
- **Hooks enforce two things.** `frozen-guard.sh` is armed *always*: it blocks edits that configure a
  frozen value, edits to the three frozen docs, and writes to `results/*/raw/`. `gate-check.sh` blocks
  source edits without approval from **W8** onward (lightweight in the W5–W7 runway, ADR-020).
- **The intended path through a frozen change is `/adr`**, then cite the ADR in the task's
  `approvals.md`. Never edit `.docs/ai/frozen-values.txt` to dodge a block.

## Documents

- **`docs/design/architecture.md`** — **the folder-structure and module-boundary authority.** Read it
  before creating a directory or adding an import; it says where each package lives and what it may
  depend on.
- **`.docs/ai/rules.md`** — the ten trip-wires this repo actually falls over, each citing its governing
  section. `.docs/` is the AI trail and is separate from human-authored `docs/`.
- **`docs/worklog/`** — one file per week, append-only; the raw material for the W20–W22 write-up.
- **`docs/Final_Proposal.md`** — the source of truth. Defines the three contributions, system architecture, tech stack, research questions, evaluation design, and scope guardrails. Any code written must match the architecture and terminology defined here (§6 Architecture, §7 Technical Stack).
- **`docs/time_line.md`** — week-by-week execution plan at ~15 h/week: **runway W5–W7 (submit Aug 31), thesis W8–W22 (complete Dec 13)** — see ADR-020. Check this for what's in scope *right now*.
- **`docs/defense_demo.md`** — the defense demo script (five live steps + a recorded load clip that is the only demonstration of scalability) and the input/output contract the debug UI must expose. Any UI/API work should conform to this contract, including the **required** counters sidebar.
- **`docs/interfaces.md`** — interface & data contracts (HTTP `/ask`, Go↔Python gRPC incl. a retrieval-only RPC for the reuse cascade, the stable chunk-ID scheme, Redis cache/dependency schemas, invalidation event). **Frozen at v0.2** — code at the seam must conform, and changes require a `decisions.md` entry.
- **`docs/experiment-protocol.md`** — reproducibility: run-manifest schema, operational metric definitions, the frozen LLM-judge prompt, statistics, and the pre-registered headline results. Experiment/measurement code conforms to this.
- **`docs/decisions.md`** — decision log (ADRs): frozen choices and open questions with decide-by weeks. **ADR-016 is the scope reduction**; **ADR-021 (2026-08-15) replaced the generation LLM** (Gemma 4 E4B → Qwen 3.5 2B) after the originally frozen model failed the W5 memory-envelope spike on this machine's real available RAM — read it before trusting a "Gemma" reference anywhere else (older prose in `Final_Proposal.md`/`README.md` may still say Gemma; `decisions.md` is authoritative). ADR-003 (embedding model: `nomic-embed-text`) and ADR-014 (chunking) are also Decided now.
- **`docs/data-card.md`** — corpus/workload provenance, licensing, schemas, versioning (filled and frozen at **W5**).
- **`docs/archive/pre_thesis-Proposal.md`** — ⚠️ **superseded**, retained as the record of the full design space. Its section numbers do not match the current proposal. Never code against it, and don't treat features described there as in scope.
- **`README.md`** (repo root) — landing page and document index.

## Intended architecture (from the proposal — binding once code lands)

Two-tier cache in front of a RAG pipeline, decoupled by language/responsibility:

- **Go gateway** (the contribution) — an **active admission controller and resource governor**, not just a proxy: concurrent request handling; a **bounded generation-concurrency pool** (semaphore) sized to the memory envelope; **backpressure / graceful load shedding** (`503 busy, retry`) so overload never swaps/OOMs; Tier-1 exact-match cache (hash lookup); Tier-2 semantic cache (embed + similarity search + the **source-overlap reuse rule**); request coalescing (`singleflight`); and a **thread-safe source→entry dependency map** for invalidation (read-mostly, guarded by `sync.RWMutex` or `atomic.Pointer` copy-on-write, mutated out-of-band by a channel-fed writer goroutine). This is where the systems and research contributions live and where most engineering effort belongs.
- **Python RAG service** (infrastructure, invoked on a cache miss or for the cascade's retrieval-only call) — corpus ingestion/chunking/embedding (LlamaIndex), retrieval, calls the local LLM. Communicates with Go over gRPC.
- **Local LLM** (**Qwen 3.5 2B** via Ollama, 4-bit `q4_K_M`, `num_ctx` fixed at 8192, **`think: false` required on every call** — ADR-021, supersedes the originally-frozen Gemma 4 E4B) and a separate **embedding service** (**`nomic-embed-text`, 768-dim** — ADR-003) — both consumed as black boxes, not modified. Ollama runs **natively on the host**, never in Docker: macOS containers have no Metal GPU passthrough, and a CPU-bound LLM invalidates every latency measurement.
- **Redis** — cache store + vector search for Tier 2.

Full request-flow diagram and component responsibilities: `docs/Final_Proposal.md` §6.

## Constraints that any code change must respect

- **Cache only the "stable" slice** (product specs, policies) — dynamic content (stock/price/order) must classify-and-bypass to a live source, never enter the cache (proposal §6.3).
- **Freeze the LLM and embedding model** once chosen — swapping either mid-study invalidates every cross-configuration comparison (proposal §12).
- **Bounded cache**: fixed capacity, LRU eviction, always — no unbounded-cache assumptions (proposal §6.3).
- **Hardware envelope**: all experiments target a single MacBook M1, 16 GB unified memory, with `OLLAMA_NUM_PARALLEL` pinned and reported (frozen at **4**, ADR-017). In practice this machine also runs other, unrelated projects — the author keeps them to **~9-10 GB used / ~5-6 GB free before any Ollama test**, which is a materially tighter real constraint than "16 GB nominal" and is what actually drove ADR-021 (see below). Load generation must run off-box (a second machine), not co-hosted with the system under test (proposal §7).
- **Govern admission to the memory envelope.** The gateway must bound in-flight generations to what unified memory can hold (permit pool sized to `OLLAMA_NUM_PARALLEL` + headroom) and shed with backpressure rather than admit work that swaps/OOMs; runs are valid only in macOS green memory pressure — yellow/red runs are discarded and repeated at lower load (proposal §7, `docs/experiment-protocol.md`).
- **Provenance-first, and deterministic.** The reuse decision is `overlap(retrieve(q), sources(e)) ≥ θ ∧ sim(q,e) ≥ τ` — source-chunk overlap, not embedding similarity alone. It is a **rule computed in Go** (set intersection over chunk IDs), not a learned model; there is no ML runtime on the hit path. Both θ and τ are swept, never hand-set.
- **Invalidation is blind dependency-purge.** Source edits purge every dependent entry via the dependency map — guaranteed-complete. Predictor-gated purging was **removed** (`decisions.md` ADR-010, superseded by ADR-016). The update set's `substantive`/`cosmetic` split exists to *measure* over-invalidation, never to gate it.
- **Single-node envelope; no scale-out.** Horizontal scaling / multi-pod, DB sharding/partitioning, and a fronting load balancer (NGINX / Elasticsearch) are out of scope — the contribution is single-envelope load conversion; scale-out (incl. distributed cache coherence for the invalidation map) is future work (proposal §14, ADR-009).
- **δ ≤ 5%** is the provisional false-hit budget (proposal §10) — the target operating point for any θ/τ tuning until the judge's measured error finalizes it. Report rates with **Wilson score intervals**.
- **Five cache configurations**, not eight (proposal §9.2): no-cache · exact-only · fixed-τ (also GPTCache's rule) · source-overlap rule · full tiered system.
- **Do not reintroduce cut scope.** The learned reuse-safety predictor, predictor-gated invalidation, GPTCache/vCache *integration*, semantic routing (RQ4), SSE streaming, and the **bypass classifier** (ADR-018 — demo stub only, not evaluated) are **out of scope** and live in proposal §14 as future work. If a task seems to need one of them, flag it rather than building it.
- **Three correctness invariants from the advisor review** (`interfaces.md` v0.3, ADR-005/019) — each closes a *silent* failure path, so none is optional:
  1. **Two Redis eviction regions.** Cache entries under LRU; `dep:*` / `entry:*` under **`noeviction`**. An evicted dependency record makes its entries unpurgeable and breaks invalidation completeness with no error.
  2. **`t1_key` on every Tier-2 record.** The Tier-1 hash is not computable from `entry_id`, so without it purges silently miss Tier 1.
  3. **Epoch-guarded write-back.** Retrieval stamps `dataset_epoch`; write-back discards if it advanced. Otherwise a generation in flight during an edit resurrects stale data after the purge.
- **C1 validity is method, not polish** (ADR-019): the reference-free labelling ablation, validation/test split by seed cluster, and the decisions-changed-by-provenance metric sit **above** judged-sample size in the drop order. Never quietly trade them for a bigger sample.
- **The envelope is measured, not assumed** (ADR-017, decided 2026-08-15). Frozen at **`num_ctx=8192`, `OLLAMA_NUM_PARALLEL=4`** from the W5 feasibility spike — μ_gen ≈ 28.2 tok/s aggregate at that pair, green pressure. The spike also forced **ADR-021**: the originally frozen Gemma 4 E4B entered yellow pressure at even the lightest config on this machine's real available RAM, so generation moved to Qwen 3.5 2B after empirically comparing five candidate models on both memory footprint and RAG-QA quality. Embeddings are served by **Ollama** (`nomic-embed-text`, 768-dim — ADR-003), never an in-process PyTorch stack (~2 GB for a ~400 MB model).
- **The platform is the thesis.** Non-negotiable: tiered caching, source-aware invalidation, the concurrency-safe gateway with admission control and memory-pressure discipline, the load-testing evaluation. Everything else follows the drop order in proposal §12 — assume it's optional and don't gold-plate it.
