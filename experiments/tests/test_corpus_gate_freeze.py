"""Item 3.6, plan steps 5 – 8: the index check, what the report records, the G1 and G2 breakdown,
the retrieval export. Additive to test_corpus_gate.py, which is not touched.

Everything here is synthetic. The ids are made up, the Redis is a fake that answers FT.INFO in the
shape the real one does (captured from the live dev-v0 index), and the Ollama is a stub. The real
index is checked by `make corpus-index-check`, not here.

Each failure of the index check has a test of its own, because each one is a way for the gate to
measure the wrong corpus and look clean doing it.
"""

import json
import math
import struct
import subprocess
from pathlib import Path

import corpus_gate as g
import pytest
from redis.exceptions import ResponseError

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIGEST = "a" * 64
DIM = 768


# =================================================================================================
# A synthetic corpus and a fake Redis that holds it
# =================================================================================================
def _write_corpus(directory: Path, policy_text: str | None = None) -> Path:
    directory.mkdir(exist_ok=True)
    product = {
        "doc_id": "product-phones-x1",
        "title": "Test Phone",
        "category": "phones",
        "specs": {"weight": "170 g"},
    }
    policy = {
        "doc_id": "policy-return-electronics",
        "title": "Returns",
        "category": "electronics",
        "policy_kind": "return",
        "condition": None,
        "text": policy_text
        or " ".join(f"Item {i} may be returned within thirty days." for i in range(80)),
    }
    for record in (product, policy):
        (directory / f"{record['doc_id']}.json").write_text(json.dumps(record))
    return directory


def _vector(seed: int) -> bytes:
    return struct.pack(f"<{DIM}f", *[(seed + i) % 7 / 7 for i in range(DIM)])


class FakeRedis:
    """Answers the three calls `read_index` makes, in the shape redis-py returns them."""

    def __init__(self, chunks: dict[str, str], version: str = "v1"):
        self.rows = [
            {
                "chunk_id": cid,
                "text": text,
                "dataset_version": version,
                "vector": _vector(n),
            }
            for n, (cid, text) in enumerate(sorted(chunks.items()))
        ]
        self.info = {
            "num_docs": len(self.rows),
            "hash_indexing_failures": 0,
            "indexing": 0,
            "percent_indexed": b"1",
        }
        self.vector_attr = [
            "algorithm",
            "FLAT",
            "data_type",
            "FLOAT32",
            "dim",
            DIM,
            "distance_metric",
            "COSINE",
        ]
        self.missing_index = False

    def execute_command(self, *args):
        assert args[0] == "FT.INFO"
        if self.missing_index:
            raise ResponseError("Unknown index name")
        vector = [b"identifier", b"vector", b"attribute", b"vector", b"type", b"VECTOR"]
        for cell in self.vector_attr:
            vector.append(cell if isinstance(cell, int) else cell.encode())
        flat = [b"index_name", b"idx:corpus"]
        for key, value in self.info.items():
            flat += [key.encode(), value]
        flat += [
            b"attributes",
            [[b"identifier", b"id", b"attribute", b"id", b"type", b"TAG"], vector],
        ]
        return flat

    def scan_iter(self, match):
        assert match.startswith("corpus:")
        yield from (f"corpus::{n}".encode() for n in range(len(self.rows)))

    def hmget(self, key, fields):
        row = self.rows[int(key.decode().rsplit("::", 1)[1])]
        return [row[f].encode() if isinstance(row[f], str) else row[f] for f in fields]


class Ollama:
    """A stub for `ollama_get` that records the paths asked, so a test can see no model is run."""

    def __init__(self, models=None, version="0.33.2", down=False):
        self.models = (
            models
            if models is not None
            else [
                {"name": "nomic-embed-text:latest", "digest": MODEL_DIGEST},
                {"name": "qwen3.5:2b-q4_K_M", "digest": "b" * 64},
            ]
        )
        self.version, self.down, self.paths = version, down, []

    def __call__(self, base_url, path):
        import httpx

        self.paths.append(path)
        if self.down:
            raise httpx.ConnectError("refused")
        return (
            {"models": self.models}
            if path == "/api/tags"
            else {"version": self.version}
        )


@pytest.fixture
def world(tmp_path, monkeypatch):
    corpus = _write_corpus(tmp_path / "corpus")
    expected = g.offline_chunks(corpus, "v1")
    ollama = Ollama()
    monkeypatch.setattr(g, "ollama_get", ollama)
    return corpus, expected, FakeRedis(expected), ollama


def _check(world, **kw):
    corpus, _, client, _ = world
    return g.index_check(client, corpus, "v1", "http://ollama", **kw)


def _assert_counts_not_ids(failures, expected):
    """A message that names an id would put an asin on a terminal."""
    text = " ".join(failures)
    for chunk_id in expected:
        assert chunk_id not in text
        assert chunk_id.split("#")[0] not in text


# =================================================================================================
# Step 5 -- the chunk digest and the index check
# =================================================================================================
def test_the_chunk_digest_is_the_digest_of_ingests_own_chunks(tmp_path):
    corpus = _write_corpus(tmp_path / "corpus")
    digest, count = g.chunk_digest(corpus, "v1")
    chunks = g.offline_chunks(corpus, "v1")
    assert (digest, count) == (g.text_digest(chunks), len(chunks))
    assert count > 2  # the policy really split


def test_the_chunk_digest_moves_with_a_text_and_a_file_but_not_the_version_tag(
    tmp_path,
):
    corpus = _write_corpus(tmp_path / "corpus")
    base, _ = g.chunk_digest(corpus, "v1")
    assert (
        g.chunk_digest(corpus, "dev-v0")[0] == base
    )  # the tag is metadata, not chunk text
    edited = _write_corpus(
        tmp_path / "edited", policy_text="Items go back within 14 days."
    )
    assert g.chunk_digest(edited, "v1")[0] != base
    (corpus / "product-phones-x2.json").write_text(
        json.dumps(
            {"doc_id": "product-phones-x2", "title": "T", "category": "c", "specs": {}}
        )
    )
    assert g.chunk_digest(corpus, "v1")[0] != base


