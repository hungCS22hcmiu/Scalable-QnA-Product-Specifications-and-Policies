# Design — lexical support arm (item 2.1)

## What this adds, and where

One new file, `gateway/internal/reuse/support.go`, plus `gateway/internal/reuse/support_test.go`.
No other file changes. *(Amended 2026-10-12: plan.md step 8b, added after the design review, also adds a
test-only `ragclient/support_live_test.go` and a `Makefile` `support-check` target — see `impact.md`'s
Amendment — and the code review changed this design in the ways listed under "Corrections after code
review" at the end of this file.)* `reuse/` stays infrastructure-free (`architecture.md` §2: "no import beyond
the standard library and no I/O") and stays a leaf in the import graph (`architecture.md`:134 —
`reuse/` imports none of its siblings, not even `ragclient`). That rules out taking a
`*ragclient.RetrieveResult` as a parameter; the function reads plain `string`/`[]string`, the same
shape `Overlap` already takes `[]string` chunk IDs rather than a richer retrieval type.

This mirrors the existing split in the package: `rule.go` holds the containment score (`Overlap`)
and its threshold application (`Thresholds.Decide`); `lane.go` holds the namespace rule. `support.go`
holds the lexical-support score and its pinned threshold, as a third, independent primitive. It is
**not** called from `httpapi/cascade.go`'s `tryTier2` by this item (spec.md, Out of scope) — that
wiring needs a cause code to log the refusal under (item 2.3) and a place to turn the arm off
(item 2.4), neither of which exists yet.

`gateway/internal/cache/normalize.go` already tokenizes text for a different purpose (the Tier-1
cache key) and is deliberately guarded against stemming or stopword removal
(`TestNormalizeDoesNotStemOrDropStopwords`, per `impact.md` finding 7) — the two tokenizers must
stay separate functions with no shared helper, since conflating them would either weaken the cache
key's normalization or quietly add stemming to the support gate. `support.go`'s tokenizer is new
and private to `reuse/`; it does not touch `cache/` at all.

`gateway/internal/reuse/doc.go`'s package comment ("the source-overlap reuse rule and the
cascade") gets one added clause naming the support gate, per `impact.md` finding 7 — a one-line
edit, in plan.md below.

## Function contracts

**Revised after design review** (`review.md` findings 2, 5, 6): the first draft returned a bare
`(float64, bool)` tuple and exported both tokenizers. Both changed.

```go
// contentTokens splits s into lowercase tokens, drops the stopword list (support.go's package
// var, see "Named decisions" §3), and drops tokens shorter than three characters. The result is a
// SET (deduplicated) -- see "Set, not multiset" below. Unexported: item 2.2's numeric arm must
// NOT reuse this. It drops 1- and 2-digit numbers on the length rule -- exactly the tokens a
// numeric-literal check exists to compare ("30", "14") -- and would hand 2.2 a silently wrong
// verdict (review.md finding 6).
func contentTokens(s string) map[string]struct{}

// textTokens splits s into lowercase tokens with no filtering -- the evidence side, which the
// formula leaves unfiltered ("tokens(C)", not "content-tokens(C)"). Still a set, for membership
// testing. Unexported for the same reason as contentTokens: it is a set over the UNION of every
// retrieved chunk, which cannot tell "1800 W" in one chunk from "1800" in one chunk and "W" in
// another -- 2.2 needs its own, unit-aware tokenizer, not this one.
func textTokens(s string) map[string]struct{}

// SupportVerdict is the lexical arm's result. A struct, not a (float64, bool) tuple, so that
// discarding the safety-relevant field takes an explicit `_` on a NAMED field a reader can see,
// not a positional return a caller can drop without noticing (review.md finding 2; the package's
// own precedent is NamespaceDecision, kept separate from Decision for exactly this reason,
// lane.go:236-238).
type SupportVerdict struct {
	// Scored is false exactly when the caller could not score at all: the RAG service sent chunk
	// IDs with no evidence text (a stale pre-1.4 server, interfaces.md B v0.9). super-plan.md item
	// 2.1 requires this NOT be scored, NOT be refused as SUPPORT, and NOT be logged as the
	// gate-off arm -- each would misattribute a stale server to the gate. The zero value of
	// SupportVerdict has Scored == false, so a caller that forgets to check it gets the SAFE
	// default (unscored), not a silently-passing or silently-failing score.
	Scored bool
	// Score is S_lex(a, C) -- meaningful only when Scored is true. 0 when the retrieval
	// legitimately returned nothing (len(chunkIDs) == 0): there is no evidence to support
	// anything, which is a real verdict, not a missing instrument. Also 0 when the answer itself
	// has no content tokens, matching Overlap's "no recorded provenance scores 0" convention.
	Score float64
	// ContentTokenCount is |content-tokens(a)|, the formula's denominator. Exists so a refusal
	// caused by a two-token answer (resolution 1/ContentTokenCount -- a single mismatch refuses)
	// is distinguishable from one caused by genuinely mismatched evidence, the same reason
	// Overlap's top-k granularity is called out (rule.go:19-21; review.md finding 5). 0 when
	// Scored is false.
	ContentTokenCount int
}

// SupportLexical computes the lexical support gate's verdict for one (answer, evidence) pair:
// S_lex(a,C) = |content-tokens(a) ∩ tokens(C)| / |content-tokens(a)|, C the union of texts'
// elements -- or reports it could not score at all. chunkIDs is consulted ONLY to tell a stale
// server apart from a legitimately empty retrieval (interfaces.md's own words: "key on
// len(ChunkIDs) > 0, since an empty retrieval is nil too") -- it is never scored over.
//
// This disambiguation is folded INTO reuse/ rather than left for httpapi to reimplement at the
// call site (item 2.3): it is the one tricky rule item 2.1 names, so it gets its own unit test
// here instead of being exercised only once, indirectly, inside a later httpapi integration test
// (impact.md finding 1). Threading chunkIDs through costs nothing architecturally -- it is a
// []string, the same shape Overlap already takes, so reuse/ stays a leaf (architecture.md §2).
func SupportLexical(answer string, texts []string, chunkIDs []string) SupportVerdict
```

