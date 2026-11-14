package httpapi

import (
	"context"
	"math"
	"testing"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/ragpb"
	"github.com/hung/thesis/gateway/internal/reuse"
)

// Item 6.0a (ADR-030), done conditions 3, 6, 13 and 14: the scope arm and the fallback answer, driven
// through Ask with fakes (no Redis, no Ollama). What reuse/'s own tests cannot show is that the write path
// and the search path agree: if a shared entry were written under one key and searched under another, no
// shared entry would ever be found, and the arm would read as a plausible null.
//
// The corpus here is three products and ONE policy document. A and B are electronics, C is furniture; the
// RAG fake retrieves the electronics return policy for all three, as it would if ADR-020's category swap
// ever failed. The category guard is then the only thing that keeps C out of the shared namespace.

const (
	scopePolicyDoc = "policy-return-electronics"
	scopeProductA  = "product-electronics-a"
	scopeProductB  = "product-electronics-b"
	scopeProductC  = "product-furniture-c"

	// scopeNeutral names no product. Every word of it is in scopeTexts, so the support gate passes.
	scopeNeutral = "unopened items may be returned within 30 days of delivery"
	// scopeNamed names product A by one of its bound words.
	scopeNamed = "the aurora may be returned within 30 days of delivery"

	scopeTauP = 0.80 // below testTau (0.85) on purpose: a candidate between them tells the two apart
)

func scopeGrounding() []string {
	return []string{scopePolicyDoc + "#chunk-0", scopePolicyDoc + "#chunk-1"}
}

var scopeTexts = []string{
	"Unopened items may be returned within 30 days of delivery. The Aurora may be returned too.",
	"Returns are free for unopened items.",
}

// scopeRAG retrieves the electronics return policy for any of the three products and answers with
// `answer`, or with the fallback when noAnswer is set.
type scopeRAG struct {
	ragpb.UnimplementedRagServiceServer
	answer   string
	noAnswer bool
}

func scopeKnows(productID string) bool {
	return productID == scopeProductA || productID == scopeProductB || productID == scopeProductC
}

func (scopeRAG) Retrieve(_ context.Context, req *ragpb.RetrieveRequest) (*ragpb.RetrieveResponse, error) {
	if req.GetTopK() != 0 {
		return nil, status.Errorf(codes.InvalidArgument, "Retrieve sent top_k=%d; the gateway must send 0", req.GetTopK())
	}
	if !scopeKnows(req.GetProductId()) {
		return nil, status.Errorf(codes.InvalidArgument, "Retrieve for unknown product_id %q", req.GetProductId())
	}
	return &ragpb.RetrieveResponse{
		ChunkIds:     scopeGrounding(),
		Scores:       []float32{0.9, 0.8},
		DatasetEpoch: testEpoch,
		Texts:        append([]string(nil), scopeTexts...),
	}, nil
}

func (s scopeRAG) Answer(req *ragpb.AnswerRequest, stream grpc.ServerStreamingServer[ragpb.AnswerChunk]) error {
	if req.GetTopK() != 0 {
		return status.Errorf(codes.InvalidArgument, "Answer sent top_k=%d; the gateway must send 0", req.GetTopK())
	}
	if !scopeKnows(req.GetProductId()) {
		return status.Errorf(codes.InvalidArgument, "Answer for unknown product_id %q", req.GetProductId())
	}
	text := s.answer
	if s.noAnswer {
		text = "Sorry, I don't have that detail for this product. Please check the product page or contact our support team."
	}
	return stream.Send(&ragpb.AnswerChunk{
		Text:           text,
		Done:           true,
		SourceChunkIds: scopeGrounding(),
		ModelUsed:      testModel,
		DatasetEpoch:   testEpoch,
		NoAnswer:       s.noAnswer,
	})
}

// mix is the unit vector (e_a + e_b) / sqrt 2.
func mix(a, b int) []float64 {
	v := make([]float64, len(basis(0)))
	v[a], v[b] = 1/math.Sqrt2, 1/math.Sqrt2
	return v
}

