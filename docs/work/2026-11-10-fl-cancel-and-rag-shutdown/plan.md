# Plan — Stop abandoned generations (F-L), and a graceful shutdown for rag.server

Design: design.md (approved 2026-11-10)

**Rules for every step.**
- `$T` below means `docs/work/2026-11-10-fl-cancel-and-rag-shutdown`. A command that uses it starts with
  `T=docs/work/2026-11-10-fl-cancel-and-rag-shutdown;`. Every command runs from the repo root unless it
  starts with `cd rag`.
- **Every command that runs Python tools starts with `export PATH="$HOME/Library/Python/3.13/bin:$PATH"`.**
  `pytest` and `ruff` live there, not on the default PATH, and without it `make test` prints
  `pytest SKIPPED — not installed` and proves nothing. Shell state does not carry between commands, so
  repeat it each time.
- A step marked **(model)** loads a model. Right before it, run `sysctl -n kern.memorystatus_vm_pressure_level`.
  `1` or `2`: go on, and write the level in the step's Result. `4`: stop and report. Every such step is
  `citable: no`.
- Existing tests are never edited (`execution.md`). `git status --porcelain rag/tests` must never show ` M`.
- Baseline, 2026-11-10, unfixed code: `cd rag && pytest -q` → **83 passed**.
- On a failed check: one quick fix only if the cause is obvious and local, then stop and report (`execution.md`).
- `- [-]` marks a step that a later phase replaced, so it is not run; the banner does not count it.

## Phase 1 — Before the fix: golden values, the failing test, the "before" probe

- [x] 1.1 Take the golden values from the unfixed code.
  - Files: `$T/evidence/golden_before.out` (new)
  - Run: `cd rag && python3 -c "import hashlib; from rag import generate; from rag.retrieve import RetrievedChunk; c=[RetrievedChunk(chunk_id='product-laptops-02#chunk-0', score=0.9, text='UltraBook Air 13: 13-inch display, 1.2 kg.', doc_id='product-laptops-02', ordinal=0)]; print(hashlib.sha256(generate._PROMPT_TEMPLATE.encode()).hexdigest()); print(hashlib.sha256(generate._build_prompt('How heavy is it?', c).encode()).hexdigest())" | tee ../$T/evidence/golden_before.out`
  - Pass: two lines. The first is `3e224f4500a18dc065ab6e24c46e25302ac275f8e145085bfb211bcf65ba67dd` (design.md §3,
    failure mode 4). The second is the golden prompt hash that 1.3 pins.
  - Result: wrote evidence/golden_before.out; line 1 is `3e224f45...67dd` (matches), line 2 is `c4f5162b72d7dca13ca8258a15c744022d5cfe05c18f7af223213d38c34a6377`

