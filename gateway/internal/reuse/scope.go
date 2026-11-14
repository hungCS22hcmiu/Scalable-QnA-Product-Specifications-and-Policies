package reuse

import "math"

// The scope arm's pure part (item 6.0a, ADR-030): where may an answer be SERVED. A POLICY answer that
// names nothing of its product is true for every product that routes to the same policy document, so
// it is stored once for all of them ("shared"). Everything here is deterministic and reads no query
// text: a word test on the ANSWER at write time, and one projection of the question vector.
//
// Stdlib only, no I/O, like the rest of this package (docs/architecture.md 2). The Python side
// (rag/src/rag/docmeta.py, experiments/scripts/scope_calibrate.py) implements the same tokenizer and
// projection, and contracts/scope/cases.json pins both: a difference is silent.

// Scope says where an entry may be served.
type Scope string

const (
	// ScopeProduct: the entry lives in "{policy_doc}@{product_id}" under the raw question vector. It is
	// today's (ADR-024) form and the only form with the arm off.
	ScopeProduct Scope = "product"
	// ScopeShared: the entry lives in the policy document's own namespace under the projected question
	// vector, and is served to every product of the same category.
	ScopeShared Scope = "shared"
)

// DocMeta is what the scope test reads about one document: `docmeta:{doc_id}` in Redis, loaded at start.
// A policy document has a Category only. A product has a Category, a TitleVec (the title embedded with
// the document prefix) and BoundWords: the words of its title and specs that name it and no other
// product, in no policy document of its category and in at most 10 % of the products.
type DocMeta struct {
	Category   string
	TitleVec   []float32
	BoundWords map[string]struct{}
}

// nearZero is the share of |v| below which nothing is left after a projection. It is in
// contracts/scope/cases.json, so the Python calibration uses the same value.
const nearZero = 1e-6

// ScopeTokens is the tokenizer the scope test and the bound-word list share: ASCII letters and digits
// make tokens, the case of an ASCII letter is folded, every other byte (punctuation, spaces, accents,
// letters of other scripts) separates tokens, and a token under two characters is dropped. The result
// is a set.
func ScopeTokens(text string) map[string]struct{} {
	out := make(map[string]struct{})
	var token []byte
	flush := func() {
		if len(token) >= 2 {
			out[string(token)] = struct{}{}
		}
		token = token[:0]
	}
	for i := 0; i < len(text); i++ {
		switch c := text[i]; {
		case c >= 'a' && c <= 'z', c >= '0' && c <= '9':
			token = append(token, c)
		case c >= 'A' && c <= 'Z':
			token = append(token, c+('a'-'A'))
		default:
			flush()
		}
	}
	flush()
	return out
}

// CanShare is the category guard and the title-vector guard, in one place so the write path (DecideScope)
// and the read path (the second search) cannot disagree. A product and a policy document may share only
// when the policy document has metadata, the product has a title vector, and both have the SAME
// non-empty category. ADR-020's category swap makes the category match in practice; this makes it hold
// if that swap ever fails, because an answer must not spread to another category.
func CanShare(product, policy DocMeta, hasPolicy bool) bool {
	return hasPolicy &&
		len(product.TitleVec) > 0 &&
		product.Category != "" &&
		product.Category == policy.Category
}

// DecideScope is the write-time scope test. ScopeShared only when the lane is POLICY, CanShare holds, and
// no token of the answer is one of the product's bound words; ScopeProduct otherwise. SPEC and MIXED
// answers are never shared. The caller never calls it with the arm off.
func DecideScope(lane Lane, answer string, product, policy DocMeta, hasPolicy bool) Scope {
	if lane != LanePolicy || !CanShare(product, policy, hasPolicy) {
		return ScopeProduct
	}
	for token := range ScopeTokens(answer) {
		if _, bound := product.BoundWords[token]; bound {
			return ScopeProduct
		}
	}
	return ScopeShared
}

// Project removes the part of the question vector v that points at the product's title vector t:
//
//	v' = normalise(v - (v . t^) t^),  t^ = t / |t|
//
// It is nil when t is missing or has another length than v, when |v| or |t| is zero, or when
// |v'| <= 1e-6 * |v| (nothing is left). A nil result means the request takes product scope only. The
// arithmetic is float64 and the result float32, the width of the stored vectors.
func Project(v, t []float32) []float32 {
	if len(t) == 0 || len(t) != len(v) {
		return nil
	}
	var nv, nt float64
	for i := range v {
		nv += float64(v[i]) * float64(v[i])
		nt += float64(t[i]) * float64(t[i])
	}
	nv, nt = math.Sqrt(nv), math.Sqrt(nt)
	if nv == 0 || nt == 0 {
		return nil
	}
	var dot float64
	for i := range v {
		dot += float64(v[i]) * float64(t[i]) / nt
	}
	rest := make([]float64, len(v))
	var nr float64
	for i := range v {
		rest[i] = float64(v[i]) - dot*float64(t[i])/nt
		nr += rest[i] * rest[i]
	}
	nr = math.Sqrt(nr)
	if nr <= nearZero*nv {
		return nil
	}
	out := make([]float32, len(v))
	for i := range rest {
		out[i] = float32(rest[i] / nr)
	}
	return out
}

// SharedNamespace is the namespace of a shared entry: the policy document alone, with no product. It is
// also what Namespace(LanePolicy, ids, "") returns, so the read path derives it from a request's own
// retrieval with the same vote the write path used.
func SharedNamespace(policyDoc string) string { return policyDoc }
