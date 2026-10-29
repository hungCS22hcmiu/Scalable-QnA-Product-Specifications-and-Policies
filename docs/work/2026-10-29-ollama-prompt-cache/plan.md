# Plan — Ollama's runner keeps every prompt in RAM

Design: design.md (approved 2026-10-29)

Paths used below:
- `T` = `docs/work/2026-10-29-ollama-prompt-cache`
- `E` = `T/evidence/rca` (the RCA's files; read them, never edit them)
- `P` = `T/evidence/probe` (new)
- `L` = `T/evidence/live` (new)

Rules for every step:
- Run commands from the repo root.
- Use `python3 -m pytest`, not `pytest`: the bare command may not be on `PATH` outside `make`.
- Before any step that loads a model, run `sysctl -n kern.memorystatus_vm_pressure_level` and write
  the value in the step's `Result:` line. Yellow (2) and swap are allowed in this task (the author,
  2026-10-29). Red (4) stops the step: report it.
- Every live number here is `citable: no`.
- Never run `make ollama-env` before step 7.5. DC 4 needs the variables unset.

## Phase 1 — The failing test

- [x] 1.1 Write `experiments/tests/test_env_check_runner_cache.py` with its fixtures, its fakes and
  the DC 1 witness only (design §3, "experiments/tests/…").
  - Files: `experiments/tests/test_env_check_runner_cache.py`
  - Contents:
    - **Docstring:** in the style of `test_env_check.py`. It says what the file guards (a runner with
      the prompt cache on must fail `make env-check`), and that fixtures come from `E/on-argv.txt`
      and `E/on-env.txt` with `/Users/hung` replaced by `/Users/u`.
    - **Constants:** `CAPTURED_ON_ARGV`, the one line of `E/on-argv.txt`. `ON_ENV`, the tokens of
      `E/on-env.txt` as a list, with `SSH_AUTH_SOCK` and `TMPDIR` given placeholder values.
      `FIXED_ENV = ON_ENV + ["LLAMA_ARG_CACHE_RAM=0", "LLAMA_ARG_CTX_CHECKPOINTS=0"]`.
      `RUNNER_PID = 34349`. `SERVER = 19379`.
    - **`_make_argv() -> list[str]`:**
      - runs `["make", "-n", "--no-print-directory", "env-check"]` with `cwd` = the repo root, and
        an environment copied from `os.environ` without `MAKEFLAGS`, `MFLAGS` and `MAKELEVEL`;
      - replaces `"\\\n"` with `" "`, applies `shlex.split`, and returns the tokens after the one
        that ends with `env_check.py`;
      - asserts that such a token was found.
    - **`_fake_rag(monkeypatch)`:** the same stand-in `rag.config` as in `test_env_check.py`. Copy
      it; do not import it from that file.
    - **`_observed()`:** an `env_check.Observed` for the captured runner: version `0.33.2`, np 1,
      ctx 8192, port 49434, total_slots 1, n_ctx 8192, model = the LLM blob.
    - **`_fake_runner(monkeypatch, argv_line, env_tokens, eww=None, ps_fails=False)`:**
      - patches `env_check.observe` to return `_observed()`;
      - patches `env_check._run` to answer exactly
        `["ps", "-ww", "-o", "command=", "-p", str(RUNNER_PID)]` with `argv_line + "\n"`, and
        `["ps", "eww", "-o", "command=", "-p", str(RUNNER_PID)]` with
        `(eww if eww is not None else argv_line + " " + " ".join(env_tokens)) + "\n"`;
      - any other command raises `AssertionError`;
      - with `ps_fails=True`, both `ps` calls raise `subprocess.CalledProcessError(1, cmd)`.
    - **`_main(monkeypatch, argv) -> int`:** sets `sys.argv = ["env_check.py", *argv]` and returns
      `env_check.main()`.
    - **`test_make_env_check_fails_on_the_captured_cache_on_runner(monkeypatch, capsys)`:** fakes
      the cache-on runner (`CAPTURED_ON_ARGV`, `ON_ENV`) and runs `_main` with `_make_argv()`. It
      asserts exit 1 and that `"prompt cache"` is in the output.
    - Reach any new function as `env_check.<name>` at call time, never with
      `from env_check import`. Then the file imports cleanly before the fix.
  - Run: `python3 -m pytest experiments/tests/test_env_check_runner_cache.py -q 2>&1 | tee T/evidence/phase1-witness.txt`
  - Pass: `1 failed`. The failure is the exit-code assertion: env-check returned 0 on the cache-on
    runner. That is the reason in §1. An `ImportError`, a fixture error or a `make` error is not a
    pass.
  - Result: wrote experiments/tests/test_env_check_runner_cache.py (witness only); `1 failed` on `assert rc == 1` (env-check printed OK, exit 0, on the cache-on runner); no model loaded; output in evidence/phase1-witness.txt

