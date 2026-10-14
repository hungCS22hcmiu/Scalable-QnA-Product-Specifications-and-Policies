# Plan — refusal cause code (item 2.3)

Do nothing here until `/approve implementation` (which needs `/approve contract` and `/approve
experiment` first). Smallest change that meets `spec.md`. Design: `design.md` revision 2. All ten
questions were answered "as recommended" on 2026-10-14 (`approvals.md`), so: `candidate_entry_id`
and `candidate_sources` are logged (Q1); a `NOT_SCORED` record makes a run inadmissible (Q2, rule
10); the sample has part (c) (Q3); order `NAMESPACE` → `SIMILARITY` → `SUPPORT` (Q4); a stale server
is refused as `NOT_SCORED` (Q5); served = `NONE`, no candidate = `null` (Q6); the gate is always on
(Q7); dev-v0 logs are not "the first logged run" (Q8); `latency_ms` is left alone (Q9); no
`refusal_cause` in the HTTP response (Q10).

Files this plan may touch:
- **New:** `reuse/cause.go`, `reuse/cause_test.go`, `telemetry/cause_fields_test.go`,
  `httpapi/cause_test.go`, `httpapi/cause_seams_test.go`, `ragclient/support_sample_live_test.go`,
  `mutation-check.py` and `sample-*.md` in this trail.
- **Edited:** `httpapi/cascade.go`, `httpapi/handler.go`, `telemetry/evallog.go`, comments only in
  `httpapi/types.go`, `reuse/support.go`, `reuse/support_numeric.go`, `reuse/rule.go`,
  `reuse/doc.go`; `docs/contracts/interfaces.md`, `docs/decisions.md`, `docs/super-plan.md`,
  `docs/architecture.md`, `README.md`; this trail.
- **Not:** any existing `*_test.go` (`harness_test.go` included), `cache/`, `ragclient/` non-test
  files, the `.proto`, `rag/`, `cmd/gateway/`, the Makefile, `Final_Proposal.md` (the author's file;
  stale lines are listed in `approvals.md` instead).

**Stop rules.** (1) If any existing test changes outcome, stop and run `/rca`; do not edit the test
(`impact.md` §3 says none should). (2) Step 1 ends with a stop: the numbers go to the author first.

## Step 1 — the real-answer sample (no wiring, no gate in the cascade)

- [x] **1a. Freeze the questions.** Write `sample-questions.md` in this trail and record its
  `sha256` in `approvals.md` **before anything runs**. Three parts (`design.md` §10):
  - (a) floor: 10–20 questions, spread over the SPEC, POLICY and MIXED lanes, yes/no ones marked;
  - (b) the five question/paraphrase pairs in `experiments/k6/mu_hit.js` (lines 71-87), so the
    answer to one is scored against the retrieval of its paraphrase;
  - (c) 5–10 pairs in the same namespace whose correct answers differ.
  Choose them with `rag ask` and `/products`, never by reading `data/` (the Read deny stays).
  Check: the author reads the file. Nothing in it is edited after the first run.
- [x] **1b. Record the starting point** in `approvals.md`: `git rev-parse HEAD`;
  `sysctl kern.memorystatus_vm_pressure_level` (yellow is allowed for this check, because it scores
  text and not time; label it "not citable", and re-read it before the run); the output of
  `go test -count=1 ./internal/reuse` (the pinning tests for the stopwords, tokenizer, numeric
  rules and unit list are green). From here, any edit to those comes **after** the sample.
- [~] **1c. Live sample test.** *(file written and compiled; NOT RUN — memory pressure level 2)* `ragclient/support_sample_live_test.go`, skipped unless
  `RAG_SEAM_ADDR` is set, in the style of `support_live_test.go`. For each question: `Retrieve` and
  `Answer` through the real `ragclient`; score with `SupportLexical` and `SupportNumeric`; print one
  row (question, lane, `S_lex`, `ContentTokenCount`, numeric verdict with `Unitless`, the two
  refusals). Parts (b) and (c) score the answer of the first question against the retrieval of the
  second. It asserts nothing about the gate's verdict: the numbers are logged, not pinned.
  Check: run it once, `go test -count=1 -run TestSupportSample -v ./internal/ragclient`, output kept
  in the trail as `sample-results.md`.
