# Impact — fa-abandonment-classification

*`impact-analyst` (opus), 2026-10-05. Recorded as returned. The corrections it implies for `spec.md`
are listed at the end. They are **not** applied here. Every probe ran in a scratch copy of the
module in the session scratchpad. Nothing was committed, Ollama was not called and no model was
loaded. Memory pressure read 2 (urgent) throughout. That voids nothing here, because no probe
measured a latency.*

> **No frozen value is touched and no run is invalidated, because no run exists.**
> `experiments/results/` holds only `.gitkeep`.
>
> **The fix is correct, and it is the right size.** The probe was run in a scratch copy, with
> `err != nil && ctx.Err() != nil` added to the `ABANDONED` case (`handler.go:494`). A disconnect
> while `Answer` is in flight then becomes `ABANDONED` with nothing written. Today it is
> `GENERATION_FAILED` with a 502. This holds both through the harness and through a real `net/http`
> server with a real client. These are unchanged:
> - every outcome a live client receives;
> - every upstream status received by a live client;
> - `SHED`;
> - a completed generation.
>
> The whole existing suite passes with the fix under `-race`.
>
> **Four wrong versions of the fix also pass the whole existing suite (measured).** The spec's
> acceptance list catches two of them: keying on the status code and dropping the `err != nil`
> guard. It misses the other two:
> - **M-closure.** Classify inside the coalesced closure, or in `ragclient`, from the *leader's*
>   context. A live follower of a leader cancelled during `Answer` then flips from a 502 to
>   `ABANDONED` with nothing written, which is an empty 200 on the wire. That widens F-D.
> - **M-order.** Place the new case above `ErrShed`. A request whose client is gone and that meets
>   a full pool and queue then moves from `SHED` to `ABANDONED`, which moves S2's shed rate.
>
> **New finding, F-L (the name is a proposal): `rag.server` keeps generating after its RPC is
> cancelled.** Probed with a stubbed `generate`, so no Ollama: the client cancelled at +0.20 s, and
> the stub ran on to +1.50 s.
> - The gateway therefore releases its one permit while Ollama's one slot is still busy.
> - The next admitted request queues **inside Ollama**. That is the invisible queue ADR-003 says
>   admission exists to prevent.
> - It is out of scope here. It must be fixed, or shown not to occur, before Phase 7, and item 1.6
>   must record the abandonment count.
>
> **A real disconnect cancels `r.Context()` only once the request body has been read to EOF
> (probed).**
> - An exact `Content-Length` body is detected at once. That is what k6, curl, urllib and the UI
>   send.
> - A body with trailing bytes is never detected, and neither is a chunked body whose terminator
>   has not arrived. The request runs to completion and is recorded `MISS`.
> - The existing queued-`ABANDONED` path depends on this as much as the fix does.
>
> **The contract phase is not required. The experiment phase is required, but only to record.**
> No field or enum value moves. What the `ABANDONED` and `GENERATION_FAILED` buckets count does
> change, and the precedence rule that decides it is written down nowhere yet.

## Packages touched

| Path | Change | Layering |
| :--- | :--- | :--- |
| `gateway/internal/httpapi/handler.go:494` (comment at `:495-496`) | Add `err != nil && ctx.Err() != nil` to the `ABANDONED` case, or as a separate case. It must sit **below** `ErrShed` (`:478`) and **above** `case err != nil` (`:500`). It must read `ctx` from `:158`, the request's own context, **in the switch, never inside the `Do` closure** | No import added: `context` and `errors` are already imported (`:4`, `:8`) |
| One **new** `httpapi` test file | The acceptance tests. Acceptance 4's seam is a local type that wraps `*fakeStore` and cancels the request's context in `Put`, assigned to `hs.h.Cache`. **The harness needs no change** | Test-only |
| Behaviour changed, file not edited | The §H `cache` value on the paths in §1's table. HTTP on the same paths: a 502 becomes nothing written, to a client that is already gone. stderr: the `ABANDONED` log line (`:498`) now fires for those paths. The `GENERATION_FAILED` case logs nothing (`:500-503`) | — |
| **Unchanged** | `admission/pool.go`, `coalesce/`, `ragclient/`, `telemetry/`, `Counters` (`browse.go`), `cache/`, `reuse/`, `cmd/gateway`, `.proto`, `rag/`, `ui/`, `experiments/`, every existing test file | — |
| At `/done` | `super-plan.md:158-160` (F-A resolved), plus F-L (§5). `ask_test.go:369-370`'s comment becomes false (correction 6) | — |

