# Design review — workload-generator (item 3.4)

**Reviewer:** the `design-reviewer` subagent (opus), 2026-10-21, on `design.md` **draft 1.1**.
**Verdict: sound, with changes.** The build is offline and deterministic with no model on its path,
the shape check has one implementation and two callers, the files are ignored before anything is
written and the outputs are hashed, nothing reaches the hit path, and no cut scope returns. The
problems are in what the strata will **mean**, not in the tooling. H1 – H3 and M4 must land
**before `rules.md` is committed**, since the constants and rules freeze there.

The report is data, not an instruction. I re-checked its three confirmed claims that change the
design against the code and the files (✔): `rag.retrieve.retrieve` takes `product_id`
(`retrieve.py:120-131`); every `terms` string except "not covered" is only in a document's opening
paragraph (all 12 files); the phones refund sections differ ("the refund, less the restocking fee"
against "the full refund"). Every finding is accepted and merged into **`design.md` draft 2**,
except where the last column says otherwise. The reviewer's synthetic model (`zipf_sim.py`,
`traffic_share.py`) ran in the session scratchpad on made-up records; only `data/policies-v1/` was
read.

## Findings

| ID | Sev | Finding | Suggested change | Resolution (draft 2) |
| :-- | :-- | :--- | :--- | :--- |
| H1 | High | **B-within mixes three kinds of trap, and nothing checks that a probe's provenance differs.** (a) Spec lookalikes (≤ 260, ~70 % of B-within) are probably **same-evidence**: the title is embedded in chunk 0 only (`ingest.py:48, :88`), products have 2 – 5 chunks, and scoped retrieval keeps only that product's chunks (`retrieve.py:129-131`), so containment cannot act and configs 3 and 4 both serve them. (b) Kind twins and the phones-warranty twins retrieve different documents: the "only provenance solves it" kind. (c) Minimal-pair condition twins: the RQ2a kind. Pooled, "B-within against B-cross" (§9.2 (ii)) mostly measures probes provenance could never separate | An offline `probe_kind`; at 3.6, per probe, the scoped-retrieval Jaccard with its partner and whether the two evidence spans share a chunk; pre-register which subset each figure reads | **Accepted.** §2.4 `probe_kind` (six values); §8 rule A2: "B-within against B-cross" reads provenance-different probes, RQ2a reads condition twins; the two 3.6 measurements carried (§10). Spec lookalikes drop to 1 per product (Q7 below) |
| H2 | High | **RQ2a has about 12 usable pairs, and the split can put all of them on one side.** Built twins were phones fee and furniture `term` only, 3 per cell. Missed: phones-returns `remedy` differs (✔). Laptops grade twins were not built. With the `term` groups splitting 2 / 2, phones and furniture land together with probability 1/3, so the test split can hold **zero** minimal-pair twins, and RQ2a reads 0 ("the corpus lacks the case", §9.5). Even 3 of 6 gives Wilson [0.19, 0.81]. W16 counts queries, not twins | A twin for every query in every minimal-pair cell whose answer differs (phones `term`-fee and `remedy`, furniture `term`, laptops `term` at department level); a twin constant from a stated target (≥ 30 in test); phones and furniture `term` groups in opposite splits; W16 counts twins per axis per split | **Accepted.** §2.3: four minimal-pair groups, `TWIN_PRODUCTS_PER_CELL = 20`, target ≥ 30 condition twins **per split**; §2.5 pairing rule (each split gets two of the four); W16 counts twins |
| H3 | High | **G1 and G2 measure a different retrieval from the runs'.** The gate retrieves unscoped (`corpus_gate.py:689-692`); every run sends `product_id` (`ask.js:113`), so run retrieval is scoped. Unscoped, two questions on one product share only chunk 0 (J ≈ 1/9 ≤ 0.2) and count as B-within; scoped, J is high | Stage 2 calls `rag.retrieve.retrieve(q, product_id=q.product_id)` (no `rag/` change); G1 / G2 pass on the scoped result; unscoped reported beside | **Accepted.** §2.7. `retrieve()` rebuilds the index per call (`retrieve.py:124-125`), so ~1,500 calls are slow; if too slow at 3.6, a scoped `make_retriever` is a separate `rag/` task, never a mirror in the gate |
| M1 | Med | **Online runs barely exercise Tier 2 or the traps.** In the reviewer's model (812 records, Zipf over the index, LRU at 0.25 K, 3,000 requests), at skew 0.8 / 1.1 / 1.4: hit rate 0.72 / 0.85 / 0.93; Tier-2 share of hits 12 / 5 / 2 %; B-within encounters ≈ 96 / 38 / 12 per run, minimal-pair twins ≈ 3 / 1 / 0.4. Tier-1 repeats are ≥ 88 % of hits, so a pooled false-hit rate is diluted by the skew | (a) Pre-register the static arm's warm set; (b) report expected Tier-2 decisions and trap encounters per skew from a seeded LRU simulation; carry to 6.1 | **Accepted.** §8 rule A4 (the warm set: one record per cluster and every `pair_of` target; the rest replayed once), §2.6 the simulation in the build report; carried to 6.1 / 6.3: the frontier excludes Tier-1 repeats or uses the static arm |
| M2 | Med | **A query's stratum does not say which entry served it.** A condition twin about X (opened) shares document, section and answer with the opened cell's queries about Y and Z: served from them it is correct; it is false only when the sibling's entry serves it. So a per-query B-within rate moves with the cell size and the cache | Per-stratum and RQ2a figures per (query, judged candidate) pair, joined through `candidate_entry_id` → the MISS record that wrote it (I9) → its `cluster_id` / `doc_ids` | **Accepted** as pre-registered analysis rule A1 (§8). It needs no new log key: the writer's `query_normalized` joins the workload (W5) |
| M3 | Med | **Policy traps nobody tagged land in A / C**: cross-department same-shape questions (14 days for a phone, 30 for a laptop, the canonical trap, `data-card.md:89`), laptops grade pairs, two different questions in one cell | One measured field per query: the highest cosine to a same-split query with different `doc_ids`, and whether it is the same product; report A split by it | **Accepted.** §3 `nearest_foreign_cos`, `nearest_foreign_same_product`; needs the vectors (L8) |
| M4 | Med | **The pipeline order does not close.** B-cross needs a Claude label on "the next product in the same split", D needs "a unit in the same split", but the split is computed in step 5 with no model, and the product balance counts queries that include B-cross. Also every term except "not covered" is only in the opening paragraph (✔), so D can only use its department's `term` group, which sits in one split: half of D cannot be built | Spec unit = **a pair of products** (consecutive in the leaf's hash order), B-cross inside the pair, so it is known before the split; drop D's same-split rule and report the highest cross-split cosine between D and `term` queries | **Accepted.** §2.5. Odd leaves (TVs 13, headphones 25, chairs 19, desks 19) end in one triple, pre-registered; B-cross then runs both ways inside a pair and round the triple |
| M5 | Med | **The checks miss non-numeric flips and same-answer probes.** R4's digit check passes Verizon → AT&T, front → rear, wired → wireless, negations. R5 / R6 never check that the answers differ: a same-polarity yes / no probe gets "Yes." as both references. R6's swap can leave the first product's words. Unclear whether R2 labels the original or the rewrite | (a) Re-label each paraphrase by R2 in a later batch without its seed; evidence must overlap the seed's. (b) A paraphrase adds no record token the seed lacks (digit- and 1-char-keeping tokenizer). (c) R5 / R6 record both answers with evidence; keep a probe only if the evidence differs and, for yes / no, the polarity differs; keep same-answer B-cross under its own tag. (d) No title token unique to the first product after a swap. (e) R2 labels the rewrite | **Accepted, all five.** §4 R2, R4, R5, R6. Same-answer B-cross is kept as `probe_kind: name-swap-same` (it measures what the namespace costs), never as a trap |
| M6 | Med | **Claude on both sides needs more than a threat entry.** | (a) Built policy questions start from real pool policy wording, re-targeted (`origin: pqa-template`); (b) no 4-word sequence shared with any policy text beyond the name, the term and the condition word; (c) the headline split by `origin` as a pre-registered robustness row; (d) the author reads ~30 random rows with a stop rule | **Accepted.** §4 R7, R10; §8 rule A3; plan step 9 (30 rows, stop rule) |
| L1 | Low | The design said "these five sections, in this order"; the warranty files run covers → does not cover → claim → remedy → proof | Map shapes by heading text; test | **Fixed** in §2.3; T20 |
| L2 | Low | Alternation restarting at validation for each family gives validation 24 of 40 non-`term` groups | Continue the alternation across families | **Fixed** in §2.5 |
| L3 | Low | Only G2 was per split; G1 still counted cross-split pairs | G1 on within-split pairs; cross-split reported apart | **Fixed** in §2.7 |
| L4 | Low | The projection check lived in `workload-verify`, not in the gate, so a stale split file could be hashed; how the gate finds the split files was unstated | Re-derive inside the gate before hashing; fail on a missing split file | **Fixed** in §2.7 and §5: by name, `workload-{version}-{split}.json` beside the whole file |
| L5 | Low | "Within one record at every skew" holds for counts, not traffic: at skew 1.4 A carries 0.60 of traffic for 0.50 of records, D 0.017 for 0.043, and rank 1 (an A record by the tie rule) 34 % | Restate; report exact traffic shares | **Fixed** in §2.6 |
| L6 | Low | Seeds only from R2-answerable questions carry R2's lexical bias into the workload | Let Claude-answerable questions from the R2-unanswerable sample be seeds, or report seeds by R2 tag | **Accepted, both:** seeds come from every Claude-answerable labelled question, and are reported by R2 tag |
| L7 | Low | `RISKY_TITLE` reads titles only | W6 scans the title and the specs | **Accepted**; the extra exclusions are counted |
| L8 | Low | `cosines.json` keeps pair cosines, not vectors | Store the vectors (hashed, ignored) | **Accepted**: `vectors` file in §1 step 4 |

