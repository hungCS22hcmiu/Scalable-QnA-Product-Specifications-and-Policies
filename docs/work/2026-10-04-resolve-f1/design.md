# Design — resolve-f1

**Revision 2**, after `impact.md` and `review.md`. It reads with `spec.md` (the finding and the
acceptance checks) and `evidence/ollama-np-override.txt`.

## 1. Two parts, one decision

| Part | What | Reversible? |
| :--- | :--- | :--- |
| **Decision** | The frozen slot value, what it means for S2, and what μ_gen ≈ 28.2 tok/s means under it → **ADR-003** | It is a frozen value. Changing it again needs another ADR |
| **Detector** | `make env-check` establishes the **effective** envelope from the live runner and fails closed | Yes. Tooling only |

## 2. The decision

### Freeze the effective slot count at 1 (Option A)

| | Option | Verdict |
| :---: | :--- | :--- |
| **A** | **The effective slot count is frozen at 1, and the gateway grants 1 permit** | **Recommended** (`review.md`: sound) |
| B | Keep requesting 4, freeze effective = 1, and size permits from a new variable | Rejected: it keeps a "4" that has no effect |
| C | Make 4 real (a model Ollama parallelises, or raw `llama-server -np 4`) | **Excluded** by the frozen model and serving stack |
| D | Upgrade Ollama in the hope that a later build parallelises `qwen35` | Not now: unknown support, and a mid-study stack change |

**Why A:**
- It is the only option where the permit count matches what the server serves.
- It describes what was actually measured. On all surviving evidence, every `qwen35` runner
  served one slot.
- The gateway can shed again: the second concurrent miss waits or is shed *in the gateway*,
  where it is counted, instead of queueing invisibly inside Ollama.
- **The study chose it in advance.** The W5 spike's go/no-go clause named this outcome (*"degenerates
  to a mutex"*) and prescribed reframing §5/§6.2 around queueing and shedding.

### A1 or A2 — does the machine-wide launchd value change? **Decided 2026-10-04: A2** (`review.md` N6)

