# Design review — refusal cause code (super-plan item 2.3)

> Written by the opus `design-reviewer` subagent on 2026-10-14 and saved here by the main session
> (the subagent has no write tool). Sections 1 to 4 and the questions are the subagent's text,
> unedited. The main session spot-checked two claims and both hold: **F1** (`cascade.go:130`,
> `handler.go:281-283` and `:529-530`, `rule.go:50-56`) and **F4** (`harness_test.go:319-330`).
> Nothing else was re-run. The last section, "Resolutions", is the main session's.

Reviewed: `design.md` revision 1, 2026-10-14, by the opus `design-reviewer`. I checked it against the code and the contract as they stand at `21e4f1b`. I edited no file. I re-ran the two support benchmarks (results in section 3).

## 1. Verdict

- **Sound with changes.** The shape is right: one pure `Judge` in `reuse/`, the cause copied before the miss path, and the zero-chunk guard before `Classify`. I could not break I2′, I3, I4 or I5 on any code path.
- **Biggest risk (silent).** On a support refusal, one record describes two different entries. `source_overlap` belongs to the judged candidate, but `entry_id` and `entry_sources` belong to the new entry the miss wrote. The planned offline Jaccard/containment check then reads 1.0 on every refusal, and nothing raises an error.
- **Counts:** 1 blocker (contract text only), 4 should-fix, 6 notes.
- Decisions D1, D2, D3 and A2 are sound as recommended. A4 and A5 need answers before `/approve contract`.

## 2. Findings, most severe first

### F1. Blocker (contract text). A refused record pairs two different entries.

*Design change, plus decision A4 for the author.*

**What is wrong.**
- After 2.3, `source_overlap` is non-null on `SUPPORT` and `NOT_SCORED` records (`handler.go:281-283`).
- That value is the judged candidate's containment, because it is computed against `c.Entry.SourceChunkIDs` (`cascade.go:130`).
- On the same record, `entry_id` and `entry_sources` name the new entry that the miss generated (`handler.go:529-530`).
- Before 2.3, a banded record was always a `TIER2_HIT`, whose `entry_sources` is the judged entry (`handler.go:305`). The only exception was the `NAMESPACE` alarm.

**Failure scenario.**
- The repo plans to derive Jaccard offline from `retrieved_chunk_ids` and `entry_sources` (`rule.go:54-56`). The proposal's metric "containment vs. Jaccard agreement" (`Final_Proposal.md:70`) depends on it.
- The miss passes its own retrieval to `Answer` (`handler.go:400`), and the service grounds on exactly those IDs (`server.py:35-36`, `retrieve.py:23-61`). So on a refused leader, `entry_sources == retrieved_chunk_ids`.
- Example: the candidate's sources are `[p#0, p#3]` and the retrieval is `[p#0, p#1, p#2]`. Then `source_overlap = 0.5`, and the gate refuses. The new entry's sources are `[p#0, p#1, p#2]`, so offline containment and Jaccard both read **1.0**.
- Result: every support refusal looks like perfect agreement.
- The HTTP MISS response has the same mismatch: `sources` (the new entry) is shown beside `source_overlap` (the candidate).

**Resolution (smallest).**
1. In v0.13 §H, add a field note: `entry_id` and `entry_sources` name the entry that was **served or written**, never the judged candidate on a refusal. Any re-derivation from `entry_sources` must select `cache == TIER2_HIT`.
2. Restate `rule.go:54-56` to match.
3. Answer A4 with: log `candidate_entry_id` and `candidate_sources` on every judged record, as extensions like `reuse_rule`. Without them the agreement metric can only use hits, which is a sample the gate has already filtered. Support refusals also cannot be audited. `raw/` is write-once, so a field missing from a run is missing forever.

### F2. Should-fix. A stale server looks like the second pre-registered null, and "INCOMPLETE" has no code behind it.

*Design change, plus decision A5 for the author.*

