# Approvals — loadgen-footprint (item 1.6)

Scope **L**. Nothing reads this file automatically since 2026-09-22; it is the human record of what was
reviewed. `Approved` stays blank until the author fills it.

| Phase          | Required    | Approved | When | ADR |
| :---           | :---        | :---     | :--- | :--- |
| impact         | L, M        | yes      | 2026-10-06 | none — no frozen value touched; ADR-001 ratifies the inherited "co-hosted" row (`decisions.md:71`) |
| contract       | if §B/§D    | n/a — no contract surface edited (`interfaces.md:164` is recorded as stale, not edited; spec decision 8) | | |
| experiment     | if measured | yes      | 2026-10-06 | ADR-001 (**written 2026-10-07**, after the recorded runs) |
| implementation | always      | yes      | 2026-10-06 | ADR-001 (written at plan step 9) |

## What the author is being asked to confirm

These are the spec's decisions that carry `☐` (spec v2). None is settled by this file's existence.

| # | Decision | Default taken |
| :-: | :--- | :--- |
| 1 | Workload | the built-in 5-question smoke set (all-hit after warm-up) plus the mixed row; nothing from `data/` |
| 2 | Rate grid | 2, 8, 16, 32 req/s, 60 s (middle 50 s is the window), 3 repetitions, `VUS = 40` |
| 5 | Evidence location | `docs/work/<task>/evidence/`, tracked |
| 6 | F-L | not fixed before 1.6 |
| 7 | Eval log | `RUN_ID` set, absolute `RESULTS_DIR` outside both trees and not Spotlight-indexed, only count + sha256 committed |
| 8 | `interfaces.md:164` | recorded in ADR-001 as **a lost measurement**, not edited |
| 9 | `make demo-reset` | **end of run only; needs the author's explicit go-ahead** (FLUSHALL + `git checkout -- data/`); fallback exists |
| 10 | Mixed-workload row | **included, default on** (≈ 4–5 min); the author may drop it, and the ADR then labels the table all-hit only |
| 11 | p95 headroom threshold | **none**; every co-hosted p95 is reported with k6's concurrent CPU |
| 12 | **Go/no-go values A and B** | **blank — required before the recorded run** (plan step 6) |

### Pre-registration (decision 12) — to be filled by the author *before* the recorded run

> If k6's steady-state mean CPU at the highest **attained** rate is ≤ **A** % of one core **and** its peak
> `phys_footprint` is ≤ **B** MB, ADR-001 adopts co-hosting unmitigated. Otherwise it must evaluate a
> mitigation (reduced VUs, or a `taskpolicy` QoS clamp) before adopting, or record co-hosting as adopted at
> a stated cost.

| Value | Set by the author | Date and time set |
| :--- | :--- | :--- |
| **A** (% of one core) | **25** | 2026-10-06 22:33 +0700 |
| **B** (MB) | **250** | 2026-10-06 22:33 +0700 |

Set by the author on 2026-10-06 at 22:33, **before any file of the recorded run exists** (`evidence/` then held
only the probes, the shakedown notes and the mutation record; the recorded run's output directory does not
exist yet). **Disclosure:** the author chose these two values *after* being told that the exploratory
shakedown, which is not evidence, had shown k6 at about 1.8 % of a core at 8 req/s and about 23 MB of
`phys_footprint`. They are therefore unlikely to bind; that is the author's call and is recorded so the ADR
cannot be read as if the thresholds had been set blind. The rule's form is unchanged: *adopt unmitigated* if
the steady-state mean at the highest **attained** rate is ≤ 25 % of one core **and** the peak `phys_footprint`
is ≤ 250 MB; otherwise evaluate a mitigation first.

The values are the author's. They are deliberately not suggested here: there is no basis in the repository
for a number, and a default written by the instrument's author is the researcher degree of freedom this
rule exists to remove.

Already decided by the author on 2026-10-06 and recorded in the spec: **models loaded** (decision 3);
**memory pressure recorded, never gating** (decision 4).

## Experiment-phase note (what this task invalidates)

**Nothing: `none — no runs yet`** (impact.md §2). `experiments/results/` is empty and no k6 footprint was
ever recorded. It **relabels**, rather than voids, the 2026-09-06 μ_hit probes (never citable: co-hosted,
`dev-v0`, no `run_id`). It **supersedes prose**, not a value: the off-box wording listed in impact.md §3.
This is the only trace the change leaves, so it is written down here as CLAUDE.md requires.

## Ledger

- 2026-10-06 — task opened; spec, impact (impact-analyst), design written. Impact corrected two premises of
  the first spec draft (§7 does not forbid co-hosting; `make check` cannot fail).
- 2026-10-06 — design review (`design-reviewer`, opus): **SOUND WITH CHANGES**, eight required changes, all
  adopted into `design.md` v2 and `spec.md` v2 (see `review.md`). Plan written (`plan.md`).
- 2026-10-06 — **`/approve impact` recorded** at the author's request. `impact.md` answers the
  frozen-artifact question (`none — no runs yet`). The first `/approve implementation` was **refused**
  because `impact` and `experiment` were still unapproved.
- 2026-10-06 — **`/approve experiment` recorded** at the author's request. The measurement change is
  described in `design.md` §2 and §9, and what it invalidates is stated above: `none — no runs yet`; it
  **relabels** the 2026-09-06 μ_hit probes and **supersedes prose**, not a value. Approving the phase does
  **not** fill the pre-registration: **A and B are still blank** and gate plan step 7.