- [x] 1.2 Write the fake Ollama fixture.
  - Files: `rag/tests/conftest.py` (new)
  - What: class `FakeOllama`, a raw-socket HTTP/1.1 server on `127.0.0.1:0`, one daemon thread per
    connection. For each request it reads the headers and the `Content-Length` body and appends the parsed JSON
    to `.bodies`. Then it waits `delay` seconds (`None` = forever) in a `recv` loop with a short timeout, so it
    notices a client close: on `b""` it appends `time.monotonic()` to `.closed_at` and ends that connection.
    If the delay ends first, it sends `HTTP/1.1 200 OK`, `Content-Type: application/json`, `Connection: close`
    and the body `{"model": "fake", "response": <text>, "done": true}`, adds 1 to `.answered`, and closes.
    Attributes: `.url` (`http://127.0.0.1:<port>`), `.bodies`, `.closed_at`, `.answered`. `close()` shuts the
    listener **and every accepted connection**, so no gRPC worker stays blocked after a test. Fixture
    `fake_ollama`: a factory `fake_ollama(delay: float | None, text: str = "the full fake answer") -> FakeOllama`
    that closes every server it made at teardown. A module docstring says what it is for (design.md §3).
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && pytest -q`
  - Pass: 83 passed.
  - Result: added rag/tests/conftest.py (FakeOllama + fake_ollama fixture); 83 passed

- [x] 1.3 Write the cancel and body tests, and run the ones that apply to the unfixed code.
  - Files: `rag/tests/test_server_cancel.py` (new)
  - Shared fixture: an epoch file in `tmp_path` holding `41`, set with `monkeypatch.setenv(epoch.ENV, ...)`;
    `retrieve.fetch_by_ids` and `retrieve.retrieve` patched to return `([_CHUNK], 41)`, where `_CHUNK` is the
    `RetrievedChunk` of 1.1; `monkeypatch.setattr(config, "OLLAMA_BASE_URL", fake.url)`. Real servers come from
    `server.build_server("127.0.0.1:0")` and are stopped with `stop(None)` at teardown. A `FakeContext` class has
    `add_callback(cb)`, which stores `cb` and returns a value set per test.
  - Tests, with these exact names:
    - `test_cancel_closes_the_ollama_request` (DC 1a). Fake `delay=5`. Call `Answer` with
      `retrieved_chunk_ids=[_CHUNK.chunk_id]` through a real channel (`rag_pb2_grpc.RagServiceStub`). Wait until
      `fake.bodies` has one entry (at most 2 s), sleep 0.2 s, `call.cancel()`, record the time, and wait up to
      1.0 s for `fake.closed_at`. Assert it is set and at most 0.5 s after the cancel, with the message
      `"F-L: the Ollama request was not closed within 0.5 s of the cancel"`.
    - `test_stopped_answer_sends_no_chunk` (DC 1b). Direct call `server.RagServicer().Answer(request,
      FakeContext())` with `add_callback` returning `True`. A thread fires the stored callback 0.2 s after the
      fake got the body. Assert `list(gen) == []` and `fake.closed_at` is set.
    - `test_stop_before_generation_makes_no_ollama_call` (DC 1b). `add_callback` returns `False` (the RPC had
      already ended). Assert `list(gen) == []` and `fake.bodies == []`.
    - `test_a_cancel_does_not_reach_another_request` (DC 1c). Real server, fake `delay=1.0`. Two `Answer` calls
      at once; cancel the first 0.2 s after both bodies arrived. The second returns exactly one chunk with
      `text == "the full fake answer"`. Then a third `Answer`, sent after the cancel, returns the full text too.
    - `test_request_body_is_unchanged` (DC 2). Fake `delay=0`. `generate.generate("How heavy is it?", [_CHUNK])`
      returns `"the full fake answer"`, and `fake.bodies == [{"model": "qwen3.5:2b-q4_K_M", "prompt":
      generate._build_prompt("How heavy is it?", [_CHUNK]), "stream": False, "think": False, "options":
      {"num_ctx": 8192}}]`, with the literals written out, never read from `config`.
    - `test_prompt_is_unchanged` (DC 2). The sha256 of `generate._PROMPT_TEMPLATE` equals line 1 of
      `golden_before.out`, and the sha256 of `generate._build_prompt("How heavy is it?", [_CHUNK])` equals line 2.
      Both are written in the test as string constants.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && pytest -v tests/test_server_cancel.py -k "cancel_closes or body_is_unchanged or prompt_is_unchanged" 2>&1 | tee ../$T/evidence/dc1_before.out`
  - Pass: `test_request_body_is_unchanged` and `test_prompt_is_unchanged` PASS, because they pin today's
    behaviour. `test_cancel_closes_the_ollama_request` FAILS with the F-L message: the bug, reproduced. Any
    other failure reason is a stop.
  - Result: added rag/tests/test_server_cancel.py (6 tests); on unfixed code cancel test FAILS with the F-L message, body and prompt tests PASS; saved evidence/dc1_before.out

- [x] 1.4 Write the live probe and its runner.
  - Files: `$T/evidence/fl_probe.sh` (new), `$T/evidence/run_fl_probe.sh` (new)
  - `fl_probe.sh` (design.md §1 DC 5). Reads `GATEWAY_LOG` (required), `PRODUCT` (default
    `product-laptops-b07qvm5x8w`, which has 3 chunks in `v1`) and `ROUNDS` (default 5). It prints the pressure
    level, then:
    1. **Pilot.** For each of 3 candidate A questions that ask for a long answer (for example "Explain in full
       detail every specification of this laptop, one by one, and what each means for a buyer, then its return
       and warranty policy."), call rag.server's `Answer` straight over gRPC on `localhost:50051` (an inline
       `python3 - <<'EOF'` using `rag.pb.rag.v1`, `product_id=$PRODUCT`, no `retrieved_chunk_ids`) and time it.
       Keep the first that takes at least 4 s. If none does, print `NO PILOT` and exit 3.
    2. **B alone.** `ROUNDS` times, B exactly as in `probe_ollama_stops.sh` (model `qwen3.5:2b-q4_K_M`,
       `think: false`, `num_ctx` 8192), timed by `curl -w '%{time_total}'`.
    3. **Rounds.** `ROUNDS` times: count the `abandoned while generating` lines in `GATEWAY_LOG`; POST `/ask`
       `{"question": A, "product_id": PRODUCT}` with `curl --max-time 1`; time B at once; then count again.
       A round is valid only if the count grew by one.
    4. **Result.** Print the pilot question and its time, both medians, `gap = median(B after) − median(B alone)`,
       the number of valid rounds, `PASS` if the gap is at most 0.5 s and `GAP` otherwise, and the pressure.
  - `run_fl_probe.sh LABEL`. Exits 2 at pressure `4`. Exits 1 if `:8080` or `:50051` already has a listener.
    Starts `make dev > $T/evidence/dev_$LABEL.log 2>&1` in the background, from the repo root, and waits up to
    120 s for `curl -s localhost:8080/stats` (`go run` compiles first). If that times out, it prints the log's
    last 30 lines and exits 1. Then it runs `GATEWAY_LOG=... bash fl_probe.sh | tee $T/evidence/fl_probe_$LABEL.out`.
    Last, it stops the stack: `kill -TERM` the PID listening on `:8080` (the gateway; `make dev`'s EXIT trap then
    stops rag.server), waits up to 90 s for `make` to exit, and if `:50051` is still held it sends `kill -TERM`
    to that PID. It exits with the probe's status.
  - Run: `bash -n $T/evidence/fl_probe.sh && bash -n $T/evidence/run_fl_probe.sh`
  - Pass: no syntax error.
  - Result: added evidence/fl_probe.sh and evidence/run_fl_probe.sh; `bash -n` on both is clean

