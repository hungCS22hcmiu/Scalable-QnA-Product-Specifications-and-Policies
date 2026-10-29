"""One arm: unload the LLM, load it fresh, send each prompt once, and sample the runner after each.

    python3 run_arm.py <label> <prompts.jsonl> <outdir> [limit]

A copy of the RCA's `evidence/rca/scripts/run_arm.py` with one change: before it takes the log offset
and loads, it unloads the LLM (`keep_alive: 0`) and waits up to 30 s until no LLM runner is left. So
the captured server log holds THIS load, with its "prompt cache is disabled" lines. If a runner is
still there after 30 s, it exits 2.

Exit 3 if memory pressure reaches 4 (red). Yellow and swap are allowed (the author, 2026-10-29).
Exit 4 if the runner's environment holds a token-like variable: it is then not saved.
citable: no.
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://localhost:11434"
MODEL = "qwen3.5:2b-q4_K_M"
BLOB = "sha256-7a3a8d55382135a773916fd7c35044b2a2a3a7b8dee788095d70f122e6d8f520"
LOG = os.path.expanduser("~/.ollama/logs/server.log")
SECRET_NAME = re.compile(r"TOKEN|SECRET|KEY|PASSW|CREDENTIAL", re.IGNORECASE)


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout


def pressure():
    return int(sh("sysctl", "-n", "kern.memorystatus_vm_pressure_level").strip())


def post(path, body, timeout=300):
    req = urllib.request.Request(
        BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def runner_or_none():
    """(pid, argv) of the LLM runner under the server on :11434, or None when there is none."""
    listeners = sh("lsof", "-nP", "-iTCP:11434", "-sTCP:LISTEN", "-t").split()
    if not listeners:
        return None
    server = int(listeners[0])
    for row in sh("ps", "-axww", "-o", "pid=,ppid=,command=").splitlines():
        pid, ppid, cmd = row.split(None, 2)
        if (
            int(ppid) == server
            and cmd.split()[0].endswith("llama-server")
            and "--model " in cmd
            and BLOB in cmd.split("--model ")[1].split()[0]
        ):
            return int(pid), cmd
    return None


def runner():
    found = runner_or_none()
    if found is None:
        raise SystemExit("no LLM runner")
    return found


def unload():
    """Unload the LLM and wait up to 30 s until no LLM runner is left; exit 2 if one is."""
    post("/api/generate", {"model": MODEL, "keep_alive": 0}, timeout=60)
    deadline = time.time() + 30
    while time.time() < deadline:
        if runner_or_none() is None:
            return
        time.sleep(1)
    print("an LLM runner is still there 30 s after the unload", flush=True)
    sys.exit(2)


def fp(pid):
    out = sh("footprint", "-p", str(pid))
    m = re.search(r"Footprint:\s*([\d.]+)\s*(KB|MB|GB)", out)
    mb = (
        float(m.group(1)) * {"KB": 1 / 1024, "MB": 1, "GB": 1024}[m.group(2)]
        if m
        else None
    )
    return mb, out


def rss_mb(pid):
    return int(sh("ps", "-o", "rss=", "-p", str(pid)).strip() or 0) / 1024


def main():
    label, prompts_path, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    limit = int(sys.argv[4]) if len(sys.argv) > 4 else 10**9
    os.makedirs(outdir, exist_ok=True)

    def P(name):
        return os.path.join(outdir, f"{label}-{name}")

    p0 = pressure()
    print(f"[{label}] pressure before load: {p0}", flush=True)
    if p0 >= 4:
        sys.exit(3)
    unload()
    log_off = os.path.getsize(LOG)
    t = time.time()
    post("/api/generate", {"model": MODEL, "options": {"num_ctx": 8192}})
    load_s = time.time() - t
    pid, cmd = runner()
    env_tokens = [
        x
        for x in sh("ps", "eww", "-o", "command=", "-p", str(pid)).split(" ")
        if re.match(r"^[A-Z_][A-Z0-9_]*=", x)
    ]
    bad = [x.split("=")[0] for x in env_tokens if SECRET_NAME.search(x.split("=")[0])]
    if bad:
        print(
            f"[{label}] runner environment holds token-like variables {bad}; not saved",
            flush=True,
        )
        sys.exit(4)
    Path(P("argv.txt")).write_text(cmd + "\n")
    Path(P("env.txt")).write_text("\n".join(env_tokens) + "\n")
    port = int(cmd.split("--port ")[1].split()[0])
    props = get(f"http://127.0.0.1:{port}/props")
    Path(P("props.json")).write_text(json.dumps(props, indent=1))
    mb, out = fp(pid)
    Path(P("footprint-0.txt")).write_text(out)
    samples = Path(P("samples.jsonl")).open("w")  # noqa: SIM115 -- closed at exit, flushed per line
    first = {
        "i": 0,
        "runner_pid": pid,
        "rss_mb": rss_mb(pid),
        "footprint_mb": mb,
        "pressure": pressure(),
        "load_s": load_s,
    }
    samples.write(json.dumps(first) + "\n")
    samples.flush()
    prompts = [
        json.loads(line) for line in Path(prompts_path).read_text().splitlines()
    ][:limit]
    for i, pr in enumerate(prompts, 1):
        pl = pressure()
        if pl >= 4:
            print(f"[{label}] RED before request {i}, stopping", flush=True)
            samples.write(json.dumps({"i": i, "abort": "red"}) + "\n")
            sys.exit(3)
        t = time.time()
        body = {
            "model": MODEL,
            "prompt": pr["prompt"],
            "stream": False,
            "think": False,
            "options": {"num_ctx": 8192},
        }
        r = post("/api/generate", body)
        wall = time.time() - t
        p2, _ = runner()
        mb, out = fp(p2)
        if i in (10, 25, len(prompts)):
            Path(P(f"footprint-{i}.txt")).write_text(out)
        rec = {
            "i": i,
            "qa_id": pr["qa_id"],
            "runner_pid": p2,
            "wall_s": round(wall, 3),
            "total_s": r["total_duration"] / 1e9,
            "load_s": r.get("load_duration", 0) / 1e9,
            "prompt_tokens": r.get("prompt_eval_count"),
            "prompt_s": r.get("prompt_eval_duration", 0) / 1e9,
            "eval_tokens": r.get("eval_count"),
            "eval_s": r.get("eval_duration", 0) / 1e9,
            "rss_mb": rss_mb(p2),
            "footprint_mb": mb,
            "pressure_before": pl,
            "pressure_after": pressure(),
        }
        samples.write(json.dumps(rec) + "\n")
        samples.flush()
        fp_text = "None" if mb is None else f"{mb:.0f}MB"
        print(
            f"[{label}] {i:3d} wall={wall:5.2f}s ptok={rec['prompt_tokens']} "
            f"rss={rec['rss_mb']:.0f}MB fp={fp_text} pres={rec['pressure_after']}",
            flush=True,
        )
    with open(LOG, "rb") as f:
        f.seek(log_off)
        new = f.read().decode("utf-8", "replace")
    Path(P("server-log.txt")).write_text(new)


if __name__ == "__main__":
    main()
