# Impact — resolve-f1

*`impact-analyst` (opus), 2026-10-04. Recorded as returned. Corrections it forced on `spec.md` and
`design.md` are applied there and listed at the end.*

> ⚠️ **This changes a frozen value**: `OLLAMA_NUM_PARALLEL = 4`, recorded at `docs/decisions.md:59`
> and `docs/contracts/interfaces.md:507`. It needs **ADR-003**. **No `run_id` exists to
> invalidate.** The ADR does void two pieces of the W5 spike record: the "aggregate at
> `NUM_PARALLEL=4`" label on μ_gen, and the whole `NUM_PARALLEL` axis of the spike grid. Freezing
> at 1 is also the spike's own pre-registered no-go branch: *"admission pool admits one generation
> at a time … degenerates to a mutex … proposal §5/§6.2 must be reframed around queueing and
> shedding"* (`git show 21aaaec^:.claude/commands/spike.md`, "Go / no-go"). The ADR has to say that
> branch fired. `Final_Proposal.md:338` asserts the opposite.

## Packages touched

| Path | Change | Layering |
| :--- | :--- | :--- |
| `Makefile:22-26, 40-43, 48-67` | export 4→1, spike echo, env-check rewrite | command surface (`architecture.md` §4) |
| `experiments/scripts/<detector>.py` (new) | argv parser + decision | measurement-protocol home (`architecture.md:121`) |
| `experiments/tests/test_<detector>.py` (new) | offline pytest | already wired: `Makefile:273`, `experiments/tests/conftest.py:7` |
| `gateway/cmd/gateway/main.go:155-173` | default 4→1, comments | config only, allowed (`architecture.md:42`) |
| `experiments/scripts/verify_admission.sh:15-17` | stale comment | — |
| docs: `decisions.md`, `interfaces.md:507`, `CLAUDE.md`, `README.md`, `super-plan.md`, `experiments/README.md` | text | — |
| `~/Library/LaunchAgents/com.thesis.ollama-env.plist` (outside the repo) | `setenv OLLAMA_NUM_PARALLEL 4` → 1 | — |

`gateway/internal/*`, `rag/` and `contracts/` are not touched. No import points left.

## 1. Every live occurrence

**Must change with ADR-003 (tracked):**

| Location | Content |
| :--- | :--- |
| `Makefile:22-26` | comment + `export OLLAMA_NUM_PARALLEL := 4`. ⚠️ This export pins the **gateway**: `make dev` inherits it into `go run ./cmd/gateway` (`Makefile:135-136`). It does **not** pin a terminal-launched Ollama, so the comment at `:23-25` is wrong. Rewrite it |
| `Makefile:41` | spike echo `OLLAMA_NUM_PARALLEL=4` |
| `Makefile:49-56` | launchd test against the literal `"4"` and the `(frozen: 4)` print |
| `Makefile:57-66` | the `pgrep` FAIL plus the F1 text at `:64-65` (drop it, see §8) |
| `gateway/cmd/gateway/main.go:155-164` | comment "frozen at 4" + F1 note |
| `main.go:165` | `getenvInt("OLLAMA_NUM_PARALLEL", 4)`. Only applies outside make |
| `main.go:168` | ⚠️ `GEN_QUEUE_BUDGET` defaults to `2*permits`, so the **queue default silently drops 8 → 2**. `spec.md` put queue re-sizing out of scope, but this change re-sizes it anyway. ADR-003 must accept that explicitly. It is permissible: `main.go:167` labels the queue budget a DEMO value, not a frozen one |
| `main.go:170-172` | startup log text about F1 |
| `CLAUDE.md:147-149` | "frozen at 4 … μ_gen ≈ 28.2 tok/s aggregate at that pair" |
| `README.md:40-42` | "28.2 tokens/sec aggregate at … `OLLAMA_NUM_PARALLEL = 4`" |
| `docs/decisions.md:41-44` | summary table: add ADR-003 |
| `decisions.md:59` | inherited row. Amend it to point at ADR-003 rather than deleting it (`:14`: never delete) |
| `decisions.md:73` | F1 open question: mark it resolved by ADR-003 |
| `docs/contracts/interfaces.md:507` | "`OLLAMA_NUM_PARALLEL = 4` (the memory envelope, from the feasibility spike)". The spec's list of pins omitted this line and `README.md:41` |
| `experiments/scripts/verify_admission.sh:15-17` | "reproduce the exact 4x200 / 4x503 split". With `N_DISTINCT=8` (`:22`) and 1 permit at queue 0 it will print 1×200 / 7×503 |
| `docs/super-plan.md:86-87` | standing constraint 1 says "open". Update at `/done` |
| `super-plan.md:113` | says the check reads "from the Ollama server log". The proposal reads runner **argv** instead. Amend the wording or record the deviation in the ADR. The Exit line at `:107` is satisfied either way |
| `experiments/README.md:5` | add the detector to the `scripts/` row |

