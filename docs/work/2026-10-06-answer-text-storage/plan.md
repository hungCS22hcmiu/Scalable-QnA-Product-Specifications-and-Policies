# Plan — answer-text-storage

**Scope L.** Nothing below starts until `/approve implementation`. Each step is independently
verifiable, and a step that adds a test writes it **first** and shows it **fail by assertion**
against the code before the step's change (the new API is stubbed to a no-op first, so a red test is
an assertion failure and not a compile error). No existing test is edited (`spec.md` question 8).
Commands run from the repository root; use `$CLAUDE_JOB_DIR/tmp` for scratch, not `/tmp`.

Authority: `spec.md` rev 3 (acceptance numbers), `design.md` rev 3, `review.md` (finding numbers).

- [x] **1. Contract text, first.** The text is **already drafted** in `contract-draft.md` (written
  2026-10-06 for `/approve contract`): `interfaces.md` **v0.11** (A1–A9) and **ADR-005** (B1–B2).
  Apply it **verbatim** to `docs/contracts/interfaces.md` and `docs/decisions.md`; do not re-draft.
  Two `⟦PENDING⟧` markers stay in ADR-005 (the drain-rate numbers, the Spotlight call); step 9 closes
  them.
  *Verify:* the contract-reviewer subagent reads v0.11 against `design.md` and finds no
  disagreement; `git diff --exit-code contracts/` clean (the `.proto` does not move).
  **Done:** applied verbatim by `$CLAUDE_JOB_DIR/tmp/apply_contract.py`; `contract-reviewer` found two MUST-FIX wording defects and eight SHOULD-FIX, corrected before commit and recorded in `approvals.md`; `git diff --exit-code contracts/` clean.

- [x] **2. `telemetry`: stubs and red tests.** Add `Record.SetAnswer`, the three nil-safe accessors,
  and `storeAnswer` as **no-ops**, plus the `linkFile` and `remove` seams. New file
  `gateway/internal/telemetry/answers_test.go` with every test of `design.md` §5 (byte-exact table,
  dedupe at the seam, order with the vacuity check, failed `Link` then retry, `Link`-ok/`Remove`-fail,
  real `chmod` after `Close`, empty text, guard + never-cleared, write-once with sentinel bytes,
  `Open` fixtures 9b, D3 with a NaN `*float64`, nil-safety and after-`Close`, a reader of
  `AnswersMissing` concurrent with `Log`). The oracle hash is `crypto/sha256`, never the package
  helper. *Verify:* every new test **fails by assertion**; the existing telemetry tests still pass.
  **Done:** 13 of 18 new telemetry tests failed by assertion against the stubs; the 5 that passed are pins (nil-safety, after-`Close`, `Open` fixture A, no-answer-no-file, concurrent accessors).

- [x] **3. `telemetry`: implement.** `Open` in the order of `design.md` §2 (`O_EXCL` first, leaf
  `Mkdir`, remove only what it made); `SetAnswer`; `storeAnswer` steps 1–5 (`seen`, guard +
  `guardRefusals`, `CreateTemp` + write + `Chmod` + checked `Close`, `link` classification by
  `fs.ErrExist`, `Remove` failure logged and not missing); `missing` under a mutex; `writeErrs`
  atomic; `sha256Hex` moves here. *Verify:* `go test -count=1 ./internal/telemetry/` green.
  **Done:** `go test -count=1 -race ./internal/telemetry/` green.

- [x] **4. `httpapi`: the exit test, red, then the call sites.** New file
  `gateway/internal/httpapi/answerstore_test.go` (acceptance 1–3), using the 1.2 harness without
  editing it: **three distinct texts**, one per serving path (Tier-1 entry seeded with its own text;
  Tier-2 `hitFixture` with `Answer` overridden to a third; MISS from `p.answer`), plus a coalesced
  follower and a repeated answer; reads only `raw/`; the invariant both ways; `GuardRefusals()==0`;
  bytes equal the JSON-decoded `answer` on `touched && Code==200`; `""` records create no file.
  *Verify red:* against HEAD's three `rec.AnswerSHA256 = sha256Hex(...)` lines it fails (no files).
  Then change the three sites (`handler.go:207`, `:308`, `:524`) to `rec.SetAnswer(...)` and delete
  `sha256Hex` and its imports. *Verify:* green; `go build ./...` clean (the `harness_test.go` helper
  that recomputes `sha256` uses its own `crypto/sha256`, so nothing else breaks).
  **Done:** red against HEAD's three call sites (guard refused all three; no files), green after; the whole existing `httpapi` suite still green.

