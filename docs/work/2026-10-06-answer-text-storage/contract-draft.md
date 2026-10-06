# Contract draft — `interfaces.md` v0.11 and ADR-005

**Status: DRAFT for `/approve contract`. Nothing here has been applied.** `docs/contracts/interfaces.md`
and `docs/decisions.md` are unchanged. On approval, plan step 1 applies this text **verbatim**; the
only thing left open then is each `⟦PENDING⟧` marker, which plan step 9 closes with a measured number
or the author's call. Decisions behind it: `approvals.md` (1–3 and 5 decided 2026-10-06), `review.md`.

**Both sides of the seam.** The writer is the gateway (`telemetry` + the three serving sites in
`httpapi`). The readers are **future**: item 5.1 (judge), 5.4 (figures) and any analysis script. No
reader exists today, so there is no consumer to break; the draft pins what they may rely on (Part A,
rules 1–9). The Go↔Python **wire is untouched**: `.proto`, §A–§G, every JSON key and the HTTP response
are unchanged (`git diff --exit-code contracts/` stays clean). No Python code changes.

---

# Part A — `docs/contracts/interfaces.md`, v0.10 → v0.11

## A1. Header (`:3`)

`**Status:** Draft v0.10 · … · **Revised:** 2026-10-05` becomes
`**Status:** Draft v0.11 · … · **Revised:** 2026-10-06`.

## A2. New block, inserted after the v0.10 block (`:55`)

> **v0.11 changes.** §H gains the **answer store**: the text behind every non-empty `answer_sha256`
> is written to `raw/answers/{answer_sha256}.txt` (**ADR-005**, `super-plan.md` item 1.5). Before this
> the log held a hash and the text lived only in the bounded LRU cache, so by the time the judge ran
> offline most `answer_sha256` values named nothing. **No JSON field is added, removed or renamed, and
> no wire shape changes**: §A–§G and the `.proto` are untouched. Two things change meaning without
> changing shape. **(1) A run can now be INCOMPLETE for a new reason** (a hash a record names has no
> file, a line failed to encode or write, the log failed to close, or an answer and its hash disagreed), on top
> of dropped records. **(2) `answer_sha256` is no longer described as "the judge dedupe key"**: a
> Tier-2 hit serves another query's answer byte for byte, so a bare answer hash would merge a true hit
> and a false hit on the same answer into one verdict (see the §H warning). **A log written before the
> 1.5 commit has no answer store and cannot be judged.**

## A3. Request-flow line (`:96`)

`Every request also appends one (H) evaluation-log record to results/{run_id}/raw/` becomes

`Every request also appends one (H) evaluation-log record to results/{run_id}/raw/, and every answer it serves is stored under results/{run_id}/raw/answers/`

## A4. §H — new subsection, inserted after the "Four evaluation metrics…" paragraph (`:442`)

