# The POLICY namespace names the product too (ADR-024)

Status: opened 2026-11-10 · spec approved 2026-11-10 · design approved 2026-11-10 · plan approved 2026-11-10
Changed by §3 (2026-11-10): DC 1 pins the form `{policy_doc}@{product_id}`; DC 2 gains a real-Redis check;
DC 4 also runs once on the unchanged code; §2 lists the new cache test.
Super-plan item: 5.6 — A shared POLICY answer can name another product (builds ADR-024, decided 2026-11-07)

## 1. Spec

**The change.** When a request carries a `product_id`, its POLICY namespace is built from the product and the
rank-1 policy document, so a POLICY answer is reused only for the product it was written for. Without a
`product_id` it stays the rank-1 policy document. A POLICY namespace never equals a MIXED one.

**Why.** ADR-024: in the judge cost run, 4 of 94 Tier-2 hits were wrong answers taken from another product's
POLICY entry (about 4.3 %, close to δ = 5 % from one cause), and the support gate passed all 4. `Tier 2.md`
Example B (e) showed it live: H2's customer was served H1's answer, which names H1's brand.

**Facts this spec rests on.**
- Both namespace callers already pass the request's `product_id`: the write-back (`httpapi/handler.go:499`) and
  the search (`httpapi/cascade.go:134`). `reuse.Namespace` drops it in the POLICY branch (`reuse/lane.go:220`).
- Since ADR-025 every `/ask` carries a `product_id`, so the "no `product_id`" case is reached only by unit tests
  and offline tools.
- Today a MIXED namespace is `product|policy`. If a POLICY namespace used that same form, the two would be
  equal. The pure-lane rule (`DecideNamespace`) has no lane check, and the Redis search filters on the
  namespace alone, so a POLICY request could be served a MIXED entry with no error.
- `escapeTag` (`cache/tier2.go:208`) escapes every character that is not a letter, digit or `_`, so any
  separator is safe in the Redis query.

**Done conditions.**

1. **The namespace, unit-tested.** A new test file in `gateway/internal/reuse/`. Pass, all of: (a) the same
   policy chunks with two different `product_id`s give two different POLICY namespaces, and the same product
   with the same rank-1 policy document gives the same one; (b) with `product_id` `""` the POLICY namespace is
   exactly the rank-1 policy document, as today; (c) from the same chunks and product, the POLICY and the
   MIXED namespace differ; (d) `DecideLane` refuses product B's POLICY entry to a POLICY query of product A at
   similarity 1.0, and serves A's own entry; (e) the form is exactly `{policy_doc}@{product_id}`, for example
   `policy-returns-01@product-kettle-01`. Run first on the unchanged code: (a), (d) and (e) fail. That output
   is saved in `evidence/`.
2. **The served path keeps products apart.** (a) Through `Ask`, with fakes (a new test in
   `gateway/internal/httpapi/`, no Redis, no Ollama): a policy question for product A misses and writes a
   POLICY entry. The same question for product B is a MISS with `similarity` null and nothing judged, and the
   fake store was searched only in B's namespace. A paraphrase for product A, at a similarity above τ, is a
   TIER2_HIT on A's entry. This shows that the write path and the search path build the same namespace.
   (b) On a real Redis (a new test in `gateway/internal/cache/`, the test server of `make test-go`): three
   entries at one vector, in `policy-returns-01@product-kettle-01`, `policy-returns-01@product-headphones-03`
   and `policy-returns-01`. A search in each namespace returns only its own entry.
3. **The stale test, approved first.** `TestMixedLaneLabelMatchesRule`'s `off` case (`httpapi/mixed_lane_test.go:195`)
   pins the POLICY namespace `policy-returns-01` for a request that carries `product-kettle-01`. After the change
   it fails only because the searched namespace now names the product, which ADR-024 predicted. Pass: the
   failure is saved in `evidence/` and shows that cause; the author approves the change in §4, with the date,
   before it is made; the diff of that file changes only the `policyNS` value; the test then passes.
