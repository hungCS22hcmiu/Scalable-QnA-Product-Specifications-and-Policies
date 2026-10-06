# Spec — answer-text-storage

**Scope:** L · **Opened:** 2026-10-06 · **Opener:** `/task` · **Phase:** 1, item **1.5**
**Revision 3**, after `review.md`. Rev 2 applied `impact.md`'s eight corrections; rev 3 applies the
design review's (finding numbers in brackets). `design.md` is at rev 3 with it.

## The change in one sentence

The gateway writes the text behind **every non-empty `answer_sha256` it logs** to
`raw/answers/{answer_sha256}.txt` in the run's `raw/` directory, content-addressed and byte-exact,
so that a finished run's answers can be read back from `raw/` alone, with the cache flushed and the
generator unloaded.

## Why

`interfaces.md` §H records `answer_sha256` and never the text. The judge (item 5.1) runs **offline
with the generator unloaded** and keys its verdicts by hash. The only other place the text lives is
the cache, a **bounded LRU** the gateway evicts from (`CACHE_CAPACITY = round(0.25·K)`), so most
served answers are gone from it by the time judging starts. An `answer_sha256` with no text behind
it is a key to nothing. Re-generating is no alternative either: the Modelfile sets `temperature 1`
(U8, below), so a second generation is a **different answer**, and §H already says the hash must be
taken from what was served.

Today the three serving paths call `sha256Hex` (`handler.go:207`, `:308`, `:524`) and keep nothing
else. That is the whole gap.

## What it serves

- **Phase 1, item 1.5** (`super-plan.md`): *"Content-addressed `raw/answers/{answer_sha256}.txt`"*.
  Exit clause: *"a judged answer is recoverable from `raw/` alone"*; *Done when*: *"A run's answers
  are reconstructable from `raw/` alone, with the cache flushed."*
- **Contribution C3** (evaluation validity): the input contract of **5.1**, which reads "Phase 1's
  answer store", and through it of every false-hit figure.
- **It changes a frozen document.** §H is frozen at v0.10 and the plan says this item *"needs a
  numbered decision"*: **ADR-005**, `interfaces.md` **v0.11**, `/approve contract`.
- **FR / NFR / RR:** `requirements.md` is an unfilled skeleton. In its terms this is a **Research
  Requirement**: violating it voids a result *silently*, because a verdict whose answer cannot be
  recovered cannot be audited. No ID is assigned (the skeleton assigns none yet).

## The invariant, stated on the record and not on delivery

> **In a run that is not INCOMPLETE, every record whose `answer_sha256` is non-empty names a file in
> `raw/answers/` whose bytes hash to that name, the file was visible before the line that names it,
> and the directory holds no file that no record names.** *("Not INCOMPLETE" is load-bearing, review 8:
> a failed write still writes its line, which then names a hash with no file; a failed line write
> leaves a file no record names. Both are counted and make the run INCOMPLETE.)*

Stated this way because a **MISS whose client left** still carries a hash (`abandon_test.go:192-207`):
the answer was generated and logged though it reached nobody. `""` means *no answer was served*
(SHED, ABANDONED, GENERATION_FAILED, a Tier-1 lookup error), and it is **not** null. An **empty
answer text is a real answer**: it hashes to `e3b0c442…` and is stored as an empty file.

## Acceptance — each a check that can be run

