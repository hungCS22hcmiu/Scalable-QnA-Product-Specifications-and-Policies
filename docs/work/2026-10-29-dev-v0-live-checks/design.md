# The live seam and support checks still pin the retired dev-v0 corpus

Status: opened 2026-10-29 · spec approved 2026-10-29 (with the test changes, §4) · design approved 2026-10-29 · plan approved 2026-10-29
Super-plan item: none — blocks the live re-check that items 1.4 and 2.1 require after any retrieval or
LlamaIndex change (`make seam-check`, `make support-check`)

## 1. Spec

**Root cause** (`rca-analyst`, 2026-10-29; raw files in `evidence/rca/`, cited as `E/`). The author
retired `dev-v0` on 2026-10-29 and Redis now holds `v1`. The two live tests still pin `dev-v0` IDs, and
none of them exists in `v1` (`EXISTS corpus::<id>` is 0 for all four). An unknown `product_id` raises no
error anywhere: `retrieve.py:_drop_other_products` drops every `product-*` chunk, and
`_ensure_own_chunk` finds nothing to splice. A scoped retrieval therefore returns nothing, or policy
chunks only.
- **`make seam-check` fails loudly** at `TestSeam/L2`. The power query's top 5 on `v1` are all product
  chunks, so the scoped call returns 0 chunks: `len(texts) = 0, len(chunk_ids) = 0: want equal and >= 1`
  (`E/seam-check.log`). L1, L3 and shift still pass; they do not depend on the corpus.
- **`make support-check` fails** at `TestSupportLive/fidelity`: 7 × `oracle: no text at corpus::…`
  (`E/support-check.log`).
- **Its two query subtests PASS while proving nothing.** Each retrieved one `v1` policy chunk and no
  product chunk, and scored the `dev-v0` answer (0.4375, 0.1875). Their checks hold whatever is
  retrieved, and the verdicts are logged, not asserted. **So a fix that re-pins only the fidelity
  hashes would make `make support-check` print PASS with the scoped product in no retrieval.** That
  is the silent failure this task must close.
- **Upstream:** item 4.4 switched Redis to `v1` and moved `test_retrieve_scoping.py`, but did not sweep
  the Go live tests. Nothing rejects an unknown `product_id` (`server.py`, `retrieve.py`, `/ask`), and
  `interfaces.md` §B v0.8 does not say what should happen. That is what turns a stale pin into a
  plausible retrieval instead of an error.

**Test or code: the tests are stale, and only in their corpus pins.** The intention changed: the author
retired `dev-v0` on 2026-10-29 (`rag/src/rag/config.py:19-22`). Each test's logic stays as it is.

**The change.** Re-pin the two live tests to `v1`, using the replacements the RCA verified on live
`v1`. Add two checks that make a future corpus switch fail loudly instead of passing empty.

**What changes in the existing tests — the author must confirm before `/approve`**
(`execution.md`, Tests):

- **`seam_live_test.go`.**
  - Changed: `spliceDoc` and `spliceChunk` become `product-laptops-b07k238ls2` and its `#chunk-0`
    (one chunk, with no power, watt or volt term). The comment at `:39-41` changes with them.
  - Unchanged: `powerQuery`, `policyQuery`, `checkAligned`, and L1–L3 and shift with all their
    assertions.
  - Verified: L1 is stable on `v1`, and L2 splices that chunk at index 0 (`E/seam-check.v1-proposal.log`).
- **`support_live_test.go`.**
  - Changed:
    - `supportProduct` becomes `product-electronics-b07wnp64zn` (REETEC headphones);
    - in both queries, only the product name changes;
    - the dev-v0 fidelity map becomes 4 `v1` chunk hashes;
    - `supportCachedAnswer`, its SHA (`197de3fd39ab`) and `supportContentTokens` (16 → 22) become the
      RCA's authored answer;
    - the header lines that cite dev-v0 sets and scores are updated.
  - Unchanged: the fidelity loop, `checkAligned`, `Scored`, the `ContentTokenCount` equality, the
    answer's SHA self-check, `top_k = 0`, and read-only access.
  - **Structural change:** the answer is no longer "`reuse/support_test.go`'s `cachedAnswer` byte for
    byte". That offline fixture stays on dev-v0, so the cross-file checksum link is cut.
