# Redis in this thesis — what is stored, and how

*Written 2026-10-15 from the code, the contract (`interfaces.md` §C–§E) and the live Redis server.
Where the code and the contract disagree, the code is described and the gap is listed in §9.*
*Updated 2026-10-25 after the `v1` freeze (ADR-015): the `v1` corpus (§1, §3), the frozen `K` (§6) and
how to empty the cache for a measured run (§11, run rule 11, ADR-010).*

---

## 1. The big picture

Redis holds **only copies** (ADR-007). The real source is the JSON files in
`data/<dataset_version>/`. If Redis loses everything, `make ingest` rebuilds the corpus, and the cache
fills again on the next misses. No data is lost. But Redis down is still an **outage**: retrieval also
needs Redis, so every request fails until it is back.

Everything lives on **one** `redis-stack-server` (`localhost:6379`, database 0). The keys form three
areas. Each area has its own key prefix.

```
                     ONE redis-stack-server  (localhost:6379, DB 0)
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  AREA 1 — CORPUS          written by Python (make ingest)                    │
│  ┌──────────────────────────────────────────┐                                │
│  │ corpus::{chunk_id}      HASH   one/chunk │ ◄─── idx:corpus (search index) │
│  └──────────────────────────────────────────┘                                │
│                                                                              │
│  AREA 2 — CACHE           written by the Go gateway (on a MISS)              │
│  ┌──────────────────────────────────────────┐                                │
│  │ t1:{sha256}             HASH   Tier 1    │                                │
│  │ t2:{entry_id}           HASH   Tier 2    │ ◄─── idx:cache  (search index) │
│  │ lru:entries             ZSET   only one  │                                │
│  └──────────────────────────────────────────┘                                │
│                                                                              │
│  AREA 3 — DEPENDENCY      written by the gateway's one writer (item 4.1)     │
│  ┌──────────────────────────────────────────┐                                │
│  │ dep:{chunk_id}          SET    of entry_id│                                │
│  │ entry:{entry_id}        HASH   t1_key,    │                                │
│  │                                source_ids │                                │
│  └──────────────────────────────────────────┘                                │
└──────────────────────────────────────────────────────────────────────────────┘

NOT in Redis:  the source JSON files ......... data/dev-v0/*.json, data/v1/*.json
               the dataset epoch ............. outside Redis on purpose (ADR-008)
               the evaluation log + answers .. experiments/results/{run_id}/raw/ (ADR-005)
```

**What the live server holds today (2026-10-15):** 44 keys, all `corpus::*` — 40 product chunks and
4 policy chunks of `dev-v0`, one chunk per document — plus the index `idx:corpus`. There are no cache
keys and no `idx:cache`, because the gateway is not running. The gateway creates `idx:cache` when it
starts (`EnsureCacheIndex`, `gateway/cmd/gateway/main.go`). This was checked again on 2026-10-25 and
had not changed.

**`v1` is frozen but not loaded.** `v1` was frozen on 2026-10-23 (ADR-015, `data/v1-freeze.json`).
Between runs Redis holds `dev-v0`. Every `v1` run starts by loading it with
`DATASET_VERSION=v1 make ingest`, then checks that the index is the corpus on disk with
`make corpus-index-check`.

**Redis never deletes a key by itself.** The server runs with `maxmemory 0` (no memory limit) and
`maxmemory-policy noeviction`. `make redis-check` fails if either is different. When the cache must
shrink, the **gateway** chooses what to delete (§6). The reason: Redis's own eviction works on bytes,
not on a number of entries, and it is one setting for the whole server, so it could also delete the
`dep:*` records that invalidation needs.

---

## 2. Redis words you need

Redis is one big map: **key → value**. The value has a type. This thesis uses three types, plus the
search module.

| Word | Meaning |
| :--- | :--- |
| **key** | The name of one record, e.g. `t2:06GKX34SBEKD749SN5JZKRYC10`. |
| **prefix** | The start of a key, e.g. `t2:`. We use prefixes like folders. Indexes and scripts find keys by prefix. |
| **HASH** | A value that is a small table of *field → value*, like a flat JSON object of strings. Write: `HSET`. Read: `HGETALL` (all fields), `HGET` (one), `HMGET` (several). `HINCRBY` adds to a number field. |
| **SET** | A bag of unique strings, with no order. `SADD`, `SMEMBERS`. |
| **ZSET** (sorted set) | A set where each member has a number called the *score*. Redis keeps it sorted by score. `ZADD`, `ZRANGE`, `ZCARD` (count), `ZREM`. |
| **RediSearch** | A module inside redis-stack that adds search indexes. `FT.CREATE` makes an index, `FT.SEARCH` queries it. |
| **index** | A search structure that **watches** every HASH whose key starts with a given prefix. When you `HSET` such a key, the index updates itself. It does not hold a second copy of the hash. |
| **field types** | **TAG** = an exact label, never split into words. **TEXT** = full text, split into words. **NUMERIC** = a number. **VECTOR** = a list of floats, searched by nearness. |
| **vector / embedding** | 768 numbers (`float32`) from `nomic-embed-text`. Texts with similar meaning get vectors that point in a similar direction. Stored as raw bytes: 768 × 4 = **3072 bytes**. |
| **cosine similarity / distance** | Similarity = how close two vectors point (1 = same direction). Redis returns **distance = 1 − similarity**. The Go code turns it back into similarity. |
| **KNN** | *k nearest neighbours*: "give me the k stored vectors closest to this one". |
| **FLAT vs HNSW** | FLAT compares the query with **every** vector: exact. HNSW is a faster, approximate search that can miss. FLAT is **frozen for the whole study**, because HNSW would make results change from run to run. |
| **hybrid query** | A filter and a KNN in one query: "the nearest vector, but only among keys whose tag is X". |
| **transaction** | `MULTI … EXEC`: several commands applied as one step. |
| **FLUSHALL** | Deletes every key **and** every index on the server. Only `make demo-reset` should run it. |