**What is wrong.**
- Design §7 says `NOT_SCORED > 0` makes a run INCOMPLETE "in the sense of §H rule 6".
- Rule 6 is a closed list of failures of the log writer (`interfaces.md:500-504`). It is computed at shutdown from the Logger's counters only (`cmd/gateway/main.go:64-67, :92-104`).
- Nothing counts `NOT_SCORED`, and the contract diff in §6 does not change rule 6.

**Failure scenario.**
- An old `rag.server` (one that sends no texts) answers a run.
- Every candidate that clears τ and the namespace becomes a MISS. On the wire it shows high `similarity` and `source_overlap` with no reason given, because `types.go:32-63` has no cause field. `/stats` and k6 see only the hit rate fall.
- That is exactly the shape of the second null (`Final_Proposal.md:426, :492`).
- The shutdown verdict still says the run is complete. Only `refusal_cause` tells the truth.

**Resolution.**
- Keep D1. Refusing is right: serving would make the run look like the gate-off arm instead.
- Add a §H rule that sits apart from rule 6, because this one can be decided from `raw/` alone: *a run with any `NOT_SCORED` record is not admissible.*
- Add one rate-limited ERROR log line at the first `NOT_SCORED`, the way `Dropped` already does it (`evallog.go:185-187`).
- A shutdown counter in `cmd/gateway` is optional. It would add a package that `impact.md` said is untouched.
- Also write two facts into §H or ADR-009. First, misaligned texts never reach `NOT_SCORED`: `ragclient` turns them into a retrieve error (`retrieve.go:53-54`), which logs cause `null`. Second, chunks whose texts are empty strings are scored, get a low `S_lex`, and read as `SUPPORT`. Only `make seam-check` catches either case.

### F3. Should-fix. The real-answer sample cannot show that the gate is inert, and one knob is not named.

*Design change.*

**What is wrong.**
- Design §10 has two parts: (a) answers against their own retrieval, and (b) an answer against a paraphrase's retrieval. In both, the gate *should admit*. So the sample can show over-refusal, but never "refuses nothing it should refuse".
- That is unknown 2 (design §11.2). A1 made it real: the namespace already closes the measured trap.
- Design §10 freezes τ_s, the stopwords and the numeric rules (`design.md:246`). It does not name the unit list, which is the one knob still marked draft (`support_numeric.go:98-99`, `decisions.md:72`).
- The ADR triggers in `decisions.md:71-72` fire "after a run has logged". This sample runs before any log exists, so by the letter, an edit made after seeing its results needs no ADR.

**Failure scenario.** Phase 2 closes with a gate that is inert in configuration 4, and nobody finds out until Phase 6. Or an edit to a draft list, made after looking at refusals, leaves no trace.

**Resolution.**
- Add part (c): 5–10 pairs in the same namespace whose correct answers differ (another condition, or another attribute of the same product). Count the refusals.
- In `approvals.md`, record which pinning tests were green when the sample ran. State that any later edit to the stopwords, tokenizer or unit list comes after the sample.
- Log `ContentTokenCount` and `Unitless` for each answer.
- Treat n = 10–20 as a go/no-go check only. For example, 0 refusals in 15 still has a 95 % Wilson upper bound of about 20 %.
- Report yes/no questions separately. "no" and "not" are stopwords but "yes" is not (`support.go:27-32`). So an answer starting "Yes, …" carries one extra content token that the evidence rarely contains. With 2–3 content tokens, that costs 0.33–0.5 of `S_lex`. v1 comes from Amazon-PQA, where many questions are probably yes/no (I did not verify the share).
- Change nothing because of what the sample shows. A bad result is a finding for the author.

### F4. Should-fix. `NAMESPACE` cannot be reached with the existing fake store.

*Design change, in the plan.*

**What is wrong.** `fakeStore.NearestTier2InNamespace` filters by namespace itself (`harness_test.go:319-330`). A direct `tryTier2` call goes through the same filter. Design §11.6 lists two new seams (omit texts, zero chunks), not this one.

