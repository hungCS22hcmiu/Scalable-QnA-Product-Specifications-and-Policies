# Plan — fh-generate-ms-on-abandoned

**Scope L.** Nothing below starts until `/approve implementation`. Each step is independently
verifiable; a step that adds a test writes it **first** and shows it **fail by assertion** against the
code before the fix (here the failing code is HEAD itself, so no stub is needed). **No existing test is
edited.** Commands run from the repository root; scratch goes in `$CLAUDE_JOB_DIR/tmp`, not `/tmp`.

Authority: `spec.md` rev 3 (acceptance numbers), `design.md` rev 2, `review.md` (finding numbers),
`contract-draft.md`.

- [x] **1. Contract text, first** *(skipped if the author declines the doc-only v0.12, `approvals.md`
  question 1)*. The text is **already drafted** in `contract-draft.md` (A1-A5, B1-B2). Apply it
  **verbatim** to `docs/contracts/interfaces.md` and `docs/decisions.md`; do not re-draft (the 1.5
  apply-script pattern: extract from the draft, assert each anchor is unique, write once).
  *Verify:* the `contract-reviewer` subagent reads v0.12 against `spec.md` and finds no disagreement;
  `git diff --exit-code contracts/` clean (the `.proto` does not move); the diff under `docs/contracts/` is
  exactly the five hunks; the greps of acceptance 8 (`Current version.*v0.12`, `// null unless this
  request`, `ADR-006`, and **no** `null unless generation ran`).
  **Done:** applied verbatim by an extraction script; `contract-reviewer` found no MUST-FIX and **six SHOULD-FIX wording items** (the selection rule rested on the undefined extension `coalesced`; permit occupancy; the overhead sentence; the `t_permit_wait_ms` pointer; "means" vs "indicates"; the "iff" qualifier), corrected before commit and recorded in `approvals.md`; `git diff --exit-code contracts/` clean; the diff is five hunks at default context (six with `-U0`).

- [x] **2. Tests, red.** New file `gateway/internal/httpapi/generatems_test.go` with T1-T6 of `design.md`
  §4, using the 1.2/F-A harness without editing it (`onAnswer`, `holdAnswers`, `leavingStore`,
  `Waiters`, `Queued`). Header names the two stale comments it supersedes (`ask_test.go:404`,
  `abandon_test.go:64-65`) and declares T3 ADMISSION-SENSITIVE and T5 F-D-SENSITIVE. Lower bounds only,
  holds ≥ 25 ms, **no `t_permit_wait_ms` assertion anywhere**, T3 `t.Logf`s its value, T6 compares
  integer µs. T6 first asserts B's `t_generate_ms` is non-null and that B's `t_permit_wait_ms` is non-null
  **as a fixture precondition** (B really queued, then was served an upstream failure; a queued request that
  is *served* does carry it, unlike a queued-then-left one), then the inequality. *Verify:* run against
  HEAD's `handler.go`: **T1, T2, T3, T5 and T6 fail by assertion** (each on a `t_generate_ms` that is null
  today); **T4 passes** (a declared pin: its value is null today and after); the whole existing suite still
  passes. A test that passes against HEAD and is not a declared pin is a defect in the test, fixed before
  step 3. T6's inequality is trivially true until the field is non-null, so what makes it a guard for F6
  and F7 is shown by those mutations in step 4.
  **Done:** T1, T2, T3, T5, T6 failed by assertion on HEAD's handler (`t_generate_ms` null); T4 passed as a declared pin.

- [x] **3. The fix.** In `gateway/internal/httpapi/handler.go`, move `rec.GenerateMS = generateMS` from
  after the outcome switch (`:523`) to **immediately after `Generations.Do` returns, before the switch**,
  with a comment stating the reading rule and why it sits before the switch (every outcome inherits it;
  SHED, queued-then-left and followers have a nil `generateMS`; **not** inside the closure, because that
  would change the leader-panics path). Delete the old assignment. *Verify:* `go build ./...`; T1-T6 green;
  the whole httpapi suite green with no test edited.
  **Done:** one statement moved after `Generations.Do`, old assignment deleted; the whole `httpapi` suite green, no existing test edited.

