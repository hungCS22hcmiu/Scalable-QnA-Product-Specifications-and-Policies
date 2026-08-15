import pytest

from rag.chunkid import make_chunk_id, parse_chunk_id


def test_make_chunk_id():
    assert make_chunk_id("policy-returns", 2) == "policy-returns#chunk-2"


def test_round_trip():
    chunk_id = make_chunk_id("product-B08XYZ", 7)
    doc_id, ordinal = parse_chunk_id(chunk_id)
    assert doc_id == "product-B08XYZ"
    assert ordinal == 7


def test_ordinal_zero():
    assert parse_chunk_id("policy-returns#chunk-0") == ("policy-returns", 0)


def test_rejects_ambiguous_doc_id():
    with pytest.raises(ValueError):
        make_chunk_id("weird#chunk-0-id", 1)


def test_parse_rejects_malformed():
    with pytest.raises(ValueError):
        parse_chunk_id("not-a-chunk-id")
