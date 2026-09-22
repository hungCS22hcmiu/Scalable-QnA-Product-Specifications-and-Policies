package reuse

import "testing"

// These pin PROPERTIES whose drift would leave the two-lane rule looking like it still worked,
// in the same spirit as rule_test.go. They are not coverage.

// collapsed is the band that reproduces the ORIGINAL single-sigma rule: Lo == Hi leaves the
// MIXED interval empty. Every pre-existing assertion below is written against it, unchanged in
// meaning -- only the call shape moved when Classify took a band instead of a float.
func collapsed(sigma float64) LaneBand { return LaneBand{Lo: sigma, Hi: sigma} }

func TestPolicyFractionSeparatesTheTwoLanes(t *testing.T) {
	// The shapes actually measured on dev-v0 2026-09-06: a spec question retrieves no policy
	// chunk at all, a policy question retrieves several. If this ever stops holding, the lane
	// selector is guessing and every number downstream of it is meaningless.
	spec := []string{
		"product-headphones-03#chunk-0", "product-headphones-04#chunk-0",
		"product-headphones-09#chunk-0", "product-headphones-01#chunk-0",
		"product-headphones-06#chunk-0",
	}
	policy := []string{
		"policy-returns-electronics#chunk-0", "policy-returns-furniture#chunk-0",
		"product-headphones-10#chunk-0", "product-headphones-09#chunk-0",
		"policy-warranty#chunk-0",
	}
	if got := PolicyFraction(spec); got != 0 {
		t.Fatalf("spec grounding: PolicyFraction = %v, want 0", got)
	}
	if got := PolicyFraction(policy); got != 0.6 {
		t.Fatalf("policy grounding: PolicyFraction = %v, want 0.6", got)
	}
	if Classify(spec, collapsed(0.2)) != LaneSpec {
		t.Fatal("spec grounding classified as POLICY")
	}
	if Classify(policy, collapsed(0.2)) != LanePolicy {
		t.Fatal("policy grounding classified as SPEC")
	}
}

func TestClassifyIsInclusiveAtSigma(t *testing.T) {
	// Decide is inclusive at theta and this must match it. If one rule is inclusive and the
	// other exclusive, a comparison between them partly measures the boundary convention.
	ids := []string{"policy-a#chunk-0", "product-b#chunk-0", "product-c#chunk-0", "product-d#chunk-0"}
	if PolicyFraction(ids) != 0.25 {
		t.Fatalf("fixture wrong: %v", PolicyFraction(ids))
	}
	if Classify(ids, collapsed(0.25)) != LanePolicy {
		t.Fatal("exactly at sigma must be POLICY (inclusive), matching Decide's >= theta")
	}
	if Classify(ids, collapsed(0.26)) != LaneSpec {
		t.Fatal("just above sigma must be SPEC")
	}
}

func TestPolicyFractionEmptyGroundingIsSpec(t *testing.T) {
	// An answer with no provenance cannot be shown to be policy-governed. Overlap already scores
	// such an entry 0; the lane selector must be conservative in the same direction, because
	// SPEC is the narrower namespace and therefore the safer default.
	if PolicyFraction(nil) != 0 {
		t.Fatal("empty grounding must score 0")
	}
	if Classify(nil, collapsed(0.2)) != LaneSpec {
		t.Fatal("empty grounding must fall in the narrower lane")
	}
}

