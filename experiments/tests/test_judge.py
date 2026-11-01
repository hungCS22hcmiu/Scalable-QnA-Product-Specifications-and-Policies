"""Item 5.1 (docs/work/2026-10-30-judge-harness/design.md): the verdict key and the judge harness.

Done condition 4: the key is pinned by a value computed outside Python, and two different questions that
share one answer (or one question under two products) never share a key. A key on the answer alone
would merge `(q1, A)` and `(q2, A)`, and the false-hit rate would take whichever verdict came first.

No Ollama, no Redis, no network: every test runs against a fake judge and a temp folder.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import judge
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_KEY_FILE = ROOT / "docs/work/2026-10-30-judge-harness/evidence/golden-key.txt"

EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
# Computed with printf, wc and shasum (plan step 2.1), not with this module: query "Is the café mug 12
# oz?" (22 characters, 23 bytes), product "product-x", and the empty answer's hash.
GOLDEN_KEY = "d2f8597f95e17b78e95c3a62c7f4c2c229e25fe21bb544e5c45647200c5fbb41"
GOLDEN_QUERY = "Is the café mug 12 oz?"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_key_golden_value():
    assert judge.verdict_key(GOLDEN_QUERY, "product-x", EMPTY_SHA) == GOLDEN_KEY


def test_key_golden_value_equals_the_shell_computed_file():
    recorded = GOLDEN_KEY_FILE.read_text().split()[0]
    assert recorded == GOLDEN_KEY


def test_key_counts_utf8_bytes_not_characters():
    # The netstring of the query must say 23 (bytes). A character count (22) is a different key.
    by_characters = hashlib.sha256(
        b"vk1:22:"
        + GOLDEN_QUERY.encode()
        + b",9:product-x,64:"
        + EMPTY_SHA.encode()
        + b","
    ).hexdigest()
    assert by_characters != GOLDEN_KEY
    by_bytes = hashlib.sha256(
        b"vk1:23:"
        + GOLDEN_QUERY.encode()
        + b",9:product-x,64:"
        + EMPTY_SHA.encode()
        + b","
    ).hexdigest()
    assert by_bytes == GOLDEN_KEY


def test_key_differs_for_two_questions_with_one_answer():
    a = sha("Returns are accepted within 30 days.")
    first = judge.verdict_key("Can I return the mug?", "product-mug", a)
    second = judge.verdict_key("Can I return the lamp?", "product-mug", a)
    assert first != second


def test_key_differs_for_one_question_and_answer_under_two_product_ids():
    a = sha("Yes.")
    first = judge.verdict_key("Is it dishwasher safe?", "product-mug", a)
    second = judge.verdict_key("Is it dishwasher safe?", "product-lamp", a)
    assert first != second


def test_key_differs_for_one_question_with_two_answers():
    first = judge.verdict_key("q", "p", sha("30 days"))
    second = judge.verdict_key("q", "p", sha("14 days"))
    assert first != second


def test_key_empty_product_id_is_a_valid_field():
    a = sha("Yes.")
    empty = judge.verdict_key("Is it safe?", "", a)
    assert len(empty) == 64 and set(empty) <= set("0123456789abcdef")
    assert empty != judge.verdict_key("Is it safe?", "product-x", a)
    assert empty == judge.verdict_key("Is it safe?", "", a)  # and it repeats


@pytest.mark.parametrize(
    "first, second",
    [
        (("a,", "b"), ("a", ",b")),
        (("a", "b,1:c"), ("a,1:b", "c")),
        (("ab", ""), ("a", "b")),
        (("1:a,", ""), ("1:a", ",")),
    ],
)
def test_key_no_text_can_fake_a_field_boundary(first, second):
    a = sha("x")
    assert judge.verdict_key(first[0], first[1], a) != judge.verdict_key(
        second[0], second[1], a
    )


def test_key_is_lowercase_hex_of_64_characters():
    key = judge.verdict_key("q", "p", sha("a"))
    assert len(key) == 64
    assert key == key.lower()
    assert set(key) <= set("0123456789abcdef")


# =================================================================================================
# Done condition 9: the harness, against a fake judge and a fake Ollama
# =================================================================================================
# A small world on disk: a finished run with 9 records, its manifest, a reference set, the frozen judge
# (a test prompt, so the fake can read question and answer back from it) and a pre-registration that
# holds the judge's hash. The run gives each error layer exactly once (see `fixture_records`).
RUN_ID = "2026-11-01T10-00-00_cfg4_fixture"
JUDGE_MODEL = "judge-m:1b"
JUDGE_DIGEST = "d" * 64
GENERATOR = "gen-m:2b"
PROMPT = "Q::{question}\nR::{reference}\nA::{answer}\n"
# The pinned reference writer (ADR-023) as the fixture's `reference-writer-v1.json` holds it. The
# reference set's version.json carries the same five fields, so the preflight passes.
WRITER = {
    "version": "reference-writer-v1",
    "model": "writer-m:4b",
    "digest": "w" * 64,
    "options": {"num_ctx": 8192, "temperature": 0, "seed": 20261101},
    "think": False,
    "prompt_sha256": "p" * 64,
}

A1 = "The mug has a 1 year warranty."
A2 = "Returns are accepted within 30 days."
A3 = "The mug holds 300 ml."
A4 = "Returns are accepted within 14 days."

REFERENCES = [
    # qa_id, question, product_id, stratum, answerable, gold documents
    (
        "qa-warranty",
        "How long is the mug warranty?",
        "product-mug",
        "A",
        True,
        ["product-mug"],
    ),
    ("qa-colour", "What colour is the mug?", "product-mug", "A", True, ["product-mug"]),
    (
        "qa-return",
        "Can I return the mug after 30 days?",
        "product-mug",
        "B-within",
        True,
        ["policy-return-new"],
    ),
    (
        "qa-return2",
        "Is the mug returnable after a month?",
        "product-mug",
        "B-within",
        True,
        ["policy-return-new"],
    ),
    (
        "qa-capacity",
        "What is the mug capacity?",
        "product-mug",
        "A",
        True,
        ["product-mug"],
    ),
    ("qa-big", "How big is the mug?", "product-mug", "A", False, ["product-mug"]),
    (
        "qa-shirt",
        "Can I return the shirt after 30 days?",
        "product-shirt",
        "B-within",
        True,
        ["policy-return-new"],
    ),
    ("qa-nopid", "Do you ship abroad?", "", "C", True, ["policy-shipping"]),
]
QUESTION = {qa: question for qa, question, *_ in REFERENCES}
PRODUCT = {qa: product for qa, _, product, *_ in REFERENCES}

# What the fake judge says for a (question, answer). A pair that is not here fails the test: the judge
# was asked something the fixture never meant to ask.
REPLIES = {
    (QUESTION["qa-warranty"], A1): "INCORRECT",
    (QUESTION["qa-colour"], A1): "INCORRECT",
    (QUESTION["qa-return"], A2): "CORRECT",
    (QUESTION["qa-return2"], A2): "INCORRECT",
    (QUESTION["qa-capacity"], A3): "maybe",
    (QUESTION["qa-big"], A3): "INCORRECT",
    (QUESTION["qa-shirt"], A4): "INCORRECT",
}


def read_jsonl(path):
    return [
        json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()
    ]


def rec(i, cache, qa, answer, entry, retrieved, mutation="off", **extra):
    """One evaluation-log record. `_answer` is the text for the answer store, removed on writing."""
    r = {
        "request_id": f"req-{i:02d}",
        "run_id": RUN_ID,
        "config_id": 4,
        "mutation": mutation,
        "support_gate": "on",
        "mixed_lane": "off",
        "query_raw": QUESTION[qa],
        "cache": cache,
        "retrieved_chunk_ids": retrieved,
        "entry_id": entry,
        "entry_sources": [f"{entry}-src"] if entry else None,
        "answer_sha256": sha(answer) if answer is not None else "",
        "_answer": answer,
    }
    if PRODUCT[qa]:
        r["product_id"] = PRODUCT[qa]
    r.update(extra)
    return r


def fixture_records(mutation="off"):
    """Nine records that give each error layer exactly once:
    1 generation (a MISS, wrong) · 2 inherited (a hit on 1's entry) · 3 a correct MISS · 4 reuse (a wrong
    hit on 3's entry) · 5 an UNPARSED MISS · 6 undecided (a wrong hit on 5's entry) · 7 retrieval (the first
    policy chunk is another document) · 8 a TIER1_HIT that shares 3's key · 9 a SHED with no answer."""
    m = mutation
    return [
        rec(
            1,
            "MISS",
            "qa-warranty",
            A1,
            "E1",
            ["product-mug#chunk-0", "policy-return-new#chunk-0"],
            m,
        ),
        rec(2, "TIER2_HIT", "qa-colour", A1, "E1", ["product-mug#chunk-1"], m),
        rec(
            3,
            "MISS",
            "qa-return",
            A2,
            "E2",
            ["policy-return-new#chunk-0", "product-mug#chunk-0"],
            m,
        ),
        rec(4, "TIER2_HIT", "qa-return2", A2, "E2", ["policy-return-new#chunk-1"], m),
        rec(5, "MISS", "qa-capacity", A3, "E3", ["product-mug#chunk-2"], m),
        rec(6, "TIER2_HIT", "qa-big", A3, "E3", ["product-mug#chunk-0"], m),
        rec(
            7,
            "MISS",
            "qa-shirt",
            A4,
            "E4",
            ["policy-return-old#chunk-0", "product-shirt#chunk-0"],
            m,
        ),
        rec(8, "TIER1_HIT", "qa-return", A2, "E2", None, m),
        rec(9, "SHED", "qa-nopid", None, "", None, m, shed=True),
    ]


