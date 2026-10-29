# Deliverables — The live seam and support checks still pin the retired dev-v0 corpus

Closed 2026-10-29 · super-plan item: none — unblocks the live re-check that items 1.4 and 2.1 require
after any retrieval or LlamaIndex change · no ADR, no contract change

## What shipped

- **`make seam-check` and `make support-check` run on `v1` again.** Their two tests had pinned
  `dev-v0` IDs, none of which exists in `v1`. The seam check failed at L2; the support check failed at
  `fidelity`, and its two query subtests passed with no product chunk in the retrieval.
- **The empty pass is closed.** Each support retrieval must now contain a chunk of the scoped product,
  check (i).
- **A future corpus switch fails loudly.** A preflight in each test fails with "pin absent … was the
  corpus switched?" when a pinned chunk is missing from Redis.
- **Changes to existing tests.** The author approved them on 2026-10-29 (design §4): the stale pins
  only, a new authored answer for the support test, and the two new checks. The verdicts are still
  logged and not asserted (item 2.1's choice).

## Files changed

- `gateway/internal/ragclient/seam_live_test.go`:
  - `spliceDoc` / `spliceChunk` become `product-laptops-b07k238ls2`;
  - the comment, and the preflight.
- `gateway/internal/ragclient/support_live_test.go`:
  - the product becomes `product-electronics-b07wnp64zn`, and only the product name changes in the
    two queries;
  - the answer, its SHA `197de3fd39ab` and 22 tokens;
  - 4 fidelity hashes;
  - check (i), the preflight, and the header.
- `docs/super-plan.md`: the Issue-2 finding (`:456`), and a new finding on the unknown `product_id`
  (`:457`).
- The trail. Its Go copies under `evidence/` are named `*.go.txt` (plan Phase 7): they belong to no
  module and are only read through `GOFLAGS=-overlay`.

## How it was verified (the main session's own re-run, 2026-10-29, pressure 1 throughout)

1. Untouched files, through an overlay of the HEAD copies:
   - seam exits 2 at L2 (`want equal and >= 1`);
   - support exits 2 at `fidelity` (7 × `oracle: no text`), and both query subtests PASS: the empty pass.
2. Check (i) alone, through an overlay: support exits 2, and both query subtests FAIL with "no
   product-headphones-03 chunk".
3. `make seam-check` → exit 0. L1, L2, L3 and shift PASS, and L2 splices
   `product-laptops-b07k238ls2#chunk-0` at index 0.
4. `make support-check` → exit 0. fidelity and both queries PASS, and each retrieval holds the
   product's chunk-0.
5. The pin-absent overlays: seam and support each exit 2 with "pin absent", before any subtest.
6. `git diff --name-only -- gateway/` lists only the two test files. `reuse/` and
   `support_sample_live_test.go` are unchanged.
7. `docs/super-plan.md` `:456–457`.
8. `make verify` → exit 0. rag: 62 passed; experiments: 778 passed; Go: ok. No FAIL and no SKIPPED
   (`evidence/recheck/make-verify-final.txt`).

All logs are in `evidence/recheck/`. After the Phase 7 rename, the DC 1, 2 and 5 overlays and both
plain targets were run again, with the same results.

## Numbers

- S_lex on `v1`, product `product-electronics-b07wnp64zn`, live scoped retrieval, embedding model only,
  pressure 1, **citable: no** (a correctness check, logged and not asserted):

| Query | Retrieved | S_lex | Verdict |
| :--- | :--- | :--- | :--- |
| paraphrase | product chunk-0, `policy-return-electronics`, `policy-return-phones-opened` | 0.9545 | ADMITS |
| warranty | product chunk-0, `policy-warranty-electronics` | 0.4091 | REFUSES |

- On `dev-v0` (2026-10-12) the same pair scored 0.8750 and 0.3125. The scores move with the corpus and
  the ranking, which is why they are logged and not pinned.

## Deferred and follow-ups

- **An unknown `product_id` is accepted silently.** Recommended: a pre-run check in the Phase 7 harness
  that every workload `product_id` exists in Redis. Today it holds: 115/115 on both splits.
- **`make demo` is still on `dev-v0`** (Phase 8). The `demo-reset` guard is in place.
- **A `v1` version of `support_sample_live_test.go`:** not planned. Phase 5's judged sample on `v1`
  answers the same question with a larger n. The file stays as a dated `dev-v0` artefact.
- **Stale wording, flagged only:**
  - `CLAUDE.md:53` (the author's file);
  - `interfaces.md` §B's "one-chunk-per-document" rationale;
  - the docstrings of `test_retrieve_scoping.py:8` and `test_store_index_ready.py:10`.
- **Done outside this task, in the same session:**
  - ADR-018: the Tier-1 key includes `product_id`;
  - `interfaces.md` v0.23;
  - the matching `Final_Proposal.md` edits.

  The "ADR owed" comments in `key.go` and `types.go` are updated after this task closes.