func TestNamespaceUsesRankNotSetMembership(t *testing.T) {
	// The measured failure this guards: on dev-v0 both an electronics return question and a
	// furniture return question retrieve BOTH return policies, so the SETS are identical and
	// carry no signal. Only rank-1 separates them. A "simplification" to sorted-set or
	// any-match would silently merge two namespaces that must stay apart.
	elec := []string{
		"policy-returns-electronics#chunk-0", "policy-returns-furniture#chunk-0",
		"product-headphones-10#chunk-0", "product-headphones-09#chunk-0", "policy-warranty#chunk-0",
	}
	furn := []string{
		"policy-returns-furniture#chunk-0", "policy-returns-electronics#chunk-0",
		"product-furniture-04#chunk-0", "policy-shipping#chunk-0", "policy-warranty#chunk-0",
	}
	gotE := Namespace(LanePolicy, elec, "")
	gotF := Namespace(LanePolicy, furn, "")
	if gotE != "policy-returns-electronics" {
		t.Fatalf("electronics namespace = %q", gotE)
	}
	if gotF != "policy-returns-furniture" {
		t.Fatalf("furniture namespace = %q", gotF)
	}
	if gotE == gotF {
		t.Fatal("the two lanes collapsed into one namespace -- rank was ignored")
	}
}

func TestNamespaceStripsChunkOrdinal(t *testing.T) {
	// The namespace is the DOCUMENT. Keying on the chunk would repartition the cache whenever a
	// policy grows a chunk, which is a silent hit-rate loss with no error.
	ids := []string{"policy-returns-electronics#chunk-2"}
	if got := Namespace(LanePolicy, ids, ""); got != "policy-returns-electronics" {
		t.Fatalf("namespace = %q, want the doc id without the ordinal", got)
	}
}

func TestSpecLanePrefersRequestProductIDOverRankOne(t *testing.T) {
	// Measured 2026-09-06: two paraphrases of one question about the EarBuds Pop 3 ranked
	// DIFFERENT products first -- headphones-04 (the Pro variant) and headphones-03. Rank-1 is
	// unstable wherever a catalog holds near-duplicate variants, which is everywhere in real
	// e-commerce. Request metadata does not drift, so it wins in this lane.
	a := []string{"product-headphones-04#chunk-0", "product-headphones-03#chunk-0"}
	b := []string{"product-headphones-03#chunk-0", "product-headphones-04#chunk-0"}
	if Namespace(LaneSpec, a, "") == Namespace(LaneSpec, b, "") {
		t.Fatal("fixture no longer reproduces the rank instability this test exists for")
	}
	if Namespace(LaneSpec, a, "product-headphones-03") != Namespace(LaneSpec, b, "product-headphones-03") {
		t.Fatal("product_id must make the namespace stable across paraphrases")
	}
}

func TestEmptyNamespaceIsUnmatchableNotAWildcard(t *testing.T) {
	// The dangerous failure: if "" matched anything, an entry whose grounding could not be
	// partitioned would become reusable by every query -- a false hit on every lookup, and the
	// rule would still report a plausible decision.
	if MatchNamespace("", "") {
		t.Fatal("two empty namespaces must not match")
	}
	if MatchNamespace("policy-returns-electronics", "") {
		t.Fatal("an entry with no namespace must not be reusable")
	}
	if MatchNamespace("", "policy-returns-electronics") {
		t.Fatal("a query with no namespace must not reuse anything")
	}
	if !MatchNamespace("policy-warranty", "policy-warranty") {
		t.Fatal("equal non-empty namespaces must match")
	}
}

func TestDecideNamespaceNeedsBothSimilarityAndMatch(t *testing.T) {
	th := Thresholds{Tau: 0.85, Theta: 0.60}
	ns := "policy-returns-electronics"

	if d := th.DecideNamespace(0.91, LanePolicy, ns, ns); !d.Reuse {
		t.Fatal("above tau with matching namespace must reuse")
	}
	if d := th.DecideNamespace(0.84, LanePolicy, ns, ns); d.Reuse {
		t.Fatal("below tau must refuse even with a matching namespace")
	}
	if d := th.DecideNamespace(0.99, LanePolicy, ns, "policy-returns-furniture"); d.Reuse {
		t.Fatal("a namespace mismatch must refuse at any similarity -- this is the whole rule")
	}
	// Inclusive at tau, matching Decide.
	if d := th.DecideNamespace(0.85, LanePolicy, ns, ns); !d.Reuse {
		t.Fatal("exactly at tau must reuse (inclusive), matching Decide")
	}
}

