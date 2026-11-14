# Tier-2 trial: scope by evidence

Status: opened 2026-11-13 · spec approved 2026-11-13 · design approved 2026-11-13 · plan approved 2026-11-13
§3 changed §1–§2 (2026-11-13): part A excludes the 16 queries at replay instead of rebuilding the
workload (a rebuild fails `make corpus-verify`); the product-scope match is served first; a category
guard; done conditions 5, 7 and 10 sharpened, 13–15 added.
Plan writing corrected §3 (2026-11-13): the trial runs with `CACHE_CAPACITY=156`, as the cost run did;
§3.3 B now gives P1 and P2 word for word.
Build found (2026-11-14, step 6.8): rule 6 never held since `29da622`; §2's contract change gains
`interfaces.md` §I rule 6; the fix is plan Phase 8 (§4).
Super-plan item: 6.0a — Tier-2 trial: scope by evidence

## 1. Spec

**The change.** Build *scope by evidence* as an on/off arm, on top of majority-vote routing and a new
generator prompt, then replay validation with the arm off and on, and make the arm the served default
only if it passes the adoption rule below.

- **A. The 16 queries with no `product_id`.** `replay.py` skips them and counts them (ADR-025's
  decision). Validation replays send 606 queries. No workload file changes.
- **B. Generator output.** A new prompt: short, direct, no mention of the context or the source, no
  greeting. When the evidence does not hold the answer, the model writes `NO_ANSWER`; the RAG service
  replaces it with one fixed, polite sentence and flags it. The gateway never writes a flagged answer
  to Tier 1, Tier 2 or the dependency map.
- **C. Vote routing.** The POLICY document of a namespace is the policy document with the most
  retrieved chunks (a tie goes to the better rank). The same rule gives MIXED its policy part. Served in
  both arms.
- **D. The scope arm** (`SCOPE_ARM=off|on`, on every record). A one-off step stores, per document, its
  category, and per product a title vector and its product-bound words. At write time, a POLICY-lane
  answer with no product-bound word, whose product and policy document share a category, is stored
  once in the shared namespace `{policy_doc}`, keyed by `normalise(v − (v·t)·t)` (`v` the question
  vector, `t` the title vector). Any other answer is stored as ADR-024 says. With the arm on, a POLICY
  request searches the product namespace (raw vector, τ) and then the shared namespace (projected
  vector, τ_P); the product-scope match is served if it passes, else the shared one.
- **E. The trial.** Two validation replays, arm off and arm on: the same seed and order, a cold cache,
  support gate off, MIXED off, τ = 0.85. Each is judged by judge-v1. Green pressure is preferred; yellow
  is allowed and recorded; red stops the run. Both are `citable: no`.

**Adoption rule — fixed now, before any replay.** Scope `on` becomes the served default only if both
hold on the validation replays:

1. POLICY-lane hits judged correct rise by **at least 20** (arm on minus arm off).
2. With the arm on, the judged-wrong share of POLICY-lane hits is **at most** the judged-wrong share of
   POLICY-lane misses in the same run **plus 5 points**.

Otherwise the served default stays `off`, and the arm is reported as a measured result. Either way, the
decision is an ADR.

**τ_P rule — fixed now, applied before the first replay, with no verdicts.** On the stored validation
question vectors, take the policy pairs with *another question on the same policy document*. τ_P is the
smallest projected cosine at which the share of those pairs that pass is not above the share that
passes raw cosine at τ = 0.85 (equal specificity).

**Done conditions.**

1. `make verify`: no FAIL; any SKIPPED target listed by name.
2. `make replay SPLIT=validation` sends 606 requests and reports 16 skipped; the two workload files
   and `data/workload-manifest.json` keep their sha256; `make corpus-verify` passes.
3. A pytest pins the served prompt's sha256 (`generate.prompt_sha256()`, system part included). A
   pytest shows a `NO_ANSWER` output becomes the fixed sentence with `no_answer` set. A Go test shows a
   flagged answer writes no Tier-1 key, no Tier-2 record and no `dep:*` member.