def test_a_matching_index_passes_and_returns_what_it_measured(world):
    _, expected, client, _ = world
    result = _check(world)
    assert result.passed, result.failures
    assert result.chunk_count == len(expected)
    assert result.chunk_digest == g.text_digest(expected)
    assert result.stored_vector_digest == g.vector_digest(
        {r["chunk_id"]: r["vector"] for r in client.rows}
    )
    assert (result.model_tag, result.model_digest) == ("nomic-embed-text", MODEL_DIGEST)
    assert result.ollama_version == "0.33.2"
    assert (
        result.vector_field["algorithm"] == "FLAT"
        and result.vector_field["dim"] == "768"
    )


def test_the_index_check_loads_no_model(world):
    """It reads Ollama's tag list and version, and nothing else."""
    _check(world)
    assert sorted(world[3].paths) == ["/api/tags", "/api/version"]


def _wrong_version(w):
    for row in w[2].rows:
        row["dataset_version"] = "dev-v0"


def _one_chunk_missing(w):
    w[2].rows.pop()
    w[2].info["num_docs"] -= 1


def _one_chunk_missing_but_counted(w):
    w[2].rows.pop()  # the index still counts it


def _a_changed_text(w):
    w[2].rows[0]["text"] += " (edited)"


def _a_stray_hash(w):
    w[2].rows.append({**w[2].rows[0], "chunk_id": "product-strayx#chunk-0"})


def _a_duplicate_id(w):
    w[2].rows[1]["chunk_id"] = w[2].rows[0]["chunk_id"]


def _indexing_failures(w):
    w[2].info["hash_indexing_failures"] = 2


def _still_indexing(w):
    w[2].info["indexing"] = 1
    w[2].info["percent_indexed"] = b"0.5"


def _hnsw(w):
    w[2].vector_attr[1] = "HNSW"


def _wrong_dim(w):
    w[2].vector_attr[5] = 384


def _wrong_metric(w):
    w[2].vector_attr[7] = "L2"


def _short_vector(w):
    w[2].rows[0]["vector"] = w[2].rows[0]["vector"][:-4]


def _no_index(w):
    w[2].missing_index = True


@pytest.mark.parametrize(
    "break_it,test_number",
    [
        (_wrong_version, "test 2"),
        (_one_chunk_missing, "test 1"),
        (_one_chunk_missing, "test 3"),
        (_one_chunk_missing_but_counted, "test 2"),
        (_one_chunk_missing_but_counted, "test 3"),
        (_a_changed_text, "test 3"),
        (_a_stray_hash, "test 2"),
        (_a_duplicate_id, "test 2"),
        (_indexing_failures, "test 1"),
        (_still_indexing, "test 1"),
        (_hnsw, "test 1"),
        (_wrong_dim, "test 1"),
        (_wrong_metric, "test 1"),
        (_short_vector, "test 4"),
        (_no_index, "test 1"),
    ],
)
def test_each_way_the_index_can_be_wrong_fails_and_names_its_test(
    world, break_it, test_number
):
    break_it(world)
    result = _check(world)
    assert not result.passed
    assert any(f.startswith(test_number) for f in result.failures), result.failures
    _assert_counts_not_ids(result.failures, world[1])


def test_an_index_that_still_holds_dev_v0_fails_a_v1_check(world, tmp_path):
    """Acceptance A4, and the state this item leaves Redis in afterwards (item 3.6 design)."""
    other = _write_corpus(
        tmp_path / "devv0", policy_text="Returns are accepted for 10 days."
    )
    stale = FakeRedis(g.offline_chunks(other, "dev-v0"), version="dev-v0")
    result = g.index_check(stale, world[0], "v1", "http://ollama")
    assert not result.passed
    joined = " ".join(result.failures)
    assert "test 2" in joined and "test 3" in joined and "'v1'" in joined


def test_a_changed_stored_vector_fails_against_the_recorded_digest(world):
    first = _check(world)
    assert first.passed
    world[2].rows[3]["vector"] = _vector(999)
    after = _check(world, recorded_vector_digest=first.stored_vector_digest)
    assert [f for f in after.failures if f.startswith("test 4")]
    assert _check(
        world
    ).passed  # with nothing recorded, the vectors are measured, not compared


def test_a_moved_embedding_model_fails_against_the_recorded_digest(world):
    first = _check(world)
    world[3].models[0]["digest"] = "c" * 64
    after = _check(world, recorded_model_digest=first.model_digest)
    assert [f for f in after.failures if f.startswith("test 5")]


def test_a_model_that_is_not_installed_fails(world):
    world[3].models[:] = [
        m for m in world[3].models if not m["name"].startswith("nomic")
    ]
    assert [f for f in _check(world).failures if f.startswith("test 5")]


def test_an_ollama_that_is_down_fails_test_5_and_keeps_the_other_results(world):
    world[3].down = True
    result = _check(world)
    assert [f for f in result.failures if f.startswith("test 5")]
    assert result.stored_vector_digest  # tests 1 – 4 still ran


def test_read_index_decodes_the_real_reply_shape(world):
    state = g.read_index(world[2], "idx:corpus", "corpus:")
    assert (state.num_docs, state.hash_indexing_failures, state.indexing) == (
        len(world[1]),
        0,
        0,
    )
    assert state.percent_indexed == 1.0
    assert (
        state.vector_field["algorithm"] == "FLAT" and state.vector_field["dim"] == "768"
    )
    assert len(state.rows) == len(world[1])


# =================================================================================================
# Step 6 -- what the report records
# =================================================================================================
def _completed(stdout):
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")


