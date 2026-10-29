# Ollama's runner keeps every prompt in RAM

Status: opened 2026-10-29 · spec approved 2026-10-29 · design approved 2026-10-29 · plan approved 2026-10-29
§3 changed §1: (a)–(d) decided; DC 6 names the probe scripts, gains four guards, allows yellow.
Plan writing changed §3 and DC 5 (`ollama-env` relaunches clean, §4 F1–F2); review changed DC 4 (F4).
Super-plan item: none — blocks 7.1 and every citable run that loads the LLM

## 1. Spec

**Root cause** (`rca-analyst`, 2026-10-29; raw files in `evidence/rca/`, cited below as `E/`).
Ollama 0.33.2 starts the bundled `llama-server` with no `--cache-ram`, so llama-server's prompt cache
is on at its default limit of 8192 MiB. After each request the slot's state is saved to host RAM as a
new entry: the KV for its tokens (12 KiB per token), one recurrent state (19.27 MiB) and its context
checkpoints (2 × 19.27 MiB). A 684-token prompt makes a 65.8 MiB entry. Distinct RAG prompts share
almost no start (all 47 restores reused `n_past = 1`), so the entries are never useful and pile up
toward 8 GiB.

- **Measured:** 50 distinct v1 RAG prompts grew the runner's `footprint` from 3,066 to 7,088 MB,
  about 82 MB per prompt, and pressure was 2 (`E/on-samples.jsonl`). The log's "49 prompts,
  4044.763 MiB" matches the growth in MALLOC_LARGE (+4,024 MB).
- **Why RSS hid it:** macOS compresses these pages, so RSS stayed near 2.3 GB. Only `footprint`
  shows the growth.
- **A second, smaller reuse, same root:** with the cache off, the slot still keeps context
  checkpoints of its own last prompt. A repeat of the same prompt then takes 0.05 s of prefill
  instead of 1.29 s (`E/off-repeat.txt`), while Ollama still reports `prompt_eval_count = 658`.
  `LLAMA_ARG_CTX_CHECKPOINTS=0` stops it (`E/nockpt-repeat.txt`).
- **The fix works:** with `LLAMA_ARG_CACHE_RAM=0` and `LLAMA_ARG_CTX_CHECKPOINTS=0` in Ollama.app's
  launchd environment, both reach the runner (`E/off2-env.txt`), the log says "prompt cache is
  disabled" and "context checkpoints disabled", and over the same 50 prompts the footprint went
  3,071 → 2,685 MB at pressure 1 (`E/off2-samples.jsonl`). Median prefill and decode speed did not
  drop: 479 → 508 tok/s and 35.5 → 36.9 tok/s (`E/compare-on-off2.txt`; the cache-on arm ran in
  yellow).
- **Why `make env-check` missed it:** it checks only the values the Makefile freezes, never the
  runner's own defaults. It passes this runner today (`E/env-check-cache-on.txt`).

**The change.** Turn off llama-server's prompt cache and context checkpoints for Ollama's runners
through Ollama.app's launchd environment, make `make env-check` fail when the live runner has either
one on, and record it as ADR-017, which amends ADR-003's envelope.

**Decided by the author at `/approve`, 2026-10-29**, each as the RCA recommended:
- **(a)** Context checkpoints are off too (`LLAMA_ARG_CTX_CHECKPOINTS=0`). Each request is
  independent, and left on they give the `no-cache` configuration free prefill on back-to-back
  duplicates under Zipf.
- **(b)** The vision encoder stays. Ollama 0.33.2 passes `--mmproj` on argv, which beats
  `LLAMA_ARG_MMPROJ_AUTO=0` (`E/nomm-*`). It costs 855 MB, fixed at load
  (`E/manual-mmproj-{yes,no}-footprint.txt`), and ADR-017 records it.
- **(c)** `launchctl setenv` is lost on reboot. `make ollama-env` sets both variables and restarts
  Ollama.app, and `env-check` fails until it is run. No LaunchAgent. While the variables are set,
  other projects' Ollama models also run without the prompt cache.
- **(d)** "1.7 GB resident" is Ollama's own estimate (`/api/ps`: 1.588 GiB), not a measurement. The
  measured footprint at load is 3.03–3.07 GB (`E/api-ps.txt`). It is corrected in `README.md` and
  `decisions.md`; `CLAUDE.md` stays the author's.

