"""Item 5.2 (docs/work/2026-11-11-labelling-ablation/design.md): the labelling ablation.

The pure half first: the frame and its two exclusions, the draw, the evidence rule, the blind sheet and its
parser, and the scores (agreement, Cohen's kappa, Wilson, the circularity rule) against hand-computed
values. The commands follow, against a fake Ollama and a temp folder.

No Ollama, no Redis, no network.
"""

import hashlib
import json
import random
from pathlib import Path

import judge
import label_ablation as la
import pytest
import select_pqa
import yaml

ROOT = Path(__file__).resolve().parents[2]


# =================================================================================================
# The frame (DC 3)
# =================================================================================================
def raw(request_id, cache, product, entry, overlap=None, query=None):
    r = {
        "request_id": request_id,
        "cache": cache,
        "entry_id": entry,
        "answer_sha256": "a" * 64,
        "query_raw": query or f"question of {request_id}",
        "source_overlap": overlap,
    }
    if product:
        r["product_id"] = product
    return r


def verdict_row(request_id, key, answerable=True):
    return {
        "request_id": request_id,
        "verdict_key": key,
        "qa_id": f"qa-{request_id}",
        "stratum": "A",
        "answerable": answerable,
        "judge_version": "judge-v1",
    }


def frame_fixture():
    """Six records: two MISSes, a MISS with no product_id, a hit on its own product's entry (overlap 1),
    a hit on another product's entry, and a hit below 1.0."""
    records = [
        raw("r1", "MISS", "P1", "E1"),
        raw("r2", "MISS", "P2", "E2"),
        raw("r3", "MISS", None, "E3"),
        raw("r4", "TIER2_HIT", "P1", "E1", overlap=1),
        raw("r5", "TIER2_HIT", "P3", "E2", overlap=1.0),
        raw("r6", "TIER2_HIT", "P2", "E2", overlap=0.7),
    ]
    judged = [verdict_row(r["request_id"], f"key-{r['request_id']}") for r in records]
    return records, judged


def test_frame_excludes_no_product_and_cross_product_hits():
    records, judged = frame_fixture()

    rows, excluded = la.frame(records, judged)

    assert excluded == {"no_product_id": 1, "cross_product_hit": 1}
    assert [r["request_id"] for r in rows] == ["r1", "r2", "r4", "r6"]
    by_id = {r["request_id"]: r for r in rows}
    assert by_id["r1"]["stratum"] == "MISS" and by_id["r1"]["bucket"] == "generated"
    assert by_id["r1"]["source_overlap"] is None
    assert by_id["r4"]["stratum"] == "hit" and by_id["r4"]["bucket"] == "1.0"
    assert by_id["r4"]["source_overlap"] == 1.0
    assert by_id["r6"]["bucket"] == "[0.6, 0.8)"


def test_frame_has_one_row_per_distinct_verdict_key():
    records, judged = frame_fixture()
    judged[3]["verdict_key"] = judged[0]["verdict_key"]  # r4 shares r1's key

    rows, _ = la.frame(records, judged)

    assert [r["request_id"] for r in rows] == [
        "r1",
        "r2",
        "r6",
    ]  # the first record wins


def test_frame_stops_on_a_record_that_is_not_a_miss_or_a_tier2_hit():
    records, judged = frame_fixture()
    records.append(raw("r7", "TIER1_HIT", "P1", "E1"))
    judged.append(verdict_row("r7", "key-r7"))

    with pytest.raises(la.AblationRefused, match="r7"):
        la.frame(records, judged)


def test_frame_stops_on_a_hit_whose_entry_has_no_miss():
    records, judged = frame_fixture()
    records.append(raw("r7", "TIER2_HIT", "P1", "E9", overlap=1))
    judged.append(verdict_row("r7", "key-r7"))

    with pytest.raises(la.AblationRefused, match="no MISS"):
        la.frame(records, judged)


@pytest.mark.parametrize(
    "overlap, bucket",
    [
        (1, "1.0"),
        (1.0, "1.0"),
        (0.9999, "[0.8, 1)"),
        (0.8, "[0.8, 1)"),
        (0.7999, "[0.6, 0.8)"),
        (0.6, "[0.6, 0.8)"),
        (0.5999, "below 0.6"),
        (0.0, "below 0.6"),
    ],
)
def test_hit_bucket_edges(overlap, bucket):
    assert la.hit_bucket(overlap) == bucket


# =================================================================================================
# The draw (DC 3)
# =================================================================================================
def draw_frame():
    rows = []
    for i in range(10):
        rows.append(
            {"verdict_key": f"h{i:02d}", "stratum": "hit", "bucket": "1.0", "n": i}
        )
    for i in range(30):
        rows.append(
            {"verdict_key": f"m{i:02d}", "stratum": "MISS", "bucket": "generated"}
        )
    random.Random(1).shuffle(rows)  # the draw must not depend on the frame's order
    return rows


def test_draw_takes_every_hit_and_n_misses_by_seed():
    rows = draw_frame()

    first = la.draw(rows, 7, 5)
    second = la.draw(list(reversed(rows)), 7, 5)

    assert first == second
    hits = [r for r in first if r["stratum"] == "hit"]
    misses = [r for r in first if r["stratum"] == "MISS"]
    assert len(hits) == 10 and {r["verdict_key"] for r in hits} == {
        f"h{i:02d}" for i in range(10)
    }
    assert len(misses) == 7
    # Entry 5: random.Random(seed).sample over the MISS keys sorted by verdict key
    sorted_miss = sorted(r["verdict_key"] for r in rows if r["stratum"] == "MISS")
    want = sorted(random.Random(5).sample(sorted_miss, 7))
    assert [r["verdict_key"] for r in misses] == want
    assert [r["stratum"] for r in first] == ["hit"] * 10 + ["MISS"] * 7


def test_draw_with_another_seed_takes_other_misses():
    rows = draw_frame()

    a = {r["verdict_key"] for r in la.draw(rows, 7, 5) if r["stratum"] == "MISS"}
    b = {r["verdict_key"] for r in la.draw(rows, 7, 6) if r["stratum"] == "MISS"}

    assert a != b


def test_draw_stops_when_there_are_fewer_misses_than_asked():
    with pytest.raises(la.AblationRefused):
        la.draw(draw_frame(), 31, 5)


# =================================================================================================
# The evidence rule (DC 5)
# =================================================================================================
def test_evidence_is_the_reference_chunk_list():
    texts = {"d1#chunk-0": "first", "d1#chunk-1": "second", "d2#chunk-0": "third"}
    row = {"chunk_ids": ["d2#chunk-0", "d1#chunk-0", "d1#chunk-1"]}

    assert la.evidence(row, texts) == "third\n\nfirst\n\nsecond"


def test_evidence_stops_on_a_chunk_the_corpus_does_not_have():
    with pytest.raises(KeyError):
        la.evidence({"chunk_ids": ["nope#chunk-0"]}, {})


# =================================================================================================
# The blind sheet (DC 4)
# =================================================================================================
QUESTION_MARK = "QMARK-where-is-it"
ANSWER_MARK = "AMARK-it-is-here"
CHUNK_MARK = "CMARK-the-documents-say"
REFERENCE_MARK = "RMARK-the-reference-says"


def sheet_items(n=5):
    return [
        {
            "item": i,
            "verdict_key": f"key-{i}",
            "question": f"{QUESTION_MARK} {i}?",
            "product_id": f"product-{i}",
            "chunks": [(f"doc-{i}#chunk-0", f"{CHUNK_MARK} {i}.")],
            "answer": f"{ANSWER_MARK} {i}.",
            # none of the fields below may reach the first sheet
            "reference": f"{REFERENCE_MARK} {i}.",
            "verdict": "INCORRECT",
            "cache": "TIER2_HIT",
            "stratum": "hit",
            "source_overlap": 0.5,
        }
        for i in range(1, n + 1)
    ]


