package httpapi

// Item 2.4 (docs/work/2026-10-14-support-gate-switch/): the support gate has an on/off switch, and
// every record names the arm in a required support_gate key. One test per line of spec.md's
// acceptance. Nothing here edits an existing test; the one additive edit to harness_test.go (the
// offArm field and the label check in checkEveryRecord) was confirmed by the author (approvals.md, Q1).
//
// Names say SupportGate, not Gate, because this package's harness already has an unrelated type `gate`
// (a blocking hook for Answer calls).
//
// The harness runs every test at config_id 5 (testConfigID), and interfaces.md H's I8 says
// configuration 5 is defined with the gate on. The off-arm tests below therefore label a "configuration
// 5" run support_gate=off, which an analysis would reject. That is harmless here: I8 is an offline
// reading rule, it is tested on its own below, and the gateway does not check it at start (F-K).

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"testing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/hung/thesis/gateway/internal/admission"
	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/reuse"
)

// useGateOff switches the harness's handler to the ablation arm and tells checkEveryRecord to expect
// it. Call it right after newHarness, before the first ask.
func (hs *harness) useGateOff() {
	hs.h.SupportGate = reuse.GateOff
	hs.offArm = true
}

// --- the offline checks, as functions over decoded records ------------------------------------
//
// They return problems instead of failing, so a test can show the check passes on a real run AND
// fails on a record that breaks it. A check that has never been seen to fail is not a check.

// gateInvariantProblems is interfaces.md H's I7 for one record: support_gate is "on" or "off";
// off means both support fields are null and the cause is neither SUPPORT nor NOT_SCORED; and on, in
// configuration 4 or 5, with cause NONE means the gate scored the candidate, so both fields are set.
// The configuration filter is review S3: a configuration with no gate would log NONE with null fields.
func gateInvariantProblems(m map[string]any) []string {
	var out []string
	raw, present := m["support_gate"]
	gate, _ := raw.(string)
	if !present {
		return []string{"support_gate is missing"}
	}
	if gate != "on" && gate != "off" {
		out = append(out, fmt.Sprintf("support_gate = %v, want \"on\" or \"off\"", raw))
	}
	cause, _ := m["refusal_cause"].(string) // "" when null
	lex, num := m["support_lex"], m["support_numeric_ok"]
	if gate == "off" {
		if lex != nil || num != nil {
			out = append(out, fmt.Sprintf("gate off but support_lex=%v support_numeric_ok=%v", lex, num))
		}
		if cause == "SUPPORT" || cause == "NOT_SCORED" {
			out = append(out, "gate off but cause "+cause)
		}
	}
	if cfg, _ := m["config_id"].(float64); gate == "on" && (cfg == 4 || cfg == 5) && cause == "NONE" {
		if lex == nil || num == nil {
			out = append(out, fmt.Sprintf("gate on, config %v, cause NONE, but support_lex=%v support_numeric_ok=%v", cfg, lex, num))
		}
	}
	return out
}

// configGateProblems is I8: configuration 5 is defined with the gate on.
func configGateProblems(m map[string]any) []string {
	if cfg, _ := m["config_id"].(float64); cfg == 5 && m["support_gate"] != "on" {
		return []string{fmt.Sprintf("config_id 5 with support_gate %v", m["support_gate"])}
	}
	return nil
}

// gateConstancyProblems: support_gate is the same on every record of a run (it is read once at start).
func gateConstancyProblems(recs []map[string]any) []string {
	seen := map[string]bool{}
	for _, r := range recs {
		g, _ := r["support_gate"].(string)
		seen[g] = true
	}
	if len(seen) > 1 {
		return []string{fmt.Sprintf("support_gate takes %d values in one run: %v", len(seen), seen)}
	}
	return nil
}

