package reuse

import (
	"fmt"
	"strconv"
	"strings"
	"testing"
	"unicode"
)

// Tests for the numeric arm (super-plan.md item 2.2). Rules and the reasons for them:
// docs/work/2026-10-14-numeric-arm/ (design.md R1-R9, and approvals.md "Frozen artefact").
//
// Every expected value below was worked out by hand from those rules BEFORE the code existed. If a
// row fails, find out whether the code or the hand-worked value is wrong. Do not edit a fixture, or a
// row, only to make it pass.
//
// The pinned dev-v0 fixtures (evidence*, cachedAnswer, specHeavyAnswer, paraphrase*/warranty*) are
// declared in support_test.go and reused here unchanged.

// readingString renders a reading on one line: "30/day" is a number with a unit, "5.3" a number
// without one, "#ipx7" a code, "!2" two unreadable spans.
func readingString(r numReading) string {
	parts := make([]string, 0, len(r.items)+1)
	for _, it := range r.items {
		switch {
		case it.code:
			parts = append(parts, "#"+it.value)
		case it.unit == "":
			parts = append(parts, it.value)
		default:
			parts = append(parts, it.value+"/"+it.unit)
		}
	}
	if r.unreadable > 0 {
		parts = append(parts, "!"+strconv.Itoa(r.unreadable))
	}
	return strings.Join(parts, " ")
}

func fakeIDs(n int) []string {
	ids := make([]string, n)
	for i := range ids {
		ids[i] = fmt.Sprintf("chunk-%d#chunk-0", i)
	}
	return ids
}

// numericHardCase is a third authored string. It exists to pin the reader on forms the dev-v0
// fixtures do not contain: ranges, thousands groups, a spaced unit, two kinds of code, a slash, a
// fraction character, number words, a currency prefix and a spaced percent sign.
//
// sha256 is pinned in TestNumericFixtureChecksums.
const numericHardCase = "Ships in 2-5 days; 1,500 units; 5.30 V, IPX7, v5.3, 24/7. Step 1: ½ off. " +
	"Twenty-four hours, one year, two ways, hundred days. $49.99 or 80 %."

func TestNumericFixtureChecksums(t *testing.T) {
	if got, want := sha12(numericHardCase), "4e858a49979c"; got != want {
		t.Errorf("numericHardCase: sha256 prefix %s, want %s -- the literal changed", got, want)
	}
}

// TestNumericReaderGolden pins the reader's exact output on every pinned string. A change to a rule
// these strings use moves at least one line here. Rules they do not use (list marker, leading point,
// tab and line-break handling, the plural cut, letter case) are pinned one by one in
// TestNumericReaderRules. Together they make the grammar a frozen definition instead of a habit: a
// verdict test alone cannot see most grammar edits, because every fixture verdict turns on one
// fact, "is 30 in the evidence".
func TestNumericReaderGolden(t *testing.T) {
	for _, c := range []struct{ name, text, want string }{
		{"headphones-01", evidenceHeadphones01, "40/hour 5.3 3.5/mm 250/g"},
		{"headphones-02", evidenceHeadphones02, "30/hour 5.2 220/g"},
		{"headphones-03", evidenceHeadphones03, "3 6/hour 24 5.3 5/g"},
		{"headphones-04", evidenceHeadphones04, "3 8/hour 32 5.3 6/g #ipx4"},
		{"headphones-09", evidenceHeadphones09, "5/hour 20 5.3 4/g"},
		{"returns", evidenceReturnsElectronics, "30/day"},
		{"warranty", evidenceWarranty, "2/year 80/percent 12/month 1/year 5/year 3/year"},
		{"cachedAnswer", cachedAnswer, "3 6/hour 24/hour 30/day"},
		{"specHeavyAnswer", specHeavyAnswer, "3 6/hour 24/hour 5.3 5/g 30/day"},
		{"hardCase", numericHardCase,
			"2 5/day 1500 5.3/v #ipx7 #v5.3 24 7 1 24/hour 1/year 49.99/$ 80/percent !2"},
	} {
		if got := readingString(readNumbers(c.text)); got != c.want {
			t.Errorf("%s:\n got  %q\n want %q", c.name, got, c.want)
		}
	}
}

