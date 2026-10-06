# Plan — loadgen-footprint (item 1.6)

Smallest change that satisfies `spec.md` v2 against `design.md` v2. Each step is independently verifiable
and names its check. **Nothing below starts until `/approve implementation`.** Steps 0 and 6 are the author's.

Rule for every step: on a failed check make **one** quick fix, then `/rca`. Tests are immutable once written
(step 2) unless an RCA proves one stale and the author confirms.

## 0. Gate — the author

- [x] `approvals.md`: impact, experiment and implementation approved; decisions **1, 2, 5, 6, 7, 8, 9, 10,
      11** confirmed or changed.
- [x] **Decision 12 is not needed to start coding**, only before step 7. It is listed here so it is not
      forgotten.

## 1. Probes — answer the unknowns before writing the instrument (no source kept)

Write the results to `evidence/probes.md`. Each probe is a one-off command; none changes the repo.

- [x] **U4** `k6 run --summary-export=… experiments/k6/ask.js` for 5 s against a stub or the live gateway:
      confirm the export is written despite `handleSummary`, which fields exist, and that
      `dropped_iterations` is absent when zero.
- [x] **U2** `footprint -p <pid>` on (a) a short-lived **child** of a shell, (b) the Ollama runner. Record the
      per-call CPU cost. If it fails on a child, the design falls back to `ru_maxrss` for k6 and says so.
- [x] **U13** In a scratch script (not under `experiments/`): `Popen` a child that exits 99, reap it with
      `os.wait4`, and print `Popen.returncode` afterwards. Confirms or refutes the ECHILD → 0 claim.
- [x] **F11 / U1** `ps -o pid=,stat=,rss=,cputime= -p <a long-lived pid>`: record the exact `cputime` format;
      compare two readings 10 s apart against `top -pid <pid> -l 2` for one busy process.
- [x] **U12** Read `OLLAMA_KEEP_ALIVE` from `~/.ollama/logs/server.log`.
- [x] **U14** Read `docs/contracts/interfaces.md` §D for the cache key prefixes (the fallback flush needs them).
- [x] **U7** Start `RUN_ID=probe-<n> RESULTS_DIR=<scratchpad> make dev`; confirm the directory appears there
      and **not** under `experiments/results/` or `gateway/`; stop it. (Uses a throwaway id.)
- **Check:** `evidence/probes.md` has a result for each; any that overturns a design assumption is raised to
  the author before step 2.

## 2. Tests first — `experiments/tests/test_loadgen_footprint.py`

- [x] Write T1–T9 exactly as in `design.md` §8, against the function contracts in §5. Burners are bounded in
      runtime and start in their own session. Tolerances are relative ±25 % with the stated absolute floor.
- **Check:** the tests exist, import the (not yet written) module, and **fail for the right reason**
  (missing implementation, not a typo). Commit nothing yet.

## 3. The sampler core — `experiments/scripts/loadgen_footprint.py`, pure parts and process parts

- [x] `parse_cputime`, `sample_ps`, `sample_machine`, `window_mean`, `run_k6`'s `wait4` loop (§3), `summarise`
      with the exclusion flags and the `a + b·rate` fit. Stdlib only; no `import rag`.
- **Check:** `python3 -m pytest experiments/tests/test_loadgen_footprint.py` green, **run three times** to
      see it is not flaky; total runtime under ~40 s; `pgrep -f` finds no stray burner or k6 afterwards.

## 4. The driver — `run`, `summarize`, `make-workload`, and the Makefile target

- [x] `run`: warm-up, per-row PID re-resolution by port and by parent/blob, the MISS-asserted refresh and the
      `ollama ps` assertion, the all-hit rows, the mixed row, per-row `vm_stat` and `footprint`, the
      sampler-overhead figure, output of `samples-*.csv`, `summary.json`, `footprint.md`.
