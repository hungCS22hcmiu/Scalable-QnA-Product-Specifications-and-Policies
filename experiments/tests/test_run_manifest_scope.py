"""Item 6.0a (ADR-030): the manifest names the scope arm and checks it against the gateway's start-up line.

`scope_arm` is on every record from item 6.0a, and the gateway prints it next to `mixed_lane=` at start
(`scope_arm=on tau_p=0.8123`). A run whose records say one arm and whose log says the other is the
silent failure ADR-010 guards: the trial would compare two runs under the wrong labels. A run from
before the arm has neither, and keeps its four arms.
"""

import json

import pytest
import run_manifest as rm
import yaml

RUN_ID = "2026-11-13T10-00-00_cfg4_scope-on"
SHA = "a" * 64
LOG = f"""\
2026/11/13 10:00:01 gateway: tau=0.850 theta=0.60 dim=768 index=idx:cache  (all DEMO values, swept later)
2026/11/13 10:00:01 gateway: lane_band=[0.20,0.20) mixed_lane=off scope_arm={{arm}} tau_p={{tau_p}} (pinned, ADR-016; scope arm: ADR-030)
2026/11/13 10:00:01 gateway: cache_capacity=156  entries, LRU, enforced by the gateway (see cache/capacity.go)
2026/11/13 10:00:01 gateway: evaluation log -> /x/experiments/results/{RUN_ID}/raw/requests.jsonl, answer text -> raw/answers/
2026/11/13 10:00:01 gateway: support_gate=off  -- the ABLATION ARM
2026/11/13 11:00:00 gateway: shutting down, flushing the evaluation log
"""
OLD_LOG = LOG.replace(" scope_arm={arm} tau_p={tau_p}", "")


def log_for(arm, tau_p="0.8123"):
    return LOG.replace("{arm}", arm).replace("{tau_p}", tau_p)


def record(i, cache="MISS", entry="E1", **extra):
    r = {
        "request_id": f"req-{i:02d}",
        "run_id": RUN_ID,
        "config_id": 4,
        "mutation": "off",
        "support_gate": "off",
        "mixed_lane": "off",
        "cache": cache,
        "entry_id": entry,
        "answer_sha256": SHA,
    }
    r.update(extra)
    return r


def records(arm):
    extra = {} if arm is None else {"scope_arm": arm}
    return [record(1, "MISS", "E1", **extra), record(2, "TIER2_HIT", "E1", **extra)]


def write_run(tmp_path, recs):
    run_dir = tmp_path / "results" / RUN_ID
    (run_dir / "raw").mkdir(parents=True)
    (run_dir / "raw" / "requests.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in recs)
    )
    return run_dir


def test_the_arm_is_read_from_the_records():
    assert rm.arms(records("on"))["scope_arm"] == "on"
    assert rm.arms(records("off"))["scope_arm"] == "off"


def test_an_older_run_has_no_scope_arm_and_keeps_four_arms():
    assert "scope_arm" not in rm.arms(records(None))


def test_records_that_differ_on_the_arm_are_refused():
    mixed = [record(1, scope_arm="on"), record(2, "TIER2_HIT", scope_arm="off")]
    with pytest.raises(rm.ManifestError, match="differ on scope_arm"):
        rm.arms(mixed)
    one_missing = [record(1, scope_arm="on"), record(2, "TIER2_HIT")]
    with pytest.raises(rm.ManifestError, match="differ on scope_arm"):
        rm.arms(one_missing)


def test_the_log_parse_reads_the_arm_and_omits_it_for_an_older_log():
    assert rm.parse_gateway_log(log_for("on"), RUN_ID)["scope_arm"] == "on"
    assert rm.parse_gateway_log(log_for("off", "n/a"), RUN_ID)["scope_arm"] == "off"
    assert "scope_arm" not in rm.parse_gateway_log(OLD_LOG, RUN_ID)


def test_a_log_with_two_arms_is_refused():
    two = log_for("on") + log_for("off").splitlines()[1] + "\n"
    with pytest.raises(rm.ManifestError, match="2 values for scope_arm"):
        rm.parse_gateway_log(two, RUN_ID)


@pytest.mark.parametrize("arm", ["on", "off"])
def test_the_check_passes_when_records_and_log_agree(tmp_path, arm):
    run_dir = write_run(tmp_path, records(arm))
    log = tmp_path / "gateway.log"
    log.write_text(log_for(arm))
    manifest = {
        "run_id": RUN_ID,
        "arms": rm.arms(records(arm)),
        "records": {"count": 2},
    }
    problems = rm.manifest_problems(manifest, run_dir, log)
    assert not [p for p in problems if "scope_arm" in p]


def test_the_check_refuses_when_the_log_and_the_records_disagree(tmp_path):
    run_dir = write_run(tmp_path, records("off"))
    log = tmp_path / "gateway.log"
    log.write_text(log_for("on"))
    manifest = {
        "run_id": RUN_ID,
        "arms": rm.arms(records("off")),
        "records": {"count": 2},
    }
    problems = rm.manifest_problems(manifest, run_dir, log)
    assert any("log says scope_arm=on, the records say off" in p for p in problems)


def test_the_check_refuses_a_log_with_the_arm_and_records_without_it(tmp_path):
    run_dir = write_run(tmp_path, records(None))
    log = tmp_path / "gateway.log"
    log.write_text(log_for("on"))
    manifest = {
        "run_id": RUN_ID,
        "arms": rm.arms(records(None)),
        "records": {"count": 2},
    }
    problems = rm.manifest_problems(manifest, run_dir, log)
    assert any("scope_arm" in p for p in problems)


def test_the_check_refuses_a_manifest_that_says_another_arm_than_the_records(tmp_path):
    run_dir = write_run(tmp_path, records("on"))
    manifest = {
        "run_id": RUN_ID,
        "arms": {**rm.arms(records("on")), "scope_arm": "off"},
        "records": {"count": 2},
    }
    problems = rm.manifest_problems(manifest, run_dir)
    assert any(
        "the records say scope_arm='on', the manifest says 'off'" in p for p in problems
    )


def test_build_manifest_refuses_a_log_of_another_arm(tmp_path):
    run_dir = write_run(tmp_path, records("on"))
    log = tmp_path / "gateway.log"
    log.write_text(log_for("off", "n/a"))
    with pytest.raises(
        rm.ManifestError, match="log says scope_arm=off but the records say on"
    ):
        rm.build_manifest(
            run_dir,
            log,
            "validation",
            git=dict,
            redis_info=dict,
            envelope=lambda: "ENVELOPE x",
            ollama=dict,
            repo=tmp_path,
        )


def test_an_older_run_still_checks_without_a_scope_arm(tmp_path):
    run_dir = write_run(tmp_path, records(None))
    log = tmp_path / "gateway.log"
    log.write_text(OLD_LOG)
    manifest = {
        "run_id": RUN_ID,
        "arms": rm.arms(records(None)),
        "records": {"count": 2},
    }
    problems = rm.manifest_problems(manifest, run_dir, log)
    assert not [p for p in problems if "scope_arm" in p]


def test_the_generator_prompt_hash_in_the_manifest_is_the_served_one(monkeypatch):
    from rag import generate

    monkeypatch.setattr(
        rm.refs,
        "generator_block",
        lambda: {"model": "m", "prompt_sha256": "old-template-hash"},
    )
    block = rm.generator_block()
    assert block["prompt_sha256"] == generate.prompt_sha256()
    assert yaml.safe_dump(block)  # a plain dict that dumps as YAML