- [x] 1.5 **(model)** Run the probe on the unfixed code. `citable: no`.
  - Run: `bash $T/evidence/run_fl_probe.sh before`
  - Pass: at least 4 valid rounds, and the result says `GAP` with a gap over 0.5 s, so the probe can see F-L.
    If it says `PASS`, stop and report: the probe cannot see the bug, and DC 5 would prove nothing.
  - Result: GAP, gap 34.715 s (B alone median 0.114 s, B after a drop 34.829 s), 5 of 5 valid rounds; pilot A took 47.4 s; pressure 2 (yellow) at start, 1 at end, citable: no; evidence/fl_probe_before.out, dev_before.log

## Phase 2 — The fix

- [x] 2.1 Add the grace setting.
  - Files: `rag/src/rag/config.py`
  - What: `SHUTDOWN_GRACE_S = float(os.environ.get("RAG_SHUTDOWN_GRACE_S", "60"))`, with a comment: the time a
    SIGTERM waits for `Answer` calls in flight, 60 s like the gateway's `shutdownGrace`; not a frozen value.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && pytest -q --ignore=tests/test_server_cancel.py`
  - Pass: 83 passed.
  - Result: added SHUTDOWN_GRACE_S (default 60, RAG_SHUTDOWN_GRACE_S) to rag/src/rag/config.py; 83 passed

- [x] 2.2 Make the Ollama call stoppable.
  - Files: `rag/src/rag/generate.py`
  - What, as design.md §3 "Files": `Cancelled`; `_stop` (a `contextvars.ContextVar[threading.Event | None]`,
    default `None`); `stop_when(stop)` (a `contextlib.contextmanager` that sets `_stop` and resets it with its
    token in `finally`); `_STOP_POLL_S = 0.05`; `_request_body(query, chunks)`; `async _post_until_stop(body,
    stop)`, which waits with `asyncio.wait({task}, timeout=_STOP_POLL_S)` in a loop, and on a set `stop` cancels
    the task, awaits it while suppressing `asyncio.CancelledError`, and raises `Cancelled`; `generate(query,
    chunks)`, which keeps its signature, raises `Cancelled` at once if the event is already set, and otherwise
    returns `asyncio.run(...)`. Remove the module-level `_client` and its comment. Write a new comment for the
    per-call `httpx.AsyncClient(timeout=_TIMEOUT)`: cancelling the task closes its connection, and Ollama then
    stops (P2 and U1 in design.md). **Do not touch `_PROMPT_TEMPLATE` or `_build_prompt`, not even their
    formatting.** Add one sentence on F-L to the module docstring.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && pytest -q --ignore=tests/test_server_cancel.py && pytest -q tests/test_server_cancel.py -k "body_is_unchanged or prompt_is_unchanged"`
  - Pass: 83 passed, then 2 passed.
  - Result: generate.py now has Cancelled, stop_when, _request_body, _post_until_stop (AsyncClient per call), same generate() signature; `git diff` shows _PROMPT_TEMPLATE and _build_prompt untouched; 83 passed, then 2 passed

- [x] 2.3 Wire the stop into `Answer`, and add the shutdown.
  - Files: `rag/src/rag/server.py`
  - What, as design.md §3 "Files" and "The shutdown path":
    - `_stop_on_rpc_end(context) -> threading.Event`.
    - `Answer`: the event first; then `epoch.read()` as today (the order rule: the epoch is still read before any
      chunk text); then `with generate.stop_when(stop): text = generate.generate(request.query, chunks)`. On
      `generate.Cancelled`, `print(..., flush=True)` one line, `rag.server: Answer stopped after X.XX s: the RPC
      ended, the Ollama request was closed`, and `return` with no chunk.
    - `_install_shutdown(server, grace)`. The handler prints `rag.server: <SIGNAME>: refusing new RPCs, waiting
      up to <grace> s for the ones in flight`, resets every handled signal to `SIG_DFL`, then calls
      `server.stop(grace)`. It handles SIGTERM always, and SIGINT only when `signal.getsignal(SIGINT)` is not
      `SIG_IGN`.
    - `serve()`: `_install_shutdown(server, config.SHUTDOWN_GRACE_S)` right **after** `server.start()`; after
      `wait_for_termination()`, print `rag.server: stopped`. Every print in `serve()` gets `flush=True`.
    - Comments say why: `add_callback` fires on every RPC end (P1, P4); `make dev` starts the server with SIGINT
      ignored and stops it with SIGTERM; the handlers go in after `start()`; a second signal takes the default
      action.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && pytest -q`
  - Pass: 89 passed (83, plus the 6 of `test_server_cancel.py`).
  - Result: server.py has _stop_on_rpc_end, the stop_when wiring in Answer, _install_shutdown and the serve() changes; 89 passed (the cancel test now passes, 3 runs in a row also 6 passed)

