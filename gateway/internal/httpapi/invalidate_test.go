package httpapi

// Item 4.4, done condition 4 (the HTTP half): POST /invalidate, driven with a fake invalidator. No Redis:
// that the purge finishes before InvalidateWait returns belongs to deps/'s tests; what httpapi owes is
// the status codes, the refusals that purge nothing, and the reply that carries the purge result.

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/hung/thesis/gateway/internal/deps"
)

// fakeInvalidator records every call and answers with the result or error it was given.
type fakeInvalidator struct {
	mu     sync.Mutex
	events []deps.Event
	result deps.PurgeResult
	err    error
}

var _ invalidator = (*fakeInvalidator)(nil)

func (f *fakeInvalidator) InvalidateWait(_ context.Context, ev deps.Event) (deps.PurgeResult, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.events = append(f.events, ev)
	return f.result, f.err
}

func (f *fakeInvalidator) calls() []deps.Event {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]deps.Event(nil), f.events...)
}

const goodInvalidateBody = `{"chunk_id":"policy-return#c0","doc_id":"policy-return","change_type":"substantive",` +
	`"new_text":"Returns are accepted within 14 days.","dataset_version":"v1","ts":"2026-10-29T10:00:00Z"}`

// invalidateOnce sends one request to a handler that has inv, and returns the recorder.
func invalidateOnce(inv invalidator, method, remoteAddr, body string) *httptest.ResponseRecorder {
	h := &Handler{Invalidator: inv}
	req := httptest.NewRequest(method, "/invalidate", strings.NewReader(body))
	req.RemoteAddr = remoteAddr
	rec := httptest.NewRecorder()
	h.Invalidate(rec, req)
	return rec
}

