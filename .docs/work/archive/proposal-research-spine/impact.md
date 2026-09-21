# Impact

**Packages touched:** none. This is a documentation-only change. `rag/`, `gateway/`, `contracts/`,
`data/` are untouched, so W6's build is unaffected and the layering in
`.docs/ai/architecture-guardrails.md` is not exercised.

**Frozen artifacts touched:** all three frozen documents.
- `docs/decisions.md` - three new ADRs (022, 023, 024).
- `docs/experiment-protocol.md` - `config_id` semantics (ADR-023); removal of the stale
  "bypass-classifier accuracy" metric, which ADR-018 already deleted but Section 4 still lists -
  a direct self-contradiction inside one section; embedding-model row still reads `TODO(ADR-003)`
  though ADR-003 froze on 2026-08-15.
- `docs/interfaces.md` - line 258 still calls ADR-003 "Open until W5"; it is Decided.

**Which prior runs are invalidated: NONE.** `experiments/results/` holds only `.gitkeep`; ADR-021
independently records "no experiment runs exist yet." The configuration restructure therefore costs
documentation, not data. This is the whole reason it is safe to do now rather than after W8.

**Reinstated scope:** none. The learned predictor, predictor-gated invalidation, GPTCache/vCache
integration, semantic routing, SSE, and the evaluated bypass classifier all stay out
(`Final_Proposal.md` Section 12, ADR-016/018). ADR-023 changes how configurations are *presented and
crossed*, not what they contain.

**Dependencies added:** none.

**Contract phase:** not required - no wire shape, chunk-ID format, or Redis schema changes. ADR-024
amends the `v1` corpus *content* spec in `data-card.md`, not `interfaces.md` Section C's ID scheme.

**Experiment phase:** REQUIRED - ADR-023 changes what `config_id` means in the run manifest, and
adds source mutation as an experimental axis. That is a change to how things are measured.

**Risk carried:** `docs/` is gitignored (`.gitignore:5`) and has no version history, so these edits
are not revertible through git. `CLAUDE.md` and `README.md` are tracked.
