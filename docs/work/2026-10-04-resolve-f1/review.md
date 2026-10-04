# Design review — resolve-f1

**Reviewer:** `design-reviewer` (opus), 2026-10-04, read-only and with no model loaded. Findings
marked **CONFIRMED** were re-checked by hand against the machine before being recorded.

**Verdict: sound with changes.**
- Option A is right, the detector is the right shape, and dropping V1 is right.
- **One finding blocks (B1).** ADR-003 must state that A changes what S2 and the admission
  metrics mean.
- Seven should-fix findings tighten the ADR's evidence and the detector. None needs a redesign.

## Findings and resolutions, most severe first

| # | Sev. | Finding | Check | Resolution |
| :---: | :---: | :--- | :---: | :--- |
| **B1** | **blocking** | **Under A the permit pool no longer bounds memory.** Ollama's scheduler holds `qwen35` to one slot whatever the gateway admits, so the pool bounds **waiting**, not memory. Live text still claims the memory mechanism: `CLAUDE.md:122-123`, `:157-159`; `README.md:31-32`; `admission/pool.go:1-2`; `super-plan.md:40`, `:50`. Acceptance 5 greps only for "4", so none of it would be caught. The meaning of `shed`, `t_permit_wait_ms`, `permit_queue_depth` **and `t_generate_ms`** moves: the last loses the Ollama-internal wait it used to absorb. The spike's go/no-go clause required this reframing before 2026-08-31, and the draft deferred it a second time with no owner | reasoned | **Accepted.** The ADR restates S2: *the pool protects queueing delay and goodput; under offered miss load above μ_gen, admitted latency ≤ (1+q)·S, overload surfaces as counted 503s, goodput does not collapse; memory is bounded by Ollama's one-slot scheduler.* The six places become wording changes in `design.md` §4. The proposal's §5/§6.2 reframing becomes a `super-plan.md` row with a binary done-condition |
| **S1** | should-fix | **The ADR's evidence includes an identity.** "28.2 × 8.9 ≈ 251 tokens … × 4 ≈ 8.9 s fits serial service" holds for **any** slot count once 28.2 = tokens ÷ wall time. Also, `impact.md`'s "9/9 runners" includes 4 `nomic-bert` runners: on the spike build the `qwen35` runners are **5 / 5 at `-np 1`**. The best surviving record was not cited: in `server-5.log:1142-1245`, four `POST /api/generate` requests submitted within ~1 s of 19:03:22 completed at **11.3, 16.6, 26.4 and 30.2 s**, one after another. That is a concurrent batch served serially, on the spike build, though at `-c 4096` on a server requesting 1 | **CONFIRMED** (completion stamps 19:03:33 / :39 / :49 / :52; start ≈ 19:03:22 for all four) | **Accepted.** The arithmetic is struck. The ADR cites 5 / 5 `qwen35` runners at `-np 1`, 9 / 9 server starts requesting 1, and the 19:03:22 batch as corroboration. It states that the batch which produced 28.2 is in no surviving log and that its method is unrecorded |
| **S2** | should-fix | **"The runner's argv is the effective configuration" is false in general.** The bundled `llama-server` has its own slot rule (`n_parallel is set to auto, using n_parallel = 4 and kv_unified = true`) and reads `LLAMA_ARG_N_PARALLEL` / `LLAMA_ARG_KV_UNIFIED` / `LLAMA_ARG_FIT*` from an environment no one can read back. Argv is what Ollama *asked for*. Its agreement with `n_slots` in 26 / 26 loads is a property of the 0.33.2 build | **CONFIRMED** (`strings` on the runner: all three present, plus `total_slots`) | **Accepted, option (a):** read `GET http://127.0.0.1:<runner --port>/props` → `total_slots`, `n_ctx`. Require argv and `/props` to agree, and fail if `/props` is unreachable. U9 verifies `/props` on 0.33.2. If it is absent, fall back to (b): the version pin is what licenses argv as effective, and it becomes mandatory |
| **S3** | should-fix | **U6 reads the wrong version, and the pin will not hold.** `ollama --version` can print the *client* version (`Warning: client version is …`, or after "could not connect"), so a substring match can pass wrongly. The 0.32.13 → 0.33.2 drift was an **unattended auto-update** on 2026-09-01. Auto-update is on, the checker runs hourly, and no 0.33.2 bundle is cached to restore from | **CONFIRMED** (`/api/version` → `0.33.2`; app DB `auto_update_enabled = 1`; `app-1.log` "performing update at startup" 2026-09-01 10:03:29; hourly checks 2026-08-17) | **Accepted.** Compare `/api/version` (already fetched in step 2). The ADR also: **(a)** has auto-update disabled, or moves off Ollama.app to `ollama serve` under a LaunchAgent (author decision); **(b)** records a restore artifact, the v0.33.2 download URL and its sha256; **(c)** names the launch method, since the app's server runs `OLLAMA_CONTEXT_LENGTH:262144` |
| **S4** | should-fix | **The detector is not tied to the server the RAG service uses.** Step 2 hardcodes `:11434` while `rag/config.py:22` makes `OLLAMA_BASE_URL` overridable. The runner is matched by blob alone, and two servers sharing `~/.ollama/models` see identical blob paths | reasoned | **Accepted.** The URL comes from `rag.config`. The runner's parent PID must equal the PID listening on that port (`lsof -nP -iTCP:<port> -sTCP:LISTEN -t`). New test: a matching runner under a foreign parent → `NoRunner` |
| **S5** | should-fix | **A mid-run reload is silent on this machine.** The Ollama app's `selected_model` is the frozen model with `context_length` 262144. One chat in the app during a run takes the only slot (F1's invisible queue, arriving from outside the gateway) and reloads the runner at a different `-c`. No error results, only two loads' worth of latency in `t_generate_ms` | **CONFIRMED** (app DB `selected_model = qwen3.5:2b-q4_K_M`, `context_length = 262144`) | **Accepted.** `env-check` prints one machine-readable line: server PID, runner PID, `/api/version`, `-np`, `-c`, `total_slots`, blob digest. The experiment phase re-checks at run end and requires the same runner PID. Recorded as a run rule: no use of the Ollama app during a run |
| **S6** | should-fix | **The queue default 8 → 2 is a headline-sized side effect.** At one slot the pool is a single-server queue with 1 + q places. As an illustration (M/M/1/K, Poisson), shedding is ≈ 6.7 % at ρ = 0.5 and ≈ 17 % at ρ = 0.8 for q = 2, against ≈ 0.1 % and ≈ 3 % for q = 8. The default rule would pick an S2 number | reasoned (queueing illustration, not measured) | **Accepted.** One ADR sentence: q becomes a **pre-registered parameter of item 7.5**, recorded per run, and no shed rate is read at an unregistered default. Note: `Retry-After: 2` (`interfaces.md:161`) is now shorter than one service time, which is harmless for k6's open arrival model |
| **S7** | should-fix | **The frozen model is checked by tag, not identity.** An `ollama pull` after an upstream change brings a new blob, which loads, matches one runner, and passes. That is a silent model swap | reasoned | **Accepted.** The ADR pins the weights blob digest (`sha256-7a3a8d55…`), and the detector compares it. One line, one test |
| N1 | note | "requested" is mislabelled. Step 1 reads the launchd value, which only the **next** server start inherits. pid 19379 was started with 4 | — | Relabelled "launchd (next start)". Acceptance 6 includes an Ollama restart. **Superseded if the author takes A2 (below)** |
| N2 | note | Step 1's second comparison compares `$(OLLAMA_NUM_PARALLEL)` with itself | — | Dropped |
| N3 | note | Step 3 leaves `keep_alive` unspecified. 0 races the `ps` read; −1 pins 1.7 GB indefinitely | — | Omitted, as `generate.py:37-46` omits it (the server default applies) |
| N4 | note | Load `nomic-embed-text` too, so `measure` reads pressure with both models resident (~2.1 GB) | — | Accepted: one embed call in step 3 |
| N5 | note | Treat `-np`/`--parallel` and `-c`/`--ctx-size` as aliases, failing on a repeat across them. Match the blob on its `sha256-…` token, not the full path | — | Accepted, with tests |
| **N6** | **note → author decision** | **The launchd variable is machine-wide.** Changing it 4 → 1 also takes slots from other projects' models that *do* run in parallel | — | **Opens a choice for the author: A1 vs A2** (`design.md` §2). Under A the launchd value has no effect on either thesis model (`qwen35`: forced 1; `nomic-bert`: 48 / 48 at `-np 1` under 4), so pinning it buys the thesis nothing and costs other projects |
| N7 | note | The permit covers the Answer RPC plus write-back (`handler.go:380-457`), so at one permit the slot idles during gRPC and Redis work. A gateway-measured μ_gen ≤ Ollama's | — | Recorded for Phase 7: name which μ_gen is measured |

