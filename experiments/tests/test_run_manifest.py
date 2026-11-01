"""Item 5.1, done condition 2 (docs/work/2026-10-30-judge-harness/design.md): the run manifest.

The manifest says which arm a run was and whether it may be judged. Its expensive failure is a manifest
that is wrong and looks right: the arms read from another run's log, a run that was killed and still
reads as complete, a hit on an entry that no MISS in the run wrote. Every test pins one such path, and
each refusal the check has is shown once.

No Ollama, no Redis, no gateway, no network: the machine's facts are injected, and the repository is a
temp folder with the three files the manifest reads.
"""

import copy
import functools
import json
from pathlib import Path

import pytest
import run_manifest as rm
import yaml

RUN_ID = "2026-11-01T10-00-00_cfg4_fixture"
SHA = "a" * 64
START_LOG = f"""\
make[1]: Entering directory '/x'
  rag.server pid 4242 listening on :50051
2026/11/01 10:00:00 gateway: dataset_epoch_file=/x/data/dataset-epoch epoch=3 (ADR-008)
2026/11/01 10:00:01 gateway: tau=0.850 theta=0.60 dim=768 index=idx:cache  (all DEMO values, swept later)
2026/11/01 10:00:01 gateway: lane_band=[0.20,0.20) mixed_lane=off (pinned, ADR-016)
2026/11/01 10:00:01 gateway: admission permits=1 queue_budget=0  (permits = the frozen served slot count,
         ADR-003; must equal np in the ENVELOPE line `make env-check` prints)
2026/11/01 10:00:01 gateway: cache_capacity=156  entries, LRU, enforced by the gateway (see cache/capacity.go)
2026/11/01 10:00:01 gateway: evaluation log -> /x/experiments/results/{RUN_ID}/raw/requests.jsonl, answer text -> raw/answers/
2026/11/01 10:00:01 gateway: support_gate=on  (default: a candidate that clears tau and the namespace is refused
         when the cached answer is not supported by this request's evidence)
2026/11/01 10:00:01 gateway listening on :8080 (redis=localhost:6379 rag=localhost:50051)
"""
END_LINE = "2026/11/01 11:00:00 gateway: shutting down, flushing the evaluation log\n"
INCOMPLETE_LINE = (
    "2026/11/01 11:00:02 gateway: THIS RUN IS INCOMPLETE -- 2 record(s) dropped\n"
)
GOOD_LOG = START_LOG + END_LINE


def record(i, cache="MISS", entry="E1", **extra):
    r = {
        "request_id": f"req-{i:02d}",
        "run_id": RUN_ID,
        "config_id": 4,
        "mutation": "off",
        "support_gate": "on",
        "mixed_lane": "off",
        "query_raw": f"Question {i}?",
        "cache": cache,
        "entry_id": entry,
        "answer_sha256": SHA,
    }
    r.update(extra)
    return r


def good_records():
    return [
        record(1, "MISS", "E1"),
        record(2, "TIER2_HIT", "E1"),
        record(3, "TIER1_HIT", "E1"),
        record(4, "MISS", "E2", refusal_cause="SUPPORT", candidate_entry_id="E1"),
    ]


def write_run(results, records, run_id=RUN_ID):
    run_dir = results / run_id
    (run_dir / "raw").mkdir(parents=True)
    (run_dir / "raw" / "requests.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records)
    )
    return run_dir


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    (repo / "rag" / "src" / "rag").mkdir(parents=True)
    (repo / "data" / "v1-freeze.json").write_text(
        json.dumps(
            {
                "dataset_version": "v1",
                "snapshot_digest": "s" * 64,
                "run_files": {
                    "validation": {"k_distinct_queries": 622, "cache_capacity": 156},
                    "test": {"k_distinct_queries": 652, "cache_capacity": 163},
                },
            }
        )
    )
    (repo / "data" / "workload-v1-validation.json").write_text("[]\n")
    (repo / "rag" / "src" / "rag" / "retrieve.py").write_text("# retrieval source\n")
    return repo


