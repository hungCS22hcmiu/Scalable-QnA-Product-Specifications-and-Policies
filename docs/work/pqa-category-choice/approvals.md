# Approvals — pqa-category-choice

Human decisions taken in this investigation, in the author's own words. An investigation writes no
source, so none of these unlocks implementation.

| Date | Decision | Author's words | Invalidates |
| :--- | :--- | :--- | :--- |
| 2026-10-03 | Open this investigation **out of phase order** — Phase 3 groundwork while the banner reads Phase 1 | "yes" — to *"open the category investigation now, or go back to Phase 1 first?"* | none |
| 2026-10-03 | **Reject** the leaf-category recommendation (`inkjet_printers`, `quadcopters_&_multirotors`, `chairs`, `mattresses`); require recognisable departments | *"too specific and not really common … I want something related to Furniture, Electronics, phone, laptop"* | none |
| 2026-10-03 | Keep the six department leaf files on disk in **`data/raw/pqa/`**, with **`data/raw/`** added to `.gitignore` first | "ok làm luôn" | none |
| 2026-10-03 | Survey alternative sources, then measure ePQA | "ok làm luôn, kiểm tra ePQA, nhưng trước đó cố tìm thêm nhiều source khác" | none |
| 2026-10-03 | **Exploratory Ollama runs may proceed under yellow pressure**; green is required only for citable thesis measurements | *"chỉ cần về green khi thiết lập đo để lấy số liệu cho thesis thật, còn testing thì không cần đợi tắt app"* | none — exploratory numbers are labelled not citable |
| 2026-10-03 | Stop the six stale `rag.server` processes sharing port 50051 | "ok tắt hết 6 cái rag.server đi" | none — no citable run existed |
| 2026-10-04 | **Approve the four-department set** (Revision 1): phones ← `unlocked_cell_phones`; laptops ← `traditional_laptops`; electronics ← `led_&_lcd_tvs` + `over-ear_headphones`; furniture ← `chairs` + `home_office_desks` → **ADR-002** | "Duyệt 4 department truoc" | none — no runs on `v1` |
| 2026-10-04 | Run `/verify`, `/ai-review` and an `impact-analyst` pass before closing | "ok" — to the four-step close plan, impact analysis included | none |
| 2026-10-04 | **Accept ADR-002 under this task's S scope** despite the ladder classing "anything measured" as L (see the finding below) | "ok" — to *"Do you accept ADR-002 going through the S process?"* | none — `impact-analyst` found no `v1` run, no `manifest.yaml`, no frozen value touched |
| 2026-10-04 | Keep the short illustrative PQA question quotations in `spec.md`, treated as quotation in the same way `data-card.md` §3 quotes, not as redistribution. Bulk examples in the JSON results were removed (`review.md` #1) | "ok" — same reply | none |

## Scope-ladder finding

This task was opened at **S** as an investigation that answers a question and writes no source. It
**closed by recording a frozen data decision** (ADR-002) that defines the corpus every later
measurement runs on. The ladder classes "anything measured" as **L**: spec → impact → design → opus
design-review → plan. This task had only the impact step, added at the end at the author's request.
It is accepted here because no `v1` run exists, and because the parts of the decision that carry
real design risk — the selection rule, the answerability filter, and the paraphrase generation —
were deliberately left open for `super-plan.md` items 3.2 and 3.4, which go through their own
scope. **The lesson for the ladder:** an investigation that ends in a data ADR has crossed into
L territory. Next time, close the investigation on its answer, and open the decision as its own
task at the scope it warrants.

## Taken by Claude as a default, open to reversal

- **ADR numbering.** The department decision is **ADR-002**, and **ADR-001 is left reserved** for the
  co-hosted-measurement decision, because Phase 1's exit criterion names that number. The author
  was asked and had not chosen; this is the option that changes nothing else.

## Not approved — still open

- A `source_category` field on product records (a schema change to `data-card.md`'s sketch).
- Renaming the stale `TODO(W8)` markers in `data-card.md`.
- The answerability criterion for item 3.2, and its validation against ePQA's 194 overlapping questions.
- The paraphrase-generation model, prompt and paraphrases-per-seed count.
- A `/bugfix` for `rag/src/rag/server.py` binding with gRPC's default `SO_REUSEPORT`.
