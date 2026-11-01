"""Item 5.1, done conditions 6 and 7 (docs/work/2026-10-30-judge-harness/design.md): the gold audit and
the gold-anchored references.

A reference built from the wrong chunks is the silent failure here. `Answer` retrieves for itself when
`retrieved_chunk_ids` is empty, and `fetch_by_ids` drops a chunk it cannot find with no error, so a
reference could be grounded on the system's own retrieval, or on fewer chunks than the gold documents
hold, and nothing would say so. Each test pins one way that happens.

No Ollama, no Redis, no network. The corpus is a handful of documents written to a temp folder; the
generator is a fake function.
"""

import hashlib
import json

import judge_references as jr
import pytest

LONG_POLICY = " ".join(
    f"Item {i} may be returned within thirty days of delivery." for i in range(90)
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# =================================================================================================
# A small corpus and a small workload
# =================================================================================================
def write_corpus(directory):
    directory.mkdir(exist_ok=True)
    docs = [
        {
            "doc_id": "product-mug",
            "title": "Mug",
            "category": "kitchen",
            "specs": {"capacity": "300 ml", "material": "ceramic"},
        },
        {
            "doc_id": "product-lamp",
            "title": "Lamp",
            "category": "home",
            "specs": {"power": "9 W"},
        },
        {
            "doc_id": "policy-return-new",
            "title": "Returns of unopened items",
            "category": "all",
            "policy_kind": "return",
            "condition": None,
            "text": LONG_POLICY,
        },
    ]
    for doc in docs:
        (directory / f"{doc['doc_id']}.json").write_text(json.dumps(doc))
    return directory


CHUNKS = {
    "product-mug": ["product-mug#chunk-0"],
    "product-lamp": ["product-lamp#chunk-0"],
    "policy-return-new": [f"policy-return-new#chunk-{i}" for i in range(3)],
}
TEXTS = {c: f"text of {c}" for ids in CHUNKS.values() for c in ids}


def query(qa_id="q-1", stratum="A", docs=("product-mug",), **kw):
    q = {
        "qa_id": qa_id,
        "question": f"Question for {qa_id}?",
        "product_id": "product-mug",
        "stratum": stratum,
        "doc_ids": list(docs),
        "reference_answer": "",
        "answerable": True,
    }
    q.update(kw)
    return q


# =================================================================================================
# DC 6: gold order and the gold audit
# =================================================================================================
def test_corpus_chunks_gives_each_documents_chunks_in_ordinal_order(tmp_path):
    chunks, texts = jr.corpus_chunks(write_corpus(tmp_path / "v1"))

    assert set(chunks) == {"product-mug", "product-lamp", "policy-return-new"}
    assert chunks["product-mug"] == ["product-mug#chunk-0"]
    policy = chunks["policy-return-new"]
    assert len(policy) >= 2  # the long policy splits
    assert policy == [f"policy-return-new#chunk-{i}" for i in range(len(policy))]
    assert set(texts) == {c for ids in chunks.values() for c in ids}
    assert texts["product-mug#chunk-0"].startswith("Product: Mug")


def test_doc_chunk_ids_is_the_first_half_of_corpus_chunks(tmp_path):
    corpus = write_corpus(tmp_path / "v1")
    assert jr.doc_chunk_ids(corpus) == jr.corpus_chunks(corpus)[0]


def test_gold_chunks_follow_doc_ids_order_then_ordinal_order():
    # D: the product first, then the policy, as the workload lists them.
    assert jr.gold_chunk_ids(["product-mug", "policy-return-new"], CHUNKS) == [
        "product-mug#chunk-0",
        "policy-return-new#chunk-0",
        "policy-return-new#chunk-1",
        "policy-return-new#chunk-2",
    ]
    # the order is the query's, not alphabetical and not the corpus's
    assert jr.gold_chunk_ids(["policy-return-new", "product-mug"], CHUNKS) == [
        "policy-return-new#chunk-0",
        "policy-return-new#chunk-1",
        "policy-return-new#chunk-2",
        "product-mug#chunk-0",
    ]


def test_gold_chunks_of_one_document_keep_ordinal_order():
    shuffled = {"policy-return-new": CHUNKS["policy-return-new"]}
    assert (
        jr.gold_chunk_ids(["policy-return-new"], shuffled)
        == CHUNKS["policy-return-new"]
    )


def test_gold_chunk_ids_raises_on_an_unknown_document():
    with pytest.raises(ValueError, match="unknown doc_id 'product-nowhere'"):
        jr.gold_chunk_ids(["product-mug", "product-nowhere"], CHUNKS)


def test_gold_chunk_ids_raises_on_an_empty_result():
    with pytest.raises(ValueError, match="empty"):
        jr.gold_chunk_ids([], CHUNKS)
    with pytest.raises(ValueError, match="empty"):
        jr.gold_chunk_ids(["product-hollow"], {"product-hollow": []})


def test_a_clean_workload_has_no_gold_problems():
    queries = [
        query("a", "A"),
        query("b", "B-within", ("policy-return-new",)),
        query("c", "B-cross"),
        query("d", "C", ("policy-return-new",)),
        query("e", "D", ("product-mug", "policy-return-new")),
        query("f", "D", ("policy-return-new", "product-mug")),
    ]
    assert jr.gold_problems(queries, CHUNKS, TEXTS) == []


def test_gold_problems_names_an_unknown_doc_id():
    problems = jr.gold_problems(
        [query("q-x", docs=("product-nowhere",))], CHUNKS, TEXTS
    )
    assert problems == ["q-x: unknown doc_id product-nowhere"]


@pytest.mark.parametrize(
    "stratum, docs, wants",
    [
        ("A", ("product-mug", "product-lamp"), "wants one document"),
        ("B-within", ("product-mug", "policy-return-new"), "wants one document"),
        ("B-cross", ("product-mug", "product-lamp"), "wants one document"),
        ("C", ("policy-return-new", "product-mug"), "wants one document"),
        ("D", ("product-mug",), "one product and one policy"),
        ("D", ("policy-return-new",), "one product and one policy"),
        ("D", ("product-mug", "product-lamp"), "one product and one policy"),
        ("D", ("policy-return-new", "policy-return-new"), "one product and one policy"),
        ("Z", ("product-mug",), "unknown stratum"),
    ],
)
def test_gold_problems_names_kinds_that_do_not_fit_the_stratum(stratum, docs, wants):
    problems = jr.gold_problems([query("q-k", stratum, docs)], CHUNKS, TEXTS)
    assert (
        len(problems) == 1 and problems[0].startswith("q-k:") and wants in problems[0]
    )


def test_gold_problems_names_a_missing_or_empty_doc_ids():
    assert (
        "doc_ids is missing or empty"
        in jr.gold_problems([query("q-e", docs=())], CHUNKS, TEXTS)[0]
    )
    no_docs = query("q-n")
    del no_docs["doc_ids"]
    assert (
        "doc_ids is missing or empty" in jr.gold_problems([no_docs], CHUNKS, TEXTS)[0]
    )


@pytest.mark.parametrize("filled", ["The right answer.", " ", None])
def test_gold_problems_names_a_reference_answer_that_is_not_the_empty_string(filled):
    problems = jr.gold_problems([query("q-r", reference_answer=filled)], CHUNKS, TEXTS)
    assert problems == ["q-r: reference_answer is not the empty string"]


def test_gold_problems_names_a_gold_set_over_the_character_limit():
    long_texts = {**TEXTS, "product-mug#chunk-0": "x" * (jr.GOLD_CHAR_LIMIT + 1)}
    problems = jr.gold_problems([query("q-big")], CHUNKS, long_texts)
    assert len(problems) == 1 and "q-big" in problems[0] and "over 24000" in problems[0]


def test_a_gold_set_exactly_at_the_limit_passes():
    at_limit = {**TEXTS, "product-mug#chunk-0": "x" * jr.GOLD_CHAR_LIMIT}
    assert jr.gold_problems([query("q-ok")], CHUNKS, at_limit) == []


def test_the_character_limit_counts_what_generate_builds_with_its_separators():
    # Two chunks of 12,000 are 24,000 characters of text and 24,002 in the prompt's context.
    chunks = {"product-mug": ["a#chunk-0", "a#chunk-1"]}
    texts = {"a#chunk-0": "x" * 12_000, "a#chunk-1": "y" * 12_000}
    assert jr.gold_context_length(chunks["product-mug"], texts) == 24_002
    problems = jr.gold_problems([query("q-two")], chunks, texts)
    assert len(problems) == 1 and "24002" in problems[0]


def test_gold_problems_never_quote_the_question_text():
    q = query("q-p", "Z", ("product-nowhere",), reference_answer="x")
    q["question"] = "A SECRET QUESTION WORDING"
    assert all("SECRET" not in line for line in jr.gold_problems([q], CHUNKS, TEXTS))


def test_gold_counts_by_stratum_and_answerable():
    queries = [
        query("a", "A"),
        query("b", "A", answerable=False),
        query("c", "B-within", ("policy-return-new",)),
        query("d", "D", ("product-mug", "policy-return-new")),
    ]
    queries.append(dict(queries[0], qa_id="a-again"))  # the same pair twice

    counts = jr.gold_counts(queries)

    assert counts["queries"] == 5
    assert counts["by_stratum"] == {"A": 3, "B-within": 1, "D": 1}
    assert counts["by_answerable"] == {"true": 4, "false": 1}
    assert counts["two_documents"] == 1
    assert counts["distinct_pairs"] == 4


def test_gold_check_prints_the_counts_and_returns_0_for_a_clean_workload(
    tmp_path, monkeypatch, capsys
):
    corpus = write_corpus(tmp_path / "v1")
    monkeypatch.setattr(
        jr, "load_split", lambda split: [query("a"), query("b", answerable=False)]
    )

    assert jr.gold_check("validation", corpus) == 0

    out = capsys.readouterr().out
    assert "2 queries" in out and "A 2" in out and "true 1, false 1" in out
    assert "judge-gold-check: ok" in out


def test_gold_check_returns_1_and_names_the_problem(tmp_path, monkeypatch, capsys):
    corpus = write_corpus(tmp_path / "v1")
    monkeypatch.setattr(
        jr,
        "load_split",
        lambda split: [query("a"), query("b", docs=("product-nowhere",))],
    )

    assert jr.gold_check("validation", corpus) == 1

    out = capsys.readouterr().out
    assert "FAIL  b: unknown doc_id product-nowhere" in out
    assert "1 problem(s)" in out


# =================================================================================================
# DC 7: make_reference
# =================================================================================================
def fake_answer(text="A reference.", sources=None, calls=None):
    def answer(question, product_id, chunk_ids):
        if calls is not None:
            calls.append((question, product_id, list(chunk_ids)))
        return text, list(chunk_ids) if sources is None else sources

    return answer


def test_make_reference_sends_the_gold_chunk_ids_in_order():
    calls = []
    ids = jr.gold_chunk_ids(["product-mug", "policy-return-new"], CHUNKS)

    ref = jr.make_reference(
        query("q-1", "D", ("product-mug", "policy-return-new")),
        ids,
        fake_answer("Yes.", calls=calls),
    )

    assert calls == [("Question for q-1?", "product-mug", ids)]
    assert ref["chunk_ids"] == ids
    assert ref["gold_doc_ids"] == ["product-mug", "policy-return-new"]
    assert ref["text"] == "Yes."
    assert ref["reference_sha256"] == sha("Yes.")
    assert ref["product_id"] == "product-mug" and ref["stratum"] == "D"


def test_make_reference_sends_an_empty_product_id_when_the_query_has_none():
    calls = []
    jr.make_reference(
        query("q-n", "C", ("policy-return-new",), product_id=None),
        CHUNKS["policy-return-new"],
        fake_answer(calls=calls),
    )
    assert calls[0][1] == ""


def test_make_reference_refuses_an_empty_chunk_list_and_never_calls_answer():
    calls = []
    with pytest.raises(jr.ReferenceRefused, match="no gold chunk IDs"):
        jr.make_reference(query("q-e"), [], fake_answer(calls=calls))
    assert calls == []  # Answer would have retrieved by itself


@pytest.mark.parametrize(
    "sources",
    [
        [
            "policy-return-new#chunk-0",
            "policy-return-new#chunk-1",
        ],  # a gold chunk was dropped
        [
            "policy-return-new#chunk-2",
            "policy-return-new#chunk-1",
            "policy-return-new#chunk-0",
        ],
        [
            *CHUNKS["policy-return-new"],
            "product-mug#chunk-0",
        ],  # a chunk that was not sent
        [
            "product-lamp#chunk-0"
        ],  # another document altogether: a retrieval, not the gold set
        [],
    ],
)
def test_make_reference_refuses_a_reply_grounded_on_other_chunks(sources):
    with pytest.raises(jr.ReferenceRefused, match="q-s: Answer grounded on"):
        jr.make_reference(
            query("q-s", docs=("policy-return-new",)),
            CHUNKS["policy-return-new"],
            fake_answer(sources=sources),
        )


# =================================================================================================
# DC 7: answer_in_process calls the Answer handler with the gold chunks
# =================================================================================================
def test_answer_in_process_hands_the_gold_chunks_to_the_answer_handler(monkeypatch):
    pytest.importorskip("rag.pb.rag.v1.rag_pb2")
    from rag import epoch, generate, retrieve

    fetched, generated = [], []

    def fake_fetch(chunk_ids):
        fetched.append(list(chunk_ids))
        return [
            retrieve.RetrievedChunk(c, 0.0, f"text {c}", "d", 0) for c in chunk_ids
        ], 3

    def fake_generate(question, chunks):
        generated.append((question, [c.chunk_id for c in chunks]))
        return "the reference"

    def never_retrieve(*args, **kwargs):
        raise AssertionError(
            "Answer retrieved for itself: the references would not be gold"
        )

    monkeypatch.setattr(epoch, "read", lambda: 3)
    monkeypatch.setattr(retrieve, "fetch_by_ids", fake_fetch)
    monkeypatch.setattr(retrieve, "retrieve", never_retrieve)
    monkeypatch.setattr(generate, "generate", fake_generate)
    ids = [
        "product-mug#chunk-0",
        "policy-return-new#chunk-1",
        "policy-return-new#chunk-0",
    ]

    text, sources = jr.answer_in_process("Can I return it?", "product-mug", ids)

    assert (text, sources) == ("the reference", ids)  # order kept, not sorted
    assert fetched == [ids]
    assert generated == [("Can I return it?", ids)]


# =================================================================================================
# DC 7: build
# =================================================================================================
class Recorder:
    def __init__(self):
        self.lines = []

    def __call__(self, line):
        self.lines.append(line)


def build_inputs(queries):
    return {
        "queries": queries,
        "corpus": (CHUNKS, TEXTS),
        "index_check": lambda: 0,
        "versions": lambda: {"generator": {"model": "m"}, "retrieval": {"top_k": 5}},
        "pressure": lambda: 1,
        "log": Recorder(),
    }


def three_queries():
    return [
        query("q-1", "A", ("product-mug",)),
        query("q-2", "B-within", ("policy-return-new",), answerable=False),
        query(
            "q-3", "D", ("product-mug", "policy-return-new"), product_id="product-mug"
        ),
    ]


def read_index(folder):
    lines = (folder / "index.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


def test_build_writes_one_content_addressed_reference_per_query(tmp_path):
    calls = []
    out = tmp_path / "refs" / "validation"

    result = jr.build(
        "validation",
        out,
        answer=fake_answer("An answer.", calls=calls),
        **build_inputs(three_queries()),
    )

    rows = read_index(out)
    assert [r["qa_id"] for r in rows] == ["q-1", "q-2", "q-3"]
    assert result["references"] == 3
    for row in rows:
        assert row["reference_sha256"] == sha("An answer.")
        assert (
            out / "answers" / f"{row['reference_sha256']}.txt"
        ).read_text() == "An answer."
        assert "text" not in row  # the text lives in answers/, not in the index
        assert set(row) == {
            "qa_id",
            "question",
            "product_id",
            "stratum",
            "answerable",
            "gold_doc_ids",
            "chunk_ids",
            "reference_sha256",
        }
    assert list((out / "answers").iterdir()) == [
        out / "answers" / f"{sha('An answer.')}.txt"
    ]
    version = json.loads((out / "version.json").read_text())
    assert version["generator"] == {"model": "m"} and version["split"] == "validation"
    assert version["references"] == 3 and "built_at" in version
    assert not (tmp_path / "refs" / "validation.partial").exists()
    assert (
        result["index_sha256"]
        == hashlib.sha256((out / "index.jsonl").read_bytes()).hexdigest()
    )


def test_build_passes_exactly_the_gold_chunks_in_order_to_the_generator(tmp_path):
    calls = []

    jr.build(
        "validation",
        tmp_path / "v",
        answer=fake_answer(calls=calls),
        **build_inputs(three_queries()),
    )

    assert [c[2] for c in calls] == [
        ["product-mug#chunk-0"],
        [
            "policy-return-new#chunk-0",
            "policy-return-new#chunk-1",
            "policy-return-new#chunk-2",
        ],
        [
            "product-mug#chunk-0",
            *CHUNKS["policy-return-new"],
        ],  # D: the product, then the policy
    ]
    rows = read_index(tmp_path / "v")
    assert [r["chunk_ids"] for r in rows] == [c[2] for c in calls]


def test_build_makes_one_reference_per_distinct_question_and_product(tmp_path):
    calls = []
    queries = [query("q-1"), query("q-1b", question="Question for q-1?"), query("q-2")]
    queries[1]["question"] = queries[0]["question"]  # the same pair under another qa_id

    result = jr.build(
        "validation",
        tmp_path / "v",
        answer=fake_answer(calls=calls),
        **build_inputs(queries),
    )

    assert result["references"] == 2 and len(calls) == 2
    assert [r["qa_id"] for r in read_index(tmp_path / "v")] == [
        "q-1",
        "q-2",
    ]  # the first qa_id


def test_build_keeps_one_question_under_two_products_as_two_references(tmp_path):
    queries = [
        query("q-1", product_id="product-mug"),
        query("q-2", product_id="product-lamp"),
    ]
    queries[1]["question"] = queries[0]["question"]
    queries[1]["doc_ids"] = ["product-lamp"]

    result = jr.build(
        "validation", tmp_path / "v", answer=fake_answer(), **build_inputs(queries)
    )

    assert result["references"] == 2


def test_build_refuses_one_pair_with_two_sets_of_gold_documents(tmp_path):
    queries = [query("q-1"), query("q-2", docs=("product-lamp",))]
    queries[1]["question"] = queries[0]["question"]
    with pytest.raises(jr.ReferenceRefused, match="q-2: same question and product"):
        jr.build(
            "validation", tmp_path / "v", answer=fake_answer(), **build_inputs(queries)
        )
    assert not (tmp_path / "v").exists()


def test_build_refuses_a_folder_that_exists_and_never_rewrites_it(tmp_path):
    out = tmp_path / "validation"
    jr.build(
        "validation", out, answer=fake_answer("first"), **build_inputs(three_queries())
    )
    before = (out / "index.jsonl").read_bytes()
    calls = []

    with pytest.raises(jr.ReferenceRefused, match="never overwritten"):
        jr.build(
            "validation",
            out,
            answer=fake_answer("second", calls=calls),
            **build_inputs(three_queries()),
        )

    assert calls == []  # the generator was never asked
    assert (out / "index.jsonl").read_bytes() == before
    assert (out / "answers" / f"{sha('first')}.txt").exists()
    assert not (out / "answers" / f"{sha('second')}.txt").exists()


def test_build_refuses_an_empty_folder_that_exists(tmp_path):
    out = tmp_path / "validation"
    out.mkdir()
    with pytest.raises(jr.ReferenceRefused, match="never overwritten"):
        jr.build(
            "validation", out, answer=fake_answer(), **build_inputs(three_queries())
        )


def test_build_refuses_a_partial_folder_left_by_an_earlier_build(tmp_path):
    (tmp_path / "validation.partial").mkdir()
    with pytest.raises(jr.ReferenceRefused, match="never overwritten"):
        jr.build(
            "validation",
            tmp_path / "validation",
            answer=fake_answer(),
            **build_inputs(three_queries()),
        )


def test_build_refuses_at_memory_pressure_4_before_it_asks_the_generator(tmp_path):
    calls = []
    inputs = build_inputs(three_queries()) | {"pressure": lambda: 4}
    with pytest.raises(jr.ReferenceRefused, match="critical"):
        jr.build(
            "validation", tmp_path / "v", answer=fake_answer(calls=calls), **inputs
        )
    assert calls == [] and not (tmp_path / "v").exists()


def test_build_prints_the_pressure_level(tmp_path):
    inputs = build_inputs(three_queries()) | {"pressure": lambda: 2}
    jr.build("validation", tmp_path / "v", answer=fake_answer(), **inputs)
    assert any("pressure level: 2" in line for line in inputs["log"].lines)


def test_build_stops_when_pressure_reaches_4_during_the_run(tmp_path):
    readings = iter([1, 4])
    inputs = build_inputs(three_queries()) | {"pressure": lambda: next(readings)}
    with pytest.raises(jr.ReferenceRefused, match="critical.*incomplete"):
        jr.build("validation", tmp_path / "v", answer=fake_answer(), **inputs)
    assert not (tmp_path / "v").exists()  # never a finished set


def test_build_refuses_unless_the_index_check_passes(tmp_path):
    calls = []
    inputs = build_inputs(three_queries()) | {"index_check": lambda: 1}
    with pytest.raises(jr.ReferenceRefused, match="corpus-index-check"):
        jr.build(
            "validation", tmp_path / "v", answer=fake_answer(calls=calls), **inputs
        )
    assert calls == [] and not (tmp_path / "v").exists()


def test_build_refuses_a_workload_with_a_gold_problem(tmp_path):
    calls = []
    queries = [query("q-1"), query("q-bad", docs=("product-nowhere",))]
    with pytest.raises(jr.ReferenceRefused, match="1 gold problem"):
        jr.build(
            "validation",
            tmp_path / "v",
            answer=fake_answer(calls=calls),
            **build_inputs(queries),
        )
    assert calls == [] and not (tmp_path / "v").exists()


def test_build_stops_on_a_reply_with_other_source_chunk_ids_and_leaves_no_finished_set(
    tmp_path,
):
    out = tmp_path / "v"
    with pytest.raises(jr.ReferenceRefused, match="Answer grounded on"):
        jr.build(
            "validation",
            out,
            answer=fake_answer(sources=["product-lamp#chunk-0"]),
            **build_inputs(three_queries()),
        )
    assert not out.exists()  # `out` exists only for a finished set
    assert (tmp_path / "v.partial").exists()  # the work so far is kept for a look


def test_build_counts_the_answerable_references_that_decline(tmp_path):
    texts = iter(
        ["I don't know.", "The context does not mention it.", "It holds 300 ml."]
    )

    def answer(question, product_id, chunk_ids):
        return next(texts), list(chunk_ids)

    inputs = build_inputs(three_queries())  # q-2 is answerable: false
    result = jr.build("validation", tmp_path / "v", answer=answer, **inputs)

    # q-1 declines (answerable), q-2 declines but is not answerable, q-3 answers
    assert result["answerable_true"] == 2
    assert result["declines"] == 1
    assert any(
        "1 of 2 answerable:true references decline" in line
        for line in inputs["log"].lines
    )
    assert any(result["index_sha256"] in line for line in inputs["log"].lines)


def test_the_decline_pattern_matches_the_probes_wording():
    for declined in (
        "I don't know.",
        "I do not know the answer.",
        "That is not mentioned in the context.",
        "The text does not specify a size.",
        "The context doesn't contain that.",
    ):
        assert jr.DONT_KNOW.search(declined), declined
    for answered in (
        "Returns are accepted within 30 days.",
        "Yes.",
        "The mug holds 300 ml.",
    ):
        assert not jr.DONT_KNOW.search(answered), answered


def test_build_keeps_a_missing_product_id_as_the_empty_string(tmp_path):
    q = query("q-n", "C", ("policy-return-new",), product_id=None)
    jr.build("validation", tmp_path / "v", answer=fake_answer(), **build_inputs([q]))
    assert read_index(tmp_path / "v")[0]["product_id"] == ""


# =================================================================================================
# The study state a reference set is made in
# =================================================================================================
def test_parse_temperature_reads_the_modelfile_line():
    shown = "top_k   20\ntop_p   0.95\npresence_penalty   1.5\ntemperature                    1"
    assert jr.parse_temperature(shown) == 1.0
    assert jr.parse_temperature("temperature 0.7\ntop_k 20") == 0.7
    assert jr.parse_temperature("top_k 20") is None
    assert jr.parse_temperature("") is None


def fake_http(tags=None, show=None):
    writer = (
        jr.load_writer()
    )  # the pinned reference writer, as `version_block` reads it

    def http(url, body=None, timeout=10.0):
        if url.endswith("/api/tags"):
            return (
                tags
                if tags is not None
                else {
                    "models": [
                        {"name": "qwen3.5:2b-q4_K_M", "digest": "ab" * 32},
                        {"name": writer["model"], "digest": writer["digest"]},
                    ]
                }
            )
        assert url.endswith("/api/show")
        if body == {"model": writer["model"]}:
            return {"parameters": "temperature 1", "capabilities": ["thinking"]}
        assert body == {"model": "qwen3.5:2b-q4_K_M"}
        return show if show is not None else {"parameters": "top_k 20\ntemperature 1"}

    return http


def test_generator_block_reads_the_digest_the_temperature_and_the_prompt_hash():
    from rag import config, generate

    block = jr.generator_block(fake_http())

    assert block == {
        "model": config.LLM_MODEL,
        "digest": "ab" * 32,
        "num_ctx": config.LLM_NUM_CTX,
        "think": config.LLM_THINK,
        "temperature": 1.0,
        "prompt_sha256": sha(generate._PROMPT_TEMPLATE),
    }
    assert list(block)[-1] == "prompt_sha256"


def test_generator_block_prompt_hash_follows_the_prompt_template(monkeypatch):
    from rag import generate

    before = jr.generator_block(fake_http())["prompt_sha256"]
    monkeypatch.setattr(
        generate, "_PROMPT_TEMPLATE", generate._PROMPT_TEMPLATE + " Be brief."
    )

    after = jr.generator_block(fake_http())["prompt_sha256"]

    assert before != after
    assert after == sha(generate._PROMPT_TEMPLATE)


def test_generator_block_refuses_a_generator_that_is_not_pulled():
    with pytest.raises(jr.ReferenceRefused, match="not in /api/tags"):
        jr.generator_block(
            fake_http(tags={"models": [{"name": "other:1b", "digest": "x"}]})
        )


def test_corpus_block_reads_the_freeze_record(tmp_path):
    freeze = tmp_path / "v1-freeze.json"
    freeze.write_text(
        json.dumps({"dataset_version": "v1", "snapshot_digest": "s" * 64, "x": 1})
    )
    assert jr.corpus_block(freeze) == {
        "dataset_version": "v1",
        "snapshot_digest": "s" * 64,
    }


def test_retrieval_block_hashes_the_retrieval_source(tmp_path):
    from rag import config

    source = tmp_path / "retrieve.py"
    source.write_text("def retrieve(): ...\n")

    block = jr.retrieval_block(source)

    assert block == {
        "retrieval_version": config.RETRIEVAL_VERSION,
        "retrieve_py_sha256": sha("def retrieve(): ...\n"),
        "top_k": config.TOP_K,
    }
    assert config.RETRIEVAL_VERSION == "adr-021"


def test_version_block_holds_the_generator_corpus_and_retrieval(tmp_path):
    from rag import generate

    block = jr.version_block(fake_http())

    # the generator's prompt hash lives inside `generator`, not beside it
    assert set(block) == {"generator", "corpus", "retrieval", "reference_writer"}
    assert block["generator"]["prompt_sha256"] == sha(generate._PROMPT_TEMPLATE)
    assert set(block["generator"]) == {
        "model",
        "digest",
        "num_ctx",
        "think",
        "temperature",
        "prompt_sha256",
    }
    assert block["generator"] == jr.generator_block(fake_http())
    assert set(block["corpus"]) == {"dataset_version", "snapshot_digest"}
    assert set(block["retrieval"]) == {
        "retrieval_version",
        "retrieve_py_sha256",
        "top_k",
    }


# =================================================================================================
# ADR-023: the reference writer
# =================================================================================================
def writer_file(tmp_path, **override):
    """A `reference-writer-v1.json` in a temp folder, with the real served prompt's hash."""
    from rag import generate

    writer = {
        "version": "reference-writer-v1",
        "model": "writer-m:4b",
        "digest": "w" * 64,
        "options": {"num_ctx": 8192, "temperature": 0, "seed": 20261101},
        "think": False,
        "prompt_sha256": sha(generate._PROMPT_TEMPLATE),
    }
    writer.update(override)
    path = tmp_path / "reference-writer-v1.json"
    path.write_text(json.dumps(writer))
    return path


def writer_http(digest="w" * 64, capabilities=("completion", "thinking"), calls=None):
    """A fake Ollama that knows `writer-m:4b`; `calls` records every (url, body)."""

    def http(url, body=None, timeout=10.0):
        if calls is not None:
            calls.append((url, body, timeout))
        if url.endswith("/api/tags"):
            return {"models": [{"name": "writer-m:4b", "digest": digest}]}
        if url.endswith("/api/show"):
            return {"capabilities": list(capabilities)}
        assert url.endswith("/api/generate")
        return {"response": "the writer's text"}

    return http


def test_writer_block_refuses_another_live_digest(tmp_path, monkeypatch):
    from rag import generate

    path = writer_file(tmp_path)

    # the live tag has the pinned digest: the block is the file's fields
    block = jr.writer_block(writer_http(), path)
    assert block == {
        "version": "reference-writer-v1",
        "model": "writer-m:4b",
        "digest": "w" * 64,
        "options": {"num_ctx": 8192, "temperature": 0, "seed": 20261101},
        "think": False,
        "prompt_sha256": sha(generate._PROMPT_TEMPLATE),
    }

    # a re-pulled tag: the live digest is no longer the pinned one
    with pytest.raises(jr.ReferenceRefused, match="live digest"):
        jr.writer_block(writer_http(digest="x" * 64), path)

    # the writer is not pulled at all
    nothing = {"models": [{"name": "other:1b", "digest": "x"}]}
    with pytest.raises(jr.ReferenceRefused, match="not in /api/tags"):
        jr.writer_block(lambda url, body=None, timeout=10.0: nothing, path)

    # the served prompt changed under the pinned hash
    monkeypatch.setattr(
        generate, "_PROMPT_TEMPLATE", generate._PROMPT_TEMPLATE + " Be brief."
    )
    with pytest.raises(jr.ReferenceRefused, match="served prompt hashes to"):
        jr.writer_block(writer_http(), path)


def test_answer_with_writer_sends_the_writer_model_and_options(tmp_path, monkeypatch):
    from rag import generate, retrieve

    path = writer_file(tmp_path)
    ids = ["product-mug#chunk-0", "policy-return-new#chunk-1"]
    fetched = []

    def fake_fetch(chunk_ids, dropped=()):
        fetched.append(list(chunk_ids))
        return [
            retrieve.RetrievedChunk(c, 0.0, f"text {c}", "d", 0)
            for c in chunk_ids
            if c not in dropped
        ], 3

    monkeypatch.setattr(retrieve, "fetch_by_ids", fake_fetch)
    calls = []

    text, sources = jr.answer_with_writer(
        "Can I return it?", "product-mug", ids, http=writer_http(calls=calls), path=path
    )

    assert (text, sources) == (
        "the writer's text",
        ids,
    )  # the IDs fetch_by_ids returned
    assert fetched == [ids]
    (_url, body, timeout) = next(c for c in calls if c[0].endswith("/api/generate"))
    expected_chunks = [
        retrieve.RetrievedChunk(c, 0.0, f"text {c}", "d", 0) for c in ids
    ]
    assert body == {
        "model": "writer-m:4b",
        "prompt": generate._build_prompt("Can I return it?", expected_chunks),
        "stream": False,
        "options": {"num_ctx": 8192, "temperature": 0, "seed": 20261101},
        "think": False,  # /api/show lists thinking
    }
    assert timeout == jr.WRITER_TIMEOUT

    # a model that does not list thinking is sent no `think` field
    calls.clear()
    jr.answer_with_writer(
        "q?",
        "",
        ids,
        http=writer_http(capabilities=("completion",), calls=calls),
        path=path,
    )
    sent = next(c[1] for c in calls if c[0].endswith("/api/generate"))
    assert "think" not in sent

    # a chunk fetch_by_ids drops shows in the returned IDs, so make_reference can refuse it
    monkeypatch.setattr(
        retrieve,
        "fetch_by_ids",
        lambda chunk_ids: fake_fetch(chunk_ids, dropped=(ids[0],)),
    )
    _, kept = jr.answer_with_writer("q?", "", ids, http=writer_http(), path=path)
    assert kept == ids[1:]
    with pytest.raises(jr.ReferenceRefused, match="not the 2 gold chunks"):
        jr.make_reference(
            query("q-w", docs=("product-mug",)),
            ids,
            lambda q, p, c: jr.answer_with_writer(
                q, p, c, http=writer_http(), path=path
            ),
        )


def test_version_block_carries_the_reference_writer():
    block = jr.version_block(fake_http())

    writer = jr.load_writer()
    assert block["reference_writer"] == jr.writer_block(fake_http())
    assert block["reference_writer"]["model"] == writer["model"]
    assert block["reference_writer"]["digest"] == writer["digest"]
    assert set(block["reference_writer"]) == {
        "version",
        "model",
        "digest",
        "options",
        "think",
        "prompt_sha256",
    }
    # the writer is not the served generator
    assert block["reference_writer"]["model"] != block["generator"]["model"]


def test_build_defaults_to_the_reference_writer():
    import inspect

    parameters = inspect.signature(jr.build).parameters

    assert parameters["answer"].default is jr.answer_with_writer
    assert parameters["answer"].default is not jr.answer_in_process
    assert parameters["versions"].default is jr.version_block


# =================================================================================================
# DC 8: the sufficiency sheet and its score
# =================================================================================================
def reference_set(tmp_path, n_b_within=12, n_other=25, n_unanswerable=4):
    """An index of reference rows plus their answer files, in a temp folder."""
    refs = tmp_path / "refs"
    (refs / "answers").mkdir(parents=True)
    rows = []
    for i in range(n_b_within + n_other + n_unanswerable):
        stratum = "B-within" if i < n_b_within else "A"
        text = f"reference {i}"
        (refs / "answers" / f"{sha(text)}.txt").write_text(text)
        rows.append(
            {
                "qa_id": f"q-{i:03d}",
                "question": f"Question {i}?",
                "product_id": "product-mug",
                "stratum": stratum,
                "answerable": i < n_b_within + n_other,
                "gold_doc_ids": ["product-mug"],
                "chunk_ids": ["product-mug#chunk-0"],
                "reference_sha256": sha(text),
            }
        )
    (refs / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return refs


def test_sheet_writes_30_pairs_with_at_least_10_b_within(tmp_path):
    refs = reference_set(tmp_path)
    out = tmp_path / "sheet.md"

    jr.sheet("validation", out, refs_dir=refs, corpus=(CHUNKS, TEXTS))

    text = out.read_text()
    assert jr.score(out) == {
        "pairs": 30,
        "b_within": text.count("stratum: B-within"),
        "yes": 0,
        "no": 0,
        "unmarked": 30,
        "other": 0,
        "ref_yes": 0,
        "ref_no": 0,
        "ref_unmarked": 30,
        "ref_other": 0,
    }
    assert text.count("stratum: B-within") >= 10
    assert (
        "text of product-mug#chunk-0" in text and "reference " in text
    )  # gold text and reference


def test_sheet_draws_only_answerable_pairs(tmp_path):
    refs = reference_set(tmp_path, n_b_within=10, n_other=20, n_unanswerable=15)
    out = tmp_path / "sheet.md"
    jr.sheet("validation", out, refs_dir=refs, corpus=(CHUNKS, TEXTS))

    drawn = {
        line.split(". ", 1)[1]
        for line in out.read_text().splitlines()
        if line.startswith("## ")
    }
    unanswerable = {r["qa_id"] for r in read_index(refs) if not r["answerable"]}
    assert len(drawn) == 30 and drawn.isdisjoint(unanswerable)


def test_sheet_is_the_same_for_the_same_seed_and_different_for_another(tmp_path):
    refs = reference_set(tmp_path)
    for name, seed in (("a", 7), ("b", 7), ("c", 8)):
        jr.sheet(
            "validation",
            tmp_path / f"{name}.md",
            seed=seed,
            refs_dir=refs,
            corpus=(CHUNKS, TEXTS),
        )

    assert (tmp_path / "a.md").read_text() == (tmp_path / "b.md").read_text()
    assert (tmp_path / "a.md").read_text() != (tmp_path / "c.md").read_text()


def test_sheet_refuses_a_reference_set_with_too_few_b_within_pairs(tmp_path):
    refs = reference_set(tmp_path, n_b_within=9, n_other=40)
    with pytest.raises(jr.ReferenceRefused, match="9 B-within"):
        jr.sheet("validation", tmp_path / "s.md", refs_dir=refs, corpus=(CHUNKS, TEXTS))
    assert not (tmp_path / "s.md").exists()


def test_sheet_never_overwrites_the_authors_marks(tmp_path):
    refs = reference_set(tmp_path)
    out = tmp_path / "sheet.md"
    out.write_text("sufficient: yes\n")
    with pytest.raises(jr.ReferenceRefused, match="never overwritten"):
        jr.sheet("validation", out, refs_dir=refs, corpus=(CHUNKS, TEXTS))
    assert out.read_text() == "sufficient: yes\n"


def marked(tmp_path, marks, ref_marks=None):
    """A sheet whose pairs are marked with `marks` and `ref_marks` (all `yes` by default), in order."""
    ref_marks = ["yes"] * len(marks) if ref_marks is None else ref_marks
    assert len(ref_marks) == len(marks)
    refs = reference_set(tmp_path)
    out = tmp_path / "sheet.md"
    jr.sheet(
        "validation",
        out,
        n=len(marks),
        min_b_within=1,
        refs_dir=refs,
        corpus=(CHUNKS, TEXTS),
    )
    parts = out.read_text().split("sufficient:\nreference right:\n")
    assert len(parts) == len(marks) + 1
    out.write_text(
        "".join(
            part + f"sufficient: {mark}\nreference right: {ref}\n"
            for part, mark, ref in zip(parts[:-1], marks, ref_marks, strict=True)
        )
        + parts[-1]
    )
    return out


def test_score_counts_yes_no_and_unmarked(tmp_path):
    sheet_file = marked(tmp_path, ["yes", "yes", "no", "", "YES", "maybe"])
    result = jr.score(sheet_file)
    assert (
        result["pairs"],
        result["yes"],
        result["no"],
        result["unmarked"],
        result["other"],
    ) == (
        6,
        3,
        1,
        1,
        1,
    )


def test_score_cli_passes_with_at_most_3_no(tmp_path, capsys):
    sheet_file = marked(tmp_path, ["no", "no", "no"] + ["yes"] * 27)
    assert jr.main(["score", str(sheet_file)]) == 0
    assert "at most 3" in capsys.readouterr().out


def test_score_cli_stops_on_more_than_3_no(tmp_path, capsys):
    sheet_file = marked(tmp_path, ["no"] * 4 + ["yes"] * 26)
    assert jr.main(["score", str(sheet_file)]) == 1
    assert "STOP" in capsys.readouterr().out


def test_score_cli_fails_while_a_pair_is_unmarked(tmp_path, capsys):
    sheet_file = marked(tmp_path, ["yes"] * 29 + [""])
    assert jr.main(["score", str(sheet_file)]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_sheet_writes_a_reference_right_cell_per_pair(tmp_path):
    refs = reference_set(tmp_path)
    out = tmp_path / "sheet.md"
    jr.sheet("validation", out, refs_dir=refs, corpus=(CHUNKS, TEXTS))

    lines = out.read_text().splitlines()
    # one empty cell per pair, right after the `sufficient:` line
    assert lines.count("reference right:") == 30
    assert lines.count("sufficient:") == 30
    for i, line in enumerate(lines):
        if line == "sufficient:":
            assert lines[i + 1] == "reference right:"
    # the header explains the cell before the first pair
    header = "\n".join(
        lines[: next(i for i, x in enumerate(lines) if x.startswith("## "))]
    )
    assert "reference right:" in header and "declines" in header


def test_score_counts_reference_right_marks(tmp_path):
    sheet_file = marked(
        tmp_path,
        ["yes"] * 6,
        ref_marks=["yes", "no", "no", "", "NO", "maybe"],
    )
    result = jr.score(sheet_file)
    assert (
        result["ref_yes"],
        result["ref_no"],
        result["ref_unmarked"],
        result["ref_other"],
    ) == (1, 3, 1, 1)
    # the `sufficient:` counts are read apart from the `reference right:` counts
    assert (result["yes"], result["no"], result["unmarked"], result["other"]) == (
        6,
        0,
        0,
        0,
    )


def test_score_cli_stops_on_more_than_3_wrong_references(tmp_path, capsys):
    sheet_file = marked(tmp_path, ["yes"] * 30, ref_marks=["no"] * 4 + ["yes"] * 26)
    assert jr.main(["score", str(sheet_file)]) == 1
    out = capsys.readouterr().out
    assert "STOP" in out and "reference right: 26 yes, 4 no" in out

    # 3 wrong references pass, as 3 insufficient golds do
    passing = marked(tmp_path / "ok", ["yes"] * 30, ref_marks=["no"] * 3 + ["yes"] * 27)
    assert jr.main(["score", str(passing)]) == 0


def test_score_cli_fails_while_a_reference_cell_is_unmarked(tmp_path, capsys):
    sheet_file = marked(tmp_path, ["yes"] * 30, ref_marks=["yes"] * 29 + [""])
    assert jr.main(["score", str(sheet_file)]) == 1
    assert "FAIL" in capsys.readouterr().out
