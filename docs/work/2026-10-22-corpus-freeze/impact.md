# Impact — corpus-freeze (item 3.6)

**Analyst:** the `impact-analyst` subagent, 2026-10-22, working from `spec.md` draft 1. It changed no
file except this one and ran no Ollama, ingest or Redis-writing command. Redis was read only
(`FT.INFO`, `--scan`, one `HGET`).

## Verdict

**The gate hashes the files but measures whatever is in Redis, and nothing checks that the two are
the same corpus.** The digest is over `data/v1/*.json` and the three workload files only
(`corpus_gate.py:867-892`). Stage 2 calls `rag.retrieve` on the live index (`corpus_gate.py:998-1012`).
With the proposed env override (default `dev-v0`), one forgotten `DATASET_VERSION=v1` gives G1 and G2
from the 44-chunk dev-v0 index printed next to a v1 digest. Scoped retrieval would then return only
dev-v0 policy chunks for most queries, so S4 ("retrieves nothing") fires for some queries, not all.
**Fix: one additive check in stage 2** (below, A).

**Second: the spec's freeze record would put asins in a tracked file.** The gate's `--report` lists
every file path (`corpus_gate.py:1091`), and 152 product file names hold the asin. The repo's rule is
"no asin in a tracked file" (`architecture.md:117-118`, `data-card.md:223-224`).

The item changes **no existing frozen value**. It *creates* frozen values (`v1`, its digest, `K` and
capacity per run file, the chunk digest), so it needs a numbered ADR. It invalidates nothing:
`experiments/results/` holds only `.gitkeep`, and Redis holds no cache key (verified). **The
experiment phase is required. The contract phase is not.**

## Packages touched

| Path | Change |
| :--- | :--- |
| `rag/src/rag/config.py:19` | `DATASET_VERSION` from the environment, default `dev-v0` (one line) |
| `rag/src/rag/ingest.py:77-90` | optional: move the split loop into one function, for the chunk digest (R11) |
| `experiments/scripts/corpus_gate.py` | additive only: index check (A), per-query export (B). No threshold edit |
| `experiments/scripts/<new freeze script>`, `experiments/tests/` | new: assemble, freeze record, verify. Tests: additions only |
| `Makefile` | new targets (assemble, `corpus-verify`); `ingest` pass-through; `demo-reset` pins `dev-v0` |
| `data/v1/` (ignored, 164 files), `data/v1-freeze.json` (tracked, new) | new |
| docs | `data-card.md` (10 markers, header, §7), `decisions.md` ADR-014, `architecture.md:106-107, :116-118, :229, :248`, `super-plan.md`, `README.md:205`, `evidence/` |
| not touched | `gateway/` (all), `contracts/`, the `.proto`, `reuse/`, `ui/`, `k6/`, `DATASET_EPOCH_STUB`, `CLAUDE.md`, `Final_Proposal.md` |

**Layering is fine.** `experiments/scripts/` is where corpus tools live (`architecture.md:82-87`).
Scripts already import `rag`, lazily and one way: `corpus_gate.py:998-999`, `select_pqa.py:548`,
`check_policies.py:229`. Nothing in `rag/` imports `experiments/` (checked). Two rules for the new
code: `rag/` must never import the freeze script (for example to check the digest inside `ingest`),
and the freeze script imports `corpus_gate.freeze_files` and `snapshot_digest`, never a copy of
them. `corpus_gate` must not import the new script (no cycle). `data/v1-freeze.json` sits beside the
other tracked manifests; add it to the tree in `architecture.md:116-118`.

## 1. What reads `DATASET_VERSION`, and what needs `dev-v0` (spec open question 1)

**Readers of the constant.** Only `rag.ingest`: `DATA_DIR` at import (`ingest.py:16`) and the chunk
tag `dataset_version` (`ingest.py:87`, schema field `store.py:45`). `retrieve`, `server`, `cli` and
the gateway never read it. **They serve whatever Redis holds.** So the default only decides what
`make ingest` and `make demo-reset` load.

