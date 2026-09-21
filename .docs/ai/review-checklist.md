# AI review checklist

What the review subagents check. Each reviewer **Reads the governing doc at review time** — this file
lists what to look for, not what the answer is.

A finding must name the file, the line, and the rule or doc section it violates. "Looks fine" is not a
finding; neither is a style preference. **Report only what would fail silently or produce a wrong number.**

---

## `contract-reviewer` — runs when a diff touches the seam

Reads: `docs/interfaces.md`, `.docs/ai/rules.md`

- [ ] Wire field names match `interfaces.md` §A exactly — `source_overlap`, not `reuse_confidence`
- [ ] `source_chunk_ids`, `t1_key`, `dataset_epoch` present wherever the schema requires (rules #6)
- [ ] Proto changed? Then `.proto` was edited and `make proto` run — no hand-edited stubs (rules #4)
- [ ] Both sides of the seam agree: a field added in Go exists in Python and vice versa
- [ ] Redis keys match §D prefixes; dependency keys are in the **no-eviction** region (rules #5)
- [ ] Chunk IDs follow `{doc_id}#chunk-{ordinal}` and are not reassigned (§C)
- [ ] Epoch is stamped at retrieval and **compared at write-back** — the race is actually closed
- [ ] No `interfaces.md` change without a version bump and an ADR

## `experiment-reviewer` — runs when a diff touches measurement

Reads: `docs/experiment-protocol.md`, `docs/Final_Proposal.md` §9, `.docs/ai/rules.md`

- [ ] Metric computed as §4 defines it — hit ratio is hits ÷ **total**; shed is **not** counted as served
- [ ] Goodput, not throughput, wherever S1/S2 are involved
- [ ] `raw/` written once and never mutated (rules #3)
- [ ] `manifest.yaml` complete before the run produces output
- [ ] Frozen values read from config, never hardcoded at a call site (rules #1)
- [ ] Judge runs offline, generator unloaded, verdicts deduped by `sha256(query‖answer)`
- [ ] Thresholds tuned on validation, reported on **held-out test** (ADR-019)
- [ ] Nothing tuned, filtered, or re-run to improve a figure (rules #10) — **the sharpest check here**
- [ ] Hit-path latency reported decomposed, band branch separate from short-circuit

## `impact-analyst` — runs at the design phase

Reads: `docs/decisions.md`, `docs/interfaces.md`, `.docs/ai/rules.md`, `.docs/ai/architecture-guardrails.md`

- [ ] Which packages does this touch, and does it respect the layering?
- [ ] **Does it touch a frozen artifact?** If yes: which ADR, and which prior runs does it invalidate?
- [ ] Does it reinstate anything from §12's do-not-reinstate list (rules #2)?
- [ ] Does it add a dependency? (rules #9 — sign-off required)
- [ ] Does it change a contract? Then the contract phase is required before implementation
- [ ] Does it change what is measured? Then the experiment phase is required
- [ ] What is the smallest change that satisfies the spec?

## `rca-analyst` — runs only after a failed `/verify` plus one quick fix

Reads: failure output, `.docs/work/<task>/plan.md`, `.docs/ai/rules.md`

- [ ] Root cause stated as a mechanism, not a symptom
- [ ] Is the **test** wrong, or the **code**? Default assumption: the code
- [ ] A test may be changed only if it is provably stale or the spec changed — and that requires
      **explicit human confirmation**, recorded in `approvals.md`
- [ ] Does the failure indicate a guardrail was already violated upstream?
- [ ] Smallest correct fix, and what it would take to prevent the class of failure
