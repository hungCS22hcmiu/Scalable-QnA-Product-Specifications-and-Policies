package reuse

import "strings"

// The lexical arm of the answer-evidence support gate (super-plan.md item 2.1), computed in Go as
// token arithmetic. Same constraint as rule.go: standard library only, no I/O, so the gate can be
// falsified in isolation (docs/architecture.md 2). Design: docs/work/2026-10-10-support-gate-lexical-arm/.
//
// Called from the cascade since item 2.3, through CheckSupport and Thresholds.Judge (cause.go), which
// also own the refusal cause. The gate has an on/off switch since item 2.4 (gate.go): with the gate off,
// Judge returns before it reaches this file's code, so a candidate is never scored.

// TauSupportLexical is the lexical gate's threshold, pinned at the value GroundedCache published and
// never swept (decisions.md, inherited frozen values). It is a constant, not a Thresholds field:
// Thresholds' fields are "swept, never hand-set", and a field here would invite an environment
// override that makes a never-swept value sweepable.
const TauSupportLexical = 0.6

// supportStopwords is Lucene's StopAnalyzer.ENGLISH_STOP_WORDS_SET, 33 words, transcribed verbatim
// and not imported (reuse/ takes no dependencies).
//
// It is part of S_lex's definition exactly as much as TauSupportLexical is, and TauSupportLexical
// cannot move to compensate for an edit here. Once the first run on v1 has logged support_lex (ADR-009
// reads "the first logged run" as a run on v1: a dev-v0 run is not citable), a change to this list, to
// the three-character rule, or to the tokenizer below silently rescales every score logged before it:
// it takes a numbered decisions.md entry, not a quiet edit. TestSupportStopwordsArePinned
// pins the list; TestContentTokensRules pins the tokenizer and the length rule. Recorded in
// decisions.md's inherited frozen-values table.
var supportStopwords = map[string]struct{}{
	"a": {}, "an": {}, "and": {}, "are": {}, "as": {}, "at": {}, "be": {}, "but": {}, "by": {},
	"for": {}, "if": {}, "in": {}, "into": {}, "is": {}, "it": {}, "no": {}, "not": {}, "of": {},
	"on": {}, "or": {}, "such": {}, "that": {}, "the": {}, "their": {}, "then": {}, "there": {},
	"these": {}, "they": {}, "this": {}, "to": {}, "was": {}, "will": {}, "with": {},
}

// minContentTokenLen is the "tokens under three characters removed" rule of the formula.
const minContentTokenLen = 3

// eachToken lowercases s and calls emit for every maximal run of [a-z0-9].
//
// ASCII only, and deliberately NOT cache.Normalize: that keeps Unicode letters and does not split
// on punctuation ("30-day" is one token there, "30" and "day" here). The two tokenizers serve
// different jobs (a cache key must not stem or drop words; this score must) and must not be unified.
// Bytes of 0x80 and above are separators, so a non-ASCII letter splits a word instead of joining it.
// No stemming: "return", "returns" and "returned" are three tokens.
func eachToken(s string, emit func(string)) {
	var b strings.Builder
	flush := func() {
		if b.Len() > 0 {
			emit(b.String())
			b.Reset()
		}
	}
	for i := 0; i < len(s); i++ {
		switch c := s[i]; {
		case c >= 'a' && c <= 'z', c >= '0' && c <= '9':
			b.WriteByte(c)
		case c >= 'A' && c <= 'Z':
			b.WriteByte(c + ('a' - 'A'))
		default:
			flush()
		}
	}
	flush()
}

// contentTokens is content-tokens(a): the answer's tokens with stopwords and tokens shorter than
// three characters removed, as a SET. A set, not a multiset, for the reason Overlap dedupes chunk
// IDs: a repeated word would otherwise move the denominator on prose that differs only in how often
// one word repeats.
//
// Unexported on purpose. Item 2.2's numeric arm must NOT reuse it: the length rule drops "30" and
// "14", exactly the literals a numeric check exists to compare.
func contentTokens(s string) map[string]struct{} {
	out := make(map[string]struct{})
	eachToken(s, func(tok string) {
		if len(tok) < minContentTokenLen {
			return
		}
		if _, stop := supportStopwords[tok]; stop {
			return
		}
		out[tok] = struct{}{}
	})
	return out
}

// textTokens is tokens(C): every token of the evidence, unfiltered (the formula filters only the
// answer's side), as a set for membership tests.
//
// Unexported for the same reason as contentTokens, and for a second one: a set over the UNION of
// every retrieved chunk cannot tell "1800 W" in one chunk from "1800" in one and "W" in another,
// so the numeric arm needs its own unit-aware tokenizer.
func textTokens(s string) map[string]struct{} {
	out := make(map[string]struct{})
	eachToken(s, func(tok string) { out[tok] = struct{}{} })
	return out
}

