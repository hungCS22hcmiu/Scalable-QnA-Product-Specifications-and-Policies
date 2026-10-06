# Spec — loadgen-footprint (item 1.6)

**Scope:** L · **Opened:** 2026-10-06 · **Phase:** 1, the last open exit clause
**Revisions:** v1 → **v2 (2026-10-06)** after `impact.md` and `review.md`. v2 corrects a false premise about
`Final_Proposal.md` §7, replaces a vacuous acceptance check, fixes the ADR's claims about `h*` and about
what Phase 7 inherits, and adds the decisions numbered 10–12.

## The change, in one sentence

Measure what a co-hosted k6 costs the machine (CPU and memory at the rates the sweep will offer, with the
SUT's memory state sampled alongside), then record that number and the co-hosted-measurement decision as
**ADR-001**.

## What it serves

- **Phase 1, item 1.6** (`docs/super-plan.md`). The exit clause it closes: *"the load generator's
  footprint is measured and the co-hosted-measurement decision is recorded as ADR-001."*
- **Discharges** S1, S2 (`measurement validity`), per the item's row.
- **Requirements:** `docs/contracts/requirements.md` is still a skeleton, so no `FR/NFR/RR` is cited. The
  nearest is the *Measuring without a second machine* section, which says in as many words that this
  decision "needs its own entry in `decisions.md`".

## Why this item exists

`Final_Proposal.md` §7 (`:336`, `:345`) and §9.4 (`:460`) **already say load generation is co-hosted** and
name ADR-001 as the record of that decision, so the repository currently cites an ADR that does not exist.
Meanwhile `experiments/k6/README.md`, `ask.js`, `mu_hit.js`, two `Makefile` banners and
`experiments/README.md` still say a co-hosted generator makes a run **invalid** (impact.md §3). No second
machine exists and none is dated, so the contradiction has to be settled on the record. (An earlier draft
of this spec attributed the "invalid" wording to the proposal; impact analysis showed that was wrong.)
`super-plan.md` argues the claim survives anyway, because S1 is an inequality and co-hosting only *lowers*
μ_hit, which makes a co-hosted μ_hit a lower bound. That argument rests on one empirical premise the plan
leaves open: **that at the rates the sweep offers (≲ 16 req/s), k6 costs little enough to leave the SUT's
headroom intact.** 1.6 measures that premise, and ADR-001 states what follows from it **and what does not**
(`review.md` findings 1–2: the lower-bound argument holds for the μ_hit leg only, and CPU share is not an
interference measurement).

## Acceptance — each is a check that can be run

1. **The sampler is itself tested** (standing constraint 6: no measurement runs off an untested
   instrument). `make test` includes `experiments/tests/test_loadgen_footprint.py`, which drives the
   sampler against real children whose CPU the child **reports about itself**, a ~3 % duty burner (the
   regime k6 is in at 2 req/s), a block of **incompressible** known size, a child that **exits 99**
   mid-sample, an injected exception that must leave **no orphan**, and a `SIGTERM`; plus pure tests of the
   `cputime` parser (including `43:57.34`, which a `HH:MM:SS` parser reads 60× wrong) and of `summarise`.
   Tolerances are **relative ±25 %**, sized to the ≥ 2× failure modes and deliberately not tight so the test
   does not flake under pressure (design.md §8). The tests are written **before** the recorded run.
2. **A footprint table exists** in this trail's `evidence/`, for each offered rate in the grid and for the
   mixed row, **labelled with its regime** (all-hit smoke set, or mixed): k6's steady-state mean CPU
   (% of one core and of the 8-core machine), p95 and max over 1 s and over 5 s windows, peak RSS
   (`ru_maxrss`) and `phys_footprint`, `vus_max`; the **slope and intercept** of CPU against achieved rate;
   achieved rate and `dropped_iterations`; the tier mix, shed count, k6's exit status and `error_rate`; the
   SUT's raw memory readings per second plus swap and page **rates** per row; the SUT's total CPU; and the
   **sampler's own overhead** beside k6's. A row carrying any exclusion flag is left out of the table and
   listed separately. The raw per-second samples sit beside the table so it is regenerable from them
   (`loadgen_footprint.py summarize`), not the reverse.
3. **ADR-001 is written** in `docs/decisions.md` in the file's own template, including an **`Invalidates:`**
   line, and contains: the per-quantity bias table; the corrected `h*` argument; the statement that the
   footprint **does not** satisfy Phase 7's interference clause, with the two candidate methods assigned to
   7.1; the pre-registered go/no-go rule and its outcome; the evidence by path; the raw zone readings; and
   the statement that the figure is **indicative unconditionally** and the run **exploratory** under
   standing constraint 4. The Summary row and the two "reserved / not yet written" notices are updated and
   `decisions.md:71` gains "(ADR-001)".
4. **Statements the ADR contradicts are reconciled** (the list is impact.md §3): `experiments/k6/README.md`,
   the headers of `ask.js` **and `mu_hit.js`**, the `make load-smoke` / `make mu-hit` banners, and
   `experiments/README.md:6` either point at ADR-001 or are corrected. `interfaces.md:164` is a contract
   surface and is **not edited**; the ADR records it as **a lost measurement**. `Final_Proposal.md` is
   **not** edited and needs no edit for co-hosting; the divergence the ADR records for the advisor is
   **pressure gating** (§7 `:343`, §9.4 `:461` against decision 4).
5. **`make verify` is green** and the **off-box wording is gone**: this grep returns only lines that cite
   ADR-001 or record history (`make check` is not used — it prints and always exits 0, so it cannot fail):
   `grep -rniE 'off-box|second machine|<sut-ip>|co-hosted run is invalid' Makefile experiments README.md CLAUDE.md docs/*.md docs/contracts`
6. **The sampler has a Makefile target** (`make footprint`, in `.PHONY` and `make help`), because
   `Makefile:2` and CLAUDE.md forbid ad-hoc invocations.
7. **`super-plan.md` item 1.6 is marked done**, its sentence *"needs green memory pressure"* (`:121`) is
   corrected to match decision 4, and Phase 1's progress line reads 6 of 6 — the phase's exit criterion then
   passes by the same by-hand checks that were run to open this task.

## Decisions taken in this spec, and the ones left to the author

| # | Question | Default taken | Why | Author confirms |
| :-: | :--- | :--- | :--- | :---: |
| 1 | Workload driven at k6 | **The built-in 5-question smoke set** in `ask.js` (all-hit after warm-up), plus the mixed row (decision 10); nothing from `data/` | `v1` does not exist (Phase 3); `dev-v0` is not citable in any result; k6's own CPU is a function of rate, VUs and response, not of question content — **reasoned, and checked by the mixed row** | ☐ |
| 2 | Offered-rate grid | **2, 8, 16, 32 req/s**, 60 s each (steady-state window = the middle 50 s), **3 repetitions**, `VUS = 40`, after a warm-up pass | The sweep's grid is item 7.1's. This brackets it: 16 is the plan's λ_max at the best reachable `h`, and S1 is about finding saturation so the sweep must offer past it. `VUS` is pinned because k6's RSS is set by VU allocation and is flat by construction otherwise | ☐ |
| 3 | Are the models loaded | **Yes**, via `make dev` (both resident, ~2.1 GB), asserted by `ollama ps` before every row | The pressure zone "alongside" means nothing for an SUT that is not in the state it will be in during the sweep | decided 2026-10-06 |
| 4 | Is memory pressure a gate | **No — recorded, never gating.** The run is classified **exploratory** under standing constraint 4 and ADR-001 calls the figure **indicative unconditionally** (not "indicative unless green") | Author's instruction 2026-10-06: development, not a benchmark. The zone cannot be classified anyway while the sysctl's encoding is unverified (design.md U8) | decided 2026-10-06 |
| 5 | Where the evidence lives | **`docs/work/<this task>/evidence/`** (tracked): the table, the per-second CSVs, derived counts. **Not** `experiments/results/` | `raw/` is gitignored (ADR-005), so an ADR citing it would cite something an examiner cannot open; and a `RUN_ID` run there would leave a manifest-less "run" that a future `results/*/raw/` glob takes in, which write-once forbids deleting | ☐ |
| 6 | F-L (`rag.server` keeps generating after cancel) | **Not fixed before 1.6** | An orphan adds no memory (ADR-003) so it cannot move k6's CPU; F-A's review recommends gating Phase 7 on it, not 1.6 | ☐ |
| 7 | The gateway's own eval log during the run | **`RUN_ID` set** with an **absolute `RESULTS_DIR` outside both trees and not Spotlight-indexed** (the session scratchpad under `/private/tmp`); only the line count and sha256 are committed | The log writer and answer store are part of the SUT's load. A relative `RESULTS_DIR` lands silently under `gateway/` after `make dev`'s `cd` | ☐ |
| 8 | `interfaces.md:164` | **Not edited; recorded in ADR-001 as a lost measurement** | A contract surface: editing it triggers the contract phase and a v0.13 bump | ☐ |
| 9 | Flushing the cache at the end | **`make demo-reset` at the end only, and it needs the author's explicit go-ahead.** There is **no** reset at the start | It FLUSHALLs Redis and runs `git checkout -- data/`, which destroys uncommitted corpus edits (tree was clean at open). If declined, a fallback deletes the cache key prefixes with the gateway down and verifies zero, with no `git checkout`. The first denial of a Bash call in this session involved `data/` | ☐ |
| 10 | **A mixed-workload row** (8 req/s × 3 reps; the 5 smoke questions + 300 uniquely suffixed variants, seeded, Zipf; generated into the trail; no `ask.js` edit; nothing from `data/`) | **Included, default on**; costs ≈ 4–5 min | The all-hit run leaves Ollama idle and never exercises Tier-2, misses or sheds, so on its own the table describes "k6's per-request cost, all-hit", not "footprint at the sweep's rates". The author may drop it, in which case the ADR labels the table all-hit only | ☐ |
| 11 | A p95 **headroom threshold** | **None.** Every co-hosted p95 is reported with k6's concurrent CPU from the same run | A threshold fixed after seeing the table is a choice of which rates' p95 become citable. This is the plan's own no-parameter option (`super-plan.md:419`) | ☐ |
| 12 | **Go/no-go values A and B** (k6 steady-state mean CPU at the top attained rate, % of one core; peak `phys_footprint`, MB) | **Blank — the author sets them in `approvals.md` before the recorded run** | Without a rule fixed first, no result could change the decision and the exit clause passes whatever the number is (`review.md` finding 3). I have no basis for the values and will not invent them | ☐ **required** |

**Phases required** (`approvals.md`): impact · experiment · implementation. Not contract.

## Out of scope

- **A "with and without k6" interference comparison.** It is not runnable: without a load generator there is
  no load. Phase 7's interference clause is **not** satisfied by this item (the footprint is CPU share, not
  contention); two candidate methods — a matched-burner test and a no-generator μ_gen measurement — are
  named in ADR-001 and **assigned to item 7.1 to design**.
