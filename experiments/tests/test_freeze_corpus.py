"""Item 3.6, plan steps 9 and 10: assemble, check-index, freeze, verify.

A tiny synthetic world on disk: three products, two policy documents, a workload and its split
files, a real selection manifest (so `verify_selection` is run, not mocked), and gate reports built
from the world itself so the digests are the real ones. Each refusal and each failure has a test of
its own, and each one asserts that nothing was written.

The names and ids here are made up. None of them looks like an asin.
"""

import copy
import json
import os
import re
from types import SimpleNamespace

import build_pqa
import corpus_gate as g
import freeze_corpus as fm
import pytest
import select_pqa
from test_corpus_gate_freeze import MODEL_DIGEST, FakeRedis, Ollama, _vector, _workload

PRODUCTS = ("product-phones-aaa001", "product-phones-aaa002", "product-phones-aaa003")
POLICIES = ("policy-return-electronics", "policy-warranty-electronics")
MARKER = "zqx"  # a token that appears in every file name here, and must never reach the record


def _product(doc_id):
    return {
        "doc_id": doc_id,
        "title": f"Phone {MARKER}",
        "category": "phones",
        "specs": {"weight": "170 g"},
    }


def _policy(doc_id):
    return {
        "doc_id": doc_id,
        "title": "Policy",
        "category": "electronics",
        "text": " ".join(f"Clause {i} applies within thirty days." for i in range(60)),
    }


def _build(tmp_path, *, product_files=None, policy_files=None, write_manifest=True):
    """The sources and the selection manifest. Files are `{name: bytes}`, so a test can plant a bad
    one; the manifest is written last, from what is there, so `verify_selection` passes."""
    data = tmp_path / "data"
    products = data / "v1-draft" / "products"
    policies = data / "policies-v1"
    for d in (products, policies, data / "v1"):
        d.mkdir(parents=True, exist_ok=True)
    (data / "v1" / ".gitkeep").write_bytes(b"")
    if product_files is None:
        product_files = {
            f"{d}.json": json.dumps(_product(d)).encode() for d in PRODUCTS
        }
    if policy_files is None:
        policy_files = {f"{d}.json": json.dumps(_policy(d)).encode() for d in POLICIES}
    for name, raw in product_files.items():
        (products / name).write_bytes(raw)
    for name, raw in policy_files.items():
        (policies / name).write_bytes(raw)
    (data / "v1-draft" / select_pqa.POOL).write_bytes(b'{"q": 1}\n')
    (data / "v1-draft" / select_pqa.GENERIC).write_bytes(b"{}")
    if write_manifest:
        _write_manifest(tmp_path)
    return fm.default_paths(tmp_path)


def _write_manifest(tmp_path):
    draft = tmp_path / "data" / "v1-draft"
    count, digest = select_pqa.products_digest(draft / select_pqa.PRODUCTS)
    manifest = {
        "stage": select_pqa.STAGE,
        "selection_version": select_pqa.SELECTION_VERSION,
        "outputs": {
            "products": count,
            "products_sha256": digest,
            "question_pool_lines": 1,
            "question_pool_sha256": build_pqa.sha256_file(draft / select_pqa.POOL),
            "generic_tokens_sha256": build_pqa.sha256_file(draft / select_pqa.GENERIC),
        },
    }
    (tmp_path / "data" / "pqa-selection.json").write_text(json.dumps(manifest))


@pytest.fixture(autouse=True)
def small_world(monkeypatch, tmp_path):
    monkeypatch.setattr(fm, "EXPECTED_POLICIES", len(POLICIES))
    monkeypatch.setattr(
        g, "REPO_ROOT", tmp_path
    )  # snapshot_digest paths are repo-relative


def _listing(directory):
    return sorted(os.listdir(directory))


