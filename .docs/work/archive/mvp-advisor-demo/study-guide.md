# Study guide + manual demo run

**Purpose.** Two things that don't belong in `slides.md` (what to present) or `plan.md` (what shipped):
(1) a reading workflow to actually understand this project from proof, not from memorised talking
points — written for a backend-only background with no prior RAG/LLM/vector-db exposure; (2) the
exact manual steps to run the demo end to end, for rehearsal or for showing the advisor without
`make demo`'s wrapper hiding what's happening.

**Authority.** This file explains *how to read* and *how to run* — it invents nothing. Every command
below is an existing `make` target (`rules.md`: use the Makefile, don't invent ad-hoc invocations);
every number is copied from `backup-run-2026-09-05.md`, `docs/worklog/W08.md`, or `slides.md`, never
recalled.

---

## Part A — Reading workflow

### The method: read → open the code → answer the Self-check cold

Every `docs/learning/NN-*.md` file ends with **→ In this thesis** links (real files/ADRs) and a
**Self-check** section. For each file: read it, open the code it links to side by side, then answer
the Self-check **without reopening the doc**. That's the actual bar — "B — Bảo vệ" in
`docs/learning/README.md` §0 — not just recognising the words on a second read.

### Phase 0 — Orientation (~45 min, no code)

`README.md` (repo root) → `docs/Final_Proposal.md` §1–§2 → `CLAUDE.md`.

Goal: name the three contributions and the 60/25/15 weighting. Nothing deeper yet — this is the map.

### Phase 1 — Foundations (~2–3 h) — do this before anything else

```
docs/learning/00-llm-basics.md
docs/learning/02-embeddings.md
docs/learning/03-rag-pipeline.md
```

**Proof step — do not skip:**

```bash
make ingest
rag ask "What is the return window on the headphones?"
redis-cli KEYS 'corpus:*' | head -5
redis-cli HGETALL corpus:<one key from above>
```

See one real chunk and one real 768-number vector before reading the math in Phase 3. Abstract
concepts that were never seen once tend to evaporate in a week.

### Phase 2 — Architecture skeleton (~2 h)

Read: `Final_Proposal.md` §6 (diagram) → `docs/design/architecture.md`.

**Proof step:** open `gateway/cmd/gateway/main.go` (the wiring), then
`gateway/internal/httpapi/handler.go`'s `Ask` function — read top to bottom **once**, just to see the
shape: Tier 1 → Tier 2 → permit → generate → write-back. Return to it in Phase 3–4 for depth.

### Phase 3 — The research core: two tiers ⭐ (~4–5 h, the deepest phase)

```
docs/learning/10-theory-of-the-two-tiers.md   (all four traces, Parts I–IV)
docs/learning/11-tier2-two-signals.md         (⭐ + §12, the three-lane rule)
```

**Proof step, section by section:**
- Part I (Tier 1) ↔ `gateway/internal/cache/normalize.go` — hand-compute a hash, check it matches.
- Part II (Tier 2 math) ↔ `gateway/internal/cache/tier2.go` (`nearest`) + `gateway/internal/reuse/rule.go`.
- §12 (lane rule) ↔ `gateway/internal/reuse/lane.go`.
- Run the tests and read the output as a second copy of the worked examples:
  ```bash
  cd gateway && go test ./internal/reuse/... -v
  ```

Cross-check against `docs/interfaces.md` §D (the wire schema) to see the math land on real bytes.

### Phase 4 — Systems layer, 60% of the weighting (~3–4 h)

```
docs/learning/21-admission-control.md
docs/learning/13-invalidation.md
docs/learning/22-load-conversion.md
```

**Proof step:**
- `gateway/internal/admission/pool.go` + `gateway/internal/coalesce/` — run with the race detector:
  ```bash
  cd gateway && go test ./internal/admission/... ./internal/coalesce/... -race -v
  ```
  This is the part a backend background makes fastest to absorb — it's ordinary concurrent-Go
  correctness, no ML content at all.
- Open `gateway/internal/deps/doc.go` — it's a 6-line stub. **C2 (invalidation) is a documented
  design, not yet running code.** Don't let a fluent read of `13-invalidation.md` create the
  impression the mechanism exists in the gateway today.
- `gateway/internal/cache/capacity.go` — the gateway-enforced count-based LRU (ADR-031).

### Phase 5 — Measurement discipline (~2 h, skimmable if short on time before a demo)

```
docs/learning/32-how-we-measure.md
docs/experiment-protocol.md  §4, §6
docs/data-card.md  §7
```

**Proof step:**
```bash
make gate-corpus
```
Read the output next to `experiments/scripts/corpus_gate.py`.

### Phase 6 — Positioning, and closing the loop (~1–2 h)

```
docs/learning/40-positioning.md
docs/decisions.md → ADR-026 specifically
.docs/work/mvp-advisor-demo/slides.md
.docs/work/mvp-advisor-demo/script.md
```

Read `slides.md`/`script.md` again **after** Phases 1–5, not before — the second read is
comprehension, not memorisation.

### Suggested pacing (~15 h/week budget)

| Week | Phase | Hours |
| :--- | :--- | ---: |
| 1 | 0 + 1 | ~4 |
| 2 | 2 + 3 | ~5–6 |
| 3 | 4 | ~4 |
| 4 | 5 + 6 | ~3–4 |

Don't force 100% comprehension of a phase before moving on — write down what didn't land in Phase 3
(likely Part II §D–E's set theory), keep moving, and return to it after Phase 4 shows the same rule
running as real code. Understanding a system is a loop, not a line — exactly like debugging a
backend service by running it first and reading source second.

### Why this transfers beyond the thesis

Three pieces here are general backend patterns, not RAG-specific, and worth reading with a
"learning a trade" mindset if the goal is building chatbot/QA platforms later:
- **Admission control + backpressure** (Phase 4) — needed by any service fronting an expensive
  downstream call, not only an LLM.
- **Provenance-keyed cache invalidation** (Phase 3–4) — applies to any answer cache backed by
  sources that change, independent of e-commerce.
- **Request coalescing** (Phase 4) — a classical pattern for any backend with duplicate concurrent
  traffic, unrelated to AI.

### Reading `docs/learning/Pre-Thesis_Report_Full.md` itself

Every phase above routes through the `docs/learning/NN-*.md` teaching files, never straight at the
report. That's deliberate: `docs/learning/README.md` §6 says outright that those eight files were
written to cover exactly the parts of the report **the demo can't prove live**, so they carry the
pedagogy the report doesn't bother with. But the report is still the primary source — it has the
literature grounding, the full falsification table, and the exact wording an advisor question may be
quoting back at you. Read it once, chapter by chapter, slotted into the phases above rather than as
a bolted-on seventh phase:

| Report section | Read alongside | Why there |
| :--- | :--- | :--- |
| Ch.1 Introduction (§1.1–§1.6) | Phase 0 | Same map as `Final_Proposal.md` §1–§2, fuller prose — the three RQs and the scope cuts (§1.5) |
| Ch.2 §2.1–§2.5 Literature Review | Phase 6, before `40-positioning.md` | The prior-art detail behind ADR-026; §2.3 "Grounded Reuse: Concurrent Work" is the two 2026 systems that forced the novelty retraction |
| Ch.2 §2.6 Research Gap and Positioning | Phase 6, with `40-positioning.md` | §2.6.3/§2.6.4 are the retraction written out in full — source for Self-check Q28/Q30 below |
| Ch.3 §3.2 Provenance-Aware Semantic Caching | Phase 3, with `11-tier2-two-signals.md` | §3.2.4 "Namespace Lanes" is the `product_id`-as-namespace argument behind Self-check Q14 |
| Ch.3 §3.3 Source-Aware Cache Invalidation | Phase 4, with `13-invalidation.md` | The dependency-map design as originally written — cross-check against the `deps/doc.go` stub gap noted in Phase 4 above |
| Ch.3 §3.4 Admission Control | Phase 4, with `21-admission-control.md` | Shorter than the learning doc; read for the report's own phrasing, not new content |
| Ch.3 §3.6 Corpus Design | Phase 5, with `data-card.md` §7 | §3.6.3 "The Sensitivity Gate" is the G1/G2/G3 gate story before ADR-028 split stratum B |
| Ch.4 §4.1–§4.3 Research Design & Environment | Phase 5 | §4.3.1 is the fullest write-up anywhere of the memory-envelope spike — the ADR-017/021 story in prose |
| Ch.4 §4.4 Evaluation Metrics | Phase 5 | Tables 4.3/4.4 pair every metric with the claim it settles — what `32-how-we-measure.md` compresses |
| Ch.4 §4.5 Threats to Validity | Phase 6, before Part C's Self-test | Table 4.5 (controlled) + §4.5.2 (carried as limitations, numbered 1–9) — this **is** the "known weaknesses" list; `docs/learning/README.md` §5's table is a curated subset of it |
| Ch.4 §4.6 Expected Outcomes | Phase 6, with the whiteboard check | Table 4.6 — the pre-registered falsification criteria; source for Self-check Q3, Q10, and the four whiteboard formulas, verbatim |
| Ch.5 Project Plan | Phase 6 | §5.1's phase table predates the 2026-09-02 replan — `docs/time_line.md` is authoritative if the two disagree (CLAUDE.md) |

Two things worth knowing before opening it:
- **It's 1127 lines.** Don't read it linearly start-to-finish in one sitting — the chapter-by-phase
  slotting above is what a linear read skips. The one time to read it straight through is *after*
  finishing Phases 0–6, as a coherence check, not as a first pass.
- **For a live pitch instead of study**, `.docs/work/mvp-advisor-demo/script.md`'s own "Quick chapter
  map" (bottom of that file) is the faster lookup — narrower, tuned to questions that come up
  off-script during rehearsal, not a full read.

---

## Part B — Manual demo run, step by step

This is the same sequence `make demo` automates, broken open so each step is visible. Use `make demo`
itself for rehearsal speed; use this version to explain to the advisor what is actually happening
under the hood, or if `jq`/the wrapper script is unavailable.

### B0 — Prerequisites, check every time (not a one-time setup)

```bash
# Memory pressure — CLAUDE.md: check before every local-AI run, not just once
sysctl kern.memorystatus_vm_pressure_level   # must read 0 (green)

# Redis reachable, and the eviction invariant holding
redis-cli PING
make redis-check

# Ollama running, with the frozen envelope actually pinned (ADR-017)
pgrep -q ollama && echo "ollama up" || echo "FAIL: start ollama first"
make env-check
```

If pressure is not green: close apps, recheck. Do **not** proceed under yellow/red for anything you
intend to show live — a run under pressure is invalid even for a demo, because a swap event mid-demo
is exactly the failure the whole platform exists to prevent.

### B1 — Cold reset

```bash
make demo-reset
```

Restores the corpus from git, `FLUSHALL`s Redis, re-ingests, and **asserts** the result
(`corpus:44 t1:0 t2:0`) rather than trusting it — refuses if it can't prove the cache is actually
cold. Must run with the gateway **stopped** (`FLUSHALL` drops `idx:cache`/`idx:corpus`, and a live
gateway only rebuilds them at startup).

### B2 — Start the gateway

```bash
make dev
```

Starts `rag.server` in the background, then the gateway with the UI bundled from `ui/dist`. Watch
for the startup line printing `tau=... theta=...` — confirms which demo values are live. To rehearse
a different τ (e.g. the "what about τ=0.86?" question):

```bash
REUSE_TAU=0.86 make dev
```

Other tunables, all demo settings, none frozen: `REUSE_THETA`, `REUSE_TAU_HIGH` (ships effectively
off at `1.0`), `LANE_SIGMA` / `LANE_SIGMA_HI` (the third-lane band, ADR-030 — `LANE_SIGMA_HI`
defaults to `LANE_SIGMA`, which collapses the band and disables the MIXED lane).

### B3 — The four pinned steps, manually

**Use these exact strings — do not paraphrase on the day** (pinned in `plan.md` Day 4 §1b, re-verified
2026-09-06; the numbers below are the actual measured run in `backup-run-2026-09-05.md`, not targets
to reproduce exactly — the machine will vary).

```bash
# Step 1 — fresh question, the cost every uncached system pays
curl -sS -X POST localhost:8080/ask -H 'content-type: application/json' \
  -d '{"question":"Am I entitled to a full refund on my headphones 30 days after delivery?"}' | jq .
# Expect: "cache":"MISS", a few seconds, similarity/source_overlap null
```

```bash
# Step 2 — exact repeat, Tier 1
curl -sS -X POST localhost:8080/ask -H 'content-type: application/json' \
  -d '{"question":"Am I entitled to a full refund on my headphones 30 days after delivery?"}' | jq .
# Expect: "cache":"TIER1_HIT", ~0 ms
```

```bash
# Step 3 — paraphrase, Tier 2, different words / same evidence
curl -sS -X POST localhost:8080/ask -H 'content-type: application/json' \
  -d '{"question":"Is a full refund possible for my headphones 30 days after delivery?"}' | jq .
# Expect: "cache":"TIER2_HIT", similarity ≈ 0.9750, source_overlap ≈ 1.00
```

```bash
# Step 4 — the trap: high similarity, different grounding
curl -sS -X POST localhost:8080/ask -H 'content-type: application/json' \
  -d '{"question":"Am I entitled to a full refund on my sofa 30 days after delivery?"}' | jq .
# Expect: "cache":"MISS", similarity ≈ 0.8689, source_overlap ≈ 0.40 — a fixed τ=0.85 threshold
# would have served the headphones answer here; the containment rule correctly refuses.
```

**Read the gateway's own terminal for the counterfactual line** — this is the sentence that *is*
C1's signal, and it's worth pointing at directly instead of paraphrasing it:

```
cascade similarity=0.8689 overlap=0.40 reuse=false similarity_only=true entered_band=true
  retrieved=[policy-returns-furniture#chunk-0 policy-returns-electronics#chunk-0 ...]
  entry_sources=[policy-returns-electronics#chunk-0 policy-returns-furniture#chunk-0 ...]
```

`similarity_only=true` while `reuse=false` says out loud: *a fixed threshold would have served this
wrong; the containment rule did not.*

Counters after all four:

```bash
curl -sS localhost:8080/stats | jq .
# requests 4, tier1_hits 1, tier2_hits 1, generations_avoided 2, hit_rate 0.5
```

### B4 — The coalescing moment (the strongest live moment, no slide needed)

Six concurrent identical questions should cost **one** generation, not six:

```bash
for i in 1 2 3 4 5 6; do
  curl -sS -X POST localhost:8080/ask -H 'content-type: application/json' \
    -d '{"question":"How long is the EarBuds Pop 3 battery, and can I return it after thirty days?"}' \
    -w ' -> %{http_code} %{time_total}s\n' -o /tmp/tab$i.json &
done
wait
curl -sS localhost:8080/stats | jq '{requests, generations_run, coalesced, generations_avoided}'
# Expect: 6 requests all answer around the same wall-clock time (one generation's worth, not 6x),
# generations_run == 1, coalesced == 5.
```

Pick a question that has **not** been asked yet in this run (or `make demo-reset` first) — if it's
already cached, all six answer instantly from Tier 1/2 and there's no generation to coalesce.

### B5 — The debug UI, as an alternative to curl

With `make dev` running and `ui/dist` built (`make ui` once, if not already built):

1. Open `http://localhost:8080` — the product catalogue, grouped by category, reading live from
   `GET /products`.
2. Click a product — opens `/#/p/{doc_id}`, a chat scoped to that product.
3. Ask the four pinned questions above, one per relevant product page. The counters sidebar
   (polling `/stats` every second) updates identically across every open tab — open several tabs to
   let the advisor see one shared total move in real time, which is the point B4 makes visually
   instead of via `curl`.
4. For the trap (step 4), the UI highlights any `sources` chunk that does **not** belong to the
   product currently open, labelled *"← not the product you asked about"* — the same arithmetic as
   the chunk-ID lists, rendered instead of printed.

### B6 — Reset between rehearsals

Stop the gateway (`Ctrl-C` on `make dev`), then repeat from **B1**. Never reset with the gateway
still listening (see B1's caveat) — the failure mode is a cache that *presents* as cold while
actually serving orphaned Tier-2 records against a rebuilt index, and nothing about it errors.

### Known fragilities to rehearse an answer for, not to hide

- **Step 4's margin over τ=0.85 is 0.019** (0.8689 vs 0.85) — survives "what about τ=0.86?" (verified,
  `REUSE_TAU=0.86 make dev` still refuses), fails at τ=0.87. Say τ is a demo setting before asked.
- **Miss latency is not one number** — measured anywhere from ~2 s to ~9.5 s across runs depending on
  machine load. Never cite a single figure; say "a few seconds, machine-dependent" and move on.
- **The sofa answer's tail can look muddled** on `dev-v0` (a corpus artefact — it correctly opens with
  the right refusal, then drags in an unrelated final-sale clause). The demo-critical contrast — yes
  for headphones, no for sofa — is intact regardless.

---

## Part C — Self-test: do you actually understand this, or do you just recognise it on re-read?

**The rule.** Read a question below. Answer it **out loud, from memory, no docs open**. If you have to
peek, that concept isn't done — go re-read its source file, then come back to *this* question, not a
similar-looking one. Recognising an answer when you see it again is not the same skill as producing it
cold, and a defence only ever tests the second one.

This is a **curated subset** — the sharpest question or two per topic, picked for diagnostic power, not
an exhaustive copy. Every file's own **Self-check** section (bottom of each `docs/learning/NN-*.md`)
has the full list; work through those too once this subset is solid.

### Phase 1 — Foundations

1. Why does an embedding model do the *opposite* of what a hash function is designed to do?
2. `sim(q, e) = 0.85`. Say precisely what that number claims, and what it does **not** claim.
3. Give the real reason this project never upgrades to an approximate vector index — not in terms of
   speed.
4. Why can't you just paste the whole corpus into every prompt instead of retrieving?
5. Give the reason this project uses RAG instead of fine-tuning that connects directly to
   invalidation (C2) — not the generic "fine-tuning is expensive" argument.
6. A 2-billion-parameter model fits in 1.7 GB resident. Why doesn't that number sound like a
   contradiction once you know what's actually loaded?

### Phase 2 — Architecture (synthesis, no single source file — this is the point)

7. Narrate a `POST /ask` request end to end, out loud, naming every component it touches on a
   **Tier-1 hit**, then again for a **miss**. Where does each one diverge from the other?
8. Point at the diagram in `Final_Proposal.md` §6 from memory and say what each arrow is, without
   looking.

### Phase 3 — The two tiers ⭐ (spend the most time here)

9. State Tier 1's correctness condition as a relation between `~` (string equality after
   normalisation) and `≈` (semantic equivalence) — and say what breaks if normalisation makes `~`
   *coarser* than `≈` rather than finer.
