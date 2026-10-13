# Design review — lexical support arm (item 2.1)

Reviewer: `design-reviewer` subagent (opus), reviewing `design.md` against `spec.md`, `impact.md`,
and the existing code (`rule.go`, `lane.go`/`lane_test.go`, `ragclient/retrieve.go`,
`httpapi/cascade.go`, `architecture.md` §2, `super-plan.md` Phase 2, `Final_Proposal.md`).

**Verdict: sound with changes.** The reviewer independently re-derived the fixture arithmetic and
confirmed it holds, confirmed `reuse/` stays infrastructure-free and a leaf, confirmed the query
text is never read, and confirmed nothing here forecloses 2.2/2.3/2.4 except as noted below. Eight
findings, each with a resolution recorded here. Full review text kept in this task's run log; this
file carries the findings and what was done about each.

## Findings and resolutions

1. **The fixture proves the formula, not the measured case — its verdict is governed by a
   shared-vocabulary ratio the design didn't name.** Because the product chunks are identical in
   both evidence sets, the refusal only holds while non-discriminating (spec) tokens stay a
   minority of the answer's content tokens; a spec-heavier answer to the same question, or a
   retrieval that returns *both* category policies at once (`lane.go:174-177` documents this
   happens on dev-v0), would score above `τ_s` and admit the warranty question. This is a real
   fragility, not a design error — but the design should disclose it rather than imply the gate
   is robust on this case generally.
   **Resolution: adopted.** Two more tests added to `support_test.go` (plan.md step 4), each
   documented as a pre-registered limitation feeding RQ2a (`super-plan.md` item 6.4), not as a
   defect: both-policies-retrieved saturates the score back above `τ_s`; a spec-heavy answer to
   the same question is admitted against the warranty evidence. The required Done-when test
   (item 2.1's own pinned pair) is unchanged — these are additional, explicitly-labelled tests.

2. **`(score float64, scored bool)` is droppable with `_`, and dropping it reproduces exactly the
   misattribution item 2.1 forbids** (a stale server scores `0 < τ_s`, becomes `refusal_cause =
   SUPPORT`). `NamespaceDecision` already exists in this package for the analogous reason — "a run
   can carry BOTH verdicts and neither can be mistaken for the other" (`lane.go:236-238`).
   **Resolution: adopted.** Return a single `SupportVerdict` struct (`Scored bool`, `Score
   float64`, `ContentTokenCount int`) instead of a tuple. The zero value reads correctly as "not
   scored"; dropping it with `_` is no longer silent since there is one value to drop, not one of
   two. `ContentTokenCount` also answers finding 5.

3. **`τ_s = 0.6` transferring to this system's own generated answers is reasoned, not measured** —
   the denominator is the answer's own content tokens, so a verbose or hedging answer is penalised
   in a way the terse fixture answer is not, and a pinned, unsweepable threshold cannot correct for
   it later.
   **Resolution: deferred, recorded as a follow-up, not blocking 2.1.** This needs ~10-20 real
   generated answers scored against their own retrieval, which needs the live pipeline (green
   pressure) — out of proportion to a pure-function unit's scope. Recorded in `approvals.md` as a
   required check **before item 2.3** wires this to anything served.

4. **The stopword list should be a named, versioned external list, not hand-curated** — `τ_s`
   cannot move, so the list is the de-facto free parameter carrying the same leverage, and
   `Final_Proposal.md`:186's own argument against hand-tuning a threshold applies equally to a
   hand-tuned list.
   **Resolution: adopted.** Switched to Lucene's `StopAnalyzer.ENGLISH_STOP_WORDS_SET` (33 words,
   a long-stable, versioned, public-domain list), cited by name and source in the code comment.
   Recomputed the fixture arithmetic against it (design.md, updated): paraphrase 14/16 ≈ 0.875,
   warranty 5/16 ≈ 0.3125 — both tokens `"has"` and `"within"` that the hand-curated list had
   removed are content tokens under Lucene's shorter list, which **adds** `"within"` as a thirteenth
   paraphrase match (it appears in the real `policy-returns-electronics` text) without changing
   either verdict. Still a wide margin on both sides.

5. **No granularity note, and short answers behave as "every token must match."** `Overlap` carries
   this warning for chunk-ID overlap (`rule.go:19-21`); `support.go` needs its analogue, and without
   the token count in the return value a refusal caused by a two-token answer is indistinguishable
   from one caused by genuinely mismatched evidence.
   **Resolution: adopted**, via `SupportVerdict.ContentTokenCount` (finding 2) plus a doc comment
   on `SupportLexical` stating the resolution is `1 / ContentTokenCount` and that a short answer is
   refused far more easily than a long one — the same shape as `Overlap`'s top-k granularity note.