## 1. Blast radius

**Layering is respected (CONFIRMED).**
- `httpapi` is the leftmost package (`architecture.md:90`), and the fix adds no import.
- Keying on the gRPC status code would import `google.golang.org/grpc/{status,codes}` into
  `httpapi`. That leaks `ragclient`'s transport into the HTTP layer, which is a second reason
  against it.

**Frozen values touched: none (CONFIRMED).**
- `num_ctx`, the slot count and `OLLAMA_NUM_PARALLEL`, the embedding model and `DIM`, `top_k`, the
  chunking, FLAT, the eviction policy, the capacity ratio, δ and `dataset_version` are all
  untouched.
- Admission timing is unchanged. The permit is released by `defer permit.Release()` inside the
  closure (`handler.go:394`) before the switch runs. The probe reads `permits_in_flight = 0` after
  every scenario, before the fix and after it.

**The measured path is touched (CONFIRMED).**
- `rec.Cache` becomes §H's `cache` (`evallog.go:34`) and feeds `Counters` (`handler.go:192`).
- The `Counters` cannot show the fix: `ABANDONED` and `GENERATION_FAILED` both count in
  `Requests` and nowhere else (`browse.go:85-86`).

**`run_id`s invalidated: none (CONFIRMED).**
- `experiments/results/` holds only `.gitkeep`, and the only commit that touched it is `3901066`.
- No `requests.jsonl` exists, either in the tree or in a filesystem-wide `find`.
- `make dev` runs with `RUN_ID` empty, so it writes no log (`main.go:201-206`).

**Outcomes, today and with the fix, measured in the scratch copy:**

| Scenario | Today | With the fix |
| :--- | :--- | :--- |
| Client cancels while `Answer` is held | `GENERATION_FAILED`, 502 written | **`ABANDONED`, nothing written**, permit released |
| Context cancelled before `Ask` (fake store) | `GENERATION_FAILED`, 502. The `Answer` RPC never reached the server | **`ABANDONED`**, nothing written |
| Upstream `CANCELED`, `DEADLINE_EXCEEDED` or `INTERNAL`, live client | `GENERATION_FAILED`, 502 | Same |
| Client leaves after `Answer` returned (during write-back) | `MISS`, 200 | Same |
| Client gone, permit and queue both full | `SHED`, 503 | Same |
| Real `net/http` server, exact `Content-Length` body, client disconnects during `Answer` | `GENERATION_FAILED`; the context was cancelled at once | **`ABANDONED`** |
| Real server, the same body followed by 2000 B of padding | `MISS` once the gate opened; **the context was never cancelled** | Same |
| Real server, chunked body not yet at EOF | `MISS`; the context was never cancelled | Same |

## 2. Every reader of `ABANDONED` and `GENERATION_FAILED`

| Reader | What it does | Depends on the misclassification? |
| :--- | :--- | :--- |
| `types.go:70-76` | Declares both. "neither served nor shed" | No. The fix makes the code match it |
| `handler.go:494-503` | The only writers | This is the change |
| `browse.go:66-87` `Counters.record` → `/stats` → `ui/src/Counters.jsx:51-57` | Both count in `requests` only | **No.** `/stats` is identical before and after |
| `telemetry/evallog.go:34` | `Cache string`, no enum check | No |
| `ask_test.go:371-401` (queued `ABANDONED`) | `context.Canceled` from `Acquire` matches `errors.Is` first | **No** (measured: passes). Its comment at `:369-370` becomes false (correction 6) |
| `ask_test.go:405-425` (`GENERATION_FAILED`) | `codes.Internal` with a live client | No. The 1.2 impact (S12) chose `Internal` precisely so as not to pin F-A |
| `harness_test.go:877-898` `recordingWriter` | "Nothing written" | No |
| `experiments/k6/ask.js:120-152` | Client side only. A k6 timeout is status 0, counted in `error_rate`. A client that left never sees the 502 | No. **Unrelated, unchanged:** an F-D empty 200 is counted in `goodput` *and* again in `error_rate` (`:139-148`) |
| `k6/mu_hit.js`, `scripts/load_burst.py:140-173`, `scripts/verify_admission.sh:60-62`, the `Makefile` demo (`:235`, `:266`), `ui/src/pages/ProductChat.jsx:6-11` | Response status or the response's `cache`. None reads the record | No |
| Any reader of `requests.jsonl` | **None exists.** The figure generators and judge are unbuilt (`super-plan.md` Phase 5) | No |
| `super-plan.md:125`, `:158-160` | Item 1.2's done-when; the F-A text | F-A is marked resolved at `/done` |
| `interfaces.md` §A `:127`, `:140` | `TIER1_HIT \| TIER2_HIT \| MISS \| BYPASS`, response only | No. Neither value reaches a response body, and the 502 is an undocumented plain-text `http.Error` |
| `interfaces.md` §H `:461` | `TIER1_HIT \| TIER2_HIT \| MISS`, which already omits all three extensions | No |
| `Final_Proposal.md` | No mention of either value. §3 `:125`: goodput excludes sheds | No |

