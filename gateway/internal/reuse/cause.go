package reuse

// The refusal cause (super-plan.md item 2.3): ONE value for every judged Tier-2 candidate, computed
// here so the order of the checks lives in one place. Same constraint as rule.go: standard library
// only, no I/O, so the decision can be falsified in isolation (docs/architecture.md 2).
// Design: docs/work/2026-10-14-refusal-cause-code/design.md.
//
// Causes are plain strings, not a named type. telemetry/ may import nothing from this repository
// (docs/architecture.md), and the same string is what reaches disk as interfaces.md H's
// refusal_cause. TestCauseValuesArePinned pins them: an analysis script compares against them.
const (
	// CauseNone: reuse is served. (Not "no cause recorded": that is a null refusal_cause.)
	CauseNone = "NONE"
	// CauseSimilarity: the namespace matched and the nearest entry is below tau.
	CauseSimilarity = "SIMILARITY"
	// CauseNamespace: the lane or namespace term refused. In configuration 4 the namespace is
	// enforced BY THE SEARCH (ADR-004), so this is reachable only if the Redis filter and Go's check
	// disagree. It is an alarm, never the cause of a cold cache: a request whose namespace holds no
	// candidate is a MISS with no candidate and gets no cause at all.
	CauseNamespace = "NAMESPACE"
	// CauseContainment is never returned. theta is outside the served rule (super-plan.md F-K), so a
	// containment refusal cannot happen. The value stays in the enum for the day F-K has an owner,
	// and it is ABSENT from a log, not zero: no analysis may print a count of it.
	CauseContainment = "CONTAINMENT"
	// CauseSupport: a support arm refused. Judged after similarity and namespace, NOT after
	// containment.
	CauseSupport = "SUPPORT"
	// CauseNotScored: the gate could not run because the RAG service sent chunk IDs with no evidence
	// text (a pre-1.4 server). Refused, so the request is not served on an unchecked answer, and kept
	// apart from SUPPORT so a stale server is not blamed on the gate (item 2.1).
	CauseNotScored = "NOT_SCORED"
)

// SupportResult is the support gate's verdict: both arms, reported separately and never summed.
type SupportResult struct {
	Lex     SupportVerdict
	Numeric NumericVerdict
}

// CheckSupport runs BOTH arms on one (cached answer, fresh evidence) pair. Neither short-circuits:
// the numeric verdict is wanted on every lexical refusal, and the reverse, because the thesis reports
// the arms apart (Final_Proposal.md section 9).
//
// retrievedChunkIDs is THIS request's retrieval, the call that produced texts. It is never the cached
// entry's SourceChunkIDs (see SupportLexical). The query text is not a parameter, so the gate cannot
// read it.
func CheckSupport(answer string, texts, retrievedChunkIDs []string) SupportResult {
	return SupportResult{
		Lex:     SupportLexical(answer, texts, retrievedChunkIDs),
		Numeric: SupportNumeric(answer, texts, retrievedChunkIDs),
	}
}

// Scored reports whether the gate could run. The two arms share one stale-server rule, so they agree;
// requiring both keeps a later edit to one of them from producing a half-scored result.
func (r SupportResult) Scored() bool { return r.Lex.Scored && r.Numeric.Scored }

// Refuses reports whether either arm refused. An unscored result does not refuse, so this is NOT the
// serve rule: use Judgement.Served.
func (r SupportResult) Refuses() bool { return r.Scored() && (r.Lex.Refuses() || r.Numeric.Refuses()) }

// Judgement is Judge's result: the cause, and the gate's verdicts when the gate ran.
type Judgement struct {
	// Cause is never empty. It is one of the Cause* constants other than CauseContainment.
	Cause string
	// Support is non-nil exactly when the candidate cleared the lane rule and tau, so the gate ran.
	// It is non-nil on NOT_SCORED too, with Scored() false: the caller logs null for the values then.
	Support *SupportResult
}

// Served reports whether reuse is served. It is the ONLY serve rule: Cause == NONE. It must never be
// written as "no arm refused" -- an unscored result does not refuse, and a stale server would be
// served (design-review N1; TestJudgeServedIsCauseNoneOnly).
func (j Judgement) Served() bool { return j.Cause == CauseNone }

// Judge gives the cause for ONE judged candidate: d is the lane verdict for it, similarity its cosine
// similarity, answer the cached answer, and texts / retrievedChunkIDs the fresh evidence of THIS
// request's retrieval. It must not be called without a candidate: a zero NamespaceDecision comes back
// as NAMESPACE, never NONE, so a missing candidate cannot be served.
//
// The order is NAMESPACE, then SIMILARITY, then the support gate:
//
//	namespace term fails          -> NAMESPACE    (gate not run)
//	not (similarity >= tau)       -> SIMILARITY   (gate not run; written positively so NaN refuses)
//	gate could not score          -> NOT_SCORED
//	either arm refuses            -> SUPPORT
//	otherwise                     -> NONE
//
// NAMESPACE goes first on purpose: it is an alarm (the search should have made it impossible), and if
// SIMILARITY won when both applied the alarm would count too few. It cannot change a false-hit
// count, since false hits are served records, which all carry NONE.
//
// Consistency with DecideLane, which TestJudgeAgreesWithDecideLane enforces on every input: the
// lane rule reuses exactly when this returns NONE, SUPPORT or NOT_SCORED. The namespace term here is
// the same expression as there (Match, and for the composite rule also LaneMatch), with the same >=.
func (t Thresholds) Judge(d NamespaceDecision, similarity float64, answer string, texts, retrievedChunkIDs []string) Judgement {
	if !(d.Match && (d.Rule != RuleComposite || d.LaneMatch)) {
		return Judgement{Cause: CauseNamespace}
	}
	if !(similarity >= t.Tau) {
		return Judgement{Cause: CauseSimilarity}
	}
	sr := CheckSupport(answer, texts, retrievedChunkIDs)
	switch {
	case !sr.Scored():
		return Judgement{Cause: CauseNotScored, Support: &sr}
	case sr.Refuses():
		return Judgement{Cause: CauseSupport, Support: &sr}
	}
	return Judgement{Cause: CauseNone, Support: &sr}
}