- 2026-10-06 — **`/approve implementation` recorded** at the author's request, with `impact` and
  `experiment` already approved and `contract` n/a. `READY_TO_IMPLEMENT` written. The first coding step is
  plan step 1 (probes).
- 2026-10-06 — **plan steps 1–5 executed** (probes, tests first, sampler core, driver + `make footprint`,
  shakedown). `make verify` green with `ruff` on `PATH` (131 `experiments` tests; **note:** `make lint`
  prints "ruff SKIPPED" when `ruff` is not on `PATH`, so a bare `make verify` can pass without linting);
  the sampler's 10 planted faults are all caught by the self-test (`evidence/mutation_run.txt`).
- 2026-10-06 — **Four deviations from the approved design**, found by the shakedown and recorded as
  design.md v2.1 (rationale in `evidence/shakedown-notes.md`): (1) the refresh is an `env-check`-shaped
  ping, not a novel question through the gateway; (2) warm-up precedes PID resolution; (3) SUT processes
  are sampled every 5th tick; (4) the cache is flushed (prefix-only, never `corpus:`) at the start of `run`
  and before each mixed repetition. None changes what ADR-001 may conclude. Deviation 4 **deletes cache
  keys under a live gateway between k6 runs** and was also used once, with the gateway down, to clear the
  shakedown's leftovers (64 `t1:` + 20 `t2:` keys; `corpus:` stayed at 44).
- 2026-10-06 22:33 — **Plan step 6 done by the author:** A = 25 % of one core, B = 250 MB (pre-registration
  below). The recorded run (step 7) may now start.
- 2026-10-07 — **plan steps 7–11 executed.** Run A (12 all-hit rows kept; 3 mixed rows died on a relative
  `--out`, excluded and left in place) and run B (the mixed row, 3 reps, all kept); the pre-registered rule
  applied in `evidence/outcome.md` (**adopt unmitigated**: 4.80 % of one core at 32 req/s against A = 25 %;
  28 MB against B = 250 MB) **before** ADR-001 was drafted; ADR-001 written; the contradicting text reconciled;
  item 1.6 closed in `super-plan.md`.
- 2026-10-07 — **`/ai-review`: two reviewers, 18 findings plus a set of small number mismatches, all resolved** (`review.md`, second half). Fixes
  went into the sampler (guards, the flush, exit status, hashes), its tests (38 → 61), the mutation harness
  (a stale-bytecode flaw found and fixed; 25/25 caught), the Makefile, ADR-001, `outcome.md`,
  `provenance.md` and `super-plan.md`. The recorded tables were regenerated from the CSVs and are identical.
- ~~Open and gating: the pre-registration values A and B~~ — **set 2026-10-06 22:33** (see above).

## For the author — found along the way, outside 1.6 and not acted on

- **The memory-pressure sensor's encoding (design.md U8).** The repository's `0 = green` may be wrong. The
  reviewer recalls XNU returning 1 / 2 / 4 (normal / warn / critical); this session read **1** and, a minute
  later, **2**, with `memory_pressure` reporting 41 % free throughout. If the reviewer is right,
  `make measure`'s `!= 0` gate (`Makefile:95`) can never pass and Phase 7 is blocked, and `CLAUDE.md`'s
  "`0` = green" is wrong. A cheap check: read `sysctl kern.memorystatus_vm_pressure_level` while Activity
  Monitor's pressure graph is green. **Unverified; no file was edited.**
- **Bash calls that touched `data/` were denied twice in this session**, so this task treats `data/` as off
  limits and uses the built-in smoke set. `make demo-reset` runs `git checkout -- data/`; decision 9 asks you
  to authorise it explicitly rather than have it surprise you.

## For the author — decisions this task does not make for you

1. **Deviation 4 is still unconfirmed.** `make footprint` deletes `t1:`, `t2:` and `lru:` keys from the SUT's
   Redis at the start of a run and before each mixed repetition (design.md v2.1 §4; it refuses to run while
   `dep:`/`entry:` exist). You approved `make demo-reset` at the end of a run (decision 9) and said "execute
   the whole plan"; neither is a confirmation of *this*. It is disclosed in the Makefile banner, `make help`,
   ADR-001 and `super-plan.md`. Confirm it, or say how you want it changed (`NO_FLUSH=1` skips it, and is
   refused with the mixed row).
2. **Stale prose in two files this task was told not to edit.** `CLAUDE.md:162-167` and `Final_Proposal.md` §7
   `:345` / §9.4 `:460` still say a co-hosted figure is "a lower bound on `h*`". ADR-001 corrects that (true of
   the μ_hit leg only). A Phase 7 session reading `CLAUDE.md` alone would take a co-hosted μ_gen for a
   conservative bound.
3. **ADR-001's one ⟦PENDING⟧:** item 7.5 measures μ_gen with a sequential client and **no** load generator.
4. **Before committing:** `evidence/footprint*/header.json` lists your top-CPU processes (some are your own
   applications) and the k6 stdout/stderr files hold absolute `/Users/...` paths. This remote is public.
5. **The pressure sensor's encoding** (design.md U8) is still unverified, and `make measure`'s `!= 0` gate may
   never pass. Outside this task; recorded in `super-plan.md`.
6. **Nothing was committed or pushed.** Everything is in the working tree.
