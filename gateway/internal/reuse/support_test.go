package reuse

import (
	"crypto/sha256"
	"encoding/hex"
	"slices"
	"strings"
	"testing"
)

// The evidence fixtures below are VERBATIM dev-v0 corpus text: data/dev-v0/*.json rendered through
// rag/src/rag/ingest.py's product_to_text / policy_to_text, so each string is what the ingestion
// pipeline stores as that chunk's text. Where they came from, and why they are not invented prose
// (invented text tuned to clear 0.6 is "tune to make a headline work", even in a unit test), is in
// docs/work/2026-10-10-support-gate-lexical-arm/design.md, "The pinned fixture".
//
// Each carries the first 12 hex digits of its SHA-256; TestSupportFixtureChecksums enforces them,
// so an edit to a literal fails a test instead of quietly changing a score. The live check in
// ragclient (make support-check) compares the same prefixes against the text in Redis.

// sha256 82b972cc13fa -- product-headphones-01.json ("SoundMax ANC Pro")
const evidenceHeadphones01 = "Product: SoundMax ANC Pro\n" +
	"Category: headphones\n" +
	"Specs:\n" +
	"- type: over-ear\n" +
	"- anc: yes\n" +
	"- battery: 40 hours\n" +
	"- connectivity: Bluetooth 5.3, 3.5mm\n" +
	"- weight: 250g\n" +
	"- mic: yes"

// sha256 4bbdd773b369 -- product-headphones-02.json ("SoundMax ANC Lite")
const evidenceHeadphones02 = "Product: SoundMax ANC Lite\n" +
	"Category: headphones\n" +
	"Specs:\n" +
	"- type: over-ear\n" +
	"- anc: yes\n" +
	"- battery: 30 hours\n" +
	"- connectivity: Bluetooth 5.2\n" +
	"- weight: 220g\n" +
	"- mic: yes"

// sha256 c42b901cdd3b -- product-headphones-03.json ("EarBuds Pop 3")
const evidenceHeadphones03 = "Product: EarBuds Pop 3\n" +
	"Category: headphones\n" +
	"Specs:\n" +
	"- type: in-ear true wireless\n" +
	"- anc: no\n" +
	"- battery: 6 hours (24 with case)\n" +
	"- connectivity: Bluetooth 5.3\n" +
	"- weight: 5g each\n" +
	"- mic: yes"

// sha256 d9f62f2671ec -- product-headphones-04.json ("EarBuds Pop 3 Pro")
const evidenceHeadphones04 = "Product: EarBuds Pop 3 Pro\n" +
	"Category: headphones\n" +
	"Specs:\n" +
	"- type: in-ear true wireless\n" +
	"- anc: yes\n" +
	"- battery: 8 hours (32 with case)\n" +
	"- connectivity: Bluetooth 5.3\n" +
	"- weight: 6g each\n" +
	"- mic: yes\n" +
	"- water_resistance: IPX4"

// sha256 60cc39d00c83 -- product-headphones-09.json ("Conference Buds")
const evidenceHeadphones09 = "Product: Conference Buds\n" +
	"Category: headphones\n" +
	"Specs:\n" +
	"- type: in-ear true wireless\n" +
	"- anc: yes\n" +
	"- battery: 5 hours (20 with case)\n" +
	"- connectivity: Bluetooth 5.3\n" +
	"- weight: 4g each\n" +
	"- mic: dual-array noise-cancelling"

// sha256 4fc52aed4784 -- policy-returns-electronics.json (the policy body is one line in the corpus)
const evidenceReturnsElectronics = "Return Policy — Electronics (Laptops, Headphones)\n\n" +
	"Items in the laptops and headphones categories may be returned within 30 days of delivery " +
	"for a full refund, provided the item is unused, in original packaging, and all accessories " +
	"are included. Opened software licenses and consumable accessories (ear tips, cables sold " +
	"separately) are non-returnable once opened. Defective items reported within the 30-day " +
	"window are eligible for a free replacement or refund, buyer's choice. Return shipping is " +
	"free for defective items; for change-of-mind returns the customer covers return shipping."

// sha256 c776d676652d -- policy-warranty.json
const evidenceWarranty = "Warranty Terms\n\n" +
	"Laptops carry a 2-year manufacturer warranty covering hardware defects, excluding accidental " +
	"damage and battery wear below 80% capacity after 12 months. Headphones carry a 1-year " +
	"warranty covering electronic and battery defects. Kitchen appliances carry a 1-year warranty " +
	"on electrical components and a 5-year warranty on the motor for stand mixers and food " +
	"processors specifically. Furniture carries a 3-year warranty against structural defects in " +
	"materials or workmanship; fabric wear, staining, and finish fading from sunlight exposure are " +
	"not covered."

