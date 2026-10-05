package httpapi

// The harness behind ask_test.go (docs/work/2026-10-04-httpapi-tests/design.md §1-§3, §8).
//
// This file is SCAFFOLDING (approvals.md, item 4): it may gain behaviour for a new seam, with a
// note in the task that adds it. It may NOT loosen a strict check -- top_k != 0, an unknown embed
// input, misaligned texts, Answer's dropped source, the shared epoch. Loosening one is changing an
// assertion, and the assertions in ask_test.go are immutable.
//
// Only the cache is faked at the Go level. The RAG service and the embedder are faked at the WIRE,
// behind the real ragclient and embed clients, because how those clients surface an error is where
// a misclassification hides (finding F-A).

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/hung/thesis/gateway/internal/admission"
	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/embed"
	"github.com/hung/thesis/gateway/internal/ragclient"
	"github.com/hung/thesis/gateway/internal/ragpb"
	"github.com/hung/thesis/gateway/internal/reuse"
	"github.com/hung/thesis/gateway/internal/telemetry"
)

const (
	// Non-default on purpose, so a record that silently dropped them would fail (S9).
	testRunID    = "httpapi-test"
	testConfigID = 5
	testMutation = "on"
	testStratum  = "B-para"

	// testEpoch is the dataset epoch both Retrieve and Answer report. Equal on purpose (S6): the
	// Phase 4 epoch guard must not discard these write-backs.
	testEpoch = uint64(7)
	testModel = "qwen3.5-2b"

	// Thresholds as cmd/gateway/main.go configures them. TauHigh is never named: its zero value
	// leaves the branch disabled, and this literal keeps compiling after 1.3 deletes the field.
	testTau   = 0.85
	testTheta = 0.60

	// hitCos and belowTauCos sit 0.10 either side of tau. No fixture similarity lies within 0.05
	// of tau (N2): the embed client narrows to float32 and the fake store computes in float64.
	hitCos      = testTau + 0.10
	belowTauCos = testTau - 0.10

	// nomicQueryPrefix deliberately restates embed's unexported queryPrefix. The fake embedder
	// knows vectors only under the prefixed input, so a request without the prefix is an unknown
	// input and gets a 500 (N1).
	nomicQueryPrefix = "search_query: "

	// waitDeadline bounds every wait. Expiring it FAILS the test; it never passes one.
	waitDeadline = 5 * time.Second

	// freshDirections starts above every direction a test picks by hand.
	freshDirections = 100
)

// --- the corpus -------------------------------------------------------------------------------

// product is one document of the fake corpus: ranked chunks, and the answer the fake service
// generates for it.
//
// The fixture rule (design.md §3, S1): every answer is a VERBATIM substring of chunk 0's text and
// contains no numerals, so the Phase 2 support gate holds on every hit these tests seed.
// checkFixtures enforces it.
//
// otherAnswer obeys the same rule but differs from answer. A seeded entry that must be refused
// carries it, so a response can tell the refused entry being served apart from a fresh generation.
type product struct {
	id          string
	texts       []string
	answer      string
	otherAnswer string
}

var (
	kettle = product{
		id: "product-kettle-01",
		texts: []string{
			"The Aurora kettle has a brushed steel body and an automatic shutoff switch.",
			"The base swivels so the kettle can be lifted from any side.",
			"Descale the kettle with a mild citric solution when scale appears.",
		},
		answer:      "a brushed steel body and an automatic shutoff switch",
		otherAnswer: "an automatic shutoff switch",
	}
	headphones = product{
		id: "product-headphones-03",
		texts: []string{
			"The EarBuds Pop ship with silicone ear tips and a compact charging case.",
			"Touch controls on each bud pause and resume playback.",
			"The case charges over a standard cable.",
		},
		answer:      "silicone ear tips and a compact charging case",
		otherAnswer: "a compact charging case",
	}
)

// corpus is read-only after initialisation. Nothing mutable is shared between tests.
var corpus = map[string]product{kettle.id: kettle, headphones.id: headphones}

// chunkIDs are interfaces.md §C's `{doc_id}#chunk-{ordinal}`, in rank order.
func (p product) chunkIDs() []string {
	ids := make([]string, len(p.texts))
	for i := range p.texts {
		ids[i] = fmt.Sprintf("%s#chunk-%d", p.id, i)
	}
	return ids
}

// answerSources is the provenance the fake Answer reports: its grounding MINUS the last chunk,
// as the real service may. It therefore differs from what Retrieve returned (S7), which is what
// lets a test tell which of the two sets was written back.
func (p product) answerSources() []string {
	ids := p.chunkIDs()
	return ids[:len(ids)-1]
}

