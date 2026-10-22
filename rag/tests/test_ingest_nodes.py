"""records_to_nodes: the one split loop that ingest writes and the corpus gate's digest reads.

Pure: no Redis, no Ollama. The records are synthetic. The byte-level check that the move out of
`main` changed nothing is the golden node dump in docs/work/2026-10-22-corpus-freeze/.
"""

from rag import chunkid
from rag.ingest import records_to_nodes

PRODUCT = {
    "doc_id": "product-test-0001",
    "title": "Test Kettle",
    "category": "kitchen",
    "specs": {"capacity": "1.7 L", "power": "2200 W"},
}
# Long enough to split into several chunks at chunk_size 256.
POLICY = {
    "doc_id": "policy-test-returns",
    "title": "Test returns",
    "text": " ".join(f"Item {i} may be returned within thirty days." for i in range(80)),
}


def test_ids_follow_the_stable_scheme():
    nodes = records_to_nodes([PRODUCT, POLICY], "v1")
    assert len(nodes) > 2  # the policy really split
    for node in nodes:
        doc_id, ordinal = chunkid.parse_chunk_id(node.id_)
        assert node.metadata["doc_id"] == doc_id
        assert node.metadata["ordinal"] == ordinal
        assert node.metadata["chunk_id"] == node.id_


def test_ordinals_run_from_zero_inside_each_document():
    nodes = records_to_nodes([PRODUCT, POLICY], "v1")
    for doc_id in (PRODUCT["doc_id"], POLICY["doc_id"]):
        ordinals = [n.metadata["ordinal"] for n in nodes if n.metadata["doc_id"] == doc_id]
        assert ordinals == list(range(len(ordinals)))


def test_the_version_is_the_argument():
    for version in ("v1", "dev-v0"):
        nodes = records_to_nodes([POLICY], version)
        assert {n.metadata["dataset_version"] for n in nodes} == {version}


def test_every_metadata_key_is_kept_out_of_the_embedded_text():
    for node in records_to_nodes([PRODUCT, POLICY], "v1"):
        keys = list(node.metadata.keys())
        assert node.excluded_embed_metadata_keys == keys
        assert node.excluded_llm_metadata_keys == keys


def test_the_same_records_give_the_same_ids_and_texts():
    first = records_to_nodes([PRODUCT, POLICY], "v1")
    second = records_to_nodes([PRODUCT, POLICY], "v1")
    assert [(n.id_, n.text) for n in first] == [(n.id_, n.text) for n in second]
