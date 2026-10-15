"""Hand mutants of build_pqa.py. One edit at a time; the whole test file runs after each; the original
is always restored. Prints a markdown table. Usage: python3 mutants.py <repo_root>

A mutant whose `old` snippet does not occur exactly once is reported as NOT APPLIED (and counted as a
failure), so a change to the builder cannot silently turn a mutant into a no-op.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
SRC = ROOT / "experiments/scripts/build_pqa.py"
TESTS = "experiments/tests/test_build_pqa.py"

CHECKS = (
    "            failures = check_output(summary, spec)\n"
    "            failures += check_round_trip(info, spec)"
)
INPUT_CHECK = (
    "            failures = check_leaf(result.stats, spec, ignored_keys)\n"
    "            if failures:\n"
    "                raise StopError(failures)"
)

# (name, old, new). `old` must occur exactly once.
MUTANTS = [
    # --- the parser -------------------------------------------------------------------------------
    ("bullets: range(1, 5) instead of (1, 6)", "for n in range(1, 6))", "for n in range(1, 5))"),
    (
        "parser swaps question_type and answer_aggregated",
        '"question_type": text["question_type"],\n                "answer_aggregated": text["answer_aggregated"],',
        '"question_type": text["answer_aggregated"],\n                "answer_aggregated": text["question_type"],',
    ),
    ("product re-created on every record (last record wins)", "if product is None:", "if True:"),
    (
        "blank question_text no longer skipped",
        "if not isinstance(question, str) or not question.strip():",
        "if not isinstance(question, str):",
    ),
    (
        "empty asin no longer skipped",
        "if not isinstance(asin, str) or not asin:",
        "if not isinstance(asin, str):",
    ),
    (
        "surrogates are not replaced",
        "cleaned, n = _LONE_SURROGATE.subn(REPLACEMENT, text)",
        "cleaned, n = text, 0",
    ),
    (
        "low surrogates (DC00-DFFF) not covered by the pattern",
        "chr(0xDFFF)",
        "chr(0xDBFF)",
    ),
    ("the asin is not cleaned of surrogates", 'text["asin"] = _clean(asin, stats)', 'text["asin"] = asin'),
    (
        "a non-string field is coerced with str()",
        '    if not isinstance(value, str):\n        stats.bad_type[name] += 1\n        return ""',
        "    if not isinstance(value, str):\n        return str(value)",
    ),
    ("line_no starts at 0", "for line_no, raw in enumerate(lines, start=1):", "for line_no, raw in enumerate(lines, start=0):"),
    ("duplicate question ids not counted", "stats.duplicate_question_ids += 1", "stats.duplicate_question_ids += 0"),
    ("key census not kept", "stats.key_census.update(obj.keys())", "pass"),
    (
        "first parsed record no longer wins (prose conflicts not seen)",
        "        elif any(product[k] != v for k, v in fields.items()):\n            conflicted.add(asin)",
        "        elif False:\n            conflicted.add(asin)",
    ),
    (
        "bytes lines replaced by str.splitlines()",
        "    for line_no, raw in enumerate(lines, start=1):",
        "    for line_no, raw in enumerate((b''.join(lines).decode('utf-8', 'surrogatepass').splitlines()), start=1):\n        raw = raw.encode('utf-8', 'surrogatepass')",
    ),
    (
        "invalid UTF-8 raises instead of being counted",
        "        except ValueError:  # JSONDecodeError, and UnicodeDecodeError for invalid UTF-8",
        "        except json.JSONDecodeError:",
    ),
    # --- the stops, as functions --------------------------------------------------------------------
    ("Stop 1 never trips", "if stats.parsed == 0:", "if False:"),
    ("Stop 2(a) never trips", "if stats.field_nonempty[name] == 0:", "if stats.field_nonempty[name] == -1:"),
    ("Stop 2(b) never trips", "for key, n in unexpected:", "for key, n in []:"),
    ("Stop 3 input: skipped pin removed", '        ("records skipped", stats.skipped_total, spec.skipped_total),\n', ""),
    ("Stop 3 input: products pin removed", '        ("products", stats.products, spec.products),\n', ""),
    ("Stop 3 output: prose_median pin removed", '        ("prose_median_chars", summary.prose_median_chars, spec.prose_median_chars),\n', ""),
    ("Stop 3 output: question_type pin removed", '        ("question_type counts", summary.question_type, spec.question_type),\n', ""),
    ("Stop 3 output: answer_aggregated pin removed", '        ("answer_aggregated counts", summary.answer_aggregated, spec.answer_aggregated),\n', ""),
    ("Stop 0: hash check disabled", "if digest != spec.sha256:", "if False:"),
    ("Stop 0: short-file check disabled", "if size < spec.bytes:", "if False:"),
    ("Stop 0: long-file check disabled", "if size > spec.bytes:", "if False:"),
    # --- the stops, wired into build() (review finding 1) -------------------------------------------
    (
        "build: Stop 0 skipped altogether",
        "        for spec in leaves:\n            verify_source(raw_dir / spec.filename, spec)\n",
        "",
    ),
    (
        "build: Stop 0 per leaf, after earlier leaves were parsed",
        "        for spec in leaves:\n            verify_source(raw_dir / spec.filename, spec)\n        for spec in leaves:\n            path = raw_dir / spec.filename",
        "        for spec in leaves:\n            verify_source(raw_dir / spec.filename, spec)\n            path = raw_dir / spec.filename",
    ),
    ("build: input checks (Stops 1, 2, 3 input) skipped", "failures = check_leaf(result.stats, spec, ignored_keys)", "failures = []"),
    (
        "build: raises only on a Stop 3 failure of the input",
        INPUT_CHECK,
        '            failures = check_leaf(result.stats, spec, ignored_keys)\n            if failures and failures[0].startswith("Stop 3"):\n                raise StopError(failures)',
    ),
    (
        "build: never raises on a Stop 1 failure",
        INPUT_CHECK,
        '            failures = check_leaf(result.stats, spec, ignored_keys)\n            if failures and not failures[0].startswith("Stop 1"):\n                raise StopError(failures)',
    ),
    (
        "build: never raises on a Stop 2 failure",
        INPUT_CHECK,
        '            failures = check_leaf(result.stats, spec, ignored_keys)\n            if failures and not failures[0].startswith("Stop 2"):\n                raise StopError(failures)',
    ),
    ("build: aggregate output pins skipped", CHECKS, "            failures = check_round_trip(info, spec)"),
    ("build: field-by-field round trip skipped", CHECKS, "            failures = check_output(summary, spec)"),
    # --- the field-by-field round trip (review finding 2) ---------------------------------------------
    ("round trip: digest comparison disabled", "if _digest(line) != info.digests[asin]:", "if False:"),
    ("round trip: unknown asin not noticed", "if asin not in info.digests:", "if False:"),
    ("round trip: repeated asin not noticed", "if asin in seen:", "if False:"),
    ("round trip: missing products not noticed", "if len(seen) != len(info.digests):", "if False:"),
    (
        "digest ignores the questions",
        '    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))',
        '    value = {k: v for k, v in value.items() if k != "questions"}\n    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))',
    ),
    ("digest taken after the writer ran", "digests[asin] = _digest(products[asin])", "pass"),
    # --- the writer and the swap -----------------------------------------------------------------------
    ("writer swaps the department for the leaf", '"department": spec.department,\n        "item_name"', '"department": spec.leaf,\n        "item_name"'),
    ("writer iterates a set (hash-seed order)", "for asin in sorted(products):", "for asin in list(set(products)):"),
    ("writer iterates in file order (no sort)", "for asin in sorted(products):", "for asin in products:"),
    ("writer hash ignores the data", "digest.update(data)", "pass"),
    (
        "manifest replaced BEFORE the interim swap",
        '        os.replace(work / "interim", interim_dir)\n        moved_new = True\n        os.replace(work / "manifest.json", manifest_path)  # LAST',
        '        os.replace(work / "manifest.json", manifest_path)\n        os.replace(work / "interim", interim_dir)\n        moved_new = True',
    ),
    (
        "rollback does not restore the old directory",
        "        if moved_old:\n            os.replace(old, interim_dir)\n        raise",
        "        raise",
    ),
    ("stale temp dirs not removed", "            shutil.rmtree(child, ignore_errors=True)", "            pass"),
    (
        "work dir not cleaned after a failure",
        "    finally:\n        shutil.rmtree(work, ignore_errors=True)",
        "    finally:\n        pass",
    ),
    (
        "build swallows unexpected errors",
        "    except (SourceMismatch, StopError) as error:",
        "    except Exception as error:",
    ),
    ("the stale-product warning is not issued", "    _warn_about_stale_product_files(interim_dir.parent)\n", ""),
    # --- the manifest (review finding 4) ------------------------------------------------------------------
    ("manifest stage changed", '"stage": "3.1-interim",', '"stage": "v1-snapshot",'),
    ("cross_leaf uses union", "len(asins[a.leaf] & asins[b.leaf])", "len(asins[a.leaf] | asins[b.leaf])"),
    (
        "distinct total is the sum",
        '"products_distinct_across_leaves": len(union),',
        '"products_distinct_across_leaves": sum(len(s) for s in asins.values()),',
    ),
    ("builder hash is not recorded correctly", '"builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),', '"builder_sha256": "0" * 64,'),
    ("manifest: lines_read zeroed", '"lines_read": stats.lines_read,', '"lines_read": 0,'),
    ("manifest: prose_median_chars zeroed", '"prose_median_chars": summary.prose_median_chars,', '"prose_median_chars": 0,'),
    ("manifest: question_type emptied", '"question_type": dict(sorted(stats.question_type.items())),', '"question_type": {},'),
    ("manifest: answer_aggregated emptied", '"answer_aggregated": dict(sorted(stats.answer_aggregated.items())),', '"answer_aggregated": {},'),
    ("manifest: bad_type emptied", '"bad_type": dict(sorted(stats.bad_type.items())),', '"bad_type": {},'),
    ("manifest: answers_bad zeroed", '"answers_bad": stats.answers_bad,', '"answers_bad": 0,'),
    ("manifest: prose_conflicts zeroed", '"prose_conflicts": stats.prose_conflicts,', '"prose_conflicts": 0,'),
    ("manifest: duplicate_question_ids zeroed", '"duplicate_question_ids": stats.duplicate_question_ids,', '"duplicate_question_ids": 0,'),
    ("manifest: surrogate_replacements zeroed", '"surrogate_replacements": stats.surrogate_replacements,', '"surrogate_replacements": 0,'),
    (
        "manifest: field_nonempty zeroed",
        '"field_nonempty": {name: stats.field_nonempty[name] for name in REAL_FIELDS},',
        '"field_nonempty": {name: 0 for name in REAL_FIELDS},',
    ),
    ("manifest: skip reasons zeroed", '"skipped": {reason: stats.skipped[reason] for reason in SKIP_REASONS},', '"skipped": {reason: 0 for reason in SKIP_REASONS},'),
    # --- the reader, verify, the command line (review findings 3 and 4) ------------------------------------
    (
        "iter_interim does not verify first",
        '    manifest = load_manifest(manifest_path)\n    verify_interim(manifest, interim_dir)\n    for source in manifest["sources"]:',
        '    manifest = load_manifest(manifest_path)\n    for source in manifest["sources"]:',
    ),
    ("load_manifest: stage guard removed", ' or manifest.get("stage") != "3.1-interim"', ""),
    ("load_manifest: version guard removed", 'if manifest.get("manifest_version") != MANIFEST_VERSION:', "if False:"),
    ("verify warns never (builder drift silent)", 'if manifest["builder_sha256"] != here:', "if False:"),
    (
        "--verify falls through to a rebuild",
        "    if args.verify:\n        return verify(args.manifest, args.raw_dir, args.interim_dir)\n",
        "",
    ),
    # --- the report lines ---------------------------------------------------------------------------------------
    (
        "build does not print the manifest hash",
        '        print(f"manifest sha256: {hashlib.sha256(data).hexdigest()}")',
        "        pass",
    ),
    (
        "verify prints a wrong manifest hash",
        'print(f"manifest sha256: {hashlib.sha256(manifest_path.read_bytes()).hexdigest()}")',
        'print("manifest sha256: " + "0" * 64)',
    ),
    ("report no longer lists skip reasons", '                f"skipped, {spec.leaf}: "', '                f"gone, {spec.leaf}: "'),
    ("report no longer lists shared asins", '        "asins shared between leaves: "', '        "nothing to see: "'),
    (
        "report drops the prose_conflicts column",
        "f\"{'leaf':<22}{'prose_conflicts':>16}{'duplicate_qids':>16}{'surrogates':>12}\"",
        "f\"{'leaf':<22}{'conflicts':>16}{'duplicate_qids':>16}{'surrogates':>12}\"",
    ),
]


def run_tests() -> tuple[bool, list[str]]:
    for pyc in (ROOT / "experiments/scripts/__pycache__").glob("build_pqa*"):
        pyc.unlink()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    p = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    failed = re.findall(r"^FAILED \S+::(\S+)", p.stdout, flags=re.M)
    errored = "error" in p.stdout.splitlines()[-1].lower() and not failed
    return (p.returncode == 0), (failed or (["<collection or runtime error>"] if errored else []))


def main() -> None:
    original = SRC.read_text(encoding="utf-8")
    assert run_tests()[0], "the unmutated tests must pass first"
    rows, bad = [], []
    try:
        for name, old, new in MUTANTS:
            n = original.count(old)
            if n != 1:
                rows.append((name, f"NOT APPLIED: snippet occurs {n} times"))
                bad.append(name + " (not applied)")
                continue
            SRC.write_text(original.replace(old, new), encoding="utf-8")
            ok, failed = run_tests()
            if ok:
                rows.append((name, "SURVIVED -- no test failed"))
                bad.append(name)
            else:
                short = ", ".join(sorted(set(failed))[:3]) + (" ..." if len(set(failed)) > 3 else "")
                rows.append((name, f"caught by {len(set(failed))}: {short}"))
    finally:
        SRC.write_text(original, encoding="utf-8")
    assert run_tests()[0], "the original must pass after restoring"
    print("| # | Mutant | Result |\n| :-: | :--- | :--- |")
    for i, (name, res) in enumerate(rows, 1):
        print(f"| {i} | {name} | {res} |")
    print(f"\n{len(rows) - len(bad)} of {len(rows)} caught. Survived or not applied: {bad or 'none'}")


if __name__ == "__main__":
    main()
