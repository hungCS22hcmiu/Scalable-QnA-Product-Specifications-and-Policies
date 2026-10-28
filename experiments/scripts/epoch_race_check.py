"""Item 4.2, done condition 10: the live epoch race. citable: no, NOT a measurement.

    make epoch-race-check

An edit advances the dataset epoch while a generation is running. The epoch guard must then discard
that generation's write-back (interfaces.md E): the client still gets the answer, the record says
`writeback_discarded: true` with `entry_id ""`, and Redis gets no t1:, t2: or entry: key for it.

The script is the check, and it cannot pass by accident: only an epoch mismatch sets the flag, so
question B passes only if the race really happened. If B's write-back was NOT discarded, the edit
landed too late to race the generation and the script says "race not forced" (exit 2); re-run it.

What it does:
  1. Builds the gateway, and makes a temp directory with its own epoch file (value 1).
  2. Starts rag.server (127.0.0.1:50053) and the gateway (127.0.0.1:18080) on that one file. The
     gateway runs MUTATION=on, because an edit happens here and the §H invariant forbids a discard
     under mutation: off.
  3. Picks two products, so neither question can be a Tier-2 hit on the other.
  4. Question A, no edit. Its write-back must land (this also loads both models).
  5. Question B: sent in a thread; 1.5 s later the epoch is advanced (python -m rag.epoch advance).
  6. Stops both processes with SIGINT (the gateway flushes its evaluation log), then checks the
     records and the Redis key diff.
  7. Deletes exactly the keys this run wrote. Never FLUSHDB: on this Redis a FLUSHDB drops every
     search index (docs/work/2026-10-27-dependency-map/design.md section 4).
  8. Writes both records, the key diff, both process logs and the pressure level to --evidence-dir.

Check the memory pressure level first, every time (CLAUDE.md): the LLM is loaded. Do not run it
beside `make verify` or any other Redis test.
"""

import argparse
import json
import os
import random
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import redis

ROOT = Path(__file__).resolve().parents[2]
RAG_ADDR = "127.0.0.1:50053"
GW_ADDR = "127.0.0.1:18080"
OLLAMA_VERSION_URL = "http://localhost:11434/api/version"
KEY_PATTERNS = ("t1:*", "t2:*", "entry:*")

# Settings that would change what the gateway does. A check that runs the defaults is the same
# check every time, whatever the calling shell exports.
SCRUBBED_ENV = (
    "REDIS_URL",
    "UI_DIR",
    "SUPPORT_GATE",
    "LANE_SIGMA",
    "LANE_SIGMA_HI",
    "CACHE_CAPACITY",
    "CONFIG_ID",
    "REUSE_TAU_HIGH",
)


