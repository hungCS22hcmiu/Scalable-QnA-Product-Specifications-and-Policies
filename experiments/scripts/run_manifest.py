"""Item 5.1: the run manifest (P1, interfaces.md section I) and its check.

    make run-manifest RUN_ID=<id> GATEWAY_LOG=<file> SPLIT=validation
    make run-manifest-check RUN_ID=<id>

`write` reads a finished run's `raw/requests.jsonl` and the gateway's start log, and writes
`results/{run_id}/manifest.yaml` once: the arms (read from the records, ADR-010), what the gateway ran
with (tau, theta, capacity, from the log), the study state (corpus, retrieval, generator), the envelope
(`env_check`, so the generator is loaded) and whether the run is admissible. The manifest holds no
question or answer text, so it stays tracked.

`check` fails on a missing field, a record whose arm differs from the manifest's, and (given the log) a
log from another run or arm.

Exit codes: 0 done / valid; 1 a check failed or a rule refused.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import cache_reset
import corpus_gate
import judge_references as refs
import yaml

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR") or ROOT / "experiments" / "results")
GATEWAY_PORT = 8080
SPLITS = ("validation", "test")
ARM_KEYS = ("config_id", "mutation", "support_gate", "mixed_lane", "scope_arm")
# `scope_arm` exists from item 6.0a. A run from before it has no such key in its records or its log, and
# its arms stay four; a run that has it in one place must have it in the other, and the two must agree.
OPTIONAL_ARM_KEYS = ("scope_arm",)
HITS = ("TIER1_HIT", "TIER2_HIT")
MANIFEST_VERSION = 1

# Every field the manifest must carry (interfaces.md section I), as dotted paths. A field is missing
# when it is absent or null; `false`, `0` and `""` are values.
REQUIRED = (
    "manifest_version",
    "run_id",
    "written_at",
    "gateway.git_sha",
    "gateway.dirty",
    "arms.config_id",
    "arms.mutation",
    "arms.support_gate",
    "arms.mixed_lane",
    "envelope",
    "redis.redis_version",
    "redis.rdb_last_save_time",
    "corpus.dataset_version",
    "corpus.snapshot_digest",
    "workload.file",
    "workload.sha256",
    "workload.K",
    "workload.frozen_cache_capacity",
    "cache.capacity",
    "cache.tau_run",
    "cache.theta_run",
    "retrieval.retrieval_version",
    "retrieval.retrieve_py_sha256",
    "retrieval.top_k",
    "generator.model",
    "generator.digest",
    "generator.num_ctx",
    "generator.think",
    "generator.temperature",
    "generator.prompt_sha256",
    "records.count",
    "records.by_cache",
    "admissibility.rule_6",
    "admissibility.rule_10",
    "admissibility.rule_12",
    "admissibility.i9",
    "admissibility.admissible",
)


class ManifestError(RuntimeError):
    """The manifest could not be built or a rule refused it. The message says which."""


# =================================================================================================
# The readers
# =================================================================================================
def read_records(run_dir: Path) -> list[dict]:
    """Every record of `run_dir/raw/requests.jsonl`. A missing file, a bad line or no record raises."""
    path = Path(run_dir) / "raw" / "requests.jsonl"
    try:
        text = path.read_text()
    except OSError as e:
        raise ManifestError(f"cannot read {path}: {e.strerror}") from None
    records = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            raise ManifestError(f"{path} line {n} is not JSON") from None
    if not records:
        raise ManifestError(f"{path} holds no records")
    return records


def arms(records: list[dict]) -> dict:
    """`config_id, mutation, support_gate, mixed_lane` and, from item 6.0a, `scope_arm`, read from the
    records (ADR-010).

    Raises when one differs across records, or when a record does not carry the key. `scope_arm` alone
    may be absent from every record (an older run); then it is left out.
    """
    if not records:
        raise ManifestError("there are no records to read the arms from")
    out = {}
    for key in ARM_KEYS:
        values = {json.dumps(r.get(key)) for r in records}
        if len(values) > 1:
            raise ManifestError(f"the records differ on {key}: {sorted(values)}")
        value = records[0].get(key)
        if value is None:
            if key in OPTIONAL_ARM_KEYS:
                continue
            raise ManifestError(f"the records carry no {key}")
        out[key] = value
    return out


def _single(pattern: str, text: str, what: str, optional: bool = False) -> str | None:
    found = sorted({m.group(1) for m in re.finditer(pattern, text, re.MULTILINE)})
    if not found:
        if optional:
            return None
        raise ManifestError(f"the gateway log has no {what}")
    if len(found) > 1:
        raise ManifestError(
            f"the gateway log has {len(found)} values for {what}: {found}"
        )
    return found[0]


# Rule 6 reads these gateway lines (interfaces.md §I). `ENDED_LINES`: one shows that the run ended with
# nothing lost. The first is the gateway's last line since item 6.0a, printed only after a clean end;
# the second is the shutdown line of logs written before `29da622`, which renamed it and so voided
# every later run (design.md §4, docs/work/2026-11-13-tier2-scope-by-evidence). `BAD_LINES`: any one
# voids the run; the last two are the warnings `29da622` added. test_run_manifest_end.py checks that
# the gateway still prints every line here except the pre-`29da622` one.
ENDED_LINES = (
    "gateway: run ended cleanly",
    "gateway: shutting down, flushing the evaluation log",
)
BAD_LINES = (
    "gateway: THIS RUN IS INCOMPLETE --",
    "gateway: WARNING requests still in flight",
    "gateway: the dependency map is INCOMPLETE",
)


def parse_gateway_log(text: str, run_id: str) -> dict:
    """What a gateway's start log says: tau, theta, capacity, the two arms, the run, and its end.

    Raises when a value is missing, when the log holds two values for one, and when the log's run id
    is not `run_id`.
    """
    log_run = _single(
        r"evaluation log -> .+/([^/\s]+)/raw/requests\.jsonl",
        text,
        "evaluation log line",
    )
    if log_run != run_id:
        raise ManifestError(f"the gateway log is for run {log_run}, not {run_id}")
    out = {
        "run_id": log_run,
        "tau": float(_single(r"gateway: tau=([0-9.]+) theta=", text, "tau")),
        "theta": float(_single(r"gateway: tau=[0-9.]+ theta=([0-9.]+)", text, "theta")),
        "cache_capacity": int(
            _single(r"gateway: cache_capacity=(\d+)", text, "cache_capacity")
        ),
        "support_gate": _single(
            r"gateway: support_gate=(on|off)\b", text, "support_gate"
        ),
        "mixed_lane": _single(
            r"lane_band=\S+ mixed_lane=(on|off)\b", text, "mixed_lane"
        ),
        "ended": any(line in text for line in ENDED_LINES),
        "incomplete": any(line in text for line in BAD_LINES),
    }
    # From item 6.0a the start-up line reads `mixed_lane=… scope_arm=… tau_p=…`. An older log has no
    # scope_arm, and then the key is left out.
    scope_arm = _single(
        r"mixed_lane=(?:on|off) scope_arm=(on|off)\b", text, "scope_arm", optional=True
    )
    if scope_arm is not None:
        out["scope_arm"] = scope_arm
    return out


def i9_violations(records: list[dict]) -> list[str]:
    """Entry IDs that a hit or a judged candidate names and no MISS record wrote (interfaces.md I9).

    Compared as sets, not in order. A MISS with an empty `entry_id` wrote no entry. A hit with no
    `entry_id` is a violation.
    """
    written = {r.get("entry_id") for r in records if r.get("cache") == "MISS"} - {
        None,
        "",
    }
    named = []
    for r in records:
        if r.get("cache") in HITS:
            named.append(r.get("entry_id") or "")
        if r.get("candidate_entry_id"):
            named.append(r["candidate_entry_id"])
    return sorted({e for e in named if e not in written})


def admissibility(records: list[dict], log: dict) -> dict:
    """The four rules a run's admissibility turns on. `True` means the rule holds.

    rule 6: the gateway ended cleanly and did not report INCOMPLETE. rule 10: no NOT_SCORED. rule 12: no
    Tier-2 search error. I9: every hit and candidate names an entry some MISS wrote.
    """
    rules = {
        "rule_6": bool(log["ended"]) and not log["incomplete"],
        "rule_10": not any(r.get("refusal_cause") == "NOT_SCORED" for r in records),
        "rule_12": not any(r.get("tier2_search_failed") for r in records),
        "i9": not i9_violations(records),
    }
    return {**rules, "admissible": all(rules.values())}


# =================================================================================================
# The writer and the check
# =================================================================================================
def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def build_manifest(
    run_dir: Path,
    log_path: Path,
    split: str,
    *,
    git: Callable[[], dict],
    redis_info: Callable[[], dict],
    envelope: Callable[[], str],
    ollama: Callable[[], dict],
    repo: Path = ROOT,
    now: Callable[[], str] = _utc_now,
) -> dict:
    """The manifest of a finished run, as a dict in the order of interfaces.md section I.

    The injected callables keep the unit tests offline: `git()` gives `git_sha` and `dirty`,
    `redis_info()` gives `redis_version` and `rdb_last_save_time`, `envelope()` the ENVELOPE line,
    `ollama()` the generator block. Raises when the log's run or arms are not the records'.
    """
    run_dir = Path(run_dir)
    records = read_records(run_dir)
    run_arms = arms(records)
    log = parse_gateway_log(Path(log_path).read_text(), run_dir.name)
    for key in ("support_gate", "mixed_lane", "scope_arm"):
        if key in OPTIONAL_ARM_KEYS and key not in log and key not in run_arms:
            continue  # a run from before item 6.0a
        if log.get(key) != run_arms.get(key):
            raise ManifestError(
                f"the gateway log says {key}={log.get(key)} but the records say {run_arms.get(key)}"
            )

    freeze = json.loads((repo / "data" / "v1-freeze.json").read_text())
    workload_file = repo / "data" / f"workload-v1-{split}.json"
    run_file = freeze["run_files"][split]
    return {
        "manifest_version": MANIFEST_VERSION,
        "run_id": run_dir.name,
        "written_at": now(),
        "gateway": git(),
        "arms": run_arms,
        "envelope": envelope(),
        "redis": redis_info(),
        "corpus": refs.corpus_block(repo / "data" / "v1-freeze.json"),
        "workload": {
            "file": str(workload_file.relative_to(repo)),
            "sha256": refs.sha256_file(workload_file),
            "K": run_file["k_distinct_queries"],
            "frozen_cache_capacity": run_file["cache_capacity"],
        },
        "cache": {
            "capacity": log["cache_capacity"],
            "tau_run": log["tau"],
            "theta_run": log["theta"],
        },
        "retrieval": refs.retrieval_block(repo / "rag" / "src" / "rag" / "retrieve.py"),
        "generator": ollama(),
        "records": {
            "count": len(records),
            "by_cache": dict(sorted(Counter(r.get("cache") for r in records).items())),
        },
        "admissibility": admissibility(records, log),
    }


def _get(manifest: dict, dotted: str):
    node = manifest
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def manifest_problems(
    manifest: dict, run_dir: Path, log_path: Path | None = None
) -> list[str]:
    """Every problem with a manifest, as messages. An empty list means it passes the check."""
    problems = [f"missing field {p}" for p in REQUIRED if _get(manifest, p) is None]
    run_dir = Path(run_dir)
    if manifest.get("run_id") not in (None, run_dir.name):
        problems.append(
            f"run_id {manifest['run_id']} is not the folder's {run_dir.name}"
        )
    envelope = manifest.get("envelope")
    if envelope is not None and not str(envelope).startswith("ENVELOPE "):
        problems.append("envelope is not an ENVELOPE line")

    try:
        records = read_records(run_dir)
        run_arms = arms(records)
    except ManifestError as e:
        return [*problems, str(e)]
    stored = manifest.get("arms") or {}
    for key in ARM_KEYS:
        if stored.get(key) is not None and stored[key] != run_arms.get(key):
            problems.append(
                f"the records say {key}={run_arms.get(key)!r}, the manifest says {stored[key]!r}"
            )
    count = _get(manifest, "records.count")
    if count is not None and count != len(records):
        problems.append(
            f"the manifest counts {count} records, requests.jsonl has {len(records)}"
        )

    if log_path is not None:
        try:
            log = parse_gateway_log(Path(log_path).read_text(), run_dir.name)
        except (ManifestError, OSError) as e:
            return [*problems, f"gateway log: {e}"]
        for key in ("support_gate", "mixed_lane", "scope_arm"):
            if key in OPTIONAL_ARM_KEYS and key not in log and key not in run_arms:
                continue  # a run from before item 6.0a
            if log.get(key) != run_arms.get(key):
                problems.append(
                    f"the gateway log says {key}={log.get(key)}, the records say {run_arms.get(key)}"
                )
    return problems


def check_manifest(run_dir: Path, log_path: Path | None = None) -> list[str]:
    """Check `run_dir/manifest.yaml`: every field present, arms equal the records', and, when the log
    is given, the log's two arms and run equal the records'. Returns the problems (empty: it passes).

    The manifest has no field for the log's arms, so the log can only be compared when it is passed.
    `build_manifest` always compares it at write time.
    """
    path = Path(run_dir) / "manifest.yaml"
    if not path.is_file():
        return [f"no manifest.yaml in {run_dir}"]
    try:
        manifest = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        return [f"manifest.yaml is not valid YAML: {e}"]
    if not isinstance(manifest, dict):
        return ["manifest.yaml is not a mapping"]
    return manifest_problems(manifest, run_dir, log_path)


# =================================================================================================
# What `write` reads from the machine
# =================================================================================================
def gateway_git() -> dict:
    """The commit, and whether the code the gateway runs (gateway/, rag/src) differs from it."""
    state = corpus_gate.git_state(paths=("gateway", "rag/src"))
    if state["commit"] is None:
        raise ManifestError("cannot read the git commit")
    return {"git_sha": state["commit"], "dirty": not state["tree_clean"]}


def redis_info() -> dict:
    import redis

    info = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379")).info()
    return {
        "redis_version": info["redis_version"],
        "rdb_last_save_time": info["rdb_last_save_time"],
    }


def checked_envelope(args: argparse.Namespace) -> str:
    """`make env-check`, as a function: load the models as the service does, check every frozen value
    against the live runner, and return the ENVELOPE line. Any failure raises, so no manifest is written
    for a run on another envelope."""
    import env_check

    from rag import config

    frozen = env_check.Frozen(
        np=args.frozen_np,
        num_ctx=config.LLM_NUM_CTX,
        version=args.ollama_version,
        blob=env_check._blob_token(args.llm_blob, "--llm-blob"),
    )
    obs = env_check.observe(frozen)
    failures = env_check.check(frozen, obs)
    argv_line, env = env_check._read_runner_env(obs.runner_pid)
    seen = env_check.runner_cache(argv_line, env)
    failures += env_check.check_runner_cache(
        {"cache_ram": args.cache_ram, "ctx_checkpoints": args.ctx_checkpoints}, seen
    )
    if failures:
        raise ManifestError(
            "the envelope is not the frozen one: " + "; ".join(failures)
        )
    return env_check.envelope_line(obs)


def generator_block() -> dict:
    """The generator block, with the served prompt's hash: `generate.prompt_sha256()`, the system text
    and the user template together (ADR-029). `refs.generator_block` reads everything else from Ollama;
    its own prompt field hashes the template alone, so it is replaced here."""
    from rag import generate

    block = refs.generator_block()
    block["prompt_sha256"] = generate.prompt_sha256()
    return block


def write(args: argparse.Namespace) -> int:
    run_dir = Path(args.results_dir) / args.run_id
    path = run_dir / "manifest.yaml"
    if path.exists():
        raise ManifestError(f"{path} exists; a manifest is written once")
    if cache_reset.listening_ports((GATEWAY_PORT,)):
        raise ManifestError(
            f"a gateway is still listening on :{GATEWAY_PORT}; stop it first"
        )

    manifest = build_manifest(
        run_dir,
        args.gateway_log,
        args.split,
        git=gateway_git,
        redis_info=redis_info,
        envelope=lambda: checked_envelope(args),
        ollama=generator_block,
    )
    problems = manifest_problems(manifest, run_dir, args.gateway_log)
    if problems:
        raise ManifestError("the manifest fails its own check: " + "; ".join(problems))
    with open(path, "x") as f:
        yaml.safe_dump(manifest, f, sort_keys=False)
    verdict = manifest["admissibility"]
    print(f"wrote {path}")
    print(
        f"  arms {manifest['arms']}  records {manifest['records']['count']}  "
        f"admissible {verdict['admissible']}"
    )
    if not verdict["admissible"]:
        broken = [k for k in ("rule_6", "rule_10", "rule_12", "i9") if not verdict[k]]
        print(f"  NOT ADMISSIBLE: {', '.join(broken)} does not hold")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)

    w = sub.add_parser(
        "write", help="write results/{run_id}/manifest.yaml (loads the models)"
    )
    w.add_argument("--run-id", required=True)
    w.add_argument("--gateway-log", type=Path, required=True)
    w.add_argument("--split", choices=SPLITS, required=True)
    w.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    # The same arguments `make env-check` passes.
    w.add_argument("--frozen-np", type=int, required=True)
    w.add_argument("--ollama-version", required=True)
    w.add_argument("--llm-blob", required=True)
    w.add_argument("--cache-ram", type=int, required=True)
    w.add_argument("--ctx-checkpoints", type=int, required=True)

    c = sub.add_parser("check", help="check results/{run_id}/manifest.yaml")
    c.add_argument("--run-id", required=True)
    c.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    c.add_argument(
        "--gateway-log", type=Path, help="also compare the log's run and arms"
    )

    args = ap.parse_args(argv)
    try:
        if args.command == "write":
            return write(args)
        problems = check_manifest(
            Path(args.results_dir) / args.run_id, args.gateway_log
        )
    except ManifestError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 -- an envelope that cannot be read is a refusal, never a skip
        print(f"REFUSED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    for p in problems:
        print(f"FAIL  {p}")
    if problems:
        print(f"run-manifest-check: {len(problems)} problem(s)")
        return 1
    print("run-manifest-check: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
