package cache

import (
	"strings"
	"unicode"
)

// Normalize implements ADR-015's Tier-1 normalization exactly: lowercase, collapse internal
// whitespace, strip surrounding/most punctuation. No stemming, no stopwords, no synonyms --
// that would smuggle a reuse decision into a package that must never make one
// (architecture-guardrails.md: cache/ owns key normalization, never a reuse decision).
// The identical function must run on both the read and write paths or Tier-1 hit rate is
// understated (ADR-015).
func Normalize(query string) string {
	lower := strings.ToLower(query)

	var b strings.Builder
	b.Grow(len(lower))
	prevSpace := false
	for _, r := range lower {
		switch {
		case unicode.IsSpace(r):
			if !prevSpace && b.Len() > 0 {
				b.WriteRune(' ')
			}
			prevSpace = true
		case unicode.IsPunct(r) || unicode.IsSymbol(r):
			// stripped
		default:
			b.WriteRune(r)
			prevSpace = false
		}
	}
	return strings.TrimSpace(b.String())
}
