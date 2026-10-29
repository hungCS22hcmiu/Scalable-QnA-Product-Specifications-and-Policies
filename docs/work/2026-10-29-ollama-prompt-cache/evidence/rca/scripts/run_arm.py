"""One arm: load the LLM, then send each prompt once, sampling the runner after every request.
Stops (exit 3) if pressure reaches 4 (red). citable: no."""
import json, os, re, subprocess, sys, time, urllib.request

BASE = "http://localhost:11434"
MODEL = "qwen3.5:2b-q4_K_M"
BLOB = "sha256-7a3a8d55382135a773916fd7c35044b2a2a3a7b8dee788095d70f122e6d8f520"
LOG = os.path.expanduser("~/.ollama/logs/server.log")
label, prompts_path, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
limit = int(sys.argv[4]) if len(sys.argv) > 4 else 10**9
os.makedirs(outdir, exist_ok=True)
P = lambda name: os.path.join(outdir, f"{label}-{name}")

def sh(*cmd): return subprocess.run(cmd, capture_output=True, text=True).stdout
def pressure(): return int(sh("sysctl", "-n", "kern.memorystatus_vm_pressure_level").strip())
def post(path, body, timeout=300):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read())
def get(url):
    with urllib.request.urlopen(url, timeout=10) as r: return json.loads(r.read())
def runner():
    server = int(sh("lsof", "-nP", "-iTCP:11434", "-sTCP:LISTEN", "-t").split()[0])
    for row in sh("ps", "-axww", "-o", "pid=,ppid=,command=").splitlines():
        pid, ppid, cmd = row.split(None, 2)
        if int(ppid) == server and cmd.split()[0].endswith("llama-server") and f"--model " in cmd and BLOB in cmd.split("--model ")[1].split()[0]:
            return int(pid), cmd
    raise SystemExit("no LLM runner")
def fp(pid):
    out = sh("footprint", "-p", str(pid))
    m = re.search(r"Footprint:\s*([\d.]+)\s*(KB|MB|GB)", out)
    mb = float(m.group(1)) * {"KB": 1/1024, "MB": 1, "GB": 1024}[m.group(2)] if m else None
    return mb, out
def rss_mb(pid): return int(sh("ps", "-o", "rss=", "-p", str(pid)).strip() or 0) / 1024

p0 = pressure(); print(f"[{label}] pressure before load: {p0}", flush=True)
if p0 >= 4: sys.exit(3)
log_off = os.path.getsize(LOG)
t = time.time(); post("/api/generate", {"model": MODEL, "options": {"num_ctx": 8192}}); load_s = time.time() - t
pid, cmd = runner()
open(P("argv.txt"), "w").write(cmd + "\n")
open(P("env.txt"), "w").write("\n".join(x for x in sh("ps", "eww", "-o", "command=", "-p", str(pid)).split(" ") if re.match(r"^[A-Z_][A-Z0-9_]*=", x)) + "\n")
port = int(cmd.split("--port ")[1].split()[0])
json.dump(get(f"http://127.0.0.1:{port}/props"), open(P("props.json"), "w"), indent=1)
mb, out = fp(pid); open(P("footprint-0.txt"), "w").write(out)
samples = open(P("samples.jsonl"), "w")
samples.write(json.dumps({"i": 0, "runner_pid": pid, "rss_mb": rss_mb(pid), "footprint_mb": mb, "pressure": pressure(), "load_s": load_s}) + "\n"); samples.flush()
prompts = [json.loads(l) for l in open(prompts_path)][:limit]
for i, pr in enumerate(prompts, 1):
    pl = pressure()
    if pl >= 4:
        print(f"[{label}] RED before request {i}, stopping", flush=True); samples.write(json.dumps({"i": i, "abort": "red"}) + "\n"); sys.exit(3)
    t = time.time()
    r = post("/api/generate", {"model": MODEL, "prompt": pr["prompt"], "stream": False, "think": False, "options": {"num_ctx": 8192}})
    wall = time.time() - t
    p2, c2 = runner()
    mb, out = fp(p2)
    if i in (10, 25, len(prompts)): open(P(f"footprint-{i}.txt"), "w").write(out)
    rec = {"i": i, "qa_id": pr["qa_id"], "runner_pid": p2, "wall_s": round(wall, 3),
           "total_s": r["total_duration"] / 1e9, "load_s": r.get("load_duration", 0) / 1e9,
           "prompt_tokens": r.get("prompt_eval_count"), "prompt_s": r.get("prompt_eval_duration", 0) / 1e9,
           "eval_tokens": r.get("eval_count"), "eval_s": r.get("eval_duration", 0) / 1e9,
           "rss_mb": rss_mb(p2), "footprint_mb": mb, "pressure_before": pl, "pressure_after": pressure()}
    samples.write(json.dumps(rec) + "\n"); samples.flush()
    print(f"[{label}] {i:2d} wall={wall:5.2f}s ptok={rec['prompt_tokens']} rss={rec['rss_mb']:.0f}MB fp={mb:.0f}MB pres={rec['pressure_after']}", flush=True)
with open(LOG, "rb") as f:
    f.seek(log_off); new = f.read().decode("utf-8", "replace")
open(P("server-log.txt"), "w").write(new)