# =================================================================================================
# assemble
# =================================================================================================
def test_assemble_copies_the_bytes_and_reports_counts(tmp_path, capsys):
    p = _build(tmp_path)
    assert fm.cmd_assemble(p) == 0
    out = capsys.readouterr().out
    assert "3 product + 2 policy = 5 files (5 copied, 0 already there)" in out
    for source in sorted((p.draft_dir / "products").glob("*.json")) + sorted(
        p.policies_dir.glob("*.json")
    ):
        assert (p.corpus_dir / source.name).read_bytes() == source.read_bytes()
    assert (p.corpus_dir / ".gitkeep").exists()


def test_a_second_assemble_changes_nothing(tmp_path, capsys):
    p = _build(tmp_path)
    fm.assemble(p)
    before = {
        n: (p.corpus_dir / n).stat().st_mtime_ns for n in os.listdir(p.corpus_dir)
    }
    capsys.readouterr()
    assert fm.cmd_assemble(p) == 0
    assert "(0 copied, 5 already there)" in capsys.readouterr().out
    assert {
        n: (p.corpus_dir / n).stat().st_mtime_ns for n in os.listdir(p.corpus_dir)
    } == before


def _stray_json(tmp_path, p):
    (p.corpus_dir / "extra.json").write_text("{}")


def _differing_file(tmp_path, p):
    (p.corpus_dir / f"{PRODUCTS[0]}.json").write_text("{}")


def _stray_subdirectory(tmp_path, p):
    (p.corpus_dir / "old").mkdir()


def _record_present(tmp_path, p):
    p.record.write_text("{}")


def _source_edited_after_selection(tmp_path, p):
    (p.draft_dir / "products" / f"{PRODUCTS[0]}.json").write_text("{}")


def _a_product_missing_from_the_drafts(tmp_path, p):
    (p.draft_dir / "products" / f"{PRODUCTS[0]}.json").unlink()


def _a_policy_missing(tmp_path, p):
    (p.policies_dir / f"{POLICIES[0]}.json").unlink()


def _a_stray_file_among_the_policies(tmp_path, p):
    (p.policies_dir / "notes.txt").write_text("x")


@pytest.mark.parametrize(
    "break_it,fragment",
    [
        (_stray_json, "1 file(s) that are not part of the corpus"),
        (_differing_file, "1 that differ from their source"),
        (_stray_subdirectory, "1 file(s) that are not part of the corpus"),
        (_record_present, "v1 is frozen"),
        (_source_edited_after_selection, "do not match the selection manifest"),
        (_a_product_missing_from_the_drafts, "do not match the selection manifest"),
        (_a_policy_missing, "1 policy document(s); 2 expected"),
        (_a_stray_file_among_the_policies, "3 policy document(s); 2 expected"),
    ],
)
def test_assemble_refuses_and_writes_nothing(tmp_path, break_it, fragment):
    p = _build(tmp_path)
    break_it(tmp_path, p)
    held = _listing(p.corpus_dir)
    with pytest.raises(fm.Refusal) as refusal:
        fm.assemble(p)
    assert fragment in " | ".join(refusal.value.lines)
    assert _listing(p.corpus_dir) == held  # nothing was written, nothing was deleted
    assert MARKER not in str(refusal.value) and "aaa00" not in str(refusal.value)


@pytest.mark.parametrize(
    "name,doc,fragment",
    [
        (
            "product-phones-bbb001.json",
            {"doc_id": "product-phones-other"},
            "name that is not its doc_id",
        ),
        ("widget-1.json", {"doc_id": "widget-1"}, "without the 'product-' prefix"),
    ],
)
def test_assemble_refuses_a_product_with_a_bad_name_or_prefix(
    tmp_path, name, doc, fragment
):
    files = {f"{d}.json": json.dumps(_product(d)).encode() for d in PRODUCTS[:2]}
    files[name] = json.dumps(doc).encode()
    p = _build(tmp_path, product_files=files)
    with pytest.raises(fm.Refusal) as refusal:
        fm.assemble(p)
    assert fragment in " | ".join(refusal.value.lines)
    assert _listing(p.corpus_dir) == [".gitkeep"]