```go
// TauSupportLexical is the lexical support gate's threshold, pinned at the value GroundedCache
// published and never swept (decisions.md's inherited frozen-values table; Final_Proposal.md §5 C1:
// "sweeping it would turn an adopted mechanism into a tuned one"). It is a standalone constant,
// not a field on Thresholds, because Thresholds' own doc comment says its fields "are swept, never
// hand-set, for anything reported" -- folding a pinned, never-swept value into that struct would
// misstate it on sight. (impact.md finding 2 confirms: a Thresholds field would invite a
// getenvFloat wire-up in cmd/gateway/main.go:175-177, making a never-swept value sweepable.)
const TauSupportLexical = 0.6
```

A caller that wants the boolean verdict today writes `v.Scored && v.Score >= TauSupportLexical`
inline, exactly as `Thresholds.Decide` compares `similarity >= t.Tau` inline rather than through a
helper. `interfaces.md` §H logs `support_lex` as the raw float (`"support_lex": 0.21`), not a
boolean, so this item still produces no combined pass/fail type for the gate overall -- that
waits for item 2.3, which combines this arm with the numeric arm's (2.2) into one cause code.

## Sequence (for context only — not built by this item)

```
httpapi.tryTier2                              reuse (this item, unwired)
    |                                                |
    | has retrieved.Texts, retrieved.ChunkIDs,
    | c.Entry.Answer
    |---- (item 2.3, later) ----------------------->  SupportLexical(c.Entry.Answer,
    |                                                       retrieved.Texts, retrieved.ChunkIDs)
    |                                                |
    |<-----------------------------------------------  SupportVerdict
    | (item 2.3) !v.Scored -> count the stale-server condition, no verdict
    |             v.Scored && v.Score < TauSupportLexical -> refusal_cause = SUPPORT
```

One claimed behaviour worth stating plainly, since it falls out of this design rather than being
built on purpose: `v.Scored == true, v.Score == 0` on a legitimately empty retrieval closes a hole
that exists in the cascade TODAY. `cascade.go:81` checks `retrieved == nil` but not
`len(retrieved.ChunkIDs) == 0`, and `Namespace`'s spec lane falls back to the request's own
`productID` regardless of what retrieval returned — so a zero-chunk retrieval can currently reach a
namespace, a candidate, and a served hit with no evidence behind the decision at all. Once wired
(item 2.3), this gate refuses that case outright. Item 2.3 should claim this deliberately rather
than rediscover it as an accidental side effect.

2.1 delivers only the right-hand column, proven by its own test inside `reuse/`.

