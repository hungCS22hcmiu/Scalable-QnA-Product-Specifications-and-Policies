# Impact — loadgen-footprint (item 1.6)

Produced by the `impact-analyst` subagent on 2026-10-06, then checked by the author-side session. Claims
the session re-verified are marked **✔ verified**; the rest are the analyst's, with the file:line it gave,
and are marked **(analyst)**. Nothing here was acted on before the sections below were read.

## Verdict

**No frozen value is touched and no prior run is invalidated: `none — no runs yet`.**
Checked: `experiments/results/` holds only `.gitkeep`; every ADR in `decisions.md`'s Summary says "no runs
yet"; a grep for `k6`, `co-host`, `footprint`, `61 req/s`, `0.9969`, `2026-09-06` finds no recorded k6
footprint number anywhere (only this trail). **Required phases:** impact · experiment · implementation.
`contract` is **not** required unless `interfaces.md:164` is edited, which this task will not do.

## Corrections this analysis forced on the spec

1. **`Final_Proposal.md` §7 does not say co-hosting is invalid.** ✔ verified. §7 `:336`, `:345` and §9.4
   `:460` already say load generation is co-hosted and name **ADR-001 (item 1.6)** as the record that does
   not yet exist. The spec's "Why this item exists" and acceptance 4 had read the k6 README's wording as if
   it were the proposal's. The statements that say co-hosting is invalid live in `experiments/k6/README.md`,
   `ask.js`, `mu_hit.js`, the Makefile banners and `experiments/README.md` (§3 below), not in the proposal.
2. **The real divergence from the proposal is about pressure, not co-hosting.** ✔ verified. §7 `:343` and
   §9.4 `:461` make leaving green a run-validity gate (*discarded and repeated*). The author decided on
   2026-10-06 that this development-stage characterisation is not gated. That is compatible only if the
   figure is labelled **indicative** and the p95 headroom criterion is later taken from a green
   re-measurement. ADR-001 must say so in terms. Separately, `super-plan.md:121` says 1.6 *"needs green
   memory pressure"*: that sentence contradicts spec decision 4 and is fixed when the item is marked done.
3. **`make check` cannot fail.** ✔ verified: every grep ends `|| echo clean`; it prints and exits 0. It
   checks three phrase families plus `git status`, nothing about ADR numbering, the Summary table or
   off-box text. Acceptance 5's "`make check` is green" is vacuous and is replaced.

## 1. Packages and boundaries (analyst)

| Path | Change | Boundary |
| :--- | :--- | :--- |
| `experiments/scripts/loadgen_footprint.py` (new) | sampler + k6 driver, stdlib only | OK — `architecture.md:65`, `:122` place the measurement protocol here |
| `experiments/tests/test_loadgen_footprint.py` (new) | self-test | OK — `conftest.py:4-7` puts `scripts/` on `sys.path` |
| `experiments/k6/ask.js` | header comment `:1-8` only | no functional edit needed (§8.10) |
| `experiments/k6/mu_hit.js` | header `:1-6`, stale `:1` | **missing from the spec's list; added** |
| `experiments/k6/README.md`, `experiments/README.md:6` | reconcile off-box text | `experiments/README.md` **missing from the spec's list; added** |
| `Makefile` | banners `:350-355`, `:379-385`; a new sampler target; `.PHONY` `:38` | the sampler needs a target (`Makefile:2`, CLAUDE.md "no ad-hoc invocations") |
| `docs/decisions.md` | `:43`, `:71`, `:84-85` | — |
| `docs/super-plan.md` | `:118-121`, `:130`, `:206-216` | — |
| `docs/work/<task>/evidence/` (new) | footprint table + raw samples | — |
| `gateway/`, `rag/`, `contracts/`, `docs/contracts/interfaces.md` | **untouched** | `interfaces.md:164` is stale, see §3 |

The only layering rules (`architecture.md` §2) cover gateway packages; for `experiments/` the convention is
that all five existing scripts are stdlib-only. **The sampler must not `import rag`**: the package is pip
`-e` installed, so the import would succeed silently and pull `rag.config` and LlamaIndex into the
instrument's resident set. The sampler talks only to `:8080` and the process table.

## 2. Frozen values and prior runs (analyst)

- **Frozen values touched: none.** Checked `num_ctx`, `OLLAMA_NUM_PARALLEL`, embedding model, `DIM`,
  `top_k`, chunking, FLAT, eviction, capacity, δ, `dataset_version`. ADR required: **only ADR-001 itself**.
- **ADR-001 ratifies, it does not change a value.** `decisions.md:71` already lists "Load generation |
  co-hosted, reported as such" as inherited frozen state. Add "(ADR-001)" to that row, as `:63` does for
  ADR-003. What ADR-001 *supersedes* is prose in the repository.
- **Prior numbers to relabel, not void.** The 2026-09-06 μ_hit probes (Tier-1 ≈ 8000, Tier-2 ≈ 61 req/s;
  `super-plan.md:55`, `:400-411`; `decisions.md:352`, `:424`) were taken co-hosted on `dev-v0` with no
  `run_id`, so they were never citable. ADR-001 labels Tier-1 ≈ 8000 **not rescued** (a ceiling, taken at
  *urgent* pressure) and Tier-2 ≈ 61 a planning lower bound only.