func productOfChunk(chunkID string) (product, bool) {
	docID, _, _ := strings.Cut(chunkID, "#")
	p, ok := corpus[docID]
	return p, ok
}

func checkFixtures(t *testing.T) {
	t.Helper()
	for _, p := range corpus {
		for _, a := range []string{p.answer, p.otherAnswer} {
			if !strings.Contains(p.texts[0], a) {
				t.Fatalf("fixture rule: %s's answer %q is not a verbatim substring of chunk 0", p.id, a)
			}
			if strings.ContainsAny(a, "0123456789") {
				t.Fatalf("fixture rule: %s's answer %q contains a numeral", p.id, a)
			}
		}
		if p.answer == p.otherAnswer {
			t.Fatalf("fixture rule: %s's two answers must differ", p.id)
		}
	}
}

// --- vectors ----------------------------------------------------------------------------------

// basis is the unit vector along direction i. Distinct directions are orthogonal, so two
// questions on different directions never reach tau.
func basis(i int) []float64 {
	v := make([]float64, embed.Dim)
	v[i] = 1
	return v
}

// toward is a unit vector whose cosine with basis(from) is exactly cos: cos·e_from + sin·e_other.
func toward(from, other int, cos float64) []float64 {
	v := make([]float64, embed.Dim)
	v[from] = cos
	v[other] = math.Sqrt(1 - cos*cos)
	return v
}

// around is a unit vector whose cosine with the unit vector v is exactly cos. Direction other must
// be orthogonal to v (v[other] == 0).
func around(v []float64, other int, cos float64) []float64 {
	out := make([]float64, len(v))
	for i, x := range v {
		out[i] = cos * x
	}
	out[other] = math.Sqrt(1 - cos*cos)
	return out
}

func float32s(v []float64) []float32 {
	out := make([]float32, len(v))
	for i, x := range v {
		out[i] = float32(x)
	}
	return out
}

func cosine(a, b []float32) float64 {
	var dot, na, nb float64
	for i := range a {
		x, y := float64(a[i]), float64(b[i])
		dot += x * y
		na += x * x
		nb += y * y
	}
	if na == 0 || nb == 0 {
		return 0
	}
	return dot / math.Sqrt(na*nb)
}

// --- the cache: an in-memory model of cache.Store ---------------------------------------------

// fakeStore is a MODEL of the store, not a per-call script: a script would encode today's call
// sequence, and 1.3 changes that sequence.
//
// It encodes three of the real store's semantics, and these tests cannot notice if cache.Store
// diverges from them (that is cache/'s own tests' job): Tier 1 partitions by
// cache.Key(cache.Normalize(q), productID); an empty namespace matches nothing; similarity is the
// raw cosine, which equals the real store's 1 - COSINE distance.
type fakeStore struct {
	mu sync.Mutex

	t1 map[string]cache.Entry
	t2 []tier2Row

	// Successful writes, in order. Seeding does not count as a write.
	t1Writes []tier1Write
	t2Writes []cache.Tier2Entry
	bumps    []string
	touches  []string // entry_ids, in order
	trims    []int    // the capacity each TrimToCapacity call was given

	calls            map[string]int // every call, by method, including ones that returned an injected error
	failing          map[string]error
	injectedReturned int
}

type tier2Row struct {
	entry cache.Tier2Entry
	vec   []float32
}

type tier1Write struct {
	key   string
	entry cache.Entry
}

var _ cacheStore = (*fakeStore)(nil)

func newFakeStore() *fakeStore {
	return &fakeStore{
		t1:      map[string]cache.Entry{},
		calls:   map[string]int{},
		failing: map[string]error{},
	}
}

// enter counts the call and returns the injected error for method, if any. Callers hold s.mu.
func (s *fakeStore) enter(method string) error {
	s.calls[method]++
	if err := s.failing[method]; err != nil {
		s.injectedReturned++
		return err
	}
	return nil
}

func (s *fakeStore) Get(_ context.Context, query, productID string) (*cache.Entry, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.enter("Get"); err != nil {
		return nil, false, err
	}
	e, ok := s.t1[cache.Key(cache.Normalize(query), productID)]
	if !ok {
		return nil, false, nil
	}
	e.SourceChunkIDs = append([]string(nil), e.SourceChunkIDs...)
	return &e, true, nil
}

func (s *fakeStore) Put(_ context.Context, query, productID string, e cache.Entry) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.enter("Put"); err != nil {
		return err
	}
	if e.EntryID == "" { // as Store.Put does
		e.EntryID = cache.NewEntryID()
	}
	e.SourceChunkIDs = append([]string(nil), e.SourceChunkIDs...)
	key := cache.Key(cache.Normalize(query), productID)
	s.t1[key] = e
	s.t1Writes = append(s.t1Writes, tier1Write{key: key, entry: e})
	return nil
}

