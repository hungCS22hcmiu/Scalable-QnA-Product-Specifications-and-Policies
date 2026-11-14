"""Item 6.0a: calibrate tau_P, the similarity threshold of the shared namespace.

    make scope-calibrate

The rule is fixed in design.md section 1, before any replay, and uses no judge verdict:

  Take the validation policy questions (gold evidence is one policy document, the query has a
  `product_id`). Take every pair of them that sit on the same policy document. A pair "passes raw" when
  the cosine of the two stored question vectors is at least tau = 0.85. tau_P is the smallest projected
  cosine at which the share of pairs that pass is not above the share that passes raw at tau = 0.85.

The projected cosine of a pair is the cosine of v' = normalise(v - (v . t^) t^), one for each question,
where t is the title vector of that question's own product (`docmeta:{product_id}` in Redis). A question
whose projection does not exist (a missing title vector, or nothing left after the projection) never
passes. The projection is the one in contracts/scope/cases.json; Go has the same function
(reuse.Project).

Reads `data/v1-draft/workload/vectors.json` and Redis. It writes nothing to Redis, and it loads no
model. The result goes to `--out` (a JSON file) and to the screen.

Exit codes: 0 done; 1 an input is missing or a rule refused.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

import judge_references as refs
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
VECTORS_PATH = ROOT / "data" / "v1-draft" / "workload" / "vectors.json"
TAU = 0.85  # ADR-009's tau, the raw threshold the rule compares with
CUT = 0.10  # the scope test's bound-word cut, pinned (rag/src/rag/docmeta.py)
NEAR_ZERO = 1e-6  # |v'| <= NEAR_ZERO * |v| means nothing is left after the projection
DOCMETA_PREFIX = "docmeta:"
DECIMALS = 4  # tau_P is rounded UP to this many decimals, so the rounding can only lower the share


class CalibrationError(RuntimeError):
    """An input is missing or wrong. The message says which."""


def project(v, t) -> list[float] | None:
    """v' = normalise(v - (v . t^) t^) with t^ = t / |t|; None when t is missing or zero, when |v| is 0,
    or when |v'| <= 1e-6 * |v|. The same rule as reuse.Project (contracts/scope/cases.json)."""
    v = np.asarray(v, dtype=np.float64)
    t = np.asarray(t, dtype=np.float64)
    if t.size == 0:
        return None
    nt = float(np.linalg.norm(t))
    nv = float(np.linalg.norm(v))
    if nt == 0.0 or nv == 0.0:
        return None
    th = t / nt
    r = v - float(v @ th) * th
    nr = float(np.linalg.norm(r))
    if nr <= NEAR_ZERO * nv:
        return None
    return (r / nr).tolist()


def policy_questions(queries: list[dict]) -> list[dict]:
    """The queries the rule is about: one gold document, a policy, and a `product_id`."""
    out = []
    for q in queries:
        docs = q.get("doc_ids") or []
        if len(docs) == 1 and docs[0].startswith("policy-") and q.get("product_id"):
            out.append(q)
    return out


def _unit(vec) -> np.ndarray:
    a = np.asarray(vec, dtype=np.float64)
    n = float(np.linalg.norm(a))
    if n == 0.0:
        raise CalibrationError("a stored question vector is zero")
    return a / n


