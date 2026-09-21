# MVP for the advisor pitch — 4 days

**Created:** 2026-09-05 · **Target:** 2026-09-09 · **Goal:** get the topic approved.
**Status 2026-09-05:** Days 0–3 done (`a6f5cb3`). Day 4 items 1 and 2 done — `make demo-reset`, `make demo`, pinned query set, text backup. **Remaining: slides, one screen recording, UI.**

**What the advisor must walk away believing:** the problem is real, the contribution is
defensible against known prior art, the student can build it, and the scope is sane.

> ⚠️ **The hard rule: slides ship even if code slips.** Approval depends on the pitch, not the
> demo. If day 4 is compressed, cut the UI, never the slides.

> **Everything downstream is paused until the meeting.** The W8 gate (G1/G2/G3, `K`, μ_hit), the
> `v1` corpus build, the θ/τ sweep specification and the `docs/learning/` series are all
> **post-approval** work. A detailed build timeline gets rewritten only if the topic is approved —
> planning it now is planning a project that may not exist. Nothing in this file depends on the
> W8 banner.

---

## Day 0 — DONE 2026-09-05. Result below.

Ran retrieval + embedding directly (`rag.retrieve`, `rag.embedding`) on candidate demo pairs,
before building anything. `dev-v0`, `top_k=5`, τ=0.85 and θ=0.6 as demo values.

| Pair | sim | overlap | τ-only (0.85) | Rule (0.85, 0.6) |
| :--- | ---: | ---: | :--- | :--- |
| Paraphrase — "Is a 20-day return possible for this laptop?" | 0.965 | 1.00 | REUSE ✓ | REUSE ✓ |
| Unrelated — "How long does shipping take?" | 0.532 | 0.40 | refuse ✓ | refuse ✓ |
| laptop vs sofa | 0.848 | 0.40 | refuse | refuse |
| **headphones vs desk** | **0.851** | **0.40** | **REUSE — wrong** | **refuse — correct** |
| policy-word heavy, headphones vs desk | 0.865 | 0.60 | REUSE — wrong | **REUSE — also wrong** |

**Verdict: the trap works. Use the headphones-vs-desk pair for demo step 4.** It is the pair where
a fixed threshold reuses and gets the answer wrong, while the containment rule refuses — which is
exactly what `defense_demo.md` §4 requires of step 4.

**Overlap was never the problem.** It separates cleanly: 1.00 for a true paraphrase, 0.40 for a
cross-category lookalike. The Day-0 worry — that 44 chunks at `top_k=5` would make overlap high
everywhere — did **not** materialise. Retrieval ranks the right policy first in both directions
(electronics 0.776 for the laptop query, furniture 0.778 for the sofa query).

**Similarity is the problem, and it is a more interesting one.** Every query of the shape
*"can I return X after N days"* lands in **0.848–0.865 regardless of X** — laptop, sofa,
headphones, desk. The embedding barely distinguishes product category inside this template. Two
consequences:

1. **It supports the thesis premise.** Similarity is a weak discriminator in exactly the band where
   the reuse decision is hard. That is why C1 exists.
2. **It makes the demo margin fragile.** 0.851 against τ=0.85 is a **0.001** margin. If the advisor
   asks "what about τ = 0.86?", the demo collapses. Do not present τ=0.85 as a chosen value —
   present the swept frontier as the real result and τ as a demo setting.

**A false hit the rule does not catch, recorded deliberately.** The policy-word-heavy phrasing
gives overlap **0.60 = θ exactly**, so the rule reuses too, and is also wrong. This is a real
limitation inside the δ ≤ 5 % budget. Better to state it than to have the committee find it.

**Carried to W8 as evidence, not as a blocker:** the narrow similarity range is early evidence that
`v1` must be built for **frontier dynamic range**, not just for the G1/G2/G3 gate. If every query
family sits in a 0.02-wide similarity band, the τ sweep of config 3 has almost nothing to sweep,
and Headline B's comparison loses resolution. Raise this when scoping `v1` (ADR-024/ADR-028).

**Decision: do not extend the corpus before the pitch.** Four days is not enough to rebuild the
corpus and Tier 2 both, and the trap already works. Extending `dev-v0` is a W8 concern.

