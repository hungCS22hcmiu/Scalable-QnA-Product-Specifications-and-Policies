# Plan — numeric arm (item 2.2)

Do nothing here until `/approve implementation`. Smallest change that meets `spec.md`. Each step
can be checked alone. Rules R1–R9 and decisions D1–D3 are in `design.md` (revision 2).

Files this plan may touch: `reuse/support_numeric.go` (new), `reuse/support_numeric_test.go`
(new), `reuse/doc.go`, `docs/decisions.md`, `docs/super-plan.md`, `docs/architecture.md`,
this trail. **Not** `support.go`, `support_test.go`, `cascade.go`, `telemetry/`, `interfaces.md`,
the live test, the Makefile.

- [x] **1. Record the definition first.** Copy R1–R9 and the unit list, as approved, into
  `approvals.md` ("Frozen artefact"). Check: the file has the final list and the D1–D3 answers
  *before* any test below runs (condition (a) of `impact.md` §6).
- [x] **2. Skeleton.** `support_numeric.go`: `NumericVerdict`, `Refuses`, `Admits`,
  `SupportNumeric` returning the stale-server case only. Doc comments say: decide with
  `Refuses()`/`Admits()`, never the counts; no threshold; not wired. Check: `go build ./...`.
- [x] **3. Reader.** Numbers, units, codes, number words, unreadable (R1–R7). Unexported, own
  tokenizer. Tests, written first:
  - `TestNumericNormalisation`: `50`≠`5`, `100`≠`1`, `0`, `0.5`, `5.30`=`5.3`, `1,500`=`1500`.
  - `TestNumericReaderGolden`: the exact (value, unit) / code list for the pinned fixture strings
    plus one hard-case string, with its sha256 pinned (like the stopword list). New authored
    strings get their own checksum test in the new file (`TestNumericFixtureChecksums`).
  - `TestNumericUnicodeNumbers`: `½`, `²`, `٣` are unreadable (pins U4).
  Check: `go test ./internal/reuse -run Numeric`.
- [x] **4. Matcher and verdict.** Per-chunk match (R8, R9). Tests:
  - done-when: `TestNumericDoneWhen` ("30-day" vs "14-day" refuses) and
    `TestNumericUnreadableBlocks` (`1,5`, `½` refuse);
  - `TestNumericMeasuredPair`: the four fixture rows in `design.md`. If one differs, record it as
    a finding. Do not change the fixture;
  - `TestNumericSeparatesGrammarEdits`: every "refuse"/"admit" row of the `design.md` table that
    is not decided by "is 30 present" (unit check, per chunk, hyphen, plural, decimals, code,
    number words, `Unitless` gap);
  - `TestNumericStaleServerAndEmptyRetrieval`: nil texts + chunk IDs → not scored; empty retrieval → scored, no
    special case.
- [x] **5. Pin the vocabulary.** `TestNumericUnitListPinned` (the exact list and aliases),
  `TestNumericNumberWordsPinned`. Check: changing one entry turns a test red.
- [x] **6. Benchmark.** `BenchmarkSupportNumeric` on the pinned strings. Record ns/op in
  `approvals.md`. Compare with `SupportLexical` (about 16 µs). Not a measurement of the system.
- [x] **7. Hand mutation check.** Apply each edit below to `support_numeric.go`, run
  `go test ./internal/reuse`, confirm RED, undo. Record the list in `approvals.md`. Edits: drop the
  unit check · join chunks · drop the hyphen rule · drop plural stripping · trim zeros on integers
  · split decimals · ignore codes · treat `vs` as plural · accept unreadable spans in the answer.
  If any stays green, add a row and repeat.
- [x] **8. Docs.** One line in `reuse/doc.go`. One row in `decisions.md`'s frozen table, with the
  condition "any edit after the first logged run needs a numbered ADR with `Invalidates:`" (or an
  ADR, if D3 says so). `super-plan.md`: item 2.2 done with a short note, row 2.3 "rests on" 2.2,
  row 2.4 "Unblocked when" `2.2 ✅`, update the progress line. `architecture.md`: lines 50 and
  203. Check: `grep -n "2.2" docs/super-plan.md` reads consistently.
- [x] **9. Verify and close.** `make verify` exit 0 (not cached: also `go test -count=1 ./...`).
  `gofmt -l gateway/` empty. `TestNoThetaSeparatesTheMeasuredPair` and all item 2.1 tests pass
  unchanged. Then `/ai-review`, `/done`.

## Do not

- Add a threshold, a window, or any field to `Thresholds`.
- Call `eachToken`, `contentTokens` or `textTokens`.
- Change a fixture to make a row pass.
- Wire the arm into the cascade.

## Implementation notes (2026-10-14)

- **Step 1 came first.** The definition was written to `approvals.md` before any code existed. It
  lists five small clarifications to `design.md` (space in a compound number word, `%` after
  spaces, ordinals are codes, leading-point number is unreadable, `litre` is a unit).
- **Tests came before the code.** Every expected value was worked out by hand. On the first run all
  13 test functions passed, including the four measured-pair rows. No row and no fixture was changed.
