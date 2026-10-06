# Impact — answer-text-storage

**Author of the analysis:** `impact-analyst` subagent, with file:line evidence; synthesised here.
Four of its claims were **re-checked by hand before being written down** and are marked ✔︎:
the gitignore and remote, `make check`, the untested `Dropped` branch, and the proto-drift row.
Everything unmarked is the subagent's reading and carries its citations.

## 1. Verdict

- **No frozen experimental value is touched and no run is invalidated.** `experiments/results/`
  holds only `.gitkeep` and no `requests.jsonl` exists anywhere on the machine.
- It **does** change a frozen document (§H), so it needs **ADR-005** (the next free number),
  `interfaces.md` **v0.11** and `/approve contract`.
- It changes **what a run must contain to be admissible** (a run with an unnamed-file hash is now
  INCOMPLETE), so the **experiment phase is required, record-only**.
- Two findings matter more than the code (§4 and §7).

## 2. Packages and layering

| File | Change |
| :--- | :--- |
| `gateway/internal/telemetry/evallog.go` (+ tests) | `Record.SetAnswer`, unexported `answerText`, `storeAnswer` on the writer goroutine, `AnswersMissing()`, `Open` creates `raw/answers/` |
| `gateway/internal/httpapi/handler.go` | `:207`, `:308`, `:524` become `rec.SetAnswer(..)`. `sha256Hex` (`:573-579`) has no other user in the module ✔︎ and moves out with its imports (`:5-6`) |
| `gateway/cmd/gateway/main.go` (+ `main_test.go`) | the INCOMPLETE rule beside `:262-264`; log line `:208` |
| tests | new test file(s) in `telemetry` and `httpapi` (see §6) |
| docs | `interfaces.md`, `decisions.md`, `architecture.md`, `experiments/README.md`, `data-card.md`, `super-plan.md` |

- **Layering holds.** `telemetry` is a leaf: imported only by `httpapi/handler.go:22`,
  `cmd/gateway/main.go:24` and `harness_test.go:45`. New imports are stdlib (`crypto/sha256`,
  `encoding/hex`). No edge, no cycle, `go.mod` unchanged.
- `docs/architecture.md:106` says telemetry "Owns: Counters and latency decomposition". It now also
  owns the run's answer store; that cell changes. `architecture.md:15-16` says a directory not
  listed "should not exist", so the tree at `:67-70` must list `raw/requests.jsonl` and
  `raw/answers/`.

## 3. What assumes the contents of `raw/` — nothing does

Nothing in the repository reads `raw/`, so nothing assumes `requests.jsonl` is its only file:
`make figures` calls `make_figures.py`, which does not exist (`Makefile:396-397`); no manifest or
hash step over `raw/` exists (P1, `decisions.md:76`); no hook, command or agent in `.claude/`
mentions it; no test lists the directory (`harness_test.go:750` and `abandon_test.go:297` open
`requests.jsonl` by path). The deleted protocol said `raw/` holds "k6 json, judge outputs, pressure
samples", so it was always meant to hold several things.

## 4. ⚠️ Run output can reach the public remote — an author decision

✔︎ `experiments/results/` is **not ignored**: `.gitignore:58` ignores only
`experiments/results/*/figures/`, `git check-ignore` returns *not ignored* for
`results/run-x/raw/requests.jsonl`, `raw/answers/abc.txt` and `manifest.yaml`, and `origin` is
`github.com/hungCS22hcmiu/Scalable-QnA-…`, public. No hook blocks a commit.

- **The exposure already exists.** `requests.jsonl` carries `query_raw`, verbatim PQA question text,
  and `data-card.md:24` says Amazon-PQA redistribution is **not granted**.