10. Write `overlap(A, B)` on paper. Say why the denominator is `|B|` and not `|A ∪ B|`, with the
    concrete case where Jaccard refuses a reuse that containment correctly allows.
11. At `top_k = 5`, how many distinct values can `θ` actually take, and why does that bound the sweep
    rather than just being a curiosity?
12. Walk the demo trap pair (headphones vs. sofa) through by hand: both chunk sets, the intersection,
    the fraction, the verdict — no notes.
13. Two follow-up questions to the same cached entry both score containment **0.80**, and need
    **opposite** verdicts. Explain the arithmetic reason no `θ` can separate them, and what the fix
    was.
14. `product_id` shows up twice in this project: rejected as a cache key, accepted as a namespace
    stabiliser. What is the actual difference between those two roles — not just "one is allowed and
    one isn't"?
15. Name one case the reuse rule is **structurally** incapable of catching (true regardless of
    tuning), and one **specific measured** false hit inside the δ ≤ 5 % budget.
16. Why is this a rule and not a learned model — give the strongest of the three reasons, not just
    the cheapest one.

### Phase 4 — Systems layer, 60% of the weighting

17. Someone with backend experience says "just rate-limit it." Give the two-clause answer that
    explains why that's a category error, not just a weaker choice.
18. Where **exactly** in the request path is a generation permit acquired, and why does that
    placement matter more than the permit mechanism itself?
