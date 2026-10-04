"""Tests for the envelope check (ADR-003, `docs/work/2026-10-04-resolve-f1/design.md` §4).

The check decides whether a measurement may run, so its expensive failure is a false OK: an
envelope reported as frozen while the live runner serves something else. That is exactly how
finding F1 stayed invisible for seven weeks — `OLLAMA_NUM_PARALLEL=4` was requested and checked,
while the runner served one slot. Every test here pins a path by which the check could pass for the
wrong reason, or fail open.

No Ollama and no `rag` are needed. The decision functions are pure, and the I/O wiring (`observe`,
`main`) runs against faked HTTP, `ps` and `lsof` plus a stand-in `rag.config`. Fixtures are cut from
what the live machine printed on 2026-10-04 (`docs/work/2026-10-04-resolve-f1/evidence/`), with the home
directory replaced.
"""

import sys
import types

import env_check
import pytest
from env_check import (
    AmbiguousRunner,
    EnvelopeError,
    Frozen,
    NoRunner,
    Observed,
    Props,
    RunnerArgs,
    Unparseable,
    blob_from_show,
    check,
    envelope_line,
    find_llm_runner,
    parse_props,
    parse_runner_args,
)

LLM_BLOB = "sha256-7a3a8d55382135a773916fd7c35044b2a2a3a7b8dee788095d70f122e6d8f520"
EMBED_BLOB = "sha256-970aa74c0a90ef7482477cf803618e776e173c007bf957f635f1015bfcfef0e6"
SERVER = 19379
BLOBS = "/Users/u/.ollama/models/blobs"
RUNNER = "/Applications/Ollama.app/Contents/Resources/llama-server"

# Verbatim shape of `ps -axww -o pid=,ppid=,command=` on 2026-10-04 (home directory replaced).
CAPTURED_LLM_ROW = (
    f"34349 {SERVER} {RUNNER} --model {BLOBS}/{LLM_BLOB} --port 62152 --host 127.0.0.1 --no-webui "
    "--offline -c 8192 -np 1 --log-verbosity 4 --no-log-prefix --no-log-timestamps --no-jinja "
    f"--chat-template chatml --mmproj {BLOBS}/{LLM_BLOB} --flash-attn auto -b 512 -ub 512 "
    "--context-shift --keep 4"
)
CAPTURED_EMBED_ROW = (
    f"34377 {SERVER} {RUNNER} --model {BLOBS}/{EMBED_BLOB} --port 62172 --host 127.0.0.1 --no-webui "
    "--offline -c 2048 -np 1 --log-verbosity 4 --no-log-prefix --no-log-timestamps --flash-attn auto "
    "--embedding -b 2048 -ub 2048 --context-shift --keep 4"
)
SERVER_ROW = f"{SERVER} 1 ollama serve"

FROZEN = Frozen(np=1, num_ctx=8192, version="0.33.2", blob=LLM_BLOB)


def llm_row(pid=34349, ppid=SERVER, c=8192, np=1, blob=LLM_BLOB, port=62152):
    return (
        f"{pid} {ppid} {RUNNER} --model {BLOBS}/{blob} --port {port} --host 127.0.0.1 --no-webui "
        f"--offline -c {c} -np {np} --chat-template chatml --mmproj {BLOBS}/{blob} --keep 4"
    )


def observed(np=1, c=8192, total_slots=1, n_ctx=8192, version="0.33.2", show_blob=LLM_BLOB,
             props_blob=LLM_BLOB):
    return Observed(
        version=version,
        server_pid=SERVER,
        runner_pid=34349,
        show_blob=show_blob,
        args=RunnerArgs(np=np, ctx=c, port=62152, model=show_blob),
        props=Props(total_slots=total_slots, n_ctx=n_ctx, model=props_blob),
    )


# =================================================================================================
# The decision
# =================================================================================================
def test_matching_envelope_passes():
    assert check(FROZEN, observed()) == []


def test_four_slots_against_a_frozen_one_fails_and_names_both():
    failures = check(FROZEN, observed(np=4, c=32768, total_slots=4))
    assert any("-np 4 ≠ frozen slot count 1" in f for f in failures)