// R1: the clean form of a number. "50" must not collapse to "5" and "100" must not collapse to
// "1" (a mutant that trims zeros on integers).
func TestNumericNormalisation(t *testing.T) {
	for in, want := range map[string]string{
		"50": "50", "5": "5", "100": "100", "1": "1", "0": "0", "0.5": "0.5", "0.50": "0.5",
		"5.30": "5.3", "5.0": "5", "1,500": "1500", "007": "7", "12,345,678": "12345678", "10.05": "10.05",
	} {
		if got := canonNumber(in); got != want {
			t.Errorf("canonNumber(%q) = %q, want %q", in, got, want)
		}
	}
}

// The reader on small inputs, one rule at a time. Each row names the rule it guards.
func TestNumericReaderRules(t *testing.T) {
	for _, c := range []struct{ rule, text, want string }{
		// R5 unit forms: glued, spaced, hyphenated, plural, singular, aliases.
		{"R5 hyphen", "30-day", "30/day"},
		{"R5 plural", "30 days", "30/day"},
		{"R5 singular", "30 day", "30/day"},
		{"R5 glued word", "30days", "30/day"},
		{"R5 glued symbol unit", "250g", "250/g"},
		{"R5 spaced short unit", "250 g", "250/g"},
		{"R5 decimal glued", "3.5mm", "3.5/mm"},
		{"R5 percent glued", "80%", "80/percent"},
		{"R5 percent spaced", "80 %", "80/percent"},
		{"R5 percent word", "80 percent", "80/percent"},
		{"R6 alias hrs", "6 hrs", "6/hour"},
		{"R6 alias watts", "5 watts", "5/w"},
		{"R6 alias volts", "12 volts", "12/v"},
		{"R6 alias grams", "5 grams", "5/g"},
		{"R6 alias feet", "6 feet", "6/ft"},
		{"R6 liter", "2 liters", "2/litre"},
		{"R6 vs is not a plural", "Bluetooth 5.2 vs 5.3", "5.2 5.3"},
		{"R5 currency prefix", "$49.99", "49.99/$"},
		{"R5 currency euro", "€5", "5/€"},
		{"R5 not a unit", "Pop 3 has", "3"},
		{"R5 word between number and unit (D2)", "30 calendar days", "30"},
		// R4 punctuation, list markers, ranges, dates.
		{"R4 full stop", "within 30 days.", "30/day"},
		{"R4 bare number then full stop", "It costs 5.", "5"},
		{"R4 comma then space", "5, 6", "5 6"},
		{"R4 list marker dot", "1. Return within 30 days\n2) Refund", "30/day"},
		{"R4 indented list marker", "  3. indented", ""},
		{"R4 decimal is not a marker", "1.5 hours", "1.5/hour"},
		{"R5 range", "5-7 days", "5 7/day"},
		{"date", "2026-10-14", "2026 10 14"},
		{"time", "10:30", "10 30"},
		{"items are a set", "30 days and 30 days", "30/day"},
		// R3 codes.
		{"R3 code", "IPX7", "#ipx7"},
		{"R3 version tail", "v5.3", "#v5.3"},
		{"R3 ordinal", "the 3rd day", "#3rd"},
		{"R3 4K", "a 4K screen", "#4k"},
		{"R3 24x7", "24x7", "#24x7"},
		{"R3 model", "WH-1000XM5", "#1000xm5"},
		// R2 unreadable.
		{"R2 comma decimal", "1,5 days", "!1"},
		{"R2 bad group", "1,2345", "!1"},
		{"R2 two points", "5.3.1", "!1"},
		{"R2 fraction char", "½ year", "!1"},
		{"R2 arabic digit", "٣ days", "!1"},
		{"R2 superscript", "m²", "!1"},
		{"R2 leading point", ".5 hours", "!1"},
		{"R2 run counts once", "٣٤ days", "!1"},
		// R7 number words.
		{"R7 two years", "two years", "2/year"},
		{"R7 one-year", "one-year warranty", "1/year"},
		{"R7 twelve months", "twelve months", "12/month"},
		{"R7 fourteen days", "fourteen days", "14/day"},
		{"R7 thirty days", "thirty days", "30/day"},
		{"R7 compound hyphen", "twenty-four hours", "24/hour"},
		{"R7 compound space", "twenty four hours", "24/hour"},
		{"R7 one of is not a number", "one of the options", ""},
		{"R7 two ways is not a number", "two ways to return it", ""},
		{"R7 hundred before a unit is unreadable", "hundred days", "!1"},
		{"R7 half before a unit is unreadable", "half years", "!1"},
		{"R7 a year is not read (known gap)", "a year", ""},
		{"R7 compound without a unit is not read", "twenty four items", ""},
		// Rows added after /ai-review: each pins a rule that no earlier row pinned.
		{"R3 digit-first code keeps its tail", "12x1.5mm", "#12x1.5"},
		{"R3 letter-first code keeps its tail", "M12x1.5mm", "#m12x1.5"},
		{"R3 4K code keeps its tail", "4K.5", "#4k.5"},
		{"R5 no unit across a line break", "30\ndays", "30"},
		{"R5 percent not across a line break", "80\n%", "80"},
		{"R5 tab between number and unit", "30\tdays", "30/day"},
		{"R5 glued unit is lowercased (V)", "12V", "12/v"},
		{"R5 glued unit is lowercased (G)", "250G", "250/g"},
		{"R6 plural cut: lbs", "5 lbs", "5/lb"},
		{"R6 plural cut: kgs", "5 kgs", "5/kg"},
		{"R6 plural cut: ozs", "5 ozs", "5/oz"},
		{"R6 plural cut: gs is not a plural of g", "5 gs", "5"},
		{"R4 tab-indented list marker", "\t3. indented", ""},
		{"R4 decimal at line start is a number, not a marker", "5.3. Bluetooth", "5.3"},
		{"R2 point after a space is a leading point", "see .5 hours", "!1"},
		{"R2 point glued to a word is not a leading point", "item.5 hours", "5/hour"},
		{"R1 first group over 3 digits is unreadable", "1234,567", "!1"},
		{"R7 ones word is lowercased", "twenty-Four hours", "24/hour"},
		{"R7 tens + teen is not a compound", "twenty-fourteen hours", "14/hour"},
		{"R7 tens + zero is not a compound", "twenty-zero hours", "0/hour"},
		{"R7 hundred without a unit is ignored", "a hundred people", ""},
		// Separators (decided after /ai-review, before any run logged the field). Accepted: a space,
		// a tab, U+00A0, U+202F; a hyphen, U+2011. Nothing else.
		{"R5 no-break space before the unit", "30\u00a0days", "30/day"},
		{"R5 narrow no-break space before the unit", "30\u202fdays", "30/day"},
		{"R5 non-breaking hyphen before the unit", "30\u2011day", "30/day"},
		{"R5 no-break space before percent", "80\u00a0%", "80/percent"},
		{"R5 several spaces before the unit", "30   days", "30/day"},
		{"R7 number word, no-break space, unit", "two\u00a0years", "2/year"},
		{"R7 compound with two spaces", "twenty  four hours", "24/hour"},
		{"R7 compound with a no-break space", "twenty\u00a0four hours", "24/hour"},
		{"R7 compound with a non-breaking hyphen", "twenty\u2011four hours", "24/hour"},
		{"R7 compound not across a line break", "twenty\nfour hours", "4/hour"},
		// Refused on purpose: a known gap, pinned so that widening the set is a decision. The answer
		// is read by value only.
		{"R5 en dash is not a hyphen (known gap)", "30\u2013day", "30"},
		{"R5 U+2010 is not a hyphen (known gap)", "30\u2010day", "30"},
		{"R5 thin space is not a space (known gap)", "30\u2009days", "30"},
	} {
		if got := readingString(readNumbers(c.text)); got != c.want {
			t.Errorf("%s: readNumbers(%q) = %q, want %q", c.rule, c.text, got, c.want)
		}
	}
}

