# Design — numeric arm (item 2.2)

Revision 2, after the design review (`review.md`). Short on purpose. Three choices are the
author's: see "Decisions for the author".

## What it does

One pure function in `reuse/support_numeric.go`. It reads the cached **answer** and the **fresh
evidence chunks**. It never reads the query. It finds every number in the answer (with its unit,
if it has one) and checks that each one is in the evidence. If one is missing, or one cannot be
read, reuse is refused. "Fail-closed" means: when unsure, refuse.

```
SupportNumeric(answer, texts, retrievedChunkIDs)
  no texts, but chunk IDs exist ─► Scored=false     stale server: not a refusal (same key as SupportLexical)
  read the answer   ─► items: numbers (value, unit?) and codes, + a count of unreadable ones
  read EACH chunk alone, with the same reader (R9) ─► its values, codes and units
  an item is supported when ONE chunk has its value AND (it has no unit OR that chunk has the unit)
  Unsupported + Unreadable == 0 ─► Admits      otherwise ─► Refuses
```

An empty retrieval has no special case: every number in the answer is then unsupported, so an
answer with numbers is refused and an answer without numbers is admitted. Closing the "zero
chunks" hole is 2.3's job, in the cascade (see `review.md`, finding 5).

## The function

```go
type NumericVerdict struct {
    Scored      bool // false only for a stale server. Everything below is meaningless then.
    Numbers     int  // items checked in the answer (numbers and codes)
    Unsupported int  // readable, but no single chunk supports them
    Unreadable  int  // could not be read. Each one blocks.
    Unitless    int  // numbers checked by value only (no listed unit). Diagnostic, never blocks.
}
func (v NumericVerdict) Refuses() bool // Scored && (Unsupported > 0 || Unreadable > 0)
func (v NumericVerdict) Admits() bool  // Scored && !Refuses()
func SupportNumeric(answer string, texts, retrievedChunkIDs []string) NumericVerdict
```

- Same shape as `SupportVerdict`. Decide with `Refuses()` or `Admits()`, never by reading the
  counts. `!Refuses()` is wrong: it is also true when not scored.
- No threshold, no constant that can be swept, nothing in `Thresholds`.
- Standard library only. Own tokenizer. It does **not** call `eachToken`, `contentTokens` or
  `textTokens` from `support.go`.
- Items are sets: the same number twice in an answer counts once.

## The rules (this is the frozen definition)

| # | Rule |
| :-: | :--- |
| R1 | **Number.** ASCII digits, optional thousands groups (`1,500`), optional decimal part (`5.3`). Compared in a clean form: no commas; leading zeros removed (but `0` and `0.5` stay); trailing zeros removed **only after the point** (`5.30` = `5.3`, `5.0` = `5`, but `100` stays `100`). |
| R2 | **Unreadable.** A digit run that breaks R1 (`1,5`, `1,2345`, `5.3.1`), or any number character that is not an ASCII digit (`½`, `²`, `٣`; test: `unicode.IsNumber`), or a number word R7 cannot read. Each counts in `Unreadable` and blocks. |
| R3 | **Codes.** A run of letters and digits that is not "number + listed unit" is a *code*: `IPX7`, `v5.3`, `BT5.3`, `1000XM5`. A code must appear **whole** (lowercase) as a token in one chunk. Otherwise it is `Unsupported`. A `.digits` tail stays part of the code (`v5.3`). |
| R4 | **Punctuation.** A `.` or `,` after digits, not followed by a digit, is punctuation, and it ends the unit lookup. A number at the start of a line followed by `.` or `)` and a space is a list marker (`1. Return…`) and is skipped. |
| R5 | **Unit.** The word **right after** the number (glued, after spaces, or after one hyphen: `250g`, `30 days`, `30-day`), if it is in the unit list. `%` right after, or `$ € £` right before, is also a unit. Any other word is not a unit; then only the value is checked and `Unitless` goes up. |
| R6 | **Unit list (closed, draft).** second, minute, hour, day, week, month, year · g, kg, mg, lb, oz · mm, cm, km, inch, ft · ml · w, kw, v, mah, wh · hz, khz, mhz, ghz, kb, mb, gb, tb, db · rpm · percent (= `%`). Aliases: sec, min, hr, hrs, yr, yrs, inches, gram, kilogram, pound, foot, feet, litre, liter, watt, volt. Lowercase. A plural `s` is dropped only if at least 2 letters remain (`days` → `day`, but `vs` stays `vs`). No other conversion: `1 year` ≠ `12 months`. |
| R7 | **Number words** are read **only when directly before a listed unit** (spaces or one hyphen). `two`…`nineteen`, `twenty`…`ninety`, and compounds (`twenty-four`) become digits. `one year` = `1 year`, but `one of`, `two ways` are not numbers. `hundred`, `thousand`, `million`, `half`, `dozen`, `couple` before a unit count as `Unreadable`. `a year` / `an hour` are **not** read (known gap F6). |
| R8 | **Per chunk.** Each text is read alone. An item's value and its unit must be in the **same** chunk (D1). Chunks are never joined. |
| R9 | **Evidence is read with the same reader.** A chunk's values are the numbers and codes in it. A chunk's units are the units attached to its numbers by R5, not any word in it. Unreadable spans in evidence are ignored: they never block. |