## V1 — the reviewer's answer

**Dropping V1 is right.**
- It cannot recover the 2026-08-15 batch.
- It would run on a different build.
- Nothing citable rests on 28.2. S1's inequality h\* > 0.988 holds for any μ_gen < μ_hit·(1/0.988 − 1)
  ≈ **0.74 req/s** at the co-hosted 61 req/s, which is 3.9× the 0.19 projection. That is
  arithmetic on planning figures, and the ADR labels it so.

**But the ADR says less than the draft did:**
- It withdraws the "= 4" label.
- It states: *"On all surviving evidence, every qwen35 runner served one slot. The batch that
  produced 28.2 is not among the surviving logs, and its method is unrecorded."*
- It calls 28.2 tok/s and 0.19 req/s **planning figures until Phase 7**.
- It corrects `super-plan.md:40`'s "frozen … at ≈ 0.19 req/s".

## New unknowns

- **U9:** does `GET /props` on the Ollama-spawned runner return `total_slots = 1` and `n_ctx = 8192`
  on 0.33.2? Checked during U4's load.
- **U10:** at startup Ollama.app logs "terminating other ollama instance" (`app-5.log`, 2026-08-15
  18:59:22). Does it also kill a LaunchAgent-run `ollama serve`? The answer decides whether the
  app must leave login items, if the author chooses that route under S3(a).

