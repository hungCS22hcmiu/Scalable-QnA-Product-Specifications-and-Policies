# Design — workload-generator (item 3.4)

**Draft 2** · 2026-10-21 · follows `spec.md` and its **proposed** answers (open questions 1 – 14).
Draft 1.1 merged the impact analysis (`impact.md`, "impact Fn"); draft 2 merges the opus design
review (`review.md`, "review Xn"). A different answer to an open question changes the sections that
name it. Nothing here runs before `/approve implementation`.

## 1. What runs, in order

```
 [0] PILOT (before rules.md is committed; review U13)
       ~20 synthetic close / far / name-swap pairs, no PQA text → nomic-embed-text (memory check)
       → evidence/pilot.md: where they fall against 0.85, while the constants can still move
                     │
 3.2: iter_selection (152 products, 4,706 pool lines)     3.3: data/policies-v1/ (12 documents)
                     │                                                 │
                     ▼                                                 │
 [1] make workload-sheets OUT=<scratchpad>   (no model)  ◄─────────────┘
       per batch: the embedded record text, its candidate questions, the policy sections;
       refuses any OUT inside the repository
                     │
                     ▼
 [2] Claude, in this session, by rules.md (rules §4 and pre-registrations §8, committed first)
       writes model-layer rows into the scratchpad
                     │
                     ▼
 [3] make workload-import IN=<scratchpad>    (no model)
       every row checked mechanically (§4); rejects listed and re-done, never repaired by a script
       → data/v1-draft/workload/model-layer.jsonl   (gitignored)
       each batch's sha256, model id and time → evidence/batches.md (tracked, counts only)
                     │       (steps 1 – 3 run twice: pass 1 labels, pass 2 writing)
                     ▼
 [4] make workload-embed     memory check first · nomic-embed-text via Ollama · no Qwen
       → data/v1-draft/workload/vectors.json   (gitignored, hashed; every query's vector, review L8)
                     │
                     ▼
 [5] make workload-build     (no model, no network, deterministic)
       verify inputs by sha256 → clusters and probes (§2.2) → stratum (§2.4) → units and
       split (§2.5) → rank (§2.6) → temp dir, swap, manifest last
       → data/workload-v1.json, data/workload-v1-validation.json, data/workload-v1-test.json
         (gitignored) · data/workload-manifest.json (tracked: hashes and counts only)
       → evidence/build.md (counts, shares, the LRU simulation of §2.6)
                     │
                     ▼
 [6] make workload-verify    re-hash; the gate's stage-1 shape check; W5, W6, W11, W16;
                             make gate-corpus STRUCTURAL=1 CORPUS_DIR=<temp: drafts + policies>
```

Step 0 and step 4 are the only steps that load a model, and it is the embedding model, never the
generator. Steps 5 and 6 can be re-run by anyone with the model layer, the vectors and the PQA
drafts. The model layer cannot be re-made (impact F9): it is the artefact, hashed, and backed up
outside git with item 5.4's raw archive (impact F10).

## 2. What the workload holds

### 2.1 Words used here

- **Seed:** a real PQA question, rewritten to be self-contained (§4 R3); or, for a policy cell no
  real question covers, a question built from real pool policy wording (§4 R7).
- **Cluster** (`cluster_id`): queries that **mean the same thing, with the same answer, from the
  same source**: a seed and its paraphrases; for policy, the same question about several products
  of the department. Same provenance by construction.
- **Probe:** a query with a `pair_of`: built against one other query to be similar to it but with a
  different source (and, for a trap, a different answer). A probe may also belong to a cluster (a
  condition twin is one of 20 queries on its own cell).
- **Unit** (`split_unit`): what the split assigns (§2.5). A unit is a union of whole clusters and
  holds every `pair_of` link of its members.

### 2.2 The parts, and how many (constants pinned in `rules.md` before any label is read)

