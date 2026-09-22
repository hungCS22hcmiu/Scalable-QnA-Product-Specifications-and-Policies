# k6 load scenarios

| Script | Measures |
| :--- | :--- |
| `ask.js` | the mixed workload at a **constant arrival rate** — hit rate, goodput, shed rate |
| `mu_hit.js` | **μ_hit**, the 100 %-hit service rate — Phase 1's exit criterion |

## ⚠️ Run it off-box

the off-box measurement rule and proposal §7: the load generator must not share a host with the system under test. On a
16 GB machine whose whole claim is that generation is memory-bound, a co-hosted k6 competes for the
envelope it is measuring. A co-hosted run is **invalid**, not merely noisy.

```sh
# on the SECOND machine
k6 run -e GATEWAY_URL=http://<sut-ip>:8080 \
       -e WORKLOAD=/path/to/workload.json \
       -e ZIPF_SKEW=1.1 -e RATE_RPS=20 -e VUS=40 -e DURATION=10m \
       ask.js
```

The gateway binds `:8080` on all interfaces by default (`HTTP_ADDR`), so the second machine needs
only the SUT's LAN address.

## Environment

| Var | Default | Notes |
| :--- | :--- | :--- |
| `GATEWAY_URL` | `http://localhost:8080` | **Override it.** The default is the co-hosted case, which is invalid for measurement |
| `WORKLOAD` | *(built-in smoke set)* | JSON array of `{question, stratum?, product_id?}`. Without it the script runs five hard-coded questions — enough to prove the harness works, **never** something to report |
| `ZIPF_SKEW` | `1.1` | The redundancy knob. Protocol §6 sweeps three levels; `manifest.yaml` records it |
| `RATE_RPS`, `VUS`, `DURATION` | `10`, `20`, `2m` | Recorded in `manifest.yaml` as `k6_scenario` |

## What the script gets right, and why it matters

- **A `503` is not a failure.** `interfaces.md` §A's shed is a graceful-degradation event that
  §4 counts separately. If k6 marked it failed, an overloaded run would report an error rate where
  the gateway behaved exactly as designed.
- **Goodput excludes sheds.** Otherwise proposal §3's S2 (stability) is satisfiable at S1's
  (capacity) expense by shedding everything.
- **Constant *arrival rate*, not closed-loop VUs.** A closed loop cannot overload the target — each
  VU waits for its own response — so it can never find the saturation point S1 is about.
- **Zipf query selection.** Redundancy is the independent variable (proposal §9.1). Uniform
  selection would make the cache look useless; a fixed cycle would make it look perfect.
- **`X-Thesis-Stratum`** is sent when the workload record carries one, so the evaluation log
  (`interfaces.md` §H) gets the label without `POST /ask` growing a measurement field.

## `mu_hit.js` — the probe that can change the report

`Final_Proposal.md` §3 and the submitted pre-thesis report both say the load-conversion crossover
`h* = μ_hit/(μ_gen + μ_hit)` is **computed rather than observed**, on the basis that μ_hit sits far
above ~16 req/s. the capacity ratio makes that falsifiable: **if this probe returns ≤ ~16 req/s the crossover
IS reachable, S1's empirical wording is restored, and the proposal, the protocol and the report all
need revising.** The script evaluates the trigger itself and prints the verdict, so it cannot be
read past.

```sh
# on the SECOND machine
k6 run -e GATEWAY_URL=http://<sut-ip>:8080 -e MODE=tier2 \
       -e WORKLOAD=/path/to/workload.json -e RATE_RPS=400 -e VUS=100 -e DURATION=60s \
       mu_hit.js
```

**`MODE` picks which ceiling.** They are different numbers and the difference is the point of
`interfaces.md` §F: a Tier-1 hit is a hash lookup; a Tier-2 hit pays an embedding round-trip, which
is what §F says *"directly bounds μ_hit"*. **`MODE=tier2` is the figure `h*` should be computed
from** — `tier1` measures a ceiling the tiered system never actually operates at.

| Var | Default | Notes |
| :--- | :--- | :--- |
| `MODE` | `tier1` | `tier2` drives each record's `paraphrase` instead of its `question` |
| `PROBE_SIZE` | `20` | The probe set must fit inside `CACHE_CAPACITY`, or the probe evicts its own working set |
| `RATE_RPS` | `400` | Deliberately over-offered. **Under-offering is the one way to get a wrong answer quietly** |

Four things it refuses to do:

1. **Measure a cache it did not verify.** `setup()` warms every query, then re-sends the text the
   scenario will actually drive and asserts it answers from cache. "100 %-hit" is checked, not
   assumed — a gateway whose write-back silently fails returns plausible 200s and a μ_hit that is
   really μ_gen.
2. **Call an un-saturated run a ceiling.** If nothing was dropped and nothing shed, the generator
   never pushed past capacity, and the summary reports a **lower bound** instead of μ_hit.
3. **Tolerate a mid-run MISS.** `unexpected_miss` has a `count==0` threshold. The usual cause is
   `CACHE_CAPACITY` smaller than the probe set, which mixes generation into the hit path.
4. **Let a `tier2` probe silently become a `tier1` one.** A paraphrase below τ misses, generates,
   and is written into Tier 1 under its own key; every later request then answers `TIER1_HIT` and
   the probe reports the hash-lookup ceiling under a Tier-2 label. Worse, the contamination
   **persists across runs**. `setup()` requires `TIER2_HIT` specifically, and the fix it names is
   stop the gateway → `make demo-reset` → restart.

`make mu-hit` runs a **co-hosted shakedown** of the same script. It proves the harness works; its
numbers are not citable, and on this machine it drives memory pressure out of green by itself —
which is the off-box measurement rule demonstrating its own reason for existing.

## Before a run counts

1. `make measure` — gates the frozen envelope, the eviction state, and green memory pressure.
2. `RUN_ID` set on the gateway, so `interfaces.md` §H's log is written. Without it four metrics in
   §4 are not computable.
3. `CACHE_CAPACITY` set to `round(0.25 × K)`. Unbounded is the default and every hit rate
   it produces is an upper bound no deployment reaches.
4. `manifest.yaml` written next to the raw output. **A run is invalid without a complete manifest**
   (the evaluation); the script prints the fields it can supply.
5. Record `memory_pressure.min_zone` on the SUT. A run that left green is discarded and repeated at
   lower load whatever the throughput says.
