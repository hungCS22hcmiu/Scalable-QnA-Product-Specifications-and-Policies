# Approvals — numeric-arm

| Phase          | Required    | Approved | When | ADR |
| :---           | :---        | :---     | :--- | :--- |
| impact         | L, M        | yes      | 2026-10-14 | — (no frozen value touched, no run invalidated: none exist, `impact.md` §2. The item **creates** a new frozen definition; it is recorded at plan step 1 and in `decisions.md` at step 8, per `impact.md` §6) |
| contract       | if §B/§D    | not required | — | `support_numeric_ok` is already in `interfaces.md` at v0.9 (`impact.md` §4). Required again at 2.3 (a "not scored" value) |
| experiment     | if measured | not required | — | Nothing is measured by 2.2. Required again at 2.3 |
| implementation | always      | yes      | 2026-10-14 | — (over `plan.md` steps 1–9 and `design.md` revision 2 as written. No frozen value touched and no run invalidated: none exist. The item creates a new frozen definition, recorded at plan step 1. D1–D3 were not answered one by one: see "Human decisions") |

## Decisions D1–D3 — accepted as recommended (2026-10-14)

Recorded from `/approve implementation`, not from separate answers (see "Human decisions"). They
stay changeable until plan step 1 writes the definition below.

- **D1.** How close must the unit be: **C** same chunk · L same line · B within K words.
- **D2.** Words between number and unit ("30 calendar days"): **accept the gap, count it** · add a knob.
- **D3.** Where to record the definition: **a `decisions.md` row with the ADR condition** · one ADR now.

The review also changed three things without asking you (number words, empty retrieval, codes).
Say so at approval if you disagree. See `review.md` findings 2, 3, 5.

## Frozen artefact this item creates

Written 2026-10-14 at plan step 1, **before any code or test existed**. Source: `design.md`
revision 2 (R1–R9) plus the five clarifications at the end of this section. Where they differ,
**this section wins**. Answers: D1 = C (same chunk) · D2 = accept the gap and count `Unitless` ·
D3 = a row in `decisions.md`.

After the first logged run, any change to anything below needs a numbered ADR with an
`Invalidates:` line (standing constraint 5). The unit list is *draft* until the Phase 3 corpus
freeze, and is frozen before any false-hit sample is looked at.

**What is read.** The answer and each evidence chunk go through one reader (R9). It produces
*items*: a number `(value, unit)` or a code. An item is supported when ONE chunk has its value
and, if it has a unit, the same chunk has that unit attached to some number in it (R8, D1 = C).

- **R1 Number.** ASCII digits `\d+`, then optional groups `,ddd` and optional `.d+`. Clean form:
  no commas, leading zeros removed (but `0` and `0.5` stay), trailing zeros removed only after the
  point (`5.30` = `5.3`, `5.0` = `5`, `100` stays `100`).
- **R2 Unreadable** (each one blocks): a digit run that breaks R1 (`1,5`, `1,2345`, `5.3.1`), a
  number with a leading point (`.5`), any non-ASCII number character (`unicode.IsNumber`: `½`,
  `²`, `٣`; one count per run), a `hundred/thousand/million/half/dozen/couple` directly before a
  listed unit. In *evidence*, unreadable spans are ignored.
- **R3 Code.** A run of letters and digits that is not "number + listed unit": `IPX7`, `v5.3`,
  `BT5.3`, `1000XM5`, `3rd`, `4K`, `24x7`. Lowercase. It must appear whole as a code in one chunk.
  A `.digits` tail stays in the code.
- **R4 Punctuation.** A `.` or `,` after digits and not before a digit is punctuation and ends the
  unit lookup. A whole number at the start of a line (spaces allowed) followed by `.` or `)` and a
  space is a list marker and is skipped.
- **R5 Unit.** For a number: glued letters (`250g`, `3.5mm`); else, after one hyphen or after
  a run of spaces, the next word (`30-day`, `30 days`; separators: see **Separators** below); `%` after zero or more spaces; `$ € £`
  directly before. Only the **word right after** counts, and only if it is a listed unit.
  Otherwise no unit: only the value is checked and `Unitless` goes up. Glued letters that are
  *not* a listed unit make the whole token a code (R3).
