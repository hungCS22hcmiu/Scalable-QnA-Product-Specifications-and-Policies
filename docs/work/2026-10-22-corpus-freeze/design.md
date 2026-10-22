# Design — corpus-freeze (item 3.6)

**Draft 3, 2026-10-22** (draft 2 + `review.md`: H1 – H4, M1 – M8, L1 – L6). Open questions are those of
`spec.md`, answered here as proposals. §8 lists what is still not known.

## 1. The flow

```
CODE BLOCK (Redis holds dev-v0; make verify stays green)
  refactor ingest (golden dump first) · gate additions · freeze_corpus.py · Makefile · tests
  make verify  ✔  → commit            (the gate then runs on a clean tree)

MEASUREMENT BLOCK
  make pqa-select-verify · make workload-verify
  corpus-assemble ─► data/v1/ (164 files, bytes copied)
  memory green? ─no─► stop (S3)
  [run 1]  DATASET_VERSION=v1 make ingest
           index check (shared function) ─fail─► precondition, not S1: re-ingest, retry
           make gate-corpus   → report + per-split export, in data/v1-draft/gate/ (gitignored)
  probe_checks (always, read-only, from the export)
  any criterion FAIL, or S5 ─► counts to evidence/, STOP, tell the author. freeze is skipped.
  [run 2]  fresh `make ingest`, same gate ─► compare with run 1 (A3, S2)
  freeze ─► data/v1-freeze.json (no file names) · corpus-verify
  data-card.md · ADR-014

RESTORE BLOCK (also on any stop)
  DATASET_VERSION=dev-v0 make ingest ─► make verify
```

On a fail only `freeze` is skipped. The export and the checks still run, because they are what lets the
author read the failure (M1).

## 2. Pieces

### 2.1 One shared split function — `rag/src/rag/ingest.py` (a refactor)

`ingest.main` has the split inline (`ingest.py:77-90`). It moves into
`records_to_nodes(records, dataset_version) -> list[node]`; `main` calls it. The names
`record_to_document`, `load_records`, `product_to_text` stay (tests import them).

**Golden check, taken with the OLD code before the move:** a digest of a full node dump — id, text,
metadata and its order, excluded keys, start and end index, `ref_doc_id` — over `dev-v0` (44 nodes) **and**
the 164 `v1` inputs (539 nodes). Only the digests are kept (hashes of PQA text are not text). After the
move the same dump gives the same digests, and no existing test changes. Two other splitter copies exist
(`select_pqa.py:548`, `check_policies.py:229`); they are not touched.

### 2.2 `experiments/scripts/freeze_corpus.py` (new)

Imports `corpus_gate` and `select_pqa`. `rag/` never imports it; `corpus_gate` never imports it.

| Subcommand | Contract |
| :--- | :--- |
| `assemble` | Calls `verify_selection` on the drafts. Copies the 152 product and 12 policy files **as bytes** (never from `iter_selection`). Compares each copy's sha256 with its source's. **Refuses** (exit 2, writes nothing) if a file name differs from its `doc_id`, a `doc_id` lacks its prefix, `data/v1/` holds any other or a differing file, or `data/v1-freeze.json` exists. Idempotent. It is **not** a restore path (M4; Phase 4 gap, named in ADR-014). |
| `check-index` | Runs the index check (§2.4 A) against the live Redis and the files. Needs Redis and the Ollama tag list, not a model run. Exit 0 or a message that names the failed test, in counts. This is the command a P1 run and a reference generation call before they start. |
| `freeze` | **In:** run 1's gate report. Recomputes the snapshot and chunk digests itself and **refuses** on a difference. Refuses if the report did not pass, has no digest, the version is not `v1`, run 2's comparison did not pass, `ungrounded` or `own_chunk_missing` is above 0, the tree was not clean, any memory reading is above 0, S5 was raised, or the record exists. Drops the `files` array and every absolute path (`workload`, `run_files[*].path`). Writes `data/v1-freeze.json`. |
| `verify` | Re-hashes the 167 files (`snapshot_digest`), recomputes the chunk digest, the manifest hash, the model digest and the retrieval config. **Fails** on any difference in these. A package-version difference **fails only if the chunk digest also moved**, otherwise it warns. A missing file is a failure, never a skip. It names the first differing file only if the gitignored per-file list is present. |

Makefile: `corpus-assemble`, `corpus-index-check`, `corpus-freeze`, `corpus-verify`.
`corpus-verify` is **not** in `make verify` (`data/v1/` is gitignored).

### 2.3 The version switch (open question 1, option a)

`config.py:19`: `DATASET_VERSION = os.environ.get("DATASET_VERSION", "dev-v0")`. `demo-reset` passes
`DATASET_VERSION=dev-v0` explicitly. `ingest` is **not** wired to Make's `VERSION`. The default does not move.