def test_sheet_hides_what_the_author_must_not_see(tmp_path):
    out = tmp_path / "sheet.md"

    la.write_sheet(sheet_items(), out, "2026-11-11T09:00:00+00:00")

    text = out.read_text()
    body = text[text.index("## Item 1") :]
    # what is shown
    for needle in (
        QUESTION_MARK,
        ANSWER_MARK,
        CHUNK_MARK,
        "product-1",
        "doc-1#chunk-0",
    ):
        assert needle in text
    # the reference is not on the first sheet
    assert REFERENCE_MARK not in text
    # no verdict word outside the rubric header
    assert "CORRECT" not in body and "INCORRECT" not in body
    assert (
        "CORRECT" in text[: text.index("## Item 1")]
    )  # the header restates the rubric
    for word in ("cache", "overlap", "stratum", "similarity"):
        assert word not in text.lower(), word
    for word in ("TIER2_HIT", "MISS"):
        assert word not in text, word


def test_sheet_is_written_once(tmp_path):
    out = tmp_path / "sheet.md"
    la.write_sheet(sheet_items(2), out, "2026-11-11T09:00:00+00:00")

    with pytest.raises(la.AblationRefused, match="exists"):
        la.write_sheet(sheet_items(2), out, "2026-11-11T09:00:00+00:00")


def fill(text, label_of_item):
    """Write `label_of_item[n]` on the `label:` line of item n."""
    out, current = [], None
    for line in text.splitlines():
        m = la.ITEM.match(line)
        if m:
            current = int(m.group(1))
        if line == "label:":
            line = f"label: {label_of_item[current]}"
        out.append(line)
    return "\n".join(out) + "\n"


def test_labels_round_trip_to_their_keys(tmp_path):
    items = sheet_items(6)
    # the shuffle: items are numbered in a seeded random order, so item n is not key n
    random.Random(3).shuffle(items)
    for n, item in enumerate(items, 1):
        item["item"] = n
    out = tmp_path / "sheet.md"
    la.write_sheet(items, out, "2026-11-11T09:00:00+00:00")
    words = ["correct", "incorrect", "unsure"]
    chosen = {it["verdict_key"]: words[i % 3] for i, it in enumerate(items)}
    by_item = {it["item"]: chosen[it["verdict_key"]] for it in items}

    parsed = la.parse_sheet(fill(out.read_text(), by_item))

    assert len(parsed) == 6
    for item in items:
        assert parsed[item["item"]] == chosen[item["verdict_key"]]


def test_an_unfilled_sheet_reads_as_unmarked(tmp_path):
    out = tmp_path / "sheet.md"
    la.write_sheet(sheet_items(3), out, "2026-11-11T09:00:00+00:00")

    assert la.parse_sheet(out.read_text()) == {1: "", 2: "", 3: ""}


@pytest.mark.parametrize(
    "line, want",
    [
        ("label: correct", "correct"),
        ("label:   Incorrect  ", "incorrect"),
        ("label: UNSURE", "unsure"),
        ("label: correct, I think", ""),  # more than one word: not a mark
        ("label:", ""),
    ],
)
def test_parse_sheet_reads_one_word_after_label(line, want):
    text = f"## Item 1\n\nsome text\n\n{line}\n"

    assert la.parse_sheet(text) == {1: want}


def test_parse_sheet_stops_on_a_repeated_item():
    with pytest.raises(la.AblationRefused, match="twice"):
        la.parse_sheet("## Item 1\nlabel: correct\n## Item 1\nlabel: correct\n")


@pytest.mark.parametrize(
    "line", ["label: correct", "## Item 9", "reference right: yes"]
)
def test_sheet_refuses_a_text_line_that_looks_like_a_field(tmp_path, line):
    items = sheet_items(2)
    items[1]["answer"] = f"The answer.\n{line}\nMore."

    with pytest.raises(la.AblationRefused, match="sheet field"):
        la.write_sheet(items, tmp_path / "sheet.md", "2026-11-11T09:00:00+00:00")


def test_refsheet_shows_the_reference_and_the_locked_label(tmp_path):
    items = sheet_items(2)
    for item in items:
        item["label"] = "incorrect"
    out = tmp_path / "refsheet.md"

    la.write_refsheet(items, out, "2026-11-11T09:00:00+00:00")

    text = out.read_text()
    assert REFERENCE_MARK in text and "author label: incorrect" in text
    assert la.parse_refsheet(text) == {1: "", 2: ""}
    assert la.parse_refsheet(
        text.replace("reference right:\n", "reference right: No\n")
    ) == {
        1: "no",
        2: "no",
    }


# =================================================================================================
# The scores (DC 7), against hand-computed values
# =================================================================================================
def table(cc, ii, ic, ci):
    """Pairs `(judge, author)`: cc both CORRECT, ii both INCORRECT, ic judge INCORRECT / author CORRECT,
    ci judge CORRECT / author INCORRECT."""
    return (
        [("CORRECT", "CORRECT")] * cc
        + [("INCORRECT", "INCORRECT")] * ii
        + [("INCORRECT", "CORRECT")] * ic
        + [("CORRECT", "INCORRECT")] * ci
    )


def test_agreement_kappa_recall_precision_by_hand():
    pairs = table(40, 10, 5, 5)

    got = la.agreement(pairs)

    assert (got["k"], got["n"]) == (50, 60)
    assert got["wilson95"] == [0.7197, 0.9069]
    assert got["kappa"] == 0.5556  # (50/60 - 0.625) / (1 - 0.625) = 5/9
    assert (got["recall"]["k"], got["recall"]["n"]) == (10, 15)
    assert got["recall"]["wilson95"] == [0.4171, 0.8482]
    assert (got["precision"]["k"], got["precision"]["n"]) == (10, 15)
    assert got["precision"]["wilson95"] == [0.4171, 0.8482]
    assert got["undecided"] == 0
    # Wilson is the module the rest of the project uses
    assert got["wilson95"] == select_pqa.wilson(50, 60)


def test_kappa_is_none_when_both_sides_use_one_label():
    pairs = table(5, 0, 0, 0)

    assert la.kappa(pairs) is None
    assert la.agreement(pairs)["k"] == 5
    assert la.kappa(table(0, 0, 0, 0)) is None  # no decided pair


def test_kappa_of_two_judges_that_always_disagree_is_negative():
    assert la.kappa(table(0, 0, 5, 5)) == -1.0


def test_unsure_and_unparsed_pairs_leave_the_denominators():
    pairs = table(40, 10, 5, 5) + [
        ("UNPARSED", "CORRECT"),
        ("CORRECT", "UNSURE"),
        ("INCORRECT", "UNSURE"),
    ]

    got = la.agreement(pairs)

    assert (got["k"], got["n"]) == (50, 60)
    assert got["undecided"] == 3
    assert got["kappa"] == 0.5556
    assert (got["recall"]["n"], got["precision"]["n"]) == (15, 15)


def test_agreement_of_no_pairs_has_no_rate_and_no_interval():
    got = la.agreement([])

    assert got["n"] == 0 and got["rate"] is None and got["wilson95"] is None
    assert got["kappa"] is None


def test_circularity_rule():
    # A0 8/10: Wilson [0.4902, 0.9433] holds A1 = 0.9
    bounded = la.circularity(la._rate(9, 10), la._rate(8, 10))
    # A0 3/10: Wilson [0.1078, 0.6032] does not hold 0.9
    quantified = la.circularity(la._rate(9, 10), la._rate(3, 10))

    assert bounded["result"] == "bounded" and bounded["inflation"] is None
    assert quantified["result"] == "quantified"
    assert quantified["inflation"] == 0.6
    assert (quantified["n_a1"], quantified["n_a0"]) == (10, 10)


def test_circularity_is_bounded_when_a0_is_at_least_a1():
    got = la.circularity(la._rate(9, 10), la._rate(10, 10))

    assert got["result"] == "bounded"


def test_circularity_is_undefined_without_pairs():
    assert la.circularity(la._rate(9, 10), la._rate(0, 0))["result"] == "undefined"
    assert la.circularity(la._rate(0, 0), la._rate(9, 10))["result"] == "undefined"


