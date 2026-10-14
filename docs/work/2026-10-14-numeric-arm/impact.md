# Impact — numeric arm (item 2.2)

Written by the main session from the `impact-analyst` report. Line numbers were spot-checked
against the files (fixture lines, `Thresholds` env read, Makefile PASS names).

## The main finding

No frozen value is touched and no run is invalidated (none exist). But 2.2 **creates a new frozen
definition**. The arm has no threshold, so its rules (what counts as a number, a unit, "nearby")
act as the tuning knob.

The fixture already shows the danger. The cached answer says "24 hours" (`support_test.go:109`).
The evidence says "6 hours (24 with case)" (`support_test.go:49`). A rule that wants the unit
right after the number refuses this paraphrase. Picking a rule *after* seeing that result is
tuning to make a headline work. So the rules must be written down and approved **before** the
measured-pair test first runs.

## 1. What it touches

| File | Change |
| :--- | :--- |
| `gateway/internal/reuse/support_numeric.go` | new |
| `gateway/internal/reuse/support_numeric_test.go` | new |
| `gateway/internal/reuse/doc.go` | one line |
| `docs/decisions.md` | one row in the frozen table |
| `docs/super-plan.md`, `docs/architecture.md` | status rows |

- `reuse/` stays a leaf. It imports only `strings` today (`support.go:3`). `unicode`, `unicode/utf8`
  and `strconv` are standard library and fine (`architecture.md:146` forbids only Redis, gRPC, HTTP).
- `go.mod` does not change.
- Take `(answer string, texts, chunkIDs []string)` like `SupportLexical` (`support.go:161`).
  Never a `ragclient` type.
- **Cut from the plan:** the optional change to `ragclient/support_live_test.go`. It needs the
  live stack, asserts nothing, and the `fidelity` subtest already proves the fixture text.
- Not touched: `httpapi`, `telemetry`, `cmd`, `.proto`, `interfaces.md`, `experiments/`.

## 2. Frozen values and runs

- No frozen-list value is touched.
- `τ_s` is not used. The arm has no threshold. **Do not** add a `TauSupportNumeric`, and do not put
  any new number in `Thresholds` (`rule.go:84`): `main.go:176-177` reads its fields from the
  environment, which would make the value sweepable.
- **Invalidates: none.** `experiments/results/` holds only `.gitkeep`.

## 3. Dropped scope

Not reinstated. The numeric arm is not on the do-not-reinstate list. It is on the droppable list
(`Final_Proposal.md:595`), so build it small. It reads the answer and the evidence, never the query.

## 4. Dependency, contract, measurement

- No dependency.
- No contract change. `support_numeric_ok` is a bool, null only on the gate-off arm
  (`interfaces.md:551,600`). To keep that meaning, the function returns a struct with a `Scored`
  field and a `Refuses()` method, like `SupportVerdict` (`support.go:107-136`):
  - stale server (no texts, chunk IDs present) → not scored;
  - answer with no numbers → scored, passes (never null);
  - empty retrieval → see `design.md` decision D3.
- Keep the *reason* for a refusal (number missing / number unreadable) in the struct, not in §H.
  Otherwise fail-closed refusals cannot be told apart from real mismatches in the "refusal rate by
  arm" metric (`Final_Proposal.md:411`).
- §H has no value for "not scored" on either arm. **2.3 will need that**, so 2.3 needs the
  contract phase and the experiment phase.
- Nothing is measured by 2.2.

## 5. Hidden risks

- **Name clash:** only `eachToken` (`support.go:44`). Do not call it either: it splits "5.3" into
  5 and 3, and "1,5" into 1 and 5, so it cannot see decimals or unreadable numbers.
- **Test file** is `package reuse`: reuse `cachedAnswer`, `paraphraseEvidence`, `sha12` and the
  other fixtures. Do not redeclare them. Do **not** edit `support_test.go` (tests are immutable).
  New authored strings need their own checksum test in the new file.
- **Chunk boundaries:** `support.go:169` joins chunks with "\n". Match **per chunk**, never over the
  joined text.
- **The pinned texts contain hard cases:** "Bluetooth 5.3", "3.5mm", "250g", "5g each", "IPX4",
  "Pop 3", "80%", "2-year". `specHeavyAnswer` (`support_test.go:116`) has "5.3": if a decimal were
  unreadable, every Bluetooth version would be refused.
- **Makefile:** `support-check` needs exactly four PASS names (`Makefile:376`) and fails on any
  SKIP (`:378`). Another reason to leave the live test alone.
- **Other docs:** `super-plan.md` row 2.4 "Unblocked when 2.2" becomes "2.2 ✅"; row 2.3 should list
  2.2; `architecture.md:50,203` change.

## 6. Frozen-definition risk

Each of these can flip `support_numeric_ok` after a run has logged it, with no error:

- the number grammar (decimals, "1,500" vs "1,5", ranges, "%", glued units, digits inside words
  like "IPX4", list markers like "1." in LLM output);
- the test for "unreadable" (`unicode.IsDigit` vs `IsNumber`: "½" and "²" are category No; the
  tables follow the Go toolchain, so pin them with test characters);
- the unit list and normalisation (day/days, "30-day" vs "30 days", case);
- the number words ("one of the…" is not a quantity);
- how "nearby" is defined, and per chunk vs joined.

A **row in `decisions.md`** is enough, as for `S_lex` (`decisions.md:71`). Two conditions:
(a) the definition is written in `approvals.md` before the measured-pair test first runs;
(b) the row says any edit after the first logged run needs a numbered ADR with an `Invalidates:`
line. The frozen table is defined as pre-thesis state (`decisions.md:54-59`), so a second
unnumbered row stretches it a little. One ADR now is the other choice. That is the author's call.

## Follow-up to record

Add the numeric arm to the follow-up "check on 10–20 real generated answers before 2.3". Real LLM
text is where fail-closed will refuse most.

## Phases required

impact · implementation. Contract and experiment are **not** required for 2.2. Both become
required at 2.3.
