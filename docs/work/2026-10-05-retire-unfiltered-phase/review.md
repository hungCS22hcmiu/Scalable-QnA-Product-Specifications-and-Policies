# Design review — retire-unfiltered-phase

**Reviewer:** `design-reviewer` (opus), 2026-10-05. Reviews `design.md` revision 2, with `spec.md` rev 2, `impact.md` and `approvals.md`.

**Method:** read-only against the repository. No model was loaded, Ollama was never called, and Redis was not touched. The probes ran in two scratch copies of `gateway/` in the session scratchpad. Nothing in the working tree changed.
- **Today's code.** The design's six new tests (T1–T6), plus one direct-call probe (T7, see S4), were run against the current cascade. This checks that they discriminate.
- **The new code.** §3's contract was implemented **as written in rev 2**, not as `impact.md`'s scratch version. The scratch copy also made every edit §3 and §4 list:
  - `cacheStore` and the fake both lose `NearestTier2`;
  - `TauHigh`, `SimilarityOnly`, `RuleSimilarityOnly`, the §H field and `hitOrMiss` are deleted;
  - the `rule_test.go` and `evallog_test.go` retirements are applied;
  - `ask_test.go` changes at `:287` and `:291` only;
  - the startup guard is added.

  `go vet`, `go build` and the full `httpapi` suite were run, also under `-race`, together with five mutation runs.
- **The guard.** A scratch gateway binary was run with `REDIS_URL`, `RAG_GRPC_ADDR` and `HTTP_ADDR` all pointed at `127.0.0.1:1`.

**CONFIRMED** means checked against the code or by one of those probes. **PLAUSIBLE** means reasoned only. The reviewer has no write tool, so Claude saved this report as returned.

**Verdict: sound with changes. Nothing blocks implementation.**
- The code is the right shape and the smallest one.
- The served-decision invariant holds for §3's contract as written. It was re-run here, not inherited from `impact.md`.
- Every finding is about **what the design says the numbers mean**. S1 must be settled before ADR-004 is written.

## Findings, most severe first

