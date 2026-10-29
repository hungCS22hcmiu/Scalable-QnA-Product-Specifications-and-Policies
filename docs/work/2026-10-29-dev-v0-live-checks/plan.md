# Plan — The live seam and support checks still pin the retired dev-v0 corpus

Design: design.md (approved 2026-10-29)

Paths used below (from the repo root):
- `T` = `docs/work/2026-10-29-dev-v0-live-checks`
- `E` = `T/evidence/rca` (the RCA's files; read them, never edit them)
- `W` = `T/evidence/witness`, `F` = `T/evidence/fix`, `O` = `T/evidence/preflight` (all new)
- `SEAM` = `gateway/internal/ragclient/seam_live_test.go`
- `SUP` = `gateway/internal/ragclient/support_live_test.go`

Rules for every step:
- The shell is zsh, so there is no `PIPESTATUS`: take a target's exit with `…; echo "exit $?"`.
- `SEAM_LOG` must be an absolute path: use `SEAM_LOG="$PWD/…"`.
- `make seam-check` and `make support-check` share port 50052, so run them one at a time.
- Before every live step, run `sysctl -n kern.memorystatus_vm_pressure_level` and write it in the
  `Result:` line. Yellow is allowed; stop at red (4). Live steps load the embedding model only and are
  `citable: no`.
- Redis stays as it is: never ingest, `FLUSHALL`, `FLUSHDB` or `make demo-reset`. Restart Ollama only
  with `make ollama-env`.
- Edit only `SEAM`, `SUP`, `docs/super-plan.md` and files under `T/evidence/`. Never touch
  `gateway/internal/reuse/` or `support_sample_live_test.go`.

## Phase 1 — The failing tests first

- [x] 1.1 Save the untouched test files, then witness DC 1 on them.
  - Run:
    1. `mkdir -p T/evidence/witness T/evidence/fix T/evidence/preflight`
    2. `git show HEAD:gateway/internal/ragclient/seam_live_test.go > W/seam_live_test.head.go`
    3. `git show HEAD:gateway/internal/ragclient/support_live_test.go > W/support_live_test.head.go`
    4. `make seam-check SEAM_LOG="$PWD/W/seam-check.log" > W/seam-check.make.out 2>&1; echo "exit $?"`
    5. `make support-check SEAM_LOG="$PWD/W/support-check.log" > W/support-check.make.out 2>&1; echo "exit $?"`
  - Pass:
    - Both exits are non-zero.
    - `W/seam-check.log` has `--- FAIL: TestSeam/L2` and `want equal and >= 1`.
    - `W/support-check.log` has `--- FAIL: TestSupportLive/fidelity` and 7 × `oracle: no text`.
      It also has `--- PASS: TestSupportLive/paraphrase-query` and `--- PASS: TestSupportLive/warranty-query`:
      that is the empty pass, recorded.
  - Result: pressure 1 (green) before both; seam-check exit 2, L2 FAIL "len(texts) = 0, len(chunk_ids) = 0: want equal and >= 1" (L1, L3, shift PASS); support-check exit 2, fidelity FAIL with 7 x "oracle: no text", paraphrase-query and warranty-query PASS (the empty pass); logs in evidence/witness/.
- [x] 1.2 Add check (i) to `SUP`, and nothing else (design §3, "Check (i)"). Put it in the query
  subtest's body, right after the `checkAligned` block, so it runs for both queries. Then save a copy
  of the file as it is now.
  - Files: `SUP`
  - Run:
    1. `make lint`
    2. `cp gateway/internal/ragclient/support_live_test.go W/support_live_test.phase1.go`
    3. `make support-check SEAM_LOG="$PWD/W/support-check-i.log" > W/support-check-i.make.out 2>&1; echo "exit $?"`
  - Pass:
    - lint is clean, and the exit is non-zero;
    - `W/support-check-i.log` has `--- FAIL: TestSupportLive/paraphrase-query` and
      `--- FAIL: TestSupportLive/warranty-query`, each with `no product-headphones-03 chunk in the
      scoped retrieval`. That is DC 2, and the reason in §1.
  - Result: pressure 1 (green); added check (i) plus the `strings` import (+7 lines in SUP), lint clean; support-check exit 2, paraphrase-query and warranty-query both FAIL "no product-headphones-03 chunk in the scoped retrieval [policy-return-electronics#chunk-0]" / "[policy-warranty-electronics#chunk-0]"; phase1 copy saved in evidence/witness/.

## Phase 2 — The fix

- [x] 2.1 Re-pin `SEAM`. Change `spliceDoc` and `spliceChunk`, and the comment at `:39-41`. Add the
  preflight after `oracle` and before `t.Run("L1", …)`, with the message from design §3. Nothing else
  changes.
  - Files: `SEAM`
  - Run: `make lint`, then `git diff --stat -- gateway/internal/ragclient/seam_live_test.go`
  - Pass: lint is clean, and the diff touches only that file.
  - Result: SEAM re-pinned to product-laptops-b07k238ls2 (+ comment at :39-43, HGet preflight via `oracle(spliceChunk)` before `retrieve`); lint clean, gofmt clean, diff is 14+/5- in that file only.
- [x] 2.2 Re-pin `SUP`. Use design §3's constants, exactly as they are in
  `E/support_live_test.v1-proposal.go`. Add the preflight after `oracle` and before
  `t.Run("fidelity", …)`. Change the self-check's message. Rewrite the header (`:3-37`) and the
  comments at `:66-70` and `:76-77` for `v1`, covering each point design §3 lists. Keep check (i) from
  1.2.
  - Files: `SUP`
  - Run: `make lint`, then
    `diff <(grep -E '^(const|var|\t"|\tsupport)' E/support_live_test.v1-proposal.go) <(grep -E '^(const|var|\t"|\tsupport)' gateway/internal/ragclient/support_live_test.go)`
  - Pass: lint is clean. The diff is empty, apart from added import lines (check (i) may need
    `"strings"`). The pattern selects only constant, map and import lines, so comment changes do not
    show.
  - Result: SUP re-pinned (product, 2 queries, answer + SHA 197de3fd39ab, 4 hashes, 22 tokens), preflight added before `fidelity`, self-check message and header/comments rewritten for v1, check (i) kept; lint and gofmt clean, constants diff against the RCA proposal shows only the added `"strings"` import.

## Phase 3 — Live checks on v1

- [x] 3.1 DC 3.
  - Run: `make seam-check SEAM_LOG="$PWD/F/seam-check.log" > F/seam-check.make.out 2>&1; echo "exit $?"`
  - Pass: exit 0. L1, L2, L3 and shift each PASS. The log line `L2: splice fired, … [product-laptops-b07k238ls2#chunk-0 …]`
    has that chunk first.
  - Result: pressure 1 (green), citable: no; exit 0; L1, L2, L3, shift PASS; log "L2: splice fired, 1 chunks [product-laptops-b07k238ls2#chunk-0]" (the chunk is the only one, at index 0); evidence/fix/seam-check.log.
- [x] 3.2 DC 4.
  - Run: `make support-check SEAM_LOG="$PWD/F/support-check.log" > F/support-check.make.out 2>&1; echo "exit $?"`
  - Pass: exit 0, and `fidelity`, `paraphrase-query` and `warranty-query` each PASS. Both
    `live chunk IDs` lines contain `product-electronics-b07wnp64zn#chunk-0`, and both `S_lex =` lines
    are present. Copy the two S_lex values into `Result:`.
  - Result: pressure 1 (green), citable: no; exit 0; fidelity, paraphrase-query, warranty-query PASS; both live chunk IDs lines hold product-electronics-b07wnp64zn#chunk-0; S_lex paraphrase = 0.9545 (ADMITS), warranty = 0.4091 (REFUSES), 22 content tokens, logged not asserted; evidence/fix/support-check.log.
- [x] 3.3 DC 5. Make the two pin-absent copies and their overlays (design §3, `evidence/preflight/`),
  then run each target through its overlay.
  - Run:
    1. `sed 's/product-laptops-b07k238ls2/product-absent-00/g' gateway/internal/ragclient/seam_live_test.go > O/seam_live_test.absent.go`
    2. `sed 's/product-electronics-b07wnp64zn/product-absent-00/g' gateway/internal/ragclient/support_live_test.go > O/support_live_test.absent.go`
    3. Write `O/overlay-seam.json` as `{"Replace": {"<abs path of SEAM>": "<abs path of O/seam_live_test.absent.go>"}}`,
       and `O/overlay-support.json` the same way for `SUP`. Follow the shape of `E/overlay-v1-proposal.json`.
    4. `GOFLAGS="-overlay=$PWD/O/overlay-seam.json" make seam-check SEAM_LOG="$PWD/O/seam-check.log" > O/seam-check.make.out 2>&1; echo "exit $?"`
    5. `GOFLAGS="-overlay=$PWD/O/overlay-support.json" make support-check SEAM_LOG="$PWD/O/support-check.log" > O/support-check.make.out 2>&1; echo "exit $?"`
  - Pass: both exits are non-zero. `O/seam-check.log` and `O/support-check.log` each contain
    `pin absent` and `product-absent-00`, and neither contains `--- PASS: TestSeam/L1` or
    `--- PASS: TestSupportLive/fidelity`: the preflight stopped each test before its subtests.
  - Result: pressure 1 (green), citable: no; both exits 2; seam log "pin absent: oracle: no text at corpus::product-absent-00#chunk-0 -- ... was the corpus switched?" and no L1 PASS; support log the same message and no fidelity PASS; copies, overlays and logs in evidence/preflight/.

## Phase 4 — Records

- [x] 4.1 Update `docs/super-plan.md`'s Issue-2 finding (the bullet that begins "**`make demo-reset`
  runs `FLUSHALL`", now `:456`). Its last sentence, "Moving `seam-check`, `support-check` and `demo` to
  `v1` is still open.", becomes: "`seam-check` and `support-check` run on `v1` since 2026-10-29 (trail
  `docs/work/2026-10-29-dev-v0-live-checks/`); moving `make demo` to `v1` is still open (Phase 8)."
  Then add the new bullet right after it, with design §3's four points on the unknown `product_id`.
  - Files: `docs/super-plan.md`
  - Run: `grep -n 'dev-v0-live-checks\|unknown .product_id' docs/super-plan.md`
  - Pass: both show.
  - Result: `docs/super-plan.md` :456 last sentence replaced as the step says, new :457 bullet on the unknown `product_id` added; grep shows both. Note: :456 still says "`make demo` and `make seam-check` still assume `dev-v0`" earlier in the same bullet (left as the step wrote it; see report).

## Phase 5 — Run and verify (each step is the done condition with the same number)

- [x] 5.1 DC 1. Re-run the untouched tests through an overlay of the HEAD copies from 1.1.
  - Run: write `W/overlay-head.json`, which maps `SEAM` → `W/seam_live_test.head.go` and `SUP` →
    `W/support_live_test.head.go`. Then:
    1. `GOFLAGS="-overlay=$PWD/W/overlay-head.json" make seam-check SEAM_LOG="$PWD/W/dc1-seam.log" > /dev/null 2>&1; echo "exit $?"`
    2. `GOFLAGS="-overlay=$PWD/W/overlay-head.json" make support-check SEAM_LOG="$PWD/W/dc1-support.log" > /dev/null 2>&1; echo "exit $?"`
  - Pass: as in step 1.1, now in `W/dc1-*.log`.
  - Result: pressure 1 (green) before both, citable: no; seam exit 2 with L2 FAIL "len(texts) = 0 ... want equal and >= 1" (L1, L3, shift PASS); support exit 2 with fidelity FAIL, 7 x "oracle: no text", both query subtests PASS (empty pass); evidence/witness/dc1-seam.log, dc1-support.log.
- [x] 5.2 DC 2. Re-run check (i) alone, through an overlay of `W/support_live_test.phase1.go`.
  - Run: write `W/overlay-phase1.json`, which maps `SUP` → `W/support_live_test.phase1.go`. Then
    `GOFLAGS="-overlay=$PWD/W/overlay-phase1.json" make support-check SEAM_LOG="$PWD/W/dc2-support.log" > /dev/null 2>&1; echo "exit $?"`
  - Pass: as in step 1.2, now in `W/dc2-support.log`.
  - Result: pressure 1 (green), citable: no; exit 2; paraphrase-query and warranty-query both FAIL "no product-headphones-03 chunk in the scoped retrieval [policy-...#chunk-0]" (fidelity also FAIL on the dev-v0 pins, as in 1.2); evidence/witness/dc2-support.log.
- [x] 5.3 DC 3: `make seam-check SEAM_LOG="$PWD/F/dc3-seam.log"`.
  - Pass: as in step 3.1.
  - Result: pressure 1 (green), citable: no; exit 0; L1, L2, L3, shift PASS; "L2: splice fired, 1 chunks [product-laptops-b07k238ls2#chunk-0]"; evidence/fix/dc3-seam.log.
- [x] 5.4 DC 4: `make support-check SEAM_LOG="$PWD/F/dc4-support.log"`.
  - Pass: as in step 3.2.
  - Result: pressure 1 (green), citable: no; exit 0; fidelity, paraphrase-query, warranty-query PASS; both live chunk IDs lines hold product-electronics-b07wnp64zn#chunk-0; S_lex 0.9545 (ADMITS) and 0.4091 (REFUSES), logged not asserted; evidence/fix/dc4-support.log.
- [x] 5.5 DC 5: commands 4 and 5 of step 3.3 again, with logs `O/dc5-seam.log` and `O/dc5-support.log`.
  - Pass: as in step 3.3.
  - Result: pressure 1 (green) before both, citable: no; both exits 2; dc5-seam.log and dc5-support.log each hold "pin absent: oracle: no text at corpus::product-absent-00#chunk-0 ... was the corpus switched?" and no L1 / fidelity PASS; evidence/preflight/.
- [x] 5.6 DC 6.
  - Run:
    1. `git diff --name-only -- gateway/`
    2. `git diff --quiet gateway/internal/reuse/; echo $?`
    3. `git diff --quiet gateway/internal/ragclient/support_sample_live_test.go; echo $?`
  - Pass: command 1 lists exactly the two test files; commands 2 and 3 each print `0`.
  - Result: `git diff --name-only -- gateway/` lists seam_live_test.go and support_live_test.go only; reuse/ diff prints 0; support_sample_live_test.go diff prints 0.
- [x] 5.7 DC 7: the `grep` of step 4.1.
  - Pass: as in step 4.1.
  - Result: grep shows `docs/super-plan.md` :456 (trail link in the Issue-2 finding) and :457 (the unknown `product_id` bullet).
- [x] 5.8 DC 8: `make verify`.
  - Pass: no FAIL. Any SKIPPED target is listed by name.
  - Result: exit 0; lint clean, build ok, all Go packages ok, pytest rag 62 passed, experiments/tests 778 passed; no FAIL and no SKIPPED target; Redis still 539 keys with idx:corpus and idx:cache; log in evidence/fix/verify.out.

## Phase 6 — Review fixes (main session, 2026-10-29)

These are text-only fixes from the executor's report. The main session made them, and its re-check
(every DC and `make verify`) ran after them.

- [x] 6.1 Correct the citation in the `SEAM` comment at `:39-41`. It cited `E/probe.out`, which shows only
  the splice firing; the comment now cites the read-only `HGET` check.
  - Files: `SEAM`
  - Result: the main session confirmed on `v1`: one chunk, 475 bytes, no power, watt or volt term. Comment only.
- [x] 6.2 Remove the stale "`make seam-check` still assumes `dev-v0`" from `docs/super-plan.md` `:456`.
  - Files: `docs/super-plan.md`
  - Result: the sentence now reads "`make demo` still assumes `dev-v0`."
- [x] 6.3 Correct the same citation in design §3.
  - Files: `T/design.md`
  - Result: done.

## Phase 7 — Evidence Go copies renamed `.go.txt` (the author, 2026-10-29, at review)

The `.go` copies under `T/evidence/` belong to no Go module: `go.mod` is in `gateway/`, and they have
none. They are only ever read through `GOFLAGS=-overlay`, which takes a replacement file's content
under any name. Left as `.go`, they showed as broken Go code in the editor. **A `*.go` name in a
ticked step above now means the same file with `.txt` added.**

- [x] 7.1 Rename the 10 `.go` files under `T/evidence/` to `*.go.txt`, and update the `Replace`
  values of the 8 overlay JSON files. The keys, which are the real files in `gateway/`, stay `.go`.
  - Files: `T/evidence/{rca,witness,preflight,recheck}/`, design §3 (one reference).
  - Result: `find docs -name '*.go'` now lists only
    `docs/work/2026-10-29-redis-index-lifecycle/evidence/rca/goprobe/main.go`. That one is left as it
    is: it has its own `go.mod` and `go.sum`, so it is a module that builds in place.
- [x] 7.2 Show that the overlays still work under the new names (main session, pressure 1, `citable: no`).
  - Result:
    - DC 1 head overlay: seam exits 2 with L2 FAIL;
    - DC 2 phase-1 overlay: support exits 2 with 2 "no product-headphones-03 chunk";
    - DC 5 absent overlays: seam and support each exit 2 with "pin absent";
    - plain `make seam-check` and `make support-check`: each exits 0.
