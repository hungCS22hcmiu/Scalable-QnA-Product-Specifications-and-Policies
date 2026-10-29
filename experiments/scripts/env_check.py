"""Envelope check — the executable form of ADR-003.

A measurement is admissible only if the generation envelope it reports is the one the live model
server actually serves. Finding F1 is why this reads the **live runner** and never the requested
configuration: `OLLAMA_NUM_PARALLEL=4` was requested, pinned and checked for seven weeks while Ollama
served the frozen model at one slot, because its scheduler refuses parallel requests for the
`qwen35` architecture. A check of the requested value passed the whole time.

    make env-check

## What is verified, and against what

| Frozen value (Makefile) | Observed from |
| :--- | :--- |
| slot count `OLLAMA_NUM_PARALLEL` | the runner's argv (`-np`), **and** the runner's own `/props` (`total_slots`) |
| `num_ctx` (`rag.config`) | argv `-c` = num_ctx × slots, and `/props` per-slot `n_ctx` |
| Ollama version `OLLAMA_VERSION` | the server's `/api/version` (never `ollama --version`: it can print the client's) |
| LLM weights `LLM_BLOB` | the tag's `FROM` blob via `/api/show`, the runner's `--model`, and `/props` `model_path` |
| prompt cache `RUNNER_CACHE_RAM` (ADR-017) | the runner's argv (`--cache-ram`), else `LLAMA_ARG_CACHE_RAM` in its environment (`ps eww`); unset fails |
| context checkpoints `RUNNER_CTX_CHECKPOINTS` (ADR-017) | the runner's argv (`--ctx-checkpoints`), else `LLAMA_ARG_CTX_CHECKPOINTS` in its environment; unset fails |

argv is what Ollama *asked of* the runner; `/props` is what the runner *did*. They are required to
agree because the bundled `llama-server` has its own slot rule (`n_parallel = auto → 4`) and reads
`LLAMA_ARG_*` from its environment, which `ps eww -p <runner pid>` shows after the argv (ADR-017;
`review.md` S2 called it unreadable). The two cache rows are checked only when `make env-check`
passes `--cache-ram` and `--ctx-checkpoints`; `llama-server` takes a setting from argv first, then
from its variable, then from its default (the cache on at 8192 MiB, 32 checkpoints).

## Which runner

Exactly one `llama-server` whose `--model` is the tag's blob **and** whose parent is the process
listening on `rag.config.OLLAMA_BASE_URL`'s port. The embedding runner also serves one slot, so
matching on anything weaker can report the right number for the wrong model. A second Ollama server
sharing `~/.ollama/models` has runners with identical blob paths, which the parent PID separates.

## Side effect

There is no runner until a model is loaded, so the check loads the LLM and the embedding model
exactly as the RAG service would (`num_ctx` from `rag.config`, the server's default `keep_alive`).
That is ~2.1 GB, and it means `make measure` reads memory pressure with the models resident, which
is the reading `CLAUDE.md` names as authoritative.

Anything that cannot be established exits 1 with its reason. Unverifiable never reads as verified.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

_BLOB = re.compile(r"sha256-[0-9a-f]{64}")
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Each runner flag the check reads, with every spelling llama-server accepts for it.
_FLAGS = {
    "np": ("-np", "--parallel"),
    "ctx": ("-c", "--ctx-size"),
    "port": ("--port",),
    "model": ("-m", "--model"),
}

# llama-server's prompt cache and context checkpoints (ADR-017): each setting with the argv spellings
# the bundled `llama-server --help` lists for it, and the variable it reads when argv sets none.
_CACHE_FLAGS: dict[str, tuple[tuple[str, ...], str]] = {
    "cache_ram": (("--cache-ram", "-cram"), "LLAMA_ARG_CACHE_RAM"),
    "ctx_checkpoints": (
        ("--ctx-checkpoints", "-ctxcp", "--swa-checkpoints"),
        "LLAMA_ARG_CTX_CHECKPOINTS",
    ),
}
_CACHE_LABELS = {
    "cache_ram": "runner prompt cache",
    "ctx_checkpoints": "runner context checkpoints",
}


class EnvelopeError(Exception):
    """The envelope could not be established. Always a failure, never a skip."""


class NoRunner(EnvelopeError):
    pass


class AmbiguousRunner(EnvelopeError):
    pass


class Unparseable(EnvelopeError):
    pass


@dataclass(frozen=True)
class Frozen:
    np: int
    num_ctx: int
    version: str
    blob: str


@dataclass(frozen=True)
class RunnerArgs:
    np: int
    ctx: int
    port: int
    model: str


@dataclass(frozen=True)
class Props:
    total_slots: int
    n_ctx: int
    model: str


@dataclass(frozen=True)
class Observed:
    version: str
    server_pid: int
    runner_pid: int
    show_blob: str
    args: RunnerArgs
    props: Props


# =================================================================================================
# Pure — parsing and the decision
# =================================================================================================
def _flag_value(tokens: list[str], spellings: tuple[str, ...], name: str) -> str:
    hits = [i for i, t in enumerate(tokens) if t in spellings]
    if not hits:
        raise Unparseable(f"runner argv carries no {'/'.join(spellings)}")
    if len(hits) > 1:
        raise Unparseable(
            f"runner argv sets {name} {len(hits)} times ({'/'.join(spellings)})"
        )
    i = hits[0]
    if i + 1 >= len(tokens):
        raise Unparseable(f"runner argv ends at {tokens[i]} with no value")
    return tokens[i + 1]


def _int(value: str, name: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise Unparseable(f"runner argv {name} = {value!r} is not an integer") from None


def _blob_token(text: str, what: str) -> str:
    m = _BLOB.search(text)
    if not m:
        raise Unparseable(f"{what} names no sha256 blob: {text!r}")
    return m.group(0)


def parse_runner_args(cmd: str) -> RunnerArgs:
    """The slot count, context, port and weights a runner was launched with. Never defaults."""
    tokens = cmd.split()
    values = {
        name: _flag_value(tokens, spellings, name) for name, spellings in _FLAGS.items()
    }
    return RunnerArgs(
        np=_int(values["np"], "np"),
        ctx=_int(values["ctx"], "ctx"),
        port=_int(values["port"], "port"),
        model=_blob_token(values["model"], "runner --model"),
    )


def _model_blob_or_none(command: str) -> str | None:
    tokens = command.split()
    for i, t in enumerate(tokens[:-1]):
        if t in _FLAGS["model"]:
            m = _BLOB.search(tokens[i + 1])
            return m.group(0) if m else None
    return None


def find_llm_runner(ps_rows: list[str], blob: str, server_pid: int) -> tuple[int, str]:
    """The one llama-server serving `blob` as a child of `server_pid`, as (pid, command)."""
    matches, foreign = [], []
    for row in ps_rows:
        parts = row.split(None, 2)
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        pid, ppid, command = int(parts[0]), int(parts[1]), parts[2]
        if Path(command.split()[0]).name != "llama-server":
            continue
        if _model_blob_or_none(command) != blob:
            continue
        (matches if ppid == server_pid else foreign).append((pid, command))
    if len(matches) > 1:
        pids = ", ".join(str(p) for p, _ in matches)
        raise AmbiguousRunner(
            f"{len(matches)} runners serve {blob[:19]}… under pid {server_pid}: {pids}"
        )
    if not matches:
        detail = (
            f"; {len(foreign)} runner(s) serve it under another server (ppid ≠ {server_pid})"
            if foreign
            else ""
        )
        raise NoRunner(
            f"no llama-server serves {blob[:19]}… under pid {server_pid}{detail}"
        )
    return matches[0]


def blob_from_show(show: dict) -> str:
    """The weights blob the tag resolves to, from `/api/show`'s Modelfile `FROM` line."""
    froms = [
        line
        for line in show.get("modelfile", "").splitlines()
        if line.startswith("FROM ")
    ]
    if len(froms) != 1:
        raise Unparseable(
            f"/api/show Modelfile has {len(froms)} FROM lines, expected exactly 1"
        )
    return _blob_token(froms[0], "/api/show FROM")