// coldStartProblems is interfaces.md H's I9 (rule 11), read from a finished log alone: every entry_id
// on a TIER1_HIT or TIER2_HIT record, and every candidate_entry_id, equals the entry_id of some MISS
// record of the same run. Compared as SETS: a hit can be logged before the MISS that wrote its entry.
// A violation means the run met an entry it did not write.
func coldStartProblems(recs []map[string]any) []string {
	written := map[string]bool{}
	for _, r := range recs {
		if r["cache"] == "MISS" {
			if id, _ := r["entry_id"].(string); id != "" {
				written[id] = true
			}
		}
	}
	var out []string
	for _, r := range recs {
		if cache, _ := r["cache"].(string); cache == "TIER1_HIT" || cache == "TIER2_HIT" {
			id, _ := r["entry_id"].(string)
			switch {
			case id == "":
				out = append(out, fmt.Sprintf("%s record with no entry_id", cache))
			case !written[id]:
				out = append(out, fmt.Sprintf("%s on entry %s, which no MISS record of this run wrote", cache, id))
			}
		}
		if id, ok := r["candidate_entry_id"].(string); ok && id != "" && !written[id] {
			out = append(out, fmt.Sprintf("candidate %s was judged, and no MISS record of this run wrote it", id))
		}
	}
	return out
}

// The checks above must be able to fail. Each case is one broken record or run.
func TestSupportGateOfflineChecksCanFail(t *testing.T) {
	nonEmpty := func(name string, problems []string) {
		t.Helper()
		if len(problems) == 0 {
			t.Errorf("%s: the check found nothing", name)
		}
	}
	empty := func(name string, problems []string) {
		t.Helper()
		if len(problems) != 0 {
			t.Errorf("%s: unexpected problems: %v", name, problems)
		}
	}

	// I7.
	nonEmpty("key missing", gateInvariantProblems(map[string]any{"config_id": 4.0}))
	nonEmpty("empty value", gateInvariantProblems(map[string]any{"support_gate": "", "config_id": 4.0}))
	nonEmpty("capital letters", gateInvariantProblems(map[string]any{"support_gate": "ON", "config_id": 4.0}))
	nonEmpty("off, but a support value", gateInvariantProblems(map[string]any{"support_gate": "off", "support_lex": 1.0, "support_numeric_ok": true}))
	nonEmpty("off, but SUPPORT", gateInvariantProblems(map[string]any{"support_gate": "off", "refusal_cause": "SUPPORT"}))
	nonEmpty("off, but NOT_SCORED", gateInvariantProblems(map[string]any{"support_gate": "off", "refusal_cause": "NOT_SCORED"}))
	nonEmpty("on, config 4, NONE, no support values", gateInvariantProblems(map[string]any{"support_gate": "on", "config_id": 4.0, "refusal_cause": "NONE"}))
	empty("off, NONE, null values", gateInvariantProblems(map[string]any{"support_gate": "off", "config_id": 4.0, "refusal_cause": "NONE", "support_lex": nil, "support_numeric_ok": nil}))
	empty("on, NONE, both values", gateInvariantProblems(map[string]any{"support_gate": "on", "config_id": 4.0, "refusal_cause": "NONE", "support_lex": 0.9, "support_numeric_ok": true}))
	// Review S3: a configuration with no gate logs NONE with null fields, and it is not an I7 failure.
	empty("config 3 with no gate", gateInvariantProblems(map[string]any{"support_gate": "on", "config_id": 3.0, "refusal_cause": "NONE", "support_lex": nil, "support_numeric_ok": nil}))

	// I8.
	nonEmpty("config 5 labelled off", configGateProblems(map[string]any{"config_id": 5.0, "support_gate": "off"}))
	empty("config 5 labelled on", configGateProblems(map[string]any{"config_id": 5.0, "support_gate": "on"}))
	empty("config 4 labelled off", configGateProblems(map[string]any{"config_id": 4.0, "support_gate": "off"}))

	// Constancy.
	nonEmpty("two arms in one run", gateConstancyProblems([]map[string]any{{"support_gate": "on"}, {"support_gate": "off"}}))
	empty("one arm in one run", gateConstancyProblems([]map[string]any{{"support_gate": "off"}, {"support_gate": "off"}}))

	// I9, including that order does not matter.
	hitFirst := []map[string]any{
		{"cache": "TIER2_HIT", "entry_id": "E1", "candidate_entry_id": "E1"},
		{"cache": "MISS", "entry_id": "E1"},
	}
	empty("a hit logged before the MISS that wrote its entry", coldStartProblems(hitFirst))
	nonEmpty("a TIER2_HIT on an entry nobody wrote", coldStartProblems([]map[string]any{{"cache": "TIER2_HIT", "entry_id": "E9", "candidate_entry_id": "E9"}}))
	nonEmpty("a TIER1_HIT on an entry nobody wrote", coldStartProblems([]map[string]any{{"cache": "TIER1_HIT", "entry_id": "E9"}}))
	nonEmpty("a refused candidate nobody wrote", coldStartProblems([]map[string]any{{"cache": "MISS", "entry_id": "E2", "candidate_entry_id": "E9"}}))
	nonEmpty("a hit with no entry_id", coldStartProblems([]map[string]any{{"cache": "TIER1_HIT", "entry_id": ""}}))
}