FAKES = {
    "git": lambda: {"git_sha": "b" * 40, "dirty": True},
    "redis_info": lambda: {"redis_version": "8.0.0", "rdb_last_save_time": 1761990000},
    "envelope": lambda: (
        "ENVELOPE server_pid=1 runner_pid=2 version=0.33.2 np=1 ctx=8192 "
        "total_slots=1 n_ctx_slot=8192 blob=sha256-x"
    ),
    "ollama": lambda: {
        "model": "gen:2b",
        "digest": "g" * 64,
        "num_ctx": 8192,
        "think": False,
        "temperature": 1.0,
        "prompt_sha256": "p" * 64,
    },
}


def built(tmp_path, records=None, log_text=GOOD_LOG, split="validation"):
    """(manifest dict, run_dir, log path, repo) for a good run."""
    results = tmp_path / "results"
    run_dir = write_run(results, good_records() if records is None else records)
    log = tmp_path / "gateway.log"
    log.write_text(log_text)
    repo = make_repo(tmp_path)
    manifest = rm.build_manifest(
        run_dir, log, split, repo=repo, now=lambda: "2026-11-01T12:00:00+00:00", **FAKES
    )
    return manifest, run_dir, log, repo


def save(manifest, run_dir):
    (run_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))


def checked(tmp_path, edit=None, log=None, records=None):
    """The problems `check_manifest` finds after `edit` is applied to a good manifest."""
    manifest, run_dir, log_path, _ = built(tmp_path, records)
    if edit:
        edit(manifest)
    save(manifest, run_dir)
    return rm.check_manifest(run_dir, log_path if log is True else log)


# =================================================================================================
# read_records and arms
# =================================================================================================
def test_read_records_reads_every_line_and_skips_blank_ones(tmp_path):
    run_dir = write_run(tmp_path, [record(1), record(2)])
    path = run_dir / "raw" / "requests.jsonl"
    path.write_text(path.read_text() + "\n\n")
    assert [r["request_id"] for r in rm.read_records(run_dir)] == ["req-01", "req-02"]


def test_read_records_raises_on_a_missing_file_a_bad_line_and_no_records(tmp_path):
    with pytest.raises(rm.ManifestError, match="cannot read"):
        rm.read_records(tmp_path / "nowhere")
    run_dir = write_run(tmp_path, [record(1)])
    path = run_dir / "raw" / "requests.jsonl"
    path.write_text(path.read_text() + "{not json\n")
    with pytest.raises(rm.ManifestError, match="line 2 is not JSON"):
        rm.read_records(run_dir)
    path.write_text("\n")
    with pytest.raises(rm.ManifestError, match="no records"):
        rm.read_records(run_dir)


def test_arms_are_read_from_the_records():
    assert rm.arms(good_records()) == {
        "config_id": 4,
        "mutation": "off",
        "support_gate": "on",
        "mixed_lane": "off",
    }


@pytest.mark.parametrize(
    "key, other",
    [
        ("config_id", 5),
        ("mutation", "on"),
        ("support_gate", "off"),
        ("mixed_lane", "on"),
    ],
)
def test_arms_raises_when_one_record_differs(key, other):
    records = good_records()
    records[2] = {**records[2], key: other}
    with pytest.raises(rm.ManifestError, match=f"differ on {key}"):
        rm.arms(records)


@pytest.mark.parametrize("key", ["config_id", "mutation", "support_gate", "mixed_lane"])
def test_arms_raises_when_the_records_do_not_carry_the_key(key):
    records = [{k: v for k, v in r.items() if k != key} for r in good_records()]
    with pytest.raises(rm.ManifestError, match=f"no {key}"):
        rm.arms(records)


def test_arms_raises_on_a_record_that_lacks_the_key_among_records_that_have_it():
    records = good_records()
    records[1] = {k: v for k, v in records[1].items() if k != "support_gate"}
    with pytest.raises(rm.ManifestError, match="differ on support_gate"):
        rm.arms(records)


def test_arms_raises_on_no_records():
    with pytest.raises(rm.ManifestError, match="no records"):
        rm.arms([])


# =================================================================================================
# parse_gateway_log
# =================================================================================================
def test_the_log_parse_reads_each_value():
    log = rm.parse_gateway_log(GOOD_LOG, RUN_ID)

    assert log == {
        "run_id": RUN_ID,
        "tau": 0.85,
        "theta": 0.6,
        "cache_capacity": 156,
        "support_gate": "on",
        "mixed_lane": "off",
        "ended": True,
        "incomplete": False,
    }


