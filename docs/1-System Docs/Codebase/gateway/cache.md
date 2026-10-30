# `gateway/internal/cache/` — both cache tiers, the LRU bound and the purge script

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `key.go`, `normalize.go`, `entry.go`, `entry_id.go`,
`store.go`, `tier2.go`, `capacity.go`, `purge.go`, `doc.go` (773 lines in all), and 11 test files. Governing
contract: `interfaces.md` §D. **Every Redis key and field** is described in `Redis-Data Structure.md` §4–§6;
this doc explains the code that reads and writes them.

## 1. Purpose

It stores and reads cached answers: Tier 1 (exact match) and Tier 2 (vector search). It enforces the cache
bound with its own LRU trim, because Redis evicts nothing. It gives `deps/` a purge that removes an entry from
both tiers. It serves **S1** (load conversion) and **C2** (the purge).

## 2. Boundaries

- It **never makes a reuse decision**. A SHA-256 equality is not a judgement; the decision is `reuse/`'s.
- It imports nothing from this repository. `httpapi` uses it through a small interface (`cacheStore` in
  `handler.go`), so tests can use a fake.
- It never reads or writes `dep:*` or `entry:*`; those belong to `deps/`.

## 3. Files

### `normalize.go` and `key.go` — the Tier-1 key

**`Normalize(query)`**: lower-case, collapse runs of white space to one space, drop every punctuation and symbol
character, trim. **No stemming, no stopwords, no synonyms**: each of those would merge two different questions at
the hash, which is a reuse decision made where nothing measures it. The same function must run on the read and
the write path. The cases it must handle are shared with Python in `contracts/normalize/cases.json`.

**Known collisions**, accepted: "Model A-1" and "Model A1" become the same text, and so do "-10 °C" and
"10 °C", or "1.5 m" and "15 m" (`Tier 2.md` §12a, row 2). Tier 1 runs no rule, so such a collision would serve
one answer for the other. Gate G3 keeps them out of the frozen workload; in real traffic they are a limit.

**`Key(normalized, productID)`** returns `t1:{sha256(normalized "\x00" productID)}` (ADR-018). An empty
`productID` is its own partition, never a wildcard. The `\x00` separator matters: without it,
`Key("ab", "c")` and `Key("a", "bc")` would be the same.

### `entry.go` and `entry_id.go` — the Tier-1 record and its ID

**`Entry`** is the Tier-1 hash: `Answer`, `SourceChunkIDs`, `ModelUsed`, `CreatedAt`, `EntryID`, and
**`Promotion`**, which marks a write that copies a Tier-2 entry into Tier 1 after a Tier-2 hit. The record holds no
`t1_key`: that lives on the Tier-2 record and in `lru:t1keys:{entry_id}`.

**`NewEntryID()`** mints a ULID: a 48-bit millisecond time plus 80 random bits, in 26 Crockford base-32
characters. It is written here, not imported, to avoid a new dependency. One ID names an answer in both tiers.

### `store.go` — Tier 1

**`Store`** wraps the Redis client and the vector width (`dim`, from `embed.Dim`).

**`Get(ctx, query, productID)`** normalises, builds the key, and reads the hash. `false` means a miss.

**`Put(ctx, query, productID, e)`** writes a Tier-1 hash and, **in the same atomic step**, adds the key to
`lru:t1keys:{entry_id}`. A key written without that record would be an orphan after eviction, serving an entry
the cache no longer holds. It mints an `EntryID` if none was given.

**Promotion** (`e.Promotion = true`) goes through **`promoteScript`**, which writes the Tier-1 key **only while
`t2:{entry_id}` exists**. The check and the write are one Lua script, because a promotion runs in the background
after a Tier-2 hit: with two calls, a trim or purge could remove the entry in between, and the promotion would
then leave a Tier-1 pointer to a purged answer. A promotion that finds no `t2:` writes nothing and is not an
error.

### `tier2.go` — Tier 2

**`EnsureCacheIndex(ctx)`** creates `idx:cache` if absent, then **waits until the index is complete**
(`waitIndexed`: no documents still indexing **and** 100 % indexed, up to 10 s). `FT.CREATE` returns at once and
indexes existing `t2:*` hashes in the background; a KNN during that scan returns nothing or a wrong entry, with
no error. The gateway runs this at every start.

**`Tier2Entry`** is the `t2:` hash (`Redis-Data Structure.md` §5.2). **`PutTier2(ctx, e, vec)`** writes it. The
caller passes the same `entry_id` and `t1_key` it used for Tier 1, so both tiers share one identity.

**`NearestTier2InNamespace(ctx, vec, namespace, k)`** runs a RediSearch hybrid query,
`(@namespace:{ns})=>[KNN k …]`: the nearest entries **inside** one namespace. This is an optimisation, not the
rule: `reuse/` checks the namespace again on whatever comes back. It replaced fetching the k nearest overall and
filtering in Go, which missed a good in-namespace entry at rank k + 1. An **empty namespace is refused without
touching Redis**.

**`NearestTier2(ctx, vec, k)`** searches the whole cache. **Nothing in the gateway calls it today**; it is the
search configuration 3 (similarity alone, ADR-019) will use once item 6.0 builds configuration selection.

**`escapeTag(v)`** escapes a TAG value. Namespaces are `doc_id`s joined by `|`, and both `-` and `|` are query
syntax: unescaped, `product-…` parses as a negation and matches nothing, with no error.