**Out of repo:** the plist (verified: `ProgramArguments = launchctl setenv OLLAMA_NUM_PARALLEL 4`,
`RunAtLoad`). After editing it, run `launchctl setenv`. Restarting Ollama is optional for the
effective value but needed for the requested value. The running server (pid 19379, up since
2026-09-06) was started with 4.

**Already consistent, no change:** `docs/data-card.md` (no occurrence; `:79` "permits" is
unrelated) and `docs/architecture.md` (no value; `:49` "permit pool" is generic).
`super-plan.md:40, 225, 245` cite 0.19 req/s, which survives (§4).
`.claude/agents/impact-analyst.md:27` names the variable but carries no value.

**Historical, leave:**
- `gateway/internal/admission/pool_test.go:21` (`const permits = 4`): a mechanism test independent
  of the frozen value, and tests are immutable.
- `docs/work/2026-10-03-pqa-category-choice/spec.md:307-308` (closed trail).
- Git history: old ADR-017/022/027, W05/W06/W08 worklogs, the w6 review.
- `docs/learning/Pre-Thesis_Report_Full.md:460, :969` and `Slim.md:632`: submitted Aug 31,
  gitignored.
- `docs/learning/00-llm-basics.md:58`: the void "~0.1 GB, NUM_PARALLEL 1→4" grid claim. Optional
  fix.

**`Final_Proposal.md` follow-ups (gitignored, do not edit here):**
- §3 `:105`
- §6.0 `:260` ("~1 GB per concurrent sequence … what the permit pool exists to bound")
- §6.1 `:275` ("sized to the parallel-generation ceiling")
- §6.2 `:282`, `:284` (promises a "documented `OLLAMA_NUM_PARALLEL` sweep", which is impossible for
  `qwen35` on this stack)
- §7 `:330`, `:337`
- **`:338`**: "sized against a real 4-way ceiling … never degenerated into a mutex. §3's and §6's
  framing therefore stands." **This is now false.**
