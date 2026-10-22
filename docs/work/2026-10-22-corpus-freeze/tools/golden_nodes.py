"""Plan steps 2 and 4: a digest of every node `rag.ingest` would write, for dev-v0 and for v1.

It runs the real `ingest.main`, with the vector store, the storage context, the embedding model
and `VectorStoreIndex` replaced by a capture, so the nodes are the ones main builds and nothing
touches Redis or Ollama. For v1 it points `ingest` at a temporary folder of symlinks to the 152
drafts and the 12 policy documents (nothing is copied, and `data/v1/` is not touched).

    golden_nodes.py            print the two digests
    golden_nodes.py --record   write evidence/golden-nodes.md (step 2, with the OLD ingest.py)
    golden_nodes.py --check    compare with that file; exit 1 on a difference (step 4, after the move)

The dump holds, per node: class, id, text in three metadata modes, metadata in order, both excluded
key lists, start and end index, ref_doc_id, relationships, node hash and the template fields. Only
digests are written to disk: a hash of PQA text is not text.
"""

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "docs" / "work" / "2026-10-22-corpus-freeze" / "evidence" / "golden-nodes.md"
INGEST = REPO / "rag" / "src" / "rag" / "ingest.py"
EXPECTED = {"dev-v0": 44, "v1": 539}  # the node counts in design.md §2.1


UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def node_dump(node, labels):
    """One node as plain data.

    The splitter links each chunk to its neighbours by a random UUID, and `ingest` then renames
    the chunk without touching those links, so PREVIOUS and NEXT hold stale random ids that differ
    on every run. They are replaced by a label per UUID, in order of first appearance: the chain
    structure stays in the digest, the randomness does not. Any id that is not a UUID is kept raw.
    """
    from llama_index.core.schema import MetadataMode

    def ident(node_id):
        if UUID.match(node_id):
            return labels.setdefault(node_id, f"uuid-{len(labels)}")
        return node_id

    relationships = {}
    for key, value in sorted(node.relationships.items(), key=lambda kv: str(kv[0])):
        items = value if isinstance(value, list) else [value]
        relationships[str(key)] = [(ident(r.node_id), str(r.node_type)) for r in items]
    return {
        "class": type(node).__name__,
        "id": node.node_id,
        "text_none": node.get_content(MetadataMode.NONE),
        "text_embed": node.get_content(MetadataMode.EMBED),
        "text_llm": node.get_content(MetadataMode.LLM),
        "metadata": list(node.metadata.items()),
        "excluded_embed": list(node.excluded_embed_metadata_keys),
        "excluded_llm": list(node.excluded_llm_metadata_keys),
        "start": node.start_char_idx,
        "end": node.end_char_idx,
        "ref_doc_id": node.ref_doc_id,
        "relationships": relationships,
        "hash": node.hash,
        "templates": [node.text_template, node.metadata_template, node.metadata_separator],
    }


def capture_nodes(data_dir, version):
    """Run the real ingest.main with the storage and embedding calls replaced by a capture."""
    from rag import config, ingest

    captured = []

    def fake_index(nodes, **_):
        captured.extend(nodes)

    with (
        mock.patch.object(ingest, "DATA_DIR", data_dir),
        mock.patch.object(config, "DATASET_VERSION", version),
        mock.patch.object(ingest.store, "get_vector_store", lambda **_: object()),
        mock.patch.object(ingest.StorageContext, "from_defaults", lambda **_: object()),
        mock.patch.object(ingest, "OllamaEmbedding", lambda: object()),
        mock.patch.object(ingest, "VectorStoreIndex", fake_index),
    ):
        ingest.main()
    return captured


def digest(nodes):
    labels = {}
    dump = [node_dump(n, labels) for n in nodes]
    blob = json.dumps(dump, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def compute():
    out = {}
    nodes = capture_nodes(REPO / "data" / "dev-v0", "dev-v0")
    out["dev-v0"] = (len(nodes), digest(nodes))

    sources = sorted((REPO / "data" / "v1-draft" / "products").glob("*.json"))
    sources += sorted((REPO / "data" / "policies-v1").glob("*.json"))
    with tempfile.TemporaryDirectory() as tmp:
        for path in sources:
            (Path(tmp) / path.name).symlink_to(path)
        nodes = capture_nodes(Path(tmp), "v1")
    out["v1"] = (len(nodes), digest(nodes))
    out["v1-inputs"] = (len(sources), "")
    return out


def recorded():
    text = OUT.read_text()
    return {m[0]: (int(m[1]), m[2]) for m in re.findall(r"^\| (dev-v0|v1) \| (\d+) \| ([0-9a-f]{64}) \|", text, re.MULTILINE)}


def main():
    result = compute()
    print(f"v1 input files: {result.pop('v1-inputs')[0]}")
    for name, (count, dig) in result.items():
        print(f"{name}: {count} nodes  {dig}")
        if count != EXPECTED[name]:
            sys.exit(f"{name}: expected {EXPECTED[name]} nodes (design.md §2.1)")

    if "--record" in sys.argv:
        blob = subprocess.run(
            ["git", "hash-object", str(INGEST)], capture_output=True, text=True, check=True
        ).stdout.strip()
        lines = [
            "# Golden node digests — item 3.6, plan steps 2 and 4",
            "",
            "Written by `tools/golden_nodes.py --record` with the **old** `rag/src/rag/ingest.py`",
            f"(git blob `{blob}`), before the refactor. After the move into `records_to_nodes`,",
            "`tools/golden_nodes.py --check` must give the same two digests.",
            "",
            "The digest is a sha256 over a dump of every node `ingest.main` builds: class, id, text in",
            "three metadata modes, metadata in order, both excluded-key lists, start and end index,",
            "`ref_doc_id`, relationships, node hash and the template fields. v1 is the 152 drafts and",
            "the 12 policy documents. No text is kept, only the digests.",
            "",
            "**Finding while taking it.** The splitter links each chunk to its neighbours by a random",
            "UUID; `ingest` renames the chunk afterwards and leaves those links alone, so PREVIOUS and",
            "NEXT hold stale random ids that change on every run (513 of the 539 v1 nodes; none in",
            "dev-v0, where every document is one chunk). They reach Redis inside `_node_content`.",
            "Harmless for retrieval, but nothing may ever hash `_node_content` or the whole hash:",
            "the index check hashes `chunk_id` and `text` only. The dump above replaces each UUID by a",
            "label in order of first appearance, so the chain structure is kept and the randomness is not.",
            "",
            "| dataset | nodes | digest |",
            "| :--- | ---: | :--- |",
        ]
        lines += [f"| {name} | {count} | {dig} |" for name, (count, dig) in result.items()]
        OUT.write_text("\n".join(lines) + "\n")
        print(f"wrote {OUT.relative_to(REPO)}")
    elif "--check" in sys.argv:
        want = recorded()
        bad = [n for n, got in result.items() if want.get(n) != got]
        if bad:
            sys.exit(f"DIFFERENT from {OUT.name}: {', '.join(bad)}")
        print("same as the recorded digests")


if __name__ == "__main__":
    main()
