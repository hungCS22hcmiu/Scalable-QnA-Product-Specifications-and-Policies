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
| ADR-002 | `v1` draws from six Amazon-PQA leaves mapped onto four departments | in force | none — no runs yet |
| ADR-003 | The generation envelope serves one slot; the admission pool bounds queueing, not memory | in force | no `run_id`; relabels μ_gen as a one-slot planning figure; voids the spike grid's `NUM_PARALLEL` axis |
| ADR-004 | The unfiltered Tier-2 phase is retired in code | in force | none — no runs yet; logs written before the 1.3 commit carry the old meanings under the same keys |
| ADR-005 | Served answer text is stored content-addressed in `raw/answers/` | in force | none — no runs yet; a log written before the 1.5 commit has no answer store and cannot be judged |
| ADR-006 | `t_generate_ms` means "this request's own `Answer` call was attempted" | in force (one open item: the 1 ms threshold) | none — no runs yet; ABANDONED and GENERATION_FAILED records' `t_generate_ms` is null before the F-H commit and not comparable across it, and any derived overhead is not either |

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
| Load generation | **co-hosted**, reported as such (**ratified by ADR-001**) | No second machine exists. The capacity claim is stated as a lower bound rather than a ceiling — see `super-plan.md`, "Measuring without a second machine" |

## Open questions carried into the thesis phase

| # | Question | Blocks |
| :--- | :--- | :--- |
| **F1** — ✅ **resolved by ADR-003, 2026-10-04** | Ollama overrides `OLLAMA_NUM_PARALLEL` to `-np 1` for this model. If the permit pool bounds to a concurrency the model server never offers, every shed rate measured so far describes the harness rather than the gateway | ~~No admission-control number is citable until this resolves.~~ Resolved: one slot frozen, one permit, `make env-check` verifies the live runner. Phase 1, item 1.1 |
| **P1** | The run-manifest schema, the frozen judge prompt, the operational metric definitions and the pre-registration record were deleted with the old protocol document and exist nowhere — not in the proposal, not in code. `experiments/k6/ask.js` still prints values "for manifest.yaml" | Phases 5, 6 and 7 all produce artefacts with no defined shape |

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
