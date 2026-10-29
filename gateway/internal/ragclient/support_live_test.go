package ragclient_test

// The live half of item 2.1 (docs/work/2026-10-10-support-gate-lexical-arm/plan.md, step 8b):
// the lexical support gate fed with text that really came out of the running retrieval service.
// Moved from the retired dev-v0 corpus to v1 on 2026-10-29 (docs/work/2026-10-29-dev-v0-live-checks/).
//
// reuse's own tests prove the formula on fixture strings transcribed from data/dev-v0, and they stay
// on dev-v0. This test proves two things they cannot:
//
//  1. fidelity -- the text Redis holds for each pinned chunk hashes to the checksum recorded in
//     this file. The pinned chunks are the four v1 chunks the two scoped retrievals below return;
//     reuse's dev-v0 fixtures are no longer pinned here. Redis is the oracle, read straight from
//     the corpus index, and shares DATA with the server, not code, as TestSeam's oracle does.
//  2. the seam, end to end -- two retrievals through the real ragclient, texts aligned with
//     chunk_ids (checkAligned), then reuse.SupportLexical on the result.
//
// Two guards make a corpus switch fail loudly instead of passing empty. A preflight fails with "pin
// absent" if a pinned chunk is missing from Redis. And each query subtest fails if its scoped
// retrieval holds no chunk of supportProduct: an unknown product_id raises no error anywhere,
// scoping drops every other product's chunk, and the policy chunks that remain would still be scored.
//
// WHAT A PASS MEANS, and what it does not. A pass means: the corpus text in Redis is the text the
// pinned checksums were taken from; the real service returned aligned texts for both queries, each
// holding a chunk of supportProduct; and SupportLexical scored both of them (Scored, 22 content
// tokens). It does NOT mean the gate refused the warranty query or admitted the paraphrase: the
// verdicts are LOGGED, not asserted (item 2.1's choice, kept). Both queries are product-scoped, and
// a scoped retrieval drops every other product's chunk (retrieve.py _drop_other_products), so it
// cannot return lane_test.go's pinned 5-chunk sets, which are dev-v0's and contain products 04, 09
// and 01/02. A comparison against those sets could never fire, so there is none. The verdicts
// observed on v1 on 2026-10-29 (not predicted, not pinned): the paraphrase query retrieved
// [product-electronics-b07wnp64zn#chunk-0, policy-return-electronics#chunk-0,
// policy-return-phones-opened#chunk-0] and scored 0.9545 (ADMITS); the warranty query retrieved
// [product-electronics-b07wnp64zn#chunk-0, policy-warranty-electronics#chunk-0] and scored 0.4091
// (REFUSES).
//
// It is NOT a measurement and NOT a request to /ask: the gate is not wired into the cascade
// (spec.md, Out of scope), so /ask cannot exercise it. The 2026-09-06 queries behind lane_test.go's
// chunk-ID sets were never recorded. The two queries below keep the dev-v0 wording and swap only
// the product name. They were written before any v1 probe ran
// (docs/work/2026-10-29-dev-v0-live-checks/evidence/rca/preregistered-candidates.txt) and must not
// be edited to make retrieval land on any set or any verdict. An unscoped variant would be a plan
// change.
//
// This test imports reuse, which reuse's isolation allows: reuse imports nothing, so it stays a
// leaf; the new edge is test-time only and points from ragclient_test to reuse.
//
// Skipped unless RAG_SEAM_ADDR is set, so `make verify` never needs the live stack. Once it is set,
// anything unreachable is a FAILURE, never a skip. Run it with `make support-check`, which fails on
// a skip, a cached result, or no test run at all. Redis is touched read-only (HGet).

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"maps"
	"os"
	"slices"
	"strings"
	"testing"

	"github.com/hung/thesis/gateway/internal/ragclient"
	"github.com/hung/thesis/gateway/internal/reuse"
	"github.com/redis/go-redis/v9"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// supportProduct scopes both retrievals, as the gateway does for a request that names a product.
