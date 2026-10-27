# Plan — Name the MIXED arm in every record

Design: design.md (approved 2026-10-27)

No step loads a model, so no memory-pressure check is needed and no step produces a citable number.
Never edit an existing `_test.go` file. New test files only. `go test -run` with a pattern that matches
nothing exits 0, so every test step runs with `-v` and its Pass names the tests that must print `PASS`.

## Phase 1 — Implement

- [x] 1.1 Add the pinned band and its two methods to `reuse`.
  - Files: `gateway/internal/reuse/lane.go`
  - Do: add `const PinnedLo = 0.20` and `const PinnedHiOn = 0.60` with ADR-016 comments; add
    `func (b LaneBand) Pinned() bool` (true for `{PinnedLo, PinnedLo}` and `{PinnedLo, PinnedHiOn}` only, exact
    comparison) and `func (b LaneBand) Arm() string` (`"on"` when `b.Hi > b.Lo`, else `"off"`). Rewrite the
    comment block above `LaneBand` (lines 93–102) to say ADR-016 pins two bands as an on/off arm and neither
    bound is swept; keep the band table (`policy_frac >= Hi -> POLICY` …).
  - Run: `cd gateway && go build ./... && go test ./internal/reuse/`
  - Pass: builds; existing reuse tests pass.
  - Result: added PinnedLo/PinnedHiOn, LaneBand.Pinned() and Arm() and rewrote the band comment in reuse/lane.go; build ok, reuse tests ok

- [x] 1.2 Add the record field.
  - Files: `gateway/internal/telemetry/evallog.go`
  - Do: after `SupportGate`, add `MixedLane string` with tag `json:"mixed_lane"` and **no** `omitempty`, and a
    comment in the style of `SupportGate`'s: the MIXED arm (interfaces.md §H v0.16, ADR-016, item 4.5), on every
    record, a plain string so the package imports nothing from the repository, no `omitempty` because the
    old-log rule keys on presence.
  - Run: `cd gateway && go build ./... && go test ./internal/telemetry/`
  - Pass: builds; existing telemetry tests pass.
  - Result: added Record.MixedLane (`json:"mixed_lane"`, no omitempty) after SupportGate in telemetry/evallog.go; build ok, telemetry tests ok

- [x] 1.3 Write the arm on every record.
  - Files: `gateway/internal/httpapi/handler.go`
  - Do: in the `telemetry.Record` literal (around line 182), directly after `SupportGate: h.SupportGate.String(),`,
    add `MixedLane: h.LaneBand.Arm(),` and extend the comment above it to cover both arms. Rewrite the
    `LaneBand` field comment (lines 107–110) so it no longer says "DEMO values … swept, never hand-set for
    anything reported": the band is one of ADR-016's two, checked at start, and it is the single source for
    both lane decisions and the `mixed_lane` label.
  - Run: `cd gateway && go build ./... && go test ./internal/httpapi/`
  - Pass: builds; existing httpapi tests pass.
  - Result: added `MixedLane: h.LaneBand.Arm()` to the record literal and rewrote the LaneBand comment in httpapi/handler.go; build ok, httpapi tests ok

- [x] 1.4 Read the band once at start and refuse anything else.
  - Files: `gateway/cmd/gateway/main.go`
  - Do: add `func bandFromEnv(lookup func(string) (string, bool)) (reuse.LaneBand, error)` next to
    `gateFromEnv`, with a doc comment in its style. Rules: `LANE_SIGMA` unset → `reuse.PinnedLo`; set → strict
    `strconv.ParseFloat` (set-but-empty, spaces, or junk is an error). `LANE_SIGMA_HI` unset → equal to
    `LANE_SIGMA`; set → the same strict parse. Then the band must satisfy `Pinned()`. Every error names both
    values (`unset` when unset), the two allowed bands and `ADR-016`. In `main`, call
    `band, err := bandFromEnv(os.LookupEnv)` right after the `gateFromEnv` block and `log.Fatalf` on error.
    Delete the two `getenvFloat("LANE_SIGMA…")` lines (keep `getenvFloat` for τ and θ). Split the start-up
    `log.Printf`: τ, θ, dim and index stay "DEMO values, swept later"; the band prints as
    `lane_band=[%.2f,%.2f) mixed_lane=%s (pinned, ADR-016)` using `band.Arm()`. Remove the `mixedLane`
    "ENABLED -- must be pre-registered" text. Rewrite the comment block above the band (lines 205–224): keep
    the dev-v0 2026-09-06 measurement that chose [0.20, 0.60) and the zero-policy-chunk note; drop "The
    operating point belongs to the sweep" and the "DEMO-value status" wording for the band.
  - Run: `cd gateway && go build ./... && go vet ./cmd/gateway/ && go test ./cmd/gateway/`
  - Pass: builds; vet clean; existing cmd/gateway tests pass.
  - Result: added bandFromEnv in cmd/gateway/main.go, called right after gateFromEnv; split the start-up log (band line cites ADR-016) and rewrote the band comment; build, vet and cmd/gateway tests ok