- [x] 2.4 Lint.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; make lint`
  - Pass: no error.
  - Result: `make lint` exits 0 (gofmt, go vet, ruff check all clean; ruff ran, not SKIPPED); I wrapped two over-long lines in server.py first

## Phase 3 — The shutdown tests

- [x] 3.1 Write the subprocess entry point.
  - Files: `rag/tests/serve_with_fakes.py` (new; a script, not collected, because its name does not start with
    `test_`)
  - What: patch `retrieve.fetch_by_ids` and `retrieve.retrieve` to return the `_CHUNK` of 1.1 with epoch `41`,
    then call the real `server.serve()`. Everything else comes from the environment: `RAG_GRPC_ADDR`,
    `OLLAMA_BASE_URL`, `DATASET_EPOCH_FILE`, `RAG_SHUTDOWN_GRACE_S`. A docstring says why: the real `serve()`
    runs, with no Redis.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && pytest -q`
  - Pass: 89 passed (nothing new collected).
  - Result: added rag/tests/serve_with_fakes.py (patches both retrieval functions, then runs the real server.serve()); 89 passed

- [x] 3.2 Write the shutdown tests.
  - Files: `rag/tests/test_server_shutdown.py` (new)
  - Helper: start `[sys.executable, <dir of this file>/serve_with_fakes.py]` with the four variables, on a free
    port (bind a socket to `127.0.0.1:0`, read the port, close it), and wait up to 10 s until the port accepts. At
    teardown, `kill()` any process still alive.
  - Tests, with these exact names:
    - `test_signal_finishes_the_answer_in_flight`, parametrised over SIGTERM and SIGINT (DC 3a–c). Fake
      `delay=1.5`, grace `10`. Start an `Answer` in a thread, wait for the fake's body, then send the signal.
      (b) An `Answer` on a **new** channel, with `timeout=2`, fails with `UNAVAILABLE`. (a) The first `Answer`
      returns one chunk with the full text. (c) `proc.wait(timeout=10) == 0`, and the time from signal to exit
      is under 10 s.
    - `test_sigint_ignored_at_start_stays_ignored` (DC 3d). Start the process with
      `preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)`, fake `delay=0`. Send SIGINT and wait
      1 s: `proc.poll() is None`, and a new `Answer` still returns the full text. Then SIGTERM:
      `proc.wait(timeout=5) == 0`.
    - `test_grace_end_stops_a_stuck_generation` (DC 4). Fake `delay=None`, grace `2`. Start an `Answer`, wait for
      the body, send SIGTERM at `t0`. `fake.closed_at` is set by `t0 + 3`, and the process has exited by
      `t0 + 4` (grace + 2).
    - `test_second_signal_exits_at_once` (DC 4). Fake `delay=None`, grace `60`. An `Answer` in flight, SIGTERM,
      then a second SIGTERM 0.5 s later. The process exits within 2 s of the second signal, with
      `returncode == -signal.SIGTERM`.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && pytest -v tests/test_server_shutdown.py`
  - Pass: 5 passed (two parameters plus three tests). Then `cd rag && pytest -q` gives 94 passed.
  - Result: added rag/tests/test_server_shutdown.py; 5 passed (11.7 s), the full suite 94 passed, and two more runs of both new files passed 11 of 11

## Phase 4 — Measure and document

- [x] 4.1 Measure the per-call cost (U2). `citable: no`, no model.
  - Files: `$T/evidence/bench_generate_overhead.py` (new)
  - What: it imports `FakeOllama` from `rag/tests/conftest.py` (add that directory to `sys.path`) and starts one
    with `delay=0`. It times 100 calls of the **old** path (a copy of the old `generate()`: one module-level
    `httpx.Client(timeout=120.0)` posting `_request_body(...)`) and 100 calls of the new `generate.generate()`,
    and prints both medians and their difference in ms. The fake closes every connection, so the old path also
    pays a new connection each call; the script prints that caveat.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && python3 ../$T/evidence/bench_generate_overhead.py | tee ../$T/evidence/bench_generate_overhead.out`
  - Pass: both medians and the difference are printed. Not gated: write the difference in Result.
  - Result: new path +15.9 ms per call (medians: old 0.547 ms, new 16.432 ms, 100 calls each, instant fake, citable: no); more than the "few ms" reasoned in design.md, still small beside seconds of generation; evidence/bench_generate_overhead.out