4. **Live replay of `Tier 2.md` Example B** (`citable: no`; memory pressure checked right before, as
   `execution.md` says, and written next to the result). `make cache-reset`, then `make dev` with the MIXED
   arm set off explicitly, gate on, τ 0.85. In order: Question 2 from H1 (`product-electronics-b07zj7qg33`)
   → MISS. Question 3 from H1 → `similarity` not null (still judged against Question 2's entry: same-product
   reuse is not lost). Question 4, Question 2's words from H2 (`product-electronics-b079jfb616`) → MISS
   with `similarity` null (nothing judged), and its response `namespace` differs from Question 2's. The
   replay also runs once **before** the change, and there Question 4 is judged against H1's entry
   (`similarity` not null), which shows the replay can see the bug. The responses, without answer text, and
   the log go to `evidence/`.
5. **Docs.** `interfaces.md` **v0.32**: §A's `product_id` row says the POLICY lane reads it too; §D's `t2:`
   schema lists the `namespace` and `lane` fields, with the namespace of each lane; a versioning row.
   `decisions.md`: ADR-024 and F-NAME say built, with the date and this trail. `super-plan.md`: item 5.6
   marked done. `Tier 2.md`: Step 4 (the POLICY row and "why are policy answers not split by product?"),
   Example A Question 5, Example B (e) and §12a row 6 say ADR-024 changed them, and the examples are read
   as "before ADR-024". The comments in `reuse/lane.go` (the file header and `Namespace`) state the new rule.
6. `make verify` passes, and no existing test is edited except the one in DC 3.

**Out of scope.**
- Phase 6's count of POLICY hits from another product's entry (ADR-024 check 3), and any new §H field.
- Option (a), a prompt that keeps product names out; option (d), a provenance check in the gate.
- The SPEC and MIXED namespaces, Tier 1, τ, the gate and the lane band. They do not change.
- `Final_Proposal.md`: the author's to edit. The task lists the places.
- Re-running the judge cost run, or any `Tier 2.md` example other than Example B, Questions 2–4.

## 2. Impact

**Files and boundaries.**
- `gateway/internal/reuse/lane.go`: the POLICY branch of `Namespace`, and its comments. `reuse` stays a pure
  package over chunk IDs, with no Redis, gRPC or HTTP (`architecture.md` §2).
- New tests: one file each in `gateway/internal/reuse/`, `gateway/internal/httpapi/` and `gateway/internal/cache/`
  (the last on the test Redis that `make test-go` starts, never `:6379`).
- `gateway/internal/httpapi/mixed_lane_test.go`: one constant, only with the author's approval (DC 3).
- No change expected in `handler.go` or `cascade.go`; §3 confirms it.
- Docs: `interfaces.md` §A, §D and the versioning table; `decisions.md` (ADR-024, F-NAME); `super-plan.md`
  item 5.6; `docs/1-System Docs/Tier 2.md` (named as stale by ADR-024).
- Not edited, but they follow the new rule because they call `reuse.Namespace`: `cmd/gateprobe` (a one-off probe
  for the 2026-10-31 trail; nothing runs it) and `ragclient/support_sample_live_test.go` (a live test that logs
  `same_namespace` and asserts nothing). Neither is re-run.
- `experiments/scripts/judge.py:160` reads the rank-1 policy document, not the namespace string, so it keeps
  its meaning.

**Frozen values touched.** None of the frozen numbers: the model, `num_ctx`, τ, τ_s, the lane band, the
capacity rule and the Tier-1 key do not change. The served reuse rule does change: the POLICY namespace
definition, as ADR-024 (a method decision) recorded on 2026-11-07.
**Prior runs invalidated: none citable.** Read as "before ADR-024", as ADR-024 says:
`2026-11-01T21-17-56_cfg4_judgecost` (citable: no), the 2026-11-07 runs behind `Tier 2.md` Examples A, B,
D and E, and any cross-product pairs of the 2026-10-31 prompt probe.