// --- acceptance 8: the safe zero value --------------------------------------------------------

// The harness builds the Handler as a struct literal and never sets SupportGate, as does every test
// that has existed so far. If the zero value turned the gate off, every 2.3 test would go red; this
// one says why. Both fixtures are ones only the gate refuses, so a handler that skipped the gate
// would serve them.
func TestSupportGateZeroHandlerRunsTheGate(t *testing.T) {
	if got := NewHandler(nil, nil, nil, reuse.Thresholds{}, reuse.LaneBand{}, (*admission.Pool)(nil)).SupportGate; got != reuse.GateOn {
		t.Fatalf("NewHandler leaves SupportGate = %v, want GateOn", got)
	}
	for _, c := range []struct{ name, answer string }{
		{"lexical arm refuses", lexRefusedAnswer},
		{"numeric arm refuses", numericRefusedAnswer},
	} {
		t.Run(c.name, func(t *testing.T) {
			hs := newHarness(t, 1, 0)
			if hs.h.SupportGate != reuse.GateOn {
				t.Fatalf("the harness handler has SupportGate = %v; its literal must not set it", hs.h.SupportGate)
			}
			hs.seedKettle(c.answer, 1)
			call := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
			hs.records(t)

			rec := call.record(t)
			rec.str("cache", "MISS") // the gate refused: a handler with the gate off would have served
			rec.str("refusal_cause", "SUPPORT")
			rec.str("support_gate", "on")
		})
	}
}

// --- acceptance 2: the off-arm through Ask ----------------------------------------------------

// The same two fixtures that 2.3 uses for a SUPPORT refusal, one that only the lexical arm refuses and
// one that only the numeric arm refuses. On: a MISS with cause SUPPORT and both values. Off: the same
// cached answer is served, TIER2_HIT with cause NONE and both support fields null.
func TestSupportGateOffServesWhatTheGateRefuses(t *testing.T) {
	for _, c := range []struct {
		name       string
		answer     string
		wantLex    float64
		wantNumOK  bool
		wantCauseO string
	}{
		{"lexical arm refuses alone", lexRefusedAnswer, 0, true, "SUPPORT"},
		{"numeric arm refuses alone", numericRefusedAnswer, 0.75, false, "SUPPORT"},
	} {
		t.Run(c.name+"/on", func(t *testing.T) {
			hs := newHarness(t, 1, 0)
			seeded := hs.seedKettle(c.answer, 1)
			call := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
			hs.records(t)

			rec := call.record(t)
			rec.str("cache", "MISS")
			rec.str("refusal_cause", c.wantCauseO)
			rec.number("support_lex", c.wantLex)
			rec.boolean("support_numeric_ok", c.wantNumOK)
			rec.str("support_gate", "on")
			rec.str("candidate_entry_id", seeded.EntryID)
		})
		t.Run(c.name+"/off", func(t *testing.T) {
			hs := newHarness(t, 1, 0)
			hs.useGateOff()
			seeded := hs.seedKettle(c.answer, 1)
			call := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
			waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
			waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 1 })
			hs.records(t)

			if call.w.Code != http.StatusOK {
				t.Fatalf("status %d: %s", call.w.Code, call.w.Body)
			}
			resp := call.response(t)
			resp.str("cache", "TIER2_HIT")
			resp.str("answer", c.answer) // the cached answer the gate would have refused

			rec := call.record(t)
			rec.str("cache", "TIER2_HIT")
			rec.str("refusal_cause", "NONE")
			rec.null("support_lex")
			rec.null("support_numeric_ok")
			rec.str("support_gate", "off")
			rec.boolean("entered_band", true)
			rec.str("candidate_entry_id", seeded.EntryID)
			rec.str("entry_id", seeded.EntryID) // served: entry_* IS the candidate
			if n := len(hs.rag.answerCalls()); n != 0 {
				t.Errorf("Answer called %d times on a served hit", n)
			}
		})
	}
}

