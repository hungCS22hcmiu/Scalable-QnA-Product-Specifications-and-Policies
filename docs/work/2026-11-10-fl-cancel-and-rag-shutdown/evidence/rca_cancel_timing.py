"""RCA follow-up 2, 2026-11-10, citable: no. Straight to Ollama, the model already loaded.

The runner (llama-server) logs with no timestamps. This script stamps each new line of
~/.ollama/logs/server.log as it appears (polled every 5 ms), on the same clock as the cut, to see WHEN
the runner logs "stop: cancel task" and when it releases the slot. If the cancel line appears about at
the cut, the runner sees the close at once and acts late. If it appears only at the end of prefill, it
sees the close late.

Usage: python3 rca_cancel_timing.py BODY_JSON T REPS   (BODY_JSON is outside the repository: it holds
corpus text). Pressure is read before every call; 4 stops it.
"""

import os
import re
import subprocess
import sys
import threading
import time

LOG = os.path.expanduser("~/.ollama/logs/server.log")
URL = "http://localhost:11434/api/generate"
B = ('{"model":"qwen3.5:2b-q4_K_M","prompt":"Reply with exactly one word: OK.","stream":false,'
     '"think":false,"options":{"num_ctx":8192}}')
KEEP = re.compile(r"task\.n_tokens|stop: cancel task|stop processing|GIN.*/api/generate")


def pressure() -> str:
    return subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
                          capture_output=True, text=True).stdout.strip()


def gate(what: str) -> None:
    p = pressure()
    print(f"  [pressure before {what}: {p}]", flush=True)
    if p == "4":
        print("STOP: pressure 4 (red)")
        sys.exit(2)


def main() -> None:
    body, cut, reps = sys.argv[1], float(sys.argv[2]), int(sys.argv[3])
    print(f"rca_cancel_timing.py, {time.strftime('%Y-%m-%d %H:%M:%S')}, citable: no; T = {cut} s")
    for i in range(1, reps + 1):
        gate(f"round {i}")
        stamped: list[tuple[float, str]] = []
        stop = threading.Event()
        f = open(LOG, errors="replace")
        f.seek(0, os.SEEK_END)
        t0 = time.monotonic()

        def follow() -> None:
            buf = ""
            while not stop.is_set():
                chunk = f.read()
                if chunk:
                    now = time.monotonic() - t0
                    buf += chunk
                    *lines, buf = buf.split("\n")
                    stamped.extend((now, ln) for ln in lines if KEEP.search(ln))
                else:
                    time.sleep(0.005)

        th = threading.Thread(target=follow, daemon=True)
        th.start()
        subprocess.run(["curl", "-s", "-o", "/dev/null", "--max-time", str(cut), "-X", "POST", URL,
                        "-d", f"@{body}"])
        t_cut = time.monotonic() - t0
        subprocess.run(["curl", "-s", "-o", "/dev/null", "-X", "POST", URL, "-d", B])
        t_b = time.monotonic() - t0
        time.sleep(0.3)
        stop.set()
        th.join()
        f.close()
        print(f"  round {i}: A sent at 0.000, curl gave up at {t_cut:.3f}, B done at {t_b:.3f} (s)")
        for t, ln in stamped:
            ln = re.sub(r"^(slot|srv) +", "", ln)
            print(f"    +{t:6.3f} s  {ln}")


if __name__ == "__main__":
    main()
