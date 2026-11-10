# Plan — The POLICY namespace names the product too (ADR-024)

Design: design.md (approved 2026-11-10)

**Rules for every step.**
- `$T` means `docs/work/2026-11-10-policy-namespace-product`. A command that uses it starts with
  `T=docs/work/2026-11-10-policy-namespace-product;`. Every command runs from the repo root unless it starts
  with `cd gateway`.
- A step marked **(model)** loads a model. Right before it, run `sysctl -n kern.memorystatus_vm_pressure_level`.
  `1` or `2`: go on, and write the level in the step's Result. `4`: stop and report. Every such step is
  `citable: no`.
- Existing tests are never edited (`execution.md`), with one exception: step 2.3, and only after the author's
  dated approval is in design.md §4.
- Go tests that need Redis run only through `make test-go` (the test server on `:6390`), never against `:6379`.
- On a failed check: one quick fix only if the cause is obvious and local, then stop and report (`execution.md`).
- `- [-]` marks a step that a later phase replaced, so it is not run; the banner does not count it.
- Baseline, 2026-11-10, unchanged code: `make verify` passes (rag 94, experiments 1117, Go all ok).

## Phase 1 — Before the change: the new tests, and the replay

- [x] 1.1 Write the namespace unit tests, and run them on the unchanged code.
  - Files: `gateway/internal/reuse/lane_policy_product_test.go` (new)
  - What (design.md §3). Use these chunk sets: `policyOnly = ["policy-returns-01#chunk-0", "policy-returns-01#chunk-1"]`,
    the same two in the other order, and `mixed = ["product-kettle-01#chunk-0", "policy-returns-01#chunk-0",
    "product-kettle-01#chunk-1"]`.
    - `TestPolicyNamespaceNamesTheProduct`, with three subtests:
      - `two_products_two_namespaces` (DC 1a): `Namespace(LanePolicy, policyOnly, "product-kettle-01")` differs
        from the same call with `"product-headphones-03"`, and the reordered set with `"product-kettle-01"`
        gives the same value as `policyOnly` with it.
      - `no_product_is_the_policy_doc` (DC 1b): `Namespace(LanePolicy, policyOnly, "") == "policy-returns-01"`.
      - `the_form` (DC 1e): `Namespace(LanePolicy, policyOnly, "product-kettle-01") == "policy-returns-01@product-kettle-01"`.
    - `TestPolicyAndMixedNamespacesNeverMeet` (DC 1c): for each product in `{"product-kettle-01",
      "product-headphones-03", ""}` and each set in `{policyOnly, mixed}`, the POLICY namespace differs from the
      MIXED one built from the same set and product, whenever both are non-empty. At least one pair must have
      both non-empty, or the test fails.
    - `TestPolicyEntryOfAnotherProductIsRefused` (DC 1d): `Thresholds{Tau: 0.85}.DecideLane` with a POLICY
      query of `product-kettle-01` (namespace built by `Namespace`) against a POLICY entry built for
      `product-headphones-03`, at similarity 1.0: `Reuse` is false. The same query against the kettle's own
      entry: `Reuse` is true.
      (Read `lane_test.go` first for how `Thresholds` is built there, and build it the same way.)
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; cd gateway && go test ./internal/reuse -run 'TestPolicyNamespaceNamesTheProduct|TestPolicyAndMixedNamespacesNeverMeet|TestPolicyEntryOfAnotherProductIsRefused' -v 2>&1 | tee ../$T/evidence/dc1_before.out`
  - Pass: `two_products_two_namespaces`, `the_form` and `TestPolicyEntryOfAnotherProductIsRefused` FAIL; the
    other two PASS. Any other result, or a failure for another reason: stop and report.
  - Result: added gateway/internal/reuse/lane_policy_product_test.go; on unchanged code `two_products_two_namespaces`, `the_form` and `TestPolicyEntryOfAnotherProductIsRefused` FAIL, the other two PASS (dc1_before.out)

- [x] 1.2 Write the `Ask` test, and run it on the unchanged code.
  - Files: `gateway/internal/httpapi/policy_product_test.go` (new)
  - What (design.md §3). A fake `policyRAG`, built like `mixedRAG` in `mixed_lane_test.go` (refuse `top_k != 0`
    the same way), registered by a helper like `useMixedRAG`. `Retrieve` and `Answer` answer for `kettle.id`
    and `headphones.id` only (anything else is a `codes.InvalidArgument` error) with the chunks
    `["policy-returns-01#chunk-0", "policy-returns-01#chunk-1"]`, texts `["Unopened items may be returned
    within 30 days of delivery.", "Returns are free for unopened items."]`, and the answer `"unopened items may
    be returned within 30 days of delivery"`; `Answer` sends that chunk list as `SourceChunkIds`, with
    `testModel` and `testEpoch`.
    `TestPolicyAnswerIsNotReusedForAnotherProduct`, with `newHarness(t, 1, 0)` and its default band:
    1. `askNear(t, q, 1, 1.0, kettle)` with `q = "Can I return an unopened item?"` → `cache` is `MISS`. Wait
       until `tier2Written()` has one entry; it is in lane `POLICY`.
    2. `askNear(t, q, 1, 1.0, headphones)` (the same words) → `cache` is `MISS`, the response's `similarity` is
       null, and the last namespace in `namespacesSearched()` is not the kettle entry's namespace.
    3. `askNear(t, "May I send back an item I never opened?", 1, hitCos, kettle)` → `cache` is `TIER2_HIT`,
       and its record's `entry_id` is the kettle entry's.
    4. `hs.records(t)`, then on the record of request 2: `cache` `MISS` and no `candidate_entry_id`.
    (Read `cause_test.go` and `mixed_lane_test.go` first for `call`, `record`, `waitFor` and the response readers.)
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; cd gateway && go test ./internal/httpapi -run TestPolicyAnswerIsNotReusedForAnotherProduct -v 2>&1 | tee ../$T/evidence/dc2a_before.out`
  - Pass: the test FAILS at request 2 (the headphones request reaches the kettle's entry). A failure at
    request 1 or 3, or a pass: stop and report.
  - Result: added gateway/internal/httpapi/policy_product_test.go (uses the existing `useRAG` helper); on unchanged code it FAILS at request 2 (`cache = "TIER2_HIT", want MISS`, namespace `policy-returns-01`) (dc2a_before.out)

- [x] 1.3 Write the Redis test.
  - Files: `gateway/internal/cache/tier2_policy_namespace_test.go` (new)
  - What: `TestTier2SearchKeepsPolicyNamespacesApart`, on `testredis.Client(t, 0)` with `NewStore(rdb, 768)`,
    `EnsureCacheIndex`, and the drop-at-end helper of `tier2_index_ready_test.go` (read it first). Three
    `PutTier2` entries, all with the same 768-dim vector, in the namespaces
    `policy-returns-01@product-kettle-01`, `policy-returns-01@product-headphones-03` and `policy-returns-01`.
    For each namespace, `NearestTier2InNamespace(ctx, vec, ns, 3)` returns exactly one entry, its own.
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; make test-go GO_TEST_PKGS=./internal/cache GO_TEST_FLAGS='-v -run TestTier2SearchKeepsPolicyNamespacesApart' 2>&1 | tee $T/evidence/dc2b.out | tail -15`
  - Pass: `--- PASS: TestTier2SearchKeepsPolicyNamespacesApart` (it tests Redis with literal values, so it
    passes before the change). `SKIP` is a fail.
  - Result: added gateway/internal/cache/tier2_policy_namespace_test.go; `--- PASS: TestTier2SearchKeepsPolicyNamespacesApart` on the test Redis :6390, no SKIP (dc2b.out)

- [x] 1.4 Write the replay script.
  - Files: `$T/evidence/replay_example_b.sh` (new)
  - What: design.md §3 "Files", `replay_example_b.sh LABEL`. Read
    `docs/work/2026-11-10-fl-cancel-and-rag-shutdown/evidence/run_fl_probe.sh` and
    `docs/work/2026-11-07-tier2-doc-examples/ask.sh` first, and follow them. In order:
    1. Print the pressure; exit 2 at `4`. Exit 1 if `:8080` or `:50051` has a listener.
    2. `make cache-reset`. If it fails, exit 1.
    3. From the repo root, `LANE_SIGMA_HI=0.20 make dev > $T/evidence/dev_$LABEL.log 2>&1 &`; wait up to 120 s
       for `curl -s localhost:8080/stats`; on timeout print the log's last 30 lines, stop the stack, exit 1.
    4. Three requests, each built with `jq -nc`, each after printing the pressure, with `sleep 2` after each so
       the write-back lands: `Q2` = "How long is the warranty on these headphones?" for
       `product-electronics-b07zj7qg33`; `Q3` = "What warranty period do these headphones come with?" for the
       same product; `Q4` = Q2's words for `product-electronics-b079jfb616`. Append one JSON line per request
       to `$T/evidence/replay_$LABEL.jsonl`: `label`, `product_id`, `pressure`, and from the response `cache`,
       `similarity`, `lane`, `namespace`, `sources`, `latency_ms`. **Never the answer text**: it can carry
       corpus text.
    5. Print `grep -o 'mixed_lane=[a-z]*' $T/evidence/dev_$LABEL.log | head -1` and the pressure at end; stop the
       stack as `run_fl_probe.sh` does (TERM the `:8080` PID, wait up to 90 s for `make`, TERM `:50051` if it is
       still held).
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; bash -n $T/evidence/replay_example_b.sh && grep -c answer $T/evidence/replay_example_b.sh`
  - Pass: no syntax error; the count is `0` (the script never names the answer field).
  - Result: added evidence/replay_example_b.sh; `bash -n` clean, `grep -c answer` = 0 (after rewording one echo from "did not answer" to "did not respond"); it also refuses if its two output files already exist

- [x] 1.5 **(model)** Replay Example B on the unchanged code. `citable: no`.
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; bash $T/evidence/replay_example_b.sh before; cat $T/evidence/replay_before.jsonl`
  - Pass: `mixed_lane=off`. Q2 `cache` is `MISS`. Q3 `similarity` is not null. Q4 `similarity` is not null (Q4
    was judged against H1's entry: the bug's precondition, as in `Tier 2.md` Example B (e)). If Q3 or Q4 is
    not judged, stop and report (design.md U2).
  - Result: `mixed_lane=off`; Q2 MISS (sim null), Q3 MISS sim 0.9256, Q4 MISS sim 1.0, all in `policy-warranty-electronics`; Q3 and Q4 were judged and refused by the support gate (cause=SUPPORT, lex 0.4375), not served; pressure 1 at start and Q2, 2 (yellow) at Q3, Q4 and end, citable: no (replay_before.jsonl, dev_before.log)

## Phase 2 — The change

- [x] 2.1 Change the POLICY branch of `Namespace`.
  - Files: `gateway/internal/reuse/lane.go`
  - What (design.md §3 "Files"): `const policyProductSeparator = "@"` with its comment; the POLICY branch
    returns `""` if there is no policy chunk, `policy` if `productID == ""`, else `policy +
    policyProductSeparator + productID` (no fallback to a product chunk). Restate for ADR-024 the file header's
    POLICY bullet, `Namespace`'s doc table (add the POLICY form with a product), and `mixedSeparator`'s note.
    Nothing else in the file changes.
  - Run: `cd gateway && gofmt -l internal/reuse; go test ./internal/reuse -v -run 'Policy' 2>&1 | tail -20; go test ./internal/reuse`
  - Pass: `gofmt -l` prints nothing; every `Policy` test and subtest PASSES; the package is `ok`.
  - Result: lane.go changed (+30 -9: `policyProductSeparator`, POLICY branch, header bullet, `Namespace` table, `mixedSeparator` note); gofmt clean; all 3 new tests and subtests PASS, package `ok`

- [x] 2.2 Run all Go tests; one existing test is expected to fail. Then stop for the author.
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; make test-go GO_TEST_FLAGS=-v 2>&1 | tee $T/evidence/dc3_stale.out | grep -E '^(--- FAIL|FAIL|ok)'`
  - Pass: the only failing test is `TestMixedLaneLabelMatchesRule/off`, failing with `cache = "MISS", want
    TIER2_HIT: the request did not reach the entry in "policy-returns-01"` (its request now searches
    `policy-returns-01@product-kettle-01`, the form 1.1 pins). `TestMixedLaneLabelMatchesRule/on`,
    `TestPolicyAnswerIsNotReusedForAnotherProduct` and `TestTier2SearchKeepsPolicyNamespacesApart` PASS.
    **Then stop and report**: step 2.3 needs the author's approval. Any other failure: stop and report.
  - Result: the only FAIL is `TestMixedLaneLabelMatchesRule/off` (`cache = "MISS", want TIER2_HIT: the request did not reach the entry in "policy-returns-01"`); `/on`, `TestPolicyAnswerIsNotReusedForAnotherProduct` and `TestTier2SearchKeepsPolicyNamespacesApart` PASS; other packages ok; 4 pre-existing live SKIPs (TestSeam, TestSupportLive, TestSupportSample, TestMeasureWriterDrain); STOPPED for the author's approval (dc3_stale.out)

- [x] 2.3 Update the stale test — only after the author's approval.
  - Precondition: design.md §4 holds the author's approval of this change, with its date. If it does not,
    stop and report.
  - Files: `gateway/internal/httpapi/mixed_lane_test.go`
  - What: line 195, `policyNS = "policy-returns-01"` becomes `policyNS = "policy-returns-01@product-kettle-01"`.
    Nothing else in the file.
  - Run: `git diff --stat gateway/internal/httpapi/mixed_lane_test.go; git diff -U0 gateway/internal/httpapi/mixed_lane_test.go | grep -E '^[-+][^-+]'; make test-go 2>&1 | grep -E '^(--- FAIL|FAIL|ok)'`
  - Pass: `1 file changed, 1 insertion(+), 1 deletion(-)`; the two changed lines are the `policyNS` line;
    every package `ok`, no `FAIL`.
  - Result: mixed_lane_test.go line 195 `policyNS` now `"policy-returns-01@product-kettle-01"`; diff is `1 file changed, 1 insertion(+), 1 deletion(-)`, only that line; `make test-go`: every package ok, no FAIL

- [x] 2.4 Lint.
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; make lint`
  - Pass: no error.
  - Result: `make lint`: `go vet ./...` clean, ruff "All checks passed!", exit 0

## Phase 3 — The replay after the change

- [x] 3.1 **(model)** Replay Example B on the changed code. `citable: no`.
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; bash $T/evidence/replay_example_b.sh after; cat $T/evidence/replay_after.jsonl`
  - Pass: `mixed_lane=off`. Q2 `cache` is `MISS`, and its `namespace` is Q2's `namespace` in `replay_before.jsonl`
    followed by `@product-electronics-b07zj7qg33`. Q3 `similarity` is not null. Q4 `cache` is `MISS`,
    `similarity` is null, and its `namespace` ends in `@product-electronics-b079jfb616`.
  - Result: `mixed_lane=off`; Q2 MISS in `policy-warranty-electronics@product-electronics-b07zj7qg33`; Q3 TIER2_HIT sim 0.9256 (same-product reuse kept, served this time); Q4 MISS, similarity null, namespace `...@product-electronics-b079jfb616`; pressure 1 at start and Q2, 2 (yellow) at Q3, Q4 and end, citable: no (replay_after.jsonl, dev_after.log)

## Phase 4 — Docs

- [x] 4.1 Bump the contract to v0.32.
  - Files: `docs/contracts/interfaces.md`
  - What: five exact replacements; each old text occurs once (checked 2026-11-10). Copy the new text exactly.
    1. Line 3: `Draft v0.31` becomes `Draft v0.32`. (`**Revised:** 2026-11-10` stays.)
    2. `**Current version: v0.31** (2026-11-10).` becomes `**Current version: v0.32** (2026-11-10).`
    3. §A, the `product_id` row. Old:
       ```
       Read **only** by the spec lane, to pin which product that lane's namespace names; the policy lane ignores it, because scoping a policy answer by product spends capacity on one answer per product.
       ```
       New:
       ```
       Read by the spec lane, to pin which product that lane's namespace names, and **since v0.32 by the policy lane too** (ADR-024): a POLICY namespace is `{policy_doc}@{product_id}`, so a policy answer is reused only for the product it was written for, at the cost of one entry per product.
       ```
    4. §D, the `t2:` block. Old (one line):
       ```
              hit_count         <int>            # reuse-value signal (future admission-control idea)
       ```
       New: that same line, then these two lines below it, aligned like it:
       ```
              namespace         <tag>            # reuse partition (reuse.Namespace): SPEC {product_id}; POLICY {policy_doc}@{product_id} (v0.32, ADR-024); MIXED {product_id}|{policy_doc}. Without a product_id, the rank-1 document of the kind
              lane              <string>         # SPEC | POLICY | MIXED, read from the entry's own generation sources
       ```
    5. The versioning table: a new row right **after** the `v0.31` row (the top rows rise: v0.28 … v0.31):
       ```
       | **v0.32** | 2026-11-10 | **The POLICY namespace names the product** (**ADR-024**, item 5.6; trail `docs/work/2026-11-10-policy-namespace-product/`). With a `product_id` (every `/ask` since v0.30), a POLICY namespace is `{policy_doc}@{product_id}`; without one it stays `{policy_doc}`. §A's `product_id` row is restated, and §D's `t2:` schema now lists `namespace` and `lane`. No wire shape or `.proto` change; `source_chunk_ids`, `t1_key` and `dataset_epoch` are untouched. A cross-product POLICY candidate is now never found (a MISS with `similarity` null), not refused, so POLICY hit rates are not comparable across this commit. `t2:` entries written before it cannot be reached; `make cache-reset` removes them. No citable run exists; the judge cost run `2026-11-01T21-17-56_cfg4_judgecost` is read as before ADR-024 |
       ```
  - Run: `grep -n "v0.32" docs/contracts/interfaces.md | cut -c1-80; grep -c "the policy lane ignores it" docs/contracts/interfaces.md; grep -n '^| \*\*v0.3[12]\*\*' docs/contracts/interfaces.md | cut -c1-30; grep -c 'POLICY {policy_doc}@{product_id}' docs/contracts/interfaces.md`
  - Pass: `v0.32` on line 3, in the §A row, in §D, on the current-version line and in the new row; the
    counts are `0` and `1`; the v0.32 row's line number is one more than the v0.31 row's.
  - Result: interfaces.md bumped to v0.32 (5 replacements, +6 -3 lines): `v0.32` on line 3, §A row (182), §D (466), current-version line (956), new row (964, one after v0.31 at 963); counts `0` and `1`

- [x] 4.2 Mark ADR-024 and F-NAME built.
  - Files: `docs/decisions.md`
  - What: four exact replacements; each old text occurs once (checked 2026-11-10).
    1. Old `**not built** — a task under item 5.6 builds it`; new `**built 2026-11-10** (trail
       `docs/work/2026-11-10-policy-namespace-product/`, `interfaces.md` v0.32)`.
    2. Old `joins the POLICY namespace; not built yet**`; new `joins the POLICY namespace; built 2026-11-10**`.
    3. Old `build task's choice. **Not built yet:** a task under item 5.6 builds it.`; new `build task's choice:
       `{policy_doc}@{product_id}`. **Built 2026-11-10** (trail `docs/work/2026-11-10-policy-namespace-product/`,
       `interfaces.md` v0.32).`
    4. Old `(v0.31; v0.30 went to ADR-025)`; new `(v0.32; v0.30 went to ADR-025, v0.31 to F-L)`.
    Rewrap a changed paragraph line to its width if it grows past it; no other text changes.
  - Run: `grep -n "ADR-024" docs/decisions.md | grep -ciE "not built"; grep -c "Built 2026-11-10" docs/decisions.md; grep -c "v0.31 to F-L" docs/decisions.md`
  - Pass: `0`, then at least `1`, then `1`.
  - Result: decisions.md: 4 replacements (ADR-024 row, F-NAME row, F-NAME paragraph rewrapped to 2 lines, `(v0.32; v0.30 went to ADR-025, v0.31 to F-L)`); counts `0`, `1`, `1`

- [x] 4.3 Restate item 5.6's text in the super-plan.
  - Files: `docs/super-plan.md`
  - What: old `**Decided 2026-11-07: (b), ADR-024. Not built yet**`; new `**Decided 2026-11-07: (b), ADR-024.
    Built 2026-11-10** (trail `docs/work/2026-11-10-policy-namespace-product/`)`. Leave the "Unblocked when"
    cell and the Progress line: `/done` writes them.
  - Run: `grep -c "ADR-024. Not built yet" docs/super-plan.md; grep -c "ADR-024. Built 2026-11-10" docs/super-plan.md`
  - Pass: `0`, then `1`.
  - Result: super-plan.md item 5.6 text now `ADR-024. Built 2026-11-10` with the trail path (1 line changed); counts `0`, `1`

- [x] 4.4 Update `Tier 2.md`.
  - Files: `docs/1-System Docs/Tier 2.md`
  - What: eight exact replacements; each old text occurs once (checked 2026-11-10). Copy the new text
    exactly; rewrap prose to the file's width (about 105 columns), never a table row.
    1. Part 3's setting. Old `**Every request carried a `product_id`**, as the `v1` workload does.`; new: that
       text followed by ` The run was before ADR-024 (10 Nov 2026); where ADR-024 changes a result, the example
       says so.`
    2. Step 4's POLICY row. Old:
       ```
       | POLICY | at least one policy chunk | the document of the **top-ranked** policy chunk | "How long is the warranty on these headphones?" → `policy-warranty-electronics` (Example B) |
       ```
       New:
       ```
       | POLICY | at least one policy chunk | the document of the **top-ranked** policy chunk, then `@` and the `product_id` (ADR-024, since 10 Nov 2026); with no `product_id`, the document alone | "How long is the warranty on these headphones?" on H1's page → `policy-warranty-electronics@product-electronics-b07zj7qg33` (Example B ran before ADR-024 and shows `policy-warranty-electronics`) |
       ```
    3. Step 4's last paragraph. Old: the paragraph that starts `**Why are policy answers not split by
       product?**` and ends `can reach another product.` New:
       ```
       **Why are policy answers split by product?** (ADR-024, built 10 Nov 2026.) A policy answer used to be
       shared by every product the policy covers, which saves cache space. Example B (e) showed the cost: an
       answer that names one product's brand reached another product, and the gate passed it. Now each
       product writes its own policy answers. The cache holds more entries, and a policy question from
       another product's page is a miss.
       ```
    4. Example A, Question 5, step 3. Old: `A policy namespace is shared by every product the` + line break +
       `   policy covers (Step 4).`; new: `A policy namespace was shared by every product the policy covers
       (Step 4). *Since ADR-024 the namespace is `policy-return-electronics@product-electronics-b079jfb616`,
       and step 4 finds nothing: a MISS with nothing judged.*` (rewrap, keeping the 3-space indent).
    5. Example B (e). Old `This is trap 13 of §12a, and no part of the rule can see it.`; new `This is trap 13 of
       §12a, and no part of the rule could see it then. ADR-024 closes it: Question 4's namespace now names H2,
       so it is a MISS with nothing judged (replayed on 10 Nov 2026,
       `docs/work/2026-11-10-policy-namespace-product/evidence/`).`
    6. §12a, false hits, row 13. Old: the cell `**nothing** in the rule; the judge marks it `INCORRECT``; new
       `**the POLICY namespace names the product** (ADR-024, since 10 Nov 2026); before that, nothing in the rule`.
       And in the same row, old `the model writes the product name into a POLICY answer, and the gate passes on
       the policy words`; new `before ADR-024: the model wrote the product name into a POLICY answer, and the
       gate passed on the policy words`.
    7. §12a, false misses, row 6. Old `ADR-018; zero on `v1`, where no question is shared across products`;
       new `ADR-018 for Tier 1, and since ADR-024 the POLICY lane of Tier 2: a policy question from another
       product's page no longer reuses (2 correct cross-product hits in the 1 Nov cost run, not citable)`.
    8. §13. Old `**`product_id` will join the POLICY namespace** (ADR-024, 7 Nov 2026, **not built yet**).`;
       new `**`product_id` joins the POLICY namespace** (ADR-024, decided 7 Nov 2026, **built 10 Nov 2026**).`
       And on the next line, old `show the rule as it runs today, before the change.`; new `show the rule as
       it ran before the change.`
  - Run: `F="docs/1-System Docs/Tier 2.md"; grep -c "ADR-024" "$F"; grep -c "not built yet" "$F"; grep -c "no part of the rule can see it" "$F"; grep -c "@product-electronics" "$F"`
  - Pass: at least `8`; `0`; `0`; at least `2`. (Corrected 2026-11-10 from `3`, a miscount in the plan: the new
    text above holds the string twice; design.md §4.)
  - Result: Tier 2.md: 8 replacements (+21 -14 lines); counts `8`, `0`, `0`, `2` (pass corrected to at least 2)

## Phase 5 — Run and verify, every done condition (numbered as design.md §1)

Replaced by Phase 7, not run: Phase 6 changes `lane.go` after it (design.md §4, 2026-11-10).

- [-] 5.1 `make verify`
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; make verify 2>&1 | tail -40`
  - Pass: no FAIL; Go, rag and experiments suites ran. Any SKIPPED target is listed by name.
  - Result:
- [-] 5.2 DC 1 — the namespace, unit-tested.
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; (cd gateway && go test ./internal/reuse -run 'TestPolicyNamespaceNamesTheProduct|TestPolicyAndMixedNamespacesNeverMeet|TestPolicyEntryOfAnotherProductIsRefused' -v 2>&1 | grep -E '^\s*--- (PASS|FAIL)'); grep -E '^\s*--- FAIL' $T/evidence/dc1_before.out`
  - Pass: every test and subtest PASSES now; the before output shows `two_products_two_namespaces`,
    `the_form` and `TestPolicyEntryOfAnotherProductIsRefused` failing.
  - Result:
- [-] 5.3 DC 2 — the served path keeps products apart.
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; make test-go GO_TEST_PKGS='./internal/httpapi ./internal/cache' GO_TEST_FLAGS='-v -run TestPolicyAnswerIsNotReusedForAnotherProduct|TestTier2SearchKeepsPolicyNamespacesApart' 2>&1 | grep -E '^\s*--- (PASS|FAIL|SKIP)'; grep -E '^\s*--- FAIL' $T/evidence/dc2a_before.out`
  - Pass: both tests PASS, neither SKIPS; the before output shows the `Ask` test failing.
  - Result:
- [-] 5.4 DC 3 — the stale test, approved first.
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; grep -n "TestMixedLaneLabelMatchesRule" $T/design.md | tail -3; grep -E 'did not reach the entry in "policy-returns-01"' $T/evidence/dc3_stale.out; git diff -U0 gateway/internal/httpapi/mixed_lane_test.go | grep -E '^[-+][^-+]'; (cd gateway && go test ./internal/httpapi -run TestMixedLaneLabelMatchesRule -v 2>&1 | grep -E '^\s*--- (PASS|FAIL)')`
  - Pass: §4 names the test with the author's approval and its date; the stale failure was saved; the diff is
    the `policyNS` line only; `on` and `off` PASS.
  - Result:
- [-] 5.5 DC 4 — the replay, before and after. `citable: no`.
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; cat $T/evidence/replay_before.jsonl $T/evidence/replay_after.jsonl; grep -o 'mixed_lane=[a-z]*' $T/evidence/dev_before.log $T/evidence/dev_after.log | sort -u`
  - Pass: as in 1.5 and 3.1, with the pressure of every request shown, and `mixed_lane=off` in both logs.
  - Result:
- [-] 5.6 DC 5 — the docs.
  - Run: the Run commands of 4.1, 4.2, 4.3 and 4.4, and `grep -n "ADR-024" gateway/internal/reuse/lane.go`.
  - Pass: as in 4.1–4.4, and `lane.go` names ADR-024 in its header, at `Namespace` and at `mixedSeparator`.
  - Result:
- [-] 5.7 DC 6 — `make verify`, and only the expected Go files changed.
  - Run: `git status --porcelain gateway`
  - Pass: 5.1 passed; ` M` only on `gateway/internal/reuse/lane.go` and
    `gateway/internal/httpapi/mixed_lane_test.go`; the three new test files show `??`.
  - Result:

## Phase 6 — Found in build: a stale comment (design.md §4, approved by the author 2026-11-10)

Run after Phase 4. Phase 5 is replaced by Phase 7, so the last run of every done condition follows this change.

- [x] 6.1 Add an ADR-024 note to the `LaneMixed` comment.
  - Files: `gateway/internal/reuse/lane.go`
  - What: right after the comment line `// Namespace and DecideLane.` (it occurs once, and ends the `LaneMixed`
    comment) and before `LaneMixed Lane = "MIXED"`, add these lines, with the same tab indent:
    ```
    	//
    	// ADR-024 (2026-11-10): the paragraph above describes the POLICY lane before ADR-024. With a
    	// product_id, a POLICY namespace keeps the product ({policy_doc}@{product_id}), so the
    	// cross-product case it names no longer arises for a request that carries one. It still holds
    	// without a product_id. What is left of MIXED's effect is mostly lane separation.
    ```
    Nothing else in the file changes.
  - Run: `cd gateway && gofmt -l internal/reuse; go test ./internal/reuse; sed -n '/LaneMixed is stratum D/,/LaneMixed Lane = "MIXED"/p' internal/reuse/lane.go | grep -c ADR-024`
  - Pass: `gofmt -l` prints nothing; `ok`; the count is `1`.
  - Result: lane.go: 5-line ADR-024 note added after the `LaneMixed` comment (blank `//` line plus 4 lines, nothing else); gofmt clean, `ok`, count `1`