- [ ] **1d. Write the result** *(waiting for 1c to run)* in `approvals.md`: `S_lex` distribution; how many are below 0.6;
  numeric refusals; numeric refusals that the lexical arm admits; yes/no answers apart; part (c)
  refused and admitted counts (an admitted pair with the same evidence chunk is the residual the
  claim carries, not a defect); the Wilson upper bound for any zero count. **Nothing is changed.**
- [ ] **1e. STOP.** *(waiting for 1c–1d)* Report 1d to the author. Steps 2 onward begin only on the author's go. If the
  gate refuses most real paraphrases, that is the second pre-registered null: a finding.

## Step 2 — `reuse/cause.go` (not wired)

Tests first, in `reuse/cause_test.go`:
- [x] `TestJudgeCauses`: one row per state in `design.md` §5 that `Judge` decides: served `NONE`;
  `SIMILARITY`; `NAMESPACE` (pure lane, and MIXED lane against a non-MIXED entry);
  `NAMESPACE` before `SIMILARITY` when both apply; `NOT_SCORED` (chunk IDs, no texts); `SUPPORT`
  by the lexical arm alone; by the numeric arm alone; by both.
- [x] `TestJudgeAgreesWithDecideLane`: for every named input (NaN, +Inf, `sim == τ`, empty
  `QueryNS`, MIXED with a SPEC entry and an equal namespace string, a zero `NamespaceDecision`),
  `d.Reuse == (cause ∈ {SUPPORT, NOT_SCORED, NONE})`. A zero decision gives `NAMESPACE`.
- [x] `TestJudgeServedIsCauseNoneOnly`: a stale server is **not** served (review N1).
- [x] `TestJudgeNeverReturnsContainment`.
- [x] `TestCheckSupportRunsBothArms`: both verdicts are present on a lexical refusal and on a
  numeric one. Use the fixture strings already in `support_test.go` and `support_numeric_test.go`.
- [x] `BenchmarkJudge`. Record ns/op in `approvals.md`. Not a measurement of the system.
Then `cause.go` as in `design.md` §4. *(done; `TestJudgeNeverReturnsContainment` is inside `TestJudgeAgreesWithDecideLane`)* Check: `go test -count=1 ./internal/reuse`; `gofmt -l` empty;
every pre-existing `reuse` test passes unchanged.

## Step 3 — `telemetry` fields

- [x] Tests first, in a **new** file `telemetry/cause_fields_test.go` (the existing nullable-field
  test is not edited): the three pointer fields render as `null`, never absent; `support_lex`
  renders `0.6` as `0.6`; the two candidate fields are absent when empty and present when set; a
  record with all five decodes into a map.
- [x] `evallog.go`: add the five fields after `EnteredBand` / beside `ReuseRule`, exactly as in
  `design.md` §4. Check: `go test -count=1 ./internal/telemetry`.

## Step 4 — the cascade (compute, but the handler still serves as before)

- [x] `cascade.go`: the zero-chunk guard after the `retrieved == nil` check; `tier2Outcome` gains
  `Cause`, `Support`, `Served`; call `Thresholds.Judge` after the band is set, passing
  `c.Entry.Answer`, **`retrieved.Texts`** and **`retrieved.ChunkIDs`** (never
  `c.Entry.SourceChunkIDs`). `tryTier2`'s signature, `Found`, `EnteredBand`, `NSDecision`,
  `Decision` and `stageTimings.Search` keep their meaning (`impact.md` §3.3). Extend the cascade
  log line with the cause.
- [x] Check (the zero-change claim): `go test -count=1 ./internal/httpapi` — **all 44 existing tests
  pass unchanged.** If one does not, stop (rule 1).

