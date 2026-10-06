"""Item 1.6: what a co-hosted load generator costs the machine it shares with the system under test.

    python3 experiments/scripts/loadgen_footprint.py run --help        # drive k6 under the sampler
    python3 experiments/scripts/loadgen_footprint.py summarize --help  # regenerate the table from the CSVs
    make footprint                                                      # the supported entry point

EXPLORATORY. The figures this produces are indicative, not citable (decisions.md ADR-001): the run is
not gated on memory pressure, and the reading is recorded raw. Design: docs/work/2026-10-06-loadgen-
footprint/design.md. The points that make it trustworthy, because each is a silent failure if wrong:

  * k6 is a CHILD of this process. Its exit status and its exact total CPU and peak RSS come from
    os.wait4, never from Popen.wait/poll (after wait4 has reaped the child, Popen.poll() returns 0 whatever
    the child exited with -- measured 2026-10-06, evidence/probes.md U13).
  * CPU is the difference of cumulative `ps cputime` over the wall time between the same two `ps` calls.
    It is never `ps %cpu`, which is a decayed average on macOS.
  * `ru_maxrss` is BYTES on macOS (KB on Linux).
  * `ps -o cputime` is `MMM:SS.ss` with no hour field; an unrecognised form raises instead of guessing.
  * Nothing here imports `rag`: the package is pip -e installed, so the import would succeed and put
    LlamaIndex inside the instrument's own resident set.

Standard library only. Uses ps, sysctl, vm_stat, footprint and ollama, which ship with macOS / the host.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import math
import os
import random
import re
import resource
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from pathlib import Path

# ---------------------------------------------------------------------------------------------------
# Parsing and one-shot readings
# ---------------------------------------------------------------------------------------------------


def parse_cputime(text: str) -> float:
    """`ps -o cputime=` as seconds. Accepts M:SS.ss / MMM:SS.ss (macOS: no hour field) and H:MM:SS.ss.

    Raises ValueError on anything else. A parser that assumed HH:MM:SS would read `43:57.34` sixty times
    wrong with no error, which is the failure this exists to refuse.
    """
    parts = text.strip().split(":")
    try:
        if len(parts) == 2:
            hours, minutes, seconds = 0, int(parts[0]), float(parts[1])
        elif len(parts) == 3:
            hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
        else:
            raise ValueError
        if hours < 0 or minutes < 0 or not 0 <= seconds < 60 or not math.isfinite(seconds):
            raise ValueError
    except ValueError:
        raise ValueError(f"unrecognised cputime {text!r}") from None
    return hours * 3600 + minutes * 60 + seconds


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile. No interpolation, so a reported p95 is a value that was observed."""
    if not values:
        raise ValueError("percentile of nothing")
    ranked = sorted(values)
    return ranked[max(1, math.ceil(p / 100.0 * len(ranked))) - 1]


@dataclass
class PsRow:
    stat: str
    rss_kb: int
    cpu_s: float


class ProcessGone(Exception):
    """A pid asked for is not in `ps`. `found` carries the rows that were."""

    def __init__(self, pids: list[int], found: dict[int, PsRow]):
        super().__init__(f"pid(s) not found: {pids}")
        self.pids, self.found = pids, found


def sample_ps(pids: list[int]) -> dict[int, PsRow]:
    """One `ps` call for every pid. A missing pid is an error, not a gap: `ps -p a,b` silently drops one."""
    if not pids:
        return {}
    out = subprocess.run(
        ["ps", "-o", "pid=,stat=,rss=,cputime=", "-p", ",".join(str(p) for p in pids)],
        capture_output=True, text=True, check=False,
    ).stdout
    rows: dict[int, PsRow] = {}
    for line in out.splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise ValueError(f"unparseable ps row {line!r}")
        rows[int(fields[0])] = PsRow(stat=fields[1], rss_kb=int(fields[2]), cpu_s=parse_cputime(fields[3]))
    missing = [p for p in pids if p not in rows]
    if missing:
        raise ProcessGone(missing, rows)
    return rows


_SWAP_USED = re.compile(r"used\s*=\s*([\d.]+)M")


def sample_machine() -> dict[str, float]:
    """The raw memory readings, one `sysctl` call. Integers are NOT mapped to a colour: this repository's
    `0 = green` is unverified against what the sysctl actually returns (design.md U8)."""
    out = subprocess.run(
        ["sysctl", "-n", "kern.memorystatus_vm_pressure_level", "kern.memorystatus_level", "vm.swapusage"],
        capture_output=True, text=True, check=False,
    ).stdout.splitlines()
    if len(out) < 3:
        raise ValueError(f"sysctl returned {len(out)} lines, expected 3: {out!r}")
    swap = _SWAP_USED.search(out[2])
    if swap is None:
        raise ValueError(f"unparseable vm.swapusage {out[2]!r}")
    return {
        "vm_pressure_level": int(out[0]),
        "memstatus_level": int(out[1]),
        "swap_used_mb": float(swap.group(1)),
    }


# ---------------------------------------------------------------------------------------------------
# Running a child under the sampler
# ---------------------------------------------------------------------------------------------------


@dataclass
class Tick:
    t: float                        # seconds since the child started (midpoint of the `ps` call)
    cpu_s: float                    # the child's cumulative CPU seconds at that instant
    rss_kb: int
    stat: str
    extra: dict[int, tuple[float, int]] = field(default_factory=dict)   # pid -> (cpu_s, rss_kb)
    machine: dict[str, float] = field(default_factory=dict)
    pid: int = 0                    # the sampled child, so an on_tick probe never has to look it up


@dataclass
class RunResult:
    ticks: list[Tick]
    wall_s: float                   # to the tick that noticed the exit: may overstate by one interval
    rusage_cpu_s: float             # exact total, from wait4
    maxrss_bytes: int               # exact peak, from wait4 (BYTES on macOS)
    exit_status: int                # from wait4's status, never from Popen
    discarded_ticks: int = 0
    flags: list[str] = field(default_factory=list)


class Interrupted(SystemExit):
    """Raised by the signal handlers so the `finally` in run_child kills the child's process group."""


def install_signal_handlers() -> None:
    def handler(signum, _frame):
        raise Interrupted(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, handler)


def child_comm(pid: int) -> str:
    """The executable's basename as `ps` reports it ('' if the pid is gone)."""
    out = subprocess.run(["ps", "-o", "comm=", "-p", str(pid)], capture_output=True, text=True, check=False).stdout.strip()
    return Path(out).name if out else ""