4. `make prompt-probe` on a seeded validation sample (generator, `citable: no`), old and new prompt in
   the same run: the meta-phrase share (`context`, `provided`, `based on`, `according to`) is at most
   half the old prompt's, and the `NO_ANSWER` share on `answerable: true` questions is at most the old
   prompt's "don't know" share plus 3 points.
5. Go tests pin the vote and its tie rule. `go run ./cmd/gateprobe -routing` on the cost run's logged
   retrievals (offline, no model) prints vote-correct ≥ top-chunk-correct for policy-gold questions.
6. A Go test shows that with `SCOPE_ARM=off` a POLICY request makes exactly one namespace search, and
   every write uses `{policy_doc}@{product_id}`.
7. `contracts/scope/cases.json` is read by a Go test and a pytest, and both pass: the tokenizer, the
   scope decision (neutral → shared; a bound word → product; another category → product; a missing
   title vector → product) and the projection (`|v′·t| < 1e-6`, `|v′| = 1`).
8. `make test-go` (Redis on :6390): a shared entry, served and promoted to Tier 1 under two products,
   is gone from Tier 2 and from both Tier-1 keys after one of its source chunks is invalidated.
9. `make seam-check` passes, and `make docmeta` leaves a category for 164 of 164 documents and a title
   vector for 152 of 152 products.
10. Before the first replay, `make scope-calibrate` prints τ_P, and a stored validation vector matches
    the gateway's own embedding of the same question (cosine ≥ 0.9999); τ_P and the scope-test cut are
    written with their date in §4 and in `preregistration.md`; this §1 is unchanged after design
    approval.
11. Both replays have `raw/` and `judge/`, `make run-manifest-check` passes with the records' `scope_arm`,
    pressure is recorded at 1 or 2 (never 4), and `make scope-trial` prints per lane and arm: hits,
    judged correct, judged wrong, Wilson intervals over requests and over clusters.
12. `decisions.md` holds an ADR for each of: vote routing, the prompt and fallback (amending ADR-023's
    prompt coupling), the scope arm, and the adoption decision with the numbers of condition 11.
13. A Go test shows a shared candidate is judged against τ_P and a product candidate against τ.
14. A Go integration test (fake store): a neutral policy answer written for product A is served to a
    paraphrase on product B of the same category, and not to a product of another category.
15. `make judge-sanity FILE=experiments/judge/sanity-fallback.jsonl` passes: the fallback is judged
    correct for an unanswerable question and incorrect for an answerable one.

**Out of scope.** Design B (lane from scores). Baseline 3′ (item 6.0). The support gate as an arm or
dropped (item 6.1). The address check and reuse tied to admission. Number checks on question pairs.
Any test-split run. Any change to τ, τ_s, `top_k`, chunking, the embedder, the generator model or
`retrieve.py`. A workload rebuild.

## 2. Impact

**Files.** Python: `rag/src/rag/generate.py`, `server.py`, a new `docmeta.py`;
`experiments/scripts/replay.py`, `run_manifest.py`, `judge.py`, `judge_references.py`, and new
`scope_calibrate.py`, `prompt_probe.py`, `scope_trial.py`; `experiments/judge/` (a pinned reference
prompt, fallback sanity pairs); `Makefile`. Go: `reuse/lane.go`, `reuse/cause.go`, a new `reuse/scope.go`;
`cache/tier2.go`, a new `cache/docmeta.go`; `httpapi/cascade.go`, `handler.go`; `ragclient/answer.go`;
`telemetry/evallog.go`; `cmd/gateway/main.go`, `cmd/gateprobe/main.go`. Shared: `contracts/rag/v1/rag.proto`
and its generated code, a new `contracts/scope/cases.json`. Boundaries (`docs/architecture.md` §2) hold:
`reuse/` stays pure; document metadata is read by `cache/`, not `catalog/`.