def test_the_log_parse_reads_the_gate_off_and_mixed_on_arm():
    text = GOOD_LOG.replace("support_gate=on", "support_gate=off").replace(
        "lane_band=[0.20,0.20) mixed_lane=off", "lane_band=[0.20,0.60) mixed_lane=on"
    )
    log = rm.parse_gateway_log(text, RUN_ID)
    assert (log["support_gate"], log["mixed_lane"]) == ("off", "on")


def test_the_log_parse_reads_an_unbounded_capacity_and_other_thresholds():
    text = GOOD_LOG.replace("cache_capacity=156", "cache_capacity=0").replace(
        "tau=0.850 theta=0.60", "tau=0.900 theta=0.55"
    )
    log = rm.parse_gateway_log(text, RUN_ID)
    assert (log["cache_capacity"], log["tau"], log["theta"]) == (0, 0.9, 0.55)


def test_the_log_parse_marks_a_run_that_was_never_told_to_stop():
    log = rm.parse_gateway_log(START_LOG, RUN_ID)  # killed: no `shutting down` line
    assert log["ended"] is False and log["incomplete"] is False


def test_the_log_parse_marks_an_incomplete_run():
    log = rm.parse_gateway_log(GOOD_LOG + INCOMPLETE_LINE, RUN_ID)
    assert log["ended"] is True and log["incomplete"] is True


def test_the_log_parse_raises_on_the_log_of_another_run():
    with pytest.raises(rm.ManifestError, match="is for run .*, not other-run"):
        rm.parse_gateway_log(GOOD_LOG, "other-run")


def test_the_log_parse_reads_a_results_path_with_spaces():
    text = GOOD_LOG.replace("/x/experiments", "/Users/some one/experiments")
    assert rm.parse_gateway_log(text, RUN_ID)["run_id"] == RUN_ID


@pytest.mark.parametrize(
    "drop, what",
    [
        ("evaluation log -> ", "evaluation log line"),
        ("tau=0.850 theta=0.60", "tau"),
        ("cache_capacity=156", "cache_capacity"),
        ("support_gate=on", "support_gate"),
        ("mixed_lane=off", "mixed_lane"),
    ],
)
def test_the_log_parse_raises_when_a_value_is_missing(drop, what):
    text = "\n".join(line for line in GOOD_LOG.splitlines() if drop not in line) + "\n"
    with pytest.raises(rm.ManifestError, match=f"no {what}"):
        rm.parse_gateway_log(text, RUN_ID)


def test_the_log_parse_raises_when_the_log_is_a_functional_run_with_the_log_disabled():
    text = GOOD_LOG.replace(
        f"evaluation log -> /x/experiments/results/{RUN_ID}/raw/requests.jsonl, answer text -> raw/answers/",
        "evaluation log DISABLED (RUN_ID unset) -- functional run, produces no measurement",
    )
    with pytest.raises(rm.ManifestError, match="no evaluation log line"):
        rm.parse_gateway_log(text, RUN_ID)


def test_the_log_parse_raises_on_a_log_that_holds_two_values_for_one_setting():
    # `tee -a` onto an old log: a second start with another capacity.
    text = GOOD_LOG + GOOD_LOG.replace("cache_capacity=156", "cache_capacity=318")
    with pytest.raises(rm.ManifestError, match="2 values for cache_capacity"):
        rm.parse_gateway_log(text, RUN_ID)


def test_the_log_parse_raises_on_a_log_that_holds_two_runs():
    text = GOOD_LOG + GOOD_LOG.replace(RUN_ID, "another-run")
    with pytest.raises(rm.ManifestError, match="2 values for evaluation log line"):
        rm.parse_gateway_log(text, RUN_ID)


# =================================================================================================
# admissibility: rules 6, 10 and 12, and I9
# =================================================================================================
def admissible(records, log_text=GOOD_LOG):
    return rm.admissibility(records, rm.parse_gateway_log(log_text, RUN_ID))


def test_a_good_run_is_admissible():
    assert admissible(good_records()) == {
        "rule_6": True,
        "rule_10": True,
        "rule_12": True,
        "i9": True,
        "admissible": True,
    }