def test_runner_that_overrode_its_arguments_fails():
    # argv says one slot, the runner reports four: llama-server's own `n_parallel = auto` rule or a
    # LLAMA_ARG_N_PARALLEL in its inherited environment. argv alone would pass this (review.md S2).
    failures = check(FROZEN, observed(np=1, total_slots=4))
    assert any("overrode" in f for f in failures)


def test_model_swapped_under_the_same_tag_fails():
    # `ollama pull` after an upstream change: the tag now resolves to other weights (review.md S7).
    other = "sha256-" + "0" * 64
    failures = check(FROZEN, observed(show_blob=other, props_blob=other))
    assert any("blob" in f for f in failures)


def test_ollama_version_drift_fails():
    # Auto-update moved 0.32.13 -> 0.33.2 unattended on 2026-09-01 (review.md S3).
    failures = check(FROZEN, observed(version="0.34.0"))
    assert any("0.34.0" in f and "0.33.2" in f for f in failures)


def test_context_check_is_real():
    frozen_4096 = Frozen(np=1, num_ctx=4096, version="0.33.2", blob=LLM_BLOB)
    assert check(frozen_4096, observed(c=8192, n_ctx=8192))


def test_argv_context_mismatch_alone_fails():
    # Isolates the argv condition: the runner reports the frozen per-slot context, but was launched
    # with another -c. Deleting that condition must turn this red.
    failures = check(FROZEN, observed(c=4096))
    assert failures == ["runner -c 4096 ≠ num_ctx × slots = 8192 × 1"]


def test_per_slot_context_mismatch_alone_fails():
    # Isolates the /props condition: argv says -c 8192, the runner reports another per-slot context.
    failures = check(FROZEN, observed(n_ctx=4096))
    assert failures == ["runner per-slot n_ctx 4096 ≠ frozen num_ctx 8192"]


def test_props_reporting_other_weights_than_argv_fails():
    other = "sha256-" + "1" * 64
    assert check(FROZEN, observed(props_blob=other))


# =================================================================================================
# Finding the runner — the silent-pass paths
# =================================================================================================
def test_finds_the_llm_runner_among_both():
    pid, cmd = find_llm_runner([SERVER_ROW, CAPTURED_EMBED_ROW, CAPTURED_LLM_ROW], LLM_BLOB, SERVER)
    assert pid == 34349
    assert LLM_BLOB in cmd


def test_embedding_runner_alone_is_no_runner_not_a_pass():
    # nomic-bert also runs at -np 1. Reading it would report the right slot count for the wrong
    # model — the one silent pass the frozen value 1 makes possible.
    with pytest.raises(NoRunner):
        find_llm_runner([SERVER_ROW, CAPTURED_EMBED_ROW], LLM_BLOB, SERVER)


def test_no_runner_loaded_is_no_runner():
    with pytest.raises(NoRunner):
        find_llm_runner([SERVER_ROW], LLM_BLOB, SERVER)


def test_two_llm_runners_are_ambiguous():
    rows = [llm_row(pid=1001), llm_row(pid=1002)]
    with pytest.raises(AmbiguousRunner):
        find_llm_runner(rows, LLM_BLOB, SERVER)


def test_runner_under_a_foreign_server_is_no_runner():
    # Two servers share ~/.ollama/models, so blob paths are identical. Only the parent PID ties a
    # runner to the server the RAG service calls (review.md S4).
    with pytest.raises(NoRunner, match="another server"):
        find_llm_runner([llm_row(ppid=55555)], LLM_BLOB, SERVER)


def test_mmproj_carrying_the_same_blob_is_one_match():
    pid, _ = find_llm_runner([CAPTURED_LLM_ROW], LLM_BLOB, SERVER)
    assert pid == 34349


def test_non_runner_process_mentioning_the_blob_is_ignored():
    row = f"777 {SERVER} /bin/cat {BLOBS}/{LLM_BLOB}"
    with pytest.raises(NoRunner):
        find_llm_runner([row], LLM_BLOB, SERVER)


# =================================================================================================
# Parsing — never default, never guess
# =================================================================================================
def test_captured_row_parses():
    cmd = CAPTURED_LLM_ROW.split(None, 2)[2]
    assert parse_runner_args(cmd) == RunnerArgs(np=1, ctx=8192, port=62152, model=LLM_BLOB)