def test_assemble_refuses_a_policy_without_its_prefix(tmp_path):
    files = {
        f"{POLICIES[0]}.json": json.dumps(_policy(POLICIES[0])).encode(),
        "doc-warranty.json": json.dumps({"doc_id": "doc-warranty"}).encode(),
    }
    p = _build(tmp_path, policy_files=files)
    with pytest.raises(fm.Refusal, match="without the 'policy-' prefix"):
        fm.assemble(p)


def test_assemble_refuses_a_source_that_is_not_json(tmp_path):
    files = {
        f"{PRODUCTS[0]}.json": b"{not json",
        **{f"{d}.json": json.dumps(_product(d)).encode() for d in PRODUCTS[1:]},
    }
    p = _build(tmp_path, product_files=files)
    with pytest.raises(fm.Refusal, match="is not JSON"):
        fm.assemble(p)


def test_assemble_without_a_selection_manifest_refuses(tmp_path):
    p = _build(tmp_path, write_manifest=False)
    with pytest.raises(fm.Refusal, match="selection manifest"):
        fm.assemble(p)
    assert _listing(p.corpus_dir) == [".gitkeep"]


# =================================================================================================
# a frozen world: assembled files, a workload, two gate reports built from them
# =================================================================================================
def _report(p, *, passed=True):
    digest, per_file = g.snapshot_digest(g.freeze_files(p.corpus_dir, p.workload))
    chunk, count = g.chunk_digest(p.corpus_dir, "v1")
    return {
        "dataset": "v1",
        "workload": f"/Users/someone/{MARKER}/workload-v1.json",  # absolute: must be dropped
        "passed": passed,
        "snapshot_digest": digest if passed else None,
        "files": [{"path": f"{rel}", "sha256": sha} for rel, sha in per_file],
        "criteria": [
            {
                "name": "G1  high-similarity / low-overlap pairs (within split)",
                "passed": passed,
                "summary": "60 pair(s) with sim >= 0.85 and J <= 0.2 (need >= 50)",
            },
            {
                "name": "G2  within-product traps exist (validation)",
                "passed": True,
                "summary": "B-within=4  B-cross=3  ratio=1.33  unlabelled=0",
            },
        ],
        "statistics": {
            "g1_pairs_within_split": {"validation": 30, "test": 30},
            "high_sim_pairs": 90,
            "run_files": {
                "whole": {
                    "path": f"/Users/someone/{MARKER}/w.json",
                    "k_distinct_queries": 1274,
                    "cache_capacity": 318,
                },
                "validation": {
                    "path": "/x/v.json",
                    "k_distinct_queries": 622,
                    "cache_capacity": 156,
                },
                "test": {
                    "path": "/x/t.json",
                    "k_distinct_queries": 652,
                    "cache_capacity": 163,
                },
            },
            "s5": {"validation": False, "test": False},
            "pair_breakdown": {
                "g1": {"validation": {}, "test": {}},
                "g2": {"validation": {}, "test": {}},
            },
            "low_overlap_pairs": 61,
        },
        "git": {"commit": "f" * 40, "tree_clean": True, "paths": list(g.GIT_PATHS)},
        "embedding": {
            "tag": "nomic-embed-text",
            "digest": MODEL_DIGEST,
            "ollama_version": "0.33.2",
        },
        "retrieval": fm.current_retrieval_config(),
        "splitter": fm.current_splitter(),
        "packages": g.package_versions(),
        "chunk_digest": chunk,
        "chunk_count": count,
        "stored_vector_digest": "c" * 64,
        "index_check": {"passed": True, "tests": 5},
        "grounding": {"ungrounded": 0, "own_chunk_missing": 0},
        "memory_pressure": {"readings": [0, 0, 0, 0]},
        "stage2_seconds": 301.5,
        "query_vectors_vs_file": {
            "compared": 4,
            "missing": 0,
            "differing": 0,
            "max_abs_diff": 0.0,
        },
    }