// cachedAnswer is the one AUTHORED string in this file. No answer text was ever logged for the
// 2026-09-06 case lane_test.go pins by chunk ID: item 1.4, the seam that carries chunk text, landed a
// month later. It is built only from facts the real documents above already fix (product-headphones-03's
// battery spec, policy-returns-electronics' return window) and echoes that policy's own phrasing
// ("30-day ... window", "full refund") instead of free vocabulary.
//
// So this fixture pins the FORMULA's behaviour on real evidence, not a replayed measurement of the
// 2026-09-06 case. The alternative, re-running the question through the live pipeline to capture a
// genuine answer, was not taken: it costs a green-pressure generation and inherits the Modelfile's
// temperature-1 non-determinism (super-plan.md, "Generation determinism (U8)") into a fixture that
// has to be exactly reproducible on every `go test`.
//
// sha256 b213e5a99fb4
const cachedAnswer = "The EarBuds Pop 3 has 6 hours of battery life, 24 hours with the case. " +
	"Return it within the 30-day return window for a full refund if unused and in original packaging."

// specHeavyAnswer is the second authored string, for TestSupportLexicalAdmitsASpecHeavyAnswer...:
// the same product's spec line first, then the same short return clause.
//
// sha256 43a42a1d3c1b
const specHeavyAnswer = "The EarBuds Pop 3 is in-ear true wireless with no ANC, 6 hours of battery life, " +
	"24 hours with the case, Bluetooth 5.3, 5g each. Return it within 30 days."

// The chunk IDs and orders are TestNoThetaSeparatesTheMeasuredPair's paraphrase and warranty sets
// (lane_test.go), index for index with the evidence slices below.
var (
	paraphraseChunkIDs = []string{
		"product-headphones-04#chunk-0", "product-headphones-03#chunk-0",
		"policy-returns-electronics#chunk-0", "product-headphones-09#chunk-0",
		"product-headphones-02#chunk-0",
	}
	paraphraseEvidence = []string{
		evidenceHeadphones04, evidenceHeadphones03, evidenceReturnsElectronics,
		evidenceHeadphones09, evidenceHeadphones02,
	}
	warrantyChunkIDs = []string{
		"product-headphones-04#chunk-0", "product-headphones-03#chunk-0",
		"product-headphones-09#chunk-0", "policy-warranty#chunk-0",
		"product-headphones-01#chunk-0",
	}
	warrantyEvidence = []string{
		evidenceHeadphones04, evidenceHeadphones03, evidenceHeadphones09,
		evidenceWarranty, evidenceHeadphones01,
	}
)

func sha12(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])[:12]
}

func TestSupportFixtureChecksums(t *testing.T) {
	for name, c := range map[string]struct{ text, want string }{
		"product-headphones-01":      {evidenceHeadphones01, "82b972cc13fa"},
		"product-headphones-02":      {evidenceHeadphones02, "4bbdd773b369"},
		"product-headphones-03":      {evidenceHeadphones03, "c42b901cdd3b"},
		"product-headphones-04":      {evidenceHeadphones04, "d9f62f2671ec"},
		"product-headphones-09":      {evidenceHeadphones09, "60cc39d00c83"},
		"policy-returns-electronics": {evidenceReturnsElectronics, "4fc52aed4784"},
		"policy-warranty":            {evidenceWarranty, "c776d676652d"},
		"cachedAnswer":               {cachedAnswer, "b213e5a99fb4"},
		"specHeavyAnswer":            {specHeavyAnswer, "43a42a1d3c1b"},
	} {
		if got := sha12(c.text); got != c.want {
			t.Errorf("%s: sha256 prefix %s, want %s -- the fixture literal changed", name, got, c.want)
		}
	}
}

