"""Load data/dev-v0/*.json -> chunk -> embed (Ollama) -> write to Redis (FLAT index).

W5 scope only: retrieval corpus, no generation. See docs/architecture.md §5.
"""

import json
from pathlib import Path

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode, Document

from rag import chunkid, config, epoch, store
from rag.embedding import OllamaEmbedding

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / config.DATASET_VERSION


def load_records(data_dir: Path) -> list[dict]:
    records = []
    for path in sorted(data_dir.glob("*.json")):
        with open(path) as f:
            record = json.load(f)
        if record["doc_id"] != path.stem:
            raise ValueError(f"{path}: doc_id {record['doc_id']!r} != filename {path.stem!r}")
        records.append(record)

    seen = set()
    for r in records:
        if r["doc_id"] in seen:
            raise ValueError(f"duplicate doc_id: {r['doc_id']!r}")
        seen.add(r["doc_id"])

    if not records:
        raise ValueError(f"no *.json files found under {data_dir}")
    return records


def record_kind(doc_id: str) -> str:
    if doc_id.startswith("product-"):
        return "product"
    if doc_id.startswith("policy-"):
        return "policy"
    raise ValueError(f"doc_id {doc_id!r} must start with 'product-' or 'policy-'")


def product_to_text(record: dict) -> str:
    lines = [f"Product: {record['title']}", f"Category: {record['category']}", "Specs:"]
    for key, value in record["specs"].items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def policy_to_text(record: dict) -> str:
    return f"{record['title']}\n\n{record['text']}"


def record_to_document(record: dict) -> Document:
    kind = record_kind(record["doc_id"])
    text = product_to_text(record) if kind == "product" else policy_to_text(record)
    return Document(
        text=text,
        doc_id=record["doc_id"],
        metadata={
            "doc_id": record["doc_id"],
            "kind": kind,
            "category": record.get("category", ""),
            "title": record["title"],
        },
    )


def records_to_nodes(records: list[dict], dataset_version: str) -> list[BaseNode]:
    """Split records into chunks with their stable ids and metadata.

    The one split loop: `main` writes these nodes, and the corpus gate's chunk digest reads them,
    so the digest cannot drift from what is ingested.
    """
    splitter = SentenceSplitter(chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP)

    all_nodes = []
    for record in records:
        document = record_to_document(record)
        nodes = splitter.get_nodes_from_documents([document])
        for ordinal, node in enumerate(nodes):
            node.id_ = chunkid.make_chunk_id(record["doc_id"], ordinal)
            node.metadata["chunk_id"] = node.id_
            node.metadata["ordinal"] = ordinal
            node.metadata["dataset_version"] = dataset_version
            node.excluded_embed_metadata_keys = list(node.metadata.keys())
            node.excluded_llm_metadata_keys = list(node.metadata.keys())
        all_nodes.extend(nodes)
    return all_nodes


def _write_index(nodes: list[BaseNode]) -> None:
    """Embed the nodes and write them to the Redis FLAT index, replacing what was there."""
    vector_store = store.get_vector_store(overwrite=True)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    embed_model = OllamaEmbedding()

    VectorStoreIndex(
        nodes,
        storage_context=storage_context,
        embed_model=embed_model,
        show_progress=True,
    )


def main() -> None:
    # The epoch path is checked first, so a long ingest cannot fail at the end for want of it.
    epoch_path = epoch.require_path()

    records = load_records(DATA_DIR)
    print(f"loaded {len(records)} records from {DATA_DIR}")

    all_nodes = records_to_nodes(records, config.DATASET_VERSION)

    print(f"split into {len(all_nodes)} chunks")

    _write_index(all_nodes)

    print(f"indexed {len(records)} docs, {len(all_nodes)} chunks -> {config.CORPUS_INDEX_NAME}")

    # Advance only after every chunk is written (interfaces.md E): a write-back in flight during
    # a rebuild then carries the old epoch and is discarded. Advancing before the write would
    # let a retrieval between the two read old chunks under the new epoch.
    print(f"dataset epoch advanced to {epoch.advance()} ({epoch_path})")


if __name__ == "__main__":
    main()