func TestInvalidateEndpointRepliesWithThePurgeResult(t *testing.T) {
	fake := &fakeInvalidator{result: deps.PurgeResult{ChunkID: "policy-return#c0", Purged: []string{"e1", "e2"}}}
	rec := invalidateOnce(fake, http.MethodPost, "127.0.0.1:5000", goodInvalidateBody)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200; body %s", rec.Code, rec.Body.String())
	}
	var got struct {
		ChunkID string   `json:"chunk_id"`
		Purged  []string `json:"purged"`
		Failed  []string `json:"failed"`
		Errors  []string `json:"errors"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatalf("the reply is not JSON: %v: %s", err, rec.Body.String())
	}
	if got.ChunkID != "policy-return#c0" || !reflect.DeepEqual(got.Purged, []string{"e1", "e2"}) {
		t.Fatalf("reply = %+v, want chunk policy-return#c0 and purged [e1 e2]", got)
	}
	// An empty list prints as [], never null: a client that reads "failed" must get a list.
	if got.Failed == nil || got.Errors == nil || len(got.Failed)+len(got.Errors) != 0 {
		t.Fatalf("failed = %#v, errors = %#v; want two empty lists", got.Failed, got.Errors)
	}
	if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
		t.Fatalf("Content-Type = %q, want application/json", ct)
	}

	calls := fake.calls()
	if len(calls) != 1 {
		t.Fatalf("InvalidateWait was called %d times, want 1", len(calls))
	}
	want := deps.Event{
		ChunkID: "policy-return#c0", DocID: "policy-return", ChangeType: "substantive",
		NewText: "Returns are accepted within 14 days.", DatasetVersion: "v1",
		TS: time.Date(2026, 10, 29, 10, 0, 0, 0, time.UTC),
	}
	if !calls[0].TS.Equal(want.TS) {
		t.Fatalf("ts = %v, want %v", calls[0].TS, want.TS)
	}
	calls[0].TS = want.TS // Equal above; DeepEqual below compares the rest
	if !reflect.DeepEqual(calls[0], want) {
		t.Fatalf("the event that reached the invalidator = %+v, want %+v", calls[0], want)
	}
}

func TestInvalidateEndpointFailedPurgeIs500(t *testing.T) {
	cases := map[string]deps.PurgeResult{
		"a failed entry":    {ChunkID: "c", Purged: []string{"e1"}, Failed: []string{"e2"}},
		"a failed SREM":     {ChunkID: "c", Purged: []string{"e1"}, Errors: []string{"srem failed"}},
		"the purge errored": {},
	}
	for name, res := range cases {
		t.Run(name, func(t *testing.T) {
			fake := &fakeInvalidator{result: res}
			if name == "the purge errored" {
				fake.err = errors.New("redis is down")
			}
			rec := invalidateOnce(fake, http.MethodPost, "[::1]:5000", goodInvalidateBody)
			if rec.Code != http.StatusInternalServerError {
				t.Fatalf("status = %d, want 500; body %s", rec.Code, rec.Body.String())
			}
			var got invalidateResponse
			if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
				t.Fatalf("a 500 still replies with the purge result as JSON: %v: %s", err, rec.Body.String())
			}
			if name == "a failed entry" && !reflect.DeepEqual(got.Failed, []string{"e2"}) {
				t.Fatalf("failed = %v, want [e2]: the caller must learn which entry failed", got.Failed)
			}
			if name == "the purge errored" && len(got.Errors) != 1 {
				t.Fatalf("errors = %v, want the error text", got.Errors)
			}
		})
	}
}

func TestInvalidateEndpointRefusesNonLoopback(t *testing.T) {
	for _, addr := range []string{"203.0.113.5:1234", "not-an-address", "[2001:db8::1]:80"} {
		fake := &fakeInvalidator{}
		rec := invalidateOnce(fake, http.MethodPost, addr, goodInvalidateBody)
		if rec.Code != http.StatusForbidden {
			t.Fatalf("RemoteAddr %q: status = %d, want 403", addr, rec.Code)
		}
		if n := len(fake.calls()); n != 0 {
			t.Fatalf("RemoteAddr %q: the invalidator was called %d times; a refused caller purges nothing", addr, n)
		}
	}
}

func TestInvalidateEndpointRefusesBadBody(t *testing.T) {
	huge := `{"chunk_id":"c","change_type":"cosmetic","new_text":"` + strings.Repeat("x", maxInvalidateBody) + `"}`
	cases := map[string]string{
		"not JSON":              `this is not json`,
		"an unknown field":      `{"chunk_id":"c","change_type":"cosmetic","surprise":1}`,
		"an empty chunk_id":     `{"chunk_id":"","change_type":"cosmetic"}`,
		"a missing chunk_id":    `{"change_type":"cosmetic"}`,
		"change_type minor":     `{"chunk_id":"c","change_type":"minor"}`,
		"a missing change_type": `{"chunk_id":"c"}`,
		"two JSON objects":      `{"chunk_id":"c","change_type":"cosmetic"}{"chunk_id":"d","change_type":"cosmetic"}`,
		"a body over 1 MB":      huge,
	}
	for name, body := range cases {
		t.Run(name, func(t *testing.T) {
			fake := &fakeInvalidator{}
			rec := invalidateOnce(fake, http.MethodPost, "127.0.0.1:5000", body)
			if rec.Code != http.StatusBadRequest {
				t.Fatalf("status = %d, want 400; body %s", rec.Code, rec.Body.String())
			}
			if n := len(fake.calls()); n != 0 {
				t.Fatalf("the invalidator was called %d times; a bad body purges nothing", n)
			}
		})
	}
}

func TestInvalidateEndpointRefusesGet(t *testing.T) {
	fake := &fakeInvalidator{}
	rec := invalidateOnce(fake, http.MethodGet, "127.0.0.1:5000", "")
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status = %d, want 405", rec.Code)
	}
	if n := len(fake.calls()); n != 0 {
		t.Fatalf("the invalidator was called %d times on a GET", n)
	}
}

func TestInvalidateEndpointWithoutMapIs503(t *testing.T) {
	rec := invalidateOnce(nil, http.MethodPost, "127.0.0.1:5000", goodInvalidateBody)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want 503", rec.Code)
	}
}

func TestInvalidateEndpointClosedMapIs503(t *testing.T) {
	fake := &fakeInvalidator{err: deps.ErrClosed}
	rec := invalidateOnce(fake, http.MethodPost, "127.0.0.1:5000", goodInvalidateBody)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want 503; body %s", rec.Code, rec.Body.String())
	}
}
