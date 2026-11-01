"""Generator comparison (2026-11-01, diagnostic, citable: no). One model per call, run one after another.

Each model answers the 30 rows of the judge-harness sufficiency sheet (`sufficiency-v2.md`) from the same gold
chunks (`retrieve.fetch_by_ids`, in the index's order) with the same served prompt (`generate._build_prompt`).
Options: `num_ctx` 8192, `temperature` 0, `seed` 20261101; every other decoding value is the model's own default
and is recorded. `think: false` is sent to a model whose `/api/show` lists `thinking`, and checked, not assumed.

Measured per model: the answers; decode and prefill speed from Ollama's own counters; the runner's peak
`footprint` (ADR-017: never RSS or /api/ps) and the peak pressure level, sampled every second with the embedding
model also resident; the runner's slot count (argv and /props); and three concurrent requests against the same
three requests sent one at a time. A pressure reading of 4 stops the model and ends the arm.

Never touches rag.config, the reference set, the judge or the pre-registration.

Usage (from the repo root):  python3 docs/work/2026-11-01-generator-selection/compare_generators.py TAG
"""

import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, "experiments/scripts")
import judge_references as jr

from rag import config, generate, retrieve

TRAIL = Path("docs/work/2026-11-01-generator-selection")
SHEET = Path("docs/work/2026-10-30-judge-harness/evidence/private/sufficiency-v2.md")
OUT_ROOT = TRAIL / "evidence/private"
BASE = config.OLLAMA_BASE_URL.rstrip("/")
OPTIONS = {"num_ctx": 8192, "temperature": 0, "seed": 20261101}
BLOB = re.compile(r"sha256-[0-9a-f]{64}")


def sh(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=False).stdout


