# Plan — RAG correctness before item 5.1

Written 2026-10-31, before any step below runs. Not a task trail: a light plan chosen by the author to move fast,
as with ADR-020. The ADRs it produces are the record. Item 5.1 (`docs/work/2026-10-30-judge-harness/`) waits at
`spec` until this plan closes, and its ADR and contract numbers are renumbered then.

**Why.** Manual tests and probes on 2026-10-31 (`v1`, citable: no) found answers that are wrong at the MISS, before
any cache reuse. Item 5.1 freezes references and the judge, so the RAG and the generator must be settled first.
- **Spec retrieval keeps one chunk.** 231 of 431 validation spec questions get only 1 chunk of their own product
  (the natural top 5 is mostly other products' chunks, which are dropped). Cases: "What comes in the box?" and
  "How long does a full charge take?" answer "not in the context", though the answer is in another chunk.
- **The generator's wording fails the support gate.** 14 of 30 fresh answers score `S_lex < 0.6` against their
  own evidence; the words missing most are "context", "based", "according".

**Order:** §1 → §2 → §3, then back to 5.1.

**The author's decisions, 2026-10-31.** X = 15 and Y = 5 are confirmed (§3), before any measurement. Steps may run
at memory pressure 2, including §2; every result line records the readings. One review at the end, plus two stops:
before 1.5 (the author stops `make dev`) and before 3.1. §1 runs 1.2's red tests first, before `retrieve.py` changes.

## §1 Spec-lane retrieval keeps enough of the product's own chunks (ADR-021)

**The change.** In `rag/src/rag/retrieve.py`, when `product_id` is set, the slots that held another product's
chunks are refilled with this product's best unused chunks (one search filtered on `doc_id`), in score order,
before ADR-020's category swap. Two variants are measured:
- **V1, always refill.**
- **V2, refill only when the natural top k holds no policy chunk** (a pure spec question). Every lane is unchanged
  by construction.

**Choice rule, fixed now.** Take V1 if, on the validation split, it changes no lane count under either MIXED arm.
Otherwise take V2.

- [x] 1.1 Measure both variants on the validation split (embedding only, citable: no): own-chunk count per spec
  question, lane counts (MIXED off and on), the category probe, the condition-routing probe.
  - Result: 2026-10-31, pressure 1 / 1, `variant-probe-output.txt`. One-chunk spec questions: before 231, V1 96, V2 98. Lanes, MIXED off: unchanged for both. MIXED on: V1 moves MIXED 24 -> 30 and POLICY 162 -> 156; V2 unchanged. Category 0, rank-1 policy not gold 26 / 167, condition-routing 99/121, 9/13, 24/43, all three alike. Cases 0/5 before, 5/5 for both. **By the rule: V2.**
- [x] 1.2 **Tests first, shown failing on the current code.** New file `rag/tests/test_retrieve_own_chunks.py`:
  - live: each of the five cases seen on 2026-10-31 must retrieve the chunk that holds its answer:

    | product | question | must retrieve |
    | :--- | :--- | :--- |
    | `product-electronics-b07r8pr5yz` | What comes in the box? | `#chunk-5` |
    | `product-electronics-b07r8pr5yz` | How long does a full charge take? | `#chunk-0` or `#chunk-5` |
    | `product-electronics-b07b63r768` | Are these headphones foldable? | `#chunk-1` |
    | `product-electronics-b07b63r768` | What is the standby time? | `#chunk-1` |
    | `product-electronics-b07b63r768` | Is a carrying case included? | `#chunk-1` |

  - pure: no chunk twice; at most `top_k`; no other product's chunk; product slots in score order; under V2, a
    retrieval that holds a policy chunk is returned untouched.

  Pass: the live tests FAIL on today's code (the run is kept in this folder). A test that passes before the fix
  is rewritten or dropped, never kept as evidence.
  - Result: 2026-10-31, pressure 1. The five live tests failed on the ADR-020 retrieval, each on the chunk the baseline recorded (`red-run.txt`). Six pure tests added with the code (`_refill_own`).
- [x] 1.3 Apply the chosen variant. Pass: every test of 1.2 passes.
  - Result: V2 applied (`_REFILL_POLICY_FREE_ONLY = True`). 29 / 29 pass: the 11 new tests and the existing scoping, category and texts tests, unchanged.
- [x] 1.4 **Retrieval checks** (embedding only, citable: no): the share of spec questions with 1 own chunk drops from
  231 / 431; lane counts with MIXED off are unchanged; category probe still 0; condition-routing not worse than
  99 / 121, 9 / 13, 24 / 43; the existing scoping and category tests pass unchanged; `make seam-check` and
  `make verify` pass.
  - Result: 2026-10-31, pressure 1. One-chunk spec questions 231 -> 98; lane counts unchanged under both arms; category 0; condition-routing unchanged. `make seam-check` PASS. `make verify` exit 0, nothing SKIPPED (rag 83, experiments 778, Go ok).
- [x] 1.5 **Answer checks, end to end** (loads the LLM, citable: no). Restart `make dev` after `make cache-reset`.
  - Ask each of the five questions of 1.2 three times. Pass: the answer states the fact (the box list; 1.5–2 hours;
    foldable; 400 hours of standby; the carrying bag) in at least 2 of 3.
  - Re-run `product_pairs.py` (8 traps, 8 paraphrases) and `tier2_probe.py B` (self-support of 30 answers). Pass:
    no trap T1 – T8 becomes a TIER2_HIT. Report the false misses and the self-support share against `baseline.md`.
  - Result: 2026-10-31, pressure 1–2 (each output file records it), every run from a cold cache. **FAIL on two counts; accepted by the author on 2026-10-31 as failed, causes known (no RCA), and recorded in ADR-021.** Answers (`answer_checks.py`, `evidence/private/answer-checks-round{1,2,3}.txt`): box 3/3, charge 2/3, foldable 3/3, standby 2/3, carrying case **0/3**: `chunk-1` ("provided EVA carrying bag") is retrieved every time, and the model answers "No". Traps (`evidence/private/product-pairs-after.txt`; the outputs quote corpus text, so they sit in the gitignored folder): **T2 became a TIER2_HIT** (similarity 0.907; A1 "15 hours", `S_lex` 1.00; served to the 12 h question). This is the same-evidence, opposite-condition residual: the baseline refused it only because its A1 was longer (`S_lex` 0.43). T1, T3 – T6, T8 MISS; T7 a TIER1_HIT on this product's own earlier entry, as in the baseline. Paraphrases 2/8 hit (P5, P6), baseline 0/8. Self-support (`self-support-after.txt`): 19/29 (66 %), baseline 16/30; SPEC 10/16 (was 7/17), POLICY 9/13 unchanged.
- [x] 1.6 Record: ADR-021, `interfaces.md` §B v0.27, evidence (scripts and before / after outputs) in this folder.
  - Result: ADR-021 (with its summary row) and `interfaces.md` v0.27 written 2026-10-31, before 1.5; ADR-021's open item names 1.5 and §2. Evidence here: `variant_probe.py`, `variant-probe-output.txt`, `red-run.txt`.

## §2 G1 and G2 on the new retrieval

One run covers ADR-020 and ADR-021. **Only in green pressure** (reading 1 before and after; otherwise repeat).
G1 fails by design (ADR-014), so the command exits non-zero; only the numbers matter.

- [x] 2.1 `make gate-corpus REPORT=data/v1-draft/gate/after-adr-021/report.json RETRIEVAL_OUT=data/v1-draft/gate/after-adr-021 VECTORS=data/v1-draft/workload/vectors.json`
  Pass: the report file exists, and the pressure readings in it are all 1.
  - Result: 2026-10-31, run while the author's gateway was up (the gate does not use it). Report written; pressure 1 in all 53 readings. Exit 2 (G1, as expected). Index check PASS; the snapshot digest would be `a5708fefa62c…`, the frozen one. G1 21 -> 26 (validation 17, test 9), still FAILED; G2 B-within 3 -> 7 (validation), 3 -> 4 (test), B-cross 10 and 5 unchanged; overlap mean 0.797 -> 0.835, variance 0.0769 -> 0.0713, J <= 0.2 across splits 39 -> 43.
- [x] 2.2 Record G1, G2 and the source-overlap distribution in ADR-021, and replace the pending note in
  `data-card.md` §7. `data/v1-freeze.json` is not rewritten.
  - Result: Recorded in ADR-021 and in `data-card.md` §7 (the pending note replaced). `data/v1-freeze.json` untouched.

## §3 The generator's prompt (ADR-022 only if it changes)

**The candidate, fixed now** (the only one measured; no other prompt is tried):

```
Answer the question using ONLY the context below. Answer directly in one or two sentences, using the words and
numbers of the context. Do not mention the context or say where the information is. If the answer is not
contained in the context, say you don't know.

Context:
{context}

Question: {query}
Answer:
```

**Measurement, fixed now.** Validation split only. For every paraphrase-with-seed pair (281) and every B-within
probe-with-its-pair (124): generate the first question's answer with each prompt (the frozen generator and
settings, one sample each), retrieve the second question's evidence, and run the **gateway's own gate code**
(similarity, namespace, both support arms; not a re-implementation). A pair **passes** if all of them admit it.

