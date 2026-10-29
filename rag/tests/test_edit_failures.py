"""Item 4.4, done condition 3: a failed purge is loud, and a second run is safe.

With the gateway down, or a non-200 reply, the edit tool exits non-zero and names the chunk. A
re-run on a chunk that already holds the new text writes it again, advances the epoch again and
posts again, so the purge that failed is tried again. A chunk that holds some OTHER text is not
touched at all. No Redis, no Ollama, no gateway: fakes and an httpx MockTransport.
"""

import json

import httpx
import pytest

from rag import edit, epoch

BEFORE = "Returns are accepted within 30 days."
AFTER = "Returns are accepted within 14 days."
CHUNK = "policy-return#chunk-0"
KEY = f"corpus::{CHUNK}"


class FakeRedis:
    """Just enough of redis.Redis for redis_writer: a dict of hashes."""

    def __init__(self, hashes):
        self.hashes = hashes
        self.hset_calls = 0

    def hmget(self, key, fields):
        h = self.hashes.get(key)
        if h is None:
            return [None for _ in fields]
        return [h.get(f) for f in fields]

    def hset(self, key, mapping):
        self.hset_calls += 1
        self.hashes[key].update(mapping)


class Counter:
    def __init__(self):
        self.advances = 0
        self.posts: list[dict] = []

    def advance(self) -> int:
        self.advances += 1
        return 10 + self.advances

    def post(self, event):
        self.posts.append(event)
        return {"chunk_id": event["chunk_id"], "purged": [], "failed": [], "errors": []}


def an_edit() -> edit.Edit:
    return edit.Edit("edit-001", "policy-return", CHUNK, "substantive", BEFORE, AFTER)


def redis_with(text: bytes | None) -> FakeRedis:
    if text is None:
        return FakeRedis({})
    return FakeRedis({KEY: {"text": text, "vector": b"old-vector"}})


@pytest.fixture
def update_set(tmp_path):
    path = tmp_path / "update-set.json"
    path.write_text(
        json.dumps(
            [
                {
                    "edit_id": "edit-001",
                    "doc_id": "policy-return",
                    "chunk_id": CHUNK,
                    "change_type": "substantive",
                    "before": BEFORE,
                    "after": AFTER,
                    "expected_effect": "answers about the return window go stale",
                }
            ]
        )
    )
    return path


@pytest.fixture
def epoch_env(tmp_path, monkeypatch):
    monkeypatch.setenv(epoch.ENV, str(tmp_path / "dataset-epoch"))


def ops_with_post(post):
    """make_ops with a fake write, advance and embed, and the given post."""
    fake = redis_with(BEFORE.encode())

    def make_ops(_gateway_url):
        return edit.redis_writer(fake), Counter().advance, post, lambda text: b"vec"

    return make_ops


def test_post_transport_error_exits_nonzero_naming_the_chunk(update_set, epoch_env, capsys):
    # The real make_post against a port nothing listens on: the gateway is down.
    post = edit.make_post("http://127.0.0.1:1", timeout=2.0)
    code = edit.main(
        [
            "--update-set",
            str(update_set),
            "--edit-id",
            "edit-001",
            "--gateway",
            "http://127.0.0.1:1",
        ],
        make_ops=ops_with_post(post),
    )

    assert code != 0
    assert CHUNK in capsys.readouterr().err


def test_post_500_exits_nonzero_naming_the_chunk(update_set, epoch_env, capsys):
    def reply_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500, json={"chunk_id": CHUNK, "purged": [], "failed": ["e2"], "errors": []}
        )

    post = edit.make_post("http://gateway.invalid", transport=httpx.MockTransport(reply_500))
    code = edit.main(
        [
            "--update-set",
            str(update_set),
            "--edit-id",
            "edit-001",
            "--gateway",
            "http://gateway.invalid",
        ],
        make_ops=ops_with_post(post),
    )

    err = capsys.readouterr().err
    assert code != 0
    assert CHUNK in err
    assert "500" in err
    assert "e2" in err  # the failed entry_id reaches the operator


def test_rerun_on_after_text_advances_and_posts_again():
    fake = redis_with(AFTER.encode())  # a first run already wrote the new text
    c = Counter()

    applied = edit.apply(
        an_edit(),
        write=edit.redis_writer(fake),
        advance=c.advance,
        post=c.post,
        embed=lambda t: b"v",
    )

    assert applied.old_text == AFTER
    assert fake.hset_calls == 1
    assert fake.hashes[KEY]["text"] == AFTER
    assert c.advances == 1  # the epoch moves again
    assert len(c.posts) == 1  # and the purge is tried again


def test_foreign_text_is_refused_before_any_side_effect():
    fake = redis_with(b"Someone else changed this chunk.")
    c = Counter()

    with pytest.raises(edit.EditError, match=CHUNK):
        edit.apply(
            an_edit(),
            write=edit.redis_writer(fake),
            advance=c.advance,
            post=c.post,
            embed=lambda t: b"v",
        )

    assert fake.hset_calls == 0  # no write
    assert fake.hashes[KEY]["text"] == b"Someone else changed this chunk."
    assert c.advances == 0  # no advance
    assert c.posts == []  # no post


def test_missing_key_is_refused():
    fake = redis_with(None)
    c = Counter()

    with pytest.raises(edit.EditError, match=CHUNK):
        edit.apply(
            an_edit(),
            write=edit.redis_writer(fake),
            advance=c.advance,
            post=c.post,
            embed=lambda t: b"v",
        )

    assert fake.hset_calls == 0
    assert c.advances == 0 and c.posts == []


def test_relative_epoch_file_is_refused(update_set, monkeypatch, capsys):
    monkeypatch.setenv(epoch.ENV, "data/dataset-epoch")  # relative
    built = []

    def make_ops(_gateway_url):
        built.append(1)
        raise AssertionError("nothing may be built when the epoch path is refused")

    code = edit.main(
        [
            "--update-set",
            str(update_set),
            "--edit-id",
            "edit-001",
            "--gateway",
            "http://127.0.0.1:1",
        ],
        make_ops=make_ops,
    )

    assert code != 0
    assert built == []
    assert "relative" in capsys.readouterr().err