**Contract change.** Yes, `interfaces.md` v0.32.
- §A: `product_id` is now read by the POLICY lane too. The wire shape does not change. The response's
  `namespace` field (an extension, `httpapi/types.go:53`) holds the new value for POLICY requests, and the
  demo UI shows it as it is.
- §D: the `namespace` TAG value of a POLICY `t2:` record changes form. Entries written before the change stay
  in Redis, and no request with a `product_id` (since ADR-025, every request) can reach them. They take
  capacity until they are evicted or `make cache-reset` deletes them. A measured run starts on an empty cache
  (rule 11), so it is not affected.
- No `.proto` change. `source_chunk_ids`, `t1_key` and `dataset_epoch` are untouched. The dependency map does
  not read the namespace.

**Measurement change.** Yes, and it is the point.
- POLICY-lane reuse across products ends. A cross-product candidate is now never found, so it shows as a
  MISS with nothing judged (`similarity` null), not as a `NAMESPACE` refusal.
- The POLICY lane will show fewer hits and more generations, and one entry per product per policy. The
  capacity rule (0.25 × K) does not change, so evictions can rise. POLICY hit rates are not comparable across
  this commit.
- Framing (ADR-024): separation across products now comes from `product_id` in every lane, so the write-up
  credits provenance only for B-within. The measured effect of the MIXED arm shrinks.
- The meaning of `lane`, `similarity`, `refusal_cause` and every other §H field does not change.

**New dependency.** None.

**Cut scope reinstated.** No.

## 3. Design

**The approach.** One branch of `reuse.Namespace` changes. In the POLICY lane, with a `product_id`, the namespace
is `{policy_doc}@{product_id}`, where `policy_doc` is the document of the rank-1 policy chunk, as today. Without a
`product_id` it stays `{policy_doc}`, with no fallback to the rank-1 product chunk (ADR-024). The callers do not
change: the write-back and the search already pass the request's `product_id`.

| Lane | With `product_id` | Without |
| :--- | :--- | :--- |
| SPEC | `{product_id}` | rank-1 product document |
| POLICY | **`{policy_doc}@{product_id}`** (new) | `{policy_doc}` (unchanged) |
| MIXED | `{product_id}\|{policy_doc}` | `{rank-1 product doc}\|{policy_doc}` |

Why this form. `@` cannot appear in a `doc_id` (§C: a slug that starts with `policy-` or `product-`), and it
differs from MIXED's `|`. The order is also reversed: a POLICY namespace starts with `policy-`, a MIXED one with
the product. So a POLICY and a MIXED namespace can never be equal, even for the same pair.

Alternatives that lost:
- `{product_id}|{policy_doc}`, MIXED's own form. It equals the MIXED namespace of the same pair, and the
  pure-lane rule (`DecideNamespace`) has no lane check, so the two lanes would meet with no error.
- Also adding a lane check to the pure-lane rule. It changes the served rule beyond what ADR-024 decided.

**Files.**
- `gateway/internal/reuse/lane.go`
  - `const policyProductSeparator = "@"`, with a comment: it cannot appear in a `doc_id` and differs from
    `mixedSeparator`, so POLICY and MIXED never meet (ADR-024).
  - `Namespace(lane Lane, chunkIDs []string, productID string) string`: the same signature. The POLICY
    branch: `policy := firstDocIDWithPrefix(chunkIDs, policyPrefix)`; `""` if there is none; `policy` if
    `productID == ""`; otherwise `policy + policyProductSeparator + productID`.
  - Comments restated for ADR-024: the file header's POLICY bullet (it says scoping by product wastes
    capacity), `Namespace`'s table, and `mixedSeparator`'s note that a MIXED namespace never equals a
    POLICY one.
- `gateway/internal/reuse/lane_policy_product_test.go` (new): `TestPolicyNamespaceNamesTheProduct`
  (DC 1a, 1b, 1e), `TestPolicyAndMixedNamespacesNeverMeet` (DC 1c, over several chunk sets and products),
  `TestPolicyEntryOfAnotherProductIsRefused` (DC 1d, through `DecideLane`).