def test_disagreements_are_the_decided_ones():
    labels = {
        "a": "correct",
        "b": "incorrect",
        "c": "unsure",
        "d": "correct",
        "e": "incorrect",
    }
    verdicts = {
        "a": "INCORRECT",  # decided, differs: yes
        "b": "INCORRECT",  # agrees
        "c": "INCORRECT",  # the author is unsure: not a disagreement
        "d": "UNPARSED",  # the judge is undecided: not a disagreement
        "e": "CORRECT",  # decided, differs: yes
    }

    assert la.disagreements(labels, verdicts, ["e", "d", "c", "b", "a"]) == ["e", "a"]


# =================================================================================================
# Entry 5 comes first (DC 1)
# =================================================================================================
PREREG = "# Pre-registration\n\n## Entry 5 — 2026-11-11 05:41Z — the labelling ablation (item 5.2)\n"


def test_entry5_end_is_the_first_instant_after_its_minute():
    assert la.entry5_end(PREREG).isoformat() == "2026-11-11T05:42:00+00:00"


def test_a_written_at_in_entry5s_minute_or_before_is_late():
    late = la.check_entry5_first(
        PREREG,
        {
            "draw.json": "2026-11-11T05:41:30+00:00",
            "sheet": "2026-11-11T05:00:00+00:00",
            "rf.json": "2026-11-11T05:42:00+00:00",
        },
    )

    assert len(late) == 2
    assert any("draw.json" in m for m in late) and any("sheet" in m for m in late)


def test_entry5_missing_is_a_refusal():
    with pytest.raises(la.AblationRefused, match="Entry 5"):
        la.entry5_end("# Pre-registration\n\n## Entry 4 — 2026-11-01 — x\n")


def test_the_real_preregistration_has_entry_5_with_a_time():
    text = (ROOT / "docs" / "preregistration.md").read_text()

    assert la.entry5_end(text).year == 2026


# =================================================================================================
# The commands, against a fake Ollama and a temp folder
# =================================================================================================
# A small world on disk: a finished run (10 MISS records, 4 hits, a MISS with no product_id and a hit on
# another product's entry), its judge output, a reference set, the two judge records and a
# pre-registration that holds the reference-free record's hash. Every text carries a marker so a test can
# search for it.
RUN = "2026-11-01T00-00-00_cfg4_fixture"
NOW = "2026-11-11T09:00:00+00:00"
ENTRY_5 = "## Entry 5 — 2026-11-11 05:41Z — the labelling ablation (item 5.2)"
ENTRY_6 = "## Entry 6 — 2026-11-11 06:37Z — the labelling ablation after the sanity failure (item 5.2)"
MODEL, DIGEST = "judge-m:1b", "d" * 64
GENERATOR = "gen-m:2b"
OPTIONS = {"temperature": 0, "seed": 1, "num_ctx": 4096, "num_predict": 8}
PROMPT_V1 = "Q::{question}\nR::{reference}\nA::{answer}\n"
PROMPT_RF = "Q::{question}\nE::{evidence}\nA::{answer}\n"
V1_CYCLE = ["CORRECT", "INCORRECT", "CORRECT", "CORRECT", "INCORRECT"]
N_MISS_FIXTURE = 5


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_jsonl(path):
    return [
        json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()
    ]


class World:
    def __init__(self, root, entry=ENTRY_5):
        self.root = root
        self.results = root / "results"
        self.run_dir = self.results / RUN
        self.adir = self.run_dir / "ablation"
        self.refs_dir = root / "refs" / "validation"
        self.judge_dir = root / "judge"
        self.prereg = root / "preregistration.md"
        self.sheet = root / "private" / "sheet.md"
        self.refsheet = root / "private" / "refsheet.md"
        self.texts = {}
        self.question_of = {}  # verdict key -> question
        self.v1_of = {}  # verdict key -> the verdict judge-v1 gave
        self._build(entry)

    # -- building ------------------------------------------------------------------------------
    def _build(self, entry):
        self.judge_dir.mkdir(parents=True)
        for name, prompt in (
            ("prompt-v1.txt", PROMPT_V1),
            ("prompt-rf-v1.txt", PROMPT_RF),
        ):
            (self.judge_dir / name).write_text(prompt)
        for version, prompt_file, prompt in (
            ("judge-v1", "prompt-v1.txt", PROMPT_V1),
            ("judge-rf-v1", "prompt-rf-v1.txt", PROMPT_RF),
        ):
            cfg = {
                "version": version,
                "model": MODEL,
                "digest": DIGEST,
                "prompt_file": prompt_file,
                "prompt_sha256": sha(prompt),
                "options": dict(OPTIONS),
            }
            (self.judge_dir / f"{version}.json").write_text(
                json.dumps(cfg, indent=2) + "\n"
            )
        rf_hash = hashlib.sha256(
            (self.judge_dir / "judge-rf-v1.json").read_bytes()
        ).hexdigest()
        self.prereg.write_text(
            f"# Pre-registration\n\n{entry}\n\njudge-rf-v1.json sha256 {rf_hash}\n\n"
            f"{ENTRY_6}\n"
        )

        records, judge_rows, verdicts = [], [], {}
        index = []
        (self.refs_dir / "answers").mkdir(parents=True)
        (self.run_dir / "raw" / "answers").mkdir(parents=True)
        counter = {"n": 0}

        def add(request_id, cache, product, entry_id, question, answer, overlap=None):
            sha_a = sha(answer)
            (self.run_dir / "raw" / "answers" / f"{sha_a}.txt").write_text(answer)
            r = {
                "request_id": request_id,
                "cache": cache,
                "entry_id": entry_id,
                "answer_sha256": sha_a,
                "query_raw": question,
                "source_overlap": overlap,
            }
            if product:
                r["product_id"] = product
            records.append(r)
            key = judge.verdict_key(question, product or "", sha_a)
            verdict = V1_CYCLE[counter["n"] % len(V1_CYCLE)]
            counter["n"] += 1
            if request_id == "h1":
                verdict = "UNPARSED"  # one undecided judge-v1 verdict, among the hits
            qa = f"qa-{request_id}"
            judge_rows.append(
                {
                    "request_id": request_id,
                    "verdict_key": key,
                    "verdict": verdict,
                    "qa_id": qa,
                    "stratum": "A",
                    "answerable": request_id != "m3",
                    "judge_version": "judge-v1",
                }
            )
            verdicts.setdefault(key, verdict)
            self.question_of[key] = question
            self.v1_of[key] = verdicts[key]
            if product:
                chunks = [f"doc-{request_id}#chunk-0", f"doc-{request_id}#chunk-1"]
                for c, t in zip(chunks, ("first", "second"), strict=True):
                    self.texts[c] = f"CTXT-{request_id}-{t}"
                ref_text = f"RTXT-{request_id}"
                ref_sha = sha(ref_text)
                (self.refs_dir / "answers" / f"{ref_sha}.txt").write_text(ref_text)
                index.append(
                    {
                        "qa_id": qa,
                        "question": question,
                        "product_id": product,
                        "stratum": "A",
                        "answerable": request_id != "m3",
                        "gold_doc_ids": [f"doc-{request_id}"],
                        "chunk_ids": chunks,
                        "reference_sha256": ref_sha,
                    }
                )

        for i in range(10):
            add(
                f"m{i}",
                "MISS",
                f"product-{i}",
                f"E{i}",
                f"QTXT-m{i} where is it?",
                f"ATXT-m{i} here.",
            )
        add("m10", "MISS", None, "E10", "QTXT-m10 no product?", "ATXT-m10 none.")
        add(
            "m11",
            "MISS",
            "product-11",
            "E11",
            "QTXT-m11 other product?",
            "ATXT-m11 there.",
        )
        # hits on their own product's entry, with the entry's answer: overlaps 1.0, 1.0, 0.7, 0.5
        for j, overlap in enumerate((1.0, 1.0, 0.7, 0.5)):
            add(
                f"h{j}",
                "TIER2_HIT",
                f"product-{j}",
                f"E{j}",
                f"QTXT-h{j} asked again?",
                f"ATXT-m{j} here.",
                overlap,
            )
        # a hit on another product's entry (excluded by the frame)
        add(
            "h4",
            "TIER2_HIT",
            "product-11",
            "E0",
            "QTXT-h4 cross?",
            "ATXT-m0 here.",
            1.0,
        )

        (self.run_dir / "raw" / "requests.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in records)
        )
        manifest = {
            "run_id": RUN,
            "arms": {"config_id": 4, "mutation": "off"},
            "admissibility": {"admissible": True},
        }
        (self.run_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest))
        (self.run_dir / "judge").mkdir()
        (self.run_dir / "judge" / "records.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in judge_rows)
        )
        (self.run_dir / "judge" / "verdicts.jsonl").write_text(
            "".join(
                json.dumps({"verdict_key": k, "verdict": v, "reply": v}) + "\n"
                for k, v in verdicts.items()
            )
        )
        (self.refs_dir / "index.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in index)
        )

    # -- calling -------------------------------------------------------------------------------
    def draw(self, **kw):
        args = {
            "results_dir": self.results,
            "n_miss": N_MISS_FIXTURE,
            "now": lambda: NOW,
        }
        args.update(kw)
        return la.run_draw(RUN, log=self.logs.append, **args)

    def sheet_cmd(self, **kw):
        args = {
            "results_dir": self.results,
            "sheet_path": self.sheet,
            "refs_dir": self.refs_dir,
            "texts": self.texts,
            "now": lambda: NOW,
            "log": self.logs.append,
        }
        args.update(kw)
        return la.run_sheet(RUN, **args)

    def rf(self, ollama=None, **kw):
        args = {
            "results_dir": self.results,
            "refs_dir": self.refs_dir,
            "rf_path": self.judge_dir / "judge-rf-v1.json",
            "judge_path": self.judge_dir / "judge-v1.json",
            "prereg_path": self.prereg,
            "generator_model": GENERATOR,
            "texts": self.texts,
            "ollama": ollama or FakeOllama(),
            "pressure": lambda: 1,
            "now": lambda: NOW,
            "log": self.logs.append,
        }
        args.update(kw)
        return la.rf_run(RUN, **args)

    def lock(self, **kw):
        args = {
            "results_dir": self.results,
            "sheet_path": self.sheet,
            "refsheet_path": self.refsheet,
            "refs_dir": self.refs_dir,
            "texts": self.texts,
            "now": lambda: NOW,
            "log": self.logs.append,
        }
        args.update(kw)
        return la.lock(RUN, **args)

    def score(self, **kw):
        args = {
            "results_dir": self.results,
            "prereg_path": self.prereg,
            "sheet_path": self.sheet,
            "refsheet_path": self.refsheet,
            "now": lambda: NOW,
            "log": self.logs.append,
        }
        args.update(kw)
        return la.score(RUN, **args)

    logs = None

    def ref_items(self):
        """The item numbers on the second sheet, in order."""
        return [
            {"item": n} for n in sorted(la.parse_refsheet(self.refsheet.read_text()))
        ]

    # -- the author ----------------------------------------------------------------------------
    def items(self):
        return read_jsonl(self.adir / "items.jsonl")

    def label_plan(self):
        """`item -> word`: the first two items whose judge-v1 verdict is decided get the opposite label
        (decided disagreements), the next such item `unsure`, every other item the judge's own verdict
        (an `UNPARSED` verdict gets `correct`)."""
        plan, flipped, unsure = {}, 0, 0
        for row in self.items():
            verdict = self.v1_of[row["verdict_key"]]
            decided = verdict in ("CORRECT", "INCORRECT")
            if decided and flipped < 2:
                plan[row["item"]] = "correct" if verdict == "INCORRECT" else "incorrect"
                flipped += 1
            elif decided and unsure < 1:
                plan[row["item"]] = "unsure"
                unsure += 1
            else:
                plan[row["item"]] = verdict.lower() if decided else "correct"
        return plan

    def author_fills_sheet(self, plan=None):
        plan = plan or self.label_plan()
        self.sheet.write_text(fill(self.sheet.read_text(), plan))
        return plan

    def author_marks_refsheet(self, marks):
        out, current = [], None
        for line in self.refsheet.read_text().splitlines():
            m = la.ITEM.match(line)
            if m:
                current = int(m.group(1))
            if line == "reference right:":
                line = f"reference right: {marks[current]}"
            out.append(line)
        self.refsheet.write_text("\n".join(out) + "\n")


