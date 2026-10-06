# Design review — loadgen-footprint (item 1.6)

Reviewer: the `design-reviewer` subagent (opus), 2026-10-06, on `design.md` v1 with `spec.md` and
`impact.md`. Its report is model output and carries no approval. Each finding below was read, checked where
it could be checked, and either adopted (with where it landed) or answered.

**Verdict: SOUND WITH CHANGES.** The shape of the instrument was endorsed (k6 as a child process, exact
rusage for totals, per-second `cputime` deltas for shape, never `ps %cpu`). The required changes are mostly
about **what ADR-001 may conclude**, plus silent paths in the Popen/`wait4` mechanics. Nothing touches the
hit path, determinism or cut scope.

| # | Finding | Blocks | Disposition | Landed in |
| :-: | :--- | :-: | :--- | :--- |
| 1 | The h\* argument: the 3.9× margin is the plan's 3.8× restated in μ_gen units, not a second cushion; "co-hosted figure is a lower bound on h\*" is false once μ_gen is also measured co-hosted; the comparator `h_r` is a third term co-hosting moves | ADR text | **Adopted.** Arithmetic re-derived (below) | design §9 |
| 2 | The "citable co-hosted" list has no bias directions; p95 is two-sided, not a bound; the "with/without k6" A/B is not runnable (no load without a generator); `interfaces.md:164` is a *lost measurement* | ADR text | **Adopted.** Per-quantity table; footprint declared not to satisfy Phase 7's interference clause; A/B removed, two candidate methods assigned to 7.1 | design §9, spec out-of-scope |
| 3 | No pre-registered rule links the result to the decision: the exit clause can pass vacuously; a post-hoc headroom threshold is a researcher degree of freedom | yes | **Adopted.** Go/no-go rule fixed before the run (values the author's); the headroom threshold is **dropped** in favour of the plan's own no-parameter option (`super-plan.md:419`): every co-hosted p95 is reported with k6's concurrent CPU | design §9, approvals |
| 4 | Silent Popen/`wait4` paths: lost exit code (CPython ECHILD → `returncode = 0`), stdout pipe stall, zeroed rusage kept, zombie tick, rusage includes start-up and teardown so total/N is a biased per-request cost, cross-check tolerance unstated | yes | **Adopted in full** | design §3, §2 |
| 5 | Self-test can pass while proving nothing: zero-filled allocation is compressible/calloc'd; no low-rate point; no exit-path test | yes | **Adopted** | design §8 |
| 6 | The instrument's own cost (`ps` ×2, `sysctl` ×3 per tick, setuid `ps`) may equal what is measured at 2 req/s | reporting | **Adopted:** overhead reported per row; one `ps` and one `sysctl` call per tick. `libproc` via ctypes **considered and not adopted** (adds a Mach-tick unit trap, ~41.7×) | design §2 |
| 7 | Pressure wording: "indicative unless green" cannot be decided while the encoding is unknown; the green re-measure has no home; standing constraint 4 not reconciled; pressure biases the figure | wording | **Adopted:** "indicative" unconditionally; the run is classified **exploratory**; the re-measure obligation dissolves because no number from this table reaches results (finding 3); swap/page deltas per row | design §9, spec decision 4 |
| 8 | The all-hit workload leaves Ollama idle and never exercises the Tier-2/embedding mechanism the lower-bound argument runs through | label (blocks); mixed row (no) | **Label adopted. Mixed row adopted as default-on**, one rate, author may drop it | design §4, spec decision 10 |
| 9 | Runbook: re-resolve PIDs every row; refresh must assert `cache == "MISS"`; `demo-reset` at the start buys nothing; SIGTERM/SIGHUP handlers; gateway/rag dirty flag; non-indexed `RESULTS_DIR` | no | **Adopted** (start-of-run `demo-reset` dropped; end flush kept with a no-`git checkout` fallback) | design §4, §6 |

## Checks the session made on the reviewer's arithmetic

`h* > h_r` ⟺ `μ_hit/μ_gen > h_r/(1 − h_r)`. At `h_r = 0.988` that threshold is **82.3** (the reviewer wrote
≈ 81). The planning ratio is 61/0.19 ≈ **321**, a single margin of **3.9×** (61/15.6), which is the plan's
3.8× (61 vs ≈ 16 req/s) expressed in μ_gen units. With `a` and `b` the factors by which co-hosting
depresses μ_hit and μ_gen, a ratio measured with both co-hosted relates to the true one by
`R_true = R_measured · b/a`; at `R_measured = 321` the claim holds iff **`b/a > 0.26`** (the reviewer's 0.253
used 81). Direction and the 0.74 req/s figure stand.

## What the reviewer could not verify (carried forward as unknowns)

- **The XNU encoding of `kern.memorystatus_vm_pressure_level`.** The reviewer recalls it as 1 / 2 / 4
  (normal / warn / critical), not the repository's 0 / 1 / 2, and notes the live reading **1** with
  `memorystatus_level` 52 looks normal. If so, **`make measure`'s `!= 0` gate can never pass**, which would
  block Phase 7. This is outside 1.6 and is **not acted on here**; it is reported to the author (U8).
- k6's fixed start-up/teardown CPU against its marginal per-request cost (settled by the slope fit's
  intercept); exec cost of `ps`/`sysctl` per tick and of `footprint` on the runner (the overhead column);
  whether v1's policy doc_ids collide with `dev-v0`'s (bears only if the author declines the end flush);
  whether k6's per-request CPU is invariant to latency and status (the mixed row); CPython's
  ECHILD → `returncode = 0` behaviour and k6's `http_req_duration` omission semantics (both confirmed in the
  self-test / probe, plan step 1–2).

