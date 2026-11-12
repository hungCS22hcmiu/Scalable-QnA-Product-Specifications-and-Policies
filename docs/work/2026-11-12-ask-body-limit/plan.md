# Plan — Cap the request size on `/ask` (item 5.5)

Design: design.md (approved 2026-11-12)

Rules for every step (`.claude/rules/execution.md`):
- Nothing in this plan loads a model or starts the gateway, so no memory-pressure check is needed. Every number is
  `citable: no`.
- Never edit, skip or loosen an existing test: new tests go only in the new file `bodylimit_test.go`. Never commit.
- The `httpapi` tests use fakes and need no Redis, so a single package can run with `go test` directly. The full run
  goes through `make verify`, which runs the Go Redis tests on their own server (:6390).
- `data/workload-v1*.json` holds PQA text. Step 3.1 prints sizes only. Never copy a question into `evidence/`.
- On a failed check: one quick fix if the cause is obvious and local, run it again, and if it still fails, stop and
  report the full output.
- `T` means `docs/work/2026-11-12-ask-body-limit`.

## Phase 0 — Baseline

- [x] 0.1 Baseline `make verify`, before any change.
  - Run: `make verify`
  - Pass: exit 0. If it fails, stop: the failure is not this task's, and the human decides.
  - Result: exit 0; 94 Python tests and 1,332 Go tests pass; no SKIPPED or FAIL line.
- [x] 0.2 The working tree holds only this task's folder.
  - Run: `git status --short`
  - Pass: only `?? docs/work/2026-11-12-ask-body-limit/`. Anything else: stop and report.
  - Result: status shows only `?? docs/work/2026-11-12-ask-body-limit/`.

## Phase 1 — Implement

- [x] 1.1 In `gateway/internal/httpapi/handler.go`, add `const maxAskBody = 8 << 10` with §3's comment, and
  `func decodeAsk(w http.ResponseWriter, r *http.Request) (askRequest, error)` with §3's steps 2 to 4: the declared
  length check (returning `&http.MaxBytesError{Limit: maxAskBody}`), `Decode` through
  `http.MaxBytesReader(w, r.Body, maxAskBody)`, then `io.Copy(io.Discard, mb)` through the same reader.
  - Files: `gateway/internal/httpapi/handler.go`
  - Run: `cd gateway && go build ./... && go vet ./internal/httpapi`
  - Pass: no error.
  - Result: added `maxAskBody` (8 << 10) and `decodeAsk` (declared length, bounded Decode, then io.Copy to Discard) to handler.go; `go build ./...` and `go vet` clean.
- [x] 1.2 In `Ask`, replace the bare `json.NewDecoder(r.Body).Decode(&req)` with `decodeAsk`. A
  `*http.MaxBytesError` (found with `errors.As`) replies
  `http.Error(w, "request too large: the body is over 8192 bytes", http.StatusRequestEntityTooLarge)`. Any other
  error, or an empty `question`, replies with today's 400 message, unchanged. The `product_id` check stays where it is.
  Nothing moves below the record literal.
  - Files: `gateway/internal/httpapi/handler.go`
  - Run: `cd gateway && gofmt -l internal/httpapi && go vet ./internal/httpapi && go test ./internal/httpapi -count=1`
  - Pass: `gofmt` prints nothing; vet is clean; the existing tests pass, unedited.
  - Result: `Ask` now calls `decodeAsk`; `*http.MaxBytesError` gets 413, other errors and an empty question keep the 400 text; gofmt prints nothing, vet clean, existing httpapi tests `ok`.

## Phase 2 — Tests (`gateway/internal/httpapi/bodylimit_test.go`, new)

- [x] 2.1 Add the helper `questionForBody(t, n, productID)` as §3 says. It builds the body exactly as `hs.start`
  does (`json.Marshal` of a `map[string]string` with `question` and `product_id`) and fails the test unless
  `len(body) == n`.
  - Files: `gateway/internal/httpapi/bodylimit_test.go`
  - Run: `cd gateway && go vet ./internal/httpapi`
  - Pass: no error.
  - Result: added bodylimit_test.go with `questionForBody` (and small helpers `askBodyOf`, `paddedObject`); `go vet ./internal/httpapi` clean, gofmt prints nothing.
