// Package telemetry writes the per-request evaluation log of interfaces.md H.
//
// Four metrics in the evaluation are NOT COMPUTABLE without this record: decisions
// changed by provenance, % entering the cascade band, false hits by cause, and the hit-path
// latency decomposition. answer_sha256 cannot be reconstructed after the fact at all: it must hash
// what was SERVED, not a possibly re-generated answer. similarity_only_decision, the other such
// field, was retired with the unfiltered cascade phase that produced it (interfaces.md §H, ADR-004).
//
// The text behind every answer_sha256 is kept too: raw/answers/{sha}.txt, written by the same
// writer goroutine BEFORE the line that names it (interfaces.md §H v0.11, ADR-005). A hash with no
// text behind it is a key to nothing once the bounded cache has evicted the entry.
package telemetry

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
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
	// answerText is the text AnswerSHA256 names. Unexported, so it never reaches the JSON line, and
	// set only by SetAnswer so the two cannot drift apart.
	answerText string

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

	// The answer store. seen is touched by the writer goroutine only. missing is read from other
	// goroutines (AnswersMissing), so mu guards it. guardRefusals is NEVER cleared: it means a call
	// site set an answer_sha256 without the text, which voids the run.
	answersDir    string
	seen          map[string]struct{}
	mu            sync.Mutex
	missing       map[string]struct{}
	guardRefusals atomic.Int64
	writeErrs     atomic.Int64
	answerErrs    atomic.Int64 // only to rate-limit the log

	// Seams for the tests, set after Open and before the first Log. They default to the os calls.
	createTemp func(dir, pattern string) (*os.File, error)
	linkFile   func(oldname, newname string) error
	removeFile func(name string) error
}

// bufferSize is deliberately large. A dropped record is a HOLE in the measurement, not a slow
// request, so the buffer should absorb any plausible burst; Dropped() exists to make a hole
// visible rather than silent.
const bufferSize = 4096

// Open creates results/{runID}/raw/requests.jsonl and raw/answers/ and starts the writer.
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

	// The leaf is created with Mkdir, never MkdirAll, and AFTER the exclusive create above has
	// claimed the run id. If it already exists this is a half-finished earlier attempt, and its files
	// must not be donated to this run: refuse, and remove only the requests.jsonl this call just made.
	// storeAnswer's EEXIST handling rests on this directory being fresh (ADR-005).
	answersDir := filepath.Join(dir, "answers")
	if err := os.Mkdir(answersDir, 0o755); err != nil {
		_ = f.Close()
		_ = os.Remove(path)
		return nil, fmt.Errorf("telemetry: creating %s (raw/ is write-once; use a new run_id): %w", answersDir, err)
	}

	l := &Logger{ch: make(chan Record, bufferSize), f: f, answersDir: answersDir,
		seen: map[string]struct{}{}, missing: map[string]struct{}{},
		createTemp: os.CreateTemp, linkFile: os.Link, removeFile: os.Remove}
	l.wg.Add(1)
	go l.run()
	return l, nil
}

