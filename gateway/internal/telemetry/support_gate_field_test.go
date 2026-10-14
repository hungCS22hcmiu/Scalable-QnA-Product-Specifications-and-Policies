package telemetry

import (
	"strings"
	"testing"
)

// Item 2.4 (docs/work/2026-10-14-support-gate-switch/): support_gate joins interfaces.md H at v0.14, a
// required key on EVERY record, "on" or "off". It is a plain string so that this package stays free of
// repository imports (docs/architecture.md); the handler writes Gate.String() into it.
//
// The key must have no omitempty. A log from the 2.3 era has no support_gate and is read as gate-on, and
// a log from before 2.3 has neither key and is neither arm; the reading table in H keys on presence, so
// a field that vanished when empty would merge a record the handler forgot to label with a log that
// predates the key. This file is new on purpose: the existing telemetry tests are not edited. logOne is
// the helper in cause_fields_test.go.

func TestSupportGateKeyIsAlwaysWritten(t *testing.T) {
	// A zero Record: the key is present even though its value is empty. The empty string is a defect
	// that H names (any value other than on or off), and it is only visible if the key is written.
	raw, m := logOne(t, Record{RequestID: "r1", Cache: "MISS"})
	v, present := m["support_gate"]
	if !present {
		t.Fatalf("support_gate is missing from a record with the field unset; it must always be written\n%s", raw)
	}
	if v != "" {
		t.Errorf("support_gate = %v on a zero Record, want the empty string", v)
	}

	for _, arm := range []string{"on", "off"} {
		raw, m = logOne(t, Record{RequestID: "r-" + arm, Cache: "TIER2_HIT", SupportGate: arm})
		if m["support_gate"] != arm {
			t.Errorf("support_gate = %v, want %q\n%s", m["support_gate"], arm, raw)
		}
		if !strings.Contains(raw, `"support_gate":"`+arm+`"`) {
			t.Errorf("the record line does not carry support_gate=%q:\n%s", arm, raw)
		}
	}
}

// It is not null, and it is not an extension. A null would read as "the gate did not run for this
// candidate", which is the support fields' statement and not the arm's.
func TestSupportGateKeyIsNeverNull(t *testing.T) {
	_, m := logOne(t, Record{RequestID: "r1", Cache: "TIER1_HIT", SupportGate: "on"})
	if v, present := m["support_gate"]; !present || v == nil {
		t.Errorf("support_gate = %v (present %v), want a non-null string on a Tier-1 record too", v, present)
	}
}
