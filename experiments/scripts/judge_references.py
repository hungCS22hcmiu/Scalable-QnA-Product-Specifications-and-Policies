"""Item 5.1: gold evidence, the reference set and the sufficiency sheet.

    make judge-gold-check SPLIT=validation       offline: are the workload's gold labels sound?
    make judge-references SPLIT=validation       loads the reference writer (citable: no)

A reference is `LLM_w(gold(q), q)`: the writer's own pinned prompt (`experiments/judge/reference-prompt-v1.txt`,
the old served prompt, ADR-029), given every chunk of the query's own `doc_ids` (in
document order) instead of what the system retrieved, and answered by the pinned reference writer
(`experiments/judge/reference-writer-v1.json`, ADR-023: `qwen3.5:4b-q4_K_M` at temperature 0). A reference
built from a run's own retrieval would share a wrong retrieval's error, and the judge would call the
reuse correct (docs/work/2026-10-30-judge-harness/design.md, section 1).

Subcommands:
  gold-check  DC 6. Counts by stratum and `answerable`; exits 1 on any problem.
  build       DC 7. One reference per distinct (question, product_id), content-addressed. Refuses unless
              `make corpus-index-check` passes, refuses at pressure 4, and never overwrites.
  sheet       DC 8. 30 gold-evidence + reference pairs for the author to mark `sufficient: yes|no`
              and `reference right: yes|no`.
  score       DC 8. Counts both marks; exits 1 when a cell is unmarked or more than 3 of either are `no`.

The reference set holds question text and PQA-grounded answers, so it is gitignored. Messages here name
a query by `qa_id` and never quote text.

Exit codes: 0 done / valid; 1 a check failed or a rule refused.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import random
import re
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

import corpus_gate

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
CORPUS_DIR = DATA_DIR / "v1"
FREEZE_PATH = DATA_DIR / "v1-freeze.json"
RETRIEVE_PY = ROOT / "rag" / "src" / "rag" / "retrieve.py"
REFERENCES_DIR = ROOT / "experiments" / "references"
WRITER_PATH = ROOT / "experiments" / "judge" / "reference-writer-v1.json"
# The reference writer keeps the OLD generator prompt (ADR-029 amends ADR-023): the references and the
# judge-error figures were measured under it, so it lives in this pinned file, not in rag/generate.py.
WRITER_PROMPT_PATH = ROOT / "experiments" / "judge" / "reference-prompt-v1.txt"
WRITER_TIMEOUT = (
    600.0  # seconds for one reference; the 4B writer decodes at about 17 tok/s
)

# Ollama drops prompt text past num_ctx with no error (design.md failure mode 10). The longest gold set
# measured on 2026-10-31 was 7,766 characters against num_ctx 8192 (about 2,000 tokens).
GOLD_CHAR_LIMIT = 24_000
SPLITS = ("validation", "test")
BUILD_SPLITS = (
    "validation",
)  # test-split references are out of scope (design.md section 1)
ONE_DOCUMENT_STRATA = ("A", "B-within", "B-cross", "C")
STRATA = (*ONE_DOCUMENT_STRATA, "D")
PRESSURE_STOP = 4  # macOS critical (CLAUDE.md, ADR-014)
PRESSURE_EVERY = 50
DETAIL_CAP = 20  # problem lines printed before "... and N more"

# The decline pattern of the 2026-10-31 prompt probe (docs/work/2026-10-31-rag-correctness/
# prompt_probe.py). A heuristic, reported beside the stop rule and never part of it: it also counts a
# "No" written as "the context does not mention ...".
DONT_KNOW = re.compile(
    r"\b(?:don[’']t|do not) know\b"
    r"|\bnot (?:contained|mentioned|specified|stated|provided|given|found|available|included|listed)"
    r" in the (?:provided )?(?:context|text)\b"
    r"|\b(?:context|text) (?:does not|doesn[’']t|did not) "
    r"(?:contain|mention|specify|state|provide|include|say|list|give)\b",
    re.IGNORECASE,
)


class ReferenceRefused(RuntimeError):
    """A rule stopped the reference set. The message says which; nothing was written for it."""


# =================================================================================================
# Small shared helpers (run_manifest.py and judge.py import these)
# =================================================================================================
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def http_json(url: str, body: dict | None = None, timeout: float = 10.0) -> dict:
    """GET, or POST when `body` is given. Returns the JSON reply. Raises OSError on a network error."""
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def kind_of(doc_id: str) -> str | None:
    if doc_id.startswith("product-"):
        return "product"
    if doc_id.startswith("policy-"):
        return "policy"
    return None


def parse_temperature(parameters: str) -> float | None:
    """The `temperature` line of `/api/show`'s `parameters` text, or None when the Modelfile has none."""
    m = re.search(r"^temperature\s+([0-9.]+)\s*$", parameters or "", re.MULTILINE)
    return float(m.group(1)) if m else None