- [-] 4.2 **(model)** Run the probe on the fixed code. `citable: no`. Replaced by Phase 6; this run is the
  evidence for DC 5(b).
  - Run: `bash $T/evidence/run_fl_probe.sh after`
  - Pass: at least 4 valid rounds, and the result says `PASS` (gap at most 0.5 s). `dev_after.log` has one
    `rag.server: Answer stopped` line per valid round.
  - Result: FAILED, not ticked: GAP 1.258 s (B alone 0.115 s, B after a drop 1.373 s), 5 of 5 valid rounds,
    5 `Answer stopped` lines; pressure 1 at start and end, citable: no. Cause: Ollama frees the slot only
    after the prompt's prefill (design.md §4).

- [-] 4.3 Restate §H and bump the contract to v0.31. Replaced by 6.3, not run: its text said the orphan was
  fully gone, and it put the new row below v0.30 in a table that is newest first.
  - Files: `docs/contracts/interfaces.md`
  - What: five exact replacements. Each old text occurs once; copy the new text exactly, one line each.
    1. Line 775, old:
       ```
       because `rag.server` may keep generating after its RPC is cancelled (F-L, a `super-plan.md` finding)
       ```
       new:
       ```
       because the gateway stops waiting first. Since v0.31 `rag.server` closes its Ollama request within about 50 ms of the cancel, so the value is close to the work done. In a log from before v0.31, `rag.server` kept generating after the cancel (F-L), and the value is a lower bound only
       ```
    2. Line 775, old:
       ```
       While F-L is open that is necessary but not sufficient (a MISS that follows an orphaned generation absorbs the remainder)
       ```
       new:
       ```
       In a log from before v0.31 (F-L open), that is necessary but not sufficient: a MISS that followed an orphaned generation absorbed the remainder
       ```
    3. Line 3: `Draft v0.30` becomes `Draft v0.31`, and `**Revised:** 2026-11-08` becomes `**Revised:** 2026-11-10`.
    4. Line 954: `**Current version: v0.30** (2026-11-08).` becomes `**Current version: v0.31** (2026-11-10).`
    5. The versioning table gets a new row right after the `v0.30` row:
       ```
       | **v0.31** | 2026-11-10 | **F-L is closed** (doc-only; trail `docs/work/2026-11-10-fl-cancel-and-rag-shutdown/`). `rag.server` closes its Ollama request when its `Answer` RPC ends, so a cancelled generation no longer runs on. §H's `t_generate_ms` note is restated. No wire shape, `.proto`, §A–§G, §I or Redis change; `source_chunk_ids`, `t1_key` and `dataset_epoch` are untouched. A MISS that follows an ABANDONED request no longer absorbs the rest of the orphan, so such latencies are not comparable across this commit; the one recorded run has no ABANDONED record. No citable run exists, so none is invalidated |
       ```
  - Run: `grep -n "v0.31" docs/contracts/interfaces.md; grep -c "While F-L is open" docs/contracts/interfaces.md`
  - Pass: `v0.31` on line 3, the current-version line and the new row; the count is `0`.
  - Result:

- [-] 4.4 Mark F-L closed in the super-plan. Replaced by 6.4, not run: its text did not name the residual.
  - Files: `docs/super-plan.md`
  - What: two exact replacements; keep the rest of each line.
    1. Old (the opening of the F-L bullet):
       ```
       - **F-L (new, found by F-A's impact analysis):
       ```
       new:
       ```
       - ✅ **F-L, closed 2026-11-10** (trail `docs/work/2026-11-10-fl-cancel-and-rag-shutdown/`; DC 5's probe is in its `evidence/`). Found by F-A's impact analysis: **
       ```
       The new text ends with `**` on purpose: the bold that the old opening started is closed later, after
       `cancelled.`, so the new text must open it again.
    2. Old:
       ```
       (the author's decision) and **still gates
       ```
       and the `Phase 7** (7.1, 7.5).` that follows it on the next line; new, in their place:
       ```
       (the author's decision); it was closed on 2026-11-10, before Phase 7.
       ```
  - Run: `grep -n "F-L" docs/super-plan.md`
  - Pass: the ✅ line shows, and `still gates Phase 7` no longer appears next to F-L.
  - Result:

## Phase 5 — Run and verify, every done condition (numbered as design.md §1)

Replaced by Phase 7, not run: DC 5 and DC 6 changed (design.md §4, 2026-11-10).

- [-] 5.1 `make verify`
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; make verify 2>&1 | tail -40`
  - Pass: no FAIL. The Python suites ran (no `pytest SKIPPED`). Any SKIPPED target is listed by name.
  - Result:
- [-] 5.2 DC 1 — the cancel.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && pytest -v tests/test_server_cancel.py -k "cancel_closes or no_chunk or before_generation or another_request"`; then `grep -n "F-L: the Ollama request was not closed" ../$T/evidence/dc1_before.out`
  - Pass: 4 passed; the grep finds the failure saved before the fix.
  - Result:
- [-] 5.3 DC 2 — same request, same answer.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && pytest -v tests/test_server_cancel.py -k "body_is_unchanged or prompt_is_unchanged"`
  - Pass: 2 passed, and the two constants in the test equal the two lines of `golden_before.out`.
  - Result:
- [-] 5.4 DC 3 — graceful shutdown.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && pytest -v tests/test_server_shutdown.py -k "finishes_the_answer or sigint_ignored"`
  - Pass: 3 passed.
  - Result:
- [-] 5.5 DC 4 — a stuck generation, and a second signal.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && pytest -v tests/test_server_shutdown.py -k "grace_end or second_signal"`
  - Pass: 2 passed.
  - Result:
- [-] 5.6 DC 5 — the live probe, before and after. `citable: no`.
  - Run: `tail -8 $T/evidence/fl_probe_before.out; tail -8 $T/evidence/fl_probe_after.out`
  - Pass: before says `GAP` (gap over 0.5 s) and after says `PASS` (gap at most 0.5 s), each with at least 4 valid
    rounds and its pressure level shown.
  - Result:
- [-] 5.7 DC 6 — the docs.
  - Run: the two commands of 4.3 and the one of 4.4.
  - Pass: as in 4.3 and 4.4.
  - Result:
- [-] 5.8 DC 7 — `make verify`, and no existing test edited.
  - Run: `git status --porcelain rag/tests`
  - Pass: 5.1 passed, and every line here starts with `??` (new files only); no line shows ` M`.
  - Result:

## Phase 6 — Fix for step 4.2: DC 5 in two parts (design.md §4, approved by the author 2026-11-10)

No code changes. The fix works; Ollama frees its slot only after the prompt's prefill, so DC 5 now checks a
drop after the prefill (a) and bounds the 1 s drop by one prefill (b).

- [x] 6.1 Let the probe drop the client at any time.
  - Files: `$T/evidence/fl_probe.sh`
  - What: add `DROP_S=${DROP_S:-1}` beside `ROUNDS`. In step 3, `curl ... --max-time "$DROP_S"` instead of
    `--max-time 1`. Print `drop at: $DROP_S s` as the second line of the output, right after `pressure at
    start`. In the header comment and the step-3 comment, write `DROP_S` (default 1) where they say 1 s, and
    list `DROP_S` with the optional variables. Nothing else changes; the last seven lines keep their form.
    `run_fl_probe.sh` does not change: `fl_probe.sh` inherits `DROP_S` from its environment.
  - Run: `T=docs/work/2026-11-10-fl-cancel-and-rag-shutdown; bash -n $T/evidence/fl_probe.sh && grep -n 'DROP_S' $T/evidence/fl_probe.sh; grep -c -- '--max-time 1' $T/evidence/fl_probe.sh`
  - Pass: no syntax error; `DROP_S` shows in its default, the `curl` and the `drop at` print; the count is `0`.
  - Result: fl_probe.sh now has `DROP_S=${DROP_S:-1}`, `--max-time "$DROP_S"` and a `drop at:` line after the pressure line; `bash -n` clean, count of `--max-time 1` is 0

- [x] 6.2 **(model)** Run the probe on the fixed code, with the drop at 4 s, after A's prefill. `citable: no`.
  - Run: `T=docs/work/2026-11-10-fl-cancel-and-rag-shutdown; DROP_S=4 bash $T/evidence/run_fl_probe.sh after-drop4`
  - Pass: `$T/evidence/fl_probe_after-drop4.out` says `drop at: 4 s`, has at least 4 valid rounds, and says
    `RESULT: PASS` (gap at most 0.5 s). `$T/evidence/dev_after-drop4.log` has one `rag.server: Answer stopped`
    line per valid round, each after at least 3.5 s, so the cut came after the prefill (about 2 s). Any other
    result: stop and report.
  - Result: PASS, gap 0.040 s (B alone median 0.115 s, B after a drop 0.155 s), 5 of 5 valid rounds, 5 `Answer stopped` lines at 3.82-4.00 s; pressure 1 before, at start and 2 at end, citable: no; evidence/fl_probe_after-drop4.out, dev_after-drop4.log

- [x] 6.3 Restate §H and bump the contract to v0.31.
  - Files: `docs/contracts/interfaces.md`
  - What: five exact replacements. Each old text occurs once (checked 2026-11-10); copy the new text exactly,
    each on one line.
    1. Line 775, old:
       ```
       because `rag.server` may keep generating after its RPC is cancelled (F-L, a `super-plan.md` finding)
       ```
       new:
       ```
       because the gateway stops waiting first. Since v0.31 `rag.server` closes its Ollama request within about 50 ms of the cancel, but Ollama frees its one slot only after it has read the whole prompt, so after a cancel during the prefill the slot stays busy for the rest of that prefill (a whole prefill took 1.94 s for a 987-token prompt; trail `docs/work/2026-11-10-fl-cancel-and-rag-shutdown/`, design.md §4). In a log from before v0.31, `rag.server` kept generating after the cancel (F-L), and the value can be far below the slot's real hold
       ```
    2. Line 775, old:
       ```
       While F-L is open that is necessary but not sufficient (a MISS that follows an orphaned generation absorbs the remainder)
       ```
       new:
       ```
       That is necessary but not sufficient: a MISS that follows an ABANDONED request can absorb the rest of the orphan's prefill (since v0.31), or the rest of the whole orphaned generation (in a log from before v0.31, F-L open)
       ```
    3. Line 3: `Draft v0.30` becomes `Draft v0.31`, and `**Revised:** 2026-11-08` becomes `**Revised:** 2026-11-10`.
    4. Line 954: `**Current version: v0.30** (2026-11-08).` becomes `**Current version: v0.31** (2026-11-10).`
    5. A new row right **above** the `v0.30` row (the table is newest first):
       ```
       | **v0.31** | 2026-11-10 | **F-L is closed, with a residual** (doc-only; trail `docs/work/2026-11-10-fl-cancel-and-rag-shutdown/`). `rag.server` closes its Ollama request when its `Answer` RPC ends, so a cancelled generation no longer runs on. Ollama frees its one slot only after it has read the whole prompt, so a cancel during the prefill still holds the slot for the rest of that prefill (a whole prefill took 1.94 s for a 987-token prompt, `citable: no`), out of the gateway's sight. §H's `t_generate_ms` note is restated. No wire shape, `.proto`, §A–§G, §I or Redis change; `source_chunk_ids`, `t1_key` and `dataset_epoch` are untouched. A MISS that follows an ABANDONED request now absorbs at most the rest of one prefill, not the rest of the orphan, so such latencies are not comparable across this commit; the one recorded run has no ABANDONED record. No citable run exists, so none is invalidated |
       ```
  - Run: `grep -n "v0.31" docs/contracts/interfaces.md | cut -c1-80; grep -c "While F-L is open" docs/contracts/interfaces.md; grep -c "the rest of the orphan's prefill" docs/contracts/interfaces.md; grep -n '^| \*\*v0.3[01]\*\*' docs/contracts/interfaces.md | cut -c1-30`
  - Pass: `v0.31` on line 3, line 775 (§H), the current-version line and the new row; the two counts are `0`
    and `1`; the v0.31 row's line number is one less than the v0.30 row's.
  - Result: five replacements applied in interfaces.md; `v0.31` on lines 3, 775, 954, 960; counts 0 and 1; the v0.31 row is line 960, the v0.30 row line 961

- [x] 6.4 Mark F-L closed, with its residual, in the super-plan.
  - Files: `docs/super-plan.md`
  - What: two exact replacements. Keep the rest of each line. Rewrapping the changed lines to about 105
    columns is allowed; no other text changes.
    1. Old (the opening of the F-L bullet):
       ```
       - **F-L (new, found by F-A's impact analysis):
       ```
       new:
       ```
       - ✅ **F-L, closed 2026-11-10, with a residual** (trail `docs/work/2026-11-10-fl-cancel-and-rag-shutdown/`; DC 5's probes are in its `evidence/`). `rag.server` now closes its Ollama request when the RPC ends, but Ollama frees its one slot only after it has read the whole prompt, so an abandoned request can still hold the slot for up to one prefill (1.94 s for a 987-token prompt; design.md §4), out of the gateway's sight. Found by F-A's impact analysis: **
       ```
       The new text ends with `**` on purpose: the bold that the old opening started is closed later, after
       `cancelled.`, so the new text must open it again.
    2. Old:
       ```
       (the author's decision) and **still gates
       ```
       and the `Phase 7** (7.1, 7.5).` that follows it on the next line; new, in their place:
       ```
       (the author's decision); it was closed on 2026-11-10, before Phase 7, with the prefill residual above.
       ```
  - Run: `grep -n "F-L" docs/super-plan.md | cut -c1-90; grep -c "still gates" docs/super-plan.md`
  - Pass: the ✅ line with `with a residual` shows; the count is `0`.
  - Result: two replacements applied in super-plan.md (F-L bullet at line 182 now opens with the ✅ text, rewrapped to ~105 columns; "still gates" is gone); the ✅ line shows, count 0

## Phase 7 — Run and verify, every done condition (numbered as design.md §1)

- [x] 7.1 `make verify`
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; make verify 2>&1 | tail -40`
  - Pass: no FAIL. The Python suites ran (no `pytest SKIPPED`). Any SKIPPED target is listed by name.
  - Result: exit 0; ruff clean, go vet/build clean, Go tests ok (cached), rag 94 passed, experiments 1117 passed, no FAIL, no SKIPPED; full output in evidence/verify_phase7.out
- [x] 7.2 DC 1 — the cancel.
  - Run: `T=docs/work/2026-11-10-fl-cancel-and-rag-shutdown; export PATH="$HOME/Library/Python/3.13/bin:$PATH"; (cd rag && pytest -v tests/test_server_cancel.py -k "cancel_closes or no_chunk or before_generation or another_request"); grep -n "F-L: the Ollama request was not closed" $T/evidence/dc1_before.out`
  - Pass: 4 passed; the grep finds the failure saved before the fix.
  - Result: 4 passed in 3.76 s; the grep finds the F-L message at lines 33 and 35 of evidence/dc1_before.out
- [x] 7.3 DC 2 — same request, same answer.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && pytest -v tests/test_server_cancel.py -k "body_is_unchanged or prompt_is_unchanged"`
  - Pass: 2 passed, and the two constants in the test equal the two lines of `golden_before.out`.
  - Result: 2 passed in 0.97 s; `_TEMPLATE_SHA256` and `_PROMPT_SHA256` (test lines 40-41) equal lines 1 and 2 of golden_before.out
- [x] 7.4 DC 3 — graceful shutdown.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && pytest -v tests/test_server_shutdown.py -k "finishes_the_answer or sigint_ignored"`
  - Pass: 3 passed.
  - Result: 3 passed in 7.84 s (SIGTERM, SIGINT, SIGINT-ignored-at-start)
- [x] 7.5 DC 4 — a stuck generation, and a second signal.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd rag && pytest -v tests/test_server_shutdown.py -k "grace_end or second_signal"`
  - Pass: 2 passed.
  - Result: 2 passed in 4.30 s
- [x] 7.6 DC 5 — the live probe: before, and after at 1 s and at 4 s. `citable: no`.
  - Run: `T=docs/work/2026-11-10-fl-cancel-and-rag-shutdown; tail -8 $T/evidence/fl_probe_before.out; tail -8 $T/evidence/fl_probe_after.out; head -2 $T/evidence/fl_probe_after-drop4.out; tail -8 $T/evidence/fl_probe_after-drop4.out`
  - Pass, each with at least 4 valid rounds and its pressure shown: before says `GAP` with a gap over 0.5 s;
    (b) `fl_probe_after.out` (drop at 1 s; run before 6.1, so it has no `drop at` line) has a gap of at most
    1.94 s; (a) `fl_probe_after-drop4.out` says `drop at: 4 s` and `PASS`, a gap of at most 0.5 s.
  - Result: before: GAP 34.715 s, 5 of 5 valid, pressure 2 at start and 1 at end; (b) after, drop 1 s: gap 1.258 s (at most 1.94), 5 of 5 valid, pressure 1 and 1; (a) after-drop4: `drop at: 4 s`, PASS, gap 0.040 s, 5 of 5 valid, pressure 1 and 2; all citable: no
- [x] 7.7 DC 6 — the docs.
  - Run: the Run commands of 6.3 and 6.4.
  - Pass: as in 6.3 and 6.4.
  - Result: re-run clean: `v0.31` on interfaces.md lines 3, 775, 954, 960 (row 960, v0.30 row 961); counts 0 and 1; super-plan F-L line 182 shows `with a residual`, "still gates" count 0
- [x] 7.8 DC 7 — `make verify`, and no existing test edited.
  - Run: `git status --porcelain rag/tests`
  - Pass: 7.1 passed, and every line here starts with `??` (new files only); no line shows ` M`.
  - Result: 7.1 passed; 4 lines, all `??` (conftest.py, serve_with_fakes.py, test_server_cancel.py, test_server_shutdown.py); no ` M`
