# Design — answer-text-storage

**Revision 3**, after `review.md`. What changed from rev 2: publication reports **what was linked**,
not "any error" (finding 3); a **never-cleared guard-refusal counter** (1); the seam moves to `link`
(4); `incomplete` takes a **struct** and gains the guard count and the `Close` error (8, 13); the
tests are rebuilt so M1 and M3 cannot hide (1, 5, 14); the burst test is re-posed (2); the invariant
is "in a run that is not INCOMPLETE" (8); the `answers.jsonl` alternative is carried (15); EEXIST's
safety is argued from the directory, not from SHA-256 (7). Rev 2's changes (`requests.jsonl` first,
`os.Link`, guard after `seen`) stand.

## 1. The shape

```
Ask (any path that serves text)                telemetry.Logger (one writer goroutine)
 ───────────────────────────────                ───────────────────────────────────────
 rec.SetAnswer(text)  ── sets ─▶ rec.AnswerSHA256 = sha256(text)
                                 rec.answerText   = text         (unexported: never in JSON)
 …deferred emit…
 h.Eval.Log(rec)      ── chan ─▶ for r := range ch {
                                    if r.AnswerSHA256 != "" { storeAnswer(r) }   // 1. the file
                                    encode(r)                                    // 2. the line
                                  }
```

The file is made visible **before** the line that names it, by the same goroutine. The ordering is
structural: nothing has to be remembered at a call site. A record dropped by a full buffer, or
skipped after `Close`, loses its line **and** its file together. "File before line" is a property of
the **writer**, not something a reader can check from `raw/`, and it holds for a hash's first
*successful* write: if the first write failed and a later record with the same hash retried
successfully, the first record's line precedes its file. So admissibility turns on the file existing
at the end, never on order (contract review, 2026-10-06).

### Why this and not another place

| Alternative | Rejected because |
| :--- | :--- |
| **Inline the text in every `requests.jsonl` record** | A record without its text becomes unrepresentable. Rejected: (1) the plan names `raw/answers/{sha}.txt`; (2) under Zipf redundancy **hits dominate**, so the file would grow with the *hit count*, not the distinct-answer count, and every analysis that parses it for latency or hit rate would pay for text it never reads; (3) 5.1's work list *is* the set of distinct hashes |
| **`raw/answers.jsonl`**: one `{sha, text}` line per first sighting, appended by the same goroutine before the record line | **The smallest version, and a real rival** (`review.md` 15). It keeps dedupe, order, retry and D3 and removes `CreateTemp`/`Chmod`/`Link`/`Remove`, the three-step `Open`, the EEXIST question, temp residue, mutations M10–M12, and the per-file Spotlight and APFS (≥ 4 KB per file) cost. It loses atomic per-answer publication (a full disk leaves a torn line, not no file) and `cat raw/answers/$sha.txt` / open-by-hash. **Default: the directory, because the plan names it and 5.1 reads by hash. Put to the author.** If the file is chosen, only the writer and the §H layout wording change |
| A separate `AnswerStore` called from `Ask` | Handler gains an I/O concern and a second failure counter, and gets **no ordering** against the record. Three call sites would each have to remember it |
| Write at `cache.Put` | Covers MISS only. A hit on an entry that predates the run is exactly the case where this run has never written the text |
| Keep the text in Redis | The cache is a bounded LRU and the next run may flush it. The plan item is the statement that this is unsound |

## 2. Contracts

### `telemetry.Record`

```go
// SetAnswer is the only way a record acquires an answer. It sets both fields from one value so
// the hash and the text cannot drift apart.
func (r *Record) SetAnswer(text string)
```

- `AnswerSHA256` stays the exported JSON field: **no wire change**. `answerText` is unexported, so
  `encoding/json` never sees it. Checked: no test compares `Record`s, builds one positionally, or
  `DeepEqual`s one (`impact.md` §6).