**Frozen values touched.**

- **The generator prompt** (`generate._PROMPT_TEMPLATE`, sha256 `3e224f45…`): replaced. ADR-023 tied the
  reference writer to it; §3 decouples them (the writer keeps the old text in a pinned file), so the
  references and ADR-026's judge-error figures stay valid. ADR-023 is amended.
- **ADR-024's POLICY namespace:** the rank-1 document becomes the vote; the arm adds a shared form.
- **ADR-025's mechanism:** exclusion at replay instead of a rebuild. The frozen `v1` workload and
  `data/v1-freeze.json` are untouched.
- **New values:** τ_P (by the rule in §1), the scope-test cut (pinned at 0.10, never swept), `SCOPE_ARM`.
- **Unchanged:** τ_s 0.6, `top_k` 5, chunking, the embedder, the generator model, `RETRIEVAL_VERSION`,
  ADR-016's band.
- **Runs invalidated:** none citable (no run is citable yet). The cost run
  `2026-11-01T21-17-56_cfg4_judgecost` (`citable: no`) no longer describes the served generator or the
  POLICY namespace; it stays the basis of item 5.2's labels.

**Contract change.** `interfaces.md` §B (`AnswerChunk.no_answer`, field 6), §C (`docmeta:{doc_id}`),
§D (Tier-2 `scope` field; the shared namespace `{policy_doc}`; the projected key vector), §H
(`scope_arm`, `query_lane`, `hit_scope`, `write_scope`, `no_answer`, `shared_similarity`,
`shared_refusal_cause`). Both sides change. `source_chunk_ids`, `t1_key` and `dataset_epoch` keep their
meaning; a shared entry can gain Tier-1 keys from many products, all in `lru:t1keys:{entry_id}`. §I
rule 6 reads a new last line of the gateway log (found at step 6.8, §4).

**Measurement change.** Yes. With the arm on, a POLICY hit can cross products, so wrong hits come in
groups: intervals are also computed by cluster. Hits are reported per `scope_arm` and per scope. The
fallback is a new outcome: counted, never a hit.

**New dependency.** None. Document metadata is about 0.5 MB, in Redis and in the gateway.

**Cut scope reinstated.** No. The scope test reads the answer, not the question; the projection uses
the title vector named by `product_id`; no classifier and no ML runtime on the hit path.

## 3. Design

### 3.1 Approach

Keep the served rule `sim ≥ τ ∧ namespace` and change *where an answer may be served*. A POLICY answer
that names nothing of its product is true for every product that routes to the same policy document, so
it is stored once for all of them. Everything new is deterministic: a word test on the answer at write
time, and one dot product on the hit path.

*The alternative it beat:* a hit-time word check (ADR-024 option (d)). It runs on every hit and only
blocks; the write-time test runs once per miss and widens reuse.

### 3.2 A POLICY request with the arm on

```mermaid
sequenceDiagram
    participant G as gateway (cascade)
    participant R as reuse/
    participant C as cache/ (Redis)
    G->>R: lane, namespace(chunkIDs, product) — vote picks policy_doc
    G->>C: KNN in "policy_doc@product" with v
    C-->>G: candidate P (or none)
    G->>R: judge P against τ
    alt P passes
        G-->>G: serve P (hit_scope = product)
    else no P, or P refused
        G->>R: category guard; v' = project(v, title[product])
        G->>C: KNN in "policy_doc" with v'
        C-->>G: candidate S (or none)
        G->>R: judge S against τ_P
        G-->>G: serve S if it passes (hit_scope = shared), else MISS
    end
```

On a miss, write-back runs the scope test on the answer and writes one entry: shared (namespace
`policy_doc`, key `v'`) or product (namespace `policy_doc@product`, key `v`). SPEC and MIXED requests,
and every request with the arm off, take today's single search and write.

### 3.3 The parts