### 2.4 Gate changes — additive only (`corpus_gate.py`), each with a test

**(A) The index check** — one function, called at the start of stage 2 and by `check-index`. It asserts:

1. `FT.INFO idx:corpus`: `num_docs` equals the offline chunk count; `hash_indexing_failures` is 0;
   `indexing` is 0; `percent_indexed` is 1; the vector field is FLAT, 768, COSINE.
2. Scanning `corpus:*`: every hash has `dataset_version == args.version`; the hash count equals `num_docs`.
3. The digest of `(chunk_id, sha256(text))` over the hashes equals the offline `chunk_digest(corpus_dir)`.
4. The digest of the stored vectors (`HGET vector`, sorted by `chunk_id`) is computed and **returned**. At
   gate time it goes in the report; at `check-index` time it must equal the recorded one.
5. The live embedding-model digest (Ollama `/api/tags`, no model load) equals the recorded one.

A failure stops with exit 1 before any embedding, and names the test by number. No threshold, pair rule or
statistic changes. `chunk_digest` lives in `corpus_gate.py` and imports `rag.ingest.records_to_nodes` lazily.

**(B) The export**, `--retrieval-out DIR`: one file **per split**. For each query: `qa_id`, the ordered
scoped ids, the ordered unscoped ids, both set sizes, and the sha256 of the query vector. Gitignored; it
holds `qa_id`s, which embed the asin, so it never goes in `evidence/`.

**(C) The report gains:** `ungrounded` count; `own_chunk_missing` count; memory-pressure readings (the gate
runs `sysctl kern.memorystatus_vm_pressure_level` itself at the start, at each progress tick and at the end);
`tree_clean` and `git_commit` for `rag/src`, `experiments/scripts`, `Makefile`; the model tag and digest;
`ollama_version`; the retrieval config; the versions of `llama-index-core`, `tiktoken`, `nltk`,
`llama-index-vector-stores-redis`, `redisvl`; the stage-2 time; the vector digest; the count of J ≤ 0.2
printed beside the histogram; and **the G1 and G2 breakdown** (§2.5).

### 2.5 The G1 and G2 breakdown (H3)

For each split, each counted pair is classed by **pair type** — same `cluster_id`, `pair_of` partners, other —
and by **`doc_ids`** — same, different. G1 and G2 are reported as the gate defines them, and the table sits
beside them. **S5:** if G2 in a split is met only by same-`cluster_id` pairs, it is read as "passed by
definition; no built trap" and stops for the author before `freeze`.

### 2.6 The freeze record, `data/v1-freeze.json` (tracked)

Digests, counts and statistics only. **No file name, no asin, no `qa_id`, no absolute path.**

```
freeze_version, dataset_version "v1", frozen_on, git_commit,
snapshot_digest, file_count 167,
chunk_digest, chunk_count, stored_vector_digest,
splitter { llama-index-core, tiktoken, nltk, chunk_size 256, chunk_overlap 40 },
embedding { tag, digest, ollama_version },
retrieval { top_k 5, index FLAT, metric COSINE, dim 768, vector-store pkgs },
workload_manifest_sha256, probe_flags_sha256,
run_files { whole | validation | test: { k_distinct_queries, cache_capacity } },
criteria [ {name, passed, summary} ], pair_breakdown, statistics { the gate's own block },
gate_run { run 1 and run 2: time, memory readings }
```

Written once. A different freeze is a different `dataset_version` and a different file.

### 2.7 The carried measurements (offline, from the export)

One script in the trail (`tools/probe_checks.py`), read-only, **counts only**. It refuses U10 and the
sibling rate on the test file.

| Output | Rule, fixed now | Reads |
| :--- | :--- | :--- |
| scoped-set sizes | distribution (1 … 5) per split, beside G1 | both |
| U12 (a) | per probe, the Jaccard of its scoped top-k with its partner's | both |
| U12 (b) | per probe, **whether the two evidence spans share a chunk**; the per-probe flags go to a gitignored file and its sha256 goes in the record, so 6.1 reads a frozen classification | both |
| U11 | is the seed's evidence chunk in the scoped top-k. A span over two chunks: report **any** and **all** | both |
| U10 | the `policy_frac` distribution of policy queries; bands in `main.go` are read, not changed | **validation only** |
| sibling | for each condition twin, does its scoped top-k hold a chunk of the other twin's document | **validation only** |
| units | does every unit in v1's policy terms appear in the numeric unit list; recorded in ADR-014 | the 12 policy files |

## 3. What fills `data-card.md`

