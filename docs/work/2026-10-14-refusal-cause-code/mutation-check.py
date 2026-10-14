#!/usr/bin/env python3
"""Hand mutation check for item 2.3 (plan step 7): reuse/cause.go, httpapi/cascade.go,
httpapi/handler.go and telemetry/evallog.go.

Usage (from the repo root):   python3 -I docs/work/2026-10-14-refusal-cause-code/mutation-check.py

It copies gateway/ to a temp directory, applies ONE edit at a time to the copy, runs
`go test ./internal/reuse ./internal/httpapi ./internal/telemetry`, and reports whether the tests
turned red. The real source is never edited. A mutant that stays GREEN means a rule is not pinned by
any test: add a test, then re-run.

If a source file changes, a pattern below may stop matching. The script then reports SKIP for it. Fix
the pattern here; do not ignore the SKIP.

Known equivalent edit, NOT in the list (it cannot change a result):
  * `SupportResult.Scored()` requiring only the lexical arm: both arms share one stale-server rule.

CORRECTION (/ai-review F3, 2026-10-14). An earlier version of this note also called "pass the entry's
`SourceChunkIDs` to Judge instead of `retrieved.ChunkIDs`" equivalent. It is NOT: a candidate with empty
provenance plus a stale server turns NOT_SCORED into SUPPORT. It is in the list now, and
TestCauseStaleServerWithAnUnprovenancedCandidateIsStillNotScored catches it.
"""
import pathlib, re, shutil, subprocess, sys, tempfile

repo = pathlib.Path(__file__).resolve().parents[3]
work = pathlib.Path(tempfile.mkdtemp(prefix="cause-mutants-"))
shutil.copytree(repo / "gateway", work / "gateway")
root = work / "gateway"

CAUSE = "internal/reuse/cause.go"
CASCADE = "internal/httpapi/cascade.go"
HANDLER = "internal/httpapi/handler.go"
EVALLOG = "internal/telemetry/evallog.go"

