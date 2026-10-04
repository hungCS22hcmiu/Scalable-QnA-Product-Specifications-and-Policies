# Review — pqa-category-choice

**Date:** 2026-10-04 · **Diff:** `.gitignore`, `docs/data-card.md`, `docs/decisions.md`, plus the
untracked trail `docs/work/pqa-category-choice/`. Nothing under `gateway/`, `rag/`, `contracts/` or
`experiments/` changed.

**Reviewers.** Neither routing rule applied: no `interfaces.md` surface was touched, and this is not a
scope-L design. So `contract-reviewer` ran as a general pass, and `impact-analyst` was added at the
author's request to check ADR-002's blast radius. Each read the rules from their own documents.
Findings marked CONFIRMED were re-checked by hand against the files before being recorded here.

**Verdict.** No frozen value is touched (`config.py` embedding / chunking / `top_k`, C/K = 0.25,
τ_s = 0.6, the doc-id prefix rule). No seam field and no eviction region is affected. ADR-002's
`Invalidates: none` holds: `experiments/results/` holds only `.gitkeep`, and no `manifest.yaml` exists.

## Findings, most severe first

| # | Finding | Status | Resolution |
| :---: | :--- | :---: | :--- |
| 1 | **Licence — redistribution.** `probe_results.json` and `scripts/novelty_embed.json` carried verbatim PQA questions in their `examples` fields. Committing them to the public remote would redistribute PQA content, which `data-card.md` §1 records as not granted | CONFIRMED | **Fixed.** Both `examples` fields removed and replaced by a note. A scan found no string over 25 characters left except hashes and file names. *Judgement left to the author:* `spec.md` still quotes a limited number of short questions as illustration, the same practice `data-card.md` §3 already follows |
| 2 | **The gate cannot check G5.** `data-card.md:8` now requires all five criteria (G1–G5), but `experiments/scripts/corpus_gate.py` implements only G1–G4 (`criteria = [g3, g4]` at `:490`; `passed = … g3.passed and g4.passed` at `:524`). A passing gate run says nothing about G5, the only lever against the support gate's residual, and it cannot be fixed after the freeze | CONFIRMED | **Fixed in the docs:** a warning in `data-card.md` §7's implementation note to check G5 by hand before any freeze. The code gap is already tracked as `super-plan.md` item 3.5 and is not this task's |
| 3 | **ADR-002 overstated its rationale.** It said return windows "differ across the four", but laptops and electronics share 30 days. Per-category warranty windows (`data-card.md` §2 requirement 2) hold only as furniture against the rest, and only from secondary sources | CONFIRMED | **Fixed.** The rationale now says three distinct values, the shared 30 days, and the weak, secondary-sourced warranty evidence |
| 4 | **`data-card.md:19` read as current.** *"policy corpus 5–10 → **8** documents"* sat beside the new ~13 | CONFIRMED | **Fixed.** Annotated as raised to ~13 by ADR-002 |
| 5 | **Pools filtered for a near-duplicate pair bias the natural re-ask rate upward.** The pools require at least one near-duplicate pair, so the selected products are more redundant than the unfiltered 5–14 per 100 that §3 reports. Citing the unfiltered rate while sizing strata from filtered pools would mis-state natural redundancy | PLAUSIBLE | **Accepted, follow-up.** When item 3.2 freezes the selection rule, record the filtered re-ask rate beside the unfiltered one |
| 6 | **The department name is embedded.** `rag/src/rag/ingest.py:48` writes `Category: {category}` into the embedded text, so TVs and headphones both embed as "electronics". Not a frozen value and no defect today | CONFIRMED | **Accepted, follow-up for item 3.1:** any leaf provenance (the open `source_category` question) stays metadata-only and never enters embedded text, or retrieval shifts silently |
| 7 | **`interfaces.md:287` is stale:** "checked … alongside G1–G3", while the prefix check is G4 and G5 exists. Predates this task | CONFIRMED | **Follow-up.** A contract edit needs its own version bump, outside this diff |
| 8 | **dev-v0 fixtures name categories that no longer exist** (`headphones`, `kitchen`): `experiments/scripts/verify_admission.sh:28-29`, `experiments/k6/mu_hit.js:72-80`, `experiments/scripts/load_burst.py:22`. `lane.go` accepts an unknown `product_id` without error | CONFIRMED | **Follow-up** at items 3.6 / 7.2, when fixtures move to `v1` |
| 9 | **`experiments/scripts/fetch_corpus_v1.py:59-62` still maps retired Amazon-Reviews-2023 categories** | CONFIRMED | **Follow-up.** Replaced by the PQA builder, item 3.1 |
| 10 | **`Final_Proposal.md` (gitignored; the framing authority) contradicts ADR-002:** `:430` and `:467` say 8 self-authored policy documents; `:431` says only one workload half can be real, with A/C "sampled" on `inkjet_printers` figures; `:570` says four gate criteria | CONFIRMED | **Follow-up for the next prose pass.** Submitted prose; not edited here |
| 11 | ADR-001 is a placeholder while `super-plan.md:107` names it | — | **By design.** Reserved for the co-hosted-measurement decision (`approvals.md`) |

No finding is open. Findings 1–4 are fixed in this diff; 5–10 are accepted with a named follow-up;
11 is intended.
