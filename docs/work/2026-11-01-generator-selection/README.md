# Generator comparison (2026-11-01) — diagnostic, citable: no

The author asked for it after the judge-harness task's step 4.7 stopped on 5 wrong references in 30
(`docs/work/2026-10-30-judge-harness/design.md` §4). It compares six local generators on one fixed set and
recommends one. **Nothing frozen changed:** `rag.config`, the reference set, the judge and the pre-registration
are untouched, and no ADR is written until the author approves a change. Answer texts stay in
`evidence/private/` (gitignored, Amazon-PQA). This file holds numbers and row numbers only.

## Setup

- **Rows:** the 30 rows of the judge-harness `sufficiency-v2.md`, in order. Each answer is generated from all the
  chunks of the row's gold documents (`retrieve.fetch_by_ids`, in the index's order), with the served prompt
  `generate._build_prompt` (sha256 `3e224f45…`).
- **Options:** `num_ctx` 8192, `temperature` 0, `seed` 20261101 for every model. The other decoding values are
  each model's defaults (below). `think: false` is sent when `/api/show` lists `thinking`.
- **Order:** one model at a time (`compare_generators.py`); all models unloaded before each.
- **Environment:** Ollama 0.33.2, the ADR-017 runner settings, Redis up, `nomic-embed-text` resident beside the
  model. Every model was Q4_K_M.

| Tag | Digest | Parameters | Family | Defaults besides the options |
| :--- | :--- | :---: | :--- | :--- |
| `qwen3.5:2b-q4_K_M` (served today) | `124a03c34777` | 2.3B | qwen35 | top_k 20, top_p 0.95, presence_penalty 1.5 |
| `qwen3.5:4b-q4_K_M` | `2a654d98e6fb` | 4.7B | qwen35 | top_k 20, top_p 0.95, presence_penalty 1.5 |
| `gemma4:e2b-it-q4_K_M` | `7fbdbf8f5e45` | 5.1B (vision and audio included) | gemma4 | top_k 64, top_p 0.95 |
| `granite4.2:3b-q4_K_M` | `40577dc168a3` | 3.7B | granite | top_p 0.95 |
| `phi4-mini:3.8b-q4_K_M` | `78fad5d182a7` | 3.8B | phi3 | none |
| `ministral-3:3b-instruct-2512-q4_K_M` | `f04aa1c738f6` | 3.8B | mistral3 | none (its default temperature 0.15 is overridden) |

## Results

Wrong answers are read against the gold evidence with the author's rule from the sheet. **The reading is the main
session's (Claude), provisional and not blind.** The only human marks are the author's, on Qwen 2B at
temperature 1. Row 25 is counted wrong when an answer asserts "80 local dimming zones", since the author marked
that evidence insufficient. It is counted right when the answer quotes or hedges "up to 80 zones".

| | Qwen 2B (T 1, author) | Qwen 2B (T 0) | **Qwen 4B** | Gemma 4 E2B | Granite 4.2 3B | Phi-4-mini | Ministral 3 3B |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Wrong, of 30 | 5 | 5 | **2** | 2 | 5 | 4 | 3–4 |
| Wrong rows | 12 17 19 21 24 | 12 17 19 24 25 | **17 25** | 17 23 | 4 8 17 23 25 | 10 17 19 25 | 11 17 23 (8) |
| Borderline rows | — | — | 4 23 | — | 24 27 | 8 | 8 |
| Invented facts | 0 | 0 | 0 (2 small extra details) | 0 | 0 | **1** (row 19) | **2** (rows 11, 23) |
| Wrong "not stated" refusals | 3 | 2 | **0** | 1 | 2 | 1 | 0 |
| Abstains on row 11 (no evidence) | yes | yes | yes | yes | yes | yes | **no** |
| Multi-part row 23 complete | yes | yes | yes | refuses | refuses | yes | **no** |
| Thinking off (checked) | — | yes | yes | yes | **no: reasoning shown in 3 rows** | n/a | n/a |
| Repeats byte for byte | — | yes (2 runs) | yes (2 runs) | not run twice | not run twice | not run twice | not run twice |
| Decode, median tok/s | — | 35.9 | 16.9 | 33.2 | 25.3 | 23.0 | 25.0 |
| Latency, median (max) s | — | 2.9 (10.3) | 5.4 (12.0) | 2.5 (4.7) | 4.5 (**46.2**) | 4.0 (7.7) | 4.3 (9.9) |
| Memory, GB: Ollama / RSS / footprint | — | 1.70 / 2.83 / 3.01 | 3.38 / 4.17 / 4.70 | **7.01** / 5.06 / 1.28 | 3.05 / 2.80 / 0.71 | 3.70 / 3.43 / 1.10 | 3.26 / 3.62 / 1.71 |
| Peak pressure in the 30-row run | — | 2 | 2 | 2 | 1 | 1 | 1 |
| Runner slots (argv `-np`, `/props`) | — | 1, 1 | 1, 1 | 1, 1 | 1, 1 | 1, 1 | 1, 1 |
| 3 requests at once vs one by one, s | — | 9.6 vs 9.2 | 21.0 vs 19.0 | 7.6 vs 8.4 | 14.4 vs 14.3 | 11.5 vs 11.8 | 13.8 vs 13.9 |