- **Benchmark (step 6).** `BenchmarkSupportNumeric` about 14.5 µs/op, 7976 B/op, 96 allocs (three
  runs: 14.7, 14.2, 14.7 µs; M1). `BenchmarkSupportLexical` in the same run: about 14.0 µs/op.
  Not a measurement of the system.
- **Mutation check (step 7).** 23 edits applied one at a time to a copy of the package in the
  scratchpad (the real source was never edited): drop the unit check · join chunks · drop the
  hyphen rule · drop plural stripping · trim integer zeros · split decimals · ignore codes · `vs` as
  a plural · ignore an unreadable number · compound only with a hyphen · no list-marker rule ·
  number words read without a unit · glued non-unit read as a number · no currency prefix · ignore
  non-ASCII numbers · no stale-server check · `Refuses` ignores `Unreadable` · no leading-point rule
  · blocked words pass · `%` not a unit · `Unitless` never counted · codes case-sensitive · every
  unit word counts as a chunk unit. **23 red, 0 survived.**
- **Step 9.** `make verify` exit 0. `go test -count=1 ./...` all ok. `gofmt -l gateway/` empty.
  `TestNoThetaSeparatesTheMeasuredPair` and all item 2.1 tests pass unchanged. Proto drift was not
  re-run: no `.proto` or generated file was touched.
- **Files changed:** `reuse/support_numeric.go` and `reuse/support_numeric_test.go` (new),
  `reuse/doc.go`, `decisions.md` (one row), `super-plan.md` (rows 2.2–2.4, progress line),
  `architecture.md` (two lines), this trail. Nothing else.
- **After `/ai-review` (same day).** See `review.md`, "Code review". Fixed: a digit-first code lost
  its `.digits` tail (`12x1.5mm`); rows added for every rule the reviewer showed was unpinned;
  one weak row split in two; `FuzzReadNumbers` added (seeds run in `go test`). The mutation script
  is kept in the trail as `mutation-check.py` and has **41 edits: 41 red, 0 survivors** (35 before the separator change below). The
  "23" above is the count before the review.
- **Separator change (same day, at the author's request).** Review finding 4 was fixed instead of
  accepted: no-break space and narrow no-break space count as spaces, `U+2011` as a hyphen, and the
  compound separator is a run of spaces. Definition amended in `approvals.md` ("Separators") before
  any run logged the field. 13 rows added, 6 mutation edits added, fuzz 3.7 M inputs clean.
- **Still to do:** `/done`.

## Outcome (2026-10-14, `/done`)

**Shipped.**
- `reuse/support_numeric.go`: `SupportNumeric`, `NumericVerdict` (`Refuses`, `Admits`). Unwired.
- `reuse/support_numeric_test.go`: 13 test functions, a fuzz test, a benchmark.
- `mutation-check.py` in this trail: 41 edits, all red.
- Docs: `doc.go`, one row in `decisions.md`, rows 2.2–2.4 and the progress line in `super-plan.md`,
  two lines in `architecture.md`.
- Done-when tests: `TestNumericDoneWhen` and `TestNumericUnreadableBlocks`, both run and passing.

**Verification at close.** `make verify` exit 0 (lint, vet, build, Go tests, Python tests). `go test
-count=1 ./...` all ok. `gofmt -l gateway/` empty. Item 2.1's tests and
`TestNoThetaSeparatesTheMeasuredPair` pass unchanged. **Not run:** proto drift (`make proto` +
`git diff`), because no `.proto` or generated file was touched; it was clean at the start of the day.
`make support-check` was not run: the live test is untouched and the arm has no live path.

**Scope was honest.** Opened at L because it adds code to `reuse/` and creates a frozen definition.
Nothing turned out larger than that.

**Frozen value or contract?** A new frozen definition: the numeric-arm row in `decisions.md`, full
text in `approvals.md` ("Frozen artefact" and "Separators"). `interfaces.md` was **not** changed, so
no version bump. **Prior runs invalidated: none.** No run exists (`experiments/results/` holds only
`.gitkeep`). From the first logged `support_numeric_ok`, any edit needs a numbered ADR with an
`Invalidates:` line.

**Deferred, with where it is recorded.**
- Wiring, cause code, on/off switch: items 2.3 and 2.4. 2.3 also needs a "not scored" value in §H
  (contract phase) and the experiment phase, and must close the zero-chunk hole in the cascade.
- The real-answer sample (10–20 answers) now covers both arms: counts of number words, list markers,
  codes, `Unitless`, `Unreadable`. Needs Ollama in green pressure. Do it before 2.3.
- The unit list is draft until the Phase 3 corpus freeze; check it against v1 text, and check the
  known gaps (other Unicode spaces and dashes, a no-break space after a list marker).
- The Phase 2 exit line says "both arms are independently switchable". Row 2.4 means the whole gate
  on/off. Fix the wording when 2.4 opens.

**Phase 2 exit line, run clause by clause.** Not complete (0 of 4 fully met).
(1) Both arms refuse the warranty case and admit the paraphrase on the pinned fixture; nothing calls
either arm outside `reuse/` (grep: no match). (2) `refusal_cause`: no match in `gateway/`.
(3) `support_gate`: no match in `gateway/` or `experiments/`. (4) `TestNoThetaSeparatesTheMeasuredPair`:
PASS.

**Suggested next:** item 2.3 is now unblocked by both arms. Start with the real-answer sample.