@pytest.mark.parametrize(
    "stdout,want", [("0\n", 0), ("1\n", 1), ("2\n", 2), ("n/a\n", None)]
)
def test_memory_pressure_is_read_from_sysctl(monkeypatch, stdout, want):
    calls = []
    monkeypatch.setattr(
        g.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or _completed(stdout)
    )
    assert g.memory_pressure_level() == want
    assert calls == [["sysctl", "-n", "kern.memorystatus_vm_pressure_level"]]


def test_memory_pressure_that_cannot_be_read_is_none_not_green(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError("sysctl")

    monkeypatch.setattr(g.subprocess, "run", boom)
    assert g.memory_pressure_level() is None


def _git(repo, *args):
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    for d in ("rag/src", "experiments/scripts", "docs"):
        (root / d).mkdir(parents=True)
    (root / "rag/src/a.py").write_text("x = 1\n")
    (root / "experiments/scripts/b.py").write_text("y = 1\n")
    (root / "Makefile").write_text("all:\n")
    (root / "docs/n.md").write_text("n\n")
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "x")
    return root


def test_git_state_is_clean_on_a_committed_tree(repo):
    state = g.git_state(repo)
    assert state["tree_clean"] and len(state["commit"]) == 40


@pytest.mark.parametrize(
    "path", ["rag/src/a.py", "experiments/scripts/b.py", "Makefile"]
)
def test_a_change_to_the_measuring_code_makes_the_tree_dirty(repo, path):
    (repo / path).write_text("changed\n")
    assert not g.git_state(repo)["tree_clean"]


def test_an_untracked_file_in_the_measuring_code_makes_the_tree_dirty(repo):
    (repo / "experiments/scripts/new.py").write_text("z = 1\n")
    assert not g.git_state(repo)["tree_clean"]


def test_a_change_outside_the_measuring_code_does_not(repo):
    (repo / "docs/n.md").write_text("edited\n")
    assert g.git_state(repo)["tree_clean"]


def test_git_state_outside_a_repository_is_not_clean(tmp_path):
    state = g.git_state(tmp_path)
    assert state["commit"] is None and not state["tree_clean"]


def test_package_versions_report_an_absent_package_as_none():
    versions = g.package_versions(("pytest", "no-such-package-xyz"))
    assert versions["pytest"] and versions["no-such-package-xyz"] is None
    assert set(g.package_versions()) == {
        "llama-index-core",
        "tiktoken",
        "nltk",
        "llama-index-vector-stores-redis",
        "redisvl",
    }


def _q(qa_id, product_id="", retrieved=(), **kw):
    return g.Query(qa_id, "?", product_id=product_id, retrieved=tuple(retrieved), **kw)


def test_grounding_counts_a_query_that_retrieved_nothing_and_one_without_its_own_chunk():
    queries = [
        _q("a", "product-phones-x1", ["product-phones-x1#chunk-0", "policy-r#chunk-0"]),
        _q("b", "product-phones-x1", ["policy-r#chunk-0"]),  # no chunk of its product
        _q(
            "c", "", ["policy-r#chunk-0"]
        ),  # a policy question: no product, so nothing to miss
        _q("d", "", []),  # retrieved nothing
        _q("e", "product-phones-x1", []),  # nothing, and so no own chunk either
    ]
    assert g.grounding_counts(queries) == {"ungrounded": 2, "own_chunk_missing": 2}


def test_a_product_id_is_matched_by_document_not_by_prefix():
    """product-phones-x1 must not match a chunk of product-phones-x10."""
    q = _q("a", "product-phones-x1", ["product-phones-x10#chunk-0"])
    assert g.grounding_counts([q])["own_chunk_missing"] == 1


# =================================================================================================
# Step 7 -- who made each counted pair
# =================================================================================================
def _pair(a, b, label="B-within"):
    return g.Pair(a.qa_id, b.qa_id, 0.9, 0.0, label)


def _two(**kw):
    a = g.Query("a", "x", doc_ids=("policy-r",), cluster_id="c1", **kw.get("a", {}))
    b = g.Query("b", "y", doc_ids=("policy-r",), cluster_id="c2", **kw.get("b", {}))
    return a, b


def test_pair_type_knows_a_built_trap_in_either_direction():
    a, b = _two(b={"pair_of": "a"})
    assert g.pair_type(a, b) == "pair_of" and g.pair_type(b, a) == "pair_of"


def test_pair_type_knows_a_paraphrase_and_everything_else():
    a, b = _two()
    assert g.pair_type(a, b) == "other"
    b.cluster_id = "c1"
    assert g.pair_type(a, b) == "same_cluster"


def test_pair_type_does_not_treat_two_empty_clusters_as_one():
    a, b = _two()
    a.cluster_id = b.cluster_id = ""
    assert g.pair_type(a, b) == "other"


def test_a_built_trap_wins_over_a_shared_cluster():
    a, b = _two(b={"pair_of": "a"})
    b.cluster_id = a.cluster_id
    assert g.pair_type(a, b) == "pair_of"


def test_docs_relation_compares_the_document_sets_not_their_order():
    a, b = _two()
    assert g.docs_relation(a, b) == "same_docs"
    a.doc_ids, b.doc_ids = ("policy-r", "product-x"), ("product-x", "policy-r")
    assert g.docs_relation(a, b) == "same_docs"
    b.doc_ids = ("policy-s",)
    assert g.docs_relation(a, b) == "different_docs"


def test_the_breakdown_has_every_cell_and_counts_each_pair_once():
    a, b = _two(b={"pair_of": "a"})
    c = g.Query("c", "z", doc_ids=("policy-s",), cluster_id="c1")
    by_id = {q.qa_id: q for q in (a, b, c)}
    table = g.pair_breakdown([_pair(a, b), _pair(a, c)], by_id)
    assert set(table) == set(g.PAIR_TYPES)
    assert all(set(row) == set(g.DOC_RELATIONS) for row in table.values())
    assert table["pair_of"] == {"same_docs": 1, "different_docs": 0}
    assert table["same_cluster"] == {"same_docs": 0, "different_docs": 1}
    assert table["other"] == {"same_docs": 0, "different_docs": 0}
    assert sum(sum(row.values()) for row in table.values()) == 2