| # | Sev. | Finding | Check | Smallest fix (author decides) |
| :---: | :---: | :--- | :---: | :--- |
| **S1** | should-fix | **R3's expression for "% reaching the provenance check" cannot detect the invariant it is meant to check.**<br>• R3 proposes `retrieved_chunk_ids != null` among past-Tier-1 records.<br>• Retrieval runs concurrently on **every** Tier-1 miss, independently of `tryTier2` (`handler.go:260-270`), and it did so before this change too. So the expression reads the same before and after the retirement.<br>• Probe: under today's code and under the new code, every past-Tier-1 record had `retrieved_chunk_ids` non-null, except the one where retrieval failed.<br>• It is therefore not "1.0 by construction". It is 1 minus the retrieval-failure rate, an availability number. An analyst would see the "invariant" fail on transient gRPC errors, which is the S3 confusion R3 set out to remove.<br>• It is also blind to the regression `Final_Proposal.md:407` guards against. A re-added similarity gate or short-circuit leaves `retrieved_chunk_ids` non-null, so the metric still reads 1.0 | CONFIRMED (code; probe on both versions) | Define the metric as: **among records with `similarity != null`, the share with `reuse_rule` ∈ {`namespace`, `composite`}.**<br>• After 1.3, `similarity` is non-null exactly when a scoped candidate was judged, and `DecideLane` then always ran (D6). So the share is 1.0 by construction. Probe: every record in the suite.<br>• Under today's code it is 4 of 9 similarity-bearing records. The below-τ early return, "settled by similarity alone", leaves `reuse_rule` empty.<br>• A re-added gate before `DecideLane`, or a `similarity_only` rule, drops it below 1.0.<br>• `reuse_rule` is an extension field (`evallog.go:64-67`, `omitempty`), so ADR-004 must say the metric rests on it, and v0.10 should name it in §H. Otherwise a later cleanup can drop it and silently void the check |
| **S2** | should-fix | **Under D2, `entered_band` is identical to `cache == TIER2_HIT`, and the design does not say so.**<br>• The scoped search returns only candidates in the query's namespace.<br>• For SPEC and POLICY, `DecideLane` then reduces to `sim >= τ`. For MIXED, only MIXED writes a `\|` namespace, so the lane always matches.<br>• Hence `Found ∧ c.sim >= τ` ⇔ `NSDecision.Reuse`. The probe confirmed it on every record of the suite under the new code.<br>• Consequences:<br>  – "% entering the cascade band" (`interfaces.md:430`) becomes the Tier-2 hit share. It is not an independent metric until θ (F-K) or the support gate (2.1) joins the served rule.<br>  – No refusal carries `source_overlap` or `overlap_decision` any more.<br>  – The design's restatement of `cascade.go:41-44` ("still true inside a namespace") is false. So are the unlisted comments at `handler.go:276-277`, `:287-289` and `types.go:26-30`, which say a refusal carries overlap, or that the counterfactual "is most informative at a refusal" | CONFIRMED (structure; probe) | Say it in ADR-004 and in the `:485` restatement: until θ or the support gate is served, `entered_band` equals the TIER2_HIT indicator. It then becomes a second free invariant: **`entered_band ∧ cache ≠ TIER2_HIT` can only mean the Redis TAG filter and Go's `MatchNamespace` disagree.** Add the three comments to §3's restatement list, and fix the `cascade.go:41-44` wording to: "a refusal carries its similarity, never an overlap" |
| **S3** | should-fix | **`refusal_cause = NAMESPACE` becomes unreachable in configuration 4, and the v0.10 edit list misses it.**<br>• §H at `interfaces.md:486` (frozen at v0.9), and the "done when" of `super-plan.md` item 2.3 ("a support refusal is distinguishable from a namespace refusal"), both assume the cascade observes a namespace mismatch.<br>• After 1.3 it never does. A cross-namespace lookalike is a MISS with **no candidate**, and `DecideLane`'s namespace check can refuse only on a filter/Go disagreement.<br>• 2.3's implementer will either never emit `NAMESPACE`, or emit it for "no candidate". The second reading turns a cold cache, or an empty namespace, into namespace refusals: a plausible wrong number in "false hits by cause" | CONFIRMED (structure) | Add `:486` to v0.10's edits: in configuration 4 the namespace is enforced by the search, not by a refusal. "No in-namespace candidate" is not a `NAMESPACE` refusal, and the namespace conjunct's effect is counted only by the configurations 3 ⋈ 4 join. At `/done`, put the same sentence in 2.3's row |
| **S4** | should-fix | **M10 (a timed no-op search on `ns == ""`) is caught by no test in the design, and a cheap test exists.**<br>• Mutation run: removing the early return leaves the design's whole suite green.<br>• §4 gives the wrong reason why no fixture reaches the path. The binding reason is that `checkEveryRecord` asserts `rec.str("product_id", …)` (`harness_test.go:1028`), and `Record.ProductID` is `omitempty` (`evallog.go:73`). Any request without `product_id` therefore fails in the harness. With `product_id` set, `Namespace` never returns `""` in any lane. "No policy documents" is irrelevant: a POLICY namespace is non-empty whenever a policy chunk exists.<br>• In production the path *is* reachable: no `product_id` (the demo sends none, `Makefile:231-232`) together with an empty retrieval, or a corpus without kind prefixes | CONFIRMED (mutation run) | Add a direct call in `cascade_test.go`, with no harness change and about 12 lines:<br>`hs.h.tryTier2(ctx, "", float32s(basis(1)), &ragclient.RetrieveResult{DatasetEpoch: testEpoch}, &tm)`, with an entry seeded at `basis(1)`. Assert `!Found`, `!EnteredBand`, `tm.Search == 0` and zero `NearestTier2InNamespace` calls.<br>• Today it fails: found, banded, `Search` = 3 µs, one call.<br>• It passes on the new code, and it catches M10 |
| **S5** | should-fix | **Demo step 4's non-null branch is reachable after 1.3 only on a TIER2_HIT, and it prints "REFUSE".**<br>• §3 keeps "the existing line" whenever `source_overlap` is non-null. That line hard-codes `< theta → REFUSE, generate instead` (`Makefile:263-264`).<br>• By S2, a non-null `source_overlap` now implies the entry was **served**. So the branch states a refusal exactly when none happened, and it also asserts `<` whatever the value is.<br>• This is the same class as the fabricated `0.00` that acceptance 8 exists to stop | CONFIRMED (structure). Which branch Q4 takes is PLAUSIBLE (see U2) | In the non-null branch, print the response's own `.cache` and `.overlap_decision`, with the number formatted by `num`. Do not print a verdict word or a comparator the script did not read |
| N1 | nit | **The guard's test pins the predicate, not the call.**<br>• Deleting `retiredEnv(os.Getenv)` from `main` leaves `main_test.go` green, so M7's "drop the guard" half is uncovered.<br>• "Non-empty" is right. It matches `getenvFloat`'s treatment of `""`, and it is all a `func(string) string` parameter can express; "set" would need `os.LookupEnv`.<br>• The `main_test.go` row asserts the error names "ADR-004", a number not yet allocated in `decisions.md` | CONFIRMED (probe: with the guard first, the binary exits 1 with the message before any dial; an empty value proceeds) | Record `REUSE_TAU_HIGH=0.95` against closed ports, run once, as acceptance 7's evidence. It needs no services and covers the call site. `main_test.go` is then optional. Assert "REUSE_TAU_HIGH" and "retired" rather than the ADR number, or allocate ADR-004's Summary row before writing code |
| N2 | nit | **Gaps in §8's contract and ADR list:**<br>(a) `overlap_decision`, `reuse_rule`, `lane` and `namespace` are not in §A at all (grep), so "`overlap_decision` on §A" edits a row that does not exist;<br>(b) the header (`:3`) and "Current version" (`:499`) also bump;<br>(c) `:448`'s example comment ("consulted provenance");<br>(d) ADR-004 lacks the file's required parts: a category line, **Alternatives** (keep the phase disabled; a display-only global search under D1; retire `entered_band`, option C; build configuration 3 now) and the Summary-table row;<br>(e) the measured `TauHigh` reasons moving from `rule.go` are dev-v0, so the ADR must say they are not citable;<br>(f) one sentence is needed so ADR-004 is not read as ratifying the four-conjunct rule: the served rule stays `sim ∧ namespace` (F-K), `overlap_decision` is configuration 4's support-off verdict, and a run's TIER2_HIT count is not configuration 4's | CONFIRMED (reading) | Add (a)–(f) to §8. For (a), record D7 in ADR-004 only, unless the author wants §A to gain the extension rows |
| N3 | nit | **T1's hit half does not discriminate today's code.** It passes on today's two-search path, because the global call is not counted under the scoped method. A second, global search is caught only at compile time (M1). Only T1's below-τ half fails today | CONFIRMED (probe) | Restate T1's "Catches" column as: a changed namespace argument, and a second scoped call |
| N4 | nit | **The change removes the last in-log witness of a namespace filter that matches nothing.**<br>• Today, a broken TAG filter shows as high `similarity` with `entered_band: true` on MISS records.<br>• After 1.3 it looks like a cold cache: `similarity` null and no Tier-2 hits.<br>• `cache/` has no live test of `NearestTier2InNamespace` on a hyphenated namespace, only `escapeTag` and the empty-namespace refusal. The only live witness is `make demo` step 3 | PLAUSIBLE | Record it in the experiment note: "Tier-2 hit rate ≈ 0 on a warm cache: rule out the filter first". Name step 3 as the witness. No code change; `cache/` stays out of scope |
| N5 | nit | **D6 moves `reuse_rule`'s meaning as well as its coverage.**<br>• `evallog.go:64-67` and `types.go:48-53` say it names the term that **decided**.<br>• On a below-τ refusal it will read `namespace`, although τ refused (probe: below-τ MISS records).<br>• A filter on "`reuse_rule` present" no longer selects hits | CONFIRMED (probe) | Restate it as: "the rule variant that judged the candidate; present iff a candidate was judged; presence is not a hit". This goes into the experiment record, and into S1's §H note |