func (s *fakeStore) PutTier2(_ context.Context, e cache.Tier2Entry, vec []float32) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.enter("PutTier2"); err != nil {
		return err
	}
	e.SourceChunkIDs = append([]string(nil), e.SourceChunkIDs...)
	s.t2 = append(s.t2, tier2Row{entry: e, vec: append([]float32(nil), vec...)})
	s.t2Writes = append(s.t2Writes, e)
	return nil
}

func (s *fakeStore) NearestTier2(_ context.Context, vec []float32, k int) ([]cache.Candidate, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.enter("NearestTier2"); err != nil {
		return nil, err
	}
	return s.nearest(vec, k, func(cache.Tier2Entry) bool { return true }), nil
}

func (s *fakeStore) NearestTier2InNamespace(_ context.Context, vec []float32, namespace string, k int) ([]cache.Candidate, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.enter("NearestTier2InNamespace"); err != nil {
		return nil, err
	}
	if namespace == "" { // never everything (tier2.go)
		return nil, nil
	}
	return s.nearest(vec, k, func(e cache.Tier2Entry) bool { return e.Namespace == namespace }), nil
}

func (s *fakeStore) nearest(vec []float32, k int, keep func(cache.Tier2Entry) bool) []cache.Candidate {
	var out []cache.Candidate
	for _, r := range s.t2 {
		if keep(r.entry) {
			out = append(out, cache.Candidate{Entry: r.entry, Similarity: cosine(vec, r.vec)})
		}
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].Similarity > out[j].Similarity })
	if len(out) > k {
		out = out[:k]
	}
	return out
}

func (s *fakeStore) BumpHitCount(_ context.Context, entryID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.enter("BumpHitCount"); err != nil {
		return err
	}
	s.bumps = append(s.bumps, entryID)
	for i := range s.t2 {
		if s.t2[i].entry.EntryID == entryID {
			s.t2[i].entry.HitCount++
		}
	}
	return nil
}

func (s *fakeStore) Touch(_ context.Context, entryID string, _ int64) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.enter("Touch"); err != nil {
		return err
	}
	s.touches = append(s.touches, entryID)
	return nil
}

// TrimToCapacity records the capacity it was asked to hold and evicts nothing. Eviction itself
// belongs to cache/'s tests; what httpapi owes is passing the configured capacity on every miss.
func (s *fakeStore) TrimToCapacity(_ context.Context, capacity int) ([]cache.EvictedEntry, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.enter("TrimToCapacity"); err != nil {
		return nil, err
	}
	s.trims = append(s.trims, capacity)
	return nil, nil
}

// fail makes method return err on every later call.
func (s *fakeStore) fail(method string, err error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.failing[method] = err
}

func (s *fakeStore) seedTier1(question, productID string, e cache.Entry) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.t1[cache.Key(cache.Normalize(question), productID)] = e
}

func (s *fakeStore) seedTier2(e cache.Tier2Entry, vec []float32) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.t2 = append(s.t2, tier2Row{entry: e, vec: vec})
}

func (s *fakeStore) callCount(method string) int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.calls[method]
}

func (s *fakeStore) injectedCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.injectedReturned
}

func (s *fakeStore) tier1Written() []tier1Write {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]tier1Write(nil), s.t1Writes...)
}

func (s *fakeStore) tier2Written() []cache.Tier2Entry {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]cache.Tier2Entry(nil), s.t2Writes...)
}

func (s *fakeStore) bumped() []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]string(nil), s.bumps...)
}

func (s *fakeStore) touched() []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]string(nil), s.touches...)
}

func (s *fakeStore) trimmedTo() []int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]int(nil), s.trims...)
}

// --- the RAG service, faked at the wire -------------------------------------------------------

// fakeRAG serves the real ragpb service on a loopback listener; ragclient.New takes only a target
// string, so it cannot be handed an in-memory dialer.
//
// It is STRICT (N1): top_k != 0 is an error, and so is an unknown product or chunk. Every such
// violation is also reported when the test ends, so a request that degraded quietly because of one
// still fails the test.
type fakeRAG struct {
	ragpb.UnimplementedRagServiceServer

	mu                   sync.Mutex
	retrieveErr          error
	answerHook           func(ctx context.Context) error
	retrieves            []retrieveCall
	answers              []answerCall
	retrieveErrsReturned int
	violations           []string

	// answerEpoch, when set, is the epoch Answer reports instead of testEpoch. Only the test of
	// which side's epoch reaches the record sets it; everywhere else the two are equal (S6).
	answerEpoch uint64
}