// R2 pins which characters count as numbers: the tables come from the Go toolchain's Unicode
// version, so the characters are named here. If a toolchain update changes the answer for one of
// them, this fails instead of the arm's meaning changing silently (design.md U4).
func TestNumericUnicodeNumbers(t *testing.T) {
	for _, r := range "½²٣⁵①Ⅷ" {
		if !unicode.IsNumber(r) {
			t.Errorf("%q: unicode.IsNumber = false in this toolchain; R2 relies on it", r)
		}
		if got := readingString(readNumbers("x " + string(r) + " y")); got != "!1" {
			t.Errorf("%q alone: got %q, want one unreadable span", r, got)
		}
	}
	for _, r := range "é—·ß" {
		if got := readingString(readNumbers("x " + string(r) + " y")); got != "" {
			t.Errorf("%q is not a number: got %q, want nothing", r, got)
		}
	}
}

// Evidence side (R9): unreadable spans in evidence are ignored, and only units attached to a
// number count as the chunk's units.
func TestNumericEvidenceIsReadWithTheSameReader(t *testing.T) {
	// "m²" and "½" in the evidence must not make the chunk refuse everything.
	v := SupportNumeric("It is 30 days.", []string{"Area 12 m² and ½ off. Returns: 30 days."}, fakeIDs(1))
	if !v.Admits() {
		t.Errorf("unreadable spans in evidence must be ignored: %+v", v)
	}
	// "hours" is a word of the chunk, but not attached to a number: it is not one of its units.
	v = SupportNumeric("It lasts 30 hours.", []string{"The 30 sheets last for hours and hours."}, fakeIDs(1))
	if !v.Refuses() {
		t.Errorf("a unit word that is not attached to a number must not count: %+v", v)
	}
}