The four shapes, drawn:

```
HASH  — one key, many fields              SET  — one key, a bag of members
┌──────────────────────────────────┐      ┌──────────────────────────────────┐
│ key  t1:1f8fa611…350b            │      │ key  dep:policy-warranty#chunk-0 │
├──────────────────┬───────────────┤      ├──────────────────────────────────┤
│ field            │ value         │      │ 06GKX34SBEKD749SN5JZKRYC10       │
├──────────────────┼───────────────┤      │ 06GKX34SBFPX9NHGTGKEDQ3XJC       │
│ answer           │ "No. The …"   │      │ …                                │
│ model_used       │ qwen3.5-2b    │      │ (no order, no duplicates)        │
│ entry_id         │ 06GKX34SBE…   │      └──────────────────────────────────┘
└──────────────────┴───────────────┘

ZSET  — one key, members sorted by score
┌──────────────────────────────────────────────────────┐
│ key  lru:entries                                     │
├───────────────────────┬──────────────────────────────┤
│ score                 │ member                       │
├───────────────────────┼──────────────────────────────┤
│ 1792050764123456789   │ 06GKX34SBEKD749SN5JZKRYC10   │  ◄ lowest score first
│ 1792050799000000000   │ 06GKX34SBFPX9NHGTGKEDQ3XJC   │
└───────────────────────┴──────────────────────────────┘

VECTOR INDEX  — watches every HASH under one prefix
idx:cache   ON HASH   PREFIX "t2:"
┌──────────────────┬──────────────────────────┬────────────────────────┬────────┐
│ key              │ embedding   VECTOR       │ namespace   TAG        │ lane   │
├──────────────────┼──────────────────────────┼────────────────────────┼────────┤
│ t2:06GKX34SBE…   │ [0.012, -0.044, … ×768]  │ product-headphones-03  │ SPEC   │
│ t2:06GKX34SBF…   │ [0.031,  0.007, … ×768]  │ policy-warranty        │ POLICY │
└──────────────────┴──────────────────────────┴────────────────────────┴────────┘
  query: "the 1 nearest embedding to mine, only where namespace = X"
```

---

## 3. Area 1 — the corpus (`corpus::{chunk_id}`, `idx:corpus`)

The corpus is the product specs and store policies the RAG service searches. Python writes it, once,
with `make ingest` (`rag/src/rag/ingest.py`).

### 3.1 From a JSON file to a Redis hash

```
data/dev-v0/product-headphones-03.json
      │  load_records(): doc_id must equal the file name; doc_id must start
      │  with "product-" or "policy-" (record_kind() refuses anything else)
      ▼
Document   text     = "Product: EarBuds Pop 3\nCategory: headphones\nSpecs:\n- type: …"
           metadata = { doc_id, kind, category, title }
      │  SentenceSplitter(chunk_size=256, chunk_overlap=40)
      ▼
chunks     id = "{doc_id}#chunk-{ordinal}"   e.g. product-headphones-03#chunk-0
           metadata += { chunk_id, ordinal, dataset_version = "dev-v0" }
      │  OllamaEmbedding: "search_document: " + text ─► nomic-embed-text ─► 768 floats
      ▼
RedisVectorStore ──HSET──► corpus::product-headphones-03#chunk-0     (HASH)
                                     │  key starts with "corpus:"
                                     ▼
                           idx:corpus indexes it automatically
```

A **product** becomes text as `Product: …` / `Category: …` / `Specs:` plus one line per spec. A
**policy** becomes its title, a blank line, and its text. In `dev-v0` every document is short, so
every document is exactly one chunk (`#chunk-0`).

In `v1` this is no longer true. Its 164 documents give **539 chunks**. Each of the 12 policy
documents is exactly **4 chunks** (48 in all), and the 152 products split into a median of 2 – 5
chunks, depending on the PQA leaf (`data-card.md` §1, §7). `v1` names look like
`product-electronics-b000tnfaq2` and `policy-return-phones-opened`.