M = [
 # --- the order and the comparisons in Judge
 ("swap NAMESPACE and SIMILARITY (A2)", CAUSE,
  "\tif !(d.Match && (d.Rule != RuleComposite || d.LaneMatch)) {\n\t\treturn Judgement{Cause: CauseNamespace}\n\t}\n\tif !(similarity >= t.Tau) {\n\t\treturn Judgement{Cause: CauseSimilarity}\n\t}\n",
  "\tif !(similarity >= t.Tau) {\n\t\treturn Judgement{Cause: CauseSimilarity}\n\t}\n\tif !(d.Match && (d.Rule != RuleComposite || d.LaneMatch)) {\n\t\treturn Judgement{Cause: CauseNamespace}\n\t}\n"),
 ("similarity written negatively (NaN passes)", CAUSE, "if !(similarity >= t.Tau) {", "if similarity < t.Tau {"),
 ("drop the lane term of the MIXED rule", CAUSE, "(d.Rule != RuleComposite || d.LaneMatch)", "true"),
 ("drop the namespace term", CAUSE, "if !(d.Match && (d.Rule != RuleComposite || d.LaneMatch)) {", "if false {"),
 ("NOT_SCORED coded as SUPPORT", CAUSE, "Cause: CauseNotScored, Support: &sr", "Cause: CauseSupport, Support: &sr"),
 ("drop the NOT_SCORED branch", CAUSE, "\tcase !sr.Scored():\n\t\treturn Judgement{Cause: CauseNotScored, Support: &sr}\n", ""),
 ("numeric arm never runs", CAUSE, "Numeric: SupportNumeric(answer, texts, retrievedChunkIDs),", "Numeric: NumericVerdict{Scored: true},"),
 ("lexical arm never runs", CAUSE, "Lex:     SupportLexical(answer, texts, retrievedChunkIDs),", "Lex:     SupportVerdict{Scored: true, Score: 1, ContentTokenCount: 1},"),
 ("Judge is handed the ENTRY's source IDs (review F3)", CASCADE,
  "c.Entry.Answer, retrieved.Texts, retrieved.ChunkIDs)", "c.Entry.Answer, retrieved.Texts, c.Entry.SourceChunkIDs)"),
 ("an embed or retrieve failure carries a cause (review F1)", CASCADE,
  "\tif vec == nil || retrieved == nil {\n\t\treturn tier2Outcome{}\n\t}",
  "\tif vec == nil || retrieved == nil {\n\t\treturn tier2Outcome{Cause: reuse.CauseSimilarity}\n\t}"),
 ("a search error carries a cause (review F1)", CASCADE,
  "\t\tlog.Printf(\"gateway: tier-2 namespace search failed, degrading to MISS: %v\", err)\n\t\treturn out",
  "\t\tlog.Printf(\"gateway: tier-2 namespace search failed, degrading to MISS: %v\", err)\n\t\tout.Cause = reuse.CauseNamespace\n\t\treturn out"),
 ("the empty-namespace exit carries a cause (review F1)", CASCADE,
  "\tif out.QueryNS == \"\" {\n\t\treturn out\n\t}",
  "\tif out.QueryNS == \"\" {\n\t\tout.Cause = reuse.CauseNamespace\n\t\treturn out\n\t}"),
 ("CheckSupport drops the chunk IDs (lexical)", CAUSE, "SupportLexical(answer, texts, retrievedChunkIDs),", "SupportLexical(answer, texts, nil),"),
 ("CheckSupport drops the chunk IDs (numeric)", CAUSE, "SupportNumeric(answer, texts, retrievedChunkIDs),", "SupportNumeric(answer, texts, nil),"),
 ("write CONTAINMENT", CAUSE, "return Judgement{Cause: CauseSimilarity}", "return Judgement{Cause: CauseContainment}"),
 ("rename a cause value", CAUSE, 'CauseNone = "NONE"', 'CauseNone = "OK"'),
 # --- the cascade
 ("drop the zero-chunk guard", CASCADE, "if len(retrieved.ChunkIDs) == 0 {", "if false {"),
 ("serve unless an arm refuses (review N1)", CASCADE,
  "out.Cause, out.Support, out.Served = j.Cause, j.Support, j.Served()",
  "out.Cause, out.Support, out.Served = j.Cause, j.Support, out.NSDecision.Reuse && (j.Support == nil || !j.Support.Refuses())"),
 ("a cold namespace coded NAMESPACE", CASCADE,
  "\tif len(scoped) == 0 {\n\t\treturn out\n\t}\n", "\tif len(scoped) == 0 {\n\t\tout.Cause = reuse.CauseNamespace\n\t\treturn out\n\t}\n"),
 # --- the handler
 ("serve on the lane rule alone", HANDLER, "\tif t2.Served {\n", "\tif t2.NSDecision.Reuse {\n"),
 ("set the cause only on the miss path", HANDLER,
  "\th.recordCause(&rec, t2, requestID)\n",
  "\tdefer func() {\n\t\tif rec.Cache == cacheMiss {\n\t\t\th.recordCause(&rec, t2, requestID)\n\t\t}\n\t}()\n"),
 ("a served hit coded null", HANDLER, 'if t2.Cause == "" {\n\t\treturn\n\t}', 'if t2.Cause == "" || t2.Cause == reuse.CauseNone {\n\t\treturn\n\t}'),
 ("a stale server logs zeros, not nulls", HANDLER, "if s := t2.Support; s != nil && s.Scored() {", "if s := t2.Support; s != nil {"),
 ("support_numeric_ok inverted", HANDLER, "numericOK := s.Lex.Score, s.Numeric.Admits()", "numericOK := s.Lex.Score, s.Numeric.Refuses()"),
 ("candidate named only when served (review F1)", HANDLER, "\tif t2.Found {\n\t\trec.CandidateEntryID", "\tif t2.Found && t2.Served {\n\t\trec.CandidateEntryID"),
 ("NOT_SCORED alarm on every request", HANDLER, "h.notScoredLogged.CompareAndSwap(false, true)", "true"),
 # --- the record
 ("refusal_cause gets omitempty", EVALLOG, '`json:"refusal_cause"`', '`json:"refusal_cause,omitempty"`'),
 ("support_lex gets omitempty", EVALLOG, '`json:"support_lex"`', '`json:"support_lex,omitempty"`'),
 ("support_numeric_ok gets omitempty", EVALLOG, '`json:"support_numeric_ok"`', '`json:"support_numeric_ok,omitempty"`'),
 ("candidate_entry_id loses omitempty", EVALLOG, '`json:"candidate_entry_id,omitempty"`', '`json:"candidate_entry_id"`'),
 ("candidate_sources loses omitempty", EVALLOG, '`json:"candidate_sources,omitempty"`', '`json:"candidate_sources"`'),
]

orig = {}
for _, f, _, _ in M:
    orig.setdefault(f, (root / f).read_text())

bad = 0
for name, f, a, b in M:
    src = root / f
    text = orig[f]
    n = text.count(a)
    if n != 1:
        print(f"SKIP  {name}: pattern found {n} times in {f}")
        bad += 1
        continue
    src.write_text(text.replace(a, b))
    r = subprocess.run(["go", "test", "-count=1", "./internal/reuse", "./internal/httpapi", "./internal/telemetry"],
                       cwd=root, capture_output=True, text=True)
    out = r.stdout + r.stderr
    failed = sorted(set(re.findall(r"--- FAIL: (\w+)", out)))
    if r.returncode == 0:
        print(f"GREEN (SURVIVED) {name}")
        bad += 1
    elif not failed:
        print(f"BUILD-ERROR {name}: {out.strip().splitlines()[:3]}")
        bad += 1
    else:
        print(f"red   {name}  <- {', '.join(failed[:3])}")
    src.write_text(text)

shutil.rmtree(work, ignore_errors=True)
print(f"{len(M)} edits, {len(M) - bad} red, {bad} survivors or problems")
sys.exit(1 if bad else 0)