def pressure() -> int:
    return int(sh(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"]).strip())


def footprint_mb(pid: int) -> float | None:
    m = re.search(
        r"Footprint:\s*([\d.]+)\s*(KB|MB|GB)", sh(["footprint", "-p", str(pid)])
    )
    if not m:
        return None
    return float(m.group(1)) * {"KB": 1 / 1024, "MB": 1, "GB": 1024}[m.group(2)]


def loaded() -> list[str]:
    return [m["name"] for m in jr.http_json(f"{BASE}/api/ps")["models"]]


def unload_all() -> None:
    for name in loaded():
        sh(["ollama", "stop", name])
    for _ in range(30):
        if not loaded():
            return
        time.sleep(1)
    raise SystemExit(f"models still loaded: {loaded()}")


def find_runner(blob: str) -> tuple[int | None, str]:
    server = sh(["pgrep", "-f", "-x", ".*/ollama serve"]).split()
    server_pid = int(server[0]) if server else -1
    for row in sh(["ps", "-axww", "-o", "pid=,ppid=,command="]).splitlines():
        parts = row.split(None, 2)
        if len(parts) == 3 and int(parts[1]) == server_pid and blob in parts[2]:
            return int(parts[0]), parts[2]
    return None, ""


def flag(command: str, *names: str) -> str | None:
    tokens = command.split()
    for i, t in enumerate(tokens[:-1]):
        if t in names:
            return tokens[i + 1]
    return None


def sheet_rows() -> list[dict]:
    text = SHEET.read_text()
    index = {r["qa_id"]: r for r in jr.read_index(jr.REFERENCES_DIR / "validation")}
    rows = []
    for part in re.split(r"(?m)^(?=## \d+\. )", text)[1:]:
        m = re.match(r"## (\d+)\. (\S+)", part)
        row = dict(index[m.group(2)])
        row["row"] = int(m.group(1))
        row["sufficient"] = jr.SUFFICIENT.findall(part)[-1]
        row["reference_right_2b"] = jr.REFERENCE_RIGHT.findall(part)[-1]
        rows.append(row)
    assert [r["row"] for r in rows] == list(range(1, 31))
    return rows


def prompt_for(r: dict) -> str:
    chunks, _ = retrieve.fetch_by_ids(list(r["chunk_ids"]))
    if [c.chunk_id for c in chunks] != list(r["chunk_ids"]):
        raise SystemExit(
            f"row {r['row']}: fetch_by_ids did not return the gold chunks in order"
        )
    return generate._build_prompt(r["question"], chunks)


def ask(model: str, prompt: str, think: bool | None) -> tuple[dict, float]:
    body = {"model": model, "prompt": prompt, "stream": False, "options": OPTIONS}
    if think is not None:
        body["think"] = think
    t0 = time.monotonic()
    reply = jr.http_json(f"{BASE}/api/generate", body, timeout=900.0)
    return reply, time.monotonic() - t0


class Sampler(threading.Thread):
    """Pressure and the runner's footprint every second; stops the model at pressure 4."""

    def __init__(self, model: str):
        super().__init__(daemon=True)
        self.model, self.pid = model, None
        self.max_pressure, self.peak_mb, self.readings = 0, 0.0, 0
        self.aborted, self._stop = False, threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            level = pressure()
            self.max_pressure = max(self.max_pressure, level)
            self.readings += 1
            if self.pid:
                mb = footprint_mb(self.pid)
                if mb:
                    self.peak_mb = max(self.peak_mb, mb)
            if level >= 4 and not self.aborted:
                self.aborted = True
                sh(["ollama", "stop", self.model])
            self._stop.wait(1.0)

    def stop(self) -> None:
        self._stop.set()


def main(model: str) -> int:
    out = OUT_ROOT / model.replace(":", "_").replace("/", "_")
    if out.exists():
        print(f"REFUSED: {out} exists")
        return 1
    unload_all()
    show = jr.http_json(f"{BASE}/api/show", {"model": model})
    caps = show.get("capabilities", [])
    think = False if "thinking" in caps else None
    tags = jr.http_json(f"{BASE}/api/tags")
    digest = next(m["digest"] for m in tags["models"] if m["name"] == model)
    blob = BLOB.search(
        next(ln for ln in show["modelfile"].splitlines() if ln.startswith("FROM "))
    )
    record = {
        "model": model,
        "digest": digest,
        "blob": blob.group(0) if blob else None,
        "details": show.get("details"),
        "capabilities": caps,
        "defaults": show.get("parameters", ""),
        "options": OPTIONS,
        "think_sent": think,
        "ollama_version": jr.http_json(f"{BASE}/api/version")["version"],
        "prompt_sha256": jr.sha256_bytes(generate._PROMPT_TEMPLATE.encode("utf-8")),
        "pressure_before": pressure(),
        "redis": sh(["redis-cli", "PING"]).strip(),
    }
    print(f"{model}: pressure before {record['pressure_before']}; capabilities {caps}")
    rows = sheet_rows()
    prompts = {r["row"]: prompt_for(r) for r in rows}

    sampler = Sampler(model)
    sampler.start()
    try:
        _, warm_s = ask(model, "Say OK.", think)
        jr.http_json(
            f"{BASE}/api/embed",
            {"model": config.EMBEDDING_MODEL, "input": "stack"},
            120.0,
        )
        record["load_seconds"] = round(warm_s, 1)
        pid, command = find_runner(record["blob"] or "")
        sampler.pid = pid
        record["runner"] = {
            "kind": Path(command.split()[0]).name if command else None,
            "np_argv": flag(command, "-np", "--parallel"),
            "ctx_argv": flag(command, "-c", "--ctx-size"),
        }
        port = flag(command, "--port")
        if port:
            try:
                props = jr.http_json(f"http://127.0.0.1:{port}/props")
                record["runner"]["total_slots"] = props.get("total_slots")
                record["runner"]["n_ctx"] = props.get(
                    "default_generation_settings", {}
                ).get("n_ctx")
            except OSError as e:
                record["runner"]["props_error"] = str(e)
        print(f"  loaded in {warm_s:.1f}s; runner {record['runner']}")

        (out / "answers").mkdir(parents=True)
        results = []
        for r in rows:
            if sampler.aborted:
                break
            reply, wall = ask(model, prompts[r["row"]], think)
            text = reply.get("response", "")
            sha = jr.sha256_bytes(text.encode("utf-8"))
            (out / "answers" / f"{sha}.txt").write_text(text)
            results.append(
                {
                    "row": r["row"],
                    "qa_id": r["qa_id"],
                    "stratum": r["stratum"],
                    "sufficient": r["sufficient"],
                    "reference_right_2b": r["reference_right_2b"],
                    "answer_sha256": sha,
                    "chars": len(text),
                    "wall_s": round(wall, 2),
                    "eval_count": reply.get("eval_count"),
                    "eval_s": (reply.get("eval_duration") or 0) / 1e9,
                    "prompt_tokens": reply.get("prompt_eval_count"),
                    "prompt_s": (reply.get("prompt_eval_duration") or 0) / 1e9,
                    "thinking_chars": len(reply.get("thinking") or ""),
                    "think_tag": "<think" in text or "</think>" in text,
                }
            )
            if r["row"] % 10 == 0:
                print(f"  {r['row']}/30; pressure max so far {sampler.max_pressure}")

        if not sampler.aborted:
            # Is the switch honoured? With think on, a thinking model should fill `thinking`.
            if think is not None:
                on, _ = ask(model, prompts[1], True)
                record["think_on_control_chars"] = len(on.get("thinking") or "")
            # Concurrency: rows 1-3 together, against the same rows one at a time above.
            spans: dict[int, tuple[float, float]] = {}

            def one(n: int, t_start: float) -> None:
                a = time.monotonic()
                ask(model, prompts[n], think)
                spans[n] = (round(a - t_start, 2), round(time.monotonic() - t_start, 2))

            t_start = time.monotonic()
            threads = [
                threading.Thread(target=one, args=(n, t_start)) for n in (1, 2, 3)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            alone = sum(x["wall_s"] for x in results if x["row"] in (1, 2, 3))
            record["concurrency"] = {
                "spans_s": {str(k): v for k, v in sorted(spans.items())},
                "together_wall_s": round(max(e for _, e in spans.values()), 2),
                "alone_sum_s": round(alone, 2),
            }
    finally:
        sampler.stop()
        sampler.join()
        sh(["ollama", "stop", model])

    record.update(
        {
            "aborted_at_pressure_4": sampler.aborted,
            "max_pressure": sampler.max_pressure,
            "peak_footprint_mb": round(sampler.peak_mb),
            "samples": sampler.readings,
            "answered": len(results),
            "pressure_after": pressure(),
        }
    )
    (out / "index.jsonl").write_text("".join(json.dumps(x) + "\n" for x in results))
    (out / "run.json").write_text(json.dumps(record, indent=2) + "\n")
    print(
        f"  done: {len(results)} answers; peak footprint {record['peak_footprint_mb']} MB; "
        f"max pressure {record['max_pressure']}; aborted {sampler.aborted}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
