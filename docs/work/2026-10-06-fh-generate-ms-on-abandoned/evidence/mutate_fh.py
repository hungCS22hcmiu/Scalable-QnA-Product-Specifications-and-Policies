"""Apply each design.md §4 mutation (F1-F9) of the F-H fix to a fresh COPY of gateway/ and record what
stops it. The working tree is never touched. Two runs each:
  (a) the EXISTING suite (generatems_test.go removed): informational;
  (b) the FULL suite: at least one NEW test must fail, by ASSERTION and not by a build error.
Usage: mutate_fh.py <scratch dir> <output md> [F1,F6,...]   (a filter writes a partial report: use a scratch OUT)
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path("/Users/hung/Desktop/Sem1/thesis")
SCRATCH = Path(sys.argv[1])
OUT = Path(sys.argv[2])
ONLY = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None

HANDLER = "internal/httpapi/handler.go"
NEW_FILE = "internal/httpapi/generatems_test.go"
PKGS = ["./internal/httpapi/"]
new_tests = set(re.findall(r"^func (Test\w+)\(", (REPO / "gateway" / NEW_FILE).read_text(), re.M))

FIX = "\trec.GenerateMS = generateMS\n\n\tswitch {\n"
FIX_OFF = "\tswitch {\n"
SUCC_OLD = "\trec.SetAnswer(gen.Text)\n\trec.Coalesced = shared\n"
SUCC_ON = "\trec.SetAnswer(gen.Text)\n\trec.GenerateMS = generateMS\n\trec.Coalesced = shared\n"
GENFAIL = "\tcase err != nil:\n\t\trec.Cache = cacheGenFailed\n"
ABANDON = "\t\trec.Cache = cacheAbandoned\n"
AFTER_ANSWER = "\t\tgenerateMS = msPtr(time.Since(genStart))\n\t\tif err != nil {\n\t\t\treturn nil, err\n\t\t}\n"

M = []
def mut(mid, desc, edits):
    M.append((mid, desc, edits))

mut("F1", "revert the fix: copy `generateMS` only on the success path",
    [(HANDLER, FIX, FIX_OFF), (HANDLER, SUCC_OLD, SUCC_ON)])
mut("F2", "copy only for GENERATION_FAILED (and the success path)",
    [(HANDLER, FIX, FIX_OFF), (HANDLER, SUCC_OLD, SUCC_ON),
     (HANDLER, GENFAIL, GENFAIL + "\t\trec.GenerateMS = generateMS\n")])
mut("F3", "copy only for ABANDONED (and the success path)",
    [(HANDLER, FIX, FIX_OFF), (HANDLER, SUCC_OLD, SUCC_ON),
     (HANDLER, ABANDON, ABANDON + "\t\trec.GenerateMS = generateMS\n")])
mut("F4", "assign a constant non-nil value before the switch (followers, queued and SHED carry it)",
    [(HANDLER, FIX, "\trec.GenerateMS = msPtr(time.Millisecond)\n\t_ = generateMS\n\n\tswitch {\n")])
mut("F5", "copy only inside the success branch of the closure",
    [(HANDLER, FIX, FIX_OFF),
     (HANDLER, AFTER_ANSWER, AFTER_ANSWER + "\t\trec.GenerateMS = generateMS\n")])
mut("F6", "record the time since Ask began instead of the generation's own span",
    [(HANDLER, FIX, "\trec.GenerateMS = msPtr(time.Since(start))\n\t_ = generateMS\n\n\tswitch {\n")])
mut("F7", "`genStart` moved above Acquire (the span includes the permit wait)",
    [(HANDLER, "\t\tpermit, err := h.Admission.Acquire(ctx)\n",
      "\t\tgenStart := time.Now()\n\t\tpermit, err := h.Admission.Acquire(ctx)\n"),
     (HANDLER, "\t\tgenStart := time.Now()\n\t\t// Hand the service", "\t\t// Hand the service")])

mut("F8", "the MISS span runs to the END of the closure (it includes write-back)",
    [(HANDLER, "\t\treturn &generation{\n", "\t\tgenerateMS = msPtr(time.Since(genStart))\n\t\treturn &generation{\n")])
mut("F9", "a coalesced MISS follower is given a generation time (a copied or shared span)",
    [(HANDLER, SUCC_OLD.replace("\trec.Coalesced = shared\n", "") + "\trec.Coalesced = shared\n",
      "\trec.SetAnswer(gen.Text)\n\trec.Coalesced = shared\n\tif shared {\n\t\trec.GenerateMS = msPtr(time.Millisecond)\n\t}\n")])


def run(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=900)
    return p.returncode, p.stdout + p.stderr


def build_copy(name, edits, drop_new):
    work = SCRATCH / name
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(REPO / "gateway", work)
    for f, old, new in edits:
        p = work / f
        t = p.read_text()
        assert t.count(old) == 1, f"{name}: anchor not unique in {f}: {old[:70]!r} ({t.count(old)})"
        p.write_text(t.replace(old, new))
    if drop_new:
        (work / NEW_FILE).unlink()
    return work


rows, all_ok = [], True
base = build_copy("base", [], False)
code, out = run(["go", "test", "-count=1", *PKGS], base)
rows.append(("(none)", "the fix as written", "—", "passes" if code == 0 else "**FAILS**"))
print("base:", "pass" if code == 0 else "FAIL", flush=True)
all_ok &= code == 0

for mid, desc, edits in M:
    if ONLY and mid not in ONLY:
        continue
    ex = build_copy(f"{mid}-existing", edits, True)
    code_e, out_e = run(["go", "test", "-count=1", *PKGS], ex)
    if code_e == 0:
        existing = "passes"
    else:
        f = sorted(set(re.findall(r"--- FAIL: (\S+)", out_e)))
        existing = "FAILS: " + (", ".join(f) if f else "(build error)")
    nw = build_copy(f"{mid}-new", edits, False)
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

lines = ["# Mutations — design.md §4", "",
         "Each mutation was applied to a fresh **copy** of `gateway/` (the working tree with the fix, never the",
         "working tree itself). Two runs each: the **existing suite** alone (`generatems_test.go` removed), and the",
         "**full suite**. A mutation counts as caught only when a **new** test fails by assertion; a build error is",
         "not a catch.", "",
         "| # | Mutation | New tests that fail | Existing suite |", "| :---: | :--- | :--- | :---: |"]
for r in rows:
    lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |")
lines += ["", f"**Every mutation caught by a new test, none by a build error: {'yes' if all_ok else 'NO (see above)'}.**"]
OUT.write_text("\n".join(lines) + "\n")