**Failure scenario.** Acceptance 2's "wrong-namespace candidate" row and acceptance 3 cannot be written. Someone may then "fix" this by loosening the fake, which `harness_test.go:5-8` forbids.

**Resolution.** Add a third seam: a small `cacheStore` in a test file that returns one fixed candidate whatever the namespace. Or test `NAMESPACE` at the `Judge` level only, and say so in the plan.

### F5. Should-fix. The band-share formula is wrong for `NAMESPACE`.

*Design change, one phrase.*

**What is wrong.** `design.md:169-170` says *% entering the cascade band* is now the share of `TIER2_HIT` plus `SUPPORT`, `NOT_SCORED` and `NAMESPACE`. Under A2, `NAMESPACE` is written at any similarity, and the band is set from similarity alone (`cascade.go:128`). So a `NAMESPACE` record below τ has `entered_band: false`.

**Failure scenario.** A reader who computes the band share from the causes counts every below-τ `NAMESPACE` record as banded. The error is small while `NAMESPACE ≈ 0`, but this is a definition sentence in a frozen contract.

**Resolution.** Write "…and `NAMESPACE` records with `entered_band: true`". Or say: compute it from `entered_band` only, as `interfaces.md:530` already defines it.

### N1. Note. The plan must use the design's serve condition, not the one in `impact.md`.

*Design change, in the plan.*

`impact.md:280` says "serve only if `NSDecision.Reuse` holds and neither arm refuses". An unscored verdict never refuses (`support.go:126-136`, `support_numeric.go:50-54`), so that wording would **serve** `NOT_SCORED`. The design's rule, `Served = (Cause == NONE)`, is correct. Acceptance 4 catches the difference; name it in the plan.

### N2. Note. A NaN similarity loses the whole record.

*Note only.*

`Judge` returns `SIMILARITY` for NaN, but `encoding/json` refuses NaN. The line then fails to encode (`evallog.go:167`), counts as a write error, and makes the run INCOMPLETE. This already happens today, because `similarity` is logged now. But design §9's "NaN similarity is `SIMILARITY`" is true only inside `Judge`. `support_lex` cannot be NaN or Inf (`support.go:166-168, :178`).

### N3. Note. The shape for 2.4.

*Decision for the author (D3).*

`Judge`'s signature works for 2.4 if 2.4 adds **one parameter to `Judge`** and the consistency test covers both values. A second function, or a branch in the cascade, would repeat the precedence and could drift. Write this into design §4 now. Also state it in §H now: on the gate-off arm a stale server cannot be seen (cause `NONE` with null support fields), so F2's check works on the gate-on arm only.

### N4. Note. Offline reading rules that §H should state.

*Design change, doc only.*

1. `CONTAINMENT` is **absent, not zero**. No analysis may print a `CONTAINMENT` count. Acceptance 6 should assert that it never appears.
2. The proposal's refusal rate (`Final_Proposal.md:411`) needs a denominator: records with cause in {`SUPPORT`, `NONE`} and `source_overlap ≥ θ_run`, with `NOT_SCORED` excluded.
3. θ_run and τ_run are not in `raw/` until P1's manifest exists. `main.go:207` prints them only to the process log.
4. ADR-009 must also restate ADR-004's diagnostic "Tier-2 hit rate ≈ 0 → rule out the filter first" (`decisions.md:523-525`). `SUPPORT` and `NOT_SCORED` are now two more explanations.

### N5. Note. A side effect of the zero-chunk guard.

*Note only.*

The guard is in the right place. The MISS response's `lane` and `namespace` are unchanged, because they come from the generation (`handler.go:416-417, :536, :548-549`). One effect is not listed. The miss still writes an entry with no provenance under namespace `product_id` (`handler.go:416-417, :436-452`), and a zero-chunk query can no longer reach it. Under a bounded cache that entry only uses up capacity. This matters only if v1 has zero-chunk requests (`impact.md` unknown 6).