def parse_props(props: dict) -> Props:
    """What the runner reports about itself (`GET /props` on llama-server)."""
    total = props.get("total_slots")
    n_ctx = props.get("default_generation_settings", {}).get("n_ctx")
    path = props.get("model_path")
    if (
        not isinstance(total, int)
        or not isinstance(n_ctx, int)
        or not isinstance(path, str)
    ):
        raise Unparseable(
            "runner /props lacks an integer total_slots, an integer "
            "default_generation_settings.n_ctx, or a model_path"
        )
    return Props(
        total_slots=total,
        n_ctx=n_ctx,
        model=_blob_token(path, "runner /props model_path"),
    )


def check(frozen: Frozen, obs: Observed) -> list[str]:
    """Every way the observed envelope differs from the frozen one. Empty means admissible."""
    failures = []
    if obs.version != frozen.version:
        failures.append(
            f"ollama server version {obs.version} ≠ pinned {frozen.version}"
        )
    if obs.show_blob != frozen.blob:
        failures.append(
            f"the LLM tag resolves to blob {obs.show_blob[:19]}… ≠ pinned {frozen.blob[:19]}… "
            "(the weights under the tag changed)"
        )
    if obs.args.np != frozen.np:
        failures.append(
            f"runner launched with -np {obs.args.np} ≠ frozen slot count {frozen.np}"
        )
    if obs.props.total_slots != obs.args.np:
        failures.append(
            f"runner reports total_slots {obs.props.total_slots} but was launched with "
            f"-np {obs.args.np}: it overrode its arguments"
        )
    if obs.args.ctx != frozen.num_ctx * obs.args.np:
        failures.append(
            f"runner -c {obs.args.ctx} ≠ num_ctx × slots = {frozen.num_ctx} × {obs.args.np}"
        )
    if obs.props.n_ctx != frozen.num_ctx:
        failures.append(
            f"runner per-slot n_ctx {obs.props.n_ctx} ≠ frozen num_ctx {frozen.num_ctx}"
        )
    if obs.props.model != obs.args.model:
        failures.append("runner /props model_path names other weights than its --model")
    return failures