- **The μ_hit probe regime** (`mu_hit.js` at ~400 req/s, the run that drove pressure to *urgent* on
  2026-09-06). `super-plan.md` is explicit that it is a different regime from the sweep. ADR-001 records it
  as **not rescued**, citing the 2026-09-06 observation, and does not re-measure it here.
- **Any threshold, tuning, or frozen value.** No τ, θ, δ, model, slot count or capacity changes.
- **Fixing F-L, F-F, F-M, F-N, F-O**, the `ABANDONED`/`GENERATION_FAILED` interpretation work, and the
  ADR-006 `⟦PENDING⟧` 1 ms threshold. Where a footprint run produces such records they are counted and
  reported, labelled **vacuous for an all-hit workload, not settled**.
- **The encoding of `kern.memorystatus_vm_pressure_level`.** The repository says `0` is green; the reviewer
  recalls XNU returning 1 / 2 / 4 and the live reading fits that. If it is right, `make measure`'s `!= 0`
  gate can never pass, which would block Phase 7. That is **outside 1.6**; it is reported to the author and
  the sampler records the raw integer so nothing here depends on the answer.
- **Editing `interfaces.md`, `Final_Proposal.md` or `CLAUDE.md`**, and **`mu_hit.js`'s verdict logic**
  (`:244` prints `mu_hit ~= X` as a ceiling, which co-hosted it cannot be; item 7.2's). This item edits
  `mu_hit.js`'s *header comment* and nothing else in it.
- **A run manifest** (open question P1). The footprint is not one of the thesis runs, so it carries no
  `manifest.yaml`. It does record the gateway git SHA, a `gateway`/`rag`-only dirty flag, k6 version and
  machine state beside the table, so the first real manifest has a precedent rather than a gap.
- **`libproc` via `ctypes`.** It would remove the exec cost and the 1 cs quantisation, but its CPU times are
  in Mach ticks on Apple Silicon (a silent ~41.7× error). Phase 7 may revisit it.
- **Any new dependency.** The sampler uses `ps`, `sysctl`, `vm_stat`, `footprint` and `memory_pressure`
  (no arguments), which ship with macOS; no PyPI package.
