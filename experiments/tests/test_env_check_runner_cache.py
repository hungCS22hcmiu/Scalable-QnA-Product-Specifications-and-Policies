"""Tests for the runner-cache check in `env_check.py` (ADR-017,
`docs/work/2026-10-29-ollama-prompt-cache/design.md` §3).

What this file guards: a runner with llama-server's prompt cache on must fail `make env-check`.
Ollama 0.33.2 starts the runner with no `--cache-ram`, so the cache is on at 8192 MiB and every
request adds a copy of its prompt to host RAM. The old `env-check` passed that runner, because it
checked only the values the Makefile freezes and never the runner's own defaults.

The check is switched on by two arguments, `--cache-ram` and `--ctx-checkpoints`, because the
immutable `test_env_check.py` runs `main()` with today's argv and expects exit 0. The risk is that
the Makefile stops passing them and `env-check` prints OK without checking. So every test here takes
its argv from `make -n env-check`, not from a copy typed in this file.

No Ollama and no `rag` are needed. Fixtures come from `E/on-argv.txt` and `E/on-env.txt`
(`docs/work/2026-10-29-ollama-prompt-cache/evidence/rca/`), the argv and environment of the runner
Ollama started at login on 2026-10-29, with `/Users/hung` replaced by `/Users/u`. The fixed runner's
environment is `on-env.txt` plus the two variables (design §4 F1: the RCA's own `off2-env.txt` carries
a shell's environment and was cut down).

New functions are reached as `env_check.<name>` at call time, never with `from env_check import`, so
this file imports cleanly before the fix and a missing check shows as a failed assertion.
"""

import os
import shlex
import subprocess
import sys
import types
from pathlib import Path

import env_check
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

LLM_BLOB = "sha256-7a3a8d55382135a773916fd7c35044b2a2a3a7b8dee788095d70f122e6d8f520"
BLOBS = "/Users/u/.ollama/models/blobs"
RUNNER = "/Applications/Ollama.app/Contents/Resources/llama-server"

# `E/on-argv.txt`, verbatim (home directory replaced): the runner of the Ollama started at login.
CAPTURED_ON_ARGV = (
    f"{RUNNER} --model {BLOBS}/{LLM_BLOB} --port 49434 --host 127.0.0.1 --no-webui --offline -c 8192 "
    "-np 1 --log-verbosity 4 --no-log-prefix --no-log-timestamps --no-jinja --chat-template chatml "
    f"--mmproj {BLOBS}/{LLM_BLOB} --flash-attn auto -b 512 -ub 512 --context-shift --keep 4"
)

# `E/on-env.txt`, as tokens. No cache variable in it: that is the bug. SSH_AUTH_SOCK and TMPDIR are
# per-boot random paths, so they hold placeholders.
ON_ENV = [
    "USER=u",
    "COMMAND_MODE=unix2003",
    "HOME=/Users/u",
    "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
    "SHELL=/bin/zsh",
    "XPC_FLAGS=0x0",
    "OLLAMA_MODELS=/Users/u/.ollama/models",
    "SSH_AUTH_SOCK=/var/run/com.apple.launchd.PLACEHOLDER/Listeners",
    "TMPDIR=/var/folders/xx/PLACEHOLDER/T/",
    "OLLAMA_NO_CLOUD=0",
    "LOGNAME=u",
    "__CF_USER_TEXT_ENCODING=0x1F6:0x0:0x0",
    "XPC_SERVICE_NAME=application.com.electron.ollama.25253687.25253693",
    "OLLAMA_CONTEXT_LENGTH=262144",
    (
        "DYLD_LIBRARY_PATH=/Applications/Ollama.app/Contents/Resources:"
        "/Applications/Ollama.app/Contents/Resources/mlx_metal_v4"
    ),
    "LLAMA_ARG_FIT_TARGET=1657",
    "LLAMA_MEDIA_MARKER=<__ollama_media_97e1fdf8c370f81663c5b294fcca7c2c__>",
]
FIXED_ENV = ON_ENV + ["LLAMA_ARG_CACHE_RAM=0", "LLAMA_ARG_CTX_CHECKPOINTS=0"]

RUNNER_PID = 34349
SERVER = 19379


