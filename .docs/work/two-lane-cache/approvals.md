# Approvals — two-lane-cache

| Phase | State | Who / when |
| :--- | :--- | :--- |
| impact | **not produced** | — |
| contract | **not produced** | — |
| experiment | **not produced** | — |
| implementation | **granted verbally in session, 2026-09-06** | the author |

## ⚠️ The workflow was bypassed deliberately, and this file exists to say so

The author instructed, verbatim: *"đây là test nên k cần làm theo workflow approval. sửa code
thẳng luôn và verify xem approach này có ổn k"* — this is a test, skip the approval workflow,
edit the code directly and verify whether the approach holds.

`READY_TO_IMPLEMENT` was therefore written **without** `/approve implementation` running, and
without spec/impact/plan. The gate (`gate-check.sh`, FULL RIGOR from W8) is satisfied
mechanically but **not substantively**. Recording that here rather than letting the trail imply
a review that never happened.

## What this branch is, and is not

- **Is:** an experiment on branch `tier2-and-reuse-rule`, to find out whether namespace equality
  derived from retrieval grounding is a better reuse rule than asymmetric containment.
- **Is not:** mergeable. Two prerequisites are unmet and both need an ADR:
  1. `product_id` on `POST /ask` changes `interfaces.md` §A, **frozen at v0.5**.
  2. The `policy-` / `product-` doc-id prefix convention is enforced only in
     `rag/src/rag/ingest.py:record_kind()`. `interfaces.md` §C does not require it, so code
     that depends on it depends on an unfrozen convention.
- Any number produced here is **not citable**: `dev-v0`, demo thresholds, `make dev`.

## Deliberate rule changes made for the experiment

- **The cascade now falls through past a namespace-mismatched candidate.** `cascade.go`'s
  existing comment says falling through to candidate 2 "is a different rule with different
  false-hit behaviour and would need its own pre-registration." That is correct and it is being
  done anyway, here, on purpose: namespace filtering is meaningless if the search stops at a
  candidate the filter rejects. It must be pre-registered before any reported run.

## Third prerequisite: the MIXED lane (added 2026-09-06)

The two-lane rule was **unsound for stratum D** — a question whose grounding spans product and
policy (`data-card.md` §2). With only two lanes, `PolicyFraction ≥ σ` sent such a question to
`LanePolicy`, whose namespace is the rank-1 policy doc, **dropping the product entirely**. Two
mixed questions about *different* products then shared a namespace and one was served the other's
spec half — a false hit the two-lane rule *creates* and the containment rule does not have, since
containment scores the whole grounding set and so covers both document kinds without a lane.

`Classify` now takes a `LaneBand{Lo, Hi}` and emits a third lane:

| lane | rule |
| :--- | :--- |
| SPEC, POLICY | `sim ≥ τ ∧ namespace equality` — unchanged |
| **MIXED** | `sim ≥ τ ∧ entry is ALSO mixed ∧ containment ≥ θ` |

Lane equality is needed **on top of** containment because overlap divides by the *entry's* source
count: a policy-only entry fully contained in a mixed question's retrieval scores 1.0 and would be
reused, serving an answer that never mentions the product. Asymmetric containment is blind to
"the query asked for more than the entry was grounded in" by construction, and stratum D is where
that bites. MIXED entries carry `namespace = ""`, which `MatchNamespace` refuses on either side,
so the three lanes partition the cache into non-interacting regions and their false-hit rates stay
separately attributable.

### Status — pre-registration owed, and the lane ships OFF

- `LANE_SIGMA_HI` defaults to `LANE_SIGMA`, **collapsing the band**: the MIXED interval is empty
  and the rule is the original two-lane rule bit for bit. `TestCollapsedBandReproducesTheOriginal
  TwoLaneRule` pins that, so the pre-registered baseline stays reproducible.
- It ships off for three reasons: `dev-v0` **cannot calibrate the band** (policy questions there
  measured `policy_frac` 0.40–0.80 against only four policy chunks, so any `Hi > 0.8` reclassifies
  every policy question as MIXED); `data-card.md` §2 calls stratum D **"impossible in `dev-v0`"**
  pending ADR-024 requirement 1's product↔policy join key; and a rule that enables itself cannot
  be pre-registered.
- **Owed before any reported run:** an ADR covering the third lane and the `(Lo, Hi)` sweep,
  alongside the two prerequisites already listed above. This is the third.

### Changing the band invalidates the cache

`LANE_SIGMA_HI` is not a hot knob. Entries carry the `lane` and `namespace` they were partitioned
with **at write time**, so a run that changes the band over a warm cache mixes entries partitioned
under two different rules — and contains no `MIXED` entry at all, because that lane did not exist
when they were written. Every mixed question then misses until the cache re-warms, biasing the new
lane's hit rate downward for reasons that have nothing to do with the rule. Flush both tiers
(`make demo-reset`) on any band change, exactly as for a τ/θ change.

### Not yet measured

The MIXED lane's fixtures are **constructed, not observed**. `lane.go` cites measured
`policy_frac` for spec (0.00) and policy (0.40–0.80) on dev-v0 2026-09-06; there is **no measured
value for a mixed grounding**, and the unit tests assume 0.5. The claim in `cmd/gateway/main.go`
that "dev-v0 cannot calibrate the band" is therefore **reasoned, not measured** — it follows from
the four-policy-chunk saturation, but has not been checked against a real mixed question.

Owed: run ~6 mixed questions through `make ask` under green pressure and record `policy_frac`.
Two outcomes, both informative:
- lands inside 0.40–0.80 → indistinguishable from pure policy on this corpus; the shipped-off
  default is confirmed and the band waits for `v1`.
- lands in a clean band of its own → the `main.go` comment is **wrong** and must be rewritten.

## MEASURED 2026-09-06 — the containment fallback FAILS in the MIXED lane

Functional run, `make dev` (numbers not citable), dev-v0, cold cache, band `[0.20, 0.60)`,
τ=0.85, θ=0.60. 26 questions through `rag ask` for the lane distribution, then the cascade through
`POST /ask`.

### Lane separation — the "cannot calibrate" claim was WRONG

| label | min | max | mean | n |
| :--- | ---: | ---: | ---: | ---: |
| SPEC | 0.00 | 0.00 | 0.00 | 10 |
| MIXED | **0.00** | 0.40 | 0.23 | 6 |
| POLICY | 0.60 | 0.80 | 0.66 | 10 |

