# Decision log

**Status:** in force · **Opened:** 2026-09-22 · **Numbering starts at ADR-001.**

This log was opened fresh for the thesis phase. The pre-thesis decision log — a separate
document with its own numbering that reached 041 — was deleted on 2026-09-22 and **nothing here
refers to it**. An `ADR-NNN` in this file means an entry in this file and nothing else.

---

## How to use this file

One entry per architecturally significant choice. Append; never renumber, never delete. A
decision that turns out wrong is superseded by a new entry, and both stay — the write-up's design
chapter is built from this history, and so is the defence.

**Every entry must carry an `Invalidates:` line.** It is the single most important sentence in the
record, because it is the only thing that answers *"are these two numbers comparable?"* months
later. An entry without it is not finished. Write `none — no runs yet` when that is the truth.

```markdown
### ADR-NNN — <title>
**Decided (scope | method | frozen | data)** · <YYYY-MM-DD> · *<documents this touches>*

<one-paragraph statement of the decision>

- **Rationale:** why, and why now.
- **Alternatives:** what was rejected, and on what evidence.
- **Consequences:** what this makes true, and what it costs.
- **Invalidates:** which prior runs or results are now void — or `none — no runs yet`.
```

Nothing enforces this automatically. The hook that used to gate frozen-value edits was removed on
2026-09-22 along with the files it read, so a frozen value can now be changed with no error and no
warning. Writing the entry is the only trace such a change leaves.

---

## Summary

| ADR | Title | Status | Invalidates |
| :--- | :--- | :--- | :--- |
| ADR-001 | *Reserved* — co-hosted load generation and the load generator's footprint (`super-plan.md` item 1.6; named by Phase 1's exit criterion) | not yet written | — |
| ADR-002 | `v1` draws from six Amazon-PQA leaves mapped onto four departments | in force | none — no runs yet |
| ADR-003 | The generation envelope serves one slot; the admission pool bounds queueing, not memory | in force | no `run_id`; relabels μ_gen as a one-slot planning figure; voids the spike grid's `NUM_PARALLEL` axis |
| ADR-004 | The unfiltered Tier-2 phase is retired in code | in force | none — no runs yet; logs written before the 1.3 commit carry the old meanings under the same keys |

---

## Inherited state — decided before this log existed

These were settled during the pre-thesis phase and are **in force**. They carry no number here
because they were not decided under this log; their full reasoning lives in git history. Treat them
as frozen: changing any one of them invalidates every measurement taken before the change, and
doing so needs a **new numbered entry** in this file saying exactly that.

| What | Value | Why it is frozen |
| :--- | :--- | :--- |
| Generation model | **Qwen 3.5 2B** via Ollama, `q4_K_M`, `think: false` | Chosen by measurement over five candidates. It replaced Gemma 4 E4B, which entered yellow memory pressure at even the lightest config on this machine's real available RAM |
| Embedding model | **`nomic-embed-text`**, 768-dim, served by Ollama | Never an in-process PyTorch stack — ~2 GB resident for a ~400 MB model, which is a whole generation slot |
| Memory envelope | `num_ctx = 8192`, ~~`OLLAMA_NUM_PARALLEL = 4`~~ **one served slot** (**amended by ADR-003**) | The largest cell of the feasibility grid that held macOS green pressure, at 1.7 GB resident. ~~μ_gen ≈ 28.2 tok/s aggregate was measured **at this pair**~~ **ADR-003:** the 4 was never served; the grid's parallel axis is void, and μ_gen ≈ 28.2 tok/s is a one-slot planning figure until Phase 7 |
| Vector index | **FLAT (exact)**, COSINE | Approximate retrieval would make `retrieve(q)` nondeterministic and inject overlap noise indistinguishable from the provenance signal. No mid-study HNSW, ever |
| Retrieval depth | `top_k` fixed | It is the denominator of the containment measure; changing it rescales θ silently |
| Cache capacity | `C / K = 0.25` | A ratio of the frozen workload's distinct-query count, so capacity scales with the corpus instead of being a magic number. The **gateway** enforces it; Redis evicts nothing |
| False-hit budget | **δ ≤ 5 %**, provisional | The target operating point for θ/τ tuning until the judge's measured error floor finalises it |
| Support-gate threshold | **`τ_s = 0.6`**, pinned | Taken from the published value. It is **never swept** — sweeping it would turn an adopted mechanism into a tuned one |
| Doc-id kind prefix | `policy-` / `product-` | The reuse rule's lane selection depends on it, so it is a contract and not a naming habit |
| Corpus | `v1` from **Amazon-PQA**; redistribution **not granted** | Ship a download-and-build script plus a hash manifest, never the raw corpus. Cite Rozen et al., NAACL-HLT 2021. `dev-v0` is the development corpus and is **not citable in any result** |
| Load generation | **co-hosted**, reported as such | No second machine exists. The capacity claim is stated as a lower bound rather than a ceiling — see `super-plan.md`, "Measuring without a second machine" |

