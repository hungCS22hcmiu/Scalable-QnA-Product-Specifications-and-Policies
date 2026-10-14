# Impact — refusal cause code (super-plan item 2.3)

> Written by the `impact-analyst` subagent on 2026-10-14 and saved here by the main session
> (the subagent has no write tool). Text is the subagent's, unedited. The main session spot-checked
> one claim: §3.4, that the measured warranty case never reaches the gate in configuration 4
> (`lane_test.go:425-495` and `harness_test.go:757` agree). Nothing else was re-run.

## Summary

- **Lead risk: this is not a logging change. It changes what Tier 2 serves.** The served rule goes from `sim ∧ namespace` to `sim ∧ namespace ∧ support`. Four things keep their keys but change meaning: `cache = TIER2_HIT`, `entered_band`, the hit rate, and `source_overlap` on a MISS. §H's own alarm I2 (`entered_band ∧ cache ≠ TIER2_HIT` never occurs) becomes false on every support refusal.
- **Existing tests that change outcome: 0.** That is 0 of the 44 test functions in `httpapi`, and 0 in `reuse`, `telemetry`, `ragclient`, `cmd/gateway`, `rag/` and `experiments/tests`. This holds only if the design keeps the three constraints in §3. It was computed by running both arms on the real fixtures; it is not assumed.
- **Spec defect: acceptance 1's warranty half cannot pass through `Ask`.** In configuration 4, the namespace search already refuses the measured warranty case, so the gate never runs. Its cause is `null`, not `SUPPORT` (§3.4). The author must restate acceptance 1 before design.
- **Prior runs invalidated: none citable.** `experiments/results/` is empty, and no `requests.jsonl` survives on disk. The two item-1.6 runs keep their ADR-001 meaning. Run B's 250 `TIER2_HIT` were served with no gate and are not comparable across the 2.3 commit.
- **Phases: the contract phase (ADR-009, `interfaces.md` v0.12 → v0.13) and the experiment phase are both required.**

## 1. Packages and files touched

