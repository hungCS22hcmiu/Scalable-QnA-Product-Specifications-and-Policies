# Writer drain rate — plan step 7 (record-only)

**Status: exploratory, not citable.** Taken on 2026-10-06 at commit `78ae546` plus the uncommitted 1.5
change, on the M1 MacBook Pro with `kern.memorystatus_vm_pressure_level` = **2** (urgent) and other
applications open, so it is **not** a green-pressure run. It measures a unit of the gateway (the
evaluation logger's writer goroutine), not the gateway under load, so it is also not S1/S2 evidence.
Go 1.26.1 darwin/arm64, temp directories on the system volume (APFS).

## Question

Does storing answers make the writer slow enough to push `Dropped()` above 0? (`design.md` §4,
`review.md` 2.) A tight `Log` loop cannot answer it: it enqueues in ~100 ns while the writer already
pays a `write(2)` per record, so drops from such a loop come from the producer. So the test times the
writer's **drain**: n = 3000 records (below the 4096 buffer, so `Dropped()` stays 0 and is asserted 0)
are enqueued, and `Close`, which drains, is timed. Medians of 9 repetitions on a fresh logger each.

Reproduce: `cd gateway && MEASURE_DRAIN=1 go test -count=1 -run TestMeasureWriterDrain -v ./internal/telemetry/`
(`internal/telemetry/answers_drain_test.go`; skipped without the variable; a measurement, never an assertion).

## Result (two runs)

| Record kind | Run 1, µs / record | Run 2, µs / record | Meaning |
| :--- | ---: | ---: | :--- |
| no answer | 4.0 | 3.7 | the pre-1.5 cost: one JSONL line |
| already seen (the control) | 4.1 | 3.6 | a map lookup, then the line |
| **first seen** | **447.6** | **436.8** | create, write, chmod, close, link, remove, then the line |

- **An already-seen record adds nothing measurable** (+0.1 and −0.1 µs, inside the noise). The Zipf
  common case, a repeated answer, costs what a record cost before 1.5.
- **A first sighting adds ≈ 433–444 µs**, about **110×** a line write.
- **Sustainable first-sighting rate ≈ 2,230–2,290 records/s** (1 / first-seen). The writer keeps up
  with that many *new* answers per second; with repeats it keeps up with ≈ 240,000–277,000 records/s,
  as before.

## What it means for the real workload

First sightings are bounded in **number**, not only in rate: distinct answers are at most
`0.25·K` (the cache capacity, plus whatever a MISS adds). `K` is not frozen until the `v1` freeze
(`data-card.md`), so the bound is stated as a function of it.

**A drop needs the buffer to fill.** Worst case: all `F = 0.25·K` first sightings arrive at once and
the offered rate stays at λ while the writer drains them at 442 µs each. Drops require
`λ · F · 0.44 ms + F > 4096`, i.e. `λ > (4096 − F) / (F · 0.00044 s)`:

| K (distinct queries) | F = 0.25·K | offered rate above which a worst-case burst can drop |
| ---: | ---: | ---: |
| 2,000 | 500 | ≈ 16,300 req/s |
| 5,000 | 1,250 | ≈ 5,200 req/s |
| 10,000 | 2,500 | ≈ 1,450 req/s |
| ≥ 16,384 | ≥ 4,096 | any burst of that many first sightings can overflow on its own |

**Against the planning figures** (`super-plan.md`): generation ≈ 0.19 req/s, Tier-2 hits ≈ 61 req/s,
Tier-1 hits ≈ 8,000 req/s (a probe, unconfirmed). At Tier-2 rates and below, the writer keeps up with
a margin of ≥ 35× even if **every** request were a first sighting. The `mu_hit.js` probe repeats one
query, so it writes about one file. **The only regime that can drop is a Tier-1-heavy phase at
thousands of req/s over a large `K`, in its first seconds**, while the cache's contents are still new
to the run.

**Verdict: not a stop condition for the planned sweep; a named constraint.** It does not stop the
task (`plan.md` "what would make me stop"): the real bound is not exceeded at any planned rate. It is
recorded in ADR-005 so a Phase 7 Tier-1 run at high rate with a large `K` checks `Dropped()` and
`AnswersMissing()` first. **If it ever bites**, the options are cheaper publication (an `OpenFile` with
mode 0644 drops the `Chmod`; the `Link`/`Remove` pair is the other cost), a larger buffer (a
measured-path change, needs its own decision), or `raw/answers.jsonl` (ADR-005, alternative 2). None
is taken now.

## Not measured

- **Spotlight** (`mds`/`mdworker`) importing each new file (`review.md` 9; `approvals.md` question 6).
  A unit test cannot see it.
- The gateway **under load** with the writer competing for CPU with k6 and the embedder (co-hosted).
- **A pressure-green run.** This one is level 2, so the absolute numbers carry that; the *ratios*
  (first-seen vs control vs no-answer, ≈ 110×) are the finding.
- **Other filesystems.** APFS only.
- File-system cache effects across a long run (3,000 files per repetition, deleted with the temp dir).

## Race detector

`go test -count=1 -race ./internal/telemetry/ ./internal/httpapi/ ./cmd/gateway/`: **ok**, all three.
`go test -count=5 -race ./internal/telemetry/`: **ok** (no flake over five repetitions of the polling
tests). The accessor-while-writing test (`TestTheAccessorsAreSafeWhileTheWriterIsRunning`) is what
gives the race run its meaning for `missing`'s mutex.