def run_child(
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    interval: float = 1.0,
    stdout: str | None = None,
    stderr: str | None = None,
    extra_pids: tuple[int, ...] = (),
    extra_every: int = 1,
    machine: bool = False,
    expect_comm: str | None = None,
    on_tick: Callable[[Tick], None] | None = None,
) -> RunResult:
    """Run `argv` as a child in its own session and sample it every `interval` seconds until it exits.

    Each tick calls `wait4(WNOHANG)` BEFORE `ps`: while the child lives it returns zeroed rusage, and the
    loop must never leave holding that. A tick taken as the child exits, or while it is a zombie, or whose
    cumulative CPU went backwards, is DISCARDED, not clamped. Output goes to files, never a PIPE (a PIPE
    with no reader stalls the child at ~64 KB and reads as low CPU). Whatever happens -- an exception from
    `on_tick`, a signal turned into an exception -- the child's process group is killed and reaped.
    """
    with contextlib.ExitStack() as files:
        out = files.enter_context(open(stdout, "wb")) if stdout else subprocess.DEVNULL
        err = files.enter_context(open(stderr, "wb")) if stderr else subprocess.DEVNULL
        proc = subprocess.Popen(argv, env=env, stdout=out, stderr=err, start_new_session=True)
        pid, reaped = proc.pid, None
        t0 = time.monotonic()
        ticks: list[Tick] = []
        discarded, flags = 0, []
        try:
            next_at = t0 + interval
            while True:
                time.sleep(max(0.0, next_at - time.monotonic()))
                next_at += interval
                done = os.wait4(pid, os.WNOHANG)
                if done[0] != 0:
                    reaped = done
                    break
                before = time.monotonic()
                try:
                    # The child is sampled every tick; the extra (SUT) pids only every `extra_every`-th. They are
                    # context, not the measurement, and one `ps` over ~9 pids costs ~25 ms against ~3 ms for one.
                    due_extra = len(ticks) % extra_every == 0
                    rows = sample_ps([pid, *extra_pids] if due_extra else [pid])
                except ProcessGone as gone:
                    if pid in gone.pids:
                        discarded += 1            # raced with its exit; the next wait4 reaps it
                        continue
                    for missing in gone.pids:
                        flag = f"sut_pid_missing:{missing}"
                        if flag not in flags:
                            flags.append(flag)
                    rows = gone.found
                after = time.monotonic()
                row = rows[pid]
                if row.stat.startswith("Z") or (ticks and row.cpu_s < ticks[-1].cpu_s):
                    discarded += 1
                    continue
                tick = Tick(
                    t=(before + after) / 2 - t0, cpu_s=row.cpu_s, rss_kb=row.rss_kb, stat=row.stat,
                    extra={p: (r.cpu_s, r.rss_kb) for p, r in rows.items() if p != pid},
                    machine=sample_machine() if machine else {}, pid=pid,
                )
                ticks.append(tick)
                if expect_comm is not None and len(ticks) == 1:
                    comm = child_comm(pid)          # a wrapper that spawns k6 would read ~0 CPU with no error
                    if comm != expect_comm:
                        flags.append(f"wrong_process:{comm or 'gone'}")
                if on_tick is not None:
                    on_tick(tick)
            wall = time.monotonic() - t0
            usage = reaped[2]
            return RunResult(
                ticks=ticks, wall_s=wall, rusage_cpu_s=usage.ru_utime + usage.ru_stime,
                maxrss_bytes=usage.ru_maxrss, exit_status=os.waitstatus_to_exitcode(reaped[1]),
                discarded_ticks=discarded, flags=flags,
            )
        finally:
            if reaped is None:                    # abnormal exit: the child may still be running
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(pid, signal.SIGKILL)
                with contextlib.suppress(ChildProcessError):
                    os.wait4(pid, 0)


def window_mean(ticks: list[Tick], trim_head: float = 5.0, trim_tail: float = 5.0) -> float:
    """Mean CPU over the steady-state window, as % of ONE core (100 = one core; can exceed 100).

    From cumulative CPU, not from averaging per-tick percentages: delta CPU over delta wall across the
    window. The window is the ticks at least `trim_head` seconds in and at least `trim_tail` before the
    last tick, so k6's start-up and teardown are excluded. Fixed in advance, never adjusted to the data.
    """
    if not ticks:
        raise ValueError("no ticks")
    last = ticks[-1].t
    window = [t for t in ticks if trim_head <= t.t <= last - trim_tail]
    if len(window) < 2:
        raise ValueError(f"fewer than two ticks in the steady-state window (head {trim_head}, tail {trim_tail})")
    span = window[-1].t - window[0].t
    if span <= 0:
        raise ValueError("steady-state window has no duration")
    return 100.0 * (window[-1].cpu_s - window[0].cpu_s) / span


def per_tick_pct(ticks: list[Tick]) -> list[float]:
    """CPU % of one core over each consecutive pair of ticks. Quantised to ~1 cs per sample (about 1 % of
    a core at a 1 s tick), so p95 and max of THIS are labelled quantised and are never used to decide."""
    return [100.0 * (b.cpu_s - a.cpu_s) / (b.t - a.t) for a, b in pairwise(ticks) if b.t > a.t]


# ---------------------------------------------------------------------------------------------------
# From runs to a table. Pure: no I/O, so it is tested on synthetic inputs with hand-computed answers.
# ---------------------------------------------------------------------------------------------------

ATTAINED = 0.95            # achieved / offered below this is UNATTAINED: the cost of a lower rate
RUSAGE_SLACK_S = 0.05      # sampled CPU may not exceed the exact total by more than this (5 cs)
ERROR_RATE_LIMIT = 0.01    # ask.js's own threshold
DISCARD_LIMIT = 0.10       # more than 10 % of a run's ticks discarded (zombie, backwards, vanished): not trusted
SAMPLED_FLOOR = 0.5        # sampled CPU under half of wait4's exact total: the sampler is not watching the child


@dataclass
class RunRecord:
    kind: str                       # "allhit" | "mixed"
    rate_offered: float
    rep: int
    achieved_rate: float
    cpu_pct_mean: float             # steady-state window, % of one core
    rss_peak_bytes: int             # ru_maxrss
    rusage_cpu_s: float             # exact total from wait4
    sampled_cpu_s: float            # last sampled cumulative CPU minus the first
    exit_status: int
    error_rate: float
    shed: int
    miss: int
    vus_max: int
    tier1: int = 0
    tier2: int = 0
    dropped: int = 0
    discarded_ticks: int = 0
    n_ticks: int = 0
    cpu_pct_p95: float = 0.0        # per-second, quantised
    cpu_pct_max: float = 0.0
    sampler_overhead_pct: float = 0.0
    flags: list[str] = field(default_factory=list)      # driver-supplied exclusion flags


@dataclass
class Row:
    kind: str
    rate_offered: float
    reps: int
    achieved_rate: float
    cpu_pct_mean: float
    cpu_pct_min: float
    cpu_pct_max: float
    cpu_pct_of_machine: float
    rss_peak_bytes: int
    vus_max: int
    sampler_overhead_pct: float


@dataclass
class Table:
    rows: list[Row]
    excluded: list[tuple[RunRecord, list[str]]]
    fit: tuple[float, float] | None     # (intercept a, slope b): cpu% = a + b * achieved_rate, all-hit only