**A. Replay exclusion.** `replay.replay()` drops queries whose `product_id` is empty before it orders
them, and its summary prints `skipped_no_product_id`. The seeded order is drawn over the 606 that
remain, so both arms see the same sequence. The test split has none, so it is unaffected.

**B. Prompt and fallback.** `generate.py` sends Ollama a `system` text and a user template.

- System text P1, word for word (lines joined with `\n`; the example is hand-written, no Amazon-PQA text):

  ```text
  You answer shoppers' questions about one product and the store's policies.
  Use only the facts given with the question.

  Rules:
  - Answer in one or two short sentences.
  - Start with the answer itself.
  - Never mention the facts, the context, a document, or where the information comes from.
  - Do not greet the shopper. Do not repeat the product's name.
  - Use the exact numbers and terms from the facts.
  - If the facts do not answer the question, reply with exactly: NO_ANSWER

  Example
  Facts: Unopened items can be returned within 30 days of delivery for a full refund.
  Question: I never opened the box. Can I still send it back?
  Answer: Yes. Unopened items can be returned within 30 days of delivery for a full refund.
  ```

- User template: `"Facts:\n{context}\n\nQuestion: {query}\nAnswer:"`.
- P2, used only if P1 fails condition 4: P1 followed by a blank line and this second example. No third
  prompt is tried; if P2 fails too, the executor stops and the human decides.

  ```text
  Example
  Facts: Weight: 2.1 kg. Screen size: 15.6 inches.
  Question: What colour is it?
  Answer: NO_ANSWER
  ```
- `finalize(text) -> (text, no_answer)`: if `\bno[ _]?answer\b` matches (any case), return the fixed
  sentence *"Sorry, I don't have that detail for this product. Please check the product page or
  contact our support team."* and `True`. Fail-closed: the sentinel never reaches a customer.
- `prompt_sha256()` hashes `system + "\x00" + template`. `run_manifest.py` and the pin test use it.
- `server.Answer` sets `AnswerChunk.no_answer`. `ragclient` exposes `NoAnswer`. In `handler.go` a
  flagged result returns before the epoch check: no `Put`, `PutTier2`, `Register`, touch or trim, and the
  record says `no_answer: true`.
- **Decoupling the references.** The old template is saved verbatim as
  `experiments/judge/reference-prompt-v1.txt` (its sha256 must be `3e224f45…`). `judge_references.py`
  reads the writer's prompt from that file. `judge.py` no longer requires the run's
  `generator.prompt_sha256` to equal the reference set's; it records both, and still requires the
  writer's prompt hash to match `reference-writer-v1.json`.

**C. Vote routing.** `reuse.policyDocByVote(chunkIDs []string) string` counts policy chunks per document
and returns the most frequent; a tie goes to the document whose first chunk ranks higher. `Namespace`
uses it for POLICY and for MIXED's policy part, on the read and the write path alike (same function).

**D. Document metadata.** `rag.docmeta` (`make docmeta`, embedding model only) reads `data/v1/*.json` and
writes `docmeta:{doc_id}` hashes: `category` for all 164 documents; for the 152 products also
`title_vec` (the title embedded with the `search_document:` prefix, float32 little-endian, like `t2:*`)
and `bound_words` (JSON list). A product-bound word is a token of the product's title and spec values
that is in no policy document of its category and occurs in at most 10 % of products (the cut).
Tokens: lowercase, split on `[^a-z0-9]+`, length ≥ 2 — written once in `contracts/scope/cases.json`.
`cache.Store.LoadDocMeta(ctx) (map[string]DocMeta, error)` reads them at start.

**D. The scope test and the projection** (`reuse/scope.go`, pure):

- `ScopeTokens(text string) map[string]struct{}`.
- `DecideScope(lane Lane, answer string, product, policy DocMeta, hasPolicy bool) Scope` — `ScopeShared`
  only when the lane is POLICY, the arm is on, the product has a title vector, both documents have the
  same non-empty category, and no answer token is a bound word; `ScopeProduct` otherwise.