| Part | Built from | Expected |
| :--- | :--- | ---: |
| Spec seeds | Claude-answerable labelled questions (from **both** R2 tags, review L6), hash order, `SPEC_SEEDS_PER_PRODUCT = 2` | ≈ 260 |
| Spec paraphrases | `PARAPHRASES_PER_SEED = 2`: one *close*, one *far* (§4 R4) | ≈ 520 |
| Natural pairs | pool pairs on one product Claude marks **same answer**: one cluster, `role: natural` | small |
| Spec B-within, natural | pool pairs on one product, near in wording, Claude marks **different answers** ("Windows 7" / "Windows 8") | tens at most (review U16) |
| Spec B-within, built | `SPEC_LOOKALIKES_PER_PRODUCT = 1`, on the product's first seed, kept only if both answers are evidenced and differ (§4 R5) | ≤ 152 |
| Spec B-cross | inside each product pair (§2.5), each product's first seed with the partner's short name swapped in, both ways; Claude labels it against the partner's record (§4 R6) | ≤ 152 |
| Policy, ordinary cells | `POLICY_PRODUCTS_PER_CELL = 3` per (shape, document), from real pool policy wording where it exists | ≈ 200 |
| Policy, twin cells | `TWIN_PRODUCTS_PER_CELL = 20` on the four minimal-pair groups (§2.3), both sides | ≈ 136 |
| D | `D_PER_PRODUCT = 1` for every other product (hash order): one product fact and its department's policy term (§4 R8) | ≈ 70 |
| Unanswerable | `UNANSWERABLE_SEEDS = 13` per department, hash order among Claude-unanswerable, 1 paraphrase each; `answerable: false` | ≈ 104 |

Total ≈ 1,500 (open question 7; the review moved effort from spec lookalikes to twins). **These are
expectations, not targets.** The constants are committed before Claude labels any question, and the
real counts are what the yield gives. A count is never pushed toward a number by changing a constant
after labels exist. The step-0 pilot (synthetic text only) is the last point where a constant may
move.

### 2.3 Policy shapes and twins

Every one of the 12 documents is an opening paragraph and five headed sections (checked
2026-10-21). Shapes are mapped **by heading text, not by position** (review L1): the warranty files
run covers → does not cover → claim → remedy → proof.

| Shape | Return document heading | Warranty document heading |
| :--- | :--- | :--- |
| `term` | the opening paragraph: the window, and the fee if any | the opening paragraph: the length, or "not covered" |
| `what` | What to send back | What the warranty covers / What international service covers |
| `start` | How to start a return | How to make a claim / Asking for help abroad |
| `remedy` | Your refund | Repair, replacement or refund / Repair or replacement / Repairs arranged abroad |
| `except` | Items / Pieces / Phones we cannot take back or accept | What the warranty does not cover / What is not covered |
| `other` | Exchanges | Proof of purchase and transfer |

Every `terms` string except "not covered" is only in the opening paragraph (checked), so the
`term` shape is the only one a number answers.

A **cell** is (shape, document). Twins are built only where the two answers differ, read from the
files, never guessed:

| Twin group | Cells | Differs by | `probe_kind` |
| :--- | :--- | :--- | :--- |
| **phones returns `term`** | opened / unopened, **fee questions only** (the 14-day window is equal, so window questions get no twin) | `$45` against no fee | `policy-condition` |
| **phones returns `remedy`** | opened / unopened | "the refund, less the restocking fee" against "the full refund" (checked) | `policy-condition` |
| **furniture returns `term`** | opened / unopened | 180 against 365 days | `policy-condition` |
| **laptops returns `term`** | new / renewed, **department level**: no product named, `product_id: null`, `TWIN_WORDINGS_DEPT = 8` wordings a side | 30 against 90 days | `condition-department` |
| phones warranty, every shape | domestic / international (not a minimal pair, ADR-012), at 3 per cell | covered against not covered | `policy-region` |
| `term`, every department | the return `term` against the warranty `term`, same product | window against length | `policy-kind` |

The first four are the **minimal-pair groups**: RQ2a's same-evidence, opposite-condition cases
(review H2). At 20 a cell they give ≈ 40 twins on each of the three product-level groups and 16 on
laptops; the split pairing (§2.5) sends two groups to each split, so each split holds **≥ 30**
minimal-pair twins (W16 counts them; the build stops below 30).

**Rules for every policy query** (checked, §4): it names a product of its document's department
(except the laptops department-level twins), never a product the risky rule flags — `check_policies`'
`RISKY_TITLE` applied to the **title and the specs** (review L7), imported, never a list of ids
(impact F19); on a split family it names its own condition value and not the sibling's, checked with
`corpus_gate.condition_hits` (the G5 word list, one implementation); on an unsplit family it names
no condition value.

### 2.4 Stratum and probe kind — one of each per query

**Stratum**, by precedence, first match wins (impact F16):

1. **D** — its `doc_ids` hold a product and a policy document.
2. **B-within** — a probe whose `pair_of` is about the **same** product, or a department-level
   twin.
