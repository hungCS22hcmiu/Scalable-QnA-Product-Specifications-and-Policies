package main

import (
	"errors"
	"strings"
	"testing"
)

// The completeness rule of interfaces.md v0.11 (§H "The answer store", rule 6; ADR-005), as a
// function so it can be tested: a log.Fatalf inside main() cannot be, and the Dropped branch this
// replaced had never been run by any test.
//
// Each field alone must name ITSELF and no other. That is what catches a field wired to the wrong
// message, and, with runCounts a struct, the call site cannot swap two int64s either.
func TestIncompleteNamesTheConditionThatFired(t *testing.T) {
	// A phrase unique to each condition's message.
	phrases := map[string]string{
		"Dropped":        "were dropped",
		"WriteErrors":    "failed to write",
		"AnswersMissing": "have no file",
		"GuardRefusals":  "skipped SetAnswer",
		"CloseErr":       "did not close cleanly",
	}
	cases := []struct {
		name string
		c    runCounts
		fire []string // which conditions are set
	}{
		{"Dropped", runCounts{Dropped: 3}, []string{"Dropped"}},
		{"WriteErrors", runCounts{WriteErrors: 2}, []string{"WriteErrors"}},
		{"AnswersMissing", runCounts{AnswersMissing: 1}, []string{"AnswersMissing"}},
		{"GuardRefusals", runCounts{GuardRefusals: 1}, []string{"GuardRefusals"}},
		{"CloseErr", runCounts{CloseErr: errors.New("disk gone")}, []string{"CloseErr"}},
		{"two", runCounts{Dropped: 1, AnswersMissing: 2}, []string{"Dropped", "AnswersMissing"}},
		{"all", runCounts{Dropped: 1, WriteErrors: 1, AnswersMissing: 1, GuardRefusals: 1, CloseErr: errors.New("x")},
			[]string{"Dropped", "WriteErrors", "AnswersMissing", "GuardRefusals", "CloseErr"}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := incomplete(tc.c)
			if err == nil {
				t.Fatal("incomplete = nil, want a reason")
			}
			fired := map[string]bool{}
			for _, f := range tc.fire {
				fired[f] = true
			}
			for field, phrase := range phrases {
				has := strings.Contains(err.Error(), phrase)
				if fired[field] && !has {
					t.Errorf("%s is set but %q is not in %q", field, phrase, err)
				}
				if !fired[field] && has {
					t.Errorf("%s is not set but %q is in %q", field, phrase, err)
				}
			}
		})
	}
}

func TestACleanRunIsComplete(t *testing.T) {
	if err := incomplete(runCounts{}); err != nil {
		t.Fatalf("incomplete(zero) = %v, want nil", err)
	}
}

// The counts are reported, not only the fact: an operator reading the log needs to know how bad it is.
func TestIncompleteReportsTheCounts(t *testing.T) {
	err := incomplete(runCounts{Dropped: 17, AnswersMissing: 4})
	if err == nil || !strings.Contains(err.Error(), "17") || !strings.Contains(err.Error(), "4 answer") {
		t.Fatalf("incomplete = %v, want it to carry 17 dropped and 4 missing", err)
	}
}