func (l *Logger) run() {
	defer l.wg.Done()
	enc := json.NewEncoder(l.f)
	for r := range l.ch {
		if r.AnswerSHA256 != "" {
			l.storeAnswer(r)
		}
		if err := enc.Encode(r); err != nil {
			// Counted, not just logged: with the file already linked, a line that fails here leaves
			// a file no record names, and a lost line is a hole the run's denominators cannot show.
			l.writeErrs.Add(1)
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

// SetAnswer is the only way a record acquires an answer. It sets the hash and the text from one
// value, so they cannot drift apart. An empty text is a real answer (it hashes to the empty
// string's digest); AnswerSHA256 == "" is what means no answer was served.
func (r *Record) SetAnswer(text string) {
	r.AnswerSHA256 = sha256Hex(text)
	r.answerText = text
}

// sha256Hex hashes the answer AS SERVED: interfaces.md §H requires it to be taken when the answer
// is served and never recomputed from a possibly re-generated one.
func sha256Hex(text string) string {
	sum := sha256.Sum256([]byte(text))
	return hex.EncodeToString(sum[:])
}

// storeAnswer makes the text behind r.AnswerSHA256 visible as raw/answers/{sha}.txt, on the writer
// goroutine and BEFORE the record's line is written, so a line never names a file that is not there
// yet. It never fails the request: the request was served long ago. A failure is counted instead.
func (l *Logger) storeAnswer(r Record) {
	sha := r.AnswerSHA256
	if _, ok := l.seen[sha]; ok {
		return // the Zipf common case: this hash's file already exists
	}

	// The guard. A record whose text does not hash to its hash means a call site set one and not
	// the other (SetAnswer sets both). Without this the writer would publish the wrong bytes under
	// the hash's name, and "the file exists" would hold while being wrong. It is not cleared by a
	// later good record: the defect is in the code, and it voids the run.
	if sha256Hex(r.answerText) != sha {
		// missing first: a reader that sees the refusal count is then guaranteed to see the hash missing too.
		l.markMissing(sha)
		l.guardRefusals.Add(1)
		log.Printf("telemetry: ERROR record %s: answer text does not hash to answer_sha256 %s; NOT written -- the run is void", r.RequestID, sha)
		return
	}

	tmp, err := l.createTemp(l.answersDir, ".answer-*.tmp") // not "*.txt": a stray temp never matches the glob
	if err != nil {
		l.answerFailed(sha, err)
		return
	}
	tmpName := tmp.Name()
	_, werr := tmp.WriteString(r.answerText)
	if werr == nil {
		werr = tmp.Chmod(0o644) // CreateTemp makes 0600; requests.jsonl is 0644
	}
	if cerr := tmp.Close(); werr == nil {
		werr = cerr // a Close error means the bytes may not be there: checked BEFORE the link
	}
	if werr != nil {
		_ = l.removeFile(tmpName)
		l.answerFailed(sha, werr)
		return
	}

	// Link, never Rename: it fails if the name exists, so a file is never overwritten, and the final
	// name only ever appears complete. EEXIST counts as success, and is safe because Open made
	// answers/ fresh and this goroutine is the only thing that creates files in it. It is NOT safe
	// because of SHA-256: a hash says nothing about bytes someone else put under the name.
	if err := l.linkFile(tmpName, filepath.Join(l.answersDir, sha+".txt")); err != nil && !errors.Is(err, fs.ErrExist) {
		_ = l.removeFile(tmpName)
		l.answerFailed(sha, err)
		return
	}
	l.seen[sha] = struct{}{}
	l.clearMissing(sha)

	// The file exists now, so a failure to remove the temp name is a stray file, not a missing
	// answer. Marking it missing would void a good run, and at temperature 1 a MISS answer is never
	// seen again to clear it.
	if err := l.removeFile(tmpName); err != nil {
		log.Printf("telemetry: removing temp file %s after publishing %s: %v", tmpName, sha, err)
	}
}

// answerFailed records that no file exists for sha. seen is not set, so the next record carrying
// the same hash retries.
func (l *Logger) answerFailed(sha string, err error) {
	l.markMissing(sha)
	if n := l.answerErrs.Add(1); n == 1 || n%1000 == 0 {
		log.Printf("telemetry: ERROR could not store answer %s (%d so far): %v -- the run will be INCOMPLETE unless a later record retries it", sha, n, err)
	}
}

func (l *Logger) markMissing(sha string) {
	l.mu.Lock()
	l.missing[sha] = struct{}{}
	l.mu.Unlock()
}

func (l *Logger) clearMissing(sha string) {
	l.mu.Lock()
	delete(l.missing, sha)
	l.mu.Unlock()
}

// AnswersMissing reports the hashes a record names that have no file right now. It is a state, not a
// count of failed attempts: a failure followed by a successful retry leaves the run complete, and
// this says so. Call it after Close, which drains the buffer; before, pending records make it
// under-count.
func (l *Logger) AnswersMissing() int {
	if l == nil {
		return 0
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	return len(l.missing)
}

// GuardRefusals reports records whose text did not hash to their answer_sha256. Never cleared.
func (l *Logger) GuardRefusals() int64 {
	if l == nil {
		return 0
	}
	return l.guardRefusals.Load()
}

// WriteErrors reports record lines that failed to encode. Dropped() does not include them.
func (l *Logger) WriteErrors() int64 {
	if l == nil {
		return 0
	}
	return l.writeErrs.Load()
}
