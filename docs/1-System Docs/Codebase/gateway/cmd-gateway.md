# `gateway/cmd/gateway/` — start-up, configuration and shutdown

**Describes:** commit `29b24a6` (30 Oct 2026); last changed in `68d732e` (item 4.4). **Files:** `main.go` (491 lines)
and nine test files.

## 1. Purpose

It reads the configuration, refuses a bad one **before** it touches anything, builds every part, wires them into
the `httpapi.Handler`, serves HTTP, and on shutdown drains everything and **decides whether the run is
admissible**. It serves **C3**: a run that was configured wrong, or lost records, must fail loudly.

## 2. Boundaries

- It imports `httpapi` and every leaf package `httpapi` uses except `coalesce` (`docs/architecture.md` §2).
- `main()` itself has **no test**. Every rule that can be tested is a pure function next to it
  (`retiredEnv`, `gateFromEnv`, `bandFromEnv`, `epochFromEnv`, `incomplete`, `finishRun`), and two tests read
  `main.go`'s source to check the wiring.

## 3. `main.go`

### Start-up order

1. **Refuse retired or bad settings**, before Redis, the log or the port is opened: `retiredEnv`, then
   `gateFromEnv`, `bandFromEnv` and `epochFromEnv`. A typo burns no run ID.
2. Connect to Redis and dial the RAG service (`ragclient.New`).
3. `cache.NewStore` and **`EnsureCacheIndex`**: create `idx:cache` if needed and **wait until it is complete**; a
   scan longer than 10 s stops the gateway.
4. `deps.New(rdb, store, 1024)` and `SetEpochSource(epochFile)`.
5. The embedder, the thresholds, the lane band, the admission pool, the cache capacity and the evaluation log,
   each **logged** at start with what it means.
6. Build the handler and set **every** dependency on it. `Deps`, `Epoch` and `Invalidator` are always set:
   without them the gateway would register nothing, never discard a stale write-back, or answer 503 to every
   edit, all with no error.
7. Print the support-gate arm **read back from the handler**, not from the parsed variable, so a forgotten
   assignment would show.
8. Register the routes (`/ask`, `/invalidate`, `/products`, `/stats`, and the UI at `/` when `UI_DIR` holds an
   `index.html`) and serve.

### Every environment variable

| Variable | Default | Rule |
| :--- | :--- | :--- |
| `REDIS_URL` | `localhost:6379` | |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | for the query embedding |
| `RAG_GRPC_ADDR` | `localhost:50051` | |
| `HTTP_ADDR` | `:8080` | |
| `DATASET_EPOCH_FILE` | **none** | required; an **absolute** path to a file holding an integer ≥ 1, else the gateway refuses to start (ADR-008) |
| `SUPPORT_GATE` | `on` (unset) | exactly `on` or `off`; set-but-empty, `ON` or ` off` stop the gateway |
| `LANE_SIGMA`, `LANE_SIGMA_HI` | 0.20, = `LANE_SIGMA` | the band must be one of ADR-016's two: [0.20, 0.20) (MIXED off) or [0.20, 0.60) (on); anything else stops the gateway |
| `REUSE_TAU` | 0.85 | a demo value, swept for anything reported; not a number stops the gateway |
| `REUSE_THETA` | 0.60 | the containment counterfactual only (ADR-019) |
| `REUSE_TAU_HIGH` | — | **retired** (ADR-004): any non-empty value stops the gateway, because an operator who sets it expects a similarity-only run |
| `OLLAMA_NUM_PARALLEL` | 1 | the admission permits; anything but 1 prints a warning (ADR-003) |
| `GEN_QUEUE_BUDGET` | 2 × permits | the queue budget `q`; pre-registered for item 7.5 |
| `CACHE_CAPACITY` | 0 (unbounded) | entries, LRU, enforced by the gateway; unbounded is logged as giving upper-bound hit rates |
| `RUN_ID` | "" | empty turns the evaluation log off (`make dev`); a reused ID stops the gateway (write-once) |
| `RESULTS_DIR` | `experiments/results` | where `{RUN_ID}/raw/` goes |
| `CONFIG_ID` | 0 | **a label only** until item 6.0; not an integer stops the gateway |
| `MUTATION` | `off` | **a label only**, and **not validated**: any string is written to the record |
| `UI_DIR` | "" | the built demo page |

