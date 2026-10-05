"""Mutation runs for item 1.4 (design.md section 4). Run from the repo root:

    python3 docs/work/2026-10-05-carry-chunk-text/evidence/mutate.py

Each mutation is applied to the working tree, the named check is run, and the file is restored from
an in-memory copy (the 1.4 edits are uncommitted, so git cannot restore them). A final hash
comparison proves every file is back to its pre-run bytes. Output: mutations.txt beside this file.

A mutation is CAUGHT when its check fails. A mutation that no check catches is a design gap: the
script reports it as MISSED and exits non-zero. "Equivalent" rows expect the check to PASS.
"""

import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUT = pathlib.Path(__file__).with_name("mutations.txt")

SERVER = "rag/src/rag/server.py"
RETRIEVE_PY = "rag/src/rag/retrieve.py"
RETRIEVE_GO = "gateway/internal/ragclient/retrieve.go"
SEAM_TEST = "gateway/internal/ragclient/seam_live_test.go"
MAKEFILE = "Makefile"

PYTEST = "cd rag && python3 -m pytest tests/test_retrieve_texts.py -q"
GO_UNIT = "cd gateway && go test -count=1 -run '^TestRetrieveTexts$' ./internal/ragclient/"
SEAM = "make seam-check"

TEXTS_LINE = "            texts=[c.text for c in chunks],"
GO_RETURN = "\treturn &RetrieveResult{\n"
MODE = '__import__("llama_index.core.schema", fromlist=["MetadataMode"]).MetadataMode'

# (id, description, file, old, new, [(check, expect_fail), ...])
MUTATIONS = [
    ("M1", "server.py omits texts", SERVER, TEXTS_LINE + "\n", "",
     [(PYTEST, True), (SEAM, True)]),
    ("M2a", "server.py sends texts reversed", SERVER, TEXTS_LINE,
     "            texts=[c.text for c in reversed(chunks)],",
     [(PYTEST, True), (SEAM, True)]),
    ("M2b", "server.py sends texts rotated by one", SERVER, TEXTS_LINE,
     "            texts=[c.text for c in chunks[1:] + chunks[:1]],",
     [(PYTEST, True), (SEAM, True)]),
    ("M3", "_to_chunks uses get_content(MetadataMode.ALL)", RETRIEVE_PY,
     "            text=n.get_content(),",
     f"            text=n.get_content(metadata_mode={MODE}.ALL),",
     [(PYTEST, True), (SEAM, True)]),
    ("M3-eq", "_to_chunks uses get_content(MetadataMode.LLM): equivalent on the live corpus",
     RETRIEVE_PY, "            text=n.get_content(),",
     f"            text=n.get_content(metadata_mode={MODE}.LLM),",
     [(PYTEST, True), (SEAM, False)]),
    ("M4", "ragclient never reads GetTexts()", RETRIEVE_GO,
     "\ttexts := resp.GetTexts()\n", "\ttexts := []string(nil)\n",
     [(GO_UNIT, True)]),
    # M5 disables the case rather than deleting it: deleting it leaves fmt unused, and the
    # COMPILER then "catches" the mutation, which says nothing about the test (first run, 2026-10-05).
    ("M5", "ragclient drops the length check", RETRIEVE_GO,
     "\tcase len(texts) != len(resp.GetChunkIds()):",
     "\tcase false && len(texts) != len(resp.GetChunkIds()):",
     [(GO_UNIT, True)]),
    ("M6", "checkAligned skips the oracle comparison", SEAM_TEST,
     "\t\tif texts[i] != want {", "\t\tif false && texts[i] != want {",
     [(SEAM, True)]),
    ("M7", "ragclient checks only len(texts) < len(chunk_ids)", RETRIEVE_GO,
     "\tcase len(texts) != len(resp.GetChunkIds()):",
     "\tcase len(texts) < len(resp.GetChunkIds()):",
     [(GO_UNIT, True)]),
    ("M8a", "server.py sends an empty text for chunk 0", SERVER, TEXTS_LINE,
     '            texts=[""] + [c.text for c in chunks[1:]],',
     [(SEAM, True)]),
    ("M8b", "oracle key built with a single colon (corpus:<id>)", SEAM_TEST,
     'const corpusKeyPrefix = "corpus::"', 'const corpusKeyPrefix = "corpus:"',
     [(SEAM, True)]),
    ("M9a", "ragclient reverses Texts", RETRIEVE_GO, GO_RETURN,
     "\tfor i, j := 0, len(texts)-1; i < j; i, j = i+1, j-1 {\n"
     "\t\ttexts[i], texts[j] = texts[j], texts[i]\n\t}\n" + GO_RETURN,
     [(GO_UNIT, True)]),
    ("M9b", "ragclient sorts Texts", RETRIEVE_GO, GO_RETURN,
     '\tsort.Strings(texts)\n' + GO_RETURN,
     [(GO_UNIT, True)]),
    # Target mutations: the guards the design relies on (review.md S4).
    ("T3", "TestSeam renamed", SEAM_TEST, "func TestSeam(t *testing.T) {",
     "func TestSeamRenamed(t *testing.T) {", [(SEAM, True)]),
    ("T4", "RAG_SEAM_ADDR dropped from the target's go test line", MAKEFILE,
     "RAG_SEAM_ADDR=127.0.0.1:$(SEAM_PORT) REDIS_URL=$(SEAM_REDIS_URL) \\\n",
     "REDIS_URL=$(SEAM_REDIS_URL) \\\n", [(SEAM, True)]),
]