- [x] **4. Mutations.** A script in `docs/work/2026-10-06-fh-generate-ms-on-abandoned/evidence/` applies
  F1-F7 of `design.md` §4 to a fresh **copy** of `gateway/` (never the working tree) and runs the existing
  suite and the new tests, as in 1.5. Expected: every mutation caught by the named new test **by
  assertion, not a build error**. F6 and F7 are the ones lower bounds alone could not catch: confirm T6
  catches both. *Verify:* `evidence/mutations.md`, every row caught; a row that is not caught is a defect
  in the test, fixed before step 5.
  **Done:** `evidence/mutations.md`: **F1-F9 all caught by a new test, none by a build error**; F6 and F7 are the ones lower bounds could not catch and T6 catches both (F7 only T6); **F8 and F9 were added after the implementation review** and are caught only by T7 and T8 (the existing suite passes under both, which is why those guards exist); F4 and F6 were first written so they did not compile and were fixed in the script, not in a test.

- [x] **5. Race, and the never-sent tail.** `go test -count=1 -race ./internal/httpapi/`, recorded
  (`make test` does not run `-race`). Then `go test -race -count=30 -run
  TestClientLeftBeforeTheRPCStillRecordsAnAttempt -v ./internal/httpapi/` and read T3's logged values:
  the **first reading of the "RPC never left" tail** against the 1 ms default. *Verify:*
  `evidence/never-sent-tail.md` with the min/median/max and how many of 30 exceed 1 ms. **Recorded, not
  asserted**, exploratory (the machine is not at green pressure) and not citable.
  **Done:** `evidence/never-sent-tail.md`: never-sent value 1-12 µs (12-31 µs under `-race`), 0 of 30 at or above 1 ms; `go test -race ./internal/httpapi/` ok.

- [x] **6. Docs that follow the code.** `docs/super-plan.md`, **in place:**
  - F-H marked ✅ resolved with the reading rule and a pointer to §H v0.12;
  - the pointer at `:165-166` to F-A's `approvals.md` repointed;
  - `:172-173` rephrased (still an upper bound, now tighter);
  - the item-1.6 notes: the threshold and its gap check go in P1's manifest; **1.6's first `RUN_ID` is
    taken after this commit**; the per-statistic selection rule;
  - new findings: `t_permit_wait_ms` null on every fast-path request **and** after a queued-then-left;
    `coalesced` set only on a served MISS (next to F-D).
  F-A's `approvals.md`: **one** dated "superseded by `2026-10-06-fh-generate-ms-on-abandoned`" note
  (`:66`, `:88`, `:111-113`); nothing else in the closed trails. `approvals.md` of this task: the
  **experiment record** (what changes, what does not, comparability, the selection rules, the threshold
  and its check, the never-sent-tail reading). *Verify:* the greps in `spec.md` acceptance 8 and
  `grep -n "null on all of them" docs/super-plan.md` finds nothing.
  **Done:** `super-plan.md` in place (F-H resolved, F-A's upper-bound line, the pointer to F-A's record, the 1.6 notes, new findings F-N and F-O); **one** dated superseded note appended to F-A's `approvals.md`; the experiment record filled.

- [x] **7. Verify, review, close.** `/verify`, reporting the proto-drift row honestly (the stubs are
  gitignored, so `git diff --exit-code contracts/` is what runs, and it is not a stub-drift check).
  `/ai-review`; apply what survives. `/done`. Commit with the attribution line; **do not push** unless
  asked.

## Outcome

