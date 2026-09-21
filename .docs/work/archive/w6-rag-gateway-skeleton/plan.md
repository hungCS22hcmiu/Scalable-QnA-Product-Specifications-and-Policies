# Plan

Ordered, smallest change that satisfies `spec.md`'s acceptance. Each step is independently
verifiable. Incorporates the `impact.md` trims (stdlib `net/http`, no Fiber/Gin, no
`singleflight`, no connection-pool abstraction beyond one long-lived conn, `null`s for
unimplemented §A fields).

- [x] `gateway/go.mod`: add `google.golang.org/grpc`, `google.golang.org/protobuf`,
      `redis/go-redis/v9`. **New dependencies — needs sign-off (rules.md #9)** before this step
      runs; recorded in `approvals.md`.
- [x] `rag/src/rag/config.py`: confirm/add the frozen generation constants (model tag
      `qwen3.5:2b-q4_K_M`, `think: false`, `num_ctx=8192` — ADR-021/ADR-017) as named constants,
      not literals scattered in `generate.py`.
- [x] `rag/src/rag/generate.py`: Ollama generation call over retrieved context. Reads frozen
      values from `config.py` only; never accepts a per-request override of `think`/`num_ctx`.
- [x] `rag/src/rag/server.py`: gRPC server implementing `RagService`.
  - `Retrieve` — thin wrapper over W5's `retrieve.py`; returns `chunk_ids`, `scores`,
    `dataset_epoch` (stub `0` until W9–11's `deps/` owns the real counter).
  - `Answer` — retrieve then generate; returns exactly **one terminal `AnswerChunk`**
    (`done=true`) — no per-token emission, `stream=false` path only (SSE stays out of scope,
    ADR-016).
- [x] `gateway/internal/cache`: Tier-1 exact-match only.
  - Key normalization exactly per ADR-015 (lowercase, collapse whitespace, strip punctuation) —
    no stemming/stopwords/synonyms (would smuggle in a reuse decision `cache/` must never make).
  - `t1:{sha256(normalized_query)}` hash: `answer`, `source_chunk_ids`, `model_used`,
    `created_at`, `entry_id` (mint a ULID on write-back) — per `interfaces.md` §D.
  - No `t1_key`/Tier-2 fields this week (§D's `t1_key` is written *by* Tier-2, which doesn't
    exist until W7) — note this gap in the worklog so it's not forgotten before any measured run.
- [x] `gateway/internal/ragclient`: one long-lived `*grpc.ClientConn` created at startup (gRPC
      multiplexes — "pooled" means not-per-request, not a custom pool). Wraps `Answer`/
      `Retrieve`; passes `dataset_epoch` through untouched (still a stub end-to-end this week).
- [x] `gateway/internal/httpapi`: `POST /ask` on stdlib `net/http`. Single call-site orchestration
      (`cache.Get` → miss → `ragclient.Answer` → `cache.Put`) so W16's admission control has one
      insertion point later. Emits the full `interfaces.md` §A response shape, with
      `similarity`/`source_overlap` as `null` (not implemented until W7/W12).
- [x] `gateway/cmd/gateway/main.go`: wire Redis client + gRPC conn + HTTP server. Stays
      logic-free — construction and `http.ListenAndServe` only.
- [x] ~~Redis: set up the eviction-region split before any `t1:*` write — `t1:*` under its own
      logical DB / `volatile-lru`+TTL, kept separate from `corpus:*`/`idx:corpus` (W5) so a
      cache-capacity eviction can never touch corpus vectors.~~
      **Deviated — the step as written is not implementable, and the deviation is safe.**
      `maxmemory-policy` is **server-global, not per logical DB** (verified: `redis-cli -n 1
      CONFIG GET maxmemory-policy` returns the same value as db 0), so interfaces.md §D's
      "logical DB" option cannot produce two policies inside one instance. Separately, the
      study's capacity is `round(0.25 × K)` **entries** (ADR-027) while Redis `maxmemory` is a
      **byte** budget, so Redis-native LRU cannot express it at all — capacity has to be
      enforced in Go, and `K` is not derived until W8 anyway. Implemented instead as
      **`make redis-check`**, which asserts the only configuration that is currently correct:
      `maxmemory-policy=noeviction`, `maxmemory=0` — nothing evictable, so no `dep:*` record
      and no `corpus:*` vector can be lost. `make dev` depends on it, so the assertion runs
      before every local run rather than being a one-time setup belief. Needs an ADR before
      W9 (`deps/`) turns this from "safe by default" into a load-bearing guarantee.
- [x] Manual round-trip check: one question end-to-end (miss → Python → answer with sources);
      same question again → Tier-1 hit in <10 ms. Record p50 miss latency informally — this is a
      worklog number, not an `experiments/results/` artifact (non-citable, `dev-v0`, ADR-020).
      **Both criteria pass** (2026-09-04). End-to-end: correct answer, 5 chunk IDs in §C format,
      `similarity`/`source_overlap` rendered as `null`, `model_used` = the wire id `qwen3.5-2b`.
      Tier-1 repeat: **p50 0.53 ms** (n=10, curl `time_total`, range 0.46–0.70) — 19x under the
      10 ms bar. Miss **p50 2506 ms** (n=10 distinct queries, warm model; min 1870, max 3751).
      Run taken outside `make dev`, whose pressure guard correctly still refuses — see the
      worklog's stale-sensor finding.
- [x] ~~`make proto` re-run only if the generated stubs are stale~~ — **not needed**: stubs
      (Aug 16) are newer than `contracts/rag/v1/rag.proto` (Aug 9, untouched this task).
- [x] `make verify` (lint + build + test) green — **and no longer vacuous.** It had been
      reporting `ruff SKIPPED` / `pytest SKIPPED` while both were in fact installed, in the
      pip user base that a non-login `/bin/bash` does not have on `PATH` — so every Python
      file this task added (`generate.py`, `server.py`, `config.py`) had never been linted or
      tested by `make`. The `Makefile` now derives that directory via `python3 -m site
      --user-base`. Re-run after the fix: ruff clean, 5 pytest tests pass, 19 Go cache
      assertions pass.
- [x] `/log` entry in `docs/worklog/W06.md`; update this file's checkboxes to match what actually
      shipped before `/done`. Appended 2026-09-04: exit-test table (5 criteria, all PASS),
      three findings (vacuous `make verify`, stuck `vm_pressure_level`, `latency_ms` cannot
      express a hit), and the step-9 deviation.

---

## Outcome (2026-09-04)

**Shipped.** All 13 plan steps. `POST /ask` round-trips end to end over gRPC with provenance;
Tier-1 exact cache reads and writes to `interfaces.md` §D's schema. `/gate` PASS on all five
criteria, executed and asserted rather than self-reported: miss p50 **2506 ms** (n=10), Tier-1
hit p50 **0.601 ms** (n=20, max 0.816) against a <10 ms bar. `make verify` exit 0 with ruff and
pytest genuinely running for the first time.

**Two defects found in review and fixed here:**
- `httpapi/handler.go` — a failed cache write-back no longer discards the completed generation
  and returns 500. It serves the answer and logs the failure, because the discarded outcome fits
  none of `experiment-protocol.md` §4's categories and would have leaked out of both the goodput
  numerator and the shed denominator (review.md F4).
- `Makefile` `env-check` — the "ollama already running" branch was a NOTE that exited 0; it is
  now a hard FAIL. macOS does not permit reading a running process's environment (`ps eww`
  returns zero tokens, tested), so the served value is genuinely unverifiable, and unverifiable
  must not read as verified (review.md F2). FAIL branch verified by actually starting Ollama.

**Deferred, with due dates.**
- **`gateway/internal/ragclient/client.go` leaves the gRPC channel at defaults**, which
  `experiment-protocol.md` §1 line 27 marks "⚠️ Not optional and not left at defaults". The value
  cannot be chosen well before the permit pool (W16) and the load profile (W8) exist, and picking
  one arbitrarily is its own hazard. **Due before W8's k6 harness** (review.md F3).
- **Redis two-region eviction split** — not implementable as §D words it (`maxmemory-policy` is
  server-global; capacity is a count, not a byte budget). `make redis-check` asserts the safe
  interim state. **Due before W9**, when `deps/` makes it load-bearing.
- **`latency_ms` cannot express a hit** (integer-ms truncation → every Tier-1 hit reports 0).
  μ_hit is `1/hit_latency`, so from this field it is undefined. **Decide before the W8 probe.**
- **`t1_key` absent** from Tier-1 records — Tier-2 authors it and does not exist yet. Required
  before any purge path is measured.

**Follow-up worth its own task — and it outranks everything above.**

`review.md` **F1: `OLLAMA_NUM_PARALLEL=4` is not in effect and cannot be.** Ollama overrides it
to `-np 1` because the frozen model's architecture does not support parallel requests; the W5
spike logs show the same `-np 1` under the same model blob, so ADR-017's μ_gen ≈ 28.2 tok/s is a
one-slot number recorded as a four-slot aggregate. This reaches the permit pool — the core
parameter of the 60 %-weighted contribution — and through μ_gen into λ_max and Headline A.
**ADR required before W8.** Not fixable in code.

Two other open questions carried out of this task, both needing decisions before W8:
the **memory-pressure sensor** (worklog finding 2 — reboot test first, then an ADR), and
**Tier-2's missing home** in the replanned timeline, which makes the W8 μ_hit probe Tier-1-only.