**Done conditions.** Live steps load the LLM and are `citable: no` (the author's decision).

1. **The failing test first.** A new file, `experiments/tests/test_env_check_runner_cache.py`, runs
   `env_check.main()` with the exact argv that `make -n env-check` prints, against the captured
   cache-on runner (`E/on-argv.txt`, `E/on-env.txt`). It expects exit 1 and a message naming the
   prompt cache. Before the fix it fails because env-check exits 0 on that runner. After the fix it
   passes.
2. **Unit cases** in the same file, all passing:
   - the captured fixed runner (`E/off2-argv.txt`, `E/off2-env.txt`) exits 0;
   - `--cache-ram` or `--ctx-checkpoints` on argv with a value other than 0 fails, even when the
     environment says 0 (argv wins);
   - a missing or different `LLAMA_ARG_CACHE_RAM` / `LLAMA_ARG_CTX_CHECKPOINTS` token fails;
   - an environment that cannot be read, or cannot be told apart from the argv, fails.
3. **Old tests untouched.** `pytest experiments/tests -q` passes, and
   `git diff --quiet experiments/tests/test_env_check.py` exits 0.
4. **Live, variables unset:** `make env-check` fails (make 2, the script 1), naming the prompt cache.
5. **Live, variables set** by `make ollama-env`: `make env-check` exits 0, prints `RUNNER_CACHE
   cache_ram=0 ctx_checkpoints=0`, and keeps `ENVELOPE` last. `ollama serve`'s environment has no
   `_=` variable, so no shell's environment reached it.
6. **Memory stays flat over 300 requests** (the author, 2026-10-29). `evidence/probe/build_prompts.py`
   builds 300 distinct questions from `data/workload-v1-validation.json` as `rag.server` would, and
   `evidence/probe/run_arm.py` loads the LLM fresh and sends them one at a time.
   `evidence/probe/verdict.py` passes only if:
   - the mean footprint of samples 251–300 is at most the mean of samples 1–50 plus 100 MB, so a
     leak of 0.4 MB per request or more fails (before the fix: +4,022 MB after 50);
   - one runner pid serves all 300, the 300 prompts are distinct, and every sample has a footprint
     and a pressure reading (yellow and swap are allowed: the author, 2026-10-29);
   - the server log for that load says "prompt cache is disabled" and "context checkpoints
     disabled", and has no "cache state:" line.
7. **No hidden reuse.** The same prompt sent three times in a row (`evidence/probe/repeat.py`): each
   repeat's prefill time is at least 0.8 × the first one's (before, with checkpoints on: 0.05 s
   against 1.29 s).
8. **Speed**, computed by `verdict.py`. On the same 300 prompts, median prefill ≥ 431 tok/s and median decode ≥ 32.0 tok/s, which
   is 0.9 × the RCA's cache-on medians (479 and 35.5). Fixed now, before the run.
9. **Records.** ADR-017 is in `docs/decisions.md` with an `Invalidates:` line. The Makefile's
   envelope block holds both values. `interfaces.md` Versioning lists them. Every "1.7 GB resident"
   in `README.md` and `decisions.md` names the measured footprint and the tool that measured it.
10. `make verify`: no FAIL; any SKIPPED target listed by name.

**Out of scope.**
- Turning the vision encoder off. It needs a serving-stack change (a newer Ollama, or llama-server
  run directly), which ADR-003 ruled out mid-study.
- Upgrading Ollama, or changing the model, the weights, `num_ctx` or the slot count.
- Re-measuring μ_gen. That is Phase 7 (items 7.2, 7.5).
- A 398 MB footprint drop at request 25 of the fixed arm. The cache was off, so it is not this bug.
- Editing `CLAUDE.md` (the author's file) or `Final_Proposal.md` (gitignored prose). The stale lines
  are listed in ADR-017, not edited.
- Issue 2 in `docs/Issue_phase4.md` (tools still tied to `dev-v0`).

## 2. Impact

**Files.** All inside `docs/architecture.md`'s boundaries. No gateway or RAG service code changes.
- `experiments/scripts/env_check.py`: a new pure check over the runner's argv and environment, and a
  helper that reads the environment with `ps eww -o command= -p <runner_pid>`. The docstring's claim
  that the runner's `LLAMA_ARG_*` environment "nobody can read back" is false, and gets corrected.
- `experiments/tests/test_env_check_runner_cache.py`: new.
- `Makefile`: the envelope block gains the two values, `env-check` passes them, and `ollama-env`
  is added (c).
- `evidence/probe/`: the task's own probe scripts, copied from the RCA's. Not tooling.
- `docs/decisions.md` (ADR-017, plus "amended by ADR-017" notes as ADR-003 left them),
  `docs/contracts/interfaces.md` (Versioning), `README.md` (`:42`, `:123`, `:184–186`).
- **A constraint from the immutable tests.** `test_env_check.py` pins the exact `ENVELOPE` line and
  the fields of `Props` and `RunnerArgs`. It also runs `main()` with only `observe` faked, and
  expects exit 0 with `ENVELOPE` as the last line. So the new check must leave `observe()`, `check()`,
  those dataclasses and `envelope_line()` as they are, and must not run for today's argv.

**Frozen values touched.**
- **Added to the ADR-003 envelope:** `LLAMA_ARG_CACHE_RAM=0` and `LLAMA_ARG_CTX_CHECKPOINTS=0`
  (a). Both are read from the live runner by `make env-check`.
- **Corrected, not changed:** "1.7 GB resident" becomes the measured footprint, 3.03–3.07 GB at load,
  855 MB of which is the vision encoder (d).
- **Restated:** ADR-003's "memory is fixed when Ollama loads the runner, and admitting requests adds
  none" was false on the live stack. With the fix it holds, and done condition 6 measures it.
- **Unchanged:** the models, the weights blob, Ollama 0.33.2, `num_ctx = 8192`, one slot.
- **Invalidates:** no `run_id` (`experiments/results/` is empty). Item 4.4's live runs
  (`docs/work/2026-10-29-update-set/evidence/live1`–`live3`) ran with the cache on. Their
  completeness (1) and precision (0.695) count purged entries, which prompt reuse cannot change, so
  they stand. Any latency or memory reading in their evidence is void.

**Contract change.** `interfaces.md` Versioning (the "frozen study-wide" list at `:805`) gains the
two runner settings, v0.21 → v0.22. Nothing at the Go↔Python seam changes, and `source_chunk_ids`,
`t1_key` and `dataset_epoch` are untouched.

**Measurement change: yes. Flagged: this is a measured path** (generation latency and the memory
envelope), though not `reuse/` and not the seam.
- In the `no-cache` configuration, a back-to-back duplicate question used to get its prefill almost
  free (0.05 s against 1.29 s). That was invisible in `prompt_eval_count`. After the fix every
  generation pays full prefill. The baseline becomes honest, and the measured gain of the gateway's
  cache can only be read against it from now on.
- Memory figures are read with `footprint`, never RSS or `/api/ps`. RSS stayed near 2.3 GB while the
  footprint reached 7 GB. ADR-017 records this as method.

**New dependency.** None. `footprint` and `ps` are part of macOS. The fix removes up to 8 GiB of
growth; the vision encoder's 855 MB stays, fixed at load.

**Cut scope reinstated.** No.

## 3. Design

**Approach.** Three parts.
1. **The fix is configuration, not code.** `make ollama-env` puts the two variables in the launchd
   environment that Ollama.app starts from. Ollama passes that environment to every runner, and
   llama-server reads a variable when argv does not set the flag (RCA unknown 1).
2. **`env-check` gains a second check**, on the runner's cache settings, read from the live
   runner's argv and environment.
3. **ADR-017 and the doc corrections.** They cite the RCA's measurements and name
   `evidence/probe/verdict.txt` as the 300-request check, so they are written before the final
   phase, and `deliverables.md` carries that run's numbers. This way the 15-minute run happens once
   in the plan, not twice.

Alternatives it beat:
- Reading the server log for "prompt cache is disabled" in `env-check`: where the log is depends
  on how Ollama was launched, which is why ADR-003 did not use the log either.
- Keeping the cache with a small limit (`LLAMA_ARG_CACHE_RAM=512`): memory is bounded, but it is
  still a hidden second cache under the `no-cache` configuration.

**How `env-check` reads a setting.** llama-server takes each setting from argv first, then from its
`LLAMA_ARG_*` variable, then from its default (8192 MiB; 32 checkpoints). `env-check` works out that
effective value from two `ps` calls on the runner pid that `observe()` already matched:
- `ps -ww -o command= -p <pid>` gives the argv;
- `ps eww -o command= -p <pid>` gives the argv followed by the environment. The environment is
  whatever follows the argv prefix.

"Unset" fails: the default keeps state, and a new build can change it.

**Why the check is switched on by arguments.** The immutable `test_env_check.py` runs `main()` with
today's argv and only `observe` faked, and expects exit 0 with `ENVELOPE` as the last line. So
`main()` runs the cache check only when it gets `--cache-ram` and `--ctx-checkpoints`, and the
Makefile always passes them. This opens one risk: the Makefile could stop passing them, and
`env-check` would print OK without checking. Done condition 1 closes it, because it takes its argv
from `make -n env-check`.

### Files

**`experiments/scripts/env_check.py`**
- `_CACHE_FLAGS: dict[str, tuple[tuple[str, ...], str]]` maps each setting to its argv spellings and
  its variable. The spellings come from the bundled `llama-server --help`:
  - `cache_ram`: `--cache-ram` or `-cram`, read from `LLAMA_ARG_CACHE_RAM`;
  - `ctx_checkpoints`: `--ctx-checkpoints`, `-ctxcp` or `--swa-checkpoints`, read from
    `LLAMA_ARG_CTX_CHECKPOINTS`.
- `@dataclass(frozen=True) class CacheSetting: value: str | None; source: str`. The source is
  `"argv"`, `"env"` or `"unset"`.
- `runner_env(argv_line: str, eww_line: str) -> list[str]` returns the tokens after the argv prefix.
  It raises `Unparseable` when `eww_line` does not start with `argv_line`, or when nothing follows
  it (the environment was not shown).
- `runner_cache(argv_line: str, env: list[str]) -> dict[str, CacheSetting]` returns each setting's
  effective value. It reads flags from the argv only and variables from the environment only.
  `--cache-ram=N` counts as the flag. It raises `Unparseable` on a flag given twice, a flag with no
  value, or a variable given twice.
- `check_runner_cache(frozen: dict[str, int], seen: dict[str, CacheSetting]) -> list[str]` returns
  one message for each setting whose value is not exactly `str(frozen[name])`, and "unset" fails.
  - Each message starts with "runner prompt cache" or "runner context checkpoints", and says the
    value and where it came from.
  - When the source is `env` or `unset`, the message ends with "run `make ollama-env`".
- `runner_cache_line(runner_pid: int, seen) -> str` returns
  `RUNNER_CACHE cache_ram=0 ctx_checkpoints=0 runner_pid=<pid>`.
- `_read_runner_env(runner_pid: int) -> tuple[str, list[str]]` makes the two `ps` calls through
  `_run`. If the runner has exited, the `CalledProcessError` becomes an `EnvelopeError`.
- `main()` gains two optional arguments, `--cache-ram N` and `--ctx-checkpoints N`:
  - one without the other prints FAIL and exits 1;
  - with both, the runner's settings are read and checked after the existing checks, and their
    failures join the same list;
  - an `EnvelopeError` from that read prints "FAIL — runner cache not verifiable: …" and exits 1;
  - one more `observed` line gives each setting and its source;
  - on success, the `RUNNER_CACHE` line comes before the `ENVELOPE` line, which stays last.
- The docstring gains two rows in its table, and the claim that the runner's environment
  "nobody can read back" is corrected.
- **Unchanged:** `observe`, `check`, `Frozen`, `RunnerArgs`, `Props`, `Observed`, `envelope_line`.

**`experiments/tests/test_env_check_runner_cache.py`** (new)
- **Fixtures** are cut from `E/on-argv.txt` and `E/on-env.txt`, with the home directory replaced,
  as `test_env_check.py` did. The fixed runner's environment is `on-env.txt` plus the two
  variables (§4 F1).
- **`_make_argv() -> list[str]`** runs `make -n --no-print-directory env-check` at the repo root,
  with `MAKEFLAGS` and `MAKELEVEL` removed from its environment, so that it prints the same thing
  inside `make test`. It joins the continued lines, applies `shlex.split`, and keeps the tokens after
  `env_check.py`.
- **Fakes:** a `rag.config` stand-in, `observe` returning the captured runner, and `_run` answering
  only the two `ps` calls (anything else raises `AssertionError`).
- **Tests:**
  - DC 1, the witness: the `make -n` argv on the cache-on runner exits 1 and names "prompt cache".
  - DC 2:
    - the fixed runner exits 0, prints `RUNNER_CACHE cache_ram=0 …`, and keeps `ENVELOPE` last;
    - `--cache-ram 8192`, `--cache-ram=8192` or `--ctx-checkpoints 32` on argv fails while the
      environment says 0;
    - argv `--cache-ram 0` with no variable passes, because argv wins;
    - a missing, different (`=8192`) or doubled variable fails;
    - `ps` raising, `ps eww` showing no environment, or `ps eww` not starting with the argv fails,
      as "not verifiable";
    - one cache argument without the other fails.
  - The new functions are reached as `env_check.<name>` at call time. The file then imports cleanly
    before the fix, so the witness fails on its assertion and not on an `ImportError`.

**`Makefile`**
- **Envelope block:** `RUNNER_CACHE_RAM := 0` and `RUNNER_CTX_CHECKPOINTS := 0`, with a comment
  citing ADR-017. They are not exported and not named `LLAMA_ARG_*`, so no recipe hands them to a
  process by accident.
- **`env-check`** passes `--cache-ram $(RUNNER_CACHE_RAM) --ctx-checkpoints $(RUNNER_CTX_CHECKPOINTS)`.
- **`ollama-env`** is new, with a `.PHONY` entry and the help text "after every reboot; never during
  a run". It:
  1. runs `launchctl setenv` for both variables;
  2. stops the app with `pkill -TERM -x Ollama`, and its `ollama serve` stops with it (in the RCA,
     an AppleScript `quit` was refused);
  3. waits up to 30 s until no `ollama serve` is left;
  4. runs `env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin open -g -a Ollama`
     and waits up to 60 s for `/api/version`. A plain `open` hands the caller's whole environment
     to the app (§4 F1). With `env -i`, only launchd's environment arrives, and the two variables
     come with it (§4 F2);
  5. prints the `LLAMA_ARG_*` variables of the new `ollama serve`, then "now run make env-check".

**`evidence/probe/`** (new; this task's scripts, not tooling)
- `build_prompts.py <workload> <out> <n>` takes one question per `cluster_id` in file order (270),
  then unseen `qa_id`s in file order until `n`. It builds each prompt with
  `rag.retrieve.retrieve` and `rag.generate._build_prompt`, as the RCA's builder did. The request
  body matches `rag.generate.generate`: `stream: false`, `think`, `num_ctx`.
- `run_arm.py <label> <prompts> <outdir>` is the RCA's script with one change: it first unloads the
  LLM (`keep_alive: 0`) and waits until no LLM runner is left, so the captured log holds this load.
- `repeat.py <prompts> <outdir>` sends prompt 1 three times in a row and records each
  `prompt_eval_duration`.
- `verdict.py <outdir>` prints every check of DC 6–8 with its numbers, and exits 0 only if all pass.
  Tok/s is computed as in the RCA's `compare.py`: the median of each request's `tokens / seconds`.

**Docs**, written before the final phase:
- `docs/decisions.md`: ADR-017 after ADR-016, its Summary row, and "amended by ADR-017" notes at
  `:73` and `:415`.
- `docs/contracts/interfaces.md`: `:805` lists the two settings, plus a v0.22 Versioning row and the
  Status line.
- `README.md`: `:42` and `:123` give the footprint and the tool that measured it. `:184–186`, the
  open issue, becomes one line saying it is fixed.
- ADR-017 lists, but does not edit, `CLAUDE.md` (the hardware-envelope bullet and `:185–186`) and
  `Final_Proposal.md` (`:280`, `:333`, `:340`).

**ADR-017**, titled "The model runner keeps no prompt cache and no context checkpoints; envelope
memory is read with `footprint`", decided (frozen). Its consequences:
- S2's "memory is fixed when the runner loads" holds again, now as a measured footprint.
- The 855 MB vision encoder is accepted.
- `make ollama-env` must run after every reboot.
- While it is set, other projects' Ollama models also lose the prompt cache.
- Method: memory is read with `footprint`, never RSS or `/api/ps`.

Its `Invalidates:` line is §2's.

### Failure modes, silent ones first

1. **The Makefile stops passing the cache arguments.** `env-check` skips the check and prints OK.
   → DC 1 takes its argv from `make -n env-check`.
2. **The probe cannot see a leak.** Four ways:
   - the runner reloads mid-run and its footprint resets;
   - the prompts repeat, so even a live cache would not grow;
   - a footprint fails to parse and the sample reads as nothing;
   - the model was already loaded, so the log holds no load lines, and "no cache state: line"
     passes with nothing checked.

   → DC 6's guards: one runner pid, distinct prompts, a footprint in every sample, and both
   "disabled" lines required.
3. **An environment token read from argv, or a flag read from the environment.** A path in argv
   could contain `LLAMA_ARG_CACHE_RAM=0`. → The environment is only what follows the argv prefix.
   DC 2 includes "`ps eww` not starting with the argv fails".
4. **The variable reaches the runner, but a build ignores it.** `env-check` would pass while the
   cache is on. → The version pin: on 0.33.2 the RCA showed the variable works
   (`E/off-server-log.txt`), and any other version fails `env-check` first. This residual is
   recorded in ADR-017.
5. **`ps eww` shows no environment** (another user, or a macOS restriction). → `runner_env` raises,
   and DC 2's "not verifiable" cases cover it.
6. **A leak under 0.4 MB per request.** DC 6 cannot see it. → Unknown 1.
7. **`make ollama-env` hands its shell's environment to Ollama.** Then an `OLLAMA_*` variable in
   someone's shell profile, such as a KV cache type, would change the runner with no error. →
   `env -i`, and DC 5 checks that `ollama serve` has no `_=` variable. A shell sets `_` for each
   command it runs; launchd and `env -i` do not.

Two failures are loud, not silent. `make ollama-env` during a run kills it. An Ollama started from a
terminal does not get the launchd environment, so `env-check` fails.

### Edge cases

- After a reboot, Ollama.app may start at login before `make ollama-env` runs. `env-check` fails
  until it does, and `ollama-env` restarts the app.
- Every restart rotates Ollama's logs. The 4.4 run's log (`~/.ollama/logs/server-4.log`, 21 MB) is
  deleted at the second restart from now. The RCA's excerpt is the record
  (`E/live-4.4-server-log-excerpt.txt`), and the author chose not to copy the full log (2026-10-29).
- **Pressure does not gate this run** (the author, 2026-10-29: it produces no thesis number, and
  yellow and swap are fine). Every sample still records it.
  - The memory check holds in yellow, because `footprint` counts compressed and swapped pages. The
    RCA's cache-on arm ran in yellow and still showed the full growth, while RSS stayed flat.
  - Only red (4) stops the probe, as the RCA's script already does. Then close apps and re-run.
  - DC 8 can fail under swap with no code fault. The cache-on medians it compares against were
    themselves taken in yellow. If DC 8 fails while pressure was above 1, the executor reports it
    with the pressure, and the human decides whether to re-run. It does not count as the one quick
    fix.
- Argv sets 0 and the environment does not: pass, because argv wins. The environment sets 0 and
  argv sets 8192: fail.

### Unknowns

1. **A leak under 0.4 MB per request.** Settled by recording the runner's footprint during the
   Phase 7 sweeps. This is a follow-up for 7.1, named in `deliverables.md`.
2. **The embedding runner.** It gets the same environment, but its memory under load is not
   measured. Settled by the same Phase 7 sampling.
3. **Surviving a reboot** is reasoned, not tested. Settled at the first reboot: `env-check` exits 1,
   then 0 after `make ollama-env`.
4. **The 398 MB drop at request 25** in the RCA's fixed arm. Not this bug; the 300-request run shows
   whether it happens again.

### Verification

Order matters: DC 4 runs before `make ollama-env`. Every live step checks pressure first, and every
number is `citable: no`.

| DC | Shown by |
| :--- | :--- |
| 1, 2 | `pytest experiments/tests/test_env_check_runner_cache.py -q` |
| 3 | `pytest experiments/tests -q`, then `git diff --quiet experiments/tests/test_env_check.py` |
| 4 | `make env-check`, with the variables still unset as the RCA left them |
| 5 | `make ollama-env`, then `make env-check`, then `ps eww` of `ollama serve` |
| 6, 8 | `build_prompts.py` → `run_arm.py` → `verdict.py` |
| 7 | `repeat.py` → `verdict.py` |
| 9 | `grep` checks named in `plan.md` |
| 10 | `make verify` |

## 4. Findings

Found while writing the plan, 2026-10-29.

- **F1 — The RCA's relaunches leaked its shell environment.** `open` passes the caller's
  environment to the app it starts (`_=/usr/bin/open` in `E/off-env.txt`). So every runner after
  the RCA's first restart carried the RCA's shell: 75–77 variables, among them
  `CLAUDE_CODE_MESSAGING_TOKEN` and `GOTELEMETRY_GOPLS_CLIENT_TOKEN`.
  - Before any commit, `E/off-env.txt`, `E/nomm-env.txt` and `E/off2-env.txt` were cut to their
    `LLAMA_*`, `OLLAMA_*`, `DYLD_*`, `XPC_SERVICE_NAME` and `_` lines. A note at the top of each
    file says so.
  - `E/on-env.txt` is the login-started Ollama's environment, and it is clean.
  - The tests take the fixed runner's environment as `on-env.txt` plus the two variables, not
    `off2-env.txt`.
- **F2 — A clean relaunch works.** Tested with no cache variable set, so DC 4 is unaffected.
  - `pkill -TERM -x Ollama` stopped the app and its server in 1 s.
  - `env -i HOME USER PATH open -g -a Ollama --env THESIS_PROBE_OPEN=1` started it with 18
    variables, none of them from the shell, and with no `_`.
  - A variable set with `launchctl setenv THESIS_PROBE_LAUNCHD 1` arrived too, so launchd's
    environment reaches the app.
  - The probe was unset again. Ollama 0.33.2 now runs clean (pid 45444), with no model loaded.
- **F3 — The runner's batch size is not fixed (out of scope; for the author).**
  - The runner Ollama started at login had `-b 512 -ub 512` (`E/on-argv.txt`, and resolve-f1's
    2026-10-04 capture). Every runner since the RCA's first restart had `-b 1024 -ub 1024`. That
    includes one loaded today on the clean server at pressure 1.
  - The flag is on argv, so Ollama chooses it. llama-server's fit step logged "no changes needed".
    The cause is not known.
  - The batch size changes prefill speed and the compute buffers' memory, and `env-check` neither
    pins nor records it. DC 8's cache-on medians came from a `-b 512` runner.
  - Suggestion: record `-b`/`-ub` in the envelope before Phase 7, as a separate decision.

Found at the build and the main session's re-check, 2026-10-29.

- **F4 — DC 4's exit code; reworded by the author's decision (2026-10-29).** DC 4 said "`make
  env-check` exits 1". The check failed as intended, naming both settings. But GNU Make 3.81 exits 2
  when any recipe fails, and only the script itself exits 1 (`evidence/live/dc4-env-check.txt`,
  `dc4-env-check-direct.txt`; re-checked in `evidence/recheck/dc4-*.txt`). The intention was "the
  check fails", so DC 4 now reads "fails (make 2, the script 1)". No test changed.
- **F5 — Amazon-PQA text in the evidence.** `E/prompts.jsonl` and `P/prompts.jsonl` hold
  workload questions (48 and 284 of them) and product chunk text. Its redistribution is not granted
  (CLAUDE.md). No other evidence file holds either, checked against all 583 validation questions of
  over 40 characters. By the repo rule for this case, both files move under `private/`, which is
  gitignored (`docs/work/*/evidence/**/private/`), and an IDs-only manifest stays beside each one
  (plan Phase 8).
- **F6 — The footprint level differs between runs; the flatness does not.**
  - The executor's 300-request run dropped from 3,059 MB after load to about 2,580 MB at
    request 1, then stayed flat.
  - The re-check run stayed near 3,080 MB from the start.
  - Both rose by at most a few MB over the run. So the docs keep "3.0–3.1 GB at load" and add no
    steady-state figure.
- **F7 — The edit hook re-formatted `env_check.py`.** It runs `ruff format` at the default 88
  columns outside `rag/`, so the whole file was re-wrapped. Its diff is 278 lines, and about 120 of
  them are the change. Kept as it is (the author, 2026-10-29).