## Phase 2 — The fix

- [x] 2.1 Add the pure functions to `experiments/scripts/env_check.py`, in its "Pure" section,
  exactly as design §3 names them: `_CACHE_FLAGS`, `CacheSetting`, `runner_env`, `runner_cache`,
  `check_runner_cache`, `runner_cache_line`.
  - Files: `experiments/scripts/env_check.py`
  - Details:
    - `runner_cache` treats a token `--cache-ram=N` (any spelling followed by `=`) as the flag.
    - `check_runner_cache` compares the value as text with `str(frozen[name])`.
    - The message prefixes are exactly `runner prompt cache` and `runner context checkpoints`.
  - Run: `make lint`, then `python3 -m pytest experiments/tests/test_env_check.py -q`
  - Pass: no lint finding, and every existing test passes.
  - Result: added _CACHE_FLAGS, CacheSetting, runner_env, runner_cache, check_runner_cache, runner_cache_line to env_check.py; `make lint` clean, test_env_check.py 44 passed (the edit hook re-wrapped existing lines of env_check.py to 88 columns, behaviour unchanged)
- [x] 2.2 Wire the check into `main()` and add `_read_runner_env` (design §3, `main()` bullets).
  Update the module docstring: two rows in the table (the cache settings, observed from the runner's
  argv and environment), and replace "an environment nobody can read back" with a sentence saying
  that `ps eww` shows it (ADR-017).
  - Files: `experiments/scripts/env_check.py`
  - Run: `python3 -m pytest experiments/tests/test_env_check.py -q`, then `git diff --stat experiments/tests/`
  - Pass: every existing test passes, and `git diff --stat experiments/tests/` prints nothing (the
    new file is untracked, so it does not show).
  - Result: added _read_runner_env, --cache-ram/--ctx-checkpoints in main() (RUNNER_CACHE line before ENVELOPE, unverifiable env joins the FAIL list), and the docstring rows; test_env_check.py 44 passed, `git diff --stat experiments/tests/` prints nothing, lint clean
- [x] 2.3 In the `Makefile` envelope block (after `LLM_BLOB`), add `RUNNER_CACHE_RAM := 0` and
  `RUNNER_CTX_CHECKPOINTS := 0`, with a short comment citing ADR-017 and saying they are not
  exported. Make the `env-check` recipe pass
  `--cache-ram $(RUNNER_CACHE_RAM) --ctx-checkpoints $(RUNNER_CTX_CHECKPOINTS)`, and change its
  help text to mention the prompt cache.
  - Files: `Makefile`
  - Run: `make -n env-check`, then `python3 -m pytest experiments/tests/test_env_check_runner_cache.py -q`
  - Pass: the dry run shows `--cache-ram 0 --ctx-checkpoints 0`, and the witness passes.
  - Result: added RUNNER_CACHE_RAM := 0 and RUNNER_CTX_CHECKPOINTS := 0 to the Makefile envelope block and passed them in env-check; `make -n env-check` shows `--cache-ram 0 --ctx-checkpoints 0`, the witness now `1 passed`
- [x] 2.4 Add the `ollama-env` target and its `.PHONY` entry (design §3, `Makefile`, steps 1–5).
  - Files: `Makefile`
  - Details:
    - Help text: `Turn off llama-server's prompt cache for Ollama.app and restart it (ADR-017). After
      every reboot; never during a run`.
    - Use `http://localhost:11434` for `/api/version`; it is `rag.config`'s default.
    - If `ollama serve` is still running after 30 s, print that it was probably started outside
      Ollama.app, and exit 1.
    - If `/api/version` does not answer within 60 s, exit 1.
  - Run: `make help | grep ollama-env`, then `make -n ollama-env`
  - Pass: the target is listed. The dry run shows, in order: two `launchctl setenv` lines,
    `pkill -TERM -x Ollama`, the wait, `env -i HOME=… USER=… PATH=/usr/bin:/bin:/usr/sbin:/sbin open -g -a Ollama`,
    the second wait, and the print. **Do not run it.**
  - Result: added the ollama-env target and .PHONY entry; `make help` lists it and `make -n ollama-env` shows setenv x2, pkill, wait, `env -i ... open -g -a Ollama`, wait, print (not run); serve detection uses `pgrep -f -x ".*/ollama serve"`, and the print step exits 1 if no LLAMA_ARG_* reached the server

## Phase 3 — Unit tests

