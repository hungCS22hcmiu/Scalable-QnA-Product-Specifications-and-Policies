# Does Redis hold any state whose loss or rollback is not recoverable from the corpus of record, and can a Redis restart leave the system stale with every intra-Redis invariant still holding?

Opened 2026-10-10. Scope **S** — investigation, no code change. Prompted by the question "why is
there no database server, and what happens when Redis dies".

**This is not the active task.** `.claude/state/active-task` still points at
`2026-10-10-support-gate-lexical-arm` (scope L, implementation locked), which carries Phase 2's
exit criterion. This trail was opened alongside it deliberately and sets no `READY_TO_IMPLEMENT`.

## Conditions on everything below

- Config values were read from the **live `redis-stack-server`** on 2026-10-10 via `redis-cli
  CONFIG GET`. They are the state of this machine on that date, not a frozen decision.
- Corpus is **`dev-v0`**, which is **not citable in any result**.
- **No measurement run was taken.** No latency, throughput, hit-rate or memory-pressure number
  appears here, and nothing in this trail may be read as a result.
- Code findings are static reads of the working tree at `c3f0898`.

---

## F1 — Redis is not the store of record. The corpus files are.

`make ingest` chunks and embeds `data/$DATASET_VERSION/*.json` into Redis
([Makefile:54-55](../../../Makefile#L54-L55), `rag/src/rag/ingest.py:16`). Redis holds
`corpus::{chunk_id}` hashes carrying text plus a 768-dim FLAT vector
(`rag/src/rag/store.py:19-47`). That is **derived state**, reconstructible by re-ingest.

The store of record is `data/<dataset_version>/*.json` plus the frozen chunking config. For `v1` it
is the download-and-build script plus the hash manifest, since Amazon-PQA redistribution is not
granted.

So the premise "all documents live in Redis" is false. There is a store of record; it is a
versioned file corpus and a deterministic build step, which is the right shape for a frozen
research corpus — a `dataset_version` tag and a hash manifest give reproducibility that a mutable
RDBMS would undermine.

## F2 — DISPROVED (and confirmed by experiment): an RDB restart cannot lose `dep:*` while keeping `t2:*`

The hypothesis I opened this investigation with was: Redis restarts from a snapshot, cache entries
come back while dependency records written after the snapshot do not, and those entries become
permanently unpurgeable — correctness invariant 1 by a route eviction policy does not cover.

**That is wrong.** RDB is an atomic point-in-time snapshot of the **whole keyspace** (fork +
copy-on-write). A restore rolls `t1:*`, `t2:*`, `dep:*`, `lru:entries` and `corpus::*` back to the
*same* instant. An entry written after the snapshot is gone and so is its dependency record. The
reverse index stays consistent with the entries it indexes.

**Measured, not just reasoned** — see the experiment below. After a `kill -9` and restore, the
dependency set came back as `[entryA]`, consistent with the `t2:entryA` that came back with it. No
orphaned dependency record, no unpurgeable entry.

Recording this because the disproof is the useful half: **invariant 1 is not threatened by
restart.** It is threatened by eviction, which `make redis-check` already closes
([Makefile:61-73](../../../Makefile#L61-L73), verified live: `maxmemory-policy=noeviction`,
`maxmemory=0`).

## F3 — The real divergence is Redis against disk, not inside Redis

Live persistence configuration, 2026-10-10:

```
appendonly         no
appendfsync        everysec      (inert while appendonly=no)
save               3600 1   300 100   60 10000
dir                /opt/homebrew/var/db/redis-stack
dbfilename         dump.rdb
```

Snapshot-only. The write-loss window on an unclean stop is up to **1 hour** if ≥1 key changed,
**5 minutes** if ≥100 changed, **60 seconds** if ≥10 000 changed.

A rollback moves the Redis keyspace backwards. **It does not move `data/` backwards.** So consider
a source edit applied the way this system applies edits — edit the JSON, re-ingest — followed by a
crash before the next snapshot. After restore:

- `corpus::*` holds the **pre-edit** chunks,
- the cache holds **resurrected pre-edit** answers, including any the invalidator had already
  purged,
- `dep:*` is consistent with both,
- and `data/` on disk holds the **edited** corpus.

Every invariant checkable *within* Redis holds. Nothing errors. The cache is serving answers that
are correct with respect to the index and stale with respect to the corpus of record. The
invalidation that already fired has been silently undone.

This is a different and narrower failure than F2's, and it is real — **demonstrated below.**

## F4 — The epoch guard cannot catch F3 if the epoch lives in Redis. It is not built yet, which is the opportunity.

`dataset_epoch` is the designed defence against stale write-back (interfaces.md §E, invariant 3).
Today it is **a constant**: `DATASET_EPOCH_STUB = 0` (`rag/src/rag/config.py:34`), returned
unconditionally by retrieval, which documents itself as "a stub until W9-11"
(`rag/src/rag/retrieve.py:125`). The guard is therefore **not live**, and F3 is not reachable in
any run taken so far — there is no epoch to roll back.

The constraint this places on Phase 4, when `deps/` is built:

> **The epoch must be sourced from outside the Redis keyspace it guards.** If the counter is stored
> as a Redis key, an RDB rollback restores the stale entry *and* the epoch that would have rejected
> it, in the same consistent snapshot. The guard then agrees with the stale entry and invariant 3
> fails silently — exactly the failure mode it exists to close. Deriving it from the corpus manifest
> hash, or from a file written by the ingest step, makes the comparison cross-medium and therefore
> able to detect the rollback.

This is the finding worth having, and the experiment below **demonstrates the exact mechanism**:
with the epoch held as a Redis key, the rollback restored `t2:entryA` (stale, purged before the
crash) *and* reset `epoch_counter` from 8 back to 7 — the same value stamped on the resurrected
entry. The guard compares 7 against 7, agrees, and admits the stale entry. Had the epoch been read
from the corpus manifest on disk it would still have read 8, and the mismatch would have been
visible.

It costs nothing to honour now because `gateway/internal/deps/` is still a one-line stub; it would
be expensive to retrofit after Phase 4 ships.

## F5 — Tier 1 is the only Redis-touching path that does not degrade

Every other path treats an unavailable dependency as a cost in hit rate, not availability:
Tier-2 search ([cascade.go:73](../../../gateway/internal/httpapi/cascade.go#L73),
[cascade.go:106](../../../gateway/internal/httpapi/cascade.go#L106)), embed and retrieve
([handler.go:249-263](../../../gateway/internal/httpapi/handler.go#L249-L263)), the catalogue
([browse.go:118](../../../gateway/internal/httpapi/browse.go#L118)).

Tier 1 returns 500 and bails:

```go
entry, hit, err := h.Cache.Get(ctx, req.Question, req.ProductID)
timings.Tier1 = time.Since(t1Start)
if err != nil {
    http.Error(w, "cache lookup failed: "+err.Error(), http.StatusInternalServerError)
    return
}
```
[handler.go:195-199](../../../gateway/internal/httpapi/handler.go#L195-L199)

Two consequences. **Availability:** Redis unreachable means every request 500s at Tier 1, in a
system that has the degradation discipline everywhere else. *(Corrected by F11: fixing this does not
restore service. The miss path retrieves from the same Redis, so the request fails at `Answer`
instead. The fix corrects the label; it does not restore availability.)* **Measurement:** that path returns before
`rec.Cache` is assigned, so the deferred emit writes `cache: ""`. There is no enum value for it —
[types.go:70-76](../../../gateway/internal/httpapi/types.go#L70-L76) defines `SHED`, `ABANDONED`
and `GENERATION_FAILED` precisely because "leaving them blank would make them indistinguishable
from a lost record", and interfaces.md §H rule 4 names "a Tier-1 lookup error" as a non-serving
outcome without giving it a value.

**Deferred, not fixed here.** The fix adds a value to the eval log's `cache` enum — interfaces.md
§A and §H, a frozen contract — and Phase 2 is **currently writing** per-request cause codes through
that same log. Changing the enum mid-phase breaks comparability between records written before and
after. Open as `/bugfix`, scope **L**, after Phase 2 closes, citing this trail.

## F6 — EXPECTED A GAP, FOUND ONE ALREADY TRACKED

I expected to find that run records capture no Redis identity, making a mid-run restart
undetectable after the fact. They do not capture it — but this is not a new finding: the
**run-manifest schema does not exist anywhere**, which is open problem **P1**
(`decisions.md:78`). A Redis identity field (`rdb_last_save_time`, `redis_version`) belongs in
P1's schema when it is written. Folding it there; no separate item.

## F7 — Cache memory does not grow with the corpus. The index does.

Capacity is `round(0.25 × K)` where `K` is the frozen workload's **distinct-query count** — a count
of entries, explicitly not a byte budget (interfaces.md §D). It is independent of corpus size: a
1 TB corpus with the same query distribution gets the same cache. The "bottleneck moves to RAM"
concern does not apply to the tier the load-conversion claim rests on.

What does grow linearly is the retrieval index, and **FLAT is an exact brute-force scan** — every
vector resident, O(N) per query. That is the component that does not survive TB scale, and it is
out of scope by two separate decisions: scale-out and scale-up (Final_Proposal §12), and HNSW as "a
scaling path never enabled mid-study" (§7), the latter for determinism rather than for capacity.

Worth stating in the write-up, because it is the actual defence and it is currently unstated: the
retrieval index is **the same component in every one of the five configurations**, so its cost
cancels out of the comparison. The claim is load conversion within a fixed envelope; it is not a
claim that the envelope scales.

Corollary from the live config: `maxmemory=0` with `noeviction` means Redis grows until the OS
kills it. The gateway's count-based trim is the **only** bound on cache size. That is by design
(interfaces.md §D) and is correct for the experiment, but it means a mis-derived `K` is an OOM
rather than a degradation.

## F8 — Retrieval is dense-only, and that conditions C1 specifically

`BM25`, `hybrid`, `sparse`, `rerank`, `cross-encoder`, `RRF`, `fusion` — **0 occurrences** across
`Final_Proposal.md`, `super-plan.md` and `contracts/interfaces.md`. Retrieval is dense top-k over a
FLAT index. Industry practice is hybrid dense+sparse fused by RRF, with a cross-encoder rerank on
≤50 candidates.

This does **not** confound the systems claim: `retrieve(q)` is identical across all five
configurations, so retrieval quality cancels.

It **does** condition C1, whose signal *is* `retrieve(q)`'s output —
`overlap(retrieve(q), sources(e)) ≥ θ` is a set operation over whatever chunks the retriever
returns. A dense-only top-k retriever returns a different-quality set than the hybrid+rerank stack
a production system would run, so the containment signal is measured over a different input than
it would see in deployment. The FLAT freeze addresses determinism and says nothing about recall.

**Do not build hybrid retrieval.** It changes a measured path (scope L) and voids prior runs, for a
quality improvement this thesis does not claim. This is a limitation paragraph, not a task.

## F9 — RESOLVED: one related-work row is missing, and it is a close neighbour

`Final_Proposal.md` §10's matrix is more complete than I assumed. FreshCache [12] is already
present and verified 2026-09-21, with a worked differentiation (probabilistic risk over
uncontrolled web sources vs. exact dependency purge over an operator-owned corpus). No gap there.
Note that CLAUDE.md's summary "two 2026 systems" is stale relative to §10, which maps four.

**Category-Aware Semantic Caching for Heterogeneous LLM Workloads** (arXiv 2510.26835, Nov 2025)
applies **per-category similarity thresholds** in place of one global τ. `category-aware` = 0
occurrences in the docs. That is one reading away from this system's namespace partition plus lane
band, so the matrix either needs a row or needs a recorded reason for excluding it. It predates the
2026-09-21 sweep, so it was either judged outside the neighbourhood or missed.

**RESOLVED 2026-10-10** from the arXiv abstract page (the PDF stays unreadable on this machine —
no `poppler`, no `pypdf`, and the Read tool needs `pdftoppm`; the abstract page was enough).
Wang, Liu, Zhu, Youssef, Nagpurkar, Chen; submitted 29 Oct 2025. Verbatim claims that matter:

- Policy is **per-category similarity thresholds, TTLs and quotas**, where the category is inferred
  from the query — "fixed thresholds cause false positives in dense spaces and miss valid
  paraphrases in sparse spaces". That is the same defect this thesis attributes to a single global
  τ, reached from **embedding-space density** rather than from provenance.
- Architecture is "a hybrid architecture separating in-memory HNSW search from external document
  storage, reducing miss cost from 30ms to 2ms". **This is the industry answer to the question that
  opened this investigation** — vector search in memory, documents in a separate store — and it is
  worth citing for exactly that reason.
- Reported hit rates: "40-60%" for high-repetition categories, "5-15%" for low-repetition or
  volatile ones. Break-even moves from 15–20 % to 3–5 % under their architecture.
- Load-responsive arm: thresholds and TTLs adjust to downstream model load, "reduce traffic to
  overloaded models by 9-17% **in theoretical projections**."

**Verdict: it needs a row in §10, and the differentiation is clean.** Two separations hold. (i) Its
signal is the **query's** category and the embedding space's local density — a property of the
query, not of what the cached answer was grounded in. This thesis's rule "must never read the query
text as a *predictive* signal" (CLAUDE.md), so the two occupy different signals even though they
diagnose the same failure of global τ. (ii) Its load-responsive arm is the one component that
overlaps the systems contribution, and it is **projected, not measured** — which is the
differentiator rather than a threat, since Phase 7 measures.

One caveat to carry into the row: the paper's per-category thresholds are a **nearer neighbour to
the lane band than anything currently in the matrix**. The row should say so plainly rather than
file it under fixed-threshold caches.

## F10 — The persistence posture is a vendor default in an upgrade-volatile path, and no decision records it

The settings in F3 are not a project choice. The running server reports:

```
redis_version   7.4.7
executable      /opt/homebrew/Caskroom/redis-stack-server/7.4.0-v8/bin/redis-server
config_file     /opt/homebrew/Caskroom/redis-stack-server/7.4.0-v8/etc/redis-stack.conf
```

Three consequences, in order of how much they matter:

1. **`appendonly no` and the `save` thresholds are the cask's shipped defaults.** No ADR mentions
   persistence; nobody chose this. F3's rollback window exists by default, not by decision.
2. **The config file lives inside a version-pinned Caskroom directory.** A `brew upgrade` of the
   cask replaces `7.4.0-v8/` wholesale, so any persistence tuning written there is silently
   discarded on upgrade — the same shape of failure as the Ollama auto-update that CLAUDE.md
   already pins off, and it would not announce itself.
3. **The LaunchAgent passes no config argument at all** (`ProgramArguments` is just the binary), so
   which config file is in force is an artefact of the cask's layout rather than anything this
   repository states.

This is RR-shaped, not NFR-shaped: it does not make the system visibly worse, it makes a run's
storage posture unrecorded and mutable by an unrelated `brew upgrade`.

## F11 — CORRECTION: total loss of Redis is an outage, not the no-cache arm

Found on 2026-10-10, while answering a follow-up question. By then ADR-007 and `drafts.md` §14 had
already been written with the wrong claim. Both are now corrected in place and marked as corrected.

**The wrong claim:** "total loss of Redis costs hit rate and nothing else: `h → 0`, `λ_max → μ_gen`,
which is the no-cache configuration, a measured arm rather than an outage." That holds only for the
**cache keys** (`t1:*`, `t2:*`, `dep:*`, `lru:entries`). The no-cache arm still **retrieves**, and the
retrieval index (`idx:corpus` and `corpus::*`) lives in the **same Redis process**:

- Python `Answer` reads Redis on both of its branches: `retrieve.fetch_by_ids` when the gateway has
  already retrieved, and `retrieve.retrieve` otherwise
  ([server.py:36-40](../../../rag/src/rag/server.py#L36-L40),
  [retrieve.py:44](../../../rag/src/rag/retrieve.py#L44)).
- The gateway turns an `Answer` error into `GENERATION_FAILED` and a 502
  ([handler.go:522-525](../../../gateway/internal/httpapi/handler.go#L522-L525)).

So with Redis **down**, every request fails, and fixing F5 would not change that. The fix only moves
the failure from a Tier-1 500 to a miss-path 502, with a correct label instead of a blank one. With
Redis **emptied** (a restart without the RDB), the index definition is gone as well, and nothing is
served until `make ingest` rebuilds it. That rebuild needs the embedding model, so it also needs a
memory-pressure check first.

**What still stands:** nothing is *lost*. Every key is derived (F1), and the LaunchAgent restarts the
process because `KeepAlive` is `true` (live reading, 2026-10-10). Redis is a single point of failure
for **availability**, not for **durability**.

**What a database server would do about it: nothing.** A store of record solves durability, and F1
shows durability is not the problem. Moving retrieval into Postgres/pgvector would only make Postgres
the single point of failure for retrieval instead. Splitting the cache and the index into separate
processes would let a *cache* failure degrade to the no-cache arm (once F5 is fixed), but the index
store would still be a single point of failure. Availability needs replicas and failover, which is
scale-out and out of scope (Final_Proposal §12). So this corrects ADR-007's **rationale**. It does
not change ADR-007's **decision**.

**Conditions:** established by reading the code, not demonstrated. The project's Redis on 6379 was not
stopped to show it, because a refused connection leaves nothing in doubt. Live footprint, for scale:
`dev-v0` is 44 chunks and `used_memory` is 5.88 MB. Of that, `vector_index_sz_mb` is 3.01, which
matches one preallocated FLAT block (1024 vectors × 3,072 B = 3.0 MiB). None of this is citable, and it
supports no extrapolation beyond "tiny".

## Evidence — the RDB rollback experiment

Script: [`rdb-rollback.sh`](rdb-rollback.sh), re-runnable. **Isolated instance on port 6399**, its
own `--dir` in the session scratchpad, `--save ''` so every snapshot is explicit and the timeline is
controlled. The project's Redis on 6379 was not touched, and the script verifies it is still up at
teardown. No corpus, no models, no measurement — this is a mechanism check, and **no number in it is
a performance result.**

Timeline: write entry A + its dep record + the corpus chunk + `epoch_counter=7` → `SAVE` → then,
*after* the snapshot, simulate an edit: `epoch_counter=8`, corpus text edited, entry A purged, dep
record updated, entry B written → `kill -9` → restart from `t.rdb`.

| key | before crash | after restart |
| :--- | :--- | :--- |
| `t2:entryA` (purged before the crash) | absent | **present again** |
| `t2:entryB` (written after the snapshot) | present | absent |
| `epoch_counter` | 8 | **7** |
| `corpus::policy-returns#chunk-0` | "EDITED corpus text" | "pre-edit corpus text" |
| `dep:policy-returns#chunk-0` | `[entryB]` | `[entryA]` |
| `t2:entryA.dataset_epoch` | — | 7 |

**What it shows.** The purge was silently undone. The dependency set is self-consistent with the
entry that came back, so F2's hypothesis is dead. And the epoch that was supposed to reject the
stale entry **rolled back to the same value stamped on it** — 7 against 7, agreement, admitted.
Every invariant checkable inside Redis holds; the staleness is only visible from outside, against
`data/`, which does not roll back.

---

## Answer

**Yes to the second half of the question, no to the first.** Nothing in Redis is unrecoverable —
every key is either derived from the corpus of record (F1) or is cache state whose loss costs hit
rate and nothing else. But a Redis restart **can** leave the system stale with every intra-Redis
invariant holding (F3), because the rollback is cross-medium: the keyspace moves backwards and
`data/` does not. The mechanism designed to catch that, the epoch guard, is a stub today (F4) and
will only catch it if the epoch is stored outside the keyspace it guards.

The original hypothesis — partial recovery breaking invariant 1 — is **disproved** (F2), and both
the disproof and the real failure are **demonstrated on an isolated instance**, not merely argued.

The posture that produces F3 is a **vendor default no decision records**, in a path a `brew upgrade`
silently replaces (F10).

**Nothing is lost, but everything stops** (F11, a correction to this trail's own first draft). The
corpus index shares the Redis process with the cache. Redis down is therefore an outage, not the
no-cache arm. Redis is a single point of failure for availability, not for durability, and a database
server would not change that.

## What it changes

| # | Change | Where | Status |
| :-- | :--- | :--- | :--- |
| 1 | ADR: **no separate datastore**; Redis holds derived state only; the corpus of record is the versioned file corpus. Record the reason (a second store on the measured path adds latency components and consumes the binding memory envelope, and moves neither C1 nor C2) | `decisions.md` | ✅ **ADR-007** |
| 2 | **Phase 4 design constraint (F4):** the dataset epoch must be sourced from outside the Redis keyspace, or invariant 3 fails silently after an RDB rollback | `decisions.md` + interfaces.md §E | ✅ **ADR-008** — the load-bearing outcome |
| 3 | Limitation: cache memory is bounded by `K` and independent of corpus size; the retrieval index is linear and FLAT is O(N); it is identical across all five configurations and therefore cancels (F7) | Final_Proposal §9.4 | drafted — `drafts.md` §1 |
| 4 | Limitation: Redis/disk rollback window under snapshot-only persistence (F3) | Final_Proposal §9.4 | drafted — `drafts.md` §1 |
| 5 | Limitation: containment is measured over a dense-only top-k retriever (F8) | Final_Proposal §9.4 | drafted — `drafts.md` §1 |
| 6 | `/bugfix` scope **L**: Tier-1 degrade-to-MISS + an enum value for a lookup error (F5) | `httpapi/`, interfaces.md §A/§H | **deferred until Phase 2 closes** |
| 7 | **Add** the Category-Aware row (F9) — nearer to the lane band than any current row; differentiate on signal (query-category density vs. retrieval provenance) and on measured-vs-projected for its load-responsive arm. Also worth citing for its in-memory-HNSW / external-document-store split, which is the industry answer to this trail's opening question | Final_Proposal §10 | drafted — `drafts.md` §2 (row + prose + ref [13]) |
| 8 | Redis identity fields in the run manifest (F6) | P1's schema | folded into P1, no separate item |
| 9 | ADR or RR: **record the Redis persistence posture** and move the config out of the Caskroom path, or state that the default is accepted. Currently unrecorded and `brew upgrade`-volatile (F10) | `decisions.md` / `requirements.md` RR | ✅ folded into **ADR-007** Consequences |
| 10 | Fix CLAUDE.md's stale "two 2026 systems" — §10 maps four, soon five (F9) | `CLAUDE.md` | drafted — `drafts.md` §3 |
| 11 | **Correct** the "total loss degrades to the no-cache arm" claim: it is an outage, because the index shares the process (F11). The decision stands; the rationale changes | ADR-007 + `drafts.md` §14 | ✅ corrected in place, marked as corrected |

Items 3–5 and 7 are prose in a gitignored document. Items 1–2 and 9 touch `decisions.md`, which is a
frozen-value authority — per CLAUDE.md they must state what they invalidate. **They invalidate
nothing**: no measured run exists that depends on the epoch (it is a stub, `DATASET_EPOCH_STUB = 0`),
and no run depends on Redis persistence configuration, which until now was unrecorded.

**Nothing in this trail is a result.** Corpus is `dev-v0`; the only experiment ran on a throwaway
instance with six synthetic keys and measured no latency, throughput or hit rate.

## Still open

- **Item 6** (Tier-1 degrade-to-MISS) is deliberately deferred until Phase 2 closes — see F5 for why
  the eval-log enum must not move mid-phase. Open it as `/bugfix`, scope **L**, citing this trail.
- **Items 3–5, 7, 10** are written as ready-to-paste text in [`drafts.md`](drafts.md) and **not
  applied**: `Final_Proposal.md` is submitted prose and `CLAUDE.md` is the project's instruction
  file. Both are the author's to edit.
- **ADR-007 carries one open item:** P1's run manifest must record `redis_version` and
  `rdb_last_save_time`, without which the restart-voids-a-run rule cannot be checked from `raw/`.
  That is P1's to close, not this trail's.

## Closed

Items 1, 2 and 9 are in `decisions.md` as **ADR-007** and **ADR-008**, each with an `Invalidates:`
line reading `none — no runs yet` and the reason it is true. No source file was touched; no
`READY_TO_IMPLEMENT` was written.