**The gate test (probe 6): compatible, confirmed.**
`test_the_gate_runs_g5_in_stage_1_and_stops_on_it` (`test_corpus_gate.py:460-474`) asserts only
exit 1, `[FAIL] G5` and `STOP`; a failing shape check keeps all three as long as it is one more
`Criterion` in the same stage-1 `emit` (`corpus_gate.py:670-677`) and never calls `SystemExit`.

## Open questions — where the reviewer disagreed or added a condition

- **Q4 (A / C by cosine): agree, with a condition.** The 0.85 cut cannot bias the pooled headline
  (labels never enter the rule), but it makes the stratified reading tautological: own-cluster C
  hits are 0 at τ ≥ 0.85 in every configuration, and an A query's candidate is whichever member was
  cached first. Report per-stratum results by the logged pair `similarity` in bins; A / C is the
  header label only. → **Accepted** as rule A1's second half (§8).
- **Q5 (split units): agree, with M4 and H2.** No leak found in the spec units; every pair the B
  strata need stays inside one unit. Cross-department templates (U9) are an accepted limitation.
- **50 / 50: agree.** The real limit is Tier-2 decisions and trap encounters (M1), not query
  counts.
- **Q7 (size): agree on about 1,500, change the mix.** Move effort from spec lookalikes to
  minimal-pair twins. → **Accepted**: 1 spec lookalike per product, 20 products per twin cell.