> **The answer store (v0.11, ADR-005).** The gateway keeps the **text** of every answer it serves,
> content-addressed, beside the log:
>
> ```
> results/{run_id}/raw/
> ├── requests.jsonl                 one JSONL record per request
> └── answers/
>     └── {answer_sha256}.txt        the answer exactly as served
> ```
>
> 1. **Name and bytes.** `{answer_sha256}` is the record's field, lowercase hex, 64 characters, plus
>    `.txt`. The file holds the **UTF-8 bytes of the served answer exactly**: no newline added, no
>    normalisation. The file's SHA-256 is its name. Readers match `^[0-9a-f]{64}\.txt$`, **verify the
>    hash when they read**, and ignore anything else. A `.answer-*.tmp` file is residue of a crash or of
>    a failed temp-file removal; readers ignore it.
> 2. **One file per distinct hash,** created once and never rewritten.
> 3. **Every path that serves text writes it:** TIER1_HIT, TIER2_HIT, and MISS, including a MISS whose
>    generation completed though the client left, and a coalesced follower. (An ABANDONED request,
>    rule 4, is one whose generation did not complete.) **A hit writes too**: the entry may predate the run, so
>    a hit can be the first time this run sees its text.
> 4. **No text, no file.** A record that served no answer (the log-only `cache` values SHED,
>    ABANDONED and GENERATION_FAILED, which §A's enum does not carry; or a Tier-1 lookup error) has `answer_sha256` equal to `""` and creates no file. `""` is **not** null.
>    An **empty answer is a real answer**: it hashes to
>    `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` and is stored as an empty file.
>    "Has an answer" means `answer_sha256 != ""`.
> 5. **The invariant. In a run that is not INCOMPLETE,** every record whose `answer_sha256` is non-empty
>    names a file in `answers/` whose bytes hash to that name, and **`answers/` holds no
>    `{answer_sha256}.txt` that no record names**. **Order:** the writer publishes the file before it
>    writes the line that names it (one writer, the file and then the line; nothing is fsynced, and on
>    macOS an `fsync` is not durable without `F_FULLFSYNC`). That is a property of the writer, **not
>    something a reader can check from `raw/`**, and it holds for a hash's first successful write: if
>    the first write failed and a later record with the same hash retried successfully, the first
>    record's line precedes its file. Admissibility turns only on the file existing at the end.
> 6. **INCOMPLETE.** A run is INCOMPLETE, and **not admissible**, if any of these holds when it ends:
>    records were dropped by a full buffer; a record's line failed to encode or write; a hash a record names has
>    **no file** at that moment (a write that failed and was not retried successfully); a record's
>    answer text did **not** hash to its `answer_sha256` (a call site set one without the other: a
>    defect, checked at a hash's first sighting and never cleared by a later retry); or the log failed to close cleanly. The gateway reports
>    this by **exit status and log at shutdown**. **Until the run manifest exists (`decisions.md`
>    P1) the verdict is not recorded in `raw/`**, so *the answers are recoverable from `raw/` alone*
>    holds, and *the run's admissibility is decidable from `raw/` alone* does not.
> 7. **What it proves.** That a file with the right hash exists for each named answer. For valid
>    UTF-8 the bytes also equal what the client decoded from the JSON response; invalid UTF-8 cannot
>    occur in a generated answer, because `AnswerChunk.text` is a proto3 `string` and protobuf-go
>    validates it on unmarshal, and a cached answer is a previously generated one.
>    It does **not** prove that the serving path sent the client the bytes it logged beyond the paths
>    the tests drive.
> 8. **Not covered.** The **retrieved chunk text** (the judge's SOURCE input) is not stored: the log
>    carries `retrieved_chunk_ids`, and the text is recoverable from the frozen corpus **only when
>    `mutation: off`**. Under `mutation: on` the text at serve time depends on
>    the ordered update set and the epoch it had reached: `dataset_epoch_at_retrieval` is logged, but
>    nothing in `raw/` yet records the update set with its epochs.
> 9. **Not published.** `experiments/results/*/raw/` is gitignored: it holds Amazon-PQA question text
>    (`query_raw`) and LLM answers grounded on PQA chunks, redistribution is not granted, and the
>    remote is public. `manifest.yaml` stays trackable.
>
> **What cannot be recovered even so:** a record skipped because it was logged after `Close` (F-F) or
> lost to a `Log`/`Close` race leaves neither a line nor a file, and is not counted. F-F is a
> `super-plan.md` finding with its own fix, the race is part of it per that finding's trail
> (`docs/work/2026-10-04-httpapi-tests/review.md`), and neither is widened by this change.

## A5. §H — the example comment (`:487`)

`"answer_sha256": "3a71..."            // ⚠️ judge dedupe key, see below` becomes

`"answer_sha256": "3a71..."            // the answer's address in raw/answers/ (v0.11); "" when no answer was served`

## A6. §H — the warning that follows the example (`:491`), replaced in full

> ⚠️ **`answer_sha256` is taken when the answer is served and cannot be reconstructed after the fact.**
> It is the `sha256` of the served answer text, and since v0.11 the text itself is kept at
> `raw/answers/{answer_sha256}.txt`, so it can be read back without the cache. The hash must still be
> taken at serve time rather than recomputed from a possibly re-generated answer: the Modelfile sets
> `temperature 1` (U8), so a second generation can be a different answer.
>
> ⚠️ **It is not, by itself, a judge verdict key.** The evaluation keys verdicts by
> `sha256(query ‖ candidate_answer)`. A Tier-2 hit serves a cached answer to a *different* query
> byte for byte, so a true hit `(q1, A)` and a false hit `(q2, A)` share one `answer_sha256`; keyed on
> the answer alone they would collapse into one verdict and the false-hit rate would be biased toward
> whichever came first. The bare `‖` is ambiguous without a delimiter; **item 5.1 fixes it.** The
> layout serves either key, since both are computable from `query_raw` and `raw/answers/`.

The second ⚠️ paragraph of the current text (`similarity_only_decision` is RETIRED) is unchanged.

## A7. §H — field-notes table, one new row (after the `t1_key` row, `:500`)

`| `answer_sha256` | **v0.11.** The SHA-256 of the answer text as served, lowercase hex, and the name of the file that holds that text in `raw/answers/`. `""` (not null) means no answer was served. See "The answer store" for the invariant and for what makes a run INCOMPLETE |`

## A8. §H — the closing line (`:508`), replaced

`` `raw/` is write-once, so this file is immutable once a run completes. ``

becomes

> `raw/` is write-once, so `requests.jsonl` **and every file under `answers/`** are immutable once a
> run completes. A run id is never reused: the gateway creates `requests.jsonl` exclusively and then
> `answers/` (non-recursively) and **refuses to start** if either already exists.

## A9. Versioning (`:514-520`)

- `:514`: *"A change to any wire shape, the chunk-ID format, or the Redis schema is a design decision"* gains **", or the §H run layout under `raw/`,"** after "the Redis schema" (a change to what a run leaves on disk is as silent a drift as a wire change).
- `:516`: `**Current version: v0.10** (2026-10-05).` → `**Current version: v0.11** (2026-10-06).`
- New first row in the table (above v0.10):

`| **v0.11** | 2026-10-06 | §H gains the **answer store**: the text behind every non-empty `answer_sha256` is written to `raw/answers/{answer_sha256}.txt`, so a run's answers are recoverable from `raw/` alone with the cache flushed (**ADR-005**, item 1.5). No JSON field changes and no wire shape changes: §A–§G and the `.proto` are unchanged. A run is now also INCOMPLETE when a named hash has no file, a line failed to encode or write, the log failed to close, or an answer and its hash disagreed. `answer_sha256` is no longer called the judge dedupe key (a bare answer hash cannot key Tier-2 verdicts). `raw/` is gitignored. A log written before the 1.5 commit has no store and cannot be judged |`

## A10. Edits to other documents that follow the contract (not part of the contract)

Listed so the diff is complete; each is a plan step, none is drafted here.
`docs/architecture.md` (the `raw/` tree lists `requests.jsonl` and `answers/`; telemetry's "Owns" cell),
`experiments/README.md:7`, `docs/data-card.md` §1 (a row for run outputs and their licence posture),
`docs/super-plan.md` (1.5 done; 5.1's wording flagged, not edited). **Stale `v0.9` strings**
(`CLAUDE.md:106`, `.claude/agents/contract-reviewer.md:11`, `architecture.md:30`): only with the
author's OK.

---

# Part B — `docs/decisions.md`, ADR-005

## B1. Summary table, one new row

`| ADR-005 | Served answer text is stored content-addressed in `raw/answers/` | in force | none — no runs yet; a log written before the 1.5 commit has no answer store and cannot be judged |`

## B2. The entry, appended after ADR-004

### ADR-005 — Served answer text is stored content-addressed in `raw/answers/`
**Decided (method)** · 2026-10-06 · *`interfaces.md` §H v0.11, `gateway/internal/telemetry/evallog.go`, `gateway/internal/httpapi/handler.go`, `gateway/cmd/gateway/main.go`, `.gitignore`, `super-plan.md` 5.4; trail `docs/work/2026-10-06-answer-text-storage/`*

The gateway writes the **text of every answer it serves** to
`results/{run_id}/raw/answers/{answer_sha256}.txt`: content-addressed, one file per distinct hash,
byte-exact, written by the evaluation logger's own writer **before** the record line that names it.
A run in which any named hash has no file, any line failed to encode or write, an answer and its hash
disagreed, or the log failed to close, is **INCOMPLETE** and not admissible. `experiments/results/*/raw/`
is **gitignored**. This is the decision `super-plan.md` item 1.5 said §H needed before it could change.

- **Rationale:**
  - **The judge runs offline with the generator unloaded**, and §H recorded `answer_sha256` and never
    the text. The only other copy is the cache, a **bounded LRU** the gateway evicts from
    (`CACHE_CAPACITY = round(0.25·K)`), so by judging time most hashes named nothing. A hash with no
    text behind it is a key to nothing.
  - **Re-generating is not an alternative.** The Modelfile sets `temperature 1` (U8), so a second
    generation can be a different answer, and §H already requires the hash to come from what was served.
  - **Content-addressed**, because 5.1's work list is the set of distinct answers, and a directory of
    them is that list. Under Zipf redundancy hits dominate, so a per-request copy would grow with the
    hit count, not the distinct-answer count.
  - **Written by the logger's writer, before the line**, so the order is structural. Nothing at a
    call site has to be remembered, and a record dropped or skipped loses its line and its file
    together.
  - **A guard** refuses to write a file whose bytes do not hash to the record's hash. It catches a
    call site that sets the hash and skips the text, which would otherwise publish an empty file
    under another text's name: that passes every "file exists" check and is wrong.
- **Alternatives:**
  - **Inline the text in every `requests.jsonl` record.** A record without its text becomes
    unrepresentable, which is its strength. Rejected: the plan names the directory; the file grows
    with the hit count; every analysis that parses it for latency or hit rate would read text it
    never uses.
  - **One `raw/answers.jsonl`**, a `{sha, text}` line per first sighting. The smallest version, and a
    real rival: it drops temp-file publication, the three-step `Open`, the `EEXIST` question and the
    per-file Spotlight and APFS (≥ 4 KB per file) cost. It loses atomic per-answer publication (a full
    disk leaves a torn line, not no file) and open-by-hash. **Rejected by the author's default**
    (2026-10-06), because the plan names the directory and 5.1 reads by hash. Reversible: only the
    writer and the §H layout wording change.
  - **A separate `AnswerStore` called from `Ask`.** Rejected: the handler gains an I/O concern and a
    second failure counter, and the file gets no ordering against the record.
  - **Write at `cache.Put`.** Rejected: it covers MISS only, and a hit on an entry that predates the
    run is exactly the case where this run has never written the text.
  - **Keep the text in Redis.** Rejected: bounded LRU, and the next run may flush it.
- **Consequences:**
  - **The invariant** (§H v0.11, rule 5). It holds in a run that is not INCOMPLETE, not in every run:
    a failed write still writes its line, which then names a hash with no file, and a line that fails
    to encode after its file was linked leaves a file no record names. Both are counted and make the
    run INCOMPLETE.
  - **The INCOMPLETE conditions are a Research Requirement** in the terms of `requirements.md`
    (violating one voids a result silently). The skeleton assigns no IDs yet, so none is numbered. They
    are: dropped records; a failed line write; a named hash with no file; an answer/hash mismatch (a
    **guard refusal**, never cleared by a later retry, because it means a call site skipped
    `SetAnswer`); a failed close.
  - **The verdict lives in the exit status and the log until P1 lands.** *Recoverable from `raw/`
    alone* holds; *admissible from `raw/` alone* does not.
  - **A `Link` that returns `EEXIST` is treated as success (the file already exists), and that is safe because of the directory,
    not because of SHA-256.** `Open` creates `answers/` with a non-recursive `Mkdir` after claiming the
    run id by exclusive create, so the directory is fresh, and the writer goroutine is the only thing
    that creates files in it. A later change that resumes a run or switches to a recursive `MkdirAll`
    would break exactly this and could silently accept a corrupt existing file.
  - **Invalid UTF-8 is unreachable**, not merely excluded: `AnswerChunk.text` is a proto3 `string` and
    protobuf-go validates it on unmarshal; cached answers come from those texts.
  - **Cost on a measured path.** Hit path: one string-header assignment, since the hash was already
    computed. Writer goroutine: a map lookup per record, and per distinct answer one create, write,
    chmod, close, link and remove. **Measured (plan step 7, `evidence/drain-rate.md`; exploratory, pressure level 2, not citable):** an
    already-seen record adds nothing measurable (≈ 4 µs, the pre-1.5 line cost), and a first sighting adds
    ≈ 440 µs (about 110× a line write), so the writer sustains ≈ 2,250 first sightings/s. Distinct answers
    are at most `0.25·K`, so a drop needs a worst-case burst of them at a high offered rate: above ≈
    16,300 req/s for K = 2,000, ≈ 5,200 for K = 5,000, ≈ 1,450 for K = 10,000, and any burst of ≥ 4,096
    first sightings (K ≥ 16,384) overflows on its own. At the planning figures (generation ≈ 0.19 req/s,
    Tier-2 ≈ 61 req/s) the margin is ≥ 35×; **only a Tier-1-heavy phase at thousands of req/s over a
    large K, in its first seconds, can drop.** A Phase 7 run of that kind checks `Dropped()` and
    `AnswersMissing()` first. Spotlight and the gateway under load are not measured. Not a `Dropped()` assertion: a tight `Log` loop would
    manufacture drops with or without this change.
  - **Limits, stated rather than fixed here:**
    - **F-F:** a record logged after `Close` is skipped and uncounted. Not widened: the CAS at the start
      of `Close` fixes the skipped set, not how long `Close` takes.
    - **`Log` racing `Close`** panics inside `Ask`'s deferred emit, where `net/http`'s per-connection
      recover swallows it: a lost record with only "http: panic serving" on stderr.
    - **`SIGKILL`** loses what is still buffered, records and answers together; a killed run is
      discarded either way.
    - The store proves **a file with the right hash exists**; it does not prove the serving path sent
      the client the bytes it logged beyond the paths the tests drive.
  - **Publication.** `experiments/results/*/raw/` is gitignored (decided 2026-10-06). `requests.jsonl`
    already carried verbatim PQA `query_raw`, and this adds LLM text grounded on PQA chunks;
    redistribution is not granted and the remote is public. `manifest.yaml` stays trackable. **Follow-on
    for `super-plan.md` 5.4:** a clean checkout no longer carries `raw/`, so "regenerate every figure
    from `raw/` on a clean checkout" now means *plus the raw archive*; 5.4 designs how that archive is
    kept and restored. With `raw/` outside version control, git no longer enforces that a finished
    run is write-once, and an edit to one would leave no trace; a hash manifest of `raw/` is not
    planned, and belongs with 5.4 and P1.
  - **Spotlight.** `/` is indexed on this machine, so each new `raw/answers/*.txt` is imported by
    `mds`/`mdworker` during the measured window (up to `0.25·K` files in the static-cache arm's
    first-sighting burst). Unmeasured. ⟦PENDING: the author's call: exclude `experiments/results/` from
    Spotlight as a run precondition, or measure it. Needed before Phase 3⟧.
  - **For 5.1** (flagged, not decided): the verdict key must be `(query, answer)`, not the bare hash,
    and the delimiter in `sha256(query ‖ answer)` is unspecified. `super-plan.md` 5.1's "deduped by
    `answer_sha256`" needs rewording. **SOURCE text is not stored**, and under `mutation: on` is
    recoverable only if the mutation harness writes the applied update set with epochs into `raw/`.
  - **U8** (temperature 1): whether it gates item 1.5 is the author's call (`approvals.md`, open
    question 7). This ADR is written on the reading that it does not, because the store keeps whatever
    was served. It bears on 5.1, where hash dedupe saves nothing if every miss produces a new text.
- **Invalidates:** none — no runs yet. A log written before the 1.5 commit has no answer store, so its
  answers are not recoverable and **it cannot be judged**.
