package telemetry

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// Run rule 12 (interfaces.md §H v0.20): the Logger counts records marked tier2_search_failed, so the
// run's end can refuse it. The count is of the marked records, not of all records.
func TestTier2SearchErrorIsCounted(t *testing.T) {
	dir := t.TempDir()
	l, err := Open(dir, "run-t2err")
	if err != nil {
		t.Fatal(err)
	}
	l.Log(Record{RequestID: "bad-1", Cache: "MISS", Tier2SearchFailed: true})
	l.Log(Record{RequestID: "ok-1", Cache: "MISS"})
	l.Log(Record{RequestID: "bad-2", Cache: "MISS", Tier2SearchFailed: true})
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}

	if got := l.Tier2SearchFailures(); got != 2 {
		t.Fatalf("Tier2SearchFailures() = %d, want 2 (two marked records and one unmarked)", got)
	}

	raw, err := os.ReadFile(filepath.Join(dir, "run-t2err", "raw", "requests.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSpace(string(raw)), "\n")
	if len(lines) != 3 {
		t.Fatalf("%d record lines, want 3", len(lines))
	}
	marked := 0
	for _, line := range lines {
		if strings.Contains(line, `"tier2_search_failed":true`) {
			marked++
			if !strings.Contains(line, `"request_id":"bad-`) {
				t.Errorf("an unmarked request carries the key: %s", line)
			}
		} else if strings.Contains(line, "tier2_search_failed") {
			t.Errorf("the key appears with a value other than true: %s", line)
		}
	}
	if marked != 2 {
		t.Errorf("%d lines carry tier2_search_failed:true, want 2", marked)
	}

	// The nil Logger (a run without a run id) counts nothing and does not panic.
	var none *Logger
	if got := none.Tier2SearchFailures(); got != 0 {
		t.Errorf("nil Logger counted %d", got)
	}
}