19. Derive `λ_max` on paper in under two minutes. Why `min`, not a sum of the two paths?
20. Derive `h*`. Plug in real μ_gen and μ_hit, and explain **why the crossover being unreachable is a
    result, not a failure** — what would falsify it instead?
21. Describe the write-back race in three sentences, then the epoch guard's fix in one.
22. Why are dependency records "safe by construction" under the current mechanism, and what design
    was tried first that couldn't actually be built on this store?
23. Six identical concurrent requests arrive during one generation. What happens, and why must
    coalescing sit **inside** the permit acquisition rather than outside it?

### Phase 5 — Measurement discipline

24. Why is a hit rate reported without a false-hit rate uninterpretable — not just "less informative"?
25. Explain label circularity in three sentences, then the double-labelling ablation that controls
    for it in two.
26. What does the B-within / B-cross split settle, and why build a measurement that could embarrass
    your own headline claim?
27. Why does LRU make configurations 3 and 4 incomparable mid-run, and what isolates them again?

### Phase 6 — Positioning

28. Deliver the three-beat positioning (GPTCache is config 3 · the contribution is admission control,
    not the cache · the novelty claim was withdrawn) in under 60 seconds, unscripted.
29. Name the four things this project explicitly does **not** claim as novel, and for each, name the
    prior work that already does it.
