# Spec — lexical support arm (super-plan item 2.1)

## Change, in one sentence

Add the lexical arm of the answer–evidence support gate to `gateway/internal/reuse/` as a pure
function — `S_lex(a,C) = |content-tokens(a) ∩ tokens(C)| / |content-tokens(a)|`, stop-words and
tokens under three characters removed from `a`'s side, gated at the pinned `τ_s = 0.6` — without
wiring it into the live `tryTier2` cascade, the cause code, or run-manifest arm switching.

## Phase and item

Phase 2 — The support gate (`docs/super-plan.md`). Item 2.1, row:

> **Lexical arm.** `S_lex(a,C) = |content-tokens(a) ∩ tokens(C)| / |content-tokens(a)|`,
> stop-words and tokens under three characters removed. `τ_s` **pinned at 0.6**, never swept.
> ⚠️ `RetrieveResult.Texts == nil` with `len(ChunkIDs) > 0` means the service sent no evidence
> text... do not score it, do not refuse it as `SUPPORT`, and do not log it as the gate-off arm
> (`support_lex: null`)... Key on `len(ChunkIDs) > 0`.
>
> Done when: On the pair pinned in `lane_test.go` (0.9382 paraphrase, 0.9208 warranty,
> containment 0.80 each) the gate admits the first and refuses the second.

Discharges contribution **C1** (per the item table — `requirements.md` is still unfilled, so this
cites the contribution rather than an `FR-xx`).

Serves the Phase 2 exit clause: *"the gate refuses the measured warranty case and admits the
measured paraphrase."* The exit clause's other three clauses (cause code, both arms switchable,
the decisive-similarity regression still reproducing) are **not** this item's job — see Out of
scope.

## Acceptance

A new test in `gateway/internal/reuse/` (package-internal, no Redis/gRPC/HTTP — `architecture.md`
§2) that:

1. Pins representative answer text and fresh-evidence text for the same two measured cases
   `TestNoThetaSeparatesTheMeasuredPair` already pins by chunk ID (paraphrase of the return
   question vs. the warranty question, same entry, same product).
2. Calls the new lexical-arm function with the cached entry's answer text against each case's
   fresh evidence text.
3. Asserts the paraphrase clears `τ_s = 0.6` and the warranty case does not.

Run with `go test ./gateway/internal/reuse/...`.

`TestNoThetaSeparatesTheMeasuredPair` itself (the decisive-similarity regression) is **not
touched** by this change — it exercises the two-lane namespace rule, a different code path — and
must still pass unmodified after this item lands.

## Out of scope

- The numeric arm (item 2.2).
- The `refusal_cause` field and §H logging of `support_lex` / `support_numeric_ok` (item 2.3).
- Making the arm switchable per run via the config × mutation grid (item 2.4).
- Calling the new function from `httpapi/cascade.go`'s `tryTier2`, or from anywhere on the live
  request path. 2.1 ships the scoring primitive and its pinned-pair proof inside `reuse/`; wiring
  it into the served decision is 2.3/2.4's job, once there is a cause code to log it under and a
  manifest flag to turn it off.
- Any change to `docs/contracts/interfaces.md` (the `support_lex` / `support_numeric_ok` /
  `refusal_cause` fields are already specified there at v0.9, waiting for 2.3 to populate them —
  2.1 adds no new contract surface).
- Any change to `telemetry/` or the evaluation log.
