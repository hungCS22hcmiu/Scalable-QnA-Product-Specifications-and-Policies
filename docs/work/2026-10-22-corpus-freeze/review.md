# Design review — corpus-freeze (item 3.6)

**Reviewer:** the `design-reviewer` subagent (opus), 2026-10-22, on `design.md` draft 2, `spec.md`
draft 2 and `impact.md`. It changed no file, ran no Ollama, ingest or Redis write, and re-counted the
workload's pairs from `vectors.json`.

**Verdict: sound with changes.** The shape is right: option (a), the additive index check, no file
names in the record, and stop rules written before the run. Four silent paths stayed open (H1 – H4).
Every fix is additive and inside the scope of the spec. All findings are accepted, with two choices
noted below. The result is `design.md` draft 3 and `spec.md` draft 3.

## Findings and what was done

| ID | Sev | Finding | Resolution |
| :-: | :-: | :--- | :--- |
| H1 | High | The record pins files, chunk text and `llama-index-core`. It does not pin the retrieval stack: the embedding model (`nomic-embed-text:latest` is a moving tag), the Ollama version, `retrieve.py`, `TOP_K`, the gate constants, `tiktoken`, `nltk`, `llama-index-vector-stores-redis`, `redisvl`. An `ollama pull` or one edit to `retrieve.py` changes every retrieval and `corpus-verify` still says PASS | **Accepted.** The record gains `git_commit` (the gate runs only on a clean tree for `rag/src`, `experiments/scripts`, `Makefile`), the model tag and digest, the Ollama version, the retrieval config and the four package versions. The index check asserts FLAT, 768, COSINE and the model digest. `verify` fails on a model-digest or config change; a package-version change fails only if the chunk digest also moved, else it warns |
| H2 | High | After A9, Redis holds `dev-v0`, and nothing a run can call compares Redis with `v1`. The index check lives only inside gate stage 2 | **Accepted.** The check becomes its own command, `freeze_corpus.py check-index` (`make corpus-index-check`), needing Redis and the files but no model. The gate calls the same function. ADR-014 says Redis holds `dev-v0` after 3.6 and that every `v1` run and every reference generation must re-ingest `v1` and pass this check first. The wiring stays in P1. The check also compares a vector digest (M7), so it proves "the index that was gated" |
| H3 | High | G1 and G2 can pass on pairs that are not traps. Counted from `vectors.json`: pairs at cosine ≥ 0.85 inside a split are 663 (validation) and 554 (test). Of these, 487 and 413 share a product and `doc_ids`, and 317 and 318 are paraphrases from one `cluster_id`. A different-product pair on one policy document is 66 and 57. The splice puts each query's own product chunk into its scoped set, so two such pairs can reach J ≤ 0.2 | **Accepted.** The gate reports G1 and G2 per split **broken down** by pair type (same `cluster_id`, `pair_of` partners, other) and by `doc_ids` (same, different). The breakdown goes into the record and the card beside the counts. New stop rule **S5** (spec): if G2 in a split is met only by same-cluster pairs, it is read as "passed by definition, no built trap" and goes to the author before the freeze |
| H4 | High | The most likely failure has no path chosen in advance. The condition and region twins (79 within-split pairs, partner cosine ≥ 0.934) are the designed B-within pairs. Each twin probably retrieves chunks of both siblings, and J ≤ 0.2 needs at most one shared chunk and a + b ≥ 6. G2 inside a split is the real risk, more than G1. On a fail, the two "fixes" (undo ADR-012's minimal pairs, or redefine the statistic) would be chosen after seeing the numbers | **Accepted.** S1 now lists the allowed next steps before run 1: report; the author reopens 3.3 or 3.4 under their own approvals; or the gate statistic is changed by **its own ADR with its own pre-registration, never in this task**. The author chooses from that list |
| M1 | Med | On a fail the diagnosis is thrown away (design §1: "nothing after the gate runs"). The export, set sizes, U12, sibling rate and H3 table are what you need to read a failure | **Accepted.** The export and the probe checks always run (read-only). Only `freeze` is skipped. On any stop, re-ingest `dev-v0` so `make verify` is green |
| M2 | Med | S3 and S4 rely on the operator. A query that retrieves nothing only gives a WARNING (`corpus_gate.py:1014-1017`). Two empty sets give J = 0, which counts as a G1 pair (`:692-696`). Memory readings are typed by hand | **Accepted.** The report gets `ungrounded` (count) and `own_chunk_missing` (queries with a `product_id` whose scoped set has no chunk of their product; expected 0), and `freeze` refuses if either is above 0. The gate reads the pressure level itself (`sysctl`) at the start, at each progress tick and at the end, and `freeze` refuses if any reading is above 0. Every attempt is logged in `evidence/`, the discarded ones too |
| M3 | Med | The golden check for the `ingest.py` refactor is too weak: `dev-v0` is 44 documents and 44 chunks, only ordinal 0. `v1` gives 539 chunks (1 – 10 per product, 4 per policy, 82 with non-ASCII text) | **Accepted.** The check runs on `dev-v0` **and** the 164 `v1` inputs, offline, over a full node dump (id, text, metadata and order, excluded keys, start and end index, `ref_doc_id`). The dump digest is taken with the **old** code before the move. `dataset_version` becomes an argument. The names `record_to_document`, `load_records`, `product_to_text` stay (tests import them) |
| M4 | Med | `assemble` cannot be the restore path: it refuses when the record exists and when `data/v1/` differs, which are the two states a restore is for | **Accepted, the smaller choice:** the claim is dropped. ADR-014 names it as a Phase 4 gap; a `--restore` belongs to the task that needs it |
| M5 | Med | `unit_list_sha256` hashes the whole of `support_numeric.go` (492 lines). Any comment edit would make `corpus-verify` fail forever on a corpus whose bytes did not change. The name also collides with `units.unit_list_sha256` in `workload-manifest.json` | **Accepted.** The hash is removed from the record and from `verify`. `TestNumericUnitListPinned` already pins the list in `make verify`. The read-only unit check is recorded in ADR-014 |
| M6 | Med | Half of the carried U12 is missing: 3.4 carries the Jaccard **and** "whether the two evidence spans share a chunk" (`design.md:155`, `super-plan.md:367`). The flag decides which probes differ in provenance (analysis rule A2) | **Accepted.** The flag is added. Per-probe flags go to a gitignored file; its sha256 goes in the record, so 6.1 reads a frozen classification |
| M7 | Med | A3 cannot be checked as written: export B has no vectors, "compared" has no pass rule, and rank order matters (the namespace comes from rank 1) | **Accepted.** The export holds each query's vector sha256 and the **ordered** id lists. A3's rules (spec): vectors exactly equal to `vectors.json` (report how many differ and the largest difference); pair counts equal the offline ones (1,342 at ≥ 0.85; 663 and 554 inside a split; 125 across), re-derived in plan step 1; id lists equal in order. A vector digest of the stored vectors (`HGET vector`, sorted by `chunk_id`) is compared between the runs. That settles U1 directly |
| M8 | Med | The planned card "correction" targets a true sentence. J ≤ 0.2 holds exactly when 6s ≤ a + b; with a, b ≤ 5 this gives s ≤ 1 always. The sentence that breaks is the one before it (`data-card.md:300`): "at equal top_k … orders pairs identically". Design §5's "this makes G1 stricter" is reasoned, not measured | **Accepted.** The monotonicity sentence is corrected and "with one shared chunk, a pair passes only if a + b ≥ 6" is added. "Stricter" is dropped. The scoped against unscoped figures show the net effect |
| L1 | Low | Asins can leak through stdout: the gate prints `qa_id`s on a warning (`:1016`), and the G3 and W details print `qa_id`s and question text | **Accepted.** Evidence comes only from the report JSON filtered to counts. New messages print counts. New tests use synthetic ids |
| L2 | Low | "Validation only" is prose, not code | **Accepted.** The export is one file per split. `probe_checks` refuses U10 and the sibling rate on the test file. For U10 only the `policy_frac` distribution is reported |
| L3 | Low | `freeze` trusts the report | **Accepted.** `freeze` recomputes the snapshot and chunk digests and refuses on a difference, refuses if the version is not `v1` or run 2's comparison did not pass, and strips `workload` and `run_files[*].path` (absolute paths) |
| L4 | Low | Order of the work: while `v1` is in Redis the `rag` live tests fail | **Accepted.** Code and tests first, `make verify` green on `dev-v0`; then the measurement block; then restore `dev-v0`. No test is "fixed" in the middle |
| L5 | Low | The histogram misleads: J = 0.2 exactly counts for G1 but sits in the "0.2 – 0.3" bucket (`:902`). Mean, variance and histogram cover all similar pairs, across splits too | **Accepted.** The count of J ≤ 0.2 is printed beside the histogram and the card says both facts |
| L6 | Low | S2 needs two more sentences | **Accepted.** "Run 1" is the first run with a passed index check and all readings green. If two runs disagree on pass or fail, that is an `/investigate`, never a best of three |

## What the review found right

Option (a) with `demo-reset` pinned and `ingest` off Make's `VERSION`. The additive index check, which
changes no statistic. Byte-for-byte text works, since Redis `text` is `node.get_content(MetadataMode.NONE)`.
Products copied as bytes and never through `iter_selection`; strays refused. No file names in the record.
S1 and S2 written before any run, and run 2 re-ingesting. U10 and the sibling rate on validation only.
`corpus-verify` kept out of `make verify`. Nothing touches the hit path, `reuse/` logic or the contracts,
and no cut scope comes back.

## Unknowns the review settled

- `FT.INFO` gives `num_docs`, `hash_indexing_failures`, `indexing` and `percent_indexed`. After a finished
  ingest `num_docs` is reliable. The check asserts all four. The scan pattern is `corpus:*`. `idx:cache`
  uses the prefix `t2:`, so no second index sits on the corpus keys.
- `v1` is 539 chunks offline. `dev-v0` and `v1` share no `doc_id`.
- `vectors.json` holds all 1,274 queries, made one at a time by the same function. Exact equality is a fair
  expectation. 36 pairs lie within ±0.001 of 0.85 and 5 within ±0.0001.
- `reference_answer` is `""` on all 1,274 records, so the H3 table uses `doc_ids` and `cluster_id`.
- The environment: Ollama 0.33.2, Redis Stack 7.4.0-v8, RediSearch 2.10.20, `llama-index-core` 0.14.23.

## Still open for the work

U1 (do ingest vectors repeat), the real composition of G1 and G2 (H3), U4 (the shape of the evidence
spans), and the stage 2 runtime.

## For the author (the two choices that are not mechanical)

1. **S5 and H4 are new pre-registered rules.** They fix, before run 1, what a failure and a "pass by
   paraphrase pairs" mean. They are part of what the experiment phase approves.
2. **M4 chose the smaller option** (drop the restore claim, carry it to Phase 4). Say if you want
   `assemble --restore` built here.


# Code review — /ai-review, 2026-10-22

Reviewer: subagent `contract-reviewer`, over `git diff 1d53949 HEAD -- gateway rag contracts experiments Makefile`
(commit `a7c1178`, 9 code files) and the evidence of the stopped run. Scope note: the working tree held no
uncommitted change under those directories, so the review ran on the task's commit. Findings were checked against
the code before they were accepted. No frozen value, no seam field and no threshold is touched by the diff
(chunk size 256, overlap 40, `top_k` 5, `nomic-embed-text`, 768, FLAT, COSINE, the chunk-id scheme and the
`corpus::` prefix; 0.85, 0.2, 50). `records_to_nodes` is the old loop with `dataset_version` as a parameter. A scan of
the changed and task files for asins and qa_ids found none. `gate-failure.md` agrees with `report.json`
(G1 21 = 13 + 8, 18 across, 39 in all, 1342, K and capacity, 53 readings, 86 s, 539 chunks, 0 of 1274 vectors differ).

| # | Finding | Status | Resolution |
| :--- | :--- | :--- | :--- |
| 1 | `verify` checked Ollama for the model tag **in the record**, not for `config.EMBEDDING_MODEL`; and it never compares the code that embeds | CONFIRMED | **Fixed (model).** `cmd_verify` now fails if `config.EMBEDDING_MODEL` differs from the record's tag; test added. **Carried (code hash):** a hash of `rag/src` in the record, so an edit to a prefix in `embedding.py` or to `retrieve.py` is caught, is a design change to the record. It matters only after a freeze, and nothing is frozen. It goes to the successor task's design |
| 2 | Before a record exists, test 4 checks vector byte length only, but the PASS line said "vectors … checked"; `freeze` did not check that the two reports are two runs | CONFIRMED | **Fixed (wording, same file).** The line now says "vector sizes checked; the vector digest and the model digest are not compared"; `freeze` refuses the same report file twice; tests added. **Carried:** a run-start time in the report, and re-embedding the 539 chunks to compare them with the stored vectors (about 19 s). A run 2 that skipped its re-ingest is still caught only by the plan and `attempts.md`. Successor task's design |
| 3 | All 53 readings were 1, read as yellow. S3 says discard and repeat; the waiver was only in `attempts.md` | CONFIRMED, then **superseded** | Fixed at the time: the waiver went into `approvals.md`. **Later the premise was found wrong:** 1 is the normal level, so the run needed no waiver and its numbers stand. Corrected in `approvals.md` and `gate-failure.md`; the encoding fix is a small step of the task that re-runs 3.6 (`g1-finding/spec.md`, section "The memory scale") |
| 4 | G2 "pass" is 3 pairs per split, of which 1 (validation) and 2 (test) are built traps; the rest are same-source paraphrases or a coincidence. S5 fires only if all are paraphrases. `gate-failure.md` showed the G1 table only | CONFIRMED | **Fixed.** `gate-failure.md` has the G2 table and a sentence on how to read it. The labelling rule (`label_pair` by `product_id`) is the 3.4 design and is not changed here; it goes to the successor task |
| 5 | `--report` was not checked with `require_git_ignored`, though the report holds 164 asin-bearing paths and an absolute workload path | CONFIRMED | **Fixed.** The report path gets the same guard as the export, before any work; test added |
| 6 | Code, a Makefile comment and two test docstrings cite ADR-014, which does not exist (decisions.md ends at ADR-013) | CONFIRMED | **Fixed.** The five references now name the item 3.6 design. ADR-014 is not written, because nothing was frozen |
| 7 | `passed` ignored memory, S4 and S5: a yellow run that passed G1 – G5 printed `--- FREEZE ---` and a digest, exit 0, and wrote `passed: true` | CONFIRMED | **Fixed.** A flagged run is `passed: false`, prints "NOT FROZEN — the five criteria pass, but this run is flagged" with the reasons, writes no digest, and the report has a `flags` list. A control test proves the pass branch is reached. `freeze` still refuses such a report on its own. Also noted, **accepted:** `own_chunk_missing` is near-vacuous, because `_ensure_own_chunk` (`retrieve.py:105-119`) splices the product's chunk in whenever `product_id` is set; the second half of S4 can only fail if the product is missing from the index, which index-check test 3 already catches. It stays as a cheap guard |
| 8 | Evidence: the J table sums to 36 where the text says 39; "Redis holds v1" was stale; `attempts.md` had no row for the step 24 ingest or for `make verify` | CONFIRMED | **Fixed** in `gate-failure.md` and `attempts.md` |
| 9 | Outside the diff: the uncommitted `.claude/settings.json` drops the `Read` deny rules for `data/raw`, `data/v1-draft`, `data/v1` | CONFIRMED | **Accepted, not ours.** The author's own change. Recorded in `approvals.md`; not part of this commit |

No finding is left open. Findings 1 and 2 each have a part carried to the successor task, named above.