class FakeOllama:
    """`/api/tags`, `/api/ps`, `/api/show` and `/api/generate`. The reply depends on the answer text in the
    prompt (the last line, `A::...`); `eval_count` is the reply's `prompt_eval_count`, or a function of the
    call number."""

    def __init__(self, verdict_of=None, eval_count=300):
        self.tags = {MODEL: DIGEST}
        self.loaded = []
        self.verdict_of = verdict_of or (
            lambda answer: "INCORRECT" if sum(map(ord, answer)) % 3 == 0 else "CORRECT"
        )
        self.eval_count = eval_count
        self.bodies = []

    def __call__(self, path, body=None):
        if path == "/api/tags":
            return {"models": [{"name": n, "digest": d} for n, d in self.tags.items()]}
        if path == "/api/ps":
            return {"models": [{"name": n} for n in self.loaded]}
        if path == "/api/show":
            return {"capabilities": ["completion"]}
        assert path == "/api/generate", path
        self.bodies.append(body)
        answer = body["prompt"].rsplit("A::", 1)[1].strip()
        count = (
            self.eval_count(len(self.bodies))
            if callable(self.eval_count)
            else self.eval_count
        )
        reply = {"response": self.verdict_of(answer)}
        if count is not None:
            reply["prompt_eval_count"] = count
        return reply


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    w.logs = []
    return w


def prepared(world):
    """The run drawn and the sheet written. No reference-free run: Entry 6 retired it."""
    assert world.draw() == 0
    assert world.sheet_cmd() == 0
    return world


def finished(world, marks=("no", "yes")):
    """Everything up to and including the score."""
    prepared(world)
    world.author_fills_sheet()
    world.lock()
    world.author_marks_refsheet(
        {row["item"]: marks[i % len(marks)] for i, row in enumerate(world.ref_items())}
    )
    return world.score()


# --- the reference-free judge record (DC 5) ---------------------------------------------------------
def test_rf_record_matches_judge_v1():
    v1 = judge.load_judge(ROOT / "experiments" / "judge" / "judge-v1.json")
    rf = judge.load_judge(ROOT / "experiments" / "judge" / "judge-rf-v1.json")

    for key in ("model", "digest", "options"):
        assert rf[key] == v1[key], key
    assert rf["version"] == "judge-rf-v1"
    assert rf["prompt_file_sha256"] == rf["prompt_sha256"]
    # only the version, the prompt file and its hash differ
    assert {k for k in v1 if k in rf and v1[k] != rf[k]} == {
        "version",
        "prompt_file",
        "prompt_sha256",
        "prompt_text",
        "prompt_file_sha256",
        "cfg_sha256",
    }
    prompt = rf["prompt_text"]
    assert "{evidence}" in prompt and "{question}" in prompt and "{answer}" in prompt
    assert "{reference}" not in prompt
    # the pre-registration holds the record's hash (Entry 5)
    assert rf["cfg_sha256"] in (ROOT / "docs" / "preregistration.md").read_text()


def test_rf_prompt_formats_with_every_placeholder():
    rf = judge.load_judge(ROOT / "experiments" / "judge" / "judge-rf-v1.json")

    text = rf["prompt_text"].format(
        question="QQ", evidence="EE {with braces}", answer="AA"
    )

    assert "QQ" in text and "EE {with braces}" in text and "AA" in text


@pytest.mark.parametrize(
    "edit",
    [
        lambda cfg: cfg.update(model="other:1b"),
        lambda cfg: cfg.update(digest="e" * 64),
        lambda cfg: cfg["options"].update(temperature=0.5),
        lambda cfg: cfg["options"].update(num_ctx=8192),
    ],
)
def test_rf_run_refuses_a_record_that_differs_from_judge_v1_in_more_than_the_prompt(
    world, edit
):
    assert world.draw() == 0
    path = world.judge_dir / "judge-rf-v1.json"
    cfg = json.loads(path.read_text())
    edit(cfg)
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    # keep the pre-registration in step, so only the equality rule can refuse
    world.prereg.write_text(
        f"{ENTRY_5}\n{hashlib.sha256(path.read_bytes()).hexdigest()}\n"
    )
    fake = FakeOllama()
    fake.tags = {cfg["model"]: cfg["digest"]}

    with pytest.raises(la.AblationRefused):
        world.rf(fake)

    assert fake.bodies == []
    assert not (world.adir / "verdicts-rf.jsonl").exists()