**Decision rule, fixed now.** Adopt the candidate only if both hold:
- the paraphrase pass rate rises by at least **X = 15** percentage points;
- the B-within trap pass rate rises by at most **Y = 5** percentage points.
(X and Y confirmed by the author on 2026-10-31, before 3.1.) Reported beside, never part of the rule: the
share of "don't know" answers on `answerable: true` questions, under each prompt.

- [x] 3.1 Run the measurement (loads the LLM, citable: no). Evidence in this folder.
  - Fixed before the run (author, 2026-10-31): τ = 0.85, the gateway's default, with the lane band at its default
    (MIXED off); the candidate's instruction is one paragraph, as in the old prompt (the line breaks above are the
    page's wrapping). Harness: `prompt_probe.py` and `gateway/cmd/gateprobe` (the gateway's own `embed` and
    `reuse` code); before the run it reproduced the live T2 (similarity 0.907, served) and T8 (namespace).
  - Result: 2026-10-31, finished 19:18, exit 0; pressure 1 in 438 of 440 readings (2 at 2). 405 / 405 pairs judged (`evidence/prompt-probe-summary.txt`, `evidence/prompt-probe-results.jsonl`; text under `evidence/private/prompt-probe/`). Paraphrase pass: old 88 / 281 (31.3 %), new 102 / 281 (36.3 %), **+5.0 points**. B-within pass: 42 / 124 (33.9 %) under both, **+0.0** (16 pairs change, as many each way). Beside the rule: "don't know" on answerable first questions 17 / 200 old, 14 / 200 new; median answer 44 vs 29 words. Also seen: 36 of the 42 B-within passes are policy-condition pairs in which one question retrieved the other condition's policy document first (18 each way).
