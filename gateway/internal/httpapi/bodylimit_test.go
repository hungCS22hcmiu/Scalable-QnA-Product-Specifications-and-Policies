package httpapi

// Tests for the request-size cap on /ask (super-plan item 5.5; docs/work/2026-11-12-ask-body-limit/).
// The limit is 8,192 bytes (interfaces.md §A v0.36). It is written here as a literal, not read from
// maxAskBody, so that changing the constant fails these tests instead of moving them.
//
// A refused request must leave nothing behind: no record, no counter, no retrieval, no generation.
// The over-the-limit tests check all four. The real-HTTP test exists because httptest.NewRequest does
// not run net/http's own body handling (design.md §3, failure mode 5).

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

const askBodyLimit = 8192

// askBodyOf is the body the harness sends for one request: json.Marshal of a map, as hs.start builds it.
func askBodyOf(t *testing.T, question, productID string) []byte {
	t.Helper()
	body, err := json.Marshal(map[string]string{"question": question, "product_id": productID})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return body
}

// questionForBody pads a question with "a" so that the body hs.start sends for it is exactly n bytes.
// It fails the test if it cannot.
func questionForBody(t *testing.T, n int, productID string) string {
	t.Helper()
	pad := n - len(askBodyOf(t, "", productID))
	if pad < 1 {
		t.Fatalf("cannot build a body of %d bytes for product_id %q: the empty question already takes %d",
			n, productID, len(askBodyOf(t, "", productID)))
	}
	q := strings.Repeat("a", pad)
	if got := len(askBodyOf(t, q, productID)); got != n {
		t.Fatalf("built a body of %d bytes, want %d", got, n)
	}
	return q
}

// paddedObject is a small valid /ask object followed by spaces, n bytes in all. json.Decoder stops at the
// end of the object, so only a read of the rest of the body can see the padding (failure mode 1).
func paddedObject(t *testing.T, n int) []byte {
	t.Helper()
	obj := askBodyOf(t, "How long is the warranty?", kettle.id)
	if n <= len(obj) {
		t.Fatalf("body of %d bytes is no longer than the object (%d)", n, len(obj))
	}
	return append(obj, bytes.Repeat([]byte(" "), n-len(obj))...)
}

// checkRefusedBeforeAnyRecord is every check a 413 gets: the status, a reply that names the limit, and then
// that no record, no counter, no retrieval and no generation came from the request.
func (hs *harness) checkRefusedBeforeAnyRecord(t *testing.T, w *httptest.ResponseRecorder) {
	t.Helper()
	if w.Code != http.StatusRequestEntityTooLarge {
		t.Errorf("status %d, want 413: %s", w.Code, w.Body)
	}
	if !strings.Contains(w.Body.String(), "8192") {
		t.Errorf("reply %q does not name the limit 8192", w.Body.String())
	}
	if err := hs.h.Eval.Close(); err != nil {
		t.Fatalf("closing the eval log: %v", err)
	}
	if recs := readJSONL(t, hs.logPath); len(recs) != 0 {
		t.Errorf("%d eval records for a refused request, want 0", len(recs))
	}
	if n := hs.h.Counters.Requests.Load(); n != 0 {
		t.Errorf("Counters.Requests = %d, want 0", n)
	}
	if calls := hs.rag.retrieveCalls(); len(calls) != 0 {
		t.Errorf("Retrieve ran %d time(s) for a refused request", len(calls))
	}
	if calls := hs.rag.answerCalls(); len(calls) != 0 {
		t.Errorf("Answer ran %d time(s) for a refused request", len(calls))
	}
}

// DC 1. A valid body of 8,193 bytes: one over.
func TestAskRefusesABodyOverTheLimit(t *testing.T) {
	hs := newHarness(t, 1, 0)
	q := questionForBody(t, askBodyLimit+1, kettle.id)
	body := askBodyOf(t, q, kettle.id)

	w := httptest.NewRecorder()
	hs.h.Ask(w, httptest.NewRequest(http.MethodPost, "/ask", bytes.NewReader(body)))
	hs.checkRefusedBeforeAnyRecord(t, w)
}