## Open questions carried into the thesis phase

| # | Question | Blocks |
| :--- | :--- | :--- |
| **F1** — ✅ **resolved by ADR-003, 2026-10-04** | Ollama overrides `OLLAMA_NUM_PARALLEL` to `-np 1` for this model. If the permit pool bounds to a concurrency the model server never offers, every shed rate measured so far describes the harness rather than the gateway | ~~No admission-control number is citable until this resolves.~~ Resolved: one slot frozen, one permit, `make env-check` verifies the live runner. Phase 1, item 1.1 |
| **P1** | The run-manifest schema, the frozen judge prompt, the operational metric definitions and the pre-registration record were deleted with the old protocol document and exist nowhere — not in the proposal, not in code. `experiments/k6/ask.js` still prints values "for manifest.yaml" | Phases 5, 6 and 7 all produce artefacts with no defined shape |

---

## Decisions

*ADR-001 is reserved for the co-hosted-measurement decision named by Phase 1's exit criterion and is
not yet written.*

### ADR-002 — `v1` draws from six Amazon-PQA leaves, mapped onto four departments
**Decided (data)** · 2026-10-04 · *`data-card.md` §1–§3, `docs/work/2026-10-03-pqa-category-choice/`*

`v1`'s product catalog and question workload come from six Amazon-PQA leaf files, mapped onto four
store departments. The department is the `category` value that product and policy records share —
the product↔policy join key of `data-card.md` §2 requirement 1. PQA has no department-level file;
every one of its 100 files is a leaf.

| `category` | Leaf file(s) | Pool under the proposed filters |
| :--- | :--- | ---: |
| `phones` | `unlocked_cell_phones` | 1,811 |
| `laptops` | `traditional_laptops` | 1,312 |
| `electronics` | `led_&_lcd_tvs` + `over-ear_headphones` | 302 + 399 |
| `furniture` | `chairs` + `home_office_desks` | 796 + 339 |

About 150 products, ~38 per department. The source bytes are pinned by sha256 in `data-card.md` §1.
*Pool* = products with 5–50 questions after removing price, stock and carrier questions, ≥ 3
bullets, no warranty term in their own prose, and at least one near-duplicate question pair
(content-word Jaccard 0.45–0.99, exact repeats excluded). The filters are proposed, not frozen;
they are fixed at `super-plan.md` item 3.2.

- **Rationale:** The author required departments a shopper recognises over PQA's narrow leaves.
  Every leaf clears the ≥ 50-products-per-category floor (from ~150 products over ≥ 3 categories)
  at least **6×**. Published return windows take **three distinct values** across the four —
  **14 / 30 / 30 / 90 days** for phones / laptops / electronics / furniture on Target's own
  returns page. Laptops and electronics share 30 days by design. `data-card.md` §2 requirement 2
  asks for differing **warranty** windows as well, and on current evidence that holds only weakly:
  ~1 year for phones, laptops and electronics against multi-year furniture, from **secondary**
  sources. A primary citation is owed before authoring, and the authored warranty terms may need
  to differ more than the published ones do. Opposing conditions of G5's kind are available from
  primary sources (opened vs unopened phones and furniture; new vs renewed laptops) and from
  traffic (domestic vs international warranty: 21.6 % of phone and 26.4 % of laptop warranty
  questions).
