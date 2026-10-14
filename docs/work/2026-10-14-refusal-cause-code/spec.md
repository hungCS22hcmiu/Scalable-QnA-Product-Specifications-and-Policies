# Spec — refusal cause code (super-plan item 2.3)

## Change, in one sentence

Call the support gate (both arms) from the Tier-2 cascade, and log for every request where a Tier-2
candidate was judged exactly one `refusal_cause`, plus `support_lex` and `support_numeric_ok`; add a
"not scored" value to §H and close the zero-chunk hole in the cascade.

## Phase and item

Phase 2, item 2.3 in `docs/super-plan.md`:

> **Refusal cause code** in §H: `SIMILARITY` | `NAMESPACE` | `CONTAINMENT` | `SUPPORT` | `NONE`,
> plus `support_lex` and `support_numeric_ok`.
>
> Done when: every Tier-2 decision in the log carries exactly one cause; a support refusal is
> distinguishable from a namespace refusal offline.
>
> ⚠️ Since 1.3, configuration 4 enforces the namespace **by the search, not by a refusal**
> (ADR-004): "no in-namespace candidate" is a MISS with no candidate and **must not** be coded
> `NAMESPACE`, or a cold cache becomes namespace refusals.

Serves Phase 2 exit clauses 1 (the cascade calls the gate), 2 (every Tier-2 refusal has a cause) and
the "recorded per request" half of 3. The switch itself is item 2.4. Discharges contributions **C1**
and **C3**. `requirements.md` is still empty, so there is no `FR-xx` / `NFR-xx` / `RR-xx` to cite.

## What 2.3 includes that the row does not say

The row reads like a logging change. It is not, because a `SUPPORT` cause cannot exist until
something calls the gate, and nothing does today. So 2.3 is four things:

1. **Wire the gate** into `tryTier2` (`httpapi/cascade.go`), on the candidate that passed
   similarity and namespace. Both arms run, and both values are logged, never summed.
2. **Log the cause and the two support fields** (`telemetry/evallog.go`, `httpapi/handler.go`).
3. **Change §H** (`interfaces.md` v0.12 → v0.13) and add a dated entry to `decisions.md`.
4. **Close the zero-chunk hole** in the cascade: a retrieval with no chunks must not reach a served
   hit (`support.go:157-160`, `support_numeric.go` doc, `approvals.md` of items 2.1 and 2.2).

## Decisions for the author (recommended; confirmed at `/approve`)

These were proposed in chat on 2026-10-14 and are not yet confirmed. They stay changeable until
`design.md` is written.

- **D1. A server that sends chunk IDs with no evidence text** (a pre-1.4 server). Recommended:
  **refuse, with its own cause `NOT_SCORED`**, counted apart from `SUPPORT`, both support fields
  `null`. It follows the numeric arm's fail-closed rule, and item 2.1 forbids calling it
  `SUPPORT` or the gate-off arm. Other option: serve it and mark it.
- **D2. What the cause is when reuse is served, and when no candidate was judged.** Recommended:
  served = **`NONE`**; no candidate judged (cold namespace, search error, embed or retrieve
  failure, empty namespace, zero chunks, Tier-1 hit) = **`null`**. §H contradicts itself today
  (the enum says `NONE`, the example says `null`).
- **D3. The switch.** Recommended: the gate is **always on in 2.3**; item 2.4 adds the switch and
  the off-arm. Other option: add a minimal `Handler` field now.

## Acceptance

Checks that can be run. Handler checks use fakes (no Redis, Ollama or Python), as in
`httpapi/ask_test.go`.

1. **Warranty and paraphrase** (restated 2026-10-14, A1 accepted by the author). Through `Ask`,
   with the fixtures the harness allows:
   - the paraphrase case is a `TIER2_HIT` with cause `NONE` and both support fields non-null;
   - the warranty case is a `MISS` with cause `null`: the namespace search finds no entry in the
     warranty query's namespace, so no candidate is judged and the gate never runs (`impact.md`
     §3.4). It is **not** coded `NAMESPACE` or `SUPPORT`;
   - a separate **synthetic** case reaches `SUPPORT`: an entry seeded in the query's own
     namespace whose answer the evidence does not support. Two of them, one per arm: the lexical
     arm refuses and the numeric arm admits, and the reverse (`impact.md` §3.5).

   The first original wording said the warranty query would be a `SUPPORT` refusal. That was wrong:
   in configuration 4 the namespace closes the measured case before the gate. The arms still
   separate the measured pair on the pinned texts (items 2.1, 2.2, unit level), which is what
   Phase 2 exit clause 1 rests on.
2. **Exactly one cause on every exit of `tryTier2`.** A table-driven test over each exit: cold
   namespace, search error, embed failure, retrieve failure, empty namespace, zero chunks,
   below τ, wrong-namespace candidate, support refusal, served hit. Each gives the cause D2 says.
3. **A cold cache is never `NAMESPACE`.** `NAMESPACE` appears only when a fake store hands back a
   wrong-namespace candidate.
4. **Not scored.** Chunk IDs with `Texts == nil`: not served, cause `NOT_SCORED` (D1), both
   support fields `null`, and never `SUPPORT`.
5. **Zero chunks.** An empty retrieval makes no Tier-2 attempt and serves nothing.
6. **Offline.** A test reads the `requests.jsonl` the logger wrote and tells a `SUPPORT` refusal
   from a `NAMESPACE` refusal by the field alone, and sums the causes to the count of judged
   candidates.
7. **Both arms logged.** On one `SUPPORT` refusal, `support_lex` and `support_numeric_ok` are both
   present and independent (a lexical pass with a numeric refusal, and the reverse).
8. **Regression.** `TestNoThetaSeparatesTheMeasuredPair` still passes; `make verify` exits 0. No
   existing test changes unless an RCA proves it stale and the author confirms (tests are
   immutable).
9. **§H and the log agree.** The `Record` fields match §H v0.13 field for field, and the stale
   statements in §H (the `entered_band` alarm, "equals the TIER2_HIT share") and in
   `cascade.go` comments are restated.
10. **Real answers, plan step 1.** Before any wiring: 10–20 answers the system really generated,
    each scored with `SupportLexical` and `SupportNumeric` against its own retrieval. Record in
    `approvals.md`: the `S_lex` distribution, how often `S_lex < 0.6`, how often the numeric arm
    refuses, and how often it refuses an answer the lexical arm admits. `τ_s` stays 0.6 whatever
    this shows: a bad result is a finding for the author, not a reason to tune.

## Out of scope

- The on/off switch, `support_gate` in the manifest, and the off-arm writing `null` (item 2.4).
- Putting θ into the served rule (F-K). `CONTAINMENT` stays in the enum and is not reachable
  until F-K has an owner. §H says so.
- Configuration 3's served path, the static-cache arm, the 3 ⋈ 4 join.
- Any change to `τ_s`, the stopword list, the numeric rules R1–R9, or the unit list.
- Trying a second candidate when the first is refused (the search stays `k=1`).
- Any ML on the hit path, and anything from the do-not-reinstate list.
- The Phase 2 exit-line wording fix (recorded for 2.4).
