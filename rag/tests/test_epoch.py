"""Item 4.2: the dataset epoch file and its start-up check (interfaces.md E, ADR-008).

The epoch is one integer in a file outside Redis. These tests use a file under tmp_path and need
no Redis, no model and no network. The failures they pin are silent ones: a lost advance makes a
later stale write-back carry an equal epoch, and a read that raises would turn a missing file into
a crash in the middle of an RPC instead of a loud refusal at start-up.
(docs/work/2026-10-28-epoch-guard/design.md section 3)
"""

import threading

import pytest

from rag import epoch, server


@pytest.fixture
def epoch_path(tmp_path, monkeypatch):
    path = tmp_path / "dataset-epoch"
    monkeypatch.setenv(epoch.ENV, str(path))
    return path


def test_advance_creates_a_missing_file_at_one(epoch_path):
    assert not epoch_path.exists()
    assert epoch.advance() == 1
    assert epoch_path.read_text().strip() == "1"
    assert epoch.read() == 1


def test_advance_increments_and_leaves_no_temp_file(epoch_path, tmp_path):
    epoch_path.write_text("4\n")
    assert epoch.advance() == 5
    assert epoch.advance() == 6
    assert epoch_path.read_text().strip() == "6"
    # Only the epoch file and its lock remain: the temp file was renamed over the old one.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dataset-epoch", "dataset-epoch.lock"]


def test_concurrent_advances_lose_nothing(epoch_path):
    returned: list[int] = []
    lock = threading.Lock()

    def worker():
        for _ in range(25):
            value = epoch.advance()
            with lock:
                returned.append(value)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert epoch.read() == 200
    # Every advance returned its own value: none was lost and none was handed out twice.
    assert sorted(returned) == list(range(1, 201))


@pytest.mark.parametrize("content", ["abc\n", "", "1.5\n"])
def test_advance_refuses_a_corrupt_file(epoch_path, content):
    epoch_path.write_text(content)
    with pytest.raises(epoch.EpochError):
        epoch.advance()
    # Never a silent reset to 1: that would make a stale stamp equal to the epoch again.
    assert epoch_path.read_text() == content


def test_read_returns_the_value(epoch_path):
    epoch_path.write_text("12\n")
    assert epoch.read() == 12
    epoch_path.write_text("  7  \n")
    assert epoch.read() == 7


@pytest.mark.parametrize("case", ["unset", "empty", "missing", "abc", "0", "-3"])
def test_read_returns_not_read_on_failure(epoch_path, monkeypatch, case):
    if case == "unset":
        monkeypatch.delenv(epoch.ENV)
    elif case == "empty":
        monkeypatch.setenv(epoch.ENV, "")
    elif case != "missing":
        epoch_path.write_text(case + "\n")
    # read() never raises, and 0 is never a real epoch.
    assert epoch.read() == epoch.NOT_READ == 0


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("unset", "not set"),
        ("empty", "empty"),
        ("relative", "relative"),
        ("missing", "does not exist"),
        ("abc", "not an integer"),
        ("0", "below 1"),
    ],
)
def test_check_refuses(epoch_path, monkeypatch, case, reason):
    if case == "unset":
        monkeypatch.delenv(epoch.ENV)
    elif case == "empty":
        monkeypatch.setenv(epoch.ENV, "")
    elif case == "relative":
        monkeypatch.setenv(epoch.ENV, "data/dataset-epoch")
    elif case != "missing":
        epoch_path.write_text(case + "\n")
    with pytest.raises(epoch.EpochError, match=reason):
        epoch.check()


def test_check_accepts_a_valid_file(epoch_path):
    epoch_path.write_text("3\n")
    assert epoch.check() == (epoch_path, 3)


def test_serve_refuses_before_binding(monkeypatch):
    """No epoch file, no start: serve() must raise before build_server binds the port."""
    built = []
    monkeypatch.setattr(server, "build_server", lambda addr: built.append(addr))
    monkeypatch.delenv(epoch.ENV, raising=False)
    with pytest.raises(epoch.EpochError):
        server.serve()
    assert built == []
