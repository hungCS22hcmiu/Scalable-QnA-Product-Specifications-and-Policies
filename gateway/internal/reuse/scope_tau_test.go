package reuse

import (
	"math"
	"testing"
)

// Item 6.0a, done condition 13: a SHARED candidate is judged against TauP and a PRODUCT candidate
// against Tau. If the two were swapped, or a shared candidate met Tau, the arm's hits would shift with
// no error. DecideLane decides the threshold once and Judge reads it from the decision (NamespaceDecision.Tau).

var scopeTh = Thresholds{Tau: 0.85, Theta: 0.60, TauP: 0.80}

const (
	// between TauP and Tau: passes for a shared candidate, fails for a product one
	simBetween = 0.82
	// under both
	simLow = 0.70
	// over both
	simHigh = 0.93
)

func sharedInput(sim float64) LaneInput {
	return LaneInput{
		Similarity: sim, QueryLane: LanePolicy, QueryNS: "policy-return-electronics",
		EntryLane: LanePolicy, EntryNS: "policy-return-electronics", Shared: true,
	}
}

func productInput(sim float64) LaneInput {
	return LaneInput{
		Similarity: sim, QueryLane: LanePolicy, QueryNS: "policy-return-electronics@product-a",
		EntryLane: LanePolicy, EntryNS: "policy-return-electronics@product-a",
	}
}

func TestSharedCandidateIsHeldToTauPAndProductCandidateToTau(t *testing.T) {
	for _, tc := range []struct {
		name       string
		in         LaneInput
		wantTau    float64
		wantReuse  bool
		wantServed bool
	}{
		{"shared between the two thresholds", sharedInput(simBetween), 0.80, true, true},
		{"product between the two thresholds", productInput(simBetween), 0.85, false, false},
		{"shared above both", sharedInput(simHigh), 0.80, true, true},
		{"product above both", productInput(simHigh), 0.85, true, true},
		{"shared below both", sharedInput(simLow), 0.80, false, false},
		{"product below both", productInput(simLow), 0.85, false, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			d := scopeTh.DecideLane(tc.in)
			if d.Tau != tc.wantTau {
				t.Errorf("DecideLane applied tau = %v, want %v", d.Tau, tc.wantTau)
			}
			if d.Reuse != tc.wantReuse {
				t.Errorf("DecideLane reuse = %v, want %v", d.Reuse, tc.wantReuse)
			}
			j := scopeTh.Judge(GateOff, d, tc.in.Similarity, "an answer", nil, nil)
			if j.Served() != tc.wantServed {
				t.Errorf("Judge served = %v (cause %s), want %v", j.Served(), j.Cause, tc.wantServed)
			}
			if !tc.wantServed && j.Cause != CauseSimilarity {
				t.Errorf("cause = %s, want SIMILARITY", j.Cause)
			}
			// The rule and the cause agree on every row (TestJudgeAgreesWithDecideLane's invariant).
			if d.Reuse != j.Served() {
				t.Errorf("DecideLane reuse %v disagrees with Judge served %v", d.Reuse, j.Served())
			}
		})
	}
}

func TestSharedCandidateAtExactlyTauPPasses(t *testing.T) {
	// Inclusive, like Tau: a pair landing on the threshold reuses.
	d := scopeTh.DecideLane(sharedInput(0.80))
	if !d.Reuse {
		t.Error("a shared candidate at exactly TauP was refused")
	}
	if d := scopeTh.DecideLane(sharedInput(math.Nextafter(0.80, 0))); d.Reuse {
		t.Error("a shared candidate just under TauP was served")
	}
}

func TestSharedCandidateFailsClosedWithoutTauPOrOutsideThePolicyLane(t *testing.T) {
	noTauP := Thresholds{Tau: 0.85, Theta: 0.60}
	d := noTauP.DecideLane(sharedInput(0.99))
	if d.Reuse || !math.IsInf(d.Tau, 1) {
		t.Errorf("no TauP: reuse %v tau %v, want refused with an infinite threshold", d.Reuse, d.Tau)
	}
	if j := noTauP.Judge(GateOff, d, 0.99, "x", nil, nil); j.Served() {
		t.Error("Judge served a shared candidate that has no TauP")
	}
	spec := sharedInput(0.99)
	spec.QueryLane, spec.EntryLane = LaneSpec, LaneSpec
	if d := scopeTh.DecideLane(spec); d.Reuse || !math.IsInf(d.Tau, 1) {
		t.Errorf("a shared candidate on the SPEC lane: reuse %v tau %v, want refused", d.Reuse, d.Tau)
	}
}

func TestSharedCandidateStillNeedsTheNamespaceToMatch(t *testing.T) {
	in := sharedInput(simHigh)
	in.EntryNS = "policy-return-furniture-opened"
	d := scopeTh.DecideLane(in)
	if d.Reuse {
		t.Error("a shared candidate in another policy document was served")
	}
	if j := scopeTh.Judge(GateOff, d, simHigh, "x", nil, nil); j.Cause != CauseNamespace {
		t.Errorf("cause = %s, want NAMESPACE", j.Cause)
	}
}

func TestProductDecisionsCarryTauAndTheDefaultIsUnchanged(t *testing.T) {
	// The three existing entry points leave Tau at the one threshold they always used.
	if d := scopeTh.DecideNamespace(0.9, LaneSpec, "a", "a"); d.Tau != 0.85 {
		t.Errorf("DecideNamespace tau = %v, want 0.85", d.Tau)
	}
	mixed := scopeTh.DecideLane(LaneInput{Similarity: 0.9, QueryLane: LaneMixed, QueryNS: "x|y", EntryLane: LaneMixed, EntryNS: "x|y"})
	if mixed.Tau != 0.85 || !mixed.Reuse {
		t.Errorf("MIXED: tau %v reuse %v, want 0.85 and reuse", mixed.Tau, mixed.Reuse)
	}
}
