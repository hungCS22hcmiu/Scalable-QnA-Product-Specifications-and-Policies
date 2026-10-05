package telemetry

import (
	"bufio"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// raw/ is write-once. Reusing a run id must FAIL, not
// append: rows from two runs in one file would be silently mixed, and every per-run denominator
// computed from it would be wrong with nothing to reveal it.
func TestOpenRefusesAnExistingRunFile(t *testing.T) {
	dir := t.TempDir()
	l, err := Open(dir, "run-1")
	if err != nil {
		t.Fatal(err)
	}
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := Open(dir, "run-1"); err == nil {
		t.Fatal("reopening a finished run's log succeeded; raw/ must be write-once")
	}
}

// An empty run id means "functional run": no file at all. A `make dev` session must not leave
// something on disk that later reads as a measurement.
func TestEmptyRunIDWritesNothing(t *testing.T) {
	dir := t.TempDir()
	l, err := Open(dir, "")
	if err != nil || l != nil {
		t.Fatalf("Open with no run id: %v, %v; want nil, nil", l, err)
	}
	l.Log(Record{RequestID: "x"}) // must not panic on the nil logger
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	entries, _ := os.ReadDir(dir)
	if len(entries) != 0 {
		t.Fatalf("a disabled logger created %d path(s)", len(entries))
	}
}

// The nullable fields must render as JSON null, never as 0 or "". A zero that reads as a real
// measurement is exactly the silent corruption interfaces.md H's pointer fields exist to prevent.
func TestNullableFieldsRenderAsNull(t *testing.T) {
	dir := t.TempDir()
	l, err := Open(dir, "run-null")
	if err != nil {
		t.Fatal(err)
	}
	l.Log(Record{RequestID: "r1", Cache: "TIER1_HIT"})
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}

	raw, err := os.ReadFile(filepath.Join(dir, "run-null", "raw", "requests.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	var m map[string]any
	if err := json.Unmarshal(raw, &m); err != nil {
		t.Fatalf("record is not valid JSON: %v", err)
	}
	for _, k := range []string{
		"similarity", "source_overlap", "stratum",
		"t_embed_ms", "t_search_ms", "t_overlap_ms", "t_permit_wait_ms", "t_generate_ms",
		"dataset_epoch_at_retrieval",
	} {
		v, present := m[k]
		if !present {
			t.Errorf("%s is missing; the schema requires the key with a null value", k)
			continue
		}
		if v != nil {
			t.Errorf("%s = %v, want null", k, v)
		}
	}
}

// One JSONL record per request, one line each.
func TestWritesOneLinePerRecord(t *testing.T) {
	dir := t.TempDir()
	l, _ := Open(dir, "run-lines")
	for _, id := range []string{"a", "b", "c"} {
		l.Log(Record{RequestID: id})
	}
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}

	f, err := os.Open(filepath.Join(dir, "run-lines", "raw", "requests.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	var ids []string
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		if strings.TrimSpace(sc.Text()) == "" {
			continue
		}
		var r Record
		if err := json.Unmarshal(sc.Bytes(), &r); err != nil {
			t.Fatalf("line is not one record: %v", err)
		}
		ids = append(ids, r.RequestID)
	}
	if strings.Join(ids, ",") != "a,b,c" {
		t.Fatalf("got %v, want a,b,c in order", ids)
	}
}

// Logging after Close must be a silent no-op, not a panic on a closed channel and not a write
// that never lands. A request finishing during shutdown is ordinary, and crashing the gateway
// there would turn a clean stop into a lost run.
func TestLogAfterCloseIsSafe(t *testing.T) {
	dir := t.TempDir()
	l, _ := Open(dir, "run-close")
	l.Log(Record{RequestID: "before"})
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	l.Log(Record{RequestID: "after"}) // must not panic
	if err := l.Close(); err != nil {
		t.Fatalf("second Close: %v", err)
	}
	if n := l.Dropped(); n != 0 {
		t.Fatalf("Dropped() = %d after a clean run, want 0", n)
	}

	raw, err := os.ReadFile(filepath.Join(dir, "run-close", "raw", "requests.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(raw), "after") {
		t.Fatal("a record logged after Close reached the file")
	}
	if !strings.Contains(string(raw), "before") {
		t.Fatal("a record logged before Close was lost -- Close must flush")
	}
}