**Things that silently assume the dev-v0 index:**

| Thing | Evidence | On a v1 index |
| :--- | :--- | :--- |
| rag live tests, run by `make test` / `make verify` | `test_retrieve_scoping.py:18-29` skips only if Redis is down; `:84`, `:108` need `product-kitchen-*` | **fail** (loud). With Ollama down they error |
| `make seam-check` | `seam_live_test.go:44-45` (`product-laptops-02`) | fail (loud) |
| `make support-check` | `support_live_test.go:58, :79-85` (dev-v0 chunk hashes) | fail (loud) |
| `make demo` | `Makefile:219-221` (headphones/sofa questions); `:227-232` checks a cold cache, **not the corpus** | runs, proves nothing (**silent**) |
| `make demo-reset` | `Makefile:187-200`: restores `data/dev-v0/`, `FLUSHALL`, then `make ingest` | loads whatever the default/env says |
| `verify_admission.sh` | `:30-31` dev-v0 product ids | scopes to products that do not exist (silent, minor) |
| Go `reuse/` tests | fixtures copied from dev-v0 text (`support_test.go:11`) | unaffected (no live index) |
| `make dev`, `measure`, `catalog/`, UI | version-blind | serve v1 |
| docs | `CLAUDE.md:53`, `README.md:205`, `ingest.py:1`, `data-card.md:14` | wrong after a flip |

**(a) Env override, default `dev-v0`.** Nothing that works today moves. Two traps. First, a
forgotten override ingests dev-v0 and the gate measures it (Verdict). Second, a shell with
`export DATASET_VERSION=v1` leaks into `make demo-reset` (`Makefile:200` calls `make ingest`), and the
demo then runs on v1 with no error.

**(b) Flip the default to `v1`.** `make ingest` and `make demo-reset` load v1. The demo then runs on
v1 with no error. seam-check, support-check and `make verify` fail until someone re-ingests dev-v0 by
hand. `data/v1/` is gitignored, so on a fresh clone `make ingest` stops loudly (`ingest.py:34-35`).

**Recommendation: (a)**, with three guards. (1) Stage 2 checks the index (A below), so the default
cannot decide the result. (2) `demo-reset` passes `DATASET_VERSION=dev-v0` explicitly. (3) **Do not
wire `ingest` to Make's `VERSION`.** `VERSION ?= v1` is global (`Makefile:411`), so that would silently
make `make ingest` and `make demo-reset` load v1, which is option (b) by accident. Leave the default
flip to the task that ports the live checks or retires dev-v0. Note that `data-card.md:14` says dev-v0
is "discarded after W8". That line is now wrong: four checks and the demo still need dev-v0. Record
this. Do not act on it here.

## 2. Redis when `v1` is ingested over `dev-v0`

`ingest.py:94` → `store.get_vector_store(overwrite=True)` → `create(overwrite=True, drop=True)`
(installed `llama_index/vector_stores/redis/base.py:288-289`, version 0.8.0) → `FT.DROPINDEX idx:corpus DD`. This
deletes the index **and** every `corpus::*` hash it indexed (44 today). Then v1 is written.
**`idx:cache`, `t1:`, `t2:`, `lru:`, `dep:` and `entry:` are not touched** (other prefix, other index).
They are all empty today. The gate never reads the cache, so the cache cannot affect the freeze.
Before any later `make dev` on v1, rule 11's `flush-cache` still applies.

**Re-ingest of dev-v0 is needed afterwards for:** `make verify` (A9 fails without it, R3),
`make seam-check`, `make support-check`, `verify_admission.sh`. `make demo` is fine only through
`make demo-reset`. Re-ingesting dev-v0 is one more Ollama command (embedding model only), under green.

## 3. Frozen values and invalidation

