"""Item 4.4: the live update-set run. citable: no. NOT a measurement.

    make update-set-check EVIDENCE=docs/work/<task>/evidence/live1

It fills a real cache through the gateway, applies the 20 edits of the update set with the real edit
tool, reads both cache tiers, and has `score_update_set.py` turn the saved IDs into completeness,
exactness and precision. It also forces one race (done condition 8) and reads where every edit landed
(done condition 13). The human's decision (design.md section 1): memory pressure is recorded, never a
gate, and the LLM may be loaded.

While it runs, Redis differs from `v1`. Nothing else may use Redis or Ollama then. It uses its own
epoch file, so `data/dataset-epoch` is not touched, and it leaves `CACHE_CAPACITY` unset (unbounded),
so no eviction can look like a purge.

Order:
  1. Preconditions: Redis, the manifest hash, every edited chunk holds its `before`, the probe file,
     free ports, Ollama. The original text and vector of each edited chunk are saved.
  2. The race (lifetime 1 of rag.server and the gateway). Reset, start, send a question that the probe
     says retrieves the 30 -> 14 day chunk, `apply` that edit 1.5 s later, restore the chunk, stop.
  3. Reset, start again (lifetime 2). A reset under a live gateway would leave its tombstones pointing
     at deleted keys, and `make cache-reset` refuses to run under one, so the race and the fill do not
     share a lifetime.
  4. Fill: up to 3 validation questions per edit, from different clusters, and 10 that no edit touches.
  5. Snapshot before. The 20 edits through `python -m rag.edit`. DC 13's reads. Snapshot after.
  6. Ask every dependent's question again.
  7. Restore the 20 chunks (reverse order), stop both processes, reset, check every chunk again holds
     its saved text and vector.
  8. Write the evidence and run the scorer.

Evidence (design.md section 3, the author's decision of 2026-10-29): every file with a `qa_id` or a chunk
ID, which can carry an ASIN, stays in `EVIDENCE/private/` (gitignored), with the request logs and process
logs that hold question text. That is `oracle.json`, `labels.json`, both snapshots, `replies.json`,
`reask.json`, `race.json`, `dc13.json`, `summary.txt` and `run-time.txt`. Only `score.json` (counts, keyed
by `edit_id`) and `pressure.txt` are written to `EVIDENCE/`, and they are committed.

Exit codes: 0 every check passed · 1 a check failed or the run stopped · 2 "race not forced" (re-run).
"""

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import cache_reset
import epoch_race_check as erc
import redis
import score_update_set
import update_set

ROOT = Path(__file__).resolve().parents[2]
RAG_PORT = 50054
GW_PORT = 18081
RAG_ADDR = f"127.0.0.1:{RAG_PORT}"
GW_ADDR = f"127.0.0.1:{GW_PORT}"
FILL_PER_EDIT = 3
CONTROLS = 10
COSINE_MIN = 0.9999
NO_ENTRY_ID = "<no entry_id>"
DEFAULT_PROBE = (
    ROOT
    / "docs"
    / "work"
    / "2026-10-29-update-set"
    / "evidence"
    / "private"
    / "probe.json"
)


# --------------------------------------------------------------------------------------------------
# The snapshot: what the two tiers hold, not what the cache's own bookkeeping says.
# --------------------------------------------------------------------------------------------------


def _s(value) -> str:
    return value.decode() if isinstance(value, bytes) else value


def snapshot(client) -> dict[str, dict]:
    """What the two cache tiers hold, as `entry_id -> {t1_keys, t2, entry}`.

    It does not trust the cache's own bookkeeping. Every `t1:*` key is read for its own `entry_id`
    field, so a promoted Tier-1 key is found even when `lru:t1keys:{entry_id}` does not list it (the
    silent failure that would let a dependent survive in Tier 1 and still look purged). Then `t2:*`
    and `entry:*` are read by their key names.

      t1_keys  the sorted `t1:*` key names whose `entry_id` field names this entry
      t2       true when `t2:{entry_id}` exists
      entry    true when `entry:{entry_id}` exists

    IDs and key names only: a Tier-1 key is a hash of the question, never the question.
    """
    out: dict[str, dict] = {}

    def rec(entry_id: str) -> dict:
        return out.setdefault(entry_id, {"t1_keys": [], "t2": False, "entry": False})

    for key in client.scan_iter(match="t1:*", count=1000):
        key = _s(key)
        entry_id = _s(client.hget(key, "entry_id")) or NO_ENTRY_ID
        rec(entry_id)["t1_keys"].append(key)
    for key in client.scan_iter(match="t2:*", count=1000):
        rec(_s(key).removeprefix("t2:"))["t2"] = True
    for key in client.scan_iter(match="entry:*", count=1000):
        rec(_s(key).removeprefix("entry:"))["entry"] = True

    for r in out.values():
        r["t1_keys"].sort()
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------------------------------