- [x] `make-workload`: seeded; the 5 smoke questions + 300 suffixed variants; writes JSON into the trail.
- [x] `summarize`: regenerates the table from the CSVs alone.
- [x] `Makefile`: a `footprint` target, in `.PHONY` (`:38`) and `make help`, with the exploratory banner.
- **Check:** `make verify` green (gofmt/vet/ruff/build/pytest); `make help` lists `footprint`;
      `summarize` on a CSV fixture reproduces a hand-computed table.

## 5. Shakedown — exploratory, not recorded

- [x] One rate, 15 s, 1 rep, against `make dev` with a throwaway `RUN_ID` and the absolute `RESULTS_DIR`.
- **Check:** the output has every column in acceptance 2; the sampler overhead is printed; `kill -TERM` of
      the sampler mid-run leaves **no** k6 behind; the refresh returned `cache == "MISS"`; the run directory
      is where step 1 said. Nothing from this step is kept as evidence.

## 6. Pre-registration — the author

- [x] The author writes **A** and **B** (go/no-go values, spec decision 12) into `approvals.md`, **dated
      before the recorded run's first request**.
- **Check:** `approvals.md` carries both values and a date earlier than `evidence/`'s first file.

## 7. The recorded run

- [x] `RUN_ID=footprint-<date> RESULTS_DIR=<absolute, scratchpad> make dev`; then
      `make footprint RATES=2,8,16,32 DURATION=60 REPS=3 MIXED=1`. Take it from HEAD (`17bf221`) so ADR-006's
      first-`RUN_ID`-after-F-H condition holds.
- [x] Stop **k6 first**, then the gateway; record the gateway's exit verdict (F-F).
- [x] Flush both tiers: `make demo-reset` **only with the author's go-ahead** (decision 9). Otherwise the
      fallback: with the gateway down, delete the key prefixes confirmed in step 1 (U14) and verify zero; **no
      `git checkout -- data/`**.
- **Check:** `redis-cli` shows no `t1`/`t2` entries afterwards; `pgrep k6` empty; `git status` shows only
      this task's files; `evidence/` holds the CSVs, `summary.json`, `footprint.md`, `probes.md`, the gateway
      log's **line count and sha256** (the log itself is not committed).

## 8. Read the result against the pre-registered rule

- [x] Apply the go/no-go rule to the steady-state mean CPU at the highest *attained* rate and the peak
      `phys_footprint`. Any excluded row is listed with its flag. State the zone readings **raw**.
- **Check:** the outcome (adopt unmitigated / evaluate a mitigation / adopt at a stated cost) is written in
      `evidence/outcome.md` before the ADR is drafted. If the rule says *evaluate a mitigation*, **stop and
      raise it to the author**; that is a design change, not a step of this plan.

## 9. ADR-001

- [x] Append ADR-001 to `docs/decisions.md` per `design.md` §9; update the Summary row; replace the two
      "reserved / not yet written" notices; add "(ADR-001)" to the inherited "Load generation" row.
- **Check:** the entry has `Invalidates:`; every number in it is traceable to a file under `evidence/`;
      the per-quantity table carries a direction for each quantity; it states that the footprint does **not**
      satisfy Phase 7's interference clause; it says **indicative** and **exploratory**; it names U8,
      `interfaces.md:164` and `mu_hit.js:244`.

## 10. Reconcile the contradicting text

- [x] `experiments/k6/README.md`, the headers of `ask.js` and `mu_hit.js` (comment only), the `Makefile`
      banners `:350-355` and `:379-385`, `experiments/README.md:6`.
- **Check:** the acceptance-5 grep returns only lines that cite ADR-001 or record history; `git diff` on
      `ask.js` and `mu_hit.js` shows **comment lines only**; `make verify` still green.

## 11. Close the item

- [x] `docs/super-plan.md`: mark item 1.6 done with the ADR and trail; correct `:121`; set the Phase 1
      progress line to 6 of 6. **Do not edit `CLAUDE.md`, `interfaces.md` or `Final_Proposal.md`.**
- **Check:** run Phase 1's exit criterion by hand, clause by clause (below).