// --- stratum D: the MIXED lane -------------------------------------------------------------
//
// data-card.md §2 pre-registers stratum D as a question whose grounding SPANS product and
// policy. These tests pin the reason it needed its own lane: with only two lanes it is not
// merely classified imprecisely, it is served WRONG.

func TestCollapsedBandReproducesTheOriginalTwoLaneRule(t *testing.T) {
	// The pre-registered baseline. If a future edit makes Lo == Hi emit MIXED, every run taken
	// under the collapsed band silently stops being comparable to the runs before it, with no
	// error anywhere.
	mixed := []string{
		"product-headphones-03#chunk-0", "product-headphones-03#chunk-1",
		"policy-warranty#chunk-0", "policy-returns-electronics#chunk-0",
	}
	if got := PolicyFraction(mixed); got != 0.5 {
		t.Fatalf("fixture wrong: PolicyFraction = %v", got)
	}
	for _, sigma := range []float64{0.2, 0.5, 0.8} {
		if got := Classify(mixed, collapsed(sigma)); got == LaneMixed {
			t.Fatalf("collapsed band at sigma=%v produced MIXED -- the baseline is no longer reproducible", sigma)
		}
	}
}

func TestMixedGroundingGetsItsOwnLaneOnlyInsideTheBand(t *testing.T) {
	mixed := []string{
		"product-headphones-03#chunk-0", "product-headphones-03#chunk-1",
		"policy-warranty#chunk-0", "policy-returns-electronics#chunk-0",
	} // policy_frac = 0.5

	if got := Classify(mixed, LaneBand{Lo: 0.2, Hi: 0.9}); got != LaneMixed {
		t.Fatalf("inside the band: lane = %s, want MIXED", got)
	}
	// Inclusive at BOTH bounds, matching Decide's >= theta and DecideNamespace's >= tau. A rule
	// that is inclusive at one bound and exclusive at the other makes a band sweep partly a
	// measurement of the boundary convention.
	if got := Classify(mixed, LaneBand{Lo: 0.5, Hi: 0.9}); got != LaneMixed {
		t.Fatalf("exactly at Lo must be MIXED (inclusive), got %s", got)
	}
	if got := Classify(mixed, LaneBand{Lo: 0.2, Hi: 0.5}); got != LanePolicy {
		t.Fatalf("exactly at Hi must be POLICY (inclusive), got %s", got)
	}
	if got := Classify(mixed, LaneBand{Lo: 0.6, Hi: 0.9}); got != LaneSpec {
		t.Fatalf("below Lo must be SPEC, got %s", got)
	}
}

func TestSingleKindGroundingIsNeverMixedHoweverTheBandIsSet(t *testing.T) {
	// Structural, not numeric. A grounding holding one kind of document cannot span two kinds,
	// so no choice of Lo may invent a mixed question out of it. Guarding this numerically would
	// make a badly swept Lo produce mixed entries with no product half to be wrong about --
	// entries that then sit in the cache unreachable by any correct rule.
	specOnly := []string{"product-headphones-03#chunk-0", "product-headphones-04#chunk-0"}
	policyOnly := []string{"policy-warranty#chunk-0", "policy-returns-electronics#chunk-0"}
	wide := LaneBand{Lo: 0.0, Hi: 1.0}

	if got := Classify(specOnly, wide); got != LaneSpec {
		t.Fatalf("all-product grounding = %s, want SPEC at any band", got)
	}
	if got := Classify(policyOnly, wide); got != LanePolicy {
		t.Fatalf("all-policy grounding = %s, want POLICY at any band", got)
	}
	if got := Classify(nil, wide); got != LaneSpec {
		t.Fatalf("empty grounding = %s, want SPEC at any band", got)
	}
}