- **ADR-006's first-`RUN_ID` condition** is satisfied if the run is taken from HEAD (`17bf221` is the F-H
  commit).

## 3. Every statement that says co-hosted is invalid / off-box / second machine (analyst)

**Must change (contradict ADR-001):**

- `experiments/k6/README.md`: `:8-12` ("A co-hosted run is **invalid**"), `:15-16` and `:58-59`
  ("on the SECOND machine", `<sut-ip>`), `:22-23`, `:29` (`GATEWAY_URL` default "invalid for
  measurement"), `:91-93`; and `:6`, which calls `mu_hit.js` "Phase 1's exit criterion" (stale: μ_hit is
  item 7.2).
- `experiments/k6/ask.js:3-8`. (`:180-181`, green-or-invalid, agrees with proposal §7 `:343` and stays.)
- `experiments/k6/mu_hit.js`: `:1` (stale "Phase 1 exit criterion"), `:3-6` (cites proposal §7 for a rule §7
  no longer contains); `:244` prints `mu_hit ~= X` as a ceiling, and co-hosted its `dropped_iterations > 0`
  test cannot distinguish target saturation from k6 starving itself — **7.2's to fix, ADR-001 names it**.
- `Makefile` `:353` ("from a second machine") and `:381-384` (`<sut-ip>`).
- `experiments/README.md:6` ("load scenarios (W8+, run off-box)").
- `docs/contracts/interfaces.md:164` ("the eval also records off-box end-to-end separately"). A contract
  surface: editing it pulls in the contract phase and a v0.13 bump. **Decision: not edited; recorded in
  ADR-001 as stale wording.**

**Already consistent:** `README.md:115`, `CLAUDE.md:162-167`, `decisions.md:71`,
`super-plan.md:364-372` and `:392-427`, nothing under `.claude/`.

## 4. Dependencies (analyst; tool presence ✔ partly verified)

None added. `ps`, `top`, `footprint`, `memory_pressure`, `sysctl`, `vm_stat` ship with macOS; k6 v1.7.1 is
installed (✔ verified, `k6 version`; `footprint` and `top` present ✔ verified). Quirks that shape the sampler:

- **`footprint -p` works without root on same-user, non-child processes** (verified by the analyst on
  `ollama serve` and `redis-server`) but costs **20-30 ms CPU per call**. At 1 Hz across ~5 SUT processes
  that can exceed k6's own CPU at 2-8 req/s. **Keep it out of the 1 Hz loop.**
- **`memory_pressure` is safe only with no arguments.** With `-l`, `-p` or a `<pages>` argument it allocates
  memory and waits; `-S` simulates a notification. Its "free percentage" equals `kern.memorystatus_level`
  — **not an independent reading**.
- **`ps -o cputime=` prints `MMM:SS.ss` with no hour field** (`redis-server` shows `43:57.34`). A parser
  assuming `HH:MM:SS` misreads long-lived SUT processes by 60× with no error. Resolution is 1 cs, so
  per-second p95/max at 2 req/s are quantised to about ±1 % of a core.
- `top -pid -l 2` needs two samples (the first CPU column is 0) and took ~2 s.

## 5. Contract, measurement, and leftover state (analyst)

- **Contract:** none, unless `interfaces.md:164` is edited. **Measurement:** yes — a new instrument and a
  new admissibility rule for co-hosted numbers; the experiment phase is required. No §H field or gateway
  path changes.
- **`RUN_ID` / `RESULTS_DIR`:** `make dev` passes `RUN_ID` through. `RESULTS_DIR` defaults to the absolute
  `$(PWD)/experiments/results` (`Makefile:149`); because of `cd $(GATEWAY)` a **relative** `RESULTS_DIR`
  lands silently under `gateway/`. `telemetry.Open` creates `<dir>/<run>/raw/requests.jsonl` with `O_EXCL`
  and `answers/` with `Mkdir` (`evallog.go:127-146`); a reused id makes the gateway refuse to start
  (`main.go:257-259`).
- **Pollution hazard.** A `RUN_ID` run under `experiments/results/` leaves a run directory with no
  `manifest.yaml` (invalid, `architecture.md:68`), whose `raw/` is gitignored so `git status` never shows
  it. A future glob over `results/*/raw/` (the 5.4 figure generators, a P1 verifier) would take it in, and
  the write-once rule forbids deleting it. **Decision: set an absolute `RESULTS_DIR` outside both trees
  and commit only derived counts (line count, sha256).**
- **Cache state.** Redis was **already warm** at analysis time (`t1:4`, `t2:3`). `make demo-reset`
  FLUSHALLs and re-ingests `dev-v0` (`:195-196`), asserts `t1 = t2 = 0` and `corpus > 0`, **refuses to run
  while the gateway is up** (`:166-173`), and runs **`git checkout -- data/`** on modified tracked corpus
  files (`:183-188`). Run it before *and* after. It flushes all 16 DBs though its guard scans db0 only
  (`:175`); only db0 has keys today.

