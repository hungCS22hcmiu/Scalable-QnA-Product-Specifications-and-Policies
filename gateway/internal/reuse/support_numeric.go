package reuse

import (
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"
)

// The numeric arm of the answer-evidence support gate (super-plan.md item 2.2): every number in the
// cached answer, with its unit, must also be in the fresh evidence, and a number this arm cannot
// read blocks reuse. Fail-closed: when unsure, refuse. Standard library only, no I/O, so it can be
// falsified in isolation (docs/architecture.md 2), like support.go.
//
// Nothing on the served path calls this yet. Wiring needs the refusal cause code (item 2.3) and the
// on/off switch (item 2.4).
//
// The rules below ARE the arm's definition, in the same way the stopword list is part of S_lex. The
// arm has no threshold, so the grammar is the only knob, and an edit to any rule, list or table in
// this file silently rescales every support_numeric_ok logged before it. Once a run has logged it,
// an edit needs a numbered decisions.md entry with an Invalidates line. The approved text of the
// rules (R1-R9) is docs/work/2026-10-14-numeric-arm/approvals.md, "Frozen artefact". The tests pin
// them: TestNumericReaderGolden, TestNumericReaderRules, TestNumericNormalisation,
// TestNumericUnitListPinned, TestNumericNumberWordsPinned, TestNumericUnicodeNumbers.
//
// It does NOT use eachToken, contentTokens or textTokens from support.go. They split "5.3" into 5
// and 3, and they drop "30" for being under three characters.

// NumericVerdict is the numeric arm's result.
//
// Like SupportVerdict, a struct and not a bool: a bool would have to call a stale server either a
// refusal (a false SUPPORT) or null (a false "gate off"). Decide through Refuses or Admits, never
// by reading the counts.
type NumericVerdict struct {
	// Scored is false exactly when the RAG service sent chunk IDs with no evidence text (a pre-1.4
	// server). That is neither a refusal nor the gate-off arm. Every other field is meaningless
	// unless Scored is true.
	Scored bool
	// Numbers is how many distinct items the answer holds: numbers (value and unit) and codes.
	Numbers int
	// Unsupported is how many of them no single evidence chunk supports.
	Unsupported int
	// Unreadable is how many number-like spans in the ANSWER could not be read. Each one blocks.
	Unreadable int
	// Unitless is how many numbers were checked by value only, because no listed unit follows them
	// (design.md D2). It never blocks. It is here so the gap can be measured.
	Unitless int
}

// Refuses reports whether the numeric arm refuses reuse: it scored, and something in the answer is
// unsupported or unreadable. An unscored verdict neither refuses nor admits.
func (v NumericVerdict) Refuses() bool {
	return v.Scored && (v.Unsupported > 0 || v.Unreadable > 0)
}

// Admits reports whether the arm scored and found nothing to refuse. It is not !Refuses(), which is
// also true for an unscored verdict.
func (v NumericVerdict) Admits() bool {
	return v.Scored && !v.Refuses()
}

// SupportNumeric checks the cached answer's numbers against the fresh evidence, chunk by chunk.
//
// An item is supported when ONE chunk has its value and, if it has a unit, the same chunk has that
// unit attached to some number in it. Chunks are read one at a time and never joined, so a number in
// one chunk is never paired with a unit in the next. The query text is never read.
//
// retrievedChunkIDs is the chunk IDs of the FRESH retrieval, as in SupportLexical, and is used only
// to tell a stale server from an empty retrieval: texts empty with chunk IDs present is not scored.
// An empty retrieval has no special case: an answer with a number is refused (the number is
// unsupported), an answer with no numbers is admitted. Closing the zero-chunk hole is item 2.3's job,
// in the cascade.
func SupportNumeric(answer string, texts []string, retrievedChunkIDs []string) NumericVerdict {
	if len(texts) == 0 && len(retrievedChunkIDs) > 0 {
		return NumericVerdict{}
	}
	ans := readNumbers(answer)
	chunks := make([]numFacts, len(texts))
	for i, t := range texts {
		chunks[i] = factsOf(readNumbers(t))
	}
	v := NumericVerdict{Scored: true, Unreadable: ans.unreadable}
	for _, it := range ans.items {
		v.Numbers++
		if !it.code && it.unit == "" {
			v.Unitless++
		}
		if !numSupported(it, chunks) {
			v.Unsupported++
		}
	}
	return v
}

// numCurrency are the symbols read as a unit when they sit directly before a number.
const numCurrency = "$€£"

