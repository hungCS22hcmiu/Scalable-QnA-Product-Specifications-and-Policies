# Impact (via `impact-analyst`)

**Lead risk.** W6 is where frozen values get written into code for the first time.
`generate.py` hardcoding `think: false` / `num_ctx` / model tag, and Go choosing a `top_k` for
`AnswerRequest`, are the two places drift is born silently. `top_k` is the worse one — the proto
makes **Go** the sender, and Go has no config pinned to ADR-014. Decision: Go sends `0` = "server
default"; Python resolves from `config.TOP_K`. Never a literal `5` in Go.

## 1. Packages touched / layering

| Package | Change | Layer check |
| :--- | :--- | :--- |
| `rag/src/rag/generate.py` | new — Ollama call | leaf; imports `config` only |
| `rag/src/rag/server.py` | new — gRPC `Answer` + `Retrieve` | right end of seam; never calls back into gateway |
| `gateway/internal/httpapi` | `POST /ask` | OK |
| `gateway/internal/cache` | Tier-1 only | OK, see trap below |
| `gateway/internal/ragclient` | pooled conn, epoch pass-through | OK |
| `gateway/cmd/gateway/main.go` | wiring | must stay logic-free |
| `gateway/internal/ragpb` | generated, untouched | not in `architecture.md` §1's canonical tree — pre-existing doc drift, worth a one-line fix separately |

**Respected, with one trap.** No left-pointing import. `admission/` being absent (W16–17) is a
temporal gap, not a violation — but the miss path must be a *single* call site
(`httpapi`: `cache.Get` → miss → `ragclient.Answer` → `cache.Put`) so admission has exactly one
place to insert later. A read-through `cache` that owns the miss path is how `cache/` would grow a
reuse decision it must never make. Tier-1 avoids the trap **by construction** — sha256 equality is
not a judgement — provided normalization stays exactly ADR-015 (lowercase, collapse whitespace,
strip punctuation). Adding stemming/stopwords/synonyms would be both a smuggled reuse decision and
an ADR-015 change.

## 2. Frozen artifacts — invoked, not changed

Cite in `approvals.md`: **ADR-021** (`qwen3.5:2b-q4_K_M`, `think: false`), **ADR-017**
(`num_ctx=8192`, `NUM_PARALLEL=4`), **ADR-014** (`top_k=5`), **ADR-003** (indirect, via
`retrieve.py`). No new ADR needed. **Invalidates: none** — `experiments/results/` has no run
directories yet. Pin generation values in `rag/src/rag/config.py`, not inline in `generate.py`.
`OLLAMA_NUM_PARALLEL` is a server-side env var, not a request option — setting `num_ctx` per
request while the server config differs would be silent divergence. `frozen-guard.sh` will fire on
these lines; that's correct — cite the ADRs to release it.

## 3. Reinstatement — no

Tier-1 stays hash-exact. SSE risk is real but containable: `Answer` is `stream AnswerChunk` at the
transport level (frozen shape), so W6 emits **exactly one terminal chunk** (`done=true`) and Go
accumulates. No per-token emission; `httpapi` does not handle `Accept: text/event-stream`.

## 4. Dependencies — sign-off required (rules #9)

`gateway/go.mod` has zero requires; `go build ./...` fails today. Needed: `google.golang.org/grpc`
+ `google.golang.org/protobuf` (mandated by the proto/ADR-007), `redis/go-redis/v9`. **Cut
Gin/Fiber** — `interfaces.md` §A is one JSON POST route; stdlib `net/http` suffices, and Fiber's
`fasthttp` breaks the `context`/timeout semantics W16 admission work needs. Expected ~20 MB RSS
compile-time footprint. Python: **no new deps** (`grpcio`/`protobuf`/`httpx` already declared).

## 5. Contract phase — NOT required

Implements §A/§B/§D as written; no `.proto` edit. Two non-wire-change notes to carry into `plan.md`:
- **`t1_key` cannot be written at W6** — it's a *Tier-2* field; no `t2:` record exists until W7.
  W6 mints `entry_id` (ULID) on Tier-1 write-back only. Consequence: W6 Tier-1 entries are
  invisible to the W9–11 dependency map — **flush the cache when Tier-2 lands**, before any
  measured run.
- **Redis regions.** `corpus:*` / `idx:corpus` already live in Redis from W5. A global
  `allkeys-lru` would make corpus vectors evictable — a silent retrieval failure. Use the
  logical-DB split (or `volatile-lru` + TTL only on `t1:*`) now. Leave capacity unset (ADR-005,
  Open, due W8). Don't touch `dataset:epoch` (that's `deps/`'s region, W9–11);
  `dataset_epoch` stays a `DATASET_EPOCH_STUB = 0` constant, but build the write-back comparison
  anyway so the path exists.

## 6. Experiment phase — NOT required

p50 miss latency is a Done-when number for `docs/worklog/W06.md`, not a campaign: no `run_id`, no
`manifest.yaml`, no `results/*/raw/` write. Label it non-citable (`dev-v0`, ADR-020). Create no
`experiments/scripts/` (that's W7). Reuse §A's existing `latency_ms` semantics rather than
inventing a metric. (Filling `experiment-protocol.md` §1.1's `TODO(W6)` footprint rows is a
separate frozen-doc edit, not part of this task.)

## 7. Smallest-change trims (fed into `plan.md`)

Cut Gin/Fiber (stdlib `net/http`). Cut `singleflight` (that's admission-adjacent, W16–17 — adding
it in front of an unbounded miss path is the wrong order). Cut any connection-pool abstraction
beyond one long-lived `*grpc.ClientConn` at startup — gRPC multiplexes, "pooled" just means
not-per-request. Cut `similarity`/`source_overlap` computation, but **emit the full §A response
shape with `null`s** so W7/W12 add values, not fields.

## Required phases

**impact · implementation.** Contract and experiment phases: not required (see §5, §6 above).
