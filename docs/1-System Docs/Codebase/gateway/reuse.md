# `gateway/internal/reuse/` — the reuse decision (C1)

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `lane.go` (375 lines), `rule.go` (109), `cause.go`
(127), `gate.go` (50), `support.go` (184), `support_numeric.go` (492), `doc.go`, and seven test files (66 tests).
**The ideas** (lanes, namespaces, the support gate, worked examples, every trap) are in
[`Tier 2.md`](../../Tier%202.md) §4–§12a. This doc explains the code.

## 1. Purpose

Given a question's fresh retrieval and one cached candidate, it decides: **serve the cached answer, or not, and
why not**. The served rule is `sim ≥ τ ∧ namespace(q) = namespace(e) ∧ support(answer(e), text(retrieve(q)))`
(ADR-019). It serves **C1**.

## 2. Boundaries

- **No I/O at all:** no Redis, no gRPC, no HTTP, only the standard library. So C1 can be tested, and refuted, in
  isolation (`docs/architecture.md` §2).
- **It never reads the query text as a signal.** Every input is chunk IDs, a similarity, the cached answer, and
  the fresh evidence text. The lane is **read from the grounding, never predicted**: a classifier's error would
  become a false-hit cause with no place in the evaluation.
- **No learned model.** Set operations and token counts only.

## 3. Files

### `lane.go` — lane, namespace and the namespace rule

**Chunk IDs** are `{doc_id}#chunk-{n}`, and `doc_id` starts with `product-` or `policy-` (`interfaces.md` §C,
checked by gate G4). Without that prefix, every question would fall into the SPEC lane with no error.

**`PolicyFraction(chunkIDs)`**: the share of retrieved chunks that are policy chunks.

**`LaneBand{Lo, Hi}`** and the two pinned bands (ADR-016): **off** = [0.20, 0.20) and **on** = [0.20, 0.60).
`Pinned()` checks that a band is one of them, exactly; `Arm()` gives the record's `mixed_lane` value.

**`Classify(chunkIDs, band)`** picks the lane: no chunks or fraction 0 → **SPEC**; fraction 1 → **POLICY**;
fraction ≥ `Hi` → POLICY; ≥ `Lo` → **MIXED**; otherwise SPEC. With the off band, MIXED is never chosen.

**`Namespace(lane, chunkIDs, productID)`**, the cache partition:
- **SPEC:** the request's `product_id` if it has one, else the first product document in rank order. Request
  metadata wins because rank 1 is unstable across paraphrases when a catalogue has near-duplicate products.
- **POLICY:** the **first policy document in rank order**. Rank, not set membership: two questions can retrieve
  the same set of policies, but the right one ranks first.
- **MIXED:** `product|policy`, the pair. Either half missing gives `""`, because half a key would widen to "any
  product" or "any policy".

The namespace is the **document**, never the chunk, so re-chunking a document does not re-partition the cache.

**`MatchNamespace(queryNS, entryNS)`**: equal and not empty. An empty namespace on either side **never matches**.

**`DecideNamespace(similarity, lane, queryNS, entryNS)`**: `similarity ≥ τ` and namespace match. It has **no
containment term** (ADR-019).

**`DecideLane(in LaneInput)`** is what the cascade calls. Pure lanes delegate to `DecideNamespace`. MIXED also
requires the **entry to be MIXED**, a check that cannot fail today (a pair key never equals a single key) but
turns that into an enforced rule. `LaneInput` is a struct, so two `Lane` and two `string` arguments cannot be
swapped by mistake.

**`NamespaceDecision`** records the verdict and **which term judged it** (`Rule`), so the log can tell the lanes'
hits apart. It also carries the containment counterfactual (`Overlap`), copied from `Decide`.

### `rule.go` — containment, kept as a counterfactual

**`Overlap(retrieved, entrySources)`** = `|retrieved ∩ entrySources| / |entrySources|`, **asymmetric
containment**, not Jaccard: "is what grounded the cached answer still what grounds this question?" Both sides
are de-duplicated. An entry with no sources scores 0. With `top_k = 5` it takes only six values (0, 0.2, …, 1).

**`Jaccard(a, b)`** is the symmetric version, kept for comparison.

**`Thresholds{Tau, Theta}`** are the rule's two values, set from `REUSE_TAU` and `REUSE_THETA` (demo values; τ is
swept). **`Decide(similarity, retrieved, entrySources)`** applies `overlap ≥ θ ∧ similarity ≥ τ`. **It never
decides what is served** (ADR-019): the cascade runs it for every candidate that clears τ and reports the result: `source_overlap` in
the evaluation record, and `overlap_decision` in the `/ask` response (not in the record). Under product-scoped
retrieval, overlap is about 1 for any two questions about one product.

### `cause.go` — one reason per judged candidate

**The causes:** `NONE` (served), `NAMESPACE` (an alarm: the scoped search should make it impossible),
`SIMILARITY`, `SUPPORT`, `NOT_SCORED` (the server sent chunk IDs without text; refused, and kept apart so a stale
server is not blamed on the gate). `CONTAINMENT` is in the list but **never returned**; it must be absent from a
log, not counted as 0.

**`Judge(g, d, similarity, answer, texts, retrievedChunkIDs)`** gives the cause, in this fixed order:
1. namespace term fails → `NAMESPACE`;
2. `!(similarity ≥ τ)` → `SIMILARITY` (written this way so NaN refuses);
3. gate off → `NONE`, without running the gate or reading `texts`;
4. gate cannot score → `NOT_SCORED`;
5. either arm refuses → `SUPPORT`;
6. otherwise `NONE`.