- `:339` ("one batch of four concurrent requests")
- §9.1 `:381` ("from the feasibility spike's `OLLAMA_NUM_PARALLEL` sweep")
- §9.4 `:469` (permit count as a memory proxy because the footprint is "nearly flat across the
  `num_ctx × NUM_PARALLEL` grid")
- §11 `:569`
- The §5/§6.2 reframing required by the spike's go/no-go clause.

## 2. Module boundaries

The proposed location respects the layering, and `architecture.md` names nothing better.

- `experiments/` owns "the measurement protocol" (`architecture.md:121`).
- A gate already lives there with its tests: `corpus_gate.py`, `test_corpus_gate.py`.
  `experiments/README.md:5` also lists the "admission self-check".
- `make test` runs `pytest experiments/tests` (`Makefile:273`) and `make lint` covers it with ruff
  (`Makefile:279`).

Alternatives that are wrong:
- `rag/` is the serving package (`architecture.md:55`), and it should not own measurement
  validity.
- `gateway/` is Go, and `main.go` is wiring only (`:42`).
- A new top-level `tools/` is forbidden: "A directory not listed here should not exist"
  (`architecture.md:15-16`).

`architecture.md:65` annotates `scripts/` as "workload gen, replay, judge, figures". Adding
"gates" is an optional S-sized doc sync.

Read the frozen tag and `num_ctx` from `rag.config` (`config.py:37`, `:44`) rather than keeping a
second copy. Import it **lazily inside `main`**, as `corpus_gate.py:504-505` does, so the offline
suite needs no `rag`/Ollama. The direction is experiments → rag, which is allowed.

## 3. Frozen values, measured paths, invalidated runs

**Frozen values touched:** `OLLAMA_NUM_PARALLEL` (4 → 1). `num_ctx` is read by the detector but
not changed.

**Measured paths touched:**
- Admission permits 4 → 1, which changes what `shed`, `permit_queue_depth` and
  `t_permit_wait_ms` mean (§H, `interfaces.md:462, 465-466`).
- The queue default 8 → 2 (`main.go:168`).
- The `make measure` validity gate (`Makefile:102`).

**`run_id`s: none.** `experiments/results/` holds only `.gitkeep`, in the working tree and in all
25 commits. No `manifest.yaml` or `requests.jsonl` exists anywhere on disk.

**Prior numbers, by source:**

| Source | Status under ADR-003 | Ever citable? |
| :--- | :--- | :--- |
| **W5 spike, 2026-08-15**: μ_gen 28.2 tok/s, 1.7 GB, "4 concurrent, 8.9 s" (`21aaaec^:docs/decisions.md:200-201`; `21aaaec^:docs/experiment-protocol.md:37-45`) | **Value kept, label voided.** The grid's `NUM_PARALLEL` axis is **void**. Surviving spike-day logs (`~/.ollama/logs/server-{5,4,3}.log`, 2026-08-15 18:59 → 08-16 19:54) show **9/9 server starts *requesting* `OLLAMA_NUM_PARALLEL:1`** and 9/9 runners at `-np 1`. So the 1→4 "~0.1 GB, nearly flat" result compared one configuration with itself. That voids old ADR-022's memory-proxy rationale (`21aaaec^:docs/decisions.md:307`) and `Final_Proposal.md:469`. Logs before 18:59 have rotated, hence "on surviving evidence" | Not `dev-v0`. It was treated as citable: a frozen value, quoted in submitted prose |
| **2026-09-06 A3 check**, "4×200 / 4×503" (`21aaaec^:docs/worklog/W08.md:478`) | Still valid as a demo of a 4-permit pool at queue 0. It made no claim about Ollama, and it won't reproduce under the new default | No: `dev-v0`, and `verify_admission.sh:5-7` says "NOT citable" |
| **2026-09-06 μ_hit probes**: tier1 ≈ 8000, tier2 ≈ 61 req/s, and the "urgent" Tier-1 run (`W08.md:518`) | Unaffected. 100 % hits, and hits take no permit | No: co-hosted, `dev-v0` |
| **W6 sequential latencies** (`21aaaec^:docs/worklog/W06.md:146`) | Unaffected; sequential (`W06.md:304-306`) | No |
| **Shed rates, p99, permit-queue depth** | **None was ever recorded** in tracked history | — |

## 4. Where μ_gen ≈ 28.2 tok/s and ≈ 0.19 req/s come from

- **28.2 tok/s.** The W5 spike was run by hand following a procedure, not a script: the `/spike`
  command, deleted, at `21aaaec^:.claude/commands/spike.md`. **No spike script and no raw output
  exist anywhere.** `make spike` (`Makefile:40-43`) only echoes and prints `vm_stat`. The number
  is recorded only in prose: old ADR-017 (`21aaaec^:docs/decisions.md:200-201`, "one batch of
  concurrent requests to completion", 4 requests, 8.9 s), the old protocol §1.1 (`:45`), and
  `W05.md:30-31`. It was measured on Ollama **0.32.13**, upgraded mid-spike from 0.22.1
  (`21aaaec^:docs/worklog/W05.md:27-28`). The live server is **0.33.2**. **The Ollama version is
  pinned nowhere in the tracked tree**, which is a frozen-envelope gap the ADR should name.
- **0.19 req/s** = "28.2 tok/s ÷ ~150 output tokens" (old ADR-027,
  `21aaaec^:docs/decisions.md:436`). **There is no ×4 factor.** It treats 28.2 as the whole
  server's aggregate, which it was: one slot. So 0.19 stays numerically valid as an aggregate
  projection. Only the "at `NUM_PARALLEL = 4`" label was ever false.
- **Arithmetic inference (method unrecorded; assumes 28.2 = total output tokens ÷ wall time):**
  - 28.2 × 8.9 s ≈ 251 tokens, or about 63 tokens per request.
  - At that length the batch itself delivered about 0.45 req/s. So **0.19 is a projection at an
    assumed ~150-token answer, not a measurement** (`docs/learning/00-llm-basics.md:82` says
    ~148).
  - 63 / 28.2 ≈ 2.2 s per request, and × 4 ≈ 8.9 s. That fits serial service at one slot.

## 5. Reinstates cut scope?

No. Nothing on `Final_Proposal.md:590`'s list is touched. Admission control stays non-negotiable
(`:586`), but it becomes a 1-permit pool plus a bounded queue.

## 6. New dependency?

None, as long as the detector uses only the stdlib (`subprocess` for `ps` and `ollama show`) and
the existing `ollama` CLI. **Do not add `psutil`.** pytest and ruff are already dev dependencies
(`rag/pyproject.toml:23`). The detector has no resident footprint. It may *load* the LLM (about
1.7 GB), but that is inside the envelope already measured.

## 7. Contract change?

**No §A–§H surface changes.**
- §H carries `shed`, `permit_queue_depth` and `t_permit_wait_ms`, but never the permit count or
  `ollama_num_parallel`.
- No run-manifest schema exists (`decisions.md:74`, P1). The old one carried `ollama_num_parallel`
  (`21aaaec^:docs/experiment-protocol.md:65`) and was deleted.
- `interfaces.md:507` is the Versioning restatement of frozen values, not a wire shape (`:497`).
  Edit it citing ADR-003; no version bump needed.

**Contract phase is not required** (§B/§D untouched). Forward note for P1: the manifest must
record the **effective** slot count from the detector, not the requested env value.

## 8. Measurement change?

**Yes. The experiment phase is required.**
- Permits 4 → 1 moves the generation queue out of Ollama (where it was invisible) into the
  gateway. Item 7.5's shed rate and permit-queue depth then measure a different, honest quantity.
- The queue default changes 8 → 2 (`main.go:168`).
- The `make measure` admissibility gate changes. That is an RR-class change.
- μ_gen keeps its value, but its meaning is restated.
- Inference, not measured: `rag/src/rag/server.py:50` (`max_workers=4`). With 4 permits, up to 4
  Answer RPCs could hold every gRPC worker. The `Retrieve` that every Tier-1 miss issues
  (`interfaces.md:485`) then queued behind them. At 1 permit, 3 workers stay free, so
  cascade-band latency under mixed load shifts.

For the experiment phase to settle:
- env-check is a point-in-time check. The runner unloads after `OLLAMA_KEEP_ALIVE:5m` and reloads
  mid-run, so decide whether to re-check at run end.
- No make target launches a *measured* gateway (`make dev` is functional-only, `Makefile:114`).
  The run must record the gateway's logged `admission permits=` (`main.go:170`) and assert it
  equals the frozen value.

## 9. Other readers of `OLLAMA_NUM_PARALLEL` / concurrency assumptions

| Location | Effect |
| :--- | :--- |
| `main.go:165`, `:168` | covered in §1 |
| `Makefile:26` → `:135-136` | the real source of the permit count under `make dev` |
| `make dev` (`Makefile:114`) | depends only on `redis-check`, **not** on env-check. Only `measure` (`:102`) is affected. Today `:57-66` makes `measure` unpassable while Ollama runs, and the detector *requires* Ollama to run, so dropping `:57-66` is **necessary**, not cosmetic |
| `verify_admission.sh:15-17, 22` | stale comment (§1) |
| `load_burst.py:123` (`--concurrency 25`) | no tie to 4. Leave |
| `experiments/k6/ask.js:29-30, 99-100`; `mu_hit.js:42-43`; `k6/README.md:18, 60` | VUs and rates are arrival-model values, not sized from permits. Leave |
| `coalesce_test.go` | no hard-coded 4. Leave |
| `pool_test.go:21` | mechanism test. Leave |
| `rag/server.py:50` (`max_workers=4`) | matched the old value by coincidence (`21aaaec^:docs/worklog/W06.md:89-96`), not the frozen value. Leave; at most a note in the ADR's consequences |

**Detector pitfalls the design should cover:**
- Match the runner on the `--model` value only. The `qwen35` runner also carries `--mmproj <blob>`.
- `n_ctx_slot = -c / -np`. A realistic `-np 4` fixture likely carries `-c 32768` (speculative;
  Ollama multiplies `num_ctx` by the slot count). Compare `-c / -np` to `num_ctx`.
- If the detector loads the model itself, it must send `options.num_ctx = 8192`. `generate.py:44`
  does; without it the runner spawns at a different `-c`.
- Use `ps -axww` so argv is not truncated (precaution).
- No runner is loaded right now. Live `ps` shows only `ollama serve` (pid 19379), so "not loaded"
  is the default live state.

## Smallest change that satisfies the spec

**Keep:**
- ADR-003.
- A stdlib-only argv detector plus offline tests.
- The env-check rewrite: delete `:57-66`, compare the launchd value to the frozen value, then call
  the detector.
- The pin edits listed in §1.

**Make explicit in ADR-003, not silent:**
- The queue default 8 → 2.
- The spike's go/no-go branch firing.
- The voided grid axis.
- The Ollama version drift.

**Cut:**
- Parsing the server log as well as argv. The log location varies by launch method: the live
  server logs to `/private/tmp`.
- A Go-side startup self-check.
- Renaming the gateway's env var.
- Touching `server.py:50`, the embedding runner, the manifest schema (P1), or re-measuring μ_gen
  (Phase 7).

## Invalidates

No `run_id`s: none exist. ADR-003 relabels μ_gen ≈ 28.2 tok/s (and 0.19 req/s) as a one-slot
server aggregate, and it voids the W5 spike's `NUM_PARALLEL` 1→4 grid axis and the "flat
footprint" memory-proxy rationale built on it. No admission number is voided, because none was
ever recorded; the only one, A3's 4×200/4×503, was a non-citable `dev-v0` check.

> **Required phases:** impact · **experiment** · implementation, plus design → opus design-review →
> plan for scope L. **Contract not required:** no §A–§H surface changes.

---

## Corrections this forced on the trail

| # | Was | Now |
| :---: | :--- | :--- |
| 1 | `spec.md`: "every shed rate and p99 measured so far partly describes Ollama's internal queue" | **None was ever recorded.** The claim was withdrawn, and the risk is restated as forward-looking |
| 2 | `spec.md` out of scope: queue re-sizing | The queue default **does** change, 8 → 2, as a consequence of the permit rule. It is accepted explicitly in the ADR and still not swept |
| 3 | `design.md` §4 pins | `interfaces.md:507`, `README.md:40-42`, `Makefile:41`, `verify_admission.sh:15-17`, `super-plan.md:113` (log → argv deviation) and `experiments/README.md:5` added |
| 4 | `design.md` §5: V1 verification run | Re-weighed in `design.md` §5: the surviving spike-day logs and the arithmetic already favour one slot, and V1 on 0.33.2 is confounded by the 0.32.13 → 0.33.2 version change |
| 5 | `design.md` U2, U5 | Resolved: 0.19 = 28.2 ÷ ~150, no ×4; the lazy `rag.config` import follows `corpus_gate.py:504-505` |
| 6 | — | New in the ADR: the spike's no-go branch fired. Pin the Ollama version (0.33.2), now that the envelope depends on a version-specific scheduler rule |