// numUnits is the closed list of canonical units (R6). Draft until the Phase 3 corpus freeze, and
// frozen before any false-hit sample is looked at.
var numUnits = map[string]struct{}{
	"second": {}, "minute": {}, "hour": {}, "day": {}, "week": {}, "month": {}, "year": {},
	"g": {}, "kg": {}, "mg": {}, "lb": {}, "oz": {},
	"mm": {}, "cm": {}, "km": {}, "inch": {}, "ft": {},
	"ml": {}, "litre": {},
	"w": {}, "kw": {}, "v": {}, "mah": {}, "wh": {},
	"hz": {}, "khz": {}, "mhz": {}, "ghz": {}, "kb": {}, "mb": {}, "gb": {}, "tb": {}, "db": {},
	"rpm": {}, "percent": {},
}

// numUnitAlias maps a spelling to its canonical unit.
var numUnitAlias = map[string]string{
	"sec": "second", "min": "minute", "hr": "hour", "hrs": "hour", "yr": "year", "yrs": "year",
	"inches": "inch", "gram": "g", "kilogram": "kg", "pound": "lb", "foot": "ft", "feet": "ft",
	"liter": "litre", "watt": "w", "volt": "v",
}

// numWords are the number words read as digits (R7), and only when directly before a listed unit.
var numWords = map[string]int{
	"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
	"eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
	"fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
	"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
	"eighty": 80, "ninety": 90,
}

// numWordsBlocked are quantity words this arm does not read. Directly before a listed unit they
// count as Unreadable, so they block instead of passing.
var numWordsBlocked = map[string]struct{}{
	"hundred": {}, "thousand": {}, "million": {}, "half": {}, "dozen": {}, "couple": {},
}

// canonUnit returns the canonical unit for a lowercase word. A plural "s" is dropped only if at
// least two letters remain, so "days" is "day" but "vs" stays "vs" and is not the unit "v".
func canonUnit(w string) (string, bool) {
	if u, ok := numUnitAlias[w]; ok {
		return u, true
	}
	if _, ok := numUnits[w]; ok {
		return w, true
	}
	if len(w) >= 3 && w[len(w)-1] == 's' {
		s := w[:len(w)-1]
		if u, ok := numUnitAlias[s]; ok {
			return u, true
		}
		if _, ok := numUnits[s]; ok {
			return s, true
		}
	}
	return "", false
}

// numItem is one thing the reader found: a number with its clean value and unit ("" if none), or a
// code (R3) whose value is the lowercase token.
type numItem struct {
	code  bool
	value string
	unit  string
}

type numReading struct {
	items      []numItem // distinct, in order of first appearance
	unreadable int       // every occurrence counts
}

// numFacts is what one evidence chunk offers (R9): the values and codes it holds, and the units
// that are attached to a number in it. A unit word that sits next to no number is not one of them.
type numFacts struct {
	values map[string]struct{}
	units  map[string]struct{}
}

func factsOf(r numReading) numFacts {
	f := numFacts{values: make(map[string]struct{}), units: make(map[string]struct{})}
	for _, it := range r.items {
		f.values[it.value] = struct{}{}
		if it.unit != "" {
			f.units[it.unit] = struct{}{}
		}
	}
	return f
}

func numSupported(it numItem, chunks []numFacts) bool {
	for _, f := range chunks {
		if _, ok := f.values[it.value]; !ok {
			continue
		}
		if it.code || it.unit == "" {
			return true
		}
		if _, ok := f.units[it.unit]; ok {
			return true
		}
	}
	return false
}

// readNumbers is the one reader, used for the answer and for every evidence chunk (R9). Unreadable
// spans are counted here; the caller decides what they mean (they block in the answer and are
// ignored in evidence, because only the answer's count is read).
func readNumbers(s string) numReading {
	sc := &numScanner{s: s, seen: make(map[numItem]struct{})}
	for i := 0; i < len(s); {
		switch c := s[i]; {
		case asciiAlpha(c):
			i = sc.word(i)
		case asciiDigit(c):
			i = sc.digits(i)
		case c >= utf8.RuneSelf:
			i = sc.nonASCII(i)
		default:
			i++
		}
	}
	return sc.out
}

type numScanner struct {
	s    string
	out  numReading
	seen map[numItem]struct{}
}

func (sc *numScanner) add(it numItem) {
	if _, dup := sc.seen[it]; dup {
		return
	}
	sc.seen[it] = struct{}{}
	sc.out.items = append(sc.out.items, it)
}

