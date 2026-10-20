# Approvals — pqa-thick-tail-selection

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | yes (`/approve impact`; no frozen value changed, no run invalidated) | 2026-10-19 | — |
| contract       | if §B/§D | n/a — no `interfaces.md` surface changes (`impact.md`) | | |
| experiment     | if measured | yes (`/approve experiment`), on `design.md` draft 3 as written, i.e. with the proposed answers. Required because `K`, the capacity and G1 / G2 come from this output. Invalidates: none — no runs yet | 2026-10-20 | ADR-011 (proposed) |
| implementation | always   | yes (`/approve implementation`), on `plan.md` draft 3 and the proposed answers; impact and experiment approved first | 2026-10-20 | ADR-011 (proposed) |

**Open questions** (`spec.md`, 1 to 11): not answered explicitly yet. The experiment approval
covers the design as written, which uses the proposed answer to each; an answer that differs from
its proposal changes the measured design and needs this row approved again. **Design review:** done, verdict *sound
with changes*, all findings merged into design draft 3 (`review.md`).

**Invalidates:** none — no runs exist (`experiments/results/` holds only `.gitkeep`). As an artefact,
the 3.1 manifest `bf0feb48…` (`data/pqa-manifest.json`, committed in `33a1a9d`) is replaced when the
builder gains the `fields_conflict` flag (only if open question 3 is "exclude").

**Pins and constants:** a change to any **new** constant in `design.md` §2 (`COVERAGE`,
`GENERIC_DF`, `MIN_ANSWERABLE`, `QUOTA`, `SEED`, `AUDIT`), to the probe-pool pins (§2.6), to the ePQA
join pin (§3.1), or any fallback step of §2.3, after the plan step 12 commit, needs a line here.
The seed and the answerability rule are never changed to fill a quota or to pass G1.
