# Spec — workload-generator (super-plan item 3.4)

**Scope:** L · **Opened:** 2026-10-21 · **Branch:** main, as for 3.1 – 3.3, unless the author says otherwise

**Why L.** The workload is what every Phase 6 and Phase 7 number is measured on. It fixes `K`, so
the cache capacity (`round(0.25 × K)`); it fixes which queries are traps and which are safe; and the
split decides what the thresholds are tuned on. A silent mistake here costs the study, not an
afternoon. It also changes a schema three readers use (`corpus_gate.py`, `k6/ask.js`, the §H log's
`stratum`).

## The change in one sentence

Add a workload generator that reads 3.2's selection through `iter_selection` and 3.3's policy
documents, takes a model layer written by Claude (answerability labels, self-contained rewrites,
paraphrases and lookalikes, each by a rule committed before the model sees any question), and
writes one frozen workload in which every query has exactly one stratum, one split and one seed
cluster, ordered by a seeded popularity rank, with no seed cluster in both splits.

## Phase and item

- **Phase 3**, item **3.4**. Discharges C1 and C3. Rests on the `v1` corpus model and the
  B-within / B-cross split (`data-card.md` §2), ADR-011 and ADR-012.
- **Done when** (`super-plan.md`): *"Every query carries exactly one stratum and one split
  assignment; no seed cluster spans both splits."*
- Feeds the Phase 3 exit's third clause (*"the validation/test splits are frozen with the
  dataset"*); the freeze itself is 3.6.
- Unblocks **3.6** (gate, freeze, hash, `K`). 3.5 is done.
- `requirements.md` is still empty, so there are no FR / NFR / RR ids to cite.

**Carry-forwards this item discharges** (super-plan Phase 3 progress lines, ADR-011, ADR-012):

