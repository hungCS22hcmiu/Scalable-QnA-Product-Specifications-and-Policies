# Plan — retire-unfiltered-phase

The smallest change that satisfies `spec.md` rev 3, ordered so that each step can be checked on its
own. It follows `design.md` rev 3, after `impact.md` and `review.md`.

## 0. Before any edit

- [x] `review.md` folded into `design.md` rev 3 and `spec.md` rev 3. S1 was the author's call:
      R3 was revised to I1 (`approvals.md`).
- [x] The author runs `/approve impact` · `/approve contract` · `/approve experiment` ·
      `/approve implementation`. All four were approved on 2026-10-05.
- [x] **Baseline on `HEAD` (`5854cbe`).** `make verify` exit 0, and
      `cd gateway && go test -count=1 ./...` green, uncached.

## 1. Tests first: each must fail on `HEAD` for the stated reason, or be marked as a pin

- [x] **Harness, the additive part only.** `NearestTier2InNamespace` records its namespace
      argument, and `namespacesSearched()` returns a copy. Restate the comment at
      `harness_test.go:60-61`. The fake's `NearestTier2` stays for now, because `HEAD`'s
      `cacheStore` still requires it.
      **Done when** the 1.2 suite passes unchanged on `HEAD`. **Done:** it passed.
- [x] **`gateway/internal/httpapi/cascade_test.go`**, T1–T7 (`design.md` §4). TIER2_HIT tests wait
      for the bump and the promotion before `records()`. Expected on `HEAD`, as measured by
      `review.md`:

      | Test | On `HEAD` | Why |
      | :--- | :--- | :--- |
      | T1 one scoped search | **fails**, below-τ half only | `HEAD` returns before the scoped search. The hit half passes (N3) |
      | T2 F-E closed | **fails**, 7 fields | `entered_band: true`, non-null `similarity`, `t_search_ms` 0.002 |
      | T3 τ boundary | **passes, as a pin** | `HEAD` already serves at `sim == τ` with the band entered |
      | T4 counterfactual target | **fails**, 3 fields | `source_overlap` 0 and `overlap_decision` false, from the global nearest |
      | T5 no retired key | **fails** | the record carries `similarity_only_decision` |
      | T6 identical question, another product | **fails** on `similarity: null` | `HEAD` reports the global nearest's 1.0 |
      | T7 empty namespace | **fails** | found, banded, `Search` ≈ 3 µs, one call |

      Any other result stops the plan: a test that passes on `HEAD` when it should fail is vacuous.
      **Result on `HEAD`: exactly as the table says.**
      - T1: the below-τ half failed (0 calls) and the hit half passed.
      - T2 failed on 7 fields, including `t_search_ms` 0.002.
      - T3 passed.
      - T4 failed on 3 fields.
      - T5 failed (`similarity_only_decision = HIT`).
      - T6 failed on `similarity` 1, and also on `entered_band`.
      - T7 failed: found, banded, `Search` 3.04 µs, one call.
- [x] **`gateway/cmd/gateway/main_test.go`**: three rows for `retiredEnv`. It asserts
      `REUSE_TAU_HIGH` and `retired`, not the ADR number.
      **Done when** it fails to compile only because `retiredEnv` does not exist yet. **Done:**
      `undefined: retiredEnv`.

## 2. The edits, in dependency order

- [x] **`reuse/`.** Delete `Thresholds.TauHigh` and its comment block, `Decision.SimilarityOnly`,
      and `RuleSimilarityOnly`. Restate the `NamespaceDecision.Overlap` comment (§3). Apply D4 in
      `rule_test.go`.
      **Done when** `go test ./internal/reuse/` passes, and `git diff` on `rule_test.go` shows only
      deletions, plus the `math` import line. **Done.** One deviation: removing the column also
      drops the trailing field from the four case rows, and gofmt realigns the struct. The
      `wantReuse` values and the `Reuse` check are unchanged. Two comments were restated beyond
      §3's list, because each became false: `NamespaceDecision.Rule` (it judges, and is set on
      refusals) and `DecideNamespace` (containment runs on banded requests, not every request).
- [x] **`telemetry/`.** Delete `Record.SimilarityOnlyDecision`. Restate the package doc and the
      `ReuseRule` comment (N5). Apply D4 in `evallog_test.go:69`.