def exclusion_flags(run: RunRecord) -> list[str]:
    """Why a run may not enter the table. A flagged run is LEFT OUT and listed, never annotated and kept."""
    flags: list[str] = []
    if run.exit_status != 0:
        flags.append("exit_status")
    if run.achieved_rate < ATTAINED * run.rate_offered:
        flags.append("unattained")
    if run.kind == "allhit":
        if run.miss > 0:
            flags.append("miss_in_allhit")
        if run.shed > 0:
            flags.append("shed_in_allhit")
        if run.error_rate > 0:
            flags.append("errors_in_allhit")
    elif run.error_rate >= ERROR_RATE_LIMIT:
        flags.append("errors_in_mixed")
    if run.sampled_cpu_s > run.rusage_cpu_s + RUSAGE_SLACK_S:
        flags.append("rusage_below_sampled")      # the sampler read something that is not the child
    if run.rusage_cpu_s > 0.5 and run.sampled_cpu_s < SAMPLED_FLOOR * run.rusage_cpu_s:
        flags.append("sampled_far_below_rusage")  # e.g. a wrapper's pid: sampled ~0 while wait4 counts what it waited for
    if run.n_ticks and run.discarded_ticks > DISCARD_LIMIT * (run.n_ticks + run.discarded_ticks):
        flags.append("many_discarded_ticks")
    flags.extend(run.flags)
    return flags