def calibrate(
    queries: list[dict],
    vectors: dict[str, dict],
    titles: dict[str, list[float]],
    tau: float = TAU,
) -> dict:
    """The rule of the module docstring. `vectors[qa_id]["vector"]` is the stored question vector;
    `titles[product_id]` is that product's title vector. Raises when an input is missing."""
    policy = policy_questions(queries)
    if not policy:
        raise CalibrationError("no validation policy question has a product_id")
    unit: dict[str, np.ndarray] = {}
    proj: dict[str, np.ndarray | None] = {}
    for q in policy:
        qa = q["qa_id"]
        if qa not in vectors:
            raise CalibrationError(f"{qa} has no stored vector")
        unit[qa] = _unit(vectors[qa]["vector"])
        if q["product_id"] not in titles:
            raise CalibrationError(f"{q['product_id']} has no title vector in Redis")
        p = project(vectors[qa]["vector"], titles[q["product_id"]])
        proj[qa] = None if p is None else np.asarray(p, dtype=np.float64)

    by_doc: dict[str, list[str]] = defaultdict(list)
    for q in policy:
        by_doc[q["doc_ids"][0]].append(q["qa_id"])

    raw_cos: list[float] = []
    proj_cos: list[float] = []  # -2.0 where a pair has no projection: it can never pass
    for ids in by_doc.values():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                raw_cos.append(float(unit[a] @ unit[b]))
                if proj[a] is None or proj[b] is None:
                    proj_cos.append(-2.0)
                else:
                    proj_cos.append(float(proj[a] @ proj[b]))
    n = len(raw_cos)
    if n == 0:
        raise CalibrationError("no two policy questions share a policy document")

    raw_pass = sum(1 for c in raw_cos if c >= tau)
    ranked = sorted(proj_cos, reverse=True)
    # The smallest projected cosine c with count(proj >= c) <= raw_pass. With ranked[k-1] the k-th
    # largest, that is ranked[raw_pass - 1] unless a tie runs past it; then the first value above the tie.
    if raw_pass == 0:
        exact = (
            ranked[0] + 10**-DECIMALS
        )  # nothing passes raw, so nothing may pass projected
    else:
        exact = min(
            c for c in set(proj_cos) if sum(1 for x in proj_cos if x >= c) <= raw_pass
        )
    tau_p = math.ceil(exact * 10**DECIMALS - 1e-9) / 10**DECIMALS
    proj_pass = sum(1 for c in proj_cos if c >= tau_p)
    if proj_pass > raw_pass:
        raise CalibrationError(
            f"tau_P {tau_p} lets {proj_pass} pairs pass, raw lets {raw_pass}"
        )
    return {
        "rule": "design.md section 1: smallest projected cosine whose pass share is not above the raw share",
        "tau_raw": tau,
        "scope_test_cut": CUT,
        "policy_questions": len(policy),
        "policy_documents": len(by_doc),
        "pairs": n,
        "no_projection_pairs": sum(1 for c in proj_cos if c == -2.0),
        "raw_pass": raw_pass,
        "raw_pass_share": raw_pass / n,
        "tau_p_exact": exact,
        "tau_p": tau_p,
        "projected_pass": proj_pass,
        "projected_pass_share": proj_pass / n,
    }


def read_titles(client, product_ids: set[str]) -> dict[str, list[float]]:
    """`title_vec` of each product, from `docmeta:{doc_id}` (float32 little-endian). Raises on a gap."""
    titles = {}
    for pid in sorted(product_ids):
        blob = client.hget(f"{DOCMETA_PREFIX}{pid}", "title_vec")
        if not blob:
            raise CalibrationError(
                f"{DOCMETA_PREFIX}{pid} has no title_vec (run make docmeta)"
            )
        titles[pid] = np.frombuffer(blob, dtype="<f4").astype(np.float64).tolist()
    return titles


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="where to write the JSON result")
    ap.add_argument("--vectors", default=str(VECTORS_PATH))
    ap.add_argument(
        "--redis-url", default=os.environ.get("REDIS_URL", "redis://localhost:6379")
    )
    args = ap.parse_args(argv)
    import redis

    try:
        queries = refs.load_split("validation")
        vectors = json.loads(Path(args.vectors).read_text())
        needed = {q["product_id"] for q in policy_questions(queries)}
        titles = read_titles(redis.from_url(args.redis_url), needed)
        result = calibrate(queries, vectors, titles)
    except (CalibrationError, OSError, ValueError) as e:
        print(f"scope-calibrate FAILED: {e}", file=sys.stderr)
        return 1
    except redis.RedisError as e:
        print(f"scope-calibrate FAILED: redis: {e!r}", file=sys.stderr)
        return 1
    result["date"] = datetime.datetime.now().astimezone().date().isoformat()
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"scope-calibrate: {result['policy_questions']} policy questions on "
        f"{result['policy_documents']} documents, {result['pairs']} pairs on the same document"
    )
    print(
        f"  raw cosine >= {result['tau_raw']}: {result['raw_pass']} pairs "
        f"({result['raw_pass_share']:.4f})"
    )
    print(
        f"  projected pairs with no projection: {result['no_projection_pairs']}; "
        f"tau_P = {result['tau_p']} ({result['projected_pass']} pairs, "
        f"{result['projected_pass_share']:.4f}; exact {result['tau_p_exact']:.6f})"
    )
    print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
