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
| ADR-001 | Load generation is co-hosted; a co-hosted figure is a bound, an indicative reading or nothing, never a ceiling | in force (one open item: how 7.5 measures μ_gen) | none — no runs yet; relabels the 2026-09-06 μ_hit probes; supersedes the off-box wording in the k6 files, two Makefile banners and `experiments/README.md`, and the "lower bound on h*" wording in CLAUDE.md, super-plan.md and Final_Proposal.md (stale until the author edits it) |
| ADR-002 | `v1` draws from six Amazon-PQA leaves mapped onto four departments | in force (its return windows and "~13 documents" are partly amended by ADR-012) | none — no runs yet |
| ADR-003 | The generation envelope serves one slot; the admission pool bounds queueing, not memory | in force | no `run_id`; relabels μ_gen as a one-slot planning figure; voids the spike grid's `NUM_PARALLEL` axis |
| ADR-004 | The unfiltered Tier-2 phase is retired in code | in force | none — no runs yet; logs written before the 1.3 commit carry the old meanings under the same keys |
| ADR-005 | Served answer text is stored content-addressed in `raw/answers/` | in force | none — no runs yet; a log written before the 1.5 commit has no answer store and cannot be judged |
| ADR-006 | `t_generate_ms` means "this request's own `Answer` call was attempted" | in force (one open item: the 1 ms threshold) | none — no runs yet; ABANDONED and GENERATION_FAILED records' `t_generate_ms` is null before the F-H commit and not comparable across it, and any derived overhead is not either |
| ADR-007 | Redis holds only derived state; the corpus of record is the versioned file corpus | in force (one open item: P1 must record `redis_version` + `rdb_last_save_time`) | none — no runs yet; no run ever depended on Redis persistence config, which was unrecorded until this entry; the restart-voids-a-run rule binds forward from P1's manifest |
| ADR-008 | The dataset epoch is sourced from outside the Redis keyspace it guards | in force (binds forward — the epoch is a constant stub until Phase 4) | none — no runs yet; `dataset_epoch_at_retrieval` carries no information while `DATASET_EPOCH_STUB = 0` |
| ADR-009 | The support gate is served, and every judged Tier-2 candidate carries one refusal cause | in force (the real-answer sample, `plan.md` steps 1c–1e, **ran 2026-10-14**: `docs/work/2026-10-14-real-answer-sample/`, no stop rule fired, nothing tuned) | none citable — no runs yet; logs written before the 2.3 commit carry `cache = TIER2_HIT`, `entered_band`, `source_overlap` and `t_search_ms` under an older meaning and lack the five new keys; the 2026-10 item-1.6 Tier-2 hits were served with no gate |
| ADR-010 | The support gate is switchable per run, and every record names the arm | in force (binds forward — no run has taken either arm yet; the real-answer sample of ADR-009 has run, `docs/work/2026-10-14-real-answer-sample/`) | none citable — no runs yet; a log from the 2.3 commit up to the 2.4 commit lacks `support_gate` and is gate-on, and a log from before the 2.3 commit is neither arm |
| ADR-011 | `v1`'s 152 products are drawn by one pre-registered rule; R2 is a pre-filter, not a label | in force (3.4 re-labels every R2-answerable workload query) | none — no runs yet; replaces the 3.1 manifest `bf0feb48…` with `741d52e3…` |
| ADR-012 | `v1`'s policy corpus is 12 authored documents, one per condition, written to rules fixed before the text; G5 is a lexical scan plus the author's read | in force (item 3.3 done 2026-10-21; 3.6 inherits five checks; 3.4 avoids 10 products) | none — no runs yet; replaces ADR-002's "14 / 30 / 30 / 90" return windows |
| ADR-013 | `v1`'s workload is 1,274 queries written by Claude under rules fixed before the text, split by unit, with `K` per run file | in force (item 3.4 done 2026-10-22; 3.6 inherits the gate changes; the Phase 5 judge is not Claude) | none — no runs yet; reads ADR-011's "separate stratum" as "separate population" |
| ADR-014 | `v1` freezes with G1 recorded as failed (21 pairs, floor 50): a corpus finding that bounds C1, not a change to the gate | in force for the form (chosen by the author 2026-10-23; the exit wording was applied at the author's instruction to close Phase 3 — the "How C1 is read" paragraph and the supervisor line are still the author's to accept) | none — no runs yet; changes how 3.6's first gate result is read; 3.6's freeze ADR becomes ADR-015 |
| ADR-015 | `v1` is frozen: 164 corpus files and 3 workload files, 539 chunks, `K` 622 / 652, with G1 recorded as failed | in force (item 3.6 done 2026-10-23; Redis holds `dev-v0` afterwards; the author and the supervisor decide whether a `v2` follows, before Phase 4) | none — no runs yet |

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
| Support-gate lexical score definition | `S_lex = \|content-tokens(a) ∩ tokens(C)\| / \|content-tokens(a)\|`: stopwords = **Lucene `StopAnalyzer.ENGLISH_STOP_WORDS_SET`** (33 words, transcribed in `reuse/support.go`); tokens under 3 characters dropped; lowercase then split on `[^a-z0-9]+` (ASCII-only, deliberately not `cache.Normalize`); **no stemming**; sets, not multisets; refused when `S_lex < τ_s` | `τ_s` is pinned and never swept, so the list, the length rule and the tokenizer carry the leverage a tuned threshold would: an edit to any of them silently rescales every `support_lex` logged before it. **Added 2026-10-12 by item 2.1, not pre-thesis.** The proposal specifies only "a fixed stopword list", so Lucene's is this thesis's choice, not the published system's, and that `τ_s = 0.6` transfers to this definition is **assumed, not measured** (to be checked on ~10–20 real generated answers before item 2.3). Pinned by `TestSupportStopwordsArePinned` and `TestContentTokensRules`; record: `docs/work/2026-10-10-support-gate-lexical-arm/approvals.md`. **After the first logged run, any edit to the list, the length rule or the tokenizer needs a numbered ADR with an `Invalidates:` line.** **"After the first logged run" means the first run on `v1` (a citable run), not a `dev-v0` run, which is not citable; decided in ADR-009, 2026-10-14. The unit list stays draft until the Phase 3 freeze and is frozen before any false-hit sample is looked at.** |
| Support-gate numeric arm definition | Every number in the cached answer must be in **one** evidence chunk that holds the same value and, if a listed unit follows the number, the same unit attached to a number in that chunk; a number the arm cannot read blocks. Number = ASCII digits with `,ddd` groups and a `.d+` part, compared clean (no commas, no leading zeros, no trailing zeros after the point, integer zeros kept). Unit = the word right after the number (glued, after spaces, or after one hyphen; a space is ` `, tab, `U+00A0` or `U+202F`, a hyphen is `-` or `U+2011`, a line break is neither), only if on a **closed list**: second…year · g, kg, mg, lb, oz · mm, cm, km, inch, ft · ml, litre · w, kw, v, mah, wh · hz…db · rpm · percent (`%`) · `$ € £` before; aliases; a plural `s` is dropped only if 2+ letters remain. Letter-digit tokens (`IPX7`, `3rd`) are *codes* and must appear whole. Number words (`zero`…`ninety`, compounds) are read only before a listed unit. Unreadable = refuse: `1,5`, `5.3.1`, `.5`, non-ASCII number characters, `hundred`/`half`/… before a unit. Chunks are read alone, never joined. No threshold | The arm has no threshold, so the grammar is its only knob: an edit to any rule, list or table silently rescales every `support_numeric_ok` logged before it. **Added 2026-10-14 by item 2.2, not pre-thesis.** The rules are this thesis's choice, not the published system's. The unit list is **draft until the Phase 3 corpus freeze** and is frozen before any false-hit sample is looked at. **After the first logged run, any edit needs a numbered ADR with an `Invalidates:` line.** Known gaps, accepted: right number with the wrong unit in the same chunk; words between number and unit (counted in `Unitless`); `a year`; other Unicode spaces and dashes (en dash, `U+2010`, thin space) between number and unit (the answer is then read by value only, and in evidence the unit is lost, so that chunk cannot support a unit). Pinned by `TestNumericReaderGolden`, `TestNumericReaderRules`, `TestNumericUnitListPinned`, `TestNumericNumberWordsPinned`; full text: `docs/work/2026-10-14-numeric-arm/approvals.md` **"After the first logged run" means the first run on `v1` (a citable run), not a `dev-v0` run, which is not citable; decided in ADR-009, 2026-10-14. The unit list stays draft until the Phase 3 freeze and is frozen before any false-hit sample is looked at.** |
| Refusal cause (served Tier-2 rule) | The served rule is similarity ∧ namespace ∧ support **with the gate on, and similarity ∧ namespace with it off** (`SUPPORT_GATE`, ADR-010). One `refusal_cause` per **judged** candidate, in this order: `NAMESPACE` → `SIMILARITY` → `SUPPORT` / `NOT_SCORED` → `NONE`. `null` = no candidate judged (never `NAMESPACE`: a cold cache is a MISS with no candidate). `NOT_SCORED` = chunk IDs with no evidence text: refused, never counted as `SUPPORT`. `CONTAINMENT` is never written (θ is outside the served rule, F-K). A retrieval with no chunks makes no Tier-2 attempt. Serve only on `NONE`. | The order, the strings and the serve rule decide what every figure that reads `refusal_cause` means; a change silently re-labels every record logged before it. **Added 2026-10-14 by item 2.3 (ADR-009).** Pinned by `TestJudgeCauses`, `TestJudgeAgreesWithDecideLane`, `TestJudgeServedIsCauseNoneOnly`, `TestCauseValuesArePinned` and 31 hand mutants (`docs/work/2026-10-14-refusal-cause-code/mutation-check.py`). **Amended 2026-10-14 by ADR-010 (item 2.4): the served rule is per arm, the off-arm returns `NONE` with no support result after the namespace and similarity checks, and the cause order is unchanged.** **After the first run on `v1`, any change needs a numbered ADR with an `Invalidates:` line** |
| Doc-id kind prefix | `policy-` / `product-` | The reuse rule's lane selection depends on it, so it is a contract and not a naming habit |
| Corpus | `v1` from **Amazon-PQA**; redistribution **not granted** | Ship a download-and-build script plus a hash manifest, never the raw corpus. Cite Rozen et al., NAACL-HLT 2021. `dev-v0` is the development corpus and is **not citable in any result** |
| Load generation | **co-hosted**, reported as such (**ratified by ADR-001**) | No second machine exists. The capacity claim is stated as a lower bound rather than a ceiling — see `super-plan.md`, "Measuring without a second machine" |

## Open questions carried into the thesis phase

| # | Question | Blocks |
| :--- | :--- | :--- |
| **F1** — ✅ **resolved by ADR-003, 2026-10-04** | Ollama overrides `OLLAMA_NUM_PARALLEL` to `-np 1` for this model. If the permit pool bounds to a concurrency the model server never offers, every shed rate measured so far describes the harness rather than the gateway | ~~No admission-control number is citable until this resolves.~~ Resolved: one slot frozen, one permit, `make env-check` verifies the live runner. Phase 1, item 1.1 |
| **P1** | The run-manifest schema, the frozen judge prompt, the operational metric definitions and the pre-registration record were deleted with the old protocol document and exist nowhere — not in the proposal, not in code. `experiments/k6/ask.js` still prints values "for manifest.yaml". **ADR-010:** the manifest must record `SUPPORT_GATE`, taking the arm from the records or checking that the environment and the records agree, never from the environment alone | Phases 5, 6 and 7 all produce artefacts with no defined shape |

---

## Decisions

### ADR-001 — Load generation is co-hosted; a co-hosted figure is a bound, an indicative reading or nothing, never a ceiling
**Decided (method)** · 2026-10-07 · *`super-plan.md` item 1.6 and "Measuring without a second machine", `experiments/k6/README.md`, `Final_Proposal.md` §7 and §9.4 (read-only); trail `docs/work/2026-10-06-loadgen-footprint/`*

