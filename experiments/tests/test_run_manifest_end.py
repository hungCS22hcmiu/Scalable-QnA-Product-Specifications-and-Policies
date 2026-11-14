"""Rule 6 reads the line the gateway prints last, and the gateway still prints every line rule 6 reads.

Commit `29da622` renamed the gateway's shutdown line, and `run_manifest.py` kept looking for the old
text, so every run after it read as inadmissible (design.md §4 of
docs/work/2026-11-13-tier2-scope-by-evidence). The fix: the gateway prints `gateway: run ended cleanly`
as its last line, only when nothing was lost, and rule 6 also fails on the two warnings `29da622` added.
The last test reads `gateway/cmd/gateway/main.go`, so a renamed line fails here instead of in a run.
"""

import pathlib

import pytest
import run_manifest as rm

RUN_ID = "2026-11-14T02-00-00_cfg4_scope-off"
START = f"""\
2026/11/14 02:00:01 gateway: tau=0.850 theta=0.60 dim=768 index=idx:cache  (all DEMO values, swept later)
2026/11/14 02:00:01 gateway: lane_band=[0.20,0.20) mixed_lane=off scope_arm=off tau_p=n/a (pinned, ADR-016; scope arm: ADR-030)
2026/11/14 02:00:01 gateway: cache_capacity=156  entries, LRU, enforced by the gateway (see cache/capacity.go)
2026/11/14 02:00:01 gateway: evaluation log -> /x/experiments/results/{RUN_ID}/raw/requests.jsonl, answer text -> raw/answers/
2026/11/14 02:00:01 gateway: support_gate=off  -- the ABLATION ARM
"""
SHUTDOWN = (
    "2026/11/14 03:00:00 gateway: shutting down: no new requests; waiting up to 1m0s for in-flight "
    "ones (Ctrl-C again to force)\n"
)
ENDED = (
    "2026/11/14 03:00:01 gateway: run ended cleanly -- every request finished, the dependency map "
    "closed with nothing lost, the evaluation log is complete\n"
)
IN_FLIGHT = (
    "2026/11/14 03:01:00 gateway: WARNING requests still in flight after 1m0s (context deadline "
    "exceeded). Their records are lost uncounted\n"
)
DEPS_INCOMPLETE = (
    "2026/11/14 03:01:01 gateway: the dependency map is INCOMPLETE: 1 registration(s) dropped after "
    "close, 0 registration write(s) failed, 0 purge call(s) failed.\n"
)
NOT_CLEAN = (
    "2026/11/14 03:01:02 gateway: the run did not end cleanly (see the lines above), so rule 6 will "
    "not admit it\n"
)
SHA = "a" * 64
RECORDS = [
    {"request_id": "req-01", "cache": "MISS", "entry_id": "E1", "answer_sha256": SHA},
    {
        "request_id": "req-02",
        "cache": "TIER2_HIT",
        "entry_id": "E1",
        "answer_sha256": SHA,
    },
]


def rule_6(text):
    return rm.admissibility(RECORDS, rm.parse_gateway_log(text, RUN_ID))["rule_6"]


def test_a_clean_end_is_admitted():
    assert rule_6(START + SHUTDOWN + ENDED) is True


def test_the_shutdown_line_alone_is_not_an_end():
    # The 2026-11-14 01-11-46 run's case before the fix, and a second Ctrl-C after it: records lost,
    # no INCOMPLETE line.
    assert rule_6(START + SHUTDOWN) is False


@pytest.mark.parametrize("bad", [IN_FLIGHT, DEPS_INCOMPLETE], ids=["in-flight", "deps"])
def test_a_warning_of_29da622_voids_the_run(bad):
    assert rule_6(START + SHUTDOWN + bad + NOT_CLEAN) is False
    # Even if an end line were also present, the warning wins.
    assert rule_6(START + SHUTDOWN + bad + ENDED) is False


def test_the_not_clean_line_is_not_read_as_an_end():
    assert rule_6(START + SHUTDOWN + NOT_CLEAN) is False


def test_the_parse_keeps_its_keys():
    log = rm.parse_gateway_log(START + SHUTDOWN + ENDED, RUN_ID)
    assert (log["ended"], log["incomplete"]) == (True, False)
    log = rm.parse_gateway_log(START + SHUTDOWN + IN_FLIGHT, RUN_ID)
    assert (log["ended"], log["incomplete"]) == (False, True)


def test_the_gateway_prints_every_line_rule_6_reads():
    main_go = (
        pathlib.Path(__file__).resolve().parents[2]
        / "gateway"
        / "cmd"
        / "gateway"
        / "main.go"
    ).read_text()
    current_end, pre_29da622_end = rm.ENDED_LINES
    assert f'runEndedLine = "{current_end}"' in main_go
    assert pre_29da622_end not in main_go  # kept only for logs written before `29da622`
    for line in rm.BAD_LINES:
        assert f'"{line}' in main_go, f"main.go no longer prints {line!r}"