### N6. Note. k=1 can make the gate defeat itself.

*Note only. No scope change.*

How it happens:
- A refused entry is never touched; only a served entry is (`handler.go:318`).
- So it stays the nearest entry for its group of paraphrases, and it refuses each paraphrase in turn.
- Meanwhile every miss writes another entry next to it.
- Under the unbounded default it never leaves the cache. Under bounded LRU it ages out.

The evidence that would show it: the same candidate refused many times in one run, with `SUPPORT` counts concentrated on a few candidates. Seeing this needs `candidate_entry_id` (F1).

### Which decisions are expensive to undo

Expensive, because they shape `raw/`, which is write-once:
- **A4.** A field that is not logged cannot be added to a finished run.
- **D2.** The meaning of `null` versus `NONE` is baked into every log.
- **Support only on banded candidates.** See unknown 6.

Cheap:
- **A2.** It can be undone offline from the logged `similarity`, once τ_run is recorded.
- **D1.** It fires only on a broken server, and F2 voids such runs.
- **D3.** Item 2.4 comes next.
- **A3.** It is paperwork.
- **A5.** It is one rule.

## 3. Checked and found sound

- **I2′, I3, I4, I5 hold on every path I traced.**
  - `Found` is set only once a candidate exists (`cascade.go:115-116`). `Entry` is a value, not a pointer (`tier2.go:65-68`), so it is never nil.
  - No error path follows a returned candidate (`cascade.go:113-145`).
  - The cause is copied at `handler.go:291-298`. So SHED (`:496`), ABANDONED (`:519`), GENERATION_FAILED (`:523`) and coalesced followers keep it, because each request runs its own `tryTier2` (`:271`) before `Do` (`:387`).
  - Those three outcomes keep `answer_sha256 == ""`, so I4 is unaffected.
  - A `NAMESPACE` candidate below τ has non-null `similarity`, `entered_band: false` and `reuse_rule` present.
- **`Judge` versus `DecideLane`.** `nsOK` equals `DecideLane`'s namespace term on both paths (`lane.go:283-293, :332-351`). Both use the same receiver's τ and the same `>=` form. NaN, empty namespaces, and MIXED with a non-MIXED entry all agree.
  - Name these inputs in the consistency test: NaN, +Inf, sim == τ, empty `QueryNS`, MIXED with `EntryLane` SPEC and an equal namespace, and a zero `NamespaceDecision`. On the zero decision, `Judge` returns `NAMESPACE`, so it must never be called without a candidate.
  - Optional: `Judge` could take the `LaneInput` and call `DecideLane` itself, so the two calls can never see different similarities.
- **A2.** It is right for the alarm. False hits are served records with cause `NONE`, so the order of refusal causes does not change any false-hit count.
- **D1, D2, D3.** All sound.
- **Both arms always run.** This is required for "decomposed by arm" (`Final_Proposal.md:411`). A short-circuit would hide the numeric verdict on every lexical refusal.
- **JSON.**
  - Pointer fields without `omitempty` render as `null`.
  - Go writes 0.6 as `0.6`, so an offline `support_lex < 0.6` agrees with `Refuses()` (`support.go:134-136`).
  - The new struct order only shifts bytes; every reader decodes into a map.
- **Determinism and scope.** `tryTier2` has no question parameter (`cascade.go:77`). There is no ML, and nothing from the cut list comes back.
- **Hit-path cost.** `Judge` is pure: no lock, no goroutine.
  - I re-ran the benchmarks on the M1: about 14 µs per arm (numeric 7,976 B / 96 allocs; lexical 12,368 B / 286 allocs). This matches `impact.md` §9.
  - The existing `log.Printf` in the cascade (`cascade.go:137`) is a larger shared cost than the gate.
- **Layering.** N2 holds, and there is no new import edge.
- **ADR-004 supersession.** The two statements ADR-009 must supersede are identified correctly (`decisions.md:500-501, :505-511`).

## 4. Unknowns I could not verify

