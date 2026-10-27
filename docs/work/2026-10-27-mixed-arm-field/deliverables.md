# Deliverables — Name the MIXED arm in every record

Closed 2026-10-27 · super-plan item 4.5 · ADR-016

## What shipped

- Every evaluation record carries a required key, `mixed_lane` (`"on"` | `"off"`), never null, with no
  `omitempty`. It is derived from `Handler.LaneBand`, the same field both lane decisions read, so the label
  and the behaviour cannot come from two places.
- The gateway reads the band once at start (`bandFromEnv`, right after `gateFromEnv`). It accepts only
  ADR-016's two bands: [0.20, 0.20), off and the default, and [0.20, 0.60), on (`LANE_SIGMA_HI=0.60`). An
  empty, unparseable or unpinned value stops the process before Redis, the RAG connection or the run directory.
- `interfaces.md` is at v0.16: the key, invariants I10–I12, the old-log reading rule (no key reads as off; a
  `composite` record disproves it), and the run identity `(config_id, mutation, support_gate, mixed_lane)`.
- The stale "swept / DEMO value" text about the band is gone from `lane.go`, `main.go`, `handler.go` and README.

## Files changed

- `gateway/internal/reuse/lane.go`: `PinnedLo`, `PinnedHiOn`, `LaneBand.Pinned()`, `LaneBand.Arm()`, comment.
- `gateway/internal/telemetry/evallog.go`: `Record.MixedLane`.
- `gateway/internal/httpapi/handler.go`: `MixedLane: h.LaneBand.Arm()` in the record literal; comments.
- `gateway/cmd/gateway/main.go`: `bandFromEnv`, its call, the split start-up log line; comment.
- New tests: `reuse/lane_band_test.go`, `telemetry/mixed_lane_field_test.go`, `cmd/gateway/lane_env_test.go`,
  `httpapi/mixed_lane_test.go`. No existing test was edited.
- Docs: `docs/contracts/interfaces.md` (v0.16), `README.md`, `docs/architecture.md`.

## How it was verified

All re-run by the main session on 2026-10-27, after the executor, with `-count=1`.

| DC | Command | Result |
| :--- | :--- | :--- |
| 1 | `go test -v -run TestMixedLaneKey ./internal/telemetry/` | 2 tests pass |
| 2 | `go test -v -run TestMixedLaneKeyOnEveryExit ./internal/httpapi/` | 14 subtests pass (7 exits × 2 arms) |
| 3 | `go test -v -run TestMixedLaneLabelMatchesRule ./internal/httpapi/` | on → `composite`, off → `namespace` |
| 4 | `go test -v -run TestBandFromEnv ./cmd/gateway/` | 18 table rows and the start-up order test pass |
| 5 | grep on `interfaces.md` | v0.16 in header, example, field row, I10–I12, version row |
| 6 | four stale-text greps | all empty; the log line names ADR-016 |
| 7 | `make verify` | exit 0; no FAIL; no SKIPPED target |
| 8 | `git status --porcelain -- '*_test.go'` | 4 lines, all `??` |
| 9 | `go test -v -run 'TestPinnedBands\|TestBandArm' ./internal/reuse/` | 3 tests pass |

Item 4.5's "Done when" was shown in two halves, both by tests: environment → band (DC 4) and band → record
(DC 2, 3). `main` passes `band` to `NewHandler` unchanged (`main.go:341`). No live gateway process was started.

## Numbers

None. No step loaded a model or measured anything. The `v1` counts quoted in README and ADR-016 (12 of 33
stratum-D queries MIXED on the on arm) come from ADR-015's U10 evidence, validation split, not from this task.

## Deferred and follow-ups

- **`plan.md` step 4.6's grep pattern** could never match the version line (`**` sits before "Current"). The
  executor checked the line with a correct grep; the ticked step is left as written.
- **`bandFromEnv`'s doc comment** says `getenvFloat` falls back on an *empty* value; it also falls back on a
  parse error, which is what its example (`0,60`) is. The reason still holds. One-line fix, not made.
- **I11 and I12 are not checked at start**, because `CONFIG_ID` selects nothing yet (F-K). They are checks on a
  finished log, as I8 is. No log reader exists yet (items 5.1, 5.4).
- **`Final_Proposal.md` §9.2 and §9.4** still say two arms and four swept parameters. The author's to edit.
