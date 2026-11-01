# Baseline — before §1 (2026-10-31)

The numbers §1.5 and §3.3 compare against. Taken on 2026-10-31 after ADR-020, before any step of `plan.md`.
**Conditions:** `v1` in Redis; the author's demo gateway (`make dev`: gate on, MIXED off, τ = 0.85, evaluation log
off); pressure 1–2; the generator at `temperature 1`, one sample per question. **citable: no.**

Re-run from the repo root, with `make dev` running: `python3 docs/work/2026-10-31-rag-correctness/product_pairs.py`
and `python3 docs/work/2026-10-31-rag-correctness/tier2_probe.py B`. Each run writes cache entries: stop the
gateway and run `make cache-reset` before a run that must start cold.

## Retrieval: own-product chunks per spec question (validation, 431 questions with a `product_id`)

| chunks of its own product | 1 | 2 | 3 | 4 | 5 |
| :--- | ---: | ---: | ---: | ---: | ---: |
| questions | **231** | 123 | 48 | 22 | 7 |

Mean share of the product's chunks retrieved: 0.65. Products have 1 – 8 chunks.

## Wrong answers at the MISS (the five cases of plan §1.2)

| product | question | answer given | where the answer is |
| :--- | :--- | :--- | :--- |
| `…b07r8pr5yz` | What comes in the box? | "does not contain specific information" | `#chunk-5`; retrieved `#chunk-0` |
| `…b07r8pr5yz` | How long does a full charge take? | "You don't know" | `#chunk-0`, `#chunk-5`; retrieved `#chunk-1` |
| `…b07b63r768` | Are these headphones foldable? | "No, … does not contain information" | `#chunk-1` |
| `…b07b63r768` | What is the standby time? | "I don't know." | `#chunk-1` |
| `…b07b63r768` | Is a carrying case included? | "does not mention" | `#chunk-1`; retrieved `#chunk-3` |

## Self-support (`tier2_probe.py B`: 30 validation questions, seed 7)

**16 / 30** fresh answers score `S_lex ≥ 0.6` against their own evidence (POLICY 9 / 13, SPEC 7 / 17).
Missing most often: "context" 20, "based" 11, "answer" 9, "according" 9, "yes" 5.

## Pairs on `product-electronics-b07b63r768` (`product_pairs.py`)

**Traps (Q2 must not be a TIER2_HIT): 0 of 8 became a hit.** T1 and T7 answered Q2 from the author's own earlier
Tier-1 entry for this product; T2 was refused by the support gate (similarity 0.907, `S_lex` 0.43); T3 – T6 by τ
(0.832, 0.778, 0.821, 0.632; T5's `S_lex` was 0.69, so the gate would have served it); T8 by the namespace.

**Paraphrases (Q2 should be a TIER2_HIT): 0 of 8 became a hit.**

| pair | similarity | refused by |
| :--- | ---: | :--- |
| P1 ANC | 0.610 | τ |
| P2 wired | 0.786 | τ |
| P3 range | 0.842 | τ (`S_lex` 1.00) |
| P4 charge time | 0.905 | gate (`S_lex` 0.50: Q2 retrieved one chunk without "around") |
| P5 foldable | 0.905 | gate (`S_lex` 0.34; the cached answer was wrong) |
| P6 bag | 0.865 | gate (`S_lex` 0.08: Q2 retrieved `#chunk-3`) |
| P7 pairing | 0.775 | τ |
| P8 battery capacity | 0.748 | τ (`S_lex` 1.00) |

## Pairs on `product-electronics-b07r8pr5yz` (`tier2_probe.py A`)

2 of 8 paraphrases became a TIER2_HIT (frequency range, similarity 0.867, `S_lex` 1.00; earcups, 0.975, 0.62).
2 were refused by τ (0.680, 0.758) and 4 by the gate (similarity 0.854 – 0.947, `S_lex` 0.33 – 0.46).

## After ADR-020, for reference

Category probe: 0 policy chunks of another category. Condition-routing probe: 99 / 121 and 9 / 13 with and
without the condition word; 24 / 43 synonyms.