30. A characterisation of a competing system turned out to be wrong during literature verification.
    What did the pre-registered process require you to do about it — and why say this out loud as a
    *result* rather than apologise for it?

### Whiteboard check — write these four from memory, not the words *around* them

```
overlap(q, e) = |retrieve(q) ∩ sources(e)| / |sources(e)|
reuse         = overlap ≥ θ  ∧  sim(q, e) ≥ τ
λ_max         = min( μ_gen/(1−h) , μ_hit/h )
h*            = μ_hit / (μ_gen + μ_hit)
```

If any of the four doesn't come out right on the first try, that's the concept to re-read tonight, not
the one to gloss over because the rest went fine.

### The capstone

`docs/learning/README.md` §"Tự kiểm" has 12 final questions written specifically as the
pre-flight check before a pitch — a wider synthesis than any single phase above. Finishing this
Part C and answering all 12 of those cold, in one sitting, with no phase skipped, is the actual
signal that you're ready — not having read every file once.

---

## Part D — `redis-cli`: is it installed, and the commands this project actually uses

### D0 — Checked on this machine, 2026-09-07: yes, already installed and running

```bash
which redis-cli        # /opt/homebrew/bin/redis-cli
redis-cli --version    # redis-cli 7.4.7
redis-cli PING         # PONG — the server is up right now
launchctl list | grep redis-stack   # com.redis-stack.server — running as a LaunchAgent
```