**Verdict: nothing depends on the old misclassification (CONFIRMED).**

**The §H `cache` enum sync: this task should not do it (CONFIRMED by reading the 1.2 trail).**

The follow-up comes from 1.2's `impact.md:125-129` and `:261`, its `spec.md:96-99` and its
`plan.md:124, :159`: sync `interfaces.md` §H's enum with the six values the code emits. It does not
belong here, for three reasons:
1. **This fix neither adds nor removes a value.** It changes which existing value one class of
   request receives.
2. **The sync is a contract change.** `interfaces.md:514` requires a `decisions.md` entry and a
   version bump. Taking it on here would make this bugfix require the contract phase.
3. **The enum is not settled yet.** F-B (`cache = ""` on a Tier-1 error) is a seventh, unnamed
   outcome whose fix decides whether it gets a label. A sync done now would need a second revision.

**Recommended instead:**
- Do the sync once, after F-B and before any Phase 7 run.
- This task's experiment record (§7) should state the precedence rule in words the sync can lift
  verbatim.

## 3. Coalescing (F-D)

The fix reads **this request's own context, in the switch, after `Do` returns**. A follower's
context is live exactly when its client is connected. For a live client the new conjunct is
therefore false, and the switch reduces to today's, byte for byte. That is the structural argument.
The matrix confirms it:

| # | Cell | Leader, today → after | Follower with a live client, today → after | Follower whose client is gone, today → after |
| :---: | :--- | :--- | :--- | :--- |
| 1 | Leader cancelled while **queued** | `ABANDONED` → same | `ABANDONED`, nothing written (an **empty 200** on the wire, F-D) → **same** | `ABANDONED` → same |
| 2 | Leader cancelled **during `Answer`** | `GENERATION_FAILED` 502 → **`ABANDONED`** | `GENERATION_FAILED` 502 → **same** | `GENERATION_FAILED` → **`ABANDONED`** |
| 3 | Leader's client left **before `Answer`** (during embed or retrieve; permit taken on the fast path) | `GENERATION_FAILED` → **`ABANDONED`** | A follower joining in the microsecond window: `GENERATION_FAILED` 502 → same | → `ABANDONED` |
| 4 | Leader **succeeds**, follower's client has left | `MISS` → same | `MISS` (`TestCoalescingWrapsAdmission`) → same | `MISS`, `coalesced: true`, 200 to a dead connection → **same** |
| 5 | Leader's upstream **genuinely fails** (`Internal`), leader live | `GENERATION_FAILED` 502 → same | `GENERATION_FAILED` 502 → same | `GENERATION_FAILED` → **`ABANDONED`** |

**Evidence.** Cells 1, 2, 4 and 5 were probed (CONFIRMED). Cell 3 was reasoned: the follower
receives the same `*status.Error` value as in cell 2 (PLAUSIBLE).

**What a follower with a live client receives is exactly unchanged in every cell (CONFIRMED).** The
fix changes followers in one way only: a follower whose **own** client has gone moves from
`GENERATION_FAILED` to `ABANDONED` (cells 2 and 5). That is the rule working, but the spec's F-D
paragraph should say so (correction 8).