def envelope_line(obs: Observed) -> str:
    """One machine-readable line a run can be re-checked against at its end (same runner_pid)."""
    return (
        f"ENVELOPE server_pid={obs.server_pid} runner_pid={obs.runner_pid} version={obs.version} "
        f"np={obs.args.np} ctx={obs.args.ctx} total_slots={obs.props.total_slots} "
        f"n_ctx_slot={obs.props.n_ctx} blob={obs.show_blob}"
    )


# -------------------------------------------------------------------------------------------------
# The runner's cache settings (ADR-017)
# -------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class CacheSetting:
    """One cache setting as the runner has it. `source` is "argv", "env" or "unset"."""

    value: str | None
    source: str


def runner_env(argv_line: str, eww_line: str) -> list[str]:
    """The environment tokens of a runner: whatever `ps eww` prints after the argv prefix.

    Nothing from the argv is ever read as an environment variable, so a path in the argv that
    contains `LLAMA_ARG_CACHE_RAM=0` cannot pass for the setting.
    """
    argv_line, eww_line = argv_line.strip(), eww_line.strip()
    if not argv_line or not eww_line.startswith(argv_line):
        raise Unparseable(
            "`ps eww` does not start with the runner's argv, so its environment cannot be told apart"
        )
    rest = eww_line[len(argv_line) :]
    if rest and not rest[0].isspace():
        raise Unparseable(
            "`ps eww` continues the runner's last argv token, so its environment cannot be told apart"
        )
    tokens = rest.split()
    if not tokens:
        raise Unparseable("`ps eww` shows no environment after the runner's argv")
    return tokens


