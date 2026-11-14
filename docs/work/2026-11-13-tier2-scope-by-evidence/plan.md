# Plan — Tier-2 trial: scope by evidence

Design: design.md (approved 2026-11-13)

Rules for every step: `.claude/rules/execution.md`. Never commit. Before any step that loads a model, run
`sysctl -n kern.memorystatus_vm_pressure_level`: 1 or 2 may proceed (write the level in `Result:`), 4 stops.
`E` below means `docs/work/2026-11-13-tier2-scope-by-evidence/evidence`; text that may hold Amazon-PQA
wording goes in `E/private/`.

## Phase 0 — Baselines before any change

- [x] 0.1 Record the hashes that done conditions 2 and 10 compare against.
  - Run: `shasum -a 256 data/workload-v1-validation.json data/workload-v1-test.json data/workload-manifest.json > E/sha-before.txt`;
    `awk '/^## 1\. Spec/,/^## 2\. Impact/' docs/work/2026-11-13-tier2-scope-by-evidence/design.md | shasum -a 256 > E/spec-sha.txt`
  - Pass: both files exist with one hash per line.
  - Result: wrote E/sha-before.txt (3 hashes) and E/spec-sha.txt (1 hash, 86631c22…).
- [x] 0.2 Record the old prompt verbatim before editing `generate.py`.
  - Files: `experiments/judge/reference-prompt-v1.txt` (new): the exact string of today's
    `generate._PROMPT_TEMPLATE`, no trailing newline.
  - Run: `shasum -a 256 experiments/judge/reference-prompt-v1.txt`
  - Pass: the hash equals `prompt_sha256` in `experiments/judge/reference-writer-v1.json` (`3e224f45…`).
  - Result: wrote experiments/judge/reference-prompt-v1.txt; sha256 3e224f45… equals reference-writer-v1.json.

## Phase 1 — Implement, Python side (design §3.3 A, B, D, E)

- [x] 1.1 Add `bool no_answer = 6;` to `AnswerChunk`, with a comment pointing at interfaces.md §B v0.37.
  - Files: `contracts/rag/v1/rag.proto`
  - Run: pressure check; `make proto`
  - Pass: stubs regenerate in Go and Python; `git diff --stat` shows only the proto and generated files.
  - Result: pressure 1; proto has field 6; Go (`NoAnswer`) and Python stubs regenerated (stubs are gitignored, so git diff shows only the proto).
- [x] 1.2 New generator prompt and fallback (§3.3 B).
  - Files: `rag/src/rag/generate.py`: `_SYSTEM_PROMPT` (P1, word for word from §3.3 B, plus one worked
    example), `_PROMPT_TEMPLATE = "Facts:\n{context}\n\nQuestion: {query}\nAnswer:"`, `FALLBACK_ANSWER`
    (the sentence in §3.3 B), `finalize(text: str) -> tuple[str, bool]`, `prompt_sha256() -> str`
    (sha256 of `system + "\x00" + template`); `_request_body` adds `"system": _SYSTEM_PROMPT`.
  - Pass: `python -c "from rag import generate; print(generate.prompt_sha256())"` prints a hash.
  - Result: generate.py has P1 word for word, the new template, FALLBACK_ANSWER, finalize, prompt_sha256 (7a6acf97...), and "system" in the request body.
- [x] 1.3 The service applies `finalize` and sets the flag.
  - Files: `rag/src/rag/server.py` (`Answer`)
  - Pass: `make test` still has no new FAIL in `rag/tests` other than the pinned-prompt test of 3.1.
  - Result: server.py Answer calls finalize and sets no_answer; I made the human-approved one-line edit to test_request_body_is_unchanged (added "system": generate._SYSTEM_PROMPT, design 4); rag/tests: 93 pass, only test_prompt_is_unchanged fails (fixed at 3.1).
- [x] 1.4 The reference writer reads its prompt from the pinned file (§3.3 B, decoupling).
  - Files: `experiments/scripts/judge_references.py` (the check at about line 316)
  - Pass: the function refuses when the file's hash differs from `reference-writer-v1.json`.
  - Result: judge_references.py: new WRITER_PROMPT_PATH and load_writer_prompt; writer_block hashes the pinned file and refuses a changed one (checked by hand); answer_with_writer builds its prompt from the file, so references keep the old prompt.
- [x] 1.5 `judge.py` drops `prompt_sha256` from the generator fields compared with the reference set,
  records both hashes in `summary.json`, and keeps the writer-prompt check.
  - Files: `experiments/scripts/judge.py` (`version_fields`, about line 297)
  - Result: judge.py no longer compares generator.prompt_sha256 (kept a presence check), summary.json has generator_prompt_sha256 {run, reference_set}, writer check kept; test_judge.py: only the 2 refusal tests of design 4 fail (moved at 3.2).
- [x] 1.6 `run_manifest.py` takes `generator.prompt_sha256` from `generate.prompt_sha256()`, adds
  `scope_arm` to `ARM_KEYS`, reads it from the records and from the gateway's start-up line
  (`scope_arm=(on|off)`), and checks that they agree.
  - Files: `experiments/scripts/run_manifest.py`
  - Result: run_manifest.py: scope_arm in ARM_KEYS (optional, so old runs keep four arms), read from records and the start-up line and checked to agree; generator.prompt_sha256 now generate.prompt_sha256() via a wrapper; all 118 existing run_manifest tests pass.
