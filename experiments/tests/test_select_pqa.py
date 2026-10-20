"""Tests for select_pqa.py (super-plan item 3.2). T-numbers are design.md §4 of
docs/work/2026-10-19-pqa-thick-tail-selection/.

Fixtures are small hand-made records, never PQA text. The interim and its manifest are written by
build_pqa's own parser, writer and manifest builder, so every hash the selector checks is real.
"""

import csv
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import build_pqa
import pytest
import select_pqa

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_PY = REPO_ROOT / "docs" / "work" / "2026-10-03-pqa-category-choice" / "probe.py"

# =================================================================================================
# Fixtures
# =================================================================================================
BULLETS = ("alpha bravo", "charlie delta", "echo foxtrot", "golf hotel", "india juliet")
ANSWERABLE = (
    "Is it alpha bravo charlie?",  # {alpha, bravo, charlie}
    "Is it alpha bravo charlie delta?",  # Jaccard 3/4 with the first: the near-duplicate pair
    "Does it echo foxtrot golf?",
    "Any hotel india juliet?",
    "Is alpha echo india included?",  # 3 of 4 covered
    "Has bravo foxtrot juliet?",
)
UNANSWERABLE = (
    "Does it have zulu yankee?",  # nothing covered
    "How tall is the chair?",  # R1 passes on "chair"; R2 removes it (generic) and fails
)
POLICY = "What is the return window?"
DYNAMIC = "What is the price?"
CARRIER = "Is it unlocked?"
DEFAULT_QUESTIONS = (*ANSWERABLE, *UNANSWERABLE, POLICY, DYNAMIC, CARRIER)  # 9 kept


def rec(asin, qid, text, title="Acme Chair Model", bullets=BULLETS, **over):
    """One raw PQA record in the real field names."""
    r = {
        "asin": asin,
        "question_id": qid,
        "question_text": text,
        "question_type": "yes-no",
        "answers": [{"answer_text": "yes"}],
        "answer_aggregated": "yes",
        "brand_name": "Acme",
        "item_name": title,
        "product_description": "A chair.",
    }
    for i in range(5):
        r[f"bullet_point{i + 1}"] = bullets[i] if i < len(bullets) else ""
    r.update(over)
    return r


def product(asin, questions=DEFAULT_QUESTIONS, **kw):
    return [rec(asin, f"{asin}-q{n}", q, **kw) for n, q in enumerate(questions)]


def asin(n):
    return f"B{n:09d}"


def chairs_records():
    """Ten products: three eligible, one failing each funnel step (design §2.2)."""
    records = []
    for n in (1, 2, 3):
        records += product(asin(n))
    records += product(asin(4), title="")  # titled
    records += product(asin(5), bullets=BULLETS[:2])  # bullets
    records += product(asin(6), title="Acme Chair Model 2-year warranty")  # no_warranty_term (title)
    conflicted = product(asin(7))
    for r in conflicted[1:]:
        r["bullet_point1"] = "different words"
    records += conflicted  # consistent
    records += product(asin(8), questions=ANSWERABLE[:4])  # cap: 4 kept
    records += product(
        asin(9), questions=(*ANSWERABLE[:4], *UNANSWERABLE, POLICY)
    )  # answerable: 4
    records += product(
        asin(10),
        questions=(
            *(ANSWERABLE[i] for i in (0, 2, 3, 4, 5)),
            "Does it have zulu yankee?",
            "Does it have zulu yankee xray?",  # a pair, but not among answerable questions
            POLICY,
        ),
    )  # pair
    return records


def desks_records():
    return product(asin(11), title="Acme Desk Model") + product(asin(12), title="Acme Desk Model")


# Counted by hand from the records above (design §2.6): capped = 5-50 kept and a near-duplicate
# pair among ALL kept; adr002 = capped and >= 3 bullets and no warranty term in the prose.
# chairs: capped fails only asin 8 (4 kept); adr002 also fails asin 5 (2 bullets).
PINS = {"capped": {"chairs": 9, "desks": 2}, "adr002": {"chairs": 8, "desks": 2}}
QUOTA = {"chairs": 2, "desks": 2}