def test_s5_is_raised_when_g2_is_met_only_by_paraphrases():
    a, b = _two()
    b.cluster_id = "c1"
    assert g.paraphrase_only([_pair(a, b)], {"a": a, "b": b})


def test_s5_is_not_raised_when_a_built_trap_meets_g2():
    a, b = _two(b={"pair_of": "a"})
    c = g.Query("c", "z", doc_ids=("policy-r",), cluster_id="c1")
    by_id = {q.qa_id: q for q in (a, b, c)}
    assert not g.paraphrase_only([_pair(a, c), _pair(a, b)], by_id)


def test_s5_is_not_raised_by_a_natural_pair_between_different_clusters():
    a, b = _two()
    assert not g.paraphrase_only([_pair(a, b)], {"a": a, "b": b})


def test_s5_ignores_pairs_that_are_not_b_within_and_needs_a_g2_to_raise():
    a, b = _two()
    b.cluster_id = "c1"
    by_id = {"a": a, "b": b}
    assert not g.paraphrase_only([_pair(a, b, "B-cross")], by_id)
    assert not g.paraphrase_only([], by_id)


def test_the_breakdown_leaves_g1_and_g2_as_defined():
    """It reads the pairs and changes nothing: the pass or fail of G1 and G2 is the same after."""
    a, b = _two()
    pairs = [_pair(a, b)]
    before = (g.check_g1(pairs), g.check_g2(pairs, scope="validation"), list(pairs))
    g.pair_breakdown(pairs, {"a": a, "b": b})
    g.paraphrase_only(pairs, {"a": a, "b": b})
    after = (g.check_g1(pairs), g.check_g2(pairs, scope="validation"), list(pairs))
    assert before == after
    assert (
        after[1].summary == "B-within=1  B-cross=0  ratio=n/a  unlabelled=0"
        and after[1].passed
    )
    assert not after[0].passed  # one pair is not 50


# =================================================================================================
# Step 8 -- the export, and the comparison with 3.4's vectors
# =================================================================================================
def _exportable():
    return [
        g.Query(
            "v1",
            "How heavy is it?",
            split="validation",
            embedding=[0.1, 0.2],
            retrieved=("c1", "c2"),
            retrieved_unscoped=("c1", "c3", "c4"),
        ),
        g.Query(
            "t1",
            "How long is the warranty?",
            split="test",
            embedding=[0.3, 0.4],
            retrieved=(),
            retrieved_unscoped=("c9",),
        ),
        g.Query(
            "v2",
            "What does it weigh?",
            split="validation",
            embedding=[0.1, 0.2],
            retrieved=("c1",),
            retrieved_unscoped=("c1",),
        ),
    ]


def test_the_export_writes_one_file_per_split_in_workload_order(tmp_path):
    written = g.write_retrieval_export(tmp_path / "out", _exportable())
    assert [p.name for p in written] == [
        "retrieval-validation.json",
        "retrieval-test.json",
    ]
    validation = json.loads(written[0].read_text())
    assert [r["qa_id"] for r in validation] == ["v1", "v2"]
    assert validation[0]["scoped"] == ["c1", "c2"] and validation[0]["unscoped"] == [
        "c1",
        "c3",
        "c4",
    ]
    assert (validation[0]["n_scoped"], validation[0]["n_unscoped"]) == (2, 3)
    assert json.loads(written[1].read_text())[0]["n_scoped"] == 0


def test_the_export_holds_no_question_text(tmp_path):
    for path in g.write_retrieval_export(tmp_path / "out", _exportable()):
        body = path.read_text()
        assert "heavy" not in body and "warranty" not in body and "question" not in body


def test_two_queries_with_one_vector_share_a_hash_and_a_one_ulp_change_moves_it(
    tmp_path,
):
    rows = json.loads(g.write_retrieval_export(tmp_path, _exportable())[0].read_text())
    assert rows[0]["vector_sha256"] == rows[1]["vector_sha256"]
    assert g.vector_sha256([0.1, 0.2]) != g.vector_sha256(
        [0.1, math.nextafter(0.2, 1.0)]
    )


def test_the_export_is_refused_where_git_does_not_ignore_it():
    with pytest.raises(SystemExit, match="not gitignored"):
        g.require_git_ignored(REPO_ROOT / "experiments" / "retrieval-validation.json")


def test_the_export_is_accepted_under_data_v1_draft_and_outside_the_repo(tmp_path):
    g.require_git_ignored(
        REPO_ROOT / "data" / "v1-draft" / "gate" / "run1" / "retrieval-test.json"
    )
    g.require_git_ignored(tmp_path / "retrieval-test.json")


def test_write_retrieval_export_refuses_a_tracked_path_before_writing(monkeypatch):
    target = REPO_ROOT / "experiments" / "_never_written"
    with pytest.raises(SystemExit, match="not gitignored"):
        g.write_retrieval_export(target, _exportable())
    assert not target.exists()


def _vectors_file(tmp_path, qs):
    path = tmp_path / "vectors.json"
    path.write_text(
        json.dumps(
            {q.qa_id: {"question": q.question, "vector": q.embedding} for q in qs}
        )
    )
    return path


def test_compare_vectors_counts_a_difference_and_its_size(tmp_path):
    queries = _exportable()
    path = _vectors_file(tmp_path, queries)
    assert g.compare_vectors(queries, path) == {
        "compared": 3,
        "missing": 0,
        "differing": 0,
        "max_abs_diff": 0.0,
    }
    queries[1].embedding = [0.3, 0.4 + 1e-9]
    result = g.compare_vectors(queries, path)
    assert result["differing"] == 1 and 0 < result["max_abs_diff"] < 2e-9