## Verdict after resolution

All eight required changes are in `design.md` v2 and `spec.md`. **The design is ready for the author's
`/approve implementation`,** subject to the decisions listed in `approvals.md`, and in particular to the
go/no-go values A and B being written there **before the recorded run** (they gate step 7 of `plan.md`, not
the start of coding).

---

# AI review of the implementation (`/ai-review`, 2026-10-07)

Two reviewers ran in parallel on the working diff: **`contract-reviewer`** (a general pass: the diff touches no
contract surface, so the skill's fallback applies) and **`feature-dev:code-reviewer`** (added by the session:
this change's real failure modes are in the instrument and in the ADR's numbers). Their reports are model
output and carry no approval. **The code reviewer had no shell and executed nothing**; its findings come from
reading the code and recomputing numbers from the stored CSV/JSON. Every finding was read, and each fix below
was run. Most severe first within each source; `C` = contract reviewer, `K` = code reviewer.

What both found **clean**: `gateway/`, `rag/`, `contracts/` and `docs/contracts/` untouched; no frozen value or
§A/§D/§E/§H surface changed; the refresh request is byte-for-byte what `env_check.py` sends; `corpus:` stayed
at 44 and `idx:cache` survived the flushes; nothing was written to `experiments/results/`; no PQA text or raw
answers in the evidence; the gateway log reconciles with k6 (10,460 = 10 + 10,450; 1,453 = 10 + 1,443);
**every number in ADR-001 matched the tables** except the small ones listed below; the pre-registration
(22:33:53) precedes every recorded file (22:34:11 onward); the h\* algebra is right; `run_child`'s `wait4`
ordering, discard rules, exit-status source and process-group kill are sound; the units and column mapping
are right; every Phase 1 exit clause's by-hand command passes (the reviewer ran them; `make seam-check`, which
needs live models, was not run).