type retrieveCall struct {
	query, productID string
}

type answerCall struct {
	query, productID string
	retrievedIDs     []string
}

func (f *fakeRAG) violate(format string, args ...any) error {
	msg := fmt.Sprintf(format, args...)
	f.mu.Lock()
	f.violations = append(f.violations, msg)
	f.mu.Unlock()
	return status.Error(codes.InvalidArgument, msg)
}

// retrieval is what the service returns for one product: its chunks in rank order, with texts
// POSITIONALLY ALIGNED to chunk_ids, so 1.4 can start reading texts without these tests changing.
func retrieval(p product) *ragpb.RetrieveResponse {
	scores := make([]float32, len(p.texts))
	for i := range scores {
		scores[i] = 0.9 - 0.1*float32(i)
	}
	return &ragpb.RetrieveResponse{
		ChunkIds:     p.chunkIDs(),
		Scores:       scores,
		DatasetEpoch: testEpoch,
		Texts:        append([]string(nil), p.texts...),
	}
}

func (f *fakeRAG) Retrieve(_ context.Context, req *ragpb.RetrieveRequest) (*ragpb.RetrieveResponse, error) {
	f.mu.Lock()
	f.retrieves = append(f.retrieves, retrieveCall{query: req.GetQuery(), productID: req.GetProductId()})
	injected := f.retrieveErr
	if injected != nil {
		f.retrieveErrsReturned++
	}
	f.mu.Unlock()

	if req.GetTopK() != 0 {
		return nil, f.violate("Retrieve sent top_k=%d; the gateway must send 0 (topKServerDefault)", req.GetTopK())
	}
	if injected != nil {
		return nil, injected
	}
	p, ok := corpus[req.GetProductId()]
	if !ok {
		return nil, f.violate("Retrieve for unknown product_id %q", req.GetProductId())
	}
	return retrieval(p), nil
}

func (f *fakeRAG) Answer(req *ragpb.AnswerRequest, stream grpc.ServerStreamingServer[ragpb.AnswerChunk]) error {
	f.mu.Lock()
	f.answers = append(f.answers, answerCall{
		query:        req.GetQuery(),
		productID:    req.GetProductId(),
		retrievedIDs: append([]string(nil), req.GetRetrievedChunkIds()...),
	})
	hook := f.answerHook
	epoch := f.answerEpoch
	f.mu.Unlock()
	if epoch == 0 {
		epoch = testEpoch
	}

	if req.GetTopK() != 0 {
		return f.violate("Answer sent top_k=%d; the gateway must send 0 (topKServerDefault)", req.GetTopK())
	}
	// A hook blocks on its gate OR on this RPC's context, never on the gate alone: grpc's Stop does
	// not wait for handlers, so a hook that ignored the context could outlive the test (S4).
	if hook != nil {
		if err := hook(stream.Context()); err != nil {
			return err
		}
	}

	// Ground on the chunks the gateway handed over; with none, retrieve for itself, as the real
	// service does.
	grounding := req.GetRetrievedChunkIds()
	if len(grounding) == 0 {
		p, ok := corpus[req.GetProductId()]
		if !ok {
			return f.violate("Answer with no chunks for unknown product_id %q", req.GetProductId())
		}
		grounding = p.chunkIDs()
	}
	p, ok := productOfChunk(grounding[0])
	if !ok {
		return f.violate("Answer grounded on unknown chunk %q", grounding[0])
	}
	return stream.Send(&ragpb.AnswerChunk{
		Text:           p.answer,
		Done:           true,
		SourceChunkIds: append([]string(nil), grounding[:len(grounding)-1]...),
		ModelUsed:      testModel,
		DatasetEpoch:   epoch,
	})
}

func (f *fakeRAG) answerAtEpoch(epoch uint64) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.answerEpoch = epoch
}

func (f *fakeRAG) failRetrieve(err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.retrieveErr = err
}

func (f *fakeRAG) onAnswer(hook func(ctx context.Context) error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.answerHook = hook
}

func (f *fakeRAG) retrieveCalls() []retrieveCall {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]retrieveCall(nil), f.retrieves...)
}

func (f *fakeRAG) answerCalls() []answerCall {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]answerCall(nil), f.answers...)
}

func (f *fakeRAG) retrieveFailures() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.retrieveErrsReturned
}

func (f *fakeRAG) violationList() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]string(nil), f.violations...)
}

// --- the embedder, faked at the wire ----------------------------------------------------------