def fit_line(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Least squares y = a + b x; None unless there are two distinct x."""
    if len({x for x, _ in points}) < 2:
        return None
    n = len(points)
    mx, my = sum(x for x, _ in points) / n, sum(y for _, y in points) / n
    sxx = sum((x - mx) ** 2 for x, _ in points)
    b = sum((x - mx) * (y - my) for x, y in points) / sxx
    return my - b * mx, b


def summarise(runs: list[RunRecord], ncpu: int) -> Table:
    kept: list[RunRecord] = []
    excluded: list[tuple[RunRecord, list[str]]] = []
    for run in runs:
        flags = exclusion_flags(run)
        (excluded.append((run, flags)) if flags else kept.append(run))
    groups: dict[tuple[str, float], list[RunRecord]] = {}
    for run in kept:
        groups.setdefault((run.kind, run.rate_offered), []).append(run)
    rows = []
    for (kind, rate), group in sorted(groups.items()):
        cpus = [r.cpu_pct_mean for r in group]
        mean = sum(cpus) / len(cpus)
        rows.append(Row(
            kind=kind, rate_offered=rate, reps=len(group),
            achieved_rate=sum(r.achieved_rate for r in group) / len(group),
            cpu_pct_mean=mean, cpu_pct_min=min(cpus), cpu_pct_max=max(cpus),
            cpu_pct_of_machine=mean / ncpu,
            rss_peak_bytes=max(r.rss_peak_bytes for r in group),
            vus_max=max(r.vus_max for r in group),
            sampler_overhead_pct=sum(r.sampler_overhead_pct for r in group) / len(group),
        ))
    fit = fit_line([(r.achieved_rate, r.cpu_pct_mean) for r in kept if r.kind == "allhit"])
    return Table(rows=rows, excluded=excluded, fit=fit)


def sliding_pct(ticks: list[Tick], width: float) -> list[float]:
    """CPU % of one core over every span of at least `width` seconds between two ticks (smoother than the
    per-tick series, and less exposed to the 1 cs quantisation and to aliasing with k6's 1 s flush)."""
    out: list[float] = []
    for i, a in enumerate(ticks):
        b = next((t for t in ticks[i + 1:] if t.t - a.t >= width), None)
        if b is not None:
            out.append(100.0 * (b.cpu_s - a.cpu_s) / (b.t - a.t))
    return out


# ---------------------------------------------------------------------------------------------------
# The driver. Everything below touches the machine; everything above is pure and unit-tested.
# ---------------------------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
K6_SCRIPT = ROOT / "experiments/k6/ask.js"
WINDOW_HEAD_S = 5.0                 # steady state excludes the first and last 5 s: fixed in advance
WINDOW_TAIL_S = 5.0

# Keep in step with the fallback set in experiments/k6/ask.js. If they drift the all-hit rows MISS inside
# the window and are excluded (miss_in_allhit), so the drift is loud rather than silent.
SMOKE_QUESTIONS = [
    "what is the battery life of the EarBuds Pop 3",
    "how long do I have to return an item",
    "what is the warranty period",
    "what is the battery life of the EarBuds Pop 3 and how long do I have to return it",
    "how much RAM does the UltraBook Pro 14 have",
]
_COLOURS = ["black", "white", "silver", "blue", "red", "green", "grey", "gold", "pink", "orange", "teal", "brown"]
_SIZES = ["small", "medium", "large", "compact", "standard", "refurbished", "boxed", "2024"]


class RunAbort(Exception):
    """A precondition failed; the run stops before it measures anything it could not trust."""


def run_text(argv: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(argv, capture_output=True, text=True, check=False, cwd=cwd).stdout


def ask(url: str, question: str, timeout: float = 150.0) -> tuple[int, dict]:
    req = urllib.request.Request(
        url.rstrip("/") + "/ask", data=json.dumps({"question": question}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, {}
    except urllib.error.URLError as err:
        raise RunAbort(f"cannot reach the gateway at {url}: {err.reason}") from err


def listener_pid(port: int) -> int:
    pids = sorted({int(p) for p in run_text(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"]).split()})
    if len(pids) != 1:
        raise RunAbort(f"expected exactly one listener on :{port}, found {pids or 'none'}")
    return pids[0]


def embed_runner_pid(rows: list[str], serve_pid: int, llm_pid: int) -> int:
    """The one `llama-server` child of `ollama serve` that is not the LLM runner. A swap of the two roles would
    attribute the LLM's CPU to the embedder (and the reverse) with no error."""
    others = []
    for row in rows:
        parts = row.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            pid, ppid, command = int(parts[0]), int(parts[1]), parts[2]
            if ppid == serve_pid and Path(command.split()[0]).name == "llama-server" and pid != llm_pid:
                others.append(pid)
    if len(others) != 1:
        raise RunAbort(f"expected exactly one embedding runner besides the LLM runner, found {others}")
    return others[0]


def resolve_sut(a: argparse.Namespace) -> dict[str, int]:
    """The SUT's processes, BY PORT where one exists and the runners by parent + blob, never by name.
    `pgrep redis-stack-server` returns the shell wrapper and `pgrep ollama` the 27 MB server, not the
    processes that hold the data and the models (impact.md §8.4)."""
    import env_check

    pids = {
        "gateway": listener_pid(a.gateway_port),
        "rag_server": listener_pid(a.rag_port),
        "redis": listener_pid(a.redis_port),
        "ollama_serve": listener_pid(a.ollama_port),
    }
    rows = run_text(["ps", "-axww", "-o", "pid=,ppid=,command="]).splitlines()
    try:
        llm_pid, _ = env_check.find_llm_runner(rows, a.llm_blob, pids["ollama_serve"])
    except Exception as err:    # the env_check error classes carry their own message
        raise RunAbort(f"cannot find the LLM runner: {err}") from err
    return {**pids, "llm_runner": llm_pid, "embed_runner": embed_runner_pid(rows, pids["ollama_serve"], llm_pid)}


def assert_models_loaded(a: argparse.Namespace) -> str:
    text = run_text(["ollama", "ps"])
    missing = [tag for tag in (a.llm_tag, a.embed_tag) if tag not in text]
    if missing:
        raise RunAbort(f"`ollama ps` does not list {missing}: the SUT is not in the state spec decision 3 requires\n{text}")
    llm_line = next(line for line in text.splitlines() if line.startswith(a.llm_tag))
    if str(a.num_ctx) not in llm_line.split():
        raise RunAbort(f"the LLM is loaded at a context other than {a.num_ctx} (the frozen envelope):\n{llm_line}")
    return text


def warm_up(a: argparse.Namespace) -> None:
    """Two sequential passes of the smoke set: the first fills the cache, the second must be all hits."""
    for pass_no in (1, 2):
        for q in SMOKE_QUESTIONS:
            status, body = ask(a.gateway_url, q)
            if status != 200:
                raise RunAbort(f"warm-up pass {pass_no}: HTTP {status} for {q!r} (U9: the smoke set must answer)")
            if pass_no == 2 and body.get("cache") == "MISS":
                raise RunAbort(f"warm-up pass 2 still MISSed {q!r}: write-back is not working, so no row would be all-hit")


# The cache's key prefixes (interfaces.md §D/§E; the same list `make demo-reset` guards on). `corpus:` is the
# ingested index and is NEVER touched here. A prefix-only DEL leaves the `idx:cache` index in place, unlike
# FLUSHALL, so it is safe under a live gateway between k6 runs.
#
# The DEPENDENCY REGION (`dep:` `entry:`, §E) is different: once C2 exists, `gateway/internal/deps/` is its only
# writer (architecture.md §2), and deleting it from outside would bypass the in-process index and the epoch,
# leaving a `t2:` record with no `dep:` set -- an unpurgeable entry, with no error (CLAUDE.md invariant 1).
# So this tool refuses to run while any exists, instead of deleting it.
DELETABLE_PREFIXES = ("t1:", "t2:", "lru:")
GUARDED_PREFIXES = ("dep:", "entry:")
CACHE_PREFIXES = (*DELETABLE_PREFIXES, *GUARDED_PREFIXES)
CORPUS_PREFIX = "corpus:"


def redis_cli(port: int = 6379) -> Callable[..., str]:
    """`redis-cli` against the port the SUT actually uses (a flush against the wrong server would report an
    empty cache and leave the SUT's warm)."""
    return lambda *argv: run_text(["redis-cli", "-p", str(port), *argv])


def cache_counts(redis: Callable[..., str]) -> dict[str, int]:
    return {p: len(redis("--scan", "--pattern", p + "*").split()) for p in (*CACHE_PREFIXES, CORPUS_PREFIX)}


def flush_cache(redis: Callable[..., str] | None = None, port: int = 6379) -> dict[str, int]:
    """Delete the cache keys (t1: t2: lru:) and nothing else; verify they are gone and the corpus untouched.
    Returns the counts BEFORE. Needed because the mixed workload is seeded: without it a second repetition
    finds the whole workload already cached by the first, and the repetitions are not samples of the same
    cold-start regime (found in the shakedown, 2026-10-06). Aborts, deleting nothing, if dependency-region
    keys exist."""
    redis = redis if redis is not None else redis_cli(port)
    if redis("PING").strip() != "PONG":
        raise RunAbort("redis-cli PING did not answer PONG")
    before = cache_counts(redis)
    guarded = {p: before[p] for p in GUARDED_PREFIXES if before[p]}
    if guarded:
        raise RunAbort(
            f"dependency-region keys exist {guarded}: C2 state must not be deleted from outside the gateway "
            "(interfaces.md §E, CLAUDE.md invariant 1). Stop the gateway and clear it deliberately."
        )
    for prefix in DELETABLE_PREFIXES:
        keys = redis("--scan", "--pattern", prefix + "*").split()
        for i in range(0, len(keys), 200):
            redis("DEL", *keys[i : i + 200])
    after = cache_counts(redis)
    left = {p: n for p, n in after.items() if p in DELETABLE_PREFIXES and n}
    if left:
        raise RunAbort(f"cache keys survived the flush: {left}")
    if after[CORPUS_PREFIX] != before[CORPUS_PREFIX]:
        raise RunAbort(f"corpus keys changed during a cache flush: {before[CORPUS_PREFIX]} -> {after[CORPUS_PREFIX]}")
    return before


def _post_json(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError) as err:
        raise RunAbort(f"POST {url}: {err}") from err


def refresh(a: argparse.Namespace) -> None:
    """Reset both models' idle timers with the SAME request `make env-check` uses to load the frozen envelope
    (`/api/generate` with `options.num_ctx`, no prompt; `/api/embed`). The service passes the same
    `options.num_ctx` (rag/src/rag/generate.py), so this does not ask Ollama for a different runner.

    A first version sent a novel QUESTION through the gateway and asserted a MISS. It could not work: every
    such question is the same template, so the first was cached and the rest Tier-2-hit it, refreshing the
    embedder and never the LLM (the shakedown's assert caught it). The guards that matter are kept in
    run_row: `ollama ps` must show the LLM at `num_ctx`, and the runner pids must be unchanged.
    """
    base = f"http://localhost:{a.ollama_port}"
    warm = _post_json(f"{base}/api/generate", {"model": a.llm_tag, "options": {"num_ctx": a.num_ctx}}, 300)
    if not warm.get("done"):
        raise RunAbort(f"refreshing {a.llm_tag} did not complete: {warm}")
    _post_json(f"{base}/api/embed", {"model": a.embed_tag, "input": "footprint-refresh"}, 120)


_FOOTPRINT = re.compile(r"Footprint:\s*([\d.]+)\s*(KB|MB|GB)")


def footprint_mb(pid: int) -> float | None:
    m = _FOOTPRINT.search(run_text(["footprint", "-p", str(pid)]))
    return None if m is None else float(m.group(1)) * {"KB": 1 / 1024, "MB": 1.0, "GB": 1024.0}[m.group(2)]


def parse_vm_stat(text: str) -> dict[str, int]:
    return {m.group(1).strip(): int(m.group(2)) for m in re.finditer(r"^(.+?):\s+(\d+)\.\s*$", text, re.MULTILINE)}


def machine_facts() -> dict:
    out = run_text(["sysctl", "-n", "hw.ncpu", "hw.perflevel0.logicalcpu", "hw.perflevel1.logicalcpu"]).split()
    return {"ncpu": int(out[0]), "perf_cores": int(out[1]), "eff_cores": int(out[2])}


def snapshot(a: argparse.Namespace) -> dict:
    """What is true of the machine at one instant; taken before, after and in the header."""
    return {
        "ollama_ps": run_text(["ollama", "ps"]),
        "vm_stat": parse_vm_stat(run_text(["vm_stat"])),
        "top5_cpu": run_text(["ps", "-Ao", "pcpu=,comm=", "-r"]).splitlines()[:5],
        # one call, no arguments: with -l / -p / <pages> memory_pressure ALLOCATES memory and waits
        "memory_pressure": run_text(["memory_pressure"]).strip().splitlines()[-12:],
        "sysctl": sample_machine(),
    }


def keep_alive_from_log() -> str | None:
    log = Path.home() / ".ollama/logs/server.log"
    if not log.exists():
        return None
    found = re.findall(r"OLLAMA_KEEP_ALIVE:(\S+)", log.read_text(errors="replace"))
    return found[-1] if found else None


def build_header(a: argparse.Namespace, sut: dict[str, int]) -> dict:
    git = lambda *argv: run_text(["git", *argv], cwd=ROOT).strip()
    return {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "git_sha": git("rev-parse", "HEAD"),
        "tree_dirty": bool(git("status", "--porcelain")),
        "sut_dirty": bool(git("status", "--porcelain", "--", "gateway", "rag")),   # the SUT, not the sampler
        "k6_version": run_text(["k6", "version"]).strip().splitlines()[0],
        "sampler_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "ask_js_sha256": hashlib.sha256(K6_SCRIPT.read_bytes()).hexdigest(),
        "machine": machine_facts(),
        "ollama_keep_alive": keep_alive_from_log(),
        "args": {k: v for k, v in vars(a).items() if k != "func"},
        "sut_pids": sut,
        "before": snapshot(a),
    }


def make_workload(path: Path, variants: int = 300, seed: int = 1) -> int:
    """The 5 smoke questions plus `variants` seeded, uniquely suffixed variants of them. The smoke set
    comes first, so a Zipf draw's head is the smoke set; the tail are first sightings that Tier-2-hit or
    MISS. Nothing here is read from data/."""
    rng = random.Random(seed)
    pool = [f"{q} for the {c} {s} one" for q in SMOKE_QUESTIONS for c in _COLOURS for s in _SIZES]
    rng.shuffle(pool)
    if len(pool) < variants:
        raise ValueError(f"only {len(pool)} distinct variants available, {variants} asked for")
    items = [{"question": q} for q in [*SMOKE_QUESTIONS, *pool[:variants]]]
    path.write_text(json.dumps(items, indent=0) + "\n")
    return len(items)


def workload_arg(out: Path) -> str:
    """The mixed workload's path as k6 must be given it: ABSOLUTE. k6 resolves `open()` relative to the
    SCRIPT's directory (experiments/k6/), not the caller's cwd, so a relative --out hands it a file that
    does not exist. The recorded run's three mixed rows died on exactly this (k6 exit 107); the shakedown
    used an absolute --out and did not catch it."""
    return str((out / "workload-mixed.json").resolve())


def k6_numbers(summary_path: Path, duration: int) -> dict:
    """From `--summary-export`. Counters never added to are ABSENT (probes.md U4), so default every count to 0."""
    m = json.loads(summary_path.read_text())["metrics"]

    def count(name: str) -> int:
        return int(m.get(name, {}).get("count", 0))

    return {
        "iterations": count("iterations"), "dropped": count("dropped_iterations"),
        "vus_max": int(m["vus_max"]["max"]), "error_rate": float(m["error_rate"]["value"]),
        "shed": int(m["shed_rate"]["passes"]),
        "tier1": count("cache_tier1_hit"), "tier2": count("cache_tier2_hit"), "miss": count("cache_miss"),
        "achieved_rate": count("iterations") / duration,
    }


def sampler_overhead_pct(self_cpu_s: float, children_cpu_s: float, k6_cpu_s: float, wall_s: float) -> float:
    """The instrument's own cost over a row, % of one core: what this process and every child it reaped spent
    (`ps`, `sysctl`, `footprint`, and k6 itself, whose rusage `wait4` adds to RUSAGE_CHILDREN), minus k6's exact
    total. Without the subtraction the instrument would be charged with the generator's cost."""
    return 100.0 * (self_cpu_s + children_cpu_s - k6_cpu_s) / wall_s


def run_row(a: argparse.Namespace, kind: str, rate: int, rep: int, sut: dict[str, int], out: Path) -> dict:
    tag = f"{kind}-r{rate}-rep{rep}"
    now = resolve_sut(a)
    flags = [] if now == sut else ["sut_pid_changed"]       # a changed runner pid is a silent model reload (F10)
    # each mixed rep is a COLD start (seeded workload): the cache keys are deleted, which `run` announces and
    # `--no-flush` refuses to combine with --mixed
    cache_before = flush_cache(port=a.redis_port) if kind == "mixed" else None
    refresh(a)
    ps_before = assert_models_loaded(a)
    vm0 = parse_vm_stat(run_text(["vm_stat"]))
    roles = list(now)
    sut_fp_before = {r: footprint_mb(now[r]) for r in roles}
    summary = out / f"k6-summary-{tag}.json"
    argv = ["k6", "run", "-e", f"GATEWAY_URL={a.gateway_url}", "-e", f"RATE_RPS={rate}", "-e", f"VUS={a.vus}",
            "-e", f"DURATION={a.duration}s", "--summary-export", str(summary)]
    if kind == "mixed":
        argv += ["-e", f"WORKLOAD={workload_arg(out)}"]
    argv.append(str(K6_SCRIPT))

    probes: list[dict] = []
    due = [10.0, max(10.0, a.duration - 10.0)]

    def probe(tick: Tick) -> None:                 # footprint costs 30-100 ms: twice a row, never at 1 Hz
        if due and tick.t >= due[0]:
            due.pop(0)
            probes.append({"t": round(tick.t, 1), "k6_phys_footprint_mb": footprint_mb(tick.pid)})

    self0, kids0 = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    result = run_child(
        argv, interval=a.interval, stdout=str(out / f"k6-stdout-{tag}.txt"), stderr=str(out / f"k6-stderr-{tag}.txt"),
        extra_pids=tuple(now[r] for r in roles), extra_every=a.sut_every, machine=True, expect_comm="k6", on_tick=probe,
    )
    self1, kids1 = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)

    def cpu(r: resource.struct_rusage) -> float:
        return r.ru_utime + r.ru_stime

    overhead_pct = sampler_overhead_pct(cpu(self1) - cpu(self0), cpu(kids1) - cpu(kids0), result.rusage_cpu_s, result.wall_s)

    csv_path = out / f"samples-{tag}.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t", "k6_cpu_s", "k6_rss_kb", "vm_pressure_level", "memstatus_level", "swap_used_mb",
                    *[f"{r}_{c}" for r in roles for c in ("cpu_s", "rss_kb")]])
        for t in result.ticks:
            w.writerow([f"{t.t:.3f}", t.cpu_s, t.rss_kb, t.machine.get("vm_pressure_level"),
                        t.machine.get("memstatus_level"), t.machine.get("swap_used_mb"),
                        *[v for r in roles for v in t.extra.get(now[r], ("", ""))]])
    numbers = k6_numbers(summary, a.duration) if summary.exists() else None
    if numbers is None:
        flags.append("no_k6_summary")
    meta = {
        "tag": tag, "kind": kind, "rate_offered": rate, "rep": rep, "duration_s": a.duration, "vus": a.vus,
        "csv": csv_path.name, "k6": numbers, "exit_status": result.exit_status,
        "rusage_cpu_s": result.rusage_cpu_s, "maxrss_bytes": result.maxrss_bytes, "wall_s": result.wall_s,
        "discarded_ticks": result.discarded_ticks, "flags": [*flags, *result.flags],
        "sampler_overhead_pct": overhead_pct, "k6_footprint_probes": probes,
        "sut_footprint_mb_before": sut_fp_before, "sut_footprint_mb_after": {r: footprint_mb(now[r]) for r in roles},
        "cache_keys_before_flush": cache_before, "vm_stat_before": vm0, "vm_stat_after": parse_vm_stat(run_text(["vm_stat"])),
        "ollama_ps_before": ps_before, "ollama_ps_after": run_text(["ollama", "ps"]), "sut_pids": now,
    }
    (out / f"run-{tag}.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def check_args(a: argparse.Namespace) -> None:
    """Refuse an incoherent combination before touching anything."""
    if a.no_flush and a.mixed:
        raise RunAbort("--no-flush cannot be combined with --mixed: a mixed repetition must start from a cold cache")
    if not [r for r in a.rates.split(",") if r.strip()] and not a.mixed:
        raise RunAbort("nothing to run: --rates is empty and --mixed is off")


def cmd_run(a: argparse.Namespace) -> int:
    check_args(a)
    install_signal_handlers()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if any(out.glob("run-*.json")):
        raise RunAbort(f"{out} already holds a run; a footprint run is never overwritten, use a new --out")
    if run_text(["pgrep", "-x", "k6"]).split():
        raise RunAbort("a k6 process is already running; it would be sampled as if it were this run's")
    # The warm-up comes FIRST: it is what loads the models (through the gateway, with the repo's own
    # options), and the runners that resolve_sut looks for do not exist until they are loaded.
    if a.no_flush:
        start_cache = None
    else:
        print("flushing the cache keys t1: t2: lru: (never corpus:, never the dependency region) on "
              f"redis :{a.redis_port} for a cold start; use --no-flush to refuse", flush=True)
        start_cache = flush_cache(port=a.redis_port)  # a cold start: leftovers of an earlier run must not leak in
    warm_up(a)
    assert_models_loaded(a)
    sut = resolve_sut(a)
    header = build_header(a, sut)
    header["cache_keys_before_start_flush"] = start_cache
    (out / "header.json").write_text(json.dumps(header, indent=2) + "\n")
    rates = [int(r) for r in a.rates.split(",") if r.strip()]       # empty --rates + --mixed: the mixed row alone
    plan = [("allhit", r, rep) for r in rates for rep in range(1, a.reps + 1)]
    if a.mixed:
        make_workload(out / "workload-mixed.json", a.variants, a.seed)
        plan += [("mixed", a.mixed_rate, rep) for rep in range(1, a.reps + 1)]
    for i, (kind, rate, rep) in enumerate(plan):
        print(f"[{i + 1}/{len(plan)}] {kind} {rate} req/s rep {rep} ({a.duration} s)", flush=True)
        run_row(a, kind, rate, rep, sut, out)
        time.sleep(a.cooldown)
    (out / "header-after.json").write_text(json.dumps(snapshot(a), indent=2) + "\n")
    print(summarize_dir(out))
    excluded = count_excluded(out)
    if excluded:
        print(f"WARNING -- {excluded} row(s) were EXCLUDED from the table (see 'Rows left out'); exit status 4", file=sys.stderr)
        return 4
    return 0


def count_excluded(directory: Path) -> int:
    return len(json.loads((Path(directory) / "summary.json").read_text())["excluded"])


# --- from the CSVs to the table -----------------------------------------------------------------------


def load_ticks(path: Path) -> tuple[
    list[Tick], dict[str, list[float]], dict[str, list[tuple[float, float]]], dict[str, list[float]]
]:
    """The k6 ticks, the raw memory readings, each SUT process's (t, cumulative CPU) series and its resident
    set in KiB (sampled every Nth tick, so the others are blank in the CSV and skipped here)."""
    ticks: list[Tick] = []
    zone: dict[str, list[float]] = {"vm_pressure_level": [], "memstatus_level": [], "swap_used_mb": []}
    sut: dict[str, list[tuple[float, float]]] = {}
    sut_rss: dict[str, list[float]] = {}
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        roles = [c[: -len("_cpu_s")] for c in (reader.fieldnames or []) if c.endswith("_cpu_s") and c != "k6_cpu_s"]
        for row in reader:
            t = float(row["t"])
            ticks.append(Tick(t=t, cpu_s=float(row["k6_cpu_s"]), rss_kb=int(row["k6_rss_kb"]), stat="R"))
            for k, values in zone.items():
                if row[k] not in ("", "None"):
                    values.append(float(row[k]))
            for role in roles:
                if row[f"{role}_cpu_s"] not in ("", "None"):
                    sut.setdefault(role, []).append((t, float(row[f"{role}_cpu_s"])))
                if row.get(f"{role}_rss_kb", "") not in ("", "None"):
                    sut_rss.setdefault(role, []).append(float(row[f"{role}_rss_kb"]))
    return ticks, zone, sut, sut_rss


def sut_cpu_pct(series: list[tuple[float, float]], lo: float, hi: float) -> float | None:
    """A SUT process's mean CPU over [lo, hi], % of one core, from its sparse cumulative samples."""
    window = [(t, c) for t, c in series if lo <= t <= hi]
    if len(window) < 2 or window[-1][0] <= window[0][0]:
        return None
    return 100.0 * (window[-1][1] - window[0][1]) / (window[-1][0] - window[0][0])


def record_from(meta: dict, ticks: list[Tick]) -> RunRecord:
    """Everything derived is recomputed from the samples; nothing is trusted from a stored summary."""
    flags = list(meta["flags"])
    try:
        mean = window_mean(ticks, WINDOW_HEAD_S, WINDOW_TAIL_S)
    except ValueError:
        mean = 0.0
        flags.append("no_steady_window")
    window = [t for t in ticks if WINDOW_HEAD_S <= t.t <= ticks[-1].t - WINDOW_TAIL_S] if ticks else []
    per_tick = per_tick_pct(window)
    k6 = meta["k6"] or {}
    return RunRecord(
        kind=meta["kind"], rate_offered=float(meta["rate_offered"]), rep=meta["rep"],
        achieved_rate=k6.get("achieved_rate", 0.0), cpu_pct_mean=mean, rss_peak_bytes=meta["maxrss_bytes"],
        rusage_cpu_s=meta["rusage_cpu_s"], sampled_cpu_s=ticks[-1].cpu_s if ticks else 0.0,
        exit_status=meta["exit_status"], error_rate=k6.get("error_rate", 1.0), shed=k6.get("shed", 0),
        miss=k6.get("miss", 0), vus_max=k6.get("vus_max", 0), tier1=k6.get("tier1", 0), tier2=k6.get("tier2", 0),
        dropped=k6.get("dropped", 0), discarded_ticks=meta.get("discarded_ticks", 0), n_ticks=len(ticks),
        cpu_pct_p95=percentile(per_tick, 95) if per_tick else 0.0,
        cpu_pct_max=max(per_tick) if per_tick else 0.0, sampler_overhead_pct=meta["sampler_overhead_pct"],
        flags=flags,
    )


def _mb(n: float) -> str:
    return f"{n / 1e6:.0f}"


def summarize_dir(directory: Path, ncpu: int | None = None) -> str:
    directory = Path(directory)
    header = json.loads((directory / "header.json").read_text()) if (directory / "header.json").exists() else {}
    ncpu = ncpu or header.get("machine", {}).get("ncpu")
    if not ncpu:
        raise RunAbort("no header.json with machine.ncpu and no --ncpu: the % of machine divisor would be a guess")
    records, zone_rows, sliding, sut_cpu, llm_rss = [], [], {}, {}, {}
    for meta_path in sorted(directory.glob("run-*.json")):
        meta = json.loads(meta_path.read_text())
        ticks, zone, sut, sut_rss = load_ticks(directory / meta["csv"])
        record = record_from(meta, ticks)
        llm = sut_rss.get("llm_runner")
        llm_rss[meta["tag"]] = (min(llm) / 1024, max(llm) / 1024) if llm else None
        hi = ticks[-1].t - WINDOW_TAIL_S if ticks else 0.0
        sut_cpu[meta["tag"]] = {role: sut_cpu_pct(series, WINDOW_HEAD_S, hi) for role, series in sut.items()}
        records.append(record)
        window = [t for t in ticks if WINDOW_HEAD_S <= t.t <= ticks[-1].t - WINDOW_TAIL_S] if ticks else []
        s5 = sliding_pct(window, 5.0)
        sliding[meta["tag"]] = (percentile(s5, 95), max(s5)) if s5 else (0.0, 0.0)
        vm0, vm1 = meta["vm_stat_before"], meta["vm_stat_after"]
        zone_rows.append((meta, zone, {k: vm1.get(k, 0) - vm0.get(k, 0) for k in ("Swapins", "Swapouts", "Pageins", "Pageouts")}))
    table = summarise(records, ncpu)
    lines = [
        "# Load-generator footprint — item 1.6",
        "",
        "> **EXPLORATORY and INDICATIVE, unconditionally** (ADR-001). Memory pressure was recorded, never gated; the",
        "> run is classified exploratory under standing constraint 4. Nothing here is a thesis result, and the",
        "> Phase 7 p95 rule does not read this table: every co-hosted p95 is reported with k6's own concurrent CPU.",
        "",
        (
            f"Gateway/rag git SHA `{header.get('git_sha', '?')[:12]}` · tree dirty: {header.get('tree_dirty')} · "
            f"**gateway/rag dirty: {header.get('sut_dirty')}** · {header.get('k6_version', '?')} · "
            f"{ncpu} logical cores ({header.get('machine', {}).get('perf_cores')} P + "
            f"{header.get('machine', {}).get('eff_cores')} E) · "
            f"`OLLAMA_KEEP_ALIVE` {header.get('ollama_keep_alive')}"
        ),
        "",
        (
            f"Steady-state window: the ticks from {WINDOW_HEAD_S:g} s after the child started to {WINDOW_TAIL_S:g} s "
            "before its last tick (49 – 50 s of a 60 s run; the endpoints are tick times, which jitter). CPU is "
            "**% of one core** (100 = one core) and, beside it, % of the whole machine (a coarse divisor: the cores "
            "are not equal). RSS is `ru_maxrss` in 10^6 bytes, a floor under pressure; `phys_footprint` is as "
            "`footprint` reports it (MiB) and is read twice per row, so the figure shown is the larger of two spot "
            "readings, not an exact peak."
        ),
        "",
    ]
    for kind, title in (("allhit", "All-hit regime (the 5-question smoke set after warm-up; Ollama idle)"),
                        ("mixed", "Mixed regime (Zipf over the smoke set + 300 suffixed variants; Tier-2, misses and sheds occur)")):
        rows = [r for r in table.rows if r.kind == kind]
        if not rows:
            continue
        lines += [f"## {title}", "",
                  "| offered req/s | reps | achieved | k6 CPU mean (% core) | spread over reps | % machine | RSS peak MB | vus_max | sampler overhead (% core) |",
                  "| ---: | ---: | ---: | ---: | :--- | ---: | ---: | ---: | ---: |"]
        for r in rows:
            lines.append(f"| {r.rate_offered:g} | {r.reps} | {r.achieved_rate:.2f} | {r.cpu_pct_mean:.2f} | "
                         f"{r.cpu_pct_min:.2f} – {r.cpu_pct_max:.2f} | {r.cpu_pct_of_machine:.3f} | "
                         f"{_mb(r.rss_peak_bytes)} | {r.vus_max} | {r.sampler_overhead_pct:.2f} |")
        lines.append("")
    if table.fit:
        a_, b_ = table.fit
        lines += [
            (
                f"**All-hit fit:** CPU % = **{a_:.2f}** (fixed cost, intercept) + **{b_:.3f}** × achieved req/s "
                f"(marginal cost, slope; {b_ / 100:.4f} CPU-seconds per request). Total ÷ N is not used: at low "
                "rates the fixed start-up cost per request exceeds the marginal one."
            ),
            "",
        ]
    lines += ["## Per run", "",
              "| run | status | k6 CPU mean | p95 / max per 1 s (quantised) | p95 / max over 5 s | RSS MB | footprint probes MB | dropped | T1 / T2 / MISS | shed | exit | discarded ticks | flags |",
              "| :--- | :--- | ---: | :--- | :--- | ---: | :--- | ---: | :--- | ---: | ---: | ---: | :--- |"]
    sut_lines = ["", "## SUT processes' CPU over the same window (% of one core; sampled every 5th tick)", "",
                 "| run | gateway | rag.server | redis | ollama serve | LLM runner | embed runner | SUT total | LLM runner RSS MiB (min – max) |",
                 "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |"]
    flagged = {id(r): f for r, f in table.excluded}
    metas = {m["tag"]: m for m, _, _ in zone_rows}
    for rec in records:
        tag = f"{rec.kind}-r{int(rec.rate_offered)}-rep{rec.rep}"
        p5 = sliding.get(tag, (0.0, 0.0))
        fp = ", ".join(f"{p['k6_phys_footprint_mb']:.0f}" for p in metas[tag]["k6_footprint_probes"] if p["k6_phys_footprint_mb"])
        lines.append(f"| {tag} | {'EXCLUDED' if id(rec) in flagged else 'kept'} | {rec.cpu_pct_mean:.2f} | "
                     f"{rec.cpu_pct_p95:.1f} / {rec.cpu_pct_max:.1f} | {p5[0]:.1f} / {p5[1]:.1f} | "
                     f"{_mb(rec.rss_peak_bytes)} | {fp or '—'} | {rec.dropped} | {rec.tier1} / {rec.tier2} / {rec.miss} | "
                     f"{rec.shed} | {rec.exit_status} | {rec.discarded_ticks} | {', '.join(flagged.get(id(rec), [])) or '—'} |")
    for tag, per_role in sut_cpu.items():
        vals = [per_role.get(r) for r in ("gateway", "rag_server", "redis", "ollama_serve", "llm_runner", "embed_runner")]
        total = sum(v for v in vals if v is not None) if any(v is not None for v in vals) else None
        cells = ["—" if v is None else f"{v:.1f}" for v in vals]
        span_rss = llm_rss.get(tag)
        rss_cell = "—" if span_rss is None else f"{span_rss[0]:.0f} – {span_rss[1]:.0f}"
        sut_lines.append(f"| {tag} | {' | '.join(cells)} | {'—' if total is None else f'{total:.1f}'} | {rss_cell} |")
    lines += sut_lines
    lines += ["", "## Rows left out of the table", ""]
    lines += [f"- `{r.kind}-r{int(r.rate_offered)}-rep{r.rep}`: {', '.join(f)}" for r, f in table.excluded] or ["- none"]
    lines += ["", "## SUT memory readings, raw (never mapped to a colour: the sysctl's encoding is unverified)", "",
              "| run | pressure level (min–max) | memstatus_level (min–max) | swap used MB (min–max) | swap-ins / swap-outs | page-ins / page-outs |",
              "| :--- | :--- | :--- | :--- | :--- | :--- |"]
    for meta, zone, delta in zone_rows:
        def span(key: str, zone=zone) -> str:
            return f"{min(zone[key]):g} – {max(zone[key]):g}" if zone[key] else "—"
        lines.append(f"| {meta['tag']} | {span('vm_pressure_level')} | {span('memstatus_level')} | {span('swap_used_mb')} | "
                     f"{delta['Swapins']} / {delta['Swapouts']} | {delta['Pageins']} / {delta['Pageouts']} |")
    lines += ["", "## Not settled by this run", "",
              ("- `ABANDONED` and `GENERATION_FAILED` counts are **vacuous for the all-hit regime** (nothing waits on a "
               "generation, so nothing reaches k6's 120 s timeout); they do not settle F-L or the k6-cancel question."),
              ("- CPU share is **not an interference measurement**: it does not measure cache, memory-bandwidth or "
               "scheduler contention against the embedding server."),
              ""]
    (directory / "footprint.md").write_text("\n".join(lines))
    (directory / "summary.json").write_text(json.dumps({
        "fit": table.fit, "rows": [asdict(r) for r in table.rows],
        "excluded": [{"run": asdict(r), "flags": f} for r, f in table.excluded]}, indent=2) + "\n")
    return str(directory / "footprint.md")


def cmd_count_log(a: argparse.Namespace) -> int:
    """After the gateway has stopped (so its log is closed): size, hash and outcome counts of its eval log.
    The log itself holds PQA-derived text and is not committed; only these derived counts are."""
    path = Path(a.log)
    blob = path.read_bytes()
    counts: dict[str, int] = {}
    shed = 0
    for line in blob.decode().splitlines():
        rec = json.loads(line)
        counts[rec["cache"] or "(empty)"] = counts.get(rec["cache"] or "(empty)", 0) + 1
        shed += bool(rec.get("shed"))
    Path(a.out).write_text(json.dumps({"lines": len(blob.decode().splitlines()), "sha256": hashlib.sha256(blob).hexdigest(),
                                        "by_cache": counts, "shed": shed}, indent=2) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="drive k6 under the sampler")
    run.add_argument("--rates", default="2,8,16,32")
    run.add_argument("--duration", type=int, default=60)
    run.add_argument("--reps", type=int, default=3)
    run.add_argument("--vus", type=int, default=40)
    run.add_argument("--mixed", action="store_true", help="add the mixed-workload row (spec decision 10)")
    run.add_argument("--mixed-rate", type=int, default=8)
    run.add_argument("--variants", type=int, default=300)
    run.add_argument("--seed", type=int, default=1)
    run.add_argument("--interval", type=float, default=1.0)
    run.add_argument("--cooldown", type=float, default=10.0)
    run.add_argument("--no-flush", action="store_true", help="do not delete the cache keys (refused with --mixed)")
    run.add_argument("--sut-every", type=int, default=5,
                     help="sample the SUT processes every Nth tick (k6 and the memory sysctls are sampled every tick)")
    run.add_argument("--gateway-url", default="http://localhost:8080")
    run.add_argument("--gateway-port", type=int, default=8080)
    run.add_argument("--rag-port", type=int, default=50051)
    run.add_argument("--redis-port", type=int, default=6379)
    run.add_argument("--ollama-port", type=int, default=11434)
    run.add_argument("--llm-blob", required=True, help="pinned sha256-… of the LLM weights (Makefile LLM_BLOB)")
    run.add_argument("--llm-tag", default="qwen3.5:2b-q4_K_M")
    run.add_argument("--embed-tag", default="nomic-embed-text")
    run.add_argument("--num-ctx", type=int, default=8192, help="the frozen num_ctx (rag/src/rag/config.py)")
    run.add_argument("--out", required=True)
    run.set_defaults(func=cmd_run)
    summ = sub.add_parser("summarize", help="regenerate footprint.md from the per-second CSVs")
    summ.add_argument("--dir", required=True)
    summ.add_argument("--ncpu", type=int, default=None, help="needed only when the run's header.json is missing")
    summ.set_defaults(func=lambda a: print(summarize_dir(Path(a.dir), a.ncpu)) or 0)
    wl = sub.add_parser("make-workload", help="write the seeded mixed workload JSON")
    wl.add_argument("--out", required=True)
    wl.add_argument("--variants", type=int, default=300)
    wl.add_argument("--seed", type=int, default=1)
    wl.set_defaults(func=lambda a: print(make_workload(Path(a.out), a.variants, a.seed)) or 0)
    fc = sub.add_parser("flush-cache", help="delete the cache keys (t1: t2: lru:); refuses if dep:/entry: exist; never corpus:")
    fc.add_argument("--redis-port", type=int, default=6379)
    fc.set_defaults(func=lambda a: print(json.dumps(flush_cache(port=a.redis_port))) or 0)
    cl = sub.add_parser("count-log", help="size, sha256 and outcome counts of the gateway's closed eval log")
    cl.add_argument("--log", required=True)
    cl.add_argument("--out", required=True)
    cl.set_defaults(func=cmd_count_log)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except RunAbort as err:
        print(f"ABORT — {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