# =================================================================================================
# Gold evidence (DC 6)
# =================================================================================================
def load_split(split: str) -> list[dict]:
    """The workload's records for one split: `data/workload-v1-{split}.json`."""
    return json.loads((DATA_DIR / f"workload-v1-{split}.json").read_text())


def corpus_chunks(data_dir: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    """(doc_id -> chunk IDs in ordinal order, chunk_id -> text), rebuilt with the ingest split.

    No embedding and no Redis, as `update_set.py verify` does it.
    """
    from rag.chunkid import parse_chunk_id
    from rag.ingest import load_records, records_to_nodes

    nodes = records_to_nodes(load_records(Path(data_dir)), "v1")
    ordered: dict[str, list[tuple[int, str]]] = {}
    texts: dict[str, str] = {}
    for node in nodes:
        doc_id, ordinal = parse_chunk_id(node.id_)
        ordered.setdefault(doc_id, []).append((ordinal, node.id_))
        texts[node.id_] = node.text
    return {d: [cid for _, cid in sorted(rows)] for d, rows in ordered.items()}, texts


def doc_chunk_ids(data_dir: Path) -> dict[str, list[str]]:
    """Each document's chunk IDs in ordinal order."""
    return corpus_chunks(data_dir)[0]


def gold_chunk_ids(doc_ids: list[str], chunks: dict[str, list[str]]) -> list[str]:
    """The documents in `doc_ids` order, each one's chunks in ordinal order.

    Raises on an unknown document or an empty result: a gold set that is empty would let `Answer`
    retrieve instead of reading gold evidence.
    """
    out: list[str] = []
    for doc_id in doc_ids:
        if doc_id not in chunks:
            raise ValueError(f"unknown doc_id {doc_id!r}")
        out.extend(chunks[doc_id])
    if not out:
        raise ValueError("the gold set is empty")
    return out


def gold_context_length(chunk_ids: list[str], texts: dict[str, str]) -> int:
    """The characters of the context `generate` builds from these chunks (joined by a blank line)."""
    return len("\n\n".join(texts[c] for c in chunk_ids))


def gold_problems(
    queries: list[dict], chunks: dict[str, list[str]], texts: dict[str, str]
) -> list[str]:
    """Every problem with the gold labels, as messages that name a query by `qa_id`, never by text."""
    problems: list[str] = []
    for q in queries:
        name = q.get("qa_id", "?")
        doc_ids = q.get("doc_ids")
        if not isinstance(doc_ids, list) or not doc_ids:
            problems.append(f"{name}: doc_ids is missing or empty")
            continue
        unknown = [d for d in doc_ids if d not in chunks]
        for d in unknown:
            problems.append(f"{name}: unknown doc_id {d}")

        kinds = sorted(str(kind_of(d)) for d in doc_ids)
        stratum = q.get("stratum")
        if stratum in ONE_DOCUMENT_STRATA:
            if len(doc_ids) != 1:
                problems.append(
                    f"{name}: stratum {stratum} wants one document, has {len(doc_ids)}"
                )
        elif stratum == "D":
            if kinds != ["policy", "product"]:
                problems.append(
                    f"{name}: stratum D wants one product and one policy document, has {kinds}"
                )
        else:
            problems.append(f"{name}: unknown stratum {stratum!r}")

        if q.get("reference_answer") != "":
            problems.append(f"{name}: reference_answer is not the empty string")

        if not unknown:
            size = gold_context_length(gold_chunk_ids(doc_ids, chunks), texts)
            if size > GOLD_CHAR_LIMIT:
                problems.append(
                    f"{name}: gold set is {size} characters, over {GOLD_CHAR_LIMIT}"
                )
    return problems


def pair_key(q: dict) -> tuple[str, str]:
    """A reference's identity: the exact question and `product_id` (`""` when the query has none)."""
    return q["question"], q.get("product_id") or ""


def gold_counts(queries: list[dict]) -> dict:
    """Counts for the gold audit: by stratum, by `answerable`, two-document queries, distinct pairs."""
    by_stratum: dict[str, int] = {}
    by_answerable = {"true": 0, "false": 0}
    for q in queries:
        by_stratum[q["stratum"]] = by_stratum.get(q["stratum"], 0) + 1
        by_answerable["true" if q.get("answerable") else "false"] += 1
    return {
        "queries": len(queries),
        "by_stratum": dict(sorted(by_stratum.items())),
        "by_answerable": by_answerable,
        "two_documents": sum(1 for q in queries if len(q.get("doc_ids") or []) == 2),
        "distinct_pairs": len({pair_key(q) for q in queries}),
    }


def gold_check(split: str, corpus_dir: Path = CORPUS_DIR) -> int:
    queries = load_split(split)
    chunks, texts = corpus_chunks(corpus_dir)
    problems = gold_problems(queries, chunks, texts)
    counts = gold_counts(queries)

    print(
        f"split {split}: {counts['queries']} queries, {counts['distinct_pairs']} distinct pairs"
    )
    print(
        "  by stratum:   "
        + ", ".join(f"{k} {v}" for k, v in counts["by_stratum"].items())
    )
    print(
        f"  by answerable: true {counts['by_answerable']['true']}, "
        f"false {counts['by_answerable']['false']}"
    )
    print(f"  with two documents: {counts['two_documents']}")
    for line in problems[:DETAIL_CAP]:
        print(f"FAIL  {line}")
    if len(problems) > DETAIL_CAP:
        print(f"FAIL  ... and {len(problems) - DETAIL_CAP} more")
    if problems:
        print(f"judge-gold-check: {len(problems)} problem(s)")
        return 1
    print("judge-gold-check: ok")
    return 0


# =================================================================================================
# The references (DC 7)
# =================================================================================================
def answer_in_process(
    query: str, product_id: str, chunk_ids: list[str]
) -> tuple[str, list[str]]:
    """Call the `Answer` handler in this process, with `chunk_ids` as `retrieved_chunk_ids`.

    The same code the gateway reaches over gRPC, with no port or process to manage. `Answer` is a
    generator that yields one terminal chunk. Returns that chunk's text and `source_chunk_ids`.
    """
    from rag.pb.rag.v1 import rag_pb2

    from rag import server

    request = rag_pb2.AnswerRequest(
        query=query, product_id=product_id, retrieved_chunk_ids=chunk_ids
    )
    replies = list(server.RagServicer().Answer(request, None))
    if len(replies) != 1:
        raise ReferenceRefused(f"Answer sent {len(replies)} chunks, want exactly one")
    return replies[0].text, list(replies[0].source_chunk_ids)


def load_writer(path: Path = WRITER_PATH) -> dict:
    """`reference-writer-v1.json` as a dict: the reference writer's model, digest, options, `think` and
    the sha256 of the served prompt it is paired with (ADR-023)."""
    return json.loads(Path(path).read_text())


def load_writer_prompt(path: Path | None = None) -> str:
    """The reference writer's prompt template, exactly as the pinned file holds it (no newline is
    added or removed). It has the `{context}` and `{query}` fields and no system text."""
    return Path(path or WRITER_PROMPT_PATH).read_bytes().decode("utf-8")


def writer_block(
    http: Callable[..., dict] = http_json,
    path: Path = WRITER_PATH,
    prompt_path: Path | None = None,
) -> dict:
    """The reference writer, checked against the live Ollama (ADR-023, design.md failure mode 15).

    Refuses when the tag is not in `/api/tags`, when its live digest differs from the file's, or when
    the writer's own pinned prompt file (`reference-prompt-v1.txt`) no longer hashes to the file's
    `prompt_sha256`. The served prompt is not read here: since ADR-029 it can change without touching
    the writer. Returns the file's fields: it is what the reference set's `version.json` stores as
    `reference_writer`.
    """
    from rag import config

    writer = load_writer(path)
    base = config.OLLAMA_BASE_URL.rstrip("/")
    tags = http(f"{base}/api/tags")
    digest = next(
        (m["digest"] for m in tags["models"] if m["name"] == writer["model"]), None
    )
    if digest is None:
        raise ReferenceRefused(
            f"the reference writer {writer['model']} is not in /api/tags"
        )
    if digest != writer["digest"]:
        raise ReferenceRefused(
            f"the live digest of {writer['model']} is {digest[:12]}..., "
            f"{Path(path).name} has {writer['digest'][:12]}..."
        )
    prompt_file = Path(prompt_path or WRITER_PROMPT_PATH)
    prompt = sha256_bytes(load_writer_prompt(prompt_file).encode("utf-8"))
    if prompt != writer["prompt_sha256"]:
        raise ReferenceRefused(
            f"the writer's prompt file {prompt_file.name} hashes to {prompt[:12]}..., "
            f"{Path(path).name} has {writer['prompt_sha256'][:12]}..."
        )
    return {
        key: writer[key]
        for key in ("version", "model", "digest", "options", "think", "prompt_sha256")
    }


def answer_with_writer(
    query: str,
    product_id: str,
    chunk_ids: list[str],
    *,
    http: Callable[..., dict] = http_json,
    path: Path = WRITER_PATH,
    prompt_path: Path | None = None,
) -> tuple[str, list[str]]:
    """Write one reference with the pinned reference writer (ADR-023).

    The writer's own prompt (`reference-prompt-v1.txt`, the old served prompt, no system text) over the
    chunks `retrieve.fetch_by_ids` loads for `chunk_ids`, joined by a blank line as the served prompt
    joins them, sent to `/api/generate` with the writer's model and options. `think` is sent (as the
    file gives it) only when `/api/show` lists `thinking`. Returns the text and the IDs `fetch_by_ids`
    returned, so `make_reference` still sees a chunk that was dropped. `product_id` only keeps the
    signature of `answer_in_process`: the prompt does not use it. That the file still hashes to the
    writer file's `prompt_sha256` is checked by `writer_block`, which `build` runs before any reference.
    """
    from rag import config, retrieve

    writer = load_writer(path)
    template = load_writer_prompt(prompt_path)
    base = config.OLLAMA_BASE_URL.rstrip("/")
    chunks, _ = retrieve.fetch_by_ids(list(chunk_ids))
    context = "\n\n".join(c.text for c in chunks)
    body = {
        "model": writer["model"],
        "prompt": template.format(context=context, query=query),
        "stream": False,
        "options": dict(writer["options"]),
    }
    show = http(f"{base}/api/show", {"model": writer["model"]})
    if "thinking" in (show.get("capabilities") or []):
        body["think"] = writer["think"]
    reply = http(f"{base}/api/generate", body, timeout=WRITER_TIMEOUT)
    return reply["response"], [c.chunk_id for c in chunks]


def make_reference(
    query: dict,
    chunk_ids: list[str],
    answer: Callable[[str, str, list[str]], tuple[str, list[str]]] = answer_in_process,
) -> dict:
    """One reference. Refuses an empty `chunk_ids` and a reply grounded on other chunks."""
    name = query.get("qa_id", "?")
    if not chunk_ids:
        raise ReferenceRefused(
            f"{name}: no gold chunk IDs; Answer would retrieve instead of reading gold evidence"
        )
    text, sources = answer(
        query["question"], query.get("product_id") or "", list(chunk_ids)
    )
    if list(sources) != list(chunk_ids):
        raise ReferenceRefused(
            f"{name}: Answer grounded on {len(sources)} chunk(s) that are not the {len(chunk_ids)} "
            "gold chunks sent, in order (fetch_by_ids drops a missing chunk with no error)"
        )
    return {
        "qa_id": query["qa_id"],
        "question": query["question"],
        "product_id": query.get("product_id") or "",
        "stratum": query["stratum"],
        "answerable": query["answerable"],
        "gold_doc_ids": list(query["doc_ids"]),
        "chunk_ids": list(chunk_ids),
        "reference_sha256": sha256_bytes(text.encode("utf-8")),
        "text": text,
    }


def generator_block(http: Callable[..., dict] = http_json) -> dict:
    """The generator as `/api/tags` and `/api/show` list it, plus the frozen settings of rag.config and
    the sha256 of the generator's prompt template (`generate._PROMPT_TEMPLATE`). The manifest's
    `generator` block and the reference set's `version.json` both come from here, so a run and its
    references made under two generator prompts show as two different blocks."""
    from rag import config, generate

    base = config.OLLAMA_BASE_URL.rstrip("/")
    tags = http(f"{base}/api/tags")
    digest = next(
        (m["digest"] for m in tags["models"] if m["name"] == config.LLM_MODEL), None
    )
    if digest is None:
        raise ReferenceRefused(f"{config.LLM_MODEL} is not in /api/tags")
    show = http(f"{base}/api/show", {"model": config.LLM_MODEL})
    return {
        "model": config.LLM_MODEL,
        "digest": digest,
        "num_ctx": config.LLM_NUM_CTX,
        "think": config.LLM_THINK,
        "temperature": parse_temperature(show.get("parameters", "")),
        "prompt_sha256": sha256_bytes(generate._PROMPT_TEMPLATE.encode("utf-8")),
    }


def corpus_block(freeze_path: Path = FREEZE_PATH) -> dict:
    freeze = json.loads(Path(freeze_path).read_text())
    return {
        "dataset_version": freeze["dataset_version"],
        "snapshot_digest": freeze["snapshot_digest"],
    }


def retrieval_block(retrieve_py: Path = RETRIEVE_PY) -> dict:
    from rag import config

    return {
        "retrieval_version": config.RETRIEVAL_VERSION,
        "retrieve_py_sha256": sha256_file(retrieve_py),
        "top_k": config.TOP_K,
    }


def version_block(http: Callable[..., dict] = http_json) -> dict:
    """The study state a reference set was made in. A run's manifest must agree with it on the generator
    (its prompt hash included), the corpus and the retrieval (the judge refuses otherwise). The
    `reference_writer` is not in a manifest: the judge compares it with `reference-writer-v1.json`."""
    return {
        "generator": generator_block(http),
        "corpus": corpus_block(),
        "retrieval": retrieval_block(),
        "reference_writer": writer_block(http),
    }


def build(
    split: str,
    out: Path,
    *,
    queries: list[dict] | None = None,
    corpus: tuple[dict[str, list[str]], dict[str, str]] | None = None,
    answer: Callable[[str, str, list[str]], tuple[str, list[str]]] = answer_with_writer,
    index_check: Callable[[], int] | None = None,
    versions: Callable[[], dict] = version_block,
    pressure: Callable[[], int | None] = corpus_gate.memory_pressure_level,
    log: Callable[[str], None] = print,
) -> dict:
    """Write the reference set for one split to `out`. Returns its counts and the index's sha256.

    Writes into `out.partial` and renames it on success, so `out` exists only for a finished set.
    Refuses when `out` (or a `.partial` of an earlier build) exists, at pressure 4, when the index in
    Redis is not the v1 corpus, and when the gold labels have a problem.
    """
    out = Path(out)
    partial = out.with_name(out.name + ".partial")
    if out.exists() or partial.exists():
        raise ReferenceRefused(
            f"{out if out.exists() else partial} exists; a reference set is never overwritten"
        )

    level = pressure()
    log(f"  memory pressure level: {level} (1 green, 2 warn, 4 critical)")
    if level == PRESSURE_STOP:
        raise ReferenceRefused(
            "memory pressure is critical (4); close apps and check again"
        )

    if index_check is None:
        import freeze_corpus

        def index_check() -> int:
            return freeze_corpus.cmd_check_index(freeze_corpus.default_paths())

    if index_check() != 0:
        raise ReferenceRefused(
            "the index in Redis is not the v1 corpus (make corpus-index-check)"
        )

    queries = load_split(split) if queries is None else queries
    chunks, texts = corpus_chunks(CORPUS_DIR) if corpus is None else corpus
    problems = gold_problems(queries, chunks, texts)
    if problems:
        raise ReferenceRefused(f"{len(problems)} gold problem(s), first: {problems[0]}")

    # One reference per distinct (question, product_id). The pair is unique in both splits (measured
    # 2026-10-31); a repeat with other gold documents would be two references for one key, so it stops.
    todo: dict[tuple[str, str], dict] = {}
    for q in queries:
        key = pair_key(q)
        if key in todo:
            if todo[key]["doc_ids"] != q["doc_ids"]:
                raise ReferenceRefused(
                    f"{q['qa_id']}: same question and product, other gold documents"
                )
            continue
        todo[key] = q

    version = versions()
    partial.mkdir(parents=True)
    (partial / "answers").mkdir()
    rows: list[dict] = []
    declines = 0
    answerable_true = 0
    for i, q in enumerate(todo.values(), 1):
        ref = make_reference(q, gold_chunk_ids(q["doc_ids"], chunks), answer)
        text = ref.pop("text")
        (partial / "answers" / f"{ref['reference_sha256']}.txt").write_bytes(
            text.encode("utf-8")
        )
        rows.append(ref)
        if q["answerable"]:
            answerable_true += 1
            declines += 1 if DONT_KNOW.search(text) else 0
        if i % PRESSURE_EVERY == 0 or i == len(todo):
            level = pressure()
            log(f"  {i}/{len(todo)} references; pressure level {level}")
            if level == PRESSURE_STOP:
                raise ReferenceRefused(
                    f"memory pressure is critical (4) after {i} references; {partial} is incomplete"
                )

    index_bytes = "".join(
        json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows
    ).encode("utf-8")
    (partial / "index.jsonl").write_bytes(index_bytes)
    version = {
        **version,
        "split": split,
        "references": len(rows),
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"
        ),
    }
    (partial / "version.json").write_text(json.dumps(version, indent=2) + "\n")
    partial.rename(out)

    result = {
        "references": len(rows),
        "answerable_true": answerable_true,
        "declines": declines,
        "index_sha256": sha256_bytes(index_bytes),
    }
    log(
        f"  {declines} of {answerable_true} answerable:true references decline to answer"
    )
    log(f"  index.jsonl sha256 {result['index_sha256']}  (the reference set's hash)")
    return result