3. **B-cross** — a probe whose `pair_of` is about a **different** product.
4. **A** — a cluster member whose highest cosine to **another member of its own cluster** is
   ≥ `SIM_FLOOR` (0.85, imported from `corpus_gate`).
5. **C** — every other cluster member.

A and C are **measured** from the recorded vectors, under the frozen embedding with the gateway's
query prefix (`search_query: `, `gateway/internal/embed/client.go:18`; `rag.embedding` applies the
same). With τ swept 0.80 – 0.98, a C query cannot reach its own cluster through Tier 2 at τ ≥ 0.85:
that is what C means, so A / C is a **header label only**, and per-stratum results are also
reported by the logged pair similarity in bins (§8 A1; review Q4).

**`probe_kind`** (review H1), offline only: `spec-attribute`, `natural`, `name-swap`,
`name-swap-same` (a B-cross whose answers are the same: kept, because it measures what the
namespace costs, but it is **not a trap** and the trap fraction excludes it), `policy-condition`,
`policy-region`, `policy-kind`, `condition-department`; `null` on non-probes. §8 A2 fixes which
figure reads which kinds. At 3.6, for every probe, the scoped-retrieval Jaccard with its partner and
whether the two evidence spans share a chunk are recorded (review H1, U12).

**Two kinds of B-within are never merged** (impact F16): this built tag, and the gate's measured
B-within (any high-similarity, low-overlap pair on one product, `corpus_gate.label_pair`).

`answerable` is its own field; `role` is `seed`, `paraphrase`, `natural`, `probe` or `d`; `origin`
is `pqa` (a real question, rewritten), `pqa-template` (built from real pool policy wording,
re-targeted, review M6) or `claude` (written by Claude).

### 2.5 Units and the split

**Spec units: pairs of products** (review M4). In each leaf, products in `sha256(SEED + ":unit:" +
doc_id)` order are taken two at a time; an odd leaf (TVs 13, headphones 25, chairs 19, desks 19)
ends in one triple. A unit holds its products' spec clusters, spec B-within probes, unanswerable
clusters, D queries, and the B-cross probes **inside** the pair (both ways; round the triple). So
B-cross is known before the split and no step needs the split to build anything.

**Policy units: (shape group, department).** Per department, 11 shape groups: `term` (both kinds,
so a kind twin never crosses) and each other shape once per kind. A policy query's named product
does not move it.

**Why.** A random split of clusters would put a probe and its target in different files, and no run
would contain the trap. A product-free policy unit stops the same question about two products (same
document, near-identical words) reaching both splits, the leak the split exists to prevent. A
product-pair unit is coarser than "by seed-question cluster" (`Final_Proposal.md:454`): it is a
union of whole clusters, so no cluster crosses, which is what the Done-when asks. Recorded.

**Assignment, pre-registered, never re-drawn** (impact F13). The unit list is written to the
manifest before the draw.

1. **The four minimal-pair groups** go first, so each split gets two: phones returns `term` and
   phones returns `remedy` to opposite splits; furniture returns `term` and laptops returns `term`
   to opposite splits. The direction of each pair is the first bit of `sha256(SEED + ":twin:" +
   pair name)`.
2. **Every other policy unit**, families in a fixed order and each family's units in hash order,
   alternates validation, test, … **continuing across families** (review L2), starting where step
   1 left the count.
3. **Product units**, per leaf in hash order, each to the split with fewer queries so far in its
   department (ties: validation). Counts are known: the whole model layer exists before the build.

D needs no same-split rule (review M4): it has no `pair_of`. The highest cross-split cosine between
a D query and a `term` query of the same document is reported instead.

**Checked:** no `cluster_id` and no `pair_of` crosses (W2); every department and every condition
axis has queries in both splits; each split holds ≥ 30 minimal-pair twins (W16); per-split counts by
stratum, `probe_kind`, department and axis are reported. A failed check stops the build; the seed
is not re-drawn.

### 2.6 Popularity rank and what the runs will see