def test_rule_6_fails_when_the_gateway_was_killed_and_left_no_shutdown_line():
    # A killed gateway writes no `THIS RUN IS INCOMPLETE` line either: only the shutdown line shows it ended.
    result = admissible(good_records(), START_LOG)
    assert result["rule_6"] is False and result["admissible"] is False
    assert result["rule_10"] and result["rule_12"] and result["i9"]


def test_rule_6_fails_on_an_incomplete_line():
    result = admissible(good_records(), GOOD_LOG + INCOMPLETE_LINE)
    assert result["rule_6"] is False and result["admissible"] is False


def test_rule_10_fails_on_a_not_scored_record():
    records = good_records() + [record(5, "MISS", "E3", refusal_cause="NOT_SCORED")]
    result = admissible(records)
    assert result["rule_10"] is False and result["admissible"] is False
    assert result["rule_6"] and result["rule_12"] and result["i9"]


def test_rule_12_fails_on_a_tier2_search_failure():
    records = good_records() + [record(5, "MISS", "E3", tier2_search_failed=True)]
    result = admissible(records)
    assert result["rule_12"] is False and result["admissible"] is False
    assert result["rule_6"] and result["rule_10"] and result["i9"]


def test_rule_12_holds_when_the_marker_is_present_but_false():
    records = good_records() + [record(5, "MISS", "E3", tier2_search_failed=False)]
    assert admissible(records)["rule_12"] is True


@pytest.mark.parametrize("cache", ["TIER1_HIT", "TIER2_HIT"])
def test_i9_fails_on_a_hit_on_an_entry_no_miss_wrote(cache):
    records = good_records() + [record(5, cache, "E-FOREIGN")]
    result = admissible(records)
    assert result["i9"] is False and result["admissible"] is False
    assert rm.i9_violations(records) == ["E-FOREIGN"]


def test_i9_fails_on_a_judged_candidate_no_miss_wrote():
    records = good_records()
    records[3] = {**records[3], "candidate_entry_id": "E-FOREIGN"}
    assert admissible(records)["i9"] is False
    assert rm.i9_violations(records) == ["E-FOREIGN"]


def test_i9_compares_sets_so_a_hit_may_be_logged_before_its_miss():
    records = [record(1, "TIER2_HIT", "E9"), record(2, "MISS", "E9")]
    assert rm.i9_violations(records) == []


def test_i9_is_not_satisfied_by_a_miss_that_wrote_no_entry():
    # A MISS with entry_id "" wrote nothing (shed, failed, write-back discarded). A hit with no entry fails.
    records = [record(1, "MISS", ""), record(2, "TIER2_HIT", "")]
    assert rm.i9_violations(records) == [""]
    records = [record(1, "MISS", ""), record(2, "TIER2_HIT", None)]
    assert rm.i9_violations(records) == [""]


def test_i9_ignores_misses_and_records_with_no_candidate():
    records = [record(1, "MISS", "E1"), record(2, "SHED", "")]
    assert rm.i9_violations(records) == []


# =================================================================================================
# build_manifest
# =================================================================================================
TOP_LEVEL_ORDER = [
    "manifest_version",
    "run_id",
    "written_at",
    "gateway",
    "arms",
    "envelope",
    "redis",
    "corpus",
    "workload",
    "cache",
    "retrieval",
    "generator",
    "records",
    "admissibility",
]


def test_the_manifest_has_the_sections_of_interfaces_i_in_order(tmp_path):
    manifest, _, _, _ = built(tmp_path)
    assert list(manifest) == TOP_LEVEL_ORDER