The load generator (k6) runs on the same machine as the system under test, because no second machine exists
and none is dated. This **ratifies** the inherited row "Load generation: co-hosted, reported as such" above,
which was frozen without a numbered entry, and **supersedes** the prose that called a co-hosted run invalid
(`experiments/k6/README.md`, the headers of `ask.js` and `mu_hit.js`, two `Makefile` banners,
`experiments/README.md`). `Final_Proposal.md` §7 and §9.4 already said co-hosted and already named this ADR as
the record of it, so nothing there needs editing for the *decision to co-host*; **but their "lower bound on
`h*`" wording (§7 `:345`, §9.4 `:460`) is superseded by the corrected argument below**, as is the same wording
in `CLAUDE.md` (`:162-167`) and in `super-plan.md` (Phase 7's exit line, item 7.2's Done-when, and "Measuring
without a second machine"). Those edits wait for the author (see **Invalidates**). A figure taken co-hosted is reported as a
**bound**, an **indicative reading**, or **not at all** — never as a ceiling. Item 1.6 measured what the
generator costs: **k6 used 1.0 % → 4.8 % of one core as the offered rate went 2 → 32 req/s (0.6 % of the
8-core machine at 32), and its `phys_footprint` read 21 – 28 MB** (the larger of two spot readings per row;
the exact peak resident set, `ru_maxrss`, was 59 MB). The author's pre-registered rule
(A = 25 % of one core, B = 250 MB, `approvals.md`, set before any file of the recorded runs existed) therefore
says **adopt co-hosting unmitigated**. That is a statement about k6's own cost. It is **not** a measurement of
interference, and the second half of this entry says what follows and what does not.

**What the measurement is** (`evidence/footprint/footprint.md`, run A; `evidence/footprint-mixed/footprint.md`,
run B; the outcome in `evidence/outcome.md`). Steady-state mean over the ticks from 5 s after k6 started to 5 s before its last tick (49 – 50 s of a 60 s row), % of **one**
core, three repetitions per rate, HEAD `17bf221`, `gateway/` and `rag/` unmodified:

| Regime | Offered req/s | Achieved | k6 CPU, mean (spread over reps) | % of the machine | k6 peak RSS | SUT total CPU | Sampler's own cost |
| :--- | ---: | ---: | :--- | ---: | ---: | ---: | ---: |
| all-hit | 2 | 2.01 | 1.01 % (0.88 – 1.10) | 0.13 % | 54 MB | 1.4 – 1.5 % | 2.66 % |
| all-hit | 8 | 8.01 | 1.94 % (1.82 – 2.04) | 0.24 % | 56 MB | 1.9 – 2.0 % | 2.39 % |
| all-hit | 16 | 16.02 | 2.70 % (2.28 – 3.20) | 0.34 % | 56 MB | 2.4 – 3.1 % | 2.29 % |
| all-hit | **32** | 32.02 | **4.80 %** (4.58 – 5.10) | 0.60 % | 59 MB | 4.4 – 4.8 % | 2.75 % |
| mixed | 8 | 8.02 | 1.41 % (1.37 – 1.48) | 0.18 % | 56 MB | 77 – 97 % | 2.33 % |

*All-hit* is the five-question smoke set after a warm-up, so every request is a Tier-1 hit and Ollama is idle.
*Mixed* is a seeded Zipf draw over the smoke set plus 300 suffixed variants, each repetition from a **cold
cache**: it produced Tier-1, Tier-2, MISS and shed outcomes together (tier mix 263 / 84 / 41 in the first
repetition, 63 – 93 sheds per row, the LLM runner at 41 – 55 % of a core and the embedding runner at 24 – 30 %).
k6's cost is linear in the rate: **CPU % = 0.81 + 0.124 × req/s**, about 0.0012 CPU-seconds per request. The two spot
`phys_footprint` readings per row stayed between 21 and 28 MB in every kept row.

- **Rationale:**
  - **The decision was already made; the record was missing.** Every Phase 7 number would otherwise be taken in
    breach of a rule the repository still printed in five places, with nothing on record saying the rule had
    been set aside.
  - **The plan's argument needed one empirical premise** — that at the rates the sweep offers, k6 costs little
    enough to leave the SUT's headroom intact. It holds for k6's own cost: the figure above is small and
    linear. **It does not by itself license the conclusion below it** (see the next section).
  - **The memory pressure was not gated, by the author's decision of 2026-10-06** (development, not a
    benchmark). The consequence is stated in terms below.
- **What is citable co-hosted — one row per quantity, with the direction co-hosting biases it:**

  | Quantity | Co-hosting bias | Status | What Phase 7 must add |
  | :--- | :--- | :--- | :--- |
  | goodput | **lower bound**: the generator takes CPU from the SUT | bound | k6's concurrent CPU from the same run |
  | shed rate | **upper bound** | bound | the same |
  | μ_hit | **lower bound** | bound, **never a ceiling**. The 2026-09-06 Tier-1 figure (≈ 8000 req/s) is **not rescued**: it is a ceiling, and it was taken at *urgent* pressure. The Tier-2 figure (≈ 61 req/s) stays a planning lower bound | per mode and per sweep point (item 7.2) |
  | hit rate under load | **two-sided**: slower generation leaves more duplicate misses in flight (coalesced followers lower the measured hit rate), while `ask.js` computes it over answered requests, which excludes sheds that are always misses (raises it) | indicative | pin `h_r` to the workload's ρ ceiling or a low-load replay |
  | **μ_gen** | co-hosting depresses it, which **raises `h*`**: anti-conservative | **not citable co-hosted for `h*`** | measure it with a sequential closed-loop client and **no** load generator (concurrency 1 saturates one slot, so `b = 1` by construction) — ⟦PENDING: the author confirms that item 7.5 does this⟧ |
  | **p95** | **two-sided**: CPU contention raises it; loopback removes network RTT; k6's `http_req_duration` may omit a request sent late (a reviewer's claim, **unverified here**) | **not a bound of either kind** | reported **only** with k6's concurrent CPU from the same run, and stated as loopback latency |
  | the **1.6 footprint** | biased by pressure (below) | **indicative, unconditionally**; the run is **exploratory** under standing constraint 4 | **not** Phase 7's interference measurement |

- **The `h*` argument, corrected.** `h* > h_r` ⟺ `μ_hit/μ_gen > h_r/(1 − h_r)`, one inequality; at
  `h_r = 0.988` the threshold is **≈ 82.3**. The planning ratio is 61/0.19 ≈ 321, a margin of **3.9×**
  (61/15.6). **That is the plan's 3.8× (61 against ≈ 16 req/s; 3.90 unrounded) restated in μ_gen units, not a second cushion**, and both inputs are
  non-citable (`dev-v0` with no `run_id`; a planning figure, ADR-003). With `a` and `b` the factors by which
  co-hosting depresses μ_hit and μ_gen, a ratio measured with both co-hosted is `R_measured = R_true · a/b`,
  so the claim holds iff **`b/a > 0.257`** (≈ 0.26) at `R_measured = 321`. "A co-hosted figure is a lower bound on `h*`"
  is therefore true of the **μ_hit leg only**. `h_r` is a third term that co-hosting moves in both directions
  (table above).
- **The footprint does not satisfy Phase 7's interference clause** (*"every co-hosted number carries its
  interference measurement"*). CPU share does not measure cache, memory-bandwidth or scheduler contention
  against the embedding server, which is the mechanism the lower-bound argument runs through. A comparison
  "with and without k6" is **not runnable** (no load without a generator). Two candidate methods are not
  designed here: (a) a **matched-burner test**, **assigned to item 7.1 to design** — a synthetic CPU burner
  sized from this footprint, run beside k6, to see whether the measured quantities move; (b) the no-generator
  μ_gen measurement above, which is **item 7.5's**. The sweep's real rate grid is item 7.1's and is not defined yet: **2, 8, 16 and 32 req/s
  bracket it; they do not measure it.**
- **Read the table with its regime.** The all-hit rows run against an **idle** SUT (Ollama near 0 %); the mixed
  row against a **busy** one (77 – 97 % of a core). A footprint judged against an idle SUT says nothing about
  headroom against a busy one. At the same 8 req/s k6 used 1.94 % in run A's all-hit rows and 1.41 % in run B's
  mixed rows (−27 %). That is a **difference between two runs**, taken in different sessions (swap 8.4 – 8.5 GB
  against 9.0 – 9.2 GB, a different gateway process, an LLM runner at 14 MiB against 286 – 968 MiB), and within
  each run the rates ran in ascending order, so drift aliases with rate. It is **not** a measured property of
  the regime and it is no bound: it says only that the all-hit figure was the higher of these two. k6's RSS is set by its VU allocation (`VUS = 40` was fixed; `vus_max` was 40 in every row) and is flat
  across rates by construction; it is an allocation floor, not a response to load.
- **The LLM was mostly not resident, although `ollama ps` listed it as loaded.** The LLM runner's resident set
  (`ps rss`, sampled every fifth tick; the column "LLM runner RSS MiB" in each table) was **2,047 – 2,334 MiB**
  in the three 2 req/s rows, **13 – 19 MiB throughout in 8 of the 12 all-hit rows** (a ninth, `allhit-r8-rep1`,
  rose from 19 to 2,048 MiB inside the row) and **286 – 968 MiB in the mixed rows** while it was generating.
  Its weights were compressed or swapped out for most of the run, and the instrument's `assert_models_loaded`
  reads only `ollama ps`, which cannot tell. This does not change k6's own CPU (k6 never touches the LLM), but
  spec decision 3 ("both models resident") held in name only, the "idle SUT" of the all-hit rows had a
  swapped-out generator, and the mixed rows' 77 – 97 % SUT CPU is the CPU of a generation that was paging its
  own weights. **A later run that needs a resident SUT must gate on the runner's resident set, not on
  `ollama ps`.**
- **The cache was unbounded.** The gateway ran with `CACHE_CAPACITY` unset (unbounded, its default): every kept
  row shows `lru:` at 0 beside non-zero `t2:` counts, and the same invocation's banner in `probes.md` reads
  `cache_capacity=0 UNBOUNDED`. The banner of the recorded gateway itself was not captured, so this is an
  inference. The mixed row's tier mix therefore comes from an unbounded cache, an upper bound on hit rate that
  no deployment reaches, with the capacity ratio (0.25 × K) not in force.
