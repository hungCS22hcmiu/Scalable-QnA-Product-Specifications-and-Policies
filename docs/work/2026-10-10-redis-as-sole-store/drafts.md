# Ready-to-paste drafts — `Final_Proposal.md` and `CLAUDE.md`

Staged rather than applied. `Final_Proposal.md` is submitted prose and gitignored; `CLAUDE.md` is
the project's own instruction file. Both are the author's to edit. The ADRs this trail produced
**are** applied: ADR-007 and ADR-008 in `decisions.md`.

Every claim below is sourced to a finding in [`spec.md`](spec.md). Nothing here is a result —
corpus is `dev-v0`, and the only experiment ran on a throwaway Redis with six synthetic keys.

---

## 1 · §9.4 "Not controlled — carried as limitations" — three new entries

House style: numbered, bold lead-in, the mitigation or the absence of one stated plainly. Numbering
continues from the existing 12.

> **13. Storage-envelope conditionality, and what cancels.** Every figure is conditional on Redis
> holding the derived corpus index in memory under an exact **FLAT** scan. Two things follow, and
> they point in opposite directions. The **cache** does not grow with the corpus: capacity is
> `round(0.25 × K)` where `K` is the frozen workload's distinct-query count — a count of entries,
> not a byte budget — so a corpus an order of magnitude larger yields the same cache. The
> **retrieval index** does grow linearly, and FLAT is O(N) per query, which is the component that
> would not survive a production catalogue; the industry answer is approximate search over an
> in-memory index with documents in a separate store (arXiv 2510.26835 reports 30 ms → 2 ms on that
> split), and both scale-out and scale-up are out of scope here by §12. What rescues the comparison
> is that **the retrieval index is the same component in all five configurations**, so its cost
> cancels out of every contrast the study draws. The claim is load conversion within a fixed
> envelope; it is **not** a claim that the envelope scales, and no such claim is made. One
> operational corollary: Redis runs with `maxmemory=0` and `noeviction` by design, so the gateway's
> count-based trim is the only bound on cache size, and a mis-derived `K` presents as an OOM rather
> than as degradation.

> **14. Redis durability, and why a restart voids a run.** Redis holds derived state only — the
> corpus of record is the versioned file corpus (**ADR-007**) — so total loss loses no data. It is
> still an outage rather than the no-cache arm. The corpus index shares the process with the cache,
> so every request fails until Redis returns and, if the keyspace was lost, until the index is
> re-ingested. Redis is a single point of failure for availability, not for durability.
> Availability would need replicas, which is scale-out and out of scope. A **partial** loss is the
> subtler problem. The persistence posture
> is snapshot-only (`appendonly no`; live reading 2026-10-10), so an unclean stop rolls the keyspace
> back by up to an hour, and the rollback **silently undoes invalidations that had already fired**:
> a purged entry returns, the dependency map returns consistent with it, and the corpus index
> returns pre-edit while `data/` on disk does not roll back at all. This was demonstrated on an
> isolated instance rather than argued. Crucially the rollback is **invisible from inside Redis** —
> every intra-Redis invariant holds — so it cannot be detected after the fact from `raw/` alone. A
> run spanning a Redis restart is therefore inadmissible, and the check is only possible once P1's
> manifest records `redis_version` and `rdb_last_save_time`. Carried as an **RR**: violating it
> voids a result silently. Note this does **not** touch correctness invariant 1 — eviction remains
> the only route to an unpurgeable dependency record, and `make redis-check` closes it.

> **15. The containment signal is measured over a dense-only retriever.** `retrieve(q)` is dense
> top-k over a FLAT index. Production retrieval is hybrid — dense plus BM25, fused by reciprocal
> rank fusion, often with a cross-encoder rerank over ≤50 candidates — and on the WANDS e-commerce
> benchmark a tuned hybrid reports ≈7 % NDCG over either arm alone. This does **not** confound the
> systems claim: `retrieve(q)` is identical across all five configurations, so retrieval quality
> cancels. It **does** condition C1, whose signal *is* `retrieve(q)`'s output —
> `overlap(retrieve(q), sources(e)) ≥ θ` is a set operation over whatever chunks come back. A
> hybrid retriever would return a different-quality chunk set, and whether asymmetric containment
> separates better or worse over a tighter set is **untested here**. The FLAT freeze addresses
> determinism (§7) and says nothing about recall. No claim is made that the measured frontier
> transfers to a production retrieval stack.

---

## 2 · §10 matrix — one new row

Insert after **Krites [5]** and before **GroundedCache [6]**: it belongs with the threshold
generation, not the grounded one, but it is the **nearest neighbour to the lane band** of anything
in the table and the row should say so.

```markdown
| **Category-Aware SC** [13] | Response | **Per-category** similarity threshold, TTL and quota; category inferred from the query, motivated by embedding-space density | No — the category is a property of the *query*, not of the answer's grounding | Per-category TTL | **Load-responsive thresholds — projected, not measured** (9–17 % traffic reduction "in theoretical projections") | Hit rate by category (40–60 % high-repetition, 5–15 % volatile); break-even 15–20 % → 3–5 % | ✅ |
```

Reference entry:

```markdown
[13] C. Wang, X. Liu, Y. Zhu, A. Youssef, P. Nagpurkar, and H. Chen, "Category-Aware Semantic
Caching for Heterogeneous LLM Workloads," arXiv:2510.26835, Oct. 2025.
```

**Prose to add after "How to read the gap from the columns":**

> **The nearest neighbour to the lane partition is not a grounded cache.** Category-Aware Semantic
> Caching [13] diagnoses the same defect this work attributes to a single global τ — in its words,
> fixed thresholds "cause false positives in dense spaces and miss valid paraphrases in sparse
> spaces" — and responds with per-category thresholds, TTLs and quotas. The diagnosis is shared;
> the signal is not. Its category is inferred from the **query** and the local density of the
> embedding space, where the rule tested here reads the **provenance of the cached answer** and is
> explicitly forbidden from using the query text as a predictive signal (§5 C1). The two therefore
> occupy different signals while agreeing about what global τ gets wrong, and that agreement is
> worth citing as independent support for the premise rather than treated as a competing claim. Its
> one genuine overlap with the systems contribution — thresholds that respond to downstream model
> load — is reported as a *theoretical projection*, which is precisely the gap Phase 7 measures.
> Its architecture is also the cleanest published statement of the storage split this work declines
> (in-memory approximate search, documents external, 30 ms → 2 ms miss cost) and is cited to that
> effect in §7 and ADR-007.

---

## 3 · `CLAUDE.md` — one stale count

Under "What this project is", the sentence reads:

> …(two 2026 systems, GroundedCache and FinCacheServe, already gate reuse on retrieval context)…

§10 maps **four** prior response caches with a verified decision rule and, with the row above,
five. Suggested replacement:

> …(the 2026 grounded-cache line — GroundedCache and FinCacheServe — already gates reuse on
> retrieval context; see §10's matrix, which maps five prior systems)…

Minor and non-binding, but CLAUDE.md is read first every session, and a count that disagrees with
the matrix is the kind of drift that gets repeated into the write-up.