## Step 5 — the handler

- [x] `handler.go`, next to `rec.ReuseRule`, **before** the miss path: set `RefusalCause`; the two
  support values only when `t2.Support != nil && t2.Support.Scored()`, copied into fresh variables;
  `CandidateEntryID` and `CandidateSources` when `t2.Found`. Serve on `t2.Served`, not on
  `t2.NSDecision.Reuse`. On the first `NOT_SCORED` of the process write one ERROR line, once (an
  `atomic.Bool` on `Handler`; the zero `Handler` must still work).
- [x] Check: the 44 existing tests still pass; `go vet ./...`.

## Step 6 — new `httpapi` tests

Two new files, no edit to `harness_test.go`. `cause_seams_test.go` holds three wrappers built from
the harness's own fields (`hs.rag`, `hs.store`, `hs.h`): a RAG server that drops `Texts`; one that
returns zero chunks for a known product; and a store whose `NearestTier2InNamespace` ignores the
namespace (it calls the harness `nearest` with a keep-all filter). Each is a test-only scaffold; none
loosens a check (`harness_test.go:5-8`). The wrapper server is started and stopped by the test.

`cause_test.go`, one test per line of `spec.md` acceptance:
- [x] **1.** Paraphrase through `Ask`: `TIER2_HIT`, `NONE`, both support fields non-null. Warranty
  case (a namespace with no entry): `MISS`, cause `null`, **not** `NAMESPACE` or `SUPPORT`.
- [x] **1b.** Synthetic `SUPPORT`, two cases: `headphones.answer` seeded in the kettle namespace
  (lexical refuses, numeric admits); `"a brushed steel body and an automatic shutoff switch rated
  1500 W"` seeded there (lexical admits at 0.75, numeric refuses) — `impact.md` §3.5.
- [x] **2.** A table over every exit of `tryTier2`: cold namespace, search error, embed failure,
  retrieve failure, empty namespace, zero chunks, below τ, wrong-namespace candidate, support
  refusal, served. Each gives the cause `design.md` §5 says. **`CONTAINMENT` never appears.**
- [x] **3.** A cold cache is never `NAMESPACE`; `NAMESPACE` appears only through the fixed-candidate
  store, including `NAMESPACE` before `SIMILARITY`.
- [x] **4.** Stale server (the dropping wrapper): not served, `NOT_SCORED`, both support fields
  `null`, never `SUPPORT`, one ERROR line in the process log.
- [x] **5.** Zero chunks: no `NearestTier2InNamespace` call (`store.calls`), `MISS`, cause `null`,
  `similarity` and `t_search_ms` null, `retrieved_chunk_ids` null with the epoch non-null.
- [x] **6.** Offline: read `requests.jsonl` and check I2′, I3, I4, I5 and I6 on **every** record;
  tell a `SUPPORT` from a `NAMESPACE` by the field alone; the causes sum to the judged candidates.
  Also: a `SUPPORT`-refused request that is then shed, and one whose generation fails, keeps its
  cause and its support values (`design.md` F3); a refused record's `candidate_*` name the old
  entry and its `entry_*` the new one.
- [x] **7.** Both arms independent: covered by 1b.
- [x] Check: `go test -count=1 -race ./internal/httpapi`.

## Step 7 — hand mutation check

- [x] `mutation-check.py` in this trail, like the 2.2 one. Each edit is applied, `go test` run,
  confirmed RED, undone. Edits: swap `NAMESPACE` and `SIMILARITY` · serve on "no arm refuses" ·
  skip the numeric arm after a lexical refusal · pass the entry's `SourceChunkIDs` · drop the
  zero-chunk guard · set the cause after the miss path · add `omitempty` to a pointer field · drop
  the `NOT_SCORED` branch · code a served hit as `null` · code a cold namespace as `NAMESPACE` ·
  drop the consistency check's NaN row · write `CONTAINMENT` somewhere · copy the loop variable's
  address. Record the count in `approvals.md`. If one stays green, add a test and repeat.