## Checked and found sound

- **A over B, C and D.** C is excluded by the frozen model and serving stack; D is a mid-study
  stack change; B keeps an environment value that has no effect.
- **Reading argv rather than the log**, as the place to find the configuration. What argv
  *proves* is S2.
- **The fail-closed contract**, and test 3 (the embedding runner alone) as the silent-pass test.
- **`ollama show --modelfile`** returns exactly one `FROM` line, and matching on `--model `
  handles `--mmproj`.
- **`ps` argv cannot be rewritten** by the parent after exec.
- **Removing the `pgrep` rule** is necessary, and loses nothing it verified.
- **Ollama.app and `ollama serve` use the same runner binary**: `/usr/local/bin/ollama` is a
  symlink into the bundle.
- **`-c = num_ctx × np`.** At np = 1 it reduces to `-c == 8192`, and at np ≠ 1 the slot check
  fails first.
- **Placement, stdlib only, and the lazy `rag.config` import.**
- **No cut scope is reinstated**, and the hit path and its determinism are untouched.

---

# Implementation review — `/ai-review`, 2026-10-04

**Reviewer:** `contract-reviewer`, routed by the `interfaces.md` edits. `design-reviewer` does not
apply after implementation; its pre-implementation review is above. The reviewer read
`interfaces.md`, `architecture.md` and ADR-003 itself. It did not run the code, and it read the
trail only in part. Findings marked **CONFIRMED** were re-checked by hand.

**Verdict.** No contract breach. Both `interfaces.md` edits are prose or a frozen-value
restatement, with no change to §A–§H wire shapes, the §B proto, the §D Redis schema or the §H
fields, so **no version bump is needed** and v0.9 stands. The frozen values agree across the
Makefile, `main.go`, ADR-003, `interfaces.md`, `CLAUDE.md`, `README.md` and `super-plan.md`. No path
in `env_check.py` prints OK on a mismatch, and every exception exits non-zero.