def test_compare_vectors_counts_a_query_the_file_does_not_hold(tmp_path):
    queries = _exportable()
    path = _vectors_file(tmp_path, queries[:2])
    assert g.compare_vectors(queries, path)["missing"] == 1


# =================================================================================================
# main(): the new pieces wired in, end to end, against fakes
# =================================================================================================
def _workload(directory):
    def rec(qa_id, question, split, rank, stratum="A", cluster="c1", pair_of=None):
        return {
            "qa_id": qa_id,
            "question": question,
            "doc_ids": ["product-phones-x1"],
            "product_id": "product-phones-x1",
            "stratum": stratum,
            "split": split,
            "cluster_id": cluster,
            "pair_of": pair_of,
            "probe_kind": None,
            "popularity_rank": rank,
        }

    records = [
        rec("v1", "How heavy is the Test Phone?", "validation", 1),
        rec("v2", "What does the Test Phone weigh?", "validation", 2),
        rec(
            "t1",
            "How long is the battery life of the Test Phone?",
            "test",
            1,
            "C",
            "c2",
        ),
        rec(
            "t2",
            "Does the Test Phone have a headphone jack?",
            "test",
            2,
            "B-within",
            "c3",
            "t1",
        ),
    ]
    whole = directory / "workload-v1.json"
    whole.write_text(json.dumps(records))
    for s in g.SPLITS:
        g.split_path(whole, s).write_text(json.dumps(g.derive_split(records, s)))
    return whole


@pytest.fixture
def full_run(tmp_path, monkeypatch, world, capsys):
    """`main()` through stage 2 with the index, the embedder, both retrievers, the memory reading
    and git all faked. G1 cannot reach 50 pairs on four queries, so the gate FAILS and the report is
    still written: that is what a failed real run looks like."""
    import rag.embedding
    import rag.retrieve
    import rag.store

    corpus, expected, client, _ = world
    whole = _workload(tmp_path)
    ids = sorted(expected)

    class Embedder:
        def get_query_embedding(self, text):
            return [1.0, float(len(text) % 5), 0.0]

    monkeypatch.setattr(rag.embedding, "OllamaEmbedding", Embedder)
    monkeypatch.setattr(rag.store, "get_redis_client", lambda: client)
    monkeypatch.setattr(
        rag.retrieve,
        "make_retriever",
        lambda: lambda text: [type("C", (), {"chunk_id": c})() for c in ids[:3]],
    )
    own = "product-phones-x1#chunk-0"
    monkeypatch.setattr(
        rag.retrieve,
        "retrieve",
        lambda text, product_id=None: (
            [type("C", (), {"chunk_id": c})() for c in (own, ids[0])],
            0,
        ),
    )
    readings = iter([1] * 100)
    monkeypatch.setattr(g, "memory_pressure_level", lambda: next(readings))
    monkeypatch.setattr(
        g,
        "git_state",
        lambda *a, **k: {
            "commit": "f" * 40,
            "tree_clean": True,
            "paths": list(g.GIT_PATHS),
        },
    )
    vectors = tmp_path / "vectors.json"
    vectors.write_text("{}")
    out = tmp_path / "out"
    report = tmp_path / "report.json"

    def run(*extra):
        monkeypatch.setattr(
            "sys.argv",
            [
                "corpus_gate.py",
                "--corpus-dir",
                str(corpus),
                "--workload",
                str(whole),
                "--report",
                str(report),
                "--retrieval-out",
                str(out),
                "--vectors",
                str(vectors),
                *extra,
            ],
        )
        code = g.main()
        return code, capsys.readouterr().out

    return run, report, out, corpus, client


def test_main_runs_the_index_check_then_writes_the_new_report_keys(full_run):
    run, report, out, _, _ = full_run
    code, text = run()
    assert code == 1  # four queries cannot make 50 pairs: G1 fails, as it should
    assert "[PASS] I   the index is the corpus" in text and "[FAIL] G1" in text
    data = json.loads(report.read_text())
    assert data["passed"] is False and data["snapshot_digest"] is None
    for key in (
        "git",
        "embedding",
        "retrieval",
        "splitter",
        "packages",
        "chunk_digest",
        "chunk_count",
        "stored_vector_digest",
        "index_check",
        "grounding",
        "memory_pressure",
        "stage2_seconds",
        "query_vectors_vs_file",
    ):
        assert key in data, key
    assert data["git"] == {
        "commit": "f" * 40,
        "tree_clean": True,
        "paths": list(g.GIT_PATHS),
    }
    assert data["embedding"] == {
        "tag": "nomic-embed-text",
        "digest": MODEL_DIGEST,
        "ollama_version": "0.33.2",
    }
    assert data["retrieval"] == {
        "top_k": 5,
        "index": "FLAT",
        "metric": "COSINE",
        "dim": 768,
        "data_type": "FLOAT32",
    }
    assert data["splitter"] == {"chunk_size": 256, "chunk_overlap": 40}
    assert data["memory_pressure"]["readings"] and set(
        data["memory_pressure"]["readings"]
    ) == {1}
    assert data["grounding"] == {"ungrounded": 0, "own_chunk_missing": 0}
    assert data["query_vectors_vs_file"]["missing"] == 4
    stats = data["statistics"]
    assert set(stats["pair_breakdown"]) == {"g1", "g2"} and set(stats["s5"]) == {
        "validation",
        "test",
    }
    assert "low_overlap_pairs" in stats
    assert sorted(p.name for p in out.iterdir()) == [
        "retrieval-test.json",
        "retrieval-validation.json",
    ]