// TestSupportLexicalSeparatesTheMeasuredPair is item 2.1's Done-when: on the pair
// TestNoThetaSeparatesTheMeasuredPair pins by chunk ID (a paraphrase and a warranty question, both
// at containment 0.80 against one cached entry), the gate admits the first and refuses the second.
// That test shows containment cannot tell them apart at any theta; this one shows that, for an answer
// whose vocabulary comes from the paraphrase's policy, the lexical score can.
//
// What it does NOT show: that the gate refuses the real 2026-09-06 warranty case. The evidence is
// real corpus text, but the cached answer is authored (see cachedAnswer), and no answer was ever
// captured for that case. The Phase 2 exit clause ("the gate refuses the measured warranty case") is
// not discharged by this fixture; the check on answers the system really generated is deferred to
// before item 2.3 (approvals.md, Recorded follow-ups).
func TestSupportLexicalSeparatesTheMeasuredPair(t *testing.T) {
	para := SupportLexical(cachedAnswer, paraphraseEvidence, paraphraseChunkIDs)
	war := SupportLexical(cachedAnswer, warrantyEvidence, warrantyChunkIDs)

	if !para.Scored || !war.Scored {
		t.Fatalf("both retrievals carry text and must be scored: paraphrase=%+v warranty=%+v", para, war)
	}
	// The denominator is the same answer both times. Pinning it catches a tokenizer change that
	// shifts every score without necessarily flipping either verdict.
	if para.ContentTokenCount != 16 || war.ContentTokenCount != 16 {
		t.Fatalf("content tokens: paraphrase=%d warranty=%d, want 16 (earbuds pop has hours battery life case return within day window full refund unused original packaging)",
			para.ContentTokenCount, war.ContentTokenCount)
	}
	if para.Score < TauSupportLexical {
		t.Errorf("paraphrase S_lex = %.4f, want >= %.2f: the gate must ADMIT the paraphrase", para.Score, TauSupportLexical)
	}
	if war.Score >= TauSupportLexical {
		t.Errorf("warranty S_lex = %.4f, want < %.2f: the gate must REFUSE the warranty question", war.Score, TauSupportLexical)
	}
	if para.Refuses() || !war.Refuses() {
		t.Errorf("Refuses(): paraphrase=%v warranty=%v, want false and true", para.Refuses(), war.Refuses())
	}
	// The exact fractions, so a margin that quietly collapses toward the threshold is visible: 14 of
	// 16 content tokens are in the returns-policy evidence, 5 of 16 in the warranty evidence.
	if para.Score != 14.0/16 || war.Score != 5.0/16 {
		t.Errorf("scores: paraphrase=%v warranty=%v, want %v and %v", para.Score, war.Score, 14.0/16, 5.0/16)
	}
}

// The next two tests assert ADMIT on a warranty question. They are a pre-registered limitation of
// the lexical arm, not regressions. They exist so the refusal above cannot be mistaken for a property
// of "the warranty case" in general. It holds only because the two evidence sets differ in WHICH
// POLICY they carry and the answer's non-discriminating (product-spec) tokens stay a minority of its
// denominator. design.md, "Disclosed fragility, not hidden".
//
// They are NOT instances of RQ2a (Final_Proposal.md RQ2a, super-plan.md item 6.4), which is defined
// as the query and the entry retrieving the SAME evidence and differing only in the condition asked
// about. Here the evidence differs from the entry's, so these are false hits the gate lets through in
// its OWN domain ("the wrong document"), and in a run they would count INSIDE the headline false-hit
// rate, not beside it. They bound how often the lexical arm can catch the wrong document.

// TestSupportLexicalAdmitsWhenBothPoliciesRetrieved: a retrieval that carries the warranty policy AND
// the returns policy, so the old evidence rides along and the score recovers. This is a constructed
// union, not an observed retrieval: lane.go documents only that a RETURN query retrieves both
// category return policies, and nothing in this repo shows a warranty query retrieving the returns
// policy.
func TestSupportLexicalAdmitsWhenBothPoliciesRetrieved(t *testing.T) {
	texts := append(slices.Clone(warrantyEvidence), evidenceReturnsElectronics)
	ids := append(slices.Clone(warrantyChunkIDs), "policy-returns-electronics#chunk-0")
	v := SupportLexical(cachedAnswer, texts, ids)
	if !v.Scored || v.Score < TauSupportLexical {
		t.Fatalf("both policies retrieved: %+v, want Scored and S_lex >= %.2f (the gate admits; documented limitation)", v, TauSupportLexical)
	}
}