`ask.js` takes the file index as the Zipf rank and samples every record (`ask.js:57-77`).
**Proposed (open question 13): per record, stratified.** Inside each split file, each stratum's
records are ordered by `sha256(SEED + ":rank:" + qa_id)`; at every position the file takes the next
record of the stratum furthest below its share of records so far (ties in the fixed order A, C,
B-within, B-cross, D). This holds each stratum's **record count** in any prefix within one of its
share. It does not equalise **traffic**: at skew 1.4 A would carry about 0.60 of the traffic for 0.50
of the records (review L5). So the build report gives the exact traffic share of every stratum and
`probe_kind` at skews 0.8, 1.1 and 1.4 (illustrative; the values are item 7.1's), computed from the
ranks.

**What an online run exercises** (review M1). The build report also runs a seeded LRU simulation
(no model): Zipf over each split file, capacity `round(0.25 × K_split)`, 3,000 requests, per skew;
it reports the expected hit rate, the Tier-2 decisions, and the encounters of each `probe_kind`
with its live partner. The reviewer's synthetic model gives Tier-1 repeats ≥ 88 % of hits and about
one minimal-pair encounter per run at skew 1.1, which is why §8 A4 fixes the static arm's warm set
here. The rank seed is never re-drawn.

### 2.7 `K`, the capacity and the gate

- **`K` per run file** (impact F1, open question 6): `K_validation`, `K_test`, `K_total` (distinct
  `normalize_t1` forms, equal to the record counts by W5). A run's capacity is `round(0.25 × K)` of
  the file it draws from. A new meaning for the frozen ratio's denominator: **ADR-013** and one
  sentence in `interfaces.md` §D (v0.15), the contract phase.
- **The contract change, both sides** (added at the contract approval, 2026-10-21).
  *The diff:* `interfaces.md:361` — "where `K` is the frozen workload's distinct-query count" becomes
  "where `K` is the distinct-query count of the workload file the run draws from (the whole file or
  one split, ADR-013)", and "derived at corpus freeze" becomes "derived at corpus freeze for each
  file". The header goes to v0.15 with one history row. `:374` ("trims to `round(0.25 × K)`") and
  the frozen list at `:701` (`C/K = 0.25`) stay as they are: both read true under the new `K`.
  *Producer side:* the gate prints `K` and `round(0.25 × K)` for each of the three files; 3.6
  records them in `data-card.md` §7. *Consumer side:* the gateway never computes `K`. It reads an
  absolute count, `CACHE_CAPACITY` (`gateway/cmd/gateway/main.go:272`), and trims to it
  (`cache/capacity.go:61`), so no Go code, wire field, §H field or `.proto` changes. `mu_hit.js`
  reads `CACHE_CAPACITY` only to check that its probe set fits, so it is not affected. The run that
  sets `CACHE_CAPACITY` must take it from its own run file's `K` (carried to P1, §11).
- **The digest covers all three files** (impact F2), and **the gate itself** finds the split files
  by name (`workload-{version}-{split}.json` beside the whole file), re-derives them from the whole
  file and fails if one is missing or differs, before it hashes (review L4).
- **G1 on within-split pairs, G2 inside each split** (impact F3, review L3, open question 14).
  Cross-split pairs are reported apart. Stricter than `data-card.md` §7 as written, so ADR-013 and
  §7 record it.
- **Stage 2 retrieves as the runs do** (review H3): `rag.retrieve.retrieve(q, product_id=...)`, not
  the unscoped `make_retriever`; G1 and G2 pass or fail on the scoped result, and the unscoped one
  is reported beside it. No `rag/` change. `retrieve()` rebuilds the index on every call
  (`retrieve.py:124-125`), so ~1,500 calls are slow; if that is too slow at 3.6, a scoped
  `make_retriever` is its own `rag/` task, never a copy of `_drop_other_products` in the gate.

## 3. The schema (the QA pair, finalised here)

```json
{ "qa_id": "q-phones-b07xyz1234-s01-para-far",
  "question": "What size battery is in the Galaxy A10e?",
  "reference_answer": "",
  "doc_ids": ["product-phones-b07xyz1234"],
  "product_id": "product-phones-b07xyz1234",
  "stratum": "A",
  "probe_kind": null,
  "split": "validation",
  "cluster_id": "c-phones-b07xyz1234-s01",
  "split_unit": "u-phones-03",
  "pair_of": null,
  "role": "paraphrase",
  "origin": "claude",
  "answerable": true,
  "r2_answerable": true,
  "nearest_foreign_cos": 0.81,
  "nearest_foreign_same_product": true,
  "popularity_rank": 412 }
```

- `qa_id` is built from its inputs, never a counter. It embeds the asin, like every product
  `doc_id`, so it never reaches a tracked file (impact F9).
- `reference_answer` stays empty: the pipeline fills it at evaluation (`data-card.md` §3).
- `doc_ids` is the **intended** source, for G3 and the analysis; not a retrieval result.
- `r2_answerable` is the pool's R2 tag, copied for `origin: pqa` queries (`null` otherwise), so
  seeds are reported by R2 tag (review L6).