class FakeOllama:
    """Stands in for Ollama: `/api/tags`, `/api/ps`, `/api/show` and `/api/generate`."""

    def __init__(self, replies):
        self.tags = {JUDGE_MODEL: JUDGE_DIGEST, GENERATOR: "g" * 64}
        self.loaded = []
        self.capabilities = ["completion"]
        self.replies = {
            k: (list(v) if isinstance(v, list) else v) for k, v in replies.items()
        }
        self.generate_bodies = []
        self.asked = []  # (question, reference, answer) of every generate call

    def __call__(self, path, body=None):
        if path == "/api/tags":
            return {"models": [{"name": n, "digest": d} for n, d in self.tags.items()]}
        if path == "/api/ps":
            return {"models": [{"name": n} for n in self.loaded]}
        if path == "/api/show":
            return {"capabilities": self.capabilities}
        assert path == "/api/generate", path
        self.generate_bodies.append(body)
        lines = body["prompt"].split("\n")
        question, reference, answer = (line.split("::", 1)[1] for line in lines[:3])
        self.asked.append((question, reference, answer))
        reply = self.replies[(question, answer)]
        if isinstance(reply, list):
            reply = reply.pop(0)
        return {"response": reply}


def generation(retrieval_version="adr-021"):
    return {
        "model": GENERATOR,
        "digest": "g" * 64,
        "num_ctx": 8192,
        "think": False,
        "temperature": 1.0,
        "prompt_sha256": "p" * 64,
    }


def study_state(retrieval_version="adr-021"):
    return {
        "generator": generation(),
        "corpus": {"dataset_version": "v1", "snapshot_digest": "c" * 64},
        "retrieval": {
            "retrieval_version": retrieval_version,
            "retrieve_py_sha256": "r" * 64,
            "top_k": 5,
        },
    }


def manifest_for(records, mutation="off", admissible=True):
    by_cache = {}
    for r in records:
        by_cache[r["cache"]] = by_cache.get(r["cache"], 0) + 1
    return {
        "manifest_version": 1,
        "run_id": RUN_ID,
        "written_at": "2026-11-01T10:00:00+00:00",
        "gateway": {"git_sha": "a" * 40, "dirty": False},
        "arms": {
            "config_id": 4,
            "mutation": mutation,
            "support_gate": "on",
            "mixed_lane": "off",
        },
        "envelope": "ENVELOPE server_pid=1 runner_pid=2 version=0.33.2 np=1 ctx=8192 "
        "total_slots=1 n_ctx_slot=8192 blob=sha256-x",
        "redis": {"redis_version": "8.0.0", "rdb_last_save_time": 1},
        **{k: v for k, v in study_state().items() if k != "generator"},
        "workload": {
            "file": "data/workload-v1-validation.json",
            "sha256": "w" * 64,
            "K": 622,
            "frozen_cache_capacity": 156,
        },
        "cache": {"capacity": 156, "tau_run": 0.85, "theta_run": 0.6},
        "generator": generation(),
        "records": {"count": len(records), "by_cache": by_cache},
        "admissibility": {
            "rule_6": True,
            "rule_10": True,
            "rule_12": True,
            "i9": True,
            "admissible": admissible,
        },
    }