// scopeMeta is the document metadata: A and B electronics, C furniture, each with its own title direction.
// A question vector mix(1, titleDir) is "the policy question" (direction 1) plus the product's name
// (the title direction), so removing the title direction leaves e_1 for every product.
func scopeMeta() map[string]reuse.DocMeta {
	return map[string]reuse.DocMeta{
		scopePolicyDoc: {Category: "electronics"},
		scopeProductA:  {Category: "electronics", TitleVec: float32s(basis(2)), BoundWords: map[string]struct{}{"aurora": {}}},
		scopeProductB:  {Category: "electronics", TitleVec: float32s(basis(4)), BoundWords: map[string]struct{}{"earbuds": {}}},
		scopeProductC:  {Category: "furniture", TitleVec: float32s(basis(6)), BoundWords: map[string]struct{}{"sofa": {}}},
	}
}

// scopeHarness is a harness with the scope RAG, the thresholds of this file and, when on is true, the arm
// switched on with the metadata. The metadata is set even with the arm off, to show it is then ignored.
func scopeHarness(t *testing.T, on bool, rag scopeRAG) *harness {
	t.Helper()
	hs := newHarness(t, 1, 0)
	hs.useRAG(t, rag)
	hs.h.Thresholds = reuse.Thresholds{Tau: testTau, Theta: testTheta, TauP: scopeTauP}
	hs.h.DocMeta = scopeMeta()
	hs.h.ScopeOn = on
	return hs
}

func (hs *harness) askVec(t *testing.T, q string, vec []float64, product string) *call {
	t.Helper()
	hs.embedder.learn(q, vec)
	return hs.ask(t, askReq{question: q, productID: product})
}

// storedVector is the key vector the fake store holds for the entry written by the n-th Tier-2 write.
func (hs *harness) storedVector(n int) []float32 {
	hs.store.mu.Lock()
	defer hs.store.mu.Unlock()
	return hs.store.t2[n].vec
}

// --- condition 6: with the arm off, nothing changes ----------------------------------------------

func TestScopeArmOffMakesOneSearchAndWritesTheProductNamespace(t *testing.T) {
	hs := scopeHarness(t, false, scopeRAG{answer: scopeNeutral})

	// A POLICY miss, then a paraphrase from the same product (a hit), then another product (a miss).
	c1 := hs.askVec(t, "Can I return an unopened item?", mix(1, 2), scopeProductA)
	c2 := hs.askVec(t, "May I send back an item I never opened?", mix(1, 2), scopeProductA)
	c3 := hs.askVec(t, "Can I return something unopened?", mix(1, 4), scopeProductB)
	waitFor(t, "the Tier-2 write-backs", func() bool { return len(hs.store.tier2Written()) == 2 })
	hs.records(t)

	// Exactly one namespace search per request, each in "{policy_doc}@{product_id}".
	got := hs.store.namespacesSearched()
	want := []string{
		scopePolicyDoc + "@" + scopeProductA,
		scopePolicyDoc + "@" + scopeProductA,
		scopePolicyDoc + "@" + scopeProductB,
	}
	if len(got) != len(want) {
		t.Fatalf("namespaces searched = %q, want one search per request %q", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("search %d was in %q, want %q", i, got[i], want[i])
		}
	}
	// Every write is a product-scope write, in the same namespace form, whatever the metadata says.
	for i, e := range hs.store.tier2Written() {
		if e.Namespace != want[0] && e.Namespace != want[2] {
			t.Errorf("write %d: namespace %q is not a {policy_doc}@{product_id} form", i, e.Namespace)
		}
		if e.Scope != "product" {
			t.Errorf("write %d: scope %q, want product", i, e.Scope)
		}
	}
	if c2.response(t).text("cache") != "TIER2_HIT" || c3.response(t).text("cache") != "MISS" {
		t.Errorf("the paraphrase on the same product must hit and another product must miss: %s / %s",
			c2.response(t).text("cache"), c3.response(t).text("cache"))
	}

	for _, c := range []*call{c1, c2, c3} {
		rec := c.record(t)
		rec.str("scope_arm", "off")
		rec.str("query_lane", "POLICY")
		rec.null("shared_similarity")
		rec.null("shared_refusal_cause")
	}
	c1.record(t).str("write_scope", "product")
	c1.record(t).null("hit_scope")
	c2.record(t).str("hit_scope", "product")
	c2.record(t).null("write_scope")
}