def test_main_keeps_every_report_key_it_had_before(full_run):
    run, report, *_ = full_run
    run()
    data = json.loads(report.read_text())
    for key in (
        "dataset",
        "workload",
        "passed",
        "snapshot_digest",
        "files",
        "criteria",
        "statistics",
    ):
        assert key in data
    for key in (
        "g1_pairs_within_split",
        "g1_pairs_across_splits",
        "b_within",
        "b_cross",
        "b_unlabelled",
        "unscoped",
        "benign_duplicate_groups",
        "high_sim_pairs",
        "overlap_mean",
        "overlap_variance",
        "strata",
        "trap_fraction",
        "run_files",
        "g5_split_families",
        "g5_offending_documents",
    ):
        assert key in data["statistics"], key


def test_main_stops_before_any_embedding_when_the_index_is_not_the_corpus(
    full_run, monkeypatch
):
    import rag.embedding

    run, report, out, _, client = full_run
    client.rows[0]["text"] += " (edited)"

    def never(*a, **k):
        raise AssertionError(
            "the embedding model was constructed after a failed index check"
        )

    monkeypatch.setattr(rag.embedding, "OllamaEmbedding", never)
    code, text = run()
    assert code == 1
    assert "[FAIL] I   test 3" in text and "precondition, not S1" in text
    assert not report.exists() and not out.exists()


def test_main_prints_counts_and_no_qa_id_when_a_query_retrieves_nothing(
    full_run, monkeypatch
):
    import rag.retrieve

    run, *_ = full_run
    monkeypatch.setattr(rag.retrieve, "retrieve", lambda text, product_id=None: ([], 0))
    _, text = run()
    assert "S4 — 4 quer(y|ies) retrieved NOTHING and 4 lack a chunk" in text
    for qa_id in ("v1", "v2", "t1", "t2"):
        assert f"'{qa_id}'" not in text


def test_main_flags_a_yellow_reading_and_the_report_keeps_it(full_run, monkeypatch):
    run, report, *_ = full_run
    readings = iter([1, 1, 2] + [1] * 100)
    monkeypatch.setattr(g, "memory_pressure_level", lambda: next(readings))
    _, text = run()
    assert "S3 — memory pressure was not green" in text
    assert 2 in json.loads(report.read_text())["memory_pressure"]["readings"]


def test_main_refuses_an_export_path_git_does_not_ignore_before_doing_any_work(
    full_run, monkeypatch
):
    import rag.embedding

    run, *_ = full_run
    monkeypatch.setattr(
        rag.embedding, "OllamaEmbedding", lambda: pytest.fail("work was started")
    )
    with pytest.raises(SystemExit, match="not gitignored"):
        run("--retrieval-out", str(REPO_ROOT / "experiments" / "_nope"))


# =================================================================================================
# /ai-review, item 3.6: a run the criteria pass can still be a run that must not be frozen
# =================================================================================================
def _criteria_all_green(monkeypatch):
    """The four-query fixture cannot make 50 pairs, so G1 and G2 are forced green. The control test
    below proves the pass branch is reached; without it the flagged-run tests could prove nothing."""
    monkeypatch.setattr(
        g, "check_g1", lambda pairs, scope="": g.Criterion("G1  forced", True, "forced")
    )
    monkeypatch.setattr(
        g,
        "check_g2",
        lambda pairs, scope="": g.Criterion(f"G2  forced ({scope})", True, "forced"),
    )


def test_control_a_green_run_that_passes_every_criterion_prints_the_digest(
    full_run, monkeypatch
):
    run, report, *_ = full_run
    _criteria_all_green(monkeypatch)
    code, text = run()
    data = json.loads(report.read_text())
    assert code == 0 and "--- FREEZE ---" in text and "NOT FROZEN" not in text
    assert data["passed"] is True and data["flags"] == []
    assert len(data["snapshot_digest"]) == 64


def test_a_yellow_reading_stops_a_run_the_criteria_pass(full_run, monkeypatch):
    run, report, *_ = full_run
    _criteria_all_green(monkeypatch)
    readings = iter([1, 1, 2] + [1] * 100)
    monkeypatch.setattr(g, "memory_pressure_level", lambda: next(readings))
    code, text = run()
    data = json.loads(report.read_text())
    assert code != 0 and "--- FREEZE ---" not in text
    assert "the five criteria pass, but this run is flagged" in text
    assert data["passed"] is False and data["snapshot_digest"] is None
    assert data["flags"] == ["S3 memory pressure was not green"]


def test_an_ungrounded_query_stops_a_run_the_criteria_pass(full_run, monkeypatch):
    import rag.retrieve

    run, report, *_ = full_run
    _criteria_all_green(monkeypatch)
    monkeypatch.setattr(rag.retrieve, "retrieve", lambda text, product_id=None: ([], 0))
    code, text = run()
    data = json.loads(report.read_text())
    assert code != 0 and "--- FREEZE ---" not in text
    assert data["passed"] is False and data["snapshot_digest"] is None
    assert "S4" in [f[:2] for f in data["flags"]]


def test_main_refuses_a_report_path_git_does_not_ignore_before_doing_any_work(
    full_run, monkeypatch
):
    import rag.embedding

    run, *_ = full_run
    monkeypatch.setattr(
        rag.embedding, "OllamaEmbedding", lambda: pytest.fail("work was started")
    )
    with pytest.raises(SystemExit, match="not gitignored"):
        run("--report", str(REPO_ROOT / "experiments" / "_nope.json"))


# =================================================================================================
# ADR-014, Block A0: on macOS 1 is the normal (green) pressure level, 2 is warn and 4 is critical
# =================================================================================================
def test_the_green_level_is_one_and_the_names_are_the_sdks():
    assert g.GREEN_LEVEL == 1
    assert g.PRESSURE_NAMES == {1: "normal", 2: "warn", 4: "critical"}