def corpus_key(chunk_id: str) -> str:
    return f"corpus::{chunk_id}"


def cosine(a: bytes, b: bytes) -> float:
    import struct

    n = len(a) // 4
    x, y = struct.unpack(f"<{n}f", a), struct.unpack(f"<{len(b) // 4}f", b)
    dot = sum(p * q for p, q in zip(x, y, strict=True))
    nx, ny = sum(p * p for p in x) ** 0.5, sum(q * q for q in y) ** 0.5
    return dot / (nx * ny) if nx and ny else 0.0


def plan_fill(
    edits: list[dict],
    probe: dict[str, list[str]],
    rows: list[dict],
    per_edit: int = FILL_PER_EDIT,
    controls: int = CONTROLS,
) -> list[dict]:
    """Which validation questions to send, as `[{qa_id, for}]`, in a fixed order.

    For each edit, up to `per_edit` questions that the probe ties to its chunk. A question from a
    cluster that was already picked is skipped: paraphrases of one question would be Tier-2 hits on
    each other and write no entry. Then `controls` questions that no edited chunk touches, evenly
    spaced through the sorted list, so they are not all one product.
    """
    edited = {e["chunk_id"] for e in edits}
    ordered = sorted(rows, key=lambda r: r["qa_id"])
    used: set[str] = set()
    plan: list[dict] = []
    for e in edits:
        got = 0
        for r in ordered:
            if got >= per_edit:
                break
            if (
                e["chunk_id"] in probe.get(r["qa_id"], [])
                and r["cluster_id"] not in used
            ):
                plan.append({"qa_id": r["qa_id"], "for": e["edit_id"]})
                used.add(r["cluster_id"])
                got += 1
    free = [
        r
        for r in ordered
        if not (set(probe.get(r["qa_id"], [])) & edited) and r["cluster_id"] not in used
    ]
    step = max(1, len(free) // max(1, controls))
    picked = 0
    for r in free[::step]:
        if picked >= controls:
            break
        if r["cluster_id"] in used:
            continue
        used.add(r["cluster_id"])
        plan.append({"qa_id": r["qa_id"], "for": "control"})
        picked += 1
    return plan


def best_ranked_question(chunk_id: str, probe: dict[str, list[str]]) -> str | None:
    """The validation question for which the probe ranks `chunk_id` highest (ties: the smaller qa_id).

    DC 13 retrieves with it after the edit. A new vector moves a chunk a little, so the question is the
    one that ranks the chunk best, where a small move cannot push it out of the top k.
    """
    best = [(ids.index(chunk_id), qa) for qa, ids in probe.items() if chunk_id in ids]
    return min(best)[1] if best else None


def dependent_questions(responses: list[dict], edited: set[str]) -> list[str]:
    """The qa_ids whose fill answer was a MISS that cites an edited chunk: the questions to ask again."""
    return [
        r["qa_id"]
        for r in responses
        if r.get("cache") == "MISS" and set(r.get("sources") or []) & edited
    ]


# --------------------------------------------------------------------------------------------------
# Processes
# --------------------------------------------------------------------------------------------------


class Services:
    """rag.server and the gateway for one lifetime, on this script's own ports and epoch file."""

    def __init__(self, tmp: Path, binary: Path, env: dict, private: Path, tag: str):
        self.tag = tag
        self.private = private
        self.run_id = f"update-set-{tag}-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        self.results_dir = tmp / f"results-{tag}"
        self.records_path = self.results_dir / self.run_id / "raw" / "requests.jsonl"
        self.binary = binary
        self.env = env
        self.rag = self.gw = None
        self.rag_log = open(private / f"rag-server-{tag}.log", "w")  # noqa: SIM115
        self.gw_log = open(private / f"gateway-{tag}.log", "w")  # noqa: SIM115
        self.gw_code = None

    def start(self) -> None:
        self.rag = subprocess.Popen(
            [sys.executable, "-m", "rag.server"],
            cwd=ROOT / "rag",
            env=self.env,
            stdout=self.rag_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        erc.wait_listening(RAG_PORT, self.rag, "rag.server")
        gw_env = {
            **self.env,
            "HTTP_ADDR": GW_ADDR,
            "MUTATION": "on",
            "RUN_ID": self.run_id,
            "RESULTS_DIR": str(self.results_dir),
            "OLLAMA_NUM_PARALLEL": "1",
        }
        self.gw = subprocess.Popen(
            [str(self.binary)],
            cwd=ROOT,
            env=gw_env,
            stdout=self.gw_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        erc.wait_listening(GW_PORT, self.gw, "gateway")

    def stop(self) -> None:
        """The gateway first: it flushes the evaluation log when it gets SIGINT."""
        self.gw_code = erc.stop(self.gw, "gateway")
        erc.stop(self.rag, "rag.server")
        self.rag_log.close()
        self.gw_log.close()

    def records(self) -> dict[str, dict]:
        return erc.read_records(self.records_path)

    def log_names_epoch_file(self, epoch_file: Path) -> bool:
        want = f"dataset_epoch_file={epoch_file}"
        return (
            want in (self.private / f"gateway-{self.tag}.log").read_text()
            and want in (self.private / f"rag-server-{self.tag}.log").read_text()
        )


def ask(
    question: str, product_id: str | None, timeout_s: float = 600
) -> tuple[int, dict]:
    payload = {"question": question}
    if product_id:
        payload["product_id"] = product_id
    req = urllib.request.Request(
        f"http://{GW_ADDR}/ask",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")[:200]}


def edit_cli(edit_id: str, set_path: Path, env: dict) -> dict:
    """Run the real edit tool. Returns {ok, epoch, purged, failed, errors} for replies.json."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "rag.edit",
            "--update-set",
            str(set_path),
            "--edit-id",
            edit_id,
            "--gateway",
            f"http://{GW_ADDR}",
        ],
        cwd=ROOT / "rag",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    row = {
        "ok": proc.returncode == 0,
        "purged": [],
        "failed": [],
        "errors": [],
        "epoch": None,
    }
    for line in proc.stdout.splitlines():
        if line.startswith("reply="):
            reply = json.loads(line[len("reply=") :])
            row.update(
                purged=reply.get("purged", []),
                failed=reply.get("failed", []),
                errors=reply.get("errors", []),
            )
        elif line.startswith("epoch_file="):
            row["epoch"] = int(line.rsplit("epoch=", 1)[1])
    if proc.returncode != 0:
        row["errors"] = row["errors"] + [
            f"edit tool exit {proc.returncode}: {proc.stderr[-300:]}"
        ]
    return row


# --------------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------------


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=1, sort_keys=True) + "\n")


def wait_for_registrations(r: redis.Redis, n_miss: int, timeout_s: float = 30) -> bool:
    """Registration is queued to the dependency map's writer, so entry:{E} lands just after the reply."""
    deadline = time.monotonic() + timeout_s
    while True:
        n = sum(1 for _ in r.scan_iter(match="entry:*", count=1000))
        if n >= n_miss:
            return True
        if time.monotonic() > deadline:
            return False
        time.sleep(0.2)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Item 4.4: the live update-set run (fill, 20 edits, completeness, exactness, "
        "precision, one forced race). Loads both Ollama models; citable: no."
    )
    ap.add_argument(
        "--evidence-dir", required=True, help="where the evidence goes; must be empty"
    )
    ap.add_argument("--set", type=Path, default=update_set.SET_PATH, dest="set_path")
    ap.add_argument("--manifest", type=Path, default=update_set.MANIFEST_PATH)
    ap.add_argument("--probe", type=Path, default=DEFAULT_PROBE)
    ap.add_argument("--workload", type=Path, default=update_set.VALIDATION_PATH)
    ap.add_argument(
        "--advance-after",
        type=float,
        default=1.5,
        help="seconds after sending the race question before the edit is applied (1.5)",
    )
    args = ap.parse_args(argv)

    ev = Path(args.evidence_dir).resolve()
    if ev.exists() and any(ev.iterdir()):
        print(
            f"FAIL  {ev} already holds files; use a new folder (evidence is write-once)"
        )
        return 1
    private = ev / "private"
    private.mkdir(parents=True, exist_ok=True)

    t_start = time.monotonic()
    checks = erc.Checks()
    level0 = erc.pressure_level()
    (ev / "pressure.txt").write_text(f"start: {level0}\n")
    print(
        f"memory pressure level: {level0} (1 = green; recorded only, never a gate; citable: no)"
    )

    # ---- 1. preconditions ----
    r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
    rb = redis.Redis(
        host="localhost", port=6379, db=0
    )  # bytes: the vector field is binary
    try:
        r.ping()
        edits = json.loads(args.set_path.read_text())
        probe = json.loads(args.probe.read_text())
        workload = json.loads(args.workload.read_text())
        manifest = json.loads(args.manifest.read_text())
    except (redis.RedisError, OSError, ValueError) as e:
        print(f"FAIL  preconditions: {type(e).__name__}: {e}")
        return 1
    if update_set.sha256_file(args.set_path) != manifest.get("sha256"):
        print("FAIL  the update set's sha256 does not match the manifest")
        return 1
    for port in (RAG_PORT, GW_PORT):
        if erc.port_taken(port):
            print(f"FAIL  port {port} already has a listener; stop it first")
            return 1
    try:
        urllib.request.urlopen(erc.OLLAMA_VERSION_URL, timeout=3).read()
    except (urllib.error.URLError, OSError) as e:
        print(f"FAIL  Ollama does not answer at {erc.OLLAMA_VERSION_URL}: {e}")
        return 1

    saved: dict[str, tuple[str, bytes]] = {}
    for e in edits:
        text, vector = rb.hmget(corpus_key(e["chunk_id"]), ["text", "vector"])
        if text is None or vector is None or text.decode() != e["before"]:
            print(
                f"FAIL  chunk {e['chunk_id']} does not hold the edit's before in Redis"
            )
            return 1
        saved[e["chunk_id"]] = (text.decode(), vector)
    by_chunk = {e["chunk_id"]: e for e in edits}
    edited = set(by_chunk)
    race_edit = next(
        (
            e
            for e in edits
            if e["change_type"] == "substantive"
            and e["doc_id"].startswith("policy-return")
            and "30 days" in e["before"]
            and "14 days" in e["after"]
        ),
        None,
    )
    if race_edit is None:
        print("FAIL  the update set has no 30 -> 14 day return edit")
        return 1
    rows_by_qa = {w["qa_id"]: w for w in workload}
    race_q = next(
        (w for w in sorted(workload, key=lambda w: w["qa_id"])
         if race_edit["chunk_id"] in probe.get(w["qa_id"], [])),
        None,
    )  # fmt: skip
    if race_q is None:
        print("FAIL  the probe ties no validation question to the 30 -> 14 day chunk")
        return 1
    plan = plan_fill(edits, probe, workload)
    print(f"preconditions ok: {len(edits)} edits, {len(plan)} fill questions planned")

    # ---- temp area, environment ----
    tmp = Path(tempfile.mkdtemp(prefix="update-set-"))
    epoch_file = tmp / "dataset-epoch"
    epoch_file.write_text("1\n")
    env = {k: v for k, v in os.environ.items() if k not in erc.SCRUBBED_ENV}
    env.update(
        DATASET_EPOCH_FILE=str(epoch_file),
        DATASET_VERSION="v1",
        RAG_GRPC_ADDR=RAG_ADDR,
    )
    # This process calls rag.edit, rag.epoch and rag.retrieve itself (the race, the restore, DC 13).
    os.environ.update(
        DATASET_EPOCH_FILE=str(epoch_file), DATASET_VERSION="v1", RAG_GRPC_ADDR=RAG_ADDR
    )
    from rag.retrieve import fetch_by_ids, retrieve

    from rag import edit as rag_edit
    from rag import epoch as rag_epoch

    writer = rag_edit.redis_writer(rb)
    post = rag_edit.make_post(f"http://{GW_ADDR}")

    def apply_in_process(e: dict, vector: bytes | None = None) -> rag_edit.Applied:
        edit = rag_edit.Edit(
            e["edit_id"],
            e["doc_id"],
            e["chunk_id"],
            e["change_type"],
            e["before"],
            e["after"],
        )
        return rag_edit.apply(
            edit, write=writer, advance=rag_epoch.advance, post=post, vector=vector
        )

    def restore_chunk(chunk_id: str) -> dict:
        text, vector = saved[chunk_id]
        return rag_edit.restore(
            chunk_id,
            text,
            vector,
            by_chunk[chunk_id]["change_type"],
            write=writer,
            advance=rag_epoch.advance,
            post=post,
        )

    run_error = ""
    race_not_forced = False
    svc = None
    edits_applied: list[str] = []
    try:
        binary = tmp / "gateway-bin"
        subprocess.run(
            ["go", "build", "-o", str(binary), "./cmd/gateway"],
            cwd=ROOT / "gateway",
            check=True,
        )

        # ---- 2. the race (lifetime 1) ----
        reset0 = cache_reset.reset(r, listening=cache_reset.listening_ports())
        print(f"cache reset before the race: {reset0}")
        svc = Services(tmp, binary, env, private, "race")
        svc.start()
        print("lifetime 1: rag.server and the gateway are listening", flush=True)
        race_vector = rag_edit.embed_document(
            race_edit["after"]
        )  # before the question is sent
        out: dict = {}

        def send() -> None:
            st, bd = ask(race_q["question"], race_q.get("product_id"))
            out.update(status=st, body=bd)

        th = threading.Thread(target=send, daemon=True)
        th.start()
        time.sleep(args.advance_after)
        epoch_before_race = rag_epoch.read()
        applied = apply_in_process(race_edit, vector=race_vector)
        print(
            f"race edit applied: epoch {epoch_before_race} -> {applied.epoch}",
            flush=True,
        )
        th.join(timeout=600)
        if th.is_alive() or "body" not in out:
            raise RuntimeError("the race question did not return")
        time.sleep(1.0)
        race_keys = snapshot(r)
        restore_chunk(race_edit["chunk_id"])
        svc.stop()
        race_rec = svc.records().get(out["body"].get("request_id", ""), {})
        race_ok_names = svc.log_names_epoch_file(epoch_file)
        retrieved = race_rec.get("retrieved_chunk_ids") or []
        race = {
            "edit_id": race_edit["edit_id"],
            "chunk_id": race_edit["chunk_id"],
            "qa_id": race_q["qa_id"],
            "http_status": out["status"],
            "cache": race_rec.get("cache"),
            "retrieved_chunk_ids": retrieved,
            "chunk_in_retrieved": race_edit["chunk_id"] in retrieved,
            "writeback_discarded": race_rec.get("writeback_discarded"),
            "entry_id": race_rec.get("entry_id"),
            "dataset_epoch_at_retrieval": race_rec.get("dataset_epoch_at_retrieval"),
            "epoch_before_edit": epoch_before_race,
            "epoch_after_edit": applied.epoch,
            "reply_purged": applied.reply.get("purged"),
            "cache_keys_after": race_keys,
        }
        write_json(private / "race.json", race)
        (private / "race-requests.jsonl").write_text(svc.records_path.read_text())
        checks.check("race: both processes name the temp epoch file", race_ok_names)
        checks.check(
            "race: HTTP 200 (the client still gets its answer)", out["status"] == 200
        )
        checks.check(
            "race: the record lists the edited chunk in retrieved_chunk_ids",
            race["chunk_in_retrieved"],
            race_edit["chunk_id"],
        )
        if race["writeback_discarded"] is False:
            race_not_forced = True
            print(
                "FAIL  race not forced: the write-back was not discarded. Re-run once.",
                flush=True,
            )
            checks.failed += 1
        else:
            checks.check(
                "race: writeback_discarded is true", race["writeback_discarded"] is True
            )
            checks.check("race: the record names no entry", race["entry_id"] == "")
            checks.check(
                "race: no t1:, t2: or entry: key exists for it",
                race_keys == {},
                str(len(race_keys)),
            )
        cache_reset.reset(
            r, listening=cache_reset.listening_ports()
        )  # clears the race's leftovers
        if race_not_forced:
            raise RuntimeError("race not forced")

        # ---- 3-4. lifetime 2: reset, start, fill ----
        svc = Services(tmp, binary, env, private, "run")
        svc.start()
        print("lifetime 2: rag.server and the gateway are listening", flush=True)
        responses: list[dict] = []
        for i, item in enumerate(plan, 1):
            w = rows_by_qa[item["qa_id"]]
            status, body = ask(w["question"], w.get("product_id"))
            responses.append(
                {
                    "qa_id": item["qa_id"],
                    "for": item["for"],
                    "status": status,
                    "cache": body.get("cache"),
                    "request_id": body.get("request_id", ""),
                    "sources": body.get("sources") or [],
                }
            )
            print(
                f"fill {i}/{len(plan)} for {item['for']}: HTTP {status} {body.get('cache')}",
                flush=True,
            )
        level1 = erc.pressure_level()
        (ev / "pressure.txt").write_text(f"start: {level0}\nafter the fill: {level1}\n")
        checks.check(
            "fill: every request answered 200",
            all(x["status"] == 200 for x in responses),
        )
        n_miss = sum(1 for x in responses if x["cache"] == "MISS")
        checks.check(
            "fill: every MISS registered its entry before the edits",
            wait_for_registrations(r, n_miss),
            f"{n_miss} misses",
        )

        # ---- 5. snapshot before, the 20 edits, DC 13, snapshot after ----
        snap_before = snapshot(r)
        write_json(private / "snapshot-before.json", snap_before)
        replies = []
        for e in edits:
            row = {
                "edit_id": e["edit_id"],
                "chunk_id": e["chunk_id"],
                **edit_cli(e["edit_id"], args.set_path, env),
            }
            replies.append(row)
            edits_applied.append(e["chunk_id"])
            print(
                f"edit {e['edit_id']}: ok={row['ok']} purged={len(row['purged'])} failed={len(row['failed'])}",
                flush=True,
            )
        write_json(private / "replies.json", replies)
        write_json(
            private / "labels.json",
            [
                {
                    "edit_id": e["edit_id"],
                    "chunk_id": e["chunk_id"],
                    "change_type": e["change_type"],
                }
                for e in edits
            ],
        )

        dc13 = []
        for e in edits:
            cid = e["chunk_id"]
            fetched, _ = fetch_by_ids([cid])
            qa = best_ranked_question(cid, probe)
            w = rows_by_qa.get(qa, {})
            got, _ = (
                retrieve(w.get("question", ""), product_id=w.get("product_id"))
                if w
                else ([], 0)
            )
            retrieved_after = next((c.text for c in got if c.chunk_id == cid), None)
            stored = rb.hget(corpus_key(cid), "vector") or b""
            expected = rag_edit.embed_document(e["after"])
            before_cos = cosine(rag_edit.embed_document(e["before"]), saved[cid][1])
            row = {
                "edit_id": e["edit_id"],
                "chunk_id": cid,
                "retrieve_qa_id": qa,
                "fetch_by_ids_is_after": bool(fetched)
                and fetched[0].text == e["after"],
                "retrieve_is_after": retrieved_after == e["after"],
                "stored_vector_bytes_equal": stored == expected,
                "stored_vector_cosine": round(cosine(stored, expected), 6)
                if stored
                else None,
                "before_vs_ingested_cosine": round(before_cos, 6),
            }
            row["ok"] = (
                row["fetch_by_ids_is_after"]
                and row["retrieve_is_after"]
                and (row["stored_vector_cosine"] or 0) >= COSINE_MIN
                and before_cos >= COSINE_MIN
            )
            dc13.append(row)
        write_json(private / "dc13.json", dc13)
        snap_after = snapshot(r)
        write_json(private / "snapshot-after.json", snap_after)
        checks.check(
            "DC 13: every row passes",
            all(x["ok"] for x in dc13),
            f"{sum(x['ok'] for x in dc13)}/{len(dc13)}",
        )
        checks.check(
            "DC 13: stored vectors equal the edit tool's embedding byte for byte",
            all(x["stored_vector_bytes_equal"] for x in dc13),
            f"{sum(x['stored_vector_bytes_equal'] for x in dc13)}/{len(dc13)} (cosine is the gate)",
        )

        # ---- 6. ask every dependent's question again ----
        reasks = []
        for qa in dependent_questions(responses, edited):
            w = rows_by_qa[qa]
            status, body = ask(w["question"], w.get("product_id"))
            reasks.append(
                {
                    "qa_id": qa,
                    "request_id": body.get("request_id", ""),
                    "status": status,
                }
            )
            print(f"re-ask {qa[:24]}...: HTTP {status} {body.get('cache')}", flush=True)

        # ---- 7. restore through the same three steps, stop, reset, check ----
        for cid in reversed(edits_applied):
            try:
                restore_chunk(cid)
            except rag_edit.EditError as err:
                print(f"restore of {cid} failed: {err}", flush=True)
        svc.stop()
        records = svc.records()
        (private / "requests.jsonl").write_text(svc.records_path.read_text())

        # ---- 8. evidence ----
        oracle = []
        for x in responses:
            rec = records.get(x["request_id"], {})
            oracle.append(
                {
                    "qa_id": x["qa_id"],
                    "entry_id": rec.get("entry_id") or "",
                    "entry_sources": rec.get("entry_sources"),
                    "outcome": rec.get("cache"),
                    "writeback_discarded": rec.get("writeback_discarded"),
                }
            )
        checks.check(
            "every fill request has a record in the evaluation log",
            all(x["request_id"] in records for x in responses),
        )
        write_json(private / "oracle.json", sorted(oracle, key=lambda o: o["qa_id"]))
        write_json(
            private / "reask.json",
            [
                {
                    "qa_id": x["qa_id"],
                    "outcome": records.get(x["request_id"], {}).get("cache"),
                    "entry_id": records.get(x["request_id"], {}).get("entry_id") or "",
                }
                for x in reasks
            ],
        )
        checks.check(
            "both processes name the temp epoch file",
            svc.log_names_epoch_file(epoch_file),
        )
        checks.check(
            "gateway exited cleanly after SIGINT",
            svc.gw_code == 0,
            f"exit code {svc.gw_code}",
        )
    except Exception as e:  # noqa: BLE001 - reported below, then cleaned up
        run_error = f"{type(e).__name__}: {e}"
        print(f"FAIL  the run stopped early: {run_error}", flush=True)
    finally:
        if svc is not None:
            svc.stop()
        # Whatever happened, put every edited chunk back to the bytes it held at the start.
        for cid, (text, vector) in saved.items():
            now = rb.hget(corpus_key(cid), "text")
            if now is None or now.decode() != text:
                rb.hset(corpus_key(cid), mapping={"text": text, "vector": vector})
                print(f"restored {cid} directly", flush=True)
        cache_reset.reset(r, listening=cache_reset.listening_ports())

    # ---- after the processes are gone: the corpus and the cache are put back ----
    back = [
        cid
        for cid, (text, vector) in saved.items()
        if (rb.hmget(corpus_key(cid), ["text", "vector"]) == [text.encode(), vector])
    ]
    checks.check(
        "every edited chunk holds its saved text and vector again",
        len(back) == len(saved),
        f"{len(back)}/{len(saved)}",
    )
    left = snapshot(r)
    checks.check(
        "the cache keys the run wrote are gone", left == {}, f"{len(left)} entries left"
    )

    scorer_code = 1
    if not run_error:
        scorer_code = score_update_set.main([str(ev)])
        checks.check(
            "the scorer passes (completeness 1, exactness 0, replies 200)",
            scorer_code == 0,
        )

    seconds = time.monotonic() - t_start
    (private / "run-time.txt").write_text(f"{seconds:.0f} seconds\n")
    (private / "summary.txt").write_text("\n".join(checks.lines) + "\n")
    print(
        f"run time {seconds:.0f} s; memory pressure at the end: {erc.pressure_level()}; evidence {ev}"
    )
    shutil.rmtree(tmp, ignore_errors=True)

    if race_not_forced:
        return 2
    if run_error or checks.failed:
        print(f"FAILED: {checks.failed} check(s) {run_error}")
        return 1
    print(
        "PASS: 20 edits purged exactly their dependents; the race write-back was discarded"
    )
    return 0


if __name__ == "__main__":
    random.seed(0)
    sys.exit(main())