- **Two new checks** (they make the tests stronger, not weaker):
  - **(i) Scoped product present.** Each support retrieval must contain a `supportProduct` chunk. This
    closes the empty pass above.
  - **(ii) Pin preflight.** At the start of each test, every pinned chunk ID must exist in Redis.
    Otherwise it fails with "pin absent … corpus switched?".
- **Not added: asserting the two verdicts.** The RCA measured ADMITS at 0.9545 and REFUSES at 0.4091 on
  `v1` (`E/support-check.v1-proposal.log`). Item 2.1 chose to log verdicts, not assert them, and this
  task keeps that choice.
- **Not changed: `support_sample_live_test.go`.** It has no Makefile target, and it reads the hash-pinned
  dev-v0 sample (`sample-questions.md`). A `v1` version would be a new pre-registered sample, which is a
  new task. It stays as a dated dev-v0 artefact.

**Done conditions.** Live runs load the embedding model only; they are `citable: no` and produce no thesis
number.
1. **The failing tests first.** Before any edit, on `v1`, `make seam-check` fails at `TestSeam/L2` with
   the empty-retrieval message. `make support-check` fails at `TestSupportLive/fidelity` with
   `oracle: no text`.
2. **The empty pass is witnessed.** With check (i) added and the dev-v0 pins still in place,
   `make support-check`'s `paraphrase-query` and `warranty-query` subtests FAIL, naming the absent
   product. Today they PASS.
3. **`make seam-check`** exits 0 on `v1` with L1, L2, L3 and shift all PASS. L2's log shows
   `product-laptops-b07k238ls2#chunk-0` spliced at index 0.
4. **`make support-check`** exits 0 on `v1`:
   - `fidelity` passes on the 4 `v1` hashes;
   - both query subtests PASS, and each retrieval contains a `product-electronics-b07wnp64zn` chunk;
   - the log shows S_lex for each query (logged, not asserted).
5. **The preflight fires.** A run with a pin changed to an absent ID fails with "pin absent", once for
   each test, using a `GOFLAGS=-overlay` copy in `evidence/` and never editing the test itself.
6. **Nothing else moved.**
   - `git diff --name-only -- gateway/` lists only the two test files;
   - `git diff --quiet gateway/internal/reuse/` exits 0;
   - `support_sample_live_test.go` is unchanged.
7. **Records.** `docs/super-plan.md`'s Issue-2 finding says `seam-check` and `support-check` run on
   `v1`, and names the unknown-`product_id` gap as an open finding.
8. `make verify`: no FAIL; any SKIPPED target is listed by name.

**Out of scope** (listed in `deliverables.md` as follow-ups):
- **Rejecting an unknown `product_id`.** It is a contract decision for `interfaces.md` §B.
- **Moving `make demo` to `v1`.** Phase 8.
- **The dev-v0 fallbacks** in `experiments/k6/ask.js`, `mu_hit.js` and `loadgen_footprint.py`. They are
  shakedowns, not checks.