- **The instrument's own cost is the same order as what it measures.** The sampler spent **2.3 – 2.75 % of a
  core per rate (2.1 – 3.1 % per run)**, more than k6 below about 16 req/s (k6: 1.0 % at 2, 1.94 % at 8). It was reduced once during the
  shakedown (SUT processes are sampled every fifth tick; it had been ~3× k6's cost) and is reported beside
  k6's figure in every row. **Phase 7 inherits it** if it runs the sampler at 1 Hz with these calls and
  should state it, or lower the frequency, or replace the `ps` and `sysctl` calls.
- **Pressure.** The reading is **raw and never mapped to a colour**: the repository says `0` is green, the
  sysctl read **2** throughout (one row's minimum was **1**), `memstatus_level` ran 28 – 55 %, **swap in use was
  8.4 – 9.2 GB and growing across the session, and every kept row shows swap-in or page-in activity** (up to
  7,980 swap-ins and 11,512 swap-outs in one row). Background daemons held the CPU at the start
  (`translationd` 46 %, `modelcatalogd` 38 %, `mobileassetd` 30 % in the top-5 before run A). Paging inflates
  CPU readings and shrinks RSS, so **the figure is indicative whatever the zone was**. This is the divergence
  from `Final_Proposal.md` §7 (`:343`) and §9.4 (`:461`), which discard a run that leaves green: **this run was
  not gated and is classified exploratory.** *Exploratory* here means: kept as a development characterisation,
  **not citable and not an input to any result**. It is **not** a run that standing constraint 4 would accept
  (a run outside green is discarded and repeated): that constraint is **unamended**, and this run falls outside
  it only because it is not a thesis run, by the author's decision of 2026-10-06. No number in the results chapter is
  sourced from this table; Phase 7's footprint comes from Phase 7's own runs. The encoding of
  `kern.memorystatus_vm_pressure_level` is **unverified** (the repository's `0 = green` may be wrong; XNU is
  recalled as returning 1 / 2 / 4), and if so `make measure`'s `!= 0` gate can never pass. That is outside this
  decision and is recorded for the author.
- **The pre-registration, and what it is worth.** A and B were fixed before any recorded file existed, so the
  rule could have sent the ADR to a mitigation. The author chose the values **after** being told that the
  exploratory shakedown, which is not evidence, had shown about 1.8 % and about 23 MB, so the rule was unlikely
  to bind, and it did not (margin 5.2× to A, 8.9× to B). The outcome is a statement about k6's own cost and
  nothing more.
- **There is no p95 headroom threshold.** An earlier draft carried one. It was dropped: a value fixed after
  seeing this table is a choice of which rates' p95 become citable. In its place, with no parameter
  (`super-plan.md`'s first option): **every co-hosted p95 is reported with k6's own concurrent CPU from the same
  run.** The sampler wraps any k6 invocation for that reason.
- **Alternatives:**
  - **A second machine.** None exists and none is dated.
  - **Keep the off-box rule and run co-hosted anyway.** Rejected: it leaves every Phase 7 number in breach of a
    frozen rule with nothing on record, which is the silent-deviation failure this log exists to prevent.
  - **Pin k6 to the efficiency cores with `taskpolicy`.** Not evaluated: the pre-registered rule did not call
    for a mitigation. A possible response if a later run exceeds A.
  - **An in-process closed-loop generator.** Rejected: a closed loop cannot saturate the target, which is the
    whole subject of S1.
- **Consequences:**
  - **Not measured, and not claimed:** interference with the embedding server; any rate above 32 req/s; the
    Tier-1 μ_hit probe regime (~400 req/s), which `super-plan.md` calls a different regime and which this entry
    records as **not rescued**; the footprint under green pressure; and the footprint against v1 content (the
    workload was the built-in smoke set and seeded variants; nothing from `data/`).
  - **Item 7.1** designs the interference method; **item 7.5** measures μ_gen without a generator (⟦PENDING⟧
    above); **item 7.2** owns `mu_hit.js`'s verdict logic. Co-hosted, a non-zero `dropped_iterations` cannot
    tell the target saturating from k6 starving itself, and `mu_hit.js`'s verdict line (`mu_hit ~= X`) prints it as if it were a
    ceiling. This entry names that and does not change it.
  - **`interfaces.md:164` records a lost measurement, not merely stale wording.** It promises "off-box
    end-to-end" latency, and that measurement will now not exist: co-hosted p95 is loopback latency and
    excludes the network. The contract is **not** edited here (a v0.13 bump and the contract phase for a
    sentence about a record this item does not touch); this entry is where it is recorded.
  - **Nothing from this footprint reaches a result.** What Phase 7 may cite is the table in this entry's
    second section, with the "what Phase 7 must add" column.
  - **What the sampler does to the SUT's cache.** `make footprint` **deletes** the `t1:`, `t2:` and `lru:`
    keys of the Redis the SUT uses, at the start of a run and before every mixed repetition (never `corpus:`),
    and **refuses to run while `dep:` or `entry:` keys exist** (the dependency region has one writer once C2
    is built; a deletion from outside would leave an unpurgeable entry with no error). The Makefile banner
    and comment now say so, `NO_FLUSH=1` skips it (refused with the mixed row), and the author's confirmation of
    this behaviour, which went beyond the single `make demo-reset` that decision 9 covered, is **pending**
    (`approvals.md`). Item 6.3's pre-populated static-cache arm must not meet this tool.
  - **The instrument changed after the recorded runs, and the numbers did not.** Review added guards (a wrong
    process, sampled CPU far below `wait4`'s total, many discarded ticks, a flush that spares the dependency
    region and follows `--redis-port`), the LLM runner's RSS column, a non-zero exit status when rows are
    excluded, and file hashes in the header. The tables of both runs were **regenerated from the stored CSVs**
    with the changed module and every number, the fit and every exclusion are identical
    (`evidence/provenance.md`). The sampler and `ask.js` were uncommitted when the runs were taken, so the
    headers carry no hash of them; `provenance.md` says what is and is not recoverable.
  - **Run history, kept as it happened.** Run A's three mixed rows died (k6 exit 107: a relative `--out`; k6
    resolves `open()` against the script's directory) and are excluded in its table with their flags; the
    mixed row was taken again as run B, in its own directory, after the fix and a green `/verify`. Neither was
    edited. `ABANDONED` and `GENERATION_FAILED` are **vacuous for the all-hit regime** and are not claimed
    settled for the mixed one (the log counter cannot tell them apart; every kept row had `error_rate = 0` and
    k6 exit 0).
- **Invalidates:** *none — no runs yet.* `experiments/results/` holds no run and no k6 footprint was ever
  recorded. It **relabels** the 2026-09-06 μ_hit probes, which were never citable (co-hosted, `dev-v0`, no
  `run_id`). What it **supersedes** is prose, not a value: the off-box wording listed above, **and the "lower bound on
  `h*`" wording** at `CLAUDE.md:162-167`, in `super-plan.md` (Phase 7's exit line, item 7.2's Done-when and
  "Measuring without a second machine", which now carries a pointer here) and at `Final_Proposal.md` §7 `:345`
  and §9.4 `:460`. Those stand until the author edits them: **read them through the corrected argument above.**

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

### ADR-005 — Served answer text is stored content-addressed in `raw/answers/`
**Decided (method)** · 2026-10-06 · *`interfaces.md` §H v0.11, `gateway/internal/telemetry/evallog.go`, `gateway/internal/httpapi/handler.go`, `gateway/cmd/gateway/main.go`, `.gitignore`, `super-plan.md` 5.4; trail `docs/work/2026-10-06-answer-text-storage/`*

The gateway writes the **text of every answer it serves** to
`results/{run_id}/raw/answers/{answer_sha256}.txt`: content-addressed, one file per distinct hash,
byte-exact, written by the evaluation logger's own writer **before** the record line that names it.
A run in which any named hash has no file, any line failed to encode or write, an answer and its hash
disagreed, or the log failed to close, is **INCOMPLETE** and not admissible. `experiments/results/*/raw/`
is **gitignored**. This is the decision `super-plan.md` item 1.5 said §H needed before it could change.

- **Rationale:**
  - **The judge runs offline with the generator unloaded**, and §H recorded `answer_sha256` and never
    the text. The only other copy is the cache, a **bounded LRU** the gateway evicts from
    (`CACHE_CAPACITY = round(0.25·K)`), so by judging time most hashes named nothing. A hash with no
    text behind it is a key to nothing.
  - **Re-generating is not an alternative.** The Modelfile sets `temperature 1` (U8), so a second
    generation can be a different answer, and §H already requires the hash to come from what was served.
  - **Content-addressed**, because 5.1's work list is the set of distinct answers, and a directory of
    them is that list. Under Zipf redundancy hits dominate, so a per-request copy would grow with the
    hit count, not the distinct-answer count.
  - **Written by the logger's writer, before the line**, so the order is structural. Nothing at a
    call site has to be remembered, and a record dropped or skipped loses its line and its file
    together.
  - **A guard** refuses to write a file whose bytes do not hash to the record's hash. It catches a
    call site that sets the hash and skips the text, which would otherwise publish an empty file
    under another text's name: that passes every "file exists" check and is wrong.
- **Alternatives:**
  - **Inline the text in every `requests.jsonl` record.** A record without its text becomes
    unrepresentable, which is its strength. Rejected: the plan names the directory; the file grows
    with the hit count; every analysis that parses it for latency or hit rate would read text it
    never uses.
  - **One `raw/answers.jsonl`**, a `{sha, text}` line per first sighting. The smallest version, and a
    real rival: it drops temp-file publication, the three-step `Open`, the `EEXIST` question and the
    per-file Spotlight and APFS (≥ 4 KB per file) cost. It loses atomic per-answer publication (a full
    disk leaves a torn line, not no file) and open-by-hash. **Rejected by the author's default**
    (2026-10-06), because the plan names the directory and 5.1 reads by hash. Reversible: only the
    writer and the §H layout wording change.
  - **A separate `AnswerStore` called from `Ask`.** Rejected: the handler gains an I/O concern and a
    second failure counter, and the file gets no ordering against the record.
  - **Write at `cache.Put`.** Rejected: it covers MISS only, and a hit on an entry that predates the
    run is exactly the case where this run has never written the text.
  - **Keep the text in Redis.** Rejected: bounded LRU, and the next run may flush it.
- **Consequences:**
  - **The invariant** (§H v0.11, rule 5). It holds in a run that is not INCOMPLETE, not in every run:
    a failed write still writes its line, which then names a hash with no file, and a line that fails
    to encode after its file was linked leaves a file no record names. Both are counted and make the
    run INCOMPLETE.
  - **The INCOMPLETE conditions are a Research Requirement** in the terms of `requirements.md`
    (violating one voids a result silently). The skeleton assigns no IDs yet, so none is numbered. They
    are: dropped records; a failed line write; a named hash with no file; an answer/hash mismatch (a
    **guard refusal**, never cleared by a later retry, because it means a call site skipped
    `SetAnswer`); a failed close.
  - **The verdict lives in the exit status and the log until P1 lands.** *Recoverable from `raw/`
    alone* holds; *admissible from `raw/` alone* does not.
  - **A `Link` that returns `EEXIST` is treated as success (the file already exists), and that is safe because of the directory,
    not because of SHA-256.** `Open` creates `answers/` with a non-recursive `Mkdir` after claiming the
    run id by exclusive create, so the directory is fresh, and the writer goroutine is the only thing
    that creates files in it. A later change that resumes a run or switches to a recursive `MkdirAll`
    would break exactly this and could silently accept a corrupt existing file.
  - **Invalid UTF-8 is unreachable**, not merely excluded: `AnswerChunk.text` is a proto3 `string` and
    protobuf-go validates it on unmarshal; cached answers come from those texts.
  - **Cost on a measured path.** Hit path: one string-header assignment, since the hash was already
    computed. Writer goroutine: a map lookup per record, and per distinct answer one create, write,
    chmod, close, link and remove. **Measured (plan step 7, `evidence/drain-rate.md`; exploratory, pressure level 2, not citable):** an
    already-seen record adds nothing measurable (≈ 4 µs, the pre-1.5 line cost), and a first sighting adds
    ≈ 440 µs (about 110× a line write), so the writer sustains ≈ 2,250 first sightings/s. Distinct answers
    are at most `0.25·K`, so a drop needs a worst-case burst of them at a high offered rate: above ≈
    16,300 req/s for K = 2,000, ≈ 5,200 for K = 5,000, ≈ 1,450 for K = 10,000, and any burst of ≥ 4,096
    first sightings (K ≥ 16,384) overflows on its own. At the planning figures (generation ≈ 0.19 req/s,
    Tier-2 ≈ 61 req/s) the margin is ≥ 35×; **only a Tier-1-heavy phase at thousands of req/s over a
    large K, in its first seconds, can drop.** A Phase 7 run of that kind checks `Dropped()` and
    `AnswersMissing()` first. Spotlight and the gateway under load are not measured. Not a `Dropped()` assertion: a tight `Log` loop would
    manufacture drops with or without this change.
  - **Limits, stated rather than fixed here:**
    - **F-F:** a record logged after `Close` is skipped and uncounted. Not widened: the CAS at the start
      of `Close` fixes the skipped set, not how long `Close` takes.
    - **`Log` racing `Close`** panics inside `Ask`'s deferred emit, where `net/http`'s per-connection
      recover swallows it: a lost record with only "http: panic serving" on stderr.
    - **`SIGKILL`** loses what is still buffered, records and answers together; a killed run is
      discarded either way.
    - The store proves **a file with the right hash exists**; it does not prove the serving path sent
      the client the bytes it logged beyond the paths the tests drive.
  - **Publication.** `experiments/results/*/raw/` is gitignored (decided 2026-10-06). `requests.jsonl`
    already carried verbatim PQA `query_raw`, and this adds LLM text grounded on PQA chunks;
    redistribution is not granted and the remote is public. `manifest.yaml` stays trackable. **Follow-on
    for `super-plan.md` 5.4:** a clean checkout no longer carries `raw/`, so "regenerate every figure
    from `raw/` on a clean checkout" now means *plus the raw archive*; 5.4 designs how that archive is
    kept and restored. With `raw/` outside version control, git no longer enforces that a finished
    run is write-once, and an edit to one would leave no trace; a hash manifest of `raw/` is not
    planned, and belongs with 5.4 and P1.
  - **Spotlight.** `/` is indexed on this machine, so each new `raw/answers/*.txt` is imported by
    `mds`/`mdworker` during the measured window (up to `0.25·K` files in the static-cache arm's
    first-sighting burst). Unmeasured. ⟦PENDING: the author's call: exclude `experiments/results/` from
    Spotlight as a run precondition, or measure it. Needed before Phase 3⟧.
  - **For 5.1** (flagged, not decided): the verdict key must be `(query, answer)`, not the bare hash,
    and the delimiter in `sha256(query ‖ answer)` is unspecified. `super-plan.md` 5.1's "deduped by
    `answer_sha256`" needs rewording. **SOURCE text is not stored**, and under `mutation: on` is
    recoverable only if the mutation harness writes the applied update set with epochs into `raw/`.
  - **U8** (temperature 1): whether it gates item 1.5 is the author's call (`approvals.md`, open
    question 7). This ADR is written on the reading that it does not, because the store keeps whatever
    was served. It bears on 5.1, where hash dedupe saves nothing if every miss produces a new text.
- **Invalidates:** none — no runs yet. A log written before the 1.5 commit has no answer store, so its
  answers are not recoverable and **it cannot be judged**.

### ADR-006 — `t_generate_ms` means "this request's own `Answer` call was attempted"
**Decided (method)** · 2026-10-06 · *`interfaces.md` §H v0.12, `gateway/internal/httpapi/handler.go`, `super-plan.md` finding F-H; trail `docs/work/2026-10-06-fh-generate-ms-on-abandoned/`*

The evaluation log's `t_generate_ms` is non-null **iff this request's own `Answer` call was attempted**,
whether it succeeded or not (for a record with a non-empty `cache`; a leader that panics after `Answer` is
logged with `cache: ""` and no value). The gateway now carries it on `ABANDONED` and `GENERATION_FAILED` leaders
that reached `Answer`, where it previously carried it on a MISS only. §H is amended to say so (v0.12,
doc-only). No field, key, wire shape or frozen value changes.

- **Rationale:**
  - **The code left a stage that ran with no span**, against the intent of §H's note that a `t_*_ms` is
    null where its stage did not run (a one-directional rule, so this is a tightening, not a breach). The
    stage (the gateway's span around `ragclient.Answer`) ran on a failed or cancelled attempt, and the
    closure computed the duration, then dropped it on every non-success path.
  - **It answers two questions that were unanswerable.** *Did an abandoned request's own `Answer` get
    attempted?* Before, only a filter on `permit_queue_depth >= 1` selected one subset and could not see a
    request that took `Acquire`'s fast path and left. *How long did a failed generation take?* The
    duration separates an immediate failure (ms) from a long one (s). It cannot separate an upstream hang
    from a slow generation: under k6 both read ≈ 120 s minus the time before `Answer`, and a hang already
    lands in `ABANDONED`.
  - **Why a contract entry for a one-line fix.** The field's *presence* used to mean exactly
    `cache == MISS ∧ ¬coalesced`. It no longer does. An analyst reading the example comment who selects
    MISS service times by presence would take in ABANDONED durations censored near 120 s and bias μ_gen,
    silently. The selection rule must live where the field is defined, not in a trail.
- **Alternatives:**
  - **Leave §H unchanged and record the rule in the trail.** Rejected by the design review: the example
    comment *"null unless generation ran"* can be read as forbidding the new values (the fast-path
    dead-context request makes no RPC), and a trail is closed when its task is.
  - **A new field** (`reached_server`, an RPC-sent timestamp). Rejected: a new §H field is a contract
    decision this bug does not need, and `t_generate_ms` plus the threshold below is enough.
  - **Also move `rec.Coalesced = shared` above the outcome switch.** Rejected for now: the same flaw, but
    a **second measurement change** (an extension field would appear on SHED, ABANDONED and
    GENERATION_FAILED records, and a follower of a shed leader would read SHED plus `coalesced`). Recorded
    as a finding next to F-D.
  - **Copy the value inside the closure** rather than after `Do`. Rejected: it changes the leader-panics
    path for no gain.
- **Consequences:**
  - **Per-statistic selection** (§H v0.12 field note): service-time and μ_gen select
    `cache == "MISS" ∧ t_generate_ms != null` (a MISS follower's value is null, a leader's is not, so this
    is exactly what presence selected before; `coalesced` is an extension field §H does not define and is
    **absent**, never `false`, on a leader), and while F-L is open that is necessary but **not
    sufficient**; permit-occupancy statistics may select on presence, but `t_generate_ms` is a **lower
    bound** on a MISS's hold (the permit is held through write-back) and no permit exists when admission
    is disabled; filters use `!= null`, never `> 0`.
  - **What a null means after the fix:** on GENERATION_FAILED a follower; on ABANDONED either a request
    that left while queued or a follower (`coalesced` is set only on a served MISS), so the two cannot be
    told apart offline except by a `t1_key` time-interval join. **F-L** is the `super-plan.md` finding that
    `rag.server` keeps generating after its RPC is cancelled; **F-D** is the one that a coalesced follower
    inherits its leader's cancellation.
  - **ABANDONED's value is censored** (F-L): at most the generation's true duration, and silent on
    whether `rag.server` finished. It tightens the orphan upper bound; it does not turn it into a count.
  - **The "RPC never left" split needs a threshold, and the threshold is pre-registered before anyone
    looks at the distribution.** *Default: 1 ms.* The gap defends the split, not the number: microseconds
    for an RPC that never left against seconds for one cancelled during a real generation. The failure
    mode is a never-sent tail above 1 ms (under `-race`, GC pauses, co-hosted CPU contention, a cancel
    during a lazy connect), which would read as "reached `rag.server`" with nothing to flag it. So an
    analysis **reports the count of ABANDONED values in [1 ms, 100 ms] beside the split and calls it
    unresolved if that count is not negligible.** The number is the author's to confirm and belongs in
    P1's manifest. ⟦PENDING: the author confirms or replaces the 1 ms default⟧
  - **Recorded, not fixed here:**
    - `t_permit_wait_ms` is **null on every fast-path request** (`Acquire` returns a permit with
      `Waited == 0` and the gateway renders a zero duration as null), which contradicts §H's *"null
      unless a permit was requested"*;
    - **and on a request that queued and then left**, because the closure returns before it is set;
    - `coalesced` is set only on a served MISS.
  - **Nothing here changes a count or a label.** Item 1.6's `ABANDONED` count is comparable across the
    commit. **1.6's first `RUN_ID` must be taken after this commit**: logs carry no gateway SHA until P1.
- **Invalidates:** none — no runs yet. A log written before the F-H commit has null `t_generate_ms` on
  `ABANDONED` and `GENERATION_FAILED` records; those two fields are **not comparable across it**, and any
  derived overhead is not either.

---

### ADR-007 — Redis holds only derived state; the corpus of record is the versioned file corpus
**Decided (scope | frozen)** · 2026-10-10 · *`docs/architecture.md`, `interfaces.md` §D/§E, `Final_Proposal.md` §7/§9.4, `Makefile` (`redis-check`); trail `docs/work/2026-10-10-redis-as-sole-store/`*

There is **no separate database server, and none will be added.** The store of record is
`data/<dataset_version>/*.json` plus the frozen chunking config — for `v1`, the download-and-build
script plus the hash manifest. Everything Redis holds is **derived**: `corpus::{chunk_id}` text and
vectors are rebuildable by `make ingest`; `t1:*`, `t2:*`, `dep:*` and `lru:entries` are cache state
whose total loss costs hit rate and nothing else. Redis is therefore a **derived-state store**, not
the system's database, and its durability requirements are correspondingly weak.

**What this does not claim.** It does not claim the storage design would scale. It claims only that
losing Redis entirely is recoverable, and that the measurement is unaffected by which store holds
the derived copy. **Recoverable does not mean survivable.** The corpus index shares the process with
the cache, so Redis down is an outage, not a degradation (see the second rationale point below).

- **Rationale:**
  - **A second store would sit on the measured path.** It adds its own latency component to every
    retrieval, consumes part of a memory envelope that is already the binding constraint (~9–10 GB
    before any Ollama test), and moves **neither contribution**: C1 is set intersection over chunk
    IDs computed in Go, C2 is a reverse index. The cost is measurement noise for no movement on the
    claim.
  - **A mutable RDBMS would weaken reproducibility.** A `dataset_version` tag plus a hash manifest
    is what makes a run repeatable; a store that can be edited out of band is the opposite of that.
  - **Durability does not need a second store, and a second store does not provide availability.**
    *(Corrected the same day. The first draft said total loss of Redis degrades to the no-cache arm,
    which is true of the cache keys only; see trail F11.)* Losing Redis loses no data, because
    everything in it is rebuildable. It is still an **outage, not a degradation**: `idx:corpus` and
    `corpus::*` share the process with the cache, and the no-cache arm still retrieves. With Redis
    down, every request fails until Redis returns and, if the keyspace was lost, until `make ingest`
    rebuilds the index. Redis is a single point of failure for availability, not for durability. A
    database server would not change that, because it would be a second single point of failure on
    the retrieval path. Availability needs replicas and failover, which is scale-out (§12). The
    outage is accepted because availability under store failure is not a measured property, and a
    restart already voids the run (Consequences).
- **Alternatives:**
  - **Postgres/pgvector as store of record** — rejected on the measured-path argument above. It is
    the right answer for a deployment and the wrong answer for this measurement.
  - **In-memory vector search + external document store** (the split Category-Aware Semantic
    Caching reports, arXiv 2510.26835, at 30 ms → 2 ms miss cost) — rejected for the same reason,
    and **cited rather than adopted**: it is the industry answer to this question and belongs in the
    write-up as such.
  - **Treating Redis as the store of record and hardening it** (AOF with `F_FULLFSYNC`, replica).
    AOF is rejected because it solves a durability problem that F1 shows does not exist, at a cost in
    write latency on the measured path. A replica would address availability, which is a real
    problem (F11), but a replica is scale-out and out of scope.
- **Consequences:**
  - **Redis durability is deliberately weak, and that is now a recorded position rather than an
    accident.** The live posture on 2026-10-10 was `appendonly no`, `save 3600 1 300 100 60 10000` —
    i.e. the **cask's shipped default**, which no decision had ever examined.
  - **Two costs are accepted and named.** (i) An unclean stop rolls the keyspace back by up to
    1 hour / 5 min / 60 s depending on write volume, which **silently undoes invalidations that had
    already fired** (trail F3, demonstrated). (ii) The config file lives at
    `/opt/homebrew/Caskroom/redis-stack-server/7.4.0-v8/etc/redis-stack.conf` — a version-pinned
    path a `brew upgrade` replaces wholesale, and the LaunchAgent passes no config argument — so the
    posture is mutable by an unrelated upgrade with no announcement.
  - **Therefore: a Redis restart during a run invalidates that run.** The rollback is not visible
    from inside Redis (trail F2: the dependency map comes back consistent with the entries it
    indexes), so this cannot be checked after the fact from `raw/` alone. **P1's run manifest must
    record `redis_version` and `rdb_last_save_time`**, which is the only way the check becomes
    possible. Carried as an **RR**, not an NFR: violating it voids a result silently.
  - **What is *not* a consequence:** correctness invariant 1 is unaffected. An evicted dependency
    record remains the only route to an unpurgeable entry, and `make redis-check` already closes it.
- **Invalidates:** none — no runs yet, and no run has ever depended on Redis persistence
  configuration, which until this entry was unrecorded. The restart-voids-a-run rule is **forward
  only**: it binds from the first run taken under P1's manifest, since no earlier log can be checked
  against it.

---

### ADR-008 — The dataset epoch is sourced from outside the Redis keyspace it guards
**Decided (method | frozen)** · 2026-10-10 · *`interfaces.md` §E, `rag/src/rag/config.py`, `rag/src/rag/retrieve.py`, `gateway/internal/deps/` (unbuilt); trail `docs/work/2026-10-10-redis-as-sole-store/`*

When C2 is built in Phase 4, `dataset_epoch` **must not be stored as a Redis key.** It is derived
from the corpus of record — the manifest hash, or a file written by the ingest step — so that
comparing an entry's stamped epoch against the current epoch is a **cross-medium** comparison.
Today it is `DATASET_EPOCH_STUB = 0`, a Python constant (`rag/src/rag/config.py:34`), so the guard
is inert and this entry binds forward rather than describing current behaviour.

- **Rationale:**
  - **An epoch inside the keyspace rolls back with the data it guards, so it cannot see the
    rollback.** This was demonstrated, not argued (trail, `rdb-rollback.sh`, isolated instance on
    port 6399): a purged entry was resurrected by an RDB restore **and** the epoch counter reset
    from 8 to 7 — the same value stamped on the resurrected entry. The guard compares 7 against 7,
    agrees, and admits stale data. Correctness invariant 3 fails **silently**, which is the exact
    failure it exists to close.
  - **Cross-medium is what makes it detectable.** `data/` does not roll back when the Redis
    keyspace does, so an epoch read from the corpus manifest still reads 8 after the restore, and
    the mismatch is visible at the first comparison.
  - **Now is the cheap moment.** `gateway/internal/deps/` is a one-line stub. Retrofitting the
    epoch's source after Phase 4 ships would touch the write-back path, the purge path and §E
    together.
- **Alternatives:**
  - **Epoch as a Redis counter** (`INCR epoch_counter`) — the obvious implementation, and the one
    this entry forbids. Rejected on the measured demonstration above.
  - **Epoch as a Redis counter plus AOF** — narrows the window, does not close it, and puts an
    `fsync` on the write path; on macOS an `fsync` is not durable without `F_FULLFSYNC`
    (`interfaces.md` §H already notes this).
  - **Detect the rollback instead of surviving it** (compare `rdb_last_save_time` at startup) —
    rejected as a weaker guarantee than making the comparison cross-medium in the first place, and
    it would only fire at startup rather than per write-back.
- **Consequences:**
  - §E gains a sourcing requirement, not a new field: the wire format and the `dataset_epoch` field
    on `t2:*` records are unchanged, so **no contract version bump** and no change at the seam.
  - The ingest step becomes the epoch's author. It must write the epoch where both services can
    read it, which makes a corpus rebuild and an epoch advance the same event — the property §E
    already assumes.
  - Phase 4's design must state where the epoch is read from; a design that reads it from Redis is
    refused against this entry.
- **Invalidates:** none — no runs yet. The epoch is a constant stub today, so no prior log's
  `dataset_epoch_at_retrieval` carries information, and none becomes comparable or incomparable
  because of this entry.

### ADR-009 — The support gate is served, and every judged Tier-2 candidate carries one refusal cause
**Decided (method | frozen)** · 2026-10-14 · *`interfaces.md` §A and §H (v0.13), `gateway/internal/reuse/cause.go`, `httpapi/cascade.go`, `httpapi/handler.go`, `telemetry/evallog.go`; trail `docs/work/2026-10-14-refusal-cause-code/`*

From the 2.3 commit the served Tier-2 rule is **similarity ∧ namespace ∧ support**: the cascade runs
both support arms on a candidate that cleared the lane rule and τ, and serves only when the one
refusal cause is `NONE`. Every **judged** candidate carries exactly one `refusal_cause`, chosen in the
order `NAMESPACE` → `SIMILARITY` → `SUPPORT` / `NOT_SCORED` → `NONE`. `null` means no candidate was
judged, and a cold cache is never `NAMESPACE`. `NOT_SCORED` (chunk IDs with no evidence text, a stale
server) is **refused** and never counted as `SUPPORT` or as the gate-off arm; a run with any such record
is not admissible (§H rule 10). `CONTAINMENT` is never written, because θ is outside the served rule
(F-K). A retrieval with **no chunks** makes no Tier-2 attempt, for both arms of configuration 4. §H
gains five keys: `refusal_cause`, `support_lex`, `support_numeric_ok`, and the extensions
`candidate_entry_id` and `candidate_sources`. On a refused record `entry_id` and `entry_sources` name the
entry the miss wrote, not the candidate.

- **Rationale:**
  - **A cause that is not logged cannot be attributed.** Without `refusal_cause` a support refusal is
    indistinguishable from a namespace refusal, and the adopted gate's contribution cannot be
    separated from the namespace rule's. The thesis records exactly that gap against the source
    paper's conjunctive reporting.
  - **One function owns the order** (`Thresholds.Judge`, `reuse/`, standard library only). It is
    tested against `DecideLane` on every input it decides (NaN, equal τ, empty namespaces, a lane
    mismatch with equal strings), so the two cannot drift. The cascade only passes values in.
  - **`NAMESPACE` comes first** because it is an alarm: the namespace is enforced by the search
    (ADR-004), so a namespace refusal means Redis and Go disagree. If `SIMILARITY` won when both
    applied, the alarm would count too few. The order cannot change a false-hit count, since false hits
    are served records and all carry `NONE`.
  - **`NOT_SCORED` refuses** because serving on an unchecked answer would make a stale server look like
    the gate-off arm, and refusing as `SUPPORT` would blame the gate for a broken instrument. It is the
    numeric arm's fail-closed rule applied to the instrument itself.
  - **`candidate_*` exist because of a defect the design review found** (`review.md` F1): on a support
    refusal `source_overlap` belongs to the candidate while `entry_id` and `entry_sources` belong to the
    new entry, whose sources equal `retrieved_chunk_ids`. An offline Jaccard from `entry_sources` reads
    1.0 on every refusal, with no error. `raw/` is write-once, so a field not logged now is missing
    from every run.
  - **The zero-chunk guard** closes a hole items 2.1 and 2.2 left open: with no chunk, the spec lane's
    namespace falls back to the product ID, the search runs, and a hit is served with no evidence behind
    it. It sits in the cascade, not in `reuse.Namespace`, which the write path also calls.
- **Alternatives:**
  - *Serve on `NOT_SCORED` and mark it* — rejected: the run then looks like the gate-off arm.
  - *`SIMILARITY` before `NAMESPACE`* — rejected: it hides the alarm below τ.
  - *Put the cause on the HTTP response* — rejected for 2.3 (no wire change); the response shows a
    high similarity and an overlap on a refused MISS with no reason, which a later demo pass may fix.
  - *A shutdown counter in `cmd/gateway` for rule 10* — rejected: rule 10 is decidable from `raw/`
    alone, and the counter would put a fourth package in a change that touches three.
  - *A guard inside `reuse.Namespace`* — rejected: it would change the write path's partition.
  - *`t_support_ms`* — not added. The gate costs about 30 µs for both arms (benchmark, M1, not a
    measurement of the system), about 0.2 % of a Tier-2 request, **inferred**: the 16 ms it divides by
    has no `RUN_ID`. It lands in `t_total − Σ t_*`. Phase 7's μ_hit with the gate on against off
    measures it.
- **Consequences:**
  - **Four keys keep their name and change meaning:** `cache = TIER2_HIT` (also passed the gate),
    `entered_band` (no longer equal to the hit indicator), `source_overlap` on a MISS (present on a
    support refusal), and `similarity`, `reuse_rule`, `t_search_ms` on a zero-chunk retrieval (null).
    Compute *% entering the cascade band* from `entered_band` alone.
  - **This supersedes three statements of ADR-004** without editing it: that `source_overlap` is null "on
    every refusal", its invariant I2 (`entered_band ∧ cache ≠ TIER2_HIT` never occurs), now I2′, and
    that "the support gate is not built" (it is served since the 2.3 commit). It
    also extends ADR-004's diagnostic *"Tier-2 hit rate ≈ 0 → rule out the filter first"*: a high
    `SUPPORT` or `NOT_SCORED` share is now a cheaper first explanation, read from the log.
  - **Phase 2 exit clause 1 is not shown through the cascade.** In configuration 4 the namespace search
    already refuses the measured warranty case before the gate, so that case is a MISS with cause
    `null`. The arms separate the measured pair only at unit level, on the pinned dev-v0 texts and an
    **authored** cached answer (items 2.1, 2.2). Whether that meets the clause is the author's call; this
    entry does not claim it.
  - **Known limit, not fixed:** the search is `k=1`. A refused entry is never touched, so it can stay
    the nearest entry for its paraphrases and refuse each in turn. It shows as one `candidate_entry_id`
    refused many times in a run.
  - **Open at the time:** the real-answer sample (`plan.md` steps 1c–1e) had not run, because memory
    pressure was level 2. `τ_s = 0.6` is not changed by it whatever it shows: a bad result is a finding for
    the author, not a reason to tune. **Update 2026-10-14: it ran** (`docs/work/2026-10-14-real-answer-sample/`,
    dev-v0, n = 27, not citable). The second pre-registered null did not occur (0 of 5 paraphrases refused);
    2 of 21 answers fell below `τ_s`; `τ_s` and the lexical definition were **not** changed. Two findings are
    carried to item 6.1: about one answer in ten is refused against its own evidence, and the lexical arm
    penalises answers that narrate "the context".
  - **The reading of "after the first logged run"** in the two support-gate frozen rows is now fixed:
    it means the first run on `v1`. A `dev-v0` run is not citable, so the Phase 3 unit-list edit needs
    no ADR, and must still come before any false-hit sample is looked at.
  - Item 2.4 adds **one parameter to `Judge`** for the gate-off arm; the consistency test then runs with
    both values, and there is no second code path.
  - **Forward note for Phase 4 (C2), from `/ai-review` F7.** While the gate is on, it can hide a missed
    purge: if an edit changes "30 days" to "14 days" and the purge misses the entry, the numeric arm
    refuses the stale entry, so a completeness check that counts stale entries *served* after an edit looks
    clean. Phase 4's completeness run must therefore use the **gate-off arm** (item 2.4), or read the
    `dep:*` and `entry:*` state directly. This is recorded here and in `super-plan.md` Phase 4.
  - **`make demo` step 3 asserts nothing** (it prints what `cache` returns), so a real answer refused by
    the gate shows as MISS there, and a MISS is now ambiguous between a filter fault (cause `null`) and a
    support refusal. The HTTP response cannot tell them apart (Q10 was "no"); the evaluation log can.
    `mu_hit.js` tier2 mode does assert `TIER2_HIT`, so it fails loudly. The Makefile was not unlocked for
    this item, so the demo comment and an assertion are left to the author (`approvals.md`).
- **Invalidates:** none citable — `experiments/results/` holds no run. Item 1.6's `footprint-20261006-b`
  (dev-v0, indicative, logs no longer on disk) served 250 `TIER2_HIT` with no gate and is not comparable
  across the 2.3 commit; ADR-001's k6-cost conclusion does not depend on what the gateway served. A log
  written before the 2.3 commit has none of the five keys and the older meanings above; do not mix the
  two derivations in one figure.

### ADR-010 — The support gate is switchable per run, and every record names the arm
**Decided (method | frozen)** · 2026-10-14 · *`interfaces.md` §H (v0.14), `gateway/internal/reuse/gate.go` and `cause.go`, `httpapi/cascade.go` and `handler.go`, `telemetry/evallog.go`, `cmd/gateway/main.go`; trail `docs/work/2026-10-14-support-gate-switch/`*

Configuration 4 is two ablation arms, the support gate **off** and **on**, and a gateway process runs
exactly one of them. The arm is chosen by the environment variable `SUPPORT_GATE`: `on`, `off`, or unset
meaning `on`. Any other value, including a set-but-empty one, stops the process before it opens Redis,
the RAG connection or the evaluation log. The arm is a typed value, `reuse.Gate` (`GateOn` is the zero
value), passed as the **first** parameter of `Thresholds.Judge`; only the exact value `GateOff` skips the
gate. It lives in **one** field, `Handler.SupportGate`, which feeds both the `Judge` call and the new
required record key `support_gate` (`"on"` or `"off"`, on every record, never null, no `omitempty`). With
the gate off, `Judge` returns cause `NONE` with no support result **after** the namespace and similarity
checks, so both support fields are null and every cause that comes before the gate is the same on both
arms. The served Tier-2 rule is now **per arm**: *similarity ∧ namespace ∧ support* with the gate on,
*similarity ∧ namespace* with it off. **Row 2.4's Done-when** ("`support_gate` in the run manifest
selects the arm") is met by this reading: there is no run manifest (P1), the gateway reads `SUPPORT_GATE`,
and P1's manifest must record it.

- **Rationale:**
  - **A switch with no label cannot be read.** After ADR-009 many records have null support fields
    (refused before the gate, `NOT_SCORED`, no candidate), so null does not name the off-arm. A run with
    no served Tier-2 hit could not be told gate-on from gate-off at all. `raw/` is write-once and there is
    no manifest, so the record is the only durable place for the arm.
  - **The zero value is the safe one.** The test harness builds `Handler` as a struct literal and never
    sets the field, as would any future literal. A zero value that meant "off" would silently ablate the
    gate. `GateOn` is `0` and a test pins it; `Judge` runs the gate for any value other than `GateOff`.
  - **One field, so the label and the behaviour cannot differ.** The parameter is required and first: a
    wrapper that kept the old signature would compile and ignore the switch, and a `bool` at a call site
    cannot be read without the signature.
  - **Parsed first, so a typo cannot burn a run id.** `gateFromEnv` takes `os.LookupEnv`'s shape,
    because `getenv` reads an empty value as unset and `make dev SUPPORT_GATE=` would quietly pick the
    default. The startup line is printed after the field is set and from it, so a forgotten assignment
    would show.
  - **A stale RAG server is not a gap on the off-arm.** The only non-test reader of `retrieved.Texts` is
    the `Judge` call, and the off-arm returns before it. So the off-arm serves the same entries with or
    without a stale server, and rule 10 (which exists because the on-arm's hit rate would describe the
    server) has nothing to check there. This is stated in §H and pinned by a test.
  - **Rule 11 is about the start state, not the arm.** The off-arm writes Tier-2 entries and Tier-1
    promotions that no gate checked, and they outlive the process; a later gate-on process serves them as
    `TIER1_HIT`, which runs no rule. The arm that wrote a foreign entry can never be known, not even with
    P1's manifest. But the start state can be checked from `raw/` alone: every `entry_id` on a hit and
    every `candidate_entry_id` is the `entry_id` of some `MISS` record of the same run (invariant I9).
- **Alternatives:**
  - *A `bool` parameter, or a wrapper keeping the old `Judge`* — rejected: both compile when the switch is
    forgotten.
  - *A minimal run manifest now* — rejected: it is P1's work and fixes the shape of every later run.
  - *Shadow scoring on the off-arm* (compute and log the gate's verdict without enforcing it) — rejected:
    a different measurement, it puts gate code on a path labelled gate-off, and the Done-when says null.
  - *Separate lexical-only and numeric-only modes* — rejected: nothing in the plan needs a third mode, and
    on a gate-on run the two logged values already show what each arm alone would have refused (not
    exactly: a different refusal leaves a different cache behind).
  - *A Redis marker key, or a `SCAN` check at start, to detect a cross-arm cache* — rejected: a marker adds
    schema and breaks "Redis holds only derived state" (ADR-007); a check at start guards the wrong side
    (the false hits come from an **on-arm** process serving off-arm entries) and would block every
    deliberate warm start.
  - *`support_gate` or `refusal_cause` in the HTTP response* — rejected: the arm belongs to the process.
  - *A `CONFIG_ID` cross-check at start* — out of scope: `CONFIG_ID` selects no behaviour yet (F-K).
- **Consequences:**
  - **This supersedes, without editing them:** ADR-009's "always on" and its forward note that 2.4 "adds
    one parameter to `Judge`" (done). The frozen-table row for the refusal cause is **amended in place**
    to the per-arm rule; its own trigger ("after the first run on `v1`") has not happened.
  - **Run identity.** A configuration-4 run is identified by `(config_id, mutation, support_gate)`.
    Configuration 5 is defined with the gate on (invariant I8). `CLAUDE.md:202-203` and
    `Final_Proposal.md:391` still say `(config_id, mutation)`; they are the author's files and are **not
    edited by this entry**, so this entry is the authority until the author edits them.
  - **Every reader of `support_gate` also filters `config_id ∈ {4, 5}`.** Configuration 3 will have no
    gate and will log cause `NONE` with null support fields; labelled `on`, it would break invariant I7's
    on-clause in a healthy run and enter the refusal-rate denominator with zero refusals. What
    configurations 1–3 write is left to the owner of F-K (recommended: `off`).
  - **Joins name their arm.** *Decisions changed by provenance* is the **3 ⋈ 4-off** join (provenance
    alone); 3 ⋈ 4-on mixes provenance with the support gate. A per-request join **between** 4-off and 4-on
    is valid only on the static-cache arm (item 6.3), because online the two caches drift apart. Online, the
    arms are compared in aggregate only.
  - **The price of the gate is read from the gap between the arms' hit rates, and part of that gap is
    ADR-009's `k=1` effect:** a refused entry stays the nearest one and refuses each paraphrase in turn.
    Report the share of `SUPPORT` refusals whose `candidate_entry_id` repeats, next to the gap. The second
    pre-registered null (the gate refuses so much that the hit rate collapses) is read from that gap.
  - **Phase 7** compares μ_hit with the gate on against off **on a probe set the gate admits**, so both arms
    serve the same hits; the arms otherwise differ in hit mix and in the background writes each hit
    triggers (`BumpHitCount` and the Tier-1 promotion), so an unmatched comparison is not the gate's cost
    alone. The gate itself costs about 30 µs per judged candidate (a benchmark, not a measurement of the
    system).
  - **Phase 4** — the completeness run must use the off-arm (or read `dep:*` and `entry:*` directly),
    because the on-arm's numeric check can hide a missed purge (ADR-009); and Phase 4 **defines the cache
    reset** that rule 11 needs once `dep:` and `entry:` exist.
  - **P1's manifest records `SUPPORT_GATE`**, taking the arm from the records or checking that the
    environment and the records agree, never from the environment alone.
  - **Known limits, not fixed:** I9 cannot see old entries that are never touched (it matters only once
    capacity is bounded), and gives a false alarm only when a MISS record never reached the log (F-F: a
    request in flight at SIGTERM can vanish with `Dropped()` at 0). It does **not** give one for a MISS
    leader whose client left: that record still names its entry (corrected after `/ai-review`, which found
    the first wording of this limit false, `docs/work/2026-10-14-support-gate-switch/review.md`);
    `main()` has no test, so "`main.go` assigns the field" is a manual check; the real-answer
    sample of ADR-009 (`τ_s = 0.6` on generated answers) is still open and decides whether the two arms
    differ at all on real answers.
- **Invalidates:** none citable — `experiments/results/` holds only `.gitkeep` and no `requests.jsonl`
  exists. A log from the 2.3 commit `94ed44b` up to the 2.4 commit has `refusal_cause` and no
  `support_gate`: it is **gate-on**. A log from before `94ed44b` has neither key: it had no gate and is
  **neither arm**; never pool it with an off-arm log. No frozen value changes: `τ_s`, the stopword list, the
  tokenizer, the numeric rules and the unit list are untouched.

### ADR-011 — `v1`'s 152 products are drawn by one pre-registered rule, and R2 is a pre-filter, not a label
**Decided (data)** · 2026-10-20 · *`data-card.md` §1, §3 and Schemas; `experiments/scripts/select_pqa.py`, `build_pqa.py` (`MANIFEST_VERSION` 2), `answerability_check.py`; `data/pqa-selection.json`; trail `docs/work/2026-10-19-pqa-thick-tail-selection/`*

`v1`'s products are the output of `make pqa-select`, which reads the 3.1 interim only through
`iter_interim` and applies one rule, committed (`ea63e5d`) before any live run and before ePQA was
fetched. **Questions:** price and stock, then carrier, questions are dropped; warranty and return
questions are tagged `policy`; every other question is `spec`, tagged answerable by **R2**: at least
half of its content tokens (the 2026-10-03 probe's tokenizer) are in the product record, after the
tokens found in ≥ 10 % of the leaf's titles are removed. **Products** are eligible with a title, ≥ 3
bullets, no warranty term in the title or the prose, consistent records (the 78 flagged by
`fields_conflict` are out), 5 – 50 kept questions, ≥ 5 R2-answerable spec questions, and a
near-duplicate pair (Jaccard 0.45 – 0.99) among them. **The draw:** per leaf, rank by
`sha256("v1-item-3.2:" + asin)` and take the quota: 38 per department, split evenly over its leaves,
except that **fallback step 1** was applied after the first live run (TVs had 13 eligible of 19): TVs
13, headphones 25. Result: **152 products and 4,706 pool questions**, consuming the 3.1 manifest
`741d52e3…`. **The reproducibility anchor is the products digest `d373c4b0…`** (the sorted file names and
hashes of the 152 records) with the pool digest `50cdcb03…`; the selection manifest's own sha256 also covers
the selector file and the llama-index-core version, so it moves with them and is not the anchor.
**R2's per-question tag is a pre-filter:** in a model audit of 100 selected questions its precision is 35 %
(21 of 60, Wilson [24, 48]) and its negative predictive value 97.5 % (39 / 40, a single false negative);
against ePQA's human labels its precision is 21 % (4 / 19), its recall 33 % (4 / 12, [14, 61]) and its NPV
93.5 % (116 / 124). Every R2-answerable question that item 3.4 turns into a workload query is labelled again,
and a sample of the R2-unanswerable ones too; spec questions the record cannot answer form a separate
stratum, reported apart and never in the headline. The pool field is named `r2_answerable`, not
`answerable`, for that reason.

- **Rationale:**
  - **The thick tail is required, not chosen:** a uniform draw returns single-question products, from
    which no stratum A or C pair can be built (`data-card.md` §1).
  - **Answerability is required (F17):** a question the record cannot answer gets "not available" as
    its reference, so reuse between two such questions is safe by construction and inflates the safe-hit
    rate of every configuration.
  - **R2 over R1, decided before any data:** R1 passes "How tall is the chair?" on "chair" alone, a
    silent failure that fills every quota. R2's failure (too strict) is loud: a short leaf stops the run.
  - **The copied filters are shown to act like the probe:** the probe's own two pool rules are counted
    on the same pass and pinned, and all twelve numbers reproduce, after `example_product.py` was re-run
    unchanged on the raw leaves (`evidence/probe-pins.md`).
  - **R2 stays for the draw, not for the label:** its "unanswerable" tag is usually right (NPV 97.5 % in
    the model audit, 93.5 % against ePQA), so the draw seldom loses a product to it; with 35 % precision its
    "answerable" tag cannot label a question. The selected products are rich in R2-tagged questions **by
    construction**; how many of those are truly answerable is estimated below, not measured.
- **Alternatives:**
  - *Thickest products first:* pushes products to the 50-question cap and raises `K` (≈ 1.5 h of
    reference generation per 1,000 distinct queries); unrepresentative of the eligible pool.
  - *An LLM label, or hand curation of every question:* hours locally, or PQA text sent to an outside
    API, or a filter coupled to the generator; hand curation cannot be re-run.
  - *Tightening R2 after the audit:* post hoc, in-sample, and it needs a fresh audit; rejected in favour
    of re-labelling at 3.4, where only workload queries need a label.
  - *Keep the first record of the 78:* then not even the number of affected selected products is known.
  - *Fallback step 2 (the pair among all kept questions):* not needed; step 1 filled every quota.
- **Consequences:**
  - ADR-002's filters were "proposed, not frozen; fixed at item 3.2": this fixes them and adds two. Its
    pool sizes describe **the probe's rule only**; the eligible pool is 452.
  - **The audit departs from its pre-registration:** the author had no time and asked Claude to mark the
    100 questions, so it is a model audit, not human-verified, by a marker who wrote R2 and read by a strict
    rule, which flatters the NPV. ePQA's labels (precision 4 / 19 = 21 %, recall 4 / 12, κ 0.17; of the 143
    spec units 93 are phones, 39 TVs or headphones, and only 11 laptops or furniture) agree in direction and
    give the weaker recall.
  - **Expected yield:** at 35 % precision, about **410** (roughly 285 – 560) of the 1,180 R2-answerable pool
    questions are truly answerable, and many selected products will have fewer than 5. It is an input to
    3.4's workload and to `K` at 3.6, where it must be measured, not assumed.
  - **A test was amended** with the fallback: `test_the_quota_is_38_per_department_split_evenly_over_its_leaves`
    now pins `QUOTA_PREREGISTERED`, and a new test pins the applied change. The spec changed (the author
    applied a pre-registered step), not the code under test, and no assertion was weakened; the author
    approved the step, and the amendment was stated in the same turn (task `approvals.md`).
  - **The selection favours long product text:** 2 – 5 chunks per selected product against 1 – 2 for the
    probe's pool. More chunks give containment more gradient, in the headline's direction. It is a
    limitation of C1 and goes into the threats to validity.
  - **One record in the TV probe pool cannot be chunked** (a 1,353-character title makes the metadata
    longer than the 256-token chunk); `make ingest` would fail on it. None is selected, and the selector
    now stops if one ever is.
  - **For 3.4:** read the drafts only through `iter_selection`; re-label every R2-answerable question it
    uses, and a sample of the R2-unanswerable ones; keep the unanswerable stratum; do not label strata with the probe's tokenizer ("Windows 7" and
    "Windows 8" share a token set); only 127 policy questions exist in the pool (92 warranty, 35 return),
    "return key" is mis-tagged as policy, and there is no shipping tag.
- **Invalidates:** none — no runs yet. As an artefact, the 3.1 manifest `bf0feb48…` is replaced by
  `741d52e3…` (`MANIFEST_VERSION` 2: every interim line gains `fields_conflict`).


### ADR-012 — `v1`'s policy corpus is 12 authored documents, one per condition, written to rules fixed before the text
**Decided (data)** · 2026-10-21 · *`data-card.md` §1, §2, Schemas, §7 and Ethics; `experiments/scripts/corpus_gate.py` (G5), `check_policies.py`; `data/policies-v1/`; trail `docs/work/2026-10-20-policy-documents/`*

`v1`'s policy half is **12 documents**, one per (kind, department, condition): returns and warranty
for phones, laptops, electronics and furniture, with **phones returns** (opened / unopened),
**laptops returns** (new / renewed), **furniture returns** (opened / unopened) and **phones
warranty** (domestic / international service) each split into two documents. There is no shipping
document and no global policy. Each record carries, beside `doc_id`, `title`, `category` and `text`,
three fields read **offline only**: `policy_kind`, `condition` and `terms`. The `doc_id` is derived
from them. The writing rules W1–W9, the condition word list and the checker were committed
(`c9a93f6`) **before the first document existed**. The terms come from the best page reached for
each, one retailer or maker per department (three are weak: Consequences), chosen by a rule fixed
before any warranty page was fetched: Best Buy,
Amazon, Target and IKEA for returns; Samsung, HP, Sony and IKEA for warranty. **G5 is
`corpus_gate.check_g5`**: a document may name only the condition it declares, over the word list
`CONDITION_AXES` (`packaging`, `grade`, `region`, `kind`). It is lexical, so **the author's read of
every document is the other half of G5**. The texts were drafted by a model (Claude) from the term
table only; the author read and approved all 12 on 2026-10-21 (P8); the 8 that `/ai-review` then
changed were re-read and approved the same day (task `approvals.md`). **The phones warranty pair is not a minimal pair** (`/ai-review` F3):
"covered" against "not covered" cannot share one text, so W5 is waived for that family by the
author, and each document is written to be true on its own.

- **Rationale:**
  - **Document granularity is required for the namespace to see a condition** (`data-card.md` §7):
    `reuse.Namespace` takes the rank-1 policy chunk's `doc_id`, so a chunk-level split leaves all
    four conjuncts blind.
  - **A both-values rule would miss the natural violation** (design review H1): a domestic warranty
    that says "not valid outside the United States" names one value and still holds two answers.
    So G5 fails any undeclared value, and `kind` is an axis too.
  - **Rules before text**, because the measured residual depends on how the conditions were
    written (`data-card.md` §3). **Siblings are minimal pairs** (the same text, the condition word
    once per section), so which sibling ranks first turns on the condition word, which is what RQ2a
    asks.
  - **No shipping:** the pool has no shipping tag, and shipping has no condition to split.
- **Alternatives:**
  - Siblings worded freely, with only the opening naming the condition: closer to a real page, but
    drafting would then move the result (review H3).
  - Invented warranty terms that differ by department: rejected; nothing is invented. Requirement 2
    then holds only in part (Consequences).
  - Excluding the 10 products whose titles contradict a policy document: rejected by the author,
    because it would reopen ADR-011's frozen selection.
  - G5 as a separate item 3.5, with a second copy of the scan in the checker: rejected; one
    implementation, two callers (the G3 lesson).
- **Consequences:**
  - **The return windows replace ADR-002's "14 / 30 / 30 / 90":** phones 14 (opened: a $45
    restocking fee), laptops 30 / renewed 90, electronics 30, furniture unopened 365 / opened 180.
    The store combines four retailers' policies, one per department.
  - **The laptops region split was dropped** by the pre-registered fallback: HP's warranty "is
    applicable in all countries", so both sides would carry one term. **`data-card.md` §2
    requirement 2 holds only in part:** warranty differs through furniture (10 years) and the phones
    region pair; phones (12 months), laptops and electronics (1 year) share one duration.
  - **The pre-registered maker rule was amended twice by the author, both times before the page it
    selects was fetched:** the Brand field was empty on most products, so the title's first word
    fills it; for electronics the top word ("Bluetooth") is not a maker, so non-maker words are
    skipped (Sony). Sony's TV and headphone terms differ (1 year / 90 days in an old manual); the
    author picked 1 year (W6).
  - **Three sources are weak and flagged:** Amazon (HTTP 503; laptops rest on the 2026-10-03
    reading, and some Renewed items get 30 days plus an 11-month warranty), HP (timeouts; a search
    summary and a 2004 PDF), Sony (blocked; old manuals on third-party sites).
  - **Reading the support gate per pair:** laptops and furniture differ by a number both ways;
    phones returns and phones warranty only one way ("no fee" and "not covered" carry no number,
    and `no` / `not` are stopwords), so in that direction both arms are expected to be blind.
  - **Two kinds only, on evidence:** a keyword probe and a 72-row sample marked by a model at the
    author's request (rule committed first) found about 6 – 10 stable store-policy questions outside
    returns and warranty in the 4,706-question pool ("do you ship to <country>?", buying a
    protection plan); delivery dates, fees and duties are dynamic and bypass the cache. The author
    kept two kinds (`evidence/policy-scope.md`).
  - **The condition fields never reach the hit path.** A condition tag on chunks is the rule term
    `Final_Proposal.md:435` rejected; `test_the_new_fields_never_reach_chunk_metadata` pins that
    `record_to_document` copies only `doc_id`, `kind`, `category`, `title`.
  - **For 3.4:** no policy-lane or stratum-D query names one of the 10 products whose titles say
    Renewed, International Version or No warranty; condition questions will mostly be constructed
    (the pool has none tagged by condition); the grade pair feeds no natural same-product pair.
  - **For 3.6:** assert `data/v1/`'s policy files equal `data/policies-v1/` byte for byte; record a
    digest of (chunk id, chunk-text sha256) and pin `llama-index-core` (0.14.23 at writing); measure
    how often the fresh top-k holds a sibling's term chunk; sweep the lane band on v1 (48 policy
    chunks against dev-v0's 4); freeze the numeric unit list (v1's terms use days, months, years
    and `$`); re-run `make policy-check` at the freeze.
  - **`/ai-review` (2026-10-21) found three text defects after the author's first read:** a
    template placeholder (`For {v} service`) left in both phones warranty documents (F1; the
    checker now fails any `{ } < >`), the international document contradicting its own term
    (F3), and gift / receipt sentences against W7 (F4). The word list was widened after the text
    existed (F2: none of the 12 hit an added word), G5 now fails a corpus with no policy
    documents (F7), and its wiring into the gate is tested (F8).