- [x] 3.1 Add the DC 2 tests to `experiments/tests/test_env_check_runner_cache.py`. Each test uses
  `_make_argv()` unless it says otherwise.
  - Files: `experiments/tests/test_env_check_runner_cache.py`
  - Tests:
    - `test_make_env_check_passes_the_captured_fixed_runner`: `CAPTURED_ON_ARGV` with `FIXED_ENV`
      exits 0. One line starts with `RUNNER_CACHE cache_ram=0 ctx_checkpoints=0`, and the last line
      starts with `ENVELOPE `.
    - `test_an_argv_flag_beats_a_zero_in_the_environment`, parametrized over ` --cache-ram 8192`,
      ` --cache-ram=8192`, ` -cram 8192`, ` --ctx-checkpoints 32`, ` -ctxcp 32` and
      ` --swa-checkpoints 32`, each appended to `CAPTURED_ON_ARGV` with `FIXED_ENV`: exit 1.
    - `test_a_zero_on_argv_passes_without_the_variables`: `CAPTURED_ON_ARGV` plus
      ` --cache-ram 0 --ctx-checkpoints 0`, with `ON_ENV`: exit 0.
    - `test_a_missing_wrong_or_doubled_variable_fails`, parametrized over `FIXED_ENV` with:
      - `LLAMA_ARG_CACHE_RAM=0` removed;
      - `LLAMA_ARG_CTX_CHECKPOINTS=0` removed;
      - `LLAMA_ARG_CACHE_RAM=8192` instead;
      - `LLAMA_ARG_CTX_CHECKPOINTS=32` instead;
      - `LLAMA_ARG_CACHE_RAM=8192` added a second time.

      Each one exits 1.
    - `test_an_environment_that_cannot_be_read_fails_closed`, parametrized over `ps` raising
      (`ps_fails=True`), `eww` equal to the argv alone, and `eww` that does not start with the argv.
      Each one exits 1, with `not verifiable` in the output.
    - `test_an_environment_token_inside_argv_is_not_read`: `CAPTURED_ON_ARGV` plus
      ` --chat-template LLAMA_ARG_CACHE_RAM=0`, with `ON_ENV`: exit 1.
    - `test_one_cache_argument_without_the_other_fails`: `_make_argv()` with the
      `--ctx-checkpoints` pair removed: exit 1.
    - `test_runner_cache_reads_argv_then_env_then_unset`: calls `env_check.runner_cache` directly
      and checks the `source` field of each of the three cases.
  - Run: `python3 -m pytest experiments/tests/test_env_check_runner_cache.py -q`
  - Pass: every test passes.
  - Result: added the DC 2 tests (fixed runner, 6 argv spellings, zero on argv, 5 bad variables, 3 unreadable-environment cases, token in argv, one argument alone x2, runner_cache sources); `21 passed` in the new file
- [x] 3.2 `make lint`
  - Pass: no finding.
  - Result: `make lint` printed "All checks passed!" and `go vet` raised nothing

## Phase 4 — Probe scripts (no model loaded)

- [x] 4.1 Write `P/build_prompts.py <workload> <out> <n>` from `E/scripts/build_prompts.py`. Change
  only the selection: first pass, the first item of each `cluster_id` in file order; second pass,
  further items in file order whose `qa_id` is not taken yet, until `n`. Keep its prompt building
  (`rag.retrieve.retrieve` with `product_id`, then `rag.generate._build_prompt`) and its output
  fields. Its docstring says `citable: no`.
  - Files: `P/build_prompts.py`
  - Run: `python3 -m py_compile P/build_prompts.py`
  - Pass: it compiles.
  - Result: wrote evidence/probe/build_prompts.py (pick() takes the first item per cluster_id, then unseen qa_ids; docstring says citable: no); compiles, and pick() on the validation workload gives 300 distinct qa_ids, first 270 from 270 clusters (no model loaded)
- [x] 4.2 Write `P/run_arm.py` as a copy of `E/scripts/run_arm.py` with one change. Before taking the
  log offset and loading, it unloads the LLM (`/api/generate` with `{"model": MODEL, "keep_alive": 0}`)
  and waits up to 30 s until no LLM runner is left. If one is still there, it exits 2. This needs a
  `runner()` variant that returns `None` instead of exiting. Keep everything else: the request body,
  the samples, the red stop, and the log capture.
  - Files: `P/run_arm.py`
  - Run: `python3 -m py_compile P/run_arm.py`
  - Pass: it compiles.
  - Result: wrote evidence/probe/run_arm.py as a copy of the RCA script plus unload() (keep_alive 0, waits up to 30 s, exit 2) and runner_or_none(); also an added guard: exit 4 and do not save env.txt if the runner environment has a TOKEN/SECRET/KEY-like name; compiles, ruff clean, runner_or_none() returns None with no model loaded
