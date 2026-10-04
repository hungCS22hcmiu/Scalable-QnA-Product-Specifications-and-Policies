# Plan — resolve-f1

The smallest change that satisfies `spec.md`, ordered so that each step can be verified on its own.
It follows `design.md` revision 2.

## 0. Before any edit

- [x] **Author decisions** (2026-10-04): **Option A**, **A2** (remove the launchd pin), and **(i)**
      (disable Ollama.app auto-update).
- [x] `/approve impact` · [x] `/approve experiment` · [x] `/approve implementation`.

## 1. Settle the live unknowns (U4, U9, U11), exploratory

Yellow pressure is allowed (author's rule, 2026-10-03). Check `kern.memorystatus_vm_pressure_level`
first anyway, because this loads ~2.1 GB.

- [x] Load the LLM with a no-prompt `/api/generate` carrying `num_ctx: 8192`. Record:
  - the runner's `ps` row;
  - `GET 127.0.0.1:<port>/props`: are `total_slots` and per-slot `n_ctx` present, and at which
    paths? (U9)
  - `/api/show`'s `FROM` (U11).
- [x] Run one `rag ask`. **Done when** the runner PID and argv are unchanged, i.e. no reload (U4).
      **Deferred to step 7** (pressure reached 2 with both models loaded).
- [x] Write the answers into `design.md` §8. **If `/props` is absent**, apply the documented
      fallback (the version pin licenses argv) and drop tests 8 and 1's props half. Record that
      before writing code.

## 2. Tests first — `experiments/tests/test_env_check.py`

- [x] Write cases 1–12 of `design.md` §4, with fixtures cut from `evidence/` and step 1's real
      `ps` and `/props` output (blob hashes kept, home directory redacted).
- [x] **Done when** `pytest experiments/tests/test_env_check.py` fails only because `env_check`
      does not exist yet.

## 3. The detector — `experiments/scripts/env_check.py`

- [x] Pure functions per `design.md` §4's contracts. `main` is the only place with I/O: `urllib`,
      `subprocess` for `ps` / `lsof`, and the lazy `rag.config` import. **Stdlib only, no
      `psutil`.**
- [x] **Done when** the step-2 suite passes, `make lint` is clean, and `make test` is green.

## 4. Wire it into the Makefile

- [x] Envelope block at `Makefile:22-26`: `OLLAMA_NUM_PARALLEL := 1`, `OLLAMA_VERSION := 0.33.2`,
      `LLM_BLOB := sha256-7a3a8d55…`. Correct the comment: the export pins the **gateway**.
- [x] `env-check` calls the script with those three values. The `pgrep` block (`:57-66`) is
      deleted. There is no launchd comparison (A2).
- [x] Spike echo (`:41`) 4 → 1.
- [x] **Done when** `make -n env-check` shows the script invocation with the three values.

## 5. Gateway wording and default

- [x] `main.go:165`: fallback 4 → 1. `:155-164` and `:170-172`: F1 resolved by ADR-003; the pool
      bounds waiting, not memory.
- [x] `admission/pool.go:1-2`: package comment, memory → queueing delay.
- [x] **Done when** `make verify`'s Go targets pass. `pool_test.go` is untouched.

## 6. The machine (outside the repo; each action confirmed with the author when it is taken)

- [x] Plist (A2): `launchctl unsetenv OLLAMA_NUM_PARALLEL`, unload, delete
      `~/Library/LaunchAgents/com.thesis.ollama-env.plist`.
- [x] Version pin (i): the author turns off auto-update in Ollama.app's settings. Verify
      `auto_update_enabled = 0` in the app DB.
- [x] The restore artifact: `Ollama-darwin.zip` v0.33.2, sha256 `2e35765d…1fa6` (GitHub-published
      digest), recorded in ADR-003.
- [x] **Restart Ollama — the old server is gone.** pid 19379 has been running since 2026-09-06 under the old environment,
      logging to a deleted session's `/private/tmp`. Start it through Ollama.app, which logs to
      `~/.ollama/logs/server.log`, a stable path.

## 7. Live acceptance (spec 1, 2, 6)

- [x] `make env-check` → **OK**, printing the `ENVELOPE` line (spec 6).
- [x] With `--frozen-np 4` → **FAIL**, naming 4 and 1 (spec 1).
- [x] With Ollama stopped → **FAIL**, "unreachable" (spec 2).
- [x] Paste all three outputs into this file under *Verification*.

## 8. ADR-003 and the documents

- [x] `decisions.md`:
  - ADR-003, per `design.md` §2–§6: decision; S2 restated; the four §H meanings; μ_gen's evidence
    and planning-figure status; version and digest pins with the restore artifact and the launch
    method; the queue default and q pre-registered for 7.5; the run rule (no app use during a
    run); the deviation from `super-plan.md:113`; the `Final_Proposal.md` lines affected;
    **Invalidates**.
  - Summary row. `:59` amended, not deleted. `:73` F1 resolved.
- [x] `interfaces.md:507` · `CLAUDE.md:122-123, 147-149, 157-159` · `README.md:31-32, 40-42` ·
      `super-plan.md:40, 50, 113`, 8.2's done-condition, and standing constraint 1 at `:86-87` ·
      `verify_admission.sh:15-17` · `experiments/README.md:5`.
- [x] **Done when** (spec 5) a `grep` over the tracked tree for `OLLAMA_NUM_PARALLEL *= *4`,
      `frozen at 4`, `four-slot`, `4-way` and `memory envelope` in admission context finds only
      history, `pool_test.go`, and the ADR's own text.

## 9. Close

- [x] `/verify` → `/ai-review` → `/done`. `/done` asks whether scope L was honest.

## Verification

### Step 1 — 2026-10-04, exploratory (pressure 1 before the load, **2 with both models loaded**, 1 after unloading)

- The warm-up (`/api/generate` with no prompt and `num_ctx 8192`) → `done_reason: load`. The runner
  argv is `-c 8192 -np 1`, with ppid 19379 = the `:11434` listener.
- `/props` → `total_slots 1`, `default_generation_settings.n_ctx 8192`, `model_path` = the pinned
  blob. `/api/show` → `FROM …sha256-7a3a8d55…`. `/api/version` → `0.33.2`.
- Both models were unloaded straight afterwards with `keep_alive: 0`. **U4's no-reload half is
  deferred to step 7.**
- Evidence: `evidence/ps-runners-2026-10-04.txt`, `evidence/runner-props-2026-10-04.json`.

### Steps 2–5, 8 — 2026-10-04

- `pytest experiments/tests/test_env_check.py`: **34 passed**. The whole experiments suite: 84
  passed.
- `make lint`: clean. The deliberate catch-all in `main` carries `# noqa: BLE001`, following
  `load_burst.py:115`.
- `make -n env-check` → `python3 experiments/scripts/env_check.py --frozen-np 1 --ollama-version
  0.33.2 --llm-blob sha256-7a3a8d55…`.
- `make verify`: **exit 0**.
- Spec 5 grep: the remaining hits are history or ADR text only. Three further memory-governor claims
  found by a wider sweep were corrected too: `README.md:100`, `httpapi/handler.go:63` (a comment)
  and `interfaces.md:157` (prose rationale, no wire change).

### Step 6–7 — 2026-10-04

- **Auto-update is off.** The author toggled it in Ollama.app, and the app DB reads
  `auto_update_enabled = 0`.
- **The old detached server (pid 19379) is gone.** Opening the app at 15:22 failed to bind
  `:11434`, because the old server held it, and quitting the app at 15:29 stopped both. That app
  start still logged `OLLAMA_NUM_PARALLEL:4`, because the launchd plist was not yet removed.
- **Spec 2:** `make env-check` with no Ollama running →
  `FAIL — envelope not verifiable: EnvelopeError: ollama unreachable at http://localhost:11434:
  … Connection refused`, make exit 2.
- **A2 done.** `launchctl unsetenv OLLAMA_NUM_PARALLEL` (before: `4`; after: unset), then the plist was
  unloaded and moved to `evidence/com.thesis.ollama-env.plist.removed-2026-10-04`. A first
  relaunch with `open -a` from this session still logged `NUM_PARALLEL:4`, because `open` passes
  the caller's environment and this session had inherited 4 from launchd before the removal. The
  author then quit and relaunched the app from Spotlight: server pid **39478**, 15:37:52,
  **`OLLAMA_NUM_PARALLEL:1`** (Ollama's default; nothing requests a value any more).
- **Spec 6:** `make env-check` → **OK** (exit 0):
  `ENVELOPE server_pid=39478 runner_pid=39617 version=0.33.2 np=1 ctx=8192 total_slots=1
  n_ctx_slot=8192 blob=sha256-7a3a8d55382135a773916fd7c35044b2a2a3a7b8dee788095d70f122e6d8f520`.
- **Spec 1:** the same live runner checked with `--frozen-np 4` → `FAIL — runner launched with -np 1
  ≠ frozen slot count 4`, exit 1.
- **U4, resolved:** one real generation through `rag.generate` (`think: false`, `num_ctx 8192`)
  → `'ready'` in 0.6 s, with runner pid **39617 before and after: no reload**.
- **Pressure** (exploratory, not citable): 1 before, **2 with both models loaded**, and still 2
  right after unloading. Both models were unloaded (`/api/ps` → `[]`).

### `/verify` — 2026-10-04

`make verify` exited **0**.

| Target | Result |
| :--- | :--- |
| Go format (`gofmt -l gateway/`) | **PASS** |
| Go vet | **PASS** |
| Go build | **PASS** |
| Go test | **PASS**: admission, cache, coalesce, ragclient, reuse, telemetry. No test files in `cmd/gateway`, `catalog`, `deps`, `embed`, `httpapi` (item 1.2), `ragpb` |
| Python lint (`ruff check rag experiments`) | **PASS** |
| Python tests: `rag/` | **PASS**, 10 / 10 |
| Python tests: `experiments/tests` | **PASS**, 84 / 84 (34 new in `test_env_check.py`) |
| Proto drift | **NOT RUN.** Both stub directories are gitignored, so `git diff` cannot see drift. No `.proto` was touched |

No target was skipped for missing tooling. The skill's "this week's worklog" instruction is stale
(weeks were retired on 2026-09-21) and was not acted on.

## Outcome — closed 2026-10-04

**Shipped.**

- **Code:**
  - `experiments/scripts/env_check.py` and 44 offline tests.
  - The `Makefile` envelope block (`OLLAMA_NUM_PARALLEL := 1`, `OLLAMA_VERSION`, `LLM_BLOB`) and
    the rewritten `env-check`, with the `pgrep` block that made `measure` unpassable removed.
  - The gateway grants 1 permit (queue default 2) and logs a WARNING when its permits differ from
    the frozen slot count.
  - Comments in `pool.go`, `handler.go`, and `pool_test.go` (comment only, author-approved).
- **Docs:**
  - **ADR-003**, plus the amended envelope and F1 rows in `decisions.md`.
  - `interfaces.md` prose at `:157` and `:507`.
  - `CLAUDE.md`, `README.md`.
  - `super-plan.md`: the spine, standing constraint 1, item 1.1, and item 8.2's done-condition.
  - `experiments/README.md`, `verify_admission.sh`.
  - Three UI texts.
- **Machine:**
  - Ollama.app auto-update off (`auto_update_enabled = 0`).
  - The launchd pin removed, with a copy kept in `evidence/`.
  - Ollama restarted through the app, now requesting Ollama's default.

**Phase exit.** The clause *"`make env-check` fails when the effective Ollama slot count differs
from the frozen value"* is **met**, run literally: `make env-check OLLAMA_NUM_PARALLEL=4` → `FAIL —
runner launched with -np 1 ≠ frozen slot count 4`, exit 2, and `make env-check` → OK plus the
`ENVELOPE` line. **Phase 1 stays open**, because 5 of 6 clauses are unmet: no `httpapi` tests, no
`texts` in `server.py`/`ragclient`, 8 gateway files still carry the retired branch, no
`raw/answers`, and no footprint measurement or ADR-001.

**Scope was honest: L.** The change moved a frozen value and a measured path, and edited
`interfaces.md` prose. The opus design review earned its place: it blocked on B1, and S1–S7 changed
the detector (`/props`, the ppid match, version and digest pins) and the ADR's wording on μ_gen
before any code existed.

**Frozen value / contract.**
- The frozen slot count moved 4 → 1, recorded in ADR-003, which names what it invalidates.
- `approvals.md` names the same: no `run_id`; μ_gen relabelled as a planning figure; the spike
  grid's `NUM_PARALLEL` axis void.
- `interfaces.md` was **not** version-bumped. Its own rule (`:497`) bumps only for a change to "a
  wire shape, the chunk-ID format, or the Redis schema", and none changed (confirmed by
  `contract-reviewer`).

**Deferred, deliberately.**
- The run-end `ENVELOPE` re-check, and the manifest assertion permits == `np` → **P1**.
- Pre-registering q → **item 7.5**.
- The `Final_Proposal.md` prose lines listed in ADR-003 → the write-up (**8.2**).
- **For the advisor:** withdraw the promised `OLLAMA_NUM_PARALLEL` sweep (§6.2), which cannot run
  on this model and stack.

**Follow-ups worth a task.**
1. **`/bugfix rag-server-reuseport`**, carried over from `pqa-category-choice`, still open.
   Phase 1 (instrument integrity).
2. **`/investigate generation-determinism`** (U8). The Modelfile sets `temperature 1` and
   `generate.py` does not override it, so the same miss can produce different answers. This bears
   on judging (Phase 5) and on reproducibility.
3. **Phase 7 notes:** `nomic-bert` also serves one slot, which may bound Tier-2 μ_hit (U7), and a
   gateway-measured μ_gen ≤ Ollama's (N7).
4. Doc drift: `architecture.md` §4's command list does not name `env-check`.
5. **Housekeeping:** shells opened before 2026-10-04 15:34 still carry `OLLAMA_NUM_PARALLEL=4`.
   The gateway now warns, and new shells are clean.