- `AnswerSHA256 == ""` means *no answer was served*. An **empty text is a real answer**:
  `SetAnswer("")` yields the hash of the empty string and an empty file. "Has an answer" is decided
  by `AnswerSHA256 != ""`, **never** by `answerText != ""`.
- `sha256Hex` moves into `telemetry`; its stale citation of `experiment-protocol.md 4` (deleted in
  `21aaaec`) is dropped.

### `telemetry.Logger`

```go
func Open(resultsDir, runID string) (*Logger, error)
func (l *Logger) AnswersMissing() int      // hashes a record names that have no file, right now
func (l *Logger) GuardRefusals() int64     // records whose text did not match their hash. NEVER cleared
func (l *Logger) WriteErrors() int64       // JSONL lines that failed to encode (D3)
```

All three accessors are **nil-safe**, like `Dropped()` (`make dev` runs with a nil Logger and `main`
calls them).

**`Open`**, in this order:
1. `MkdirAll(raw)`.
2. `OpenFile(requests.jsonl, O_CREATE|O_EXCL|O_WRONLY)`: **the existing freshness proof, first.**
   Failure: refuse, as today. Nothing has been created inside a finished run.
3. `Mkdir(raw/answers)` (leaf `Mkdir`, **not** `MkdirAll`). If it fails, **close and remove only the
   `requests.jsonl` this call just created**, then refuse. A crash between steps 2 and 3 burns the
   run id and leaves no directory a later run could inherit.
4. Start the writer. `RUN_ID` empty still returns `nil, nil` and writes and starts nothing.

**`storeAnswer(r Record)`**, on the writer goroutine only:

1. `seen[sha]` → return. (The Zipf common case.)
2. **Guard:** if `sha256(r.answerText) != r.AnswerSHA256`, **do not write**: add 1 to
   `guardRefusals` (**never cleared**), add `sha` to `missing`, log, return. It catches a call site
   that sets the exported field directly and skips `SetAnswer`, which would otherwise publish an
   empty file under another text's name: it passes every "file exists" check and is wrong. It sits
   after the `seen` check, so it costs one hash per *distinct* answer and can never let a wrong file
   be published (a record skipped by `seen` names a hash a guarded record already published).
3. `os.CreateTemp(raw/answers, ".answer-*.tmp")` (**does not end in `.txt`**, so a `*.txt` glob never
   meets a stray temp file). Write `[]byte(text)` exactly: no newline added, no normalisation.
   `Chmod 0644` (`CreateTemp` is 0600; `requests.jsonl` is 0644). **Check `Close`'s error.** Any
   failure so far: remove the temp file, add `sha` to `missing`, log, return. `seen` is **not**
   set, so the next record with that hash retries.
4. `l.linkFile(tmp, raw/answers/{sha}.txt)` (default `os.Link`). **`Link` fails if the name exists,
   and that is the point:** a file is never overwritten (`Rename` would), and the final name only
   ever appears complete.
   - success, **or** an error satisfying `errors.Is(err, fs.ErrExist)`: the file is there. Set
     `seen[sha]`, **delete** `sha` from `missing`. `EEXIST` is safe to treat as success **because
     `Open`'s leaf `Mkdir` guarantees the directory is fresh and this goroutine is the only thing
     that creates files in it**, *not* because of SHA-256: a hash says nothing about bytes someone
     else wrote under that name. A later "resume" or `MkdirAll` change would break exactly this.
   - any other error: **no `{sha}.txt` was linked**: add `sha` to `missing`, log, do not set `seen`.
5. `os.Remove(tmp)`. **A failure here, after a successful `Link`, is logged and is not a missing
   answer**: the file exists. (Marking it missing would void a good run, because at temperature 1 a
   MISS answer is never seen again to clear it.)

`AnswersMissing()` is *the number of hashes a record names that have no file right now*, not the
number of failed attempts. A transient failure followed by a successful retry leaves the run
complete, and the count says so.

**The line write (D3).** `encode(r)`'s error is, besides the existing log, counted in an atomic
`writeErrs`. Today it is only logged and `Dropped()` stays 0. This is what makes the second half of
the invariant ("no unnamed file") loud: with the file linked and the encode then failing, a file
exists that no record names.