// fakeEmbedder is Ollama's /api/embed. It knows a vector only under the exact input string, with
// the nomic prefix included, and answers anything else with a 500 (N1).
type fakeEmbedder struct {
	mu         sync.Mutex
	vectors    map[string][]float64
	failAll    bool
	calls      int
	failures   int
	violations []string
}

func (e *fakeEmbedder) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Model string   `json:"model"`
		Input []string `json:"input"`
	}
	decodeErr := json.NewDecoder(r.Body).Decode(&body)

	e.mu.Lock()
	e.calls++
	var vec []float64
	var violation string
	switch {
	case r.Method != http.MethodPost || r.URL.Path != "/api/embed":
		violation = fmt.Sprintf("unexpected %s %s", r.Method, r.URL.Path)
	case decodeErr != nil:
		violation = fmt.Sprintf("undecodable body: %v", decodeErr)
	case body.Model != embed.Model:
		violation = fmt.Sprintf("model %q, want %q", body.Model, embed.Model)
	case len(body.Input) != 1:
		violation = fmt.Sprintf("%d inputs, want 1", len(body.Input))
	case e.failAll:
		e.failures++
	default:
		v, ok := e.vectors[body.Input[0]]
		if !ok {
			violation = fmt.Sprintf("unknown input %q", body.Input[0])
		}
		vec = v
	}
	if violation != "" {
		e.violations = append(e.violations, violation)
	}
	e.mu.Unlock()

	if vec == nil {
		http.Error(w, "fake embedder: no vector", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"embeddings": [][]float64{vec}})
}

func (e *fakeEmbedder) learn(question string, vec []float64) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.vectors[nomicQueryPrefix+question] = vec
}

func (e *fakeEmbedder) failEverything() {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.failAll = true
}

func (e *fakeEmbedder) counts() (calls, failures int) {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.calls, e.failures
}

func (e *fakeEmbedder) violationList() []string {
	e.mu.Lock()
	defer e.mu.Unlock()
	return append([]string(nil), e.violations...)
}

// --- the harness ------------------------------------------------------------------------------

type harness struct {
	h        *Handler
	store    *fakeStore
	rag      *fakeRAG
	embedder *fakeEmbedder
	logPath  string

	srv      *grpc.Server
	client   *ragclient.Client
	embedSrv *httptest.Server

	mu        sync.Mutex
	calls     []*call
	gates     []*gate
	nextFresh int
	asks      sync.WaitGroup
}

// newHarness builds one Handler the way cmd/gateway/main.go does, around a fresh cache, RAG
// service, embedder and Logger. Nothing is shared between tests.
func newHarness(t *testing.T, permits, queue int) *harness {
	t.Helper()
	checkFixtures(t)

	hs := &harness{
		store:     newFakeStore(),
		rag:       &fakeRAG{},
		embedder:  &fakeEmbedder{vectors: map[string][]float64{}},
		nextFresh: freshDirections,
	}

	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	hs.srv = grpc.NewServer()
	ragpb.RegisterRagServiceServer(hs.srv, hs.rag)
	go func() { _ = hs.srv.Serve(lis) }()

	hs.client, err = ragclient.New(lis.Addr().String())
	if err != nil {
		hs.srv.Stop()
		t.Fatalf("ragclient: %v", err)
	}
	hs.embedSrv = httptest.NewServer(hs.embedder)

	dir := t.TempDir()
	logger, err := telemetry.Open(dir, testRunID)
	if err != nil {
		t.Fatalf("telemetry: %v", err)
	}
	hs.logPath = filepath.Join(dir, testRunID, "raw", "requests.jsonl")

	hs.h = &Handler{
		Cache:      hs.store,
		RAG:        hs.client,
		Embed:      embed.New(hs.embedSrv.URL, embed.Model),
		Thresholds: reuse.Thresholds{Tau: testTau, Theta: testTheta},
		LaneBand:   reuse.LaneBand{Lo: 0.20, Hi: 0.20},
		Admission:  admission.New(permits, queue),
		Eval:       logger,
		RunID:      testRunID,
		ConfigID:   testConfigID,
		Mutation:   testMutation,
	}

	t.Cleanup(func() { hs.cleanup(t) })
	return hs
}