def runner_cache(argv_line: str, env: list[str]) -> dict[str, CacheSetting]:
    """Each cache setting's effective value: the argv flag, else the `LLAMA_ARG_*` variable, else unset.

    llama-server takes a setting from argv first, then from its variable, then from its default.
    Flags are read from the argv only and variables from the environment only.
    """
    argv = argv_line.split()
    seen: dict[str, CacheSetting] = {}
    for name, (spellings, var) in _CACHE_FLAGS.items():
        values: list[str] = []
        for i, t in enumerate(argv):
            if t in spellings:
                if i + 1 >= len(argv):
                    raise Unparseable(f"runner argv ends at {t} with no value")
                values.append(argv[i + 1])
            else:
                for s in spellings:
                    if t.startswith(s + "="):
                        values.append(t[len(s) + 1 :])
        if len(values) > 1:
            raise Unparseable(
                f"runner argv sets {name} {len(values)} times ({'/'.join(spellings)})"
            )
        if values:
            seen[name] = CacheSetting(values[0], "argv")
            continue
        from_env = [t[len(var) + 1 :] for t in env if t.startswith(var + "=")]
        if len(from_env) > 1:
            raise Unparseable(f"runner environment sets {var} {len(from_env)} times")
        seen[name] = (
            CacheSetting(from_env[0], "env")
            if from_env
            else CacheSetting(None, "unset")
        )
    return seen


def check_runner_cache(
    frozen: dict[str, int], seen: dict[str, CacheSetting]
) -> list[str]:
    """Every cache setting that is not exactly the frozen value. "Unset" fails: the default keeps state."""
    failures = []
    for name, (spellings, var) in _CACHE_FLAGS.items():
        setting, want = seen[name], str(frozen[name])
        if setting.value == want:
            continue
        shown = "unset" if setting.value is None else repr(setting.value)
        msg = (
            f"{_CACHE_LABELS[name]}: {spellings[0]} / {var} is {shown} (from {setting.source}), "
            f"not the frozen {want}"
        )
        if setting.source != "argv":
            msg += "; run `make ollama-env`"
        failures.append(msg)
    return failures


def runner_cache_line(runner_pid: int, seen: dict[str, CacheSetting]) -> str:
    """One machine-readable line for a runner whose cache settings passed."""
    return (
        f"RUNNER_CACHE cache_ram={seen['cache_ram'].value} "
        f"ctx_checkpoints={seen['ctx_checkpoints'].value} runner_pid={runner_pid}"
    )


# =================================================================================================
# I/O
# =================================================================================================
def _http_json(url: str, body: dict | None = None, timeout: float = 10.0) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def _listener_pid(port: int) -> int:
    try:
        out = _run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"])
    except subprocess.CalledProcessError:
        out = ""
    pids = sorted({int(p) for p in out.split()})
    if len(pids) != 1:
        raise EnvelopeError(
            f"expected one process listening on :{port}, found {pids or 'none'}"
        )
    return pids[0]


def observe(frozen: Frozen) -> Observed:
    # Imported here, not at module scope, so the offline tests need neither rag nor Ollama.
    from rag import config

    base = config.OLLAMA_BASE_URL.rstrip("/")
    url = urlparse(base)
    if url.hostname not in _LOCAL_HOSTS:
        raise EnvelopeError(
            f"OLLAMA_BASE_URL {base} is not local; its runner cannot be inspected"
        )
    port = url.port or 11434

    try:
        version = _http_json(f"{base}/api/version")["version"]
    except OSError as e:
        raise EnvelopeError(f"ollama unreachable at {base}: {e}") from None
    server_pid = _listener_pid(port)

    print(
        f"  loading {config.LLM_MODEL} (num_ctx {config.LLM_NUM_CTX}) and "
        f"{config.EMBEDDING_MODEL} as the service would, ~2.1 GB ..."
    )
    warm = _http_json(
        f"{base}/api/generate",
        {"model": config.LLM_MODEL, "options": {"num_ctx": config.LLM_NUM_CTX}},
        timeout=300,
    )
    if not warm.get("done"):
        raise EnvelopeError(f"loading {config.LLM_MODEL} did not complete: {warm}")
    _http_json(
        f"{base}/api/embed",
        {"model": config.EMBEDDING_MODEL, "input": "env-check"},
        timeout=120,
    )

    show_blob = blob_from_show(
        _http_json(f"{base}/api/show", {"model": config.LLM_MODEL})
    )
    rows = _run(["ps", "-axww", "-o", "pid=,ppid=,command="]).splitlines()
    runner_pid, command = find_llm_runner(rows, show_blob, server_pid)
    args = parse_runner_args(command)
    try:
        props = parse_props(_http_json(f"http://127.0.0.1:{args.port}/props"))
    except OSError as e:
        raise EnvelopeError(f"runner /props unreachable on :{args.port}: {e}") from None

    return Observed(
        version=version,
        server_pid=server_pid,
        runner_pid=runner_pid,
        show_blob=show_blob,
        args=args,
        props=props,
    )


