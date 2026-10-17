# Spec — tier2-explainer

**Scope:** S · **Opened:** 2026-10-16 · **Phase:** 3 — documentation that serves no exit clause, opened
at the author's request: a doc in `docs/Tier 2.md` that lets a reviewer new to the project understand
the Tier-2 semantic cache, from the idea to the mechanism, with examples in detail.

**The change, in one sentence:** write `docs/Tier 2.md` (empty today) as a stand-alone explainer of
Tier 2 as the code serves it at commit `33a1a9d`, with no code, contract or frozen value changed.

**Acceptance:** every number in the doc traces to a test fixture, the real-answer sample
(`docs/work/2026-10-14-real-answer-sample/sample-results.md`), the 15 Oct demo log
(`docs/0. progress 16-10.md`) or a default in `cmd/gateway/main.go`; the tests the examples rest on pass
(`go test ./internal/reuse -run 'TestNoThetaSeparatesTheMeasuredPair|TestSupportLexicalSeparatesTheMeasuredPair|TestNumericMeasuredPair|TestJudgeAgreesWithDecideLane'`);
the served rule is stated per gate arm, and containment is stated as logged-only; no item number or
ADR appears before the "Further reading" section; `git status` shows only the doc and this trail.

**Second change, same day, at the author's request:** a "Manual demo on the UI page" section in
`docs/0. progress 16-10.md` (new §1.6; Invalidation renumbered to §1.7). Its lanes, namespaces and
similarities come from a read-only preview run with the gateway stopped and no cache key touched
(`evidence/demo_preview*.py`, output in `evidence/preview-output.txt`; memory pressure 1, exploratory).
The gate's verdicts and latencies cannot be previewed and are stated as such.

**Third change, 2026-10-17, at the author's request ("update README.md"):** Status (the support gate
built, Phase 3 started with item 3.1, Phase 2 closed 2026-10-15), the Documents table (`docs/Tier 2.md`,
the progress report), the Redis row (ADR-007), the `data/` and `cmd/` layout lines, and how to run both
demos and the PQA build. Prose only; the claim, the rule and the framing are unchanged.

**Found by the preview (reported, not fixed — `reuse/` is scope L):**
- **The POLICY namespace follows the question's words, not the product's category.** On the sofa page,
  "Can I return this after 30 days?" ranks `policy-returns-electronics` first, so it shares a namespace
  with the headphones return question (similarity 0.8732). Only the gate stands between the sofa and the
  electronics answer.
- **Product scoping makes one policy chunk decide the lane.** On a product page the retriever drops other
  products, so "How long does the battery last?" keeps two chunks (`policy-warranty`, the product) and
  becomes POLICY in `policy-warranty`. The same words on the Pro page share that namespace at similarity
  1.0000, so the product namespace no longer protects a spec question.
- **The single warranty document puts every category in one namespace** (the G5 residual, live): laptop
  "How long is the warranty on this?" against headphones "… on these?" scores 0.9397.

**Out of scope:** editing the Redis draft, the Redis draft, `architecture.md` or any contract;
any new measurement. No run is invalidated (none exist).