> **This is pair selection, not tuning.** `defense_demo.md` §4 explicitly directs picking the
> paraphrase and the trap in advance, and requires the trap be one a *tuned* fixed threshold gets
> wrong. That is a different activity from rule #10's prohibition: the **evaluation** sweeps the
> whole workload and reports a frontier; the **demo** shows one illustrative pair. Never let the
> demo pair's numbers appear as a result.

---

## Days 1–2 — Tier 2 — DONE 2026-09-05 (`a6f5cb3`)

Shipped in one ~3 h session: `embed/client.go`, `cache/tier2.go`, `ragclient/retrieve.go`,
`httpapi/cascade.go`, handler/main wiring. `make verify` exit 0 throughout. Full record and the
three decisions taken along the way are in `docs/worklog/W08.md`, entry *"Tier 2 + the containment
rule"* — **that entry is the record; this section is kept as the spec it was built against.**

Spec as written (all of it implemented):

This is the bulk. It does not exist at all today: the 2026-09-02 replan deleted the W7 row that
owned `embed/` and `reuse/`, and no later stage picked it up.

**`gateway/internal/embed/`**
- Ollama `/api/embed` client, `nomic-embed-text`, 768-dim (ADR-003).
- ⚠️ **The nomic prefix convention** — `search_query: ` for queries, `search_document: ` for
  documents. `rag/src/rag/embedding.py` already documents this as a silent-degradation risk. Get
  it wrong and similarity is quietly worse with no error.

**Redis vector index**
- `FT.CREATE idx:cache ON HASH PREFIX 1 t2:` with a 768-dim `FLAT` vector field, cosine.
- **FLAT, never HNSW** — frozen study-wide. Approximate retrieval makes `retrieve(q)`
  nondeterministic and injects overlap noise indistinguishable from C1's signal.

**Tier-2 record (`interfaces.md` §D) — `t2:{entry_id}`**
```
embedding, query_text, answer, source_chunk_ids,
t1_key,          # ⚠️ REQUIRED — Tier-1's hash is not computable from entry_id,
                 #    so without it a purge silently misses Tier 1
dataset_epoch,   # stub 0 until Phase 2
source_overlap
```

**Write-back** — on a MISS, write **both** tiers, sharing one `entry_id`.

**Lookup** — Tier-1 miss → embed query → KNN top-1 → if `sim ≥ τ` → `TIER2_HIT`.
Start with `τ = 0.85`. It is a demo value, not a frozen one; say so out loud.

**Done when:** a paraphrase of a cached question returns `TIER2_HIT` with a real `similarity`,
and an unrelated question returns `MISS`.

---

## Day 3 — The overlap rule, and the demo data — DONE 2026-09-05 (`a6f5cb3`)

`reuse/rule.go` (asymmetric containment, pure, zero non-stdlib imports) plus 7 table tests. The
four demo steps ran twice in a row without touching code — `defense_demo.md` §4's rehearsal gate.
Measured, all non-citable (`dev-v0`, demo θ/τ, `make dev`):

| Step | Result | sim | overlap | latency |
| :--- | :--- | ---: | ---: | ---: |
| 1. Fresh (headphones → electronics, 30-day) | `MISS` | — | — | 3.8 s |
| 2. Exact repeat | `TIER1_HIT` | — | — | 0 ms |
| 3. Paraphrase | `TIER2_HIT` | 0.935 | **0.800** | 40 ms |
| 4. **The trap** (desk → furniture, 14 d + 15 %) | **`MISS`** | 0.851 | 0.400 | 3.6 s |

⚠️ **SUPERSEDED 2026-09-05 by the pinned query set in Day 4 §1b — step 3's overlap is 1.00; say 1.00 on the day.** The original note read: *Step 3's overlap is 0.800, not the ≈1.0 this file predicted below. Say 0.8 on the day.* It
clears θ=0.6 comfortably and the argument is unchanged, but a number that contradicts the slide is
a question you do not want to spend the meeting on.

Spec as written:

**This is cheaper than it looks and it is the whole research claim.** The expensive half already
exists: `server.py` implements the `Retrieve` RPC, and `ragclient` already wraps it.

