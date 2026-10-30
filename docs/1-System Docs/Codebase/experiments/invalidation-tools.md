# `experiments/scripts/` — the invalidation tools

**Describes:** commit `29b24a6` (30 Oct 2026); last changed in `68d732e` (item 4.4). **Files:** `update_set.py` (224
lines), `update_set_check.py` (836), `score_update_set.py` (182), `epoch_race_check.py` (597), `cache_reset.py` (136).
**The system view** is in [`Invalidation.md`](../../Cache_Invalidation/Invalidation.md) and
[`Update set.md`](../../Cache_Invalidation/Update%20set.md); this doc says what each script does.

## 1. Purpose

They build and check the update set, run invalidation live, score it, force the epoch race, and reset the cache
before a measured run. They serve **C2** and **C3**. None of their runs is citable.

## 2. Boundaries

- **Never `FLUSHDB` or `FLUSHALL`**: on this Redis either drops every search index (see
  [`testredis.md`](../gateway/testredis.md)). Keys are deleted by prefix or by name.
- Files holding `qa_id`s or chunk IDs (which can carry an ASIN) stay in a gitignored `private/` folder; only counts
  are committed.
- The live scripts load the models: check memory pressure first. While they run, use nothing else on Redis or Ollama.

## 3. The scripts

### `update_set.py`

- **`make update-set-probe OUT=<file>`**: runs the product-scoped retrieval for every validation question and writes
  `qa_id → chunk_ids` (IDs only). It is how edits were chosen on chunks that some question reaches.
- **`make update-set-verify`**: offline. Rebuilds the `v1` chunk texts with `rag.ingest.records_to_nodes` (no
  embedding), checks every edit's `before` is in its chunk, the counts, the 30 → 14 day edit, and the manifest hash.
  It names edits and chunks by ID and never prints text.

### `update_set_check.py` — `make update-set-check EVIDENCE=<new folder>`

The live run of [`Update set.md`](../../Cache_Invalidation/Update%20set.md) §3: preconditions; the forced race; a reset
and a fill; snapshots before and after the 20 edits (through `rag.edit.apply`); the re-ask; restoring every chunk
(through `rag.edit.restore`) and checking its text and vector; then the scorer. It runs its own `rag.server` and
gateway with **their own epoch file**, so `data/dataset-epoch` is never touched, and with **no cache bound**, so no
eviction can look like a purge. Exit codes: 0 every check passed · 1 a check failed · 2 "race not forced" (re-run).

### `score_update_set.py` — `make update-set-score EVIDENCE=<folder>`

Reads only the saved files, never Redis. It computes completeness, exactness and precision from the sets P, D and G,
with sources taken from the **evaluation log**, never from `dep:*`, and runs ten checks. Two runs on one folder print
the same bytes. Definitions: [`Update set.md`](../../Cache_Invalidation/Update%20set.md) §4.

### `epoch_race_check.py` — `make epoch-race-check` (item 4.2)

Forces the race of `Invalidation.md` §9 with an epoch advance standing in for an edit:
1. builds the gateway; makes a temp epoch file (value 1);
2. starts `rag.server` (port 50053) and the gateway (port 18080) on that file, with `MUTATION=on`;
3. picks two products, so neither question can be a Tier-2 hit on the other;
4. question A with no edit: its write-back must land;
5. question B, with the epoch advanced 1.5 s after it is sent;
6. stops both with SIGINT (the log is flushed), and checks the records and the Redis key difference;
7. deletes exactly the keys it wrote;
8. writes the evidence.

**It cannot pass by accident**: only a real epoch mismatch sets `writeback_discarded`. If B was not discarded, the
advance came too late, and it exits 2, "race not forced".

### `cache_reset.py` — `make cache-reset`

Run rule 11: a measured run starts on a cache it wrote itself. It deletes every `t1:`, `t2:`, `lru:`, `dep:` and
`entry:` key with `SCAN` + `UNLINK`, and nothing else. Then it checks the five prefixes are empty, the number of
`corpus:` keys is unchanged, and `FT._LIST` shows the same indexes. **It refuses while a gateway port (8080, 18080,
18081) is listening**: a reset under a live gateway would leave its tombstones pointing at deleted keys. A gateway on
another port is not seen.

## 4. Callers and callees

- Run through `make` (above). `update_set_check.py` imports `cache_reset`, `epoch_race_check`, `score_update_set` and
  `update_set`, and calls `rag.edit`.

## 5. Tests that pin them

`experiments/tests/test_update_set.py`, `test_update_set_snapshot.py`, `test_score_update_set.py` and
`test_cache_reset.py`. The scorer's tests cover every check and both numbers' edge cases; the snapshot test covers the
scan of every `t1:*` key.

## 6. Silent failures to watch

- **Scoring from `dep:*`** would hide a registration that never happened. The scorer reads the log.
- **A reset under a running gateway on another port** is not refused (only 8080, 18080 and 18081 are checked).
- **A completeness run with the support gate on** can hide a missed purge in the re-ask (ADR-009); the snapshot
  comparison still catches it.

## 7. Commit

`29b24a6`; last changed in `68d732e`.