## 12. `/verify` → `/ai-review` → `/done`

- [x] `/verify`; `/ai-review` (the contract-reviewer is not needed: no seam is touched); `/done`, which asks
      whether scope L was honest.

### Phase 1 exit criterion, by hand (the commands, so closing it is not a judgement)

| Clause | Command / artefact |
| :--- | :--- |
| `httpapi` tests cover every exit path of `Ask` | `cd gateway && go test ./internal/httpapi/...`; the six outcomes appear in `ask_test.go` |
| `env-check` fails when the slot count differs | `python3 -m pytest experiments/tests/test_env_check.py -k four_slots` |
| `texts` aligned Python → Go | `pytest rag/tests/test_retrieve_texts.py`; `go test ./internal/ragclient/...`; `make seam-check` when models are available |
| no retired branch | `grep -rIn "tau_high\|TauHigh\|similarity_only_decision" gateway rag contracts` finds only `retiredEnv` and its tests |
| answer recoverable from `raw/` | `go test ./internal/httpapi/ -run TestEveryServedAnswerIsRecoverableFromRawAlone` |
| footprint measured, ADR-001 recorded | `evidence/footprint/footprint.md` and `evidence/footprint-mixed/footprint.md` exist; `grep -n "ADR-001" docs/decisions.md` shows a real entry, not "Reserved" |

## Risks to the plan itself

- **Step 7 is the only step with a machine state outside the repo.** It leaves Redis warm, a results
  directory in the scratchpad, and models loaded. The end flush and the orphan checks are its guards.
- **Step 6 can block step 7 indefinitely** if the author does not set A and B. That is the intended
  behaviour: a run taken without them would be a run whose outcome could not change the decision.
- **Step 8 can reopen the design.** If the rule says *evaluate a mitigation*, the plan stops there.

---

## Execution log

### `/verify` after step 7's first run (2026-10-07, before the mixed-only rerun)

Run with `ruff` on `PATH` (`~/Library/Python/3.13/bin`); a bare `make verify` prints "ruff SKIPPED" without it.