class Checks:
    """One PASS or FAIL line per check, in the order they run."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failed = 0

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        line = f"{'PASS' if ok else 'FAIL'}  {name}" + (
            f"  [{detail}]" if detail else ""
        )
        print(line, flush=True)
        self.lines.append(line)
        if not ok:
            self.failed += 1
        return ok


def port_taken(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_listening(
    port: int, proc: subprocess.Popen, label: str, timeout_s: float = 90
) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"{label} exited on startup with code {proc.returncode}")
        if port_taken(port):
            return
        time.sleep(0.5)
    raise RuntimeError(f"{label} not listening on :{port} after {timeout_s:.0f} s")


def pressure_level() -> str:
    out = subprocess.run(
        ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip() or "unknown"


def doc_of(chunk_id: str) -> str:
    return chunk_id.split("#", 1)[0]


def pick_products(r: redis.Redis) -> list[tuple[str, str]]:
    """Two product docs of different categories as (doc_id, title).

    Different products give different Tier-1 keys and different namespaces, so neither question can
    be a hit on the other. Products that a cached entry already cites are avoided, so a leftover
    entry cannot answer a question as a Tier-2 hit; if that leaves fewer than two categories, all
    products are used and the MISS check on question A says if it mattered.
    """
    docs = sorted(
        {
            doc_of(k.split("::", 1)[1])
            for k in r.scan_iter("corpus::product-*", count=1000)
        }
    )
    busy: set[str] = set()
    for key in r.scan_iter("t2:*", count=1000):
        raw = r.hget(key, "source_chunk_ids")
        if raw:
            busy.update(doc_of(c) for c in json.loads(raw))

    def two(candidates: list[str]) -> list[str]:
        picked: list[str] = []
        for d in candidates:
            if all(d.split("-")[1] != p.split("-")[1] for p in picked):
                picked.append(d)
            if len(picked) == 2:
                break
        return picked

    chosen = two([d for d in docs if d not in busy]) or []
    if len(chosen) < 2:
        chosen = two(docs)
    if len(chosen) < 2:
        raise RuntimeError(
            f"need product docs of two categories in Redis, found {docs}"
        )
    out = []
    for d in chosen:
        text = r.hget(f"corpus::{d}#chunk-0", "text") or ""
        first = text.splitlines()[0] if text else ""
        out.append((d, first.removeprefix("Product:").strip() or d))
    return out


def ask(
    question: str, product_id: str, timeout_s: float = 600
) -> tuple[int, dict, float]:
    body = json.dumps({"question": question, "product_id": product_id}).encode()
    req = urllib.request.Request(
        f"http://{GW_ADDR}/ask", data=body, headers={"content-type": "application/json"}
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.status, json.loads(resp.read()), time.monotonic() - t0
    except urllib.error.HTTPError as e:
        return (
            e.code,
            {"error": e.read().decode(errors="replace")},
            time.monotonic() - t0,
        )


def snapshot(r: redis.Redis) -> set[str]:
    keys: set[str] = set()
    for pattern in KEY_PATTERNS:
        keys.update(r.scan_iter(pattern, count=1000))
    return keys


def wait_for_new_entry(
    r: redis.Redis, before: set[str], timeout_s: float = 10
) -> set[str]:
    """The registration is queued to the dependency map's writer, so entry:{A} lands a moment after
    the response. The snapshot is taken once it has."""
    deadline = time.monotonic() + timeout_s
    while True:
        now = snapshot(r)
        if (
            any(k.startswith("entry:") for k in now - before)
            or time.monotonic() > deadline
        ):
            return now
        time.sleep(0.1)


def read_records(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                records[rec["request_id"]] = rec
    return records


def purge_entry(r: redis.Redis, rec: dict) -> list[str]:
    """Delete exactly the keys one written entry owns, and nothing else. Never FLUSHDB."""
    eid = rec.get("entry_id") or ""
    if not eid:
        return []
    done = []
    t1_key = rec.get("t1_key") or ""
    # Same rule as cache.PurgeEntry: Tier 1 is keyed by the query, so delete it only if it still
    # names this entry.
    if t1_key and r.hget(t1_key, "entry_id") == eid:
        r.delete(t1_key)
        done.append(t1_key)
    # lru:t1keys:{eid} is the cache's per-entry set of Tier-1 keys (interfaces.md §D v0.19).
    for key in (f"t2:{eid}", f"entry:{eid}", f"lru:t1keys:{eid}"):
        if r.delete(key):
            done.append(key)
    for chunk in rec.get("entry_sources") or []:
        if r.srem(f"dep:{chunk}", eid):  # Redis drops a set when its last member goes
            done.append(f"dep:{chunk} -= {eid}")
    if r.zrem("lru:entries", eid):
        done.append(f"lru:entries -= {eid}")
    return done


def stop(proc: subprocess.Popen | None, label: str, grace_s: float = 30) -> int | None:
    if proc is None or proc.poll() is not None:
        return None if proc is None else proc.returncode
    proc.send_signal(signal.SIGINT)
    try:
        return proc.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        print(f"  {label} ignored SIGINT for {grace_s:.0f} s; killing it", flush=True)
        proc.kill()
        return proc.wait()


def prepare_evidence_dir(path: Path) -> Path:
    """A previous attempt's evidence is kept (a 'race not forced' first run is worth reading), so a
    non-empty directory is renamed, never overwritten."""
    if path.exists() and any(path.iterdir()):
        stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).strftime(
            "%Y%m%d-%H%M%S"
        )
        path.rename(path.with_name(f"{path.name}.prev-{stamp}"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Item 4.2 DC 10: advance the dataset epoch while a generation runs and check "
        "that its write-back is discarded. Loads the LLM; citable: no."
    )
    ap.add_argument(
        "--evidence-dir", required=True, help="where the records, key diff and logs go"
    )
    ap.add_argument(
        "--advance-after",
        type=float,
        default=1.5,
        help="seconds after sending question B before the epoch is advanced (1.5)",
    )
    args = ap.parse_args()

    ev = prepare_evidence_dir(Path(args.evidence_dir).resolve())
    checks = Checks()
    level_before = pressure_level()
    print(
        f"memory pressure level: {level_before} (1 = green, 2 = yellow, 4 = red; citable: no)"
    )

    # --- preflight: refuse to start on anything that would make the run mean something else ---
    r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
    try:
        r.ping()
    except redis.RedisError as e:
        print(f"FAIL  redis does not answer: {e}")
        return 1
    for port in (50053, 18080):
        if port_taken(port):
            print(f"FAIL  port {port} already has a listener; stop it first")
            return 1
    try:
        urllib.request.urlopen(OLLAMA_VERSION_URL, timeout=3).read()
    except (urllib.error.URLError, OSError) as e:
        print(f"FAIL  Ollama does not answer at {OLLAMA_VERSION_URL}: {e}")
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="epoch-race-"))
    epoch_file = tmp / "dataset-epoch"
    epoch_file.write_text("1\n")
    results_dir = tmp / "results"
    run_id = "epoch-race-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    records_path = results_dir / run_id / "raw" / "requests.jsonl"
    print(f"temp dir {tmp}; epoch file {epoch_file}; run_id {run_id}")

    env = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
    env["DATASET_EPOCH_FILE"] = str(epoch_file)
    env["RAG_GRPC_ADDR"] = RAG_ADDR
    gw_env = {
        **env,
        "HTTP_ADDR": GW_ADDR,
        "MUTATION": "on",
        "RUN_ID": run_id,
        "RESULTS_DIR": str(results_dir),
        "OLLAMA_NUM_PARALLEL": "1",
    }

    rag_proc = gw_proc = None
    rag_log = open(ev / "rag-server.log", "w")  # noqa: SIM115 - closed in the finally below
    gw_log = open(ev / "gateway.log", "w")  # noqa: SIM115
    s0 = s1 = s2 = None
    prods: list[tuple[str, str]] = []
    resp: dict[str, dict] = {}
    timing: dict[str, float] = {}
    run_error = ""
    gw_code = None
    records: dict[str, dict] = {}

    try:
        try:
            binary = tmp / "gateway-bin"
            subprocess.run(
                ["go", "build", "-o", str(binary), "./cmd/gateway"],
                cwd=ROOT / "gateway",
                check=True,
            )
            rag_proc = subprocess.Popen(
                [sys.executable, "-m", "rag.server"],
                cwd=ROOT / "rag",
                env=env,
                stdout=rag_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            wait_listening(50053, rag_proc, "rag.server")
            gw_proc = subprocess.Popen(
                [str(binary)],
                cwd=ROOT,
                env=gw_env,
                stdout=gw_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            wait_listening(18080, gw_proc, "gateway")
            print("rag.server and the gateway are listening", flush=True)

            prods = pick_products(r)
            (pa, ta), (pb, tb) = prods
            token = f"{random.randrange(16**6):06x}"
            # A long answer keeps the generation running past the advance. The token keeps the
            # question out of any Tier-1 key and Tier-2 neighbourhood an older run left behind.
            qa = (
                f"In detail, list every specification of the {ta} one by one and say what each "
                f"one means for a buyer. (ref {token}a)"
            )
            qb = (
                f"In detail, list every specification of the {tb} one by one and say what each "
                f"one means for a buyer. (ref {token}b)"
            )
            print(f"A: {pa}   B: {pb}", flush=True)

            s0 = snapshot(r)
            status, body, secs = ask(qa, pa)
            resp["A"], timing["A"] = {"status": status, **body}, secs
            print(
                f"A answered: HTTP {status}, cache={body.get('cache')}, {secs:.1f} s",
                flush=True,
            )
            s1 = wait_for_new_entry(r, s0)

            out: dict = {}

            def send_b() -> None:
                t0 = time.monotonic()
                st, bd, _ = ask(qb, pb)
                out.update(status=st, body=bd, secs=time.monotonic() - t0)

            th = threading.Thread(target=send_b, daemon=True)
            th.start()
            time.sleep(args.advance_after)
            adv = subprocess.run(
                [sys.executable, "-m", "rag.epoch", "advance"],
                cwd=ROOT / "rag",
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            print(f"advance: {adv.stdout.strip() or adv.stderr.strip()}", flush=True)
            if adv.returncode != 0:
                raise RuntimeError(f"rag.epoch advance failed: {adv.stderr.strip()}")
            th.join(timeout=600)
            if th.is_alive() or "body" not in out:
                raise RuntimeError("question B did not return")
            resp["B"], timing["B"] = (
                {"status": out["status"], **out["body"]},
                out["secs"],
            )
            print(
                f"B answered: HTTP {out['status']}, cache={out['body'].get('cache')}, "
                f"{out['secs']:.1f} s (epoch advanced {args.advance_after} s after sending)",
                flush=True,
            )
            time.sleep(1.0)  # let any late write settle before the second snapshot
            s2 = snapshot(r)
        except Exception as e:  # noqa: BLE001 - reported below, then cleaned up
            run_error = f"{type(e).__name__}: {e}"
            print(f"FAIL  the run stopped early: {run_error}", flush=True)
        finally:
            gw_code = stop(gw_proc, "gateway")  # first: it flushes the evaluation log
            stop(rag_proc, "rag.server")
            rag_log.close()
            gw_log.close()

        records = read_records(records_path)
        a_rec = records.get(resp.get("A", {}).get("request_id", ""), {})
        b_rec = records.get(resp.get("B", {}).get("request_id", ""), {})
        race_not_forced = False

        if not run_error:
            ca, cb = resp["A"], resp["B"]
            checks.check(
                "A: HTTP 200, a MISS with an answer",
                ca["status"] == 200
                and ca.get("cache") == "MISS"
                and bool(ca.get("answer")),
                f"status={ca['status']} cache={ca.get('cache')}",
            )
            checks.check(
                "A: record writeback_discarded false",
                a_rec.get("writeback_discarded") is False,
                f"got {a_rec.get('writeback_discarded')!r}",
            )
            a_id = a_rec.get("entry_id") or ""
            checks.check("A: record names an entry", bool(a_id), f"entry_id={a_id!r}")
            a_keys = {
                k for k in (a_rec.get("t1_key"), f"t2:{a_id}", f"entry:{a_id}") if k
            }
            missing = (
                sorted(k for k in a_keys if not r.exists(k))
                if a_id
                else ["(no entry_id)"]
            )
            checks.check(
                "A: its t1:, t2: and entry: keys exist in Redis",
                not missing,
                f"missing {missing}" if missing else "",
            )
            checks.check(
                "A: dataset_epoch_at_retrieval is the file's value 1",
                a_rec.get("dataset_epoch_at_retrieval") == 1,
                f"got {a_rec.get('dataset_epoch_at_retrieval')!r}",
            )

            checks.check(
                "B: HTTP 200 with an answer (the client still gets it)",
                cb["status"] == 200 and bool(cb.get("answer")),
                f"status={cb['status']} answer_len={len(cb.get('answer') or '')}",
            )
            checks.check(
                "B: cache MISS",
                cb.get("cache") == "MISS" and b_rec.get("cache") == "MISS",
                f"response={cb.get('cache')} record={b_rec.get('cache')}",
            )
            checks.check(
                "B: dataset_epoch_at_retrieval is 1 (read before the advance)",
                b_rec.get("dataset_epoch_at_retrieval") == 1,
                f"got {b_rec.get('dataset_epoch_at_retrieval')!r}",
            )
            discarded = b_rec.get("writeback_discarded")
            if discarded is False:
                race_not_forced = True
                print(
                    f"FAIL  race not forced: B's write-back was not discarded. t_generate_ms="
                    f"{b_rec.get('t_generate_ms')}; the epoch was advanced {args.advance_after} s "
                    f"after B was sent, so a generation shorter than that cannot race it. "
                    f"Re-run once.",
                    flush=True,
                )
                checks.failed += 1
            else:
                checks.check(
                    "B: record writeback_discarded true",
                    discarded is True,
                    f"got {discarded!r}",
                )
                checks.check(
                    "B: record entry_id is empty",
                    b_rec.get("entry_id") == "",
                    f"got {b_rec.get('entry_id')!r}",
                )
                checks.check(
                    "B: record entry_sources is null",
                    b_rec.get("entry_sources") is None,
                    f"got {b_rec.get('entry_sources')!r}",
                )
            new_for_b = (
                sorted(s2 - s1)
                if s1 is not None and s2 is not None
                else ["(no snapshot)"]
            )
            checks.check(
                "no t1:, t2: or entry: key appeared between A's end and B's end",
                not new_for_b,
                f"new keys {new_for_b}" if new_for_b else "",
            )
            checks.check(
                "epoch file now holds 2",
                epoch_file.read_text().strip() == "2",
                f"holds {epoch_file.read_text().strip()!r}",
            )

        # Both services read ONE file: each start-up line names the temp path (failure mode 6).
        checks.check(
            "gateway log names the epoch file",
            f"dataset_epoch_file={epoch_file}" in (ev / "gateway.log").read_text(),
            str(epoch_file),
        )
        checks.check(
            "rag.server log names the epoch file",
            f"dataset_epoch_file={epoch_file}" in (ev / "rag-server.log").read_text(),
            str(epoch_file),
        )
        checks.check(
            "gateway exited cleanly after SIGINT", gw_code == 0, f"exit code {gw_code}"
        )

        # --- evidence, then cleanup (the records are needed for both) ---
        for name, rec in (("A", a_rec), ("B", b_rec)):
            (ev / f"record-{name}.json").write_text(json.dumps(rec, indent=2) + "\n")
        for name, body in resp.items():
            (ev / f"response-{name}.json").write_text(json.dumps(body, indent=2) + "\n")
        if records_path.exists():
            (ev / "requests.jsonl").write_text(records_path.read_text())
        diff_lines = ["# keys that appeared while A ran (S1 - S0)"]
        diff_lines += [f"+ {k}" for k in sorted((s1 or set()) - (s0 or set()))]
        diff_lines += [
            "# keys that appeared between A's end and B's end (S2 - S1): must be empty"
        ]
        diff_lines += [f"+ {k}" for k in sorted((s2 or set()) - (s1 or set()))]
        (ev / "key-diff.txt").write_text("\n".join(diff_lines) + "\n")
    finally:
        # Delete exactly what this run wrote. A and, if the guard failed, B; never FLUSHDB.
        removed: list[str] = []
        for rec in records.values():
            removed += purge_entry(r, rec)
        leftovers = sorted(snapshot(r) - (s0 or set())) if s0 is not None else []
        (ev / "cleanup.txt").write_text(
            "removed:\n"
            + "".join(f"  {k}\n" for k in removed)
            + "keys new since the start that remain (should be none):\n"
            + "".join(f"  {k}\n" for k in leftovers)
        )
        print(
            f"cleanup removed {len(removed)} item(s); {len(leftovers)} new key(s) remain"
            + (f": {leftovers}" if leftovers else ""),
            flush=True,
        )

    level_after = pressure_level()
    (ev / "pressure.txt").write_text(
        f"before the run: {level_before}\nafter the run:  {level_after}\n"
        "(1 = green, 2 = yellow, 4 = red; this check is citable: no)\n"
    )
    (ev / "summary.txt").write_text("\n".join(checks.lines) + "\n")
    print(f"memory pressure level after: {level_after}")
    print(f"evidence: {ev}")

    if run_error:
        return 1
    if race_not_forced:
        return 2
    if checks.failed:
        print(f"FAILED: {checks.failed} check(s)")
        return 1
    print("PASS: the epoch advanced mid-generation, and the write-back was discarded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