1. Read 3.2's drafts **only** through `select_pqa.iter_selection`.
2. **Label again every R2-answerable question that becomes a workload query**, and a sample of the
   R2-unanswerable ones. The labeller is **Claude** (the author, 2026-10-21: "claude again
   obviously"). Never Qwen. The ~410 (≈ 285 – 560) truly answerable estimate is measured here, not
   assumed.
3. Spec questions the record cannot answer are a **separate population**, reported apart, never in
   the headline.
4. Never label strata with the probe's tokenizer ("Windows 7" and "Windows 8" share a token set).
5. Policy questions are scarce (127; the tagger misses "replacement" and "send back", and tags
   "return key"); condition questions will mostly be constructed; there is no shipping tag.
6. No policy-lane or stratum-D query names one of the **10 products** whose titles say Renewed,
   International Version or No warranty (ADR-012).
7. The grade pair (laptops new / renewed) feeds no natural same-product pair.
8. `data/workload-v1.json` **must be gitignored before it holds PQA text** (impact F11 of 3.2).
9. `data-card.md` `TODO(W8)`s this item owns: §3 "question count K, rewrite policy, per-stratum
   counts" (the counts; `K` itself is recorded at 3.6), §2 "natural vs constructed B-within pairs",
   §4 "#clusters, #lookalike pairs, generation model / prompt", Schemas "finalize the QA pair".

## What gets built (proposed — `design.md` has the definitions)

- **The model layer** (gitignored): Claude's answerability labels, one short product name per
  product, self-contained rewrites, and generated paraphrases and lookalikes. Written in batches
  from sheets that a script prepares in the session scratchpad, by `rules.md` (the rules, the
  constants and the pre-registered analysis rules), committed **before** the first batch and after
  a small pilot on synthetic text. Hashed in the manifest.
- **`experiments/scripts/build_workload.py`** (no model, deterministic): checks the model layer
  against the selection and the policy corpus, assigns stratum, seed cluster, split and popularity
  rank, and writes:
  - `data/workload-v1.json` — the whole workload, the gate's input (**gitignored**);
  - `data/workload-v1-validation.json`, `data/workload-v1-test.json` — the run inputs, each in its
    own popularity order (gitignored), because `k6/ask.js` takes the **file order as the Zipf rank**
    and samples every record in the file;
  - `data/workload-manifest.json` — tracked: hashes, counts, rules, the model id and prompt hashes;
    no PQA text and no asin.
- **The QA-pair schema gains** `split`, `cluster_id`, `split_unit`, `pair_of`, `role`, `origin`,
  `answerable` and `popularity_rank` (`design.md` §3). A new stage-1 check in `corpus_gate.py`,
  reported beside G3 – G5, refuses a record without a stratum or a split and a seed cluster or a
  built pair in both splits; `load_workload` stays lenient, so the existing end-to-end gate test is
  untouched (impact F8). The gate also reports `K`, the capacity, G1 and G2 per split, and its
  snapshot digest covers all three workload files (impact F1 – F3).
- **Make targets** (names proposed): `workload-sheets`, `workload-build`, `workload-verify`.
- **Records:** `data-card.md` §2 – §4 and Schemas, `architecture.md`, `.gitignore`, and ADR-013
  (data) if the author agrees.

## Acceptance — each is a command, a test or a recorded read

| # | Check | How |
| :-: | :--- | :--- |
| W1 | Every record has exactly one `stratum` in {A, B-within, B-cross, C, D}, exactly one `split` in {validation, test}, and one `cluster_id`; a fixture missing any of them fails | unit test + `make workload-verify` |
| W2 | **No seed cluster spans both splits**; nor does any pair the workload builds on purpose (a B-within or B-cross probe and the query it imitates, a D query and its sources' clusters). A fixture that crosses fails and names the cluster | unit test + `make workload-verify` + the gate's stage-1 shape check |
| W3 | It reads 3.2's outputs only through `iter_selection`; a changed draft stops it before anything is written | unit test |
| W4 | Two runs with `PYTHONHASHSEED=0` and `=1` give byte-identical outputs and manifest | unit test |
| W5 | No two records share `normalize_t1(question)` across the **whole** workload (stricter than G3, so the §H offline join on `query_normalized` is exact whether or not a run sends `product_id`) | unit test + `make gate-corpus STRUCTURAL=1` |
| W6 | Every `product_id` is a `doc_id` in the selection; every `doc_ids` entry is a corpus `doc_id`; no policy-lane or D record names one of the 10 risky products | unit test + `make workload-verify` |
| W7 | Every R2-answerable seed in the workload carries a Claude label; a recorded sample of R2-unanswerable ones does too; R2 against Claude is reported with Wilson intervals | `make workload-verify` + trail evidence |
| W8 | Every model-layer row was written after the rule and prompt commit; the manifest records the model id and the prompt's sha256 | git log + manifest |
| W9 | The tracked manifest holds no PQA text and no asin (allow-list test, as 3.2's) | unit test |
| W10 | `data/workload-v1*.json` and the model layer are gitignored before the first one is written | `git check-ignore` |
| W11 | The popularity rank is a seeded hash, independent of stratum and split; each split file's order is its rank | unit test |
| W12 | `make gate-corpus STRUCTURAL=1 WORKLOAD=data/workload-v1.json` passes (G3, G4, G5) against a corpus directory holding the 152 drafts and the 12 policies | live run, recorded |
| W13 | `data-card.md` §2 – §4 and Schemas are filled for what this item owns; `architecture.md` lists the script, the files and the targets | read |
| W14 | `make test` and `ruff check experiments` pass; `git status --porcelain data/` is the same before and after `make test` | commands |
| W15 | Both split files are exact projections of the whole file (re-derived byte for byte), and the gate's snapshot digest changes when either is re-ordered | unit test + `make workload-verify` |
| W16 | Every condition axis and every department has queries in both splits; **each split holds ≥ 30 minimal-pair condition twins** (else the build stops); per-split counts by stratum, `probe_kind`, department and axis are reported | unit test + `make workload-verify` |
| W17 | Every probe carries one `probe_kind`; every non-probe carries `null`; a `name-swap-same` probe is never counted as a trap | unit test |
| W18 | The step-0 pilot (synthetic text only) and `rules.md` (the rules R1 – R10, the constants and the analysis rules A1 – A4 of `design.md` §8) are committed **before the first sheet is read** | git log |
| W19 | The gate's stage 2 retrieves with each query's `product_id`, as the runs do; G1 counts within-split pairs and G2 holds inside each split; the unscoped and cross-split counts are reported beside | unit test (fake retriever); live at 3.6 |

## Out of scope

- Building `data/v1/`, ingesting it, G1 / G2, the snapshot digest, recording `K` and the capacity
  (3.6). This item reports the counts the freeze will record; it does not freeze.
- Reference answers (`reference_answer` stays empty: they are generated by the pipeline at
  evaluation time, `data-card.md` §3).
- The Zipf skew values (Phase 7, item 7.1) and any change to `k6/ask.js` or `mu_hit.js`.
- The update set (4.4), the judge (5.1), the sweep pre-registration (6.1).
- Any change to `rag/`, `gateway/`, the `.proto`, `reuse/`, or 3.2's selection or 3.3's documents
  (both frozen by ADR-011 and ADR-012). `interfaces.md` changes in **one sentence only**: §D's
  definition of `K`, if open question 6 is accepted (impact F1; the contract phase).
- Qwen anywhere in the build. Ollama is used only for the frozen embedding, if open question 4 says so.

## Open questions for the author

Each has a proposal. `design.md` gives the reasons.

1. **Claude labels — and then the judge.** ADR-011 says the labeller is "never Qwen or the Phase 5
   judge". With Claude as labeller, the Phase 5 judge (item 5.1, not chosen yet) must be another
   model, **or** ADR-013 records why one model may do both. Proposed: keep the rule, so 5.1 picks a
   judge that is not Claude.
2. **How Claude writes the model layer.** In this session, from sheets prepared in the scratchpad
   (proposed: the 3.2 audit's method, no new dependency, no API key; it cannot be re-run, so the
   output file is the artefact, hashed), or a script that calls the Anthropic API (re-runnable,
   but a new dependency and a key).
3. **Paraphrases and lookalikes by Claude too** (proposed, same method and the same record), or
   another model?
4. **How A and C are told apart.** By the frozen embedding: a paraphrase with cosine ≥ 0.85 to its
   seed is A, below is C (proposed: the gate's own "high similarity", measured, not intended; it
   needs `nomic-embed-text` through Ollama, with the memory check), or by what Claude was asked to
   write ("close" or "far")? *The design review agrees, with a condition: A / C is a header label
   only, and per-stratum results are also reported by the logged similarity in bins.*
5. **The split unit.** Proposed (changed by the design review, M4 and H2): **a pair of products**
   for spec queries (all their clusters and probes, with B-cross built inside the pair, so nothing
   needs the split before it exists) and **(shape group, department)** for policy queries. The four
   minimal-pair groups are paired so that each split gets two, and so ≥ 30 condition twins. Split
   50 / 50 by seeded hash, balanced per department. Other option: a plain random split of seed
   clusters, which lets B pairs and same-product paraphrases cross the split.
6. **`K` per split.** `ask.js` runs one split file, so a run's working set is one split. Proposed:
   record `K_validation`, `K_test` and `K_total`, and derive each run's capacity from the `K` of
   the split it runs (`round(0.25 × K_split)`). This reads the frozen "C / K = 0.25" for a split,
   so it needs ADR-013. Other option: one capacity from `K_total`, which gives each split run a cache
   about half its working set instead of a quarter.
7. **Size.** Proposed: about **1,500 distinct queries** (≈ 750 per split). Reference generation is
   about 1.5 h per 1,000 (ADR-011), so ≈ 2.3 h once, and each online run's misses stay near an hour.
   The answerable spec seeds (~410 expected) cap the spec half. *After the design review: one spec
   lookalike per product instead of one per seed, and 20 products per minimal-pair twin cell.*
8. **Unanswerable spec questions.** A separate population through an `answerable: false` field,
   with the stratum still saying how the query relates to its seed (proposed: answerability and
   stratum are two different things), or a sixth stratum value?
9. **Policy queries name a product** ("Can I return the Galaxy A10e once I have opened it?"), as a
   shopper on a product page would (proposed: this is where one cached policy answer serves every
   product in a department), or name only the department?
10. **`product_id` on every record** (proposed: the product the query is about; whether a run sends
    it is the run manifest's choice, P1), or only on spec queries?
11. **ADR-013 (data):** the generator's rules, the model layer and its model id, the split unit,
    `K` per split, and the labeller–judge rule. Written at the end with the real counts, as ADR-011
    and ADR-012 were (proposed), or no ADR? *After the design review: the counts at the end, but the
    analysis rules (pair-level RQ2a, which probes each figure reads, the static warm set) go in
    `rules.md` before the first sheet, because they are pre-registrations.*

*Added after the impact analysis (`impact.md`):*

12. **Do unanswerable queries ride in the run files?** (impact F4) Proposed: yes. Shoppers ask
    them, so the cache should see them; their hits are judged and reported apart by the query's own
    `answerable`, and `K` includes them. ADR-011's "separate stratum" then reads "separate
    population". Other option: keep them out of the run files and give them runs of their own.
13. **Popularity:** per record and stratified, so every stratum's share of the busiest ranks equals
    its share of the file at any skew (proposed, impact F5), or per cluster (a question's wordings
    share a band of ranks)?
14. **G2 inside each split** (impact F3): a pair whose two queries sit in different split files
    never meets in a run, so G1 and G2 are reported per split and G2 must hold in each (proposed;
    stricter than `data-card.md` §7, so ADR-013 records it), or G2 over the whole file as written?
