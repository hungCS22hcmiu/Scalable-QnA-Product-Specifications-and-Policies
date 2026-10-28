package main

import (
	"os"
	"strings"
	"testing"
)

// TestMainWiresEpoch reads main.go as text, because main() has no seam a test can run: it opens Redis,
// dials the RAG service and listens. Two failures are silent. A handler with no epoch source never
// discards (httpapi treats a nil Epoch as "guard off", so that older tests still work), and
// writeback_discarded then stays false, which reads as "no race happened". A dependency map with no
// source leaves the late gap open, and nothing shows it (item 4.2, design failure modes 2 and 3).
//
// Comment lines are dropped first, so a needle that appears only in a comment does not count.
func TestMainWiresEpoch(t *testing.T) {
	raw, err := os.ReadFile("main.go")
	if err != nil {
		t.Fatal(err)
	}
	var code []string
	for _, line := range strings.Split(string(raw), "\n") {
		if strings.HasPrefix(strings.TrimSpace(line), "//") {
			continue
		}
		code = append(code, line)
	}
	src := strings.Join(code, "\n")

	index := func(needle string) int {
		t.Helper()
		i := strings.Index(src, needle)
		if i < 0 {
			t.Fatalf("main.go (comments dropped) has no %q", needle)
		}
		return i
	}

	index("epochFile, epochNow, err := epochFromEnv(os.LookupEnv)")

	build := index("depMap := deps.New(")
	setSource := index("depMap.SetEpochSource(epochFile)")
	if setSource < build {
		t.Errorf("depMap.SetEpochSource(epochFile) (at %d) comes before depMap := deps.New( (at %d): the map does not exist yet", setSource, build)
	}

	newHandler := index("httpapi.NewHandler(")
	assign := index("handler.Epoch = epochFile")
	if assign < newHandler {
		t.Errorf("handler.Epoch = epochFile (at %d) comes before httpapi.NewHandler( (at %d): the handler does not exist yet", assign, newHandler)
	}

	late := index("depMap.LateDiscards()")
	finish := index("finishRun(evalLog)")
	if late > finish {
		t.Errorf("depMap.LateDiscards() (at %d) comes after finishRun(evalLog) (at %d): the count must be logged before the run is judged", late, finish)
	}
}