// cleanup runs in the order design.md §8 fixes. Closing the Logger before the joins would let a
// late Log panic with "send on closed channel" on a test goroutine, which kills the whole binary
// and hides the failure that triggered cleanup.
func (hs *harness) cleanup(t *testing.T) {
	hs.mu.Lock()
	gates := append([]*gate(nil), hs.gates...)
	hs.mu.Unlock()
	for _, g := range gates { // 1. release every blocked hook
		g.open()
	}
	hs.srv.Stop() // 2. cancels every in-flight RPC
	joined := joinWithin(&hs.asks, waitDeadline)
	if !joined { // 3. join every Ask
		t.Errorf("cleanup: an Ask call was still running %v after its hooks were released", waitDeadline)
	}
	_ = hs.client.Close()
	hs.embedSrv.Close() // 4.
	if joined {
		_ = hs.h.Eval.Close() // 5. idempotent: records() may already have closed it
	}

	for _, v := range hs.rag.violationList() {
		t.Errorf("fake RAG service: %s", v)
	}
	for _, v := range hs.embedder.violationList() {
		t.Errorf("fake embedder: %s", v)
	}
}

// embedFresh gives each question its own direction, orthogonal to every other, so none of them
// is similar to anything.
func (hs *harness) embedFresh(questions ...string) {
	hs.mu.Lock()
	defer hs.mu.Unlock()
	for _, q := range questions {
		hs.embedder.learn(q, basis(hs.nextFresh))
		hs.nextFresh++
	}
}

// hitFixture is the Tier-2 entry a question about p would reuse, satisfying EVERY conjunct of the
// fixture rule (design.md §3): p's namespace in the SPEC lane, sources contained in what retrieval
// returns for p, an answer that is a verbatim substring of p's chunk 0, and the shared epoch. A test
// that refuses on one conjunct changes that one field and nothing else.
func hitFixture(p product, question string) cache.Tier2Entry {
	return cache.Tier2Entry{
		EntryID:        cache.NewEntryID(),
		QueryText:      question,
		Answer:         p.answer,
		SourceChunkIDs: p.answerSources(),
		T1Key:          cache.Key(cache.Normalize(question), p.id),
		DatasetEpoch:   testEpoch,
		Namespace:      p.id,
		Lane:           string(reuse.LaneSpec),
	}
}

// seedHit stores hitFixture(p, question) with vector basis(dir). A query embedded as
// toward(dir, ·, hitCos) is a hit.
func (hs *harness) seedHit(p product, question string, dir int) cache.Tier2Entry {
	e := hitFixture(p, question)
	hs.store.seedTier2(e, float32s(basis(dir)))
	return e
}

// gate holds blocked Answer calls until the test opens it. cleanup opens every gate first.
type gate struct {
	ch   chan struct{}
	once sync.Once
}

func (g *gate) open() { g.once.Do(func() { close(g.ch) }) }

// holdAnswers makes every Answer call wait until the returned gate opens, or until its own RPC's
// context ends, whichever comes first.
func (hs *harness) holdAnswers() *gate {
	g := &gate{ch: make(chan struct{})}
	hs.mu.Lock()
	hs.gates = append(hs.gates, g)
	hs.mu.Unlock()
	hs.rag.onAnswer(func(ctx context.Context) error {
		select {
		case <-g.ch:
			return nil
		case <-ctx.Done():
			return ctx.Err()
		}
	})
	return g
}

// --- requests ---------------------------------------------------------------------------------

type askReq struct {
	question  string
	productID string
	ctx       context.Context // nil means a context that is never cancelled
}

type call struct {
	req  askReq
	w    *recordingWriter
	done chan struct{}

	resp map[string]any // the body, when it is a JSON object
	rec  map[string]any // this call's eval record, set by records()
}

// recordingWriter remembers whether Ask wrote anything at all. httptest.ResponseRecorder reports
// 200 for a response nobody wrote, which cannot be told from a real 200 -- and ABANDONED must
// write nothing.
type recordingWriter struct {
	*httptest.ResponseRecorder
	touched bool
}

func (w *recordingWriter) WriteHeader(code int) {
	w.touched = true
	w.ResponseRecorder.WriteHeader(code)
}

func (w *recordingWriter) Write(b []byte) (int, error) {
	w.touched = true
	return w.ResponseRecorder.Write(b)
}

// wroteNothing is "no status, no header, no body".
func (w *recordingWriter) wroteNothing() bool {
	return !w.touched && len(w.Header()) == 0 && w.Body.Len() == 0
}