@pytest.fixture
def world(tmp_path):
    p = _build(tmp_path)
    fm.assemble(p)
    _workload(tmp_path / "data")
    p.manifest.write_text(json.dumps({"stage": "3.4-workload"}))
    p.probe_flags.parent.mkdir(parents=True, exist_ok=True)
    p.probe_flags.write_text(json.dumps({"flags": [True, False]}))
    r1 = _report(p)
    r2 = copy.deepcopy(r1)
    run1, run2 = p.files_from, p.probe_flags.parent / "run2" / "report.json"
    run1.parent.mkdir(parents=True, exist_ok=True)
    run2.parent.mkdir(parents=True, exist_ok=True)

    def save():
        run1.write_text(json.dumps(r1))
        run2.write_text(json.dumps(r2))

    save()
    return SimpleNamespace(
        p=p, r1=r1, r2=r2, run1=run1, run2=run2, save=save, tmp=tmp_path
    )


def _freeze(w):
    w.save()
    return fm.cmd_freeze(w.p, w.run1, w.run2)


def _scan(text):
    return {
        "asin": fm.ASIN.search(text),
        "qa_id": fm.QA_ID.search(text),
        "path": "/Users/" in text,
    }


# =================================================================================================
# freeze
# =================================================================================================
def test_freeze_writes_the_record_with_the_gates_own_integers(world, capsys):
    assert _freeze(world) == 0
    record = json.loads(world.p.record.read_text())
    assert record["dataset_version"] == "v1" and record["freeze_version"] == 1
    assert record["snapshot_digest"] == world.r1["snapshot_digest"]
    assert record["file_count"] == len(world.r1["files"]) == 5 + 3
    assert (
        record["chunk_digest"] == world.r1["chunk_digest"] and record["chunk_count"] > 5
    )
    assert record["run_files"] == {
        "whole": {"k_distinct_queries": 1274, "cache_capacity": 318},
        "validation": {"k_distinct_queries": 622, "cache_capacity": 156},
        "test": {"k_distinct_queries": 652, "cache_capacity": 163},
    }
    assert record["workload_manifest_sha256"] == build_pqa.sha256_file(world.p.manifest)
    assert record["probe_flags_sha256"] == build_pqa.sha256_file(world.p.probe_flags)
    assert record["git_commit"] == "f" * 40
    assert (
        record["embedding"] == world.r1["embedding"]
        and record["packages"] == world.r1["packages"]
    )
    assert record["gate_run"]["run1"] == {
        "stage2_seconds": 301.5,
        "memory_readings": 4,
        "memory_max": 0,
        "query_vectors_vs_file": world.r1["query_vectors_vs_file"],
    }
    out = capsys.readouterr().out
    assert (
        "K=622" in out
        and "capacity=156" in out
        and "K=652" in out
        and "capacity=163" in out
    )


def test_the_record_holds_no_file_name_asin_qa_id_or_absolute_path(world):
    _freeze(world)
    text = world.p.record.read_text()
    assert MARKER not in text  # the absolute workload path carried it
    assert not any(_scan(text).values())
    for name in os.listdir(world.p.corpus_dir):
        assert name not in text and name.removesuffix(".json") not in text
    assert "files" not in json.loads(text)


def test_freeze_is_written_once(world):
    _freeze(world)
    first = world.p.record.read_text()
    with pytest.raises(fm.Refusal, match="already frozen"):
        _freeze(world)
    assert world.p.record.read_text() == first


def _run1(key_path, value):
    def mutate(w):
        node = w.r1
        for key in key_path[:-1]:
            node = node[key]
        node[key_path[-1]] = value

    return mutate


def _run2(key_path, value):
    def mutate(w):
        node = w.r2
        for key in key_path[:-1]:
            node = node[key]
        node[key_path[-1]] = value

    return mutate


def _drop_key(w):
    del w.r1["grounding"]


def _record_exists(w):
    w.p.record.write_text("{}")


