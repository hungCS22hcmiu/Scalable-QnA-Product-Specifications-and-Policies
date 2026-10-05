package ragclient_test

// The live half of item 1.4: texts flows Python -> Go with positional alignment asserted
// (docs/work/2026-10-05-carry-chunk-text/design.md 3c).
//
// The real ragclient dials a rag.server that `make seam-check` started from the working tree, and
// every texts[i] is compared with the `text` field of corpus::<chunk_ids[i]>, read straight from
// Redis. The oracle shares DATA with the server, not code: a bug in server.py, retrieve.py or the
// client cannot also bend the oracle.
//
// Skipped unless RAG_SEAM_ADDR is set, so `make verify` never needs the live stack. Once it is set,
// anything unreachable is a FAILURE, never a skip. `make seam-check` also fails on a skip, a cached
// result, or no test run at all, because each of those exits 0 here.

import (
	"context"
	"errors"
	"fmt"
	"os"
	"slices"
	"testing"
	"time"

	"github.com/hung/thesis/gateway/internal/ragclient"
	"github.com/redis/go-redis/v9"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// seamDeadline sits above the Python embed timeout (60 s, rag/src/rag/embedding.py): the first
// Retrieve loads nomic-embed-text, and a cold load must not read as a seam fault.
const seamDeadline = 90 * time.Second

// corpusKeyPrefix is the key retrieve.py builds (f"{CORPUS_KEY_PREFIX}:{chunk_id}", with the prefix
// "corpus:"). Hard-coded: neither cache nor catalog owns the corpus key, and importing either from
// ragclient's tests would point the dependency graph the wrong way.
const corpusKeyPrefix = "corpus::"

// The splice case: product-laptops-02's only chunk has no power or watt term, so for this query it
// is expected not to rank naturally, and product scoping must splice it in at index 0
// (retrieve.py _ensure_own_chunk). The test asserts that, rather than assuming it.
const (
	powerQuery   = "what is the power rating of this item exactly right now"
	spliceDoc    = "product-laptops-02"
	spliceChunk  = "product-laptops-02#chunk-0"
	policyQuery  = "can I return an opened item"
	defaultRedis = "redis://localhost:6379/0"
)

// errTextMismatch marks the one failure the shift subtest is looking for. Any other error -- an
// oracle miss, a length mismatch -- would also make a rotated array "fail", for the wrong reason.
var errTextMismatch = errors.New("text does not match the oracle")

// checkAligned is the alignment assertion: same length, at least one element, none empty, and
// texts[i] byte-equal to the oracle's text for ids[i].
func checkAligned(ids, texts []string, oracle func(string) (string, error)) error {
	if len(ids) < 1 || len(texts) != len(ids) {
		return fmt.Errorf("len(texts) = %d, len(chunk_ids) = %d: want equal and >= 1", len(texts), len(ids))
	}
	for i, txt := range texts {
		if txt == "" {
			return fmt.Errorf("texts[%d] (%s) is empty", i, ids[i])
		}
	}
	for i, id := range ids {
		want, err := oracle(id)
		if err != nil {
			return err
		}
		if texts[i] != want {
			return fmt.Errorf("%w: texts[%d] is not the text of %s", errTextMismatch, i, id)
		}
	}
	return nil
}

func TestSeam(t *testing.T) {
	addr := os.Getenv("RAG_SEAM_ADDR")
	if addr == "" {
		t.Skip("set RAG_SEAM_ADDR to a running rag.server -- run `make seam-check`")
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

	rag, err := ragclient.New(addr)
	if err != nil {
		t.Fatalf("ragclient.New(%s): %v", addr, err)
	}
	t.Cleanup(func() { _ = rag.Close() })

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

	retrieve := func(t *testing.T, query, productID string) *ragclient.RetrieveResult {
		t.Helper()
		ctx, cancel := context.WithTimeout(context.Background(), seamDeadline)
		defer cancel()
		// top_k = 0, as the gateway sends: the service resolves it from config.TOP_K.
		r, err := rag.Retrieve(ctx, query, 0, productID)
		if status.Code(err) == codes.DeadlineExceeded || errors.Is(err, context.DeadlineExceeded) {
			t.Fatalf("Retrieve(%q, %q) exceeded %s: a cold embedding load or a seam fault: %v", query, productID, seamDeadline, err)
		}
		if err != nil {
			t.Fatalf("Retrieve(%q, %q): %v", query, productID, err)
		}
		return r
	}

	var l1 *ragclient.RetrieveResult

	t.Run("L1", func(t *testing.T) {
		first := retrieve(t, powerQuery, "")
		// Issued twice: "absent from L1" in L2 must not rest on an untested assumption that the
		// query embedding is bit-identical across calls (design.md U7).
		second := retrieve(t, powerQuery, "")
		if !slices.Equal(first.ChunkIDs, second.ChunkIDs) {
			t.Fatalf("unscoped retrieval is not stable across calls: %v then %v", first.ChunkIDs, second.ChunkIDs)
		}
		if err := checkAligned(first.ChunkIDs, first.Texts, oracle); err != nil {
			t.Fatal(err)
		}
		t.Logf("L1: %d chunks %v", len(first.ChunkIDs), first.ChunkIDs)
		l1 = first
	})

	t.Run("L2", func(t *testing.T) {
		if l1 == nil {
			t.Fatal("L1 did not complete; the splice cannot be shown to fire without it")
		}
		r := retrieve(t, powerQuery, spliceDoc)
		if err := checkAligned(r.ChunkIDs, r.Texts, oracle); err != nil {
			t.Fatal(err)
		}
		if slices.Contains(l1.ChunkIDs, spliceChunk) {
			t.Fatalf("%s ranks naturally for %q, so the splice never fires; choose another pair (design.md U2)", spliceChunk, powerQuery)
		}
		if r.ChunkIDs[0] != spliceChunk {
			t.Fatalf("scoped chunk_ids[0] = %s, want the spliced %s", r.ChunkIDs[0], spliceChunk)
		}
		t.Logf("L2: splice fired, %d chunks %v", len(r.ChunkIDs), r.ChunkIDs)
	})

	t.Run("L3", func(t *testing.T) {
		r := retrieve(t, policyQuery, "")
		if err := checkAligned(r.ChunkIDs, r.Texts, oracle); err != nil {
			t.Fatal(err)
		}
		t.Logf("L3: %d chunks %v", len(r.ChunkIDs), r.ChunkIDs)
	})

	t.Run("shift", func(t *testing.T) {
		if l1 == nil {
			t.Fatal("L1 did not complete; nothing to shift")
		}
		if len(l1.Texts) < 2 {
			t.Fatalf("L1 has %d texts; a shift needs at least 2", len(l1.Texts))
		}
		seen := make(map[string]string, len(l1.Texts))
		for i, txt := range l1.Texts {
			if prev, dup := seen[txt]; dup {
				t.Fatalf("%s and %s share a text, so a rotation could match by accident", prev, l1.ChunkIDs[i])
			}
			seen[txt] = l1.ChunkIDs[i]
		}
		rotated := append(slices.Clone(l1.Texts[1:]), l1.Texts[0])
		if err := checkAligned(l1.ChunkIDs, rotated, oracle); !errors.Is(err, errTextMismatch) {
			t.Fatalf("checkAligned on texts rotated by one returned %v; the checker cannot see a shift", err)
		}
	})
}
