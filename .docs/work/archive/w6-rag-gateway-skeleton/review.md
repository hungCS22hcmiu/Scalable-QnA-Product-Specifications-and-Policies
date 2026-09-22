# AI Review — w6-rag-gateway-skeleton

**Date:** 2026-09-04 · **Reviewers:** `contract-reviewer`, `experiment-reviewer`, plus a
log-forensics pass that produced F1 (which neither agent found).

`contract-reviewer`: **no findings.** Verified independently — provenance intact across all five
hops, `dataset_epoch` correctly plumbed but not written to Tier-1 (§D has no such field there),
`t1_key` correctly absent (Tier-2 authors it), no left-pointing imports, `cache/` makes no reuse
decision, `httpapi` is the single call site, `go.mod` matches `approvals.md`. It also endorsed
the step-9 `redis-check` deviation as sound and strictly safer than the planned split.

---

## F1 · CONFIRMED · CRITICAL · rules.md #1 · `OLLAMA_NUM_PARALLEL=4` is not in effect, and cannot be

**Not a code defect — a frozen value that does not hold in reality.** ADR-017 freezes
`num_ctx=8192, OLLAMA_NUM_PARALLEL=4` and records **μ_gen ≈ 28.2 tok/s "aggregate at that pair"**.
The pair has never run on this machine.

Evidence, from the Ollama server log of this session's own exit-test run:

```
llama-server ... -c 8192 -np 1 ...            <- effective parallelism 1
llama_context: n_seq_max = 1
srv load_model: initializing, n_slots = 1, n_ctx_slot = 8192
WARN sched.go:509 "model architecture does not currently
     support parallel requests" architecture=qwen35
```

Ollama accepts `OLLAMA_NUM_PARALLEL=4`, echoes it back in its `server config` line, and then
**overrides it to `-np 1`** because the frozen generation model's architecture does not support
parallel requests in Ollama 0.33.2.

This is not new to today. `~/.ollama/logs/server-{3,4,5}.log` (2026-08-15 / 08-16 — the W5
feasibility spike that produced ADR-017 **and** ADR-021) show `-np 1` in every instance, three
occurrences each, never `-np 4`. Model blob `sha256-7a3a8d553821` in those logs is byte-identical
to the blob loaded today for `qwen3.5:2b-q4_K_M`. Same model, same single slot, then and now.
At spike time `OLLAMA_NUM_PARALLEL` was additionally pinned nowhere at all (W06 worklog,
2026-08-19), so Ollama was choosing its own default — which was also 1.

**Why it is the worst class of failure.** Every check passes:
`make env-check` → `launchd=4` ✅ · Ollama's own config line → `OLLAMA_NUM_PARALLEL:4` ✅ ·
a run manifest built per `experiment-protocol.md` §1 → reports `OLLAMA_NUM_PARALLEL=4` ✅ —
while the model serves on **one** slot. Nothing errors. The reported configuration is false.

**Blast radius:**
1. **ADR-017's μ_gen is mis-attributed.** 28.2 tok/s is a 1-slot number labelled as a 4-slot
   aggregate.
2. **The permit pool — the core parameter of the 60 %-weighted contribution — is sized wrong.**
   `CLAUDE.md` and proposal §6.1 specify it as `OLLAMA_NUM_PARALLEL + headroom`. Sized to 4
   against a 1-slot backend, the gateway admits four generations that then **serialise inside
   Ollama**. The queue forms behind the backend, invisible to the gateway's permit accounting —
   the same hazard `experiment-protocol.md` §1 names for gRPC, at the Ollama seam instead.
3. **λ_max = min(μ_gen/(1−h), μ_hit/h)** and therefore Headline A's capacity model inherit the
   wrong μ_gen.
4. **S2's memory rationale shifts.** KV-cache footprint scales with slots; this run predicted
   2.7 GiB at one slot. The envelope was sized for a concurrency that does not exist.

**Action: ADR, before W8.** Options to weigh there — re-measure μ_gen and freeze
`NUM_PARALLEL=1` as the honest effective value and size the permit pool to it; or check whether a
newer Ollama or a different frozen model supports parallel slots, noting ADR-021 forbids casually
swapping the model. Not fixable in code. **Cannot be left implicit: a run reporting `4` is
reporting a number that was never true.**