@dataclass
class World:
    root: Path
    fake: FakeOllama

    @property
    def run_dir(self):
        return self.root / "results" / RUN_ID

    @property
    def refs_dir(self):
        return self.root / "refs" / "validation"

    @property
    def judge_path(self):
        return self.root / "judge" / "judge-v1.json"

    @property
    def writer_path(self):
        return self.root / "judge" / "reference-writer-v1.json"

    @property
    def prereg(self):
        return self.root / "preregistration.md"

    def run(self, **kw):
        args = {
            "results_dir": self.root / "results",
            "refs_root": self.root / "refs",
            "judge_path": self.judge_path,
            "writer_path": self.writer_path,
            "prereg_path": self.prereg,
            "ollama": self.fake,
            "pressure": lambda: 1,
            "log": lambda s: None,
        }
        args.update(kw)
        return judge.run(RUN_ID, **args)

    def out(self, name):
        return read_jsonl(self.run_dir / "judge" / name)

    def nothing_judged(self):
        return (
            self.fake.generate_bodies == []
            and not (self.run_dir / "judge").exists()
            and not (self.run_dir / "judge.partial").exists()
        )


def build_world(
    tmp_path,
    *,
    records=None,
    mutation="off",
    admissible=True,
    replies=None,
    version=None,
    prereg_has_hash=True,
    manifest_edit=None,
):
    root = tmp_path
    root.mkdir(parents=True, exist_ok=True)
    records = fixture_records(mutation) if records is None else records
    fake = FakeOllama(REPLIES if replies is None else replies)

    # the frozen judge: a prompt, judge-v1.json, and a pre-registration that holds its hash
    jdir = root / "judge"
    jdir.mkdir()
    (jdir / "prompt-v1.txt").write_text(PROMPT)
    cfg = {
        "version": "judge-v1",
        "model": JUDGE_MODEL,
        "digest": JUDGE_DIGEST,
        "prompt_file": "prompt-v1.txt",
        "prompt_sha256": sha(PROMPT),
        "options": {"temperature": 0, "seed": 1, "num_ctx": 4096, "num_predict": 8},
    }
    (jdir / "judge-v1.json").write_text(json.dumps(cfg, indent=2) + "\n")
    (jdir / "reference-writer-v1.json").write_text(json.dumps(WRITER, indent=2) + "\n")
    cfg_hash = hashlib.sha256((jdir / "judge-v1.json").read_bytes()).hexdigest()
    (root / "preregistration.md").write_text(
        f"# Pre-registration\n\n## 2026-11-01\njudge-v1.json sha256 {cfg_hash if prereg_has_hash else '-'}\n"
    )

    # the reference set
    refs_dir = root / "refs" / "validation"
    (refs_dir / "answers").mkdir(parents=True)
    rows = []
    for qa, question, product, stratum, answerable, gold in REFERENCES:
        text = f"REF {qa}"
        (refs_dir / "answers" / f"{sha(text)}.txt").write_text(text)
        rows.append(
            {
                "qa_id": qa,
                "question": question,
                "product_id": product,
                "stratum": stratum,
                "answerable": answerable,
                "gold_doc_ids": gold,
                "chunk_ids": [f"{g}#chunk-0" for g in gold],
                "reference_sha256": sha(text),
            }
        )
    (refs_dir / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    state = {**study_state(), "reference_writer": json.loads(json.dumps(WRITER))}
    if version:
        section, key, value = version
        state[section][key] = value
    (refs_dir / "version.json").write_text(json.dumps(state))

    # the run: records, answers and the manifest
    run_dir = root / "results" / RUN_ID
    (run_dir / "raw" / "answers").mkdir(parents=True)
    lines = []
    for r in records:
        r = dict(r)
        text = r.pop("_answer", None)
        if text is not None:
            (run_dir / "raw" / "answers" / f"{sha(text)}.txt").write_bytes(
                text.encode()
            )
        lines.append(json.dumps(r))
    (run_dir / "raw" / "requests.jsonl").write_text("\n".join(lines) + "\n")
    manifest = manifest_for(records, mutation, admissible)
    if manifest_edit:
        manifest_edit(manifest)
    (run_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))
    return World(root, fake)


# --- it judges every served answer, once per key ---------------------------------------------------
def test_dc9_judges_every_served_answer_once_per_verdict_key(tmp_path):
    world = build_world(tmp_path)

    summary = world.run()

    verdicts = world.out("verdicts.jsonl")
    rows = world.out("records.jsonl")
    assert (
        len(verdicts) == 7
    )  # records 3 and 8 are one key: the same question, product and answer
    assert len({v["verdict_key"] for v in verdicts}) == 7
    assert len(rows) == 9  # every record has a row
    served = [r for r in rows if r["verdict_key"] is not None]
    assert len(served) == 8  # all but the SHED
    assert all(r["verdict"] in judge.VERDICTS for r in served)
    shed = next(r for r in rows if r["cache"] == "SHED")
    assert (
        shed["verdict"] is None
        and shed["verdict_key"] is None
        and shed["layer"] is None
    )
    by_id = {r["request_id"]: r for r in rows}
    assert by_id["req-08"]["verdict_key"] == by_id["req-03"]["verdict_key"]
    assert by_id["req-08"]["verdict"] == by_id["req-03"]["verdict"] == "CORRECT"
    assert summary["verdict_keys"] == 7
    assert summary["records"]["total"] == 9 and summary["records"]["judged"] == 8
    # 7 keys judged once, then all 7 asked again (the re-judge takes at most 30)
    assert len(world.fake.generate_bodies) == 14
    first_pass = world.fake.asked[:7]
    assert len({(q, a) for q, _, a in first_pass}) == 7


def test_dc9_each_key_is_judged_against_its_own_reference(tmp_path):
    world = build_world(tmp_path)
    world.run()

    qa_of = {question: qa for qa, question in QUESTION.items()}
    for question, reference, _ in world.fake.asked:
        assert reference == f"REF {qa_of[question]}"


def test_dc9_one_question_asked_twice_with_one_answer_is_judged_once(tmp_path):
    records = fixture_records()
    records.append(rec(10, "TIER1_HIT", "qa-warranty", A1, "E1", None))
    world = build_world(tmp_path, records=records)

    world.run()

    assert len(world.out("verdicts.jsonl")) == 7
    assert len(world.out("records.jsonl")) == 10