const supportProduct = "product-electronics-b07wnp64zn"

// The two queries: the dev-v0 wording from plan.md step 8b with only the product name changed,
// written before any v1 probe ran.
const (
	supportParaphraseQuery = "How long is the battery on the REETEC wireless headphones, and how many days do I have to return them?"
	supportWarrantyQuery   = "How long is the battery on the REETEC wireless headphones, and what does the warranty cover?"
)

// supportCachedAnswer is authored, not captured: two facts from the product's chunk-0 (a 500 mAh
// battery, up to 20 hours of playing time) and the wording of policy-return-electronics#chunk-0.
// It is no longer reuse/support_test.go's cachedAnswer. That offline fixture stays on dev-v0, so the
// two files share nothing and the checksum link between them is cut. The checksum below catches an
// edit to THIS copy.
const supportCachedAnswer = "The REETEC wireless headphones have a 500 mAh battery with up to 20 hours of playing time. " +
	"Headphones can be sent back within 30 days of the day you received them for a full refund or an exchange."

const supportCachedAnswerSHA = "197de3fd39ab"

// supportFixtureSHA are the checksums of the four v1 chunks the two scoped retrievals return (the
// product's chunk-0 and three policy chunks), keyed by the chunk ID whose Redis text must match.
// They replace the seven dev-v0 fixture checksums.
var supportFixtureSHA = map[string]string{
	"product-electronics-b07wnp64zn#chunk-0": "83620a1dfec3",
	"policy-return-electronics#chunk-0":      "9a28b8462d8e",
	"policy-return-phones-opened#chunk-0":    "7cda127b39db",
	"policy-warranty-electronics#chunk-0":    "7d2a986e2099",
}

// supportContentTokens is |content-tokens(supportCachedAnswer)|: it depends on the answer alone, so
// it guards the tokenizer and the copy of the answer, not the retrieval.
const supportContentTokens = 22

func sha12(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])[:12]
}