This came from `brew install redis-stack` (the cask), **not** plain `redis`/`redis-server` — see
CLAUDE.md: plain Homebrew `redis` 8.10 ships a config referencing search-module files it doesn't
bundle and crashes on start. The binary on this machine is `redis-stack-server`, and RediSearch (the
module every `FT.*` command below needs) is already loaded:

```bash
redis-cli MODULE LIST   # shows "search" — confirms RediSearch is active, not plain Redis
```

If any of the above fails on a re-check later (server restarted, moved machines): reload the
LaunchAgent per CLAUDE.md — `launchctl load -w ~/Library/LaunchAgents/com.redis-stack.server.plist`
— rather than `brew services`, which can't manage a cask.

### D1 — `redis-cli` itself, for someone who has never used it

Two modes:

```bash
redis-cli                 # interactive shell — type commands, see results, Ctrl-D to quit
redis-cli PING             # one-shot — run one command, print result, exit. Scriptable.
```

Everything this project stores is a **Hash** (a flat string→string map under one key) — there's no
List, Set, Sorted-Set-as-a-primary-store, or String value anywhere in the cache/corpus data itself
(the one exception, `lru:entries`, is a Sorted Set used purely as an eviction index — see D4). So the
only data-reading primitives worth knowing here are:

```bash
redis-cli HGETALL <key>        # every field of one hash, as a flat list
redis-cli HGET <key> <field>   # one field only
redis-cli HKEYS <key>          # just the field names, not the values
redis-cli KEYS '<pattern>'     # ⚠️ blocks the server while it scans — fine on this tiny dataset,
                                #   never do this on a production-sized keyspace
redis-cli --scan --pattern '<pattern>'   # the non-blocking equivalent — prefer this out of habit
redis-cli DBSIZE                # total key count across everything
redis-cli TTL <key>             # -1 always, here — nothing in this project expires by time;
                                 # see D3, eviction is count-based, not TTL-based
```

