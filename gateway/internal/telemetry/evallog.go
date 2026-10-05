// Package telemetry writes the per-request evaluation log of interfaces.md H.
//
// Four metrics in the evaluation are NOT COMPUTABLE without this record: decisions
// changed by provenance, % entering the cascade band, false hits by cause, and the hit-path
// latency decomposition. answer_sha256 cannot be reconstructed after the fact at all: it must hash
// what was SERVED, not a possibly re-generated answer. similarity_only_decision, the other such
// field, was retired with the unfiltered cascade phase that produced it (interfaces.md §H, ADR-004).
package telemetry

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
)

// Record is interfaces.md H's JSONL schema, field for field. Pointers are the fields the schema
// marks nullable -- they must render as `null`, not as a zero that reads as a real measurement.
type Record struct {
	RequestID string `json:"request_id"`
	RunID     string `json:"run_id"`
	ConfigID  int    `json:"config_id"`
	Mutation  string `json:"mutation"`
	TS        string `json:"ts"`

	QueryRaw        string  `json:"query_raw"`
	QueryNormalized string  `json:"query_normalized"`
	T1Key           string  `json:"t1_key"`
	Stratum         *string `json:"stratum"`

	Cache         string   `json:"cache"`
	Similarity    *float64 `json:"similarity"`
	SourceOverlap *float64 `json:"source_overlap"`
	EnteredBand   bool     `json:"entered_band"`

	RetrievedChunkIDs []string `json:"retrieved_chunk_ids"`
	EntrySources      []string `json:"entry_sources"`
	EntryID           string   `json:"entry_id"`

	TotalMS       float64  `json:"t_total_ms"`
	Tier1MS       float64  `json:"t_tier1_ms"`
	EmbedMS       *float64 `json:"t_embed_ms"`
	SearchMS      *float64 `json:"t_search_ms"`
	OverlapMS     *float64 `json:"t_overlap_ms"`
	PermitWaitMS  *float64 `json:"t_permit_wait_ms"`
	GenerateMS    *float64 `json:"t_generate_ms"`
	Shed          bool     `json:"shed"`
	PermitQueue   int      `json:"permit_queue_depth"`
	DatasetEpoch  *uint64  `json:"dataset_epoch_at_retrieval"`
	WritebackDisc bool     `json:"writeback_discarded"`

	AnswerSHA256 string `json:"answer_sha256"`

	// --- beyond the frozen schema ---
	// Coalesced marks a request served by another request's generation. It is NOT in
	// interfaces.md H and is an extension: generations avoided by coalescing is a quantity
	// distinct from cache hits and not derivable from the frozen fields, because a coalesced
	// request is a MISS by every field the schema has. Promoting it needs an ADR.
	Coalesced bool `json:"coalesced,omitempty"`
	// ReuseRule names the rule variant that judged the Tier-2 candidate (two-lane experiment):
	// present iff a candidate was judged, refusals included, so its presence is not a hit. Also an
	// extension, but "% reaching the provenance check" is computed from it (ADR-004), so dropping
	// it voids that metric silently.
	ReuseRule string `json:"reuse_rule,omitempty"`
	// ProductID records the request's product scope now that it is part of the Tier-1 key
	// (⚠️ BYPASS 2026-09-09, reverses the rejection -- cache.Key). Required, not optional,
	// because handler.go's offline stratum join on query_normalized was exact only under
	// the one-stratum-per-normalised-form guarantee, which a product-scoped Tier-1 key
	// relaxes; t1_key alone cannot recover which product a record belongs to.
	ProductID string `json:"product_id,omitempty"`
}

// Logger appends Records as JSONL, off the request path.
//
// The nil Logger is valid and does nothing, so `make dev` needs no run id and the call sites need
// no branch.
type Logger struct {
	ch      chan Record
	f       *os.File
	wg      sync.WaitGroup
	dropped atomic.Int64
	closed  atomic.Bool
}

// bufferSize is deliberately large. A dropped record is a HOLE in the measurement, not a slow
// request, so the buffer should absorb any plausible burst; Dropped() exists to make a hole
// visible rather than silent.
const bufferSize = 4096

// Open creates results/{runID}/raw/requests.jsonl and starts the writer.
//
// ⚠️ O_EXCL, never append. raw/ is WRITE-ONCE: if a run
// id is reused, the correct action is a new run id, never adding rows to a finished run's file.
// Refusing to start is the loud version of that rule.
//
// An empty runID disables logging and returns a nil Logger.
func Open(resultsDir, runID string) (*Logger, error) {
	if runID == "" {
		return nil, nil
	}
	dir := filepath.Join(resultsDir, runID, "raw")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, fmt.Errorf("telemetry: creating %s: %w", dir, err)
	}
	path := filepath.Join(dir, "requests.jsonl")
	f, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o644)
	if err != nil {
		return nil, fmt.Errorf("telemetry: %s must not already exist (raw/ is write-once; use a new run_id): %w", path, err)
	}

	l := &Logger{ch: make(chan Record, bufferSize), f: f}
	l.wg.Add(1)
	go l.run()
	return l, nil
}

func (l *Logger) run() {
	defer l.wg.Done()
	enc := json.NewEncoder(l.f)
	for r := range l.ch {
		if err := enc.Encode(r); err != nil {
			log.Printf("telemetry: writing record %s: %v", r.RequestID, err)
		}
	}
}

// Log queues a record. It never blocks: a request that has already been answered must not wait on
// a log write. If the buffer is full the record is DROPPED and counted -- see Dropped.
func (l *Logger) Log(r Record) {
	if l == nil || l.closed.Load() {
		return
	}
	select {
	case l.ch <- r:
	default:
		if n := l.dropped.Add(1); n == 1 || n%1000 == 0 {
			log.Printf("telemetry: ERROR dropped %d evaluation record(s) -- the run has holes in it", n)
		}
	}
}

// Dropped reports records lost to a full buffer. A run with a nonzero count is missing rows from
// the evaluation's denominators and should be repeated, so this belongs in the manifest.
func (l *Logger) Dropped() int64 {
	if l == nil {
		return 0
	}
	return l.dropped.Load()
}

func (l *Logger) Close() error {
	if l == nil || !l.closed.CompareAndSwap(false, true) {
		return nil
	}
	close(l.ch)
	l.wg.Wait()
	if n := l.dropped.Load(); n > 0 {
		log.Printf("telemetry: run finished having DROPPED %d record(s)", n)
	}
	return l.f.Close()
}
