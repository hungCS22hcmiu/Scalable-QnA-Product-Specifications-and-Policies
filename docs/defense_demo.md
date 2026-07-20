# Defense Demo Plan — What to Show the Council

**Companion to:** `pre_thesis-Proposal.md` (contributions, evaluation) and `time_line.md` (when to build/rehearse this).
**Principle:** the council grades claims and evidence, not product polish. The demo makes the invisible caching layer visible; the pre-run experiment figures are the evidence; the full e-commerce system never exists.

---

## 1. Scope of What Is Shown

**Not built, not shown:** user accounts, cart, checkout, orders, product browsing — no e-commerce product UI of any kind (proposal §10: the assistant and UI are hosts for the scalability layer, not products).

**Built and shown:**
- The **QA service** (Go gateway + Python RAG + local LLM) over the product/policy corpus.
- A minimal **debug-view UI** (one page) that exposes the system's decision-making.
- **Pre-computed experiment figures** on slides — the headline results are never generated live.
- The classify-and-bypass step (§4.4) may appear with a **stubbed** live source (fake stock/price) — its point is the routing decision, not real inventory.

## 2. The System's Input/Output Contract

The platform is a service with one primary endpoint. The **metadata is the thesis** — a plain chat UI would hide everything the council needs to see.

**Input**

```http
POST /ask
{"question": "Can I return this laptop after 30 days?"}
```

**Output**

```json
{
  "answer": "Returns are accepted within 30 days of delivery...",
  "cache": "TIER2_HIT",                    // TIER1_HIT | TIER2_HIT | MISS | BYPASS
  "latency_ms": 48,                        // vs ~4000 ms on a MISS
  "similarity": 0.93,                      // Tier-2 embedding similarity
  "reuse_confidence": 0.98,                // predictor output — Contribution 1
  "sources": ["policy-returns#chunk-2"]    // provenance tags — Contribution 2
}
```

## 3. The Debug-View UI (1–2 days of work, no more)

One page:

- **Question box** + submit.
- **Answer area** (streams on a miss, instant on a hit).
- **Metrics panel** per request: cache-path badge (color-coded: green TIER1, blue TIER2, orange MISS, grey BYPASS), latency, similarity, reuse-confidence, source chunks.
- Optional sidebar: running counters (total requests, hit rate, generations avoided) — cheap and demo-friendly.

A debug view beats a polished consumer UI at a defense: it makes the contribution observable.

## 4. The Five-Step Demo Script (~5 minutes, thesis defense)

Each step is one request and demonstrates one mechanism. Rehearse until it runs twice in a row without touching code (`time_line.md` W9/W22 gates).

| Step | You do | Screen shows | Proves | Say out loud |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Ask a fresh question | `MISS` · ~4 s · answer streams · sources listed | The expensive path every uncached system pays every time | "This is the cost of every request without caching." |
| 2 | Ask the **exact same** question | `TIER1_HIT` · ~5 ms | Exact-match tier | "Identical repeats — very common in product traffic — cost nothing." |
| 3 | Ask a **paraphrase** ("Is 30-day return possible for this laptop?") | `TIER2_HIT` · ~50 ms · similarity ≈ 0.9 | Semantic tier | "Different words, same question — still no LLM call." |
| 4 | Ask a **lookalike trap** — same wording, different product category with a different policy | High similarity **but low reuse-confidence** → `MISS` → *correct* answer | **Contribution 1** | "A fixed threshold would have served the wrong answer here. The predictor saw the sources differ." |
| 5 | **Edit the policy file** (change 30→14 days), re-ask step 1's question | Entry purged → `MISS` → new correct answer | **Contribution 2** | "No stale answer, no waiting for a TTL — the cache tracked its sources." |

**Optional closer (30 s):** a *recorded* clip of a k6 run — requests/sec and hit rate climbing on the counters. Recorded, not live: live load tests are how defense demos die.

### Demo data prep

- Seed the corpus so steps 3–5 are deterministic: pick the paraphrase and the lookalike trap **from your validation set** in advance and verify their cache behavior the night before.
- Keep a reset script (`make demo-reset`) that restores the corpus, flushes the cache, and pre-warms nothing — so the demo starts from a known state every rehearsal.

## 5. Defense-Day Structure

A defense is **slides + short scripted demo + Q&A** (~30–45 min total; confirm your program's exact format with the advisor).

1. **Slides (~15–20 min):** problem → architecture diagram (proposal §4.5) → contributions → **headline figures as the climax**: throughput/latency-vs-concurrency curves (Headline A) and the hit-rate/false-hit frontier vs the deterministic source-overlap rule, GPTCache & vCache at the finalized false-hit budget (Headline B). The comparison to prior art happens here, on a slide — never live.
2. **Demo (~5 min):** the five-step script above.
3. **Q&A:** expected pokes and where the answers live — "why not just TTL?" (§2, RQ3 results), "what if the predictor is wrong?" (false-hit budget δ, fallback to fixed threshold, §3/§8), "how is this different from vCache?" (source-grounding features + invalidation, §8), "does the cache benefit depend on your workload design?" (redundancy sweep, §7.1).

## 6. Pre-Thesis vs. Thesis Defense

| | Pre-thesis (Sep 2026) | Thesis (Dec 2026) |
| :--- | :--- | :--- |
| Demo steps | **1–3 only** (miss, exact hit, semantic hit with fixed τ) | **Full 1–5** (incl. predictor trap + live invalidation) |
| Steps 4–5 | Shown as *design slides*, not live | Live |
| Figures | One preliminary load curve + hit-rate table (W8) | Headline A + Headline B with CIs, baseline comparison |
| Message | "The platform exists end-to-end; here is the research I will do on top of it." | "Here are the proposal's claims, and here is the measured evidence for each." |

## 7. Insurance

- **Record a full run-through video** of the demo (timeline W9 and W22). If anything breaks live, narrate the video without apology — councils accept this routinely.
- Test the demo **on the projector/screen setup** if possible: font sizes on the metrics panel must be readable from the back of the room.
- Have the two headline figures printed as a handout fallback.