**Where it would change: in a fix placed anywhere other than the switch.**
- **M-closure (measured).** Normalise the error inside the closure, as in
  `if ctx.Err() != nil { return nil, ctx.Err() }` after `Answer`. The leader's raw
  `context.Canceled` then reaches every follower. Cell 2's live follower becomes `ABANDONED` with
  nothing written: **F-D's empty 200, widened from the queued cell to the `Answer` cell**. The
  whole existing suite passes.
- **Translating in `ragclient`** (`status.Code == Canceled` → `context.Canceled`) does the same to
  followers. It also files an upstream `CANCELED` with a live client as `ABANDONED`.

**The test that catches both.** Cell 2 with a live follower: assert the follower **got a written
response and is not `ABANDONED`**.
- Do **not** assert `502`/`GENERATION_FAILED`. That would pin F-D's defect.
- A future F-D fix that serves the follower (`MISS`, 200) still passes this assertion.

## 4. Does a real disconnect cancel `r.Context()` here? Only if the body reached EOF

**How `Ask` reads the body.** `json.NewDecoder(r.Body).Decode(&req)` at `handler.go:152`. There is
no `http.MaxBytesReader`, no drain to EOF, and no server timeout or `BaseContext`
(`main.go:244`, `&http.Server{Addr, Handler}`).

**net/http's behaviour (go1.26.1):**
- A request with a body starts the connection's background read only when the body hits EOF:
  `registerOnHitEOF(req.Body, w.conn.r.startBackgroundRead)` (`server.go:2060-2062`).
- Only that read sees the closed socket and cancels the context (`server.go:769-773`).
- For a `Content-Length` body, `body.readLocked` reports EOF together with the last bytes once the
  limit reaches 0 (`transfer.go:876-883`). A JSON object that ends at the final byte is therefore
  at EOF as soon as `Decode` reads it.
- `Decode` stops at the closing brace and never reads further. Trailing bytes, or a chunked
  terminator that has not arrived, leave the background read unstarted, and the server never
  learns that the client left.

**Probed** with `httptest.NewServer` around `Handler.Ask`, a real `http.Client` that cancels while
`Answer` is held, and the gate opened one second later:

| Body | Context cancelled? | Record today | Record with the fix |
| :--- | :--- | :--- | :--- |
| Exact `Content-Length`, ends at `}` | **Yes, at once** | `GENERATION_FAILED` | **`ABANDONED`** |
| `Content-Length`, JSON + 2000 B of spaces | **No** | `MISS`, `t_generate_ms` ≈ 1003 | `MISS` |
| Chunked, terminator not sent | **No** | `MISS`, ≈ 1054 | `MISS` |

**What depends on it.**
- **Both paths depend on it (CONFIRMED).** The queued path waits on `ctx.Done()`
  (`pool.go:113-114`), and the fix reads `ctx.Err()`. A disconnect the server never sees is
  recorded as whatever completes: a `MISS` counted as server-side goodput, while the client
  recorded an error.
- **The harness does not trigger it (PLAUSIBLE; k6 was not run).** k6 posts a
  `JSON.stringify` string (`ask.js:120`). `load_burst.py` (urllib bytes), `verify_admission.sh`
  (`curl`) and the UI's `fetch` with a string body all send an exact `Content-Length` with no
  trailing bytes.

**For acceptance 5:**
- Build the body as `bytes.NewReader(json.Marshal(...))`. That is the shape the probe used, and
  the test is meaningful with it.
- Say in the spec that detection rests on this framing.
- Draining the body to EOF after `Decode` (bounded by `MaxBytesReader`) would make detection
  independent of the client's framing. It is **cut** from the smallest change and recorded as a
  limitation.

## 5. Does `rag.server` stop generating on cancel? No — new finding F-L

**By reading (CONFIRMED).**
- `RagServicer.Answer` (`server.py:28-50`) is synchronous. It calls `generate.generate` (`:41`), a
  blocking `httpx` `POST` to Ollama with a 120 s timeout (`generate.py:15, :36-48`).
- Nothing checks `context.is_active()`, registers `context.add_callback`, or aborts. A
  `grep is_active|add_callback` over `rag/` finds nothing.
- grpcio's synchronous server does not interrupt a handler thread when its RPC is cancelled.

**Probed (CONFIRMED).**
- `rag.server.build_server` was run on loopback. `rag.generate` and `rag.retrieve` were replaced
  with stubs before import, so neither Ollama nor llama_index was loaded.