| # | Sev. | Status | Finding | Resolution |
| :-: | :-: | :-: | :--- | :--- |
| C1 | MED | CONFIRMED | ADR-001 declares the h\* argument corrected but leaves the old one live in `CLAUDE.md:162-167`, `super-plan.md` (Phase 7 exit, 7.2, "Measuring…"), `Final_Proposal.md` §7 `:345` / §9.4 `:460`, and the ADR said "nothing there needs editing". A Phase 7 session reading only `CLAUDE.md` would report `h*` from a co-hosted μ_gen as a conservative bound | **Fixed in the files this task owns:** the ADR now lists them as superseded (first paragraph, Summary row, `Invalidates:`); `super-plan.md` carries a pointer in "Measuring…" and a one-line note under Phase 7's exit; the k6 README cites ADR-001. **`CLAUDE.md` and `Final_Proposal.md` are not edited: the author's** (queued in `approvals.md` and `super-plan.md`) |
| K4 | MED | CONFIRMED | "Both models resident" (spec decision 3) is not what the recorded SUT looked like: the LLM runner's RSS was 13–19 MiB in 8 of 12 all-hit rows (a ninth rose from 19 to 2,048 MiB inside the row) and 286–968 MiB in the mixed rows, while `ollama ps` passed. `assert_models_loaded` cannot tell | **Disclosed, not fixed:** a new column "LLM runner RSS MiB" in every table; ADR-001, `outcome.md` and `super-plan.md` say it plainly, including that a run needing a resident SUT must gate on the runner's RSS. k6's own CPU is unaffected; the "idle SUT" and the mixed rows' SUT CPU are what it changes |
| K1 | MED | PLAUSIBLE (recorded data CONFIRMED unaffected) | Design F1's "assert the process name" was never implemented, and the one cross-check (`sampled > rusage`) cannot fire for a wrapper pid (sampled ≈ 0 against a large `wait4` total) | **Fixed:** `run_child(expect_comm=…)` flags `wrong_process:<comm>` on the first tick (the driver passes `"k6"`); a new exclusion `sampled_far_below_rusage` (sampled < 50 % of the exact total). Both tested and mutation-checked. Every recorded row sampled 92–97 % of its rusage, so none trips it |
| K2 | MED | CONFIRMED | `discarded_ticks` was recorded but never read: a run losing half its ticks entered the table as "kept" | **Fixed:** `many_discarded_ticks` (> 10 % of a run's ticks) excludes the row, and a "discarded ticks" column prints the count. All 18 recorded runs have 0 |
| K3 | MED | CONFIRMED | The pre-registered "peak `phys_footprint`" is the larger of **two spot probes** per row, not a peak | **Fixed by wording** (no instrument can read a peak at 30–100 ms per call): ADR-001, `outcome.md` and the table's note say "the larger of two spot readings", and give the exact `ru_maxrss` peak (59 MB). The verdict is not near flipping on either (28 and 59 MB against 250) |
| K5 | MED | PLAUSIBLE | The −27 % "regime dependence" and the rate slope are confounded with session and time (different swap levels, gateway pid, LLM residency; rates ran strictly ascending) | **Fixed by wording:** it is now "a difference between two runs", neither a bound nor a property of the regime; spec decision 1's assumption is "neither confirmed nor refuted" |
| C2 | MED-LOW | CONFIRMED | `make footprint` deletes the live gateway's cache keys without saying so, and that went beyond the single `make demo-reset` that decision 9 covered | **Disclosed and constrained:** the Makefile comment, banner and `make help` say so; `run` prints it; `NO_FLUSH=1` / `--no-flush` skips it and is refused with the mixed row (tested). **The author's confirmation is still pending** (below) |
| C3 | LOW-MED | PLAUSIBLE | The flush deleted `dep:` and `entry:` from outside the gateway; once C2 exists that breaks invariant 1 with no error | **Fixed:** `flush_cache` deletes only `t1: t2: lru:` and **aborts, deleting nothing,** if `dep:` or `entry:` exist (tested, mutation-checked). The tests that expected the old deletion were changed with the behaviour, not weakened |
| C4 | LOW | CONFIRMED | The flush ignored `--redis-port`, so against a non-default port it would report an empty cache and leave the SUT's warm | **Fixed:** `redis_cli(port)` is threaded through `run`, `run_row` and `flush-cache --redis-port` (tested, mutation-checked). **Accepted:** `demo-reset`'s foreign-key guard is not replicated; the flush is prefix-only and a shared Redis holding another project's `t1:`/`t2:`/`lru:` keys would lose them (low; the same machine, one Redis) |
| K6 | LOW | CONFIRMED | Tests that let a wrong instrument pass: the window constants pinned by no test; `sample_machine` never called; `sample_ps`'s missing-pid behaviour and `sut_pid_missing` untested; `errors_in_mixed` untested; the summarize fixture had no SUT columns; an always-true assertion (`"INDICATIVE" in text`); a test name that over-claimed (T5); T3's floor looser than the design | **Fixed:** 24 new tests (38 → 61 for the sampler): the window constants pinned with a profile that makes a wrong window read 55 % instead of 10 %; canned-output tests for `sample_machine` and `sample_ps`; the `sut_pid_missing` branch; `errors_in_mixed`; a fixture with SUT columns and per-row probe joins; `_mb`; the overhead formula and the runner-role choice as pure functions. The vacuous assertion was removed, T5 renamed to what it asserts, T3's floor tightened from 1.5 to 1.0 pp |
| K7 | LOW | CONFIRMED | Ten planted faults left plausible silent ones uncovered; `mutation_run.txt` described an earlier module | **Fixed:** 15 more mutants (window head/tail, wrong sysctl field, missing pid as a gap, `errors_in_mixed`, `_mb`, overhead, role swap, dependency-region deletion, wrong process, discarded ticks, sampled floor, redis port, `--no-flush --mixed`, ncpu guess) — **25/25 caught**; the file now records the final run and the module's sha256. **A flaw in the mutation harness itself was found on the way** (see below) |
| K8 | LOW | CONFIRMED | `MIXED=0` still enabled the mixed row (`$(if $(MIXED),…)` is true for any non-empty string) | **Fixed:** `$(filter-out 0 no false,$(MIXED))`; five `make -n` cases tested |
| K9 | LOW | CONFIRMED | `cmd_run` exits 0 even when every row is excluded (run A's three dead mixed rows exited 0) | **Fixed:** exit status 4 and a stderr warning when any row is excluded (`count_excluded`, tested) |
| K10 | LOW | CONFIRMED | Provenance: the sampler and `ask.js` were uncommitted and unhashed; `summarize` silently fell back to `os.cpu_count()` | **Fixed for the future** (header hashes; `summarize` refuses without a core count); **for the recorded runs unrecoverable, and documented** (`evidence/provenance.md`) together with the regeneration check: the tables rebuilt from the CSVs with the changed module are **identical** |
| C5 | LOW | CONFIRMED | The mixed rows used an unbounded cache (`lru: 0` beside non-zero `t2:`) and the ADR did not say so | **Fixed:** one bullet in ADR-001 (an inference, with the evidence for it) |
| C6 | LOW | PLAUSIBLE | "Exploratory under standing constraint 4" rests on an undocumented override, and 1.6's Done-when says "the sweep's actual rates" | **Fixed:** the ADR defines *exploratory* (not citable, not an input to any result, **not** a run constraint 4 would accept; the constraint is unamended). The Done-when is **not amended**; the 1.6 row now says so |
| C7 | LOW | CONFIRMED | Stale references: `mu_hit.js:244` (moved by this diff's own header edit), `plan.md`'s by-hand path, `approvals.md` | **Fixed:** cited by the verdict line's text; the path corrected; `approvals.md` reconciled |
| K11 | LOW | CONFIRMED | The window is not exactly "the middle 50 s" (it is 49–50 s because the tail endpoint is the last tick) | **Fixed by wording** in the ADR and the table's note |
| — | — | CONFIRMED | Small number mismatches: swap "8.3–9.2" (data: 8.4–9.2 GB); sampler cost "2.3–2.75 %" is the per-rate mean (per run 2.1–3.1 %); `outcome.md` listed four of the five flags of the failed rows; "3.8× restated as 3.9×" (the same ratio, rounded differently); `b/a > 0.26` (exact 0.257); method (b) assigned to 7.1 in one place and 7.5 in another; decimal MB vs MiB | **All corrected** in the ADR and `outcome.md`; the units are now stated in the table's note |
| — | — | CONFIRMED | Cosmetic: `header.json` lists the author's top-CPU processes and the k6 files hold absolute `/Users/...` paths; this remote is public | **Noted for the author** before anything is committed (`provenance.md`); nothing scrubbed, because recorded evidence is not edited |

## A flaw in the mutation harness, found while resolving K7

The first full mutation run reported 24/25: `--no-flush with --mixed is accepted` *survived* in the full run
and was *caught* when run alone. The cause was the harness: that mutant and the one before it (`the flush
ignores --redis-port`) both shorten the file by exactly 17 characters, and Python reuses cached bytecode when
the source's mtime (whole seconds) and size match, so the later mutant ran on the earlier one's bytecode. **Any
earlier "caught" or "survived" could have been wrong in either direction.** The harness now sets
`PYTHONDONTWRITEBYTECODE`, empties the module's `__pycache__` before every run, refuses to start unless every
selector passes (and selects something) on the unmodified module, and counts only a pytest exit status of 1 as
a catch (5, "nothing selected", no longer counts). All 25 were then re-run: **25/25 caught.**

## State after resolution

- `make verify` and the full sampler suite: re-run in the next ledger entry of `plan.md`.
- **No finding is unresolved.** Open items that are the author's, not blocking `/done`: (1) confirm that
  `make footprint` may delete `t1:`/`t2:`/`lru:` keys (deviation 4, beyond decision 9); (2) edit `CLAUDE.md`
  `:162-167` and `Final_Proposal.md` §7 `:345` / §9.4 `:460` through ADR-001's per-quantity table;
  (3) the ADR's one ⟦PENDING⟧ (item 7.5 measures μ_gen with no generator); (4) review the evidence directory
  for personal process names and paths before committing.