- **Invalidates:** none — no runs yet. `v1` is not frozen, and `data/dev-v0/` is untouched. As a
  record, ADR-002's return windows are replaced.


### ADR-013 — `v1`'s workload is 1,274 queries written by Claude under rules fixed before the text, split by unit, with `K` per run file
**Decided (data)** · 2026-10-22 · *`data-card.md` §3, §4, §6, §7 and Schemas; `contracts/interfaces.md` §D (v0.15); `experiments/scripts/build_workload.py`, `corpus_gate.py`; `data/workload-manifest.json`; trail `docs/work/2026-10-21-workload-generator/`*

`v1`'s query workload is **1,274 queries** (validation 622, test 652), built by
`experiments/scripts/build_workload.py`. The script uses no model and is deterministic: two builds
gave one manifest sha256, `7ee717a846a2…`. It reads a **model layer** that Claude
(`claude-opus-5-5`) wrote in this session from sheets that a script prepared: which spec questions
the product text answers, one short name per product, the rewrites of the seeds, and the
paraphrases, lookalikes, name swaps, D questions and policy wordings. Claude then labelled every
written spec query again, **blind, without its seed**, and a disagreement drops the query. The
rules (`rules.md`, sha256 `f4035be73a56…`) and every constant were committed (`98c4689`) **before
the first sheet was read**, after a pilot on synthetic text. The split is by whole **units**:
pairs of products for spec queries, and (shape group, department) for policy queries. The four
minimal-pair groups put their two sides in opposite splits. The popularity rank is per record and
stratified. **`K` is the distinct-query count of the file a run draws from**, and a run draws from a
split file: 622 and 652, with capacity `round(0.25 × K)` = 156 and 163. The whole file (1,274; 318)
is the gate's input, not a run file. The gate counts G1 inside
a split, requires G2 inside each split, retrieves scoped by `product_id` as a run does, and hashes
the whole file with its two split files. The 94 queries the record cannot answer ride in the run
files with `answerable: false`: ADR-011's "separate stratum" is read as **"separate population"**.
**The labeller is not the judge:** the Phase 5 judge (item 5.1) is not Claude, and the ~100
human-verified pairs are not Claude-marked.