**The `search_document: ` prefix** is a rule of the nomic model: stored text gets
`search_document: `, questions get `search_query: `. Skipping it does not fail. It only makes the
search quietly worse. Python and Go both add it.

### 3.2 One corpus hash, field by field

This is the real record from the live server:

```
KEY  corpus::product-headphones-03#chunk-0                                  HASH
┌─────────────────────────────────────────────────────────────────────────────┐
│ OUR FIELDS — declared in store.build_schema(), indexed by idx:corpus        │
│   id               product-headphones-03#chunk-0                 TAG        │
│   doc_id           product-headphones-03                         TAG        │
│   chunk_id         product-headphones-03#chunk-0                 TAG        │
│   ordinal          0                                             NUMERIC    │
│   kind             product                                       TAG        │
│   category         headphones                                    TAG        │
│   dataset_version  dev-v0                                        TAG        │
│   text             "Product: EarBuds Pop 3\nCategory: …"         TEXT       │
│   vector           <3072 bytes = 768 × float32>                  VECTOR     │
├─────────────────────────────────────────────────────────────────────────────┤
│ OUR FIELD — stored, not indexed                                             │
│   title            EarBuds Pop 3                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ LLAMAINDEX'S OWN FIELDS — bookkeeping, our code never reads them            │
│   document_id      product-headphones-03                                    │
│   ref_doc_id       product-headphones-03                                    │
│   _node_type       TextNode                                                 │
│   _node_content    {"id_": …, "metadata": {…}, "relationships": …}  ~1 KB   │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Field | Meaning |
| :--- | :--- |
| `id`, `chunk_id` | The chunk's stable name, `{doc_id}#chunk-{ordinal}` (`interfaces.md` §C). Both caches and invalidation refer to chunks by this name. |
| `doc_id` | The source document, e.g. `product-headphones-03`, `policy-warranty`. The prefix (`product-` / `policy-`) is the **only** place the kind is recorded, and the reuse rule reads it. |
| `ordinal` | The chunk's position in its document, from 0. |
| `kind` | `product` or `policy`, taken from the `doc_id` prefix. |
| `category` | In `dev-v0`: e.g. `headphones`, `laptops`, and empty for policies. In `v1`: the store department (`phones`, `laptops`, `electronics`, `furniture`), and a policy carries its department too (`policy-return-electronics` → `electronics`). |
| `dataset_version` | Which corpus build this is (`dev-v0` or `v1`). A re-chunk is a new version, never an in-place change. |
| `text` | The chunk text. This is what the LLM reads and what the support gate checks answers against. |
| `vector` | The chunk's embedding. Searched by KNN. |
| `title` | Display name. Stored, never searched. |
| `_node_content` etc. | LlamaIndex's own copy of the chunk, used when it rebuilds a chunk object after a search. |

### 3.3 The corpus index

```
INDEX  idx:corpus   ON HASH   PREFIX "corpus:"        (rag/src/rag/store.py)
  id               TAG
  doc_id           TAG
  text             TEXT
  vector           VECTOR   FLAT · FLOAT32 · DIM 768 · COSINE
  chunk_id         TAG
  ordinal          NUMERIC
  category         TAG
  kind             TAG      "product" | "policy"
  dataset_version  TAG
```

**The double colon.** The config says the prefix is `corpus:` (`config.py`), but LlamaIndex adds its
own `:` after it, so the real keys are `corpus::{chunk_id}`. The index prefix `corpus:` still matches
them. Any code that builds a corpus key by hand must use two colons, or it finds nothing and reports
no error (`retrieve.fetch_by_ids` does this correctly). The Go side writes `t2:` itself, with one
colon.

### 3.4 How the corpus is read

The corpus is read in two ways.

1. **Search (`Retrieve`).** The question becomes a vector (`search_query: ` prefix), then a KNN search
   on `idx:corpus` returns the **top 5** chunks (`TOP_K = 5`). If the request has a `product_id`, the
   chunks of *other* products are dropped **after** ranking, and if this product's own chunk is
   missing, one extra search filtered to `doc_id = product_id` adds it at the top
   (`retrieve.py:_drop_other_products`, `_ensure_own_chunk`).
2. **Fetch by ID (`Answer`, on a miss).** The gateway already has the 5 chunk IDs from step 1, so
   Python does not search again. It reads each chunk with
   `HMGET corpus::{chunk_id} text doc_id ordinal` (`retrieve.fetch_by_ids`). A missing chunk is
   dropped, never replaced.

---

## 4. Area 2a — Tier 1, the exact-match cache (`t1:{sha256}`)

Tier 1 answers a question that was **already asked in the same words**, for the same product. It is
one hash lookup: no vector, no similarity, no reuse rule.

### 4.1 How the key is built