- [x] 4.3 Write `P/repeat.py <prompts> <outdir>`. It sends the first prompt in `<prompts>` three times
  in a row, with the same request body as `run_arm.py`, and writes `<outdir>/repeat-samples.jsonl`
  with `i`, `prompt_tokens` and `prompt_s` (`prompt_eval_duration / 1e9`).
  - Files: `P/repeat.py`
  - Run: `python3 -m py_compile P/repeat.py`
  - Pass: it compiles.
  - Result: wrote evidence/probe/repeat.py (sends prompt 1 three times with run_arm.py request body, writes repeat-samples.jsonl with i, prompt_tokens, prompt_s); compiles
- [x] 4.4 Write `P/verdict.py`, with the arguments `--samples`, `--log`, `--prompts`, an optional
  `--repeat`, `--n` (default 300) and `--window` (default 50). It prints one `PASS`/`FAIL` line with
  its numbers for each check below, and exits 0 only if all pass.
  - Files: `P/verdict.py`
  - Checks:
    - `n` request samples (lines with `wall_s`) and no `abort` line;
    - the first `n` prompts in `--prompts` are distinct (by `prompt` text);
    - one `runner_pid` in every sample, sample 0 included;
    - every `footprint_mb` is a number;
    - DC 6: the mean of the last `window` footprints minus the mean of the first `window` is at
      most 100 MB;
    - the log contains `prompt cache is disabled` and `context checkpoints disabled`, and no
      `cache state:`;
    - DC 8: the median of `prompt_tokens / prompt_s` is at least 431, and the median of
      `eval_tokens / eval_s` is at least 32.0;
    - with `--repeat`, DC 7: samples 2 and 3 each have `prompt_s` at least 0.8 × sample 1's.

    It also prints the highest pressure seen, which is not a check.
  - Run: `python3 -m py_compile P/verdict.py`
  - Pass: it compiles.
  - Result: wrote evidence/probe/verdict.py (7 checks, plus DC 7 with --repeat; PASS/FAIL line each, highest pressure printed as a non-check; exit 0 only if all pass); compiles
- [x] 4.5 Show that `verdict.py` can fail. Run it on the RCA's cache-on arm.
  - Run: `python3 P/verdict.py --samples E/on-samples.jsonl --log E/on-server-log.txt --prompts E/prompts.jsonl --n 50 --window 10 | tee P/selftest-on.txt`
  - Pass: exit 1, with exactly two FAIL lines: the footprint (an increase above 2,000 MB) and the
    log check (`cache state:` present, the "disabled" lines absent). Every other line is PASS.
  - Result: exit 1 with exactly two FAIL lines: footprint +3301 MB (limit 100) and the log ("cache state:" x50, no "disabled" lines); the other five lines PASS (prefill 479, decode 35.5 tok/s); output in evidence/probe/selftest-on.txt
- [x] 4.6 Show that the "this load" guard works. The RCA's fixed arm reused a model that was already
  loaded, so its log holds no load lines.
  - Run: `python3 P/verdict.py --samples E/off2-samples.jsonl --log E/off2-server-log.txt --prompts E/prompts.jsonl --n 50 --window 10 | tee P/selftest-off2.txt`
  - Pass: exit 1, with exactly one FAIL line: the log check (no "disabled" lines). Every other line
    is PASS.
  - Result: exit 1 with exactly one FAIL line, the log ("disabled" lines x0, since that arm reused a loaded model); footprint -395 MB, 508 / 36.9 tok/s, all other lines PASS; output in evidence/probe/selftest-off2.txt

## Phase 5 — The probe prompts (loads the embedding model; `citable: no`)

- [x] 5.1 Build the 300 prompts. Redis must hold `v1`: `redis-cli PING` returns `PONG`, and
  `make corpus-index-check` passes. Check pressure first.
  - Run: `python3 P/build_prompts.py data/workload-v1-validation.json P/prompts.jsonl 300`
  - Pass: it prints `300 prompts written`, and
    `python3 -c "import json; r=[json.loads(l) for l in open('P/prompts.jsonl')]; print(len(r), len({x['prompt'] for x in r}))"`
    prints `300 300`.
  - Result: redis PONG and corpus-index-check PASS (539 chunks); pressure 1 before and after; build_prompts.py printed "300 prompts written", and the distinct check printed `300 300` (evidence/probe/prompts.jsonl, citable: no)

## Phase 6 — Records