MIXED separates cleanly from POLICY (0.40 vs 0.60), so `cmd/gateway/main.go`'s claim that dev-v0
cannot calibrate the band is **false and must be rewritten**. The real boundary problem is at
**Lo**: 1 of 6 mixed questions ("how much does the SoundMax ANC Pro weigh and what is its warranty
period") retrieved **zero policy chunks**, classified SPEC, and so has no grounding for the
warranty half at all.

### The decisive result: no θ separates a legitimate hit from a false hit

Two requests against the same cached mixed entry (grounded in `policy-returns-electronics`):

| query | differing chunk | overlap | verdict | correct? |
| :--- | :--- | ---: | :--- | :--- |
| paraphrase, same return question | `hp-02` vs `hp-01` | **0.80** | TIER2_HIT | ✅ |
| same product, **warranty** instead of return | `policy-warranty` vs `policy-returns-electronics` | **0.80** | TIER2_HIT | ❌ **false hit** |

The second was served the 30-day return answer for a warranty question. Retrieval was **not** at
fault — it returned `policy-warranty` correctly. Containment is **dominated by the lane-irrelevant
half**: a mixed grounding is ~4 product chunks to ~1 policy chunk, so the one chunk carrying the
entire semantic difference is 0.20 of the denominator. Both cases score exactly 0.80, and at
top-5 the overlap granularity is 0.2, so the only θ that refuses the false hit (θ > 0.80) refuses
nearly every legitimate reuse too.

**This is the B-within trap (ADR-028) appearing inside the MIXED lane, and containment does not
solve it.** The lane-equality term works — it correctly refused a spec-only entry at sim 0.9244 /
overlap 0.80 where `overlap_decision=true`, i.e. the pre-existing containment rule alone would
have served a battery-life answer to a battery-life-plus-returns question. But lane equality is
too coarse to be the whole rule.

### Consequence: the MIXED arm needs the composite key after all

The composite `product|policy` key rejected in `Namespace`'s doc comment was rejected on the
reasoning that it over-specifies and causes false MISSES. The measured evidence says the
alternative causes false HITS, which is the worse direction against a δ ≤ 5 % budget. On the three
observed cases a composite key is right all three times where containment is right twice:

| case | rank-1 policy (query vs entry) | composite | containment |
| :--- | :--- | :--- | :--- |
| paraphrase | returns-electronics = returns-electronics | reuse ✅ | reuse ✅ |
| warranty | **warranty ≠ returns-electronics** | refuse ✅ | reuse ❌ |
| spec-only entry | (entry not mixed) | refuse ✅ | refuse ✅ (lane term) |

Proposed: in the MIXED lane require `sim ≥ τ ∧ entry is MIXED ∧ product-side match ∧ policy-side
rank-1 match`. Not yet implemented — this supersedes the fallback described above and needs its
own pre-registration.

### Also observed

`ns=product-headphones-04` was assigned to "what is the battery life of the EarBuds Pop 3" while
the answer came from `product-headphones-03` — the rank-1 instability `Namespace`'s comment
documents, live, because `make ask` sends no `product_id`. The SPEC lane's namespace named a
different product than the answer describes.

### CONFIRMED 2026-09-06 — the composite key closes the false hit

Same functional setup, cold cache, band `[0.20, 0.60)`. Entry seeded from *"battery life of the
EarBuds Pop 3 and how long do I have to return it"*, namespace
`product-headphones-04|policy-returns-electronics`.

| follow-up | similarity | overlap | containment would | composite rule | correct? |
| :--- | ---: | ---: | :--- | :--- | :--- |
| paraphrase, same return question | 0.9382 | 0.80 | reuse | **TIER2_HIT** (`rule=composite`) | ✅ |
| same product, **warranty** instead | 0.9578 | 0.80 | reuse | **MISS**, ns `…\|policy-warranty` | ✅ |

Both still score an identical containment of 0.80 and both still clear τ — the second even more
clearly than before at 0.9578 — so neither τ nor θ separates them. The rank-1 policy component
does. `overlap_decision=true` travels on both responses as the recorded counterfactual, so the run
carries its own evidence that the rule it replaced would have served the wrong answer.

The lane-equality term also still earns its place: the mixed question was refused against the
spec-only entry at similarity 0.9244 / overlap 0.80 where containment again said reuse.

Unchanged and still owed: the ADR, and the pre-registration of the third lane plus the `(Lo, Hi)`
sweep. The lane still ships **off** (`LANE_SIGMA_HI` defaults to `LANE_SIGMA`).

## Diverse-workload run 2026-09-06 (27 requests, functional, NOT citable)

Cold cache, band `[0.20, 0.60)`, τ=0.85, θ=0.60, `make ask` (**no `product_id`**). Ten seeds, then
17 probes labelled by construction against the `data-card.md` §2 strata. Three rules scored on the
same 17 responses — similarity-only is derived from the returned `similarity`, containment from
the `overlap_decision` counterfactual, and the lane rule from the actual outcome:

| rule | correct reuse | **false hit** | missed reuse | correct refuse |
| :--- | ---: | ---: | ---: | ---: |
| similarity-only (config 3, GPTCache's) | 5 | **7** | 2 | 3 |
| containment (C1 as it stands) | 5 | **6** | 2 | 4 |
| lane + composite | 4 | **4** | 3 | 6 |

Seventeen probes is far too few to report, and the labels are hand-assigned. What the run is good
for is **attribution**, and there every one of the lane rule's four false hits traces to something
other than the composite key:

| false hit | cause | fix |
| :--- | :--- | :--- |
| "EarBuds Pop 3 **Pro**" served the Pop 3 answer | **rank-1 instability** — the seed for the non-Pro took `product-headphones-04` (the *Pro*) as rank-1, so both landed in one namespace | `product_id` (see below) |
| sofa material + **shipping** served the sofa-returns answer | **retrieval** ranked `policy-returns-furniture` first for a shipping question; the composite key faithfully recorded what retrieval said | corpus / retrieval, not the rule |
| "how much **storage**" served the **RAM** answer | **SPEC lane by design** — its namespace is the product, so any two questions about one product above τ reuse | unchanged by this work; a known granularity limit |
| shipping **for furniture** served the general shipping answer | **label uncertainty** — `policy-shipping` is one doc for all categories, so this may be correct reuse mislabelled MISS | re-label on `v1` |

The **composite key itself produced no false hit**. In the mixed lane it was right on 6 of 7, and
twice it refused where containment reused: the B-cross pair `product-laptops-02|policy-warranty` vs
`product-laptops-01|policy-warranty` (similarity 0.9177, overlap 0.80) and the B-within warranty
pair (similarity 0.9578, overlap 0.80).

Two of the three missed reuses were **τ**, not the namespace: the stratum-C paraphrases scored
0.7042 and 0.7557 and never entered the band. That is τ=0.85 being a demo value, not a rule defect.

### `product_id` is now empirically motivated, not just argued

Rank-1 instability caused **one false hit and one false miss** in the same run. Re-seeded cold with
`product_id` on the request, both flip to correct:

| request | `product_id` | namespace | outcome | containment would |
| :--- | :--- | :--- | :--- | :--- |
| seed: battery life of the EarBuds Pop 3 | `product-headphones-03` | `product-headphones-03` | MISS | — |
| paraphrase: how long does the battery last | `product-headphones-03` | `product-headphones-03` | **TIER2_HIT** ✅ (was a missed reuse) | reuse |
| the **Pro** variant | `product-headphones-04` | `product-headphones-04` | **MISS** ✅ (was a false hit) | **reuse** |

The Pro case refuses at similarity 0.9685 where containment accepts. This strengthens the
prerequisite already listed above: `product_id` on `POST /ask` changes `interfaces.md` §A, frozen
at v0.5, and needs an ADR.

## Hit-path optimisations 2026-09-06 — done, and they did NOT move mu_hit

Three changes, all behaviour-preserving (the decisive sequence re-run cold reproduces identical
similarities 0.4237 / 0.9244 / 0.9382 / 0.9578, identical verdicts, identical namespaces):

1. **Namespace-scoped KNN replaces the Go-side fan-out.** `cache.NearestTier2InNamespace` issues
   a RediSearch hybrid query `(@namespace:{ns})=>[KNN 1 ...]`. The cascade is now two searches:
   unfiltered `k=1` to work the τ gate (the namespace is not known until after retrieval), then
   scoped `k=1`. `laneCandidateFanout = 10` is deleted. `reuse.DecideLane` still re-checks
   namespace equality on the result, so the filter stays an optimisation and the rule stays in
   `reuse/` (architecture.md §2).
2. **`hit_count` bump detached** from the response path (`go` + `context.WithoutCancel` + a 2 s
   bound). The `tier2.go` comment already called it fire-and-forget; the call site awaited it.
3. **Containment no longer computed inside `DecideLane`.** It ran per candidate across the fan-out
   and all but one result was discarded. The cascade now fills `NamespaceDecision.Overlap` once,
   for the served candidate. `LaneInput` lost its two chunk-list fields as a result.

### Measured: no mu_hit improvement, and that is the finding

| | TIER2_HIT `latency_ms` |
| :--- | :--- |
| before (sync bump, fan-out 10) | 30, 33, 35, 35, 35, 36, 37, 42 — median **35 ms** |
| after | 31, 37, 37, 37 — median **37 ms** |

Indistinguishable, and `t_search` median rose slightly (0.583 → 0.668 ms) because two round-trips
replaced one. The hit path is **dominated by the embed round-trip (~15 ms) and the Retrieve RPC
(~18 ms)**; a Redis RTT and a handful of map allocations are noise against that.

So these are **correctness and scaling** fixes, not latency fixes, and they should be recorded as
such:

- the fan-out horizon was a false-miss source that worsens as the cache fills and would have read
  as an eviction effect in a load test. It is gone. It was **not demonstrable at this corpus size**
  (three entries), so this is an argument from the code, not a measurement.
- the detached bump removes a *failure coupling*: a stalled Redis previously stalled the response.
- per-lookup work is now constant in cache size rather than deserialising `k` answers.

**Only the τ_high short-circuit will move mu_hit.** It removes the ~18 ms Retrieve from clear hits,
and it is the branch Pre-Thesis §3.2.3 Figure 3.2 specifies and this cascade does not yet have.
mu_hit recorded before it exists is mu_hit for a cascade where *every* hit pays retrieval — which
matters because ADR-027's S1 turns on that number.

### A1 measured — embed ∥ Retrieve: 35 ms → 27 ms

Functional run, cold cache, six distinct paraphrases hitting one mixed entry.

| | TIER2_HIT `latency_ms` |
| :--- | :--- |
| sequential | 30, 33, 35, 35, 35, 36, 37, 42 — median **35 ms** |
| concurrent | 26, 27, 27, 30, 35 — median **27 ms** |

~23 %, not the ~40 % predicted. The prediction assumed the hit path would become `max(15, 18)`;
in fact `t_overlap` **rose from ~18 ms to ~26 ms** because the Retrieve RPC now contends with the
embedding call for CPU on a single machine. `t_embed` is unchanged (~15 ms) and finishes first, so
the hit path is now bounded by Retrieve alone.

Consequence for the remaining work: **~27 ms is close to structural.** The only way below it is to
not retrieve on the hit path, which is τ_high — and the measured similarity distribution says
there is no safe τ_high window on this corpus. A8 removes the *second* retrieval on the miss path,
not this one.

⚠️ Correction to the plan's rationale: "costs nothing in RAG load" holds only **after A8**. Until
then a below-τ miss performs two retrievals (the speculative one plus `Answer`'s internal one)
where it previously performed one. ~18 ms of retrieval against a multi-second generation.

### A2 + A3 measured — coalescing and admission

**Coalescing** (`gateway/internal/coalesce`, hand-rolled; no new module, rules.md #9). Five
concurrent *identical* cold questions:

| | result |
| :--- | :--- |
| one cold generation, alone | 1.02 s |
| five concurrent identical | **all five returned at 820 ms**, wall 0.85 s |

Identical latencies and a wall time matching a single generation are the signature of one
execution shared five ways. Without it — and with ollama serving `-np 1` (env-check F1) — the five
would have serialised to ~5 s and burned five generations.

Keyed on `sha256(normalize(q)) + "\x00" + product_id`, **not** the Tier-1 key alone: two requests
with the same text but different `product_id` write entries under different namespaces
(`reuse.Namespace` reads it in the spec lane), so they are not the same work.

**Admission** (`gateway/internal/admission`). Coalescing wraps the permit, never the reverse — N
duplicates take one permit. With `permits=4` (from `OLLAMA_NUM_PARALLEL`, ADR-017) and
`GEN_QUEUE_BUDGET=0`, eight concurrent *distinct* questions gave exactly **4 × 200 and 4 × 503**,
and the shed response matches `interfaces.md` §A verbatim:

```
HTTP/1.1 503 Service Unavailable
Retry-After: 2
{"error":"busy","reason":"generation_pool_saturated","request_id":"06G7B562D896GBEDJVACQ40CEC"}
```

A cancelled waiter is deliberately **not** counted as a shed (it is the client leaving, not a
decision this gateway made); a double `Release` is a no-op rather than a silent capacity increase.

⚠️ Carried forward from `make env-check` finding **F1**: for qwen3.5, `OLLAMA_NUM_PARALLEL` has no
effect because ollama overrides it to `-np 1`. The pool therefore bounds the gateway to a
concurrency the model server does not offer, and surplus permits queue *inside* ollama where this
gateway cannot shed them. That ADR must be resolved before any shed rate is read as a property of
the gateway. The startup banner says so on every boot.

**Regression:** the decisive four reproduce exactly — 0.4237 / 0.9244 / 0.9382 / 0.9578, same
verdicts, same namespaces.

### A4–A7 done: capacity, Jaccard, evaluation log, τ_high

**A4 — bounded cache as an entry COUNT** (`gateway/internal/cache/capacity.go`). A Redis ZSET
`lru:entries` scored by last access; after each write-back the gateway trims to
`CACHE_CAPACITY`, deleting **both** `t1:` and `t2:` of each victim.

This deviates from `interfaces.md` §D's "logical DB with `allkeys-lru`" and needs its ADR. §D
cannot express what ADR-027 requires: capacity is `round(0.25 × K)` **entries** while
`allkeys-lru` evicts by **bytes**, and `maxmemory-policy` is server-global rather than per-DB, so
§D's two-region split is not achievable on one `redis-stack-server`. `make redis-check` had already
reasoned to this and refuses any `maxmemory`. Enforcing the count in the gateway keeps
`maxmemory-policy=noeviction` globally, so the dependency region is safe **by construction** — a
stronger guarantee than §D asked for — and `redis-check` stays green unmodified. Verified live:
`CACHE_CAPACITY=3` held the cache at exactly 3 entries across 6 requests, evicting twice.

**A5 — `reuse.Jaccard`**, pure function, **zero hit-path cost**. §H logs both
`retrieved_chunk_ids` and `entry_sources`, so the run-level figure Pre-Thesis §3.2.2/§3.2.3
requires is derived exactly, offline. Confirmed present in a real log record.

**A6 — per-request evaluation log** (`gateway/internal/telemetry`, `interfaces.md` §H). One JSONL
record per request on **every** exit path, emitted from a `defer` so a later `return` cannot skip
it. `O_EXCL`, never append: a reused `RUN_ID` refuses to start, which is the loud form of rules.md
#3's write-once. Graceful shutdown added to `main.go` solely so the buffer flushes — a hard exit
would silently shorten a run's own record of itself. Dropped records are counted and make the run
exit non-zero.

Three outcomes were added beyond §A's `cache` values so every request lands in exactly one bucket:
`SHED`, `ABANDONED`, `GENERATION_FAILED`. Two fields extend §H and need an ADR to promote:
`coalesced` (a coalesced request is a MISS by every frozen field, so generations avoided by
coalescing is not derivable) and `reuse_rule`. `stratum` arrives as an optional
`X-Thesis-Stratum` header rather than a body field, because §A is frozen at v0.5; absent, the
label joins offline on `query_normalized`, which ADR-028's Tier-1 collision invariant makes exact.

**A7 — τ_high, shipped disabled** (`REUSE_TAU_HIGH` defaults to `1.0`, pinned by a test). Two
measured reasons, both recorded above: no safe window exists on dev-v0, and since A1 made
retrieval concurrent a short-circuit **saves no latency anyway** — retrieval has already completed
by the time the gate is reached. What was an optimisation is now purely a rule variant, kept so
the frontier has the point. A short-circuit is logged as `reuse_rule=similarity_only` so a false
hit made that way is never charged to a provenance rule that did not run.

### Two integration bugs this work introduced, both caught by the repo's own guards

1. **`RESULTS_DIR` resolved against `gateway/`**, because `make dev` does `cd $(GATEWAY)`. The
   first smoke run wrote to `gateway/experiments/results/…`. Fixed by passing an absolute
   `RESULTS_DIR` from the `dev` target. The stray directory, and the three smoke-run directories
   under `experiments/results/`, were deleted on the author's instruction: all four were untracked
   artifacts of this session's shakedown, not runs. `experiments/results/` is back to `.gitkeep`.
   rules.md #3's write-once rule protects real run output, and none of these was one.
2. **`make demo-reset` began refusing every reset**, because A4's `lru:entries` key is not in its
   allowed-prefix guard and it read as a foreign key belonging to another project. The guard did
   exactly its job. `lru:` added to the allowed set.

### Regression, cold cache, verified

`0.4237 / 0.9244 / 0.9382 / 0.9578` — identical to the pre-optimisation baseline, same verdicts,
same namespaces, `MISS / MISS / TIER2_HIT / MISS`.

### Not done: A8 (one retrieval per request)

Stopped deliberately. `AnswerRequest` gaining pre-retrieved chunk IDs is not sufficient on its own:
`rag/src/rag/server.py` needs the chunk **text**, and `retrieve.retrieve()` obtains it through
LlamaIndex. Passing IDs therefore requires a new fetch-by-id path coupling to LlamaIndex's
internal Redis field (`_node_content`) — a new coupling, on a frozen seam, whose ADR is not
written. Design decided, blocker named, not started.

## ADRs — written 2026-09-06

The three prerequisites this file has carried since the branch opened are now recorded in
`docs/decisions.md`. Citing them here is what releases `frozen-guard.sh` for the edits they cover.

| ADR | Decision | Clears |
| :--- | :--- | :--- |
| **ADR-030** | Reuse rule v2 — `MIXED` lane, `(sigma_lo, sigma_hi)` band, composite namespace, `tau_high` knob | The lane rule itself, and the pre-registration owed for the third lane and the band sweep |
| **ADR-031** | Cache capacity is an entry count enforced by the gateway | The deviation from `interfaces.md` §D's `allkeys-lru` wording, and the frozen "two-region eviction policy" line |
| **ADR-032** | `interfaces.md` v0.6 — optional `product_id` on `POST /ask`; `policy-`/`product-` doc-id prefix promoted to an invariant | Prerequisites 1 and 2 from the top of this file |

**ADR-030 records the containment fallback as a rejected alternative**, with the measured pair that
killed it, rather than quietly replacing it — the reasoning that produced it was wrong in an
instructive way and the write-up needs it.

**ADR-031 carries the required `Invalidates:` line**: none, because `experiments/results/` holds no
run directories. Had any existed they would all be void — capacity governs hit rate directly, and a
byte-budgeted cache is not the same experiment as a count-bounded one.

### Still owed

- **`interfaces.md` itself is not yet edited to v0.6.** ADR-032 decides the change; the contract
  document still reads v0.5. The §A `product_id` row, the §C prefix invariant, §D's eviction
  paragraph and the "Frozen study-wide" line (which still names the two-region policy) all need the
  edit, plus the version bump in the header and the Versioning section.
- **`data-card.md` §7** gains a fourth gate check (every `doc_id` carries a kind prefix), per
  ADR-032's consequences.
- **§B / A8** — one retrieval per request — deliberately excluded from v0.6 and awaiting its own ADR
  once the mechanism for giving the RAG service chunk text is settled.

## A8 + k6 done 2026-09-06 — ADR-033, `interfaces.md` v0.7

**A8 — one retrieval per request.** `AnswerRequest` gains `retrieved_chunk_ids`; when non-empty the
RAG service skips its own retrieval and grounds generation on exactly those chunks.

The blocker recorded earlier — *"the service needs chunk text, so this couples to LlamaIndex's
internal `_node_content`"* — **was wrong.** `text` is a field `store.build_schema()` declares, so
`fetch_by_ids` reads a schema field, not a storage-layout detail. The earlier probe that suggested
otherwise had used a malformed key: corpus keys carry a **double** colon (`corpus::{chunk_id}`)
because LlamaIndex appends its own separator to the configured prefix — the same quirk
`cache/tier2.go` documents from the other side.

Three obligations, each closing a silent failure, are in the proto comment, `interfaces.md` §B and
ADR-033: return the ids you were given (provenance is C1's input and C2's key), preserve rank order
(the namespace comes from the rank-1 document of each kind), and drop a missing id rather than
substitute one (a fabricated chunk puts text in an answer no provenance accounts for).

Verified live: regression exact — `0.4237 / 0.9244 / 0.9382 / 0.9578`, same verdicts, same
namespaces, and the response's `sources` matches the ids the gateway had retrieved, which is the
observable form of obligation 1.

**k6 harness** — `experiments/k6/ask.js` + README, and `make load-smoke` for a co-hosted shakedown
that labels itself non-citable. Shakedown result: 40 requests, 0 errors, 0 sheds, 34 TIER1 / 6 MISS,
Zipf sampling working.

Four things the script is deliberate about:
- **A `503` is not a failure.** k6's default handling would report an error rate exactly where the
  gateway behaved as designed, and `experiment-protocol.md` §4 counts sheds separately.
- **Goodput excludes sheds**, or S2 is satisfiable at S1's expense by shedding everything.
- **Constant arrival rate, not closed-loop VUs.** A closed loop cannot overload the target, so it
  can never find the saturation point S1 is about.
- **Zipf selection**, because redundancy is the independent variable; uniform makes the cache look
  useless and a fixed cycle makes it look perfect.

### Documents now in force

| Doc | State |
| :--- | :--- |
| `docs/decisions.md` | ADR-030 … **ADR-033** |
| `docs/interfaces.md` | **v0.7** — §A `product_id`, §B pre-retrieved chunks, §C prefix invariant, §D gateway eviction, §H `entered_band` restated |
| `docs/data-card.md` | §7 gate is now **four** criteria (G4 = doc-id kind prefix) |
| `CLAUDE.md` | interfaces reference updated to v0.7 |

## W8 gate apparatus, 2026-09-06 — corpus gate + μ_hit probe

The gate's four criteria and the μ_hit probe were specification-only. Both are now executable, and
running them produced findings that change what `v1` has to be.

### `experiments/scripts/corpus_gate.py` — G1…G4, via `make gate-corpus`

Refuses to print a snapshot digest unless all four criteria pass, so a corpus cannot become
"frozen" by accident. `REPORT=<path>` also writes the statistics as JSON.

**Two stages, which resolves an apparent contradiction in `data-card.md` §7.** §7 says a failure
means *"do not proceed to ingestion"*, yet G1/G2 are defined over `retrieve(q)`, which needs an
ingested index. They split by what they need: **G3/G4 are structural** (corpus files and the
workload file only — `STRUCTURAL=1` runs them alone, the loop to run while authoring); **G1/G2 need
the frozen retrieval path**. Stage 1 failing aborts before stage 2, so a mis-slugged corpus is never
embedded. §7 now records the split.

**A cross-language hazard G3 introduced, and the pin that closes it.** G3 has to group queries the
way Tier 1 will, so it needs ADR-015's normalization in Python — a second implementation of a
function that already exists in Go, where the Go one is authoritative because it is the one that
runs on the hit path. A looser mirror lets the gate pass a corpus that collides in production; a
tighter one rejects a corpus Tier 1 would have handled. Both are silent. The two are now pinned to
shared golden vectors in `contracts/normalize/cases.json`, asserted from both languages
(`cache.TestNormalizeMatchesCrossLanguageContract` and `experiments/tests/test_corpus_gate.py`).
27 cases; a divergence fails one side or the other, which is the only way it would ever be noticed.

**Shakedown against `dev-v0` — 24 questions, 44 documents.** Not a gate result (`dev-v0` is not
gated, ADR-020), but a measurement worth recording:

| | Result |
| :--- | :--- |
| G3 / G4 | pass |
| **G1** | **0 pairs** with `sim ≥ 0.85 ∧ J ≤ 0.2` (needs ≥ 50) |
| **G2** | **0 B-within** |
| overlap across the 16 high-similarity pairs | mean **0.68**, var 0.077, lowest occupied bucket **0.2–0.3** |

*No pair at all* falls below the ceiling. This is **ADR-024 requirement 3 measured rather than
predicted**: 44 documents ingesting to 44 chunks gives every question a near-identical retrieval
set, so `dev-v0` cannot express the phenomenon C1 studies — a null C1 on it would say nothing about
the rule. It is the concrete target `v1` has to clear.

### `experiments/k6/mu_hit.js` — the probe that can change the report

ADR-027 makes S1's wording falsifiable: **≤ ~16 req/s and the crossover is reachable**, restoring
S1's empirical form and forcing revisions to `Final_Proposal.md` §3 and `experiment-protocol.md` §6.
The script evaluates that trigger itself and prints the verdict, so it cannot be read past.

**Two ceilings, because they are different numbers.** `interfaces.md` §F says the embedding
round-trip *"directly bounds μ_hit"*. A Tier-1 hit does not pay it; a Tier-2 hit does. Reporting the
Tier-1 figure as μ_hit would state a ceiling the tiered system never operates at, so `MODE` selects
which is measured and the summary names which one it produced.

**Co-hosted shakedown (NOT citable — ADR-012):**

| MODE | μ_hit | p95 | evidence of saturation |
| :--- | ---: | ---: | :--- |
| `tier1` | ~**8000** req/s | 2.7 ms | 44 dropped of 120 k |
| `tier2` | ~**61** req/s | — | 6783 dropped of 8000 offered |

61 req/s is ≈ 16 ms per hit at full concurrency, which matches the ~15 ms embed round-trip measured
in A1. **μ_hit is bounded by the embedding call**, exactly as §F predicted — the two measurements
corroborate from opposite directions.

**The verdict, with its caveat.** 61 > 16, so ADR-027's restated S1 stands and the finding remains
"generation-bound throughout the operating range" (`h* = 61/(0.19+61) = 0.997`, against a best
reachable `h ≈ 0.988`). But the margin is **3.8×, not the order of magnitude the phrase "far above
~16 req/s" implies**, and the recorded probe must confirm it off-box. The co-hosting bias runs in
the safe direction — k6 at 400 rps starves the very embedding server that is the bottleneck, so the
off-box figure should be *higher*, pushing `h*` further out of reach — but "should be" is not a
measurement.

**Four things the probe refuses to do**, each closing a silent failure:

1. Measure a cache it did not verify. `setup()` warms, then re-sends the text the scenario will
   drive and asserts it answers from cache. A gateway whose write-back silently fails returns
   plausible 200s and a μ_hit that is really μ_gen.
2. Call an un-saturated run a ceiling. Nothing dropped and nothing shed ⇒ reported as a **lower
   bound**. This fired twice in practice before the rate was high enough.
3. Tolerate a mid-run MISS (`unexpected_miss` has a `count==0` threshold).
4. Let a `tier2` probe silently become a `tier1` one. A paraphrase below τ misses, generates, and is
   written into Tier 1 under its own key; every later request then answers `TIER1_HIT` under a
   Tier-2 label — and the contamination **persists across runs**. This is not hypothetical: the
   first fallback paraphrase set contained *"how long does the EarBuds Pop 3 battery last"*, which
   measures **0.84** against its question — below τ. It contaminated the cache on its first run and
   the guard caught it on the second. Every paraphrase in the fallback set was then measured and
   sits at 0.92–0.98.

### Also landed

- `make test` now runs `experiments/tests` (48 tests) alongside `rag/tests`.
- `rag.retrieve.make_retriever()` — binds the index once for callers issuing hundreds of queries;
  the retrieval path itself is unchanged, so the gate measures what production does.
- The co-hosted load runs drove macOS memory pressure from green to **urgent (2)** on their own,
  which is ADR-012 demonstrating its own reason for existing.

### Still owed for the W8 gate — and why

| Item | Status |
| :--- | :--- |
| `v1` frozen + hashed | **Blocked on the corpus, not on tooling.** The gate runs; there is nothing to run it against |
| `K` + derived capacity in `data-card.md` §7 | Emitted by the gate; needs the frozen workload |
| μ_hit recorded | Probe works and gives a verdict; the **recorded** number needs a second machine |
| k6 off-box | Harness ready; needs a second machine (ADR-012) |

## ⚠️ BYPASS 2026-09-09 — Tier-1 key scoped by `product_id`, workflow skipped again

The author instructed, verbatim: *"spawn opus để make plan rồi bypass implement thẳng luon, có
bug gì thì sau này sửa lại, đang cần gấp cho demo MVP"* — spawn an agent to plan it, then bypass
the workflow and implement directly; fix any bugs later; this is urgent for the MVP demo. Same
pattern as the top of this file: implemented, verified (`make test`, `make lint` both green),
recorded here honestly rather than letting the trail imply a review that never happened.

**What changed.** `gateway/internal/cache/key.go`'s `Key` now takes `(normalized, productID
string)` and hashes `normalized + "\x00" + productID`. `""` is its own partition, never a
wildcard. Threaded through `Store.Get`/`Store.Put`, `handler.go` (one hoisted `t1Key`, replacing
four independent re-derivations of the same formula — the eval-log record, the Tier-1 lookup,
the coalescing key, and `Tier2Entry.T1Key`), `telemetry.Record.ProductID` (new field, needed
because the offline stratum join on `query_normalized` was exact only under the one-stratum-
per-normalised-form guarantee this bypass relaxes), and `experiments/scripts/corpus_gate.py`'s
G3 (partition key is now `(normalize(q), product_id)`, not `normalize(q)` alone).

**Why:** two literally identical questions asked about two different products previously hashed
to the SAME Tier-1 key and would collide silently — Tier 1 runs no reuse rule, so the second
question is served the first one's answer permanently, from the first write, with nothing in
the system able to detect it (see [[10-theory-of-the-two-tiers]] §2, the `~ ⊆ ≈` correctness
condition). G3 already proved this cannot happen **within the frozen evaluation corpus** — but
only there; a real user typing an under-specified question on a product page was unprotected.

**⚠️ This directly reverses a recorded, reasoned decision — not an unstated assumption.**
`docs/decisions.md` ADR-028 explicitly considered and **rejected** "Add `product_id` to the
request and the Tier-1 key," on a thesis-validity ground: *"it moves the work C1 does into the
cache key and forces C1's claim to be restated as 'provenance beats similarity given product
scoping' — materially weaker."* ADR-028's prescribed alternative was to keep workload queries
self-contained (name the product/category in the query text) and let G3 catch violations.

**Why this bypass is narrower than what ADR-028 rejected, and why it's owed an ADR rather than
assumed safe.** The conversation preceding this change worked through the distinction: Tier 1 is
literal-text hashing only. Stratum B (both B-cross and B-within) is defined at **paraphrase**
similarity — different wording, evaluated at Tier 2 via embedding — and by construction never
reaches Tier 1's exact-match path regardless of what's in the Tier-1 key. So this change touches
only the narrow case ADR-028 didn't actually evaluate: literal (not paraphrased) text duplicates
across products. It should NOT move any measured B-within/B-cross/C1 number. But this is
reasoning stated here, in a bypass commit, not a superseding ADR with its own falsification
condition — which is exactly the process ADR-028 asked for and this session skipped.

**Owed before this is citable, mergeable, or safe to build on:**
1. A superseding ADR in `docs/decisions.md`, citing ADR-028 and recording the counter-argument
   above (Tier-1's literal-match scope is disjoint from Tier-2's paraphrase-level B stratum).
2. `interfaces.md` §D still reads the old formula (`t1:{sha256(normalized_query)}`) —
   `frozen-guard.sh` correctly refuses to let this session edit it without the ADR above.
3. `/approve contract` (touches an `interfaces.md` §D surface) and `/approve experiment` (G3
   changed what the corpus gate admits), alongside `/approve implementation`.
4. No test exercises the collision end-to-end through `httpapi` (no test files exist in that
   package at all) — `cache.TestKeyIsScopedByProductID` covers the unit, not the handler wiring.

**Invalidates:** no runs — `experiments/results/` holds no run directories (verified).
**Cache:** any pre-existing `t1:*` Redis key is now permanently unreadable under the new
formula (silent, not an error — it just never matches again). Run `make demo-reset` before the
next `make dev`/demo session.

**Regression:** `go build ./...`, `go test ./...` (all packages, including 4 new `cache` tests),
`python3 -m pytest experiments/tests` (50/50, including 2 new G3 tests), and `make lint` all
green. No golden values in `TestKey`/`TestKeyIsStableAcrossTrivialSpellingVariants` were
weakened — both were mechanically updated for the new signature and still assert everything they
asserted before.

## Retrieval scoping 2026-09-10 — ADR-034, `interfaces.md` v0.8

**What changed.** `RetrieveRequest`/`AnswerRequest` gain an optional `product_id`. When set,
`rag/src/rag/retrieve.py:retrieve()` restricts the corpus search's candidate set to
`doc_id == product_id OR kind == "policy"` before ranking, then applies the existing `top_k`
unchanged — empty/absent `product_id` is bit-for-bit today's behaviour. Threaded through
`gateway/internal/ragclient/{retrieve,answer}.go` and both call sites in `handler.go` —
`req.ProductID` was already in scope at both, no restructuring needed.

**Why.** Found live 2026-09-09/10: a generic, product-agnostic question ("what is the power rating
of this item exactly right now") retrieved the identical five chunks from unrelated
`product-kitchen-*` documents for three different products in a row (a laptop, headphones, a
furniture item) — retrieval has zero product context, and `dev-v0` is one chunk per document
across 44 docs, so a literal-word match in an unrelated category can beat the actual asked-about
product outright. Naming the product in the query text fixed it, confirming the defect sits in
retrieval's candidate set, not generation.

**This does not reopen ADR-028 or ADR-032's "§B is not part of this version."** ADR-028 rejected
`product_id` as a *cache/reuse-decision key*; this change makes no cross-query comparison and
touches no reuse decision — `reuse/lane.go`, `reuse/rule.go`, the cache-key functions, and
namespace/lane classification are all untouched, still deriving their partition from
post-retrieval evidence. ADR-032's §B deferral was for a different, since-resolved feature
(ADR-033). Full rationale in `docs/decisions.md` ADR-034 — done properly this time: ADR first,
`interfaces.md` bumped to v0.8, both languages, new tests, no bypass.

**Regression:** `gofmt -l .` clean, `go vet ./...` clean, `go build ./...` clean, `go test ./...`
green across every package (2 new `ragclient` tests: `TestRetrievePassesProductID`,
`TestRetrieveEmptyProductIDIsZeroValue`, `TestAnswerPassesProductID`,
`TestAnswerEmptyProductIDIsZeroValue`). `ruff check src/` clean. `pytest tests/` in `rag/`:
9/9 green (4 new: 2 pure `_scope_filters` tests, 2 live-guarded — including the bug-shape
regression, which reproduces and closes the exact failure live: `product-laptops-02` scoped
correctly excludes every `product-kitchen-*` chunk, and the same query truly unscoped still
returns one, proving the test exercises the real precondition). `experiments/tests/`: 50/50 green,
unchanged (`make_retriever`/`corpus_gate.py` deliberately untouched). `reuse/lane_test.go`'s pinned
golden value (`0.9382`, one of this branch's four decisive similarities) passes unchanged — this
fix never touches `reuse/lane.go` or `reuse/rule.go`, so the decisive sequence is untouched by
construction, not just by observation.

**Live manual verification** (`make dev`, fresh queries to avoid stale pre-fix Tier-1 entries):
cross-product contamination closed for all three tested products (`product-laptops-02`,
`product-headphones-02`, `product-furniture-03`) — each MISS now retrieves its own product's
chunk plus policy chunks, never a `product-kitchen-*` chunk. Naming the product in the query text
(no `product_id` sent) still resolves correctly, unaffected. No `product_id` sent, generic
phrasing → reproduces the old unscoped (kitchen-contaminated) result exactly, confirming backward
compatibility for callers that supply no context. One unrelated observation, out of scope for this
fix: a near-duplicate generic phrasing across two different products can still trigger a Tier-2
`TIER2_HIT` via namespace/similarity matching on the *cache* layer — a pre-existing
`reuse/`-package behavior this fix does not touch (constraint: never modify the reuse decision),
noted here rather than chased down tonight.

### Documents now in force

| Doc | State |
| :--- | :--- |
| `docs/decisions.md` | ADR-030 … **ADR-034** |
| `docs/interfaces.md` | **v0.8** — §B `RetrieveRequest`/`AnswerRequest` gain `product_id` |
| `contracts/rag/v1/rag.proto` | `product_id` added to `RetrieveRequest` (field 3) and `AnswerRequest` (field 5) |

### Same-night hotfix — ADR-034's first implementation regressed, caught by manual testing

**Found:** running a broader battery of live curl checks past the initial regression suite
surfaced a real cross-product false hit that the initial `doc_id == product_id OR kind ==
"policy"` pre-filter design did not anticipate. On `dev-v0` (four policy docs, one chunk per
product) that eligibility pool has only five members at `top_k = 5`, so nearly every candidate
came back regardless of relevance — `PolicyFraction` (`reuse/lane.go`) saturated toward ~0.8 for
almost any product-scoped question, misclassifying plain `SPEC` questions as `POLICY` and
collapsing unrelated products into the same policy-dominated namespace (`policy-warranty` or
whichever policy doc ranked first). Verified live: `product-kitchen-05` (Air Fryer XL, a genuine
`"power": "1800W"` spec) was served `product-laptops-02`'s cached "no power information" answer —
worse than the bug ADR-034 originally closed, because it needs no wording repeat, only two
similarly-generic questions on two different products.

**Fixed:** `retrieve()` now runs the normal unscoped `top_k` search first (ranking untouched),
then **post-filters**: drops any chunk belonging to a different product, and splices in exactly
the one chunk `product_id` itself owns only if it did not naturally rank. Policy content still
reaches the result whenever it genuinely ranks (the `MIXED` lane's reason to exist, ADR-030, is
unaffected), but can no longer be forced in by construction of a too-small eligible pool.
`docs/decisions.md` ADR-034 and `docs/interfaces.md` §B amended in place (same night, not yet
citable by any run, no new ADR number) rather than left to drift from what actually ships.

**Regression, post-hotfix:** `rag/tests/test_retrieve_scoping.py` — 5/5 green, including a new
test pinning the regression itself
(`test_scoping_does_not_flood_policy_chunks_for_a_plain_spec_question`). `pytest tests/`: 10/10.
`experiments/tests/`: 50/50, unchanged.

**Live re-verification, broader battery** (`make dev`, cache tiers flushed, fresh queries):
- The original 4-product cross-contamination probe, re-run: `product-laptops-02`,
  `product-headphones-02`, `product-furniture-03` all correctly `lane=SPEC`,
  `ns=<their own product_id>`, sources = own chunk only. **`product-kitchen-05` now correctly
  answers "1800W"** instead of being served another product's "no info" answer.
- Legit same-product paraphrase reuse (`product-kitchen-05`, below-tau on wording, correct fresh
  MISS + correct answer) — unaffected.
- Genuine policy-flavored question (return window) on `product-headphones-02`: correctly
  `lane=POLICY`, `ns=policy-returns-electronics`, answer "14 days".
- Same policy question, different product, **same real policy** (`product-headphones-05`):
  correctly `TIER2_HIT` reusing the `product-headphones-02` answer — legitimate reuse, not a
  false hit, since both products genuinely share the electronics return window.
- Same-shaped question on `product-furniture-03` (different category, different real return
  window): correctly its own `MISS`, own `ns=policy-returns-furniture`, not confused with the
  headphones entry despite near-identical wording.
- MIXED-shaped question (spec + policy in one, `product-laptops-05`): both halves answered
  correctly (16GB RAM, 30-day return), sources clean, no forced-in policy beyond what's relevant.
- Condition-flip trap on the same product (`product-laptops-05`, "warranty period" vs. "return
  period"): correctly two different real policy documents, two different namespaces
  (`policy-warranty` vs. `policy-returns-electronics`), two different correct answers — not the
  same-chunk-opposite-condition residual case (RS §3.2/slide 10 row 3), since these are genuinely
  different source documents, not one document read two ways.
- **Minor edge case, not fixed tonight:** a `product_id` that matches nothing in the corpus (typo
  or stale id) degrades to an ungrounded `MISS` ("I don't know") rather than erroring, but the
  response's `namespace` still echoes the bogus id even though nothing was actually grounded to
  it. Not a false-hit risk (there is no content to serve wrong), and not reachable through the
  real UI (`product_id` comes from the page route, never free text) — noted, not chased down.

## Same-night find — Tier-2 hits never promoted into Tier 1

**Found:** user observation, verified against `handler.go` directly. The `TIER2_HIT` branch
(`handler.go`, `if t2.NSDecision.Reuse`) calls `BumpHitCount` and `touch`, but never
`Cache.Put` — only the `MISS`/generation branch writes Tier 1. Consequence: a repeat of the
*exact same paraphrase text* (same product) keeps paying Tier-2's cost (embed + scoped search)
on every occurrence after the first, instead of collapsing to Tier-1's hash lookup the way a
byte-identical repeat of the *original* wording already does. Not a correctness bug — the answer
served is still whatever Tier-2 already validated — but a real, unforced gap against this
project's own load-conversion premise: repeated traffic should get cheaper to serve, not stay at
the same cost forever.

**Fixed:** the `TIER2_HIT` branch now also fires a detached, fire-and-forget `Cache.Put` (same
pattern as the existing `BumpHitCount` goroutine — must never add a Redis round-trip to the hit
path), writing the current query's exact text + `product_id` into Tier 1, pointing at the
*existing* `entry_id` rather than minting a new one.

**⚠️ Known limitation, documented in-code (`handler.go`), not fixed tonight:** the Tier-2
record's `t1_key` field is singular (`interfaces.md` §D; `capacity.go`'s eviction reads exactly
one field) and was written for the entry's *original* Tier-1 key at MISS time. Each promoted key
from a different paraphrase is a second (third, fourth, …) untracked Tier-1 pointer at the same
`entry_id`. Harmless today: `cache_capacity` defaults **unbounded** (`TrimToCapacity` never
evicts anything in the current functional config), and C2/invalidation is **0% built**
(`Recommended_system.md` §2) — so nothing exists yet that would try to clean these up and miss
them. This becomes a real orphan/staleness risk the moment either capacity is bounded (ADR-027)
or C2 ships, and needs its own decision then: track multiple `t1_key`s per entry, or decide
promoted keys should not survive an eviction/purge cycle. Flagged here so it isn't rediscovered
as a surprise later.

**Regression:** `gofmt -l .`, `go vet ./...`, `go build ./...`, `go test ./...` — all green, no
existing test touched. `pytest rag/tests/ experiments/tests/`: 60/60, unchanged (this is a
Go-only change).

**Live verification:** fresh MISS (`product-kitchen-05`, "what is the wattage of this air
fryer") → paraphrase → correctly `TIER2_HIT`, 42 ms → **the exact same paraphrase asked again**
→ now correctly `TIER1_HIT`, 0 ms (previously would have repeated the 42 ms `TIER2_HIT` path
indefinitely).
