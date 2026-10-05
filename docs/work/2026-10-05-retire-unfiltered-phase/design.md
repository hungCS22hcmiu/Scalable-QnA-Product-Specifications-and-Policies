# Design — retire-unfiltered-phase

**Revision 3**, after `review.md`. It reads with `spec.md` and `approvals.md`.

**Decided by the author:**
- **D1:** `similarity` is null when there is no scoped candidate.
- **D2:** `entered_band` is restated, not retired.
- **D4:** the stale tests are retired.
- **R1:** the configuration-3 gap is accepted, with the startup guard.
- **R3,** as revised after the review's S1.

**Changed from rev 2.** Every one of `review.md`'s findings is applied:

| Finding | Where it lands |
| :--- | :--- |
| S1, the provenance-check expression | §7 R3, §8 |
| S2, `entered_band` ≡ TIER2_HIT | §2a, §3's comment table, §8 |
| S3, `refusal_cause = NAMESPACE` | §6 F9, §8 |
| S4, a direct test of the empty namespace | T7 |
| S5, the demo's non-null branch | §3 |
| N1 | the guard's test and its evidence |
| N2 | §8 |
| N3 | T1 |
| N4, N5 | §6, §8 |

## 1. Shape

```
                        TODAY                                          AFTER
 Ask ─► embed ∥ Retrieve                                Ask ─► embed ∥ Retrieve
          │                                                       │
 tryTier2(vec, retrieved)                               tryTier2(vec, retrieved)
   vec == nil → {}                                        vec == nil ∨ retrieved == nil → {}       F-E closed · D5 · FIRST (see below)
   NearestTier2(vec,1)  ── GLOBAL ──┐                     lane, ns ← Classify, Namespace(retrieved)
   nearest < τ → {Found, nearest}   │ removed             out ← {QueryLane: lane, QueryNS: ns}
   TauHigh short-circuit            │ removed             ns == "" → out                           S2: no call, no span
   EnteredBand = true  (F-E)        │                     timed: NearestTier2InNamespace(vec, ns, 1)   ── the only search
   retrieved == nil → {nearest, band}                     error ∨ empty → out                      D1: similarity null
   Decision ← Decide(nearest) (+SimOnly)                  c ← scoped[0];  Found, Candidate ← c
   lane, ns ← Classify, Namespace                         NSDecision ← DecideLane(c, lane, ns)     UNCHANGED rule · D6
   NearestTier2InNamespace(vec, ns, 1)                    c.Similarity >= τ  ⇒                     D2 · S7 (positive form)
   served ← scoped hit, else GLOBAL nearest                   EnteredBand ← true
   NSDecision.Overlap ← Overlap(served)                       Decision ← Decide(c)                D3 · no SimilarityOnly
   log (… similarity_only=…)                                  NSDecision.Overlap ← Decision.Overlap   one computation
                                                          log (no similarity_only)
```

**The `retrieved == nil` check must stay first.** Suppose a mutation derives `ns` from
`productID` after retrieval has failed. The spec lane then names the product, the scoped search
finds an entry, and the request is **served without provenance**. `TestRetrieveFailureDegradesToMiss`
and T2 both catch it (`review.md` question 1, M11).

`Ask` (`handler.go:272-345`) keeps its shape. It loses the `SimilarityOnlyDecision` assignment
(`:302-307`) and `hitOrMiss` (`:565-571`), which is its only caller. It reads the same
`tier2Outcome` fields as today. `QueryLane` and `QueryNS` are now set whenever retrieval
succeeded, which changes no output. Their only readers are the TIER2_HIT response (`:366-367`) and
the cascade's log line. The MISS response takes `lane` and `namespace` from `Answer`'s result
(`:521`).

## 2. Why no served decision moves

`DecideLane` is untouched, and it is the only thing that can produce `NSDecision.Reuse`. The
side effects are `BumpHitCount`, `touch` and the Tier-1 promotion. They run only on
`NSDecision.Reuse` (`handler.go:311`) and key on `t2.Candidate`, so they do not move either.

The claim was checked twice:
- `impact.md` §3 lists all 13 paths and ran impact's own scratch version.
- `review.md` implemented §3's contract **as written** and re-ran the full suite, also under
  `-race`. Only `:287` and `:291` changed.

