# Design — loadgen-footprint (item 1.6)

Scope L. Written before any code. Read with `spec.md`; the unknowns are in §7 and are the point of this
document.

**Revisions.** v1 (2026-10-06) → **v2 (2026-10-06)** after `impact.md` and `review.md`. v2 changes: the
mean is taken over a stated steady-state window and the Popen/`wait4` mechanics are specified (§2–§3); the
instrument's own cost is reported (§2); the runbook drops the start-of-run reset, re-resolves PIDs and
asserts the refresh is a MISS (§4); a mixed-workload row is added (§4); the self-test is specified (§8);
ADR-001's outline is rewritten around a per-quantity bias table, a pre-registered go/no-go rule and a
corrected h\* argument (§9).

## Amendments found while implementing (v2.1, 2026-10-06)

The shakedown (`evidence/shakedown-notes.md`) found four things in the approved design. Each is a mechanism
change that keeps its intent; they **supersede** the lines named, and are recorded in `approvals.md`.

1. **The refresh (§4, F10) no longer sends a question through the gateway.** It sends the request
   `make env-check` uses to load the frozen envelope (`/api/generate` with `options.num_ctx`, no prompt,
   and `/api/embed`). The "novel question must be a MISS" version cannot work: every such question is the
   same template, so the first is cached and the rest Tier-2-hit it, refreshing the embedder and never the
   LLM. The service passes the same `options.num_ctx`, so the runner asked for is the same. The guards
   stay: `ollama ps` must list both models with the LLM at `num_ctx`, and the runner PIDs are re-resolved
   and compared every row.
2. **Warm-up first, then PID resolution (§4).** The runners do not exist until the warm-up loads the models.
3. **SUT processes are sampled every 5th tick** (`--sut-every`), not every tick (§2). One `ps` over ~9 pids
   cost ~25 ms against ~3 ms for one, which made the sampler's own cost ~3× k6's (F17). k6 and the memory
   sysctls stay at 1 Hz. The sampler's overhead is still reported beside k6's, and is still the same order
   as k6 at 8 req/s.
4. **A cold cache at the start of `run` and before every mixed repetition (§4).** The mixed workload is
   seeded, so without a flush a second repetition finds the whole workload cached by the first and the
   repetitions are not samples of one regime. `flush_cache` deletes only `t1: t2: dep: entry: lru:`, never
   `corpus:`, verifies the result, and leaves the `idx:cache` index alone (unlike `FLUSHALL`). This
   **replaces** §4's "there is no `make demo-reset` at the start": that line was right for the all-hit rows
   only. A prefix-only delete is the "fallback" of spec decision 9; `make demo-reset` is not used.

## 1. What is being built

Four things, in dependency order:

1. **`experiments/scripts/loadgen_footprint.py`** — a stdlib-only sampler/driver with three subcommands:
   `run` (drive k6 and sample), `summarize` (regenerate the table from the per-second CSVs, so the table is
   derived from the samples and never the reverse), and `make-workload` (a seeded generator for the mixed
   row, §4). `run` wraps **any** k6 invocation, so Phase 7 can run its sweep under the same sampler and
   report k6's concurrent CPU beside every p95 (§9).
2. **`experiments/tests/test_loadgen_footprint.py`** — proves the sampler reads known loads correctly
   (acceptance 1). Written **before** the recorded run, and before the driver.
3. **`make footprint`** — the Makefile target (`.PHONY`, `make help`), because `Makefile:2` and CLAUDE.md
   forbid ad-hoc invocations.
4. **ADR-001** in `docs/decisions.md`, built from the table, plus the reconciling doc edits (impact.md §3).

Nothing in `gateway/`, `rag/`, `contracts/` or `docs/contracts/` changes. The sampler imports nothing from
either service — in particular **never `import rag`**: the package is pip-`-e` installed so the import would
succeed silently and pull LlamaIndex into the instrument's own resident set.

## 2. The measurement

k6 is a child of the sampler. That gives two independent readings of the same quantity, each used for what
it is good at:

