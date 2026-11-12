"""Item 5.4: raw_archive.py (the hash list, the tar, the check and the restore).

Every test builds a small fake run in `tmp_path`. None reads a real run's `raw/` or `judge/`.
"""

import hashlib
import io
import json
import os
import shutil
import tarfile

import pytest
import raw_archive as ra
import yaml

RUN_ID = "2026-11-12T00-00-00_cfg4_fake"
ANSWERS = [b"answer one", b"answer two", b"answer three"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_run(results, run_id=RUN_ID, judge=True):
    """A fake run: manifest.yaml (records.count 4), raw/requests.jsonl (one null answer_sha256), three
    content-addressed answers and, unless `judge` is False, judge/verdicts.jsonl."""
    run = results / run_id
    (run / "raw" / "answers").mkdir(parents=True)
    shas = [sha(a) for a in ANSWERS]
    for data, s in zip(ANSWERS, shas):
        (run / "raw" / "answers" / f"{s}.txt").write_bytes(data)
    records = [
        {"request_id": "r1", "answer_sha256": shas[0]},
        {"request_id": "r2", "answer_sha256": shas[1]},
        {"request_id": "r3", "answer_sha256": shas[2]},
        {"request_id": "r4", "answer_sha256": None},
    ]
    (run / "raw" / "requests.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records)
    )
    (run / "manifest.yaml").write_text(
        yaml.safe_dump({"run_id": run_id, "records": {"count": len(records)}})
    )
    if judge:
        (run / "judge").mkdir()
        (run / "judge" / "verdicts.jsonl").write_text('{"verdict": "CORRECT"}\n')
    return run


@pytest.fixture
def world(tmp_path):
    """results/ with one fake run, and an archive folder that does not exist yet."""
    results = tmp_path / "results"
    results.mkdir()
    return results, make_run(results), tmp_path / "archive"


def tar_path(arch, run_id=RUN_ID):
    return arch / f"{run_id}.tar"


def snapshot(folder):
    """path -> bytes of every file under `folder`, to show that nothing was written or changed."""
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def crafted_tar(path, members):
    """A tar of `(TarInfo, bytes | None)` members, written by hand."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w") as tar:
        for info, data in members:
            tar.addfile(info, io.BytesIO(data) if data is not None else None)


def file_member(name, data=b"evil"):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    return info, data


# -------------------------------------------------------------------------------------------------
# hash_tree, format_list, read_list
# -------------------------------------------------------------------------------------------------
def test_hash_tree_is_sorted_posix_and_skips_ds_store(world):
    _, run, _ = world
    (run / "raw" / ".DS_Store").write_bytes(b"junk")
    (run / "judge" / ".DS_Store").write_bytes(b"junk")
    rows = ra.hash_tree(run)
    paths = [p for p, _ in rows]
    assert paths == sorted(paths)
    assert all("\\" not in p and not p.startswith("/") for p in paths)
    assert paths[0].startswith("judge/") and "raw/requests.jsonl" in paths
    assert not any(p.endswith(".DS_Store") for p in paths)
    assert len(rows) == 5  # 3 answers, requests.jsonl, verdicts.jsonl
    assert dict(rows)["judge/verdicts.jsonl"] == sha(b'{"verdict": "CORRECT"}\n')


def test_hash_tree_refuses_a_symlinked_file(world):
    _, run, _ = world
    os.symlink(run / "manifest.yaml", run / "raw" / "link.txt")
    with pytest.raises(ra.ArchiveRefused, match="raw/link.txt is a symlink"):
        ra.hash_tree(run)


def test_hash_tree_refuses_a_symlinked_folder(world, tmp_path):
    _, run, _ = world
    os.symlink(tmp_path, run / "raw" / "dirlink")
    with pytest.raises(ra.ArchiveRefused, match="dirlink is a symlink"):
        ra.hash_tree(run)


def test_hash_tree_refuses_a_path_with_a_newline(world):
    _, run, _ = world
    (run / "raw" / "bad\nname.txt").write_bytes(b"x")
    with pytest.raises(ra.ArchiveRefused, match="line break"):
        ra.hash_tree(run)


def test_hash_tree_covers_only_the_folders_that_exist(world):
    results, _, _ = world
    run = make_run(results, "run-no-judge", judge=False)
    paths = [p for p, _ in ra.hash_tree(run)]
    assert paths and all(p.startswith("raw/") for p in paths)


def test_format_list_and_read_list_round_trip(world):
    _, run, _ = world
    rows = ra.hash_tree(run)
    text = ra.format_list(rows)
    assert text.splitlines()[0] == f"{rows[0][1]}  {rows[0][0]}"  # the shasum format
    (run / ra.HASH_LIST).write_text(text)
    assert ra.read_list(run) == dict(rows)


@pytest.mark.parametrize(
    "line",
    ["not a hash line", "abc  raw/x", f"{'a' * 64} raw/x", f"{'A' * 64}  raw/x", ""],
)
def test_read_list_raises_on_a_malformed_line(world, line):
    _, run, _ = world
    (run / ra.HASH_LIST).write_text(f"{'a' * 64}  raw/ok\n{line}\n")
    with pytest.raises(ra.ArchiveRefused, match="line 2"):
        ra.read_list(run)


def test_read_list_raises_on_a_repeated_path(world):
    _, run, _ = world
    (run / ra.HASH_LIST).write_text(f"{'a' * 64}  raw/x\n{'b' * 64}  raw/x\n")
    with pytest.raises(ra.ArchiveRefused, match="repeats raw/x"):
        ra.read_list(run)


# -------------------------------------------------------------------------------------------------
# archive
# -------------------------------------------------------------------------------------------------
def test_archive_writes_one_list_line_per_file_and_a_matching_tar(world):
    _, run, arch = world
    (run / "raw" / ".DS_Store").write_bytes(b"junk")
    ra.archive(run, arch)
    listed = ra.read_list(run)
    assert len(listed) == 5
    assert set(listed) == {p for p, _ in ra.hash_tree(run)}
    with tarfile.open(tar_path(arch)) as tar:
        members = tar.getmembers()
        assert [m.name for m in members] == sorted(listed)
        assert all(m.isreg() for m in members)
        for m in members:
            assert sha(tar.extractfile(m).read()) == listed[m.name]
    assert not (arch / f"{RUN_ID}.tar.partial").exists()
    assert not (run / f"{ra.HASH_LIST}.partial").exists()
    assert ra.check(run) == []


def test_archive_refuses_when_the_list_exists(world):
    _, run, arch = world
    (run / ra.HASH_LIST).write_text("old\n")
    with pytest.raises(ra.ArchiveRefused, match="exists"):
        ra.archive(run, arch)
    assert (run / ra.HASH_LIST).read_text() == "old\n"
    assert not arch.exists()


def test_archive_refuses_when_the_tar_exists(world):
    _, run, arch = world
    arch.mkdir()
    tar_path(arch).write_bytes(b"old tar")
    with pytest.raises(ra.ArchiveRefused, match="exists"):
        ra.archive(run, arch)
    assert tar_path(arch).read_bytes() == b"old tar"
    assert not (run / ra.HASH_LIST).exists()


def test_archive_refuses_a_leftover_partial_tar(world):
    _, run, arch = world
    arch.mkdir()
    (arch / f"{RUN_ID}.tar.partial").write_bytes(b"half")
    with pytest.raises(ra.ArchiveRefused, match="left over"):
        ra.archive(run, arch)
    assert not tar_path(arch).exists()
    assert not (run / ra.HASH_LIST).exists()


def test_archive_refuses_without_manifest(world):
    _, run, arch = world
    (run / "manifest.yaml").unlink()
    with pytest.raises(ra.ArchiveRefused, match="manifest.yaml"):
        ra.archive(run, arch)
    assert not arch.exists() and not (run / ra.HASH_LIST).exists()


def test_archive_refuses_without_raw(world):
    _, run, arch = world
    shutil.rmtree(run / "raw")
    with pytest.raises(ra.ArchiveRefused, match="no raw/"):
        ra.archive(run, arch)
    assert not arch.exists() and not (run / ra.HASH_LIST).exists()


@pytest.mark.parametrize("cut", [2 * 1024 + 100, 2 * 1024, 3 * 1024 + 700])
def test_verify_tar_refuses_a_truncated_tar(world, cut):
    # 5 small members take 1024 bytes each: a cut inside a member breaks the tar, a cut between two members drops
    # the rest. Both must raise, so a truncated tar never looks complete.
    _, run, arch = world
    ra.archive(run, arch)
    rows = ra.hash_tree(run)
    tar_path(arch).write_bytes(tar_path(arch).read_bytes()[:cut])
    with pytest.raises(ra.ArchiveRefused, match="left for inspection"):
        ra._verify_tar(tar_path(arch), rows)


def test_verify_tar_refuses_a_member_with_other_bytes(world):
    _, run, arch = world
    rows = ra.hash_tree(run)
    crafted_tar(tar_path(arch), [file_member(path, b"other bytes") for path, _ in rows])
    with pytest.raises(ra.ArchiveRefused, match="does not match"):
        ra._verify_tar(tar_path(arch), rows)


# -------------------------------------------------------------------------------------------------
# cross_check
# -------------------------------------------------------------------------------------------------
def test_cross_check_passes_on_a_consistent_run(world):
    _, run, _ = world
    assert ra.cross_check(run) == []


def test_cross_check_refuses_a_misnamed_answer_and_nothing_is_written(world):
    _, run, arch = world
    answers = run / "raw" / "answers"
    victim = min(answers.iterdir())
    victim.rename(answers / f"{'0' * 64}.txt")
    problems = ra.cross_check(run)
    assert any(p.startswith("misnamed answer: raw/answers/0000") for p in problems)
    with pytest.raises(ra.ArchiveRefused, match="misnamed answer"):
        ra.archive(run, arch)
    assert not arch.exists() and not (run / ra.HASH_LIST).exists()


def test_cross_check_refuses_a_referenced_answer_with_no_file(world):
    _, run, arch = world
    gone = min((run / "raw" / "answers").iterdir())
    gone.unlink()
    problems = ra.cross_check(run)
    assert f"missing answer: {gone.stem}" in problems
    with pytest.raises(ra.ArchiveRefused, match="missing answer"):
        ra.archive(run, arch)
    assert not arch.exists() and not (run / ra.HASH_LIST).exists()


def test_cross_check_refuses_a_record_count_unlike_the_manifests(world):
    _, run, arch = world
    with open(run / "raw" / "requests.jsonl", "a") as f:
        f.write(json.dumps({"request_id": "r5", "answer_sha256": None}) + "\n")
    problems = ra.cross_check(run)
    assert problems == ["raw/requests.jsonl has 5 lines, manifest.yaml counts 4"]
    with pytest.raises(ra.ArchiveRefused, match="5 lines"):
        ra.archive(run, arch)
    assert not arch.exists() and not (run / ra.HASH_LIST).exists()


def test_cross_check_refuses_a_manifest_without_a_count(world):
    _, run, _ = world
    (run / "manifest.yaml").write_text(yaml.safe_dump({"run_id": RUN_ID}))
    assert ra.cross_check(run) == ["manifest.yaml has no records.count"]


def test_cross_check_names_a_line_that_is_not_json(world):
    _, run, _ = world
    with open(run / "raw" / "requests.jsonl", "a") as f:
        f.write("not json\n")
    assert "raw/requests.jsonl line 5 is not JSON" in ra.cross_check(run)


# -------------------------------------------------------------------------------------------------
# check
# -------------------------------------------------------------------------------------------------
def test_check_is_empty_on_an_intact_run(world):
    _, run, arch = world
    ra.archive(run, arch)
    assert ra.check(run) == []


def test_check_names_a_file_with_one_changed_byte(world):
    _, run, arch = world
    ra.archive(run, arch)
    target = run / "judge" / "verdicts.jsonl"
    data = bytearray(target.read_bytes())
    data[3] ^= 1
    target.write_bytes(bytes(data))
    assert ra.check(run) == ["changed: judge/verdicts.jsonl"]


def test_check_names_a_deleted_file(world):
    _, run, arch = world
    ra.archive(run, arch)
    gone = min((run / "raw" / "answers").iterdir())
    gone.unlink()
    assert ra.check(run) == [f"missing: raw/answers/{gone.name}"]


def test_check_names_an_added_file(world):
    _, run, arch = world
    ra.archive(run, arch)
    (run / "raw" / "extra.txt").write_text("new")
    assert ra.check(run) == ["added: raw/extra.txt"]


def test_check_ignores_an_added_ds_store(world):
    _, run, arch = world
    ra.archive(run, arch)
    (run / "raw" / ".DS_Store").write_bytes(b"junk")
    (run / "judge" / ".DS_Store").write_bytes(b"junk")
    assert ra.check(run) == []


def test_check_lists_problems_sorted_by_path(world):
    _, run, arch = world
    ra.archive(run, arch)
    (run / "raw" / "zzz.txt").write_text("new")
    (run / "judge" / "verdicts.jsonl").unlink()
    (run / "raw" / "answers").joinpath(
        min(p.name for p in (run / "raw" / "answers").iterdir())
    ).write_bytes(b"changed")
    problems = ra.check(run)
    assert len(problems) == 3
    assert [p.split(": ")[1] for p in problems] == sorted(
        p.split(": ")[1] for p in problems
    )


def test_check_says_no_hash_list(world):
    _, run, _ = world
    assert ra.check(run) == ["no hash list"]


def test_check_says_no_raw(world):
    _, run, arch = world
    ra.archive(run, arch)
    shutil.rmtree(run / "raw")
    assert ra.check(run) == ["no raw/"]


def test_check_reports_a_bad_list_and_a_symlink_as_problems(world):
    _, run, arch = world
    ra.archive(run, arch)
    good = (run / ra.HASH_LIST).read_text()
    (run / ra.HASH_LIST).write_text("garbage\n")
    assert ra.check(run)[0].startswith("bad hash list:")
    (run / ra.HASH_LIST).write_text(good)
    os.symlink(run / "manifest.yaml", run / "raw" / "link.txt")
    assert ra.check(run)[0].startswith("unsafe:")


# -------------------------------------------------------------------------------------------------
# restore
# -------------------------------------------------------------------------------------------------
def archived_then_lost(world):
    """Archive the run, then delete `raw/` and `judge/`: the state of a clean checkout plus the archive."""
    _, run, arch = world
    ra.archive(run, arch)
    before = snapshot(run)
    shutil.rmtree(run / "raw")
    shutil.rmtree(run / "judge")
    return run, arch, before


def test_round_trip_gives_the_same_bytes(world):
    run, arch, before = archived_then_lost(world)
    ra.restore(run, arch)
    assert snapshot(run) == before
    assert ra.check(run) == []


def test_restore_refuses_when_raw_exists(world):
    run, arch, _ = archived_then_lost(world)
    (run / "raw").mkdir()
    with pytest.raises(ra.ArchiveRefused, match="raw"):
        ra.restore(run, arch)
    assert list((run / "raw").iterdir()) == [] and not (run / "judge").exists()


def test_restore_refuses_when_judge_exists(world):
    run, arch, _ = archived_then_lost(world)
    (run / "judge").mkdir()
    with pytest.raises(ra.ArchiveRefused, match="judge"):
        ra.restore(run, arch)
    assert not (run / "raw").exists() and list((run / "judge").iterdir()) == []


def test_restore_refuses_when_the_tar_is_missing(world):
    run, arch, _ = archived_then_lost(world)
    tar_path(arch).unlink()
    with pytest.raises(ra.ArchiveRefused, match="no archive"):
        ra.restore(run, arch)
    assert not (run / "raw").exists()


def test_restore_refuses_when_the_list_is_missing(world):
    run, arch, _ = archived_then_lost(world)
    (run / ra.HASH_LIST).unlink()
    with pytest.raises(ra.ArchiveRefused, match=ra.HASH_LIST):
        ra.restore(run, arch)
    assert not (run / "raw").exists()


def dir_member(name):
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE
    return info, None


def link_member(name, linkname):
    info = tarfile.TarInfo(name)
    info.type = tarfile.SYMTYPE
    info.linkname = linkname
    return info, None


@pytest.mark.parametrize("kind", ["dotdot", "absolute", "symlink", "outside", "dir"])
def test_restore_refuses_a_bad_member_and_extracts_nothing(world, tmp_path, kind):
    run, arch, _ = archived_then_lost(world)
    evil = tmp_path / "abs_evil"
    bad = {
        "dotdot": file_member("../evil"),
        "absolute": file_member(str(evil)),
        "symlink": link_member("raw/link", "/etc/passwd"),
        "outside": file_member("manifest.yaml"),
        "dir": dir_member("raw/folder"),
    }[kind]
    # a good member comes first, so "nothing was extracted" means the check ran before the extraction
    crafted_tar(
        tar_path(arch),
        [file_member("raw/good.txt", b"fine"), bad],
    )
    with pytest.raises(ra.ArchiveRefused, match="nothing was extracted"):
        ra.restore(run, arch)
    assert not (run / "raw").exists() and not (run / "judge").exists()
    assert not (run.parent / "evil").exists() and not evil.exists()


def test_restore_raises_when_the_restored_files_are_not_the_listed_ones(world):
    run, arch, _ = archived_then_lost(world)
    rows = [(p, h) for p, h in ra.read_list(run).items()]
    crafted_tar(tar_path(arch), [file_member(p, b"other") for p, _ in rows])
    with pytest.raises(ra.ArchiveRefused, match="changed: "):
        ra.restore(run, arch)


def test_a_run_with_no_judge_archives_and_restores_raw_only(world):
    results, _, arch = world
    run = make_run(results, "run-no-judge", judge=False)
    ra.archive(run, arch)
    assert all(p.startswith("raw/") for p in ra.read_list(run))
    before = snapshot(run)
    shutil.rmtree(run / "raw")
    ra.restore(run, arch)
    assert snapshot(run) == before
    assert not (run / "judge").exists()


# -------------------------------------------------------------------------------------------------
# main
# -------------------------------------------------------------------------------------------------
def argv(command, results, arch, run_id=RUN_ID):
    out = [command, "--results-dir", str(results), "--archive-dir", str(arch)]
    return out + ["--run-id", run_id] if run_id else out


def test_main_archive_returns_0_then_2(world, capsys):
    results, _, arch = world
    assert ra.main(argv("archive", results, arch)) == 0
    out = capsys.readouterr().out
    assert "5 files" in out and ra.HASH_LIST in out and f"{RUN_ID}.tar" in out
    assert ra.main(argv("archive", results, arch)) == 2
    assert "REFUSED" in capsys.readouterr().err


def test_main_check_returns_0_then_1_after_a_change(world, capsys):
    results, run, arch = world
    assert ra.main(argv("archive", results, arch)) == 0
    capsys.readouterr()
    assert ra.main(argv("check", results, arch)) == 0
    assert f"ok {RUN_ID} (5 files)" in capsys.readouterr().out
    (run / "raw" / "requests.jsonl").write_bytes(b"changed")
    assert ra.main(argv("check", results, arch)) == 1
    assert "changed: raw/requests.jsonl" in capsys.readouterr().out


def test_main_restore_returns_2_on_a_refusal(world, capsys):
    results, _, arch = world
    assert ra.main(argv("archive", results, arch)) == 0
    capsys.readouterr()
    assert ra.main(argv("restore", results, arch)) == 2  # raw/ and judge/ still exist
    assert "REFUSED" in capsys.readouterr().err


def test_main_restore_returns_0_after_a_loss(world, capsys):
    results, run, arch = world
    assert ra.main(argv("archive", results, arch)) == 0
    shutil.rmtree(run / "raw")
    shutil.rmtree(run / "judge")
    capsys.readouterr()
    assert ra.main(argv("restore", results, arch)) == 0
    assert ra.check(run) == []


def test_main_check_without_a_run_id_checks_every_run_with_a_manifest(world, capsys):
    results, _, arch = world
    other = make_run(results, "2026-11-12T01-00-00_cfg4_other")
    (results / "not-a-run").mkdir()  # no manifest.yaml: not a run
    assert ra.main(argv("archive", results, arch)) == 0
    capsys.readouterr()
    # the second run has no list: reported as `no hash list`, exit 1
    assert ra.main(argv("check", results, arch, run_id=None)) == 1
    out = capsys.readouterr().out
    assert f"ok {RUN_ID}" in out
    assert "FAIL  2026-11-12T01-00-00_cfg4_other: no hash list" in out
    assert "not-a-run" not in out
    # archive it too: both are intact
    assert (
        ra.main(argv("archive", results, arch, run_id="2026-11-12T01-00-00_cfg4_other"))
        == 0
    )
    capsys.readouterr()
    assert ra.main(argv("check", results, arch, run_id=None)) == 0
    assert capsys.readouterr().out.count("ok ") == 2
    assert other.is_dir()


def test_main_check_without_a_run_id_exits_1_when_there_is_no_run(tmp_path, capsys):
    results = tmp_path / "results"
    results.mkdir()
    (results / "folder-without-manifest").mkdir()
    assert ra.main(argv("check", results, tmp_path / "a", run_id=None)) == 1
    assert "no run to check" in capsys.readouterr().out
    assert ra.main(argv("check", tmp_path / "missing", tmp_path / "a", None)) == 1


def test_main_refuses_a_run_id_that_is_a_path(world, capsys):
    results, _, arch = world
    assert ra.main(argv("archive", results, arch, run_id="../x")) == 2
    assert "is not a run id" in capsys.readouterr().err