### D2 — This project's key schema, with a real example pulled from this machine right now

| Prefix | What it holds | Written by | Example key on this machine |
| :--- | :--- | :--- | :--- |
| `corpus::*` | One document chunk (product spec or policy) + its embedding | `rag/src/rag/ingest.py` | `corpus::product-headphones-03#chunk-0` |
| `t1:*` | Tier-1 exact-match entry: the stored answer, keyed by `sha256(normalize(q))` | Go gateway | `t1:1603db45d2...` |
| `t2:*` | Tier-2 semantic entry: answer + embedding + provenance | Go gateway | `t2:06G7F18C46A...` (a ULID) |
| `dep:*` / `entry:*` | C2's dependency map | `gateway/internal/deps/` | **empty on this machine** — deps/ is a 6-line stub, C2 not built yet (see Phase 4) |
| `lru:*` | The sorted set the gateway trims against to enforce count-based capacity (ADR-031) | Go gateway | empty here too — only appears once the cache actually exceeds capacity |

**⚠️ The one gotcha that silently breaks a manual query:** corpus keys use a **double** colon
(`corpus::product-headphones-03#chunk-0`), everything else uses a **single** one (`t1:...`, `t2:...`).
This isn't a typo to "fix" — LlamaIndex appends its own separator on top of the configured
`corpus:` prefix. Type a single colon by habit when reaching for a corpus key and it matches nothing,
silently (`--scan` returns empty, no error).