- [x] **`httpapi/`:**
  - `cacheStore` and the fake both lose `NearestTier2`, in the same edit.
  - `tryTier2` is rewritten to `design.md` §3's contract, with the `retrieved == nil` check first.
  - `handler.go` loses the `SimilarityOnlyDecision` assignment and `hitOrMiss`.
  - Every comment in §3's table is restated, except `types.go:48-53`, the response's
    `ReuseRule`. It is left as it was: the response sets it only on a TIER2_HIT (the MISS response
    omits it), so "names which term decided" is still true there. N5 concerns the record's field,
    which is restated.
- [x] **`ask_test.go`.** `:287` → `resp.null("similarity")`; `:291` →
      `rec.boolean("entered_band", false)`. Nothing else in the file changes. Before the edit, these
      two lines were the only failures in the whole suite.
- [x] **`cmd/gateway/main.go`.** Remove `TauHigh`, `REUSE_TAU_HIGH`, the `short-circuit:` line and
      `math`. Add `retiredEnv`, and call it with `os.Getenv` before any wiring.
- [x] **`Makefile` demo step 4.** The null branch prints the namespace line. The non-null branch
      prints `.cache`, `.overlap_decision` and the overlap formatted by `num`, with no verdict word
      (S5). **Deviation:** the old `shared / total` ratio is dropped from that branch. It is computed
      from `.sources`, not read from the response, and on a hit it is always 1. The `shared` and
      `total` variables went with it.

## 3. Check

- [x] `cd gateway && go test -count=1 ./...`, and the same with `-race` for `./internal/httpapi/`:
      all green, T1–T7 and `main_test.go` included. `TestBelowTauDoesNotEnterTheBand` passes with
      its lines untouched. **Green**, `-race` included (`./internal/httpapi/`, `./cmd/gateway/`).
- [x] **Acceptance 5:** `git diff -U0 -- gateway/internal/httpapi/ask_test.go` shows exactly two
      changed lines, `:287` and `:291`. **Two lines, confirmed.**
- [x] **Acceptance 1, three greps.** All pass:
  - grep 1 finds only the guard and its test, T5's absence test, and history comments
    (`evallog.go:6`, `cascade_test.go:169, :190`);
  - grep 2 finds nothing;
  - grep 3 prints `1`.

  The greps run:
  - The retired-names grep finds only history comments and the guard:
    `grep -rnE "TauHigh|tau_high|REUSE_TAU_HIGH|SimilarityOnly|similarity_only" gateway rag --include='*.go' --include='*.py'`.
  - No non-test call site remains: `grep -n 'NearestTier2(' gateway/internal/httpapi/*.go | grep -v _test.go`
    finds nothing.
  - The guard is called once: `grep -c 'retiredEnv(os.Getenv)' gateway/cmd/gateway/main.go` prints `1`.
- [x] **Acceptance 7.** Run the built binary with `REUSE_TAU_HIGH=0.95` and `REDIS_URL`,
      `RAG_GRPC_ADDR`, `HTTP_ADDR` at `127.0.0.1:1`. It must exit 1 with the message before any
      dial. Then run it with `REUSE_TAU_HIGH=` (empty), which must get past the guard. Save both
      outputs to `evidence/startup-guard.txt`. No model is loaded, so the pressure check does not
      apply. **Done:** `0.95` exits 1 with the message before any dial. An empty value reaches the
      Redis dial, which the closed port refuses.
- [x] **Acceptance 8.** Run step 4's formatting fragment offline with `null` and `0.25`. Neither
      prints `0.00`, `REFUSE` or `<`, and the null case prints the namespace line. Save the output
      to `evidence/demo-step4.txt`. **Done.** The fragment was extracted from the Makefile itself.
      None of the forbidden tokens appears.
- [x] **Mutations M1–M11** (`design.md` §5). Apply each to a clean tree, run the named test,
      record red, then revert. Record M9 as not behaviourally catchable, with the reason. The
      results go to `evidence/mutations.md`. **All 12 runnable mutations are caught**, each by the
      check §5 names. Two confirm why the greps exist:
      - M1′: the suite stays green; only grep 2 catches it.
      - M7b: `main_test.go` stays green; only grep 3 catches it.
- [x] `make verify` green (exit 0).

