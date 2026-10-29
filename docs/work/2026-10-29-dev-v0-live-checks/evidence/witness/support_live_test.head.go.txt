package ragclient_test

// The live half of item 2.1 (docs/work/2026-10-10-support-gate-lexical-arm/plan.md, step 8b):
// the lexical support gate fed with text that really came out of the running retrieval service.
//
// reuse's own tests prove the formula on fixture strings I transcribed from data/dev-v0. This test
// proves two things they cannot:
//
//  1. fidelity -- the text Redis holds for each fixture chunk hashes to the checksum recorded for the
//     fixture literal (design.md, "The pinned fixture"). Redis is the oracle, read straight from
//     the corpus index, and shares DATA with the server, not code, as TestSeam's oracle does.
//  2. the seam, end to end -- two retrievals through the real ragclient, texts aligned with
//     chunk_ids (checkAligned), then reuse.SupportLexical on the result.
//
// WHAT A PASS MEANS, and what it does not. A pass means: the corpus text in Redis is the text the
// fixture was built from; the real service returned aligned texts for both queries; and
// SupportLexical scored both of them (Scored, 16 content tokens). It does NOT mean the gate refused
// the warranty query or admitted the paraphrase: the verdicts are LOGGED, not asserted. Both
// queries are product-scoped, and a scoped retrieval drops every other product's chunk
// (retrieve.py _drop_other_products), so it cannot return lane_test.go's pinned 5-chunk sets, which
// contain products 04, 09 and 01/02. A comparison against those sets could never fire, so there is
// none. The verdicts observed on 2026-10-12 (not predicted, not pinned): the paraphrase query
// retrieved [product-headphones-03, policy-returns-electronics] and scored 0.8750; the warranty query
// retrieved [product-headphones-03, policy-warranty] and scored 0.3125.
//
// It is NOT a measurement and NOT a request to /ask: the gate is not wired into the cascade
// (spec.md, Out of scope), so /ask cannot exercise it. The 2026-09-06 queries behind lane_test.go's
// chunk-ID sets were never recorded. The two queries below were fixed in plan.md BEFORE anything
// ran and must not be edited to make retrieval land on any set or any verdict. An unscoped variant
// would be a plan change.
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
	"testing"

	"github.com/hung/thesis/gateway/internal/ragclient"
	"github.com/hung/thesis/gateway/internal/reuse"
	"github.com/redis/go-redis/v9"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// supportProduct scopes both retrievals, as the gateway does for a request that names a product.
const supportProduct = "product-headphones-03"

// The two queries, fixed in plan.md step 8b before this test was ever run.
const (
	supportParaphraseQuery = "How long is the battery on the EarBuds Pop 3, and how many days do I have to return it?"
	supportWarrantyQuery   = "How long is the battery on the EarBuds Pop 3, and what does the warranty cover?"
)

// supportCachedAnswer is reuse/support_test.go's cachedAnswer, byte for byte. It is authored, not
// captured (see the note there). The checksum below catches an edit to THIS copy. It cannot catch
// the other copy being edited together with its own checksum: the two files share no code (a test
// file's names are not importable), so the same 12 hex digits are kept in both by hand. The seven
// chunk checksums below are duplicated the same way.
const supportCachedAnswer = "The EarBuds Pop 3 has 6 hours of battery life, 24 hours with the case. " +
	"Return it within the 30-day return window for a full refund if unused and in original packaging."

const supportCachedAnswerSHA = "b213e5a99fb4"

// supportFixtureSHA are design.md's checksums for the seven fixture chunks, keyed by the chunk ID
// whose Redis text must match.
var supportFixtureSHA = map[string]string{
	"product-headphones-01#chunk-0":      "82b972cc13fa",
	"product-headphones-02#chunk-0":      "4bbdd773b369",
	"product-headphones-03#chunk-0":      "c42b901cdd3b",
	"product-headphones-04#chunk-0":      "d9f62f2671ec",
	"product-headphones-09#chunk-0":      "60cc39d00c83",
	"policy-returns-electronics#chunk-0": "4fc52aed4784",
	"policy-warranty#chunk-0":            "c776d676652d",
}

// supportContentTokens is |content-tokens(supportCachedAnswer)|: it depends on the answer alone, so
// it guards the tokenizer and the copy of the answer, not the retrieval.
const supportContentTokens = 16

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
		t.Fatalf("supportCachedAnswer sha256 prefix %s, want %s: drifted from reuse/support_test.go's cachedAnswer", got, supportCachedAnswerSHA)
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