**Why `SUPPORT_GATE`, the lane band and the epoch file use `os.LookupEnv`.** `getenv` reads an empty value as
unset, so `SUPPORT_GATE=` would quietly run the default arm under a run ID meant for the other. These three tell
"unset" from "set but empty" and refuse the second.

### Shutdown order, and the run verdict

On SIGINT or SIGTERM, `srv.Shutdown` gets 10 s to finish in-flight requests. Then:
1. **`depMap.Close`** drains the dependency writer. A registration that arrives after it is counted in `Dropped()`.
2. If the map dropped, failed to register or failed to purge anything, a warning says the map is **incomplete**.
   `LateDiscards` are reported separately: they are discarded write-backs, not incompleteness.
3. **`finishRun`** closes the evaluation log **first** (which drains its buffer), **then** reads its counters. Read
   before, they would under-count and an incomplete run would look complete.
4. **`incomplete`** names every condition that makes the run inadmissible: dropped records, failed line writes,
   missing answer files, guard refusals, Tier-2 search errors (run rule 12), or a failed close. If any fired, the
   gateway exits with **`THIS RUN IS INCOMPLETE`**.

**Known gap (finding F-F):** `ListenAndServe` returns as soon as `Shutdown` **starts**, and `main` does not wait for
it to end, so the log can close while handlers are still running. Requests in flight at SIGTERM can vanish with
`Dropped()` at 0. Until it is fixed, stop the load before SIGTERM.

### `spaHandler(dir)`

Serves the built demo page: a real file where one exists, `index.html` everywhere else, so the page's own router
can own paths like `/p/{doc_id}`. The UI is served by the gateway, so no Node process runs at demo time.

## 4. Callers and callees

- **Started by** `make dev` (with `rag.server`), the live checks (`make epoch-race-check`, `make update-set-check`),
  and by hand (`go run ./cmd/gateway`).
- **Builds** every internal package and wires them into `httpapi.Handler`.

## 5. Tests that pin it

| Test | Guarantees |
| :--- | :--- |
| `TestRetiredEnvRefusesTauHigh` | `REUSE_TAU_HIGH` stops the gateway |
| `TestGateFromEnv`, `TestGateFromEnvErrorShowsTheValue` | only `on` / `off`; the error shows the bad value |
| `TestBandFromEnv`, `TestBandFromEnvRunsBeforeSideEffects` | only the two pinned bands; checked before anything opens |
| `TestEpochFromEnv`, `TestEpochFromEnvRunsBeforeSideEffects` | the epoch file rules; checked before anything opens |
| `TestMainWiresDeps`, `TestMainWiresEpoch` | `main.go` sets the dependency map and the epoch source (they read the source file) |
| `TestIncompleteNamesTheConditionThatFired`, `TestIncompleteReportsTheCounts`, `TestACleanRunIsComplete`, `TestIncompleteNamesTier2SearchFailures` | the run verdict |
| `TestFinishRunReadsTheCountersAfterTheBufferHasDrained` and three more `TestFinishRun*` | close first, read the counters after |

## 6. Silent failures to watch

- **`CONFIG_ID` and `MUTATION` are labels only.** Setting `CONFIG_ID=1` still runs the full system, and `MUTATION`
  accepts any spelling. A record's `config_id` does not yet name the path that ran (item 6.0).
- **`OLLAMA_NUM_PARALLEL` above 1** only warns. A measured run must check `permits` against `make env-check`'s
  `ENVELOPE` line.
- **`CACHE_CAPACITY=0`** gives upper-bound hit rates. Set it to `round(0.25 × K)` for a measured run.
- **F-F at shutdown** (above).

## 7. Commit

`29b24a6`.
