# Recommended system — pivot proposal for the advisor meeting

**Created:** 2026-09-09 · **For:** advisor meeting 2026-09-10 · **Status:** ⚠️ **DRAFT — nothing
in this file is decided.** The current codebase and `docs/` are still the frozen source of truth.
This file exists so the author has one place to review, the night before, everything that came.  
out of a same-day research spawn (Opus agent, full transcript folded in below) before deciding
what to actually bring into the room tomorrow.

**What happens after the meeting, not before:** if the advisor agrees with some or all of this,
the next steps are — in order — an ADR (or several) in `docs/decisions.md`, an edit to
`docs/interfaces.md` where the contract changes, and only then edits to `docs/Final_Proposal.md`
(claims C1/C2/C3, literature review) and the report. **None of that is done yet.** This file is
the pre-meeting staging ground, not the change itself.

---

## 1. Why this file exists

A same-session conversation worked through: (a) whether Tier-1 needed `product_id` in its key
(implemented, as a workflow bypass — see `.docs/work/two-lane-cache/approvals.md`), (b) whether
Tier-2's unfiltered "Phase 1" search is still pulling its weight now that the three-lane namespace
rule exists, and (c) — the open question that actually matters for the thesis — how to detect the
most dangerous unsolved failure mode: **a cached answer and a new query share the same or
near-identical grounding, similarity is high, but the correct answer is opposite**, because the
query differs by a condition-flipping word or phrase ("opened" vs "unopened", "warranty" vs
"return"). This is the structural boundary already proven in `docs/learning/10-theory-of-the-two-
tiers.md` §E: `overlap = 1` is necessary but not sufficient, because it says nothing about `q`.

An Opus subagent was spawned to research four questions against the actual literature and
production practice, grounded in this repo's real constraints (no ML on the hit path — ADR-016;
lane/reuse decisions read from provenance, never from query text — ADR-018; deterministic,
swept-not-hand-set thresholds — `.docs/ai/rules.md` #10). Its findings are folded into §3 below,
condensed from the full memo already relayed in conversation. Citations are kept because they are
the thing worth bringing to the advisor.

---

## 2. Current state — what is actually built, as of 2026-09-09

| Component | Status |
| :--- | :--- |
| Tier-1 exact-match, scoped by `product_id` | **Built, bypassed workflow** (`cache.Key(normalized, productID)`) — reverses ADR-028's "product_id in the Tier-1 key — Rejected" for the narrow literal-duplicate-text-across-products case. Owed: a superseding ADR, `interfaces.md` §D edit, `/approve contract` + `/approve experiment`. |
| Tier-2 three-lane namespace rule (SPEC/POLICY/MIXED) | **Built** (`reuse/lane.go`), ships **OFF by default** (`LANE_SIGMA_HI = LANE_SIGMA`, band collapsed). Measured on `dev-v0` (not citable, 17 probes): namespace rule beat pure containment 4/4 on the measured disagreements. Owed: ADR, pre-registration of `(σ_lo, σ_hi)`, a `v1` run. |
| Tier-2 "Phase 1" (unfiltered KNN + τ_high) | **Built, load-bearing today** for the `similarity_only_decision` counterfactual (`interfaces.md` §H) and for `τ_high` (disabled). Proven functionally redundant for the *served* reuse decision — namespace/lane re-checks τ independently on the scoped candidate. |
| Admission control (permit pool, shed, coalescing) | **Built and measured.** 8 concurrent distinct requests at `permits=4` → exactly 4×200 / 4×503; 5 concurrent identical → coalesced to one generation. ⚠️ **Threatened by unresolved `env-check` finding F1**: Ollama overrides `OLLAMA_NUM_PARALLEL` to `-np 1`, so the permit pool may be bounding to a concurrency the model server never actually offers. |
| C2 — dependency map / invalidation | **0% implemented.** `gateway/internal/deps/` is a package-doc stub only. This is this week's (W9) gate requirement. |
| G4-equivalent (lexical support gate) | **Not implemented.** See §3.2 — this is the main new idea from tonight's research. |
| `v1` corpus | **Not built.** `dev-v0` measured G1=0, G2=0 B-within — cannot express the phenomenon C1 studies. |

---

## 3. Research findings (Opus agent, 2026-09-09) — condensed, with sources

Full grounding read by the agent: `CLAUDE.md`; `docs/decisions.md` ADR-016/018/019/024/026/027/028/030/031/032/033; `gateway/internal/reuse/{lane,rule}.go`; `docs/learning/10-theory-of-the-two-tiers.md` §E; `docs/learning/11-tier2-two-signals.md` §12; `.docs/work/two-lane-cache/approvals.md`; `docs/interfaces.md` §E.

### 3.1 Executive summary

1. **MIXED-lane decomposition** (split a mixed question into a spec fragment + a policy fragment, cache each independently) is a real, structurally novel idea (fragment keyed by *chunk-set*, not by text or embedding — literature has fragment-caching but always text/embedding-keyed) — but it is the most expensive of the four directions and changes the experiment grid. **Recommendation: future work, or a bounded ablation on the MIXED stratum only — not a shipped tier.**
2. **The opposite-meaning false hit is the one question that matters most, and there is a direction that satisfies every constraint** — it already sits inside a paper `ADR-026` cites and does not fully adopt. See §3.2.
3. **Invalidation design is not missing anything obvious.** It is the RAG-cache instance of CDN cache-tag/surrogate-key invalidation (Akamai/Fastly/Varnish, a decade-old pattern) — a positioning strength, not a redesign need.
4. **Admission control stands on its own**, independent of how the Tier-2 research question resolves. It is a recognized, currently-active LLM-serving research pattern (2026). Its one real threat is internal (F1), not literature.

### 3.2 The core finding — GroundedCache's fourth gate (G4)