| Quantity | Source | Why this one |
| :--- | :--- | :--- |
| **k6 CPU, steady-state mean** | Δ cumulative `cputime` ÷ Δ wall, over the **steady-state window**, from the per-second samples | The window excludes k6's start-up (it preallocates VU runtimes) and teardown (summary computation, export), which are a fixed cost and not the rate's |
| k6 CPU, **total** | `os.wait4` → `ru_utime + ru_stime` | Exact. Used for three things only: the total, a sanity check, and the start-up + teardown figure |
| k6 **peak RSS** | `ru_maxrss` from the same `wait4` (**bytes** on macOS — U3) | Exact peak; `ps rss` is a floor under pressure |
| k6 CPU **shape** (p95, max over time) | per-second `cputime` deltas | The only source of a distribution |
| Marginal cost per request | **slope** `b` of `cpu% = a + b · achieved_rate` over the 12 (rate, rep) points | Total ÷ N is biased: at 2 req/s (~120 requests) the fixed start-up cost per request can exceed the marginal one, so CPU-per-request would *fall* with rate. The intercept `a` is reported as the fixed cost |

**The steady-state window is fixed in advance: the sampled ticks excluding the first 5 s and the last 5 s of
the 60 s scenario** (so 50 s). It is not adjusted after seeing the data.

**Checks, with tolerances stated now:**

- `rusage_total ≥` the last sampled cumulative CPU. A violation means the sampler read something that is not
  k6 and is an **instrument error**: the row is excluded.
- `rusage_total − (sampled window CPU)` is reported as *start-up + teardown*. It is **not** a pass/fail
  check, because a systematic gap is expected and a tolerance on it would either always fire or be widened
  after the fact.
- A per-tick `cputime` delta that is negative (non-monotone) or taken while the process is a zombie (`STAT`
  starts with `Z`) is **discarded**, not clamped.

**CPU is not read from `ps %cpu`.** On macOS that column is a decaying average, not a rate over the interval
(U1). The sampler differences cumulative CPU time (`ps -o cputime=`, 1 cs resolution) between ticks and
divides by the measured wall time between those same two `ps` calls, not by the nominal 1.000 s.

**Per-second p95 and max are labelled quantised** (±1 cs ≈ ±1 % of a core per sample) and prone to aliasing
with k6's own 1 s metric flush; they are also reported over **5 s windows**. Neither is used for a decision.

### Per-tick record (1 Hz, matching 7.1's "pressure sampled at ≥ 1 Hz")

One `ps -o pid=,stat=,rss=,cputime= -p <all pids>` call and one `sysctl -n` call per tick.

| Field | Source | Note |
| :--- | :--- | :--- |
| `t` | monotonic clock | seconds since the k6 child started |
| `k6_cpu_pct` | `cputime` delta | % of **one** core (100 = one core; can exceed 100) |
| `k6_rss_kb` | `ps rss` | A floor under pressure (the analyst saw 1,952 KB RSS against 11 MB `phys_footprint`, 5.6×) |
| `vm_pressure_level` | `sysctl kern.memorystatus_vm_pressure_level` | **Raw integer, never translated** (U8) |
| `memstatus_level` | `sysctl kern.memorystatus_level` | The figure `make dev` already gates on; **the same quantity as `memory_pressure`'s "free %"**, not an independent reading |
| `swap_used_mb` | `sysctl vm.swapusage` | |
| per SUT process: `cpu_pct`, `rss_kb` | the same `ps` call | gateway, `rag.server`, the Ollama runner(s), `redis-server` |

Per **row**, once: `vm_stat` swap-in / swap-out / page-in / page-out counters at the start and end (so
"this row swapped" is a **rate**, not a level — pressure biases CPU upward through page-ins and
decompression); `footprint -p <k6>` **twice** (t ≈ 10 s and ≈ 50 s; each call costs 20–30 ms CPU, which at
2 req/s is a measurable share of what is measured, so it is never in the 1 Hz loop) and `footprint` on each
SUT process at the start and end of the row; `ollama ps` before and after; `OLLAMA_KEEP_ALIVE` as read from
the server log (U12); the top-5 CPU processes before and after; the git SHA and **two** dirty flags — the
whole tree and `git diff --quiet -- gateway rag`, so the header describes the SUT, not the sampler being
edited; k6 version; `hw.ncpu` and the P/E split. `memory_pressure` is invoked **once with no arguments** at
each end of the run and never in the loop (with `-l`, `-p` or a page count it allocates memory and waits).