6. **Do not export `ContentTokens`/`TextTokens`** — the design's own "should 2.2 reuse these"
   question is answered no: the numeric arm must match literals **and units**, and both the
   ≥3-character rule (drops `"30"`, `"14"`) and the set-over-the-union shape (cannot tell `"1800 W"`
   in one chunk from `"1800"` in one and `"W"` in another) would silently hand 2.2 a wrong verdict.
   **Resolution: adopted.** Both tokenizer functions stay unexported. Exported surface is
   `SupportVerdict`, `SupportLexical`, `TauSupportLexical` only. A comment on the unexported
   tokenizer says why 2.2 must not reuse it.

7. **The tokenizer's normalisation (ASCII-only case fold + split) was never recorded as part of
   `S_lex`'s frozen definition**, as `impact.md`'s lead risk asked for, and only four of five
   paraphrase-evidence texts were quoted verbatim in `design.md` (`product-headphones-02` was
   described, not quoted).
   **Resolution: adopted.** `approvals.md` now records the stopword list, the ≥3-character rule,
   AND the normalisation rule (lowercase, split on `[^a-z0-9]+`, ASCII-only — a deliberate
   divergence from `cache.Normalize`, which keeps Unicode letters and does not split on punctuation)
   as one frozen artefact, with its source. `design.md` now quotes all five product chunks and both
   policy chunks verbatim, with a checksum per string so the transcription is auditable without
   re-reading `data/`.

8. **Smaller items**, each resolved as noted:
   - `cascade.go:45-47`'s comment ("while the served rule is similarity AND namespace") will go
     stale once item 2.3 wires the gate in. **Added to 2.3's forward list in `approvals.md`** —
     not this item's to fix, since this item does not touch `cascade.go`.
   - **`support_lex`'s denominator is Tier-2 hits only** (the gate never runs without a retrieval,
     and only Tier-2 candidates retrieve). **Added to 2.3's forward list** for whoever writes that
     metric's definition.
   - **`BenchmarkSupportLexical`, adopted** — turns `Final_Proposal.md`:168's "microseconds" claim
     from reasoned into measured, for free, inside this item's own test file (plan.md step 6).
   - **A test pinning the stopword list's length and a checksum, adopted** — an accidental future
     edit to the list fails a test instead of silently rescaling every score it touches
     (plan.md step 5).
   - **`scored == true, score == 0` on an empty retrieval closes an existing hole**
     (`cascade.go:81` checks `retrieved == nil` but not `len(ChunkIDs) == 0`, and the spec lane's
     namespace falls back to `productID` regardless) — **noted in design.md as a deliberate,
     claimed behaviour**, not an accidental side effect, so item 2.3 states it rather than
     rediscovering it.

## On authoring the cached-answer sentence

The reviewer found this legitimate — the authored side is constrained to vocabulary the real
documents already fix, and the margin is wide enough that no plausible rewording flips it — but
flagged that the design should not call the result a regression **on the measured case**, since no
answer text was ever captured for it. **Resolution: adopted.** The test's doc comment (plan.md
step 3) states plainly that the answer is authored under stated constraints and that the test pins
the *formula's* behaviour on real evidence, not a captured measurement — and names the alternative
(re-running the question through the live pipeline to capture a real answer) and why it wasn't
taken here: it would cost a green-pressure generation and introduce the Modelfile's
`temperature 1` non-determinism (super-plan.md, "Generation determinism (U8)", still open) into a
fixture that is supposed to be exactly reproducible.

---

# Code review of the implementation (`/ai-review`, 2026-10-12)

Reviewer: `contract-reviewer` subagent, general pass (the diff touches the Go↔Python seam in a test,
reads the Redis `corpus::` schema, and adds a `reuse/` primitive). Routed there because the
`design-reviewer` row of `/ai-review` is for a design *before* implementation, which `## Findings
and resolutions` above already covers. Scope: `reuse/{support.go,support_test.go,doc.go}`,
`ragclient/support_live_test.go`, `Makefile`. The reviewer's report is model output; every citation
it relied on was re-checked against the source before acting (results inline). Mutation testing was
denied to the reviewer by the permission system, so finding 4b was by reading; it has since been
mutation-checked by the main session.

**Verdict: no finding changes behaviour as it stood; one is a latent hazard for item 2.3 (finding 1),
the rest overstate what the code or tests guarantee, plus one record gap (4a).** Checked and found
sound: `reuse/` imports only `strings` and stays a leaf (the test-time edge `ragclient_test → reuse`
is allowed, `architecture.md` §2 calls the graph "an observation, not a rule"); the live test reads
`corpus::<chunk_id>` field `text` in DB 0 with only `PING`/`HGET`, so no `t1:`/`t2:`/`dep:`/`entry:`/
`lru:`/`dataset:epoch` key is touched and a missing key cannot pass as `""`; all seven fixture
checksums reproduce from live Redis independently of the test; the stale-server vs empty-retrieval
split matches `ragclient/retrieve.go`; `TauSupportLexical` is a const, the admit boundary is
inclusive as the proposal states, the list is exactly Lucene's 33 words, the query text is never
read; the `support-check` startup block is identical to `seam-check`'s, which is unchanged; nothing
touches `cascade.go`, `telemetry/`, `interfaces.md`, the numeric arm or `refusal_cause`.