def test_rf_run_refuses_a_record_the_pre_registration_does_not_hold(world):
    assert world.draw() == 0
    world.prereg.write_text(ENTRY_5 + "\n")

    with pytest.raises(la.AblationRefused, match="preregistration"):
        world.rf()


def test_rf_run_refuses_while_the_generator_is_loaded(world):
    assert world.draw() == 0
    fake = FakeOllama()
    fake.loaded = [GENERATOR]

    with pytest.raises(la.AblationRefused, match="loaded"):
        world.rf(fake)

    assert fake.bodies == []


# --- the reference-free run (DC 5) --------------------------------------------------------------------
def test_rf_run_writes_one_verdict_per_sampled_key(world):
    assert world.draw() == 0
    summary = world.rf()

    sample = read_jsonl(world.adir / "sample.jsonl")
    rows = read_jsonl(world.adir / "verdicts-rf.jsonl")
    assert [r["verdict_key"] for r in rows] == [r["verdict_key"] for r in sample]
    assert len(rows) == 4 + N_MISS_FIXTURE
    assert all(r["verdict"] in ("CORRECT", "INCORRECT") for r in rows)
    assert all(r["prompt_eval_count"] == 300 and r["written_at"] == NOW for r in rows)
    written = json.loads((world.adir / "rf.json").read_text())
    assert written == {**summary, "verdicts": summary["verdicts"]}
    assert written["judge_version"] == "judge-rf-v1"
    assert written["max_prompt_eval_count"] == 300 and written["num_ctx"] == 4096
    assert written["rows_reportable"] is True
    assert written["pressure_readings"] == [1, 1]
    assert written["verdicts"]["UNPARSED"] == 0


def test_rf_run_asks_with_the_gold_evidence_and_not_the_reference(world):
    assert world.draw() == 0
    fake = FakeOllama()
    world.rf(fake)

    sample = read_jsonl(world.adir / "sample.jsonl")
    by_question = {world.question_of[r["verdict_key"]]: r for r in sample}
    assert len(fake.bodies) == len(sample)
    for body in fake.bodies:
        prompt = body["prompt"]
        question = prompt.split("\n")[0].removeprefix("Q::")
        assert question in by_question
        request_id = by_question[question]["request_id"]
        assert f"CTXT-{request_id}-first\n\nCTXT-{request_id}-second" in prompt
        assert "RTXT" not in prompt
        assert body["options"] == OPTIONS and body["stream"] is False


def test_rf_run_stops_on_a_cut_prompt(world):
    assert world.draw() == 0
    fake = FakeOllama(eval_count=lambda call: 4096 if call == 3 else 300)

    with pytest.raises(la.AblationRefused, match="may be cut"):
        world.rf(fake)

    assert len(fake.bodies) == 3
    assert not (world.adir / "verdicts-rf.jsonl").exists()
    assert not (world.adir / "rf.json").exists()
    assert sorted(p.name for p in world.adir.iterdir()) == ["draw.json", "sample.jsonl"]


def test_rf_run_stops_on_a_reply_without_a_prompt_eval_count(world):
    assert world.draw() == 0

    with pytest.raises(la.AblationRefused, match="None"):
        world.rf(FakeOllama(eval_count=None))

    assert not (world.adir / "verdicts-rf.jsonl").exists()


def test_rf_run_stops_at_pressure_4_and_leaves_nothing(world):
    assert world.draw() == 0

    with pytest.raises(judge.JudgeRefused, match="critical"):
        world.rf(pressure=lambda: 4)

    assert not (world.adir / "rf.json").exists()


def test_rf_run_over_two_percent_unparsed_is_written_but_not_reportable(world):
    assert world.draw() == 0

    summary = world.rf(FakeOllama(verdict_of=lambda answer: "maybe"))

    assert summary["rows_reportable"] is False
    assert summary["unparsed_share"] == 1.0
    assert (world.adir / "rf.json").exists()
    assert any("STOP" in line for line in world.logs)


def test_rf_run_refuses_when_its_output_exists(world):
    prepared(world)
    world.rf()

    with pytest.raises(la.AblationRefused, match="exists"):
        world.rf()


# --- the draw command (DC 3) ----------------------------------------------------------------------
def test_draw_writes_the_sample_and_a_second_run_says_identical(world):
    assert world.draw() == 0

    sample = read_jsonl(world.adir / "sample.jsonl")
    summary = json.loads((world.adir / "draw.json").read_text())
    assert len(sample) == 4 + N_MISS_FIXTURE
    assert summary["frame"]["excluded"] == {"no_product_id": 1, "cross_product_hit": 1}
    # 12 MISS records minus the one with no product_id, plus the 4 hits (the fifth hit is cross-product)
    assert summary["frame"]["keys"] == 11 + 4
    assert summary["sample"]["by_stratum"] == {"MISS": N_MISS_FIXTURE, "hit": 4}
    assert summary["sample"]["by_bucket"]["1.0"] == 2
    assert summary["written_at"] == NOW
    before = (world.adir / "sample.jsonl").read_bytes()

    assert world.draw(now=lambda: "2027-01-01T00:00:00+00:00") == 0

    assert world.logs[-1] == "identical"
    assert (world.adir / "sample.jsonl").read_bytes() == before  # untouched
    assert json.loads((world.adir / "draw.json").read_text())["written_at"] == NOW


def test_draw_says_different_when_the_sample_file_changed(world):
    assert world.draw() == 0
    path = world.adir / "sample.jsonl"
    path.write_text(path.read_text().replace('"MISS"', '"miss"', 1))

    assert world.draw() == 1

    assert world.logs[-1].startswith("DIFFERENT")


def test_draw_refuses_when_only_one_of_its_outputs_exists(world):
    assert world.draw() == 0
    (world.adir / "draw.json").unlink()

    with pytest.raises(la.AblationRefused, match="only one"):
        world.draw()


def test_draw_refuses_a_run_that_is_not_admissible(world):
    manifest = world.run_dir / "manifest.yaml"
    data = yaml.safe_load(manifest.read_text())
    data["admissibility"]["admissible"] = False
    manifest.write_text(yaml.safe_dump(data))

    with pytest.raises(la.AblationRefused, match="admissible"):
        world.draw()


def test_draw_refuses_a_run_judged_by_another_judge(world):
    path = world.run_dir / "judge" / "records.jsonl"
    path.write_text(path.read_text().replace("judge-v1", "judge-v2"))

    with pytest.raises(la.AblationRefused, match="judge-v2"):
        world.draw()


# --- the sheet command (DC 4) ---------------------------------------------------------------------
def test_sheet_items_map_each_item_to_its_own_key(world):
    assert world.draw() == 0
    assert world.sheet_cmd() == 0

    sections = la._sections(world.sheet.read_text())
    items = world.items()
    assert sorted(r["item"] for r in items) == list(range(1, 4 + N_MISS_FIXTURE + 1))
    for row in items:
        section = sections[row["item"]]
        assert world.question_of[row["verdict_key"]] in section
    # the order is a seeded shuffle of the sample, not the sample's order
    sample_keys = [r["verdict_key"] for r in read_jsonl(world.adir / "sample.jsonl")]
    assert sorted(r["verdict_key"] for r in items) == sorted(sample_keys)
    assert [r["verdict_key"] for r in items] != sample_keys


def test_sheet_shows_the_gold_evidence_and_no_reference_or_verdict(world):
    assert world.draw() == 0
    assert world.sheet_cmd() == 0

    text = world.sheet.read_text()
    assert "CTXT-" in text and "ATXT-" in text and "QTXT-" in text
    assert "RTXT" not in text
    body = text[text.index("## Item 1") :]
    assert "CORRECT" not in body and "INCORRECT" not in body
    for word in ("cache", "overlap", "stratum", "similarity"):
        assert word not in text.lower(), word
    for word in ("TIER2_HIT", "MISS"):
        assert word not in text, word


