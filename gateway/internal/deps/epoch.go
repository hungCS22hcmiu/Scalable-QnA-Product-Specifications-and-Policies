package deps

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// EpochSource reads the dataset epoch (interfaces.md §E, ADR-008). The write-back guard in httpapi
// and the writer's late check in this package both take it, so a test can supply any value or error.
type EpochSource interface {
	Current() (uint64, error)
}

// EpochFile is the epoch source of the real gateway: one decimal integer >= 1 in a file outside
// Redis. The Python RAG service stamps the same file's value on every retrieval, and an edit
// advances it.
//
// Current re-reads the file on every call, on purpose. A cached value would miss an advance, and a
// write-back stamped before an edit would then pass the guard against the old epoch. The read is a
// few bytes and runs once per write-back, never on the hit path.
type EpochFile struct {
	path string
}

var _ EpochSource = (*EpochFile)(nil)

// OpenEpochFile checks the file once and returns it with its current value. It refuses a relative
// path (the gateway and rag.server run from different directories), a missing file, a value that is
// not an integer, and a value below 1. 0 is never a real epoch.
func OpenEpochFile(path string) (*EpochFile, uint64, error) {
	if !filepath.IsAbs(path) {
		return nil, 0, fmt.Errorf("deps: epoch file %q is a relative path; use an absolute one", path)
	}
	f := &EpochFile{path: path}
	v, err := f.Current()
	if err != nil {
		return nil, 0, err
	}
	return f, v, nil
}

// Current reads the file now. A trailing newline or spaces are allowed; anything else that is not a
// decimal integer >= 1 is an error, so a guard that cannot read the epoch fails closed.
func (f *EpochFile) Current() (uint64, error) {
	raw, err := os.ReadFile(f.path)
	if err != nil {
		return 0, fmt.Errorf("deps: reading epoch file: %w", err)
	}
	s := strings.TrimSpace(string(raw))
	n, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("deps: epoch file %s holds %q, not an integer", f.path, truncate(s, 40))
	}
	if n < 1 {
		return 0, fmt.Errorf("deps: epoch file %s holds %d, below 1", f.path, n)
	}
	return uint64(n), nil
}

// Path is the file this source reads, for the start-up log line.
func (f *EpochFile) Path() string { return f.path }

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}