- `gateway/internal/httpapi/policy_product_test.go` (new): a fake `policyRAG`, like `mixedRAG`, that answers
  `Retrieve` and `Answer` for both `kettle` and `headphones` with two `policy-returns-01` chunks, whose texts
  hold every word of its answer, so the gate passes. `TestPolicyAnswerIsNotReusedForAnotherProduct` (DC 2a):
  `newHarness`, the default band (off), a MISS for kettle and its write-back (`tier2Written`), then the same
  question for headphones and a paraphrase for kettle (`askNear` at `hitCos`). It checks `cache`,
  `similarity`, `namespacesSearched()` and the record.
- `gateway/internal/cache/tier2_policy_namespace_test.go` (new): `TestTier2SearchKeepsPolicyNamespacesApart`
  (DC 2b) on `testredis.Client(t, 0)`, with `EnsureCacheIndex` and the drop-at-end helper of
  `tier2_index_ready_test.go`.
- `gateway/internal/httpapi/mixed_lane_test.go`: `policyNS = "policy-returns-01@product-kettle-01"`, only after
  the author's approval in §4 (DC 3).
- `evidence/replay_example_b.sh LABEL` (DC 4), adapted from `docs/work/2026-11-07-tier2-doc-examples/ask.sh`
  and this repo's `run_fl_probe.sh` pattern. It exits 2 at pressure 4 and 1 if `:8080` or `:50051` is taken.
  It runs `make cache-reset`, then starts `LANE_SIGMA_HI=0.20 make dev` in the background (MIXED off, set
  explicitly), logging to `evidence/dev_$LABEL.log`, and waits for `/stats`. It sends the three questions:
  Q2 "How long is the warranty on these headphones?" for H1, Q3 "What warranty period do these headphones
  come with?" for H1, and Q4 (Q2's words) for H2. It saves `cache`, `similarity`, `lane`, `namespace`,
  `sources` and `latency_ms` of each to `evidence/replay_$LABEL.jsonl`, but **no answer text**, which can carry
  corpus text. It prints the pressure at start, before each request, and at end, then stops the stack as
  `run_fl_probe.sh` does.
- Docs: as DC 5.

**Failure modes, silent ones first.**
1. **POLICY and MIXED namespaces meet** (a shared form). A POLICY request is served a MIXED entry, or the
   reverse, with no error. Caught by DC 1(c), and DC 1(e) pins the form.
2. **The write path and the search path build different POLICY namespaces.** No POLICY entry is found again.
   The POLICY hit rate falls to zero, which reads like ADR-024's expected cost. Caught by DC 2(a): a
   same-product paraphrase is still a TIER2_HIT after the real write-back. Also caught by DC 4 (Q3 is still
   judged).
3. **Redis does not match the new value** (an unescaped `@`, or the TAG field splitting it). Every POLICY
   lookup is a miss, with no error. Caught by DC 2(b) on a real Redis, and by DC 4.
4. **The product does not reach the served namespace** (an empty product on one path). Cross-product reuse
   goes on. Caught by DC 2(a) (product B gets a MISS with nothing judged) and by DC 4 (Q4).
5. **The no-product case drifts**, for example a fallback to the rank-1 product chunk. Offline tools and
   old fixtures change meaning. Caught by DC 1(b) and the existing lane tests, which pin `""` cases.
6. **The stale test is loosened** instead of updated. The MIXED arm's label check would then prove nothing.
   Caught by DC 3: the diff changes only the `policyNS` value.

**Edge cases.**
- A crafted `product_id` that holds `@` or `|` (ADR-025 refuses only a blank one). It can only meet a namespace
  written under another crafted id, so only that client's own entries. The SPEC lane has the same property
  today. The client is trusted to name its product.
- The MIXED arm. With the arm on, a mixed grounding stays MIXED (`product|policy`). With it off, the same
  grounding is POLICY (`policy@product`). A run uses one arm, so no entry crosses arms.