- `Project(v, t []float32) []float32` — `v − (v·t)·t`, renormalised; nil when `t` is missing or the result
  is near zero (then the request takes product scope only).
- `SharedNamespace(policyDoc string) string` — the policy document alone.
- `LaneInput` gains `Shared bool`; `Thresholds` gains `TauP`; `NamespaceDecision` gains `Tau`, the
  threshold it applied. `Judge` compares similarity with `d.Tau`, so a shared candidate meets τ_P and a
  product candidate meets τ.

**D. Gateway wiring.** `main.go` reads `SCOPE_ARM` (`off` default; any other value than `off|on` stops
the start) and `REUSE_TAU_P` (required when the arm is on), loads the metadata, and refuses to start
with the arm on if any product lacks a title vector. Its start-up line adds `scope_arm=… tau_p=…` for
`run_manifest.py`. `Tier2Entry` gains `Scope` (`product|shared`), stored as the plain field `scope`; the
index is unchanged because `namespace` is already a TAG. `tryTier2` adds the second search exactly as
§3.2. Dependency registration is unchanged: a shared entry depends on every chunk it was generated
over, so an edit to the writer product's own chunk also purges it (over-invalidation, counted by item
6.5).

**E. Calibration, probes and the trial.**

- `scope_calibrate.py` applies the τ_P rule of §1 to `data/v1-draft/workload/vectors.json` (validation
  ids) and the `title_vec`s in Redis, read-only. `gateprobe -embedcheck` embeds three stored questions
  through the gateway's own client and prints the cosine against the stored vector.
- `prompt_probe.py` draws a seeded sample of 120 validation queries (100 `answerable: true`, 20 `false`),
  retrieves as the service does, and generates with both prompts. It prints the two shares of
  condition 4. `citable: no`.
- `gateprobe -routing` reads the cost run's `raw/requests.jsonl` and the validation workload and applies
  `reuse.Namespace` to each logged retrieval, for the top-chunk rule and the vote.
- Each replay: `make cache-reset`, start the gateway with `CONFIG_ID=4 MUTATION=off SUPPORT_GATE=off
  LANE_SIGMA_HI=0.20 REUSE_TAU=0.85 CACHE_CAPACITY=156 SCOPE_ARM=… REUSE_TAU_P=…`, then `make replay`,
  `make run-manifest`,
  `make judge`. `scope_trial.py` reads both runs' `judge/records.jsonl` and `raw/requests.jsonl`, takes
  the lane from `query_lane`, and prints the table of condition 11 and the verdict of the adoption rule.
  A cluster counts as wrong when any of its hits is wrong.

### 3.4 Failure modes, silent ones first

1. **The Go and Python tokenizers differ.** Bound words are never found, every policy answer looks
   neutral, and answers that name a product are shared. *Symptom:* trap 13 comes back across products.
   *Caught by* condition 7 (one fixture for both languages) and 14.
2. **Written with `v`, searched with `v'` (or the reverse).** Shared entries are never found. *Symptom:*
   the arm looks useless, a plausible null. *Caught by* condition 14.
3. **A shared candidate judged against τ, or a product one against τ_P.** The arm's hits shift with no
   error. *Caught by* condition 13.
4. **A shared entry's Tier-1 copies survive a purge.** Stale answers under other products. *Caught by*
   condition 8.
5. **A fallback written to the cache.** "No detail" served to a later question that has an answer.
   *Caught by* condition 3.
6. **A missing or zero title vector projected anyway.** `v'` equals `v`, so product names stay in the
   key. *Caught by* condition 7 (missing → product scope) and 9 (152 of 152).
7. **τ_P calibrated on vectors the gateway never computes.** τ_P is wrong by a constant. *Caught by*
   condition 10 (cosine ≥ 0.9999).
8. **The record's `scope_arm` says one arm and the gateway ran another.** *Caught by* condition 11
   (`run-manifest-check` reads the arm from the records and the start-up line, ADR-010).