| Path | Today | After | Served |
| :--- | :--- | :--- | :---: |
| `vec == nil` (embed failed) | `{}` | `{}` | MISS = MISS |
| `retrieved == nil` (any similarity) | F-E's band entry, or an early return | `{}`, no search | MISS = MISS |
| global nearest < τ | early return | scoped `c.sim ≤ global < τ`, so `DecideLane` refuses on τ | MISS = MISS |
| global ≥ τ, the namespace empty or holding no entry | `served = nearest`, refused | `{lane, ns}` | MISS = MISS |
| global ≥ τ, a scoped candidate exists | `DecideLane(c)` | `DecideLane(c)` | identical |
| either search errors | MISS | MISS (one search fewer that can fail) | MISS = MISS |
| `TauHigh ≤ 1` (non-default) | serves on similarity alone | the knob is gone, and setting it stops startup | **changes**, for a value no run used (R1) |

**Preconditions:** one cache snapshot; `REUSE_TAU_HIGH` unset or above 1.0; the frozen FLAT
index. Under HNSW, `c.sim ≤ global.sim` fails, and row 3 with it.

### 2a. What D2 makes `entered_band` (`review.md` S2)

The scoped search returns only candidates in the query's namespace.
- **SPEC and POLICY.** `DecideLane` then reduces to `sim >= τ`.
- **MIXED.** Only a MIXED entry carries a `|` namespace, so the lane always matches.

So `Found ∧ c.sim >= τ` ⇔ `NSDecision.Reuse`, and under D2 **`entered_band` equals the TIER2_HIT
indicator**. This holds until θ (F-K) or the support gate (2.1) joins the served rule. It has three
consequences:
- **"% entering the cascade band" is the Tier-2 hit share** until then. It is not an independent
  metric.
- **No refusal carries `source_overlap` or `overlap_decision`.** A refusal carries its
  similarity, never an overlap.
- **Two invariants come free:**
  - **I1:** every record with `similarity != null` has `reuse_rule` ∈ {`namespace`,
    `composite`}. This is R3's metric (§7), and it is 1.0 by construction.
  - **I2:** no record has `entered_band ∧ cache ≠ TIER2_HIT`. A violation can only mean that the
    Redis TAG filter and Go's `MatchNamespace` disagree.

## 3. Function contracts

### `tryTier2(ctx, productID, vec, retrieved, t) tier2Outcome`

- **Pre:** `vec` is the query embedding or nil; `retrieved` is this request's `Retrieve` result or
  nil.
- **Search budget.** At most one `NearestTier2InNamespace` call per request, and none when
  `vec == nil`, `retrieved == nil` or `ns == ""`. `cacheStore` loses `NearestTier2`, so no global
  search can come back without editing the interface, which is a visible change.
- **Timing (S2, D5).** `t.Search` is set only around the one call. `msPtr` turns a zero `Search`
  into `null`, so `t_search_ms` is null exactly when no search ran. That is why the empty
  namespace returns **before** the call: timing a no-op call yields `0.000`, which reads as a
  measurement. T7 pins it.
- **Returns:**
  - `QueryLane` and `QueryNS` whenever `retrieved != nil`.
  - `Found` iff the scoped search returned a candidate. `Candidate` is that candidate and nothing
    else, so `similarity` is that candidate's similarity or null (D1).
  - `NSDecision` is `DecideLane`'s verdict whenever `Found`. `reuse_rule` is therefore present iff
    a candidate was judged, **including below-τ refusals**, and its presence is not a hit (D6, N5).
  - `EnteredBand` is true iff `Found ∧ c.Similarity >= τ` (D2). It is written in the positive
    form, so a NaN similarity does not enter the band, agreeing with `DecideLane`'s `>=` (S7).
  - `Decision`, the containment counterfactual, is computed iff `EnteredBand`, on `c` (D3), and has
    no `SimilarityOnly`. `NSDecision.Overlap` copies `Decision.Overlap` in the same branch.
- **The log line** prints when `Found`, without `similarity_only`.

**`NSDecision.Overlap`: kept** (`review.md` question 4).
- It is never serialised.
- Deleting it would also edit `lane_test.go:407-418`, which is outside D4.
- F-K's fix will restructure it anyway.