The gate prints the statistics and `--report` writes them; none is typed by hand. The ten `TODO(W8)` markers
(table rows 23, 24, 25, 27 and the six in §7); the 3.1 skip rules; the pair breakdown; the count of J ≤ 0.2
beside the histogram, with the note that mean, variance and histogram cover all similar pairs, across splits
too. **Corrections:** the sentence "at equal `top_k` … orders pairs identically" (`data-card.md:300`) is false
for scoped sets, which differ in size. It gets "with one shared chunk, a pair passes only if a + b ≥ 6".
"At most one shared chunk" stays true (6s ≤ a + b with a, b ≤ 5 gives s ≤ 1). Also `data-card.md:14`.

## 4. Failure modes

| What goes wrong | Silent? | What stops it |
| :--- | :---: | :--- |
| Gate measures a stale, wrong or partial index | yes | index check, tests 1 – 3 |
| The index holds other vectors or a moved model | yes | tests 4 and 5; the vector digest in the record |
| `DATASET_VERSION` forgotten at ingest | yes | the same check; `demo-reset` pinned; `ingest` not on `VERSION` |
| After 3.6 Redis holds `dev-v0` and a `v1` run starts | yes | `check-index` before every run (P1 wires it); ADR-014 says so |
| Retrieval code, model tag or a package changes | yes | `git_commit`, model digest, retrieval config, versions in the record; `verify` |
| A covered file changes after the freeze | yes | `verify`: the digest and the chunk digest |
| G1 or G2 passes on paraphrase pairs | yes | the breakdown (§2.5) and S5 |
| A query retrieves nothing, or lacks its own product's chunk | yes | `ungrounded`, `own_chunk_missing`: `freeze` refuses above 0 |
| Memory goes yellow in a run | yes | the gate reads it itself; `freeze` refuses above 0 |
| A run is repeated until the numbers look good | yes | every attempt logged in `evidence/`; S2 fixes run 1 as the figure |
| G1 or G2 fails and the corpus or statistic is nudged | yes | S1 lists the allowed steps; a statistic change is its own ADR |
| U10 or the sibling rate on test is read as a tuning input | yes | refused in code; validation only |
| An asin reaches a tracked file or stdout | yes | no file names in the record; counts-only messages; synthetic ids in tests |
| The refactor changes a node | yes | golden node dump on `dev-v0` and `v1`, taken with the old code |
| `data/v1/` holds a stray `*.json` | yes | `assemble` refuses strays |
| `make verify` fails with `v1` in Redis | no, loud | restore block; code finished and green first |
| `make demo` on a `v1` index proves nothing | yes | `demo-reset` pinned to `dev-v0` |

## 5. Edge cases

- `assemble` after a freeze exists: refuses. A workload file missing at `verify`: a failure that names it.
- Run 2 begins from the index run 1 left: it re-ingests first (`overwrite=True` drops it).
- Scoped sets can be shorter than five. J ≤ 0.2 still needs at most one shared chunk, and with one it needs
  a + b ≥ 6. The effect of scoping on G1 is **not** assumed; the scoped and unscoped figures show it.
- Python's `round` is half-to-even (318.5 → 318). Only the whole file, which is not a run file, is hit.
- A pair at J = 0.2 exactly counts for G1 but falls in the "0.2 – 0.3" histogram bucket (`corpus_gate.py:902`).

## 6. What this design does not do

No threshold, rule, chunk setting or retrieval setting changes. No corpus or workload file is edited.
Nothing under `gateway/`, `contracts/` or `reuse/` changes. The default of `DATASET_VERSION` does not flip,
`pyproject.toml` is not edited, `DATASET_EPOCH_STUB` stays, no second Ollama pass is made for the
measurements, and there is no restore command.

## 7. Order of the work

Code and tests first; `make verify` green on `dev-v0`; commit. Then the measurement block. Then the restore
block. No test is changed or "fixed" in the middle (the `rag` live tests fail while `v1` is in Redis, and that
is expected).

## 8. Unknowns still to verify

- **U1. Embedding determinism.** Run 2 re-ingests; the stored-vector digests of the two runs are compared,
  and so are the query-vector hashes against `vectors.json`.
- **U2. Stage 2 runtime.** Estimate 3 – 10 minutes a run. Recorded on run 1.
- **U5. Whether G1 ≥ 50 and G2 > 0 hold.** The real risk, and by the review more G2 than G1: the twins' top-5
  may hold the sibling document's chunks. `dev-v0` gave 0 pairs for a similar reason.
- **U4. The shape of the evidence spans** (the model layer, gitignored), for U11 and U12 (b).
- **U6. Where a policy query's scoped retrieval goes.** 16 validation records have no `product_id`.
- **U9. ADR-014's kind.** "Decided (data)". The log holds ADR-001 … ADR-013.
- **U11. Whether `llama-index-vector-stores-redis` returns `text` byte-for-byte.** The review read
  `node.get_content(MetadataMode.NONE)`; the golden check on `dev-v0` confirms it on the live store.
- **U12. Whether the model digest is stable across an Ollama restart.** Read twice during the work.
