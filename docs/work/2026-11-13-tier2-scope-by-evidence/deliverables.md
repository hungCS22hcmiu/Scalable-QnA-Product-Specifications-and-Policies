# Deliverables — Tier-2 trial: scope by evidence

Closed 2026-11-14 · super-plan item 6.0a · verdict of the pre-registered rule: **KEEP OFF** (ADR-031)

## What shipped

- **Served in every arm from now on:** majority-vote routing of the POLICY document (ADR-028); the new
  generator prompt with a `NO_ANSWER` sentinel that `rag.server` replaces by one fixed sentence, flagged and never
  cached (ADR-029; prompt sha256 `7a6acf97…`, frozen for Phase 6). The reference writer keeps the old prompt in a
  pinned file, so the references and ADR-026's judge-error figures stay valid.
- **Replay:** validation replays skip the 16 queries with no `product_id` and send 606 (ADR-025's decision; no
  workload file changed).
- **The scope arm** (`SCOPE_ARM=off|on`, ADR-030): built, tested, on every record, default `off`.
- **Fix found at step 6.8:** rule 6 of the run manifest had held for no run since `29da622`. The gateway now prints
  `gateway: run ended cleanly` last, only after a clean end, and rule 6 also fails on the two warnings of
  `29da622` (design §4, plan Phase 8).
- `interfaces.md` v0.37 (§B, §C, §D, §H, §I); pre-registration Entry 8 (τ_P and the cut, dated before the trial).

## Files changed

Python: `rag/src/rag/{generate,server}.py`, new `rag/src/rag/docmeta.py`; `experiments/scripts/{replay,run_manifest,
judge,judge_references}.py`, new `{scope_calibrate,prompt_probe,scope_trial}.py`; `experiments/judge/` (pinned
reference prompt, fallback sanity pairs); `Makefile`. Go: `reuse/{lane,cause,rule}.go`, new `reuse/scope.go`;
`cache/tier2.go`, new `cache/docmeta.go`; `httpapi/{cascade,handler}.go`; `ragclient/answer.go`;
`telemetry/evallog.go`; `cmd/gateway/main.go`; `cmd/gateprobe/main.go`. Shared: `contracts/rag/v1/rag.proto`, new
`contracts/scope/cases.json`. Docs: `interfaces.md`, `decisions.md` (ADR-028–031), `preregistration.md`. Tests:
four existing files changed with the human's approval (design §4); new files in `rag/tests`, `experiments/tests`,
`reuse/`, `httpapi/`, `cache/`, `deps/`, `cmd/gateway/`.

## How it was verified (main session's own re-run, 2026-11-14 03:00–03:20 +07:00, pressure 1)

1. `make verify` → exit 0; no FAIL, no SKIPPED (rag 109, experiments 1,400, Go all ok).
2. Both replays 606 sent / 16 skipped; `shasum -c sha-before.txt` → 3 OK; `make corpus-verify` → PASS.
3. `test_generate_prompt.py`, `test_server_cancel.py` pass; `TestNoAnswerIsServedAndWritesNothing` passes.
4. `evidence/prompt-probe.json`: meta phrases 0.733 → 0.192 (≤ half); `NO_ANSWER` 0.06 ≤ 0.10 + 0.03.
5. Six `TestVote*` pass; `gateprobe -routing`: vote 143 ≥ top chunk 131 of 158.
6. `TestScopeArmOffMakesOneSearchAndWritesTheProductNamespace` passes.
7. `TestScopeTokens/DecideScope/ProjectMatchesCrossLanguageContract` and `test_scope_contract.py` pass.
8. `make test-go GO_TEST_FLAGS=-count=1` ok; `TestInvalidateDropsASharedEntryAndItsTier1CopiesUnderTwoProducts` passes.
9. `docmeta:*` 164 keys, 164 categories, 152 title vectors; `make seam-check` → exit 0.
10. τ_P 0.8329 printed; embedcheck 3 of 3 at cosine 1.000000; Entry 8 at 01:10, before both trial `RUN_ID`s; §1 hash
    `86631c22…` unchanged.
11. `make run-manifest-check` ok for both runs (`admissible: true`, `rule_6: true`); pressure never 4; `make
    scope-trial` reproduces the table and `KEEP OFF` byte for byte.
12. ADR-028, 029, 030, 031 in `decisions.md`, each with `Invalidates:`.
13. `TestSharedCandidateIsHeldToTauPAndProductCandidateToTau` and three more pass.
14. `TestScopeArmOnSharesANeutralPolicyAnswerWithinACategory` passes.
15. `make judge-sanity FILE=experiments/judge/sanity-fallback.jsonl` → 4 of 4, 0 UNPARSED (re-run by the main session).

## Numbers (all `v1` validation, `citable: no`)

- **Trial runs**, configuration 4, mutation off, support gate off, MIXED off, τ 0.85, capacity 156, judge-v1:
  arm off `2026-11-14T01-43-29_cfg4_scope-off` (426 MISS, 180 TIER2_HIT; 361 correct, 245 incorrect; pressure 1 at 20
  of 20 samples); arm on `2026-11-14T02-18-25_cfg4_scope-on`, τ_P 0.8329 (423 MISS, 183 TIER2_HIT; 363 correct, 243
  incorrect; pressure 2 at 3 samples, then 1 at 17).
- **POLICY lane:** off 8 hits, 1 correct, 7 wrong; on 15 hits, 9 correct, 6 wrong. Rule 1: +8, needs +20, FAIL.
  Rule 2: 0.400 ≤ 0.419 + 0.05, pass. By scope (arm on): 14 shared hits 9/5, 1 product hit 0/1. 97 of 145 POLICY
  answers were written shared. Shared hit similarity 0.834–0.957, median 0.863.
- **Prompt probe** (seed 20261113, 100 answerable + 20 not, generator, pressure 1–2): see condition 4.
- **Fallback in the arm-off run:** 56 of 606; 42 on answerable questions, 35 of them with the gold document
  retrieved (the model gave up). 14 of 40 unanswerable questions got it.
- **τ_P calibration:** 142 policy questions, 1,322 same-document pairs; raw 78 pass at 0.85, projected 77 at 0.8329.

## Deferred and follow-ups

- Run folders kept as written: `…T01-11-00…` (empty start, no manifest) and `…T01-11-46…` (complete but
  `admissible: false`, rule 6). All three new runs were archived (`make raw-archive`); `make raw-check` → all ok.
- Item 6.1: the support gate as an arm (H1), the 2b judge pass, and the false-hit metric (a′/b/c) by ADR first.
- Repeating the scope arm needs a new pre-registered rule and its own task; not recommended now.
- The 6.0a row says "workload rebuild"; the task chose replay exclusion instead (design Status line).
  `Pipelines/Workload.md` still says 622.
- `make check` prints `grep: … No such file or directory` for `docs/` paths with spaces (seen by the executor, not
  investigated).