// --- design F6: a stale server cannot change what the off-arm serves --------------------------

// The off-arm never reads the evidence text, so a server that sends chunk IDs with no text (a pre-1.4
// server) is served exactly as a healthy one, with no NOT_SCORED and no alarm line. On the on-arm the
// same request is NOT_SCORED and refused. Rule 10 therefore has nothing to check on the off-arm
// (interfaces.md H, v0.14): this test is what keeps that statement a rule and not an accident.
func TestSupportGateOffDoesNotReadEvidence(t *testing.T) {
	var logged bytes.Buffer
	log.SetOutput(&logged)
	t.Cleanup(func() { log.SetOutput(os.Stderr) })

	t.Run("off", func(t *testing.T) {
		hs := newHarness(t, 1, 0)
		hs.useGateOff()
		hs.useRAG(t, textlessRAG{hs.rag})
		seeded := hs.seedKettle(kettle.answer, 1)
		call := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
		waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
		waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 1 })
		hs.records(t)

		rec := call.record(t)
		rec.str("cache", "TIER2_HIT")
		rec.str("refusal_cause", "NONE")
		rec.null("support_lex")
		rec.null("support_numeric_ok")
		rec.str("candidate_entry_id", seeded.EntryID)
		if n := strings.Count(logged.String(), "refusal_cause=NOT_SCORED"); n != 0 {
			t.Errorf("%d NOT_SCORED alarm lines on the off-arm, want 0\n%s", n, logged.String())
		}
	})

	t.Run("on", func(t *testing.T) {
		hs := newHarness(t, 1, 0)
		hs.useRAG(t, textlessRAG{hs.rag})
		hs.seedKettle(kettle.answer, 1)
		call := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
		hs.records(t)

		rec := call.record(t)
		rec.str("cache", "MISS")
		rec.str("refusal_cause", "NOT_SCORED") // the contrast: the same request, the gate on
		// The positive control for the zero the off subtest asserted (/ai-review): this same request, on
		// the on-arm, DOES write the alarm line, so the buffer can show one. Without it the zero above
		// would also hold if the line were never written by anyone.
		if n := strings.Count(logged.String(), "refusal_cause=NOT_SCORED"); n != 1 {
			t.Errorf("%d NOT_SCORED alarm lines after the on-arm request, want exactly 1 (the control for the off-arm's 0)\n%s", n, logged.String())
		}
	})
}

// --- acceptance 5: the causes before the gate are the same on both arms -----------------------

