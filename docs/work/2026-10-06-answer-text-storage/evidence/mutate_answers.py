"""Apply each design.md §5 mutation (M1-M16, M17-M18 on `incomplete`, M19-M25 from the implementation review) of the answer
store to a fresh COPY of gateway/ and record what stops it.

The working tree is never touched. For each mutation, two runs:
  (a) the EXISTING suite (the four new test files removed): informational. A mutation that the old suite
      already catches is fine; one it does not catch is exactly why the new tests exist.
  (b) the FULL suite (existing + new): at least one NEW test must fail, by ASSERTION and not by a build
      error, for the mutation to count as caught.
Usage: mutate_answers.py <scratch dir> <output md> [M9,M12,...]   (a filter writes a partial report: use a scratch OUT)
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path("/Users/hung/Desktop/Sem1/thesis")
SCRATCH = Path(sys.argv[1])
OUT = Path(sys.argv[2])

EVAL = "internal/telemetry/evallog.go"
HANDLER = "internal/httpapi/handler.go"
MAIN = "cmd/gateway/main.go"
NEW_FILES = ["internal/telemetry/answers_test.go", "internal/httpapi/answerstore_test.go",
             "cmd/gateway/incomplete_test.go", "cmd/gateway/finish_test.go"]
PKGS = ["./internal/telemetry/", "./internal/httpapi/", "./cmd/gateway/"]

new_tests = set()
for f in NEW_FILES:
    new_tests |= set(re.findall(r"^func (Test\w+)\(", (REPO / "gateway" / f).read_text(), re.M))

OLD_SHA = '''package httpapi

import (
	"crypto/sha256"
	"encoding/hex"
)

func sha256Hex(answer string) string {
	sum := sha256.Sum256([]byte(answer))
	return hex.EncodeToString(sum[:])
}
'''

M = []
def mut(mid, desc, edits, extras=None):
    M.append((mid, desc, edits, extras or {}))

mut("M1", "write the answer only on a MISS (hits never write)",
    [(EVAL, "\tsha := r.AnswerSHA256\n\tif _, ok := l.seen[sha]; ok {",
      "\tsha := r.AnswerSHA256\n\tif r.Cache != \"MISS\" {\n\t\treturn\n\t}\n\tif _, ok := l.seen[sha]; ok {")])
mut("M2", "the line is written before the file",
    [(EVAL, "\t\tif r.AnswerSHA256 != \"\" {\n\t\t\tl.storeAnswer(r)\n\t\t}\n\t\tif err := enc.Encode(r); err != nil {",
      "\t\tencErr := enc.Encode(r)\n\t\tif r.AnswerSHA256 != \"\" {\n\t\t\tl.storeAnswer(r)\n\t\t}\n\t\tif err := encErr; err != nil {")])
mut("M3", "the Tier-1 call site left on the old assignment (hash set, text not)",
    [(HANDLER, "\t\trec.SetAnswer(entry.Answer)\n", "\t\trec.AnswerSHA256 = sha256Hex(entry.Answer)\n")],
    {"internal/httpapi/mut_sha.go": OLD_SHA})
mut("M4", "`seen` is set before the write succeeds",
    [(EVAL, "\ttmp, err := l.createTemp(l.answersDir, \".answer-*.tmp\")",
      "\tl.seen[sha] = struct{}{}\n\ttmp, err := l.createTemp(l.answersDir, \".answer-*.tmp\")")])
mut("M5", "`missing` is never cleared by a successful retry",
    [(EVAL, "func (l *Logger) clearMissing(sha string) {\n\tl.mu.Lock()\n\tdelete(l.missing, sha)\n\tl.mu.Unlock()\n}",
      "func (l *Logger) clearMissing(sha string) {}")])
mut("M6", "no dedupe (every record tries to publish)",
    [(EVAL, "\tif _, ok := l.seen[sha]; ok {\n\t\treturn // the Zipf common case: this hash's file already exists\n\t}\n", "")])
mut("M7", "the hash is taken over the TRIMMED text (the shared helper changes, so the guard agrees with it)",
    [(EVAL, "\tsum := sha256.Sum256([]byte(text))", "\tsum := sha256.Sum256([]byte(strings.TrimSpace(text)))"),
     (EVAL, "\t\"path/filepath\"\n", "\t\"path/filepath\"\n\t\"strings\"\n")])
mut("M8", "a failed write is not counted missing",
    [(EVAL, "func (l *Logger) answerFailed(sha string, err error) {\n\tl.markMissing(sha)\n",
      "func (l *Logger) answerFailed(sha string, err error) {\n")])
mut("M9", "the guard is removed",
    [(EVAL, "\tif sha256Hex(r.answerText) != sha {\n\t\t// missing first: a reader that sees the refusal count is then guaranteed to see the hash missing too.\n\t\tl.markMissing(sha)\n\t\tl.guardRefusals.Add(1)\n\t\tlog.Printf(\"telemetry: ERROR record %s: answer text does not hash to answer_sha256 %s; NOT written -- the run is void\", r.RequestID, sha)\n\t\treturn\n\t}\n", "")])
mut("M10", "the temp file is left behind after a failed Link",
    [(EVAL, "err != nil && !errors.Is(err, fs.ErrExist) {\n\t\t_ = l.removeFile(tmpName)\n\t\tl.answerFailed(sha, err)",
      "err != nil && !errors.Is(err, fs.ErrExist) {\n\t\tl.answerFailed(sha, err)")])
mut("M11", "Rename instead of Link (overwrites an existing file)",
    [(EVAL, "linkFile: os.Link, removeFile: os.Remove}", "linkFile: os.Rename, removeFile: os.Remove}")])
mut("M12", "Open makes answers/ BEFORE the exclusive create, and tolerates it already existing",
    [(EVAL, "\tf, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o644)",
      "\t_ = os.MkdirAll(filepath.Join(dir, \"answers\"), 0o755)\n\tf, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o644)"),
     (EVAL, "if err := os.Mkdir(answersDir, 0o755); err != nil {", "if err := os.MkdirAll(answersDir, 0o755); err != nil {")])
mut("M13", "a failed line write is not counted",
    [(EVAL, "\t\t\tl.writeErrs.Add(1)\n", "")])
mut("M14", "a failed temp removal AFTER a successful Link marks the hash missing",
    [(EVAL, "\tif err := l.removeFile(tmpName); err != nil {\n\t\tlog.Printf(\"telemetry: removing temp file",
      "\tif err := l.removeFile(tmpName); err != nil {\n\t\tl.markMissing(sha)\n\t\tlog.Printf(\"telemetry: removing temp file")])
mut("M15", "EEXIST from Link is treated as an error",
    [(EVAL, "err != nil && !errors.Is(err, fs.ErrExist) {", "err != nil && (errors.Is(err, fs.ErrExist) || !errors.Is(err, fs.ErrExist)) {")])
mut("M16", "a guard refusal is cleared by a later successful write",
    [(EVAL, "\tl.seen[sha] = struct{}{}\n\tl.clearMissing(sha)\n",
      "\tl.seen[sha] = struct{}{}\n\tl.clearMissing(sha)\n\tl.guardRefusals.Store(0)\n")])
mut("M17", "`incomplete` ignores AnswersMissing",
    [(MAIN, "\tif c.AnswersMissing > 0 {", "\tif false && c.AnswersMissing > 0 {")])
mut("M18", "`incomplete` reports WriteErrors under the Dropped condition's count (fields crossed)",
    [(MAIN, "\tif c.WriteErrors > 0 {\n\t\twhy = append(why, fmt.Sprintf(\"%d record line(s) failed to write\", c.WriteErrors))",
      "\tif c.WriteErrors > 0 {\n\t\twhy = append(why, fmt.Sprintf(\"%d evaluation record(s) were dropped\", c.WriteErrors))")])

mut("M19", "a failed temp write/chmod/close is ignored: the (possibly truncated) temp is linked under {sha}.txt",
    [(EVAL, "\tif werr != nil {\n\t\t_ = l.removeFile(tmpName)\n\t\tl.answerFailed(sha, werr)\n\t\treturn\n\t}\n", "\t_ = werr\n")])
mut("M20", "finishRun reads the counters BEFORE Close (a queued record is not yet counted)",
    [(MAIN, "\tcloseErr = l.Close()\n\tverdict = incomplete(runCounts{\n\t\tDropped:        l.Dropped(),\n\t\tWriteErrors:    l.WriteErrors(),\n\t\tGuardRefusals:  l.GuardRefusals(),\n\t\tAnswersMissing: l.AnswersMissing(),\n\t\tCloseErr:       closeErr,\n\t})\n\treturn closeErr, verdict",
      "\tcounts := runCounts{Dropped: l.Dropped(), WriteErrors: l.WriteErrors(), GuardRefusals: l.GuardRefusals(), AnswersMissing: l.AnswersMissing()}\n\tcloseErr = l.Close()\n\tcounts.CloseErr = closeErr\n\tverdict = incomplete(counts)\n\treturn closeErr, verdict")])
mut("M21", "finishRun does not pass the guard-refusal count to `incomplete`",
    [(MAIN, "\t\tGuardRefusals:  l.GuardRefusals(),\n", "\t\tGuardRefusals:  0,\n")])
mut("M22", "the Tier-2 call site left on the old assignment (hash set, text not)",
    [(HANDLER, "\t\trec.SetAnswer(t2.Candidate.Entry.Answer)\n", "\t\trec.AnswerSHA256 = sha256Hex(t2.Candidate.Entry.Answer)\n")],
    {"internal/httpapi/mut_sha.go": OLD_SHA})
mut("M23", "the MISS call site left on the old assignment (hash set, text not)",
    [(HANDLER, "\trec.SetAnswer(gen.Text)\n", "\trec.AnswerSHA256 = sha256Hex(gen.Text)\n")],
    {"internal/httpapi/mut_sha.go": OLD_SHA})
mut("M24", "the Tier-1 site stores a consistent but WRONG text (the served answer plus a space)",
    [(HANDLER, "\t\trec.SetAnswer(entry.Answer)\n", "\t\trec.SetAnswer(entry.Answer + \" \")\n")])
mut("M25", "the MISS site skips SetAnswer when the client has left (a completed generation is dropped)",
    [(HANDLER, "\trec.SetAnswer(gen.Text)\n", "\tif ctx.Err() == nil {\n\t\trec.SetAnswer(gen.Text)\n\t}\n")])


def run(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=900)
    return p.returncode, p.stdout + p.stderr


def build_copy(name, edits, extras, drop_new):
    work = SCRATCH / name
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(REPO / "gateway", work)
    for f, old, new in edits:
        p = work / f
        t = p.read_text()
        assert t.count(old) == 1, f"{name}: anchor not unique in {f}: {old[:70]!r} ({t.count(old)})"
        p.write_text(t.replace(old, new))
    for f, content in extras.items():
        (work / f).write_text(content)
    if drop_new:
        for f in NEW_FILES:
            (work / f).unlink()
    return work


rows, all_ok = [], True

base = build_copy("base", [], {}, False)
code, out = run(["go", "test", "-count=1", *PKGS], base)
rows.append(("(none)", "the change as written", "—", "passes" if code == 0 else "**FAILS**"))
print("base:", "pass" if code == 0 else "FAIL", flush=True)
all_ok &= code == 0

ONLY = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
for mid, desc, edits, extras in M:
    if ONLY and mid not in ONLY:
        continue
    # (a) the existing suite alone
    ex = build_copy(f"{mid}-existing", edits, extras, True)
    code_e, out_e = run(["go", "test", "-count=1", *PKGS], ex)
    if code_e == 0:
        existing = "passes"
    else:
        f = sorted(set(re.findall(r"--- FAIL: (\S+)", out_e)))
        existing = "FAILS: " + (", ".join(f) if f else "(build error)")
    # (b) the full suite
    nw = build_copy(f"{mid}-new", edits, extras, False)
    code_n, out_n = run(["go", "test", "-count=1", *PKGS], nw)
    fails = sorted(set(re.findall(r"--- FAIL: (Test\w+)", out_n)))
    if code_n != 0 and not fails:
        caught = "**BUILD ERROR, not a catch**: " + (out_n.strip().splitlines() or ["?"])[-1][:110]
        all_ok = False
    elif not fails:
        caught = "**NOT CAUGHT**"
        all_ok = False
    else:
        by_new = [f for f in fails if f in new_tests]
        if not by_new:
            caught = "**caught only by an existing test**: " + ", ".join(fails)
            all_ok = False
        else:
            caught = ", ".join(by_new)
    rows.append((mid, desc, caught, existing))
    print(mid, "|", caught, "| existing:", existing, flush=True)

lines = ["# Mutations — design.md §5", "",
         "Each mutation was applied to a fresh **copy** of `gateway/` (the working tree with the change,",
         "never the working tree itself). Two runs each: the **existing suite** alone (the three new test",
         "files removed), and the **full suite**. A mutation counts as caught only when a **new** test",
         "fails by assertion; a build error is not a catch.", "",
         "| # | Mutation | New tests that fail | Existing suite |", "| :---: | :--- | :--- | :---: |"]
for r in rows:
    lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |")
lines += ["", f"**Every mutation caught by a new test, none by a build error: {'yes' if all_ok else 'NO (see above)'}.**"]
OUT.write_text("\n".join(lines) + "\n")