def test_sheet_refuses_when_the_sheet_or_items_exist(world):
    assert world.draw() == 0
    assert world.sheet_cmd() == 0

    with pytest.raises(la.AblationRefused, match="exists"):
        world.sheet_cmd()


def test_sheet_refuses_without_a_draw(world):
    with pytest.raises(la.AblationRefused, match="draw"):
        world.sheet_cmd()


def test_sheet_stops_when_the_sample_is_not_this_runs(world):
    assert world.draw() == 0
    path = world.adir / "sample.jsonl"
    rows = read_jsonl(path)
    rows[0]["verdict_key"] = "0" * 64
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))

    with pytest.raises(la.AblationRefused, match="recompute"):
        world.sheet_cmd()


# --- lock (DC 6) -------------------------------------------------------------------------------------
def test_lock_writes_every_label_with_the_sheets_sha256(world):
    prepared(world)
    plan = world.author_fills_sheet()
    sheet_sha = hashlib.sha256(world.sheet.read_bytes()).hexdigest()

    result = world.lock()

    rows = read_jsonl(world.adir / "labels.jsonl")
    assert len(rows) == 4 + N_MISS_FIXTURE
    assert {r["sheet_sha256"] for r in rows} == {sheet_sha}
    key_of = {r["item"]: r["verdict_key"] for r in world.items()}
    for row in rows:
        assert row["label"] == plan[row["item"]]
        assert row["verdict_key"] == key_of[row["item"]]
        assert row["written_at"] == NOW
    assert result["sheet_sha256"] == sheet_sha and result["labels"] == len(rows)


def test_lock_refuses_an_unmarked_item_and_an_unknown_word(world, tmp_path):
    prepared(world)
    plan = world.label_plan()
    original = world.sheet.read_text()

    world.sheet.write_text(fill(original, {**plan, 3: ""}))
    with pytest.raises(la.AblationRefused, match="unmarked"):
        world.lock()

    world.sheet.write_text(fill(original, {**plan, 3: "maybe"}))
    with pytest.raises(la.AblationRefused, match="word"):
        world.lock()

    assert not (world.adir / "labels.jsonl").exists()
    assert not world.refsheet.exists()


def test_lock_refuses_a_sheet_whose_items_are_not_the_items_file(world):
    prepared(world)
    world.author_fills_sheet()
    world.sheet.write_text(
        world.sheet.read_text().replace("## Item 1\n", "## Item 99\n")
    )

    with pytest.raises(la.AblationRefused, match="items.jsonl"):
        world.lock()


def test_lock_refuses_when_its_output_exists(world):
    prepared(world)
    world.author_fills_sheet()
    world.lock()

    with pytest.raises(la.AblationRefused, match="exists"):
        world.lock()


def test_refsheet_holds_only_decided_disagreements(world):
    prepared(world)
    plan = world.author_fills_sheet()
    verdict_of_item = {r["item"]: world.v1_of[r["verdict_key"]] for r in world.items()}
    expected = sorted(
        n
        for n, word in plan.items()
        if word != "unsure"
        and verdict_of_item[n] in ("CORRECT", "INCORRECT")
        and word.upper() != verdict_of_item[n]
    )
    # the scenario holds all three kinds the sheet must leave out
    assert len(expected) == 2
    assert "unsure" in plan.values() and "UNPARSED" in verdict_of_item.values()

    result = world.lock()

    shown = sorted(la.parse_refsheet(world.refsheet.read_text()))
    assert shown == expected and result["disagreements"] == 2
    text = world.refsheet.read_text()
    for n in expected:
        assert f"author label: {plan[n]}" in text
    assert text.count("RTXT-") == 2  # the reference answer appears only for those two
    assert sum(1 for line in text.splitlines() if line == "reference right:") == 2


def test_lock_with_no_disagreement_writes_an_empty_second_sheet(world):
    prepared(world)
    plan = {
        r["item"]: (
            "correct"
            if world.v1_of[r["verdict_key"]] == "UNPARSED"
            else world.v1_of[r["verdict_key"]].lower()
        )
        for r in world.items()
    }
    world.author_fills_sheet(plan)

    result = world.lock()

    assert result["disagreements"] == 0
    assert la.parse_refsheet(world.refsheet.read_text()) == {}


def test_lock_refuses_a_changed_sheet(world):
    prepared(world)
    world.author_fills_sheet()
    world.lock()
    world.author_marks_refsheet(
        {n: "yes" for n in la.parse_refsheet(world.refsheet.read_text())}
    )
    before = world.sheet.read_text()
    after = before.replace("label: correct", "label: incorrect", 1)
    assert after != before  # the edit really changed the sheet
    world.sheet.write_text(after)

    with pytest.raises(la.AblationRefused, match="changed after the lock"):
        world.score()

    assert not (world.adir / "scores.json").exists()
    assert not (world.adir / "refcheck.jsonl").exists()


# --- the rf sanity pairs ---------------------------------------------------------------------------------
def sanity_file(world, rows):
    path = world.root / "sanity.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def run_sanity(world, path, ollama=None, **kw):
    args = {
        "refs_dir": world.refs_dir,
        "rf_path": world.judge_dir / "judge-rf-v1.json",
        "judge_path": world.judge_dir / "judge-v1.json",
        "prereg_path": world.prereg,
        "generator_model": GENERATOR,
        "texts": world.texts,
        "ollama": ollama or FakeOllama(),
        "pressure": lambda: 1,
        "now": lambda: NOW,
        "log": world.logs.append,
    }
    args.update(kw)
    return la.rf_sanity(path, **args)


def test_rf_sanity_passes_when_every_verdict_is_the_expected_one(world):
    answers = {"qa-m1": "right answer", "qa-m2": "wrong answer"}
    fake = FakeOllama(
        verdict_of=lambda a: "CORRECT" if a == answers["qa-m1"] else "INCORRECT"
    )
    path = sanity_file(
        world,
        [
            {
                "qa_id": "qa-m1",
                "answer": answers["qa-m1"],
                "expected": "CORRECT",
                "kind": "ok",
            },
            {
                "qa_id": "qa-m2",
                "answer": answers["qa-m2"],
                "expected": "INCORRECT",
                "kind": "bad",
            },
        ],
    )

    assert run_sanity(world, path, fake) == 0

    assert f"written_at: {NOW}" in world.logs
    assert world.logs[-1] == "  2 of 2 correct, 0 UNPARSED"
    # each pair is judged with its gold evidence, not a reference
    assert "CTXT-m1-first\n\nCTXT-m1-second" in fake.bodies[0]["prompt"]
    assert not any("RTXT" in b["prompt"] for b in fake.bodies)


def test_rf_sanity_fails_on_a_wrong_or_unparsed_verdict(world):
    path = sanity_file(
        world,
        [
            {"qa_id": "qa-m1", "answer": "x", "expected": "CORRECT", "kind": "a"},
            {"qa_id": "qa-m2", "answer": "y", "expected": "CORRECT", "kind": "b"},
        ],
    )

    assert run_sanity(world, path, FakeOllama(verdict_of=lambda a: "INCORRECT")) == 1
    assert world.logs[-1] == "  0 of 2 correct, 0 UNPARSED"
    assert run_sanity(world, path, FakeOllama(verdict_of=lambda a: "unsure")) == 1
    assert world.logs[-1] == "  0 of 2 correct, 2 UNPARSED"


def test_rf_sanity_refuses_an_unknown_qa_id_and_a_loaded_generator(world):
    path = sanity_file(
        world, [{"qa_id": "nope", "answer": "x", "expected": "CORRECT", "kind": "a"}]
    )

    with pytest.raises(la.AblationRefused, match="not in the reference set"):
        run_sanity(world, path)
    loaded = FakeOllama()
    loaded.loaded = [GENERATOR]
    with pytest.raises(la.AblationRefused, match="loaded"):
        run_sanity(world, path, loaded)