| # | Finding | Check | Resolution |
| :---: | :--- | :---: | :--- |
| 1 | **A live "the pool bounds memory" statement remains in the UI**: `ui/src/Counters.jsx:63` ("rather than admitted past the memory envelope"). The UI is the first thing a reader of the demo sees | **CONFIRMED**, plus **two more the reviewer missed**: `ui/src/pages/ProductChat.jsx:119` ("work that would push the machine into swapping") and an `ui/src/api.js:20` comment | **Fixed**, all three now worded as queueing behind the one generation slot |
| 2 | **`gateway/internal/admission/pool_test.go:17-19`**: the comment "if more than `permits` generations can be in flight … a run can swap" is a stale memory claim. The test itself (`const permits = 4`) is parametric and still valid | **CONFIRMED** | **Fixed, comment only, with the author's explicit confirmation** (`approvals.md`, 2026-10-04: "ok sửa comment đi"), since test files are immutable. No code or assertion changed, and `go test -count=1` passes. The suggested extra `permits = 1` case was **declined**: the parametric test already covers the mechanism, and adding coverage there is outside this task |
| 3 | **The gateway's permit count is never checked against the runner.** `main.go` takes permits from `OLLAMA_NUM_PARALLEL`, a variable shared with Ollama's own. A gateway started outside `make` from a shell that kept the old 4 runs 4 permits against 1 slot while `env-check` passes: F1 again, from the gateway's side | **CONFIRMED, not hypothetical**: this session's own shell still carries `OLLAMA_NUM_PARALLEL=4`, inherited from launchd before the plist was removed, and `verify_admission.sh` documents an out-of-make launch (`go run ./cmd/gateway`) | **Fixed (warning):** `main.go` names the frozen value as `const frozenSlots = 1` and logs a loud `WARNING` when the permits differ. It warns rather than refuses, because a demo may size the pool on purpose. **Residual, already recorded** (`design.md` F-7): a measured run asserts permits == `ENVELOPE np`, part of the P1 manifest |
| 4 | **The I/O half of `env_check.py` was untested.** These could regress silently: `main()` returning 1 on an exception, `_listener_pid` with zero or several listeners, the non-local `OLLAMA_BASE_URL` refusal, and the `observe()` wiring (the matched blob passed to `find_llm_runner`, `/props` fetched from that runner's own port) | **CONFIRMED** | **Fixed: 7 tests** with faked HTTP, `ps` and `lsof` and a stand-in `rag.config`: observe matches the LLM runner and fetches its `/props`; a runner override reaches `check`; a non-local server is refused; zero or two listeners are refused; `main` exits 1 when the envelope is unverifiable, 1 on a malformed pinned blob, 1 on a mismatch, and 0 with the `ENVELOPE` line on a match. The warm-up body is asserted equal to `{model, options:{num_ctx}}` |
| 5 | **Two `check()` conditions were not isolated.** The context test failed through both `-c` and per-slot `n_ctx` at once, so deleting either condition stayed green. The 4-vs-1 test asserted only `"4" in f and "1" in f` | **CONFIRMED** | **Fixed:** two isolated tests (`-c 4096` alone; `/props n_ctx 4096` alone), each asserting the exact message. The 4-vs-1 assertion is **strengthened** to the exact message. That test was written in this task and is uncommitted, and it was tightened, not weakened |
| 6 | **Nothing re-checks the runner at run end.** It unloads after the 5-minute `keep_alive` and could come back changed | PLAUSIBLE, low | **Accepted, deferred** by the experiment approval (`approvals.md`): no target launches a measured gateway yet, so the run-end `ENVELOPE` re-check (same `runner_pid`) belongs to the P1 manifest work |

**Re-verified after the fixes:** `make verify` exit 0; `experiments/tests` 94 / 94 (44 in
`test_env_check.py`); `make lint` clean, after sorting the imports and replacing a `str.join` that
`FLY002` flagged.

**Open:** none. Every finding is fixed or accepted with a named follow-up.