- **Existing frozen values:** none changed. `num_ctx`, `OLLAMA_NUM_PARALLEL`, embedding model, `DIM`,
  `top_k` 5, chunking 256/40, FLAT, `noeviction`, ratio 0.25 and δ are all untouched.
- **New frozen values:** `dataset_version = v1`, its snapshot digest, `K` 622/652 and capacity 156/163,
  the chunk digest and the `llama-index-core` version, the hash of the numeric unit list, and the
  §7 statistics. **ADR required: ADR-014 (data), "v1 is frozen".**
- **Invalidates: none — no runs yet.** `experiments/results/` holds only `.gitkeep`. Redis has 0
  `t1:`/`t2:`/`lru:` keys. dev-v0 numbers (lane band, demo margin) are not runs and not citable.
- **Binds forward (needs a new `dataset_version` and a new gate run):** any byte of the 164 corpus
  files or the 3 workload files; the chunk size or overlap; the text format (`ingest.py:47-70`); a
  `llama-index-core` change that moves a chunk (the chunk digest shows it); the embedding model or its
  prefixes (`embedding.py:53-67`); `top_k`; **the scoped-retrieval code** (`retrieve.py:77-132`).
  A "faster scoped retriever" must return the same ids in the same order, and it must be checked
  against the exported per-query sets. Also ADR-013's list (`decisions.md:1307-1309`), the gate's
  constants (`corpus_gate.py:81-84, :102`), and the unit list (`support_numeric.go:21` already asks
  for an ADR).

## 4. Dropped scope

None. Nothing here touches the bypass classifier, the learned predictor, predictor-gated
invalidation, semantic routing, SSE or HNSW (`Final_Proposal.md:599`). Retrieval stays FLAT.

## 5. New dependency

None. The gate stays numpy-free (`corpus_gate.py:677`). ADR-012 says "pin `llama-index-core`". A pin
in `rag/pyproject.toml` (`>=0.11` today) is a change to a dependency spec, not a new package (0 MB;
0.14.23 is installed). **It still needs the author's sign-off.** The smaller option: record the
version in the freeze record and have `corpus-verify` fail when the installed version differs.

## 6. Contract

**No contract change. The contract phase is not required.** §B and the `.proto` are unchanged. §C:
v1 is a content expansion under a new `dataset_version` (`interfaces.md:363, :369`). §D v0.15
already says the absolute capacity "is derived at corpus freeze for each file, as the integer the gate
prints" (`:375`). The numbers go into `data-card.md`, not into §D.

**`DATASET_EPOCH_STUB = 0` (`config.py:34`):** no functional interaction today. Write-back never
compares it (`architecture.md:205-208`), and the gate never uses the cache. One effect to record:
epoch 0 now labels two different corpora, so `dataset_epoch_at_retrieval` cannot tell dev-v0 from
v1 in a log. Only a run manifest's `dataset_version` can (P1). ADR-008 says the epoch comes "from
the corpus of record" (`decisions.md:789-791`). The freeze record is a good future source for it.
**Do not wire it here:** that changes §B/§E behaviour and is Phase 4's design. (`interfaces.md:461`
still says the epoch is held in Redis, which ADR-008 forbids. That is also Phase 4's to fix.)

## 7. Measurement — the experiment phase is required

The gate run **is** the measurement that fixes the corpus statistics, and the carried counts
(U10 – U12, the sibling-chunk rate) are new counts whose rules are not written yet. Things to fix
before the first run on v1:

- Thresholds stay: 0.85, 0.2, 50, 0.25 (`corpus_gate.py:81-84`) and `CONDITION_AXES` (`:102`).
  Edits to `corpus_gate.py` are additive and tested. No existing test changes.
- **Does run 2 re-ingest?** Decide now (R6).
- **U11:** what "the evidence span's chunk" is when a span crosses two chunks (overlap 40).
- **U10 and the sibling rate read validation only.** The lane band is "swept, never hand-set"
  (`reuse/lane.go:94-95`). A test-split `policy_frac` table that a later task reads to pick the band
  is tuning on test. G1/G2 stay per split, as ADR-013 requires.