- `nearest_foreign_cos` / `nearest_foreign_same_product`: the highest cosine to a **same-split**
  query with different `doc_ids`, and whether that query is about the same product (review M3). It
  shows the traps nobody built (cross-department `term` questions, laptops grade, two questions in
  one cell); A is reported split by it.
- `product_id` is set whenever a product is named; the gate needs it to label a pair (impact F6).
  ⚠️ `ask.js` and `mu_hit.js` send it whenever present, so every run sends it and `Retrieve` is
  product-scoped (`interfaces.md` v0.8). Runs without it would need a variant run file with its own
  hash, never an `ask.js` edit; the run identity names which (P1).
- The new fields are read by the gate's stage-1 shape check (§5) and ignored by `ask.js`.
  `stratum` reaches the §H log through `X-Thesis-Stratum`; the rest joins offline on
  `query_normalized`, exact because of W5. `answerable`, `role`, `probe_kind` and condition words
  never go into a header or a request body. **No §A or §H field changes.**

## 4. The rules for the model layer (in `rules.md`, committed before the first sheet is read)

Claude writes rows; the import step checks each one mechanically; a failed row is listed and
re-done, never repaired by the script. Model id `claude-opus-5-5`, recorded per batch with the
sha256 of `rules.md` (a batch written by a subagent records its own model id). Tokens for every
check below: lower-case, split on `[^a-z0-9]+`, **one-character tokens and digits kept**, Lucene's
33 stop words removed — never the probe's tokenizer (impact F12).

- **R1 Name.** One short name per product: 2 – 6 words, every word from the title, unique among the
  152. *Checked.*
- **R2 Label.** Answerable only if the embedded record (title, bullets, description, brand) states
  the fact that answers it, with no outside knowledge; a yes / no question is answerable if the
  record settles it either way; unsure → not answerable. An answerable label carries `answer` (one
  short line) and `evidence` (a verbatim substring of the record, 3 – 30 words). *Checked:* the
  substring is in the record. Pass 1 labels the original question (the yield and the seed choice);
  pass 2 labels **every written query on its own**, without its seed (review M5 a, e), and a
  disagreement drops it, counted.
- **R3 Rewrite.** Replace "this", "it", "the item" and the like with the short name; keep every
  other word's meaning; no new fact; one question, ≤ 30 words, ASCII. *Checked:* the short name is
  present; the digit set equals the original's.
- **R4 Paraphrase.** *Close*: change a few words. *Far*: different words and order. Both keep the
  short name and the answer, and change no number, unit, model name or value. *Checked:* digit set
  equal to the seed's; the short name present; **no record token the seed lacks** (catches Verizon →
  AT&T, front → rear when the record names both; review M5 b); its pass-2 evidence overlaps the
  seed's; `normalize_t1` differs from every other query.
- **R5 Spec lookalike.** Same product, a few words changed, a different attribute; Claude writes
  the probe's `answer` and `evidence` and names the attribute. *Kept only if* both are evidenced,
  the evidence differs from the seed's, and, for yes / no, the polarity differs (review M5 c).
- **R6 B-cross.** The script swaps the partner's short name into the seed; *checked:* no title token
  unique to the first product remains (review M5 d). Claude labels it against the partner's record
  with `answer` and `evidence`. Answers differ → `name-swap`; the same → `name-swap-same`;
  unanswerable → dropped, counted.
- **R7 Policy.** Each real pool policy question (the 127 plus those a wider keyword list finds:
  "replacement", "send back", "refund", "exchange") is assigned to one document and one shape, or to
  `ambiguous` (its condition cannot be known), `not_covered` or `not_policy`; assigned ones are
  rewritten. **Built** policy questions start from a real pool policy question's wording,
  re-targeted to the cell (`origin: pqa-template`, review M6 a); only where none fits does Claude
  write one (`origin: claude`). *Checked:* §2.3's product and condition rules.
- **R8 D.** One question needing a product fact (with `evidence`) and its department's policy term.
  *Checked:* evidence in the record; the term string from `terms` in the text.
- **R9 Natural pairs.** Candidates are pool pairs on one product whose token Jaccard (the tokenizer
  above) is ≥ 0.45; Claude marks each `same` or `different`, with evidence for both.
- **R10 No shared policy wording** (review M6 b). No policy or D query shares a 4-token sequence
  with any policy document's text, after removing the short name, the term string and the condition
  word. *Checked.*

## 5. Function contracts