// DC 1. The silent case: Decode stops at the end of the object, so the padding after it is only seen by
// the read of the rest of the body.
func TestAskRefusesAnObjectFollowedByPaddingOverTheLimit(t *testing.T) {
	hs := newHarness(t, 1, 0)
	body := paddedObject(t, askBodyLimit+1)

	// No declared length (as a chunked request has), so the length check cannot catch it: only reading the
	// rest of the body after the object can (plan Phase 6, a mutation check showed this test passed without it).
	req := httptest.NewRequest(http.MethodPost, "/ask", bytes.NewReader(body))
	req.ContentLength = -1

	w := httptest.NewRecorder()
	hs.h.Ask(w, req)
	hs.checkRefusedBeforeAnyRecord(t, w)
}

// countingBody counts the reads and the bytes a handler takes from it.
type countingBody struct {
	r     io.Reader
	reads int
	bytes int
}

func (c *countingBody) Read(p []byte) (int, error) {
	c.reads++
	n, err := c.r.Read(p)
	c.bytes += n
	return n, err
}

// DC 1. A declared Content-Length over the limit is refused before a byte is read.
func TestAskRefusesADeclaredLengthOverTheLimit(t *testing.T) {
	hs := newHarness(t, 1, 0)
	body := &countingBody{r: bytes.NewReader(askBodyOf(t, "How long is the warranty?", kettle.id))}
	req := httptest.NewRequest(http.MethodPost, "/ask", body)
	req.ContentLength = askBodyLimit + 1

	w := httptest.NewRecorder()
	hs.h.Ask(w, req)
	hs.checkRefusedBeforeAnyRecord(t, w)
	if body.reads != 0 || body.bytes != 0 {
		t.Errorf("the handler read the body (%d reads, %d bytes); a declared length over the limit is refused first",
			body.reads, body.bytes)
	}
}

// DC 2. Exactly at the limit, and one under it, are served.
func TestAskServesABodyAtTheLimit(t *testing.T) {
	hs := newHarness(t, 1, 0)
	for _, n := range []int{askBodyLimit, askBodyLimit - 1} {
		q := questionForBody(t, n, kettle.id)
		hs.embedFresh(q)
		c := hs.ask(t, askReq{question: q, productID: kettle.id})
		if c.w.Code != http.StatusOK {
			t.Fatalf("body of %d bytes: status %d, want 200: %.200s", n, c.w.Code, c.w.Body)
		}
		c.response(t).str("cache", "MISS")
	}
	hs.records(t)
}

// seenByServer is what the real server reported about each request it handed to Ask.
type seenByServer struct {
	mu       sync.Mutex
	lengths  []int64
	chunked  []bool
	statuses []int
}