func TestNumericDoneWhen(t *testing.T) {
	ans := "Our return window is the 30-day return period."
	only14 := []string{"The return window is a 14-day period for all items."}
	if v := SupportNumeric(ans, only14, fakeIDs(1)); !v.Refuses() || v.Unsupported != 1 {
		t.Errorf("a cached 30-day answer against evidence with only 14-day must be refused: %+v", v)
	}
	// Positive control: the same answer against evidence that does carry 30 days is admitted, so the
	// refusal above is about the number and not about anything else in the sentence.
	has30 := []string{"The return window is a 30-day period for all items."}
	if v := SupportNumeric(ans, has30, fakeIDs(1)); !v.Admits() {
		t.Errorf("positive control: 30-day against 30-day must be admitted: %+v", v)
	}
}

func TestNumericUnreadableBlocks(t *testing.T) {
	ev := []string{"Returns within 30 days. Battery 6 hours."}
	for _, ans := range []string{"about 1,5 days", "it lasts ½ a year", "it lasts ٣ days", "weighs 5.3.1 g", "is 12 m² wide"} {
		v := SupportNumeric(ans, ev, fakeIDs(1))
		if !v.Refuses() || v.Unreadable != 1 {
			t.Errorf("%q: an unreadable number must block: %+v", ans, v)
		}
	}
	// The same answers with the number removed are not blocked, so the block is the number's doing.
	if v := SupportNumeric("it lasts a long time", ev, fakeIDs(1)); !v.Admits() {
		t.Errorf("positive control: an answer with no numbers must be admitted: %+v", v)
	}
}

func TestNumericStaleServerAndEmptyRetrieval(t *testing.T) {
	// A pre-1.4 server: chunk IDs but no texts. Not scored, not a refusal (same rule as SupportLexical).
	v := SupportNumeric("It is 30 days.", nil, fakeIDs(3))
	if v.Scored || v.Refuses() || v.Admits() {
		t.Errorf("stale server must be unscored, neither refused nor admitted: %+v", v)
	}
	// An empty retrieval has no special case (review.md finding 5): an answer with a number is
	// refused because the number is unsupported, an answer without numbers is admitted. The
	// zero-chunk hole is closed in the cascade by item 2.3, not here.
	v = SupportNumeric("It is 30 days.", nil, nil)
	if !v.Scored || !v.Refuses() || v.Unsupported != 1 {
		t.Errorf("empty retrieval, answer with a number: %+v", v)
	}
	v = SupportNumeric("Ask the store.", nil, nil)
	if !v.Scored || !v.Admits() {
		t.Errorf("empty retrieval, answer with no numbers: %+v", v)
	}
}

// The measured pair (design.md "What I expect"). The fixtures decide only one fact: whether 30 is
// in the evidence. Everything else in the verdict is the same on both sides.
func TestNumericMeasuredPair(t *testing.T) {
	for _, c := range []struct {
		name              string
		answer            string
		evidence          []string
		ids               []string
		refuse            bool
		numbers, unitless int
	}{
		{"cachedAnswer/paraphrase", cachedAnswer, paraphraseEvidence, paraphraseChunkIDs, false, 4, 1},
		{"cachedAnswer/warranty", cachedAnswer, warrantyEvidence, warrantyChunkIDs, true, 4, 1},
		{"specHeavy/paraphrase", specHeavyAnswer, paraphraseEvidence, paraphraseChunkIDs, false, 6, 2},
		{"specHeavy/warranty", specHeavyAnswer, warrantyEvidence, warrantyChunkIDs, true, 6, 2},
	} {
		v := SupportNumeric(c.answer, c.evidence, c.ids)
		if !v.Scored || v.Refuses() != c.refuse || v.Admits() == c.refuse {
			t.Errorf("%s: refuse=%v want %v: %+v", c.name, v.Refuses(), c.refuse, v)
		}
		if v.Numbers != c.numbers || v.Unitless != c.unitless || v.Unreadable != 0 {
			t.Errorf("%s: counts %+v, want Numbers=%d Unitless=%d Unreadable=0", c.name, v, c.numbers, c.unitless)
		}
		wantUnsupported := 0
		if c.refuse {
			wantUnsupported = 1 // the 30-day return window, and nothing else
		}
		if v.Unsupported != wantUnsupported {
			t.Errorf("%s: Unsupported = %d, want %d", c.name, v.Unsupported, wantUnsupported)
		}
	}
}