func TestMixedNamespaceIsThePairAndNeedsBothHalves(t *testing.T) {
	// Replaces TestMixedLaneHasNoNamespaceAndSoCannotMatchOne, whose premise (MIXED has no
	// namespace, containment decides) was refuted by the 2026-09-06 run.
	mixed := []string{"product-headphones-03#chunk-0", "policy-warranty#chunk-0"}
	if got := Namespace(LaneMixed, mixed, ""); got != "product-headphones-03|policy-warranty" {
		t.Fatalf("MIXED namespace = %q, want the pair", got)
	}
	// productID still wins on the product half, for the rank-1 instability reason the SPEC lane
	// has: a mixed question about a near-duplicate variant must not drift namespace between
	// paraphrases on the product side either.
	if got := Namespace(LaneMixed, mixed, "product-headphones-99"); got != "product-headphones-99|policy-warranty" {
		t.Fatalf("productID did not win the product half: %q", got)
	}

	// HALF a composite key must be UNMATCHABLE, never a wildcard. Returning just the policy half
	// when no product chunk was retrieved would silently widen the entry to "any product" -- the
	// exact over-broad namespace the lane exists to prevent.
	if got := Namespace(LaneMixed, []string{"policy-warranty#chunk-0"}, ""); got != "" {
		t.Fatalf("missing product half must give \"\", got %q", got)
	}
	if got := Namespace(LaneMixed, []string{"product-headphones-03#chunk-0"}, ""); got != "" {
		t.Fatalf("missing policy half must give \"\", got %q", got)
	}
	// A composite can never equal a pure-lane namespace, so the lanes cannot collide through the
	// key even before DecideLane's explicit lane check.
	if Namespace(LaneMixed, mixed, "") == Namespace(LaneSpec, mixed, "") ||
		Namespace(LaneMixed, mixed, "") == Namespace(LanePolicy, mixed, "") {
		t.Fatal("a composite namespace collided with a pure-lane one")
	}
}

func TestMixedQuestionsAboutDifferentProductsAreNotInterchangeable(t *testing.T) {
	// THE BUG THE LANE EXISTS FOR, end to end.
	//
	// "warranty + battery life of the EarBuds Pop 3" and "warranty + weight of the Sofa Nord"
	// both retrieve policy-warranty at rank 1. Under the two-lane rule both take
	// namespace="policy-warranty", match, and the sofa asker is served the headphones' spec.
	// Their similarity is high because both are warranty questions, so tau does not save it.
	th := Thresholds{Tau: 0.85, Theta: 0.60}
	band := LaneBand{Lo: 0.2, Hi: 0.9}

	headphones := []string{"policy-warranty#chunk-0", "product-headphones-03#chunk-0"}
	sofa := []string{"policy-warranty#chunk-0", "product-furniture-04#chunk-0"}

	// The old rule's verdict, shown so the regression is visible rather than asserted in prose.
	if !th.DecideNamespace(0.93, LanePolicy,
		Namespace(LanePolicy, sofa, ""), Namespace(LanePolicy, headphones, "")).Reuse {
		t.Fatal("fixture no longer reproduces the two-lane false hit this lane exists to close")
	}

	lane := Classify(sofa, band)
	if lane != LaneMixed {
		t.Fatalf("sofa question classified %s, want MIXED", lane)
	}
	d := th.DecideLane(LaneInput{
		Similarity: 0.93,
		QueryLane:  lane,
		QueryNS:    Namespace(lane, sofa, "product-furniture-04"),
		EntryLane:  Classify(headphones, band),
		EntryNS:    Namespace(Classify(headphones, band), headphones, "product-headphones-03"),
	})
	if d.Reuse {
		t.Fatal("a mixed question was served another product's mixed answer -- the whole point, missed")
	}
	if d.Rule != RuleComposite {
		t.Fatalf("MIXED decided by %q, want %q", d.Rule, RuleComposite)
	}
	// Refused on the composite key, not on the lane: both groundings ARE mixed. The recorded
	// counterfactual shows containment would also have refused this one (0.5 < theta) -- this is
	// the case containment gets RIGHT, kept so the pair of tests shows exactly where the two
	// rules diverge and where they agree.
	if !d.LaneMatch {
		t.Fatal("both groundings are mixed; the refusal must come from the key, not the lane")
	}
	if got := Overlap(sofa, headphones); got != 0.5 {
		t.Fatalf("counterfactual overlap = %v, want 0.5", got)
	}
}