## Findings and resolutions

1. **[CONFIRMED] `support.go`, `SupportVerdict` doc: "a caller that forgets to check `Scored` gets the
   safe default" is false.** A caller who writes `v.Score < TauSupportLexical` compiles, and on an
   unscored verdict (`Score` 0) it is true: the stale server becomes a SUPPORT refusal, the exact
   misattribution the struct was adopted to prevent. The struct only stops `score, _ :=`.
   **Resolved: fixed.** Added `func (v SupportVerdict) Refuses() bool { return v.Scored && v.Score <
   TauSupportLexical }` as the one sanctioned way to get a refusal, with a doc comment saying an
   unscored verdict neither refuses nor admits (so `!v.Refuses()` is NOT "may reuse") and that
   `Score` is meaningless unless `Scored`. `TestSupportVerdictRefuses` pins it, including the
   unscored row; two mutants (drop the `Scored` check; `<=`) are killed. This extends the exported
   surface recorded under finding 6 above (`SupportVerdict`, `SupportLexical`,
   `TauSupportLexical`) by one method. **Alternative not taken:** `Score = NaN` when unscored, so a
   JSON log fails loudly. It would change the documented meaning of `Score` and the zero value; the
   method does the job without that. **Forward note for item 2.3:** the cause-code branch must call
   `Refuses()`, never compare `Score`; nothing enforces that until 2.3 exists.

2. **[CONFIRMED] `ragclient/support_live_test.go`: the live test asserts nothing about the verdicts,
   and its one score assertion could never fire.** Both queries are product-scoped, and
   `retrieve.py:_drop_other_products` removes every other product's chunk, so a live set can never
   equal `lane_test.go`'s pinned sets (they contain products 04, 09 and 01/02). The `sameIDSet`
   branch, the pinned-ID slices and the two pinned scores were dead code; the subtests' names read
   as if they checked the verdicts; the `make` PASS line would print for any retrieval.
   **Resolved: fixed.** Removed the dead branch and constants (a deviation from `plan.md` step 8b
   item 3, which specified the conditional check; it cannot fire). The header now has a "WHAT A PASS
   MEANS" paragraph: the pass means Redis text = fixture text, aligned texts came back, and
   `SupportLexical` scored both retrievals; verdicts are **logged, not asserted**. The observed
   2026-10-12 values are recorded there labelled "observed, not predicted, not pinned". The `make`
   PASS line now says "Verdicts are LOGGED, not asserted." The queries were not changed. **Not
   done:** asserting the observed directions (would turn a non-measurement into a regression pin on
   retrieval behaviour, after seeing the result) and an unscoped variant (a plan change).

3. **[CONFIRMED] The two "disclosed fragility" tests were filed under RQ2a, and they are not RQ2a.**
   `Final_Proposal.md` RQ2a (line 355) and `super-plan.md` 6.4 define it as the query and the entry
   retrieving the **same** evidence and differing only in the condition asked about. In
   `TestSupportLexicalAdmitsWhenBothPoliciesRetrieved` the evidence is a superset of the warranty set
   plus the returns policy; in `TestSupportLexicalAdmitsASpecHeavyAnswer...` the cached answer is a
   different document from the entry's. Both are false hits the gate lets through **in its own
   domain** ("the wrong document"), and in a run they would count **inside** the headline false-hit
   rate, not beside it as RQ2a is. The "not contrived" claim cited `lane.go:174-177`, which says only
   that a **return** query retrieves both return policies; nothing in this repo shows a warranty
   query retrieving the returns policy. Re-checked against `lane.go` and the proposal: the reviewer
   is right on all three points. **Resolved: fixed.** Test comments now say these are limitations of
   the lexical arm in its own domain that bound how often it catches the wrong document, not RQ2a,
   and that the both-policies evidence is a constructed union. `design.md` carries a correction
   (below); this file's finding 1 above, which says "feeding RQ2a", is left as the historical
   record and superseded here. **Consequence worth stating:** the false-hit rate the headline
   reports must include cases of this shape.

