"""Item 6.0a, done condition 4: does the new generator prompt keep its two promises? (`citable: no`)

    make prompt-probe

A seeded sample of 120 validation queries that carry a `product_id` (100 with `answerable: true`, 20 with
`false`). Each is retrieved as the service does (`rag.retrieve.retrieve`), then answered twice by the
served generator: once with the old prompt (`experiments/judge/reference-prompt-v1.txt`, no system text)
and once with the served prompt (`generate._SYSTEM_PROMPT` and `_PROMPT_TEMPLATE`, the very request body
the service sends). Sampling is Ollama's default, as in the service, so a second run can differ.

Two measurements, each as a share:

  meta   the answers that hold `context`, `provided`, `based on` or `according to`, over all 120, on the
         model's raw output (before `finalize`, which would hide a meta phrase behind the fallback).
         Pass: the new share is at most half the old share.
  refuse the answers that decline, over the 100 answerable questions: the old prompt's "don't know"
         (the regex `judge_references.DONT_KNOW`) against the new prompt's `NO_ANSWER` (`finalize`).
         Pass: the new share is at most the old share plus 3 points.

The answers hold Amazon-PQA wording, so they go to `--out` under the trail's `evidence/private/`; the
summary (`--summary`) holds counts only. The probe loads the embedding model and the generator: check
`sysctl kern.memorystatus_vm_pressure_level` first. It stops at level 4.

Exit codes: 0 the probe ran and both conditions hold; 1 a condition failed or a rule refused.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from collections.abc import Callable
from pathlib import Path

import corpus_gate
import judge_references as refs

ROOT = Path(__file__).resolve().parents[2]
OLD_PROMPT_PATH = ROOT / "experiments" / "judge" / "reference-prompt-v1.txt"
SEED = 20261113
N_ANSWERABLE = 100
N_UNANSWERABLE = 20
PRESSURE_STOP = 4  # macOS critical (CLAUDE.md, ADR-014)
PRESSURE_EVERY = 20
REFUSE_MARGIN = (
    0.03  # the new refusal share may exceed the old by this much (done condition 4)
)
META = re.compile(r"\b(?:context|provided|based on|according to)\b", re.IGNORECASE)


class ProbeStopped(RuntimeError):
    """A rule stopped the probe. The message says which."""


def draw(queries: list[dict], seed: int = SEED) -> list[dict]:
    """100 `answerable: true` and 20 `false` queries that have a `product_id`, drawn from the file in
    `qa_id` order so the draw does not depend on the file's order. The same seed gives the same sample."""
    pool = sorted((q for q in queries if q.get("product_id")), key=lambda q: q["qa_id"])
    yes = [q for q in pool if q.get("answerable") is True]
    no = [q for q in pool if q.get("answerable") is False]
    if len(yes) < N_ANSWERABLE or len(no) < N_UNANSWERABLE:
        raise ProbeStopped(
            f"the pool has {len(yes)} answerable and {len(no)} unanswerable queries"
        )
    rng = random.Random(seed)
    return rng.sample(yes, N_ANSWERABLE) + rng.sample(no, N_UNANSWERABLE)


def old_body(query: str, chunks: list, template: str) -> dict:
    """The request body of the old prompt: today's body without the system text, and the old template."""
    from rag import generate

    body = dict(generate._request_body(query, chunks))
    body.pop("system", None)
    body["prompt"] = template.format(
        context="\n\n".join(c.text for c in chunks), query=query
    )
    return body


def send(body: dict) -> str:
    from rag import generate

    return asyncio.run(generate._post_until_stop(body, None))


def shares(rows: list[dict]) -> dict:
    """The counts and shares of done condition 4 from the probe's rows. `rows` carry `answerable`,
    `old`, `new_raw` and `no_answer`."""
    n = len(rows)
    answerable = [r for r in rows if r["answerable"]]
    meta_old = sum(1 for r in rows if META.search(r["old"]))
    meta_new = sum(1 for r in rows if META.search(r["new_raw"]))
    dont_know_old = sum(1 for r in answerable if refs.DONT_KNOW.search(r["old"]))
    no_answer_new = sum(1 for r in answerable if r["no_answer"])
    out = {
        "n": n,
        "n_answerable": len(answerable),
        "meta_old": meta_old,
        "meta_new": meta_new,
        "meta_share_old": meta_old / n if n else 0.0,
        "meta_share_new": meta_new / n if n else 0.0,
        "dont_know_old": dont_know_old,
        "no_answer_new": no_answer_new,
        "refuse_share_old": dont_know_old / len(answerable) if answerable else 0.0,
        "refuse_share_new": no_answer_new / len(answerable) if answerable else 0.0,
        "no_answer_new_all": sum(1 for r in rows if r["no_answer"]),
    }
    out["meta_ok"] = meta_new * 2 <= meta_old
    out["refuse_ok"] = (
        out["refuse_share_new"] <= out["refuse_share_old"] + REFUSE_MARGIN + 1e-12
    )
    return out