### `cmd/gateway/main.go`

```go
// runCounts is everything that can make a finished run inadmissible. A struct, so two int64
// fields cannot be passed in the wrong order.
type runCounts struct {
	Dropped, WriteErrors, GuardRefusals int64
	AnswersMissing                      int
	CloseErr                            error
}

// incomplete reports why a finished run cannot be admitted, or nil.
func incomplete(c runCounts) error
```

Pure, on the `retiredEnv` pattern (`main.go:51-57`), table-tested. `main` builds it **after
`evalLog.Close()`**, at the site that checks `Dropped()` now, and keeps the `log.Fatalf`. Before
`Close`, pending records would make `AnswersMissing` under-count and a run read as complete when it
is not. `Close`'s own error (`main.go:259-261` only logs it) is an input. A **guard refusal voids
the run** (default; question 4): it means a call site skipped `SetAnswer`, a defect that
invalidates the measurement and that `missing`'s retry could otherwise mask. The old `Dropped`
branch, which no test has ever run, is covered by the same table. The log line at `:208` also says
where the answers go.

### `httpapi/handler.go`

Three assignments become `rec.SetAnswer(...)`: Tier-1 (`:207`, `entry.Answer`), Tier-2 (`:308`,
`t2.Candidate.Entry.Answer`), miss (`:524`, `gen.Text`). `sha256Hex` and its imports go.

### `interfaces.md` v0.11 and ADR-005

§H gains: the layout; lowercase-hex `{sha}.txt` names; raw UTF-8 bytes, no added newline; **in a run
that is not INCOMPLETE** the file is visible before the line that names it, every non-empty
`answer_sha256` names a file whose bytes hash to its name, and no file is unnamed; **no text, no
file**; `""` not null; empty text hashes to `e3b0c442…`; the incompleteness rule. **It does not
re-ratify the `:487` "judge dedupe key" label**: the comment becomes *the answer's address in
`raw/answers/`*, and the `:491` key stays `sha256(query ‖ answer)` (`review.md` 10: a bare answer
hash would collapse a true hit and a false hit on the same answer into one verdict). No JSON field
changes. ADR-005 also records: the publication posture the author chooses, the Spotlight
precondition if the author makes it one, the alternatives in §1, the EEXIST reasoning, that invalid
UTF-8 is unreachable because protobuf-go validates a `string` on unmarshal, and these three limits:
**F-F** (a record logged after `Close` is skipped, uncounted; this change does not widen it, since
the CAS at the start of `Close` fixes the skipped set, not how long `Close` takes), **`Log` racing
`Close`** (a panic inside `Ask`'s deferred emit, swallowed by `net/http`'s per-connection recover:
a lost record with only "http: panic serving" on stderr), and that **the INCOMPLETE verdict lives
only in the exit status and stderr until P1 lands**, so *answers recoverable from `raw/` alone*
holds and *admissibility decidable from `raw/` alone* does not.

## 3. Failure modes