`experiments/scripts/build_workload.py`:

- `write_sheets(out_dir, pass_no, batch_size) -> list[Path]` — reads through `iter_selection`;
  refuses an `out_dir` inside the repository.
- `import_rows(in_dir, layer_path) -> ImportReport` — validates every row (§4); appends only valid
  ones; returns the rejects and the batch record. Re-importing a key with different text is an
  error, not an overwrite.
- `embed_all(queries, embedder) -> dict[qa_id, list[float]]` — the only model call; `embedder` is
  injected, so tests pass a fake.
- `build(selection, policies, layer, vectors) -> Workload` — pure; no I/O.
- `make_units`, `assign_split`, `assign_stratum`, `rank`, `simulate_lru` — pure.
- `write_outputs(workload, data_dir)` — temp dir, swap with restore, manifest last (3.2's pattern).
- `verify(data_dir) -> None` — re-hashes; runs the shape check, W5, W6, W11, W16; exit 2 on failure.

`experiments/scripts/corpus_gate.py` (imports no script, impact F8):

- `Query` gains `split`, `cluster_id`, `pair_of` (defaults); `load_workload` stays lenient.
- `check_workload_shape(queries) -> Criterion` — **stage 1, one more `Criterion` in the same
  `emit`**, never a `SystemExit`: one stratum in the five, one split in the two, no `cluster_id` or
  `pair_of` across splits, both splits non-empty. The builder calls the same function.
  `test_the_gate_runs_g5_in_stage_1_and_stops_on_it` passes unchanged.
- The split files found by name, re-derived and compared before the digest; the digest over the
  corpus and the three files.
- Stage 2: scoped retrieval; G1 on within-split pairs, G2 per split, cross-split and unscoped
  reported; `K` and the capacity per split in the printout and the JSON report.
- `Makefile`: `CORPUS_DIR` passed to `--corpus-dir` (impact F19).

## 6. Tests (all fixtures in `tmp_path`, never under `data/`)

T1 one stratum, one split, one cluster per record (W1) · T2 a cluster or a `pair_of` across splits
fails and is named, in the builder and in `check_workload_shape` (W2) · T3 a changed draft stops the
build before writing (W3) · T4 byte-identical outputs under two hash seeds (W4) · T5 two records
with one `normalize_t1` form fail (W5) · T6 a risky product (title or specs) in a policy or D record
fails; an unknown `doc_id` fails (W6) · T7 the manifest allow-list: no asin, no question text, no
`qa_id` (W9) · T8 the stratified rank keeps every prefix's counts within one, and does not follow
construction order (W11) · T9 the stratum precedence, one case per line, a cosine of exactly 0.85 ·
T10 each §4 check, one row each side of its edge · T11 the split: the minimal-pair pairing,
alternation continuing across families, every axis in both splits, determinism · T12 product-pair
units and the closing triple; B-cross only inside a unit · T13 twins only where the answers differ
(phones window: no twin; phones fee and refund: twins) · T14 the gate prints `K` and the capacity per
split · T15 `write_sheets` refuses an out dir inside the repository · T16 "Windows 7" / "Windows 8"
on one product is a natural-pair candidate and never one cluster (impact F12) · T17 the existing
end-to-end gate test passes unchanged; a well-formed workload passes the shape check · T18 the
digest changes when a split file is re-ordered, and the gate fails on a missing or stale split file
(impact F2, review L4) · T19 the build stops with fewer than 30 minimal-pair twins in a split · T20
shapes map by heading text (a fixture with the warranty order) · T21 R4 rejects a paraphrase adding
a record token · T22 R5 / R6 keep a probe only with different evidence and, for yes / no, different
polarity; a same-answer swap becomes `name-swap-same` · T23 R10 rejects a shared 4-token sequence ·
T24 stage 2 calls the scoped `retrieve` with each query's `product_id` (a fake retriever records the
calls).

## 7. Failure modes — silent ones first