def enc(r):
    return json.dumps(r).encode("utf-8") + b"\n"


def write_interim(tmp_path, leaves):
    """leaves: {leaf: (department, records)}. Written through build_pqa's parser, writer and
    manifest builder, so the hashes iter_interim checks are real."""
    interim = tmp_path / "v1-draft" / "pqa"
    interim.mkdir(parents=True)
    specs, entries, asins = [], {}, {}
    for leaf, (department, records) in leaves.items():
        result = build_pqa.parse_leaf([enc(r) for r in records])
        spec = build_pqa.LeafSpec(
            leaf=leaf,
            department=department,
            bytes=0,
            sha256="0" * 64,
            parsed=result.stats.parsed,
            products=result.stats.products,
            skipped_total=0,
        )
        info = build_pqa.write_interim(result.products, spec, interim)
        summary = build_pqa.summarise_interim(info.path)
        entries[leaf] = build_pqa.leaf_entry(result.stats, info, summary)
        asins[leaf] = frozenset(result.products)
        specs.append(spec)
    manifest = build_pqa.build_manifest(tuple(specs), entries, asins)
    path = tmp_path / "pqa-manifest.json"
    path.write_bytes(build_pqa.manifest_bytes(manifest))
    return path, interim


def fake_chunker(record):
    return len(record["title"]) + sum(len(v) for v in record["specs"].values()), 1


@pytest.fixture
def world(tmp_path):
    manifest, interim = write_interim(
        tmp_path, {"chairs": ("furniture", chairs_records()), "desks": ("furniture", desks_records())}
    )
    return {
        "manifest_path": manifest,
        "interim_dir": interim,
        "draft_dir": tmp_path / "v1-draft",
        "selection_path": tmp_path / "pqa-selection.json",
    }


def run(world, **over):
    kw = {"quota": QUOTA, "pins": PINS, "chunker": fake_chunker, **over}
    return select_pqa.select(**world, **kw)


def selection(world):
    return json.loads(world["selection_path"].read_bytes())


def outputs_of(world):
    d = world["draft_dir"]
    files = {p.name: p.read_bytes() for p in sorted((d / "products").iterdir())}
    return {
        "products": files,
        "pool": (d / select_pqa.POOL).read_bytes(),
        "generic": (d / select_pqa.GENERIC).read_bytes(),
        "selection": world["selection_path"].read_bytes(),
    }


def line(**over):
    """One interim product line, as iter_interim yields it."""
    base = {
        "asin": asin(1),
        "leaf": "chairs",
        "department": "furniture",
        "item_name": "Acme Chair Model",
        "brand_name": "Acme",
        "bullets": list(BULLETS),
        "product_description": "A chair.",
        "fields_conflict": False,
        "questions": [
            {
                "line_no": n + 1,
                "question_id": f"q{n}",
                "question_text": q,
                "question_type": "yes-no",
                "answer_aggregated": "yes",
                "answers": ["yes"],
            }
            for n, q in enumerate(DEFAULT_QUESTIONS)
        ],
    }
    base.update(over)
    return base


GENERIC = frozenset({"acme", "chair", "model"})