# --- the join --------------------------------------------------------------------------------------
def index_rows(world):
    return read_jsonl(world.refs_dir / "index.jsonl")


def test_dc9_a_record_matching_no_workload_pair_stops_the_run(tmp_path):
    records = fixture_records()
    records.append(
        rec(
            10,
            "MISS",
            "qa-warranty",
            A1,
            "E9",
            ["product-mug#chunk-0"],
            query_raw="Not asked?",
        )
    )
    world = build_world(tmp_path, records=records)

    with pytest.raises(judge.JudgeRefused, match="req-10.*no workload"):
        world.run()

    assert world.nothing_judged()


def test_dc9_join_is_exact_on_question_and_product_id(tmp_path):
    world = build_world(tmp_path)
    index = index_rows(world)
    base = rec(1, "MISS", "qa-warranty", A1, "E1", [])
    other_product = rec(
        2, "MISS", "qa-warranty", A1, "E1", [], product_id="product-lamp"
    )
    no_product = {k: v for k, v in base.items() if k != "product_id"}
    padded = rec(
        3, "MISS", "qa-warranty", A1, "E1", [], query_raw=QUESTION["qa-warranty"] + " "
    )

    assert judge.join([base], index)["req-01"]["qa_id"] == "qa-warranty"
    for loose in (other_product, no_product, padded):
        with pytest.raises(judge.JudgeRefused, match="no workload"):
            judge.join([loose], index)


def test_dc9_join_treats_a_missing_product_id_as_the_empty_string(tmp_path):
    world = build_world(tmp_path)
    record = rec(9, "SHED", "qa-nopid", None, "", None)
    assert "product_id" not in record

    assert judge.join([record], index_rows(world))["req-09"]["qa_id"] == "qa-nopid"


def test_dc9_join_stops_on_a_request_id_that_repeats(tmp_path):
    world = build_world(tmp_path)
    one = rec(1, "MISS", "qa-warranty", A1, "E1", [])
    with pytest.raises(judge.JudgeRefused, match="twice"):
        judge.join([one, dict(one)], index_rows(world))


# --- the layers ------------------------------------------------------------------------------------
def test_dc9_the_fixture_gives_each_layer_exactly_once(tmp_path):
    world = build_world(tmp_path)

    summary = world.run()

    assert summary["layers"] == {
        "retrieval": 1,
        "generation": 1,
        "inherited": 1,
        "reuse": 1,
        "undecided": 1,
    }
    rows = {r["request_id"]: r for r in world.out("records.jsonl")}
    assert rows["req-01"]["layer"] == "generation"
    assert rows["req-02"]["layer"] == "inherited"
    assert rows["req-04"]["layer"] == "reuse"
    assert rows["req-06"]["layer"] == "undecided"
    assert rows["req-07"]["layer"] == "retrieval"
    for correct in (
        "req-03",
        "req-05",
        "req-08",
    ):  # CORRECT, UNPARSED, CORRECT: no layer
        assert rows[correct]["layer"] is None


def test_dc9_verdict_rows_store_the_fields_apart(tmp_path):
    world = build_world(tmp_path)
    world.run()

    rows = {r["request_id"]: r for r in world.out("records.jsonl")}
    reuse = rows["req-04"]
    index_hash = hashlib.sha256(
        (world.refs_dir / "index.jsonl").read_bytes()
    ).hexdigest()
    manifest_hash = hashlib.sha256(
        (world.run_dir / "manifest.yaml").read_bytes()
    ).hexdigest()
    assert reuse["gold_doc_ids"] == ["policy-return-new"]
    assert reuse["retrieved_chunk_ids"] == ["policy-return-new#chunk-1"]
    assert reuse["entry_sources"] == ["E2-src"]
    assert reuse["candidate_sources"] is None
    assert reuse["reference_sha256"] == sha("REF qa-return2")
    assert reuse["reference_version"] == index_hash
    assert reuse["manifest_sha256"] == manifest_hash
    assert reuse["judge_version"] == "judge-v1"
    assert reuse["layer"] == "reuse"
    assert reuse["entry_miss_request_id"] == "req-03"
    assert reuse["retrieval_miss"] is False
    assert reuse["qa_id"] == "qa-return2" and reuse["stratum"] == "B-within"
    assert reuse["answerable"] is True and rows["req-06"]["answerable"] is False
    assert rows["req-07"]["retrieval_miss"] is True
    assert rows["req-08"]["retrieval_miss"] is None  # a TIER1_HIT has no retrieval
    assert rows["req-08"]["entry_miss_request_id"] == "req-03"
    assert (
        rows["req-01"]["entry_miss_request_id"] is None
    )  # a MISS is its own entry's MISS


def test_dc9_a_hit_whose_entry_has_no_miss_in_the_run_is_undecided_not_reuse():
    hit = {"request_id": "r", "cache": "TIER2_HIT", "entry_id": "gone"}
    assert judge.layer(hit, "INCORRECT", None, False) == "undecided"


@pytest.mark.parametrize(
    "cache, entry_verdict, miss, want",
    [
        ("MISS", None, True, "retrieval"),
        (
            "TIER2_HIT",
            "INCORRECT",
            True,
            "retrieval",
        ),  # rule 1 comes first, for a hit too
        ("MISS", None, False, "generation"),
        ("MISS", None, None, "generation"),
        ("TIER2_HIT", "INCORRECT", False, "inherited"),
        ("TIER1_HIT", "INCORRECT", None, "inherited"),
        ("TIER2_HIT", "CORRECT", False, "reuse"),
        ("TIER1_HIT", "CORRECT", None, "reuse"),
        ("TIER2_HIT", "UNPARSED", False, "undecided"),
        ("TIER2_HIT", None, False, "undecided"),
    ],
)
def test_dc9_layer_first_match_wins(cache, entry_verdict, miss, want):
    record = {"request_id": "r", "cache": cache}
    assert judge.layer(record, "INCORRECT", entry_verdict, miss) == want


@pytest.mark.parametrize("verdict", ["CORRECT", "UNPARSED", None])
def test_dc9_only_an_incorrect_record_has_a_layer(verdict):
    record = {"request_id": "r", "cache": "MISS"}
    assert judge.layer(record, verdict, None, True) is None


def test_dc9_retrieval_miss_has_no_answer_without_a_retrieval():
    assert judge.retrieval_miss(None, ["product-a"]) is None


