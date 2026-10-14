package reuse

import (
	"fmt"
	"math"
	"testing"
)

// Item 2.4 (docs/work/2026-10-14-support-gate-switch/): the support gate has an on/off switch. These
// tests are written before gate.go. Names say SupportGate or Gate, not "gate" alone, so they read apart
// from the unrelated blocking-hook type in httpapi's test harness.

// The zero value of Gate is the safe one. A struct that never sets it (the httpapi test harness builds
// a Handler as a struct literal and never does) must run the gate: a forgotten field must not ablate
// the research arm. If the constants are reordered, this is the test that notices.
func TestSupportGateZeroValueIsOn(t *testing.T) {
	var zero Gate
	if zero != GateOn {
		t.Fatalf("the zero Gate is %v, want GateOn: a forgotten field would silently switch the arm", zero)
	}
	if Gate(0) != GateOn {
		t.Errorf("Gate(0) = %v, want GateOn", Gate(0))
	}
	for g, want := range map[Gate]string{GateOn: "on", GateOff: "off", Gate(7): "invalid", Gate(-1): "invalid"} {
		if got := g.String(); got != want {
			t.Errorf("Gate(%d).String() = %q, want %q", int(g), got, want)
		}
	}
	// The record's support_gate key is written from String(), so the two strings are a contract
	// (interfaces.md section H). An analysis script compares against them.
	if GateOn.String() != "on" || GateOff.String() != "off" {
		t.Errorf("the strings of GateOn and GateOff are part of the log format")
	}
}

// ParseGate takes exactly "on" and "off". Not a case-insensitive match and not a trimmed one: the value
// comes from an environment variable, and a value that is almost right must stop the gateway, not pick
// an arm. On error the Gate it returns is GateOn, so a caller that ignores the error still runs the gate.
func TestParseGate(t *testing.T) {
	for _, c := range []struct {
		in      string
		want    Gate
		wantErr bool
	}{
		{"on", GateOn, false},
		{"off", GateOff, false},
		{"", GateOn, true},
		{"ON", GateOn, true},
		{"Off", GateOn, true},
		{" on", GateOn, true},
		{"on ", GateOn, true},
		{"on\n", GateOn, true},
		{"0", GateOn, true},
		{"1", GateOn, true},
		{"true", GateOn, true},
		{"false", GateOn, true},
		{"yes", GateOn, true},
		{"onoff", GateOn, true},
	} {
		got, err := ParseGate(c.in)
		if (err != nil) != c.wantErr {
			t.Errorf("ParseGate(%q): err = %v, wantErr %v", c.in, err, c.wantErr)
			continue
		}
		if got != c.want {
			t.Errorf("ParseGate(%q) = %v, want %v", c.in, got, c.want)
		}
	}
}

// eachLaneInput walks the same grid as TestJudgeAgreesWithDecideLane, which is the set of inputs that
// break comparisons (NaN) and namespaces (empty strings, a lane mismatch with equal strings). It is
// here and not shared with cause_test.go because that file is an existing test (item 2.4, A1).
func eachLaneInput(fn func(sim float64, d NamespaceDecision, label string)) {
	sims := []float64{math.NaN(), math.Inf(1), math.Inf(-1), -1, 0, 0.8499999, 0.85, 0.8500001, 1, 2}
	lanes := []Lane{LaneSpec, LanePolicy, LaneMixed}
	nss := []string{"", "a", "b"}
	for _, sim := range sims {
		for _, ql := range lanes {
			for _, el := range lanes {
				for _, qn := range nss {
					for _, en := range nss {
						d := judged(sim, ql, qn, el, en)
						fn(sim, d, fmt.Sprintf("q=%s/%q e=%s/%q", ql, qn, el, en))
					}
				}
			}
		}
	}
}