- **Rationale:**
  - **Redundancy and traps must be made.** PQA has 5 – 14 re-asks per 100 questions and few
    traps (`data-card.md` §3), so Tier 2 needs written paraphrases, and C1 needs written lookalikes
    and condition twins. Qwen is the system under test, so it does not write (the author,
    2026-10-21).
  - **In this session, from scratchpad sheets.** No new dependency, no key, and PQA text never
    enters git. The price is repeatability: a re-run would write new text and so give a new `K`,
    new strata and a new split. So the model layer is hashed into the manifest and written once.
  - **Units, because a random split of clusters would separate a probe from its target.** Then no
    run would hold the trap. A product-free policy unit also stops the same question about two
    products reaching both splits. Each split holds at least 30 minimal-pair twins (56 and 80).
  - **`K` per file, because a run draws from one file.** A capacity taken from the whole file
    would be about twice too large for a split run (318 against 156 or 163). The whole file is not a
    run file at all: its popularity ranks restart at the split boundary, so `ask.js` would put 17 %,
    6.4 % and 1.6 % of its traffic on test records at skews 0.8, 1.1 and 1.4.
  - **G1 within split and G2 per split** (stricter than the table in `data-card.md` §7), because a
    pair across the splits is never in one run.
  - **Unanswerable queries stay in the run files** because shoppers ask them, so the cache should
    see them. They are reported apart by their own `answerable`.