- **Alternatives:**
  - The leaf set `inkjet_printers`, `quadcopters_&_multirotors`, `chairs`, `mattresses` —
    recommended first on secondary measures and rejected by the author as too narrow. The
    evidence stays in the trail.
  - `carrier_cell_phones` for phones — dominated by `unlocked_cell_phones`: pool 387 against 2,260
    after the carrier filter, at the same carrier-question rate (~33 %).
  - **ePQA** (Amazon Science) as a replacement source — CDLA-Sharing-1.0 permits redistribution,
    which PQA's terms do not, but 2.66 questions per product and 0.3 % near-duplicate clustering
    give no traffic redundancy for a cache study. Kept instead as a **validation set** for the
    answerability filter: 194 questions in these six leaves carry ePQA's human labels.
  - Ten further sources were surveyed (AmazonQA, hetPQA, semiPQA, xPQA, HomeDepotQA, McMarket, JD
    product QA, Flipkart, Bitext, DRIP-R). None combines product content, real questions and
    per-product redundancy.
- **Consequences:**
  - Item 3.2's selection rule must add an **answerability filter**. Only ~20–23 % of real product
    questions are answerable from product specifications (ePQA 22.9 %; Flipkart ~20 %), so every
    pool above is an **upper bound** until that filter exists.
  - Natural within-product paraphrasing is low: 5–14 re-asks per 100 questions at cosine ≥ 0.85
    under the frozen embedding. **Generated paraphrases become Tier 2's volume source.** Natural and
    generated pairs are reported separately, and traffic redundancy is modelled by Zipf, never
    inherited from PQA, whose public Q&A board deduplicates what gets posted.
  - Real paraphrases and traps share the 0.80–0.85 cosine band in natural traffic (*"wifi?"* ~
    *"wi-fi?"* at 0.806 against *"USB ports"* ~ *"Ethernet port"* at 0.801). This is RQ2's premise
    observed before any rule is applied, and the B-within stratum can draw on it.
  - The policy corpus grows from 8 to ~13 documents (fixed at item 3.3). `electronics` contributes
    lookalikes but no primary-sourced condition pair. `laptops` and `electronics` share 30-day
    terms, which is where namespace partitioning refuses a safe reuse.
  - `data-card.md` §3's statement that PQA contains no policy questions is withdrawn. Policy
    *wording* can be sampled (thousands of warranty and return questions per leaf); policy
    *grounding* stays authored.
  - The raw files live in `data/raw/pqa/`, gitignored permanently, and are never redistributed.
    The builder verifies sha256 and a non-zero parse rate; the S3 ETags are multipart with an
    unpublished part size and cannot be checked.
- **Invalidates:** none — no runs yet on `v1`. `dev-v0` results stay non-citable, unchanged.


### ADR-003 — The generation envelope serves one slot; the admission pool bounds queueing, not memory
**Decided (frozen)** · 2026-10-04 · *`Makefile` envelope block, `experiments/scripts/env_check.py`, `gateway/cmd/gateway/main.go`, `admission/pool.go`, `interfaces.md` Versioning, `CLAUDE.md`, `README.md`, `super-plan.md`; trail `docs/work/2026-10-04-resolve-f1/`*

The frozen generation slot count is **1**, meaning the slots the model runner actually serves, which
`make env-check` verifies against the live runner. The gateway grants one admission permit. Ollama
0.33.2 refuses parallel requests for the `qwen35` architecture (Qwen 3.5 is a hybrid, with Gated
DeltaNet in three of every four layers) and launches its runner at `-np 1` whatever
`OLLAMA_NUM_PARALLEL` requests. **The frozen value 4 was never served.** `num_ctx = 8192` is
unchanged. The Ollama server version (**0.33.2**) and the LLM weights blob
(`sha256-7a3a8d55…6e8f520`) join the envelope. Both are pinned in the Makefile and checked by
`env-check`.

- **Rationale:**
  - **F1, confirmed 2026-10-04 (`docs/work/2026-10-04-resolve-f1/evidence/`).**
    - The live server ran with `OLLAMA_NUM_PARALLEL:4`. In 26 / 26 `qwen35` loads it logged
      `"model architecture does not currently support parallel requests"` and launched
      `-np 1`, with `n_slots = 1`.
    - On the spike build: 5 / 5 `qwen35` runners at `-np 1`, and 9 / 9 server starts
      *requesting* 1. The launchd pin that requested 4 was created on 2026-08-19, four days
      after the spike.
    - Corroboration: a four-request batch submitted at ≈ 19:03:22 on 2026-08-15 completed
      serially, at 11.3 / 16.6 / 26.4 / 30.2 s (`~/.ollama/logs/server-5.log:1142-1245`,
      at `-c 4096`).
    - No surviving log shows a `qwen35` runner with more than one slot.
  - **The W5 spike pre-registered this branch:** *"admission pool admits one generation at a
    time … degenerates to a mutex … proposal §5/§6.2 must be reframed around queueing and
    shedding."* It fired, and this entry takes it.
  - **One slot is the only value where the permit count equals what the server serves.** Any
    surplus permit queues requests inside Ollama, where the gateway can neither see nor shed them.