@pytest.mark.parametrize(
    "retrieved, gold, want",
    [
        (["product-a#chunk-0"], ["product-a"], False),
        (["product-b#chunk-0"], ["product-a"], True),
        ([], ["product-a"], True),  # an empty retrieval is a retrieval that missed
        (
            ["product-b#chunk-0", "product-a#chunk-3"],
            ["product-a"],
            False,
        ),  # any rank counts
        (["policy-new#chunk-0"], ["policy-new"], False),
        (
            ["policy-old#chunk-0", "policy-new#chunk-1"],
            ["policy-new"],
            True,
        ),  # not the first policy
        (
            ["product-a#chunk-0", "policy-new#chunk-1"],
            ["policy-new"],
            False,
        ),  # products do not count
        (["product-a#chunk-0"], ["policy-new"], True),  # no policy chunk at all
        (
            ["product-a#chunk-0", "policy-new#chunk-0"],
            ["product-a", "policy-new"],
            False,
        ),
        (
            ["policy-new#chunk-0"],
            ["product-a", "policy-new"],
            True,
        ),  # D: the product is missing
        (
            ["product-a#chunk-0", "policy-old#chunk-0"],
            ["product-a", "policy-new"],
            True,
        ),
    ],
)
def test_dc9_retrieval_miss_rule(retrieved, gold, want):
    assert judge.retrieval_miss(retrieved, gold) is want


def test_dc9_entry_miss_is_the_leader_not_a_coalesced_follower():
    follower = {"request_id": "f", "cache": "MISS", "entry_id": "E", "coalesced": True}
    leader = {"request_id": "l", "cache": "MISS", "entry_id": "E"}
    shed = {"request_id": "s", "cache": "MISS", "entry_id": ""}
    hit = {"request_id": "h", "cache": "TIER2_HIT", "entry_id": "E"}

    assert judge.entry_misses([follower, leader, hit, shed])["E"]["request_id"] == "l"
    assert judge.entry_misses([leader, follower])["E"]["request_id"] == "l"
    assert judge.entry_misses([follower])["E"]["request_id"] == "f"
    assert "" not in judge.entry_misses([shed])


# --- the parse -------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "reply, want",
    [
        ("CORRECT", "CORRECT"),
        ("INCORRECT", "INCORRECT"),
        ("  CORRECT\n", "CORRECT"),
        ("\tINCORRECT  ", "INCORRECT"),
        ("correct", "UNPARSED"),
        ("incorrect", "UNPARSED"),
        ("Incorrect", "UNPARSED"),
        ("CORRECT.", "UNPARSED"),
        ("INCORRECT.", "UNPARSED"),
        ("INCORRECT CORRECT", "UNPARSED"),
        ("CORRECT INCORRECT", "UNPARSED"),
        ("The answer is CORRECT", "UNPARSED"),
        ("NOT CORRECT", "UNPARSED"),
        ("", "UNPARSED"),
        ("   ", "UNPARSED"),
    ],
)
def test_dc9_parse_reads_only_the_two_exact_tokens(reply, want):
    assert judge.parse_verdict(reply) == want


def test_dc9_incorrect_never_reads_as_correct():
    # INCORRECT contains CORRECT: a substring test would call every wrong answer right.
    assert judge.parse_verdict("INCORRECT") != "CORRECT"
    assert judge.parse_verdict("INCORRECT\n") == "INCORRECT"


def test_dc9_a_reply_in_the_wrong_format_is_stored_and_counted_unparsed(tmp_path):
    world = build_world(tmp_path)

    summary = world.run()

    by_reply = {v["reply"]: v for v in world.out("verdicts.jsonl")}
    assert by_reply["maybe"]["verdict"] == "UNPARSED"  # the raw reply is kept
    assert summary["verdicts"] == {"CORRECT": 1, "INCORRECT": 5, "UNPARSED": 1}


def test_dc9_unparsed_over_two_percent_means_the_rates_are_not_reportable(tmp_path):
    world = build_world(tmp_path)
    summary = world.run()
    assert summary["unparsed_share"] == pytest.approx(1 / 7)
    assert summary["rates_reportable"] is False


def test_dc9_no_unparsed_means_the_rates_are_reportable(tmp_path):
    replies = {**REPLIES, (QUESTION["qa-capacity"], A3): "CORRECT"}
    world = build_world(tmp_path, replies=replies)
    summary = world.run()
    assert summary["verdicts"]["UNPARSED"] == 0
    assert summary["rates_reportable"] is True
    assert summary["layers"]["undecided"] == 0
    assert summary["layers"]["reuse"] == 2  # record 6 now has a CORRECT entry behind it


# --- the answers -----------------------------------------------------------------------------------
def test_dc9_load_answers_reads_every_named_file(tmp_path):
    world = build_world(tmp_path)
    records = read_jsonl(world.run_dir / "raw" / "requests.jsonl")

    answers = judge.load_answers(world.run_dir, records)

    assert answers[sha(A1)] == A1 and answers[sha(A4)] == A4
    assert "" not in answers and len(answers) == 4


def test_dc9_load_answers_stops_on_a_file_that_does_not_hash_to_its_name(tmp_path):
    world = build_world(tmp_path)
    records = read_jsonl(world.run_dir / "raw" / "requests.jsonl")
    (world.run_dir / "raw" / "answers" / f"{sha(A2)}.txt").write_text(
        "edited after the run"
    )

    with pytest.raises(judge.JudgeRefused, match="does not hash"):
        judge.load_answers(world.run_dir, records)
    with pytest.raises(judge.JudgeRefused, match="does not hash"):
        world.run()
    assert world.nothing_judged()


def test_dc9_load_answers_stops_on_a_missing_file(tmp_path):
    world = build_world(tmp_path)
    records = read_jsonl(world.run_dir / "raw" / "requests.jsonl")
    (world.run_dir / "raw" / "answers" / f"{sha(A3)}.txt").unlink()

    with pytest.raises(judge.JudgeRefused, match="missing"):
        judge.load_answers(world.run_dir, records)


def test_dc9_load_answers_stops_on_a_hash_that_is_not_64_hex(tmp_path):
    world = build_world(tmp_path)
    bad = [{"request_id": "x", "answer_sha256": "../../etc/passwd"}]
    with pytest.raises(judge.JudgeRefused, match="64"):
        judge.load_answers(world.run_dir, bad)


