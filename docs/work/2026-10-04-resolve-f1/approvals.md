# Approvals — resolve-f1

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | **yes**  | 2026-10-04 | ADR-003 (to be written) |
| contract       | if §B/§D | **not required.** No §A–§H surface changes; `interfaces.md:507` is a frozen-value restatement (`impact.md` §7) | | |
| experiment     | if measured — **required.** Admission sizing 4 → 1, the queue default 8 → 2, and the `make measure` gate change (`impact.md` §8) | **yes** | 2026-10-04 | ADR-003 (to be written) |
| implementation | always   | **yes**  | 2026-10-04 | ADR-003 (to be written) |

## Human decisions

| Date | Decision | Author's words | Invalidates |
| :--- | :--- | :--- | :--- |
| 2026-10-04 | Open item 1.1 **before** 1.2, against the recommendation to start with the `httpapi` tests | "làm 1.1 trước đi, mở task" | none |
| 2026-10-04 | **Approve the impact analysis** (`impact.md`). The task changes the frozen value `OLLAMA_NUM_PARALLEL = 4` (`decisions.md:59`, `interfaces.md:507`) | `/approve impact` | **No `run_id`**: none exists (`experiments/results/` holds only `.gitkeep`). It **relabels** μ_gen ≈ 28.2 tok/s and 0.19 req/s as planning figures from a one-slot server. It **voids** the W5 spike grid's `NUM_PARALLEL` axis and old ADR-022's "flat footprint" memory-proxy rationale. **No admission number is voided**, because none was recorded; A3's 4×200 / 4×503 was a non-citable `dev-v0` mechanism check (`impact.md` §3) |
| 2026-10-04 | **Approve the measurement change** as described in `impact.md` §8 and `design.md` §2 and §6. Gateway permits 4 → 1. Queue default 8 → 2 under the unchanged `2 × permits` rule, with **q a pre-registered parameter of item 7.5** and no shed rate read at an unregistered default. `make measure` now requires Ollama running with the frozen models loaded, and reads pressure with them resident. S2 is restated as queueing delay and goodput, not memory. Four §H fields change meaning (`shed`, `t_permit_wait_ms`, `permit_queue_depth`, `t_generate_ms`) | `/approve experiment` | Same as the impact row: **no `run_id`**. Every admission metric taken from here on means the restated quantity, and no earlier one exists to compare against. **Not decided by this approval:** whether `measure` re-checks the `ENVELOPE` line at run end. No target launches a measured gateway yet, so that belongs with the P1 manifest work (`design.md` §4, F-7, F-8) |
| 2026-10-04 | **Option A confirmed:** the effective slot count is frozen at 1, the gateway grants 1 permit, and S2 is restated as queueing delay and shedding rather than memory | "Yes, Option A (Recommended)" | As recorded in the impact and experiment rows |
| 2026-10-04 | **A2:** remove the machine-wide launchd pin (`launchctl unsetenv`, then unload and delete `com.thesis.ollama-env.plist`). What is frozen is the **effective** value, which the detector verifies | "A2: remove it (Recommended)" | none. The launchd value had no effect on either thesis model |
| 2026-10-04 | **Hold the version pin with (i):** turn off Ollama.app's auto-update. The app stays, under the run rule "no use of the Ollama app during a run" | "(i) Turn off auto-update (Recommended)" | none |

| 2026-10-04 | **Edit a comment in an immutable test file:** `gateway/internal/admission/pool_test.go:17-19`. Comment only, no code or assertion changed. The stale "a run can swap" memory claim is replaced by the ADR-003 slot-bound wording (`review.md`, implementation finding 2) | "ok sửa comment đi" | none. The test's behaviour is unchanged (`go test -count=1` passes) |
| 2026-10-04, after close | **Edit the docstring of an immutable test file:** `experiments/tests/test_env_check.py:1` and `:11` now point to `docs/work/2026-10-04-resolve-f1/` after the trails were dated. Path text only, no code or assertion changed (commit `e47c206`) | "ok làm đi", to the proposal to commit with the docstring fix | none. `ruff check` passes |
## Open — needs the author

*None. All three were decided on 2026-10-04; see Human decisions.*

## Taken by Claude as a default, open to reversal

- **V1 dropped.** No re-run of the W5 batch. The ADR says less instead: μ_gen is a planning
  figure until Phase 7 (`design.md` §3; the reviewer agreed).
- **ADR number 003.** ADR-001 stays reserved for item 1.6.