4. **[CONFIRMED] 4a. The new frozen definition is recorded in `approvals.md` only.** `decisions.md`'s
   inherited frozen-values table has the row "Support-gate threshold `τ_s = 0.6` … taken from the
   published value" and nothing for the stopword list, the length rule, the ASCII tokenizer or
   no-stemming, though comments and test messages in the code say a change "takes a numbered
   `decisions.md` entry". The `τ_s` row also implies the published value transfers to this
   tokenizer; nothing says it does, and nothing says GroundedCache used Lucene's list (the proposal
   says only "a fixed stopword list"). **RESOLVED 2026-10-12 by the author's choice of option (a).** `CLAUDE.md` names `approvals.md`
   as "the only record" of a frozen change, and also says frozen values are resolved from
   `decisions.md`, so both readings are defensible and the decision log is the author's. Options:
   (a) one pointer row in the frozen table (value, why it is frozen, "added by item 2.1, not
   pre-thesis", `τ_s` transfer **assumed**); (b) a numbered ADR; (c) leave it in `approvals.md`.
   Asked via the question tool; the author chose (a). **Done:** one row added to `decisions.md`'s
   inherited frozen-values table, directly under the `τ_s` row: the definition, why it is frozen,
   "Added 2026-10-12 by item 2.1, not pre-thesis", that the proposal specifies only "a fixed
   stopword list" so Lucene's is this thesis's choice, and that the `τ_s = 0.6` transfer is assumed,
   not measured. `decisions.md` also holds unrelated uncommitted edits (ADR-007/008) from another
   task, so that file needs a partial commit or a separate one.
   **4b. [PLAUSIBLE, by reading → now confirmed by mutation] the claim that
   `TestSupportStopwordsArePinned` "fails on any change" overstated it:** it pins the list only;
   apostrophes and underscores (the corpus has `buyer's`, `water_resistance`) were unpinned.
   **Resolved: fixed.** Two cases added to `TestContentTokensRules`; both "treat `_` / `'` as a word
   character" mutants are killed; the `support.go` comment now says which test pins what.

5. **[PLAUSIBLE] `SupportLexical`'s `chunkIDs []string` does not say it must be the fresh
   retrieval's.** `entry.SourceChunkIDs` has the same type and is never empty; passing it compiles
   and turns an empty retrieval into "unscored" instead of "scored 0", silently reopening the hole
   the design claims to close. **Resolved: fixed.** Parameter renamed `retrievedChunkIDs`; the doc
   says "never the cached entry's `source_chunk_ids`" and why. No behavioural change, no caller yet.

6. **[CONFIRMED] Doc statements the source does not support.**
   (a) `support.go` said the `len(chunkIDs) > 0` rule is "as interfaces.md B says"; `interfaces.md`
   does not say it (re-checked by grep). It is in `ragclient/retrieve.go` (`RetrieveResult.Texts`)
   and `super-plan.md` item 2.1. **Fixed** in `support.go`'s comments; `design.md` repeats the wrong
   attribution ("interfaces.md's own words") and carries a correction.
   (b) The live test said the answer checksum is "pinned so a drift between the two copies fails
   here". It catches an edit to the live copy only; editing `cachedAnswer` and its checksum together
   in `support_test.go` passes. The seven chunk checksums are also duplicated by hand. **Fixed** by
   rewording the comment to say exactly that; no mechanism can share them (a test file's names are
   not importable), so this is accepted.
   (c) `TestSupportLexicalSeparatesTheMeasuredPair`'s "this one shows the text can" overstated an
   authored answer. **Fixed:** the comment now says what it shows and that the Phase 2 exit clause
   ("the gate refuses the measured warranty case") is **not** discharged by this fixture; the check
   on answers the system really generated is the deferred follow-up in `approvals.md`.

7. **[CONFIRMED, low] Trail and doc drift.** `design.md` says "No other file changes" but step 8b
   added `ragclient/support_live_test.go` and a `Makefile` target (only `impact.md` carried an
   Amendment); `architecture.md` called `seam-check` "the one live check" and listed the support
   gate as simply "not built". **Resolved: fixed.** `design.md` amended; `architecture.md`'s file
   tree line, "Check the code" row and "Not built" row updated (three lines). `architecture.md` §4
   describes `seam-check`/`support-check` only in that one row.

**Unrelated working-tree changes** (reviewer's note, confirmed by `git status`): `docs/decisions.md`
(ADR-007/008) and `docs/work/2026-10-10-redis-as-sole-store/` are not part of this task. Keep them
out of this task's commit.

**Status:** every finding is fixed, including **4a** (resolved by the author's choice, above). No finding is open.
After these fixes `make verify` was re-run (exit 0, 0 SKIPPED), the Go tests re-run uncached, and
`make support-check` re-run on the edited live test (2026-10-12, memory pressure level 1; it had been
held back while pressure was level 2): PASS, fidelity PASS, same live sets and scores as before
(paraphrase-query `[product-headphones-03, policy-returns-electronics]` 0.8750; warranty-query
`[product-headphones-03, policy-warranty]` 0.3125), no listener left on `:50052`.
