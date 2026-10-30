# `gateway/internal/httpapi/` — the HTTP endpoints and the request path

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `handler.go` (751 lines), `cascade.go` (227), `invalidate.go`
(155), `browse.go` (145), `types.go` (79), `doc.go`, and 15 test files (89 tests). Governing contracts:
`interfaces.md` §A (`/ask`), §E (`/invalidate`), §H (the record).

## 1. Purpose

It serves the gateway's four endpoints and runs one request through every tier. It is the only package that
imports its siblings: it wires the cache, the reuse rule, admission, coalescing, the dependency map and the log
together. It serves **S1, S2, C1, C2 and C3** at their meeting point.

| Endpoint | Handler | For |
| :--- | :--- | :--- |
| `POST /ask` | `Ask` (`handler.go`) | a question; the measured path |
| `POST /invalidate` | `Invalidate` (`invalidate.go`) | a source edit; loopback only |
| `GET /products` | `Products` (`browse.go`) | the demo's product list |
| `GET /stats` | `Stats` (`browse.go`) | the demo's counters |

## 2. Boundaries

- The **cascade** (`cascade.go`) is Tier 2's plumbing; the **decision** is `reuse/`'s.
- The request path reaches the store, the dependency map and the epoch through small interfaces (`cacheStore`,
  `dependencyMap`, `epochSource`, `invalidator`), each with a compile-time check that the real type still fits.
  So every test here runs **against fakes**: no Redis, no Ollama, no Python.

## 3. Files

### `handler.go` — `Ask`, step by step

`Handler` holds the dependencies (cache, RAG client, embedder, thresholds, lane band, admission pool,
coalescing group, dependency map, epoch source, evaluation log, counters, catalog) and the run labels
(`RunID`, `ConfigID`, `Mutation`, `SupportGate`). `NewHandler` builds it; `cmd/gateway` sets the rest.

**1. Decode and set up.** Only `POST`, with a JSON body that has a `question`. The Tier-1 key is computed **once**
(`cache.Key(cache.Normalize(question), product_id)`) and reused for the Tier-1 lookup, the coalescing key and Tier
2's `t1_key`, so the formula cannot drift. The record is created with its run labels (`support_gate`,
`mixed_lane`, `config_id`, `mutation`) already set, and **one deferred function writes it**: whatever path returns,
exactly one record is logged, and the demo counters are bumped from the same record.

**2. Tier 1.** `Cache.Get`. A hit whose entry is **tombstoned** (`Deps.Invalidated`) is refused, named in
`invalidated_entry_id`, and the request goes on as a miss. A live hit is touched (LRU) and served as
`TIER1_HIT`. A Redis error is a 500.

**3. Embed and retrieve, in parallel.** Two goroutines: `Embed.Query` and `RAG.Retrieve` (scoped by `product_id`,
`topK = 0` so Python's `TOP_K` applies). Either failure **degrades to a miss**, never a 500: a Tier-2 outage should
cost hit rate, not availability, and a 500 fits no category the evaluation counts. Both spans are timed on their
own; they overlap, so they no longer add up to the total.

**4. Tier 2** (`tryTier2`, below). The outcome fills the record (`recordCause`): similarity, cause, support values,
the containment counterfactual, the candidate, and `tier2_search_failed`.

**5. A served Tier-2 hit** (cause `NONE`): `TIER2_HIT`. Two background writes, each with its own timeout and
**detached** from the request, so neither adds a Redis round-trip to the hit path: `BumpHitCount`, and a
**promotion** of the entry into Tier 1 under this question's key (`Put` with `Promotion`, written only while the
`t2:` record exists).

**6. A miss.** Inside `Generations.Do(t1Key, …)` (coalescing), the leader:
1. takes a permit (`Admission.Acquire`), released when the closure ends;
2. calls `RAG.Answer` with the chunk IDs it already retrieved, so the server does not retrieve again;
3. **the epoch guard**: reads the epoch and, on any difference from `Answer`'s epoch or a read error, discards
   the write-back (`writeback_discarded: true`) but still returns the answer;
