package reuse

import (
	"math"
	"testing"
)

// Item 2.3 (docs/work/2026-10-14-refusal-cause-code/): Thresholds.Judge turns a lane verdict, a
// similarity and the support gate into ONE cause. These tests are written before cause.go.
//
// The answers below are the fixtures already in support_test.go (cachedAnswer, paraphraseEvidence,
// warrantyEvidence) plus two short authored strings whose verdicts were computed, not chosen to land
// anywhere, and are pinned in TestCheckSupportRunsBothArms: one the lexical arm refuses and the
// numeric arm admits, and the reverse.

var judgeTh = Thresholds{Tau: 0.85, Theta: 0.60}

const (
	// lexOnlyRefused: no numbers (the numeric arm has nothing to refuse), no word in the evidence.
	lexOnlyRefused = "A brushed steel kettle with an automatic shutoff switch."
	// numericOnlyRefused: 9 of 10 content tokens are in the paraphrase evidence, but "9 hours" is not.
	numericOnlyRefused = "The EarBuds Pop 3 is in-ear true wireless with Bluetooth 5.3 and 9 hours of battery life, 24 hours with the case."
)

// judged builds the lane verdict the way the cascade does, so the tests exercise Judge against what
// DecideLane really returns and not against a hand-built struct.
func judged(sim float64, qLane Lane, qNS string, eLane Lane, eNS string) NamespaceDecision {
	return judgeTh.DecideLane(LaneInput{
		Similarity: sim, QueryLane: qLane, QueryNS: qNS, EntryLane: eLane, EntryNS: eNS,
	})
}

func TestJudgeCauses(t *testing.T) {
	same := judged(0.93, LaneSpec, "product-headphones-03", LaneSpec, "product-headphones-03")
	for _, c := range []struct {
		name       string
		d          NamespaceDecision
		sim        float64
		answer     string
		texts, ids []string
		want       string
		wantGate   bool // the gate ran, so Support is non-nil
	}{
		{"served", same, 0.93, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs, CauseNone, true},
		{"below tau", judged(0.50, LaneSpec, "a", LaneSpec, "a"), 0.50, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs, CauseSimilarity, false},
		{"another namespace", judged(0.93, LaneSpec, "a", LaneSpec, "b"), 0.93, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs, CauseNamespace, false},
		// A2: the namespace alarm must not be hidden by a low similarity.
		{"namespace before similarity", judged(0.50, LaneSpec, "a", LaneSpec, "b"), 0.50, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs, CauseNamespace, false},
		// The lane term of the MIXED rule: equal namespace strings, but the entry is not MIXED.
		{"mixed query, spec entry, equal string", judged(0.93, LaneMixed, "x", LaneSpec, "x"), 0.93, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs, CauseNamespace, false},
		{"mixed query, mixed entry", judged(0.93, LaneMixed, "x", LaneMixed, "x"), 0.93, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs, CauseNone, true},
		// D1: chunk IDs with no text is a stale server, not a verdict.
		{"stale server, nil texts", same, 0.93, cachedAnswer, nil, paraphraseChunkIDs, CauseNotScored, true},
		{"stale server, empty texts", same, 0.93, cachedAnswer, []string{}, paraphraseChunkIDs, CauseNotScored, true},
		{"lexical arm refuses alone", same, 0.93, lexOnlyRefused, paraphraseEvidence, paraphraseChunkIDs, CauseSupport, true},
		{"numeric arm refuses alone", same, 0.93, numericOnlyRefused, paraphraseEvidence, paraphraseChunkIDs, CauseSupport, true},
		{"both arms refuse", same, 0.93, cachedAnswer, warrantyEvidence, warrantyChunkIDs, CauseSupport, true},
	} {
		t.Run(c.name, func(t *testing.T) {
			j := judgeTh.Judge(GateOn, c.d, c.sim, c.answer, c.texts, c.ids)
			if j.Cause != c.want {
				t.Fatalf("cause = %q, want %q", j.Cause, c.want)
			}
			if (j.Support != nil) != c.wantGate {
				t.Fatalf("Support != nil is %v, want %v (the gate runs only after similarity and namespace pass)",
					j.Support != nil, c.wantGate)
			}
			if j.Served() != (c.want == CauseNone) {
				t.Errorf("Served() = %v for cause %q", j.Served(), c.want)
			}
		})
	}
}

// The consistency rule of design.md 4: Judge must agree with DecideLane about everything DecideLane
// decides, on every input including the ones that break comparisons (NaN) and the ones that break
// namespaces (empty strings, a lane mismatch with equal strings). If either function is edited and
// they drift, this fails; nothing else would.
func TestJudgeAgreesWithDecideLane(t *testing.T) {
	sims := []float64{math.NaN(), math.Inf(1), math.Inf(-1), -1, 0, 0.8499999, 0.85, 0.8500001, 1, 2}
	lanes := []Lane{LaneSpec, LanePolicy, LaneMixed}
	nss := []string{"", "a", "b"}
	for _, sim := range sims {
		for _, ql := range lanes {
			for _, el := range lanes {
				for _, qn := range nss {
					for _, en := range nss {
						d := judged(sim, ql, qn, el, en)
						// Evidence that the gate admits, so the only way to a refusal is the lane rule.
						j := judgeTh.Judge(GateOn, d, sim, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs)
						gateRan := j.Cause == CauseNone || j.Cause == CauseSupport || j.Cause == CauseNotScored
						if d.Reuse != gateRan {
							t.Fatalf("sim=%v q=%s/%q e=%s/%q: DecideLane.Reuse=%v but cause=%q",
								sim, ql, qn, el, en, d.Reuse, j.Cause)
						}
						if d.Reuse && j.Cause != CauseNone {
							t.Fatalf("sim=%v q=%s/%q e=%s/%q: lane rule reuses, admitting evidence, cause=%q",
								sim, ql, qn, el, en, j.Cause)
						}
						if j.Cause == CauseContainment {
							t.Fatalf("Judge returned CONTAINMENT (theta is outside the served rule, F-K)")
						}
					}
				}
			}
		}
	}

	// A zero decision is "no candidate". Judge must never be called with one, and if it is, the
	// answer is NAMESPACE, never NONE: a missing candidate must not be servable.
	if j := judgeTh.Judge(GateOn, NamespaceDecision{}, 0.99, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs); j.Cause != CauseNamespace || j.Served() {
		t.Errorf("zero NamespaceDecision: %+v, want NAMESPACE and not served", j)
	}
}