1. **Does the gate refuse anything realistic in configuration 4?** Verify with F3's part (c).
2. **How do real answers score, including yes/no answers?** Verify in plan step 1, with F3's additions.
3. **Is the 0.2 % hit-path share right?** The per-arm cost is measured. The 0.2 % share is not: the 16 ms Tier-2 figure it divides by has no `RUN_ID`, and GC under load and v1 chunk lengths are unmeasured. Verify with Phase 7's μ_hit, gate on against gate off.
4. **Can a Tier-2 hash deleted during a search come back with empty fields?** If so, its namespace is `""` and the result is a `NAMESPACE` alarm that no filter bug caused. Verify with a live test on redis-stack under bounded capacity, or in the RediSearch docs.
5. **TAG case.** The namespace TAG has no `CASESENSITIVE` (`tier2.go:94`). RediSearch lowercases TAG values by default (from its docs; I did not check live). `MatchNamespace` is case-sensitive (`lane.go:232-234`). So a `product_id` with capitals would turn every candidate into `NAMESPACE`: the alarm working, but on bad input. Verify with one live query using `Product-Kettle-01`.
6. **Will item 6.1 sweep τ offline from one run, or run once per point?** If offline, the support and overlap values exist only for banded candidates, so a τ below τ_run cannot be swept with the gate on. Decide in 6.1.

## Questions only the author can answer

Each has the reviewer's recommendation first.

1. **A4.** Log `candidate_entry_id` and `candidate_sources` on every judged record? **Recommend yes.** Other options: `candidate_entry_id` only; or nothing, with F1's doc-only restriction.
2. **A5.** Does any `NOT_SCORED` record make a run inadmissible, checked from `raw/` and announced by one ERROR log line? **Recommend yes.** Other options: also add a shutdown counter in `cmd/gateway`; or no.
3. Add part (c), negative pairs, to the real-answer sample? **Recommend yes.**
4. **A2.** `NAMESPACE` before `SIMILARITY`? **Recommend yes.**
5. **D1.** Refuse with cause `NOT_SCORED`? **Recommend yes.**
6. **D2.** `NONE` when served, `null` when no candidate was judged? **Recommend yes.**
7. **D3.** Gate always on in 2.3, and 2.4 adds one parameter to `Judge` with no second code path? **Recommend yes.**
8. **A3.** Do dev-v0 logs count as "the first logged run"? **Recommend no.** ADR-009 should say the trigger is the first run on v1.
9. Leave ADR-001's `latency_ms` sentence out of v0.13? **Recommend yes**, so ADR-009 changes one thing.
10. Add `refusal_cause` to the HTTP response now? **Recommend no** for 2.3; revisit it in a demo pass.

---

## Resolutions (main session, 2026-10-14)

Every design change goes into `design.md` revision 2. Nothing below was decided by the author yet:
the ten questions are asked in `approvals.md` ("Open — needs the author").

| Finding | Resolution | Where | Needs the author |
| :--- | :--- | :--- | :--- |
| F1 blocker | Field note in §H v0.13 (`entry_*` = served or written, never the candidate); restate the `rule.go:54-56` comment; log `candidate_entry_id` and `candidate_sources` as extension fields, present iff a candidate was judged | design rev 2 §4, §6 | Q1 (A4) |
| F2 | New §H rule 10, apart from rule 6: any `NOT_SCORED` record makes a run inadmissible, decidable from `raw/`; one rate-limited ERROR log line; state the two facts (misaligned texts give cause `null`; empty-string texts give `SUPPORT`) | rev 2 §6, §7 | Q2 (A5) |
| F3 | Add part (c), same-namespace pairs with different correct answers; name the unit list as a frozen knob; record the green pinning tests; log `ContentTokenCount` and `Unitless` per sampled answer; report yes/no answers apart; n is a go/no-go check, with the Wilson bound stated | rev 2 §10 | Q3 |
| F4 | A third test seam (a fixed-candidate store), or test `NAMESPACE` at the `Judge` level only; the plan says which | rev 2 §11 | no |
| F5 | Band-share wording fixed: `NAMESPACE` records with `entered_band: true` only | rev 2 §6 | no |
| N1 | `Served = (Cause == NONE)`, never derived from `Refuses()`; `impact.md:280` is superseded on this point (not edited: it is approved) | rev 2 §4; plan | no |
| N2 | Note a NaN similarity loses the whole record at encode time (already true today) | rev 2 §9 | no |
| N3 | 2.4 adds one parameter to `Judge`, the consistency test covers both values; §H states that a gate-off stale server is invisible | rev 2 §4, §6 | Q7 (D3) |
| N4 | The four offline reading rules go into §H and ADR-009 | rev 2 §6 | no |
| N5, N6 | Noted in the edge cases; N6 is read through `candidate_entry_id` | rev 2 §9 | no |
| Unknowns 4, 5, 6 | Carried into design §11 as things to verify | rev 2 §11 | no |