### The instrument's own cost, reported per row

`sampler_overhead = (RUSAGE_SELF + RUSAGE_CHILDREN delta over the row) − k6's wait4 rusage`, in % of one
core, printed **beside** k6's CPU. It is stdlib and exact (RUSAGE_CHILDREN includes the reaped `ps`/`sysctl`/
`footprint` children). A sampler whose cost is the same order as the thing measured, unreported, is not
defensible; at 2 req/s it may be. (`libproc` via `ctypes` would remove the exec cost, the 1 cs
quantisation and U2 together, but `ri_user_time` is in Mach ticks on Apple Silicon — a silent ~41.7× error
— so it is **not adopted** for this item; Phase 7 may revisit it if the overhead column says it matters.)

### Derived per row (all repetitions of one offered rate)

- k6 CPU: steady-state mean, p95 and max, as **% of one core and % of the 8-core machine** (the 4 P + 4 E
  asymmetry makes "% of machine" a coarse divisor and the table says so).
- k6 peak RSS (`ru_maxrss`), `phys_footprint` at the two probes, `vus_max`.
- The slope `b`, intercept `a`, and their spread, across the grid (reported once, not per row).
- **Achieved rate and `dropped_iterations`** against the offered rate; achieved < 95 % of offered marks the
  row **unattained** (its footprint is that of a lower rate, F2).
- The tier mix `TIER1 / TIER2 / MISS`, the shed count, `error_rate`, k6's exit status, and the
  `ABANDONED` / `GENERATION_FAILED` counts — the last two labelled **vacuous for an all-hit workload, not
  settled** (F14).
- The SUT's raw zone readings (min / max of each field), swap/page deltas, the SUT's total CPU (so k6's
  share is stated against its neighbours), and the sampler overhead.
- The spread across repetitions (min–max), not a point. **A row carrying any exclusion flag is left out of
  the table and listed separately**; it is not annotated and kept.

## 3. The process mechanics (every one a silent failure if wrong)

- **Exit status comes from `wait4`'s status** (`os.waitstatus_to_exitcode`). The sampler **never** calls
  `Popen.wait`, `poll` or `communicate`: after the sampler reaps k6 itself, CPython's `Popen` hits `ECHILD`
  and sets `returncode = 0`, so `ask.js`'s `error_rate < 0.01` threshold (exit 99) would be lost. (Believed
  from the CPython source, not run: the self-test and probe confirm it.)
- **k6's stdout and stderr go to files, never `PIPE`.** A `PIPE` with no reader stalls k6 at ~64 KB, which
  reads as low CPU and a lower achieved rate that the 95 % flag may not catch.
- **Each tick calls `wait4(pid, WNOHANG)` before `ps`.** While k6 is alive `wait4` returns zeroed rusage,
  and the loop must never leave holding that value; once it reports the child gone the tick is discarded
  (k6 can exit between `wait4` and `ps`).
- **k6 starts in its own session** (`start_new_session=True`). The sampler installs `SIGTERM`/`SIGHUP`
  handlers that raise, so a `finally` kills the k6 process group; it refuses to start if a `k6` process
  already exists. Self-test burners are bounded in runtime and killed the same way (F13).
- **All-hit rows require** exit status 0, `error_rate = 0`, no 503s, `MISS = 0` in the window, and
  achieved ≥ 95 % of offered. Non-200 responses are **not** counted as MISS, so `MISS = 0` alone holds on a
  run full of errors.

## 4. Sequence of a recorded run