- **A `v1` version of `support_sample_live_test.go`.**
- **Stale wording, flagged only:**
  - `CLAUDE.md:53` (the author's file);
  - `interfaces.md` §B's "one-chunk-per-document" rationale;
  - the docstrings of `test_retrieve_scoping.py:8` and `test_store_index_ready.py:10`, which are
    existing test files.

## 2. Impact

**Files.** `gateway/internal/ragclient/seam_live_test.go` and `support_live_test.go`: test files only,
in the package they already live in. No production code changes, and nothing in `docs/architecture.md`'s
boundaries moves. The Makefile targets are unchanged: they require each named subtest to PASS and reject
any SKIP, and the new checks sit inside the existing subtests. `docs/super-plan.md` gets one finding
updated.

**At the seam: flagged.** These are the two tests that guard the Go↔Python seam (`texts` aligned with
`chunk_ids`) and the support gate on live text. No seam or `reuse/` code changes, and no number changes.
The checks' S_lex values are logged and never cited.

**Frozen values touched.** None. **Invalidates:** none. No `run_id` exists, and these checks produce
no measured number.

**Contract change.** None. The unknown-`product_id` behaviour is a gap in `interfaces.md` §B v0.8. It
is flagged for the author and not fixed here.

**Measurement change.** None. Both are pass/fail correctness checks.

**New dependency.** None.

**Corpus licensing.**
- The new support answer and queries are authored. They name one `v1` product and two of its facts:
  a 500 mAh battery and 20 hours of playing time.
- The tests otherwise hold only chunk IDs and SHA-256 prefixes. No Amazon-PQA text is copied.
- The RCA's evidence was scanned against every `v1` product chunk and all 583 long validation
  questions: none appears.

**Cut scope reinstated.** No.

## 3. Design

**Approach.** Change the two test files by hand, using the RCA's `v1` proposals, which already passed
both targets through `GOFLAGS=-overlay` (`E/*.v1-proposal.*`). Add check (i) and the preflight (ii).
The order matters:
1. Witness the two failures on the untouched files (DC 1).
2. Add check (i) alone, with the dev-v0 pins still in place, and witness the empty pass turning into a
   failure (DC 2).
3. Only then re-pin and add the preflight. Once the preflight exists, it stops the test before the
   query subtests run, so DC 2 can no longer be witnessed.

Alternative it beat: a corpus-agnostic test that picks its pins from Redis at run time, as
`epoch_race_check.py` does. Rejected: it rewrites both tests' logic, not only their pins, and a test
that chooses its own fixture can always find one that passes.

### Files

**`gateway/internal/ragclient/seam_live_test.go`**
- `spliceDoc` becomes `"product-laptops-b07k238ls2"`, and `spliceChunk` its `#chunk-0`. The comment
  at `:39-41` says this product's only chunk has no power, watt or volt term. That was checked on `v1`
  with a read-only `HGET` (one chunk, 475 bytes, no match). `E/probe.out` shows only the splice firing,
  which was cited by mistake and is corrected at review (plan Phase 6).
- **Preflight:** in `TestSeam`, after `oracle` is defined and before the first `t.Run`, call
  `oracle(spliceChunk)`. On an error, `t.Fatalf("pin absent: %v -- this check is pinned to the v1
  corpus; was the corpus switched?", err)`. It issues an `HGet`, so the file's "HGet is the only
  command" claim stays true.
- **Unchanged:** `powerQuery`, `policyQuery`, `checkAligned`, `errTextMismatch`, the oracle, and L1,
  L2, L3 and shift with every assertion.

**`gateway/internal/ragclient/support_live_test.go`**
- **Constants**, exactly as in `E/support_live_test.v1-proposal.go.txt`:
  - `supportProduct`;
  - the two queries, with only the product name changed;
  - `supportCachedAnswer` and `supportCachedAnswerSHA = "197de3fd39ab"`;
  - the 4-entry `supportFixtureSHA`;
  - `supportContentTokens = 22`.
- **Check (i)**, in each query subtest right after `checkAligned`. If no ID in `r.ChunkIDs` starts with
  `supportProduct + "#"`, then `t.Fatalf("no %s chunk in the scoped retrieval %v: the product is
  absent from the corpus, or scoping is broken", supportProduct, r.ChunkIDs)`. It sits after
  `checkAligned`, because an empty retrieval already fails there with its own message.
- **Preflight (ii)**, after `oracle` and before `t.Run("fidelity")`. Call `oracle` on every
  `supportFixtureSHA` key and on `supportProduct + "#chunk-0"`, and `t.Fatalf("pin absent: …")` on
  the first error. The product's own chunk is checked by name, so changing only `supportProduct`
  still trips it.
- **The answer's self-check** keeps its assertion. Its message changes from "drifted from
  reuse/support_test.go's cachedAnswer" to "drifted from the answer recorded in this file": the
  cross-file link is cut.
- **The header** (`:3-37`) and the comments at `:66-70` and `:76-77` are rewritten for `v1`. They keep
  the same structure and say:
  - fidelity now pins the `v1` chunks the two scoped retrievals return. It no longer pins reuse's
    dev-v0 fixtures, which stay as they are;
  - "16 content tokens" becomes 22;
  - the observed verdicts are the RCA's (paraphrase: product chunk-0 +
    `policy-return-electronics` + `policy-return-phones-opened`, 0.9545, ADMITS; warranty: product
    chunk-0 + `policy-warranty-electronics`, 0.4091, REFUSES). They are observed, not predicted and
    not pinned;
  - the queries moved to `v1` by swapping only the product name, written before any probe ran
    (`E/preregistered-candidates.txt`), and must not be edited to land on a set or a verdict;
  - the verdicts are still logged, not asserted (item 2.1's choice, kept).
- **Unchanged:** the fidelity loop, `checkAligned`, `Scored`, the `ContentTokenCount` equality,
  `top_k = 0`, the deadline handling, and read-only access.

**`evidence/preflight/`** (new, for DC 5). For each test, `sed` makes a copy that renames its pinned
product to `product-absent-00`:
- `s/product-laptops-b07k238ls2/product-absent-00/g` for the seam test;
- `s/product-electronics-b07wnp64zn/product-absent-00/g` for the support test.

An overlay JSON maps the real file to the copy, and the target is run with
`GOFLAGS=-overlay=<abs path>`, the RCA's method. The test files themselves are never edited for
DC 5.

**`docs/super-plan.md`.** The Issue-2 finding (now `:456`) says `seam-check` and `support-check` run on
`v1`, with this trail. One new bullet records the unknown-`product_id` gap:
- nothing rejects it;
- `interfaces.md` §B v0.8 is silent about it;
- every `v1` workload `product_id` exists in Redis today (622 + 652 queries, 115 products each,
  checked 2026-10-29);
- suggestion: a pre-run check in the Phase 7 harness.

### Failure modes, silent ones first

1. **The re-pinned support check passes with the product absent from the retrieval.** This is today's
   empty pass. → Check (i); DC 2 witnesses it, and DC 4 runs it on `v1`.
2. **Check (i) never runs**, because the preflight or a `Fatal` stops the subtest first, or because it
   was added to only one subtest. → DC 2 is witnessed before the preflight exists, and on both
   subtests.
3. **A future corpus switch reads as a seam fault**, as with "len(texts) = 0" today. → The preflight;
   DC 5 shows its message for each test.
4. **A DC 5 overlay that does not apply** (GOFLAGS not reaching `go test`, or a cached result). The run
   would then PASS. → DC 5 requires a FAIL that names "pin absent". The targets already reject
   `(cached)` and run `-count=1`.
5. **New pins without the property.**
   - Seam: L2 still asserts that the chunk is absent from L1 and spliced at index 0.
   - Support: the two-sided verdict is logged, not asserted. That is a residual this task keeps by
     choice (item 2.1), so DC 4 records S_lex for both queries in its log.
6. **A pass with a skip, a cached result or no tests.** Both targets already fail on each.

### Edge cases

- **Ranking can move.** The `v1` scores rest on retrieval ranking, so a re-ingest or a LlamaIndex change
  can change them. Fidelity and alignment fail on changed text; a changed ranking only changes the
  logged S_lex.
- **`support_sample_live_test.go` is untouched.** It still pins dev-v0, has no target, and is not part
  of `make verify`.

### Unknowns

- How `support_sample_live_test.go` behaves on `v1` is reasoned (a fatal "0 chunks"), not run, because
  it loads the LLM. It is out of scope.

### Verification

Every live step checks pressure first, loads the embedding model only, and is `citable: no`.

| DC | Shown by |
| :--- | :--- |
| 1 | `make seam-check`, `make support-check` on the untouched files; logs in `evidence/witness/` |
| 2 | `make support-check` after check (i) alone; both query subtests FAIL naming the product |
| 3, 4 | `make seam-check`, `make support-check` after the fix |
| 5 | the two overlay runs in `evidence/preflight/` |
| 6 | `git diff --name-only -- gateway/`, `git diff --quiet gateway/internal/reuse/`, `git diff --quiet gateway/internal/ragclient/support_sample_live_test.go` |
| 7 | `grep` in `docs/super-plan.md` |
| 8 | `make verify` |

## 4. Findings

- **The test changes are approved by the author (2026-10-29).** The author typed `/approve` on this
  spec, which lists every change to `seam_live_test.go` and `support_live_test.go` under "the author
  must confirm before `/approve`", and asked first how `product_id` applies to `v1`.
  - The changes are: the stale corpus pins, the authored answer and its cut link to
    `reuse/support_test.go`, check (i) and the preflight.
  - Kept by choice: no verdict assertion, and `support_sample_live_test.go` untouched.
  - Why the tests are stale: the author retired `dev-v0` on 2026-10-29, which changed the corpus
    they test.