- [x] **5. `main`: `incomplete` and its call site.** `runCounts` struct and `incomplete` in
  `gateway/cmd/gateway/main.go`; table test in `main_test.go` (new test, existing untouched): each
  field alone, each pair, none, and the `Dropped` row. Build `runCounts` **after `evalLog.Close()`**
  at the existing `Dropped()` site, include `CloseErr` and `GuardRefusals`, keep the `log.Fatalf`;
  update the log line at `:208`. *Verify:* `go test ./cmd/gateway/`; the call site is read, not
  assumed, to come after `Close`.
  **Done:** `runCounts` / `incomplete` (table-tested) and the call site after `Close`; `go test ./cmd/gateway/` green; M17 and M18 prove the table can fail.

- [x] **6. Mutations.** A script in `docs/work/2026-10-06-answer-text-storage/evidence/` applies each
  of `design.md` §5's M1–M16 to a fresh **copy** of `gateway/` (never the working tree) and runs the
  existing suite and the new tests. Expected: every mutation passes the existing suite, **and each is
  caught by its named new test, by assertion and not by a build error.** M1 and M3 are the ones the
  first design could not catch: confirm they are caught by the exit test's distinct texts and by the
  never-cleared guard counter respectively. *Verify:* `evidence/mutations.md`, every row caught,
  none by a build error; a row that is not caught is a defect in the test, fixed before step 7.
  **Done:** `evidence/mutations.md`: M1-M18 all caught by a new test, none by a build error; the existing suite passes under every one; M1 and M3 are caught only by the exit test's distinct texts.

- [x] **7. Race and drain rate.** `go test -race -count=1 ./internal/telemetry/ ./internal/httpapi/`,
  result recorded. Then the **drain-rate measurement** (`design.md` §4): the writer's drain time per
  first-seen record against already-seen records as the control, the derived sustainable
  first-sighting rate, and the real bound (first sightings ≤ `0.25·K` plus MISSes at the measured hit
  rate; K is not frozen, so state the bound as a function of K and give one worked value). *Verify:*
  both numbers in `evidence/drain-rate.md`. **Recorded, not asserted.**
  **Done:** `evidence/drain-rate.md`: first sighting ≈ 440 µs, already-seen ≈ 0; `-race` ok on three packages.

- [x] **8. Docs that follow the code.** `docs/architecture.md`: the `raw/` tree lists
  `requests.jsonl` and `answers/`, and telemetry's "Owns" cell (`:106`) names the answer store.
  `experiments/README.md:7`. `docs/data-card.md` §1: a row for run outputs and their licence
  posture. `docs/super-plan.md`: item 1.5 marked done (clause count 5 of 6), and the 5.1 wording
  flagged (not edited). **Only with the author's OK:** the stale `v0.9` strings (`CLAUDE.md:106`,
  `.claude/agents/contract-reviewer.md:11`, `architecture.md:30`). *Verify:* the named greps of
  acceptance 11, including `grep -L` printing nothing.
  **Done:** architecture tree + telemetry cell, `experiments/README.md`, `data-card.md` row, `.gitignore`, `super-plan.md` 5.4 and the Phase 5 Exit line. **Not done, awaiting the author's OK:** the stale `v0.9` strings (`CLAUDE.md:106`, `contract-reviewer.md:11`, `architecture.md:30`). 1.5's status line in `super-plan.md` is written at `/done`.

- [x] **9. Close the ADR.** Fill ADR-005's placeholders: the publication posture the author chose,
  the Spotlight precondition if the author made it one, the step-7 numbers. Record the experiment
  phase in `approvals.md`: no §H key, span or counting rule changed; the new INCOMPLETE conditions;
  the drain-rate result. *Verify:* `grep -c '⟦PENDING' docs/decisions.md` prints 0. **That does not mean nothing is open:** ADR-005
  also flags, in prose and not as a marker, 5.1's verdict key and delimiter, U8, the SOURCE text under
  `mutation: on`, and the raw archive design for 5.4. They live in `approvals.md`.
  **Done:** experiment record filled; ADR-005 has **one** `⟦PENDING⟧` left, the Spotlight call, which is the author's.

