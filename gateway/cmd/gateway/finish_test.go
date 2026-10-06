package main

import (
	"fmt"
	"math"
	"path/filepath"
	"strings"
	"testing"

	"github.com/hung/thesis/gateway/internal/telemetry"
)

// finishRun is the call site of `incomplete`: Close, THEN read the counters. incomplete_test.go tests
// the rule; these test the ORDER and the wiring (found by the implementation review: a run that read
// the counters before Close, or fed a field from the wrong accessor, passed every test).

func openLog(t *testing.T) *telemetry.Logger {
	t.Helper()
	l, err := telemetry.Open(filepath.Join(t.TempDir(), "results"), "run-finish")
	if err != nil {
		t.Fatal(err)
	}
	return l
}

// A queue of records each carrying a hash with no matching text. Every one is a guard refusal, but
// only once the writer has PROCESSED it, so a count read before Close sees only a prefix of them. The
// exact total is what proves the counters were read after the drain.
func TestFinishRunReadsTheCountersAfterTheBufferHasDrained(t *testing.T) {
	const n = 2000 // below the 4096 buffer: none dropped
	l := openLog(t)
	for i := range n {
		l.Log(telemetry.Record{RequestID: fmt.Sprintf("r%d", i), Cache: "MISS", AnswerSHA256: "0123abcd"})
	}
	closeErr, verdict := finishRun(l)
	if closeErr != nil {
		t.Fatalf("close: %v", closeErr)
	}
	if verdict == nil {
		t.Fatal("finishRun = nil for a run of 2000 guard refusals")
	}
	if want := fmt.Sprintf("%d record(s) carried an answer_sha256", n); !strings.Contains(verdict.Error(), want) {
		t.Fatalf("verdict = %q, want it to count all %d refusals (%q): the counters were read before the drain", verdict, n, want)
	}
	if !strings.Contains(verdict.Error(), "1 answer(s) named by a record have no file") {
		t.Fatalf("verdict = %q, want the one missing hash named too", verdict)
	}
}

func TestFinishRunNamesAFailedLineWrite(t *testing.T) {
	l := openLog(t)
	nan := math.NaN()
	l.Log(telemetry.Record{RequestID: "nan", SourceOverlap: &nan}) // json: unsupported value
	_, verdict := finishRun(l)
	if verdict == nil || !strings.Contains(verdict.Error(), "1 record line(s) failed to write") {
		t.Fatalf("verdict = %v, want one failed line write", verdict)
	}
}

func TestFinishRunOfACleanLogIsComplete(t *testing.T) {
	l := openLog(t)
	for i, text := range []string{"one answer", "another answer", "one answer"} {
		r := telemetry.Record{RequestID: fmt.Sprintf("r%d", i), Cache: "MISS"}
		r.SetAnswer(text)
		l.Log(r)
	}
	closeErr, verdict := finishRun(l)
	if closeErr != nil || verdict != nil {
		t.Fatalf("finishRun = %v, %v, want a complete run", closeErr, verdict)
	}
}

// make dev runs with a nil log; finishing it must be a no-op, not a nil dereference.
func TestFinishRunOfANilLogIsComplete(t *testing.T) {
	closeErr, verdict := finishRun(nil)
	if closeErr != nil || verdict != nil {
		t.Fatalf("finishRun(nil) = %v, %v, want nil, nil", closeErr, verdict)
	}
}