## F2 · CONFIRMED · rules.md #1 · `env-check` warns where it must fail

`Makefile:44` — `@pgrep -q ollama && echo "  NOTE: ollama already running ..." || true`. Exits 0,
so `make dev` proceeds. Ollama reads the variable **only at process start** (the target's own FAIL
text says so), so an Ollama started before the pin serves under an unknown value while the check
reports green.

Compounding it: the live value cannot be read back. macOS blocks reading another process's
environment — `ps eww` on an owned process returns **0** environment tokens (tested). So
"already running" is genuinely unverifiable, and unverifiable must not read as verified.

F1 also changes what this check should assert: the *requested* value is not the quantity that
matters — the **effective slot count** is, and that appears only in the Ollama server log.

**Action: fix now** — hard-fail when Ollama is already running, and print how to restart it.

## F3 · CONFIRMED · `experiment-protocol.md` §1 (line 27) · gRPC channel left at defaults

`gateway/internal/ragclient/client.go:20` calls `grpc.NewClient` with transport credentials only —
no `MaxConcurrentStreams`, no channel count, no keepalive. The protocol's wording is explicit:

> **gRPC channel configuration** — … ⚠️ **Not optional and not left at defaults**: HTTP/2 caps
> concurrent streams per connection, so an exhausted channel queues **client-side** and is
> indistinguishable from gateway saturation in the admission-control results.

`ragclient/` is the designated sole owner of this channel (`architecture-guardrails.md`), so this
is the last natural place to set it before W8's load patterns are built around today's defaults.

**Not yet a wrong number** — admission control does not exist and W6 produced no citable figures.
But the value cannot be chosen well until the permit pool exists (W16) and the load profile is
known (W8), and picking one arbitrarily now is its own hazard. **Escalated as a decision**, with
a hard due date: before the k6 harness lands in W8.

## F4 · CONFIRMED · `experiment-protocol.md` §4 · a failed cache write discards a completed generation

`gateway/internal/httpapi/handler.go:73-80` — when `Cache.Put` fails after a successful
generation, the handler returns HTTP 500 and **throws the answer away**. That outcome is none of
`TIER1_HIT | TIER2_HIT | MISS | BYPASS | 503-shed`, the only categories §4's goodput/shed split
accounts for; under load a nonzero rate of it would leak out of both the goodput numerator and
the shed denominator once §H logging is wired in.

It is also backwards on the thesis's own terms: a generation is the most expensive resource in
the system, and the entire contribution is about not spending it twice. Discarding a completed
one because a cache write failed spends it for nothing.

**Action: fix now** — serve the answer, log the write-back failure as its own outcome.

## F5 · Informational · carried forward, no action this week

- `latency_ms` integer-ms truncation makes every Tier-1 hit report `0` (W06 worklog finding 3).
  Confirmed independently. μ_hit is `1/hit_latency`, so from this field it is *undefined*, not
  merely imprecise. Decide before the W8 probe.
- The timer's placement is otherwise correct: `start` is set before body decode and read
  immediately before `writeJSON` on both branches, excluding encode/flush — consistent with the
  protocol's "internal — gateway spans".
- When §H's decomposition (`t_tier1_ms`, `t_embed_ms`, …) lands, stage timers must be measured
  **independently**, never backfilled by subtracting from a single `start` — §H notes the stage
  sums need not equal `t_total_ms`.
- Whoever lands Tier-2 capacity must update `make redis-check`, which currently fails **any**
  non-`noeviction` policy and will therefore block the correct future configuration. Weakening
  the check instead of implementing the split would be exactly the quiet accommodation rule #10
  warns about.

---

## Resolution

| # | Severity | Resolution |
| :-- | :--- | :--- |
| F1 | CRITICAL | **Open — ADR required before W8.** Not fixable in code. |
| F2 | High | Fixed in this task. |
| F3 | Medium | **Accepted with due date** — decided before W8's k6 harness. |
| F4 | Medium | Fixed in this task. |
| F5 | Info | Carried forward; F5.1 decided before the W8 μ_hit probe. |
