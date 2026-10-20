# Approvals — policy-documents

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | yes (`/approve impact`; no frozen value changed, no run invalidated, `impact.md` §2) | 2026-10-20 | — |
| contract       | if §B/§D | n/a — no `interfaces.md` surface changes (`impact.md` §5) | | |
| experiment     | if measured | yes (`/approve experiment`), on `design.md` draft 2 as written, i.e. **with the proposed answers** to `spec.md` 1–10. Required because this item writes half of the measured corpus and fixes the inputs of G1, G2, G5, RQ2a's condition pairs, the lane split and the policy namespace (`impact.md` §6). No run happens here. Invalidates: none — no runs yet | 2026-10-20 | ADR-012 (proposed) |
| implementation | always   | yes (`/approve implementation`), on `plan.md` draft 2 and the proposed answers; impact and experiment approved first, contract n/a | 2026-10-20 | ADR-012 (proposed) |

**Open questions** (`spec.md`, 1 to 10): not answered explicitly yet. `design.md` draft 2 and
`plan.md` draft 2 use the proposed answer to each, and the experiment approval covers the design as
written with those answers. **An answer that differs from its proposal changes the measured design
and needs the experiment row approved again.** Questions 9 and 10 were added after the design
review.

**Design review:** done, verdict *sound, with changes*; every finding accepted and merged into
`design.md` draft 2 (`review.md`).

**Invalidates:** none — no runs exist (`experiments/results/` holds only `.gitkeep`); `v1` is not
frozen; `data/dev-v0/` is not touched.

**Blocker before plan step 1:** this session denies Read and Write on `data/`. Writing
`data/policies-v1/` and reading the 152 titles (U8) need the author to grant that access.

**Document read-through (P8):** none yet. One line per document goes here when the author approves
it.

**2026-10-21 — two answers from the author.** (1) **Renewed laptops: 90 days**, the Amazon Renewed
Guarantee's standard term as read on 2026-10-03 (three re-fetches gave HTTP 503); the conflict on
some Renewed items (30 days plus an 11-month warranty) goes into the data card. This is the
proposal, so the experiment approval stands. (2) **Data access: narrow the deny rule** in
`.claude/settings.json` to `Read(./data/raw/**)`, `Read(./data/v1-draft/**)`, `Read(./data/v1/**)`,
keeping PQA text out of the session and opening `data/policies-v1/`. Claude's edit was refused by
the auto-mode safety check, so **the author makes this edit**; until then plan steps 1, 2 (warranty
makers) and 4 (placing the documents) wait.

**2026-10-21 — two more answers from the author**, after `make policy-sources` (counts only, read
through `select_pqa.iter_selection`). (1) **The maker rule is amended** before any maker page was
fetched: the Brand field, else the title's first word (`evidence/sources.md`). (2) **The 10 products
whose titles can contradict a policy document stay** (phones 7: Renewed 2, "International Version"
4, "No warranty" 4, one title can hold several; electronics 2 Renewed; laptops 1 Renewed). ADR-011's
152 stay frozen. **Carried to 3.4:** no policy-lane or stratum-D query names one of them; the data
card records them as a C1 limitation. Neither answer changes the measured design approved for 3.3.