// TestSupportLexicalAdmitsASpecHeavyAnswerAgainstWarrantyEvidence: the same warranty evidence that
// refused cachedAnswer admits an answer whose wording leads with the product's spec line, because
// those tokens are in every product chunk and so in the warranty retrieval too. The same false hit
// the gate exists to refuse, reproduced by changing only the answer's wording. specHeavyAnswer is
// authored, like cachedAnswer. Note it is a different cached answer from cachedAnswer, so this is not
// the same-entry, same-evidence pair RQ2a defines.
func TestSupportLexicalAdmitsASpecHeavyAnswerAgainstWarrantyEvidence(t *testing.T) {
	v := SupportLexical(specHeavyAnswer, warrantyEvidence, warrantyChunkIDs)
	if !v.Scored || v.Score < TauSupportLexical {
		t.Fatalf("spec-heavy answer vs warranty evidence: %+v, want Scored and S_lex >= %.2f (the gate admits; documented limitation)", v, TauSupportLexical)
	}
	// Same answer against the paraphrase evidence is also admitted, so the admit is not an accident
	// of the warranty set.
	if p := SupportLexical(specHeavyAnswer, paraphraseEvidence, paraphraseChunkIDs); p.Score < v.Score {
		t.Errorf("spec-heavy answer scored lower on the paraphrase evidence (%v) than on the warranty evidence (%v)", p.Score, v.Score)
	}
}

// The three states of SupportVerdict.Scored. These use short literals, not the corpus text: they
// exercise the signature's contract, not the measured case.

func TestSupportLexicalStaleServerIsNotScored(t *testing.T) {
	// Chunk IDs but no text: a pre-1.4 rag.server. This must be neither a score nor a refusal.
	for name, texts := range map[string][]string{"nil": nil, "empty non-nil": {}} {
		v := SupportLexical("battery life of the earbuds", texts, []string{"product-headphones-03#chunk-0"})
		if v != (SupportVerdict{}) {
			t.Errorf("%s texts with chunk IDs: %+v, want the zero SupportVerdict (Scored false)", name, v)
		}
	}
}

// TestSupportVerdictRefuses pins the one sanctioned way to turn a verdict into a refusal. The row that
// matters is the unscored one: Score 0 is below TauSupportLexical, and reading Score alone would
// call a stale server a SUPPORT refusal.
func TestSupportVerdictRefuses(t *testing.T) {
	for _, c := range []struct {
		name string
		v    SupportVerdict
		want bool
	}{
		{"zero value (unscored)", SupportVerdict{}, false},
		{"unscored with a stray low score", SupportVerdict{Scored: false, Score: 0.1}, false},
		{"scored below tau", SupportVerdict{Scored: true, Score: 0.5, ContentTokenCount: 4}, true},
		{"scored exactly at tau admits", SupportVerdict{Scored: true, Score: TauSupportLexical, ContentTokenCount: 5}, false},
		{"scored above tau", SupportVerdict{Scored: true, Score: 0.9, ContentTokenCount: 10}, false},
		{"scored zero (empty retrieval)", SupportVerdict{Scored: true, Score: 0}, true},
	} {
		if got := c.v.Refuses(); got != c.want {
			t.Errorf("%s: Refuses() = %v, want %v", c.name, got, c.want)
		}
	}
	// End to end for the stale-server case: the verdict SupportLexical returns must not refuse.
	if SupportLexical("battery life of the earbuds", nil, []string{"x#chunk-0"}).Refuses() {
		t.Error("a stale-server retrieval (chunk IDs, no texts) must not be refused as SUPPORT")
	}
}

func TestSupportLexicalEmptyRetrievalScoresZero(t *testing.T) {
	// No chunks AND no text: a legitimately empty retrieval. A real verdict (nothing supports
	// anything), not a missing instrument.
	for name, ids := range map[string][]string{"nil": nil, "empty non-nil": {}} {
		v := SupportLexical("battery life of the earbuds", nil, ids)
		if !v.Scored || v.Score != 0 || v.ContentTokenCount != 3 {
			t.Errorf("%s chunk IDs: %+v, want Scored, Score 0, ContentTokenCount 3 (battery life earbuds)", name, v)
		}
	}
}

func TestSupportLexicalAnswerWithNoContentTokens(t *testing.T) {
	// Only stopwords and short tokens: nothing to support. Scored with 0, not a division by zero.
	v := SupportLexical("a is of it", []string{"anything at all"}, []string{"x#chunk-0"})
	if !v.Scored || v.Score != 0 || v.ContentTokenCount != 0 {
		t.Errorf("answer with no content tokens: %+v, want Scored, Score 0, ContentTokenCount 0", v)
	}
	if v := SupportLexical("", nil, nil); !v.Scored || v.Score != 0 {
		t.Errorf("empty answer, empty retrieval: %+v, want Scored with Score 0", v)
	}
}