## The eight questions

1. **Is §2 complete for §3's contract as written? Yes.** The contract was implemented verbatim and the full `httpapi` suite run.
   - Only `:287` and `:291` needed changing.
   - `TestBelowTauDoesNotEnterTheBand` passes unchanged.
   - Everything else passes, also under `-race`.

   On the new ordering:
   - `Classify` and `Namespace` are pure. `QueryLane` and `QueryNS` are read only by the TIER2_HIT response and the log line.
   - The `ns == ""` return replaces a call the real store already answers with nil before reaching Redis (`tier2.go:153-157`). The MISS is the same, with no span and no log.
   - The only new side effects are reporting ones: `reuse_rule` on below-τ refusals (N5), and the stderr log line on those refusals.

   The `retrieved == nil` check coming first is **load-bearing**. In a mutation that derives `ns` from `productID` when retrieval has failed, the request is **served without provenance**. `TestRetrieveFailureDegradesToMiss` and T2 both catch it (CONFIRMED). Keep it first and keep it pinned.
2. **T3 is sound.**
   - One-hot vectors survive JSON and float32 exactly, and the fake's float64 cosine of two identical one-hot vectors is exactly 1. T3 asserted `similarity == 1` with no tolerance, and it passed.
   - The τ override is race-free. It is written before the `go` statement in `start()`, it passes `-race`, and `ask_test.go:741` (`Capacity`) is the precedent.
   - T3 is the **only** test that catches M4 (mutation run).
   - It is a TIER2_HIT, so it must `waitFor` the bump and the promotion before `records()`, as `ask_test.go:173-174` does. T1's hit half, T4 and T5 need the same.
   - Optionally, also assert `overlap_decision: true`.
