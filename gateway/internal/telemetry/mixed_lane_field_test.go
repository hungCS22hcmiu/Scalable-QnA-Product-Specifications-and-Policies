package telemetry

import (
	"strings"
	"testing"
)

// Item 4.5 (docs/work/2026-10-27-mixed-arm-field/): mixed_lane joins interfaces.md H at v0.16, a required
// key on EVERY record, "on" or "off" (ADR-016). It is a plain string so that this package stays free of
// repository imports (docs/architecture.md); the handler writes LaneBand.Arm() into it.
//
// The key must have no omitempty. A log from before v0.16 has no mixed_lane and reads as off, and a
// composite record disproves that reading; the rule keys on presence, so a field that vanished when
// empty would merge a record the handler forgot to label with a log that predates the key. This file is
// new on purpose: the existing telemetry tests are not edited. logOne is the helper in
// cause_fields_test.go.

func TestMixedLaneKeyIsAlwaysWritten(t *testing.T) {
	// A zero Record: the key is present even though its value is empty. The empty string is a defect
	// that H names (any value other than on or off), and it is only visible if the key is written.
	raw, m := logOne(t, Record{RequestID: "r1", Cache: "MISS"})
	v, present := m["mixed_lane"]
	if !present {
		t.Fatalf("mixed_lane is missing from a record with the field unset; it must always be written\n%s", raw)
	}
	if v != "" {
		t.Errorf("mixed_lane = %v on a zero Record, want the empty string", v)
	}
	if !strings.Contains(raw, `"mixed_lane":""`) {
		t.Errorf("the record line does not carry mixed_lane as an empty string:\n%s", raw)
	}

	for _, arm := range []string{"on", "off"} {
		raw, m = logOne(t, Record{RequestID: "r-" + arm, Cache: "TIER2_HIT", MixedLane: arm})
		if m["mixed_lane"] != arm {
			t.Errorf("mixed_lane = %v, want %q\n%s", m["mixed_lane"], arm, raw)
		}
		if !strings.Contains(raw, `"mixed_lane":"`+arm+`"`) {
			t.Errorf("the record line does not carry mixed_lane=%q:\n%s", arm, raw)
		}
	}
}

// It is not null. A null would read as "no lane decision was made for this request", which is not what
// the arm says: the arm is a property of the process, not of the request.
func TestMixedLaneKeyIsNeverNull(t *testing.T) {
	_, m := logOne(t, Record{RequestID: "r1", Cache: "TIER1_HIT", MixedLane: "off"})
	v, present := m["mixed_lane"]
	if !present || v == nil {
		t.Fatalf("mixed_lane = %v (present %v), want a non-null string on a Tier-1 record too", v, present)
	}
	if _, ok := v.(string); !ok {
		t.Errorf("mixed_lane = %v (%T), want a string", v, v)
	}
}