4. mints one `entry_id` and computes the new entry's **own** lane and namespace from the answer's sources (not the
   query's);
5. writes Tier 1 (`Put`) and, if there is a vector, Tier 2 (`PutTier2`, with `t1_key` and `dataset_epoch`). A
   failed write **never fails the request**: the generation is the most expensive thing in the system;
6. **registers** the dependencies (`Deps.Register`) whatever the two writes returned, with no context;
7. touches the entry, then trims to `CACHE_CAPACITY` (`TrimToCapacity`) and logs any victims.

**7. The outcome switch**, after `Do` returns, in fixed precedence: `ErrShed` → `SHED` (503, `Retry-After: 2`);
this request's own client gone → `ABANDONED` (nothing written); any other error → `GENERATION_FAILED` (502);
otherwise `MISS` (200). `t_generate_ms` is copied **before** the switch, so every outcome carries it.
[`Admission Control.md`](../../Admission%20Control/Admission%20Control.md) §7 has the full table.

**Helpers.** `touch` swallows its error (a missed LRU touch costs only a little hit rate). `durMS` and `msPtr`
convert durations; **`msPtr` returns nil for zero**, so a stage that did not run is `null` (and so is a zero
permit wait, finding F-N). `stratumHeader` reads the load generator's stratum label from a request header.
`topKServerDefault = 0` and `modelUsedConstant = "qwen3.5-2b"` mirror Python's config.

### `cascade.go` — `tryTier2`

1. **No retrieval, or a retrieval with zero chunks → no candidate.** Checked before any namespace is derived:
   otherwise the SPEC lane would fall back to the `product_id` alone and could serve an entry with no evidence.
2. `reuse.Classify` gives the lane; `reuse.Namespace` gives the namespace. An empty namespace → no search.
3. **One scoped search**, `NearestTier2InNamespace(vec, ns, 1)`. k = 1 is enough: every result is in the
   namespace, so the most similar one is the best one. A search **error** sets `SearchFailed` (run rule 12: the run
   is then inadmissible) and degrades to a miss.
4. **A tombstoned candidate is dropped** before it is judged: a miss with no cause.
5. `reuse.DecideLane` gives the lane verdict; if `similarity ≥ τ`, `reuse.Decide` computes the **containment
   counterfactual** (logged, never served).
6. `reuse.Judge` gives the one cause, with **this request's** evidence (`retrieved.Texts`, `retrieved.ChunkIDs`),
   never the entry's sources, and with `h.SupportGate`, the same field that labels the record.
7. One log line shows both verdicts side by side.

`stageTimings` holds §F's four hit-path spans (Tier 1, embed, search, rule). `tier2Outcome` is returned even for a
refused candidate, so a refusal still logs its similarity.

### `invalidate.go` — `POST /invalidate`

Covered in [`Invalidation.md`](../../Cache_Invalidation/Invalidation.md) §8. In short: method `POST` only (405),
loopback callers only (403), a body of at most 1 MB that is exactly the §E event with no unknown fields and a
`change_type` of `substantive` or `cosmetic` (400), then `InvalidateWait`. It answers 503 with no map or a closed
map, 500 if any entry failed, else 200 with `purged`, `failed` and `errors` (never null). It never refuses under
`MUTATION=off`: refusing a purge would leave stale entries.

### `browse.go` — the demo endpoints

`Counters` (`requests`, `tier1_hits`, `tier2_hits`, `misses`, `shed`, `coalesced`, `generations_run`, and the derived
`generations_avoided` and `hit_rate`) are bumped from each finished record, so they cannot disagree with the log. `Stats` serves them; `Products` serves `catalog.Products` (an empty
list when there is no catalog). Neither is on a measured path.

### `types.go`

`askRequest` (`question`, optional `product_id`) and `askResponse` (§A: `answer`, `cache`, `latency_ms`,
`similarity`, `source_overlap`, `sources`, `model_used`, `request_id`, plus the extensions `lane`, `namespace`,
`reuse_rule` and `overlap_decision`), and the `cache` outcome names (`TIER1_HIT`, `TIER2_HIT`, `MISS`, `SHED`,
`ABANDONED`, `GENERATION_FAILED`). `overlap_decision` is in the **response** only, not in the evaluation record. The
response's `cache` is `TIER1_HIT`, `TIER2_HIT` or `MISS`; `interfaces.md` §A also lists `BYPASS`, which the gateway
never sends (the bypass classifier is out of scope).

## 4. Callers and callees

- **Built and wired by** `cmd/gateway/main.go`, which registers the four routes (and the UI at `/` when `UI_DIR` is
  set).
- **Calls** `cache`, `embed`, `ragclient`, `reuse`, `coalesce`, `admission`, `deps`, `telemetry`, `catalog`.

## 5. Tests that pin it

89 tests in 15 files, all against fakes. Item 1.2's rule: **every exit path of `Ask` has a test asserting both its
response and its record**.

| File | Tests | Covers |
| :--- | ---: | :--- |
| `ask_test.go` | 20 | each exit path, coalescing wraps admission, no sharing across products, write-back failure still serves |
| `cause_test.go` | 16 | the refusal cause on every path, including a stale server (`NOT_SCORED`) |
| `generatems_test.go` | 8 | `t_generate_ms` on leaders, followers, failures |
| `support_gate_test.go` | 8 | both gate arms, labelled and behaving as labelled |
| `abandon_test.go` | 7 | ABANDONED classification, including a real disconnect and a live follower (F-D) |
| `cascade_test.go` | 7 | the cascade's response fields, `overlap_decision` |
| `invalidate_test.go` | 7 | every status of `POST /invalidate` |
| `epoch_guard_test.go` | 6 | the write-back guard discards on any epoch difference |
| `invalidation_test.go` | 4 | a tombstoned entry is refused on Tier 1 and dropped on Tier 2 |
| others | 6 | the answer store, the MIXED arm, promotion, a Tier-2 search error |

## 6. Silent failures to watch

- **Classifying a request from the leader's context** inside the coalescing closure would give every follower the
  leader's cancellation. The switch reads **this** request's context, after `Do` returns.
- **Feeding the support gate the entry's sources** instead of the fresh retrieval would score the old answer
  against its own evidence.
- **A new return path** that bypassed the deferred emit would lose its record. Keep the single deferred emit.
- **Records lost at shutdown** (F-F) and the null permit wait on the fast path (F-N): see
  [`telemetry.md`](telemetry.md).
- **`CONFIG_ID` only labels the record today.** Every configuration runs the same path until item 6.0 builds
  configuration selection.

## 7. Commit

`29b24a6`.
