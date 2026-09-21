# Impact analysis

**Packages touched:** none. This task writes only to `docs/decisions.md`, `docs/interfaces.md`,
`docs/experiment-protocol.md`, and `docs/worklog/W05.md`. No `gateway/`, `rag/`, or `contracts/`
source exists yet for this change to touch — layering in `.docs/ai/architecture-guardrails.md` is
not implicated.

**Touches a frozen artifact — yes, two:**
- **ADR-002** (generation LLM: Gemma 4 E4B) is superseded by a new ADR (next number after ADR-020
  = **ADR-021**). Alternatives tested and rejected are recorded in the ADR itself.
- **ADR-017** (envelope frozen from measurement) moves from `Open — blocks W5` to `Decided
  (frozen)`, with the actual measured `num_ctx`, `OLLAMA_NUM_PARALLEL`, and μ_gen.

**Invalidates:** none. No experiment run has executed — `docs/worklog/W05.md`'s log is empty,
`experiments/results/` has no run directories. This decision lands before any measurement that
would need to be discarded.

**Reinstates anything from `Final_Proposal.md` §12's do-not-reinstate list?** No. This is an
infrastructure swap (which model serves generation), not a scope change — the learned predictor,
predictor-gated invalidation, GPTCache/vCache integration, semantic routing, SSE streaming, and
bypass-classifier evaluation are untouched.

**Adds a dependency?** No. Generation is still called over the same Ollama HTTP API `rag/generate.py`
was already going to use for the embedding endpoint (`httpx`, already in `rag/pyproject.toml`) — only
the model tag and one request parameter (`think: false`) change.

**Changes a contract (`interfaces.md` surfaces)?** Yes, minor — the `model_used` example/literal
value and the "Frozen study-wide" line's `num_ctx`/`OLLAMA_NUM_PARALLEL` values move from
placeholder/open to their decided values. No wire-shape change. **Contract phase: required**
(interfaces.md is edited).

**Changes what or how anything is measured?** Yes — `experiment-protocol.md` §1.1's memory-budget
table TODO cells are filled with real spike numbers, and §1's "Frozen for the whole study" LLM line
changes. **Experiment phase: required** (experiment-protocol.md is edited).

**Implementation phase:** required (no source code lands in this task, but marking as required per
the approvals template; nothing to unlock beyond the doc edits themselves under the W5–W7
lightweight gate, ADR-020).