3. **T4 discriminates.**
   - `hitFixture(kettle)` has sources `[#0, #1]`, a subset of `retrieval(kettle)` = `[#0, #1, #2]`, so the overlap is exactly 2/2.
   - Today's code gives `source_overlap: 0` and `overlap_decision: false` in both the response and the record. The new code gives 1 and true.
   - Fixture used: the query at `toward(1, 2, 0.99)`, headphones at `basis(1)`, and the kettle entry at `around(query, 3, hitCos)`. The response's `answer` shows which entry was served.
4. **U5: keep it, as designed.** It is never serialised, and F-K's fix will move containment into the served decision and restructure this anyway. Deleting it now would also edit `lane_test.go:407-418`, which is outside D4's list. The comment must say it duplicates `Decision.Overlap` and is zero unless `entered_band` is true.
5. **"Closed by structure" is not needed.** S4's direct call costs about 12 lines and catches M10.
6. **Fire on non-empty.** A pure function is fine, but the binary run is what covers the wiring (N1).
7. **R3's reading is not faithful.** See S1. The probe settles it on both versions of the code.
8. See S2, S3 and N2. The experiment record also needs:
   - the `entered_band` ≡ TIER2_HIT identity and the two invariants (S1, S2);
   - N5;
   - N4.

## Unknowns

| # | Status |
| :---: | :--- |
| U1 | **FLAT subset on live Redis** (`c.sim ≤ global.sim`): PLAUSIBLE, and moot. The only exposure is a float discrepancy exactly at τ. Even then, the new code applies τ to the candidate it serves, which is the rule |
| U2 | **Demo Q4 lands in a different policy namespace from Q1**, so it takes the null branch. PLAUSIBLE, from `lane.go:174-177`. It is settled by one `make demo` at green pressure. S5 makes either branch truthful |
| U3 | **The ≈ 1 % hit-path saving** is estimated. Phase 7 measures it from `t_search_ms` |
| U4 | **The live TAG filter on hyphenated slugs** (N4). It is witnessed only by demo step 3 |
| Design U3 and U4 | **Settled.** `TestBelowTau…` is byte-identical and passes. The "both searches" subtest compiles and passes vacuously |

## Checked and found sound

- **The invariant.** It holds for the contract as written (question 1).
- **Every listed edit compiles.** `go vet` is clean. `main.go` and `rule_test.go` lose `math` with no other fallout.
- **The tests discriminate.** Against today's code:
  - T2 fails on 7 fields: `t_search_ms` reads 0.002, an S2-shaped number;
  - T4 fails on 3, T5 on 1 and T6 on 1;
  - T1's below-τ half fails.

  All of them pass on the new code.