1. **The exit test (binding).** A Go test drives a workload through `Ask` against fakes and the
   **real** `telemetry.Logger` in a temp `results/` dir. It covers a MISS, a TIER1_HIT, a TIER2_HIT,
   a coalesced follower, and a repeat of one answer. It reads **only** `raw/`. The invariant above
   holds **both ways** (every non-empty hash has a file; every file is named), and for every response
   with `touched && Code == 200` (an F-D follower's recorder is untouched yet reports 200) the file's
   bytes equal the JSON-decoded `answer` the client received for that `request_id`.
   `GuardRefusals() == 0`.
2. **Hits write too, and no path can heal another** [review 1]. The store starts **pre-warmed**, and
   **each of the three serving paths serves a text that no other path serves in the run**: Tier-1
   from an entry seeded with its own text, Tier-2 from a fixture whose `Answer` is a third text, MISS
   from the fake's `p.answer`. Otherwise an MISS-only writer (M1), or a call site left on the old
   assignment (M3), is hidden by another path writing the same text. The guard-refusal count is never
   cleared, so M3 fails whatever the order of requests.
3. **No text, no file.** SHED, ABANDONED and GENERATION_FAILED records carry `answer_sha256 == ""`
   and create no file. The directory holds exactly the distinct hashes the records name, no more
   (no orphan, no `.tmp` residue after a clean `Close`) and no fewer.
4. **Dedupe.** Ten requests served the same text produce **one** file, written **once** (counted at
   the write seam, not inferred from the directory).
5. **Order.** For each record, its file is **visible before its line is**. Asserted by wrapping the
   real `link` step: after it returns, the file exists **and** the record's line is absent; and the
   hook ran at least N times, so the test is not vacuous when the store is skipped. (Not "durable":
   nothing is fsynced, and on macOS `fsync` is not durable without `F_FULLFSYNC`. A `SIGKILL`ed run
   is discarded.)
6. **A failed write is loud, never silent.** With `raw/answers/` made unwritable, the request is
   still **served** and its record **written**, and `AnswersMissing()` reports the hash. Failure is
   injected at the **`link` seam** (a non-`EEXIST` error: no `.tmp`, no `{sha}.txt`, count 1), so it
   is deterministic; a real `chmod 0500` directory covers only `CreateTemp`, read after `Close` has
   drained. A later record with the same hash **retries**; a retry that succeeds clears it. A `Link`
   that succeeds followed by a `Remove` that fails is **not** missing [review 3]. The extracted
   completeness function returns an error, so `main` ends the run INCOMPLETE.
7. **Byte-exact.** Text containing `\r\n`, a trailing newline, no trailing newline, multi-byte
   characters and the empty string round-trips with an identical hash. Invalid UTF-8 is **unreachable**, not merely excluded: `AnswerChunk.text` is a proto3 `string`
   and protobuf-go validates it on unmarshal [review 17]. The test oracle is `crypto/sha256`
   directly, never telemetry's helper [review 14].
8. **The disabled logger is unchanged.** `RUN_ID` unset writes nothing and starts nothing;
   `answer_sha256` is on the record exactly as before; `AnswersMissing`, `GuardRefusals` and
   `WriteErrors` are **nil-safe** (`make dev` calls them on a nil Logger). A record logged **after `Close`** creates no
   file (an *extension* of `TestLogAfterCloseIsSafe`, not an edit).
9. **Write-once.** Reopening a finished run still fails (`TestOpenRefusesAnExistingRunFile`).
   A file already in `raw/answers/` is **never rewritten**: pre-create `{H}.txt` with **sentinel bytes
   that differ from the text**, log a record with H, and its bytes **and** inode are unchanged
   (catches both `Rename` and an in-place truncate). `Open` on a `raw/` that holds `requests.jsonl`
   and **no `answers/`** creates nothing and refuses; a pre-existing `answers/` refuses and removes
   only the `requests.jsonl` this call made.
10. **The completeness rule is a function with a test.** `incomplete(runCounts{Dropped, WriteErrors,
    GuardRefusals, AnswersMissing, CloseErr})` is a pure function in `cmd/gateway`, **a struct so two
    `int64`s cannot swap**, table-tested: each field alone, each pair, none (it also covers the old
    `Dropped` branch, which no test has ever run). It is called **after `Close`**. A guard refusal
    **voids the run** (default), because it means a call site skipped `SetAnswer`.
11. **Contract.** `interfaces.md` v0.11 and ADR-005 state the layout, the write order, "no text, no
    file", `""`-not-null, the incompleteness rule and the **publication posture** (below). Checked by
    named greps, **not** `make check` (which cannot fail, `Makefile:404-413`):
    `grep -n 'Current version.*v0.11' docs/contracts/interfaces.md`; `grep -L 'raw/answers'
    docs/architecture.md docs/contracts/interfaces.md experiments/README.md` **prints nothing** (a
    plain `grep` over three files exits 0 if any one matches, the same flaw [review 6]); `grep -n
    'ADR-005' docs/decisions.md`; and `grep -n '//.*judge dedupe key' docs/contracts/interfaces.md`
    finds nothing (v0.11 does not re-ratify the label in the field comment [review 10]; the phrase
    still appears in the v0.11 changes block and Versioning row, which say it was *dropped*).
12. **`make verify` exit 0**, `go test -race` once on `telemetry` and `httpapi` with the result
    recorded, and `git diff --exit-code contracts/` clean. *"Proto drift" as `/verify` runs it checks
    nothing:* both stub directories are gitignored, so a `git diff` on them is always clean
    (`impact.md` §10.6). Reported, not fixed here.
13. **Throughput (record-only, re-posed [review 2]).** Not a `Dropped()` assertion: a tight `Log` loop
    would manufacture drops with or without this change. Time the writer's **drain per first-seen
    record against already-seen records as the control**, derive the sustainable first-sighting rate,
    and compare it with the real bound (first sightings ≤ `0.25·K` plus MISSes). Both numbers go in
    the experiment record.

## Not in this task

- **The judge harness (5.1)** and anything that reads `raw/answers/`. 5.1 must also pick **one**
  dedupe key (`sha256(query ‖ answer)` per `data-card.md:141` and `interfaces.md:491`, or the bare
  `answer_sha256` per `super-plan.md` 5.1). Both are computable from `raw/`.
- **Retrieved chunk text.** The record carries `retrieved_chunk_ids`; the text lives in the corpus.
  It is recoverable from the frozen corpus **only when `mutation: off`**: under `mutation: on` the
  text at serve time depends on `dataset_epoch_at_retrieval` plus the ordered update set. Whether the
  judge needs the evidence text is 5.1's question; the exit clause says *"a judged **answer**"*.
- **The run manifest** (`manifest.yaml`): no writer exists. The new counts belong beside
  `Dropped()`; 1.6's P1 manifest work records them.
- **Answer determinism (U8).** See open question 1.
- **Compression, rotation, pruning.** Bounded by distinct served answers. A size problem is a new
  decision.
- **A verifier script for finished real runs.** A candidate follow-up; the Go test is the binding
  evidence.
- **F-F** (a record logged after `Close` is skipped and uncounted; a `Log` racing `Close` panics).
  `super-plan.md` leaves it to its own fix. **This task does not widen it**: the skipped set is fixed by
  the CAS at the start of `Close`, not by how long `Close` takes [review 12].
- **Editing the shared test helper** `checkEveryRecord` (`harness_test.go:1023`). See open
  question 4.
- **The stale version strings** (`CLAUDE.md:106`, `.claude/agents/contract-reviewer.md:11`,
  `architecture.md:30` all say v0.9). Edited only with the author's OK.

## Open questions — the author's

1. **U8, temperature 1.** `super-plan.md`: generation determinism *"needs an investigation before
   1.5 or 5.1 is built on it."* **My reading: it does not gate 1.5** (the store keeps what was
   served, whatever the temperature) and does gate 5.1, where hash dedupe saves nothing if every
   miss makes a new text. It is the author's plan text, so it is raised, not decided.