func TestSupportLive(t *testing.T) {
	addr := os.Getenv("RAG_SEAM_ADDR")
	if addr == "" {
		t.Skip("set RAG_SEAM_ADDR to a running rag.server -- run `make support-check`")
	}
	if got := sha12(supportCachedAnswer); got != supportCachedAnswerSHA {
		t.Fatalf("supportCachedAnswer sha256 prefix %s, want %s: drifted from the answer recorded in this file", got, supportCachedAnswerSHA)
	}

	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = defaultRedis
	}
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		t.Fatalf("REDIS_URL %q: %v", redisURL, err)
	}
	if opt.DB != 0 {
		t.Fatalf("REDIS_URL selects DB %d; the corpus index lives in DB 0", opt.DB)
	}
	// Read-only: HGet is the only command this test issues. DB 0 holds the corpus and the dev
	// cache, so nothing here may write or flush.
	rdb := redis.NewClient(opt)
	t.Cleanup(func() { _ = rdb.Close() })
	if err := rdb.Ping(context.Background()).Err(); err != nil {
		t.Fatalf("redis unreachable at %s: %v", redisURL, err)
	}
	oracle := func(id string) (string, error) {
		// .Result(), not .Val(): Val() turns a missing key into "", and "" == "" would pass.
		txt, err := rdb.HGet(context.Background(), corpusKeyPrefix+id, "text").Result()
		if errors.Is(err, redis.Nil) {
			return "", fmt.Errorf("oracle: no text at %s%s", corpusKeyPrefix, id)
		}
		if err != nil {
			return "", fmt.Errorf("oracle: %s%s: %w", corpusKeyPrefix, id, err)
		}
		return txt, nil
	}

	rag, err := ragclient.New(addr)
	if err != nil {
		t.Fatalf("ragclient.New(%s): %v", addr, err)
	}
	t.Cleanup(func() { _ = rag.Close() })

	// Preflight: every pinned chunk must exist in this corpus. Otherwise a corpus switch shows up
	// as a run of "oracle: no text" lines in fidelity. The product's own chunk is checked by name,
	// so changing supportProduct alone still trips it. HGet only, through the oracle, so the
	// read-only claim above stays true.
	for _, id := range append(slices.Sorted(maps.Keys(supportFixtureSHA)), supportProduct+"#chunk-0") {
		if _, err := oracle(id); err != nil {
			t.Fatalf("pin absent: %v -- this check is pinned to the v1 corpus; was the corpus switched?", err)
		}
	}

	t.Run("fidelity", func(t *testing.T) {
		// Does the text in the corpus index equal the text the fixture was built from? It assumes
		// Redis stores ingest.py's product_to_text / policy_to_text output byte for byte; a chunker
		// that altered whitespace would fail here, and that is a finding about the fixture, not a
		// reason to loosen this comparison.
		for _, id := range slices.Sorted(maps.Keys(supportFixtureSHA)) {
			txt, err := oracle(id)
			if err != nil {
				t.Errorf("%v", err)
				continue
			}
			if got, want := sha12(txt), supportFixtureSHA[id]; got != want {
				t.Errorf("%s: Redis text sha256 prefix %s, fixture recorded %s", id, got, want)
			}
		}
	})

	retrieve := func(t *testing.T, query string) *ragclient.RetrieveResult {
		t.Helper()
		ctx, cancel := context.WithTimeout(context.Background(), seamDeadline)
		defer cancel()
		// top_k = 0, as the gateway sends: the service resolves it from config.TOP_K.
		r, err := rag.Retrieve(ctx, query, 0, supportProduct)
		if status.Code(err) == codes.DeadlineExceeded || errors.Is(err, context.DeadlineExceeded) {
			t.Fatalf("Retrieve(%q, %q) exceeded %s: a cold embedding load or a seam fault: %v", query, supportProduct, seamDeadline, err)
		}
		if err != nil {
			t.Fatalf("Retrieve(%q, %q): %v", query, supportProduct, err)
		}
		return r
	}

	for _, c := range []struct{ name, query string }{
		{"paraphrase-query", supportParaphraseQuery},
		{"warranty-query", supportWarrantyQuery},
	} {
		t.Run(c.name, func(t *testing.T) {
			r := retrieve(t, c.query)
			if err := checkAligned(r.ChunkIDs, r.Texts, oracle); err != nil {
				t.Fatal(err)
			}
			// The scoped product must be in the retrieval. Without this, a corpus that lacks the
			// product still passes: scoping drops every other product's chunk, the policy chunks
			// stay, and SupportLexical scores them.
			if !slices.ContainsFunc(r.ChunkIDs, func(id string) bool { return strings.HasPrefix(id, supportProduct+"#") }) {
				t.Fatalf("no %s chunk in the scoped retrieval %v: the product is absent from the corpus, or scoping is broken", supportProduct, r.ChunkIDs)
			}
			v := reuse.SupportLexical(supportCachedAnswer, r.Texts, r.ChunkIDs)
			if !v.Scored {
				t.Fatalf("a retrieval with %d aligned texts came back unscored: %+v", len(r.Texts), v)
			}
			if v.ContentTokenCount != supportContentTokens {
				t.Errorf("ContentTokenCount = %d, want %d (the answer is the same on every call)", v.ContentTokenCount, supportContentTokens)
			}
			// Logged, not asserted: see the header, "WHAT A PASS MEANS".
			verdict := "ADMITS"
			if v.Refuses() {
				verdict = "REFUSES"
			}
			t.Logf("live chunk IDs %v", r.ChunkIDs)
			t.Logf("S_lex = %.4f over %d content tokens: the gate %s (tau_s = %.2f) -- logged, not asserted", v.Score, v.ContentTokenCount, verdict, reuse.TauSupportLexical)
		})
	}
}