// With the gate off, a candidate that clears the namespace and tau is served whatever the evidence says,
// and everything that comes BEFORE the gate is unchanged. The table is TestJudgeCauses with both arms
// side by side, so a row reads "the on-arm says X, the off-arm says Y". Support is nil on every off
// row, refusals included: the gate did not run, and a nil result is how the log writes null for both
// support fields.
func TestJudgeGateOffServesWhatTheGateRefuses(t *testing.T) {
	same := judged(0.93, LaneSpec, "product-headphones-03", LaneSpec, "product-headphones-03")
	for _, c := range []struct {
		name       string
		d          NamespaceDecision
		sim        float64
		answer     string
		texts, ids []string
		wantOn     string // the cause with the gate on: pins the table against TestJudgeCauses
		wantOff    string
	}{
		{"served", same, 0.93, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs, CauseNone, CauseNone},
		{"below tau", judged(0.50, LaneSpec, "a", LaneSpec, "a"), 0.50, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs, CauseSimilarity, CauseSimilarity},
		{"another namespace", judged(0.93, LaneSpec, "a", LaneSpec, "b"), 0.93, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs, CauseNamespace, CauseNamespace},
		{"namespace before similarity", judged(0.50, LaneSpec, "a", LaneSpec, "b"), 0.50, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs, CauseNamespace, CauseNamespace},
		{"mixed query, spec entry, equal string", judged(0.93, LaneMixed, "x", LaneSpec, "x"), 0.93, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs, CauseNamespace, CauseNamespace},
		{"mixed query, mixed entry", judged(0.93, LaneMixed, "x", LaneMixed, "x"), 0.93, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs, CauseNone, CauseNone},
		// What the gate refuses with the gate on is served with it off.
		{"stale server, nil texts", same, 0.93, cachedAnswer, nil, paraphraseChunkIDs, CauseNotScored, CauseNone},
		{"stale server, empty texts", same, 0.93, cachedAnswer, []string{}, paraphraseChunkIDs, CauseNotScored, CauseNone},
		{"lexical arm refuses alone", same, 0.93, lexOnlyRefused, paraphraseEvidence, paraphraseChunkIDs, CauseSupport, CauseNone},
		{"numeric arm refuses alone", same, 0.93, numericOnlyRefused, paraphraseEvidence, paraphraseChunkIDs, CauseSupport, CauseNone},
		{"both arms refuse", same, 0.93, cachedAnswer, warrantyEvidence, warrantyChunkIDs, CauseSupport, CauseNone},
	} {
		t.Run(c.name, func(t *testing.T) {
			if on := judgeTh.Judge(GateOn, c.d, c.sim, c.answer, c.texts, c.ids); on.Cause != c.wantOn {
				t.Fatalf("gate on: cause = %q, want %q (the table no longer matches TestJudgeCauses)", on.Cause, c.wantOn)
			}
			off := judgeTh.Judge(GateOff, c.d, c.sim, c.answer, c.texts, c.ids)
			if off.Cause != c.wantOff {
				t.Fatalf("gate off: cause = %q, want %q", off.Cause, c.wantOff)
			}
			if off.Support != nil {
				t.Errorf("gate off: Support = %+v, want nil (the gate did not run, so both support fields log null)", off.Support)
			}
			if off.Served() != (c.wantOff == CauseNone) {
				t.Errorf("gate off: Served() = %v for cause %q", off.Served(), off.Cause)
			}
		})
	}
}