## The pinned fixture

`impact.md` (finding 7) raised the right objection to my first draft here: `TestNoThetaSeparatesTheMeasuredPair`
pins the *real* dev-v0 chunk IDs for this case, and authoring prose freely until it happens to clear
or miss `τ_s = 0.6` is the "tune to make a headline work" failure mode even inside a unit test. The
fix is to read the real chunk text the IDs name (`data/dev-v0/`, via a one-time, user-approved
exception to the repo's `Read(./data/**)` deny rule, reverted immediately after) and derive the
score from that, rather than invent sentences to order. The design review (`review.md` finding 7)
caught that the first draft of this section quoted only four of five product chunks; all five are
quoted verbatim below, each with a SHA-256 prefix so the transcription is auditable without
re-reading `data/`.

**The evidence side is 100% real**, rendered through the actual ingestion template
(`rag/src/rag/ingest.py:47-55`, `product_to_text` / `policy_to_text`) applied to the real JSON:

```
product-headphones-01.json ("SoundMax ANC Pro")                          sha256:82b972cc13fa…
  Product: SoundMax ANC Pro
  Category: headphones
  Specs:
  - type: over-ear
  - anc: yes
  - battery: 40 hours
  - connectivity: Bluetooth 5.3, 3.5mm
  - weight: 250g
  - mic: yes

product-headphones-02.json ("SoundMax ANC Lite")                         sha256:4bbdd773b369…
  Product: SoundMax ANC Lite
  Category: headphones
  Specs:
  - type: over-ear
  - anc: yes
  - battery: 30 hours
  - connectivity: Bluetooth 5.2
  - weight: 220g
  - mic: yes

product-headphones-03.json ("EarBuds Pop 3")                             sha256:c42b901cdd3b…
  Product: EarBuds Pop 3
  Category: headphones
  Specs:
  - type: in-ear true wireless
  - anc: no
  - battery: 6 hours (24 with case)
  - connectivity: Bluetooth 5.3
  - weight: 5g each
  - mic: yes

product-headphones-04.json ("EarBuds Pop 3 Pro")                         sha256:d9f62f2671ec…
  Product: EarBuds Pop 3 Pro
  Category: headphones
  Specs:
  - type: in-ear true wireless
  - anc: yes
  - battery: 8 hours (32 with case)
  - connectivity: Bluetooth 5.3
  - weight: 6g each
  - mic: yes
  - water_resistance: IPX4

product-headphones-09.json ("Conference Buds")                           sha256:60cc39d00c83…
  Product: Conference Buds
  Category: headphones
  Specs:
  - type: in-ear true wireless
  - anc: yes
  - battery: 5 hours (20 with case)
  - connectivity: Bluetooth 5.3
  - weight: 4g each
  - mic: dual-array noise-cancelling

policy-returns-electronics.json, full text                               sha256:4fc52aed4784…
  Return Policy — Electronics (Laptops, Headphones)

  Items in the laptops and headphones categories may be returned within 30 days of delivery
  for a full refund, provided the item is unused, in original packaging, and all accessories
  are included. Opened software licenses and consumable accessories (ear tips, cables sold
  separately) are non-returnable once opened. Defective items reported within the 30-day
  window are eligible for a free replacement or refund, buyer's choice. Return shipping is
  free for defective items; for change-of-mind returns the customer covers return shipping.

policy-warranty.json, full text                                          sha256:c776d676652d…
  Warranty Terms

  Laptops carry a 2-year manufacturer warranty covering hardware defects, excluding accidental
  damage and battery wear below 80% capacity after 12 months. Headphones carry a 1-year
  warranty covering electronic and battery defects. Kitchen appliances carry a 1-year warranty
  on electrical components and a 5-year warranty on the motor for stand mixers and food
  processors specifically. Furniture carries a 3-year warranty against structural defects in
  materials or workmanship; fabric wear, staining, and finish fading from sunlight exposure are
  not covered.
```

`support_test.go`'s evidence fixtures are these texts verbatim:

- **paraphrase evidence** = `{-04, -03, policy-returns-electronics, -09, -02}` (`lane_test.go`'s
  `paraphrase` chunk-ID set).
- **warranty evidence** = `{-04, -03, -09, policy-warranty, -01}` (`lane_test.go`'s `warranty`
  set) — `policy-returns-electronics` is **absent** from this set entirely, not merely outscored.
  `review.md` finding 1 flags this absence as the fragile part: the verdict holds only because the
  two evidence sets differ in which *policy* they carry, not because the rule is robust to a
  retrieval that returns both (see "Disclosed fragility" below).

**The cached answer (`a`) cannot be real text in the same sense**, because no answer was ever
logged with its own text for this case — item 1.4 (the seam that carries chunk *text*) landed on
2026-10-05, a month after the 2026-09-06 run that produced this chunk-ID fixture, so nothing
captured what the cached answer actually said. One sentence has to be authored. To keep it from
being "whatever text clears 0.6," it is built only from facts already fixed by the real data above
(product-headphones-03's own battery spec, policy-returns-electronics's own return window) and
echoes that document's own phrasing ("30-day window", "full refund") rather than free vocabulary.
`review.md`'s closing note applies here: this pins the *formula's* behaviour on real evidence, not
a captured measurement of the 2026-09-06 case (no answer text exists to measure), and the
alternative — re-running the question through the live pipeline today to capture a genuine answer
— was not taken because it would cost a green-pressure generation and inherit the Modelfile's
`temperature 1` non-determinism (super-plan.md, "Generation determinism (U8)", still open) into a
fixture meant to be exactly reproducible on every `go test` run.

```
a = "The EarBuds Pop 3 has 6 hours of battery life, 24 hours with the case. Return it within
     the 30-day return window for a full refund if unused and in original packaging."
```

**Tokenizing `a`** (lowercase; split on `[^a-z0-9]+`; drop length < 3; drop the stopword list
below) gives `content-tokens(a)` = `{earbuds, pop, has, hours, battery, life, case, return,
within, day, window, full, refund, unused, original, packaging}` — **16 tokens**. (`"30-day"`
splits to `"30"`, dropped by length, and `"day"`, kept — the same hyphen the real policy text
itself uses in `"30-day window"`. `"has"` and `"within"` survive because the stopword list below,
revised per `review.md` finding 4, is shorter than my first hand-curated one.)

Checking each of those 16 against the two evidence unions (by hand — the implementation's own test
is the authority, this is a sanity check for the review):

| token | in paraphrase evidence? | in warranty evidence? |
| :--- | :---: | :---: |
| earbuds, pop, hours, battery, case | ✅ (product texts, unaffected by the policy swap) | ✅ (same product texts) |
| life, has | ❌ (neither word appears anywhere) | ❌ |
| return, day, window, full, refund, unused, original, packaging, within | ✅ (all in `policy-returns-electronics` — "within" appears twice there) | ❌ (none appear in `policy-warranty`) |

`S_lex(paraphrase) = 14/16 = 0.875` (clears 0.6 with margin). `S_lex(warranty) = 5/16 = 0.3125`
(fails 0.6 with margin). The gap is wide — not a near-miss on either side.

**Stopword list used for this derivation** — `review.md` finding 4 answers the first draft's own
open question (whether to anchor this to a named external list): yes. This is Lucene's
`StopAnalyzer.ENGLISH_STOP_WORDS_SET` (33 words, long-stable and public domain), committed verbatim
as the literal Go `var`, cited by name and source in `support.go`'s comment — not a hand-curated
list, so the arithmetic above is reproducible from a named source rather than from this document
alone:

```
a, an, and, are, as, at, be, but, by, for, if, in, into, is, it,
no, not, of, on, or, such, that, the, their, then, there, these,
they, this, to, was, will, with
```

(`"has"` and `"within"` are deliberately NOT in this list — that is why they survive into
`content-tokens(a)` above, unlike in the hand-curated list my first draft used.)

**Disclosed fragility, not hidden** (`review.md` finding 1): the refusal above holds only while the
answer's non-discriminating tokens (`earbuds, pop, hours, battery, case` — present in every
product's text, hence in BOTH evidence sets) stay a minority of `content-tokens(a)`. Two more
tests make this a stated, pre-registered limitation feeding RQ2a (`super-plan.md` item 6.4) rather
than an undisclosed one:

1. **Both policies retrieved** — evidence = warranty evidence ∪ `policy-returns-electronics`.
   `lane.go:174-177` documents that a return query on dev-v0 can retrieve *both* category return
   policies at once, so this is not a contrived union. `S_lex` recovers to ≈0.875 (the
   `policy-returns-electronics` tokens are back), and the gate **admits** — same answer, same
   "warranty question" framing, opposite verdict, because the fresh retrieval happened to carry
   the old evidence alongside the new.
2. **A spec-heavy answer to the same question** — e.g. one that leads with the full spec line
   (`"in-ear true wireless, no ANC, 6 hours battery life, 24 hours with the case, Bluetooth 5.3,
   5 g"`) and appends a short return clause — scored against the **warranty** evidence set. The
   non-discriminating spec tokens now dominate the denominator, `S_lex` clears `τ_s`, and the gate
   **admits** a warranty question — the same false hit `Final_Proposal.md`'s worked example exists
   to show the gate refusing, reproduced by changing only the answer's own wording.

Both tests assert **admit**, are named to say so (e.g.
`TestSupportLexicalAdmitsWhenBothPoliciesRetrieved`,
`TestSupportLexicalAdmitsASpecHeavyAnswerAgainstWarrantyEvidence`), and their doc comments point at
this section and at RQ2a — a test that asserts a gate *fails* cannot later be mistaken for evidence
that it was tuned to pass.

`TestNoThetaSeparatesTheMeasuredPair` (`lane_test.go`) stays untouched — it is the chunk-ID version
of the same documented 2026-09-06 case, and `spec.md` requires it still pass unmodified. The new
tests document the same case from the text side and should say so in their doc comments, the way
`lane_test.go:420-433`'s comment cross-references the rule it exists to avoid being broken by, and
should cite this design doc for where the evidence text came from rather than re-deriving the
provenance inline.

## Named decisions (and why)

1. **Set, not multiset.** `content-tokens(a)` and `tokens(C)` are deduplicated before counting.
   `Overlap` already made this call for chunk IDs with an explicit rationale ("duplicate chunk IDs
   would inflate the numerator past the denominator... both variants return a plausible number in
   [0,1]" — `rule.go`:26-27) and the same silent-plausibility failure mode applies to a word
   repeated in an answer. Alternative (multiset / raw token counts) is not chosen: it would let a
   repeated word inflate the denominator and change the score on prose that differs only in how
   often one word repeats, which is exactly the kind of wording-sensitivity the no-ML, "token
   arithmetic" framing (`Final_Proposal.md`:168) is trying to avoid.
2. **Tokenization**: lowercase, then split on runs of non-alphanumeric characters
   (`[^a-z0-9]+` after lowercasing). No stemming — "return"/"returns"/"returned" are three distinct
   tokens. This matches the "tokenise, stopword-filter, set-intersect, divide" description
   (`Final_Proposal.md`:168) literally: no step there is a stemmer, and adding one would be an
   unstated enrichment of an "adopted, not tuned" mechanism.
3. **The stopword list is Lucene's named `StopAnalyzer.ENGLISH_STOP_WORDS_SET`** (33 words),
   committed verbatim as a Go `var` in `support.go`, cited by name and source — **revised from a
   hand-curated list after `review.md` finding 4**: `τ_s` cannot move, so an uncredited,
   hand-picked list would carry the same leverage over the outcome that a hand-tuned threshold
   would, which is precisely the thing `Final_Proposal.md`:186 argues against for `τ_s` itself. No
   new dependency either way (`go.mod` currently pulls in only `redis/go-redis` and generated
   protobuf code — confirmed by `impact.md` finding 4) — the list is transcribed, not imported,
   so `architecture.md` §2's standard-library-only rule for `reuse/` still holds. A fixed artefact
   like `policyPrefix`/`productPrefix` in `lane.go`, not a parameter.
4. **Numeric tokens get no special treatment in this item.** A content token that happens to be
   digits (anything 3+ characters, e.g. `"365"`) is scored exactly like any other token under 2.1's
   filter. The fail-closed numeric-literal-and-unit check is item 2.2's separate arm, layered on
   top; 2.1 must not pre-empt it by, say, excluding digit tokens from `S_lex` "because the numeric
   arm will handle numbers" — that would silently narrow what 2.1's own score covers with no record
   of the decision.
5. **`SupportLexical` takes `chunkIDs []string` and returns a `SupportVerdict` struct**, not a
   bare `float64` over `evidence []string` as my first draft had it, and not the `(float64, bool)`
   tuple my second draft had either. `impact.md` finding 1 is why `chunkIDs` is a parameter at
   all: "count the condition" (super-plan.md item 2.1) cannot live in `reuse/` if the function only
   sees text, because telling a stale server apart from a legitimately empty retrieval needs
   `len(chunkIDs)` too. `review.md` finding 2 is why the result is a named struct rather than a
   tuple: `score, _ := SupportLexical(...)` silently compiles and reads the stale-server case as
   `score == 0`, which is `< τ_s`, which is exactly the misattribution item 2.1 forbids — a struct
   with a named `Scored` field makes that drop visible rather than silent. Centralizing the whole
   rule here also gives it its own direct unit test, the same reason `Overlap` and `Decide` live
   in `reuse/` at all rather than inline in the cascade.
6. **The tokenizer's normalisation is ASCII-only** (lowercase, then split on `[^a-z0-9]+`) and
   deliberately diverges from `cache.Normalize`, which keeps Unicode letters and strips punctuation
   WITHOUT splitting (so `"30-day"` becomes `"30day"` there, but `"30"` + `"day"` here). `impact.md`'s
   lead risk named this normalisation, alongside the stopword list and the length rule, as part of
   `S_lex`'s frozen definition (`review.md` finding 7) — recorded in `approvals.md`, not just here,
   so it is not rediscovered as a surprise the first time someone compares the two tokenizers'
   output on the same string.

## Residual open items (not blocking this item — recorded for later)

- **Whether `τ_s = 0.6` transfers to this system's own generated answers is reasoned, not
  measured** (`review.md` finding 3): the denominator is the answer's OWN content-token count, so
  a verbose or hedging real answer is penalised in a way the terse fixture answer above is not.
  Needs ~10-20 real generated answers scored against their own retrieval before item 2.3 wires
  this to anything served — out of proportion to a pure-function unit's scope, so deferred rather
  than blocking 2.1, and recorded in `approvals.md` as a precondition on 2.3.
- **Two forward notes for item 2.3**, recorded in `approvals.md` rather than fixed here, since
  this item does not touch `cascade.go`: its comment at `cascade.go:45-47` ("while the served
  rule is similarity AND namespace") goes stale the moment the gate is wired in; and `support_lex`'s
  denominator in any aggregate reporting is Tier-2 hits only, since the gate never runs without a
  retrieval.

## Corrections after code review (2026-10-12)

The text above is left as written, as the record of the design the reviewer saw. `review.md`, "Code
review of the implementation", gives the findings; these are the statements in this file that it
supersedes.

- **"interfaces.md's own words: key on `len(ChunkIDs) > 0`" (Function contracts, and Named decision 5)
  is wrong.** `interfaces.md` does not say it. The rule is in `ragclient/retrieve.go` (the comment on
  `RetrieveResult.Texts`) and `super-plan.md` item 2.1. (Finding 6a.)
- **"the zero value of `SupportVerdict` … gets the SAFE default" overclaims.** The zero value is
  `Scored == false`, but its `Score` is 0, below `τ_s`, so a caller that reads `Score` alone refuses a
  stale server as SUPPORT. The exported surface is now `SupportVerdict`, `SupportLexical`,
  `TauSupportLexical` **and `(SupportVerdict).Refuses()`**, which returns `Scored && Score < τ_s` and is
  the only sanctioned way to get a refusal. (Finding 1.)
- **The parameter `chunkIDs` is now `retrievedChunkIDs`**, documented as the fresh retrieval's IDs and
  never the entry's `source_chunk_ids`. (Finding 5.)
- **The stale-server guard is `len(texts) == 0 && len(retrievedChunkIDs) > 0`**, not `texts == nil &&
  …` (`plan.md`, Implementation notes).
- **"Disclosed fragility" tests do not feed RQ2a.** RQ2a is the query and the entry retrieving the
  *same* evidence. Both tests have *different* evidence from the entry's, so they are limitations of
  the lexical arm in its own domain ("the wrong document") whose false hits would count **inside** the
  headline false-hit rate, not beside it. The both-policies evidence is a constructed union; `lane.go`
  documents only that a *return* query retrieves both return policies. (Finding 3.)
- **The fixture pins the formula on real evidence with an authored answer; it does not discharge the
  Phase 2 exit clause "the gate refuses the measured warranty case".** (Finding 6c.)
- **Step 8b's pinned-score comparison was removed**: product-scoped retrieval cannot return the pinned
  sets, so it could never fire. The live test's verdicts are logged, not asserted. (Finding 2.)
