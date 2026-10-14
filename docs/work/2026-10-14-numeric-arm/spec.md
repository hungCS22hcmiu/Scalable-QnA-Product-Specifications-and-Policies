# Spec — numeric arm (super-plan item 2.2)

## Change, in one sentence

Add the numeric arm of the support gate to `gateway/internal/reuse/` as a pure function: every
number in the cached answer, with its unit, must also appear in the fresh evidence text, and a
number the arm cannot read blocks reuse (fail-closed). Nothing on the served path calls it.

## Phase and item

Phase 2, item 2.2 in `docs/super-plan.md`:

> **Numeric arm.** Every numeric literal and its unit in the cached answer must appear in the
> fresh evidence. **Fail-closed.**
>
> Done when: a cached "30-day" answer is refused against evidence carrying only "14-day"; an
> unparseable number blocks rather than passes.

Serves exit clause 1 ("the gate refuses the measured warranty case and admits the measured
paraphrase") together with the lexical arm from item 2.1. Discharges contribution **C1**.
`requirements.md` is still empty, so there is no `FR-xx` to cite.

Why this item before 2.3: 2.3 combines both arms into one cause code, and `interfaces.md` says
`support_numeric_ok` is null only on the gate-off arm. Wiring 2.3 first would log a false null.

## Acceptance

All checks run in `reuse/` with plain `go test`. No Redis, gRPC or HTTP.

1. **Done-when, part 1.** A cached answer that says "30-day" is refused against evidence that
   only says "14-day".
2. **Done-when, part 2.** A number the arm cannot read (for example `1,5`, `½`, a non-ASCII
   digit) makes the verdict refuse. It never passes.
3. **The measured pair.** On the same pinned texts as `support_test.go`, the numeric arm admits
   the paraphrase evidence and refuses the warranty evidence. If it does not, that is a finding
   for the design, not a reason to change the fixture.
4. **Stale server.** `texts == nil` with `len(chunkIDs) > 0` is "not scored". It is not a
   refusal and not the gate-off arm (same rule as item 2.1).
5. **Rules are pinned.** The unit list, the number-word rules, the code rule and the
   normalisation each have a test, so a silent edit fails a test. Rows exist that fail if the
   unit check, the per-chunk rule, the hyphen rule, the plural rule or the decimal rule is removed.
6. `make verify` exits 0. Item 2.1's tests and `TestNoThetaSeparatesTheMeasuredPair` pass
   unchanged.

## Out of scope

- Calling the arm from `httpapi/cascade.go` (items 2.3, 2.4).
- The `refusal_cause` field and the §H log fields (item 2.3).
- The per-run on/off switch (item 2.4).
- Any change to `docs/contracts/interfaces.md`. The fields are already there at v0.9.
- Any change to the lexical arm in `support.go`.
- Unit conversion ("1 year" vs "12 months"). These count as different. It costs some extra
  refusals, which fail-closed accepts.
- Checking `τ_s = 0.6` on real generated answers. That is a follow-up for item 2.3.
- Any learned model or tuned threshold. The arm has no threshold.