| Failure | What happens | Visible how |
| :--- | :--- | :--- |
| `raw/answers/` cannot be created at start | `Open` refuses; the gateway does not start; the just-made `requests.jsonl` is removed | at startup, loud |
| Disk full / directory unwritable mid-run | The request is **served**, its record **written** (and so names a hash with no file), the hash is `missing` | `AnswersMissing() > 0` → `incomplete` → run ends INCOMPLETE; logged at the time too |
| …then a later record with that hash succeeds | Retried (not in `seen`); clears `missing` | count returns to 0 |
| `Link` succeeds, `Remove(tmp)` fails | The file exists; a stray `.answer-*.tmp` remains | logged; **not** missing; a stray temp is outside the `{sha}.txt` pattern |
| The JSONL line fails to encode (e.g. a NaN `*float64`) | Logged, **counted** (D3); the file was already linked, so an unnamed file exists | `WriteErrors() > 0` → INCOMPLETE |
| A call site sets `AnswerSHA256` without `SetAnswer` | The guard refuses to write | `GuardRefusals() > 0` → INCOMPLETE, never cleared |
| `f.Close()` fails at the end | Logged today only | `CloseErr` → INCOMPLETE |
| Channel buffer full | Record **and** its answer are dropped (`Dropped()` today) | already INCOMPLETE |
| `SIGKILL` | Buffered records and answers are lost together | the run is discarded either way |
| Crash between temp write and link | A stray `.answer-*.tmp`; **no** `{sha}.txt` and no record naming it | readers match `^[0-9a-f]{64}\.txt$` only; a clean `Close` leaves none (asserted) |
| Same text, same instant | One writer goroutine: no race, one file | acceptance 4 |
| `Link` unsupported (a filesystem without hard links) | Every first sighting fails → `missing` | loud at the first request; unknown 5 |
| Record logged after `Close` | Skipped, **not counted** (F-F, unchanged), and so is its file | F-F's own fix |

## 4. What this costs on a measured path

Hit path: one string-header assignment; the hash was already computed. Writer goroutine: a map
lookup per record (it already makes one unbuffered `write(2)` per record), and **per distinct
answer** one create, write, chmod, close, link and remove, against a 4096-record buffer. The
`mu_hit.js` probe repeats one query, so it writes about one file; MISSes are ~0.19 req/s. The
exposure is a **burst of first-seen answers** (the static-cache arm). **Not measured yet.**

**How it is measured (re-posed by `review.md` 2).** A tight `Log` loop enqueues in ~100 ns while the
writer already pays a `write(2)` per record, so a `Dropped() > 0` result for N > 4096 would be
produced by the test's producer, not by the gateway. Instead: time the writer's **drain per
first-seen record**, with **already-seen records as the control**, derive the **sustainable
first-sighting rate**, and compare it with the real bound: first sightings ≤ `CACHE_CAPACITY` =
0.25·K plus MISSes, arriving at the measured hit rate. Both numbers go in the experiment record.
**Not measurable in a unit test:** Spotlight (`mds`/`mdworker`) importing each new `.txt`
(`review.md` 9). That is the author's question 5.

## 5. Tests (all new files; no existing test is edited)

**`telemetry/answers_test.go`** — the store in isolation, seams `l.createTemp`, `l.linkFile` and
`l.removeFile` (defaults `os.CreateTemp`, `os.Link`, `os.Remove`; `createTemp` added by the
implementation review, I1), all set **before the first `Log`**:
- **byte-exact table** (7): `\r\n`, trailing newline / none, multi-byte, empty. The oracle hash is
  `crypto/sha256` **directly**, never telemetry's helper;
- **dedupe** counted at the seam (4);
- **order**: wrap the real `linkFile`; after it returns assert the file exists **and** the record's
  line is **absent**; assert the hook ran ≥ N times (else the test is vacuous when `storeAnswer` is
  skipped) (5);
- **a failed `Link`** with a non-`EEXIST` error: no `.tmp`, no `{sha}.txt`, `AnswersMissing()==1`,
  the line still written; then a retry with the seam restored clears it to 0 (6);
- **`Link` succeeds, `Remove` fails** (a `remove` seam): not missing, 0;
- **a real `chmod 0o500` directory** (`CreateTemp` fails), read **after `Close` has drained**, no
  retry in it;
- **empty text** is a file named `e3b0c442…`;
- **guard**: a mismatched record is refused, `GuardRefusals()==1`, and a later record with the same
  hash and the right text **does not clear it**;
- **write-once** (9a): pre-create `{H}.txt` with **sentinel bytes ≠ the text**, log a record with H,
  assert bytes **and** inode unchanged;
- **`Open` on a `raw/` that holds `requests.jsonl` and no `answers/`** creates nothing and refuses
  (9b); a pre-existing `answers/` refuses and removes only the `requests.jsonl` it made;
