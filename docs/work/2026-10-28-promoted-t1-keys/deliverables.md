# Deliverables — Track every Tier-1 key of an entry

Closed 2026-10-28 · super-plan item 4.3 · no new ADR (`interfaces.md` v0.19)

## What shipped

- **Every Tier-1 key of an entry is recorded** in a cache-owned set, `lru:t1keys:{entry_id}`. It is written in
  the same atomic step as the Tier-1 hash, on the miss write-back and on the promotion. This was the
  decision the item asked for: track the keys, not drop them on purge.
- **One script, `dropEntryScript`, defines "this entry is gone"**, for both the trim and the purge. Its
  candidates are the set, the `t2:` record's `t1_key`, and the caller's key. Each key is deleted only if it
  still names the entry; then `t2:`, the set and the `lru:entries` member go. `dep:*` and `entry:*` are never
  touched.
- **A promotion is written only while `t2:` exists**, in one script, so it cannot bring back a pointer at an
  entry that was just evicted or purged. The handler marks it with `cache.Entry.Promotion`.
- **Also fixed:**
  - A Tier-1-only entry no longer leaves an orphan key when it is evicted.
  - Eviction no longer deletes a reused key blindly.
- **Fixed at build, from the RCA in design §4:** `rag/store.py`'s `get_vector_store` waits until the corpus
  index is fully built (`wait_until_indexed`; `IndexNotReady` after 5 s). Before this, a search right after
  the index was recreated saw part of the corpus with no error. That is what made `make verify` fail now and
  then, in 4.1 and here.

## Files changed

- Gateway: `cache/capacity.go`, `cache/purge.go`, `cache/store.go`, `cache/entry.go`, `httpapi/handler.go`.
- RAG: `rag/src/rag/store.py`.
- `experiments/scripts/epoch_race_check.py`: its cleanup deletes the new set.
- New tests: `cache/t1keys_test.go`, `t1keys_trim_test.go`, `t1keys_purge_test.go`, `t1keys_orphan_test.go`,
  `deps/t1keys_test.go`, `httpapi/t1keys_test.go`, `rag/tests/test_store_index_ready.py`,
  `rag/tests/test_store_index_timeout.py`. No existing test was edited.
- Docs: `interfaces.md` v0.19 (§D set and rules; §E step 3 and its `entry:` plan), `architecture.md`,
  `Redis-Data Structure.md`.

## How it was verified

The main session re-ran these on 2026-10-28, one at a time, after Phase 5.

| DC | Command | Result |
| :--- | :--- | :--- |
| 1, 2 | `go test -run 'TestPutRecords\|TestPromotion' ./internal/cache/` | 3 pass |
| 3, 4 | `go test -run TestTrimDrops ./internal/cache/` | 2 pass |
| 5 | `go test -run TestPurgeDrops` (cache); `-run TestInvalidateDropsPromotedKey` (deps, DB 14) | 2 + 1 pass |
| 6 | `go test -p 1 -v ./internal/cache/ ./internal/deps/` | 45 pass, nothing else; old capacity, purge, eviction tests included |
| 7 | `go test -run TestNoOrphan ./internal/cache/` | pass |
| 8 | `go test -v ./internal/httpapi/` | `TestTier2HitPromotesConditionally` passes; no FAIL or SKIP |
| 9 | greps on the three docs | v0.19 lines present; no stale "not tracked" or "Item 4.3 will add" |
| 10 | `make verify`, alone, Go test cache cleared | `exit=0`; no FAIL; no SKIPPED target (`evidence/verify-recheck-2.out`) |
| 11 | `git status --porcelain -- '*_test.go' 'rag/tests/*'` | 8 lines, all `??` |
| 12 | grep in `epoch_race_check.py` | 2 lines |
| 13 | the two new rag tests | fail before the fix (`evidence/index-ready-before.out`: `indexing` 1, 4 of 44 docs), pass after |

The first `make verify` re-check failed (`evidence/verify-recheck.out`). That is the finding in design §4,
fixed in Phase 5. The old flaky test also passed straight after the Go tests had dropped the index.

The item's "Done when" is met: a purge removes every Tier-1 pointer at the entry, promoted ones included
(DC 5), and an eviction leaves no orphan (DC 3, 7). Both are shown by tests on Redis DB 14 and 15. No live
gateway run was made.

## Numbers

None. The tests that loaded the embedding model (`test_retrieve_scoping.py`, inside `make verify`) ran at
memory pressure level 2 (yellow), on the `dev-v0` corpus. They are functional checks: `citable: no`.

## Deferred and follow-ups

- **Next, a `/bugfix` on the Redis index lifecycle** (design §4, problems 2 and 3), before item 4.4:
  - The Go test helpers' `FLUSHDB` drops every search index on the shared server. The fix edits existing
    test files and needs the human's approval.
  - `cache/tier2.go` may have the same create-then-search race for `idx:cache` at gateway start. This is
    not checked yet.
- **Promoted keys written before this change** stay untracked. A measured run starts on a cache it wrote
  itself (run rule 11), and the reset for that rule still has no owner.
- **`interfaces.md` §E's "Purge decision" line** still says "dropping both the `t2:` record and its
  `t1_key`". It is less complete than step 3, but not wrong.
- **Carried from 4.1:** a failed purge still deletes `dep:{chunk}`.