func TestSupportGateOffCausesBeforeTheGateAreUnchanged(t *testing.T) {
	t.Run("below tau is SIMILARITY", func(t *testing.T) {
		hs := newHarness(t, 1, 0)
		hs.useGateOff()
		seeded := hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
		call := hs.askNear(t, "Does the Aurora kettle have a lid?", 1, belowTauCos, kettle)
		hs.records(t)

		rec := call.record(t)
		rec.str("cache", "MISS")
		rec.str("refusal_cause", "SIMILARITY")
		rec.null("support_lex")
		rec.null("support_numeric_ok")
		rec.boolean("entered_band", false)
		rec.str("candidate_entry_id", seeded.EntryID)
	})

	t.Run("a wrong-namespace candidate is the NAMESPACE alarm, not served", func(t *testing.T) {
		hs := newHarness(t, 1, 0)
		hs.useGateOff()
		hs.h.Cache = anyNamespaceStore{hs.store}
		wrong := hs.seedHit(headphones, "What do the EarBuds Pop ship with?", 1)
		call := hs.askNear(t, "What is included with the Aurora kettle?", 1, hitCos, kettle)
		hs.records(t)

		rec := call.record(t)
		rec.str("cache", "MISS") // the off branch sits AFTER the namespace check, so this is refused
		rec.str("refusal_cause", "NAMESPACE")
		rec.null("support_lex")
		rec.null("support_numeric_ok")
		rec.str("candidate_entry_id", wrong.EntryID)
	})

	t.Run("a cold namespace is null, and a search ran", func(t *testing.T) {
		hs := newHarness(t, 1, 0)
		hs.useGateOff()
		hs.embedFresh("Is the Aurora kettle cordless?")
		call := hs.ask(t, askReq{question: "Is the Aurora kettle cordless?", productID: kettle.id})
		hs.records(t)

		rec := call.record(t)
		rec.str("cache", "MISS")
		rec.null("refusal_cause")
		rec.null("similarity")
		rec.notNull("t_search_ms")
	})

	t.Run("zero chunks make no Tier-2 attempt", func(t *testing.T) {
		hs := newHarness(t, 1, 0)
		hs.useGateOff()
		hs.useRAG(t, zeroChunkRAG{hs.rag})
		hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1) // a hit if the guard were missing
		call := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
		hs.records(t)

		if n := hs.store.callCount("NearestTier2InNamespace"); n != 0 {
			t.Errorf("%d Tier-2 searches after a zero-chunk retrieval, want 0 (the guard holds on both arms)", n)
		}
		rec := call.record(t)
		rec.str("cache", "MISS")
		rec.null("refusal_cause")
		rec.absent("candidate_entry_id")
	})
}

// --- acceptance 6: every record names the arm -------------------------------------------------

// Every exit of Ask that writes a record, on both arms. The label is already checked on every call of
// every test that calls records(t), by checkEveryRecord; this test makes sure each exit IS reached on
// each arm, and says so out loud. The 405 and 400 exits write no record at all (they return before the
// deferred emit is registered), as before 2.4.
func TestSupportGateKeyOnEveryExit(t *testing.T) {
	const qa, qb = "Is the Aurora kettle cordless?", "Does the Aurora kettle whistle?"
	for _, c := range []struct {
		name           string
		permits, queue int
		wantCache      string
		run            func(t *testing.T, hs *harness) *call
	}{
		{"Tier-1 lookup error", 1, 0, "", func(t *testing.T, hs *harness) *call {
			hs.embedFresh(qa)
			hs.store.fail("Get", errors.New("redis: connection refused"))
			return hs.ask(t, askReq{question: qa, productID: kettle.id})
		}},
		{"TIER1_HIT", 1, 0, "TIER1_HIT", func(t *testing.T, hs *harness) *call {
			hs.store.seedTier1(qa, kettle.id, cache.Entry{
				Answer: kettle.answer, SourceChunkIDs: kettle.answerSources(), ModelUsed: testModel, EntryID: cache.NewEntryID(),
			})
			return hs.ask(t, askReq{question: qa, productID: kettle.id})
		}},
		{"TIER2_HIT", 1, 0, "TIER2_HIT", func(t *testing.T, hs *harness) *call {
			hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
			c := hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle)
			waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
			waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 1 })
			return c
		}},
		{"MISS", 1, 0, "MISS", func(t *testing.T, hs *harness) *call {
			hs.embedFresh(qa)
			return hs.ask(t, askReq{question: qa, productID: kettle.id})
		}},
		{"SHED", 1, 0, "SHED", func(t *testing.T, hs *harness) *call {
			hs.embedFresh(qa, qb)
			g := hs.holdAnswers()
			a := hs.start(askReq{question: qa, productID: kettle.id})
			waitFor(t, "A to hold the permit", func() bool { return hs.h.Admission.InFlight() == 1 })
			b := hs.ask(t, askReq{question: qb, productID: kettle.id})
			g.open()
			a.wait(t)
			return b
		}},
		{"ABANDONED", 1, 1, "ABANDONED", func(t *testing.T, hs *harness) *call {
			hs.embedFresh(qa, qb)
			g := hs.holdAnswers()
			a := hs.start(askReq{question: qa, productID: kettle.id})
			waitFor(t, "A to hold the permit", func() bool { return hs.h.Admission.InFlight() == 1 })
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			b := hs.start(askReq{question: qb, productID: kettle.id, ctx: ctx})
			waitFor(t, "B to queue", func() bool { return hs.h.Admission.Queued() == 1 })
			cancel()
			b.wait(t)
			g.open()
			a.wait(t)
			return b
		}},
		{"GENERATION_FAILED", 1, 0, "GENERATION_FAILED", func(t *testing.T, hs *harness) *call {
			hs.embedFresh(qa)
			hs.rag.onAnswer(func(context.Context) error { return status.Error(codes.Internal, "the model runner crashed") })
			return hs.ask(t, askReq{question: qa, productID: kettle.id})
		}},
	} {
		for _, arm := range []string{"on", "off"} {
			t.Run(c.name+"/"+arm, func(t *testing.T) {
				hs := newHarness(t, c.permits, c.queue)
				if arm == "off" {
					hs.useGateOff()
				}
				call := c.run(t, hs)
				hs.records(t)

				rec := call.record(t)
				rec.str("cache", c.wantCache) // the exit this case is meant to reach
				rec.str("support_gate", arm)
			})
		}
	}
}

