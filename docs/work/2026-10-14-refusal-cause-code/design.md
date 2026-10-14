# Design — refusal cause code (super-plan item 2.3)

Revision 2, 2026-10-14. Revision 1 was reviewed by the opus `design-reviewer` (`review.md`: sound
with changes, 1 blocker, 4 should-fix, 6 notes). All design changes are in this revision. The ten
questions the review raised were **all answered "as recommended" by the author on 2026-10-14**
(`approvals.md`); where this design depends on one, it says **[Q#]**. Written in plain English;
names, numbers and frozen values are exact.

## Changes since revision 1

- **F1 (blocker).** A refused record pairs the candidate's `source_overlap` with the *new* entry's
  `entry_id` and `entry_sources`. §6 says so in the contract; §4 adds `candidate_entry_id` and
  `candidate_sources` **[Q1]**.
- **F2.** `NOT_SCORED > 0` is not "INCOMPLETE" (rule 6 has no code for it). §6 and §7 add a separate
  rule and one ERROR log line **[Q2]**.
- **F3.** §10 adds part (c) to the real-answer sample, names the unit list as a frozen knob, and
  states how small the sample is.
- **F4.** §11 adds a third test seam for `NAMESPACE`.
- **F5.** The band-share wording is fixed (§6).
- **N1–N6.** §4 (serve rule, 2.4 shape), §6 (offline reading rules), §9 (NaN, zero-chunk write path,
  k=1), §11 (new unknowns).

## 1. The design in one paragraph

One new pure function in `reuse/`, `Thresholds.Judge`, takes the lane verdict, the similarity and the
cached answer with the fresh evidence. It returns **one cause** and the two support verdicts. The
cascade calls it once per judged candidate and serves only when the cause is `NONE`. The handler
copies the cause, the two support values and the candidate's identity into the log record **before**
the miss path, so a shed, abandoned or failed request keeps its Tier-2 cause. A zero-chunk retrieval
is stopped at the top of `tryTier2`, before any namespace is derived. §H goes to v0.13 and ADR-009
records the change.

## 2. Decisions this design rests on

Status of every row: **confirmed by the author, 2026-10-14** ("yes" to all ten recommendations).
The words "recommended" and "proposed" in the table are the history of each row.

| # | Decision | Status |
| :-- | :--- | :--- |
| D1 | Chunk IDs with no evidence text → **refuse, cause `NOT_SCORED`**, both support fields `null` | recommended; reviewer: sound. **[Q5]** |
| D2 | Served = `NONE`. No candidate judged = `null` | recommended; reviewer: sound. **[Q6]** |
| D3 | The gate is **always on** in 2.3. Item 2.4 adds **one parameter to `Judge`**, with no second code path | recommended; reviewer: sound. **[Q7]** |
| A1 | Warranty case = `MISS`, cause `null`; a synthetic case reaches `SUPPORT` | **accepted** by the author, 2026-10-14 |
| A2 | Order: `NAMESPACE` → `SIMILARITY` → (`CONTAINMENT`) → `SUPPORT` / `NOT_SCORED` → `NONE` | proposed; reviewer: right for the alarm, no effect on false-hit counts. **[Q4]** |
| N1 | The decision lives in `reuse/` (pure, stdlib only); the cascade only passes values in | this design |
| N2 | Causes are plain strings; `telemetry` never imports `reuse` | this design |
| N3 | The three required fields are pointers **without** `omitempty`; the two candidate fields are extensions with `omitempty`, like `reuse_rule` | this design |
| N4 | No `t_support_ms` in 2.3 (cost stated in §7) | this design |

Why A2 puts `NAMESPACE` first: the namespace is enforced by the search, so a namespace refusal
means Redis and Go disagree. If `SIMILARITY` won when both apply, that alarm would count too few.

## 3. Flow

```
Ask
 ├─ Tier 1 miss
 ├─ embed ‖ retrieve                      (concurrent, unchanged)
 └─ tryTier2(productID, vec, retrieved)
      1  vec == nil || retrieved == nil              → {}   cause null   (unchanged)
      2  len(retrieved.ChunkIDs) == 0      [NEW]     → {}   cause null
      3  Classify, Namespace; QueryNS == ""          → {}   cause null   (unchanged)
      4  NearestTier2InNamespace(k=1): error / none  → {}   cause null   (unchanged)
      5  DecideLane → NSDecision                     (unchanged)
      6  sim ≥ τ → EnteredBand + containment counterfactual   (unchanged)
      7  Judge(NSDecision, sim, c.Entry.Answer,
               retrieved.Texts, retrieved.ChunkIDs)  [NEW]  → Cause, Support
      8  Served = (Cause == NONE)                    [NEW]
 Ask
      rec.Similarity, rec.SourceOverlap, rec.EnteredBand, rec.ReuseRule   (unchanged)
      rec.RefusalCause, rec.SupportLex, rec.SupportNumericOK,
      rec.CandidateEntryID, rec.CandidateSources        [NEW, before the miss path]
      if t2.Served → TIER2_HIT path   (body unchanged)
      else         → miss path        (unchanged)
```

Step 7, inside `Judge`:

```
nsOK := d.Match && (d.Rule != RuleComposite || d.LaneMatch)
!nsOK                    → NAMESPACE      (gate not run)
!(similarity >= t.Tau)   → SIMILARITY     (gate not run; written positively so NaN refuses)
sr := CheckSupport(answer, texts, ids)    // BOTH arms always run, never summed
!sr.Scored()             → NOT_SCORED     (a stale server; values are not logged)
sr.Refuses()             → SUPPORT
otherwise                → NONE
```

`CONTAINMENT` is never returned. θ is not in the served rule (F-K), so a containment refusal cannot
happen. It stays in the enum for the day F-K has an owner. It is **absent, not zero** (see §6).

## 4. Function contracts

All in `gateway/internal/reuse/`, standard library only, no I/O (`architecture.md` §2).

```go
// cause.go  (new)
const (
    CauseNone        = "NONE"
    CauseSimilarity  = "SIMILARITY"
    CauseNamespace   = "NAMESPACE"
    CauseContainment = "CONTAINMENT" // never returned while θ is outside the served rule (F-K)
    CauseSupport     = "SUPPORT"
    CauseNotScored   = "NOT_SCORED"
)

type SupportResult struct{ Lex SupportVerdict; Numeric NumericVerdict }
func CheckSupport(answer string, texts, retrievedChunkIDs []string) SupportResult
func (r SupportResult) Scored() bool  // Lex.Scored && Numeric.Scored
func (r SupportResult) Refuses() bool // Scored() && (Lex.Refuses() || Numeric.Refuses())

type Judgement struct {
    Cause   string         // never empty
    Support *SupportResult // nil unless the gate ran
}
func (j Judgement) Served() bool { return j.Cause == CauseNone }
func (t Thresholds) Judge(d NamespaceDecision, similarity float64,
    answer string, texts, retrievedChunkIDs []string) Judgement
```

- **Serve rule (review N1).** The cascade serves on `Judgement.Served()`, which is `Cause == NONE`.
  It must **never** be derived from `Refuses()`: an unscored verdict does not refuse, so "serve unless
  an arm refuses" would serve `NOT_SCORED`. `impact.md` (line 280) words it that way; this design
  supersedes that sentence.
- `Refuses()` is the only way to read a verdict. Nothing reads `Score` alone (`support.go:105-106`).
- `retrievedChunkIDs` is **this request's** retrieval. It is never the entry's `SourceChunkIDs`
  (`support.go:145-147`). The function has no parameter for the query text, so the gate cannot read
  it.
- **`Judge` must never be called without a candidate.** A zero `NamespaceDecision` returns
  `NAMESPACE`.
- **Consistency rule, tested:** for every input, `d.Reuse == (cause ∈ {SUPPORT, NOT_SCORED, NONE})`.
  The test names these inputs: NaN, +Inf, `sim == τ`, empty `QueryNS`, MIXED lane with a SPEC entry
  and an equal namespace string, and a zero `NamespaceDecision`.
- **Item 2.4 (review N3).** The gate-off arm is **one more parameter to `Judge`**, and the same
  consistency test runs with both values. A second function or a branch in the cascade would repeat
  the order and could drift.

In `httpapi/cascade.go`, `tier2Outcome` gains `Cause string` (`""` = null), `Support
*reuse.SupportResult` and `Served bool`. `tryTier2`'s signature, `Found`, `EnteredBand`,
`NSDecision`, `Decision` and `stageTimings.Search` keep their meaning (`impact.md` §3.3).

In `telemetry/evallog.go`, after `EnteredBand`:

```go
RefusalCause     *string  `json:"refusal_cause"`
SupportLex       *float64 `json:"support_lex"`
SupportNumericOK *bool    `json:"support_numeric_ok"`
```

and, beside `ReuseRule`, as extensions **[Q1]**:

```go
CandidateEntryID string   `json:"candidate_entry_id,omitempty"`
CandidateSources []string `json:"candidate_sources,omitempty"`
```

In `handler.go` (before the miss path, next to `rec.ReuseRule`): set `RefusalCause` when `t2.Cause !=
""`. Set the two support values only when `t2.Support != nil && t2.Support.Scored()`: `SupportLex =
&Lex.Score`, `SupportNumericOK = &Numeric.Admits()`. Copy into fresh variables, not loop or struct
fields, so no pointer aliases a reused value. Set the candidate fields whenever `t2.Found`. When the
first `NOT_SCORED` of the process is seen, write one ERROR line to the process log, once **[Q2]**.

## 5. What each state logs

`sim` = `similarity`. "–" means null. `band` = `entered_band`.

| State | `cache` | `sim` | `band` | `refusal_cause` | `support_lex` | `support_numeric_ok` |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Tier-1 hit / lookup error | TIER1_HIT / `""` | – | false | – | – | – |
| Embed failed, retrieve failed, zero chunks, empty namespace, search error, nothing in the namespace | MISS… | – | false | – | – | – |
| Nearest in-namespace entry below τ | MISS… | < τ | false | `SIMILARITY` | – | – |
| Filter and Go disagree (alarm) | MISS… | any | sim ≥ τ | `NAMESPACE` | – | – |
| Chunks but no texts | MISS… | ≥ τ | true | `NOT_SCORED` | – | – |
| A support arm refuses | MISS / SHED / ABANDONED / GENERATION_FAILED | ≥ τ | true | `SUPPORT` | number | bool |
| Served | TIER2_HIT | ≥ τ | true | `NONE` | number | bool |

Item 2.4 adds one row: gate off, served = `NONE` with both support fields `–`. On that arm a stale
server cannot be seen (cause `NONE`, null support fields).

## 6. The contract diff, for `/approve contract`

`interfaces.md` v0.12 → v0.13 (§A and §H; §B and the `.proto` are unchanged: `Texts` already crosses
the seam). The seam has two sides here: Python sends nothing new; Go writes five new keys.

**§H record (the example JSON and the field table):**
1. Rewrite the example. Today it is a `TIER2_HIT` with `refusal_cause: "SUPPORT"`, which is
   impossible. Use two consistent records: a served hit (`NONE`, both values present) and a refused
   one.
2. `refusal_cause`: add `NOT_SCORED`. Say: null means no candidate was judged; `NONE` means served;
   order is `NAMESPACE` → `SIMILARITY` → `SUPPORT` / `NOT_SCORED`; `CONTAINMENT` is never written
   until F-K has an owner; `SUPPORT` is judged after similarity ∧ namespace and **not after
   containment**.
3. `support_lex`, `support_numeric_ok`: null now also means not reached, `SIMILARITY`, `NAMESPACE` or
   `NOT_SCORED`. The two gate arms are told apart only among records with cause `NONE`.
4. **`entry_id` and `entry_sources` (review F1).** They name the entry that was **served or
   written**, never the judged candidate on a refusal. On a refused record they describe the new
   MISS entry, whose sources equal `retrieved_chunk_ids`. Any offline overlap or Jaccard computed
   from `entry_sources` must select `cache == TIER2_HIT`. `candidate_entry_id` and
   `candidate_sources` (extensions, present iff a candidate was judged) name the candidate **[Q1]**.
   The comment on `Jaccard` in `rule.go:50-56` is restated to match.
5. `entered_band`: it no longer equals the TIER2_HIT indicator. Restate the alarm (see invariants).
6. `t_search_ms`: add "zero chunks" to the cases where no search ran.
7. `similarity`, `reuse_rule`: also null when the retrieval had zero chunks.
8. Version table and `Current version`: v0.13. ADR-001's pending `latency_ms` wording (§A, "waiting
   for a v0.13 bump") is **left alone**, and v0.13 says so **[Q9]**.

**Invariants, rewritten and added** (each is a check on a finished log):
- **I1** unchanged: `reuse_rule` is present on every judged candidate.
- **I2′** replaces I2: `refusal_cause == "NAMESPACE"` never occurs in a healthy run. Also,
  `entered_band ∧ cache ≠ TIER2_HIT` implies `refusal_cause ∈ {SUPPORT, NOT_SCORED, NAMESPACE}`.
- **I3** `refusal_cause ≠ null` ⇔ `similarity ≠ null` ⇔ `reuse_rule` present ⇔ `candidate_entry_id`
  present.
- **I4** `refusal_cause == "NONE"` ⇔ `cache == "TIER2_HIT"`.
- **I5** `support_lex` and `support_numeric_ok` are both null or both non-null; non-null implies
  cause ∈ {`NONE`, `SUPPORT`}; cause `SUPPORT` implies non-null (until 2.4's gate-off arm).
- **I6** `refusal_cause == "CONTAINMENT"` never occurs. **Absent, not zero:** an analysis must not
  print a `CONTAINMENT` count.

**Metrics (offline reading rules):**
- *% entering the cascade band* is computed from `entered_band` only, as the existing definition
  says. It is the share of `TIER2_HIT`, `SUPPORT` and `NOT_SCORED`, plus `NAMESPACE` records **with
  `entered_band: true`** (review F5).
- The proposal's refusal rate (`Final_Proposal.md` §9) needs a denominator: records with cause in
  {`SUPPORT`, `NONE`} and `source_overlap ≥ θ_run`, with `NOT_SCORED` excluded. θ_run and τ_run are
  **not in `raw/`** until the P1 manifest exists (`cmd/gateway/main.go:207` prints them to the
  process log only).

**New rule 10, apart from rule 6 (review F2) [Q2].** A run with any record whose `refusal_cause` is
`NOT_SCORED` is **not admissible**. It can be decided from `raw/` alone. Two facts belong beside it:
misaligned texts never become `NOT_SCORED` (`ragclient` turns them into a retrieve error, so the
cause is `null`), and chunks whose texts are empty strings *are* scored, get a low `S_lex`, and read
as `SUPPORT`. Only `make seam-check` catches either.

**§A:** the wire shape is unchanged. A support-refused MISS now carries non-null `similarity`,
`source_overlap` and `overlap_decision`, so the sentence "such a candidate is always served, so a
refusal never carries an overlap" is reworded. `similarity` null also covers zero chunks. The pairing
table gains a second MISS row, and the `sources` field of a refused MISS is noted as the new entry's
(the same pairing as F1). No `refusal_cause` is added to the response **[Q10]**.

**ADR-009** records the above in `decisions.md` (and a summary row). It supersedes two statements of
ADR-004 (overlap is null "on every refusal"; its I2) without editing ADR-004, and restates ADR-004's
diagnostic "Tier-2 hit rate ≈ 0 → rule out the filter first": `SUPPORT` and `NOT_SCORED` are now two
more explanations. Its `Invalidates:` line: *no citable run; logs written before the 2.3 commit
carry `TIER2_HIT`, `entered_band` and `source_overlap` under an older meaning, and have none of the
five new keys.* One question it must answer: does a dev-v0 log count as "the first logged run" for
the frozen rows (`decisions.md:71-72`)? Recommended: **no**, and ADR-009 says the trigger is the
first run on v1 **[Q8]**.

## 7. The measurement change, for `/approve experiment`

- **What changes.** The served Tier-2 decision, so the Tier-2 hit rate, the tier mix, the band share
  and *false hits by cause* all move. Two logs from before and after the 2.3 commit must not share a
  figure.
- **What it invalidates.** No citable run. `footprint-20261006-b`'s 250 `TIER2_HIT` were served with
  no gate (`impact.md` §2).
- **Refusal rate.** See §6, "Metrics".
- **`NOT_SCORED > 0`** means a stale server answered some request. Under rule 10 the run is not
  admissible. This is a separate rule from rule 6, because rule 6 is computed at shutdown from the
  writer's counters and nothing counts `NOT_SCORED` there **[Q2]**.
- **Gate latency.** About 30 µs for both arms (`impact.md` §9; the reviewer re-ran the benchmarks:
  about 14 µs per arm, matching). That is about 0.2 % of a Tier-2 request, **inferred, not
  measured**: the 16 ms it divides by has no `RUN_ID`. It has no span, so it lands in `t_total −
  Σ t_*`. The proposal wants it reported as its own component. Not added in 2.3; Phase 7's μ_hit
  with the gate on against off measures it.
- **What a support refusal leaves behind.** With `candidate_entry_id` and `candidate_sources`,
  nothing is lost. Without them the agreement metric can only use served hits, which the gate has
  already filtered, and a refusal cannot be audited. `raw/` is write-once, so a field missing from a
  run is missing forever **[Q1]**.

## 8. Failure modes, silent ones first

| # | What goes wrong | Why it is silent | Guard |
| :-- | :--- | :--- | :--- |
| F1 | A refused record pairs the candidate's overlap with the new entry's sources, so offline Jaccard reads 1.0 | plausible number, no error | §6 item 4; `candidate_sources` [Q1] |
| F2 | A stale server is logged as `SUPPORT`, or as null like the gate-off arm | both look like gate behaviour | cause `NOT_SCORED`; rule 10; acceptance 4 |
| F3 | The cause is set after the miss path, so SHED, ABANDONED and GENERATION_FAILED lose it | those records look like "no candidate" | set it next to `ReuseRule`; test each outcome |
| F4 | A served hit with cause ≠ `NONE`, or a refusal with `NONE` | the counts still add up | I4 as a test over every row |
| F5 | `Judge` and `DecideLane` disagree after an edit to either | both return a plausible answer | the consistency rule in §4, with named inputs |
| F6 | The §H alarm I2 is left as written | fires on every support refusal, so it gets ignored | rewrite I2 in v0.13 |
| F7 | A cold namespace coded `NAMESPACE` | the cause counts look like a bug in Redis | acceptance 3 |
| F8 | Fields get `omitempty`, so "null" and "key absent" merge | a pre-2.3 log reads as gate-off | N3; a test that the keys render as `null` |
| F9 | The gate is passed the entry's `SourceChunkIDs` | compiles; wrong denominator | `Judge` takes this request's IDs; review check |
| F10 | `req.Question` reaches the gate | would make the gate predictive | `tryTier2` has no query parameter, so it cannot |
| F11 | The serve rule is written as "no arm refuses" | serves `NOT_SCORED` | `Served = (Cause == NONE)`; acceptance 4 |

## 9. Edge cases

- **Empty or stopword-only cached answer.** `S_lex` is 0 (`support.go:163-168`), so it is always
  refused as `SUPPORT`. Accepted: it follows 2.1's rule. The real-answer sample counts how often.
- **Support refusal, then regeneration.** The MISS writes a new entry in the same namespace. The next
  paraphrase may find the old entry again (the search is `k=1`) and be refused again. A refused entry
  is never touched (only a served one is, `handler.go:318`), so it stays the nearest one for its
  group of paraphrases and can refuse each in turn. Out of scope (spec). **How to see it:** the same
  `candidate_entry_id` refused many times in one run (review N6).
- **Coalesced followers.** Each runs its own `tryTier2`, so each has its own cause.
- **Tier-1 promotion** happens only on a served hit, so a refused answer is never promoted.
- **Zero chunks.** `similarity`, `reuse_rule` and `t_search_ms` are null even with a `product_id`.
  Offline: `retrieved_chunk_ids` null with `dataset_epoch_at_retrieval` non-null. A retrieval failure
  has both null. The MISS response's `lane` and `namespace` come from the write path, so the guard
  changes nothing on the wire. The write path still stores a zero-provenance entry under namespace
  `product_id` (`handler.go:416-417`), which a zero-chunk query can no longer reach: under a bounded
  cache it only uses capacity (review N5).
- **NaN similarity** is `SIMILARITY` inside `Judge`. But `encoding/json` refuses NaN, so the line
  fails to encode and the run is INCOMPLETE by rule 6. That already happens today (review N2).
  `support_lex` cannot be NaN or Inf.
- **MIXED lane with a pure-lane entry** is a `NAMESPACE` refusal (lane term). The search filter
  cannot return one, so it is also an alarm.

## 10. How acceptance 10 changes the order

The real-answer sample is plan step 1 and runs **before** any wiring. Three parts, so it looks at
both what the gate should admit and what it should refuse:
- **(a) Floor.** 10–20 generated answers, each scored against its own retrieval.
- **(b) Reuse case.** Pairs where the answer to one question is scored against the retrieval of a
  paraphrase. The five paraphrases in `experiments/k6/mu_hit.js` are real candidates (verify in the
  plan).
- **(c) Negative pairs (review F3).** 5–10 pairs in the same namespace whose correct answers differ
  (another condition, or another attribute of the same product). Count the refusals. Without this
  the sample cannot show that the gate is inert.

Rules fixed before looking:
- **Nothing is tuned.** `τ_s`, the stopwords, the tokenizer, the numeric rules R1–R9 **and the unit
  list** (the one knob still marked draft) stay as they are. The ADR triggers in `decisions.md:71-72`
  fire "after a run has logged", and this sample logs no run, so the letter would allow a quiet edit.
  `approvals.md` therefore records which pinning tests were green when the sample ran, and states
  that any later edit to those comes **after** the sample.
- Each answer's `ContentTokenCount` and `Unitless` are recorded.
- Yes/no questions are reported apart. "no" and "not" are stopwords but "yes" is not, so an answer
  that starts "Yes, …" carries one extra content token the evidence rarely contains; on a 2–3 token
  answer that costs 0.33–0.5 of `S_lex`.
- **n = 10–20 is a go/no-go check, not an estimate.** 0 refusals in 15 still leaves a 95 % Wilson
  upper bound near 20 %.

**The numbers go to the author before step 2 starts.** If the gate refuses most real paraphrases,
that is the proposal's second pre-registered null: a finding, and the author decides whether to
continue.

## 11. Unknowns that still need verifying

1. How real answers do against the gate (§10). Verify: plan step 1.
2. Whether any realistic configuration-4 case reaches `SUPPORT` at all. If none does, the gate is
   inert on dev-v0. Verify: §10 part (c), counting causes through `Ask`.
3. How often a cached answer has no content tokens (always refused).
4. The author's ten questions, **[Q1–Q10]** in `approvals.md`.
5. Whether `make demo` step 3 and `mu_hit.js` tier2 still get a `TIER2_HIT` on their five
   paraphrases. They fail loudly if not.
6. **Test seams (review F4).** `fakeStore.NearestTier2InNamespace` filters by namespace itself
   (`harness_test.go:319-330`), so `NAMESPACE` cannot be reached with it. Three small seams are
   needed, none of which loosens a check (`harness_test.go:5-8`): omit texts, return zero chunks,
   and a fixed-candidate store that ignores the namespace. Alternatively test `NAMESPACE`, and the
   stale-server case, at the `Judge` and `tryTier2` level only. The plan says which.
7. Whether the benchmarks hold at v1 chunk lengths (Phase 3).
8. Whether a Tier-2 record deleted during a search can come back with empty fields (namespace `""`),
   which would be a `NAMESPACE` alarm no filter bug caused. Verify: a live test on redis-stack under
   bounded capacity.
9. **TAG case.** The namespace TAG has no `CASESENSITIVE` (`tier2.go:94`) and RediSearch lowercases
   TAG values by default, while `MatchNamespace` is case-sensitive (`lane.go:232-234`). A
   `product_id` with capitals could turn every candidate into `NAMESPACE`. Verify: one live query
   with `Product-Kettle-01`. A fix, if needed, is outside 2.3.
10. Whether item 6.1 sweeps τ offline from one run. If so, support and overlap values exist only for
    banded candidates, so a τ below `τ_run` cannot be swept with the gate on. Decide in 6.1.

## 12. Out of scope, restated

The switch and the manifest (2.4); θ in the served rule (F-K); configuration 3; a second candidate;
a cause type inside `telemetry`; a guard inside `reuse.Namespace` (it would change the write path's
partition, `handler.go:416-417`); any new §A response field; `t_support_ms`; a shutdown counter in
`cmd/gateway` (unless Q2 is answered that way).