def _read_runner_env(runner_pid: int) -> tuple[str, list[str]]:
    """The runner's argv line and its environment tokens, from two `ps` calls on its pid."""
    try:
        argv_line = _run(["ps", "-ww", "-o", "command=", "-p", str(runner_pid)])
        eww_line = _run(["ps", "eww", "-o", "command=", "-p", str(runner_pid)])
    except subprocess.CalledProcessError as e:
        raise EnvelopeError(
            f"`ps` could not read runner {runner_pid} (exit {e.returncode}); has it exited?"
        ) from None
    return argv_line.strip(), runner_env(argv_line, eww_line)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--frozen-np", type=int, required=True, help="frozen generation slot count"
    )
    ap.add_argument(
        "--ollama-version", required=True, help="pinned Ollama server version"
    )
    ap.add_argument(
        "--llm-blob", required=True, help="pinned sha256-… of the LLM weights"
    )
    ap.add_argument(
        "--cache-ram",
        type=int,
        help="frozen prompt-cache limit in MiB (ADR-017); needs --ctx-checkpoints",
    )
    ap.add_argument(
        "--ctx-checkpoints",
        type=int,
        help="frozen context-checkpoint count (ADR-017); needs --cache-ram",
    )
    args = ap.parse_args()

    if (args.cache_ram is None) != (args.ctx_checkpoints is None):
        print("  FAIL — --cache-ram and --ctx-checkpoints must be given together")
        return 1

    try:
        from rag import config

        frozen = Frozen(
            np=args.frozen_np,
            num_ctx=config.LLM_NUM_CTX,
            version=args.ollama_version,
            blob=_blob_token(args.llm_blob, "--llm-blob"),
        )
        obs = observe(frozen)
    except Exception as e:  # noqa: BLE001 -- any failure to establish the envelope is a FAIL, never a skip
        print(f"  FAIL — envelope not verifiable: {type(e).__name__}: {e}")
        return 1

    print(
        f"  frozen    np={frozen.np} num_ctx={frozen.num_ctx} ollama={frozen.version} "
        f"blob={frozen.blob[:19]}…"
    )
    print(
        f"  observed  np={obs.args.np} (argv) / {obs.props.total_slots} (runner) · "
        f"-c {obs.args.ctx} · n_ctx/slot {obs.props.n_ctx} · ollama {obs.version}"
    )
    failures = check(frozen, obs)

    seen = None
    if args.cache_ram is not None:
        try:
            argv_line, env = _read_runner_env(obs.runner_pid)
            seen = runner_cache(argv_line, env)
        except EnvelopeError as e:
            failures.append(f"runner cache not verifiable: {type(e).__name__}: {e}")
        else:
            print(
                "  observed  "
                + " · ".join(
                    f"{name}={'unset' if s.value is None else s.value} ({s.source})"
                    for name, s in seen.items()
                )
            )
            failures += check_runner_cache(
                {"cache_ram": args.cache_ram, "ctx_checkpoints": args.ctx_checkpoints},
                seen,
            )

    for f in failures:
        print(f"  FAIL — {f}")
    if failures:
        print(
            "         A run under this envelope is not the configuration the study reports."
        )
        return 1
    print("  OK")
    if seen is not None:
        print(runner_cache_line(obs.runner_pid, seen))
    print(envelope_line(obs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