func TestMixedQuestionMayNotReuseAPolicyOnlyEntry(t *testing.T) {
	// Why lane equality is needed ON TOP of containment. Overlap divides by the ENTRY's source
	// count, so a two-chunk policy-only entry fully contained in a mixed question's retrieval
	// scores 1.0 -- a perfect containment score for an answer that never mentions the product.
	// Asymmetric containment is blind to "the query asked for more than the entry was grounded
	// in" by construction, and stratum D is exactly where that blindness bites.
	th := Thresholds{Tau: 0.85, Theta: 0.60}
	band := LaneBand{Lo: 0.2, Hi: 0.9}

	policyEntry := []string{"policy-warranty#chunk-0", "policy-returns-electronics#chunk-0"}
	mixedQuery := []string{
		"policy-warranty#chunk-0", "policy-returns-electronics#chunk-0",
		"product-headphones-03#chunk-0", "product-headphones-03#chunk-1",
	}
	if got := Overlap(mixedQuery, policyEntry); got != 1.0 {
		t.Fatalf("fixture wrong: overlap = %v, want the full 1.0 that makes this trap possible", got)
	}

	d := th.DecideLane(LaneInput{
		Similarity: 0.95,
		QueryLane:  Classify(mixedQuery, band),
		QueryNS:    Namespace(Classify(mixedQuery, band), mixedQuery, "product-headphones-03"),
		EntryLane:  Classify(policyEntry, band),
		EntryNS:    Namespace(Classify(policyEntry, band), policyEntry, ""),
	})
	if d.Reuse {
		t.Fatal("containment alone served a policy-only answer to a question that also asked about a product")
	}
	if d.LaneMatch {
		t.Fatal("a POLICY entry must not count as a lane match for a MIXED query")
	}
}

func TestPureQuestionMayNotReuseAMixedEntry(t *testing.T) {
	// The other direction. A mixed entry is written with namespace "", and MatchNamespace refuses
	// "" on either side -- so the three lanes partition the cache into non-interacting regions
	// and their false-hit rates stay separately attributable.
	th := Thresholds{Tau: 0.85, Theta: 0.60}
	band := LaneBand{Lo: 0.2, Hi: 0.9}

	mixedEntry := []string{"policy-warranty#chunk-0", "product-headphones-03#chunk-0"}
	specQuery := []string{"product-headphones-03#chunk-0", "product-headphones-03#chunk-1"}

	entryLane := Classify(mixedEntry, band)
	if entryLane != LaneMixed {
		t.Fatalf("fixture wrong: entry lane = %s", entryLane)
	}
	d := th.DecideLane(LaneInput{
		Similarity: 0.99,
		QueryLane:  Classify(specQuery, band),
		QueryNS:    Namespace(LaneSpec, specQuery, "product-headphones-03"),
		EntryLane:  entryLane,
		EntryNS:    Namespace(entryLane, mixedEntry, "product-headphones-03"),
	})
	if d.Reuse {
		t.Fatal("a spec question reused a mixed entry -- the lanes are no longer disjoint")
	}
	if d.Rule != RuleNamespace {
		t.Fatalf("a SPEC query must be decided by %q, got %q", RuleNamespace, d.Rule)
	}
}

