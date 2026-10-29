package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net"
	"net/http"
	"time"

	"github.com/hung/thesis/gateway/internal/deps"
)

// maxInvalidateBody bounds POST /invalidate's body. An edit's new_text is one chunk, a few hundred
// words; 1 MB is far above any real event and far below anything that would strain the gateway.
const maxInvalidateBody = 1 << 20

// invalidator is the part of *deps.Map that POST /invalidate uses (item 4.4, interfaces.md §E). An
// interface so the handler's tests need no Redis: the purge itself belongs to deps/'s tests.
type invalidator interface {
	InvalidateWait(ctx context.Context, ev deps.Event) (deps.PurgeResult, error)
}

var _ invalidator = (*deps.Map)(nil) // the real map must keep satisfying it

// invalidateRequest is interfaces.md §E's invalidation event, as JSON. Unknown fields are refused.
type invalidateRequest struct {
	ChunkID        string    `json:"chunk_id"`
	DocID          string    `json:"doc_id"`
	ChangeType     string    `json:"change_type"`
	NewText        string    `json:"new_text"`
	DatasetVersion string    `json:"dataset_version"`
	TS             time.Time `json:"ts"`
}

// invalidateResponse is the purge result. The slices are never null: a caller that reads "purged" gets
// a list, empty when the chunk had no dependents.
type invalidateResponse struct {
	ChunkID string   `json:"chunk_id"`
	Purged  []string `json:"purged"`
	Failed  []string `json:"failed"`
	Errors  []string `json:"errors"`
}

// Invalidate serves POST /invalidate: it purges every entry that depends on one chunk, WAITS until the
// Redis purge has finished, and replies with what was purged and what failed.
//
//   - 405 unless POST; 403 unless the caller is on loopback (the edit tool runs on this machine, and an
//     open purge endpoint is a way to empty the cache);
//   - 400 for a body over 1 MB, a body that is not one JSON object, an unknown field, an empty chunk_id,
//     or a change_type other than substantive/cosmetic. Nothing is purged;
//   - 503 when there is no Invalidator or the map is closed;
//   - 500 when any entry failed to purge, or the purge could not start;
//   - 200 otherwise.
//
// It never refuses under MUTATION=off: refusing a purge would leave stale entries in the cache, and the
// mutation arm is the operator's choice. change_type is checked and recorded, never used as a gate
// (interfaces.md §E).
func (h *Handler) Invalidate(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if !isLoopback(r.RemoteAddr) {
		log.Printf("invalidate: refused a caller that is not on loopback: %s", r.RemoteAddr)
		http.Error(w, "forbidden: /invalidate accepts loopback callers only", http.StatusForbidden)
		return
	}

	req, err := decodeInvalidate(w, r)
	if err != nil {
		log.Printf("invalidate: bad request: %v", err)
		http.Error(w, "invalid request: "+err.Error(), http.StatusBadRequest)
		return
	}

	if h.Invalidator == nil {
		http.Error(w, "invalidation is not available: the gateway has no dependency map", http.StatusServiceUnavailable)
		return
	}

	res, err := h.Invalidator.InvalidateWait(r.Context(), deps.Event{
		ChunkID: req.ChunkID, DocID: req.DocID, ChangeType: req.ChangeType, NewText: req.NewText,
		DatasetVersion: req.DatasetVersion, TS: req.TS,
	})
	if err != nil {
		status := http.StatusInternalServerError
		if errors.Is(err, deps.ErrClosed) {
			status = http.StatusServiceUnavailable
		}
		log.Printf("invalidate: chunk=%s change_type=%s status=%d: %v", req.ChunkID, req.ChangeType, status, err)
		writeInvalidate(w, status, invalidateResponse{
			ChunkID: req.ChunkID, Purged: []string{}, Failed: []string{}, Errors: []string{err.Error()},
		})
		return
	}

	status := http.StatusOK
	if len(res.Failed) > 0 || len(res.Errors) > 0 {
		status = http.StatusInternalServerError
	}
	log.Printf("invalidate: chunk=%s change_type=%s purged=%d failed=%d errors=%d status=%d",
		res.ChunkID, req.ChangeType, len(res.Purged), len(res.Failed), len(res.Errors), status)
	writeInvalidate(w, status, invalidateResponse{
		ChunkID: res.ChunkID, Purged: nonNil(res.Purged), Failed: nonNil(res.Failed), Errors: nonNil(res.Errors),
	})
}

// decodeInvalidate reads and checks the body. Any problem is a 400 for the caller, whatever its cause.
func decodeInvalidate(w http.ResponseWriter, r *http.Request) (invalidateRequest, error) {
	var req invalidateRequest
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxInvalidateBody))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&req); err != nil {
		return req, err
	}
	if _, err := dec.Token(); !errors.Is(err, io.EOF) {
		return req, errors.New("the body must hold exactly one JSON object")
	}
	if req.ChunkID == "" {
		return req, errors.New("chunk_id is empty")
	}
	if req.ChangeType != "substantive" && req.ChangeType != "cosmetic" {
		return req, errors.New(`change_type must be "substantive" or "cosmetic"`)
	}
	return req, nil
}

func writeInvalidate(w http.ResponseWriter, status int, body invalidateResponse) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(body); err != nil {
		log.Printf("invalidate: writing the reply: %v", err)
	}
}

func nonNil(s []string) []string {
	if s == nil {
		return []string{}
	}
	return s
}

// isLoopback reports whether a RemoteAddr ("host:port") is a loopback address. An address that does
// not parse is not loopback.
func isLoopback(remoteAddr string) bool {
	host, _, err := net.SplitHostPort(remoteAddr)
	if err != nil {
		return false
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}