- **This change makes it larger.** Answers are LLM text grounded on PQA chunks, often near-verbatim
  (the harness fixture's answer is "a verbatim substring of p's chunk 0", `harness_test.go:810`).
- `dev-v0` runs are fine (author-written, `.gitignore:20-21`). A **v1** run's `raw/` must never be
  committed.
- **It collides with the plan.** `super-plan.md` 5.4 ("`make figures` regenerates every figure from
  write-once `raw/` on a clean checkout") and proposal §13.5 assume `raw/` is tracked.
- **Needed:** a decision, recorded in ADR-005, **before the first v1 run** (not before 1.5's code).
  The cheapest protective default is one `.gitignore` line, `experiments/results/*/raw/`, with 5.4's
  "clean checkout" reworded to "clean checkout + the raw archive". It is the author's call, so it
  goes in `approvals.md` as open; nothing in this task changes `.gitignore` without it.

## 5. Frozen values and measurement

- **None touched:** `num_ctx`, slot count, embedding model, `DIM`, `top_k`, chunking, FLAT,
  eviction, capacity, δ, `dataset_version`. The store never touches Redis.
- **Hit path:** the SHA-256 is already computed at `:207` and `:308`. New work is one string-header
  copy. No timed span changes: `t_tier1_ms` wraps only `Cache.Get` (`:196-198`), and `t_total_ms`
  and `latency_ms` already include the hash.
- **Writer goroutine:** already one unbuffered `write(2)` per record (`evallog.go:122`). New: a map
  lookup per record, and per **distinct** answer a create, write, close and link. Distinct answers
  are bounded by MISSes (~0.19 req/s) plus first sightings of pre-warmed entries (≤ `0.25·K`); the
  `mu_hit.js` probe repeats one query and writes about one file.
- **The risk is a burst of first-seen answers** (the static-cache arm) pushing the 4096-slot buffer
  to drop. **Unmeasured.** A burst test is in the plan and its result goes in the experiment record.
- **Semantic change:** a run is now also INCOMPLETE when a named hash has no file. That is a
  run-admissibility rule (an RR). No §H key, span or counting rule changes.
- **Invalidates:** none (no runs). **Experiment phase: required, record-only.**

## 6. Contract and tests

**Unchanged:** `.proto`, §A–§G, the HTTP response and every JSON key (the unexported field never
reaches JSON). The `.proto` must not appear in the diff.

**`interfaces.md`:** `:3` header; a "v0.11 changes" block (note the v0.8 block at `:57` is already
out of order); `:96` request-flow line; `:440` §H intro (layout, lowercase-hex names, raw UTF-8
bytes with no added newline, file before line, "no text, no file", `""` not null means no answer,
empty text hashes to `e3b0c442…`); `:487` and `:491` (`answer_sha256` warning: *recoverable from
`raw/answers/` only*); `:508` ("this file is immutable" → plural, plus the INCOMPLETE rule);
`:516` current version and a new row at `:520`. **`decisions.md`:** ADR-005, Summary row, the
`Invalidates:` line.

**Stale version strings the spec omitted:** `.claude/agents/contract-reviewer.md:11` says
"currently v0.9" (the reviewer this contract phase will use), `CLAUDE.md:106` says "At v0.9", and
`architecture.md:30` says "(v0.9)". Reported; edited only with the author's OK.

**`data-card.md`:** its §1 table (`:21-24`) lists what the study produces; it should gain a row for
run outputs and their licence posture (ties to §4).

**Existing tests:** no `Record` comparison (`Record` holds slices, so `==` will not compile, and
`reflect.DeepEqual` is never applied to it); every `Record` literal is keyed; `evallog_test.go:106`
decodes into `Record` and ignores the unexported field. So an added unexported field breaks nothing.
`TestOpenRefusesAnExistingRunFile` and `TestEmptyRunIDWritesNothing` still hold. `TestLogAfterCloseIsSafe`
should be **extended** (not edited) with a case: an answer logged after `Close` creates no file.

**The shared helper.** `harness_test.go:1023-1042` (`checkEveryRecord`) already recomputes
`sha256(answer)` on every 200 and is run by ~30 tests. Adding "and `raw/answers/{sha}.txt` holds
those bytes" there would give every one of them the check for free, **but it edits an existing test
helper, and CLAUDE.md makes tests immutable**. Default taken: **leave it untouched** and put the
new assertions in new test files. The strengthening is offered to the author in `approvals.md`.

**`cmd/gateway`.** ✔︎ `main_test.go` tests only `retiredEnv`, and the existing `Dropped()` branch
(`main.go:262-264`) has **never been run by any test**: `log.Fatalf` inside `main()` is not
testable. The new INCOMPLETE rule is extracted into a pure function on the `retiredEnv` pattern
(`main.go:51-57`) and table-tested, which also covers the old `Dropped` condition.

## 7. Concurrency and failure surface

- The only caller of `Logger.Log` is the deferred emit (`handler.go:189`). `Record` is copied by
  value across the channel; a string header shares immutable bytes, so no aliasing hazard. Each
  buffered record now pins its answer: worst case 4096 × answer size, a few MB.
- **Close:** CAS, `close(ch)`, `wg.Wait`, `f.Close`, no `Sync` (`evallog.go:154-164`). `main.go`
  calls Close while handlers may still be draining (**F-F**); a record logged after Close is skipped
  and **not counted** (`:133`); a `Log` racing `Close` panics (documented at
  `harness_test.go:769-771`). This change lengthens `wg.Wait` by the pending file writes, **but does not widen
  F-F's window**: the skipped set is fixed by the CAS at the start of `Close`, not by how long it
  takes (`review.md` 12). A skipped record also skips its file, so no hash is left dangling.
- ⚠️ **Disk-full is half silent today.** `enc.Encode` errors are only logged
  (`evallog.go:124-126`): lost lines, `Dropped()` at 0, run not INCOMPLETE. After this change an
  answer-file failure is counted but a **line** failure still is not. Closing it is ~3 lines
  (see design §3, decision D3); left open it is an asymmetry the ADR must state.
- **Read-only directory:** at start `Open` fails and `main.go:203` exits; mid-run it behaves like
  disk-full.
- **Nil logger (`make dev`):** `Log` returns at `:133`. `SetAnswer` is today's hash plus a header
  copy. No new file, directory or goroutine.
- **`-race`:** `make test` and `make verify` never use it (`Makefile:283-301`). The new
  `seen` / `missing` state is to be run under `go test -race` at least once, result recorded.

## 8. Scope and dependencies

- Nothing from `Final_Proposal.md` §12's do-not-reinstate list returns. No dependency added
  (stdlib only). Memory: the seen-set is ~100 B per distinct answer, under 1 MB. Disk: ≥ 4 KB per
  file on APFS.

## 9. Compatibility with the judge (5.1)

- `experiment-protocol.md` **does not exist** (deleted in `21aaaec`, 2026-09-22), yet
  `handler.go:574-575` still cites "experiment-protocol.md 4". That comment is fixed when
  `sha256Hex` moves.
- The deleted protocol dedupes by `sha256(query ‖ candidate_answer)`, offline, template inputs
  QUESTION + REFERENCE + SOURCE + CANDIDATE. P1 (`decisions.md:76`) records that the frozen judge
  prompt now exists nowhere. Live docs disagree on the key (`data-card.md:141-142` and
  `interfaces.md:491` say `sha256(query ‖ answer)`; `super-plan.md` 5.1 says "deduped by
  `answer_sha256`"). **5.1 must pick one**; both are computable from `query_raw` plus
  `raw/answers/`, so the layout is compatible with either. The bare `‖` with no delimiter is
  ambiguous, and that is 5.1's.
- **SOURCE** (retrieved chunk text) is recoverable from the frozen corpus only when
  `mutation: off`. When `mutation: on`, the text at serve time depends on
  `dataset_epoch_at_retrieval` plus the ordered update set. The spec's "not in this task" note must
  carry that.

## 10. Corrections to `spec.md` (applied in revision 2)

1. State the invariant **on the record, not on delivery**: a MISS whose client left still carries a
   hash and a file (`abandon_test.go:192-207`). The rule is *every non-empty `answer_sha256` names a
   file, and no file is unnamed*. "The answer the client received" means the JSON-decoded `answer`;
   invalid UTF-8 becomes U+FFFD in `writeJSON`, so acceptance 7 excludes it.
2. Acceptance 5: not "durable". Nothing is fsynced, and on macOS `fsync` is not durable without
   `F_FULLFSYNC`. The guarantee is **visible before the line**.
3. Acceptance 6 was asymmetric (a failed line is uncounted). Decision D3.
4. Acceptance 9: "never rewritten with different bytes" is a SHA-256 collision and cannot be
   tested. Assert **never rewritten**; `os.Rename` overwrites, so the design uses `os.Link`.
5. Acceptance 10: ✔︎ `make check` **cannot fail** (`Makefile:404-413`: every grep ends in
   `|| echo clean`, and a match also exits 0). Replaced by explicit greps.
6. Acceptance 11: ✔︎ **"proto drift 0" checks nothing.** Both stub directories are gitignored
   (`.gitignore:40-41`, and `git ls-files` lists none), so `git diff --exit-code` on them is always
   clean. Replaced by `git diff --exit-code contracts/`, with the limit stated.
7. Omitted: the architecture tree entry, the stale version strings, the `data-card.md` row, the
   publication posture (§4), and `main`'s untested INCOMPLETE path.
8. Pin in the contract: `""` (not null) means no answer was served; an empty answer text is a real
   answer.

## 11. Risks passed to design review

1. **Publication** (§4). 2. **`Open` ordering** (`Mkdir` before the `O_EXCL` create can leave a
directory inside a finished write-once run; do the `O_EXCL` create first). 3. **`os.CreateTemp` is
mode 0600** and `requests.jsonl` is 0644: chmod before publishing; the temp name must not end in
`.txt`. 4. **Guard placement:** after the `seen` check, not before. 5. **Silent-loss paths that
remain:** encode errors, F-F late records, the Log/Close panic window. 6. **Writer throughput:**
burst test. 7. **Test hygiene:** the shared helper, `-race`, `main`'s INCOMPLETE logic.
