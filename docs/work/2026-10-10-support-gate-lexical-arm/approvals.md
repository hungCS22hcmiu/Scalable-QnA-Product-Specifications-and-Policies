# Approvals — support-gate-lexical-arm

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | yes      | 2026-10-12 | — (no frozen value touched; `τ_s = 0.6` is already frozen as inherited state, `decisions.md:68` — this item does not create that pin, only consumes it. No `run_id` invalidated: none exist, and the served Tier-2 decision in `cascade.go` is untouched, `impact.md` §2) |
| contract       | if §B/§D | not required | — | `support_lex`/`support_numeric_ok`/`refusal_cause` are already specified in `interfaces.md` at v0.9 (`impact.md` §5); this item adds no wire-format surface and does not wire into the cascade |
| experiment     | if measured | not required | — | `telemetry/` and `experiments/` unchanged (`impact.md` §6) |
| implementation | always   | yes      | 2026-10-12 | — (over `plan.md` as amended, i.e. including step 8b; no frozen value touched, no run invalidated). **Implemented 2026-10-12, `make verify` exit 0.** `BenchmarkSupportLexical` ≈ 15.9 µs/op (steady state, M1, 286 allocs; cold 1×: 62 µs). `make support-check` PASS, pressure level 1 (yellow, recorded not gated), log kept only in the session scratchpad (not durable); the facts are here and in `plan.md` "Implementation notes". Live sets: paraphrase-query `[product-headphones-03, policy-returns-electronics]` S_lex 0.8750 ADMITS; warranty-query `[product-headphones-03, policy-warranty]` S_lex 0.3125 REFUSES. Both differ from `lane_test.go`'s pinned 5-chunk sets (scoped retrieval drops other products' chunks), so the pinned-score assertion did not apply |

**Amendment after the impact approval (2026-10-12):** the author asked for a live check against the
real retrieval service and said "yes" to adding it as `plan.md` step 8b. That adds a test-only file
in `ragclient/` and a `Makefile` target, which `impact.md` (as approved) did not cover; `impact.md`
now carries an Amendment section describing it. The first `/approve impact` (earlier on
2026-10-12) predated that amendment; **the author re-ran `/approve impact` after the amendment was
written, so the approval above now covers step 8b** (see Human decisions). No frozen value is
touched either way.

## Frozen artefact recorded by this item

`impact.md`'s lead risk: once any run logs `support_lex`, the stopword list and the tokenizer's
normalisation rule become part of `S_lex`'s definition exactly as much as `τ_s` is, and `τ_s`
cannot move to compensate for a later edit to either. Recorded here, not only in `design.md` and
`support.go`'s comments, so a future change to either is a decision against a stated prior rather
than a silent edit:

- **Stopword list**: Lucene's `StopAnalyzer.ENGLISH_STOP_WORDS_SET`, 33 words, transcribed
  verbatim (not imported) in `gateway/internal/reuse/support.go` — `a, an, and, are, as, at, be,
  but, by, for, if, in, into, is, it, no, not, of, on, or, such, that, the, their, then, there,
  these, they, this, to, was, will, with`.
- **Length rule**: tokens shorter than 3 characters are dropped (super-plan.md item 2.1's own
  wording).
- **Normalisation**: lowercase, then split on runs of non-`[a-z0-9]` characters — ASCII-only, and
  deliberately **not** the same rule as `cache.Normalize` (which keeps Unicode letters and strips
  punctuation without splitting). `design.md` Named decision 6 and `review.md` finding 7.
- **No stemming.** `"return"`/`"returns"`/`"returned"` are three distinct tokens.

A change to any of the four invalidates every `support_lex` value logged before it, the same way a
change to `τ_s` would — if one is ever needed, it takes a numbered `decisions.md` entry stating
that, per standing constraint 5.

## Human decisions

