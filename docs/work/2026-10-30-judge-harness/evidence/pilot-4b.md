# Pilot: Qwen 3.5 4B as the reference writer, on the 30 sheet rows (2026-11-01)

**Diagnostic, citable: no.** Not part of the frozen protocol: it does not replace Entry 2's reference set, and no
verdict ran. The author asked for it after step 4.7's stop rule fired (design.md §4). Question and answer texts stay in
`private/pilot-4b/` (gitignored); this file holds numbers and hashes only.

## Setup

- **Rows:** the 30 rows of `private/sufficiency-v2.md`, in its order. The gold chunks come from `retrieve.fetch_by_ids`,
  in the index's order, and the prompt is `generate._build_prompt`, unchanged (prompt sha256 `3e224f45…`). The
  author's `sufficient` marks are kept as they are.
- **Arms**, each with `think: false`, `num_ctx` 8192, `temperature` 0 and `seed` 20261101 (`pilot_4b.py`):
  - `4b-t0`: `qwen3.5:4b-q4_K_M`, digest `2a654d98e6fb…`. Index sha256 `2b10f445…`.
  - `4b-t0-repeat`: the same again. All 30 texts are byte-identical to `4b-t0`.
  - `2b-t0`: `qwen3.5:2b-q4_K_M` at temperature 0, a control that separates the model from the temperature. Index
    sha256 `1ddbb151…`.
- **Baseline:** Entry 2's references (`qwen3.5:2b`, temperature 1.0), marked by the author.
- **Memory:** pressure 1 before each arm, and 1 to 2 during the 4B arms. Ollama reported 3.30 GB for 4B at
  `num_ctx` 8192. Median time per reference: 4B 5.0 s, 2B 3.0 s.

## Marks

The 2B (temperature 1) column is the author's. The two pilot columns are **the main session's provisional reading**,
made with the same rule. It is not blind: it was made after the author's 2B marks were known, and the reader is Claude,
the model that wrote the workload (ADR-013). The author's blind marks would replace it.

| Row | Stratum | 2B, T 1 (author) | 4B, T 0 (provisional) | 2B, T 0 (provisional) | Note |
| :---: | :--- | :---: | :---: | :---: | :--- |
| 12 | B-within | no | **yes** | no | the opened-phone fee: 4B applies the $45 rule; 2B at T 0 says "No …, however yes" |
| 17 | A | no | **no** | no | all three miss that the power adapter the evidence lists is the adapter asked about |
| 19 | A | no | **yes** | no | 4B: LPDDR3 is a kind of SDRAM; 2B at T 0: "not SDRAM" |
| 21 | B-within | no | **yes** | yes | the opened-phone fee |
| 24 | B-within | no | **yes** | no | the opened-phone fee |
| 25 | A | yes | **no?** | no? | the author marked the evidence insufficient; 4B and 2B at T 0 both answer "80" from "up to 80 zones" |
| 4 | C | yes | yes? | yes | 4B adds "to the original payment method", which the evidence does not state |
| 23 | C | yes | yes? | yes | 4B lists items left in the box as a refusal reason; the evidence says only that they are not returned |
| the other 22 | | yes | yes | yes | |

**Counts of `reference right: no`, of 30:**
- **2B, T 1 (author):** 5.
- **4B, T 0:** 1 if row 25 is read as right, 2 if read by the author's row-25 marks, 4 if the borderline rows 4 and 23
  also count. Wilson 95 %: 1 → [0.6, 16.7], 2 → [1.8, 21.3], 4 → [5.3, 29.7].
- **2B, T 0:** 4, or 5 with row 25.

## Sampling assumptions

- **The draw.** Random with seed 7, but stratified: 10 drawn from B-within, then 20 from the other `answerable: true`
  pairs. So B-within is 17 of 30 against 21 % of the split, C is 2, and D, B-cross and `answerable: false` are absent.
  The raw rate is not a split-wide estimate.
- **Clusters.**
  - Five rows are one template, the opened-phone restocking fee: rows 2, 5, 12, 21 and 24.
  - Six rows share one gold document.
  - Rows 14 and 20 are near-duplicate questions.
  - So the rows are not independent, the effective sample is smaller than 30, and the Wilson intervals above are too
    narrow.
- **The same rows found the problem and test the fix.** Three of the four fixes are one pattern. A fresh draw (another
  seed), marked blind by the author, is needed for an unbiased estimate.