# =================================================================================================
# Fixtures and fakes
# =================================================================================================
def _make_argv() -> list[str]:
    """The arguments `make env-check` passes to env_check.py, as `make -n` prints them."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL")
    }
    out = subprocess.run(
        ["make", "-n", "--no-print-directory", "env-check"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    tokens = shlex.split(out.replace("\\\n", " "))
    at = [i for i, t in enumerate(tokens) if t.endswith("env_check.py")]
    assert at, f"`make -n env-check` does not run env_check.py: {out!r}"
    return tokens[at[0] + 1 :]


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


def _observed():
    return env_check.Observed(
        version="0.33.2",
        server_pid=SERVER,
        runner_pid=RUNNER_PID,
        show_blob=LLM_BLOB,
        args=env_check.RunnerArgs(np=1, ctx=8192, port=49434, model=LLM_BLOB),
        props=env_check.Props(total_slots=1, n_ctx=8192, model=LLM_BLOB),
    )


def _fake_runner(monkeypatch, argv_line, env_tokens, eww=None, ps_fails=False):
    """The captured runner. Only the two `ps` calls on its pid are answered; anything else fails."""
    _fake_rag(monkeypatch)
    monkeypatch.setattr(env_check, "observe", lambda frozen: _observed())
    ps_argv = ["ps", "-ww", "-o", "command=", "-p", str(RUNNER_PID)]
    ps_eww = ["ps", "eww", "-o", "command=", "-p", str(RUNNER_PID)]
    shown = eww if eww is not None else argv_line + " " + " ".join(env_tokens)

    def run(cmd):
        if cmd not in (ps_argv, ps_eww):
            raise AssertionError(f"unexpected command {cmd}")
        if ps_fails:
            raise subprocess.CalledProcessError(1, cmd)
        return (argv_line if cmd == ps_argv else shown) + "\n"

    monkeypatch.setattr(env_check, "_run", run)


def _main(monkeypatch, argv) -> int:
    monkeypatch.setattr(sys, "argv", ["env_check.py", *argv])
    return env_check.main()


# =================================================================================================
# DC 1 — the witness
# =================================================================================================
def test_make_env_check_fails_on_the_captured_cache_on_runner(monkeypatch, capsys):
    # The runner Ollama 0.33.2 started with no --cache-ram: its prompt cache is on at 8192 MiB.
    # `make env-check` passed it (E/env-check-cache-on.txt). It must exit 1 and name the cache.
    _fake_runner(monkeypatch, CAPTURED_ON_ARGV, ON_ENV)
    rc = _main(monkeypatch, _make_argv())
    out = capsys.readouterr().out
    assert rc == 1, (
        f"env-check exited {rc} on a runner with the prompt cache on:\n{out}"
    )
    assert "prompt cache" in out


# =================================================================================================
# DC 2 — the cases around it
# =================================================================================================
def _check(monkeypatch, capsys, argv_line, env_tokens, make_argv=None, **fake):
    """Run main() with `make env-check`'s arguments against a faked runner; return (exit, output)."""
    _fake_runner(monkeypatch, argv_line, env_tokens, **fake)
    rc = _main(monkeypatch, _make_argv() if make_argv is None else make_argv)
    return rc, capsys.readouterr().out


def test_make_env_check_passes_the_captured_fixed_runner(monkeypatch, capsys):
    rc, out = _check(monkeypatch, capsys, CAPTURED_ON_ARGV, FIXED_ENV)
    assert rc == 0, out
    lines = out.strip().splitlines()
    assert any(
        l.startswith("RUNNER_CACHE cache_ram=0 ctx_checkpoints=0") for l in lines
    ), out
    assert lines[-1].startswith("ENVELOPE "), out


@pytest.mark.parametrize(
    "extra",
    [
        " --cache-ram 8192",
        " --cache-ram=8192",
        " -cram 8192",
        " --ctx-checkpoints 32",
        " -ctxcp 32",
        " --swa-checkpoints 32",
    ],
)
def test_an_argv_flag_beats_a_zero_in_the_environment(monkeypatch, capsys, extra):
    # llama-server reads argv first: the environment saying 0 cannot save a runner whose argv says 8192.
    rc, out = _check(monkeypatch, capsys, CAPTURED_ON_ARGV + extra, FIXED_ENV)
    assert rc == 1, out