| Target | Command | Result |
| :--- | :--- | :--- |
| Go format | `gofmt -l gateway/` | **PASS** (no output) |
| Go vet | `cd gateway && go vet ./...` | **PASS** (exit 0) |
| Go build | `cd gateway && go build ./...` | **PASS** (exit 0) |
| Go test | `cd gateway && go test -count=1 ./...` | **PASS** (exit 0; uncached) |
| Python lint | `ruff check rag experiments` | **PASS** |
| Python tests, rag | `pytest` in `rag/` | **PASS** (15) |
| Python tests, experiments | `pytest experiments/tests` | **PASS** (132, incl. 38 for the sampler) |
| Proto drift | `git diff --exit-code -- contracts/` | **`contracts/` clean — but the stub-drift check is vacuous**: both stub directories are gitignored (`super-plan.md`, "For 1.5": `/verify`'s proto-drift row checks nothing). Not reported as PASS. No `.proto` was touched by this task |

Skipped: none. `make test` and `make verify` still do not run `-race` (recorded finding, not this task's).

The sampler's self-test was also shown able to fail: `evidence/mutation_run.txt` — 10 planted faults, all caught.

### Step 7 — the recorded run, and what went wrong with it

- **Run A** (`evidence/footprint/`, `RUN_ID=footprint-20261006`, HEAD `17bf221`, `gateway`/`rag` unmodified): the
  12 all-hit rows (2, 8, 16, 32 req/s × 3) are all kept. **The 3 mixed rows died** (k6 exit 107): `--out` was
  relative, and k6 resolves `open()` against the script's directory. The shakedown used an absolute `--out`
  and did not catch it. The sampler's guards worked: the rows are excluded with `exit_status`,
  `no_k6_summary`, `errors_in_mixed`, `no_steady_window`, and nothing was averaged in. Run A is **left as it
  is** (write-once); its three failed rows stay in its table as the record.
- **Fix** (`workload_arg`, absolute path; test added; `--rates ""` allowed for a mixed-only run; Makefile
  quotes `$(RATES)`), then `/verify` as above, then **Run B** (`evidence/footprint-mixed/`,
  `RUN_ID=footprint-20261006-b`): the mixed row alone, in a new directory.

### Steps 7–12, closed (2026-10-07)

- **Step 7** done as two runs (A: all-hit rows + three mixed rows that died on a relative `--out`; B: the mixed
  row alone). Gateway stopped after k6 each time ("flushing the evaluation log"); logs counted
  (`gateway-log-summary*.json`); cache keys flushed; no stray process.
- **Step 8** `evidence/outcome.md`, written before the ADR: **adopt co-hosting unmitigated**.
- **Step 9** ADR-001 in `docs/decisions.md`. **Step 10** the contradicting text reconciled (the acceptance-5
  grep for wording that contradicts co-hosting returns nothing; `interfaces.md:164` deliberately left, recorded
  in the ADR). **Step 11** item 1.6 closed in `super-plan.md`.
- **Step 12** `/ai-review` found 18 things plus small mismatches (`review.md`, second half), all resolved. Final
  `/verify`, run with `ruff` on `PATH`:

| Target | Result |
| :--- | :--- |
| `make verify` (gofmt, vet, ruff, build, go test, pytest rag, pytest experiments) | **PASS**, exit 0, **0 SKIPPED** |
| `go test -count=1 ./...` (uncached) | **PASS** |
| `pytest experiments/tests` | **PASS**, 155 (94 before this task + 61 for the sampler) |
| `ruff check rag experiments` and the mutation script | **PASS** |
| Sampler mutation check | **25/25 caught** (`evidence/mutation_run.txt`, module sha256 prefix `79f8137bb50a8b23`) |
| `k6 inspect` on the two edited scripts | both parse |
| Proto drift | `contracts/` untouched; the stub-drift check is vacuous (stubs are gitignored), **not reported as PASS** |

Two runs of a step were repeated, not one: the mixed row (run B) after the relative-path fix, and the mutation
suite after its own stale-bytecode flaw was found. Nothing was committed.

### Deviations from this plan as written (all 25 steps were performed; these did not go as written)

- **Step 0, "decisions … confirmed or changed":** the author approved implementation with the spec's defaults and
  never confirmed decisions 1, 2, 5–11 one by one; **decision 9 was changed** in practice (no `make demo-reset`
  was run; a prefix-only cache flush was used instead), and that change is **not yet confirmed** by the author.
- **Step 4 / 5, "the MISS-asserted refresh":** replaced by an `env-check`-shaped ping (design.md v2.1 §1); the
  MISS-asserted question could not work (found in the shakedown).
- **Step 7, "Flush both tiers: `make demo-reset`":** done with the prefix-only flush. And step 7 ran as **two
  runs** (A, then B for the mixed row, after a relative-path bug).
- **Step 12, "the contract-reviewer is not needed":** the `/ai-review` skill's fallback ran it as a general pass
  anyway, beside a code reviewer.
- **Added, not in the plan:** the cache flush before each mixed repetition; `--sut-every`; `--no-flush`;
  `provenance.md`; the review round's guards, columns and 24 further tests; the mutation harness repair.

---

## Outcome — closed 2026-10-07 (`/done`)

**Scope L was honest.** The task measured something, wrote a numbered decision (ADR-001) and touched
`decisions.md`; it touched **no** seam (`interfaces.md`, the `.proto`, `gateway/`, `rag/`, `reuse/` are
unmodified), no frozen value, and no `raw/`. It would have been wrong at M or S. One finding about the ladder:
**the L design review (two reviewers, eight required changes) could not stand in for a shakedown.** The
shakedown found four mechanism errors the approved design contained (a refresh that cannot reach the LLM, an
order that cannot find runners that are not yet loaded, a sampler costing 3× its subject, a seeded workload that
is cached after its first repetition), and the recorded run found a fifth (a relative `--out`). Impact analysis
and design review corrected two false premises in the spec before any code. **A scope-L measurement plan should
name its shakedown as a step that may rewrite the design**, as this plan did.

**What shipped**

- `experiments/scripts/loadgen_footprint.py` (the sampler/driver) with 61 tests and a 25-fault mutation check;
  `make footprint`. It is stdlib-only, wraps any k6 invocation, and is meant to be reused by Phase 7.
- Two recorded runs under `evidence/footprint/` and `evidence/footprint-mixed/`, the outcome of the
  pre-registered rule (`evidence/outcome.md`: **adopt co-hosting unmitigated**, 4.80 % of one core at 32 req/s
  against A = 25 %; 28 MB against B = 250 MB), the probes, the shakedown notes, and `provenance.md`.
- **ADR-001** (`docs/decisions.md`): ratifies the inherited "co-hosted" row, supersedes the off-box wording,
  gives a per-quantity table of what is citable co-hosted and in which direction it is biased, **corrects the
  `h*` lower-bound argument (true of the μ_hit leg only)**, and says the footprint is *not* an interference
  measurement.
- The off-box wording reconciled in the k6 README, `ask.js` and `mu_hit.js` (comments only), two Makefile
  banners and `experiments/README.md`. Item 1.6 closed in `super-plan.md`; Phase 1 progress 6 of 6; 7.1's
  blocker marked ✅.

**Frozen values and contracts:** none changed. `interfaces.md` was not edited, so no version bump is owed.
**Runs invalidated: none — no runs yet** (`approvals.md`, experiment-phase note). It *relabels* the 2026-09-06
μ_hit probes (never citable) and *supersedes prose*, not a value.

**Deferred, and where it goes**

| Deferred | Owner |
| :--- | :--- |
| The interference method (a matched-burner test, or the no-generator μ_gen) | item **7.1** to design; the no-generator μ_gen is **7.5's** (⟦PENDING⟧ in ADR-001) |
| `mu_hit.js`'s verdict line prints `mu_hit ~= X` as a ceiling; co-hosted `dropped_iterations` cannot tell saturation from k6 starving | item **7.2** |
| A gate on the LLM runner's resident set (`ollama ps` is not a residency check) | any later run that needs a resident SUT |
| Lowering the sampler's own cost (≈ k6's below ~16 req/s) | Phase 7, if it runs the sampler at 1 Hz |
| The "lower bound on `h*`" prose in `CLAUDE.md:162-167` and `Final_Proposal.md` §7 `:345` / §9.4 `:460` | **the author** |
| Whether `make footprint` may delete `t1:`/`t2:`/`lru:` keys (deviation 4) | **the author** (`approvals.md`) |
| The memory-pressure sensor's encoding; `make measure`'s `!= 0` gate | **the author**, outside this task |
| `make lint` silently skips ruff when it is not on `PATH`; `make check` cannot fail; `/verify`'s proto-drift row checks nothing | recorded in `super-plan.md`, unfixed |

**Follow-up worth a new task:** an investigation of the pressure sensor (`/investigate`): one command read while
Activity Monitor's graph is green settles whether `make measure` can ever pass, and Phase 7 depends on it.

**Suggested commit** (not run). The evidence directories hold the author's process names and local paths:
review `evidence/footprint*/header.json` and the k6 stdout/stderr files before `git add`.

```
Item 1.6: measure the co-hosted k6 footprint and record ADR-001

k6 costs 1.0 -> 4.8 % of one core at 2 -> 32 req/s, so co-hosting is adopted unmitigated under the
pre-registered rule. ADR-001 says what is citable co-hosted (a bound, an indicative reading, or nothing, never
a ceiling) and corrects the h* lower-bound argument, which holds for the mu_hit leg only. Adds the
loadgen_footprint sampler (61 tests, 25-fault mutation check) and `make footprint`.
Task: docs/work/2026-10-06-loadgen-footprint/  (scope L)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
```