Source: [Grounded Cache Routing for RAG: When Is It Safe to Reuse an Answer? (arXiv 2605.27494)](https://arxiv.org/abs/2605.27494) — the same paper `ADR-026` already cites to narrow C1's novelty. `ADR-026` maps three of the paper's four gates onto this system's mechanisms. **The fourth is not adopted.**

> **G4 (lexical support).** `S(a, C)` = the fraction of content tokens in the cached answer `a`
> that also appear in the freshly-retrieved evidence `C`. Content tokens exclude stopwords and
> tokens under 3 characters. Reject reuse when `S(a,C) < τ_s` (paper default `τ_s = 0.6`).
>
> The paper's own per-gate ablation: *"the lexical support gate is the load-bearing safety
> mechanism... removing it raises unsafe-served rate by +0.12–0.13."*

**Why it fits every constraint this project has:**

| Constraint | G4 |
| :--- | :--- |
| No ML on the hit path (ADR-016) | Satisfied — tokenize, stopword-filter, set-intersect, divide. Pure Go, no model. |
| Reads only provenance, never the query text (ADR-018's reasoning) | Satisfied — G4 reads the **cached answer's text** and the **newly retrieved chunks' text**. Both are provenance-side artifacts, not the query. |
| Cost | Microseconds, against a hit path already measured at ~27 ms (dominated by embed + Retrieve RPC). |

**Concrete worked trace, on this project's own measured pair** (`.docs/work/two-lane-cache/approvals.md`, 2026-09-06): cached answer *"electronics carry a 30-day return window, full refund"* vs. a warranty question retrieving `policy-warranty#chunk-*`. Both score containment **0.80** identically (no θ separates them — the documented failure). G4 does separate them: the cached answer's tokens {return, window, refund, day} barely overlap the warranty chunk's tokens {warranty, defect, coverage} — `S` collapses, G4 refuses.

**The honest limit, stated precisely (do not let this be discovered instead of disclosed):** G4 is an **evidence-mismatch** detector. It catches false hits where the *wrong chunk/document* got associated with the query (cross-document, cross-namespace-adjacent cases — exactly the POLICY-lane warranty/return trap). It does **not** catch the case where retrieval genuinely returns the *same* chunk both times and the query itself flips the condition within that one chunk (e.g. "is the battery removable" vs "is the battery NOT removable", or a policy paragraph that states both "opened" and "unopened" conditions together) — there, the freshly-retrieved evidence is identical either way, so G4 sees full lexical support regardless of which reading is being asked. **This residual is exactly the structural limit already proven in `10-theory-of-the-two-tiers.md` §E — G4 narrows it, it does not close it.**

**Consequence:** G4 and condition-tagging at ingestion (§3.4) are complementary, not redundant — G4 catches cross-chunk evidence mismatches; condition-tagging is what prevents the same-chunk case from existing in the first place, by forcing opposing conditions apart at corpus-authoring time.

### 3.3 The uncomfortable finding to bring to the advisor

⚠️ (numbers read via HTML/abstract fetch — re-verify against the PDF before citing in the report) On GroundedCache's own benchmark: a naive semantic cache achieves ~1.95× speedup but is unsafe; the fully-gated (all 4 gates) version achieves **~1.04× speedup** — barely a cache at all, in exchange for near-zero unsafe hits.

**If this transfers to this project's workload, the load-conversion claim and the safety claim pull in opposite directions.** The honest headline may need to be a **frontier** (hit-rate vs. safety, at a stated δ), not a single speedup number. The system's design already anticipates this (Wilson intervals at δ, the pre-registered null) — but the **narrative** framing for the report/defense may need an explicit adjustment. This is squarely a question for the advisor, not a unilateral call.

### 3.4 Other directions, condensed (full classification table was in the research memo; kept here only where it changes a decision)

- **Condition-tags at ingestion + finer chunking** (⭐ second-strongest direction) — tag each chunk at corpus-build time with a structured attribute (e.g. `condition: opened|unopened`); reuse requires tag-set agreement, not just chunk overlap. No ML, no query-text read, cost is corpus/contract work. **This is largely work already owed** — `ADR-024` requirement 3 already says "distinct conditions must land in distinct chunks or there is nothing for containment to separate." The only new decision is whether to add an explicit tag on top of the chunk split. **Must be decided before the `v1` freeze, not after** — it is cheap now, expensive later.
- **Margin/gap-check** (rank-1 vs rank-2 similarity) — deterministic, no text read, but weak for this project's specific measured trap (the false hit scored *higher* similarity than the correct answer, 0.9578 vs 0.9382 — a margin check would not have flagged it). Cite in related work; do not build.
- **NLI/entailment gate, negation-aware embeddings, LLM-judge-per-query** — all categorically out of bounds (ML on hit path, or breaks the frozen embedding model, or defeats the cache's purpose by calling an LLM per request). Independently confirmed by [The Semantic Illusion (arXiv 2512.15068)](https://arxiv.org/abs/2512.15068): NLI models collapse under conformal calibration the same way embeddings do; only a full LLM judge (7% FPR) actually solves it — and that costs the generation being cached. **This is a real finding for the thesis, not just a scope excuse**: the cheap version doesn't work well enough, and the version that works isn't cheap.
- **Async/admission-time verification** (verify at cache-write time, not serve time — e.g. Apple's Krites, arXiv 2602.13165) — architecturally interesting, would let a full LLM-judge call happen off the hit path (amortized over every future hit on that entry), but changes what the false-hit metric measures (catches *repeat* false hits, not the first one) and is a ~3-week detour. **Flag as a design-space observation for the write-up, not a build item**, unless the advisor is specifically excited by it.
- **Fine-grained fragment caching (§1's MIXED decomposition)** — feasible as a bounded ablation on the MIXED stratum only (deterministic concatenation instead of an LLM synthesis call, reported as "what fragmenting would buy" rather than shipped). A full third cache tier with synthesis is not realistic in the remaining ~13 weeks given `v1` is not yet frozen.

### 3.5 Invalidation — no redesign needed

The frozen design (`interfaces.md` §E: `dep:{chunk_id} → SET(entry_id)`, single writer goroutine, copy-on-write in-process index, monotonic `dataset:epoch`, blind purge) **is** the mature industry pattern — CDN cache-tag / surrogate-key invalidation (Akamai, Fastly, Varnish `xkey`). Good positioning sentence for the report: *"the dependency map is the RAG-cache instance of CDN surrogate-key invalidation, with the source chunk as the tag."*

One gap worth adding to `interfaces.md` §E before implementation: **invalidation latency is not currently specified.** Between an edit event and the completed Redis purge fan-out, an entry is stale-but-servable — a read landing in that window is a real staleness case, not covered by the epoch guard (which only protects write-back). Either check `dataset:epoch` on the read path too, or state and measure the window.

The only genuinely different alternative (epoch-in-key, versioned lazy invalidation — bump the epoch, let LRU reclaim orphans, no dependency map at all) is **strictly worse for this thesis**: it makes invalidation maximally imprecise (one edit invalidates the *entire* cache), which makes the `substantive`/`cosmetic` over-invalidation metric (ADR-024) uninformative, and it deletes C2 (the lock-free dependency map) as a differentiator entirely. Good slide (shows the simplest alternative was considered and rejected for a stated reason), not a redesign.

### 3.6 Admission control — confirmed as an independent, currently-active systems pattern

Bounded-concurrency admission control + graceful `503`+`Retry-After` shedding + bounded queues + request coalescing in front of an LLM service is recognized, current (2026) research and production practice: [BeLLMan (arXiv 2510.15330)](https://arxiv.org/pdf/2510.15330), [llm-d flow control (Red Hat, Aug 2026)](https://developers.redhat.com/articles/2026/08/27/llm-d-flow-control-priority-queuing-for-shared-gpu-inference) — *"admission control determines when a request can advance; scheduling determines where"*, matching this gateway's role precisely — Ray Serve's bounded queues + 503 shedding, vLLM's explicit requirement for an external admission controller. Coalescing via `singleflight`/request-coalescing is a named, standard pattern.

**This contribution does not depend on how the Tier-2 research question resolves.** `ADR-026`'s own conclusion — *"the 60% systems pillar is untouched by either [prior-art] system"* — holds; neither GroundedCache nor FinCacheServe bounds concurrent residency or sheds under memory pressure.

**The one real threat is internal, not literature: finding F1.** `env-check` already recorded that Ollama overrides `OLLAMA_NUM_PARALLEL` to `-np 1` for this model, meaning the permit pool (`permits=4`) may admit work that then queues *inside* Ollama, invisible to and unshedddable by the gateway — the exact failure admission control exists to prevent. Any shed rate measured under that condition describes the harness, not the gateway. **This must be resolved before any admission-control number is reported as citable — ahead of everything else in this file.**

### 3.7 Two live findings from demo rehearsal, 2026-09-09 (functional run, `dev-v0`, τ=0.85/θ=0.60 demo values — not swept, not citable, but real and worth bringing tomorrow)

Found by hand-testing the debug UI against furniture/headphones products, not by design. Both are
stronger, more concrete evidence for points already in this file than anything synthetic.

**Finding 1 — POLICY-lane namespace rank-1 instability contaminates cached CONTENT, not just its
label.** Asking *"what is the maximum number of days i can return this product?"* on an Office
Chair (furniture) page returned a correct-sounding furniture answer, but the response's
`namespace` field read `policy-returns-electronics` — the wrong policy. Cause: `Namespace()` for
the POLICY lane takes the **first** `policy-`-prefixed chunk in `retrieved.ChunkIDs`
(`firstDocIDWithPrefix`), and in this retrieval `policy-returns-electronics#chunk-0` happened to
rank first even though the answer was grounded in furniture's 14-day policy. Worse than a label
bug: a later question — *"how can i return this product?"*, no product context — retrieved chunks
from **two different furniture products at once** (`product-furniture-07` and
`product-furniture-03`), and the LLM, given both in context, generated an answer naming **both
products by name**. That answer was cached and later correctly *reused* (`TIER2_HIT`, sim=1.00,
overlap=1.00, `rule=namespace`) — the reuse rule did its job faithfully; the contamination
happened at **generation time**, from a query with no stabilizing context. This is the live,
concrete version of the "POLICY lane has no `product_id`-equivalent stabiliser" gap already
flagged in conversation — SPEC lane has one, POLICY lane does not.

⚠️ **Independent of decision 6 (Phase 1 removal) — do not conflate the two.** `Classify()` and
`Namespace()` run identically whether Phase 1 exists or not; `firstDocIDWithPrefix` picks
whatever ranks first in `retrieved.ChunkIDs` either way, and the generation-time contamination
(two products in one retrieval) happens entirely outside the Tier-2 cascade. **Removing Phase 1
tomorrow does not fix Finding 1.** What would: G4 (decision 2, catches it if the served answer's
text stops matching newly-retrieved evidence) or a dedicated POLICY-lane stabiliser — neither
built yet, both out of scope for tomorrow's code, in scope for what gets said out loud.

**Finding 2 — the `τ_high` "disabled" boundary is not airtight, and it demonstrates C1's own
thesis by accident.** Sequence: *"can i reuturn this after 999 days?"* asked once → `MISS`,
sim=0.7980, generated and cached (grounded in headphones policy). The **identical** text asked
again (different `product_id` context, so Tier-1 correctly missed) → `TIER2_HIT`,
**sim=1.0000, `rule=similarity_only`, `source_overlap` and `lane` both null**. `similarity_only`
means the `τ_high` short-circuit fired — reuse served with **no provenance check at all**. `τ_high`
is configured at exactly `1.0` specifically to be unreachable (`docs/learning/11-tier2-two-signals.md`
§7: shipped disabled). But the gate is `similarity >= τ_high`, not `>`, and a **literal repeat**
re-embeds to a bit-identical vector — cosine of a vector against itself is exactly `1.0` in
floating point, not an approximation that rounds up. The boundary is reachable after all, on
exactly the case (an identical query re-asked in a different context) that most needs the
provenance check to run. This is a small, real, easily-fixed bug (`>=` → `>`, or pin `τ_high` above
1.0 so it is unreachable by construction) — **not fixed tonight**, per the standing rule that
source changes wait for tomorrow's decisions — but it is close to the best possible illustration of
this thesis's own central claim: even a threshold believed disabled can silently let a
similarity-only reuse through, in exactly the shape (same text, different grounding context) C1
exists to catch.

**Why both matter for tomorrow, beyond being bugs to fix eventually:** Finding 1 strengthens the
case for G4 (decision 2) and condition-tagging (decision 4) with a real example, not a
constructed one. Finding 2 is close to unusable-as-is for the report (it is a boundary-condition
artifact of a disabled knob, not a finding about the reuse rule itself) but is an excellent
*verbal* anecdote for the meeting — it makes the hit-rate/safety tension (slide 10 / §3.3) concrete
rather than abstract.

---

## 4. Recommended priority order (for the remaining ~13 weeks)

| # | Item | Why this order |
| :--- | :--- | :--- |
| 1 | **Resolve F1** (Ollama `-np` mismatch) | Threatens the already-measured 60% pillar. Nothing else matters if this isn't fixed first. |
| 2 | **Build C2** (dependency map, blind purge, epoch guard) — keep the existing frozen design | 0% code today, is this week's gate, and research confirms the design needs no change. |
| 3 | **Add G4** (lexical-support gate) to `reuse/` | Cheapest new mechanism (~1–2 weeks), satisfies every constraint, directly targets the highest-priority open question, has a literature default (`τ_s=0.6`) to ship as an ablation without a fifth sweep dimension. |
| 4 | **Decide condition-tagging** as part of `v1` corpus authoring | Already-owed work (ADR-024 requirement 3); the only new decision is the explicit tag. Must decide before the freeze. |
| 5 | **Phase 1 removal** — conditional, see §5 | Not on the critical path of 1–4. Zero benefit to any of them. Defer until after the advisor confirms the framing pivot (§5). |
| — | Fragment-caching (MIXED decomposition), admission-time LLM verification | Explicitly **not** in scope for the remaining time — future work only. |

---

## 5. Phase 1 removal — the conditional decision

**Do not remove Phase 1 unconditionally.** Two separate justifications were examined in conversation, and only one of them is currently available:

- **Correctness**: already proven redundant — the namespace/lane rule independently re-checks `similarity ≥ τ` on its own scoped candidate, so the served verdict is identical with or without Phase 1's unfiltered gate. **This alone is not sufficient reason to remove it.**
- **Measurement**: Phase 1 is the *only* source of the `similarity_only_decision` counterfactual required by `interfaces.md` §H (frozen, "measurement-critical") — the number that lets the report say "a similarity-only baseline (GPTCache-equivalent) would have been wrong here." Removing Phase 1 removes this capability entirely, and `τ_high` (disabled but still speced) becomes meaningless without it.

**The removal only becomes justified if the advisor agrees to a framing pivot:** away from "prove provenance beats similarity-only" (already partly conceded not novel by ADR-026) and toward "the three-lane namespace rule + G4 lexical gate is the reuse mechanism; here is the residual risk, characterized and partially bounded." Under that pivot, the similarity-only counterfactual is no longer the thesis's headline measurement, and Phase 1 (plus `τ_high`) can be retired.

**If the advisor agrees tomorrow**, removal requires, properly (not another workflow bypass):

1. An ADR retiring `similarity_only_decision` reporting, citing the framing pivot as the reason.
2. Removing `τ_high` alongside it (it has no function without Phase 1's unfiltered candidate) — code, env var, and the pinned-default test.
3. Checking `experiment-protocol.md`'s five-configuration grid (`ADR-023`) — does config 3 (similarity-only baseline) still get measured as an independent benchmark run, decoupled from the live runtime cascade? If so, nothing is lost; if config 3's measurement depended on Phase 1 running inline, that needs its own resolution.

### Proposed post-pivot sequence (draft only, for discussion)

```
Client      Gateway(Go)         Tier1(Redis)   Tier2(Redis)      reuse/        Admission   RAG+Ollama
  |             |                    |              |                |            |            |
  |--POST /ask->|                    |              |                |            |            |
  |             |--Get(q,pid)------->|              |                |            |            |
  |             |<--MISS-------------|              |                |            |            |
  |             |==embed(q)========================================================>|          |
  |             |==retrieve(q) [concurrent]====================================================>|
  |             |<==vec, retrieved.ChunkIDs====================================================  |
  |             |          Classify(chunkIDs) -> lane (SPEC/POLICY/MIXED, pure fn)               |
  |             |          Namespace(lane, chunkIDs, productID) -> ns                             |
  |             |--KNN(k=1, SCOPED to ns)------------->|                |                        |
  |             |<--candidate, sim----------------------|                |                        |
  |             |--DecideLane(sim>=tau AND ns match)------------------->|                        |
  |             |                                                        |--reuse? -> G4 check:  |
  |             |                                                        |   lexical-support(cached_answer, retrieved_evidence) >= tau_s?
  |             |<--final Reuse/Refuse-----------------------------------|                        |
  |      [Refuse -> MISS, generate]                                                               |
  |             |--Generations.Do(coalesceKey)-------------------------------------->|            |
  |             |                                    |--Admission.Acquire()-------->|             |
  |             |                                    |<--permit / 503 shed----------|             |
  |             |                                    |--RAG.Answer(q, retrievedIDs)-------------->|
  |             |                                    |<--text, sources-----------------------------|
  |             |--Put(t1) + PutTier2(t2, epoch) + deps.Register(entry_id, chunks)               |
  |<--200-------|                    |              |                |                           |
```

No unfiltered Phase-1 search, no `τ_high` branch — one scoped Tier-2 search, `DecideLane`, then the new G4 gate before serving.

### Proposed post-pivot architecture (draft only)

```
+-------------------------- Go Gateway --------------------------+
|  httpapi/handler.go -> cache/ (Tier-1: t1:{sha256(norm+pid)})   |
|                      -> embed/, ragclient/                       |
|                      -> cascade.go -> cache/ (Tier-2, scoped KNN)|
|                                    -> reuse/                     |
|                                        lane.go   (Classify, NS)  |
|                                        rule.go   (containment)   |
|                                        lexical.go (NEW: G4)      |
|                      -> coalesce/, admission/ (verify F1 first)  |
|  deps/  (C2, NEW)                                                |
|    Register(entry_id, chunk_ids) after every write-back          |
|    in-process copy-on-write map, single writer goroutine         |
|    Redis: dep:{chunk_id} -> SET(entry_id)  [noeviction region]   |
+-------------------------------------------------------------------+
              | gRPC
              v
+------------------ Python RAG service ------------------+
|  retrieve.py (LlamaIndex, FLAT/COSINE)                   |
|  generate.py (Ollama, Qwen 3.5 2B, num_ctx=8192)          |
+-----------------------------------------------------------+
              v
+---------------- Redis (two eviction regions) -------------+
|  LRU:        t1:*, t2:*, idx:cache, idx:corpus, lru:*      |
|  noeviction: dep:*, dataset:epoch                          |
+-------------------------------------------------------------+
```

---

## 6. Draft reframing of C1/C2/C3 — for discussion only, NOT applied to `Final_Proposal.md` yet

This section is a preview of what would change if the advisor approves the pivot. **Nothing here has been written into `docs/Final_Proposal.md` or `docs/decisions.md`.** It exists so the author walks into the meeting with the shape of the change already thought through, not to pre-empt the advisor's decision.

- **C1 (was: "retrieval provenance beats embedding similarity as a reuse-safety signal")** → proposed: *"a namespace-partitioned provenance rule, augmented by a deterministic answer-evidence lexical-support gate, dominates a fixed-threshold similarity baseline at a pre-registered error budget δ; the residual failure mode (same-evidence, opposite-condition queries) is characterized as a structural limit, not eliminated."* Narrower than the original claim, but non-redundant against both prior-art papers ADR-026 already found (neither has the namespace+lexical-gate combination), and honest about what remains open.
- **C2 (dependency map / invalidation)** — unchanged in mechanism; framing gains the CDN surrogate-key positioning from §3.5, plus the invalidation-latency measurement gap noted there.
- **C3 (or wherever admission control is numbered)** — unchanged; strengthened by the 2026 llm-d/BeLLMan citations in §3.6, contingent on F1 being resolved first.
- **Literature review** — needs a new paragraph on the negation/polarity-blindness literature (§3.2's citations: the *Scientific Reports* 2025 negation-similarity finding, NevIR/ExcluIR benchmarks, and *The Semantic Illusion* arXiv 2512.15068) as the independent confirmation of the `10-theory-of-the-two-tiers.md` §E structural argument — this is new, citable support that did not exist in the current literature review.
- **`experiment-protocol.md`** — needs review of whether config 3 (similarity-only baseline) is still measured as intended once Phase 1 is retired from the live cascade (§5, point 3).

---

## 7. Agenda for the advisor meeting, 2026-09-10 (six questions, priority order)

1. **F1** — Ollama overriding `OLLAMA_NUM_PARALLEL` to `-np 1`. Resolve before anything else; it threatens an already-measured contribution.
2. **Adopt GroundedCache's G4?** ADR-026 cites the paper but not this gate; the paper's own ablation calls it load-bearing. Adopt as an ablation at their default `τ_s=0.6`, or deliberately not adopt and record why?
3. **The hit-rate/safety tension** (§3.3) — if full safety gating collapses hit rate the way GroundedCache's own numbers suggest, should the headline result be framed as a frontier rather than a speedup?
4. **Condition-tagging** — decide before the `v1` freeze, since it is cheap now and expensive after.
5. **Is MIXED-lane fragment caching (§1) a bounded ablation, or a future-work paragraph?** Given `v1` is not yet frozen, my read is: not a shipped tier in the remaining time.
6. **Phase 1 removal and the framing pivot (§5)** — is the advisor willing to move C1's headline claim from "provenance vs. similarity" to "namespace + lexical-support gate, residual risk characterized"? This is the one decision that changes what gets built for the rest of the term, not just a code cleanup.

---

## 8. Execution plan if approved — fix / build / test, starting from today's codebase

Concrete, per priority item from §4. Each item lists what changes in the existing codebase
(**Fix**), what is genuinely new (**Build**), and what must be tested before moving to the next
item — do not batch `make verify` to the end, run it after each priority lands.

### 8.1 Priority 1 — resolve F1 (Ollama `-np` mismatch)

**Fix:**
- Confirm the real behavior: run `OLLAMA_NUM_PARALLEL=4 ollama serve` and check whether Ollama
  actually serves 4 concurrent generations for `qwen3.5` or silently caps at `-np 1`.
- If capped at 1: set `permits=1` in `gateway/cmd/gateway/main.go`'s admission pool
  initialization, and **re-derive the whole envelope** (μ_gen, `h*`, λ_max) — ADR-017's frozen
  pair assumed `NUM_PARALLEL=4` actually took effect.
- If a real fix exists (Ollama config/flag to force true parallelism for this model): apply it,
  keep `permits=4`.

**Test:**
- `make env-check` — confirm F1 no longer fires.
- Re-run the A2/A3-style admission test (N concurrent distinct requests, count 200s vs 503s)
  against the corrected concurrency.
- If `permits` changed: re-run the μ_gen/μ_hit probes.

**Files:** `gateway/cmd/gateway/main.go`, `Makefile` (`env-check` target), a new ADR in
`docs/decisions.md` recording the resolution.

### 8.2 Priority 2 — build C2 (dependency map + invalidation), 0% → complete

**Build (all new):**
- `gateway/internal/deps/deps.go` — in-process copy-on-write map (`atomic.Pointer` or
  `sync.RWMutex`), `Register(entryID string, chunkIDs []string)`.
- A single writer goroutine fed by a channel, consuming invalidation events matching
  `interfaces.md` §E's schema (`chunk_id, doc_id, change_type, new_text, dataset_version, ts`),
  updating the in-process index, then fanning the purge out to Redis off the request path.
- Purge logic: `SMEMBERS dep:{chunk_id}` → for each `entry_id`, delete `t2:{entry_id}` **and**
  `t1:{the t1_key stored on that Tier-2 record}` → `DEL dep:{chunk_id}` → `INCR dataset:epoch`.
- **An edit-trigger surface** — check `docs/defense_demo.md` for an expected demo affordance; if
  none exists, add a small admin path or `make` target to fire an edit event.

**Fix (a real gap found while planning this, not previously implemented):**
- **The epoch guard at write-back does not exist yet.** `handler.go` currently only *stamps* the
  epoch observed at retrieval time and `PutTier2` only *stores* it — there is no comparison
  against the current `dataset:epoch` before writing. Add: before `Cache.Put`/`PutTier2`, read
  the current epoch; if it has advanced past the one captured at retrieval, discard the
  write-back and set `rec.WritebackDisc = true` (the `telemetry.Record` field already exists,
  it is simply never set today).
- `make redis-check`'s allowed-key-prefix guard needs `dep:` added, or it will read the new
  prefix as foreign and start refusing `demo-reset` — the same failure A4's `lru:` prefix caused
  once already (`.docs/work/two-lane-cache/approvals.md`).

**Test:**
- `deps_test.go`: register an entry, purge one chunk, assert exactly its dependents are gone and
  unrelated entries survive — this **is** the W9 gate's exit criterion, so this test doubles as
  the gate check.
- `-race`: concurrent `Register` and purge.
- Epoch-guard test: simulate a generation in flight when an edit lands mid-flight; assert the
  write-back is discarded, not resurrected.
- `make redis-check` again, with `dep:*` present.

**Files:** `gateway/internal/deps/*.go` (new), `gateway/internal/httpapi/handler.go` (wire
`Register` + the epoch-guard check), `gateway/cmd/gateway/main.go` (start the writer goroutine,
wire it into graceful shutdown), `Makefile`.

### 8.3 Priority 3 — add G4 (lexical-support gate) — ⚠️ a wiring gap surfaced while planning this

**The gap:** G4 needs to compare the cached answer's tokens against the **text** of the
freshly-retrieved chunks. Checking the actual `Retrieve` RPC (`contracts/rag/v1/rag.proto`,
`rag/src/rag/server.py`) shows it returns only `chunk_ids` and `scores` — **no text**. The
gateway (Go) has no chunk content to compare against today. This must be resolved before G4 can
run at all.

**Fix (contract change, needs its own ADR):**
- Extend the `Retrieve` RPC to also return chunk text — `contracts/rag/v1/rag.proto`,
  `rag/src/rag/server.py`'s `Retrieve` handler, `gateway/internal/ragclient/`, and
  `docs/interfaces.md` §B (frozen — cite the ADR).

**Build:**
- `gateway/internal/reuse/lexical.go` (new) — a tokenizer (lowercase, strip punctuation, split on
  whitespace), a small stopword list, a ≥3-character token-length filter, and
  `S(a, C) = |tokens(a) ∩ tokens(C)| / |tokens(a)|`.
- `Thresholds.TauS float64` (paper default `0.6`), called after `DecideLane` returns `Reuse=true`
  — a failing `S` overrides the verdict to refuse.
- A new eval-log value (`reuse_rule = "g4_refused"`) so a refusal caused by G4 is never confused
  with a namespace-caused refusal — the two-cause-attribution discipline this project already
  applies elsewhere.

**Test:**
- Golden-case unit test on this project's own measured pair (return-answer vs. warranty-chunk →
  `S` low; a real paraphrase → `S` high).
- Cascade-level test: the previously-measured false hit (namespace/containment says reuse) is now
  correctly refused by G4.
- Regression: every existing legitimate HIT case still clears `τ_s = 0.6` — G4 must not introduce
  new false *misses* on cases already passing.

**Files:** `contracts/rag/v1/rag.proto`, `rag/src/rag/server.py`, `gateway/internal/ragclient/`,
`gateway/internal/reuse/lexical.go` (new), `gateway/internal/httpapi/cascade.go`,
`docs/interfaces.md` §B.

### 8.4 Priority 4 — condition-tagging + the `v1` corpus

**Build:**
- Author real policy documents (5 categories × return + warranty, plus platform-wide, plus a
  couple of product-specific override traps — see the scope-level discussion this session), with
  opposing conditions deliberately split into separate chunks.
- Add `scope` / `applies_to_product` fields to the policy record schema.
- Convert `data/v1-draft/` (175 products, already fetched) into the frozen `data/v1/`, alongside
  the new policy corpus.

**Test:**
- `make gate-corpus VERSION=v1` — all four criteria (G1–G4) must pass.
- Manually confirm at least one constructed condition-flip pair retrieves two **different** chunks
  per condition — the mechanism G4/condition-tagging both depend on.

**Files:** `data/v1/*.json`, `docs/data-card.md` (fill the `TODO(W8)`s, then freeze).

### 8.5 Priority 5 — Phase 1 removal (only if the advisor approves the framing pivot)

**Fix:** remove the unfiltered Tier-2 search and the `τ_high` branch from `cascade.go`; remove
`Thresholds.TauHigh`; remove `similarity_only_decision` from the eval log and the `/ask` response.

**Test:** full regression; confirm `ui/` does not break if `similarity_only_decision` disappears
from the response; confirm `experiment-protocol.md`'s config 3 (similarity-only baseline) is still
measurable as an independent benchmark run once it is no longer computed inline in the cascade.

### 8.6 Cross-cutting, after every priority above

- `make verify` (lint + build + test) after each priority — not batched to the end.
- `-race` on every concurrency-sensitive package touched: `deps/`, `admission/`, `coalesce/`.
- Regression baseline: re-check the four familiar similarities `0.4237 / 0.9244 / 0.9382 /
  0.9578` (used throughout `.docs/work/two-lane-cache/approvals.md` as a smoke-test signature)
  after any change that could plausibly move them.
- `make demo-reset` after any Redis schema change.

---

## Sources (full list — from the 2026-09-09 research spawn)

**Semantic caching — safety and reuse gates**
- [Grounded Cache Routing for RAG (arXiv 2605.27494)](https://arxiv.org/abs/2605.27494)
- [FinCacheServe — Dependency-Consistent Answer Reuse (arXiv 2607.26076)](https://arxiv.org/abs/2607.26076)
- [vCache: Verified Semantic Prompt Caching (arXiv 2502.03771)](https://arxiv.org/abs/2502.03771)
- [Asynchronous Verified Semantic Caching — Krites (arXiv 2602.13165)](https://arxiv.org/abs/2602.13165) · [Apple ML Research](https://machinelearning.apple.com/research/semantic-caching)
- [Redis semantic cache docs](https://redis.io/docs/latest/develop/use-cases/semantic-cache/) · [10 techniques to optimize semantic cache — Redis LangCache](https://redis.io/blog/10-techniques-for-semantic-cache-optimization/)

**Production write-ups on false hits**
- [TrueFoundry — Why Text-Based Cache Keys Are the Wrong Default](https://www.truefoundry.com/blog/semantic-caching-llm-gateway)
- [Sage Engineering — What we learnt adding a semantic cache to a RAG service](https://engineeringatsage.com/posts/2026-07-semantic-cache-rag-service)
- [PyImageSearch — Semantic Caching for LLMs: TTLs, Confidence, and Cache Safety](https://pyimagesearch.com/2026/05/04/semantic-caching-for-llms-ttls-confidence-and-cache-safety/)

**Negation, embeddings, and verification limits**
- [The Semantic Illusion (arXiv 2512.15068)](https://arxiv.org/abs/2512.15068)
- [Computation of sentence similarity score... negation sentence (Scientific Reports 2025)](https://www.nature.com/articles/s41598-025-34084-2)
- [Semantic Adapter — Diagnosing and Mitigating Negation Blindness (arXiv 2504.00584)](https://arxiv.org/pdf/2504.00584)
- [E-SENS: Exclusion-Sensitive Penalization (arXiv 2608.30130)](https://arxiv.org/html/2608.30130v1)

**Decomposition and fragment-level caching**
- [SemanticALLI (arXiv 2601.16286)](https://arxiv.org/abs/2601.16286) · [CacheRAG (arXiv 2604.26176)](https://arxiv.org/abs/2604.26176) · [Cache-Craft (arXiv 2502.15734)](https://arxiv.org/pdf/2502.15734)
- [Dense X Retrieval — propositions](https://clusteredbytes.pages.dev/posts/2024/llamaindex-dense-x-retrieval/) · [PropRAG (arXiv 2504.18070)](https://arxiv.org/pdf/2504.18070)

**Invalidation**
- [Akamai — Purge methods / cache tags](https://techdocs.akamai.com/purge-cache/docs/purge-methods) · [Fastly Surrogate Keys](https://www.hward.com/varnish-cache-invalidation-with-fastly-surrogate-keys/)
- [Lazy Maintenance of Materialized Views (VLDB 2007)](https://www.vldb.org/conf/2007/papers/research/p231-zhou.pdf)

**Admission control, backpressure, coalescing**
- [BeLLMan (arXiv 2510.15330)](https://arxiv.org/pdf/2510.15330) · [llm-d flow control (Red Hat)](https://developers.redhat.com/articles/2026/08/27/llm-d-flow-control-priority-queuing-for-shared-gpu-inference)
- [Overload Control for Scaling WeChat Microservices (arXiv 1806.04075)](https://arxiv.org/pdf/1806.04075)
- [Request coalescing with Go singleflight](https://rednafi.com/go/request-coalescing/)

⚠️ Several numbers above (marked in §3) were read via HTML/abstract fetch during the research spawn — re-verify against the source PDF before they go into the report or defense slides.

---

## 9. Refined directions — deep research pass, 2026-09-10 late night

Four levers §3 did not cover: `v1` chunking, the embedding model, burst-shaped admission control, and any
remaining deterministic route to a tighter false-hit rate. **Every source below was fetched directly before being
written down**; one that failed that check is named in §9.4. Nothing here is decided.

### 9.1 The four levers

| Lever | Recommendation | Why | Effort | To adopt |
| :--- | :--- | :--- | :--- | :--- |
| **Chunking (`v1`)** | Split policy docs on **clause/section structure**, one condition per chunk, ~128–192 tok. Spend effort on **boundaries**, not size. Re-check `top_k=5` jointly. | Two 2026 evaluations converge on structure-aware over semantic and LLM-guided, at lower cost: [Taiwo & Yusoff, 2603.24556](https://arxiv.org/abs/2603.24556) (*table-heavy specifications*) and [Zhou et al., 2602.16974](https://arxiv.org/abs/2602.16974) — *"simple structure-based methods outperform LLM-guided alternatives for in-corpus retrieval."* Zhou also finds chunk **size** correlates only *weakly* with in-corpus retrieval: **the licence to pick boundaries for C1's benefit at little retrieval cost.** [Chroma](https://www.trychroma.com/research/evaluating-chunking) prices size — at top-5, precision **7.0 % @ 200 tok vs 3.6 % @ 400 tok**. | **Low** — corpus authoring already owed at `v1` | ADR amending **ADR-014 for `v1` only**. Cheap now, impossible after the freeze |
| **Embedding model** | **Don't swap on leaderboard scores — bake off on this corpus's own B-within traps.** One drop-in candidate: `embeddinggemma`. | Window genuinely open (no `v1` runs). `nomic-embed-text` is Feb-2024 ([2402.01613](https://arxiv.org/abs/2402.01613)). [EmbeddingGemma](https://arxiv.org/abs/2509.20354): 308 M, **natively 768-dim** so `DIM` is unchanged, 2K ctx, `<200 MB` quantized, 622 MB Ollama tag (needs Ollama ≥ 0.11.10); Google claims *"highest ranking open multilingual text embedding model under 500M."* [`qwen3-embedding:0.6b`](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B): MTEB **English v2 70.70**, 32K ctx — but **1024-dim**, changing `interfaces.md` §D. ⚠️ nomic reports MTEB **v1**, the others **v2**; the gap is *not* directly readable. | **Low–medium** — a re-ingest and re-probe | ADR superseding **ADR-003**, *only if the bake-off wins*. Code, not config: `embedding.py` hardcodes nomic's `search_query:`/`search_document:` prefixes |
| **Admission control** | **Keep the permit count static.** Add a **CoDel-style queue timeout + adaptive LIFO** as the burst discipline. | Under a retail burst the permit count must *not* move — memory fixes it (ADR-022) — so adaptation belongs in the **queue**. [Ben Maurer, *Fail at Scale*, ACM Queue 2015](https://queue.acm.org/detail.cfm?id=2839461) gives both in ~30 deterministic lines: CoDel (`if queue.lastEmptyTime() < now-N { timeout = M ms } else { timeout = N s }`) sheds by **deadline**; adaptive LIFO serves newest-first once a queue forms, the oldest waiter having usually already given up. `admission/pool.go` sheds on a **depth** bound today (a full `chan struct{}`) — burst-blind: a burst of long generations and a steady trickle look identical to it. | **Low–medium** — one package | Extends **ADR-022**. No contract or grid change |
| **Other → δ** | Add a **numeric-support gate** `S_num` beside G4's `S_lex`: every numeric literal+unit in the cached answer must appear in the fresh evidence, else refuse. | Sharper than G4 *on this domain*: policy answers are number-dense ("30-day", "1800 W") and the return/warranty trap differs precisely in its **number** even where prose tokens overlap. [Proof-Carrying Numbers (Solatorio, 2509.06902)](https://arxiv.org/abs/2509.06902) formalises exactly this — numeric spans mechanically matched under a declared policy, checked by *"a renderer, not the model"*, proven sound and **fail-closed** (the right default for a serving decision). [Sigloch & Benzmüller, 2605.26942](https://arxiv.org/abs/2605.26942) report symbolic pattern checks catching **>83 %** of hallucinated structured-entity values, no ML. | **~1 day over G4** — rides the *same* `Retrieve`-returns-text change §8.3 needs | Folds into G4's ADR; `S_lex` and `S_num` as **two** arms |

**Two honest limits.** `S_num` inherits G4's residual exactly (§3.2): same chunk, both conditions, both numbers
present → both gates pass. **Only the corpus split closes that** — a third reason priority 4 must land before the
`v1` freeze. And no leaderboard measures the condition-flip mode; §3.4's negation literature says every bi-encoder
is weak there, so **a swap plausibly buys retrieval quality and zero C1 safety** — itself the finding: *the
false-hit problem is not an embedding-quality problem.*

### 9.2 CacheSense — the foil C2 has been missing

CacheSense (Dang, Chen, Wu, Liu & Yang, 2026) invalidates by **similarity between changed content and cached
entries**, reporting a ~92 % reduction in stale-cache hits. That makes it the sharpest available comparison for
C2: it is architecturally *the design ADR-010 already rejected* — a similarity gate **estimating** which entries
an edit touches — and it reports exactly the number that argument predicts, **92 %, not 100 %**, the residual ~8 %
served stale with no error path. C2's blind purge is complete **by construction**: the dependency record is
written from the same `source_chunk_ids` the answer was generated over (ADR-033), so an edit's dependent set is
never estimated, it is **looked up**. C2's claim is therefore dominance *in kind, not degree* — **estimated →
looked-up**, not 92 % → 100 % — with the cost named in the same breath, since completeness is bought with
precision and the `substantive`/`cosmetic` split (ADR-024) prices it. It also sharpens **ADR-026 differentiator
4**: CacheSense reports the completeness *loss*, FinCacheServe reports completeness without precision — this
thesis would be the only one of the three reporting both sides. ⚠️ The 92 % figure is second-hand (relayed
ResearchGate record) — **confirm against the paper before the report.**

### 9.3 The 3–4 % question — for the advisor, not a decision

**ADR-006 froze δ ≤ 5 % *provisionally*, to be finalised ~W14 once judge error is measured**, on the rationale
that δ must clearly exceed the judge's own error — the metric's noise floor. Targeting 3–4 % **inverts that
logic**: it fixes the target before the floor is known. And the funded sample cannot see the difference — at the
~100 human-verified pairs ADR-016 left, the **Wilson 95 % interval around an observed 3.5 % runs ≈ [0.4 %, 8.2 %]**,
which contains 5 %. **3–4 % and 5 % are not separable at the sample size the budget pays for.** Three options:
**(a)** pre-register 3–4 % — needs an ADR superseding ADR-006 *and* a larger judged sample, which ADR-019's drop
order forbids buying by trading away the labelling ablation; **(b)** keep δ ≤ 5 % frozen and **additionally report
the (θ, τ) point at 3.5 %** as a second row on the same frontier — free, since the frontier is swept anyway, and
pre-commits nothing; **(c)** defer to W14 as ADR-006 already plans. **Recommend (b)**, merged with §7 question 3
(the hit-rate/safety tension) — they are one conversation.

### 9.4 What did NOT pan out

- **fin.ai, *Structured, Agentic RAG for Ecommerce*** (Shukla, 2026-05-07) — a search summary attributed two
  perfect quotes to it ("chunk at attribute level, not page level"; "keep policy chunks small"). **Fetching the
  page shows it contains neither**; they were synthesised across sources. Dropped — this pass's sharpest reminder
  that *a search snippet is not a source*.
- **Late chunking** ([2409.04701](https://arxiv.org/abs/2409.04701), Jina) — the right idea for this corpus, and
  nomic's 8192 ctx would support it. **Infeasible:** it needs token-level embeddings and per-chunk mean pooling,
  and Ollama's `/api/embed` returns one pooled vector per input, so it would need the in-process PyTorch stack
  ADR-017 rejected on the envelope. Future work.
- **RexBERT** ([2602.04605](https://arxiv.org/abs/2602.04605)) — e-commerce-specialised encoders (17 M–400 M)
  beating larger general ones, but a **base encoder needing fine-tuning**: ML on the critical path (ADR-016).
  **Amazon ESCI** likewise fails: query→product *ranking* with E/S/C/I labels, no policy docs, no paraphrase
  pairs — it cannot supply B-within traps and is no substitute for authoring `v1`.
- **Netflix `concurrency-limits`** (gradient / Vegas) — checked and **deliberately rejected**: it infers the limit
  from RTT, and latency is wrong here for the same reason ADR-022 rejected *rate* — the binding constraint is
  resident KV cache, and generation latency moves with output length. Keep as an ADR-022 *alternative considered*.
- **[2608.06135](https://arxiv.org/abs/2608.06135)** (WAIT modified for bursty LLM arrivals) and **Alibaba's
  Double 11 peaks** (583 k orders/s, 2020) — the first schedules *inside* the inference engine (unreachable;
  Ollama is a black box, and **F1** is the live proof), the second is a scale this envelope never engages. Only
  the burst *shape* transfers, which is what §9.1's queue row uses.
- **[2607.01852](https://arxiv.org/abs/2607.01852)** (chunking on academic texts) — cluster-based semantic chunking
  did *not* beat fixed-size/recursive. Corroborates "don't over-engineer chunking" but transfers poorly.
- **Redis's own "Improving semantic cache system performance" deck** (RedisConf-style vendor slide, 2025) — checked
  against this project point by point. Distance-threshold tuning is already done (τ/θ sweep). Cross-encoder
  reranker and LLM reranker/validator are both ML added to the decision path — the second is the exact
  LLM-judge-per-query already rejected in §3.4, same citation. Temporal context detection is the same idea as
  FreshCache above, already covered at the coarser bypass-classifier level (ADR-018). Code detection doesn't apply
  (no code content in this corpus). One item survives: **fuzzy matching** (typo/near-exact handling ahead of the
  embedding call) is genuinely ADR-016-compatible — edit-distance is deterministic, not ML — but it targets a
  failure mode (typos) this thesis doesn't study, so it's a one-line future-work note, not a build item.

### 9.5 Does this change §4 or §7?

**§4's priority order does not change — 1 → 5 stand as written**; two items only grow inside their existing slot:
priority **3 (G4)** gains `S_num` at ~one extra day on the same contract change and ADR, and priority **4 (`v1`)**
now also carries the **chunk-boundary** decision, which reinforces its "decide before the freeze" urgency rather
than altering it. **§7's agenda gains exactly one question and loses none** — the **embedding-model window**, open
only until the `v1` freeze — and §7 question 3 should be merged with §9.3's δ question, being one conversation.