- **Memory.** No single figure is right for every architecture. `footprint` leaves out the weights that are mapped
  from file, which is why Gemma 4 shows 1.28 GB. RSS leaves out some private buffers. Ollama's `size` is its own
  allocation. Read the largest of the three against the ~6 GB ceiling. The memory figures come from a separate probe
  with the longest prompt (767–1,416 tokens). Footprint is still the right tool for growth over time (ADR-017).
- **Thinking.** Every thinking-capable model returned an empty `thinking` field with `think: false`. Qwen and Gemma
  filled it when asked with `think: true`, so they honour the switch. Granite did not fill it, and wrote
  `…</think>` reasoning of 2,264–4,707 characters into the answer itself in rows 8, 24 and 27.
- **Concurrency.** Every runner has one slot, and three requests sent together finish one after another. So no
  candidate changes ADR-003's one served slot.
- **Row 17** (a question about which accessories come in the box) fails for all seven. Each model reads the power
  adapter that the evidence lists as not being the adapter the question names.

## Recommendation: Qwen 3.5 4B (`qwen3.5:4b-q4_K_M`)

- **Answer quality:**
  - It has the fewest wrong answers of the candidates that fit the memory limit: 2 of 30, against 5 for today's 2B.
  - It removes every wrong "not stated" refusal: the opened-phone fee in rows 12, 21 and 24.
  - It invents no fact, and it is complete on the multi-part rows.
  - A 2B control at temperature 0 keeps the errors, so the gain is the model, not the temperature.
- **Memory:** about 4.7 GB at most, under the ~6 GB ceiling. Pressure peaked at 2.
- **Stable inference:** its thinking switch is honoured and checked, and it repeated byte for byte across two
  separate runs.
- **Judge independence:** it is the generator's own family, not Gemma's, so ADR-022's judge stays valid.
- **Cost:** it is the slowest candidate. Decode is 16.9 against 35.9 tok/s, and latency 5.4 against 2.9 s, so μ_gen
  roughly halves and every Phase 6 replay takes about twice as long.

**Not chosen:**
- **Gemma 4 E2B** ties on errors, but it needs **7.0 GB**, over the ceiling. It is also Gemma, the judge's family,
  so its errors would correlate with the judge's and would force a new judge.
- **Ministral 3 3B** makes unsupported claims: it answers row 11 where the evidence is missing, and adds refusal
  conditions in row 23.
- **Phi-4-mini** invents "LPDDR4" in row 19.
- **Granite 4.2 3B** does not honour `think: false`, and one answer took 46 s.

## Limits of this comparison

- The 30 rows are the rows that found the problem. They are stratified (B-within 17 of 30), and 5 of them are one
  template, so they are not independent. A fresh sample marked blind by the author is the unbiased check.
- Every pilot mark is Claude's, not blind, and Claude wrote the workload (ADR-013). The author's blind marks on the
  chosen model replace them.
- The memory figures are with `nomic-embed-text` resident and Redis up, but without the gateway and `rag.server`
  processes. `make env-check` with the full stack is the real check.
- All timing numbers come from a co-hosted machine at pressure 1 to 2, so none is citable.