# =================================================================================================
# The sufficiency sheet (DC 8)
# =================================================================================================
SUFFICIENT = re.compile(r"^sufficient:[ \t]*(\S*)[ \t]*$", re.MULTILINE)
REFERENCE_RIGHT = re.compile(r"^reference right:[ \t]*(\S*)[ \t]*$", re.MULTILINE)
SECTION = re.compile(r"^## \d+\. ", re.MULTILINE)


def read_index(refs_dir: Path) -> list[dict]:
    text = (Path(refs_dir) / "index.jsonl").read_text()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def sheet(
    split: str,
    out: Path,
    n: int = 30,
    min_b_within: int = 10,
    seed: int = 7,
    *,
    refs_dir: Path | None = None,
    corpus: tuple[dict[str, list[str]], dict[str, str]] | None = None,
) -> int:
    """Write `n` gold-evidence + reference pairs as Markdown, `min_b_within` of them B-within.

    Only `answerable: true` pairs are drawn: an unanswerable question has no sufficient evidence to
    judge. Each pair is a section ending in an empty `sufficient:` line and an empty `reference right:`
    line for the author. Writes the file once and never over a file that exists. Gitignored: it holds
    question text and PQA-grounded text.
    """
    out = Path(out)
    if out.exists():
        raise ReferenceRefused(
            f"{out} exists; the author's marks are never overwritten"
        )
    refs_dir = REFERENCES_DIR / split if refs_dir is None else Path(refs_dir)
    texts = (corpus_chunks(CORPUS_DIR) if corpus is None else corpus)[1]

    rows = sorted(
        (r for r in read_index(refs_dir) if r["answerable"]), key=lambda r: r["qa_id"]
    )
    rng = random.Random(seed)
    b_within = [r for r in rows if r["stratum"] == "B-within"]
    if len(b_within) < min_b_within or len(rows) < n:
        raise ReferenceRefused(
            f"{len(b_within)} B-within and {len(rows)} answerable references; "
            f"want {min_b_within} and {n}"
        )
    picked = rng.sample(b_within, min_b_within)
    taken = {r["qa_id"] for r in picked}
    picked += rng.sample([r for r in rows if r["qa_id"] not in taken], n - min_b_within)
    rng.shuffle(picked)

    lines = [
        f"# Gold sufficiency sheet, {split}, {n} pairs (seed {seed})",
        "",
        "For each pair, read the gold evidence and the reference answer. Write `yes` after",
        "`sufficient:` if the gold evidence is enough to answer the question (so the reference can be",
        "right), or `no` if it is not. Leave nothing else on that line.",
        "Also write `yes` after `reference right:` if the reference answer is correct by the gold",
        "evidence, or `no` if it is wrong. A reference that declines is right only when the evidence",
        "does not answer the question.",
        "",
    ]
    for i, r in enumerate(picked, 1):
        ref_text = (refs_dir / "answers" / f"{r['reference_sha256']}.txt").read_text()
        lines += [
            f"## {i}. {r['qa_id']}",
            "",
            f"stratum: {r['stratum']}",
            f"question: {r['question']}",
            f"gold documents: {', '.join(r['gold_doc_ids'])}",
            "",
            "### gold evidence",
            "",
        ]
        for chunk_id in r["chunk_ids"]:
            lines += [f"[{chunk_id}]", "", texts[chunk_id], ""]
        lines += [
            "### reference answer",
            "",
            ref_text,
            "",
            "### mark",
            "",
            "sufficient:",
            "reference right:",
            "",
        ]
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out}: {len(picked)} pairs, {min_b_within} or more B-within")
    return 0


