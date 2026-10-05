# Plan — carry-chunk-text

The smallest change that satisfies `spec.md`, ordered so that each step can be verified on its own.
It follows `design.md` revision 3, after `impact.md` and `review.md`.

## 0. Before any edit

- [x] **Commit item 1.2's work** (spec acceptance 0). Asked by the author on 2026-10-05
      ("commit 1.2 trước đi"). `8d637f7`, fast-forwarded into `main` and pushed.
      `/verify` before the commit, 2026-10-05: gofmt **PASS** · go vet **PASS** · go build **PASS**
      · go test **PASS** (re-run with `-count=1`: the first pass was cached) · ruff **PASS** ·
      pytest `rag/` **PASS** (10) · pytest `experiments/` **PASS** (94) · proto drift **PASS**
      (`make proto`, then no diff on either stub). Nothing skipped.
- [x] D1: **D1-a**, approved by `review.md` on condition S3 (applied in step 3 and step 7).
- [x] `/approve impact` · `/approve implementation` (both 2026-10-05). Contract and experiment are not required
      (`impact.md` §5, §6); `approvals.md` records why.

## 1. Unknowns

U1, U3 and U6 are settled by `review.md`. U4 is moot. U5 goes to 3.1. **U2 and U7 stay open**, and
step 5 settles them live.

## 2. Tests first

- [x] `rag/tests/test_retrieve_texts.py` (`design.md` §3a): the servicer-alignment test and the
      `_to_chunks` raw-text test. **Done when** the servicer test fails only because `texts` is
      empty, and the `_to_chunks` test **passes** (it pins current behaviour).
- [x] `gateway/internal/ragclient/retrieve_texts_test.go` (§3b, six rows, a non-sorted
      non-palindromic aligned fixture). **Done when** it fails to compile only because
      `RetrieveResult.Texts` and `ErrTextsMisaligned` do not exist yet.
- [x] `gateway/internal/ragclient/seam_live_test.go`, `package ragclient_test` (§3c): `TestSeam` with
      subtests `L1`, `L2`, `L3`, `shift`; 90 s deadline; `REDIS_URL`; `HGet(...).Result()`.
      **Done when** `go vet ./internal/ragclient/` is clean and, with `RAG_SEAM_ADDR` unset, it
      reports SKIP under `-v`.
- [x] `git diff --exit-code` on `ragclient/retrieve_test.go` and `ragclient/answer_test.go`, and
      `test -z "$(git status --porcelain -- gateway/internal/httpapi/)"`.

## 3. The two edits

- [x] `rag/src/rag/server.py`: `texts=[c.text for c in chunks]` (Edit 1). Nothing else in the file.
- [x] `gateway/internal/ragclient/retrieve.go`: `Texts`, `ErrTextsMisaligned`, the three-way length
      rule (Edit 2). **The `Texts` doc comment carries the 2.1 obligation word for word from
      `design.md` §2** (`review.md` S3): nil with non-empty `ChunkIDs` is not scored, not SUPPORT,
      not gate-off.
- [x] **Done when** step 2's unit tests pass, `make lint` is clean, and `make test` is green.

## 4. `make seam-check`

- [x] Target per `design.md` §3d, steps 1–8: pressure line, `redis-cli PING`, informational
      `:50051` PID count, a private `SEAM_PORT` (default 50052) that must be free, `rag.server`
      started from the tree under a `trap`, wait for the listener (30 s), `go test -count=1 -v -run
      '^TestSeam$'` teed to `SEAM_LOG` under `pipefail`, then the output check. Add it to `.PHONY`
      with a `##` help line.
- [x] **Done when** the target fails, rather than passing, with Redis stopped, and with
      `SEAM_PORT` already taken.

## 5. Live evidence (acceptance 3, 4, 6; U2, U7)