## Step 8 — documents

- [x] `interfaces.md` v0.13 exactly as `design.md` §6 (each numbered item and every invariant);
  `Current version` and the version table.
- [x] `decisions.md`: **ADR-009** and its summary row, with `Invalidates:`; it supersedes two
  statements of ADR-004 without editing it, restates ADR-004's "hit rate ≈ 0" diagnostic, answers
  Q8, and records the frozen-table rows for the cause order and the rule-10 condition.
- [x] `super-plan.md`: row 2.3 `✅ Done`, its trail and ADR; rows 2.4 and 2.3 blockers; the Phase 2
  progress line (clause 2 met; clause 1 met by the arms, not the cascade; clause 3 half). Do not
  restate the exit line.
- [x] `architecture.md` (lines 50, 165-168, 203), `README.md` (66-68, 160-162): the gate is wired.
- [x] Code comments that went stale: `cascade.go` (38-41, 44-46, 59-60, 125-127), `handler.go`
  (273-274, 284-286, 300-301), `types.go` (26-31, 56-58), `support.go` (9-10, 157-160),
  `support_numeric.go` (15-16, 70-72), `doc.go`, and `rule.go` (50-56: derive from `entry_sources`
  only on `TIER2_HIT`).
- [x] `approvals.md`: the stale lines in `Final_Proposal.md` (155, 190, 226, 411), for the author.
- [x] Check: `grep -n "v0.12" docs/contracts/interfaces.md` leaves only history; `make check` reads
  consistently.

## Step 9 — verify and close

- [x] `make verify` exit 0 *(run twice, the second after the /ai-review fixes)*, and `cd gateway && go test -count=1 -race ./...`. `gofmt -l gateway/`
  empty. `TestNoThetaSeparatesTheMeasuredPair` and every item 2.1 and 2.2 test pass unchanged.
- [~] If the stack is up: `make support-check` *(NOT RUN: memory pressure level 2; it starts its own rag.server and loads the embedding model. Retrieval is unchanged by this item.)* (retrieval is unchanged, so it should still pass).
- [x] `/ai-review` *(done: 0 High, 2 Medium, 5 Low, all resolved or recorded; `review.md`, last part)*
- [x] `/done` *(run 2026-10-14 at the author's word, with plan steps 1c–1e deferred; see Outcome)*

## Do not

- Change a threshold, `τ_s`, a stopword, the tokenizer, a numeric rule or the unit list.
- Edit an existing test, or loosen a harness check.
- Pass `req.Question` to anything the gate reads, or `c.Entry.SourceChunkIDs` as the retrieval.
- Add the switch, the manifest, θ in the served rule, a second candidate, `t_support_ms`, a
  `refusal_cause` on the HTTP response, or a guard inside `reuse.Namespace`.
- Edit `Final_Proposal.md`.
- Tune anything after step 1 to make a number look better.

## Outcome (2026-10-14, `/done`)

**Shipped.** The support gate is served: `reuse.Thresholds.Judge` returns one refusal cause for every judged
Tier-2 candidate, and the cascade serves only on `NONE`. Five keys join the evaluation log
(`refusal_cause`, `support_lex`, `support_numeric_ok`, `candidate_entry_id`, `candidate_sources`);
`NOT_SCORED` refuses a server that sent no evidence text and makes a run inadmissible (§H rule 10); a
retrieval with no chunks makes no Tier-2 attempt. `interfaces.md` v0.13, ADR-009 (also three frozen-table
rows touched: a new cause row, and the reading of "first logged run" as the first `v1` run, which was Q8).
Evidence: `make verify` exit 0 (run three times, the last at close, nothing SKIPPED inside it); `go test
-count=1 -race ./...` passes; the 44 pre-existing `httpapi` tests passed unchanged after every step and no
existing test file was edited; 18 new `httpapi` tests, 5 in `reuse`, 4 in `telemetry`; 31 hand mutants, all
red; `/ai-review` 0 High, 2 Medium, 5 Low, all resolved or recorded; `BenchmarkJudge` about 29.6 µs and 383
allocs for both arms.

**Deferred — in this item, still open.**
- **Plan steps 1c to 1e: the real-answer sample.** `τ_s = 0.6` has not been looked at on a real generated
  answer, and the numeric arm's refusals on real answers are uncounted. Memory pressure was level 2 (swap 4.2 to
  4.4 GB of 5.1 GB), which the yellow allowance does not cover. The questions are frozen (sha256 in
  `approvals.md`), the live test is written, hashed to that file and skipped, and the command is at the end of
  `approvals.md`. **It blocks closing Phase 2** (`super-plan.md`). Not run: `make support-check`,
  `make seam-check`, the live `TestSupportSample`; retrieval is unchanged, but nothing live was exercised.