- [x] 1.5 Contract to v0.16.
  - Files: `docs/contracts/interfaces.md`
  - Do, all in one pass:
    - Line 3: `Draft v0.15` → `Draft v0.16`, `Revised: 2026-10-22` → `Revised: 2026-10-27`.
    - §H example record: after the `support_gate` line add
      `"mixed_lane": "off",                   // v0.16 — on|off, on EVERY record; the MIXED arm this gateway process ran (ADR-016)`.
    - §H field table: a `mixed_lane` row right after `support_gate`. It says: v0.16 (ADR-016, item 4.5); `"on"`
      or `"off"` on every record, never null, no `omitempty`; derived from the same `LaneBand` the lane rule
      reads, so label and behaviour cannot differ; `on` = [0.20, 0.60) (`LANE_SIGMA_HI=0.60`), `off` = the
      closed band at 0.20 (the default); any other band, an empty or unparseable value stops the process at
      start; constant across a run; **a configuration-4 run is identified by `(config_id, mutation,
      support_gate, mixed_lane)`**; reading an old log: no key ⇒ read as `off` (ADR-016), and a record with
      `reuse_rule == "composite"` disproves that.
    - §H invariants, after I9: **I10 (v0.16), the MIXED arm**: `mixed_lane ∈ {"on","off"}` on every record,
      constant across the run; `mixed_lane == "off"` ⇒ no record has `reuse_rule == "composite"`.
      **I11 (v0.16)**: `config_id == 5` ⇒ `mixed_lane == "on"`. **I12 (v0.16)**: `config_id == 4 ∧
      support_gate == "off"` ⇒ `mixed_lane == "off"` (ADR-016's three arms). Add after I12 one sentence:
      like I8, I11 and I12 are checks on a finished log, because `CONFIG_ID` selects no behaviour yet (F-K).
    - *Offline reading rules*: the last sentence becomes "… are reported **per arm** — per support-gate arm
      and, since v0.16, per MIXED arm — never pooled."
    - *Joins name their arm*: add "Since v0.16 configuration 4 has three arms (ADR-016): gate off and MIXED
      off, gate on and MIXED off, gate on and MIXED on. A join names both arms."
    - Versioning: `Current version: v0.15** (2026-10-22)` → `v0.16** (2026-10-27)`; a new top row
      `| **v0.16** | 2026-10-27 | …`: the MIXED lane is an on/off arm (ADR-016, item 4.5); §H gains one
      required key `mixed_lane`, invariants I10–I12, and the run identity grows by the MIXED arm; a band other
      than ADR-016's two stops the gateway at start; no wire shape, §A, §B, §D or `.proto` change; a log
      without the key reads as off. Keep the row's style and length near v0.14's.
  - Run: `grep -n "mixed_lane\|v0.16\|I10\|I11\|I12" docs/contracts/interfaces.md`
  - Pass: the version line, the example, the field row, I10–I12 and the version row all appear.
  - Result: interfaces.md to v0.16 (header, example, field row, I10-I12, per-arm and joins sentences, version row); grep shows all eight places

- [x] 1.6 README.
  - Files: `README.md`
  - Do: replace the bullet that starts `- **The MIXED lane is off.**` (lines 176–179) with: the MIXED lane is an
    on/off arm (ADR-016): on is the band [0.20, 0.60) (`LANE_SIGMA_HI=0.60`), off is the closed default; any
    other band stops the gateway at start; every evaluation record names the arm in `mixed_lane`; on the `v1`
    validation split the on arm reads 12 of 33 stratum-D queries as MIXED, and the off arm reads 27 as POLICY
    and 6 as SPEC.
  - Run: `grep -n "Item 4.0 chooses\|mixed_lane" README.md`
  - Pass: no `Item 4.0 chooses`; one `mixed_lane` line.
  - Result: README.md bullet now says the MIXED lane is an on/off arm (ADR-016) named in `mixed_lane`; grep shows no `Item 4.0 chooses` and one `mixed_lane` line

- [x] 1.7 Architecture.
  - Files: `docs/architecture.md`
  - Do: on line 48, add `bandFromEnv` beside `gateFromEnv` in the list of `cmd/gateway`'s env rules. Nothing else.
  - Run: `grep -n "bandFromEnv" docs/architecture.md`
  - Pass: one line.
  - Result: architecture.md line 49 now lists bandFromEnv beside gateFromEnv; grep shows one line

## Phase 2 — Unit tests

- [x] 2.1 `reuse`: the pinned bands (DC 9).
  - Files: `gateway/internal/reuse/lane_band_test.go` (new)
  - Do: `TestPinnedBands`: `Pinned()` true for `{0.20,0.20}` and `{0.20,0.60}`; false for `{0.20,0.70}`,
    `{0.30,0.30}`, `{0.20,0.10}`, `{0,0}`, `{0.20,0.6000001}`. `TestBandArm`: `{0.20,0.20}` and `{0,0}` → `"off"`,
    `{0.20,0.60}` → `"on"`. `TestPinnedBandsClassifyMixedGrounding`: for the grounding
    `[product-kettle-01#chunk-0, policy-returns-01#chunk-0, product-kettle-01#chunk-1]`, `Classify` gives
    `LaneMixed` under `{PinnedLo, PinnedHiOn}` and `LanePolicy` under `{PinnedLo, PinnedLo}`, and each band's
    `Arm()` is `"on"` and `"off"` respectively.
  - Run: `cd gateway && go test -count=1 -v -run 'TestPinnedBands|TestBandArm' ./internal/reuse/`
  - Pass: `TestPinnedBands`, `TestBandArm` and `TestPinnedBandsClassifyMixedGrounding` each print `--- PASS`.
  - Result: added reuse/lane_band_test.go; TestPinnedBands (8 rows), TestBandArm (3 rows) and TestPinnedBandsClassifyMixedGrounding all print `--- PASS`

- [x] 2.2 `telemetry`: the key is always written (DC 1).
  - Files: `gateway/internal/telemetry/mixed_lane_field_test.go` (new)
  - Do: mirror `support_gate_field_test.go`, using `logOne` from `cause_fields_test.go`.
    `TestMixedLaneKeyIsAlwaysWritten`: a zero `Record` writes the key with `""`; `"on"` and `"off"` are written
    as given and appear in the raw line as `"mixed_lane":"on"` / `"off"`. `TestMixedLaneKeyIsNeverNull`: a
    Tier-1 record with `MixedLane: "off"` has a non-null string.
  - Run: `cd gateway && go test -count=1 -v -run 'TestMixedLaneKey' ./internal/telemetry/`
  - Pass: both tests print `--- PASS`.
  - Result: added telemetry/mixed_lane_field_test.go; TestMixedLaneKeyIsAlwaysWritten and TestMixedLaneKeyIsNeverNull print `--- PASS`

- [x] 2.3 `cmd/gateway`: the start-up check (DC 4).
  - Files: `gateway/cmd/gateway/lane_env_test.go` (new)
  - Do: `TestBandFromEnv`, a table over a fake `lookup` built from a map (absent key = unset):
    unset/unset → off; `LANE_SIGMA=0.20` + `LANE_SIGMA_HI=0.20` → off; `LANE_SIGMA=0.20` only → off;
    `LANE_SIGMA_HI=0.20` only → off; `LANE_SIGMA_HI=0.60` → on; `0.20` + `0.60` → on; `LANE_SIGMA_HI=0.6` → on.
    Errors: `LANE_SIGMA_HI=0.70`; `LANE_SIGMA=0.30`; `LANE_SIGMA=0.60` with `LANE_SIGMA_HI` unset;
    `LANE_SIGMA_HI=0.10`; `LANE_SIGMA_HI=abc`; `LANE_SIGMA_HI=` (set, empty); `LANE_SIGMA=` (set, empty);
    `LANE_SIGMA_HI=" 0.60"`. For each accepted row check the band and `band.Arm()`; for each error row check the
    error is non-nil and its text contains `ADR-016` and the offending value.
    `TestBandFromEnvRunsBeforeSideEffects`: read `main.go`, drop lines whose trimmed text starts with `//`,
    and check the first index of `bandFromEnv(os.LookupEnv)` is after `gateFromEnv(os.LookupEnv)` and before
    each of `redis.NewClient(`, `ragclient.New(` and `telemetry.Open(`; fail if any needle is missing.
  - Run: `cd gateway && go test -count=1 -v -run 'TestBandFromEnv' ./cmd/gateway/`
  - Pass: `TestBandFromEnv` (every subtest) and `TestBandFromEnvRunsBeforeSideEffects` print `--- PASS`.
  - Result: added cmd/gateway/lane_env_test.go; TestBandFromEnv (8 accepted + 10 refused rows) and TestBandFromEnvRunsBeforeSideEffects print `--- PASS`

## Phase 3 — Integration tests

- [x] 3.1 `httpapi`: the arm on every exit path (DC 2).
  - Files: `gateway/internal/httpapi/mixed_lane_test.go` (new)
  - Do: `TestMixedLaneKeyOnEveryExit`. Copy the seven-case table of `TestSupportGateKeyOnEveryExit`
    (`support_gate_test.go:397`) into the new file — copy, do not edit the original. Loop over two arms:
    `"off"` → `reuse.LaneBand{Lo: reuse.PinnedLo, Hi: reuse.PinnedLo}`, `"on"` →
    `{Lo: reuse.PinnedLo, Hi: reuse.PinnedHiOn}`. In each subtest set `hs.h.LaneBand` right after `newHarness`,
    before the case runs. Assert `rec.str("cache", c.wantCache)` and `rec.str("mixed_lane", arm)`.
  - Run: `cd gateway && go test -count=1 -v -run 'TestMixedLaneKeyOnEveryExit' ./internal/httpapi/`
  - Pass: 14 subtests (7 exits × 2 arms) each print `--- PASS`, including `TIER1_HIT`, `TIER2_HIT`, `MISS` and
    `SHED` on both arms.
  - Result: added httpapi/mixed_lane_test.go with TestMixedLaneKeyOnEveryExit; all 14 subtests (7 exits x 2 arms) print `--- PASS`

- [x] 3.2 `httpapi`: label and behaviour agree (DC 3).
  - Files: `gateway/internal/httpapi/mixed_lane_test.go`
  - Do: `TestMixedLaneLabelMatchesRule`, two subtests (`on`, `off`), each with its own `newHarness(t, 1, 0)`.
    In the new file define a small gRPC fake `mixedRAG` (embed `ragpb.UnimplementedRagServiceServer`):
    `Retrieve` returns chunk IDs `[product-kettle-01#chunk-0, policy-returns-01#chunk-0,
    product-kettle-01#chunk-1]`, scores `[0.9, 0.8, 0.7]`, `DatasetEpoch: testEpoch`, and aligned `Texts`
    (`kettle.texts[0]`, `"Unopened items may be returned within the return window."`, `kettle.texts[1]`).
    `Answer` streams one chunk with `kettle.answer` and the same source IDs; mirror the field use of
    `fakeRAG.Answer` (`harness_test.go:528`). Serve it on `127.0.0.1:0`, build `ragclient.New(addr)`, set
    `hs.h.RAG` to that client, and register a `t.Cleanup` that closes the client and stops the server.
    Seed with `hs.store.seedTier2`, both at `float32s(basis(1))`: a MIXED entry (`Lane: "MIXED"`, `Namespace:
    "product-kettle-01|policy-returns-01"`) and a POLICY entry (`Lane: "POLICY"`, `Namespace:
    "policy-returns-01"`), each with `Answer: kettle.answer`, the three chunk IDs as sources, a fresh
    `EntryID`, `DatasetEpoch: testEpoch` and a `T1Key`. Set `hs.h.LaneBand` for the arm, ask with
    `hs.askNear(t, "Can I return the Aurora kettle, and what is its body made of?", 1, hitCos, kettle)`, then
    `hs.records(t)`. On: `mixed_lane` `"on"`, `reuse_rule` `"composite"`, and `hs.store.namespacesSearched()`
    equals `["product-kettle-01|policy-returns-01"]`. Off: `"off"`, `"namespace"`, and `["policy-returns-01"]`.
  - Run: `cd gateway && go test -count=1 -v -run 'TestMixedLaneLabelMatchesRule' ./internal/httpapi/`
  - Pass: both subtests print `--- PASS`. If they fail because the routing differs from design §3, stop and
    report: that is a design question, not a test to adjust.
  - Result: added mixedRAG fake and TestMixedLaneLabelMatchesRule; `on` and `off` print `--- PASS`, routing as design §3 (on: composite, pair namespace; off: namespace, policy namespace)

## Phase 4 — Run and verify

- [x] 4.1 `make verify`
  - Pass: no FAIL; any SKIPPED target listed by name.
  - Result: exit 0 (run twice); go vet, ruff, build, all go packages ok, 23 pytest and 731 tests pass; no FAIL, no SKIPPED
- [x] 4.2 DC 1 — `cd gateway && go test -count=1 -v -run 'TestMixedLaneKey' ./internal/telemetry/ && go test ./internal/telemetry/`
  - Pass: both new tests `--- PASS`; package `ok`.
  - Result: TestMixedLaneKeyIsAlwaysWritten and TestMixedLaneKeyIsNeverNull `--- PASS`; telemetry package ok
- [x] 4.3 DC 2 — `cd gateway && go test -count=1 -v -run 'TestMixedLaneKeyOnEveryExit' ./internal/httpapi/ && go test ./internal/httpapi/`
  - Pass: 14 subtests `--- PASS`; package `ok`.
  - Result: 14 subtests (7 exits x off/on) `--- PASS`; httpapi package ok
- [x] 4.4 DC 3 — `cd gateway && go test -count=1 -v -run 'TestMixedLaneLabelMatchesRule' ./internal/httpapi/`
  - Pass: `on` and `off` `--- PASS`.
  - Result: `on` (composite, pair namespace) and `off` (namespace, policy namespace) `--- PASS`
- [x] 4.5 DC 4 — `cd gateway && go test -count=1 -v -run 'TestBandFromEnv' ./cmd/gateway/ && go test ./cmd/gateway/`
  - Pass: both tests and every table row `--- PASS`; package `ok`.
  - Result: TestBandFromEnv (18 rows) and TestBandFromEnvRunsBeforeSideEffects `--- PASS`; cmd/gateway package ok
- [x] 4.6 DC 5 — `grep -n "Current version: \*\*v0.16\|Draft v0.16\|\"mixed_lane\"\|I10 (v0.16)\|I11 (v0.16)\|I12 (v0.16)\|| \*\*v0.16\*\*" docs/contracts/interfaces.md`
  - Pass: the version line, header, example, I10, I11, I12 and the version row each appear; the field row and the
    old-log rule are present on reading the `mixed_lane` row.
  - Result: header (l.3), example (l.583), I10-I12 (l.685-687) and version row (l.711) match; the plan's `Current version: \*\*v0.16` pattern cannot match `**Current version: v0.16**`, so I grepped `Current version: v0.16` (l.707); the field row (l.666) holds the old-log rule
- [x] 4.7 DC 6 — each prints nothing:
  `grep -n "Both bounds are swept" gateway/internal/reuse/lane.go`;
  `grep -n "operating point belongs to the sweep" gateway/cmd/gateway/main.go`;
  `grep -n "Item 4.0 chooses" README.md`;
  `grep -n "swept, never hand-set for anything reported" gateway/internal/httpapi/handler.go`;
  and `grep -n "lane_band" gateway/cmd/gateway/main.go` shows the band printed with `ADR-016`, not "DEMO".
  - Pass: four empty outputs; the log line names ADR-016.
  - Result: all four greps print nothing; main.go:280 prints `lane_band=[..) mixed_lane=%s (pinned, ADR-016)`
- [x] 4.8 `make verify` passed in 4.1 (DC 7). Record the SKIPPED names, if any.
  - Result: passed in 4.1 (exit 0, run twice); no SKIPPED target
- [x] 4.9 DC 8 — `git status --porcelain -- '*_test.go'`
  - Pass: every line starts with `??` or `A ` (new files); no line starts with ` M`, `M`, ` D` or `D`.
  - Result: four lines, all `??` (lane_env_test.go, mixed_lane_test.go, lane_band_test.go, mixed_lane_field_test.go); no `M` or `D`
- [x] 4.10 DC 9 — `cd gateway && go test -count=1 -v -run 'TestPinnedBands|TestBandArm' ./internal/reuse/ && go test ./internal/reuse/`
  - Pass: the three new tests `--- PASS`; package `ok`.
  - Result: TestPinnedBands, TestBandArm and TestPinnedBandsClassifyMixedGrounding `--- PASS`; reuse package ok