def test_dc9_an_empty_answer_is_a_real_answer_and_is_judged(tmp_path):
    empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert sha("") == empty
    records = fixture_records()
    records.append(rec(10, "MISS", "qa-colour", "", "E5", ["product-mug#chunk-0"]))
    replies = {**REPLIES, (QUESTION["qa-colour"], ""): "INCORRECT"}
    world = build_world(tmp_path, records=records, replies=replies)

    world.run()

    row = next(r for r in world.out("records.jsonl") if r["request_id"] == "req-10")
    assert row["verdict"] == "INCORRECT" and row["verdict_key"] is not None
    assert row["layer"] == "generation"


# --- the preflight: it refuses before the first judge call ------------------------------------------
@pytest.mark.parametrize(
    "section, key, value",
    [
        ("corpus", "snapshot_digest", "z" * 64),
        ("retrieval", "retrieval_version", "adr-022"),
        ("retrieval", "retrieve_py_sha256", "z" * 64),
        ("retrieval", "top_k", 7),
        ("generator", "digest", "z" * 64),
        ("generator", "model", "other:2b"),
        ("generator", "num_ctx", 4096),
        ("generator", "think", True),
        ("generator", "temperature", 0.5),
        ("generator", "prompt_sha256", "z" * 64),
    ],
)
def test_dc9_refuses_when_the_manifest_and_the_reference_index_disagree(
    tmp_path, section, key, value
):
    world = build_world(tmp_path, version=(section, key, value))

    with pytest.raises(judge.JudgeRefused, match=f"{section}.{key}"):
        world.run()

    assert world.nothing_judged()  # it never continues on a mismatch


def test_dc9_preflight_refuses_another_generator_prompt(tmp_path):
    # References and the run were made under two generator prompts: every other field agrees, so only
    # the prompt hash can show it. The six generator fields come from one function on both sides.
    world = build_world(tmp_path, version=("generator", "prompt_sha256", "z" * 64))
    manifest = yaml.safe_load((world.run_dir / "manifest.yaml").read_text())
    ref_version = json.loads((world.refs_dir / "version.json").read_text())
    cfg = judge.load_judge(world.judge_path)

    problems = judge.preflight(
        manifest,
        ref_version,
        cfg,
        world.prereg.read_text(),
        world.fake,
        writer_cfg=judge.refs.load_writer(world.writer_path),
    )

    assert len(problems) == 1
    assert problems[0].startswith("generator.prompt_sha256:")
    assert manifest["generator"]["prompt_sha256"] == "p" * 64
    assert ref_version["generator"]["prompt_sha256"] == "z" * 64
    with pytest.raises(judge.JudgeRefused, match="generator.prompt_sha256"):
        world.run()
    assert world.nothing_judged()


def test_dc9_preflight_refuses_a_reference_set_that_has_no_generator_prompt(tmp_path):
    # A version.json from before the prompt hash moved into the generator block must not pass.
    world = build_world(tmp_path)
    manifest = yaml.safe_load((world.run_dir / "manifest.yaml").read_text())
    ref_version = json.loads((world.refs_dir / "version.json").read_text())
    del ref_version["generator"]["prompt_sha256"]
    cfg = judge.load_judge(world.judge_path)

    problems = judge.preflight(
        manifest,
        ref_version,
        cfg,
        world.prereg.read_text(),
        world.fake,
        writer_cfg=judge.refs.load_writer(world.writer_path),
    )

    assert len(problems) == 1 and "generator.prompt_sha256" in problems[0]


@pytest.mark.parametrize(
    "key, value",
    [
        ("model", "other:4b"),
        ("digest", "z" * 64),
        ("options", {"num_ctx": 8192, "temperature": 1, "seed": 20261101}),
        ("think", True),
        ("prompt_sha256", "z" * 64),
    ],
)
def test_dc9_preflight_refuses_another_reference_writer(tmp_path, key, value):
    # References written by another model, digest, option set, thinking mode or prompt than the pinned
    # reference-writer-v1.json (ADR-023). Every other field agrees, so only the writer can show it.
    world = build_world(tmp_path, version=("reference_writer", key, value))
    manifest = yaml.safe_load((world.run_dir / "manifest.yaml").read_text())
    ref_version = json.loads((world.refs_dir / "version.json").read_text())
    cfg = judge.load_judge(world.judge_path)

    problems = judge.preflight(
        manifest,
        ref_version,
        cfg,
        world.prereg.read_text(),
        world.fake,
        writer_cfg=judge.refs.load_writer(world.writer_path),
    )

    assert len(problems) == 1
    assert problems[0].startswith(f"reference_writer.{key}:")
    with pytest.raises(judge.JudgeRefused, match=f"reference_writer.{key}"):
        world.run()
    assert world.nothing_judged()


def test_dc9_preflight_refuses_a_set_without_a_writer(tmp_path):
    # A version.json from before ADR-023 (no `reference_writer`) was written by the served generator.
    world = build_world(tmp_path)
    manifest = yaml.safe_load((world.run_dir / "manifest.yaml").read_text())
    ref_version = json.loads((world.refs_dir / "version.json").read_text())
    del ref_version["reference_writer"]
    cfg = judge.load_judge(world.judge_path)

    problems = judge.preflight(
        manifest,
        ref_version,
        cfg,
        world.prereg.read_text(),
        world.fake,
        writer_cfg=judge.refs.load_writer(world.writer_path),
    )

    assert len(problems) == 1 and "no reference_writer block" in problems[0]
    (world.refs_dir / "version.json").write_text(json.dumps(ref_version))
    with pytest.raises(judge.JudgeRefused, match="no reference_writer block"):
        world.run()
    assert world.nothing_judged()


def test_dc9_a_matching_reference_set_passes_the_preflight(tmp_path):
    world = build_world(tmp_path)
    manifest = yaml.safe_load((world.run_dir / "manifest.yaml").read_text())
    ref_version = json.loads((world.refs_dir / "version.json").read_text())
    cfg = judge.load_judge(world.judge_path)
    prereg = world.prereg.read_text()

    writer = judge.refs.load_writer(world.writer_path)
    assert (
        judge.preflight(
            manifest, ref_version, cfg, prereg, world.fake, writer_cfg=writer
        )
        == []
    )


def test_dc9_refuses_an_inadmissible_run(tmp_path):
    world = build_world(tmp_path, admissible=False)
    with pytest.raises(judge.JudgeRefused, match="admissible"):
        world.run()
    assert world.nothing_judged()