// --- condition 14: a neutral answer is served across products of one category ----------------------

func TestScopeArmOnSharesANeutralPolicyAnswerWithinACategory(t *testing.T) {
	hs := scopeHarness(t, true, scopeRAG{answer: scopeNeutral})

	// 1. Product A asks. A MISS, and the answer names nothing of A, so it is written ONCE, in the shared
	// namespace, under the vector with A's title direction removed (e_1).
	c1 := hs.askVec(t, "Can I return an unopened item?", mix(1, 2), scopeProductA)
	waitFor(t, "the first Tier-2 write-back", func() bool { return len(hs.store.tier2Written()) == 1 })
	entry := hs.store.tier2Written()[0]
	if entry.Namespace != scopePolicyDoc || entry.Scope != "shared" || entry.Lane != "POLICY" {
		t.Fatalf("the neutral answer was written as namespace %q scope %q lane %q, want the shared form %q/shared/POLICY",
			entry.Namespace, entry.Scope, entry.Lane, scopePolicyDoc)
	}
	key := hs.storedVector(0)
	if c := cosine(key, float32s(basis(1))); c < 0.99999 {
		t.Errorf("the shared key vector has cosine %v with e_1, want 1: the title direction was not removed", c)
	}
	if c := cosine(key, float32s(basis(2))); math.Abs(c) > 1e-6 {
		t.Errorf("the shared key vector still points at the title: cosine %v", c)
	}

	// 2. Product B asks a paraphrase. B's own namespace is empty, so the product search finds nothing; the
	// shared search finds A's entry. The raw cosine of the two question vectors is only 0.5, so without the
	// projection this could never be a hit.
	c2 := hs.askVec(t, "May I send back an item I never opened?", mix(1, 4), scopeProductB)
	if got := c2.response(t).text("cache"); got != "TIER2_HIT" {
		t.Fatalf("B's paraphrase: cache = %q, want TIER2_HIT from the shared entry", got)
	}
	c2.response(t).str("answer", scopeNeutral)
	waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
	waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 2 })

	// 3. Product C (furniture) asks. The policy document is electronics, so the category guard keeps C out of
	// the shared namespace: a MISS, generated and written in C's own product namespace.
	c3 := hs.askVec(t, "Is it possible to return a sealed item?", mix(1, 6), scopeProductC)
	if got := c3.response(t).text("cache"); got != "MISS" {
		t.Fatalf("C's request: cache = %q, want MISS: the shared entry crossed into another category", got)
	}
	waitFor(t, "the third Tier-2 write-back", func() bool { return len(hs.store.tier2Written()) == 2 })
	hs.records(t)

	if e := hs.store.tier2Written()[1]; e.Namespace != scopePolicyDoc+"@"+scopeProductC || e.Scope != "product" {
		t.Errorf("C's answer was written as %q scope %q, want %q product",
			e.Namespace, e.Scope, scopePolicyDoc+"@"+scopeProductC)
	}
	// Searches, in order: A (product, then shared: both empty), B (product, then shared: found), C (product
	// only: the category guard stops the shared search).
	want := []string{
		scopePolicyDoc + "@" + scopeProductA,
		scopePolicyDoc,
		scopePolicyDoc + "@" + scopeProductB,
		scopePolicyDoc,
		scopePolicyDoc + "@" + scopeProductC,
	}
	got := hs.store.namespacesSearched()
	if len(got) != len(want) {
		t.Fatalf("namespaces searched = %q, want %q", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("search %d was in %q, want %q", i, got[i], want[i])
		}
	}
	r1, r2, r3 := c1.record(t), c2.record(t), c3.record(t)
	for _, r := range []fields{r1, r2, r3} {
		r.str("scope_arm", "on")
		r.str("query_lane", "POLICY")
	}
	r1.str("write_scope", "shared")
	r2.str("cache", "TIER2_HIT")
	r2.str("hit_scope", "shared")
	r2.str("entry_id", entry.EntryID)
	r2.str("refusal_cause", "NONE")
	r2.notNull("similarity") // a hit keeps its similarity (interfaces.md H, I3)
	r2.notNull("shared_similarity")
	r2.str("shared_refusal_cause", "NONE")
	r3.str("write_scope", "product")
	r3.null("hit_scope")
	r3.null("shared_similarity") // the category guard stopped the search: no shared candidate

	// The shared hit was promoted into Tier 1 under B's own key, and the entry says it.
	promoted := false
	for _, w := range hs.store.tier1Written() {
		if w.entry.Promotion && w.entry.EntryID == entry.EntryID && w.key == cache.Key(cache.Normalize("May I send back an item I never opened?"), scopeProductB) {
			promoted = true
		}
	}
	if !promoted {
		t.Errorf("no Tier-1 promotion of the shared entry %s under B's key; writes: %+v", entry.EntryID, hs.store.tier1Written())
	}
}

