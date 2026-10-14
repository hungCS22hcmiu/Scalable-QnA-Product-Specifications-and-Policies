package telemetry

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// Item 2.3 (docs/work/2026-10-14-refusal-cause-code/): five keys join interfaces.md H at v0.13.
// refusal_cause, support_lex and support_numeric_ok are required keys with a null value when there is
// nothing to say; candidate_entry_id and candidate_sources are extensions, present iff a candidate
// was judged (like reuse_rule). This file is new on purpose: TestNullableFieldsRenderAsNull is an
// existing test and is not edited.

// logOne writes one record through a real Logger and returns the raw line and its decoding.
func logOne(t *testing.T, rec Record) (string, map[string]any) {
	t.Helper()
	dir := t.TempDir()
	l, err := Open(dir, "run-cause")
	if err != nil {
		t.Fatal(err)
	}
	l.Log(rec)
	if err := l.Close(); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(filepath.Join(dir, "run-cause", "raw", "requests.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	var m map[string]any
	if err := json.Unmarshal(raw, &m); err != nil {
		t.Fatalf("record is not valid JSON: %v\n%s", err, raw)
	}
	return string(raw), m
}

// "Null" and "key absent" must stay different. A log from before the 2.3 commit has none of the three
// keys; a log from after has them, null where the gate did not run. If a pointer field gained
// omitempty, the two would merge and a pre-2.3 log would read as the gate-off arm (design.md F8).
func TestCauseFieldsRenderAsNull(t *testing.T) {
	_, m := logOne(t, Record{RequestID: "r1", Cache: "MISS"})
	for _, k := range []string{"refusal_cause", "support_lex", "support_numeric_ok"} {
		v, present := m[k]
		if !present {
			t.Errorf("%s is missing; the key must be present with a null value", k)
			continue
		}
		if v != nil {
			t.Errorf("%s = %v, want null", k, v)
		}
	}
}

func TestCandidateFieldsAreExtensions(t *testing.T) {
	_, m := logOne(t, Record{RequestID: "r1", Cache: "MISS"})
	for _, k := range []string{"candidate_entry_id", "candidate_sources"} {
		if _, present := m[k]; present {
			t.Errorf("%s is present on a record that judged no candidate; it must be absent", k)
		}
	}

	_, m = logOne(t, Record{
		RequestID: "r2", Cache: "MISS",
		CandidateEntryID: "01J-cand", CandidateSources: []string{"product-headphones-03#chunk-0"},
	})
	if m["candidate_entry_id"] != "01J-cand" {
		t.Errorf("candidate_entry_id = %v", m["candidate_entry_id"])
	}
	src, _ := m["candidate_sources"].([]any)
	if len(src) != 1 || src[0] != "product-headphones-03#chunk-0" {
		t.Errorf("candidate_sources = %v", m["candidate_sources"])
	}
}

// A zero is a real measurement. support_lex 0 (nothing supported) and support_numeric_ok false (a
// number refused) must render as 0 and false, not null: null means the gate did not run.
func TestCauseFieldsRenderValues(t *testing.T) {
	cause, zero, no := "SUPPORT", 0.0, false
	raw, m := logOne(t, Record{RequestID: "r1", Cache: "MISS", RefusalCause: &cause, SupportLex: &zero, SupportNumericOK: &no})
	if m["refusal_cause"] != "SUPPORT" {
		t.Errorf("refusal_cause = %v", m["refusal_cause"])
	}
	if v, ok := m["support_lex"]; !ok || v != 0.0 {
		t.Errorf("support_lex = %v (present %v), want 0 and not null", v, ok)
	}
	if v, ok := m["support_numeric_ok"]; !ok || v != false {
		t.Errorf("support_numeric_ok = %v (present %v), want false and not null", v, ok)
	}
	if !strings.Contains(raw, `"support_lex":0,`) || !strings.Contains(raw, `"support_numeric_ok":false`) {
		t.Errorf("raw line does not carry the literal values: %s", raw)
	}
}

// An offline `support_lex < 0.6` has to agree with SupportVerdict.Refuses (Score < TauSupportLexical).
// Go writes 0.6 as 0.6, so the two cannot disagree on the pinned threshold itself.
func TestSupportLexIsWrittenExactly(t *testing.T) {
	for _, v := range []float64{0.6, 0.3125, 0.875, 1} {
		raw, m := logOne(t, Record{RequestID: "r1", Cache: "TIER2_HIT", SupportLex: &v})
		if m["support_lex"] != v {
			t.Errorf("support_lex round-trip: wrote %v, read %v\n%s", v, m["support_lex"], raw)
		}
	}
}