def _mark(pattern: re.Pattern[str], section: str) -> str:
    """The word after the cell's label: the last match in the section, case-folded ("" if none)."""
    found = pattern.findall(section)
    return found[-1].lower() if found else ""


def _tally(word: str, counts: dict[str, int]) -> None:
    if word in ("yes", "no"):
        counts[word] += 1
    elif word == "":
        counts["unmarked"] += 1
    else:
        counts["other"] += 1


def score(sheet_path: Path) -> dict:
    """Count the author's marks. A section is one pair; its two marks are the word after
    `sufficient:` and the word after `reference right:`."""
    text = Path(sheet_path).read_text()
    starts = [m.start() for m in SECTION.finditer(text)]
    sections = [
        text[a:b] for a, b in zip(starts, [*starts[1:], len(text)], strict=True)
    ]
    marks = {"yes": 0, "no": 0, "unmarked": 0, "other": 0}
    ref_marks = {"yes": 0, "no": 0, "unmarked": 0, "other": 0}
    b_within = 0
    for section in sections:
        if re.search(r"^stratum: B-within$", section, re.MULTILINE):
            b_within += 1
        _tally(_mark(SUFFICIENT, section), marks)
        _tally(_mark(REFERENCE_RIGHT, section), ref_marks)
    return {
        "pairs": len(sections),
        "b_within": b_within,
        **marks,
        **{f"ref_{k}": v for k, v in ref_marks.items()},
    }