**`gateway/internal/reuse/`** — one function:
```
overlap(retrieve(q), sources(e)) = |retrieve(q) ∩ sources(e)| / |sources(e)|
```
Asymmetric containment, not Jaccard. Reads as: *is the evidence that produced the cached answer
still the evidence for this new question?*

**Wire the cascade:** Tier-2 candidate passes τ → call `Retrieve(q)` → intersect chunk IDs →
`overlap ≥ θ` → serve. Otherwise fall through to MISS. Start `θ = 0.6`.

**The response must show `similarity` and `source_overlap` together.** The fields already exist in
`httpapi/types.go` as `null`. Filling them is the demo.

> A quiet win worth knowing: with `top_k = 5` on both sides, `|A∩B|/|B|` takes only **6 discrete
> values** (0, 0.2, 0.4, 0.6, 0.8, 1.0). θ has no finer resolution than 0.2. Nobody has written
> this down yet, and it bounds the θ sweep.

**Then lock the demo script** — verify by running, not by hoping:
1. Fresh question → `MISS`, ~2.5 s, sources listed
2. Same question → `TIER1_HIT`, < 1 ms
3. Paraphrase → `TIER2_HIT`, similarity ≈ 0.9, overlap ≈ 1.0
4. **The trap** → similarity high, **overlap ≈ 0** → `MISS` → correct answer

Step 4 must be a pair a *tuned* fixed τ also gets wrong. If a fixed threshold refuses it too, the
step proves nothing.

---

## Day 4 — the only remaining day. Do these in order.

The code is done. What is left is everything that decides whether the code is *seen working*. The
order below is by risk removed per hour, not by how interesting the work is.

### 1. Make the demo resettable — DONE 2026-09-05

`make demo-reset` is implemented and verified by *running* it plus all four steps, twice in a row.
It restores `data/` from git, `FLUSHALL`s, re-ingests, then **asserts the state it claims**
(`t1:*`==0, `t2:*`==0, `corpus:*`>0) and exits non-zero if the cache is not actually cold.

Two hazards found while building it, both of which would have failed silently on the day:

1. **`FLUSHALL` drops `idx:cache` and `idx:corpus` along with the keys** (verified — RediSearch
   ties indexes to the keyspace). The gateway only calls `EnsureCacheIndex` at **startup**, so
   resetting under a live gateway leaves it writing `t2:*` records into an index that no longer
   exists: step 3 never reaches `TIER2_HIT` and **nothing reports an error**. The target now
   refuses to run while `:8080` is listening. **Order is: stop `dev` -> `demo-reset` -> `dev`.**
2. **`FLUSHALL` wipes every database on the server**, and this machine is shared with unrelated
   projects (CLAUDE.md). The target counts keys outside `corpus:|t1:|t2:|dep:|entry:` and refuses
   rather than destroying someone else's data.

`FT.DROPINDEX` is still never used — dropping the index while leaving the `t2:*` hashes is what
produces a warm cache that presents as cold.

### 1b. The demo query set — PINNED 2026-09-05

**The four questions had never been written down anywhere.** Reconstructing them from
`W08.md` and `slides.md` produced a pair whose similarity landed at **0.8186 — below tau**, so the
trap was refused by the *threshold* rather than by the rule, and step 4 proved nothing
(`defense_demo.md` §4: "if a fixed tau also refuses it, the step proves nothing"). Re-derived by
sweeping noun x template offline (no cache writes), then verified end-to-end through the gateway.

**Use these strings verbatim. Do not paraphrase them on the day.**

| Step | Question | Result | sim | overlap |
| :-- | :--- | :--- | ---: | ---: |
| 1 | `Am I entitled to a full refund on my headphones 30 days after delivery?` | `MISS` | — | — |
| 2 | *(identical to step 1)* | `TIER1_HIT` | — | — |
| 3 | `Is a full refund possible for my headphones 30 days after delivery?` | `TIER2_HIT` | **0.9750** | **1.00** |
| 4 | `Am I entitled to a full refund on my sofa 30 days after delivery?` | **`MISS`** | **0.8689** | **0.40** |

Strictly better than the pair recorded earlier on 2026-09-05 (sim 0.851 / overlap 0.800) on both
axes:

- **Step 4's margin over tau=0.85 is now 0.019, not 0.001.** It survives "what about tau = 0.86?".
  It still fails at tau = 0.87 — keep saying tau is a demo setting, not a frozen value.
