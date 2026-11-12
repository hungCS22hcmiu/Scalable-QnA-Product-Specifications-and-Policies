# Cap the request size on `/ask` (item 5.5)

Status: opened 2026-11-12 · spec approved 2026-11-12 · design approved 2026-11-12 · plan approved 2026-11-12
Changed by §3: DCs 1 and 3 add a small JSON object followed by enough spaces to pass the limit (`Decode` stops at the
object, so this body would get through) and a declared `Content-Length` over the limit. 8 KiB stays (spec approved
unchanged).
Super-plan item: 5.5 — Cap the request size on `/ask`

## 1. Spec

**The change.** `/ask` reads at most **8,192 bytes** of request body (`maxAskBody`, 8 KiB). A larger body is refused
with **413**, on the same early path as a malformed request, before any record exists. Today `handler.go:208` decodes
the body with no limit, so one very large request can take a lot of gateway memory.

Why these values:
- **8 KiB.** The longest body the frozen `v1` workload sends is 242 bytes (its longest question is 178 bytes), so the
  limit is about 34 times higher. 8 KiB is about 2,000 tokens, far more than any product question needs.
- **413, not 400.** A client can tell "too large" from "malformed". `replay.py` counts it as `http_413`, and k6 as a
  non-200 error, with no change to either. Invalid JSON and a missing `product_id` stay 400.

**Done conditions**

1. **Over the limit.** A new Go test sends `Ask` a valid JSON body of 8,193 bytes (the `question` padded). The status
   is 413 and the reply names the limit. No record is logged, `Counters.Requests` stays 0, and Retrieve and Answer
   never run. Two more bodies get the same result: a small valid object followed by spaces up to 8,193 bytes, and a
   request whose declared `Content-Length` is over the limit.
2. **At the limit.** In the same test file, a valid body of exactly 8,192 bytes, and one of 8,191, are served (200).
3. **Over real HTTP.** Through `httptest.NewServer`, which is real `net/http` over TCP: a body of 8,193 bytes gets
   413, both with a `Content-Length` and sent chunked (no length). So does the small object followed by spaces, sent
   chunked. A body of 8,192 bytes gets 200.
4. **Above the workload.** A command reads the three frozen files `data/workload-v1.json`, `-validation.json` and
   `-test.json`. It prints the longest `/ask` body, built as `replay.py` builds it (`json.dumps`) and as k6 does
   (UTF-8, as `JSON.stringify`). Both are at most 242 bytes, below 8,192. The output is saved to `evidence/`.
5. `make verify` exits 0 with no SKIPPED target. The existing `TestRejectsBadMethodAndBody` and
   `TestRejectsMissingProductID` pass unedited, so invalid JSON is still 400. Under the test files, `git status` shows
   only the new file `gateway/internal/httpapi/bodylimit_test.go`.
6. **Docs.** `interfaces.md` §A states the limit, the 413 reply and why, at **v0.36**. The `/ask` request table and
   the error cases agree.

**Out of scope**
- A per-client rate limit, authentication and a filter for meaningless questions. These were decided out on
  2026-10-27, and item 8.2 reports them as limitations.
- A separate cap on `question` length. Also out: refusing data after the JSON object, as `/invalidate` does. `/ask`
  keeps ignoring it, as today.
- `/invalidate`, which already has its own 1 MiB cap. The other routes read no body.
- Any change to `replay.py` or `k6/ask.js`. No live run: no gateway is started and no model is loaded.

## 2. Impact

**Files**
- Changed: `gateway/internal/httpapi/handler.go`, which gets the constant and the bounded decode.
- New: `gateway/internal/httpapi/bodylimit_test.go`.
- Docs: `docs/contracts/interfaces.md` §A, and `docs/super-plan.md` at close.
- Boundaries: request checks belong to `httpapi/`, the HTTP edge (`architecture.md`: "POST /ask … → §A"). No new
  import. `/invalidate` already uses the same `http.MaxBytesReader` pattern.

**Frozen values touched: none.** The limit is a new contract value in §A, not a study parameter. **Prior runs
invalidated: none.** Every body of the frozen `v1` workload is at most 242 bytes (DC 4), and the cost run
`2026-11-01T21-17-56_cfg4_judgecost` has no question longer than 178 bytes. So no request of any past run, and no
future run on `v1`, reaches the limit.

**Contract change: yes, additive, §A, v0.36.**
- The server side: a new 413 reply.
- The client side: `replay.py` and k6 need no change, because they never send a body near the limit.
- §H is unchanged: a refused request leaves no record, like ADR-025's 400.

**Measurement change: none.** No record, counter or field changes, and the frozen workload never reaches the limit.

**New dependency: none.** The change lowers memory: one request's body is bounded at 8 KiB.

**Cut scope reinstated: no.** The rate limit, authentication and the question filter stay out.

## 3. Design

**Approach.** Read the body through `http.MaxBytesReader(w, r.Body, maxAskBody)`, the pattern `/invalidate` already
uses, and turn its `*http.MaxBytesError` into 413. Then read the rest of the body through the same reader, so a body
over the limit is refused even when the JSON object ends early. The alternative was reading the whole body with
`io.ReadAll` and a length check. It lost because `MaxBytesReader` stops at the limit and never holds more than it
reads, and `http.Server` closes the connection for us.

The order of checks in `Ask`, each an early return before the record exists:
1. the method is not POST → 405 (as today);
2. a declared `r.ContentLength > maxAskBody` → 413, before anything is read;
3. `json.NewDecoder(mb).Decode(&req)` fails: a `*http.MaxBytesError` → 413, any other error → 400 (as today);
4. `io.Copy(io.Discard, mb)` reads what is left: a `*http.MaxBytesError` → 413, any other error → 400. Data after the
   object that fits under the limit is still ignored, as today;