def test_long_aliases_parse():
    cmd = f"{RUNNER} --model {BLOBS}/{LLM_BLOB} --port 1 --ctx-size 8192 --parallel 1"
    assert parse_runner_args(cmd) == RunnerArgs(np=1, ctx=8192, port=1, model=LLM_BLOB)


@pytest.mark.parametrize(
    "cmd",
    [
        f"{RUNNER} --model {BLOBS}/{LLM_BLOB} --port 1 -c 8192",  # -np absent
        f"{RUNNER} --model {BLOBS}/{LLM_BLOB} --port 1 -c 8192 -np x",  # -np not an integer
        f"{RUNNER} --model {BLOBS}/{LLM_BLOB} --port 1 -c 8192 -np 1 --parallel 1",  # repeated
        f"{RUNNER} --model {BLOBS}/{LLM_BLOB} --port 1 -np 1",  # -c absent
        f"{RUNNER} --model {BLOBS}/{LLM_BLOB} -c 8192 -np 1",  # --port absent
        f"{RUNNER} --model /tmp/model.gguf --port 1 -c 8192 -np 1",  # no blob token
        f"{RUNNER} --port 1 -c 8192 -np",  # flag with no value
    ],
)
def test_unparseable_runner_args_raise(cmd):
    with pytest.raises(Unparseable):
        parse_runner_args(cmd)


def test_blob_from_show():
    show = {"modelfile": f"# Modelfile\nFROM {BLOBS}/{LLM_BLOB}\nPARAMETER temperature 1\n"}
    assert blob_from_show(show) == LLM_BLOB


@pytest.mark.parametrize(
    "show",
    [
        {},
        {"modelfile": "PARAMETER temperature 1\n"},
        {"modelfile": "FROM qwen3.5:2b\n"},
        {"modelfile": f"FROM {BLOBS}/{LLM_BLOB}\nFROM {BLOBS}/{EMBED_BLOB}\n"},
    ],
)
def test_blob_from_show_refuses_what_it_cannot_pin(show):
    with pytest.raises(Unparseable):
        blob_from_show(show)


def test_parse_props():
    # Field paths as the 0.33.2 runner served them (evidence/runner-props-2026-10-04.json).
    props = {
        "total_slots": 1,
        "default_generation_settings": {"n_ctx": 8192},
        "model_path": f"{BLOBS}/{LLM_BLOB}",
    }
    assert parse_props(props) == Props(total_slots=1, n_ctx=8192, model=LLM_BLOB)


@pytest.mark.parametrize(
    "props",
    [
        {"default_generation_settings": {"n_ctx": 8192}, "model_path": f"{BLOBS}/{LLM_BLOB}"},
        {"total_slots": 1, "model_path": f"{BLOBS}/{LLM_BLOB}"},
        {"total_slots": 1, "default_generation_settings": {"n_ctx": 8192}},
        {"total_slots": "1", "default_generation_settings": {"n_ctx": 8192}, "model_path": LLM_BLOB},
    ],
)
def test_parse_props_refuses_missing_fields(props):
    with pytest.raises(Unparseable):
        parse_props(props)


# =================================================================================================
# The record a run can be checked against at its end
# =================================================================================================
def test_envelope_line_is_stable():
    assert envelope_line(observed()) == (
        f"ENVELOPE server_pid={SERVER} runner_pid=34349 version=0.33.2 np=1 ctx=8192 "
        f"total_slots=1 n_ctx_slot=8192 blob={LLM_BLOB}"
    )


# =================================================================================================
# The I/O wiring — faked, so a later edit cannot silently disconnect the checks from the machine
# =================================================================================================
def _fake_rag(monkeypatch, base="http://localhost:11434"):
    config = types.SimpleNamespace(
        OLLAMA_BASE_URL=base,
        LLM_MODEL="qwen3.5:2b-q4_K_M",
        LLM_NUM_CTX=8192,
        EMBEDDING_MODEL="nomic-embed-text",
    )
    rag = types.ModuleType("rag")
    rag.config = config
    monkeypatch.setitem(sys.modules, "rag", rag)
    monkeypatch.setitem(sys.modules, "rag.config", config)