Not a measurement, so yellow pressure is allowed (author's rule). The target prints the level, which
the evidence keeps. It loads the embedding model, not the LLM.

- [x] `make seam-check SEAM_LOG=docs/work/2026-10-05-carry-chunk-text/evidence/seam-check.txt`
      passes: L1 stable across two calls (U7), L1–L3 aligned against the Redis oracle, the splice
      shown to fire on L2 (U2), and the rotated L1 rejected.
- [x] If L2's splice does not fire, pick another product/query pair and record why. Do not drop the
      assertion.

## 6. Mutations (`design.md` §4)

- [x] Apply M1–M9 one at a time, run the named test (`make seam-check` for every 3c row; it restarts
      its own server, so each edit is seen), confirm it fails, and revert. Record M3-eq as an
      equivalent mutant.
- [x] T1–T4 against the target.
- [x] Record everything in `evidence/mutations.txt`. A mutation no test catches is a design gap:
      stop and report it. Do not patch around it.
- [x] `git diff` afterwards shows only the intended edits.

**Outcome, 2026-10-05.**
- Step 2: the servicer test failed only on `texts` (0 ≠ 4); the `_to_chunks` test passed; both Go
  files failed to compile only on `Texts` / `ErrTextsMisaligned`.
- Step 3: all green; immutable files and `httpapi/` clean; `go list -deps ./internal/ragclient |
  grep -c redis` = 0.
- Step 4: the target fails with Redis unreachable (`SEAM_REDIS_URL=redis://localhost:1/0`, rather
  than stopping the shared Redis) and with port 50052 taken. No `rag.server` left running.
- Step 5: **pressure level 2 (urgent)**; the author chose to run anyway (`approvals.md`). PASS:
  L1 5 chunks, stable across two calls (U7 settled); L2 splice fired, one chunk (U2 settled); L3 5
  chunks; shift rejected. `evidence/seam-check.txt`. The full `make` output is saved there, not
  only the `go test` log, so the pressure line is in the evidence.
- Step 6: `evidence/mutate.py` → `evidence/mutations.txt`. **The first run found two gaps** and
  stopped (`design.md` §4, "First run"): M9a/M9b missed by 3b because of slice aliasing, and M5
  caught only by the compiler. Both fixed with the author's go-ahead; **second run: 0 gaps**, files
  restored byte for byte.

## 7. Close

- [x] `make verify` green (2026-10-05; Go also re-run with `-count=1`).
- [x] `/ai-review`, with the `contract-reviewer` because the seam is touched: **no findings**, conforms to §B (`review.md`, "Implementation review").
- [x] State in the `/done` summary that `make verify` does not run the live path. Of F4c, only part
      (c) is left to `make seam-check`, which is re-run by hand after any retrieval or LlamaIndex
      change (`design.md` §3d).
- [x] At `/done`:
  - `super-plan.md`: 1.4's row ✅, the Phase 1 progress line, and **2.1's row gains the nil-texts
    obligation sentence**, not only the ✅ on its blocker (`review.md` S3).
  - `architecture.md` §4 target list gains `seam-check` (`impact.md` correction 8).
  - 3.1 gains the UTF-8 note (`design.md` §6).

## Outcome — closed 2026-10-05

**Shipped.**
- `rag/src/rag/server.py`: `Retrieve` sends `texts=[c.text for c in chunks]`, from the same list as
  `chunk_ids`.
- `gateway/internal/ragclient/retrieve.go`: `RetrieveResult.Texts`, nil when absent;
  `ErrTextsMisaligned` on a partial array; the 2.1 obligation in the `Texts` doc comment.
- Tests: `rag/tests/test_retrieve_texts.py` (servicer alignment, `_to_chunks` raw text, empty);
  `ragclient/retrieve_texts_test.go` (six wire shapes); `ragclient/seam_live_test.go` (live, Redis
  oracle, L1–L3 and `shift`).
- `make seam-check`: owns its server on `:50052`, fails unless every subtest ran and passed.
- Evidence: `evidence/seam-check.txt` (PASS), `evidence/mutate.py` → `evidence/mutations.txt`
  (0 gaps on run 2).

**Checks at close.** `make verify` green, nothing skipped (gofmt, vet, build, `go test` also with
`-count=1`, ruff, pytest 13 + 94); proto drift none. `/ai-review` (`contract-reviewer`): no
findings. The live check last ran on this exact code in mutation run 2 (T1, twice, PASS); it was
not re-run at close because pressure stayed at level 2 and the author's level-2 approval was for one
run. **`make verify` does not run the live path.** Of F4c only part (c), `text` dropping out of
`return_fields`, is left to `make seam-check`, re-run by hand after any retrieval or LlamaIndex
change.

**Scope was honest.** Opened as M, raised to L before any work: it touched the gRPC seam and the
measured path. It touched no frozen value and no contract, and needed neither phase.

**Deferred, and where it went.**
- 2.1's obligation on nil `Texts` → `super-plan.md` 2.1 row, and the `Texts` doc comment.
- `make dev` may orphan `rag.server`; `rag-server-reuseport` should close before 2.1's live
  reproduction and Phase 7 → `super-plan.md`, "Found while closing 1.4".
- UTF-8 for the PQA builder → the same list, addressed to 3.1.
- `architecture.md` §4 and `CLAUDE.md` "Commands that work today" gained `seam-check`.

**Follow-up worth a task:** `rag-server-reuseport` together with the `make dev` orphan, as one
`/bugfix`. It is the only thing between this task's evidence and a gateway that can silently talk to
a stale server.
