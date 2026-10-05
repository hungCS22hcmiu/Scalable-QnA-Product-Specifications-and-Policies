# Impact — retire-unfiltered-phase

*`impact-analyst` (opus), 2026-10-05. Recorded as returned. The corrections it implies for `spec.md`
are listed at the end. They are **not** applied here.*

> **No frozen value is touched and no run is invalidated, because none exists.**
> `experiments/results/` holds only `.gitkeep`. `TauHigh` / `REUSE_TAU_HIGH` is a demo knob that is
> frozen nowhere, and it ships disabled.
>
> **The invariant holds. It was checked, not only argued.** A scratch copy of the module had
> phase 1 deleted: one `NearestTier2InNamespace` search, with `Decide` run on the scoped candidate.
> The whole 1.2 suite then passes every `cache` outcome, status, answer and side-effect assertion.
> The only failures are `ask_test.go:287` and `:291`, both reported fields of
> `TestTier2RefusesAnEntryFromAnotherNamespace`. The invariant has three preconditions:
> - it is judged on one cache snapshot;
> - `REUSE_TAU_HIGH` is unset or > 1.0 (it is unset everywhere on this machine);
> - the index is exact (FLAT, which is frozen).
>
> **The contract phase is required.** Three reasons:
> - three §A/§H fields keep their names but change meaning;
> - five `interfaces.md` passages describe a short-circuit or a global nearest that will no longer
>   exist;
> - the retirement itself has never been ratified in `decisions.md`. `Final_Proposal.md:10-19`
>   says so.
>
> One ADR plus a version row covers all three.
>
> **The experiment phase is required, and small.** `t_search_ms` gets a new definition. The inline
> counterfactual disappears before anything replaces it. There is nothing to re-measure.
>
> **Three things the spec does not yet see:**
> - **D2 is constrained.** Retiring `entered_band` breaks `ask_test.go:226` and `:539`. Both are
>   outside what 1.2 allowed: *"If 1.3 breaks any other test of this task, 1.3 is wrong."* Restating
>   it as *"a same-namespace candidate cleared τ"* leaves `TestBelowTauDoesNotEnterTheBand`
>   byte-identical. But it contradicts `Final_Proposal.md:407` ("1.0 by construction").
> - **Keep `cache.Store.NearestTier2`.** Configuration 3 (fixed-τ, GPTCache's rule) *is* an
>   unfiltered k=1 search with a τ gate. The v0.9 join needs that configuration, and no item
>   builds it yet (F-K).
> - **`make demo` step 4 will print a fabricated `0.00`.** The trap question lands in another
>   policy namespace, so `source_overlap` comes back null. `Makefile:263-264` then formats the null
>   with `%.2f`. Bash prints `printf: null: invalid number` and then `0.00 < theta → REFUSE`. That
>   is F-E's signature, now in the demo.

## Packages touched

| Path | Change | Layering |
| :--- | :--- | :--- |
| `gateway/internal/httpapi/cascade.go:59-176` | Delete phase 1 and the short-circuit (`:79-105`). Check `retrieved == nil` before any Tier-2 work. Run one scoped search, then `DecideLane`, then `Decide` on the **scoped** candidate. Set `EnteredBand` per D2. Drop `similarity_only` from the log line (`:163-173`) | Imports unchanged: `cache`, `ragclient`, `reuse` |
| `cascade.go:29-37, :47` | Restate the `Search` comment ("SUM of two"), the `Overlap` comment ("short-circuit") and the `EnteredBand` comment | — |
| `httpapi/handler.go:56` | Remove `NearestTier2` from `cacheStore` | — |
| `handler.go:302-307, :565-571` | Remove the `SimilarityOnlyDecision` assignment and `hitOrMiss`, its only caller. `make lint` is `gofmt` + `go vet` (`Makefile:290-293`), which do not flag a dead unexported function | — |
| `handler.go:231-235`, `types.go:55-60` | Comments that cite the short-circuit or `similarity_only_decision`. `types.go:58` trips acceptance 1's grep | — |
| `reuse/rule.go:82-140` | Delete `Thresholds.TauHigh` (`:88-112`) and `Decision.SimilarityOnly` (`:120-125`, `:138`) | Stays stdlib-only |
| `reuse/lane.go:259-269, :272-282` | Delete `RuleSimilarityOnly`. Restate the `NamespaceDecision.Overlap` comment, which cites `similarity_only_decision` (`:267`, trips acceptance 1) and "the rule this one replaced" | — |
| `telemetry/evallog.go:3-7, :38, :64-67` | Delete the field. Restate the package doc (`:6` trips acceptance 1) and the `ReuseRule` comment | Still imports nothing from the repo |
| `cmd/gateway/main.go:8, :104-114, :142-153` | Delete `TauHigh`, `REUSE_TAU_HIGH`, the short-circuit startup line, and the `math` import (its only use) | Wiring only |
| Tests | `reuse/rule_test.go`, `telemetry/evallog_test.go:69`, `httpapi/ask_test.go:287, :291`, `httpapi/harness_test.go:60-61` (plus the optional `:316-323` and `:325-335`), and one **new** `httpapi` test file | See §6 |
| **Unchanged** | `cache/` (see §1), `ragclient/`, `embed/`, `admission/`, `coalesce/`, `catalog/`, `contracts/rag/v1/rag.proto`, `rag/`, `go.mod`, `go.sum` | — |
| Contract phase | `interfaces.md:119-120, :132-133, :138, :430, :447, :477, :485`, the version row (`:499-503`); one new `decisions.md` ADR | §4 |
| At `/done` | `architecture.md:114-115`; `super-plan.md:118-120, :126`; `Final_Proposal.md:407, :589` (the author's prose, gitignored); `Makefile:263-264` and `ui/src/pages/ProductChat.jsx:67-70`, depending on D1 | §8 |

## 1. Layering, and where `NearestTier2` goes

**Layering is respected.** Every edit removes code, and no import is added.
- `reuse` stays stdlib-only (`rule.go:3-5`).
- `telemetry` still imports nothing from the repo (`architecture.md:106`).
- `httpapi` keeps importing `cache`, `reuse` and `ragclient`. All three already exist, and all
  point right (`architecture.md:90`).
- `main.go` and `rule_test.go` lose `math`. Forgetting that is a compile error, not a silent one.

**Callers of `cache.Store.NearestTier2` (`tier2.go:133-136`), whole repo, `.git` excluded:**

| Site | What it is |
| :--- | :--- |
| `httpapi/cascade.go:82` | The phase being deleted |
| `httpapi/handler.go:56` | The interface method |
| `httpapi/harness_test.go:316-323` | The fake |
| `httpapi/ask_test.go:589` | A string passed to `fail()`, not a call |
| `cache/tier2.go:64` | A comment ("see NearestTier2") |
| `catalog/`, `cmd/`, `experiments/scripts/`, `experiments/k6/`, `ui/`, `rag/` | **None.** `catalog` runs its own search on the *corpus* index. No Python touches `idx:cache` (`grep idx:cache\|KNN`) |
| `docs/` | Trails only (history) |

**The verdict:**
- **Remove it from `cacheStore`: yes.** Then the cascade *cannot* call it through `h.Cache`, so
  acceptance 2's "never" becomes a compile-time fact. The fake keeps compiling, because a type with
  extra methods still satisfies the smaller interface (`harness_test.go:254`).
- **Remove it from `cache/`: no. Keep it.**
  - Configuration 3 serves the global nearest at `sim ≥ τ`, with no namespace. It is *"Fixed-threshold
    semantic (best τ) — also GPTCache's decision rule"* (`Final_Proposal.md` §9.2). That is exactly
    `NearestTier2(vec, 1)` plus a τ gate.
  - v0.9 retires the phase **inside configuration 4's cascade**. It does not retire
    configuration 3's mechanism: the counterfactual becomes *"a cross-configuration join of
    configurations 3 and 4"* (`interfaces.md:477`).
  - Nothing builds configuration 3 yet. `ConfigID` selects nothing (F-K, `super-plan.md:149-152`),
    and no item owns it.
  - Deleting the method now means re-adding it then.
  - The smallest change leaves `cache/` untouched. An **optional** one-line doc comment at
    `tier2.go:133` could say "configuration 3's primitive; not on configuration 4's path".
- **A caution that comes with keeping it.** One mutation stays invisible to every fake:
  `h.Cache.(*cache.Store).NearestTier2(...)` inside the cascade. The type assertion fails against
  the fake, so every test passes. Only a grep catches it (§9, S4).

## 2. Frozen values, measured path, invalidated runs

**Frozen values touched: none.**

| Candidate | Evidence | Verdict |
| :--- | :--- | :--- |
| `TauHigh` / `REUSE_TAU_HIGH` | Absent from: `decisions.md` (inherited state `:54-68`, ADR-001 to ADR-003); the frozen list at `interfaces.md:507`; the §9.2 configuration grid; §9.4's swept parameters (*"four swept parameters (τ, θ, σ_lo, σ_hi)"*, `Final_Proposal.md:451`); `data-card.md`; the `Makefile` (the demo reads only `REUSE_TAU`/`REUSE_THETA` at `:230`, and `measure` at `:94-104` sets no threshold). `rule.go:82-83` calls the thresholds demo values. It ships `+Inf` (`main.go:114`) and is unset in the environment, in `launchctl getenv` and in the shell profiles | **Not frozen.** This removes a disabled knob |
| τ, θ, `LaneBand` | Read the same way as before | Untouched |
| FLAT index | `tier2.go:78-85` | Untouched. **The invariant depends on it** (§3) |
| `top_k`, embedding model, `DIM`, chunking, capacity ratio, δ, `dataset_version`, `num_ctx`, slots | — | Untouched |

**Measured path: touched.** Searches per Tier-1 miss that has a vector:

| Request | Searches today | Searches after | `t_search_ms`, today → after |
| :--- | :---: | :---: | :--- |
| Retrieval failed | 1 global | 0 | a span → `null` |
| Global nearest below τ | 1 global | 1 scoped | the global span → a TAG-filtered hybrid span |
| Global nearest ≥ τ, empty namespace | 1 global (the scoped call returns before Redis, `tier2.go:153-157`) | 0 | a span → `null`, **provided the no-op call is not timed** (S2) |
| Global ≥ τ, namespace non-empty (**every Tier-2 hit**) | 2, summed (`cascade.go:29-33`) | 1 | a sum → one span |
| Empty cache | 1 global | 1 scoped | span → span |

So the spec's *"every Tier-1 miss does one Redis KNN search fewer"* is true for hits and banded
refusals. Below-τ requests swap one search for another.

**Cost: estimated, not measured.**
- **No benchmark exists.** `grep -rn "func Benchmark" gateway` finds nothing.
- **It could not be measured live.** At analysis time:
  - RediSearch held **no index**. `FT._LIST` was empty; DB 0 held 51 keys, 3 of them `t2:`. The
    gateway creates `idx:cache` only at startup (`main.go:91`), and creating one here would be a
    write to the shared DB 0.
  - Memory pressure read **2 (urgent)**.
- **The estimate:**
  - At dev size, one loopback `FT.SEARCH … KNN 1` returning 11 fields (`tier2.go:187-199`)
    costs ≈ 0.1–0.3 ms. That is mostly the round-trip and the parse.
  - On top of that comes a brute-force term, linear in the number of cached entries: one 768-d
    cosine per entry. At a few hundred entries that adds ≈ 0.05–0.1 ms.
  - The Tier-2 critical path is ≈ 18 ms (`handler.go:226-235`, the maximum of embed and retrieve).
    So the saving is ≈ 1 %.
- **No separate experiment is needed.** §H logs `t_search_ms` per request, so Phase 7 measures the
  real figure.

**μ_hit:**
- **Tier 2.** Each hit loses one Redis round-trip. At saturation, though, Tier 2 is bounded by the
  **one-slot `nomic-embed-text`**, which serves both the query embedding and `Retrieve`'s
  (`super-plan.md:253`). Redis is a different resource, so μ_hit moves little or not at all, and it
  cannot move down.
- **Tier 1, ≈ 8000 req/s.** It returns at `handler.go:204-222`, before Tier 2. Untouched.
- **The planning figure of ≈ 61 req/s** (2026-09-06, not citable, `Final_Proposal.md:101`) was taken
  with up to two searches per hit, when τ_high defaulted to 1.0 (`main.go:104-108`).
  - It stays a valid **lower bound**. h* rises with μ_hit (`super-plan.md:286-293`), and removing
    work cannot lower μ_hit.
  - The 3.8× margin is unchanged.

**`run_id`s invalidated: none.**
- `experiments/results/` holds only `.gitkeep`. The only commit that ever touched it is `3901066`.
- No `requests.jsonl` exists anywhere in the tree.
- `make dev` writes no log: `RUN_ID` is empty (`main.go:202`).

## 3. Is "served decisions are identical" true?

**Yes, on any single cache snapshot, given `REUSE_TAU_HIGH` unset or > 1.0.** Every path through
`tryTier2` and `Ask`'s use of `t2` (`handler.go:274-311`) is listed below. "Today" refers to
`cascade.go` and `handler.go`.

| # | Path | Today | After | Served | Reported change |
| :---: | :--- | :--- | :--- | :---: | :--- |
| 1 | `vec == nil` (embed failed) | Zero outcome (`:75-77`) | Same | MISS = MISS | None (`ask_test.go:538-539` hold) |
| 2 | `retrieved == nil`, global < τ | `Found`, early return (`:96-98`) | No search | MISS = MISS | `similarity` → null; `t_search_ms` → null |
| 3 | `retrieved == nil`, global ≥ τ (**F-E**) | `EnteredBand = true` then a zero `Decision` (`:106-112`) | No search | MISS = MISS | `entered_band` true → false; `source_overlap` 0 → null; `overlap_decision` false → null; `similarity_only_decision` `"MISS"` → absent; `similarity` → null; `t_search_ms` → null. **F-E is closed** |
| 4 | Global search errors | Degrades to MISS (`:84-87`) | No global search | MISS | — |
| 5 | Cache empty | `:88-90` | The scoped search returns nothing | MISS = MISS | None |
| 6 | Global < τ, retrieval ok | Early return (`:96-98`) | Scoped `c`, with `c.sim ≤ global.sim < τ`, so `DecideLane` refuses (`lane.go:295, :351`) | MISS = MISS | None under D2-B. Under A′: `entered_band` → true and `source_overlap` → a number. `reuse_rule` goes `""` → `"namespace"` if `DecideLane` runs unconditionally (D6) |
| 7 | Global ≥ τ and `TauHigh` fires | Served with no provenance (`:102-105`) | The branch is gone | **Differs** | Reachable only with `REUSE_TAU_HIGH ≤ 1.0`. Default `+Inf`; the harness's zero value is disabled by `TauHigh > 0` (`:102`); unset on this machine. This is the precondition |
| 8 | Global ≥ τ, `QueryNS == ""` | The scoped call returns nil (`tier2.go:153-157`); `served := nearest`; refused | No Redis call | MISS = MISS | `similarity` global → null; `entered_band` true → false (B); `source_overlap` → null |
| 9 | Global ≥ τ in another namespace, nothing in the query's | `served := nearest`, refused (`:141`) | The scoped search is empty | MISS = MISS | As row 8. **This is `TestTier2RefusesAnEntryFromAnotherNamespace`** |
| 10 | Global ≥ τ, scoped search errors | Returns `Found`/`EnteredBand` for the global nearest (`:134-137`) | Error → MISS | MISS = MISS | `similarity`, `entered_band` and `source_overlap` of the global nearest → null / false |
| 11 | Global ≥ τ, scoped `c` ≥ τ, same namespace | `DecideLane` serves `c` (`:142-153`) | The same call | HIT `c` = HIT `c` | `source_overlap` and `overlap_decision` are now `c`'s (**F-G fixed**). Identical whenever the global nearest is `c` |
| 12 | Global ≥ τ elsewhere, scoped `c` < τ | `DecideLane` refuses on τ | Same | MISS = MISS | `similarity` global → `c`'s; `entered_band` → false (B); `source_overlap` → null. `TestAnotherNamespaceAboveTau…` asserts the outcome only, and holds |
| 13 | MIXED lane (band open) | Composite namespace, `DecideLane` at `lane.go:348-359` | Same | Same | As rows 11 and 12. The collapsed default (`main.go:136-137`) never reaches it |

**Why row 6 holds.** The scoped candidates are a subset of the global ones, and FLAT is exact. So
`c.sim ≤ global.sim`, computed by the same distance function. Under HNSW the global "nearest" could
be approximate, and the subset argument would fail. The invariant rests on the frozen index.

**Side effects do not flip either:**
- The hit-count bump (`handler.go:320-326`), the touch (`:327`) and the Tier-1 promotion
  (`:343-354`) key on `t2.Candidate`, and only when `NSDecision.Reuse` is true (`:311`). In row 11
  that is the same `c` before and after.
- The miss path's writes (`:436-472`) read `vec`, `retrieved` and `t1Key`, never `t2`.
- The counters key on `rec.Cache`.

**Two qualifications:**
- **The claim holds per snapshot.**
  - Today's two searches can see two cache states. A write-back or a `TrimToCapacity` eviction can
    land between `:82` and `:132`. After the change there is one search, so one state.
  - Under concurrent load an outcome can therefore differ by timing, as it already does from run
    to run. The change removes a race window; it adds none.
  - On the static-cache arm, where nothing writes, the equivalence is exact.
  - The shorter path also shifts coalescing windows slightly (`handler.go:396`).
- **Failure counts.** A banded request now makes one fewer Redis call, so there is one fewer place
  where a transient error turns a would-be hit into a MISS (row 4). This is a difference in
  outcomes under failure, not in decisions.

**The empirical check.** It ran in a scratch copy of the module, in the session scratchpad; nothing
was committed. `tryTier2` was replaced with:
1. `vec` or `retrieved` nil → return a zero outcome;
2. derive the lane and namespace; an empty namespace → return;
3. one `NearestTier2InNamespace`;
4. `DecideLane` on `c`;
5. `EnteredBand` and `Decide` only if `c.sim ≥ τ`.

`go test -count=1 ./internal/httpapi/` then failed **only**
`TestTier2RefusesAnEntryFromAnotherNamespace`:
- at `:287`: `similarity is null`;
- at `:291`: `entered_band = false, want true`.

With `EnteredBand` set whenever a scoped candidate exists (A′), `TestBelowTauDoesNotEnterTheBand`
also fails, at `:316` (`source_overlap = 1, want null`) and `:320`. The baseline suite was green
beforehand.

## 4. Contract

**Required.** The field set barely moves: `similarity_only_decision` is already absent from §H's
example (`interfaces.md:432-472`), so the record only catches up. What makes this a contract change
is that the code is what gives three fields their meaning, and five passages describe a mechanism
that is about to stop existing.
- **Precedent:** v0.6 took a version row for restating `entered_band` alone (`:505`).
- **The rule:** any change needs a dated `decisions.md` entry and a version bump (`:6`, `:497`).

**What must change:**

| Where | Today | Must say |
| :--- | :--- | :--- |
| `:119` (example comment) | `similarity` *"null on TIER1/BYPASS"* | Also null on a MISS with no in-namespace candidate, a failed embedding, or a failed retrieval |
| `:120`, `:133`, `:447` | `source_overlap` *"null unless the cascade ran"* / *"null when the cascade short-circuited"* | Per D2-B: *"null unless retrieval succeeded and a same-namespace candidate cleared τ"* |
| `:132` | `similarity` *"of the matched Tier-2 entry"* | *"of the nearest entry **within the query's namespace**"* (D1) |
| `:138` | *"a high-similarity, low-overlap miss is the lookalike trap the rule exists to catch"* | **Unreachable after 1.3 while F-K stands.** A cross-namespace lookalike becomes a MISS with `similarity: null`. A same-namespace candidate with high similarity and low overlap is **served**, with `overlap_decision: false`. Annotate it, or restate it as *"a TIER2_HIT with `overlap_decision: false` is a reuse the containment conjunct would have refused"* |
| `:430` | *"% entering the cascade band"* | Align with `Final_Proposal.md:407`'s naming, per D2 |
| `:485` | `entered_band` *"Distinguishes short-circuit hits from cascade-band hits"* | The D2 restatement. With τ_high gone, the band is [τ, 1] |
| `:477` | *"A log written before v0.9 carries the old field"* | *"…before the 1.3 commit."* The code emitted the field until 1.3 lands, so a log dated after v0.9 can still carry it |
| `:499-503` | v0.9 | A new version row |
| **Unchanged** | §B, §C, §D, §E, `.proto`, both stubs | — |

**ADR.** `decisions.md` holds no entry that ratifies the retirement. `Final_Proposal.md:10-19` names
it as pending: *"ahead of the decision records that must ratify it … retiring the unfiltered phase,
`τ_high`, and the inline `similarity_only_decision`"*.

One ADR (the next free number, ADR-004) should:
- ratify the retirement;
- record D1–D7;
- carry **Invalidates:** *none — no runs yet*. Add that logs written before the 1.3 commit carry
  the old meanings under the same key names.

## 5. Measurement

**What is measured changes, so the experiment phase is required.**
1. **`t_search_ms`** is redefined: one span instead of a sum of two, and `null` wherever no search
   ran (rows 2, 3 and 8). It is not comparable across the commit.
2. **`similarity`, `source_overlap` and `entered_band`** change meaning (D1–D3).
3. **The containment counterfactual changes identity (D3).**
   - **Today:** `Decide(nearest)` is pure containment on the *global* nearest. That is the C1 rule
     as it stood before namespaces (`cascade.go:114-115`: *"apples-to-apples with the pre-existing
     rule"*).
   - **After:** `Decide(c)` on the in-namespace candidate computes `sim ≥ τ ∧ namespace ∧ overlap ≥ θ`.
     That is **configuration 4's support-off rule** (§9.2 row 4).
   - **What is gained:** the logged counterfactual matches the claim, and F-K's gap (served versus
     configuration 4) becomes readable on every request.
   - **What is lost:** no log can re-derive "namespace versus pure containment" any more, the
     comparison `lane.go:259-269` and `:286-291` cite. No configuration in the grid needs it.
4. **`similarity_only_decision` disappears.** Decisions-changed-by-provenance then has no derivation
   until the replacement below exists.
5. **`reuse_rule`** (an extension field) appears on below-τ refusals (D6).

**Nothing needs re-measuring, because no runs exist.** The experiment phase records three things:
- the new meanings;
- the rule never to mix logs from either side of the commit;
- a discriminator between them: the gateway SHA in the manifest. That manifest's schema does not
  exist yet (P1, `decisions.md:75`). Until it does, the presence of the `similarity_only_decision`
  key is the only discriminator inside the log.

**Configuration 3 and the 6.3 join.** Removing the field breaks nothing that exists, because
Phase 6 has no code. But it removes the only **existing** derivation of a non-negotiable metric
(`Final_Proposal.md:586-588`) before its replacement exists.

**What the replacement needs:**

| Need | Status |
| :--- | :--- |
| A configuration-3 served rule: global k=1 plus τ, no namespace | Not built. `ConfigID` selects nothing (F-K). **No `super-plan.md` item.** It needs `Store.NearestTier2` (§1) |
| A static-cache mode: pre-populated, write-disabled | Item 6.3, not built. It must also disable Tier-1 promotion (`handler.go:343-354`) and the LRU touch/trim. Otherwise configurations 3 and 4 diverge in Tier 1, and the join compares different tiers |
| A query-identity join key | `request_id` differs per run (cf. `interfaces.md:477`). Use `query_normalized` + `product_id`. `product_id` has been in the Tier-1 key since 2026-09-09 (`types.go:18-22`), and §H logs it with `omitempty` (`evallog.go:68-73`) |
| The join script | Not built |

**One collision ahead:** acceptance 6's *"re-adding an unfiltered search is caught by a test"* will
fire on configuration 3 the day it is built, unless the test is scoped to configuration 4's cascade.

## 6. Tests

**`reuse/rule_test.go`.** Every case below is a staleness fix: the field was retired at v0.9
(`interfaces.md:41-45, :477, :503`).

| Test | Lines | After 1.3 | What to do |
| :--- | :--- | :--- | :--- |
| `TestDecideRequiresBothConditions` | the `wantSimOnly` field at `:87`, its column at `:89-92`, the check at `:99-101` | Compile error | Delete the column and the check. The `Reuse` checks (`:96-98`) stay byte-identical |
| `TestDecideBoundariesAreInclusive` | `:105-119` | Unaffected | — |
| `TestSimilarityOnlyIsTheBaselineCounterfactual` | `:121-134` | Compile error | Delete. Its `Reuse` half (`:128-130`) is already covered by the trap case at `:90` and by `TestOverlapEdgeCases:65` (empty retrieval scores 0) |
| `TestTauHighDefaultIsDisabled` | `:178-197`; pins `TauHigh: 1.0` at `:185` | Compile error | Delete. It has been stale since 2026-09-09: it pins `1.0`, and `main.go:114` ships `+Inf` |
| `TestTauHighDefaultSurvivesIdenticalVector` | `:199-213` | Compile error | Delete it, and drop `math` (`:4`). The regression class (an identical question served across products with no namespace check) is now closed by structure. Move its **property** into the new `httpapi` file: the identical question, another product, spec lane → MISS |
| `reuse/lane_test.go` | — | Unaffected | `RuleSimilarityOnly` appears in no test |

**`telemetry/evallog_test.go`:**

| Test | Line | After 1.3 | What to do |
| :--- | :--- | :--- | :--- |
| `TestNullableFieldsRenderAsNull` (`:49-82`) | `:69` lists `similarity_only_decision` | **Fails at run time**, at `:75` ("is missing"), once the field leaves `Record` | Staleness. Remove the one string. Acceptance 3 belongs in `httpapi`, via `fields.absent` (`harness_test.go:1162`) |

**`httpapi/harness_test.go`.** This is scaffolding under 1.2's `approvals.md` item 4: a note in the
trail suffices, as long as no strict check is loosened.

| Site | After 1.3 | Recommendation |
| :--- | :--- | :--- |
| `:60-61`, the comment *"TauHigh is never named … after 1.3 deletes the field"* | Acceptance 1's grep hits it | Edit the comment |
| The fake's `NearestTier2` (`:316-323`) | Compiles unchanged, as a superset | **Delete it.** If anyone then re-adds `NearestTier2` to `cacheStore`, `:254` stops compiling, which is the catch acceptance 6 wants, for free. Deleting a method nothing calls loosens no check |
| `NearestTier2InNamespace` (`:325-335`) | — | **Record the namespace argument**, so a test can assert the search ran on the *query's* namespace. That catches an unfiltered search re-added through a wildcard namespace |

**`httpapi/ask_test.go`.** Its assertions are immutable; 1.2's item 2 names the two tests 1.3 may
change. The "measured" results come from the scratch run in §3.

| Test | Lines | After 1.3 | Kind |
| :--- | :--- | :--- | :--- |
| `TestTier2RefusesAnEntryFromAnotherNamespace` | `:287` `resp.notNull("similarity")`; `:291` `rec.boolean("entered_band", true)` | **Fails (measured)** | A reported-field change, authorised in advance (item 2) and contingent on D1 and D2. It is not a staleness RCA. It becomes `resp.null("similarity")` and `rec.boolean("entered_band", false)`. The status check (`:282`), `cache` MISS (`:285`), the answer (`:286`) and the single `Answer` call (`:292`) are unchanged |
| `TestBelowTauDoesNotEnterTheBand` | `:316`, `:320` | **Passes unchanged** under D2-B (measured). Fails at both lines under A′ | — |
| `TestTier2SearchFailureDegradesToMiss`, subtest "both searches" | `:589` | Passes (measured). The scoped failure still fires, so `injectedCount() > 0` at `:604` | **Vacuous**, not broken. Its `NearestTier2` injection targets a method nothing calls, so it now duplicates the second subtest, and its name is false. The file is immutable: leave it, and record it |
| `TestAnotherNamespaceAboveTauDoesNotLiftAnEntryBelowTau` | `:689-716`, outcome only | Passes (measured) | Keep. It catches the mutation where a global τ gate lifts a scoped entry below τ |
| `TestRetrieveFailureDegradesToMiss` | `:551-578` | Passes. It asserts nothing F-E corrupts | Acceptance 4's F-E test must be **new**, not an edit here |
| `TestEmbedFailureDegradesToMiss` (`:538-539`), `TestTier2HitInsideTheNamespace…` (`:218-228`), `TestTier1Hit…` (`:54-62`) | — | Pass | `:226` and `:539` need the `entered_band` **key** to exist: `boolean` calls `get`, which Fatals on an absent key (`harness_test.go:1118-1124, :1141`). **So D2's option C, retiring the field, breaks two tests outside item 2's allowance** |

## 7. Cut scope and new dependencies

**No cut scope is reinstated.** Nothing on `Final_Proposal.md:590`'s list is touched. This task
*executes* `:589` (*"Retired, not merely disabled … not yet executed in code: item 1.3"*).

Keeping `Store.NearestTier2` (§1) does not reinstate anything:
- What was retired is the phase **inside configuration 4's cascade**, together with its
  short-circuit.
- Configuration 3's similarity-only rule is in the grid (§9.2 row 3).

**No new dependency.** The resident footprint is zero, and the binary loses code.

## 8. Docs that go stale

| Doc | Lines | Stale text | When |
| :--- | :--- | :--- | :--- |
| `interfaces.md` | the §4 table | — | Contract phase |
| `architecture.md` | `:114-115` | A "Tier-2 hit (short-circuit)" row. A "cascade band → `ragclient.Retrieve`" row, which is already wrong because retrieval runs concurrently | Collapse into one Tier-2 row, at `/done` |
| `Final_Proposal.md` (gitignored; the author's prose) | `:10-19` | The ratification is still pending | Once the ADR exists |
| | `:407` | *"% reaching the provenance check … 1.0 by construction"* | Conflicts with D2-B. The author decides |
| | `:589` | *"decided, and not yet executed in code"* | At `/done` |
| | `:101`, `:189-195`, `:223` | Already correct. `:191` states the invariant §3 confirms | — |
| `super-plan.md` | `:118-120`, `:126` | The progress line and the 1.3 row | At `/done` |
| `decisions.md` | — | Silent on the retirement | The new ADR |
| `CLAUDE.md`, `data-card.md`, `README.md`, `.claude/` | — | No live mention of τ_high, `similarity_only` or a short-circuit (grep). `design-reviewer.md:24` is history | — |
| `Makefile` | `:251`, `:263-264` | Demo step 4, *"the trap — high similarity, different evidence"*; `%.2f` applied to a null. Assumes `DEMO_Q4` (sofa) ranks a different return policy first than `DEMO_Q1` (headphones), as `lane.go:174-177` records for this pair | D1 |
| `ui/src/pages/ProductChat.jsx` | `:67-70`, `:149-153` | Null-safe (`fmt` at `:13` renders "—"), but the promised demonstration loses its high-similarity number | D1 |
| Code comments | `types.go:58`, `lane.go:267`, `evallog.go:6`, `harness_test.go:60` | Cite retired names. Acceptance 1's grep hits all four | In this task |

## 9. What would fail silently

Ranked.

| # | Hazard | Evidence | Design must |
| :---: | :--- | :--- | :--- |
| S1 | **Same key names, different quantities.** D1–D3 and `t_search_ms` change meaning under unchanged keys. A figure over logs from both sides of the commit mixes global-nearest and scoped values, with no error | `interfaces.md:477` dates the boundary at v0.9, but the code kept emitting the old meanings until this commit | Put the boundary at the **commit** in the ADR and the §H note. Record the SHA once P1's manifest exists. Until then, the presence of the `similarity_only_decision` key is the discriminator |
| S2 | **`t_search_ms: 0` instead of null.** Suppose the cascade calls `NearestTier2InNamespace(…, "", …)` and times it. The real Store returns in ~100 ns without touching Redis. `durMS` rounds that to `0.000`, and `msPtr` returns a pointer because the duration is not zero. The result is a zero that reads as a measurement, and it drags the mean down. The same happens on rows 2 and 3 if anything is timed there | `tier2.go:153-157`; `handler.go:187-188, :555-563` | Neither call nor time the search when `retrieved == nil` or the namespace is empty. The fake cannot reveal this (1.2 `impact.md` S5) |
| S3 | **`entered_band` is chosen without reading `Final_Proposal.md:407`.** Under B its share is not 1.0, so an analyst running §9.2's "invariant check" against it sees a failed invariant. Under A′ it is nearly constant | `Final_Proposal.md:407`; `interfaces.md:430` | Record in the ADR which §H expression computes "% reaching the provenance check" (under B: `retrieved_chunk_ids != null` among records past Tier 1) |
| S4 | **Vacuous mutation tests.** Three ways:<br>(a) Once `NearestTier2` leaves `cacheStore`, a fake call-count for it is 0 by construction.<br>(b) A re-added short-circuit ships disabled (`+Inf`, or zero in the harness), so no behavioural test can see it. Only acceptance 1's grep can, and only if it reuses the old names.<br>(c) `h.Cache.(*cache.Store).NearestTier2` is invisible to every fake | Acceptance 2 and 6; `cascade.go:102`; `harness_test.go:254` | Run acceptance 1's grep and `grep -n 'NearestTier2(' gateway/internal/httpapi/*.go` (non-test files) inside `/verify`. Assert the scoped search's namespace argument. Make the short-circuit test **live**: an identical question about another product at `sim = 1.0` must MISS |
| S5 | **The demo prints a fabricated overlap.** Step 4 shows `0.00 < theta → REFUSE`, which `printf` invented from a null. It is the same shape as F-E | `Makefile:263-264`; verified: `printf '%.2f' null` prints `0.00` and exits 1, and the recipe's `;` chain carries on | Use the recipe's `num` helper, or skip the line when the value is null. Either way, record it under D1 |
| S6 | **Comments go on describing the old counterfactual.** After D3 the number is configuration 4's rule, but the comments still say *"what the rule this one replaced would have scored"* | `lane.go:259-269`; `types.go:55-60`; `cascade.go:114-115` | Restate all three in this task |
| S7 | **A NaN similarity.** Today's early return is `sim < τ` (`:96`), so a NaN "enters the band". `DecideLane`'s `>=` refuses it | `1 − ParseFloat("nan")`, `tier2.go:228-232` | Write the band test positively, `sim >= τ`, so the reported field agrees with the served rule |
| S8 | **Configuration 3 gets blocked.** Deleting `Store.NearestTier2`, or an acceptance-6 test that is not scoped to configuration 4, leaves Phase 6 either unable to build configuration 3 or facing a test that forbids it. The temptation will be to weaken the test | §1, §5 | Keep the method. Scope the test |
| S9 | **Timing and races** (the qualifications in §3) | — | Nothing. Not a regression |

## Smallest change that satisfies the spec

**Keep:**
- **`cascade.go`:**
  - `vec` or `retrieved` nil → return a zero outcome;
  - derive the lane and namespace, and return when the namespace is empty, without calling the
    search or timing it;
  - one timed scoped search, then `DecideLane` on its first candidate;
  - **if `c.sim >= τ`**: `EnteredBand`, `Decide(c)` and `NSDecision.Overlap`.
- **Delete** `TauHigh`, `SimilarityOnly`, `RuleSimilarityOnly`, `REUSE_TAU_HIGH`, the startup
  line, `hitOrMiss` and the §H field.
- **Remove `NearestTier2` from `cacheStore`.**
- **Test edits:**
  - `rule_test.go`: remove the four `SimilarityOnly`/`TauHigh` sites;
  - `evallog_test.go:69`: remove one string;
  - `ask_test.go:287, :291`: two lines, under D1 and D2.
- **Harness:** fix the comment at `:60-61`. Optionally delete the fake's `NearestTier2` and record
  the namespace argument.
- **One new `httpapi` test file** covering:
  - one scoped search, on the query's namespace;
  - F-E: the retrieval-failure record and response;
  - no `similarity_only_decision` key;
  - an identical question about another product at `sim = 1.0` → MISS;
  - on a hit, `source_overlap` describes the served entry when another namespace holds a closer
    one (F-G).
- **Comments** in `types.go`, `lane.go` and `evallog.go`.

**Cut:**
- Any edit to `cache/`, except the optional doc line.
- `refusal_cause` (2.3).
- Putting θ into the served decision (F-K).
- Renaming or retiring `entered_band`.
- Any edit to the "both searches" subtest.
- Any harness change that loosens a check.
- A demo rebuild. The `Makefile` null guard is one line, and D1 decides it.

## Invalidates

**Nothing.**
- **`run_id`s:** none exist.
- **Frozen values:** none changed. No ADR is needed **for a frozen value**. One is needed for the
  contract (§4).
- **Planning figures:** Tier-2 ≈ 61 req/s remains a valid lower bound. The Tier-1 probe is
  untouched.
- **Logs:** none exist. Any future log must not be mixed across the commit (S1).

> **Required phases:** impact · contract · experiment · implementation, plus design → opus
> design-review → plan for scope L.
> - **Contract:** the §A and §H note edits, a version row, and one ADR that ratifies the retirement
>   and records D1–D7. No change to §B, §D or the `.proto`.
> - **Experiment:** the `t_search_ms` redefinition, the D1–D3 meanings, the counterfactual's new
>   identity, and the gap until configuration 3 and the static arm exist. Nothing to re-measure.
> - **No precondition:** 1.2 and 1.4 are committed (`8d637f7`, `d96c0cb`), so acceptance 5's diff
>   has a baseline.

---

## Corrections this implies for the trail (not applied)

| # | Where | Correction |
| :---: | :--- | :--- |
| 1 | `spec.md` "Why scope L" | *"Every Tier-1 miss does one KNN fewer"* → Tier-2 hits and banded refusals do one fewer. Below-τ requests swap a global search for a scoped one. Retrieval-failed and empty-namespace requests do none (§2) |
| 2 | `spec.md` D2 | Add the constraint: option C (retire) breaks `ask_test.go:226, :539`, which 1.2's item 2 excludes. A′ changes `:316, :320`. B leaves `TestBelowTau…` byte-identical and conflicts with `Final_Proposal.md:407`. **Recommend B**, because it is the band's old definition with τ_high → ∞, read on the scoped candidate |
| 3 | `spec.md` D table | Add three rows:<br>• **D5:** `t_search_ms` is null on rows 2, 3 and 8.<br>• **D6:** `reuse_rule` appears on below-τ refusals if `DecideLane` runs unconditionally.<br>• **D7:** the response's `overlap_decision` is null on a retrieval failure |
| 4 | `spec.md` D3 | State that the counterfactual becomes configuration 4's support-off rule, and that "namespace versus pure containment" can no longer be derived from a log (§5) |
| 5 | `spec.md` acceptance 1 | Name the comments it will hit: `types.go:58`, `lane.go:267`, `evallog.go:6`, `harness_test.go:60` (the last under item 4's note). Add `grep -n 'NearestTier2(' gateway/internal/httpapi/*.go` (non-test files), and run both in `/verify` |
| 6 | `spec.md` acceptance 2 | Change "retrieval succeeding" to "retrieval succeeding **and a non-empty namespace**". Replace "the global `NearestTier2` never" (vacuous once the method is off the interface) with "the namespace argument equals the query's namespace" |
| 7 | `spec.md` acceptance 4 | Add `similarity: null`, `t_search_ms: null` and the response's `overlap_decision: null`. Without them, a global search kept on the retrieval-failure path passes |
| 8 | `spec.md` acceptance 5 | New tests go in a **new** file, or `git diff -- ask_test.go` shows them. Name the exact lines: `:287`, `:291` (under D2-B, `TestBelowTau…` is unchanged) |
| 9 | `spec.md` acceptance 6 | A disabled short-circuit cannot be caught by behaviour. Test a **live** one (the same question about another product at `sim = 1.0` → MISS) and grep for the rest. Scope the "unfiltered search" mutation to configuration 4's cascade, because configuration 3 will need one |
| 10 | `spec.md` "Out of scope" | Resolve `cache.Store.NearestTier2`: **keep it** as configuration 3's primitive. There is no caller outside the request path (§1) |
| 11 | `spec.md` D1 | Name the concrete demo costs: `Makefile:263-264` (a fabricated `0.00`) and `ProductChat.jsx:67-70` |
| 12 | `spec.md` "Rests on" | The retirement has no `decisions.md` entry (`Final_Proposal.md:10-19`). The contract phase's ADR ratifies it |
| 13 | At `/done` | `architecture.md:114-115`; `super-plan.md:118-120, :126`; `Final_Proposal.md:407, :589` (the author's); add to the F-K note that configuration 3 has no owning item |
