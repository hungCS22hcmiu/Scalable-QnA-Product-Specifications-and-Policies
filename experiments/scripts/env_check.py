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

argv is what Ollama *asked of* the runner; `/props` is what the runner *did*. They are required to
agree because the bundled `llama-server` has its own slot rule (`n_parallel = auto → 4`) and reads
`LLAMA_ARG_*` from an environment nobody can read back (`review.md` S2).

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
        raise Unparseable(f"runner argv sets {name} {len(hits)} times ({'/'.join(spellings)})")
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
    values = {name: _flag_value(tokens, spellings, name) for name, spellings in _FLAGS.items()}
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
        raise AmbiguousRunner(f"{len(matches)} runners serve {blob[:19]}… under pid {server_pid}: {pids}")
    if not matches:
        detail = (
            f"; {len(foreign)} runner(s) serve it under another server (ppid ≠ {server_pid})"
            if foreign
            else ""
        )
        raise NoRunner(f"no llama-server serves {blob[:19]}… under pid {server_pid}{detail}")
    return matches[0]


def blob_from_show(show: dict) -> str:
    """The weights blob the tag resolves to, from `/api/show`'s Modelfile `FROM` line."""
    froms = [line for line in show.get("modelfile", "").splitlines() if line.startswith("FROM ")]
    if len(froms) != 1:
        raise Unparseable(f"/api/show Modelfile has {len(froms)} FROM lines, expected exactly 1")
    return _blob_token(froms[0], "/api/show FROM")


def parse_props(props: dict) -> Props:
    """What the runner reports about itself (`GET /props` on llama-server)."""
    total = props.get("total_slots")
    n_ctx = props.get("default_generation_settings", {}).get("n_ctx")
    path = props.get("model_path")
    if not isinstance(total, int) or not isinstance(n_ctx, int) or not isinstance(path, str):
        raise Unparseable(
            "runner /props lacks an integer total_slots, an integer "
            "default_generation_settings.n_ctx, or a model_path"
        )
    return Props(total_slots=total, n_ctx=n_ctx, model=_blob_token(path, "runner /props model_path"))


def check(frozen: Frozen, obs: Observed) -> list[str]:
    """Every way the observed envelope differs from the frozen one. Empty means admissible."""
    failures = []
    if obs.version != frozen.version:
        failures.append(f"ollama server version {obs.version} ≠ pinned {frozen.version}")
    if obs.show_blob != frozen.blob:
        failures.append(
            f"the LLM tag resolves to blob {obs.show_blob[:19]}… ≠ pinned {frozen.blob[:19]}… "
            "(the weights under the tag changed)"
        )
    if obs.args.np != frozen.np:
        failures.append(f"runner launched with -np {obs.args.np} ≠ frozen slot count {frozen.np}")
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
        failures.append(f"runner per-slot n_ctx {obs.props.n_ctx} ≠ frozen num_ctx {frozen.num_ctx}")
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


# =================================================================================================
# I/O
# =================================================================================================
def _http_json(url: str, body: dict | None = None, timeout: float = 10.0) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
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
        raise EnvelopeError(f"expected one process listening on :{port}, found {pids or 'none'}")
    return pids[0]


def observe(frozen: Frozen) -> Observed:
    # Imported here, not at module scope, so the offline tests need neither rag nor Ollama.
    from rag import config

    base = config.OLLAMA_BASE_URL.rstrip("/")
    url = urlparse(base)
    if url.hostname not in _LOCAL_HOSTS:
        raise EnvelopeError(f"OLLAMA_BASE_URL {base} is not local; its runner cannot be inspected")
    port = url.port or 11434

    try:
        version = _http_json(f"{base}/api/version")["version"]
    except OSError as e:
        raise EnvelopeError(f"ollama unreachable at {base}: {e}") from None
    server_pid = _listener_pid(port)

    print(f"  loading {config.LLM_MODEL} (num_ctx {config.LLM_NUM_CTX}) and "
          f"{config.EMBEDDING_MODEL} as the service would, ~2.1 GB ...")
    warm = _http_json(
        f"{base}/api/generate",
        {"model": config.LLM_MODEL, "options": {"num_ctx": config.LLM_NUM_CTX}},
        timeout=300,
    )
    if not warm.get("done"):
        raise EnvelopeError(f"loading {config.LLM_MODEL} did not complete: {warm}")
    _http_json(f"{base}/api/embed", {"model": config.EMBEDDING_MODEL, "input": "env-check"}, timeout=120)

    show_blob = blob_from_show(_http_json(f"{base}/api/show", {"model": config.LLM_MODEL}))
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frozen-np", type=int, required=True, help="frozen generation slot count")
    ap.add_argument("--ollama-version", required=True, help="pinned Ollama server version")
    ap.add_argument("--llm-blob", required=True, help="pinned sha256-… of the LLM weights")
    args = ap.parse_args()

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

    print(f"  frozen    np={frozen.np} num_ctx={frozen.num_ctx} ollama={frozen.version} "
          f"blob={frozen.blob[:19]}…")
    print(f"  observed  np={obs.args.np} (argv) / {obs.props.total_slots} (runner) · "
          f"-c {obs.args.ctx} · n_ctx/slot {obs.props.n_ctx} · ollama {obs.version}")
    failures = check(frozen, obs)
    for f in failures:
        print(f"  FAIL — {f}")
    if failures:
        print("         A run under this envelope is not the configuration the study reports.")
        return 1
    print("  OK")
    print(envelope_line(obs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
