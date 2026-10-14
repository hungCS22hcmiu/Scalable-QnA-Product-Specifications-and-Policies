# Design review — numeric arm (item 2.2)

Reviewer: `design-reviewer` (opus), on `design.md` revision 1. Resolutions are the main session's.
The reviewer could not read `data/dev-v0/` (denied), so it checked only the units in the pinned
fixtures.

**Verdict: sound with changes.** The shape is right (pure function, no threshold, never reads the
query, no model, no cut scope). The problems were in the grammar and the tests.

## Findings, most severe first

1. **[CONFIRMED] The planned tests could not see most of the grammar.** Every fixture row is decided
   by one fact: "is 30 in the evidence". These edits would all keep the table green: drop the unit
   check; join chunks (R8); drop the hyphen; drop plural stripping; trim zeros on integers (`30`
   becomes `3`); split `5.3` into 5 and 3.
   **Resolved: fixed.** `design.md` now has rows that separate each of them. `plan.md` adds a
   *golden extraction test* (the exact item list for the pinned strings, hash-pinned like the
   stopword list), a normalisation table, and a hand mutation check (step 7).

2. **[CONFIRMED] Number words failed open.** R7 skipped `thirteen`…`nineteen`, `hundred`, `half`,
   `dozen`. "within fourteen days" had no number, so it passed. "twenty-four hours" read as 20 and
   4, and both were in a real chunk (h09), so a wrong 24 passed.
   **Resolved: fixed.** R7 now covers 0–99 with compounds, reads a number word only before a listed
   unit, and counts `hundred/thousand/million/half/dozen/couple` before a unit as `Unreadable`.
   "a year" / "an hour" stay unread: recorded as known gap F6.

