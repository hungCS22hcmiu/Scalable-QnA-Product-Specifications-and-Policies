"""The dataset epoch: one integer in a file outside Redis (interfaces.md §E, ADR-008).

The RAG service stamps the epoch on every retrieval and the gateway compares it at write-back, so a
generation that started before an edit cannot write its old answer back after the purge. The file
holds one decimal integer >= 1. 0 (NOT_READ) is never a real epoch: it is what read() returns when
it cannot read the file.

Order rules (§E): a retrieval reads the epoch BEFORE it reads chunk texts. An edit writes the new
text first, then advances the epoch, then calls Invalidate. Standard library only.

    python -m rag.epoch advance   # +1, creates the file at 1
    python -m rag.epoch show      # path and value; fails if the file is not valid
"""

import fcntl
import os
import re
import sys
import tempfile
from pathlib import Path

ENV = "DATASET_EPOCH_FILE"
NOT_READ = 0

_INTEGER = re.compile(r"[+-]?[0-9]+")


class EpochError(Exception):
    """The epoch file is not usable. The message names the reason."""


def _parse(text: str, where: str) -> int:
    """A decimal integer >= 1. Surrounding whitespace (a trailing newline) is allowed."""
    s = text.strip()
    if not _INTEGER.fullmatch(s):
        raise EpochError(f"{where}: {s[:40]!r} is not an integer")
    value = int(s)
    if value < 1:
        raise EpochError(f"{where}: epoch {value} is below 1")
    return value


def _load(path: Path) -> int:
    try:
        text = path.read_text()
    except FileNotFoundError:
        raise EpochError(f"{path}: file does not exist") from None
    except (OSError, UnicodeDecodeError) as e:
        raise EpochError(f"{path}: cannot be read ({e})") from None
    return _parse(text, str(path))


def read() -> int:
    """The epoch now, or NOT_READ. Never raises: the loud failure is at start-up (check)."""
    value = os.environ.get(ENV, "")
    if not value:
        return NOT_READ
    try:
        return _load(Path(value))
    except EpochError:
        return NOT_READ


def require_path() -> Path:
    """The configured path: the variable must be set, non-empty and absolute. The file itself may
    not exist yet (advance() and ingest create it)."""
    value = os.environ.get(ENV)
    if value is None:
        raise EpochError(f"{ENV} is not set")
    if not value.strip():
        raise EpochError(f"{ENV} is empty")
    path = Path(value)
    if not path.is_absolute():
        raise EpochError(f"{ENV}={value!r} is a relative path; use an absolute one")
    return path


def check() -> tuple[Path, int]:
    """The start-up check: the path is absolute, the file exists and holds an integer >= 1."""
    path = require_path()
    return path, _load(path)


def advance() -> int:
    """Add 1 and return the new value; a missing file becomes 1.

    Serialised by an exclusive flock on `<file>.lock`. The new value goes to a temp file in the same
    directory, is fsync'd, then renamed over the old one, so a reader sees the old or the new value
    and never a partial one. A present file that is not a valid epoch raises: resetting it to 1
    would make a stale stamp equal to the epoch again.
    """
    path = require_path()
    lock_path = path.with_name(path.name + ".lock")
    with open(lock_path, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # released when `lock` closes
        current = _load(path) if path.exists() else 0
        new = current + 1
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(f"{new}\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise
    return new


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in ("advance", "show"):
        print("usage: python -m rag.epoch advance | show", file=sys.stderr)
        return 2
    try:
        if args[0] == "advance":
            value = advance()
            path = require_path()
        else:
            path, value = check()
    except EpochError as e:
        print(f"epoch: {e}", file=sys.stderr)
        return 1
    print(f"dataset_epoch_file={path} epoch={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