- A Python gRPC client cancelled `Answer` while the stub `generate` slept for 1.5 s.
- Timeline: `generate_start` +0.000 s · `client_cancel` +0.203 s · client sees `CANCELLED`
  +0.205 s · **`generate_end` +1.505 s**.
- In production that stub is the Ollama call, and `httpx` stays connected, so Ollama has no
  disconnect to abort on.

**Not every abandonment creates an orphan.**
- A client that is gone before `Answer` never reaches the server. The probe counted 0 RPCs seen by
  the server for the pre-cancelled request, so that case costs only `Acquire`'s microsecond.
- The orphan arises when the client leaves **after the RPC was sent**. That is exactly the path
  this fix relabels `ABANDONED`.

**Consequence: a separate finding, out of scope here. Proposed name F-L.**

*An abandoned generation keeps the one slot after the gateway has released its permit.*
- The permit returns as soon as `Answer` fails (`handler.go:394`).
- The next admitted request sends its own `Answer`, which Python runs on another of its 4 workers
  (`server.py:62`).
- Ollama, at `-np 1`, queues that request behind the orphan. Its queue is unbounded at that scale:
  `OLLAMA_MAX_QUEUE:512` (`docs/work/2026-10-04-resolve-f1/evidence/ollama-np-override.txt:13`).
- This is *"surplus permit queues requests inside Ollama, where the gateway can neither see nor
  shed them"* (ADR-003, `decisions.md:181-182`). It also falsifies the premise at
  `Final_Proposal.md:321`: cancellation propagation releases the permit, but not the slot.

**Silent effects, each up to one service time S per orphan** (S ≈ 5 s at the 0.19 req/s planning
figure, capped at 120 s by `httpx`):
- **`t_generate_ms`** of the next request absorbs the orphan's remainder. That is the
  Ollama-internal wait ADR-003 says one slot removed (`decisions.md:211`).
- **ADR-003's bound breaks.** Admitted latency ≤ (1 + q) · S (`decisions.md:202`) no longer holds.
- **Gateway-measured μ_gen falls.** The orphan spends the slot on an answer that nobody receives
  and that is never cached, because write-back runs only on success.
- **PLAUSIBLE: Tier-2 `Retrieve` can wait.** Orphans plus the live `Answer` share the 4 Python
  workers with `Retrieve`, which sits on the Tier-2 hit path. An orphaned `Retrieve`
  (`server.py:15-26`) also keeps embedding on `nomic-embed-text`'s single slot.

**What this means for item 1.6, and then for Phase 7.**
- **This fix makes these events visible as `ABANDONED`. F-L makes each of them cost a slot.**
- Item 1.6 should do one of three things:
  - record the count of `ABANDONED` records carrying `permit_queue_depth`, beside the footprint;
  - choose a k6 timeout well above (1 + q) · S plus a cold model load (today `ask.js:124` sets
    120 s, `mu_hit.js` 180 s and 30 s), so that abandonment during `Answer` stays near zero;
  - or fix F-L first.
- **Before 7.1 and 7.5:** fix F-L, or show that abandonment during `Answer` is ≈ 0 in every run.
- **The fix's shape, recorded here and not built:** check `context.is_active()` before
  generating, and on cancel close a per-request streaming `httpx` response (`add_callback`). Ollama
  stops when its HTTP client disconnects.

## 6. Other paths that meet a cancelled context

| Path | What a dead context does | Changed? |
| :--- | :--- | :--- |
| **Tier-1 lookup** (`handler.go:197-202`) | Any error gives a 500 and `cache: ""` (F-B). **With the real store, a dead context fails here first.** go-redis v9.22.0 checks it before taking a connection: `getConn` → `waitTurn` (`internal/pool/pool.go:897`, `:1164-1170`). `fakeStore.Get` ignores the context (`harness_test.go:277`) | No. **So acceptance 2 tests a fake-only path.** In production, a client gone before `Ask` lands on F-B (correction 2) |
| Embed (`:245-258`) | Error, then degrade. Logs *"embed failed, degrading to MISS: … context canceled"* | No |
| Retrieve (`:259-269`) | Status `Canceled`, then degrade | No |
| Tier-2 search (`cascade.go:103-107`) | Degrade | No |
| Shed (`:478`) | `Acquire` reads no context before the queue, so a dead client meeting a full pool is `SHED` (probed) | No, **provided the new case stays below `ErrShed`** (M-order) |
| Queued `Acquire` (`pool.go:110-114`) | Raw `context.Canceled`, then `ABANDONED`. If the permit frees at the same moment, `select` may take it instead and call `Answer` on a dead context: today a coin flip between `ABANDONED` and `GENERATION_FAILED` (1.2 `review.md` S3) | **Yes:** both branches now land `ABANDONED`. The flake disappears |
| The miss-path switch | The only classifier | **Yes** |