def test_the_manifest_values_come_from_the_records_the_log_and_the_repository(tmp_path):
    manifest, _, _, repo = built(tmp_path)

    assert manifest["manifest_version"] == 1 and manifest["run_id"] == RUN_ID
    assert manifest["written_at"] == "2026-11-01T12:00:00+00:00"
    assert manifest["gateway"] == {"git_sha": "b" * 40, "dirty": True}
    assert manifest["arms"] == rm.arms(good_records())
    assert manifest["envelope"].startswith("ENVELOPE server_pid=1")
    assert manifest["redis"] == {
        "redis_version": "8.0.0",
        "rdb_last_save_time": 1761990000,
    }
    assert manifest["corpus"] == {"dataset_version": "v1", "snapshot_digest": "s" * 64}
    assert manifest["workload"] == {
        "file": "data/workload-v1-validation.json",
        "sha256": rm.refs.sha256_file(repo / "data" / "workload-v1-validation.json"),
        "K": 622,
        "frozen_cache_capacity": 156,
    }
    assert manifest["cache"] == {"capacity": 156, "tau_run": 0.85, "theta_run": 0.6}
    assert manifest["retrieval"]["retrieve_py_sha256"] == rm.refs.sha256_bytes(
        b"# retrieval source\n"
    )
    assert (
        manifest["retrieval"]["retrieval_version"] == "adr-021"
        and manifest["retrieval"]["top_k"] == 5
    )
    assert manifest["generator"] == FAKES["ollama"]()
    assert manifest["records"] == {
        "count": 4,
        "by_cache": {"MISS": 2, "TIER1_HIT": 1, "TIER2_HIT": 1},
    }
    assert manifest["admissibility"]["admissible"] is True


def test_the_manifest_reads_the_test_splits_capacity_for_the_test_split(tmp_path):
    results = tmp_path / "results"
    run_dir = write_run(results, good_records())
    log = tmp_path / "log"
    log.write_text(GOOD_LOG)
    repo = make_repo(tmp_path)
    (repo / "data" / "workload-v1-test.json").write_text("[]\n")

    manifest = rm.build_manifest(run_dir, log, "test", repo=repo, **FAKES)

    assert manifest["workload"]["file"] == "data/workload-v1-test.json"
    assert (
        manifest["workload"]["K"],
        manifest["workload"]["frozen_cache_capacity"],
    ) == (652, 163)


def test_the_manifest_records_a_run_that_is_not_admissible_and_does_not_hide_it(
    tmp_path,
):
    manifest, _, _, _ = built(tmp_path, log_text=START_LOG)  # a killed gateway
    assert manifest["admissibility"]["rule_6"] is False
    assert manifest["admissibility"]["admissible"] is False


def test_the_manifest_refuses_a_log_whose_arm_is_not_the_records(tmp_path):
    with pytest.raises(
        rm.ManifestError, match="log says support_gate=off but the records say on"
    ):
        built(
            tmp_path, log_text=GOOD_LOG.replace("support_gate=on", "support_gate=off")
        )
    with pytest.raises(
        rm.ManifestError, match="log says mixed_lane=on but the records say off"
    ):
        built(
            tmp_path / "second",
            log_text=GOOD_LOG.replace("mixed_lane=off", "mixed_lane=on"),
        )


def test_the_manifest_refuses_the_log_of_another_run(tmp_path):
    with pytest.raises(rm.ManifestError, match="is for run another-run"):
        built(tmp_path, log_text=GOOD_LOG.replace(RUN_ID, "another-run"))


def test_the_manifest_refuses_records_that_disagree_on_an_arm(tmp_path):
    records = good_records()
    records[1] = {**records[1], "mutation": "on"}
    with pytest.raises(rm.ManifestError, match="differ on mutation"):
        built(tmp_path, records)


def test_the_manifest_holds_no_question_or_answer_text(tmp_path):
    manifest, _, _, _ = built(tmp_path)
    dumped = yaml.safe_dump(manifest)
    assert "Question 1?" not in dumped and "query_raw" not in dumped


def test_the_manifest_round_trips_through_yaml_with_the_arms_still_strings(tmp_path):
    manifest, run_dir, _, _ = built(tmp_path)
    save(manifest, run_dir)

    loaded = yaml.safe_load((run_dir / "manifest.yaml").read_text())

    assert loaded == manifest  # "on" and "off" are not read back as booleans
    assert (
        loaded["arms"]["mutation"] == "off" and loaded["arms"]["support_gate"] == "on"
    )
    assert list(loaded) == TOP_LEVEL_ORDER


# =================================================================================================
# check_manifest
# =================================================================================================
def test_a_good_manifest_passes_the_check(tmp_path):
    assert checked(tmp_path) == []


def test_a_good_manifest_passes_the_check_with_its_log(tmp_path):
    assert checked(tmp_path, log=True) == []