// SupportVerdict is the lexical arm's result.
//
// It is a struct rather than a (float64, bool) so the safety-relevant field cannot be dropped
// silently: with a tuple, `score, _ := SupportLexical(...)` compiles and reads an unscorable
// retrieval as score 0, which is below TauSupportLexical, which is a SUPPORT refusal. The package
// keeps NamespaceDecision apart from Decision for the same reason (lane.go).
//
// A struct does NOT stop a caller from reading Score alone: `v.Score < TauSupportLexical` compiles,
// and on an unscored verdict (Score 0) it is true. Decide through Refuses, never through Score.
type SupportVerdict struct {
	// Scored is false exactly when the instrument could not run: the RAG service sent chunk IDs with
	// no evidence text, i.e. a pre-1.4 server (ragclient/retrieve.go, RetrieveResult.Texts). That
	// must not be scored, must not be refused as SUPPORT, and must not be logged as the gate-off
	// arm. The zero value is Scored == false, but its Score is 0, so Score is MEANINGLESS unless
	// Scored is true.
	Scored bool
	// Score is S_lex(a, C). Meaningful only when Scored. 0 when the retrieval legitimately returned
	// nothing (no evidence supports nothing: a real verdict, not a missing instrument), and 0 when
	// the answer has no content tokens (nothing to support, matching Overlap's "no recorded
	// provenance scores 0").
	Score float64
	// ContentTokenCount is |content-tokens(a)|, the denominator. It is here so a refusal can be told
	// apart from a short answer: the score's resolution is 1/ContentTokenCount, so a two-token
	// answer is refused the moment one token is missing from the evidence, whatever the evidence
	// says. The same shape as Overlap's top-k granularity note. 0 when not Scored.
	ContentTokenCount int
}

// Refuses reports whether the lexical arm refuses reuse: it scored, and scored below
// TauSupportLexical. An unscored verdict neither refuses nor admits, so it returns false here and the
// caller must count that condition separately (v.Scored == false); a caller that wants "may reuse"
// must NOT write !v.Refuses(), which is also true for an unscored verdict.
//
// This is the one sanctioned way to turn a verdict into a refusal, so the Scored check cannot be
// forgotten at the call site (the cause code, item 2.3). The comparison is inclusive on the admit
// side, as the proposal states it: refused when S_lex < tau_s.
func (v SupportVerdict) Refuses() bool {
	return v.Scored && v.Score < TauSupportLexical
}

// SupportLexical computes the lexical support gate for one (cached answer, fresh evidence) pair:
//
//	S_lex(a, C) = |content-tokens(a) ∩ tokens(C)| / |content-tokens(a)|
//
// C is the union of the elements of texts. The query text is never read: the gate scores the CACHED
// ANSWER against the NEW evidence.
//
// retrievedChunkIDs is the chunk IDs of the FRESH retrieval, the same call that produced texts. It
// is NEVER the cached entry's source_chunk_ids, which is also a []string and is never empty: passing
// that compiles, and would make an empty retrieval read as "unscored" instead of "scored 0".
//
// It is consulted only to tell a stale server from an empty retrieval. An empty texts is ambiguous
// by itself (proto3 decodes both "no texts" and "no chunks" to nil), so the rule keys on
// len(retrievedChunkIDs) > 0, as ragclient/retrieve.go (RetrieveResult.Texts) and super-plan.md item
// 2.1 say. It is never scored over. texts[i] is assumed to belong to retrievedChunkIDs[i];
// alignment is the seam's job, asserted by the live check in ragclient.
//
// Granularity: the score takes only multiples of 1/ContentTokenCount. See SupportVerdict.
//
// An empty retrieval returns Scored with Score 0, which refuses it. That is deliberate. The cascade
// no longer lets one reach the gate (item 2.3: tryTier2 returns before deriving a namespace when the
// retrieval has no chunks), because the spec lane's namespace falls back to the request's product ID
// and a zero-chunk retrieval could otherwise reach a served hit with no evidence behind it. The
// score stays 0 here so the function is safe on its own.
func SupportLexical(answer string, texts []string, retrievedChunkIDs []string) SupportVerdict {
	if len(texts) == 0 && len(retrievedChunkIDs) > 0 {
		return SupportVerdict{}
	}
	content := contentTokens(answer)
	if len(content) == 0 {
		return SupportVerdict{Scored: true}
	}
	evidence := textTokens(strings.Join(texts, "\n"))
	supported := 0
	for tok := range content {
		if _, ok := evidence[tok]; ok {
			supported++
		}
	}
	return SupportVerdict{
		Scored:            true,
		Score:             float64(supported) / float64(len(content)),
		ContentTokenCount: len(content),
	}
}