2. **⚠️ Publication posture** (`impact.md` §4). `experiments/results/*/raw/` is **not gitignored**
   and `origin` is public GitHub. `requests.jsonl` already carries verbatim PQA `query_raw`
   (redistribution not granted); this task adds PQA-derived answer text. It collides with
   `super-plan.md` 5.4's "clean checkout". **Recommendation:** ignore `experiments/results/*/raw/`
   now, reword 5.4 to "clean checkout + the raw archive", and record it in ADR-005. Needed before
   the first **v1** run, not before this code; the author decides, and nothing here touches
   `.gitignore` without that.
3. **Count a failed JSONL line write too?** (decision **D3**, `design.md` §2). Today an encode error
   is only logged: lines lost, `Dropped()` 0, run not INCOMPLETE. **The review shows this is not
   scope creep** (review 8): with a file linked and its line then failing to encode, a file exists that
   no record names, so without D3 the second half of the invariant ("no unnamed file") is violated
   silently. **Default: counted**, ~3 lines, in the same completeness function; the `Close` error
   joins it. It is the author's to cut, in which case the ADR states the asymmetry instead.
4. **Should a guard refusal void the run?** (`design.md` §2). It means a call site skipped
   `SetAnswer`. **Default: yes**, via a never-cleared counter; otherwise a later retry with the right
   text would mask a defect that invalidates the measurement.
5. **`raw/answers/` directory or one `raw/answers.jsonl`?** (`design.md` §1, review 15). The file is
   the smallest version: it drops the temp/`Link`/`Remove` machinery, the three-step `Open`, and the
   per-file Spotlight and APFS (≥ 4 KB) cost, and loses atomic per-answer publication and
   `cat raw/answers/$sha.txt`. **Default: the directory**, as the plan names it.
6. **Spotlight.** `/` is indexed, so every new `raw/answers/*.txt` is imported by `mds`/`mdworker` on
   the measured machine in the measured window (up to `0.25·K` files in the static-cache arm's
   first-sighting burst). Unmeasured. Make **excluding `experiments/results/` from Spotlight a run
   precondition**, like keeping Ollama auto-update off, or measure it? Needed before Phase 3.
7. **5.1's verdict key.** A bare `answer_sha256` cannot key Tier-2 verdicts (a reused answer is
   byte-identical across queries, so a true hit and a false hit on the same answer would collapse
   into one verdict and the false-hit rate would be biased toward whichever came first). v0.11
   therefore does not call it "the judge dedupe key", and **`super-plan.md` 5.1's wording
   ("deduped by `answer_sha256`") is flagged, not edited**: it is 5.1's design.
8. **Strengthen `checkEveryRecord`?** It already recomputes `sha256(answer)` on every 200 in ~30
   tests; one added assertion would give all of them the file check. It edits an existing test
   helper and CLAUDE.md makes tests immutable. **Default taken: no**; new assertions live in new
   files.

## Limitations to state in the ADR

- `SIGKILL` loses what is still in the channel buffer, **records and answers alike**; a killed run
  is discarded either way.
- The store proves **a file exists with the right hash**, and for valid UTF-8 that the bytes equal
  what the client decoded. It cannot prove a serving bug did not send other bytes than it logged,
  beyond the paths acceptance 1 drives.
- A record dropped by a full buffer (`Dropped() > 0`) is already a hole; its answer is not written
  either, and the run is already INCOMPLETE for that reason.
- **F-F:** a record logged after `Close` is skipped and uncounted. This task does not widen it.
- **`Log` racing `Close`** panics inside `Ask`'s deferred emit, where `net/http`'s per-connection
  recover swallows it: a lost record with only "http: panic serving" on stderr.
- **The INCOMPLETE verdict lives only in the exit status and stderr until P1 lands.** *Answers
  recoverable from `raw/` alone* holds; *admissibility decidable from `raw/` alone* does not.
- **`EEXIST` is treated as success because `Open`'s leaf `Mkdir` guarantees a fresh directory and the
  writer goroutine is the only creator of files in it**, not because of SHA-256.
