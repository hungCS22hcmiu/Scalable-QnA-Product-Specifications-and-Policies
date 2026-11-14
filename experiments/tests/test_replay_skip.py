"""Item 6.0a (ADR-025's decision, design.md 3.3 A): the replay command skips a query with no
`product_id` and counts it.

The gateway refuses such a query with a 400 (ADR-025), so sending it would only add an error outcome.
Validation has 16 of them and the test split has none. The two arms of the scope trial must see the
same sequence, so the seeded order is drawn over the queries that remain, and it must not change
when a skipped query is added or removed.
"""

from collections import Counter

import replay as rp


def queries(n=12):
    """Queries 3, 7 and 11 have no product: an empty string, None, and no key at all."""
    out = []
    for i in range(n):
        q = {"qa_id": f"q-{i}", "question": f"Question {i}?", "stratum": "A"}
        if i == 3:
            q["product_id"] = ""
        elif i == 7:
            q["product_id"] = None
        elif i != 11:
            q["product_id"] = f"product-{i}"
        out.append(q)
    return out


class Sender:
    def __init__(self):
        self.asked = []

    def __call__(self, url, body, headers, timeout):
        self.asked.append(body["question"])
        return 200, {"cache": "MISS"}


def run(qs, **kw):
    sender = Sender()
    lines = []
    counts = rp.replay(
        "validation",
        "http://localhost:8080",
        7,
        queries=qs,
        post=sender,
        pressure=lambda: 1,
        log=lines.append,
        **kw,
    )
    return counts, sender.asked, lines


def test_a_query_without_a_product_id_is_not_sent_and_is_counted():
    qs = queries()
    counts, asked, lines = run(qs, skip_no_product_id=True)

    assert counts["skipped_no_product_id"] == 3
    assert counts["sent"] == len(asked) == 9
    assert not set(asked) & {"Question 3?", "Question 7?", "Question 11?"}
    assert any("3 skipped" in line for line in lines)


def test_the_summary_says_zero_when_nothing_is_skipped():
    qs = [q for q in queries() if q.get("product_id")]
    counts, asked, _ = run(qs, skip_no_product_id=True)
    assert counts["skipped_no_product_id"] == 0
    assert counts["sent"] == len(asked) == len(qs)
    assert (
        "skipped_no_product_id" in counts
    )  # present, as 0, so a test split reads "0 skipped"


def test_without_the_flag_every_query_is_sent_and_nothing_is_counted_as_skipped():
    qs = queries()
    counts, asked, _ = run(qs)
    assert counts["sent"] == len(asked) == len(qs)
    assert "skipped_no_product_id" not in counts


def test_the_order_of_the_others_does_not_depend_on_the_skipped_queries():
    full = queries()
    kept = [q for q in full if q.get("product_id")]
    _, with_skipped, _ = run(full, skip_no_product_id=True)
    _, without, _ = run(kept, skip_no_product_id=True)
    assert (
        with_skipped == without
    )  # the same sequence, whatever the skipped queries are or where


def test_the_command_turns_the_exclusion_on(monkeypatch):
    seen = []
    monkeypatch.setattr(rp, "replay", lambda *a, **k: seen.append(k) or Counter())
    rp.main(["--split", "validation"])
    assert seen == [{"skip_no_product_id": True}]