**Shipped (2026-10-06).** `t_generate_ms` is non-null iff the request's own `Answer` call was attempted, so
ABANDONED and GENERATION_FAILED leaders now carry the time their attempt took. One statement moved: `rec.GenerateMS =
generateMS` now sits right after `Generations.Do`, before the outcome switch, and the success-path copy is deleted.
- **Code:** `httpapi/handler.go` only (one statement and its comment). Nothing else in the module changed.
- **Contract:** `interfaces.md` **v0.12** (doc-only: the `t_generate_ms` example comment, a field-note row with the
  per-statistic selection rule, the v0.12 block, the Versioning row, plus one cross-reference sentence in the
  `t_*_ms` row) and **ADR-006**. `.proto`, §A-§G and every JSON key unchanged (`git diff --exit-code contracts/`
  clean).
- **Tests, one new file (no existing test edited):** `httpapi/generatems_test.go`, eight tests. T1-T3, T5, T6
  were red against HEAD by assertion; T4, T7 and T8 are declared pins/guards, green throughout.
- **Evidence:** `evidence/mutations.md` (**9 of 9** mutations caught by a new test, none by a build error),
  `evidence/never-sent-tail.md` (never-sent value 1-12 µs, 12-31 µs under `-race`, 0 of 30 at or above 1 ms;
  exploratory), `go test -race` on `httpapi` ok.
- **Repo changes beyond the code:** `super-plan.md` (F-H resolved, F-A's upper-bound line, the pointer to F-A's
  record repointed, the 1.6 notes, new findings **F-N** and **F-O**); **one** dated "superseded" note appended to the
  F-A trail's `approvals.md`.
- **Verified:** `make verify` exit 0 (gofmt, vet, build, Go tests, ruff, pytest 15 + 94); `-race -count=3` on
  `httpapi` ok. **Nothing SKIPPED.** *Caveat on the "proto drift" row:* it checks nothing (the stubs are
  gitignored); `git diff --exit-code contracts/` is what ran, and it is not a stub-drift check.
- **Scope held:** L was right. The field is in the evaluation log, and the review turned a one-line fix into a
  contract amendment (v0.12 + ADR-006) because the field's presence changed meaning.

**Review.** The design review (opus) forced the contract decision (the first analysis was inconsistent about whether
§H's example comments are normative), dropped two assertions that would have pinned known defects, and added the
nested-spans test T6. The contract review corrected wording that could produce a wrong number: **the selection rule
rested on `coalesced`, an extension §H does not define and that is absent on leaders**, so it is now
`cache == "MISS" ∧ t_generate_ms != null`. The implementation review added T7 and T8 for two clauses of §H that no
test could fail on. No MUST-FIX in either implementation pass.

**Deferred, with the author** (`approvals.md`, `super-plan.md`): the **1 ms threshold** for "the RPC never left"
(ADR-006 carries one `⟦PENDING⟧`); the 1.5 items still open (Spotlight, 5.1's verdict key wording, U8, the stale
`v0.9` strings, `-race` in `make test`). **New findings, not fixed:** **F-N** (`t_permit_wait_ms` is null on every
fast-path request, after a queued-then-left, and when admission is disabled) and **F-O** (`coalesced` is set only on
a served MISS and is not in §H).
**Follow-ups worth a task:** F-N and F-O (each needs a contract note like this one), F-D (decides what a follower
should read), F-L, and fixing `/verify`'s proto-drift row.
**Not verified live:** the field against a real gateway run with Redis, Ollama and k6. The never-sent tail in
particular has only a fixture reading; the first `RUN_ID` is the real one, and **it must be taken after this commit**.

## What would make me stop and ask
- A mutation that no test catches after one fix to the test.
- Any need to edit an existing test (none is expected: `impact.md` §4).
- T3's reading showing the never-sent tail routinely above 1 ms: it does not change the fix, but it
  changes what the threshold default can honestly claim, and goes to the author.
- The contract reviewer finding that v0.12 contradicts another §H statement.