# --- score (DC 7, DC 1) -----------------------------------------------------------------------------------
def test_score_reports_hits_and_misses_apart_with_counts_that_add_up(world):
    scores = finished(world)

    assert set(scores["by_stratum"]) == {"hit", "MISS"}
    sample = read_jsonl(world.adir / "sample.jsonl")
    labels = {
        r["verdict_key"]: r["label"] for r in read_jsonl(world.adir / "labels.jsonl")
    }
    for stratum in ("hit", "MISS"):
        keys = [r["verdict_key"] for r in sample if r["stratum"] == stratum]
        block = scores["by_stratum"][stratum]
        pairs = [
            (world.v1_of[k], labels[k].upper())
            for k in keys
            if world.v1_of[k] in ("CORRECT", "INCORRECT") and labels[k] != "unsure"
        ]
        assert block["keys"] == len(keys)
        assert block["judge_vs_author"]["n"] == len(pairs)
        assert block["judge_vs_author"]["k"] == sum(1 for a, b in pairs if a == b)
        assert block["judge_vs_author"]["undecided"] == len(keys) - len(pairs)
    # the answerable-false key (m3) has its own row, when it was drawn
    assert "answerable_false_judge_vs_author" in scores["by_stratum"]["MISS"]
    assert scores["sample_keys"] == 4 + N_MISS_FIXTURE
    assert scores["entry5_first"] is True
    assert any(line.startswith("entry 5 first: yes") for line in world.logs)


def test_score_wilson_intervals_are_the_projects_wilson(world):
    scores = finished(world)

    for stratum in ("hit", "MISS"):
        block = scores["by_stratum"][stratum]["judge_vs_author"]
        assert block["wilson95"] == select_pqa.wilson(block["k"], block["n"])


def test_score_buckets_split_the_hits(world):
    scores = finished(world)

    buckets = scores["by_stratum"]["hit"]["judge_vs_author_by_bucket"]
    assert set(buckets) == {"1.0", "[0.8, 1)", "[0.6, 0.8)", "below 0.6", "below 1.0"}
    assert buckets["1.0"]["keys"] == 2
    assert buckets["[0.6, 0.8)"]["keys"] == 1 and buckets["below 0.6"]["keys"] == 1
    assert buckets["[0.8, 1)"]["keys"] == 0
    assert buckets["below 1.0"]["keys"] == 2
    miss = scores["by_stratum"]["MISS"]["judge_vs_author_by_bucket"]
    assert set(miss) == {"generated"} and miss["generated"]["keys"] == N_MISS_FIXTURE
    assert scores["circularity"]["result"] in ("bounded", "quantified", "undefined")


def test_score_layer5_counts_the_no_marks_over_the_decided_keys(world):
    scores = finished(world, marks=("no", "yes"))

    refcheck = read_jsonl(world.adir / "refcheck.jsonl")
    assert len(refcheck) == 2
    assert [r["reference_right"] for r in refcheck] == ["no", "yes"]
    sample = {r["verdict_key"]: r for r in read_jsonl(world.adir / "sample.jsonl")}
    labels = {
        r["verdict_key"]: r["label"] for r in read_jsonl(world.adir / "labels.jsonl")
    }
    no_key = refcheck[0]["verdict_key"]
    for stratum in ("hit", "MISS"):
        decided = sum(
            1
            for k, r in sample.items()
            if r["stratum"] == stratum and labels[k] != "unsure"
        )
        block = scores["layer5"][stratum]
        assert block["n"] == decided
        assert block["k"] == (1 if sample[no_key]["stratum"] == stratum else 0)
        assert block["wilson95"] == select_pqa.wilson(block["k"], block["n"])
    assert sum(b["checked"] for b in scores["layer5"].values()) == 2


def test_score_refuses_an_unmarked_second_sheet(world):
    prepared(world)
    world.author_fills_sheet()
    world.lock()

    with pytest.raises(la.AblationRefused, match="yes or no"):
        world.score()

    assert not (world.adir / "scores.json").exists()


def test_score_refuses_a_second_sheet_that_is_not_the_disagreements(world):
    prepared(world)
    world.author_fills_sheet()
    world.lock()
    world.refsheet.write_text("# empty\n")

    with pytest.raises(la.AblationRefused, match="second sheet"):
        world.score()


def test_score_refuses_when_entry_5_is_not_earlier(world):
    prepared(world)
    world.author_fills_sheet()
    world.lock()
    world.author_marks_refsheet(
        {n: "yes" for n in la.parse_refsheet(world.refsheet.read_text())}
    )
    world.prereg.write_text(world.prereg.read_text().replace("05:41Z", "23:59Z"))

    with pytest.raises(la.AblationRefused, match="not after Entry 5"):
        world.score()

    assert "entry 5 first: NO" in world.logs
    assert not (world.adir / "scores.json").exists()


def test_score_refuses_when_a_sanity_log_is_older_than_entry_5(world, tmp_path):
    prepared(world)
    world.author_fills_sheet()
    world.lock()
    world.author_marks_refsheet(
        {n: "yes" for n in la.parse_refsheet(world.refsheet.read_text())}
    )
    log = tmp_path / "rf-sanity-1.log"
    log.write_text(
        "written_at: 2026-11-11T05:00:00+00:00\n  12 of 12 correct, 0 UNPARSED\n"
    )

    with pytest.raises(la.AblationRefused, match="rf-sanity-1.log"):
        world.score(sanity_logs=[log])


def test_score_refuses_when_its_output_exists(world):
    finished(world)

    with pytest.raises(la.AblationRefused, match="exists"):
        world.score()


def test_score_prints_the_tables(world):
    finished(world)

    out = "\n".join(world.logs)
    for needle in (
        "== hit",
        "== MISS",
        "(a) judge-v1 vs author",
        "(b) not computed: judge-rf-v1 failed its sanity check (Entry 6)",
        "(c) judge-v1 vs author, by bucket",
        "bucket 1.0",
        "bucket below 1.0",
        "bucket generated",
        "(d) layer 5",
        "(e) circularity",
        "kappa",
        "entry 5 first: yes",
        "entry 6 first: yes",
    ):
        assert needle in out, needle
    assert "vs judge-rf-v1" not in out  # no score compares with the failed judge


# --- no corpus text in a committed file (DC 7) -------------------------------------------------------------
def test_committed_outputs_hold_no_text(world):
    finished(world)

    committed = [p for p in world.adir.rglob("*") if p.is_file()]
    assert {p.name for p in committed} == {
        "draw.json",
        "sample.jsonl",
        "items.jsonl",
        "labels.jsonl",
        "refcheck.jsonl",
        "scores.json",
    }
    markers = ("QTXT", "ATXT", "CTXT", "RTXT", "where is it", "asked again", "here.")
    # the questions, answers, evidence and references themselves
    needles = (
        list(world.question_of.values())
        + [f"ATXT-m{i} here." for i in range(10)]
        + list(world.texts.values())
        + [f"RTXT-{r}" for r in ("m0", "m1", "h0")]
        + list(markers)
    )
    for path in committed:
        body = path.read_text()
        for needle in needles:
            assert needle not in body, (path.name, needle[:10])
    # and the private sheets, which hold the text, are not under ablation/
    assert "QTXT" in world.sheet.read_text() and "RTXT" in world.refsheet.read_text()
    assert (
        world.adir not in world.sheet.parents
        and world.adir not in world.refsheet.parents
    )


def test_the_reference_free_replies_hold_only_a_verdict_word(world):
    prepared(world)
    world.rf()

    for row in read_jsonl(world.adir / "verdicts-rf.jsonl"):
        assert row["reply"] in ("CORRECT", "INCORRECT")
        assert set(row) == {
            "verdict_key",
            "verdict",
            "reply",
            "seconds",
            "prompt_eval_count",
            "written_at",
        }


# =================================================================================================
# After the sanity failure (Entry 6): no reference-free run, the author is the reference-free side
# =================================================================================================
def test_score_needs_no_rf_files(world):
    scores = finished(world)

    names = {p.name for p in world.adir.iterdir()}
    assert "verdicts-rf.jsonl" not in names and "rf.json" not in names
    assert scores["reference_free_side"] == "author"
    assert scores["judge_rf"] == la.RF_FAILED
    assert scores["entry5_first"] is True and scores["entry6_first"] is True
    assert "rf_rows_reportable" not in scores
    written = (world.adir / "scores.json").read_text()
    assert "judge_vs_rf" not in written and "rf_vs_author" not in written