- **R6 Unit list (closed, draft).** second, minute, hour, day, week, month, year · g, kg, mg, lb,
  oz · mm, cm, km, inch, ft · ml, litre · w, kw, v, mah, wh · hz, khz, mhz, ghz, kb, mb, gb, tb, db
  · rpm · percent (= `%`) · `$`, `€`, `£`. Aliases: sec→second, min→minute, hr/hrs→hour,
  yr/yrs→year, inches→inch, gram→g, kilogram→kg, pound→lb, foot/feet→ft, liter→litre, watt→w,
  volt→v. Lowercase. A plural `s` is dropped only if at least 2 letters remain (`days`→`day`;
  `vs` stays `vs`). No other conversion: `1 year` ≠ `12 months`.
- **R7 Number words**, read only when directly before a listed unit (spaces or one hyphen):
  `zero`…`nineteen`, `twenty`…`ninety`, and a tens word + ones word `one`…`nine` joined by one
  hyphen or a run of spaces (`twenty-four`, `twenty four`, `twenty  four`). `one year` = 1 year; `one of`, `two ways`
  are not numbers. `hundred/thousand/million/half/dozen/couple` before a unit = unreadable.
  `a year` / `an hour` are not read (known gap).
- **R8 Per chunk.** Each text is read alone. Chunks are never joined.
- **R9 Evidence** is read with the same reader. A chunk's values are its numbers and codes. A
  chunk's units are the units attached to its numbers by R5, not any word in it.

**Verdict.** `Scored` is false only when `len(texts) == 0 && len(chunkIDs) > 0` (stale server).
`Refuses()` = `Scored && (Unsupported > 0 || Unreadable > 0)`. Items are a set; `Unreadable` counts
every occurrence. No empty-retrieval special case. No threshold.

**Clarifications made at this step** (not in `design.md`; none changes a decision):
1. R7 accepts a space as well as a hyphen in a compound (`twenty four`). `design.md` said
   hyphen only, which would have read `twenty four hours` as 4 hours and hidden the 20.
2. R5 accepts `%` after spaces, not only glued (`80 %`).
3. R3 states that ordinals and other digit-letter tokens (`3rd`, `4K`, `1080p`) are codes.
4. R2 adds the leading-point number (`.5`) as unreadable. It would otherwise read as 5.
5. R6 makes `litre` a unit with the alias `liter`. `design.md` listed both as aliases with no target.
6. **Amended after `/ai-review`, at the author's request ("fix it now please", 2026-10-14), before any
   run logged the field.** See **Separators** below: R5 and R7 accept no-break spaces and the
   non-breaking hyphen, and the R7 compound separator is a run of spaces.

Known gaps, accepted: `a year`; words between number and unit (D2); numbers above 99 written in
words (`two hundred and fifty grams` reads only `fifty grams`); right number with a wrong unit in
the same chunk (D1).

## Separators (amends R5 and R7, 2026-10-14, after `/ai-review` finding 4)

A **space** is exactly: `' '`, tab, `U+00A0` (no-break space), `U+202F` (narrow no-break space). A
**hyphen** is exactly: `-` and `U+2011` (non-breaking hyphen). A line break is neither. Used in R5
(between a number and its unit, and before `%`) and in R7 (inside a compound number word, where a
run of spaces is allowed). Pinned by `TestNumericReaderRules` (accepted ones and refused ones) and
by six edits in `mutation-check.py`.

Refused on purpose, so the answer is read by value only and the evidence loses the unit: en dash
`U+2013`, `U+2010`, thin space `U+2009` and the other Unicode spaces and dashes. A no-break space
after a list marker (`1.` + `U+00A0`) is not a marker space either (R4 is unchanged). These are
known gaps, pinned by rows so that widening the set is a decision, not a drift. Check the v1 text
at Phase 3.

## Known gap found at /ai-review (now resolved above)