```
question  "Does the EarBuds Pop 3 have ANC?"          product_id  "product-headphones-03"
      │                                                     │
      │ Normalize():  lowercase                             │
      │               remove punctuation and symbols        │
      │               collapse spaces, trim                 │
      ▼                                                     │
"does the earbuds pop 3 have anc"                           │
      │                                                     │
      └──────────────► join with one zero byte \x00 ◄───────┘

      "does the earbuds pop 3 have anc" + \x00 + "product-headphones-03"
                                  │
                                  │ sha256, written as 64 hex characters
                                  ▼
      t1:1f8fa611c1ed1e4df9715196eb6655811dc94a774927dded7a5c00767b76350b
```

(This key is real: it is what the code computes for this question and product.)

- `Normalize()` is `gateway/internal/cache/normalize.go`; the key is `cache.Key` in `key.go`. The
  same function runs when reading and when writing, so the two always agree.
- Punctuation is **removed**, not replaced by a space. So `Model A-1` and `Model A1` give the same
  key, and so do `don't` and `dont`.
- **`product_id` is part of the key.** The same question about two products gives two keys. A request
  with no `product_id` uses `""`, which is its own group: it never matches a product's key.
- **The `\x00` byte** separates the two parts. Without it, `"ab" + "c"` and `"a" + "bc"` would hash the
  same.

### 4.2 The Tier-1 hash

| Field | Example | Meaning |
| :--- | :--- | :--- |
| `answer` | `"No. The EarBuds Pop 3 do not have active noise cancellation."` | The generated answer text. |
| `source_chunk_ids` | `["product-headphones-03#chunk-0", …]` | A JSON array as one string: the chunks the answer was generated from. |
| `model_used` | `qwen3.5-2b` | The LLM id. |
| `created_at` | `2026-10-15T09:12:44Z` | Write time, RFC 3339, UTC. |
| `entry_id` | `06GKX34SBEKD749SN5JZKRYC10` | Links this record to its Tier-2 twin and to `lru:entries`. |

**Who writes it:** the miss write-back (`handler.go`, after generation), and the *promotion* after a
Tier-2 hit (§5.5). **Who reads it:** the first step of every request, with `HGETALL`.

**Tier 1 runs no rule, so its safety comes from the corpus.** Two questions with different correct
answers must never normalise to the same string. The corpus gate checks this before the corpus is
frozen (`interfaces.md` §D, `data-card.md` §7).

---

## 5. Area 2b — Tier 2, the semantic cache (`t2:{entry_id}`, `idx:cache`)

Tier 2 answers a question that **means** the same as an earlier one, even in other words. It finds the
nearest stored question by vector, and then the `reuse/` package decides whether its answer is safe to
serve. The `cache/` package only stores and finds candidates. It **never** decides reuse.

### 5.1 The `entry_id`

Each miss creates one new `entry_id`, a **ULID**: 26 characters, a millisecond timestamp followed by
random bits, e.g. `06GKX34SBEKD749SN5JZKRYC10` (`cache/entry_id.go`). The same id is used for the
Tier-1 record, the Tier-2 key, and the `lru:entries` member. Sharing one id is what lets eviction and
purge find both tiers.

### 5.2 The Tier-2 hash

| Field | Stored as | Indexed in `idx:cache` | Meaning |
| :--- | :--- | :--- | :--- |
| `embedding` | 3072 bytes | VECTOR | The vector of the question that caused the miss (`search_query: ` prefix). |
| `query_text` | string | TEXT | That question, as the user typed it (not normalised). |
| `answer` | string | — | The answer, same text as in Tier 1. |
| `source_chunk_ids` | JSON array string | — | **Provenance**: the chunks the answer was built from. The reuse rule compares them with what the *new* question retrieves. |
| `t1_key` | string | TAG | The full Tier-1 key written in the same miss, e.g. `t1:1f8fa611…`. |
| `dataset_epoch` | integer | NUMERIC | The corpus version when the answer was made: the epoch file's value (≥ 1) since item 4.2. |
| `namespace` | string | TAG | The partition this entry belongs to (§5.3). |
| `lane` | `SPEC` / `POLICY` / `MIXED` | TAG | The kind of question (§5.3). |
| `source_overlap` | float | — | Written as `0` and never updated (see §9). |
| `hit_count` | integer | — | Starts at 0, +1 on every Tier-2 hit (`HINCRBY`). Feeds the demo's "generations avoided" counter. |
| `created_at` | RFC 3339 | — | Write time, UTC. |

**Why `t1_key` matters.** The Tier-1 key is a hash of the question, so it **cannot be computed** from an
`entry_id`. Without this back-pointer, deleting an entry would remove `t2:` but leave its Tier-1 copy
serving the old answer. This is correctness invariant 2.

### 5.3 `lane` and `namespace` — how the cache is split into groups

Both values come from the **chunk IDs that retrieval returned**, never from the question text.

**Lane.** Count the share of retrieved chunk IDs that start with `policy-` (the *policy fraction*):