- [x] 3.2 Apply the rule. If adopted: change `rag/src/rag/generate.py`, write ADR-022, and note it in item 5.1's
  spec (its references use the generator). If not: record the measured cost of the old prompt in ADR-021.
  - Result: +5.0 < 15, so the candidate is **not adopted**. `generate.py` unchanged, no ADR-022. The old prompt's measured cost, and the B-within passes, recorded in ADR-021.
- [x] 3.3 **Only if adopted, verify.** A new test pins the prompt template (its sha256), so a later edit fails it.
  `make verify` passes. Then, as in 1.5, after a restart and `make cache-reset`: re-run `product_pairs.py` and
  `tier2_probe.py B`. Pass: no trap T1 – T8 becomes a TIER2_HIT; the five answers of 1.5 still state their facts
  in at least 2 of 3. Report the self-support share and the "don't know" share against §1's numbers.
  - Result: not applicable: the candidate was not adopted (3.2).

## Closing

- [x] Item 5.1's spec renumbered to the next free ADR and `interfaces.md` version; `retrieval_version` names the
  ADR-021 retrieval. The super-plan's Phase 5 note says this plan closed.
  - Result: 2026-10-31. 5.1's `design.md` now names ADR-022 and v0.28; `RETRIEVAL_VERSION`'s first value is the ADR-021 retrieval. Also added at the author's instruction: the B-within fact of §3.1, and a *retrieval miss* now includes a POLICY request whose namespace document is not gold. ADR-020's and ADR-021's forward references and the super-plan's Phase 5 note updated. **Plan closed.**