def test_the_check_needs_a_manifest(tmp_path):
    run_dir = write_run(tmp_path, good_records())
    assert rm.check_manifest(run_dir) == [f"no manifest.yaml in {run_dir}"]


def test_the_check_refuses_a_manifest_that_is_not_yaml_or_not_a_mapping(tmp_path):
    run_dir = write_run(tmp_path, good_records())
    (run_dir / "manifest.yaml").write_text("a: [unclosed\n")
    assert "not valid YAML" in rm.check_manifest(run_dir)[0]
    (run_dir / "manifest.yaml").write_text("- just\n- a list\n")
    assert rm.check_manifest(run_dir) == ["manifest.yaml is not a mapping"]


@pytest.mark.parametrize("path", rm.REQUIRED)
def test_the_check_refuses_a_missing_field(tmp_path, path):
    def drop(manifest):
        node = manifest
        *parents, last = path.split(".")
        for part in parents:
            node = node[part]
        del node[last]

    problems = checked(tmp_path, drop)

    assert f"missing field {path}" in problems


@pytest.mark.parametrize(
    "path", ["gateway.git_sha", "cache.tau_run", "generator.digest", "envelope"]
)
def test_the_check_treats_a_null_field_as_missing(tmp_path, path):
    def null(manifest):
        node = manifest
        *parents, last = path.split(".")
        for part in parents:
            node = node[part]
        node[last] = None

    assert f"missing field {path}" in checked(tmp_path, null)


def test_check_refuses_a_manifest_without_the_generator_prompt(tmp_path):
    # A manifest from before the prompt hash joined the generator block: the preflight could not tell
    # that the references and the run were made under two generator prompts.
    def drop(manifest):
        del manifest["generator"]["prompt_sha256"]

    def null(manifest):
        manifest["generator"]["prompt_sha256"] = None

    assert checked(tmp_path / "dropped", drop) == [
        "missing field generator.prompt_sha256"
    ]
    assert checked(tmp_path / "null", null) == ["missing field generator.prompt_sha256"]
    assert rm.REQUIRED.index("generator.prompt_sha256") == (
        rm.REQUIRED.index("generator.temperature") + 1
    )


def test_the_manifests_generator_block_has_the_six_fields_in_order(tmp_path):
    manifest, _, _, _ = built(tmp_path)
    assert list(manifest["generator"]) == [
        "model",
        "digest",
        "num_ctx",
        "think",
        "temperature",
        "prompt_sha256",
    ]


def test_the_check_accepts_false_and_zero_as_values(tmp_path):
    def falsy(manifest):
        manifest["gateway"]["dirty"] = False
        manifest["cache"]["capacity"] = 0
        manifest["generator"]["think"] = False

    assert checked(tmp_path, falsy) == []


def test_the_check_refuses_an_envelope_that_is_not_an_envelope_line(tmp_path):
    problems = checked(tmp_path, lambda m: m.update(envelope="all fine, trust me"))
    assert problems == ["envelope is not an ENVELOPE line"]


def test_the_check_refuses_a_record_whose_arm_differs_from_the_manifests(tmp_path):
    # The run was edited after the manifest: one record now says it ran the other support-gate arm.
    manifest, run_dir, _, _ = built(tmp_path)
    save(manifest, run_dir)
    path = run_dir / "raw" / "requests.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[1]["support_gate"] = "off"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))

    problems = rm.check_manifest(run_dir)

    assert problems == ["the records differ on support_gate: ['\"off\"', '\"on\"']"]


def test_the_check_refuses_arms_in_the_manifest_that_the_records_do_not_have(tmp_path):
    def other_arm(manifest):
        manifest["arms"]["support_gate"] = "off"
        manifest["arms"]["mutation"] = "on"

    problems = checked(tmp_path, other_arm)

    assert "the records say support_gate='on', the manifest says 'off'" in problems
    assert "the records say mutation='off', the manifest says 'on'" in problems


def test_the_check_refuses_a_record_count_that_is_not_the_files(tmp_path):
    problems = checked(tmp_path, lambda m: m["records"].update(count=5))
    assert problems == ["the manifest counts 5 records, requests.jsonl has 4"]