**A client that leaves during embed or retrieve while a Tier-2 candidate exists (CONFIRMED by
reading; the dead-context half was probed).**
- The failed leg leaves `vec` or `retrieved` nil, so `tryTier2` returns a zero outcome
  (`cascade.go:81-83`) and the request takes the miss path.
- `Acquire`'s fast path admits it, and `Answer` fails on the client side without reaching the
  server.
- The record is `GENERATION_FAILED` today and `ABANDONED` after the fix, with `similarity: null`.
- The hit it would have been is counted in neither case. No orphan is created.
- A client that leaves **after** embed, retrieve and search have finished is served the hit on a
  dead connection and recorded `TIER2_HIT`. That is consistent with acceptance 4: completed work
  keeps its label.

## 7. Cut scope, dependencies, contract, measurement

| Question | Answer | Reason |
| :--- | :--- | :--- |
| Reinstates cut scope? | **No** (CONFIRMED) | Nothing on `Final_Proposal.md:599`'s list is involved: the bypass classifier, the learned predictor, predictor-gated invalidation, semantic routing, SSE, FLAT → HNSW |
| New dependency? | **No** (CONFIRMED) | No import and no module. Zero resident bytes |
| Contract change? | **No: the contract phase is not required** (CONFIRMED) | §A: neither value reaches a response. §H: no field and no enum value is added or removed, and `:461` already omits the extensions. `.proto` and §B–§E are untouched |
| Measurement change? | **Yes, in how requests are counted, not in what is measured.** **The experiment phase is required, record-only** | See below |

**What changes in the counting.** No field or timing changes. Bucket membership does.

- **Before.** `ABANDONED` held:
  - abandonments while queued;
  - F-D's live followers (cell 1);
  - half of the queued abandonments that lost the `select` race.

  Every other observed abandonment was `GENERATION_FAILED`.
- **After.** `ABANDONED` means *this request's client was gone when the miss path returned an
  error*. It also holds two groups whose clients had not left:
  - F-D's live followers (cell 1, unchanged);
  - genuine upstream failures whose client had already left (cell 5).

  `GENERATION_FAILED` means *the upstream failed while this request's client was still
  connected*.

**What the experiment phase records** (nothing is re-measured):
1. **The precedence:** `SHED` > *own client gone* ⇒ `ABANDONED` > `GENERATION_FAILED`. And
   `err == nil` ⇒ `MISS`, whether or not the client is still there.
2. **The residual misattributions:**
   - abandonment at completion → `MISS` (§8 S4);
   - a disconnect the server cannot see → whatever completes (§4);
   - F-D's live followers → `ABANDONED`.
3. **Reconciling client and server counts:**
   - a k6 timeout (status 0) is `ABANDONED` **or** `MISS` on the server;
   - an F-D follower is a 200 on the client and `ABANDONED` on the server.
4. **F-L's effect on `t_generate_ms`** and on admitted latency near saturation (§5).

If the author prefers, these four items can live in `approvals.md` instead of a separate artefact.
Either way, they must be written down before 1.6.

## 8. What would fail silently

Ranked.