```
operator                sampler                    k6 (child)         SUT (make dev)
   │  RUN_ID=footprint-<date> RESULTS_DIR=<absolute, outside both trees, not Spotlight-indexed> make dev
   │                                                                     ▶ redis, rag.server, gateway
   │  (RUN_ID set, so the gateway runs in its sweep configuration: log writer + answer store on)
   │  make footprint RATES=2,8,16,32 DURATION=60 REPS=3 MIXED=1
   │─────────────────────────▶│
   │                          │ resolve SUT pids — by port where possible (:8080 gateway, :50051 rag.server,
   │                          │   :6379 Redis) and the runner by parent + blob as env_check.py does; ASSERT
   │                          │   every pid is present (ps -p silently drops a missing one); header
   │                          │ WARM-UP: one sequential pass of the 5 smoke questions, each must be 200
   │                          │ ── all-hit rows ───────────────────────────────────────────────────────────
   │                          │ for rate in grid, rep in 1..3:
   │                          │    re-resolve PIDs, assert unchanged (a changed runner PID is a silent
   │                          │      model reload, F10)
   │                          │    REFRESH: one NOVEL question through the gateway; it MUST return
   │                          │      cache == "MISS" (a unique-looking question can Tier-2 hit and so
   │                          │      refresh only the embedder); retry with a new nonce ≤ 3×, else abort the
   │                          │      row. Then `ollama ps` must list BOTH models. Outside the window.
   │                          │    Popen k6 run ask.js -e RATE_RPS=… -e VUS=40 --summary-export … (own session)
   │                          │                                            ─────▶│ constant-arrival-rate ──▶ gateway
   │                          │    1 Hz: sample k6 + machine + SUT; wait4(WNOHANG) first each tick
   │                          │    wait4 returns → rusage, exit status; parse the summary (U4)
   │                          │    ≈10 s cool-down
   │                          │ ── mixed row (MIXED=1) ─────────────────────────────────────────────────────
   │                          │ make-workload: the 5 smoke questions + 300 uniquely suffixed variants, seeded
   │                          │ 8 req/s × 3 reps, Zipf as ask.js already does. MISS > 0, TIER2 > 0 and sheds
   │                          │   are EXPECTED here, so the all-hit assertions do not apply; exit status 0 and
   │                          │   the achieved rate still do. Run LAST: it fills both tiers.
   │                          │ ollama ps (after); vm_stat; write samples-*.csv, summary.json, footprint.md
   │  stop k6 BEFORE the gateway (F-F), record the gateway's exit verdict, then stop `make dev`
   │  FLUSH both tiers (make demo-reset — needs the author's OK; else the no-checkout fallback in plan.md)
```

**There is no `make demo-reset` at the start.** The warm-up turns the smoke set into hits regardless, so a
start-of-run reset buys nothing and doubles the exposure of decision 9 (spec). The end flush stays: the smoke
questions must not survive into a later real run (F7).

**Gating.** None on memory pressure (spec decision 4). The sampler *records* the zone; the run is
**exploratory** under standing constraint 4 and ADR-001 calls the figure **indicative unconditionally** (§9).
`make dev` keeps its own gate (`kern.memorystatus_level ≥ 25`), which exists so the models load without
swapping and is unrelated to benchmark validity.

**Why the refresh goes through the gateway and not straight to Ollama.** A direct request that merely touches
a model would be the obvious way to reset its idle timer, but the repo's own calls pass explicit options
(`num_ctx`, `think: false`), and Ollama reloads a runner whose options differ from the loaded one. A
hand-built ping with different options could silently reload the generation model at a different `num_ctx`,
which is the frozen envelope. That mechanism is unverified; it is reason enough to use the one path already
known to match the frozen options.

## 5. Function contracts (the sampler)

```
parse_cputime(s) -> float                 # "0:01.23" "43:57.34" "225:43.35" "1:02:03.04"; unknown format RAISES
sample_ps(pids) -> {pid: (stat, rss_kb, cpu_seconds)}   # one call; a missing pid is an error, not a gap
sample_machine() -> {level, memstatus_level, swap_used_mb}   # raw integers, never mapped
window_mean(samples, trim_head=5, trim_tail=5) -> float # Δcpu_seconds/Δwall over the window, % of one core
run_k6(rate, duration, vus, env, workload) -> RunResult # samples[], rusage, exit_status, k6_summary, flags[]
summarise(runs, ncpu) -> Table                          # pure; no I/O; excludes flagged rows; fits a + b·rate
```

`parse_cputime`, `window_mean` and `summarise` are pure, so they are tested on synthetic inputs with
hand-computed answers; process-level behaviour is tested against real children of known load (§8).

## 6. Failure modes — silent ones first