- [x] 1.7 `replay.py` drops queries with an empty `product_id` before ordering and prints
  `skipped_no_product_id` in its summary (§3.3 A).
  - Files: `experiments/scripts/replay.py`
  - Result: replay.py: replay() has a keyword skip_no_product_id (default off so the 23 existing replay tests pass unchanged); main() turns it on, so make replay skips and counts them; dry run on the real validation split with a fake sender: 606 sent, 16 skipped.
- [x] 1.8 The shared fixture (§3.3 D, done condition 7).
  - Files: `contracts/scope/cases.json` (new): `tokenize` cases (text → sorted tokens, including digits,
    hyphens, units and a two-letter token); `scope` cases (lane, answer, product and policy category,
    bound words, has-title → `product|shared`), covering: neutral → shared, a bound word → product,
    another category → product, a missing title vector → product, a SPEC or MIXED lane → product;
    `project` cases (three small vectors `v`, `t` and the expected `v′` to 1e-9).
  - Result: wrote contracts/scope/cases.json (11 tokenize, 10 scope, 9 project cases; the tokenize and project cases re-derived by hand in Python and agree).
- [x] 1.9 Document metadata (§3.3 D).
  - Files: `rag/src/rag/docmeta.py` (new): `scope_tokens(text) -> set[str]`,
    `bound_words(product, category_policy_tokens, df, n_products, cut=0.10) -> list[str]`,
    `build(corpus_dir) -> list[dict]`, `write(client, rows)`, and `main()`; `Makefile` target `docmeta`
    (memory check first, like `ingest`).
  - Pass: `make help` lists `docmeta`.
  - Result: added rag/src/rag/docmeta.py (scope_tokens, bound_words, build, write, main) and Makefile target docmeta; build() offline on data/v1 gives 164 categories, 152 products, 13-213 bound words each; ruff clean; make help lists docmeta.
- [x] 1.10 `experiments/scripts/scope_calibrate.py` (new) and target `scope-calibrate`: the τ_P rule of
  §1 on `data/v1-draft/workload/vectors.json` (validation ids) and the `title_vec`s read from Redis;
  prints raw pass share at τ = 0.85, τ_P, and pair counts; writes `E/scope-calibrate.json`.
  - Result: added experiments/scripts/scope_calibrate.py (project, calibrate, read_titles, main) and Makefile target scope-calibrate; smoke test with random title vectors ran (142 policy questions, 12 documents, 1322 pairs; not a result, the real run is 6.6); ruff clean.
- [x] 1.11 `experiments/scripts/prompt_probe.py` (new) and target `prompt-probe`: seed 20261113, 100
  `answerable: true` and 20 `false` validation queries with a `product_id`; retrieve with
  `rag.retrieve.retrieve(q, product_id=…)`; generate with the old prompt (from
  `experiments/judge/reference-prompt-v1.txt`, no system text) and the served prompt; print the
  meta-phrase shares and the no-answer shares of condition 4; answers to `E/private/prompt-probe.jsonl`.
  - Result: added experiments/scripts/prompt_probe.py (draw seed 20261113: 100 answerable + 20 not; probe; shares) and Makefile target prompt-probe; checked offline with fakes (sample is 120, order-independent); ruff clean; the live run is 6.3.
- [x] 1.12 `experiments/scripts/scope_trial.py` (new) and target `scope-trial RUNS="<off> <on>"`: reads
  both runs' `raw/requests.jsonl` and `judge/records.jsonl`; prints, per `query_lane` and `scope_arm`:
  hits, judged correct, judged wrong, Wilson 95 % over requests and over clusters (a cluster is wrong
  when any of its hits is wrong); POLICY misses' judged-wrong share; `write_scope` counts; then the two
  adoption tests of §1 and the verdict `ADOPT` or `KEEP OFF`. Writes `E/scope-trial.json`.
  - Result: added experiments/scripts/scope_trial.py (tally, lanes, wilson, verdict_of_rule, main) and Makefile target scope-trial; an extra new test file experiments/tests/test_scope_trial.py (9 pass) pins the rule, the Tier-1 lane and the cluster count; ruff clean.
- [x] 1.13 Fallback sanity pairs in the format `judge.py sanity()` reads: 2 pairs with an unanswerable
  question and the fallback (expected correct), 2 with an answerable question and the fallback (expected
  incorrect). Hand-written; no Amazon-PQA wording.
  - Files: `experiments/judge/sanity-fallback.jsonl` (new)
  - Result: wrote experiments/judge/sanity-fallback.jsonl: 2 unanswerable questions (reference declines, expected CORRECT) and 2 answerable (expected INCORRECT) with the fixed fallback sentence; only qa_ids and the fallback, no PQA wording; all 4 qa_ids are in the reference index.

## Phase 2 — Implement, Go side (design §3.3 C, D)

- [x] 2.1 `policyDocByVote(chunkIDs []string) string` (count per document, tie → better first rank);
  `Namespace` uses it for POLICY and MIXED's policy part.
  - Files: `gateway/internal/reuse/lane.go`
  - Result: added policyDocByVote (count per policy document, a tie goes to the better first rank) to reuse/lane.go; Namespace uses it for POLICY and MIXED's policy part; go build ok; existing reuse tests, TestNamespaceUsesRankNotSetMembership included, still pass.
- [x] 2.2 `reuse/scope.go` (new, pure): `type Scope string` (`ScopeProduct`, `ScopeShared`),
  `ScopeTokens`, `type DocMeta struct{Category string; TitleVec []float32; BoundWords map[string]struct{}}`
  (or the same fields as arguments, if `cache/` must own the type — keep `reuse/` import-free),
  `DecideScope`, `Project`, `SharedNamespace`.
  - Result: added reuse/scope.go: Scope, DocMeta, ScopeTokens (ASCII-only fold; the Python tokenizer and cases.json now say the same), CanShare (the category guard), DecideScope, Project, SharedNamespace; reuse/ stays stdlib only; go build and vet ok.
