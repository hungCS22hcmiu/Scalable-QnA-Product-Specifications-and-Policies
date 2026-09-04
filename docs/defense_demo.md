# Defense Demo Plan — What to Show the Council

**Companion to:** `Final_Proposal.md` (contributions, evaluation) and `time_line.md` (when to build/rehearse this). **Revised:** 2026-08-09 (ADR-016).
**Principle:** the council grades claims and evidence, not product polish. The demo makes the invisible caching layer visible; the pre-run experiment figures are the evidence; the full e-commerce system never exists.

---

## 1. Scope of What Is Shown

**Not built, not shown:** user accounts, cart, checkout, orders, product browsing — no e-commerce product UI of any kind (proposal §12: the assistant and UI are hosts for the scalability layer, not products).

**Built and shown:**
- The **QA service** (Go gateway + Python RAG + local LLM) over the product/policy corpus.
- A minimal **debug-view UI** (one page) that exposes the system's decision-making.
- **Pre-computed experiment figures** on slides — the headline results are never generated live.
- A **recorded load-test clip** (~45 s), played as demo step 6. It is the only part of the demo that demonstrates scalability, and it is recorded rather than live so the overload region can be shown safely.
- The classify-and-bypass step (§6.3) may appear with a **stubbed** live source (fake stock/price) — its point is the routing decision, not real inventory. It is a **hardcoded keyword rule and not an evaluated component** (ADR-018); do not present it as a classifier or claim accuracy for it.

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
  "source_overlap": 0.80,                  // overlap rule score — Contribution 1
  "sources": ["policy-returns#chunk-2"]    // provenance tags — Contribution 2
}
```

`similarity` and `source_overlap` shown **side by side** are the whole research claim in two numbers: the council can watch a high-similarity, low-overlap query be correctly refused (step 4).

## 3. The Debug-View UI (1–2 days of work, no more)

One page:

- **Question box** + submit.
- **Answer area** (instant on a hit, ~4 s on a miss — no streaming; SSE is out of scope per ADR-016).
- **Metrics panel** per request: cache-path badge (color-coded: green TIER1, blue TIER2, orange MISS, grey BYPASS), latency, similarity, **source-overlap score**, and the source chunk IDs.
- For step 4, show **both** chunk-ID lists — the incoming query's retrieval and the candidate entry's provenance — so the overlap decision is visibly arithmetic rather than a black box.
- **Required sidebar** — running counters: total requests, hit rate, and **generations avoided**. Not optional. *Generations avoided* is the load-conversion ratio (§3) rendered as a single live number, which makes it the cheapest scalability evidence available and the only one visible during steps 1–5. It costs three counters and it is what stops the demo from being purely a correctness story.

A debug view beats a polished consumer UI at a defense: it makes the contribution observable.

## 4. The Six-Step Demo Script (~6 minutes, thesis defense)

Steps 1–5 are one live request each, demonstrating one mechanism each. **Step 6 is recorded**, and it is the only step that demonstrates the word in the title. Rehearse until steps 1–5 run twice in a row without touching code (`time_line.md` **W7**/W22 gates).

| Step | You do | Screen shows | Proves | Say out loud |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Ask a fresh question | `MISS` · ~4 s · sources listed | The expensive path every uncached system pays every time | "This is the cost of every request without caching." |
| 2 | Ask the **exact same** question | `TIER1_HIT` · ~5 ms | Exact-match tier | "Identical repeats — very common in product traffic — cost nothing." |
| 3 | Ask a **paraphrase** ("Is 30-day return possible for this laptop?") | `TIER2_HIT` · ~50 ms · similarity ≈ 0.9 · overlap ≈ 1.0 | Semantic tier | "Different words, same question, same sources — still no LLM call." |
| 4 | Ask a **lookalike trap** — near-identical wording, different product category with a different policy | similarity ≈ 0.94 **but overlap = 0.0** → `MISS` → *correct* answer. Show both chunk-ID lists | **Contribution 1** | "A fixed threshold would have served the wrong answer here — the questions look alike. But they ground in different chunks, and the rule can see that." |
| 5 | **Edit the policy file** (change 30→14 days), re-ask step 1's question | Entry purged → `MISS` → new correct answer | **Contribution 2** | "No stale answer, no waiting for a TTL — the cache tracked its sources." |
| **6** | **Play the recorded load clip** (~45 s) — do not run it live | Goodput climbing with the cache on vs. the cache-off baseline flattening; the counters' *generations avoided* rising; then at overload, `503`s appearing **while memory pressure stays green** | **Scalability — S1 + S2 (§3)** | "Steps 1–5 showed one request getting cheaper. This shows the machine absorbing more of them — and, past saturation, shedding instead of swapping." |

**Step 4 is stronger than it looks.** Because the decision is a set intersection rather than a model score, you can put the two chunk-ID lists on screen and let the council verify the refusal themselves. A learned predictor would have produced a number nobody in the room could check.

**Step 6 is not optional, and it is not live.** Without it the demo proves *correctness of caching* and never once demonstrates the title word: steps 1–5 are five sequential requests, and scalability here is goodput under concurrency (§3 S1), not latency per request. It stays **recorded** because live load tests are how defense demos die — and because a recording lets you show the overload region, which you cannot safely drive in a lecture room. The clip must contain three things or it is not doing its job:

1. **Goodput vs. offered load**, cache-on against cache-off — this is S1, the capacity claim.
2. **The shed transition** — `503 busy, retry` appearing while the memory-pressure indicator stays green. This is S2, and it is the single most convincing image in the thesis: the machine refusing work rather than dying of it.
3. **The counters** — *generations avoided* is the load-conversion ratio in one number.

**Covering S4 (thesis defense only).** Steps 1–5 fire the source edit with no concurrent load, so "invalidation without stalling the read fast path" is never shown. In the thesis-phase recording, **fire the policy edit while the load clip is running** and keep fast-path p99 on screen: the purge lands, dependent entries drop out of the hit counter, and p99 does not move. That single overlay covers S4 and turns C2 from a feature into a concurrency result.

### Demo data prep

- Seed the corpus so steps 3–5 are deterministic: pick the paraphrase and the lookalike trap in advance from the frozen workload, and verify their cache behaviour the night before. The trap must be a pair that a *tuned* fixed threshold genuinely gets wrong — if a fixed τ also refuses it, the step proves nothing.
- Keep a reset script (`make demo-reset`) that restores the corpus, flushes the cache, and pre-warms nothing — so the demo starts from a known state every rehearsal.

## 5. Defense-Day Structure

A defense is **slides + short scripted demo + Q&A** (~30–45 min total; confirm your program's exact format with the advisor).

1. **Slides (~15–20 min):** problem → architecture diagram (proposal §6) → contributions → **headline figures as the climax**: throughput/latency-vs-concurrency curves with stability telemetry (Headline A) and the hit-rate/false-hit frontier of the source-overlap rule vs. the fixed-threshold sweep at the finalized budget (Headline B). Comparison to prior art happens here, on a slide — never live.
2. **Demo (~6 min):** the six-step script above — five live requests, then the recorded load clip.
3. **Q&A:** expected pokes and where the answers live —
   - *"Why not just TTL?"* → §4, RQ3 results.
   - *"How is this different from vCache?"* → retrieval provenance as the decision signal, plus invalidation (§10). Be direct that vCache is compared **on design, not measured**, and why (ADR-016).
   - *"Why not learn the threshold?"* → the signal is the contribution, the model is the combiner; the rule isolates the signal and is inspectable. Learned combination is §14 future work, and the rule is the experiment that says whether it is worth building.
   - *"Is this really scalable on one laptop?"* → §3: the definition is capacity-per-fixed-envelope, its four clauses, and what is explicitly not claimed.
   - *"Does the benefit depend on your workload design?"* → redundancy is an independent variable, swept across three levels (§9.1).
   - **"Your demo is five sequential requests — where is the scalability?"** → concede the point and redirect: steps 1–5 demonstrate the *mechanism* (per-request cost asymmetry), **step 6 and Headline A demonstrate the *property*** (goodput under concurrency, and shedding rather than swapping past saturation). Scalability here is defined as capacity-per-fixed-envelope with four measurable clauses (§3), and a five-request script can only ever show S3.
   - **"Isn't your false-hit label circular with your rule?"** → the sharpest question you will get. Answer with the reference-free ablation: agreement between reference-anchored and reference-free labelling, **by overlap bucket** (ADR-019). Have that plot ready as a backup slide.
   - **"You tuned three parameters against one — how much of the gap is selection?"** → validation/test split by seed cluster; the frontier shown is held-out.
   - **"Your rule pays a retrieval on the hit path. Show me latency."** → hit-path p95 and % band-entry are reported at every frontier point, in the same figure.
   - **"Show me the memory budget."** → the W5 spike table: OS, weights, KV per sequence, Python, Redis, gateway, headroom (ADR-017).
   - **"Search engines have invalidated result caches on document updates for twenty years. What's new in C2?"** → concede the precedent immediately and cite it yourself; C2's contribution is the characterization on a live serving path plus the epoch-guarded write-back, not the mechanism (§5 C2).

## 6. Pre-Thesis vs. Thesis Defense

| | Pre-thesis (submit **Aug 31, 2026**) | Thesis (**Dec 13, 2026**) |
| :--- | :--- | :--- |
| Demo steps | **1–3 live** (miss, exact hit, semantic hit with fixed τ) | **Full 1–5 live** (incl. the overlap trap + live invalidation) |
| Steps 4–5 | Shown as *design slides*, not live | Live |
| Step 6 (scalability) | Recorded clip of the **in-process concurrency probe** (W7): hit vs. miss throughput at 1/2/4/8 clients. Modest, but it is the only scalability evidence the runway can produce — and it beats having none | Recorded **k6** clip: goodput cache-on vs. cache-off, the `503` shed transition with pressure green, and the mid-load source edit covering S4 |
| Figures | Hit-rate table + latency/concurrency table (W7) — labelled **preliminary and from `dev-v0`**, not citable as results | Headline A + Headline B with Wilson intervals |
| Message | "The platform exists end-to-end; here is the research I will do on top of it." | "Here are the proposal's claims, and here is the measured evidence for each." |

**On the pre-thesis Step 6.** The runway has no k6 harness and no off-box generator — both move to W8 (ADR-020) — so the pre-thesis clip comes from the simple in-process Go probe. Say so explicitly on the slide. A modest, honestly-labelled throughput comparison is a stronger position than presenting a correctness demo for a thesis whose title says *scalable*.

## 7. Insurance

- **Record a full run-through video** of the demo (timeline **W7** and W22). If anything breaks live, narrate the video without apology — councils accept this routinely.
- Test the demo **on the projector/screen setup** if possible: font sizes on the metrics panel must be readable from the back of the room.
- Have the two headline figures printed as a handout fallback.
