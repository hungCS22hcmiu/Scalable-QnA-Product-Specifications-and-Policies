# Spec

**Change.** Rebuild the *research logic* of `docs/Final_Proposal.md` so every major design decision
is traceable to `Problem → Evidence → Gap → Requirement → Design → Hypothesis → Experiment →
Falsification`, per advisor feedback that the proposal has "many technical details but does not make
the reasoning behind the project sufficiently convincing."

**Serves:** advisor review (2026-08-18); pre-thesis submission Aug 31 (`time_line.md` W7).

**Acceptance:**
- A Design-Justification Matrix exists covering 14 decision rows, every cell citing a real ADR.
- Cache-layer terminology is pinned (response cache vs inference KV cache vs prompt/prefix cache).
- A Threats to Validity section exists (none exists anywhere in the repo today).
- Metrics carry an explicit claim linkage.
- RQ1 and RQ3 have pre-registered nulls (only RQ2 has one today).
- Five configurations are presented as a ladder x mutation grid, with Case 4/5 stated as
  mutation extensions of Case 2/3.
- `make check` stays clean; `make verify` unaffected.

**Out of scope** (deferred, stated so the omission is deliberate):
- Related Work chapter with verified citations - the `[verify]` block is **W10**. Writing it now
  would mean fabricating citations, which the advisor's own brief forbids.
- Dataset sensitivity *evidence* - `v1` does not exist; the gate applies to `v1` only; `dev-v0`
  is non-citable (ADR-020). Only the `v1` **spec** is amended here.
- The full 37-45 page pre-thesis report blueprint - roughly 2-3x current volume.
- Any change to `rag/`, `gateway/`, `data/` - W6 build must not be disturbed.
