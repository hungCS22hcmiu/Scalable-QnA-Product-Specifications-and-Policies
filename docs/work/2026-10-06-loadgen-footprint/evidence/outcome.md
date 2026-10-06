# Outcome — plan step 8: the pre-registered rule applied

Written **before** ADR-001 was drafted, as the plan requires. The rule and its values are the author's, set in
`approvals.md` on 2026-10-06 at 22:33, before any file of the recorded runs existed:

> If k6's steady-state mean CPU at the highest **attained** rate is ≤ **A = 25 %** of one core **and** its peak
> `phys_footprint` is ≤ **B = 250 MB**, ADR-001 adopts co-hosting unmitigated. Otherwise it must evaluate a
> mitigation first, or record co-hosting as adopted at a stated cost.

## The two runs (neither is edited; both are kept)

| Run | Directory | `RUN_ID` | What it holds |
| :--- | :--- | :--- | :--- |
| A | `evidence/footprint/` | `footprint-20261006` | the 12 all-hit rows (2, 8, 16, 32 req/s × 3 reps), **all kept**; and 3 mixed rows that **died** (k6 exit 107: a relative `--out` made k6 look for the workload file in `experiments/k6/`), excluded with `exit_status`, `unattained`, `errors_in_mixed`, `no_k6_summary`, `no_steady_window` |
| B | `evidence/footprint-mixed/` | `footprint-20261006-b` | the mixed row alone (8 req/s × 3 reps), taken after the fix and after `/verify`; **all kept** |

Both from HEAD `17bf221` (so ADR-006's condition on 1.6's first `RUN_ID` holds), with `gateway/` and `rag/`
unmodified; the working tree was dirty only with this task's own files.

## Applying the rule

| Quantity | Value | Bound | Result |
| :--- | :--- | :--- | :--- |
| Highest **attained** rate | **32 req/s** — achieved 32.02 in all three reps, 0 dropped iterations | — | attained (≥ 95 % of offered) |
| k6 steady-state mean CPU at 32 req/s | **4.80 %** of one core (reps 5.10, 4.71, 4.58) = **0.60 %** of the 8-core machine | **A = 25 %** | **≤ A** |
| `phys_footprint` of k6, the larger of two spot readings per row | **28 MB** (all readings in all kept rows lie between 21 and 28 MB) | **B = 250 MB** | **≤ B** |
| Peak resident set of k6 (`ru_maxrss`, exact), for the record | 59 MB (all-hit), 56 MB (mixed) | — | a different quantity |

B was written as a bound on k6's *peak* `phys_footprint`. The instrument reads `footprint` twice per row
(at about 10 s and 50 s, because each call costs 30–100 ms of CPU), so 28 MB is the largest of 30 spot
readings per rate, **not an exact peak**. The exact peak resident set is 59 MB. Neither comes near 250 MB, so
the verdict does not depend on which is meant, but the figure must not be described as the peak.

**Outcome: ADOPT co-hosting UNMITIGATED.** No mitigation (reduced VUs, `taskpolicy` QoS) is evaluated, because
the rule did not call for one. The rule was not binding: the margin to A is 5.2× and to B 8.9×, and the author
chose the values knowing the exploratory shakedown had shown about 1.8 % and about 23 MB (`approvals.md`).

## What the runs also show, to be read with the rule's outcome and not instead of it

- **k6's cost is linear and small:** CPU % = **0.81 + 0.124 × req/s** (intercept the fixed cost, slope the
  marginal), i.e. about **0.0012 CPU-seconds per request**. Extrapolated to the plan's λ_max ≈ 16 req/s that is
  about 2.8 % of a core, and the measured 2.70 % at 16 req/s agrees.
- **The all-hit regime is not the sweep's regime.** At the same offered 8 req/s, k6 used **1.94 %** in run A's
  all-hit rows and **1.41 %** in run B's mixed rows (−27 %). That is a **difference between two runs**, taken
  in different sessions (swap 8.4–8.5 GB against 9.0–9.2 GB, a different gateway process, an LLM runner at
  14 MiB against 286–968 MiB), and within each run the rates ran in ascending order, so drift aliases with
  rate. It is **not** a measured property of the regime and it is no bound. Spec decision 1's assumption ("k6's
  cost is a function of rate, not of what the gateway answers") is therefore **neither confirmed nor refuted**.
- **The SUT's state differs enormously between the regimes:** SUT total CPU is **1.4–4.8 %** of a core all-hit
  (Ollama idle) and **77–97 %** mixed (LLM runner 41–55 %, embedding runner 24–30 %). A footprint judged
  against an idle SUT says nothing about headroom against a busy one.
- **The LLM was mostly not resident, although `ollama ps` listed it as loaded.** Its resident set (the new
  "LLM runner RSS MiB" column; read from the stored CSVs) was **2,047–2,334 MiB** in the three 2 req/s rows,
  **13–19 MiB throughout in 8 of the 12 all-hit rows** (`allhit-r8-rep1` rose from 19 to 2,048 MiB inside the
  row) and **286–968 MiB in the mixed rows** while generating. `assert_models_loaded` reads only `ollama ps`
  and cannot tell. k6's own CPU is unaffected, but spec decision 3 held in name only and the "idle SUT" had a
  swapped-out generator. A run that needs a resident SUT must gate on the runner's resident set.
- **The instrument's own cost is the same order as what it measures:** 2.3–2.75 % of a core per rate
  (2.1–3.1 % per run), against
  k6's 1.0 % at 2 req/s and 1.94 % at 8. Below about 16 req/s the sampler costs more than k6. **Phase 7 inherits
  this** if it runs the sampler at 1 Hz with these calls.
- **The machine was not quiet, and the zone is indicative at best.** The pressure sysctl read **2** throughout
  (one row's minimum was **1**), `memstatus_level` 28–55, swap in use **8.4–9.2 GB** and growing across the session,
  and **every row shows swap-in or page-in activity** (up to 7,980 swap-ins and 11,512 swap-outs in a single
  row). Background daemons held the CPU at the start (`translationd` 46 %, `modelcatalogd` 38 %,
  `mobileassetd` 30 % in the top-5 before run A). None of this was controlled; none was gated (spec decision 4).
- **No request failed or was abandoned, as far as k6 can say.** Every kept row has `error_rate = 0` and k6 exit
  0. k6 counts any status other than 200 or 503 as an error (`ask.js`). A client that leaves is a status-0
  timeout, so no abandonment reached k6's 120 s limit. That a failed generation answers with a non-200 is my
  reading of §A and **was not checked here**, so "no `GENERATION_FAILED`" rests on it. The gateway log (`gateway-log-summary*.json`) is
  consistent: run A has 10,460 lines, 5 `MISS` (the warm-up), 10,455 `TIER1_HIT`, no sheds; run B has 1,453
  lines: 815 `TIER1_HIT`, 250 `TIER2_HIT`, 151 `MISS`, 237 `SHED`. `count-log` keys on `cache` and `shed`
  only and cannot tell `ABANDONED` from `GENERATION_FAILED`, so those are **not** claimed settled for any
  workload with a generation in flight.
- **Not measured, and not claimed:** interference with the embedding server (CPU share is not contention),
  any rate above 32 req/s, the Tier-1 μ_hit probe regime (~400 req/s), and the footprint under green pressure.