- **Mutations.** M3, M4 and A′ are each caught. Running `Decide` on every found candidate is an equivalent mutant, because `Ask` reads `Decision` only when `EnteredBand` is true.
- **No other readers.** Nothing outside `gateway/` reads `entered_band`, `similarity_only_decision`, `overlap_decision` or `t_search_ms`: no analysis script in `experiments/`, and `ui/src` only displays them. Grep finds no `REUSE_TAU_HIGH` in the Makefile, the shell environment, `launchctl` or the LaunchAgents.
- **No principle is violated.**
  - The decision stays a Go rule. There is no model on the hit path, and the query text is not read as a predictive signal.
  - No cut scope returns. Keeping `Store.NearestTier2` as configuration 3's primitive is right.
- **No smaller design exists.** The one optional trim is `main_test.go` (N1).

---

**Summary:** 0 blocking, 5 should-fix (S1–S5), 5 nits (N1–N5).

**Most urgent:** S1, because R3's expression would go into a ratifying ADR as the definition of a thesis metric, and it cannot fail. Then S2 and S3, which are the same root seen from two fields: after 1.3 the cascade never observes a refusal from outside the namespace.

Scratch evidence (session scratchpad, not in the repo): `scratchpad/gw/` (the new code with the review tests in `internal/httpapi/cascade_review_test.go`) and `scratchpad/gw_old/` (today's code).

## Resolutions (2026-10-05)

Every finding above is resolved. None is left open.

| # | Resolution | Where |
| :---: | :--- | :--- |
| S1 | **Fixed, by the author's decision.** R3 was revised to I1: among records with `similarity != null`, the share with `reuse_rule` ∈ {`namespace`, `composite`}. `reuse_rule` is named in §H so that it cannot be dropped silently | `approvals.md` (R3 revised); ADR-004; `interfaces.md` §H metrics paragraph and the `reuse_rule` row |
| S2 | **Fixed.** The identity `entered_band` ≡ TIER2_HIT and invariant I2 are stated, and the comments that claimed a refusal carries overlap are restated | `design.md` §2a; ADR-004; §H `entered_band` note; `cascade.go` (`tier2Outcome`, `EnteredBand`), `handler.go:276-289`, `types.go` (`askResponse`) |
| S3 | **Fixed in the contract**: in configuration 4 the namespace is enforced by the search, not by a refusal, and "no candidate" is not `NAMESPACE`. **At `/done`:** the same sentence goes into item 2.3's row | §H `refusal_cause` note; ADR-004 |
| S4 | **Fixed.** T7 calls `tryTier2` directly. It failed on `HEAD` (found, banded, 3.04 µs, one call) and catches M10 | `cascade_test.go`; `evidence/mutations.md` |
| S5 | **Fixed.** The non-null branch prints only `.cache`, `.overlap_decision` and `.source_overlap`, with no verdict word or comparator. The computed `shared / total` ratio is dropped | `Makefile` step 4; `evidence/demo-step4.txt` |
| N1 | **Fixed.** The binary run is recorded, and grep 3 pins the call site. `main_test.go` asserts `REUSE_TAU_HIGH` and `retired`, not the ADR number | `evidence/startup-guard.txt`; `evidence/mutations.md` (M7a, M7b) |
| N2 | **Fixed:**<br>(a) D7 is recorded in ADR-004 only; §A gains no extension rows;<br>(b) the header and "Current version" are bumped;<br>(c) the `:448` example comment is restated;<br>(d) ADR-004 has its category line, Alternatives and Summary row;<br>(e) the `τ_high` reasons are marked as dev-v0 and not citable;<br>(f) ADR-004 has a "What this does not ratify" paragraph | `interfaces.md`; `decisions.md` |
| N3 | **Fixed.** T1's "Catches" column is restated. Confirmed on `HEAD`: the hit half passes and the below-τ half fails | `design.md` §4; `plan.md` step 1 |
| N4 | **Recorded:** *"Tier-2 hit rate ≈ 0 on a warm cache: rule out the filter first"*, with demo step 3 as the witness. No code change | experiment record (`approvals.md`); ADR-004 |
| N5 | **Fixed.** `reuse_rule` is restated as "present iff a candidate was judged; presence is not a hit" | `evallog.go` `ReuseRule`; `lane.go` `NamespaceDecision.Rule`; §H `reuse_rule` row; experiment record |

# Implementation review — `/ai-review`, 2026-10-05

**Reviewer:** `contract-reviewer` (sonnet). It reviewed the working-tree diff against `5854cbe`: 14
files plus `main_test.go` and `cascade_test.go`. It ran `go vet ./...` and `go test ./...`, both
passing. It edited no file, and Claude recorded its report here.

**Verdict: the diff conforms to `interfaces.md` v0.10 at the seam.** No finding fails silently in
code. Two wording defects in the new docs could each have produced a wrong reading.

## Findings, most severe first

| # | Sev. | Finding | Check | Resolution |
| :---: | :--- | :--- | :---: | :--- |
| C1 | low | **§H's `t_*_ms` note said `t_search_ms` is "null when … the namespace was empty".**<br>The code nulls it only when no search ran: `vec` nil, `retrieved` nil, or `QueryNS == ""`.<br>A namespace that resolves but holds no entry (a cold cache) still runs the search, and so does a Redis error. Both carry a span.<br>A reader taking "empty" to mean "holds no entry" would expect null on a cold-cache MISS, and compute the wrong denominator for search latency | CONFIRMED (`cascade.go`: `t.Search` is set before the error and emptiness checks) | **Fixed.** §H now says *"null exactly when no search ran … a search that ran and found nothing (a cold cache) or errored still carries its span, so a MISS can show `similarity: null` beside a non-null `t_search_ms`"*. The same wording is fixed in `approvals.md`'s experiment record. ADR-004 already said "null where no search ran" |
| C2 | low | **ADR-004 said "`reuse_rule` appears on below-τ refusals too"**, which could be read as the HTTP body.<br>The §H record carries it on every judged candidate. The MISS **response** never sets it (`handler.go`, MISS `askResponse`); only the TIER2_HIT response does.<br>§A does not name `reuse_rule`, so there is no seam break | CONFIRMED | **Fixed.** ADR-004 now reads *"`reuse_rule` in the §H record … The HTTP response carries it only on a TIER2_HIT"*. The experiment record says the same |

## Checked and found clean (reviewer's list, condensed)

- **`similarity`.**
  - It is set only when `t2.Found`, which comes only from the scoped search.
  - It is null on TIER1_HIT, and on an embedding failure, a retrieval failure, an empty namespace and a Redis error.
- **`source_overlap` and `overlap_decision`.**
  - They are set only inside `EnteredBand` (`c.Similarity >= Tau`).
  - Both are null on a retrieval failure, which closes F-E and F-G.
- **`entered_band` ≡ TIER2_HIT**, MIXED included: a `|` namespace never equals a SPEC or POLICY one. So I2 holds, and so does "a refusal never carries an overlap".
- **`t_search_ms`** is one span, and `msPtr` renders zero as null.
- **The removal is complete:** the record field, `Decision.SimilarityOnly`, `RuleSimilarityOnly`, `TauHigh`, `hitOrMiss`, and `cacheStore.NearestTier2`. `cache.Store.NearestTier2` is kept, as ADR-004 states.
- **`REUSE_TAU_HIGH`.** A non-empty value is refused, and an empty one reads as unset.
- **Nothing outside the scope moved:**
  - the diff does not touch `rag/`, the `.proto`, `internal/cache`, the Redis schemas or `architecture.md`;
  - τ, θ and the lane band are unchanged;
  - the §D and §E fields (`t1_key`, `dataset_epoch`, `source_chunk_ids`) are untouched, and so is the write-back path.
- **The versioning is consistent:** the §H "1.3 commit" caveat, the v0.10 row and ADR-004's Summary row agree with each other and with the code.

**Unresolved findings: none.**