- Evidence holds counts only: no `qa_id`, no asin, no question (the gate prints `qa_id`s on a warning,
  `corpus_gate.py:1016`).

## 8. Spec claims, checked

- **13 `TODO(W8)`, ten this item's:** correct. Lines 23, 24, 25, 27 and 331, 332, 333, 335, 336, 337.
  The other three are 6, 28 and 173. ✔
- **167 files:** correct. `freeze_files` = 164 `*.json` + 3 run files (`corpus_gate.py:887-892`).
  The glob skips `data/v1/.gitkeep`. ✔
- **152 drafts, digest `d373c4b0…a468`:** recomputed, matches `data/pqa-selection.json`. ✔ But
  `products_digest` hashes **every entry of a directory** (`select_pqa.py:519-525`), so it cannot be run
  on `data/v1/` (12 policies and `.gitkeep` are there too). Check the drafts with `verify_selection`
  (`:1010-1024`), then **copy bytes** and compare each copy's sha256. Never write from `iter_selection`:
  it yields parsed JSON (`:1036`), and re-serialising changes the bytes.
- **`data/policies-v1/` has 12 files** ✔. **`data/v1/` holds only `.gitkeep`** ✔. **Redis holds
  dev-v0, 44 chunks** ✔, tag `dataset_version = dev-v0` on each.
- **`K` and capacity** recomputed offline: whole 1,274/318, validation 622/156, test 652/163 ✔.
  Python's `round` is half-to-even: 318.5 gives 318. Half-up (Go `math.Round`, or by hand) gives 319.
  Only the whole file is affected, and it is not a run file. Record the integers and never recompute them elsewhere.
- **Workload ids:** all 147 distinct `product_id`s and all `doc_ids` exist among the 164 files. The 16
  records with no `product_id` are all in validation. On the right index, the splice never misses. ✔
- **Missing from the spec:** the index check (A); asins in the record (Verdict); A9 needs a dev-v0
  re-ingest first (R3); the carried counts need per-query sets that the gate does not export (B); the
  re-ingest decision (R6); `data-card.md:14` against keeping dev-v0; the docs list (`architecture.md`,
  `README.md`, `data-card.md` header). **A3's "same digest" is true by construction**, because it hashes
  files only. The real repeat check is the G1/G2 counts and the per-query sets.

## 9. Risks the spec does not name

- **R1. Wrong index, silent.** See the Verdict. **(A)** In stage 2, before retrieving: the index's
  `@dataset_version:{v1}` count equals `num_docs`, and its `doc_id` set equals the corpus files. The
  tag already exists (`ingest.py:87`, read live).
- **R2. Asins in tracked files:** the freeze record, the chunk-id list and the gate logs in `evidence/`.
  Track only digests and counts. Keep per-file lists in a gitignored place (`data/v1-draft/`).
- **R3. `make verify` fails while Redis holds v1** (`test_retrieve_scoping.py:84, :108`). Tests are
  immutable, so fix the **order**: freeze, then `make ingest` (dev-v0), then `make verify`.
- **R4. `make demo` on v1 is silent** (`Makefile:227-232` checks only for a cold cache). Option (a)
  plus `demo-reset` pinned to dev-v0 covers it.
- **R5. Stage 2 runtime: minutes, not hours.** Per query: 1 embedding (`:1010` → `get_query_embedding`),
  1 in `retrieve()` plus 1 more on a splice (`retrieve.py:128, :116`), and 1 unscoped. That is about
  3 – 4 per query, or 3,800 – 5,100 Ollama calls. At 3.4's rate (1,274 in 25 s, ≈ 20 ms;
  `…workload-generator/evidence/memory.md:11`), that is 1.5 – 2 min. `retrieve()` builds a new
  `RedisVectorStore` each call (two Redis clients and an index check, `retrieve.py:126-127`): ms each.
  `similar_pairs` is about 811 k pure-Python dot products of 768 values: tens of seconds. **Estimate
  3 – 10 min per run.** Record the real time on run 1.