def test_dc9_refuses_mutation_on(tmp_path):
    world = build_world(tmp_path, mutation="on")
    with pytest.raises(judge.JudgeRefused, match="mutation: on"):
        world.run()
    assert world.nothing_judged()


def test_dc9_refuses_when_the_manifest_check_fails_on_a_missing_field(tmp_path):
    def drop(manifest):
        del manifest["redis"]["rdb_last_save_time"]

    world = build_world(tmp_path, manifest_edit=drop)
    with pytest.raises(judge.JudgeRefused, match="manifest check.*rdb_last_save_time"):
        world.run()
    assert world.nothing_judged()


def test_dc9_refuses_when_a_record_has_another_arm_than_the_manifest(tmp_path):
    records = fixture_records()
    records[3] = {**records[3], "support_gate": "off"}
    world = build_world(tmp_path, records=records)
    with pytest.raises(judge.JudgeRefused, match="manifest check.*support_gate"):
        world.run()
    assert world.nothing_judged()


def test_dc9_refuses_without_a_manifest(tmp_path):
    world = build_world(tmp_path)
    (world.run_dir / "manifest.yaml").unlink()
    with pytest.raises(judge.JudgeRefused, match="manifest.yaml"):
        world.run()
    assert world.nothing_judged()


def test_dc9_refuses_while_the_generator_is_loaded(tmp_path):
    world = build_world(tmp_path)
    world.fake.loaded = [GENERATOR]
    with pytest.raises(judge.JudgeRefused, match="loaded"):
        world.run()
    assert world.nothing_judged()


def test_dc9_refuses_when_the_live_judge_digest_differs(tmp_path):
    world = build_world(tmp_path)
    world.fake.tags[JUDGE_MODEL] = "e" * 64  # a re-pulled tag
    with pytest.raises(judge.JudgeRefused, match="digest"):
        world.run()
    assert world.nothing_judged()


def test_dc9_refuses_when_the_judge_is_not_pulled(tmp_path):
    world = build_world(tmp_path)
    del world.fake.tags[JUDGE_MODEL]
    with pytest.raises(judge.JudgeRefused, match="not in /api/tags"):
        world.run()
    assert world.nothing_judged()


def test_dc9_refuses_when_the_prompt_file_was_edited(tmp_path):
    world = build_world(tmp_path)
    (world.root / "judge" / "prompt-v1.txt").write_text(PROMPT + "Be kind.\n")
    with pytest.raises(judge.JudgeRefused, match="prompt file"):
        world.run()
    assert world.nothing_judged()


def test_dc9_refuses_when_the_judge_config_is_not_pre_registered(tmp_path):
    world = build_world(tmp_path, prereg_has_hash=False)
    with pytest.raises(judge.JudgeRefused, match="preregistration"):
        world.run()
    assert world.nothing_judged()


def test_dc9_refuses_when_judge_config_was_edited_after_pre_registration(tmp_path):
    world = build_world(tmp_path)
    cfg = json.loads(world.judge_path.read_text())
    cfg["options"]["temperature"] = 0.7
    world.judge_path.write_text(json.dumps(cfg, indent=2) + "\n")
    with pytest.raises(judge.JudgeRefused, match="preregistration"):
        world.run()
    assert world.nothing_judged()


def test_dc9_refuses_when_the_output_exists(tmp_path):
    world = build_world(tmp_path)
    (world.run_dir / "judge").mkdir()
    with pytest.raises(judge.JudgeRefused, match="exists"):
        world.run()
    assert world.fake.generate_bodies == []


def test_dc9_refuses_when_a_partial_output_exists(tmp_path):
    world = build_world(tmp_path)
    (world.run_dir / "judge.partial").mkdir()
    with pytest.raises(judge.JudgeRefused, match="exists"):
        world.run()
    assert world.fake.generate_bodies == []


def test_dc9_a_second_run_is_refused_and_leaves_the_first_output_alone(tmp_path):
    world = build_world(tmp_path)
    world.run()
    before = (world.run_dir / "judge" / "verdicts.jsonl").read_bytes()
    calls = len(world.fake.generate_bodies)

    with pytest.raises(judge.JudgeRefused, match="exists"):
        world.run()

    assert (world.run_dir / "judge" / "verdicts.jsonl").read_bytes() == before
    assert len(world.fake.generate_bodies) == calls


def test_dc9_refuses_at_pressure_4_and_writes_nothing(tmp_path):
    world = build_world(tmp_path)
    with pytest.raises(judge.JudgeRefused, match="critical"):
        world.run(pressure=lambda: 4)
    assert world.nothing_judged()


def test_dc9_every_pressure_reading_is_stored_in_the_summary(tmp_path):
    world = build_world(tmp_path)
    summary = world.run(pressure=lambda: 2)
    assert summary["pressure_readings"] == [2]
    stored = json.loads((world.run_dir / "judge" / "summary.json").read_text())
    assert stored["pressure_readings"] == [2]


# --- where it writes -------------------------------------------------------------------------------
def snapshot(folder):
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def test_dc9_writes_beside_raw_not_inside(tmp_path):
    world = build_world(tmp_path)
    before = snapshot(world.run_dir / "raw")

    world.run()

    assert snapshot(world.run_dir / "raw") == before  # raw/ is untouched
    assert not (world.run_dir / "raw" / "judge").exists()
    assert sorted(p.name for p in (world.run_dir / "judge").iterdir()) == [
        "records.jsonl",
        "summary.json",
        "verdicts.jsonl",
    ]
    assert not (world.run_dir / "judge.partial").exists()  # renamed, not left behind
    assert (world.run_dir / "manifest.yaml").is_file()


def test_dc9_the_summary_holds_counts_and_timing(tmp_path):
    world = build_world(tmp_path)
    summary = world.run()

    assert summary["records"]["by_cache"] == {
        "MISS": 4,
        "SHED": 1,
        "TIER1_HIT": 1,
        "TIER2_HIT": 3,
    }
    assert summary["records"]["judged_by_cache"] == {
        "MISS": 4,
        "TIER1_HIT": 1,
        "TIER2_HIT": 3,
    }
    assert summary["seconds_per_verdict"]["median"] >= 0
    assert (
        summary["seconds_per_verdict"]["p95"]
        >= summary["seconds_per_verdict"]["median"]
    )
    assert summary["judge_version"] == "judge-v1"
    assert "reference_set_sha256" in summary and "wall_seconds" in summary