- Entries written before the change have no product in their POLICY namespace, and no request reaches them.
  `make cache-reset` removes them, and a measured run starts empty.
- Tier 1 and coalescing are keyed by product already (ADR-018), and invalidation goes by chunk ID. Both are
  unchanged.

**Unknowns.**
- U1: how far POLICY hits fall on `v1`. The judge cost run had 6 cross-product hits of 94 (2 correct,
  4 wrong). Phase 6 measures it, not this task.
- U2: whether Example B's retrieval still ranks as it did on 7 Nov. The before run settles it: if Q3 or Q4
  is not judged there, the replay cannot show the change, and the step stops and reports.

**Verification.**
- DC 1: `go test ./internal/reuse -run Policy -v`, once on the unchanged code (saved), once after.
- DC 2: `make test-go`, which runs the httpapi test and the cache test on the test Redis.
- DC 3: the `off` case run after the change (saved), the approval in §4, then `git diff` of the file.
- DC 4: `replay_example_b.sh before` on the unchanged code, `replay_example_b.sh after` on the changed code.
- DC 5: greps of each changed doc. DC 6: `make verify`, and `git status --porcelain gateway` shows ` M` only
  on `lane.go` and `mixed_lane_test.go`.

## 4. Findings

**The stale test (DC 3), 2026-11-10.** After step 2.1, `make test-go` has one failure,
`TestMixedLaneLabelMatchesRule/off` (`mixed_lane_test.go:234`): `cache = "MISS", want TIER2_HIT: the request
did not reach the entry in "policy-returns-01"` (`evidence/dc3_stale.out`). Its request carries
`product-kettle-01` and lands in the POLICY lane on the off arm, so it now searches
`policy-returns-01@product-kettle-01`, the form DC 1(e) pins. The test seeds its POLICY entry at the old
`policy-returns-01`. The test is stale, as ADR-024 predicted; the code is right. Proposed change: line 195,
`policyNS = "policy-returns-01@product-kettle-01"`, and nothing else.
**Author's approval:** given in chat, 2026-11-10. Step 2.3 makes the change.

**The replay before the change (step 1.5).** Q4 was judged against H1's entry (similarity 1.0), so the
replay sees the bug's precondition. But this time the support gate refused both Q3 and Q4 (`S_lex` 0.4375,
below 0.6), so no wrong answer was served, unlike Example B (e) on 7 Nov: the generated answer differs
between runs. DC 4 compares judged against not judged, so it still holds.

**A stale comment that §3 missed.** `lane.go:47-58`, the `LaneMixed` comment, says a mixed question forced
into the POLICY lane "DROPS the product entirely". Since ADR-024 that is true only without a `product_id`.
Approved by the author, 2026-11-10: keep the paragraph as history and add one note after it
(plan.md Phase 6). Phase 7 then re-runs every done condition, so Phase 5 is marked replaced.

**Step 4.4 stopped, 2026-11-10: a miscount in the plan.** Its check printed `8`, `0`, `0`, `2`, against "at
least 3" for `@product-electronics`. The plan's new text for 4.4 holds that string twice (Step 4's POLICY
row and Example A, Question 5); the third match in plan.md is the step's own `grep` command. All eight
replacements are in place (`git diff`: +21 −14). Fix: 4.4's pass value is corrected to 2. No doc or code
changes. That count proves the cause, so no `rca-analyst` was spawned.

**Step 7.3's command, 2026-11-10.** Its `GO_TEST_FLAGS='-v -run A|B'` reaches the Makefile recipe
unquoted, so the shell read `|` as a pipe and no test ran. The executor's one quick fix quoted the pattern
(`GO_TEST_FLAGS="-v -run 'A|B'"`), and both tests passed. The main session's re-check used the quoted form.

**Main-session re-check, 2026-11-10.** `make verify` exits 0 (rag 94, experiments 1117, Go all ok). DC 1–3
were re-run with `-count=1`, and DC 4–6 were read from the evidence and the tree. All pass.