- [x] 2.3 `LaneInput.Shared`, `Thresholds.TauP`, `NamespaceDecision.Tau`; `DecideLane` sets `Tau` from
  `Shared`; `Judge` compares similarity with `d.Tau`.
  - Files: `gateway/internal/reuse/lane.go`, `cause.go`
  - Result: reuse: LaneInput.Shared, Thresholds.TauP (rule.go), NamespaceDecision.Tau; DecideLane sets Tau (TauP for a shared candidate, +Inf if TauP is unset or the lane is not POLICY, fail closed); Judge compares with d.Tau; all existing reuse tests pass.
- [x] 2.4 `cache.Store.LoadDocMeta(ctx) (map[string]DocMeta, error)` over `docmeta:*` (SCAN, never KEYS).
  - Files: `gateway/internal/cache/docmeta.go` (new)
  - Result: added gateway/internal/cache/docmeta.go: cache.DocMeta and Store.LoadDocMeta (SCAN, never KEYS; refuses a title vector of the wrong width or bad bound_words); builds; its Redis test is in phase 4.
- [x] 2.5 `Tier2Entry.Scope`, written and read as the field `scope`; empty reads as `product`.
  - Files: `gateway/internal/cache/tier2.go`
  - Result: Tier2Entry.Scope written and read as the plain field scope (not indexed; empty or unknown reads and writes as product); builds.
- [x] 2.6 `AnswerResult.NoAnswer` from `AnswerChunk.no_answer`.
  - Files: `gateway/internal/ragclient/answer.go`
  - Result: ragclient.AnswerResult gains NoAnswer, read from AnswerChunk.no_answer; builds.
- [x] 2.7 The second search of §3.2 in `tryTier2`; `tier2Outcome` gains the shared candidate, its
  similarity and cause, and `HitScope`.
  - Files: `gateway/internal/httpapi/cascade.go`
  - Result: cascade.go: tryTier2 split into productCandidate, judge and sharedCandidate; with ScopeOn and a POLICY request the product candidate is judged first (Tau), then the shared one (projected vector, TauP, category guard); a shared hit fills the primary fields; added Handler.ScopeOn and Handler.DocMeta (handler.go); with the arm off the search and verdict are unchanged; httpapi, reuse and cache tests pass.
- [x] 2.8 Write-back: a `NoAnswer` result returns before the epoch check and writes nothing; otherwise
  `DecideScope`, then a shared write (`SharedNamespace`, projected vector, `Scope: shared`) or today's
  write. Records get the new §H fields.
  - Files: `gateway/internal/httpapi/handler.go`
  - Result: handler.go: a NoAnswer result returns from the closure before the entry id and the epoch check (nothing written, entry_id empty, no_answer true); otherwise DecideScope then a shared write (SharedNamespace, projected key, scope shared) or today's write; the record gets the new fields; with the arm off the write is unchanged; httpapi tests pass.
- [x] 2.9 New record fields, none with `omitempty`: `scope_arm`, `query_lane`, `hit_scope`,
  `write_scope`, `no_answer`, `shared_similarity`, `shared_refusal_cause`.
  - Files: `gateway/internal/telemetry/evallog.go`
  - Result: telemetry.Record gains scope_arm, query_lane, hit_scope, write_scope, no_answer, shared_similarity, shared_refusal_cause, none with omitempty; telemetry tests pass.
- [x] 2.10 `SCOPE_ARM` (`off` default; other values stop the start), `REUSE_TAU_P` (required when on),
  `LoadDocMeta` at start (arm on and a product without `title_vec` stops the start), and
  `scope_arm=… tau_p=…` on the start-up line next to `mixed_lane=`.
  - Files: `gateway/cmd/gateway/main.go`
  - Result: main.go: scopeFromEnv (SCOPE_ARM off by default via the constant scopeArmDefault, other values stop the start; REUSE_TAU_P required in (0,1] when on), checkDocMeta (a product without a title vector, or no product metadata, stops the start with the arm on), LoadDocMeta at start with the arm on, handler.ScopeOn and DocMeta, TauP in Thresholds, and scope_arm=... tau_p=... on the lane_band line next to mixed_lane=; cmd/gateway tests pass.