- **Alternatives:**
  - **Keep requesting 4 and size permits separately.** Rejected: an environment value that has
    no effect.
  - **Make 4 real**, with a model Ollama parallelises or a raw `llama-server -np 4`. Excluded:
    the generation model is frozen, and the second is a serving-stack change. A dense model also
    multiplies KV memory. The frozen model caches only 6 of 24 layers: 12 KiB per token, 96 MiB
    at 8192 (measured). The W5 figures for the dense candidates are unproven at 4 slots for the
    reason above, and Gemma 4 E2B already failed at one slot (7.7 GB).
  - **Upgrade Ollama.** Not now: support is unknown, and it is a mid-study stack change.
  - **A machine-wide launchd pin at 1.** Rejected in favour of removing the pin. It had no effect
    on either thesis model (`nomic-bert` ran 48 / 48 at `-np 1` under 4), and it would take
    parallel slots from other projects' models. The pin, `com.thesis.ollama-env.plist`, was
    therefore removed on 2026-10-04, and a copy is kept in the trail's `evidence/`.
  - **Re-running the W5 batch to test the relabelling.** Dropped: it cannot recover the
    2026-08-15 batch, and it would run on a different build.
- **Consequences:**
  - **S2 is restated.** The admission pool protects **queueing delay and goodput, not memory**.
    Memory is fixed when Ollama loads the runner, at its slot count, and admitting requests adds
    none. Under offered miss load above μ_gen:
    - admitted latency stays ≤ (1 + q) · S, where S is one service time and q the queue budget;
    - overload surfaces as counted `503`s;
    - goodput does not collapse.

    *"Bounds in-flight generation to what memory can hold"* is withdrawn everywhere live.
  - **Four §H fields change meaning:**
    - `shed`: the request would have waited more than q service times;
    - `t_permit_wait_ms`: all of the generation waiting;
    - `permit_queue_depth`: the whole queue;
    - `t_generate_ms`: loses the Ollama-internal wait it absorbed under 4 permits.
  - **The queue default moves 8 → 2** under the unchanged `2 × permits` rule. At one slot, q
    sets the S2 shed rate directly. As an M/M/1/K illustration at ρ = 0.8: ≈ 17 % shed at q = 2,
    against ≈ 3 % at q = 8. So **q is a pre-registered parameter of item 7.5**, recorded per run,
    and no shed rate is read at an unregistered default.
  - **μ_gen ≈ 28.2 tok/s and 0.19 req/s are planning figures until Phase 7.**
    - 0.19 req/s = 28.2 ÷ ~150 output tokens, with no ×4.
    - The label "aggregate at `OLLAMA_NUM_PARALLEL = 4`" is withdrawn.
    - On all surviving evidence, every `qwen35` runner served one slot. The batch that produced
      28.2 is in no surviving log, and its method is unrecorded: the token definition, the prompt
      and the output length.
    - Planning arithmetic only: S1's h\* > 0.988 holds for any μ_gen < 61 × (1/0.988 − 1) ≈
      0.74 req/s at the co-hosted μ_hit.
  - **The spike grid's `NUM_PARALLEL` axis is void,** and with it the "nearly flat footprint"
    memory-proxy rationale. "Largest cell that held green" rests on `num_ctx` alone. The 1.7 GB
    resident is a one-slot figure, consistent with this entry.
  - **The proposal's promised `OLLAMA_NUM_PARALLEL` sweep (§6.2) cannot be run** on this model and
    stack. It is withdrawn, pending the advisor's view.
  - **Version and identity are checked, and the pin is held.**
    - `env-check` compares `/api/version` and the weights blob in three places: the tag's
      `FROM`, the runner's `--model`, and the runner's `/props` `model_path`.
    - Ollama.app's auto-update is **off** (app DB `auto_update_enabled = 0`, 2026-10-04). It moved
      0.32.13 → 0.33.2 unattended on 2026-09-01.
    - **Restore artifact:** `Ollama-darwin.zip` v0.33.2, 194,977,237 bytes,
      `sha256:2e35765d941f51e6947f6ce33cb6b66d82c287780f5b64d0f71381067e0c1fa6` (the
      GitHub-published digest),
      `https://github.com/ollama/ollama/releases/download/v0.33.2/Ollama-darwin.zip`.
    - **Launch method:** Ollama.app. Its server logs to `~/.ollama/logs/server.log` and runs
      `OLLAMA_CONTEXT_LENGTH 262144`, which the service overrides per request with `num_ctx`.
  - **`env-check` reads the live runner.**
    - It takes the one `llama-server` serving the frozen blob as a child of the server on
      `OLLAMA_BASE_URL`. Its argv (`-np`, `-c`) and its own `/props` (`total_slots`, per-slot
      `n_ctx`) must agree.
    - It loads both models (~2.1 GB) to do so, fails closed when anything cannot be established,
      and prints an `ENVELOPE` line a run can be re-checked against at its end.
    - This deviates from `super-plan.md` item 1.1's wording ("from the Ollama server log"), because
      the log's location depends on how Ollama was launched.
  - **Run rule: no use of the Ollama app during a run.** Its selected model is the frozen model at
    context 262144, so one chat takes the only slot and reloads the runner, with no error.
  - **Forward, for P1:** the run manifest records the `ENVELOPE` line and the gateway's logged
    `permits`, and asserts they agree.
  - **Write-up:**
    - Item 8.2 frames admission control as queueing and shedding at one slot.
    - The limitations state that the backend serves one generation stream, so gains are measured
      against it, not against a batched backend.
    - Affected `Final_Proposal.md` lines (gitignored prose, not edited here): §3 `:105`; §6.0
      `:260`; §6.1 `:275`; §6.2 `:282`, `:284`; §7 `:330`, `:337`, **`:338` (now false)**, `:339`;
      §9.1 `:381`; §9.4 `:469`; §11 `:569`.