// Rows that tell the grammar's rules apart. Each row would stay green under the mutant named in
// the last column if it were not here (review.md finding 1). Run by hand in plan step 7.
func TestNumericSeparatesGrammarEdits(t *testing.T) {
	for _, c := range []struct {
		name     string
		answer   string
		evidence []string
		refuse   bool
		guards   string
	}{
		{"unit check", "It lasts 30 days.", []string{evidenceHeadphones02}, true,
			"dropping the unit check: h02 has 30 but only with hours"},
		{"per chunk", "It lasts 30 days.", []string{"Battery 30 hours.", "Window 14 days."}, true,
			"joining the chunks: 30 and days are in different chunks"},
		{"hyphen", "The 30-day window.", []string{"Battery 30 hours."}, true,
			"dropping the hyphen rule: 30-day would become a bare 30, which 30 hours supports"},
		{"plural", "The 30 days window.", []string{"Battery 30 hours."}, true,
			"dropping plural stripping: days would not be a unit, so only 30 would be checked"},
		{"hyphen and plural, positive control", "The 30-day window.", []string{"within 30 days"}, false,
			"positive control for the two rows above"},
		{"decimal is one number", "Bluetooth 3.5", []string{evidenceHeadphones03}, true,
			"splitting 3.5 into 3 and 5: h03 has both"},
		{"code must match", "It has an IPX7 rating.", []string{evidenceHeadphones04}, true,
			"ignoring codes"},
		{"code present", "It has an IPX4 rating.", []string{evidenceHeadphones04}, false,
			"positive control for the row above"},
		{"number word value", "Lasts twenty-four hours.", []string{evidenceHeadphones09}, true,
			"reading twenty-four as 20 and 4: h09 has both"},
		{"number word present", "Lasts twenty-four hours.", []string{evidenceHeadphones03}, false,
			"positive control: h03 has 24 and hours"},
		{"fourteen days", "Return within fourteen days.", []string{evidenceReturnsElectronics}, true,
			"skipping teen words"},
		{"integer zeros", "It lasts 3 hours.", []string{"It lasts 30 hours."}, true,
			"trimming zeros of integers: 30 would become 3"},
		{"integer zeros 100", "It lasts 1 hour.", []string{"It lasts 100 hours."}, true,
			"same, for 100"},
		{"trailing decimal zeros", "It weighs 5.30 g.", []string{"It weighs 5.3 g."}, false,
			"not cleaning 5.30 to 5.3"},
		{"vs is not a unit", "Bluetooth 5.2 vs 5.3", []string{"Bluetooth 5.2 and 5.3"}, false,
			"reading vs as the unit v"},
		{"D2 gap: a word between number and unit", "Within 30 calendar days.",
			[]string{evidenceHeadphones02, evidenceWarranty}, false,
			"pins the accepted gap: value only, so 30 hours supports 30 calendar days"},
		{"D1 weakness: right number, wrong unit, same chunk", "A 12-year warranty.",
			[]string{evidenceWarranty}, false,
			"pins the accepted weakness of option C: 12 months and 2-year are in one chunk"},
		{"no numbers", "Ask the store.", []string{evidenceWarranty}, false, "positive control"},
	} {
		v := SupportNumeric(c.answer, c.evidence, fakeIDs(len(c.evidence)))
		if v.Refuses() != c.refuse {
			t.Errorf("%s: refuse=%v, want %v (guards against: %s): %+v", c.name, v.Refuses(), c.refuse, c.guards, v)
		}
	}
	// The D2 gap is counted, so the real-answer sample can measure it.
	if v := SupportNumeric("Within 30 calendar days.", []string{evidenceHeadphones02}, fakeIDs(1)); v.Unitless != 1 {
		t.Errorf("a number checked by value only must be counted in Unitless: %+v", v)
	}
}