Its comment is restated to say that it duplicates `Decision.Overlap` and is zero unless
`entered_band` is true.

### τ in one place: rev 1's `ClearsTau` stays withdrawn

The cascade keeps its local `c.Similarity >= h.Thresholds.Tau`. The τ-boundary test T3 is the
**only** test that catches M4 (confirmed by a mutation run), and it also catches a `>` drift in
`DecideLane`, because it asserts both TIER2_HIT and `entered_band: true`. A shared predicate would
refactor `reuse/` and still need T3.

### `reuse` package

- `Thresholds` loses `TauHigh` and its comment block (`rule.go:88-112`). ADR-004 carries its
  measured reasons, marked as dev-v0 and **not citable** (§8).
- `Decision` loses `SimilarityOnly`, and `Decide` returns `{Reuse, Overlap}`.
- `RuleSimilarityOnly` goes (`lane.go:276-281`).
- The `NamespaceDecision.Overlap` comment (`lane.go:259-269`) is restated. It now says what it
  duplicates and when it is zero, and cites §H's own decision-time rule in place of
  `similarity_only_decision`.

### Comments restated (S6, `review.md` S2, N5)

| Site | Today | Restated as |
| :--- | :--- | :--- |
| `cascade.go:29-33` `stageTimings.Search` | "the SUM of two … searches" | one span; zero, so null, when no search ran |
| `cascade.go:34-37` `Overlap` | "short-circuited below tau" | drop the short-circuit; read `EnteredBand` for the band |
| `cascade.go:41-44` `tier2Outcome` | "a refusal must still carry its similarity and overlap" | **"a refusal carries its similarity, never an overlap"**; a cross-namespace lookalike is a plain MISS (D1) |
| `cascade.go:47` `EnteredBand` | "similarity cleared tau, so the cascade paid for retrieval" | "a same-namespace candidate cleared τ; equals TIER2_HIT while the served rule is sim ∧ namespace" |
| `cascade.go:51-53, :59-68` | "two searches, not one" | one scoped search, and why the namespace must come first |
| `cascade.go:114-115` | "apples-to-apples with the pre-existing rule" | configuration 4's support-off rule, on the candidate the served rule judged (D3) |
| `handler.go:231-235` | "fall below tau and short-circuit" | "find no candidate above τ" |
| `handler.go:276-277` | "on a refusal they are the evidence FOR the refusal" | similarity travels on any judged candidate; overlap only on a banded one, which is a hit |
| `handler.go:287-289` | "a refusal is exactly where the two rules are most likely to disagree" | the counterfactual travels on every banded response; while F-K stands, that is every TIER2_HIT |
| `types.go:26-30` `askResponse` | "a high-similarity, low-overlap miss is the lookalike trap" | the pair renders `null` rather than dropping; a TIER2_HIT with `overlap_decision: false` is a reuse containment would have refused |
| `types.go:48-53` `ReuseRule`, `evallog.go:64-67` | "names which TERM … decided"; "keeps a similarity-only short-circuit from being charged…" | "the rule variant that judged the candidate; present iff a candidate was judged; presence is not a hit" (N5) |
| `types.go:55-60` `OverlapDecision` | cites `similarity_only_decision` | cites §H's decision-time rule |

### `telemetry`

`Record.SimilarityOnlyDecision` goes, and the package doc (`evallog.go:3-7`) is restated. The
`ReuseRule` comment is in the table above. §H's v0.9 note already describes the removal, and v0.10
dates it at the commit.

### `cmd/gateway/main.go`: the startup guard (R1, acceptance 7)

- **What goes.** `REUSE_TAU_HIGH` is no longer read. The `TauHigh` initialiser (`:104-114`), the
  `short-circuit:` startup line (`:142-153`) and the `math` import go with it.
- **The guard.** `func retiredEnv(getenv func(string) string) error` returns an error when
  `REUSE_TAU_HIGH` is **non-empty**. `main` calls `retiredEnv(os.Getenv)` before any wiring and
  `log.Fatal`s on the error.
- **Why non-empty.** `getenvFloat` treats `""` as unset, so an empty value never enabled the
  short-circuit.
- **The message:** `REUSE_TAU_HIGH is retired (interfaces.md v0.10, ADR-004): the gateway no
  longer serves on similarity alone. Unset it. Configuration 3 has no code path yet.`