// --- acceptance 7: the arm invariant, read from a finished log --------------------------------

// A run per arm that reaches a served hit, both kinds of support refusal (on) or their served
// equivalents (off), a similarity refusal and an empty namespace. I7 holds on every record, the arm is
// constant, and the run is not vacuous: the off-arm really served the three candidates the on-arm
// refused or admitted.
func TestSupportGateInvariants(t *testing.T) {
	for _, arm := range []string{"on", "off"} {
		t.Run(arm, func(t *testing.T) {
			hs := newHarness(t, 1, 0)
			if arm == "off" {
				hs.useGateOff()
			}
			hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
			hs.seedKettle(lexRefusedAnswer, 4)
			hs.seedKettle(numericRefusedAnswer, 7)
			hs.seedHit(kettle, "Does the Aurora kettle have a lid?", 10)

			var calls []*call
			calls = append(calls, hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle))
			calls = append(calls, hs.askNear(t, "What is the kettle made from?", 4, hitCos, kettle))
			calls = append(calls, hs.askNear(t, "How strong is the kettle?", 7, hitCos, kettle))
			calls = append(calls, hs.askNear(t, "Is the kettle lid removable?", 10, belowTauCos, kettle))
			hs.embedder.learn("What do the EarBuds Pop ship with in the box?", basis(130))
			calls = append(calls, hs.ask(t, askReq{question: "What do the EarBuds Pop ship with in the box?", productID: headphones.id}))
			hits := 1
			if arm == "off" {
				hits = 3
			}
			// A served hit bumps hit_count and promotes to Tier 1 in the background; a miss writes its own
			// Tier-1 key. Five requests in either arm: 1 hit + 4 misses on, 3 hits + 2 misses off.
			waitFor(t, "the hit_count bumps", func() bool { return len(hs.store.bumped()) == hits })
			waitFor(t, "the Tier-1 writes", func() bool { return len(hs.store.tier1Written()) == len(calls) })
			hs.records(t)

			count := map[string]int{}
			var recs []map[string]any
			for _, c := range calls {
				rec := c.record(t)
				recs = append(recs, c.rec)
				if p := gateInvariantProblems(c.rec); len(p) != 0 {
					t.Errorf("%s: %v", rec.what, p)
				}
				cause, _ := rec.get("refusal_cause").(string)
				count[cause]++
			}
			if p := gateConstancyProblems(recs); len(p) != 0 {
				t.Error(p)
			}
			want := map[string]int{"NONE": 1, "SUPPORT": 2, "SIMILARITY": 1, "": 1}
			if arm == "off" {
				want = map[string]int{"NONE": 3, "SIMILARITY": 1, "": 1}
			}
			for cause, n := range want {
				if count[cause] != n {
					t.Errorf("arm %s, cause %q: %d records, want %d (all: %v)", arm, cause, count[cause], n, count)
				}
			}
		})
	}
}

// --- rule 11 and I9 ---------------------------------------------------------------------------