// The vocabulary is part of the definition. Changing one entry must turn a test red.
func TestNumericUnitListPinned(t *testing.T) {
	wantUnits := strings.Fields("second minute hour day week month year g kg mg lb oz mm cm km inch ft " +
		"ml litre w kw v mah wh hz khz mhz ghz kb mb gb tb db rpm percent")
	if len(numUnits) != len(wantUnits) {
		t.Errorf("unit list has %d entries, want %d", len(numUnits), len(wantUnits))
	}
	for _, u := range wantUnits {
		if _, ok := numUnits[u]; !ok {
			t.Errorf("unit %q is missing from the list", u)
		}
	}
	wantAlias := map[string]string{
		"sec": "second", "min": "minute", "hr": "hour", "hrs": "hour", "yr": "year", "yrs": "year",
		"inches": "inch", "gram": "g", "kilogram": "kg", "pound": "lb", "foot": "ft", "feet": "ft",
		"liter": "litre", "watt": "w", "volt": "v",
	}
	if len(numUnitAlias) != len(wantAlias) {
		t.Errorf("alias list has %d entries, want %d", len(numUnitAlias), len(wantAlias))
	}
	for a, u := range wantAlias {
		if numUnitAlias[a] != u {
			t.Errorf("alias %q = %q, want %q", a, numUnitAlias[a], u)
		}
	}
	if numCurrency != "$€£" {
		t.Errorf("currency symbols = %q, want %q", numCurrency, "$€£")
	}
}

func TestNumericNumberWordsPinned(t *testing.T) {
	want := map[string]int{
		"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
		"eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
		"fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
		"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
		"eighty": 80, "ninety": 90,
	}
	if len(numWords) != len(want) {
		t.Errorf("number-word table has %d entries, want %d", len(numWords), len(want))
	}
	for w, v := range want {
		if numWords[w] != v {
			t.Errorf("number word %q = %d, want %d", w, numWords[w], v)
		}
	}
	for w := range strings.FieldsSeq("hundred thousand million half dozen couple") {
		if _, ok := numWordsBlocked[w]; !ok {
			t.Errorf("%q must be in the unreadable number-word list", w)
		}
	}
	if len(numWordsBlocked) != 6 {
		t.Errorf("unreadable number-word list has %d entries, want 6", len(numWordsBlocked))
	}
}

// FuzzReadNumbers: no input may panic or hang the reader, and any text read against itself as
// evidence must be fully supported (every item it holds has its own value and unit in that chunk).
// `go test` runs the seeds; `go test -fuzz FuzzReadNumbers ./internal/reuse` explores. A panic here
// would be a panic on the hit path.
func FuzzReadNumbers(f *testing.F) {
	for _, s := range []string{
		"", "-", "%", "5", "5-", "5%", "twenty-", "twenty -", "one-", "hundred", "hundred ", ".", "..5",
		"1,", "1,5", "5.", "$", "€", "€5", "£", "1.", "1)", "1. ", "\n1. x", "٣", "½", "3½", "m²",
		"\xff", "5\xff", "IPX", "v5.", "v5.3.", "24x", "12x1.5mm", "3 ", "3\t-day", "twenty four",
		"twenty  four hours", "30\u00a0days", "30\u2011day", "twenty\u202ffour\u2011hours", "80\u00a0%",
		"\u00a0", "5\u00a0", "5\u2011", "\u2011", cachedAnswer, specHeavyAnswer, numericHardCase, evidenceHeadphones03,
		evidenceWarranty,
	} {
		f.Add(s)
	}
	f.Fuzz(func(t *testing.T, s string) {
		r := readNumbers(s)
		if readingString(r) != readingString(readNumbers(s)) {
			t.Fatalf("not deterministic: %q", s)
		}
		v := SupportNumeric(s, []string{s}, []string{"c#0"})
		if !v.Scored || v.Unsupported != 0 {
			t.Fatalf("text read against itself must be fully supported: %q -> %+v", s, v)
		}
		if v.Numbers != len(r.items) || v.Unreadable != r.unreadable {
			t.Fatalf("counts disagree with the reading: %q -> %+v vs %+v", s, v, r)
		}
		for _, it := range r.items {
			if it.value == "" {
				t.Fatalf("empty value: %q -> %+v", s, it)
			}
		}
	})
}

func BenchmarkSupportNumeric(b *testing.B) {
	b.ReportAllocs()
	for b.Loop() {
		if v := SupportNumeric(cachedAnswer, paraphraseEvidence, paraphraseChunkIDs); !v.Scored {
			b.Fatal("not scored")
		}
	}
}
