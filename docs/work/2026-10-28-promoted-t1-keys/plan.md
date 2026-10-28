# Plan — Track every Tier-1 key of an entry

Design: design.md (approved 2026-10-28)

**Before any step:** `redis-cli PING` answers `PONG`. The `cache` tests use Redis DB 15 (`testStore`), and the
`deps` tests use DB 14. Both call `FLUSHDB`, which on this server drops every search index (4.1 design §4).
So **run one command at a time**, and when one command tests both packages, pass `-p 1` so they run one
after the other.

Never edit an existing `_test.go` file. `go test -run` exits 0 when nothing matches, so every test step runs
with `-v`, and its Pass line names the tests that must print `--- PASS`. A `--- SKIP` is a failed step. No
step loads a model, so no memory check is needed and no number here is citable.

## Phase 1 — Implement

- [x] 1.1 The shared removal script, and the trim.
  - Files: `gateway/internal/cache/capacity.go`
  - Do: exactly design §3 "Files", `cache/capacity.go`:
    - `t1KeysPrefix` and `t1KeysKey`, with the comment about the `lru:` region.
    - `dropEntryScript`, as the Lua in §3.
    - `(s *Store) dropEntry(ctx, entryID, extraT1Key string) (string, []string, error)`.
    - `TrimToCapacity` calls `dropEntry(ctx, id, "")` per victim, in place of its `HGET` and `TxPipeline`.
    - `EvictedEntry` gains `T1Keys []string`, and keeps `T1Key` as the `t2:` record's `t1_key`.
    - Update the `TrimToCapacity` doc comment: both tiers of a victim still die together, and that now
      includes every Tier-1 key in the set.
  - Run: `cd gateway && go build ./... && go test -count=1 -v ./internal/cache/ 2>&1 | grep -E "^(--- |ok|FAIL)"`
  - Pass: builds; every existing cache test `--- PASS`; no `--- SKIP`; `ok`.
  - Result: added t1KeysPrefix, t1KeysKey, dropEntryScript, dropEntry and EvictedEntry.T1Keys to cache/capacity.go; trim runs the script per victim; 19 cache tests PASS, no SKIP.

- [x] 1.2 The purge uses the same script.
  - Files: `gateway/internal/cache/purge.go`
  - Do: `PurgeEntry` keeps its signature and its empty-`entryID` early return, then calls
    `dropEntry(ctx, entryID, t1Key)` and wraps any error as it does now. Delete `purgeScript`, and the Go
    `HGET` of `t1_key`: the script does both now. Rewrite the doc comments to say this and to point to
    `dropEntryScript`.
  - Run: `cd gateway && go build ./... && go test -count=1 -p 1 -v ./internal/cache/ ./internal/deps/ 2>&1 | grep -E "^(--- |ok|FAIL)"`
  - Pass: every existing test in both packages `--- PASS`, including 4.1's three `TestPurgeEntry*`; no
    `--- SKIP`; two `ok`.
  - Result: cache/purge.go now calls dropEntry and drops purgeScript and its Go HGET; 19 cache and 17 deps tests PASS, no SKIP, two ok.

- [x] 1.3 Every Tier-1 write is recorded, and the promotion is conditional.
  - Files: `gateway/internal/cache/store.go`
  - Do: as design §3, `cache/store.go`.
    - `Entry.Promotion bool`, with its comment.
    - `Put`, not a promotion: the existing `HSET` and `SADD t1KeysKey(e.EntryID) key` in one `TxPipeline`.
    - `Put`, a promotion: an error if `EntryID` is empty; otherwise `promoteScript`, with `KEYS = {t2:E,
      key, lru:t1keys:E}` and the five hash fields in `ARGV`. A script result of 0 returns nil.
    - Comment why the check and the write are one script (the race in design §3).
  - Run: `cd gateway && go build ./... && go vet ./internal/cache/ && go test -count=1 -v ./internal/cache/ 2>&1 | grep -E "^(--- |ok|FAIL)"`
  - Pass: builds; vet clean; every existing cache test `--- PASS`.
  - Result: Put now does HSET+SADD in one TxPipeline, and a Promotion write runs promoteScript (store.go); Entry.Promotion added in entry.go (where Entry is declared); build and vet clean, 19 cache tests PASS.

