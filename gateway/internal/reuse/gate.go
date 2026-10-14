package reuse

import "fmt"

// The support gate's on/off switch (super-plan.md item 2.4): configuration 4 is two ablation arms, the
// gate on and the gate off. Same constraint as rule.go and cause.go: standard library only, no I/O, so
// the decision can be falsified in isolation (docs/architecture.md 2).
// Design: docs/work/2026-10-14-support-gate-switch/design.md.

// Gate says whether the support gate runs.
//
// The zero value is GateOn, on purpose. The httpapi test harness builds a Handler as a struct literal
// and never sets the field, so a zero value that meant "off" would ablate the gate in every one of its
// tests and, through any other literal, in production. Only the exact value GateOff skips the gate:
// Judge runs it for anything else, so a value nobody planned for fails toward the safe arm.
// TestSupportGateZeroValueIsOn pins the order.
type Gate int

const (
	// GateOn: the gate runs. The default, and the value of the 2.3 behaviour.
	GateOn Gate = iota
	// GateOff: the ablation arm. A candidate that clears the namespace and tau is served without the
	// gate; Judge returns cause NONE with no support result, and both support fields are null in the log.
	GateOff
)

// String is the value written to the evaluation record's support_gate key (interfaces.md section H)
// and printed at start. An unknown value gives "invalid", which section H calls a defect.
func (g Gate) String() string {
	switch g {
	case GateOn:
		return "on"
	case GateOff:
		return "off"
	}
	return "invalid"
}

// ParseGate takes exactly "on" or "off". Not "ON", not "", not " on": the value arrives from an
// environment variable, and a value that is almost right must stop the gateway rather than pick an arm.
// On error the Gate returned is GateOn, so a caller that ignores the error still runs the gate.
func ParseGate(s string) (Gate, error) {
	switch s {
	case "on":
		return GateOn, nil
	case "off":
		return GateOff, nil
	}
	return GateOn, fmt.Errorf("support gate %q is not %q or %q", s, "on", "off")
}
