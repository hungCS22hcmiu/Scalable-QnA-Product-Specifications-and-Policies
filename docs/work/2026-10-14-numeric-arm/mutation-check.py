#!/usr/bin/env python3
"""Hand mutation check for gateway/internal/reuse/support_numeric.go (item 2.2, plan step 7).

Usage (from the repo root):   python3 -I docs/work/2026-10-14-numeric-arm/mutation-check.py

It copies gateway/ to a temp directory, applies ONE edit at a time to the copy, runs
`go test ./internal/reuse`, and reports whether the tests turned red. The real source is never
edited. A mutant that stays GREEN means a rule is not pinned by any test: add a row, then re-run.

If you change support_numeric.go, a pattern below may stop matching. The script then reports SKIP
for it. Fix the pattern here; do not ignore the SKIP.
"""
import pathlib, re, shutil, subprocess, sys, tempfile

repo = pathlib.Path(__file__).resolve().parents[3]
work = pathlib.Path(tempfile.mkdtemp(prefix="numeric-mutants-"))
shutil.copytree(repo / "gateway", work / "gateway")
root = work / "gateway"
src = root / "internal/reuse/support_numeric.go"
orig = src.read_text()

M = [
 # --- first 23: the original plan step 7 list plus 14 more
 ("drop the unit check", "if _, ok := f.units[it.unit]; ok {", "if true {"),
 ("join the chunks (R8)", "chunks := make([]numFacts, len(texts))\n\tfor i, t := range texts {\n\t\tchunks[i] = factsOf(readNumbers(t))\n\t}",
  "chunks := []numFacts{factsOf(readNumbers(strings.Join(texts, \"\\n\")))}"),
 ("drop the hyphen rule", "if hw := hyphenWidth(s, p); hw > 0 {", "if hw := hyphenWidth(s, p); hw > 0 && false {"),
 ("drop plural stripping", "if len(w) >= 3 && w[len(w)-1] == 's' {", "if false {"),
 ("trim zeros of integers", "if intPart == \"\" {\n\t\tintPart = \"0\"\n\t}", "intPart = strings.TrimRight(intPart, \"0\")\n\tif intPart == \"\" {\n\t\tintPart = \"0\"\n\t}"),
 ("split decimals", "(s[k] == '.' || s[k] == ',') && asciiDigit(s[k+1])", "(s[k] == ',') && asciiDigit(s[k+1])"),
 ("ignore codes in words", "sc.add(numItem{code: true, value: strings.ToLower(s[i:k])})", "_ = k"),
 ("vs read as plural (needs only 1 letter left)", "if len(w) >= 3 && w[len(w)-1] == 's' {", "if len(w) >= 2 && w[len(w)-1] == 's' {"),
 ("unreadable blob ignored", "if !blobValid(blob) {\n\t\tsc.out.unreadable++\n\t\treturn k\n\t}", "if !blobValid(blob) {\n\t\treturn k\n\t}"),
 ("compound only with hyphen", "if q, _ := afterSeparator(s, end); val >= 20 && val%10 == 0 && q > end {", "if q, via := afterSeparator(s, end); val >= 20 && val%10 == 0 && q > end && via {"),
 ("no list-marker rule", "if strings.ContainsAny(blob, \".,\") {\n\t\treturn false\n\t}", "if true {\n\t\treturn false\n\t}"),
 ("number words read without a unit", "\tif unit, uend, ok := sc.unitAfter(end); ok {\n\t\tsc.add(numItem{value: strconv.Itoa(val), unit: unit})\n\t\treturn uend\n\t}\n\treturn end",
  "\tif unit, uend, ok := sc.unitAfter(end); ok {\n\t\tsc.add(numItem{value: strconv.Itoa(val), unit: unit})\n\t\treturn uend\n\t}\n\tsc.add(numItem{value: strconv.Itoa(val)})\n\treturn end"),
 ("glued non-unit read as number, not code", "sc.add(numItem{code: true, value: strings.ToLower(s[i:m])})", "sc.add(numItem{value: value})"),
 ("no currency prefix", "strings.ContainsRune(numCurrency, r)", "false"),
 ("non-ASCII numbers ignored", "\tsc.out.unreadable++\n\ti += n\n\tfor i < len(sc.s) {", "\ti += n\n\tfor i < len(sc.s) {"),
 ("no stale-server check", "if len(texts) == 0 && len(retrievedChunkIDs) > 0 {", "if false {"),
 ("Refuses ignores Unreadable", "v.Scored && (v.Unsupported > 0 || v.Unreadable > 0)", "v.Scored && v.Unsupported > 0"),
 ("no leading-point rule", "if i > 0 && s[i-1] == '.' &&", "if false &&"),
 ("blocked words pass", "sc.out.unreadable++\n\t\t\treturn end", "return end"),
 ("percent sign not a unit", "return \"percent\", q + 1, true", "return \"\", p, false"),
 ("Unitless never counted", "if !it.code && it.unit == \"\" {\n\t\t\tv.Unitless++\n\t\t}", ""),
 ("code compared case-sensitively", "sc.add(numItem{code: true, value: strings.ToLower(s[i:k])})", "sc.add(numItem{code: true, value: s[i:k]})"),
 ("evidence units = every unit word", "if it.unit != \"\" {\n\t\t\tf.units[it.unit] = struct{}{}\n\t\t}", "f.units[it.unit] = struct{}{}\n\t\tf.units[\"hour\"] = struct{}{}"),
 # --- added after /ai-review (the reviewer's survivors, now pinned by rows)
 ("line break allowed between number and unit", "case ' ', '\\t', '\\u00a0', '\\u202f':", "case ' ', '\\t', '\\n', '\\u00a0', '\\u202f':"),
 ("list marker without the whole-number check", "if strings.ContainsAny(blob, \".,\") {\n\t\treturn false\n\t}", "if false {\n\t\treturn false\n\t}"),
 ("leading point also after a word", "(i < 2 || !asciiAlnum(s[i-2]))", "true"),
 ("no tab between number and unit", "case ' ', '\\t', '\\u00a0', '\\u202f':", "case ' ', '\\u00a0', '\\u202f':"),
 ("no tab before a list marker", "s[p] != ' ' && s[p] != '\\t'", "s[p] != ' '"),
 ("plural cut needs 3 letters (lbs, kgs lose their unit)", "if len(w) >= 3 && w[len(w)-1] == 's' {", "if len(w) >= 4 && w[len(w)-1] == 's' {"),
 ("glued unit not lowercased", "canonUnit(strings.ToLower(s[k:m]))", "canonUnit(s[k:m])"),
 ("ones word not lowercased", "numWords[strings.ToLower(s[q:m])]", "numWords[s[q:m]]"),
 ("first thousands group may be any length", "if len(groups[0]) > 3 {", "if false {"),
 ("tens + any word is a compound", "ones >= 1 && ones <= 9", "true"),
 ("blocked word unreadable even without a unit", "if _, end, ok := sc.unitAfter(j); ok {\n\t\t\tsc.out.unreadable++\n\t\t\treturn end\n\t\t}",
  "sc.out.unreadable++\n\t\tif _, end, ok := sc.unitAfter(j); ok {\n\t\t\treturn end\n\t\t}"),
 # --- added with the separator change (no-break space and hyphen), after /ai-review
 ("no-break space is not a space", "case ' ', '\\t', '\\u00a0', '\\u202f':", "case ' ', '\\t', '\\u202f':"),
 ("narrow no-break space is not a space", "case ' ', '\\t', '\\u00a0', '\\u202f':", "case ' ', '\\t', '\\u00a0':"),
 ("U+2011 is not a hyphen", "case '-', '\\u2011':", "case '-':"),
 ("only one space is skipped", "for sw := spaceWidth(s, q); sw > 0; sw = spaceWidth(s, q) {\n\t\tq += sw\n\t}", "if sw := spaceWidth(s, q); sw > 0 {\n\t\tq += sw\n\t}"),
 ("en dash accepted as a hyphen", "case '-', '\\u2011':", "case '-', '\\u2011', '\\u2013':"),
 ("thin space accepted as a space", "case ' ', '\\t', '\\u00a0', '\\u202f':", "case ' ', '\\t', '\\u00a0', '\\u202f', '\\u2009':"),
 ("digit-first code loses its tail", "m = codeTail(s, m) // \"12x1.5\" is one code, as \"M12x1.5\" is\n", ""),
]

bad = 0
for name, a, b in M:
    n = orig.count(a)
    if n != 1:
        print(f"SKIP  {name}: pattern found {n} times"); bad += 1; continue
    src.write_text(orig.replace(a, b))
    r = subprocess.run(["go", "test", "-count=1", "./internal/reuse"], cwd=root, capture_output=True, text=True)
    out = r.stdout + r.stderr
    failed = sorted(set(re.findall(r"--- FAIL: (\w+)", out)))
    if r.returncode == 0:
        print(f"GREEN (SURVIVED) {name}"); bad += 1
    elif not failed:
        print(f"BUILD-ERROR {name}: {out.strip().splitlines()[:3]}"); bad += 1
    else:
        print(f"red   {name}  <- {', '.join(failed[:3])}")
src.write_text(orig)
shutil.rmtree(work, ignore_errors=True)
print(f"{len(M)} edits, {len(M) - bad} red, {bad} survivors or problems")
sys.exit(1 if bad else 0)