- [x] **10. Verify, review, close.** `/verify`. **Report the proto-drift row honestly:** both stub
  directories are gitignored, so `git diff` on them is vacuously clean; use
  `git diff --exit-code contracts/` and say so. `/ai-review`; apply what survives. `/done`. Commit
  with the attribution line; **do not push** unless asked.

## Outcome

**Shipped (2026-10-06).** The gateway writes the text behind every non-empty `answer_sha256` to
`raw/answers/{sha}.txt`, content-addressed, byte-exact, written by the logger's own writer before the
line that names it, and a run is INCOMPLETE if a named hash has no file, a line failed to encode or
write, an answer and its hash disagree, or the log failed to close.
- **Code:** `telemetry/evallog.go` (`SetAnswer`, `storeAnswer`, `Open`'s three-step create, three
  nil-safe accessors, three seams), `httpapi/handler.go` (three `SetAnswer` sites; `sha256Hex` moved),
  `cmd/gateway/main.go` (`runCounts`, `incomplete`, `finishRun`, the post-`Close` call site).
- **Contract:** `interfaces.md` **v0.11** (§H "The answer store", rules 1-9) and **ADR-005**;
  `.proto`, §A-§G and every JSON key unchanged (`git diff --exit-code contracts/` clean).
- **Tests, all new files (no existing test edited):** `telemetry/answers_test.go` (19, plus `answers_drain_test.go`, a skipped measurement),
  `httpapi/answerstore_test.go` (2, the exit test with three distinct texts and the
  abandoned-but-MISS path), `cmd/gateway/incomplete_test.go` and `finish_test.go`.
- **Evidence:** `evidence/mutations.md` (**25 of 25** mutations caught by a new test, none by a build
  error; the existing suite passes under 23 of them), `evidence/drain-rate.md` (first sighting
  ≈ 440 µs, already-seen ≈ 0; sustainable ≈ 2,250 first sightings/s), `go test -race` on three
  packages.
- **Repo changes beyond the code:** `.gitignore` ignores `experiments/results/*/raw/` (the author's
  decision); `super-plan.md` 5.4's *Done when* and Phase 5's Exit reworded to "plus the raw archive";
  `architecture.md`, `experiments/README.md`, `data-card.md` updated.
- **Verified:** `make verify` exit 0 (gofmt, vet, build, Go tests, ruff, pytest 15 + 94); `-race` ok.
  **Nothing SKIPPED.** *Caveat on the "proto drift" row:* it checks nothing (the stubs are gitignored);
  `git diff --exit-code contracts/` is what ran, and it is not a stub-drift check.
- **Scope held:** L was right. It changed a frozen document (§H) and added a run-admissibility rule.
  Nothing touched `reuse/`, a `.proto`, or a frozen experimental value.

**Review.** The design review (opus) fixed the exit test's power (distinct texts per path), the
burst-test posing, the `Link`/`Remove` error classification and the seams. The contract review
corrected wording that overstated the order guarantee and the "no unnamed file" rule. The
implementation review closed two surviving mutations (the failed-write branch; `main`'s order of
`Close` and reading the counters) and one flaky test. No MUST-FIX in the implementation review.

**Deferred, with the author** (all in `approvals.md` and `super-plan.md` "Found while closing 1.5"):
the Spotlight precondition (ADR-005 keeps **one** `⟦PENDING⟧` for it); 5.1's verdict key and wording;
U8 (temperature 1: does it gate 1.5? Claude's reading is no); the stale `v0.9` strings; whether to add
`-race` to `make test`; the shared helper `checkEveryRecord` (left untouched).
**Follow-ups worth a task:** F-M (`main` exits 0 on a bind failure), F-F (wait for `Shutdown` before
`Close`), a verifier script for a finished run's `raw/`, and fixing `/verify`'s proto-drift row.
**Not verified live:** the store against a real gateway run with Redis, Ollama and k6. The unit and
exit tests use the real `Logger` over fakes; item 1.6's first run is the first real exercise.

## What would make me stop and ask
- A mutation that no test catches after one fix to the test.
- The step-7 drain rate showing the writer cannot keep up with the **bound** (not with a synthetic
  burst): that changes the design (the `answers.jsonl` alternative, or a bigger buffer, which is a
  measured-path change) and goes to the author.
- `os.Link` failing on the results filesystem.
- Any need to edit an existing test.
