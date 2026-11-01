"""Item 5.1 (docs/work/2026-10-30-judge-harness/design.md): the replay sender.

`replay` must send each query once, in an order a second run can repeat, with what the gateway reads:
the question, `product_id` only when the query has one, and the stratum header. A request that carried
a `product_id` the workload did not give would change the Tier-1 key and the retrieval scope (ADR-018),
and the run would not be the workload's.

No gateway, no network: the sender is a fake function, and `urlopen` is faked for the HTTP wrapper.
"""

import io
import json
import urllib.error
from collections import Counter

import pytest
import replay as rp


def queries(n=10):
    out = []
    for i in range(n):
        q = {
            "qa_id": f"q-{i}",
            "question": f"Question {i}?",
            "stratum": ["A", "B-within", "C", "D", "B-cross"][i % 5],
        }
        if i % 3:  # some queries have a product, some have none
            q["product_id"] = f"product-{i}"
        elif i % 2:
            q["product_id"] = ""
        else:
            q["product_id"] = None
        out.append(q)
    return out


class Sender:
    """Records each request; answers 200 with a cache value unless told otherwise."""

    def __init__(self, status=200, cache="MISS", fail_on=()):
        self.calls = []
        self.status = status
        self.cache = cache
        self.fail_on = set(fail_on)

    def __call__(self, url, body, headers, timeout):
        self.calls.append(
            {"url": url, "body": body, "headers": headers, "timeout": timeout}
        )
        if len(self.calls) in self.fail_on:
            raise ConnectionRefusedError("gateway down")
        return self.status, (
            {"cache": self.cache} if self.status == 200 else {"error": "busy"}
        )


def run(qs, sender, seed=7, pressure=lambda: 1, url="http://localhost:8080"):
    lines = []
    counts = rp.replay(
        "validation",
        url,
        seed,
        queries=qs,
        post=sender,
        pressure=pressure,
        log=lines.append,
    )
    return counts, lines


def test_the_same_seed_gives_the_same_order():
    qs = queries(40)
    first, second = Sender(), Sender()

    run(qs, first, seed=7)
    run(qs, second, seed=7)

    assert [c["body"]["question"] for c in first.calls] == [
        c["body"]["question"] for c in second.calls
    ]


def test_another_seed_gives_another_order_and_neither_is_the_files_order():
    qs = queries(40)
    seven, eight = Sender(), Sender()

    run(qs, seven, seed=7)
    run(qs, eight, seed=8)

    asked = lambda s: [c["body"]["question"] for c in s.calls]
    assert asked(seven) != asked(eight)
    assert asked(seven) != [q["question"] for q in qs]  # it is shuffled


def test_the_order_function_is_pure_and_repeatable():
    qs = queries(30)
    before = [q["qa_id"] for q in qs]

    a, b = rp.order(qs, 7), rp.order(qs, 7)

    assert [q["qa_id"] for q in qs] == before  # the input is not shuffled in place
    assert a == b and sorted(q["qa_id"] for q in a) == sorted(before)


def test_every_query_is_sent_once_and_only_once():
    qs = queries(37)
    sender = Sender()

    counts, _ = run(qs, sender)

    asked = [c["body"]["question"] for c in sender.calls]
    assert sorted(asked) == sorted(q["question"] for q in qs)
    assert len(asked) == len(set(asked)) == 37
    assert counts["sent"] == 37


def test_the_stratum_header_is_sent_with_each_query():
    qs = queries(10)
    sender = Sender()

    run(qs, sender)

    stratum = {q["question"]: q["stratum"] for q in qs}
    for call in sender.calls:
        assert call["headers"]["X-Thesis-Stratum"] == stratum[call["body"]["question"]]
        assert call["headers"]["Content-Type"] == "application/json"


def test_no_product_id_key_is_sent_when_it_is_empty_or_absent():
    qs = queries(12)
    qs.append({"qa_id": "q-bare", "question": "No product key at all?", "stratum": "C"})
    sender = Sender()

    run(qs, sender)

    product = {q["question"]: q.get("product_id") for q in qs}
    kinds = Counter()
    for call in sender.calls:
        wanted = product[call["body"]["question"]]
        if wanted:
            assert call["body"] == {
                "question": call["body"]["question"],
                "product_id": wanted,
            }
            kinds["with"] += 1
        else:
            assert call["body"] == {
                "question": call["body"]["question"]
            }  # no key, not null, not ""
            assert "product_id" not in call["body"]
            kinds["without"] += 1
    assert (
        kinds["with"] > 0 and kinds["without"] >= 3
    )  # None, "" and absent were all exercised


def test_the_body_holds_only_the_question_and_the_product():
    body, headers = rp.request_for(
        {
            "question": "q?",
            "product_id": "p",
            "stratum": "A",
            "doc_ids": ["x"],
            "qa_id": "n",
        }
    )
    assert body == {
        "question": "q?",
        "product_id": "p",
    }  # no gold label reaches the system
    assert headers == {"Content-Type": "application/json", "X-Thesis-Stratum": "A"}


def test_a_query_without_a_stratum_sends_no_stratum_header():
    _, headers = rp.request_for({"question": "q?"})
    assert "X-Thesis-Stratum" not in headers


def test_the_request_goes_to_ask_and_a_trailing_slash_is_not_doubled():
    for url in ("http://localhost:8080", "http://localhost:8080/"):
        sender = Sender()
        run(queries(3), sender, url=url)
        assert {c["url"] for c in sender.calls} == {"http://localhost:8080/ask"}