func TestScopeArmOnAnAnswerThatNamesTheProductStaysProductScope(t *testing.T) {
	hs := scopeHarness(t, true, scopeRAG{answer: scopeNamed})

	c1 := hs.askVec(t, "Can I return the Aurora if it is unopened?", mix(1, 2), scopeProductA)
	waitFor(t, "the Tier-2 write-back", func() bool { return len(hs.store.tier2Written()) == 1 })
	e := hs.store.tier2Written()[0]
	if e.Namespace != scopePolicyDoc+"@"+scopeProductA || e.Scope != "product" {
		t.Errorf("an answer naming the product was written as %q scope %q, want %q product",
			e.Namespace, e.Scope, scopePolicyDoc+"@"+scopeProductA)
	}
	if c := cosine(hs.storedVector(0), float32s(mix(1, 2))); c < 0.99999 {
		t.Errorf("a product-scope entry is keyed by the RAW vector; cosine with it is %v", c)
	}
	// B asks the same thing: it must not be served A's named answer. Its shared search finds nothing.
	c2 := hs.askVec(t, "May I send back an item I never opened?", mix(1, 4), scopeProductB)
	if got := c2.response(t).text("cache"); got != "MISS" {
		t.Errorf("B's request = %q, want MISS: an answer that names product A was served to B", got)
	}
	hs.records(t)
	c1.record(t).str("write_scope", "product")
	c2.record(t).null("shared_similarity")
}

// --- the product-scope match is served first -------------------------------------------------------

func TestScopeArmOnServesTheProductMatchBeforeTheSharedOne(t *testing.T) {
	hs := scopeHarness(t, true, scopeRAG{answer: scopeNeutral})
	q := "Can I return an unopened item?"
	hs.embedder.learn(q, mix(1, 4))

	productEntry := cache.Tier2Entry{
		EntryID: cache.NewEntryID(), QueryText: q, Answer: scopeNeutral, SourceChunkIDs: scopeGrounding(),
		T1Key: cache.Key(cache.Normalize(q), scopeProductB), DatasetEpoch: testEpoch,
		Namespace: scopePolicyDoc + "@" + scopeProductB, Lane: "POLICY", Scope: "product",
	}
	sharedEntry := productEntry
	sharedEntry.EntryID, sharedEntry.Namespace, sharedEntry.Scope = cache.NewEntryID(), scopePolicyDoc, "shared"
	hs.store.seedTier2(productEntry, float32s(mix(1, 4)))
	hs.store.seedTier2(sharedEntry, float32s(basis(1)))

	c := hs.ask(t, askReq{question: q, productID: scopeProductB})
	waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
	hs.records(t)

	rec := c.record(t)
	rec.str("cache", "TIER2_HIT")
	rec.str("entry_id", productEntry.EntryID)
	rec.str("hit_scope", "product")
	rec.null("shared_similarity") // the shared search never ran
	if got := hs.store.namespacesSearched(); len(got) != 1 {
		t.Errorf("namespaces searched = %q, want only the product namespace", got)
	}
}

