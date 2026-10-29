"""The verdict on one `run_arm.py` arm: done conditions 6, 7 and 8 of the task, with their numbers.

    python3 verdict.py --samples <label>-samples.jsonl --log <label>-server-log.txt \
        --prompts prompts.jsonl [--repeat repeat-samples.jsonl] [--n 300] [--window 50]

Prints one PASS or FAIL line per check, then the highest memory pressure seen (not a check), and
exits 0 only if every check passed. citable: no.

The guards come first, because each one is a way for the probe to see nothing and still look fine:
the runner reloading mid-run (its footprint resets), prompts that repeat (a live cache would not
grow), a footprint that did not parse, and a log without this load's lines (so "no cache state:
line" would pass with nothing checked).
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

GROWTH_MB = 100.0  # DC 6: last-window mean may exceed first-window mean by at most this
PREFILL_MIN = 431.0  # DC 8: 0.9 x the RCA's cache-on median of 479 tok/s
DECODE_MIN = 32.0  # DC 8: 0.9 x the RCA's cache-on median of 35.5 tok/s
REPEAT_RATIO = 0.8  # DC 7: a repeat's prefill is at least this share of the first one's


def read_jsonl(path):
    return [
        json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()
    ]


def is_number(v):
    return isinstance(v, int | float) and not isinstance(v, bool)


def check_samples(samples, requests, n):
    aborts = [r for r in samples if "abort" in r]
    ok = len(requests) == n and not aborts
    return (
        ok,
        f"{len(requests)} request samples (want {n}), {len(aborts)} abort line(s)",
    )


def check_distinct(prompts, n):
    first = [p.get("prompt") for p in prompts[:n]]
    ok = len(first) == n and len(set(first)) == n
    return (
        ok,
        f"{len(set(first))} distinct among the first {len(first)} prompts (want {n})",
    )


def check_one_runner(samples):
    body = [r for r in samples if "abort" not in r]
    pids = {r.get("runner_pid") for r in body}
    has_zero = any(r.get("i") == 0 for r in body)
    ok = len(pids) == 1 and None not in pids and has_zero
    return (
        ok,
        f"runner_pid values {sorted(map(str, pids))} over {len(body)} samples, sample 0 present: {has_zero}",
    )


def check_footprints(samples):
    body = [r for r in samples if "abort" not in r]
    bad = [r.get("i") for r in body if not is_number(r.get("footprint_mb"))]
    return (
        not bad,
        f"{len(body) - len(bad)} of {len(body)} samples have a footprint"
        + (f"; missing at i={bad[:10]}" if bad else ""),
    )


def check_growth(requests, window):
    fps = [r.get("footprint_mb") for r in requests]
    if len(fps) < 2 * window or not all(is_number(v) for v in fps):
        return (
            False,
            f"cannot compute: {len(fps)} request footprints for windows of {window}",
        )
    first = statistics.fmean(fps[:window])
    last = statistics.fmean(fps[-window:])
    grew = last - first
    n = len(fps)
    return grew <= GROWTH_MB, (
        f"mean footprint of samples {n - window + 1}-{n} = {last:.0f} MB, of samples 1-{window} = "
        f"{first:.0f} MB, increase {grew:+.0f} MB (limit {GROWTH_MB:.0f})"
    )


def check_log(log_text):
    cache_off = log_text.count("prompt cache is disabled")
    ckpt_off = log_text.count("context checkpoints disabled")
    state = log_text.count("cache state:")
    ok = cache_off >= 1 and ckpt_off >= 1 and state == 0
    return ok, (
        f'"prompt cache is disabled" x{cache_off}, "context checkpoints disabled" x{ckpt_off}, '
        f'"cache state:" lines x{state} (want >=1, >=1, 0)'
    )


def check_speed(requests):
    try:
        prefill = [r["prompt_tokens"] / r["prompt_s"] for r in requests]
        decode = [r["eval_tokens"] / r["eval_s"] for r in requests]
    except (KeyError, TypeError, ZeroDivisionError) as e:
        return False, f"cannot compute tokens per second: {type(e).__name__}: {e}"
    if not requests:
        return False, "no request samples"
    p, d = statistics.median(prefill), statistics.median(decode)
    ok = p >= PREFILL_MIN and d >= DECODE_MIN
    return ok, (
        f"median prefill {p:.0f} tok/s (min {PREFILL_MIN:.0f}), "
        f"median decode {d:.1f} tok/s (min {DECODE_MIN:.1f})"
    )


def check_repeat(repeat):
    if len(repeat) != 3:
        return False, f"{len(repeat)} repeat samples (want 3)"
    t = [r.get("prompt_s") for r in repeat]
    if not all(is_number(v) for v in t) or t[0] <= 0:
        return False, f"unusable prefill times {t}"
    ok = t[1] >= REPEAT_RATIO * t[0] and t[2] >= REPEAT_RATIO * t[0]
    return ok, (
        f"prefill {t[0]:.3f} s, then {t[1]:.3f} s and {t[2]:.3f} s "
        f"(each repeat must be >= {REPEAT_RATIO} x the first = {REPEAT_RATIO * t[0]:.3f} s)"
    )


def highest_pressure(samples):
    seen = []
    for r in samples:
        for k in ("pressure", "pressure_before", "pressure_after"):
            if is_number(r.get(k)):
                seen.append(r[k])
    return max(seen) if seen else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--samples", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--repeat")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--window", type=int, default=50)
    a = ap.parse_args()

    samples = read_jsonl(a.samples)
    requests = [r for r in samples if "wall_s" in r]
    log_text = Path(a.log).read_text(errors="replace")
    prompts = read_jsonl(a.prompts)

    results = [
        ("samples", *check_samples(samples, requests, a.n)),
        ("distinct prompts", *check_distinct(prompts, a.n)),
        ("one runner", *check_one_runner(samples)),
        ("footprints", *check_footprints(samples)),
        ("DC 6 memory flat", *check_growth(requests, a.window)),
        ("DC 6 server log", *check_log(log_text)),
        ("DC 8 speed", *check_speed(requests)),
    ]
    if a.repeat:
        results.append(("DC 7 no hidden reuse", *check_repeat(read_jsonl(a.repeat))))

    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    print(
        f"highest memory pressure seen: {highest_pressure(samples)} (not a check; 1=green 2=yellow 4=red)"
    )
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