**Read one of each, for real, right now:**

```bash
redis-cli HGETALL 'corpus::product-headphones-03#chunk-0'
# doc_id, category, title, kind, text, ordinal, ... — the actual chunk text is in `text`

redis-cli HGETALL 't1:1603db45d2505cd469555d6f619b01e36c3341b38fcff394e01218062862994f'
# answer, model_used — the literal generated text this Tier-1 entry serves

redis-cli HKEYS 't2:06G7F18C46AHVRNYQ9QXZY4744'
# answer, source_chunk_ids, t1_key, similarity's neighbour source, embedding, namespace, lane,
# hit_count, dataset_epoch, created_at, query_text, source_overlap
```

Do **not** `HGETALL` a `t2:*` key by default — `embedding` is a raw ~3 KB float32 blob and floods
the terminal. `HKEYS` first, then `HGET <key> <specific field>` for what you actually want.

### D3 — The RediSearch commands (`FT.*`) — vector search lives here, not in plain Redis

```bash
redis-cli FT._LIST              # idx:corpus, idx:cache — the two indexes this project builds
redis-cli FT.INFO idx:cache     # schema: FLAT algorithm, COSINE metric, which fields are indexed
```

**The exact query the gateway issues for a Tier-2 lookup** (see [[02-embeddings]] §5) — you can run
the *structure* of it by hand, though supplying a real 768-float `$vec` from the CLI is impractical,
so this is for reading, not for typing verbatim:

```
FT.SEARCH idx:cache "(@namespace:{some_namespace})=>[KNN 1 @embedding $vec AS dist]" \
  PARAMS 2 vec "<768 raw floats>" DIALECT 2
```

What you *can* run directly — a plain tag/text filter with no vector math, useful for sanity-checking
the corpus without touching the gateway:

```bash
redis-cli FT.SEARCH idx:corpus '@kind:{product}' LIMIT 0 5 RETURN 2 title category
```

This is exactly the query `gateway/internal/catalog/catalog.go` runs to populate the demo UI's
product list — running it by hand is a fast way to check "does the corpus look right" without
starting the gateway at all.

### D4 — Operational commands worth knowing for this specific project

```bash
redis-cli CONFIG GET maxmemory-policy   # must read "noeviction" — see below
redis-cli CONFIG GET maxmemory          # must read "0" — no byte budget is ever set
```

Both matter because of **ADR-031**: this project's cache capacity is an **entry count**, enforced by
the *gateway* trimming a sorted set (`lru:entries`) on every write-back — Redis itself is configured
to evict **nothing at all**. If `maxmemory-policy` ever reads anything other than `noeviction` here,
`make redis-check` will refuse to let `make dev` proceed, and for good reason: any `allkeys-*` policy
can evict a `dep:*` record and silently break C2's completeness with no error (this is invariant #1
in `CLAUDE.md`).

```bash
redis-cli DBSIZE                                        # everything, all prefixes combined
redis-cli --scan --pattern 't1:*' | wc -l                # is the cache cold? (0 = yes)
redis-cli --scan --pattern 't2:*' | wc -l
```

This pair is exactly what `make demo-reset` and `make demo` check before doing anything — if you
ever see conflicting behaviour between what a curl response says and what you expect, run these two
first, before suspecting the gateway logic.

**Never run `FLUSHALL` by hand outside `make demo-reset`.** It wipes **every database on this Redis
server**, not just this project's keys — and `make demo-reset` refuses to run it if it detects
foreign keys for exactly that reason (`Makefile`'s `demo-reset` target). If you need a clean state,
use the make target; it's the one place in this project that command is allowed to run.

**Never run `FT.DROPINDEX`.** It drops the index definition but leaves the underlying `t1:*`/`t2:*`/
`corpus::*` hashes behind. The gateway only calls `EnsureCacheIndex` at **startup**, so a dropped
index under a live gateway means new writes go into a keyspace nothing is indexing — the cache looks
warm to `redis-cli DBSIZE` but is invisible to every `FT.SEARCH`, and nothing about it errors. This
exact failure mode is documented in `plan.md` Day 4 §1 — it's why `demo-reset` uses `FLUSHALL`
instead.