## 6. Dropped scope

None involved (`Final_Proposal.md:599`, CLAUDE.md "Do not reintroduce cut scope"). Removing the need for a
second machine is not scale-out.

## 7. What `make check` and `make verify` check

`make check`: vacuous (above). `make verify` is gofmt/vet/ruff over `rag experiments`, build, then pytest
over `experiments/tests`. The real risk is a **flaky self-test**: at pressure level 2, `ps rss` of a freshly
allocated block can read low through compression. Wide tolerances, a few seconds, and prefer `ru_maxrss`.
"Tests are immutable" plus the one-fix rule turns a flaky test into a standing tax.

## 8. Other blast radius, silent paths first (analyst)

1. **The models unload mid-run.** `~/.ollama/logs/server.log` shows an `OLLAMA_KEEP_ALIVE` setting
   (the analyst read `5m0s`; the session saw the setting present but not its value) and ✔ **no
   `keep_alive` appears anywhere in `rag/src` or `gateway/`**. After the warm-up the smoke set is all
   Tier-1 hits (Tier-2 hits are promoted, `handler.go:320`); Tier-1 never calls Ollama, so ~5 min into a
   ~14-minute schedule both models unload, freeing ~2.1 GB, improving the zone reading and silently voiding
   spec decision 3. **Re-warm both models and check `ollama ps` before each row.**
2. **`ps rss` understates under pressure**: at level 2 with 6.0 GB swap used the analyst measured
   `redis-server` RSS 1,952 KB against `phys_footprint` 11 MB (5.6×). Cite `phys_footprint`, or state RSS is
   a floor.
3. **k6's RSS is set by its VU allocation, not the rate.** `ask.js:99-100` preallocates `VUS` (default 20,
   to 80). An all-hit run needs ~1 VU, so the RSS column is flat by construction. Pin `VUS` and record
   `vus_max`.
4. **SUT PIDs mis-resolve:** `pgrep -f redis-stack-server` returns the bash wrapper (64 KB), not
   `redis-server`; `pgrep -x ollama` returns `ollama serve` (27 MB), not the `llama-server` runners that
   hold the models. Assert process names or select runners by parent, as `env_check.py` does.
5. **The h\* lower bound leaks through μ_gen.** h\* = μ_hit/(μ_gen+μ_hit) *falls* as μ_gen rises. If μ_gen
   is itself measured co-hosted (7.5), co-hosting can depress it and push h\* up — anti-conservative. The
   claim survives on ADR-003's margin: h\* reaches 0.988 only at μ_gen ≈ 0.74 req/s (✔ arithmetic checked:
   61·(1/0.988 − 1) = 0.741), ≈ 3.9× the 0.19 projection. **ADR-001 must state this**, not only
   "monotone in μ_hit".
6. **The plan contradicts itself on pressure** (`super-plan.md:121` vs spec decision 4); the machine reads
   level 2, so the table will be **indicative**; the Phase 7 p95 headroom criterion must come from a green
   re-measurement, not from this table.
7. **Orphaned processes.** A burner left behind by an interrupted test, or a k6 left behind by a sampler
   crash, contaminates every later measurement with no error. Self-terminating burners, children in their
   own session, kill the group in a `finally`.
8. **This run cannot settle what `super-plan.md:207-214` expects of it.** All-hit traffic gives
   `ABANDONED` = 0 and nothing reaches k6's 120 s timeout: report those as **vacuous, not settled**. Also
   F-F: stop k6 before stopping `make dev`, and record the gateway's exit verdict (`main.go:315-321`).
9. **The dirty flag will mislead.** Uncommitted sampler and doc edits mark the tree dirty. Record a
   separate `git diff --quiet -- gateway rag` so the first manifest precedent describes the SUT.
10. **Smallest change:** `ask.js` needs no functional edit — k6 v1.7.1's `--summary-export` works beside a
    custom `handleSummary` (analyst-verified: exports `iterations`, `vus_max`, custom metrics;
    `dropped_iterations` appears only when non-zero, so default it to 0). Leave `interfaces.md:164`
    unedited. Skip the U6 high-rate row and any CLAUDE.md edit. Do not commit the gateway log.

## Risks ranked

1. Models unload after Ollama's idle `keep_alive`, silently changing the SUT state mid-run.
2. ADR-001 would record a non-existent §7 divergence while the real one (pressure gating) goes unrecorded.
3. RSS understates under pressure; the RSS column is flat by construction through `VUS`.
4. A `RUN_ID` run under `experiments/results/` leaves a manifest-less "run" that future globs take in.
5. The h\* lower bound ignores co-hosted depression of μ_gen (safe only by ADR-003's 3.9× margin).
6. SUT PIDs resolve to the wrapper or server instead of `redis-server` and the runners.
7. Acceptance 5 is vacuous.
8. The self-test is flaky under pressure, or leaves an orphaned burner.
9. `mu_hit.js`, `experiments/README.md:6`, `interfaces.md:164` missing from the reconcile list.