- **Alternatives:**
  - The API path: adds a dependency and a key, and is no more repeatable. Both paths send PQA text
    to Anthropic.
  - Qwen as the writer: rejected by the author.
  - A split by seed-question cluster alone (`Final_Proposal.md:454`): rejected; a product-pair unit
    is a union of whole clusters, so no cluster crosses, which is what that line asks.
  - Rank per cluster, a sixth stratum for unanswerable queries, and unanswerable queries in runs of
    their own: all proposed and not taken (`design.md` §10).
- **Consequences:**
  - **The counts** (`evidence/build.md`): strata A 761, B-within 272, C 150, D 69, B-cross 22;
    94 unanswerable; 136 minimal-pair twins; trap fraction 0.2229 (validation 0.2074, test 0.2377).
    Pass 1 gave a yield of 448 (R2 precision 0.362, NPV 0.869; the repeat agreed on 38 of 40), so
    pass 2 had **214 answerable spec seeds, not the ~304 the design expected**. The blind check
    then dropped 16 spec seeds, 5 unanswerable seeds, 17 lookalikes, 2 paraphrases, 10 natural pairs
    and 47 name swaps (the partner's record cannot answer), plus what went with a dropped seed.
  - **Thin where C1 and RQ2 need it.** B-cross has 22 records (12 `name-swap`, 10 `name-swap-same`).
    Natural B-within traps are 10 of 272, and none of the 163 policy ones. All 16
    `condition-department` records are in validation, so the test split reads RQ2a from
    `policy-condition` (80) alone. Intervals on these will be wide.
  - **PQA text went to Anthropic** through the Claude session, in the sheets. The author accepted
    the path at the experiment approval (2026-10-21). Anthropic's own terms for that use were not
    checked in this item. Nothing derived is tracked: the three workload files and the model layer
    are gitignored, and `data/workload-manifest.json` holds hashes and counts only.
  - **Claude is on both sides: it wrote the policies (ADR-012) and the workload.** A habit of the
    writer is shared by both, and a cache that matches the writer's phrasing would look better than
    it is. The controls: the rules before the text; built policy questions start from real pool
    wording (`origin: pqa-template`); R10, no shared 4-token sequence with any policy text beyond
    the name, the term and the condition word; the headline reported by `origin` as a pre-registered
    row (A3); the blind check; the 30-row read; and a judge that is not Claude.
  - **Two of those controls are weaker than the plan meant.** The blind check ran in a new context
    window but is the same model, so it is not an independent labeller. **The 30-row read was done
    by Claude at the author's instruction, not by the author** (0 of 30 broke their rule; 1 was
    not a shopper's question). It cannot show that Claude's reading of a rule is wrong. The author
    can mark the same sheet later; if 3 or more break, the stop rule applies as written. The
    labelling conventions of pass 1 and of the check round (for example, a worldwide claim makes a
    country question answerable, a hedged one does not) were applied by Claude and were not checked
    by anyone else.
  - **The reject counts of the import measure little.** Rows went through a read-only pre-check
    first, so the import rejected 1 of 1,097 write rows and none of 1,028 check rows. The drop
    counts above are the measure.
  - **Found at the `/ai-review` of 2026-10-22 (trail `review.md`, F1 – F10), and recorded here:**
    - **Not every trap can fire.** Only 182 of the 284 traps have a cosine of at least 0.85 with
      their partner: the reachable fraction is 0.143 (validation 0.119, test 0.166) against the
      trap fraction 0.2229. None of the 22 B-cross probes reaches 0.85 (the highest is 0.804);
      23 of 99 lookalikes, 4 of 10 natural traps and 1 of 9 `policy-kind` probes do; all 154
      condition and region twins do. B-cross is labelled by construction, not measured as A and C
      are. The analysis reads results by the logged pair similarity (`rules.md` A1) and reports
      the reachable fraction beside the trap fraction (`evidence/partner-cosine.md`). The twin
      floor of 30 counts records: validation has 56 (28 pairs), test 80 (40 pairs).
    - **Natural pairs are rewrites.** The 64 natural-pair queries were rewritten to name their
      product (R3); none equals the pool text. The 30-row read left them out on the wrong belief that
      they are real text, so none of the 64 (including the 10 natural traps) was read.
    - **The model id is nominal.** `claude-opus-5-5` in `batches.md` and the manifest is the
      importer's default and was never checked against the model that wrote a batch. `make
      workload-import MODEL=<id>` now records a real one. "Written by `claude-opus-5-5`" above means
      "recorded as".
    - **Cross-split near-duplicates on policy documents:** 74 pairs of policy-cell queries and 8
      pairs with a D query are on one policy document in different splits at cosine ≥ 0.85. The
      policy unit keeps one cell in one split, not the different shapes of one document, and not D.
    - **`pqa-template` covers 22 name swaps** (spec wording re-targeted) as well as 72 policy
      queries, so the A3 row "origin in pqa, pqa-template" includes the B-cross probes.
    - **`workload-verify` now recomputes** the counts of each file and compares the current input
      hashes with the manifest; before, it re-hashed only the outputs.
    - **The contract sentence was narrowed:** `interfaces.md` v0.15 says a run draws from one of the
      two split files (the approved wording also allowed the whole file). `CLAUDE.md` still gives the
      single-`K` meaning ("the frozen workload's distinct-query count"); it is the author's to edit.
  - **Carried forward** (`design.md` §11): to 3.6, the digest over three files, `K` for each file,
    G1 and G2 per split on the ingested `v1` (scoped, with unscoped beside), and per-probe retrieval
    checks; to 5.1 and 5.2, the judge rule and the rubric for a wrong-product answer; to 6.1 and
    6.3, the analysis rules A1 – A4 in `rules.md`; to 7.2, the probe file for `mu_hit.js`; to P1,
    the run names its run file and sets `CACHE_CAPACITY` from that file's `K`. The comment at
    `gateway/cmd/gateway/main.go:267-268` still gives the old meaning of `K`; P1 changes the
    comment with the wiring. `ask.js` is unchanged.
  - **Binds forward.** After 3.6, changing the rank seed, the split unit or its seed, the A / C
    rule, the model layer or the "`K` per run file" rule needs a new `dataset_version`. Undoing the
    labeller-is-not-the-judge rule needs a later ADR that says why one model may do both.
- **Invalidates:** none — no runs yet. `experiments/results/` holds only `.gitkeep`, and
  `data/dev-v0/` is untouched. As a record, ADR-011's "separate stratum" for unanswerable queries is
  replaced by "separate population", and `interfaces.md` §D's definition of `K` changes (v0.15).

---

### ADR-014 — `v1` freezes with G1 recorded as failed: 21 pairs against a floor of 50, kept as a corpus finding that bounds C1
**Decided (data)** · 2026-10-23 · *`data-card.md` §7; `Final_Proposal.md` lines 436, 438, 497, 499; `experiments/scripts/corpus_gate.py`, `freeze_corpus.py`, `Makefile`, `verify_admission.sh`; trail `docs/work/2026-10-22-g1-finding/`; item 3.6 (`docs/work/2026-10-22-corpus-freeze/`)*

The first gate run on the ingested `v1` failed **G1**: **21** pairs inside a split (13 validation,
8 test) against a floor of **50**. G1's rule, its threshold (cosine ≥ 0.85, Jaccard ≤ 0.2, at least
50), its pair definition and this result are **kept exactly as they are**. `v1` is frozen **with G1
recorded as FAILED**. The gate keeps `passed: false`, the freeze record carries `known_failures`,
and the failure is reported as a **corpus finding that bounds C1's applicability**, which is what
`Final_Proposal.md:497` says to do. A narrow, opt-in allowance in the gate and the freeze tool
makes this possible, and nothing else.

**This is a fourth option.** Item 3.6's stop rule S1 named three next steps "and no other": (1)
accept the failure as the result and report it; (2) reopen item 3.3 or 3.4; (3) change the gate
statistic. Freezing with the failure on record is none of them. The author chose it on 2026-10-23,
**after seeing the number 21**. The proposal's row was written before; the choice between this and
a rework was made after.

- **Rationale:**
  - **The proposal pre-registered this case.** The falsifier row "The corpus itself"
    (`Final_Proposal.md:497`): *"The corpus gate cannot pass **G1** (enough qualifying pairs) or
    **G2** (any within-product pair) even after the structural requirements of the `v1` corpus
    model and the B-within / B-cross split are met. Thresholds in `data-card.md` §7"* — response:
    *"The phenomenon is genuinely thin in this domain. Reported as a **corpus finding** that bounds
    C1's applicability — not engineered around with further corpus manipulation"*. Line 499:
    *"**No success criterion is redefined after seeing results.** If a threshold above is missed,
    the row's right-hand column is what gets written."* Both structural requirements are met: all
    12 policy documents are 4 chunks (≥ 3), and B-within and B-cross are built.
  - **The authority conflict is named, and settled.** Line 438 says *"`data-card.md` §7 is the
    authority for the procedure, the thresholds, and the failure actions"* and *"the standing
    instruction on any failure is **fix the corpus, not the rule**"*. §7 says the same
    (`data-card.md:306`: *"Fix the corpus, not the rule — add categories, differentiate policy
    windows per category, re-run"*; `:327`: *"Fix the corpus, re-run all five. Do not proceed to
    ingestion"*). Line 438 is the general instruction. Line 497 is the specific case, written for
    this exact failure, and line 499 says its right-hand column "is what gets written". The
    specific case governs. §7 is still the authority for the thresholds, and none of them moves.
  - **The shortfall has three parts, and the ADR does not call all of it structural.**
    - *Products: structural.* Retrieval is scoped to a product and a product has about 3 chunks, so
      two questions about one product share chunks (J = 1). Only questions about *different*
      products can have J ≤ 0.2. All 24 such pairs at cosine ≥ 0.85 come from **5 product pairs**.
      If every one of the 39 pairs (21 + 18 across the splits) sat inside a split the total would be
      39, still below 50 (`evidence/l2-feasibility.md`). Choosing partners by name similarity has no
      support in the data: the 36 most similar short names contain none of the 5 productive pairs.
    - *Policy: a choice.* Most chunks shared by the reachable twin pairs are policy chunks (81 of
      127 in validation, 106 of 188 in test; the design review's count, `review.md` finding 2).
      The author controls those documents. The gate's own advice, "lengthen policy documents"
      (`corpus_gate.py:823-825`; `data-card.md:306`), was **never tried**. It is **declined**, after
      the count was seen, because ADR-012 writes sibling twins as minimal pairs (rule W5, waived only
      for the phones warranty pair) and because line 497 says not to engineer around the finding.
    - *The 50: no derivation.* `data-card.md:306` writes "≥ ~50" and nothing derives it. That is a
      weakness of the criterion, and it is a reason to report the failure with its caveats, not to
      change the criterion after seeing 21.
  - **A passing G1 by redefinition would carry a claim the data cannot back.** Line 436 says G1
    *"requires enough high-similarity / low-overlap pairs to detect a signal at all"*. An existence
    check ("at least one") would read that as something it does not say.
  - **Memory-scale correction, in this task.** See "The memory scale" below. This ADR says "run 1
    stands" because of it, so it cannot wait for a later task.
- **Alternatives:**
  - **S1 (1) alone, nothing frozen.** Rejected: the later phases need a frozen corpus, and line 497
    says the finding is *reported*, not that work stops.
  - **S1 (2), reopen 3.3 or 3.4.** A workload lever (more cross-product look-alikes) has no support
    in the data (above). Longer policy documents are declined (above).
  - **S1 (3), change the gate statistic** (rule R2: an existence check), **or lower the 50.**
    Rejected: it moves the line that 497 names and 499 forbids, after the result was seen.
  - **Run the reachable-trap count through a power calculation.** Rejected: the proposal counts the
    false-hit rate over hits (`:408`), dropped sample-size planning (`:79`), and expects the RQ2a
    residual to be non-zero (`:412`). A zero-error yardstick would start from the wrong premise.
- **The facts** (item 3.6's run 1; all 53 memory readings were `1`, the normal level, so the run
  stands; counts only, no file name, asin or qa_id):
  - **G1: 21 inside a split (13 + 8)**, plus 18 across the splits (not gated), 1,342 pairs at
    cosine ≥ 0.85 in all, floor 50. **Not met.**
  - **G2: B-within 3 in each split** (validation: 1 built trap + 2 paraphrase pairs; test: 2 built
    traps + 1 coincidence). Met, thinly. S5 was not raised. G3, G4, G5, `W`, `S`: met. 539 chunks,
    164 documents, 1,274 queries.
  - **Reachable traps** (a probe with a partner whose kind is a trap kind, not `name-swap-same`, and
    whose cosine to the partner is ≥ 0.85; 3.4's definition, `partner_cosine.py:72`). **As records:
    74 of 129 in validation, 108 of 155 in test, 182 of 284** (ADR-013 has the split by kind: 23 of
    99 lookalikes, 4 of 10 natural traps, 1 of 9 policy-kind, all 154 condition and region twins,
    none of the 22 B-cross). **As unique pairs** (146 of the 284 records are mutual twins that name
    each other): **45 in validation, 67 in test** — the design review's count; Block C of the trail
    reproduces it with the gate's function before the code is accepted.
  - **No sample size and no power claim stands beside these numbers.**
- **How C1 is read, in both directions** *(proposed text, **not yet accepted by the author**; it
  is the author's wording in the end, and it is fixed before any C1 run)*. A null result is
  reported as "no difference resolvable on a corpus where the phenomenon is thin, at these
  counts", never as "the rule fails" and never as "the corpus is at fault". A positive result is
  reported with the trap counts (records and unique pairs) and Wilson intervals, never as "enough
  traps". Neither reading is changed after the first C1 run.
- **What the finding bounds, and what it does not show.** It bounds C1: the phenomenon is present
  in `v1` but thin, so the comparison of the reuse rule with the best fixed threshold can be
  resolved only as finely as those counts allow, and its intervals must be reported. It does **not**
  show that the rule works or that it fails, that `v1` is a bad corpus, that 50 is the right number,
  or that a corpus with longer policy documents would not pass.
- **The mechanism and its limits** (built in this task, after this ADR is committed):
  - `corpus_gate.py --accept-failed G1`. Nothing is accepted by default. Only `G1` is a legal value,
    only for `dataset_version v1`, and **only when the snapshot digest equals the pinned
    constant** below. If any corpus or workload file changes, the allowance stops working and a new
    decision is needed. With it, a run where G1 is the only failed criterion and no flag (S3, S4,
    S5) is raised prints the digest under "FREEZE WITH A RECORDED FAILURE (G1, ADR-014)", exits
    with code **3**, and writes `passed: false`, `freezable: true`, `accepted_failures: ["G1"]`.
    Without the flag, behaviour is today's.
  - `freeze_corpus.py freeze` accepts a report only if its failed criteria **equal** a non-empty
    `accepted_failures` set `{G1}`, its digest equals the pin, and **both runs** accept the same
    set. The freeze record gets `known_failures` (criterion, ADR, counts, floor).
  - The gate reports the reachable traps per split and probe kind, as records and as unique pairs,
    "reported, not gated".
  - **Pinned snapshot digest** (164 corpus files and 3 workload files):
    `a5708fefa62cec0aef5505e9e5242bc04bf351fd02a2efb5da54a98f211bb2e4`. Run 1 printed its first 12
    characters, `a5708fefa62c`. **Run 1's files**, copied on 2026-10-23 to
    `data/v1-draft/gate/first-run/` (gitignored), sha256: `report.json`
    `c1ad09eeb2b6ac8cd0cc9d07dbe5d022d473a0486bc27bb927c71c05fe2ff039`;
    `retrieval-validation.json`
    `1e2e17357c456c296e0b01a9178013e0f3ff523cc23135fead3306910da7bc57`; `retrieval-test.json`
    `7a90de70423cf89ec46ef041a7c640395324bec09e679631f5c6314a8c7ced5f`.
  - Item 3.6's two runs write to **new folders**, never `run1/`, and are compared by hand with the
    preserved copy: 21 = 13 + 8, 18 across, 1,342 pairs. Any other count stops the work.
- **The memory scale.** On macOS `kern.memorystatus_vm_pressure_level` is **1 = normal (green), 2 =
  warn, 4 = critical**; the SDK header defines `DISPATCH_MEMORYPRESSURE_NORMAL 0x01`, `_WARN 0x02`,
  `_CRITICAL 0x04`. The machine read `1` with 47 % free, and the Activity Monitor graph was green
  at that reading. The repository's rule "`0` = green" (`CLAUDE.md:44`, `README.md:227`, the
  `Makefile`, `corpus_gate.py`, `freeze_corpus.py`, `verify_admission.sh`) is wrong, and it was
  stricter than needed, never looser: it could not accept the level the sensor reports as normal.
  Run 1 therefore stands, and item 3.6's records that called it "yellow" are corrected. From Block
  A0 of this task, `1` is green, held in one named constant. The test edits that follow are the
  numbers only (green `0 → 1`, the old yellow `1 → 2`) and are made only after the author confirms
  the list. `CLAUDE.md` and `README.md` are the author's to correct.
- **Consequences:**
  - **Phase 3's exit line cannot be met as written** ("G1…G5 all pass"). *Proposed wording, not yet
    accepted by the author; the author edits `docs/super-plan.md`, which `.claude/hooks/lib.sh`
    reads:* "G2…G5 pass, G1 is recorded as ADR-014's finding with its counts, and `make
    gate-corpus` prints the snapshot digest under a recorded failure · `K`, the derived capacity
    and every frozen corpus statistic are recorded in `data-card.md` · the validation/test splits
    are frozen with the dataset."
  - **Item 3.6 reopens** after this task: its S1 text, A3 (ii), A5 and the lines that say "G1 ≥ 50
    must pass" change; its two runs use `ACCEPT_FAILED=G1`; `data-card.md` §7 (including line
    258, "refuses to print a snapshot hash unless all five…", which becomes false) gets the status
    paragraph; its freeze ADR is **ADR-015**.
  - **The thesis text on C1's applicability** is the author's and the supervisor's.
  - **Has the supervisor seen this?** *Not recorded yet.* Whether they see it before the first C1
    run is the author's decision; this line is updated when that is known.
  - **Binds forward.** After the freeze, changing G1, the 50, the pair definition or the allowance's
    files needs a new ADR. A reader must never take the pinned digest as a pass: the banner,
    exit code 3, `known_failures`, `passed: false` and this ADR all say it is not.
- **Invalidates:** none — no runs yet. `experiments/results/` holds only `.gitkeep`, and Redis
  holds `dev-v0` and no cache key. It changes how item 3.6's first gate result is read (a finding,
  not a stop for rework) and which numbers 3.6's trail cites. It replaces no corpus file, no
  workload file and no digest input: the pinned digest is the digest of the files as they stand.

---

### ADR-015 — `v1` is frozen: 164 corpus files and 3 workload files, with G1 recorded as failed
**Decided (data)** · 2026-10-23 · *`data/v1-freeze.json`; `data-card.md` §1, §7; `experiments/scripts/freeze_corpus.py`, `corpus_gate.py`; trail `docs/work/2026-10-23-corpus-freeze-run/` (item 3.6, second part)*

`v1` is frozen on 2026-10-23: **152 product and 12 policy documents (164 files), the whole workload file and its two split files (167 files in
all)**, snapshot digest `a5708fefa62cec0aef5505e9e5242bc04bf351fd02a2efb5da54a98f211bb2e4`, **539 chunks** (chunk digest `6eea2238…b9bb3`),
`K` = **622** (validation) and **652** (test) with cache capacity `round(0.25 × K)` = **156** and **163**. The stack is `nomic-embed-text`
(digest `0a109f42…e59f`, Ollama 0.33.2), FLAT / COSINE / 768 dimensions / `top_k` 5, chunks 256 / 40; the record holds the full values.
It was frozen **with G1 recorded as FAILED** (ADR-014): 21 pairs inside a split (13 validation, 8 test) against a floor of 50. The gate reports
`passed: false`, `data/v1-freeze.json` lists the failure under `known_failures`, and this is **not a pass**. Two gate runs from fresh ingests
(`ACCEPT_FAILED=G1`, commit `a09b48d`, 53 memory readings each, all `1`) agree on every count and digest, and the first run, taken before the
allowance existed, agrees with them: the two retrieval exports are byte-identical to the first run's (`evidence/run-a.md`, `run-b.md`).

- **What it binds.** After this freeze, changing a corpus or workload file, the rank seed, the split unit or its seed, the A / C rule, the model
  layer, the "`K` per run file" rule, the 3.1 skip rules (first parsed record wins; lone surrogates replaced and counted; non-strings counted, not
  coerced), the chunking, `top_k`, the embedding model or the retrieval config needs a **new `dataset_version`** and an ADR. `make corpus-verify`
  checks the files, chunks, model and config against the record. **Redis holds `dev-v0` after this item**, so every `v1` run starts with
  `DATASET_VERSION=v1 make ingest` and `make corpus-index-check`.
- **Rationale.** Phase 4 onward (the update set, the judge, every run) needs a fixed corpus, and nothing is measured on an unfrozen one. The
  proposal pre-registered the response to a G1 failure (`Final_Proposal.md:497`): report it, do not engineer around it. ADR-014 has the reasons.
- **Alternatives.** Wait for the supervisor before freezing: not taken, because a freeze is cheap to supersede (a `v2` is a new `dataset_version`,
  not an edit of `v1`) and the supervisor can still decide it before Phase 4 and before any C1 run. Build a `v2` now (more products, longer
  policy documents): not in this item; it would redo items 3.2, 3.4 and 3.6, and it is a decision for the author and the supervisor. If it is taken,
  it needs its own ADR that says why, keeps `v1`'s finding in the thesis, and applies the same G1 threshold of 50 (the allowance of ADR-014 is pinned
  to `v1`'s digest and does not carry over).
- **Consequences.**
  - **Carried measurements, recorded and not acted on** (counts; `2026-10-22-corpus-freeze/evidence/probe-checks.md`). Evidence spans located: 777,
    of which 94 lie over more than one chunk. The seed's evidence chunk is in the scoped top-k for 75 of 101 validation seeds (all chunks: 68) and 66
    of 97 test seeds (61). Policy queries (158, validation): `policy_frac` is 0.8 for 99 of them; with the default collapsed lane band
    (Lo = Hi = 0.20) 156 are POLICY, 2 SPEC and **none MIXED**, and the candidate band [0.20, 0.60) would make 9 MIXED; of 33 D queries, 27 are POLICY
    and 6 SPEC under the default band; of 431 product-only queries, 428 are SPEC. Twins (validation): 51 of 56 hold both twin documents in the top-k.
    Units: of 13 policy terms, 11 are read by a listed unit, 1 by a currency symbol and 1 has no number, so **no unit is missing** from the
    gateway's list. The lane band is a gateway constant and stays as it is; a change is a task of its own.
  - **The corpus bounds C1** as ADR-014 says. The reachable traps are 74 / 129 (validation), 108 / 155 (test) and 182 / 284 as records, and 45, 67
    and 112 of 211 as unique pairs; no sample size stands beside them.
  - **Claude is on both sides.** Claude wrote the policy documents (ADR-012) and the workload (ADR-013). The controls of ADR-013 carry over: rules
    before text, R10, the headline by `origin`, the blind check, the 30-row read, and a judge that is not Claude. Two of them are weaker than the
    plan meant (the blind check is the same model; the 30-row read was done by Claude), as ADR-013 says.
  - **There is no restore path for `data/v1/`** (it has no git). `freeze_corpus.py assemble` rebuilds it from the gitignored drafts byte for byte
    (checked on 2026-10-23 into a scratch directory), but a `--restore` command is not built. It is carried to Phase 4, with `data/v1-draft/`.
  - **The memory scale.** Green is the sensor level `1`: the Activity Monitor graph was green at 1 and yellow at 2 on this machine
    (`evidence/memory-scale.md`), as the SDK header says. `GREEN_LEVEL` in `corpus_gate.py` holds it (ADR-014).
  - **The Phase 3 exit line** was amended on 2026-10-23, at the author's instruction to close the phase, to the wording ADR-014 proposed.
- **Invalidates:** none — no runs yet. `experiments/results/` holds only `.gitkeep`. Item 3.6's first gate run stands as ADR-014's finding.