```
policy fraction = 0              ─► SPEC
policy fraction = 1              ─► POLICY
policy fraction ≥ Hi             ─► POLICY
Lo ≤ policy fraction < Hi        ─► MIXED
otherwise                        ─► SPEC
```

`Lo` and `Hi` default to `0.20` and `0.20`, so the MIXED band is empty and switched off by default
(`LANE_SIGMA`, `LANE_SIGMA_HI` in `main.go`).

**Namespace.** The group a question is searched in:

| Lane | Namespace | Example |
| :--- | :--- | :--- |
| SPEC | the request's `product_id`; if none, the `doc_id` of the first product chunk | `product-headphones-03` |
| POLICY | the `doc_id` of the **rank-1** policy chunk | `policy-returns-electronics` |
| MIXED | `{product}\|{policy}`, both needed | `product-headphones-03\|policy-warranty` |

An **empty** namespace never matches anything. It is not a wildcard.

The stored entry's lane and namespace come from **its own** `source_chunk_ids`, the chunks its answer
was built from. The incoming question's lane and namespace come from **its** retrieval. A hit needs
the two namespaces to be equal.

### 5.4 The cache index and the search

```
INDEX  idx:cache   ON HASH   PREFIX "t2:"          (gateway/internal/cache/tier2.go)
  embedding       VECTOR   FLAT · FLOAT32 · DIM 768 · COSINE
  query_text      TEXT
  t1_key          TAG
  dataset_epoch   NUMERIC
  namespace       TAG
  lane            TAG
```

Each Tier-2 lookup is **one** hybrid query, the nearest entry **inside the question's namespace**:

```
FT.SEARCH idx:cache
    "(@namespace:{product\-headphones\-03})=>[KNN 1 @embedding $vec AS dist]"
    PARAMS 2 vec <3072 bytes>   SORTBY dist ASC   LIMIT 0 1   DIALECT 2
    RETURN  every field except embedding
```

- **k = 1.** Only the single nearest entry in that namespace is judged.
- **`-` and `|` are escaped** with `\`. Unescaped, `product-headphones-03` is read as a negation and
  matches nothing, with no error.
- **`embedding` is not returned.** It would add ~3 KB to every lookup for nothing.
- The result's `dist` is cosine **distance**. Go computes **similarity = 1 − dist** and hands the
  candidate to `reuse/`, which decides.
- `namespace` and `lane` are **TAG**, not TEXT. TEXT would split `policy-returns-electronics` into
  words, and two different namespaces could match each other.

### 5.5 The two tiers together

Both tiers are written by **one** miss, with the **same** `entry_id` and the **same** answer:

```
┌─ t1:1f8fa611…350b ──────────────────────────── HASH ─┐
│ answer            "No. The EarBuds Pop 3 …"          │
│ source_chunk_ids  ["product-headphones-03#chunk-0"]  │
│ model_used        qwen3.5-2b                         │
│ created_at        2026-10-15T09:12:44Z               │
│ entry_id          06GKX34SBEKD749SN5JZKRYC10 ────────┼───┐
└──────────────────────────────────────────────────────┘   │
                         ▲                                 │ same entry_id
                         │ t1_key points back here         │
                         │                                 │
┌─ t2:06GKX34SBEKD749SN5JZKRYC10 ─────────────── HASH ─┐   │
│ (key = t2: + entry_id)                               │◄──┘
│ embedding         <768 × float32>              [VEC] │
│ query_text        "Does the EarBuds Pop 3…"    [TXT] │
│ answer            "No. The EarBuds Pop 3 …"          │
│ source_chunk_ids  ["product-headphones-03#chunk-0"] ─┼──► corpus::{chunk_id}
│ t1_key            t1:1f8fa611…350b             [TAG] │
│ dataset_epoch     1                            [NUM] │
│ namespace         product-headphones-03        [TAG] │
│ lane              SPEC                         [TAG] │
│ source_overlap    0                                  │
│ hit_count         0                                  │
│ created_at        2026-10-15T09:12:44Z               │
└──────────────────────────────────────────────────────┘
  [VEC] [TXT] [TAG] [NUM] = indexed by idx:cache