3. **[CONFIRMED trace] Letter-glued digits (`IPX7`, `v5.2`, `BT5.3`) were never checked.** The
   reason "the lexical arm sees them" was wrong: `S_lex` is a ratio, so a wrong rating passed both
   arms (0.625 in the reviewer's example).
   **Resolved: fixed.** R3: such a run is a *code* and must appear whole in one chunk. Fail-closed,
   no knob.

4. **[CONFIRMED] One word between number and unit drops the unit** ("30 calendar days", "2 full
   years"). Value-only is almost no check for small numbers.
   **Resolved: open for the author (D2).** No fix without a knob. Design: accept, count it in
   `Unitless`, pin it with a test, measure it in the real-answer sample.

5. **[CONFIRMED] D3 (refuse on empty retrieval) had a false premise.** Row 2.4 and the proposal
   (`Final_Proposal.md:186,455`) switch the **whole gate** on/off. There is no state with lexical
   off and numeric on. And on the on-arm, `S_lex` already refuses an empty retrieval
   (`support.go:157`). D3 would only add refusals that are not about numbers, and pollute the
   "refusal rate by arm" metric (`Final_Proposal.md:411`).
   **Resolved: fixed.** The special case and the `NoEvidence` field are gone. The stale-server key
   is the same as `SupportLexical`. 2.3 must close the zero-chunk hole in the cascade.
   *Side note:* the Phase 2 exit line says "both arms are independently switchable". Row 2.4 means
   the gate on/off. The wording is loose. Fix it when 2.4 opens.

6. **[CONFIRMED] Option C is weak on real text.** It differs from "unit anywhere in the evidence"
   only across chunks. "a 12-year warranty" passes against `2-year` + `12 months`. A sharper option
   with no knob is "same line in the chunk".
   **Resolved: open for the author (D1).** Checked the cost of L: `ingest.py:47-55` writes a
   product one spec per line but a policy as one paragraph, so L equals C for policies, and L ties
   the arm to the ingest template. Recommendation stays C, with L and B as later steps.

7. **[CONFIRMED] The evidence side was not specified.** Rows 2 and 4 pass only if evidence gets the
   same lowercase, plural and glued-unit handling. Unreadable spans in evidence (`m²`, `½`) could
   block every request on Amazon-PQA text.
   **Resolved: fixed.** New rule R9: same reader; a chunk's units are only those attached to its
   numbers; unreadable spans in evidence are ignored.

8. **[CONFIRMED] Ordinary text is refused too often.** R7 converted `two` in "two ways". "Bluetooth
   5.2 vs 5.3" read `vs` as the unit `v` (volts).
   **Resolved: fixed.** Number words are read only before a listed unit. A plural `s` is dropped
   only if at least 2 letters remain.

9. **[Minor]** `spec.md` acceptance 5 asked for a "window size" test, but there is no window.
   Spelled-out units fell back to value-only. The unit list should be frozen before any false-hit
   sample is seen.
   **Resolved: fixed.** Spec edited. Aliases added (gram, watt, volt, pound, foot/feet, litre).
   The list is frozen before the sample is looked at (`design.md`, `plan.md`).

## Ambiguities in revision 1, now settled in revision 2

- `v5.3`: one code with a `.digits` tail (R3).
- `one-year`: read as 1 year (R7 allows one hyphen).
- `vs`: not a plural (R6).
- A comma after the number ends the unit lookup (R4).
- `0` stays `0`, `0.5` stays `0.5`; integer zeros are never trimmed (R1).

## Not settled by the review

U1–U6 in `design.md`. The hand-made prediction table was traced by the reviewer: all 9 original
rows hold, but only the "is 30 present" part was exercised. The new rows have not been run.

---

# Code review (`/ai-review`, 2026-10-14)

Routing: the diff touches only `reuse/` and docs (no contract, Redis, wire or proto change), so
`contract-reviewer` ran as a general pass, on top of my own fuzz run. **Verdict: clean with notes.**
The reviewer traced the code against R1–R9 and the five clarifications with about 300 probe strings.
It found no panic and no branch that fails to advance (6.9 M random strings, 1.4 M fuzz runs), no
boundary or rule violation (stdlib only, no threshold, no env read, `support.go` and
`support_test.go` untouched, only the allowed files changed), and no doc that names a test that does
not exist. Every other statement in the docs was checked and holds.

## Findings and resolutions

1. **[CONFIRMED] A digit-first code lost its `.digits` tail** (`12x1.5mm` read as `#12x1` plus a
   stray `5/mm`; `4K.5` as `#4k 5`). R3 says the tail stays. Letter-first codes were right, so the
   two forms disagreed. I reproduced it on the real code.
   **Resolved: fixed.** One helper, `codeTail`, now serves both forms. Three rows added.

2. **[CONFIRMED] Several frozen rules had no test that bites,** and two docs read as if all were
   pinned. About ten edits stayed green: line break between number and unit; the whole-number
   check of the list marker; the leading-point exception; tab handling (two places); the plural
   cut (`lbs`, `kgs`); lowercasing of a glued unit and of the ones word; the first thousands group;
   tens + zero/teen; `hundred` without a unit.
   **Resolved: fixed.** One row per item in `TestNumericReaderRules`; each edit is now in
   `mutation-check.py` and turns a test red. The Golden test comment no longer claims it covers
   every rule. The "23 edits" sentence in `super-plan.md` now says 35 and says what that proves.
   Note: the reviewer tried 80+ edits and named about ten; I re-ran those. Other untried edits may
   still survive. The count is a floor, not a guarantee.

3. **[CONFIRMED, low] One row guarded less than it claimed:** "hyphen and plural" stayed green if the
   hyphen rule was dropped. **Resolved: fixed.** Split into a hyphen row and a plural row, each
   against a chunk that has 30 only with hours; the old row stays as a positive control.

4. **[PLAUSIBLE, low] A non-breaking space or hyphen between number and unit drops the unit** on the
   answer side (fails open to a value-only check) and loses it on the evidence side (false
   refusal). Reproduced: `30<U+00A0>days` and `30<U+2011>day` read as `30`; `twenty  four hours`
   (two spaces) reads as `4/hour`.
   **Resolved: fixed, at the author's request** ("fix it now please"). R5 now accepts `U+00A0` and
   `U+202F` as spaces and `U+2011` as a hyphen; R7 accepts a run of spaces in a compound. Amended in
   `approvals.md` ("Separators") before any run logged the field. Rows pin the accepted characters
   and the refused ones (en dash, `U+2010`, thin space), which stay known gaps.

5. **[CONFIRMED, docs] Trail notes differed from the plan:** benchmark and mutation list were only in
   `plan.md`; `plan.md` named a test that does not exist (`TestNumericStaleServer`); the mutation
   script was not kept. **Resolved: fixed.** `approvals.md` has an Implementation record; the test
   name is corrected; the script is `mutation-check.py` in this trail.