def probe(
    queries: list[dict],
    *,
    template: str | None = None,
    retrieve: Callable | None = None,
    ask: Callable[[dict], str] = send,
    pressure: Callable[[], int | None] = corpus_gate.memory_pressure_level,
    log: Callable[[str], None] = print,
    out_rows: Callable[[dict], None] = lambda row: None,
) -> dict:
    """Run the probe over `queries` (already drawn). `retrieve(query, product_id)` returns the chunks;
    `ask(body)` returns the model's text. Raises `ProbeStopped` at pressure 4."""
    from rag import generate

    if retrieve is None:
        from rag import retrieve as rr

        def retrieve(query, product_id):
            return rr.retrieve(query, product_id=product_id)[0]

    template = (
        OLD_PROMPT_PATH.read_bytes().decode("utf-8") if template is None else template
    )
    level = pressure()
    log(
        f"  memory pressure level: {level} (1 green, 2 warn, 4 critical); {len(queries)} queries"
    )
    if level == PRESSURE_STOP:
        raise ProbeStopped(
            "memory pressure is critical (4); close apps and check again"
        )

    rows = []
    for i, q in enumerate(queries, 1):
        chunks = retrieve(q["question"], q["product_id"])
        old = ask(old_body(q["question"], chunks, template))
        new_raw = ask(generate._request_body(q["question"], chunks))
        final, no_answer = generate.finalize(new_raw)
        row = {
            "qa_id": q["qa_id"],
            "answerable": q["answerable"] is True,
            "question": q["question"],
            "old": old,
            "new_raw": new_raw,
            "new_final": final,
            "no_answer": no_answer,
        }
        rows.append(row)
        out_rows(row)
        if i % PRESSURE_EVERY == 0 or i == len(queries):
            level = pressure()
            log(f"  {i}/{len(queries)} done; pressure level {level}")
            if level == PRESSURE_STOP:
                raise ProbeStopped(f"memory pressure is critical (4) after {i} queries")
    result = shares(rows)
    result["new_prompt_sha256"] = generate.prompt_sha256()
    result["old_prompt_sha256"] = refs.sha256_bytes(template.encode("utf-8"))
    result["seed"] = SEED
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--out", required=True, help="the answers (private: Amazon-PQA wording)"
    )
    ap.add_argument("--summary", required=True, help="the counts (no text)")
    args = ap.parse_args(argv)
    queries = draw(refs.load_split("validation"))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(out_path, "x") as f:

            def write_row(row: dict) -> None:
                f.write(json.dumps(row) + "\n")
                f.flush()

            result = probe(queries, out_rows=write_row)
    except FileExistsError:
        print(
            f"prompt-probe: {out_path} exists; it is never overwritten", file=sys.stderr
        )
        return 1
    except ProbeStopped as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        return 1
    Path(args.summary).write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"meta phrases   old {result['meta_old']}/{result['n']} ({result['meta_share_old']:.3f})  "
        f"new {result['meta_new']}/{result['n']} ({result['meta_share_new']:.3f})  "
        f"{'PASS' if result['meta_ok'] else 'FAIL'} (new at most half of old)"
    )
    print(
        f"refusal on answerable  old don't-know {result['dont_know_old']}/{result['n_answerable']} "
        f"({result['refuse_share_old']:.3f})  new NO_ANSWER {result['no_answer_new']}/"
        f"{result['n_answerable']} ({result['refuse_share_new']:.3f})  "
        f"{'PASS' if result['refuse_ok'] else 'FAIL'} (new at most old + 3 points)"
    )
    print(f"  NO_ANSWER over all {result['n']}: {result['no_answer_new_all']}")
    print(f"  new prompt sha256 {result['new_prompt_sha256']}")
    print(f"  wrote {args.out} (private) and {args.summary}")
    return 0 if result["meta_ok"] and result["refuse_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