def _digest_mismatch(w):
    (w.p.corpus_dir / f"{PRODUCTS[0]}.json").write_text(
        json.dumps(_product(PRODUCTS[0])) + " "
    )


def _chunk_digest_mismatch(w):
    w.r1["chunk_digest"] = w.r2["chunk_digest"] = "0" * 64


def _manifest_missing(w):
    w.p.manifest.unlink()


def _probe_flags_missing(w):
    w.p.probe_flags.unlink()


def _run2_other_pass_fail(w):
    w.r2["criteria"][1]["passed"] = False


@pytest.mark.parametrize(
    "mutate,fragment",
    [
        (_run1(["passed"], False), "run 1: the gate did not pass"),
        (_run1(["snapshot_digest"], None), "run 1: the report has no snapshot digest"),
        (_run1(["dataset"], "dev-v0"), "run 1: the report is for dataset 'dev-v0'"),
        (_run2(["passed"], False), "run 2: the gate did not pass"),
        (_run2(["dataset"], "dev-v0"), "run 2: the report is for dataset"),
        (
            _run1(["index_check", "passed"], False),
            "run 1: the index check did not pass",
        ),
        (
            _run1(["grounding", "ungrounded"], 1),
            "run 1: 1 ungrounded and 0 own-chunk-missing",
        ),
        (
            _run2(["grounding", "own_chunk_missing"], 2),
            "run 2: 0 ungrounded and 2 own-chunk-missing",
        ),
        (
            _run1(["git", "tree_clean"], False),
            "run 1: the code that measures was not a clean commit",
        ),
        (
            _run2(["git", "tree_clean"], False),
            "run 2: the code that measures was not a clean commit",
        ),
        (
            _run1(["memory_pressure", "readings"], [0, 1, 0]),
            "run 1: memory pressure was not green",
        ),
        (
            _run2(["memory_pressure", "readings"], [0, None, 0]),
            "run 2: memory pressure was not green",
        ),
        (
            _run1(["memory_pressure", "readings"], []),
            "run 1: memory pressure was not green",
        ),
        (
            _run1(["memory_pressure", "readings"], [True]),
            "run 1: memory pressure was not green",
        ),
        (
            _run1(["statistics", "s5"], {"validation": False, "test": True}),
            "run 1: S5 raised in test",
        ),
        (
            _run2(["statistics", "s5"], {"validation": True, "test": False}),
            "run 2: S5 raised in validation",
        ),
        (_drop_key, "run 1: the report lacks grounding"),
        (_record_exists, "already frozen"),
        (_digest_mismatch, "hash to a different snapshot digest than run 1 reported"),
        (
            _chunk_digest_mismatch,
            "chunks to a different chunk digest than run 1 reported",
        ),
        (_manifest_missing, "workload-manifest.json is missing"),
        (_probe_flags_missing, "probe-flags.json is missing"),
        (_run2_other_pass_fail, "the two runs differ on pass or fail"),
        (
            _run2(["stored_vector_digest"], "d" * 64),
            "the two runs differ in stored_vector_digest",
        ),
        (_run2(["embedding", "digest"], "e" * 64), "the two runs differ in embedding"),
        (_run2(["packages", "tiktoken"], "0.0.1"), "the two runs differ in packages"),
        (_run2(["git", "commit"], "a" * 40), "the two runs ran at different commits"),
    ],
)
def test_freeze_refuses_and_writes_nothing(world, mutate, fragment):
    existed = world.p.record.exists()
    mutate(world)
    existed = existed or world.p.record.exists()
    with pytest.raises(fm.Refusal) as refusal:
        _freeze(world)
    assert fragment in " | ".join(refusal.value.lines), refusal.value.lines
    assert world.p.record.exists() == existed
    if not existed:
        assert not world.p.record.exists()