| Package | File : line | What changes | Layering |
| :--- | :--- | :--- | :--- |
| `httpapi` | `cascade.go:81-132` | Add a zero-chunk guard before `Classify` (after `:81-83`). Call both arms only after `DecideLane` passes (`:117-123`). Add the cause and the two verdicts to `tier2Outcome` (`:42-57`). Comments `:38-41`, `:44-46`, `:59-60` and `:125-127` go stale. | OK. It already imports `reuse` and `ragclient`. |
| `httpapi` | `handler.go:291-302` | Copy the cause and the two support values into `rec` with the other Tier-2 fields (`:291-298`). Then serve only if the namespace rule **and** the gate admit (`:302`). Comments `:273-274`, `:284-286` and `:300-301` go stale. | OK |
| `httpapi` | `types.go:26-31, :56-58` | Comments only. No new wire field is needed. | OK |
| `telemetry` | `evallog.go:42-45` | Three fields after `EnteredBand`: `refusal_cause *string`, `support_lex *float64`, `support_numeric_ok *bool`, all without `omitempty`. | OK **only if they are plain Go types**. `telemetry` may import nothing from the repo (`architecture.md:152`), so the field must never be a `reuse.Cause`. |
| `reuse` | `support.go:9-10, :157-160` · `support_numeric.go:15-16, :70-72` · `doc.go:2-3` | Comments only. Optional: a cause enum and a pure "combine the two verdicts" function. | OK if it stays stdlib-only and takes `[]string`. A `*ragclient.RetrieveResult` parameter would add a `reuse → ragclient` edge, which is forbidden (`architecture.md:146`). |
| `ragclient`, `cache`, `rag/`, `.proto` | — | Nothing. `Texts` already crosses the seam (`ragclient/retrieve.go:24-33, :50-55`), so §B is unchanged. | — |
| `cmd/gateway` | — | Nothing under D3 = always on. One env var under D3-B. | — |
| `httpapi` tests | new files | New tests only. The harness may gain seams; it may not loosen a check (`harness_test.go:5-8`). | — |
| docs | see §5 | `interfaces.md` (§A, §H, version), `decisions.md` (ADR-009 and its summary row), `super-plan.md`, `architecture.md`, `README.md`, and `Final_Proposal.md` (the author's file). | — |

No new import edge and no cycle.

## 2. Frozen values and measured paths

- **Frozen values that are read, not changed:**
  - `τ_s = 0.6` (`support.go:16`);
  - the `S_lex` definition;
  - the numeric rules R1–R9 and the unit list.
- **CLAUDE.md frozen list:** nothing on it is touched (`num_ctx`, slots, embedding model, `DIM`, `top_k`, chunking, FLAT, eviction, capacity, δ, `dataset_version`).
- **Frozen contract that changes:** §H gains `NOT_SCORED` and new null rules, and §A/§H statements become false (§5). This needs **ADR-009** and **v0.13**.
- **Measured path that changes:** the served Tier-2 decision.
- **Two frozen-row clauses fire at the first logged run.**
  - `decisions.md:71`: after any run has logged `support_lex`, an edit to the stopwords or the tokenizer needs an ADR.
  - `decisions.md:72`: "After the first logged run, any edit needs a numbered ADR". Yet the unit list is "draft until the Phase 3 corpus freeze".
  - After 2.3, any `RUN_ID` logs both fields. So the planned Phase 3 unit-list edit would need an ADR, unless ADR-009 says dev-v0 logs do not count. **The author decides this in ADR-009.**

**Invalidates (one sentence):** None citable — `experiments/results/` holds no run; the only `RUN_ID`s are item 1.6's `footprint-20261006` (all Tier-1, which the gate never touches) and `footprint-20261006-b` (dev-v0, indicative, logs no longer on disk), whose 250 `TIER2_HIT` were served with no gate and are not comparable across the 2.3 commit, while ADR-001's k6-cost conclusion does not depend on what the gateway served.

**Logs written before the 2.3 commit: same key, different meaning**

| Key | Before | After |
| :--- | :--- | :--- |
| `cache = TIER2_HIT` | sim ∧ namespace | sim ∧ namespace ∧ support |
| `entered_band` | equals `TIER2_HIT` | `TIER2_HIT` ∨ `SUPPORT` ∨ `NOT_SCORED` (∨ the `NAMESPACE` alarm) |
| `source_overlap` on a non-hit (and `overlap_decision` on the response) | never present, except the alarm | present on `SUPPORT` and `NOT_SCORED` |
| `similarity`, `reuse_rule`, `t_search_ms` on a zero-chunk retrieval that has a `product_id` | non-null | null |

- **In-log discriminator:** the three new keys are absent before the commit. Keep them without `omitempty` so that key presence marks which side a log is from.
- **The Tier-2 ≈ 61 req/s planning figure** (2026-09-06, no `RUN_ID`) was taken with no gate. Strictly, it is no longer a lower bound for the gated path. The gap is about 0.2 % (§9), and Phase 7 re-measures it anyway.

## 3. Existing tests at risk

**Answer: 0 tests change outcome.** The baseline is green today (`go test` on `httpapi`, `reuse`, `telemetry`, `ragclient`).

**Why the fakes pass the gate:**
- Every fake retrieval carries aligned `Texts` for all 3 chunks (`harness_test.go:493-504`).
- The fixture rule (`harness_test.go:86-88`, enforced at `:148-163`) says each corpus answer is a verbatim substring of chunk 0 and contains no numerals.
- A scratch copy of both arms was run on the four fixture answers against their own product's texts. Each gives **`S_lex` = 1.0000, numeric arm admits.**

**3.1 Tests that serve a `TIER2_HIT` (8). All stay hits.**

| Test | Answer scored | Evidence |
| :--- | :--- | :--- |
| `TestCascadeSearchesOnceInTheQuerysNamespace/hit` (`cascade_test.go:34`) | `kettle.answer` | kettle |
| `TestCandidateExactlyAtTauIsServedAndEntersTheBand` (`cascade_test.go:111`) | `kettle.answer` | kettle |
| `TestCounterfactualIsComputedOnTheServedEntry` (`cascade_test.go:141`) | `kettle.answer` | kettle |
| `TestRecordCarriesNoSimilarityOnlyDecision` (`cascade_test.go:171`) | `kettle.answer` | kettle |
| `TestMissThenParaphraseIsATier2Hit` (`ask_test.go:163`) | `kettle.answer`, written by the fake `Answer` | kettle |
| `TestTier2HitInsideTheNamespaceAndPromotesToTier1` (`ask_test.go:195`) | `kettle.answer` | kettle |
| `TestBoundedCacheTouchesTheServedEntryAndTrimsToCapacity` (`ask_test.go:739`) | `kettle.answer` | kettle |
| `TestEveryServedAnswerIsRecoverableFromRawAlone` (`answerstore_test.go:35`) | `headphones.otherAnswer` | headphones |

**3.2 Tests where the gate never runs.**
- **Cause `SIMILARITY`:** `…/below tau` (`cascade_test.go:34`), `TestBelowTauDoesNotEnterTheBand` (`ask_test.go:302`), `TestAnotherNamespaceAboveTauDoesNotLiftAnEntryBelowTau` (`ask_test.go:689`).
- **No candidate, cause null:**
  - `TestTier2RefusesAnEntryFromAnotherNamespace` (`ask_test.go:269`);
  - `TestIdenticalQuestionAboutAnotherProductIsNotServed` (`cascade_test.go:192`);
  - the degradation tests (`ask_test.go:519, :551, :584`; `cascade_test.go:73`);
  - `TestEmptyNamespaceRunsNoSearch` (`cascade_test.go:222`).
- **MISS-path tests** (`abandon_test.go`, `generatems_test.go`, and shed/coalesce in `ask_test.go`): a later request in the same test may find an earlier write-back at cosine 0. That gives `SIMILARITY`. Nothing asserts it.
- **Telemetry tests:**
  - `TestNullableFieldsRenderAsNull` (`evallog_test.go:49-82`) lists the keys that must be null. The new keys are not in its list, so it passes.
  - `answers_test.go:224-225` matches only the substring `"request_id":"…"`, so key order does not matter.

**3.3 Three constraints that keep the count at 0.**
1. **Keep `tryTier2`'s signature, `tier2Outcome.Found`, `.EnteredBand` and `stageTimings.Search`.** `cascade_test.go:227-237` calls `tryTier2` directly. Any change fails to compile, and that fails the whole package.
2. **Run the gate only on a candidate that passed `DecideLane`.** Keep `EnteredBand = sim ≥ τ` (`cascade.go:128`): five tests assert it.
3. **Pass this request's `retrieved.Texts` and `retrieved.ChunkIDs`, never `c.Entry.SourceChunkIDs`.** `support.go:145-147` warns about this: with the entry's IDs, a stale server would read as "scored 0".

**3.4 Acceptance 1 is not reachable as written. The author must decide.**
- **Why the warranty half fails:**
  - The measured pair has one policy chunk in five (`lane_test.go:440-449`).
  - With the harness band `{0.20, 0.20}` (`harness_test.go:757`) it is classified POLICY (`lane.go:127-128`). The paraphrase's namespace is `policy-returns-electronics`; the warranty's is `policy-warranty`.
  - With the band `{0.20, 0.60}` it is MIXED, and the composite keys differ in the same way (`lane_test.go:483-486`).
  - Either way, the scoped search (`cascade.go:103`) never hands the returns-namespace entry to the warranty query. The result is a MISS with no candidate, so the cause is `null` (D2).
- **The fixture cannot simply be added either:**
  - The measured texts and `cachedAnswer` contain numerals. Adding them to `corpus` breaks `checkFixtures` for every test.
  - The fake `Answer` rejects a rank-1 chunk it does not know (`harness_test.go:563-566`). The warranty MISS has `product-headphones-04` at rank 1, which is unknown.
  - Fixing this needs a separate product map as a new seam, not a loosened check.
- **Recommendation:** restate acceptance 1 as:
  - the paraphrase is a `TIER2_HIT` with cause `NONE` and both support fields non-null;
  - the warranty is a MISS with cause `null` ("refused by the namespace search");
  - plus a separate synthetic `SUPPORT` case.
- **Do not seed the entry in the warranty namespace to force `SUPPORT`.** That is no longer the measured case.
- **What this means for Phase 2:** in configuration 4 the namespace already closes the gate's own measured case. Phase 2 exit clause 1 is met by the arms (2.1, 2.2), not by the cascade.

**3.5 What the new tests need.**
- **No harness edit** for acceptance 2, 3, 6 and 7. Seeded entries are not checked by `checkFixtures`, so synthetic answers can be seeded freely. Two were computed:
  - `headphones.answer` seeded in the kettle namespace: `S_lex` 0, numeric admits. So the lexical arm refuses and the numeric arm passes.
  - `"a brushed steel body and an automatic shutoff switch rated 1500 W"` seeded in the kettle namespace: `S_lex` 0.75 (6/8), numeric refuses. So the lexical arm passes and the numeric arm refuses.
- **Acceptance 4 (stale server) and 5 (zero chunks):** the decision can be tested with a direct `tryTier2` call, as T7 does. Testing through `Ask` needs a new `fakeRAG` seam (omit texts; return zero chunks for a known product). That counts as allowed scaffolding, with a note in the task.

## 4. The zero-chunk hole

**How it is reached today (SPEC lane only):**
1. `handler.go:257-267`: `Retrieve` succeeds with no chunks.
2. `cascade.go:81` passes, because `retrieved` is not nil.
3. `cascade.go:88`: `Classify(empty)` returns SPEC (`lane.go:118-120`).
4. `cascade.go:89`: `Namespace(SPEC, empty, productID)` returns `productID` (`lane.go:192-193, :213-216`).
5. `cascade.go:94`: the namespace is not empty, so the search runs (`:103`).
6. `DecideLane` (`:117`) then serves if sim ≥ τ. **A hit is served with no evidence behind it.**

- **Lanes:** SPEC only. POLICY and MIXED need a chunk of their own kind. A non-empty `product_id` is required; without it the namespace is `""` and no search runs (T7).
- **With the real service: reachable.**
  - `rag/src/rag/retrieve.py:129-131` drops other products' chunks, and `_ensure_own_chunk` (`:105-119`) adds nothing when the product has no chunk.
  - So an unknown `product_id` whose top_k holds no policy chunk returns zero chunks.
  - So does any query against an empty corpus index (FLUSHALL without ingest).
  - The write path also creates such entries: `handler.go:416-417` gives an empty-provenance entry the namespace `product_id`.
- **With the fakes:** not reachable through `Ask`. The fake `Retrieve` answers an unknown product with an error (`harness_test.go:521-524`), and a known product always has 3 chunks.
- **Tests that rely on the hole: none.** T7 (`cascade_test.go:222`) passes zero chunks with `productID ""`, which is the empty-namespace path. With the guard placed before `Classify`, T7 still gets `Found=false`, `Search=0` and no search call.
- **If the gate is wired with no guard:** the lexical arm scores 0 and refuses, while the numeric arm admits a number-free answer (computed). That logs `SUPPORT`, against acceptance 5.
- **Where to put the guard:** in the cascade, as the spec says. Not in `reuse.Namespace`, because that would also change the write path's partition (`handler.go:417`).
- **Side effects of the guard:**
  - `similarity`, `reuse_rule` and `t_search_ms` become null on zero-chunk requests that have a `product_id`. §H must say so.
  - Offline, zero chunks reads as `retrieved_chunk_ids` null (proto decodes empty as nil) with `dataset_epoch_at_retrieval` non-null. A retrieval failure has both null.
- **Left over, out of scope:** the write path still creates zero-provenance entries.

## 5. Contract and document statements that go stale

**§H (`interfaces.md`)**

| Line | Today | Verdict |
| :--- | :--- | :--- |
| `:3`, `:615`, version table | v0.12 | Bump to v0.13. |
| `:529` | I1, "1.0 by construction" | Still true: `reuse_rule` is set on every judged candidate (`handler.go:293`). No change. |
| `:530` | "% entering the cascade band … equals the TIER2_HIT share" | **False.** It becomes TIER2_HIT + SUPPORT + NOT_SCORED (+ the NAMESPACE alarm). Reword. |
| `:545-551` | The example record is a `TIER2_HIT` carrying `refusal_cause: "SUPPORT"` and `support_numeric_ok: false`. Its comment says "null when reuse was served", which contradicts `NONE` at `:598`. | **Impossible after 2.3.** Rewrite it as one consistent record, following D2. |
| `:550-551` | support comments: "null when the gate arm is off" | Incomplete. Reword. |
| `:597` | `entered_band` note and I2: "`entered_band ∧ cache ≠ TIER2_HIT` never occurs" | **False** on every SUPPORT or NOT_SCORED refusal. Restate it as "… `∧ refusal_cause ∉ {SUPPORT, NOT_SCORED}` never occurs". NAMESPACE stays the alarm. |
| `:598` | `refusal_cause` note | Add `NOT_SCORED`, the D2 null rule, a precedence order, "CONTAINMENT is unreachable until F-K", and that SUPPORT is judged after sim ∧ namespace, **not after containment**. |
| `:599` | `reuse_rule` note | Still true. |
| `:600` | "Both null on the gate-off arm … how the two arms are told apart" | **No longer true on its own.** Null now also means: no candidate, SIMILARITY, NAMESPACE, NOT_SCORED. The arms are told apart only among `refusal_cause = NONE`. |
| `:601` | `t_search_ms` is "null exactly when no search ran" (embed or retrieval failed, or empty namespace) | **Add zero chunks**, or it becomes false. |
| `:164` | `latency_ms` sentence about off-box end-to-end | ADR-001 already waits on "a v0.13 bump" (`super-plan.md:335-337`, `decisions.md:235`). Either fold it into v0.13, or say v0.13 leaves it alone. |

Suggested new invariant for §H: `refusal_cause != null` ⇔ `similarity != null` ⇔ `reuse_rule` is present. This is exactly the check acceptance 6 needs.

**§A**
- **Wire shape:** unchanged. No new field is needed.
- **Values:** a support-refused MISS now carries non-null `similarity`, `source_overlap` and `overlap_decision`.
- **`:166`** says "such a candidate is always served, so a refusal never carries an overlap". This becomes **false**. Reword.
- **`:165`:** add zero chunks to the `similarity` null cases.
- **`:173`:** add the support-refused MISS as a second pairing.
- **Debug UI:** it will show "MISS · sim 0.93 · overlap 1.00 · rule —" with no reason. A `refusal_cause` extension on the response is optional. The smallest change leaves the wire alone.

**Other documents and code**
- **`decisions.md`:**
  - `:500-501` (ADR-004: overlap null "on every refusal") becomes false.
  - `:505-511` (ADR-004's I2) becomes false.
  - ADR-009 must supersede both. Do not edit ADR-004.
- **`Final_Proposal.md`** (the author's file):
  - `:155` ("the support gate is not built yet") goes stale.
  - `:190` (band share "identical to a Tier-2 hit") goes stale.
  - `:411` defines the refusal rate as refusals of reuse that "similarity, namespace **and containment**" accepted. 2.3 logs refusals after sim ∧ namespace only (F-K). This is a definition gap: compute offline with `source_overlap ≥ θ_run`.
  - `:226`: the cause list lacks `NOT_SCORED`.
- **`README.md`:** `:66-68`, `:160-162`.
- **`architecture.md`:** `:50`, `:165-168`, `:203`.
- **`super-plan.md`:** `:349` (progress), `:355` (row 2.3).
- **Code comments:** listed in §1.

## 6. The `null` ambiguity

| State | `cache` | `similarity` | `entered_band` | `refusal_cause` | `support_lex` | `support_numeric_ok` |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Tier-1 hit / Tier-1 lookup error | TIER1_HIT / `""` | null | false | null | null | null |
| Embed failed · retrieve failed · zero chunks · empty namespace · search error · cold namespace | MISS… | null | false | null | null | null |
| Below τ | MISS… | < τ | false | `SIMILARITY` | null | null |
| Filter/Go namespace disagreement | MISS… | any | maybe true | `NAMESPACE` | null | null |
| Stale server (chunks but no texts) | MISS… | ≥ τ | true | `NOT_SCORED` | null | null |
| Gate refused | MISS / SHED / ABANDONED / GENERATION_FAILED | ≥ τ | true | `SUPPORT` | number | bool |
| Gate on, served | TIER2_HIT | ≥ τ | true | `NONE` | number | bool |
| Gate off, served (2.4) | TIER2_HIT | ≥ τ | true | `NONE` | null | null |

**Verdict: D1–D3 work.** Every judged state has its own (`refusal_cause`, support-nullity) pair. Caveats:
1. **The cause must be set at `handler.go:291-298`, before the miss path.** Then SHED, ABANDONED and GENERATION_FAILED records keep their Tier-2 cause.
2. **A `null` cause covers 8 states.** Other fields tell most of them apart. Search error and cold namespace cannot be told apart (pre-existing; §H `:601` says so). This is fine, because none of the 8 is a Tier-2 decision.
3. **Precedence is not defined yet.** If sim < τ and the namespace also disagrees, one cause must win. If `SIMILARITY` wins, the `NAMESPACE` alarm under-counts. **Recommended: NAMESPACE first, then SIMILARITY, (CONTAINMENT), SUPPORT.** The design decides.
4. **2.4's gate-off arm with a stale server** logs `NONE` with null support fields, the same as a normal gate-off hit. That is acceptable, because the off-arm never reads texts. §H should state it as a rule.
5. **`NOT_SCORED > 0` in a run means a stale server answered.** The experiment phase decides whether that voids the run, as `Dropped()` does.
6. **The fields must be pointers and never `omitempty`.** Otherwise "null" and "key absent" (a pre-2.3 log) merge.

## 7. Other readers of the log

- **No reader breaks.**
  - `experiments/scripts/loadgen_footprint.py:1013-1025` (`count-log`) reads only `cache` and `shed`. It hashes the whole file, so its sha changes by construction, which is fine.
  - No other script, k6 file, Makefile target or `rag/` test parses `requests.jsonl`.
  - `load_burst.py:141-147`, `k6/ask.js:150-151` and `k6/mu_hit.js:163-164` read the HTTP response's `cache` only.
- **Loud breakage risk (exploratory tools, not tests):**
  - `mu_hit.js` tier2 mode requires `TIER2_HIT` on five real paraphrases in `setup()` (`:73-82`, `:146-171`). `make demo` step 3 needs the same (`Makefile:212-214, :243-245`).
  - If the gate refuses a real answer, both fail. They fail loudly, not silently.
- **Key order:** `encoding/json` follows struct order, so inserting after `EnteredBand` (`evallog.go:45`) shifts every line's bytes. Nothing reads by position: tests decode to maps.
- **Answer store:** untouched.
  - `storeAnswer` reads only `AnswerSHA256` and `answerText` (`evallog.go:230-285`), and the file-before-line order is unchanged.
  - A refused answer is never served, so it gets no file (rule 3).
- **Gap for Phase 5/6 (the experiment phase decides):** on a `SUPPORT` refusal, nothing in `raw/` names what was refused.
  - `rec.EntryID` is the new MISS entry (`handler.go:529`).
  - The refused text is not stored, and the evidence text is not stored either (§H rule 8).
  - So a support refusal cannot be checked offline.
  - Cheap options: log the refused `entry_id`, `ContentTokenCount` and `Unitless`. 2.1 and 2.2 added the last two so that short answers and unit gaps could be measured.

## 8. Dependency, scope, measurement, contract

- **New dependency: none.** Stdlib only, no module, and no resident memory beyond short-lived per-request allocations. No sign-off is needed.
- **Dropped scope: nothing reinstated.** `Final_Proposal.md:599` lists the bypass classifier, the predictor, predictor-gated invalidation, routing, SSE and HNSW; 2.3 touches none of them.
  - The arms are token arithmetic and never read the query text (`support.go:142-143`, `support_numeric.go:66`). **The wiring must not pass `req.Question`.**
  - The gate's on/off arm is non-negotiable (`:595`), and it is 2.4's job.
- **Measurement: yes, so the experiment phase is required.** It covers:
  - the served rule, the hit rate, the tier mix, `entered_band` and the band share;
  - the three new fields;
  - the refusal-rate definition against the proposal's (`:411`);
  - what `NOT_SCORED > 0` means for a run;
  - whether to log the refused entry and the token counts;
  - the gate's latency. It has no §H span; the proposal (`:494`) wants it reported as its own component. Today it lands in `t_total − Σ t_*`.
- **Contract: yes, so the contract phase is required.** ADR-009 (with its `Invalidates:` line from §2) and `interfaces.md` v0.13.

## 9. Hit-path cost

- **Measured costs** (M1, dev-v0 pinned strings, not citable):

  | Arm | Time | Memory | Allocations |
  | :--- | :--- | :--- | :--- |
  | Lexical | ≈ 14.0–15.9 µs | 12,368 B | 286 |
  | Numeric | ≈ 14.5 µs | 7,976 B | 96 |
  | Both (acceptance 7 needs both values on every gated candidate) | ≈ 30 µs | ≈ 20 KB | ≈ 382 |

- **Against Tier 2 (≈ 61 req/s, ≈ 16 ms per request, bounded by the one-slot embedding server, `super-plan.md:423`):** about 0.2 %. **It does not matter to μ_hit.** It runs in each request's own goroutine and does not serialize. At 61 req/s it costs ≈ 1.8 ms of CPU per second and ≈ 1.2 MB/s of garbage.
- **Tier 1 (≈ 8000 req/s):** untouched.
- **Locks: none.** Both arms are pure functions, and the package maps (`support.go:27`, `support_numeric.go:100-130`) are read-only.
- **New allocations:** the ones above, plus three small pointers per record.
- **Two cautions:**
  - The cost grows linearly with evidence length (`strings.Join` at `support.go:169`). Re-run both benchmarks on v1 text.
  - The gate has no §H span.

## 10. Unknowns, ranked

1. **How real answers do against the gate (acceptance 10).** The `S_lex` distribution is unknown, and so are numeric refusals: for example, an answer that echoes the question's "30 days" when the evidence does not say it. The result could be that the gate refuses most reuse (the proposal's second pre-registered null), which would also break demo step 3 and `mu-hit` tier2. **Verify:** plan step 1, with 10–20 dev-v0 answers and the pressure level recorded.
2. **Whether any realistic configuration-4 case reaches `SUPPORT` at all,** given that the namespace already separates the measured trap (§3.4). If none does, the gate is inert on dev-v0 (the first null). **Verify:** in the same sample, run paraphrase pairs through `Ask` and count the causes.
3. **Cause precedence** (§6.3). The author decides in design.
4. **Whether Phase 5/6 need** the refused `entry_id`, `ContentTokenCount` or `Unitless` per record. The experiment phase decides.
5. **Whether dev-v0 logs count as "the first logged run"** for `decisions.md:71-72`. The author decides in ADR-009.
6. **Whether the real v1 workload ever returns zero chunks.** **Verify:** probe the index with an unknown `product_id`, and check at Phase 3 that every workload `product_id` has a chunk.
7. **Whether the benchmark holds at v1 chunk lengths.** **Verify:** re-benchmark at Phase 3 or Phase 7.

## Smallest change that meets the spec

- **Do:**
  - the zero-chunk guard in `tryTier2`, before `Classify`;
  - both arms after `DecideLane` passes;
  - `NOT_SCORED` when either verdict has `Scored == false`;
  - three pointer fields in `Record`, set at `handler.go:291-298`;
  - serve only if `NSDecision.Reuse` holds and neither arm refuses;
  - the §A/§H rewording and ADR-009.
- **Cut:**
  - D3-B (the switch belongs to 2.4);
  - any new §A response field;
  - `t_support_ms`;
  - a second candidate;
  - a guard inside `reuse.Namespace`;
  - a cause type inside `telemetry`;
  - harness edits beyond the two `fakeRAG` seams.
- **First:** fix acceptance 1 (§3.4) before `design.md`.

**Required phases:** impact · contract · experiment · implementation (scope L: design → opus design-review → plan come in between)
