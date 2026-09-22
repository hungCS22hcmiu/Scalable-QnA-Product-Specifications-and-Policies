---
description: Structured root-cause analysis after a failed /verify plus one quick-fix attempt
---

Invoked when `/verify` failed twice. **Stop trying fixes.** Hand off to the `rca-analyst` subagent.

Give the agent:
- The full failure output from both `/verify` runs
- The one quick fix that was attempted, and why it did not work
- `docs/work/<task>/plan.md` and `spec.md`
- `docs/architecture.md` — the module boundaries the fix must respect

Require it to return:

1. **Root cause as a mechanism**, not a symptom. "The test fails" is not a root cause; "the epoch is
   stamped after retrieval returns, so a concurrent edit is not observed" is.
2. **Is the test wrong or the code wrong?** Default assumption: **the code.** Shifting to "the test is
   wrong" requires evidence that the test encodes an assumption the spec has since changed.
3. **Whether a guardrail was already violated upstream** — a failure here is often a symptom of a
   layering or contract breach committed earlier.
4. **The smallest correct fix**, and separately, what would prevent this class of failure.

Then:
- Write the analysis to `docs/work/<task>/review.md` under an `## RCA` heading.
- If the conclusion is "the test is stale / the spec changed", **stop and ask the human explicitly.**
  Record their answer in `approvals.md`. Do not change the test on your own judgement.
- If the conclusion is a code fix, add it to `plan.md` as a step and implement it, then `/verify` again.

If two RCAs in a row point at the same subsystem, say so — that is a design problem, not a bug.