def test_a_difference_in_counts_alone_is_recorded_and_run_1_stays_the_figure(
    world, capsys
):
    """S2: if the runs differ only in counts, record both; the frozen figure is run 1's."""
    world.r2["statistics"]["g1_pairs_within_split"] = {"validation": 31, "test": 30}
    world.r2["statistics"]["high_sim_pairs"] = 91
    assert _freeze(world) == 0
    record = json.loads(world.p.record.read_text())
    assert record["statistics"]["g1_pairs_within_split"] == {
        "validation": 30,
        "test": 30,
    }
    assert record["gate_run"]["comparison"] == [
        "statistics differ between the runs in: g1_pairs_within_split, high_sim_pairs"
    ]
    assert "run 1 is the figure" in capsys.readouterr().out


@pytest.mark.parametrize(
    "leak,kind",
    [
        ("see product-phones-" + "b0" + "7abc1234 for details", "an asin"),
        ("q-" + "policy-return-electronics:except-x", "a qa_id"),
        ("/Users/someone/data/x", "an absolute path"),
    ],
)
def test_freeze_refuses_a_record_that_would_carry_an_identifier(world, leak, kind):
    world.r1["criteria"][0]["summary"] = leak
    world.r2["criteria"][0]["summary"] = leak
    with pytest.raises(fm.Refusal, match=f"look like {kind}"):
        _freeze(world)
    assert not world.p.record.exists()


def test_the_refusal_names_every_reason_at_once(world):
    world.r1["grounding"]["ungrounded"] = 3
    world.r1["git"]["tree_clean"] = False
    world.r1["memory_pressure"]["readings"] = [2]
    with pytest.raises(fm.Refusal) as refusal:
        _freeze(world)
    assert len(refusal.value.lines) == 3


def test_freeze_reads_an_old_report_by_name_not_by_default(world):
    for key in ("git", "memory_pressure", "grounding", "index_check"):
        del world.r1[key]
    with pytest.raises(fm.Refusal) as refusal:
        _freeze(world)
    assert (
        "the report lacks git, " in refusal.value.lines[0]
        and "older gate" in refusal.value.lines[0]
    )


def test_freeze_with_no_report_file_refuses(world):
    with pytest.raises(fm.Refusal, match="no gate report"):
        fm.cmd_freeze(world.p, world.tmp / "nope.json", world.run2)


# =================================================================================================
# verify
# =================================================================================================
@pytest.fixture
def frozen(world):
    assert _freeze(world) == 0
    world.ollama = Ollama()
    return world


def _verify(w, **kw):
    return fm.cmd_verify(w.p, ollama_get=w.ollama, base_url="http://ollama", **kw)


def test_verify_passes_on_the_frozen_files(frozen, capsys):
    assert _verify(frozen) == 0
    assert "[PASS] v1 still matches v1-freeze.json: 8 files" in capsys.readouterr().out


def test_verify_reads_no_model(frozen):
    _verify(frozen)
    assert sorted(frozen.ollama.paths) == ["/api/tags", "/api/version"]


def test_one_flipped_byte_in_one_file_fails_and_names_it_from_the_per_file_list(
    frozen, capsys
):
    path = frozen.p.corpus_dir / f"{PRODUCTS[1]}.json"
    raw = bytearray(path.read_bytes())
    raw[-3] ^= 0x01
    path.write_bytes(bytes(raw))
    assert _verify(frozen) == 1
    out = capsys.readouterr().out
    assert "no longer hash to the recorded snapshot digest" in out
    assert f"first difference: data/v1/{PRODUCTS[1]}.json" in out


def test_without_the_per_file_list_it_fails_but_names_nothing(frozen, capsys):
    frozen.p.files_from.unlink()
    (frozen.p.corpus_dir / f"{PRODUCTS[1]}.json").write_text("{}")
    assert _verify(frozen) == 1
    out = capsys.readouterr().out
    assert (
        "no longer hash" in out
        and "first difference" not in out
        and PRODUCTS[1] not in out
    )