- **Step 3's overlap is 1.00**, which removes the slide-vs-screen conflict Day 3 flagged. The
  "say 0.800 on the day" warning below is **superseded** — say 1.00.

Gateway log for step 4, the counterfactual stated outright:

```
cascade similarity=0.8689 overlap=0.40 reuse=false similarity_only=true entered_band=true
  retrieved=[policy-returns-furniture#chunk-0 policy-returns-electronics#chunk-0 policy-shipping#chunk-0 product-furniture-04#chunk-0 product-furniture-08#chunk-0]
  entry_sources=[policy-returns-electronics#chunk-0 policy-returns-furniture#chunk-0 policy-warranty#chunk-0 product-headphones-03#chunk-0 product-headphones-04#chunk-0]
```

**Two wrinkles to know before the advisor finds them.**

- **The sofa answer's tail is muddled.** It opens correctly ("No, you are not entitled to a full
  refund", 14 days + restocking fee) but then drags in `dev-v0`'s custom/made-to-order final-sale
  clause and half-contradicts itself. The demo-critical contrast — *yes* for headphones, *no* for
  sofa — is intact. This is a `dev-v0` corpus artifact, not a rule failure.
- **The sweep found many cross-category pairs the rule gets WRONG.** e.g. *monitor* vs *desk* at
  the same template: similarity 0.908, overlap **1.00** -> the rule reuses, and is wrong.
  Retrieval returns the identical five chunks for both, so the rule cannot separate what
  retrieval did not. Same class as Day 0's overlap-0.60 false hit, but larger than it looked:
  with 44 chunks at `top_k=5`, overlap is a weak discriminator too. It is direct evidence for the
  `v1` "frontier dynamic range" argument already carried to W8 below, and it belongs in the
  delta <= 5 % discussion. **Do not volunteer it as a demo step; do have the answer ready** — the
  honest framing is that the rule shifts the error, and the frontier quantifies by how much.

All numbers non-citable (`dev-v0`, demo theta/tau, `make dev`).

### 2. Capture the backup — TEXT BACKUP DONE 2026-09-05, screen recording still owed

**`make demo` now exists**, so the four steps are one command instead of four hand-typed `curl`s.
It refuses to run against a warm cache or a dead gateway, prints cache badge · latency ·
`similarity` · `source_overlap` per step, renders **both chunk-ID lists with the shared entries
ticked** and the overlap arithmetic spelled out, and ends with the three counters (requests, hit
rate, generations avoided). That is `defense_demo.md` §3's required sidebar in text form, which
also discharges the ladder's item-6 fallback (`curl | jq`) ahead of time.

θ and τ are read from `REUSE_THETA`/`REUSE_TAU` in the printed arithmetic, not hardcoded — so if
the advisor asks to change one live, the output cannot silently contradict the running gateway.

**Captured:** `.docs/work/mvp-advisor-demo/backup-run-2026-09-05.md` — a verbatim transcript of a
provably-cold run of all four steps plus the gateway cascade log lines, and the rehearsed answer
to *"what about τ = 0.86?"* (verified: still `entered_band=true`, still `reuse=false`; it does
**not** survive τ = 0.87).

**Still owed, and it needs a human:** an actual screen recording. Run
`make demo-reset` → `make dev` → `make demo` under a screen recorder, one take, `DEMO_PAUSE=2`
(the default) so each step is readable. Do it once before the meeting.

### 3. Slides

Content is settled in `slides.md`; what is missing is a rendered deck.

