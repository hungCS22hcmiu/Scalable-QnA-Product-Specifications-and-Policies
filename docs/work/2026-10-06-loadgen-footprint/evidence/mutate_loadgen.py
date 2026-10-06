"""Mutation check for the sampler self-test (item 1.6, plan step 3).

A suite that passes on its first run proves little until it is shown to FAIL when the instrument is wrong.
Each mutant below plants one of the silent failures design.md §6 names, runs only the tests that are meant
to catch it, and reports whether they did. The real module is restored byte-for-byte afterwards (verified
by sha256), and the script refuses to start if the restore point cannot be made.

    python3 docs/work/2026-10-06-loadgen-footprint/evidence/mutate_loadgen.py
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "experiments/scripts/loadgen_footprint.py"
TESTS = ROOT / "experiments/tests/test_loadgen_footprint.py"

# (name, old text, new text, pytest -k selector for the tests that should catch it)
MUTANTS = [
    ("CPU reads 2x (the ps %cpu class)",
     "return 100.0 * (window[-1].cpu_s", "return 200.0 * (window[-1].cpu_s", "cpu_matches"),
    ("ru_maxrss treated as KB (1024x)",
     "maxrss_bytes=usage.ru_maxrss,", "maxrss_bytes=usage.ru_maxrss * 1024,", "peak_rss"),
    ("exit status taken as Popen reports it (0)",
     "exit_status=os.waitstatus_to_exitcode(reaped[1]),", "exit_status=0,", "exit_status_comes"),
    ("cputime M:SS read as H:MM (60x)",
     "hours, minutes, seconds = 0, int(parts[0]), float(parts[1])",
     "hours, minutes, seconds = int(parts[0]), int(parts[1]), 0.0", "parse_cputime"),
    ("no kill on abnormal exit",
     "os.killpg(pid, signal.SIGKILL)", "pass", "orphan"),
    ("signal handlers do nothing",
     "raise Interrupted(128 + signum)", "return", "sigterm"),
    ("unattained rule inverted",
     "if run.achieved_rate < ATTAINED * run.rate_offered:",
     "if run.achieved_rate > ATTAINED * run.rate_offered:", "summarise"),
    ("zombie / backwards ticks kept",
     "if row.stat.startswith(\"Z\") or (ticks and row.cpu_s < ticks[-1].cpu_s):", "if False:", "discarded"),
    ("a vanished child is not recognised as the child",
     "if pid in gone.pids:", "if False:", "discarded"),
    ("sampler imports rag",
     "import math\n", "import math\nimport rag.config  # noqa\n", "importing_the_sampler"),
    # --- added after the AI review of 2026-10-07: faults the first ten did not plant
    ("steady-state window has no head trim",
     "WINDOW_HEAD_S = 5.0", "WINDOW_HEAD_S = 0.0", "window_is_pinned"),
    ("steady-state window has no tail trim",
     "WINDOW_TAIL_S = 5.0", "WINDOW_TAIL_S = 0.0", "window_is_pinned"),
    ("sample_machine reads the wrong field for swap",
     '"swap_used_mb": float(swap.group(1)),', '"swap_used_mb": float(out[1]),', "sample_machine"),
    ("sample_ps treats a missing pid as a gap",
     "    if missing:\n        raise ProcessGone(missing, rows)", "    if False:\n        raise ProcessGone(missing, rows)", "sample_ps"),
    ("errors in the mixed regime no longer exclude a row",
     "    elif run.error_rate >= ERROR_RATE_LIMIT:", "    elif False:", "errors_in_the_mixed"),
    ("RSS column uses the wrong divisor",
     'return f"{n / 1e6:.0f}"', 'return f"{n / 1e3:.0f}"', "decimal_megabytes"),
    ("sampler overhead is not net of k6's own CPU",
     "return 100.0 * (self_cpu_s + children_cpu_s - k6_cpu_s) / wall_s",
     "return 100.0 * (self_cpu_s + children_cpu_s) / wall_s", "overhead"),
    ("the LLM and embedding runner roles are swapped",
     'and Path(command.split()[0]).name == "llama-server" and pid != llm_pid:',
     'and Path(command.split()[0]).name == "llama-server" and pid == llm_pid:', "embedding_runner"),
    ("the flush deletes the dependency region",
     "    if guarded:\n        raise RunAbort(", "    if False:\n        raise RunAbort(", "dependency_region"),
    ("a wrong process (a wrapper) is not flagged",
     "if comm != expect_comm:", "if False:", "not_the_expected"),
    ("many discarded ticks do not exclude a run",
     "if run.n_ticks and run.discarded_ticks > DISCARD_LIMIT * (run.n_ticks + run.discarded_ticks):",
     "if False:", "left_out_when_the_sampler"),
    ("sampled CPU far below wait4's total does not exclude a run",
     "if run.rusage_cpu_s > 0.5 and run.sampled_cpu_s < SAMPLED_FLOOR * run.rusage_cpu_s:",
     "if False:", "left_out_when_the_sampler"),
    ("the flush ignores --redis-port",
     'lambda *argv: run_text(["redis-cli", "-p", str(port), *argv])',
     'lambda *argv: run_text(["redis-cli", *argv])', "redis_port"),
    ("--no-flush with --mixed is accepted",
     "    if a.no_flush and a.mixed:", "    if False:", "incoherent"),
    ("summarize guesses the core count",
     "    if not ncpu:", "    if False:", "core_count"),
]


# Python reuses cached bytecode when the source's mtime (in whole seconds) and size match. Two mutants that
# shorten the file by the same number of characters, written within one second, then run on the FIRST one's
# bytecode: a mutant is "caught" or "survives" on the wrong code. (Found 2026-10-07: "--no-flush" survived in a
# full run and was caught alone.) So bytecode is off and the cache is emptied before every run.
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def clear_bytecode():
    for pyc in (ROOT / "experiments/scripts/__pycache__").glob("loadgen_footprint*.pyc"):
        pyc.unlink()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selectors_pass_on_the_original():
    """A selector that matches no test exits 5, and a test that fails for an unrelated reason exits 1; either
    would be counted as a mutant 'caught'. So every selector must pass, and select something, on the original."""
    bad = []
    for selector in sorted({m[3] for m in MUTANTS}):
        run = subprocess.run(
            [sys.executable, "-m", "pytest", str(TESTS), "-q", "-x", "-k", selector, "-p", "no:cacheprovider"],
            capture_output=True, text=True, cwd=ROOT, check=False, env=ENV,
        )
        if run.returncode != 0:
            bad.append((selector, run.returncode))
    return bad


def main():
    bad = selectors_pass_on_the_original()
    if bad:
        print(f"REFUSING TO RUN: these selectors do not pass (or select nothing) on the unmodified module: {bad}")
        sys.exit(2)
    backup = Path(tempfile.mkdtemp()) / TARGET.name
    shutil.copy2(TARGET, backup)
    original = sha(TARGET)
    survived = []
    try:
        only = sys.argv[1] if len(sys.argv) > 1 else None          # run just the mutants whose name contains this
        for name, old, new, selector in MUTANTS:
            if only and only not in name:
                continue
            text = backup.read_text()
            if text.count(old) != 1:
                print(f"SKIP   {name}: pattern matches {text.count(old)} times (the module changed)")
                survived.append(name + " (unplanted)")
                continue
            TARGET.write_text(text.replace(old, new))
            clear_bytecode()
            run = subprocess.run(
                [sys.executable, "-m", "pytest", str(TESTS), "-q", "-x", "-k", selector, "-p", "no:cacheprovider"],
                capture_output=True, text=True, cwd=ROOT, check=False, env=ENV,
            )
            caught = run.returncode == 1          # 1 = a test FAILED; 5 (nothing selected) or 2 (error) is not a catch
            print(f"{'caught ' if caught else 'SURVIVED'} {name}  [-k {selector}]")
            if not caught:
                survived.append(name)
                print(f"    returncode {run.returncode}; last output:\n    " + run.stdout[-500:].replace("\n", "\n    "))
    finally:
        shutil.copy2(backup, TARGET)
        clear_bytecode()
        assert sha(TARGET) == original, "restore failed: the module is NOT byte-identical to the original"
    print(f"\n{len(MUTANTS) - len(survived)}/{len(MUTANTS)} caught; module restored (sha256 {original[:16]}…)")
    sys.exit(1 if survived else 0)


if __name__ == "__main__":
    main()