- [x] 1.4 The handler asks for the conditional promotion.
  - Files: `gateway/internal/httpapi/handler.go`
  - Do: in the promotion goroutine's `cache.Entry`, add `Promotion: true`. Replace the "⚠️ Known limitation"
    paragraph with two lines: every Tier-1 key is recorded in `lru:t1keys:{entry_id}`, and the promotion is
    written only while `t2:` exists (interfaces.md §D v0.19). Do not change the miss write-back's `Put` or
    the `cacheStore` interface.
  - Run: `cd gateway && go build ./... && go test -count=1 ./internal/httpapi/`
  - Pass: builds; `ok` (every existing promotion test still passes through the fake `Put`).
  - Result: handler.go's promotion Put sets Promotion: true and the Known-limitation paragraph became two lines; build ok, httpapi tests ok.

- [x] 1.5 The 4.2 race check cleans the set too.
  - Files: `experiments/scripts/epoch_race_check.py`
  - Do: in `cleanup`, also `r.delete(f"lru:t1keys:{eid}")`, and append it to `done` when it deleted
    something. Add a one-line comment pointing to `interfaces.md` §D v0.19. Do not run the script.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && python3 -m py_compile experiments/scripts/epoch_race_check.py && ruff check experiments/scripts/epoch_race_check.py && grep -n "lru:t1keys:" experiments/scripts/epoch_race_check.py`
  - Pass: compiles; ruff clean; the grep prints the line.
  - Result: the script has no `cleanup` function; the per-entry delete is `purge_entry`, so lru:t1keys:{eid} went into its key loop there; compiles, ruff clean, grep prints lines 228-229.

- [x] 1.6 Contract to v0.19.
  - Files: `docs/contracts/interfaces.md`
  - Do:
    - Line 3: `Draft v0.18` → `Draft v0.19`.
    - §D, after the Tier-1 block: the `lru:t1keys:{entry_id}` SET. Cover:
      - every Tier-1 key ever written for the entry; written in the same atomic step as the Tier-1 hash
        (the miss write-back and the promotion);
      - the promotion is written only while `t2:{entry_id}` exists, in one script;
      - why it is in the `lru:` region, not `entry:`.
    - §D's capacity / eviction text: a victim's Tier-1 keys come from the set, the `t2:` record's `t1_key`,
      and nothing else. Each is deleted only if its `entry_id` still names the victim; then `t2:`, the set and
      the `lru:entries` member go. `dep:*` and `entry:*` are still never touched.
    - §E: in "Why `entry:{entry_id}` exists", replace "Item 4.3 will add promoted Tier-1 keys to it" with
      "promoted Tier-1 keys are tracked in §D's `lru:t1keys:{entry_id}` instead (v0.19), because eviction must
      find them and `cache/` never reads `entry:*`". Purge step 3: the candidates are the set, the `t2:`
      `t1_key` and `entry:`'s `t1_key`; the rest is unchanged.
    - Versioning: `Current version` → v0.19 (2026-10-28), and a new top row. It says: item 4.3; §D gains the
      set and its rules; §E's step 3 and its `entry:` plan; no wire, §A, §B, §H or `.proto` change. Under
      bounded capacity an evicted entry can no longer be served through a promoted or orphaned Tier-1 key.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && grep -n "v0.19\|lru:t1keys:" docs/contracts/interfaces.md | cut -c1-110; grep -n "Item 4.3 will add" docs/contracts/interfaces.md`
  - Pass: the header, §D set, §E text and version lines appear; the last grep prints nothing.
  - Result: interfaces.md is v0.19: header, §D set and eviction text, §E "why entry:" sentence and purge step 3, version row; greps show all of them and "Item 4.3 will add" is gone.