---

# `/ai-review` of the working diff (2026-10-14, after implementation)

> Written by the `contract-reviewer` subagent on 2026-10-14 and saved here by the main session (the
> subagent has no write tool). The findings F1 to F7 are the subagent's text, unedited, apart from
> line wrapping. The ten "checks" are condensed by the main session to one line each; the full text
> said "checked, sound" for nine and pointed at F1, F3, F5 and F6 for the rest. The main session
> spot-checked F1 and F3 before fixing them (reading `cascade.go`, `cascade_test.go` and the
> reasoning of F3), and both hold. The last section, "Resolutions", is the main session's.

**Verdict.** Clean against the contract; changes needed in tests and docs, none in the code. 0 High,
2 Medium (F1, F2), 5 Low (F3 to F7). The reviewer ran `go vet`, `go build`, `gofmt -l`, `go test -count=1
./...`, `go test -race` on `reuse`, `httpapi` and `telemetry`, the mutation script ("27 edits, 27 red"),
`BenchmarkJudge` three times (29.7 to 29.9 µs, 383 allocs, 20.4 KB), the table parser on the real
question file, and four scratch mutants and two scratch tests on a copy. It edited no repository file.

## Findings, most severe first

### F1. Medium, CONFIRMED. Four "cause is null" exits have no assertion.
- **Where:** `cascade.go` (embed or retrieve failed, empty `QueryNS`, search error). Rule: `spec.md`
  acceptance 2; `design.md` F7; §H I1 and I3.
- **What was missing:** `cause_test.go` asserted a null cause only for a cold namespace, zero chunks and
  the warranty case. `TestCauseOfflineReading`'s "empty namespace" case is really "the search found
  nothing". Embed failure, retrieve failure, search error and `QueryNS == ""` had no assertion.
- **Failure scenario:** an edit codes a search error as `NAMESPACE`, or an embed failure as
  `SIMILARITY`. Records with no candidate then carry a cause, I3 breaks, and the `NAMESPACE` alarm and
  "false hits by cause" are wrong, with no test red. The reviewer applied three such edits in a scratch
  copy; the suite stayed green.
- **Smallest fix:** one table test using the existing fakes, plus the three edits in the mutation script.

### F2. Medium, CONFIRMED. ADR-009 says Phase 2 clause 1 "is met"; row 2.3 is marked done while its own acceptance 10 has not run.
- **Where:** `decisions.md` (ADR-009, "Phase 2 exit clause 1 is met by the arms"); `super-plan.md` row 2.3
  and the progress line. Rule: claims must match evidence; `spec.md` acceptance 10 ("before any wiring").
- **Problem:** through `Ask` the warranty case is a MISS with cause `null`; the arms separate the pair
  only on an authored answer (row 2.1 says none was captured). "Met" is stronger than the evidence and
  stronger than `super-plan.md`'s own "the author's call". The ✅ and "items 2.1, 2.2 and 2.3 are done"
  let the sample drop off the list; the Phase 2 Exit line has no sample clause.