def _fake_machine(monkeypatch, total_slots=1):
    urls = []

    def http_json(url, body=None, timeout=10.0):
        urls.append(url)
        if url.endswith("/api/version"):
            return {"version": "0.33.2"}
        if url.endswith("/api/generate"):
            assert body == {"model": "qwen3.5:2b-q4_K_M", "options": {"num_ctx": 8192}}
            return {"done": True, "done_reason": "load"}
        if url.endswith("/api/embed"):
            return {"embeddings": [[0.0]]}
        if url.endswith("/api/show"):
            return {"modelfile": f"FROM {BLOBS}/{LLM_BLOB}\n"}
        if url == "http://127.0.0.1:62152/props":
            return {
                "total_slots": total_slots,
                "default_generation_settings": {"n_ctx": 8192},
                "model_path": f"{BLOBS}/{LLM_BLOB}",
            }
        raise AssertionError(f"unexpected request to {url}")

    rows = f"{SERVER_ROW}\n{CAPTURED_EMBED_ROW}\n{CAPTURED_LLM_ROW}\n"
    monkeypatch.setattr(env_check, "_http_json", http_json)
    monkeypatch.setattr(env_check, "_run", lambda cmd: rows)
    monkeypatch.setattr(env_check, "_listener_pid", lambda port: SERVER)
    return urls


def test_observe_reads_the_runner_it_matched(monkeypatch):
    _fake_rag(monkeypatch)
    urls = _fake_machine(monkeypatch)
    obs = env_check.observe(FROZEN)
    assert obs.runner_pid == 34349  # the LLM runner, not the embedding runner beside it
    assert "http://127.0.0.1:62152/props" in urls  # /props from THAT runner's own port
    assert check(FROZEN, obs) == []


def test_observe_carries_a_runner_override_through_to_the_check(monkeypatch):
    _fake_rag(monkeypatch)
    _fake_machine(monkeypatch, total_slots=4)
    failures = check(FROZEN, env_check.observe(FROZEN))
    assert any("overrode" in f for f in failures)


def test_observe_refuses_a_server_it_cannot_inspect(monkeypatch):
    _fake_rag(monkeypatch, base="http://10.0.0.5:11434")
    _fake_machine(monkeypatch)
    with pytest.raises(EnvelopeError, match="not local"):
        env_check.observe(FROZEN)


@pytest.mark.parametrize("lsof_out", ["", "111\n222\n"])
def test_listener_pid_refuses_none_or_several(monkeypatch, lsof_out):
    monkeypatch.setattr(env_check, "_run", lambda cmd: lsof_out)
    with pytest.raises(EnvelopeError):
        env_check._listener_pid(11434)


def _run_main(monkeypatch, blob=LLM_BLOB):
    argv = ["env_check.py", "--frozen-np", "1", "--ollama-version", "0.33.2", "--llm-blob", blob]
    monkeypatch.setattr(sys, "argv", argv)
    return env_check.main()


def test_main_exits_1_when_the_envelope_cannot_be_established(monkeypatch, capsys):
    _fake_rag(monkeypatch)

    def unreachable(frozen):
        raise EnvelopeError("ollama unreachable")

    monkeypatch.setattr(env_check, "observe", unreachable)
    assert _run_main(monkeypatch) == 1
    assert "FAIL — envelope not verifiable" in capsys.readouterr().out


def test_main_exits_1_on_a_malformed_pinned_blob(monkeypatch):
    _fake_rag(monkeypatch)
    monkeypatch.setattr(env_check, "observe", lambda frozen: observed())
    assert _run_main(monkeypatch, blob="not-a-digest") == 1


def test_main_exits_1_on_a_mismatch_and_0_with_the_envelope_line_on_a_match(monkeypatch, capsys):
    _fake_rag(monkeypatch)
    monkeypatch.setattr(env_check, "observe", lambda frozen: observed(np=4, c=32768, total_slots=4))
    assert _run_main(monkeypatch) == 1
    capsys.readouterr()
    monkeypatch.setattr(env_check, "observe", lambda frozen: observed())
    assert _run_main(monkeypatch) == 0
    assert capsys.readouterr().out.splitlines()[-1].startswith("ENVELOPE server_pid=19379 ")