def test_a_missing_corpus_file_is_a_failure_not_a_skip(frozen, capsys):
    (frozen.p.corpus_dir / f"{PRODUCTS[0]}.json").unlink()
    assert _verify(frozen) == 1
    out = capsys.readouterr().out
    assert "7 file(s) now, 8 recorded" in out
    assert f"first difference: data/v1/{PRODUCTS[0]}.json" in out


def test_a_missing_workload_file_is_a_failure(frozen, capsys):
    g.split_path(frozen.p.workload, "test").unlink()
    assert _verify(frozen) == 1
    assert "cannot be read" in capsys.readouterr().out


def test_a_missing_corpus_directory_is_a_failure(frozen):
    for f in frozen.p.corpus_dir.iterdir():
        f.unlink()
    frozen.p.corpus_dir.rmdir()
    assert _verify(frozen) == 1


def test_a_moved_embedding_model_digest_fails(frozen, capsys):
    frozen.ollama.models[0]["digest"] = "9" * 64
    assert _verify(frozen) == 1
    assert "digest differs from the recorded one" in capsys.readouterr().out


def test_an_uninstalled_embedding_model_fails(frozen, capsys):
    frozen.ollama.models[:] = []
    assert _verify(frozen) == 1
    assert "not installed" in capsys.readouterr().out


def test_an_ollama_that_is_down_fails(frozen, capsys):
    frozen.ollama.down = True
    assert _verify(frozen) == 1
    assert "Ollama did not answer properly" in capsys.readouterr().out


def test_a_different_ollama_version_warns_and_does_not_fail(frozen, capsys):
    frozen.ollama.version = "0.34.0"
    assert _verify(frozen) == 0
    assert "[WARN] Ollama is 0.34.0" in capsys.readouterr().out


@pytest.mark.parametrize("attr,value", [("TOP_K", 6), ("EMBEDDING_DIM", 384)])
def test_a_changed_retrieval_config_fails(frozen, monkeypatch, capsys, attr, value):
    from rag import config

    monkeypatch.setattr(config, attr, value)
    assert _verify(frozen) == 1
    assert "the retrieval config differs from the record" in capsys.readouterr().out


def test_a_changed_index_algorithm_in_the_record_fails(frozen, capsys):
    record = json.loads(frozen.p.record.read_text())
    record["retrieval"]["index"] = "HNSW"
    frozen.p.record.write_text(json.dumps(record))
    assert _verify(frozen) == 1
    assert "retrieval config differs" in capsys.readouterr().out


def test_a_changed_chunk_size_fails(frozen, monkeypatch, capsys):
    from rag import config

    monkeypatch.setattr(config, "CHUNK_SIZE", 128)
    assert _verify(frozen) == 1
    out = capsys.readouterr().out
    assert "chunk size or overlap differs" in out and "different chunk digest" in out


def _tamper_package(w, name="tiktoken"):
    record = json.loads(w.p.record.read_text())
    record["packages"][name] = "0.0.1"
    w.p.record.write_text(json.dumps(record))


def test_a_package_version_alone_warns_and_does_not_fail(frozen, capsys):
    _tamper_package(frozen)
    assert _verify(frozen) == 0
    out = capsys.readouterr().out
    assert (
        "[WARN] package version(s) changed (tiktoken); the chunk digest did not move"
        in out
    )


def test_a_package_version_with_a_moved_chunk_digest_fails(frozen, monkeypatch, capsys):
    from rag import config

    _tamper_package(frozen)
    monkeypatch.setattr(config, "CHUNK_SIZE", 128)
    assert _verify(frozen) == 1
    assert (
        "package version(s) changed (tiktoken) and the chunks moved with them"
        in capsys.readouterr().out
    )


def test_a_changed_workload_manifest_fails(frozen, capsys):
    frozen.p.manifest.write_text(json.dumps({"stage": "3.4-workload", "edited": True}))
    assert _verify(frozen) == 1
    assert "the workload manifest differs from the record" in capsys.readouterr().out