- **D3**: a NaN `*float64` makes `Encode` fail: `WriteErrors()==1`, the file was linked and **no
  line names it**;
- **nil-safety**: the three accessors on a nil Logger; a record logged after `Close` creates no
  file (8, an *extension* of `TestLogAfterCloseIsSafe`, not an edit);
- **`-race`**, with a test that reads `AnswersMissing()` **while `Log` calls are still running**,
  else the race run proves nothing about `missing`'s mutex;
- **drain-rate measurement** (§4): recorded, not asserted.

**`httpapi/answerstore_test.go`** — the exit test (1–3). Real `Logger`, the 1.2 harness's fakes, a
pre-warmed store, every serving path, then read **only** `raw/` (the store is not touched: "flush"
is ceremonial). **Three distinct texts, so no path can heal another** (`review.md` 1): Tier-1 served
from an entry seeded with **its own text**, Tier-2 from a hit fixture whose `Answer` is overridden
to **a third text**, MISS from the fake `Answer`'s `p.answer`. Plus a coalesced follower and a
repeat of one answer. Assertions: the invariant both ways (every non-empty hash has a file; every
file is named); `GuardRefusals()==0`; for every response with `touched && Code==200` (an F-D
follower's recorder is untouched yet reports 200) the file's bytes equal the JSON-decoded `answer`;
`""` records create no file.

**`cmd/gateway/incomplete_test.go` and `finish_test.go`** — a new test for `incomplete` (10) and, from the
implementation review (I2), for `finishRun`, the call site that does `Close` and **then** reads the
counters, against a real Logger. `incomplete`'s table: each field alone, each
pair, none; the `Dropped` row covers the branch no test has run.

**Mutations**, each applied to a copy and each expected to be caught by a named test, as in
1.2/1.3/F-A: M1 write on MISS only · M2 line before file · M3 one call site left on the old
assignment · M4 `seen` set before the write succeeds · M5 `missing` never cleared · M6 no dedupe ·
M7 hash of trimmed text · M8 a failed write not counted · M9 guard removed · M10 temp file left
behind after a failed `Link` · M11 `Rename` instead of `Link` · M12 `Open` makes the directory
first · M13 a failed line write not counted · **M14** `Remove` failure marks the hash missing ·
**M15** `EEXIST` treated as an error · **M16** guard refusal cleared by a later retry · **M17, M18** `incomplete` ignores a field / crosses two ·
**M19–M25** (implementation review): a failed temp write ignored, `finishRun` reads before `Close`, a field
not passed, the Tier-2 or MISS site reverted, a consistent-but-wrong text, `SetAnswer` skipped when the
client left.

## 6. Unknowns that still need verifying

1. **The drain rate and the sustainable first-sighting rate** (§4). Estimated, not measured.
2. **Byte-exactness against the wire.** `writeJSON` replaces invalid UTF-8 with U+FFFD; the cases
   where that would matter are **unreachable** (protobuf-go validates a proto3 `string`), stated in
   the ADR as following from that.
3. **Memory held by the buffer:** 4096 buffered records can pin ~4096 answers (a few MB). Small;
   stated, not measured.
4. **U8 / temperature 1:** the author's call (`spec.md` open question 1).
5. **`os.Link` on the results filesystem.** APFS and HFS+ support hard links, the only filesystem this
   runs on; not tested on anything else. Failure is loud (§3).
6. **Does the judge need the evidence text in `raw/` too?** Under `mutation: on` SOURCE is
   recoverable only if the mutation harness writes the applied update set with epochs into `raw/`;
   otherwise 5.1 needs the chunk text as served, which the gateway has held since 1.4: a second §H
   field and a sibling store. **Not hedged here** (a content-agnostic `storeBlob` would be unused
   code: no field can be added without a contract decision). 5.1 owns it.
7. **Spotlight** importing each new file during a measured window (`review.md` 9): the author's.
8. **Publication posture:** the author's, before the first v1 run.
9. **Directory or `answers.jsonl`** (§1): the author's.