// The consistency rule of design.md 4, for the off arm: Judge must agree with DecideLane about
// everything DecideLane decides, on every input, WITH evidence that the gate would refuse and with no
// evidence text at all. Off, the cause is NONE exactly when the lane rule reuses, the gate result is
// nil, and none of SUPPORT, NOT_SCORED or CONTAINMENT can appear. If the off branch ever moves above
// the namespace or similarity check, a wrong-namespace candidate is served and this fails.
func TestJudgeAgreesWithDecideLaneGateOff(t *testing.T) {
	evidence := []struct {
		name       string
		texts, ids []string
	}{
		{"evidence the gate admits", paraphraseEvidence, paraphraseChunkIDs},
		{"evidence the gate refuses", warrantyEvidence, warrantyChunkIDs},
		{"no evidence text (a stale server)", nil, paraphraseChunkIDs},
	}
	eachLaneInput(func(sim float64, d NamespaceDecision, label string) {
		for _, ev := range evidence {
			j := judgeTh.Judge(GateOff, d, sim, cachedAnswer, ev.texts, ev.ids)
			if served := j.Cause == CauseNone; served != d.Reuse {
				t.Fatalf("sim=%v %s [%s]: DecideLane.Reuse=%v but gate-off cause=%q", sim, label, ev.name, d.Reuse, j.Cause)
			}
			if j.Support != nil {
				t.Fatalf("sim=%v %s [%s]: gate off but Support = %+v", sim, label, ev.name, j.Support)
			}
			switch j.Cause {
			case CauseNone, CauseNamespace, CauseSimilarity:
			default:
				t.Fatalf("sim=%v %s [%s]: gate off returned %q, which only the gate or an unreachable rule can write", sim, label, ev.name, j.Cause)
			}
			if j.Served() != d.Reuse {
				t.Fatalf("sim=%v %s [%s]: Served()=%v, DecideLane.Reuse=%v", sim, label, ev.name, j.Served(), d.Reuse)
			}
		}
	})

	// A zero decision is "no candidate". Off, as on, the answer is NAMESPACE and never NONE: a missing
	// candidate must not be servable on either arm.
	if j := judgeTh.Judge(GateOff, NamespaceDecision{}, 0.99, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs); j.Cause != CauseNamespace || j.Served() {
		t.Errorf("gate off, zero NamespaceDecision: %+v, want NAMESPACE and not served", j)
	}
}

// Every cause that comes before the gate is the same on both arms, and every candidate that reaches the
// gate on the on-arm is NONE on the off-arm. Together with the test above this is the whole difference
// between the arms: the gate's own refusals.
func TestJudgeBothArmsAgreeBeforeTheGate(t *testing.T) {
	evidence := []struct {
		answer     string
		texts, ids []string
	}{
		{cachedAnswer, paraphraseEvidence, paraphraseChunkIDs},
		{cachedAnswer, warrantyEvidence, warrantyChunkIDs},
		{lexOnlyRefused, paraphraseEvidence, paraphraseChunkIDs},
		{numericOnlyRefused, paraphraseEvidence, paraphraseChunkIDs},
		{cachedAnswer, nil, paraphraseChunkIDs},
	}
	eachLaneInput(func(sim float64, d NamespaceDecision, label string) {
		for _, ev := range evidence {
			on := judgeTh.Judge(GateOn, d, sim, ev.answer, ev.texts, ev.ids)
			off := judgeTh.Judge(GateOff, d, sim, ev.answer, ev.texts, ev.ids)
			switch on.Cause {
			case CauseNamespace, CauseSimilarity:
				if off.Cause != on.Cause {
					t.Fatalf("sim=%v %s: gate on says %q before the gate, gate off says %q", sim, label, on.Cause, off.Cause)
				}
			case CauseNone, CauseSupport, CauseNotScored:
				if off.Cause != CauseNone {
					t.Fatalf("sim=%v %s: gate on reached the gate (%q), gate off says %q, want NONE", sim, label, on.Cause, off.Cause)
				}
			default:
				t.Fatalf("sim=%v %s: gate on returned %q", sim, label, on.Cause)
			}
		}
	})
}

// Only the exact value GateOff skips the gate. A value nobody planned for (a future constant, a
// corrupted integer) runs it, so the unsafe direction needs a deliberate GateOff.
func TestJudgeUnknownGateRunsTheGate(t *testing.T) {
	same := judged(0.93, LaneSpec, "product-headphones-03", LaneSpec, "product-headphones-03")
	for _, g := range []Gate{Gate(2), Gate(7), Gate(-1)} {
		if j := judgeTh.Judge(g, same, 0.93, numericOnlyRefused, paraphraseEvidence, paraphraseChunkIDs); j.Cause != CauseSupport || j.Support == nil {
			t.Errorf("Gate(%d), refusing answer: %+v, want SUPPORT with a gate result (the gate must run)", int(g), j)
		}
		if j := judgeTh.Judge(g, same, 0.93, cachedAnswer, nil, paraphraseChunkIDs); j.Cause != CauseNotScored {
			t.Errorf("Gate(%d), stale server: cause %q, want NOT_SCORED (the gate must run)", int(g), j.Cause)
		}
	}
}
