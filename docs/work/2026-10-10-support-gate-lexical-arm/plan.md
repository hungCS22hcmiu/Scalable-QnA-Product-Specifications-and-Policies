# Plan — lexical support arm (item 2.1)

Ordered, each step independently verifiable. No step touches `httpapi/`, `cache/`, `telemetry/`,
or `docs/contracts/interfaces.md` (spec.md, Out of scope). Step 8b adds one **test-only** file in
`ragclient/` and a `Makefile` target — no served code outside `reuse/` changes. Unlocked by
`/approve implementation`.

- [x] **1. `gateway/internal/reuse/support.go`** — new file. In order:
  - The Lucene `StopAnalyzer.ENGLISH_STOP_WORDS_SET` stopword list (33 words, design.md "The
    pinned fixture" / Named decision 3), as a package `var`, with a doc comment citing the name
    and source and stating it is transcribed verbatim, not imported.
  - `contentTokens(s string) map[string]struct{}` — lowercase, split on `[^a-z0-9]+`, drop
    length < 3, drop stopwords. Unexported, with the doc comment from design.md explaining why
    item 2.2 must not reuse it (drops short numeric literals the numeric arm needs).
  - `textTokens(s string) map[string]struct{}` — lowercase, split on `[^a-z0-9]+`, no filtering.
    Unexported, same reasoning.
  - `SupportVerdict struct { Scored bool; Score float64; ContentTokenCount int }`, with the three
    field doc comments from design.md's "Function contracts".
  - `SupportLexical(answer string, texts []string, chunkIDs []string) SupportVerdict`:
    - `texts == nil && len(chunkIDs) > 0` → `SupportVerdict{}` (zero value: `Scored: false`).
    - otherwise, `c := contentTokens(answer)`; `ContentTokenCount := len(c)`; if `len(c) == 0`,
      return `SupportVerdict{Scored: true, Score: 0, ContentTokenCount: 0}`; otherwise build
      `union := textTokens(strings.Join(texts, "\n"))` (nil/empty `texts` joins to `""`, an empty
      token set — covers the legitimately-empty-retrieval case for free, no separate branch
      needed), count `c`'s members present in `union`, divide by `len(c)`.
  - `const TauSupportLexical = 0.6`, with the doc comment from design.md citing
    `decisions.md`'s inherited frozen-values table and explaining why it is not a `Thresholds`
    field.
  - *Verify:* `go build ./gateway/...` compiles; `gofmt -l` clean.

- [x] **2. `gateway/internal/reuse/doc.go`** — one line added to the package comment naming the
  support gate alongside "the source-overlap reuse rule and the cascade" (design.md, "What this
  adds, and where"; `impact.md` finding 7).
  - *Verify:* `git diff` shows a one-line, comment-only change.

- [x] **3. `gateway/internal/reuse/support_test.go`** —
  `TestSupportLexicalSeparatesTheMeasuredPair`, the item's required Done-when test:
  - The seven evidence strings from design.md's "The pinned fixture", transcribed verbatim, each
    as a named `const` or fixture var with a comment carrying its SHA-256 prefix from design.md
    (so a future edit to the literal is visible as a diff against a stated checksum, not just
    against prose).
  - The authored answer string `a`, with a doc comment stating plainly: (a) the evidence texts are
    verbatim dev-v0 corpus text via `ingest.py`'s real templates, (b) the answer is authored
    because no answer text exists for the 2026-09-06 case `lane_test.go` pins by chunk ID, (c) it
    is constrained to vocabulary the real documents already fix, not freely chosen, and (d) this
    test therefore pins the *formula's* behaviour on real evidence, not a replayed measurement —
    cross-referencing `lane_test.go:420-433`'s comment style and this task's design.md.
  - Record the answer sentence's own SHA-256 prefix in a comment beside it (design.md checksums
    the seven evidence texts, not the answer) — step 8b pins the same value.
  - Assert `SupportLexical(a, paraphraseEvidence, paraphraseChunkIDs)` has `Scored: true` and
    `Score >= TauSupportLexical`.
  - Assert `SupportLexical(a, warrantyEvidence, warrantyChunkIDs)` has `Scored: true` and
    `Score < TauSupportLexical`.
  - Assert `ContentTokenCount == 16` on both calls (same answer both times) — catches a
    tokenizer regression that shifts the denominator without necessarily flipping either verdict.
  - *Verify:* `go test ./gateway/internal/reuse/... -run TestSupportLexicalSeparatesTheMeasuredPair -v`.

- [x] **4. Disclosed-fragility tests**, same file, per design.md "Disclosed fragility, not
  hidden" and `review.md` finding 1 — each doc-commented as a pre-registered limitation feeding
  RQ2a (`super-plan.md` item 6.4), not a regression:
  - `TestSupportLexicalAdmitsWhenBothPoliciesRetrieved`: evidence = warranty evidence set plus the
    `policy-returns-electronics` string; assert `Scored: true` and `Score >= TauSupportLexical`
    (the gate admits).
  - `TestSupportLexicalAdmitsASpecHeavyAnswerAgainstWarrantyEvidence`: a second authored answer
    leading with the full spec line (design.md gives the wording) scored against warranty
    evidence; assert `Scored: true` and `Score >= TauSupportLexical` (the gate admits a warranty
    question).
  - *Verify:* both tests pass, and each fails if commented out of the assertion (i.e. temporarily
    flip `>=`/`<` while writing them, confirm the test catches it, then flip back) — cheap manual
    check that the assertion direction is the one intended, since both of these assert "admits"
    where the headline test asserts "refuses."

- [x] **5. Tri-state coverage**, same file — one test per `SupportVerdict.Scored` branch, each
  using short literal fixtures (not the corpus text) since these exercise the signature's
  contract, not the measured case:
  - `texts == nil, chunkIDs == []string{"x"}` → `Scored: false`, `Score: 0`, `ContentTokenCount: 0`
    (the stale-server case item 2.1 forbids scoring).
  - `texts == nil, chunkIDs == nil` → `Scored: true`, `Score: 0` (legitimately empty retrieval).
  - an answer with only stopwords/short tokens (e.g. `"a is of"`) against non-empty evidence →
    `Scored: true`, `Score: 0`, `ContentTokenCount: 0` (no content tokens to support).
  - *Verify:* `go test ./gateway/internal/reuse/... -run TestSupportLexical -v` covers all three
    alongside step 3/4's tests.

- [x] **6. Stopword-list pin**, per `review.md` finding 8 — a test asserting
  `len(stopwords) == 33` and a checksum of the sorted, joined list, so an accidental future edit
  fails a test instead of silently rescaling every score that depends on it (`impact.md`'s lead
  risk). *Verify:* the test passes against the literal written in step 1, and fails if a word is
  added or removed (confirm once, by hand, then leave it).

- [x] **7. `BenchmarkSupportLexical`**, per `review.md` finding 8 — benchmarks `SupportLexical`
  over the paraphrase fixture (one representative ~600-character evidence set), turning
  `Final_Proposal.md`:168's "microseconds" claim from reasoned into measured for this item.
  *Verify:* `go test ./gateway/internal/reuse/... -bench SupportLexical -benchtime=1x` runs and
  reports a number; record it in `approvals.md`'s implementation row.

- [x] **8. Full verification**: `go build ./gateway/...`, `go vet ./gateway/...`,
  `go test ./gateway/internal/reuse/... -race -v`, `gofmt -l gateway/internal/reuse/` (empty
  output). Confirm `TestNoThetaSeparatesTheMeasuredPair` (`lane_test.go`) still passes unmodified
  — `go test ./gateway/internal/reuse/... -run TestNoThetaSeparatesTheMeasuredPair -v`.

- [x] **8b. Live check against the real retrieval service** *(added 2026-10-12 at the author's
  request; see `impact.md` Amendment)*. Steps 3-8 prove the formula on text I transcribed from
  `data/dev-v0/*.json`; nothing there proves the running service hands `SupportLexical` the same
  text. This is item 1.4's seam (`ragclient/seam_live_test.go`) taken one hop further. It is **not a
  measurement** and not a request to `/ask` — the gate is not wired in (spec.md, Out of scope), so
  `/ask` cannot exercise it. Files:
  - `gateway/internal/ragclient/support_live_test.go` — package `ragclient_test`, test name
    `TestSupportLive` (must not match seam-check's `-run '^TestSeam$'`). Reuses the same-package
    helpers `checkAligned`, `corpusKeyPrefix`, `seamDeadline`. Skipped unless `RAG_SEAM_ADDR` is
    set; once set, anything unreachable is a **failure**, never a skip. Redis access is read-only
    (`HGet` only, DB 0 holds the corpus).
  - A `support-check` target in the `Makefile` (+ `.PHONY`), modelled on `seam-check`: starts its
    own `rag.server` on `:50052` from the working tree, runs only `TestSupportLive`, and fails on a
    skip, a cached result, or no test run. **The startup block is copied, not factored out** —
    editing `seam-check`'s recipe would reopen item 1.4's verified target. `make verify` never
    runs it, same as `seam-check`.
  - What it asserts:
    1. **Transcription fidelity.** For each of the seven fixture chunk IDs, the Redis oracle text
       (`corpus::<id>` field `text`) has the SHA-256 prefix recorded for it in `design.md` "The
       pinned fixture". This is what ties the step-3 literals to the ingested corpus, not to my
       reading of the JSON. **Unverified assumption this tests:** that the text stored in Redis
       equals `ingest.py`'s `product_to_text`/`policy_to_text` output byte-for-byte (the chunker
       could alter whitespace). If this fails, it is a finding about the fixture — re-derive the
       literals from the Redis text and redo design.md's arithmetic — not something to loosen the
       comparison around.
    2. **Seam + stale-server guard on real data.** Two retrievals through the real `ragclient`
       (`top_k = 0`, `productID = "product-headphones-03"`, as the gateway sends), each passing
       `checkAligned`; then `reuse.SupportLexical(a, r.Texts, r.ChunkIDs)` must return
       `Scored: true` and `ContentTokenCount == 16` for both. The answer `a` is the same sentence as
       step 3, copied with its SHA-256 prefix pinned so drift from `support_test.go` fails here.
    3. **Score check, conditional.** If a retrieval returns exactly the fixture's chunk-ID set for
       that case, its score must equal the fixture score (0.875 paraphrase, 0.3125 warranty).
       Otherwise the test **logs** the live ID set and score and passes — the 2026-09-06 queries
       were never recorded (`lane_test.go` pins chunk IDs only), so live retrieval is not owed to
       reproduce those sets.
  - **The two queries are fixed here, before anything runs, and are not edited afterwards to make
    retrieval land on the pinned sets** (`CLAUDE.md`: never tune to make a headline work). If
    retrieval returns different sets, that is reported, not repaired:
    - paraphrase-case: `"How long is the battery on the EarBuds Pop 3, and how many days do I have to return it?"`
    - warranty-case: `"How long is the battery on the EarBuds Pop 3, and what does the warranty cover?"`
  - Preconditions (the target prints them, as `seam-check` does): `redis-cli PING`, corpus ingested
    (`make ingest`), no listener on `:50052`. It loads the embedding model, **not the LLM**.
    Memory-pressure level is recorded, not gated — same status as `seam-check`, because nothing
    here is citable.
  - *Verify:* `make support-check` ends in PASS with the log kept (`SEAM_LOG=<path>`). Record the
    log path, the two live ID sets, and the two scores in `approvals.md`'s implementation row. The
    transcription-fidelity check should also be shown to **fail** once, by hand (flip one byte of
    one fixture literal in a scratch copy), so a vacuous pass is ruled out.

- [x] **9. `/verify`** (the project-wide check) — confirm the only files changed are
  `gateway/internal/reuse/{support.go,support_test.go,doc.go}`,
  `gateway/internal/ragclient/support_live_test.go` and the `Makefile` (`git status`), and that
  `make lint`/`make test` pass or report `SKIPPED` only for tooling reasons already known
  (`CLAUDE.md`'s `ruff`/`pytest` PATH note), not for this change. Also confirm `make test` /
  `make verify` did **not** run `TestSupportLive` (it must skip without `RAG_SEAM_ADDR`).

## Implementation notes (2026-10-12)

All ten steps done. What differs from the plan as written, and what was found:

**Deviations (small, deliberate):**
- **Stale-server guard is `len(texts) == 0 && len(chunkIDs) > 0`, not `texts == nil && ...`.** proto3
  decodes "no texts" to nil, so in production the two are the same; an empty non-nil slice with
  chunk IDs would otherwise score 0 and read as a SUPPORT refusal, the exact misattribution the
  struct exists to prevent. `TestSupportLexicalStaleServerIsNotScored` covers both shapes, and the
  nil-only mutant is killed by it.
- **The tokenizer folds ASCII case by hand over bytes** (`eachToken`) instead of calling
  `strings.ToLower`, so the "ASCII-only" rule in `approvals.md` is literally true: Unicode lowercasing
  maps U+212A KELVIN SIGN to `k`, which would have let a non-ASCII character join a token. Bytes
  >= 0x80 are separators. `contentTokens` and `textTokens` share it.
- **`supportStopwords` is a `map[string]struct{}`** (set), not a slice, so membership is O(1) and the
  pin test sorts the keys.
- **Extra tests beyond the plan:** `TestSupportFixtureChecksums` (the literals' SHA-256 prefixes are
  asserted, not just commented), `TestContentTokensRules`, `TestSupportLexicalIsSetNotMultiset`,
  `TestSupportLexicalEvidenceIsTheUnionOfChunks`.
- **`specHeavyAnswer`** (step 4) is a second authored string; design.md gave only a fragment. Its
  wording was fixed before scoring: "The EarBuds Pop 3 is in-ear true wireless with no ANC, 6 hours of
  battery life, 24 hours with the case, Bluetooth 5.3, 5g each. Return it within 30 days."
  S_lex = 11/15 = 0.733 against the warranty evidence.

**Verification evidence:**
- Fixture: all seven corpus texts reproduce design.md's SHA-256 prefixes byte-for-byte (the policy
  bodies are one line in the corpus; title + `\n\n` + body). An independent Python reference gives
  14/16 and 5/16, and 14/16 for the both-policies case, matching the Go scores.
- **Mutation checks** (scratch copy of the package, 11 mutants of `support.go`: add `within` to the
  stopwords, drop `the`, remove the stale guard, nil-only stale guard, invert the score, join chunks
  with no separator, length rule 2 and 4, no uppercase fold, unscored on empty content, drop
  `ContentTokenCount`) were all killed. A corrupted fixture literal is caught by
  `TestSupportFixtureChecksums`; a corrupted checksum in the live test fails `make support-check`.
- **`BenchmarkSupportLexical`** (Apple M1, 5-chunk paraphrase evidence): ~15.9 us/op steady state
  (`-benchtime=20000x`), 12368 B/op, 286 allocs/op; a cold single iteration (`-benchtime=1x`) is
  62 us. Co-hosted and non-citable. "Microseconds" holds. 286 allocs is the per-token string
  allocation; not optimised, nothing needs it yet.
- **`make support-check`: PASS**, memory pressure level 1 (yellow; recorded, not gated; the check is
  not a measurement and loads only nomic-embed-text). Fidelity: the text in Redis hashes to all
  seven recorded checksums, so the transcription assumption holds.

**Finding from step 8b: live retrieval does not reproduce lane_test.go's pinned sets.** Both queries
(fixed in advance, productID `product-headphones-03`) returned **two** chunks:
- paraphrase-query: `[product-headphones-03#chunk-0, policy-returns-electronics#chunk-0]`, S_lex 0.8750, ADMITS
- warranty-query: `[product-headphones-03#chunk-0, policy-warranty#chunk-0]`, S_lex 0.3125, REFUSES

The scores equal the fixture's only because the same discriminating policy chunk was retrieved; the
score assertion correctly did not apply. Cause, from `retrieve.py`: a product-scoped request
post-filters every OTHER product's chunk (`_drop_other_products`), and the pinned sets contain chunks
of products 04, 09 and 01/02, so they cannot come from a product-scoped retrieval on current code.
They came from an unscoped request. The queries were NOT edited to chase the pinned sets. An unscoped
variant would be a plan change and was not run.

**`/verify` (2026-10-12):** `make verify` exit 0.

| Target | Result |
| :--- | :--- |
| Go format (`gofmt -l gateway/`) | PASS (no output) |
| Go vet | PASS |
| Go build | PASS |
| Go test (`go test ./...`) | PASS (all packages with tests; `reuse` and `ragclient` included) |
| Python lint (`ruff check rag/ experiments/`) | PASS (found via `make`'s PATH; not on the shell's PATH) |
| Python tests (`pytest rag/`) | PASS, 15 passed |
| Python tests (`pytest experiments/tests`) | PASS, 155 passed |
| Proto drift | PASS, by hash: the stubs are gitignored (`gateway/internal/ragpb/`, `rag/src/rag/pb/`), so `git diff --exit-code` would be vacuous. Instead, SHA-256 of all 5 generated stub files before and after `make proto` (exit 0) were identical |

Re-run on a second `/verify` the same day: `make verify` exit 0, 0 SKIPPED, `go test -count=1 ./...`
all packages ok (the `make verify` run showed `(cached)` for Go packages, so the uncached run was done
separately), pytest 15 + 155 passed, `gofmt -l gateway/` empty.

Files changed: `gateway/internal/reuse/{support.go,support_test.go,doc.go}`,
`gateway/internal/ragclient/support_live_test.go`, `Makefile` (`support-check`, `.PHONY`). The
`docs/decisions.md` modification in `git status` predates this task. `TestNoThetaSeparatesTheMeasuredPair`
passes unmodified; `lane.go`, `lane_test.go` and `rule.go` have no diff. `make verify` never runs
`TestSupportLive` (it skips without `RAG_SEAM_ADDR`).

The `/verify` skill also says to record the result in "this week's worklog"; weeks were removed
2026-09-21 (`/phase`), so no worklog was written.

## Changes after the code review (2026-10-12, `review.md` "Code review of the implementation")

- `support.go`: added `(SupportVerdict).Refuses()`; reworded the `Scored`/zero-value comment (it
  claimed a safe default that did not exist); parameter `chunkIDs` renamed `retrievedChunkIDs`; the
  `len(...) > 0` rule now cites `ragclient/retrieve.go` and `super-plan.md` 2.1, not `interfaces.md`.
- `support_test.go`: `TestSupportVerdictRefuses` added; `Refuses()` asserted in the required test;
  apostrophe and underscore cases added to `TestContentTokensRules`; the two limitation tests no
  longer claim to feed RQ2a; the required test says it does not discharge the Phase 2 exit clause.
  New mutants killed: `Refuses` without the `Scored` check, `Refuses` with `<=`, `_` and `'` as word
  characters, stale guard removed.
- `support_live_test.go`: removed the pinned-set comparison and its constants (product-scoped
  retrieval can never return the pinned sets, so it could not fire); header "WHAT A PASS MEANS"; the
  verdict log line uses `Refuses()`. `Makefile` PASS line now says verdicts are logged, not asserted.
  This departs from step 8b item 3 as written.
- `architecture.md`: three lines updated (file tree, "Check the code", "Not built").
- `design.md`: amended with a "Corrections after code review" section.

**Re-verified after these changes:** `gofmt -l gateway/` empty, `go vet` clean, `make verify` exit 0
(0 SKIPPED; pytest 15 + 155), `go test -count=1 ./...` all ok.

**Done since:** `make support-check` re-run after the live-test edit (2026-10-12, pressure level 1): PASS,
fidelity PASS, paraphrase-query 0.8750 and warranty-query 0.3125 on the same live sets as the first run.

**Finding 4a closed** by the author's choice: pointer row added to `decisions.md`'s frozen table.

## Outcome (`/done`, 2026-10-12)

**Shipped.** The lexical arm of the answer-evidence support gate as a pure, unwired function in
`gateway/internal/reuse/support.go` (`SupportLexical`, `SupportVerdict` with `Refuses()`,
`TauSupportLexical = 0.6`, the 33-word Lucene stopword list); its tests, including the item's
Done-when test `TestSupportLexicalSeparatesTheMeasuredPair`; a live check (`make support-check`,
`ragclient/support_live_test.go`); the frozen `S_lex` definition recorded in `approvals.md` and as a
row in `decisions.md`; three stale lines in `architecture.md`. `make verify` exit 0 (0 SKIPPED);
`TestNoThetaSeparatesTheMeasuredPair` unmodified and passing; `make support-check` PASS twice.

**What the Done-when test does and does not show.** It passes: the paraphrase scores 14/16 = 0.875
(admitted), the warranty case 5/16 = 0.3125 (refused), on verbatim dev-v0 evidence. The cached
answer is authored, because no answer text was ever captured for the 2026-09-06 case, so this pins
the formula's behaviour, not a replayed measurement.

**Phase 2 exit criterion, run clause by clause (2026-10-12): not met.**
1. *refuses the measured warranty case, admits the measured paraphrase*: fixture level only; nothing
   calls `SupportLexical` outside `reuse/` (grep), and there is no check on answers the system
   really generated. Not met.
2. *every Tier-2 refusal carries a cause code*: no `refusal_cause` anywhere in `gateway/` (grep).
   Item 2.3. Not met.
3. *both arms independently switchable and recorded*: no `support_gate` anywhere in `gateway/` or
   `experiments/` (grep). Items 2.2, 2.4. Not met.
4. *the decisive-similarity regression still reproduces*: `TestNoThetaSeparatesTheMeasuredPair` PASS.
   Holds, and must be re-run when the phase closes.

**Deferred (recorded in `approvals.md`).** (1) Before item 2.3 wires the gate: score ~10-20 real
generated answers against their own retrieval, to test whether `τ_s = 0.6` suits this system's
answers. It needs the live LLM at green pressure. (2) For 2.3: `cascade.go:45-47`'s comment goes
stale; `support_lex`'s denominator is Tier-2 hits only; the cause-code branch must call
`Refuses()`, never compare `Score`; claim the empty-retrieval hole being closed on purpose.

**Follow-ups worth a task.** (a) An *unscoped* live variant of step 8b, if the 2026-09-06 chunk-ID
sets are to be reproduced at all: product-scoped retrieval cannot return them (they contain other
products' chunks), which `lane_test.go`'s comment does not mention. Would be a plan change. (b) The
limitation tests show the lexical arm admits some wrong-document cases; the headline false-hit rate
must include that shape (`review.md` finding 3).

**Scope was honest.** Opened at L because it lives in `reuse/` and feeds a measured claim; it did
touch `reuse/`. Step 8b later added a test-only file in `ragclient/` and a `Makefile` target, which
`impact.md` records as an Amendment and the author re-approved. No contract (`interfaces.md`
untouched, no version bump needed) and no pre-thesis frozen value changed. A new frozen definition
(`S_lex`) was created; no run has logged `support_lex`, so **no prior run is invalidated**.