| # | Failure | What it does | Guard |
| :-: | :--- | :--- | :--- |
| F1 | Sampler watches the wrong PID (a wrapper, not k6) | Reads a near-zero footprint with no error | Launch `k6` directly via `Popen`, not through a shell; assert the process name; `rusage_total ≥ sampled` is the backstop |
| F2 | k6 cannot sustain the offered rate (VUs exhausted) | The row is labelled "16 req/s" but is the cost of ~9 | Achieved rate and `dropped_iterations` (default 0 when absent); **unattained** below 95 % → row excluded |
| F3 | CPU units: % of one core vs % of the machine | A 3× error that reads as headroom | Both reported, labelled; the self-test fixes what 100 means |
| F4 | RSS units: `ru_maxrss` is bytes on macOS, KB on Linux | A 1024× error | The self-test allocates a known block and asserts the reported size |
| F5 | The smoke set is all hits; the real mix has Tier-2 hits and ~1.2 % misses holding VUs open | Understates k6's in-flight connections, RSS and the SUT's work | **The regime is labelled** on every table and in the ADR; the mixed row exercises Tier-2, misses and sheds at one rate. Invariance of k6's per-request CPU across the two is **reasoned, not assumed**: the mixed row is the check |
| F6 | A generation in flight (warm-up miss, unexpected MISS) during the window | Inflates SUT CPU and the zone reading | Sequential warm-up that must return 200; MISS > 0 in an all-hit row excludes it |
| F7 | The run leaves smoke/variant entries in both cache tiers and files under `<RESULTS_DIR>/<RUN_ID>/` | A later real run inherits a warm cache of non-corpus questions, biasing hit rate | End flush; throwaway `RUN_ID`; `RESULTS_DIR` outside both trees (never `experiments/results/`, where a manifest-less "run" would be taken in by a future `results/*/raw/` glob and write-once forbids deleting it) |
| F8 | Another heavy process shares the machine | Inflates every number | Top-5 CPU processes recorded before and after; not controlled (dev stance); the ADR says so |
| F9 | **The ADR over-reads the footprint.** "k6 uses 3 % of a core, so interference is negligible" | A claim the data cannot carry: CPU share does not measure cache, memory-bandwidth or scheduler contention against the *embedding server*, which is the mechanism the lower-bound argument runs through | §9: the footprint is declared **not** to satisfy Phase 7's interference clause, and the per-quantity table gives each quantity a bias direction |
| F10 | Ollama unloads a model mid-run (idle `keep_alive`; the repo sets none, so Ollama's default applies). After warm-up the smoke set is all Tier-1 and Tier-1 never calls Ollama | The zone reading *improves* (~2.1 GB freed) while decision 3 is silently void | Per-row MISS-asserted refresh and an `ollama ps` assertion before every row; PIDs re-resolved every row |
| F11 | `ps -o cputime=` is `MMM:SS.ss` with no hour field | A parser assuming `HH:MM:SS` misreads long-lived SUT processes by 60× | `parse_cputime` accepts the observed forms and **raises** on anything else; unit-tested on `43:57.34` |
| F12 | k6's RSS is set by its VU allocation (`ask.js:99-100`), and an all-hit run needs ~1 VU | The RSS column is flat across rates **by construction** | `VUS` pinned to 40, `vus_max` recorded; the ADR calls RSS an allocation floor, not a rate response |
| F13 | An orphan: a burner from an interrupted test, or a k6 after a sampler crash | Contaminates every later measurement | Own session, process-group kill in `finally`, signal handlers that raise, refuse to start if a `k6` exists |
| F14 | All-hit traffic makes `ABANDONED` ≈ 0 and `GENERATION_FAILED` ≈ 0 | Reading "0 abandoned" as "the upstream never hung" or as settling F-L / the k6-cancel question | Reported **vacuous for this workload, not settled** |
| F15 | The exit code is lost (CPython ECHILD → `returncode = 0`) | A k6 that failed its threshold looks clean | Status from `wait4` only (§3); the self-test has a child that exits 99 |
| F16 | k6 stdout on a `PIPE` fills | k6 stalls; CPU reads low | Output to files |
| F17 | The sampler's own cost ≈ k6's at 2 req/s | The "k6 is small" conclusion is partly the instrument | Overhead reported beside k6's (§2) |
| F18 | Pressure biases the figure: CPU reads high (page-ins, decompression), RSS low | The "indicative" number drifts from the green one | `vm_stat` swap/page **rates** per row; ADR says indicative unconditionally |
| F19 | A post-hoc go/no-go or headroom threshold | Choosing which rates' p95 become citable after seeing the table | Go/no-go values fixed in `approvals.md` **before** the run; no headroom threshold exists (§9) |

## 7. Unknowns that still need verifying

None is assumed; each has the step that resolves it.

| # | Unknown | Resolved by |
| :-: | :--- | :--- |
| **U1** | Whether `ps %cpu` is usable on this macOS. Believed to be a decayed average | Not relied on. The cputime-delta method is validated in §8 against burners whose CPU the child **reports about itself** |
| **U2** | `footprint -p` works without root on same-user non-child processes (analyst's probe), 20–30 ms per call on small ones; **cost on the ~1.7 GB runner unverified**; whether it works on a child | Plan step 1 probes k6 (a child) and the runner and records the cost. `phys_footprint` is the cited figure, RSS the floor, and the call is never in the 1 Hz loop |
| **U3** | `ru_maxrss` unit on this OS | §8 allocates a known block of incompressible data and asserts the figure; assumed bytes, **not trusted** |
| **U4** | How to get achieved rate and `dropped_iterations` out of k6 given `ask.js`'s `handleSummary`. The analyst reports `--summary-export` works beside it on k6 v1.7.1 and `dropped_iterations` appears **only when non-zero** | Plan step 1 re-probes; read with default 0. Fallbacks: `--out json=`; the gateway's `requests.jsonl` line count. Editing `handleSummary` is the last resort and needs an `approvals.md` line |
| **U5** | Whether three 60 s repetitions are stable enough | Read from the spread. If run-to-run spread exceeds the between-rate difference the table says "not resolved at this resolution" |
| **U6** | A high-rate informational row (≈ 400 req/s, all-Tier-1) so the "ceiling not citable" line has a number | **Not included.** The ADR cites the 2026-09-06 observation (impact.md §2) |
| **U7** | `make dev` passes `RUN_ID` through (analyst-verified); a relative `RESULTS_DIR` lands under `gateway/`; a reused id refuses to start | Settled by design: absolute `RESULTS_DIR` outside both trees, fresh `RUN_ID`; plan step 1 confirms where the directory appears |
| **U8** | The encoding of `kern.memorystatus_vm_pressure_level`. The repository says `0` = green. The reviewer recalls XNU returning 1 / 2 / 4 (normal / warn / critical), and the live reading was **1** with `memstatus_level` 52 and, a minute apart, **2** with `memory_pressure` reporting 41 % free. **I do not know which is right** | Not decided here. The sampler records the raw integer and the ADR reports raw readings, never a colour. Checking it against Activity Monitor's pressure graph is cheap and **outside 1.6**; if the reviewer is right, `make measure`'s `!= 0` gate can never pass, which blocks Phase 7. Reported to the author |
| **U9** | Whether the smoke questions return 200 against the current corpus (they name products that may not exist) | The warm-up asserts 200; a non-200 stops the run before sampling |
| **U10** | How much of k6's cost is the response body | Stated as an assumption in the ADR; the mixed row gives one comparison |
| **U11** | Whether the smoke set's near-duplicate pair (Q1/Q4) is served by Tier 2 rather than Tier 1 | The k6 summary reports the mix per row |
| **U12** | The actual `OLLAMA_KEEP_ALIVE`: the analyst read `5m0s`; this session saw the setting but not its value; nothing in `rag/src` or `gateway/` sets it (✔ grepped) | Read from the server log in plan step 1, recorded in the header. The design does not depend on the value, only on the models being checked every row |
| **U13** | CPython's `Popen` ECHILD → `returncode = 0` behaviour, and k6's `http_req_duration` semantics when k6 itself sends late (coordinated omission) | The first in §8 (T5); the second is stated in the ADR as the reviewer's claim, **unverified** |
| **U14** | The cache key prefixes, for the fallback flush if the author declines `make demo-reset` | Plan step 1 reads `interfaces.md` §D; the fallback is not used until the prefixes are confirmed there |

## 8. The self-test (acceptance 1)

Standing constraint 6: no measurement runs off an untested instrument. The ground truth is **what the child
reports about itself** (`time.process_time()` written at exit), not a duty-cycle estimate, so the test does
not depend on a burner hitting its nominal percentage. Tolerances are **relative ±25 %** (plus a stated
absolute floor for the small cases), sized to catch the ≥ 2× failure modes — 2× (`%cpu`), 60× (cputime
parser), 1024× (`ru_maxrss` units), ~41.7× (Mach ticks) — and deliberately not tight, so the test does not
flake under pressure. Total runtime budget: **under ~40 s**.

| # | Test | Asserts |
| :-: | :--- | :--- |
| T1 | A busy loop, 5 s | window mean within ±25 % of the child's own CPU/wall (≈ 100 %) |
| T2 | A 50 % duty burner, 6 s | within ±25 % of the child's self-reported CPU |
| T3 | A **~3 % duty burner**, 8 s (the regime k6 is in at 2 req/s, where 1 cs is ±1 % of a core) | window mean within ±25 % **or** ±0.05 CPU-s absolute, of the self-reported figure |
| T4 | A child holds **100 MB of `os.urandom` data**, touched, for 3 s | `ru_maxrss` in MB lies between 80 and 150 (a zero-filled block is calloc'd/compressible and proves nothing; this also traps the bytes-vs-KB error) |
| T5 | A child that **exits 99** after 2 s while being sampled | exit status 99 is recorded **from `wait4`**, the last tick is discarded, no exception |
| T6 | `parse_cputime` on `0:01.23`, `43:57.34`, `225:43.35`, `1:02:03.04`, and an unknown form | the four values exact; the unknown form **raises** |
| T7 | `summarise` on synthetic runs with known `a`, `b` | recovers `a` and `b`; a row at 94 % of offered is excluded, one at 96 % kept; a row with exit ≠ 0 or `MISS > 0` (all-hit) is excluded |
| T8 | An exception injected mid-run | the child's process group is **gone** afterwards (no orphan) |
| T9 | The sampler sent `SIGTERM` while a bounded burner runs | the burner is dead within 5 s |

T5 and T8 also settle U13's first half.

## 9. ADR-001 — outline (v2)

`Decided (method)` · date of the recorded run · `Touches: super-plan "Measuring without a second machine",
experiments/k6/README.md, Final_Proposal.md §7 and §9.4 (read-only)`.

**Decision.** Load generation is co-hosted on the SUT machine, and every number taken that way is reported
as a **bound, an indicative figure or not at all — never as a ceiling**. It **ratifies** the inherited
"Load generation: co-hosted" row (`decisions.md:71`, which gains "(ADR-001)") and **supersedes** the
off-box wording in the k6 README, `ask.js`, `mu_hit.js`, two Makefile banners and `experiments/README.md`.
`Final_Proposal.md` §7 and §9.4 already say co-hosted and name this ADR.

**What is citable co-hosted — one row per quantity, with the direction co-hosting biases it:**

| Quantity | Co-hosting bias | Status | What Phase 7 must add |
| :--- | :--- | :--- | :--- |
| goodput | **lower bound** (the generator starves the SUT) | bound | k6's concurrent CPU from the same run |
| shed rate | **upper bound** | bound | same |
| μ_hit | **lower bound** | bound; never a ceiling. Tier-1 ≈ 8000 (2026-09-06) is **not rescued**; Tier-2 ≈ 61 is a planning lower bound | per mode and per sweep point (7.2) |
| hit rate under load | **two-sided**: slower generation leaves more duplicate misses in flight (coalesced followers lower measured `h`); `ask.js` computes `h` over answered requests, which excludes sheds that are always misses (raises it) | indicative | pin `h_r` to the workload's ρ ceiling or a low-load replay |
| **μ_gen** | co-hosting depresses it, which **raises `h*`**: anti-conservative | **not citable co-hosted** for `h*` | measure it with a **sequential closed-loop client and no load generator** (concurrency 1 saturates one slot, so `b = 1` by construction) |
| **p95** | **two-sided**: CPU contention raises it; loopback removes network RTT; k6's `http_req_duration` may omit a late send (reviewer's claim, unverified) | **not a bound of either kind** | reported **only** with k6's concurrent CPU from the same run, and stated as loopback latency |
| the **1.6 footprint** | pressure-biased (F18) | **indicative, unconditionally**; the run is **exploratory** under standing constraint 4 | **not** Phase 7's interference measurement |

**The `h*` argument, corrected.** `h* > h_r` ⟺ `μ_hit/μ_gen > h_r/(1 − h_r)`, a single inequality; at
`h_r = 0.988` the threshold is **≈ 82.3**. The planning ratio is 61/0.19 ≈ 321, a margin of **3.9×**
(61/15.6) — **the plan's 3.8× restated in μ_gen units, not a second cushion**, and both inputs are
non-citable (`dev-v0` with no `run_id`; a planning figure, ADR-003). With `a`, `b` the factors by which
co-hosting depresses μ_hit and μ_gen, a ratio measured with both co-hosted is `R_measured = R_true · a/b`,
so the claim holds iff **`b/a > 0.26`** at `R_measured = 321`. The statement "a co-hosted figure is a lower
bound on `h*`" is therefore true of the **μ_hit leg only**. `h_r` is a third term co-hosting moves in both
directions (table above).

**The footprint does not satisfy Phase 7's interference clause** (*"every co-hosted number carries its
interference measurement"*). CPU share does not measure cache, memory-bandwidth or scheduler contention
against the embedding server, which is the mechanism the lower-bound argument runs through. A
"with and without k6" comparison is **not runnable** (no load without a generator). Two candidate methods are
**assigned to item 7.1 to design**, not designed here: (a) a **matched-burner test** — a synthetic CPU burner
sized from this footprint run beside k6, to see whether the measured quantities move; (b) the no-generator
μ_gen measurement above.

**Pre-registered go/no-go rule** (values A and B written into `approvals.md` by the author **before the
recorded run**): if k6's steady-state mean CPU at the highest *attained* rate is ≤ **A** % of one core and its
peak `phys_footprint` is ≤ **B** MB, ADR-001 adopts co-hosting unmitigated; otherwise it must evaluate a
mitigation (reduced VUs, or a `taskpolicy` QoS clamp) in a follow-up row before adopting, or record
co-hosting as adopted at a stated cost. Keyed on the steady-state mean and peak footprint, **not** on
per-second max.

**There is no headroom threshold.** v1 carried one as a `⟦PENDING⟧`; it is dropped, because a value fixed
after seeing this table is a choice of which rates' p95 become citable. The rule in its place has no
parameter (`super-plan.md:419`'s first option): **every co-hosted p95 is reported with k6's concurrent CPU
from the same run.** The sampler wraps Phase 7's runs for that reason, and 7.1 already needs ≥ 1 Hz sampling.
No number in the results chapter is sourced from this table, so the "re-measure under green" obligation
dissolves rather than needing a home in 7.1's Done-when.

**Pressure.** The ADR reports raw readings (the sysctl integer, `memstatus_level`, `memory_pressure`'s free %,
swap used, `vm_stat` deltas), never a colour, and calls the figure indicative whatever they say. It records
the divergence from §7 `:343` and §9.4 `:461` (a run that leaves green is discarded): this run was not gated
by the author's decision of 2026-10-06 and is classified exploratory. It also records U8 — the encoding is
unverified and may make `make measure`'s gate unpassable — for the author.

- **Evidence:** the table, the per-second CSVs, the probe results and the gateway log's line count and
  sha256, by path under this trail, with the regime labelled (all-hit and mixed) and the zone readings.
- **Alternatives:** a second machine (none exists, none dated); pinning k6 to efficiency cores with
  `taskpolicy` (not evaluated unless the go/no-go rule fails); an in-process closed-loop generator
  (rejected: a closed loop cannot saturate, which is S1's whole subject).
- **Consequences:** Phase 7 carries the interference method and the no-generator μ_gen. The ADR records
  `interfaces.md:164` ("off-box end-to-end") as **a lost measurement**, not merely stale wording: co-hosted
  p95 is loopback latency and excludes the network. It records `mu_hit.js:244` (a co-hosted
  `dropped_iterations > 0` cannot tell target saturation from k6 starving itself) as 7.2's to fix.
- **Invalidates:** *none — no runs yet* (impact.md §2: `experiments/results/` is empty and no k6 footprint
  was ever recorded). The 2026-09-06 μ_hit probes were never citable (co-hosted, `dev-v0`, no `run_id`); the
  ADR **relabels** them. What it **supersedes** is stated separately: the off-box wording listed above.