- **Invalidates:**
  - **No `run_id`:** none exists.
  - **Relabelled:** μ_gen ≈ 28.2 tok/s and 0.19 req/s become planning figures from a one-slot
    server.
  - **Void:** the W5 spike grid's `NUM_PARALLEL` axis, and the memory-proxy rationale built on it.
  - **No admission number is voided,** because none was recorded. The only one, a 4×200 / 4×503
    mechanism check on `dev-v0`, was never citable.

### ADR-004 — The unfiltered Tier-2 phase is retired in code
**Decided (method)** · 2026-10-05 · *`gateway/internal/httpapi/cascade.go`, `handler.go`, `types.go`, `reuse/rule.go`, `reuse/lane.go`, `telemetry/evallog.go`, `cmd/gateway/main.go`, `Makefile` (demo step 4), `interfaces.md` v0.10; trail `docs/work/2026-10-05-retire-unfiltered-phase/`*

Configuration 4's Tier-2 cascade issues **at most one** vector search, scoped to the query's
namespace, which is derived from that request's retrieval. The unfiltered (global) k=1 search that
used to work the τ gate is removed, together with the `τ_high` short-circuit (`REUSE_TAU_HIGH`)
and the inline `similarity_only_decision` record field. The gateway refuses to start when
`REUSE_TAU_HIGH` is non-empty. This ratifies the retirement that `interfaces.md` v0.9 described and
`Final_Proposal.md` named as awaiting a decision record.

**What this does not ratify.** The served rule stays **similarity ∧ namespace**: θ is computed but
not consulted (finding F-K, `super-plan.md`), and the support gate is not built. `overlap_decision`
is configuration 4's support-off verdict, logged as a counterfactual. A run's TIER2_HIT count is
therefore **not** configuration 4's until F-K is fixed.