// DC 3. The same limits over a real connection, with a Content-Length and chunked (no length).
func TestAskBodyLimitOverRealHTTP(t *testing.T) {
	hs := newHarness(t, 1, 0)
	seen := &seenByServer{}
	// The wrapper only records what the server saw, then calls Ask. It exists so the test can prove a
	// "chunked" request really reached the handler without a length.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen.mu.Lock()
		seen.lengths = append(seen.lengths, r.ContentLength)
		seen.chunked = append(seen.chunked, len(r.TransferEncoding) == 1 && r.TransferEncoding[0] == "chunked")
		seen.mu.Unlock()
		hs.h.Ask(w, r)
	}))
	t.Cleanup(srv.Close)

	post := func(t *testing.T, body []byte, chunked bool) int {
		t.Helper()
		var rd io.Reader = bytes.NewReader(body)
		if chunked {
			rd = io.MultiReader(rd) // an unknown reader type: net/http cannot know its length
		}
		req, err := http.NewRequest(http.MethodPost, srv.URL, rd)
		if err != nil {
			t.Fatalf("new request: %v", err)
		}
		if chunked {
			req.ContentLength = -1 // unknown, so the client sends Transfer-Encoding: chunked
			if req.ContentLength != -1 {
				t.Fatalf("req.ContentLength = %d, want -1", req.ContentLength)
			}
		} else if req.ContentLength != int64(len(body)) {
			t.Fatalf("req.ContentLength = %d, want %d", req.ContentLength, len(body))
		}
		req.Header.Set("Content-Type", "application/json")
		resp, err := srv.Client().Do(req)
		if err != nil {
			t.Fatalf("post of %d bytes (chunked=%v): %v", len(body), chunked, err)
		}
		defer resp.Body.Close()
		reply, _ := io.ReadAll(resp.Body)
		seen.mu.Lock()
		seen.statuses = append(seen.statuses, resp.StatusCode)
		seen.mu.Unlock()
		t.Logf("%d bytes, chunked=%v -> %d %s", len(body), chunked, resp.StatusCode, strings.TrimSpace(string(reply)))
		return resp.StatusCode
	}

	over := askBodyOf(t, questionForBody(t, askBodyLimit+1, kettle.id), kettle.id)
	padded := paddedObject(t, askBodyLimit+1)
	atLimitQ := questionForBody(t, askBodyLimit, kettle.id)
	atLimit := askBodyOf(t, atLimitQ, kettle.id)

	if got := post(t, over, false); got != http.StatusRequestEntityTooLarge {
		t.Errorf("8193 bytes with a length: status %d, want 413", got)
	}
	if got := post(t, over, true); got != http.StatusRequestEntityTooLarge {
		t.Errorf("8193 bytes chunked: status %d, want 413", got)
	}
	if got := post(t, padded, true); got != http.StatusRequestEntityTooLarge {
		t.Errorf("padded object chunked: status %d, want 413", got)
	}
	hs.embedFresh(atLimitQ)
	if got := post(t, atLimit, false); got != http.StatusOK {
		t.Errorf("8192 bytes: status %d, want 200", got)
	}

	seen.mu.Lock()
	defer seen.mu.Unlock()
	wantLen := []int64{askBodyLimit + 1, -1, -1, askBodyLimit}
	wantChunked := []bool{false, true, true, false}
	if len(seen.lengths) != len(wantLen) {
		t.Fatalf("the server saw %d requests, want %d", len(seen.lengths), len(wantLen))
	}
	for i := range wantLen {
		if seen.lengths[i] != wantLen[i] || seen.chunked[i] != wantChunked[i] {
			t.Errorf("request %d reached the handler with ContentLength %d, chunked=%v; want %d, %v",
				i+1, seen.lengths[i], seen.chunked[i], wantLen[i], wantChunked[i])
		}
	}
}

// The new check must not turn a malformed small body into a 413. These are the same causes as
// TestRejectsBadMethodAndBody and TestRejectsMissingProductID, with 413 ruled out.
func TestAskStillSays400ForSmallMalformedBodies(t *testing.T) {
	hs := newHarness(t, 1, 0)
	for _, tc := range []struct{ name, body string }{
		{"invalid JSON", `{"question": `},
		{"empty question", `{"question": "", "product_id": "` + kettle.id + `"}`},
		{"blank product_id", `{"question": "how long is the warranty?", "product_id": "   "}`},
	} {
		t.Run(tc.name, func(t *testing.T) {
			w := httptest.NewRecorder()
			hs.h.Ask(w, httptest.NewRequest(http.MethodPost, "/ask", strings.NewReader(tc.body)))
			if w.Code != http.StatusBadRequest {
				t.Errorf("status %d, want 400: %s", w.Code, w.Body)
			}
		})
	}
	if n := len(hs.rag.retrieveCalls()); n != 0 {
		t.Errorf("Retrieve ran %d time(s) for a refused request", n)
	}
}