// The tokenizer is part of S_lex's frozen definition (approvals.md): these pin what it does.
func TestContentTokensRules(t *testing.T) {
	// Dropped: "the" (stopword); "30", "na", "ve", "5g" (under three characters). "naïve" splits at
	// the non-ASCII letter, which is a separator. Kept: "30-day" splits at the hyphen, so "day"
	// survives; case folds; no stemming, so return/returns/returned stay three tokens.
	got := contentTokens("The 30-day RETURN window; returns, returned. IPX4 (24h) naïve 5g")
	want := []string{"24h", "day", "ipx4", "return", "returned", "returns", "window"}
	keys := make([]string, 0, len(got))
	for k := range got {
		keys = append(keys, k)
	}
	slices.Sort(keys)
	if !slices.Equal(keys, want) {
		t.Errorf("contentTokens = %v, want %v", keys, want)
	}

	// Apostrophes and underscores are separators, not word characters: the corpus has "buyer's" and
	// "water_resistance". "s" is under three characters, so only "buyer" survives from the first.
	// The earlier case does not cover these, and a change here would move scores on real evidence.
	for _, c := range []struct {
		in   string
		want []string
	}{
		{"buyer's choice", []string{"buyer", "choice"}},
		{"water_resistance: IPX4", []string{"ipx4", "resistance", "water"}},
	} {
		got := contentTokens(c.in)
		keys := make([]string, 0, len(got))
		for k := range got {
			keys = append(keys, k)
		}
		slices.Sort(keys)
		if !slices.Equal(keys, c.want) {
			t.Errorf("contentTokens(%q) = %v, want %v", c.in, keys, c.want)
		}
	}
}

func TestSupportLexicalIsSetNotMultiset(t *testing.T) {
	// Repeating a word in the answer must not move the denominator.
	once := SupportLexical("refund policy", []string{"refund"}, []string{"x#chunk-0"})
	many := SupportLexical("refund refund refund policy policy", []string{"refund"}, []string{"x#chunk-0"})
	if once != many || once.Score != 0.5 || once.ContentTokenCount != 2 {
		t.Errorf("repeats changed the verdict: once=%+v many=%+v, want both {Scored Score 0.5 ContentTokenCount 2}", once, many)
	}
}

func TestSupportLexicalEvidenceIsTheUnionOfChunks(t *testing.T) {
	// One answer token per chunk: neither chunk alone supports it, the union does.
	ids := []string{"a#chunk-0", "b#chunk-0"}
	v := SupportLexical("battery warranty", []string{"the battery", "a warranty"}, ids)
	if v.Score != 1 {
		t.Errorf("union of chunks: %+v, want Score 1", v)
	}
	// Chunks are joined with a separator, so a word cannot be fused across a chunk boundary.
	v = SupportLexical("batterywarranty", []string{"battery", "warranty"}, ids)
	if v.Score != 0 {
		t.Errorf("fused word across chunks was supported: %+v", v)
	}
}

// TestSupportStopwordsArePinned fails on any edit to the list. The list is part of S_lex's
// definition while TauSupportLexical cannot move to compensate, so a change must be a decision
// (a numbered decisions.md entry, per approvals.md), not a drive-by. If you are here because this
// failed after an intentional edit: that edit invalidates every support_lex logged before it.
func TestSupportStopwordsArePinned(t *testing.T) {
	const wantCount = 33 // Lucene StopAnalyzer.ENGLISH_STOP_WORDS_SET
	const wantSHA256 = "0b8e898f5a7ba5282a7c4da3452a423d50cc6197d520886cd1753dd64e143d38"
	words := make([]string, 0, len(supportStopwords))
	for w := range supportStopwords {
		words = append(words, w)
	}
	slices.Sort(words)
	if len(words) != wantCount {
		t.Fatalf("supportStopwords has %d words, want %d", len(words), wantCount)
	}
	sum := sha256.Sum256([]byte(strings.Join(words, ",")))
	if got := hex.EncodeToString(sum[:]); got != wantSHA256 {
		t.Errorf("supportStopwords sha256 = %s, want %s", got, wantSHA256)
	}
	// "has" and "within" are deliberately NOT stopwords: they are content tokens of cachedAnswer,
	// and the 16-token denominator above depends on it.
	for _, w := range []string{"has", "within"} {
		if _, ok := supportStopwords[w]; ok {
			t.Errorf("%q must not be a stopword", w)
		}
	}
}

// BenchmarkSupportLexical turns Final_Proposal.md's "microseconds" claim for the gate from reasoned
// into measured, on a representative evidence set (~600 bytes of policy plus four product chunks).
func BenchmarkSupportLexical(b *testing.B) {
	b.ReportAllocs()
	for b.Loop() {
		if v := SupportLexical(cachedAnswer, paraphraseEvidence, paraphraseChunkIDs); !v.Scored {
			b.Fatal("not scored")
		}
	}
}