- **The test (N1).** `cmd/gateway/main_test.go`, `package main`, with three rows:
  - unset → nil;
  - `"0.95"` → an error containing `REUSE_TAU_HIGH` and `retired` (not the ADR number);
  - `""` → nil.

  It pins the predicate.
- **The call site** is covered twice:
  - **Once, as evidence:** the built binary is run with `REUSE_TAU_HIGH=0.95` and every address at
    `127.0.0.1:1`. It must exit 1 with the message before any dial, and an empty value must get
    past the guard. The run needs no services, and its output goes to `evidence/`.
  - **For later edits:** a grep in acceptance 1 that finds `retiredEnv(os.Getenv)` exactly once.
- **Layering.** A startup refusal is wiring validation, of the same kind as `getenvFloat`'s
  `log.Fatalf`.

### `Makefile` demo step 4 (acceptance 8; `review.md` S5)

Today `:263-264` formats `.source_overlap` with `%.2f`, and hard-codes `< theta → REFUSE`. After
1.3, a non-null `source_overlap` means the entry was **served** (§2a). So the line would invent a
number on a null, and a refusal on a hit. The change reads `ov=$(jq -r .source_overlap …)`, then:
- **`null`:** print `no cached entry in this question's namespace  →  MISS, generate instead`.
- **Otherwise:** print the response's own fields: `cache <.cache>  ·  overlap_decision
  <.overlap_decision>  ·  overlap <num ov %.2f>`. **No verdict word or comparator** goes in that
  the script did not read.

The ✓-marked source listing stays, because it reads `.sources`.

**Checked offline** on the fragment, with `null` and `0.25` and no live run. Which branch Q4 takes
live is `review.md` U2 (PLAUSIBLE: null), and either branch is now truthful.

Three things are out of scope (`spec.md`) and recorded at `/done`, not edited:
- the step-4 header, *"high similarity, different evidence"*;
- the intro line, *"The refusal is arithmetic"*;
- `ProductChat.jsx:67-70`.

## 4. Tests

### Declared, may change (1.2 `approvals.md` item 2)

| Test | Change | Under |
| :--- | :--- | :--- |
| `TestTier2RefusesAnEntryFromAnotherNamespace` | `:287` `resp.notNull("similarity")` → `resp.null("similarity")`; `:291` `rec.boolean("entered_band", true)` → `false`. Status, `cache`, answer and the `Answer` count are unchanged | D1, D2 |
| `TestBelowTauDoesNotEnterTheBand` | **None.** It passes byte-identical, as confirmed by both `impact.md` and `review.md` | — |

`ask_test.go` changes at exactly those two lines. Its two `DECLARED 1.3-SENSITIVE` comment blocks
(`:264-268`, `:298-301`) read as history after the commit and are not edited. That keeps
`git diff -- ask_test.go` a two-line audit (acceptance 5).

### Retired as stale (D4, decided)

| File | Edit |
| :--- | :--- |
| `reuse/rule_test.go` | drop `wantSimOnly` (`:87`, the column at `:89-92`, the check at `:99-101`), keeping the `Reuse` checks byte-identical; delete `TestSimilarityOnlyIsTheBaselineCounterfactual` (`:121-134`), `TestTauHighDefaultIsDisabled` (`:178-197`) and `TestTauHighDefaultSurvivesIdenticalVector` (`:199-213`); drop `math` |
| `telemetry/evallog_test.go:69` | remove the `"similarity_only_decision"` string |

### Harness (scaffolding, 1.2 `approvals.md` item 4: a trail note, no check loosened)

- **The fake's `NearestTier2` is deleted**, in the same edit that removes it from `cacheStore`.
  After that, re-adding it to the interface breaks `var _ cacheStore = (*fakeStore)(nil)` (M1).
  The `"both searches"` subtest still compiles, but it goes vacuous. That is recorded, not edited.
- **The namespace argument is recorded.** `NearestTier2InNamespace` appends its argument to
  `s.namespaces`, and `namespacesSearched()` returns a copy.
- **The comment at `:60-61` is restated**, because it names `TauHigh`.

### New: `gateway/internal/httpapi/cascade_test.go`

Every TIER2_HIT test waits for the bump and the promotion before calling `records()`, as
`ask_test.go:173-174` does. That applies to T1's hit half, T3, T4 and T5.

| # | Test | Asserts | Catches |
| :---: | :--- | :--- | :--- |
| T1 | one scoped search | on a TIER2_HIT, and on a below-τ MISS: `callCount("NearestTier2InNamespace") == 1` and `namespacesSearched() == [kettle.id]`. Only the below-τ half fails on `HEAD` (N3) | a changed namespace argument; a second scoped call. A second **global** search is M1, caught at compile time |
| T2 | F-E closed | `Retrieve` fails, with a same-namespace entry at `hitCos` → MISS. **Record:** `entered_band: false`; `similarity`, `source_overlap` and `t_search_ms` all null. **Response:** `similarity`, `source_overlap` and `overlap_decision` all null. And zero scoped calls | M3, M11; a search kept on the failure path |
| T3 | τ boundary | query and entry both at `basis(1)`, with `hs.h.Thresholds.Tau = 1.0` set before the only request → TIER2_HIT, `similarity == 1` exactly, `entered_band: true`, `overlap_decision: true` | M4, and a `>` drift in `DecideLane` |
| T4 | counterfactual target (F-G) | query at `toward(1, 2, 0.99)`, a headphones entry at `basis(1)` (closer, overlap 0), and a kettle entry at `around(query, 3, hitCos)` (sources `[#0, #1]`, so overlap 2/2) → TIER2_HIT serving the kettle answer, with `source_overlap == 1` and `overlap_decision: true` in both the response and the record | M5. `HEAD` reports 0 and false |
| T5 | no retired key | a banded request's record has **no** `similarity_only_decision` key (`fields.absent`) | M6 |
| T6 | identical question, another product | the byte-identical question, seeded for headphones and asked about the kettle, both at `basis(1)` (similarity exactly 1.0), default τ → MISS, `similarity: null`, one `Answer` call | M8, the 2026-09-09 class (moved from `rule_test.go`) |
| T7 | empty namespace, no span (S4) | a direct call: `hs.h.tryTier2(ctx, "", float32s(basis(1)), &ragclient.RetrieveResult{DatasetEpoch: testEpoch}, &tm)`, with an entry seeded at `basis(1)` → `!Found`, `!EnteredBand`, `tm.Search == 0`, zero scoped calls. On `HEAD`: found, banded, `Search` ≈ 3 µs, one call | M10 |

**Why T7 calls `tryTier2` directly.** No request through the harness can reach `ns == ""`.
`checkEveryRecord` asserts `product_id` on every record (`harness_test.go:1028`), and with a
`product_id` set, `Namespace` never returns `""`. Production *can* reach it: the demo sends no
`product_id`, and an empty retrieval or a corpus without kind prefixes yields an empty namespace.

**One gap is left.** `h.Cache.(*cache.Store).NearestTier2(…)` inside the cascade is invisible to
every fake (`impact.md` S4c). Acceptance 1's second grep catches it.

## 5. Mutations: each must be caught

| # | Mutation | Caught by |
| :---: | :--- | :--- |
| M1 | Re-add a global `NearestTier2` call, re-adding it to `cacheStore` | compile (`harness_test.go:254`) |
| M1′ | Call it through a type assertion on `*cache.Store` | acceptance 1's `NearestTier2(` grep |
| M2 | Report a candidate other than the scoped one on a refusal | declared test 1 (`similarity` null) |
| M3 | Set `EnteredBand`, or search, before the `retrieved` nil check | T2 |
| M4 | `EnteredBand ← c.Similarity > τ` | T3 (the only one) |
| M5 | Compute the counterfactual on any other candidate | T4 |
| M6 | Re-add `similarity_only_decision` to the record | T5; acceptance 1's grep |
| M7a | Change the guard's predicate | `main_test.go` |
| M7b | Drop the call `retiredEnv(os.Getenv)` | acceptance 1's call-site grep; the recorded binary run |
| M8 | A short-circuit re-added **enabled** at 1.0 | T6 |
| M9 | A short-circuit re-added **disabled** | nothing behavioural can see it. Acceptance 1's grep catches it if it reuses the old names |
| M10 | Time a no-op search on `ns == ""` | T7 |
| M11 | Derive `ns` when `retrieved == nil` (served without provenance) | `TestRetrieveFailureDegradesToMiss`, T2 |

Each mutation must be run once against the new suite, with its result recorded in
`evidence/mutations.md`.

**`Decide` run on every found candidate is an equivalent mutant,** because `Ask` reads `Decision`
only when `EnteredBand` is true. It is not listed as a defect.

## 6. Failure modes, silent first

| # | Failure | Silent? | Closed by |
| :---: | :--- | :--- | :--- |
| F1 | A served decision changes | **yes** | §2, re-run twice; acceptance 5 |
| F2 | `entered_band` and the served τ drift apart at the boundary | **yes** | T3 |
| F3 | `REUSE_TAU_HIGH` still set somewhere and quietly ignored | **yes** | the startup guard |
| F4 | Logs from both sides of the commit are mixed: same keys, different quantities | **yes**, at write-up | ADR-004 and §H date the boundary at the **commit**. Until P1's manifest carries the SHA, the presence of the `similarity_only_decision` key discriminates. No log exists today |
| F5 | `t_search_ms: 0.000` where no search ran | **yes** | the return before the call; T2, T7 |
| F6 | The demo prints a fabricated `0.00`, or "REFUSE" on a hit | no, it shows, but it reads as true | the step-4 guard (acceptance 8) |
| F7 | A comment still describes the old counterfactual, or a refusal carrying overlap | **yes**, to the next reader | §3's table |
| F8 | "% reaching the provenance check" computed from an expression that cannot fail | **yes** | R3 as revised (I1), named in ADR-004 and §H |
| F9 | 2.3 emits `refusal_cause = NAMESPACE` for "no in-namespace candidate", turning a cold cache into namespace refusals (`review.md` S3) | **yes**, a plausible wrong number in "false hits by cause" | the `:486` edit in v0.10, and the same sentence in 2.3's row at `/done` |
| F10 | A TAG filter that matches nothing looks like a cold cache: `similarity` null, no Tier-2 hits (N4) | **yes** | the experiment record: *"Tier-2 hit rate ≈ 0 on a warm cache: rule out the filter first"*; demo step 3 is the live witness. I2 catches the opposite disagreement |
| F11 | A filter on "`reuse_rule` present" read as "hit" (N5) | **yes** | §3's restated comments, and the experiment record |

## 7. Risks and decisions

| # | Item | Status |
| :---: | :--- | :--- |
| R1 | Configuration 3 loses its only code path (`REUSE_TAU_HIGH=τ`); `CONFIG_ID` selects nothing (F-K) | **Decided:** accept the gap, with the startup guard. `cache.Store.NearestTier2` is kept as configuration 3's primitive. `/done` records that configuration 3, the static-cache arm and the join script have no `super-plan.md` item |
| R2 (D4) | Four `rule_test.go` sites and one `evallog_test.go` string assert retired behaviour | **Decided:** retired as stale (§4) |
| R3 | `Final_Proposal.md:407`: *"% reaching the provenance check"* is 1.0 by construction once the phase is retired | **Decided, revised after S1.** `:407` stays true and unedited. ADR-004 and §H define it as **I1**: among records with `similarity != null`, the share with `reuse_rule` ∈ {`namespace`, `composite`}. On `HEAD` it reads 4/9, because the below-τ early return leaves `reuse_rule` empty; after 1.3 it is 1.0. A gate re-added before `DecideLane` drops it. **`interfaces.md:430`'s "% entering the cascade band"** is the `entered_band: true` share, which equals the TIER2_HIT share until F-K or 2.1 (§2a) |
| U1 | `cache.Store.NearestTier2` | Settled: kept |
| U2 | v0.10 or a note correction | Settled: v0.10 plus ADR-004 |
| U3 | `TestBelowTauDoesNotEnterTheBand` unchanged | Settled: byte-identical and passing (`review.md`) |
| U4 | `"both searches"` still fails a search | Settled: it passes vacuously |
| U5 | Delete `NSDecision.Overlap` | Settled: kept (§3) |
| U6 | Demo Q4's live branch | PLAUSIBLE: null. Settled by one `make demo` at green pressure, which is not required, because S5 makes both branches truthful |
| U7 | The live TAG filter on hyphenated slugs | Witnessed only by demo step 3; `cache/` is out of scope (F10) |
| U8 | The ≈ 1 % hit-path saving | Estimated; Phase 7 measures it from `t_search_ms` |

## 8. Contract and experiment phases

### Contract: `interfaces.md` v0.10

| Where | Edit |
| :--- | :--- |
| `:3`, `:499` | Header and "Current version" → v0.10 (N2b) |
| `:119`, `:132` | `similarity` is that of the nearest entry **within the query's namespace**. It is null on TIER1, BYPASS and a failed embedding or retrieval, and on a MISS with no in-namespace candidate (D1) |
| `:120`, `:133`, `:447` | `source_overlap`: *"null unless retrieval succeeded and a same-namespace candidate cleared τ; while the served rule is sim ∧ namespace, that is exactly a TIER2_HIT"* |
| `:138` | The lookalike-trap sentence is annotated. A cross-namespace lookalike is a MISS with `similarity: null`. *"A TIER2_HIT with `overlap_decision: false` is a reuse the containment conjunct would have refused."* Both stand while F-K does |
| `:430` | Both metrics, each with its §H expression: I1 for "% reaching the provenance check", and `entered_band` for "% entering the cascade band" (R3) |
| `:448` | The example comment *"consulted provenance"* → *"a same-namespace candidate cleared τ"* (N2c) |
| `:477` | *"before v0.9"* → *"before the 1.3 commit"* |
| `:485` | `entered_band` restated per D2. The band is [τ, 1], and the field equals TIER2_HIT until θ or the support gate is served. I2 is its invariant (S2) |
| `:486` | `refusal_cause`: in configuration 4 the namespace is enforced **by the search, not by a refusal**. "No in-namespace candidate" is not a `NAMESPACE` refusal. The namespace conjunct's effect is counted only by the configurations 3 ⋈ 4 join (S3) |
| §H field notes | A `reuse_rule` row (S1). It is an extension field, and I1 rests on it, so a cleanup must not drop it. It is present iff a candidate was judged; presence is not a hit (N5) |
| Versioning | The v0.10 row |
| **Not edited** | §A gains no `overlap_decision` row, because none exists there today (N2a). D7 is recorded in ADR-004 only, unless the author asks for §A's extension rows. §B, §C, §D, §E, the `.proto` and both stubs are untouched |

### ADR-004, *"The unfiltered Tier-2 phase is retired in code"*

**Decided (method)** · 2026-10-05. It ratifies the retirement that `Final_Proposal.md:10-19` names
as pending. It carries:
- **The statement:** at most one namespace-scoped search; `τ_high` and `similarity_only_decision`
  are retired.
- **One sentence on what it does not ratify (N2f).** The served rule stays `sim ∧ namespace`
  (F-K). `overlap_decision` is configuration 4's support-off verdict. A run's TIER2_HIT count is
  not configuration 4's.
- **Rationale:** v0.9; the subset argument over the FLAT index; F-E and F-G closed. It also carries
  the measured reasons `rule.go` gave for disabling `TauHigh`, marked as **dev-v0, not citable**
  (N2e).
- **Alternatives (N2d):**
  - keep the phase, disabled;
  - a display-only global search under D1;
  - retire `entered_band` (option C, which breaks `ask_test.go:226, :539`);
  - build configuration 3 now.
- **Consequences:** D1–D7; §2a's identity and I1/I2; R1's gap; F9's `:486` reading.
- **Invalidates:** *none: no runs exist; logs written before the 1.3 commit carry the old meanings
  under the same keys.*
- **A row in the Summary table** (N2d).

### Experiment record (in `approvals.md`)

No run exists, so nothing is re-measured. The record states:
- `t_search_ms` is one span, and null wherever no search ran;
- the D1–D3 meanings;
- the counterfactual's new identity: configuration 4's support-off rule;
- `entered_band` ≡ TIER2_HIT until F-K or 2.1, together with I1 and I2;
- `reuse_rule` is present iff a candidate was judged, and its presence is not a hit (N5);
- logs are never mixed across the commit, and the discriminator between them;
- *"Tier-2 hit rate ≈ 0 on a warm cache: rule out the filter first"*, with demo step 3 as the
  witness (N4);
- decisions-changed-by-provenance has no derivation until configuration 3, the static-cache arm
  and the join script exist.