def test_the_check_refuses_a_manifest_of_another_runs_folder(tmp_path):
    problems = checked(tmp_path, lambda m: m.update(run_id="another-run"))
    assert problems == [f"run_id another-run is not the folder's {RUN_ID}"]


def test_the_check_refuses_a_log_of_another_run(tmp_path):
    manifest, run_dir, _, _ = built(tmp_path)
    save(manifest, run_dir)
    other = tmp_path / "other.log"
    other.write_text(GOOD_LOG.replace(RUN_ID, "another-run"))

    problems = rm.check_manifest(run_dir, other)

    assert len(problems) == 1 and problems[0].startswith("gateway log:")
    assert "is for run another-run" in problems[0]


@pytest.mark.parametrize(
    "old, new, key, log_says",
    [
        ("support_gate=on", "support_gate=off", "support_gate", "off"),
        ("mixed_lane=off", "mixed_lane=on", "mixed_lane", "on"),
    ],
)
def test_the_check_refuses_a_log_whose_arm_differs_from_the_records(
    tmp_path, old, new, key, log_says
):
    manifest, run_dir, _, _ = built(tmp_path)
    save(manifest, run_dir)
    other = tmp_path / "other.log"
    other.write_text(GOOD_LOG.replace(old, new))

    problems = rm.check_manifest(run_dir, other)

    assert problems == [
        f"the gateway log says {key}={log_says}, the records say {old.split('=')[1]}"
    ]


def test_the_check_reports_every_problem_it_finds(tmp_path):
    def several(manifest):
        del manifest["redis"]["redis_version"]
        manifest["arms"]["config_id"] = 5
        manifest["records"]["count"] = 99

    assert len(checked(tmp_path, several)) == 3


def test_the_check_passes_a_manifest_that_says_not_admissible(tmp_path):
    # Inadmissible is a fact the manifest records, not a malformed manifest: `judge` refuses it.
    def inadmissible(manifest):
        manifest["admissibility"]["i9"] = False
        manifest["admissibility"]["admissible"] = False

    assert checked(tmp_path, inadmissible) == []


# =================================================================================================
# write and the command line
# =================================================================================================
def write_args(tmp_path, **kw):
    import argparse

    args = {
        "run_id": RUN_ID,
        "gateway_log": tmp_path / "gateway.log",
        "split": "validation",
        "results_dir": tmp_path / "results",
        "frozen_np": 1,
        "ollama_version": "0.33.2",
        "llm_blob": "sha256-" + "7" * 64,
        "cache_ram": 0,
        "ctx_checkpoints": 0,
    }
    args.update(kw)
    return argparse.Namespace(**args)


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """The machine's facts faked: no listener on :8080, and the git, Redis, envelope and Ollama reads."""
    repo = make_repo(tmp_path)
    monkeypatch.setattr(rm.cache_reset, "listening_ports", lambda ports: [])
    monkeypatch.setattr(rm, "gateway_git", FAKES["git"])
    monkeypatch.setattr(rm, "redis_info", FAKES["redis_info"])
    monkeypatch.setattr(rm, "checked_envelope", lambda args: FAKES["envelope"]())
    monkeypatch.setattr(rm.refs, "generator_block", FAKES["ollama"])
    monkeypatch.setattr(
        rm, "build_manifest", functools.partial(rm.build_manifest, repo=repo)
    )
    write_run(tmp_path / "results", good_records())
    (tmp_path / "gateway.log").write_text(GOOD_LOG)
    return tmp_path


def test_write_refuses_while_the_gateway_listens_on_8080(machine, monkeypatch):
    monkeypatch.setattr(rm.cache_reset, "listening_ports", lambda ports: [8080])
    with pytest.raises(rm.ManifestError, match="still listening on :8080"):
        rm.write(write_args(machine))
    assert not (machine / "results" / RUN_ID / "manifest.yaml").exists()


def test_write_refuses_a_manifest_that_exists_and_leaves_it_alone(machine):
    path = machine / "results" / RUN_ID / "manifest.yaml"
    path.write_text("manifest_version: 1\n")
    with pytest.raises(rm.ManifestError, match="a manifest is written once"):
        rm.write(write_args(machine))
    assert path.read_text() == "manifest_version: 1\n"


