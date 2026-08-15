"""Stable chunk-ID scheme — interfaces.md §C, reuse-critical for C1/C2.

Format: {doc_id}#chunk-{ordinal}. Must survive the dev-v0 -> v1 corpus change (ADR-020):
a re-chunk is a new dataset_version, never a silent ID reassignment.
"""

SEPARATOR = "#chunk-"


def make_chunk_id(doc_id: str, ordinal: int) -> str:
    if SEPARATOR in doc_id:
        raise ValueError(f"doc_id {doc_id!r} must not contain {SEPARATOR!r} (ambiguous chunk_id)")
    return f"{doc_id}{SEPARATOR}{ordinal}"


def parse_chunk_id(chunk_id: str) -> tuple[str, int]:
    doc_id, _, tail = chunk_id.rpartition(SEPARATOR)
    if not doc_id:
        raise ValueError(f"{chunk_id!r} is not a valid chunk_id (expected doc_id{SEPARATOR}n)")
    return doc_id, int(tail)
