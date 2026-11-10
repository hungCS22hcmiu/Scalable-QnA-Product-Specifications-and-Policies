# Deliverables — The POLICY namespace names the product too (ADR-024)

Closed 2026-11-10 · super-plan item 5.6: built; its Phase 6 clause stays open (below)

## What shipped

- With a `product_id`, a POLICY namespace is `{policy_doc}@{product_id}`, so a policy answer is reused only
  for the product it was written for. Without a `product_id` it stays `{policy_doc}`, with no fallback to a
  product chunk. The SPEC and MIXED namespaces, Tier 1, τ, the gate and the lane band do not change.
- `@` differs from MIXED's `|`, and the order is reversed, so a POLICY and a MIXED namespace never meet.
- Docs: `interfaces.md` v0.32 (§A's `product_id` row; §D's `t2:` schema now lists `namespace` and `lane`),
  ADR-024 and F-NAME marked built, item 5.6's text, eight edits in `Tier 2.md`, and the `lane.go` comments.

## Files changed

- `gateway/internal/reuse/lane.go`: `policyProductSeparator`, the POLICY branch of `Namespace`, and the
  comments at the file header, `LaneMixed`, `Namespace` and `mixedSeparator`.
- New tests: `reuse/lane_policy_product_test.go` (3 tests, 3 subtests), `httpapi/policy_product_test.go`
  (a fake `policyRAG` and 1 test), `cache/tier2_policy_namespace_test.go` (1 test, on the test Redis).
- `gateway/internal/httpapi/mixed_lane_test.go`: the one line `policyNS`, approved by the author on
  2026-11-10 (design.md §4).
- `docs/contracts/interfaces.md`, `docs/decisions.md`, `docs/super-plan.md`, `docs/1-System Docs/Tier 2.md`.
- **Frozen values touched: none.** The served rule's POLICY namespace changed, as ADR-024 decided.
  **Prior runs invalidated: none citable.** The judge cost run `2026-11-01T21-17-56_cfg4_judgecost` and the
  2026-11-07 runs behind `Tier 2.md` are read as "before ADR-024".
- Not this task: `gateway/cmd/gateway/main.go` (the gateway drain fix) is still uncommitted.

## How it was verified

Main session, 2026-11-10, after the executor:
- `make verify` → exit 0. rag 94 passed, experiments 1117 passed, every Go package ok. No SKIPPED target.
  Inside the Go run, four tests skip as before: `TestSeam`, `TestSupportLive`, `TestSupportSample`
  (they need a live rag.server) and `TestMeasureWriterDrain` (a measurement).
- DC 1 → all pass, run with `-count=1`. Before the change, `two_products_two_namespaces`, `the_form` and
  `TestPolicyEntryOfAnotherProductIsRefused` failed (`evidence/dc1_before.out`).
- DC 2 → both tests pass, no SKIP. Before the change, product B's request was a TIER2_HIT on product A's
  entry (`evidence/dc2a_before.out`).
- DC 3 → the approval is in §4, dated; the stale failure is in `evidence/dc3_stale.out`; the diff is the
  `policyNS` line; `on` and `off` pass.
- DC 4 → before: Q4 judged against H1's entry; after: Q4 a MISS with nothing judged; Q3 judged in both runs.
- DC 5 → `v0.32` in five places of `interfaces.md`; the counts of plan steps 4.1–4.4 hold; `lane.go` names
  ADR-024 four times.
- DC 6 → only `lane.go` and the approved test line are modified; three new test files.

## Numbers

All `citable: no`. Corpus `v1`, `make dev` with MIXED off (`LANE_SIGMA_HI=0.20`), gate on, τ 0.85, the
cache reset before each run, pressure 1 at the first request and 2 after.
- Before: Q2 MISS. Q3 at similarity 0.9256 and Q4 at 1.0000, both in `policy-warranty-electronics`, both
  refused by the gate (`SUPPORT`, `S_lex` 0.4375 of 32 words), so no wrong answer was served this time.
- After: Q2 MISS in `policy-warranty-electronics@product-electronics-b07zj7qg33`. Q3 TIER2_HIT at 0.9256
  (`S_lex` 1.0000 of 1 word: that run's answer was very short). Q4 MISS, `similarity` null, in
  `policy-warranty-electronics@product-electronics-b079jfb616`.

## Deferred and follow-ups

- **Item 5.6 is not marked ✅ Done.** Its "Done when" third clause and ADR-024's check 3 belong to Phase 6:
  count POLICY hits whose entry was written for another product (0 expected for requests with a
  `product_id`), and report such false hits as their own cause, from `product_id` and `entry_sources`.
- `docs/learning/Final_Proposal.md`, the author's to edit: line 159 (the MIXED lane's reason: "taking the
  policy drops the product") and lines 434–439 (`product_id` "is not otherwise part of the reuse decision";
  ADR-024 credits provenance only for B-within).
- Phase 6 should expect fewer POLICY hits and more generations: one entry per product per policy.
- The replay shows the fix as "judged → not judged". It could not show a wrong answer being stopped, because
  the gate refused Q4 in the before-run.
- Two plan slips, with no code effect (design.md §4): the count in 4.4 and the quoting in 7.3.
- The work sits on the branch `fl-cancel-and-rag-shutdown`, on top of the F-L commit.