- Step order was reversed from `design.md` §10 (sample first) because of that pressure. No rule or threshold
  was touched, so nothing depends on the order, but the stop at 1e (numbers to the author before wiring) did
  not happen.

**Was the scope honest?** Yes. Opened at L; it changed a frozen document (`interfaces.md`), `reuse/`, and the
served path that every Phase 5 to 6 figure reads. One finding for the ladder: a step that needs the live stack
and a memory state the machine may not be in should be a separate task from the code, so it cannot hold
the code hostage. The L scope was right; the plan mixed two kinds of step.

**Contract and frozen values.** `interfaces.md` bumped v0.12 to v0.13. **Prior runs invalidated: none
citable** (`experiments/results/` is empty). Item 1.6's `footprint-20261006-b` served 250 `TIER2_HIT` with
no gate and is not comparable across the 2.3 commit; a log from before the commit lacks the five keys and
carries `TIER2_HIT`, `entered_band`, `source_overlap` and `t_search_ms` under an older meaning. No threshold,
stopword, tokenizer rule, numeric rule or unit changed.

**Phase 2 exit line, run concretely (2026-10-14): NOT closed.**
1. *refuses the warranty case, admits the paraphrase*: the arms do it on the pinned texts
   (`TestSupportLexicalSeparatesTheMeasuredPair`, `TestNumericMeasuredPair`, `TestNumericDoneWhen` PASS) with an
   authored cached answer. Through `Ask` the namespace search refuses the warranty case first, so it is a MISS
   with cause `null`. Whether that meets the clause is the author's call.
2. *every Tier-2 refusal carries a cause code*: met (`TestCauseOfflineReading`,
   `TestCauseIsNullOnEveryExitWithNoCandidate`, `TestJudgeAgreesWithDecideLane` PASS).
3. *both arms independently switchable and recorded*: recorded yes; **switchable no** (`grep support_gate`
   finds nothing in `gateway/` or `experiments/`). Item 2.4.
4. *decisive-similarity regression reproduces*: met (`TestNoThetaSeparatesTheMeasuredPair` PASS).

**Follow-ups worth a task.**
1. **Run the real-answer sample** (`/investigate`, no code): needs green or yellow pressure. Blocks Phase 2.
2. **Item 2.4**: the `support_gate` switch, as one parameter to `Judge`; also fix the Phase 2 exit wording
   ("independently switchable" means the whole gate on or off, not each arm).
3. For the author, no unlock needed from me: `Makefile:353` comment; `make demo` step 3 has no assertion;
   `ragclient/support_live_test.go:26` header; `Final_Proposal.md` lines 155, 190, 226, 411.
4. F-K still has no owner (θ is not in the served rule, so `CONTAINMENT` is never written).
5. Carried forward, not blocking: Phase 4's completeness run must use the gate-off arm (ADR-009); verify the
   RediSearch TAG case-insensitivity against `MatchNamespace`; verify whether a Tier-2 record deleted during a
   search can come back with an empty namespace; check zero-chunk requests and the benchmark at `v1` lengths
   (Phase 3); decide in 6.1 whether τ is swept offline from one run.