| What goes wrong, silently | What catches it |
| :--- | :--- |
| A paraphrase changes the answer ("Windows 8", "AT&T", "rear"): a safe-looking A hit is a false hit, charged to the rule | R4's digit and record-token checks; the pass-2 relabel without the seed; the author's read |
| A probe has the same answer, or one the record cannot give: a trap that cannot fire, so RQ2a looks better than it is | R5 / R6 evidence and polarity; twins only where the files differ (T13); `name-swap-same` kept apart |
| B-within pools probes provenance could never separate with ones only provenance separates | `probe_kind`, and §8 A2 fixes which kinds each figure reads (review H1) |
| RQ2a lands with zero cases in the test split | The minimal-pair pairing; ≥ 30 twins per split, or the build stops (T19) |
| The gate's G1 / G2 measure an unscoped retrieval the runs never do | Scoped stage 2 (T24) |
| The split puts a probe and its target apart | Units; W2 in the builder and in the gate |
| G1 / G2 count pairs whose two queries sit in different files | G1 within split, G2 per split |
| The same policy question about two products reaches both splits | Product-free policy units |
| A step needs the split before the split exists (B-cross, D) | Product-pair units; D has no split rule (review M4) |
| One rank draw shifts a stratum's traffic, or traffic is read as record share | The stratified rank; exact traffic shares reported (review L5) |
| Online runs see almost no Tier-2 decisions or traps, and the result is read as "the rule is safe" | The LRU simulation in the build report; §8 A4's static warm set; carried to 6.1 |
| A per-stratum false-hit rate moves with the cell size or the cache content | §8 A1: figures per (query, judged candidate) pair |
| Traps nobody built hide in A | `nearest_foreign_cos` (review M3) |
| `K` over the whole file sets a capacity half the run's working set | `K` per run file, ADR-013 |
| A split file is changed after the freeze | The gate re-derives and hashes all three (T18) |
| Claude's wording matches Claude's policy text, helping retrieval and `S_lex` | R7 `pqa-template`, R10, §8 A3's robustness row (review M6) |
| A risky product reaches a policy or D query | W6 on title and specs |
| Two queries normalise to one Tier-1 key | W5 |
| PQA text or an asin reaches git | `.gitignore` first; the allow-list; sheets refused inside the repository; trail evidence counts only |
| The model layer or the vectors change after a build | sha256 in the manifest; batch hashes committed; `workload-verify` |
| Claude's labels drift over many batches | `RELABEL = 40` questions labelled twice in different batches; agreement reported |

## 8. Pre-registered analysis rules (in `rules.md`, before the first sheet; review Q11)

The workload fixes what these figures can mean, so the rules are fixed with it. Phase 6 computes
them; changing one needs an ADR.

- **A1 — Pair level** (review M2, Q4). Per-stratum figures and RQ2a are computed per (query, judged
  candidate) pair: `candidate_entry_id` → the MISS record that wrote the entry (I9 guarantees one) →
  its `query_normalized` → the workload record → its `cluster_id`, `doc_ids` and `probe_kind`. RQ2a
  = the share of condition-twin requests, made while their twin's entry was live, that were served
  from it. Per-stratum results are also given by the logged `similarity` in bins of 0.02 from 0.80.
- **A2 — Which probes each figure reads** (review H1). "B-within against B-cross" (§9.2 (ii)) reads
  the provenance-different kinds: `policy-kind`, `policy-region`, `name-swap`, and the
  `spec-attribute` and `natural` probes whose 3.6 measurement shows different evidence chunks. RQ2a
  reads `policy-condition` and `condition-department`. `name-swap-same` is never a trap and appears
  only in the namespace-cost row.
- **A3 — A robustness row by wording source** (review M6 c). The headline is also reported on
  `origin ∈ {pqa, pqa-template}` alone.
- **A4 — The static arm's warm set** (review M1). Warm with one record per cluster (its lowest rank)
  plus every `pair_of` target; replay every other record once, in rank order. Item 6.3 uses this set
  unless an ADR changes it.

## 9. Unknowns that still need verifying

- **U1 — The true answerable yield** (ADR-011: ≈ 410 of 1,180, 285 – 560). Below about 200, the
  spec half shrinks. Measured in pass 1; the constants do not move.
- **U2 — Where Claude's paraphrases fall against 0.85.** The short name in every query may hold
  short questions above 0.85, so C could be nearly empty. The step-0 pilot gives a first view on
  synthetic text; step 4 measures it.
- **U3 — Whether B-cross probes reach 0.85.** Different names may pull them below. Pilot, then step 4.
- **U4 — Same-product similarity in general.** Naming the product raises the similarity of
  unrelated questions on one product. Reported through `nearest_foreign_cos`.
- **U5 — How many real policy questions survive R7.** Counted.
- **U6 — G1 and G2 at 3.6**, now per split and scoped. If either fails, "fix the corpus" may reach
  this workload and reopen 3.4. Step 4's vectors give an early count of cross-cluster pairs above
  0.85 per split.