| # | Hazard | Evidence | Design must |
| :---: | :--- | :--- | :--- |
| S1 | **Orphaned generations (F-L).** An `ABANDONED` that happens during `Answer` still occupies the slot after the permit is released. `t_generate_ms` and admitted latency for the *next* request absorb it, with no error. The fix makes these records look free | §5 probe; `server.py:28-50`; ADR-003 | Record F-L. Keep it out of this task. Gate 1.6 and Phase 7 on it (§5) |
| S2 | **The wrong fix passes every existing test.** M-closure, M-order, M-code (`status.Code == Canceled`) and M-guard (`err != nil` dropped) **all pass the whole 1.2 suite (measured)**. M-closure widens F-D to live followers. M-order moves dead-client sheds out of the shed rate. M-code files a `rag.server` restart's `CANCELED` against a live client as `ABANDONED`. M-guard relabels completed generations | Scratch mutation runs | The new file covers each one: cell 2 with a live follower (§3); a dead client against a full pool and queue → `SHED`; upstream `CANCELED` and `DEADLINE_EXCEEDED` with a live client → `GENERATION_FAILED`; a cancel inside `Put` → `MISS` |
| S3 | **A disconnect the server cannot see.** Trailing bytes or an unterminated chunked body leave the context live, so the abandonment is recorded `MISS`. Server-side goodput then counts a request the client gave up on | §4 probe | Acceptance 5 uses an exact-length body. State the limitation in the experiment record |
| S4 | **A client that leaves as the generation finishes.**<br>• Leaving after `Answer` returned is `MISS` (correct), but with the real store the write-back runs on a dead context and fails (go-redis checks the context first). The answer is never cached, and the record carries an `entry_id` that was never stored (F-J).<br>• Leaving after Python finished but before `Recv` is `ABANDONED`, with the generation fully spent and `t_generate_ms` null (F-H). An early leave and a late leave cannot be told apart | Probe (`MISS`); `handler.go:403, :510`; go-redis `pool.go:1164-1170` | Nothing in this task. **Widen F-H to `ABANDONED`**: after this fix it is where nearly all generation time spent on failures lands (correction 10). Note the write-back-on-dead-context trigger under F-J |
| S5 | **`ABANDONED` absorbs a genuine upstream failure** when this request's client had also left (cell 5's follower). If the leader's client also left, the upstream failure leaves no `GENERATION_FAILED` anywhere in §H | Probe, cell 5 | Record the precedence (§7). The alternative (own context gone **and** status in {`Canceled`, `DeadlineExceeded`}) keeps cell 5 as `GENERATION_FAILED`. It still reads this request's context, so it is not the forbidden status-code keying. A design decision, D1 |
| S6 | **A future server-side deadline would be filed as a client leaving.** Today the request context can only be cancelled by the client: no server timeouts, `TimeoutHandler` or `BaseContext` (`main.go:244`). Add one, and gateway-caused timeouts become `ABANDONED` | `main.go:244` | A code comment at the case naming this assumption. `context.Cause` is the tool if it ever stops holding |
| S7 | **`ABANDONED` read as "the client left".** F-D's live followers (cell 1) are in it, and they received an empty 200, which k6 counts as goodput **and** as an error (`ask.js:139-148`) | Probe, cell 1 | Record it. F-D's own fix closes it |
| S8 | **`Counters` against the record** | Both are driven from `rec.Cache` at the single deferred exit (`handler.go:180-193`), so they agree by construction. `/stats` lumps both buckets together | Nothing. *(Separately and unchanged: `Log` can drop on a full buffer while `Counters` do not, `evallog.go:136-142`, and that is caught by `Dropped()`)* |
| S9 | **The `Retry-After` header and the log lines** | `Retry-After` is set only on `SHED` (`:481`). No client or script retries (grep). The `ABANDONED` line (`:498`) now prints a gRPC status, and says *"while generating"* for leaves that happened before generation. The `GENERATION_FAILED` path logs **nothing** (`:500-503`) | Optional: reword `:498`. stderr is not the measurement channel |
| S10 | **A race between a real error and a leave.** A client leaving microseconds after a genuine error returns is filed `ABANDONED` | Reasoned | Nothing. The window is negligible |

**And if the fix is not made:**
- `GENERATION_FAILED` is inflated by every observed abandonment except those queued.
- A Phase 7 gateway failure rate would then charge client timeouts to the gateway.
- The queued case stays a coin flip (§6).

This is the larger silent error, which is why the fix is right.

## Smallest change that satisfies the spec

**Keep:**
- **`handler.go`:**
  - one conjunct, `err != nil && ctx.Err() != nil`, in the `ABANDONED` case or as its own case;
  - placed below `ErrShed` and above `case err != nil`;
  - reading the request's own `ctx`, in the switch;
  - one comment line naming the S6 assumption.
- **One new test file**, covering:
  - acceptance 1: `Answer` held, then cancel;
  - acceptance 2, restated per correction 2;
  - acceptance 3: `CANCELED`, `DEADLINE_EXCEEDED` and `INTERNAL` with a live client;
  - acceptance 4: a local `cacheStore` wrapper that cancels in `Put`;
  - acceptance 5: `httptest.NewServer` with an exact-length body;
  - a dead client against a full pool and queue → `SHED`;
  - cell 2 with a live follower → a written response that is not `ABANDONED`.

