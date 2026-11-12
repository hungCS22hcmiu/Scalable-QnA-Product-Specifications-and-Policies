# Deliverables — Cap the request size on `/ask` (item 5.5)

Closed 2026-11-12 · super-plan item 5.5 · `interfaces.md` v0.36 · no ADR

## What shipped

- `/ask` reads at most **8,192 bytes** of body (`maxAskBody`, 8 KiB). A larger body gets **413** with
  `request too large: the body is over 8192 bytes`, on the malformed-request path, before any record exists.
- `decodeAsk` checks in three places: a declared `Content-Length` over the limit (before a byte is read), the JSON
  decode through `http.MaxBytesReader`, and the rest of the body after the object. The last one stops a small object
  followed by padding from getting through.
- Invalid JSON, an empty `question` and a blank `product_id` still get 400, with the same messages.
- `interfaces.md` §A: the "Body size (v0.36)" note, and the version moved to v0.36.

## Files changed

- Modified: `gateway/internal/httpapi/handler.go`, `docs/contracts/interfaces.md`, `docs/super-plan.md`.
- New: `gateway/internal/httpapi/bodylimit_test.go` (seven tests) and `evidence/workload-max-body.txt` (sizes only).
- **Frozen values touched: none. Prior runs invalidated: none.** No `v1` body is near the limit (DC 4), and the cost
  run's longest question is 178 bytes.
- The contract change is additive (§A). `replay.py` and k6 are unchanged; §H is unchanged.

## How it was verified

Main session, 2026-11-12, after the executor (the last runs follow plan Phase 6):
- `make verify` → exit 0; Go packages `ok` (`httpapi` uncached); rag 94 passed; experiments 1332 passed; no
  SKIPPED target, no FAIL.
- `go test ./internal/httpapi -count=1 -race` → `ok`.
- DC 1 → the three `TestAskRefuses…` tests pass: 413, the reply names 8192, no log line, `Requests` 0, no Retrieve
  or Answer. The declared-length test read 0 bytes.
- DC 2 → `TestAskServesABodyAtTheLimit`: 8,192 and 8,191 bytes give 200 MISS, one record each.
- DC 3 → `TestAskBodyLimitOverRealHTTP`: 413 (with a length), 413 (chunked), 413 (padded object, chunked), 200
  (8,192 bytes).
- DC 4 → longest `v1` body 242 bytes (`replay.py`) and 239 (k6), against 8,192.
- DC 5 → `TestRejectsBadMethodAndBody`, `TestRejectsMissingProductID` and `TestAskStillSays400…` pass. Under the
  test files, `git status` shows only `?? gateway/internal/httpapi/bodylimit_test.go`.
- DC 6 → the note is at `interfaces.md` line 184; `v0.36` appears 5 times.
- **Mutation check** (the drain removed from `decodeAsk`, then restored byte for byte): both padded tests fail with
  200, want 413. Before the Phase 6 fix, only the real-HTTP one did.

## Numbers

All `citable: no`. Nothing loaded a model or started the gateway, so memory pressure does not apply.
- The longest `/ask` body over the frozen `v1` workload (1,274 queries; validation 622, test 652): 242 bytes as
  `json.dumps` builds it, 239 as UTF-8 `JSON.stringify` does. Limit 8,192, about 34 times higher.

## Deferred and follow-ups

- **Phase 6 (the main session's fix):** `TestAskRefusesAnObjectFollowedByPaddingOverTheLimit` first passed without
  the drain, because its request had a known length. It now sends none (design.md §4).
- **Executor deviations, accepted:** the real-HTTP test records whether each request arrived chunked; the tests use
  the literal 8192, so changing the limit fails them on purpose.
- A body that is both malformed and over the limit may get 400 or 413 (§A says so). Both are refused before any
  record.
- Stale text left: the 5.5 row of `super-plan.md` still says "this is the only input guard built". ADR-025 added the
  `product_id` check, as ADR-025 itself notes.
- The Phase 6 exit is not met: `experiments/results/` holds only the cost run, and Headline B does not exist yet.
