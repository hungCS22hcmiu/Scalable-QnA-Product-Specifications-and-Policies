"""The sampler's self-test (item 1.6, design.md §8; standing constraint 6: no measurement runs off an
untested instrument).

The ground truth for CPU is what the child reports about itself (`time.process_time()`), not a duty-cycle
estimate, so no test depends on a burner hitting its nominal percentage. Tolerances are relative ±25 %,
sized to catch the failure modes this instrument can have silently -- 2x (`ps %cpu`), 60x (a cputime
parser that assumes HH:MM:SS), 1024x (`ru_maxrss` units), ~41.7x (Mach ticks) -- and deliberately not
tight, so the suite does not flake under memory pressure. Total runtime is a few tens of seconds.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import loadgen_footprint as lf
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

# A burner whose CPU the child reports about itself. Bounded in runtime so an interrupted test cannot
# leave a CPU-eater behind (design.md F13).
BURNER = r"""
import json, os, sys, time
mode, seconds, report, pidfile = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4]
open(pidfile, "w").write(str(os.getpid()))
t_start = time.monotonic()
t_end = t_start + seconds
if mode == "busy":
    while time.monotonic() < t_end:
        pass
elif mode.startswith("duty"):
    on, period = float(mode[4:]), 0.02
    while time.monotonic() < t_end:
        t = time.monotonic()
        while time.monotonic() - t < on * period:
            pass
        time.sleep((1 - on) * period)
elif mode == "alloc":
    block = os.urandom(100_000_000)      # incompressible, and fully written, so it is resident
    time.sleep(seconds)
elif mode == "exit99":
    time.sleep(seconds)
    json.dump({"cpu": time.process_time(), "wall": time.monotonic() - t_start}, open(report, "w"))
    sys.exit(99)