def test_it_sends_one_request_at_a_time():
    in_flight = []

    def sender(url, body, headers, timeout):
        in_flight.append(1)
        assert sum(in_flight) == 1  # nothing else is running while this call is
        in_flight.pop()
        return 200, {"cache": "MISS"}

    counts, _ = run(queries(20), sender)
    assert counts["sent"] == 20


def test_the_counts_say_what_the_gateway_answered():
    sender = Sender(cache="TIER2_HIT")
    counts, _ = run(queries(6), sender)
    assert (
        counts["http_200"] == 6
        and counts["cache_TIER2_HIT"] == 6
        and counts["errors"] == 0
    )


def test_a_shed_is_counted_as_a_503_and_not_as_an_error():
    counts, _ = run(queries(5), Sender(status=503))
    assert counts["http_503"] == 5 and counts["errors"] == 0 and counts["sent"] == 5
    assert counts["cache_MISS"] == 0  # a shed has no cache value


def test_a_connection_failure_is_counted_and_the_replay_goes_on():
    counts, _ = run(queries(6), Sender(fail_on={2, 4}))
    assert counts["errors"] == 2 and counts["http_200"] == 4 and counts["sent"] == 6


def test_progress_and_pressure_are_printed_every_50_requests():
    readings = []

    def pressure():
        readings.append(1)
        return 1

    _, lines = run(queries(120), Sender(), pressure=pressure)

    assert len(readings) == 4  # at the start, at 50, at 100, and at the end (120)
    progress = [line for line in lines if "sent; pressure level" in line]
    assert [line.split("/")[0].strip() for line in progress] == ["50", "100", "120"]
    assert any("memory pressure level: 1" in line for line in lines)


def test_it_stops_at_pressure_4_before_the_first_request():
    sender = Sender()
    with pytest.raises(rp.ReplayStopped, match="critical"):
        run(queries(10), sender, pressure=lambda: 4)
    assert sender.calls == []


def test_it_stops_when_pressure_reaches_4_during_the_replay():
    readings = iter([1, 4])
    sender = Sender()
    with pytest.raises(rp.ReplayStopped, match="after 50 requests"):
        run(queries(120), sender, pressure=lambda: next(readings))
    assert len(sender.calls) == 50


def test_pressure_2_is_reported_and_the_replay_goes_on():
    sender = Sender()
    counts, lines = run(queries(60), sender, pressure=lambda: 2)
    assert counts["sent"] == 60
    assert any("pressure level 2" in line for line in lines)


# --- the HTTP wrapper -------------------------------------------------------------------------------
class Response:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_http_post_sends_json_with_the_headers_and_returns_status_and_body(monkeypatch):
    seen = []

    def fake_urlopen(req, timeout):
        seen.append((req, timeout))
        return Response({"cache": "MISS"})

    monkeypatch.setattr(rp.urllib.request, "urlopen", fake_urlopen)

    status, body = rp.http_post(
        "http://x/ask",
        {"question": "q?"},
        {"Content-Type": "application/json", "X-Thesis-Stratum": "B-within"},
        9.0,
    )

    req, timeout = seen[0]
    assert (status, body, timeout) == (200, {"cache": "MISS"}, 9.0)
    assert req.get_method() == "POST" and json.loads(req.data) == {"question": "q?"}
    assert req.get_header("X-thesis-stratum") == "B-within"


def test_http_post_returns_a_503_as_a_status_with_its_body(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url, 503, "busy", {}, io.BytesIO(b'{"error":"busy, retry"}')
        )

    monkeypatch.setattr(rp.urllib.request, "urlopen", fake_urlopen)

    assert rp.http_post("http://x/ask", {}, {}, 1.0) == (503, {"error": "busy, retry"})


def test_http_post_returns_none_for_an_error_body_that_is_not_json(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url, 502, "bad", {}, io.BytesIO(b"<html>oops</html>")
        )

    monkeypatch.setattr(rp.urllib.request, "urlopen", fake_urlopen)

    assert rp.http_post("http://x/ask", {}, {}, 1.0) == (502, None)


# --- the command line -------------------------------------------------------------------------------
def test_the_command_exits_1_when_a_request_failed_and_0_when_none_did(
    monkeypatch, capsys
):
    monkeypatch.setattr(rp, "replay", lambda *a, **k: Counter(sent=3, http_200=3))
    assert rp.main(["--split", "validation"]) == 0

    monkeypatch.setattr(
        rp, "replay", lambda *a, **k: Counter(sent=3, http_200=2, errors=1)
    )
    assert rp.main(["--split", "validation"]) == 1
    assert "errors" in capsys.readouterr().out


def test_the_command_exits_1_when_the_replay_stopped(monkeypatch, capsys):
    def stopped(*a, **k):
        raise rp.ReplayStopped("memory pressure is critical (4)")

    monkeypatch.setattr(rp, "replay", stopped)
    assert rp.main(["--split", "validation"]) == 1
    assert "STOPPED" in capsys.readouterr().err


def test_the_command_passes_the_split_url_and_seed_on(monkeypatch):
    seen = []
    monkeypatch.setattr(rp, "replay", lambda *a, **k: seen.append(a) or Counter())
    rp.main(["--split", "validation", "--url", "http://h:1", "--seed", "11"])
    assert seen == [("validation", "http://h:1", 11)]