**`nearest(…)`** runs the KNN and turns the cosine **distance** Redis returns into **similarity** (1 − distance).
**`encodeVector`** packs float32 values little-endian, the layout Redis expects.

**`BumpHitCount(ctx, entryID)`** increments a served Tier-2 entry's counter, fire-and-forget (it feeds the
demo's "generations avoided").

### `capacity.go` — the LRU bound

**`lruKey = "lru:entries"`**: a sorted set of `entry_id`s scored by last access. It is not prefixed `t1:` or
`t2:`, and it is never evicted. **`t1KeysPrefix = "lru:t1keys:"`**: the per-entry set of every Tier-1 key
written for it (item 4.3). It lives in the `lru:` region, not in `deps/`'s `entry:`, because this package never
reads the dependency records.

**`Touch(ctx, entryID, now)`** records an access, on every hit and every write-back, fire-and-forget. A missed
touch only makes an entry look older.

**`dropEntryScript`** is what "this entry is gone" means. **Both the trim and the purge run it**, so they can never
disagree. It gathers candidate Tier-1 keys from three places (the `lru:t1keys:` set, the `t2:` record's `t1_key`,
and a key the caller passes), deletes each **only if its `entry_id` still names this entry**, then deletes `t2:`,
the set and the `lru:entries` member. It never touches `dep:*` or `entry:*`. The key names are read at run time,
which Redis Cluster would refuse; the single standalone server makes it fine.

**`TrimToCapacity(ctx, capacity)`** evicts the least recently used entries until at most `capacity` remain; 0 or
less means unbounded. **Both tiers of a victim go together**: deleting `t2:` alone would leave the Tier-1 copy
serving an answer the experiment thinks is gone, and the capacity sweep would measure nothing. It returns the
victims, so the caller can log what the bound cost.

**`CachedEntries(ctx)`** is the entry count. Only the tests call it today; it is meant for the run manifest
(item 5.1).

### `purge.go`

**`PurgeEntry(ctx, entryID, t1Key)`** runs `dropEntryScript` for one entry. It is what `deps/` calls through its
`Purger` interface. `t1Key` may be empty; for a Tier-1-only entry, `deps/` passes the key it recorded in
`entry:`.

## 4. Callers and callees

- **`cmd/gateway/main.go`**: `NewStore(rdb, embed.Dim)`, `EnsureCacheIndex` at start, and passes the store to
  `deps.New` as the `Purger`.
- **`httpapi`**: `Get` and `Put` (Tier 1), `NearestTier2InNamespace` (`cascade.go`), `PutTier2`, `Touch`,
  `TrimToCapacity` (after each write-back, with `CACHE_CAPACITY`), `BumpHitCount`, and `Put` with `Promotion`.
- **`deps`**: `PurgeEntry`.

## 5. Tests that pin it

The Redis tests run on the throwaway server (`make test-go`).

| Area | Tests |
| :--- | :--- |
| Normalisation and key | `TestNormalize`, `TestNormalizeIsIdempotent`, `TestNormalizeDoesNotStemOrDropStopwords`, `TestNormalizeCollapsesHyphenatedModelNames` (the documented collision), `TestNormalizeMatchesCrossLanguageContract`, `TestKey`, `TestKeyIsScopedByProductID`, `TestKeySeparatorIsUnambiguous` |
| LRU trim | `TestTrimEvictsLeastRecentlyUsedFirst`, `TestEvictionRemovesBothTiers`, `TestTouchRescuesAnOtherwiseDoomedEntry`, `TestZeroCapacityEvictsNothing`, `TestEvictionLeavesDependencyRecordsAlone` |
| Tier-1 key tracking | `TestPutRecordsTier1Key`, `TestPromotionNeedsTier2`, `TestPromotionWithoutEntryIDFails`, `TestNoOrphan`, `TestTrimDropsEveryTier1Key`, `TestTrimDropsLeaveAReusedKey` |
| Purge | `TestPurgeEntryDeletesBothTiers`, `TestPurgeEntryLeavesReusedTier1Key`, `TestPurgeEntryReadsT1KeyFromTier2`, `TestPurgeDropsEveryTier1Key`, `TestPurgeDropsLeaveAReusedKey` |
| Index readiness and search | `TestEnsureCacheIndexReturnsOnlyWhenIndexed`, `TestEnsureCacheIndexWaitsWhenItAlreadyExists`, four `TestWaitIndexed*` tests, `TestEscapeTagEscapesEveryCharacterThatIsQuerySyntax`, `TestNearestInNamespaceRefusesTheEmptyNamespaceWithoutTouchingRedis` |

## 6. Silent failures to watch

- **A key prefix mismatch** between what is written (`t2:`, one colon) and the index's `PREFIX` indexes nothing,
  and every lookup misses with no error. Python's corpus keys have two colons (`corpus::`); that difference is
  correct.
- **An unescaped namespace** matches nothing: every Tier-2 lookup becomes a miss.
- **Any `FLUSHDB` or `FLUSHALL`** drops `idx:cache` and `idx:corpus` (see [`testredis.md`](testredis.md)). Use
  `make cache-reset`.
- **Normalisation collisions** serve one answer for a different question in Tier 1, which runs no rule.

## 7. Commit

`29b24a6`.