# =================================================================================================
# Command line
# =================================================================================================
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("gold-check", help="DC 6: audit the gold labels, offline")
    p_check.add_argument("--split", choices=SPLITS, required=True)
    p_check.add_argument("--corpus-dir", type=Path, default=CORPUS_DIR)

    p_build = sub.add_parser(
        "build", help="DC 7: write the reference set (loads the generator)"
    )
    p_build.add_argument("--split", choices=BUILD_SPLITS, required=True)
    p_build.add_argument(
        "--out", type=Path, help="default: experiments/references/<split>"
    )

    p_sheet = sub.add_parser(
        "sheet", help="DC 8: write the sufficiency sheet for the author"
    )
    p_sheet.add_argument("--split", choices=BUILD_SPLITS, required=True)
    p_sheet.add_argument("--out", type=Path, required=True)
    p_sheet.add_argument("--n", type=int, default=30)
    p_sheet.add_argument("--min-b-within", type=int, default=10)
    p_sheet.add_argument("--seed", type=int, default=7)

    p_score = sub.add_parser("score", help="DC 8: count the author's marks")
    p_score.add_argument("sheet", type=Path)

    args = ap.parse_args(argv)
    try:
        if args.command == "gold-check":
            return gold_check(args.split, args.corpus_dir)
        if args.command == "build":
            build(args.split, args.out or REFERENCES_DIR / args.split)
            return 0
        if args.command == "sheet":
            return sheet(args.split, args.out, args.n, args.min_b_within, args.seed)
        result = score(args.sheet)
    except ReferenceRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1

    print(
        f"{result['pairs']} pairs ({result['b_within']} B-within): "
        f"{result['yes']} yes, {result['no']} no, {result['unmarked']} unmarked, "
        f"{result['other']} other"
    )
    print(
        f"reference right: {result['ref_yes']} yes, {result['ref_no']} no, "
        f"{result['ref_unmarked']} unmarked, {result['ref_other']} other"
    )
    if (
        result["unmarked"]
        or result["other"]
        or result["ref_unmarked"]
        or result["ref_other"]
    ):
        print(
            "FAIL  every pair needs `sufficient: yes|no` and `reference right: yes|no`"
        )
        return 1
    if result["no"] > 3 or result["ref_no"] > 3:
        print(
            "STOP  more than 3 `no` in `sufficient:` or in `reference right:`: stop and report "
            "before any verdict (design.md DC 8)"
        )
        return 1
    print("ok  at most 3 `no` in each cell")
    return 0


if __name__ == "__main__":
    sys.exit(main())