- **Smallest fix:** use `super-plan.md`'s wording in ADR-009; mark row 2.3 "done except acceptance 10" and
  keep the sample as a named item that blocks closing Phase 2.

### F3. Low, CONFIRMED. A mutant called "known equivalent" is not equivalent.
- **Where:** `mutation-check.py` docstring; `cascade.go` `Judge` call. Rule: `design.md` F9, `support.go`
  "never the entry's source IDs".
- **What is wrong:** passing `c.Entry.SourceChunkIDs` instead of `retrieved.ChunkIDs` is not equivalent
  when the candidate has empty provenance and the server is stale (reviewer's scratch test: correct code
  logs `NOT_SCORED`; the mutant logs `SUPPORT` with `support_lex = 0`). Empty-provenance candidates exist
  (a zero-chunk miss writes one).
- **Smallest fix:** one test (a candidate with nil sources plus `textlessRAG` expects `NOT_SCORED`); move
  the mutant into the list.

### F4. Low, CONFIRMED. `candidate_sources` is absent for a candidate with empty provenance, which breaks "present iff a candidate was judged".
- **Where:** `evallog.go` (`omitempty`); `interfaces.md` extension-field row and I3.
- **Effect:** I3 keyed on `candidate_entry_id` still holds, but a reader who tests for the
  `candidate_sources` key undercounts judged candidates, exactly the unprovenanced hits.
- **Smallest fix:** say in §H that `candidate_entry_id` is the presence marker and `candidate_sources` is
  also omitted when empty.

### F5. Low, CONFIRMED. Two different freeze triggers for the support-gate definitions.
- **Where:** `support.go` comment ("Once any run has logged support_lex"); `decisions.md` lexical row
  (the inserted sentence defines "the first logged run" but the row never stated the trigger).
- **Failure scenario:** after a dev-v0 run logs `support_lex`, someone edits the stopwords; the code
  comment says an ADR is needed, the decisions table says it is not.
- **Smallest fix:** update the comment to cite ADR-009; add the trigger sentence to the lexical row.

### F6. Low, CONFIRMED. Statements that the gate is unwired or not built, left in the repo.
- `super-plan.md` rows 2.1 and 2.2 ("**Unwired**"); `Makefile:353` ("the gate is not wired in yet");
  `ragclient/support_live_test.go:26` ("not wired into the cascade", an immutable test file);
  `decisions.md` ADR-004 ("the support gate is not built", history, not to be edited, but ADR-009 should say
  it supersedes **three** statements, not two); `super-plan.md` F-K bullet.