// --- condition 13, through the cascade: TauP for a shared candidate, Tau for a product one ---------

func TestScopeArmOnJudgesTheSharedCandidateAgainstTauPAndTheProductOneAgainstTau(t *testing.T) {
	// A question vector whose cosine with e_1 is 0.82: between TauP (0.80) and tau (0.85).
	between := toward(1, 3, 0.82)
	q := "Can I return an unopened item?"

	t.Run("a shared candidate at 0.82 is served", func(t *testing.T) {
		hs := scopeHarness(t, true, scopeRAG{answer: scopeNeutral})
		hs.embedder.learn(q, between)
		shared := cache.Tier2Entry{
			EntryID: cache.NewEntryID(), QueryText: "x", Answer: scopeNeutral, SourceChunkIDs: scopeGrounding(),
			T1Key: "t1", DatasetEpoch: testEpoch, Namespace: scopePolicyDoc, Lane: "POLICY", Scope: "shared",
		}
		hs.store.seedTier2(shared, float32s(basis(1)))
		c := hs.ask(t, askReq{question: q, productID: scopeProductB})
		waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
		hs.records(t)
		rec := c.record(t)
		rec.str("cache", "TIER2_HIT")
		rec.str("hit_scope", "shared")
		rec.near("shared_similarity", 0.82, 1e-4)
	})

	t.Run("a product candidate at 0.82 is refused", func(t *testing.T) {
		hs := scopeHarness(t, true, scopeRAG{answer: scopeNeutral})
		hs.embedder.learn(q, between)
		product := cache.Tier2Entry{
			EntryID: cache.NewEntryID(), QueryText: "x", Answer: scopeNeutral, SourceChunkIDs: scopeGrounding(),
			T1Key: "t1", DatasetEpoch: testEpoch, Namespace: scopePolicyDoc + "@" + scopeProductB, Lane: "POLICY", Scope: "product",
		}
		hs.store.seedTier2(product, float32s(basis(1)))
		c := hs.ask(t, askReq{question: q, productID: scopeProductB})
		hs.records(t)
		rec := c.record(t)
		rec.str("cache", "MISS")
		rec.str("refusal_cause", "SIMILARITY")
		rec.str("candidate_entry_id", product.EntryID)
		rec.null("shared_similarity")
	})

	t.Run("a shared candidate below tau_P is refused with its own cause", func(t *testing.T) {
		hs := scopeHarness(t, true, scopeRAG{answer: scopeNeutral})
		hs.embedder.learn(q, toward(1, 3, 0.70))
		shared := cache.Tier2Entry{
			EntryID: cache.NewEntryID(), QueryText: "x", Answer: scopeNeutral, SourceChunkIDs: scopeGrounding(),
			T1Key: "t1", DatasetEpoch: testEpoch, Namespace: scopePolicyDoc, Lane: "POLICY", Scope: "shared",
		}
		hs.store.seedTier2(shared, float32s(basis(1)))
		c := hs.ask(t, askReq{question: q, productID: scopeProductB})
		hs.records(t)
		rec := c.record(t)
		rec.str("cache", "MISS")
		rec.str("shared_refusal_cause", "SIMILARITY")
		rec.near("shared_similarity", 0.70, 1e-4)
		rec.null("refusal_cause") // no product candidate was judged
	})
}