- [x] 2.2 DC 1: `TestAskRefusesABodyOverTheLimit`, `TestAskRefusesAnObjectFollowedByPaddingOverTheLimit` and
  `TestAskRefusesADeclaredLengthOverTheLimit`, as §3 says. Each checks the 413, that the reply contains `8192`,
  that the log at `hs.logPath` has no line after `hs.h.Eval.Close()`, that `hs.h.Counters.Requests.Load()` is 0, and
  that `hs.rag.retrieveCalls()` and `hs.rag.answerCalls()` are empty. The declared-length test uses a reader that
  counts its reads and asserts 0 bytes were read.
  - Files: `gateway/internal/httpapi/bodylimit_test.go`
  - Run: `cd gateway && go test ./internal/httpapi -run 'TestAskRefuses' -count=1 -v`
  - Pass: the three tests PASS.
  - Result: added the three DC 1 tests; all PASS (413, reply names 8192, no log line, Requests 0, no Retrieve/Answer, declared-length test read 0 bytes).
- [x] 2.3 DC 2: `TestAskServesABodyAtTheLimit`. For 8,192 and 8,191 bytes, call `hs.embedFresh(q)`, then
  `hs.ask(t, askReq{question: q, productID: kettle.id})`, then `hs.records(t)` once at the end. Both are 200 and MISS.
  - Files: `gateway/internal/httpapi/bodylimit_test.go`
  - Run: `cd gateway && go test ./internal/httpapi -run 'TestAskServesABodyAtTheLimit' -count=1 -v`
  - Pass: PASS.
  - Result: added `TestAskServesABodyAtTheLimit`; 8,192 and 8,191 bytes both 200 MISS, `hs.records` passes (one record each); PASS.
- [x] 2.4 DC 3: `TestAskBodyLimitOverRealHTTP`, with `httptest.NewServer(http.HandlerFunc(hs.h.Ask))` and the
  server's own client. Four requests: 8,193 bytes with a length → 413; the same body chunked (wrap the reader so it
  has no length, and check that `req.ContentLength` is -1 before sending) → 413; the padded object, chunked → 413;
  8,192 bytes (after `hs.embedFresh`) → 200. Do not call `hs.records`.
  - Files: `gateway/internal/httpapi/bodylimit_test.go`
  - Run: `cd gateway && go test ./internal/httpapi -run 'TestAskBodyLimitOverRealHTTP' -count=1 -v`
  - Pass: PASS, with the four statuses in its log.
  - Result: added `TestAskBodyLimitOverRealHTTP`; statuses 413 (length), 413 (chunked), 413 (padded, chunked), 200 (8,192 bytes); server saw ContentLength -1 and chunked on the two chunked requests; PASS.
- [x] 2.5 `TestAskStillSays400ForSmallMalformedBodies`: invalid JSON, an empty question and a blank `product_id`,
  each under the limit, get 400, never 413.
  - Files: `gateway/internal/httpapi/bodylimit_test.go`
  - Run: `cd gateway && go test ./internal/httpapi -run 'TestAskStillSays400' -count=1 -v`
  - Pass: PASS.
  - Result: added `TestAskStillSays400ForSmallMalformedBodies`; invalid JSON, empty question and blank product_id all get 400; PASS.
- [x] 2.6 The whole package, with the race detector.
  - Run: `cd gateway && go test ./internal/httpapi -count=1 -race`
  - Pass: `ok`.
  - Result: whole httpapi package with `-race`: `ok` (3.2s).

## Phase 3 — The workload check (DC 4, citable: no)

- [x] 3.1 Measure the longest `/ask` body of the frozen `v1` workload, as `replay.py` and k6 build it.
  - Run: `python3 - > $T/evidence/workload-max-body.txt <<'EOF'` with a script that reads `data/workload-v1.json`,
    `data/workload-v1-validation.json` and `data/workload-v1-test.json`. For each query it builds
    `{"question": q["question"]}`, adds `product_id` when the query has one (as `replay.request_for` does), and
    measures `len(json.dumps(body).encode())` (replay) and
    `len(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))` (k6, `JSON.stringify`). It
    prints, per file, the number of queries and the two maxima, then the overall maxima and the limit 8192. It
    prints no question text.
  - Pass: every maximum is at most 242 and below 8,192; the file holds numbers and file names only.
  - Result: wrote evidence/workload-max-body.txt (sizes and file names only): longest body 242 bytes (replay, json.dumps) and 239 bytes (k6, JSON.stringify) over 1,274 + 622 + 652 queries; both below 8,192.

## Phase 4 — Docs