def test_normal_readings_raise_no_s3_flag_and_the_run_passes(full_run, monkeypatch):
    run, report, *_ = full_run
    _criteria_all_green(monkeypatch)
    readings = iter([g.GREEN_LEVEL] * 100)
    monkeypatch.setattr(g, "memory_pressure_level", lambda: next(readings))
    code, text = run()
    data = json.loads(report.read_text())
    assert "S3" not in text and data["flags"] == []
    assert code == 0 and data["passed"] is True and "--- FREEZE ---" in text


@pytest.mark.parametrize(
    "bad,words",
    [(2, "warn"), (4, "critical"), (None, "could not be read"), (0, "0")],
)
def test_any_reading_but_one_raises_s3_and_the_message_names_it(
    full_run, monkeypatch, bad, words
):
    run, report, *_ = full_run
    _criteria_all_green(monkeypatch)
    readings = iter([1, 1, bad] + [1] * 100)
    monkeypatch.setattr(g, "memory_pressure_level", lambda: next(readings))
    code, text = run()
    data = json.loads(report.read_text())
    assert code != 0 and "--- FREEZE ---" not in text
    assert "S3 — memory pressure was not green" in text and words in text
    assert data["flags"] == ["S3 memory pressure was not green"]
    assert data["passed"] is False and data["snapshot_digest"] is None


# =================================================================================================
# ADR-014, Block A: `--accept-failed G1` -- a pinned, opt-in allowance, and the reachable traps
# =================================================================================================
PIN = "d" * 64


def _g1_fails_the_rest_pass(monkeypatch, g2_passes=True):
    monkeypatch.setattr(
        g,
        "check_g1",
        lambda pairs, scope="": g.Criterion("G1  forced", False, "forced"),
    )
    monkeypatch.setattr(
        g,
        "check_g2",
        lambda pairs, scope="": g.Criterion(
            f"G2  forced ({scope})", g2_passes, "forced"
        ),
    )


def _pin(monkeypatch, value=PIN):
    """The fixture's files cannot hash to the real pin, so the digest and the pin are both set."""
    monkeypatch.setattr(g, "ACCEPTED_SNAPSHOT_DIGEST", PIN)
    monkeypatch.setattr(
        g, "snapshot_digest", lambda paths: (value, [("f.json", "0" * 64)])
    )


def _not_honoured(full_run, text_has):
    run, report, *_ = full_run
    code, text = run("--accept-failed", "G1")
    data = json.loads(report.read_text())
    assert code == 1 and "FREEZE WITH A RECORDED FAILURE" not in text
    assert data["passed"] is False and data["freezable"] is False
    assert data["accepted_failures"] == [] and data["snapshot_digest"] is None
    assert "--accept-failed G1 was given but not honoured" in text and text_has in text


def test_the_pin_is_the_digest_run_1_printed():
    assert len(g.ACCEPTED_SNAPSHOT_DIGEST) == 64
    assert g.ACCEPTED_SNAPSHOT_DIGEST.startswith("a5708fefa62c")
    assert (g.ACCEPTABLE_FAILURES, g.ACCEPTABLE_VERSION, g.FINDING_ADR) == (
        ("G1",),
        "v1",
        "ADR-014",
    )


@pytest.mark.parametrize("bad", ["G2", "G1,G2", "g1", "W", "S", "all"])
def test_accept_failed_refuses_any_value_but_g1_before_any_work(
    full_run, monkeypatch, bad
):
    import rag.embedding

    run, *_ = full_run
    monkeypatch.setattr(
        rag.embedding, "OllamaEmbedding", lambda: pytest.fail("work was started")
    )
    with pytest.raises(SystemExit, match="only G1"):
        run("--accept-failed", bad)


def test_accept_failed_refuses_any_version_but_v1_before_any_work(
    full_run, monkeypatch
):
    import rag.embedding

    run, *_ = full_run
    monkeypatch.setattr(
        rag.embedding, "OllamaEmbedding", lambda: pytest.fail("work was started")
    )
    with pytest.raises(SystemExit, match="only for dataset version v1"):
        run("--version", "v2", "--accept-failed", "G1")


def test_a_list_with_spaces_and_repeats_is_collapsed():
    assert g.parse_accept_failed("", "v1") == ()
    assert g.parse_accept_failed(None, "v2") == ()
    assert g.parse_accept_failed(" G1, G1 ,", "v1") == ("G1",)


def test_without_the_flag_a_failed_g1_is_a_plain_failure(full_run, monkeypatch):
    run, report, *_ = full_run
    _g1_fails_the_rest_pass(monkeypatch)
    _pin(monkeypatch)
    code, text = run()
    data = json.loads(report.read_text())
    assert code == 1 and "FREEZE WITH A RECORDED FAILURE" not in text
    assert "NOT FROZEN — a criterion failed" in text
    assert data["passed"] is False and data["freezable"] is False
    assert data["accepted_failures"] == [] and data["snapshot_digest"] is None


def test_an_accepted_g1_failure_is_freezable_loud_and_not_a_pass(full_run, monkeypatch):
    run, report, *_ = full_run
    _g1_fails_the_rest_pass(monkeypatch)
    _pin(monkeypatch)
    code, text = run("--accept-failed", "G1")
    data = json.loads(report.read_text())
    assert code == 3
    assert "--- FREEZE WITH A RECORDED FAILURE (G1, ADR-014) ---" in text
    assert "--- FREEZE ---" not in text and PIN in text and "not a pass" in text
    assert "G1 failed and is accepted as a recorded failure (ADR-014)" in text
    assert data["passed"] is False and data["freezable"] is True
    assert data["accepted_failures"] == ["G1"] and data["flags"] == []
    assert data["snapshot_digest"] == PIN


def test_the_flag_is_not_honoured_when_the_digest_is_not_the_pin(full_run, monkeypatch):
    _g1_fails_the_rest_pass(monkeypatch)
    _pin(monkeypatch, value="e" * 64)
    _not_honoured(full_run, "not the pinned snapshot")


