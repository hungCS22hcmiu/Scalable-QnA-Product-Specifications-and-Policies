package main

import (
	"strings"
	"testing"

	"github.com/hung/thesis/gateway/internal/telemetry"
)

// Run rule 12 (interfaces.md §H v0.20): a run with any Tier-2 search error is not admissible. A
// marked record that nothing counts, or a count that incomplete() ignores, leaves the run looking
// admissible with a colder cache, so both halves are pinned here.

func TestIncompleteNamesTier2SearchFailures(t *testing.T) {
	err := incomplete(runCounts{Tier2SearchFailures: 2})
	if err == nil {
		t.Fatal("a run with 2 Tier-2 search failures was called complete")
	}
	for _, want := range []string{"2 request(s) hit a Tier-2 search error", "rule 12"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("the verdict should say %q, got: %v", want, err)
		}
	}
	if err := incomplete(runCounts{}); err != nil {
		t.Errorf("a run with no failures of any kind was refused: %v", err)
	}
}

func TestFinishRunCountsTier2SearchFailures(t *testing.T) {
	l, err := telemetry.Open(t.TempDir(), "run-rule12")
	if err != nil {
		t.Fatal(err)
	}
	l.Log(telemetry.Record{RequestID: "r1", Cache: "MISS", Tier2SearchFailed: true})
	closeErr, verdict := finishRun(l)
	if closeErr != nil {
		t.Fatalf("closing the log: %v", closeErr)
	}
	if verdict == nil {
		t.Fatal("finishRun called a run with a Tier-2 search error admissible")
	}
	if !strings.Contains(verdict.Error(), "Tier-2 search error") {
		t.Errorf("the verdict should name the Tier-2 search error, got: %v", verdict)
	}

	// The control: the same run with an ordinary MISS is complete.
	ok, err := telemetry.Open(t.TempDir(), "run-rule12-ok")
	if err != nil {
		t.Fatal(err)
	}
	ok.Log(telemetry.Record{RequestID: "r1", Cache: "MISS"})
	if closeErr, verdict := finishRun(ok); closeErr != nil || verdict != nil {
		t.Errorf("an ordinary run was refused: close=%v verdict=%v", closeErr, verdict)
	}
}
