# Spec — docs-readme-architecture-refresh

**Scope:** S · **Opened:** 2026-10-07 · **Phase:** 2 (the support gate) — housekeeping that serves no
exit clause, opened at the author's request ("update README.md và các docs/architecture.md").
Phase 1 closed 2026-10-07 with 6 of 6 exit clauses, and neither file has moved with it.

## The change, in one sentence

Bring `README.md` and `docs/architecture.md` back in line with the repository as it stands on
2026-10-07 — status, what is built, what is served, the import graph, the tree, the command surface —
changing **prose only**, no code, no contract, no frozen value.

## What is stale (each verified against the tree, not remembered)

**`README.md`**
1. **Status** says Phase 1 is "in progress". It closed 2026-10-07 (`super-plan.md` Phase 1 progress
   note); Phase 2 is the current phase (`.claude/state/phase` = 2).
2. **Status overstates what is served.** It says "the reuse rule with its three lanes … built and
   tested", and the claim section describes four conjuncts. F-K is open (`super-plan.md`): the served
   Tier-2 rule is `similarity ∧ namespace`; θ reaches only a logged counterfactual and the support gate
   is Phase 2. The claim section stays as the claim; the status must say what runs.
3. **Invalidation is written in the present tense** ("dependent entries are purged exactly") but
   `gateway/internal/deps/` is a six-line `doc.go`. C2 is Phase 4.
4. **Load-testing row** says "Interference is measured and reported". ADR-001 says item 1.6 measured
   k6's own cost (1.0 → 4.8 % of one core, 21–28 MB, indicative) and that this is **not** an
   interference measurement; a co-hosted figure is a bound, an indicative reading or nothing, never a
   ceiling.
5. **`ADR-003` is cited three times with no pointer** to `docs/decisions.md`, and `architecture.md`
   calls the README a "landing page + document index" while it holds no index.
6. **Repository layout** omits `catalog`, the `deps` stub, `decisions.md` and `data/`; **Running it**
   omits `make env-check` and `make seam-check`.

**`docs/architecture.md`**
1. **§1 tree:** no `decisions.md`; `work/<task-slug>/` is now `work/<YYYY-MM-DD>-<slug>/`; `ragpb/`
   (generated, gitignored) is absent; `rag/` lists 5 of its 10 modules; `experiments/` omits
   `tests/` and most of `scripts/`; `k6/` is marked "(W8+)" but exists; `dev-v0` / `v1` carry week
   labels the repo retired on 2026-09-21; `contracts/normalize/cases.json` is absent.
2. **§2 layering diagram is not the import graph.** It draws `httpapi → admission → cache → reuse →
   ragclient`. The actual graph (`go list`): `httpapi` is the **only** package that imports siblings
   (`admission cache catalog coalesce embed ragclient reuse telemetry`); every other internal package
   imports none, and `ragclient` imports only generated `ragpb`. "Telemetry imported by all" is
   wrong — it is imported by `httpapi` and `cmd`. Reported as an **observation about today**, not a
   new rule: Phase 4's `deps/` will legitimately need `cache`.
3. **§4 command surface** lists 12 of the 23 targets `make help` prints.
4. **§5 inventory** is dated 2026-09-21: it says `httpapi` has no tests (item 1.2 closed that
   2026-10-04) and lists **`embed` under "built and tested" — it has no test file**. `make figures`
   invokes `experiments/scripts/make_figures.py`, which does not exist.
5. **§3** gets one sentence that the served Tier-2 rule is `similarity ∧ namespace` until F-K closes.

## Found while implementing (not in the list above)

- **README Stack row for the gateway named three primitives the code does not use.** It listed
  `atomic.Pointer` copy-on-write, `singleflight` and `x/sync/semaphore`; `go.mod` has no `x/sync`,
  `admission.Pool` is a channel-based counting semaphore, `coalesce.Group` is hand-rolled (its own
  comment says why), and `atomic.Pointer` appears nowhere because `deps/` is unbuilt. Row corrected.
  **`CLAUDE.md` makes the same claim** (`:129-134`, "semaphore", "`singleflight`", "`atomic.Pointer`
  copy-on-write") — out of scope here, reported alongside the `interfaces.md` v0.9 staleness.
- **`coalesce/` was missing from `architecture.md`'s tree and boundary table**, though §5 listed it as
  built. Added to both.

## Acceptance — checks that can be run

- `grep -n "in progress" README.md` finds Phase 2, not Phase 1.
- Every `ADR-NNN` in both files resolves to the entry of that number in `docs/decisions.md` that
  says what the sentence claims (ADR-001 co-hosting · 003 one slot · 004 retired phase · 005 answer
  store).
- Every package named in architecture.md §1 exists on disk, or is marked not built; every directory
  on disk under `gateway/internal/`, `rag/src/rag/` and `experiments/` appears in §1.
- Every `make` target named in either file appears in `make help`, and §4 names every target `make
  help` prints.
- `go list` re-run over `gateway/internal/*` reproduces the import statement in §2.
- `make check` (documentation consistency sweep) reports nothing new.
- `git diff --stat` touches exactly `README.md` and `docs/architecture.md` (plus this trail).

## Out of scope

- **`CLAUDE.md`** — also stale (it still says `interfaces.md` is "at v0.9"; the file is v0.12) but
  the author named two files. Reported, not edited.
- `docs/super-plan.md`, `docs/contracts/*`, `decisions.md`, `.claude/README.md`.
- **No claim is added or softened.** The research claim, the four-conjunct rule and the framing in
  `README.md` stay as written; only the *status* of what is built changes.
- No frozen value, contract, ADR or measured path is touched, so no prior run is invalidated (none
  exist).