# --- the re-judge ----------------------------------------------------------------------------------
def test_dc9_the_rejudge_asks_the_same_keys_again_and_counts_the_flips(tmp_path):
    replies = {**REPLIES, (QUESTION["qa-shirt"], A4): ["INCORRECT", "CORRECT"]}
    world = build_world(tmp_path, replies=replies)

    summary = world.run()

    assert summary["rejudge"]["keys"] == 7  # fewer than 30 keys: all of them
    assert summary["rejudge"]["flips"] == 1
    flipped = summary["rejudge"]["flipped_keys"][0]
    shirt = next(r for r in world.out("records.jsonl") if r["qa_id"] == "qa-shirt")
    assert flipped == shirt["verdict_key"]
    assert shirt["verdict"] == "INCORRECT"  # the first verdict is the one that counts


def test_dc9_a_judge_that_repeats_itself_has_no_flips(tmp_path):
    summary = build_world(tmp_path).run()
    assert summary["rejudge"]["flips"] == 0


def test_dc9_the_rejudge_takes_at_most_30_keys(tmp_path):
    records = fixture_records()
    replies = dict(REPLIES)
    for i in range(40):  # 40 more distinct answers to one question: 40 more keys
        text = f"Answer number {i}"
        records.append(
            rec(100 + i, "MISS", "qa-colour", text, f"X{i}", ["product-mug#chunk-0"])
        )
        replies[(QUESTION["qa-colour"], text)] = "CORRECT"
    world = build_world(tmp_path, records=records, replies=replies)

    summary = world.run()

    assert summary["verdict_keys"] == 47
    assert summary["rejudge"]["keys"] == 30
    assert len(world.fake.generate_bodies) == 47 + 30


# --- the call --------------------------------------------------------------------------------------
def test_dc9_ask_judge_sends_one_non_streaming_generate_call(tmp_path):
    world = build_world(tmp_path)
    cfg = judge.load_judge(world.judge_path)
    seen = []

    def post(path, body):
        seen.append((path, body))
        return {"response": "CORRECT"}

    reply, seconds = judge.ask_judge("What is {x}?", "ref {y}", "ans {z}", cfg, post)

    assert reply == "CORRECT" and seconds >= 0
    assert len(seen) == 1
    path, body = seen[0]
    assert path == "/api/generate"
    assert body["stream"] is False
    assert body["model"] == JUDGE_MODEL
    assert body["options"] == cfg["options"]
    assert (
        body["prompt"] == "Q::What is {x}?\nR::ref {y}\nA::ans {z}\n"
    )  # braces in text are safe
    assert "think" not in body


def test_dc9_think_false_is_sent_only_to_a_model_that_lists_thinking(tmp_path):
    plain = build_world(tmp_path / "plain")
    plain.run()
    assert all("think" not in b for b in plain.fake.generate_bodies)

    thinker = build_world(tmp_path / "thinker")
    thinker.fake.capabilities = ["completion", "thinking"]
    thinker.run()
    assert all(b["think"] is False for b in thinker.fake.generate_bodies)


# --- the sanity pairs ------------------------------------------------------------------------------
def sanity_file(world, rows):
    path = world.root / "sanity.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def run_sanity(world, path, **kw):
    args = {
        "refs_dir": world.refs_dir,
        "judge_path": world.judge_path,
        "prereg_path": world.prereg,
        "generator_model": GENERATOR,
        "ollama": world.fake,
        "pressure": lambda: 1,
        "log": lambda s: None,
    }
    args.update(kw)
    return judge.sanity(path, **args)


SANITY = [
    {"qa_id": "qa-return", "answer": "Yes.", "expected": "CORRECT", "kind": "bare yes"},
    {
        "qa_id": "qa-colour",
        "answer": "It is blue.",
        "expected": "INCORRECT",
        "kind": "wrong",
    },
]


def sanity_world(tmp_path, replies):
    world = build_world(tmp_path, replies=replies)
    return world, sanity_file(world, SANITY)


def test_dc9_sanity_passes_when_every_verdict_is_the_expected_one(tmp_path):
    replies = {
        (QUESTION["qa-return"], "Yes."): "CORRECT",
        (QUESTION["qa-colour"], "It is blue."): "INCORRECT",
    }
    world, path = sanity_world(tmp_path, replies)

    assert run_sanity(world, path) == 0
    # each pair is judged against its own reference
    assert {a: r for _, r, a in world.fake.asked} == {
        "Yes.": "REF qa-return",
        "It is blue.": "REF qa-colour",
    }


def test_dc9_sanity_fails_on_a_wrong_verdict(tmp_path):
    replies = {
        (QUESTION["qa-return"], "Yes."): "INCORRECT",  # the judge gets one wrong
        (QUESTION["qa-colour"], "It is blue."): "INCORRECT",
    }
    world, path = sanity_world(tmp_path, replies)
    assert run_sanity(world, path) == 1


def test_dc9_sanity_counts_an_unparsed_reply_as_wrong(tmp_path):
    replies = {
        (QUESTION["qa-return"], "Yes."): "CORRECT.",
        (QUESTION["qa-colour"], "It is blue."): "INCORRECT",
    }
    world, path = sanity_world(tmp_path, replies)
    assert run_sanity(world, path) == 1


def test_dc9_sanity_refuses_while_the_generator_is_loaded(tmp_path):
    world, path = sanity_world(tmp_path, {})
    world.fake.loaded = [GENERATOR]
    with pytest.raises(judge.JudgeRefused, match="loaded"):
        run_sanity(world, path)
    assert world.fake.generate_bodies == []


def test_dc9_sanity_refuses_a_judge_that_is_not_pre_registered(tmp_path):
    world = build_world(tmp_path, prereg_has_hash=False)
    path = sanity_file(world, SANITY)
    with pytest.raises(judge.JudgeRefused, match="preregistration"):
        run_sanity(world, path)
    assert world.fake.generate_bodies == []


def test_dc9_sanity_refuses_a_qa_id_that_is_not_in_the_reference_set(tmp_path):
    world = build_world(tmp_path)
    path = sanity_file(
        world, [{"qa_id": "qa-nowhere", "answer": "x", "expected": "CORRECT"}]
    )
    with pytest.raises(judge.JudgeRefused, match="qa-nowhere"):
        run_sanity(world, path)