The rules and the list are part of what `support_numeric_ok` means, the same way the stopword
list is part of `S_lex`. They are pinned by tests (see `plan.md`). The unit list stays **draft
until the Phase 3 corpus freeze**, and is frozen **before** any false-hit sample is looked at.

## Decisions for the author

**D1 — How close must the unit be?**
- **A. Right next to the number in the evidence.** *Rejected.* It fails the project's own
  fixture ("24 hours" in the answer, "6 hours (24 with case)" in the evidence).
- **B. Within K words.** Sharper, but K is a new knob that someone can tune.
- **C. Same chunk (recommended).** No knob. It follows the proposal ("must appear in the freshly
  retrieved evidence"). Weak spot: right number, wrong unit, same chunk. Example: "a 12-year
  warranty" passes against a chunk that has "2-year" and "12 months".
- **L. Same line inside the chunk.** No knob, and sharper on product specs (one spec per line).
  But ingest writes a policy as one paragraph (`ingest.py:47-55`), so for policies L is the same
  as C. And it ties the arm to the ingest template: a layout change would silently change what
  the arm means.
- I saw the fixture before choosing. I recommend C because it has no knob and follows the
  proposal, not because it makes the pair pass. Cross-product mixing is already stopped earlier by
  the namespace rule. L or B can come later, as a new ADR, if the judged false-hit sample shows C
  is too weak.

**D2 — Words between the number and the unit** ("30 calendar days", "2 full years"). R5 sees no
unit there, so only the value is checked. This is close to no check for small numbers like 3 or
5.3. There is no fix without a knob. Recommended: **accept the gap**, count it in `Unitless`, pin
it with a test, and measure it in the real-answer sample. The other choice is to add a skip-one-word
knob (B).

**D3 — Where to record the definition.** Recommended: a row in `decisions.md`'s frozen table, like
`S_lex` (precedent: `decisions.md:71`). The row must say: any edit after the first logged run
needs a numbered ADR with an `Invalidates:` line. The other choice is one ADR now.

(Number words, empty retrieval and code handling are decided in the rules above; the review
changed all three. Say so at approval if you disagree.)

## What I expect (predicted by hand, not run)

| Answer | Evidence | Expected |
| :--- | :--- | :--- |
| "30-day return" | "14-day window" | refuse (30 missing) |
| `cachedAnswer` | paraphrase evidence | admit |
| `cachedAnswer` | warranty evidence | refuse (no 30) |
| `specHeavyAnswer` | paraphrase evidence | admit |
| `specHeavyAnswer` | warranty evidence | refuse (no 30) |
| "about 1,5 days" | anything | refuse (unreadable) |
| "30 days" | `[h02]` only | refuse (30 is there, but only with `hour`) |
| "30 days" | two chunks `["30 hours", "14 days"]` | refuse (per chunk) |
| "30-day" | `["within 30 days"]` | admit (hyphen, plural) |
| "Bluetooth 3.5" | `[h03]` | refuse (decimal is one number) |
| "has an IPX7 rating" | `[h04]` | refuse (code) |
| "twenty-four hours" | `[h09]` | refuse (no 24 there) |
| "fourteen days" | returns policy | refuse (no 14) |
| "30 calendar days" | `[h02, warranty]` | **admit**, `Unitless=1` (known gap D2) |
| no numbers | non-empty evidence | admit |
| no numbers | empty retrieval | admit (2.3 closes the hole) |
| "30 days" | empty retrieval | refuse |
| any | texts nil, chunk IDs present | not scored |

Normalisation rows: `50` ≠ `5`, `100` ≠ `1`, `0`, `0.5`, `5.30` = `5.3`, `1,500` = `1500`.

The pinned fixtures decide only "is 30 in the evidence". The other rows exist to catch silent
edits to the grammar. If a row comes out different when run, that is a finding. The fixture
stays as it is.

## Failure modes

- **F1. Too many refusals on real model text.** Derived numbers ("6 + 24 = 30 hours"), dates,
  `24/7`, `Step 1:` can refuse a good answer. Fail-closed accepts this. Measured in the
  real-answer sample.
- **F2. Right number, wrong unit, same chunk** is admitted (D1-C).
- **F3. Unit not in the list** (a new unit in the v1 corpus): only the value is checked. Weaker,
  not unsafe. `Unitless` shows how often.
- **F4. Compound or odd number words** (`twenty four` without a hyphen) may refuse. Safe, costs hits.
- **F5. A caller reads the counts instead of `Refuses()`.** Guarded by the doc comment.
- **F6. "a year", "an hour"** are not read. A wrong value hidden there passes. Known gap.
- **F7. Words between number and unit** (D2).

## Unknowns

- **U1.** How the real model writes numbers (digits, words, list markers, codes, extra words).
  Answered by the 10–20 real-answer sample, which now covers both arms (`approvals.md`).
- **U2.** Whether the unit list fits the v1 corpus (draft until Phase 3).
- **U3.** Whether C is sharp enough. Answered later by the judged false-hit sample.
- **U4.** `unicode.IsNumber` depends on the Go version. Pin it with test characters.
- **U5.** §H has no value for "not scored". 2.3 must add one.
- **U6.** The table above is a prediction. It has not been run.

## Not decided here

Wiring, the cause code and the gate on/off switch (2.3, 2.4). No change to `support.go`,
`support_test.go`, `cascade.go`, `telemetry/`, `interfaces.md`, the live test or the Makefile.