- **Rationale:**
  - **v0.9 had already retired the phase in the contract, but the code still ran it.** It searched
    outside the namespace the rule enforces, so on a refusal it could only report an entry the rule
    would never serve. It also cost a second Redis search on every Tier-2 hit.
  - **No served decision changes**, checked twice rather than argued.
    - **Why it holds.** The scoped candidates are a subset of the global ones, and the frozen FLAT
      index is exact. So the scoped nearest's similarity is at most the global nearest's.
    - **The checks.** The impact analysis deleted the phase in a scratch copy. The design review
      implemented the final contract as written. Both ran the item 1.2 suite. Only two reported
      fields of one declared test changed, and every cache outcome, status, answer and side effect
      held.
    - **Preconditions:** one cache snapshot; `REUSE_TAU_HIGH` unset (it was, everywhere); the FLAT
      index. Under HNSW the subset argument fails.
  - **Two reporting defects close with it:**
    - **F-E:** a failed retrieval reported a band entry with a zero overlap.
    - **F-G:** the counterfactual was computed on the global nearest rather than the served entry.
  - **Why `τ_high` was disabled before this:** the reasons `reuse/rule.go` carried, kept here when
    the field went. They were measured on **dev-v0 and are not citable**:
    - across 17 labelled probes, traps and correct reuses interleaved: the worst trap scored
      0.9685, and only one of seven correct reuses (0.9899) sat above it;
    - once retrieval ran concurrently with the embedding, a short-circuit saved no latency;
    - on 2026-09-09, the old default of 1.0 fired live. The byte-identical question asked about two
      products embeds to the same vector (similarity exactly 1.0), and one product's answer was
      served for the other's question with no namespace check.
- **Alternatives:**
  - **Keep the phase, disabled.** Rejected: it still runs the global search and still reports the
    global nearest on every refusal, which the rule never judges.
  - **Keep a display-only global search** so a cross-namespace lookalike still shows a high
    similarity in the demo. Rejected by the author (D1): it would pay a search on every request to
    report a number no decision uses.
  - **Retire `entered_band`** instead of restating it. Rejected: it breaks two item-1.2 tests outside
    the two that 1.2 declared 1.3 may change.
  - **Build configuration 3 now.** Out of scope: that is configuration selection, F-K's item.
- **Consequences:**
  - **What the reported fields now mean** (D1–D7, under unchanged key names):
    - `similarity` is the nearest entry within the query's namespace, or null.
    - `entered_band` means a same-namespace candidate cleared τ.
    - `source_overlap` and `overlap_decision` are computed only for that candidate. They are null on
      a retrieval failure, and on every refusal.
    - `t_search_ms` is one span, null where no search ran.
    - `reuse_rule` in the §H record appears on below-τ refusals too. The HTTP response carries it
      only on a TIER2_HIT.
  - **`entered_band` ≡ TIER2_HIT** while θ and the support gate are outside the served decision.
    This yields two invariants:
    - **I1, the metric.** *% reaching the provenance check* = among records with
      `similarity != null`, the share with `reuse_rule` ∈ {`namespace`, `composite`}. It is 1.0 by
      construction, so a gate re-added before the lane rule drops it.
    - **I2.** `entered_band ∧ cache ≠ TIER2_HIT` never occurs. One would mean the Redis TAG filter
      and Go's `MatchNamespace` disagree.

    I1 rests on the extension field `reuse_rule`, which v0.10 names in §H so that it is not dropped.
    `Final_Proposal.md`'s *"1.0 by construction"* stays true and is not edited.
  - **`refusal_cause = NAMESPACE`** is unreachable in configuration 4 except through a filter/Go
    disagreement. "No in-namespace candidate" is not a namespace refusal (item 2.3 must not code it
    as one).
  - **Configuration 3 has no code path.** `REUSE_TAU_HIGH` was the only way to serve on similarity
    alone over the whole cache. `cache.Store.NearestTier2` is kept as configuration 3's primitive.
    Configuration 3's served rule, the static-cache arm and the join script that *decisions changed
    by provenance* needs have no `super-plan.md` item yet. Until they exist, that metric has no
    derivation.
  - **A filter that matches nothing now looks like a cold cache** (`similarity` null, no Tier-2 hits).
    On a warm cache with a Tier-2 hit rate ≈ 0, rule out the filter first. `make demo` step 3 is its
    live witness.
  - **`make demo` step 4** prints only what the response carries. Its header and its UI hint still
    tell the old cross-namespace story, and are left for a demo pass.
- **Invalidates:** **none — no runs yet.** `experiments/results/` holds no run. Logs written before
  the 1.3 commit carry the old meanings under the same keys, and the `similarity_only_decision` key
  is the only in-log discriminator until P1's manifest records the gateway SHA. **Never mix the two
  in one figure.** The Tier-2 planning figure (≈ 61 req/s) stays a valid lower bound: removing a
  search cannot lower μ_hit.