- **R6. Embedding nondeterminism.** Two runs on one ingest test only the query side. Ingest embeds in
  batches, so a chunk's vector can depend on its batch. With an identical corpus the batches are the
  same, so the vectors are probably equal, but this is not proven. Two free checks: compare the gate's
  query vectors with 3.4's `vectors.json` (same function, `build_workload.py:2645-2648`), and count the
  queries whose top-5 differs between runs.
- **R7. Scoped sets can be shorter than 5.** `_drop_other_products` filters on the `doc_id` metadata
  (`retrieve.py:95-102`), and `_ensure_own_chunk` splices one own chunk (`:105-119`). With 152 products,
  a scoped set can hold 1 – 2 chunks. Then `data-card.md:300` ("`J ≤ 0.2` admits at most one shared
  chunk") is false: 1 shared chunk in 2 + 2 gives J = 0.33. **This makes G1 stricter, not looser.**
  Record the set-size distribution beside G1, so a failure can be read.
- **R8. Test-split leak** through U10 and the sibling rate (§7).
- **R9. Memory.** 3.4's embedding ran at pressure level 2 (`memory.md:11`). Only `nomic-embed-text`
  (~0.37 GB) is needed here, not the LLM. Green is still required (S3 and A10), and it may take time
  to get.
- **R10. Phase 4 has no restore path.** A `mutation: on` run that edits `data/v1/` cannot use
  `git checkout`, because the folder is gitignored (`demo-reset` relies on git for dev-v0). Keep the
  assemble step idempotent: it is the restore path, and `corpus-verify` detects drift.
- **R11. A third copy of the splitter.** `ingest.main` has the split inline (`ingest.py:77-90`), and
  `select_pqa.py:548-550` and `check_policies.py:229-231` already have their own copies. Metadata
  present at split time moves chunk boundaries (ADR-011's unchunkable title). Use one shared function,
  **and** compare the offline chunk digest with the chunk ids and texts in Redis (stronger than the
  spec's count-only check).
- **R12. `retrieve_all`'s docstring is wrong** (`corpus_gate.py:795-796`: "keeps … all policy
  chunks"). It is a post-filter (`interfaces.md` §B v0.8). Doc only.

## 10. Smallest change that meets the spec

1. `config.py:19`: read the env var, default `dev-v0`. `demo-reset` pins `dev-v0`.
2. Assemble: run `make pqa-select-verify` and `make workload-verify` first (both exist and are offline;
   the workload manifest already binds the selection and the policies). Then copy bytes and compare
   hashes. **Skip `make policy-check` on `data/v1/`:** byte-equality with `data/policies-v1/` makes the
   existing run on that folder enough.
3. Gate: (A) the index check; (B) an optional gitignored per-query export (scoped and unscoped ids,
   set sizes). Nothing else changes.
4. `data/v1-freeze.json`: digest, counts, `K` and capacity, chunk digest, `llama-index-core` version,
   the workload-manifest sha256 and the unit-list sha256. **No file names.** `make corpus-verify`
   recomputes the digest through `corpus_gate.snapshot_digest`.
5. One offline script computes U10 – U12 and the sibling rate from export (B), counts only. **No
   second Ollama pass.**

**Cut:** the default flip, the pyproject pin (unless the author signs off), any `DATASET_EPOCH_STUB`
change, `CACHE_CAPACITY` wiring, the faster retriever, and any edit to `reuse/` or the gateway.

> **Required phases:** impact · experiment · implementation. (Contract: not required. Scope L also
> needs design and the opus design-review; ADR-014 records the freeze with "Invalidates: none — no
> runs yet".)