func asciiDigit(c byte) bool { return c >= '0' && c <= '9' }
func asciiAlpha(c byte) bool { return c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' }
func asciiAlnum(c byte) bool { return asciiDigit(c) || asciiAlpha(c) }

// nonASCII handles a byte of 0x80 or more. A number character that is not an ASCII digit (a
// fraction, a superscript, an Arabic digit) is unreadable (R2): one count per run of them. Any other
// non-ASCII character is a separator.
func (sc *numScanner) nonASCII(i int) int {
	r, n := utf8.DecodeRuneInString(sc.s[i:])
	if !unicode.IsNumber(r) {
		return i + n
	}
	sc.out.unreadable++
	i += n
	for i < len(sc.s) {
		r, n = utf8.DecodeRuneInString(sc.s[i:])
		if r < utf8.RuneSelf || !unicode.IsNumber(r) {
			break
		}
		i += n
	}
	return i
}

// word handles a run starting with a letter: a code if it holds a digit (R3), a number word (R7),
// or an ordinary word, which is skipped.
func (sc *numScanner) word(i int) int {
	s := sc.s
	j := i
	for j < len(s) && asciiAlnum(s[j]) {
		j++
	}
	run := s[i:j]
	if strings.IndexFunc(run, func(r rune) bool { return r >= '0' && r <= '9' }) >= 0 {
		k := codeTail(s, j)
		sc.add(numItem{code: true, value: strings.ToLower(s[i:k])})
		return k
	}
	w := strings.ToLower(run)
	if v, ok := numWords[w]; ok {
		return sc.numberWord(j, v)
	}
	if _, ok := numWordsBlocked[w]; ok {
		if _, end, ok := sc.unitAfter(j); ok {
			sc.out.unreadable++
			return end
		}
	}
	return j
}

// numberWord reads a number word that ends at end. It is a number only if a listed unit follows
// ("two years", not "two ways"). A tens word may take a ones word after one hyphen or a run of
// spaces ("twenty-four", "twenty four", "twenty  four").
func (sc *numScanner) numberWord(end, val int) int {
	s := sc.s
	if q, _ := afterSeparator(s, end); val >= 20 && val%10 == 0 && q > end {
		m := q
		for m < len(s) && asciiAlpha(s[m]) {
			m++
		}
		if ones, ok := numWords[strings.ToLower(s[q:m])]; ok && ones >= 1 && ones <= 9 {
			if unit, uend, ok := sc.unitAfter(m); ok {
				sc.add(numItem{value: strconv.Itoa(val + ones), unit: unit})
				return uend
			}
		}
	}
	if unit, uend, ok := sc.unitAfter(end); ok {
		sc.add(numItem{value: strconv.Itoa(val), unit: unit})
		return uend
	}
	return end
}

// unitAfter looks for a listed unit right after position p: after one hyphen, or after a run of
// spaces (see afterSeparator; never across a line break). "%" counts after spaces. Only the very
// next word counts (R5). A comma or full stop in between ends the search, which is R4.
func (sc *numScanner) unitAfter(p int) (unit string, end int, ok bool) {
	s := sc.s
	q, viaHyphen := afterSeparator(s, p)
	if !viaHyphen && q < len(s) && s[q] == '%' {
		return "percent", q + 1, true
	}
	if q < len(s) && asciiAlpha(s[q]) {
		m := q
		for m < len(s) && asciiAlnum(s[m]) {
			m++
		}
		if u, ok := canonUnit(strings.ToLower(s[q:m])); ok {
			return u, m, true
		}
	}
	return "", p, false
}

// The separators the reader accepts between a number and its unit, and inside a compound number
// word (R5, R7). Exactly these, and no others:
//
//	space:  ' '  '\t'  U+00A0 (no-break space)  U+202F (narrow no-break space)
//	hyphen: '-'  U+2011 (non-breaking hyphen)
//
// The no-break forms are what typeset text and some models write ("30 days", "30\u2011day"). A line
// break is not a separator. En dash, U+2010, thin space and the other Unicode spaces are NOT
// accepted: the answer is then read by value only and the evidence loses the unit. TestNumericReaderRules
// pins both the accepted and the refused ones.
func spaceWidth(s string, q int) int {
	if q >= len(s) {
		return 0
	}
	switch r, n := utf8.DecodeRuneInString(s[q:]); r {
	case ' ', '\t', '\u00a0', '\u202f':
		return n
	}
	return 0
}

func hyphenWidth(s string, q int) int {
	if q >= len(s) {
		return 0
	}
	switch r, n := utf8.DecodeRuneInString(s[q:]); r {
	case '-', '\u2011':
		return n
	}
	return 0
}

// afterSeparator returns the position after one hyphen, or else after a run of spaces (possibly an
// empty run), and whether it was a hyphen.
func afterSeparator(s string, p int) (q int, viaHyphen bool) {
	if hw := hyphenWidth(s, p); hw > 0 {
		return p + hw, true
	}
	q = p
	for sw := spaceWidth(s, q); sw > 0; sw = spaceWidth(s, q) {
		q += sw
	}
	return q, false
}

// digits handles a run starting with a digit: R1, R2, R4, R5.
func (sc *numScanner) digits(i int) int {
	s := sc.s
	k := i
	for k < len(s) && asciiDigit(s[k]) {
		k++
	}
	// Join ".ddd" and ",ddd" parts. A point or comma NOT followed by a digit is punctuation (R4).
	for k+1 < len(s) && (s[k] == '.' || s[k] == ',') && asciiDigit(s[k+1]) {
		k++
		for k < len(s) && asciiDigit(s[k]) {
			k++
		}
	}
	blob := s[i:k]

	if i > 0 && s[i-1] == '.' && (i < 2 || !asciiAlnum(s[i-2])) { // ".5": would read as 5
		sc.out.unreadable++
		return k
	}
	if sc.listMarker(i, k, blob) {
		return k
	}
	if !blobValid(blob) {
		sc.out.unreadable++
		return k
	}
	value := canonNumber(blob)

	if k < len(s) && asciiAlpha(s[k]) { // letters glued to the number: a unit, or else a code
		m := k
		for m < len(s) && asciiAlnum(s[m]) {
			m++
		}
		if u, ok := canonUnit(strings.ToLower(s[k:m])); ok {
			sc.add(numItem{value: value, unit: u})
			return m
		}
		m = codeTail(s, m) // "12x1.5" is one code, as "M12x1.5" is
		sc.add(numItem{code: true, value: strings.ToLower(s[i:m])})
		return m
	}
	if r, _ := utf8.DecodeLastRuneInString(s[:i]); r != utf8.RuneError && strings.ContainsRune(numCurrency, r) {
		sc.add(numItem{value: value, unit: string(r)})
		return k
	}
	unit, _, _ := sc.unitAfter(k)
	sc.add(numItem{value: value, unit: unit})
	return k
}

// codeTail extends a code that ends at j with its ".digits" parts, so "v5.3" and "12x1.5" are each
// one code (R3). A point not followed by a digit is punctuation and stays out.
func codeTail(s string, j int) int {
	for j+1 < len(s) && s[j] == '.' && asciiDigit(s[j+1]) {
		j++
		for j < len(s) && asciiDigit(s[j]) {
			j++
		}
	}
	return j
}

// listMarker reports whether the digits at s[i:k] are a list marker: a whole number at the start of
// a line, with only spaces or tabs before it, followed by "." or ")" and a space ("1. Return...").
func (sc *numScanner) listMarker(i, k int, blob string) bool {
	s := sc.s
	if strings.ContainsAny(blob, ".,") {
		return false
	}
	if k+1 >= len(s) || (s[k] != '.' && s[k] != ')') || s[k+1] != ' ' {
		return false
	}
	for p := i - 1; p >= 0 && s[p] != '\n'; p-- {
		if s[p] != ' ' && s[p] != '\t' {
			return false
		}
	}
	return true
}

// blobValid is R1's grammar: digits, then optional ",ddd" groups, then an optional ".d+". The blob
// holds only digits, points and commas, each point or comma followed by a digit.
func blobValid(b string) bool {
	intPart, frac, hasFrac := strings.Cut(b, ".")
	if hasFrac && strings.ContainsAny(frac, ".,") { // "5.3.1", "1.5,3"
		return false
	}
	if strings.Contains(intPart, ",") {
		groups := strings.Split(intPart, ",")
		if len(groups[0]) > 3 {
			return false
		}
		for _, g := range groups[1:] {
			if len(g) != 3 {
				return false
			}
		}
	}
	return true
}

// canonNumber is R1's clean form of a valid blob: no commas, no leading zeros (but "0" and "0.5"
// stay), no trailing zeros after the point. Zeros of an integer are never trimmed: "100" is "100".
func canonNumber(blob string) string {
	blob = strings.ReplaceAll(blob, ",", "")
	intPart, frac, hasFrac := strings.Cut(blob, ".")
	intPart = strings.TrimLeft(intPart, "0")
	if intPart == "" {
		intPart = "0"
	}
	if hasFrac {
		if frac = strings.TrimRight(frac, "0"); frac != "" {
			return intPart + "." + frac
		}
	}
	return intPart
}