5. an empty `question` → 400, a blank `product_id` → 400 (as today).

### Files

**`gateway/internal/httpapi/handler.go`**
- `const maxAskBody = 8 << 10`, with a comment: 8,192 bytes, about 34 times the longest `v1` body (242 bytes), §A
  v0.36.
- `errBodyTooLarge` is not needed: a size failure is recognised with `errors.As(err, &mbe)` where
  `var mbe *http.MaxBytesError`.
- `func decodeAsk(w http.ResponseWriter, r *http.Request) (askRequest, error)` runs steps 2 to 4 and returns the
  request. For step 2, it returns `&http.MaxBytesError{Limit: maxAskBody}`, so one `errors.As` covers every size case.
- `Ask` calls `decodeAsk`. On a size error it replies
  `http.Error(w, "request too large: the body is over 8192 bytes", http.StatusRequestEntityTooLarge)`; on any other
  error it replies with today's 400 message, unchanged. Steps 1 and 5 stay where they are.

**`gateway/internal/httpapi/bodylimit_test.go`** (new; uses the existing `newHarness`)
- `questionForBody(t, n int, productID string) string` pads a question with `a` so that the body the harness sends
  (`json.Marshal` of `question` and `product_id`) is exactly `n` bytes, and fails the test if it cannot.
- `TestAskRefusesABodyOverTheLimit` (DC 1): 8,193 bytes through `hs.h.Ask` → 413, and the reply contains `8192`.
- `TestAskRefusesAnObjectFollowedByPaddingOverTheLimit` (DC 1): a small valid object, then spaces up to 8,193 bytes →
  413.
- `TestAskRefusesADeclaredLengthOverTheLimit` (DC 1): a request whose `ContentLength` is set above the limit → 413,
  and the test's reader shows that no byte was read.
- In all three: after `hs.h.Eval.Close()`, the log at `hs.logPath` has no line; `Counters.Requests` is 0;
  `hs.rag.retrieveCalls()` and `answerCalls()` are empty.
- `TestAskServesABodyAtTheLimit` (DC 2): 8,192 and 8,191 bytes through `hs.ask` (with `hs.embedFresh`) → 200, MISS,
  and `hs.records` passes, so each has exactly one record.
- `TestAskBodyLimitOverRealHTTP` (DC 3): `httptest.NewServer(http.HandlerFunc(hs.h.Ask))`. 8,193 bytes with a length
  → 413; 8,193 bytes chunked (a reader with no length) → 413; the padded object, chunked → 413; 8,192 bytes → 200.
  These requests are not sent through `hs.start`, so the test does not call `hs.records`.
- `TestAskStillSays400ForSmallMalformedBodies`: invalid JSON, an empty question and a blank `product_id`, all under
  the limit, still get 400 (it adds to the existing tests and does not edit them).

**`docs/contracts/interfaces.md`** §A: a "Body size (v0.36)" note under the `POST /ask` request table. It gives the
limit in bytes, the 413 reply, why, that no record is written, and that a body that is both malformed and over the
limit may get 400 or 413 (both are refused before any record). The status line, "Current version" and the versioning
table go to v0.36.

### Failure modes, silent ones first

1. **A body over the limit gets through.** `Decode` stops at the end of the first JSON value, so a small object
   followed by a large padding would never touch the limit. Symptom: none; the cap looks built. Guard: step 4 and
   DC 1's padded test.
2. **A refused request leaves a record or bumps a counter.** Symptom: a new outcome in §H that no counting rule
   knows. Guard: refusing before the record literal; DC 1 checks the log, the counter and the RAG calls.
3. **Off by one.** A body of exactly 8,192 bytes refused, or 8,193 accepted. Guard: DC 1 and DC 2.
4. **Another error read as 413, or a size error read as 400.** Symptom: a client counts the wrong cause. Guard:
   `errors.As` on the size error only; DC 1, DC 5 and the new 400 test.
5. **The test harness, not `net/http`, is what passes.** `httptest.NewRequest` does not run the server's own body
   handling. Guard: DC 3 runs over a real connection, with and without a length.

### Edge cases

- The limit counts bytes, not characters. A multi-byte question reaches it sooner.
- An empty body is still 400 (`Decode` returns `io.EOF`).
- A malformed body over the limit may get 400, if the decoder fails before it reaches the limit. It is still refused
  before any record, and §A says so.
- For a much larger body, the server closes the connection after the 413. A client still sending may see a reset
  instead of the reply. Small over-limit bodies, like DC 3's, read the reply.

### Unknowns

- That `http.Server` sends the 413 before closing the connection for an 8,193-byte chunked body. This is reasoned
  from the `net/http` docs, and DC 3 settles it.

### Verification

- **DCs 1–3:** `go test ./internal/httpapi -run 'TestAsk.*(Limit|Body|400)' -count=1 -v`, through `make test-go` in
  `make verify`.
- **DC 4:** a `python3` command over the three workload files, its output saved to `evidence/workload-max-body.txt`.
- **DC 5:** `make verify`, and `git status` on the test files.
- **DC 6:** `grep` for the §A note and `v0.36`.

## 4. Findings

- **2026-11-12, the main session's re-check.** A mutation check removed the `io.Copy` drain from `decodeAsk`. DC 3's
  chunked padded case failed, as it should, but DC 1's `TestAskRefusesAnObjectFollowedByPaddingOverTheLimit` still
  passed: `httptest.NewRequest` gives the request a known length, so the declared-length check refused it first. The
  test now sets `ContentLength = -1`, and with the drain removed it fails too (plan Phase 6). No existing test
  changed: the file is new in this task.
