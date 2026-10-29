"""Build N distinct RAG prompts exactly as rag.server would, for the 300-request memory probe.

    python3 build_prompts.py <workload.json> <out.jsonl> <n>

citable: no. This is this task's own probe script (ADR-017), not tooling. It loads the embedding
model through Ollama (retrieval), so check memory pressure first.

Selection (design section 3): the first question of each `cluster_id`, in file order (270 for
`data/workload-v1-validation.json`); then, in file order, further questions whose `qa_id` is not
taken yet, until N. Every prompt differs, so a live prompt cache cannot be hidden by a repeat.

Each prompt is built as the service builds it: `rag.retrieve.retrieve` with the question's
`product_id`, then `rag.generate._build_prompt`. Output fields are the RCA builder's.
"""

import json
import sys

from rag import generate, retrieve


def pick(items: list[dict], n: int) -> list[dict]:
    picked: list[dict] = []
    taken: set[str] = set()
    seen_clusters: set[str] = set()
    for it in items:
        if it["cluster_id"] in seen_clusters:
            continue
        seen_clusters.add(it["cluster_id"])
        taken.add(it["qa_id"])
        picked.append(it)
        if len(picked) == n:
            return picked
    for it in items:
        if it["qa_id"] in taken:
            continue
        taken.add(it["qa_id"])
        picked.append(it)
        if len(picked) == n:
            return picked
    raise SystemExit(f"the workload holds only {len(picked)} questions, {n} asked")


def main() -> None:
    workload, out, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    with open(workload) as f:
        items = json.load(f)
    picked = pick(items, n)
    with open(out, "w") as f:
        for it in picked:
            chunks, _epoch = retrieve.retrieve(
                it["question"], product_id=it["product_id"]
            )
            record = {
                "qa_id": it["qa_id"],
                "product_id": it["product_id"],
                "chunk_ids": [c.chunk_id for c in chunks],
                "prompt": generate._build_prompt(it["question"], chunks),
            }
            f.write(json.dumps(record) + "\n")
    print(len(picked), "prompts written")


if __name__ == "__main__":
    main()