lru:entries (ZSET) also gets the member 06GKX34SBEKD749SN5JZKRYC10
```

**Promotion.** When Tier 2 serves a hit, the gateway also writes a **new Tier-1 record** for the exact
words of *this* question, pointing to the same `entry_id`. The next identical question then stops at
Tier 1 and skips the embed and the search. It runs in the background and never slows the hit. Its
weak point is in §9.

---

## 6. Area 2c — `lru:entries`, the eviction order

The cache has a fixed size: **`round(0.25 × K)` entries**, where `K` is the number of distinct
questions in the **run file**, the workload split the run uses (`interfaces.md` v0.15). The gateway
keeps this limit, not Redis.

- **What it is:** one ZSET. Member = `entry_id`. Score = time of the last access, in Unix
  **nanoseconds**. Lowest score = least recently used.
- **When it is written (`ZADD`):** on a Tier-1 hit, a Tier-2 hit, and a miss write-back.
- **When it exists:** **only if `CACHE_CAPACITY` is set above 0.** The default is `0`, which means
  "no limit". Then the gateway skips every `ZADD` and never trims, so you will **not see this key** in a
  normal `make dev` run.
- **The frozen values (2026-10-23, `data-card.md` §7):** `K` is 622 for the validation file and 652
  for the test file, so the capacity is **156** and **163** entries. The whole workload file (1,274)
  is the corpus gate's input, not a run file. The code still defaults to `0`: making each run set
  `CACHE_CAPACITY` from its run file's `K` is carried to P1.
- Its name has no `t1:`/`t2:` prefix on purpose: those prefixes are what the index and the purge scan.

**Trim**, after each miss write-back (`cache/capacity.go:TrimToCapacity`):

```
lru:entries   (ZSET, sorted by score = last access, Unix nanoseconds)

   score                    member (entry_id)
   1792050764123456789      06GKX34SBEKD749SN5JZKRYC10   ◄ oldest  ┐ victims
   1792050799000000000      06GKX34SBFPX9NHGTGKEDQ3XJC             ┘ (count − capacity)
   ──────────────────────────────────────────────────── cut here ────
   1792050812000000000      06GKX3B0…                              kept
   …
   1792062461314392064      06GKX9QZ…                    ◄ newest

1. ZCARD lru:entries                     how many entries?
2. ZRANGE lru:entries 0 (excess−1)       the oldest ones are the victims
3. for each victim:
     HGET t2:{id} t1_key                 find its Tier-1 key
     MULTI
       DEL  t2:{id}
       DEL  t1:{…}                       both tiers die together
       ZREM lru:entries {id}
     EXEC
```

Both tiers must go together. If only `t2:` were deleted, Tier 1 would keep serving the answer from a
plain hash lookup, and the capacity limit would measure nothing.

---

## 7. How one request touches Redis

Every `/ask` request goes down this path. Each arrow is labelled with the Redis command it sends.

```
POST /ask { question, product_id }
  │
  ▼
① TIER 1 ─── HGETALL t1:{sha256(normalize(q) \x00 product_id)}
  │      found ──► TIER1_HIT: return the stored answer
  │                ZADD lru:entries               (only if capacity is set)
  │ not found
  ▼
② IN PARALLEL
     embed the question       Ollama, "search_query: …"            no Redis
     Retrieve (Python)        FT.SEARCH idx:corpus  KNN 5   ─► 5 chunk IDs + texts
  │
  ▼
③ lane + namespace from the 5 chunk IDs                            no Redis, pure Go
  │
  ▼