## Phase 7 — Run and verify, every done condition (numbered as design.md §1)

- [x] 7.1 `make verify`
  - Run: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"; make verify 2>&1 | tail -40`
  - Pass: no FAIL; Go, rag and experiments suites ran. Any SKIPPED target is listed by name.
  - Result: `make verify` exit 0: Go 10 packages ok, rag 94 passed, experiments 1117 passed; no FAIL, no SKIPPED target (verify_final.out)
- [x] 7.2 DC 1 — the namespace, unit-tested.
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; (cd gateway && go test ./internal/reuse -run 'TestPolicyNamespaceNamesTheProduct|TestPolicyAndMixedNamespacesNeverMeet|TestPolicyEntryOfAnotherProductIsRefused' -v 2>&1 | grep -E '^\s*--- (PASS|FAIL)'); grep -E '^\s*--- FAIL' $T/evidence/dc1_before.out`
  - Pass: every test and subtest PASSES now; the before output shows `two_products_two_namespaces`,
    `the_form` and `TestPolicyEntryOfAnotherProductIsRefused` failing.
  - Result: DC 1: all 3 tests and 3 subtests PASS now; dc1_before.out shows `two_products_two_namespaces`, `the_form` and `TestPolicyEntryOfAnotherProductIsRefused` FAIL
- [x] 7.3 DC 2 — the served path keeps products apart.
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; make test-go GO_TEST_PKGS='./internal/httpapi ./internal/cache' GO_TEST_FLAGS='-v -run TestPolicyAnswerIsNotReusedForAnotherProduct|TestTier2SearchKeepsPolicyNamespacesApart' 2>&1 | grep -E '^\s*--- (PASS|FAIL|SKIP)'; grep -E '^\s*--- FAIL' $T/evidence/dc2a_before.out`
  - Pass: both tests PASS, neither SKIPS; the before output shows the `Ask` test failing.
  - Result: DC 2: both tests PASS, no SKIP; dc2a_before.out shows the Ask test FAIL. The plan's command pipes in the shell (unquoted `|` in GO_TEST_FLAGS: "command not found", no test ran); quick fix: `GO_TEST_FLAGS="-v -run 'A|B'"`. Live indexes idx:corpus and idx:cache intact after both runs