// start runs one Ask on its own goroutine. Every request sends X-Thesis-Stratum, so every record
// must echo it (S9).
func (hs *harness) start(r askReq) *call {
	body, _ := json.Marshal(map[string]string{"question": r.question, "product_id": r.productID})
	req := httptest.NewRequest(http.MethodPost, "/ask", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Thesis-Stratum", testStratum)
	if r.ctx != nil {
		req = req.WithContext(r.ctx)
	}

	c := &call{req: r, w: &recordingWriter{ResponseRecorder: httptest.NewRecorder()}, done: make(chan struct{})}
	hs.mu.Lock()
	hs.calls = append(hs.calls, c)
	hs.mu.Unlock()

	hs.asks.Add(1)
	go func() {
		defer hs.asks.Done()
		defer close(c.done)
		hs.h.Ask(c.w, req)
	}()
	return c
}

// wait joins the call and decodes its body.
func (c *call) wait(t *testing.T) *call {
	t.Helper()
	select {
	case <-c.done:
	case <-time.After(waitDeadline):
		t.Fatalf("Ask(%q) did not return within %v", c.req.question, waitDeadline)
	}
	var obj map[string]any
	if json.Unmarshal(c.w.Body.Bytes(), &obj) == nil {
		c.resp = obj
	}
	return c
}

// ask runs one Ask to completion.
func (hs *harness) ask(t *testing.T, r askReq) *call {
	t.Helper()
	return hs.start(r).wait(t)
}

// records joins every call, closes the Logger, reads the evaluation log back, matches each record
// to its call, and runs the checks every request gets (S9). Call it once, after the last Ask.
//
// Records are decoded into map[string]any, not telemetry.Record, so that null and 0 stay
// distinguishable.
func (hs *harness) records(t *testing.T) {
	t.Helper()
	if !joinWithin(&hs.asks, waitDeadline) {
		t.Fatalf("an Ask call did not return within %v", waitDeadline)
	}
	if err := hs.h.Eval.Close(); err != nil {
		t.Fatalf("closing the eval log: %v", err)
	}
	recs := readJSONL(t, hs.logPath)

	hs.mu.Lock()
	calls := append([]*call(nil), hs.calls...)
	hs.mu.Unlock()
	for _, c := range calls {
		c.wait(t)
	}

	// The single-exit emit of interfaces.md §H: exactly one record per Ask call, on every path.
	if len(recs) != len(calls) {
		t.Fatalf("%d eval records for %d Ask calls; §H requires exactly one per request", len(recs), len(calls))
	}
	if got := hs.h.Counters.Requests.Load(); got != int64(len(recs)) {
		t.Errorf("Counters.Requests = %d, want %d (one per record)", got, len(recs))
	}

	// Match by the response's request_id where there is one. Otherwise by query_raw, which must
	// then be unambiguous (S3).
	claimed := make([]bool, len(recs))
	byID := map[string]int{}
	for i, r := range recs {
		id, _ := r["request_id"].(string)
		if _, dup := byID[id]; dup {
			t.Fatalf("two eval records share request_id %q", id)
		}
		byID[id] = i
	}
	for _, c := range calls {
		id, ok := c.resp["request_id"].(string)
		if !ok {
			continue
		}
		i, found := byID[id]
		if !found {
			t.Fatalf("Ask(%q) answered with request_id %q, which no eval record carries", c.req.question, id)
		}
		c.rec, claimed[i] = recs[i], true
	}
	for _, c := range calls {
		if c.rec != nil {
			continue
		}
		match := -1
		for i, r := range recs {
			if !claimed[i] && r["query_raw"] == c.req.question {
				if match >= 0 {
					t.Fatalf("Ask(%q) matches more than one unclaimed record; give it a question no other call uses", c.req.question)
				}
				match = i
			}
		}
		if match < 0 {
			t.Fatalf("Ask(%q) has no eval record", c.req.question)
		}
		c.rec, claimed[match] = recs[match], true
	}

	for _, c := range calls {
		hs.checkEveryRecord(t, c)
	}
}

// checkEveryRecord is S9: what every record must carry, whatever path the request took.
func (hs *harness) checkEveryRecord(t *testing.T, c *call) {
	t.Helper()
	rec := c.record(t)
	rec.str("run_id", testRunID)
	rec.number("config_id", testConfigID)
	rec.str("mutation", testMutation)
	rec.str("product_id", c.req.productID)
	rec.str("stratum", testStratum)
	rec.str("query_raw", c.req.question)

	// On a 200: the record's request_id is the join key to the response, and answer_sha256 is the
	// judge's dedupe key. Both must describe what was actually served.
	if c.w.touched && c.w.Code == http.StatusOK {
		resp := c.response(t)
		rec.str("request_id", resp.text("request_id"))
		answer, _ := resp.get("answer").(string)
		sum := sha256.Sum256([]byte(answer))
		rec.str("answer_sha256", hex.EncodeToString(sum[:]))
	}
}

func readJSONL(t *testing.T, path string) []map[string]any {
	t.Helper()
	f, err := os.Open(path)
	if err != nil {
		t.Fatalf("opening the eval log: %v", err)
	}
	defer f.Close()
	var out []map[string]any
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		var m map[string]any
		if err := json.Unmarshal(sc.Bytes(), &m); err != nil {
			t.Fatalf("eval log line is not a JSON object: %v\n%s", err, sc.Bytes())
		}
		out = append(out, m)
	}
	if err := sc.Err(); err != nil {
		t.Fatalf("reading the eval log: %v", err)
	}
	return out
}