- **U7 — In-session throughput and consistency** over about 1,500 labels and 1,500 written queries.
  The repeat sample measures drift.
- **U8 — Whether runs should send `product_id`** (impact F6). P1.
- **U9 — The leak that remains:** one shape on two departments' documents in different splits.
  Not a same-source leak; the highest cross-split cosine between same-document queries is reported.
- **U10 — The lane band** (impact F7): with MIXED enabled at 6.1, a policy query naming a product
  may be namespaced per product. 3.6 measures `policy_frac`.
- **U11 — Is a Claude-answerable query answerable from its scoped top-k?** If the evidence chunk is
  not retrieved, both references say "not available" and the trap cannot fire. 3.6 maps each
  evidence span to its chunk and checks the scoped retrieval returns it.
- **U12 — Provenance difference per built probe** (review H1). 3.6.
- **U13 — The pilot** (step 0) itself: synthetic text may not behave like PQA wording.
- **U14 — Tier-2 decisions and trap encounters per skew** (review M1): the LRU simulation gives the
  expectation; 7.1 measures it.
- **U15 — How 5.1's rubric scores** a reused answer that names the wrong product, or a
  same-polarity "Yes.". It decides whether `name-swap-same` hits are false.
- **U16 — Thin natural traps** (review U16). Policy B-within will be about 100 % built; natural spec
  B-within with an answerable probe is probably tens at most. `data-card.md:148` ("PQA supplies
  B-within traps naturally") must be restated with the real count.

## 10. The proposed answers, with reasons

1. **Keep "the labeller is not the judge".** One model doing both would share its blind spots across
   the population and the verdict; the ~100-pair human check validates only the judge; Claude also
   wrote the policies (impact F15). 5.1 picks a judge that is not Claude, or ADR-013 says why the
   rule may go.
2. **In this session, from scratchpad sheets.** No dependency, no key, PQA text never in git. The
   API path adds both but not repeatability: a re-run writes new text, so a new `K`, strata and
   split (impact F9). Both send PQA text to Anthropic; ADR-013 records it.
3. **Claude writes paraphrases and lookalikes too**, under R4 – R6 and R10; data-card §4's
   "generation model / prompt" is the model id and `rules.md`'s sha256.
4. **A and C by measurement**, as a header label, with similarity bins beside (§8 A1).
5. **Product-pair and (shape group, department) units**, with the minimal-pair pairing (§2.5).
6. **`K` per run file.**
7. **About 1,500**, with effort on twins rather than spec lookalikes (review Q7).
8. **`answerable` as a field**, not a sixth stratum (the §H enum stays).
9. **Policy queries name a product** (U10 is the risk).
10. **`product_id` whenever a product is named** (§3).
11. **ADR-013 (data) at the end for the counts**; the analysis rules (§8) and the constants go in
    `rules.md` **before** the first sheet.
12. **Unanswerable queries ride in the run files**, reported apart by their own `answerable`;
    ADR-011's "separate stratum" becomes "separate population".
13. **Rank per record, stratified** (§2.6); the reviewer found the rank rule moves Tier-2 volume by
    at most 1.5×.
14. **G1 within split and G2 per split** (§2.7).

## 11. Carried forward

- **To 3.6:** the gate's digest over the three files (the gate re-derives them); `K_validation`,
  `K_test`, `K_total` and the capacity rule; G1 / G2 per split on the ingested `v1`, scoped, with
  unscoped beside; per-stratum and per-`probe_kind` counts and the trap fraction, per split; per
  probe, the scoped-retrieval Jaccard and the evidence-chunk check (U11, U12); `policy_frac` of the
  policy queries under each candidate band (U10).
- **To 5.1 and 5.2:** the judge is not Claude (open question 1); the ~100 human-verified pairs are
  not Claude-marked (impact F15); the rubric for a wrong-product answer and a same-polarity "Yes."
  (U15).
- **To 6.1 / 6.3:** §8 A1 – A4; the frontier excludes Tier-1 repeats or is computed on the static
  arm (review M1).
- **To 7.2:** `mu_hit.js` tier-2 mode reads a `paraphrase` field from the first 20 records (impact
  F19); its probe file is 7.2's to build from this workload.
- **To P1:** the run identity names the run file (and a `product_id` variant, if one is made), and
  the run sets `CACHE_CAPACITY = round(0.25 × K)` of that file. The comment at
  `gateway/cmd/gateway/main.go:267-268` still gives the old meaning of `K`; P1 updates it with the
  wiring (comment only).