- [x] 7.4 DC 3 — the stale test, approved first.
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; grep -n "Author's approval" $T/design.md; grep -E 'did not reach the entry in "policy-returns-01"' $T/evidence/dc3_stale.out; git diff -U0 gateway/internal/httpapi/mixed_lane_test.go | grep -E '^[-+][^-+]'; (cd gateway && go test ./internal/httpapi -run TestMixedLaneLabelMatchesRule -v 2>&1 | grep -E '^\s*--- (PASS|FAIL)')`
  - Pass: §4 holds the author's approval with its date; the stale failure was saved; the diff is the
    `policyNS` line only; `on` and `off` PASS.
  - Result: DC 3: §4 line 232 holds "Author's approval: given in chat, 2026-11-10"; the stale failure is in dc3_stale.out (`did not reach the entry in "policy-returns-01"`); the diff is the `policyNS` line only; `TestMixedLaneLabelMatchesRule` `on` and `off` PASS
- [x] 7.5 DC 4 — the replay, before and after. `citable: no`.
  - Run: `T=docs/work/2026-11-10-policy-namespace-product; cat $T/evidence/replay_before.jsonl $T/evidence/replay_after.jsonl; grep -o 'mixed_lane=[a-z]*' $T/evidence/dev_before.log $T/evidence/dev_after.log | sort -u`
  - Pass: as in 1.5 and 3.1, with the pressure of every request shown, and `mixed_lane=off` in both logs.
  - Result: DC 4: before and after as in 1.5 and 3.1 (before: Q2 MISS sim null, Q3 sim 0.9256, Q4 sim 1.0 all in `policy-warranty-electronics`; after: Q2 MISS `...@<H1>`, Q3 sim 0.9256 TIER2_HIT, Q4 MISS sim null `...@<H2>`); pressure shown for every request (1, 2, 2 before; 1, 2, 2 after); `mixed_lane=off` in both logs; no answer text in either jsonl; citable: no
- [x] 7.6 DC 5 — the docs.
  - Run: the Run commands of 4.1, 4.2, 4.3 and 4.4, and `grep -n "ADR-024" gateway/internal/reuse/lane.go`.
  - Pass: as in 4.1–4.4, and `lane.go` names ADR-024 in its header, at `LaneMixed`, at `Namespace` and at
    `mixedSeparator`.
  - Result: DC 5: the Run commands of 4.1 to 4.4 give the same results as when ticked (4.1: v0.32 in the 5 places, counts `0`,`1`, rows 963/964; 4.2: `0`,`1`,`1`; 4.3: `0`,`1`; 4.4: `8`,`0`,`0`,`2`); `lane.go` names ADR-024 in its header (15), at `LaneMixed` (60), `Namespace` (183) and `mixedSeparator` (252)
- [x] 7.7 DC 6 — `make verify`, and only the expected Go files changed.
  - Run: `git status --porcelain gateway`
  - Pass: 7.1 passed; ` M` only on `gateway/internal/reuse/lane.go`, `gateway/internal/httpapi/mixed_lane_test.go`
    and `gateway/cmd/gateway/main.go` (the gateway drain fix from before this task, not touched here); the
    three new test files show `??`.
  - Result: DC 6: 7.1 passed; ` M` only on `lane.go`, `mixed_lane_test.go` and `cmd/gateway/main.go` (the drain fix from before this task, not touched); the three new test files show `??`