- [x] 6.1 Append ADR-017 to `docs/decisions.md` after ADR-016, in the format under "How to use this
  file".
  - Files: `docs/decisions.md`
  - Content (design §3, "ADR-017"):
    - **Title:** "The model runner keeps no prompt cache and no context checkpoints; envelope memory
      is read with `footprint`". **Decided (frozen)** · 2026-10-29, listing the files this task
      touches and the trail.
    - **Rationale:** the RCA's numbers from design §1 (3,066 → 7,088 MB over 50 prompts; about
      82 MB per prompt; 47 of 47 restores at `n_past = 1`; 0.05 s against 1.29 s repeat prefill
      with checkpoints on; 3,071 → 2,685 MB and 479 → 508 / 35.5 → 36.9 tok/s with both off). It
      names `P/verdict.txt` as the 300-request check.
    - **Alternatives:** a small `cache-ram`; turning off only the cache; reading the server log; a
      login LaunchAgent; a newer Ollama or a raw llama-server.
    - **Consequences:**
      - S2's fixed-at-load memory holds, as a measured footprint;
      - the 855 MB vision encoder is accepted;
      - `make ollama-env` runs after every reboot, with a clean environment (design §4 F1, F2);
      - other projects' models lose the prompt cache too;
      - the residual of failure mode 4 (a build that ignores the variable);
      - memory is read with `footprint`, never RSS or `/api/ps`;
      - the batch-size finding (§4 F3) is left open for the author;
      - stale lines, listed but not edited: `CLAUDE.md` (the hardware-envelope bullet, `:185–186`)
        and `Final_Proposal.md` (`:280`, `:333`, `:340`).
    - **Invalidates:** design §2's "Invalidates" bullet.
  - Run: `grep -c '^### ADR-017 ' docs/decisions.md`, then `awk '/^### ADR-017 /,0' docs/decisions.md | grep -c '^- \*\*Invalidates:\*\*'`
  - Pass: `1` and `1`.
  - Result: appended ADR-017 to docs/decisions.md (rationale with the RCA numbers, five alternatives, consequences incl. F3 and the stale lines, Invalidates); the two greps print 1 and 1
- [x] 6.2 Add the ADR-017 row to the `docs/decisions.md` Summary table, in the same columns.
  Add an "(**amended by ADR-017**: …)" note in the "Memory envelope" row (now `:73`) and next to
  ADR-003's "The 1.7 GB resident" (`:415`). Each note gives Ollama's estimate against the measured
  footprint, 3.03–3.07 GB at load, read with `footprint`. Do not delete or reword the old text.
  - Files: `docs/decisions.md`
  - Run: `grep -n 'ADR-017' docs/decisions.md`
  - Pass: hits in the Summary table, at the Memory envelope row, in ADR-003's body, and in ADR-017.
  - Result: added the ADR-017 Summary row and "amended by ADR-017" notes at the Memory envelope row (:74) and in ADR-003 (:416-419), old text kept; `grep -n ADR-017` hits at :59, :74, :417 and :1569
- [x] 6.3 Update `docs/contracts/interfaces.md`:
  - the frozen study-wide list (now `:805`) gains "llama-server's prompt cache and context
    checkpoints off (`LLAMA_ARG_CACHE_RAM=0`, `LLAMA_ARG_CTX_CHECKPOINTS=0`, **ADR-017**; `make
    env-check` reads them from the live runner)";
  - a **v0.22** row at the top of the Versioning table, in the style of v0.21's. It says no wire
    shape, `.proto` or §A–§H change, and that `source_chunk_ids`, `t1_key` and `dataset_epoch` are
    untouched;
  - the Status line becomes `Draft v0.22`, revised 2026-10-29.
  - Files: `docs/contracts/interfaces.md`
  - Run: `grep -n 'LLAMA_ARG_CACHE_RAM\|v0.22' docs/contracts/interfaces.md`
  - Pass: the frozen list, the Versioning row and the Status line each show.
  - Result: interfaces.md: frozen study-wide list gains both settings (:806), a v0.22 Versioning row on top (:789), Status line and "Current version" line moved to v0.22; grep shows all of them