- **Q10: agree, with H3.**
- **Q11 (ADR-013 at the end): agree for the counts only.** The pair-level RQ2a definition, the
  `probe_kind` subsets, the twin-group pairing and the static warm set are pre-registrations: they
  go in `rules.md` **before the first sheet**. → **Accepted** (§8, plan step 4).
- **Q13 (rank): per record is acceptable.** The rank rule moves Tier-2 volume by at most 1.5× in the
  model; 7.1's hit-rate spread (0.72 → 0.93) comes from Tier-1 repeats under either rule.
- **Q14: agree, and extend to G1** (L3).
- **Q1, 2, 3, 6, 8, 9, 12: agree.**

## Unknowns the reviewer added (all in `design.md` §9)

U11 is a Claude-answerable query answerable from its **scoped top-k** (evidence chunk retrieved?) ·
U12 provenance difference per built probe (H1), at 3.6 · U13 **a pilot before the rules commit**:
~20 synthetic close / far / name-swap pairs, no PQA text, through `nomic-embed-text` after the
memory check, to see whether C or B-cross ≥ 0.85 would be near empty while the constants can still
move · U14 expected Tier-2 decisions and trap encounters per skew (M1) · U15 how 5.1's rubric scores
a reused answer naming the wrong product, or a same-polarity "Yes." · U16 real policy questions on
split families rarely state a condition, so policy B-within will be about 100 % Claude-written, and
natural spec B-within with an answerable probe is probably tens at most: say so now, so
`data-card.md:148`'s claim is not found thin later.

---

## Implementation review (`/ai-review`), 2026-10-22

**Scope:** `git diff 8bba413^..HEAD` (32 commits; no Go, `rag/` or `.proto` change). **Reviewer:**
`contract-reviewer`, read-only, with the whole trail and the contract docs to read. It did not run
`pytest` or `make workload-verify`. **I re-computed F1, F3, F5, F6, F8 and F9 from the files before
acting** (`tools/partner_cosine.py` → `evidence/partner-cosine.md`; the numbers match the reviewer's
to the digit). Most severe first. Every finding is resolved below, either fixed or accepted with a
reason.