- [x] 1.7 Architecture and the Redis notes.
  - Files: `docs/architecture.md`, `docs/Redis-Data Structure.md`
  - Do:
    - `architecture.md`: the bullet "A promoted Tier-1 key is not tracked" goes. If that leaves the list
      header's count wrong ("Two parts…"), fix the count. Invariant 3 says every Tier-1 key, promoted ones
      included, is recorded in `lru:t1keys:{entry_id}` (item 4.3).
    - `Redis-Data Structure.md`:
      - §1's map gains the set under the cache region;
      - §5.5's "Promotion" says it is tracked and conditional;
      - §6 (`lru:entries`) describes the set beside it and what the trim deletes;
      - §8's purge steps match the script;
      - §9 gap 5 says "Resolved in v0.19 (item 4.3)", in the style of gap 4.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && grep -n "not tracked\|not \*\*covered\|Promoted Tier-1 keys are orphans" docs/architecture.md "docs/Redis-Data Structure.md"; grep -c "lru:t1keys:" "docs/Redis-Data Structure.md"`
  - Pass: the first grep prints nothing; the count is at least 3.
  - Result: architecture.md bullet gone, count fixed to "One part", invariant 3 rewritten; Redis notes edited in §1, §5.5, §6, §8, §9 gap 5, plus the §4.2 and §7 lines that the trim and write-back changes made stale; first grep empty, `lru:t1keys:` count 13.

## Phase 2 — Unit tests

- [x] 2.1 `cache`: the write records the key, and the promotion is conditional (DC 1, 2).
  - Files: `gateway/internal/cache/t1keys_test.go` (new, `package cache`)
  - Do: use `testStore`. Keys come from `Key(Normalize(q), pid)`. A "live" `t2:E` is a direct `HSET`, as
    `seed` does. Tests:
    - `TestPutRecordsTier1Key`: `Put(q1, E)`, `HSET t2:E`, then a `Promotion` `Put(q2, E)`. `SMEMBERS
      lru:t1keys:E` is exactly the two keys, and both `t1:` hashes name `E`.
    - `TestPromotionNeedsTier2`: with no `t2:E`, a `Promotion` `Put` returns nil and writes neither the key
      nor the set. After `HSET t2:E`, the same call writes both.
    - `TestPromotionWithoutEntryIDFails`: an error, and nothing is written.
  - Run: `cd gateway && go test -count=1 -v -run 'TestPutRecords|TestPromotion' ./internal/cache/`
  - Pass: three `--- PASS`; no `--- SKIP`.
  - Result: added cache/t1keys_test.go (TestPutRecordsTier1Key, TestPromotionNeedsTier2, TestPromotionWithoutEntryIDFails); three PASS, no SKIP.

- [x] 2.2 `cache`: the trim drops every Tier-1 key (DC 3, 4).
  - Files: `gateway/internal/cache/t1keys_trim_test.go` (new)
  - Do:
    - `TestTrimDropsEveryTier1Key`: `E` (`HSET t2:E` with `t1_key` k1, `Put(q1,E)`, a promoted `Put(q2,E)`),
      `F` (`Put(q3,F)` only) and `G` (`t2:G`, `Put(q4,G)`). Touch them oldest to newest: E, F, G. Then
      `TrimToCapacity(1)` evicts E and F. Afterwards there is no k1, k2 or k3, no `t2:E`, no
      `lru:t1keys:E` / `:F`, and no `lru:entries` member for E or F. G's `t1:`, `t2:`, set and member are
      unchanged. The returned `T1Keys` lists k1 and k2 for E, and k3 for F.
    - `TestTrimDropsLeaveAReusedKey`: after E is set up, `HSET k1 entry_id E2`. Evicting E leaves k1.
  - Run: `cd gateway && go test -count=1 -v -run TestTrimDrops ./internal/cache/`
  - Pass: two `--- PASS`.
  - Result: added cache/t1keys_trim_test.go (TestTrimDropsEveryTier1Key, TestTrimDropsLeaveAReusedKey); two PASS; G also has a promoted key there, a stricter unchanged-check than the plan's G.

- [x] 2.3 `cache`: the purge drops every Tier-1 key (DC 5, the cache half).
  - Files: `gateway/internal/cache/t1keys_purge_test.go` (new)
  - Do:
    - `TestPurgeDropsEveryTier1Key`: E with a miss key and a promoted key. `PurgeEntry(E, "")` deletes both,
      the set, `t2:E` and the `lru:entries` member.
    - `TestPurgeDropsLeaveAReusedKey`: the promoted key re-pointed at `E2` survives.
  - Run: `cd gateway && go test -count=1 -v -run TestPurgeDrops ./internal/cache/`
  - Pass: two `--- PASS`.
  - Result: added cache/t1keys_purge_test.go (TestPurgeDropsEveryTier1Key, TestPurgeDropsLeaveAReusedKey); two PASS.

- [x] 2.4 `deps`: the purge end to end (DC 5, the deps half).
  - Files: `gateway/internal/deps/t1keys_test.go` (new, `package deps`)
  - Do: `TestInvalidateDropsPromotedKey` uses 4.1's `testRedis`, `newMap`, `barrier`, and a `cache.NewStore(rdb,
    768)` as both the store and the `Purger`. Set up E through the store: `HSET t2:E`, `Put(q1,E)` and a
    promoted `Put(q2,E)`. Then `Register(E, sources {A}, T1Key k1)` with no epoch source, `Invalidate(A)`,
    and `barrier`. Afterwards no `t1:*` key has `entry_id` E (scan them), and `lru:t1keys:E` is gone.
  - Run: `cd gateway && go test -count=1 -v -run TestInvalidateDropsPromotedKey ./internal/deps/`
  - Pass: `--- PASS`; no `--- SKIP`.
  - Result: added deps/t1keys_test.go (TestInvalidateDropsPromotedKey, real Store as Purger, DB 14); PASS, no SKIP.

- [x] 2.5 `cache`: no orphan after a mixed sequence (DC 7).
  - Files: `gateway/internal/cache/t1keys_orphan_test.go` (new)
  - Do: `TestNoOrphan`. Six entries:
    - four full (a `t2:` hash, a miss `Put`) and two Tier-1 only;
    - three promotions, one of them after its entry was trimmed (it must write nothing);
    - `Touch` after every write, as the handler does.

    Then `TrimToCapacity(3)` and `PurgeEntry` on one remaining entry. At the end:
    - `SCAN t1:*`: every key's `entry_id` is a `lru:entries` member;
    - `SCAN lru:t1keys:*`: every set's entry is a `lru:entries` member;
    - every listed key exists and names that entry.
  - Run: `cd gateway && go test -count=1 -v -run TestNoOrphan ./internal/cache/`
  - Pass: `--- PASS`.
  - Result: added cache/t1keys_orphan_test.go (TestNoOrphan: six entries, three promotions, trim to 3, purge of F4; T2 and F3 remain with 3 t1 keys and 2 sets); PASS.

## Phase 3 — Integration tests

- [x] 3.1 `httpapi`: the promotion is conditional on the request path (DC 8).
  - Files: `gateway/internal/httpapi/t1keys_test.go` (new)
  - Do: `TestTier2HitPromotesConditionally`. Use `newHarness(t, 1, 0)`, then `seedHit` and `askNear` as the
    existing Tier-2 tests do, and wait for "the Tier-1 promotion". `hs.store.tier1Written()[0].entry.Promotion`
    is true. A separate plain MISS on another question writes one Tier-1 entry with `Promotion` false.
  - Run: `cd gateway && go test -count=1 -v -run TestTier2HitPromotesConditionally ./internal/httpapi/`
  - Pass: `--- PASS`.
  - Result: added httpapi/t1keys_test.go (TestTier2HitPromotesConditionally; the miss check uses a second harness so the counts stay clean); PASS.

## Phase 4 — Run and verify

Run every step alone, in order.

- [x] 4.1 `redis-cli PING` → `PONG`; `go clean -testcache`; then `make verify` alone.
  - Pass: exit 0; no FAIL; any SKIPPED target listed by name.
  - Result: PONG; uncached `make verify` ran alone: gofmt, vet and ruff clean, all Go packages ok, 50 rag tests and 731 experiments tests passed, no FAIL, no SKIPPED (log: evidence/verify-1.out; the shell's exit code was lost to `tee`, but the log has no error line).
- [x] 4.2 DC 1, 2 — `cd gateway && go test -count=1 -v -run 'TestPutRecords|TestPromotion' ./internal/cache/`
  - Pass: three `--- PASS`; no `--- SKIP`.
  - Result: TestPutRecordsTier1Key, TestPromotionNeedsTier2, TestPromotionWithoutEntryIDFails all PASS; no SKIP.
- [x] 4.3 DC 3, 4 — `cd gateway && go test -count=1 -v -run TestTrimDrops ./internal/cache/`
  - Pass: two `--- PASS`.
  - Result: TestTrimDropsEveryTier1Key and TestTrimDropsLeaveAReusedKey PASS.
- [x] 4.4 DC 5 — `cd gateway && go test -count=1 -v -run TestPurgeDrops ./internal/cache/`, then
  `go test -count=1 -v -run TestInvalidateDropsPromotedKey ./internal/deps/`
  - Pass: three `--- PASS` in all; no `--- SKIP`.
  - Result: TestPurgeDropsEveryTier1Key and TestPurgeDropsLeaveAReusedKey (cache) PASS; TestInvalidateDropsPromotedKey (deps) PASS; no SKIP.
- [x] 4.5 DC 6 — `cd gateway && go test -count=1 -p 1 -v ./internal/cache/ ./internal/deps/ 2>&1 | grep -E "^(--- |ok|FAIL)"`
  - Pass: every line is `--- PASS` or `ok`. That includes `capacity_test.go`'s tests,
    `TestEvictionLeavesDependencyRecordsAlone`, 4.1's `TestPurgeEntry*` and every `deps` test.
  - Result: 27 cache and 18 deps tests all `--- PASS`, two `ok`, no SKIP or FAIL; the old seeds without a set still go through `t1_key`.
- [x] 4.6 DC 7 — `cd gateway && go test -count=1 -v -run TestNoOrphan ./internal/cache/`
  - Pass: `--- PASS`.
  - Result: TestNoOrphan PASS.
- [x] 4.7 DC 8 — `cd gateway && go test -count=1 -v ./internal/httpapi/ 2>&1 | grep -E "^(--- FAIL|--- SKIP|ok|FAIL)|TestTier2HitPromotesConditionally"`
  - Pass: `--- PASS: TestTier2HitPromotesConditionally`; `ok`; no `--- FAIL` and no `--- SKIP` (so every
    existing promotion test passed).
  - Result: `--- PASS: TestTier2HitPromotesConditionally`, `ok`, no --- FAIL and no --- SKIP.
- [x] 4.8 DC 9 — the greps of steps 1.6 and 1.7.
  - Pass: as in 1.6 and 1.7.
  - Result: interfaces.md shows v0.19 header, §D set, §E text and version rows and no "Item 4.3 will add"; the not-tracked grep is empty; the Redis notes have 13 `lru:t1keys:` lines and architecture.md invariant 3 names it.
- [x] 4.9 DC 10 — `make verify` passed in 4.1, with Redis up. Record any SKIPPED names.
  - Result: `make verify` (4.1, run alone, Redis up) had no FAIL and no SKIPPED target: ruff and pytest ran (50 rag, 731 experiments tests passed).
- [x] 4.10 DC 11 — `cd /Users/hung/Desktop/Sem1/thesis && git status --porcelain -- '*_test.go' 'rag/tests/*'`
  - Pass: every line starts with `??` or `A `; none with `M` or `D`.
  - Result: six lines, all `??` (the six new t1keys_*test.go files); no `M` or `D`.
- [x] 4.11 DC 12 — `grep -n "lru:t1keys:" experiments/scripts/epoch_race_check.py`
  - Pass: not empty.
  - Result: prints lines 228 and 229 of epoch_race_check.py.

## Phase 5 — Fix §4's finding: the RAG read path waits for its index (added at build, 2026-10-28)

The human chose to fix §4's finding inside 4.3 (option A). Design: §3 "The index-ready fix". The failing
test comes first. Run every step alone. Never `FLUSHDB`, and never drop `idx:corpus`. `rag` tests run as
`cd rag && python3 -m pytest …`, with ruff and pytest on `PATH` as before.

- [x] 5.1 The failing test.
  - Files: `rag/tests/test_store_index_ready.py` (new)
  - Do: `test_get_vector_store_returns_only_after_background_indexing_finishes`, exactly as design §3.
    Mark it the way `test_retrieve_scoping.py` marks its Redis tests. It refuses to run if the patched name
    equals `idx:corpus`. Its cleanup runs in a `finally`. Do not touch `store.py` yet.
  - Run: `cd rag && python3 -m pytest -v tests/test_store_index_ready.py 2>&1 | tee ../docs/work/2026-10-28-promoted-t1-keys/evidence/index-ready-before.out | tail -15; redis-cli FT._LIST`
  - Pass: the test **FAILS**, because `FT.INFO` shows `indexing` 1 or `num_docs` below the count (the reason
    in §4), not because of an import or set-up error. `FT._LIST` shows `idx:corpus` and no `idx:test-ready`.
  - Result: added rag/tests/test_store_index_ready.py; it FAILS for §4's reason (`indexing` 1, `percent_indexed` 0.09, `num_docs` 4 of 44; log: evidence/index-ready-before.out); `FT._LIST` shows only `idx:corpus`. Pressure level 2, no model loaded.

- [x] 5.2 The fix.
  - Files: `rag/src/rag/store.py`
  - Do: `IndexNotReady`, `wait_until_indexed`, and the call in `get_vector_store`, exactly as design §3.
    Add a comment saying why: §4, the index is filled in the background after `FT.CREATE`, and a search
    before it finishes sees part of the corpus with no error.
  - Run: `cd rag && python3 -m pytest -v tests/test_store_index_ready.py 2>&1 | tee ../docs/work/2026-10-28-promoted-t1-keys/evidence/index-ready-after.out | tail -5 && ruff check src/rag/store.py`
  - Pass: the test `PASSED`; ruff clean.
  - Result: rag/src/rag/store.py gained IndexNotReady, wait_until_indexed and the call in get_vector_store; the test PASSED (evidence/index-ready-after.out), ruff clean after one comment rewrap for E501.

- [x] 5.3 The timeout test.
  - Files: `rag/tests/test_store_index_timeout.py` (new)
  - Do: `test_wait_until_indexed_raises_when_indexing_never_finishes`, with a fake client and a short
    timeout (for example 0.05 s). It asserts `IndexNotReady` is raised and that the call took at least the
    timeout. No Redis.
  - Run: `cd rag && python3 -m pytest -v tests/test_store_index_timeout.py`
  - Pass: `PASSED`.
  - Result: added rag/tests/test_store_index_timeout.py (fake client, 0.05 s limit, asserts IndexNotReady and elapsed >= limit); PASSED, ruff clean, no Redis used.

- [x] 5.4 The old flaky test, from a cold index.
  - Run: `redis-cli -n 13 DBSIZE` (must be 0), then `redis-cli -n 13 FLUSHDB`, so `FT._LIST` is empty, as
    after the Go tests. Then `cd rag && python3 -m pytest -v tests/test_retrieve_scoping.py`, then
    `redis-cli FT._LIST`.
  - Pass: all `test_retrieve_scoping.py` tests `PASSED`; `FT._LIST` shows `idx:corpus` again. Loads the
    embedding model only: `citable: no`. Write the pressure level next to the result.
  - Result: DB 13 had 0 keys, `FLUSHDB` there left `FT._LIST` empty; all 5 `test_retrieve_scoping.py` tests PASSED and `FT._LIST` shows `idx:corpus` again. Pressure level 2 (yellow), citable: no.

- [x] 5.5 `make verify`, alone, after `go clean -testcache`, with the exit code captured. Do not pipe it:
  `make verify > ../evidence-file 2>&1; echo "exit=$?"`.
  - Run: `cd /Users/hung/Desktop/Sem1/thesis && redis-cli PING && go clean -testcache && make verify > docs/work/2026-10-28-promoted-t1-keys/evidence/verify-phase5.out 2>&1; echo "exit=$?"`
  - Pass: `exit=0`; no FAIL; no SKIPPED target.
  - Result: `exit=0` (no pipe); lint, all Go packages ok, 52 rag tests (50 old + 2 new) and 731 experiments tests passed; no FAIL, no SKIPPED (evidence/verify-phase5.out). Pressure level 2, citable: no.