| Date | Decision | Author's words | Invalidates |
| :--- | :--- | :--- | :--- |
| 2026-10-10 | **Open item 2.1 at scope L** (`/task support-gate-lexical-arm L`) | — (slash command) | — |
| 2026-10-10 | **Fixture text source: grant a one-time `Read(./data/**)` exception** rather than have the author paste chunk text or accept synthetic prose, so the test fixture could be built from the real dev-v0 corpus instead of invented sentences | Chose *"Grant a one-time read exception"* | — |
| 2026-10-12 | **`/approve impact`** — impact.md accepted: only `reuse/` touched, no frozen value changed, `τ_s = 0.6` consumed not created, no run invalidated. The stopword list / length rule / normalisation are recorded above as the frozen artefact this item creates | — (slash command) | — |
| 2026-10-12 | **Add a live check against the real retrieval service** as `plan.md` step 8b, after asking whether the plan had any curl / real-server test | Asked *"does the current plan have any CURL test … real request to the system?"*, then answered *"yes"* to adding step 8b | — |
| 2026-10-12 | **`/approve implementation`** — unlocks `gateway/internal/reuse/{support.go,support_test.go,doc.go}`, `gateway/internal/ragclient/support_live_test.go` and the `Makefile` `support-check` target, per `plan.md` steps 1-9 incl. 8b. Given after being told the earlier `/approve impact` did not cover 8b; the impact re-approval followed (next row) | — (slash command) | — |
| 2026-10-12 | **`/approve impact` (second time)** — re-run after `impact.md` gained its step-8b Amendment (test-only `ragclient/support_live_test.go`, `Makefile` `support-check`, test-time edge `ragclient_test → reuse`; `reuse/` still a leaf). `impact.md` re-checked: the Amendment section is present and states no frozen value touched, no run invalidated. The Amendment was written by the main session, not `impact-analyst` — the author's approval is the review it received | — (slash command) | — |
| 2026-10-12 | **`/ai-review` finding 4a: record the `S_lex` definition as a pointer row in `decisions.md`'s frozen table** (the alternatives offered were a numbered ADR, or leaving `approvals.md` as the only record) | Chose *"Pointer row in the frozen table (Recommended)"* | — |
| 2026-10-12 | **`/done`** | — (slash command) | — |

**Correction to this ledger:** the impact row above read `yes · 2026-10-10` from the moment this
file was first written, i.e. before the author had run `/approve impact`. That was a premature
record — the approval is the 2026-10-12 `/approve impact` line in the table above, and the row now
carries that date. Nothing was built on the earlier entry (no source edit has occurred; implementation
is still locked).

The exception was opened in `.claude/settings.json` (removing the `Read(./data/**)` deny entry),
the seven needed `data/dev-v0/*.json` files were read, and the entry was restored immediately
(`git diff` against the committed file was empty afterward — confirmed before continuing). The
texts captured from that read are quoted verbatim, with SHA-256 prefixes, in `design.md`'s "The
pinned fixture".

## Recorded follow-ups (not blocking this item)

- **Before item 2.3 wires this gate to anything served**: measure `S_lex(answer, its own
  retrieval)` over ~10-20 real dev-v0 generated answers and record the distribution here, to check
  whether `τ_s = 0.6` — pinned against the answer's own content-token count — is safe for this
  system's actual (verbose, sometimes hedging) answers, not just the terse fixture answer in this
  item's test (`review.md` finding 3; `design.md` "Residual open items").
- **For item 2.3**: `cascade.go:45-47`'s comment ("while the served rule is similarity AND
  namespace") goes stale once the gate is wired in; `support_lex`'s denominator in any aggregate
  reporting is Tier-2 hits only, since the gate never runs without a retrieval (`review.md`
  finding 8; `design.md` "Residual open items").

## Open — needs the author

Impact (including the step-8b Amendment) and implementation are both approved. `/ai-review` also
added `(SupportVerdict).Refuses()` to the exported surface (`review.md`, finding 1), after the
impact approval; it adds no import edge, file or frozen value.

## Status (2026-10-12, closed)

- Approved by the author: **impact** (2026-10-12, re-run to cover the step-8b Amendment),
  **implementation** (2026-10-12).
- `READY_TO_IMPLEMENT` written at approval, **deleted by `/done`**; the gate is re-locked.
- Done: `SCOPE` (L), `spec.md`, `impact.md` (delegated to `impact-analyst`), `design.md` (three
  revisions: initial, after `impact.md`, after `review.md`), `review.md` (delegated to
  `design-reviewer`, opus: **sound with changes**, 8 findings, all 8 resolved into `design.md`
  and this file), `plan.md`.
- Done: plan.md's steps 1-9 (incl. 8b), `/verify`, `/ai-review`, `/done`. Record in the
  implementation row, when done: the `BenchmarkSupportLexical` number (step 7) and the `make
  support-check` log path, live ID sets and scores (step 8b).