- A non-breaking space (`U+00A0`, `U+202F`), a non-breaking hyphen (`U+2011`) or two spaces between a
  number and its unit. The answer is read by value only (counted in `Unitless`). In evidence the
  unit is lost, so that chunk cannot support a unit (a false refusal). `twenty  four hours` (two
  spaces) reads as 4 hours.
- **Resolved 2026-10-14**: the author chose to fix it now. See **Separators** above. Two spaces
  between a number and a unit already worked; the case that failed was the compound (`twenty  four`).

## Implementation record (2026-10-14)

- Benchmark: `BenchmarkSupportNumeric` about 14.5 µs/op, 7976 B/op, 96 allocs. `BenchmarkSupportLexical`
  in the same run: about 14.0 µs/op (M1). Not a measurement of the system.
- Mutation check: `mutation-check.py` in this trail. **41 edits, 41 red, 0 survivors** (23 before
  `/ai-review`, 12 added after it, 6 more with the separator change). It proves those 41 are caught,
  not that every edit is.
- Fuzz: 1.2 M inputs in a scratch copy before the review, 1.4 M more by the reviewer, 3.7 M after the
  separator change. No panic, no hang. `FuzzReadNumbers` is now in the test file, so its seeds run in every `go test`.

## Human decisions

| Date | Decision | Author's words | Invalidates |
| :--- | :--- | :--- | :--- |
| 2026-10-14 | **Open item 2.2 at scope L** (`/task numeric-arm L`) | "oke now we start phase 2.2" | — |
| 2026-10-14 | **`/approve impact`** — `impact.md` accepted. This approves the blast-radius analysis only. It does **not** answer D1–D3, and it does not unlock source edits | — (slash command) | — |
| 2026-10-14 | **`/approve implementation`** — unlocks `reuse/support_numeric.go`, `reuse/support_numeric_test.go`, `reuse/doc.go`, and the doc rows in `decisions.md`, `super-plan.md`, `architecture.md`, per `plan.md` steps 1–9. **D1–D3 were not answered separately.** The command was run after the author read the three recommendations, with no objection, so this is recorded as acceptance of `design.md` revision 2 as written: **D1 = C** (same chunk), **D2 = accept the gap and count `Unitless`**, **D3 = a `decisions.md` row with the ADR condition**. The three changes made without asking (number words, empty retrieval, codes) are accepted the same way. The author can change any of them until plan step 1 copies the definition here | — (slash command) | — |
| 2026-10-14 | **`/done`** | — (slash command) | — |

## Recorded follow-ups (not blocking this item)

- **Real-answer sample, now for both arms.** The check on 10–20 real generated answers (already
  required before 2.3, see the 2.1 trail) must also count: number words, list markers, codes
  (`IPX7`), words between number and unit (`Unitless`), `Unreadable`, and how often the numeric
  arm refuses an answer the lexical arm admits. Needs Ollama in green pressure.
- **For 2.3:** (a) §H needs a value for "not scored" for both arms; (b) the zero-chunk hole
  (`support.go:157-160`) is closed in the cascade, not in an arm; (c) `cascade.go:45-47` comment
  goes stale.
- **For 2.4:** the Phase 2 exit line says "both arms are independently switchable", but row 2.4
  and the proposal mean the whole gate on/off. Fix the wording when 2.4 opens.
- **Phase 3:** the unit list is draft until the corpus freeze. Check it against v1 text, and freeze
  it before any false-hit sample is looked at.

## Status (2026-10-14)

- Done: `SCOPE` (L), `spec.md`, `impact.md` (from `impact-analyst`), `design.md` (revision 2),
  `review.md` (`design-reviewer`, opus: sound with changes, 9 findings; 7 resolved into the design,
  2 are decisions D1 and D2 for the author), `plan.md`.
- Approved by the author: **impact** (2026-10-14), **implementation** (2026-10-14).
- `READY_TO_IMPLEMENT` written at approval, **deleted by `/done`**; the gate is re-locked.
- Implemented 2026-10-14: plan steps 1–9, `make verify` exit 0 (see `plan.md`, Implementation notes). Next: `/ai-review`, `/done`.
- **Closed 2026-10-14.** Prior runs invalidated: none (no run exists). See `plan.md`, Outcome.