- **Smallest fix:** "wired by 2.3" in rows 2.1 and 2.2; fix the Makefile comment (needs the author's go);
  ADR-009 "three".

### F7. Low, PLAUSIBLE. Forward risks, not tested.
- **C2 completeness is confounded while the gate is always on.** If an edit changes "30 days" to "14 days"
  and a purge is missed, the numeric arm refuses the stale entry, so a completeness check that counts stale
  entries *served* looks clean. Nothing says which arm Phase 4 uses.
- **`make demo` step 3 asserts nothing** (`Makefile:215-265`): a real answer refused by the gate shows as
  MISS, ambiguous between a filter fault (cause `null`) and a support refusal; the response cannot tell
  them apart (Q10 was "no"). `mu_hit.js` tier2 mode does assert `TIER2_HIT`.

## The ten checks (condensed by the main session)
1. §H field by field: sound (keys, types, null rules, `entered_band` on a `NAMESPACE` record). One precision
   gap beyond F4: `entry_id` is `""` on a refused request that was then shed, abandoned or failed.
2. Invariants I1 to I6 and rule 10 on every path: sound; no counter-example from SHED, ABANDONED,
   GENERATION_FAILED, a coalesced follower, a Tier-1 hit, an embed or retrieve failure, zero chunks, an empty
   namespace, a search error or NaN. (The null exits are right by construction but untested: F1.)
3. Serve decision: `handler.go` `if t2.Served` is the only way to a `TIER2_HIT`; bump, touch and Tier-1
   promotion are all inside it; `t1_key`, the epoch stamp and `dep:*`/`entry:*` are untouched.
4. Imports: sound (`reuse` is standard library only; `telemetry` imports nothing from the repository; no cause
   type crosses a package).
5. Query text: sound (`Judge` receives the cached answer and this request's texts and IDs; no query text).
6. Frozen values and rule #10: sound (the diff of `reuse/support*.go`, `rule.go`, `doc.go` is comments only;
   no existing test file touched; the sample file's hash matches). One wording issue: F5.
7. Zero-chunk guard: sound; the write path, Tier-1 key and coalescing key are untouched.
8. Docs: the code matches ADR-009 and v0.13; the problems are F2, F5 and F6.
9. Live sample test: sound (structural assertions only, verifies the hash, writes nothing, parses 16/5/6
   rows, a bad row fails rather than skips, parts b and c score the right pair).
10. Hit-path cost: sound (no new lock or goroutine; about 30 µs, 383 allocs, 20 KB for the two arms).

## Could not verify (reviewer)
Anything live (memory pressure is level 2): the real-answer sample, `make seam-check`, `make demo`,
`mu_hit.js`, so whether the five paraphrases still get a `TIER2_HIT` with the gate on. The RediSearch TAG
case-insensitivity against Go's case-sensitive `MatchNamespace` (`design.md` unknown 9).
`Final_Proposal.md` (gitignored, not read). Whether the current Python server always sends `texts`.

## Resolutions (main session, 2026-10-14)

| Finding | Status | What was done |
| :--- | :--- | :--- |
| F1 | **fixed** | `TestCauseIsNullOnEveryExitWithNoCandidate` (embed failure, retrieve failure, search error; each proves its failure fired) and `TestCauseEmptyNamespaceExitHasNoCauseAndRunsNoSearch` (a direct `tryTier2` call with a chunk ID that has no kind prefix). Three mutants added to `mutation-check.py`; all red. **Side finding:** the existing `TestEmptyNamespaceRunsNoSearch` passes zero chunks and now goes through the zero-chunk guard, not the empty-namespace branch; it is not edited (immutable) and the new test is the one that reaches the branch |
| F2 | **fixed (wording), open item kept** | ADR-009 now says the arms separate the pair only at unit level on an authored answer and that whether this meets clause 1 is the author's call. `super-plan.md`: row 2.3 reads "Done-when passes; acceptance 10 (the real-answer sample) is OPEN and blocks Phase 2", and the progress line says the same. **The sample itself has not run: memory pressure was level 2** |
| F3 | **fixed** | `TestCauseStaleServerWithAnUnprovenancedCandidateIsStillNotScored`; the mutant is in the list and red; the docstring's "known equivalent" claim is corrected in the script |
| F4 | **fixed (contract text)** | §H says `candidate_entry_id` is the presence marker and `candidate_sources` is also absent when empty; the test pins it |
| F5 | **fixed** | `support.go` and `support_numeric.go` comments now cite ADR-009's reading; the lexical frozen row states its own trigger |
| F6 | **partly fixed, rest accepted and recorded** | Fixed: `super-plan.md` rows 2.1 and 2.2, the F-K bullet, ADR-009 "three". **Accepted, for the author:** `Makefile:353` (the Makefile was not unlocked for this item) and `ragclient/support_live_test.go:26` (an existing test file, immutable); ADR-004's own wording is history and stays |
| F7 | **recorded, not built** | Forward notes in ADR-009 and in `super-plan.md` Phase 4 (the completeness run must use the gate-off arm of item 2.4, or read `dep:*`/`entry:*` directly). `make demo` step 3 has no assertion; left to the author with the Makefile |
| `entry_id` precision | **fixed** | §H says `entry_id` is `""` and `entry_sources` null on a refused request that was then shed, abandoned or failed |
