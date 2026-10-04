package cache

import "testing"

// Normalize is the whole of Tier-1's safety. interfaces.md §D: "This lookup is a bare hash
// equality test -- no similarity check, no containment check", so a normalization change that
// merges two queries with different correct answers serves the wrong one "permanently, with
// nothing to detect it", and the resulting false hit is charged to a reuse rule that never ran.
// These cases are therefore the executable statement of the Tier-1 normalization contract, not incidental coverage.
func TestNormalize(t *testing.T) {
	cases := []struct {
		name string
		in   string
		want string
	}{
		{"lowercase", "How Long Is The WARRANTY", "how long is the warranty"},
		{"collapse runs of spaces", "how  long   is", "how long is"},
		{"collapse mixed whitespace", "how\tlong\nis", "how long is"},
		{"trim surrounding whitespace", "   how long is   ", "how long is"},
		{"strip trailing punctuation", "can i return this?", "can i return this"},
		{"strip repeated terminal punctuation", "really?!", "really"},
		{"internal punctuation does not join words", "laptop, headphones", "laptop headphones"},
		{"punctuation between spaces leaves one space", "laptop , headphones", "laptop headphones"},
		{"apostrophe stripped", "what's the return window", "whats the return window"},
		{"symbols stripped", "under $500 & in stock", "under 500 in stock"},
		{"non-breaking space is whitespace", "how long", "how long"},
		{"already normalized is unchanged", "how long is the warranty", "how long is the warranty"},
		{"punctuation only normalizes to empty", "???", ""},
		{"empty stays empty", "", ""},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := Normalize(tc.in); got != tc.want {
				t.Errorf("Normalize(%q) = %q, want %q", tc.in, got, tc.want)
			}
		})
	}
}

// the Tier-1 normalization contract requires the identical function on the read and write paths. Store.Get and Store.Put
// both call Key(Normalize(q)); idempotence is what makes that safe if a normalized string is
// ever re-normalized in between (e.g. a value read back out of Redis and fed forward).
func TestNormalizeIsIdempotent(t *testing.T) {
	for _, in := range []string{
		"How Long Is The WARRANTY?",
		"  laptop ,  headphones  ",
		"???",
		"",
	} {
		once := Normalize(in)
		if twice := Normalize(once); twice != once {
			t.Errorf("Normalize(Normalize(%q)) = %q, want %q", in, twice, once)
		}
	}
}

// The known lossy case, recorded in interfaces.md §D: "stripping punctuation collapses
// `Model A-1` and `Model A1` -- harmless within one product, not harmless across two."
// This test asserts the collapse so the behaviour stays a deliberate, documented trade-off
// rather than a surprise. The corpus gate is what keeps it safe: data-card.md §7's invariant
// is that no two queries with different reference_answer or doc_ids share a normalize(q).
func TestNormalizeCollapsesHyphenatedModelNames(t *testing.T) {
	if a, b := Normalize("Model A-1"), Normalize("Model A1"); a != b {
		t.Fatalf("expected the documented collision: Normalize(%q)=%q vs Normalize(%q)=%q",
			"Model A-1", a, "Model A1", b)
	}
}

// The guard against smuggling a reuse decision into cache/. architecture.md §2: cache/ "must
// never make a reuse decision -- that is reuse/". Stemming, stopword removal or synonym
// folding would each merge distinct questions at the hash, which is a reuse judgement made
// where nothing measures it and no threshold governs it.
func TestNormalizeDoesNotStemOrDropStopwords(t *testing.T) {
	distinct := [][2]string{
		{"return", "returns"},                              // no stemming
		{"the warranty", "warranty"},                       // no stopword removal
		{"how long is the return window", "return window"}, // no phrase reduction
		{"can i return this", "can i refund this"},         // no synonym folding
	}
	for _, pair := range distinct {
		if Normalize(pair[0]) == Normalize(pair[1]) {
			t.Errorf("Normalize merged %q and %q -- that is a reuse decision, and cache/ must not make one",
				pair[0], pair[1])
		}
	}
}

// interfaces.md §D: KEY t1:{sha256(normalized_query "\x00" product_id)}. ⚠️ BYPASS 2026-09-09,
// reverses the "product_id in the Tier-1 key -- Rejected" -- see cache.Key.
func TestKey(t *testing.T) {
	const q = "how long is the warranty"

	got := Key(q, "")
	if want := 3 + 64; len(got) != want {
		t.Errorf("Key(%q,\"\") = %q, want %d chars (t1: + 64 hex)", q, got, want)
	}
	if got[:3] != "t1:" {
		t.Errorf("Key(%q,\"\") = %q, want the t1: prefix", q, got)
	}
	if again := Key(q, ""); again != got {
		t.Errorf("Key is not deterministic: %q then %q", got, again)
	}
	if other := Key("how long is the return window", ""); other == got {
		t.Error("distinct normalized queries produced the same Tier-1 key")
	}
}

// The read/write-path invariant of the Tier-1 normalization contract, stated end to end: spellings that differ only in
// case, spacing or punctuation must reach the same Redis key, or the Tier-1 hit rate is
// understated and configuration 2's "literal-repeat share" measurement (proposal §2b row 7)
// is wrong. Fixed at one product_id, so this also asserts stability holds WITHIN a product.
func TestKeyIsStableAcrossTrivialSpellingVariants(t *testing.T) {
	const productID = "product-headphones-03"
	want := Key(Normalize("how long is the warranty"), productID)

	for _, variant := range []string{
		"How long is the warranty?",
		"HOW LONG IS THE WARRANTY",
		"  how   long is the warranty  ",
		"how long is the warranty.",
	} {
		if got := Key(Normalize(variant), productID); got != want {
			t.Errorf("Key(Normalize(%q), %q) = %q, want %q", variant, productID, got, want)
		}
	}
}

// TestKeyIsScopedByProductID is the bug this bypass fixes: two literally identical questions
// asked about different products must NOT collide -- see the conversation in
// the now-reversed rejection.
func TestKeyIsScopedByProductID(t *testing.T) {
	const q = "how long is the battery life"

	a := Key(q, "product-headphones-03")
	b := Key(q, "product-headphones-04")
	if a == b {
		t.Errorf("Key(%q, product-03) == Key(%q, product-04) = %q -- different products collided", q, q, a)
	}

	empty := Key(q, "")
	if empty == a || empty == b {
		t.Errorf("Key(%q, \"\") collided with a product-scoped key -- empty product_id must be its own partition, not a wildcard", q)
	}
}

// TestKeySeparatorIsUnambiguous pins the "\x00" separator: without it, Key("ab","c") and
// Key("a","bc") would hash identically.
func TestKeySeparatorIsUnambiguous(t *testing.T) {
	if Key("ab", "c") == Key("a", "bc") {
		t.Error(`Key("ab","c") == Key("a","bc") -- the normalized/product_id separator is ambiguous`)
	}
}