**Cut:**
- Any edit to `pool.go`, `coalesce.go`, `ragclient/`, `rag/` or the harness.
- Draining or limiting the body (§4).
- Copying `t_generate_ms` onto `ABANDONED` (F-H).
- The §H enum sync (§2).
- The k6 non-empty-answer check (F-D).
- F-L.

## Invalidates

**Nothing.**
- **`run_id`s:** none exist (§1).
- **Frozen values:** none changed. No ADR is needed.
- **Planning figures:** untouched. Admission timing is identical, and no hit path changes.
- **Logs:** none exist. A future log is not comparable across the commit for the
  `ABANDONED` / `GENERATION_FAILED` split. Every other field is comparable.

> **Required phases:** impact · experiment (record-only: §7's four items) · implementation, plus
> design → opus design-review → plan for scope L.
> - **Contract:** not required. No §A–§H field, enum value or `.proto` changes, and the §H enum
>   sync waits for F-B (§2).
> - **Experiment:** nothing to re-measure. Record the precedence rule, the residual
>   misattributions, client/server reconciliation and F-L's effect before item 1.6.

---

## Corrections this implies for `spec.md` (not applied)

| # | Where | Correction |
| :---: | :--- | :--- |
| 1 | "The bug, and its cause" | `pool.go:124-126` → `pool.go:113-114`. The file has 120 lines |
| 2 | Acceptance 2 | *"cancelled before `Ask` starts … reaches `Answer`"* holds only against `fakeStore`, which ignores the context. With real Redis, that request fails at Tier 1 (F-B: 500, `cache: ""`). Restate it as **"the client leaves after Tier 1, during embed or retrieve"**. Note that `ragclient.Answer` then fails on the client side, and the server never sees the call (probe) |
| 3 | Acceptance 3 | Add: a request whose client is gone and that meets a full pool and queue stays **`SHED`**. Name `rag.server`'s own cancellation (a restart, for example) as the live-client `CANCELED` case |
| 4 | Acceptance 4 | Name the seam: a local `cacheStore` wrapper in the new file cancels the request's context in `Put`, assigned to `hs.h.Cache`. The harness is unchanged |
| 5 | Acceptance 5 | Require an exact `Content-Length` body (`bytes.Reader`). State that detection depends on the body reaching EOF (§4), and record the padded and chunked cases as a limitation, not as desired behaviour |
| 6 | Acceptance 6 | `ask_test.go:369-370` (*"… is logged GENERATION_FAILED today (F-A)"*) becomes false. Either allow a **comment-only** edit there (no assertion changes) or record the stale comment. As written, "`git diff` … is empty" forbids the fix |
| 7 | Acceptance 7 | Add **M-closure** (classify in the closure or in `ragclient`, from the leader's context) and **M-order** (the case above `ErrShed`). Both pass the existing suite (measured). M-closure's test asserts that cell 2's live follower **got a written response and is not `ABANDONED`**. It must not assert 502, which would pin F-D |
| 8 | Out of scope, F-D | Add: a follower whose **own** client has gone moves `GENERATION_FAILED` → `ABANDONED` (cells 2 and 5). That is the rule, not a change to what a live follower receives |
| 9 | Out of scope, `rag.server` | Resolved: **it does not stop** (§5, probed). Record F-L in `super-plan.md`'s Phase 1 findings at `/done`, with its gate on 1.6 and Phase 7 |
| 10 | Out of scope, F-H | Widen F-H to `ABANDONED`. After this fix it is where most generation time spent on failures lands. `generateMS` is set at `:403` and copied only at `:510` |
| 11 | New decision D1 | The precedence for cell 5: the client being gone beats an upstream failure (as written), or the conjunction with `Canceled`/`DeadlineExceeded` (§8 S5). Either way, record it |
| 12 | "Why scope L" / phases | Contract: not required. **Experiment: required, record-only** (§7). The bucket membership on the measured path changes, and the precedence is written down nowhere else |
| 13 | New, forward | The rule assumes `r.Context()` is cancelled only by the client (`main.go:244`). Say so in a code comment at the case (§8 S6) |