// Review N1: the cascade serves on Served(), which is Cause == NONE. An unscored verdict does not
// "refuse", so a rule written as "serve unless an arm refuses" would serve a stale server. This test
// is the one that notices.
func TestJudgeServedIsCauseNoneOnly(t *testing.T) {
	d := judged(0.93, LaneSpec, "a", LaneSpec, "a")
	j := judgeTh.Judge(GateOn, d, 0.93, cachedAnswer, nil, paraphraseChunkIDs)
	if j.Support == nil || j.Support.Scored() {
		t.Fatalf("setup: a stale server must reach the gate and come back unscored: %+v", j.Support)
	}
	if j.Support.Refuses() {
		t.Fatalf("setup: an unscored result does not refuse, which is exactly why Served must not be !Refuses()")
	}
	if j.Served() {
		t.Errorf("a stale server was served (cause %q)", j.Cause)
	}
	for _, cause := range []string{CauseSimilarity, CauseNamespace, CauseContainment, CauseSupport, CauseNotScored, ""} {
		if (Judgement{Cause: cause}).Served() {
			t.Errorf("Served() is true for cause %q", cause)
		}
	}
	if !(Judgement{Cause: CauseNone}).Served() {
		t.Error("Served() is false for NONE")
	}
}

// Both arms always run and are reported separately (spec acceptance 7): a lexical refusal still
// carries the numeric verdict, and the reverse.
func TestCheckSupportRunsBothArms(t *testing.T) {
	lex := CheckSupport(lexOnlyRefused, paraphraseEvidence, paraphraseChunkIDs)
	if !lex.Lex.Refuses() || lex.Numeric.Refuses() || !lex.Numeric.Scored || !lex.Refuses() {
		t.Errorf("lexical-only: lex=%+v numeric=%+v", lex.Lex, lex.Numeric)
	}
	if lex.Lex.Score != 0 || lex.Lex.ContentTokenCount != 6 {
		t.Errorf("lexical-only fixture drifted: %+v, want score 0 over 6 content tokens", lex.Lex)
	}

	num := CheckSupport(numericOnlyRefused, paraphraseEvidence, paraphraseChunkIDs)
	if num.Lex.Refuses() || !num.Numeric.Refuses() || !num.Lex.Scored || !num.Refuses() {
		t.Errorf("numeric-only: lex=%+v numeric=%+v", num.Lex, num.Numeric)
	}
	if num.Lex.Score != 0.9 || num.Numeric.Unsupported != 1 {
		t.Errorf("numeric-only fixture drifted: lex=%v unsupported=%d, want 0.9 and 1", num.Lex.Score, num.Numeric.Unsupported)
	}

	ok := CheckSupport(cachedAnswer, paraphraseEvidence, paraphraseChunkIDs)
	if ok.Refuses() || !ok.Scored() {
		t.Errorf("the measured paraphrase must be scored and admitted: %+v", ok)
	}

	// Stale server: neither arm scores, so the pair is unscored and does not refuse.
	stale := CheckSupport(cachedAnswer, nil, paraphraseChunkIDs)
	if stale.Scored() || stale.Refuses() {
		t.Errorf("stale server: %+v, want unscored and not refusing", stale)
	}
	// EACH arm must see this request's chunk IDs. The pair is unscored if either arm is, so checking
	// only the pair would let one arm lose the IDs and read a stale server as "scored 0".
	if stale.Lex.Scored || stale.Numeric.Scored {
		t.Errorf("stale server: lex.Scored=%v numeric.Scored=%v, want both false", stale.Lex.Scored, stale.Numeric.Scored)
	}
}

func TestCauseValuesArePinned(t *testing.T) {
	// These strings are the values of interfaces.md H's refusal_cause. They reach disk, and an
	// analysis script compares against them, so a rename is a contract change (ADR-009).
	want := map[string]string{
		CauseNone: "NONE", CauseSimilarity: "SIMILARITY", CauseNamespace: "NAMESPACE",
		CauseContainment: "CONTAINMENT", CauseSupport: "SUPPORT", CauseNotScored: "NOT_SCORED",
	}
	for got, w := range want {
		if got != w {
			t.Errorf("cause constant = %q, want %q", got, w)
		}
	}
	if len(want) != 6 {
		t.Errorf("%d distinct causes, want 6", len(want))
	}
}

// BenchmarkJudge: both arms on the pinned paraphrase evidence, the gated hit path. Not a
// measurement of the system (design.md 7); the number goes in approvals.md.
func BenchmarkJudge(b *testing.B) {
	d := judged(0.93, LaneSpec, "a", LaneSpec, "a")
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		if j := judgeTh.Judge(GateOn, d, 0.93, cachedAnswer, paraphraseEvidence, paraphraseChunkIDs); !j.Served() {
			b.Fatal("benchmark input stopped being served")
		}
	}
}
