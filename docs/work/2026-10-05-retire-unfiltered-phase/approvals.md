# Approvals — retire-unfiltered-phase

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | yes      | 2026-10-05 | — (no frozen value touched; no `run_id` invalidated: none exist, `impact.md` §2) |
| contract       | if §B/§D | yes      | 2026-10-05 | ADR-004 (to be written, plan step 4). §A/§H notes plus v0.10 per `design.md` §8; §B, §D, `.proto` and stubs untouched; no frozen value |
| experiment     | if measured | yes   | 2026-10-05 | ADR-004. Redefines `t_search_ms` and the meanings of `similarity`, `entered_band`, `source_overlap`, `reuse_rule` and the counterfactual (`impact.md` §5, `design.md` §8). Invalidates no `run_id`: none exist. Logs must not be mixed across the 1.3 commit |
| implementation | always   | yes      | 2026-10-05 | ADR-004 (written in plan step 4) |

## Human decisions

| Date | Decision | Author's words | Invalidates |
| :--- | :--- | :--- | :--- |
| 2026-10-05 | **Open item 1.3 at scope L** | "push đi rồi mở task 1.3" | — |
| 2026-10-05 | **D1: `similarity` on a refusal is the scoped candidate's, or `null`.** A cross-namespace lookalike now reports `null`. The §A lookalike-trap demo stops showing a high similarity beside the refusal; no display-only global search is kept | Chose *"null (Recommended)"* | none: no runs exist (`impact.md` §2). Logs written before the 1.3 commit carry the old meaning under the same key (S1) |
| 2026-10-05 | **D2: `entered_band` is restated, not retired.** It comes to mean "a same-namespace candidate cleared τ", which needs a §H field-note edit | Chose *"Restate it (Recommended)"* | none: no runs exist (`impact.md` §2). Logs written before the 1.3 commit carry the old meaning under the same key (S1) |
| 2026-10-05 | **D4: retire the stale tests.** Delete `rule_test.go`'s `wantSimOnly` column and check, `TestSimilarityOnlyIsTheBaselineCounterfactual`, `TestTauHighDefaultIsDisabled` and `TestTauHighDefaultSurvivesIdenticalVector`, and the `similarity_only_decision` string in `evallog_test.go:69`. The `Reuse` checks stay byte-identical. The identical-vector property moves to a live `httpapi` test (T6, `design.md` §4). The staleness proof is the contract itself: v0.9 retired what they assert | Chose *"Retire as stale (Recommended)"* | none: tests only |
| 2026-10-05 | **R1: accept the configuration-3 gap, with the startup guard.** Keep `cache.Store.NearestTier2` as configuration 3's primitive. The gateway refuses to start when `REUSE_TAU_HIGH` is non-empty. `/done` records that configuration 3, the static-cache arm and the join script have no `super-plan.md` item | Chose *"Accept gap + guard (Recommended)"* | none: the knob was disabled by default and no run used it |
| 2026-10-05 | **R3: ADR-004 names the §H expression behind each metric.** *"% reaching the provenance check"* is the share of past-Tier-1 records with `retrieved_chunk_ids != null` (the invariant check, 1.0 up to retrieval failures). *"% entering the cascade band"* is the share with `entered_band: true`. `Final_Proposal.md:407` stays true and is not edited | Chose *"ADR names expressions (Recommended)"* | none |
| 2026-10-05 | **R3 revised after `review.md` S1.** The expression above cannot fail: retrieval runs on every Tier-1 miss before and after 1.3, so it reads 1 minus the retrieval-failure rate and is blind to a re-added gate. ADR-004 instead defines *"% reaching the provenance check"* as **the share of records with `similarity != null` whose `reuse_rule` ∈ {`namespace`, `composite`}**. That is 1.0 by construction after 1.3; on today's code it reads 4/9. v0.10 names `reuse_rule` in §H, because the metric rests on it | Chose *"reuse_rule among judged (Recommended)"* | none |

## Open — needs the author

None. D4, R1 and R3 were decided on 2026-10-05 (above).

## Status (2026-10-05, resumed)

- Done: `SCOPE`, `spec.md` rev 2, `impact.md`, `design.md` rev 2, and the author's D1, D2, D4, R1 and R3.
- Done: `review.md` (opus): sound with changes, 0 blocking, 5 should-fix, 5 nits. All folded
  into `design.md` rev 3 and `plan.md`.
- Done: all four phases approved (2026-10-05). Implementation complete through `plan.md` step 4:
  - code and tests;
  - the evidence in `evidence/`: the startup guard, demo step 4, and the mutations;
  - `interfaces.md` v0.10, ADR-004, and the experiment record.

  `make verify` is green.
- Done: `/ai-review`. The diff conforms to v0.10; C1 and C2 (doc wording) are fixed.
- Next: `/done`. Nothing is committed yet.

## Experiment record (phase approved 2026-10-05; ADR-004)

No run exists, so nothing is re-measured. From the 1.3 commit on:

| Quantity | Before the commit | After |
| :--- | :--- | :--- |
| `t_search_ms` | the sum of a global and a scoped search span | **one** scoped span; null **exactly when no search ran** (embedding or retrieval failed, or the namespace resolved to empty). A search that found nothing or errored keeps its span |
| `similarity` | the global nearest, even from another namespace | the nearest **within the query's namespace**, or null |
| `entered_band` | the global nearest cleared τ (and `τ_high` did not fire) | a same-namespace candidate cleared τ: **≡ TIER2_HIT** while θ and the support gate are outside the served rule |
| `source_overlap`, `overlap_decision` | containment on the global nearest: pure containment, the pre-namespace C1 rule | containment on the judged candidate: **configuration 4's support-off rule**. Null on every refusal and on a retrieval failure |
| `reuse_rule` | present when a scoped candidate was judged after the global τ gate | present iff a candidate was judged, below-τ refusals included. **Its presence is not a hit.** (§H record; the response carries it only on a TIER2_HIT) |
| `similarity_only_decision` | present on banded requests | **absent** |

**Invariants a run can check from its own log:**
- **I1**, *% reaching the provenance check*: among records with `similarity != null`, the share with `reuse_rule` ∈ {`namespace`, `composite`} is 1.0.
- **I2**: no record has `entered_band ∧ cache ≠ TIER2_HIT`.

**Rules:**
- **Never mix logs from either side of the commit** in one figure.
- Until P1's manifest records the gateway SHA, the presence of the `similarity_only_decision` key
  is the only in-log discriminator.
- **Tier-2 hit rate ≈ 0 on a warm cache: rule out the namespace filter first.** A filter that
  matches nothing now looks like a cold cache. `make demo` step 3 is its live witness.
- **Decisions changed by provenance has no derivation** until configuration 3's served rule, the
  static-cache arm and the 3 ⋈ 4 join script exist. None has a `super-plan.md` item (R1).

## Taken by Claude as a default, open to reversal

- **D3**: the containment counterfactual (`source_overlap`, `overlap_decision`) is computed on the
  scoped candidate, the same entry the served rule judges (`spec.md`).