@pytest.mark.parametrize("how", ["edit", "delete"])
def test_a_changed_or_missing_probe_flag_file_fails(frozen, capsys, how):
    if how == "edit":
        frozen.p.probe_flags.write_text(json.dumps({"flags": [False, False]}))
    else:
        frozen.p.probe_flags.unlink()
    assert _verify(frozen) == 1
    assert "the probe-flag file" in capsys.readouterr().out


def test_verify_without_a_record_fails(world, capsys):
    assert fm.cmd_verify(world.p, ollama_get=Ollama()) == 1
    assert "no freeze record" in capsys.readouterr().out


# =================================================================================================
# check-index
# =================================================================================================
@pytest.fixture
def indexed(world, monkeypatch):
    ollama = Ollama()
    monkeypatch.setattr(g, "ollama_get", ollama)
    return world, FakeRedis(g.offline_chunks(world.p.corpus_dir, "v1")), ollama


def test_check_index_passes_on_the_corpus_before_any_freeze(indexed, capsys):
    world, client, _ = indexed
    assert fm.cmd_check_index(world.p, client=client, base_url="http://ollama") == 0
    assert "(no freeze record yet: measured)" in capsys.readouterr().out


def test_check_index_exits_non_zero_on_an_index_that_holds_dev_v0(
    indexed, tmp_path, capsys
):
    """Acceptance A4, and the state this item leaves Redis in (ADR-014)."""
    world, _, _ = indexed
    stale = FakeRedis(
        {"product-phones-old001#chunk-0": "an old text"}, version="dev-v0"
    )
    assert fm.cmd_check_index(world.p, client=stale, base_url="http://ollama") == 1
    out = capsys.readouterr().out
    assert (
        "test 2" in out and "test 3" in out and "DATASET_VERSION=v1 make ingest" in out
    )
    assert "old001" not in out


def test_check_index_compares_with_the_record_once_there_is_one(indexed, capsys):
    world, client, ollama = indexed
    record = {"stored_vector_digest": "", "embedding": {"digest": MODEL_DIGEST}}
    record["stored_vector_digest"] = g.vector_digest(
        {r["chunk_id"]: r["vector"] for r in client.rows}
    )
    world.p.record.write_text(json.dumps(record))
    assert fm.cmd_check_index(world.p, client=client, base_url="http://ollama") == 0
    assert "and compared with the record" in capsys.readouterr().out

    client.rows[2]["vector"] = _vector(3)  # one vector moved
    assert fm.cmd_check_index(world.p, client=client, base_url="http://ollama") == 1
    assert "test 4" in capsys.readouterr().out

    client.rows[2]["vector"] = _vector(2)
    ollama.models[0]["digest"] = "8" * 64  # the model moved
    assert fm.cmd_check_index(world.p, client=client, base_url="http://ollama") == 1
    assert "test 5" in capsys.readouterr().out


# =================================================================================================
# the command line
# =================================================================================================
def test_main_assembles_and_prints_a_refusal_on_stderr_with_exit_2(
    tmp_path, monkeypatch, capsys
):
    p = _build(tmp_path)
    monkeypatch.setattr(fm, "default_paths", lambda *a, **k: p)
    assert fm.main(["assemble"]) == 0
    (p.corpus_dir / "extra.json").write_text("{}")
    assert fm.main(["assemble"]) == 2
    captured = capsys.readouterr()
    assert (
        "REFUSED — nothing was written" in captured.err
        and "not part of the corpus" in captured.err
    )


def test_main_freeze_needs_both_reports(capsys):
    with pytest.raises(SystemExit):
        fm.main(["freeze", "--run1", "a.json"])
    assert "--run2" in capsys.readouterr().err


def test_the_scan_patterns_do_not_fire_on_digests_or_ordinary_words():
    text = json.dumps(
        {"d": "a" * 40, "m": MODEL_DIGEST, "n": "B-within=4", "v": "0.33.2"}
    )
    assert not any(_scan(text).values())
    assert not re.search(fm.QA_ID, "a question about a quarter")