func TestMixedLaneReusesWhenGroundingIsGenuinelyTheSame(t *testing.T) {
	// The lane must not be a disguised bypass. Two paraphrases of one mixed question ground out
	// the same way and must reuse, or stratum D is simply uncacheable and the fallback bought
	// nothing.
	th := Thresholds{Tau: 0.85, Theta: 0.60}
	band := LaneBand{Lo: 0.2, Hi: 0.9}

	entry := []string{"policy-warranty#chunk-0", "product-headphones-03#chunk-0"}
	query := []string{"product-headphones-03#chunk-0", "policy-warranty#chunk-0"} // same set, different rank

	d := th.DecideLane(LaneInput{
		Similarity: 0.91,
		QueryLane:  Classify(query, band),
		QueryNS:    Namespace(LaneMixed, query, "product-headphones-03"),
		EntryLane:  Classify(entry, band),
		EntryNS:    Namespace(LaneMixed, entry, "product-headphones-03"),
	})
	if !d.Reuse {
		t.Fatalf("identical grounding refused: match=%v lane_match=%v", d.Match, d.LaneMatch)
	}
	if got := Overlap(query, entry); got != 1.0 {
		t.Fatalf("counterfactual overlap = %v, want 1.0", got)
	}
	// Below tau must still refuse -- the composite key replaces the namespace term, not the tau
	// gate. Namespaces are passed so it is unambiguously tau doing the refusing.
	if th.DecideLane(LaneInput{
		Similarity: 0.84, QueryLane: LaneMixed, EntryLane: LaneMixed,
		QueryNS: Namespace(LaneMixed, query, "product-headphones-03"),
		EntryNS: Namespace(LaneMixed, entry, "product-headphones-03"),
	}).Reuse {
		t.Fatal("below tau must refuse in the MIXED lane too")
	}
}

func TestDecideLaneRecordsWhichTermDecided(t *testing.T) {
	// Without this the fallback's contribution to the false-hit rate cannot be attributed, which
	// would put it outside experiment-protocol.md §4's two-cause split.
	th := Thresholds{Tau: 0.85, Theta: 0.60}
	ns := "policy-warranty"

	pure := th.DecideLane(LaneInput{Similarity: 0.9, QueryLane: LanePolicy, QueryNS: ns, EntryNS: ns})
	if pure.Rule != RuleNamespace || !pure.Reuse {
		t.Fatalf("pure lane: rule=%q reuse=%v", pure.Rule, pure.Reuse)
	}
	// DecideLane computes NO containment, in any lane. The cascade fills Overlap in afterwards
	// for the served candidate only; computing it here would run it per candidate across the
	// fan-out and discard all but one.
	if pure.Overlap != 0 {
		t.Fatal("DecideLane must not compute an overlap")
	}
	mixed := th.DecideLane(LaneInput{Similarity: 0.9, QueryLane: LaneMixed, EntryLane: LaneMixed,
		QueryNS: "p|q", EntryNS: "p|q"})
	if mixed.Overlap != 0 {
		t.Fatal("DecideLane must not compute an overlap in the MIXED lane either")
	}
}