The gate-off line comes **after** the first two, so a wrong namespace or a NaN is refused on both arms. `g` is the
first parameter so no caller can leave it out.

**`Judgement.Served()`** is the **only** serve rule: `Cause == NONE`. It must never be written as "no arm refused",
because an unscored result does not refuse.

**`CheckSupport`** runs **both** arms and returns them separately (`SupportResult`); neither short-circuits.
`Scored()` and `Refuses()` combine them.

### `gate.go` — the support gate switch

**`Gate`** is `GateOn` (the default) or `GateOff` (the ablation arm, ADR-010). **`ParseGate`** accepts exactly
`"on"` or `"off"`; anything else is an error, and `cmd/gateway` then refuses to start.

### `support.go` — the lexical arm

**`SupportLexical(answer, texts, retrievedChunkIDs)`**:
`S_lex = |content-tokens(answer) ∩ tokens(evidence)| / |content-tokens(answer)|`, refused when below
**`TauSupportLexical = 0.6`** (pinned from GroundedCache, never swept).
- Tokens: lower-case, split on anything that is not `[a-z0-9]`, as sets. Content tokens also drop the 33 Lucene
  English stopwords (`supportStopwords`) and tokens shorter than 3 characters. No stemming.
- **The evidence is the fresh retrieval's text**, never the cached entry's sources, and **the query is never
  read**.
- `SupportVerdict` keeps `Scored`, `Score` and `ContentTokenCount`. Its resolution is 1 / token count, so a
  two-token answer is refused as soon as one token is missing.
- **`Refuses()`** is the one sanctioned way to turn a verdict into a refusal: "scored and below 0.6". `!Refuses()`
  is **not** "may reuse", because it is also true when unscored.

These rules are frozen values (`docs/decisions.md`, "Support-gate lexical score definition"): any edit after the
first `v1` run needs an ADR.

### `support_numeric.go` — the numeric arm

**`SupportNumeric(answer, texts, retrievedChunkIDs)`** checks that **every number in the answer is in one evidence
chunk with the same value, and the same unit** if a listed unit follows it. It has no threshold.
- **`readNumbers`** is the one reader, used for the answer and for each chunk (`numScanner` does the work). It
  reads ASCII numbers with `,ddd` groups and a `.d` part, compares them in a clean form (`canonNumber`), reads a
  unit only from a **closed list** (`numUnits`, `numUnitAlias`, currency symbols before a number), reads number
  words only before a listed unit, and treats letter-digit tokens (`IPX7`, `3rd`) as **codes** that must appear
  whole.
- **Anything it cannot read refuses** (`1,5`, `5.3.1`, `.5`, non-ASCII digits): it fails closed.
- **Chunks are read alone**, never joined (`factsOf`, `numSupported`).
- `NumericVerdict` has `Refuses()` and `Admits()`; `Admits()` is not `!Refuses()`.

The full grammar is a frozen value (`docs/decisions.md`, "Support-gate numeric arm definition"), with its accepted
gaps.

## 4. Callers and callees

- **Called by** `httpapi`'s cascade (`cascade.go`): `Classify` and `Namespace` once per request, `DecideLane`,
  `Decide` (the counterfactual) and `Judge` for the one candidate; and by the write-back (`handler.go`), which
  classifies the **answer's own** sources to give the new entry its lane and namespace.
- **Configured by** `cmd/gateway/main.go`: `Thresholds` from `REUSE_TAU` and `REUSE_THETA`, the band from
  `LANE_SIGMA` / `LANE_SIGMA_HI` (only the two pinned bands start), the gate from `SUPPORT_GATE`.
- **Calls** nothing.

## 5. Tests that pin it

66 tests in seven files. Some that guard against a plausible wrong number:

| Test | Guarantees |
| :--- | :--- |
| `TestJudgeServedIsCauseNoneOnly` | serving means `Cause == NONE`, nothing else |
| `TestJudgeAgreesWithDecideLane`, `TestJudgeAgreesWithDecideLaneGateOff` | `Judge` and `DecideLane` agree on every input, both arms |
| `TestJudgeBothArmsAgreeBeforeTheGate`, `TestCheckSupportRunsBothArms` | both arms run; the gate switch changes only what comes after τ |
| `TestDecideNamespaceNeedsBothSimilarityAndMatch`, `TestMixedNamespaceIsThePairAndNeedsBothHalves` | the namespace rule and the MIXED pair |
| `TestDecideRequiresBothConditions` | the containment counterfactual's two terms |
| `TestSupportStopwordsArePinned`, `TestContentTokensRules` | the lexical arm's frozen list and token rules |
| `TestNumericReaderGolden`, `TestNumericReaderRules`, `TestNumericUnitListPinned`, `TestNumericNumberWordsPinned` | the numeric arm's frozen grammar |
| `TestSupportLexicalStaleServerIsNotScored`, `TestNumericStaleServerAndEmptyRetrieval` | a server without texts is unscored, never refused |

## 6. Silent failures to watch

- **Swapping containment's denominator, or "simplifying" it to Jaccard**, changes every overlap value and still
  returns a plausible number in [0, 1].
- **Passing the cached entry's sources as `retrievedChunkIDs`** to a support arm would score the old answer against
  its own old evidence, and always admit.
- **An edit to the stopword list, the token rules or the unit list** silently rescales every logged support value.
  They are frozen; a change needs an ADR.
- **A namespace computed from the query's grounding at write-back** would partition entries wrongly; the write-back
  uses the answer's own sources.

## 7. Commit

`29b24a6`.
