# Spec — architecture-refresh

**Scope:** S · **Opened:** 2026-10-16 · **Phase:** 3 (corpus and workload) — housekeeping that serves no
exit clause, opened at the author's request ("read the current codebase and update docs/architecture.md").

## The change, in one sentence

Bring `docs/architecture.md` in line with the code as it stands on 2026-10-16, changing **prose only**:
no code, no contract, no frozen value.

## What is stale (each checked against the code, not remembered)

1. **ADR-007 and ADR-008 are missing.** Both list `docs/architecture.md` as an affected file, and the
   doc names neither: Redis holds only derived state (ADR-007), and the epoch must not be a Redis key
   (ADR-008).
2. **§6 invariant 4 reads as if the epoch guard works.** The epoch is `DATASET_EPOCH_STUB = 0`
   (`rag/src/rag/config.py:34`); write-back stores it and never compares it
   (`gateway/internal/httpapi/handler.go:467`); `writeback_discarded` is never assigned (item 4.2).
3. **The old "no-eviction region".** §6 invariant 2 and the `deps/` row in §2 still describe the v0.3
   two-region split. Since `interfaces.md` v0.6, Redis evicts nothing and the gateway trims entries
   through `lru:entries` (`cache/capacity.go`, `TrimToCapacity`).
4. **Smaller drift.** `cmd/gateway` holds tested pure functions (`gateFromEnv`, `retiredEnv`,
   `incomplete`, `finishRun`), so "no logic" is not accurate. `httpapi` also serves `/products` and
   `/stats`. A miss passes the retrieved chunk IDs to `Answer`, so Python does not retrieve twice. A
   Tier-2 serve promotes into Tier 1 with an untracked key (item 4.3). `corpus_gate.py` has G1–G4 only
   (G5 is item 3.5). The tracked `docs/0. progress 16-10.md` is not in the tree.

## Found while implementing (reported, not fixed)

- **`make check` now prints "clean" when it is not.** `DOCSRC` splits `docs/0. progress 16-10.md` and
  `docs/Redis-Data Structure.md` at their spaces, so `grep` exits 2 on the missing pieces and
  `|| echo "  clean"` fires even after real hits are printed. The sweep's "clean" line cannot be trusted
  until those two files are renamed or `DOCSRC` handles spaces. This change adds no new hit.
- **`CACHE_CAPACITY` defaults to `0` (unbounded)** (`gateway/cmd/gateway/main.go:272`). Added to §3,
  since it is why the trim on the miss path does nothing today.

## Acceptance — checks that can be run

- `go list` over `gateway/...` reproduces the import graph in §2.
- Every `make` target in §4 appears in `make help`, and the reverse.
- Every ADR and item number added resolves to the entry in `docs/decisions.md` or `docs/super-plan.md`
  that says what the sentence claims.
- `make check` reports nothing new.
- `git diff --stat` touches only `docs/architecture.md` (plus this trail).

## Out of scope

- `docs/Redis-Data Structure.md` is untracked (the author's draft), so it is not added to the tree.
- No new "must never" rule is added for `httpapi` or `embed`.
- `README.md`, `CLAUDE.md`, `interfaces.md`, `super-plan.md` and `decisions.md` are not edited.
- No frozen value, contract, ADR or measured path is touched, so no run is invalidated (none exist).