def test_write_writes_a_manifest_that_passes_the_check(machine, capsys):
    assert rm.write(write_args(machine)) == 0

    run_dir = machine / "results" / RUN_ID
    assert rm.check_manifest(run_dir, machine / "gateway.log") == []
    loaded = yaml.safe_load((run_dir / "manifest.yaml").read_text())
    assert list(loaded) == TOP_LEVEL_ORDER
    assert loaded["admissibility"]["admissible"] is True
    assert "admissible True" in capsys.readouterr().out


def test_write_says_which_rule_a_run_breaks(machine, capsys):
    (machine / "gateway.log").write_text(START_LOG)  # a killed gateway
    assert rm.write(write_args(machine)) == 0
    out = capsys.readouterr().out
    assert "NOT ADMISSIBLE: rule_6" in out


def test_write_refuses_a_log_of_another_arm_and_writes_nothing(machine):
    (machine / "gateway.log").write_text(
        GOOD_LOG.replace("support_gate=on", "support_gate=off")
    )
    with pytest.raises(rm.ManifestError, match="log says support_gate=off"):
        rm.write(write_args(machine))
    assert not (machine / "results" / RUN_ID / "manifest.yaml").exists()


def test_write_refuses_a_run_that_has_no_records(machine):
    (machine / "results" / RUN_ID / "raw" / "requests.jsonl").write_text("")
    with pytest.raises(rm.ManifestError, match="no records"):
        rm.write(write_args(machine))


def test_the_check_command_exits_0_for_a_good_manifest_and_1_for_a_bad_one(
    machine, capsys
):
    rm.write(write_args(machine))
    results = str(machine / "results")

    assert rm.main(["check", "--run-id", RUN_ID, "--results-dir", results]) == 0
    assert "run-manifest-check: ok" in capsys.readouterr().out

    path = machine / "results" / RUN_ID / "manifest.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest_bad = copy.deepcopy(manifest)
    del manifest_bad["workload"]["sha256"]
    path.write_text(yaml.safe_dump(manifest_bad, sort_keys=False))

    assert rm.main(["check", "--run-id", RUN_ID, "--results-dir", results]) == 1
    out = capsys.readouterr().out
    assert "FAIL  missing field workload.sha256" in out and "1 problem(s)" in out


def test_the_check_command_given_a_log_refuses_the_log_of_another_arm(machine, capsys):
    rm.write(write_args(machine))
    other = machine / "other.log"
    other.write_text(GOOD_LOG.replace("support_gate=on", "support_gate=off"))

    code = rm.main(
        [
            "check",
            "--run-id",
            RUN_ID,
            "--results-dir",
            str(machine / "results"),
            "--gateway-log",
            str(other),
        ]
    )

    assert code == 1
    assert "the gateway log says support_gate=off" in capsys.readouterr().out


def test_the_check_command_exits_1_when_the_run_has_no_records(tmp_path, capsys):
    (tmp_path / "results" / RUN_ID).mkdir(parents=True)
    (tmp_path / "results" / RUN_ID / "manifest.yaml").write_text(
        "manifest_version: 1\n"
    )
    assert (
        rm.main(
            ["check", "--run-id", RUN_ID, "--results-dir", str(tmp_path / "results")]
        )
        == 1
    )
    assert "FAIL" in capsys.readouterr().out


def test_the_gateway_git_function_gives_a_sha_and_a_dirty_flag(monkeypatch):
    monkeypatch.setattr(
        rm.corpus_gate,
        "git_state",
        lambda paths: {"commit": "c" * 40, "tree_clean": False, "paths": list(paths)},
    )
    assert rm.gateway_git() == {"git_sha": "c" * 40, "dirty": True}
    monkeypatch.setattr(
        rm.corpus_gate, "git_state", lambda paths: {"commit": None, "tree_clean": False}
    )
    with pytest.raises(rm.ManifestError, match="git commit"):
        rm.gateway_git()


def test_the_manifest_module_reads_no_path_outside_the_repository_and_the_run(tmp_path):
    # `repo` is the only place the repository's data is read from: a manifest built against a temp
    # repository must not touch the real data/ folder.
    manifest, _, _, repo = built(tmp_path)
    assert manifest["workload"]["sha256"] == rm.refs.sha256_file(
        Path(repo) / "data" / "workload-v1-validation.json"
    )