func TestScopeArmOnIgnoresASharedNamespaceEntryThatIsNotMarkedShared(t *testing.T) {
	// An entry in the policy document's own namespace without scope "shared" is one written before the arm
	// (ADR-025's form). It was keyed by a raw vector and must not be compared with a projected one.
	hs := scopeHarness(t, true, scopeRAG{answer: scopeNeutral})
	q := "Can I return an unopened item?"
	hs.embedder.learn(q, mix(1, 4))
	legacy := cache.Tier2Entry{
		EntryID: cache.NewEntryID(), QueryText: "x", Answer: scopeNeutral, SourceChunkIDs: scopeGrounding(),
		T1Key: "t1", DatasetEpoch: testEpoch, Namespace: scopePolicyDoc, Lane: "POLICY",
	}
	hs.store.seedTier2(legacy, float32s(basis(1)))
	c := hs.ask(t, askReq{question: q, productID: scopeProductB})
	hs.records(t)
	c.record(t).str("cache", "MISS")
	c.record(t).null("shared_similarity")
}

// --- condition 3: a fallback answer is served and never stored ---------------------------------------

func TestNoAnswerIsServedAndWritesNothing(t *testing.T) {
	for _, on := range []bool{false, true} {
		name := "arm off"
		if on {
			name = "arm on"
		}
		t.Run(name, func(t *testing.T) {
			hs := scopeHarness(t, on, scopeRAG{noAnswer: true})
			fd := newFakeDeps()
			hs.h.Deps = fd
			hs.h.Capacity = 2 // a bounded cache, so a touch or a trim would show
			// An epoch that differs from Answer's: had the epoch check run before the return, the record
			// would say writeback_discarded. The fallback returns before it.
			hs.h.Epoch = &fakeEpoch{v: testEpoch + 1}

			c := hs.askVec(t, "What colour is the box?", mix(1, 2), scopeProductA)
			hs.records(t)

			if c.w.Code != 200 {
				t.Fatalf("status %d: %s", c.w.Code, c.w.Body)
			}
			c.response(t).str("cache", "MISS")
			c.response(t).str("answer", "Sorry, I don't have that detail for this product. Please check the product page or contact our support team.")
			for _, method := range []string{"Put", "PutTier2", "Touch", "TrimToCapacity", "BumpHitCount"} {
				if n := hs.store.callCount(method); n != 0 {
					t.Errorf("%s was called %d time(s) for a fallback answer, want 0", method, n)
				}
			}
			if regs := fd.registrations(); len(regs) != 0 {
				t.Errorf("%d dependency registration(s) for a fallback answer, want 0: %+v", len(regs), regs)
			}
			if n := len(hs.store.t1Writes) + len(hs.store.t2Writes); n != 0 {
				t.Errorf("%d tier write(s) recorded for a fallback answer, want 0", n)
			}
			rec := c.record(t)
			rec.str("cache", "MISS")
			rec.boolean("no_answer", true)
			rec.str("entry_id", "")
			rec.null("entry_sources")
			rec.null("write_scope")
			rec.boolean("writeback_discarded", false)
			if on {
				rec.str("scope_arm", "on")
			} else {
				rec.str("scope_arm", "off")
			}
		})
	}
}

func TestAFallbackAnswerIsNotServedToALaterQuestionThatHasAnAnswer(t *testing.T) {
	// The harm the rule prevents: "no detail" cached for one question and served to a paraphrase.
	hs := scopeHarness(t, true, scopeRAG{noAnswer: true})
	c1 := hs.askVec(t, "What colour is the box?", mix(1, 2), scopeProductA)
	c2 := hs.askVec(t, "Which colour is the box?", mix(1, 2), scopeProductA) // the same vector, the same product
	hs.records(t)
	c1.record(t).str("cache", "MISS")
	c2.record(t).str("cache", "MISS") // not a hit: nothing was cached
	c2.record(t).boolean("no_answer", true)
}

func TestARecordWithAnOrdinaryAnswerHasNoAnswerFalse(t *testing.T) {
	hs := scopeHarness(t, false, scopeRAG{answer: scopeNeutral})
	c := hs.askVec(t, "Can I return an unopened item?", mix(1, 2), scopeProductA)
	hs.records(t)
	c.record(t).boolean("no_answer", false)
}