- [x] 2.11 `gateprobe -routing <requests.jsonl> <workload.json>` (top-chunk and vote correct counts for
  policy-gold questions) and `gateprobe -embedcheck <vectors.json> <n>` (gateway embedding against the
  stored vector, cosine).
  - Files: `gateway/cmd/gateprobe/main.go`
  - Result: gateprobe: -routing <requests.jsonl> <workload.json> (top-chunk and vote correct for policy-gold questions, exit 1 if vote < top) and -embedcheck <vectors.json> <n> (cosine of the gateway's own embedding against the stored vector, exit 1 under 0.9999); the existing -in/-out mode is unchanged; builds and vets; the live runs are 6.5 and 6.6.
- [x] 2.12 `go build ./...` and `go vet ./...` in `gateway/`.
  - Pass: no error.
  - Result: cd gateway: go build ./... and go vet ./... both clean.

## Phase 3 — Unit tests

- [x] 3.1 Move the prompt pin to the new prompt (approved in design §4): `rag/tests/test_server_cancel.py`
  pins `generate.prompt_sha256()`; a new `rag/tests/test_generate_prompt.py` pins it too and tests
  `finalize` (`NO_ANSWER`, `No answer.`, `no_answer`, an answer that only mentions "answer" → unchanged).
  - Run: `pytest rag/tests -q`
  - Result: rag/tests/test_server_cancel.py: test_prompt_is_unchanged now pins generate.prompt_sha256() (7a6acf97...) and the new built prompt hash (design 4, human-approved); new rag/tests/test_generate_prompt.py pins the hash, covers both parts, the request body, finalize (sentinel forms, ordinary answers unchanged); pytest rag/tests: 109 pass.
- [x] 3.2 `experiments/tests/test_judge.py` (approved in design §4): the generator-prompt refusal becomes
  a writer-prompt refusal; add a test that a run whose generator prompt differs from the reference set
  is still judged and both hashes are in the summary.
  - Result: experiments/tests/test_judge.py (human-approved, design 4): removed the generator-prompt row from the disagreement parametrize and turned the generator-prompt refusal into a writer-prompt refusal (plus: a differing generator prompt gives no problem); added a test that such a run is judged and summary.json holds both hashes; 120 tests pass; the diff touches only those regions.
- [x] 3.3 `experiments/tests/test_judge_references.py` (approved in design §4): the writer prompt comes
  from `reference-prompt-v1.txt`; a changed file is refused.
  - Result: experiments/tests/test_judge_references.py (human-approved, design 4): writer_file hashes the pinned reference-prompt-v1.txt; the 'prompt changed' check now changes that file (passed as prompt_path) and expects 'prompt file ... hashes to'; the body test expects the old template from the file; 78 tests pass; 18 lines added, 15 removed.
- [x] 3.4 New pytest: `replay` skips a query with no `product_id` and counts it; the order of the others
  does not depend on it.
  - Result: new experiments/tests/test_replay_skip.py (5 pass): a query with an empty, null or missing product_id is not sent and is counted (3 of 12); 0 is reported when none is skipped; the order of the others is the same with or without them; the command turns the exclusion on.
- [x] 3.5 New pytest: `run_manifest` reads `scope_arm` from records and the start-up line, and refuses
  when they disagree.
  - Result: new experiments/tests/test_run_manifest_scope.py (13 pass): scope_arm is read from the records and from the start-up line, an older run keeps four arms, records or logs that disagree (or a log with the arm and records without) are refused by the check and by build_manifest, and the manifest's generator hash is generate.prompt_sha256().
- [x] 3.6 New pytest reading `contracts/scope/cases.json`: `docmeta.scope_tokens` and the Python
  projection used by `scope_calibrate.py` meet every case; `bound_words` drops a word that is in the
  category's policies and a word above the 10 % cut.
  - Run: `pytest experiments/tests rag/tests -q`
  - Result: new experiments/tests/test_scope_contract.py (34 pass): docmeta.scope_tokens and scope_calibrate.project meet every case of contracts/scope/cases.json (projected vector unit and orthogonal to t); bound_words drops a word in the category's policies and a word above the 10 % cut, and keeps one at exactly 10 %; build() on data/v1 gives 164 categories and 152 products.
- [x] 3.7 Go tests in `reuse/`: the vote (2–1 against rank-1, a tie, MIXED's policy part); a test reading
  `contracts/scope/cases.json` for `ScopeTokens`, `DecideScope` and `Project`; a τ / τ_P test (condition
  13); `TestNamespaceUsesRankNotSetMembership` still passes unchanged.
  - Run: `cd gateway && go test ./internal/reuse/...`
  - Result: new Go tests in reuse/: vote_test.go (2-1 against rank 1, ties either way, stability, MIXED's policy part, SPEC unchanged), scope_contract_test.go (reads contracts/scope/cases.json for ScopeTokens, DecideScope, Project; unit and orthogonal checks), scope_tau_test.go (a shared candidate meets TauP, a product one Tau, fail closed without TauP); go test ./internal/reuse/...: ok; TestNamespaceUsesRankNotSetMembership passes unchanged.
- [x] 3.8 Go tests in `httpapi/` with the fake store: arm off makes one search and writes
  `{doc}@{product}` (condition 6); a `NoAnswer` result writes no Tier-1 key, no Tier-2 record and no
  registration (condition 3); a neutral answer written for product A is served to a paraphrase on
  product B of the same category and not to a product of another category (condition 14).
  - Run: `cd gateway && go test ./internal/httpapi/...`
  - Result: new gateway/internal/httpapi/scope_test.go (fake store, own RAG fake; 9 tests, all pass): arm off makes one search per request and writes {doc}@{product} with scope product even with metadata loaded; a NoAnswer result writes no Tier-1 key, no Tier-2 record, no registration, touch or trim, even with an advanced epoch, and the record says no_answer; arm on shares a neutral answer from product A to B of the same category (raw cosine 0.5, projected 1) and not to the furniture product C; a named answer stays product scope; product match served first; TauP vs Tau through the cascade; legacy entry ignored. Mutation checks (skipping the NoAnswer return, writing the raw key) made the tests fail; handler.go restored; go test ./internal/httpapi: ok.

## Phase 4 — Integration tests

- [x] 4.1 A `testredis` test: a shared entry served and promoted to Tier 1 under two products, then one
  source chunk invalidated; Tier 2 and both Tier-1 keys are gone (condition 8).
  - Run: `make test-go`
  - Result: new Redis tests: deps/scope_shared_test.go (a shared entry promoted to Tier 1 under two more products is gone from Tier 2 and from all three Tier-1 keys after its policy chunk, or the writer product's own chunk, is invalidated; an unrelated entry survives), cache/docmeta_test.go (LoadDocMeta decodes category, float32 LE title vector and bound words; refuses a wrong width and bad JSON) and cache/tier2_scope_test.go (scope round trip; an old entry reads as product); make test-go: all packages ok (6 s).
- [x] 4.2 `make test` and `make lint`.
  - Pass: no FAIL; SKIPPED targets listed by name.
  - Result: make lint: exit 0 (after shortening two comment lines of mine in generate.py); make test: exit 0, no FAIL and no SKIPPED (rag 109 passed, experiments 1393 passed, Go tests ok).

## Phase 5 — Contract and records

- [x] 5.1 `docs/contracts/interfaces.md` v0.37: §B `no_answer` and the fallback; §C `docmeta:{doc_id}`;
  §D `scope`, the shared namespace, the projected key, the vote; §H the seven fields; a version row that
  names ADR-028–030 and says no run is invalidated.
  - Result: interfaces.md v0.37 (2026-11-13): §B no_answer + fallback, §C docmeta, §D vote/scope/shared/v′/τ_P, §H seven keys + I14/I15, §I scope_arm, version row naming ADR-028–030, no run invalidated (checked by the main session 2026-11-14).
- [x] 5.2 `docs/decisions.md`: ADR-028 vote routing (amends ADR-024's rank-1 rule); ADR-029 the prompt,
  the sentinel and the fallback, and the reference writer's own pinned prompt (amends ADR-023); ADR-030
  the scope arm, its cut 0.10, τ_P's rule, product-first serving, the category guard, and ADR-025's
  mechanism moved to replay. Each with `Invalidates:` (no citable run).
  - Result: added ADR-028, 029, 030 to docs/decisions.md after ADR-027 (same heading and field format, each with `Invalidates:` = no citable run) and three summary-table rows; wording and numbers from design.md, no new decision; design.md untouched.

## Phase 6 — Runs (all `citable: no`)

- [x] 6.1 Pressure check; `make docmeta`.
  - Pass: it reports 164 categories and 152 title vectors (condition 9). Embedding model only.
  - Result: pressure 1 (citable: no); make docmeta: 164 categories for 164 documents, 152 title vectors for 152 products, bound words 13-213 per product; 164 docmeta:* keys in Redis.
- [x] 6.2 Pressure check; `make seam-check`.
  - Pass: exit 0 (condition 9).
  - Result: pressure 1 (citable: no); make seam-check exit 0: texts aligned with chunk_ids on L1-L3, splice fired, shift rejected.
- [x] 6.3 Pressure check; `make prompt-probe` (generator).
  - Pass: condition 4. If P1 fails, replace the system text with P2 exactly as §3.3 B says, re-run 3.1's
    pin update and this step once. If P2 fails too, stop and report.
  - Result: pressure 1 at start, 2 during the run (citable: no); P1 passes: meta phrases old 88/120 (0.733) vs new 23/120 (0.192); NO_ANSWER on answerable new 6/100 (0.060) vs old "don't know" 10/100 (0.100); P2 not needed; prompt sha256 7a6acf97...; summary in E/prompt-probe.json.
- [x] 6.4 `ollama stop qwen3.5:2b-q4_K_M`; pressure check;
  `make judge-sanity FILE=experiments/judge/sanity-fallback.jsonl` (judge).
  - Pass: exit 0 (condition 15).
  - Result: ollama stop done; pressure 1 (citable: no); make judge-sanity FILE=sanity-fallback.jsonl exit 0: 4 of 4 correct, 0 UNPARSED (2 unanswerable -> CORRECT, 2 answerable -> INCORRECT).
- [x] 6.5 `cd gateway && go run ./cmd/gateprobe -routing ../experiments/results/2026-11-01T21-17-56_cfg4_judgecost/raw/requests.jsonl ../data/workload-v1-validation.json`
  - Pass: vote-correct ≥ top-chunk-correct (condition 5). No model.
  - Result: gateprobe -routing exit 0: 158 policy-gold questions; vote correct 143, top-chunk correct 131 (vote right and top wrong 19, top right and vote wrong 7); output in E/routing-probe.txt.
- [x] 6.6 Pressure check; `make scope-calibrate`; `cd gateway && go run ./cmd/gateprobe -embedcheck ../data/v1-draft/workload/vectors.json 3`.
  - Pass: τ_P printed; each cosine ≥ 0.9999. Write τ_P, the cut 0.10 and today's date in design.md §4 and
    as Entry 8 in `docs/preregistration.md`, before 6.7 (condition 10).
  - Result: pressure 2 (citable: no); τ_P = 0.8329 (exact 0.832813; raw pass 78/1322, projected 77/1322; 142 policy questions, 12 documents); embedcheck 3 of 3 cosine 1.000000; τ_P, cut 0.10 and the date written in design.md §4 and as Entry 8 in docs/preregistration.md (2026-11-14 01:10 +07:00), before 6.7; §1 hash unchanged.
- [x] 6.7 The arm-off replay. `make cache-reset`; pressure check; in one shell
  `RUN_ID=$(date +%Y-%m-%dT%H-%M-%S)_cfg4_scope-off CONFIG_ID=4 MUTATION=off SUPPORT_GATE=off LANE_SIGMA_HI=0.20 REUSE_TAU=0.85 CACHE_CAPACITY=156 SCOPE_ARM=off make dev 2>&1 | tee E/private/gateway-scope-off.log`;
  in another `make replay SPLIT=validation 2>&1 | tee E/private/replay-scope-off.log`; sample pressure
  each minute to `E/pressure-scope-off.log`; stop the gateway with `kill -INT` on the gateway binary.
  - Pass: 606 sent, 16 skipped, 0 SHED; the log has no `THIS RUN IS INCOMPLETE`; pressure never 4.
  - Result: RUN_ID 2026-11-14T01-11-46_cfg4_scope-off; cache-reset first; pressure 1 at all 24 samples (E/pressure-scope-off.log), citable: no; replay done: 606 sent, 16 skipped, 606 http_200, 0 SHED (430 MISS, 176 TIER2_HIT); records: scope_arm off on all 606, write_scope product 373 (null 233), no_answer 57; gateway log has no INCOMPLETE line; stopped with kill -INT on the gateway binary. Note: a first start at 01:11:00 (run folder 2026-11-14T01-11-00_cfg4_scope-off, empty raw/requests.jsonl, zero requests) was stopped before any replay, because I feared the tool's background timeout; its log is E/private/gateway-scope-off-aborted-start.log and the empty folder is left as is.
  - Result (rerun): RUN_ID 2026-11-14T01-43-29_cfg4_scope-off; cache-reset first; pressure 1 at all 20 samples (E/pressure-scope-off.log), citable: no; 606 sent, 16 skipped, 606 http_200, 0 SHED (426 MISS, 180 TIER2_HIT); records: scope_arm off on all 606, write_scope product 370, no_answer 56; no INCOMPLETE line; stopped with kill -INT on the gateway binary; its last gateway: line is `run ended cleanly`; the inadmissible run's renamed logs are untouched.
- [x] 6.8 `make run-manifest RUN_ID=<off> GATEWAY_LOG=E/private/gateway-scope-off.log SPLIT=validation && make run-manifest-check RUN_ID=<off> GATEWAY_LOG=E/private/gateway-scope-off.log`;
  `ollama stop qwen3.5:2b-q4_K_M`; pressure check; `make judge RUN_ID=<off>`.
  - Pass: `admissible: true`, `scope_arm: off`; `judge/` written.
  - STOPPED (not ticked): `make run-manifest` wrote the manifest (arms ok, scope_arm off, 606 records) but `admissible: false`, `rule_6` false: run_manifest.py:178 and interfaces.md §I look for the log line `shutting down, flushing the evaluation log`, and commit 29da622 (before this task) renamed it in main.go to `shutting down: no new requests; ...`. Not fixed; needs the human. The manifest is write-once, so this run cannot be made admissible.
  - Result (rerun, 2026-11-14T01-43-29_cfg4_scope-off): pressure 1 throughout (manifest, 606 judge readings; citable: no); make run-manifest: admissible True, arms config 4 / off / off / off / scope_arm off, 606 records, rule_6 true; run-manifest-check ok; ollama stop done; make judge wrote judge/ (606 records, CORRECT 361, INCORRECT 245, 0 UNPARSED).
- [x] 6.9 The arm-on replay: as 6.7 with `_cfg4_scope-on`, `SCOPE_ARM=on REUSE_TAU_P=<τ_P from 6.6>`, and
  logs named `scope-on`.
  - Pass: as 6.7.
  - Result: RUN_ID 2026-11-14T02-18-25_cfg4_scope-on; cache-reset first; SCOPE_ARM=on REUSE_TAU_P=0.8329 (start-up line shows scope_arm=on tau_p=0.8329); pressure 2 (yellow) at the first 3 samples, then 1 at the other 17, never 4 (E/pressure-scope-on.log), citable: no; 606 sent, 16 skipped, 606 http_200, 0 SHED (423 MISS, 183 TIER2_HIT: 169 product, 14 shared); records: scope_arm on on all 606, write_scope product 266, shared 97, no_answer 60; no INCOMPLETE line; stopped with kill -INT on the gateway binary; its last gateway: line is `run ended cleanly`.
- [x] 6.10 As 6.8 for `<on>`.
  - Pass: `admissible: true`, `scope_arm: on`; `judge/` written.
  - Result: pressure 1 at the manifest and at all 606 judge readings (citable: no); make run-manifest: admissible True, arms config 4 / off / off / off / scope_arm on, 606 records, rule_6 true; run-manifest-check ok; ollama stop done; make judge wrote judge/ for 2026-11-14T02-18-25_cfg4_scope-on (606 records, CORRECT 363, INCORRECT 243, 0 UNPARSED).
- [x] 6.11 `make scope-trial RUNS="<off> <on>"`.
  - Pass: the table of condition 11 and a verdict. Copy both into `E/scope-trial.txt`.
  - Result: scope_trial.py printed the table and the verdict KEEP OFF (copied to E/scope-trial.txt, json in E/scope-trial.json): POLICY hits judged correct off 1, on 9 (rule 1: +8, need 20, FAIL); POLICY wrong share of hits 0.400 on vs misses 0.419 + 0.05 (rule 2 pass); hit counts POLICY 8 off, 15 on (14 shared); SPEC 172 off, 168 on.
- [x] 6.12 Draft ADR-031, the adoption decision, with the numbers of 6.11 and the verdict of the rule.
  If the verdict is `ADOPT`, change `SCOPE_ARM`'s default to `on` in `main.go` and its default test, and
  say so in ADR-030; if `KEEP OFF`, change nothing.
  - Files: `docs/decisions.md`, maybe `gateway/cmd/gateway/main.go`
  - Result: added ADR-031 (and its summary row) to docs/decisions.md with the 6.11 table and the verdict KEEP OFF exactly as printed (rule 1: +8 against 20, FAIL; rule 2 pass); verdict is not ADOPT, so main.go and its default test and ADR-030 are unchanged (SCOPE_ARM default stays off).

## Phase 7 — Run and verify every done condition

- [x] 7.1 Done condition 1 — `make verify`.
  - Pass: no FAIL; any SKIPPED target listed by name.
  - Result: make verify exit 0: go vet, go build, ruff clean; Go tests ok in every package with tests; rag 109 passed; experiments 1400 passed; no FAIL, no SKIPPED target.
- [x] 7.2 Done condition 2 — `shasum -a 256 -c E/sha-before.txt`; the 6.7 and 6.9 summaries; pressure
  check; `make corpus-verify`.
  - Pass: all three hashes OK; 606 sent and 16 skipped in both; corpus-verify exit 0.
  - Result: shasum -c E/sha-before.txt: 3 of 3 OK; both replays report 606 sent and 16 skipped (arm off 2026-11-14T01-43-29, arm on 2026-11-14T02-18-25); pressure 1; make corpus-verify exit 0 (PASS: 167 files, 539 chunks, model and config match).
- [x] 7.3 Done condition 3 — `pytest rag/tests/test_generate_prompt.py rag/tests/test_server_cancel.py -q`;
  the 3.8 no-answer Go test.
  - Result: python3 -m pytest rag/tests/test_generate_prompt.py rag/tests/test_server_cancel.py -q: 21 passed (pins prompt_sha256 7a6acf97..., NO_ANSWER becomes the fixed sentence with no_answer set); go test -count=1 -run NoAnswer ./internal/httpapi (TestNoAnswerIsServedAndWritesNothing, arm off and on): PASS, no Tier-1 key, no Tier-2 record, no dep member.
- [x] 7.4 Done condition 4 — the 6.3 output.
  - Result: E/prompt-probe.json (the 6.3 run, seed 20261113, 120 queries, citable: no): meta-phrase share new 23/120 = 0.192 against old 88/120 = 0.733 (at most half, meta_ok true); NO_ANSWER on answerable new 6/100 = 0.060 against old don't-know 10/100 = 0.100 (limit 0.130, refuse_ok true).
- [x] 7.5 Done condition 5 — the 3.7 vote tests; the 6.5 output.
  - Result: go test -count=1 ./internal/reuse (Vote*, Namespace*): PASS, incl. 2-1 against rank 1, ties, MIXED's policy part, and TestNamespaceUsesRankNotSetMembership unchanged; E/routing-probe.txt (6.5): 158 policy-gold questions, vote correct 143 >= top-chunk correct 131, PASS.
- [x] 7.6 Done condition 6 — the 3.8 arm-off test.
  - Result: go test -count=1 ./internal/httpapi -run TestScopeArmOff: PASS (TestScopeArmOffMakesOneSearchAndWritesTheProductNamespace: one namespace search per POLICY request, every write {doc}@{product}, scope product).
- [x] 7.7 Done condition 7 — the 3.6 pytest and the 3.7 fixture test.
  - Result: python3 -m pytest experiments/tests/test_scope_contract.py: 34 passed (scope_tokens, projection, bound_words against contracts/scope/cases.json); go test -count=1 ./internal/reuse: TestScopeTokensMatchesCrossLanguageContract, TestDecideScopeMatchesCrossLanguageContract, TestProjectMatchesCrossLanguageContract PASS.
- [x] 7.8 Done condition 8 — the 4.1 test under `make test-go`.
  - Result: make test-go GO_TEST_FLAGS=-count=1 (Redis on :6390): all packages ok, live indexes idx:cache and idx:corpus intact; TestInvalidateDropsASharedEntryAndItsTier1CopiesUnderTwoProducts PASS (a shared entry promoted to Tier 1 under two more products is gone from Tier 2 and all Tier-1 keys after one source chunk is invalidated).
- [x] 7.9 Done condition 9 — the 6.1 counts; `make seam-check`.
  - Result: docmeta in Redis: 164 keys, category on 164 of 164, title_vec on 152 of 152 products (counted with redis-cli; 6.1 printed the same); pressure 1 (citable: no); make seam-check exit 0: texts aligned with chunk_ids on L1-L3, splice fired, shift rejected.
- [x] 7.10 Done condition 10 — the 6.6 output; §4 and Entry 8 dated before the 6.7 `RUN_ID` time;
  `awk '/^## 1\. Spec/,/^## 2\. Impact/' docs/work/2026-11-13-tier2-scope-by-evidence/design.md | shasum -a 256 -c E/spec-sha.txt`
  (rewrite the file's path field to `-` first if `shasum` needs it).
  - Pass: the §1 hash is unchanged.
  - Result: E/scope-calibrate.json: tau_P 0.8329 (exact 0.832813), cut 0.10, 142 policy questions, 12 documents, 1322 pairs; E/embedcheck.txt: 3 of 3 cosine 1.000000 (>= 0.9999); design §4 and preregistration Entry 8 are dated 2026-11-14 01:10 +07:00, before the first trial RUN_ID (T01-11-00) and the rerun ids (T01-43-29, T02-18-25); the §1 hash is unchanged: shasum -a 256 -c E/spec-sha.txt on the awk output prints '-: OK' (86631c22...).
- [x] 7.11 Done condition 11 — `make run-manifest-check RUN_ID=<off>` and `RUN_ID=<on>`; the pressure
  logs; the 6.11 table.
  - Result: make run-manifest-check ok for both runs (with and without GATEWAY_LOG; scope_arm off and on read from records and start-up line, admissible true); both have raw/ and judge/; pressure logs: arm off 1 at all 20 samples, arm on 2 at the first 3 samples and 1 at the other 17, never 4 (E/pressure-scope-off.log, E/pressure-scope-on.log); E/scope-trial.txt has per lane and arm hits, correct, wrong and Wilson intervals over requests and clusters.
- [x] 7.12 Done condition 12 — ADR-028, 029, 030 and 031 in `docs/decisions.md`.
  - Result: docs/decisions.md holds ADR-028 (vote routing), ADR-029 (prompt, sentinel, fallback; amends ADR-023), ADR-030 (the scope arm) and ADR-031 (adoption: KEEP OFF, with the 6.11 numbers), each with its Invalidates line and a summary-table row.
- [x] 7.13 Done condition 13 — the 3.7 τ / τ_P test.
  - Result: go test -count=1 ./internal/reuse -run Tau: TestSharedCandidateIsHeldToTauPAndProductCandidateToTau, TestSharedCandidateAtExactlyTauPPasses, TestSharedCandidateFailsClosedWithoutTauPOrOutsideThePolicyLane, TestProductDecisionsCarryTauAndTheDefaultIsUnchanged PASS; httpapi TestScopeArmOnJudgesTheSharedCandidateAgainstTauPAndTheProductOneAgainstTau PASS.
- [x] 7.14 Done condition 14 — the 3.8 cross-product test.
  - Result: go test -count=1 ./internal/httpapi -run TestScopeArmOnSharesANeutralPolicyAnswerWithinACategory: PASS (neutral answer written for product A served to a paraphrase on product B of the same category, not to the furniture product C).
- [x] 7.15 Done condition 15 — the 6.4 output.
  - Result: the 6.4 output (judge-sanity on experiments/judge/sanity-fallback.jsonl, pressure 1, citable: no): exit 0, 4 of 4 correct, 0 UNPARSED (2 unanswerable questions with the fallback judged CORRECT, 2 answerable judged INCORRECT).

## Phase 8 — Fix: rule 6 never held (found at 6.8; design §4, approved 2026-11-14)

- [x] 8.1 The gateway prints `gateway: run ended cleanly` as its last line, only on a clean end.
  - Files: `gateway/cmd/gateway/main.go`: const `runEndedLine`; `type runEnd struct` (what `ListenAndServe`
    and `Shutdown` returned, the map's close error and its three counts, the log's close error, the verdict)
    with a pure `clean() bool`; the shutdown goroutine keeps `Shutdown`'s error for `main`.
  - Run: `cd gateway && go build ./... && go vet ./...`
  - Pass: no error; `srv.Shutdown(` < `depMap.Close(` < `finishRun(evalLog)` < the new line in the code.
  - Result: main.go: runEndedLine, runEnd.clean(), Shutdown's error kept; printed last only when clean, else a 'did not end cleanly' line; go build and vet clean (main session, 2026-11-14).
- [x] 8.2 `run_manifest.py`: `ended` is true for `run ended cleanly` or the pre-`29da622` line; `incomplete`
  is true for the INCOMPLETE line or either warning of `29da622`. The parse keeps its keys.
  - Files: `experiments/scripts/run_manifest.py`
  - Pass: `pytest experiments/tests/test_run_manifest.py experiments/tests/test_run_manifest_scope.py -q`
    passes unchanged.
  - Result: run_manifest.py: ENDED_LINES (new last line, pre-29da622 line) and BAD_LINES (INCOMPLETE and the two warnings); parse keys unchanged; 131 existing tests pass unchanged.
- [x] 8.3 New tests: Go, `runEnd.clean()` over each way to fail and the order of the line in `main.go`;
  pytest, the new line is admissible, each warning and the `29da622` start line alone are not, and every
  line rule 6 reads is printed by `gateway/cmd/gateway/main.go`.
  - Files: `gateway/cmd/gateway/runend_test.go`, `experiments/tests/test_run_manifest_end.py` (new)
  - Run: `make test`
  - Pass: no FAIL.
  - Result: new runend_test.go (clean() over 9 ways to fail; line order in main.go) and test_run_manifest_end.py (7 pass, incl. main.go prints every line rule 6 reads); make test exit 0 (rag 109, experiments 1400, Go ok); make lint exit 0.
- [x] 8.4 `interfaces.md` §I `rule_6` and the v0.37 row say the same.
  - Result: interfaces.md §I rule_6 names the end line, the pre-29da622 line and the three bad lines; the v0.37 row says so and that both 2026-11-14 runs stay inadmissible.
- [x] 8.5 Repeat 6.7 under a new `RUN_ID` (`make cache-reset` first: Redis holds the inadmissible run's
  cache). Add a second `Result (rerun):` line under 6.7 and tick it; then 6.8–6.12 and Phase 7 in order.
  - Pass: as 6.7, and the gateway log's last `gateway:` line is `run ended cleanly`.
  - Result: 6.7 repeated as 2026-11-14T01-43-29_cfg4_scope-off (cache-reset first, 606 sent, 16 skipped, 0 SHED, pressure 1; the gateway log's last gateway: line is 'run ended cleanly'; run-manifest admissible true); then 6.8-6.12 (arm on 2026-11-14T02-18-25_cfg4_scope-on, admissible true, ADR-031 with verdict KEEP OFF) and 7.1-7.15 all ticked; the first 6.7 run's renamed logs were not touched.
