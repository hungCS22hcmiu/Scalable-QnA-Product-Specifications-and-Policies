"""Item 5.4: the raw archive (docs/work/2026-11-12-figure-generators/design.md, section 3; ADR-027).

A run's `raw/` and `judge/` hold PQA text, so they are gitignored. This script keeps them safe and proves they
are unchanged, with two files per run:

    results/<run_id>/archive.sha256     the hash list: tracked, pushed. One `<sha256>  <path>` line per file
                                        under raw/ and judge/ (the `shasum -a 256` format). Paths and hashes
                                        only, no text.
    $RAW_ARCHIVE_DIR/<run_id>.tar       the archive: outside the repository, never pushed. It holds the run's
                                        raw/ and judge/ files only. Default folder: ~/thesis-raw-archive.

Three commands (the Makefile calls them as `make raw-archive`, `make raw-check` and `make raw-restore`):

    raw_archive.py archive --run-id <id>    cross-check the run, write the tar, read it back, write the list
    raw_archive.py check [--run-id <id>]    compare the files with the list (no id: every run that has a manifest.yaml; exit 1 if none)
    raw_archive.py restore --run-id <id>    put raw/ and judge/ back from the tar, then check them

Options for every command: `--results-dir` (default `$RESULTS_DIR`, else `experiments/results`) and
`--archive-dir` (default `$RAW_ARCHIVE_DIR`, else `~/thesis-raw-archive`).

`archive` refuses to overwrite either file, and writes the list last, so a run is never blessed by a list that
has no tar behind it. `restore` refuses when `raw/` or `judge/` exists, and before it extracts anything it
refuses a tar member that is not a regular file under raw/ or judge/.

It loads no model, and every number it prints is `citable: no`.

Exit codes: 0 done / intact; 1 `check` found a problem; 2 a refusal (`REFUSED: ...` on stderr) or bad usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tarfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR") or ROOT / "experiments" / "results")
ARCHIVE_DIR = Path(
    os.environ.get("RAW_ARCHIVE_DIR") or Path.home() / "thesis-raw-archive"
)
HASH_LIST = "archive.sha256"
FOLDERS = ("raw", "judge")
IGNORED = (".DS_Store",)
CHUNK = 1 << 20
LINE = re.compile(r"([0-9a-f]{64})  (.+)")


class ArchiveRefused(Exception):
    """A rule refused the command, or a file is unsafe to archive. The message says which."""


# =================================================================================================
# The hash list
# =================================================================================================
def _sha256_stream(src) -> str:
    h = hashlib.sha256()
    for block in iter(lambda: src.read(CHUNK), b""):
        h.update(block)
    return h.hexdigest()


def _sha256_file(path: Path) -> str:
    with open(path, "rb") as f:
        return _sha256_stream(f)


def hash_tree(run_dir: Path) -> list[tuple[str, str]]:
    """`(path, sha256)` for every file under the `FOLDERS` of `run_dir` that exist, sorted by path.

    Paths are relative to `run_dir`, in POSIX form. A name in `IGNORED` is skipped. A symlink, any other file
    that is not a regular file, or a path with a newline raises `ArchiveRefused`.
    """
    run_dir = Path(run_dir)
    rows: list[tuple[str, str]] = []
    for folder in FOLDERS:
        top = run_dir / folder
        if not os.path.lexists(top):
            continue
        if top.is_symlink() or not top.is_dir():
            raise ArchiveRefused(f"{folder}/ is not a plain folder")
        for root, dirs, files in os.walk(top):
            for name in dirs:
                if (Path(root) / name).is_symlink():
                    rel = (Path(root) / name).relative_to(run_dir).as_posix()
                    raise ArchiveRefused(f"{rel} is a symlink")
            for name in files:
                path = Path(root) / name
                rel = path.relative_to(run_dir).as_posix()
                mode = os.lstat(path).st_mode
                if stat.S_ISLNK(mode):
                    raise ArchiveRefused(f"{rel} is a symlink")
                if name in IGNORED:
                    continue
                if "\n" in rel or "\r" in rel:
                    raise ArchiveRefused(f"a path with a line break: {rel!r}")
                if not stat.S_ISREG(mode):
                    raise ArchiveRefused(f"{rel} is not a regular file")
                rows.append((rel, _sha256_file(path)))
    return sorted(rows)


def format_list(rows: list[tuple[str, str]]) -> str:
    """One `<sha256>  <path>` line per `(path, sha256)` row: the `shasum -a 256` format, so
    `shasum -a 256 -c archive.sha256` in the run folder is a second, independent check."""
    return "".join(f"{sha}  {path}\n" for path, sha in rows)


def read_list(run_dir: Path) -> dict[str, str]:
    """The run's hash list as path -> sha256. A missing file, a malformed line or a repeated path raises
    `ArchiveRefused`."""
    path = Path(run_dir) / HASH_LIST
    try:
        text = path.read_text()
    except OSError as e:
        raise ArchiveRefused(f"cannot read {path}: {e.strerror}") from None
    out: dict[str, str] = {}
    for n, line in enumerate(text.splitlines(), 1):
        m = LINE.fullmatch(line)
        if m is None:
            raise ArchiveRefused(f"{path} line {n} is not '<sha256>  <path>'")
        sha, rel = m.groups()
        if rel in out:
            raise ArchiveRefused(f"{path} line {n} repeats {rel}")
        out[rel] = sha
    return out


# =================================================================================================
# The check
# =================================================================================================
def check(run_dir: Path) -> list[str]:
    """The problems of a run's `raw/` and `judge/` against its hash list, each naming a path. An empty list
    means the run is intact.

    `no hash list`, `no raw/`, then `missing: <path>` (listed, not on disk), `changed: <path>` (listed, other
    bytes) and `added: <path>` (on disk, not listed), sorted by path. A list that cannot be read, or a file
    that is unsafe to hash (a symlink), is one problem, `bad hash list: ...` or `unsafe: ...`.
    """
    run_dir = Path(run_dir)
    if not (run_dir / HASH_LIST).is_file():
        return ["no hash list"]
    if not (run_dir / "raw").is_dir():
        return ["no raw/"]
    try:
        listed = read_list(run_dir)
    except ArchiveRefused as e:
        return [f"bad hash list: {e}"]
    try:
        actual = dict(hash_tree(run_dir))
    except ArchiveRefused as e:
        return [f"unsafe: {e}"]
    problems = []
    for path in sorted(listed.keys() | actual.keys()):
        if path not in actual:
            problems.append(f"missing: {path}")
        elif path not in listed:
            problems.append(f"added: {path}")
        elif actual[path] != listed[path]:
            problems.append(f"changed: {path}")
    return problems


def _requests_lines(run_dir: Path) -> list[str]:
    """The non-blank lines of `raw/requests.jsonl` (the same lines `run_manifest.read_records` counts)."""
    path = Path(run_dir) / "raw" / "requests.jsonl"
    try:
        return [x for x in path.read_text().splitlines() if x.strip()]
    except OSError as e:
        raise ArchiveRefused(f"cannot read {path}: {e.strerror}") from None


def cross_check(run_dir: Path) -> list[str]:
    """What must hold before a hash list is written (done condition 1). The problems, empty when all hold:

    - every `raw/answers/<x>.txt` hashes to `x` (`misnamed answer: <path>`);
    - every non-null `answer_sha256` in `raw/requests.jsonl` has its file (`missing answer: <sha256>`);
    - the number of lines of `raw/requests.jsonl` is `records.count` in `manifest.yaml`.

    A list written over a run that already lost files would bless the loss, so `archive` calls this first.
    """
    run_dir = Path(run_dir)
    problems: list[str] = []
    answers = run_dir / "raw" / "answers"
    have: set[str] = set()
    if answers.is_dir():
        for path in sorted(answers.iterdir()):
            if path.name in IGNORED:
                continue
            have.add(path.stem)
            if path.suffix != ".txt" or _sha256_file(path) != path.stem:
                problems.append(f"misnamed answer: raw/answers/{path.name}")

    try:
        lines = _requests_lines(run_dir)
    except ArchiveRefused as e:
        return [*problems, str(e)]
    wanted: set[str] = set()
    for n, line in enumerate(lines, 1):
        try:
            record = json.loads(line)
        except ValueError:
            problems.append(f"raw/requests.jsonl line {n} is not JSON")
            continue
        sha = record.get("answer_sha256") if isinstance(record, dict) else None
        if sha:
            wanted.add(sha)
    problems += [f"missing answer: {sha}" for sha in sorted(wanted - have)]

    try:
        manifest = yaml.safe_load((run_dir / "manifest.yaml").read_text())
        count = manifest["records"]["count"]
    except (OSError, yaml.YAMLError, KeyError, TypeError):
        problems.append("manifest.yaml has no records.count")
    else:
        if count != len(lines):
            problems.append(
                f"raw/requests.jsonl has {len(lines)} lines, manifest.yaml counts {count}"
            )
    return problems


# =================================================================================================
# The archive
# =================================================================================================
def _verify_tar(tar_path: Path, rows: list[tuple[str, str]]) -> None:
    """Read the tar back and compare every member's sha256 with `rows`. A mismatch raises and leaves the tar
    where it is, for inspection (a truncated tar must not look like a complete one)."""
    expected = dict(rows)
    seen: dict[str, str] = {}
    count = 0
    try:
        with tarfile.open(tar_path, "r") as tar:
            for member in tar:
                count += 1
                if not member.isreg():
                    raise ArchiveRefused(
                        f"{tar_path} holds {member.name}, which is not a regular file; the tar is left for inspection"
                    )
                src = tar.extractfile(member)
                assert src is not None
                seen[member.name] = _sha256_stream(src)
    except (tarfile.TarError, EOFError) as e:
        raise ArchiveRefused(
            f"{tar_path} cannot be read back: {e}; the tar is left for inspection"
        ) from None
    wrong = sorted(name for name, sha in expected.items() if seen.get(name) != sha)
    extra = sorted(set(seen) - set(expected))
    if wrong or extra or count != len(rows):
        raise ArchiveRefused(
            f"{tar_path} does not match the files ({len(wrong)} missing or different, {len(extra)} extra); "
            f"the tar is left for inspection. First: {(wrong + extra)[:3]}"
        )


def archive(run_dir: Path, archive_dir: Path) -> None:
    """Write `<archive_dir>/<run_id>.tar` and `<run_dir>/archive.sha256`, in this order:

    1. refuse when `manifest.yaml` or `raw/` is missing, or when the list or the tar already exists;
    2. refuse when `cross_check` returns anything;
    3. write the tar to `<run_id>.tar.partial` (files only, paths relative to the run folder), then rename it;
    4. read the tar back and compare every member's sha256 with `hash_tree`;
    5. write the list last, through a temp file and a rename.

    Nothing is written when step 1 or 2 refuses. A refusal raises `ArchiveRefused`.
    """
    run_dir, archive_dir = Path(run_dir), Path(archive_dir)
    run_id = run_dir.name
    tar_path = archive_dir / f"{run_id}.tar"
    partial = archive_dir / f"{run_id}.tar.partial"
    list_path = run_dir / HASH_LIST

    if not (run_dir / "manifest.yaml").is_file():
        raise ArchiveRefused(
            f"no manifest.yaml in {run_dir}: a run without one is invalid"
        )
    if not (run_dir / "raw").is_dir():
        raise ArchiveRefused(f"no raw/ in {run_dir}")
    for path in (list_path, tar_path):
        if os.path.lexists(path):
            raise ArchiveRefused(f"{path} exists; an archive is never overwritten")
    if os.path.lexists(partial):
        raise ArchiveRefused(
            f"{partial} is left over from an earlier attempt; look at it and remove it by hand"
        )

    problems = cross_check(run_dir)
    if problems:
        raise ArchiveRefused(
            "the run is not consistent, so nothing was written: " + "; ".join(problems)
        )
    rows = hash_tree(run_dir)

    archive_dir.mkdir(parents=True, exist_ok=True)
    with open(partial, "xb") as f:
        with tarfile.open(fileobj=f, mode="w") as tar:
            for rel, _ in rows:
                path = run_dir / rel
                info = tarfile.TarInfo(rel)
                info.size = os.lstat(path).st_size
                info.mtime = int(os.lstat(path).st_mtime)
                info.mode = 0o644
                with open(path, "rb") as src:
                    tar.addfile(info, src)
        f.flush()
        os.fsync(f.fileno())
    if os.path.lexists(tar_path):
        raise ArchiveRefused(
            f"{tar_path} appeared while writing; it is never overwritten"
        )
    partial.rename(tar_path)

    _verify_tar(tar_path, rows)

    tmp = run_dir / f"{HASH_LIST}.partial"
    tmp.write_text(format_list(rows))
    tmp.rename(list_path)


# =================================================================================================
# The restore
# =================================================================================================
def _member_problem(member: tarfile.TarInfo) -> str | None:
    """Why a tar member is not safe to extract, or None. Only a regular file under `raw/` or `judge/` is."""
    if not member.isreg():
        return "is not a regular file (a link, a device or a folder)"
    parts = member.name.split("/")
    if member.name.startswith("/"):
        return "is an absolute path"
    if any(part in ("", ".", "..") for part in parts):
        return "has an empty, '.' or '..' part in its path"
    if len(parts) < 2 or parts[0] not in FOLDERS:
        return "is outside raw/ and judge/"
    return None


def restore(run_dir: Path, archive_dir: Path) -> None:
    """Put `raw/` and `judge/` back from the tar, then `check` them against the hash list.

    Refuses, and extracts nothing, when the list or the tar is missing, when `raw/` or `judge/` already exists,
    or when any tar member is not a regular file under `raw/` or `judge/` (a link, a device, an absolute path,
    `..`). A non-empty `check` after the extraction raises, naming each problem.
    """
    run_dir, archive_dir = Path(run_dir), Path(archive_dir)
    tar_path = archive_dir / f"{run_dir.name}.tar"
    if not (run_dir / HASH_LIST).is_file():
        raise ArchiveRefused(f"no {HASH_LIST} in {run_dir}")
    if not tar_path.is_file():
        raise ArchiveRefused(f"no archive at {tar_path}")
    for folder in FOLDERS:
        if os.path.lexists(run_dir / folder):
            raise ArchiveRefused(
                f"{run_dir / folder} exists; a restore never writes over it"
            )
    try:
        with tarfile.open(tar_path, "r") as tar:
            members = tar.getmembers()
            for member in members:
                why = _member_problem(member)
                if why:
                    raise ArchiveRefused(
                        f"tar member {member.name!r} {why}; nothing was extracted"
                    )
            tar.extractall(path=run_dir, members=members, filter="data")
    except (tarfile.TarError, EOFError) as e:
        raise ArchiveRefused(f"{tar_path} cannot be read as a tar: {e}") from None
    problems = check(run_dir)
    if problems:
        raise ArchiveRefused(
            "the restored files are not the listed ones: " + "; ".join(problems)
        )


# =================================================================================================
# The commands
# =================================================================================================
def _run_dir(results_dir: Path, run_id: str) -> Path:
    if not run_id or run_id in (".", "..") or Path(run_id).name != run_id:
        raise ArchiveRefused(f"{run_id!r} is not a run id")
    return Path(results_dir) / run_id


def _cmd_archive(args: argparse.Namespace) -> int:
    run_dir = _run_dir(args.results_dir, args.run_id)
    archive(run_dir, args.archive_dir)
    print(f"archived {run_dir.name}: {len(read_list(run_dir))} files")
    print(f"  wrote {run_dir / HASH_LIST}")
    print(f"  wrote {Path(args.archive_dir) / (run_dir.name + '.tar')}")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    if args.run_id:
        runs = [_run_dir(args.results_dir, args.run_id)]
    else:
        base = Path(args.results_dir)
        runs = (
            sorted(d for d in base.iterdir() if (d / "manifest.yaml").is_file())
            if base.is_dir()
            else []
        )
        if not runs:
            print(f"FAIL: no run to check (no folder in {base} has a manifest.yaml)")
            return 1
    failed = 0
    for run_dir in runs:
        problems = check(run_dir)
        for problem in problems:
            print(f"FAIL  {run_dir.name}: {problem}")
        if problems:
            failed += 1
        else:
            print(f"ok {run_dir.name} ({len(read_list(run_dir))} files)")
    return 1 if failed else 0


def _cmd_restore(args: argparse.Namespace) -> int:
    run_dir = _run_dir(args.results_dir, args.run_id)
    restore(run_dir, args.archive_dir)
    print(
        f"restored {run_dir.name}: {len(read_list(run_dir))} files, all match {HASH_LIST}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    common.add_argument("--archive-dir", type=Path, default=ARCHIVE_DIR)

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    a = sub.add_parser(
        "archive",
        parents=[common],
        help="write the tar and the hash list (refuses to overwrite either)",
    )
    a.add_argument("--run-id", required=True)
    c = sub.add_parser(
        "check",
        parents=[common],
        help="compare raw/ and judge/ with the hash list (no --run-id: every run that has a manifest.yaml)",
    )
    c.add_argument("--run-id")
    r = sub.add_parser(
        "restore",
        parents=[common],
        help="put raw/ and judge/ back from the tar, then check them",
    )
    r.add_argument("--run-id", required=True)

    args = ap.parse_args(argv)
    try:
        return {"archive": _cmd_archive, "check": _cmd_check, "restore": _cmd_restore}[
            args.command
        ](args)
    except ArchiveRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