# M9b needs the sort import.
IMPORT_FIX = {"M9b": ('\t"fmt"\n', '\t"fmt"\n\t"sort"\n')}

# Checks that are not file edits.
EXTRA = [
    ("T1", "make seam-check run twice; the second must still execute, never (cached)"),
    ("T2", "TestSeam with RAG_SEAM_ADDR pointed at a closed port must exit non-zero, not skip"),
]


def run(cmd: str) -> tuple[int, str]:
    p = subprocess.run(["bash", "-c", cmd], cwd=ROOT, capture_output=True, text=True, check=False)
    return p.returncode, (p.stdout + p.stderr)


def digest(paths) -> dict:
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}


def tail(out: str, n: int = 3) -> str:
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    return " | ".join(lines[-n:])[:300]


def main() -> int:
    files = sorted({m[2] for m in MUTATIONS})
    before = digest(files)
    rows, gaps = [], 0
    pressure = run("sysctl -n kern.memorystatus_vm_pressure_level")[1].strip()

    for mid, desc, path, old, new, checks in MUTATIONS:
        f = ROOT / path
        original = f.read_text()
        if original.count(old) != 1:
            rows.append(f"{mid}  ERROR  anchor not found exactly once in {path}")
            gaps += 1
            continue
        mutated = original.replace(old, new)
        if mid in IMPORT_FIX:
            a, b = IMPORT_FIX[mid]
            mutated = mutated.replace(a, b, 1)
        try:
            f.write_text(mutated)
            for cmd, expect_fail in checks:
                code, out = run(cmd)
                failed = code != 0
                if expect_fail:
                    verdict = "CAUGHT" if failed else "MISSED"
                else:
                    verdict = "PASSES (equivalent, as expected)" if not failed else "FAILS (unexpected)"
                if verdict in ("MISSED", "FAILS (unexpected)"):
                    gaps += 1
                rows.append(f"{mid:6} {verdict:34} [{cmd}]  {desc}\n         exit={code}: {tail(out)}")
        finally:
            f.write_text(original)

    # T1: twice in a row.
    for attempt in (1, 2):
        code, out = run(SEAM)
        ok = code == 0 and "=== RUN   TestSeam/L1" in out and "(cached)" not in out
        if not ok:
            gaps += 1
        rows.append(f"T1     {'OK' if ok else 'FAILED':34} [{SEAM}] run {attempt}: executed, no (cached)\n"
                    f"         exit={code}: {tail(out)}")

    # T2: closed port, Redis reachable.
    code, out = run("cd gateway && RAG_SEAM_ADDR=127.0.0.1:1 go test -count=1 -v -run '^TestSeam$' "
                    "./internal/ragclient/")
    ok = code != 0 and "--- SKIP" not in out
    if not ok:
        gaps += 1
    rows.append(f"T2     {'CAUGHT' if ok else 'MISSED':34} [RAG_SEAM_ADDR=127.0.0.1:1 go test]  "
                f"closed port must fail, not skip\n         exit={code}: {tail(out)}")

    after = digest(files)
    restored = before == after
    if not restored:
        gaps += 1

    header = [
        "# Item 1.4 mutation runs (design.md section 4) -- generated by mutate.py",
        f"# memory pressure level at start: {pressure} (author chose to run under 2; pass/fail only)",
        f"# files restored to pre-run bytes: {'yes' if restored else 'NO'}",
        f"# gaps (MISSED / unexpected / not restored): {gaps}",
        "",
    ]
    OUT.write_text("\n".join(header + rows) + "\n")
    print(OUT.read_text())
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