④ TIER 2 ─── FT.SEARCH idx:cache "(@namespace:{ns})=>[KNN 1 …]"
  │      candidate passes the reuse rule ──► TIER2_HIT: return its answer
  │                HINCRBY t2:{id} hit_count 1        (background)
  │                ZADD lru:entries                   (only if capacity is set)
  │                HSET t1:{this question's key}      (promotion, background)
  │ no candidate, or refused
  ▼
⑤ MISS ─── wait for the one generation slot (admission);
           identical questions share one generation (coalescing)
     Python Answer:  HMGET corpus::{chunk_id} text doc_id ordinal  × 5
                     (reads by ID, no second search)
     the LLM writes the answer
  │
  ▼
⑥ WRITE-BACK  (new entry_id)
     HSET t1:{key}        answer, source_chunk_ids, model_used, created_at, entry_id
     HSET t2:{entry_id}   embedding, query_text, answer, source_chunk_ids, t1_key,
                          dataset_epoch, source_overlap, hit_count, created_at,
                          namespace, lane
     ZADD lru:entries     (if capacity set)
     trim                 ZCARD → ZRANGE → HGET → MULTI DEL DEL ZREM EXEC
  │
  ▼
MISS: return the new answer
```

Some details that matter:

- **A failed cache write never fails the request.** The answer is already generated, so it is served
  and the error is only logged. The same holds for `HINCRBY`, `ZADD` and promotion.
- **If the embedding or the retrieval fails, or retrieval returns no chunk,** Tier 2 is skipped and
  the request goes to the miss path.
- **If the embedding failed,** the write-back has no vector, so no `t2:` record is written. Tier 1
  still is.
- **If retrieval failed,** Python searches the corpus itself during `Answer`.
- **If the namespace is empty,** Tier 2 is not searched at all.

---

## 8. Area 3 — invalidation (built in item 4.1)

`gateway/internal/deps/` is the only code that writes `dep:*` and `entry:*`. One writer goroutine does
it, fed by one channel. What follows is what `interfaces.md` §E and ADR-008 require, as built. The epoch
guard is built in item 4.2 (below).

**`dep:{chunk_id}`** is a SET of every `entry_id` whose answer used that chunk — the
`source_chunk_ids` field, turned around. It is the "reverse index" that lets a chunk edit find every
answer built on it. After each write-back the gateway sends the entry to the writer, which adds the
`entry_id` to the SET of each of its source chunks.

**`entry:{entry_id}`** is a HASH with two fields: `t1_key` and `source_chunk_ids` (a JSON array). The
writer creates it in the same transaction as the `dep:` entries. It exists because a write-back with no
vector (the embedding failed) writes Tier 1 only. That entry has no `t2:` record to read `t1_key`
from, so without `entry:` its Tier-1 copy could not be purged. The Makefile counts it as a thesis key
(`demo-reset`), `make footprint` refuses to delete it, and a test checks that the trim never deletes
`dep:*` or `entry:*` keys (`capacity_test.go:TestEvictionLeavesDependencyRecordsAlone`). Only the purge
deletes them, so an evicted entry can stay listed in a `dep:` SET. Purging it later does nothing to the
tiers and removes its `entry:` record.

```
a chunk is edited:  policy-warranty#chunk-0        (Go call: Invalidate(event); item 4.4 sends it)
      │
      ▼
SMEMBERS dep:policy-warranty#chunk-0  ─►  { 06GKX34SBE…, 06GKX34SBF…, … }
      │
      ▼
the in-process snapshot now lists these entry_ids  ──  Invalidate returns here;
                                                       a hit on any of them is refused from now on
      │ for each entry_id
      ▼
HGET entry:{entry_id} t1_key  ─►  t1:1f8fa611…
      │
      ▼
one Lua script:  DEL t2:{entry_id}
                 DEL t1:1f8fa611…  only if its entry_id field is still this entry
                 ZREM lru:entries {entry_id}
      │
      ▼
DEL entry:{entry_id}          then, after all entries:  DEL dep:policy-warranty#chunk-0
                              "blind purge": every entry, no judgement

the epoch advances  —  one integer in a file outside Redis, NOT a Redis key (ADR-008)
a write-back whose dataset_epoch differs from the current epoch is discarded   (item 4.2)
```

**Why the Tier-1 delete is conditional.** Tier 1 is keyed by the normalised question. A newer entry for
the same question writes the same `t1:` key. A plain `DEL` from the older entry's purge would remove
the newer entry too. The Lua script compares the `entry_id` field and deletes only on a match, in one
step, so nothing can overwrite the key between the check and the delete.

**The in-process snapshot.** The writer keeps a copy-on-write set of invalidated `entry_id`s and swaps
it in **before** it deletes anything in Redis. A hit reads Redis first and checks the set second, so a
hit that could still see a purged entry also sees its tombstone. If a Redis call fails during a purge,
the failure is counted and logged and the tombstone stays: this process still refuses the entry, but a
restarted process would serve the leftover Redis copy.

**Why the epoch is not in Redis (ADR-008).** If Redis restarts from an old snapshot, the purged entries
come back **and** a Redis epoch counter goes back with them. The check then compares old with old,
agrees, and serves stale data. An epoch in a file outside Redis does not go back, so the mismatch
is seen. The epoch is one integer in the file named by `DATASET_EPOCH_FILE`. The RAG service reads it
first in each call and stamps it. The gateway reads it again at write-back, and discards the write-back on
any difference or read error. The dependency map's writer reads it once more at registration, so an edit
that lands between the write-back and the registration is caught too (item 4.2).

**The three correctness invariants**, all about Redis:

1. **`dep:*` and `entry:*` must never be evicted.** That is why Redis runs `noeviction` and the gateway
   does LRU itself (§1, §6).
2. **Every `t2:` record carries `t1_key`.** Otherwise purge and trim cannot find Tier 1 (§5.2).
   `entry:` carries it too, for the Tier-1-only entry.
3. **Write-back is guarded by the epoch.** Otherwise a generation still running during an edit writes
   the old answer back after the purge. Built in item 4.2.

---

## 9. Known gaps — where the code and the contract differ

1. **Tier-1 key includes `product_id`.** `interfaces.md` §D says `t1:{sha256(normalized_query)}`. The
   code adds `"\x00" + product_id` (a bypass from 2026-09-09). A superseding ADR is still owed
   (`cache/key.go`).
2. **`namespace` and `lane` are not in §D.** The code stores them on `t2:` and indexes them in
   `idx:cache` (`cache/tier2.go`).
3. **`source_overlap` is always 0.** §D calls it "last overlap score computed for this entry". The
   write-back never sets it and nothing updates it. The real overlap is in the evaluation log.
4. **Resolved in `interfaces.md` v0.18.** §E used to name a Redis key `dataset:epoch`, which ADR-008
   forbids. §E now names the epoch file (`DATASET_EPOCH_FILE`).
5. **Promoted Tier-1 keys are orphans.** `t1_key` holds one key, the one from the miss. A promoted key
   (§5.5) is not recorded anywhere, so trim and purge will not delete it. The hit path refuses it
   inside the same gateway process, because its record names the same `entry_id`; after a restart a
   leftover promoted key would serve. It is harmless while capacity is unbounded and must be fixed
   before capacity is bounded or a run restarts the gateway after an edit (item 4.3; `handler.go`, the
   comment above the promotion).

---

## 10. Glossary of thesis terms

| Term | Meaning |
| :--- | :--- |
| **chunk** | A piece of a source document. The unit that is embedded, searched and cited. |
| **`chunk_id`** | `{doc_id}#chunk-{ordinal}`, e.g. `policy-warranty#chunk-0`. Stable inside one dataset version. |
| **`doc_id`** | The source document's name. Starts with `product-` or `policy-`. Equals the JSON file name. |
| **`ordinal`** | A chunk's position in its document, from 0. |
| **`dataset_version`** | The corpus build (`dev-v0`, or the frozen `v1`). Changing the chunking means a new version. |
| **embedding** | A 768-number vector of a text, from `nomic-embed-text` via Ollama. |
| **`entry_id`** | The ULID of one cached answer. Shared by its `t1:` record, its `t2:` key and `lru:entries`. |
| **`t1_key`** | The Tier-1 key stored inside the Tier-2 record, so Tier 1 can be found from an `entry_id`. |
| **provenance / `source_chunk_ids`** | The chunks an answer was generated from. The core of the reuse rule and of invalidation. |
| **lane** | SPEC, POLICY or MIXED: the kind of question, from the policy fraction of its retrieved chunks. |
| **namespace** | The cache group a question is searched in: a product, a policy, or a pair. |
| **`dataset_epoch`** | The corpus version an answer was made under. Used to reject stale write-backs. The epoch file's value (≥ 1) since item 4.2. |
| **write-back** | Writing a new answer into both tiers after a miss. |
| **promotion** | After a Tier-2 hit, also writing a Tier-1 record for the exact words of that question. |
| **capacity, K** | Cache size = `round(0.25 × K)` entries; `K` = distinct questions in the run file: 622 (validation) or 652 (test), so 156 or 163 entries. |
| **τ (tau)** | The similarity threshold for Tier 2. Swept, never hand-set (demo default 0.85). |
| **θ (theta)** | The source-overlap threshold. Swept, never hand-set (demo default 0.60). |
| **support gate** | The check that a cached answer is supported by the new question's retrieved text (`τ_s = 0.6`). |
| **TIER1_HIT / TIER2_HIT / MISS** | Which path served the request. |

---

## 11. Look for yourself (read-only commands)

```sh
redis-cli CONFIG GET maxmemory-policy            # must say noeviction
make redis-check                                 # checks noeviction and maxmemory 0
redis-cli FT._LIST                               # which indexes exist
redis-cli FT.INFO idx:corpus                     # schema and num_docs
redis-cli --scan --pattern 'corpus::*' | wc -l   # how many chunks
redis-cli HMGET 'corpus::policy-warranty#chunk-0' doc_id kind text
redis-cli --scan --pattern 't1:*'                # Tier-1 keys
redis-cli --scan --pattern 't2:*'                # Tier-2 keys
redis-cli HMGET t2:<entry_id> query_text answer namespace lane t1_key hit_count
redis-cli ZRANGE lru:entries 0 -1 WITHSCORES     # empty unless CACHE_CAPACITY > 0
make corpus-index-check                          # is the index in Redis the v1 corpus on disk?
```

`HGETALL` on a `corpus::` or `t2:` key prints the vector as unreadable bytes. Use `HMGET` with field
names instead.

**Two ways to empty the cache, for two purposes** (run rule 11, `interfaces.md` §H v0.14, ADR-010):

| Purpose | Command | What it deletes |
| :--- | :--- | :--- |
| A measured run | `python3 experiments/scripts/loadgen_footprint.py flush-cache` | Only `t1:`, `t2:` and `lru:`. Never `corpus:`. It refuses to run while any `dep:` or `entry:` key exists. |
| A demo | `make demo-reset` | Everything (`FLUSHALL`). Then it restores `data/` from git and re-ingests the corpus. |

A measured run must **start with `t1:`, `t2:` and `lru:` empty**. Entries left by an earlier process
(for example, one that ran the gate-off arm) would otherwise be served under the wrong label.
Invariant I9 checks this from `raw/` alone, and a run that breaks it is not admissible. Once Phase 4
writes `dep:` records, the flush tool refuses every time, so **Phase 4 must define a new reset**.

**Do not run `FLUSHALL` or `FT.DROPINDEX` by hand.** For a demo, use `make demo-reset`, and stop the
gateway first. `FT.DROPINDEX` alone keeps the `t2:` hashes; when the gateway restarts it re-creates `idx:cache`,
which picks them up again, so a warm cache looks cold. `FLUSHALL` under a running gateway deletes
`idx:cache`, and new `t2:` records are then written into no index, so Tier 2 never hits and nothing
reports an error.