// A run that started on an empty cache passes: every entry a hit names was written by a MISS record of
// the same log. The run reaches a Tier-2 hit on a MISS's entry, the Tier-1 hit that its promotion makes
// possible, a coalesced leader and follower (one generation, one entry, two MISS records), and a
// refused candidate. Then the same check FAILS, naming the entry, when a request hits an entry that
// was seeded straight into the store, which is what a warm start from another run looks like.
func TestSupportGateColdStartInvariant(t *testing.T) {
	t.Run("a run that wrote its own cache passes", func(t *testing.T) {
		hs := newHarness(t, 1, 0)
		const q, paraphrase, q2 = "Is the Aurora kettle body made of steel?", "Is the body of the Aurora kettle steel?", "Is the Aurora kettle cordless?"
		hs.embedder.learn(q, basis(1))
		hs.embedder.learn(paraphrase, toward(1, 2, hitCos))

		miss := hs.ask(t, askReq{question: q, productID: kettle.id})
		hit := hs.ask(t, askReq{question: paraphrase, productID: kettle.id})
		waitFor(t, "the hit_count bump", func() bool { return len(hs.store.bumped()) == 1 })
		waitFor(t, "the Tier-1 promotion", func() bool { return len(hs.store.tier1Written()) == 2 })
		again := hs.ask(t, askReq{question: paraphrase, productID: kettle.id}) // the promoted Tier-1 key

		hs.embedFresh(q2)
		g := hs.holdAnswers()
		key := cache.Key(cache.Normalize(q2), kettle.id)
		lead := hs.start(askReq{question: q2, productID: kettle.id})
		follow := hs.start(askReq{question: q2, productID: kettle.id})
		waitFor(t, "the follower to wait on the leader", func() bool { return hs.h.Generations.Waiters(key) == 1 })
		g.open()
		hs.records(t)

		recs := readJSONL(t, hs.logPath)
		if p := coldStartProblems(recs); len(p) != 0 {
			t.Fatalf("a run that wrote its own cache broke I9: %v", p)
		}
		// Not vacuous: the shapes the invariant has to cope with are really in the log.
		miss.record(t).str("cache", "MISS")
		hit.record(t).str("cache", "TIER2_HIT")
		again.record(t).str("cache", "TIER1_HIT")
		missID := miss.record(t).text("entry_id")
		hit.record(t).str("entry_id", missID)
		again.record(t).str("entry_id", missID) // the promotion keeps the entry id
		hit.record(t).str("candidate_entry_id", missID)
		if lead.record(t).text("entry_id") != follow.record(t).text("entry_id") {
			t.Errorf("the leader and its follower disagree on the entry they share")
		}
		if lead.record(t).text("entry_id") == missID {
			t.Errorf("the second generation reused the first entry's id")
		}
	})

	t.Run("a warm start fails, naming the entry", func(t *testing.T) {
		for _, c := range []struct {
			name string
			run  func(hs *harness) (call *call, foreignID string)
		}{
			{"a Tier-2 hit on a seeded entry", func(hs *harness) (*call, string) {
				seeded := hs.seedHit(kettle, "What is the Aurora kettle's body made of?", 1)
				return hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle), seeded.EntryID
			}},
			{"a Tier-1 hit on a seeded key", func(hs *harness) (*call, string) {
				const q = "What is the Aurora kettle made of?"
				stored := cache.Entry{Answer: kettle.answer, SourceChunkIDs: kettle.answerSources(), ModelUsed: testModel, EntryID: cache.NewEntryID()}
				hs.store.seedTier1(q, kettle.id, stored)
				return hs.ask(t, askReq{question: q, productID: kettle.id}), stored.EntryID
			}},
			{"a refused candidate nobody wrote", func(hs *harness) (*call, string) {
				seeded := hs.seedKettle(lexRefusedAnswer, 1)
				return hs.askNear(t, "Which material is the Aurora kettle body?", 1, hitCos, kettle), seeded.EntryID
			}},
		} {
			t.Run(c.name, func(t *testing.T) {
				hs := newHarness(t, 1, 0)
				_, foreign := c.run(hs)
				hs.records(t)

				problems := coldStartProblems(readJSONL(t, hs.logPath))
				if len(problems) == 0 {
					t.Fatalf("the check missed an entry the run did not write (%s)", foreign)
				}
				if !strings.Contains(strings.Join(problems, "\n"), foreign) {
					t.Errorf("the problem does not name the entry %s: %v", foreign, problems)
				}
			})
		}
	})
}