// TestNoThetaSeparatesTheMeasuredPair is the reason this lane does not use containment.
//
// These are the exact chunk sets logged on 2026-09-06 (functional run, dev-v0; the numbers are
// not citable but the SHAPE is what is pinned). One cached entry, two follow-up requests, both
// scoring an identical containment of 0.80 while needing opposite verdicts:
//
//	entry:      battery life of the EarBuds Pop 3 + how long do I have to return it
//	request A:  a paraphrase of the same question         -> reuse is CORRECT
//	request B:  same product, WARRANTY instead of return  -> reuse is a FALSE HIT
//
// A mixed grounding is ~4 product chunks to ~1 policy chunk, so the chunk carrying the whole
// difference is 1/5 of the denominator; at top-5 the overlap granularity is 0.2. If this test
// ever passes with a containment-based MIXED arm, the arithmetic has changed and the finding must
// be re-measured before the rule is changed back.
func TestNoThetaSeparatesTheMeasuredPair(t *testing.T) {
	entry := []string{
		"product-headphones-04#chunk-0", "product-headphones-03#chunk-0",
		"policy-returns-electronics#chunk-0", "product-headphones-09#chunk-0",
		"product-headphones-01#chunk-0",
	}
	paraphrase := []string{ // differs only in which trailing PRODUCT chunk ranked fifth
		"product-headphones-04#chunk-0", "product-headphones-03#chunk-0",
		"policy-returns-electronics#chunk-0", "product-headphones-09#chunk-0",
		"product-headphones-02#chunk-0",
	}
	warranty := []string{ // differs only in the POLICY chunk -- the entire semantic difference
		"product-headphones-04#chunk-0", "product-headphones-03#chunk-0",
		"product-headphones-09#chunk-0", "policy-warranty#chunk-0",
		"product-headphones-01#chunk-0",
	}

	// The premise: containment cannot tell them apart at ANY theta.
	if Overlap(paraphrase, entry) != 0.8 || Overlap(warranty, entry) != 0.8 {
		t.Fatalf("premise gone: paraphrase=%v warranty=%v -- both were 0.80 when measured",
			Overlap(paraphrase, entry), Overlap(warranty, entry))
	}

	th := Thresholds{Tau: 0.85, Theta: 0.60}
	band := LaneBand{Lo: 0.20, Hi: 0.60}
	const productID = "product-headphones-03"

	decide := func(retrieved []string, sim float64) NamespaceDecision {
		lane := Classify(retrieved, band)
		if lane != LaneMixed {
			t.Fatalf("fixture classified %s, want MIXED", lane)
		}
		return th.DecideLane(LaneInput{
			Similarity: sim,
			QueryLane:  lane,
			QueryNS:    Namespace(lane, retrieved, productID),
			EntryLane:  LaneMixed,
			EntryNS:    Namespace(LaneMixed, entry, productID),
		})
	}

	// Similarities as measured: 0.9382 and 0.9208. Both clear tau, so tau does not separate them
	// either -- the key is the only thing that can.
	a := decide(paraphrase, 0.9382)
	b := decide(warranty, 0.9208)

	if !a.Reuse {
		t.Fatalf("the legitimate paraphrase was refused: query_ns=%q entry_ns=%q", a.QueryNS, a.EntryNS)
	}
	if b.Reuse {
		t.Fatalf("FALSE HIT: a warranty question served the return answer (query_ns=%q entry_ns=%q)",
			b.QueryNS, b.EntryNS)
	}
	// Both counterfactuals must still say "containment would have reused", or this test has
	// stopped documenting the failure it exists for.
	if Overlap(paraphrase, entry) != 0.8 || Overlap(warranty, entry) != 0.8 {
		t.Fatal("counterfactuals drifted; this test no longer documents the failure it exists for")
	}
	if !th.Decide(0.9208, warranty, entry).Reuse {
		t.Fatal("the containment rule no longer reuses the false-hit case -- re-measure before trusting this")
	}
}

func TestMixedLaneRefusesWhenAComponentIsMissing(t *testing.T) {
	// The measured Lo-boundary case: "how much does the SoundMax ANC Pro weigh and what is its
	// warranty period" retrieved FIVE product chunks and zero policy chunks. Its policy half is
	// ungrounded, so whatever was generated for it must never be reused as a mixed answer.
	th := Thresholds{Tau: 0.85, Theta: 0.60}
	noPolicy := []string{
		"product-headphones-01#chunk-0", "product-headphones-02#chunk-0",
		"product-headphones-10#chunk-0", "product-headphones-04#chunk-0",
		"product-headphones-05#chunk-0",
	}
	// It does not even reach MIXED -- policy_frac is 0, so it is structurally SPEC.
	if got := Classify(noPolicy, LaneBand{Lo: 0.20, Hi: 0.60}); got != LaneSpec {
		t.Fatalf("zero-policy grounding classified %s, want SPEC", got)
	}
	// And were it forced into the mixed lane, the half-key must be unmatchable rather than
	// widening to "any policy".
	d := th.DecideLane(LaneInput{
		Similarity: 0.99,
		QueryLane:  LaneMixed,
		QueryNS:    Namespace(LaneMixed, noPolicy, "product-headphones-01"),
		EntryLane:  LaneMixed,
		EntryNS:    "product-headphones-01|policy-warranty",
	})
	if d.Reuse {
		t.Fatal("a half-composite key matched -- it widened to any policy")
	}
}