9. **The served prompt's hash leaves out the system text.** The manifest describes the wrong prompt.
   *Caught by* condition 3 (the pin hashes both parts).
10. **The replay order changes between arms.** The two runs differ by more than the arm. *Caught by*
    condition 2 (606 sent in both; the seed is in the manifest).
11. **A category guard missing.** If ADR-020's swap ever failed, an answer would spread to another
    category. *Caught by* conditions 7 and 14.
12. **The judge refuses the trial runs** (prompt hash mismatch). Loud, not silent: condition 11 fails.

### 3.5 Edge cases

- A POLICY request whose product has no metadata: product scope only, logged as such.
- A policy document with no category (none in `v1`): never shared.
- MIXED and SPEC answers: never shared, in either arm.
- Two product-scope and shared entries for the same question: the product one is served first.
- A coalesced follower gets the leader's answer and writes nothing, as today.
- A warm cache from before ADR-025 holds `{policy_doc}` namespaces without a `scope` field. Every trial
  run starts from `make cache-reset` (ADR-010's own-cache rule), so none is read.

### 3.6 Unknowns

- Whether a shared answer is judged right for another product. Only the trial settles it.
- Whether P1 makes about three quarters of policy answers neutral (36 answers, `tier2-novelty-research.md`).
  Condition 4 and the trial's `write_scope` counts settle it.
- The electronics policies cover TVs and headphones in one text, so a neutral answer can still be wrong
  for another product type. The trial's wrong hits per cluster show it; it is reported in RQ2a.
- The effect of LRU at 0.25 × K: both arms run at `CACHE_CAPACITY=156`, as the cost run did. Shared
  entries take fewer slots, so the arm may also gain from eviction; the trial cannot separate the two.

### 3.7 Verification

| Condition | How |
| :--- | :--- |
| 1 | `make verify` |
| 2 | `make replay` summary; `shasum -a 256` before and after; `make corpus-verify` |
| 3, 7 | pytest and Go unit tests |
| 4 | `make prompt-probe` (generator, pressure checked, `citable: no`) |
| 5 | Go unit tests; `go run ./cmd/gateprobe -routing` |
| 6, 13, 14 | Go tests with the fake store in `httpapi` |
| 8 | `make test-go` |
| 9 | `make seam-check`; `make docmeta` summary |
| 10 | `make scope-calibrate`; `gateprobe -embedcheck`; the dated entries |
| 11 | the two replays, `make run-manifest-check`, `make scope-trial` |
| 12 | the ADRs in `decisions.md` |
| 15 | `make judge-sanity` (judge loaded, `citable: no`) |

Rough cost: build about 5 days; runs about 3 hours (docmeta 1 min, prompt probe 15 min, two replays of
40–60 min, two judge passes of about 20 min).

## 4. Findings

**Existing tests that this design changes — approved by the human with the design, 2026-11-13:**

- `rag/tests/test_server_cancel.py` pins the old template's sha256. The prompt changes on purpose, so the
  pin moves to the new `prompt_sha256()`.
- `experiments/tests/test_judge.py` expects a refusal when the run's `generator.prompt_sha256` differs from
  the reference set's. After the decoupling that refusal moves to the writer's prompt.
- `experiments/tests/test_judge_references.py`: the writer's prompt is read from the pinned file, not from
  `generate._PROMPT_TEMPLATE`.

`reuse/lane_test.go` `TestNamespaceUsesRankNotSetMembership` keeps passing under the vote (each list
has one chunk per document, so the tie rule picks rank 1). Any other existing test that fails is a stop
for the executor.

**Found at step 1.3 and approved by the human, 2026-11-13:** `rag/tests/test_server_cancel.py`
`test_request_body_is_unchanged` asserts the Ollama body has exactly five fields. §3.3 B adds a sixth,
`"system"`, on purpose. The expected body gains exactly `"system": generate._SYSTEM_PROMPT` and nothing
else, so the test still catches any other change to the body.

**τ_P and the cut, fixed before the first replay (step 6.6, 2026-11-14 01:10 +07:00).** The rule of §1, applied by
`make scope-calibrate` to the validation vectors and the title vectors, with no verdict: 142 policy questions, 12 documents,
1,322 same-document pairs; raw cosine at τ = 0.85 passes 78 (0.0590); **τ_P = 0.8329** (exact 0.832813) passes 77
(0.0582); no pair without a projection. `gateprobe -embedcheck`: 3 of 3 stored vectors equal the gateway's own embedding
(cosine 1.000000). **The scope-test cut is 0.10**, pinned. Both are in `preregistration.md` Entry 8, dated the same
minute, before any trial `RUN_ID`. The figures are in `evidence/scope-calibrate.json` and `evidence/embedcheck.txt`. §1 is
unchanged since approval (its sha256 `86631c22…` matches `evidence/spec-sha.txt`).

**Found at step 6.8, 2026-11-14 — rule 6 could never hold, fix approved by the human the same day.**
The arm-off run `2026-11-14T01-11-46_cfg4_scope-off` was clean (606 records, no INCOMPLETE line, pressure 1),
but `make run-manifest` wrote `admissible: false`, `rule_6: false`.

- *Cause.* Commit `29da622` (2026-11-12, before this task) changed the gateway's shutdown line from
  `gateway: shutting down, flushing the evaluation log` to `gateway: shutting down: no new requests; …`.
  `run_manifest.py` and `interfaces.md` §I still look for the old text, so every run since that commit fails
  rule 6. The only such runs are today's two. The commit's diff proves it, so no `rca-analyst` was run.
- *A deeper gap.* Both lines are printed when shutdown *starts*. A second Ctrl-C then kills the process,
  buffered records are lost and no INCOMPLETE line is printed, yet rule 6 would hold. Rule 6 also ignored
  the two warnings `29da622` added: `WARNING requests still in flight` and `the dependency map is INCOMPLETE`.
- *Fix (option 1 of three; the others only matched the new text).* The gateway prints
  `gateway: run ended cleanly` as its **last** line, and only when the server stopped by `Shutdown`, every
  request finished, the dependency map closed with nothing dropped or failed, and the log closed complete.
  Rule 6 holds when the log has that line, or the pre-`29da622` line, and none of the INCOMPLETE line and
  the two warnings. `parse_gateway_log` keeps its keys (`ended`, `incomplete`). A pytest checks that every
  line rule 6 reads is printed by `main.go`, so a renamed line fails a test, not a run. No existing test
  changes. Contract: `interfaces.md` §I `rule_6`, in v0.37.
- *Runs.* Both folders of 2026-11-14 stay as written (write-once, `citable: no`): `…T01-11-00…` is an empty
  start the executor stopped, `…T01-11-46…` is inadmissible. Step 6.7 is repeated under a new `RUN_ID`.

**Main-session check, 2026-11-14 03:00–03:20 +07:00.** Every done condition 1–15 re-run by the main session, not read
from the executor's report: all pass, and `make scope-trial` reproduces `KEEP OFF` byte for byte. Pressure 1 throughout.

**POLICY hits split by scope (agreed with the author, not part of the adoption rule; `evidence/scope-split.json`).**
Arm off: 8 hits, all product scope, 1 judged correct and 7 wrong. Arm on: 14 shared hits, 9 correct and 5 wrong; 1
product hit, wrong. So the shared hits are about as often right as a fresh answer (POLICY misses: 0.419 wrong), and the
arm also removed 7 wrong product-scope hits. Rule 1 failed on volume, not on quality: 97 of 145 POLICY answers were
written shared, but only 14 were found again. The shared hits' similarity runs 0.834–0.957 (median 0.863), just over
τ_P 0.8329, which the equal-specificity rule of §1 set close to τ.