func joinWithin(wg *sync.WaitGroup, d time.Duration) bool {
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()
	select {
	case <-done:
		return true
	case <-time.After(d):
		return false
	}
}

// waitFor polls cond until it holds. Expiring the deadline fails the test.
func waitFor(t *testing.T, what string, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(waitDeadline)
	for !cond() {
		if time.Now().After(deadline) {
			t.Fatalf("timed out after %v waiting for %s", waitDeadline, what)
		}
		time.Sleep(time.Millisecond)
	}
}

// --- assertions on decoded JSON ---------------------------------------------------------------

// fields asserts on one decoded JSON object. "null" means the key is present with a null value;
// an absent key is a different thing and fails a null assertion.
type fields struct {
	t    *testing.T
	what string
	m    map[string]any
}

func (c *call) record(t *testing.T) fields {
	t.Helper()
	if c.rec == nil {
		t.Fatalf("Ask(%q): no eval record; call records() first", c.req.question)
	}
	return fields{t: t, what: fmt.Sprintf("record of Ask(%q)", c.req.question), m: c.rec}
}

func (c *call) response(t *testing.T) fields {
	t.Helper()
	if c.resp == nil {
		t.Fatalf("Ask(%q): the response body is not a JSON object: %q", c.req.question, c.w.Body.String())
	}
	return fields{t: t, what: fmt.Sprintf("response to Ask(%q)", c.req.question), m: c.resp}
}

func (f fields) get(key string) any {
	f.t.Helper()
	v, ok := f.m[key]
	if !ok {
		f.t.Fatalf("%s: no %q key", f.what, key)
	}
	return v
}

func (f fields) str(key, want string) {
	f.t.Helper()
	if got := f.get(key); got != want {
		f.t.Errorf("%s: %s = %v, want %q", f.what, key, got, want)
	}
}

func (f fields) number(key string, want float64) {
	f.t.Helper()
	if got := f.get(key); got != want {
		f.t.Errorf("%s: %s = %v, want %v", f.what, key, got, want)
	}
}

func (f fields) boolean(key string, want bool) {
	f.t.Helper()
	if got := f.get(key); got != want {
		f.t.Errorf("%s: %s = %v, want %v", f.what, key, got, want)
	}
}

func (f fields) null(key string) {
	f.t.Helper()
	if got := f.get(key); got != nil {
		f.t.Errorf("%s: %s = %v, want null", f.what, key, got)
	}
}

func (f fields) notNull(key string) {
	f.t.Helper()
	if f.get(key) == nil {
		f.t.Errorf("%s: %s is null", f.what, key)
	}
}

func (f fields) absent(key string) {
	f.t.Helper()
	if v, ok := f.m[key]; ok {
		f.t.Errorf("%s: %s = %v, want the key absent", f.what, key, v)
	}
}

// notTrue accepts an absent key or false. It is for extension fields whose omitempty is a
// serialisation detail, not a contract.
func (f fields) notTrue(key string) {
	f.t.Helper()
	if v := f.m[key]; v == true {
		f.t.Errorf("%s: %s = true", f.what, key)
	}
}

// near asserts a number within tol of want, for values that crossed a float32 narrowing.
func (f fields) near(key string, want, tol float64) {
	f.t.Helper()
	got, ok := f.get(key).(float64)
	if !ok || math.Abs(got-want) > tol {
		f.t.Errorf("%s: %s = %v, want %v ± %v", f.what, key, f.m[key], want, tol)
	}
}

func (f fields) strs(key string, want []string) {
	f.t.Helper()
	raw, ok := f.get(key).([]any)
	if !ok {
		f.t.Errorf("%s: %s = %v, want %q", f.what, key, f.m[key], want)
		return
	}
	got := make([]string, len(raw))
	for i, v := range raw {
		got[i], _ = v.(string)
	}
	if !reflect.DeepEqual(got, want) {
		f.t.Errorf("%s: %s = %q, want %q", f.what, key, got, want)
	}
}

// text returns a string field, failing if it is anything else.
func (f fields) text(key string) string {
	f.t.Helper()
	s, ok := f.get(key).(string)
	if !ok {
		f.t.Fatalf("%s: %s = %v, want a string", f.what, key, f.m[key])
	}
	return s
}