def synthetic_score_world(tmp_path, a1, a0, with_rf_files):
    """Hand-written `ablation/` files for `score`: `a1[1]` hits at 1.0 of which `a1[0]` have the author
    agreeing with `judge-v1`, `a0[1]` hits below 1.0 (bucket `below 0.6`) of which `a0[0]` agree, and 2 MISS
    that agree. `judge-v1` says `CORRECT` everywhere; the author says `incorrect` where they disagree. With
    `with_rf_files`, a reference-free verdict file with the opposite verdicts sits in `ablation/`."""
    results = tmp_path / "results"
    adir = results / RUN / "ablation"
    (results / RUN / "judge").mkdir(parents=True)
    adir.mkdir()
    rows, labels, disagree = [], {}, []
    for stratum, bucket, agree, n in (
        ("hit", "1.0", *a1),
        ("hit", "below 0.6", *a0),
        ("MISS", "generated", 2, 2),
    ):
        for i in range(n):
            key = f"key-{bucket}-{i}"
            rows.append(
                {
                    "verdict_key": key,
                    "request_id": f"req-{key}",
                    "cache": "MISS" if stratum == "MISS" else "TIER2_HIT",
                    "stratum": stratum,
                    "bucket": bucket,
                    "source_overlap": None,
                    "qa_id": f"qa-{key}",
                    "answerable": True,
                    "workload_stratum": "A",
                }
            )
            labels[key] = "correct" if i < agree else "incorrect"
            if i >= agree:
                disagree.append(key)
    numbered = {r["verdict_key"]: n for n, r in enumerate(rows, 1)}
    when = "2026-11-11T09:00:00+00:00"
    sheet_text = "# sheet\n"
    (tmp_path / "private").mkdir()
    sheet = tmp_path / "private" / "sheet.md"
    sheet.write_text(sheet_text)
    refsheet = tmp_path / "private" / "refsheet.md"
    refsheet.write_text(
        "".join(f"## Item {numbered[k]}\n\nreference right: yes\n\n" for k in disagree)
    )
    prereg = tmp_path / "preregistration.md"
    prereg.write_text(f"{ENTRY_5}\n\n{ENTRY_6}\n")

    def write(path, items):
        path.write_text("".join(json.dumps(r) + "\n" for r in items))

    write(adir / "sample.jsonl", rows)
    write(
        adir / "items.jsonl",
        [
            {"item": n, "verdict_key": k, "written_at": when}
            for k, n in numbered.items()
        ],
    )
    write(
        adir / "labels.jsonl",
        [
            {
                "item": numbered[k],
                "verdict_key": k,
                "label": w,
                "sheet_sha256": sha(sheet_text),
                "written_at": when,
            }
            for k, w in labels.items()
        ],
    )
    (adir / "draw.json").write_text(
        json.dumps({"written_at": "2026-11-11T08:00:00+00:00"})
    )
    write(
        results / RUN / "judge" / "verdicts.jsonl",
        [{"verdict_key": k, "verdict": "CORRECT", "reply": "CORRECT"} for k in labels],
    )
    if with_rf_files:
        write(
            adir / "verdicts-rf.jsonl",
            [
                {"verdict_key": k, "verdict": "INCORRECT", "written_at": when}
                for k in labels
            ],
        )
        (adir / "rf.json").write_text(
            json.dumps({"written_at": when, "rows_reportable": False})
        )

    def score():
        logs = []
        scores = la.score(
            RUN,
            results_dir=results,
            prereg_path=prereg,
            sheet_path=sheet,
            refsheet_path=refsheet,
            now=lambda: when,
            log=logs.append,
        )
        return scores, logs

    return score


@pytest.mark.parametrize("with_rf_files", [False, True])
def test_circularity_is_judge_v1_against_author(tmp_path, with_rf_files):
    # hits at 1.0: judge-v1 and the author agree on 9 of 10; below 1.0: on 3 of 10
    score = synthetic_score_world(tmp_path, (9, 10), (3, 10), with_rf_files)

    scores, logs = score()

    by_bucket = scores["by_stratum"]["hit"]["judge_vs_author_by_bucket"]
    assert (by_bucket["1.0"]["k"], by_bucket["1.0"]["n"]) == (9, 10)
    assert (by_bucket["below 1.0"]["k"], by_bucket["below 1.0"]["n"]) == (3, 10)
    assert by_bucket["below 1.0"]["wilson95"] == [0.1078, 0.6032]
    assert scores["circularity"] == {
        "result": "quantified",
        "inflation": 0.6,
        "a1": 0.9,
        "a0": 0.3,
        "n_a1": 10,
        "n_a0": 10,
    }
    assert "(e) circularity: quantified" in logs
    # the 8 disagreements are on the second sheet and none is a wrong reference
    assert scores["layer5"]["hit"]["k"] == 0 and scores["layer5"]["hit"]["checked"] == 8


def test_circularity_is_bounded_when_the_below_1_agreement_holds_up(tmp_path):
    score = synthetic_score_world(tmp_path, (9, 10), (8, 10), False)

    scores, _ = score()

    assert scores["circularity"]["result"] == "bounded"
    assert scores["circularity"]["inflation"] is None


def test_score_refuses_entry6_after_the_sheet(world):
    prepared(world)
    world.author_fills_sheet()
    world.lock()
    world.author_marks_refsheet(
        {n: "yes" for n in la.parse_refsheet(world.refsheet.read_text())}
    )
    # the sheet's written_at is 09:00:00; Entry 6 in the same minute is not provably earlier
    world.prereg.write_text(world.prereg.read_text().replace("06:37Z", "09:00Z"))

    with pytest.raises(la.AblationRefused, match="not after Entry 6"):
        world.score()

    assert "entry 6 first: NO" in world.logs
    assert not (world.adir / "scores.json").exists()
    assert not (world.adir / "refcheck.jsonl").exists()


def test_score_prints_entry6_first_yes_when_it_came_before_the_sheet(world):
    finished(world)

    assert any(line.startswith("entry 6 first: yes") for line in world.logs)


def test_score_refuses_a_preregistration_without_entry6(world):
    prepared(world)
    world.author_fills_sheet()
    world.lock()
    world.author_marks_refsheet(
        {n: "yes" for n in la.parse_refsheet(world.refsheet.read_text())}
    )
    world.prereg.write_text(world.prereg.read_text().replace("## Entry 6", "## Note 6"))

    with pytest.raises(la.AblationRefused, match="no Entry 6"):
        world.score()


def test_entry6_end_is_the_first_instant_after_its_minute():
    text = f"{ENTRY_5}\n\n{ENTRY_6}\n"

    assert la.entry6_end(text).isoformat() == "2026-11-11T06:38:00+00:00"


def test_check_entry6_first_compares_with_the_sheet_only():
    text = f"{ENTRY_5}\n\n{ENTRY_6}\n"

    assert la.check_entry6_first(text, "2026-11-11T06:38:00+00:00") == []
    late = la.check_entry6_first(text, "2026-11-11T06:37:59+00:00")
    assert len(late) == 1 and "sheet" in late[0] and "Entry 6" in late[0]


def test_entry6_missing_is_a_refusal():
    with pytest.raises(la.AblationRefused, match="Entry 6"):
        la.entry6_end(f"{ENTRY_5}\n")


def test_the_real_preregistration_has_entry6_with_a_time():
    text = (ROOT / "docs" / "preregistration.md").read_text()

    assert la.entry6_end(text) > la.entry5_end(text)


def test_rf_command_is_retired(tmp_path, monkeypatch, capsys):
    def no_ollama(*args, **kwargs):
        raise AssertionError("the retired rf command called Ollama")

    monkeypatch.setattr(judge, "make_ollama", no_ollama)
    monkeypatch.setattr(la, "rf_run", no_ollama)

    code = la.main(["rf", "--run-id", "x", "--results-dir", str(tmp_path / "results")])

    assert code == 1
    err = capsys.readouterr().err
    assert "REFUSED: retired by Entry 6: judge-rf-v1 failed its sanity check" in err
    assert list(tmp_path.iterdir()) == []  # nothing was written