def test_the_flag_is_not_honoured_with_the_real_pin_on_the_fixture_files(
    full_run, monkeypatch
):
    _g1_fails_the_rest_pass(monkeypatch)
    _not_honoured(full_run, "not the pinned snapshot")


def test_the_flag_is_not_honoured_when_another_criterion_fails_too(
    full_run, monkeypatch
):
    _g1_fails_the_rest_pass(monkeypatch, g2_passes=False)
    _pin(monkeypatch)
    _not_honoured(full_run, "other criteria failed")


def test_the_flag_is_not_honoured_under_s3(full_run, monkeypatch):
    _g1_fails_the_rest_pass(monkeypatch)
    _pin(monkeypatch)
    readings = iter([1, 1, 2] + [1] * 100)
    monkeypatch.setattr(g, "memory_pressure_level", lambda: next(readings))
    _not_honoured(full_run, "a flag was raised")


def test_the_flag_is_not_honoured_for_an_ungrounded_run(full_run, monkeypatch):
    import rag.retrieve

    _g1_fails_the_rest_pass(monkeypatch)
    _pin(monkeypatch)
    monkeypatch.setattr(rag.retrieve, "retrieve", lambda text, product_id=None: ([], 0))
    _not_honoured(full_run, "a flag was raised")


def test_the_flag_is_not_honoured_when_g2_is_met_by_paraphrases_only(
    full_run, monkeypatch
):
    _g1_fails_the_rest_pass(monkeypatch)
    _pin(monkeypatch)
    monkeypatch.setattr(g, "paraphrase_only", lambda pairs, by_id: True)
    _not_honoured(full_run, "a flag was raised")


def test_the_flag_changes_nothing_when_g1_passes(full_run, monkeypatch):
    run, report, *_ = full_run
    _criteria_all_green(monkeypatch)
    _pin(monkeypatch)
    code, text = run("--accept-failed", "G1")
    data = json.loads(report.read_text())
    assert code == 0 and "--- FREEZE ---" in text
    assert "RECORDED FAILURE" not in text
    assert data["passed"] is True and data["freezable"] is False
    assert data["accepted_failures"] == [] and data["snapshot_digest"] == PIN


def test_an_old_run_without_the_flag_keeps_exit_codes_zero_and_one(
    full_run, monkeypatch
):
    run, *_ = full_run
    assert run()[0] == 1  # G1 fails on four queries
    _criteria_all_green(monkeypatch)
    assert run()[0] == 0


# --- reachable traps (3.4's definition, partner_cosine.py: a probe_kind other than name-swap-same;
# --- reachable when the cosine with its pair_of partner is at least SIM_FLOOR) -------------------
def _probe(qa_id, split, vec, pair_of="", probe_kind=""):
    return g.Query(
        qa_id=qa_id,
        question=qa_id,
        split=split,
        embedding=vec,
        pair_of=pair_of,
        probe_kind=probe_kind,
    )


NEAR, FAR = [1.0, 0.1], [0.1, 1.0]


def test_reachable_traps_by_split_and_kind_as_records_and_unique_pairs():
    qs = [
        _probe("a", "validation", [1.0, 0.0]),
        _probe("t1", "validation", NEAR, "a", "lookalike"),  # reachable
        _probe("t2", "validation", FAR, "a", "lookalike"),  # a trap, out of reach
        _probe(
            "x", "validation", NEAR, "y", "policy-condition"
        ),  # mutual twins, reachable
        _probe("y", "validation", [1.0, 0.0], "x", "policy-condition"),
        _probe("n", "validation", NEAR, "a", "name-swap-same"),  # not a trap
        _probe(
            "p", "validation", NEAR, "a", ""
        ),  # pair_of without a probe_kind: ignored
        _probe("b", "test", [1.0, 0.0]),
        _probe("t3", "test", NEAR, "b", "lookalike"),
    ]
    got = g.reachable_traps(qs)
    v = got["validation"]
    assert v["lookalike"] == {
        "records": 2,
        "reachable": 1,
        "pairs": 2,
        "pairs_reachable": 1,
    }
    assert v["policy-condition"] == {
        "records": 2,
        "reachable": 2,
        "pairs": 1,
        "pairs_reachable": 1,
    }
    assert v["all"] == {"records": 4, "reachable": 3, "pairs": 3, "pairs_reachable": 2}
    assert "name-swap-same" not in v
    assert got["test"]["all"] == {
        "records": 1,
        "reachable": 1,
        "pairs": 1,
        "pairs_reachable": 1,
    }
    assert got["whole"]["all"] == {
        "records": 5,
        "reachable": 4,
        "pairs": 4,
        "pairs_reachable": 3,
    }


def test_a_partner_that_is_missing_or_at_the_floor_is_counted_correctly(monkeypatch):
    at_floor = [
        3.0,
        4.0,
    ]  # cosine 0.6 with [1, 0]; the floor is set to exactly that value
    monkeypatch.setattr(g, "SIM_FLOOR", g.cosine([1.0, 0.0], at_floor))
    qs = [
        _probe("a", "validation", [1.0, 0.0]),
        _probe("at", "validation", at_floor, "a", "lookalike"),
        _probe("gone", "validation", NEAR, "no-such-record", "lookalike"),
    ]
    got = g.reachable_traps(qs)["validation"]["all"]
    assert got["records"] == 2 and got["reachable"] == 1


def test_a_run_prints_and_records_the_reachable_traps_with_no_sample_size(full_run):
    run, report, *_ = full_run
    _, text = run()
    stats = json.loads(report.read_text())["statistics"]
    assert set(stats["reachable_traps"]) == {"validation", "test", "whole"}
    assert "reachable traps" in text and "reported, not gated" in text
    assert "sample size" not in text and "power" not in text