# =================================================================================================
# T12: the copied constants equal the probe's
# =================================================================================================
def load_probe():
    spec = importlib.util.spec_from_file_location("probe_2026_10_03", PROBE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_probe_constant_equals_the_probe_file():
    probe = load_probe()
    assert select_pqa.STOP == probe.STOP
    assert (select_pqa.ND_LO, select_pqa.ND_HI) == (probe.ND_LO, probe.ND_HI)
    assert (select_pqa.CAP_LO, select_pqa.CAP_HI) == (probe.CAP_LO, probe.CAP_HI)
    assert select_pqa.PAIR_CAP == probe.PAIR_CAP
    for name in ("DYNAMIC_Q", "CARRIER_Q", "WARRANTY_TERM"):
        ours, theirs = getattr(select_pqa, name), getattr(probe, name)
        assert (ours.pattern, ours.flags) == (theirs.pattern, theirs.flags), name
    assert select_pqa.POLICY_Q.keys() == probe.POLICY_Q.keys()
    for kind, rx in probe.POLICY_Q.items():
        assert (select_pqa.POLICY_Q[kind].pattern, select_pqa.POLICY_Q[kind].flags) == (
            rx.pattern,
            rx.flags,
        )
    for text in ("Works with Windows 7?", "It's a 2-in-1, isn't it?", "", "USB-C 3.1 ports x2"):
        assert select_pqa.content_tokens(text) == probe.content_tokens(text)
    a, b = select_pqa.content_tokens("alpha bravo"), select_pqa.content_tokens("alpha charlie")
    assert select_pqa.jaccard(a, b) == probe.jaccard(a, b)


def test_the_probe_pins_are_the_recorded_numbers():
    """capped: probe_results.json's n_capped_nocarrier. adr002: ADR-002, re-derived 2026-10-20."""
    results = json.loads((PROBE_PY.parent / "probe_results.json").read_text(encoding="utf-8"))
    by_leaf = {r["file"][len("amazon_pqa_") : -len(".json")]: r for r in results}
    for leaf, pin in select_pqa.PROBE_PINS["capped"].items():
        assert pin == by_leaf[leaf]["n_capped_nocarrier"], leaf
    assert select_pqa.PROBE_PINS["adr002"] == {
        "unlocked_cell_phones": 1811,
        "traditional_laptops": 1312,
        "led_&_lcd_tvs": 302,
        "over-ear_headphones": 399,
        "chairs": 796,
        "home_office_desks": 339,
    }


def test_the_quota_is_38_per_department_split_evenly_over_its_leaves():
    by_dept = {}
    for spec in build_pqa.LEAVES:
        by_dept.setdefault(spec.department, []).append(spec.leaf)
    assert set(select_pqa.QUOTA) == {s.leaf for s in build_pqa.LEAVES}
    for leaves in by_dept.values():
        assert sum(select_pqa.QUOTA[leaf] for leaf in leaves) == select_pqa.DEPARTMENT_QUOTA
        assert len({select_pqa.QUOTA[leaf] for leaf in leaves}) == 1
    assert set(select_pqa.PROBE_PINS["capped"]) == set(select_pqa.QUOTA)


# =================================================================================================
# T7, T8: tags
# =================================================================================================
def tokens_of(**over):
    return select_pqa.record_tokens(line(**over))


def test_tag_order_a_price_question_that_says_warranty_is_dropped_not_policy():
    t = select_pqa.tag("What is the price of the extended warranty?", tokens_of(), GENERIC)
    assert t.kind == "dynamic"
    assert select_pqa.tag("Is the warranty unlocked?", tokens_of(), GENERIC).kind == "carrier"
    policy = select_pqa.tag("Can I return it under warranty?", tokens_of(), GENERIC)
    assert (policy.kind, policy.policy_kinds) == ("policy", ("return", "warranty"))


def test_r2_coverage_exactly_one_half_passes_and_just_below_fails():
    record = tokens_of()
    assert select_pqa.tag("alpha zulu", record, GENERIC).answerable  # 1 of 2
    assert not select_pqa.tag("alpha zulu yankee", record, GENERIC).answerable  # 1 of 3
    assert select_pqa.tag("alpha bravo zulu", record, GENERIC).answerable  # 2 of 3


def test_r2_an_all_generic_question_is_not_answerable():
    t = select_pqa.tag("Acme chair model?", tokens_of(), GENERIC)
    assert (t.kind, t.q_tokens, t.answerable) == ("spec", 0, False)
    assert t.answerable_r1  # R1 passes on the generic words alone: that is H1


def test_r1_and_r2_differ_on_the_product_noun_question():
    t = select_pqa.tag("How tall is the chair?", tokens_of(), GENERIC)
    assert t.answerable_r1 and not t.answerable


def test_the_department_word_does_not_make_a_question_answerable():
    t = select_pqa.tag("Is it furniture?", tokens_of(), GENERIC)
    assert not t.answerable and not t.answerable_r1


def test_title_only_marks_an_answer_covered_only_by_title_words():
    record = tokens_of(item_name="Acme Chair Model Ergonomic")
    t = select_pqa.tag("Is it ergonomic?", record, GENERIC)
    assert t.answerable and t.title_only
    assert not select_pqa.tag("Is it alpha?", record, GENERIC).title_only


# =================================================================================================
# T9, T20: the funnel
# =================================================================================================
def failure(**over):
    return select_pqa.evaluate(line(**over), GENERIC).failed


def questions(texts):
    return [
        {
            "line_no": n + 1,
            "question_id": f"q{n}",
            "question_text": q,
            "question_type": "yes-no",
            "answer_aggregated": "yes",
            "answers": [],
        }
        for n, q in enumerate(texts)
    ]


def test_a_default_line_is_eligible():
    assert failure() is None


def test_bullets_three_pass_and_two_fail():
    assert failure(bullets=["alpha bravo", "charlie delta", "echo foxtrot", "", ""]) is None
    assert failure(bullets=["alpha bravo", "charlie delta", "   ", "", ""]) == "bullets"


def test_a_warranty_term_in_the_title_or_the_prose_fails():
    assert failure(item_name="Acme Chair Model 3 year warranty") == "no_warranty_term"
    assert failure(product_description="Backed by a two year warranty.") == "no_warranty_term"
    # The probe's regex needs a number AND a unit: "lifetime warranty" alone is not a term.
    assert failure(product_description="Backed by a lifetime warranty.") is None


def test_a_conflicted_product_fails_consistent():
    assert failure(fields_conflict=True) == "consistent"


def test_kept_questions_five_to_fifty():
    five = (*ANSWERABLE[:2], *ANSWERABLE[2:5])  # 5 answerable, the pair included
    assert failure(questions=questions(five)) is None
    assert failure(questions=questions(ANSWERABLE[:4])) == "cap"
    extra = [f"zulu number {n:02d}" for n in range(51 - len(ANSWERABLE))]
    assert failure(questions=questions([*ANSWERABLE, *extra[:-1]])) is None  # 50 kept
    assert failure(questions=questions([*ANSWERABLE, *extra])) == "cap"  # 51 kept


def test_dropped_questions_do_not_count_as_kept():
    texts = [*ANSWERABLE[:4], DYNAMIC, CARRIER]
    assert failure(questions=questions(texts)) == "cap"


def test_answerable_five_pass_and_four_fail():
    assert failure(questions=questions([*ANSWERABLE[:5], *UNANSWERABLE])) is None
    assert failure(questions=questions([*ANSWERABLE[:4], *UNANSWERABLE, POLICY])) == "answerable"


def test_the_pair_must_be_among_answerable_questions():
    no_pair = [ANSWERABLE[i] for i in (0, 2, 3, 4, 5)]
    texts = [*no_pair, "Does it have zulu yankee?", "Does it have zulu yankee xray?"]
    assert failure(questions=questions(texts)) == "pair"


def test_an_interim_line_without_the_flag_raises_whatever_it_would_fail():
    bad = line(item_name="")  # would fail `titled` first
    del bad["fields_conflict"]
    with pytest.raises(KeyError):
        select_pqa.evaluate(bad, GENERIC)
    with pytest.raises(select_pqa.SelectionStop):
        select_pqa.evaluate(line(fields_conflict=1), GENERIC)


def test_the_funnel_adds_up_and_counts_each_step_once(world):
    assert run(world) == 0
    f = selection(world)["funnel"]["chairs"]
    assert f["products_in"] == 10
    assert f["removed"] == {step: 1 for step in select_pqa.STEPS}
    assert f["eligible"] == 3 and f["selected"] == 2
    assert f["products_in"] == sum(f["removed"].values()) + f["eligible"]
    assert f["questions_dropped"] == {"dynamic": 7, "carrier": 7}  # products 1-7 carry both
    assert selection(world)["probe_pools"] == {
        "chairs": {"capped": 9, "adr002": 8},
        "desks": {"capped": 2, "adr002": 2},
    }


# =================================================================================================
# T10, T11: the draw
# =================================================================================================
def test_the_draw_takes_exactly_the_quota_by_hash_rank():
    eligible = {"x": [asin(n) for n in range(10)], "y": [asin(n) for n in range(10, 15)]}
    chosen = select_pqa.draw(eligible, {"x": 3, "y": 5})
    assert [len(chosen["x"]), len(chosen["y"])] == [3, 5]
    assert chosen["x"] == sorted(eligible["x"], key=select_pqa.rank)[:3]


def test_a_short_pool_stops_and_names_the_leaf():
    with pytest.raises(select_pqa.SelectionStop, match="y"):
        select_pqa.draw({"x": [asin(1), asin(2)], "y": [asin(3)]}, {"x": 1, "y": 2})


def test_a_short_pool_exits_2_through_select(world, capsys):
    assert run(world, quota={"chairs": 4, "desks": 2}) == 2
    err = capsys.readouterr().err
    assert "chairs: 3 eligible, quota 4" in err
    assert not world["selection_path"].exists()


def test_removing_one_product_does_not_reorder_the_others():
    pool = [asin(n) for n in range(40)]
    order = sorted(pool, key=select_pqa.rank)
    for gone in (order[0], order[7], order[-1]):
        assert sorted([a for a in pool if a != gone], key=select_pqa.rank) == [
            a for a in order if a != gone
        ]


# =================================================================================================
# T1, T2, T16, T17, T18: stops and clean-up
# =================================================================================================
def assert_nothing_published(world):
    d = world["draft_dir"]
    assert not world["selection_path"].exists()
    for name in (select_pqa.PRODUCTS, select_pqa.POOL, select_pqa.GENERIC):
        assert not (d / name).exists()
    assert not [p.name for p in d.iterdir() if p.name.startswith(select_pqa.TEMP_PREFIX)]


def test_a_stale_product_file_stops_the_run(world, capsys):
    (world["draft_dir"] / "product-x.json").write_text("{}", encoding="utf-8")
    assert run(world) == 2
    assert "product-*.json" in capsys.readouterr().err
    assert_nothing_published(world)


def test_an_interim_changed_after_its_manifest_stops_the_run(world):
    path = world["interim_dir"] / "chairs.jsonl"
    path.write_bytes(path.read_bytes() + b"\n")
    assert run(world) == 2
    assert_nothing_published(world)


def test_probe_pins_that_do_not_reproduce_stop_before_the_draw(world, capsys):
    pins = {"capped": {"chairs": 9, "desks": 2}, "adr002": {"chairs": 7, "desks": 2}}
    assert run(world, pins=pins) == 2
    err = capsys.readouterr().err
    assert "chairs: probe pool adr002 = 8, pinned 7" in err
    assert_nothing_published(world)


def test_an_interim_changed_during_the_pass_stops_before_anything_is_written(
    world, monkeypatch
):
    real = build_pqa.iter_interim
    calls = []

    def changing(manifest_path, interim_dir):
        calls.append(1)
        yield from real(manifest_path, interim_dir)
        if len(calls) == 2:  # after the last line of pass 2
            path = interim_dir / "desks.jsonl"
            path.write_bytes(path.read_bytes() + b"\n")

    monkeypatch.setattr(build_pqa, "iter_interim", changing)
    assert run(world) == 2
    assert_nothing_published(world)


def test_a_manifest_changed_during_the_pass_stops(world, monkeypatch, capsys):
    real = build_pqa.iter_interim
    calls = []

    def changing(manifest_path, interim_dir):
        calls.append(1)
        yield from real(manifest_path, interim_dir)
        if len(calls) == 2:
            manifest_path.write_bytes(manifest_path.read_bytes() + b" ")

    monkeypatch.setattr(build_pqa, "iter_interim", changing)
    assert run(world) == 2
    assert "changed while" in capsys.readouterr().err


def test_temp_directories_are_removed_and_3_1_s_are_left_alone(world):
    d = world["draft_dir"]
    (d / ".pqa-build-77").mkdir()
    (d / f"{select_pqa.TEMP_PREFIX}old-5").mkdir()  # the leftover of a crashed 3.2 run
    assert run(world) == 0
    names = sorted(p.name for p in d.iterdir())
    assert ".pqa-build-77" in names
    assert not [n for n in names if n.startswith(select_pqa.TEMP_PREFIX)]
    assert run(world, pins={"capped": {"chairs": 0}, "adr002": {}}) == 2
    assert not [p for p in d.iterdir() if p.name.startswith(select_pqa.TEMP_PREFIX)]


# =================================================================================================
# T3, T4, T5, T6, T13: the outputs
# =================================================================================================
def test_records_have_the_ingest_shape_and_no_leaf(world):
    assert run(world) == 0
    from rag.ingest import load_records

    records = load_records(world["draft_dir"] / "products")
    assert len(records) == 4
    leaves = {"chairs", "desks"}
    for r in records:
        assert r["doc_id"].startswith("product-furniture-b0000000")
        assert list(r) == ["doc_id", "title", "category", "specs"]
        assert r["category"] == "furniture"
        values = [r["doc_id"], r["title"], r["category"], *r["specs"], *r["specs"].values()]
        assert not leaves & set(values)


def test_an_asin_that_is_not_ten_upper_case_characters_is_refused():
    with pytest.raises(select_pqa.SelectionStop):
        select_pqa.doc_id_of(line(asin="b000000001"))
    with pytest.raises(select_pqa.SelectionStop):
        select_pqa.doc_id_of(line(asin="B00000001"))
    assert select_pqa.doc_id_of(line()) == "product-furniture-b000000001"


def test_specs_keep_their_source_order_through_the_embedded_text(world):
    from rag.ingest import product_to_text

    record = select_pqa.product_record(
        line(bullets=["one", "", "three", "  ", "five"], product_description="desc", brand_name="B")
    )
    assert list(record["specs"]) == ["Feature 1", "Feature 3", "Feature 5", "Description", "Brand"]
    assert product_to_text(record) == (
        "Product: Acme Chair Model\nCategory: furniture\nSpecs:\n- Feature 1: one\n"
        "- Feature 3: three\n- Feature 5: five\n- Description: desc\n- Brand: B"
    )
    assert run(world) == 0
    written = next((world["draft_dir"] / "products").iterdir())
    specs = json.loads(written.read_text(encoding="utf-8"))["specs"]
    assert list(specs) == [*(f"Feature {n}" for n in range(1, 6)), "Description", "Brand"]


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def test_every_string_in_the_selection_manifest_is_on_the_allow_list(world):
    assert run(world) == 0
    data = world["selection_path"].read_bytes()
    allowed = {
        select_pqa.STAGE,
        select_pqa.NOTE,
        select_pqa.SEED,
        "furniture",
        "1/2",
        "1/10",
        "0.45",
        "0.99",
        *select_pqa.STEPS,
        select_pqa.DYNAMIC_Q.pattern,
        select_pqa.CARRIER_Q.pattern,
        select_pqa.WARRANTY_TERM.pattern,
        *(rx.pattern for rx in select_pqa.POLICY_Q.values()),
    }
    for s in _strings(json.loads(data)):
        is_digest = len(s) == 64 and set(s) <= set("0123456789abcdef")
        assert is_digest or s in allowed, s
    for n in range(1, 13):
        assert asin(n).encode() not in data and asin(n).lower().encode() not in data
    assert b"alpha" not in data and b"Acme" not in data


def test_no_dropped_question_reaches_the_pool(world):
    assert run(world) == 0
    pool = [json.loads(x) for x in (world["draft_dir"] / select_pqa.POOL).read_text().splitlines()]
    assert len(pool) == 4 * 9
    assert {q["tag"] for q in pool} == {"spec", "policy"}
    texts = {q["question_text"] for q in pool}
    assert DYNAMIC not in texts and CARRIER not in texts
    policy = [q for q in pool if q["tag"] == "policy"]
    assert all(q["answerable"] is None and q["policy_kinds"] == ["return"] for q in policy)
    assert pool == sorted(pool, key=lambda q: (q["doc_id"], q["line_no"]))


DRIVER = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import select_pqa
args = json.loads(Path(sys.argv[2]).read_text())
code = select_pqa.select(
    Path(args["manifest"]), Path(args["interim"]), Path(args["draft"]), Path(args["selection"]),
    quota=args["quota"], pins=args["pins"],
    chunker=lambda r: (len(r["title"]), 1),
)
sys.exit(code)
"""


def test_two_runs_under_different_hash_seeds_are_byte_identical(tmp_path):
    scripts = str(Path(select_pqa.__file__).parent)
    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER, encoding="utf-8")
    results = []
    for seed in ("0", "1"):
        root = tmp_path / f"seed{seed}"
        manifest, interim = write_interim(
            root,
            {"chairs": ("furniture", chairs_records()), "desks": ("furniture", desks_records())},
        )
        args = {
            "manifest": str(manifest),
            "interim": str(interim),
            "draft": str(root / "v1-draft"),
            "selection": str(root / "pqa-selection.json"),
            "quota": QUOTA,
            "pins": PINS,
        }
        (root / "args.json").write_text(json.dumps(args), encoding="utf-8")
        env = {**os.environ, "PYTHONHASHSEED": seed}
        subprocess.run(
            [sys.executable, str(driver), scripts, str(root / "args.json")],
            check=True,
            env=env,
            capture_output=True,
        )
        world = {"draft_dir": root / "v1-draft", "selection_path": root / "pqa-selection.json"}
        results.append(outputs_of(world))
    assert results[0] == results[1]
    assert len(results[0]["products"]) == 4  # not vacuous


def test_the_real_chunker_measures_a_record_as_ingest_would():
    measure = select_pqa.default_chunker()
    chars, chunks = measure(select_pqa.product_record(line()))
    assert chars > 0 and chunks >= 1


# =================================================================================================
# T14: re-asks
# =================================================================================================
def test_reasks_are_counted_in_two_parts_and_digit_flips_apart():
    r = select_pqa.ReAsk()
    r.add(
        [
            "works with windows 7",
            "works with windows 8",  # the same token set: "7" and "8" are one character
            "alpha bravo charlie",
            "alpha bravo charlie delta",  # Jaccard 3/4: a near-duplicate
            "zulu",
        ]
    )
    assert r.as_dict() == {
        "questions": 5,
        "clusters_exact": 4,
        "clusters_all": 3,
        "digit_flips": 1,
    }


# =================================================================================================
# T19: the sanctioned reader, and the swap
# =================================================================================================
def test_iter_selection_yields_everything_after_hashing(world):
    assert run(world) == 0
    items = list(select_pqa.iter_selection(world["selection_path"], world["draft_dir"]))
    assert [k for k, _ in items].count("product") == 4
    assert [k for k, _ in items].count("question") == 36


@pytest.mark.parametrize("damage", ["change", "remove", "extra", "pool"])
def test_iter_selection_refuses_changed_outputs_before_yielding(world, damage):
    assert run(world) == 0
    d = world["draft_dir"]
    first = min((d / "products").iterdir())
    if damage == "change":
        first.write_bytes(first.read_bytes() + b" ")
    elif damage == "remove":
        first.unlink()
    elif damage == "extra":
        (d / "products" / "product-furniture-zzzzzzzzzz.json").write_text("{}", encoding="utf-8")
    else:
        pool = d / select_pqa.POOL
        pool.write_bytes(pool.read_bytes()[:-1])
    with pytest.raises(select_pqa.SelectionMismatch):
        next(select_pqa.iter_selection(world["selection_path"], d))


def test_a_failed_swap_restores_the_previous_outputs(world, monkeypatch):
    assert run(world) == 0
    before = outputs_of(world)
    real = os.replace

    def failing(src, dst):
        if Path(dst) == world["selection_path"]:
            raise OSError("disk full")
        real(src, dst)

    monkeypatch.setattr(select_pqa.os, "replace", failing)
    with pytest.raises(OSError, match="disk full"):
        run(world, quota={"chairs": 1, "desks": 2})  # a different selection: 3 products
    assert outputs_of(world) == before
    assert not [
        p for p in world["draft_dir"].iterdir() if p.name.startswith(select_pqa.TEMP_PREFIX)
    ]


# =================================================================================================
# T21: the blind audit
# =================================================================================================
def synthetic_pool():
    pool = []
    for dept in ("alpha", "bravo"):
        for n in range(30):
            pool.append(
                {"doc_id": f"product-{dept}-x", "line_no": n, "department": dept, "tag": "spec",
                 "answerable": n < 18}
            )
        pool.append({"doc_id": f"product-{dept}-x", "line_no": 99, "department": dept,
                     "tag": "policy", "answerable": None})
    return pool


def test_the_audit_sample_is_fifteen_and_ten_per_department_in_a_fixed_order():
    sample = select_pqa.audit_sample(synthetic_pool())
    assert len(sample) == 50
    for dept in ("alpha", "bravo"):
        mine = [q for q in sample if q["department"] == dept]
        assert sum(q["answerable"] for q in mine) == 15
        assert sum(not q["answerable"] for q in mine) == 10
    assert sample == select_pqa.audit_sample(list(reversed(synthetic_pool())))
    ranks = [select_pqa.audit_rank(q["doc_id"], q["line_no"]) for q in sample]
    assert ranks == sorted(ranks)


def test_an_audit_group_too_small_stops():
    pool = [q for q in synthetic_pool() if q["answerable"] is not False][:20]
    with pytest.raises(select_pqa.SelectionStop):
        select_pqa.audit_sample(pool)


def test_the_audit_sheet_has_no_tag_and_scores_from_the_marks(world, monkeypatch, tmp_path):
    monkeypatch.setattr(select_pqa, "AUDIT_ANSWERABLE", 3)
    monkeypatch.setattr(select_pqa, "AUDIT_UNANSWERABLE", 2)
    assert run(world) == 0
    sheet = world["draft_dir"] / select_pqa.AUDIT_SHEET
    assert select_pqa.write_audit_sheet(world["selection_path"], world["draft_dir"], sheet) == 0
    first = sheet.read_bytes()
    assert select_pqa.write_audit_sheet(world["selection_path"], world["draft_dir"], sheet) == 0
    assert sheet.read_bytes() == first  # the same seed gives the same sheet
    with sheet.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert tuple(rows[0]) == select_pqa.SHEET_COLUMNS
    assert len(rows) == 5 and all(r["answerable"] == "" for r in rows)
    out = tmp_path / "audit.json"
    assert select_pqa.score_audit(world["selection_path"], world["draft_dir"], sheet, out) == 2
    for r in rows:
        r["answerable"] = "yes" if "zulu" not in r["question"] and "tall" not in r["question"] else "no"
    with sheet.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=select_pqa.SHEET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    assert select_pqa.score_audit(world["selection_path"], world["draft_dir"], sheet, out) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["pooled"] == {"tp": 3, "fp": 0, "fn": 0, "tn": 2}
    assert result["precision"]["k"] == 3 and result["precision"]["n"] == 3


def test_wilson_matches_a_hand_computed_interval():
    assert select_pqa.wilson(0, 0) is None
    assert select_pqa.wilson(10, 10) == [0.7225, 1.0]
    low, high = select_pqa.wilson(5, 10)
    assert (low, high) == (0.2366, 0.7634)
