# `gateway/internal/telemetry/` — the evaluation log and the answer store

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `evallog.go` (397 lines), `doc.go`, and seven test
files. Governing contract: `interfaces.md` §H. The field-by-field meaning of the record is in §H; this doc
explains how it is written.

## 1. Purpose

It writes **one record per request** to `experiments/results/{run_id}/raw/requests.jsonl`, and the text of every
served answer to `raw/answers/{answer_sha256}.txt`. Four metrics cannot be computed without it: decisions
changed by provenance, the share of requests entering the band, false hits by cause, and the hit-path latency
breakdown. It serves **C3** (the evaluation protocol).

## 2. Boundaries

- It imports **nothing** from this repository, so any package may import it (`docs/architecture.md` §2).
- `raw/` is **write-once** (ADR-005). The package never appends to a finished run.
- The fuller package description is the package comment in `evallog.go`; `doc.go` names the governing contract,
  `interfaces.md` §H.

## 3. `evallog.go`

**`Record`** is §H's schema, field for field. Three rules shape it:
- **A nullable field is a pointer** (`Similarity`, `SupportLex`, `PermitWaitMS`, `GenerateMS`, `DatasetEpoch`…),
  so "not measured" renders as `null`, never as a 0 that reads like a real value.
- **§H fields never use `omitempty`.** Every key is present on every line, so a missing key is a bug, not an
  absent value. The tests pin this for `support_gate` and `mixed_lane`.
- **Gateway extension fields do use `omitempty`**, because they are not in §H: `coalesced`, `reuse_rule`,
  `candidate_entry_id`, `candidate_sources`, `invalidated_entry_id`, `tier2_search_failed`, `product_id`.

**`SetAnswer(text)`** is the **only** way a record gets an answer. It sets the hash and the text from one value,
so they cannot differ. An empty answer is a real answer (it hashes to the empty string's digest); an empty
`AnswerSHA256` means no answer was served.

**`Logger`** writes records off the request path. **A nil `Logger` is valid and does nothing**, so `make dev`
needs no run ID and call sites need no branch.

**`Open(resultsDir, runID)`**:
- An empty `runID` returns a nil `Logger`: logging is off, and the gateway says so at start.
- Otherwise it creates `raw/requests.jsonl` with **`O_EXCL`**: if the file exists, it refuses to start. A reused
  run ID needs a new run ID, never more lines added to a finished run.
- It creates a fresh `raw/answers/`, and refuses one that already exists. On a refusal it removes only what it
  made.

**`Log(r)`** puts the record on a buffered channel (4,096 places) and **never blocks**: an answered request
must not wait for a log write. If the buffer is full, the record is **dropped and counted** (`Dropped()`). A
dropped record is a hole in the measurement, so the run must be repeated.

**`run()`**, the one writer goroutine, for each record:
1. **`storeAnswer`** first, so a line never names a file that is not there yet.
2. Then the JSON line.

**`storeAnswer(r)`**, step by step:
1. If this hash was already written (`seen`), stop. This is the common case under a Zipf workload.
2. **The guard:** if the text does not hash to `AnswerSHA256`, write nothing, mark the hash missing, and count a
   `GuardRefusal`. This means a call site set one and not the other; the run is **void**, and the count is never
   cleared.
3. Write the text to a temp file (`.answer-*.tmp`, not `*.txt`), set mode 0644, close it, and check every error
   **before** publishing.
4. **Link** (never rename) the temp file to `{sha}.txt`. A link fails if the name exists, so a file is never
   overwritten and the final name only ever appears complete. "Already exists" counts as success, which is safe
   because `Open` made `answers/` fresh and only this goroutine writes there.
5. Mark the hash seen, clear it from missing, and remove the temp name. A failure to remove the temp file is a
   stray file, **not** a missing answer.

**Counters, all safe to read while the writer runs:** `Dropped()` (buffer full), `AnswersMissing()` (hashes a
record names with no file now; read it after `Close`), `GuardRefusals()`, `WriteErrors()` (lines that failed
to encode), and `Tier2SearchFailures()` (records with `tier2_search_failed`; any non-zero count makes the run
inadmissible under run rule 12, because a failed search degrades to a MISS and looks like a colder cache).

**`Close()`** stops intake, drains the buffer, and closes the file.

## 4. Callers and callees

- **Opened by** `cmd/gateway/main.go` with `RESULTS_DIR` and `RUN_ID`.
- **Filled by** `httpapi.(*Handler).Ask`, which builds the record during the request and logs it in one
  deferred call, so every exit path writes exactly one record.
- **Read by** the Phase 5–7 scripts that turn a run into numbers (the judge reads `raw/answers/`).

## 5. Tests that pin it

34 tests across seven files. The main groups:

| Group | Examples |
| :--- | :--- |
| Write-once | `TestOpenRefusesAnExistingRunFile`, `TestOpenRefusesAPreexistingAnswersDirectoryAndRemovesOnlyWhatItMade`, `TestAnExistingAnswerFileIsNeverRewritten` |
| Nulls and keys | `TestNullableFieldsRenderAsNull`, `TestCauseFieldsRenderAsNull`, `TestSupportGateKeyIsNeverNull`, `TestMixedLaneKeyIsAlwaysWritten`, `TestCandidateFieldsAreExtensions` |
| Answer store | `TestTheFileIsVisibleBeforeTheLineThatNamesIt`, `TestIdenticalAnswersAreWrittenOnce`, `TestAnswerTextRoundTripsByteExact`, `TestAnEmptyAnswerIsAFileNamedForTheEmptyHash` |
| Failures counted, never silent | `TestTheGuardRefusesAMismatchAndNeverForgets`, `TestAFailedLinkIsCountedAndALaterRecordRetries`, `TestAnEncodeFailureIsCountedAndLeavesAnUnnamedFile`, `TestTier2SearchErrorIsCounted` |
| Lifecycle | `TestEmptyRunIDWritesNothing`, `TestLogAfterCloseIsSafe`, `TestTheAccessorsAreSafeWhileTheWriterIsRunning`, `TestMeasureWriterDrain` |

## 6. Silent failures to watch

- **A run with a non-zero counter** (`Dropped`, `AnswersMissing`, `GuardRefusals`, `WriteErrors`,
  `Tier2SearchFailures`) is incomplete or inadmissible, but the run itself finishes normally. The run manifest
  must record and check them.
- **Records lost at shutdown** (finding F-F): `main` closes the log while `Shutdown` is still draining, so
  requests in flight at SIGTERM can vanish with `Dropped()` at 0. Stop the load before SIGTERM until it is fixed.
- **Known gaps in what is written** (§H readers): `t_permit_wait_ms` is null on the fast path (F-N), and
  `coalesced` is set only on a served MISS (F-O).

## 7. Commit

`29b24a6`.