json.dump({"cpu": time.process_time(), "wall": time.monotonic() - t_start}, open(report, "w"))
"""


def burner(tmp_path, mode, seconds):
    report, pidfile = tmp_path / "report.json", tmp_path / "pid"
    return [sys.executable, "-c", BURNER, mode, str(seconds), str(report), str(pidfile)], report, pidfile


def self_reported_cpu(report):
    return json.loads(report.read_text())["cpu"]


def self_reported_pct(report):
    """The child's own CPU over its own wall clock, as % of one core. `run_child` only notices the child
    has gone at the next tick, so its `wall_s` can overstate by up to one interval; the child's own
    account does not have that error."""
    r = json.loads(report.read_text())
    return 100.0 * r["cpu"] / r["wall"]


def within(measured, expected, rel=0.25, floor_pp=0.0):
    return abs(measured - expected) <= max(rel * expected, floor_pp)


def gone(pid, wait=3.0):
    """True once `pid` no longer exists (and is not a zombie)."""
    end = time.monotonic() + wait
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        stat = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
        ).stdout
        if stat.strip() == "":
            return True
        time.sleep(0.1)
    return False


# --- T1-T3: CPU, against the child's own account of itself -------------------------------------------


@pytest.mark.parametrize(
    "mode, seconds, floor_pp",
    [
        ("busy", 5, 0.0),        # T1  ~100 % of one core
        ("duty0.5", 6, 0.0),     # T2  ~50 %
        ("duty0.03", 8, 1.0),    # T3  ~3 %: the regime k6 is in at 2 req/s, where 1 cs is ~1 % of a core
    ],
)
def test_cpu_matches_what_the_child_reports_about_itself(tmp_path, mode, seconds, floor_pp):
    argv, report, _ = burner(tmp_path, mode, seconds)
    run = lf.run_child(argv, interval=0.5)
    assert run.exit_status == 0
    expected = self_reported_pct(report)
    measured = lf.window_mean(run.ticks, trim_head=1.0, trim_tail=1.0)
    assert within(measured, expected, floor_pp=floor_pp), (measured, expected)
    # the exact total from wait4 must also agree with the child's own account
    assert within(run.rusage_cpu_s, self_reported_cpu(report), floor_pp=0.05)


# --- T4: peak RSS, and the bytes-vs-KB trap ----------------------------------------------------------


def test_peak_rss_is_reported_in_bytes_for_a_known_incompressible_block(tmp_path):
    argv, _, _ = burner(tmp_path, "alloc", 3)
    run = lf.run_child(argv, interval=0.5)
    mb = run.maxrss_bytes / 1e6
    # 100 MB block + interpreter. A KB/bytes mix-up is off by 1024x and cannot land here.
    assert 80 <= mb <= 150, mb
    assert max(t.rss_kb for t in run.ticks) / 1e3 >= 60       # ps agrees it was resident (a floor)


# --- T5: the exit code must come from wait4, not from Popen ------------------------------------------


def test_exit_status_comes_from_wait4_not_popen_and_ticks_are_monotone(tmp_path):
    argv, _, _ = burner(tmp_path, "exit99", 2)
    run = lf.run_child(argv, interval=0.5)
    assert run.exit_status == 99                      # Popen.poll() would say 0 after wait4 reaped it
    assert all(b.cpu_s >= a.cpu_s for a, b in zip(run.ticks, run.ticks[1:]))
    assert all(not t.stat.startswith("Z") for t in run.ticks)


def test_zombie_backwards_and_vanished_ticks_are_discarded_not_clamped(tmp_path, monkeypatch):
    """Real data is monotone, so the discard branches need a scripted `ps`: a zombie row, a cumulative CPU
    that goes backwards, and the child vanishing between wait4 and ps (k6 exiting mid-tick)."""
    script = iter([
        ("row", "R", 1.0),
        ("row", "Z", 1.5),                      # zombie: discard
        ("row", "R", 0.5),                      # backwards: discard
        ("gone",),                              # raced with its exit: discard
        ("row", "R", 2.0),
        ("row", "R", 3.0),
    ])

    def fake_sample_ps(pids):
        step = next(script, ("row", "R", 4.0))
        if step[0] == "gone":
            raise lf.ProcessGone([pids[0]], {})
        return {pids[0]: lf.PsRow(stat=step[1], rss_kb=1000, cpu_s=step[2])}

    monkeypatch.setattr(lf, "sample_ps", fake_sample_ps)
    run = lf.run_child([sys.executable, "-c", "import time; time.sleep(3)"], interval=0.2)
    assert [t.cpu_s for t in run.ticks[:3]] == [1.0, 2.0, 3.0]
    assert run.discarded_ticks == 3
    assert run.exit_status == 0


def test_neighbour_pids_are_sampled_every_nth_tick_but_the_child_every_tick(tmp_path):
    argv, _, _ = burner(tmp_path, "busy", 3)
    run = lf.run_child(argv, interval=0.3, extra_pids=(os.getpid(),), extra_every=3)
    assert len(run.ticks) >= 6
    assert [bool(t.extra) for t in run.ticks[:6]] == [True, False, False, True, False, False]


# --- T6: the cputime parser, pure --------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, seconds",
    [
        ("0:01.23", 1.23),
        ("43:57.34", 43 * 60 + 57.34),
        ("225:43.35", 225 * 60 + 43.35),
        ("4631:14.66", 4631 * 60 + 14.66),
        ("1:02:03.04", 3600 + 2 * 60 + 3.04),
    ],
)
def test_parse_cputime_accepts_the_observed_forms(text, seconds):
    assert lf.parse_cputime(text) == pytest.approx(seconds)


@pytest.mark.parametrize("text", ["", "abc", "1:2:3:4", "1-02:03:04", "12"])
def test_parse_cputime_raises_on_an_unknown_form_instead_of_guessing(text):
    with pytest.raises(ValueError):
        lf.parse_cputime(text)


def test_percentile_is_nearest_rank():
    assert lf.percentile(list(range(1, 101)), 95) == 95
    assert lf.percentile([7.0], 95) == 7.0


# --- T7: summarise, pure -----------------------------------------------------------------------------


def rec(rate, rep=1, cpu=None, **kw):
    """A kept-by-default all-hit run whose CPU is exactly 1.0 + 0.5 * rate (% of one core)."""
    base = {
        "kind": "allhit", "rate_offered": rate, "rep": rep, "achieved_rate": rate,
        "cpu_pct_mean": 1.0 + 0.5 * rate if cpu is None else cpu,
        "rss_peak_bytes": 40_000_000, "rusage_cpu_s": 10.0, "sampled_cpu_s": 9.0,
        "exit_status": 0, "error_rate": 0.0, "shed": 0, "miss": 0, "vus_max": 40,
    }
    base.update(kw)
    return lf.RunRecord(**base)


def test_summarise_recovers_the_intercept_and_slope_across_the_grid():
    runs = [rec(r, rep) for r in (2, 8, 16, 32) for rep in (1, 2, 3)]
    table = lf.summarise(runs, ncpu=8)
    assert table.excluded == []
    a, b = table.fit
    assert a == pytest.approx(1.0) and b == pytest.approx(0.5)
    row16 = next(r for r in table.rows if r.rate_offered == 16 and r.kind == "allhit")
    assert row16.cpu_pct_mean == pytest.approx(9.0)
    assert row16.cpu_pct_of_machine == pytest.approx(9.0 / 8)


def test_summarise_excludes_an_unattained_row_at_94_percent_but_keeps_96():
    table = lf.summarise([rec(16, 1, achieved_rate=16 * 0.94), rec(16, 2, achieved_rate=16 * 0.96)], ncpu=8)
    assert [(r.rep, f) for r, f in table.excluded] == [(1, ["unattained"])]


@pytest.mark.parametrize(
    "kw, flag",
    [
        ({"exit_status": 1}, "exit_status"),
        ({"miss": 1}, "miss_in_allhit"),
        ({"shed": 1}, "shed_in_allhit"),
        ({"error_rate": 0.02}, "errors_in_allhit"),
        # the sampler read something that is not k6
        ({"rusage_cpu_s": 5.0, "sampled_cpu_s": 9.0}, "rusage_below_sampled"),
    ],
)
def test_summarise_excludes_a_flagged_row_instead_of_annotating_it(kw, flag):
    table = lf.summarise([rec(8, 1, **kw), rec(8, 2)], ncpu=8)
    assert [(r.rep, f) for r, f in table.excluded] == [(1, [flag])]
    assert [r.reps for r in table.rows] == [1]


def test_the_mixed_row_expects_misses_and_sheds_so_they_do_not_exclude_it():
    table = lf.summarise([rec(8, 1, kind="mixed", miss=40, shed=12)], ncpu=8)
    assert table.excluded == []
    assert table.fit is None                              # one regime, one rate: nothing to fit


def test_window_mean_refuses_to_report_a_window_it_does_not_have():
    ticks = [lf.Tick(t=float(i), cpu_s=float(i), rss_kb=1, stat="R") for i in range(4)]
    with pytest.raises(ValueError):
        lf.window_mean(ticks, trim_head=5.0, trim_tail=5.0)


# --- T8, T9: nothing is left running -----------------------------------------------------------------


def test_an_exception_mid_run_leaves_no_orphan(tmp_path):
    argv, _, pidfile = burner(tmp_path, "busy", 30)       # would run 30 s if it were orphaned

    def boom(tick):
        raise RuntimeError("injected")

    started = time.monotonic()
    with pytest.raises(RuntimeError, match="injected"):
        lf.run_child(argv, interval=0.3, on_tick=boom)
    # Bounded in TIME as well as in state: a version that forgot to kill the child would still end up
    # "gone" -- after the 30 s burner finished on its own.
    assert time.monotonic() - started < 10
    assert gone(int(pidfile.read_text()))


def test_sigterm_to_the_sampler_kills_the_child(tmp_path):
    argv, _, pidfile = burner(tmp_path, "busy", 30)
    harness = (
        f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); import loadgen_footprint as lf; "
        f"lf.install_signal_handlers(); lf.run_child({argv!r}, interval=0.3)"
    )
    sampler = subprocess.Popen([sys.executable, "-I", "-c", harness], start_new_session=True)
    try:
        for _ in range(50):                               # wait for the burner to announce its pid
            if pidfile.exists() and pidfile.read_text():
                break
            time.sleep(0.1)
        child = int(pidfile.read_text())
        os.kill(sampler.pid, signal.SIGTERM)
        sampler.wait(timeout=10)
        assert gone(child, wait=5.0)
    finally:
        if sampler.poll() is None:
            os.killpg(sampler.pid, signal.SIGKILL)


# --- T10: the instrument must not carry the system under test inside it ------------------------------


def test_importing_the_sampler_does_not_import_rag():
    code = (
        f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); import loadgen_footprint; "
        "bad = sorted(m for m in sys.modules if m == 'rag' or m.startswith('rag.')); "
        "assert not bad, bad"
    )
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr


# --- the driver's pure parts: the table from a CSV, the workload, the k6 export, vm_stat -------------


SUT_FACTORS = {"gateway": 0.02, "rag_server": 0.01, "redis": 0.005, "ollama_serve": 0.0,
               "llm_runner": 0.5, "embed_runner": 0.25}


def write_run(directory, tag, kind, rate, rep, *, cpu_per_s=0.1, seconds=20, miss=0, achieved=None, cum=None,
              sut=False, probe_mb=55.0):
    """A fixture run: cumulative CPU rises `cpu_per_s` per second, i.e. cpu_per_s * 100 % of one core, unless
    `cum` gives the cumulative series. `sut` adds the SUT columns, sampled every 5th tick as the driver does."""
    csv_name = f"samples-{tag}.csv"
    cum = cum if cum is not None else [0.5 + cpu_per_s * t for t in range(seconds + 1)]
    cols = "t,k6_cpu_s,k6_rss_kb,vm_pressure_level,memstatus_level,swap_used_mb"
    if sut:
        cols += "".join(f",{r}_cpu_s,{r}_rss_kb" for r in SUT_FACTORS)
    with (directory / csv_name).open("w") as fh:
        fh.write(cols + "\n")
        for t, c in enumerate(cum):
            line = f"{t},{c},40000,2,42,5990.0"
            if sut:
                for r, f in SUT_FACTORS.items():
                    rss = (2_000_000 if t < 10 else 15_000) if r == "llm_runner" else 40_000
                    line += f",{1.0 + f * t},{rss}" if t % 5 == 0 else ",,"
            fh.write(line + "\n")
    meta = {
        "tag": tag, "kind": kind, "rate_offered": rate, "rep": rep, "csv": csv_name,
        "k6": {"achieved_rate": float(rate) if achieved is None else achieved, "error_rate": 0.0, "shed": 0,
               "miss": miss, "vus_max": 40, "tier1": 100, "tier2": 0, "dropped": 0},
        "exit_status": 0, "maxrss_bytes": 60_000_000, "rusage_cpu_s": cum[-1] + 0.2, "discarded_ticks": 0,
        "sampler_overhead_pct": 1.5, "flags": [], "k6_footprint_probes": [{"t": 10.0, "k6_phys_footprint_mb": probe_mb}],
        "vm_stat_before": {"Swapins": 10, "Swapouts": 20, "Pageins": 100, "Pageouts": 5},
        "vm_stat_after": {"Swapins": 10, "Swapouts": 25, "Pageins": 130, "Pageouts": 5},
    }
    (directory / f"run-{tag}.json").write_text(json.dumps(meta))


def test_summarize_reproduces_a_hand_computed_table_from_the_csvs_alone(tmp_path):
    (tmp_path / "header.json").write_text(json.dumps({
        "machine": {"ncpu": 8, "perf_cores": 4, "eff_cores": 4}, "git_sha": "a" * 40,
        "tree_dirty": True, "sut_dirty": False, "k6_version": "k6 v1.7.1", "ollama_keep_alive": "5m0s"}))
    write_run(tmp_path, "allhit-r8-rep1", "allhit", 8, 1, cpu_per_s=0.10)    # 10 % of one core
    write_run(tmp_path, "allhit-r8-rep2", "allhit", 8, 2, cpu_per_s=0.12)    # 12 %
    write_run(tmp_path, "allhit-r8-rep3", "allhit", 8, 3, miss=1)            # a MISS in an all-hit row: left out
    text = Path(lf.summarize_dir(tmp_path)).read_text()
    # mean of 10 and 12 = 11.00; spread 10.00 - 12.00; % of the 8-core machine = 11/8 = 1.375
    assert "| 8 | 2 | 8.00 | 11.00 | 10.00 – 12.00 | 1.375 |" in text
    assert "allhit-r8-rep3`: miss_in_allhit" in text
    assert "EXCLUDED" in text
    assert "0 / 5" in text and "30 / 0" in text            # swap-ins/outs and page-ins/outs, as deltas


def test_the_workload_is_seeded_unique_and_starts_with_the_smoke_set(tmp_path):
    a, b, c = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "c.json"
    assert lf.make_workload(a, 300, 1) == 305
    lf.make_workload(b, 300, 1)
    lf.make_workload(c, 300, 2)
    items = [r["question"] for r in json.loads(a.read_text())]
    assert items[:5] == lf.SMOKE_QUESTIONS
    assert len(set(items)) == 305
    assert a.read_bytes() == b.read_bytes()                # same seed, same file
    assert a.read_bytes() != c.read_bytes()                # different seed, different order
    with pytest.raises(ValueError):
        lf.make_workload(tmp_path / "d.json", 10_000, 1)


def test_k6_numbers_default_absent_counters_to_zero(tmp_path):
    """Probe U4: a Counter never added to is ABSENT from --summary-export, and dropped_iterations appears
    only when non-zero. Reading them without a default would raise, or worse, be skipped."""
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"metrics": {
        "iterations": {"count": 30, "rate": 5.0}, "vus_max": {"max": 5, "value": 5, "min": 5},
        "error_rate": {"passes": 0, "fails": 30, "value": 0}, "shed_rate": {"passes": 0, "fails": 30, "value": 0},
        "cache_tier1_hit": {"count": 30}}}))
    n = lf.k6_numbers(path, duration=6)
    assert (n["dropped"], n["tier2"], n["miss"]) == (0, 0, 0)
    assert n["tier1"] == 30 and n["achieved_rate"] == 5.0 and n["vus_max"] == 5
    path.write_text(json.dumps({"metrics": {
        "iterations": {"count": 48}, "dropped_iterations": {"count": 253}, "vus_max": {"max": 4},
        "error_rate": {"value": 0}, "shed_rate": {"passes": 3}}}))
    n = lf.k6_numbers(path, duration=6)
    assert n["dropped"] == 253 and n["shed"] == 3 and n["achieved_rate"] == 8.0


def test_parse_vm_stat_reads_the_counters_it_reports_on():
    text = "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free:      12345.\nPageins:  165339131.\nSwapouts:      9.\n"
    got = lf.parse_vm_stat(text)
    assert got["Pageins"] == 165339131 and got["Swapouts"] == 9 and got["Pages free"] == 12345


# --- the cache flush: prefix-only, verified, never the corpus ---------------------------------------


class FakeRedis:
    """Just enough of redis-cli for flush_cache: PING, --scan --pattern, DEL."""

    def __init__(self, keys, stuck=()):
        self.keys, self.stuck = set(keys), set(stuck)

    def __call__(self, *argv):
        if argv == ("PING",):
            return "PONG\n"
        if argv[:2] == ("--scan", "--pattern"):
            prefix = argv[2][:-1]
            return "\n".join(sorted(k for k in self.keys if k.startswith(prefix)))
        if argv[0] == "DEL":
            self.keys -= {k for k in argv[1:] if k not in self.stuck}
            return ""
        raise AssertionError(argv)


def test_flush_cache_deletes_only_cache_prefixes_and_never_the_corpus():
    r = FakeRedis({"corpus:a", "corpus:b", "t1:x", "t1:y", "t2:z", "lru:entries", "other:k"})
    before = lf.flush_cache(r)
    assert before["t1:"] == 2 and before["corpus:"] == 2
    assert r.keys == {"corpus:a", "corpus:b", "other:k"}          # a foreign key is left alone as well


def test_flush_cache_aborts_if_a_cache_key_survives():
    r = FakeRedis({"corpus:a", "t1:x"}, stuck={"t1:x"})
    with pytest.raises(lf.RunAbort, match="survived"):
        lf.flush_cache(r)


def test_flush_cache_aborts_if_redis_does_not_answer():
    with pytest.raises(lf.RunAbort, match="PONG"):
        lf.flush_cache(lambda *argv: "")


def test_the_workload_path_given_to_k6_is_absolute_even_for_a_relative_out(tmp_path, monkeypatch):
    """k6 resolves open() against the script's directory, not the cwd (the recorded run's mixed rows died on
    a relative --out with exit 107)."""
    monkeypatch.chdir(tmp_path)
    arg = lf.workload_arg(Path("evidence/footprint"))
    assert Path(arg).is_absolute()
    assert arg == str(tmp_path.resolve() / "evidence/footprint/workload-mixed.json")


# --- review round (2026-10-07): guards and pure helpers the first suite did not reach -----------------


@pytest.mark.parametrize(
    "kw, flag",
    [
        ({"rusage_cpu_s": 10.0, "sampled_cpu_s": 1.0}, "sampled_far_below_rusage"),   # a wrapper's pid
        ({"discarded_ticks": 20, "n_ticks": 60}, "many_discarded_ticks"),
    ],
)
def test_the_run_is_left_out_when_the_sampler_was_not_watching_the_child_or_lost_many_ticks(kw, flag):
    assert flag in lf.exclusion_flags(rec(8, 1, **kw))


def test_a_few_discarded_ticks_do_not_exclude_a_run():
    assert lf.exclusion_flags(rec(8, 1, discarded_ticks=5, n_ticks=60)) == []


def test_errors_in_the_mixed_regime_exclude_the_row():
    assert lf.exclusion_flags(rec(8, 1, kind="mixed", error_rate=0.02)) == ["errors_in_mixed"]
    assert lf.exclusion_flags(rec(8, 1, kind="mixed", error_rate=0.0, miss=9, shed=9)) == []


def test_a_child_that_is_not_the_expected_executable_is_flagged_on_the_first_tick():
    wrong = lf.run_child(["/bin/sleep", "2"], interval=0.4, expect_comm="k6")
    right = lf.run_child(["/bin/sleep", "2"], interval=0.4, expect_comm="sleep")
    assert wrong.flags == ["wrong_process:sleep"]
    assert right.flags == []


def test_sample_machine_maps_each_sysctl_line_to_its_own_field(monkeypatch):
    out = "2\n42\ntotal = 7168.00M  used = 5990.75M  free = 1177.25M  (encrypted)\n"
    monkeypatch.setattr(lf.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=out))
    assert lf.sample_machine() == {"vm_pressure_level": 2, "memstatus_level": 42, "swap_used_mb": 5990.75}


def test_sample_ps_raises_for_a_missing_pid_instead_of_dropping_it(monkeypatch):
    out = "  100 Ss     1234   0:01.00\n"
    monkeypatch.setattr(lf.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=out))
    with pytest.raises(lf.ProcessGone) as err:
        lf.sample_ps([100, 200])
    assert err.value.pids == [200] and list(err.value.found) == [100]


def test_a_missing_neighbour_pid_is_flagged_and_the_tick_is_kept(monkeypatch):
    calls = {"n": 0}

    def fake(pids):
        calls["n"] += 1
        rows = {pids[0]: lf.PsRow(stat="R", rss_kb=1000, cpu_s=1.0 + 0.1 * calls["n"])}
        if len(pids) > 1:
            raise lf.ProcessGone([pids[1]], rows)
        return rows

    monkeypatch.setattr(lf, "sample_ps", fake)
    run = lf.run_child([sys.executable, "-c", "import time; time.sleep(1.5)"], interval=0.3, extra_pids=(999_999,))
    assert "sut_pid_missing:999999" in run.flags
    assert len(run.ticks) >= 2 and run.discarded_ticks == 0


def test_the_steady_state_window_is_pinned_and_excludes_the_head_and_the_tail(tmp_path):
    assert (lf.WINDOW_HEAD_S, lf.WINDOW_TAIL_S) == (5.0, 5.0)         # fixed in advance (design §2)
    cum, total = [0.5], 0.5
    for t in range(1, 21):                                             # 1 core in the first and last 5 s, 0.1 between
        total += 1.0 if (t <= 5 or t > 15) else 0.1
        cum.append(total)
    write_run(tmp_path, "allhit-r8-rep1", "allhit", 8, 1, cum=cum)
    text = Path(lf.summarize_dir(tmp_path, ncpu=8)).read_text()
    assert "| 8 | 1 | 8.00 | 10.00 |" in text            # a window of 0..20 would read 55 %


def test_summarize_needs_a_core_count_rather_than_guessing_one(tmp_path):
    write_run(tmp_path, "allhit-r8-rep1", "allhit", 8, 1)
    with pytest.raises(lf.RunAbort, match="ncpu"):
        lf.summarize_dir(tmp_path)
    assert Path(lf.summarize_dir(tmp_path, ncpu=8)).exists()


def test_the_sut_table_pairs_each_role_with_its_own_cpu_and_the_llm_runners_rss(tmp_path):
    write_run(tmp_path, "allhit-r8-rep1", "allhit", 8, 1, sut=True, probe_mb=55.0)
    write_run(tmp_path, "allhit-r8-rep2", "allhit", 8, 2, sut=True, probe_mb=77.0)
    text = Path(lf.summarize_dir(tmp_path, ncpu=8)).read_text()
    # window 5..15 s, samples at t = 5, 10, 15: CPU % = 100 x factor for each role; LLM RSS 2,000,000 KiB then 15,000
    assert "| allhit-r8-rep1 | 2.0 | 1.0 | 0.5 | 0.0 | 50.0 | 25.0 | 78.5 | 15 – 1953 |" in text
    rows = {line.split("|")[1].strip(): line for line in text.splitlines()
            if line.startswith("| allhit-r8-rep") and "| kept |" in line}          # the per-run table's rows only
    assert "55" in rows["allhit-r8-rep1"] and "77" not in rows["allhit-r8-rep1"]      # each row keeps its own probe
    assert "77" in rows["allhit-r8-rep2"] and "55" not in rows["allhit-r8-rep2"]


def test_rss_is_reported_in_decimal_megabytes():
    assert lf._mb(60_000_000) == "60"


def test_the_sampler_overhead_is_charged_net_of_k6s_own_cpu():
    # this process 0.5 s + reaped children 1.0 s (k6 0.7 s among them) over 60 s: the instrument spent 0.8 s
    assert lf.sampler_overhead_pct(0.5, 1.0, 0.7, 60.0) == pytest.approx(100 * 0.8 / 60)


def test_the_embedding_runner_is_the_llama_server_that_is_not_the_llm_runner():
    rows = [
        "  100     1 /Applications/Ollama.app/ollama serve",
        "  200   100 /Applications/Ollama.app/llama-server --model /m/sha256-" + "a" * 64,
        "  300   100 /Applications/Ollama.app/llama-server --model /m/sha256-" + "b" * 64,
        "  400   999 /Applications/Other.app/llama-server --model /m/sha256-" + "c" * 64,   # another server's
    ]
    assert lf.embed_runner_pid(rows, serve_pid=100, llm_pid=200) == 300
    assert lf.embed_runner_pid(rows, serve_pid=100, llm_pid=300) == 200
    with pytest.raises(lf.RunAbort):
        lf.embed_runner_pid(rows[:2], serve_pid=100, llm_pid=200)                      # no embedder at all


def test_a_run_with_excluded_rows_is_countable_so_the_exit_status_can_say_so(tmp_path):
    write_run(tmp_path, "allhit-r8-rep1", "allhit", 8, 1)
    write_run(tmp_path, "allhit-r8-rep2", "allhit", 8, 2, miss=1)
    lf.summarize_dir(tmp_path, ncpu=8)
    assert lf.count_excluded(tmp_path) == 1


def test_the_flush_refuses_to_delete_the_dependency_region_and_deletes_nothing():
    r = FakeRedis({"corpus:a", "t1:x", "t2:y", "dep:c#chunk-1", "entry:e"})
    with pytest.raises(lf.RunAbort, match="dependency-region"):
        lf.flush_cache(r)
    assert r.keys == {"corpus:a", "t1:x", "t2:y", "dep:c#chunk-1", "entry:e"}


def test_the_flush_talks_to_the_redis_port_the_sut_uses(monkeypatch):
    seen = []
    monkeypatch.setattr(lf, "run_text", lambda argv, cwd=None: seen.append(argv) or "PONG\n")
    lf.redis_cli(6380)("PING")
    assert seen == [["redis-cli", "-p", "6380", "PING"]]


def test_incoherent_arguments_are_refused_before_anything_is_touched():
    ns = argparse.Namespace
    with pytest.raises(lf.RunAbort, match="cold cache"):
        lf.check_args(ns(no_flush=True, mixed=True, rates="2"))
    with pytest.raises(lf.RunAbort, match="nothing to run"):
        lf.check_args(ns(no_flush=False, mixed=False, rates=""))
    lf.check_args(ns(no_flush=False, mixed=True, rates=""))             # the mixed row alone is fine


@pytest.mark.parametrize(
    "vars_, mixed, no_flush",
    [(["MIXED=0"], False, False), (["MIXED=1"], True, False), (["MIXED="], False, False), ([], True, False),
     (["NO_FLUSH=1", "MIXED=0"], False, True)],
)
def test_the_makefile_target_passes_the_flags_the_variables_ask_for(vars_, mixed, no_flush):
    root = Path(__file__).resolve().parents[2]
    out = subprocess.run(["make", "-n", "footprint", "OUT=/tmp/x", *vars_], cwd=root, capture_output=True,
                         text=True, check=False).stdout
    assert ("--mixed" in out) is mixed and ("--no-flush" in out) is no_flush