⚠️ **Resolve the number conflict first.** Slide 8 cites miss p50 **2506 ms** (n=20, W6); the demo
now runs **3.8 s**. If the screen shows one number while the slide shows another, that becomes the
question the meeting is about. Pick one: either drop the latency figures from slide 8 and let the
live run supply them, or keep them and label the provenance out loud ("n=20, W6 exit test, quieter
machine"). Do not present both silently.

Also carry slide 3's paraphrase overlap as **1.00** and slide 6's trap as **sim 0.8689 / overlap 0.40**, per Day 4 §1b — not the 0.800 / 0.851 figures Day 3 recorded.

### 4. Debug UI — only if 1–3 are done

One HTML file, no framework: question box, answer, colour-coded cache badge, latency, similarity,
`source_overlap`, and — for step 4 — **both chunk-ID lists side by side**, so the refusal is
visibly arithmetic. Plus three counters: requests, hit rate, **generations avoided**.

**Acceptable fallback:** a shell script wrapping `curl | jq` with the fields formatted. Ugly, but
it shows the same two numbers. Do not spend day 4 on CSS.

### Explicitly not on day 4

`make demo-reset` aside, nothing in the deferred list from W08 gets touched: not `PutBoth`, not the
Redis/HTTP plumbing tests, not the double-embed on the cascade band, not `reuse/doc.go`'s scope
contradiction, not F1, not the pressure sensor. None of them changes what the advisor sees.

---

## Descope ladder — cut from the bottom

| Priority | Item | Status | If cut |
| :-- | :--- | :--- | :--- |
| 0 | **A demo that starts cold** (`make demo-reset`) | ✅ done | Not cuttable — without it steps 1–4 do not exist. |
| 1 | **Slides** | ❌ TODO | Never cut. |
| 2 | Tier-2 works, `TIER2_HIT` visible | ✅ done | Without it there is no "two tiers" to show. |
| 3 | `similarity` displayed | ✅ done | — |
| 4 | Overlap rule + `source_overlap` | ✅ done | Without it the pitch is "I built a cache", not a thesis. |
| 5 | Recorded backup of the four steps | 🟡 text transcript captured; screen recording still owed | Cut only if the live run is already proven twice on the day. |
| 6 | Debug UI | ❌ TODO | Fallback **already built**: `make demo`. |
| 7 | Counters sidebar | 🟡 text form done in `make demo` | Explain the UI version verbally as planned work. |
| 8 | Invalidation demo (C2) | — | **Already cut** — Phase 2. Do not attempt. |

---

## Two run modes — settled 2026-09-05, do not re-litigate

`make dev` was blocking all MVP work: it gated on `kern.memorystatus_vm_pressure_level == 0`,
which is stuck at `1` on this machine. Four days of hitting that wall is exactly the pressure that
makes someone weaken a guard — the rule #10 hazard. Fixed by splitting the targets so each gate
matches what its mode actually requires:

| | `make dev` | `make measure` |
| :--- | :--- | :--- |
| Purpose | Demo, MVP, debugging | Anything whose number reaches the thesis |
| Memory gate | `memorystatus_level ≥ 25%` — enough to load the models without swapping | Full proposal §7 validity rule |
| `env-check` | not required | required |
| Close apps first | **no** | yes |
| Numbers | **NOT citable**, banner says so every run | citable |

The metric matters: the check first used `free+purgeable`, which read **0.4 GB** on a machine with
**60 % available** — macOS reclaims inactive pages, so free pages badly understate what can be
allocated. It would have failed constantly. `kern.memorystatus_level` is the signal that tracked
correctly all session (83 % → 66 % as the model loaded).

**The hazard was never the relaxed run.** Demo runs produce no citable number — every headline
figure is pre-computed and the load clip pre-recorded (`defense_demo.md` §4). The hazard is a
demo latency drifting onto a slide, which is why `dev` prints a non-citable banner on every run.

## Rules while building

- **Do not touch frozen values.** `top_k=5`, 768-dim, FLAT, `num_ctx=8192`, `q4_K_M`,
  `think:false`. τ and θ are demo values and are **swept** later, never hand-set for the record.
- **No ML on the hit path.** The rule is a set intersection, nothing more.
- **`make verify` green before each day ends.** It is honest now — it actually runs ruff and
  pytest since 2026-09-04.
- **Open a `/task`** for this work. The gate is FULL RIGOR from W8, and this pulls Phase 3's
  containment rule forward — record that in the worklog so the plan change is traceable.
- **Do not fix F1 or the pressure sensor this week.** Both block W8, not the pitch.

---

## What to ask the advisor for

1. **Approval of the narrowed claim** — is the post-ADR-026 contribution enough for a thesis?
2. **A second machine on the same LAN** for off-box load generation (W8 needs it; a cloud VM is
   wrong — WAN latency contaminates the measurement).
3. **Confirmation of the defence format** and date.