| | A1 — pin launchd at 1 | **A2 — remove the launchd pin** |
| :--- | :--- | :--- |
| What is frozen | `OLLAMA_NUM_PARALLEL = 1`, requested machine-wide | The **effective** slot count (1), verified by the detector; permits = 1 via the Makefile |
| Effect on the thesis models | None. `qwen35` is forced to 1, and `nomic-bert` ran 48 / 48 at `-np 1` under 4 | None, for the same reason |
| Effect on other projects | **Takes parallel slots from their models** | None (Ollama's default applies) |
| If a future Ollama parallelises `qwen35` | Still 1 | Effective would change → **the detector fails**. The version pin (§5) also blocks the upgrade |
| `env-check` step 0 | launchd value = 1 ("next start") | Removed |
| The plist | edited 4 → 1 | unloaded and deleted |

**Decided: A2** (`approvals.md`). The launchd value has no effect on either thesis model, so pinning it buys
the thesis nothing and costs every other project on this machine. What the thesis depends on, the
effective value, is the thing the detector verifies.

### What A does to S2 — the blocking finding (`review.md` B1)

Under A the permit pool **no longer bounds memory**. Ollama's one-slot scheduler does that,
whatever the gateway admits. What the pool protects is **queueing delay and goodput**. ADR-003
restates S2 in those terms:

> Under offered miss load above μ_gen, admitted latency stays ≤ (1 + q) · S, where S is one service
> time and q the queue budget. Overload surfaces as counted `503`s, and goodput does not collapse.
> Memory is bounded by Ollama's one-slot scheduler, not by the permit pool.

Four §H fields change meaning, and the ADR lists them:

| Field | Meaning under A |
| :--- | :--- |
| `shed` | "would have waited more than q service times" |
| `t_permit_wait_ms` | now carries **all** of the generation wait |
| `permit_queue_depth` | the whole queue |
| `t_generate_ms` | **loses** the Ollama-internal wait it absorbed under 4 permits |

A 1-permit pool still demonstrates admission control: a single-server queue with a bounded wait
queue and explicit shedding. **Coalescing becomes more valuable**, because N identical misses
consume the only slot once. What it no longer demonstrates is **memory** governance, and that
wording is corrected everywhere live (§6). Item **8.2** owns the write-up's framing (§6).

## 3. What μ_gen ≈ 28.2 tok/s means (`review.md` S1, V1)

The ADR says **only** this:

- **Withdrawn:** the label *"aggregate at `OLLAMA_NUM_PARALLEL = 4`"*.
- **Evidence:** on all surviving evidence, every `qwen35` runner served one slot:
  - spike build: **5 / 5** `qwen35` runners at `-np 1`, and **9 / 9** server starts requesting 1
    (`~/.ollama/logs/server-{3,4,5}.log`);
  - live build: **26 / 26** (`evidence/`);
  - corroboration: a four-request batch submitted at ≈ 19:03:22 on 2026-08-15 completed
    **serially**, at 11.3 / 16.6 / 26.4 / 30.2 s (`server-5.log:1142-1245`; that load was at
    `-c 4096`).
- **Unknown:** the batch that produced 28.2 is in no surviving log, and its method is unrecorded:
  the token definition, the prompt and the output length.
- **Status:** 28.2 tok/s and 0.19 req/s (= 28.2 ÷ ~150 output tokens, no ×4) are **planning
  figures until Phase 7** re-measures μ_gen on the pinned version.
- **Planning arithmetic, labelled as such:** S1's inequality h\* > 0.988 holds for any
  μ_gen < 61 × (1/0.988 − 1) ≈ **0.74 req/s** at the co-hosted μ_hit, which is 3.9× the projection.
- **The struck argument:** "28.2 × 8.9 s … fits serial service" is an identity that holds for any
  slot count. It does not appear in the ADR.
- **No verification run (V1).** It could not recover the 2026-08-15 batch, it would run on a
  different build, and nothing citable rests on 28.2.

## 4. The detector

### Inputs — one place each

| Value | Source |
| :--- | :--- |
| Frozen slot count, Ollama version, LLM weights digest | The **Makefile's envelope block**, passed as arguments: `OLLAMA_NUM_PARALLEL := 1`, `OLLAMA_VERSION := 0.33.2`, `LLM_BLOB := sha256-7a3a8d55…` |
| `OLLAMA_BASE_URL`, `LLM_MODEL`, `LLM_NUM_CTX`, `EMBEDDING_MODEL` | `rag.config`, imported **lazily inside `main`** (as `corpus_gate.py:504-505` does). These are the values the service actually uses |

### Activity

```
make env-check  →  python experiments/scripts/env_check.py --frozen-np … --ollama-version … --llm-blob …
 │
 ├─1 GET {base}/api/version            unreachable, or version ≠ pinned ───────────────► FAIL
 ├─2 server_pid := lsof -nP -iTCP:{port} -sTCP:LISTEN -t     ≠ exactly one ───────────► FAIL
 ├─3 warm:  POST {base}/api/generate {model: LLM_MODEL, options:{num_ctx: LLM_NUM_CTX}}
 │          POST {base}/api/embed    {model: EMBEDDING_MODEL, input: "env-check"}
 │          (no prompt, no keep_alive: the server default applies, as in generate.py)
 │                                     error / timeout ─────────────────────────────────► FAIL
 ├─4 blob   := POST {base}/api/show {model: LLM_MODEL} → FROM → "sha256-…" token
 │                                     absent, or ≠ pinned digest (silent model swap) ───► FAIL
 ├─5 rows   := ps -axww -o pid=,ppid=,command=
 │   runner := rows with "llama-server", --model token == blob, ppid == server_pid
 │                                     0 → NoRunner, ≥ 2 → AmbiguousRunner ─────────────► FAIL
 ├─6 argv   := -np|--parallel, -c|--ctx-size, --port   absent / repeated / non-int ────► FAIL
 ├─7 props  := GET 127.0.0.1:{--port}/props → total_slots, n_ctx    unreachable ───────► FAIL
 ├─8 np == total_slots == frozen  ∧  -c == num_ctx × np  ∧  props n_ctx consistent ────► FAIL, printing all
 └─ OK, plus one machine-readable line:
    ENVELOPE server_pid=… runner_pid=… version=… np=… ctx=… total_slots=… blob=…
```

**Why argv and `/props` together** (`review.md` S2):
- **argv** is what Ollama *asked of* the runner.
- **`/props`** is what the runner *did*. The runner has its own `n_parallel = auto → 4` rule, and
  it reads `LLAMA_ARG_*` from an environment no one can read back.
- Requiring both to agree catches a runner that overrode its arguments.
- If U9 finds no `/props` on 0.33.2, the version pin is what licenses argv as effective, and the
  ADR says so in those words.

**Why not the server log.** It lives wherever the launcher put it: `~/.ollama/logs/` under the
app, a terminal under `ollama serve`, or `/private/tmp` today.

**Why step 3 loads the models.** No runner exists until a model loads (`/api/ps` returned `[]`
today). `CLAUDE.md` names pressure *with the model loaded* as the authoritative signal, and
`measure` reads pressure after `env-check`. So loading both models (~2.1 GB) makes that reading
the right one.

**What is removed.** The `pgrep -q ollama → FAIL` block (`Makefile:57-66`). It never verified the
served value, and it makes `measure` impossible to pass while Ollama is up, which is the only time a
measurement can happen.

**S5 — the run-end re-check.** The `ENVELOPE` line makes a run-end comparison possible without a
load: same `runner_pid`, same values. Whether `measure` requires it is an **experiment-phase**
decision. The run rule *no use of the Ollama app during a run* is recorded in the ADR. The app's
`selected_model` is the frozen model at `context_length` 262144, so one chat takes the only slot
and reloads the runner.

### Function contracts

All parsing and decision functions are pure. All I/O lives in `main`.

| Function | Contract |
| :--- | :--- |
| `parse_runner_args(argv) -> RunnerArgs(np, ctx, port, model_token)` | Integer `-np`/`--parallel`, `-c`/`--ctx-size` and `--port`; the `sha256-…` token of `--model`. Raises `Unparseable` if any is absent, repeated (including across aliases) or non-integer. Never defaults |
| `find_llm_runner(ps_rows, blob, server_pid) -> (pid, argv)` | The one row whose command contains `llama-server`, whose `--model` token equals `blob`, and whose ppid equals `server_pid`. Raises `NoRunner` / `AmbiguousRunner`. `--mmproj` carrying the same blob is not a second match |
| `blob_from_show(show_json) -> str` | The `sha256-…` token of the `FROM` line. Raises `Unparseable` if absent |
| `parse_props(props_json) -> (total_slots, n_ctx)` | Field paths fixed by U9. Raises `Unparseable` if absent |
| `check(frozen, observed) -> list[str]` | Failure messages; an empty list passes. Each message names the expected and the observed value |
| `envelope_line(observed) -> str` | The single `ENVELOPE …` line, key order fixed |
| `main(argv) -> int` | Runs the steps and prints. Exits 0 only on an empty failure list. Every exception exits 1 with its reason |

### Tests — `experiments/tests/test_env_check.py`, offline

Fixtures are cut from `evidence/` and a real `ps` row.

| # | Case | Expect |
| :---: | :--- | :--- |
| 1 | LLM runner `-c 8192 -np 1`, props `total_slots 1`, frozen 1 | pass |
| 2 | Same runner at `-c 32768 -np 4`, frozen 1 | fail, naming 4 and 1 |
| 3 | Only the `nomic-bert` runner (`-np 1`) | `NoRunner`, **not** a pass: the silent-pass case |
| 4 | Two LLM runners under the same server | `AmbiguousRunner` |
| 5 | Matching runner under a **foreign** ppid | `NoRunner` (`review.md` S4) |
| 6 | `-np` missing; `-np x`; `-np 1 --parallel 1` | `Unparseable` |
| 7 | `--mmproj <same blob>` present | exactly one match |
| 8 | argv `-np 1`, props `total_slots 4` | fail: the runner overrode its args (S2) |
| 9 | Blob ≠ pinned digest | fail: silent model swap (S7) |
| 10 | Version ≠ pinned | fail (S3) |
| 11 | `-c 8192 -np 1`, frozen `num_ctx` 4096 | fail: the `-c` check is real |
| 12 | `envelope_line` | stable key order, every field present |

## 5. The Ollama version and model identity join the envelope (`review.md` S3, S7)

- **Pin 0.33.2,** compared through `/api/version`, never `ollama --version`, which can print the
  client's version.
- **Pin the LLM weights digest** `sha256-7a3a8d55…`, so an `ollama pull` on the tag cannot swap the
  model silently.
- **The pin must be holdable.** The 0.32.13 → 0.33.2 drift was an **unattended auto-update**
  (`auto_update_enabled = 1`; "performing update at startup", 2026-09-01). **Decided 2026-10-04:
  (i), disable auto-update in Ollama.app.** The rejected alternative was (ii), running `ollama serve`
  under a LaunchAgent. The app stays, so the run rule *no use of the Ollama app during a run*
  carries the S5 risk.
- **The ADR records a restore artifact:** the v0.33.2 macOS download URL and its sha256. No
  0.33.2 bundle is cached locally today.
- **The ADR names the launch method,** because the app's server runs `OLLAMA_CONTEXT_LENGTH:262144`
  and the detached one runs 0. The detector is immune (it sends `num_ctx`), but the record should
  not be ambiguous.

## 6. Changes under A

Values come from `impact.md` §1. Wording comes from `review.md` B1.

| Where | Change |
| :--- | :--- |
| `Makefile:22-26` | The envelope block: `OLLAMA_NUM_PARALLEL := 1`, plus `OLLAMA_VERSION` and `LLM_BLOB`. The comment is corrected: the export pins the **gateway** via `make dev`, not Ollama |
| `Makefile:41` | spike echo 4 → 1 |
| `Makefile:48-67` | `env-check` → §4. The `pgrep` block is deleted |
| plist (outside the repo) | **A2:** `launchctl unsetenv OLLAMA_NUM_PARALLEL`, unload, delete |
| `gateway/cmd/gateway/main.go:155-172` | fallback 4 → 1. The comments and startup log say F1 is resolved by ADR-003 and that the pool bounds waiting, not memory |
| `gateway/internal/admission/pool.go:1-2` | package comment: memory → queueing delay (a comment only) |
| `decisions.md` | ADR-003 entry and summary row. `:59` amended to point at ADR-003 (never deleted). `:73` F1 resolved |
| `interfaces.md:507` | frozen-value restatement → 1, citing ADR-003. No version bump |
| `CLAUDE.md:122-123`, `:147-149`, `:157-159` | "sized to the memory envelope", "frozen at 4 … aggregate at that pair" → ADR-003 wording |
| `README.md:31-32`, `:40-42` | same |
| `super-plan.md:40`, `:50`, `:113` | "μ_gen is frozen … ≈ 0.19 req/s" → a planning figure; the admission framing; item 1.1 reads argv + `/props` |
| `super-plan.md` item **8.2** | Done-condition gains: *"the admission-control chapter frames the pool as queueing and shedding at one slot, per ADR-003, and never as a memory bound"*. This gives the twice-deferred reframing an owner |
| `verify_admission.sh:15-17` | comment: the split under 1 permit |
| `experiments/README.md:5` | the detector added to the `scripts/` row |

**Left alone, deliberately:**
- `pool_test.go:21` (mechanism test; tests are immutable).
- `rag/server.py:50` (`max_workers=4`, a coincidence).
- k6 VU counts.
- `Final_Proposal.md`: gitignored submitted prose. The ADR lists its affected lines.

**The queue default moves 8 → 2** under the unchanged `2 × permits` rule (`review.md` S6). At one
slot this choice sets the S2 shed rate. As a queueing illustration, at ρ = 0.8 it sheds ≈ 17 %
against ≈ 3 % for q = 8. So the ADR makes **q a pre-registered parameter of item 7.5**, recorded per
run, and no shed rate is read at an unregistered default.

## 7. Failure modes — silent first

| # | Failure | Silent? | Guard |
| :---: | :--- | :---: | :--- |
| F-1 | The detector reads the embedding runner and passes for the wrong model | **yes** | blob + ppid match; test 3 |
| F-2 | No runner found, reported as OK | **yes** | `NoRunner` → FAIL; test 3 |
| F-3 | The runner overrides its argv (`n_parallel = auto`, `LLAMA_ARG_*`) | **yes** | argv vs `/props`; test 8 |
| F-4 | Another Ollama server has the same blob loaded | **yes** | URL from `rag.config`, ppid = listener PID; test 5 |
| F-5 | `ollama pull` swaps the weights under the same tag | **yes** | digest pin; test 9 |
| F-6 | Ollama auto-updates | **yes** | version pin via `/api/version`; test 10; auto-update off or the launch method changed (author) |
| F-7 | A gateway launched outside `make` gets the wrong permit count | **yes** | The fallback becomes 1. **Residual** for P1: the manifest asserts the gateway's logged `permits` = the `ENVELOPE` `np` |
| F-8 | A mid-run reload, e.g. a chat in the Ollama app | **yes** | The `ENVELOPE` line enables a run-end check (experiment phase); run rule: no app use |
| F-9 | `ps` truncates argv | yes without `ww` | `-axww`; `Unparseable` |
| F-10 | The warm-up loads under different options than the service | yes | options from `rag.config`; U4 |

## 8. Unknowns — still to verify

| # | Unknown | Resolved how |
| :---: | :--- | :--- |
| U4 | ~~Does the warm-up load `-c 8192 -np 1`, with no reload on the first real generation?~~ | **Resolved 2026-10-04 (plan step 7):** runner pid 39617 was unchanged across a real `rag.generate` call. Earlier note: the warm-up loads `-c 8192 -np 1` (`evidence/ps-runners-2026-10-04.txt`). The no-reload half is **deferred to plan step 7**, because pressure reached 2 (urgent) with both models loaded, and step 7 needs a fresh load anyway |
| U9 | ~~Does the runner's `/props` exist on 0.33.2?~~ | **Resolved 2026-10-04:** yes. `total_slots: 1` at top level, per-slot `default_generation_settings.n_ctx: 8192`, and `model_path` naming the blob, which gives a third identity check. `build_info b1-d222767c7` (`evidence/runner-props-2026-10-04.json`). Tests 1 and 8 keep their `/props` half |
| U10 | ~~Does Ollama.app kill a LaunchAgent-run `ollama serve`?~~ | **Moot:** the author chose §5 (i) |
| U11 | ~~Does `/api/show` return the `FROM` blob path?~~ | **Resolved 2026-10-04:** `modelfile` carries `FROM …/sha256-7a3a8d55…` |
| U7 | `nomic-bert` runs one slot. Does that bound Tier-2 μ_hit? | **Out of scope**, recorded for Phase 7 |
| U8 | The Modelfile sets `temperature 1`, and `generate.py` does not override it | **Out of scope**, flagged for the author (judging, reproducibility) |
| N7 | At one permit the slot idles during the permit's gRPC and Redis work, so gateway-measured μ_gen ≤ Ollama's | Recorded for Phase 7: name which μ_gen is measured |