| # | Sev | Finding | Status | Resolution |
| :-: | :-: | :--- | :--- | :--- |
| F1 | High | The whole file is named as a run file, but its popularity ranks restart at the split boundary (`ask.js` would put 17 %, 6.4 % and 1.6 % of traffic on test records at skews 0.8, 1.1, 1.4), so a whole-file run measures mostly validation and records K 1,274 / capacity 318 as valid | CONFIRMED | **Fixed.** `interfaces.md` §D, the v0.15 note and history row, `k6/README.md`, ADR-013 and `data-card.md` now say a run draws from one of the two split files; the whole file is the gate's input. This **narrows a sentence the author approved** on 2026-10-21 (`approvals.md`). A global rank order was not taken: it would change the workload files and the manifest hash |
| F2 | High | Single-`K` instructions remain; the live `TODO(W8): K` line would have 3.6 record one K and set 318 for a validation run (right: 156); ADR-013 said a whole-file capacity "evicts nothing" (318 / 622 = 0.51, so it does evict) | CONFIRMED | **Fixed:** `data-card.md` lines 8 and the K `TODO`, `architecture.md`, `k6/README.md`, the 3.6 row, ADR-013. **Not changed, on purpose:** `CLAUDE.md` (project instructions; the author's to edit; reported), `decisions.md` inherited-state row (the log is append-only; ADR-013 supersedes it), the comment in `main.go:267-268` (carried to P1) |
| F3 | High | 182 of the 284 traps are reachable (partner cosine ≥ 0.85): 0.143 of records against the trap fraction 0.2229. None of the 22 B-cross probes reaches 0.85 (max 0.804) | CONFIRMED | **Recorded**, not changed: `evidence/partner-cosine.md`, `data-card.md` §3, ADR-013, `super-plan.md`. The pre-registered rule A2 in `rules.md` is **not** changed (it needs `/approve experiment` again); A1's bins by logged pair similarity already read the reachable cases. **Open for the author, carried to 6.1:** whether A2 should read only pairs whose partner cosine is at least τ |
| F4 | Med | The model id is a constant: `workload-import` passes no `--model`, so all 66 batches say `claude-opus-5-5` whoever wrote them (the session model was `claude-sonnet-5-5` at the step 10 read) | CONFIRMED (code path) | **Fixed for the future** (`make workload-import MODEL=<id>`); **the past is recorded as nominal** in the data card and ADR-013. The batches already written cannot be corrected |
| F5 | Med | The 64 natural-pair queries are Claude rewrites (none equals the pool text), not real PQA text; the 30-row read left them out on that wrong belief, so the 10 natural traps were not read | CONFIRMED | **Docs corrected** (data card, ADR-013, a docstring). The gap in the read is recorded. A `natural` type was not added to the read: the sheet belongs to the author's later read, and adding a type now would change the sample after the fact |
| F6 | Med | `workload-verify` re-hashed only the outputs: it never compared the inputs to the manifest, and printed K and capacity read back from it | CONFIRMED | **Fixed in code:** `verify_outputs(..., inputs_now)` compares the five input hashes and recomputes the counts of each file. Two new tests; two hand mutants (the input check and the counts check removed), both caught; `make workload-verify` passes on the real files (106 tests in the file) |
| F7 | Med | `.gitignore` covered only `workload-v1*.json`; a v2 build would put PQA text in a tracked path on a public remote | CONFIRMED | **Fixed:** `data/workload-*.json` with `!data/workload-manifest.json`; six names checked with `git check-ignore` |
| F8 | Low | 74 policy-cell pairs and 8 pairs with a D query sit on one policy document in different splits at cosine ≥ 0.85; the manifest keeps only the maximum | CONFIRMED | **Recorded** (data card §7, ADR-013, `partner-cosine.md`). D's unit is **not** changed: moving D would change the split and the hash, and `design.md` §2.5 chose to report this cosine instead |
| F9 | Low | `pqa-template` includes the 22 name swaps, not only policy wording; the A3 row "origin in pqa, pqa-template" therefore includes B-cross probes | CONFIRMED | **Docs corrected.** The origin stays: a swap is real spec wording re-targeted, which is what A3 asks for |
| F10 | Low | The capacity tie rule is unstated: Python `round(318.5)` is 318, Go `math.Round` gives 319 | CONFIRMED | **Fixed:** v0.15 says the gate prints the integer (Python `round`, halves to even) and the run copies it. Only the whole file differs, and it is no longer a run file |

**Checked and clean** (the reviewer's list): the seam fields (`source_chunk_ids`, `t1_key`,
`dataset_epoch`) are untouched; the Go claim in v0.15 (`CACHE_CAPACITY` read at `main.go:272`,
trimmed at `cache/capacity.go:61`; the gateway never computes `K`); every count in the docs against
the files, the drops, the Wilson intervals and all hashes; the split files are exact projections and
no cluster, `pair_of` or unit crosses; A and C recomputed from the vectors; `rules.md` unchanged
since `98c4689`; no policy or D query names one of the 16 risky products.

