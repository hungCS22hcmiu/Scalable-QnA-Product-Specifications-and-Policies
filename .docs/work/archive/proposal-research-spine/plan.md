# Plan

- [x] ADR-022 - admission control (permit semaphore; alternatives: rate limiting, token bucket,
      queue-only, 429 vs 503) -> `docs/decisions.md`
- [x] ADR-023 - five-config ladder x mutation axis; Case 4/5 as mutation extensions -> `decisions.md`
- [x] ADR-024 - `v1` corpus data model + sensitivity-gate overlap formula -> `decisions.md`
- [x] `Final_Proposal.md` Section 2b - Design-Justification Matrix (14 rows, harvested from ADRs)
- [x] `Final_Proposal.md` Section 6.0 - cache-layer taxonomy (response vs KV vs prefix vs context)
- [x] `Final_Proposal.md` Section 9.2 - five-config x mutation grid + the mandatory Case 4/5 paragraph
- [x] `Final_Proposal.md` Section 9.4 - Threats to Validity (new; none exists in the repo)
- [x] `Final_Proposal.md` Sections 9.1/9.2 - add a claim-linkage column to both metric tables
- [x] `Final_Proposal.md` Section 5 - pre-registered nulls for RQ1 and RQ3 + a decision rule for RQ2's
- [x] `docs/data-card.md` - `v1` spec amendment + gate overlap formula
- [x] `docs/experiment-protocol.md` - config_id semantics; drop stale bypass metric; ADR-003 row
- [x] `docs/interfaces.md` - ADR-003 status line
- [x] `docs/decisions.md` - header date; ADR-006 W13/W14 mismatch
- [x] `CLAUDE.md` - data-card week (says W5, data-card says W8)
- [x] `make check` clean; `make verify` green; `[verify]` markers all still present
- [x] `/done`, then restore `.claude/state/active-task` to `w6-rag-gateway-skeleton`

**Outcome (2026-08-18).** All planned items shipped. `make check` clean on all four sweeps.

**`make verify` FAILS — pre-existing, not caused by this task.** `gateway/go.mod` declares zero
requires while the generated `internal/ragpb/*.pb.go` stubs (created 2026-08-16 00:07 by
`make proto`, commit 02cd446) import `google.golang.org/grpc` and `google.golang.org/protobuf`.
W5's "verify green" was recorded 2026-08-15, before those stubs existed. This task changed no code
— `git status` shows only `CLAUDE.md` and `README.md`, and `docs/` is gitignored. The fix is
**step 1 of `w6-rag-gateway-skeleton`'s plan** (add the three Go dependencies, which needs
sign-off per rules.md #9).

**Not closed via `/done`:** the precondition "`/verify` passed" is not met, and `/ai-review` was
not run. Left open deliberately rather than force-closed.

**Second advisor round, same day (2026-08-18).** Advisor supplied the research-first 9-step process
and a decision-tier taxonomy. It caught a real defect in the first round's work: the
Design-Justification Matrix listed "Go for the gateway" and "provenance-aware reuse" as **peer rows**,
flattening an implementation choice and the research claim to one level, and row 2 reproduced the
same author-preference reason ("Rust — learning cost") the advisor had asked to remove. Shipped:

- `Final_Proposal.md` **§7.0** — three decision tiers (Research / Architectural / Implementation),
  with the separating test *"if this choice were replaced by a reasonable equivalent, would the
  hypothesis still be tested identically?"*, plus Requirement/Decision/Rationale/Research-relevance/
  Control paragraphs for Go and gRPC, and the "why no broker on the query path" answer.
- **"matches the author's strengths" removed** from the §7 stack table; ADR-001 reframed to separate
  scientific justification from project-management rationale (Rust explicitly *not* rejected on merit).
- **New experimental control, previously absent anywhere:** the transport stack is held constant
  across all configurations, and gateway<->RAG overhead is measured as its own latency component
  (ADR-007, §9.4). Without it a config-3-vs-4 frontier gap could originate in the transport.
- **gRPC channel concurrency configured and recorded per run**, not left at defaults, with
  client-side queueing reported separately from permit-queue depth (`experiment-protocol.md` §1) —
  HTTP/2 stream caps otherwise look identical to gateway saturation.
- §2b rows tagged R/A so research and architectural decisions are no longer peers.

**Both open items resolved the same session:**
- **ADR-025 — no message broker.** Query path rejected on semantics *and* measurement; mutation path
  rejected because at ADR-009's single-node scope there is one producer and one consumer, so there is
  nothing to decouple, and a resident broker would land inside the RQ3 invalidation-under-load
  measurement. Redis Pub/Sub examined and rejected separately: fire-and-forget with no delivery
  guarantee would break C2 completeness **silently**. Recorded as the natural scale-out design in §14.
- **§10.1 comparison-matrix scaffold built** — 7 rows (GPTCache, vCache, Krites, RAGCache/CAG, IR
  result caches, materialized-view maintenance, LLM serving schedulers) × 6 research dimensions, plus
  a "this thesis" row. **Every external cell marked ⬜ needs verification**; nothing asserted. W10's
  row in `time_line.md` now says *fill the scaffold* rather than start from zero.

**Deferred, tracked:** Related Work with verified citations -> W10; dataset sensitivity evidence
-> W8; full 37-45 page report blueprint -> after W8. Two overdue items surfaced and NOT handled
here: **ADR-013 (LICENSE) is Open with decide-by W7**, and **ADR-016's "confirm with the advisor"
action** is still unrecorded.