- [x] 4.1 `docs/contracts/interfaces.md` §A: add "Body size (v0.36)" under the `POST /ask` request table, with what
  §3 lists. Move the status line, "Current version" and the versioning table to v0.36.
  - Files: `docs/contracts/interfaces.md`
  - Run: `grep -n "Body size (v0.36)\|413" docs/contracts/interfaces.md; grep -c "v0.36" docs/contracts/interfaces.md`
  - Pass: the note and a 413 line in §A; the count is at least 4.
  - Result: interfaces.md §A gains "Body size (v0.36)" under the request table (limit, 413 text, why, no record, 400-or-413 when malformed and over); status line, Current version and a new versioning-table row are at v0.36; grep finds the note, 413 lines and 5 lines with v0.36.

## Phase 5 — Run and verify (every done condition)

- [x] 5.1 `make verify`
  - Pass: exit 0; no FAIL; no SKIPPED target.
  - Result: exit 0; vet, build, all Go packages `ok` (httpapi ran uncached), 94 Python tests pass; no FAIL and no SKIPPED line.
- [x] 5.2 DC 1 — over the limit.
  - Run: `cd gateway && go test ./internal/httpapi -run 'TestAskRefuses' -count=1 -v`
  - Pass: three PASS lines.
  - Result: DC 1: three PASS lines (TestAskRefusesABodyOverTheLimit, ...AnObjectFollowedByPaddingOverTheLimit, ...ADeclaredLengthOverTheLimit).
- [x] 5.3 DC 2 — at the limit.
  - Run: `cd gateway && go test ./internal/httpapi -run 'TestAskServesABodyAtTheLimit' -count=1 -v`
  - Pass: PASS.
  - Result: DC 2: TestAskServesABodyAtTheLimit PASS (8,192 and 8,191 bytes both 200 MISS).
- [x] 5.4 DC 3 — over real HTTP.
  - Run: `cd gateway && go test ./internal/httpapi -run 'TestAskBodyLimitOverRealHTTP' -count=1 -v`
  - Pass: PASS.
  - Result: DC 3: TestAskBodyLimitOverRealHTTP PASS; log shows 413, 413, 413, 200 for the four requests.
- [x] 5.5 DC 4 — above the workload.
  - Run: `cat $T/evidence/workload-max-body.txt`
  - Pass: both overall maxima at most 242, below 8192.
  - Result: DC 4: evidence/workload-max-body.txt shows overall maxima 242 bytes (replay) and 239 bytes (k6), both below 8192.
- [x] 5.6 DC 5 — existing tests untouched.
  - Run: `cd gateway && go test ./internal/httpapi -run 'TestRejectsBadMethodAndBody|TestRejectsMissingProductID|TestAskStillSays400' -count=1 -v`;
    then `git status --short -- ':(glob)**/*_test.go' ':(glob)**/test_*.py'`
  - Pass: all PASS; the status shows only `?? gateway/internal/httpapi/bodylimit_test.go`.
  - Result: DC 5: TestRejectsBadMethodAndBody, TestRejectsMissingProductID and TestAskStillSays400 all PASS; test-file status shows only `?? gateway/internal/httpapi/bodylimit_test.go`.
- [x] 5.7 DC 6 — docs.
  - Run: `grep -n "Body size (v0.36)" docs/contracts/interfaces.md; grep -c "v0.36" docs/contracts/interfaces.md`
  - Pass: the note is in §A; the count is at least 4.
  - Result: DC 6: "Body size (v0.36)" is in §A (line 184); 5 lines contain v0.36.

## Phase 6 — Fix found by the main session's re-check

A mutation check (the `io.Copy` drain removed from `decodeAsk`) failed DC 3's chunked padded case, as it should,
but `TestAskRefusesAnObjectFollowedByPaddingOverTheLimit` still passed: its request carried a known length, so the
declared-length check refused it first and the drain was never reached. The test file is new in this task, so it may
change.

- [x] 6.1 In that test, set `req.ContentLength = -1` so only the drain can refuse the body.
  - Files: `gateway/internal/httpapi/bodylimit_test.go`
  - Run: `cd gateway && go test ./internal/httpapi -run TestAskRefuses -count=1 -v`, then the same mutation again
  - Pass: three PASS with the drain; with the drain removed, both padded cases (DC 1 and DC 3) FAIL.
  - Result: (main session) 3 PASS with the drain; with it removed, TestAskRefusesAnObjectFollowedByPaddingOverTheLimit and TestAskBodyLimitOverRealHTTP FAIL (200, want 413); handler.go restored byte for byte; package passes with -race.
