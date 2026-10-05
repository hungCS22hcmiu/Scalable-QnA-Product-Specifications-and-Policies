# Spec — retire-unfiltered-phase

**Scope:** L · **Opened:** 2026-10-05 · **Phase:** 1, item **1.3**
**Revision 3**, after `review.md`. Rev 2 applied all 13 of `impact.md`'s corrections, and D1/D2 are
the author's. Rev 3 amends D2 and acceptance 1, 6, 7, 8 and 9 for `review.md`'s S1–S5 and N1, as
`design.md` rev 3 records.

## The change in one sentence

Remove the retired parts of the Tier-2 cascade, so that configuration 4's cascade issues **at
most one** namespace-scoped search and the code conforms to `interfaces.md`. Three things go:
- the unfiltered Tier-2 search phase;
- the `TauHigh` / `REUSE_TAU_HIGH` short-circuit;
- the `similarity_only_decision` record field.

The contract notes these change are restated, and the retirement is ratified in an ADR.

## What it serves

- **Phase 1, item 1.3** (`super-plan.md`): *"The cascade issues one scoped search; `grep -r
  tau_high` finds only history; §H no longer carries the retired field."* It also corrects the
  stale pinned default in `rule_test.go`.
- **Exit-criterion clause discharged:** *"no retired branch remains in the cascade."*
- **Discharges:** C1, C3. `contracts/requirements.md` is still empty.
- **Rests on:** the advisor-approved pivot of 2026-09-15. `Final_Proposal.md:10-19` names this
  retirement as **awaiting a decision record**, and `decisions.md` has none. `interfaces.md` v0.9
  already describes it (`:34-45`, `:477`), but the code still runs the branch. **This task's
  contract phase writes ADR-004 to ratify it.**

## Why scope L

- **It touches `reuse/`.** `rule.go` holds `TauHigh` and `Decision.SimilarityOnly`; `lane.go` holds
  `RuleSimilarityOnly`.
- **It touches a measured path** (`impact.md` §2):
  - Tier-2 hits and banded refusals do one Redis KNN fewer.
  - Below-τ requests swap a global search for a scoped one.
  - Retrieval-failed and empty-namespace requests do no search at all.
- **It changes §H and §A meanings.** One field goes. `similarity`, `source_overlap`, `entered_band`
  and `t_search_ms` keep their names but change meaning. Contract phase, experiment phase, ADR-004.

## The invariant: served decisions do not change

Verified, not only argued: `impact.md` §3 deleted phase 1 in a scratch copy and ran the 1.2 suite.
Only `ask_test.go:287` and `:291` failed, both reported fields.
- **Why it holds.** The scoped candidates are a subset of the global ones, and the FLAT index is
  exact, so `c.sim ≤ global.sim`. If the global nearest is below τ, the scoped one is too.
  Otherwise today's code already decides on the scoped candidate with `DecideLane`.
- **What it needs:** one cache snapshot; `REUSE_TAU_HIGH` unset or above 1.0 (the default is `+Inf`,
  and it is unset on this machine); and the frozen FLAT index. Under HNSW the subset argument fails.
- **F-K is preserved, not fixed.** The served rule is similarity ∧ namespace, and θ stays in the
  counterfactual. This task must not move θ into the served decision.

## What changes in reporting

| # | Field | Today | After | Status |
| :---: | :--- | :--- | :--- | :--- |
| D1 | `similarity` | the global nearest, even from another namespace | the nearest **within the query's namespace**, or `null` when there is none, or when the embedding or retrieval failed | **Author: null** |
| D2 | `entered_band` | the global nearest cleared τ and `TauHigh` did not fire | **a same-namespace candidate cleared τ.** Retiring it is ruled out: it would break `ask_test.go:226, :539`, outside 1.2's allowance | **Author: restate.** While the served rule is sim ∧ namespace, this **equals the TIER2_HIT indicator** (`review.md` S2; `design.md` §2a). `:407` is reconciled by R3 (`approvals.md`) |
| D3 | `source_overlap` / `overlap_decision` (the counterfactual) | `Decide` on the global nearest: pure containment, the pre-namespace C1 rule | `Decide` on the scoped candidate: `sim ≥ τ ∧ namespace ∧ overlap ≥ θ`, which is **configuration 4's support-off rule**. F-K's gap becomes readable on every request. "Namespace versus pure containment" can no longer be derived from a log, and no configuration needs it | Default |
| D4 | tests outside 1.2's two | assert `TauHigh`, `SimilarityOnly`, the stale `1.0` default, and the `similarity_only_decision` key | removed as **stale**, since v0.9 retired what they assert (`impact.md` §6) | **Author** |
| D5 | `t_search_ms` | the sum of two searches | one span, `null` wherever no search ran (retrieval failed, empty namespace) | Default |
| D6 | `reuse_rule` | `""` on a below-τ refusal (early return) | `"namespace"` / `"composite"` whenever a scoped candidate exists, since `DecideLane` ran | Default |
| D7 | response `overlap_decision` on a retrieval failure | `false` (F-E) | `null` | Default (F-E closed) |

**Demo costs of D1–D3** (`impact.md` corrections 11):
- `make demo` step 4 runs `printf %.2f` on a `source_overlap` that is now `null`, which would print
  a **fabricated `0.00`** (`Makefile:263-264`) under the old "overlap < θ → REFUSE" story. **In
  scope:** that step must never print a number derived from `null`.
- `ui/src/pages/ProductChat.jsx:67-70`'s hint text describes the old cross-product refusal. **Out of
  scope**; recorded.

## Acceptance — each is a check that can be run

1. **No retired code is left.**
   `grep -rnE "TauHigh|tau_high|REUSE_TAU_HIGH|SimilarityOnly|similarity_only" gateway rag
   --include='*.go' --include='*.py'` finds only comments that name the retirement as history.
   Those include the rewritten `types.go:58`, `lane.go:267`, `evallog.go:6` and
   `harness_test.go:60`, and the startup guard. The grep `grep -n 'NearestTier2(' gateway/internal/httpapi/*.go`
   finds no non-test call site. `grep -c 'retiredEnv(os.Getenv)' gateway/cmd/gateway/main.go`
   prints `1`.
2. **At most one scoped search, on the query's namespace.** On a Tier-1 miss with retrieval
   succeeding and a non-empty namespace, the cascade calls `NearestTier2InNamespace` exactly once,
   with the query's namespace as its argument. The fake records the argument. `NearestTier2` leaves
   `cacheStore` and the fake, so a global search cannot return without editing the interface.
3. **§H.** No record carries a `similarity_only_decision` key (`fields.absent`).
4. **F-E is closed.** On a `Retrieve` failure with a same-namespace entry at or above τ:
   - the record shows `entered_band: false`, and `source_overlap`, `similarity` and `t_search_ms`
     all `null`;
   - the response shows `source_overlap`, `overlap_decision` and `similarity` all `null`;
   - no search ran.
5. **Served outcomes are unchanged.** Every `cache` outcome, HTTP status and answer asserted in
   `gateway/internal/httpapi/ask_test.go` holds. That file changes **only** at `:287`
   (`notNull("similarity")` → `null`) and `:291` (`entered_band` `true` → `false`), under D1 and
   D2. `TestBelowTauDoesNotEnterTheBand` stays byte-identical. New tests go in a **new** file.
6. **Mutations, scoped to configuration 4's cascade.** Configuration 3, when built, will search
   globally by design. Each of these is caught:
   - a re-added global search (compile, and the namespace argument);
   - the global nearest reported on a refusal;
   - `EnteredBand` set before the `retrieved` check;
   - the counterfactual computed on any other candidate;
   - `entered_band` and the served τ disagreeing at `sim == τ`;
   - the field re-added;
   - a search, or a span, on an empty namespace (`design.md` T7);
   - a namespace derived after retrieval failed (served without provenance).

   A re-added short-circuit ships disabled, so behaviour cannot catch it. The **property** is
   tested live instead: the byte-identical question about another product, at `sim = 1.0`, is a
   MISS. Everything else is caught by acceptance 1's grep.
7. **Startup guard.** If `REUSE_TAU_HIGH` is non-empty, the gateway refuses to start and names the
   retirement, so no run can believe it is a configuration-3 baseline (`design.md` R1). The
   evidence is a recorded run of the built binary with `REUSE_TAU_HIGH=0.95` and every address at
   `127.0.0.1:1`. It exits 1 with the message before any dial, and an empty value gets past the
   guard.
8. **Demo.** `make demo` step 4 prints no number derived from a `null`, and no verdict word or
   comparator it did not read from the response (`review.md` S5). Checked on the step's formatting
   fragment with `null` and `0.25`, without a live run.
9. **Contract.** `interfaces.md` v0.10 carries every row of `design.md` §8's table. That table
   covers `impact.md` §4 plus `:3`, `:448`, `:486` and a `reuse_rule` row. ADR-004 records:
   - the retirement and D1–D7;
   - the `entered_band` ≡ TIER2_HIT identity, with I1 and I2;
   - R3's metric expression;
   - its Alternatives, and a Summary row;
   - *"Invalidates: none — no runs yet; logs written before the 1.3 commit carry the old meanings
     under the same keys."*
10. `make verify` is green.

## Out of scope

- **F-K**: putting θ into the served decision.
- **Configuration 3.** Its served rule (global k=1 + τ), the static-cache mode, the query-identity
  join and the join script. None of these has a `super-plan.md` item (`impact.md` §5). **Keep
  `cache.Store.NearestTier2`**: it has no caller after this task, but it is configuration 3's
  primitive (`impact.md` §1). Recording the missing owner is a `/done` step.
- `refusal_cause` (2.3), the support gate (2.1–2.2), F-A, F-F, F-J.
- The UI hint text, and any demo redesign beyond acceptance 8.
- `Final_Proposal.md` (the author's prose): `:407` and `:589` are listed at `/done`, not edited here.