def test_a_zero_on_argv_passes_without_the_variables(monkeypatch, capsys):
    argv_line = CAPTURED_ON_ARGV + " --cache-ram 0 --ctx-checkpoints 0"
    rc, out = _check(monkeypatch, capsys, argv_line, ON_ENV)
    assert rc == 0, out


@pytest.mark.parametrize(
    "env_tokens",
    [
        [t for t in FIXED_ENV if t != "LLAMA_ARG_CACHE_RAM=0"],
        [t for t in FIXED_ENV if t != "LLAMA_ARG_CTX_CHECKPOINTS=0"],
        [
            "LLAMA_ARG_CACHE_RAM=8192" if t == "LLAMA_ARG_CACHE_RAM=0" else t
            for t in FIXED_ENV
        ],
        [
            "LLAMA_ARG_CTX_CHECKPOINTS=32" if t == "LLAMA_ARG_CTX_CHECKPOINTS=0" else t
            for t in FIXED_ENV
        ],
        FIXED_ENV + ["LLAMA_ARG_CACHE_RAM=8192"],
    ],
    ids=[
        "cache_ram missing",
        "ctx_checkpoints missing",
        "cache_ram 8192",
        "ctx_checkpoints 32",
        "cache_ram doubled",
    ],
)
def test_a_missing_wrong_or_doubled_variable_fails(monkeypatch, capsys, env_tokens):
    rc, out = _check(monkeypatch, capsys, CAPTURED_ON_ARGV, env_tokens)
    assert rc == 1, out


@pytest.mark.parametrize(
    "fake",
    [
        {"ps_fails": True},
        {"eww": CAPTURED_ON_ARGV},
        {"eww": "/other/llama-server --port 1 " + " ".join(FIXED_ENV)},
    ],
    ids=["ps raises", "eww shows no environment", "eww does not start with the argv"],
)
def test_an_environment_that_cannot_be_read_fails_closed(monkeypatch, capsys, fake):
    rc, out = _check(monkeypatch, capsys, CAPTURED_ON_ARGV, FIXED_ENV, **fake)
    assert rc == 1, out
    assert "not verifiable" in out


def test_an_environment_token_inside_argv_is_not_read(monkeypatch, capsys):
    # The token sits in the argv, not in the environment that follows it: it must not count.
    argv_line = CAPTURED_ON_ARGV + " --chat-template LLAMA_ARG_CACHE_RAM=0"
    rc, out = _check(monkeypatch, capsys, argv_line, ON_ENV)
    assert rc == 1, out
    assert "prompt cache" in out


@pytest.mark.parametrize("dropped", ["--ctx-checkpoints", "--cache-ram"])
def test_one_cache_argument_without_the_other_fails(monkeypatch, capsys, dropped):
    argv = _make_argv()
    at = argv.index(dropped)
    del argv[at : at + 2]
    rc, out = _check(monkeypatch, capsys, CAPTURED_ON_ARGV, FIXED_ENV, make_argv=argv)
    assert rc == 1, out
    assert "together" in out


def test_runner_cache_reads_argv_then_env_then_unset():
    both_flags = CAPTURED_ON_ARGV + " --cache-ram 0 --ctx-checkpoints 0"
    both_vars = ["LLAMA_ARG_CACHE_RAM=0", "LLAMA_ARG_CTX_CHECKPOINTS=0"]
    zero = env_check.CacheSetting
    # argv wins, even when the environment disagrees
    seen = env_check.runner_cache(both_flags, ["LLAMA_ARG_CACHE_RAM=8192"])
    assert seen == {
        "cache_ram": zero("0", "argv"),
        "ctx_checkpoints": zero("0", "argv"),
    }
    # no flag: the variable
    seen = env_check.runner_cache(CAPTURED_ON_ARGV, both_vars)
    assert seen == {"cache_ram": zero("0", "env"), "ctx_checkpoints": zero("0", "env")}
    # neither: unset, which is not 0
    seen = env_check.runner_cache(CAPTURED_ON_ARGV, ON_ENV)
    assert seen == {
        "cache_ram": zero(None, "unset"),
        "ctx_checkpoints": zero(None, "unset"),
    }
    # each setting is decided on its own
    seen = env_check.runner_cache(CAPTURED_ON_ARGV + " --cache-ram=0", both_vars[1:])
    assert seen == {"cache_ram": zero("0", "argv"), "ctx_checkpoints": zero("0", "env")}