## 4. Contract and experiment text (the approved phases)

- [x] `interfaces.md` v0.10: every row of `design.md` §8's table, plus the version row and a
      top-of-file v0.10 change note, matching the file's convention.
- [x] `decisions.md`: ADR-004 (`design.md` §8) and its Summary-table row.
- [x] `approvals.md`: the experiment record (`design.md` §8).

## 5. Review and close

- [x] `/ai-review` (`contract-reviewer` on the §A/§H diff). The diff conforms. Two low-severity doc
      wording defects (C1, C2) were fixed; none is unresolved (`review.md`).
- [x] `/done` (2026-10-05). It records:
  - `super-plan.md:118-120, :126` (the progress line and item 1.3);
  - item 2.3's row: "no in-namespace candidate is not a `NAMESPACE` refusal" (S3);
  - the configuration-3 owner gap in F-K's note (R1);
  - `architecture.md:114-115` (collapse to one Tier-2 row);
  - for the author: `Final_Proposal.md:589`, and `:10-19` now that ADR-004 exists;
  - out of scope, recorded: the demo step-4 header and intro line, the `Makefile:212` comment
    (*"the trap (Q4) … fails theta=0.60"*), and `ProductChat.jsx:67-70`;
  - the vacuous `"both searches"` subtest;
  - whether scope L was honest.

## Outcome (2026-10-05, `/done`)

**`/verify` before closing** (`make verify` exit 0, plus proto drift run separately). **Nothing is
SKIPPED:**

| Target | Result |
| :--- | :--- |
| gofmt | **PASS** |
| go vet | **PASS** |
| go build | **PASS** |
| go test | **PASS** |
| ruff | **PASS** |
| pytest `rag/` | **PASS** (15) |
| pytest `experiments/` | **PASS** (94) |
| proto drift | **PASS** (`make proto`, no diff on either stub) |

**Shipped:**
- **Configuration 4's cascade:**
  - at most one namespace-scoped Tier-2 search;
  - no global search, no `τ_high`, no `similarity_only_decision`;
  - F-E and F-G closed;
  - the startup guard on `REUSE_TAU_HIGH`;
  - demo step 4 truthful on both branches.
- **Tests:** T1–T7 and `main_test.go`. D4's stale tests are retired. `ask_test.go` changes at
  exactly `:287` and `:291`.
- **Evidence:** the startup guard, demo step 4, and 12 of 12 runnable mutations caught
  (`evidence/`).
- **Records:** `interfaces.md` v0.10; ADR-004; the experiment record (I1, I2, the commit boundary);
  `super-plan.md` item 1.3 ✅, the progress line, the 2.3 sentence (S3) and the F-K note (R1);
  `architecture.md` §3's Tier-2 row.

**The scope was honest.** It was opened at L, and the work touched `reuse/`, the §A/§H contract
and a measured path (`t_search_ms`), so L was right. No phase was skipped: spec → impact → design
→ opus review → plan, with all four approvals.

**A contract changed, and no frozen value did.** `interfaces.md` was bumped to v0.10.
`approvals.md` says which prior runs are invalidated: **none, because none exist**. Logs written
before the 1.3 commit carry the old meanings under the same keys, and must never be mixed with
later ones.

**Deferred, each worth a task when its time comes:**
1. **Configuration 3, the static-cache arm and the 3 ⋈ 4 join script.** None has an item, and
   *decisions changed by provenance* has no derivation without them. Recorded in F-K's note; it
   needs an owner before Phase 6.
2. **Demo and UI story text.** These still tell the old cross-namespace lookalike story:
   - step 4's header and intro line;
   - the `Makefile:212` comment;
   - `ui/src/pages/ProductChat.jsx:67-70`.

   A small docs task, before the next demo.
3. **Live confirmation**, by one `make demo` at green pressure:
   - which branch Q4 takes (`review.md` U2: PLAUSIBLE, null);
   - that the TAG filter matches hyphenated slugs (U4/N4).
4. **The vacuous `"both searches"` subtest** (`ask_test.go:589`) now injects into a method nothing
   calls. The file is immutable, so removing or renaming it needs the author's confirmation.
5. **For the author, not edited here:** `Final_Proposal.md:589` (*"not yet executed in code"* is
   now false) and `:10-19` (the ratification is no longer pending: ADR-004).