- [x] 6.4 Update `README.md`:
  - `:42` and `:123`: replace "1.7 GB resident" with the measured footprint (about 3.0–3.1 GB at
    load, read with `footprint`; 1.7 GB was Ollama's own estimate), citing ADR-017;
  - `:184–186`, the "not yet fixed" bullet: replace it with one bullet saying the runner keeps no
    prompt cache (ADR-017), and that `make ollama-env` runs after every reboot.
  - Files: `README.md`
  - Run: command 4 of step 7.9
  - Pass: it prints `OK`.
  - Result: README.md: :42 and :123 now give the measured footprint (about 3.0–3.1 GB at load, `footprint`) and keep 1.7 GB as Ollama estimate, citing ADR-017; the "not yet fixed" bullet is one bullet on ADR-017 plus `make ollama-env` after every reboot; the 7.9 command-4 check printed OK

## Phase 7 — Run and verify (each step is the done condition with the same number)

- [x] 7.1 Done condition 1 — the witness passes after the fix.
  - Run: `python3 -m pytest experiments/tests/test_env_check_runner_cache.py -q -k fails_on_the_captured_cache_on_runner`
  - Pass: `1 passed`, and `T/evidence/phase1-witness.txt` shows it failed before the fix.
  - Result: `1 passed, 20 deselected`; evidence/phase1-witness.txt shows the same test `1 failed` before the fix
- [x] 7.2 Done condition 2 — every case.
  - Run: `python3 -m pytest experiments/tests/test_env_check_runner_cache.py -q`
  - Pass: all pass.
  - Result: `21 passed` in test_env_check_runner_cache.py (witness, fixed runner, argv beats env x6, zero on argv, bad variables x5, unreadable env x3, token in argv, one argument alone x2, source order)
- [x] 7.3 Done condition 3 — the old tests are untouched.
  - Run: `python3 -m pytest experiments/tests -q`, then `git diff --quiet experiments/tests/test_env_check.py; echo $?`
  - Pass: no failure, and `0`.
  - Result: `pytest experiments/tests -q`: 778 passed; `git diff --quiet experiments/tests/test_env_check.py` exit 0
- [x] 7.4 Done condition 4 — the variables are unset, and env-check fails. Loads both models; check
  pressure first; `citable: no`.
  - Run: `launchctl getenv LLAMA_ARG_CACHE_RAM; launchctl getenv LLAMA_ARG_CTX_CHECKPOINTS`, then
    `make env-check > L/dc4-env-check.txt 2>&1; echo "exit $?"; cat L/dc4-env-check.txt`
    (the shell is zsh, so no `PIPESTATUS`)
  - Pass: both `getenv` print nothing, the exit is `1`, and the output contains
    `runner prompt cache` and `runner context checkpoints`.
  - Result: Held back first: the pass condition `exit 1` did not hold literally. Pressure 1 before (2 after); both `getenv` print nothing; output names `runner prompt cache` and `runner context checkpoints` (both unset). `make env-check` exits 2, not 1: GNU Make 3.81 returns 2 for any failed recipe ("Error 1"), while `python3 experiments/scripts/env_check.py ...` run directly exits 1 (evidence/live/dc4-env-check-direct.txt). Plan wording to be settled by the human. Passes DC 4 as reworded 2026-10-29 (design §4 F4).
- [x] 7.5 Done condition 5 — after `make ollama-env`, env-check passes. Loads both models; check
  pressure first; `citable: no`.
  - Run:
    1. `make ollama-env > L/dc5-ollama-env.txt 2>&1; echo "exit $?"; cat L/dc5-ollama-env.txt`
    2. `make env-check > L/dc5-env-check.txt 2>&1; echo "exit $?"; cat L/dc5-env-check.txt`
    3. `ps eww -o command= -p "$(pgrep -x ollama | head -1)" | tr ' ' '\n' | grep -E '^(_|LLAMA_ARG_[A-Z_]*)=' | tee L/dc5-serve-env.txt`
  - Pass: both exits are `0`. In `L/dc5-env-check.txt`, one line starts with
    `RUNNER_CACHE cache_ram=0 ctx_checkpoints=0`, and the last line starts with `ENVELOPE `.
    `L/dc5-serve-env.txt` has both `LLAMA_ARG_*=0` lines and no `_=` line.
  - Result: pressure 2 before `make ollama-env`, 1 before `make env-check`; both exit 0 (new ollama serve pid 62494); env-check prints `observed cache_ram=0 (env) · ctx_checkpoints=0 (env)`, `RUNNER_CACHE cache_ram=0 ctx_checkpoints=0 runner_pid=62714`, ENVELOPE last; serve env has both LLAMA_ARG_*=0 and no `_=` line (evidence/live/dc5-*.txt, citable: no)
- [x] 7.6 Done condition 6 — memory stays flat over 300 requests. It takes about 15 minutes, longer
  than the 10-minute foreground limit, so run it with Bash `run_in_background: true` and wait for it
  to finish. Check pressure first; `citable: no`.
  - Run: `python3 P/run_arm.py fixed P/prompts.jsonl P/out`, then
    `python3 P/verdict.py --samples P/out/fixed-samples.jsonl --log P/out/fixed-server-log.txt --prompts P/prompts.jsonl > P/verdict-dc6.txt; cat P/verdict-dc6.txt`
  - Pass: in `P/verdict-dc6.txt`, every check before the DC 8 line is PASS. The exit code is not
    used here, because DC 8 has its own step.
  - Result: pressure 2 before load and on requests 1-3, then 1 for requests 4-300 (swap not checked); run_arm exit 0, 300 requests, one runner pid 63308; footprint samples 1-50 mean 2588 MB, 251-300 mean 2589 MB (+1, limit 100); log has "prompt cache is disabled" x1, "context checkpoints disabled" x1, no "cache state:"; every check before DC 8 PASS (evidence/probe/verdict-dc6.txt, citable: no)
- [x] 7.7 Done condition 7 — no hidden reuse. Run this right after 7.6. `citable: no`.
  - Run: `python3 P/repeat.py P/prompts.jsonl P/out`, then
    `python3 P/verdict.py --samples P/out/fixed-samples.jsonl --log P/out/fixed-server-log.txt --prompts P/prompts.jsonl --repeat P/out/repeat-samples.jsonl > P/verdict.txt; echo "exit $?"; cat P/verdict.txt`
  - Pass: the DC 7 line in `P/verdict.txt` is PASS. `P/verdict.txt` is the record ADR-017 names.
  - Result: pressure 1; repeat prefill 1.340 s, 1.334 s, 1.359 s (each >= 1.072 s; before the fix 0.05 s against 1.29 s); DC 7 line PASS and all 8 lines PASS, exit 0 (evidence/probe/verdict.txt, citable: no)
- [x] 7.8 Done condition 8 — speed.
  - Run: read the DC 8 line of `P/verdict.txt`
  - Pass: PASS. If it fails while the highest pressure was above 1, report it with the pressure
    and stop (design §3, edge cases). It is not the one quick fix.
  - Result: DC 8 line PASS: median prefill 484 tok/s (min 431), median decode 34.8 tok/s (min 32.0); highest pressure seen 2, so no pressure caveat was needed (citable: no)
- [x] 7.9 Done condition 9 — records.
  - Run:
    1. `grep -c '^### ADR-017 ' docs/decisions.md`
    2. `grep -nE '^RUNNER_(CACHE_RAM|CTX_CHECKPOINTS) := 0$' Makefile`
    3. `grep -n 'LLAMA_ARG_CACHE_RAM' docs/contracts/interfaces.md`
    4. Every "1.7 GB" in `README.md` and `docs/decisions.md` has "footprint" on its own line or
       the next one:
       ```bash
       python3 - <<'EOF'
       import re, sys
       bad = []
       for p in ("README.md", "docs/decisions.md"):
           lines = open(p).read().splitlines()
           for i, line in enumerate(lines):
               window = line + " " + (lines[i + 1] if i + 1 < len(lines) else "")
               if re.search(r"1\.7 GB", line) and "footprint" not in window:
                   bad.append(f"{p}:{i + 1}")
       print("OK" if not bad else "missing footprint at " + ", ".join(bad))
       sys.exit(1 if bad else 0)
       EOF
       ```
  - Pass: `1`; two Makefile lines; at least one hit; `OK`.
  - Result: grep 1: `1`; grep 2: Makefile:42 and :43; grep 3: interfaces.md :789 and :806; the 1.7 GB footprint check prints OK (exit 0)
- [x] 7.10 Done condition 10 — `make verify`.
  - Pass: no FAIL. Any SKIPPED target is listed by name.
  - Result: `make verify` exit 0: lint clean, go build and tests ok, rag 62 passed, experiments 778 passed; no FAIL and no SKIPPED target (evidence/live/make-verify.txt)

## Phase 8 — Review fixes (the author, 2026-10-29; design §4 F4, F5)

Run this phase only after the main session says its re-check run has finished, because that run
reads `P/prompts.jsonl`.

- [x] 8.1 Make two wording fixes in `docs/decisions.md`.
  - Files: `docs/decisions.md`
  - **ADR-003's note** (now `:417–419`). Replace the three lines from `resident is a one-slot
    figure, consistent with this entry. (**Amended by ADR-017, 2026-10-29,** measured with` through
    `3.03–3.07 GB, read with \`footprint\`.)` with exactly:
    ```
        resident is a one-slot figure, consistent with this entry. (**Amended by ADR-017,** read with
        `footprint`: 1.7 GB was Ollama's own estimate, `/api/ps` 1.588 GiB; the measured footprint at
        load is 3.03–3.07 GB.)
    ```
  - **ADR-017's `make ollama-env` bullet** (now `:1619–1620`). Replace `` `make env-check`
    exits 1 until it has run. `` with `` `make env-check` fails until it has run. ``
  - Run: command 4 of step 7.9, then `grep -n 'exits 1 until' docs/decisions.md`
  - Pass: `OK`, and the grep finds nothing.
  - Result: ADR-003 note replaced with the three lines as specified and ADR-017 now says "fails until it has run"; check 4 printed OK and the grep finds nothing. One quick fix: the plan's line breaks left check 4 failing at decisions.md:416 (no "footprint" in the next line), so I moved the line break after "read with `footprint`:", same words
- [x] 8.2 Move the two Amazon-PQA files under `private/` and leave an IDs-only manifest beside each
  (design §4 F5). This is the one allowed change to `E/`.
  - Files: `E/prompts.jsonl` → `E/private/prompts.jsonl`; `P/prompts.jsonl` →
    `P/private/prompts.jsonl`; new `E/prompts-manifest.json` and `P/prompts-manifest.json`.
  - Each manifest is JSON with these keys:
    - `file`: `"private/prompts.jsonl"`;
    - `sha256` and `count`: of the moved file;
    - `qa_ids`: in file order;
    - `rebuild`: the command that regenerates the file. For `E`, that is
      `python3 E/scripts/build_prompts.py data/workload-v1-validation.json E/private/prompts.jsonl 50`;
      for `P`, it is
      `python3 P/build_prompts.py data/workload-v1-validation.json P/private/prompts.jsonl 300`.
      Write both with the full `docs/work/…` paths;
    - `why`: "Amazon-PQA question and chunk text; redistribution is not granted (CLAUDE.md). design.md §4 F5."
  - Run, from the repo root:
    1. `git check-ignore -v docs/work/2026-10-29-ollama-prompt-cache/evidence/rca/private/prompts.jsonl docs/work/2026-10-29-ollama-prompt-cache/evidence/probe/private/prompts.jsonl`
    2. `git status --porcelain --untracked-files=all docs/work/2026-10-29-ollama-prompt-cache | grep -i prompts`
    3. this scan, which must print `0 files`:
       ```bash
       python3 - <<'EOF'
       import json, glob, os
       T = "docs/work/2026-10-29-ollama-prompt-cache/evidence"
       qs = [i["question"] for i in json.load(open("data/workload-v1-validation.json")) if len(i["question"]) > 40]
       hits = [f for f in glob.glob(f"{T}/**/*", recursive=True)
               if os.path.isfile(f) and "/private/" not in f
               and any(q in open(f, errors="replace").read() for q in qs)]
       print(len(hits), "files", hits)
       EOF
       ```
  - Pass:
    - command 1 prints two lines, each naming the `docs/work/*/evidence/**/private/` rule;
    - command 2 shows only the two manifests;
    - command 3 prints `0 files []`.
  - Result: Held back first, one literal mismatch. Both files moved under `private/` (rca 50 prompts, probe 300), both manifests written (sha256 and count re-checked against the moved files). Command 1 prints two lines naming `.gitignore:52 docs/work/*/evidence/**/private/`. Command 3 prints `0 files []`, recheck/ included. Command 2 prints the two manifests AND `rca/scripts/build_prompts.py` and `probe/build_prompts.py` (the grep matches their file names); nothing under `private/` shows. Tick if you accept the two scripts. Ticked by the main session 2026-10-29: command 2's `grep -i prompts` was too broad (the plan's error); `git status` shows no `prompts.jsonl` outside `private/`, the manifests match their files (sha256, count, qa_ids), and the scan finds 0 files.
- [x] 8.3 Tick step 7.4. Its evidence (`L/dc4-env-check.txt`: make exits 2; `L/dc4-env-check-direct.txt`:
  the script exits 1) passes DC 4 as the author reworded it (design §4 F4). Append to 7.4's
  `Result:` line: " Passes DC 4 as reworded 2026-10-29 (design §4 F4)."
  - Files: `T/plan.md`
  - Pass: 7.4 is ticked.
  - Result: ticked 7.4 and appended " Passes DC 4 as reworded 2026-10-29 (design §4 F4)." to its Result; I also changed the first words of my own earlier Result line from "NOT TICKED, ..." to "Held back first: ..." so it no longer contradicts the tick
- [x] 8.4 Re-run done conditions 9 and 10: the four commands of step 7.9, then `make verify`.
  - Pass: as in steps 7.9 and 7.10.
  - Result: step 7.9 again: `1`; Makefile :42 and :43; interfaces.md :789 and :806; the 1.7 GB footprint check prints OK. `make verify` exit 0, no FAIL, no SKIPPED target (rag 62 passed, experiments 778 passed, Go ok; evidence/live/make-verify-phase8.txt)
